"""Main interface: transcript + live caption over the reactive triangular wave."""
import html
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QPainter
from PySide6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QSystemTrayIcon, QMenu, QTextBrowser, QVBoxLayout, QWidget)

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
QComboBox{background:rgba(255,255,255,0.07);color:#d6def8;border:1px solid rgba(255,255,255,0.16);border-radius:8px;padding:5px 10px;font-size:12px}
QComboBox QAbstractItemView{background:#10162e;color:#d6def8;selection-background-color:#2a3a7a}
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
        lay.setContentsMargins(34, 22, 34, 180)
        lay.setSpacing(10)
        top = QHBoxLayout()
        top.addSpacing(170)
        self.state_lbl = QLabel("READY", objectName="state")
        self.state_lbl.setMinimumWidth(130)
        top.addWidget(self.state_lbl)
        top.addStretch()
        self.b_mic = self._btn("Mic", True, "Listen for your voice")
        self.b_watch = self._btn("Watch screen", rt.cfg["watch_screen"], "Attach a screenshot to each request")
        self.b_conf = self._btn("Confirm risky", rt.cfg["confirm_risky"], "Ask before shell commands / writing files")
        self.b_wake = self._btn("Wake word", rt.cfg["wake_word"], 'Only react after you say "Trilion"')
        self.b_mic.setChecked(True)
        self.b_talk = self._btn("Talk", False, "Click, speak, click again to send (always works)")
        self.b_stop = QPushButton("Stop")
        self.b_stop.clicked.connect(self._stop)
        for b in (self.b_talk, self.b_mic, self.b_watch, self.b_wake, self.b_conf, self.b_stop):
            top.addWidget(b)
        lay.addLayout(top)
        row0 = QHBoxLayout()
        row0.addSpacing(170)
        self.dev = QComboBox()
        self.dev.setMinimumWidth(320)
        self.dev.setToolTip("Microphone")
        self._fill_devices()
        self.dev.currentIndexChanged.connect(self._pick_dev)
        row0.addWidget(self.dev)
        self.meter = QLabel("", objectName="state")
        self.meter.setMinimumWidth(190)
        row0.addWidget(self.meter)
        row0.addStretch()
        b_copy = QPushButton("Copy log")
        b_copy.setToolTip("Copy the diagnostic log to the clipboard")
        b_copy.clicked.connect(self._copy_log)
        row0.addWidget(b_copy)
        lay.addLayout(row0)

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
        self.inp.setPlaceholderText('Type here and press Enter, or just speak')
        self.inp.returnPressed.connect(self._send)
        row.addWidget(self.inp)
        lay.addLayout(row)

        self.b_mic.toggled.connect(lambda v: setattr(self.assistant, "mic_enabled", v))
        self.b_talk.toggled.connect(self._talk)
        self.b_watch.toggled.connect(lambda v: self._cfg("watch_screen", v))
        self.b_conf.toggled.connect(lambda v: self._cfg("confirm_risky", v))
        self.b_wake.toggled.connect(lambda v: self._cfg("wake_word", v))
        bridge.state.connect(self._on_state)
        bridge.mic_level.connect(lambda v: setattr(self, "mic_lvl", v))
        bridge.out_level.connect(lambda v: setattr(self, "out_lvl", v))
        bridge.caption.connect(self.caption.setText)
        bridge.message.connect(self._on_message)
        bridge.confirm_req.connect(self._on_confirm)
        self._add("assistant", "Online. Click Talk and speak, or just talk (watch the MIC meter), or type below.")

        for m in getattr(rt, "warnings", []):
            self._add("error", m)
        self._quitting = False
        self._ht = self._hs = False
        self._init_tray()
        self._apply_affinity()
        self.hotkey_timer = QTimer(self)
        self.hotkey_timer.timeout.connect(self._poll_hotkeys)
        self.hotkey_timer.start(50)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    # ---- tray ----
    def _init_tray(self):
        self.tray_ok = QSystemTrayIcon.isSystemTrayAvailable()
        self.tray = QSystemTrayIcon(QApplication.windowIcon(), self)
        self.tray.setToolTip("Trilion - Ctrl+Alt+T talk, Ctrl+Alt+S stop")
        menu = QMenu()
        act_show = QAction("Show Trilion", menu)
        act_show.triggered.connect(self._show_front)
        act_talk = QAction("Talk (Ctrl+Alt+T)", menu)
        act_talk.triggered.connect(lambda: self.b_talk.toggle())
        act_stop = QAction("Stop everything (Ctrl+Alt+S)", menu)
        act_stop.triggered.connect(self._stop)
        from ..paths import autostart_enabled, set_autostart
        act_auto = QAction("Start with Windows (hidden in tray)", menu, checkable=True)
        act_auto.setChecked(autostart_enabled())
        act_auto.toggled.connect(lambda v: set_autostart(v))
        act_tray = QAction("Close button hides to tray", menu, checkable=True)
        act_tray.setChecked(bool(self.rt.cfg.get("close_to_tray", False)))
        act_tray.toggled.connect(lambda v: self._cfg("close_to_tray", v))
        act_old = QAction("Use the lighter brain (Qwen2.5-VL 7B) - restart needed", menu, checkable=True)
        act_old.setChecked(self.rt.cfg.get("brain") == "qwen2.5-vl-7b")
        act_old.toggled.connect(lambda v: self._cfg("brain", "qwen2.5-vl-7b" if v else "qwen3.5-9b"))
        act_quit = QAction("Quit Trilion", menu)
        act_quit.triggered.connect(self._quit)
        for a in (act_show, act_talk, act_stop):
            menu.addAction(a)
        menu.addSeparator()
        for a in (act_auto, act_tray, act_old):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray._menu = menu  # keep alive
        self.tray.activated.connect(lambda r: self._show_front() if r == QSystemTrayIcon.Trigger else None)
        if self.tray_ok:
            self.tray.show()

    def _show_front(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit(self):
        self._quitting = True
        self.close()

    # ---- global hotkeys (polled; no keyboard hooks, so no antivirus noise) ----
    def _poll_hotkeys(self):
        try:
            import ctypes
            down = lambda vk: bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
        except Exception:
            self.hotkey_timer.stop()
            return
        combo = down(0x11) and down(0x12)
        t, st = combo and down(0x54), combo and down(0x53)   # Ctrl+Alt+T / Ctrl+Alt+S
        if t and not self._ht:
            self.b_talk.toggle()
        if st and not self._hs:
            self._stop()
        self._ht, self._hs = t, st

    def _apply_affinity(self):
        try:  # keep Trilion's own window out of the screenshots it takes
            import ctypes
            ctypes.windll.user32.SetWindowDisplayAffinity(int(self.winId()), 0x11)
        except Exception:
            pass

    def _btn(self, text, on, tip):
        b = QPushButton(text)
        b.setCheckable(True)
        b.setChecked(bool(on))
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        return b

    def _fill_devices(self):
        import sounddevice as sd
        self.dev.blockSignals(True)
        self.dev.clear()
        self.dev.addItem("Default microphone", None)
        want = self.rt.cfg.get("mic_device")
        pick = 0
        try:
            seen = set()
            api = sd.query_hostapis(sd.default.hostapi)
            for i in api["devices"]:
                d = sd.query_devices(i)
                if d["max_input_channels"] > 0 and d["name"] not in seen:
                    seen.add(d["name"])
                    self.dev.addItem(d["name"], i)  # store the index: names are not unique
                    if d["name"] == want:
                        pick = self.dev.count() - 1
        except Exception:
            pass
        self.dev.setCurrentIndex(pick)
        self.dev.blockSignals(False)

    def _pick_dev(self, _):
        idx = self.dev.currentData()
        self._cfg("mic_device", self.dev.currentText() if idx is not None else None)
        try:
            self.rt.listener.set_device(idx)
        except Exception as e:
            self._add("error", f"Could not open that microphone: {e}")

    def _talk(self, on):
        if on:
            self.assistant.stop()
            self.rt.listener.begin_manual()
            self.state_lbl.setText("RECORDING")
        else:
            self.rt.listener.end_manual()

    def _copy_log(self):
        from ..paths import collect_logs
        QApplication.clipboard().setText(collect_logs())
        self._add("heard", "Log copied to the clipboard - paste it into the chat.")

    def _stop(self):
        self.b_talk.setChecked(False)
        self.assistant.stop()

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
        elif role == "heard":
            h = f'<p style="margin:2px 0;color:#9a8fc0"><i>{t}</i></p>'
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
        bars = int(min(10, self.mic_lvl * 14))
        self.meter.setText("MIC " + "|" * bars + "." * (10 - bars))
        self.wave.tick(dt)
        self.update()

    def showEvent(self, e):
        super().showEvent(e)
        self._apply_affinity()

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
        if self.rt.cfg.get("close_to_tray", False) and self.tray_ok and not self._quitting:
            self.hide()
            e.ignore()
            return
        try:
            self.assistant.stop()
            self.rt.listener.stop()
            self.rt.player.close()
            self.rt.llm.stop()
            self.tray.hide()
        finally:
            QApplication.quit()
            e.accept()
