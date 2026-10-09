"""Lyric captions: the words of the song (or the lines of a spoken scene) drawn on the exported film as it plays, and written to an
.srt subtitles file next to it.

The lines always come from the analysed song map (the lyrics PULSEFRAME aligned to the audio, or a spoken scene's exact dialogue
timings), so there is nothing to keep in step. What you change is kept apart from them:

  <project>/captions.json   {"enabled": bool, "style": {...}, "edits": {line_key: {"text", "hidden", "start", "end"}}}

Look is layered: the film's style, then a section's (say every CHORUS line bigger), then a single line's own size, colour or
position. A layer that says nothing inherits the one below it.

A line's key is made from its own words (and how many times those words have occurred), not from its position, so your edits
survive re-analysing the song, and an edit follows the line it was made to even if timings move.

Captions are drawn as ONE extra stream over the picture (each caption a transparent full-frame still held for its time), not one
input per line, so a song with sixty lines costs about what one overlay does. Words reach the picture only through Pillow; ffmpeg is
given file names this module made and validated numbers.

  python -m pulseframe_analysis.captions <get|set|edit|preview> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import hashlib
from .safe import sha1 as _sha1
import json
import os
import re
import sys

MAX_LINES = 600
MIN_SHOW = 0.8          # seconds a caption stays at least
LINGER = 0.15
GAP = 0.05
DEFAULTS = {"size": 0.05, "y": 0.9, "color": "#ffffff", "font": "", "names": False, "srt": True, "uppercase": False}
LOOK = ("size", "y", "color", "font")          # what a section or a single line may set for itself
LOOK_LIMITS = {"size": (0.02, 0.15), "y": (0.05, 0.95)}


def _look_value(d: str, k: str, v):
    """A size, position, colour or font, clamped or checked; None (or "") means inherit."""
    if v in (None, ""):
        return None
    if k == "font":
        from . import fonts
        return fonts.check(d, v)
    if k == "color":
        c = str(v).strip().lstrip("#")
        return "#" + c.lower() if re.fullmatch(r"[0-9a-fA-F]{6}", c) else None
    lo, hi = LOOK_LIMITS[k]
    return min(hi, max(lo, float(v)))


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


def load(d: str) -> dict:
    c = _read(os.path.join(d, "captions.json"), {}) or {}
    return {"enabled": bool(c.get("enabled")), "style": {**DEFAULTS, **(c.get("style") or {})}, "edits": c.get("edits") or {},
            "sections": c.get("sections") or {}}


def _save(d: str, c: dict) -> None:
    _write(os.path.join(d, "captions.json"), {"schema": 1, **c})


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", str(text).lower().replace("’", "'")))


def lines(d: str) -> list[dict]:
    """The caption lines in order, with your edits applied: {key, text, original, start, end, hidden, edited, section, performer}."""
    sm = _read(os.path.join(d, "songmap.json"), {}) or {}
    cfg = load(d)
    raw = [x for x in sm.get("lyrics") or [] if x.get("text") and x.get("start") is not None]
    raw.sort(key=lambda x: float(x["start"]))
    seen: dict[str, int] = {}
    out = []
    for x in raw[:MAX_LINES]:
        h = _sha1(_norm(x["text"]).encode()).hexdigest()[:8]
        seen[h] = seen.get(h, 0) + 1
        key = f"{h}-{seen[h]}"
        e = cfg["edits"].get(key) or {}
        text = " ".join(str(e.get("text") if e.get("text") is not None else x["text"]).split())[:300]
        start = float(e["start"]) if e.get("start") is not None else float(x["start"])
        end = float(e["end"]) if e.get("end") is not None else float(x["end"] if x.get("end") is not None else start + 3.0)
        section = str(x.get("section") or "")
        sec = cfg["sections"].get(section.upper()) or {}
        own = {k: e[k] for k in LOOK if e.get(k) is not None}
        out.append({"key": key, "text": text, "original": str(x["text"]), "start": start, "end": end, "hidden": bool(e.get("hidden")),
                    "edited": bool(e), "section": section, "performer": x.get("performer") or "", "own": own,
                    "look": {k: own.get(k, sec.get(k, cfg["style"][k])) for k in LOOK}})
    # a caption never runs into the next one and stays long enough to read
    visible = [o for o in out if not o["hidden"]]
    for a, b in zip(visible, visible[1:] + [None]):
        limit = (b["start"] - GAP) if b else float(sm.get("duration") or a["end"] + 5)
        a["end"] = max(a["start"] + 0.2, min(max(a["end"] + LINGER, a["start"] + MIN_SHOW), limit))
    return out


def caption_text(o: dict, style: dict) -> str:
    t = o["text"].upper() if style.get("uppercase") else o["text"]
    return f"{o['performer']}: {t}" if style.get("names") and o.get("performer") else t


# ---------------------------------------------------------------- drawing

def _frame_png(d: str, o: dict, style: dict, W: int, H: int) -> str:
    """One caption as a transparent full-frame still (so it needs no position of its own at export)."""
    from PIL import Image
    from . import overlays as O
    style = {**style, **(o.get("look") or {})}
    text = caption_text(o, style)
    from . import fonts
    spec = {"kind": "text", "text": text, "size": style["size"], "color": style["color"], "font": style.get("font") or ""}
    key = _sha1(json.dumps([text, style["size"], style["y"], style["color"], W, H, fonts.signature(d, spec["font"])]).encode()).hexdigest()[:14]
    out = os.path.join(d, "cache", "captions", f"{key}.png")
    if not os.path.exists(out):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        ov = O.render_image(d, spec, W, H)
        frame = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        frame.alpha_composite(ov, O._position({"x": 0.5, "y": style["y"]}, ov.size, W, H))
        frame.save(out + ".part.png")
        os.replace(out + ".part.png", out)
    return out


def _blank(d: str, W: int, H: int) -> str:
    from PIL import Image
    out = os.path.join(d, "cache", "captions", f"blank-{W}x{H}.png")
    if not os.path.exists(out):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(out)
    return out


def track(d: str, W: int, H: int, duration: float) -> str | None:
    """A concat list (ffconcat) that holds each caption still for its time and a blank between, covering the whole film; None when
    captions are off or there is nothing to show."""
    cfg = load(d)
    if not cfg["enabled"]:
        return None
    vis = [o for o in lines(d) if not o["hidden"] and caption_text(o, cfg["style"]).strip() and o["start"] < duration]
    if not vis:
        return None
    work = os.path.join(d, "cache", "captions")
    entries, t = [], 0.0
    blank = _blank(d, W, H)

    def add(path: str, secs: float) -> None:
        if secs > 0.001:
            entries.append((path, secs))

    for o in vis:
        start, end = max(t, o["start"]), min(o["end"], duration)
        if end <= start:
            continue
        add(blank, start - t)
        add(_frame_png(d, o, cfg["style"], W, H), end - start)
        t = end
    add(blank, duration - t + 0.5)
    lst = os.path.join(work, "track.ffconcat")
    with open(lst, "w", encoding="utf-8") as f:
        f.write("ffconcat version 1.0\n")
        for path, secs in entries:
            f.write(f"file '{path.replace(os.sep, '/')}'\nduration {secs:.3f}\n")
        f.write(f"file '{entries[-1][0].replace(os.sep, '/')}'\n")       # the concat demuxer needs the last file named again
    return lst


def write_srt(d: str, video: str) -> str | None:
    """The visible captions as an .srt next to the film (same name)."""
    cfg = load(d)
    if not (cfg["enabled"] and cfg["style"].get("srt")):
        return None
    from .show_finish import write_srt as _srt
    cues = [(o["start"], o["end"], caption_text(o, cfg["style"])) for o in lines(d) if not o["hidden"] and o["text"].strip()]
    if not cues:
        return None
    path = os.path.splitext(video)[0] + ".srt"
    _srt(path, cues)
    return path


# ---------------------------------------------------------------- editing

def get(d: str) -> dict:
    sm = _read(os.path.join(d, "songmap.json"), {}) or {}
    cfg = load(d)
    ls = lines(d)
    reason = "" if ls else ("The song hasn't been analysed yet." if not sm else "The song map has no timed lyrics. Add the lyrics when you set up the song, then analyse it again.")
    return {"enabled": cfg["enabled"], "style": cfg["style"], "lines": ls, "available": bool(ls), "reason": reason,
            "sections": cfg["sections"], "section_names": sorted({o["section"].upper() for o in ls if o["section"]})}


def set_style(d: str, x: dict) -> dict:
    cfg = load(d)
    if "enabled" in x:
        cfg["enabled"] = bool(x["enabled"])
    st = cfg["style"]
    for k, lo, hi in (("size", 0.02, 0.15), ("y", 0.05, 0.95)):
        if k in x:
            st[k] = min(hi, max(lo, float(x[k])))
    for k in ("names", "srt", "uppercase"):
        if k in x:
            st[k] = bool(x[k])
    if "color" in x:
        c = str(x["color"]).strip().lstrip("#")
        st["color"] = "#" + (c if re.fullmatch(r"[0-9a-fA-F]{6}", c) else "ffffff")
    if "font" in x:
        from . import fonts
        st["font"] = fonts.check(d, x["font"])
    _save(d, cfg)
    return get(d)


def set_section(d: str, section: str, x: dict) -> dict:
    """The look of every caption in one song section (CHORUS, VERSE...). Say nothing for a value to inherit the film's; reset clears it."""
    name = str(section or "").strip().upper()[:40]
    if not name:
        raise SystemExit("Choose a section.")
    cfg = load(d)
    if x.get("reset"):
        cfg["sections"].pop(name, None)
    else:
        cur = dict(cfg["sections"].get(name) or {})
        for k in LOOK:
            if k in x:
                v = _look_value(d, k, x[k])
                if v is None:
                    cur.pop(k, None)
                else:
                    cur[k] = v
        if cur:
            cfg["sections"][name] = cur
        else:
            cfg["sections"].pop(name, None)
    _save(d, cfg)
    return get(d)


def edit(d: str, key: str, x: dict) -> dict:
    """Change one line: its words, its times, hide it, or put it back (reset)."""
    cfg = load(d)
    if not any(o["key"] == key for o in lines(d)):
        raise SystemExit("That line isn't in the song's lyrics any more.")
    if x.get("reset"):
        cfg["edits"].pop(key, None)
    else:
        e = dict(cfg["edits"].get(key) or {})
        if "text" in x:
            t = " ".join(str(x["text"]).split())[:300]
            if not t:
                raise SystemExit("Write the caption, or hide the line instead.")
            e["text"] = t
        if "hidden" in x:
            e["hidden"] = bool(x["hidden"])
        for k in LOOK:                                  # this line's own size, colour or position (empty = like its section)
            if k in x:
                e[k] = _look_value(d, k, x[k])
        for k in ("start", "end"):
            if k in x:
                e[k] = None if x[k] in (None, "") else max(0.0, float(x[k]))
        if e.get("start") is not None and e.get("end") is not None and e["end"] <= e["start"]:
            raise SystemExit("The end must be after the start.")
        cfg["edits"][key] = {k: v for k, v in e.items() if v is not None}
    _save(d, cfg)
    return get(d)


def preview(d: str, key: str | None = None, W: int = 960, H: int = 540) -> dict:
    """A caption on a dark stand-in frame, exactly where it will sit (the chosen line, else the first visible one)."""
    from PIL import Image
    cfg = load(d)
    ls = [o for o in lines(d) if not o["hidden"]]
    o = next((x for x in ls if x["key"] == key), None) or (ls[0] if ls else None)
    if not o:
        raise SystemExit("There is no caption to preview.")
    png = _frame_png(d, o, cfg["style"], W, H)
    frame = Image.new("RGBA", (W, H), (38, 42, 52, 255))
    with Image.open(png) as ov:
        frame.alpha_composite(ov.convert("RGBA"))
    out = os.path.join(d, "cache", "captions", "preview.png")
    frame.convert("RGB").save(out)
    return {"path": os.path.relpath(out, d).replace(os.sep, "/")}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="pulseframe-captions")
    ap.add_argument("action", choices=["get", "set", "edit", "preview", "section"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "get":
            res = get(a.project)
        elif a.action == "set":
            res = set_style(a.project, x)
        elif a.action == "edit":
            res = edit(a.project, x["key"], x)
        elif a.action == "section":
            res = set_section(a.project, x["section"], x)
        else:
            res = preview(a.project, x.get("key"))
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
