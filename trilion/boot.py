"""Background loader. Runs after the loading window is already on screen."""
import logging
import traceback

from PySide6.QtCore import QThread, Signal

from .paths import Config

log = logging.getLogger("trilion.boot")

# (key, weight). Weights roughly track real time on a first run.
STEPS = [("engine", 12), ("brain", 38), ("voice_dl", 6), ("ears_dl", 6), ("start", 2),
         ("engines", 10), ("wait", 26)]
TOTAL = sum(w for _, w in STEPS)


class Runtime:
    pass


class Boot(QThread):
    progress = Signal(float, str)
    failed = Signal(str)
    ready = Signal(object)

    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge

    def _cb(self, key):
        before = 0
        for k, w in STEPS:
            if k == key:
                weight = w
                break
            before += w

        def cb(frac, text):
            self.progress.emit((before + weight * max(0.0, min(1.0, frac))) / TOTAL, text)
        return cb

    def run(self):
        try:
            self.progress.emit(0.0, "Loading components…")
            cfg = Config()
            rt = Runtime()
            rt.cfg = cfg
            from .core.llama import LlamaServer
            from .core.stt import STT, ensure_whisper
            from .core.tts import TTS, ensure_voice
            from .core.audio import Listener, Player
            rt.llm = LlamaServer(cfg)

            rt.llm.ensure_binary(self._cb("engine"))
            rt.llm.ensure_model(self._cb("brain"))
            voice_dir = ensure_voice(self._cb("voice_dl"))
            whisper_dir = ensure_whisper(cfg, self._cb("ears_dl"))

            # Start the GPU brain first; load voice + ears on CPU while it warms up.
            self._cb("start")(0, "Starting brain…")
            rt.llm.start()
            e = self._cb("engines")
            e(0.05, "Loading ears…")
            rt.stt = STT(whisper_dir, cfg)
            e(0.5, "Loading voice…")
            rt.tts = TTS(voice_dir, cfg)
            e(0.9, "Opening audio devices…")
            rt.player = Player(self.bridge.out_level.emit)
            rt.listener = Listener(self.bridge.mic_level.emit,
                                   lambda m: self.bridge.message.emit("error", m))
            rt.listener.device = cfg.get("mic_device")
            e(1, "Senses online")
            rt.llm.wait_ready(self._cb("wait"))
            rt.listener.start()
            self.progress.emit(1.0, "Ready")
            self.ready.emit(rt)
        except Exception as ex:
            log.error("boot failed: %s\n%s", ex, traceback.format_exc())
            self.failed.emit(f"{ex}\n(see %LOCALAPPDATA%\\Trilion\\logs)")
