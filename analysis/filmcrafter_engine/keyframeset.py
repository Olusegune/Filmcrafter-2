"""Work on the whole set of keyframes at once: look at everyone's hands, and redo keyframes on one picture model.

  check_plan / check_run     Look at the hands and bodies in every approved keyframe of a shot with people in it, before any video is made from them. Each result is kept (by picture, so a new
                             keyframe is never judged by an old result) and shown on the shot's card. This only looks; it changes nothing. It needs an AI brain with vision (a few cents a picture).
  remake_plan / remake_run   Make new keyframes for the ones that failed the check, on the same model, with the correction for the problem.
  remodel_plan / remodel_run Make new keyframes on ONE picture model for every shot whose approved keyframe was made by a different one, so the whole cast is drawn the same way.
  swap_status / apply_swaps  The new pictures wait beside the old ones; nothing changes until you choose to use them. Applying is one step in the shot history (it can be undone).

Nothing is ever deleted: the old keyframes stay in each shot's versions, and videos already made from them are not touched (they are made from the old picture, so they are re-rendered if wanted).
Shots whose keyframe is your own picture (not made by a model here) and shots that are locked are left alone.

  python -m filmcrafter_engine.keyframeset <action> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from .shothistory import tracked

CHECK_USD = 0.02            # about what one vision check costs; shown as a guide only
CHECKS_FILE = "keyframe_checks.json"
MAX_CHECKS = 2000


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


# ---------------------------------------------------------------- what the keyframes are now

def keyframe_job(jobs: list[dict], plan_name: str, shot_id: str, rel: str | None) -> dict | None:
    """The finished keyframe job that made this picture (newest if several), or None (your own picture, or one imported)."""
    if not rel:
        return None
    hits = [j for j in jobs if isinstance(j, dict) and j.get("kind") == "image" and j.get("shot_id") == shot_id and j.get("plan") == plan_name
            and j.get("state") == "ready" and j.get("output") == rel and j.get("frame", "start") != "end"]
    return max(hits, key=lambda j: j.get("created", 0), default=None)


def inside(d: str, rel) -> bool:
    """A file that exists inside the project folder (a path from a project file that leads anywhere else is never used)."""
    if not isinstance(rel, str) or not rel or os.path.isabs(rel):
        return False
    base = os.path.realpath(d)
    full = os.path.realpath(os.path.join(d, rel))
    return full.startswith(base + os.sep) and os.path.isfile(full)


def checks(d: str) -> dict:
    c = _read(os.path.join(d, CHECKS_FILE), {})
    return c if isinstance(c, dict) else {}


def check_state(res) -> str | None:
    """fail | look | pass | None for one keyframe check result. `look` is a picture that passed with a minor problem (soft hands) worth seeing."""
    if not isinstance(res, dict) or res.get("ok") is None:
        return None
    if res.get("ok") is False:
        return "fail"
    return "look" if any(isinstance(p, dict) and p.get("severity") == "minor" for p in res.get("problems") or []) else "pass"


def current(d: str) -> list[dict]:
    """Every shot with its approved keyframe: {shot, shot_obj, rel, job, provider, model, locked, check}."""
    from .library import _plan, shot_state
    plan_name, plan = _plan(d)
    jobs = (_read(os.path.join(d, "jobs.json"), {"jobs": []}) or {}).get("jobs", [])
    kfs = (_read(os.path.join(d, "keyframes.json"), {}) or {}).get(plan_name, {})
    state, saved = shot_state(d), checks(d)
    out = []
    for sc in plan.get("scenes", []):
        for sh in sc.get("shots", []):
            sid = sh["id"]
            ref = kfs.get(sid)
            rel = ref[len("project:"):] if isinstance(ref, str) and ref.startswith("project:") else None
            if rel and not inside(d, rel):
                rel = None
            job = keyframe_job(jobs, plan_name, sid, rel)
            res = saved.get(rel) if rel else None
            if res is None and job:
                res = job.get("still_check")
            out.append({"shot": sid, "shot_obj": sh, "rel": rel, "job": job, "provider": (job or {}).get("provider"), "model": (job or {}).get("model"),
                        "locked": bool((state.get(sid) or {}).get("locked")), "check": res, "plan": plan_name})
    return out


def state_for(d: str) -> dict:
    """{shot: fail|look|pass} for the cards on the timeline."""
    return {c["shot"]: s for c in current(d) if c["rel"] and (s := check_state(c["check"]))}


# ---------------------------------------------------------------- looking at hands

def flagged(d: str) -> list[dict]:
    """The keyframes whose hands or body the check flagged (failed, or passed with a note): {shot, image, state, detail}, failures first."""
    out = []
    for c in current(d):
        st = check_state(c["check"]) if c["rel"] else None
        if st in ("fail", "look"):
            probs = [p for p in (c["check"].get("problems") or []) if isinstance(p, dict) and (st == "fail" or p.get("severity") == "minor")]
            out.append({"shot": c["shot"], "image": c["rel"], "state": st, "locked": c["locked"], "detail": " ".join(str(p.get("detail", "")) for p in probs)[:240]})
    return sorted(out, key=lambda x: x["state"] != "fail")


def _targets(d: str, shots, again: bool) -> tuple[list[dict], list[str], list[dict]]:
    from . import anatomy
    want = set(shots) if shots else None
    todo, already, skipped = [], [], []
    for c in current(d):
        if want is not None and c["shot"] not in want:
            continue
        if not c["rel"]:
            skipped.append({"shot": c["shot"], "reason": "no approved keyframe yet"})
        elif not anatomy.guard(c["shot_obj"]):
            skipped.append({"shot": c["shot"], "reason": "nobody is in this shot"})
        elif isinstance(c["check"], dict) and c["check"].get("anatomy_checked") and not again:
            already.append(c["shot"])
        else:
            todo.append(c)
    return todo, already, skipped


def check_plan(d: str, shots=None, again: bool = False) -> dict:
    """What a hands check would look at, and about what it costs. Free: nothing is sent."""
    from .stills import can_check
    todo, already, skipped = _targets(d, shots, again)
    try:
        able = can_check()
    except Exception:
        able = False
    return {"flagged": flagged(d), "shots": [c["shot"] for c in todo], "already": already, "skipped": skipped, "usd_est": round(len(todo) * CHECK_USD, 2), "can_check": bool(able),
            "unavailable": "" if able else "Checking needs an AI brain that can look at pictures: add an OpenAI key in Settings, or set up a local model that can see."}


def check_run(d: str, shots=None, again: bool = False) -> dict:
    """Look at every keyframe in the plan. Results are saved as they come, so stopping part-way keeps what was done."""
    from .render import emit
    from .stills import can_check, check
    if not can_check():
        raise SystemExit(check_plan(d, shots, again)["unavailable"])
    todo, _, _ = _targets(d, shots, again)
    path = os.path.join(d, CHECKS_FILE)
    saved = checks(d)
    summary: dict = {"checked": 0, "passed": 0, "failed": [], "look": [], "errors": []}
    for i, c in enumerate(todo, 1):
        emit(event="progress", stage=f"checking hands in keyframe {c['shot']} ({i} of {len(todo)})")
        try:
            res = check(d, {"shot_id": c["shot"], "output": c["rel"], "plan": c["plan"]})
        except SystemExit as e:
            summary["errors"].append({"shot": c["shot"], "error": str(e)})
            continue
        except Exception as e:
            from .director import openai_error
            summary["errors"].append({"shot": c["shot"], "error": openai_error(e)})
            continue
        res["anatomy_checked"] = True
        res["checked_at"] = int(time.time())
        saved[c["rel"]] = res
        if len(saved) > MAX_CHECKS:
            saved = dict(list(saved.items())[-MAX_CHECKS:])
        _write(path, saved)
        summary["checked"] += 1
        s = check_state(res)
        if s == "fail":
            summary["failed"].append({"shot": c["shot"], "kinds": sorted({p["kind"] for p in res["problems"]}), "detail": " ".join(p["detail"] for p in res["problems"])[:300]})
        elif s == "look":
            summary["look"].append({"shot": c["shot"], "detail": " ".join(p["detail"] for p in res["problems"] if p.get("severity") == "minor")[:300]})
        else:
            summary["passed"] += 1
    return summary


# ---------------------------------------------------------------- making new keyframes to swap in

def _need_key(provider: str) -> None:
    from .router import PROVIDER_NAMES, available
    if provider != "comfyui" and not available(provider):
        raise SystemExit(f"Add your {PROVIDER_NAMES.get(provider, provider)} key in Settings first.")


def queue_swaps(d: str, items: list[dict], reason: str) -> dict:
    """Queue a new keyframe for each {shot, provider, model, notes}. They are tagged so that apply_swaps can find them; nothing replaces an approved keyframe yet."""
    from .render import Store, enqueue
    from .routing import batch_usd
    store = Store(d)
    queued, usd = [], 0.0
    for it in items:
        _need_key(it["provider"])
        made = enqueue(d, [it["shot"]], it["provider"], it["model"], {}, it.get("notes") or [], kind="image")
        usd += batch_usd(d, [it["shot"]], it["provider"], it["model"], "image")
        for m in made:
            store.update(m, swap_in=reason)
            queued.append(m)
    return {"queued": len(queued), "jobs": queued, "usd_est": round(usd, 2)}


def remake_plan(d: str) -> dict:
    """The keyframes that failed the check and could be made again on the model that made them. Free."""
    from .routing import batch_usd
    items, skipped = [], []
    for c in current(d):
        if check_state(c["check"]) != "fail":
            continue
        if c["locked"]:
            skipped.append({"shot": c["shot"], "reason": "locked"})
        elif not c["job"]:
            skipped.append({"shot": c["shot"], "reason": "not made by a model here (your own picture)"})
        else:
            items.append({"shot": c["shot"], "provider": c["provider"], "model": c["model"], "notes": [c["check"].get("fix")] if c["check"].get("fix") else []})
    usd = sum(batch_usd(d, [i["shot"]], i["provider"], i["model"], "image") for i in items)
    return {"shots": [i["shot"] for i in items], "skipped": skipped, "usd_est": round(usd, 2)}


def remake_run(d: str, shots=None) -> dict:
    """Make new keyframes for the failed ones (all of them, or the shots given)."""
    from .library import shot_state
    want = set(shots) if shots else None
    locked = {s for s, v in shot_state(d).items() if isinstance(v, dict) and v.get("locked")}
    items = []
    for c in current(d):
        if check_state(c["check"]) == "fail" and c["job"] and c["shot"] not in locked and (want is None or c["shot"] in want):
            items.append({"shot": c["shot"], "provider": c["provider"], "model": c["model"], "notes": [c["check"].get("fix")] if c["check"].get("fix") else []})
    if not items:
        raise SystemExit("No keyframe that failed the check can be made again.")
    return queue_swaps(d, items, "hands")


def _target(d: str, provider, model):
    """The picture model to bring everything to: the one given, else the pinned one, else the one that made most of the keyframes."""
    from .routing import models
    cur = current(d)
    if not provider or not model:
        project = _read(os.path.join(d, "project.json"), {}) or {}
        pin = (((project.get("routing") or {}).get("pins")) or {}).get("image")
        if pin:
            provider, model = pin.get("provider"), pin.get("model")
        else:
            counts: dict = {}
            for c in cur:
                if c["job"]:
                    counts[(c["provider"], c["model"])] = counts.get((c["provider"], c["model"]), 0) + 1
            if not counts:
                raise SystemExit("There are no keyframes made by a picture model yet.")
            provider, model = max(counts.items(), key=lambda kv: kv[1])[0]
    row = next((m for m in models("image") if m["provider"] == provider and m["model"] == model), None)
    if not row:
        raise SystemExit("That picture model isn't in FilmCrafter's list, or you don't have a key for its service.")
    if row.get("sees_references") is False:
        raise SystemExit(f"{row['label']} can't see your character pictures, so the people would change. Choose a model that can.")
    return provider, model, row, cur


def remodel_plan(d: str, provider=None, model=None) -> dict:
    """Which keyframes were made by a different picture model than the target, and about what redoing them costs. Free."""
    from .routing import batch_usd
    provider, model, row, cur = _target(d, provider, model)
    items, skipped, used = [], [], {}
    for c in cur:
        if not c["rel"]:
            continue
        if c["job"]:
            used[(c["provider"], c["model"])] = used.get((c["provider"], c["model"]), 0) + 1
        if c["job"] and (c["provider"], c["model"]) == (provider, model):
            continue
        if c["locked"]:
            skipped.append({"shot": c["shot"], "reason": "locked"})
        elif not c["job"]:
            skipped.append({"shot": c["shot"], "reason": "your own picture"})
        else:
            items.append({"shot": c["shot"], "from": c["model"]})
    usd = batch_usd(d, [i["shot"] for i in items], provider, model, "image") if items else 0.0
    return {"target": {"provider": provider, "model": model, "label": row["label"], "price_usd": row["price_usd"]}, "shots": [i["shot"] for i in items], "from": items, "skipped": skipped,
            "used": [{"provider": p, "model": m, "count": n} for (p, m), n in sorted(used.items(), key=lambda kv: -kv[1])], "usd_est": usd}


def remodel_run(d: str, provider=None, model=None, shots=None, pin: bool = True) -> dict:
    """Make new keyframes on the target model for the shots whose approved keyframe came from another (and pin the target for the project, so new ones match)."""
    plan = remodel_plan(d, provider, model)
    t = plan["target"]
    ids = [s for s in plan["shots"] if not shots or s in set(shots)]
    if not ids:
        raise SystemExit("Every keyframe that can be redone is already on that model.")
    out = queue_swaps(d, [{"shot": s, "provider": t["provider"], "model": t["model"], "notes": []} for s in ids], "model")
    if pin:
        from .routing import set_
        set_(d, {"pin": {"kind": "image", "provider": t["provider"], "model": t["model"]}})
    return {**out, "target": t}


# ---------------------------------------------------------------- using them

def swap_status(d: str) -> dict:
    """Where the new keyframes are: still being made, ready to use, or failed."""
    from .library import _plan
    plan_name, _ = _plan(d)
    jobs = (_read(os.path.join(d, "jobs.json"), {"jobs": []}) or {}).get("jobs", [])
    out: dict = {"making": 0, "ready": 0, "failed": 0, "reasons": {}}
    best: dict = {}
    for j in jobs:
        if not isinstance(j, dict) or not j.get("swap_in") or j.get("plan") != plan_name or j.get("kind") != "image":
            continue
        r = out["reasons"].setdefault(j["swap_in"], {"making": 0, "ready": 0, "failed": 0})
        if j["state"] in ("queued", "submitting", "submitted", "uncertain"):
            r["making"] += 1
            out["making"] += 1
        elif j["state"] == "failed":
            r["failed"] += 1
            out["failed"] += 1
        elif j["state"] == "ready" and not j.get("rejected"):
            if j.get("shot_id") not in best or j.get("created", 0) > best[j["shot_id"]].get("created", 0):
                best[j["shot_id"]] = j
    for sid, j in best.items():
        r = out["reasons"].setdefault(j["swap_in"], {"making": 0, "ready": 0, "failed": 0})
        if isinstance(j.get("still_check"), dict) and j["still_check"].get("ok") is False:
            r["failed"] += 1
            out["failed"] += 1
        else:
            r["ready"] += 1
            out["ready"] += 1
    out["shots_ready"] = sorted(sid for sid, j in best.items() if not (isinstance(j.get("still_check"), dict) and j["still_check"].get("ok") is False))
    return out


def _all_shots(d: str, shots=None, *a, **k) -> list[str]:
    from .library import _plan
    if shots:
        return list(shots)
    try:
        return [s["id"] for sc in _plan(d)[1]["scenes"] for s in sc["shots"]]
    except (OSError, KeyError, ValueError, TypeError):
        return []


@tracked("Use new keyframes", _all_shots)
def apply_swaps(d: str, shots=None) -> dict:
    """Make the newest finished new keyframe of each shot its approved keyframe (all shots, or the ones given). One undoable step."""
    from .library import _plan, shot_state
    from .render import Store
    plan_name, _ = _plan(d)
    store = Store(d)
    state = shot_state(d)
    want = set(shots) if shots else None
    path = os.path.join(d, "keyframes.json")
    kf = _read(path, {}) or {}
    applied, skipped = [], []
    best: dict = {}
    for j in store.jobs:
        if j.get("swap_in") and j.get("plan") == plan_name and j.get("kind") == "image" and j.get("state") == "ready" and not j.get("rejected") and j.get("output") \
                and inside(d, j["output"]) and (want is None or j["shot_id"] in want):
            if j["shot_id"] not in best or j.get("created", 0) > best[j["shot_id"]].get("created", 0):
                best[j["shot_id"]] = j
    for sid, j in sorted(best.items()):
        if (state.get(sid) or {}).get("locked"):
            skipped.append({"shot": sid, "reason": "locked"})
        elif isinstance(j.get("still_check"), dict) and j["still_check"].get("ok") is False:
            skipped.append({"shot": sid, "reason": "the new picture failed its check"})
        else:
            kf.setdefault(plan_name, {})[sid] = "project:" + j["output"]
            applied.append(sid)
    if applied:
        _write(path, kf)
        now = int(time.time())
        for j in store.jobs:
            if j.get("swap_in") and j.get("plan") == plan_name and j.get("shot_id") in applied:
                store.update(j, swap_in=None, swap_applied=now)
    return {"applied": applied, "skipped": skipped}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-keyframeset")
    ap.add_argument("action", choices=["check_plan", "check_run", "remake_plan", "remake_run", "remodel_plan", "remodel_run", "swap_status", "swap_apply"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    d = a.project
    try:
        res = (check_plan(d, x.get("shots"), bool(x.get("again"))) if a.action == "check_plan" else check_run(d, x.get("shots"), bool(x.get("again"))) if a.action == "check_run" else
               remake_plan(d) if a.action == "remake_plan" else remake_run(d, x.get("shots")) if a.action == "remake_run" else
               remodel_plan(d, x.get("provider"), x.get("model")) if a.action == "remodel_plan" else
               remodel_run(d, x.get("provider"), x.get("model"), x.get("shots"), x.get("pin", True) is not False) if a.action == "remodel_run" else
               swap_status(d) if a.action == "swap_status" else apply_swaps(d, x.get("shots")))
        print(json.dumps({"event": "result", "data": res}), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except Exception as e:
        print(json.dumps({"event": "error", "message": f"{type(e).__name__}: {e}"}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
