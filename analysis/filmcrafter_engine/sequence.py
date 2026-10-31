"""The sequence: what is on the film's timeline, as integer ticks (see edit_time.py), kept in the film's edit record (`<film>/edit/edit.json`, key `sequence`).

A film that was never edited has NO stored sequence: opening it writes nothing, and the sequence is derived from the shot plan exactly as `export.build` has always laid it out
(sequence_derive.py). The first edit CONFORMS it: the derived sequence is written once, with the change, and from then on it is the film's edit. A shot added to the plan afterwards is
UNPLACED until you place it, and a clip whose shot was taken out of the plan is an ORPHAN that the export leaves out and says so; nothing is added, moved or dropped silently, and the screenplay,
the shot contracts and the takes are never written.

  {"fps": [24, 1], "length": ticks, "next": n,
   "tracks": [{"id": "V1", "kind": "video", "locked": false, "hidden": false, "muted": false,
               "clips": [{"id": "c1", "shot": "S01-01", "start": ticks, "source_in": ticks, "duration": ticks, "take": null}]}],
   "markers": [{"id": "m1", "at": ticks, "name": "..."}], "ranges": [{"id": "r1", "start": ticks, "end": ticks, "name": "..."}]}

`start` is on the film's timeline; `source_in` is in the clip's own take (so a trim or a split never moves what belongs to the take); times are whole ticks and whole frames.
"""
from __future__ import annotations

import copy

from . import edit_time as T

MAX_CLIPS, MAX_MARKERS, MAX_NAME = 2000, 500, 80
TRACK_KINDS = ("video",)


def fps_of(seq: dict) -> T.FrameRate:
    return T.FrameRate.of(seq.get("fps"))


def _int(v, default: int = 0) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) else default


def clean(raw) -> dict | None:
    """A stored sequence made safe: only the known parts, whole numbers, in order. None when there is nothing usable (the film then reads as never edited)."""
    if not isinstance(raw, dict) or not isinstance(raw.get("tracks"), list):
        return None
    fps = T.FrameRate.of(raw.get("fps"))
    ft = fps.frame_ticks
    tracks = []
    for t in raw["tracks"][:8]:
        if not isinstance(t, dict) or t.get("kind") not in TRACK_KINDS or not isinstance(t.get("id"), str):
            continue
        clips = []
        for c in (t.get("clips") if isinstance(t.get("clips"), list) else [])[:MAX_CLIPS]:
            if not isinstance(c, dict) or not isinstance(c.get("id"), str) or not isinstance(c.get("shot"), str):
                continue
            st, si, du = _int(c.get("start"), -1), _int(c.get("source_in"), -1), _int(c.get("duration"), 0)
            if st < 0 or si < 0 or du <= 0 or st % ft or si % ft or du % ft:
                continue
            clips.append({"id": c["id"][:20], "shot": c["shot"][:40], "start": st, "source_in": si, "duration": du, "take": c.get("take") if isinstance(c.get("take"), str) else None})
        clips.sort(key=lambda x: x["start"])
        tracks.append({"id": t["id"][:10], "kind": "video", "locked": bool(t.get("locked")), "hidden": bool(t.get("hidden")), "muted": bool(t.get("muted")), "clips": clips})
    if not tracks:
        return None
    marks = [{"id": str(m["id"])[:20], "at": _int(m.get("at"), 0), "name": " ".join(str(m.get("name", "")).split())[:MAX_NAME]}
             for m in (raw.get("markers") if isinstance(raw.get("markers"), list) else [])[:MAX_MARKERS] if isinstance(m, dict) and isinstance(m.get("id"), str) and _int(m.get("at"), -1) >= 0]
    ranges = [{"id": str(r["id"])[:20], "start": _int(r.get("start"), -1), "end": _int(r.get("end"), -1), "name": " ".join(str(r.get("name", "")).split())[:MAX_NAME]}
              for r in (raw.get("ranges") if isinstance(raw.get("ranges"), list) else [])[:MAX_MARKERS]
              if isinstance(r, dict) and isinstance(r.get("id"), str) and 0 <= _int(r.get("start"), -1) < _int(r.get("end"), -1)]
    length = max(_int(raw.get("length"), 0), max((c["start"] + c["duration"] for t in tracks for c in t["clips"]), default=0))
    return {"fps": fps.as_list(), "length": length - length % ft, "next": max(_int(raw.get("next"), 1), 1), "tracks": tracks, "markers": marks, "ranges": ranges}


def validate(seq: dict) -> None:
    """The rules every sequence keeps. Raises SystemExit with a plain reason; an operation that would break one changes nothing."""
    ft = fps_of(seq).frame_ticks
    seen = set()
    for t in seq["tracks"]:
        end = 0
        for c in t["clips"]:
            if c["id"] in seen:
                raise SystemExit("Two clips have the same name.")
            seen.add(c["id"])
            if c["start"] < 0 or c["source_in"] < 0 or c["duration"] <= 0:
                raise SystemExit("A clip cannot start before the film, start before its own beginning, or be empty.")
            if c["start"] % ft or c["source_in"] % ft or c["duration"] % ft:
                raise SystemExit("A clip has to start and end on a whole frame.")
            if c["start"] < end:
                raise SystemExit("Two clips would overlap.")
            end = c["start"] + c["duration"]
    if len(seen) > MAX_CLIPS:
        raise SystemExit("There are too many clips.")


def normalise(seq: dict) -> dict:
    """Sorted, with a length that is at least the end of the last clip."""
    for t in seq["tracks"]:
        t["clips"].sort(key=lambda c: c["start"])
    ends = [c["start"] + c["duration"] for t in seq["tracks"] for c in t["clips"]]
    seq["length"] = max(seq.get("length", 0), max(ends, default=0))
    return seq


def copy_of(seq: dict) -> dict:
    return copy.deepcopy(seq)


def new_id(seq: dict, prefix: str = "c") -> str:
    n = max(_int(seq.get("next"), 1), 1)
    seq["next"] = n + 1
    return f"{prefix}{n}"


def video(seq: dict, track: str = "V1") -> dict:
    t = next((x for x in seq["tracks"] if x["id"] == track), None)
    if not t:
        raise SystemExit("That track is not there.")
    return t


def find(seq: dict, clip_id: str) -> tuple[dict, dict]:
    for t in seq["tracks"]:
        for c in t["clips"]:
            if c["id"] == clip_id:
                return t, c
    raise SystemExit("That clip is not in the film.")


def end_of(c: dict) -> int:
    return c["start"] + c["duration"]


def status(seq: dict, plan_shots: list[str]) -> dict:
    """How the stored sequence and the shot plan agree: shots with no clip (unplaced) and clips whose shot has gone (orphans)."""
    placed = {c["shot"] for t in seq["tracks"] for c in t["clips"]}
    plan = set(plan_shots)
    return {"unplaced": [s for s in plan_shots if s not in placed], "orphans": [c["id"] for t in seq["tracks"] for c in t["clips"] if c["shot"] not in plan]}
