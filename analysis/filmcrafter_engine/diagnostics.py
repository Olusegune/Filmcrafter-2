"""Provider diagnostics: is each provider usable right now, and what really happened last time?

Free checks only (no generation is ever sent): key present, a signed-in read (models list or balance),
and the real job history across projects. Keys are never printed or returned.

  python -m filmcrafter_engine.diagnostics run <projects_root>
"""
from __future__ import annotations

import glob
import json
import os
import sys

import requests

from .render import ERROR_KINDS, classify_error

UA = {"User-Agent": "FilmCrafter"}
KEY_VARS = {"openai": "FILMCRAFTER_OPENAI_KEY", "fal": "FAL_KEY", "kie": "KIE_KEY", "google": "GEMINI_API_KEY", "byteplus": "BYTEPLUS_KEY"}
NAMES = {"openai": "OpenAI", "fal": "fal", "kie": "Kie", "google": "Google (Veo, Nano Banana)", "byteplus": "BytePlus (Seedream)"}

RECOVERY = {
    "no_key": "Add the key in Settings → Keys.",
    "auth": "The key was refused. Paste a fresh key from the provider's dashboard in Settings → Keys.",
    "credits": "Top up this provider's balance, or move queued work to another provider (Autopilot offers this).",
    "unavailable": "The model isn't offered to this account. Pick another model for the shot.",
    "rate_limit": "Wait a minute and retry; FilmCrafter retries automatically.",
    "invalid": "The provider rejected the settings. Re-make the shot with default settings, and report it if it repeats.",
    "policy": "Reword the shot; the provider's content filter blocked it.",
    "timeout": "Check the internet connection, then retry.",
    "service": "The provider had a problem on its side. Retry later.",
    "download": "Retry the download from the take's menu; the render itself was paid for and finished.",
    "missing_input": "Give the shot the input it needs (usually an approved keyframe).",
    "offline": "FilmCrafter couldn't reach the provider. Check the internet connection.",
    "expired_input": "Retry the render: FilmCrafter uploads the reference images again.",
}


def _probe(provider: str, key: str) -> tuple[str, str, int | None]:
    """(status, message, http_status) from a free signed-in request."""
    try:
        if provider == "openai":
            r = requests.get("https://api.openai.com/v1/models", headers={**UA, "Authorization": f"Bearer {key}"}, timeout=15)
            if r.ok:
                ids = {m["id"] for m in r.json().get("data", [])}
                img = sorted(i for i in ids if i.startswith("gpt-image"))
                return "ok", f"Signed in. Image models on this account: {', '.join(img) or 'none listed'}.", 200
        elif provider == "fal":
            r = requests.get("https://rest.fal.ai/billing/user_balance", headers={**UA, "Authorization": f"Key {key}"}, timeout=15)
            if r.ok:
                return "ok", f"Signed in. Balance reported: {float(r.text.strip()):.2f} USD.", 200
        elif provider == "kie":
            r = requests.get("https://api.kie.ai/api/v1/chat/credit", headers={**UA, "Authorization": f"Bearer {key}"}, timeout=15)
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.ok and isinstance(body.get("data"), (int, float)):
                return "ok", f"Signed in. {body['data']:,.0f} credits.", 200
            if r.ok:   # Kie answers 200 with its own code for a bad key
                return "error", str(body.get("msg") or body)[:300], body.get("code")
        elif provider == "google":
            r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", headers={**UA, "x-goog-api-key": key}, timeout=15)
            if r.ok:
                ids = [m["name"].split("/")[-1] for m in r.json().get("models", [])]
                veo = [i for i in ids if "veo" in i or "image" in i]
                return "ok", f"Signed in. {len(ids)} models; video/image: {', '.join(veo[:6]) or 'none listed'}.", 200
        elif provider == "byteplus":       # BytePlus has no free request that proves a key, and a picture is the only call that can be billed: the first picture tests it
            return "unchecked", "Saved. BytePlus has no free key check; the first picture tests it.", None
        else:
            return "error", "Unknown provider.", None
        return "error", (r.text or r.reason)[:300], r.status_code
    except requests.RequestException as e:
        return "offline", f"{type(e).__name__}", None


def history(root: str, extra: list[str] | None = None) -> dict:
    """Per provider: real finished and failed jobs across all projects (the projects folder plus recent ones)."""
    out: dict[str, dict] = {}
    files = glob.glob(os.path.join(root, "*", "jobs.json")) + [os.path.join(x, "jobs.json") for x in extra or []]
    seen = set()
    for f in files:
        key = os.path.normcase(os.path.abspath(f))
        if key in seen or not os.path.exists(f):
            continue
        seen.add(key)
        try:
            jobs = json.load(open(f, encoding="utf-8")).get("jobs", [])
        except (OSError, ValueError):
            continue
        project = os.path.basename(os.path.dirname(f))
        for j in jobs:
            h = out.setdefault(j.get("provider", "?"), {"ready": 0, "failed": 0, "last_ok": None, "last_fail": None})
            stamp = j.get("updated") or j.get("created") or 0
            row = {"project": project, "shot": j.get("shot_id"), "model": j.get("model"), "kind": j.get("kind", "video"), "at": stamp}
            if j.get("state") == "ready":
                h["ready"] += 1
                if not h["last_ok"] or stamp > h["last_ok"]["at"]:
                    h["last_ok"] = row
            elif j.get("state") == "failed":
                h["failed"] += 1
                if not h["last_fail"] or stamp > h["last_fail"]["at"]:
                    kind = j.get("error_kind") or classify_error(j.get("error") or "")
                    h["last_fail"] = {**row, "error_kind": kind, "error": (j.get("error") or "")[:300],
                                      "recovery": RECOVERY.get(kind, RECOVERY["service"])}
    return out


def run(root: str | None, extra: list[str] | None = None) -> dict:
    hist = history(root, extra) if root else {}
    rows = []
    for p, var in KEY_VARS.items():
        key = os.environ.get(var)
        h = hist.get(p) or {"ready": 0, "failed": 0, "last_ok": None, "last_fail": None}
        if not key:
            status, msg, kind = "unavailable", "No key saved.", "no_key"
        else:
            st, msg, code = _probe(p, key)
            kind = None if st in ("ok", "unchecked") else ("offline" if st == "offline" else classify_error(msg, code if isinstance(code, int) else None))
            # verified = signed in now AND at least one real render finished; mocked tests never count
            status = "unavailable" if kind in ("auth", "offline") else ("verified" if st in ("ok", "unchecked") and h["ready"] else
                                                                         "blocked" if kind == "credits" else "unverified")
        rows.append({"provider": p, "name": NAMES[p], "status": status, "message": msg,
                     "error_kind": kind, "explanation": ERROR_KINDS.get(kind or "", ""),
                     "recovery": RECOVERY.get(kind) if kind else None, "history": h})
    return {"providers": rows}


def main(argv: list[str]) -> int:
    try:
        root = argv[1] if len(argv) > 1 else None
        print(json.dumps({"event": "result", "data": run(root, argv[2:])}), flush=True)
        return 0
    except Exception as e:
        print(json.dumps({"event": "error", "message": f"{type(e).__name__}: {e}"}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
