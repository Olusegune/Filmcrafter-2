"""Proving a video model with a real render.

A start → end shot is only as good as the model's honesty about the end frame. Some models are proven (frames.PROVEN_END, from docs/END_FRAMES.md); the rest are flagged "not yet proven".
This module lets you prove one yourself, from a take you already paid for, at no extra cost:

  check(d, shot)    measure how close the take's LAST frame is to the shot's end picture, against how close it is to the START picture. Free and local.
  record(d, shot)   if the take really landed, remember that this model is proven on this computer. The measurement is made again here: the screen cannot claim a result.
  forget(p, m)      take a model off your proven list.
  report()          the built-in proven models and the ones you have proven.

The measure is the mean difference of two small grey pictures (0 to 255), the same one behind the numbers in END_FRAMES.md (1.9 against 21.0 for Hailuo 02).

  python -m filmcrafter_engine.proof <check|record|forget|report> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time

LANDED_MAX = 12.0        # the last frame is this close to the end picture (out of 255) or closer ...
LANDED_RATIO = 0.5       # ... and at most half as far from it as from the start picture
UNCLEAR_START = 3.0      # start and end pictures that look this alike prove nothing either way
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/:@+-]{0,199}")
MAX_RECORDS = 500


def store_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".filmcrafter", "proven_models.json")


def _records() -> list[dict]:
    try:
        with open(store_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [r for r in data if isinstance(r, dict) and isinstance(r.get("provider"), str) and isinstance(r.get("model"), str)
            and NAME.fullmatch(r["provider"]) and NAME.fullmatch(r["model"])][:MAX_RECORDS]


def _save(records: list[dict]) -> None:
    os.makedirs(os.path.dirname(store_path()), exist_ok=True)
    tmp = store_path() + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=1)
    os.replace(tmp, store_path())


def is_proven(provider: str, model: str) -> bool:
    """Built-in proof, or yours."""
    from .frames import PROVEN_END
    return (provider, model) in PROVEN_END or any(r["provider"] == provider and r["model"] == model for r in _records())


def _small(path: str):
    from PIL import Image
    with Image.open(path) as im:
        return list(im.convert("L").resize((64, 36)).tobytes())


def difference(a: str, b: str) -> float:
    """Mean difference of two pictures, 0 (the same) to 255."""
    pa, pb = _small(a), _small(b)
    return round(sum(abs(x - y) for x, y in zip(pa, pb)) / len(pa), 1)


def verdict(start_diff: float, end_diff: float) -> str:
    """landed | missed | unclear, from how far the last frame is from the start and end pictures."""
    if start_diff < UNCLEAR_START:
        return "unclear"
    return "landed" if end_diff <= LANDED_MAX and end_diff <= start_diff * LANDED_RATIO else "missed"


def _take(d: str, shot_id: str):
    from .extend import video_behind
    from .library import chosen_take, shot_state
    from .render import _load_plan, _read
    plan_name, plan = _load_plan(d)
    jobs = _read(os.path.join(d, "jobs.json"), {"jobs": []})["jobs"]
    take = chosen_take(d, shot_id, plan_name, jobs, shot_state(d))
    return plan_name, plan, take, (video_behind(jobs, take) if take else None)


def check(d: str, shot_id: str) -> dict:
    """Where the shot's take landed. Free: nothing is sent anywhere."""
    from . import frames
    from .export import last_frame_png
    plan_name, plan, take, src = _take(d, shot_id)
    out: dict = {"shot": shot_id, "ok": False}
    end = frames.end_ref(d, plan_name, plan, shot_id)
    start = frames.start_ref(d, plan_name, shot_id)
    if not end or not start:
        out["reason"] = "This shot needs both a start and an end picture to check where it landed."
        return out
    if not take or (src.get("kind") or "video") != "video" or not src.get("output"):
        out["reason"] = "This shot has no finished video take yet."
        return out
    video = os.path.join(d, src["output"])
    if not os.path.isfile(video):
        out["reason"] = "The take's video is missing from the project."
        return out
    with tempfile.TemporaryDirectory() as tmp:
        last = os.path.join(tmp, "last.png")
        if not last_frame_png(video, last):
            out["reason"] = "Couldn't read the last frame of that take."
            return out
        sd = difference(last, os.path.join(d, start[len("project:"):]))
        ed = difference(last, os.path.join(d, end[len("project:"):]))
    v = verdict(sd, ed)
    provider, model = src.get("provider", ""), src.get("model", "")
    out.update({"ok": True, "verdict": v, "start_diff": sd, "end_diff": ed, "provider": provider, "model": model, "take": src.get("id"),
                "proven": is_proven(provider, model),
                "text": {"landed": f"The take's last frame is much closer to the end picture ({ed}) than to the start ({sd}): it landed.",
                         "missed": f"The take's last frame is not close to the end picture ({ed} against {sd} from the start): it did not land where you asked.",
                         "unclear": f"The start and end pictures are too alike ({sd} apart) to tell: nothing is proven either way."}[v]})
    return out


def record(d: str, shot_id: str, note: str = "") -> dict:
    """Remember the model as proven, but only if this shot's take really landed (measured again here)."""
    res = check(d, shot_id)
    if not res.get("ok"):
        raise SystemExit(res.get("reason", "Can't check that shot."))
    if res["verdict"] != "landed":
        raise SystemExit("That take did not land on its end picture, so the model is not marked as proven.")
    provider, model = res["provider"], res["model"]
    if not (NAME.fullmatch(provider or "") and NAME.fullmatch(model or "")):
        raise SystemExit("That take doesn't name its model, so it can't be recorded.")
    recs = [r for r in _records() if not (r["provider"] == provider and r["model"] == model)]
    recs.append({"provider": provider, "model": model, "date": time.strftime("%Y-%m-%d"), "end_diff": res["end_diff"], "start_diff": res["start_diff"],
                 "note": re.sub(r"[\x00-\x1f\x7f]+", " ", str(note or "")).strip()[:200]})
    _save(recs[-MAX_RECORDS:])
    return report()


def forget(provider: str, model: str) -> dict:
    _save([r for r in _records() if not (r["provider"] == provider and r["model"] == model)])
    return report()


def report() -> dict:
    from .frames import PROVEN_END
    mine = sorted(_records(), key=lambda r: r.get("date", ""), reverse=True)
    return {"built_in": [{"provider": p, "model": m} for p, m in sorted(PROVEN_END)],
            "yours": [{"provider": r["provider"], "model": r["model"], "date": r.get("date"), "end_diff": r.get("end_diff"), "start_diff": r.get("start_diff"), "note": r.get("note", "")} for r in mine]}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-proof")
    ap.add_argument("action", choices=["check", "record", "forget", "report"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        res = check(a.project, x["shot"]) if a.action == "check" else record(a.project, x["shot"], x.get("note", "")) if a.action == "record" else \
            forget(str(x.get("provider", "")), str(x.get("model", ""))) if a.action == "forget" else report()
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
