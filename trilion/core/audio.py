"""Microphone listener (energy VAD) and speaker player. Both report live levels for the wave."""
import collections
import queue
import threading
import time

import numpy as np
import sounddevice as sd

SR_IN = 16000
SR_OUT = 24000


class Listener:
    def __init__(self, on_level, on_warn=None):
        self.on_level = on_level
        self.on_warn = on_warn or (lambda m: None)
        self.on_utterance = None          # on_utterance(audio, forced=False)
        self.gate = lambda: False         # True -> ignore the mic right now
        self.device = None
        self.stream = None
        self.floor = 0.003
        self.manual = False
        self.manual_buf = []
        self.peak_seen = 0.0
        self.started = 0.0
        self.warned = False
        self._reset()

    def _reset(self):
        self.pre = collections.deque(maxlen=10)
        self.buf = []
        self.speaking = False
        self.loud = 0
        self.last_voice = 0.0
        self.t_start = 0.0

    def start(self):
        self.stop()
        self.started = time.monotonic()
        self.peak_seen = 0.0
        self.warned = False
        self.stream = sd.InputStream(samplerate=SR_IN, channels=1, dtype="float32", blocksize=512,
                                     device=self.device, callback=self._cb)
        self.stream.start()

    def stop(self):
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def set_device(self, name):
        self.device = name
        self._reset()
        self.start()

    # ---- click-to-talk: records everything until end_manual() ----
    def begin_manual(self):
        self.manual_buf = []
        self.manual = True

    def end_manual(self):
        self.manual = False
        buf, self.manual_buf = self.manual_buf, []
        if buf and self.on_utterance:
            audio = np.concatenate(buf)
            if len(audio) > SR_IN * 0.4:
                self.on_utterance(audio, True)

    def _cb(self, indata, frames, t, status):
        x = indata[:, 0].copy()
        rms = float(np.sqrt(np.mean(x * x)))
        now = time.monotonic()
        self.peak_seen = max(self.peak_seen, rms)
        if not self.warned and now - self.started > 5 and self.peak_seen == 0.0:
            self.warned = True
            self.on_warn("Trilion is getting pure silence from the microphone. In Windows: Settings > Privacy & "
                         "security > Microphone > turn on 'Let desktop apps access your microphone', or pick "
                         "another mic in the dropdown.")
        if self.manual:
            self.on_level(min(1.0, rms * 14))
            self.manual_buf.append(x)
            return
        if self.gate():
            if self.speaking or self.buf:
                self._reset()
            self.on_level(0.0)
            return
        self.on_level(min(1.0, rms * 14))
        thr = max(0.006, self.floor * 3.0)
        if not self.speaking:
            if rms < thr:
                self.floor = 0.97 * self.floor + 0.03 * rms
            self.pre.append(x)
            self.loud = self.loud + 1 if rms > thr else 0
            if self.loud >= 3:
                self.speaking = True
                self.buf = list(self.pre)
                self.t_start = self.last_voice = now
        else:
            self.buf.append(x)
            if rms > thr:
                self.last_voice = now
            if now - self.last_voice > 0.9 or now - self.t_start > 25:
                audio = np.concatenate(self.buf)
                dur = now - self.t_start
                self._reset()
                if dur > 0.5 and self.on_utterance:
                    self.on_utterance(audio, False)


class Player:
    def __init__(self, on_level):
        self.on_level = on_level
        self.q = queue.Queue()
        self.cur = None
        self.pos = 0
        self.lock = threading.Lock()
        self.stream = sd.OutputStream(samplerate=SR_OUT, channels=1, dtype="float32",
                                      blocksize=1024, callback=self._cb)
        self.stream.start()

    def play(self, samples, sr=SR_OUT):
        samples = np.asarray(samples, dtype=np.float32)
        if sr != SR_OUT:
            n = int(len(samples) * SR_OUT / sr)
            samples = np.interp(np.linspace(0, len(samples) - 1, n), np.arange(len(samples)), samples).astype(np.float32)
        self.q.put(samples)

    def busy(self):
        return not self.q.empty() or (self.cur is not None and self.pos < len(self.cur))

    def stop(self):
        with self.lock:
            while not self.q.empty():
                try:
                    self.q.get_nowait()
                except queue.Empty:
                    break
            self.cur = None

    def _cb(self, outdata, frames, t, status):
        out = np.zeros(frames, dtype=np.float32)
        filled = 0
        with self.lock:
            while filled < frames:
                if self.cur is None or self.pos >= len(self.cur):
                    try:
                        self.cur = self.q.get_nowait()
                        self.pos = 0
                    except queue.Empty:
                        self.cur = None
                        break
                n = min(frames - filled, len(self.cur) - self.pos)
                out[filled:filled + n] = self.cur[self.pos:self.pos + n]
                filled += n
                self.pos += n
        outdata[:, 0] = out
        self.on_level(min(1.0, float(np.sqrt(np.mean(out * out))) * 5.0))

    def close(self):
        self.stream.stop()
        self.stream.close()
