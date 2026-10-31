---
name: daily-briefing
description: Give a short morning briefing: date, weather, top news, and PC status.
---
1. Get the date and time with run_shell: powershell -c "Get-Date -Format 'dddd, d MMMM yyyy HH:mm'".
2. web_search "weather today" plus the user's city if you remember it (ask once, then remember it).
3. web_search "top news today" and read the 3 best headlines.
4. Do a quick check with the system-check skill only if the user asked for it.
5. Speak it as 4-6 short sentences.
