import ctypes
import os
import tempfile
import threading
import time

os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()

import pytest  # noqa: E402

from trilion.core import agent as agent_mod  # noqa: E402
from trilion.core import gameinput as gi  # noqa: E402
from trilion.core import screen  # noqa: E402
from trilion.core.tools import Tools, tool_specs  # noqa: E402


def player(**kw):
    be = gi.RecordingBackend()
    return gi.GameInput(be, **kw), be


def kinds(be, name):
    return [e for e in be.events if e[1] == name]


def test_sendinput_structs_match_windows_layout():
    assert ctypes.sizeof(gi.INPUT) == 40           # x64 INPUT size SendInput requires
    assert ctypes.sizeof(gi.KEYBDINPUT) == 24 and ctypes.sizeof(gi.MOUSEINPUT) == 32


def test_scan_codes_and_aliases():
    assert gi.key_info("w") == (0x11, False) and gi.key_info("a") == (0x1E, False) and gi.key_info("Space") == (0x39, False)
    assert gi.key_info("up") == (0x48, True) and gi.key_info("shift") == (0x2A, False) and gi.key_info("F5") == (0x3F, False)
    assert gi.parse_keys("w, shift+space") == ["w", "lshift", "space"]
    with pytest.raises(ValueError):
        gi.parse_keys("w,banana")


def test_hold_releases_after_the_action():
    g, be = player()
    t = time.perf_counter()
    assert g.act(hold="w,shift", ms=120) is True
    assert time.perf_counter() - t >= 0.115
    downs = [e[2] for e in kinds(be, "key") if e[4]]
    ups = [e[2] for e in kinds(be, "key") if not e[4]]
    assert sorted(downs) == sorted(ups) == [0x11, 0x2A] and not g.keys


def test_keep_holds_across_actions_without_retyping():
    g, be = player()
    g.act(hold="w", ms=20, keep=True)
    assert "w" in g.keys
    g.act(hold="w,space", ms=20, keep=True)
    assert len([e for e in kinds(be, "key") if e[2] == 0x11 and e[4]]) == 1   # w pressed once, stayed down
    g.act(hold="", ms=10)                                                       # keys not listed are released
    assert not g.keys and len([e for e in kinds(be, "key") if e[2] == 0x11 and not e[4]]) == 1


def test_mouse_moves_exactly_the_requested_counts_smoothly():
    g, be = player()
    t = time.perf_counter()
    g.act(dx=100, dy=-37, ms=160)
    moves = kinds(be, "move")
    assert sum(m[2] for m in moves) == 100 and sum(m[3] for m in moves) == -37
    assert len(moves) >= 8 and max(abs(m[2]) for m in moves) <= 20             # spread out, not one jump
    assert time.perf_counter() - t >= 0.155
    g.act(dx=3, dy=0, ms=0)                                                     # tiny instant move still exact
    assert sum(m[2] for m in kinds(be, "move")) == 103


def test_tap_click_and_scroll():
    g, be = player()
    g.act(tap="e,1", click="right", scroll=-2, ms=10)
    assert [(e[2], e[4]) for e in kinds(be, "key")] == [(0x12, True), (0x12, False), (0x02, True), (0x02, False)]
    assert [(e[2], e[3]) for e in kinds(be, "button")] == [("right", True), ("right", False)]
    assert kinds(be, "wheel")[0][2] == -2
    with pytest.raises(ValueError):
        g.act(click="banana")


def test_stop_interrupts_and_releases():
    g, be = player()
    t = time.perf_counter()
    assert g.act(hold="w", dx=500, dy=0, ms=3000, stop=lambda: True) is False
    assert time.perf_counter() - t < 0.5 and not g.keys and not g.buttons


def test_deadman_timer_releases_forgotten_keys():
    g, be = player(deadman=0.15)
    g.act(hold="w", ms=10, keep=True)
    assert "w" in g.keys
    time.sleep(0.6)
    assert not g.keys and kinds(be, "key")[-1][4] is False


def test_click_at_uses_absolute_position():
    g, be = player()
    g.click_at(640, 360, "left", double=True)
    assert kinds(be, "abs")[0][2:] == (640, 360) and len(kinds(be, "button")) == 4


# ------------------------------------------------------------------ tool layer
def tools(confirm=lambda q: True, front="My Game", **cfg):
    t = Tools({"confirm_risky": False, **cfg}, confirm, cancelled=lambda: False)
    t.game_backend = gi.RecordingBackend()
    t._foreground_title = lambda: front
    t.t_focus_window = lambda title: "focused"
    return t


def test_game_tools_need_game_mode_and_consent():
    t = tools()
    assert "Game mode is off" in t.run({"tool": "game_act", "args": {"hold": "w"}})
    asked = []
    t2 = tools(confirm=lambda q: asked.append(q) or False)
    assert "declined" in t2.run({"tool": "game_mode", "args": {"on": True, "window": "My Game"}})
    assert not t2.game_on and "anti-cheat" in asked[0]


def test_game_act_only_sends_when_the_game_window_is_in_front():
    t = tools(front="Notepad")
    t.run({"tool": "game_mode", "args": {"on": True, "window": "My Game"}})
    assert "not in front" in t.run({"tool": "game_act", "args": {"hold": "w", "ms": 30}})
    assert t.game_backend.events == []                       # nothing leaked into the wrong window
    t._foreground_title = lambda: "My Game - v1.2"
    assert t.run({"tool": "game_act", "args": {"hold": "w", "ms": 30}}) == "Done."
    assert any(e[1] == "key" for e in t.game_backend.events)


def test_bad_keys_are_reported_not_crashed_and_mode_off_releases():
    t = tools()
    t.run({"tool": "game_mode", "args": {"on": True, "window": "My Game"}})
    assert "Bad input" in t.run({"tool": "game_act", "args": {"hold": "w,banana"}})
    t.game.act(hold="w", ms=5, keep=True)
    assert "off" in t.run({"tool": "game_mode", "args": {"on": False}}) and not t.game_on
    assert kinds(t.game_backend, "key")[-1][4] is False


def test_game_tools_are_in_the_strict_schema_and_docs():
    spec = tool_specs()["game_act"]
    assert spec[0]["ms"]["type"] == "number" and spec[0]["keep"]["type"] == "boolean" and spec[1] == []
    assert tool_specs()["game_mode"][0]["on"]["type"] == "boolean"


# ------------------------------------------------------------------ the agent playing
class Sig:
    def __init__(self):
        self.items = []

    def emit(self, *a):
        self.items.append(a)


class Bridge:
    def __init__(self):
        self.state, self.message, self.caption, self.mic_level, self.out_level = (Sig() for _ in range(5))

    def ask(self, q):
        return True


class LLM:
    structured_ok = True

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def chat_stream(self, messages, cancel=None, **kw):
        self.calls.append(messages)
        yield self.replies.pop(0)


class RT:
    cfg = {"watch_screen": True, "confirm_risky": False, "structured": True, "max_steps": 4, "screen_max_width": 1280}

    class tts:
        synth = staticmethod(lambda t: ([0.0] * 10, 24000))

    class player:
        play = staticmethod(lambda *a: None)
        busy = staticmethod(lambda: False)
        stop = staticmethod(lambda: None)

    class listener:
        gate = None
        on_utterance = None
    stt = None


def j(say, tool=None, **args):
    import json
    return json.dumps({"say": say, "action": {"tool": tool, "args": args} if tool else None})


def test_agent_plays_several_identical_steps_and_releases_on_stop(monkeypatch):
    monkeypatch.setattr(screen, "grab", lambda *a, **k: ("QQ==", (1280, 720)))
    rt = RT()
    rt.llm = LLM([j("Starting.", "game_mode", on=True, window="My Game"),
                  j("Forward.", "game_act", hold="w", ms=20, keep=True),
                  j("Forward.", "game_act", hold="w", ms=20, keep=True),
                  j("Forward.", "game_act", hold="w", ms=20, keep=True),
                  j("I walked ahead.")])
    a = agent_mod.Assistant(rt, Bridge())
    a.tools.game_backend = gi.RecordingBackend()
    a.tools._foreground_title = lambda: "My Game"
    a.tools.t_focus_window = lambda title: "focused"
    a.submit_text("start playing my game and walk forward")
    for _ in range(200):
        time.sleep(0.05)
        if not a.busy:
            break
    assert a.tools.game_on and len([c for c in rt.llm.calls]) == 5            # 3 identical game_act steps were allowed
    assert "GAME MODE IS ON" in rt.llm.calls[1][0]["content"] and "GAME MODE IS ON" not in rt.llm.calls[0][0]["content"]
    assert "w" in a.tools.game.keys                                            # keep=true: still held ...
    a.stop()                                                                   # ... until Stop (Ctrl+Alt+S)
    assert not a.tools.game.keys and kinds(a.tools.game_backend, "key")[-1][4] is False
