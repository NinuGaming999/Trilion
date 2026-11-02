import json
import os
import tempfile
import time

os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()

from trilion.core import agent as agent_mod  # noqa: E402
from trilion.core import screen  # noqa: E402
from trilion.core.tools import Tools, is_failure, reply_schema, tool_specs  # noqa: E402


def test_failure_detection():
    for bad in ("No control named 'x'. Run ui_list", "Blocked: you must not guess links",
                "run_shell failed: boom", "UI Automation is not available; use click",
                "Window 'Discord' does not expose its buttons (normal for Discord)",
                "The game window 'X' is not in front, so nothing was sent.", "Unknown tool 'zzz'."):
        assert is_failure(bad), bad
    for ok in ("Clicked (5,5).", "Opened notepad.", "Done.", "The user declined this action.", "exit 0\nfine"):
        assert not is_failure(ok), ok


def test_schema_can_exclude_disabled_tools():
    names = lambda sch: {v["properties"]["tool"]["const"] for v in sch["properties"]["action"]["anyOf"][1]["oneOf"]}
    full, cut = names(reply_schema()), names(reply_schema({"ui_click", "ui_type", "ui_list"}))
    assert {"ui_click", "ui_type", "ui_list"} <= full and not ({"ui_click", "ui_type", "ui_list"} & cut)
    assert {"click", "click_type"} <= cut
    assert tool_specs()["click_type"][1] == ["x", "y", "text"]


def test_click_type_clicks_then_types():
    t = Tools({"confirm_risky": False, "confirm_critical": False}, lambda q: True)
    calls = []
    t.t_click = lambda x, y, button="left", double=False: calls.append(("click", x, y))
    t.t_type_text = lambda text, enter=False: calls.append(("type", text, enter))
    assert "typed" in t.run({"tool": "click_type", "args": {"x": 500, "y": 900, "text": "hello", "enter": True}})
    assert calls == [("click", 500, 900), ("type", "hello", True)]


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
    cfg = {"watch_screen": True, "confirm_risky": False, "structured": True, "max_steps": 8, "screen_max_width": 1280}

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


def test_discord_case_ui_click_fails_twice_then_model_is_forced_to_use_coordinates(monkeypatch):
    monkeypatch.setattr(screen, "grab", lambda *a, **k: ("QQ==", (1280, 720)))
    rt = RT()
    rt.llm = LLM([
        j("I will click the message input bar.", "ui_click", name="Message #one-for-all", window="Ninu Gaming"),
        j("I will click the message input bar.", "ui_click", name="Message #one-for-all", window="Ninu"),
        j("Clicking the box directly.", "click_type", x=500, y=900, text="hi there", enter=True),
        j("I sent the message."),
    ])
    a = agent_mod.Assistant(rt, Bridge())
    ran = []

    def fake_run(act):
        ran.append(act["tool"])
        if act["tool"] == "ui_click":
            return "No control named 'Message #one-for-all'. Run ui_list or use the screenshot."
        return "Clicked (500,900) and typed."
    a.tools.run = fake_run
    a.submit_text("write hi there in the discord chat box")
    for _ in range(200):
        time.sleep(0.05)
        if not a.busy:
            break
    assert ran == ["ui_click", "ui_click", "click_type"]
    allowed = lambda kw: {v["properties"]["tool"]["const"] for v in kw["schema"]["properties"]["action"]["anyOf"][1]["oneOf"]}
    assert "ui_click" in allowed(rt.llm.calls[1][1])                    # still allowed after one failure
    assert "ui_click" not in allowed(rt.llm.calls[2][1])                # grammar no longer lets it choose ui_click
    assert "do not repeat" in rt.llm.calls[1][0][-1]["content"][0]["text"].lower()
    assert "disabled for this task: ui_click" in rt.llm.calls[2][0][-1]["content"][0]["text"].lower().replace("tools now ", "")


def test_app_without_controls_disables_ui_tools_immediately(monkeypatch):
    monkeypatch.setattr(screen, "grab", lambda *a, **k: ("QQ==", (1280, 720)))
    rt = RT()
    rt.llm = LLM([j("Let me list controls.", "ui_list", window="Discord"), j("Done.")])
    a = agent_mod.Assistant(rt, Bridge())
    a.tools.run = lambda act: "Window 'Discord' does not expose its buttons (normal for Discord, browsers). Use click."
    a.submit_text("look at the buttons in discord")
    for _ in range(200):
        time.sleep(0.05)
        if not a.busy:
            break
    names = {v["properties"]["tool"]["const"] for v in rt.llm.calls[1][1]["schema"]["properties"]["action"]["anyOf"][1]["oneOf"]}
    assert not ({"ui_list", "ui_click", "ui_type"} & names)
