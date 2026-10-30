"""Thread-safe signals between worker threads and the Qt UI."""
import threading

from PySide6.QtCore import QObject, Signal


class Bridge(QObject):
    progress = Signal(float, str)
    state = Signal(str)          # idle | listening | thinking | speaking | acting
    mic_level = Signal(float)
    out_level = Signal(float)
    message = Signal(str, str)   # role (user|assistant|action|error), text
    caption = Signal(str)
    confirm_req = Signal(str, object)

    def ask(self, question):
        """Called from a worker thread; blocks until the user answers in the UI."""
        ev, box = threading.Event(), [False]
        self.confirm_req.emit(question, (ev, box))
        ev.wait(120)
        return box[0]
