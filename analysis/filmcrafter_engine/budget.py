"""Budget guard: provider balances, what this project has spent, and whether a batch fits.

  python -m filmcrafter_engine.budget status <project> [--need '{"fal": 4.05, "kie": 0}']
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import requests

KIE_USD_PER_CREDIT = 0.005   # Kie's published rate (1,000 credits ≈ $5); used only to show a rough dollar figure
UA = {"User-Agent": "FilmCrafter"}


def balance(provider: str) -> dict:
    """{"provider", "amount", "unit", "known"} — unknown (known=False) when the provider doesn't say."""
    try:
        if provider == "fal" and os.environ.get("FAL_KEY"):
            r = requests.get("https://rest.fal.ai/billing/user_balance", headers={**UA, "Authorization": f"Key {os.environ['FAL_KEY']}"}, timeout=15)
            if r.status_code == 200:
                return {"provider": "fal", "amount": round(float(r.text.strip()), 2), "unit": "usd", "known": True}
        if provider == "kie" and os.environ.get("KIE_KEY"):
            r = requests.get("https://api.kie.ai/api/v1/chat/credit", headers={**UA, "Authorization": f"Bearer {os.environ['KIE_KEY']}"}, timeout=15)
            if r.status_code == 200 and isinstance(r.json().get("data"), (int, float)):
                return {"provider": "kie", "amount": float(r.json()["data"]), "unit": "credits", "known": True,
                        "usd": round(float(r.json()["data"]) * KIE_USD_PER_CREDIT, 2)}
    except (requests.RequestException, ValueError):
        pass
    return {"provider": provider, "amount": None, "unit": None, "known": False}


def spent(d: str) -> dict:
    """What this project has cost so far, per provider (fal: estimated USD; Kie: credits billed; others: counts)."""
    try:
        jobs = json.load(open(os.path.join(d, "jobs.json"), encoding="utf-8"))["jobs"]
    except (OSError, ValueError):
        jobs = []
    out = {"fal_usd": 0.0, "kie_credits": 0.0, "openai_images": 0, "google_jobs": 0, "renders": 0}
    for j in jobs:
        if j["state"] not in ("ready", "submitted"):   # refused/failed-before-sending jobs cost nothing
            continue
        out["renders"] += 1
        if j["provider"] == "fal":
            out["fal_usd"] += float(j.get("estimate_usd") or 0)
        elif j["provider"] == "kie":
            out["kie_credits"] += float(j.get("cost") or 0)
        elif j["provider"] == "openai":
            out["openai_images"] += 1
        elif j["provider"] == "google":
            out["google_jobs"] += 1
    out["fal_usd"] = round(out["fal_usd"], 2)
    out["kie_usd"] = round(out["kie_credits"] * KIE_USD_PER_CREDIT, 2)
    out["total_usd"] = round(out["fal_usd"] + out["kie_usd"], 2)
    return out


def fits(need: dict, balances: dict) -> dict:
    """Per provider: does the estimated need fit the balance? need is USD (fal) or credits (kie)."""
    verdict = {}
    for p, amount in (need or {}).items():
        b = balances.get(p) or {}
        if not b.get("known") or amount is None:
            verdict[p] = {"fits": None, "reason": "balance unknown"}
        elif b["amount"] <= 0 and p == "fal":
            # fal's billing figure isn't documented: it has accepted work while negative, so warn, don't block
            verdict[p] = {"fits": None, "reason": f"fal reports {b['amount']} USD. Renders may be refused; if they are, "
                                                  "FilmCrafter pauses them uncharged and offers Kie."}
        elif b["amount"] <= 0:
            verdict[p] = {"fits": False, "reason": f"{p} balance is {b['amount']} {b['unit']}; top up first"}
        else:
            verdict[p] = {"fits": b["amount"] >= amount, "short": round(max(0.0, amount - b["amount"]), 2)}
    return verdict


def status(d: str | None, need: dict | None = None) -> dict:
    bal = {p: balance(p) for p in ("fal", "kie")}
    return {"balances": bal, "spent": spent(d) if d else None, "fits": fits(need or {}, bal)}


def reroute(d: str, provider: str, to: str | None = None) -> dict:
    """Move this provider's queued (not yet sent, so unbilled) jobs to the same model family elsewhere."""
    from .render import Store, enqueue
    from .router import equivalent
    store = Store(d)
    moved, stuck = [], []
    for j in [x for x in store.jobs if x["provider"] == provider and x["state"] == "queued"]:
        alt = equivalent(provider, j["model"], j.get("kind", "video"), to)
        if not alt:
            stuck.append(j["shot_id"]); continue
        store.update(j, state="dismissed", error=f"Moved to {alt['provider']} ({alt['label']}) by the budget guard.")
        made = enqueue(d, [j["shot_id"]], alt["provider"], alt["model"], {} if not alt["same_family"] else j.get("overrides") or {},
                       j.get("fix_notes") or [], j.get("kind", "video"), j.get("source_job"))
        moved += [{"shot": j["shot_id"], "to": alt["provider"], "model": alt["model"], "same_family": alt["same_family"]} for _ in made]
    return {"moved": moved, "stuck": stuck}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-budget")
    ap.add_argument("action", choices=["status", "reroute"])
    ap.add_argument("--provider")
    ap.add_argument("--to")
    ap.add_argument("project", nargs="?")
    ap.add_argument("--need", default="{}")
    a = ap.parse_args(argv)
    try:
        res = status(a.project, json.loads(a.need)) if a.action == "status" else reroute(a.project, a.provider, a.to)
        print(json.dumps({"event": "result", "data": res}), flush=True)
        return 0
    except Exception as e:
        print(json.dumps({"event": "error", "message": f"{type(e).__name__}: {e}"}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
