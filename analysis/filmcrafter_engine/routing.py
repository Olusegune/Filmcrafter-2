"""Routing modes and project budgets.

Local First: only what runs on this computer (ComfyUI workflows, the local AI brain, moving stills, export). Cloud
             renders are refused, so nothing is spent and everything works offline.
Balanced:    the cheapest proven cloud models (Wan for video, Nano Banana for stills), Kie before fal.
Premium:     the best proven models (Seedance 2 / Veo for video, GPT Image 2.5 for stills).

A project budget (USD) is enforced when work is queued: a batch that would take the project past it is refused
before anything is sent. Kie credits count at the published rate.

  python -m filmcrafter_engine.routing <action> <project> --data '{...}'   actions: status | set | pick
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys

MODES = {
    "cheapest": {"label": "Cheapest", "blurb": "The lowest real price per shot among proven models on Kie and fal (often Hailuo video, Nano Banana stills)."},
    "hybrid": {"label": "Hybrid", "blurb": "Keyframes on Kie (cheap, and they see your characters), videos free on your ComfyUI."},
    "local": {"label": "Local First", "blurb": "Only this computer: ComfyUI, a local AI model, moving stills. Free and works offline."},
    "balanced": {"label": "Balanced", "blurb": "The cheapest proven cloud models (Wan video, Nano Banana stills)."},
    "premium": {"label": "Premium", "blurb": "The best proven models (Seedance 2 or Veo video, GPT Image 2.5 stills)."},
}
DEFAULT_MODE = "premium"   # what FilmCrafter did before modes existed
# family preference per mode and kind; providers tried in the order given
PREFS = {
    ("balanced", "video"): [("wan", ["kie", "fal"]), ("hailuo", ["kie", "fal"]), ("kling", ["kie", "fal"])],
    ("balanced", "image"): [("nano-banana", ["kie", "fal", "google"])],
    # Kie.ai is the first choice everywhere it has the model: the lowest prices and the widest list (fal and Google follow, for people who prefer them)
    ("premium", "video"): [("seedance", ["kie", "fal"]), ("veo", ["kie", "google", "fal"]), ("kling", ["kie", "fal"])],
    ("premium", "image"): [("gpt-image", ["kie", "openai", "fal"]), ("nano-banana", ["kie", "fal", "google"])],
}
SHOT_SECONDS = 5


def shot_price(provider: str, model: str) -> float | None:
    """Real USD per 5-second shot (video) or per still: Kie from what the model actually cost, fal from its price list."""
    try:
        if provider == "kie":
            from .budget import KIE_USD_PER_CREDIT
            from .render import kie_cost_memory
            c = kie_cost_memory().get(model)
            return round(float(c) * KIE_USD_PER_CREDIT, 3) if c else None
        if provider == "fal":
            from .render import _fal_price
            p = _fal_price(model)
            if not p:
                return None
            unit, up = str(p.get("unit", "")).lower(), float(p.get("unit_price", 0))
            px = 1280 * 720 * 24 * SHOT_SECONDS
            if "second" in unit:
                return round(up * SHOT_SECONDS, 3)
            if "megapixel" in unit:
                return round(up * px / 1e6, 3)
            if "token" in unit:
                return round(px / 1024 / (1000 if "1000" in unit else 1) * up, 3)
            if "minute" in unit:
                return round(up * SHOT_SECONDS / 60, 3)
            if unit.strip() in ("units", "unit"):   # fal's "units" differ per model: don't guess a price
                return None
            return round(up, 3)   # per image / per video
    except Exception:
        return None
    return None


def _cheapest(kind: str, providers: tuple = ("kie", "fal")) -> dict | None:
    from .router import FAMILIES, VERIFIED, available
    best = None
    for fam in FAMILIES.values():
        if fam.get("kind") != kind:
            continue
        for p in providers:
            m = fam.get(p)
            if not m or not available(p) or not VERIFIED.get((p, m)):   # proven models only: cheap must still work
                continue
            usd = shot_price(p, m)
            if usd is not None and (best is None or usd < best["price_usd"]):
                best = {"provider": p, "model": m, "label": fam["label"], "free": False, "verified": True, "price_usd": usd}
    return best


FALLBACK_USD = {"image": 0.25, "video": 1.00, "lipsync": 0.50}   # when a provider publishes no price: assume high, not zero
FALLBACK_BIG_PICTURE_USD = 0.75                                    # a 2K or 4K picture with no price yet (Kie shows its price only after the first one): higher still


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def settings(project: dict) -> dict:
    r = project.get("routing") or {}
    b = r.get("budget_usd")
    return {"mode": r.get("mode") if r.get("mode") in MODES else DEFAULT_MODE,
            "budget_usd": float(b) if isinstance(b, (int, float)) and b > 0 else None, "chosen": bool(r.get("mode"))}


def online(timeout: float = 2.0) -> bool:
    for host in ("api.kie.ai", "fal.run", "api.openai.com"):
        try:
            socket.create_connection((host, 443), timeout=timeout).close()
            return True
        except OSError:
            continue
    return False


def _comfy_flow(kind: str) -> dict | None:
    try:
        from . import comfy
        if not comfy.reachable():
            return None
        return next((w for w in comfy.workflows() if (w.get("kind") or "video") == kind), None)
    except Exception:
        return None


def pick(project: dict, kind: str = "video") -> dict:
    """What 'Auto' renders with in this project's mode: {provider, model, label, free} or {provider: None, reason}."""
    from .router import FAMILIES, VERIFIED, available
    mode = settings(project)["mode"]
    pin = ((project.get("routing") or {}).get("pins") or {}).get(kind if kind in ("image", "video") else "video")
    if pin and mode != "local" and not (mode == "hybrid" and kind == "video") and available(pin.get("provider", "")):
        fam = next((f for f in FAMILIES.values() if f.get(pin["provider"]) == pin["model"]), {})
        return {"provider": pin["provider"], "model": pin["model"], "label": fam.get("label") or pin["model"].split("/")[-1],
                "free": False, "mode": mode, "pinned": True, "verified": bool(VERIFIED.get((pin["provider"], pin["model"]))),
                "price_usd": shot_price(pin["provider"], pin["model"])}
    if mode == "hybrid":
        if kind == "image":   # the cheapest proven Kie image model: it sees the character references
            c = _cheapest("image", providers=("kie",))
            if c:
                return {**c, "mode": mode}
            return {"provider": None, "mode": mode, "free": False, "reason": "Hybrid needs a Kie key for keyframes (Settings → Keys)."}
        w = _comfy_flow("video")
        if w:
            return {"provider": "comfyui", "model": w["model"], "label": w.get("title") or "ComfyUI", "free": True, "mode": mode, "price_usd": 0.0}
        return {"provider": None, "mode": mode, "free": True,
                "reason": "Hybrid renders videos on ComfyUI: start it and press Find ComfyUI in Settings."}
    if mode == "local":
        w = _comfy_flow(kind)
        if w:
            return {"provider": "comfyui", "model": w["model"], "label": w.get("title") or "ComfyUI", "free": True, "mode": mode}
        return {"provider": None, "mode": mode, "free": True,
                "reason": f"Local First: no ComfyUI {kind} workflow is running on this computer. Use moving stills and your own "
                          "media (free), add a workflow in Settings, or switch to Balanced or Premium."}
    k = kind if kind in ("image", "video") else "video"
    if mode == "cheapest":
        c = _cheapest(k)
        if c:
            return {**c, "mode": mode}
        mode = "balanced"   # no priced proven model reachable: fall back to Balanced's order
    for fam, provs in PREFS[(mode, k)]:
        for p in provs:
            m = FAMILIES[fam].get(p)
            if m and available(p):
                return {"provider": p, "model": m, "label": FAMILIES[fam]["label"], "free": False, "mode": settings(project)["mode"],
                        "verified": bool(VERIFIED.get((p, m))), "price_usd": shot_price(p, m)}
    return {"provider": None, "mode": mode, "free": False, "reason": "Add a fal.ai, Kie.ai or OpenAI key in Settings to render."}


def batch_usd(d: str, shot_ids: list[str], provider: str, model: str | None, kind: str) -> float:
    """Estimated USD for a batch; unknown prices count at a deliberately high fallback."""
    if provider == "comfyui":
        return 0.0
    from .budget import KIE_USD_PER_CREDIT
    from .render import estimate
    try:
        e = estimate(d, shot_ids, provider, model, kind if kind != "lipsync" else "video")
    except Exception:
        e = {}
    if provider == "kie" and e.get("kie_credits_est"):
        return round(e["kie_credits_est"] * KIE_USD_PER_CREDIT, 2)
    if e.get("usd") is not None:
        return float(e["usd"])
    each = FALLBACK_BIG_PICTURE_USD if e.get("size_unpriced") else FALLBACK_USD.get(kind, 1.0)
    return round((e.get("usd_known") or 0) + each * (e.get("unknown") or len(shot_ids)), 2)


def pending_usd(d: str) -> float:
    """Queued and in-flight renders not yet counted as spent (they will be)."""
    from .budget import KIE_USD_PER_CREDIT
    from .render import kie_cost_memory
    jobs = _read(os.path.join(d, "jobs.json"), {"jobs": []})["jobs"]
    mem, total = kie_cost_memory(), 0.0
    for j in jobs:
        if j["state"] not in ("queued", "submitting") or j["provider"] in ("comfyui", "own"):
            continue
        if j.get("estimate_usd") is not None:
            total += float(j["estimate_usd"])
        elif j["provider"] == "kie" and mem.get(f"{j['model']}|{j['size_key']}" if j.get("size_key") else j["model"]):
            total += mem[f"{j['model']}|{j['size_key']}" if j.get("size_key") else j["model"]] * KIE_USD_PER_CREDIT      # at the size the job asks for, never the basic size's price
        elif j.get("size_key"):
            total += FALLBACK_BIG_PICTURE_USD
        else:
            total += FALLBACK_USD.get(j.get("kind", "video"), 1.0)
    return round(total, 2)


# A hard ceiling on one batch, whatever the mode or budget say: a loop, a typo or a bad caller cannot queue a film's worth of paid renders in one call.
# It is not a setting. Bigger work goes in several batches, each confirmed on its own (the shell requires a confirmation per batch).
BATCH_MAX_SHOTS = 120
BATCH_MAX_USD = 250.0
BATCH_PRICE_CHECK_FROM = 10   # smaller batches cannot reach the dollar ceiling (one request is never priced above $100), so their price is not looked up here


def guard(d: str, shot_ids: list[str], provider: str, model: str | None, kind: str) -> None:
    """Called before queueing. Raises SystemExit (nothing is sent) when the mode or the budget says no."""
    project = _read(os.path.join(d, "project.json"), {})
    s = settings(project)
    if provider == "comfyui" or not shot_ids:
        return
    if s["mode"] == "local":
        raise SystemExit("Local First is on, so nothing is sent to paid cloud services. Render with ComfyUI, use moving "
                         "stills, or switch this project to Balanced or Premium (Plan & budget).")
    if len(shot_ids) > BATCH_MAX_SHOTS:
        raise SystemExit(f"That is {len(shot_ids)} shots in one batch; the most FilmCrafter will send at once is {BATCH_MAX_SHOTS}. Nothing was sent. Render them in smaller batches.")
    need = batch_usd(d, shot_ids, provider, model, kind) if s["budget_usd"] is not None or len(shot_ids) >= BATCH_PRICE_CHECK_FROM else None
    if need is not None and need > BATCH_MAX_USD + 1e-6:
        raise SystemExit(f"This batch would cost about ${need:.2f}; the most FilmCrafter will send at once is ${BATCH_MAX_USD:.0f}. Nothing was sent. Render fewer shots at a time.")
    if s["budget_usd"] is None:
        return
    from .budget import spent
    used = spent(d)["total_usd"] + pending_usd(d)
    if used + need > s["budget_usd"] + 1e-6:
        raise SystemExit(f"Over budget: this project has spent ${used:.2f} of its ${s['budget_usd']:.2f} budget, and this "
                         f"would add about ${need:.2f}. Nothing was sent. Raise the budget in Plan & budget, or render fewer shots.")


def models(kind: str) -> list[dict]:
    """Every model FilmCrafter knows for this kind on your connected providers, cheapest first, with the real price
    per shot (Kie: what it actually charged; fal: its price list) and whether a real render has proved it here."""
    from .router import FAMILIES, VERIFIED, available
    from .modelblurbs import blurb
    from .modelinfo import sees_pictures
    out = []
    for key, fam in FAMILIES.items():
        if fam.get("kind") != kind:
            continue
        for p in ("kie", "fal", "google", "openai"):
            m = fam.get(p)
            if m and available(p):
                out.append({"label": fam["label"], "provider": p, "model": m, "price_usd": shot_price(p, m),
                            "verified": bool(VERIFIED.get((p, m))), "family": key, **blurb(key),
                            "sees_references": sees_pictures(m, kind) if kind == "image" else None})
    out.sort(key=lambda x: (x["price_usd"] is None, x["price_usd"] or 0, not x["verified"]))
    return out


def consistency(d: str) -> dict:
    """Which picture models made this project's keyframes. Mixed models draw people differently, so more than one (and none pinned) is worth a warning."""
    from .router import FAMILIES
    from .modelblurbs import ONE_MODEL_ADVICE
    jobs = (_read(os.path.join(d, "jobs.json"), {"jobs": []}) or {}).get("jobs", [])
    project = _read(os.path.join(d, "project.json"), {})
    counts: dict[tuple, int] = {}
    for j in jobs:
        if isinstance(j, dict) and j.get("kind") == "image" and j.get("state") == "ready" and j.get("frame", "start") != "end" and not j.get("rejected") and j.get("provider") and j.get("model"):
            counts[(j["provider"], j["model"])] = counts.get((j["provider"], j["model"]), 0) + 1
    used = []
    for (p, m), n in sorted(counts.items(), key=lambda kv: -kv[1]):
        fam = next((f for f in FAMILIES.values() if f.get(p) == m), {})
        used.append({"provider": p, "model": m, "label": fam.get("label") or m.split("/")[-1], "count": n})
    pinned = bool(((project.get("routing") or {}).get("pins") or {}).get("image"))
    return {"image_models": used, "mixed": len(used) > 1, "pinned": pinned, "advice": ONE_MODEL_ADVICE if len(used) > 1 and not pinned else ""}


def status(d: str) -> dict:
    from .budget import spent
    project = _read(os.path.join(d, "project.json"), {})
    s = settings(project)
    used = spent(d)["total_usd"]
    net = online()
    try:
        from .llm import config
        brain = config()
    except Exception:
        brain = {"provider": "openai"}
    return {**s, "modes": [{"id": k, **v} for k, v in MODES.items()], "spent_usd": used,
            "remaining_usd": round(s["budget_usd"] - used, 2) if s["budget_usd"] else None, "online": net,
            "video": pick(project, "video"), "image": pick(project, "image"),
            "pins": (project.get("routing") or {}).get("pins") or {}, "consistency": consistency(d), "auto_retry": bool((project.get("routing") or {}).get("auto_retry")),
            "brain": {"provider": brain["provider"], "local": brain["provider"] != "openai"},
            "works_offline": ["Moving stills and your own media", "Transitions, camera moves, acting micro-motion",
                              "Continuity rules", "Export"] + (["The AI brain (local model)"] if brain["provider"] != "openai" else [])
            + (["ComfyUI renders"] if _comfy_flow("video") or _comfy_flow("image") else [])}


def set_(d: str, data: dict) -> dict:
    path = os.path.join(d, "project.json")
    p = _read(path, {})
    r = dict(p.get("routing") or {})
    if "mode" in data:
        if data["mode"] not in MODES:
            raise SystemExit("Choose Cheapest, Hybrid, Local First, Balanced or Premium.")
        r["mode"] = data["mode"]
    if "pin" in data:   # {"kind": "video"|"image", "provider": ..., "model": ...} or {"kind": ..., "clear": true}
        pins = dict(r.get("pins") or {})
        x = data["pin"] or {}
        if x.get("kind") not in ("image", "video"):
            raise SystemExit("Pin a video or a keyframe model.")
        if x.get("clear"):
            pins.pop(x["kind"], None)
        else:
            from .router import FAMILIES
            if not any(f.get(x.get("provider")) == x.get("model") and f.get("kind") == x["kind"] for f in FAMILIES.values()):
                raise SystemExit("That model isn't in FilmCrafter's list for this kind.")
            pins[x["kind"]] = {"provider": x["provider"], "model": x["model"]}
        r["pins"] = pins
    if "auto_retry" in data:   # retry failed videos on a cheaper proven model without asking (retrycheap.py)
        if data["auto_retry"]:
            r["auto_retry"] = True
        else:
            r.pop("auto_retry", None)
    if "budget_usd" in data:
        b = data["budget_usd"]
        if b in (None, "", 0):
            r.pop("budget_usd", None)
        else:
            try:
                b = round(float(b), 2)
            except (TypeError, ValueError):
                raise SystemExit("Enter the budget in dollars, e.g. 25.")
            if b <= 0 or b > 100000:
                raise SystemExit("Enter a budget between $0.01 and $100,000, or leave it empty for none.")
            r["budget_usd"] = b
    p = _read(path, {})
    p["routing"] = r
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return status(d)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-routing")
    ap.add_argument("action", choices=["status", "set", "pick", "models"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "status":
            res = status(a.project)
        elif a.action == "set":
            res = set_(a.project, x)
        elif a.action == "models":
            from .modelblurbs import ONE_MODEL_ADVICE
            res = {"video": models("video"), "image": models("image"), "advice": ONE_MODEL_ADVICE}
        else:
            res = pick(_read(os.path.join(a.project, "project.json"), {}), x.get("kind", "video"))
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
