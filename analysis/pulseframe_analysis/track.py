"""How each model has done in THIS project: takes made, failures (and why), what they cost, whether their review was good, and for sung shots whether the sound in the take followed the vocal.

Nothing is invented and nothing is sent anywhere: it only reads what the project already recorded (jobs.json), and runs the free local sound check on sung takes that have not been checked yet
(a few at a time). The point is that the choice of model, and of lip-sync mode, rests on what your own renders did, not on a guess.

  python -m pulseframe_analysis.track stats <project>
"""
from __future__ import annotations

import argparse
import json
import os
import sys

MAX_CHECKS = 6          # sound checks run on the spot per call (each reads one short take)
FAIL_STATES = ("failed",)


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _num(v) -> float | None:
    try:
        f = float(v)
        return f if f == f and abs(f) != float("inf") else None
    except (TypeError, ValueError):
        return None


def tally(jobs: list[dict]) -> dict:
    """Per model: {provider, model, takes, failed, failures: {kind: n}, cost, reviews: {verdict: n}, sound: {verdict: n}, sung}. Only video takes count."""
    out: dict[tuple, dict] = {}
    for j in jobs:
        if not isinstance(j, dict) or j.get("kind", "video") != "video" or j.get("media_kind") == "image" or j.get("provider") == "own":
            continue
        key = (str(j.get("provider") or ""), str(j.get("model") or ""))
        if not key[1] or j.get("state") not in ("ready",) + FAIL_STATES:
            continue                                   # a render still queued or running has not done anything yet
        m = out.setdefault(key, {"provider": key[0], "model": key[1], "takes": 0, "failed": 0, "failures": {}, "cost": 0.0, "reviews": {}, "sound": {}, "sung": 0})
        if j.get("state") == "ready":
            m["takes"] += 1
            c = _num(j.get("cost"))
            if c and (j.get("cost_unit") in (None, "usd", "USD", "$")):
                m["cost"] = round(m["cost"] + c, 4)
            rv = (j.get("review") or {}).get("verdict") if isinstance(j.get("review"), dict) else None
            if rv:
                m["reviews"][rv] = m["reviews"].get(rv, 0) + 1
            t = j.get("audio_timing")
            if isinstance(t, dict) and t.get("verdict"):
                m["sung"] += 1
                m["sound"][t["verdict"]] = m["sound"].get(t["verdict"], 0) + 1
        elif j.get("state") in FAIL_STATES:
            m["failed"] += 1
            k = str(j.get("error_kind") or "other")
            m["failures"][k] = m["failures"].get(k, 0) + 1
    return {f"{k[0]}|{k[1]}": v for k, v in out.items()}


def check_sound(d: str, limit: int = MAX_CHECKS) -> int:
    """Run the free sound check on sung takes in use that have none yet. Returns how many were checked."""
    from .lipsync_check import timing_shot
    from .library import chosen_take, shot_state
    from .planio import load_plan
    from .render import Store, singing
    try:
        plan_name, plan = load_plan(d)
    except SystemExit:
        return 0
    store, state = Store(d), shot_state(d)
    done = 0
    for sc in plan.get("scenes", []):
        for sh in sc.get("shots", []):
            if done >= limit:
                return done
            t = chosen_take(d, sh["id"], plan_name, store.jobs, state)
            if not t or t.get("media_kind") == "image" or t.get("provider") == "own" or t.get("audio_timing") or not singing(d, sh, plan):
                continue
            try:
                res = timing_shot(d, sh, t)
            except Exception:
                continue
            j = next((x for x in store.jobs if x["id"] == t["id"]), None)
            if j is not None:
                store.update(j, audio_timing=res)
                done += 1
    return done


def stats(d: str, check: bool = True) -> dict:
    checked = check_sound(d) if check else 0
    from .render import Store
    jobs = Store(d).jobs if os.path.exists(os.path.join(d, "jobs.json")) else []
    models = tally(jobs)
    rows = sorted(models.values(), key=lambda m: (-(m["takes"] + m["failed"]), m["model"]))
    return {"models": rows, "checked_now": checked}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="pulseframe-track")
    ap.add_argument("action", choices=["stats"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        print(json.dumps({"event": "result", "data": stats(a.project, bool(x.get("check", True)))}), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except Exception as e:
        print(json.dumps({"event": "error", "message": f"{type(e).__name__}: {e}"}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
