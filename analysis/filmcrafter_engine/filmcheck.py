"""The Continuity Director for a film: it reads the shots in order and says where something may have changed between them.

It looks for drift in who is in a shot and in what state (outfit, age, injury), the place, the light and time of day, props that appear and then vanish, how a shot
begins compared with how the one before it ended, which shoulder the camera looks over, and people who have no pictures (so their face could change). It is advisory:
every finding says "may" and gives a reason; you decide, and nothing is ever blocked or changed.

  <Film>/continuity/findings.json   your decision on each finding (noted or dismissed), kept when the checks run again

  python -m filmcrafter_engine.filmcheck <action> <film_dir> --data '{...}'
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

SEVERITIES = ("note", "look", "likely")


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


def _write(path, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _fid(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8"), usedforsecurity=False).hexdigest()[:10]


def _label(bible: dict, key: str, ent_id, state_id) -> str:
    for e in bible.get(key, []):
        if e["id"] == ent_id:
            for s in e["states"]:
                if s["id"] == state_id:
                    return s["label"]
    return state_id or ""


def check_all(contracts: list[dict], bible: dict) -> list[dict]:
    """Every finding for these shots (in order) against this Bible. Pure: nothing is read or written."""
    found: list[dict] = []

    def add(kind: str, shot: str, severity: str, text: str, suggestion: str = "", other: str = "", extra: dict | None = None) -> None:
        found.append({"id": _fid(kind, shot, other, text[:40]), "kind": kind, "shot": shot, "other": other, "severity": severity, "text": text, "suggestion": suggestion, "status": "open", **(extra or {})})

    pics = {c["id"]: bool(c["media"]) for c in bible.get("characters", [])}
    seen_nopic: set[str] = set()
    for c in contracts:
        for p in c["characters"]:
            if p.get("character_id") and not pics.get(p["character_id"], True) and p["character_id"] not in seen_nopic:
                seen_nopic.add(p["character_id"])
                add("identity", c["id"], "likely", f"{p['name'].title()} has no pictures in Cast & World, so their face and clothes may change from shot to shot.", "Add a master picture in Cast & World.", p["character_id"])
        if c["dialogue"] and not c["performance"].get("emotional_intention", "").strip():
            add("performance", c["id"], "note", f"{c['id']} has dialogue but no stated feeling, so the acting may come out generic.", "Say what the audience should feel in the Acting tab.")

    for a, b in zip(contracts, contracts[1:]):
        if a["scene"] != b["scene"]:
            continue
        pair = f"{a['id']}>{b['id']}"
        by_a = {p["name"].lower(): p for p in a["characters"]}
        for p in b["characters"]:
            q = by_a.get(p["name"].lower())
            if not q:
                continue
            for field, what, key in (("state_id", "state", "characters"), ("wardrobe_id", "outfit", "characters")):
                if q.get(field) and p.get(field) and q[field] != p[field]:
                    la = _label(bible, "characters", q.get("character_id"), q.get("state_id")) if field == "state_id" else q[field]
                    lb = _label(bible, "characters", p.get("character_id"), p.get("state_id")) if field == "state_id" else p[field]
                    add("character", b["id"], "likely", f"{p['name'].title()} may have changed {what}: {la} in {a['id']}, {lb} in {b['id']}.",
                        "If the change is meant, ignore this. If not, set them to the same " + what + ".", pair + field)
        la_, lb_ = a["lighting"].get("time", "").strip().lower(), b["lighting"].get("time", "").strip().lower()
        if la_ and lb_ and la_ != lb_:
            add("light", b["id"], "look", f"The time of day may have changed between {a['id']} ({a['lighting']['time']}) and {b['id']} ({b['lighting']['time']}) in the same scene.", "", pair + "time")
        ea, eb = a["environment"], b["environment"]
        if (ea.get("id") or ea.get("name")) and (eb.get("id") or eb.get("name")) and (ea.get("id") or ea.get("name", "").lower()) != (eb.get("id") or eb.get("name", "").lower()):
            add("place", b["id"], "look", f"The place may have changed between {a['id']} ({ea.get('name')}) and {b['id']} ({eb.get('name')}) without the scene changing.", "", pair + "place")
        names_b = {x["name"].lower() for x in b["props"]}
        for pr in a["props"]:
            if pr["name"].lower() not in names_b and pr["name"].lower() in (b["action"] + " " + b["continuity"]).lower() + " " + a["closing_state"].lower():
                add("prop", b["id"], "note", f"{pr['name']} is in {a['id']} but not listed in {b['id']}. If it is still there, it may disappear.", "Add it to the next shot's props.", pair + pr["name"])
        if a["closing_state"].strip() and not b["opening_state"].strip():
            add("state", b["id"], "note", f"{b['id']} doesn't say how it begins. {a['id']} ends: \"{a['closing_state'].strip()[:120]}\".", "Use that as how this shot begins.", pair + "open",
                {"apply": {"opening_state": a["closing_state"].strip()}})
        if a["camera"]["framing"] == "over the shoulder" and b["camera"]["framing"] == "over the shoulder" and a["characters"] and b["characters"] \
                and a["characters"][0]["name"].lower() == b["characters"][0]["name"].lower() and a["dialogue"] and b["dialogue"] and a["dialogue"][-1]["speaker"].lower() != b["dialogue"][0]["speaker"].lower():
            add("direction", b["id"], "look", f"{a['id']} and {b['id']} both look over {a['characters'][0]['name'].title()}'s shoulder, but the other person speaks in the second. The reverse shot usually looks the other way.",
                "Put the camera behind the other person.", pair + "ots")
    from . import blocking                                   # the top-down plans: the camera should stay on one side of the line between two people
    for x in blocking.crossings(contracts):
        add("direction", x["shot"], "look", x["message"], x["fix"], x["previous"] + ">" + x["shot"] + "line")
    return found


def run(d: str) -> dict:
    from . import bible as B
    from . import shots
    shots._film(d)
    idx = shots._index(d)
    cons = [c for c in (_read(shots._cpath(d, s)) for s in idx["order"]) if isinstance(c, dict)]
    found = check_all(cons, B.load(d))
    path = os.path.join(d, "continuity", "findings.json")
    decided = (_read(path, {}) or {}).get("decided", {})
    for f in found:
        if f["id"] in decided:
            f["status"] = decided[f["id"]]
    return {"findings": found, "open": sum(1 for f in found if f["status"] == "open"), "shots": len(cons)}


def decide(d: str, fid: str, state: str) -> dict:
    """Mark a finding noted (you'll deal with it) or dismissed (it is meant). Nothing in the film changes."""
    if state not in ("open", "noted", "dismissed"):
        raise SystemExit("Choose noted, dismissed or open.")
    r = run(d)
    if not any(f["id"] == fid for f in r["findings"]):
        raise SystemExit("That finding isn't there any more.")
    path = os.path.join(d, "continuity", "findings.json")
    data = _read(path, {}) or {}
    data.setdefault("decided", {})
    if state == "open":
        data["decided"].pop(fid, None)
    else:
        data["decided"][fid] = state
    _write(path, data)
    return run(d)


def apply(d: str, fid: str) -> dict:
    """Do what a finding suggests, when it is a plain text suggestion (a shot's opening state): you press the button and it is applied."""
    from . import shots
    r = run(d)
    f = next((x for x in r["findings"] if x["id"] == fid), None)
    if not f or not f.get("apply"):
        raise SystemExit("There is nothing to apply for that finding.")
    shots.set_fields(d, f["shot"], f["apply"])
    return run(d)                                                   # the finding is gone because the shot now says it


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-filmcheck")
    ap.add_argument("action", choices=["check", "decide", "apply"])
    ap.add_argument("target")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "check":
            res = run(a.target)
        elif a.action == "decide":
            res = decide(a.target, str(x.get("id", "")), str(x.get("state", "")))
        else:
            res = apply(a.target, str(x.get("id", "")))
        emit(event="result", data=res)
        return 0
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=__import__("filmcrafter_engine.errtext", fromlist=["plain"]).plain(e))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
