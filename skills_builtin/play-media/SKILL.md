---
name: play-media
description: Play a video, song or stream the user asks for (YouTube, Spotify, etc.) without guessing links.
---
1. Never invent a link. For a YouTube video call play_youtube with the user's words. For music use open_search with site "spotify". If play_youtube opens the wrong video, use open_search with site "youtube" and pick the right result from the page.
2. Wait 2 seconds, then look. Find the best matching result by its title on screen.
3. Try ui_click with the video title text first. If that fails, click its thumbnail or title using the screenshot coordinates.
4. Look again and confirm the page title matches what the user asked for. If it does not, go back (press alt+left) and pick another result.
5. Tell the user the exact title that is now playing. Use press_keys with "space" (pause) or "volumeup" if asked.
