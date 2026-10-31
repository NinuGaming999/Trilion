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


def collect_logs(n=160):
    """Text for the 'Copy log' buttons: app log + engine log tail + settings."""
    import platform
    parts = [f"Trilion {__import__('trilion').__version__} / {platform.platform()}"]
    for title, f in (("trilion.log", "trilion.log"), ("llama-server.log", "llama-server.log")):
        try:
            lines = (sub("logs") / f).read_text(encoding="utf-8", errors="ignore").splitlines()[-n:]
            parts.append(f"===== {title} (last {len(lines)} lines) =====\n" + "\n".join(lines))
        except Exception:
            parts.append(f"===== {title}: (none) =====")
    try:
        parts.append("===== config.json =====\n" + (app_dir() / "config.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    return "\n\n".join(parts)


def open_logs_folder():
    import os
    try:
        os.startfile(str(sub("logs")))
    except Exception:
        pass


_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except Exception:
        return False


def set_autostart(on):
    """Start Trilion (hidden in the tray) when you sign in to Windows."""
    import sys
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, f'"{sys.executable}" --minimized')
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False
