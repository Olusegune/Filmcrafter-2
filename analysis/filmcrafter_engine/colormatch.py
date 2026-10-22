"""Colour matching between shots: AI renders of one scene can differ in brightness, contrast and colour cast from shot to shot. This looks at the take each shot uses,
works out how far each is from the typical shot (or from a shot you choose), and writes a small correction per shot that the export applies. Nothing is re-rendered, nothing is
sent anywhere, and the takes themselves are never changed: the correction is only applied when the film is put together, and can be turned off or cleared.

The correction is a straight-line adjustment of brightness (Y) and the two colour channels (U, V), strong enough to move a shot towards the reference by `strength` (0 to 1).

Two more things AI pictures often need, both applied only when the film is put together:
  cast      a colour cast that runs through the WHOLE film (the yellow, orange or golden tint some image models put over everything). Matching shots to the typical shot cannot remove it,
            because the typical shot has it too. So the film's own average colour is measured and moved back towards neutral by one shared offset (each shot keeps its own differences: a night
            scene stays blue, a sunset stays warm). Small casts are left alone.
  finish    a light denoise (`hqdn3d`) and an optional fine grain that hides a waxy, over-smooth look. Both are off until you turn them on.

  python -m filmcrafter_engine.colormatch <state|analyze|set|clear> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time

GRADE = "grade.json"
CAST_MIN = 3.0                           # a film-wide cast smaller than this (in studio-range colour units) is not a cast worth correcting
CAST_MAX = 18.0                          # and one correction never moves the colour by more than this
DENOISE = "hqdn3d=2.0:1.5:3.0:3.0"       # a light, temporal denoise
GRAIN = "noise=alls=5:allf=t"            # a fine, moving grain
MIN_GAIN, MAX_GAIN = 0.75, 1.35          # a correction never stretches or squeezes a channel more than this
IGNORE_BELOW = 0.06                      # shots already this close to the reference (as a fraction of the range) are left alone
SAMPLES = (0.2, 0.5, 0.8)


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


def _write(path: str, data) -> None:
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    for i in range(40):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == 39:
                raise
            time.sleep(0.05)


def load(d: str) -> dict:
    g = _read(os.path.join(d, GRADE), {}) or {}
    return {"enabled": bool(g.get("enabled", False)), "strength": min(1.0, max(0.0, float(g.get("strength", 0.7)))), "reference": g.get("reference"),
            "shots": g.get("shots") or {}, "stats": g.get("stats") or {}, "analysed": g.get("analysed"),
            "cast": bool(g.get("cast", False)), "cast_strength": min(1.0, max(0.0, float(g.get("cast_strength", 0.85)))), "cast_fix": g.get("cast_fix"), "cast_seen": g.get("cast_seen"),
            "denoise": bool(g.get("denoise", False)), "grain": bool(g.get("grain", False))}


def measure_cast(stats: dict) -> dict | None:
    """The colour cast that runs through the whole film: the median colour of the shots against neutral. {"u", "v", "size", "label"} (u and v are how far the film leans, in colour units)."""
    if not stats:
        return None
    mu = statistics.median(s["u"][0] for s in stats.values()) - 128.0
    mv = statistics.median(s["v"][0] for s in stats.values()) - 128.0
    size = (mu * mu + mv * mv) ** 0.5
    if mu < 0 and abs(mv) < abs(mu) * 0.4:
        label = "yellow"
    elif mu < 0 and mv > 0:
        label = "yellow-orange"
    elif mu < 0:
        label = "yellow-green"
    elif mv > 0:
        label = "magenta"
    else:
        label = "blue-green" if mu > abs(mv) * 0.4 else "green"
    return {"u": round(mu, 2), "v": round(mv, 2), "size": round(size, 2), "label": label, "noticeable": size >= CAST_MIN}


def cast_fix_of(seen: dict | None, strength: float) -> dict | None:
    """The shared offset that moves the film's colour back towards neutral, or None when there is no cast worth correcting."""
    if not seen or not seen.get("noticeable"):
        return None
    cl = lambda x: max(-CAST_MAX, min(CAST_MAX, x))
    return {"u": round(cl(-seen["u"] * strength), 2), "v": round(cl(-seen["v"] * strength), 2)}


def _yuv(rgb):
    """Mean and spread of Y, U, V (HD matrix, studio range, as the film is stored) over some RGB pixels (an N x 3 array of 0..255)."""
    import numpy as np
    r, g, b = (rgb[:, i].astype(float) / 255.0 for i in range(3))
    y = 16 + 219 * (0.2126 * r + 0.7152 * g + 0.0722 * b)
    u = 128 + 224 * (-0.1146 * r - 0.3854 * g + 0.5 * b)
    v = 128 + 224 * (0.5 * r - 0.4542 * g - 0.0458 * b)
    return {k: [float(np.mean(a)), float(np.std(a)) + 1e-6] for k, a in (("y", y), ("u", u), ("v", v))}


def _frames(path: str, work: str) -> list:
    """A few small pictures of the take (or the picture itself)."""
    import numpy as np
    from PIL import Image
    from .export import NO_WINDOW, ffmpeg
    ext = os.path.splitext(path)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".webp"):
        with Image.open(path) as im:
            return [np.asarray(im.convert("RGB").resize((160, 90)))]
    out = []
    probe = subprocess.run([ffmpeg(), "-hide_banner", "-i", path], capture_output=True, text=True, creationflags=NO_WINDOW).stderr
    import re
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", probe)
    dur = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 2.0
    os.makedirs(work, exist_ok=True)
    for k, f in enumerate(SAMPLES):
        png = os.path.join(work, f"s{os.getpid()}_{k}.png")
        subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{dur * f:.2f}", "-i", path, "-frames:v", "1", "-vf", "scale=160:90", png],
                       creationflags=NO_WINDOW)
        if os.path.exists(png):
            with Image.open(png) as im:
                out.append(np.asarray(im.convert("RGB")))
            os.remove(png)
    return out


def shot_stats(d: str, path: str) -> dict | None:
    import numpy as np
    frames = _frames(path, os.path.join(d, "cache", "colormatch"))
    if not frames:
        return None
    return _yuv(np.concatenate([f.reshape(-1, 3) for f in frames]))


def _takes(d: str) -> dict:
    from .library import chosen_take, shot_state
    plan_name = "directed" if os.path.exists(os.path.join(d, "directed.json")) else "production"
    plan = _read(os.path.join(d, f"{plan_name}.json"), {"scenes": []}) or {"scenes": []}
    jobs = (_read(os.path.join(d, "jobs.json"), {"jobs": []}) or {}).get("jobs", [])
    state = shot_state(d)
    out = {}
    for sc in plan.get("scenes", []):
        for sh in sc.get("shots", []):
            t = chosen_take(d, sh["id"], plan_name, jobs, state)
            if t and t.get("output"):
                p = os.path.join(d, t["output"])
                if os.path.isfile(p):
                    out[sh["id"]] = p
    return out


def _correction(stat: dict, ref: dict, strength: float) -> dict:
    """y/u/v: [gain, offset] so that out = val * gain + offset moves this shot's average and spread towards the reference's."""
    fix = {}
    for ch in ("y", "u", "v"):
        m, s = stat[ch]
        rm, rs = ref[ch]
        gain = min(MAX_GAIN, max(MIN_GAIN, rs / s))
        a = 1 + strength * (gain - 1)
        b = strength * (rm - m * gain)
        fix[ch] = [round(a, 4), round(b, 3)]
    return fix


def _distance(stat: dict, ref: dict) -> float:
    """How far a shot is from the reference, as a fraction of the studio range: brightness and colour cast (spread counts less)."""
    return (abs(stat["y"][0] - ref["y"][0]) / 219 + (abs(stat["u"][0] - ref["u"][0]) + abs(stat["v"][0] - ref["v"][0])) / 224
            + 0.5 * abs(stat["y"][1] - ref["y"][1]) / 219)


def reference_of(stats: dict, chosen: str | None) -> dict | None:
    if chosen and chosen in stats:
        return stats[chosen]
    if not stats:
        return None
    return {ch: [statistics.median(s[ch][0] for s in stats.values()), statistics.median(s[ch][1] for s in stats.values())] for ch in ("y", "u", "v")}


def analyze(d: str, strength: float | None = None, reference: str | None = None) -> dict:
    """Look at the take each shot uses and write a correction for the shots that differ from the reference."""
    cur = load(d)
    strength = cur["strength"] if strength is None else min(1.0, max(0.0, float(strength)))
    takes = _takes(d)
    if len(takes) < 1:
        raise SystemExit("Colour matching needs at least one shot with a take or picture to look at.")
    cache = _read(os.path.join(d, "cache", "colormatch.json"), {}) or {}
    stats = {}
    for sid, path in takes.items():
        key = f"{path}|{os.path.getmtime(path)}|{os.path.getsize(path)}"
        hit = cache.get(sid)
        if hit and hit.get("key") == key:
            stats[sid] = hit["stat"]
            continue
        st = shot_stats(d, path)
        if st:
            stats[sid] = st
            cache[sid] = {"key": key, "stat": st}
    os.makedirs(os.path.join(d, "cache"), exist_ok=True)
    _write(os.path.join(d, "cache", "colormatch.json"), cache)
    ref_id = cur["reference"] if reference is None else (reference or None)       # None: keep the one set; "": the typical shot
    ref = reference_of(stats, ref_id)
    if not ref:
        raise SystemExit("None of the takes could be read.")
    shots = {}
    for sid, st in stats.items():
        if sid != ref_id and _distance(st, ref) >= IGNORE_BELOW:
            shots[sid] = _correction(st, ref, strength)
    seen = measure_cast(stats)
    grade = {**{k: cur[k] for k in ("cast", "cast_strength", "denoise", "grain")}, "cast_seen": seen, "cast_fix": cast_fix_of(seen, cur["cast_strength"]),
             "enabled": cur["enabled"], "strength": strength, "reference": ref_id if ref_id in stats else None, "shots": shots, "stats": {k: {c: [round(x, 2) for x in v] for c, v in s.items()} for k, s in stats.items()},
             "analysed": int(time.time())}
    _write(os.path.join(d, GRADE), grade)
    return state(d)


def state(d: str) -> dict:
    g = load(d)
    ref = reference_of({k: v for k, v in g["stats"].items()}, g["reference"])
    rows = []
    for sid, st in g["stats"].items():
        rows.append({"shot": sid, "distance": round(_distance(st, ref), 3) if ref else 0.0, "bright": round(st["y"][0] - ref["y"][0], 1) if ref else 0.0,
                     "adjusted": sid in g["shots"], "is_reference": sid == g["reference"]})
    rows.sort(key=lambda r: -r["distance"])
    from . import picturecare
    project = _read(os.path.join(d, "project.json"), {}) or {}
    return {"enabled": g["enabled"], "strength": g["strength"], "reference": g["reference"], "analysed": g["analysed"], "rows": rows, "adjusted": len(g["shots"]),
            "cast": g["cast"], "cast_strength": g["cast_strength"], "cast_seen": g["cast_seen"], "cast_fix": g["cast_fix"], "denoise": g["denoise"], "grain": g["grain"],
            "picture_care": picturecare.enabled(project)}


def set_options(d: str, spec: dict) -> dict:
    """Turn the correction on or off for the export, change its strength or the reference shot (the corrections are worked out again)."""
    g = _read(os.path.join(d, GRADE), None)
    if "prompts" in spec:                            # ask the picture and video models for natural skin and neutral colour (picturecare.py): a setting of the film
        pj = _read(os.path.join(d, "project.json"), {}) or {}
        pj["picture_care"] = {"on": bool(spec["prompts"])}
        _write(os.path.join(d, "project.json"), pj)
    if not g:
        if not any(k in spec for k in ("enabled", "cast", "cast_strength", "denoise", "grain")):
            return state(d)
        g = {"enabled": False, "strength": 0.7, "reference": None, "shots": {}, "stats": {}, "analysed": None}
    changed = False
    for k in ("enabled", "cast", "denoise", "grain"):
        if k in spec:
            g[k] = bool(spec[k])
            changed = True
    if "cast_strength" in spec:
        g["cast_strength"] = min(1.0, max(0.0, float(spec["cast_strength"])))
        changed = True
    if changed:
        cs = min(1.0, max(0.0, float(g.get("cast_strength", 0.85))))
        g["cast_seen"] = measure_cast(g.get("stats") or {})
        g["cast_fix"] = cast_fix_of(g["cast_seen"], cs)
        _write(os.path.join(d, GRADE), g)
    if "strength" in spec or "reference" in spec:
        analyze(d, strength=spec.get("strength"), reference=spec["reference"] if "reference" in spec else None)
    return state(d)


def clear(d: str) -> dict:
    p = os.path.join(d, GRADE)
    if os.path.exists(p):
        os.remove(p)
    return state(d)


def filter_for(d: str, shot_id: str) -> str:
    """The ffmpeg filter for this shot's correction ('' when there is none, it is off, or the shot is the reference). Only numbers made here go in."""
    g = load(d)
    if not g["enabled"]:
        return ""
    fix = g["shots"].get(shot_id)
    cf = g["cast_fix"] if g["cast"] else None
    out = [DENOISE] if g["denoise"] else []
    if fix or cf:
        parts = []
        for ch, lo, hi in (("y", 16, 235), ("u", 16, 240), ("v", 16, 240)):
            a, b = (float(x) for x in fix[ch]) if fix else (1.0, 0.0)
            if cf and ch in ("u", "v"):
                b += float(cf[ch])                        # the film-wide cast offset, shared by every shot
            parts.append(f"{ch}='clip(val*{a:.4f}+({b:.3f}),{lo},{hi})'")
        out.append("lutyuv=" + ":".join(parts))
    if g["grain"]:
        out.append(GRAIN)
    return ",".join(out)


def signature(d: str, shot_id: str) -> str:
    """Part of the export cache key: changes when this shot's correction does."""
    return filter_for(d, shot_id)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-colormatch")
    ap.add_argument("action", choices=["state", "analyze", "set", "clear"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "state":
            res = state(a.project)
        elif a.action == "analyze":
            res = analyze(a.project, x.get("strength"), x.get("reference"))
        elif a.action == "set":
            res = set_options(a.project, x)
        else:
            res = clear(a.project)
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
