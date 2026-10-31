"""Speech-to-text (faster-whisper, CPU int8 so the GPU stays free for the brain)."""
import logging
import os

from ..paths import sub
from .download import download, hf_files, hf_url

log = logging.getLogger("trilion.stt")
SKIP = {".gitattributes", "README.md"}


def ensure_whisper(cfg, prog):
    repo = cfg["whisper_repo"]
    d = sub("models", "whisper", repo.split("/")[-1])
    if (d / "model.bin").exists() and not list(d.glob("*.part")):
        prog(1, "Ears ready")
        return d
    files = [f for f in hf_files(repo) if f not in SKIP and "/" not in f]
    for i, f in enumerate(files):
        download(hf_url(repo, f), d / f,
                 lambda dn, t, i=i: prog((i + dn / max(t, 1)) / len(files), "Downloading speech model…"))
    prog(1, "Ears ready")
    return d


class STT:
    def __init__(self, model_dir, cfg):
        from faster_whisper import WhisperModel
        self.cfg = cfg
        threads = max(2, min(8, (os.cpu_count() or 4) // 2))
        self.model = WhisperModel(str(model_dir), device="cpu", compute_type="int8", cpu_threads=threads)

    def transcribe(self, audio):
        import numpy as np
        peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
        if peak > 1e-4:  # quiet mics: bring speech up to a healthy level
            audio = np.clip(audio * min(0.8 / peak, 30.0), -1, 1).astype(np.float32)
        segs, _ = self.model.transcribe(audio, language=self.cfg.get("whisper_language"), beam_size=1,
                                        condition_on_previous_text=False, vad_filter=False,
                                        initial_prompt="Trilion, open Notepad. Trilion, what is on my screen?")
        text = " ".join(s.text.strip() for s in segs if s.no_speech_prob < 0.85).strip()
        if len(text) < 2 or text.lower().strip(" .!") in {"you", "thank you", "thanks for watching", "bye"}:
            return ""
        return text
