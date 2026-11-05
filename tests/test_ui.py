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


class Game:
    keys, buttons, last_move = {"w"}, set(), (5, -3)


class Tools:
    game_on, game_profile, game_window, game = False, "", "", Game()


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


# ------------------------------------------------------------------ overlay / recording / OBS integration
def test_overlay_toggle_masks_and_settings_stay_in_sync(win):
    from trilion.core import screen
    w, b, a, app = win
    assert not w.overlay.isVisible() and w._overlay_mask() is None
    w.set_overlay(True)
    app.processEvents()
    assert w.overlay.isVisible() and w.cfg["overlay_on"] is True and w.cb_overlay.isChecked()
    assert w._overlay_mask() is not None and w._overlay_mask() in screen.mask_rects()      # AI screenshots black it out
    w.set_overlay_locked(False)
    assert not w.overlay.locked and not w.cb_lock.isChecked() and w.act_unlock.isChecked()
    w.cycle_overlay_size()
    assert w.overlay.size_name == "full"
    w.set_overlay(False)
    assert not w.overlay.isVisible() and w._overlay_mask() is None and not w.act_overlay.isChecked()


def test_main_window_is_masked_only_when_it_is_shown_in_recordings(win):
    w, b, a, app = win
    assert w._main_mask() is None                         # default: hidden from recordings and screenshots
    w.set_show_in_recordings(True)
    assert w.cfg["show_in_recordings"] is True and w.cb_rec.isChecked()
    assert w._main_mask() is not None or os.name != "nt"  # real window rect is a Windows API; offscreen has none


def test_obs_source_starts_stops_and_streams_live_state(win):
    import json as _json
    import urllib.request
    w, b, a, app = win
    w.cfg["hud_port"] = 0
    w.set_web_hud(True)
    try:
        assert w.hud is not None and w.cb_web.isChecked() and w.url_lbl.text().startswith("http://127.0.0.1:")
        b.message.emit("action", 'open_app {"name": "discord"}')
        b.message.emit("result", "ok|open_app|Opened discord.")
        for _ in range(6):
            w._tick()
        data = _json.loads(urllib.request.urlopen(w.hud.url + "state").read())
        assert data["version"] and data["events"][-1] == {"k": "ok", "text": "open_app: discord"}
        assert data["game"] is None and any("open_app: discord" in t for t, _ in data["lines"]["full"])
    finally:
        w.set_web_hud(False)
    assert w.hud is None and w.url_lbl.text() == "(off)"


def test_hud_snapshot_reports_game_state(win):
    w, b, a, app = win
    a.tools.game_on, a.tools.game_profile = True, "minecraft"
    snap = w._hud_snapshot("acting", 0.3, [25, 211, 255])
    a.tools.game_on = False
    assert snap["game"] == {"on": True, "profile": "minecraft", "keys": ["w"], "buttons": [], "move": [5, -3]}
    assert snap["state"] == "acting" and snap["brain"] == "Qwen3.5 9B" and snap["color"] == [25, 211, 255]
