"""Skills: folders with a SKILL.md (name + description + instructions) and optional scripts.
Trilion only sees the one-line descriptions until a task matches, then loads the full file."""
import re
import shutil
import sys
from pathlib import Path

from ..paths import sub


def builtin_dir() -> Path:
    base = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parents[2]
    return Path(base) / "skills_builtin"


def user_dir() -> Path:
    return sub("skills")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")[:40]


def parse(md: str):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", md, re.S)
    meta, body = {}, md
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip()
        body = m.group(2)
    return meta, body


class Skills:
    def __init__(self):
        src, dst = builtin_dir(), user_dir()
        if src.exists():
            for d in src.iterdir():  # copy built-ins once; never overwrite the user's edits
                if d.is_dir() and not (dst / d.name).exists():
                    shutil.copytree(d, dst / d.name)

    def all(self):
        out = []
        for d in sorted(user_dir().iterdir()):
            f = d / "SKILL.md"
            if d.is_dir() and f.exists():
                meta, _ = parse(f.read_text(encoding="utf-8", errors="ignore"))
                out.append({"name": meta.get("name") or d.name, "description": meta.get("description", ""),
                            "dir": d})
        return out

    def prompt_block(self):
        items = self.all()
        if not items:
            return ""
        lines = [f"- {s['name']}: {s['description'][:140]}" for s in items]
        return "Skills you can load with use_skill (do this first when a request matches):\n" + "\n".join(lines)

    def find(self, name):
        key = slug(name)
        for s in self.all():
            if slug(s["name"]) == key or s["dir"].name == key:
                return s
        return None

    def get(self, name):
        s = self.find(name)
        if not s:
            return None
        _, body = parse((s["dir"] / "SKILL.md").read_text(encoding="utf-8", errors="ignore"))
        scripts = [p.name for p in s["dir"].iterdir() if p.suffix.lower() in (".ps1", ".py", ".bat", ".cmd")]
        return body.strip(), scripts

    def create(self, name, description, instructions):
        key = slug(name)
        if not key:
            raise ValueError("Skill needs a name")
        d = user_dir() / key
        d.mkdir(parents=True, exist_ok=True)
        text = f"---\nname: {key}\ndescription: {description.strip()}\n---\n{instructions.strip()}\n"
        (d / "SKILL.md").write_text(text, encoding="utf-8")
        return d

    def script_path(self, skill, script):
        s = self.find(skill)
        if not s:
            raise FileNotFoundError(f"No skill named '{skill}'")
        p = s["dir"] / Path(script).name  # basename only: no path tricks
        if not p.exists():
            raise FileNotFoundError(f"No script '{script}' in skill '{skill}'")
        return p
