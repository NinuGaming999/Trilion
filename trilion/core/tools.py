"""Everything Trilion can do on the PC. Risky tools ask for confirmation first."""
import contextlib
import ctypes
import inspect
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
ui_list {"window":"<window title>"}              - numbered list of buttons/fields/menus in a window ([id] Type: name); window optional = front window
APPS & WINDOWS
open_app {"name":"<app name>"}               - launch an app, file, folder or shortcut by name/path
play_youtube {"query":"<search words>"}     - find a YouTube video by search words and open the top result (then look to confirm it is right)
open_search {"site":"youtube","query":"<search words>"} - open a site's search page (youtube, google, maps, spotify, wikipedia, github, amazon, images)
open_url {"url":"https://..."}            - open a link (only links you found with web_search/open_search/fetch_url, or the user gave you)
focus_window {"title":"<window title>"}           - bring a window to the front (title substring)
MOUSE & KEYBOARD
ui_click {"id":12}  or  {"name":"<control name>","window":"<window title>"} - click a control from the last ui_list. Only works in apps that expose their controls (NOT Discord, browsers, Electron apps or games: use click there)
ui_type {"id":12,"text":"<text>","enter":false}  - click a text field from the last ui_list and type
click {"x":100,"y":200,"button":"left","double":false} - click at the screenshot coordinates (works in every app)
click_type {"x":100,"y":200,"text":"<text>","enter":false} - click a text box at those coordinates, then type into it (chat boxes, search bars)
drag {"x1":10,"y1":10,"x2":300,"y2":200}  - drag with the mouse
move {"x":100,"y":200}   scroll {"amount":-5} (negative = down)
type_text {"text":"<text>","enter":false}  - type at the cursor
press_keys {"keys":"ctrl+s"}              - key or combo: enter, win, alt+tab, win+d, volumeup, volumedown, volumemute, playpause, nexttrack ...
clipboard_get {}   clipboard_set {"text":"..."}
wait {"seconds":2}
INTERNET
web_search {"query":"..."}                - search the web (returns real links)
fetch_url {"url":"https://..."}           - read a web page as text
FILES & SYSTEM
list_dir {"path":"C:/Users"}   read_file {"path":"C:/a.txt"}
write_file {"path":"C:/a.txt","content":"..."}   - asks the user
run_shell {"command":"..."}               - cmd/PowerShell (e.g. powershell -c "..."); asks the user
run_python {"code":"print(2+2)"}          - run Python for calculations or data work; asks the user
GAMES (real keyboard and mouse only; single-player games)
game_mode {"on":true,"window":"<game window title>"} - start or stop game mode (asks the user once; stopping releases every key)
game_act {"hold":"<keys, comma separated>","tap":"<keys>","dx":0,"dy":0,"click":"<left|right|middle>","scroll":0,"ms":500,"keep":false} - ONE timed action: keys in hold stay down for ms, then release; dx/dy move the mouse in counts (camera/aim); tap presses keys once. Keys: a-z 0-9 space enter esc tab shift ctrl alt up down left right f1-f12
game_click {"x":0,"y":0,"button":"left","double":false} - click a spot in a menu (same coordinates as the screenshot)
game_release {} - let go of every key and mouse button
SKILLS & MEMORY
use_skill {"name":"play-media"}           - load a skill's step-by-step instructions
list_skills {}                            - all skills
create_skill {"name":"my-skill","description":"when to use it","instructions":"1. ... 2. ..."}
run_skill_script {"skill":"my-skill","script":"do.ps1","args":""} - run a script stored in a skill; asks the user
remember {"fact":"The user's city is Dhaka"}   forget {"fact":"city"}"""

RISKY = {"run_shell", "write_file", "run_python", "run_skill_script"}
SCREEN_TOOLS = {"game_act", "game_click", "game_mode", "open_app", "open_url", "open_search", "look", "click", "move", "scroll", "type_text",
                "press_keys", "wait", "drag", "focus_window", "ui_click", "ui_type", "click_type", "play_youtube", "search_site"}

SEARCH_SITES = {
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "google": "https://www.google.com/search?q={q}",
    "images": "https://www.google.com/search?tbm=isch&q={q}",
    "maps": "https://www.google.com/maps/search/{q}",
    "spotify": "https://open.spotify.com/search/{q}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={q}",
    "github": "https://github.com/search?q={q}",
    "amazon": "https://www.amazon.com/s?k={q}",
}
CRITICAL_RE = re.compile(
    r"\b(delete|remove|erase|format|uninstall|empty (the )?recycle|send|submit|post|publish|pay|buy|purchase|"
    r"checkout|place order|confirm (payment|order|purchase)|transfer|withdraw|sign out|log out|logout|"
    r"shut ?down|restart|factory reset)\b", re.I)
CRITICAL_KEYS = {"alt+f4", "shift+delete", "ctrl+shift+delete", "delete"}
URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")
INTERACTIVE = {"ButtonControl", "EditControl", "MenuItemControl", "ListItemControl", "TabItemControl",
               "CheckBoxControl", "RadioButtonControl", "HyperlinkControl", "ComboBoxControl",
               "TreeItemControl", "SplitButtonControl"}


class Tools:
    def __init__(self, cfg, confirm, skills=None, memory=None, cancelled=lambda: False):
        self.cfg = cfg
        self.confirm = confirm  # confirm(text) -> bool (blocking)
        self.skills, self.memory, self.cancelled = skills, memory, cancelled
        self.extra_image = None  # (b64, (w,h)) a tool wants shown to the model
        self.known_urls = set()  # links the model may open: user-given or found via search
        self._ui_map = {}        # id -> (x, y, name, type) from the last ui_list
        self.game = None         # GameInput while game mode is on
        self.game_window = ""    # title text of the game window that must be in front
        self.game_backend = None  # tests inject a recording backend here

    def note_text(self, text):
        for u in URL_RE.findall(text or ""):
            self.known_urls.add(u.rstrip(".,;"))

    def run(self, action):
        name = action.get("tool", "")
        args = action.get("args", {}) or {}
        fn = getattr(self, "t_" + name, None)
        if not fn:
            return f"Unknown tool '{name}'."
        reason = self.critical_reason(name, args) if self.cfg.get("confirm_critical", True) else None
        if reason and not self.confirm(f"Trilion is about to {reason}. Allow?"):
            return "The user declined this action."
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

    def critical_reason(self, name, args):
        """Irreversible-looking actions (delete / pay / send ...) always ask first, even if 'Confirm risky' is off."""
        try:
            label = None
            if name == "ui_click":
                if args.get("id") is not None and str(args["id"]).lstrip("-").isdigit():
                    item = self._ui_map.get(int(args["id"]))
                    label = item[2] if item else None
                label = label or args.get("name")
            elif name in ("click", "click_type"):
                label = self._name_at(args.get("x"), args.get("y"))
            elif name == "press_keys":
                keys = str(args.get("keys", "")).replace(" ", "").lower()
                return f"press {keys}" if keys in CRITICAL_KEYS else None
            if label and CRITICAL_RE.search(label):
                return f"click '{label[:50]}'"
        except Exception:
            pass
        return None

    def _name_at(self, x, y):
        """Best-effort: name of the control under a screenshot point (UI Automation)."""
        if x is None or y is None:
            return None
        try:
            import uiautomation as auto
            sx, sy = screen.to_screen(x, y)
            c = auto.ControlFromPoint(sx, sy)
            return (c.Name or "").strip() if c else None
        except Exception:
            return None

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

    def _url_ok(self, url):
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.netloc:
            return False
        if u.path in ("", "/") and not u.query:
            return True  # a site's front page is safe
        return any(url == k or url.startswith(k) for k in self.known_urls)

    def t_open_url(self, url, _user_text=""):
        if "dQw4w9WgXcQ" in url:  # the 7B brain loves this link
            return "Blocked: that is the Rickroll video. Do not invent links; use play_youtube with search words instead."
        if not self._url_ok(url):
            return ("Blocked: you must not guess links. Use web_search (then open one of its result links), "
                    "open_search, or play_youtube to find the right page.")
        webbrowser.open(url)
        time.sleep(1.5)
        return f"Opened {url}."

    def t_play_youtube(self, query):
        import requests
        from urllib.parse import quote_plus
        page = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        try:
            html = requests.get(page, headers=dict(UA, **{"Accept-Language": "en"}), timeout=15).text
            ids = [i for i in re.findall(r'"videoId":"([\w-]{11})"', html) if i != "dQw4w9WgXcQ"]
            if ids:
                self.known_urls.add(f"https://www.youtube.com/watch?v={ids[0]}")
                webbrowser.open(f"https://www.youtube.com/watch?v={ids[0]}")
                time.sleep(2)
                return f"Opened the top YouTube result for '{query}'."
        except Exception:
            pass
        webbrowser.open(page)
        time.sleep(2)
        return f"Opened YouTube search results for '{query}'."

    def t_search_site(self, query, site="google"):
        from urllib.parse import quote_plus
        q = quote_plus(query)
        urls = {"google": f"https://www.google.com/search?q={q}",
                "youtube": f"https://www.youtube.com/results?search_query={q}",
                "maps": f"https://www.google.com/maps/search/{q}",
                "amazon": f"https://www.amazon.com/s?k={q}",
                "wikipedia": f"https://en.wikipedia.org/w/index.php?search={q}"}
        webbrowser.open(urls.get(site.lower(), urls["google"]))
        time.sleep(2)
        return f"Opened {site} search for '{query}'."

    def t_open_search(self, site, query):
        from urllib.parse import quote_plus
        tpl = SEARCH_SITES.get(site.lower())
        if not tpl:
            return f"Unknown site '{site}'. Choose from: {', '.join(SEARCH_SITES)}."
        url = tpl.format(q=quote_plus(query))
        self.known_urls.add(url)
        webbrowser.open(url)
        time.sleep(2.0)
        return f"Opened {site} search for '{query}'."

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

    def t_click_type(self, x, y, text, enter=False):
        """Click a text box at screenshot coordinates, then type: one step for chat boxes / search bars."""
        self.t_click(x, y)
        time.sleep(0.25)
        self.t_type_text(text, enter=enter)
        return f"Clicked ({x},{y}) and typed."

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
            self.known_urls.add(url)
            sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', rest, re.S)
            out.append(f"{self._strip(title)} - {url}\n  {self._strip(sn.group(1)) if sn else ''}")
            if len(out) >= 5:
                break
        return "\n".join(out) or "No results (search page format may have changed)."

    def t_fetch_url(self, url):
        import requests
        r = requests.get(url, headers=UA, timeout=20)
        for h in re.findall(r'href="(https?://[^"]+)"', r.text)[:80]:
            self.known_urls.add(h.replace("&amp;", "&"))
        self.known_urls.add(url)
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

    # ---- UI Automation: click controls by name ----
    def _uia_root(self, window=None):
        import uiautomation as auto
        if window:
            w = auto.WindowControl(searchDepth=1, SubName=window)
            if not w.Exists(2, 0.3):
                raise RuntimeError(f"No window matching '{window}'. Use list_windows or focus_window.")
            return auto, w
        w = auto.GetForegroundControl()
        w = w.GetTopLevelControl() or w
        if (w.Name or "").startswith("Trilion"):
            raise RuntimeError("Trilion's own window is in front. Use focus_window on the target app first, "
                               "or pass the window name.")
        return auto, w

    def _uia_walk(self, auto, root, limit=1500, seconds=4.0):
        t0, n = time.time(), 0
        for c, _depth in auto.WalkControl(root, includeTop=False, maxDepth=14):
            n += 1
            if n > limit or time.time() - t0 > seconds:
                return
            try:
                name = (c.Name or "").strip()
                if not name or c.IsOffscreen:
                    continue
                r = c.BoundingRectangle
                if r.width() < 2 or r.height() < 2:
                    continue
                yield c, name, c.ControlTypeName, (r.xcenter(), r.ycenter())
            except Exception:
                continue

    def t_ui_list(self, window=None):
        try:
            auto, root = self._uia_root(window)
        except ImportError:
            return "UI Automation is not available; use the screenshot instead."
        out, seen, self._ui_map = [], set(), {}
        for _c, name, typ, pos in self._uia_walk(auto, root):
            if typ in INTERACTIVE and (typ, name) not in seen:
                seen.add((typ, name))
                n = len(out) + 1
                self._ui_map[n] = (pos[0], pos[1], name, typ)
                out.append(f"[{n}] {typ.replace('Control', '')}: {name[:60]}")
            if len(out) >= 70:
                break
        head = f"Window '{root.Name}'. Use the [id] with ui_click / ui_type:\n"
        if not out:
            return (f"Window '{root.Name}' does not expose its buttons (normal for Discord, browsers, Electron apps and "
                    "games). Use click or click_type with coordinates from the screenshot.")
        return head + "\n".join(out)

    def _uia_find(self, name, window=None):
        auto, root = self._uia_root(window)
        key, best = name.lower().strip(), None
        for c, nm, typ, pos in self._uia_walk(auto, root):
            low = nm.lower()
            if key not in low:
                continue
            score = (low == key) * 4 + (typ in INTERACTIVE) * 2 + (low.startswith(key)) * 1
            if best is None or score > best[0]:
                best = (score, nm, typ, pos)
                if score >= 6:
                    break
        if not best:
            raise RuntimeError(f"No control named '{name}'. Run ui_list or use the screenshot.")
        return best

    def _ui_target(self, id=None, name=None, window=None):
        if id is not None:
            item = self._ui_map.get(int(id))
            if not item:
                raise RuntimeError(f"No control with id {id}. Run ui_list first.")
            return item[2], item[3], (item[0], item[1])
        if not name:
            raise RuntimeError("Give an id from ui_list, or a control name.")
        _s, nm, typ, pos = self._uia_find(name, window)
        return nm, typ, pos

    def t_ui_click(self, id=None, name=None, window=None, double=False):
        try:
            nm, typ, (x, y) = self._ui_target(id, name, window)
        except ImportError:
            return "UI Automation is not available; use click with screenshot coordinates."
        self._gui().click(x, y, clicks=2 if double else 1)
        time.sleep(0.5)
        return f"Clicked {typ.replace('Control', '')} '{nm[:50]}'."

    def t_ui_type(self, text, id=None, name=None, window=None, enter=False):
        try:
            nm, typ, (x, y) = self._ui_target(id, name, window)
        except ImportError:
            return "UI Automation is not available; click the field, then use type_text."
        self._gui().click(x, y)
        time.sleep(0.3)
        self.t_type_text(text, enter=enter)
        return f"Typed into '{nm[:50]}'."

    # ---- games: real keyboard and mouse only ----
    @property
    def game_on(self):
        return self.game is not None

    def release_game(self):
        if self.game:
            self.game.release_all()

    def _foreground_title(self):
        if os.name != "nt":
            return ""
        u = ctypes.windll.user32
        h = u.GetForegroundWindow()
        n = u.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(h, buf, n + 1)
        return buf.value

    def _game_ready(self):
        if not self.game:
            raise RuntimeError("Game mode is off. Call game_mode first.")
        if self.game_window and self.game_window.lower() not in self._foreground_title().lower():
            self.t_focus_window(self.game_window)
            if self.game_window.lower() not in self._foreground_title().lower():
                raise RuntimeError(f"The game window '{self.game_window}' is not in front, so nothing was sent.")

    def t_game_mode(self, on=True, window=""):
        if not on:
            self.release_game()
            self.game, self.game_window = None, ""
            return "Game mode off. All keys and buttons released."
        if self.game:
            self.game_window = window or self.game_window
            return f"Game mode already on for '{self.game_window or 'any window'}'."
        if self.cfg.get("confirm_critical", True) and not self.confirm(
                f"Let Trilion play '{window or 'the game in front'}' with your keyboard and mouse? "
                "Only use this for single-player games: online games with anti-cheat may block it or ban you. "
                "Ctrl+Alt+S stops it instantly."):
            return "The user declined game mode."
        from .gameinput import GameInput, WinBackend
        backend = self.game_backend or WinBackend()
        self.game, self.game_window = GameInput(backend), window
        if window:
            self.t_focus_window(window)
        return f"Game mode on for '{window or 'the window in front'}'. Play with game_act, one short action at a time."

    def t_game_act(self, hold="", tap="", dx=0, dy=0, click="", scroll=0, ms=300, keep=False):
        self._game_ready()
        try:
            done = self.game.act(hold, tap, dx, dy, click, scroll, ms, keep, stop=self.cancelled)
        except ValueError as e:
            return f"Bad input: {e}"
        return "Done." if done else "Interrupted; everything released."

    def t_game_click(self, x, y, button="left", double=False):
        self._game_ready()
        sx, sy = screen.to_screen(x, y)
        self.game.click_at(sx, sy, button, double)
        return f"Clicked ({x},{y})."

    def t_game_release(self):
        self.release_game()
        return "Everything released."

    # ---- skills & memory ----
    def t_list_skills(self):
        return "\n".join(f"{s['name']}: {s['description']}" for s in self.skills.all()) or "(no skills)"

    def t_use_skill(self, name):
        got = self.skills.get(name)
        if not got:
            return f"No skill named '{name}'. Available:\n" + self.t_list_skills()
        body, scripts = got
        extra = f"\n[Scripts you can run with run_skill_script: {', '.join(scripts)}]" if scripts else ""
        return body[:3500] + extra

    def t_create_skill(self, name, description, instructions):
        d = self.skills.create(name, description, instructions)
        return f"Saved skill '{d.name}'. Folder: {d}"

    def t_run_skill_script(self, skill, script, args=""):
        import shlex
        p = self.skills.script_path(skill, script)
        argv = shlex.split(args, posix=False) if args else []
        suffix = p.suffix.lower()
        if suffix == ".ps1":
            r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(p), *argv],
                               capture_output=True, text=True, timeout=120, creationflags=NO_WINDOW)
        elif suffix in (".bat", ".cmd"):
            r = subprocess.run(["cmd", "/c", str(p), *argv], capture_output=True, text=True, timeout=120,
                               creationflags=NO_WINDOW)
        elif suffix == ".py":
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                exec(compile(p.read_text(encoding="utf-8"), str(p), "exec"), {"__name__": "__main__", "ARGS": argv})
            return buf.getvalue()[-2200:] or "(no output)"
        else:
            return "Unsupported script type."
        return f"exit {r.returncode}\n{(r.stdout + r.stderr).strip()[-2200:]}"

    def t_remember(self, fact):
        return self.memory.add(fact)

    def t_forget(self, fact):
        return self.memory.forget(fact)


# ---------------------------------------------------------------------------
# Strict reply format: {"say": "...", "action": null | {"tool": ..., "args": {...}}}
# The schema is built from the tool method signatures, so it can never drift from the code.
_NUM = {"x", "y", "w", "h", "x1", "y1", "x2", "y2", "amount", "seconds", "dx", "dy", "ms", "scroll"}
_INT = {"id"}
_BOOL = {"double", "enter", "on", "keep"}


_FAIL_START = ("no control", "no window", "unknown tool", "bad arguments", "bad input", "blocked", "game mode is off",
               "ui automation is not available", "no skill", "unsupported")


def is_failure(result):
    """True when a tool result means the action did not work (but not when the user simply said no)."""
    low = str(result).strip().lower()
    if low.startswith("the user declined"):
        return False
    return (low.startswith(_FAIL_START) or " failed:" in low or "does not expose its buttons" in low
            or "is not in front" in low)


LEGACY_TOOLS = {"search_site"}   # still works if called, but the model is not offered it (open_search replaces it)


def tool_specs(exclude=()):
    specs = {}
    for attr in dir(Tools):
        if not attr.startswith("t_") or attr[2:] in LEGACY_TOOLS or attr[2:] in exclude:
            continue
        props, req = {}, []
        for p in inspect.signature(getattr(Tools, attr)).parameters.values():
            if p.name == "self" or p.name.startswith("_"):
                continue
            typ = ("integer" if p.name in _INT else "number" if p.name in _NUM
                   else "boolean" if p.name in _BOOL or isinstance(p.default, bool) else "string")
            props[p.name] = {"type": typ}
            if p.default is inspect.Parameter.empty:
                req.append(p.name)
        specs[attr[2:]] = (props, req)
    return specs


def reply_schema(exclude=()):
    variants = []
    for name, (props, req) in sorted(tool_specs(exclude).items()):
        variants.append({
            "type": "object",
            "properties": {"tool": {"const": name},
                           "args": {"type": "object", "properties": props, "required": req,
                                    "additionalProperties": False}},
            "required": ["tool", "args"], "additionalProperties": False})
    return {"type": "object",
            "properties": {"say": {"type": "string"},
                           "action": {"anyOf": [{"type": "null"}, {"oneOf": variants}]}},
            "required": ["say", "action"], "additionalProperties": False}
