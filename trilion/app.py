import ctypes
import os
import sys


def main():
    minimized = "--minimized" in sys.argv
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
    app.setQuitOnLastWindowClosed(False)  # the tray keeps Trilion alive; windows quit explicitly
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
        b.failed.connect(on_failed)
        b.ready.connect(on_ready)
        b.start()

    def on_failed(msg):
        loading.set_error(msg)
        loading.show()  # also when started hidden at login

    loading = LoadingWindow(on_retry=start_boot)
    if not minimized:
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
        win.setObjectName("trilionRoot")
        win.setStyleSheet("QWidget#trilionRoot { background-color:#030b17; }\n" + win.styleSheet())
        state["win"] = win
        loading.finishing = True
        if minimized and win.tray_ok:
            loading.close()
        else:
            win.show()
            loading.close()

    # 2) Heavy work happens off the UI thread.
    start_boot()
    sys.exit(app.exec())
