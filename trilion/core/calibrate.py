"""Find out how the brain writes click coordinates (pixels, 0..1000, or 0..1) by showing it a test picture."""
import base64
import io
import json
import logging
import math

log = logging.getLogger("trilion.calibrate")

W, H = 1280, 720
CIRCLE = (960, 200)  # known position of the red circle
SCHEMA = {"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
          "required": ["x", "y"], "additionalProperties": False}


def make_test_image():
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W, H), (245, 245, 245))
    d = ImageDraw.Draw(im)
    d.rectangle((60, 480, 220, 640), fill=(40, 90, 200))                      # a distractor
    d.ellipse((CIRCLE[0] - 45, CIRCLE[1] - 45, CIRCLE[0] + 45, CIRCLE[1] + 45), fill=(220, 30, 30))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def decide(x, y):
    """Map the model's answer to a coordinate mode, or None if it fits none of them."""
    cands = {
        "pixel": (CIRCLE[0], CIRCLE[1], W, H),
        "norm1000": (CIRCLE[0] / W * 1000, CIRCLE[1] / H * 1000, 1000, 1000),
        "unit": (CIRCLE[0] / W, CIRCLE[1] / H, 1, 1),
    }
    best, best_d = None, 1e9
    for mode, (tx, ty, sx, sy) in cands.items():
        d = math.hypot((x - tx) / sx, (y - ty) / sy)
        if d < best_d:
            best, best_d = mode, d
    return best if best_d < 0.12 else None


def calibrate(llm):
    msg = [{"role": "user", "content": [
        {"type": "text", "text": f"This image is {W}x{H} pixels. Find the red circle and give the center point of "
                                 'it as JSON {"x": number, "y": number}, in the coordinate system you normally use '
                                 "for clicking on screens."},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + make_test_image()}},
    ]}]
    text = "".join(llm.chat_stream(msg, schema=SCHEMA, max_tokens=60, temperature=0.0))
    obj = json.loads(text[text.index("{"): text.rindex("}") + 1])
    mode = decide(float(obj["x"]), float(obj["y"]))
    log.info("calibration answer %s -> %s", obj, mode)
    return mode
