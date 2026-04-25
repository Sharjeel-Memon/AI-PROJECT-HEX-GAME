# -*- coding: utf-8 -*-
"""
GUI.py  –  Hex Game Graphical Interface
Draws the board using tkinter Canvas polygons (no PNG tiles needed for board cells).
Supports: Human vs Human, Human vs AI with Easy / Medium / Hard difficulty.
Always 11×11. Auto-launches in GUI mode.
"""

import math
import os
import threading
from tkinter import *

from board import HexBoard
from heuristic import TwoDistanceHeuristic, ChargeHeuristic
from player import GuiPlayer, AlphaBetaPlayer

try:
    import pygame
except ImportError:
    pygame = None

# ── Visual constants ──────────────────────────────────────────────────────────
BG          = "#282828"
EMPTY_CLR   = "#c8c8c8"
BLUE_CLR    = "#2244cc"
RED_CLR     = "#cc2222"
WIN_CLR     = "#ffdd44"     # winning-path highlight
OUTLINE_CLR = "#111111"
LABEL_CLR   = "#ffffff"
BLUE_BORDER = "#2244cc"
RED_BORDER  = "#cc2222"

BTN_BG   = "#3a3a3a"
BTN_FG   = "#ffffff"
BTN_ABG  = "#555555"
EXIT_BG  = "#aa3333"
EXIT_ABG = "#cc4444"

HEX_R = 28          # pointy-top hexagon radius (px)
BOARD_SIZE = 11

AI_DIFFICULTIES = {
    "Easy": {
        "description": "Fast moves, shallow search",
        "search_depth": 1,
        "max_time": 0,
    },
    "Medium": {
        "description": "Balanced strength and speed",
        "search_depth": 2,
        "max_time": 0,
    },
    "Hard": {
        "description": "Strongest AI, slower moves",
        "search_depth": -1,
        "max_time": 10,
    },
}


# ── Geometry helpers ──────────────────────────────────────────────────────────
_SQ3 = math.sqrt(3)

def _col_step():   return _SQ3 * HEX_R        # px between column centres
def _row_xstep():  return _SQ3 * HEX_R / 2    # x shift per row (parallelogram)
def _row_ystep():  return 1.5 * HEX_R          # px between row centres

def hex_center(row, col, x_off, y_off):
    """Pixel centre of hex (row, col) for a pointy-top hex grid."""
    x = x_off + col * _col_step() + row * _row_xstep()
    y = y_off + row * _row_ystep()
    return x, y

def hex_poly(cx, cy, r=HEX_R):
    """Flat [x0,y0,x1,y1,...] for a pointy-top hexagon centred at (cx,cy)."""
    pts = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        pts.append(cx + r * math.cos(angle))
        pts.append(cy + r * math.sin(angle))
    return pts

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


# ── HexBoardCanvas ────────────────────────────────────────────────────────────
class HexBoardCanvas:
    """
    Renders an 11×11 Hex board onto a tkinter Canvas using drawn polygons.
    Call update() to refresh colours from the HexBoard object.
    """

    def __init__(self, canvas: Canvas, board: HexBoard, x_off: int, y_off: int,
                 click_cb=None):
        self.canvas   = canvas
        self.board    = board
        self.x_off    = x_off
        self.y_off    = y_off
        self.click_cb = click_cb          # callback(row, col) on hex click
        self._ids     = {}                # (row,col) → canvas polygon id

        self._draw_borders()
        self._draw_cells()
        self._draw_labels()

    # ── Private drawing ───────────────────────────────────────────────────
    def _draw_borders(self):
        """Thick coloured lines along the four parallelogram edges."""
        n  = BOARD_SIZE - 1
        lw = HEX_R // 2 + 4

        edges = {
            "top":    [(0,   c) for c in range(BOARD_SIZE)],
            "bottom": [(n,   c) for c in range(BOARD_SIZE)],
            "left":   [(r,   0) for r in range(BOARD_SIZE)],
            "right":  [(r,   n) for r in range(BOARD_SIZE)],
        }
        colors = {
            "top": RED_BORDER, "bottom": RED_BORDER,
            "left": BLUE_BORDER, "right": BLUE_BORDER,
        }

        for name, cells in edges.items():
            color = colors[name]
            pts   = [hex_center(r, c, self.x_off, self.y_off) for r, c in cells]
            for i in range(len(pts) - 1):
                x1, y1 = pts[i]
                x2, y2 = pts[i + 1]
                self.canvas.create_line(x1, y1, x2, y2,
                                        fill=color, width=lw,
                                        capstyle=ROUND, tags="border")

    def _draw_cells(self):
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                cx, cy = hex_center(row, col, self.x_off, self.y_off)
                pts = hex_poly(cx, cy)
                pid = self.canvas.create_polygon(
                    pts, fill=EMPTY_CLR, outline=OUTLINE_CLR, width=1,
                    tags=("cell", f"c{row}_{col}")
                )
                self._ids[(row, col)] = pid
                if self.click_cb:
                    self.canvas.tag_bind(pid, "<Button-1>",
                                         self._make_handler(row, col))

    def _draw_labels(self):
        for col in range(BOARD_SIZE):
            cx, cy = hex_center(0, col, self.x_off, self.y_off)
            self.canvas.create_text(cx, cy - HEX_R - 14,
                                    text=LETTERS[col],
                                    fill=LABEL_CLR,
                                    font=("Helvetica", 11, "bold"),
                                    tags="label")
        for row in range(BOARD_SIZE):
            cx, cy = hex_center(row, 0, self.x_off, self.y_off)
            self.canvas.create_text(cx - HEX_R - 18, cy,
                                    text=str(row),
                                    fill=LABEL_CLR,
                                    font=("Helvetica", 11, "bold"),
                                    tags="label")

    def _make_handler(self, row, col):
        def handler(_event):
            if self.click_cb:
                self.click_cb(row, col)
        return handler

    # ── Public ────────────────────────────────────────────────────────────
    def update(self, winning_group=None):
        """Repaint all hex cells from the current board state."""
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                v   = self.board[row][col]
                pid = self._ids[(row, col)]
                if winning_group and (row, col) in winning_group:
                    clr = WIN_CLR
                elif v == 1:
                    clr = BLUE_CLR
                elif v == -1:
                    clr = RED_CLR
                else:
                    clr = EMPTY_CLR
                self.canvas.itemconfig(pid, fill=clr)


# ── HexGameApp ────────────────────────────────────────────────────────────────
class HexGameApp:
    """
    Top-level application controller.
    Flow: start screen → game screen → (restart / back to start).
    """

    def __init__(self):
        self.window = Tk()
        self.window.title("Hex")
        self.window.configure(bg=BG)
        self.window.resizable(False, False)

        # Game state
        self.board      = None
        self.players    = None
        self.board_canvas: HexBoardCanvas = None
        self.mode       = None          # "hvh" | "hvai"
        self.ai_difficulty = "Hard"     # Easy | Medium | Hard
        self.difficulty_var = None

        # UI refs
        self.status_var = None
        self._loop_id   = None

        # AI threading
        self._ai_thinking = False

        # Win tracking
        self._game_over       = False
        self._win_sound_played = False

        self._init_sounds()
        self._show_start_screen()

    # ═════════════════════════════════════════════════════════════════════
    # Sounds
    # ═════════════════════════════════════════════════════════════════════
    def _init_sounds(self):
        """Load move/win sounds and print the reason if loading fails."""
        self.sounds_enabled = False
        self.sounds = {}
        self.sound_error = None

        if pygame is None:
            self.sound_error = "pygame is not installed. Run: pip install pygame"
            print(f"[sound] OFF - {self.sound_error}")
            return

        try:
            base = os.path.dirname(os.path.abspath(__file__))
            sound_dirs = [
                os.path.join(base, "sounds"),
                base,
                os.getcwd(),
            ]
            filenames = {
                "human": "human_move.ogg",
                "ai": "AI_move.ogg",
                "win": "win_sound.ogg",
            }
            resolved = {}
            for key, filename in filenames.items():
                for folder in sound_dirs:
                    candidate = os.path.join(folder, filename)
                    if os.path.exists(candidate):
                        resolved[key] = candidate
                        break
                if key not in resolved:
                    raise FileNotFoundError(f"Missing sound file: {filename}")

            pygame.mixer.pre_init(44100, -16, 2, 512)
            pygame.mixer.init()
            self.sounds["human"] = pygame.mixer.Sound(resolved["human"])
            self.sounds["ai"]    = pygame.mixer.Sound(resolved["ai"])
            self.sounds["win"]   = pygame.mixer.Sound(resolved["win"])

            # Keep sounds gentle across platforms. Some Linux mixers play short
            # OGG effects surprisingly hot, so we cap the playback volume here.
            self.sounds["human"].set_volume(0.28)
            self.sounds["ai"].set_volume(0.24)
            self.sounds["win"].set_volume(0.30)

            self.sounds_enabled  = True
            print(f"[sound] ON - loaded sounds from {os.path.dirname(resolved['human'])}")
        except Exception as exc:
            self.sound_error = str(exc)
            print(f"[sound] OFF - {self.sound_error}")

    def _play(self, key):
        if self.sounds_enabled and key in self.sounds:
            try:
                self.sounds[key].play()
                return
            except Exception as exc:
                self.sound_error = str(exc)
                print(f"[sound] play failed - {self.sound_error}")

        try:
            self.window.bell()
        except Exception:
            pass

    # Window management
    # ═════════════════════════════════════════════════════════════════════
    def _clear(self):
        if self._loop_id:
            self.window.after_cancel(self._loop_id)
            self._loop_id = None
        for w in self.window.winfo_children():
            w.destroy()
        self.board_canvas = None
        self.status_var   = None

    # ═════════════════════════════════════════════════════════════════════
    # Start screen
    # ═════════════════════════════════════════════════════════════════════
    def _show_start_screen(self):
        self._clear()
        self.board   = None
        self.players = None

        outer = Frame(self.window, bg=BG)
        outer.pack(expand=True, fill=BOTH)

        frame = Frame(outer, bg=BG, padx=70, pady=60)
        frame.place(relx=0.5, rely=0.5, anchor=CENTER)

        Label(frame, text="HEX",
              font=("Helvetica", 52, "bold"), fg="white", bg=BG
              ).pack(pady=(0, 4))
        Label(frame, text="11 × 11 Strategy Board Game",
              font=("Helvetica", 13), fg="#999999", bg=BG
              ).pack(pady=(0, 24))

        Label(frame, text="AI Difficulty",
              font=("Helvetica", 11, "bold"), fg="#dddddd", bg=BG
              ).pack(pady=(0, 6))

        self.difficulty_var = StringVar(value=self.ai_difficulty)
        difficulty_menu = OptionMenu(frame, self.difficulty_var, *AI_DIFFICULTIES.keys())
        difficulty_menu.config(
            font=("Helvetica", 12, "bold"),
            bg=BTN_BG, fg=BTN_FG,
            activebackground=BTN_ABG, activeforeground=BTN_FG,
            relief=FLAT, cursor="hand2",
            highlightthickness=0, width=16
        )
        difficulty_menu["menu"].config(
            bg=BTN_BG, fg=BTN_FG,
            activebackground=BTN_ABG, activeforeground=BTN_FG
        )
        difficulty_menu.pack(fill=X, pady=(0, 14))

        difficulty_hint = StringVar(value=AI_DIFFICULTIES[self.ai_difficulty]["description"])
        Label(frame, textvariable=difficulty_hint,
              font=("Helvetica", 10), fg="#aaaaaa", bg=BG
              ).pack(pady=(0, 16))

        def update_difficulty_hint(*_args):
            selected = self.difficulty_var.get()
            difficulty_hint.set(AI_DIFFICULTIES[selected]["description"])

        self.difficulty_var.trace_add("write", update_difficulty_hint)

        def btn(text, cmd, bg=BTN_BG, abg=BTN_ABG):
            b = Button(frame, text=text, command=cmd,
                       font=("Helvetica", 15, "bold"),
                       bg=bg, fg=BTN_FG,
                       activebackground=abg, activeforeground=BTN_FG,
                       relief=FLAT, cursor="hand2", pady=12)
            b.pack(fill=X, pady=5)

        btn("Human vs Human", lambda: self._start_game("hvh"))
        btn("Human vs AI",    lambda: self._start_game("hvai", self.difficulty_var.get()))
        btn("Test Sound",     lambda: self._play("human"))
        btn("Exit", self._exit_app, bg=EXIT_BG, abg=EXIT_ABG)

        # Size the window to the start screen
        self.window.update_idletasks()
        self.window.geometry("460x460")

    # ═════════════════════════════════════════════════════════════════════
    # Game startup
    # ═════════════════════════════════════════════════════════════════════
    def _start_game(self, mode, difficulty=None):
        self._clear()
        self.mode             = mode
        if difficulty in AI_DIFFICULTIES:
            self.ai_difficulty = difficulty
        self._game_over       = False
        self._win_sound_played = False
        self._ai_thinking     = False

        self.board   = HexBoard(BOARD_SIZE, swap_rule=False)
        self.players = [None, None, None]          # indices 1 and -1 (== 2)
        self.players[1] = GuiPlayer(1)             # human always player 1

        if mode == "hvh":
            self.players[2] = GuiPlayer(-1)
        else:
            settings = AI_DIFFICULTIES[self.ai_difficulty]
            self.players[2] = AlphaBetaPlayer(
                -1,
                TwoDistanceHeuristic(),
                search_depth=settings["search_depth"],
                max_time=settings["max_time"],
                sorter=ChargeHeuristic(BOARD_SIZE),
            )

        self._build_game_ui()

    # ─────────────────────────────────────────────────────────────────────
    def _build_game_ui(self):
        """Build the Canvas + labels + buttons for the active game."""
        # Calculate canvas size from hex geometry
        x_off = 110
        y_off = 70

        total_width  = (BOARD_SIZE - 1) * _col_step() + (BOARD_SIZE - 1) * _row_xstep()
        total_height = (BOARD_SIZE - 1) * _row_ystep()

        canvas_w = int(x_off + total_width  + HEX_R + 70)
        canvas_h = int(y_off + total_height + HEX_R + 20)

        # Main canvas
        canvas = Canvas(self.window, width=canvas_w, height=canvas_h,
                        bg=BG, highlightthickness=0)
        canvas.pack(side=TOP)

        self.board_canvas = HexBoardCanvas(
            canvas, self.board, x_off, y_off,
            click_cb=self._on_hex_click
        )

        # Status label
        if self.mode == "hvai":
            Label(self.window,
                  text=f"Difficulty: {self.ai_difficulty}",
                  font=("Helvetica", 10, "bold"),
                  fg="#aaaaaa", bg=BG
                  ).pack(pady=(8, 0))

        self.status_var = StringVar(value="")
        Label(self.window, textvariable=self.status_var,
              font=("Helvetica", 14, "bold"),
              fg="white", bg=BG
              ).pack(pady=(4 if self.mode == "hvai" else 8, 0))

        # Control buttons
        btn_frame = Frame(self.window, bg=BG)
        btn_frame.pack(pady=10)

        controls = [
            ("Restart",   self._restart,    BTN_BG,  BTN_ABG),
            ("Undo",      self._undo,       BTN_BG,  BTN_ABG),
            ("Menu",      self._show_start_screen, BTN_BG, BTN_ABG),
            ("Exit Game", self._exit_app,   EXIT_BG, EXIT_ABG),
        ]
        for text, cmd, bg, abg in controls:
            Button(btn_frame, text=text, command=cmd,
                   font=("Helvetica", 11, "bold"),
                   bg=bg, fg=BTN_FG,
                   activebackground=abg, activeforeground=BTN_FG,
                   relief=FLAT, cursor="hand2",
                   padx=18, pady=6
                   ).pack(side=LEFT, padx=6)

        # Fit window to content
        win_h = canvas_h + (100 if self.mode == "hvai" else 80)
        self.window.geometry(f"{canvas_w}x{win_h}")

        # Kick off the game loop
        self._loop_id = self.window.after(120, self._game_loop)

    # ═════════════════════════════════════════════════════════════════════
    # Game loop (runs every 100 ms via window.after)
    # ═════════════════════════════════════════════════════════════════════
    def _game_loop(self):
        if self.board is None or self.board_canvas is None:
            return

        # ── Step 1: always render the current board state first ──────────
        # Do NOT check for winner yet — render first so the stone that was
        # just placed is visible on screen before any win announcement.
        self.board_canvas.update()

        # ── Step 2: flush canvas changes to the screen ───────────────────
        self.window.update_idletasks()

        # ── Step 3: check for a winner (after the board is visible) ──────
        if self._game_over:
            # Re-render with winning-path highlight
            self.board_canvas.update(winning_group=self.board.winning_group)
            self._refresh_status()
            self._loop_id = self.window.after(150, self._game_loop)
            return

        if self.board.winner != 0:
            self._game_over = True
            # Re-render immediately with winning-path highlight
            self.board_canvas.update(winning_group=self.board.winning_group)
            self.window.update_idletasks()
            if not self._win_sound_played:
                self._play("win")
                self._win_sound_played = True
            self._refresh_status()
            self._loop_id = self.window.after(150, self._game_loop)
            return

        # ── Step 4: update status label ───────────────────────────────────
        self._refresh_status()

        # ── Step 5: trigger AI move in background thread ─────────────────
        current = self.players[self.board.turn]
        if not isinstance(current, GuiPlayer) and not self._ai_thinking:
            self._ai_thinking = True
            threading.Thread(target=self._run_ai, daemon=True).start()

        self._loop_id = self.window.after(100, self._game_loop)

    # ─────────────────────────────────────────────────────────────────────
    def _run_ai(self):
        """
        Runs the AI search in a background thread.

        Key design: the search runs entirely on a *deep copy* of the board.
        This means the real (displayed) board is never touched during search,
        so there is no blinking or flickering of cells while the AI thinks.
        Only the single winning move is applied to the real board at the end.
        """
        from copy import deepcopy
        try:
            turn = self.board.turn           # capture before search starts
            board_copy = deepcopy(self.board) # isolated scratch board

            moves_before = len(board_copy.move_list)
            # Run the selected AI difficulty search on the copy
            self.players[turn].move(board_copy)

            # — Apply result to the real board —
            if board_copy._winner not in (None, 0) and len(board_copy.move_list) == moves_before:
                # AI decided to resign (extremely rare)
                self.board.resign()
            elif len(board_copy.move_list) > moves_before:
                final_move = board_copy.move_list[-1]
                self.board.play(*final_move)
                self._play("ai")
        finally:
            self._ai_thinking = False

    # ═════════════════════════════════════════════════════════════════════
    # Click handling (human moves)
    # ═════════════════════════════════════════════════════════════════════
    def _on_hex_click(self, row, col):
        """Direct click → play move if it's a human's turn."""
        if self._game_over or self._ai_thinking:
            return
        if not isinstance(self.players[self.board.turn], GuiPlayer):
            return
        before = len(self.board.move_list)
        self.board.play(row, col)
        if len(self.board.move_list) > before:
            self._play("human")

    # ═════════════════════════════════════════════════════════════════════
    # Controls
    # ═════════════════════════════════════════════════════════════════════
    def _restart(self):
        self._start_game(self.mode)

    def _undo(self):
        if self.board is None or not self.board.move_list or self._ai_thinking:
            return
        if self._game_over:
            self._game_over = False
        if self.mode == "hvh":
            self.board.undo()
        else:
            # Undo until it is the human's turn (player 1)
            self.board.undo()
            while self.board.move_list and self.board.turn != 1:
                self.board.undo()
        if self.board_canvas:
            self.board_canvas.update()
        self._refresh_status()

    def _exit_app(self):
        self.window.destroy()

    # ═════════════════════════════════════════════════════════════════════
    # Status label
    # ═════════════════════════════════════════════════════════════════════
    def _refresh_status(self):
        if self.status_var is None or self.board is None:
            return
        b = self.board
        if b.winner != 0:
            if self.mode == "hvai":
                text = "You Win!" if b.winner == 1 else "AI Wins!"
            else:
                text = ("Blue Player Wins!" if b.winner == 1
                        else "Red Player Wins!")
        elif self._ai_thinking:
            text = f"AI is thinking... ({self.ai_difficulty})" if self.mode == "hvai" else "AI is thinking..."
        elif self.mode == "hvai":
            text = "Your Turn (Blue)" if b.turn == 1 else "AI Turn (Red)"
        else:
            text = ("Blue Player's Turn" if b.turn == 1
                    else "Red Player's Turn")
        self.status_var.set(text)

# ── Entry point ───────────────────────────────────────────────────────────────
def start_application():
    """Called by main.py.  Always starts the GUI directly."""
    app = HexGameApp()
    app.window.mainloop()
