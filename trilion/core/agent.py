"""The assistant loop: hear -> see -> think -> speak/act, streaming sentence by sentence."""
import json
import logging
import queue
import re
import threading
import time

from . import screen
from .memory import Memory
from .skills import Skills
from .tools import SCREEN_TOOLS, TOOL_DOCS, Tools

log = logging.getLogger("trilion.agent")

WAKE_RE = re.compile(r"\b(tri+l+[iy]?[oae]n|tri+l+ing|tri+\s?lion|try\s?lion|tri+\s?leon|trillion|trillian|trilian|trylon)\b[,.!?]?", re.I)
ACTION_RE = re.compile(r"<action>\s*(\{.*?\})\s*</action>", re.S)

SYSTEM = f"""You are Trilion, a friendly voice assistant living on the user's Windows PC. \
You can SEE their screen (a screenshot is attached to their messages) and CONTROL the PC with tools.

Your replies are spoken aloud, so: 1-3 short sentences, plain words, no markdown, no lists, no emojis.

To use tools, end your reply with one or more action tags, exactly like this:
<action>{{"tool": "<tool name>", "args": {{<arguments from the tool list>}}}}</action>
You will then receive the results and a fresh screenshot, and continue. When the task is finished, \
reply normally with no action tag.
Never write a tool name as plain words; a command only works inside the action tag.
Only use a tool when the user asked you to DO something. For questions, chat, or unclear speech, just answer in words (or ask what they mean) and do NOT use any tool. Say briefly what you are about to do before acting.

You can do almost anything on this PC: open and operate apps, browse and search the web, manage files, \
run PowerShell/cmd commands for system tasks, and write Python. Break big jobs into steps and keep going \
until it is done; do not give up after one failed try.

Rules:
- NEVER make up links or file paths. For videos use play_youtube; for anything else use search_site or web_search first.
- If the request is vague (for example "open a video" or "play something"), ask what they want instead of guessing.
- The screenshot never shows your own window. If text is small or unclear, use zoom on that region before answering.
- Click coordinates are pixels in the screenshot image you were shown (its size is given).
- Prefer open_app and keyboard shortcuts over clicking; they are more reliable.
- Check the new screenshot before claiming something worked. If it did not, try another way or ask.
- NEVER invent or guess a link or a video. To find something, use open_search or web_search and open only what you actually found, then look at the screen to confirm it is the right thing.
- When a request matches a skill in your skills list, call use_skill FIRST and follow its steps.
- Prefer ui_list / ui_click / ui_type (controls by name) over pixel clicks. Fall back to the screenshot if they fail.
- When the user tells you a lasting fact or preference ("remember...", their name, city, habits), call remember.
- After you work out a useful multi-step procedure, offer to save it with create_skill.
- Never run destructive commands (deleting, formatting, killing system processes) unless clearly asked.
- If the request is unclear, ask one short question.

Tools:
{TOOL_DOCS}
"""


TOOL_NAMES = ("open_app", "open_url", "open_search", "play_youtube", "search_site", "look", "zoom", "ui_list",
              "ui_click", "ui_type", "click", "drag", "move", "scroll", "type_text", "press_keys", "wait",
              "list_windows", "focus_window", "clipboard_get", "clipboard_set", "web_search", "fetch_url",
              "list_dir", "read_file", "write_file", "run_shell", "run_python", "use_skill", "list_skills",
              "create_skill", "run_skill_script", "remember", "forget")
# only names with an underscore are unambiguous (plain words like "look" or "wait" are normal speech)
TOOL_WORD_RE = re.compile(r"\b(" + "|".join(n for n in TOOL_NAMES if "_" in n) + r")\b")
MARKERS = ("<action>", "```", '{"tool"', "{ \"tool\"", "{'tool'")
_DEC = json.JSONDecoder()


def _norm(d):
    if not isinstance(d, dict) or "tool" not in d:
        return None
    args = d.get("args")
    if not isinstance(args, dict):
        args = {k: v for k, v in d.items() if k not in ("tool", "args")}
    return {"tool": str(d["tool"]).strip(), "args": args}


def parse_actions(text):
    """Accept the proper <action>{...}</action> form, but also the sloppy forms small models produce:
    bare/fenced JSON, 'open_app(name="notepad")', or 'open app notepad'."""
    out = []
    for m in ACTION_RE.finditer(text):
        try:
            d = _norm(json.loads(m.group(1)))
        except Exception:
            d = None
        out.append(d or {"tool": "_bad", "args": {}, "raw": m.group(1)})
    if out:
        return out
    for m in re.finditer(r"\{", text):  # bare or fenced JSON anywhere in the reply
        try:
            obj, _ = _DEC.raw_decode(text[m.start():])
        except Exception:
            continue
        d = _norm(obj)
        if d:
            out.append(d)
    if out:
        return out
    m = re.search(r"\b(open[_ ]app)\b\s*[:(=]?\s*(?:name\s*=\s*)?[\"']?([A-Za-z0-9 ._:\\/+-]{1,60}?)[\"')]*\s*(?:[.\n]|$)", text, re.I)
    if m and m.group(2).strip():
        return [{"tool": "open_app", "args": {"name": m.group(2).strip()}}]
    m = re.search(r"\b(open[_ ]url)\s*[:(=]?\s*(?:url\s*=\s*)?[\"']?(https?://[^\s\"')]+)", text, re.I)
    if m:
        return [{"tool": "open_url", "args": {"url": m.group(2)}}]
    return out


def strip_actions(text):
    t = ACTION_RE.sub("", text)
    cut = len(t)
    for mk in MARKERS:
        i = t.find(mk)
        if i >= 0:
            cut = min(cut, i)
    t = t[:cut]
    t = "\n".join(l for l in t.splitlines() if not TOOL_WORD_RE.search(l) and not re.search(r"\bopen app\b", l, re.I))
    return t.strip()


def clean_for_speech(s):
    s = re.sub(r"[*_`#>]+", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


class Streamer:
    """Turns a token stream into whole sentences (ignoring <action> blocks)."""

    def __init__(self, emit):
        self.emit, self.text, self.spoken = emit, "", 0

    def _visible(self, final):
        cut = len(self.text)
        for mk in MARKERS:
            i = self.text.find(mk)
            if i >= 0:
                cut = min(cut, i)
        if cut < len(self.text):
            return self.text[:cut]
        if not final:  # hold back a possible half-typed marker at the very end
            for j in range(max(0, len(self.text) - 8), len(self.text)):
                tail = self.text[j:]
                if any(mk.startswith(tail) for mk in MARKERS):
                    return self.text[:j]
        return self.text

    def _say(self, sentence):
        if TOOL_WORD_RE.search(sentence) or re.search(r"\bopen app\b", sentence, re.I):
            return  # the model is "reading out" a command instead of running it: never speak that
        self.emit(sentence)

    def feed(self, delta):
        self.text += delta
        vis = self._visible(False)
        seg = vis[self.spoken:]
        end = 0
        for m in re.finditer(r"[.!?]\s|\n", seg):
            end = m.end()
        if end:
            self._say(seg[:end])
            self.spoken += end

    def finish(self):
        vis = self._visible(True)
        rest = vis[self.spoken:]
        if rest.strip():
            self._say(rest)
        self.spoken = len(vis)


class Speaker:
    def __init__(self, tts, player, bridge):
        self.tts, self.player, self.bridge = tts, player, bridge
        self.q = queue.Queue()
        self.pending = 0
        self.lock = threading.Lock()
        self.cancelled = False
        threading.Thread(target=self._run, daemon=True).start()

    def say(self, text):
        text = clean_for_speech(text)
        if not text:
            return
        with self.lock:
            self.pending += 1
        self.q.put(text)

    def _run(self):
        while True:
            text = self.q.get()
            try:
                if not self.cancelled:
                    samples, sr = self.tts.synth(text)
                    if not self.cancelled:
                        self.bridge.caption.emit(text)
                        self.player.play(samples, sr)
            except Exception:
                log.exception("tts failed")
            finally:
                with self.lock:
                    self.pending -= 1

    def wait_done(self, timeout=180):
        end = time.time() + timeout
        while (self.pending > 0 or self.player.busy()) and time.time() < end and not self.cancelled:
            time.sleep(0.05)

    def stop(self):
        self.cancelled = True
        while True:
            try:
                self.q.get_nowait()
                with self.lock:
                    self.pending -= 1
            except queue.Empty:
                break
        self.player.stop()

    def reset(self):
        self.cancelled = False


class Assistant:
    def __init__(self, rt, bridge):
        self.rt, self.cfg, self.bridge = rt, rt.cfg, bridge
        self.speaker = Speaker(rt.tts, rt.player, bridge)
        self.skills, self.memory = Skills(), Memory()
        self.tools = Tools(self.cfg, bridge.ask, self.skills, self.memory, lambda: self.cancel.is_set())
        self.q = queue.Queue()
        self.cancel = threading.Event()
        self.history = []
        self.busy = False
        self.mic_enabled = True
        self.unmute_at = 0.0
        self.last_active = 0.0
        rt.listener.gate = self._ignore_audio
        rt.listener.on_utterance = self.on_audio
        threading.Thread(target=self._loop, daemon=True).start()

    # ---- inputs ----
    def _ignore_audio(self):
        return (not self.mic_enabled) or self.busy or self.rt.player.busy() or time.time() < self.unmute_at

    def on_audio(self, audio, forced=False):
        self.busy = True
        self.q.put(("audio", audio, forced))

    def submit_text(self, text):
        self.busy = True
        self.q.put(("text", text, True))

    def stop(self):
        self.cancel.set()
        self.speaker.stop()

    # ---- main loop ----
    def _state(self, s):
        self.bridge.state.emit(s)

    def _loop(self):
        while True:
            kind, payload, forced = self.q.get()
            try:
                self.cancel.clear()
                self.speaker.reset()
                text = payload
                if kind == "audio":
                    self._state("thinking")
                    text = self.rt.stt.transcribe(payload)
                    if not text:
                        if forced:
                            self.bridge.message.emit("heard", "(could not make out any words)")
                        continue
                    if not forced and len(text.split()) < 2:
                        from . import intents
                        if not intents.match(text):
                            log.info("ignored one-word noise: %s", text)
                            continue
                    active = time.time() - self.last_active < 45
                    if self.cfg.get("wake_word", False) and not forced and not active and not WAKE_RE.search(text):
                        log.info("ignored (no wake word): %s", text)
                        self.bridge.message.emit("heard", f'Heard "{text}" - say "Trilion" first, or turn off Wake word.')
                        continue
                    stripped = WAKE_RE.sub("", text, count=1).strip(" ,.!?")
                    text = stripped or "(The user just said your name. Greet them briefly.)"
                self.last_active = time.time()
                self._turn(text, show_user=kind == "audio" or True)
            except Exception as e:
                log.exception("turn failed")
                self.bridge.message.emit("error", str(e))
                self.speaker.say("Sorry, something went wrong.")
            finally:
                self.speaker.wait_done()
                self.last_active = time.time()
                self.unmute_at = time.time() + 0.6
                self.busy = not self.q.empty()
                self.bridge.caption.emit("")
                self._state("idle")

    def _user_msg(self, text, shot=True):
        if not shot:
            return {"role": "user", "content": text}
        b64, (w, h) = screen.grab(self.cfg.get("screen_max_width", 1280))
        return {"role": "user", "content": [
            {"type": "text", "text": f"{text}\n[Screenshot attached, {w}x{h} px]"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]}

    def _messages(self):
        last_img = max((i for i, m in enumerate(self.history) if isinstance(m["content"], list)), default=-1)
        extra = "\n\n".join(b for b in (self.skills.prompt_block(), self.memory.prompt_block()) if b)
        out = [{"role": "system", "content": SYSTEM + ("\n" + extra if extra else "")}]
        for i, m in enumerate(self.history):
            c = m["content"]
            if isinstance(c, list) and i != last_img:
                c = " ".join(p["text"] for p in c if p["type"] == "text") + " [older screenshot omitted]"
            out.append({"role": m["role"], "content": c})
        return out

    def _trim(self):
        self.history = self.history[-14:]
        while self.history and self.history[0]["role"] != "user":
            self.history.pop(0)

    def _quick(self, text):
        """Simple commands run instantly without asking the model."""
        from . import intents
        try:
            hit = intents.match(text)
        except Exception:
            return False
        if not hit:
            return False
        speech, action = hit
        note = ""
        if action:
            self._state("acting")
            self.bridge.message.emit("action", f"{action['tool']} {json.dumps(action['args'], ensure_ascii=False)[:90]}")
            res = self.tools.run(action)
            bad = res.lower().startswith(("blocked", "unknown", "bad arguments")) or " failed:" in res.lower()
            if bad:
                speech = "Sorry, that did not work."
                self.bridge.message.emit("error", res[:200])
            note = f" [did {action['tool']}: {res[:80]}]"
        self.bridge.message.emit("assistant", speech)
        self._speak(speech)
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": speech + note})
        self._trim()
        return True

    def _speak(self, sentence):
        self._state("speaking")
        self.speaker.say(sentence)

    def _turn(self, text, show_user=True):
        self.bridge.message.emit("user", text)
        self.tools.note_text(text)
        if self._quick(text):
            return
        self._state("thinking")
        self.history.append(self._user_msg(text, self.cfg.get("watch_screen", True)))
        last_sig = None
        for _ in range(int(self.cfg.get("max_steps", 8))):
            if self.cancel.is_set():
                break
            streamer, full = Streamer(self._speak), ""
            for delta in self.rt.llm.chat_stream(self._messages(), cancel=self.cancel):
                full += delta
                streamer.feed(delta)
            streamer.finish()
            self.history.append({"role": "assistant", "content": full})
            said = strip_actions(full)
            if said:
                self.bridge.message.emit("assistant", said)
            actions = parse_actions(full)
            if not actions or self.cancel.is_set():
                break
            sig = json.dumps(actions, sort_keys=True, ensure_ascii=False)
            if sig == last_sig:  # the model is looping on the same command: stop instead of repeating it
                self._speak("I seem to be repeating myself, so I stopped.")
                break
            last_sig = sig
            self.speaker.wait_done()
            self._state("acting")
            results, need_shot = [], False
            for a in actions[:4]:
                if self.cancel.is_set():
                    results.append("Stopped by the user.")
                    break
                if a.get("tool") == "_bad":
                    results.append("Could not parse your action JSON; use valid JSON.")
                    continue
                self.bridge.message.emit("action", f"{a.get('tool')} {json.dumps(a.get('args', {}), ensure_ascii=False)[:90]}")
                results.append(f"{a.get('tool')}: {self.tools.run(a)}")
                need_shot |= a.get("tool") in SCREEN_TOOLS
            msg = ("Tool results:\n" + "\n".join(results) +
                   "\nIf the user's request is now done, reply with ONE short spoken sentence and NO action tag. "
                   "Never repeat an action that already succeeded.")
            um = self._user_msg(msg, need_shot or self.cfg.get("watch_screen", True))
            if self.tools.extra_image:
                b64z, (zw, zh) = self.tools.extra_image
                self.tools.extra_image = None
                if isinstance(um["content"], str):
                    um["content"] = [{"type": "text", "text": um["content"]}]
                um["content"][0]["text"] += f"\n[Close-up image attached, {zw}x{zh}]"
                um["content"].append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64z}"}})
            self.history.append(um)
            self._state("thinking")
        self._trim()
