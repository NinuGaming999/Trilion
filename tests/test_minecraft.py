import json
import os
import tempfile
import time

os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()

import pytest  # noqa: E402

from trilion.core import agent as agent_mod  # noqa: E402
from trilion.core import gameinput as gi  # noqa: E402
from trilion.core import intents, minecraft, screen  # noqa: E402
from trilion.core.tools import Tools  # noqa: E402


def kinds(be, name):
    return [e for e in be.events if e[1] == name]


# ------------------------------------------------------------------ maths
def test_camera_maths():
    assert minecraft.deg_per_count(100) == pytest.approx(0.15)                  # default sensitivity
    assert minecraft.counts_for(90, -45, 100) == (600, -300)
    assert minecraft.counts_for(90, 0, 100, turn_scale=1.5) == (400, 0)         # camera over-turns -> fewer counts
    assert minecraft.deg_per_count(200) > minecraft.deg_per_count(100) > minecraft.deg_per_count(50)
    assert minecraft.aim_degrees(960, 540, 960, 540, 1080) == (0.0, 0.0)
    yaw, pitch = minecraft.aim_degrees(960 + 771.2, 540, 960, 540, 1080, 70)    # focal length at 1080p / 70 deg
    assert yaw == pytest.approx(45, abs=0.1) and pitch == 0
    assert minecraft.aim_degrees(960, 0, 960, 540, 1080)[1] < 0                  # target above centre -> look up (negative)


def test_walk_keys():
    assert minecraft.walk_keys("forward-left", sprint=True, jump=True) == ["w", "a", "ctrl", "space"]
    assert minecraft.walk_keys("back", sneak=True) == ["s", "shift"]
    with pytest.raises(ValueError):
        minecraft.walk_keys("sideways")


# ------------------------------------------------------------------ input layer
def test_hold_mouse_button_for_mining_and_release():
    be = gi.RecordingBackend()
    g = gi.GameInput(be)
    t = time.perf_counter()
    g.act(hold_click="left", ms=200)
    assert time.perf_counter() - t >= 0.19
    b = kinds(be, "button")
    assert [(e[2], e[3]) for e in b] == [("left", True), ("left", False)] and b[1][0] - b[0][0] >= 0.19
    g.act(hold_click="right", ms=10, keep=True)
    assert "right" in g.buttons
    g.act(hold_click="", ms=10)
    assert not g.buttons


def test_shift_click_order():
    be = gi.RecordingBackend()
    gi.GameInput(be).click_at(100, 200, "left", shift=True)
    seq = [(e[1], e[2:]) for e in be.events]
    assert seq[0] == ("key", (0x2A, False, True)) and seq[-1] == ("key", (0x2A, False, False))
    assert ("abs", (100, 200)) in seq


# ------------------------------------------------------------------ tools
def mc_tools(front="Minecraft 1.21 - Singleplayer", **cfg):
    t = Tools({"confirm_risky": False, **cfg}, lambda q: True, cancelled=lambda: False)
    t.game_backend = gi.RecordingBackend()
    t._foreground_title = lambda: front
    t.t_focus_window = lambda title: "focused"
    return t


def start(t):
    return t.run({"tool": "game_mode", "args": {"on": True, "window": "", "profile": "minecraft"}})


def test_mc_tools_need_minecraft_profile():
    t = mc_tools()
    t.run({"tool": "game_mode", "args": {"on": True, "window": "Some Game"}})
    assert "Minecraft mode is off" in t.run({"tool": "mc_look", "args": {"yaw": 10}})
    assert t.game_profile == "" and t.game_window == "Some Game"


def test_minecraft_profile_defaults_and_launcher_is_ignored():
    t = mc_tools(front="Minecraft Launcher")
    assert "Minecraft tools" in start(t)
    assert t.game_window == "Minecraft" and t.game_profile == "minecraft"
    assert "not in front" in t.run({"tool": "mc_mine", "args": {"ms": 300}})
    assert t.game_backend.events == []                                          # nothing sent to the launcher
    t._foreground_title = lambda: "Minecraft 1.21.4 - Singleplayer"
    assert t.run({"tool": "mc_mine", "args": {"ms": 300}}) == "Done."


def test_mc_look_turns_exact_degrees():
    t = mc_tools()
    start(t)
    assert "turned yaw 90.0" in t.run({"tool": "mc_look", "args": {"yaw": 90, "pitch": 0}})
    moves = kinds(t.game_backend, "move")
    assert sum(m[2] for m in moves) == 600 and sum(m[3] for m in moves) == 0
    t.game_backend.events.clear()
    t.run({"tool": "mc_look", "args": {"yaw": -30, "pitch": 15}})
    moves = kinds(t.game_backend, "move")
    assert (sum(m[2] for m in moves), sum(m[3] for m in moves)) == (-200, 100)


def test_mc_aim_converts_a_screen_point_to_camera_turn(monkeypatch):
    t = mc_tools()
    start(t)
    screen.LAST.update(scale=1.0, left=0, top=0, w=1920, h=1080)
    screen.COORD["mode"] = "pixel"
    t._game_rect = lambda: (0, 0, 1920, 1080)
    try:
        t.run({"tool": "mc_aim", "args": {"x": 960 + 771, "y": 540}})
        dx = sum(m[2] for m in kinds(t.game_backend, "move"))
        assert abs(dx - 300) <= 2                                                # 45 degrees = 300 counts
    finally:
        screen.LAST.update(w=0, h=0)


def test_mc_actions_press_the_right_inputs():
    t = mc_tools()
    start(t)
    t.run({"tool": "mc_walk", "args": {"dir": "forward", "ms": 150, "sprint": True}})
    assert sorted(e[2] for e in kinds(t.game_backend, "key") if e[4]) == sorted([0x11, 0x1D])
    t.run({"tool": "mc_hotbar", "args": {"slot": 3}})
    assert kinds(t.game_backend, "key")[-2][2] == 0x04                           # key "3"
    assert "Bad input" in t.run({"tool": "mc_hotbar", "args": {"slot": 12}})
    assert "Bad input" in t.run({"tool": "mc_walk", "args": {"dir": "sideways"}})
    n = len(t.game_backend.events)
    t.run({"tool": "mc_use", "args": {"ms": 300}})
    ev = t.game_backend.events[n:]
    assert [(e[2], e[3]) for e in ev if e[1] == "button"] == [("right", True), ("right", False)]
    t0 = time.perf_counter()
    t.run({"tool": "mc_attack", "args": {"times": 2}})
    assert time.perf_counter() - t0 >= 1.25                                      # cooldown respected
    t.run({"tool": "mc_inventory", "args": {}})
    assert kinds(t.game_backend, "key")[-2][2] == 0x12                           # "e"
    t.run({"tool": "mc_close", "args": {}})
    assert kinds(t.game_backend, "key")[-2][2] == 0x01                           # esc


def test_turn_scale_calibration_changes_future_turns():
    t = mc_tools()
    start(t)
    assert "1.333" in t.run({"tool": "mc_set_turn_scale", "args": {"requested": 90, "actual": 120}})
    t.game_backend.events.clear()
    t.run({"tool": "mc_look", "args": {"yaw": 90, "pitch": 0}})
    assert sum(m[2] for m in kinds(t.game_backend, "move")) == 450               # 600 / 1.333
    assert "Bad input" in t.run({"tool": "mc_set_turn_scale", "args": {"requested": 0, "actual": 5}})


# ------------------------------------------------------------------ intents
def test_minecraft_voice_commands():
    assert intents.match("play minecraft")[1] == {"tool": "game_mode", "args": {"on": True, "window": "Minecraft", "profile": "minecraft"}}
    assert intents.match("Trilion, start Minecraft for me")[1]["args"]["profile"] == "minecraft"
    assert intents.match("stop playing")[1] == {"tool": "game_mode", "args": {"on": False}}
    assert intents.match("play lofi")[1]["tool"] == "play_youtube"               # other "play ..." unchanged


# ------------------------------------------------------------------ the agent in Minecraft mode
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
        self.calls.append((messages, kw))
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
    return json.dumps({"say": say, "action": {"tool": tool, "args": args} if tool else None})


def test_agent_offers_minecraft_tools_only_after_minecraft_mode_starts(monkeypatch):
    monkeypatch.setattr(screen, "grab", lambda *a, **k: ("QQ==", (1280, 720)))
    rt = RT()
    rt.llm = LLM([j("Starting.", "game_mode", on=True, window="Minecraft", profile="minecraft"),
                  j("Turning.", "mc_look", yaw=30, pitch=0),
                  j("Mining.", "mc_mine", ms=400), j("Mining.", "mc_mine", ms=400), j("Mining.", "mc_mine", ms=400),
                  j("The block is gone.")])
    a = agent_mod.Assistant(rt, Bridge())
    a.tools.game_backend = gi.RecordingBackend()
    a.tools._foreground_title = lambda: "Minecraft 1.21 - Singleplayer"
    a.tools.t_focus_window = lambda title: "focused"
    a.submit_text("go and gather some wood in the game for me")
    for _ in range(300):
        time.sleep(0.05)
        if not a.busy:
            break
    names = lambda kw: {v["properties"]["tool"]["const"] for v in kw["schema"]["properties"]["action"]["anyOf"][1]["oneOf"]}
    assert not (minecraft.MC_TOOLS & names(rt.llm.calls[0][1]))                 # hidden before the mode is on
    assert minecraft.MC_TOOLS <= names(rt.llm.calls[1][1])                       # offered afterwards
    assert "MINECRAFT MODE" not in rt.llm.calls[0][0][0]["content"] and "MINECRAFT MODE" in rt.llm.calls[1][0][0]["content"]
    assert "mc_aim" in rt.llm.calls[1][0][0]["content"]
    assert len(rt.llm.calls) == 6                                               # 3 identical mc_mine steps were allowed
    assert sum(m[2] for m in kinds(a.tools.game_backend, "move")) == 200        # 30 degrees = 200 counts
    a.stop()
    assert not a.tools.game.keys and not a.tools.game.buttons
