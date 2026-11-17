"""Run only the avatar web server for development:  python scripts/avatar_dev.py [port]
Then open http://127.0.0.1:<port>/avatar"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from trilion.core.avatar import AvatarService  # noqa: E402
from trilion.core.hud import WebHud  # noqa: E402

hud = WebHud(int(sys.argv[1]) if len(sys.argv) > 1 else 17999)
hud.start()
AvatarService({}, hud).ensure_model()
print("avatar page:", hud.url + "avatar", flush=True)
while True:
    time.sleep(3600)
