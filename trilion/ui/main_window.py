"""Trilion command center: sphere core, live feed, agents, system monitor and a big talk bar."""
import html
import os
import time
from collections import deque

from PySide6.QtCore import QDateTime, QTimer, Qt
from PySide6.QtGui import QAction, QIcon, QLinearGradient, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QMenu, QMessageBox, QPushButton, QScrollArea, QSlider, QStackedWidget,
                               QSystemTrayIcon, QTextBrowser, QVBoxLayout, QWidget)

from ..core import screen
from ..core.hud import WebHud, hud_lines
from ..core.sysmon import SysMon
from . import winutil
from .overlay import CORNERS, SIZES, Overlay
from .theme import C, col
from .wave import TriWave
from .widgets import (AgentCard, Brand, Chip, CmdButton, Constellation, Donut, FeedList, IconButton, MicButton,
                      MiniWave, NavButton, OrbWidget, Panel, StatusPill, StatusRow, StopButton, TalkBar, Timeline)

QSS = """
QWidget{color:#dff0ff;font-family:'Segoe UI';font-size:12px}
QToolTip{background:#0a2144;color:#dff0ff;border:1px solid #1f8fff;padding:4px}
QLineEdit{background:rgba(8,28,56,210);border:1px solid rgba(40,150,255,120);border-radius:9px;padding:7px 12px;
 color:#eaf6ff;selection-background-color:#1b5fa8}
QLineEdit:focus{border:1px solid #19d3ff}
QPushButton#btn{background:rgba(14,56,108,200);border:1px solid rgba(40,170,255,150);border-radius:9px;padding:7px 14px;color:#e8f6ff}
QPushButton#btn:hover{background:rgba(24,96,170,220);border:1px solid #19d3ff}
QPushButton#danger{background:rgba(120,24,40,200);border:1px solid rgba(255,95,110,170);border-radius:9px;padding:7px 14px;color:#ffe8ea}
QPushButton#danger:hover{background:rgba(170,34,56,230)}
QCheckBox{spacing:10px;padding:3px}
QCheckBox::indicator{width:18px;height:18px;border-radius:5px;border:1px solid rgba(40,150,255,170);background:rgba(8,28,56,210)}
QCheckBox::indicator:checked{background:#19d3ff;border:1px solid #bff0ff}
QComboBox{background:rgba(8,28,56,210);border:1px solid rgba(40,150,255,120);border-radius:8px;padding:6px 10px}
QComboBox QAbstractItemView{background:#0a2144;color:#dff0ff;selection-background-color:#1b5fa8;border:1px solid #1f8fff}
QTextBrowser,QListWidget{background:transparent;border:none;outline:0}
QListWidget::item{padding:7px 8px;border-bottom:1px solid rgba(40,150,255,45)}
QListWidget::item:selected{background:rgba(25,211,255,60);color:white}
QScrollBar:vertical{width:6px;background:transparent}
QScrollBar::handle:vertical{background:rgba(60,170,255,120);border-radius:3px}
QScrollBar::add-line,QScrollBar::sub-line{height:0}
QLabel#dim{color:#7a9cc8}
QLabel#big{font-size:20px;font-weight:600;color:#eaf8ff}
QLabel#cap{color:#cfeeff;font-size:13px}
"""

STATE_SUB = {"idle": "Tap to talk  -  Ctrl+Alt+T", "listening": "I am listening...", "thinking": "Thinking...",
             "speaking": "Speaking...", "acting": "Working on it..."}
VOICE_TXT = {"idle": "Ready", "listening": "Listening...", "thinking": "Thinking...", "speaking": "Speaking...",
             "acting": "Working..."}


def _btn(text, name="btn", slot=None):
    b = QPushButton(text)
    b.setObjectName(name)
    b.setCursor(Qt.PointingHandCursor)
    if slot:
        b.clicked.connect(slot)
    return b


class MainWindow(QWidget):
    def __init__(self, rt, assistant, bridge):
        super().__init__()
        self.rt, self.assistant, self.bridge, self.cfg = rt, assistant, bridge, rt.cfg
        self.setWindowTitle("Trilion")
        self.resize(1360, 860)
        self.setMinimumSize(1100, 700)
        self.setStyleSheet(QSS)
        self.wave = TriWave()
        self.state, self.talking = "idle", False
        self.mic_lvl = self.out_lvl = 0.0
        self.turns = self.tool_calls = self.warnings = 0
        self.focus = False
        self._quitting = False
        self._ht = self._hs = False
        self.t0 = self.last = time.monotonic()
        self._slow_n = 0
        self.sysmon = SysMon()
        self.sysmon.start()
        from .. import __version__
        self.hud_events = deque(maxlen=8)
        self.hud = None
        self._tick_n = 0
        self._keys_edge = {"o": False, "u": False, "m": False}
        self.overlay = Overlay(self.cfg, __version__)
        self._build()
        self._wire()
        self._init_tray()
        self._apply_affinity()
        screen.add_mask(self._overlay_mask)   # Trilion's own windows are blacked out in the AI's screenshots
        screen.add_mask(self._main_mask)
        if self.cfg.get("overlay_on"):
            self.overlay.show()
        if self.cfg.get("hud_web"):
            self.set_web_hud(True)
        self._feed("live", "Trilion is online. Say something, tap the talk bar, or type a command.")
        for m in getattr(rt, "warnings", []):
            self._feed("warn", m)
            self.warnings += 1
        self._slow()
        self.anim = QTimer(self)
        self.anim.timeout.connect(self._tick)
        self.anim.start(33)
        self.slow = QTimer(self)
        self.slow.timeout.connect(self._slow)
        self.slow.start(1000)
        self.hotkey_timer = QTimer(self)
        self.hotkey_timer.timeout.connect(self._poll_hotkeys)
        self.hotkey_timer.start(50)

    # ------------------------------------------------------------------ layout
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)
        mid = QHBoxLayout()
        mid.setSpacing(12)
        outer.addLayout(mid, 1)
        self.sidebar = self._build_sidebar()
        mid.addWidget(self.sidebar)
        right = QVBoxLayout()
        right.setSpacing(10)
        mid.addLayout(right, 1)
        right.addWidget(self._build_topbar())
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        self.pages = {}
        for key, builder in (("command", self._page_dashboard), ("core", self._page_core), ("chat", self._page_chat),
                             ("skills", self._page_skills), ("memory", self._page_memory),
                             ("game", self._page_game), ("settings", self._page_settings)):
            self.pages[key] = self.stack.addWidget(builder())
        outer.addWidget(self._build_bottom())
        self._goto("command")

    def _build_sidebar(self):
        side = QWidget()
        side.setFixedWidth(232)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.brand = Brand()
        lay.addWidget(self.brand)
        nav = Panel("", pad=(8, 8, 8, 8))
        nav.body.setSpacing(2)
        self.nav = {}
        for key, icon, text in (("command", "grid", "Command Center"), ("core", "core", "AI Core"),
                                ("chat", "chat", "Conversations"), ("skills", "skills", "Tools & Skills"),
                                ("memory", "memory", "Memory"), ("game", "game", "Game Mode"),
                                ("settings", "settings", "Settings")):
            b = NavButton(icon, text)
            b.clicked.connect(lambda _=False, k=key: self._goto(k))
            nav.body.addWidget(b)
            self.nav[key] = b
        nav.body.addStretch()
        lay.addWidget(nav, 1)
        voice = Panel("Voice Status", pad=(12, 34, 12, 10))
        self.voice_wave = MiniWave("cyan")
        self.voice_wave.setFixedHeight(26)
        voice.body.addWidget(self.voice_wave)
        self.voice_lbl = QLabel("Ready")
        self.voice_lbl.setAlignment(Qt.AlignCenter)
        self.voice_lbl.setObjectName("cap")
        voice.body.addWidget(self.voice_lbl)
        self.mic_btn = MicButton()
        self.mic_btn.clicked.connect(lambda: self.set_talking(not self.talking))
        voice.body.addWidget(self.mic_btn, 0, Qt.AlignHCenter)
        self.mic_hint = QLabel("Tap to Speak")
        self.mic_hint.setAlignment(Qt.AlignCenter)
        self.mic_hint.setObjectName("dim")
        voice.body.addWidget(self.mic_hint)
        self.focus_btn = _btn("Focus Mode", slot=self._toggle_focus)
        voice.body.addWidget(self.focus_btn)
        lay.addWidget(voice)
        return side

    def _build_topbar(self):
        bar = QWidget()
        bar.setFixedHeight(56)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.pill = StatusPill()
        lay.addWidget(self.pill)
        lay.addStretch()
        clock = QVBoxLayout()
        clock.setSpacing(0)
        self.date_lbl = QLabel("")
        self.date_lbl.setAlignment(Qt.AlignCenter)
        self.date_lbl.setObjectName("dim")
        self.time_lbl = QLabel("")
        self.time_lbl.setAlignment(Qt.AlignCenter)
        self.time_lbl.setStyleSheet("font-size:22px;font-weight:600;color:#19d3ff;letter-spacing:2px")
        clock.addWidget(self.date_lbl)
        clock.addWidget(self.time_lbl)
        lay.addLayout(clock)
        lay.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search the feed...")
        self.search.setFixedWidth(230)
        lay.addWidget(self.search)
        self.bell = IconButton("bell", "Warnings: open the conversation log")
        self.bell.clicked.connect(lambda: self._goto("chat"))
        lay.addWidget(self.bell)
        gear = IconButton("settings", "Settings")
        gear.clicked.connect(lambda: self._goto("settings"))
        lay.addWidget(gear)
        stop = StopButton()
        stop.clicked.connect(self._stop)
        lay.addWidget(stop)
        op = QLabel(f"<b>{os.environ.get('USERNAME') or os.environ.get('USER') or 'Operator'}</b><br>"
                    "<span style='color:#7a9cc8;font-size:10px'>Commander</span>")
        op.setStyleSheet("padding:4px 12px;border:1px solid rgba(40,150,255,110);border-radius:10px;"
                         "background:rgba(8,30,60,190)")
        lay.addWidget(op)
        return bar

    def _build_bottom(self):
        bar = QWidget()
        bar.setFixedHeight(72)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.chip_brain, self.chip_mic, self.chip_net = Chip("brain", "BRAIN"), Chip("mic", "MICROPHONE"), Chip("pulse", "NETWORK")
        for c in (self.chip_brain, self.chip_mic, self.chip_net):
            c.setFixedWidth(190)
            lay.addWidget(c)
        self.talk = TalkBar()
        self.talk.clicked.connect(lambda: self.set_talking(not self.talking))
        lay.addWidget(self.talk, 1)
        self.brief = _btn("Executive Briefing", slot=lambda: self.assistant.submit_text("Give me my daily briefing."))
        self.brief.setFixedHeight(44)
        lay.addWidget(self.brief)
        return bar

    # ------------------------------------------------------------------ pages
    def _page_dashboard(self):
        page = QWidget()
        col_ = QVBoxLayout(page)
        col_.setContentsMargins(0, 0, 0, 0)
        col_.setSpacing(10)
        self.row1, self.row2, self.row3 = QHBoxLayout(), QHBoxLayout(), QHBoxLayout()
        for r in (self.row1, self.row2, self.row3):
            r.setSpacing(10)
        col_.addLayout(self.row1, 50)
        col_.addLayout(self.row2, 25)
        col_.addLayout(self.row3, 25)

        # --- AI core overview
        self.ov = Panel("AI Core Overview")
        self.ov_rows = {}
        for key, icon, color, name in (("core", "brain", "cyan", "AI Core"), ("memory", "memory", "blue", "Memory"),
                                       ("voice", "mic", "green", "Voice"), ("skills", "skills", "violet", "Skills"),
                                       ("models", "core", "amber", "Models"), ("system", "pulse", "green", "System")):
            r = StatusRow(icon, name, color)
            self.ov.body.addWidget(r)
            self.ov_rows[key] = r
        self.row1.addWidget(self.ov, 22)

        # --- hero
        hero = Panel("", pad=(8, 8, 8, 10))
        from .. import __version__
        self.orb = OrbWidget(__version__)
        hero.body.addWidget(self.orb, 1)
        self.caption = QLabel("")
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.setWordWrap(True)
        self.caption.setObjectName("cap")
        self.caption.setMinimumHeight(40)
        hero.body.addWidget(self.caption)
        self.row1.addWidget(hero, 48)

        # --- live feed + input
        feed = Panel("Live Intelligence Feed", "View All >", lambda: self._goto("chat"))
        self.feed = FeedList()
        feed.body.addWidget(self.feed, 1)
        inp = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a command for Trilion...")
        inp.addWidget(self.input, 1)
        send = _btn("Send", slot=lambda: self._send(self.input))
        inp.addWidget(send)
        feed.body.addLayout(inp)
        self.row1.addWidget(feed, 30)

        # --- agents
        ag = Panel("Active Agents")
        grid = QHBoxLayout()
        left, right = QVBoxLayout(), QVBoxLayout()
        self.agents = {}
        for key, name, icon, color, side in (("brain", "Brain", "brain", "violet", left), ("ears", "Ears", "ear", "cyan", right),
                                             ("voice", "Voice", "speaker", "pink", left), ("hands", "Hands", "hand", "amber", right),
                                             ("eyes", "Eyes", "eye", "green", left), ("game", "Game Player", "game", "blue", right)):
            c = AgentCard(name, icon, color)
            side.addWidget(c)
            self.agents[key] = c
        grid.addLayout(left)
        grid.addLayout(right)
        ag.body.addLayout(grid)
        self.row2.addWidget(ag, 50)

        tl = Panel("Mission Timeline", "View Log >", lambda: self._goto("chat"))
        self.timeline = Timeline()
        tl.body.addWidget(self.timeline, 1)
        self.row2.addWidget(tl, 26)

        qc = Panel("Quick Commands")
        for icon, text, fn in (("mic", "Start Talking", lambda: self.set_talking(not self.talking)),
                               ("game", "Play Minecraft", lambda: self.assistant.submit_text("play minecraft")),
                               ("clock", "Daily Briefing", lambda: self.assistant.submit_text("Give me my daily briefing.")),
                               ("pulse", "System Check", lambda: self.assistant.submit_text("Run a system check on my PC."))):
            b = CmdButton(icon, text)
            b.clicked.connect(fn)
            qc.body.addWidget(b)
        self.row2.addWidget(qc, 24)

        # --- system monitor
        sm = Panel("System Monitor")
        h = QHBoxLayout()
        self.donuts = {k: Donut(lbl, colr) for k, lbl, colr in (("cpu", "CPU", "cyan"), ("ram", "RAM", "blue"),
                                                                 ("disk", "Disk", "green"), ("gpu", "GPU", "violet"))}
        for d in self.donuts.values():
            h.addWidget(d)
        sm.body.addLayout(h)
        self.row3.addWidget(sm, 30)

        mi = Panel("Memory Insights", "View >", lambda: self._goto("memory"))
        hh = QHBoxLayout()
        self.constel = Constellation()
        hh.addWidget(self.constel, 3)
        stats = QVBoxLayout()
        self.stat_labels = {}
        for k, lbl in (("mem", "Memories"), ("turns", "Session Turns"), ("calls", "Tool Calls")):
            a = QLabel(lbl)
            a.setObjectName("dim")
            b = QLabel("0")
            b.setObjectName("big")
            stats.addWidget(a)
            stats.addWidget(b)
            self.stat_labels[k] = b
        hh.addLayout(stats, 1)
        mi.body.addLayout(hh)
        self.row3.addWidget(mi, 26)

        ms = Panel("Local Models", "Manage >", lambda: self._goto("settings"))
        g = QHBoxLayout()
        a_, b_ = QVBoxLayout(), QVBoxLayout()
        self.model_rows = {}
        for key, icon, color, name, side in (("brain", "brain", "cyan", "Brain", a_), ("vision", "eye", "green", "Vision", b_),
                                             ("ears", "ear", "blue", "Ears", a_), ("voice", "speaker", "pink", "Voice", b_),
                                             ("json", "check", "violet", "Strict Replies", a_), ("clicks", "hand", "amber", "Click Mode", b_)):
            r = StatusRow(icon, name, color)
            side.addWidget(r)
            self.model_rows[key] = r
        g.addLayout(a_)
        g.addLayout(b_)
        ms.body.addLayout(g)
        self.row3.addWidget(ms, 44)
        return page

    def _page_core(self):
        p = Panel("AI Core")
        self.core_info = QTextBrowser()
        p.body.addWidget(self.core_info, 1)
        row = QHBoxLayout()
        row.addWidget(_btn("Re-run click calibration on next start", slot=self._recalibrate))
        row.addStretch()
        p.body.addLayout(row)
        return p

    def _page_chat(self):
        p = Panel("Conversation")
        self.log = QTextBrowser()
        self.log.setOpenExternalLinks(False)
        p.body.addWidget(self.log, 1)
        row = QHBoxLayout()
        self.input2 = QLineEdit()
        self.input2.setPlaceholderText("Type a command for Trilion...")
        row.addWidget(self.input2, 1)
        row.addWidget(_btn("Send", slot=lambda: self._send(self.input2)))
        p.body.addLayout(row)
        return p

    def _page_skills(self):
        p = Panel("Tools & Skills")
        self.skill_list = QListWidget()
        p.body.addWidget(self.skill_list, 1)
        row = QHBoxLayout()
        row.addWidget(_btn("Open skills folder", slot=self._open_skills))
        row.addWidget(_btn("Refresh", slot=self._refresh_skills))
        row.addStretch()
        p.body.addLayout(row)
        return p

    def _page_memory(self):
        p = Panel("Memory")
        self.mem_list = QListWidget()
        p.body.addWidget(self.mem_list, 1)
        row = QHBoxLayout()
        row.addWidget(_btn("Forget selected", "danger", self._forget_selected))
        row.addWidget(_btn("Refresh", slot=self._refresh_memory))
        row.addStretch()
        p.body.addLayout(row)
        hint = QLabel("Tell Trilion \"remember that ...\" to add a fact.")
        hint.setObjectName("dim")
        p.body.addWidget(hint)
        return p

    def _page_game(self):
        p = Panel("Game Mode")
        self.game_info = QLabel("")
        self.game_info.setWordWrap(True)
        self.game_info.setTextFormat(Qt.RichText)
        p.body.addWidget(self.game_info)
        row = QHBoxLayout()
        row.addWidget(_btn("Play Minecraft", slot=lambda: self.assistant.submit_text("play minecraft")))
        row.addWidget(_btn("Stop game mode", "danger", lambda: self.assistant.submit_text("stop playing")))
        row.addStretch()
        p.body.addLayout(row)
        p.body.addStretch()
        return p

    def _page_settings(self):
        p = Panel("Settings")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent}")
        inner = QWidget()
        inner.setStyleSheet("background:transparent")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 8, 0)
        scroll.setWidget(inner)
        p.body.addWidget(scroll, 1)

        def section(text):
            lb = QLabel(text.upper())
            lb.setStyleSheet("color:#38c9ff;font-weight:600;letter-spacing:2px;padding-top:10px")
            lay.addWidget(lb)

        def check(text, key=None, slot=None, checked=None):
            cb = QCheckBox(text)
            cb.setChecked(bool(self.cfg.get(key, False)) if checked is None else checked)
            cb.toggled.connect(slot or (lambda v, k=key: self._cfg(k, v)))
            lay.addWidget(cb)
            return cb

        section("Behaviour")
        check("Watch the screen (attach a screenshot to each request)", "watch_screen")
        check("Wake word: only react after I say \"Trilion\"", "wake_word")
        check("Ask before shell commands and file writes", "confirm_risky")
        check("Always ask before Delete / Pay / Send style clicks", "confirm_critical")
        check("Strict replies (forced JSON format)", "structured")
        check("Close button hides to the tray", "close_to_tray")
        check("Microphone listening", slot=lambda v: setattr(self.assistant, "mic_enabled", v), checked=True)
        from ..paths import autostart_enabled, set_autostart
        check("Start with Windows (hidden in the tray)", slot=lambda v: set_autostart(v), checked=autostart_enabled())

        section("Overlay & screen recording")
        self.cb_overlay = check("Show the always-on-top overlay: core + live data (Ctrl+Alt+O)", slot=self.set_overlay,
                                checked=bool(self.cfg.get("overlay_on")))
        self.cb_lock = check("Overlay is click-through (untick, or Ctrl+Alt+U, to drag it)", slot=self.set_overlay_locked,
                             checked=self.overlay.locked)
        self.cb_rec = check("Show Trilion's main window in screen recordings", slot=self.set_show_in_recordings,
                            checked=bool(self.cfg.get("show_in_recordings")))
        note = QLabel("The overlay always appears in recordings that capture the desktop (OBS Display Capture, NVIDIA, "
                      "Windows Game Bar full screen). Exclusive-fullscreen games hide it: use borderless windowed. "
                      "Trilion's own screenshots black the overlay out so the AI ignores it.")
        note.setWordWrap(True)
        note.setObjectName("dim")
        lay.addWidget(note)
        r = QHBoxLayout()
        r.addWidget(QLabel("Overlay size"))
        self.size_box = QComboBox()
        for k in SIZES:
            self.size_box.addItem(k.capitalize(), k)
        self.size_box.setCurrentIndex(max(0, self.size_box.findData(self.overlay.size_name)))
        self.size_box.currentIndexChanged.connect(lambda _: self.overlay.set_size(self.size_box.currentData()))
        r.addWidget(self.size_box)
        r.addWidget(QLabel("Corner"))
        self.corner_box = QComboBox()
        for k in CORNERS:
            self.corner_box.addItem(k.replace("-", " ").title(), k)
        self.corner_box.setCurrentIndex(max(0, self.corner_box.findData(self.cfg.get("overlay_corner", "top-right"))))
        self.corner_box.currentIndexChanged.connect(lambda _: self.overlay.set_corner(self.corner_box.currentData()))
        r.addWidget(self.corner_box)
        r.addWidget(QLabel("Opacity"))
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(30, 100)
        self.opacity.setValue(int(float(self.cfg.get("overlay_opacity", 0.88)) * 100))
        self.opacity.setFixedWidth(120)
        self.opacity.valueChanged.connect(lambda v: self.overlay.set_opacity(v / 100))
        r.addWidget(self.opacity)
        r.addStretch()
        lay.addLayout(r)
        self.cb_web = check("Serve the overlay to OBS as a Browser Source (works with any capture method)",
                            slot=self.set_web_hud, checked=bool(self.cfg.get("hud_web")))
        r = QHBoxLayout()
        self.url_lbl = QLabel("(off)")
        self.url_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.url_lbl.setStyleSheet("color:#19d3ff;font-family:Consolas")
        r.addWidget(self.url_lbl, 1)
        r.addWidget(_btn("Copy URL", slot=self._copy_hud_url))
        lay.addLayout(r)
        hint = QLabel("In OBS: Sources > + > Browser > paste the URL > width 440, height 520. "
                      "Add ?size=compact or ?size=full for other sizes, and &bg=0 for no background.")
        hint.setWordWrap(True)
        hint.setObjectName("dim")
        lay.addWidget(hint)

        section("Devices & brain")
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Microphone"))
        self.dev = QComboBox()
        self.dev.setMinimumWidth(320)
        self._fill_devices()
        self.dev.currentIndexChanged.connect(self._pick_dev)
        r1.addWidget(self.dev)
        r1.addStretch()
        lay.addLayout(r1)
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Brain (restart needed)"))
        self.brain_box = QComboBox()
        from ..paths import BRAINS
        for k, v in BRAINS.items():
            self.brain_box.addItem(v["label"], k)
        self.brain_box.setCurrentIndex(max(0, self.brain_box.findData(self.cfg.get("brain"))))
        self.brain_box.currentIndexChanged.connect(lambda _: self._cfg("brain", self.brain_box.currentData()))
        r2.addWidget(self.brain_box)
        r2.addStretch()
        lay.addLayout(r2)
        r3 = QHBoxLayout()
        r3.addWidget(_btn("Copy log", slot=self._copy_log))
        r3.addWidget(_btn("Open logs folder", slot=self._open_logs))
        r3.addStretch()
        lay.addLayout(r3)
        lay.addStretch()
        return p

    # ------------------------------------------------------------------ wiring
    def _wire(self):
        b = self.bridge
        b.state.connect(self._on_state)
        b.mic_level.connect(lambda v: setattr(self, "mic_lvl", v))
        b.out_level.connect(lambda v: setattr(self, "out_lvl", v))
        b.caption.connect(self.caption.setText)
        b.message.connect(self._on_message)
        b.confirm_req.connect(self._on_confirm)
        self.search.textChanged.connect(self.feed.set_filter)
        self.input.returnPressed.connect(lambda: self._send(self.input))
        self.input2.returnPressed.connect(lambda: self._send(self.input2))

    def _goto(self, key):
        self.stack.setCurrentIndex(self.pages[key])
        for k, b in self.nav.items():
            b.setChecked(k == key)
        if key == "skills":
            self._refresh_skills()
        elif key == "memory":
            self._refresh_memory()
        elif key == "core":
            self._refresh_core()
        elif key == "game":
            self._refresh_game()

    def _toggle_focus(self):
        self.focus = not self.focus
        self.sidebar.setVisible(not self.focus)
        for w in (self.ov, ):
            w.setVisible(not self.focus)
        for lay in (self.row2, self.row3):
            for i in range(lay.count()):
                lay.itemAt(i).widget().setVisible(not self.focus)
        self.focus_btn.setText("Exit Focus" if self.focus else "Focus Mode")
        if self.focus:
            self.focus_exit = getattr(self, "focus_exit", None) or QPushButton("Exit Focus Mode", self)
            self.focus_exit.setObjectName("btn")
            self.focus_exit.clicked.connect(self._toggle_focus)
            self.focus_exit.move(20, 14)
            self.focus_exit.show()
        elif getattr(self, "focus_exit", None):
            self.focus_exit.hide()

    # ------------------------------------------------------------------ events
    def _ts(self):
        return QDateTime.currentDateTime().toString("hh:mm ap").lower()

    def _feed(self, kind, text):
        self.feed.add(kind, text, self._ts())

    def _on_state(self, s):
        self.state = s
        self.wave.set_state(s)
        self._refresh_agents()

    def _hud_event(self, kind, text):
        self.hud_events.append({"k": kind, "text": text})

    def _on_message(self, role, text):
        self._log(role, text)
        if role == "user":
            self._hud_event("you", f"you: {text}")
        elif role == "assistant":
            self._hud_event("reply", text)
        elif role == "action":
            self._hud_event("run", self._short_action(text))
        elif role == "result":
            for ev in reversed(self.hud_events):
                if ev["k"] == "run":
                    ev["k"] = "ok" if text.startswith("ok|") else "fail"
                    break
        elif role == "error":
            self._hud_event("warn", text)
        if role == "user":
            self.turns += 1
            self._feed("you", f"You: {text}")
        elif role == "assistant":
            self._feed("reply", text)
        elif role == "action":
            self.tool_calls += 1
            self.timeline.add(QDateTime.currentDateTime().toString("hh:mm"), self._short_action(text))
            self._feed("action", text)
        elif role == "result":
            ok, _, msg = (text.split("|", 2) + ["", ""])[:3]
            self.timeline.finish(ok == "ok")
            if ok != "ok":
                self._feed("warn", msg)
        elif role == "error":
            self.warnings += 1
            self._feed("warn", text)
            self.bell.badge = True
            self.bell.update()
        elif role == "heard":
            self._feed("info", text)

    @staticmethod
    def _short_action(text):
        """'open_app {"name": "discord"}' -> 'open_app: discord'"""
        import json
        tool, _, rest = text.partition(" ")
        try:
            vals = [str(v) for v in json.loads(rest).values() if v not in ("", None, False)]
            return f"{tool}: {', '.join(vals)[:40]}" if vals else tool
        except Exception:
            return text

    def _log(self, role, text):
        t = html.escape(text).replace("\n", "<br>")
        h = {"user": f'<p style="margin:8px 0"><span style="color:#7fe8ff">You</span>&nbsp; {t}</p>',
             "assistant": f'<p style="margin:8px 0"><span style="color:#ff7fb8">Trilion</span>&nbsp; {t}</p>',
             "action": f'<p style="margin:2px 0;color:#7c89b8">&#9656; {t}</p>',
             "heard": f'<p style="margin:2px 0;color:#9a8fc0"><i>{t}</i></p>',
             "error": f'<p style="margin:6px 0;color:#ff8a8a">{t}</p>'}.get(role)
        if h:
            self.log.append(h)

    def _send(self, line):
        t = line.text().strip()
        if t:
            line.clear()
            self.assistant.submit_text(t)

    def _on_confirm(self, question, handle):
        ev, box = handle
        r = QMessageBox.question(self, "Trilion needs permission", question,
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        box[0] = r == QMessageBox.Yes
        ev.set()

    # ------------------------------------------------------------------ voice
    def set_talking(self, on):
        if on == self.talking:
            return
        self.talking = on
        if on:
            self.assistant.stop()
            self.rt.listener.begin_manual()
        else:
            self.rt.listener.end_manual()

    def _stop(self):
        if self.talking:                       # discard what was being recorded
            self.talking = False
            self.rt.listener.manual = False
            self.rt.listener.manual_buf = []
        self.assistant.stop()

    # ------------------------------------------------------------------ periodic refresh
    def _level_and_state(self):
        if self.talking:
            return self.mic_lvl, "listening"
        if self.state == "speaking":
            return self.out_lvl, "speaking"
        if self.mic_lvl > 0.08 and self.state in ("idle", "listening"):
            return self.mic_lvl, "listening"
        return 0.0, self.state

    def _tick(self):
        now = time.monotonic()
        dt, self.last = min(0.1, now - self.last), now
        t = now - self.t0
        lvl, shown = self._level_and_state()
        self.wave.set_state(shown)
        self.wave.set_level(lvl)
        self.wave.tick(dt)
        c, wl = self.wave.color, self.wave.level
        if self.stack.currentIndex() == self.pages["command"]:
            self.orb.tick(t, wl, shown, c)
            for a in self.agents.values():
                a.wave.tick(t, wl)
            self.timeline.tick(t)
            self.constel.tick(t)
        self.brand.tick(t, c)
        self.talk.tick(t, wl, shown, c)
        self.mic_btn.tick(t, wl, self.talking or shown == "listening", c)
        self.voice_wave.active = shown in ("listening", "speaking") or self.talking
        self.voice_wave.tick(t, wl)
        sub = "Recording... tap again to send" if self.talking else STATE_SUB.get(shown, "")
        self.talk.sub = sub
        self._tick_n += 1
        if self._tick_n % 3 == 0 and (self.overlay.isVisible() or self.hud):
            snap = self._hud_snapshot(shown, wl, c)
            if self.overlay.isVisible():
                self.overlay.set_snapshot(snap)
            if self.hud:
                self.hud.update(snap)
        self.voice_lbl.setText("Recording..." if self.talking else VOICE_TXT.get(shown, "Ready"))
        self.mic_hint.setText("Tap to send" if self.talking else ("Tap to Speak" if shown == "idle" else ""))
        self.update()

    def _hud_snapshot(self, shown, wl, c):
        from .. import __version__
        d, tools = self.sysmon.data, self.assistant.tools
        game = None
        if tools.game_on:
            g = tools.game
            game = {"on": True, "profile": tools.game_profile, "keys": sorted(g.keys),
                    "buttons": sorted(g.buttons), "move": list(g.last_move)}
        llm = self.rt.llm
        brain = llm.brain["label"].split(" (")[0] if hasattr(llm, "brain") else "Local model"
        return {"version": __version__, "state": shown, "color": [int(x) for x in c], "level": round(wl, 3),
                "brain": brain, "tps": getattr(llm, "last_tps", None), "cpu": d["cpu"], "ram": d["ram"],
                "gpu": d["gpu"], "vram": d["vram"], "vram_total": d["vram_total"], "mic": self.mic_lvl,
                "out": self.out_lvl, "events": list(self.hud_events), "game": game}

    def _slow(self):
        now = QDateTime.currentDateTime()
        self.date_lbl.setText(now.toString("dddd, d MMMM yyyy"))
        self.time_lbl.setText(now.toString("hh:mm:ss ap").lower())
        d = self.sysmon.data
        self.donuts["cpu"].set(d["cpu"])
        self.donuts["ram"].set(d["ram"])
        self.donuts["disk"].set(d["disk"])
        if d["gpu"] is not None and d["vram_total"]:
            self.donuts["gpu"].set(100.0 * d["vram"] / d["vram_total"], f"{d['vram'] / 1024:.1f}G")
            self.donuts["gpu"].label = "VRAM"
        else:
            self.donuts["gpu"].set(0, "n/a")
        mem = len(getattr(self.assistant.memory, "items", []))
        if self._slow_n % 15 == 0:
            self._skills_n = len(self.assistant.skills.all())
        self._slow_n += 1
        brain = self.rt.llm.brain["label"] if hasattr(self.rt.llm, "brain") else "Local model"
        vram_full = bool(d["vram_total"]) and d["vram"] / d["vram_total"] > 0.97
        ok = d["ram"] < 95 and not vram_full            # CPU spikes are normal while the AI is working
        self.pill.set(ok, "OPTIMAL" if ok else "BUSY")
        o = self.ov_rows
        o["core"].set(f"Active  -  {brain.split(' (')[0]}")
        o["memory"].set(f"{mem} stored")
        o["voice"].set("Online" if getattr(self.assistant, "mic_enabled", True) else "Mic off", getattr(self.assistant, "mic_enabled", True))
        o["skills"].set(f"{self._skills_n} loaded")
        o["models"].set("3 loaded")
        o["system"].set("Optimal" if ok else "Heavy load", ok)
        self.stat_labels["mem"].setText(str(mem))
        self.stat_labels["turns"].setText(str(self.turns))
        self.stat_labels["calls"].setText(str(self.tool_calls))
        self.constel.set_count(mem)
        self.nav["chat"].badge = self.turns or None
        self.nav["skills"].badge = self._skills_n or None
        self.nav["chat"].update()
        self.nav["skills"].update()
        m = self.model_rows
        m["brain"].set(brain.split(" (")[0])
        m["vision"].set("Screen reading online")
        m["ears"].set(str(self.cfg.get("whisper_repo", "whisper")).split("/")[-1].replace("faster-whisper-", "Whisper "))
        m["voice"].set(f"Kokoro - {self.cfg.get('voice', '')}")
        sj = getattr(self.rt.llm, "structured_ok", True) and self.cfg.get("structured", False)
        m["json"].set("On" if sj else "Off", bool(sj))
        m["clicks"].set(str(self.cfg.get("coord_mode") or "auto"))
        self.chip_brain.set(brain.split(" (")[0])
        self.chip_mic.set(self.cfg.get("mic_device") or "Windows default")
        self.chip_net.set("Local only (offline)")
        self._refresh_agents()

    def _refresh_agents(self):
        st, a = self.state, self.agents
        talk = self.talking or st == "listening" or self.mic_lvl > 0.08
        mic_on = getattr(self.assistant, "mic_enabled", True)
        a["ears"].set_state("Listening" if talk and mic_on else ("Standby" if mic_on else "Muted"), talk and mic_on)
        a["brain"].set_state("Thinking" if st == "thinking" else "Standby", st == "thinking")
        a["voice"].set_state("Speaking" if st == "speaking" else "Standby", st == "speaking")
        a["hands"].set_state("Working" if st == "acting" else "Standby", st == "acting")
        watch = bool(self.cfg.get("watch_screen", True))
        a["eyes"].set_state("Watching" if watch and st in ("thinking", "acting") else ("Standby" if watch else "Off"),
                            watch and st in ("thinking", "acting"))
        tools = self.assistant.tools
        if tools.game_on:
            a["game"].set_state(f"Playing {tools.game_profile or tools.game_window or 'game'}", True)
        else:
            a["game"].set_state("Standby", False)

    # ------------------------------------------------------------------ page refreshers
    def _refresh_core(self):
        llm, cfg = self.rt.llm, self.cfg
        b = getattr(llm, "brain", {})
        rows = [("Brain", b.get("label", "?")), ("Model repo", b.get("repo", "?")), ("Quantization", b.get("quant", "?")),
                ("Context window", cfg.get("context")), ("Strict JSON replies", getattr(llm, "structured_ok", True)),
                ("Click coordinates", cfg.get("coord_mode") or "auto"), ("Speech recognition", cfg.get("whisper_repo")),
                ("Voice", cfg.get("voice")), ("Screenshot width", cfg.get("screen_max_width")),
                ("Minecraft sensitivity / FOV / turn scale",
                 f"{cfg.get('mc_sensitivity', 100)}% / {cfg.get('mc_fov', 70)} / {cfg.get('mc_turn_scale', 1.0)}")]
        self.core_info.setHtml("<table cellpadding='7'>" + "".join(
            f"<tr><td style='color:#7a9cc8'>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>" for k, v in rows) + "</table>")

    def _recalibrate(self):
        self._cfg("coord_checked", None)
        self._feed("info", "Click calibration will run again the next time Trilion starts.")

    def _refresh_skills(self):
        from ..core.tools import tool_specs
        self.skill_list.clear()
        for s in self.assistant.skills.all():
            self.skill_list.addItem(f"{s['name']}  -  {s['description']}")
        self.skill_list.addItem(f"({len(tool_specs())} built-in tools are always available)")

    def _open_skills(self):
        try:
            from ..core.skills import user_dir
            os.startfile(str(user_dir()))
        except Exception:
            pass

    def _refresh_memory(self):
        self.mem_list.clear()
        for i in self.assistant.memory.items:
            self.mem_list.addItem(i["fact"])
        if not self.assistant.memory.items:
            self.mem_list.addItem("(nothing remembered yet)")

    def _forget_selected(self):
        for it in self.mem_list.selectedItems():
            self.assistant.memory.forget(it.text())
        self._refresh_memory()

    def _refresh_game(self):
        t = self.assistant.tools
        state = f"<b style='color:#34ffaa'>ON</b> - {html.escape(t.game_window or 'any window')} ({t.game_profile or 'general'})" \
            if t.game_on else "<b style='color:#7a9cc8'>OFF</b>"
        self.game_info.setText(
            f"<p>Game mode: {state}</p>"
            "<p style='color:#9cc4ee'>Trilion plays with the real keyboard and mouse only: scan-code keys, exact relative mouse "
            "moves, short timed actions, and a dead-man timer that releases every key. Use single-player games; online games with "
            "anti-cheat may block fake input.</p>"
            "<p style='color:#9cc4ee'>Hotkeys: <b>Ctrl+Alt+T</b> talk, <b>Ctrl+Alt+S</b> stop and release everything.</p>"
            "<p style='color:#9cc4ee'>Minecraft tip: Raw Input ON, sensitivity 100%, FOV 70, FOV Effects 0%, View Bobbing OFF.</p>")

    # ------------------------------------------------------------------ overlay / recording / OBS
    def _overlay_mask(self):
        return self.overlay.rect_real()

    def _main_mask(self):
        if not self.cfg.get("show_in_recordings") or not self.isVisible() or self.isMinimized():
            return None
        return winutil.window_rect(int(self.winId()))

    def _sync_checks(self):
        for cb, val in ((getattr(self, "cb_overlay", None), self.overlay.isVisible()),
                        (getattr(self, "cb_lock", None), self.overlay.locked),
                        (getattr(self, "cb_rec", None), bool(self.cfg.get("show_in_recordings"))),
                        (getattr(self, "cb_web", None), self.hud is not None)):
            if cb is not None and cb.isChecked() != val:
                cb.blockSignals(True)
                cb.setChecked(val)
                cb.blockSignals(False)
        for act, val in ((getattr(self, "act_overlay", None), self.overlay.isVisible()),
                         (getattr(self, "act_unlock", None), not self.overlay.locked)):
            if act is not None and act.isChecked() != val:
                act.blockSignals(True)
                act.setChecked(val)
                act.blockSignals(False)

    def set_overlay(self, on):
        self._cfg("overlay_on", bool(on))
        if on:
            self.overlay.apply_layout()
            self.overlay.show()
        else:
            self.overlay.hide()
        self._sync_checks()

    def set_overlay_locked(self, locked):
        self.overlay.set_locked(locked)
        self._sync_checks()

    def cycle_overlay_size(self):
        name = self.overlay.cycle_size()
        self._feed("info", f"Overlay size: {name}")

    def set_show_in_recordings(self, on):
        self._cfg("show_in_recordings", bool(on))
        self._apply_affinity()
        self._sync_checks()

    def set_web_hud(self, on):
        self._cfg("hud_web", bool(on))
        if on and self.hud is None:
            try:
                self.hud = WebHud(int(self.cfg.get("hud_port", 17655)))
                self.hud.start()
                self._feed("info", f"OBS Browser Source ready: {self.hud.url}")
            except Exception as e:
                self.hud = None
                self._cfg("hud_web", False)
                self._feed("warn", f"Could not start the OBS source: {e}")
        elif not on and self.hud is not None:
            self.hud.stop()
            self.hud = None
        if getattr(self, "url_lbl", None):
            self.url_lbl.setText(self.hud.url + "?size=standard" if self.hud else "(off)")
        self._sync_checks()

    def _copy_hud_url(self):
        if self.hud:
            QApplication.clipboard().setText(self.hud.url + "?size=standard")
            self._feed("info", "OBS Browser Source URL copied. In OBS: Sources > + > Browser > paste it.")
        else:
            self._feed("warn", "Turn on 'Serve the overlay to OBS' first.")

    # ------------------------------------------------------------------ settings helpers
    def _cfg(self, k, v):
        self.cfg[k] = v
        try:
            self.cfg.save()
        except Exception:
            pass

    def _fill_devices(self):
        import sounddevice as sd
        self.dev.blockSignals(True)
        self.dev.clear()
        self.dev.addItem("Default microphone", None)
        want, pick = self.cfg.get("mic_device"), 0
        try:
            seen = set()
            for i in sd.query_hostapis(sd.default.hostapi)["devices"]:
                d = sd.query_devices(i)
                if d["max_input_channels"] > 0 and d["name"] not in seen:
                    seen.add(d["name"])
                    self.dev.addItem(d["name"], i)           # store the index: names are not unique
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
            self._feed("warn", f"Could not open that microphone: {e}")

    def _copy_log(self):
        from ..paths import collect_logs
        QApplication.clipboard().setText(collect_logs())
        self._feed("info", "Log copied to the clipboard - paste it into the chat.")

    def _open_logs(self):
        from ..paths import open_logs_folder
        open_logs_folder()

    # ------------------------------------------------------------------ tray / hotkeys / window
    def _init_tray(self):
        self.tray_ok = QSystemTrayIcon.isSystemTrayAvailable()
        icon = QApplication.windowIcon()
        if icon.isNull():                       # never show a blank tray icon
            from PySide6.QtGui import QPainter as _P
            from .wave import draw_logo
            pm = QPixmap(64, 64)
            pm.fill(Qt.transparent)
            pp = _P(pm)
            pp.setRenderHint(_P.Antialiasing)
            draw_logo(pp, 32, 34, 26, (25, 211, 255))
            pp.end()
            icon = QIcon(pm)
            QApplication.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("Trilion - Ctrl+Alt+T talk, Ctrl+Alt+S stop")
        menu = QMenu()
        act_show = QAction("Show Trilion", menu)
        act_show.triggered.connect(self._show_front)
        act_talk = QAction("Talk (Ctrl+Alt+T)", menu)
        act_talk.triggered.connect(lambda: self.set_talking(not self.talking))
        act_stop = QAction("Stop everything (Ctrl+Alt+S)", menu)
        act_stop.triggered.connect(self._stop)
        from ..paths import autostart_enabled, set_autostart
        act_auto = QAction("Start with Windows (hidden in tray)", menu, checkable=True)
        act_auto.setChecked(autostart_enabled())
        act_auto.toggled.connect(lambda v: set_autostart(v))
        act_tray = QAction("Close button hides to tray", menu, checkable=True)
        act_tray.setChecked(bool(self.cfg.get("close_to_tray", False)))
        act_tray.toggled.connect(lambda v: self._cfg("close_to_tray", v))
        self.act_overlay = QAction("Show overlay (Ctrl+Alt+O)", menu, checkable=True)
        self.act_overlay.setChecked(bool(self.cfg.get("overlay_on")))
        self.act_overlay.toggled.connect(self.set_overlay)
        self.act_unlock = QAction("Unlock overlay to drag it (Ctrl+Alt+U)", menu, checkable=True)
        self.act_unlock.setChecked(not self.overlay.locked)
        self.act_unlock.toggled.connect(lambda v: self.set_overlay_locked(not v))
        act_size = QAction("Next overlay size (Ctrl+Alt+M)", menu)
        act_size.triggered.connect(self.cycle_overlay_size)
        act_old = QAction("Use the lighter brain (Qwen2.5-VL 7B) - restart needed", menu, checkable=True)
        act_old.setChecked(self.cfg.get("brain") == "qwen2.5-vl-7b")
        act_old.toggled.connect(lambda v: self._cfg("brain", "qwen2.5-vl-7b" if v else "qwen3.5-9b"))
        act_quit = QAction("Quit Trilion", menu)
        act_quit.triggered.connect(self._quit)
        for a in (act_show, act_talk, act_stop):
            menu.addAction(a)
        menu.addSeparator()
        for a in (self.act_overlay, self.act_unlock, act_size):
            menu.addAction(a)
        menu.addSeparator()
        for a in (act_auto, act_tray, act_old):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray._menu = menu
        self.tray.activated.connect(lambda r: self._show_front() if r == QSystemTrayIcon.Trigger else None)
        if self.tray_ok:
            self.tray.show()
            if not self.cfg.get("tray_hint_shown"):
                self.tray.showMessage("Trilion is running",
                                      "Its icon lives in the tray. If you do not see it, click the ^ arrow next to the "
                                      "clock (Windows hides new icons there).", QSystemTrayIcon.Information, 8000)
                self._cfg("tray_hint_shown", True)

    def _show_front(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit(self):
        self._quitting = True
        self.close()

    def _poll_hotkeys(self):
        try:
            import ctypes
            user32 = ctypes.windll.user32
        except Exception:
            self.hotkey_timer.stop()      # not Windows: no global hotkeys
            return
        down = lambda vk: bool(user32.GetAsyncKeyState(vk) & 0x8000)
        combo = down(0x11) and down(0x12)
        t, st = combo and down(0x54), combo and down(0x53)   # Ctrl+Alt+T / Ctrl+Alt+S
        if t and not self._ht:
            self.set_talking(not self.talking)
        if st and not self._hs:
            self._stop()
        self._ht, self._hs = t, st
        for key, vk, fn in (("o", 0x4F, lambda: self.set_overlay(not self.overlay.isVisible())),   # Ctrl+Alt+O
                            ("u", 0x55, lambda: self.set_overlay_locked(not self.overlay.locked)),  # Ctrl+Alt+U
                            ("m", 0x4D, self.cycle_overlay_size)):                                  # Ctrl+Alt+M
            now = combo and down(vk)
            if now and not self._keys_edge[key]:
                fn()
            self._keys_edge[key] = now

    def _apply_affinity(self):
        # Default: hidden from screenshots AND recordings (so the AI sees what is behind it).
        # With "show in recordings" on, it is capturable and blacked out in the AI's screenshots instead.
        winutil.set_capture_hidden(int(self.winId()), not self.cfg.get("show_in_recordings", False))

    def showEvent(self, e):
        super().showEvent(e)
        self._apply_affinity()

    def paintEvent(self, e):
        p = QPainter(self)
        w, h = self.width(), self.height()
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, col("bg0"))
        g.setColorAt(1, col("bg1"))
        p.fillRect(0, 0, w, h, g)
        rg = QRadialGradient(w * 0.5, h * 0.32, w * 0.55)
        rg.setColorAt(0, col((20, 110, 210), 46))
        rg.setColorAt(1, col((20, 110, 210), 0))
        p.fillRect(0, 0, w, h, rg)

    def closeEvent(self, e):
        if self.cfg.get("close_to_tray", False) and self.tray_ok and not self._quitting:
            self.hide()
            e.ignore()
            return
        try:
            screen.remove_mask(self._overlay_mask)
            screen.remove_mask(self._main_mask)
            self.overlay.hide()
            if self.hud:
                self.hud.stop()
            self.assistant.stop()
            self.rt.listener.stop()
            self.rt.player.close()
            self.rt.llm.stop()
            self.tray.hide()
        finally:
            QApplication.quit()
            e.accept()
