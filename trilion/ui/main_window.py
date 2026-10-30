"""Main interface: transcript + live caption over the reactive triangular wave."""
import html
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QTextBrowser, QVBoxLayout, QWidget)

from .wave import TriWave, draw_logo

QSS = """
QTextBrowser{background:transparent;border:none;color:#cfd8f5;font-size:14px;selection-background-color:#3a4a8a}
QLineEdit{background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.16);border-radius:10px;
 color:#eef2ff;padding:9px 14px;font-size:14px}
QLineEdit:focus{border:1px solid rgba(90,200,255,0.8)}
QPushButton{background:rgba(255,255,255,0.07);color:#d6def8;border:1px solid rgba(255,255,255,0.16);
 border-radius:10px;padding:8px 14px;font-size:13px}
QPushButton:hover{background:rgba(255,255,255,0.15)}
QPushButton:checked{background:rgba(58,214,255,0.22);border:1px solid rgba(58,214,255,0.7);color:white}
QLabel#caption{color:#ffffff;font-size:20px;font-weight:500}
QLabel#state{color:#8fa0d0;font-size:12px;letter-spacing:3px}
"""
STATE_TEXT = {"idle": "READY", "listening": "LISTENING", "thinking": "THINKING",
              "speaking": "SPEAKING", "acting": "WORKING ON IT"}


class MainWindow(QWidget):
    def __init__(self, rt, assistant, bridge):
        super().__init__()
        self.rt, self.assistant, self.bridge = rt, assistant, bridge
        self.setWindowTitle("Trilion")
        self.resize(940, 680)
        self.setMinimumSize(720, 520)
        self.setStyleSheet(QSS)
        self.wave = TriWave()
        self.state = "idle"
        self.mic_lvl = self.out_lvl = 0.0
        self.last = time.monotonic()
        self.t0 = self.last

        lay = QVBoxLayout(self)
        lay.setContentsMargins(34, 22, 34, 185)
        lay.setSpacing(10)
        top = QHBoxLayout()
        top.addSpacing(170)
        self.state_lbl = QLabel("READY", objectName="state")
        top.addWidget(self.state_lbl)
        top.addStretch()
        self.b_mic = self._btn("Mic", True, "Listen for your voice")
        self.b_watch = self._btn("Watch screen", rt.cfg["watch_screen"], "Attach a screenshot to each request")
        self.b_conf = self._btn("Confirm risky", rt.cfg["confirm_risky"], "Ask before shell commands / writing files")
        self.b_wake = self._btn("Wake word", rt.cfg["wake_word"], 'Only react after you say "Trilion"')
        self.b_mic.setChecked(True)
        self.b_stop = QPushButton("Stop")
        self.b_stop.clicked.connect(self.assistant.stop)
        for b in (self.b_mic, self.b_watch, self.b_wake, self.b_conf, self.b_stop):
            top.addWidget(b)
        lay.addLayout(top)

        self.log = QTextBrowser()
        self.log.setOpenExternalLinks(False)
        lay.addWidget(self.log, 1)
        self.caption = QLabel("", objectName="caption")
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.setWordWrap(True)
        self.caption.setMinimumHeight(54)
        lay.addWidget(self.caption)
        row = QHBoxLayout()
        self.inp = QLineEdit()
        self.inp.setPlaceholderText('Say "Trilion, …" or type here and press Enter')
        self.inp.returnPressed.connect(self._send)
        row.addWidget(self.inp)
        lay.addLayout(row)

        self.b_mic.toggled.connect(lambda v: setattr(self.assistant, "mic_enabled", v))
        self.b_watch.toggled.connect(lambda v: self._cfg("watch_screen", v))
        self.b_conf.toggled.connect(lambda v: self._cfg("confirm_risky", v))
        self.b_wake.toggled.connect(lambda v: self._cfg("wake_word", v))
        bridge.state.connect(self._on_state)
        bridge.mic_level.connect(lambda v: setattr(self, "mic_lvl", v))
        bridge.out_level.connect(lambda v: setattr(self, "out_lvl", v))
        bridge.caption.connect(self.caption.setText)
        bridge.message.connect(self._on_message)
        bridge.confirm_req.connect(self._on_confirm)
        self._add("assistant", 'Online. Say "Trilion" and ask me anything, or type below.')

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def _btn(self, text, on, tip):
        b = QPushButton(text)
        b.setCheckable(True)
        b.setChecked(bool(on))
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        return b

    def _cfg(self, k, v):
        self.rt.cfg[k] = v
        self.rt.cfg.save()

    def _send(self):
        t = self.inp.text().strip()
        if t:
            self.inp.clear()
            self.assistant.submit_text(t)

    def _on_state(self, s):
        self.state = s
        self.wave.set_state(s)
        self.state_lbl.setText(STATE_TEXT.get(s, s.upper()))

    def _on_message(self, role, text):
        self._add(role, text)

    def _add(self, role, text):
        t = html.escape(text).replace("\n", "<br>")
        if role == "user":
            h = f'<p style="margin:8px 0"><span style="color:#7fe8ff">You</span>&nbsp; {t}</p>'
        elif role == "assistant":
            h = f'<p style="margin:8px 0"><span style="color:#ff7fb8">Trilion</span>&nbsp; {t}</p>'
        elif role == "action":
            h = f'<p style="margin:2px 0;color:#7c89b8">&#9656; {t}</p>'
        else:
            h = f'<p style="margin:6px 0;color:#ff8a8a">{t}</p>'
        self.log.append(h)

    def _on_confirm(self, question, handle):
        ev, box = handle
        r = QMessageBox.question(self, "Trilion needs permission", question,
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        box[0] = r == QMessageBox.Yes
        ev.set()

    def _tick(self):
        now = time.monotonic()
        dt = min(0.1, now - self.last)
        self.last = now
        # Voice drives the wave: your mic while idle/listening, her voice while speaking.
        if self.state == "speaking":
            self.wave.set_level(self.out_lvl)
        elif self.mic_lvl > 0.08 and self.state in ("idle", "listening"):
            if self.state != "listening":
                self.wave.set_state("listening")
            self.wave.set_level(self.mic_lvl)
        else:
            if self.state == "idle" and self.wave.state == "listening":
                self.wave.set_state("idle")
            self.wave.set_level(0.0)
        self.wave.tick(dt)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        w, h = self.width(), self.height()
        self.wave.paint_background(p, w, h)
        self.wave.paint(p, w, h)
        draw_logo(p, 56, 40, 17, self.wave.color, spin=(time.monotonic() - self.t0) * 0.5, level=self.wave.level)
        f = QFont("Segoe UI", 12)
        f.setWeight(QFont.DemiBold)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 5)
        p.setFont(f)
        p.setPen(QColor(235, 240, 255))
        p.drawText(QRectF(80, 24, 200, 32), Qt.AlignLeft | Qt.AlignVCenter, "TRILION")

    def closeEvent(self, e):
        try:
            self.assistant.stop()
            self.rt.listener.stop()
            self.rt.player.close()
            self.rt.llm.stop()
        finally:
            QApplication.quit()
            e.accept()
