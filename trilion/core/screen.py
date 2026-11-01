"""Screen capture. Remembers scale/offset so clicks map back to real pixels."""
import base64
import io

LAST = {"scale": 1.0, "left": 0, "top": 0, "w": 0, "h": 0, "thumb": None}
# How the model writes click coordinates: pixel = pixels of the screenshot, norm1000 = 0..1000 on each axis,
# unit = 0..1 fractions. Measured per brain at first launch (see calibrate.py).
COORD = {"mode": "pixel"}


def grab(max_width=1280, quality=85):
    import mss
    from PIL import Image
    with mss.mss() as s:
        mon = s.monitors[1]
        raw = s.grab(mon)
        im = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    scale = min(1.0, max_width / im.width)
    if scale < 1.0:
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    LAST.update(scale=scale, left=mon["left"], top=mon["top"], w=im.width, h=im.height,
                thumb=im.convert("L").resize((32, 18)).tobytes())
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return b64, (im.width, im.height)


def to_screen(x, y):
    """Model coordinates -> real screen pixels."""
    mode = COORD["mode"]
    if mode == "norm1000":
        x, y = x / 1000.0 * LAST["w"], y / 1000.0 * LAST["h"]
    elif mode == "unit":
        x, y = x * LAST["w"], y * LAST["h"]
    s = LAST["scale"] or 1.0
    return int(LAST["left"] + x / s), int(LAST["top"] + y / s)


def screen_changed(before, after, threshold=1.5):
    """True if two thumbnails differ (mean absolute pixel difference). None when unknown."""
    if not before or not after or len(before) != len(after):
        return None
    return sum(abs(a - b) for a, b in zip(before, after)) / len(before) > threshold


def zoom(x, y, w, h, out_width=1000):
    """Native-resolution crop of a region (screenshot coords), upscaled for reading small text."""
    import mss
    from PIL import Image
    x0, y0 = to_screen(x, y)
    x1, y1 = to_screen(x + w, y + h)
    with mss.mss() as s:
        raw = s.grab({"left": x0, "top": y0, "width": max(8, x1 - x0), "height": max(8, y1 - y0)})
        im = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    k = min(3.0, out_width / im.width)
    if abs(k - 1) > 0.05:
        im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode(), im.size
