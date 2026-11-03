"""Minecraft helpers: exact camera maths and the prompt text used while Minecraft mode is on.

Minecraft turns the camera by  counts * ((sens*0.6+0.2)^3 * 8) * 0.15  degrees, where sens is the internal
0..1 slider value (the menu shows it doubled: default 100% = 0.5 = 0.15 degrees per mouse count)."""
import math

MC_TOOLS = {"mc_aim", "mc_look", "mc_walk", "mc_mine", "mc_attack", "mc_use", "mc_hotbar", "mc_inventory",
            "mc_close", "mc_set_turn_scale"}


def internal_sens(menu_percent):
    return max(0.0, min(1.0, float(menu_percent) / 200.0))


def deg_per_count(menu_percent=100, turn_scale=1.0):
    d = internal_sens(menu_percent) * 0.6 + 0.2
    return (d ** 3) * 8.0 * 0.15 * float(turn_scale)


def counts_for(yaw, pitch, menu_percent=100, turn_scale=1.0):
    dpc = deg_per_count(menu_percent, turn_scale)
    return int(round(yaw / dpc)), int(round(pitch / dpc))


def aim_degrees(tx, ty, cx, cy, height_px, fov_vertical=70.0):
    """Camera turn (yaw right+, pitch down+) that puts the crosshair (cx, cy) on the screen point (tx, ty)."""
    focal = (height_px / 2.0) / math.tan(math.radians(fov_vertical) / 2.0)
    return math.degrees(math.atan((tx - cx) / focal)), math.degrees(math.atan((ty - cy) / focal))


WALK = {"forward": "w", "back": "s", "backward": "s", "left": "a", "right": "d",
        "w": "w", "s": "s", "a": "a", "d": "d"}


def walk_keys(direction, sprint=False, jump=False, sneak=False):
    keys = []
    for part in str(direction or "forward").lower().replace("+", "-").replace(" ", "-").split("-"):
        if part:
            if part not in WALK:
                raise ValueError(f"Unknown direction '{part}'. Use forward, back, left, right (or forward-left ...)")
            if WALK[part] not in keys:
                keys.append(WALK[part])
    if sprint:
        keys.append("ctrl")
    if jump:
        keys.append("space")
    if sneak:
        keys.append("shift")
    return keys


MC_DOCS = """\
MINECRAFT TOOLS (Minecraft mode is on)
mc_aim {"x":0,"y":0} - turn the camera so the crosshair (screen centre) lands exactly on that screenshot point; use before mining, attacking or placing
mc_look {"yaw":0,"pitch":0} - turn the camera by degrees (yaw: right is +, pitch: down is +)
mc_walk {"dir":"<forward|back|left|right|forward-left ...>","ms":800,"sprint":false,"jump":false,"sneak":false} - walk
mc_mine {"ms":1500} - hold the left mouse button: break the block under the crosshair (use longer for hard blocks)
mc_attack {"times":1} - hit what the crosshair is on, spaced for the sword cooldown
mc_use {"ms":0} - right click: place a block / use an item; ms above 0 holds it (eat, draw a bow)
mc_hotbar {"slot":1} - select hotbar slot 1-9
mc_inventory {} - open or close the inventory (the mouse is then free: use game_click; add shift to shift-click)
mc_close {} - press Esc (close a menu)
mc_set_turn_scale {"requested":90,"actual":90} - calibration: how many degrees the camera really turned"""

MC_RULES = """MINECRAFT MODE. The crosshair is the centre of the screen: whatever it touches is what you mine, hit or place on.
- To work on a block or mob: look at the screenshot, mc_aim at it, then mc_mine / mc_attack / mc_use, then look again.
- To go somewhere: mc_aim at it, then mc_walk forward for a short time (400-1200 ms). Re-aim often; keep steps short when mobs are near.
- Mining by hand: a log takes about 3 seconds; stone needs a pickaxe. If the block did not break, mine longer.
- Open menus with mc_inventory, then use game_click on the screenshot positions (the cursor is free in menus); mc_close or mc_inventory to leave.
- Watch the hearts and hunger bars. If health is low or a hostile mob is close: back away, block it, or eat; never dig straight down; stay away from lava and cliff edges (hold sneak near edges).
- Say what you will do in one short sentence, act, then check the result on the next screenshot."""
