"""What this film has cost so far, in one place (read-only; it never changes, sends or buys anything).

It reads the two records FilmCrafter already keeps: the render jobs (`render/jobs.json`: pictures, video, lip-sync) and the paid-operations ledger (`voice/ledger.json`: voices, sound effects, music).
Each provider reports money in its own unit, so units are never added together: ElevenLabs credits, Kie credits and fal dollars stay apart. An amount is called `reported` only when the provider's own
reply carried it; anything else is an `estimate` and is shown as one, never added to a reported figure.

  python -m filmcrafter_engine.spending summary <film>
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import paidops as P
from . import safeio

STEPS = ("pictures", "video", "lipsync", "voices", "sound_effects", "music", "other")
LABEL = {"pictures": "Pictures", "video": "Video", "lipsync": "Lip-sync", "voices": "Voices", "sound_effects": "Sound effects", "music": "Music", "other": "Other"}
UNIT_NAME = {"usd": "dollars (estimated)", "kie_credits": "Kie credits", "elevenlabs_credits": "ElevenLabs credits", "voice_slot": "voice slots", "credits": "credits", "unknown": "unknown units"}
COUNTED = ("ready", "submitted")


def emit(**kw) -> None:
    sys.stdout.write(json.dumps(kw) + "\n")
    sys.stdout.flush()


def _slot(rows: dict, step: str, provider: str, unit: str) -> dict:
    return rows.setdefault((step, provider, unit), {"step": step, "label": LABEL[step], "provider": provider, "unit": unit, "unit_name": UNIT_NAME.get(unit, unit),
                                                       "operations": 0, "reported": 0.0, "reported_operations": 0, "estimated": 0.0, "estimated_operations": 0})


def _step_of_action(action: str, area: str | None) -> str:
    a = (action or "").lower()
    if a == "sfx" or area == "sfx":
        return "sound_effects"
    if a == "music" or area == "music":
        return "music"
    if a in ("speak", "preview", "design", "design_save", "clone", "sample") or area == "voice":
        return "voices"
    return "other"


def summary(d: str) -> dict:
    """The film's spend by step and provider, what is still uncertain, and the limits that are set. Free and local."""
    rows: dict = {}
    problems: list[str] = []
    try:                                                              # read the plain file: a summary must never move or copy anything, even a damaged file
        jobs = (json.load(open(os.path.join(d, "render", "jobs.json"), encoding="utf-8")) or {}).get("jobs", [])
    except FileNotFoundError:
        jobs = []
    except (OSError, ValueError, AttributeError):
        jobs, problems = [], ["The list of pictures and videos could not be read, so they are not counted here."]
    for j in jobs if isinstance(jobs, list) else []:
        if not isinstance(j, dict) or j.get("state") not in COUNTED:
            continue                                                  # refused or failed-before-sending jobs cost nothing
        kind = j.get("kind", "video")
        step = "pictures" if kind == "image" else "lipsync" if kind == "lipsync" else "video" if kind == "video" else "other"
        prov = j.get("provider") or "unknown"
        if prov == "kie":
            s = _slot(rows, step, prov, "kie_credits")
            s["operations"] += 1
            if j.get("cost") is not None:
                s["reported"] += float(j["cost"]); s["reported_operations"] += 1
        elif prov == "fal":
            s = _slot(rows, step, prov, "usd")
            s["operations"] += 1
            if j.get("estimate_usd") is not None:
                s["estimated"] += float(j["estimate_usd"]); s["estimated_operations"] += 1
        else:
            _slot(rows, step, prov, "unknown")["operations"] += 1       # openai / google and others: counted, no amount to show
    ledger = P.Ledger(os.path.join(d, "voice", "ledger.json"), film=os.path.basename(os.path.normpath(d)))
    try:
        data = ledger.read_plain()
    except (OSError, ValueError):
        data, problems = {"entries": [], "limits": {}}, problems + ["The record of paid voice and sound work could not be read, so it is not counted here."]
    uncertain = []
    for e in data["entries"]:
        counted = e["status"] == P.COMPLETED or (e["status"] == P.UNCERTAIN and (e.get("resolved") or {}).get("outcome") == "charged")
        if e["status"] == P.UNCERTAIN and not e.get("resolved"):
            uncertain.append({"id": e["id"], "provider": e["provider"], "action": e["action"], "at": e["at"], "shot": e.get("shot"), "person": e.get("person")})
        if not counted:
            continue
        step = _step_of_action(e.get("action"), e.get("area"))
        unit = (e.get("estimate") or {}).get("unit", "unknown")
        s = _slot(rows, step, e["provider"], unit)
        s["operations"] += 1
        act = e.get("actual") or {}
        if act.get("reported") and act.get("amount") is not None:
            s["reported"] += float(act["amount"]); s["reported_operations"] += 1
        else:
            s["estimated"] += float((e.get("estimate") or {}).get("amount") or 0); s["estimated_operations"] += 1
    lines = sorted(rows.values(), key=lambda r: (STEPS.index(r["step"]), r["provider"]))
    for r in lines:
        r["reported"], r["estimated"] = round(r["reported"], 2), round(r["estimated"], 2)
    totals: dict = {}
    for r in lines:                                                      # per unit only: never across providers or units
        t = totals.setdefault(r["unit"], {"unit": r["unit"], "unit_name": r["unit_name"], "operations": 0, "reported": 0.0, "estimated": 0.0})
        t["operations"] += r["operations"]; t["reported"] += r["reported"]; t["estimated"] += r["estimated"]
    for t in totals.values():
        t["reported"], t["estimated"] = round(t["reported"], 2), round(t["estimated"], 2)
    return {"lines": lines, "totals": list(totals.values()), "uncertain": uncertain, "limits": data.get("limits", {}), "problems": problems, "operations": sum(r["operations"] for r in lines),
            "note": "Amounts marked reported came from the provider's own reply; estimates are our guess from the published price. Not tracked here: the writing helper (planning with a language model)."}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="spending")
    ap.add_argument("action", choices=["summary"])
    ap.add_argument("film")
    a = ap.parse_args(argv)
    try:
        d = os.path.abspath(a.film)
        if not isinstance(safeio.read_json(os.path.join(d, "film.json"), None), dict):
            raise SystemExit("That isn't a FilmCrafter film.")
        emit(event="result", data=summary(d))
        return 0
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
