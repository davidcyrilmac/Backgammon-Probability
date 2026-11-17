"""Backgammon Best Move -- Kivy front end for bgengine.py

Light (cream) checkers are YOURS and move 24 -> 1 (top-right round to
bottom-right). Red checkers are the opponent's. Set up the position by
tapping the board, pick the dice, press ANALYZE.
"""
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Rectangle, Triangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget

import bgengine as bg

BG = (0.09, 0.11, 0.13, 1)
FELT = (0.10, 0.30, 0.22, 1)
BAR = (0.28, 0.18, 0.10, 1)
TRI_A = (0.72, 0.58, 0.38, 1)
TRI_B = (0.42, 0.26, 0.16, 1)
LIGHT = (0.96, 0.93, 0.84, 1)
RED = (0.78, 0.14, 0.14, 1)
INK = (0.08, 0.08, 0.08, 1)
COLS = 14          # 6 points | bar | 6 points | off-tray


def _tex(text, size, color=(1, 1, 1, 1)):
    lab = CoreLabel(text=text, font_size=size, color=color)
    lab.refresh()
    return lab.texture


class BoardView(Widget):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        self.bind(pos=self.redraw, size=self.redraw)

    # ---- geometry -------------------------------------------------------
    def _geom(self):
        m = max(dp(12), self.height * 0.05)
        x0, y0 = self.x, self.y + m
        w, h = self.width, self.height - 2 * m
        return x0, y0, w, h, m, w / COLS

    @staticmethod
    def _col_of_point(p):
        idx = (p - 13) if p >= 13 else (12 - p)
        return idx if idx < 6 else idx + 1

    # ---- drawing --------------------------------------------------------
    def redraw(self, *_):
        self.canvas.clear()
        if self.width < 10:
            return
        pos = self.app.pos_view
        x0, y0, w, h, m, cw = self._geom()
        half = h / 2.0
        r = min(cw * 0.46, half / 6.0)
        with self.canvas:
            Color(*FELT)
            Rectangle(pos=(x0, y0), size=(w, h))
            Color(*BAR)
            Rectangle(pos=(x0 + 6 * cw, y0), size=(cw, h))
            Rectangle(pos=(x0 + 13 * cw, y0), size=(cw, h))
            # triangles + numbers + checkers
            for p in range(1, 25):
                col = self._col_of_point(p)
                cx = x0 + col * cw + cw / 2
                top = p >= 13
                Color(*(TRI_A if p % 2 else TRI_B))
                if top:
                    Triangle(points=[cx - cw / 2 + 2, y0 + h, cx + cw / 2 - 2,
                                     y0 + h, cx, y0 + h - half * 0.85])
                else:
                    Triangle(points=[cx - cw / 2 + 2, y0, cx + cw / 2 - 2, y0,
                                     cx, y0 + half * 0.85])
                t = _tex(str(p), sp(9), (0.85, 0.85, 0.85, 1))
                ty = (y0 + h + m / 2) if top else (y0 - m / 2)
                Color(1, 1, 1, 1)
                Rectangle(texture=t, size=t.size,
                          pos=(cx - t.width / 2, ty - t.height / 2))
                n = pos.board[p - 1]
                if n:
                    self._stack(cx, y0, h, r, abs(n), top,
                                LIGHT if n > 0 else RED)
            # bar and tray: one disc with a count
            qy = h / 4.0
            self._badge(x0 + 6.5 * cw, y0 + 3 * qy, r, pos.bar_opp, RED)
            self._badge(x0 + 6.5 * cw, y0 + qy, r, pos.bar_me, LIGHT)
            self._badge(x0 + 13.5 * cw, y0 + 3 * qy, r, pos.off_opp, RED)
            self._badge(x0 + 13.5 * cw, y0 + qy, r, pos.off_me, LIGHT)
            for cxx, lab in ((6.5, "BAR"), (13.5, "OFF")):
                t = _tex(lab, sp(8), (0.9, 0.8, 0.6, 1))
                Color(1, 1, 1, 1)
                Rectangle(texture=t, size=t.size,
                          pos=(x0 + cxx * cw - t.width / 2,
                               y0 + h / 2 - t.height / 2))

    def _disc(self, cx, cy, r, color):
        Color(0, 0, 0, 0.55)
        Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
        Color(*color)
        Ellipse(pos=(cx - r + 1.5, cy - r + 1.5), size=(2 * r - 3, 2 * r - 3))

    def _stack(self, cx, y0, h, r, n, top, color):
        shown = min(n, 5)
        for k in range(shown):
            cy = (y0 + h - r - k * 2 * r) if top else (y0 + r + k * 2 * r)
            self._disc(cx, cy, r, color)
        if n > 5:
            k = shown - 1
            cy = (y0 + h - r - k * 2 * r) if top else (y0 + r + k * 2 * r)
            t = _tex(str(n), sp(13), INK)
            Color(1, 1, 1, 1)
            Rectangle(texture=t, size=t.size,
                      pos=(cx - t.width / 2, cy - t.height / 2))

    def _badge(self, cx, cy, r, n, color):
        if n <= 0:
            return
        self._disc(cx, cy, r, color)
        t = _tex(str(n), sp(13), INK)
        Color(1, 1, 1, 1)
        Rectangle(texture=t, size=t.size,
                  pos=(cx - t.width / 2, cy - t.height / 2))

    # ---- touch ----------------------------------------------------------
    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        x0, y0, w, h, m, cw = self._geom()
        col = int((touch.x - x0) // cw)
        col = max(0, min(COLS - 1, col))
        if col == 6:
            self.app.tap("bar")
        elif col == 13:
            self.app.tap("off")
        else:
            idx = col if col < 6 else col - 1       # 0..11 along the row
            top = touch.y > y0 + h / 2
            p = (13 + idx) if top else (12 - idx)
            self.app.tap("point", p - 1)
        return True


class BGApp(App):
    title = "Backgammon Best Move"

    def build(self):
        Window.clearcolor = BG
        self.pos_base = bg.opening_position()
        self.pos_view = self.pos_base
        self.previewing = False
        self.busy = False
        self.cands = []

        root = BoxLayout(orientation="vertical", padding=dp(6),
                         spacing=dp(4))
        self.board = BoardView(self, size_hint_y=0.36)
        root.add_widget(self.board)

        self.status = Label(text="", size_hint_y=None, height=dp(34),
                            font_size=sp(12), halign="center",
                            valign="middle", markup=True)
        self.status.bind(size=lambda w, s: setattr(w, "text_size", s))
        root.add_widget(self.status)

        # tools: side + add/remove
        row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(4))
        self.t_light = ToggleButton(text="Light", group="side",
                                    state="down", allow_no_selection=False)
        self.t_red = ToggleButton(text="Red", group="side",
                                  allow_no_selection=False)
        self.t_add = ToggleButton(text="Add", group="mode", state="down",
                                  allow_no_selection=False)
        self.t_rem = ToggleButton(text="Remove", group="mode",
                                  allow_no_selection=False)
        for b in (self.t_light, self.t_red, self.t_add, self.t_rem):
            row.add_widget(b)
        root.add_widget(row)

        row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(4))
        for txt, fn in (("Opening", self.do_opening), ("Clear", self.do_clear),
                        ("Swap sides", self.do_swap),
                        ("Reset view", self.do_reset_view)):
            b = Button(text=txt)
            b.bind(on_release=lambda _b, f=fn: f())
            row.add_widget(b)
        root.add_widget(row)

        # dice
        self.dice = {}
        for name in ("d1", "d2"):
            row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
            row.add_widget(Label(text="Die " + name[1], size_hint_x=0.9,
                                 font_size=sp(12)))
            for v in range(1, 7):
                tb = ToggleButton(text=str(v), group=name)
                tb.value = v
                row.add_widget(tb)
            self.dice[name] = row
            root.add_widget(row)

        self.go = Button(text="ANALYZE", size_hint_y=None, height=dp(48),
                         bold=True, background_color=(0.1, 0.55, 0.35, 1))
        self.go.bind(on_release=lambda *_: self.do_analyze())
        root.add_widget(self.go)

        self.results = GridLayout(cols=1, size_hint_y=None, spacing=dp(3))
        self.results.bind(minimum_height=self.results.setter("height"))
        sv = ScrollView(size_hint_y=0.40)
        sv.add_widget(self.results)
        root.add_widget(sv)
        self.say("Set up the board, choose both dice, press ANALYZE.")
        self.refresh()
        return root

    # ---- helpers --------------------------------------------------------
    def side(self):
        return "L" if self.t_light.state == "down" else "R"

    def delta(self):
        return 1 if self.t_add.state == "down" else -1

    def die(self, name):
        for ch in self.dice[name].children:
            if isinstance(ch, ToggleButton) and ch.state == "down":
                return ch.value
        return None

    def say(self, text):
        self.results.clear_widgets()
        lab = Label(text=text, size_hint_y=None, height=dp(60),
                    font_size=sp(13), halign="center", valign="middle")
        lab.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.results.add_widget(lab)

    def refresh(self):
        pos = self.pos_view
        me, opp = bg.pip_counts(pos)
        nh, loss, nb = bg.hit_stats(pos)
        tag = "  [b]PREVIEW (Red to roll)[/b]" if self.previewing else ""
        probs = bg.validate(pos)
        warn = ("  [color=ff8844]%s[/color]" % "; ".join(probs)) if probs \
            and not self.previewing else ""
        self.status.text = (
            "Pips  Light %d  Red %d   |   Red hits a Light blot on "
            "%d/36 rolls (%.1f%%)%s%s" % (me, opp, nh, nh / 0.36, tag, warn))
        self.board.redraw()

    # ---- editing --------------------------------------------------------
    def _begin_edit(self):
        if self.previewing:
            self.previewing = False
            self.pos_view = self.pos_base
        return self.pos_base

    def tap(self, kind, idx=None):
        if self.busy:
            return
        pos = self._begin_edit()
        d, s = self.delta(), self.side()
        if kind == "point":
            bg.edit_point(pos, idx, s, d)
        elif kind == "bar":
            bg.edit_bar(pos, s, d)
        else:
            bg.edit_off(pos, s, d)
        self.pos_view = pos
        self.refresh()

    def do_opening(self):
        self.pos_base = bg.opening_position()
        self.pos_view, self.previewing = self.pos_base, False
        self.say("Opening position loaded.")
        self.refresh()

    def do_clear(self):
        self.pos_base = bg.Position()
        self.pos_view, self.previewing = self.pos_base, False
        self.say("Board cleared. Tap points to add checkers (15 each).")
        self.refresh()

    def do_swap(self):
        self.pos_base = self._begin_edit().flipped()
        self.pos_view = self.pos_base
        self.say("Sides swapped: the colours trade places.")
        self.refresh()

    def do_reset_view(self):
        self.previewing = False
        self.pos_view = self.pos_base
        self.refresh()

    # ---- analysis -------------------------------------------------------
    def do_analyze(self):
        if self.busy:
            return
        pos = self._begin_edit().copy()
        d1, d2 = self.die("d1"), self.die("d2")
        if d1 is None or d2 is None:
            self.say("Pick both dice first.")
            return
        probs = bg.validate(pos)
        if probs:
            self.say("Fix the board first:\n" + "; ".join(probs))
            return
        self.busy = True
        self.go.text = "Thinking..."
        self.go.disabled = True
        self.say("Evaluating every legal play against all 21 opposing rolls...")

        def work():
            try:
                c = bg.analyze(pos, d1, d2, depth=2, top_n=8)
                err = None
            except Exception as e:           # keep the UI alive
                c, err = [], repr(e)
            Clock.schedule_once(lambda dt: self.show(c, d1, d2, err))

        threading.Thread(target=work, daemon=True).start()

    def show(self, cands, d1, d2, err):
        self.busy = False
        self.go.text = "ANALYZE"
        self.go.disabled = False
        self.cands = cands
        self.results.clear_widgets()
        if err:
            self.say("Error: " + err)
            return
        if not cands:
            self.say("No legal move with %d-%d: you must pass." % (d1, d2))
            return
        best = cands[0]
        head = Label(
            text="[b]Best: %s[/b]   (est. %.1f%% to win)\n"
                 "Tap a line to preview the resulting position."
                 % (best.notation or "(no move)", best.win_pct),
            markup=True, size_hint_y=None, height=dp(52), font_size=sp(13),
            halign="center", valign="middle")
        head.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.results.add_widget(head)
        for i, c in enumerate(cands[:25], 1):
            shot = ("%d/36 shots" % c.shot_rolls) if c.blots else "safe"
            gap = "" if i == 1 else "  (%.1f%% behind)" % (
                cands[0].win_pct - c.win_pct)
            btn = Button(
                text="%d.  %s\n[size=%d]win %.1f%%%s   |   %s   |   %d blot%s"
                     "   |   %s[/size]"
                     % (i, c.notation or "(no move)", int(sp(10)), c.win_pct,
                        gap, shot, c.blots, "" if c.blots == 1 else "s",
                        "2-ply" if c.ply == 2 else "1-ply"),
                markup=True, size_hint_y=None, height=dp(56),
                halign="left", valign="middle", font_size=sp(14),
                background_color=(0.2, 0.34, 0.5, 1) if i == 1
                else (0.18, 0.2, 0.24, 1))
            btn.bind(size=lambda w, s: setattr(w, "text_size",
                                               (s[0] - dp(12), s[1])))
            btn.bind(on_release=lambda _b, cc=c: self.preview(cc))
            self.results.add_widget(btn)

    def preview(self, cand):
        self.previewing = True
        self.pos_view = cand.pos
        self.refresh()


if __name__ == "__main__":
    BGApp().run()
