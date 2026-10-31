# Trilion

A local, voice-driven AI assistant for Windows that **sees your screen**, **talks to you**, and **controls your PC**.
Everything runs on your own machine (tuned for an RTX 3060 12 GB). No cloud, no API keys.

## Download (fast)
Go to the **[Releases](../../releases/latest)** page and download **`Trilion-Setup.exe`**. Run it, then start Trilion from the desktop shortcut.
(`Trilion-portable.zip` is the same app without an installer.)

On the **first launch** Trilion downloads the engine and models (~6 GB) once into `%LOCALAPPDATA%\Trilion`
with a progress bar. Later launches only load the models into memory.

## What it can do
- **See:** screenshots of your screen (its own window is hidden from them) plus a `zoom` tool for small text.
- **Hear / speak:** local Whisper + Kokoro. Just talk, or click **Talk** (click, speak, click again).
- **Operate apps by name:** Windows UI Automation lets it click buttons and type into fields by their names, with screenshot clicking as the fallback.
- **Web:** search and read pages; it never guesses links, only opens ones it found.
- **Files and system:** files, PowerShell/cmd, Python (risky actions ask first).
- **Skills:** folders with a `SKILL.md` in `%LOCALAPPDATA%\Trilion\skills\`. Trilion loads one when your request matches it. Built in: play-media, research-topic, organize-folder, system-check, take-notes, daily-briefing, operate-app, learn-skill. Say *"Trilion, learn how to do this"* to have it write a new skill, or add your own folder (optionally with `.ps1` / `.py` scripts it can run).
- **Memory:** tell it "remember that ..." and it keeps facts between sessions (`memory.json`); say "forget ..." to remove them.

## Keys and tray
`Ctrl+Alt+T` talk on/off from anywhere - `Ctrl+Alt+S` stop everything. The tray icon menu has Show, Talk, Stop, *Start with Windows* and *Close button hides to tray*.
Slam the mouse into a screen corner to abort mouse control.

## Run from source
```
pip install -r requirements.txt
python run_trilion.py
```
Settings: `%LOCALAPPDATA%\Trilion\config.json`. Logs: `%LOCALAPPDATA%\Trilion\logs` (or the **Copy log** button).

## Notes
- A 7B model is good, not perfect: it can still misread a screen or misclick. Ask it to double-check, and keep "Confirm risky" on.
- Built on: llama.cpp, faster-whisper, kokoro-onnx, PySide6, PyAutoGUI, uiautomation, mss.
