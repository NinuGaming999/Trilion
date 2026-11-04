# Trilion

A local, voice-driven AI assistant for Windows that **sees your screen**, **talks to you**, and **controls your PC**.
Everything runs on your own machine (tuned for an RTX 3060 12 GB). No cloud, no API keys.

## Download (fast)
Go to the **[Releases](../../releases/latest)** page and download **`Trilion-Setup.exe`**. Run it, then start Trilion from the desktop shortcut.
(`Trilion-portable.zip` is the same app without an installer.)

On the **first launch** Trilion downloads the engine and models (about 9 GB) once into `%LOCALAPPDATA%\Trilion`
with a progress bar. Later launches only load the models into memory.

## The interface (v0.8): Trilion Command Center
A dark-glass dashboard with a rotating triangle-mesh **AI core**, and every panel shows real data:
- **AI Core Overview, Local Models, Active Agents:** live status of the brain, ears, voice, hands, eyes and game player (they light up and animate while they work).
- **Live Intelligence Feed + Mission Timeline:** what you said, what Trilion replied, every action it ran (Running / Done / Failed), and warnings. The search box filters the feed.
- **System Monitor:** CPU, RAM, disk and GPU memory. **Memory Insights:** what Trilion remembers, session turns, tool calls.
- **Talk bar:** the big *TALK TO TRILION* button (or the mic in the sidebar, or Ctrl+Alt+T) with a triangular waveform that reacts to your voice and to Trilion's.
- **Pages:** Command Center, AI Core, Conversations, Tools & Skills, Memory, Game Mode, Settings. *Focus Mode* hides everything except the core and the feed. The red square stops everything.

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

### Minecraft mode (v0.6)
Say **"play Minecraft"** with a single-player world open (Java edition). Trilion uses only the keyboard and mouse, like a player:
- **Exact camera:** it converts "that block over there" into the exact number of mouse counts using Minecraft's own sensitivity maths and your FOV (`mc_aim`), then looks again and corrects.
- **Real player actions:** hold-to-mine, sword hits spaced for the cooldown, hold-to-eat, place blocks, hotbar, inventory, shift-click.
- **Safety:** the launcher window is never typed into; held keys and buttons are released on **Ctrl+Alt+S**.
- **Recommended Minecraft settings:** Raw Input ON, sensitivity 100%, FOV 70, FOV Effects 0%, View Bobbing OFF, Auto-Jump ON; turn off Windows "Enhance pointer precision". Say *"set up Minecraft"* to have it walk you through a quick camera calibration (settings `mc_sensitivity`, `mc_fov`, `mc_turn_scale` in `config.json`).
- Built-in skills: `minecraft-setup`, `minecraft-survival`, `minecraft-building`. Say **"stop playing"** to leave game mode.
- Honest limits: it thinks about once per second or two while the game keeps running, so Creative or Peaceful difficulty is the best way to start; survival at night is risky.

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
