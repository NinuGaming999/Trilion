"""Manages a local llama.cpp server (vision-capable) and talks to it.

Everything is fetched on first run into %LOCALAPPDATA%/Trilion, so the .exe itself
stays small and starts fast."""
import json
import logging
import os
import re
import socket
import subprocess
import time
import zipfile

import requests

from ..paths import brain_info, sub
from .download import download, hf_files, hf_url

log = logging.getLogger("trilion.llama")
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


REL = "https://github.com/ggml-org/llama.cpp/releases"


def resolve_tag():
    """llama.cpp's 'latest' release can be a stub that only holds nightly-tag.txt;
    the real builds live under the bNNNN tag it points to."""
    r = requests.get(REL + "/latest", headers={"User-Agent": "Trilion"}, timeout=30)
    tag = r.url.rstrip("/").split("/")[-1]
    if re.fullmatch(r"b\d+", tag):
        return tag
    t = requests.get(f"{REL}/download/{tag}/nightly-tag.txt", headers={"User-Agent": "Trilion"}, timeout=30)
    t.raise_for_status()
    return t.text.strip()


def candidate_builds(tag):
    """(label, main zip url, optional runtime zip url), best first."""
    d = f"{REL}/download/{tag}/"
    return [
        ("CUDA 12.4", d + f"llama-{tag}-bin-win-cuda-12.4-x64.zip", d + "cudart-llama-bin-win-cuda-12.4-x64.zip"),
        ("Vulkan", d + f"llama-{tag}-bin-win-vulkan-x64.zip", None),
        ("CPU", d + f"llama-{tag}-bin-win-cpu-x64.zip", None),
    ]


def exists(url):
    try:
        return requests.head(url, allow_redirects=True, timeout=20, headers={"User-Agent": "Trilion"}).status_code == 200
    except requests.RequestException:
        return False


def strip_think(deltas):
    """Remove <think>...</think> blocks from a token stream (Qwen3.5 may emit them even when told not to)."""
    OPEN, CLOSE = "<think>", "</think>"
    buf, inside = "", False
    for d in deltas:
        buf += d
        while True:
            if not inside:
                i = buf.find(OPEN)
                if i >= 0:
                    if buf[:i]:
                        yield buf[:i]
                    buf, inside = buf[i + len(OPEN):], True
                    continue
                hold = next((k for k in range(min(len(OPEN) - 1, len(buf)), 0, -1) if OPEN.startswith(buf[-k:])), 0)
                if len(buf) > hold:
                    yield buf[:len(buf) - hold]
                    buf = buf[len(buf) - hold:]
                break
            j = buf.find(CLOSE)
            if j >= 0:
                buf, inside = buf[j + len(CLOSE):], False
                continue
            hold = next((k for k in range(min(len(CLOSE) - 1, len(buf)), 0, -1) if CLOSE.startswith(buf[-k:])), 0)
            buf = buf[len(buf) - hold:] if hold else ""
            break
    if buf and not inside:
        yield buf


def pick_files(names, quant, mm_pref):
    """Choose (model, projector) from a list of file names."""
    ggufs = [f for f in names if f.lower().endswith(".gguf")]
    mm = [f for f in ggufs if "mmproj" in f.lower()]
    models = [f for f in ggufs if "mmproj" not in f.lower() and quant.lower() in f.lower()
              and not re.search(r"-\d{5}-of-\d{5}", f)]
    models.sort(key=lambda f: ("ud-" in f.lower(), len(f)))  # plain quant before "UD-...XL" variants
    mm.sort(key=lambda f: (next((i for i, p in enumerate(mm_pref) if re.search(p, f.lower())), 9), len(f)))
    return (models[0] if models else None), (mm[0] if mm else None)


OOM_WORDS = ("out of memory", "cudamalloc", "failed to allocate", "outofdevicememory", "cuda error")
ARG_WORDS = ("invalid argument", "unknown argument", "unrecognized", "error: unknown", "invalid value")


class LlamaServer:
    def __init__(self, cfg):
        self.cfg = cfg
        self.brain = brain_info(cfg)
        self.proc = None
        self.port = None
        self.bin_dir = sub("llama")
        self.model_dir = sub("models", "llm") if self.brain["legacy_dir"] else sub("models", "llm", self.brain["key"])
        self.structured_ok = True
        self.variant = 0      # 0 = all flags, 1 = without optional flags, 2 = also low memory
        self.restarts = 0

    # ---------- files ----------
    def find_exe(self):
        for name in ("llama-server.exe", "llama-server"):
            for p in self.bin_dir.rglob(name):
                return p
        return None

    def ensure_binary(self, prog):
        if self.find_exe():
            prog(1, "Engine ready")
            return
        prog(0, "Finding llama.cpp engine…")
        tag = resolve_tag()
        label, url_main, url_rt = next((c for c in candidate_builds(tag) if exists(c[1])), (None,) * 3)
        if not url_main:
            raise RuntimeError(f"No Windows llama.cpp build found for {tag}")
        log.info("llama.cpp %s (%s): %s", tag, label, url_main)
        tmp = sub("downloads")
        zmain = download(url_main, tmp / url_main.split("/")[-1],
                         lambda d, t: prog(0.8 * d / max(t, 1), f"Downloading engine ({label})…"))
        zrt = None
        if url_rt:
            zrt = download(url_rt, tmp / url_rt.split("/")[-1],
                           lambda d, t: prog(0.8 + 0.15 * d / max(t, 1), "Downloading CUDA runtime…"))
        prog(0.96, "Unpacking engine…")
        for z in (zmain, zrt):
            if z:
                with zipfile.ZipFile(z) as zf:
                    zf.extractall(self.bin_dir)
                os.remove(z)
        if not self.find_exe():
            raise RuntimeError("llama-server not found after extraction")
        prog(1, "Engine ready")

    def _local_model(self):
        names = {p.name: p for p in self.model_dir.glob("*.gguf")}
        model, mm = pick_files(list(names), self.brain["quant"], self.brain["mm_pref"])
        if model and mm:
            return names[model], names[mm]
        return None

    def ensure_model(self, prog):
        if self._local_model():
            prog(1, "Brain model ready")
            return
        repo, quant = self.brain["repo"], self.brain["quant"]
        prog(0, f"Looking up brain model ({self.brain['key']})…")
        model, mm = pick_files(hf_files(repo), quant, self.brain["mm_pref"])
        if not model or not mm:
            raise RuntimeError(f"{repo} has no {quant} model + projector pair")
        download(hf_url(repo, model), self.model_dir / os.path.basename(model),
                 lambda d, t: prog(0.89 * d / max(t, 1), f"Downloading brain model… {d / 1e9:.1f} / {t / 1e9:.1f} GB"))
        download(hf_url(repo, mm), self.model_dir / os.path.basename(mm),
                 lambda d, t: prog(0.89 + 0.11 * d / max(t, 1), "Downloading vision module…"))
        prog(1, "Brain model ready")

    # ---------- process ----------
    def _kill_stale(self):
        pidf = sub("run") / "llama.pid"
        if pidf.exists():
            try:
                pid = int(pidf.read_text())
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True,
                                   creationflags=NO_WINDOW)
            except Exception:
                pass

    def build_cmd(self, exe, gguf, mm, port):
        ctx = int(self.cfg["context"])
        cmd = [str(exe), "-m", str(gguf), "--mmproj", str(mm), "--host", "127.0.0.1", "--port", str(port),
               "-ngl", str(self.cfg["gpu_layers"]), "--alias", "trilion"]
        if self.variant >= 2:
            ctx = min(ctx, 6144)
            cmd += ["--no-mmproj-offload"]
        cmd += ["-c", str(ctx)]
        if self.variant == 0:  # optional flags: dropped automatically if this llama.cpp build rejects them
            if self.brain["family"].startswith("qwen3"):
                cmd += ["--chat-template-kwargs", '{"enable_thinking":false}', "--reasoning-budget", "0"]
            else:
                cmd += ["--image-min-tokens", "1024"]
        return cmd

    def start(self):
        self._kill_stale()
        exe = self.find_exe()
        gguf, mm = self._local_model()
        self.port = _free_port()
        cmd = self.build_cmd(exe, gguf, mm, self.port)
        logf = open(sub("logs") / "llama-server.log", "ab")
        logf.write(f"\n===== start variant {self.variant}: {' '.join(cmd)}\n".encode())
        logf.flush()
        self.proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT,
                                     cwd=str(exe.parent), creationflags=NO_WINDOW)
        (sub("run") / "llama.pid").write_text(str(self.proc.pid))
        log.info("llama-server pid %s on port %s (variant %s)", self.proc.pid, self.port, self.variant)

    def _log_tail(self, n=1500):
        try:
            return (sub("logs") / "llama-server.log").read_text(errors="ignore")[-n:]
        except Exception:
            return ""

    def _recover(self):
        """The engine died while loading: pick the next, safer launch variant (max 2 restarts)."""
        tail = self._log_tail().lower()
        if self.restarts >= 2:
            return False
        if any(w in tail for w in OOM_WORDS) and self.variant < 2:
            self.variant = 2
        elif self.variant == 0:
            self.variant = 1
        else:
            return False
        self.restarts += 1
        log.warning("engine exited while loading; retrying with variant %s", self.variant)
        self.start()
        return True

    def wait_ready(self, prog, timeout=300):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.proc.poll() is not None:
                if self._recover():
                    t0 = time.time()
                    continue
                raise RuntimeError("The AI engine stopped while loading.\n" + self._log_tail(1200))
            try:
                if requests.get(f"http://127.0.0.1:{self.port}/health", timeout=1).status_code == 200:
                    self._check_vision()
                    prog(1, "Brain online")
                    return
            except requests.RequestException:
                pass
            el = time.time() - t0
            prog(min(0.95, el / 25), "Loading brain onto the GPU…" if self.variant < 2 else "Loading brain (low-memory mode)…")
            time.sleep(0.4)
        raise RuntimeError("Timed out waiting for the AI engine")

    def _check_vision(self):
        try:
            props = requests.get(f"http://127.0.0.1:{self.port}/props", timeout=3).json()
            mods = props.get("modalities")
            if mods is not None and not mods.get("vision", False):
                raise RuntimeError("The vision module did not load, so Trilion cannot see the screen. "
                                   "Delete the brain folder in %LOCALAPPDATA%\\Trilion\\models\\llm and relaunch.")
        except requests.RequestException:
            pass

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except Exception:
                self.proc.kill()

    # ---------- chat ----------
    def chat_stream(self, messages, cancel=None, max_tokens=450, temperature=None, schema=None):
        smp = self.brain["sampling"]
        body = {"model": "trilion", "messages": messages, "stream": True, "max_tokens": max_tokens,
                "temperature": smp["temperature"] if temperature is None else temperature,
                "top_p": smp["top_p"], "top_k": smp["top_k"], "cache_prompt": True}
        if self.brain["family"].startswith("qwen3"):
            body["chat_template_kwargs"] = {"enable_thinking": False}
        use_schema = schema is not None and self.structured_ok
        if use_schema:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "reply", "strict": True, "schema": schema}}
        try:
            yield from strip_think(self._stream(body, cancel))
        except requests.HTTPError as e:
            if not use_schema:
                raise
            log.warning("structured output rejected (%s); falling back to free text", e)
            self.structured_ok = False
            body.pop("response_format", None)
            yield from strip_think(self._stream(body, cancel))

    def _stream(self, body, cancel):
        with requests.post(f"http://127.0.0.1:{self.port}/v1/chat/completions", json=body,
                           stream=True, timeout=(5, 300)) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if cancel is not None and cancel.is_set():
                    return
                if not line or not line.startswith(b"data:"):
                    continue
                data = line[5:].strip()
                if data == b"[DONE]":
                    return
                try:
                    delta = json.loads(data)["choices"][0]["delta"].get("content")
                except Exception:
                    continue
                if delta:
                    yield delta
