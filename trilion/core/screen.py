"""Screen capture. Remembers scale/offset so clicks map back to real pixels."""
import base64
import io

LAST = {"scale": 1.0, "left": 0, "top": 0, "w": 0, "h": 0}


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
    LAST.update(scale=scale, left=mon["left"], top=mon["top"], w=im.width, h=im.height)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return b64, (im.width, im.height)


def to_screen(x, y):
    s = LAST["scale"] or 1.0
    return int(LAST["left"] + x / s), int(LAST["top"] + y / s)


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
