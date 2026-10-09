"""Retry a failed render on a cheaper model.

When a render fails for a reason another model might not share (the model was retired, refused a setting, needed an input PULSEFRAME can't supply, or the provider had an error or timed out),
the failed take offers a short list of cheaper models that PULSEFRAME has proved with a real render, with the price of each, and one click queues the shot again on the one you choose.
Nothing is sent without that click unless you turn on "Retry failed videos on a cheaper model" for the project, and then only for video, only once per shot, only when the new model
costs less than the failed one, and only inside the project's budget.

Rules that keep this safe and sensible:
  - Only a job that FAILED (not one that may already be rendering, or may have been billed: those are "uncertain").
  - Never for a content-filter refusal (`policy`): switching models to get past a provider's filter is not a retry, and never for key or credit problems (another model on the same account fails the same way).
  - Only models with a real, proven render, on providers you have a key for, whose price is known; never the model that just failed.
  - A shot that lands on an end frame only goes to a model that can take one.
  - Pictures keep one model: an automatic retry never switches a picture model (people would stop looking the same), and a manual one says so and shows the warning.
  - The new job is an ordinary job: the project budget applies and the price is shown first; the failed one stays in the list, marked as retried.

  python -m pulseframe_analysis.retrycheap <options|retry> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# failures where a different model could succeed
SWITCHABLE = {"unavailable", "invalid", "missing_input", "service", "timeout", "rate_limit", "download"}
MAX_OPTIONS = 3


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _job(d: str, job_id: str) -> dict:
    j = next((x for x in (_read(os.path.join(d, "jobs.json"), {"jobs": []}) or {}).get("jobs", []) if isinstance(x, dict) and x.get("id") == job_id), None)
    if not j:
        raise SystemExit("That render job no longer exists.")
    return j


def _original_price(j: dict) -> float | None:
    from .budget import KIE_USD_PER_CREDIT
    from .routing import shot_price
    if j.get("estimate_usd") is not None:
        return float(j["estimate_usd"])
    if j["provider"] == "kie" and j.get("cost_unit") == "credits" and j.get("cost"):
        return round(float(j["cost"]) * KIE_USD_PER_CREDIT, 4)
    return shot_price(j["provider"], j["model"])


def why_not(j: dict) -> str | None:
    """Why this job can't be retried on another model, in plain words, or None when it can."""
    if j.get("kind", "video") not in ("video", "image"):
        return "Only a video or a keyframe can be retried on another model."
    if j.get("state") == "uncertain":
        return "This render may already be running or billed at the provider. Check it there before sending it anywhere else."
    if j.get("state") != "failed":
        return "Only a failed render can be retried on another model."
    if j.get("retried_as"):
        return "This render has already been retried on another model."
    kind = j.get("error_kind")
    if kind == "policy":
        return "The provider's content filter blocked this shot. Reword the shot rather than switching models."
    if kind in ("auth", "credits"):
        return "This is a problem with your account at that provider, so another model there would fail the same way. Fix it in Settings, or use Move to another provider in Plan & budget."
    if kind not in SWITCHABLE:
        return "This failure isn't one that another model would fix."
    return None


def options(d: str, job_id: str) -> dict:
    """The cheaper models this failed job could be sent to, cheapest first, each with its price. Free: nothing is sent."""
    from . import frames
    from .modelblurbs import ONE_MODEL_ADVICE
    from .routing import models
    j = _job(d, job_id)
    out: dict = {"job": job_id, "shot": j.get("shot_id"), "can": False, "options": []}
    reason = why_not(j)
    if reason:
        out["reason"] = reason
        return out
    kind = j.get("kind", "video")
    orig = _original_price(j)
    out["original_usd"] = orig
    out["failed_model"] = j["model"]
    project = _read(os.path.join(d, "project.json"), {})
    pinned_image = bool((((project.get("routing") or {}).get("pins")) or {}).get("image"))
    needs_end = False
    if kind == "video":
        try:
            plan_name, plan = frames._plan(d)
            needs_end = bool(frames.end_ref(d, plan_name, plan, j["shot_id"]))
        except Exception:
            needs_end = False
    rows = []
    for m in models(kind):
        if (m["provider"], m["model"]) == (j["provider"], j["model"]) or not m["verified"] or m["price_usd"] is None:
            continue
        if needs_end:
            try:
                if not frames.model_for(m["provider"], m["model"], True).get("supports_end"):
                    continue
            except Exception:
                continue
        if kind == "image" and m.get("sees_references") is False:
            continue                                           # a words-only model can't see the character pictures: the people would change
        cheaper = None if orig is None else m["price_usd"] < orig - 1e-9
        if orig is not None and not cheaper:
            continue
        rows.append({"provider": m["provider"], "model": m["model"], "label": m["label"], "price_usd": m["price_usd"], "cheaper": cheaper,
                     "saves_usd": None if orig is None else round(orig - m["price_usd"], 4), "strength": m.get("strength", ""),
                     "warning": ONE_MODEL_ADVICE if kind == "image" else ""})
    rows.sort(key=lambda r: r["price_usd"])
    out["options"] = rows[:MAX_OPTIONS]
    out["can"] = bool(out["options"])
    if not out["can"]:
        out["reason"] = "No cheaper model that PULSEFRAME has proved is available on the services you have keys for." if orig is not None else \
            "No other proven model with a known price is available on the services you have keys for."
    out["auto"] = bool((project.get("routing") or {}).get("auto_retry"))
    out["image_pinned"] = pinned_image
    return out


def retry(d: str, job_id: str, provider: str, model: str, auto: bool = False) -> dict:
    """Queue the failed job's shot again on one of the models `options` offered. Anything else is refused. The budget guard and the mode apply as for any render."""
    from .render import Store, enqueue
    opts = options(d, job_id)
    if not opts["can"]:
        raise SystemExit(opts.get("reason") or "This render can't be retried on another model.")
    pick = next((o for o in opts["options"] if o["provider"] == provider and o["model"] == model), None)
    if not pick:
        raise SystemExit("Choose one of the models offered for this render.")
    j = _job(d, job_id)
    store = Store(d)
    made = enqueue(d, [j["shot_id"]], provider, model, {}, j.get("fix_notes") or [], j.get("kind", "video"), j.get("source_job"))
    for m in made:
        store.update(m, retry_of=job_id, retry_note=f"Retried on {pick['label']} after {j['model'].split('/')[-1]} failed.", **({"auto_retried": True} if auto else {}))
    mine = next((x for x in store.jobs if x["id"] == job_id), None)
    if mine:
        store.update(mine, retried_as=made[0]["id"] if made else None)
    return {"queued": [m["id"] for m in made], "jobs": made, "model": model, "provider": provider, "price_usd": pick["price_usd"], "label": pick["label"]}


def due(jobs: list[dict], run_started: int) -> list[dict]:
    """The failed jobs the renderer should look at now: failed during THIS run (an old failure is never retried behind your back when a new render starts), and not looked at already."""
    return [j for j in jobs if j.get("state") == "failed" and not j.get("auto_retry_checked") and (j.get("updated") or 0) >= run_started]


def auto_enabled(d: str) -> bool:
    return bool(((_read(os.path.join(d, "project.json"), {}) or {}).get("routing") or {}).get("auto_retry"))


def after_failure(d: str, store, job: dict) -> str | None:
    """Called by the renderer when a job has failed. With "Retry failed videos on a cheaper model" on, queues the shot once on the cheapest proven model that costs less. Returns what it did."""
    from .render import emit
    if job.get("kind", "video") != "video" or job.get("retry_of") or job.get("retried_as") or not auto_enabled(d):
        return None
    try:
        opts = options(d, job["id"])
    except SystemExit:
        return None
    good = [o for o in opts.get("options", []) if o.get("cheaper") is True]
    if not good:
        return None
    pick = good[0]
    try:
        retry(d, job["id"], pick["provider"], pick["model"], auto=True)
    except SystemExit as e:                                   # the budget or the mode said no: leave the failure as it is
        emit(event="progress", stage=f"not retried on a cheaper model: {e}")
        return None
    emit(event="progress", stage=f"retrying {job['shot_id']} on {pick['label']} (about ${pick['price_usd']:.2f}, cheaper than the model that failed)")
    return pick["label"]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="pulseframe-retrycheap")
    ap.add_argument("action", choices=["options", "retry"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        res = options(a.project, str(x.get("job", ""))) if a.action == "options" else retry(a.project, str(x.get("job", "")), str(x.get("provider", "")), str(x.get("model", "")))
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
