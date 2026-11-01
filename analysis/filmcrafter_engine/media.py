"""Bring Your Own Media: the zero-cost path. Nothing here calls a provider or costs money.

Your own clips and images become takes of shots (exactly like rendered takes, so versions, approval, preview and
export all work). Images move with a camera move (zoom or pan), approved keyframes can become moving stills, shots
get transitions, and a song-only project can get a plain shot plan cut on the bars.

  python -m filmcrafter_engine.media <action> <project> --data '{...}'
  actions: import | fill | stills | motion | transition | plan
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import uuid

IMAGE_EXT = {"png", "jpg", "jpeg", "webp"}
VIDEO_EXT = {"mp4", "mov", "webm", "m4v", "mkv"}
MOTIONS = ["none", "zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"]
from .transitions import TRANSITIONS, clean_seconds   # how a shot enters: cut, dissolve, dips, wipes, slides, whips, zoom through (see transitions.py)
OWN = "own"


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data):
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def media_kind(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    raise SystemExit("Use an image (PNG, JPG, WebP) or a video clip (MP4, MOV, WebM).")


def _default_motion(i: int) -> str:
    return ["zoom_in", "pan_right", "zoom_out", "pan_left"][i % 4]   # gentle variety when many stills are placed


def _add_take(d: str, shot_id: str, rel: str, kind: str, motion: str | None, source: str) -> dict:
    from .library import approve, shot_state
    from .render import Store, _load_plan, _shot
    plan_name, plan = _load_plan(d)
    shot, _ = _shot(plan, shot_id)
    if shot_state(d).get(shot_id, {}).get("locked"):
        raise SystemExit(f"{shot_id} is locked. Unlock it to change its take.")
    now = int(time.time())
    job = {"id": uuid.uuid4().hex[:12], "shot_id": shot_id, "plan": plan_name, "source_shots": shot.get("source_shots", []),
           "shot_start": shot["start"], "shot_end": shot["end"], "provider": OWN, "model": source, "kind": "video",
           "media_kind": kind, "motion": (motion if motion in MOTIONS else "zoom_in") if kind == "image" else None,
           "overrides": {}, "fix_notes": [], "state": "ready", "provider_job_id": None, "attempts": 0,
           "created": now, "updated": now, "output": rel, "error": None, "cost": 0, "cost_unit": "usd"}
    store = Store(d)
    store.jobs.append(job)
    store.save()
    approve(d, shot_id, job["id"])
    return job


def import_media(d: str, shot_id: str, path: str, motion: str | None = None, role: str = "take") -> dict:
    """Copy a file into the project and use it for a shot: as its take (default) or as its keyframe."""
    from .safe import check_id, file_part
    if not os.path.isfile(path):
        raise SystemExit("That file can't be found.")
    kind = media_kind(path)
    from .render import _load_plan, _shot            # the shot must exist before anything is copied
    _shot(_load_plan(d)[1], check_id(shot_id))
    os.makedirs(os.path.join(d, "media"), exist_ok=True)
    ext = path.rsplit(".", 1)[-1].lower()
    rel = f"media/{file_part(shot_id)}_{uuid.uuid4().hex[:6]}.{ext}"
    shutil.copy2(path, os.path.join(d, rel))
    if role == "keyframe":
        if kind != "image":
            raise SystemExit("A keyframe must be an image.")
        from .render import _load_plan
        plan_name, _ = _load_plan(d)
        p = os.path.join(d, "keyframes.json")
        kf = _read(p, {}) or {}
        kf.setdefault(plan_name, {})[shot_id] = f"project:{rel}"
        _write(p, kf)
        return {"shot": shot_id, "keyframe": rel}
    return _add_take(d, shot_id, rel, kind, motion, os.path.basename(path))


def fill(d: str, paths: list[str], start: str | None = None, only_empty: bool = True) -> dict:
    """Place several files on the timeline in order, one per shot, from `start` (or the first shot without a take)."""
    from .library import chosen_take, shot_state
    from .render import _load_plan
    plan_name, plan = _load_plan(d)
    ids = [s["id"] for sc in plan.get("scenes", []) for s in sorted(sc["shots"], key=lambda x: x["start"])]
    jobs = _read(os.path.join(d, "jobs.json"), {"jobs": []})["jobs"]
    state = shot_state(d)
    if start in ids:
        ids = ids[ids.index(start):]
    placed, skipped = [], []
    queue = list(paths)
    for sid in ids:
        if not queue:
            break
        if state.get(sid, {}).get("locked") or (only_empty and chosen_take(d, sid, plan_name, jobs, state)):
            continue
        p = queue.pop(0)
        try:
            j = import_media(d, sid, p, _default_motion(len(placed)))
            placed.append({"shot": sid, "file": os.path.basename(p), "kind": j["media_kind"]})
        except SystemExit as e:
            skipped.append({"file": os.path.basename(p), "reason": str(e)})
    skipped += [{"file": os.path.basename(p), "reason": "No empty shot left for it."} for p in queue]
    return {"placed": placed, "skipped": skipped}


def stills(d: str, shots: list[str] | None = None, motion: str | None = None) -> dict:
    """Free draft: every shot with an approved keyframe but no video take gets its keyframe as a moving still."""
    from .library import chosen_take, shot_state
    from .render import _load_plan
    plan_name, plan = _load_plan(d)
    kfs = (_read(os.path.join(d, "keyframes.json"), {}) or {}).get(plan_name, {})
    jobs = _read(os.path.join(d, "jobs.json"), {"jobs": []})["jobs"]
    state = shot_state(d)
    made = []
    for sc in plan.get("scenes", []):
        for sh in sc["shots"]:
            sid = sh["id"]
            if shots and sid not in shots:
                continue
            kf = kfs.get(sid)
            rel = kf[len("project:"):] if isinstance(kf, str) and kf.startswith("project:") else None
            if not rel or not os.path.exists(os.path.join(d, rel)) or state.get(sid, {}).get("locked"):
                continue
            if not shots and chosen_take(d, sid, plan_name, jobs, state):
                continue
            _add_take(d, sid, rel, "image", motion or _default_motion(len(made)), "keyframe (moving still)")
            made.append(sid)
    return {"made": made}


def set_motion(d: str, job_id: str, motion: str) -> dict:
    from .render import Store
    if motion not in MOTIONS:
        raise SystemExit("Unknown camera move.")
    store = Store(d)
    j = next((x for x in store.jobs if x["id"] == job_id), None)
    if not j or j.get("media_kind") != "image":
        raise SystemExit("Camera moves apply to still images.")
    store.update(j, motion=motion)
    return {"job": job_id, "motion": motion}


def set_transition(d: str, shot_ids: list[str], transition: str, seconds=None) -> dict:
    """How these shots enter from the shot before them, and for how long (None: the transition's own length)."""
    from .library import set_shot
    if transition not in TRANSITIONS:
        raise SystemExit("Unknown transition.")
    secs = clean_seconds(transition, seconds)
    for sid in shot_ids:
        set_shot(d, sid, transition=transition, transition_s=secs)
    return {"shots": shot_ids, "transition": transition, "seconds": secs}


def plan_from_song(d: str, bars: int = 4) -> dict:
    """A plain shot plan with no AI: one scene per song section, a new shot every `bars` bars (on the downbeat)."""
    if os.path.exists(os.path.join(d, "production.json")) or os.path.exists(os.path.join(d, "directed.json")):
        raise SystemExit("This project already has a shot plan.")
    sm = _read(os.path.join(d, "songmap.json"))
    if not sm:
        raise SystemExit("The song hasn't been analysed yet.")
    dur = float(sm["duration"])
    downs = sorted(float(x) for x in sm.get("downbeats") or [])
    if len(downs) < 2:   # no bar grid: fall back to the tempo, or 8-second shots
        step = 240.0 / sm["bpm"] if sm.get("bpm") else 2.0
        downs = [i * step for i in range(int(dur / step) + 1)]
    sections = sm.get("sections") or [{"start": 0.0, "end": dur, "label": "SONG"}]
    scenes = []
    for n, sec in enumerate(sections, 1):
        s0, s1 = float(sec["start"]), float(sec["end"])
        cuts = [s0] + [b for b in downs[::max(1, bars)] if s0 + 1.0 < b < s1 - 1.0] + [s1]
        shots = []
        for k, (a, b) in enumerate(zip(cuts, cuts[1:]), 1):
            shots.append({"id": f"S{n:02d}-{k:02d}", "scene": n, "number": k, "description": "", "framing": "",
                          "camera_moves": [], "performers": [], "start": round(a, 3), "end": round(b, 3),
                          "section": sec.get("group"), "lyrics": [], "source_shots": [f"S{n:02d}-{k:02d}"],
                          "beats": [], "renderer": "auto", "state": "planned", "flags": []})
        label = (sec.get("label") or "SECTION").title()
        scenes.append({"number": n, "heading": f"{label} {n}", "fields": {}, "notes": {}, "characters": [],
                       "sung_lines": [], "start": s0, "end": s1, "shots": shots})
    _write(os.path.join(d, "production.json"), {"schema_version": 1, "meta": {"source": "song only (no AI)"},
                                                  "characters": [], "scenes": scenes})
    return {"scenes": len(scenes), "shots": sum(len(s["shots"]) for s in scenes)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-media")
    ap.add_argument("action", choices=["import", "fill", "stills", "motion", "transition", "plan"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    d = a.project
    try:
        if a.action == "import":
            res = import_media(d, x["shot"], x["path"], x.get("motion"), x.get("role", "take"))
        elif a.action == "fill":
            res = fill(d, x["paths"], x.get("start"), x.get("only_empty", True))
        elif a.action == "stills":
            res = stills(d, x.get("shots"), x.get("motion"))
        elif a.action == "motion":
            res = set_motion(d, x["job"], x["motion"])
        elif a.action == "transition":
            res = set_transition(d, x["shots"], x["transition"], x.get("seconds"))
        else:
            res = plan_from_song(d, int(x.get("bars", 4)))
        print(json.dumps({"event": "result", "data": res}), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except Exception as e:
        print(json.dumps({"event": "error", "message": __import__("filmcrafter_engine.errtext", fromlist=["plain"]).plain(e)}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
