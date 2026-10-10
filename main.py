"""Tic Tac Toe vs a Cheating Phone - Android (Kivy) edition.

Touch controls
  tap a square ........ place your mark
  hold a square ....... a certain kind of "click" (the desktop Ctrl+Alt+click)
  tap the monitor ..... poke the computer
  menu button ......... New Game, Stats, Sound, About, Exit
  Android Back ........ closes dialogs; press twice on the board to leave
"""
import os
import random
import threading
import time

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex as hexc
from kivy.utils import platform

import game_core as gc
from controller import Game
from game_core import ACHIEVEMENTS, CHEAT_LEVELS, CPU, HUMAN, PLAY_CHOICES

LONG_PRESS = 0.45        # seconds to hold a square for the "secret" click
GLOW_SCALE = 0.8         # tweak if lines look too thick / thin on your phone
CONTACT = "kennyjones18@gmail.com"

# Colors (the desktop palette comes from game_core; a few extras for touch UI)
BTN_BG = "#13242b"
BTN_EDGE = "#2a4650"
SEL_BG = "#0e3a42"
CYAN = "#37e6ff"
MUTED = "#8aa4ad"


# ---------------------------------------------------------------------------
# Small UI helpers
# ---------------------------------------------------------------------------
def paint_bg(widget, color, radius=0):
    """Give any widget a solid (optionally rounded) background."""
    with widget.canvas.before:
        Color(*hexc(color))
        rect = (RoundedRectangle(pos=widget.pos, size=widget.size, radius=[radius])
                if radius else Rectangle(pos=widget.pos, size=widget.size))

    def sync(*_):
        rect.pos, rect.size = widget.pos, widget.size
    widget.bind(pos=sync, size=sync)


def text_label(text="", size=14, color=gc.TEXT, bold=False, halign="center",
               valign="middle", markup=False, **kw):
    lbl = Label(text=text, font_size=sp(size), color=hexc(color), bold=bold,
                halign=halign, valign=valign, markup=markup, **kw)
    lbl.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
    return lbl


def vibrate(ms):
    try:
        from plyer import vibrator
        vibrator.vibrate(time=ms / 1000.0)
    except Exception:
        pass            # no vibrator / desktop / permission missing


def open_mail(address):
    """Open the mail app (or copy the address if there isn't one)."""
    try:
        if platform == "android":
            from jnius import autoclass
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            Activity = autoclass("org.kivy.android.PythonActivity")
            intent = Intent(Intent.ACTION_SENDTO)
            intent.setData(Uri.parse("mailto:" + address))
            Activity.mActivity.startActivity(intent)
        else:
            import webbrowser
            webbrowser.open("mailto:" + address)
        return True
    except Exception:
        Clipboard.copy(address)
        return False


class TapLabel(ButtonBehavior, Label):
    """A label that can be tapped (used for the email link)."""


class FlatButton(ButtonBehavior, Label):
    """A rounded, dark-themed button (Kivy's default grey one clashes)."""

    def __init__(self, text="", bg=BTN_BG, fg=gc.TEXT, border=None, radius=22,
                 size=15, bold=False, on_tap=None, **kw):
        super().__init__(text=text, color=hexc(fg), font_size=sp(size), bold=bold, **kw)
        self._bg, self._border = bg, border or bg
        self._radius = dp(radius)
        with self.canvas.before:
            self._fill = Color(*hexc(bg))
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[self._radius])
            self._edge = Color(*hexc(self._border))
            self._line = Line(rounded_rectangle=(self.x, self.y, self.width, self.height,
                                                 self._radius), width=dp(1.3))
        self.bind(pos=self._sync, size=self._sync, state=self._recolor)
        if on_tap:
            self.bind(on_release=lambda *_: on_tap())

    def _sync(self, *_):
        r = max(1, min(self._radius, self.height / 2, self.width / 2))
        self._rect.pos, self._rect.size = self.pos, self.size
        self._rect.radius = [r]
        self._line.rounded_rectangle = (self.x, self.y, self.width, self.height, r)

    def _recolor(self, *_):
        self._fill.rgba = hexc(gc.blend(self._bg, "#ffffff", 0.18) if self.state == "down" else self._bg)

    def restyle(self, bg, border, fg, bold=False):
        self._bg, self._border = bg, border
        self._edge.rgba = hexc(border)
        self.color = hexc(fg)
        self.bold = bold
        self._recolor()


class Segmented(BoxLayout):
    """Big touch-friendly replacement for the desktop 'pill' toggles."""

    def __init__(self, title, key, options, game, **kw):
        super().__init__(orientation="vertical", size_hint_y=None, height=dp(78),
                         spacing=dp(4), **kw)
        self.key, self.game, self.buttons = key, game, {}
        self.add_widget(text_label(title, 13, MUTED, halign="left", size_hint_y=None, height=dp(22)))
        row = BoxLayout(spacing=dp(8))
        for name in options:
            b = FlatButton(text=name, size=14, radius=14,
                           on_tap=lambda n=name: self.choose(n))
            self.buttons[name] = b
            row.add_widget(b)
        self.add_widget(row)
        self.refresh()

    def choose(self, name):
        self.game.set_option(self.key, name)
        self.refresh()

    def refresh(self):
        current = getattr(self.game, self.key)
        for name, b in self.buttons.items():
            if name == current:
                b.restyle(SEL_BG, CYAN, gc.TEXT, bold=True)
            else:
                b.restyle(BTN_BG, BTN_EDGE, MUTED)


class IconWidget(Widget):
    """The little person / computer icons in the score bar."""

    def __init__(self, kind, **kw):
        super().__init__(size_hint_x=None, width=dp(44), **kw)
        self.kind = kind
        self.bind(pos=self.redraw, size=self.redraw)

    def redraw(self, *_):
        self.canvas.clear()
        cx, cy = self.x + self.width / 2.0, self.y + self.height / 2.0
        u = min(self.width, self.height) / 40.0
        with self.canvas:
            if self.kind == "person":
                Color(*hexc("#ff5c7a"))
                Ellipse(pos=(cx - 6 * u, cy + 1 * u), size=(12 * u, 12 * u))
                RoundedRectangle(pos=(cx - 11 * u, cy - 13 * u), size=(22 * u, 12 * u),
                                 radius=[8 * u, 8 * u, 1, 1])
            else:   # monitor
                Color(*hexc("#4da3ff"))
                Line(rounded_rectangle=(cx - 14 * u, cy - 6 * u, 28 * u, 20 * u, 3 * u), width=2 * u)
                Line(points=[cx, cy - 6 * u, cx, cy - 12 * u], width=1.6 * u)
                Line(points=[cx - 7 * u, cy - 12 * u, cx + 7 * u, cy - 12 * u],
                     width=1.6 * u, cap="round")
                Line(points=[cx - 7 * u, cy + 4 * u, cx - 2 * u, cy + 8 * u], width=1.4 * u)


class PokeIcon(IconWidget):
    """The monitor: tap it ten times. (You know you want to.)"""

    def __init__(self, on_poke, **kw):
        super().__init__("monitor", **kw)
        self.on_poke = on_poke

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.on_poke()
            return True
        return super().on_touch_down(touch)


class GrudgeBar(BoxLayout):
    """'Grudge' label plus ten ticks that fill up as the computer gets angrier."""

    def __init__(self, **kw):
        super().__init__(size_hint_y=None, height=dp(18), spacing=dp(8), **kw)
        self.level = 0
        self.add_widget(text_label("Grudge", 12, MUTED,
                                   halign="right", size_hint_x=None, width=dp(56)))
        self.bar = Widget()
        self.add_widget(self.bar)
        self.bar.bind(pos=self.redraw, size=self.redraw)
        self.opacity = 0

    def set_level(self, level, visible):
        self.level = level
        self.opacity = 1 if visible else 0
        self.redraw()

    def redraw(self, *_):
        b = self.bar
        b.canvas.clear()
        n = gc.GRUDGE_MAX
        gap = dp(3)
        w = max(1, (b.width - gap * (n - 1)) / n)
        h = dp(8)
        with b.canvas:
            for k in range(n):
                Color(*hexc("#ff5c7a" if k < self.level else "#1d3340"))
                RoundedRectangle(pos=(b.x + k * (w + gap), b.y + b.height / 2.0 - h / 2),
                                 size=(w, h), radius=[dp(3)])


# ---------------------------------------------------------------------------
# The board (+ the margin around it where the "outside the box" O appears)
# ---------------------------------------------------------------------------
class PlayArea(Widget):
    """Draws the 3x3 board inside a 5x5 area: the extra ring is the outside zone."""

    def __init__(self, screen, **kw):
        super().__init__(**kw)
        self.screen = screen
        self.progress = {}             # square -> 0..1 draw-in animation
        self.shake_off = (0.0, 0.0)
        self._anim = None
        self.bind(pos=self.redraw, size=self.redraw)

    # ----- geometry -----
    def geometry(self):
        side = min(self.width, self.height)
        cell = side / 5.0
        x0 = self.x + (self.width - side) / 2 + self.shake_off[0]
        y0 = self.y + (self.height - side) / 2 + self.shake_off[1]
        return x0 + cell, y0 + side - cell, cell        # board left, board top, cell size

    def to_px(self, u, v):
        gx, gy, cell = self.geometry()
        return gx + u * cell, gy - v * cell

    def cell_at(self, x, y):
        gx, gy, cell = self.geometry()
        if cell <= 0:
            return None
        pad = cell * 0.22
        if not (gx - pad <= x <= gx + 3 * cell + pad and gy - 3 * cell - pad <= y <= gy + pad):
            return None
        col = min(2, max(0, int((x - gx) // cell)))
        row = min(2, max(0, int((gy - y) // cell)))
        return row * 3 + col

    # ----- drawing -----
    def redraw(self, snap=False, *_):
        if snap is True:
            self.progress.clear()
        self.canvas.clear()
        g = self.screen.game
        if g is None or min(self.size) <= 0:
            return
        gx, gy, cell = self.geometry()
        k = cell / 104.0 * GLOW_SCALE
        pad = cell * 0.22
        with self.canvas:
            # panel behind the board
            Color(*hexc(gc.PANEL))
            RoundedRectangle(pos=(gx - pad, gy - 3 * cell - pad),
                             size=(3 * cell + 2 * pad, 3 * cell + 2 * pad), radius=[cell * 0.2])
            Color(*hexc(gc.PANEL_EDGE))
            Line(rounded_rectangle=(gx - pad, gy - 3 * cell - pad,
                                    3 * cell + 2 * pad, 3 * cell + 2 * pad, cell * 0.2),
                 width=max(1.0, 1.5 * k))
            # grid
            for width, col in gc.glow_layers(gc.CYAN, gc.PANEL):
                Color(*hexc(col))
                for n in (1, 2):
                    Line(points=[gx + n * cell, gy - 0.1 * cell, gx + n * cell, gy - 2.9 * cell],
                         width=max(1.0, width * k), cap="round")
                    Line(points=[gx + 0.1 * cell, gy - n * cell, gx + 2.9 * cell, gy - n * cell],
                         width=max(1.0, width * k), cap="round")
            # marks
            for i, who in enumerate(g.board):
                if who:
                    cx, cy = self.to_px((i % 3) + 0.5, (i // 3) + 0.5)
                    self.draw_shape(g.shape_of(who, i), cx, cy, cell,
                                    self.progress.get(i, 1.0), gc.PANEL)
            # the O that was placed outside the box
            if g.outside_mark:
                row, col, shape = g.outside_mark
                cx, cy = self.to_px(col + 0.5, row + 0.5)
                self.draw_shape(shape, cx, cy, cell, 1.0, gc.BG)
            # glowing strike lines (drawn last, on top of every mark)
            for p1, p2 in g.lines.values():
                (x1, y1), (x2, y2) = self.to_px(*p1), self.to_px(*p2)
                for width, col in gc.win_line_layers():
                    Color(*hexc(col))
                    Line(points=[x1, y1, x2, y2], width=max(1.0, width * k), cap="round")

    def draw_shape(self, shape, cx, cy, cell, p, bg):
        color = gc.SHAPE_COLORS[shape]
        k = cell / 104.0 * GLOW_SCALE
        for width, col in gc.glow_layers(color, bg):
            Color(*hexc(col))
            w = max(1.0, width * k)
            if shape in ("X", "T"):
                r = cell * 0.25
                first = min(1.0, p * 2)
                second = max(0.0, p * 2 - 1)
                Line(points=[cx - r, cy + r, cx - r + 2 * r * first, cy + r - 2 * r * first],
                     width=w, cap="round")
                if second > 0:
                    Line(points=[cx + r, cy + r, cx + r - 2 * r * second, cy + r - 2 * r * second],
                         width=w, cap="round")
                if shape == "T" and p >= 0.5:      # the glitched X grows a stray tail
                    Line(points=[cx + r * 0.2, cy + r * 1.2, cx + r * 0.2, cy - r * 1.35],
                         width=w, cap="round")
            else:
                r = cell * 0.27
                ring = p if shape == "O" else min(1.0, p / 0.85)
                if ring >= 0.999:
                    Line(circle=(cx, cy, r), width=w)
                elif ring > 0.02:
                    Line(circle=(cx, cy, r, 0, 360 * ring), width=w, cap="round")
                if shape == "Q" and p > 0.85:
                    t = min(1.0, (p - 0.85) / 0.15)
                    sx, sy = cx + r * 0.35, cy - r * 0.35
                    Line(points=[sx, sy, sx + r * 0.75 * t, sy - r * 0.75 * t], width=w, cap="round")

    # ----- animation -----
    def animate_mark(self, i):
        self.progress[i] = 0.02
        if self._anim is None:
            self._anim = Clock.schedule_interval(self._tick, 1 / 60.0)
        self.redraw()

    def _tick(self, dt):
        for i in list(self.progress):
            self.progress[i] += dt / 0.12
            if self.progress[i] >= 1.0:
                del self.progress[i]
        if not self.progress and self._anim is not None:
            self._anim.cancel()
            self._anim = None
        self.redraw()

    def shake(self):
        steps = [random.choice((-1, 1)) * dp(random.choice((4, 7, 10))) for _ in range(10)]

        def step(dt, n=[0]):
            if n[0] >= len(steps):
                self.shake_off = (0.0, 0.0)
                self.redraw()
                return False
            self.shake_off = (steps[n[0]], steps[n[0]] * 0.4 * (-1) ** n[0])
            n[0] += 1
            self.redraw()
        Clock.schedule_interval(step, 0.03)

    # ----- touch: tap = place a mark, hold = the "secret" click -----
    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        cell = self.cell_at(*touch.pos)
        if cell is None:
            return False
        touch.grab(self)
        touch.ud["cell"] = cell
        touch.ud["start"] = touch.pos
        touch.ud["long"] = False
        touch.ud["moved"] = False
        touch.ud["ev"] = Clock.schedule_once(lambda dt: self._long_press(touch), LONG_PRESS)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            sx, sy = touch.ud["start"]
            if abs(touch.x - sx) > dp(16) or abs(touch.y - sy) > dp(16):
                touch.ud["moved"] = True
                touch.ud["ev"].cancel()
            return True
        return False

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        touch.ud["ev"].cancel()
        if not touch.ud["long"] and not touch.ud["moved"]:
            self.screen.game.click(touch.ud["cell"])
        return True

    def _long_press(self, touch):
        touch.ud["long"] = True
        if self.screen.game.click(touch.ud["cell"], secret=True):
            vibrate(40)


# ---------------------------------------------------------------------------
# Sound (the WAVs are synthesized by game_core; we save them once and load them)
# ---------------------------------------------------------------------------
class SoundBank:
    def __init__(self, folder):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        self.ready = set()
        self.cache = {}
        threading.Thread(target=self._make_all, daemon=True).start()

    def _path(self, name):
        return os.path.join(self.folder, name + ".wav")

    def _make_all(self):
        for name in gc.SOUND_MAKERS:
            try:
                path = self._path(name)
                if not os.path.exists(path):
                    tmp = path + ".tmp"
                    with open(tmp, "wb") as f:
                        f.write(gc.get_sound(name))
                    os.replace(tmp, path)
                self.ready.add(name)
            except Exception:
                pass

    def play(self, name):
        if name not in self.ready:
            return
        snd = self.cache.get(name)
        if snd is None:
            snd = SoundLoader.load(self._path(name))
            self.cache[name] = snd
        if snd:
            snd.stop()
            snd.play()


# ---------------------------------------------------------------------------
# The main screen (also the "ui" object the Game talks to)
# ---------------------------------------------------------------------------
class GameScreen(BoxLayout):
    def __init__(self, data_dir, **kw):
        super().__init__(orientation="vertical", padding=[dp(10), dp(6), dp(10), dp(12)],
                         spacing=dp(4), **kw)
        self.game = None
        self.sounds = SoundBank(os.path.join(data_dir, "sounds"))
        paint_bg(self, gc.BG)

        # --- top bar ---
        bar = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        bar.add_widget(FlatButton(text="Menu", size=14, radius=16, size_hint_x=None, width=dp(76),
                                  bg=gc.MENU_BG,
                                  border=BTN_EDGE, on_tap=self.open_menu))
        bar.add_widget(text_label(gc.TITLE, 15, gc.TEXT, bold=True))
        bar.add_widget(FlatButton(text="Options", size=14, radius=16, size_hint_x=None,
                                  width=dp(76), border=BTN_EDGE, on_tap=self.open_options))
        self.add_widget(bar)

        # --- status, chat line, grudge, scores ---
        self.status = text_label("", 22, gc.TEXT, bold=True, size_hint_y=None, height=dp(38))
        self.add_widget(self.status)
        self.taunt = text_label("", 14, gc.TAUNT_COLOR, size_hint_y=None, height=dp(50))
        self.taunt.italic = True
        self.add_widget(self.taunt)
        self.grudge_bar = GrudgeBar()
        self.add_widget(self.grudge_bar)

        score = BoxLayout(size_hint_y=None, height=dp(52))
        self.score_labels = {}
        for key, icon in (("you", IconWidget("person")),
                          ("cpu", PokeIcon(self.poke_pressed)),
                          ("draw", None)):
            cell = BoxLayout()
            if icon:
                cell.add_widget(icon)
            lbl = text_label("", 14, gc.TEXT, halign="left", markup=True)
            self.score_labels[key] = lbl
            cell.add_widget(lbl)
            score.add_widget(cell)
        self.add_widget(score)

        # --- the board ---
        self.board = PlayArea(self)
        self.add_widget(self.board)

        # --- new game ---
        self.add_widget(FlatButton(text="New Game", size=17, bold=True, size_hint_y=None,
                                   height=dp(54), bg=SEL_BG, border=CYAN, on_tap=self.new_game_pressed))

        self.game = Game(self, gc.Stats(os.path.join(data_dir, "stats.json")))
        self.game.start()
        self.refresh_grudge()

    # ===== the "ui" interface used by Game =====
    def schedule(self, secs, fn):
        return Clock.schedule_once(lambda dt: fn(), secs)

    def cancel(self, handle):
        handle.cancel()

    def play(self, name):
        self.sounds.play(name)

    def vibrate(self, ms):
        vibrate(ms)

    def set_status(self, text):
        self.status.text = text

    def show_taunt(self, text, gold):
        self.taunt.text = text
        self.taunt.color = hexc(gc.GOLD if gold else gc.TAUNT_COLOR)
        self.taunt.italic = not gold
        self.taunt.bold = gold

    def refresh_scores(self):
        d = self.game.stats.data
        self.score_labels["you"].text = f"[size={int(sp(11))}]You[/size]\n[b]{d['wins']}[/b]"
        self.score_labels["cpu"].text = f"[size={int(sp(11))}]Computer[/size]\n[b]{d['losses']}[/b]"
        self.score_labels["draw"].text = f"[size={int(sp(11))}]Draws[/size]\n[b]{d['draws']}[/b]"

    def refresh_grudge(self):
        if self.game is None:
            return
        level = self.game.cheat_level
        self.grudge_bar.set_level(self.game.grudge, level != "Honest" and self.game.grudge > 0)

    def animate_mark(self, i):
        self.board.animate_mark(i)

    def redraw(self, snap=False):
        self.board.redraw(snap=snap)

    def shake(self):
        self.board.shake()

    def show_goodbye(self):
        view = ModalView(size_hint=(0.88, None), height=dp(250), auto_dismiss=False,
                         background="", background_color=hexc(gc.BG))
        box = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(8))
        box.add_widget(text_label("Thank you for playing!", 20, gc.CYAN, bold=True,
                                  size_hint_y=None, height=dp(36)))
        box.add_widget(text_label(f"Achievement unlocked: {gc.ACH_INFO['poked'][1]}", 14, gc.GOLD,
                                  size_hint_y=None, height=dp(26)))
        italic = text_label("You found the dumbest one. See you next time.", 14, gc.TEXT)
        italic.italic = True
        box.add_widget(italic)
        box.add_widget(FlatButton(text="OK", size=16, bold=True, size_hint_y=None, height=dp(50),
                                  bg=SEL_BG, border=CYAN, on_tap=view.dismiss))
        view.add_widget(box)
        view.bind(on_dismiss=self.quit_app)          # OK, Back button, or the 12 s timer all leave
        view.open()
        self.game.play("fanfare")
        Clock.schedule_once(lambda dt: view.dismiss(), 12)

    def quit_app(self, *_):
        App.get_running_app().stop()

    # ===== button handlers =====
    def poke_pressed(self):
        if self.game:
            self.game.poke()

    def new_game_pressed(self):
        self.game.new_game()

    def open_modal(self, view):
        """Open a dialog and pause the snooze timer while it is up."""
        self.game.hold()
        view.bind(on_dismiss=lambda *_: self.game.release())
        view.open()

    def make_dialog(self, size_hint, height=None):
        view = ModalView(size_hint=size_hint, background="", background_color=hexc(gc.PANEL))
        if height:
            view.size_hint_y = None
            view.height = height
        return view

    # ----- menu -----
    def open_menu(self):
        view = self.make_dialog((0.8, None), dp(8 + 5 * 58 + 8))
        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))

        def later(fn):
            def go():
                view.dismiss()
                Clock.schedule_once(lambda dt: fn(), 0.05)
            return go

        sound = FlatButton(text="", size=16, border=BTN_EDGE, radius=16)

        def sound_text():
            sound.text = "Sound: " + ("On" if self.game.sound_on else "Off")

        def toggle():
            self.game.toggle_sound()
            sound_text()
        sound.bind(on_release=lambda *_: toggle())
        sound_text()

        for label, fn in (("New Game", later(self.game.new_game)),
                          ("Stats", later(self.open_stats))):
            box.add_widget(FlatButton(text=label, size=16, border=BTN_EDGE, radius=16, on_tap=fn))
        box.add_widget(sound)
        box.add_widget(FlatButton(text="About", size=16, border=BTN_EDGE, radius=16,
                                  on_tap=later(self.open_about)))
        box.add_widget(FlatButton(text="Exit Program", size=16, border="#7a2c3b", radius=16,
                                  on_tap=later(self.quit_app)))
        view.add_widget(box)
        self.open_modal(view)

    # ----- options -----
    def open_options(self):
        view = self.make_dialog((0.92, None), dp(32 + 3 * 82 + 62 + 24))
        box = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(8))
        box.add_widget(text_label("Options", 18, gc.TEXT, bold=True, size_hint_y=None, height=dp(30)))
        box.add_widget(Segmented("Play as", "play_as", list(PLAY_CHOICES), self.game))
        box.add_widget(Segmented("Difficulty", "difficulty", ["Easy", "Hard"], self.game))
        box.add_widget(Segmented("Cheating", "cheat_level", list(CHEAT_LEVELS), self.game))
        box.add_widget(FlatButton(text="Done", size=16, bold=True, size_hint_y=None, height=dp(50),
                                  bg=SEL_BG, border=CYAN, on_tap=view.dismiss))
        view.add_widget(box)
        self.open_modal(view)

    # ----- stats -----
    def open_stats(self):
        d = self.game.stats.data
        view = self.make_dialog((0.96, 0.94))
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(6))
        box.add_widget(text_label("Your Record", 20, gc.CYAN, bold=True,
                                  size_hint_y=None, height=dp(30)))
        box.add_widget(text_label(gc.rank_for(d), 15, gc.GOLD, size_hint_y=None, height=dp(24)))
        hint = gc.next_rank_hint(d)
        if hint:
            box.add_widget(text_label(hint, 11, "#6f9aa3", size_hint_y=None, height=dp(18)))

        games = d["games"]
        rate = f"{round(100 * d['wins'] / games)}%" if games else "-"
        tiles = [("Games", games), ("Wins", d["wins"]), ("Losses", d["losses"]),
                 ("Draws", d["draws"]), ("Win rate", rate), ("Win streak", d["streak"]),
                 ("Best streak", d["best_streak"]), ("Outside losses", d["outside_losses"])]
        if d["cheats_used"]:
            tiles.append(("Caught cheating", d["cheats_used"]))
        rows = (len(tiles) + 2) // 3
        grid = GridLayout(cols=3, spacing=dp(6), size_hint_y=None,
                          height=dp(rows * 56 + (rows - 1) * 6))
        for name, value in tiles:
            t = BoxLayout(orientation="vertical")
            paint_bg(t, gc.PANEL, dp(12))
            t.add_widget(text_label(str(value), 19, gc.CYAN, bold=True))
            t.add_widget(text_label(name, 11, "#8fb9c1", size_hint_y=None, height=dp(18)))
            grid.add_widget(t)
        box.add_widget(grid)

        earned = d["achievements"]
        box.add_widget(text_label(f"Achievements   {len(earned)}/{len(ACHIEVEMENTS)}", 15, gc.TEXT,
                                  bold=True, size_hint_y=None, height=dp(30)))
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        col = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
        col.bind(minimum_height=col.setter("height"))
        for aid, name, desc, secret in ACHIEVEMENTS:
            have = aid in earned
            if secret and not have:
                name, desc = "Secret achievement", "Keep playing to find out."
            card = BoxLayout(size_hint_y=None, height=dp(62), padding=dp(10), spacing=dp(8))
            paint_bg(card, SEL_BG if have else gc.PANEL, dp(12))
            card.add_widget(text_label("OK" if have else "?", 13, gc.GOLD if have else MUTED,
                                       bold=True, size_hint_x=None, width=dp(26)))
            txt = BoxLayout(orientation="vertical")
            txt.add_widget(text_label(name, 14, gc.GOLD if have else gc.TEXT, bold=True,
                                      halign="left", size_hint_y=None, height=dp(22)))
            txt.add_widget(text_label(desc, 12, MUTED, halign="left", valign="top"))
            card.add_widget(txt)
            col.add_widget(card)
        scroll.add_widget(col)
        box.add_widget(scroll)

        reset = FlatButton(text="Reset Stats", size=14, border="#7a2c3b", radius=14)
        state = {"armed": False, "ev": None}

        def disarm(*_):
            state["armed"] = False
            reset.text = "Reset Stats"

        def on_reset(*_):
            if not state["armed"]:
                state["armed"] = True
                reset.text = "Tap again to erase everything"
                state["ev"] = Clock.schedule_once(disarm, 3)
            else:
                if state["ev"]:
                    state["ev"].cancel()
                self.game.reset_stats()
                view.dismiss()
                Clock.schedule_once(lambda dt: self.open_stats(), 0.1)
        reset.bind(on_release=on_reset)
        buttons = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        buttons.add_widget(reset)
        buttons.add_widget(FlatButton(text="Close", size=15, bold=True, bg=SEL_BG, border=CYAN,
                                      radius=14, on_tap=view.dismiss))
        box.add_widget(buttons)
        view.add_widget(box)
        self.open_modal(view)

    # ----- about -----
    def open_about(self):
        view = self.make_dialog((0.92, None), min(dp(500), Window.height * 0.92))
        box = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(6))
        box.add_widget(text_label(gc.TITLE, 18, gc.CYAN, bold=True, size_hint_y=None, height=dp(34)))
        box.add_widget(text_label(f"Version {gc.VERSION}", 12, "#6f9aa3", size_hint_y=None, height=dp(20)))
        box.add_widget(text_label(
            "You play X. The computer plays O. The computer is a very good player "
            "and an even better cheater. Find out what it is willing to do to win.\n\n"
            "Pick how dirty it plays under Options. On Honest it plays fair. "
            "On Shameless, it does not.\n\n"
            "Rumour has it that the computer is not the only one who can cheat. "
            "On a touchscreen, some taps just need a little longer.", 14, gc.TEXT))
        credit = text_label("Created by Telz (J.Whitesides)", 14, gc.TEXT, size_hint_y=None, height=dp(30))
        credit.italic = True
        box.add_widget(credit)
        mail = TapLabel(text=f"[color={CYAN[1:]}][u]{CONTACT}[/u][/color]", markup=True,
                        font_size=sp(15), color=hexc(gc.TEXT), size_hint_y=None, height=dp(48))

        def on_mail(*_):
            if not open_mail(CONTACT):          # no mail app on the phone: copy the address instead
                mail.text = f"{CONTACT}  (copied!)"
        mail.bind(on_release=on_mail)
        box.add_widget(mail)
        box.add_widget(FlatButton(text="OK", size=16, bold=True, size_hint_y=None, height=dp(50),
                                  bg=SEL_BG, border=CYAN, on_tap=view.dismiss))
        view.add_widget(box)
        self.open_modal(view)


# ---------------------------------------------------------------------------
# The app
# ---------------------------------------------------------------------------
class TicTacToeApp(App):
    title = gc.TITLE

    def build(self):
        Window.clearcolor = hexc(gc.BG)
        if platform not in ("android", "ios"):
            Window.size = (390, 800)        # phone-shaped window when testing on a PC
        Window.bind(on_keyboard=self.on_key)
        self.last_back = 0.0
        self.screen = GameScreen(self.user_data_dir)
        return self.screen

    def on_key(self, window, key, *args):
        if key != 27:                       # Android Back (or Esc on a PC)
            return False
        for child in Window.children[:]:
            if isinstance(child, ModalView):
                child.dismiss()
                return True
        now = time.time()
        if now - self.last_back < 2.0:
            self.stop()
        else:
            self.last_back = now
            self.screen.show_taunt("Press Back again to leave. I'll miss you.", False)
        return True

    def on_pause(self):
        self.screen.game.hold()             # snooze timer must not run while you're away
        self.screen.game.stats.save()
        return True

    def on_resume(self):
        self.screen.game.release()

    def on_stop(self):
        self.screen.game.stats.save()


if __name__ == "__main__":
    TicTacToeApp().run()
