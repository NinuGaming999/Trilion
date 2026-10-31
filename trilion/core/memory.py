"""Long-term memory: short facts about the user, kept between sessions."""
import json
import time

from ..paths import app_dir


class Memory:
    def __init__(self):
        self.path = app_dir() / "memory.json"
        self.items = []
        try:
            self.items = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            pass

    def _save(self):
        try:
            self.path.write_text(json.dumps(self.items, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass

    def add(self, fact):
        fact = " ".join(fact.split())[:300]
        if not fact:
            return "Nothing to remember."
        if any(i["fact"].lower() == fact.lower() for i in self.items):
            return "Already remembered."
        self.items.append({"fact": fact, "t": int(time.time())})
        self.items = self.items[-100:]
        self._save()
        return f"Remembered: {fact}"

    def forget(self, text):
        key = text.lower().strip()
        keep = [i for i in self.items if key not in i["fact"].lower()]
        n = len(self.items) - len(keep)
        self.items = keep
        self._save()
        return f"Forgot {n} item(s)." if n else "I had nothing matching that."

    def prompt_block(self):
        if not self.items:
            return ""
        lines, total = [], 0
        for i in reversed(self.items):
            if total + len(i["fact"]) > 1800:
                break
            lines.append("- " + i["fact"])
            total += len(i["fact"])
        return "What you remember about the user (use it naturally):\n" + "\n".join(reversed(lines))
