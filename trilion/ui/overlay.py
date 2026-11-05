"""Always-on-top Trilion overlay: the AI core plus a few lines of terminal data.

It is a normal (capturable) window, so it appears in screen recordings that capture the desktop. By default it is
click-through and never takes focus; unlock it (Ctrl+Alt+U) to drag it somewhere else."""
from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QFont, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

from ..core.hud import hud_lines
from . import winutil
from .theme import C, col, font, pen
from .widgets import OrbWidget

SIZES = {"compact": (236, 236), "standard": (340, 372), "full": (420, 500)}
ORB_H = {"compact": 168, "standard": 196, "full": 256}
CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")
KIND_COLOR = {"head": "cyan", "text": "text", "dim": "dim", "ok": "green", "fail": "red", "warn": "red",
              "run": "amber", "you": (127, 232, 255), "reply": (255, 127, 184)}
MARGIN = 24


class Overlay(QWidget):
    def __init__(self, cfg, version=""):
        flags = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
                 | Qt.NoDropShadowWindowHint)
        super().__init__(None, flags)
        self.cfg = cfg
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowTitle("Trilion Overlay")
        self.snap, self.lines = {}, []
        self.locked = bool(cfg.get("overlay_locked", True))
        self._drag = None
        self.orb = OrbWidget(version, compact=True)
        self.orb.setParent(self)
        self.orb.setMinimumSize(0, 0)
        self.orb.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setWindowOpacity(float(cfg.get("overlay_opacity", 0.88)))
        self.apply_layout()
        self.anim = QTimer(self)
        self.anim.timeout.connect(self._animate)
        self.anim.start(33)
        self.pin = QTimer(self)                   # Windows can push the taskbar above us: keep re-asserting
        self.pin.timeout.connect(self._pin)
        self.pin.start(500)
        self._t = 0.0

    # ---- layout ----
    @property
    def size_name(self):
        n = self.cfg.get("overlay_size", "standard")
        return n if n in SIZES else "standard"

    def apply_layout(self):
        w, h = SIZES[self.size_name]
        self.resize(w, h)
        self.orb.setGeometry(0, 6, w, ORB_H[self.size_name])
        self.place()
        self.lines = hud_lines(self.snap, self.size_name) if self.snap else []
        self.update()

    def place(self):
        x, y = self.cfg.get("overlay_x"), self.cfg.get("overlay_y")
        corner = self.cfg.get("overlay_corner", "top-right")
        if corner == "custom" and x is not None and y is not None:
            self.move(int(x), int(y))
            return
        scr = (QGuiApplication.primaryScreen() or QGuiApplication.screens()[0]).availableGeometry()
        left = scr.left() + MARGIN if "left" in corner else scr.right() - self.width() - MARGIN
        top = scr.top() + MARGIN if corner.startswith("top") else scr.bottom() - self.height() - MARGIN
        self.move(left, top)

    def set_size(self, name):
        self.cfg["overlay_size"] = name if name in SIZES else "standard"
        self._save()
        self.apply_layout()

    def cycle_size(self):
        names = list(SIZES)
        self.set_size(names[(names.index(self.size_name) + 1) % len(names)])
        return self.size_name

    def set_corner(self, corner):
        self.cfg["overlay_corner"] = corner
        self._save()
        self.place()

    def set_opacity(self, v):
        self.cfg["overlay_opacity"] = max(0.2, min(1.0, float(v)))
        self._save()
        self.setWindowOpacity(self.cfg["overlay_opacity"])

    def _save(self):
        try:
            self.cfg.save()
        except Exception:
            pass

    # ---- click-through / drag ----
    def set_locked(self, locked):
        self.locked = bool(locked)
        self.cfg["overlay_locked"] = self.locked
        self._save()
        self._apply_lock()
        self.update()

    def _apply_lock(self):
        if not winutil.set_click_through(int(self.winId()), self.locked):
            self.setAttribute(Qt.WA_TransparentForMouseEvents, self.locked)

    def mousePressEvent(self, e):
        if not self.locked and e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self.cfg["overlay_corner"] = "custom"
            self.cfg["overlay_x"], self.cfg["overlay_y"] = self.x(), self.y()
            self._save()

    # ---- showing ----
    def showEvent(self, e):
        super().showEvent(e)
        self._apply_lock()
        self._pin()

    def _pin(self):
        if self.isVisible():
            winutil.set_topmost(int(self.winId()))

    def rect_real(self):
        """Where the overlay is on screen (real pixels) - used to black it out in the AI's screenshots."""
        if not self.isVisible():
            return None
        r = winutil.window_rect(int(self.winId()))
        if r:
            return r
        dpr = self.devicePixelRatioF()
        g = self.frameGeometry()
        return int(g.left() * dpr), int(g.top() * dpr), int((g.right() + 1) * dpr), int((g.bottom() + 1) * dpr)

    # ---- data + painting ----
    def set_snapshot(self, snap):
        self.snap = snap
        self.lines = hud_lines(snap, self.size_name)
        self.update()

    def _animate(self):
        if not self.isVisible():
            return
        self._t += 0.033
        s = self.snap
        if s:
            self.orb.tick(self._t, s.get("level", 0.0), s.get("state", "idle"), s.get("color", [25, 211, 255]))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setBrush(col((4, 14, 32), 168))
        p.setPen(pen("cyan" if self.locked else "amber", 1.2, 150))
        p.drawRoundedRect(r, 14, 14)
        f = QFont("Consolas")
        f.setStyleHint(QFont.Monospace)
        f.setPointSizeF(9.0)
        p.setFont(f)
        y = 6 + ORB_H[self.size_name] + 2
        for text, kind in self.lines:
            p.setPen(col(KIND_COLOR.get(kind, "text")))
            if kind == "head":
                f.setBold(True)
                p.setFont(f)
            p.drawText(QRectF(12, y, r.width() - 20, 17), Qt.AlignLeft | Qt.AlignVCenter, text)
            if kind == "head":
                f.setBold(False)
                p.setFont(f)
            y += 17
        if not self.locked:
            p.setPen(col("amber"))
            p.drawText(QRectF(12, r.bottom() - 18, r.width() - 20, 16), Qt.AlignRight | Qt.AlignVCenter,
                       "drag me  -  Ctrl+Alt+U to lock")
