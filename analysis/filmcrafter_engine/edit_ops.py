"""The editing operations: pure functions from a sequence to a new sequence, in whole ticks (see edit_time.py).

Each one works on a COPY, checks the whole result against the sequence's rules (`sequence.validate`: in order, no overlaps, positive lengths, whole frames) and only then hands it back; an
operation that cannot be done raises SystemExit with a plain reason and changes nothing. Nothing here touches a take, a shot contract or a file: it only describes the cut.

  split           cut a clip in two at a time
  trim            move a clip's start or end (regular: the film does not move; ripple: what follows moves with it)
  delete          take a clip out (ripple: close the hole)
  move            put a clip somewhere else (ripple: insert it between clips and make room)
  roll            move the cut between two touching clips
  close_gap       bring a clip, and what follows, back to the clip before it
  place           put a shot that has no clip on the end of the film
  marker_*, range_*, track_set   markers, named ranges, and a track's lock, visibility and mute

A locked track refuses every change except unlocking it. Times in and out are ticks that fall on a frame (the door snaps what a person gives it); there is no floating-point time in this file.
"""
from __future__ import annotations

from . import sequence as Q

OPS = ("split", "trim", "delete", "move", "roll", "close_gap", "place", "marker_set", "marker_remove", "range_set", "range_remove", "track_set")


def _track_clip(seq: dict, clip_id: str) -> tuple[dict, dict]:
    t, c = Q.find(seq, clip_id)
    if t["locked"]:
        raise SystemExit(f"The track {t['id']} is locked. Unlock it to edit.")
    return t, c


def _frame_ok(seq: dict, *ticks: int) -> None:
    ft = Q.fps_of(seq).frame_ticks
    for x in ticks:
        if not isinstance(x, int) or isinstance(x, bool) or x < 0 or x % ft:
            raise SystemExit("A time has to be a whole frame, inside the film.")


def _finish(seq: dict) -> dict:
    Q.normalise(seq)
    Q.validate(seq)
    return seq


def _later(track: dict, clip: dict) -> list[dict]:
    return [c for c in track["clips"] if c["start"] > clip["start"]]


def _shift(clips: list[dict], by: int) -> None:
    for c in clips:
        c["start"] += by


def split(seq: dict, at: int, clip: str | None = None, track: str = "V1") -> dict:
    out = Q.copy_of(seq)
    _frame_ok(out, at)
    t = Q.video(out, track)
    if t["locked"]:
        raise SystemExit(f"The track {t['id']} is locked. Unlock it to edit.")
    hit = next((c for c in t["clips"] if (clip is None or c["id"] == clip) and c["start"] < at < Q.end_of(c)), None)
    if hit is None:
        raise SystemExit("There is no clip to cut there (a cut has to fall inside a clip, not on its edge).")
    first = hit["duration"]
    hit["duration"] = at - hit["start"]
    second = {"id": Q.new_id(out), "shot": hit["shot"], "start": at, "source_in": hit["source_in"] + hit["duration"], "duration": first - hit["duration"], "take": hit.get("take")}
    t["clips"].append(second)
    return _finish(out)


def trim(seq: dict, clip: str, edge: str, to: int, ripple: bool = False) -> dict:
    if edge not in ("in", "out"):
        raise SystemExit("Trim the start (in) or the end (out) of a clip.")
    out = Q.copy_of(seq)
    t, c = _track_clip(out, clip)
    _frame_ok(out, to)
    ordered = sorted(t["clips"], key=lambda x: x["start"])
    i = ordered.index(next(x for x in ordered if x["id"] == c["id"]))
    prev_end = Q.end_of(ordered[i - 1]) if i else 0
    nxt = ordered[i + 1] if i + 1 < len(ordered) else None
    later = _later(t, c)
    if edge == "in":
        delta = to - c["start"]
        if ripple:
            # the clip keeps its place; its first frames are given up (or taken back from the take), and what follows moves by the same amount
            if delta < 0 and c["source_in"] < -delta:
                raise SystemExit("There is no more of this clip before its start to bring back.")
            if c["duration"] - delta <= 0:
                raise SystemExit("A clip cannot be trimmed to nothing. Delete it instead.")
            c["source_in"] += delta
            c["duration"] -= delta
            _shift(later, -delta)
            out["length"] += -delta
        else:
            if to < prev_end:
                raise SystemExit("The start cannot go back past the clip before it.")
            if delta < 0 and c["source_in"] < -delta:
                raise SystemExit("There is no more of this clip before its start to bring back.")
            if c["duration"] - delta <= 0:
                raise SystemExit("A clip cannot be trimmed to nothing. Delete it instead.")
            c["start"] = to
            c["source_in"] += delta
            c["duration"] -= delta
    else:
        new = to - c["start"]
        if new <= 0:
            raise SystemExit("A clip cannot be trimmed to nothing. Delete it instead.")
        if ripple:
            delta = new - c["duration"]
            c["duration"] = new
            _shift(later, delta)
            out["length"] += delta
        else:
            if nxt is not None and to > nxt["start"]:
                raise SystemExit("The end cannot go past the clip after it.")
            c["duration"] = new
    return _finish(out)


def delete(seq: dict, clip: str, ripple: bool = False) -> dict:
    out = Q.copy_of(seq)
    t, c = _track_clip(out, clip)
    later = _later(t, c)
    t["clips"] = [x for x in t["clips"] if x["id"] != c["id"]]
    if ripple:
        _shift(later, -c["duration"])
        out["length"] = max(0, out["length"] - c["duration"])
    return _finish(out)


def move(seq: dict, clip: str, to: int, ripple: bool = False) -> dict:
    out = Q.copy_of(seq)
    t, c = _track_clip(out, clip)
    _frame_ok(out, to)
    rest = [x for x in t["clips"] if x["id"] != c["id"]]
    if not ripple:
        c["start"] = to
        if any(to < Q.end_of(x) and x["start"] < to + c["duration"] for x in rest):
            raise SystemExit("There is no room for the clip there: it would overlap another. Move it into a gap, or use a ripple move to make room.")
        return _finish(out)
    # a ripple move lifts the clip out (closing the hole), then puts it in front of the first clip that starts after the middle of where it was dropped
    rest.sort(key=lambda x: x["start"])
    after = [x for x in rest if x["start"] > c["start"]]
    _shift(after, -c["duration"])
    drop = to + c["duration"] // 2
    at = next((x["start"] for x in rest if x["start"] + x["duration"] // 2 >= drop), None)
    if at is None:
        at = max((Q.end_of(x) for x in rest), default=0)
    for x in rest:
        if x["start"] >= at:
            x["start"] += c["duration"]
    c["start"] = at
    t["clips"] = rest + [c]
    return _finish(out)


def roll(seq: dict, clip: str, to: int) -> dict:
    """Move the cut at the END of `clip` to `to`, shortening the clip after it as much as this one grows (or the other way round)."""
    out = Q.copy_of(seq)
    t, left = _track_clip(out, clip)
    _frame_ok(out, to)
    right = next((x for x in t["clips"] if x["start"] == Q.end_of(left)), None)
    if right is None:
        raise SystemExit("These two clips are not touching, so there is no cut to roll.")
    delta = to - Q.end_of(left)
    if delta < 0 and right["source_in"] < -delta:
        raise SystemExit("There is no more of the clip after the cut to bring back.")
    if left["duration"] + delta <= 0 or right["duration"] - delta <= 0:
        raise SystemExit("A roll cannot make either clip empty.")
    left["duration"] += delta
    right["start"] += delta
    right["source_in"] += delta
    right["duration"] -= delta
    return _finish(out)


def close_gap(seq: dict, clip: str) -> dict:
    out = Q.copy_of(seq)
    t, c = _track_clip(out, clip)
    before = [x for x in t["clips"] if Q.end_of(x) <= c["start"]]
    prev_end = max((Q.end_of(x) for x in before), default=0)
    gap = c["start"] - prev_end
    if gap <= 0:
        raise SystemExit("There is no gap before this clip.")
    _shift([c] + _later(t, c), -gap)
    out["length"] = max(0, out["length"] - gap)
    return _finish(out)


def place(seq: dict, shot: str, duration: int, track: str = "V1") -> dict:
    """A shot of the plan that has no clip, put on the end of the film for the length its contract gives it."""
    out = Q.copy_of(seq)
    t = Q.video(out, track)
    if t["locked"]:
        raise SystemExit(f"The track {t['id']} is locked. Unlock it to edit.")
    _frame_ok(out, duration)
    if duration <= 0:
        raise SystemExit("A clip cannot be empty.")
    if any(c["shot"] == shot for c in t["clips"]):
        raise SystemExit("That shot is already in the film.")
    start = max((Q.end_of(c) for c in t["clips"]), default=0)
    t["clips"].append({"id": Q.new_id(out), "shot": shot, "start": start, "source_in": 0, "duration": duration, "take": None})
    return _finish(out)


def marker_set(seq: dict, at: int, name: str = "", marker: str | None = None) -> dict:
    out = Q.copy_of(seq)
    _frame_ok(out, at)
    name = " ".join(str(name or "").split())[:Q.MAX_NAME]
    if marker:
        m = next((x for x in out["markers"] if x["id"] == marker), None)
        if m is None:
            raise SystemExit("That marker is not there.")
        m["at"], m["name"] = at, name
    else:
        if len(out["markers"]) >= Q.MAX_MARKERS:
            raise SystemExit("There are too many markers.")
        out["markers"].append({"id": Q.new_id(out, "m"), "at": at, "name": name})
    out["markers"].sort(key=lambda x: x["at"])
    return _finish(out)


def marker_remove(seq: dict, marker: str) -> dict:
    out = Q.copy_of(seq)
    if not any(x["id"] == marker for x in out["markers"]):
        raise SystemExit("That marker is not there.")
    out["markers"] = [x for x in out["markers"] if x["id"] != marker]
    return _finish(out)


def range_set(seq: dict, start: int, end: int, name: str = "", range_id: str | None = None) -> dict:
    out = Q.copy_of(seq)
    _frame_ok(out, start, end)
    if end <= start:
        raise SystemExit("A range has to end after it starts.")
    name = " ".join(str(name or "").split())[:Q.MAX_NAME]
    if range_id:
        r = next((x for x in out["ranges"] if x["id"] == range_id), None)
        if r is None:
            raise SystemExit("That range is not there.")
        r.update({"start": start, "end": end, "name": name})
    else:
        if len(out["ranges"]) >= Q.MAX_MARKERS:
            raise SystemExit("There are too many ranges.")
        out["ranges"].append({"id": Q.new_id(out, "r"), "start": start, "end": end, "name": name})
    out["ranges"].sort(key=lambda x: x["start"])
    return _finish(out)


def range_remove(seq: dict, range_id: str) -> dict:
    out = Q.copy_of(seq)
    if not any(x["id"] == range_id for x in out["ranges"]):
        raise SystemExit("That range is not there.")
    out["ranges"] = [x for x in out["ranges"] if x["id"] != range_id]
    return _finish(out)


def track_set(seq: dict, track: str, **flags) -> dict:
    out = Q.copy_of(seq)
    t = Q.video(out, track)
    got = False
    for k in ("locked", "hidden", "muted"):
        if k in flags and isinstance(flags[k], bool):
            t[k] = flags[k]
            got = True
    if not got:
        raise SystemExit("Say whether to lock, hide or mute the track.")
    return _finish(out)


def snap_to(points: list[int], at: int, tolerance: int) -> int:
    """The nearest of `points` within `tolerance` ticks of `at`, else `at` itself. A tie goes to the earlier point."""
    best = None
    for p in sorted(points):
        gap = abs(p - at)
        if gap <= tolerance and (best is None or gap < abs(best - at)):
            best = p
    return at if best is None else best


def run(seq: dict, op: str, p: dict) -> dict:
    """One named operation with its parameters (all ticks and ids), as the door calls it."""
    if op == "split":
        return split(seq, p["at"], p.get("clip"), p.get("track", "V1"))
    if op == "trim":
        return trim(seq, p["clip"], p["edge"], p["to"], bool(p.get("ripple")))
    if op == "delete":
        return delete(seq, p["clip"], bool(p.get("ripple")))
    if op == "move":
        return move(seq, p["clip"], p["to"], bool(p.get("ripple")))
    if op == "roll":
        return roll(seq, p["clip"], p["to"])
    if op == "close_gap":
        return close_gap(seq, p["clip"])
    if op == "place":
        return place(seq, p["shot"], p["duration"], p.get("track", "V1"))
    if op == "marker_set":
        return marker_set(seq, p["at"], p.get("name", ""), p.get("marker"))
    if op == "marker_remove":
        return marker_remove(seq, p["marker"])
    if op == "range_set":
        return range_set(seq, p["start"], p["end"], p.get("name", ""), p.get("range"))
    if op == "range_remove":
        return range_remove(seq, p["range"])
    if op == "track_set":
        return track_set(seq, p["track"], **{k: p[k] for k in ("locked", "hidden", "muted") if k in p})
    raise SystemExit("Unknown edit.")
