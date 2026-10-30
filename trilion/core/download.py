"""Resumable downloads with progress callbacks."""
import time
from pathlib import Path

import requests

UA = {"User-Agent": "Trilion/0.1"}


def download(url, dest, on_progress=None, headers=None):
    """Download url -> dest, resuming a .part file if present.
    on_progress(done_bytes, total_bytes)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        if on_progress:
            on_progress(1, 1)
        return dest
    part = dest.with_name(dest.name + ".part")
    pos = part.stat().st_size if part.exists() else 0
    h = dict(UA, **(headers or {}))
    if pos:
        h["Range"] = f"bytes={pos}-"
    with requests.get(url, stream=True, headers=h, timeout=30, allow_redirects=True) as r:
        if r.status_code == 416:  # already complete
            part.replace(dest)
            return dest
        r.raise_for_status()
        if pos and r.status_code != 206:
            pos = 0
        total = int(r.headers.get("Content-Length", 0)) + pos
        last = 0.0
        done = pos
        with open(part, "ab" if pos else "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                now = time.monotonic()
                if on_progress and now - last > 0.1:
                    on_progress(done, total)
                    last = now
    part.replace(dest)
    if on_progress:
        on_progress(1, 1)
    return dest


def hf_files(repo):
    r = requests.get(f"https://huggingface.co/api/models/{repo}", headers=UA, timeout=30)
    r.raise_for_status()
    return [s["rfilename"] for s in r.json().get("siblings", [])]


def hf_url(repo, filename):
    return f"https://huggingface.co/{repo}/resolve/main/{filename}"
