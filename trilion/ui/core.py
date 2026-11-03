"""Voice-reactive 3D neural core, drawn with Qt so it needs no extra 3D runtime."""
import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


class OrbCore(QWidget):
    """A lightweight, perspective-projected wireframe sphere driven by live audio."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(210)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.state = "idle"
        self.mic_level = 0.0
        self.out_level = 0.0
        self.phase = 0.0
        self.pulse = 0.0
        self.spin_rate = 0.42
        self.accent = QColor("#32dff5")
        self.secondary = QColor("#447dff")
        self.glow = QColor("#123f80")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(25)

    def set_palette(self, accent, secondary, glow):
        self.accent = QColor(accent)
        self.secondary = QColor(secondary)
        self.glow = QColor(glow)
        self.update()

    def set_state(self, state):
        self.state = state if state in ("idle", "listening", "thinking", "speaking", "acting") else "idle"
        self.update()

    def set_levels(self, mic, output):
        self.mic_level = max(0.0, min(1.0, float(mic)))
        self.out_level = max(0.0, min(1.0, float(output)))

    def _tick(self):
        level = self.out_level if self.state == "speaking" else self.mic_level
        if self.state == "thinking":
            level = max(level, 0.18 + 0.08 * math.sin(self.phase * 2.1))
        elif self.state == "acting":
            level = max(level, 0.16 + 0.10 * abs(math.sin(self.phase * 3.2)))
        target = 0.34 + level * 2.35
        self.spin_rate += (target - self.spin_rate) * 0.08
        self.phase += 0.025 * self.spin_rate
        self.pulse += 0.045 + level * 0.11
        self.update()

    def _project(self, lat, lon, radius, yaw, pitch):
        x = math.cos(lat) * math.sin(lon)
        y = math.sin(lat)
        z = math.cos(lat) * math.cos(lon)
        x1 = x * math.cos(yaw) + z * math.sin(yaw)
        z1 = -x * math.sin(yaw) + z * math.cos(yaw)
        y2 = y * math.cos(pitch) - z1 * math.sin(pitch)
        z2 = y * math.sin(pitch) + z1 * math.cos(pitch)
        perspective = 2.7 / (2.7 - z2 * 0.34)
        return x1 * radius * perspective, y2 * radius * perspective, z2

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        cx, cy = w * 0.5, h * 0.49
        level = self.out_level if self.state == "speaking" else self.mic_level
        if self.state == "thinking":
            level = max(level, 0.16)
        elif self.state == "acting":
            level = max(level, 0.13)
        radius = min(w * 0.205, h * 0.385) * (1.0 + level * 0.055)

        halo = QRadialGradient(cx, cy, radius * (2.45 + level * 0.28))
        c = QColor(self.glow)
        c.setAlpha(105 + int(level * 55))
        halo.setColorAt(0.0, c)
        c2 = QColor(self.accent)
        c2.setAlpha(24 + int(level * 46))
        halo.setColorAt(0.55, c2)
        halo.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        p.drawEllipse(cx - radius * 2.5, cy - radius * 2.5, radius * 5.0, radius * 5.0)

        sphere = QRadialGradient(cx - radius * 0.34, cy - radius * 0.42, radius * 1.75)
        sphere.setColorAt(0.0, QColor(30, 75, 112, 145))
        sphere.setColorAt(0.55, QColor(8, 25, 49, 165))
        sphere.setColorAt(1.0, QColor(2, 8, 22, 215))
        p.setBrush(sphere)
        p.setPen(QPen(QColor(self.accent.red(), self.accent.green(), self.accent.blue(), 105), 1.15))
        p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

        yaw = self.phase * 0.72
        pitch = -0.30 + math.sin(self.phase * 0.23) * 0.10

        # Latitude rings.
        for lat_i in range(-5, 6):
            lat = lat_i * math.pi / 12.0
            path_front, path_back = QPainterPath(), QPainterPath()
            started_front = started_back = False
            for k in range(97):
                lon = -math.pi + (2 * math.pi * k / 96)
                x, y, z = self._project(lat, lon, radius, yaw, pitch)
                path = path_front if z >= -0.02 else path_back
                started = started_front if z >= -0.02 else started_back
                if not started:
                    path.moveTo(cx + x, cy + y)
                    if z >= -0.02:
                        started_front = True
                    else:
                        started_back = True
                else:
                    path.lineTo(cx + x, cy + y)
            back_col = QColor(self.secondary)
            back_col.setAlpha(24)
            p.setPen(QPen(back_col, 0.7))
            p.drawPath(path_back)
            front_col = QColor(self.accent)
            front_col.setAlpha(58 + int(28 * max(0.0, 1.0 - abs(lat_i) / 6)))
            p.setPen(QPen(front_col, 0.85 if lat_i else 1.1))
            p.drawPath(path_front)

        # Longitude meridians, with the far side attenuated.
        for lon_i in range(16):
            lon = 2 * math.pi * lon_i / 16
            path_front, path_back = QPainterPath(), QPainterPath()
            started_front = started_back = False
            for k in range(65):
                lat = -math.pi / 2 + math.pi * k / 64
                x, y, z = self._project(lat, lon, radius, yaw, pitch)
                path = path_front if z >= -0.02 else path_back
                started = started_front if z >= -0.02 else started_back
                if not started:
                    path.moveTo(cx + x, cy + y)
                    if z >= -0.02:
                        started_front = True
                    else:
                        started_back = True
                else:
                    path.lineTo(cx + x, cy + y)
            back_col = QColor(self.secondary)
            back_col.setAlpha(19)
            p.setPen(QPen(back_col, 0.65))
            p.drawPath(path_back)
            front_col = QColor(self.accent)
            front_col.setAlpha(52)
            p.setPen(QPen(front_col, 0.75))
            p.drawPath(path_front)

        # Nodes embedded in the mesh, travelling with the sphere.
        for i in range(34):
            lat = -1.25 + (i % 9) * 0.3125
            lon = (i * 2.399963229728653) % (2 * math.pi)
            x, y, z = self._project(lat, lon, radius, yaw, pitch)
            if z < -0.28:
                continue
            dot = 1.2 + max(0.0, z) * 1.1
            node = QColor(self.accent)
            node.setAlpha(70 + int(max(0.0, z) * 140))
            p.setPen(Qt.NoPen)
            p.setBrush(node)
            p.drawEllipse(cx + x - dot / 2, cy + y - dot / 2, dot, dot)

        # Tilted orbit tracks and live orbiting nodes.
        for index in range(2):
            tilt = 0.34 if index == 0 else -0.53
            orbit = QPainterPath()
            for k in range(121):
                a = 2 * math.pi * k / 120
                ox = math.cos(a + yaw * (0.55 if index == 0 else -0.38)) * radius * (1.64 if index == 0 else 1.84)
                oy = math.sin(a) * radius * tilt
                oy += math.sin(a + yaw) * radius * (0.20 if index == 0 else -0.16)
                if k == 0:
                    orbit.moveTo(cx + ox, cy + oy)
                else:
                    orbit.lineTo(cx + ox, cy + oy)
            oc = QColor(self.secondary if index else self.accent)
            oc.setAlpha(65 if index == 0 else 42)
            p.setPen(QPen(oc, 1.0 if index == 0 else 0.75))
            p.setBrush(Qt.NoBrush)
            p.drawPath(orbit)

            a = self.phase * (0.58 if index == 0 else -0.44) + index * 2.4
            ox = math.cos(a) * radius * (1.64 if index == 0 else 1.84)
            oy = math.sin(a) * radius * tilt + math.sin(a + yaw) * radius * (0.20 if index == 0 else -0.16)
            node_glow = QRadialGradient(cx + ox, cy + oy, 13 + level * 8)
            nc = QColor(self.accent if index == 0 else self.secondary)
            nc.setAlpha(175)
            node_glow.setColorAt(0, nc)
            nc.setAlpha(0)
            node_glow.setColorAt(1, nc)
            p.setBrush(node_glow)
            p.setPen(Qt.NoPen)
            p.drawEllipse(cx + ox - 13, cy + oy - 13, 26, 26)

        core_glow = QRadialGradient(cx - radius * 0.12, cy - radius * 0.16, radius * 0.72)
        center = QColor(self.accent)
        center.setAlpha(36 + int(level * 55))
        core_glow.setColorAt(0, center)
        center.setAlpha(0)
        core_glow.setColorAt(1, center)
        p.setBrush(core_glow)
        p.drawEllipse(cx - radius * 0.72, cy - radius * 0.72, radius * 1.44, radius * 1.44)
        p.end()
