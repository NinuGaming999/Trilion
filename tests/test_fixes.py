import os
import tempfile

os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()

from trilion.core import intents  # noqa: E402
from trilion.core.agent import Streamer, parse_actions, strip_actions  # noqa: E402


def test_parse_sloppy_forms():
    assert parse_actions('Sure. <action>{"tool": "open_app", "args": {"name": "notepad"}}</action>')[0]["args"]["name"] == "notepad"
    assert parse_actions('```json\n{"tool": "open_app", "args": {"name": "calc"}}\n```')[0]["tool"] == "open_app"
    assert parse_actions('{"tool": "open_app", "name": "paint"}')[0]["args"] == {"name": "paint"}
    assert parse_actions("open app notepad")[0] == {"tool": "open_app", "args": {"name": "notepad"}}
    assert parse_actions('open_app(name="notepad")')[0]["args"]["name"] == "notepad"
    assert parse_actions("I will look at the screen and wait.") == []


def test_speech_never_reads_commands():
    assert strip_actions("open app notepad") == ""
    assert strip_actions("Opening it. ```json\n{\"tool\":\"look\"}\n```") == "Opening it."
    out = []
    s = Streamer(out.append)
    for d in ["Let me look at it. ", "open_app notepad. ", "Done now."]:
        s.feed(d)
    s.finish()
    spoken = " ".join(out)
    assert "open_app" not in spoken and "look at it" in spoken and "Done now." in spoken


def test_quick_intents():
    sp, a = intents.match("Open Notepad")
    assert a == {"tool": "open_app", "args": {"name": "notepad"}}
    assert intents.match("trilion, please open the calculator")[1]["args"]["name"] == "calc"
    assert intents.match("open youtube")[1] == {"tool": "open_url", "args": {"url": "https://www.youtube.com"}}
    assert intents.match("open github.com")[1]["tool"] == "open_url"
    assert intents.match("play lofi hip hop")[1] == {"tool": "play_youtube", "args": {"query": "lofi hip hop"}}
    assert intents.match("search for best gpu on google")[1]["args"] == {"site": "google", "query": "best gpu"}
    assert intents.match("volume up")[1]["args"]["keys"] == "volumeup"
    assert intents.match("what time is it")[1] is None and "It is" in intents.match("what time is it")[0]


def test_vague_requests_go_to_the_model():
    for t in ("open a video", "open it", "open something for me", "tell me a joke",
              "open the settings of my network adapter and change it"):
        assert intents.match(t) is None, t
