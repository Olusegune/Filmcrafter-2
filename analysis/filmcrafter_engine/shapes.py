"""Shapes and icons for the Layers panel: a rectangle, rounded box, circle or line (filled, outlined, see-through) and a small set of icons, drawn as
transparent pictures the same way text and signs are. Free: nothing here calls a service. The screen draws the same things with CSS and SVG for the
player, from the same numbers (see src/PlayerOverlays.tsx and src/shapeIcons.json).

A shape's `width` and `height` are fractions of the frame's width and height. Its outline is `stroke_w` of the frame height, drawn inside the box.
`opacity` is how solid it is, `rotation` turns it clockwise in degrees, `radius` rounds a rounded box (a fraction of its shorter side).
"""
from __future__ import annotations

from .shape_icons import ICONS

SHAPES = ("rect", "rounded", "circle", "line")
SHAPE_NAMES = {"rect": "Rectangle", "rounded": "Rounded box", "circle": "Circle", "line": "Line"}
SS = 4                                  # drawn this much larger, then reduced, so edges are smooth


def gradient(size: tuple[int, int], c1, c2, angle: float = 180.0):
    """A two-colour gradient as a picture, the way CSS draws `linear-gradient(<angle>deg, c1, c2)`: 0 is to the top, 90 to the right, 180 to the bottom."""
    import math

    import numpy as np
    from PIL import Image
    w, h = max(1, size[0]), max(1, size[1])
    a = math.radians(angle)
    dx, dy = math.sin(a), -math.cos(a)
    span = abs(w * dx) + abs(h * dy) or 1.0
    xs = (np.arange(w) + 0.5 - w / 2)[None, :]
    ys = (np.arange(h) + 0.5 - h / 2)[:, None]
    t = np.clip(0.5 + (xs * dx + ys * dy) / span, 0, 1)[..., None]
    rgb = (np.array(c1, dtype=float) * (1 - t) + np.array(c2, dtype=float) * t).round().astype(np.uint8)
    return Image.fromarray(np.dstack([rgb, np.full((h, w, 1), 255, np.uint8)]), "RGBA")


def paint(size: tuple[int, int], o: dict, opacity: float, hex_rgb):
    """What a shape, icon or lettering is filled with, as a picture of this size: its colour, or a gradient from `color` to `color2` at `angle`."""
    from PIL import Image
    c1 = hex_rgb(o.get("color"))
    if o.get("gradient") and o.get("color2"):
        im = gradient(size, c1, hex_rgb(o["color2"]), float(o.get("angle") if o.get("angle") is not None else 180))
    else:
        im = Image.new("RGBA", size, c1 + (255,))
    if opacity < 1:
        im.putalpha(im.split()[3].point(lambda v: round(v * opacity)))
    return im


def _rgba(rgb: tuple[int, int, int], opacity: float) -> tuple[int, int, int, int]:
    return rgb[0], rgb[1], rgb[2], round(255 * min(1.0, max(0.0, opacity)))


def _box(draw, shape: str, box: tuple[int, int, int, int], fill, radius: float) -> None:
    x0, y0, x1, y1 = box
    if x1 <= x0 or y1 <= y0:
        return
    if shape == "circle":
        draw.ellipse(box, fill=fill)
    elif shape == "rounded":
        draw.rounded_rectangle(box, radius=max(0, round(radius * min(x1 - x0, y1 - y0))), fill=fill)
    else:
        draw.rectangle(box, fill=fill)


def draw_shape(o: dict, W: int, H: int, hex_rgb):
    """A rectangle, rounded box, circle or line as a transparent picture sized for a W x H frame."""
    from PIL import Image, ImageDraw
    scale = min(5.0, max(0.1, float(o.get("scale") or 1)))
    shape = o.get("shape") if o.get("shape") in SHAPES else "rect"
    w = max(2, min(W * 2, round(W * float(o.get("width") or 0.3) * scale)))
    h = max(2, min(H * 2, round(H * float(o.get("height") or (0.006 if shape == "line" else 0.2)) * scale)))
    op = float(o.get("opacity") if o.get("opacity") is not None else 1.0)
    sw = round(H * float(o.get("stroke_w") or 0))
    filled = o.get("filled", True) is not False
    kind = "rect" if shape == "line" else shape
    radius = float(o.get("radius") if o.get("radius") is not None else 0.2)
    ss = 4 if max(w, h) <= 1000 else 2 if max(w, h) <= 2000 else 1
    size = (w * ss, h * ss)
    outer, inner = Image.new("L", size, 0), Image.new("L", size, 0)
    _box(ImageDraw.Draw(outer), kind, (0, 0, size[0] - 1, size[1] - 1), 255, radius)
    if sw > 0:
        _box(ImageDraw.Draw(inner), kind, (sw * ss, sw * ss, size[0] - 1 - sw * ss, size[1] - 1 - sw * ss), 255, radius)
    else:
        inner = outer
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    if sw > 0:                                                       # the outline is the whole shape (or just the ring when unfilled); the inside goes on top
        from PIL import ImageChops
        edge = Image.new("RGBA", size, _rgba(hex_rgb(o.get("stroke") or "#ffffff"), 1.0))
        edge.putalpha((outer if filled else ImageChops.subtract(outer, inner)).point(lambda v: round(v * op)))
        out = edge
    if filled:
        body = paint((w, h), o, 1.0, hex_rgb)
        body = body.resize(size, Image.BILINEAR) if ss > 1 else body
        body.putalpha(inner.point(lambda v: round(v * op)))
        out = Image.alpha_composite(out, body)
    return _finish(out, (w, h), o)


def draw_icon(o: dict, W: int, H: int, hex_rgb):
    """One of the built-in icons, in one colour, as a transparent picture sized for a W x H frame (its width is the icon's size)."""
    from PIL import Image, ImageDraw
    icon = ICONS.get(o.get("icon") or "star") or ICONS["star"]
    scale = min(5.0, max(0.1, float(o.get("scale") or 1)))
    s = max(4, min(W * 2, round(W * float(o.get("width") or 0.12) * scale)))
    op = float(o.get("opacity") if o.get("opacity") is not None else 1.0)
    ss = 4 if s <= 1000 else 2
    mask = Image.new("L", (s * ss, s * ss), 0)
    d = ImageDraw.Draw(mask)
    for poly in icon["polys"]:
        d.polygon([(x * (s * ss - 1), y * (s * ss - 1)) for x, y in poly], fill=255)
    big = paint((s, s), o, 1.0, hex_rgb).resize((s * ss, s * ss), Image.BILINEAR)
    big.putalpha(mask.point(lambda v: round(v * op)))
    return _finish(big, (s, s), o)


def _finish(big, size: tuple[int, int], o: dict):
    from PIL import Image
    im = big.convert("RGBa").resize(size, Image.BOX).convert("RGBA")      # an area average (no ringing) with the colour weighted by its opacity, so edges stay clean
    turn = float(o.get("rotation") or 0)
    if turn:
        im = im.rotate(-turn, resample=Image.BICUBIC, expand=True)       # clockwise, as on the screen
    return im
