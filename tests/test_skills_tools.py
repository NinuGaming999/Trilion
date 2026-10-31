import os
import tempfile

os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()

from trilion.core.memory import Memory  # noqa: E402
from trilion.core.skills import Skills, parse  # noqa: E402
from trilion.core.tools import Tools  # noqa: E402


class Cfg(dict):
    pass


def make():
    return Tools(Cfg(confirm_risky=False), lambda q: True, Skills(), Memory())


def test_builtin_skills_installed_and_listed():
    sk = Skills()
    names = {s["name"] for s in sk.all()}
    assert {"play-media", "research-topic", "operate-app", "learn-skill"} <= names
    assert "play-media:" in sk.prompt_block().replace("- ", "")


def test_create_and_use_skill():
    t = make()
    assert "Saved skill" in t.run({"tool": "create_skill", "args": {
        "name": "My Skill!", "description": "when x", "instructions": "1. do it"}})
    assert "1. do it" in t.run({"tool": "use_skill", "args": {"name": "my-skill"}})
    assert "No skill" in t.run({"tool": "use_skill", "args": {"name": "nope"}})


def test_script_path_cannot_escape():
    sk = Skills()
    try:
        sk.script_path("play-media", "../../config.json")
        assert False
    except FileNotFoundError:
        pass


def test_link_guard():
    t = make()
    assert "Blocked" in t.run({"tool": "open_url", "args": {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}})
    t.note_text("please open https://example.com/page?id=3 for me")
    assert t._url_ok("https://example.com/page?id=3")
    assert t._url_ok("https://www.youtube.com/")        # front pages are fine
    assert not t._url_ok("https://evil.example/x")


def test_memory():
    t = make()
    assert "Remembered" in t.run({"tool": "remember", "args": {"fact": "City is Dhaka"}})
    assert "Dhaka" in t.memory.prompt_block()
    assert "Forgot 1" in t.run({"tool": "forget", "args": {"fact": "dhaka"}})


def test_unknown_tool_and_bad_args():
    t = make()
    assert "Unknown tool" in t.run({"tool": "nope"})
    assert "Bad arguments" in t.run({"tool": "wait", "args": {"bogus": 1}})


def test_parse_frontmatter():
    meta, body = parse("---\nname: a\ndescription: b c\n---\nhello")
    assert meta == {"name": "a", "description": "b c"} and body == "hello"
