"""Dance-ready: what makes a shot work as a dance shot, checked for free on this computer, and the beat structure a dance shot's prompt is given.

A video model dances well when it is shown the whole body, given a shot long enough for a move to read, and told where the beat is. This module
  * writes one short line of beat structure into a dance shot's prompt (beats, bars, whether the shot starts on a downbeat), and
  * checks every dance shot against those three things and says what to change.

  python -m filmcrafter_engine.dance check <project>
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

MIN_BPM, MAX_BPM = 30.0, 300.0
MIN_S = 1.5            # a move needs this long to read
MAX_S = 10.0           # models rarely hold one move longer
OFF_BEAT_S = 0.15      # a cut this far from a beat feels late or early
ON_DOWNBEAT_S = 0.12
CLOSE = re.compile(r"close|tight|\bcu\b|\becu\b|\bmcu\b|portrait|head and shoulders|insert|detail", re.I)


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _num(v, default=0.0) -> float:
    try:
        f = float(v)
        return f if f == f and abs(f) != float("inf") else default
    except (TypeError, ValueError):
        return default


def _grid(sm: dict) -> tuple[float, list[float], list[float]]:
    """(bpm, downbeats, every beat): beats are the song's own downbeats with the beats between them, from the tempo."""
    bpm = _num((sm or {}).get("bpm"))
    if not MIN_BPM <= bpm <= MAX_BPM:      # a damaged song map must not make a grid of a billion beats (or none): treat the tempo as unknown
        bpm = 0.0
    downs = sorted(_num(x) for x in (sm or {}).get("downbeats") or [] if isinstance(x, (int, float)))
    duration = min(_num((sm or {}).get("duration")), 3 * 3600.0)
    beats: list[float] = []
    if bpm > 0 and duration > 0:
        step = 60.0 / bpm
        t = (downs[0] if downs else 0.0) % step
        while t <= duration + 1e-6:
            beats.append(round(t, 4))
            t += step
    return bpm, downs, beats


def _nearest(t: float, points: list[float]) -> tuple[float, float] | None:
    return min(((abs(p - t), p) for p in points), default=None)


def beat_line(d: str, shot: dict) -> str | None:
    """One line telling a dance shot's video prompt where the beat is, or None when the song's tempo is not known."""
    sm = _read(os.path.join(d, "songmap.json"), {}) or {}
    bpm, downs, beats = _grid(sm)
    s, e = _num(shot.get("start")), _num(shot.get("end"))
    if bpm <= 0 or e <= s:
        return None
    n = max(1, round((e - s) * bpm / 60.0))
    near = _nearest(s, downs)
    on = near is not None and near[0] <= ON_DOWNBEAT_S
    accents = [round(a - s, 1) for a in (sm.get("accents") or []) if isinstance(a, (int, float)) and s <= a <= e][:3]
    bars = n / 4
    span = f"{n} beats" + (f" ({bars:g} bars)" if n % 4 == 0 else "")
    out = f"Beat: {span} at {round(bpm)} BPM; the shot {'starts on the downbeat' if on else 'starts between downbeats'}, so land the big moves on the beat"
    if accents:
        out += " (strong hits at " + ", ".join(f"{a:g} s" for a in accents) + " in)"
    return out + "."


def is_dancing(d: str, shot: dict) -> bool:
    from .onboarding import choreo_get, dance_override, is_dance_shot
    mode = dance_override(d, shot.get("id"))
    if mode == "off":
        return False
    c = choreo_get(d)
    planned = ((c.get("plan") or {}).get("shots") or {}).get(shot.get("id", ""))
    if planned is not None:
        return bool(planned.get("dancing", True)) if isinstance(planned, dict) else False
    return mode == "on" or is_dance_shot(shot)


def check_shot(shot: dict, beats: list[float]) -> list[dict]:
    issues = []
    s, e = _num(shot.get("start")), _num(shot.get("end"))
    length = e - s
    framing = f"{shot.get('framing', '')} {shot.get('lens', '')}"
    if CLOSE.search(framing):
        issues.append({"kind": "close", "text": f"The frame is {framing.strip() or 'close'}: the body, which is the dance, is mostly out of shot.", "fix": "Use a wide or full-body frame for this shot."})
    if not shot.get("performers"):
        issues.append({"kind": "nobody", "text": "No performer is listed in this shot, so nobody dances.", "fix": "Add the dancers to the shot."})
    if 0 < length < MIN_S:
        issues.append({"kind": "short", "text": f"The shot is only {length:.1f} s: too short for a move to read.", "fix": f"Make it at least {MIN_S:g} s, or merge it with a neighbour."})
    if length > MAX_S:
        issues.append({"kind": "long", "text": f"The shot is {length:.1f} s: a video model rarely holds one move that long.", "fix": "Split it at a bar line into two shots."})
    near = _nearest(s, beats)
    if near is not None and near[0] > OFF_BEAT_S:
        issues.append({"kind": "off_beat", "text": f"The cut lands {near[0]:.2f} s away from the nearest beat ({near[1]:.2f} s).", "fix": f"Move the start of the shot to {near[1]:.2f} s."})
    return issues


def check(d: str) -> dict:
    """Every dance shot of the plan with what is wrong with it for dancing. Free; reads files only."""
    from .planio import load_plan as _load_plan
    sm = _read(os.path.join(d, "songmap.json"), {}) or {}
    _, _, beats = _grid(sm)
    try:
        _, plan = _load_plan(d)
    except SystemExit:
        return {"dance_shots": 0, "clean": 0, "shots": [], "note": "There is no shot plan yet."}
    rows = []
    for sc in plan.get("scenes", []):
        for sh in sc.get("shots", []):
            if not is_dancing(d, sh):
                continue
            issues = check_shot(sh, beats)
            rows.append({"shot": sh["id"], "start": _num(sh.get("start")), "end": _num(sh.get("end")), "framing": sh.get("framing") or "", "issues": issues})
    clean = sum(1 for r in rows if not r["issues"])
    note = "" if rows else "No shot is a dance shot yet: write a choreography plan, or mark a shot as dancing in its Acting panel."
    if rows and not beats:
        note = "The song's tempo is not known, so cuts could not be compared with the beat."
    return {"dance_shots": len(rows), "clean": clean, "shots": rows, "note": note}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-dance")
    ap.add_argument("action", choices=["check"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    try:
        print(json.dumps({"event": "result", "data": check(a.project)}), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except Exception as e:
        print(json.dumps({"event": "error", "message": f"{type(e).__name__}: {e}"}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
