import math
import os
import sys
import tempfile
import types

os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6.QtWidgets")  # CI installs no Qt; this runs on developer machines


class Cfg(dict):
    def save(self):
        pass


class Listener:
    manual, manual_buf = False, []
    calls = []

    def begin_manual(self):
        self.manual = True
        self.calls.append("begin")

    def end_manual(self):
        self.manual = False
        self.calls.append("end")

    def set_device(self, n):
        pass

    def stop(self):
        pass


class Skills:
    def all(self):
        return [{"name": n, "description": "d"} for n in "abc"]


class Mem:
    items = [{"fact": "City is Dhaka"}]

    def forget(self, t):
        return "ok"


class Tools:
    game_on, game_profile, game_window = False, "", ""


class Assistant:
    mic_enabled, skills, memory, tools = True, Skills(), Mem(), Tools()
    sent, stopped = [], 0

    def stop(self):
        self.stopped += 1

    def submit_text(self, t):
        self.sent.append(t)


class LLM:
    brain = {"label": "Qwen3.5 9B (recommended)", "repo": "r", "quant": "Q6_K"}
    structured_ok = True


class RT:
    cfg = Cfg(watch_screen=True, confirm_risky=True, confirm_critical=True, wake_word=False, structured=True,
              coord_mode="norm1000", whisper_repo="Systran/faster-whisper-small", voice="af_heart",
              brain="qwen3.5-9b", mic_device=None, context=12288, screen_max_width=1280)
    listener, llm, warnings = Listener(), LLM(), ["Boot warning: mic was silent"]


@pytest.fixture
def win(monkeypatch):
    sd = types.ModuleType("sounddevice")
    sd.default = types.SimpleNamespace(hostapi=0)
    sd.query_hostapis = lambda i: {"devices": [0]}
    sd.query_devices = lambda i: {"name": "USB Mic", "max_input_channels": 1}
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from trilion.core.bridge import Bridge
    from trilion.ui.main_window import MainWindow
    b = Bridge()
    a = Assistant()
    a.sent, a.stopped = [], 0
    w = MainWindow(RT(), a, b)
    w.resize(1360, 860)
    w.show()
    app.processEvents()
    yield w, b, a, app
    w.hotkey_timer.stop()
    w.anim.stop()
    w.slow.stop()


def test_every_page_opens_and_renders(win):
    w, b, a, app = win
    for key in w.pages:
        w._goto(key)
        app.processEvents()
        assert w.grab().width() == 1360
    assert w.nav["skills"].badge == 3


def test_events_fill_feed_timeline_and_counters(win):
    w, b, a, app = win
    b.message.emit("user", "open the calculator")
    b.message.emit("action", 'open_app {"name": "calc"}')
    b.message.emit("result", "ok|open_app|Opened calc.")
    b.message.emit("action", 'ui_click {"id": 3}')
    b.message.emit("result", "fail|ui_click|No control with id 3")
    b.message.emit("error", "Something broke")
    assert (w.turns, w.tool_calls, w.warnings) == (1, 2, 2)           # boot warning + error
    assert [i["status"] for i in w.timeline.items] == ["failed", "done"]
    assert w.timeline.items[1]["label"] == "open_app: calc"
    assert len(w.feed.rows) >= 6 and "Opened" not in w.feed.rows[0].text
    w.search.setText("calculator")
    assert [r.isVisible() for r in w.feed.rows if "calculator" in r.text.lower()] == [True]
    assert not any(r.isVisible() for r in w.feed.rows if "calculator" not in r.text.lower())


def test_talk_toggle_stop_and_quick_commands(win):
    w, b, a, app = win
    w.set_talking(True)
    assert w.talking and RT.listener.manual and a.stopped == 1
    w._stop()                                       # Stop discards the recording instead of sending it
    assert not w.talking and not RT.listener.manual and RT.listener.manual_buf == []
    w.input.setText("hello there")
    w._send(w.input)
    assert a.sent == ["hello there"] and w.input.text() == ""
    w.brief.click()
    assert "daily briefing" in a.sent[-1].lower()


def test_agent_cards_follow_state_and_focus_mode(win):
    w, b, a, app = win
    b.state.emit("speaking")
    assert w.agents["voice"].active and not w.agents["brain"].active
    b.state.emit("thinking")
    assert w.agents["brain"].active and w.agents["eyes"].active
    b.state.emit("idle")
    assert not any(c.active for k, c in w.agents.items() if k in ("brain", "voice", "hands"))
    w._toggle_focus()
    assert w.sidebar.isHidden() and w.ov.isHidden()
    w._toggle_focus()
    assert not w.sidebar.isHidden()


def test_settings_write_config_and_short_action_labels(win):
    w, b, a, app = win
    w._cfg("watch_screen", False)
    assert w.cfg["watch_screen"] is False
    assert w._short_action('click_type {"x": 5, "y": 6, "text": "hi", "enter": false}') == "click_type: 5, 6, hi"
    assert w._short_action("look") == "look"
