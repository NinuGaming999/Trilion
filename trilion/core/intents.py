"""Instant, model-free handling of simple commands ("open notepad", "volume up", "what time is it").
These work even if the language model is confused, and answer in milliseconds."""
import re
from datetime import datetime

APPS = {
    "notepad": "notepad", "calculator": "calc", "calc": "calc", "paint": "mspaint",
    "file explorer": "explorer", "explorer": "explorer", "files": "explorer", "task manager": "taskmgr",
    "command prompt": "cmd", "cmd": "cmd", "terminal": "wt", "powershell": "powershell",
    "settings": "ms-settings:", "control panel": "control", "snipping tool": "snippingtool",
    "chrome": "chrome", "google chrome": "chrome", "edge": "msedge", "microsoft edge": "msedge",
    "firefox": "firefox", "word": "winword", "excel": "excel", "powerpoint": "powerpnt",
    "spotify": "spotify", "discord": "discord", "steam": "steam", "vs code": "code",
    "visual studio code": "code", "code": "code", "camera": "microsoft.windows.camera:",
    "clock": "ms-clock:", "obs": "obs64", "vlc": "vlc",
}
SITES = {
    "youtube": "https://www.youtube.com", "google": "https://www.google.com",
    "gmail": "https://mail.google.com", "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com", "twitter": "https://x.com", "x": "https://x.com",
    "github": "https://github.com", "reddit": "https://www.reddit.com", "netflix": "https://www.netflix.com",
    "whatsapp": "https://web.whatsapp.com", "chatgpt": "https://chatgpt.com", "twitch": "https://www.twitch.tv",
    "amazon": "https://www.amazon.com", "wikipedia": "https://www.wikipedia.org",
    "google drive": "https://drive.google.com", "maps": "https://www.google.com/maps",
}
VAGUE = {"a video", "video", "videos", "music", "a song", "song", "something", "it", "that", "this",
         "a file", "file", "files please", "a link", "link", "a page", "page", "a tab", "tab", "app", "an app"}
KEYS = {
    "volume up": ("volumeup", "Turning it up."), "louder": ("volumeup", "Turning it up."),
    "volume down": ("volumedown", "Turning it down."), "quieter": ("volumedown", "Turning it down."),
    "mute": ("volumemute", "Muted."), "unmute": ("volumemute", "Unmuted."),
    "next song": ("nexttrack", "Next track."), "next track": ("nexttrack", "Next track."),
    "previous song": ("prevtrack", "Previous track."), "previous track": ("prevtrack", "Previous track."),
    "pause": ("playpause", "Done."), "resume": ("playpause", "Done."),
    "pause the music": ("playpause", "Done."), "pause the video": ("playpause", "Done."),
    "play the music": ("playpause", "Done."), "play the video": ("playpause", "Done."),
}
DOMAIN_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.(com|net|org|io|gg|tv|co|app|dev|xyz|me|info|bd)(/\S*)?$")


def _clean(text):
    t = text.lower().strip()
    t = re.sub(r"^(hey |ok |okay )?(trilion|please)[,.!? ]*", "", t)
    t = re.sub(r"\b(please|for me|now)\b", " ", t)
    t = re.sub(r"[.!?,]+$", "", t.strip())
    return re.sub(r"\s+", " ", t).strip()


def match(text):
    """Return (speech, action_dict_or_None) when the request is simple enough, else None."""
    t = _clean(text)
    if not t:
        return None
    if t in KEYS:
        key, say = KEYS[t]
        return say, {"tool": "press_keys", "args": {"keys": key}}
    if re.fullmatch(r"(what('s| is) the )?(current )?time( is it)?( now)?|what time is it", t):
        return f"It is {datetime.now().strftime('%I:%M %p').lstrip('0')}.", None
    if re.fullmatch(r"(what('s| is) )?(the )?(today's |current )?date( today)?|what day is it( today)?", t):
        return f"Today is {datetime.now().strftime('%A, %B %d').replace(' 0', ' ')}.", None

    m = re.fullmatch(r"play (.+?)(?: on youtube)?", t)
    if m and "spotify" not in t and m.group(1) not in VAGUE:
        q = m.group(1)
        return f"Playing {q} on YouTube.", {"tool": "play_youtube", "args": {"query": q}}
    m = re.fullmatch(r"(?:search|google|look up|search for)(?: for)? (.+?)(?: on (google|youtube|maps|amazon|wikipedia|github))?", t)
    if m and m.group(1) not in VAGUE:
        site = m.group(2) or "google"
        return f"Searching {site} for {m.group(1)}.", {"tool": "open_search", "args": {"site": site, "query": m.group(1)}}

    m = re.fullmatch(r"(?:open|launch|start|run)(?: up)?(?: the)?(?: app)? (.+)", t)
    if m:
        name = m.group(1).strip()
        if name in VAGUE or len(name.split()) > 3:
            return None
        if name in SITES:
            return f"Opening {name}.", {"tool": "open_url", "args": {"url": SITES[name]}}
        if DOMAIN_RE.match(name.replace(" dot ", ".")):
            return f"Opening {name}.", {"tool": "open_url", "args": {"url": "https://" + name.replace(" dot ", ".")}}
        return f"Opening {name}.", {"tool": "open_app", "args": {"name": APPS.get(name, name)}}
    return None
