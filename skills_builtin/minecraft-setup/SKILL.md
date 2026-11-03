---
name: minecraft-setup
description: Get Minecraft (Java) ready for Trilion: recommended settings and a quick camera calibration.
---
1. Use a single-player world (Creative is easiest for a first test). Windowed or F11 fullscreen are both fine; keep the Minecraft window in front.
2. Options > Controls > Mouse Settings: Raw Input ON, Sensitivity 100% (the default), Auto-Jump ON. Options > Video Settings: FOV 70, FOV Effects 0%, View Bobbing OFF. In Windows, turn off "Enhance pointer precision" in mouse settings.
3. Say "play Minecraft" (this starts Minecraft mode).
4. Optional calibration if aiming is off: press F3 so the debug text shows "Facing: ... (yaw / pitch)". Use zoom to read the yaw number. Call mc_look with yaw 90, then read the yaw again. Call mc_set_turn_scale with requested 90 and actual = how many degrees the yaw really changed (ignore the sign). Press F3 again to hide the text.
