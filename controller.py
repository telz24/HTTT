"""The game itself: turns, cheats, achievements, snooze timer.

This is the TicTacToe class from the desktop version with every tkinter call
taken out. It talks to the screen only through a small `ui` object (see
GameScreen in main.py), so it can be tested without Kivy.

Board geometry is in "cell units": the visible 3x3 board has its top-left corner
at (0, 0) and each square is 1x1. The centre of (row, col) is (col + .5, row + .5).
Row/col -1 and 3 are the invisible squares just outside the board.
"""
import random
import re
import time

from game_core import (
    ACH_INFO, CAUGHT_YOU, CHEAT_LEVELS, CHEAT_TAUNTS, CPU, DRAW_TAUNTS,
    ERASE_TAUNTS, FAKE_REVEAL_TAUNTS, FAKE_WIN_TAUNTS, FLIP_TAUNTS, GOLD,
    GRUDGE_MAX, GRUDGE_STEP, HUMAN, INSULTS, ODD_MARK_CHANCE,
    OUTSIDE_WIN_TAUNTS, PLAY_CHOICES, POKE_FINAL, POKE_LINES, POKE_REPEAT,
    POKE_TARGET, Q_QUIPS, SNOOZE_TAUNTS, SORE_LOSER, T_QUIPS, WIN_LINES,
    ACHIEVEMENTS, best_move, find_winner, minimax, outside_wins,
)


def center(row, col):
    return (col + 0.5, row + 0.5)


class Game:
    def __init__(self, ui, stats):
        self.ui = ui
        self.stats = stats
        s = stats.data["settings"]
        if s["difficulty"] not in ("Easy", "Hard"):
            s["difficulty"] = "Hard"
        if s["cheat_level"] not in CHEAT_LEVELS:
            s["cheat_level"] = "Sneaky"
        if s["play_as"] not in PLAY_CHOICES:
            s["play_as"] = "X"
        self.difficulty = s["difficulty"]
        self.cheat_level = s["cheat_level"]
        self.play_as = s["play_as"]

        self.board = [""] * 9
        self.odd = [False] * 9          # squares where the computer's mark glitched into a Q / T
        self.quip = None
        self.human_moves = []           # your marks, oldest first
        self.lines = {}                 # tag -> ((u1, v1), (u2, v2)) strike lines to draw
        self.outside_mark = None        # (row, col, shape) of the O placed outside the box
        self.game_over = False
        self.round = 0                  # bumps every new game (cancels stale delayed events)
        self.grudge = 0
        self.cheated_this_game = False
        self.idle_job = None
        self.cpu_job = None
        self.holds = 0                  # >0 while a dialog is open or the app is in the background
        self.toast_queue = []
        self.toast_busy = False
        self.toast_showing = False
        self.pokes = 0
        self.finale_running = False
        self.status = ""
        # X always goes first, so if you play O the computer opens the game
        self.starter = HUMAN if self.play_as != "O" else CPU
        self.player = self.starter

    # ===== startup =====
    def start(self):
        self.update_labels()
        self.ui.refresh_grudge()
        self.ui.redraw(snap=True)
        self.start_idle_timer()
        if self.player == CPU:
            self.schedule_cpu(0.7)

    # ===== which shape is whose =====
    @property
    def human_shape(self):
        return "O" if self.play_as == "O" else "X"

    @property
    def cpu_shape(self):
        return "X" if self.play_as == "O" else "O"

    @property
    def odd_shape(self):
        return "T" if self.cpu_shape == "X" else "Q"

    def shape_of(self, who, i=None):
        if who == HUMAN:
            return self.human_shape
        return self.odd_shape if (i is not None and self.odd[i]) else self.cpu_shape

    def odd_quips(self):
        return Q_QUIPS if self.odd_shape == "Q" else T_QUIPS

    def flush_quip(self):
        if self.quip:
            self.say(self.quip, raw=True)
            self.quip = None

    # ===== settings, sound, timers =====
    @property
    def sound_on(self):
        return self.stats.data["settings"]["sound"]

    def toggle_sound(self):
        s = self.stats.data["settings"]
        s["sound"] = not s["sound"]
        self.stats.save()
        self.play("bubble")

    def chance(self, key):
        base = CHEAT_LEVELS[self.cheat_level][key]
        if base <= 0:
            return 0.0
        return min(0.95, base + GRUDGE_STEP * self.grudge)

    def play(self, name):
        if self.sound_on:
            self.ui.play(name)

    def buzz(self, ms):
        if self.sound_on:
            self.ui.vibrate(ms)

    def schedule(self, secs, fn):
        return self.ui.schedule(secs, fn)

    def schedule_cpu(self, secs):
        """Queue the computer's turn (never two at once)."""
        if self.cpu_job is not None:
            self.ui.cancel(self.cpu_job)
        self.cpu_job = self.schedule(secs, self._cpu_due)

    def _cpu_due(self):
        self.cpu_job = None
        self.computer_move()

    def hold(self):
        """A dialog opened or the app went to the background: stop the snooze clock."""
        self.holds += 1
        self.cancel_idle_timer()

    def release(self):
        self.holds = max(0, self.holds - 1)
        if (self.holds == 0 and not self.game_over and self.player == HUMAN
                and not self.finale_running):
            self.start_idle_timer()

    # ===== what the computer says =====
    def localize(self, text):
        """Lines are written as if you're X and the computer is O; use the real shapes."""
        mapping = {"X": self.human_shape, "O": self.cpu_shape}
        return re.sub(r"\b([XO])\b", lambda m: mapping[m.group(1)], text)

    def say(self, text, color=None, raw=False):
        """Chat line under the status. color given = a gold achievement toast."""
        if color is not None:
            self.ui.show_taunt(text, True)
            return
        if not text and self.toast_showing:
            return                                  # don't wipe an achievement early
        self.ui.show_taunt(text if raw else self.localize(text), False)

    # ===== the board =====
    def mark(self, i, who):
        self.board[i] = who
        if i in self.human_moves:
            self.human_moves.remove(i)
        if who == HUMAN:
            self.human_moves.append(i)
        self.odd[i] = who == CPU and random.random() < ODD_MARK_CHANCE
        if self.odd[i]:
            self.quip = random.choice(self.odd_quips())
        self.play("x" if who == HUMAN else "o")
        self.ui.animate_mark(i)

    def clear(self, i):
        self.board[i] = ""
        self.odd[i] = False
        if i in self.human_moves:
            self.human_moves.remove(i)
        self.ui.redraw()

    def refresh_board(self):
        self.human_moves = [i for i, c in enumerate(self.board) if c == HUMAN]
        self.ui.redraw(snap=True)

    def show_win_line(self, rid, start, end, extend=True, tag="win"):
        """Glowing line through the winning squares (start/end are cell-unit points)."""
        if rid != self.round:
            return
        (x1, y1), (x2, y2) = start, end
        if extend:
            dx, dy = x2 - x1, y2 - y1
            length = max((dx * dx + dy * dy) ** 0.5, 1e-9)
            ex, ey = dx / length * 0.3, dy / length * 0.3
            x1, y1, x2, y2 = x1 - ex, y1 - ey, x2 + ex, y2 + ey
        self.lines[tag] = ((x1, y1), (x2, y2))
        self.ui.redraw()

    # ===== grudge =====
    def add_grudge(self):
        self.grudge = min(GRUDGE_MAX, self.grudge + 1)
        self.ui.refresh_grudge()

    # ===== the dumbest achievement =====
    def poke(self):
        if self.finale_running:
            return
        self.pokes += 1
        if self.pokes < POKE_TARGET:
            self.say(POKE_LINES[min(self.pokes, len(POKE_LINES)) - 1], raw=True)
            self.play("bubble")
            return
        self.pokes = 0
        earned = self.stats.data["achievements"]
        if "poked" in earned:
            self.say(POKE_REPEAT, raw=True)
            return
        earned["poked"] = int(time.time())
        self.stats.save()
        self.start_finale()

    def start_finale(self):
        self.finale_running = True
        self.game_over = True           # lock the board
        self.cancel_idle_timer()
        self.status = "Achievement unlocked!"
        self.ui.set_status(self.status)
        self.say(random.choice(POKE_FINAL), color=GOLD)
        self.play("achievement")
        self.schedule(3.2, self.ui.show_goodbye)

    # ===== options (Play as / Difficulty / Cheating) =====
    def set_option(self, key, name):
        current = getattr(self, key)
        if current == name:
            return
        setattr(self, key, name)
        self.stats.data["settings"][key] = name
        self.stats.save()
        if key == "cheat_level":
            self.ui.refresh_grudge()
            self.start_idle_timer()
        elif key == "play_as":
            self.starter = HUMAN if self.human_shape == "X" else CPU
            self.new_game(change_starter=False)

    def reset_stats(self):
        self.stats.reset()
        self.grudge = 0
        self.ui.refresh_grudge()
        self.update_labels()

    # ===== labels =====
    def update_labels(self):
        if not self.game_over:
            if self.player == HUMAN:
                self.status = f"Your turn ({self.human_shape})"
            else:
                self.status = "Computer is thinking..."
            self.ui.set_status(self.status)
        self.ui.refresh_scores()

    # ===== achievements =====
    def unlock(self, aid):
        earned = self.stats.data["achievements"]
        if aid in earned:
            return
        earned[aid] = int(time.time())
        self.stats.save()
        self.toast_queue.append(aid)
        if not self.toast_busy:
            self.toast_busy = True
            self.schedule(1.5, self.next_toast)

    def next_toast(self):
        if not self.toast_queue:
            self.toast_busy = False
            self.toast_showing = False
            self.ui.show_taunt("", False)
            return
        name = ACH_INFO[self.toast_queue.pop(0)][1]
        self.toast_showing = True
        self.say(f"Achievement unlocked: {name}", color=GOLD)
        self.play("achievement")
        self.schedule(2.6, self.next_toast)

    def record_result(self, result, outside=False):
        d = self.stats.data
        d["games"] += 1
        if result == "win":
            d["wins"] += 1
            d["streak"] += 1
            d["best_streak"] = max(d["best_streak"], d["streak"])
            self.unlock("first_win")
            self.unlock("win_cheating" if self.cheated_this_game else "honest_win")
            if self.difficulty == "Hard" and not self.cheated_this_game:
                self.unlock("hard_win")
            if self.cheat_level == "Shameless" and not self.cheated_this_game:
                self.unlock("fair_fight")
            if d["streak"] >= 3:
                self.unlock("streak3")
            if d["streak"] >= 5:
                self.unlock("streak5")
        elif result == "loss":
            d["losses"] += 1
            d["streak"] = 0
            if outside:
                d["outside_losses"] += 1
                self.unlock("outside_loss")
        else:
            d["draws"] += 1
            d["streak"] = 0
            if d["draws"] >= 5:
                self.unlock("draw5")
        if d["games"] >= 10:
            self.unlock("survivor10")
        if d["games"] >= 50:
            self.unlock("veteran50")
        if not self.cheated_this_game:
            self.grudge = max(0, self.grudge - 1)
            self.ui.refresh_grudge()
        self.stats.save()
        self.play({"win": "win", "loss": "lose", "draw": "draw"}[result])
        self.buzz({"win": 60, "loss": 250, "draw": 90}[result])
        self.update_labels()

    # ===== player input =====
    def click(self, i, secret=False):
        """You tapped square i (secret=True: a long press, the cheat).

        Returns True if something happened."""
        if i is None or self.game_over or self.player != HUMAN:
            return False
        if secret:
            if not self.player_cheat(i):
                return False
        else:
            if self.board[i]:
                return False
            self.cancel_idle_timer()
            self.say("")
            self.mark(i, HUMAN)
            self.end_check()

        if self.game_over:
            return True
        if self.player == CPU:
            self.schedule_cpu(0.6)
        else:
            self.start_idle_timer()   # a bonus mark leaves it your turn
        return True

    def register_cheat(self):
        self.cancel_idle_timer()
        self.cheated_this_game = True
        self.stats.data["cheats_used"] += 1
        self.add_grudge()
        self.play("caught")
        self.unlock("caught")
        self.stats.save()

    def player_cheat(self, i):
        """Long press. Returns True if it did something."""
        if self.board[i] == CPU:
            self.register_cheat()                       # steal the computer's square
            self.mark(i, HUMAN)
            self.say(random.choice(CAUGHT_YOU["steal"]))
            self.end_check()
            return True
        if self.board[i] == "":
            self.register_cheat()                       # bonus mark: keep your turn
            self.mark(i, HUMAN)
            if find_winner(self.board) or all(self.board):
                self.end_check()
            else:
                self.say(random.choice(CAUGHT_YOU["double"]))
            return True
        return False

    # ===== "snooze you lose" =====
    def idle_seconds(self):
        base = CHEAT_LEVELS[self.cheat_level]["snooze"]
        if base is None:
            return None
        return max(6, base - self.grudge)

    def start_idle_timer(self):
        self.cancel_idle_timer()
        secs = self.idle_seconds()
        if (secs is None or self.game_over or self.player != HUMAN
                or self.holds > 0 or self.finale_running):
            return
        self.idle_job = self.schedule(secs, self.snooze_fire)

    def cancel_idle_timer(self):
        if self.idle_job is not None:
            self.ui.cancel(self.idle_job)
            self.idle_job = None

    def snooze_fire(self):
        self.idle_job = None
        if self.game_over or self.player != HUMAN or self.holds > 0:
            return
        d = self.stats.data
        d["snoozes"] += 1
        self.unlock("snoozed")
        self.mark(self.normal_choice(), CPU)
        self.say(random.choice(SNOOZE_TAUNTS))
        self.play("snooze")
        if find_winner(self.board) or all(self.board):
            self.end_check()
        else:
            self.update_labels()
            self.start_idle_timer()
        self.flush_quip()

    # ===== the computer's "outside the box" cheat =====
    def pick_outside_win(self):
        """Choose an invisible square that gives the computer three in a row.

        On a phone the margin around the board is always on screen, so every
        outside square is a valid choice."""
        options = [(cells, rc) for cells, rc in outside_wins(self.board)]
        return random.choice(options) if options else None

    def outside_win(self, choice):
        cells, outside = choice
        rid = self.round
        self.game_over = True           # lock the board while the cheat plays out
        self.cancel_idle_timer()
        self.say("")
        shape = self.cpu_shape
        if random.random() < ODD_MARK_CHANCE:
            shape = self.odd_shape
            self.quip = random.choice(self.odd_quips())
        self.outside_mark = (outside[0], outside[1], shape)
        self.ui.redraw()
        self.play("outside")
        self.buzz(400)
        self.ui.shake()
        self.schedule(0.7, lambda: self.finish_outside_win(rid, cells, outside))

    def finish_outside_win(self, rid, cells, outside):
        if rid != self.round:
            return                      # a new game started in the meantime
        ox, oy = center(*outside)
        pts = [center(i // 3, i % 3) for i in cells]
        sx, sy = max(pts, key=lambda p: (p[0] - ox) ** 2 + (p[1] - oy) ** 2)
        length = max(((ox - sx) ** 2 + (oy - sy) ** 2) ** 0.5, 1e-9)
        ux, uy = (ox - sx) / length, (oy - sy) / length
        ext = 0.3
        p1 = (sx - ux * ext, sy - uy * ext)
        p2 = (ox + ux * ext, oy + uy * ext)
        self.show_win_line(rid, p1, p2, extend=False)
        self.status = "Computer wins!"
        self.ui.set_status(self.status)
        if self.quip:
            self.say(self.quip, raw=True)
            self.quip = None
        else:
            self.say(random.choice(OUTSIDE_WIN_TAUNTS))
        self.record_result("loss", outside=True)

    # ===== the computer's other cheats =====
    def flip_helps(self):
        if not any(self.board):
            return False
        swap = {HUMAN: CPU, CPU: HUMAN, "": ""}
        flipped = [swap[c] for c in self.board]
        return minimax(flipped, HUMAN) > minimax(list(self.board), CPU)

    def cpu_flip(self):
        swap = {HUMAN: CPU, CPU: HUMAN, "": ""}
        self.board = [swap[c] for c in self.board]
        self.odd = [False] * 9
        self.refresh_board()
        self.stats.data["flips"] += 1
        self.unlock("flipped")
        self.stats.save()
        self.say(random.choice(FLIP_TAUNTS))
        self.play("flip")
        self.buzz(120)
        self.end_check()

    def fake_pair(self):
        pairs = []
        for line in WIN_LINES:
            cells = [self.board[i] for i in line]
            if cells.count(CPU) == 2:
                pairs.append(tuple(i for i in line if self.board[i] == CPU))
        return random.choice(pairs) if pairs else None

    def fake_win(self, pair):
        rid = self.round
        self.game_over = True           # lock the board for the big announcement
        self.cancel_idle_timer()
        a = center(pair[0] // 3, pair[0] % 3)
        b = center(pair[1] // 3, pair[1] % 3)
        self.show_win_line(rid, a, b, tag="fake")
        self.status = "Computer wins!"
        self.ui.set_status(self.status)
        self.say(random.choice(FAKE_WIN_TAUNTS))
        self.play("fanfare")
        self.schedule(2.3, lambda: self.reveal_fake(rid))

    def reveal_fake(self, rid):
        if rid != self.round:
            return
        self.lines.pop("fake", None)
        self.ui.redraw()
        self.game_over = False
        self.stats.data["fake_wins"] += 1
        self.unlock("fooled")
        self.stats.save()
        self.say(random.choice(FAKE_REVEAL_TAUNTS))
        self.play("boing")
        self.update_labels()
        self.start_idle_timer()

    # ===== computer moves =====
    def normal_choice(self):
        empty = [i for i in range(9) if not self.board[i]]
        if self.difficulty == "Easy":
            return random.choice(empty)
        return best_move(self.board)

    def computer_move(self):
        if self.game_over or self.player != CPU:
            return
        self.cancel_idle_timer()

        # 1. The big one: win by playing an invisible square outside the board
        if random.random() < self.chance("outside"):
            choice = self.pick_outside_win()
            if choice:
                self.outside_win(choice)
                return

        # 2. Board flip (only when it really helps the computer)
        if random.random() < self.chance("flip") and self.flip_helps():
            self.cpu_flip()
            return

        # 3. Double move, square steal, or erasing your last mark
        human_squares = [i for i in range(9) if self.board[i] == HUMAN]
        c = self.chance("cheat")
        table = [("double", c / 2)]
        if human_squares:
            table.append(("steal", c / 2))
        if self.human_moves:
            table.append(("erase", self.chance("erase")))
        roll, acc, cheat = random.random(), 0.0, None
        for name, p in table:
            acc += p
            if roll < acc:
                cheat = name
                break

        if cheat == "steal":
            victim = random.choice(human_squares)
            self.mark(victim, CPU)
            self.say(random.choice(CHEAT_TAUNTS["steal"]))
            self.play("cheat")
            self.buzz(80)
            self.end_check()
            self.flush_quip()
            return

        if cheat == "erase":
            self.clear(self.human_moves[-1])
            self.stats.data["erases"] += 1
            self.unlock("whatx")
            self.stats.save()
            self.say(random.choice(ERASE_TAUNTS))
            self.play("erase")

        first = self.normal_choice()
        self.mark(first, CPU)

        if cheat == "double" and not find_winner(self.board) and not all(self.board):
            self.say(random.choice(CHEAT_TAUNTS["double"]))
            self.play("cheat")
            self.buzz(80)
            self.mark(self.normal_choice(), CPU)

        self.end_check()
        self.flush_quip()

        # 4. Fake win: announce victory with only two in a row
        if not self.game_over and random.random() < self.chance("fake"):
            pair = self.fake_pair()
            if pair:
                self.fake_win(pair)

    # ===== game flow =====
    def end_check(self):
        line = find_winner(self.board)
        if line:
            self.game_over = True
            self.cancel_idle_timer()
            rid = self.round
            a = center(line[0] // 3, line[0] % 3)
            b = center(line[2] // 3, line[2] % 3)
            self.schedule(0.28, lambda: self.show_win_line(rid, a, b))
            if self.board[line[0]] == HUMAN:
                self.status = "You win!"
                self.ui.set_status(self.status)
                self.say(random.choice(SORE_LOSER))
                self.record_result("win")
            else:
                self.status = "Computer wins!"
                self.ui.set_status(self.status)
                self.say(random.choice(INSULTS))
                self.record_result("loss")
        elif all(self.board):
            self.game_over = True
            self.cancel_idle_timer()
            self.status = "It's a draw!"
            self.ui.set_status(self.status)
            self.say(random.choice(DRAW_TAUNTS))
            self.record_result("draw")
        else:
            self.player = CPU if self.player == HUMAN else HUMAN
            self.update_labels()
            if self.player == HUMAN:
                self.start_idle_timer()

    def new_game(self, change_starter=True):
        if self.finale_running:
            return
        self.round += 1
        self.cancel_idle_timer()
        if self.cpu_job is not None:
            self.ui.cancel(self.cpu_job)
            self.cpu_job = None
        self.board = [""] * 9
        self.human_moves = []
        self.odd = [False] * 9
        self.quip = None
        self.lines = {}
        self.outside_mark = None
        self.game_over = False
        self.cheated_this_game = False
        if change_starter:
            self.starter = CPU if self.starter == HUMAN else HUMAN
        self.player = self.starter
        self.say("")
        self.update_labels()
        self.ui.redraw(snap=True)
        if self.player == CPU:
            self.schedule_cpu(0.6)
        else:
            self.start_idle_timer()
