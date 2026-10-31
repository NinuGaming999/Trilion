import os
import tempfile
import time

os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()

from trilion.core import agent as agent_mod  # noqa: E402
from trilion.core import screen  # noqa: E402


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


class FakeLLM:
    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    def chat_stream(self, messages, cancel=None, **kw):
        self.seen.append(messages)
        text = self.replies.pop(0)
        for i in range(0, len(text), 7):
            yield text[i:i + 7]


class FakeTTS:
    def synth(self, text):
        return [0.0] * 100, 24000


class FakePlayer:
    def play(self, *a):
        pass

    def busy(self):
        return False

    def stop(self):
        pass


class Listener:
    gate = None
    on_utterance = None


class RT:
    cfg = {"watch_screen": True, "confirm_risky": False, "max_steps": 6, "screen_max_width": 1280}
    tts, player, listener = FakeTTS(), FakePlayer(), Listener()
    stt = None


def test_full_turn_with_skill_and_memory(monkeypatch):
    monkeypatch.setattr(screen, "grab", lambda *a, **k: ("QUJD", (1280, 720)))
    rt = RT()
    rt.llm = FakeLLM([
        'Let me check how. <action>{"tool": "use_skill", "args": {"name": "play-media"}}</action>',
        'Noted. <action>{"tool": "remember", "args": {"fact": "User likes lofi"}}</action>',
        "All set, I will play it carefully.",
    ])
    b = Bridge()
    a = agent_mod.Assistant(rt, b)
    a.submit_text("I would like to listen to something relaxing")
    for _ in range(100):
        time.sleep(0.05)
        if not a.busy:
            break
    assert not a.busy
    roles = [m[0] for m in b.message.items]
    assert roles.count("action") == 2 and "assistant" in roles
    # the skill list and the loaded skill reached the model
    assert "play-media" in rt.llm.seen[0][0]["content"]
    assert any("play_youtube" in str(m["content"]) for m in rt.llm.seen[1])
    assert "lofi" in a.memory.prompt_block()
    # memory is injected on later turns
    assert "User likes lofi" in rt.llm.seen[2][0]["content"]


def test_open_notepad_runs_instantly_without_the_model(monkeypatch):
    monkeypatch.setattr(screen, "grab", lambda *a, **k: ("QUJD", (1280, 720)))
    rt = RT()
    rt.llm = FakeLLM([])          # would raise if the model were asked
    b = Bridge()
    a = agent_mod.Assistant(rt, b)
    ran = []
    a.tools.run = lambda act: ran.append(act) or "Opened notepad."
    a.submit_text("open notepad")
    for _ in range(100):
        time.sleep(0.05)
        if not a.busy:
            break
    assert ran == [{"tool": "open_app", "args": {"name": "notepad"}}]
    assert rt.llm.seen == []
    assert ("assistant", "Opening notepad.") in b.message.items


def test_repeated_action_loop_is_stopped(monkeypatch):
    monkeypatch.setattr(screen, "grab", lambda *a, **k: ("QUJD", (1280, 720)))
    rt = RT()
    same = 'Doing it. <action>{"tool": "open_app", "args": {"name": "notepad"}}</action>'
    rt.llm = FakeLLM([same] * 8)
    b = Bridge()
    a = agent_mod.Assistant(rt, b)
    ran = []
    a.tools.run = lambda act: ran.append(act) or "Opened notepad."
    a.submit_text("tell me about the weather somehow")
    for _ in range(100):
        time.sleep(0.05)
        if not a.busy:
            break
    assert len(ran) == 1                      # ran once, the repeat was refused
    assert len(rt.llm.seen) == 2              # and the loop ended on the second reply


def test_system_prompt_has_no_copyable_open_notepad_example():
    assert "open notepad" not in agent_mod.SYSTEM.lower()
    assert "do NOT use any tool" in agent_mod.SYSTEM


def test_tool_docs_have_no_copyable_app_examples():
    from trilion.core.tools import TOOL_DOCS
    assert "notepad" not in TOOL_DOCS.lower()
