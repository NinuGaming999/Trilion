"""Paths, config and logging. Kept dependency-free so it imports instantly."""
import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import APP_NAME

DEFAULTS = {
    # Brain: any vision-capable GGUF repo on Hugging Face that llama.cpp supports.
    "llm_repo": "ggml-org/Qwen2.5-VL-7B-Instruct-GGUF",
    "llm_quant": "Q4_K_M",
    "context": 12288,
    "gpu_layers": 99,
    # Ears (runs on CPU so the GPU stays free for the brain)
    "whisper_repo": "Systran/faster-whisper-small",
    "whisper_language": "en",  # None = auto-detect (less reliable on short phrases)
    # Voice
    "voice": "af_heart",
    # Behaviour
    "wake_word": False,       # if on: say "Trilion ..." (stays awake 45 s after each reply)
    "mic_device": None,       # input device name; None = Windows default
    "config_version": 2,
    "watch_screen": True,     # attach a fresh screenshot to every request
    "confirm_risky": True,    # ask before shell commands / writing files
    "max_steps": 8,
    "screen_max_width": 1280,
}


def app_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(Path.home(), ".local", "share")
    p = Path(base) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def sub(*names) -> Path:
    p = app_dir().joinpath(*names)
    p.mkdir(parents=True, exist_ok=True)
    return p


class Config(dict):
    def __init__(self):
        super().__init__(DEFAULTS)
        self.path = app_dir() / "config.json"
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text(encoding="utf-8"))
                self.update(saved)
                if saved.get("config_version", 1) < 2:  # v0.1 defaults were too strict
                    self.update(wake_word=False, whisper_language="en", context=12288,
                                screen_max_width=1280, config_version=2)
                    self.save()
            except Exception:
                pass
        else:
            self.save()

    def save(self):
        try:
            self.path.write_text(json.dumps(dict(self), indent=2), encoding="utf-8")
        except Exception:
            pass


def setup_logging():
    log = logging.getLogger("trilion")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fh = RotatingFileHandler(sub("logs") / "trilion.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(fh)
    return log
