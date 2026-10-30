"""Text-to-speech (Kokoro, ONNX, runs on CPU)."""
import logging

from ..paths import sub
from .download import download

log = logging.getLogger("trilion.tts")
BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = ["kokoro-v1.0.onnx", "voices-v1.0.bin"]


def ensure_voice(prog):
    d = sub("models", "kokoro")
    for i, f in enumerate(FILES):
        download(BASE + f, d / f, lambda dn, t, i=i: prog((i + dn / max(t, 1)) / len(FILES), "Downloading voice…"))
    prog(1, "Voice ready")
    return d


class TTS:
    def __init__(self, model_dir, cfg):
        from kokoro_onnx import Kokoro
        self.k = Kokoro(str(model_dir / FILES[0]), str(model_dir / FILES[1]))
        self.voice = cfg["voice"]
        self.k.create("Ready.", voice=self.voice, speed=1.0, lang="en-us")  # warm-up

    def synth(self, text):
        samples, sr = self.k.create(text, voice=self.voice, speed=1.05, lang="en-us")
        return samples, sr
