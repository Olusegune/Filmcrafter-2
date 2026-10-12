"""On-screen text over the finished video: signs, titles, charts, captions, logos.

Image and video models can't spell and FilmCrafter can't ask them to, so text that must read correctly is added at export, as a
second pass over the finished picture. An overlay is a line of text, a text-sign SVG (what a Producer package makes) or a picture,
shown from a start to an end with a short fade, at a position you choose.

  <project>/overlays.json   {"overlays": [{id, kind: text|svg|image, text, file, source: manual|package, section, start, end,
                                           x, y, size|width, color, fade, enabled}]}

Timing is a start and end in seconds, or a song section ("chorus1" = the first chorus, "verse2", "pre1", "bridge", "final" = the
last chorus) found in the analysed song map. Several overlays in one section are staggered through it so they never pile up.

The text, the files and the numbers here become pictures drawn by Pillow and plain numbers in an ffmpeg filter graph; nothing a
user types is ever placed in a command line or a filter, only validated numbers and file names this module made itself.

  python -m filmcrafter_engine.overlays <list|add|update|remove|preview|sync> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import hashlib
from .safe import sha1 as _sha1
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".svg")
MAX_TEXT = 300
MAX_OVERLAYS = 200
MAX_FILE = 25_000_000
SHOW_FOR = 5.0           # longest a section-timed overlay stays up
MARGIN = 0.03            # safe margin, as a fraction of the frame
ANIMS = ("fade", "rise", "drop", "slide_left", "slide_right", "zoom_in", "zoom_out", "pushin", "wipe", "typewriter", "bounce", "pop", "pulse", "accent")
ANIM_NAMES = {"fade": "Fade", "rise": "Rise", "drop": "Drop in", "slide_left": "Slide from the right", "slide_right": "Slide from the left",
              "zoom_in": "Zoom in and settle", "zoom_out": "Settle down", "pushin": "Slow push-in", "wipe": "Wipe in from the left",
              "typewriter": "Typewriter", "bounce": "Bounce in", "pop": "Pop in", "pulse": "Pulse to the beat", "accent": "Pulse on the strong hits"}
EASES = ("linear", "ease_in", "ease_out", "ease_in_out", "hold")
KEY_PROPS = ("x", "y", "scale", "rotation", "opacity")      # x, y: where the centre is (fractions of the frame); scale, opacity: multiply the layer's own; rotation: degrees added to its own
MAX_KEYS = 12
SECTIONS = {"intro": "INTRO", "verse": "VERSE", "pre": "PRE-CHORUS", "prechorus": "PRE-CHORUS", "pre-chorus": "PRE-CHORUS",
            "chorus": "CHORUS", "bridge": "BRIDGE", "outro": "OUTRO"}


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data) -> None:
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _inside(base: str, path: str) -> bool:
    b, p = os.path.normcase(os.path.realpath(base)), os.path.normcase(os.path.realpath(path))
    try:
        return os.path.commonpath([b, p]) == b and p != b
    except ValueError:
        return False


def load(d: str) -> list[dict]:
    return (_read(os.path.join(d, "overlays.json"), {}) or {}).get("overlays") or []


UNDO_KEEP = 40            # how many changes to the layers can be taken back


def _history_path(d: str) -> str:
    return os.path.join(d, "cache", "undo-layers.json")


def _history(d: str) -> dict:
    h = _read(_history_path(d), {}) or {}
    ok = lambda x: isinstance(x, list) and all(isinstance(o, dict) for o in x)      # a snapshot is a list of layers; anything else in the file is ignored
    h = h if isinstance(h, dict) else {}
    return {"undo": [x for x in h.get("undo", []) if ok(x)] if isinstance(h.get("undo"), list) else [],
            "redo": [x for x in h.get("redo", []) if ok(x)] if isinstance(h.get("redo"), list) else []}


def _save(d: str, items: list[dict], track: bool = True) -> None:
    """Write the layers. Every change first keeps the layers as they were, so it can be undone (the engine's own copies: nothing from the screen is replayed)."""
    if track:
        prev = load(d)
        if prev != items:
            h = _history(d)
            h["undo"] = (h["undo"] + [prev])[-UNDO_KEEP:]
            h["redo"] = []                                  # a new change ends the redo trail
            os.makedirs(os.path.dirname(_history_path(d)), exist_ok=True)
            _write(_history_path(d), h)
    _write(os.path.join(d, "overlays.json"), {"schema": 1, "overlays": items})


def history(d: str) -> dict:
    h = _history(d)
    return {"can_undo": bool(h["undo"]), "can_redo": bool(h["redo"]), "undo": len(h["undo"]), "redo": len(h["redo"])}


def undo(d: str) -> list[dict]:
    """Put the layers back as they were before the last change."""
    h = _history(d)
    if not h["undo"]:
        raise SystemExit("There is nothing to undo.")
    prev = h["undo"].pop()
    h["redo"] = (h["redo"] + [load(d)])[-UNDO_KEEP:]
    _write(_history_path(d), h)
    _save(d, prev, track=False)
    return resolve(d)


def redo(d: str) -> list[dict]:
    h = _history(d)
    if not h["redo"]:
        raise SystemExit("There is nothing to redo.")
    nxt = h["redo"].pop()
    h["undo"] = (h["undo"] + [load(d)])[-UNDO_KEEP:]
    _write(_history_path(d), h)
    _save(d, nxt, track=False)
    return resolve(d)


# ---------------------------------------------------------------- when

def section_span(songmap: dict, token: str) -> tuple[float, float] | None:
    """(start, end) of the section a token names: 'chorus1', 'verse2', 'pre1', 'bridge', 'final' (the last chorus)."""
    tok = (token or "").strip().lower().replace(" ", "")
    m = re.fullmatch(r"([a-z\-]+?)(\d+)?", tok)
    if not m:
        return None
    word, n = m.group(1), int(m.group(2) or 1)
    secs = songmap.get("sections") or []
    if word == "final":
        pool = [s for s in secs if str(s.get("label", "")).upper() == "CHORUS"]
        n = len(pool)
    else:
        label = SECTIONS.get(word, word.upper())
        pool = [s for s in secs if str(s.get("label", "")).upper() == label]
    if not 1 <= n <= len(pool):
        return None
    s = pool[n - 1]
    return float(s["start"]), float(s["end"])


def resolve(d: str) -> list[dict]:
    """Every overlay with a concrete start and end (or why it has none yet). Overlays on the same section share it in turn."""
    items = load(d)
    sm = _read(os.path.join(d, "songmap.json"), {}) or {}
    duration = float(sm.get("duration") or 0)
    by_section: dict[str, list[dict]] = {}
    for o in items:
        if o.get("start") is None and o.get("section"):
            by_section.setdefault(str(o["section"]).strip().lower().replace(" ", ""), []).append(o)
    out = []
    for o in items:
        r = {**o, "placed": False, "reason": "", "explicit": o.get("start") is not None, "explicit_end": o.get("end") is not None}
        start, end = o.get("start"), o.get("end")
        if start is not None:
            end = end if end is not None else start + 4.0
            r.update(start=float(start), end=float(end), placed=True)
        elif o.get("section"):
            key = str(o["section"]).strip().lower().replace(" ", "")
            span = section_span(sm, key)
            if not span:
                r["reason"] = f"the song map has no section \"{o['section']}\" yet" if sm else "the song hasn't been analysed yet"
            else:
                mates = by_section[key]
                slot = (span[1] - span[0]) / len(mates)
                show = max(1.0, min(SHOW_FOR, slot - 0.3))
                at = span[0] + mates.index(o) * slot + min(0.3, slot / 4)
                r.update(start=round(at, 3), end=round(min(at + show, span[1]), 3), placed=True)
        else:
            r["reason"] = "no time or section set"
        if r["placed"] and duration:
            r["end"] = min(r["end"], duration)
            if r["end"] <= r["start"]:
                r.update(placed=False, reason="it starts after the song ends")
        out.append(r)
    return out


# ---------------------------------------------------------------- what

def _hex(c: str | None, default: str = "#ffffff") -> tuple[int, int, int]:
    c = (c or default).strip().lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{3}", c):
        c = "".join(x * 2 for x in c)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", c):
        c = default.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _tight(img):
    box = img.split()[3].getbbox()
    return img.crop(box) if box else img


def _with_shadow(img):
    """A soft dark shadow behind the lettering so it reads over bright or busy pictures."""
    from PIL import Image, ImageFilter
    pad = max(8, img.width // 60)
    canvas = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
    canvas.paste(img, (pad, pad))
    blur = canvas.split()[3].filter(ImageFilter.GaussianBlur(max(2, pad // 3)))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow.putalpha(blur.point(lambda v: int(v * 0.75)))
    offset = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    offset.paste(shadow, (max(1, pad // 5), max(2, pad // 3)))
    return Image.alpha_composite(offset, canvas)



def _wrap(draw, text: str, font, width: int) -> list[str]:
    """Words broken into lines no wider than `width`."""
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and draw.textlength(trial, font=font) > width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + ([cur] if cur else [])


def render_image(d: str, o: dict, W: int, H: int):
    """The overlay as a transparent picture sized for a W x H frame."""
    from PIL import Image, ImageDraw
    kind = o.get("kind", "text")
    if kind in ("shape", "icon"):
        from . import shapes
        return (shapes.draw_shape if kind == "shape" else shapes.draw_icon)(o, W, H, _hex)          # flat, so no shadow
    if kind == "fill":
        from . import shapes
        a, b = _hex(o.get("color"), "#000000"), _hex(o.get("color2") or o.get("color"), "#000000")
        return shapes.gradient((W, H), a, b, float(o.get("angle") if o.get("angle") is not None else 180))      # top colour to bottom colour by default; one colour when both are the same
    scale = min(5.0, max(0.1, float(o.get("scale") or 1)))
    if kind == "text":
        from . import fonts, shapes
        size = max(10, min(int(H * 1.5), int(H * min(0.3, max(0.02, float(o.get("size") or 0.06))) * scale)))
        font = fonts.load(d, o.get("font"), size)
        probe = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        lines = []
        for para in str(o.get("text", "")).splitlines() or [""]:
            lines += _wrap(probe, para, font, int(W * 0.84)) or [""]
        lines = lines[:8]
        lh = int(size * 1.25)
        sw = min(int(H * 0.03), round(H * float(o.get("stroke_w") or 0)))
        pad = 4 + sw
        wide = max((probe.textlength(x, font=font) for x in lines), default=1)
        box = (int(wide) + 2 * pad, lh * len(lines) + 2 * pad)
        fill_mask, line_mask = Image.new("L", box, 0), Image.new("L", box, 0)
        fd, ld = ImageDraw.Draw(fill_mask), ImageDraw.Draw(line_mask)
        for i, ln in enumerate(lines):
            at = ((box[0] - probe.textlength(ln, font=font)) / 2, pad + i * lh)
            fd.text(at, ln, font=font, fill=255)
            if sw:
                ld.text(at, ln, font=font, fill=255, stroke_width=sw)
        opacity = float(o.get("opacity") if o.get("opacity") is not None else 1.0)
        tight = (line_mask if sw else fill_mask).getbbox()                   # the gradient runs across the lettering itself, not the empty room around it
        if tight:
            fill_mask, line_mask, box = fill_mask.crop(tight), line_mask.crop(tight), (tight[2] - tight[0], tight[3] - tight[1])
        layer = shapes.paint(box, o, opacity, _hex)
        layer.putalpha(fill_mask.point(lambda v: round(v * opacity)))
        if sw:
            outline = Image.new("RGBA", box, _hex(o.get("stroke") or "#000000") + (0,))
            outline.putalpha(line_mask.point(lambda v: round(v * opacity)))
            layer = Image.alpha_composite(outline, layer)
        im = _tight(layer)
        if o.get("rotation"):
            im = _tight(im.rotate(-float(o["rotation"]), resample=Image.BICUBIC, expand=True))
        return _with_shadow(im) if o.get("shadow", True) else im
    else:
        path = os.path.join(d, o.get("file", ""))
        if not (os.path.isfile(path) and _inside(d, path)):
            raise SystemExit(f"The picture for \"{o.get('text') or o.get('id')}\" is missing.")
        if path.lower().endswith(".svg"):
            from .svg_text import Unsupported, to_png
            tmp = os.path.join(d, "cache", "overlays", f"svg-{_sha1((path + str(os.path.getmtime(path))).encode()).hexdigest()[:12]}.png")
            os.makedirs(os.path.dirname(tmp), exist_ok=True)
            try:
                if not os.path.exists(tmp):
                    to_png(path, tmp, transparent=True)
            except Unsupported as e:
                raise SystemExit(f"\"{os.path.basename(path)}\" can't be drawn ({e}). Use a PNG, or a sign made only of text.")
            im = _tight(Image.open(tmp).convert("RGBA"))
        else:
            im = Image.open(path).convert("RGBA")
        if o.get("cover"):                      # a backdrop: scaled to fill the whole frame, the overflow cropped
            k = max(W / im.width, H / im.height)
            im = im.resize((max(W, round(im.width * k)), max(H, round(im.height * k))), Image.LANCZOS)
            left, top = (im.width - W) // 2, (im.height - H) // 2
            return im.crop((left, top, left + W, top + H))
        width = int(W * min(2.0, max(0.05, float(o.get("width") or 0.6) * scale)))
        im = im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)
        if o.get("opacity") is not None and float(o["opacity"]) < 1:
            im.putalpha(im.split()[3].point(lambda v: round(v * float(o["opacity"]))))
        if o.get("rotation"):
            im = im.rotate(-float(o["rotation"]), resample=Image.BICUBIC, expand=True)
    return _with_shadow(im) if o.get("shadow", True) else im


def render_png(d: str, o: dict, W: int, H: int) -> tuple[str, tuple[int, int]]:
    """The overlay's picture on disk (cached by what it is made from) and its size."""
    from . import fonts
    key = _sha1(json.dumps([o.get("kind"), o.get("text"), o.get("file"), o.get("size"), o.get("width"), o.get("color"), o.get("color2"), bool(o.get("cover")), W, H,
                                   [o.get(k) for k in ("shape", "icon", "height", "stroke", "stroke_w", "opacity", "rotation", "radius", "filled", "scale", "angle", "gradient", "shadow")],
                                   fonts.signature(d, o.get("font")) if o.get("kind", "text") == "text" else ""],
                                  sort_keys=True).encode()).hexdigest()[:14]
    out = os.path.join(d, "cache", "overlays", f"{key}.png")
    if not os.path.exists(out):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        im = render_image(d, o, W, H)
        im.save(out + ".part.png")
        os.replace(out + ".part.png", out)
        return out, im.size
    from PIL import Image
    with Image.open(out) as im:
        return out, im.size


def _position(o: dict, size: tuple[int, int], W: int, H: int) -> tuple[int, int]:
    """Top-left pixel of the overlay, centred on (x, y) and kept inside the safe margin."""
    w, h = size
    if o.get("kind") == "fill" or o.get("cover"):
        return 0, 0                          # a backdrop covers the frame; it is never moved inside the safe margin
    if o.get("kind") in ("shape", "icon"):   # a shape goes exactly where it is put, anywhere in the frame
        x = round(W * float(o.get("x", 0.5)) - w / 2)
        y = round(H * float(o.get("y", 0.5)) - h / 2)
        return max(0, min(x, W - w)), max(0, min(y, H - h))
    mx, my = int(W * MARGIN), int(H * MARGIN)
    x = round(W * float(o.get("x", 0.5)) - w / 2)
    y = round(H * float(o.get("y", 0.86)) - h / 2)
    return max(mx, min(x, W - w - mx)), max(my, min(y, H - h - my))


def motion(anim, s: float, e: float, f: float, x: int, y: int, size: tuple[int, int], W: int, H: int,
           beat: tuple[float, float] | None = None, chars: int = 0, accents: list[float] | None = None) -> tuple[str, str]:
    """How an overlay moves, as two ffmpeg pieces: an optional scale filter for the picture and the overlay's x/y. Only numbers made here go in
    (never text a user typed). `t` is the film's time in seconds; the move eases out over `m` seconds from the start, then the overlay holds still."""
    anim = anim if anim in ANIMS else "fade"
    w, h = size
    m = max(f, min(1.2, (e - s) / 2))
    p = f"clip((t-({s:.3f}))/{m:.3f},0,1)"                  # 0 at the start, 1 once settled
    ease = f"pow(1-{p},3)"                                  # 1 -> 0, fast then slow
    if anim == "rise":
        return "", f"x={x}:y='{y}+{round(0.07 * H)}*{ease}'"
    if anim == "drop":
        return "", f"x={x}:y='{y}-{round(0.07 * H)}*{ease}'"
    if anim == "slide_left":
        return "", f"x='{x}+{round(0.14 * W)}*{ease}':y={y}"
    if anim == "slide_right":
        return "", f"x='{x}-{round(0.14 * W)}*{ease}':y={y}"
    if anim in ("wipe", "typewriter"):          # revealed from the left: smoothly, or a letter at a time (a stepped wipe, so letters of unequal width are only approximate)
        g = p.replace("(t-", "(T-")                          # geq calls the time T
        r = g if anim == "wipe" or chars < 2 else f"(floor({chars}*{g}+0.0001)/{chars})"
        return (f",geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*lt(X,W*{r}+0.5)'", f"x={x}:y={y}")
    if anim == "bounce":                         # drops in from above and settles with a few diminishing bounces
        return "", f"x={x}:y='{y}-{round(0.09 * H)}*pow(1-{p},2)*cos(3*PI*{p})'"
    cx, cy = x + w / 2, y + h / 2
    if anim == "pop":                            # grows from nothing and overshoots a little before settling
        k = f"max(0.05,1+2.70158*pow({p}-1,3)+1.70158*pow({p}-1,2))"
    elif anim == "pulse" and beat:               # swells on every beat and relaxes before the next
        period, first = beat
        k = f"(1+0.06*pow(1-mod(mod(t-({first:.3f}),{period:.4f})+{period:.4f},{period:.4f})/{period:.4f},3))"
    elif anim == "accent" and accents:           # swells on each strong hit the song map found, and settles before the next
        near = sorted(a for a in accents if s - 0.5 <= a <= e + 0.5)[:60]
        if not near:
            return "", f"x={x}:y={y}"
        swell = lambda o: f"pow(1-clip((t-({o:.3f}))/{ACCENT_FOR},0,1),3)"
        expr = f"(1+{ACCENT_BY}*{swell(near[-1])})"
        for o, nxt in reversed(list(zip(near, near[1:]))):
            expr = f"if(lt(t,{nxt:.3f}),(1+{ACCENT_BY}*{swell(o)}),{expr})"
        k = f"if(lt(t,{near[0]:.3f}),1,{expr})"
    elif anim in ("zoom_in", "zoom_out"):
        start = 0.82 if anim == "zoom_in" else 1.18
        k = f"({start}+({1 - start})*(1-{ease}))"
    elif anim == "pushin":
        k = f"(1+0.08*clip((t-({s:.3f}))/{max(0.5, e - s):.3f},0,1))"
    else:
        return "", f"x={x}:y={y}"
    return f",scale=w='iw*{k}':h='ih*{k}':eval=frame", f"x='{cx:.1f}-overlay_w/2':y='{cy:.1f}-overlay_h/2'"


def beat_grid(d: str) -> tuple[float, float] | None:
    """(seconds per beat, time of the first beat) from the song map, for the layers that pulse to the beat."""
    sm = _read(os.path.join(d, "songmap.json"), {}) or {}
    try:
        bpm = float(sm.get("bpm") or 0)
    except (TypeError, ValueError):
        return None
    if not (40 <= bpm <= 240):
        return None
    marks = sm.get("downbeats") or sm.get("beats") or []
    first = float(marks[0]) if marks else 0.0
    return 60.0 / bpm, max(0.0, first)


# ---------------------------------------------------------------- keyframes
# A layer with keyframes moves by them instead of by its Movement preset. Each key is a moment (seconds after the layer appears) and any of x, y, scale,
# rotation and opacity; between two keys a property goes from one value to the next with the easing of the first key, before the first key it holds the
# first value and after the last key the last. A key that leaves a property out does not touch it. The screen draws them with the same formulas (src/overlayKeys.ts).

def clean_keys(raw) -> list[dict]:
    if raw in (None, [], ""):
        return []
    if not isinstance(raw, list):
        raise SystemExit("Keyframes must be a list.")
    if len(raw) > MAX_KEYS:
        raise SystemExit(f"A layer can have {MAX_KEYS} keyframes at most.")
    by_time: dict[float, dict] = {}
    for k in raw:
        if not isinstance(k, dict):
            raise SystemExit("Each keyframe needs a time.")
        try:
            t = round(min(86400.0, max(0.0, float(k.get("t")))), 3)
        except (TypeError, ValueError):
            raise SystemExit("Each keyframe needs a time in seconds.")
        ease = k.get("ease", "ease_in_out")
        if ease not in EASES:
            raise SystemExit("Choose one of the easings in the list.")
        key: dict = {"t": t, "ease": ease}
        for prop, lo, hi in (("x", -0.5, 1.5), ("y", -0.5, 1.5), ("scale", 0.05, 5.0), ("rotation", -720.0, 720.0), ("opacity", 0.0, 1.0)):
            if k.get(prop) is not None:
                try:
                    key[prop] = round(min(hi, max(lo, float(k[prop]))), 4)
                except (TypeError, ValueError):
                    raise SystemExit(f"The {prop} of a keyframe must be a number.")
        by_time[t] = key                                  # two keys at the same moment: the later one wins
    return [by_time[t] for t in sorted(by_time)]


def _ease(name: str, u: float) -> float:
    u = min(1.0, max(0.0, u))
    return {"linear": u, "ease_in": u * u, "ease_out": 2 * u - u * u, "ease_in_out": u * u * (3 - 2 * u), "hold": 0.0}[name]


def eval_keys(keys: list[dict], t: float) -> dict:
    """The keyed values at `t` seconds after the layer appears: {prop: value} for each property some key sets."""
    out = {}
    for prop in KEY_PROPS:
        pts = [(k["t"], k[prop], k.get("ease", "ease_in_out")) for k in keys if prop in k]
        if not pts:
            continue
        if t <= pts[0][0]:
            out[prop] = pts[0][1]
            continue
        value = pts[-1][1]
        for (t0, v0, e0), (t1, v1, _) in zip(pts, pts[1:]):
            if t < t1:
                value = v0 + (v1 - v0) * _ease(e0, (t - t0) / max(t1 - t0, 1e-3))
                break
        out[prop] = value
    return out


def key_expr(keys: list[dict], prop: str, rel: str) -> str | None:
    """The same curve as an ffmpeg expression of `rel` (the seconds since the layer appeared), or None when no key sets this property."""
    pts = [(k["t"], k[prop], k.get("ease", "ease_in_out")) for k in keys if prop in k]
    if not pts:
        return None
    expr = f"{pts[-1][1]:.4f}"
    for (t0, v0, e0), (t1, v1, _) in reversed(list(zip(pts, pts[1:]))):
        u = f"(({rel}-{t0:.3f})/{max(t1 - t0, 1e-3):.3f})"
        curve = {"linear": u, "ease_in": f"({u}*{u})", "ease_out": f"(2*{u}-{u}*{u})", "ease_in_out": f"({u}*{u}*(3-2*{u}))", "hold": "0"}[e0]
        expr = f"if(lt({rel},{t1:.3f}),({v0:.4f}+({v1 - v0:.4f})*{curve}),{expr})"
    return f"if(lt({rel},{pts[0][0]:.3f}),{pts[0][1]:.4f},{expr})"


def motion_keys(o: dict, s: float, f: float, size: tuple[int, int], W: int, H: int) -> tuple[str, str]:
    """The filters and overlay position for a layer that moves by its keyframes (the preset is not used). Order: opacity, rotation, scale, then placed by its centre."""
    keys = o["keys"]
    rel, relT = f"(t-({s:.3f}))", f"(T-({s:.3f}))"        # most filters call the time t, geq calls it T
    pre = ""
    op = key_expr(keys, "opacity", relT)
    if op:
        pre += f",geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*({op})'"
    rot = key_expr(keys, "rotation", rel)
    if rot:                                                # first on a transparent square big enough to hold it turned any way (so no edge is smeared into the corners)
        pre += (",pad=w='ceil(hypot(iw,ih)/2)*2':h='ceil(hypot(iw,ih)/2)*2':x='(ow-iw)/2':y='(oh-ih)/2':color=0x00000000"
                f",rotate=a='({rot})*PI/180':ow='iw':oh='ih':c=none")
    sc = key_expr(keys, "scale", rel)
    if sc:
        pre += f",scale=w='iw*max(0.05,{sc})':h='ih*max(0.05,{sc})':eval=frame"
    xe = key_expr(keys, "x", rel) or f"{float(o.get('x', 0.5)):.4f}"
    ye = key_expr(keys, "y", rel) or f"{float(o.get('y', 0.5)):.4f}"
    return pre, f"x='({xe})*{W}-overlay_w/2':y='({ye})*{H}-overlay_h/2'"


BATCH = 16          # layers drawn in one pass; a film with more is drawn in time slices, so a pass only holds the layers that are up during it
SLICE = 12.0        # seconds of film in one slice
MIN_SLICE = 2.0
ACCENT_FOR, ACCENT_BY = 0.35, 0.08     # a strong hit swells a layer by 8% and it settles over a third of a second (the screen uses the same numbers)
PASS_TIMEOUT = 3 * 3600       # seconds one ffmpeg run may take before it is given up on
LEAD = 2.2          # a pass starts this far before its first frame (and drops the extra), so a fade that was under way at the join is drawn in full


def _passes(placed: list[dict], total_frames: int | None, fps: int) -> list[tuple[int, int | None, list[dict]]]:
    """[(first frame, frame after the last or None for the end of the film, the layers up during it)]. One pass when the layers are few."""
    if len(placed) <= BATCH or not total_frames:
        return [(0, None, placed)]

    def up(a: int, b: int) -> list[dict]:
        lo, hi = a / fps - 0.25, b / fps + 0.25
        return [o for o in placed if float(o["end"]) > lo and float(o["start"]) < hi]

    out: list[tuple[int, int | None, list[dict]]] = []

    def cut(a: int, b: int) -> None:
        here = up(a, b)
        if len(here) > BATCH and (b - a) / fps > MIN_SLICE * 2:     # too many up at once: half the slice
            mid = (a + b) // 2
            cut(a, mid)
            cut(mid, b)
        else:
            out.append((a, b, here))
    step = max(1, round(SLICE * fps))
    a = 0
    while a < total_frames:
        cut(a, min(total_frames, a + step))
        a += step
    last = out[-1]
    out[-1] = (last[0], None, last[2])                                 # the last pass runs to the end of the film, whatever its exact length
    return out


def _pass(d: str, video: str, out: str, first_frame: int | None, frames: int | None, layers: list[dict], cap: str | None, W: int, H: int, fps: int, with_sound: bool,
          beat: tuple[float, float] | None, tag: str, joined: bool = False, cap_origin: float = 0.0, accents: list[float] | None = None) -> str | None:
    """One ffmpeg run: the film from `first_frame` for `frames` frames with these layers (and the captions) drawn on it. None when it worked, else what went wrong."""
    from .export import ffmpeg
    begin = (first_frame or 0) / fps                    # where this slice of the film starts
    shift = max(0.0, begin - LEAD)                      # the pass reads from here; the layers' times are the film's, so they are moved back by this much
    cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"] + (["-ss", f"{shift:.4f}"] if shift else []) + ["-i", video]
    chains, prev, first = [], "0:v", 1
    if cap:     # every caption is a transparent full-frame still held for its time: one input, however many lines
        cap_from = shift + cap_origin                    # the caption track covers the whole song; a piece of the film starts part-way into it
        cmd += (["-ss", f"{cap_from:.4f}"] if cap_from else []) + ["-f", "concat", "-safe", "0", "-i", os.path.abspath(cap)]
        chains.append(f"[1:v]fps={fps},format=rgba[cap];[0:v][cap]overlay=eof_action=pass:shortest=0[vc]")
        prev, first = "vc", 2
    shifted_beat = (beat[0], beat[1] - shift) if beat else None
    shifted_hits = [a - shift for a in accents] if accents else None
    for k, o in enumerate(layers, first):
        png, size = render_png(d, o, W, H)
        x, y = _position(o, size, W, H)
        s, e = float(o["start"]) - shift, float(o["end"]) - shift
        f = max(0.05, min(float(o.get("fade", 0.4) or 0.4), (e - s) / 3))
        # The picture is named without its folder: the command runs where it is, so a long list stays short enough for Windows.
        # The picture exists only while the layer is up (not for the whole slice): a looped picture is read as fast as it can be, and for a full-frame layer at 1080p that
        # filled gigabytes of memory in seconds.
        on = max(0.0, s)
        cmd += ["-loop", "1", "-framerate", str(fps), "-t", f"{e - on + 0.25:.3f}", "-itsoffset", f"{on:.3f}", "-i", os.path.basename(png)]
        if o.get("keys") and o.get("kind") != "fill" and not o.get("cover"):
            pre, pos = motion_keys(o, s, f, size, W, H)
        else:
            pre, pos = motion(o.get("anim"), s, e, f, x, y, size, W, H, shifted_beat, len(str(o.get("text") or "")) if o.get("kind", "text") == "text" else 0, shifted_hits)
        fade_in = f"fade=t=in:st={s:.3f}:d={f:.3f}:alpha=1," if s >= 0 else ""         # a layer up before this pass starts faded in during the lead-in that is cut off
        chains.append(f"[{k}:v]format=rgba,{fade_in}fade=t=out:st={max(0.0, e - f):.3f}:d={f:.3f}:alpha=1{pre}[o{k}]")
        chains.append(f"[{prev}][o{k}]overlay={pos}:eof_action=pass:enable='between(t,{s:.3f},{e:.3f})'[v{k}]")
        prev = f"v{k}"
    graph = f"{out}.{tag}.graph.txt"
    if begin > shift:                                    # drop the lead-in: the slice starts exactly on its first frame
        chains.append(f"[{prev}]trim=start={begin - shift:.4f},setpts=PTS-STARTPTS[cut]")
        prev = "cut"
    if chains:
        with open(graph, "w", encoding="utf-8") as fh:       # the filter graph goes in a file: with dozens of layers it is far longer than a command line may be
            fh.write(";\n".join(chains))
        cmd += ["-filter_complex_script", graph, "-map", f"[{prev}]"]
    else:                                                    # nothing is up during this slice: the film itself, encoded the same way so the slices join
        cmd += ["-map", "0:v"]
    cmd += ["-map", "0:a?", "-c:a", "copy"] if with_sound else ["-an"]
    # a slice that will be joined to others is encoded without B-frames: they start a few frames late, and the joins would then drop or repeat frames
    cmd += (["-frames:v", str(frames)] if frames else []) + ["-c:v", "libx264", "-crf", "18", "-preset", "medium"] + (["-bf", "0"] if joined else []) + ["-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv", "-movflags", "+faststart", out]
    work = os.path.join(d, "cache", "overlays")
    os.makedirs(work, exist_ok=True)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW, cwd=work, timeout=PASS_TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"it stopped making progress after {PASS_TIMEOUT // 60} minutes"          # a stalled run must not hang the export for ever
    finally:
        if os.path.exists(graph):
            os.remove(graph)
    if r.returncode or not os.path.exists(out):
        return (r.stderr or "")[-200:] or "ffmpeg stopped"
    return None


def burn(d: str, video: str, W: int, H: int, fps: int = 24, duration: float | None = None, origin: float = 0.0) -> dict:
    """Draw the lyric captions (one stream) and every enabled, placed overlay onto the finished video (re-encoded once; the sound is
    copied). With many layers the film is drawn in time slices, each holding only the layers that are up during it, and the slices are joined without
    another re-encode (a stream for every layer over a whole film used about 17 GB of memory for 87 layers). The original file is only replaced when the
    new one was made. `origin`: when the video is only a piece of the film (a preview), where in the film it starts. Returns {count, captions, error?}."""
    from . import captions
    from .export import ffmpeg
    video = os.path.abspath(video)                      # the commands below run in another folder
    placed = [o for o in resolve(d) if o.get("enabled", True) and o["placed"]]
    if duration is None:
        duration = float((_read(os.path.join(d, "songmap.json"), {}) or {}).get("duration") or 0)
    if origin:                                          # a piece of the film: the layers are moved back to its start and only those up during it are kept
        end_at = origin + (duration or 0)
        placed = [{**o, "start": float(o["start"]) - origin, "end": float(o["end"]) - origin} for o in placed if float(o["end"]) > origin and (not duration or float(o["start"]) < end_at)]
    cap = None
    if duration:
        try:
            cap = captions.track(d, W, H, duration + origin)
        except SystemExit as e:
            return {"count": 0, "captions": 0, "error": str(e)}
    if not placed and not cap:
        return {"count": 0, "captions": 0}
    beat = beat_grid(d)
    if beat and origin:
        beat = (beat[0], beat[1] - origin)
    hits = [float(a) - origin for a in ((_read(os.path.join(d, "songmap.json"), {}) or {}).get("accents") or [])[:2000]]
    passes = _passes(placed, round(duration * fps) if duration else None, fps)
    tmp = video + ".overlay.mp4"
    pieces: list[str] = []
    listing = f"{video}.{os.getpid()}.parts.txt"
    tag = str(os.getpid())

    def clean() -> None:
        for f in pieces + [listing, tmp]:
            if os.path.exists(f):
                os.remove(f)
    try:
        if len(passes) == 1:
            err = _pass(d, video, tmp, None, None, passes[0][2], cap, W, H, fps, True, beat, tag, cap_origin=origin, accents=hits)
        else:
            err = None
            for n, (a, b, layers) in enumerate(passes):
                piece = f"{video}.{tag}.part{n}.mp4"
                pieces.append(piece)
                err = _pass(d, video, piece, a, (b - a) if b else None, layers, cap, W, H, fps, False, beat, f"{tag}p{n}", joined=True, cap_origin=origin, accents=hits)
                if err:
                    break
            if not err:
                with open(listing, "w", encoding="utf-8") as fh:
                    for piece, (first_frame, after, _) in zip(pieces, passes):
                        fh.write("file '" + piece.replace("'", "'\\''") + "'\n")
                        if after:                       # say how long the slice is: a file reports its length without its last frame's time, which would shorten every join
                            fh.write(f"duration {(after - first_frame) / fps:.6f}\n")
                r = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing, "-i", video, "-map", "0:v", "-map", "1:a?",
                                    "-c", "copy", "-movflags", "+faststart", tmp], capture_output=True, text=True, creationflags=NO_WINDOW)
                if r.returncode or not os.path.exists(tmp):
                    err = (r.stderr or "")[-200:] or "ffmpeg stopped"
        if err:
            return {"count": 0, "captions": 0, "error": "Drawing the text failed: " + err}
        os.replace(tmp, video)
        return {"count": len(placed), "captions": 1 if cap else 0}
    except SystemExit as e:
        return {"count": 0, "captions": 0, "error": str(e)}
    finally:
        clean()


# ---------------------------------------------------------------- editing

def _f(value, name: str) -> float:
    """A number from what the screen sent: anything else (text, a list, nan) is refused plainly instead of reaching a filter or crashing."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise SystemExit(f"The {name} must be a number.")
    if v != v:
        raise SystemExit(f"The {name} must be a number.")
    return v


def _clean(d: str, x: dict, cur: dict | None = None) -> dict:
    """A validated overlay from what the screen sent: every number clamped, every file inside the project."""
    o = dict(cur or {})
    kind = x.get("kind", o.get("kind", "text"))
    if kind not in ("text", "svg", "image", "fill", "shape", "icon"):
        raise SystemExit("Choose text, a sign, a picture, a colour, a shape or an icon.")
    o["kind"] = kind
    if "text" in x or kind == "text":
        text = str(x.get("text", o.get("text", ""))).strip()[:MAX_TEXT]
        if kind == "text" and not text:
            raise SystemExit("Write the text to show.")
        o["text"] = text
    if "section" in x:
        o["section"] = str(x["section"] or "").strip().lower().replace(" ", "")[:20]
    for k, lo, hi in (("start", 0, 86400), ("end", 0, 86400)):
        if k in x:
            o[k] = None if x[k] in (None, "") else min(hi, max(lo, _f(x[k], k)))
    if o.get("start") is not None and o.get("end") is not None and o["end"] <= o["start"]:
        raise SystemExit("The end must be after the start.")
    for k, lo, hi, dflt in (("x", 0.0, 1.0, 0.5), ("y", 0.0, 1.0, 0.86), ("size", 0.02, 0.3, 0.06), ("width", 0.05, 1.0, 0.6), ("fade", 0.0, 2.0, 0.4)):
        if k in x:
            o[k] = min(hi, max(lo, _f(x[k], k)))
        else:
            o.setdefault(k, dflt)
    if "color" in x:
        o["color"] = "#%02x%02x%02x" % _hex(str(x["color"]))
    o.setdefault("color", "#ffffff")
    if x.get("color2"):
        o["color2"] = "#%02x%02x%02x" % _hex(str(x["color2"]))
    if "anim" in x:
        if x["anim"] not in ANIMS:
            raise SystemExit("Choose one of the movements in the list.")
        o["anim"] = x["anim"]
    o.setdefault("anim", "fade")
    if "cover" in x:
        o["cover"] = bool(x["cover"])
    if "group" in x:
        o["group"] = re.sub(r"[^a-z0-9_:-]", "", str(x["group"]).lower())[:40]
    if "font" in x:
        from . import fonts
        o["font"] = fonts.check(d, x["font"])
    from . import shapes
    if kind == "shape" or "shape" in x:
        if x.get("shape", o.get("shape", "rect")) not in shapes.SHAPES:
            raise SystemExit("Choose a rectangle, rounded box, circle or line.")
        o["shape"] = x.get("shape", o.get("shape", "rect"))
    if kind == "icon" or "icon" in x:
        if x.get("icon", o.get("icon", "star")) not in shapes.ICONS:
            raise SystemExit("Choose one of the icons in the list.")
        o["icon"] = x.get("icon", o.get("icon", "star"))
    for k, lo, hi in (("height", 0.002, 1.0), ("stroke_w", 0.0, 0.05), ("opacity", 0.05, 1.0), ("rotation", -180.0, 180.0), ("radius", 0.0, 0.5), ("scale", 0.1, 5.0), ("angle", 0.0, 360.0)):
        if k in x:
            o[k] = min(hi, max(lo, _f(x[k], k)))
    if x.get("stroke"):
        o["stroke"] = "#%02x%02x%02x" % _hex(str(x["stroke"]))
    if "filled" in x:
        o["filled"] = bool(x["filled"])
    for k in ("gradient", "shadow"):
        if k in x:
            o[k] = bool(x[k])
    if "keys" in x:
        keys = clean_keys(x["keys"])
        if keys:
            o["keys"] = keys
        else:
            o.pop("keys", None)
    if kind == "shape":
        o.setdefault("height", 0.006 if o.get("shape") == "line" else 0.2)
        o.setdefault("stroke", "#ffffff")
    if "name" in x:
        o["name"] = " ".join(str(x["name"] or "").split())[:60]
    if "enabled" in x:
        o["enabled"] = bool(x["enabled"])
    o.setdefault("enabled", True)
    o.setdefault("source", "manual")
    return o


def add(d: str, x: dict) -> list[dict]:
    items = load(d)
    if len(items) >= MAX_OVERLAYS:
        raise SystemExit(f"A project can have {MAX_OVERLAYS} overlays at most.")
    if x.get("image") and not x.get("kind"):
        x = {**x, "kind": "image"}                  # a chosen picture file is a picture overlay unless said otherwise
    o = _clean(d, x)
    o["id"] = "ov_" + uuid.uuid4().hex[:8]
    if x.get("image"):                           # a picture or sign file chosen on disk: copied into the project
        src = str(x["image"])
        ext = os.path.splitext(src)[1].lower()
        if ext not in IMAGE_EXT or not os.path.isfile(src):
            raise SystemExit("Use a PNG, JPG, WebP or text-sign SVG file.")
        if os.path.getsize(src) > MAX_FILE:
            raise SystemExit("That file is too large (25 MB at most).")
        os.makedirs(os.path.join(d, "assets", "overlays"), exist_ok=True)
        rel = f"assets/overlays/{o['id']}{ext}"
        shutil.copy2(src, os.path.join(d, rel))
        o["file"] = rel
        o["kind"] = "svg" if ext == ".svg" else "image"
        o.setdefault("text", os.path.basename(src)[:80])
    elif o["kind"] not in ("text", "fill", "shape", "icon"):
        raise SystemExit("Choose the picture for this overlay.")
    items.append(o)
    _save(d, items)
    return resolve(d)


def update(d: str, oid: str, x: dict) -> list[dict]:
    items = load(d)
    i = next((k for k, o in enumerate(items) if o.get("id") == oid), None)
    if i is None:
        raise SystemExit("That overlay isn't in the project.")
    items[i] = {**_clean(d, x, items[i]), "id": oid}
    _save(d, items)
    return resolve(d)


def remove(d: str, oid: str) -> list[dict]:
    items = load(d)
    _save(d, [o for o in items if o.get("id") != oid])
    return resolve(d)


def reorder(d: str, oid: str, to) -> list[dict]:
    """Move a layer in the drawing order (the list order: the last one is drawn on top). `to` is up | down | top | bottom, or a list position."""
    items = load(d)
    i = next((k for k, o in enumerate(items) if o.get("id") == oid), None)
    if i is None:
        raise SystemExit("That overlay isn't in the project.")
    last = len(items) - 1
    if to == "up":
        j = min(last, i + 1)
    elif to == "down":
        j = max(0, i - 1)
    elif to == "top":
        j = last
    elif to == "bottom":
        j = 0
    else:
        try:
            j = min(last, max(0, int(to)))
        except (TypeError, ValueError):
            raise SystemExit("Choose up, down, top or bottom.")
    items.insert(j, items.pop(i))
    _save(d, items)
    return resolve(d)


def duplicate(d: str, oid: str) -> list[dict]:
    """A copy of a layer just above it, nudged down a little so it can be seen."""
    items = load(d)
    if len(items) >= MAX_OVERLAYS:
        raise SystemExit(f"A project can have {MAX_OVERLAYS} overlays at most.")
    i = next((k for k, o in enumerate(items) if o.get("id") == oid), None)
    if i is None:
        raise SystemExit("That overlay isn't in the project.")
    copy = {**items[i], "id": "ov_" + uuid.uuid4().hex[:8], "y": min(1.0, round(float(items[i].get("y", 0.5)) + 0.05, 3)), "source": "manual"}
    copy.pop("group", None)                              # a copy of a title-card part is its own layer, not part of the card
    if items[i].get("name"):
        copy["name"] = (str(items[i]["name"]) + " copy")[:60]
    items.insert(i + 1, copy)
    _save(d, items)
    return resolve(d)


def preview(d: str, oid: str, W: int = 960, H: int = 540) -> dict:
    """The overlay where it will sit on a dark 16:9 stand-in frame (a still, nothing is rendered or billed)."""
    from PIL import Image
    o = next((x for x in load(d) if x.get("id") == oid), None)
    if not o:
        raise SystemExit("That overlay isn't in the project.")
    png, size = render_png(d, o, W, H)
    frame = Image.new("RGBA", (W, H), (38, 42, 52, 255))
    with Image.open(png) as ov:
        frame.alpha_composite(ov.convert("RGBA"), _position(o, size, W, H))
    out = os.path.join(d, "cache", "overlays", f"preview-{oid}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    frame.convert("RGB").save(out)
    return {"path": os.path.relpath(out, d).replace(os.sep, "/")}


def sync_package(d: str) -> list[dict]:
    """Bring in the text signs a Producer package listed in overlay_map.json: {id, text, section, file}. Re-importing updates a sign's
    text and picture but keeps what you changed (timing, position, size, whether it is on)."""
    mp = _read(os.path.join(d, "assets", "producer", "overlay_map.json"), None)
    if not isinstance(mp, list):
        return load(d)
    items = load(d)
    have = {o.get("package_id"): o for o in items if o.get("package_id")}
    for e in mp[:MAX_OVERLAYS]:
        if not isinstance(e, dict) or not e.get("id") or not e.get("file"):
            continue
        name = re.sub(r"[^\w.\-]+", "_", os.path.basename(str(e["file"])))
        rel = f"assets/producer/{name}"
        if not os.path.isfile(os.path.join(d, rel)) or not name.lower().endswith(IMAGE_EXT):
            continue
        cur = have.get(e["id"])
        base = {"kind": "svg" if name.lower().endswith(".svg") else "image", "text": str(e.get("text", ""))[:MAX_TEXT], "file": rel,
                "section": str(e.get("section", "")).strip().lower().replace(" ", "")[:20], "source": "package", "package_id": e["id"]}
        if cur:
            cur.update(base)
            continue
        o = _clean(d, {"kind": base["kind"], "text": base["text"], "section": base["section"]})
        o.update(base)
        o["id"] = "ov_" + uuid.uuid4().hex[:8]
        multi = len(str(e.get("text", "")).split("|")) > 1 or "\n" in str(e.get("text", ""))
        o.update(width=0.5 if multi else 0.6, y=0.5 if multi else 0.86)       # a chart sits in the middle; a sign in the lower third
        items.append(o)
    _save(d, items)
    return resolve(d)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-overlays")
    ap.add_argument("action", choices=["list", "add", "update", "remove", "preview", "sync", "reorder", "duplicate", "history", "undo", "redo"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "list":
            res = resolve(a.project)
        elif a.action == "add":
            res = add(a.project, x)
        elif a.action == "update":
            res = update(a.project, x["id"], x)
        elif a.action == "remove":
            res = remove(a.project, x["id"])
        elif a.action == "sync":
            res = sync_package(a.project)
        elif a.action == "reorder":
            res = reorder(a.project, x["id"], x.get("to"))
        elif a.action == "duplicate":
            res = duplicate(a.project, x["id"])
        elif a.action == "history":
            res = history(a.project)
        elif a.action == "undo":
            res = undo(a.project)
        elif a.action == "redo":
            res = redo(a.project)
        else:
            res = preview(a.project, x["id"])
        print(json.dumps({"event": "result", "data": res}), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except Exception as e:
        print(json.dumps({"event": "error", "message": f"{type(e).__name__}: {e}"}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
