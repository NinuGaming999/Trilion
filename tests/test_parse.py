from trilion.core.agent import Streamer, parse_actions, strip_actions


def test_actions():
    t = 'Opening it. <action>{"tool": "open_app", "args": {"name": "notepad"}}</action>'
    assert parse_actions(t)[0]["tool"] == "open_app"
    assert strip_actions(t) == "Opening it."


def test_streamer_hides_actions():
    out = []
    s = Streamer(out.append)
    for d in ["Sure. Open", "ing now. <act", 'ion>{"tool":"look","args":{}}</action>']:
        s.feed(d)
    s.finish()
    joined = "".join(out)
    assert "action" not in joined and "Sure." in joined and "Opening now." in joined
