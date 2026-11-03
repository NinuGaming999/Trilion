"""Trilion command-centre dashboard. The dashboard is a view over the existing local runtime."""
import html
import math
import os
import time
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QPainter
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSystemTrayIcon, QMenu,
    QTextBrowser, QVBoxLayout, QWidget, QProgressBar
)

from .core import OrbCore

THEMES = {
    "NEURAL": {"accent": "#25d9f2", "secondary": "#4a80ff", "glow": "#124d80"},
    "FOCUS": {"accent": "#ad83ff", "secondary": "#5572ff", "glow": "#39206f"},
    "AURORA": {"accent": "#42e6ad", "secondary": "#19a5bb", "glow": "#124e4a"},
}
STATE_TEXT = {"idle": "SYSTEM READY", "listening": "LISTENING", "thinking": "THINKING",
              "speaking": "SPEAKING", "acting": "EXECUTING"}


def _qss(accent):
    return f"""
    QWidget {{ color:#dce9f8; font-family:'Segoe UI'; font-size:12px; }}
    QFrame#sidebar {{ background:#061321; border:1px solid #142e45; border-radius:13px; }}
    QFrame#card {{ background:rgba(7,22,39,236); border:1px solid #173750; border-radius:10px; }}
    QFrame#metric {{ background:rgba(13,37,58,190); border:1px solid #1a3c55; border-radius:7px; }}
    QLabel#eyebrow {{ color:#86a7c2; font-size:9px; font-weight:700; letter-spacing:1.7px; }}
    QLabel#muted {{ color:#7795ad; font-size:10px; }}
    QLabel#value {{ color:#effaff; font-size:12px; font-weight:650; }}
    QLabel#brand {{ color:#dffaff; font-size:19px; font-weight:750; letter-spacing:4px; }}
    QLabel#brandSub {{ color:{accent}; font-size:8px; font-weight:700; letter-spacing:2.3px; }}
    QLabel#clock {{ color:{accent}; font-size:19px; font-weight:700; }}
    QLabel#state {{ color:{accent}; font-size:10px; font-weight:750; letter-spacing:1.6px; }}
    QLabel#caption {{ color:#e7faff; font-size:12px; font-weight:600; }}
    QPushButton {{ background:#0d263c; color:#cfe2f2; border:1px solid #21445d; border-radius:7px; padding:7px 10px; font-size:11px; }}
    QPushButton:hover {{ background:#12344e; border-color:{accent}; }}
    QPushButton:checked {{ background:{accent}; color:#031421; border-color:{accent}; font-weight:750; }}
    QPushButton#nav {{ background:transparent; border:1px solid transparent; text-align:left; padding:8px 10px; color:#a8bfd2; }}
    QPushButton#nav:hover {{ background:#0d293e; border-color:#1a4059; color:#effaff; }}
    QPushButton#nav:checked {{ background:#103149; border-color:{accent}; color:#f3fdff; }}
    QPushButton#primary {{ background:{accent}; color:#031421; border:1px solid {accent}; font-weight:750; padding:9px 15px; }}
    QPushButton#primary:hover {{ background:#9af4ff; }}
    QLineEdit {{ background:#081b2b; border:1px solid #1b3c54; border-radius:8px; padding:8px 11px; color:#e9f7ff; selection-background-color:{accent}; }}
    QLineEdit:focus {{ border:1px solid {accent}; }}
    QComboBox {{ background:#0a2033; color:#dceeff; border:1px solid #24465f; border-radius:7px; padding:7px 10px; min-width:112px; }}
    QComboBox QAbstractItemView {{ background:#0b2032; color:#e4f2ff; selection-background-color:#18415c; }}
    QTextBrowser {{ background:transparent; border:0; color:#c9dced; font-size:11px; }}
    QProgressBar {{ background:#071522; border:1px solid #1c3c54; border-radius:4px; height:6px; text-align:center; }}
    QProgressBar::chunk {{ background:{accent}; border-radius:3px; }}
    QScrollArea {{ background:transparent; border:0; }}
    """


class MainWindow(QWidget):
    def __init__(self, rt, assistant, bridge):
        super().__init__()
        self.rt, self.assistant, self.bridge = rt, assistant, bridge
        self.setWindowTitle("Trilion | Command Center")
        self.resize(1380, 860)
        self.setMinimumSize(1050, 690)
        self.theme_name = "NEURAL"
        self.state = "idle"
        self.mic_lvl = self.out_lvl = 0.0
        self._last_refresh = 0.0
        self._quitting = False
        self._ht = self._hs = False
        self.feed_entries = []

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(9)
        self.sidebar = self._build_sidebar()
        root.addWidget(self.sidebar)

        main = QVBoxLayout()
        main.setSpacing(9)
        root.addLayout(main, 1)
        main.addWidget(self._build_header())

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.dash = QWidget()
        self.dash_grid = QGridLayout(self.dash)
        self.dash_grid.setContentsMargins(0, 0, 0, 0)
        self.dash_grid.setHorizontalSpacing(9)
        self.dash_grid.setVerticalSpacing(9)
        self._build_dashboard()
        self.scroll.setWidget(self.dash)
        main.addWidget(self.scroll, 1)
        main.addWidget(self._build_bottom_bar())

        self._apply_theme()
        self._wire_runtime()
        self._add("assistant", "Trilion is online. Talk naturally, use the Talk control, or type a request below.")
        for warning in getattr(rt, "warnings", []):
            self._push_feed("AUDIO / SYSTEM WARNING", warning, "WARN")
        self._push_feed("LOCAL RUNTIME", "Local AI, speech recognition, and voice output are ready.", "LIVE")
        self._refresh_runtime_cards()
        self._init_tray()
        self._apply_affinity()

        self.hotkey_timer = QTimer(self)
        self.hotkey_timer.timeout.connect(self._poll_hotkeys)
        self.hotkey_timer.start(50)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(100)

    # ---------- dashboard construction ----------
    def _card(self, title, subtitle=None):
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(11, 9, 11, 10)
        layout.setSpacing(7)
        head = QHBoxLayout()
        label = QLabel(title.upper())
        label.setObjectName("eyebrow")
        head.addWidget(label)
        head.addStretch()
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("muted")
            head.addWidget(sub)
        layout.addLayout(head)
        return frame, layout

    def _metric_row(self, glyph, title, value, note="", tint=None):
        row = QFrame()
        row.setObjectName("metric")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(8, 5, 8, 5)
        lay.setSpacing(8)
        icon = QLabel(glyph)
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(27, 27)
        icon.setStyleSheet(f"background:{tint or '#123a52'};border-radius:7px;color:#e9fbff;font-size:14px;font-weight:700;")
        lay.addWidget(icon)
        col = QVBoxLayout()
        col.setSpacing(1)
        name = QLabel(title)
        name.setObjectName("value")
        val = QLabel(value)
        val.setObjectName("muted")
        if note:
            val.setToolTip(note)
        col.addWidget(name)
        col.addWidget(val)
        lay.addLayout(col, 1)
        return row, val

    def _build_sidebar(self):
        panel = QFrame()
        panel.setObjectName("sidebar")
        panel.setFixedWidth(196)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 14, 12, 12)
        lay.setSpacing(7)
        brand = QHBoxLayout()
        mark = QLabel("◉")
        mark.setStyleSheet("color:#28dff4;font-size:28px;font-weight:300;")
        brand.addWidget(mark)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        name = QLabel("TRILION")
        name.setObjectName("brand")
        sub = QLabel("COMMAND CENTER")
        sub.setObjectName("brandSub")
        brand_text.addWidget(name)
        brand_text.addWidget(sub)
        brand.addLayout(brand_text)
        lay.addLayout(brand)
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background:#17344b;border:0;")
        lay.addWidget(divider)
        self.nav_buttons = {}
        navs = [("⌂", "Command Center", "core"), ("◎", "AI Core", "core"),
                ("◈", "Agents", "agents"), ("▤", "Tasks", "activity"),
                ("♫", "Voice", "core"), ("▣", "Memory", "memory"),
                ("▧", "Conversations", "activity"), ("◇", "Skills", "llm"),
                ("⌘", "Tools & Skills", "llm"), ("⤢", "Quick Commands", "quick")]
        for glyph, title, target in navs:
            b = QPushButton(f"{glyph}    {title}")
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda checked=False, n=title, t=target: self._navigate(n, t))
            lay.addWidget(b)
            self.nav_buttons[title] = b
        self.nav_buttons["Command Center"].setChecked(True)
        lay.addStretch(1)

        voice_title = QLabel("VOICE STATUS")
        voice_title.setObjectName("eyebrow")
        lay.addWidget(voice_title)
        self.sidebar_state = QLabel("●  READY TO LISTEN")
        self.sidebar_state.setObjectName("muted")
        lay.addWidget(self.sidebar_state)
        self.sidebar_meter = LevelMeter()
        self.sidebar_meter.setFixedHeight(36)
        lay.addWidget(self.sidebar_meter)
        self.dev = QComboBox()
        self.dev.setToolTip("Select microphone input")
        self._fill_devices()
        self.dev.currentIndexChanged.connect(self._pick_dev)
        lay.addWidget(self.dev)
        self.b_talk = QPushButton("◉   START VOICE CHAT")
        self.b_talk.setCheckable(True)
        self.b_talk.setObjectName("primary")
        self.b_talk.toggled.connect(self._talk)
        lay.addWidget(self.b_talk)

        settings = QHBoxLayout()
        self.b_mic = self._toggle("MIC", True, "Enable or mute continuous microphone listening")
        self.b_watch = self._toggle("VISION", self.rt.cfg.get("watch_screen", True), "Attach a screenshot to requests")
        settings.addWidget(self.b_mic)
        settings.addWidget(self.b_watch)
        lay.addLayout(settings)
        safety = QHBoxLayout()
        self.b_conf = self._toggle("CONFIRM", self.rt.cfg.get("confirm_risky", True), "Ask before risky shell commands or file writes")
        self.b_wake = self._toggle("WAKE WORD", self.rt.cfg.get("wake_word", False), 'Only react after you say "Trilion"')
        safety.addWidget(self.b_conf)
        safety.addWidget(self.b_wake)
        lay.addLayout(safety)
        self.b_stop = QPushButton("■   STOP EVERYTHING")
        self.b_stop.clicked.connect(self._stop)
        lay.addWidget(self.b_stop)
        return panel

    def _build_header(self):
        bar = QFrame()
        bar.setObjectName("card")
        bar.setFixedHeight(55)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 5, 12, 5)
        self.system_status = QLabel("●  SYSTEM STATUS   OPTIMAL")
        self.system_status.setObjectName("state")
        lay.addWidget(self.system_status)
        lay.addStretch(1)
        clock_col = QVBoxLayout()
        clock_col.setSpacing(0)
        self.date_lbl = QLabel()
        self.date_lbl.setObjectName("muted")
        self.date_lbl.setAlignment(Qt.AlignCenter)
        self.clock_lbl = QLabel()
        self.clock_lbl.setObjectName("clock")
        self.clock_lbl.setAlignment(Qt.AlignCenter)
        clock_col.addWidget(self.date_lbl)
        clock_col.addWidget(self.clock_lbl)
        lay.addLayout(clock_col)
        lay.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("⌕  Search activity…")
        self.search.setFixedWidth(190)
        self.search.textChanged.connect(self._filter_feed)
        lay.addWidget(self.search)
        mode_label = QLabel("VISUAL MODE")
        mode_label.setObjectName("eyebrow")
        lay.addWidget(mode_label)
        self.mode = QComboBox()
        self.mode.addItems(list(THEMES))
        self.mode.currentTextChanged.connect(self._mode_changed)
        lay.addWidget(self.mode)
        operator = QLabel("OPERATOR  ◉")
        operator.setStyleSheet("background:#102a40;border:1px solid #244b65;border-radius:15px;padding:7px 10px;color:#dffaff;font-size:10px;font-weight:700;")
        lay.addWidget(operator)
        return bar

    def _build_dashboard(self):
        self.dash_grid.setColumnStretch(0, 13)
        self.dash_grid.setColumnStretch(1, 23)
        self.dash_grid.setColumnStretch(2, 13)
        self.dash_grid.setColumnStretch(3, 13)
        self.dash_grid.setRowStretch(0, 10)
        self.dash_grid.setRowStretch(1, 9)
        self.dash_grid.setRowStretch(2, 7)

        overview, ov = self._card("AI core overview", "LOCAL")
        self.overview_values = {}
        for glyph, title, value, key in [
            ("◎", "AI Core", "Online", "core"), ("▤", "Memory", "0 Stored", "memory"),
            ("◉", "Voice", "Ready", "voice"), ("◈", "Vision", "Enabled", "vision"),
            ("⌘", "Tools", "Available", "tools"), ("✦", "System", "Optimal", "system")]:
            row, val = self._metric_row(glyph, title, value)
            ov.addWidget(row)
            self.overview_values[key] = val
        self.dash_grid.addWidget(overview, 0, 0)
        self.nav_targets = {"overview": overview}

        core_card, core_lay = self._card("Trilion neural core", "3D • VOICE REACTIVE")
        self.orb = OrbCore()
        core_lay.addWidget(self.orb, 1)
        self.core_caption = QLabel("TRILION   /   LOCAL NEURAL ENGINE")
        self.core_caption.setObjectName("caption")
        self.core_caption.setAlignment(Qt.AlignCenter)
        core_lay.addWidget(self.core_caption)
        self.core_state = QLabel("IDLE  •  AWAITING INPUT")
        self.core_state.setObjectName("muted")
        self.core_state.setAlignment(Qt.AlignCenter)
        core_lay.addWidget(self.core_state)
        self.dash_grid.addWidget(core_card, 0, 1, 1, 2)
        self.nav_targets["core"] = core_card
        overview.setMinimumHeight(260)
        overview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        feed_card, feed_lay = self._card("Live intelligence feed", "LIVE")
        self.feed_list = QTextBrowser()
        self.feed_list.setMinimumHeight(215)
        self.feed_list.setMaximumHeight(255)
        feed_lay.addWidget(self.feed_list, 1)
        feed_all = QPushButton("VIEW ALL ACTIVITY  ›")
        feed_all.clicked.connect(lambda: self._navigate("Conversations", "activity"))
        feed_lay.addWidget(feed_all)
        self.dash_grid.addWidget(feed_card, 0, 3)

        agents_card, agents_lay = self._card("Active agents & systems", "LOCAL MODULES")
        modules = QGridLayout()
        modules.setSpacing(6)
        self.module_values = {}
        module_data = [("⌘", "Local AI Agent", "Running", "agent"), ("◎", "Vision Engine", "Ready", "vision"),
                       ("◉", "Voice Listener", "Online", "listener"), ("▤", "Memory Agent", "Ready", "memory"),
                       ("⚙", "Tool Executor", "Ready", "tools"), ("◌", "Safety Guard", "Enabled", "safety")]
        for i, (glyph, title, value, key) in enumerate(module_data):
            row, label = self._metric_row(glyph, title, value)
            modules.addWidget(row, i // 3, i % 3)
            self.module_values[key] = label
        agents_lay.addLayout(modules)
        self.dash_grid.addWidget(agents_card, 1, 0, 1, 2)
        self.nav_targets["agents"] = agents_card

        activity_card, activity_lay = self._card("Mission timeline", "SESSION")
        self.log = QTextBrowser()
        self.log.setMinimumHeight(145)
        activity_lay.addWidget(self.log, 1)
        self.dash_grid.addWidget(activity_card, 1, 2)
        self.nav_targets["activity"] = activity_card

        quick_card, quick_lay = self._card("Quick commands")
        self.quick_new = QPushButton("＋   Start a new task")
        self.quick_new.clicked.connect(self._focus_input)
        quick_lay.addWidget(self.quick_new)
        self.quick_voice = QPushButton("◉   Start voice chat")
        self.quick_voice.clicked.connect(lambda: self.b_talk.toggle())
        quick_lay.addWidget(self.quick_voice)
        quick_logs = QPushButton("▤   Open diagnostic logs")
        quick_logs.clicked.connect(self._open_logs)
        quick_lay.addWidget(quick_logs)
        quick_copy = QPushButton("⧉   Copy diagnostics")
        quick_copy.clicked.connect(self._copy_log)
        quick_lay.addWidget(quick_copy)
        quick_stop = QPushButton("■   Stop current action")
        quick_stop.clicked.connect(self._stop)
        quick_lay.addWidget(quick_stop)
        quick_lay.addStretch(1)
        self.dash_grid.addWidget(quick_card, 1, 3)
        self.nav_targets["quick"] = quick_card

        monitor_card, monitor_lay = self._card("System monitor", "CONFIGURED RUNTIME")
        self.runtime_bars = {}
        for key, label, value, maximum in [
            ("gpu", "GPU LAYERS", int(self.rt.cfg.get("gpu_layers", 99)), 99),
            ("context", "CONTEXT WINDOW", int(self.rt.cfg.get("context", 12288)), 16384),
            ("screen", "SCREEN CAPTURE WIDTH", int(self.rt.cfg.get("screen_max_width", 1280)), 1920)]:
            line = QHBoxLayout()
            txt = QLabel(label)
            txt.setObjectName("muted")
            val = QLabel(self._format_runtime(key, value))
            val.setObjectName("value")
            line.addWidget(txt)
            line.addStretch(1)
            line.addWidget(val)
            monitor_lay.addLayout(line)
            bar = QProgressBar()
            bar.setRange(0, maximum)
            bar.setValue(max(0, min(maximum, value)))
            bar.setTextVisible(False)
            monitor_lay.addWidget(bar)
            self.runtime_bars[key] = (bar, val)
        monitor_lay.addStretch(1)
        self.dash_grid.addWidget(monitor_card, 2, 0)

        memory_card, memory_lay = self._card("Memory insights", "LOCAL MEMORY")
        self.memory_count = QLabel("0")
        self.memory_count.setObjectName("clock")
        self.memory_count.setAlignment(Qt.AlignCenter)
        self.memory_count.setStyleSheet("font-size:26px;")
        memory_lay.addWidget(self.memory_count)
        self.memory_note = QLabel("STORED FACTS")
        self.memory_note.setObjectName("muted")
        self.memory_note.setAlignment(Qt.AlignCenter)
        memory_lay.addWidget(self.memory_note)
        self.turn_count = QLabel("SESSION TURNS   0")
        self.turn_count.setObjectName("value")
        self.turn_count.setAlignment(Qt.AlignCenter)
        memory_lay.addWidget(self.turn_count)
        memory_btn = QPushButton("OPEN MEMORY FOLDER  ›")
        memory_btn.clicked.connect(self._open_memory)
        memory_lay.addWidget(memory_btn)
        self.dash_grid.addWidget(memory_card, 2, 1)
        self.nav_targets["memory"] = memory_card

        llm_card, llm_lay = self._card("LLM & voice status", "LOCAL PROVIDERS")
        self.provider_values = {}
        provider_grid = QGridLayout()
        provider_grid.setSpacing(6)
        providers = [("◈", "LLM BRAIN", "Loading", "brain"), ("◉", "SPEECH TO TEXT", "Whisper", "stt"),
                     ("♫", "VOICE OUTPUT", "Kokoro", "tts"), ("⌂", "INFERENCE", "llama.cpp", "engine")]
        for i, (glyph, title, value, key) in enumerate(providers):
            row, val = self._metric_row(glyph, title, value)
            provider_grid.addWidget(row, i // 2, i % 2)
            self.provider_values[key] = val
        llm_lay.addLayout(provider_grid)
        llm_bottom = QLabel("PRIVATE BY DESIGN   •   ALL INFERENCE RUNS LOCALLY")
        llm_bottom.setObjectName("muted")
        llm_bottom.setAlignment(Qt.AlignCenter)
        llm_lay.addWidget(llm_bottom)
        self.dash_grid.addWidget(llm_card, 2, 2, 1, 2)
        self.nav_targets["llm"] = llm_card

    def _build_bottom_bar(self):
        dock = QFrame()
        dock.setObjectName("card")
        dock.setFixedHeight(66)
        lay = QHBoxLayout(dock)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(8)
        self.dock_local = self._dock_pill("⌂", "LOCAL ENGINE", "ONLINE")
        self.dock_vision = self._dock_pill("◎", "VISION", "ON" if self.rt.cfg.get("watch_screen", True) else "OFF")
        self.dock_voice = self._dock_pill("♫", "VOICE", self.rt.cfg.get("voice", "af_heart"))
        lay.addWidget(self.dock_local)
        lay.addWidget(self.dock_vision)
        lay.addWidget(self.dock_voice)
        lay.addStretch(1)
        self.bottom_caption = QLabel("TRILION IS READY")
        self.bottom_caption.setObjectName("muted")
        lay.addWidget(self.bottom_caption)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Send a command to Trilion…")
        self.input.setMinimumWidth(230)
        self.input.returnPressed.connect(self._send)
        lay.addWidget(self.input, 2)
        self.talk_bottom = QPushButton("◉  TALK TO TRILION")
        self.talk_bottom.setObjectName("primary")
        self.talk_bottom.clicked.connect(lambda: self.b_talk.toggle())
        lay.addWidget(self.talk_bottom)
        briefing = QPushButton("›  BRIEFING")
        briefing.clicked.connect(self._briefing)
        lay.addWidget(briefing)
        return dock

    def _dock_pill(self, glyph, name, value):
        pill = QFrame()
        pill.setObjectName("metric")
        l = QHBoxLayout(pill)
        l.setContentsMargins(8, 5, 8, 5)
        icon = QLabel(glyph)
        icon.setStyleSheet("color:#33dff2;font-size:15px;")
        l.addWidget(icon)
        col = QVBoxLayout()
        col.setSpacing(0)
        a = QLabel(name)
        a.setObjectName("eyebrow")
        b = QLabel(value)
        b.setObjectName("muted")
        col.addWidget(a)
        col.addWidget(b)
        l.addLayout(col)
        pill.value_label = b
        return pill

    # ---------- theme / navigation ----------
    def _apply_theme(self):
        colors = THEMES[self.theme_name]
        self.setStyleSheet(_qss(colors["accent"]))
        self.orb.set_palette(colors["accent"], colors["secondary"], colors["glow"])
        self.system_status.setStyleSheet(f"color:{colors['accent']};font-weight:750;letter-spacing:1px;")
        self.clock_lbl.setStyleSheet(f"color:{colors['accent']};font-size:19px;font-weight:700;")
        self.memory_count.setStyleSheet(f"color:{colors['accent']};font-size:26px;font-weight:700;")

    def _navigate(self, name, target):
        for key, button in self.nav_buttons.items():
            button.setChecked(key == name)
        widget = self.nav_targets.get(target)
        if widget is not None:
            self.scroll.ensureWidgetVisible(widget, 18, 18)
        self._push_feed("NAVIGATION", f"Dashboard focus: {name}.", "INFO")

    # ---------- runtime data / actions ----------
    def _wire_runtime(self):
        self.b_mic.toggled.connect(lambda v: setattr(self.assistant, "mic_enabled", v))
        self.b_watch.toggled.connect(lambda v: self._cfg("watch_screen", v))
        self.b_conf.toggled.connect(lambda v: self._cfg("confirm_risky", v))
        self.b_wake.toggled.connect(lambda v: self._cfg("wake_word", v))
        self.bridge.state.connect(self._on_state)
        self.bridge.mic_level.connect(self._on_mic_level)
        self.bridge.out_level.connect(self._on_out_level)
        self.bridge.caption.connect(self._on_caption)
        self.bridge.message.connect(self._on_message)
        self.bridge.confirm_req.connect(self._on_confirm)

    def _refresh_runtime_cards(self):
        memory = getattr(self.assistant, "memory", None)
        memories = len(getattr(memory, "items", []))
        turns = len(getattr(self.assistant, "history", [])) // 2
        self.overview_values["memory"].setText(f"{memories:,} stored")
        self.overview_values["voice"].setText("Listening" if self.assistant.mic_enabled else "Muted")
        self.overview_values["vision"].setText("Enabled" if self.rt.cfg.get("watch_screen", True) else "Disabled")
        self.overview_values["tools"].setText("Ready")
        self.overview_values["system"].setText("Optimal")
        self.module_values["vision"].setText("Enabled" if self.rt.cfg.get("watch_screen", True) else "Standby")
        self.module_values["listener"].setText("Listening" if self.assistant.mic_enabled else "Muted")
        self.module_values["memory"].setText(f"{memories:,} facts")
        self.module_values["safety"].setText("Confirm risky actions" if self.rt.cfg.get("confirm_risky", True) else "Critical checks active")
        self.memory_count.setText(f"{memories:,}")
        self.turn_count.setText(f"SESSION TURNS   {turns:,}")
        brain = getattr(self.rt.llm, "brain", {})
        self.provider_values["brain"].setText(brain.get("label", brain.get("key", "Local model")))
        self.provider_values["stt"].setText(self.rt.cfg.get("whisper_repo", "Whisper").split("/")[-1])
        self.provider_values["tts"].setText(f"Kokoro • {self.rt.cfg.get('voice', 'af_heart')}")
        self.provider_values["engine"].setText("llama.cpp • ONLINE")
        self.dock_vision.value_label.setText("ON" if self.rt.cfg.get("watch_screen", True) else "OFF")
        self.dock_voice.value_label.setText(self.rt.cfg.get("voice", "af_heart"))

    def _format_runtime(self, key, value):
        if key == "context":
            return f"{value / 1024:g}K TOKENS"
        if key == "screen":
            return f"{value:,} PX"
        return f"{value}/99"

    def _tick(self):
        now = datetime.now()
        self.date_lbl.setText(now.strftime("%A, %d %B %Y"))
        self.clock_lbl.setText(now.strftime("%I:%M:%S %p").lstrip("0"))
        self.orb.set_levels(self.mic_lvl, self.out_lvl)
        self.sidebar_meter.set_levels(self.mic_lvl, self.out_lvl, self.state)
        if self.state == "idle" and self.mic_lvl > 0.08:
            self.sidebar_state.setText("●  VOICE DETECTED")
        elif self.state == "idle":
            self.sidebar_state.setText("●  READY TO LISTEN" if self.assistant.mic_enabled else "●  MICROPHONE MUTED")
        if time.monotonic() - self._last_refresh >= 1.0:
            self._last_refresh = time.monotonic()
            self._refresh_runtime_cards()

    def _on_state(self, state):
        self.state = state
        self.orb.set_state(state)
        label = STATE_TEXT.get(state, state.upper())
        self.system_status.setText(f"●  SYSTEM STATUS   {label}")
        self.core_state.setText(f"{label}  •  VOICE REACTIVE CORE")
        self.sidebar_state.setText(f"●  {label}")
        self.bottom_caption.setText(f"TRILION  /  {label}")
        self._push_feed("CORE STATE", f"Neural core state changed to {label.lower()}.", "LIVE")

    def _on_mic_level(self, value):
        self.mic_lvl = value
        self.orb.set_levels(self.mic_lvl, self.out_lvl)

    def _on_out_level(self, value):
        self.out_lvl = value
        self.orb.set_levels(self.mic_lvl, self.out_lvl)

    def _on_caption(self, text):
        self.core_caption.setText(text if text else "TRILION   /   LOCAL NEURAL ENGINE")
        if text:
            self._push_feed("VOICE OUTPUT", text, "AUDIO")

    def _on_message(self, role, text):
        self._add(role, text)
        if role in ("user", "assistant", "action", "error"):
            self._push_feed(role.upper(), text, "WARN" if role == "error" else "LIVE")

    def _push_feed(self, title, body, tag="INFO"):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.feed_entries.insert(0, (stamp, title, body, tag))
        self.feed_entries = self.feed_entries[:30]
        self._filter_feed(self.search.text() if hasattr(self, "search") else "")

    def _filter_feed(self, query):
        q = (query or "").lower().strip()
        visible = [entry for entry in self.feed_entries if not q or q in " ".join(entry).lower()]
        pieces = []
        for stamp, title, body, tag in visible[:9]:
            safe_title = html.escape(title)
            safe_body = html.escape(body[:150])
            color = "#ffba62" if tag == "WARN" else "#42dbef" if tag in ("LIVE", "AUDIO", "MODE") else "#8da8c0"
            pieces.append(f'<p style="margin:4px 0 7px 0"><span style="color:{color};font-size:9px">● {stamp}  {tag}</span><br><b style="color:#dceeff">{safe_title}</b><br><span style="color:#91a9bf">{safe_body}</span></p>')
        self.feed_list.setHtml("<div>" + "".join(pieces) + "</div>")

    def _add(self, role, text):
        safe = html.escape(text).replace("\n", "<br>")
        if role == "user":
            fragment = f'<p style="margin:6px 0"><b style="color:#66e6f7">YOU</b> &nbsp;{safe}</p>'
        elif role == "assistant":
            fragment = f'<p style="margin:6px 0"><b style="color:#a58bff">TRILION</b> &nbsp;{safe}</p>'
        elif role == "heard":
            fragment = f'<p style="margin:3px 0;color:#839bb2"><i>{safe}</i></p>'
        elif role == "action":
            fragment = f'<p style="margin:3px 0;color:#72c5d3">▸ {safe}</p>'
        else:
            fragment = f'<p style="margin:4px 0;color:#ff9696">{safe}</p>'
        self.log.append(fragment)

    def _mode_changed(self, name):
        if name not in THEMES:
            return
        self.theme_name = name
        self._apply_theme()
        self._push_feed("VISUAL MODE", f"Dashboard palette changed to {name.title()}.", "MODE")

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
                    self.dev.addItem(d["name"], i)
                    if d["name"] == want:
                        pick = self.dev.count() - 1
        except Exception:
            pass
        self.dev.setCurrentIndex(pick)
        self.dev.blockSignals(False)

    def _pick_dev(self, _index):
        idx = self.dev.currentData()
        self._cfg("mic_device", self.dev.currentText() if idx is not None else None)
        try:
            self.rt.listener.set_device(idx)
            self._push_feed("AUDIO INPUT", f"Microphone changed to {self.dev.currentText()}.", "INFO")
        except Exception as exc:
            self._add("error", f"Could not open that microphone: {exc}")

    def _talk(self, on):
        self.b_talk.setText("◉   STOP & SEND" if on else "◉   START VOICE CHAT")
        self.talk_bottom.setText("◉  END VOICE CHAT" if on else "◉  TALK TO TRILION")
        if on:
            self.assistant.stop()
            self.rt.listener.begin_manual()
            self.core_state.setText("RECORDING  •  SPEAK NOW")
            self._push_feed("VOICE INPUT", "Manual recording started.", "AUDIO")
        else:
            self.rt.listener.end_manual()
            self._push_feed("VOICE INPUT", "Recording sent for transcription.", "AUDIO")

    def _toggle(self, text, checked, tip):
        b = QPushButton(text)
        b.setCheckable(True)
        b.setChecked(bool(checked))
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        return b

    def _cfg(self, key, value):
        self.rt.cfg[key] = value
        self.rt.cfg.save()
        self._refresh_runtime_cards()

    def _send(self):
        text = self.input.text().strip()
        if text:
            self.input.clear()
            self.assistant.submit_text(text)

    def _focus_input(self):
        self.input.setFocus()
        self.scroll.ensureWidgetVisible(self.input, 0, 0)

    def _briefing(self):
        self.assistant.submit_text("Give me a concise briefing of the current Trilion session, recent conversation, and what you can help me do next.")

    def _copy_log(self):
        from ..paths import collect_logs
        QApplication.clipboard().setText(collect_logs())
        self._add("heard", "Diagnostic log copied to the clipboard.")

    def _open_logs(self):
        from ..paths import open_logs_folder
        open_logs_folder()

    def _open_memory(self):
        from ..paths import app_dir
        try:
            os.startfile(str(app_dir()))
        except Exception as exc:
            self._add("error", f"Could not open the Trilion data folder: {exc}")

    def _stop(self):
        self.b_talk.setChecked(False)
        self.assistant.stop()
        self._push_feed("CONTROL", "Stop command sent to the assistant.", "WARN")

    def _on_confirm(self, question, handle):
        event, box = handle
        result = QMessageBox.question(self, "Trilion permission request", question,
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        box[0] = result == QMessageBox.Yes
        event.set()

    # ---------- tray / Windows integration ----------
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
        act_auto.toggled.connect(lambda value: set_autostart(value))
        act_tray = QAction("Close button hides to tray", menu, checkable=True)
        act_tray.setChecked(bool(self.rt.cfg.get("close_to_tray", False)))
        act_tray.toggled.connect(lambda value: self._cfg("close_to_tray", value))
        act_old = QAction("Use the lighter brain (Qwen2.5-VL 7B) - restart needed", menu, checkable=True)
        act_old.setChecked(self.rt.cfg.get("brain") == "qwen2.5-vl-7b")
        act_old.toggled.connect(lambda value: self._cfg("brain", "qwen2.5-vl-7b" if value else "qwen3.5-9b"))
        act_quit = QAction("Quit Trilion", menu)
        act_quit.triggered.connect(self._quit)
        for action in (act_show, act_talk, act_stop):
            menu.addAction(action)
        menu.addSeparator()
        for action in (act_auto, act_tray, act_old):
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray._menu = menu
        self.tray.activated.connect(lambda reason: self._show_front() if reason == QSystemTrayIcon.Trigger else None)
        if self.tray_ok:
            self.tray.show()

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
            down = lambda key: bool(ctypes.windll.user32.GetAsyncKeyState(key) & 0x8000)
        except Exception:
            self.hotkey_timer.stop()
            return
        combo = down(0x11) and down(0x12)
        talk, stop = combo and down(0x54), combo and down(0x53)
        if talk and not self._ht:
            self.b_talk.toggle()
        if stop and not self._hs:
            self._stop()
        self._ht, self._hs = talk, stop

    def _apply_affinity(self):
        try:
            import ctypes
            ctypes.windll.user32.SetWindowDisplayAffinity(int(self.winId()), 0x11)
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_affinity()

    def closeEvent(self, event):
        if self.rt.cfg.get("close_to_tray", False) and self.tray_ok and not self._quitting:
            self.hide()
            event.ignore()
            return
        try:
            self.assistant.stop()
            self.rt.listener.stop()
            self.rt.player.close()
            self.rt.llm.stop()
            self.tray.hide()
        finally:
            QApplication.quit()
            event.accept()


class LevelMeter(QWidget):
    """Small live bar meter for input/output audio."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mic = self.output = 0.0
        self.state = "idle"
        self.phase = 0.0
        self.setMinimumWidth(140)

    def set_levels(self, mic, output, state):
        self.mic, self.output, self.state = mic, output, state
        self.phase += 0.18
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        n = 32
        gap = 3
        bar_w = max(2, (w - gap * (n - 1)) / n)
        level = self.output if self.state == "speaking" else self.mic
        for i in range(n):
            wave = 0.12 + 0.88 * abs(math.sin(i * 0.42 + self.phase))
            amp = max(0.08, level * wave)
            bh = max(3, (h - 4) * amp)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(42, 216, 239, 100 + int(130 * amp)))
            x = i * (bar_w + gap)
            p.drawRoundedRect(int(x), int((h - bh) / 2), int(bar_w), int(bh), 2, 2)
        p.end()
