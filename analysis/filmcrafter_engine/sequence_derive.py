"""The sequence a film has before anyone edits it: the shots laid end to end from the shot plan, exactly where `export.build` has always put them.

This is the one place the edit model meets floating seconds: the plan states each shot's start and end in seconds, and the export has always turned them into whole frames with
`round(seconds * 24)`. The same expression is used here so a film that was never edited has the same frame boundaries as before (a test compares them on every shot of the test films).
It is kept apart from the editing modules so the rule "no floating time in the edit maths" can be checked on them.
"""
from __future__ import annotations

import os

from . import edit_time as T
from . import safeio

FPS = T.FPS_24


def plan_of(d: str) -> tuple[str, dict, dict]:
    """(plan name, plan, song map) of a render project, or SystemExit when it has none."""
    name = "directed" if os.path.exists(os.path.join(d, "directed.json")) else "production"
    plan = safeio.read_json(os.path.join(d, f"{name}.json"), None)
    sm = safeio.read_json(os.path.join(d, "songmap.json"), None)
    if not isinstance(plan, dict) or not isinstance(sm, dict) or "duration" not in sm:
        raise SystemExit("This project needs a song map and a shot plan before it can be edited.")
    return name, plan, sm


def shots_of(plan: dict) -> list[tuple[dict, dict]]:
    return sorted(((sh, sc) for sc in plan.get("scenes", []) for sh in sc.get("shots", []) if isinstance(sh, dict) and sh.get("id")), key=lambda x: x[0]["start"])


def derive(d: str) -> dict:
    """The film as the plan lays it out, as a sequence of whole-frame clips and its length."""
    _, plan, sm = plan_of(d)
    fps = FPS
    total_frames = round(sm["duration"] * 24)
    cursor, clips = 0, []
    for sh, _ in shots_of(plan):
        f0, f1 = max(cursor, round(sh["start"] * 24)), min(total_frames, round(sh["end"] * 24))
        if f1 > f0:
            clips.append({"id": f"c{len(clips) + 1}", "shot": sh["id"], "start": T.tick_of_frame(f0, fps), "source_in": 0, "duration": T.tick_of_frame(f1 - f0, fps), "take": None})
        cursor = max(cursor, f1)
    return {"fps": fps.as_list(), "length": T.tick_of_frame(total_frames, fps), "next": len(clips) + 1,
            "tracks": [{"id": "V1", "kind": "video", "locked": False, "hidden": False, "muted": False, "clips": clips}], "markers": [], "ranges": []}
