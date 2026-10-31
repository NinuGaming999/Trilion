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
        if peak < 0.012:          # basically silence / hiss: never send to Whisper
            return ""
        audio = np.clip(audio * min(0.8 / peak, 8.0), -1, 1).astype(np.float32)
        # Only bias the spelling of the name when the wake word is on. NEVER put command-like
        # phrases in the prompt: Whisper repeats them when it hears noise.
        prompt = "Trilion." if self.cfg.get("wake_word") else None
        kw = dict(language=self.cfg.get("whisper_language"), beam_size=1, condition_on_previous_text=False,
                  initial_prompt=prompt, no_speech_threshold=0.6, log_prob_threshold=-1.0)
        try:
            segs = list(self.model.transcribe(audio, vad_filter=True,
                                              vad_parameters=dict(min_silence_duration_ms=400, speech_pad_ms=200),
                                              **kw)[0])
        except Exception:
            segs = list(self.model.transcribe(audio, **kw)[0])
        text = " ".join(s.text.strip() for s in segs if s.no_speech_prob < 0.6 and s.avg_logprob > -1.0).strip()
        low = text.lower().strip(" .!?,'\"")
        if len(low) < 2 or low in HALLUCINATIONS:
            return ""
        return text


HALLUCINATIONS = {"you", "thank you", "thanks", "thanks for watching", "thank you for watching", "bye", "bye bye",
                  "okay", "ok", "hmm", "uh", "um", "the", "so", "yeah", "oh", "i", "subtitles by the amara.org community"}
