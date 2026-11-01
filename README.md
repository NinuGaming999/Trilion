# Trilion

A local, voice-driven AI assistant for Windows that **sees your screen**, **talks to you**, and **controls your PC**.
Everything runs on your own machine (tuned for an RTX 3060 12 GB). No cloud, no API keys.

## Download (fast)
Go to the **[Releases](../../releases/latest)** page and download **`Trilion-Setup.exe`**. Run it, then start Trilion from the desktop shortcut.
(`Trilion-portable.zip` is the same app without an installer.)

On the **first launch** Trilion downloads the engine and models (about 9 GB) once into `%LOCALAPPDATA%\Trilion`
with a progress bar. Later launches only load the models into memory.

## The brain (v0.4)
Trilion now runs **Qwen3.5 9B** (Q6_K, vision built in) through llama.cpp, with "thinking" switched off for speed.
Replies are forced into a strict `{say, action}` JSON format by a grammar, so a command can never be malformed or read aloud.
On first launch it also runs a quick self-test to learn how the model writes click coordinates.
If the engine rejects a flag or runs out of VRAM, Trilion retries automatically with safer settings; if strict mode is rejected it falls back to plain text.
The older **Qwen2.5-VL 7B** brain is still available: tray menu -> *Use the lighter brain* (restart needed), or set `"brain": "qwen2.5-vl-7b"` in `config.json`.
If Q6_K is too big for your GPU, set `"llm_quant_override": "Q4_K_M"`.

## What it can do
- **See:** screenshots of your screen (its own window is hidden from them) plus a `zoom` tool for small text.
- **Hear / speak:** local Whisper + Kokoro. Just talk, or click **Talk** (click, speak, click again).
- **Operate apps by number:** `ui_list` numbers the buttons, menus and fields in a window; Trilion picks an id with `ui_click` / `ui_type` (Windows UI Automation). Screenshot clicking is the fallback, and it is told when the screen did not change after an action.
- **Safety:** clicks on things like Delete, Send, Pay or Buy (and Alt+F4) always ask first, even if *Confirm risky* is off (`"confirm_critical": false` to disable).
- **Web:** search and read pages; it never guesses links, only opens ones it found.
- **Files and system:** files, PowerShell/cmd, Python (risky actions ask first).
- **Skills:** folders with a `SKILL.md` in `%LOCALAPPDATA%\Trilion\skills\`. Trilion loads one when your request matches it. Built in: play-media, research-topic, organize-folder, system-check, take-notes, daily-briefing, operate-app, learn-skill. Say *"Trilion, learn how to do this"* to have it write a new skill, or add your own folder (optionally with `.ps1` / `.py` scripts it can run).
- **Memory:** tell it "remember that ..." and it keeps facts between sessions (`memory.json`); say "forget ..." to remove them.

## Playing games (v0.5)
Trilion plays the way a person does: it looks at the screen and uses **only the keyboard and mouse** - no game files, memory or add-ons.
Say *"Trilion, start playing <game>"* (the game window must be open, ideally borderless-windowed). It asks once, then plays in short steps: look, send one timed action, look again.
- Keys are sent as hardware **scan codes**, which DirectX games accept (plain key presses are often ignored).
- The mouse moves in **relative counts**, spread smoothly over time, so camera/aim moves are exact (a 100-count move is always exactly 100).
- Held keys are always released on **Ctrl+Alt+S**, on quit, and by a 3-second dead-man timer.
- Input is only sent while the game window is in front.
- A local 7-9B model decides about once per second or two: good for turn-based, puzzle, card, strategy, point-and-click and slow exploration games; not for twitch shooters or rhythm games.
- Use it for **single-player games**. Online games with anti-cheat may block fake input or ban the account. If a game runs as administrator, start Trilion as administrator too.

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
