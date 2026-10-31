"""Instant-on loading window: appears before any heavy import happens."""
import math
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QWidget

from .wave import TriWave, draw_logo

STYLE = """QPushButton{background:rgba(255,255,255,0.08);color:#dfe6ff;border:1px solid rgba(255,255,255,0.18);
border-radius:8px;padding:7px 18px;font-size:13px}QPushButton:hover{background:rgba(255,255,255,0.16)}"""


class LoadingWindow(QWidget):
    def __init__(self, on_retry=None):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedSize(680, 400)
        self.setWindowTitle("Trilion")
        self.target = 0.0
        self.shown = 0.0
        self.status = "Starting…"
        self.error = None
        self.wave = TriWave()
        self.wave.set_state("loading")
        self.t0 = time.monotonic()
        self.last = time.monotonic()
        self._drag = None
        self.on_retry = on_retry
        scr = QApplication.primaryScreen().availableGeometry()
        self.move(scr.center().x() - 340, scr.center().y() - 200)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.btns = QWidget(self)
        self.btns.setLayout(row)
        self.retry = QPushButton("Retry")
        self.quit = QPushButton("Quit")
        self.copy = QPushButton("Copy log")
        self.folder = QPushButton("Open logs")
        self.copy.clicked.connect(self._copy)
        self.folder.clicked.connect(self._folder)
        for b in (self.retry, self.copy, self.folder, self.quit):
            b.setStyleSheet(STYLE)
            b.setCursor(Qt.PointingHandCursor)
            row.addWidget(b)
        self.retry.clicked.connect(lambda: self.on_retry and self.on_retry())
        self.quit.clicked.connect(QApplication.quit)
        self.btns.setGeometry(110, 335, 460, 38)
        self.btns.hide()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def _copy(self):
        from ..paths import collect_logs
        QApplication.clipboard().setText(collect_logs())
        self.copy.setText("Copied!")

    def _folder(self):
        from ..paths import open_logs_folder
        open_logs_folder()

    def set_progress(self, frac, text):
        self.error = None
        self.btns.hide()
        self.target = max(self.target, min(1.0, frac)) if frac >= self.target - 0.2 else frac
        self.status = text

    def set_error(self, text):
        self.error = text
        self.copy.setText("Copy log")
        self.btns.show()

    def _tick(self):
        now = time.monotonic()
        dt = now - self.last
        self.last = now
        self.shown += (self.target - self.shown) * (1 - math.exp(-6 * dt))
        self.wave.set_level(0.30 + 0.45 * abs(math.sin((now - self.t0) * 2.3)))
        self.wave.tick(dt)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        w, h = self.width(), self.height()
        self.wave.paint_background(p, w, h)
        self.wave.paint(p, w, h, region=140)
        draw_logo(p, w / 2, 100, 46, self.wave.color, spin=(time.monotonic() - self.t0) * 0.6,
                  level=self.wave.level)
        f = QFont("Segoe UI", 22)
        f.setWeight(QFont.DemiBold)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 8)
        p.setFont(f)
        p.setPen(QColor(235, 240, 255))
        p.drawText(QRectF(0, 160, w, 40), Qt.AlignCenter, "TRILION")
        # progress bar
        bx, by, bw, bh = 90, 228, w - 180, 8
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 25))
        p.drawRoundedRect(QRectF(bx, by, bw, bh), 4, 4)
        fw = max(bh, bw * self.shown)
        g = QLinearGradient(bx, 0, bx + bw, 0)
        g.setColorAt(0, QColor(58, 214, 255))
        g.setColorAt(1, QColor(155, 107, 255))
        p.setBrush(g)
        p.drawRoundedRect(QRectF(bx, by, fw, bh), 4, 4)
        p.setBrush(QColor(255, 255, 255, 230))  # glowing tip
        p.drawEllipse(QRectF(bx + fw - 6, by - 2, 12, 12))
        f2 = QFont("Segoe UI", 10)
        p.setFont(f2)
        p.setPen(QColor(190, 200, 230))
        p.drawText(QRectF(bx, by + 18, bw - 60, 24), Qt.AlignLeft | Qt.AlignVCenter, self.status)
        p.setPen(QColor(235, 240, 255))
        p.drawText(QRectF(bx + bw - 60, by + 18, 60, 24), Qt.AlignRight | Qt.AlignVCenter,
                   f"{int(self.shown * 100)}%")
        if self.error:
            p.setPen(QColor(255, 130, 130))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(QRectF(60, 285, w - 120, 50), Qt.AlignHCenter | Qt.TextWordWrap, self.error[:260])
        else:
            p.setPen(QColor(120, 135, 175))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(QRectF(0, 292, w, 20), Qt.AlignCenter, "First launch downloads the AI models once (~6 GB). Next starts are fast.")
        p.setPen(QPen(QColor(255, 255, 255, 35), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(0, 0, w - 1, h - 1)

    def mousePressEvent(self, e):
        self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None
