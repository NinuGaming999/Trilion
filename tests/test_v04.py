import json
import os
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()

import pytest  # noqa: E402

from trilion import paths  # noqa: E402
from trilion.core import agent as agent_mod  # noqa: E402
from trilion.core import calibrate, screen  # noqa: E402
from trilion.core.llama import LlamaServer, pick_files, strip_think  # noqa: E402
from trilion.core.tools import Tools, reply_schema, tool_specs  # noqa: E402


# ---------------------------------------------------------------- brains / config
def test_brain_presets_and_migration(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    d = tmp_path / "Trilion"
    d.mkdir()
    (d / "config.json").write_text(json.dumps({"config_version": 2, "llm_repo": "x/y", "llm_quant": "Q4_K_M",
                                               "watch_screen": False, "mic_device": "USB mic"}))
    cfg = paths.Config()
    assert cfg["brain"] == "qwen3.5-9b" and "llm_repo" not in cfg and cfg["config_version"] == 3
    assert cfg["watch_screen"] is False and cfg["mic_device"] == "USB mic"   # user's own settings survive
    assert paths.brain_info({"brain": "nonsense"})["key"] == "qwen3.5-9b"
    assert paths.brain_info({"brain": "qwen3.5-9b", "llm_quant_override": "Q4_K_M"})["quant"] == "Q4_K_M"


def test_pick_files_prefers_plain_quant_and_right_projector():
    names = ["Qwen3.5-9B-UD-Q6_K_XL.gguf", "Qwen3.5-9B-Q6_K.gguf", "Qwen3.5-9B-Q8_0.gguf",
             "mmproj-BF16.gguf", "mmproj-F16.gguf", "README.md"]
    pref = paths.BRAINS["qwen3.5-9b"]["mm_pref"]
    assert pick_files(names, "Q6_K", pref) == ("Qwen3.5-9B-Q6_K.gguf", "mmproj-F16.gguf")
    old = ["Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf", "mmproj-Qwen2.5-VL-7B-Instruct-Q8_0.gguf",
           "mmproj-Qwen2.5-VL-7B-Instruct-f16.gguf"]
    assert pick_files(old, "Q4_K_M", paths.BRAINS["qwen2.5-vl-7b"]["mm_pref"])[1].endswith("Q8_0.gguf")


def test_each_brain_gets_its_own_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    new = LlamaServer({"brain": "qwen3.5-9b", "context": 8192, "gpu_layers": 99})
    old = LlamaServer({"brain": "qwen2.5-vl-7b", "context": 8192, "gpu_layers": 99})
    assert new.model_dir.name == "qwen3.5-9b" and old.model_dir.name == "llm"   # old files stay where they were


def test_launch_flags_and_retry_variants(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    s = LlamaServer({"brain": "qwen3.5-9b", "context": 12288, "gpu_layers": 99})
    full = s.build_cmd("srv", "m.gguf", "mm.gguf", 1234)
    assert "--reasoning-budget" in full and "enable_thinking" in " ".join(full) and "12288" in full
    s.variant = 1
    assert "--reasoning-budget" not in s.build_cmd("srv", "m", "mm", 1)
    s.variant = 2
    low = s.build_cmd("srv", "m", "mm", 1)
    assert "--no-mmproj-offload" in low and "6144" in low


# ---------------------------------------------------------------- streaming helpers
def test_strip_think_across_chunk_boundaries():
    chunks = ["Hello <thi", "nk>secret plan</th", "ink> world", "!"]
    assert "".join(strip_think(iter(chunks))) == "Hello  world!"
    assert "".join(strip_think(iter(["no tags ", "here <b>bold</b>"]))) == "no tags here <b>bold</b>"


def test_say_extractor_streams_only_the_spoken_text():
    ex, spoken = agent_mod.SayExtractor(), ""
    reply = '{"say": "Opening it. \\"Now\\" \\u00e9", "action": {"tool": "look", "args": {}}}'
    for i in range(0, len(reply), 3):
        spoken += ex.feed(reply[i:i + 3])
    assert spoken == 'Opening it. "Now" é'


def test_parse_structured():
    say, acts = agent_mod.parse_structured('{"say":"On it.","action":{"tool":"ui_click","args":{"id":3}}}')
    assert say == "On it." and acts == [{"tool": "ui_click", "args": {"id": 3}}]
    assert agent_mod.parse_structured('{"say":"Hi","action":null}') == ("Hi", [])
    say, acts = agent_mod.parse_structured('Sure. <action>{"tool": "look", "args": {}}</action>')   # old style still works
    assert acts[0]["tool"] == "look"


def test_prompt_variants():
    j = agent_mod.build_system(True, "norm1000")
    t = agent_mod.build_system(False, "pixel")
    assert "Reply ONLY with a JSON object" in j and "0 to 1000" in j and "<action>" not in j
    assert "<action>" in t and "pixels in the screenshot" in t
    for p in (j, t):
        assert "notepad" not in p.lower()


# ---------------------------------------------------------------- tools
def test_schema_covers_every_tool_and_requires_the_right_args():
    specs = tool_specs()
    assert {"open_app", "ui_click", "ui_list", "click", "look", "run_shell", "play_youtube"} <= set(specs)
    assert specs["open_app"][1] == ["name"] and specs["look"] == ({}, [])
    assert specs["ui_click"][0]["id"]["type"] == "integer" and specs["click"][0]["x"]["type"] == "number"
    sch = reply_schema()
    variants = sch["properties"]["action"]["anyOf"][1]["oneOf"]
    assert len(variants) == len(specs) and all(v["properties"]["tool"]["const"] in specs for v in variants)
    assert sch["required"] == ["say", "action"]
    # every tool mentioned in the docs exists
    from trilion.core.tools import TOOL_DOCS
    for name in specs:
        assert name in TOOL_DOCS, f"{name} missing from TOOL_DOCS"


class Gui:
    def __init__(self):
        self.calls = []

    def click(self, *a, **k):
        self.calls.append(("click", a, k))


def make_tools(confirm=lambda q: True, **cfg):
    t = Tools({"confirm_risky": False, **cfg}, confirm)
    t.gui = Gui()
    t._gui = lambda: t.gui
    return t


def test_ui_ids_click_the_right_control():
    t = make_tools()
    t._ui_map = {1: (100, 200, "Save", "ButtonControl"), 2: (300, 400, "Cancel", "ButtonControl")}
    assert "Clicked Button 'Cancel'" in t.run({"tool": "ui_click", "args": {"id": 2}})
    assert t.gui.calls[0][1] == (300, 400)
    assert "No control with id 9" in t.run({"tool": "ui_click", "args": {"id": 9}})


def test_critical_clicks_always_ask_even_when_risky_confirm_is_off():
    asked = []
    t = make_tools(confirm=lambda q: asked.append(q) or False)
    t._ui_map = {1: (1, 1, "Delete all files", "ButtonControl"), 2: (2, 2, "Open", "ButtonControl")}
    assert "declined" in t.run({"tool": "ui_click", "args": {"id": 1}})
    assert t.gui.calls == [] and "Delete all files" in asked[0]
    assert "Clicked" in t.run({"tool": "ui_click", "args": {"id": 2}})          # harmless click: no question
    assert "declined" in t.run({"tool": "press_keys", "args": {"keys": "Alt+F4"}})
    t2 = make_tools(confirm=lambda q: False, confirm_critical=False)
    t2._ui_map = {1: (1, 1, "Pay now", "ButtonControl")}
    assert "Clicked" in t2.run({"tool": "ui_click", "args": {"id": 1}})        # explicit opt-out


# ---------------------------------------------------------------- screen / calibration
def test_coordinate_modes_map_to_real_pixels():
    screen.LAST.update(scale=0.5, left=100, top=50, w=1280, h=720)   # screenshot is half-size of a 2560x1440 screen
    try:
        screen.COORD["mode"] = "pixel"
        assert screen.to_screen(640, 360) == (100 + 1280, 50 + 720)
        screen.COORD["mode"] = "norm1000"
        assert screen.to_screen(500, 500) == (100 + 1280, 50 + 720)
        screen.COORD["mode"] = "unit"
        assert screen.to_screen(0.5, 0.5) == (100 + 1280, 50 + 720)
    finally:
        screen.COORD["mode"] = "pixel"
        screen.LAST.update(scale=1.0, left=0, top=0)


def test_screen_changed():
    a, b = bytes([10] * 576), bytes([10] * 576)
    assert screen.screen_changed(a, b) is False
    assert screen.screen_changed(a, bytes([90] * 576)) is True
    assert screen.screen_changed(None, b) is None


def test_calibration_decision():
    assert calibrate.decide(960, 200) == "pixel"
    assert calibrate.decide(750, 278) == "norm1000"
    assert calibrate.decide(0.75, 0.278) == "unit"
    assert calibrate.decide(100, 900) is None
    assert len(calibrate.make_test_image()) > 100


# ---------------------------------------------------------------- fake llama-server end to end
class Fake(BaseHTTPRequestHandler):
    reject_schema = False
    reply = ""
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.seen.append(body)
        if "response_format" in body and Fake.reject_schema:
            self.send_response(400)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        text = Fake.reply
        for i in range(0, len(text), 5):
            chunk = {"choices": [{"delta": {"content": text[i:i + 5]}}]}
            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
        self.wfile.write(b"data: [DONE]\n\n")


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    httpd = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    llm = LlamaServer({"brain": "qwen3.5-9b", "context": 8192, "gpu_layers": 99})
    llm.port = httpd.server_address[1]
    Fake.reject_schema, Fake.seen = False, []
    yield llm
    httpd.shutdown()


def test_chat_stream_sends_schema_disables_thinking_and_strips_think(server):
    Fake.reply = '<think>hmm</think>{"say":"Hi","action":null}'
    out = "".join(server.chat_stream([{"role": "user", "content": "hi"}], schema=reply_schema()))
    assert out == '{"say":"Hi","action":null}'
    body = Fake.seen[0]
    assert body["response_format"]["type"] == "json_schema"
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["top_k"] == 20 and body["stream"] is True


def test_structured_output_falls_back_when_the_server_rejects_the_schema(server):
    Fake.reject_schema, Fake.reply = True, "plain answer"
    out = "".join(server.chat_stream([{"role": "user", "content": "hi"}], schema=reply_schema()))
    assert out == "plain answer" and server.structured_ok is False
    assert "response_format" not in Fake.seen[-1]
    Fake.seen.clear()
    "".join(server.chat_stream([{"role": "user", "content": "again"}], schema=reply_schema()))
    assert "response_format" not in Fake.seen[0]            # stays off afterwards


def test_calibration_end_to_end_with_fake_model(server):
    Fake.reply = '{"x": 751, "y": 280}'
    assert calibrate.calibrate(server) == "norm1000"


# ---------------------------------------------------------------- the agent loop in JSON mode
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


class ScriptedLLM:
    structured_ok = True

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def chat_stream(self, messages, cancel=None, **kw):
        self.calls.append((messages, kw))
        text = self.replies.pop(0)
        for i in range(0, len(text), 6):
            yield text[i:i + 6]


class RT:
    cfg = {"watch_screen": True, "confirm_risky": False, "structured": True, "max_steps": 6, "screen_max_width": 1280}

    class tts:
        @staticmethod
        def synth(t):
            return [0.0] * 10, 24000

    class player:
        play = staticmethod(lambda *a: None)
        busy = staticmethod(lambda: False)
        stop = staticmethod(lambda: None)

    class listener:
        gate = None
        on_utterance = None
    stt = None


def test_json_mode_turn_speaks_say_runs_action_and_reflects_on_unchanged_screen(monkeypatch):
    shots = iter([("QQ==", (1280, 720))] * 10)
    monkeypatch.setattr(screen, "grab", lambda *a, **k: (screen.LAST.update(thumb=bytes([5] * 576)) or next(shots)))
    rt = RT()
    rt.llm = ScriptedLLM([
        '{"say": "Clicking it now.", "action": {"tool": "ui_click", "args": {"id": 4}}}',
        '{"say": "Done.", "action": null}',
    ])
    b = Bridge()
    a = agent_mod.Assistant(rt, b)
    ran = []
    a.tools.run = lambda act: ran.append(act) or "Clicked Button 'OK'."
    a.submit_text("please press the OK button in the dialog")
    for _ in range(100):
        time.sleep(0.05)
        if not a.busy:
            break
    assert ran == [{"tool": "ui_click", "args": {"id": 4}}]
    assert ("assistant", "Clicking it now.") in b.message.items and ("assistant", "Done.") in b.message.items
    assert all("schema" in kw for _, kw in rt.llm.calls)                     # grammar requested every step
    second = rt.llm.calls[1][0][-1]["content"]
    assert "did not change" in second[0]["text"]                              # reflection note reached the model
    assert "Reply ONLY with a JSON object" in rt.llm.calls[0][0][0]["content"]
