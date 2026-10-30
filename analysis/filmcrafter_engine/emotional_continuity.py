"""Emotional continuity: where each person's feeling goes from scene to scene, and the places where it jumps, stalls or never rests.

It reads the emotional arcs already written in the Acting screen (one point per scene: an emotion and an intensity from 1 to 10) and looks only at the arcs, nothing else. It does not say a
performance is right or wrong; it points at places a director may want to look at, in plain words, and each one can be dismissed (kept in performance/emotion.json, so it stays dismissed).

  abrupt   the feeling changes by 5 or more steps between two scenes next to each other
  flat     three or more scenes in a row with the same feeling at the same strength
  nonstop  three or more scenes in a row at 8 or higher: nobody can stay at full strength; there is no room to build
  unrested a high point (8 or more) followed straight away by a quiet one (3 or less) with no step between

Free, local, deterministic.
"""
from __future__ import annotations

import os

from . import safeio

FILE = "emotion.json"


def _path(d: str) -> str:
    from . import character_performance as CP
    return os.path.join(CP.root(d), FILE)


def _dismissed(d: str) -> list[str]:
    try:
        s = safeio.read_json(_path(d), {})
    except SystemExit:
        s = {}
    raw = s.get("dismissed") if isinstance(s, dict) else None
    return [str(x)[:160] for x in raw if isinstance(x, str)][:500] if isinstance(raw, list) else []


def flags_for(person: str, track: list[dict]) -> list[dict]:
    """The places in one person's track worth a look. Each has a stable id (person, kind, scenes) so a dismissal survives edits elsewhere."""
    out = []

    def add(kind: str, scenes: list[str], message: str):
        out.append({"id": f"{person}|{kind}|{'>'.join(scenes)}", "kind": kind, "scenes": scenes, "message": message})
    for a, b in zip(track, track[1:]):
        step = abs(b["intensity"] - a["intensity"])
        if step >= 5 and a["emotion"].lower() != b["emotion"].lower():
            add("abrupt", [a["section"], b["section"]], f"{person} goes from {a['emotion']} ({a['intensity']}/10) to {b['emotion']} ({b['intensity']}/10) between {a['section']} and {b['section']}. "
                "If nothing in the story causes that change, it may feel sudden.")
        if a["intensity"] >= 8 and b["intensity"] <= 3:
            add("unrested", [a["section"], b["section"]], f"{person} drops from a high point ({a['intensity']}/10) to almost nothing ({b['intensity']}/10) with no step between. A quieter middle may read better.")
    for i in range(len(track) - 2):
        w = track[i:i + 3]
        names = [x["section"] for x in w]
        if len({(x["emotion"].lower(), x["intensity"]) for x in w}) == 1:
            add("flat", names, f"{person} feels the same ({w[0]['emotion']}, {w[0]['intensity']}/10) for {', '.join(names)}. A small change may keep it alive.")
        if all(x["intensity"] >= 8 for x in w):
            add("nonstop", names, f"{person} is at 8 or more for {', '.join(names)}. Full strength for long wears out; leaving room lets the peak land.")
    seen, uniq = set(), []
    for f in out:
        if f["id"] not in seen:
            seen.add(f["id"])
            uniq.append(f)
    return uniq


def get(d: str) -> dict:
    from . import acting
    try:
        arcs = acting.arc_get(d)
    except SystemExit:
        return {"people": [], "sections": [], "dismissed": _dismissed(d)}
    gone = set(_dismissed(d))
    people = []
    for name, a in arcs["arcs"].items():
        track = a["points"]
        fl = flags_for(name, track)
        people.append({"name": name, "track": track, "source": a.get("source"), "flags": [f for f in fl if f["id"] not in gone],
                       "dismissed": sum(1 for f in fl if f["id"] in gone)})
    return {"people": people, "sections": arcs["sections"], "dismissed": sorted(gone)}


def dismiss(d: str, flag_id: str, undo: bool = False) -> dict:
    flag_id = str(flag_id or "")[:160]
    if flag_id.count("|") != 2:
        raise SystemExit("That is not a flag of the emotional arc.")

    def change(data):
        data = data if isinstance(data, dict) else {}
        cur = [x for x in (data.get("dismissed") if isinstance(data.get("dismissed"), list) else []) if isinstance(x, str)]
        if undo:
            cur = [x for x in cur if x != flag_id]
        elif flag_id not in cur:
            cur.append(flag_id)
        data["dismissed"], data["schema"] = cur[-500:], 1
        return data
    from . import character_performance as CP
    os.makedirs(CP.root(d), exist_ok=True)
    safeio.update_json(_path(d), change, {})
    return get(d)
