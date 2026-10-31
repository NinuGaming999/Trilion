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

from ..paths import sub
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


class LlamaServer:
    def __init__(self, cfg):
        self.cfg = cfg
        self.proc = None
        self.port = None
        self.bin_dir = sub("llama")
        self.model_dir = sub("models", "llm")

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
        quant = self.cfg["llm_quant"].lower()
        ggufs = [p for p in self.model_dir.glob("*.gguf")]
        model = [p for p in ggufs if "mmproj" not in p.name.lower() and quant in p.name.lower()]
        mm = [p for p in ggufs if "mmproj" in p.name.lower()]
        if model and mm:
            mm.sort(key=lambda p: ("q8" not in p.name.lower(), "f16" not in p.name.lower()))
            return model[0], mm[0]
        return None

    def ensure_model(self, prog):
        if self._local_model():
            prog(1, "Brain model ready")
            return
        repo, quant = self.cfg["llm_repo"], self.cfg["llm_quant"]
        prog(0, "Looking up brain model…")
        files = [f for f in hf_files(repo) if f.endswith(".gguf")]
        model = [f for f in files if "mmproj" not in f.lower() and quant.lower() in f.lower()]
        mm = [f for f in files if "mmproj" in f.lower()]
        if not model or not mm:
            raise RuntimeError(f"{repo} has no {quant} model + mmproj pair")
        mm.sort(key=lambda f: ("q8" not in f.lower(), "f16" not in f.lower()))
        download(hf_url(repo, model[0]), self.model_dir / os.path.basename(model[0]),
                 lambda d, t: prog(0.86 * d / max(t, 1), f"Downloading brain model… {d / 1e9:.1f} / {t / 1e9:.1f} GB"))
        download(hf_url(repo, mm[0]), self.model_dir / os.path.basename(mm[0]),
                 lambda d, t: prog(0.86 + 0.14 * d / max(t, 1), "Downloading vision module…"))
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

    def start(self):
        self._kill_stale()
        exe = self.find_exe()
        gguf, mm = self._local_model()
        self.port = _free_port()
        cmd = [str(exe), "-m", str(gguf), "--mmproj", str(mm), "--host", "127.0.0.1",
               "--port", str(self.port), "-ngl", str(self.cfg["gpu_layers"]),
               "-c", str(self.cfg["context"]), "--alias", "trilion"]
        logf = open(sub("logs") / "llama-server.log", "wb")
        self.proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT,
                                     cwd=str(exe.parent), creationflags=NO_WINDOW)
        (sub("run") / "llama.pid").write_text(str(self.proc.pid))
        log.info("llama-server pid %s on port %s", self.proc.pid, self.port)

    def wait_ready(self, prog, timeout=300):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.proc.poll() is not None:
                tail = ""
                try:
                    tail = (sub("logs") / "llama-server.log").read_text(errors="ignore")[-1200:]
                except Exception:
                    pass
                raise RuntimeError("The AI engine stopped while loading.\n" + tail)
            try:
                if requests.get(f"http://127.0.0.1:{self.port}/health", timeout=1).status_code == 200:
                    self._check_vision()
                    prog(1, "Brain online")
                    return
            except requests.RequestException:
                pass
            el = time.time() - t0
            prog(min(0.95, el / 25), "Loading brain onto the GPU…")
            time.sleep(0.4)
        raise RuntimeError("Timed out waiting for the AI engine")

    def _check_vision(self):
        try:
            props = requests.get(f"http://127.0.0.1:{self.port}/props", timeout=3).json()
            mods = props.get("modalities")
            if mods is not None and not mods.get("vision", False):
                raise RuntimeError("The vision module did not load, so Trilion cannot see the screen. "
                                   "Delete %LOCALAPPDATA%\\Trilion\\models\\llm and relaunch.")
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
    def chat_stream(self, messages, cancel=None, max_tokens=450, temperature=0.3):
        body = {"model": "trilion", "messages": messages, "stream": True, "max_tokens": max_tokens,
                "temperature": temperature, "top_p": 0.9, "cache_prompt": True}
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
