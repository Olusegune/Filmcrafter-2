"""Insert a custom frame into the timeline: a new, ordinary shot of a length you choose, placed before or after a shot you pick.

The new shot is a real shot, so it has everything the others have: its prompt, a keyframe, the model and quality choices, takes, review and the
Supervisor. What it shows is up to you: a generated shot (describe it; optionally start from your picture), a colour or gradient card, your own
picture (with a slow camera move) or your own clip. A picture, clip or colour is free; a generated shot is priced and confirmed like any other.

The song keeps its clock: the new shot uses time the song already has. It takes the empty stretch next to the shot first, and only what is
still missing is cut from the neighbouring shot (which keeps at least a second). Nothing is moved later, so the film stays in sync.

  python -m filmcrafter_engine.customframe <state|insert|remove> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from . import titlecard as T
from .safe import check_id, file_part

MIN_LEN, MAX_LEN, KEEP = 0.5, 15.0, 1.0
MODES = ("generate", "colour", "picture", "clip")


def emit(**kw) -> None:
    T.emit(**kw)


def _ordered(plan: dict) -> list[tuple[dict, dict]]:
    out = [(sc, s) for sc in plan.get("scenes", []) for s in sc.get("shots", [])]
    return sorted(out, key=lambda x: float(x[1]["start"]))


def state(d: str) -> dict:
    _, plan = T._plan(d)
    shots = [{"id": s["id"], "start": float(s["start"]), "end": float(s["end"]), "intro": bool(s.get("intro")), "custom": bool(s.get("custom"))} for _, s in _ordered(plan)]
    return {"shots": shots, "min": MIN_LEN, "max": MAX_LEN, "keep": KEEP}


def remove(d: str, shot_id: str) -> dict:
    """Take away a frame added here (or an intro shot): the shot goes, the time it cut from a neighbour is given back, and its take and keyframe are
    let go (the files stay until you clean up). Only shots that were added by you can be removed."""
    name, plan = T._plan(d)
    hit = next(((sc, s) for sc in plan.get("scenes", []) for s in sc.get("shots", []) if s["id"] == shot_id), None)
    if not hit or not (hit[1].get("custom") or hit[1].get("intro")):
        raise SystemExit("Only a frame you added can be removed.")
    scene, shot = hit
    gave = shot.get("gave") or {}
    back = None
    nb = next((s for sc in plan["scenes"] for s in sc["shots"] if s["id"] == gave.get("shot")), None)
    if nb and gave.get("by"):
        by = float(gave["by"])
        if gave.get("side") == "start" and abs(float(nb["start"]) - float(shot["end"])) < 0.01:      # it still touches the shot it was cut from
            nb["start"] = round(float(nb["start"]) - by, 3)
            back = nb
        elif gave.get("side") == "end" and abs(float(nb["end"]) - float(shot["start"])) < 0.01:
            nb["end"] = round(float(nb["end"]) + by, 3)
            back = nb
        if back:
            back["duration_seconds"] = round(float(back["end"]) - float(back["start"]), 3)
            back["revised"] = int(time.time())
    scene["shots"] = [s for s in scene["shots"] if s["id"] != shot_id]
    T._write(os.path.join(d, f"{name}.json"), plan)
    for fname, key in (("keyframes.json", name), ("shots.json", None)):
        p = os.path.join(d, fname)
        data = T._read(p, {}) or {}
        box = data.get(key) if key else data
        if isinstance(box, dict) and shot_id in box:
            del box[shot_id]
            T._write(p, data)
    jp = os.path.join(d, "jobs.json")
    jobs = T._read(jp, {"jobs": []}) or {"jobs": []}
    changed = False
    for j in jobs.get("jobs", []):
        if isinstance(j, dict) and j.get("shot_id") == shot_id and j.get("state") != "dismissed":
            j["state"] = "dismissed"
            changed = True
    if changed:
        T._write(jp, jobs)
    return {"removed": shot_id, "gave_back": ({"shot": back["id"], "by": float(gave["by"])} if back else None)}


def _new_id(existing: set[str], neighbour: str) -> str:
    n = 1
    while f"{neighbour}c{n}" in existing:
        n += 1
    return f"{neighbour}c{n}"


def _colour_card(d: str, sid: str, c1: str, c2: str | None) -> str:
    """A 1920x1080 picture (one colour, or a top-to-bottom gradient) in the project; the path inside it."""
    from PIL import Image
    from . import overlays as O
    a = O._hex(str(c1 or "#101820"))
    b = O._hex(str(c2 or c1 or "#101820"))
    col = Image.new("RGB", (1, 2), a)
    col.putpixel((0, 1), b)
    os.makedirs(os.path.join(d, "assets", "refs"), exist_ok=True)
    rel = f"assets/refs/card-{file_part(sid)}.png"
    col.resize((1920, 1080), Image.BILINEAR).save(os.path.join(d, rel))
    return rel


def insert(d: str, spec: dict) -> dict:
    mode = spec.get("mode", "generate")
    if mode not in MODES:
        raise SystemExit("Choose generated, colour, picture or clip.")
    where = spec.get("where", "after")
    if where not in ("before", "after"):
        raise SystemExit("Choose before or after the shot.")
    try:
        need = float(spec.get("length"))
    except (TypeError, ValueError):
        raise SystemExit("Give the frame a length in seconds.")
    if not (MIN_LEN <= need <= MAX_LEN):
        raise SystemExit(f"A frame lasts between {MIN_LEN:g} and {MAX_LEN:g} seconds.")
    prompt = T._text(spec.get("prompt"), T.MAX_PROMPT)
    if mode == "generate" and not prompt:
        raise SystemExit("Describe what the frame should show.")
    file = str(spec.get("file") or spec.get("picture") or "")
    if mode in ("picture", "clip") and not file:
        raise SystemExit("Choose the picture." if mode == "picture" else "Choose the clip.")
    if mode in ("picture", "clip"):                      # refuse a wrong kind of file before anything is changed
        from . import media
        if not os.path.isfile(file):
            raise SystemExit("That file can't be found.")
        if media.media_kind(file) != ("image" if mode == "picture" else "video"):
            raise SystemExit("Choose a picture (PNG, JPG or WebP)." if mode == "picture" else "Choose a video clip (MP4, MOV, WebM).")
    name, plan = T._plan(d)
    order = _ordered(plan)
    if spec.get("shot") is not None and any(s["id"] == spec.get("shot") for _, s in order):
        check_id(spec.get("shot"))                          # an id that could be a path is refused before anything is changed
    pos = next((i for i, (_, s) in enumerate(order) if s["id"] == spec.get("shot")), None)
    if pos is None:
        raise SystemExit("Choose the shot to put the frame next to.")
    scene, anchor = order[pos]
    from .library import shot_state
    dur = float(anchor["end"]) - float(anchor["start"])
    if where == "before":
        free = max(0.0, float(anchor["start"]) - (float(order[pos - 1][1]["end"]) if pos > 0 else 0.0))
    else:
        song = T._song_duration(d)
        nxt = float(order[pos + 1][1]["start"]) if pos + 1 < len(order) else (song or float(anchor["end"]))
        free = max(0.0, nxt - float(anchor["end"]))
    take = min(free, need)
    trim = round(need - take, 3)
    if trim > 0:
        if dur - trim < KEEP:
            raise SystemExit(f"{anchor['id']} is only {dur:.1f} s long, so it cannot give up {trim:.1f} s. Choose a shorter frame or a longer shot.")
        if shot_state(d).get(anchor["id"], {}).get("locked"):
            raise SystemExit(f"{anchor['id']} is locked and would have to be shortened. Unlock it first.")
    if where == "before":
        start, end = float(anchor["start"]) - take, float(anchor["start"]) + trim
        if trim:
            anchor["start"] = round(float(anchor["start"]) + trim, 3)
    else:
        start, end = float(anchor["end"]) - trim, float(anchor["end"]) + take
        if trim:
            anchor["end"] = round(float(anchor["end"]) - trim, 3)
    start, end = round(start, 3), round(end, 3)
    gave = {"shot": anchor["id"], "side": "start" if where == "before" else "end", "by": trim} if trim else None
    if trim:
        anchor["duration_seconds"] = round(float(anchor["end"]) - float(anchor["start"]), 3)
        anchor["revised"] = int(time.time())          # its length changed: a take made for the old length is flagged
    existing = {s["id"] for sc in plan["scenes"] for s in sc["shots"]}
    sid = _new_id(existing, anchor["id"])
    what = {"generate": prompt, "colour": "A plain colour card.", "picture": "Your own picture.", "clip": "Your own clip."}[mode]
    shot = {"id": sid, "scene": scene.get("number", 1), "number": 0, "start": start, "end": end, "duration_seconds": round(end - start, 3),
            "source_shots": [], "beats": [what], "dropped_beats": [], "purpose": "A frame added by you", "performers": [], "emotion": "",
            "performance_intensity": 3, "performance": "", "expression": "", "movement": "", "framing": "Wide", "lens": "", "camera_movement": "",
            "camera_energy": "gentle", "lighting": "", "environment": "", "wardrobe": "", "continuity": "", "sync_event": "",
            "visual_prompt": (prompt.rstrip(". ") + ". No text, no letters, no logos.") if mode == "generate" else "",
            "renderer": "auto", "state": "planned", "revised": int(time.time()), "custom": True}
    if gave:
        shot["gave"] = gave
    scene["shots"].append(shot)
    scene["shots"].sort(key=lambda s: float(s["start"]))
    scene["start"] = min(float(scene.get("start", start)), start)
    scene["end"] = max(float(scene.get("end", end)), end)
    # files first, so a refusal (a bad picture) leaves the plan untouched
    keyframe = rel = None
    if mode == "generate" and file:
        rel = T._picture(d, file)
        from PIL import Image
        png = f"assets/refs/frame-{file_part(sid)}.png"
        os.makedirs(os.path.join(d, "assets", "refs"), exist_ok=True)
        with Image.open(os.path.join(d, rel)) as im:
            im.convert("RGB").save(os.path.join(d, png))
        keyframe = "project:" + png
    if mode == "colour":
        rel = _colour_card(d, sid, spec.get("color"), spec.get("color2"))
    T._write(os.path.join(d, f"{name}.json"), plan)
    if keyframe:
        kp = os.path.join(d, "keyframes.json")
        kf = T._read(kp, {}) or {}
        kf.setdefault(name, {})[sid] = keyframe
        T._write(kp, kf)
    if mode in ("picture", "clip", "colour"):
        from . import media
        src = os.path.join(d, rel) if rel else file
        motion = "none" if mode == "colour" else (spec.get("motion") or "zoom_in")
        media.import_media(d, sid, src, motion)
    return {"shot": sid, "plan": name, "start": start, "end": end, "trimmed": ({"shot": anchor["id"], "by": trim} if trim else None), "mode": mode,
            "keyframe": bool(keyframe)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-customframe")
    ap.add_argument("action", choices=["state", "insert", "remove"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        emit(event="result", data=state(a.project) if a.action == "state" else insert(a.project, x) if a.action == "insert" else remove(a.project, str(x.get("shot") or "")))
        return 0
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=__import__("filmcrafter_engine.errtext", fromlist=["plain"]).plain(e))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
