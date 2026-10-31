"""Everything Trilion can do on the PC. Risky tools ask for confirmation first."""
import contextlib
import ctypes
import io
import logging
import os
import re
import subprocess
import time
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import screen

log = logging.getLogger("trilion.tools")
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Trilion/0.2"}

TOOL_DOCS = """\
SEEING
look {}                                   - fresh screenshot
zoom {"x":100,"y":200,"w":400,"h":200}    - read small text: native-resolution close-up of a region (screenshot coords)
list_windows {}                           - titles of open windows
APPS & WINDOWS
open_app {"name":"notepad"}               - launch an app, file, folder or shortcut by name/path
open_url {"url":"https://..."}            - open a link in the browser
focus_window {"title":"Chrome"}           - bring a window to the front (title substring)
MOUSE & KEYBOARD
click {"x":100,"y":200,"button":"left","double":false} - click at screenshot pixel coords
drag {"x1":10,"y1":10,"x2":300,"y2":200}  - drag with the mouse
move {"x":100,"y":200}   scroll {"amount":-5} (negative = down)
type_text {"text":"hello","enter":false}  - type at the cursor
press_keys {"keys":"ctrl+s"}              - key or combo: enter, win, alt+tab, win+d, ctrl+shift+esc, volumeup, volumedown, volumemute, playpause, nexttrack, printscreen ...
clipboard_get {}   clipboard_set {"text":"..."}
wait {"seconds":2}
INTERNET
web_search {"query":"..."}                - search the web
fetch_url {"url":"https://..."}           - read a web page as text
FILES & SYSTEM
list_dir {"path":"C:/Users"}   read_file {"path":"C:/a.txt"}
write_file {"path":"C:/a.txt","content":"..."}   - asks the user
run_shell {"command":"..."}               - cmd/PowerShell (e.g. powershell -c "..."); asks the user. Use it for anything with no button: installing, killing tasks, settings, system info.
run_python {"code":"print(2+2)"}          - run Python for calculations or file/data work; asks the user"""

RISKY = {"run_shell", "write_file", "run_python"}
SCREEN_TOOLS = {"open_app", "open_url", "look", "click", "move", "scroll", "type_text", "press_keys", "wait",
                "drag", "focus_window"}


class Tools:
    def __init__(self, cfg, confirm):
        self.cfg = cfg
        self.confirm = confirm  # confirm(text) -> bool (blocking)
        self.extra_image = None  # (b64, (w,h)) a tool wants shown to the model

    def run(self, action):
        name = action.get("tool", "")
        args = action.get("args", {}) or {}
        fn = getattr(self, "t_" + name, None)
        if not fn:
            return f"Unknown tool '{name}'."
        if name in RISKY and self.cfg.get("confirm_risky", True):
            if not self.confirm(f"Trilion wants to run: {name} {str(args)[:300]}"):
                return "The user declined this action."
        try:
            return str(fn(**args))[:3000]
        except TypeError as e:
            return f"Bad arguments for {name}: {e}"
        except Exception as e:
            log.exception("tool %s failed", name)
            return f"{name} failed: {e}"

    def _gui(self):
        import pyautogui
        pyautogui.PAUSE = 0.08
        pyautogui.FAILSAFE = True  # slam the mouse into a screen corner to abort
        return pyautogui

    # ---- seeing ----
    def t_look(self):
        return "Fresh screenshot attached."

    def t_zoom(self, x, y, w, h):
        self.extra_image = screen.zoom(x, y, w, h)
        return f"Close-up of region ({x},{y},{w},{h}) attached as a second image."

    def t_list_windows(self):
        if os.name != "nt":
            return "Windows only."
        u = ctypes.windll.user32
        titles = []
        cb_t = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def cb(hwnd, _):
            if u.IsWindowVisible(hwnd):
                n = u.GetWindowTextLengthW(hwnd)
                if n:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    u.GetWindowTextW(hwnd, buf, n + 1)
                    titles.append(buf.value)
            return True
        u.EnumWindows(cb_t(cb), 0)
        return "\n".join(t for t in titles if t != "Program Manager") or "(none)"

    # ---- apps ----
    def t_open_app(self, name):
        try:
            os.startfile(name)
            time.sleep(1.2)
            return f"Opened {name}."
        except Exception:
            g = self._gui()
            g.press("win")
            time.sleep(0.5)
            g.write(name, interval=0.02)
            time.sleep(0.9)
            g.press("enter")
            time.sleep(1.5)
            return f"Tried to open {name} via Start search."

    def t_open_url(self, url):
        webbrowser.open(url)
        time.sleep(1.5)
        return f"Opened {url}."

    def t_focus_window(self, title):
        if os.name != "nt":
            return "Windows only."
        u = ctypes.windll.user32
        found = []
        cb_t = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def cb(hwnd, _):
            if u.IsWindowVisible(hwnd):
                n = u.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                if title.lower() in buf.value.lower():
                    found.append(hwnd)
            return True
        u.EnumWindows(cb_t(cb), 0)
        if not found:
            return f"No window matching '{title}'."
        h = found[0]
        if u.IsIconic(h):
            u.ShowWindow(h, 9)
        u.keybd_event(0x12, 0, 0, 0)  # tap ALT so Windows allows the focus change
        u.SetForegroundWindow(h)
        u.keybd_event(0x12, 0, 2, 0)
        time.sleep(0.5)
        return f"Focused window '{title}'."

    # ---- mouse & keyboard ----
    def t_click(self, x, y, button="left", double=False):
        sx, sy = screen.to_screen(x, y)
        self._gui().click(sx, sy, button=button, clicks=2 if double else 1)
        time.sleep(0.4)
        return f"Clicked ({x},{y})."

    def t_drag(self, x1, y1, x2, y2):
        g = self._gui()
        a, b = screen.to_screen(x1, y1), screen.to_screen(x2, y2)
        g.moveTo(*a, duration=0.15)
        g.dragTo(*b, duration=0.5, button="left")
        return "Dragged."

    def t_move(self, x, y):
        self._gui().moveTo(*screen.to_screen(x, y), duration=0.15)
        return "Moved."

    def t_scroll(self, amount):
        self._gui().scroll(int(amount) * 100)
        return "Scrolled."

    def t_type_text(self, text, enter=False):
        g = self._gui()
        if text.isascii():
            g.write(text, interval=0.01)
        else:
            import pyperclip
            pyperclip.copy(text)
            g.hotkey("ctrl", "v")
        if enter:
            g.press("enter")
        return "Typed."

    def t_press_keys(self, keys):
        parts = [k.strip().lower() for k in keys.replace(" ", "").split("+") if k]
        g = self._gui()
        g.hotkey(*parts) if len(parts) > 1 else g.press(parts[0])
        time.sleep(0.3)
        return f"Pressed {keys}."

    def t_clipboard_get(self):
        import pyperclip
        return pyperclip.paste()[:2500]

    def t_clipboard_set(self, text):
        import pyperclip
        pyperclip.copy(text)
        return "Copied to clipboard."

    def t_wait(self, seconds=1):
        time.sleep(min(float(seconds), 15))
        return "Waited."

    # ---- internet ----
    @staticmethod
    def _strip(html):
        html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
        html = re.sub(r"(?s)<[^>]+>", " ", html)
        html = html.replace("&amp;", "&").replace("&quot;", '"').replace("&#x27;", "'").replace("&nbsp;", " ")
        return re.sub(r"\s+", " ", html).strip()

    def t_web_search(self, query):
        import requests
        r = requests.get("https://html.duckduckgo.com/html/", params={"q": query}, headers=UA, timeout=20)
        out = []
        for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=class="result__a"|$)', r.text, re.S):
            href, title, rest = m.groups()
            q = parse_qs(urlparse(href).query).get("uddg")
            url = unquote(q[0]) if q else href
            sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', rest, re.S)
            out.append(f"{self._strip(title)} - {url}\n  {self._strip(sn.group(1)) if sn else ''}")
            if len(out) >= 5:
                break
        return "\n".join(out) or "No results (search page format may have changed)."

    def t_fetch_url(self, url):
        import requests
        r = requests.get(url, headers=UA, timeout=20)
        return self._strip(r.text)[:2800]

    # ---- files / shell / python ----
    def t_list_dir(self, path="."):
        return "\n".join(sorted(os.listdir(path))[:200]) or "(empty)"

    def t_read_file(self, path):
        return Path(path).read_text(encoding="utf-8", errors="ignore")[:2800]

    def t_write_file(self, path, content):
        Path(path).write_text(content, encoding="utf-8")
        return f"Wrote {path}."

    def t_run_shell(self, command):
        r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60,
                           creationflags=NO_WINDOW)
        return f"exit {r.returncode}\n{(r.stdout + r.stderr).strip()[-2200:]}"

    def t_run_python(self, code):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            exec(compile(code, "<trilion>", "exec"), {"__name__": "__trilion__"})
        return buf.getvalue()[-2200:] or "(no output)"
