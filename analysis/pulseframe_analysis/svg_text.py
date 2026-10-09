"""Text-sign SVGs as PNG, so image models can use them as references.

Image models take PNG, JPEG and WebP, not SVG. A Producer package's text signs ("I AM YOUR MOTHER!", an org chart as lines of
text) are tiny SVGs made only of <text> and <rect>, which Pillow can draw. Anything with other shapes (paths, circles,
gradients, images, scripts) is left alone: this is not a general SVG renderer, and an unreadable file is skipped by the caller.

The file comes from a package someone else made, so it is read as data: size-limited, no DOCTYPE or entities (nothing is
expanded or fetched), only the elements below, and a capped canvas.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET

MAX_BYTES = 200_000
MAX_SIDE = 4096
MAX_TEXTS = 200
ALLOWED = {"svg", "g", "rect", "text", "tspan", "title", "desc"}
NAMED = {"white": "#ffffff", "black": "#000000", "gold": "#ffd700", "red": "#ff0000", "gray": "#808080", "grey": "#808080",
         "blue": "#0000ff", "green": "#008000", "yellow": "#ffff00", "orange": "#ffa500", "silver": "#c0c0c0"}
BACKGROUND = (11, 11, 11)


class Unsupported(Exception):
    pass


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _num(v, default: float) -> float:
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)", str(v)) if v is not None else None
    return float(m.group(1)) if m else default


def _color(v: str | None, default=(255, 255, 255)):
    v = (v or "").strip().lower()
    v = NAMED.get(v, v)
    if re.fullmatch(r"#[0-9a-f]{3}", v):
        v = "#" + "".join(c * 2 for c in v[1:])
    if re.fullmatch(r"#[0-9a-f]{6}", v):
        return tuple(int(v[i:i + 2], 16) for i in (1, 3, 5))
    if v in ("", "none", "transparent"):
        return None if v else default
    raise Unsupported(f"colour {v}")


def _font(size: int, bold: bool):
    from PIL import ImageFont
    names = (("DejaVuSans-Bold.ttf", "arialbd.ttf", "segoeuib.ttf") if bold else ("DejaVuSans.ttf", "arial.ttf", "segoeui.ttf"))
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def to_png(src: str, out: str, transparent: bool = False) -> str:
    """Draw a text-sign SVG to a PNG at `out` (on a near-black background, or transparent for compositing over video).
    Raises Unsupported for anything this does not handle."""
    from PIL import Image, ImageDraw
    if os.path.getsize(src) > MAX_BYTES:
        raise Unsupported("file too large")
    raw = open(src, "rb").read()
    if re.search(rb"<!\s*(DOCTYPE|ENTITY)", raw, re.I):
        raise Unsupported("DOCTYPE or ENTITY")
    try:
        root = ET.fromstring(raw)  # nosec B314
    except ET.ParseError as e:
        raise Unsupported(f"not valid SVG ({e})")
    if _local(root.tag) != "svg":
        raise Unsupported("not an SVG")
    for el in root.iter():
        if _local(el.tag) not in ALLOWED:
            raise Unsupported(f"<{_local(el.tag)}> is not supported")
        if any(k.lower().startswith("on") or "href" in k.lower() for k in el.attrib):
            raise Unsupported("scripts and links are not supported")
    vb = [float(x) for x in re.split(r"[\s,]+", root.get("viewBox", "").strip()) if x] if root.get("viewBox") else []
    w = _num(root.get("width"), vb[2] if len(vb) == 4 else 1024)
    h = _num(root.get("height"), vb[3] if len(vb) == 4 else 256)
    vw, vh = (vb[2], vb[3]) if len(vb) == 4 and vb[2] > 0 and vb[3] > 0 else (w, h)
    if not (1 <= w <= MAX_SIDE and 1 <= h <= MAX_SIDE):
        raise Unsupported("canvas size")
    sx, sy = w / vw, h / vh
    img = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0)) if transparent else Image.new("RGB", (int(w), int(h)), BACKGROUND)
    d = ImageDraw.Draw(img)
    drawn = 0

    def put(draw_mask, color) -> None:
        """Transparent mode: paint `color` where draw_mask(ImageDraw) marks a layer, composited properly so edges stay clean."""
        nonlocal img
        mask = Image.new("L", img.size, 0)
        draw_mask(ImageDraw.Draw(mask))
        layer = Image.new("RGBA", img.size, tuple(color) + (0,))
        layer.putalpha(mask)
        img = Image.alpha_composite(img, layer)

    for el in root.iter():
        tag = _local(el.tag)
        if tag == "rect":
            fill = _color(el.get("fill"), (0, 0, 0))
            if fill:
                x, y, rw, rh = (_num(el.get(k), 0) for k in ("x", "y", "width", "height"))
                if transparent:
                    put(lambda m, b=[x * sx, y * sy, (x + rw) * sx, (y + rh) * sy]: m.rectangle(b, fill=255), fill)
                else:
                    d.rectangle([x * sx, y * sy, (x + rw) * sx, (y + rh) * sy], fill=fill)
        elif tag == "text":
            text = " ".join("".join(el.itertext()).split())
            if not text:
                continue
            drawn += 1
            if drawn > MAX_TEXTS:
                raise Unsupported("too much text")
            size = max(6, min(400, int(_num(el.get("font-size"), 16) * sy)))
            font = _font(size, "bold" in (el.get("font-weight") or "").lower() or (el.get("font-weight") or "").strip() in ("600", "700", "800", "900"))
            anchor = {"middle": "m", "end": "r"}.get((el.get("text-anchor") or "").strip(), "l") + "s"
            at = (_num(el.get("x"), 0) * sx, _num(el.get("y"), size) * sy)
            color = _color(el.get("fill"), (0, 0, 0)) or (0, 0, 0)
            if transparent:
                put(lambda m, at=at, text=text, font=font, anchor=anchor: m.text(at, text, font=font, fill=255, anchor=anchor), color)
            else:
                d.text(at, text, font=font, fill=color, anchor=anchor)
    if not drawn:
        raise Unsupported("nothing to draw")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out + ".part.png")
    os.replace(out + ".part.png", out)
    return out
