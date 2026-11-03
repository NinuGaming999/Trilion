"""Custom-painted widgets for the Trilion command center."""
import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QRadialGradient)
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from .theme import C, col, draw_icon, font, pen
from .wave import STATE_COLORS, tri

KIND = {  # feed kind -> (colour, icon, chip text)
    "you": ("cyan", "mic", "YOU"), "reply": ("violet", "chat", "REPLY"), "action": ("amber", "hand", "ACTION"),
    "warn": ("red", "warn", "WARN"), "info": ("blue", "info", "INFO"), "live": ("green", "pulse", "LIVE"),
    "tip": ("green", "skills", "TIP"),
}


class Panel(QWidget):
    """Glass panel with a glowing border, corner accents and an upper-case title."""

    def __init__(self, title="", action=None, on_action=None, pad=(14, 38, 14, 12)):
        super().__init__()
        self.title = title
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(*pad)
        self.body.setSpacing(6)
        self.action = None
        if action:
            self.action = QPushButton(action, self)
            self.action.setCursor(Qt.PointingHandCursor)
            self.action.setFlat(True)
            self.action.setStyleSheet("QPushButton{color:#38c9ff;border:none;background:transparent;font-size:11px;padding:2px 4px}"
                                      "QPushButton:hover{color:#bff0ff}")
            if on_action:
                self.action.clicked.connect(on_action)

    def resizeEvent(self, e):
        if self.action:
            self.action.adjustSize()
            self.action.move(self.width() - self.action.width() - 12, 8)
        super().resizeEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        g = QLinearGradient(0, 0, 0, r.height())
        g.setColorAt(0, col((14, 46, 88), 190))
        g.setColorAt(1, col((5, 20, 44), 210))
        p.setBrush(g)
        p.setPen(pen((38, 150, 255), 1, 115))
        p.drawRoundedRect(r, 10, 10)
        p.setPen(pen((120, 220, 255), 1, 45))
        p.drawLine(QPointF(r.left() + 16, r.top() + 1), QPointF(r.right() - 16, r.top() + 1))
        p.setPen(pen("cyan", 2, 235))
        L = 15
        for x, y, sx, sy in ((r.left(), r.top(), 1, 1), (r.right(), r.top(), -1, 1),
                             (r.left(), r.bottom(), 1, -1), (r.right(), r.bottom(), -1, -1)):
            p.drawLine(QPointF(x + sx * 1, y + sy * 9), QPointF(x + sx * 1, y + sy * 1))
            p.drawLine(QPointF(x + sx * 1, y + sy * 1), QPointF(x + sx * L, y + sy * 1))
        if self.title:
            p.setFont(font(8.2, True, 1.9))
            p.setPen(col((150, 218, 255)))
            room = (self.action.width() + 26) if self.action else 14
            p.drawText(QRectF(14, 9, r.width() - room - 14, 22), Qt.AlignLeft | Qt.AlignVCenter, self.title.upper())


class NavButton(QPushButton):
    def __init__(self, icon, text, badge=None):
        super().__init__()
        self.icon_name, self.text_, self.badge = icon, text, badge
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(38)
        self.setFlat(True)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        if self.isChecked() or self.underMouse():
            g = QLinearGradient(r.left(), 0, r.right(), 0)
            g.setColorAt(0, col("cyan", 70 if self.isChecked() else 28))
            g.setColorAt(1, col("cyan", 8))
            p.setBrush(g)
            p.setPen(pen("cyan", 1, 170 if self.isChecked() else 60))
            p.drawRoundedRect(r, 7, 7)
        draw_icon(p, self.icon_name, QRectF(r.left() + 10, r.top() + 6, 20, r.height() - 12),
                  "cyan" if self.isChecked() else (150, 190, 230), 1.4)
        p.setFont(font(9.6, self.isChecked()))
        p.setPen(col("text" if self.isChecked() else (190, 215, 245)))
        p.drawText(QRectF(r.left() + 42, r.top(), r.width() - 70, r.height()), Qt.AlignLeft | Qt.AlignVCenter, self.text_)
        if self.badge:
            b = QRectF(r.right() - 30, r.center().y() - 9, 24, 18)
            p.setBrush(col((30, 70, 130), 200))
            p.setPen(pen("cyan", 1, 90))
            p.drawRoundedRect(b, 9, 9)
            p.setFont(font(8, True))
            p.setPen(col("text"))
            p.drawText(b, Qt.AlignCenter, str(self.badge))


class Donut(QWidget):
    def __init__(self, label, color="cyan"):
        super().__init__()
        self.label, self.color, self.value, self.sub = label, color, 0.0, ""
        self.setMinimumSize(70, 70)

    def set(self, value, sub=""):
        self.value, self.sub = max(0.0, min(100.0, value or 0.0)), sub
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = min(self.width(), self.height()) - 10
        r = QRectF((self.width() - s) / 2, (self.height() - s) / 2, s, s)
        w = max(5, s * 0.1)
        rr = r.adjusted(w / 2, w / 2, -w / 2, -w / 2)
        p.setPen(pen((255, 255, 255), w, 26))
        p.drawEllipse(rr)
        c = self.color if self.value < 85 else "amber"
        span = int(-self.value / 100 * 360 * 16)
        p.setPen(pen(c, w + 5, 38))
        p.drawArc(rr, 90 * 16, span)
        p.setPen(pen(c, w, 255))
        p.drawArc(rr, 90 * 16, span)
        p.setPen(col((170, 205, 240)))
        p.setFont(font(max(6.5, s / 11), False))
        p.drawText(QRectF(r.left(), r.center().y() - s * .30, r.width(), s * .26), Qt.AlignCenter, self.label)
        p.setPen(col("text"))
        p.setFont(font(max(8.5, s / 6.2), True))
        p.drawText(QRectF(r.left(), r.center().y() - s * .06, r.width(), s * .3), Qt.AlignCenter,
                   f"{self.value:.0f}%" if not self.sub else self.sub)


class MiniWave(QWidget):
    def __init__(self, color="cyan"):
        super().__init__()
        self.color, self.active, self.t, self.level = color, False, 0.0, 0.0
        self.setMinimumHeight(18)

    def tick(self, t, level=0.0):
        self.t, self.level = t, level
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n, w, h = 26, self.width(), self.height()
        for i in range(n):
            x = (i + 0.5) * w / n
            amp = (0.18 + 0.82 * abs(math.sin(self.t * 5 + i * 0.7) * math.sin(self.t * 2.3 + i * 0.31))) if self.active else 0.12
            amp *= (0.35 + 0.65 * self.level) if self.active else 1
            y = h * 0.5 * max(0.08, amp)
            p.setPen(pen(self.color, 1.6, 230 if self.active else 70))
            p.drawLine(QPointF(x, h / 2 - y), QPointF(x, h / 2 + y))


class AgentCard(QWidget):
    def __init__(self, name, icon, color):
        super().__init__()
        self.name, self.icon, self.color = name, icon, color
        self.status, self.active = "Standby", False
        self.wave = MiniWave(color)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 10, 8)
        lay.addStretch()
        self.wave.setFixedSize(54, 26)
        lay.addWidget(self.wave, 0, Qt.AlignRight | Qt.AlignBottom)
        self.setMinimumHeight(54)

    def set_state(self, status, active):
        self.status, self.active = status, active
        self.wave.active = active
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        base = C[self.color] if isinstance(self.color, str) else self.color
        g = QLinearGradient(0, 0, r.width(), r.height())
        g.setColorAt(0, col(base, 40 if self.active else 22))
        g.setColorAt(1, col((6, 22, 46), 190))
        p.setBrush(g)
        p.setPen(pen(base, 1, 140 if self.active else 70))
        p.drawRoundedRect(r, 8, 8)
        box = QRectF(r.left() + 9, r.top() + 9, 32, 32)
        p.setBrush(col(base, 38))
        p.setPen(pen(base, 1, 120))
        p.drawRoundedRect(box, 7, 7)
        draw_icon(p, self.icon, box, base, 1.5)
        p.setFont(font(9.4, True))
        p.setPen(col("text"))
        p.drawText(QRectF(box.right() + 9, r.top() + 8, r.width() - 60, 18), Qt.AlignLeft | Qt.AlignVCenter, self.name)
        dot = C["green"] if self.active else (140, 160, 190)
        p.setBrush(col(dot, 255))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(box.right() + 13, r.top() + 36), 3, 3)
        p.setFont(font(8.2))
        p.setPen(col((60, 255, 170) if self.active else (140, 165, 200)))
        p.drawText(QRectF(box.right() + 21, r.top() + 27, r.width() - 80, 16), Qt.AlignLeft | Qt.AlignVCenter, self.status)


class OrbWidget(QWidget):
    """The Trilion core: a rotating mesh sphere made of triangles, with orbit rings and a glowing base."""

    def __init__(self, version=""):
        super().__init__()
        self.version = version
        self.t, self.level, self.state = 0.0, 0.0, "idle"
        self.color = list(STATE_COLORS["idle"])
        self.verts, self.edges = self._icosphere(2)
        self.setMinimumSize(300, 220)

    @staticmethod
    def _icosphere(sub):
        t = (1 + 5 ** 0.5) / 2
        v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
             (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
        f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
             (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11),
             (6, 2, 10), (8, 6, 7), (9, 8, 1)]
        norm = lambda a: tuple(x / math.sqrt(sum(y * y for y in a)) for x in a)
        v = [norm(a) for a in v]
        for _ in range(sub):
            cache, nf = {}, []

            def mid(i, j):
                k = (min(i, j), max(i, j))
                if k not in cache:
                    a, b = v[i], v[j]
                    v.append(norm(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)))
                    cache[k] = len(v) - 1
                return cache[k]
            for a, b, c in f:
                ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
                nf += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
            f = nf
        edges = set()
        for a, b, c in f:
            for x, y in ((a, b), (b, c), (c, a)):
                edges.add((min(x, y), max(x, y)))
        return v, sorted(edges)

    def tick(self, t, level, state, color):
        self.t, self.level, self.state, self.color = t, level, state, color
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h * 0.44
        R = min(w * 0.30, h * 0.33) * (1 + 0.035 * self.level)
        c = [int(x) for x in self.color]
        # soft halo
        rg = QRadialGradient(cx, cy, R * 1.9)
        rg.setColorAt(0, QColor(c[0], c[1], c[2], int(70 + 70 * self.level)))
        rg.setColorAt(0.5, QColor(c[0], c[1], c[2], 22))
        rg.setColorAt(1, QColor(c[0], c[1], c[2], 0))
        p.setPen(Qt.NoPen)
        p.setBrush(rg)
        p.drawEllipse(QPointF(cx, cy), R * 1.9, R * 1.9)
        # base platform
        for i, k in enumerate((1.15, 0.9, 0.65)):
            p.setPen(pen(c, 1.2, 150 - i * 35))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy + R * 1.18), R * k * 1.25, R * k * 0.2)
        # orbit rings
        for i, (tilt, sp) in enumerate(((70, 0.5), (-25, -0.35), (115, 0.25))):
            p.save()
            p.translate(cx, cy)
            p.rotate(tilt)
            p.setPen(pen(c, 1.0, 85))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(0, 0), R * 1.45, R * 0.42)
            a = self.t * sp * 2
            p.setBrush(col((255, 255, 255), 230))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(math.cos(a) * R * 1.45, math.sin(a) * R * 0.42), 2.6, 2.6)
            p.restore()
        # mesh sphere (triangles)
        ay, ax = self.t * 0.35, 0.35
        ca, sa, cb, sb = math.cos(ay), math.sin(ay), math.cos(ax), math.sin(ax)
        pts = []
        for x, y, z in self.verts:
            x1, z1 = x * ca + z * sa, -x * sa + z * ca
            y1, z2 = y * cb - z1 * sb, y * sb + z1 * cb
            pts.append((cx + x1 * R, cy + y1 * R, z2))
        p.setBrush(QColor(c[0], c[1], c[2], 18))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), R, R)
        for a, b in self.edges:
            x1, y1, z1 = pts[a]
            x2, y2, z2 = pts[b]
            depth = (z1 + z2) / 2
            alpha = int(28 + 110 * (depth + 1) / 2 + 40 * self.level)
            p.setPen(pen(c, 0.8 if depth < 0 else 1.1, min(220, alpha)))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        p.setPen(Qt.NoPen)
        for x, y, z in pts[::2]:
            if z > 0.1:
                p.setBrush(QColor(200, 245, 255, int(60 + 150 * z)))
                p.drawEllipse(QPointF(x, y), 1.4, 1.4)
        # name (on a dark band so it stays readable over the mesh)
        band = QLinearGradient(cx - R, 0, cx + R, 0)
        band.setColorAt(0, QColor(4, 14, 32, 0))
        band.setColorAt(0.5, QColor(4, 14, 32, 150))
        band.setColorAt(1, QColor(4, 14, 32, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(band)
        p.drawRect(QRectF(cx - R * 1.05, cy - R * 0.28, R * 2.1, R * 0.95))
        path = QPainterPath()
        f = font(max(18, R * 0.30), True, R * 0.12)
        text = "TRILION"
        fm = QFontMetrics(f)
        tw = fm.horizontalAdvance(text) + R * 0.12 * len(text)
        path.addText(cx - tw / 2, cy + fm.ascent() / 2 - 4, f, text)
        p.setBrush(Qt.NoBrush)
        p.setPen(pen(c, 7, 40))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(col((205, 245, 255)))
        p.drawPath(path)
        p.setFont(font(max(8.5, R * 0.1), True, 5))
        p.setPen(col((235, 250, 255), 240))
        p.drawText(QRectF(0, cy + R * 0.34, w, 24), Qt.AlignHCenter | Qt.AlignTop, "A I   C O R E")
        p.setFont(font(8.5))
        p.setPen(col((150, 190, 230)))
        p.drawText(QRectF(0, cy + R * 0.34 + 22, w, 20), Qt.AlignHCenter | Qt.AlignTop, f"v{self.version}")


class FeedRow(QWidget):
    def __init__(self, kind, text, when):
        super().__init__()
        self.kind, self.text, self.when = kind, text, when
        self.setFixedHeight(46)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color, icon, chip = KIND.get(self.kind, KIND["info"])
        base = C[color]
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setBrush(col((10, 34, 66), 150))
        p.setPen(pen((40, 140, 230), 1, 60))
        p.drawRoundedRect(r, 7, 7)
        box = QRectF(r.left() + 7, r.top() + 8, 28, 28)
        p.setBrush(col(base, 36))
        p.setPen(pen(base, 1, 110))
        p.drawRoundedRect(box, 6, 6)
        draw_icon(p, icon, box, base, 1.4)
        p.save()
        p.setClipRect(QRectF(box.right() + 8, r.top() + 4, r.width() - 110, r.height() - 8))
        p.setFont(font(8.6))
        p.setPen(col((222, 238, 255)))
        p.drawText(QRectF(box.right() + 8, r.top() + 4, r.width() - 110, r.height() - 8),
                   Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, self.text)
        p.restore()
        chip_r = QRectF(r.right() - 66, r.top() + 7, 58, 17)
        p.setBrush(col(base, 30))
        p.setPen(pen(base, 1, 120))
        p.drawRoundedRect(chip_r, 6, 6)
        p.setFont(font(7.4, True, 0.6))
        p.setPen(col(base))
        p.drawText(chip_r, Qt.AlignCenter, chip)
        p.setFont(font(7.4))
        p.setPen(col((130, 160, 200)))
        p.drawText(QRectF(r.right() - 66, r.top() + 25, 58, 14), Qt.AlignCenter, self.when)


class FeedList(QScrollArea):
    MAX = 60

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea{background:transparent}QScrollBar:vertical{width:6px;background:transparent}"
                           "QScrollBar::handle:vertical{background:rgba(60,170,255,120);border-radius:3px}"
                           "QScrollBar::add-line,QScrollBar::sub-line{height:0}")
        inner = QWidget()
        inner.setStyleSheet("background:transparent")
        self.col = QVBoxLayout(inner)
        self.col.setContentsMargins(0, 0, 4, 0)
        self.col.setSpacing(5)
        self.col.addStretch()
        self.setWidget(inner)
        self.rows = []
        self.filter = ""

    def add(self, kind, text, when):
        row = FeedRow(kind, text, when)
        self.col.insertWidget(0, row)
        self.rows.insert(0, row)
        while len(self.rows) > self.MAX:
            old = self.rows.pop()
            self.col.removeWidget(old)
            old.deleteLater()
        row.setVisible(self._match(row))
        self.verticalScrollBar().setValue(0)

    def _match(self, row):
        return not self.filter or self.filter in row.text.lower()

    def set_filter(self, text):
        self.filter = text.lower().strip()
        for r in self.rows:
            r.setVisible(self._match(r))


class Timeline(QWidget):
    MAX = 5

    def __init__(self):
        super().__init__()
        self.items = []   # dicts: t, label, status
        self.t = 0.0
        self.setMinimumHeight(110)

    def add(self, when, label):
        self.items.insert(0, {"t": when, "label": label, "status": "running"})
        del self.items[self.MAX:]
        self.update()

    def finish(self, ok):
        for it in self.items:
            if it["status"] == "running":
                it["status"] = "done" if ok else "failed"
                break
        self.update()

    def tick(self, t):
        self.t = t
        if any(i["status"] == "running" for i in self.items):
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.items:
            p.setFont(font(9))
            p.setPen(col((120, 155, 195)))
            p.drawText(self.rect(), Qt.AlignCenter, "No actions yet.\nAsk Trilion to do something.")
            return
        rh = max(30, self.height() / self.MAX)
        for i, it in enumerate(self.items):
            y = i * rh
            colr = {"running": "amber", "done": "green", "failed": "red"}[it["status"]]
            p.setFont(font(8))
            p.setPen(col((140, 170, 210)))
            p.drawText(QRectF(0, y, 46, rh * 0.6), Qt.AlignLeft | Qt.AlignVCenter, it["t"])
            p.setBrush(col(colr))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(54, y + rh * 0.3), 3.2, 3.2)
            p.setFont(font(8.6))
            p.setPen(col((225, 240, 255)))
            fm = QFontMetrics(p.font())
            p.drawText(QRectF(64, y, self.width() - 140, rh * 0.6), Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(it["label"], Qt.ElideRight, int(self.width() - 140)))
            p.setFont(font(8, True))
            p.setPen(col(colr))
            txt = {"running": "Running", "done": "Done", "failed": "Failed"}[it["status"]]
            p.drawText(QRectF(self.width() - 70, y, 70, rh * 0.6), Qt.AlignRight | Qt.AlignVCenter, txt)
            frac = 1.0 if it["status"] != "running" else (math.sin(self.t * 3) * 0.5 + 0.5) * 0.8 + 0.1
            p.setPen(pen((255, 255, 255), 2, 22))
            p.drawLine(QPointF(64, y + rh * 0.7), QPointF(self.width() - 8, y + rh * 0.7))
            p.setPen(pen(colr, 2, 220))
            p.drawLine(QPointF(64, y + rh * 0.7), QPointF(64 + (self.width() - 72) * frac, y + rh * 0.7))


class Constellation(QWidget):
    """Decorative memory map: one node per remembered fact."""

    def __init__(self):
        super().__init__()
        self.n, self.t = 0, 0.0
        self.setMinimumHeight(70)

    def set_count(self, n):
        self.n = n
        self.update()

    def tick(self, t):
        self.t = t
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rnd = random.Random(7)
        k = min(max(self.n, 6), 16)
        pts = [QPointF(rnd.uniform(0.06, 0.94) * self.width(), rnd.uniform(0.12, 0.88) * self.height()) for _ in range(k)]
        for i in range(1, k):
            j = rnd.randrange(0, i)
            p.setPen(pen("cyan", 1, 90))
            p.drawLine(pts[i], pts[j])
        for i, q in enumerate(pts):
            on = i < self.n
            pulse = 0.5 + 0.5 * math.sin(self.t * 2 + i)
            p.setBrush(col("cyan" if on else (80, 120, 170), 230 if on else 110))
            p.setPen(Qt.NoPen)
            p.drawEllipse(q, 2.4 + (1.2 * pulse if on else 0), 2.4 + (1.2 * pulse if on else 0))


class TalkBar(QPushButton):
    """The big 'TALK TO TRILION' pill with triangular waveforms on each side."""

    def __init__(self):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self.t, self.level, self.state, self.color = 0.0, 0.0, "idle", list(STATE_COLORS["idle"])
        self.title, self.sub = "TALK TO TRILION", "Tap to talk"
        self.setMinimumHeight(66)

    def tick(self, t, level, state, color):
        self.t, self.level, self.state, self.color = t, level, state, color
        self.update()

    def _zig(self, p, x0, x1, y, sign, c):
        n = 46
        path = QPainterPath()
        for i in range(n + 1):
            u = i / n
            x = x0 + (x1 - x0) * u
            amp = (3 + 15 * self.level) * (1 - u) ** 0.8
            v = tri(u * 9 * sign + self.t * 0.8) * amp
            (path.moveTo if i == 0 else path.lineTo)(x, y + v)
        p.setBrush(Qt.NoBrush)
        p.setPen(pen(c, 1.6, 200))
        p.drawPath(path)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = [int(x) for x in self.color]
        w, h = self.width(), self.height()
        pw = min(430, w * 0.55)
        pill = QRectF((w - pw) / 2, 4, pw, h - 8)
        self._zig(p, 6, pill.left() - 10, h / 2, 1, c)
        self._zig(p, w - 6, pill.right() + 10, h / 2, -1, c)
        g = QLinearGradient(pill.left(), 0, pill.right(), 0)
        g.setColorAt(0, QColor(c[0], c[1], c[2], 40 + int(40 * self.level)))
        g.setColorAt(0.5, QColor(12, 46, 90, 230))
        g.setColorAt(1, QColor(c[0], c[1], c[2], 40 + int(40 * self.level)))
        p.setPen(pen(c, 5, 40 + int(60 * self.level)))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
        p.setPen(pen(c, 1.6, 230))
        p.setBrush(g)
        p.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
        # little triangle-wave icon
        icon = QRectF(pill.left() + 18, pill.top() + 12, 44, pill.height() - 24)
        path = QPainterPath()
        for i in range(9):
            x = icon.left() + icon.width() * i / 8
            y = icon.center().y() + (icon.height() * (0.18 + 0.32 * self.level)) * (1 if i % 2 else -1)
            (path.moveTo if i == 0 else path.lineTo)(x, y)
        p.setBrush(Qt.NoBrush)
        p.setPen(pen(c, 2, 240))
        p.drawPath(path)
        p.setFont(font(11, True, 2.6))
        p.setPen(col((230, 247, 255)))
        p.drawText(QRectF(pill.left() + 70, pill.top() + 2, pill.width() - 80, pill.height() * 0.52),
                   Qt.AlignHCenter | Qt.AlignBottom, self.title)
        p.setFont(font(8.2, True))
        p.setPen(col((190, 225, 250)))
        p.drawText(QRectF(pill.left() + 70, pill.top() + pill.height() * 0.56, pill.width() - 80, pill.height() * 0.4),
                   Qt.AlignHCenter | Qt.AlignTop, self.sub)


class MicButton(QPushButton):
    """Round glowing microphone button for the sidebar voice box."""

    def __init__(self):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self.setFixedSize(86, 86)
        self.t, self.level, self.on, self.color = 0.0, 0.0, False, list(STATE_COLORS["idle"])

    def tick(self, t, level, on, color):
        self.t, self.level, self.on, self.color = t, level, on, color
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = [int(x) for x in self.color]
        ctr = QPointF(self.width() / 2, self.height() / 2)
        for i, rad in enumerate((40, 34, 28)):
            k = 1 + 0.07 * self.level * (3 - i) + (0.03 * math.sin(self.t * 3 + i) if self.on else 0)
            p.setPen(pen(c, 1.4, 160 - i * 40))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(ctr, rad * k, rad * k)
        rg = QRadialGradient(ctr, 24)
        rg.setColorAt(0, QColor(c[0], c[1], c[2], 150 if self.on else 90))
        rg.setColorAt(1, QColor(c[0], c[1], c[2], 25))
        p.setBrush(rg)
        p.setPen(pen(c, 1.6, 220))
        p.drawEllipse(ctr, 24, 24)
        draw_icon(p, "mic", QRectF(ctr.x() - 13, ctr.y() - 13, 26, 26), (225, 247, 255), 2.0)


class StatusRow(QWidget):
    """Icon + name + coloured status line (AI Core overview, model tiles)."""

    def __init__(self, icon, name, color="cyan"):
        super().__init__()
        self.icon, self.name, self.color, self.status, self.ok = icon, name, color, "", True
        self.setMinimumHeight(34)

    def set(self, status, ok=True):
        if (status, ok) != (self.status, self.ok):
            self.status, self.ok = status, ok
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        base = C[self.color] if isinstance(self.color, str) else self.color
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setBrush(col((10, 36, 70), 140))
        p.setPen(pen((40, 140, 230), 1, 70))
        p.drawRoundedRect(r, 7, 7)
        box = QRectF(r.left() + 6, r.top() + 5, r.height() - 10, r.height() - 10)
        p.setBrush(col(base, 36))
        p.setPen(pen(base, 1, 110))
        p.drawRoundedRect(box, 6, 6)
        draw_icon(p, self.icon, box, base, 1.4)
        p.setFont(font(8.8, True))
        p.setPen(col("text"))
        p.drawText(QRectF(box.right() + 8, r.top() + 2, r.width() - 50, r.height() / 2), Qt.AlignLeft | Qt.AlignBottom, self.name)
        p.setFont(font(7.8))
        p.setPen(col((60, 255, 170) if self.ok else (255, 191, 64)))
        fm = QFontMetrics(p.font())
        p.drawText(QRectF(box.right() + 8, r.center().y() + 1, r.width() - 50, r.height() / 2 - 2), Qt.AlignLeft | Qt.AlignTop,
                   fm.elidedText(self.status, Qt.ElideRight, int(r.width() - box.right() - 14)))


class CmdButton(QPushButton):
    def __init__(self, icon, text):
        super().__init__()
        self.icon_name, self.text_ = icon, text
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self.setMinimumHeight(30)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        hot = self.underMouse()
        p.setBrush(col((14, 52, 100) if hot else (10, 36, 70), 190))
        p.setPen(pen("cyan" if hot else (40, 140, 230), 1, 170 if hot else 80))
        p.drawRoundedRect(r, 7, 7)
        box = QRectF(r.left() + 8, r.top() + 5, r.height() - 10, r.height() - 10)
        draw_icon(p, self.icon_name, box, "cyan", 1.4)
        p.setFont(font(9.2))
        p.setPen(col("text"))
        p.drawText(QRectF(box.right() + 10, r.top(), r.width() - 60, r.height()), Qt.AlignLeft | Qt.AlignVCenter, self.text_)
        p.setPen(pen("cyan", 1.5, 200))
        cx, cy = r.right() - 14, r.center().y()
        p.drawLine(QPointF(cx - 3, cy - 4), QPointF(cx + 1, cy))
        p.drawLine(QPointF(cx + 1, cy), QPointF(cx - 3, cy + 4))


class IconButton(QPushButton):
    def __init__(self, icon, tip="", badge=False):
        super().__init__()
        self.icon_name, self.badge = icon, badge
        self.setToolTip(tip)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self.setFixedSize(38, 38)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        p.setBrush(col((14, 52, 100) if self.underMouse() else (10, 36, 70), 170))
        p.setPen(pen((40, 150, 240), 1, 110))
        p.drawRoundedRect(r, 9, 9)
        draw_icon(p, self.icon_name, r.adjusted(7, 7, -7, -7), (170, 215, 250), 1.5)
        if self.badge:
            p.setBrush(col("red"))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(r.right() - 5, r.top() + 5), 4, 4)


class Chip(QWidget):
    """Bottom-bar info chip: icon + small label + value."""

    def __init__(self, icon, label):
        super().__init__()
        self.icon, self.label, self.value = icon, label, ""
        self.setMinimumSize(140, 44)

    def set(self, value):
        if value != self.value:
            self.value = value
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setBrush(col((10, 34, 66), 170))
        p.setPen(pen((40, 150, 240), 1, 90))
        p.drawRoundedRect(r, 8, 8)
        draw_icon(p, self.icon, QRectF(r.left() + 10, r.top() + 10, 22, r.height() - 20), "cyan", 1.4)
        p.setFont(font(7.4))
        p.setPen(col((125, 160, 205)))
        p.drawText(QRectF(r.left() + 40, r.top() + 5, r.width() - 46, 14), Qt.AlignLeft | Qt.AlignVCenter, self.label)
        p.setFont(font(8.6, True))
        p.setPen(col("text"))
        fm = QFontMetrics(p.font())
        p.drawText(QRectF(r.left() + 40, r.top() + 20, r.width() - 46, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(self.value, Qt.ElideRight, int(r.width() - 48)))


class StatusPill(QWidget):
    def __init__(self):
        super().__init__()
        self.ok, self.text = True, "OPTIMAL"
        self.setFixedSize(220, 36)

    def set(self, ok, text):
        if (ok, text) != (self.ok, self.text):
            self.ok, self.text = ok, text
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setBrush(col((8, 30, 60), 200))
        p.setPen(pen("cyan", 1, 140))
        p.drawRoundedRect(r, 9, 9)
        p.setFont(font(7.8, True, 1.4))
        p.setPen(col((200, 230, 255)))
        p.drawText(QRectF(14, 0, 110, r.height()), Qt.AlignLeft | Qt.AlignVCenter, "SYSTEM STATUS")
        colr = C["green"] if self.ok else C["amber"]
        p.setBrush(col(colr))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(132, r.center().y()), 3.5, 3.5)
        p.setFont(font(8.2, True, 1.2))
        p.setPen(col(colr))
        p.drawText(QRectF(142, 0, 76, r.height()), Qt.AlignLeft | Qt.AlignVCenter, self.text)


class Brand(QWidget):
    def __init__(self):
        super().__init__()
        self.t, self.color = 0.0, list(STATE_COLORS["idle"])
        self.setFixedHeight(64)

    def tick(self, t, color):
        self.t, self.color = t, color
        self.update()

    def paintEvent(self, e):
        from .wave import draw_logo
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setBrush(col((8, 30, 60), 190))
        p.setPen(pen("cyan", 1, 120))
        p.drawRoundedRect(r, 10, 10)
        draw_logo(p, 34, r.center().y(), 15, self.color, spin=self.t * 0.5)
        p.setFont(font(15, True, 4))
        p.setPen(col((235, 246, 255)))
        p.drawText(QRectF(60, 8, r.width() - 64, 28), Qt.AlignLeft | Qt.AlignVCenter, "TRILION")
        p.setFont(font(7.4, False, 2.4))
        p.setPen(col((120, 190, 235)))
        p.drawText(QRectF(61, 34, r.width() - 64, 18), Qt.AlignLeft | Qt.AlignVCenter, "COMMAND CENTER")


class StopButton(IconButton):
    def __init__(self):
        super().__init__("play", "Stop everything (Ctrl+Alt+S)")

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        p.setBrush(col((120, 24, 40), 215 if self.underMouse() else 170))
        p.setPen(pen("red", 1, 190))
        p.drawRoundedRect(r, 9, 9)
        p.setBrush(col((255, 190, 196)))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(r.center().x() - 6, r.center().y() - 6, 12, 12), 2, 2)
