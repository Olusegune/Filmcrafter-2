"""The door to editing the film's cut: read the sequence, make one named edit, undo and redo. Free and local; it only writes the film's edit record (`<film>/edit/edit.json`), never a take,
a shot contract or the screenplay.

  sequence_get   the cut as it stands (stored, or derived from the shot plan when the film has never been edited: nothing is written by looking), with what is unplaced or orphaned
  edit           one operation: split, trim, delete, move, roll, close_gap, place, marker_set, marker_remove, range_set, range_remove, track_set (edit_ops.py)
  place_missing  put every shot that has no clip on the end of the film, for the length its plan gives it
  snap           the nearest cut, marker or the playhead to a time, within a few frames
  undo | redo    the last change to the cut, a grade or a saved look (one history for all three)

A person gives times in seconds; they are rounded once to the nearest whole frame here and are whole ticks from then on (edit_time.py).

  python -m filmcrafter_engine.editing <action> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import sys

from . import edit_ops as O
from . import edit_time as T
from . import grading as G
from . import sequence as Q
from . import sequence_derive as D

ACTIONS = ("sequence_get", "edit", "place_missing", "snap", "undo", "redo")
SNAP_FRAMES = 6


def current(d: str) -> tuple[dict, bool]:
    """(the sequence, whether it is stored). A film never edited reads as the plan lays it out; nothing is written."""
    stored = Q.clean(G.load(d)["_extra"].get("sequence"))
    return (stored, True) if stored else (D.derive(d), False)


def _view(seq: dict) -> dict:
    fps = Q.fps_of(seq)
    ft = fps.frame_ticks
    one = lambda c: {**c, "start_s": T.ticks_to_seconds(c["start"]), "duration_s": T.ticks_to_seconds(c["duration"]), "source_in_s": T.ticks_to_seconds(c["source_in"]),
                     "start_frame": c["start"] // ft, "frames": c["duration"] // ft}
    return {"fps": fps.as_list(), "frame_ticks": ft, "ticks_per_second": T.TICKS_PER_SECOND, "length": seq["length"], "length_s": T.ticks_to_seconds(seq["length"]),
            "tracks": [{**t, "clips": [one(c) for c in t["clips"]]} for t in seq["tracks"]],
            "markers": [{**m, "at_s": T.ticks_to_seconds(m["at"])} for m in seq["markers"]],
            "ranges": [{**r, "start_s": T.ticks_to_seconds(r["start"]), "end_s": T.ticks_to_seconds(r["end"])} for r in seq["ranges"]]}


def get(d: str) -> dict:
    notes: list[str] = []
    G.load(d, notes)                                               # a damaged record is put back from its backup here, and the person is told
    seq, stored = current(d)
    _, plan, _ = D.plan_of(d)
    shots = [sh["id"] for sh, _ in D.shots_of(plan)]
    st = G.state(d)
    return {"stored": stored, "sequence": _view(seq), "notes": notes, **Q.status(seq, shots), "can_undo": st["can_undo"], "can_redo": st["can_redo"], "history": st["history"]}


def _t(seq: dict, v, name: str) -> int:
    try:
        return T.seconds_to_ticks(v, Q.fps_of(seq))
    except (ValueError, TypeError, ArithmeticError):
        raise SystemExit(f"The {name} is not a time.")


def _params(seq: dict, op: str, x: dict) -> dict:
    """The person's words for an operation (seconds, clip names) as the operation's own (ticks, names). Anything not asked for is not passed on."""
    p: dict = {}
    for k in ("clip", "marker", "range", "track", "edge", "shot", "name"):
        if k in x:
            if not isinstance(x[k], str) or len(x[k]) > 80:
                raise SystemExit(f"The {k} is not valid.")
            p[k] = x[k]
    for k in ("at", "to", "start", "end"):
        if k in x:
            p[k] = _t(seq, x[k], k)
    if "duration" in x:
        p["duration"] = _t(seq, x["duration"], "length")
    for k in ("ripple", "locked", "hidden", "muted"):
        if k in x:
            if not isinstance(x[k], bool):
                raise SystemExit(f"{k} is yes or no.")
            p[k] = x[k]
    return p


def edit(d: str, op: str, x: dict) -> dict:
    if op not in O.OPS:
        raise SystemExit("Unknown edit.")
    seq, _ = current(d)
    p = _params(seq, op, x)
    try:
        new = O.run(seq, op, p)
    except KeyError as e:
        raise SystemExit(f"This edit needs {e.args[0]}.")
    label = {"split": "cut a clip", "trim": "trimmed a clip", "delete": "deleted a clip", "move": "moved a clip", "roll": "rolled a cut", "close_gap": "closed a gap", "place": "placed a shot",
             "marker_set": "set a marker", "marker_remove": "removed a marker", "range_set": "set a range", "range_remove": "removed a range", "track_set": "changed a track"}[op]

    def change(cur):
        cur["_extra"]["sequence"] = new
    G._save(d, change, label)
    return get(d)


def place_missing(d: str) -> dict:
    seq, _ = current(d)
    _, plan, _ = D.plan_of(d)
    out = seq
    n = 0
    for sh, _ in D.shots_of(plan):
        if any(c["shot"] == sh["id"] for t in out["tracks"] for c in t["clips"]):
            continue
        frames = max(1, round((sh["end"] - sh["start"]) * 24))       # the plan's own length for the shot, in whole frames, as the export has always taken it
        out = O.place(out, sh["id"], T.tick_of_frame(frames, Q.fps_of(out)))
        n += 1
    if not n:
        raise SystemExit("Every shot already has a clip.")

    def change(cur):
        cur["_extra"]["sequence"] = out
    G._save(d, change, f"placed {n} shot{'s' if n != 1 else ''}")
    return get(d)


def snap(d: str, at, extra: list | None = None, frames: int = SNAP_FRAMES) -> dict:
    seq, _ = current(d)
    fps = Q.fps_of(seq)
    pts = [0, seq["length"]] + [m["at"] for m in seq["markers"]]
    for t in seq["tracks"]:
        for c in t["clips"]:
            pts += [c["start"], c["start"] + c["duration"]]
    for v in (extra if isinstance(extra, list) else [])[:200]:
        try:
            pts.append(T.seconds_to_ticks(v, fps))
        except (ValueError, TypeError, ArithmeticError):
            pass
    want = _t(seq, at, "time")
    got = O.snap_to(pts, want, max(1, min(int(frames), 60)) * fps.frame_ticks)
    return {"at": T.ticks_to_seconds(got), "tick": got, "snapped": got != want}


def hand_off_note(d: str) -> str | None:
    """A line for the hand-off files (EDL, OTIO, XML, Premiere, Resolve): they are made from the shot plan and cannot show the cut yet, and they say so rather than look as if they could."""
    try:
        return ("The film's cut has been edited (trims, cuts or moves). These files are made from the shot plan and do not include those edits yet; the finished film does."
                if current(d)[1] else None)
    except SystemExit:
        return None


def run(d: str, action: str, x: dict) -> dict:
    if action == "sequence_get":
        return get(d)
    if action == "edit":
        return edit(d, str(x.get("op", "")), x)
    if action == "place_missing":
        return place_missing(d)
    if action == "snap":
        return snap(d, x.get("at"), x.get("points"), x.get("frames", SNAP_FRAMES) if isinstance(x.get("frames", SNAP_FRAMES), int) else SNAP_FRAMES)
    if action == "undo":
        G.undo(d)
        return get(d)
    if action == "redo":
        G.redo(d)
        return get(d)
    raise SystemExit("Unknown action.")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-editing")
    ap.add_argument("action", choices=["sequence_get", "edit", "place_missing", "snap", "undo", "redo"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    try:
        x = json.loads(a.data)
        print(json.dumps({"event": "result", "data": run(a.project, a.action, x if isinstance(x, dict) else {})}, ensure_ascii=False), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
    except Exception as e:                       # noqa: BLE001
        print(json.dumps({"event": "error", "message": __import__("filmcrafter_engine.errtext", fromlist=["plain"]).plain(e)}), flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
