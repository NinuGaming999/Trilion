"""Everything Trilion can do on the PC. Risky tools ask for confirmation first."""
import logging
import os
import subprocess
import time
import webbrowser
from pathlib import Path

from . import screen

log = logging.getLogger("trilion.tools")
NO_WINDOW = 0x08000000 if os.name == "nt" else 0

TOOL_DOCS = """\
open_app {"name": "notepad"}            - launch an app, file or folder by name/path
open_url {"url": "https://..."}         - open a link in the default browser
look {}                                  - take a fresh screenshot
click {"x": 100, "y": 200, "button": "left", "double": false} - click at pixel coords of the screenshot
move {"x": 100, "y": 200}                - move the mouse
scroll {"amount": -5}                    - scroll (negative = down)
type_text {"text": "hello"}              - type text at the cursor
press_keys {"keys": "ctrl+s"}            - press a key or combo (enter, win, alt+tab, ctrl+shift+esc ...)
wait {"seconds": 2}                      - wait for something to load
list_dir {"path": "C:/Users"}            - list a folder
read_file {"path": "C:/a.txt"}           - read a text file
write_file {"path": "C:/a.txt", "content": "..."} - write a text file (asks the user)
run_shell {"command": "dir"}             - run a Windows shell command (asks the user)"""

RISKY = {"run_shell", "write_file"}
SCREEN_TOOLS = {"open_app", "open_url", "look", "click", "move", "scroll", "type_text", "press_keys", "wait"}


class Tools:
    def __init__(self, cfg, confirm):
        self.cfg = cfg
        self.confirm = confirm  # confirm(text) -> bool (blocking)

    def run(self, action):
        name = action.get("tool", "")
        args = action.get("args", {}) or {}
        fn = getattr(self, "t_" + name, None)
        if not fn:
            return f"Unknown tool '{name}'."
        if name in RISKY and self.cfg.get("confirm_risky", True):
            if not self.confirm(f"Trilion wants to run: {name} {args}"):
                return "The user declined this action."
        try:
            return str(fn(**args))[:2500]
        except TypeError as e:
            return f"Bad arguments for {name}: {e}"
        except Exception as e:
            log.exception("tool %s failed", name)
            return f"{name} failed: {e}"

    # ---- GUI ----
    def _gui(self):
        import pyautogui
        pyautogui.PAUSE = 0.08
        pyautogui.FAILSAFE = True  # slam the mouse into a screen corner to abort
        return pyautogui

    def t_open_app(self, name):
        try:
            os.startfile(name)  # Windows: apps registered in the shell, files, folders
            time.sleep(1.2)
            return f"Opened {name}."
        except Exception:
            g = self._gui()
            g.press("win")
            time.sleep(0.5)
            g.write(name, interval=0.02)
            time.sleep(0.8)
            g.press("enter")
            time.sleep(1.5)
            return f"Tried to open {name} via Start search."

    def t_open_url(self, url):
        webbrowser.open(url)
        time.sleep(1.5)
        return f"Opened {url}."

    def t_look(self):
        return "Fresh screenshot attached."

    def t_click(self, x, y, button="left", double=False):
        g = self._gui()
        sx, sy = screen.to_screen(x, y)
        g.click(sx, sy, button=button, clicks=2 if double else 1)
        time.sleep(0.4)
        return f"Clicked ({x},{y})."

    def t_move(self, x, y):
        sx, sy = screen.to_screen(x, y)
        self._gui().moveTo(sx, sy, duration=0.15)
        return "Moved."

    def t_scroll(self, amount):
        self._gui().scroll(int(amount) * 100)
        return "Scrolled."

    def t_type_text(self, text):
        g = self._gui()
        if text.isascii():
            g.write(text, interval=0.01)
        else:
            import pyperclip
            pyperclip.copy(text)
            g.hotkey("ctrl", "v")
        return "Typed."

    def t_press_keys(self, keys):
        parts = [k.strip().lower() for k in keys.replace(" ", "").split("+") if k]
        g = self._gui()
        g.hotkey(*parts) if len(parts) > 1 else g.press(parts[0])
        time.sleep(0.3)
        return f"Pressed {keys}."

    def t_wait(self, seconds=1):
        time.sleep(min(float(seconds), 15))
        return "Waited."

    # ---- files / shell ----
    def t_list_dir(self, path="."):
        items = sorted(os.listdir(path))[:200]
        return "\n".join(items) or "(empty)"

    def t_read_file(self, path):
        return Path(path).read_text(encoding="utf-8", errors="ignore")[:2400]

    def t_write_file(self, path, content):
        Path(path).write_text(content, encoding="utf-8")
        return f"Wrote {path}."

    def t_run_shell(self, command):
        r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=45,
                           creationflags=NO_WINDOW)
        out = (r.stdout + r.stderr).strip()
        return f"exit {r.returncode}\n{out[-2000:]}"
