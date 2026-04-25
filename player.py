# -*- coding: utf-8 -*-
"""
player.py  -  Player implementations for the Hex board game.
Only the classes actually used by the application are kept:
  - GuiPlayer      : human player driven by GUI clicks
  - AlphaBetaPlayer: AI using alpha-beta search with iterative deepening
"""

import itertools
import math
from abc import ABC, abstractmethod
from math import inf
from timeit import default_timer

from board import SWAP_MOVE


# ── Abstract base classes ─────────────────────────────────────────────────────

class Player(ABC):
    def __init__(self, player_num):
        super().__init__()
        self.player_num = player_num

    @abstractmethod
    def move(self, board):
        pass

    @abstractmethod
    def is_human(self):
        pass


class HumanPlayer(Player, ABC):
    def is_human(self):
        return True


class ComputerPlayer(Player, ABC):
    def is_human(self):
        return False


# ── Human player (GUI clicks) ─────────────────────────────────────────────────

class GuiPlayer(HumanPlayer):
    """
    Human player whose moves are injected directly by the GUI click handler.
    The move() method is never called in the current GUI architecture
    (HexGameApp._on_hex_click writes directly to the board).
    The class is kept so isinstance checks work correctly.
    """
    def set_gui(self, gui):
        self.gui = gui

    def move(self, board):
        pass   # handled by HexGameApp._on_hex_click


# ── AI player: Alpha-Beta with iterative deepening ────────────────────────────

class AlphaBetaPlayer(ComputerPlayer):
    """
    Minimax AI with:
      - Alpha-beta pruning
      - Killer-move heuristic
      - Transposition table
      - Iterative deepening (when search_depth == -1)
      - Configurable move-ordering via a fast sorter heuristic

    Parameters
    ----------
    player_num   : 1 or -1
    heuristic    : Heuristic used to score leaf nodes (TwoDistanceHeuristic)
    search_depth : Fixed depth; use -1 for iterative deepening
    max_time     : Time budget in seconds (only used when search_depth == -1)
    sorter       : Optional Heuristic used to order candidate moves for
                   better pruning (ChargeHeuristic)
    killer_moves : Number of killer moves remembered per depth level
    """

    def __init__(self, player_num, heuristic, search_depth=-1,
                 max_time=0, sorter=None, killer_moves=6):
        super().__init__(player_num)
        self.search_depth = search_depth
        self.max_time     = max_time
        self.heuristic    = heuristic
        self.sorter       = sorter
        self.killer_moves = killer_moves

        if search_depth < 0 and max_time <= 0:
            raise ValueError('AlphaBetaPlayer needs either search_depth or max_time')

    # ── Public entry point ────────────────────────────────────────────────

    def move(self, board):
        transposition_table = {}
        if self.search_depth < 0:
            val, move_list = self.iterative_deepening(board, self.max_time)
        else:
            val, move_list, _ = self.alpha_beta(
                board, self.search_depth, -inf, inf,
                self.player_num, transposition_table, sorter=self.sorter
            )

        # Resign only if the position is provably lost; otherwise play best move
        if move_list is None or val * self.player_num <= -10000:
            board.resign()
        else:
            board.play(*(move_list[0]))

    # ── Alpha-Beta search ─────────────────────────────────────────────────

    def alpha_beta(self, board, depth, alpha, beta, player, transposition_table,
                   killer_moves=None, sorter=None, start_time=None, max_time=None):

        # Initialise or extend the killer-moves table
        if killer_moves is None:
            killer_moves = [
                [(board.size // 2, board.size // 2)] * self.killer_moves
                for _ in range(depth + 1)
            ]
        elif len(killer_moves) < depth:
            killer_moves.extend(
                [(board.size // 2, board.size // 2)] * self.killer_moves
                for _ in range(depth + 1 - len(killer_moves))
            )

        # Base case: leaf node or game over
        if depth == 0 or board.winner != 0:
            return self.heuristic.get_value(board), None, False

        # Generate all legal moves
        options = [
            (y, x)
            for (y, x) in itertools.product(range(board.size), repeat=2)
            if board[y][x] == 0
        ]
        if board.swap_rule and len(board.move_list) == 1:
            options.append(SWAP_MOVE)

        # Sort moves using the fast sorter heuristic (better pruning)
        if sorter is not None:
            child_val = sorter.get_child_values(board)
            options.sort(
                key=lambda m: 0 if m == SWAP_MOVE
                else child_val[m[0]][m[1]] * -board.turn
            )

        # Prepend killer moves so they are tried first
        options  = itertools.chain(killer_moves[depth], options)
        searched = set()

        value     = -inf if player == 1 else inf
        best_move = None
        time_up   = False

        for move in options:
            if board[move[0]][move[1]] != 0 or move in searched:
                continue
            searched.add(move)
            board.play(*move)
            board_state = board.hashable()

            if transposition_table is not None:
                if board_state in transposition_table:
                    move_val, move_list = transposition_table[board_state]
                else:
                    move_val, move_list, time_up = self.alpha_beta(
                        board, depth - 1, alpha, beta, -player,
                        transposition_table,
                        killer_moves=killer_moves, sorter=sorter,
                        start_time=start_time, max_time=max_time
                    )
                    if not time_up:
                        transposition_table[board_state] = (move_val, move_list)
            else:
                move_val, move_list, time_up = self.alpha_beta(
                    board, depth - 1, alpha, beta, -player,
                    transposition_table,
                    killer_moves=killer_moves, sorter=sorter,
                    start_time=start_time, max_time=max_time
                )

            board.undo()

            if not time_up:
                if player > 0:
                    if move_val > value:
                        value     = move_val
                        best_move = (move, move_list)
                    alpha = max(alpha, value)
                else:
                    if move_val < value:
                        value     = move_val
                        best_move = (move, move_list)
                    beta = min(beta, value)

                # Alpha-beta cutoff
                if alpha >= beta:
                    if move not in killer_moves[depth]:
                        killer_moves[depth].append(move)
                        killer_moves[depth].pop(0)
                    break

            # Time-limit check
            if max_time and (time_up or (default_timer() - start_time > max_time)):
                time_up = True
                break

        return value, best_move, time_up

    # ── Iterative deepening ───────────────────────────────────────────────

    def iterative_deepening(self, board, max_time):
        """
        Run alpha_beta at depth 1, 2, 3, … until the time budget is used.

        The threshold for starting the next depth is 0.5 (50% of budget spent).
        This is more aggressive than the former 0.2 threshold, which caused the
        AI to stop iterating after using only 20% of the allotted time — meaning
        it rarely searched beyond depth 3.  With 0.5 the AI attempts deeper
        searches, improving move quality across the whole game.
        """
        start_time = default_timer()
        depth      = 1
        val        = 0
        move_list  = None
        time_up    = False

        while not time_up:
            transposition_table = {}
            next_val, next_move_list, time_up = self.alpha_beta(
                board, depth, -inf, inf, self.player_num,
                transposition_table,
                sorter=self.sorter,
                start_time=start_time, max_time=max_time
            )

            # Only commit results from fully completed searches
            if not time_up:
                val       = next_val
                move_list = next_move_list
                depth    += 1

            # Stop if 50% of the budget has been spent (previously 0.2 = 20%).
            # Raising this lets the AI attempt deeper depths much more often,
            # strictly increasing move quality without increasing wall-clock time.
            elapsed_ratio = (default_timer() - start_time) / max_time
            if elapsed_ratio > 0.5:
                time_up = True

            # Stop early if a definitive result is already known
            if abs(val) == math.inf:
                time_up = True

        return val, move_list
