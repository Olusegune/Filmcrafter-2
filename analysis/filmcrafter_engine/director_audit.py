"""What the Director changed: the shot plan you gave it against the shot plan it made.

The Director may merge two planned beats into one shot (to give a short beat enough screen time) and may drop a beat it can't
fit. It says so in its notes, but a merge can still be wrong for a particular moment: two people's lines in one clip, two actions
in four seconds. This lists every merge, drop and gap with the reason to look twice, and can undo a merge.

  audit   what was planned, what was directed, and what to check
  split   turn one merged shot back into its beats as separate shots

A split never renumbers anything: the first beat keeps the shot's id (and so any keyframe or take already made for it), and the
others get the same id with a letter (S09-03b), so no render, keyframe or reference is ever pointed at the wrong shot. The old
directed plan is kept beside it (directed.before-split-<time>.json).

  python -m filmcrafter_engine.director_audit <audit|split> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import string
import sys
import time

MIN_SHOT = 1.5          # seconds: below this a generated shot doesn't read
CROWDED = 2.0           # seconds per action below which a merged shot is flagged


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data) -> None:
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def _plans(d: str) -> tuple[dict, dict]:
    prod = _read(os.path.join(d, "production.json"))
    directed = _read(os.path.join(d, "directed.json"))
    if not prod:
        raise SystemExit("This project has no shot plan from a script or package to compare against.")
    if not directed:
        raise SystemExit("The Director hasn't directed this project yet.")
    return prod, directed


def _index(prod: dict) -> dict[str, dict]:
    """Every id a directed shot might use for a planned shot: its own id, the ids it lists as sources, and its package id."""
    idx: dict[str, dict] = {}
    for sc in prod["scenes"]:
        for s in sc["shots"]:
            idx[s["id"]] = s
            for x in s.get("source_shots") or []:
                idx.setdefault(x, s)
            if s.get("external_id"):
                idx.setdefault(s["external_id"], s)
    return idx


def _sources(shot: dict, idx: dict[str, dict]) -> list[dict]:
    out, seen = [], set()
    for sid in shot.get("source_shots") or []:
        src = idx.get(sid)
        if src and src["id"] not in seen:
            seen.add(src["id"])
            out.append(src)
    return out


def _people(s: dict) -> list[str]:
    return [p for p in s.get("performers") or []]


def audit(d: str) -> dict:
    prod, directed = _plans(d)
    idx = _index(prod)
    planned = [s for sc in prod["scenes"] for s in sc["shots"]]
    made = [(sc, s) for sc in directed["scenes"] for s in sc["shots"]]
    covered: set[str] = set()
    merges, drops = [], []
    for sc, s in made:
        srcs = _sources(s, idx)
        covered.update(x["id"] for x in srcs)
        dur = float(s["end"]) - float(s["start"])
        if len(srcs) > 1:
            risks = []
            who = [set(_people(x)) for x in srcs]
            if len({frozenset(w) for w in who}) > 1:
                risks.append("different people are the focus of each beat")
            cues = [x.get("lyrics") or [] for x in srcs]
            if sum(1 for c in cues if c) > 1:
                risks.append("two separate lyric or dialogue lines fall in one shot (only one can be lip-synced)")
            if dur / len(srcs) < CROWDED:
                risks.append(f"each of the {len(srcs)} actions gets under {CROWDED:.0f} seconds")
            if len(srcs) >= 3:
                risks.append("three or more actions in one clip")
            merges.append({"shot": s["id"], "scene": sc["number"], "start": round(float(s["start"]), 2), "end": round(float(s["end"]), 2),
                           "duration": round(dur, 2), "check": bool(risks), "risks": risks,
                           "note": (sc.get("director_note") or "")[:400],
                           "sources": [{"id": x["id"], "cue": x.get("lyrics") or [], "people": _people(x), "description": (x.get("description") or "")[:200]} for x in srcs]})
        if s.get("dropped_beats"):
            drops.append({"shot": s["id"], "beats": s["dropped_beats"]})
    uncovered = [{"id": s["id"], "description": (s.get("description") or "")[:160], "cue": s.get("lyrics") or []} for s in planned if s["id"] not in covered]
    return {"planned": len(planned), "directed": len(made), "merges": merges, "drops": drops, "uncovered": uncovered,
            "ok": not merges and not drops and not uncovered}


def _letters(base: str, taken: set[str], n: int) -> list[str]:
    ids = [base]
    for ch in string.ascii_lowercase[1:]:
        if len(ids) == n:
            break
        if f"{base}{ch}" not in taken:
            ids.append(f"{base}{ch}")
    return ids


def split(d: str, shot_id: str) -> dict:
    """Turn a merged directed shot back into one shot per planned beat, in order, sharing its time in proportion to the beats' own."""
    prod, directed = _plans(d)
    idx = _index(prod)
    sc = next((c for c in directed["scenes"] if any(s["id"] == shot_id for s in c["shots"])), None)
    if not sc:
        raise SystemExit("That shot isn't in the directed plan.")
    pos = next(i for i, s in enumerate(sc["shots"]) if s["id"] == shot_id)
    shot = sc["shots"][pos]
    srcs = _sources(shot, idx)
    if len(srcs) < 2:
        raise SystemExit(f"{shot_id} isn't a merge: it carries one beat.")
    start, end = float(shot["start"]), float(shot["end"])
    n = len(srcs)
    if end - start < MIN_SHOT * n:
        raise SystemExit(f"{shot_id} is only {end - start:.1f} seconds, too short to split into {n} shots of at least {MIN_SHOT} seconds.")
    weights = [max(0.1, float(x.get("end", 0)) - float(x.get("start", 0))) or 1.0 for x in srcs]
    total = sum(weights)
    spans = [max(MIN_SHOT, (end - start) * w / total) for w in weights]
    over = sum(spans) - (end - start)
    if over > 1e-6:                                                    # take the excess back from the longest pieces, never below the minimum
        for i in sorted(range(n), key=lambda k: -spans[k]):
            cut = min(over, spans[i] - MIN_SHOT)
            spans[i] -= cut
            over -= cut
    taken = {s["id"] for c in directed["scenes"] for s in c["shots"]}
    ids = _letters(shot_id, taken, n)
    if len(ids) < n:
        raise SystemExit("Too many splits of this shot already.")
    pieces, t = [], start
    for i, (src, secs, new_id) in enumerate(zip(srcs, spans, ids)):
        p = copy.deepcopy(shot)
        p.pop("dropped_beats", None)
        a, b = round(t, 3), round(t + secs if i < n - 1 else end, 3)
        text = src.get("description") or (src.get("beats") or [""])[0]
        p.update(id=new_id, start=a, end=b, duration_seconds=round(b - a, 3), source_shots=(src.get("source_shots") or [src["id"]])[:1],
                 beats=[text] if text else [], visual_prompt=text, performers=_people(src) or shot.get("performers", []),
                 split_from=shot_id, state="planned")
        if src.get("framing"):
            p["framing"] = src["framing"]
        pieces.append(p)
        t = b
    backup = os.path.join(d, f"directed.before-split-{time.strftime('%Y%m%d-%H%M%S')}.json")
    _write(backup, directed)
    sc["shots"][pos:pos + 1] = pieces
    _write(os.path.join(d, "directed.json"), directed)
    return {"split": [p["id"] for p in pieces], "spans": [[p["start"], p["end"]] for p in pieces],
            "note": f"{shot_id} keeps any keyframe or take already made for it; those were made for the merged action, so make them again if they look wrong. "
                    f"The new shot(s) {', '.join(p['id'] for p in pieces[1:])} start without one.", "backup": os.path.basename(backup)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-director-audit")
    ap.add_argument("action", choices=["audit", "split"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        res = audit(a.project) if a.action == "audit" else split(a.project, x["shot"])
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
