import ctypes
import os
import sys


def main():
    if os.name == "nt":
        try:  # real pixel coordinates for screen reading / clicking
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Trilion.Assistant")
        except Exception:
            pass

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("Trilion")
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    icon = os.path.join(base, "assets", "trilion.ico")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))

    # 1) Show the loading window immediately - only light imports so far.
    from .ui.loading import LoadingWindow
    state = {}

    def start_boot():
        from .boot import Boot
        b = Boot(bridge)
        state["boot"] = b
        b.progress.connect(loading.set_progress)
        b.failed.connect(loading.set_error)
        b.ready.connect(on_ready)
        b.start()

    loading = LoadingWindow(on_retry=start_boot)
    loading.show()
    app.processEvents()

    from .core.bridge import Bridge
    from .paths import setup_logging
    setup_logging()
    bridge = Bridge()

    def on_ready(rt):
        from .core.agent import Assistant
        from .ui.main_window import MainWindow
        assistant = Assistant(rt, bridge)
        win = MainWindow(rt, assistant, bridge)
        state["win"] = win
        win.show()
        loading.close()

    # 2) Heavy work happens off the UI thread.
    start_boot()
    sys.exit(app.exec())
