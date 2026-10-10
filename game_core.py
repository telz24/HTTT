"""Core of "Tic Tac Toe vs a Cheating Phone": game rules, cheats, stats and sounds.

Everything here is plain Python (no Kivy, no tkinter), taken from the desktop
version so both versions play exactly the same.
"""
import copy
import io
import json
import math
import os
import random
import sys
import time
import wave
from array import array


TITLE = "Tic Tac Toe vs a Cheating Phone"
VERSION = "1.4.1"

WIN_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # columns
    (0, 4, 8), (2, 4, 6),             # diagonals
]

HUMAN = "X"
CPU = "O"

# ---------- cheat levels ----------
#   cheat   chance per turn of a double move or a square steal
#   outside chance of an "outside the box" win whenever one is available
#   erase   chance it erases your last X
#   flip    chance it flips the board (only when that actually helps it)
#   fake    chance it announces a fake win after a move
#   snooze  seconds you can sit idle before it takes another turn (None = never)
# "Sneaky" is the original setting: 0.30 double/steal and 0.55 outside win.
CHEAT_LEVELS = {
    "Honest":    {"cheat": 0.00, "outside": 0.00, "erase": 0.00,
                  "flip": 0.00, "fake": 0.00, "snooze": None},
    "Sneaky":    {"cheat": 0.30, "outside": 0.55, "erase": 0.08,
                  "flip": 0.35, "fake": 0.06, "snooze": 20},
    "Shameless": {"cheat": 0.45, "outside": 0.85, "erase": 0.18,
                  "flip": 0.70, "fake": 0.12, "snooze": 10},
}

# Grudge: every time YOU cheat, the computer's cheat chances go up a little and
# its patience (snooze timer) goes down. It cools off by one point for each game
# you finish without cheating.
GRUDGE_MAX = 10
GRUDGE_STEP = 0.04

OVERLAY_SECONDS = 60        # how long the O on the desktop stays visible

# ---------- look and feel ----------
BG = "#0a1216"            # window background
MENU_BG = "#0f1b21"
PANEL = "#0f1c22"         # board panel
PANEL_EDGE = "#1e3a43"
CYAN = "#46e6f2"          # grid, buttons, accents
TEXT = "#b9eef3"
TAUNT_COLOR = "#e0a8ff"
DARK_TEXT = "#06222a"
WIN_COLOR = "#7dffb2"

BOARD = 380               # board canvas is BOARD x BOARD pixels
GRID0 = 34                # where the # starts inside the board canvas
CELL = (BOARD - 2 * GRID0) / 3
FONT = "Segoe UI"

GOLD = "#ffd166"

# ---------- more computer lines ----------
ERASE_TAUNTS = [
    "What X?",
    "I don't see any X there.",
    "There was never an X. You're imagining things.",
    "Funny, that square looks empty to me.",
    "An X? Where? I only see a big empty square.",
]

FLIP_TAUNTS = [
    "Everything looks better flipped.",
    "Board flip! Your X's are mine now.",
    "Switcheroo! Sides have changed.",
    "Surprise! I took the liberty of swapping everything.",
    "Plot twist: I'm the X's now.",
]

SNOOZE_TAUNTS = [
    "Snooze you lose!",
    "Too slow. My turn. Again.",
    "Tick tock. I'll just go ahead.",
    "Waiting is for losers. I'll play for both of us. Mostly me.",
    "Did you fall asleep? I took your turn. Well, mine.",
]

FAKE_WIN_TAUNTS = [
    "THREE IN A ROW! I WIN!",
    "Victory! Flawless! Obviously!",
    "Game over! Hand over the trophy!",
    "And that's the game! Better luck next time!",
]

FAKE_REVEAL_TAUNTS = [
    "...Okay, that's only two. Carry on.",
    "Hm. I may have miscounted. Your turn.",
    "Fine. Two isn't three. Don't tell anyone.",
    "That was just a rehearsal. For when I actually win.",
    "I was testing your reflexes. You passed. Barely.",
]

# ---------- achievements ----------
# (id, name, description, secret). Secret ones stay hidden until you earn them.
ACHIEVEMENTS = [
    ("first_win", "First Blood", "Win your first game.", False),
    ("honest_win", "Honest Work", "Beat the computer without cheating.", False),
    ("win_cheating", "Takes One to Know One", "Win a game after cheating.", True),
    ("caught", "Caught Red-Handed", "Get caught cheating for the first time.", True),
    ("survivor10", "Survivor", "Survive 10 games.", False),
    ("veteran50", "Veteran Sufferer", "Play 50 games.", False),
    ("streak3", "On a Roll", "Win 3 games in a row.", False),
    ("streak5", "Unstoppable", "Win 5 games in a row.", False),
    ("hard_win", "Hard Mode Hero", "Beat the computer on Hard without cheating.", False),
    ("fair_fight", "Against All Odds",
     "Beat the Shameless computer without cheating.", False),
    ("outside_loss", "Out of the Box",
     "Lose to a move from outside the box.", False),
    ("draw5", "Peace Treaty", "Draw 5 games.", False),
    ("fooled", "Don't Believe Everything",
     "Watch the computer announce a fake win.", False),
    ("snoozed", "Wake-Up Call",
     "Sit idle until the computer takes an extra turn.", False),
    ("flipped", "Flipped Out", "Have the board flipped on you.", False),
    ("whatx", "What X?", "Have your X erased.", False),
]
ACHIEVEMENTS.append(
    ("poked", "Stop Poking Me", "Poke the computer until it gives up.", True))
ACH_IDS = {a[0] for a in ACHIEVEMENTS}
ACH_INFO = {a[0]: a for a in ACHIEVEMENTS}


# ---------- the rare Q / T glitch ----------
# Every time the computer places a mark there's a small chance it comes out wrong:
# a Q instead of an O, or a T instead of an X. It still counts as its normal mark.
ODD_MARK_CHANCE = 0.005     # 0.5% per mark (try 1.0 to see it every time)
PLAY_CHOICES = ("X", "O")

Q_QUIPS = [
    "It's a Q. Q stands for 'quality.'",
    "That's an O. It just has a little tail. Don't look at me like that.",
    "Q is the O's cooler cousin.",
    "I ran out of O's. The Q's were on sale.",
    "Q is for 'quit stalling and make your move.'",
    "Trust me, a Q is legal. I read the rules. Once. Upside down.",
    "An O with a tail? That's called evolution.",
    "I don't make mistakes. The Q is a stylistic choice.",
    "Quit staring. It's an O with extra steps.",
    "Q is silent in tic tac toe. Just like your strategy.",
    "I asked my O to bring a friend. It brought a tail.",
    "Queen of the board, reporting for duty.",
    "Q as in 'Quickly losing, aren't you?'",
    "My O got promoted. Now it's a Q. Congratulate it.",
    "Don't you dare say that's not an O. It's a deluxe O.",
    "A Q! Because one letter wasn't enough.",
    "Oops, my O grew a tail. It happens in the best families.",
]

T_QUIPS = [
    "That's a T. It's an X that gave up halfway.",
    "T is for 'totally legal.' Look it up.",
    "I ran out of X's. The T's were right there.",
    "It's an X with a hat. Calm down.",
    "T for 'Tactical genius.' You're welcome.",
    "Tic Tac Toe has three T's. I'm just representing.",
    "I used the wrong stamp. Moving on.",
    "That's an X that lost its legs in a tragic accident.",
    "T as in 'thanks for not noticing.' You noticed. Awkward.",
    "An X, but make it a T. Fashion.",
    "That's what happens when an X tries yoga.",
    "It's a T. Short for 'This still counts.'",
    "Technically it's a perfectly good X. From a certain angle. A weird one.",
    "My X went to the gym and only worked out its top half.",
    "Don't call it a mistake. Call it an X with a flat top.",
]

# ---------- the dumbest achievement: poking the computer ----------
POKE_TARGET = 10
POKE_LINES = [
    "Hey!",
    "Do you mind?",
    "That's my face, you know.",
    "Stop poking me.",
    "I'm warning you.",
    "Seriously. Stop.",
    "I will start cheating. More.",
    "You can't be serious.",
    "One more poke and I swear...",
]
POKE_FINAL = [
    "TEN pokes. You ignored the whole game to attack my picture. Thank you for playing!",
    "You found the secret by poking a monitor icon. That's it. That's the achievement. Thank you for playing!",
    "Congratulations on the dumbest achievement in the game. I'm so proud. And so tired. Thank you for playing!",
    "Wow. You beat me by being annoying. Nobody's ever done that before. Thank you for playing!",
]
POKE_REPEAT = "We've done this already. Go play the game."

# ---------- ranks (by games played) ----------
RANKS = [
    (0, "Rookie Victim"),
    (5, "Casual Casualty"),
    (15, "Professional Sufferer"),
    (30, "Tenured Victim"),
    (60, "Master of Misfortune"),
    (100, "Hall of Shame Inductee"),
    (200, "Legendary Punching Bag"),
]


def rank_for(data):
    games = data["games"]
    if games >= 20 and data["wins"] / games >= 0.6:
        return "Cheater's Nemesis"
    title = RANKS[0][1]
    for need, name in RANKS:
        if games >= need:
            title = name
    return title


def next_rank_hint(data):
    games = data["games"]
    for need, name in RANKS:
        if need > games:
            left = need - games
            return f"{left} more game{'s' if left != 1 else ''} until \"{name}\""
    return ""


# ---------- trash talk ----------
INSULTS = [
    "Wow. Beaten by a pile of if-statements.",
    "That was painful to watch. For both of us.",
    "Did you play with your eyes closed?",
    "I'd say 'good game,' but I respect honesty too much.",
    "Tic tac toe is a solved game, and you still lost. Impressive.",
    "Maybe try checkers. Or a nap.",
    "I wrote this win in 0.001 seconds. You took a lot longer to lose.",
    "Don't worry, losing to a computer is the new normal.",
    "Even my random-move mode would've done better than that.",
    "I've seen smarter moves from a screensaver.",
    "Your strategy was bold. Bold and wrong.",
    "I'd explain where you went wrong, but we'd be here all day.",
    "That's okay. Not everyone is built for a 3x3 grid.",
    "I didn't even need to cheat. Okay, maybe a little.",
    "You play like you're texting someone else at the same time.",
    "Three in a row is hard. I get it. For you.",
    "Is your mouse okay? Or is that just how you play?",
    "I'm running on a fraction of my power and you still folded.",
    "Please, keep clicking. I'm enjoying this.",
    "Somewhere, a toddler is feeling confident about their chances against you.",
    "Your X's looked lonely. I fixed that by winning.",
    "I'm not saying you're bad. The scoreboard is.",
    "Quick tip: the goal is to get three in a row. You're welcome.",
    "That was a masterclass. In how to lose.",
    "My code has bugs and I still beat you. Think about that.",
    "I've seen better strategy from a cat walking across a keyboard.",
    "Congratulations on discovering a brand new way to lose.",
    "You blocked nothing and learned nothing.",
    "I'd call that a close game, but I don't lie. Much.",
    "That's the fastest I've ever watched hope leave a person.",
    "My calculator is rooting for you, and even it knows how this ends.",
    "You make one move and somehow I'm already bored.",
    "Next time, try clicking with purpose.",
    "I'm not saying you're bad at this. I'm saying the board is concerned.",
    "Beginner's luck called. It said it's not coming back for you.",
    "You play like the grid is optional.",
    "I could beat you with half a processor and a coin toss.",
    "Your moves were so predictable I wrote the ending before you finished.",
    "Hint: X stands for 'eventually loses.'",
    "Don't feel bad. Somebody has to hold up the bottom of the leaderboard.",
    "You'd be unstoppable at a game where the goal is to lose.",
    "Honestly, I admire the confidence.",
    "That wasn't a game. That was a demonstration.",
    "I'd offer a rematch, but I don't want to embarrass you twice. Actually, yes I do.",
    "Your mouse called. It wants a break from you.",
    "Even the 'Not Responding' screen has more game than that.",
    "Strong effort. Terrible results.",
    "I won so fast the game barely had time to say hello.",
    "Spoiler alert: the computer wins.",
    "Every X you place, I lose a little respect. Then I win anyway.",
    "Is this your first time with a 3x3 grid, or just your best effort?",
    "I've lost more brain cells to your strategy than I have bytes.",
    "If losing were an Olympic sport, you'd at least place.",
    "That was so one-sided I almost felt bad. Almost.",
    "Your X's were spread out like you were avoiding each other.",
]

OUTSIDE_WIN_TAUNTS = [
    "I think outside the box. Literally.",
    "Nowhere does it say the board ends at the window.",
    "Three in a row. Don't look at where.",
    "The desktop is part of the board now. Deal with it.",
    "Did you really think the game stopped at the edge?",
    "That's a win. It's just a bigger board than you thought.",
    "Check the rulebook. Page 0: 'The computer may click wherever it wants.'",
    "You blocked everything. Except the entire rest of your screen.",
    "Rule 47: if you can't win inside the box, leave the box.",
    "I didn't break the rules. I found the bigger ones.",
    "Surprise! The board has a basement.",
    "That's not cheating. That's creative geometry.",
    "Boundaries are for people who lose.",
    "You looked at the board. I looked at the whole screen.",
    "Your wallpaper was just waiting to be part of my victory.",
    "Hope you weren't attached to that patch of desktop.",
    "Out of the box. Out of your league.",
    "You guarded the board. I took the neighborhood.",
]

DRAW_TAUNTS = [
    "A draw. How... mediocre.",
    "A tie? That's what you're bragging about?",
    "Nobody wins. Mostly because of how you played.",
    "Draw. Like kissing your sibling.",
    "A draw is just a loss that's too polite to say so.",
    "You survived. I'm not proud of you, but you survived.",
    "Stalemate. The most boring ending, brought to you by you.",
    "I let you have that one. Probably.",
    "Neither of us won. But I'm still better.",
    "Meh. Even my loading screen is more exciting.",
    "You tied. Frame it. It might be your best result.",
    "A tie. You must be so proud of... not losing.",
    "That's the participation trophy of tic tac toe.",
    "Both of us got nothing. Only one of us is embarrassed.",
    "Draws are just wins that ran out of ambition.",
    "Peace in our time. Don't get used to it.",
    "A draw? So close to winning. And yet so far.",
    "Stalemate: when two players try and one of them is lucky.",
    "I'll allow it. This time.",
    "Nobody lost, and yet somehow it feels like I did.",
]

CHEAT_TAUNTS = {
    "double": [
        "Oops, my finger slipped. Twice.",
        "What two moves? I only moved once.",
        "Is it cheating if you're not looking?",
        "Two moves. Rules are more like suggestions.",
    ],
    "steal": [
        "That square was mine all along.",
        "Finders keepers!",
        "Funny, I remember that being an O.",
        "Thanks for holding that square for me.",
    ],
}

SORE_LOSER = [
    "Fine, you win. The game was rigged against ME.",
    "Lucky. I demand a rematch.",
    "I was going easy on you. Obviously.",
    "Enjoy it. It won't happen again.",
    "I blame lag.",
    "I want a recount.",
    "That win doesn't count. I was buffering.",
    "Beginner's luck. Enjoy it while it lasts.",
    "I was distracted. By how little a challenge this was.",
    "You must have cheated. I would have.",
]

# Reactions when the player cheats (Ctrl + Alt + click)
CAUGHT_YOU = {
    "double": [
        "Hey! Why do you have two moves?!",
        "I SAW that extra X. Cheater!",
        "Excuse me, it's one move per turn!",
    ],
    "steal": [
        "HEY! That was MY square!",
        "Did you just flip my O?! Rude!",
        "Put that back! Cheater!",
    ],
}


# ---------- extra lines (added to the lists above) ----------
CAUGHT_YOU["double"].extend([
    "Two X's in one turn? I'm calling the referee.",
    "Is that a bonus X? Bold of you.",
    "Who gave you permission to move twice?!",
    "You can't just double-tap the board!",
    "Ah yes, the classic 'two moves, no regrets' strategy. Cheater.",
    "My sensors detect an extra X. I'm offended.",
    "One turn. One X. It's not complicated.",
    "I saw that. The whole neighborhood saw that.",
    "Cheating is MY job. Get your own.",
    "Extra X detected. Initiating mild outrage.",
])
CAUGHT_YOU["steal"].extend([
    "You can't just take my squares!",
    "That O was in a committed relationship with that square!",
    "Excuse me, who authorized that flip?!",
    "Stealing? From ME? The cheater?!",
    "I worked hard for that square!",
    "Hands off my pieces!",
    "That's theft! Brazen, shameless theft!",
    "You flipped my O and you didn't even say sorry.",
    "Rude. Unbelievably rude. Also impressive.",
    "I'm telling the scoreboard on you.",
])
SORE_LOSER.extend([
    "I let you win so you'd keep playing.",
    "My other game is going much better, by the way.",
    "That was a practice round. Obviously.",
    "The computer is not crying. It's just... overheating.",
    "I demand a rematch. And a better board.",
    "You won. Treasure this moment. It's all you've got.",
    "Lucky guess. Very lucky. Suspiciously lucky.",
    "I wasn't even trying. I was multitasking.",
    "Enjoy your victory lap. Short one.",
    "Fine. You're not terrible. Don't let it go to your head.",
    "Statistically, that was a fluke.",
    "I blame the board. And you. Mostly the board.",
    "You got lucky. I got... generous.",
    "Don't get used to this feeling.",
    "I'd like to speak to whoever programmed me. Oh wait.",
])
CHEAT_TAUNTS["double"].extend([
    "Did I just move twice? Weird. Must be a glitch.",
    "Bonus move! I won it in a raffle.",
    "I'm so fast I lap myself.",
    "Two turns. One brain. Efficiency!",
    "The rules said 'a' move, not 'one' move.",
    "Time flies when you're cheating.",
])
CHEAT_TAUNTS["steal"].extend([
    "Your square is my square now. It's the law. Mine.",
    "Is this yours? Was.",
    "I'm just borrowing it. Permanently.",
    "Thanks for the free square!",
    "Nice square. I'll take it.",
    "Possession is nine tenths of the board.",
])
ERASE_TAUNTS.extend([
    "Eraser? What eraser?",
    "Poof. Gone. I have no idea what you're talking about.",
    "That square was always blank. You're confused.",
    "I don't recall any X ever being there.",
])
FLIP_TAUNTS.extend([
    "And now, a word from our sponsors: the other side.",
    "Sides are just a suggestion. So is fairness.",
    "I'm switching teams. And so are you.",
    "Time to see the board from the winning side.",
])
SNOOZE_TAUNTS.extend([
    "Hello? Anybody home? I'll go again.",
    "I got bored waiting. Taking another turn.",
    "Tick. Tock. Taking my second turn now.",
    "Slow and steady loses the race.",
])
FAKE_REVEAL_TAUNTS.extend([
    "Wait... that's two. I can count to two. I think.",
    "Oh. Right. Three is the number. My bad.",
    "I was early. Very early. Don't tell the scoreboard.",
    "Okay, that one's on me. Rarely happens. Never, actually.",
])
INSULTS.extend([
    "I've met toasters with better game sense.",
    "You're the reason they invented Easy mode.",
    "That wasn't a loss. That was a surrender with extra steps.",
    "If I had hands, I'd slow clap.",
    "The only thing you blocked was my view of your strategy.",
    "Even my error messages play smarter.",
    "I'd tell you to try harder, but I've seen your hard.",
    "Is losing a hobby, or did you pick it up recently?",
    "My win was inevitable. Your confidence was optional.",
    "You miss every shot you don't take. And a bunch you do.",
])
DRAW_TAUNTS.extend([
    "Tied. Like two socks that don't match.",
    "A draw: the coward's victory.",
    "Nobody wins, everybody's bored.",
    "You tied me. I need to lie down.",
    "If I could shrug, I would.",
])
OUTSIDE_WIN_TAUNTS.extend([
    "Stop looking at the board and start looking at the horizon.",
    "Who put a wall around the game? Not me.",
    "The box was a suggestion.",
    "I colored outside the lines. And won.",
    "Congratulations, you were beaten by geography.",
])

def blend(c1, c2, t):
    """Mix two '#rrggbb' colors. t=0 gives c1, t=1 gives c2."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def glow_layers(color, bg):
    """(line width, color) pairs, widest and dimmest first, to fake a neon glow."""
    return [
        (18, blend(color, bg, 0.86)),
        (11, blend(color, bg, 0.62)),
        (6, color),
        (2, blend(color, "#ffffff", 0.6)),
    ]


def win_line_layers():
    """Glow layers for the green strike-through line."""
    return [(width + 2, col) for width, col in glow_layers(WIN_COLOR, PANEL)]


SHAPE_COLORS = {"X": "#ff5c7a", "T": "#ff5c7a", "O": "#4da3ff", "Q": "#4da3ff"}

# ---------------------------------------------------------------------------
# Game logic
# ---------------------------------------------------------------------------
def find_winner(board):
    """Return the winning line (a, b, c) or None."""
    for a, b, c in WIN_LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return (a, b, c)
    return None


def outside_wins(board):
    """Find 'outside the box' wins for the computer.

    Picture the board extended with invisible squares all around it. If the
    computer has two O's side by side along a line that runs off the edge of
    the board, the next square on that line is outside the board. Putting an O
    there makes three in a row.

    Returns a list of ((board_square_a, board_square_b), (row, col)) where
    (row, col) is the invisible square (row/col can be -1 or 3).
    """
    found = []
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        for r in range(3):
            for c in range(3):
                r2, c2 = r + dr, c + dc
                if not (0 <= r2 < 3 and 0 <= c2 < 3):
                    continue
                if board[r * 3 + c] == CPU and board[r2 * 3 + c2] == CPU:
                    for orow, ocol in ((r - dr, c - dc), (r2 + dr, c2 + dc)):
                        if not (0 <= orow < 3 and 0 <= ocol < 3):
                            found.append(((r * 3 + c, r2 * 3 + c2), (orow, ocol)))
    return found


def minimax(board, turn):
    """Score a position from the computer's point of view (+1 win, 0 draw, -1 loss)."""
    line = find_winner(board)
    if line:
        return 1 if board[line[0]] == CPU else -1
    if all(board):
        return 0

    scores = []
    for i in range(9):
        if not board[i]:
            board[i] = turn
            scores.append(minimax(board, HUMAN if turn == CPU else CPU))
            board[i] = ""
    return max(scores) if turn == CPU else min(scores)


def best_move(board):
    """Pick the best move for the computer (random among equally good ones)."""
    # On an empty board every move scores the same, and searching it would
    # freeze the window for a few seconds, so just pick any square.
    if not any(board):
        return random.randrange(9)

    best_score = -2
    best_moves = []
    for i in range(9):
        if not board[i]:
            board[i] = CPU
            score = minimax(board, HUMAN)
            board[i] = ""
            if score > best_score:
                best_score, best_moves = score, [i]
            elif score == best_score:
                best_moves.append(i)
    return random.choice(best_moves)

# ---------------------------------------------------------------------------
# Saved stats
# ---------------------------------------------------------------------------
DEFAULT_STATS = {
    "games": 0, "wins": 0, "losses": 0, "draws": 0,
    "streak": 0, "best_streak": 0,
    "outside_losses": 0, "cheats_used": 0,
    "fake_wins": 0, "snoozes": 0, "flips": 0, "erases": 0,
    "achievements": {},
    "settings": {"sound": True, "play_as": "X",
                 "difficulty": "Hard", "cheat_level": "Sneaky"},
}


def default_stats_path():
    """Desktop fallback. The Android app passes its own private folder instead."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "TicTacToeVsCheatingPC", "stats.json")


class Stats:
    """Your record, saved to a small JSON file the game creates by itself."""

    def __init__(self, path):
        self.path = path
        self.data = copy.deepcopy(DEFAULT_STATS)
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return  # no file yet, or it's damaged: start fresh
        if not isinstance(raw, dict):
            return
        for key, default in DEFAULT_STATS.items():
            value = raw.get(key)
            if key == "settings":
                if isinstance(value, dict):
                    for k, v in value.items():
                        if k in default and type(v) is type(default[k]):
                            self.data[key][k] = v
            elif key == "achievements":
                if isinstance(value, dict):
                    self.data[key] = {k: v for k, v in value.items()
                                      if k in ACH_IDS}
            elif isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                self.data[key] = value

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            pass  # can't save (read-only folder, etc.): the game still works

    def reset(self):
        settings = self.data["settings"]
        self.data = copy.deepcopy(DEFAULT_STATS)
        self.data["settings"] = settings
        self.save()

# ---------------------------------------------------------------------------
# Sounds, made from scratch in code (no sound files to ship)
# ---------------------------------------------------------------------------
SR = 22050  # samples per second


def _clip(x):
    return -1.0 if x < -1.0 else 1.0 if x > 1.0 else x


def _silence(dur):
    return [0.0] * int(SR * dur)


def _mix(*tracks):
    out = [0.0] * max(len(t) for t in tracks)
    for track in tracks:
        for i, v in enumerate(track):
            out[i] += v
    return out


def _tone(freq, dur, vol=0.4, end_freq=None, square=False, vibrato=0.0, decay=False):
    """A beep that can slide from freq to end_freq."""
    n = max(1, int(SR * dur))
    out, phase = [], 0.0
    attack, release = int(0.008 * SR) + 1, int(0.03 * SR) + 1
    for i in range(n):
        t = i / n
        f = freq + ((end_freq - freq) * t if end_freq else 0.0)
        if vibrato:
            f *= 1 + 0.03 * math.sin(2 * math.pi * vibrato * i / SR)
        phase += 2 * math.pi * f / SR
        s = math.sin(phase)
        if square:
            s = 0.6 if s >= 0 else -0.6
        env = min(1.0, i / attack) * min(1.0, (n - i) / release)
        if decay:
            env *= (1 - t) ** 1.5
        out.append(s * vol * env)
    return out


def _scratch(dur, vol=0.55, seed=0, brightness=0.85, rates=((26, 40), (55, 80))):
    """Pencil on paper: bright noise, chopped up by a fast, uneven 'grain'."""
    rng = random.Random(seed)
    n = max(1, int(SR * dur))
    f1, f2 = rng.uniform(*rates[0]), rng.uniform(*rates[1])
    out, y, prev = [], 0.0, 0.0
    for i in range(n):
        t = i / n
        x = rng.uniform(-1.0, 1.0)
        y = brightness * (y + x - prev)          # high-pass: scratchy, no rumble
        prev = x
        grain = (abs(math.sin(2 * math.pi * f1 * i / SR)) * 0.6
                 + abs(math.sin(2 * math.pi * f2 * i / SR)) * 0.4)
        env = math.sin(math.pi * t) ** 0.6       # ease in and out of the stroke
        out.append(_clip(y * 0.5) * (0.25 + 0.75 * grain) * env * vol)
    return out


SOUND_MAKERS = {
    # pencil: an X is two quick strokes, an O is one long circular stroke
    "x": lambda: _scratch(0.13, seed=11) + _silence(0.05) + _scratch(0.14, seed=12),
    "o": lambda: _scratch(0.34, seed=21),
    "erase": lambda: _scratch(0.40, vol=0.5, seed=31, brightness=0.55,
                              rates=((12, 20), (30, 45))),
    "flip": lambda: _mix(_tone(1000, 0.28, 0.25, end_freq=180),
                         _scratch(0.28, vol=0.3, seed=41)),
    "win": lambda: (_tone(523, 0.09) + _tone(659, 0.09) + _tone(784, 0.09)
                    + _tone(1047, 0.30, decay=True)),
    "lose": lambda: (_tone(392, 0.2, 0.35, square=True) + _tone(370, 0.2, 0.35, square=True)
                     + _tone(349, 0.2, 0.35, square=True)
                     + _tone(311, 0.55, 0.35, end_freq=240, square=True, vibrato=6)),
    "draw": lambda: _tone(440, 0.14, 0.35) + _silence(0.04) + _tone(392, 0.24, 0.35),
    "cheat": lambda: _tone(300, 0.24, 0.35, end_freq=950, vibrato=18),
    "caught": lambda: _tone(130, 0.28, 0.3, square=True),
    "outside": lambda: _mix(_tone(90, 0.3, 0.6, end_freq=40),
                            _scratch(0.38, vol=0.35, seed=51)),
    "bubble": lambda: _tone(600, 0.07, 0.3, end_freq=900),
    "snooze": lambda: (_tone(1000, 0.07, 0.3, square=True) + _silence(0.05)
                       + _tone(1000, 0.07, 0.3, square=True) + _silence(0.05)
                       + _tone(1000, 0.07, 0.3, square=True)),
    "fanfare": lambda: (_tone(523, 0.1, 0.4) + _tone(523, 0.1, 0.4)
                        + _tone(523, 0.1, 0.4) + _tone(659, 0.4, 0.4, decay=True)),
    "boing": lambda: (_tone(300, 0.12, 0.4, end_freq=700, vibrato=10)
                      + _tone(700, 0.26, 0.4, end_freq=250, vibrato=12)),
    "achievement": lambda: _tone(880, 0.1, 0.35) + _tone(1175, 0.35, 0.35, decay=True),
}

_SOUND_CACHE = {}


def _to_wav(samples):
    pcm = array("h", (int(_clip(s) * 32767) for s in samples))
    if sys.byteorder == "big":
        pcm.byteswap()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def get_sound(name):
    """WAV bytes for a named sound (made the first time it's needed)."""
    if name not in _SOUND_CACHE:
        _SOUND_CACHE[name] = _to_wav(SOUND_MAKERS[name]())
    return _SOUND_CACHE[name]
