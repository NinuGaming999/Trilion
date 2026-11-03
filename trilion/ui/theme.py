"""Colours, fonts and tiny vector icons for the Trilion command-center look."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainterPath, QPen

C = dict(bg0=(3, 9, 22), bg1=(6, 26, 52), cyan=(25, 211, 255), blue=(48, 140, 255), text=(222, 238, 255),
         dim=(122, 156, 200), green=(52, 255, 170), amber=(255, 191, 64), red=(255, 95, 110),
         violet=(155, 107, 255), pink=(255, 95, 162))


def col(c, a=255):
    rgb = C[c] if isinstance(c, str) else c
    return QColor(rgb[0], rgb[1], rgb[2], a)


def font(size=9.0, bold=False, spacing=0.0):
    f = QFont("Segoe UI")
    f.setPointSizeF(size)
    f.setWeight(QFont.DemiBold if bold else QFont.Normal)
    if spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    return f


def pen(c, w=1.0, a=255):
    p = QPen(col(c, a), w)
    p.setCapStyle(Qt.RoundCap)
    p.setJoinStyle(Qt.RoundJoin)
    return p


def draw_icon(p, name, rect, color="cyan", width=1.5, alpha=255):
    """Draw a simple line icon inside rect."""
    r = QRectF(rect)
    cx, cy, s = r.center().x(), r.center().y(), min(r.width(), r.height()) / 2 * 0.82
    p.save()
    p.setPen(pen(color, width, alpha))
    p.setBrush(Qt.NoBrush)
    P = QPointF
    if name == "grid":
        for dx in (-1, 1):
            for dy in (-1, 1):
                p.drawRoundedRect(QRectF(cx + dx * s * .55 - s * .38, cy + dy * s * .55 - s * .38, s * .76, s * .76), 2, 2)
    elif name == "core":
        p.drawEllipse(P(cx, cy), s * .75, s * .75)
        p.drawEllipse(P(cx, cy), s * .3, s * .3)
        for a in (90, 210, 330):
            x, y = math.cos(math.radians(a)), -math.sin(math.radians(a))
            p.drawLine(P(cx + x * s * .75, cy + y * s * .75), P(cx + x * s * 1.0, cy + y * s * 1.0))
    elif name == "chat":
        p.drawRoundedRect(QRectF(cx - s, cy - s * .8, s * 2, s * 1.35), 4, 4)
        path = QPainterPath()
        path.moveTo(cx - s * .4, cy + s * .55)
        path.lineTo(cx - s * .6, cy + s)
        path.lineTo(cx, cy + s * .55)
        p.drawPath(path)
    elif name == "skills":
        path = QPainterPath()
        path.moveTo(cx + s * .2, cy - s)
        path.lineTo(cx - s * .6, cy + s * .15)
        path.lineTo(cx - s * .05, cy + s * .15)
        path.lineTo(cx - s * .2, cy + s)
        path.lineTo(cx + s * .6, cy - s * .2)
        path.lineTo(cx + s * .05, cy - s * .2)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "memory":
        p.drawEllipse(QRectF(cx - s * .8, cy - s, s * 1.6, s * .6))
        p.drawLine(P(cx - s * .8, cy - s * .7), P(cx - s * .8, cy + s * .7))
        p.drawLine(P(cx + s * .8, cy - s * .7), P(cx + s * .8, cy + s * .7))
        p.drawArc(QRectF(cx - s * .8, cy + s * .4, s * 1.6, s * .6), 180 * 16, 180 * 16)
        p.drawArc(QRectF(cx - s * .8, cy - s * .15, s * 1.6, s * .6), 180 * 16, 180 * 16)
    elif name == "game":
        p.drawRoundedRect(QRectF(cx - s, cy - s * .6, s * 2, s * 1.2), s * .55, s * .55)
        p.drawLine(P(cx - s * .55, cy), P(cx - s * .15, cy))
        p.drawLine(P(cx - s * .35, cy - s * .2), P(cx - s * .35, cy + s * .2))
        p.drawPoint(P(cx + s * .35, cy - s * .12))
        p.drawPoint(P(cx + s * .6, cy + s * .12))
    elif name == "settings":
        p.drawEllipse(P(cx, cy), s * .38, s * .38)
        for i in range(8):
            a = math.radians(i * 45)
            p.drawLine(P(cx + math.cos(a) * s * .62, cy + math.sin(a) * s * .62),
                       P(cx + math.cos(a) * s * .95, cy + math.sin(a) * s * .95))
        p.drawEllipse(P(cx, cy), s * .62, s * .62)
    elif name == "logs":
        p.drawRoundedRect(QRectF(cx - s * .7, cy - s, s * 1.4, s * 2), 3, 3)
        for k in (-.5, 0, .5):
            p.drawLine(P(cx - s * .4, cy + k * s), P(cx + s * .4, cy + k * s))
    elif name == "mic":
        p.drawRoundedRect(QRectF(cx - s * .3, cy - s, s * .6, s * 1.2), s * .3, s * .3)
        p.drawArc(QRectF(cx - s * .65, cy - s * .55, s * 1.3, s * 1.2), 200 * 16, 140 * 16)
        p.drawLine(P(cx, cy + s * .65), P(cx, cy + s))
    elif name == "eye":
        p.drawEllipse(QRectF(cx - s, cy - s * .55, s * 2, s * 1.1))
        p.drawEllipse(P(cx, cy), s * .28, s * .28)
    elif name == "ear":   # audio bars
        for i, h in enumerate((.35, .8, 1.0, .6, .3)):
            x = cx + (i - 2) * s * .42
            p.drawLine(P(x, cy - s * h), P(x, cy + s * h))
    elif name == "brain":
        pts = [P(cx - s * .6, cy - s * .3), P(cx + s * .1, cy - s * .7), P(cx + s * .7, cy - s * .1),
               P(cx + s * .2, cy + s * .6), P(cx - s * .5, cy + s * .4)]
        for a, b in ((0, 1), (1, 2), (2, 3), (3, 4), (4, 0), (0, 2), (1, 3)):
            p.drawLine(pts[a], pts[b])
        for q in pts:
            p.drawEllipse(q, s * .13, s * .13)
    elif name == "hand":  # pointer
        path = QPainterPath()
        path.moveTo(cx - s * .55, cy - s * .9)
        path.lineTo(cx - s * .55, cy + s * .55)
        path.lineTo(cx - s * .2, cy + s * .2)
        path.lineTo(cx + s * .15, cy + s * .9)
        path.lineTo(cx + s * .4, cy + s * .8)
        path.lineTo(cx + s * .05, cy + s * .1)
        path.lineTo(cx + s * .55, cy + s * .1)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "speaker":
        path = QPainterPath()
        path.moveTo(cx - s * .9, cy - s * .35)
        path.lineTo(cx - s * .4, cy - s * .35)
        path.lineTo(cx + s * .1, cy - s * .8)
        path.lineTo(cx + s * .1, cy + s * .8)
        path.lineTo(cx - s * .4, cy + s * .35)
        path.lineTo(cx - s * .9, cy + s * .35)
        path.closeSubpath()
        p.drawPath(path)
        p.drawArc(QRectF(cx - s * .1, cy - s * .5, s * .9, s), -60 * 16, 120 * 16)
    elif name == "clock":
        p.drawEllipse(P(cx, cy), s, s)
        p.drawLine(P(cx, cy), P(cx, cy - s * .6))
        p.drawLine(P(cx, cy), P(cx + s * .4, cy + s * .2))
    elif name == "check":
        path = QPainterPath()
        path.moveTo(cx - s * .7, cy)
        path.lineTo(cx - s * .15, cy + s * .55)
        path.lineTo(cx + s * .75, cy - s * .6)
        p.drawPath(path)
    elif name == "warn":
        path = QPainterPath()
        path.moveTo(cx, cy - s)
        path.lineTo(cx + s, cy + s * .8)
        path.lineTo(cx - s, cy + s * .8)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(P(cx, cy - s * .35), P(cx, cy + s * .25))
        p.drawPoint(P(cx, cy + s * .55))
    elif name == "info":
        p.drawEllipse(P(cx, cy), s, s)
        p.drawLine(P(cx, cy - s * .05), P(cx, cy + s * .5))
        p.drawPoint(P(cx, cy - s * .45))
    elif name == "play":
        path = QPainterPath()
        path.moveTo(cx - s * .5, cy - s * .8)
        path.lineTo(cx + s * .8, cy)
        path.lineTo(cx - s * .5, cy + s * .8)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "search":
        p.drawEllipse(P(cx - s * .15, cy - s * .15), s * .6, s * .6)
        p.drawLine(P(cx + s * .3, cy + s * .3), P(cx + s * .85, cy + s * .85))
    elif name == "bell":
        path = QPainterPath()
        path.moveTo(cx - s * .7, cy + s * .45)
        path.lineTo(cx + s * .7, cy + s * .45)
        path.lineTo(cx + s * .5, cy + s * .2)
        path.lineTo(cx + s * .5, cy - s * .2)
        path.cubicTo(cx + s * .5, cy - s * .9, cx - s * .5, cy - s * .9, cx - s * .5, cy - s * .2)
        path.lineTo(cx - s * .5, cy + s * .2)
        path.closeSubpath()
        p.drawPath(path)
        p.drawArc(QRectF(cx - s * .2, cy + s * .4, s * .4, s * .4), 180 * 16, 180 * 16)
    elif name == "user":
        p.drawEllipse(P(cx, cy - s * .35), s * .4, s * .4)
        p.drawArc(QRectF(cx - s * .8, cy + s * .1, s * 1.6, s * 1.4), 0, 180 * 16)
    elif name == "pulse":
        path = QPainterPath()
        path.moveTo(cx - s, cy)
        for x, y in ((-.5, 0), (-.3, -.8), (0, .8), (.25, -.2), (.4, 0), (1, 0)):
            path.lineTo(cx + x * s, cy + y * s)
        p.drawPath(path)
    elif name == "folder":
        p.drawRoundedRect(QRectF(cx - s, cy - s * .55, s * 2, s * 1.35), 3, 3)
        p.drawLine(P(cx - s, cy - s * .55), P(cx - s * .4, cy - s * .85))
    elif name == "tri":
        pts = [P(cx + s * math.sin(j * 2.0944), cy - s * math.cos(j * 2.0944)) for j in range(3)]
        path = QPainterPath()
        path.moveTo(pts[0])
        path.lineTo(pts[1])
        path.lineTo(pts[2])
        path.closeSubpath()
        p.drawPath(path)
    p.restore()
