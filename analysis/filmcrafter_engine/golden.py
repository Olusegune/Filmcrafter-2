"""Golden-path helpers: what each shot is using, what went stale, a free preview, and splitting a batch by balance.

  python -m filmcrafter_engine.golden <action> <project> --data '{...}'
  actions: status | preview | split | changes
"""
from __future__ import annotations

import argparse
import json
import os
import sys

STILL_MODEL = "keyframe (moving still)"
COPY_GRACE_S = 300          # files closer in time than this are not evidence of a change: copying a project stamps them all alike


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _plan(d):
    name = "directed" if os.path.exists(os.path.join(d, "directed.json")) else "production"
    return name, _read(os.path.join(d, f"{name}.json"), {"scenes": []})


def take_kind(take: dict | None) -> str:
    """'video' (rendered or your own clip), 'still' (a moving still) or 'none'."""
    if not take:
        return "none"
    return "still" if take.get("media_kind") == "image" else "video"


def is_stale(d: str, take: dict | None, kf_ref: str | None) -> bool:
    """A rendered take made from a different keyframe than the one approved now."""
    if not take or take.get("provider") == "own" or not kf_ref or not kf_ref.startswith("project:"):
        return False
    used = take.get("keyframe_ref")
    if used:
        return used != kf_ref
    # Older takes did not record the keyframe they were made from, so judge by file times: the keyframe was changed after the take was sent AND after the take's own file was written.
    # The second test matters: a project that was copied (Save As, a backup, another computer) has every file stamped with the copy time, and with only the first test every shot looked
    # out of date (70 of 76 in one real project), which invites paying to render them all again.
    try:
        kf_t = os.path.getmtime(os.path.join(d, kf_ref[8:]))
        sent = float(take.get("submitted") or take["created"])
        out_t = os.path.getmtime(os.path.join(d, take["output"])) if take.get("output") else 0.0
        return kf_t > sent + 5 and kf_t > out_t + COPY_GRACE_S
    except (OSError, KeyError, ValueError):
        return False


def status(d: str) -> dict:
    from .library import chosen_take, shot_state
    plan_name, plan = _plan(d)
    jobs = _read(os.path.join(d, "jobs.json"), {"jobs": []})["jobs"]
    state = shot_state(d)
    kfs = (_read(os.path.join(d, "keyframes.json"), {}) or {}).get(plan_name, {})
    shots = []
    for sc in plan.get("scenes", []):
        for sh in sorted(sc["shots"], key=lambda x: x["start"]):
            t = chosen_take(d, sh["id"], plan_name, jobs, state)
            k = kfs.get(sh["id"]) or None
            shots.append({"id": sh["id"], "scene": sc.get("number"), "take": take_kind(t), "keyframe": bool(k),
                          "stale": is_stale(d, t, k), "locked": bool(state.get(sh["id"], {}).get("locked")),
                          "described": bool(sh.get("visual_prompt") or sh.get("beats") or sh.get("description"))})
    count = lambda f: [s["id"] for s in shots if f(s)]
    return {"shots": shots, "video": count(lambda s: s["take"] == "video"), "still": count(lambda s: s["take"] == "still"),
            "none": count(lambda s: s["take"] == "none"), "stale": count(lambda s: s["stale"] and not s["locked"]),
            "total": len(shots)}


def preview(d: str, preset: str | None = None) -> dict:
    """Free: every shot with a keyframe but no take becomes a moving still, then a draft export of the whole song."""
    from . import export, media
    made = media.stills(d)["made"]
    p = _read(os.path.join(d, "project.json"), {})
    preset = preset or export.preset_for(p.get("aspect_ratio"))
    out = export.build(d, preset)
    return {"stills_made": made, "export": out}


def split(d: str, shots: list[str], kind: str, models: dict) -> dict:
    """Fill Kie up to its balance, send the rest to fal (same model family), cheapest-first provider order.
    models: {"kie": model, "fal": model}. Returns the two shot lists and what each costs."""
    from .budget import KIE_USD_PER_CREDIT, balance
    from .render import estimate
    kb, fb = balance("kie"), balance("fal")
    per_kie = per_fal = None
    if models.get("kie"):
        e = estimate(d, shots[:1], "kie", models["kie"], kind) if shots else {}
        per_kie = (e.get("kie_credits_est") or 0) or None
    if models.get("fal"):
        e = estimate(d, shots[:1], "fal", models["fal"], kind) if shots else {}
        per_fal = e.get("usd") if e.get("usd") is not None else None
    kie_n = len(shots)
    if per_kie and kb.get("known"):
        kie_n = min(len(shots), int(max(0.0, kb["amount"]) // per_kie))
    elif not models.get("kie"):
        kie_n = 0
    kie_shots, fal_shots = shots[:kie_n], shots[kie_n:]
    out = {"kie": kie_shots, "fal": fal_shots, "kie_credits": round((per_kie or 0) * len(kie_shots)),
           "kie_usd": round((per_kie or 0) * len(kie_shots) * KIE_USD_PER_CREDIT, 2),
           "fal_usd": round((per_fal or 0) * len(fal_shots), 2) if per_fal is not None else None,
           "kie_balance": kb.get("amount"), "fal_balance": fb.get("amount"), "per_kie_credits": per_kie, "per_fal_usd": per_fal}
    out["needed"] = bool(fal_shots) and bool(kie_shots)
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-golden")
    ap.add_argument("action", choices=["status", "preview", "split", "changes"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "changes":
            from .changes import since_last_take
            res = since_last_take(a.project, str(x["shot"]), x.get("provider"), x.get("model"), x.get("overrides") or {})
        else:
            res = status(a.project) if a.action == "status" else preview(a.project, x.get("preset")) if a.action == "preview" \
                else split(a.project, x["shots"], x.get("kind", "video"), x.get("models") or {})
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
