"""The intro title card: a title (and subtitle) that moves in over a backdrop, laid on the part of the song before the first shot.

A card is a few on-screen overlays (a backdrop, the title, the subtitle) that share a group, so it can be redesigned or removed as one.
The backdrop is a colour or gradient, or a picture you choose (scaled to fill the frame, with a slow push-in). Nothing here costs money:
it is drawn at export. For a moving backdrop the card can also create an ordinary *intro shot* from a prompt (and, if you give one, a
picture that becomes its first frame); that shot is rendered like any other, after you have seen the price.

  python -m pulseframe_analysis.titlecard <state|preview|make|remove|intro_shot> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import hashlib
from .safe import sha1 as _sha1
import json
import os
import re
import shutil
import sys
import time
import uuid

from . import overlays as O

GROUP = "card:intro"
MAX_TITLE, MAX_SUB, MAX_PROMPT = 80, 120, 600
PICTURE_EXT = (".png", ".jpg", ".jpeg", ".webp")
BACKDROPS = ("none", "colour", "picture")


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data) -> None:
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def _plan(d: str) -> tuple[str, dict]:
    name = "directed" if os.path.exists(os.path.join(d, "directed.json")) else "production"
    return name, _read(os.path.join(d, f"{name}.json"), {"scenes": []}) or {"scenes": []}


def gap(d: str) -> tuple[float, float] | None:
    """The part of the song before the first shot (0 to the first shot's start), when it is long enough to hold a card."""
    _, plan = _plan(d)
    starts = [float(s["start"]) for sc in plan.get("scenes", []) for s in sc.get("shots", [])]
    if starts and min(starts) >= 1.5:
        return 0.0, round(min(starts), 3)
    return None


def span(d: str) -> tuple[float, float] | None:
    """Where the card sits: the part before the first shot, or, once an intro shot has been added there, that shot's time."""
    g = gap(d)
    if g:
        return g
    _, plan = _plan(d)
    for sc in plan.get("scenes", []):
        for s in sc.get("shots", []):
            if s.get("intro"):
                return float(s["start"]), float(s["end"])
    return None


def _song_duration(d: str) -> float:
    return float((_read(os.path.join(d, "songmap.json"), {}) or {}).get("duration") or 0)


def _text(x, n: int) -> str:
    return " ".join(str(x or "").split())[:n]


def _picture(d: str, src: str) -> str:
    """A picture chosen on disk, copied into the project (as PNG when it is another type); the path inside the project."""
    src = os.path.abspath(str(src or ""))
    if not (os.path.isfile(src) and src.lower().endswith(PICTURE_EXT)):
        raise SystemExit("Choose a PNG, JPG or WebP picture.")
    if os.path.getsize(src) > O.MAX_FILE:
        raise SystemExit("That picture is larger than 25 MB.")
    from PIL import Image
    try:
        with Image.open(src) as im:
            im.verify()
    except Exception:
        raise SystemExit("That file does not open as a picture.")
    os.makedirs(os.path.join(d, "assets", "overlays"), exist_ok=True)
    rel = f"assets/overlays/card-{uuid.uuid4().hex[:8]}{os.path.splitext(src)[1].lower()}"
    shutil.copy2(src, os.path.join(d, rel))
    return rel


def clean(d: str, spec: dict) -> dict:
    """The card's settings, validated: text trimmed, numbers clamped, the backdrop and movement from the allowed lists."""
    title = _text(spec.get("title"), MAX_TITLE)
    if not title:
        raise SystemExit("Write the title.")
    bg = spec.get("background") or {}
    kind = bg.get("type", "none")
    if kind not in BACKDROPS:
        raise SystemExit("Choose a black, colour or picture backdrop.")
    anim = spec.get("anim", "rise")
    if anim not in O.ANIMS:
        raise SystemExit("Choose one of the movements in the list.")
    g = span(d)
    dur = _song_duration(d)
    start = spec.get("start")
    end = spec.get("end")
    if start is None:
        start = (g[0] + min(0.4, (g[1] - g[0]) / 6)) if g else 0.4
    if end is None:
        end = (g[1] - min(0.4, (g[1] - g[0]) / 6)) if g else min(dur or 6.0, 6.0)
    start, end = max(0.0, float(start)), float(end)
    if dur:
        end = min(end, dur)
    if end - start < 1.0:
        raise SystemExit("The card needs at least a second on screen.")
    out = {"title": title, "subtitle": _text(spec.get("subtitle"), MAX_SUB), "anim": anim, "start": round(start, 2), "end": round(end, 2),
           "color": "#%02x%02x%02x" % O._hex(str(spec.get("color") or "#ffffff")), "size": min(0.16, max(0.04, float(spec.get("size") or 0.09))),
           "background": {"type": kind}}
    if spec.get("font"):
        from . import fonts
        out["font"] = fonts.check(d, spec["font"])
    if kind == "colour":
        out["background"]["color"] = "#%02x%02x%02x" % O._hex(str(bg.get("color") or "#101820"))
        if bg.get("color2"):
            out["background"]["color2"] = "#%02x%02x%02x" % O._hex(str(bg["color2"]))
    if kind == "picture":
        if bg.get("file") and not bg.get("picture"):          # the picture of a card made before: kept as it is
            f = str(bg["file"])
            p = os.path.join(d, f)
            if not (os.path.isfile(p) and O._inside(d, p)):
                raise SystemExit("The backdrop picture is missing. Choose it again.")
            out["background"]["file"] = f
        else:
            out["background"]["picture"] = str(bg.get("picture") or "")
    return out


def _members(d: str) -> list[dict]:
    return [o for o in O.load(d) if o.get("group") == GROUP]


def remove(d: str) -> dict:
    """Take the intro card away (all of its parts)."""
    keep = [o for o in O.load(d) if o.get("group") != GROUP]
    O._save(d, keep)
    return state(d)


def make(d: str, spec: dict) -> dict:
    """Create (or replace) the intro card from the settings."""
    c = clean(d, spec)
    bg = c["background"]
    picture = None
    if bg["type"] == "picture":
        picture = bg.get("file") or _picture(d, bg["picture"])
    keep = [o for o in O.load(d) if o.get("group") != GROUP]
    O._save(d, keep)
    common = {"group": GROUP, "start": c["start"], "end": c["end"]}
    if bg["type"] == "colour":
        O.add(d, {**common, "kind": "fill", "text": "Intro backdrop", "color": bg["color"], "color2": bg.get("color2") or bg["color"], "cover": True, "fade": 0.6, "anim": "fade"})
    elif bg["type"] == "picture":
        items = O.load(d)
        o = O._clean(d, {**common, "kind": "image", "text": "Intro backdrop", "cover": True, "fade": 0.6, "anim": "pushin"})
        o["id"], o["file"] = "ov_" + uuid.uuid4().hex[:8], picture
        items.append(o)
        O._save(d, items)
    t = {**common, "kind": "text", "text": c["title"], "x": 0.5, "y": 0.46 if c["subtitle"] else 0.5, "size": c["size"], "color": c["color"], "fade": 0.7, "anim": c["anim"]}
    if c.get("font"):
        t["font"] = c["font"]
    O.add(d, t)
    if c["subtitle"]:
        sub = {**common, "kind": "text", "text": c["subtitle"], "start": min(c["end"] - 0.5, c["start"] + 0.5), "x": 0.5, "y": 0.62, "size": max(0.03, round(c["size"] * 0.45, 3)),
               "color": c["color"], "fade": 0.7, "anim": "fade"}
        if c.get("font"):
            sub["font"] = c["font"]
        O.add(d, sub)
    return state(d)


def state(d: str) -> dict:
    parts = _members(d)
    card = None
    if parts:
        title = next((p for p in parts if p.get("kind") == "text"), parts[0])
        subs = [p for p in parts if p.get("kind") == "text" and p is not title]
        back = next((p for p in parts if p.get("kind") in ("fill", "image")), None)
        card = {"title": title.get("text", ""), "subtitle": subs[0]["text"] if subs else "", "anim": title.get("anim", "fade"), "start": title.get("start"), "end": title.get("end"),
                "color": title.get("color", "#ffffff"), "size": title.get("size", 0.09), "font": title.get("font"),
                "background": ({"type": "colour", "color": back.get("color"), "color2": back.get("color2")} if back and back["kind"] == "fill"
                               else {"type": "picture", "file": back.get("file")} if back else {"type": "none"})}
    proj = _read(os.path.join(d, "project.json"), {}) or {}
    return {"gap": gap(d), "span": span(d), "card": card, "title": _text(proj.get("title"), MAX_TITLE), "animations": [{"id": a, "name": O.ANIM_NAMES[a]} for a in O.ANIMS]}


def preview(d: str, spec: dict, W: int = 960, H: int = 540) -> dict:
    """A still of how the card looks once it has settled (a picture in the project's cache), without changing anything."""
    from PIL import Image
    c = clean(d, {**spec, "background": {k: v for k, v in (spec.get("background") or {}).items()}})
    base = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    bg = c["background"]
    if bg["type"] == "colour":
        base.alpha_composite(O.render_image(d, {"kind": "fill", "color": bg["color"], "color2": bg.get("color2") or bg["color"]}, W, H))
    elif bg["type"] == "picture":
        src = bg.get("file") and os.path.join(d, bg["file"]) or bg.get("picture")
        if src and os.path.isfile(src):
            tmp = Image.open(src).convert("RGBA")
            k = max(W / tmp.width, H / tmp.height)
            tmp = tmp.resize((max(W, round(tmp.width * k)), max(H, round(tmp.height * k))))
            left, top = (tmp.width - W) // 2, (tmp.height - H) // 2
            base.alpha_composite(tmp.crop((left, top, left + W, top + H)))

    def put(text, y, size, anim="fade"):
        o = {"kind": "text", "text": text, "x": 0.5, "y": y, "size": size, "color": c["color"], "font": c.get("font")}
        im = O.render_image(d, o, W, H)
        x, yy = O._position(o, im.size, W, H)
        base.alpha_composite(im, (x, yy))
    put(c["title"], 0.46 if c["subtitle"] else 0.5, c["size"])
    if c["subtitle"]:
        put(c["subtitle"], 0.62, max(0.03, round(c["size"] * 0.45, 3)))
    key = _sha1(json.dumps(c, sort_keys=True).encode()).hexdigest()[:12]
    rel = f"cache/overlays/card-preview-{key}.png"
    os.makedirs(os.path.join(d, "cache", "overlays"), exist_ok=True)
    out = os.path.join(d, rel)
    base.convert("RGB").save(out + ".part.png")
    os.replace(out + ".part.png", out)
    return {"path": rel}


def intro_shot(d: str, spec: dict) -> dict:
    """Add an ordinary shot over the part of the song before the first shot: you describe the motion (and may choose a picture to start
    from), then make its keyframe and video like any other shot. Returns {shot}."""
    prompt = _text(spec.get("prompt"), MAX_PROMPT)
    if not prompt:
        raise SystemExit("Describe what should move or appear behind the title.")
    g = gap(d)
    if not g:
        raise SystemExit("There is no room before the first shot for an intro (it needs at least a second and a half).")
    name, plan = _plan(d)
    if not plan.get("scenes"):
        raise SystemExit("This project has no shots yet.")
    scene = plan["scenes"][0]
    existing = {s["id"] for sc in plan["scenes"] for s in sc["shots"]}
    base = f"S{int(scene.get('number', 1)):02d}-00"
    sid = base
    for suffix in ("", "b", "c", "d", "e", "f"):
        sid = base + suffix
        if sid not in existing:
            break
    else:
        raise SystemExit("An intro shot already exists. Use that one.")
    end = g[1]
    keyframe = None
    if spec.get("picture"):
        rel = _picture(d, spec["picture"])
        from PIL import Image
        from .safe import file_part
        png = f"assets/refs/intro-{file_part(sid)}.png"
        os.makedirs(os.path.join(d, "assets", "refs"), exist_ok=True)
        with Image.open(os.path.join(d, rel)) as im:
            im.convert("RGB").save(os.path.join(d, png))
        keyframe = "project:" + png
    shot = {"id": sid, "scene": scene.get("number", 1), "number": 0, "start": g[0], "end": end, "duration_seconds": round(end - g[0], 3),
            "source_shots": [], "beats": [prompt], "dropped_beats": [], "purpose": "Opening backdrop for the title card", "performers": [],
            "emotion": "", "performance_intensity": 3, "performance": "", "expression": "", "movement": "", "framing": "Wide", "lens": "", "camera_movement": "Slow push-in",
            "camera_energy": "gentle", "lighting": "", "environment": "", "wardrobe": "", "continuity": "", "sync_event": "",
            "visual_prompt": f"{prompt.rstrip('. ')}. An abstract opening backdrop with calm room in the middle for a title. No text, no letters, no logos.",
            "renderer": "auto", "state": "planned", "revised": int(time.time()), "intro": True}
    scene["shots"].insert(0, shot)
    scene["start"] = min(float(scene.get("start", g[0])), g[0])
    _write(os.path.join(d, f"{name}.json"), plan)
    if keyframe:
        kp = os.path.join(d, "keyframes.json")
        kf = _read(kp, {}) or {}
        kf.setdefault(name, {})[sid] = keyframe
        _write(kp, kf)
    return {"shot": sid, "plan": name, "keyframe": bool(keyframe), "start": g[0], "end": end}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="pulseframe-titlecard")
    ap.add_argument("action", choices=["state", "preview", "make", "remove", "intro_shot"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "state":
            res = state(a.project)
        elif a.action == "preview":
            res = preview(a.project, x)
        elif a.action == "make":
            res = make(a.project, x)
        elif a.action == "remove":
            res = remove(a.project)
        else:
            res = intro_shot(a.project, x)
        emit(event="result", data=res)
        return 0
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
