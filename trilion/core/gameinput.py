"""Game input: the same keyboard and mouse a person uses, nothing else.

* Keys are sent as hardware scan codes (DirectX games ignore plain virtual-key presses).
* The mouse moves in RELATIVE counts (what first-person cameras read), spread smoothly over time,
  with exact sub-pixel bookkeeping so a 100-count move is always exactly 100 counts.
* Everything held is released on stop / quit / crash, and by a dead-man timer if Trilion goes quiet.
The Windows backend talks to SendInput; tests use a recording backend."""
import atexit
import ctypes
import logging
import math
import threading
import time

log = logging.getLogger("trilion.game")

# ---------------------------------------------------------------- scan codes (set 1)
_SC = {}
for i, ch in enumerate("1234567890"):
    _SC[ch] = 0x02 + i
for row, start in (("qwertyuiop", 0x10), ("asdfghjkl", 0x1E), ("zxcvbnm", 0x2C)):
    for i, ch in enumerate(row):
        _SC[ch] = start + i
_SC.update({"esc": 0x01, "minus": 0x0C, "equals": 0x0D, "backspace": 0x0E, "tab": 0x0F, "lbracket": 0x1A,
            "rbracket": 0x1B, "enter": 0x1C, "lctrl": 0x1D, "semicolon": 0x27, "quote": 0x28, "grave": 0x29,
            "lshift": 0x2A, "backslash": 0x2B, "comma": 0x33, "period": 0x34, "slash": 0x35, "rshift": 0x36,
            "lalt": 0x38, "space": 0x39, "capslock": 0x3A, "f11": 0x57, "f12": 0x58})
for n in range(1, 11):
    _SC[f"f{n}"] = 0x3A + n
_EXT = {"up": 0x48, "left": 0x4B, "right": 0x4D, "down": 0x50, "insert": 0x52, "delete": 0x53, "home": 0x47,
        "end": 0x4F, "pageup": 0x49, "pagedown": 0x51, "rctrl": 0x1D, "ralt": 0x38, "lwin": 0x5B, "rwin": 0x5C}
_ALIAS = {"shift": "lshift", "ctrl": "lctrl", "control": "lctrl", "alt": "lalt", "return": "enter",
          "escape": "esc", "arrowup": "up", "arrowdown": "down", "arrowleft": "left", "arrowright": "right",
          "pgup": "pageup", "pgdn": "pagedown", "del": "delete", "ins": "insert", "windows": "lwin",
          "win": "lwin", "caps": "capslock", "-": "minus", "=": "equals", "[": "lbracket", "]": "rbracket",
          ";": "semicolon", "'": "quote", "`": "grave", "\\": "backslash", ",": "comma", ".": "period",
          "/": "slash", " ": "space", "spacebar": "space", "bksp": "backspace"}
BUTTONS = ("left", "right", "middle")


def key_info(name):
    """-> (scan_code, extended) for a key name, or raise ValueError."""
    k = str(name).strip().lower()
    k = _ALIAS.get(k, k)
    if k in _EXT:
        return _EXT[k], True
    if k in _SC:
        return _SC[k], False
    raise ValueError(f"Unknown key '{name}'. Use a-z, 0-9, space, enter, esc, tab, shift, ctrl, alt, "
                     "up/down/left/right, f1-f12")


def parse_keys(text):
    if isinstance(text, (list, tuple)):
        items = text
    else:
        items = [p for p in str(text or "").replace("+", ",").replace(" ", ",").split(",")]
    out = []
    for p in items:
        p = str(p).strip()
        if p:
            key_info(p)  # validate early
            canon = _ALIAS.get(p.lower(), p.lower())
            if canon not in out:
                out.append(canon)
    return out


# ---------------------------------------------------------------- backends
class RecordingBackend:
    """For tests / dry runs: records what would be sent."""

    def __init__(self):
        self.events = []
        self.t0 = time.perf_counter()

    def _add(self, *e):
        self.events.append((round(time.perf_counter() - self.t0, 4),) + e)

    def key(self, scan, extended, down):
        self._add("key", scan, extended, down)

    def move_rel(self, dx, dy):
        self._add("move", dx, dy)

    def move_abs(self, x, y):
        self._add("abs", x, y)

    def button(self, name, down):
        self._add("button", name, down)

    def wheel(self, notches):
        self._add("wheel", notches)


class WinBackend:
    """SendInput with scan codes / relative mouse. Windows only."""

    def __init__(self):
        self.u = ctypes.windll.user32
        try:
            ctypes.windll.winmm.timeBeginPeriod(1)  # 1 ms timer resolution -> precise timing
            self._timer = True
        except Exception:
            self._timer = False

    def close(self):
        if self._timer:
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass

    def _send(self, inp):
        if self.u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
            raise OSError("SendInput was blocked (is the game running as administrator? start Trilion as administrator too)")

    def key(self, scan, extended, down):
        flags = 0x0008 | (0x0001 if extended else 0) | (0 if down else 0x0002)  # SCANCODE [| EXTENDED] [| KEYUP]
        i = INPUT(type=1)
        i.u.ki = KEYBDINPUT(0, scan, flags, 0, 0)
        self._send(i)

    def _mouse(self, dx, dy, data, flags):
        i = INPUT(type=0)
        i.u.mi = MOUSEINPUT(dx, dy, data, flags, 0, 0)
        self._send(i)

    def move_rel(self, dx, dy):
        self._mouse(int(dx), int(dy), 0, 0x0001)

    def move_abs(self, x, y):
        vx, vy = self.u.GetSystemMetrics(76), self.u.GetSystemMetrics(77)
        vw, vh = max(2, self.u.GetSystemMetrics(78)), max(2, self.u.GetSystemMetrics(79))
        nx, ny = int((x - vx) * 65535 / (vw - 1)), int((y - vy) * 65535 / (vh - 1))
        self._mouse(nx, ny, 0, 0x0001 | 0x8000 | 0x4000)  # MOVE | ABSOLUTE | VIRTUALDESK

    def button(self, name, down):
        flag = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}[name][0 if down else 1]
        self._mouse(0, 0, 0, flag)

    def wheel(self, notches):
        self._mouse(0, 0, ctypes.c_uint32(int(notches) * 120).value, 0x0800)


# SendInput structures with explicit sizes so they are identical on every platform (INPUT = 40 bytes on x64)
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_int32), ("dy", ctypes.c_int32), ("mouseData", ctypes.c_uint32),
                ("dwFlags", ctypes.c_uint32), ("time", ctypes.c_uint32), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_uint16), ("wScan", ctypes.c_uint16), ("dwFlags", ctypes.c_uint32),
                ("time", ctypes.c_uint32), ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_uint32), ("wParamL", ctypes.c_uint16), ("wParamH", ctypes.c_uint16)]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_uint32), ("u", _U)]


# ---------------------------------------------------------------- the player
class GameInput:
    STEP = 0.008  # mouse sample interval (~125 Hz)

    def __init__(self, backend, deadman=3.0):
        self.b = backend
        self.deadman = deadman
        self.keys = set()
        self.buttons = set()
        self.lock = threading.RLock()
        self.last_cmd = time.monotonic()
        self._watch = None
        atexit.register(self.release_all)

    # ---- safety ----
    def _ensure_watchdog(self):
        if self._watch is None or not self._watch.is_alive():
            self._watch = threading.Thread(target=self._dog, daemon=True)
            self._watch.start()

    def _dog(self):
        while True:
            time.sleep(min(0.25, max(0.02, self.deadman / 4)))
            with self.lock:
                if (self.keys or self.buttons) and time.monotonic() - self.last_cmd > self.deadman:
                    log.warning("dead-man timer: releasing held inputs")
                    self.release_all()

    def release_all(self):
        with self.lock:
            for k in list(self.keys):
                self._key(k, False)
            for bn in list(self.buttons):
                self._btn(bn, False)

    # ---- primitives ----
    def _key(self, name, down):
        sc, ext = key_info(name)
        self.b.key(sc, ext, down)
        (self.keys.add if down else self.keys.discard)(_ALIAS.get(name.lower(), name.lower()))

    def _btn(self, name, down):
        self.b.button(name, down)
        (self.buttons.add if down else self.buttons.discard)(name)

    def _sleep_until(self, t, stop):
        while True:
            left = t - time.perf_counter()
            if left <= 0:
                return True
            if stop():
                return False
            time.sleep(min(left, 0.004) if left > 0.004 else 0)

    def move_smooth(self, dx, dy, ms, stop=lambda: False):
        """Move the mouse by exactly (dx, dy) counts, spread over ms milliseconds."""
        dx, dy = int(dx), int(dy)
        if not dx and not dy:
            return True
        n = max(1, math.ceil(ms / 1000.0 / self.STEP))
        t0, px, py = time.perf_counter(), 0, 0
        for i in range(1, n + 1):
            tx, ty = round(dx * i / n), round(dy * i / n)
            if tx != px or ty != py:
                self.b.move_rel(tx - px, ty - py)
                px, py = tx, ty
            if i < n and not self._sleep_until(t0 + ms / 1000.0 * i / n, stop):
                return False
        return True

    # ---- the one call the model uses ----
    def act(self, hold="", tap="", dx=0, dy=0, click="", scroll=0, ms=300, keep=False, stop=lambda: False):
        """Hold keys for ms, tap keys, move the mouse, click, scroll - all timed locally."""
        hold_keys, tap_keys = parse_keys(hold), parse_keys(tap)
        click = (click or "").lower().strip()
        if click and click not in BUTTONS:
            raise ValueError("click must be left, right or middle")
        ms = int(max(0, min(5000, ms if ms is not None else 300)))
        with self.lock:
            self.last_cmd = time.monotonic()
            self._ensure_watchdog()
            for k in list(self.keys):                 # keys not listed are released (Lumine-style chunks)
                if k not in hold_keys:
                    self._key(k, False)
            for k in hold_keys:
                if k not in self.keys:
                    self._key(k, True)
        t_start = time.perf_counter()
        ok = True
        try:
            for k in tap_keys:
                with self.lock:
                    self._key(k, True)
                time.sleep(0.04)
                with self.lock:
                    self._key(k, False)
                time.sleep(0.02)
            if scroll:
                self.b.wheel(int(scroll))
            if click:
                with self.lock:
                    self._btn(click, True)
                time.sleep(0.045)
                with self.lock:
                    self._btn(click, False)
            remaining = ms - (time.perf_counter() - t_start) * 1000
            if dx or dy:
                ok = self.move_smooth(dx, dy, max(0, remaining), stop)
            ok = ok and self._sleep_until(t_start + ms / 1000.0, stop)
        finally:
            if not keep or not ok or stop():
                self.release_all()
            self.last_cmd = time.monotonic()
        return ok

    def click_at(self, x, y, button="left", double=False):
        if button not in BUTTONS:
            raise ValueError("button must be left, right or middle")
        with self.lock:
            self.last_cmd = time.monotonic()
        self.b.move_abs(int(x), int(y))
        time.sleep(0.06)
        for _ in range(2 if double else 1):
            self.b.button(button, True)
            time.sleep(0.045)
            self.b.button(button, False)
            time.sleep(0.06)
