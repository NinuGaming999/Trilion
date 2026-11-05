import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from trilion.core import screen  # noqa: E402
from trilion.core.hud import WebHud, bar, hud_lines  # noqa: E402
from trilion.core.llama import LlamaServer  # noqa: E402

SNAP = {"version": "0.9.0", "state": "acting", "brain": "Qwen3.5 9B", "tps": 41.37, "cpu": 14, "ram": 54,
        "vram": 8300.0, "vram_total": 12288.0, "mic": 0.5, "out": 0.1,
        "game": {"on": True, "profile": "minecraft", "keys": ["w", "lshift"], "buttons": ["left"], "move": [120, -40]},
        "events": [{"k": "run", "text": "open_app: discord"}, {"k": "ok", "text": "open_app: discord"},
                   {"k": "fail", "text": "ui_click: " + "a very long failure reason " * 4}]}


# ------------------------------------------------------------------ HUD text
def test_hud_lines_by_size_and_width():
    c, s, f = (hud_lines(SNAP, z) for z in ("compact", "standard", "full"))
    assert len(c) == 2 and len(c) < len(s) <= len(f)
    assert c[0][0].startswith("TRILION v0.9.0  [ACTING]") and "41.4 tok/s" in c[1][0]
    for lines in (c, s, f):
        assert all(len(t) <= 44 for t, _ in lines), [t for t, _ in lines if len(t) > 44]
    texts = " ".join(t for t, _ in f)
    assert "vram 8.1/12G" in texts and "game minecraft hold w,lshift,L mv +120,-40" in texts
    assert hud_lines({"state": "idle", "version": "1"}, "full")[-1][0].startswith("> waiting")
    assert bar(0.5) == "\u2588" * 4 + "\u2591" * 4 and bar(7) == "\u2588" * 8 and bar(None) == "\u2591" * 8


# ------------------------------------------------------------------ OBS browser source
def test_web_hud_serves_state_and_page_on_localhost_only():
    h = WebHud(0)
    h.start()
    try:
        assert h.httpd.server_address[0] == "127.0.0.1"
        h.update(SNAP)
        data = json.loads(urllib.request.urlopen(h.url + "state").read())
        assert set(data["lines"]) == {"compact", "standard", "full"} and data["state"] == "acting"
        assert data["lines"]["compact"][0][1] == "head"
        page = urllib.request.urlopen(h.url + "?size=compact&bg=0").read().decode()
        assert "<canvas" in page and "236px" in page and "background:transparent" in page.replace(" ", "")
        assert "340px" in urllib.request.urlopen(h.url).read().decode()
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(h.url + "secrets")
    finally:
        h.stop()


def test_web_hud_picks_another_port_when_busy():
    a, b = WebHud(0), None
    a.start()
    try:
        b = WebHud(a.port)
        b.start()
        assert b.port != a.port
    finally:
        a.stop()
        if b:
            b.stop()


# ------------------------------------------------------------------ keep Trilion's windows out of the AI's screenshots
def test_masks_blacken_the_right_pixels():
    from PIL import Image
    im = Image.new("RGB", (200, 100), (200, 200, 200))
    out = screen.apply_masks(im.copy(), [(1100, 1050, 1150, 1080)], 1000, 1000, 1.0)   # monitor origin (1000,1000)
    assert out.getpixel((120, 60)) == (0, 0, 0) and out.getpixel((10, 10)) == (200, 200, 200)
    half = screen.apply_masks(im.copy(), [(1100, 1050, 1150, 1080)], 1000, 1000, 0.5)  # image is half-size
    assert half.getpixel((60, 30)) == (0, 0, 0) and half.getpixel((120, 60)) == (200, 200, 200)
    assert screen.apply_masks(im.copy(), [], 0, 0).getpixel((5, 5)) == (200, 200, 200)


def test_mask_registry_ignores_broken_entries():
    good, hidden = (lambda: (1, 2, 3, 4)), (lambda: None)

    def bad():
        raise RuntimeError

    for fn in (good, hidden, bad):
        screen.add_mask(fn)
    try:
        assert screen.mask_rects() == [(1, 2, 3, 4)]
    finally:
        for fn in (good, hidden, bad):
            screen.remove_mask(fn)
    assert screen.mask_rects() == []


def test_window_helpers_are_safe_off_windows():
    from trilion.ui import winutil
    if os.name != "nt":
        assert winutil.window_rect(1) is None and winutil.set_click_through(1, True) is False
        winutil.set_topmost(1)
        winutil.set_capture_hidden(1, True)


# ------------------------------------------------------------------ engine speed
class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for t in ("a", "b", "c", "d", "e"):
            self.wfile.write(b"data: " + json.dumps({"choices": [{"delta": {"content": t}}]}).encode() + b"\n\n")
        last = {"choices": [{"delta": {}, "finish_reason": "stop"}], "timings": {"predicted_per_second": 52.5}}
        self.wfile.write(b"data: " + json.dumps(last).encode() + b"\n\ndata: [DONE]\n\n")


def test_tokens_per_second_comes_from_engine_timings(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    httpd = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        llm = LlamaServer({"brain": "qwen3.5-9b", "context": 4096, "gpu_layers": 99})
        llm.port = httpd.server_address[1]
        assert "".join(llm.chat_stream([{"role": "user", "content": "hi"}])) == "abcde"
        assert llm.last_tps == pytest.approx(52.5)
    finally:
        httpd.shutdown()


# ------------------------------------------------------------------ the overlay window (needs Qt)
qt = pytest.importorskip("PySide6.QtWidgets")


class Cfg(dict):
    def save(self):
        pass


@pytest.fixture
def overlay():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from trilion.ui.overlay import Overlay
    o = Overlay(Cfg(overlay_size="standard", overlay_corner="top-right", overlay_opacity=0.9), "0.9.0")
    yield o, app
    o.anim.stop()
    o.pin.stop()
    o.close()


def test_overlay_sizes_corners_and_hidden_rect(overlay):
    from PySide6.QtGui import QGuiApplication
    o, app = overlay
    assert o.rect_real() is None                                   # hidden -> nothing to black out
    o.show()
    app.processEvents()
    scr = QGuiApplication.primaryScreen().availableGeometry()
    for corner in ("top-left", "top-right", "bottom-left", "bottom-right"):
        o.set_corner(corner)
        g = o.frameGeometry()
        assert scr.left() <= g.left() and g.right() <= scr.right() + 1 and scr.top() <= g.top() and g.bottom() <= scr.bottom() + 1
    assert o.cycle_size() == "full" and o.width() == 420 and o.cycle_size() == "compact" and o.width() == 236
    assert o.cycle_size() == "standard"
    l, t, r, b = o.rect_real()
    assert r - l >= o.width() and b - t >= o.height()


def test_overlay_lock_unlock_and_drag_saves_position(overlay):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    o, app = overlay
    o.show()
    o.set_locked(True)
    assert o.locked and o.cfg["overlay_locked"] is True
    o.set_locked(False)
    assert not o.locked
    start = o.frameGeometry().topLeft()
    ev = lambda kind, pos: QMouseEvent(kind, QPointF(pos), QPointF(pos), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    o.mousePressEvent(ev(QEvent.MouseButtonPress, start + o.rect().center()))
    o.mouseMoveEvent(ev(QEvent.MouseMove, start + o.rect().center() + __import__("PySide6.QtCore", fromlist=["QPoint"]).QPoint(-120, 80)))
    o.mouseReleaseEvent(ev(QEvent.MouseButtonRelease, start))
    assert o.cfg["overlay_corner"] == "custom" and o.cfg["overlay_x"] == o.x() and o.cfg["overlay_y"] == o.y()
    assert o.x() != start.x()
    o.set_locked(True)
    o.press = None
    o.place()                                                      # custom position is restored


def test_overlay_draws_snapshot_lines(overlay):
    o, app = overlay
    o.show()
    o.set_snapshot({**SNAP, "level": 0.4, "color": [255, 95, 162]})
    for _ in range(5):
        o._animate()
    app.processEvents()
    assert o.lines[0][0].startswith("TRILION v0.9.0") and len(o.lines) == len(hud_lines(SNAP, "standard"))
    img = o.grab().toImage()
    assert img.width() == 340 and img.height() == 372
    o.set_opacity(0.05)
    assert o.cfg["overlay_opacity"] == 0.2                          # too faint -> clamped
    o.set_opacity(7)
    assert o.cfg["overlay_opacity"] == 1.0
