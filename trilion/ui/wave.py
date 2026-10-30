"""The signature triangular wavy base + logo. Pure painting, no heavy imports."""
import math

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient

STATE_COLORS = {
    "loading": (58, 214, 255),
    "idle": (58, 214, 255),
    "listening": (77, 255, 176),
    "thinking": (155, 107, 255),
    "speaking": (255, 95, 162),
    "acting": (255, 191, 64),
}
# (teeth across the window, height scale, scroll speed, phase)
LAYERS = [(11, 0.60, 0.55, 0.0), (17, 0.85, -0.80, 1.7), (25, 1.00, 1.10, 3.1), (39, 0.50, -1.50, 4.4)]


def tri(t):
    return 2 * abs(2 * (t - math.floor(t + 0.5))) - 1


class TriWave:
    def __init__(self):
        self.t = 0.0
        self.level = 0.0
        self.target = 0.0
        self.state = "idle"
        self.color = list(STATE_COLORS["idle"])

    def set_state(self, s):
        self.state = s if s in STATE_COLORS else "idle"

    def set_level(self, v):
        self.target = max(0.0, min(1.0, v))

    def tick(self, dt):
        self.t += dt
        tgt = self.target
        if self.state == "thinking":
            tgt = 0.16 + 0.10 * math.sin(self.t * 3.2)
        elif self.state == "acting":
            tgt = 0.20 + 0.12 * abs(math.sin(self.t * 5.0))
        elif self.state in ("idle", "loading"):
            tgt = max(tgt, 0.05 + 0.03 * math.sin(self.t * 1.3))
        rate = 22.0 if tgt > self.level else 6.0  # fast attack, slow decay
        self.level += (tgt - self.level) * (1 - math.exp(-rate * dt))
        goal = STATE_COLORS[self.state]
        k = 1 - math.exp(-6.0 * dt)
        for i in range(3):
            self.color[i] += (goal[i] - self.color[i]) * k

    def paint_background(self, p, w, h):
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor(6, 9, 20))
        g.setColorAt(1, QColor(12, 16, 36))
        p.fillRect(0, 0, w, h, g)
        c = QColor(*[int(v) for v in self.color])
        rg = QRadialGradient(w / 2, h, h * 0.9)
        c.setAlpha(int(30 + 70 * self.level))
        rg.setColorAt(0, c)
        c.setAlpha(0)
        rg.setColorAt(1, c)
        p.fillRect(0, 0, w, h, rg)

    def paint(self, p, w, h, region=None):
        region = region or min(h * 0.42, 230)
        base = h - region * 0.30
        amp_max = region * 0.50
        col = [int(v) for v in self.color]
        p.setRenderHint(QPainter.Antialiasing, True)
        for li, (teeth, hs, speed, ph) in enumerate(LAYERS):
            width = w / teeth
            off = (self.t * speed * 0.35 + ph) % 1.0
            path = QPainterPath()
            path.moveTo(-width, h)
            m = -2
            while True:
                x = (m * 0.5 - off) * width
                if x > w + width:
                    break
                xn = min(max(x / w, 0.0), 1.0)
                env = 0.40 + 0.60 * math.sin(math.pi * xn) ** 1.4
                jit = 1.0 + 0.40 * self.level * math.sin(m * 1.9 + self.t * (4 + li) + ph)
                peak = (m % 2 == 0)  # alternate valleys / peaks
                a = 5 + amp_max * self.level * hs * env * jit
                y = base - (a if peak else a * 0.05) - li * 3
                path.lineTo(x, y)
                m += 1
            path.lineTo(w + width, h)
            path.closeSubpath()
            top = base - amp_max * self.level * hs
            g = QLinearGradient(0, top, 0, h)
            alpha = [70, 90, 120, 60][li]
            g.setColorAt(0, QColor(col[0], col[1], col[2], alpha))
            g.setColorAt(1, QColor(col[0], col[1], col[2], 6))
            p.fillPath(path, g)
            pen = QPen(QColor(col[0], col[1], col[2], 90 + li * 35), 1.6 if li != 2 else 2.2)
            p.setPen(pen)
            p.drawPath(path)


def draw_logo(p, cx, cy, size, color, spin=0.0, level=0.0):
    """Nested triangles - the Trilion mark."""
    p.setRenderHint(QPainter.Antialiasing, True)
    c = QColor(*[int(v) for v in color])
    for i, (k, a) in enumerate([(1.0, 255), (0.62, 170), (0.30, 110)]):
        r = size * k * (1 + 0.06 * level * (i + 1))
        ang = spin * (1 if i % 2 == 0 else -1) + i * 0.0
        pts = [QPointF(cx + r * math.sin(ang + j * 2.0944), cy - r * math.cos(ang + j * 2.0944)) for j in range(3)]
        path = QPainterPath()
        path.moveTo(pts[0])
        path.lineTo(pts[1])
        path.lineTo(pts[2])
        path.closeSubpath()
        cc = QColor(c)
        cc.setAlpha(a)
        p.setPen(QPen(cc, 2.4 - i * 0.5))
        fill = QColor(c)
        fill.setAlpha(28 if i == 0 else 0)
        p.setBrush(fill)
        p.drawPath(path)
