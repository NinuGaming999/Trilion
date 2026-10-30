# Trilion

A local, voice-driven AI assistant for Windows that can **see your screen**, **talk to you**, and **control your PC**.
Everything runs on your own machine (tuned for an RTX 3060 12 GB). No cloud, no API keys.

- **Brain + vision:** Qwen2.5-VL 7B (Q4) through a bundled `llama.cpp` server, on the GPU (~6.5 GB VRAM)
- **Ears:** faster-whisper (CPU, int8) - **Voice:** Kokoro TTS (CPU)
- **Hands:** open apps/URLs, keyboard, mouse, files, shell (risky actions ask first)
- **UI:** instant loading screen with progress bar, then a triangular wave that reacts to your voice and Trilion's voice

## Get the .exe
Open the **Actions** tab -> latest *Build Trilion for Windows* run -> download `Trilion-Windows`:
- `Trilion-Setup.exe` - one-file installer (recommended; the installed app starts fastest)
- `Trilion-portable.zip` - unzip and run `Trilion.exe`

On the **first launch** Trilion downloads the engine and models (~6 GB) once into `%LOCALAPPDATA%\Trilion`
with a progress bar. Every launch after that only loads the models into memory.

## Use it
Say **"Trilion, ..."** (it stays awake 45 s after each reply) or type in the box.
Examples: "Trilion, open Notepad and write a shopping list", "what's on my screen?", "open YouTube".
Toggles: Mic, Watch screen, Wake word, Confirm risky. **Stop** interrupts. Slam the mouse into a screen corner to abort mouse control.

## Run from source
```
pip install -r requirements.txt
python run_trilion.py
```
Settings live in `%LOCALAPPDATA%\Trilion\config.json` (model repo, quant, voice, Whisper size, context, ...).
Logs: `%LOCALAPPDATA%\Trilion\logs`.

## Notes
- Clicking by coordinates is the weakest part of a 7B model; keyboard/`open_app` are preferred. A GUI-specialist model (UI-TARS) is the upgrade path.
- Built on: llama.cpp, faster-whisper, kokoro-onnx, PySide6, PyAutoGUI, mss.
