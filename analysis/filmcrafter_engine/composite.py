"""Compositing for layers: how a layer mixes with the picture under it (blend modes), a shape that hides part of it (a mask), and a colour that is cut out of a picture (a key).

Blend modes are done by ffmpeg when the film is made, in full-range RGB with the HD matrix written out (as the colour grade does), and only for the frames the layer is up: the rest of the
film is left exactly as it was. A mask and a key change the layer's own picture, so they are drawn once and cached like the rest of it. Nothing here calls a provider or costs anything.

Every value comes from the screen, so each is checked: a blend mode is one of a fixed list (it goes into a filter graph by name, never as typed), numbers are clamped, colours are parsed.
"""
from __future__ import annotations

import numpy as np

# what the person sees -> ffmpeg's name for it
BLENDS: dict[str, str] = {"multiply": "multiply", "screen": "screen", "overlay": "overlay", "softlight": "softlight", "hardlight": "hardlight",
                          "darken": "darken", "lighten": "lighten", "add": "addition", "difference": "difference"}
MASKS = ("ellipse", "rounded", "rect")

TO_RGB = "scale=in_range=tv:in_color_matrix=bt709:out_range=pc:out_color_matrix=bt709:flags=accurate_rnd+full_chroma_int,format=gbrp16le"
TO_YUV = "scale=in_range=pc:out_range=tv:out_color_matrix=bt709:flags=accurate_rnd+full_chroma_int,format=yuv420p"


def _num(x, name: str, lo: float, hi: float) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise SystemExit(f"{name} must be a number.")
    if v != v:
        raise SystemExit(f"{name} must be a number.")
    return min(hi, max(lo, v))


def clean(x: dict, o: dict, hexify) -> None:
    """Put the compositing fields of `x` into `o` (checked). A field set to nothing removes the effect."""
    if "blend" in x:
        b = str(x["blend"] or "normal").lower().replace(" ", "").replace("_", "")
        if b in ("", "normal"):
            o.pop("blend", None)
        elif b in BLENDS:
            o["blend"] = b
        else:
            raise SystemExit("Choose one of the blend modes in the list.")
    if "mask" in x:
        m = str(x["mask"] or "none").lower()
        if m in ("", "none"):
            for k in ("mask", "mask_size", "mask_feather", "mask_invert"):
                o.pop(k, None)
        elif m in MASKS:
            o["mask"] = m
            o.setdefault("mask_size", 0.8)
        else:
            raise SystemExit("Choose an ellipse, a rounded box or a rectangle for the mask.")
    if o.get("mask"):
        if "mask_size" in x:
            o["mask_size"] = _num(x["mask_size"], "The mask size", 0.05, 1.0)
        if "mask_feather" in x:
            v = _num(x["mask_feather"], "The mask softness", 0.0, 1.0)
            if v:
                o["mask_feather"] = v
            else:
                o.pop("mask_feather", None)
        if "mask_invert" in x:
            if x["mask_invert"]:
                o["mask_invert"] = True
            else:
                o.pop("mask_invert", None)
    if "key_color" in x:
        if not x["key_color"]:
            for k in ("key_color", "key_tol", "key_soft", "key_spill"):
                o.pop(k, None)
        else:
            o["key_color"] = "#%02x%02x%02x" % hexify(str(x["key_color"]))
            o.setdefault("key_tol", 0.35)
            o.setdefault("key_soft", 0.15)
            o.setdefault("key_spill", 0.6)
    if o.get("key_color"):
        for k, name, dflt in (("key_tol", "The colour range", 0.35), ("key_soft", "The edge softness", 0.15), ("key_spill", "The spill removal", 0.6)):
            if k in x:
                o[k] = _num(x[k], name, 0.0, 1.0)


def signature(o: dict) -> list:
    """What the layer's own picture depends on, for its cache name: empty (so every existing layer keeps its cached picture) unless a mask or a key is set."""
    out: list = []
    if o.get("mask"):
        out += ["mask", o["mask"], o.get("mask_size", 0.8), o.get("mask_feather", 0), bool(o.get("mask_invert"))]
    if o.get("key_color"):
        out += ["key", o["key_color"], o.get("key_tol", 0.35), o.get("key_soft", 0.15), o.get("key_spill", 0.6)]
    return out


def _chroma(rgb):
    """Which colour it is, without how bright: each channel's share of the pixel. A green screen in shadow has the same shares as one in the light, so it is the same green."""
    total = rgb.sum(axis=-1, keepdims=True)
    return rgb / np.maximum(total, 1.0)


def apply_key(im, o: dict, hexify):
    """The picture with one colour made transparent (soft at the edge), and the colour's reflection on what is left taken out ("spill")."""
    if not o.get("key_color"):
        return im
    from PIL import Image
    a = np.asarray(im.convert("RGBA"), dtype=np.float32).copy()
    rgb = a[..., :3]
    key = np.array(hexify(o["key_color"]), dtype=np.float32)
    dist = np.linalg.norm(_chroma(rgb) - _chroma(key), axis=-1) / 1.4143       # 0 for the key colour (lit or in shadow); 1 for the opposite primary
    dist = np.where(rgb.sum(axis=-1) < 24.0, 1.0, dist)                         # near black has no colour to speak of: it stays
    lo = float(o.get("key_tol", 0.35)) * 0.6
    hi = lo + float(o.get("key_soft", 0.15)) * 0.6 + 1e-4
    t = np.clip((dist - lo) / (hi - lo), 0.0, 1.0)
    t = t * t * (3.0 - 2.0 * t)
    a[..., 3] *= t
    spill = float(o.get("key_spill", 0.6))
    if spill > 0:
        c = int(np.argmax(key))                                                # the channel the screen is made of: green for a green screen
        others = [i for i in range(3) if i != c]
        limit = (rgb[..., others[0]] + rgb[..., others[1]]) / 2.0
        rgb[..., c] -= np.maximum(0.0, rgb[..., c] - limit) * spill            # no more of that colour than the other two together would give
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


def apply_mask(im, o: dict):
    """The picture shown only through a shape (or only outside it), with a soft edge if asked: a spotlight, a round portrait, a vignette."""
    if not o.get("mask"):
        return im
    from PIL import Image, ImageChops, ImageDraw, ImageFilter
    w, h = im.size
    k = float(o.get("mask_size", 0.8))
    mw, mh = max(2, round(w * k)), max(2, round(h * k))
    box = ((w - mw) // 2, (h - mh) // 2, (w - mw) // 2 + mw - 1, (h - mh) // 2 + mh - 1)
    m = Image.new("L", (w, h), 0)
    dr = ImageDraw.Draw(m)
    if o["mask"] == "ellipse":
        dr.ellipse(box, fill=255)
    elif o["mask"] == "rounded":
        dr.rounded_rectangle(box, radius=min(mw, mh) * 0.22, fill=255)
    else:
        dr.rectangle(box, fill=255)
    f = float(o.get("mask_feather", 0))
    if f:
        m = m.filter(ImageFilter.GaussianBlur(f * min(w, h) * 0.25))
    if o.get("mask_invert"):
        m = ImageChops.invert(m)
    out = im.convert("RGBA")
    out.putalpha(ImageChops.multiply(out.split()[3], m))
    return out


def graph(k: int, prev: str, pos: str, mode: str, s: float, e: float, W: int, H: int, fps: int) -> tuple[list[str], str]:
    """The filter-graph pieces that mix layer `k` (already faded and moved by its own chain, labelled [o{k}]) into [prev] with this blend mode while it is up.
    Returns (the pieces, the label of the picture that comes out). Outside the layer's time the picture is the one that came in, untouched."""
    if mode not in BLENDS:
        raise SystemExit("Choose one of the blend modes in the list.")
    ff = BLENDS[mode]
    return ([
        f"color=c=black@0:s={W}x{H}:r={fps}:d={max(e, 0.0) + 0.5:.3f},format=rgba[bk{k}]",
        f"[bk{k}][o{k}]overlay={pos}:eof_action=pass[L{k}]",                       # the layer on a transparent frame of the film's size, where it is at that moment
        f"[L{k}]split[Lc{k}][La{k}]",
        f"[La{k}]alphaextract,format=gray16le[A{k}]",
        f"[Lc{k}]format=gbrp16le[Lr{k}]",
        f"[{prev}]split[pp{k}][pq{k}]",                                             # a label can be used once: one copy goes through the blend, one is kept as it was
        f"[pp{k}]{TO_RGB},split[pa{k}][pb{k}]",
        f"[pa{k}][Lr{k}]blend=all_mode={ff}:all_opacity=1[bl{k}]",
        f"[pb{k}][bl{k}][A{k}]maskedmerge[mm{k}]",                                  # blended where the layer is, the picture as it was elsewhere (its own transparency is the mask)
        f"[mm{k}]{TO_YUV}[res{k}]",
        f"[pq{k}][res{k}]overlay=eof_action=pass:enable='between(t,{s:.3f},{e:.3f})',format=yuv420p[v{k}]",
    ], f"v{k}")
