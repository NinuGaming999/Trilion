# PyInstaller spec - onedir build (starts much faster than onefile, which unpacks on every launch)
from PyInstaller.utils.hooks import collect_all

datas = [("assets/trilion.ico", "assets"), ("assets/trilion.png", "assets"),
         ("skills_builtin", "skills_builtin")]
binaries, hidden = [], ["sounddevice", "pyautogui", "pyperclip", "mss"]
for pkg in ("faster_whisper", "ctranslate2", "onnxruntime", "kokoro_onnx", "espeakng_loader",
            "phonemizer", "language_tags", "segments", "csvw", "tokenizers", "av", "_sounddevice_data",
            "uiautomation", "comtypes"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hidden += h
    except Exception:
        pass

a = Analysis(
    ["run_trilion.py"], pathex=["."], binaries=binaries, datas=datas, hiddenimports=hidden,
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "torch", "PySide6.QtWebEngineCore",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore", "IPython", "pytest"],
    noarchive=False,
)

# Trim files Trilion never loads (smaller download, same behaviour).
_DROP = ("opengl32sw", "qt6pdf", "qt6quick", "qt6qml", "qt6virtualkeyboard")
a.binaries = [x for x in a.binaries if not any(k in x[0].lower() for k in _DROP)]
a.datas = [x for x in a.datas if not ("pyside6" in x[0].lower() and "translations" in x[0].lower())]

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Trilion", console=False, upx=False,
          icon="assets/trilion.ico")
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Trilion")
