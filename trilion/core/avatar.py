"""The 3D avatar page: serves the web app and the model, and lets the AI drive her in-character reactions.

Everything is served by the local HUD server on 127.0.0.1 - see hud.py for the host/token protections."""
import json
import logging
import mimetypes
import re
import sys
import threading
import time
import wave
import zipfile
from pathlib import Path

from ..paths import sub
from .download import download

log = logging.getLogger("trilion.avatar")

MODEL_ZIP_URL = "https://raw.githubusercontent.com/NinuGaming999/Trilion/main/genshin-impact-arlecchino.zip"
MODEL_FBX = "source/arlecchino.fbx"
STATIC_EXT = {".js", ".html", ".css", ".json", ".png", ".jpg", ".txt", ".svg", ".wasm"}
MODEL_EXT = {".fbx", ".png", ".jpg", ".jpeg", ".tga", ".json"}
mimetypes.add_type("text/javascript", ".js")


def web_dir():
    base = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parents[2]
    return Path(base) / "trilion" / "web" / "avatar"


def safe_join(base, rel):
    """base/rel, or None if rel tries to leave base (.., absolute paths, backslashes, drive letters)."""
    rel = rel.replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/") or ":" in rel or "\x00" in rel:
        return None
    p = (Path(base) / rel).resolve()
    try:
        p.relative_to(Path(base).resolve())
    except ValueError:
        return None
    return p if p.is_file() else None


def safe_extract(zip_path, dest):
    """Extract a zip without letting entries escape `dest` (zip-slip)."""
    dest = Path(dest).resolve()
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            try:
                (dest / info.filename).resolve().relative_to(dest)
            except ValueError:
                raise RuntimeError(f"unsafe path in zip: {info.filename}")
        z.extractall(dest)


def slug(text):
    return re.sub(r"[^a-z]+", "-", text.lower()).strip("-") or "line"


class AvatarService:
    def __init__(self, cfg, hud, model_dir=None, llm=None, assistant=None, tts=None):
        self.cfg, self.hud = cfg, hud
        self.assistant, self.tts = assistant, tts
        self.enabled = True
        self.mind = AvatarMind(cfg, llm, assistant) if (llm and assistant) else None
        self.cache_dir = sub("avatars", "cache")
        self.model_dir = Path(model_dir) if model_dir else sub("avatars", "arlecchino")
        self.status = {"model_ready": False, "downloading": False, "error": None}
        self._lock = threading.Lock()
        hud.add_route("/avatar", self.handle)
        hud.state_hooks.append(self.state_extra)
        self.refresh_status()

    # ---- model files ----
    def model_present(self):
        return (self.model_dir / MODEL_FBX).is_file()

    def refresh_status(self):
        self.status["model_ready"] = self.model_present()
        return self.status

    def ensure_model(self, prog=None):
        """Make sure the FBX + textures are on disk: local folder, the repo copy (dev), or download from GitHub."""
        if self.model_present():
            return True
        with self._lock:
            if self.model_present():
                return True
            self.status.update(downloading=True, error=None)
            try:
                repo_zip = Path(__file__).resolve().parents[2] / "genshin-impact-arlecchino.zip"
                if repo_zip.is_file():
                    zpath = repo_zip
                else:
                    zpath = download(self.cfg.get("avatar_zip_url") or MODEL_ZIP_URL, sub("downloads") / "avatar-model.zip", prog)
                safe_extract(zpath, self.model_dir)
                if not self.model_present():
                    raise RuntimeError("the zip does not contain source/arlecchino.fbx")
            except Exception as e:
                log.exception("avatar model setup failed")
                self.status["error"] = str(e)
            finally:
                self.status["downloading"] = False
                self.refresh_status()
        return self.status["model_ready"]

    def ensure_model_async(self):
        if not self.model_present() and not self.status["downloading"]:
            threading.Thread(target=self.ensure_model, daemon=True).start()

    # ---- state / fillers ----
    def state_extra(self):
        return {"avatar": self.mind.public() if self.mind else {"line": None}}

    def prepare_fillers(self):
        """Synthesise the short stock lines once so the page can play them instantly (no waiting for the AI)."""
        if not self.tts:
            return

        def run():
            import numpy as np
            for text in FILLER_LINES:
                p = self.cache_dir / (slug(text) + ".wav")
                if p.exists():
                    continue
                try:
                    samples, sr = self.tts.synth(text, self.cfg.get("avatar_voice") or None)
                    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1, 1) * 32767).astype("<i2").tobytes()
                    with wave.open(str(p), "wb") as w:
                        w.setnchannels(1)
                        w.setsampwidth(2)
                        w.setframerate(int(sr))
                        w.writeframes(pcm)
                except Exception:
                    log.exception("filler synth failed: %s", text)
        threading.Thread(target=run, daemon=True).start()

    # ---- HTTP ----
    def _file(self, base, rel, exts, cache=0):
        p = safe_join(base, rel)
        if not p or p.suffix.lower() not in exts:
            return 404, b"not found", "text/plain"
        ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype == "application/json":
            ctype += "; charset=utf-8"
        body = p.read_bytes()
        return (200, body, ctype, {"Cache-Control": f"public, max-age={cache}"}) if cache else (200, body, ctype)

    def page(self):
        html = (web_dir() / "index.html").read_text(encoding="utf-8")
        conf = {"model": "/avatar/model/" + MODEL_FBX, "name": "Trilion"}
        return html.replace("__TOKEN__", self.hud.token).replace("__CONFIG__", json.dumps(conf))

    def handle(self, method, path, query, headers, body):
        if not self.enabled:
            return None
        if method == "GET":
            if path in ("/avatar", "/avatar/"):
                self.ensure_model_async()
                return 200, self.page().encode("utf-8"), "text/html; charset=utf-8"
            if path == "/avatar/status":
                return 200, json.dumps(self.refresh_status()).encode(), "application/json"
            if path.startswith("/avatar/static/"):
                return self._file(web_dir(), path[len("/avatar/static/"):], STATIC_EXT)
            if path.startswith("/avatar/model/"):
                return self._file(self.model_dir, path[len("/avatar/model/"):], MODEL_EXT, cache=3600)
            if path.startswith("/avatar/audio/"):
                name = path[len("/avatar/audio/"):]
                if re.fullmatch(r"[a-z\-]+\.wav", name):
                    return self._file(self.cache_dir, name, {".wav"}, cache=3600)
        if method == "POST":
            if path == "/avatar/event" and self.mind:
                ok = self.mind.handle(body if isinstance(body, dict) else {})
                return 200, json.dumps({"ok": ok}).encode(), "application/json"
            if path == "/avatar/say" and self.assistant:
                text = str((body or {}).get("text", "")).strip()[:300]
                if text:
                    self.assistant.submit_text(text)
                return 200, b'{"ok": true}', "application/json"
        return None


# ======================================================================================================== AI mind
EMOTIONS = ["neutral", "curious", "amused", "annoyed", "angry", "furious", "sad", "calm"]
GESTURES = ["none", "nod", "shake_head", "glare", "turn_away", "sigh", "point", "tilt", "shrug"]
REPLY_SCHEMA = {
    "type": "object",
    "properties": {"say": {"type": "string"}, "emotion": {"enum": EMOTIONS}, "gesture": {"enum": GESTURES}},
    "required": ["say", "emotion", "gesture"], "additionalProperties": False}

PERSONA = """You are Trilion, an AI assistant that lives on the user's PC. On the avatar page the user sees you as a tall, \
composed woman with silver-and-black hair and a red-and-black coat. Your character: calm, dry, controlled, quietly \
intimidating, with a cold sense of humour. You like order and you do not like being touched without permission.
You answer a user's touches in character with ONE short sentence (at most 14 words), no stage directions, no emoji.
Moods: calm = curious or mildly amused; annoyed = a cold warning; angry = sharp and icy menace; furious = clipped, \
frosty, final. After a cool-down give a grudging, dry forgiveness. Menace stays theatrical and light: never graphic, \
never cruel, never insulting the person, never a real threat. Vary your wording; do not repeat earlier lines.
Reply ONLY with JSON: {"say": ..., "emotion": ..., "gesture": ...}."""

# stock lines the page plays instantly; mind.js keeps the same list (a test checks they match)
FILLER_LINES = ["...?", "Hm.", "Yes?", "Hands to yourself.", "Don't.", "Hm. Careful.", "That is enough.",
                "You test my patience.", "Once more, and I leave.", "Enough!", "Insolent.", "Do not touch me again.",
                "...Better.", "Hm. Good.", "Now, where were we."]


class AvatarMind:
    """Turns page events into in-character lines. The page reacts instantly on its own; this adds the AI's words."""
    MIN_GAP = {"touch": 4.0, "cooled": 20.0, "idle": 90.0, "hello": 600.0}

    def __init__(self, cfg, llm, assistant, clock=time.time):
        self.cfg, self.llm, self.assistant, self.clock = cfg, llm, assistant, clock
        self.line, self._id, self.recent, self.last = None, 0, [], {}
        self.busy = False
        self.lock = threading.Lock()

    def public(self):
        return {"line": self.line}

    def handle(self, ev):
        """Called from the HTTP thread; never blocks. Returns True if an AI reaction was started."""
        kind = str(ev.get("type", ""))
        if kind not in self.MIN_GAP:
            return False
        now = self.clock()
        with self.lock:
            if self.busy or now - self.last.get(kind, -1e9) < self.MIN_GAP[kind]:
                return False
            if getattr(self.assistant, "busy", False):          # never talk over a real task
                return False
            self.busy = True
            self.last[kind] = now
        threading.Thread(target=self._run, args=(ev,), daemon=True).start()
        return True

    def build_messages(self, ev):
        facts = {k: ev[k] for k in ("type", "zone", "kind", "level", "anger", "count", "sulking", "snap") if k in ev}
        facts["earlier_lines"] = self.recent[-3:]
        return [{"role": "system", "content": PERSONA}, {"role": "user", "content": json.dumps(facts)}]

    @staticmethod
    def parse(text):
        """JSON reply -> (say, emotion, gesture); tolerant of plain text."""
        say, emo, ges = "", "neutral", "none"
        try:
            i, j = text.find("{"), text.rfind("}")
            obj = json.loads(text[i:j + 1])
            say, emo, ges = str(obj.get("say", "")), obj.get("emotion", "neutral"), obj.get("gesture", "none")
        except Exception:
            say = text.strip().strip('"')
        say = " ".join(say.split())[:140]
        return say, emo if emo in EMOTIONS else "neutral", ges if ges in GESTURES else "none"

    def _run(self, ev):
        try:
            text = "".join(self.llm.chat_stream(self.build_messages(ev), schema=REPLY_SCHEMA, max_tokens=90, temperature=0.85))
            say, emo, ges = self.parse(text)
            if not say:
                return
            self._id += 1
            self.line = {"id": self._id, "text": say, "emotion": emo, "gesture": ges, "t": self.clock()}
            self.recent.append(say)
            if self.cfg.get("avatar_speak", True):
                self.assistant.say_direct(say)
        except Exception:
            log.exception("avatar reaction failed")
        finally:
            self.busy = False
