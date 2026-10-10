import heapq, itertools, random, sys, os, tempfile
import game_core as gc
from controller import Game

class Handle:
    def __init__(self): self.cancelled = False
    def cancel(self): self.cancelled = True

class FakeUI:
    def __init__(self):
        self.now = 0.0; self.q = []; self.seq = itertools.count()
        self.status = ""; self.taunt = ""; self.sounds = []; self.shakes = 0
        self.buzzes = 0; self.goodbye = False; self.redraws = 0; self.animated = []
    def schedule(self, secs, fn):
        h = Handle(); heapq.heappush(self.q, (self.now + secs, next(self.seq), fn, h)); return h
    def cancel(self, h): h.cancel()
    def advance(self, secs):
        end = self.now + secs
        while self.q and self.q[0][0] <= end:
            t, _, fn, h = heapq.heappop(self.q); self.now = t
            if not h.cancelled: fn()
        self.now = end
    def play(self, n): self.sounds.append(n)
    def vibrate(self, ms): self.buzzes += 1
    def set_status(self, t): self.status = t
    def show_taunt(self, t, gold): self.taunt = t
    def refresh_scores(self): pass
    def refresh_grudge(self): pass
    def animate_mark(self, i): self.animated.append(i)
    def redraw(self, snap=False): self.redraws += 1
    def shake(self): self.shakes += 1
    def show_goodbye(self): self.goodbye = True

def make(level="Sneaky", diff="Hard", play_as="X"):
    st = gc.Stats(os.path.join(tempfile.mkdtemp(), "s.json"))
    st.data["settings"].update(cheat_level=level, difficulty=diff, play_as=play_as)
    ui = FakeUI(); g = Game(ui, st); g.start(); return g, ui

# 1. random full games, all levels, both sides
random.seed(1)
stuck = 0
for level in gc.CHEAT_LEVELS:
    for play_as in ("X", "O"):
        for diff in ("Easy", "Hard"):
            g, ui = make(level, diff, play_as)
            for n in range(40):
                for _ in range(80):
                    ui.advance(1.0)
                    if g.game_over and not g.finale_running: break
                    if g.player == gc.HUMAN and not g.game_over:
                        empty = [i for i in range(9) if not g.board[i]]
                        if empty:
                            if random.random() < 0.12:
                                g.click(random.randrange(9), secret=True)   # random long press
                            else:
                                g.click(random.choice(empty))
                ui.advance(10)
                if not g.game_over: stuck += 1
                assert g.board.count("X") + g.board.count("O") >= 0
                g.new_game()
            d = g.stats.data
            assert d["games"] == d["wins"] + d["losses"] + d["draws"], (level, d)
            print(f"{level:9} as {play_as} {diff:4}: games={d['games']:3} W{d['wins']:2} L{d['losses']:2} D{d['draws']:2} outside={d['outside_losses']} flips={d['flips']} fakes={d['fake_wins']} erases={d['erases']} cheats={d['cheats_used']}")
print("stuck games:", stuck)

# 2. Honest never cheats
g, ui = make("Honest", "Hard", "X")
for _ in range(30):
    while not g.game_over:
        g.click(random.choice([i for i in range(9) if not g.board[i]])); ui.advance(1)
    g.new_game()
assert g.stats.data["flips"] == g.stats.data["fake_wins"] == g.stats.data["erases"] == g.stats.data["outside_losses"] == 0
print("honest: no cheats ok")

# 3. outside win geometry (force it)
g, ui = make("Shameless", "Hard", "X")
g.board = ["O","O","","X","X","","","",""]; g.player = gc.CPU; g.human_moves=[3,4]
random.seed(5)
ch = g.pick_outside_win(); assert ch, "should have outside option"
g.outside_win(ch); ui.advance(2)
assert g.outside_mark and "win" in g.lines and g.game_over and g.stats.data["outside_losses"] == 1
print("outside:", g.outside_mark, g.lines["win"], "shakes", ui.shakes)

# 4. long press: steal and bonus
g, ui = make("Honest", "Hard", "X")
g.click(4); ui.advance(3)
assert g.board[4] == "X"
cpu_sq = [i for i in range(9) if g.board[i] == "O"][0]
assert g.click(cpu_sq, secret=True) and g.board[cpu_sq] == "X"
print("steal ok; cheats_used", g.stats.data["cheats_used"], "grudge", g.grudge)

# 5. snooze + hold/release (dialog / background pause)
g, ui = make("Shameless", "Hard", "X")
secs = g.idle_seconds(); print("shameless snooze secs:", secs)
g.hold(); ui.advance(secs + 5); assert g.stats.data["snoozes"] == 0 and g.player == gc.HUMAN
g.release(); ui.advance(secs + 1); assert g.stats.data["snoozes"] == 1
print("snooze/hold ok")

# 6. poke finale
g, ui = make("Sneaky", "Hard", "X")
for _ in range(gc.POKE_TARGET): g.poke()
ui.advance(5); assert ui.goodbye and "poked" in g.stats.data["achievements"]
g.new_game(); assert g.finale_running and g.game_over
print("poke finale ok")

# 7. play as O: computer opens, shapes localized
g, ui = make("Honest", "Hard", "O"); ui.advance(2)
assert g.board.count("O") == 1 and g.human_shape == "O" and g.cpu_shape == "X"
print("play-as-O ok:", g.board)

# 8. switching play_as mid-game, stale cpu job cancelled
g, ui = make("Honest", "Hard", "O"); g.set_option("play_as", "X"); ui.advance(3)
assert g.board.count("O") == 0 and g.player == gc.HUMAN
g.set_option("play_as", "O"); g.set_option("play_as", "X"); g.set_option("play_as", "O"); ui.advance(3)
assert sum(1 for c in g.board if c) == 1, g.board
print("option switching ok")
# 9. Hard Mode Hero only for a clean win; cheated wins still count as wins
for cheated in (True, False):
    g, ui = make("Honest", "Hard", "X")
    g.cheated_this_game = cheated
    g.record_result("win")
    got = "hard_win" in g.stats.data["achievements"]
    assert got == (not cheated), (cheated, got)
    assert "win_cheating" in g.stats.data["achievements"] if cheated else "honest_win" in g.stats.data["achievements"]
    assert g.stats.data["wins"] == 1
print("hard_win: cheated -> locked, clean -> unlocked")
print("ALL PASSED")
