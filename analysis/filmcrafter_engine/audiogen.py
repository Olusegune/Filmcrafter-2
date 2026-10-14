"""Making sound effects and music with an AI provider, safely: price first, one yes, every call in the film's ledger, nothing made twice, nothing assumed about the rights.

Providers (checked against their documentation on 2026-10-14; see docs/CREATIVE_PRODUCTION_EXPANSION.md for what was and was not verified):
  elevenlabs_sfx    ElevenLabs sound effects   POST /v1/sound-generation        text, duration_seconds 0.5 to 30 (or the model chooses), prompt_influence 0 to 1, loop (v2 model only)
                    cost: ElevenLabs' help centre says 11 credits per second for a set duration, 100 per generation when it chooses: shown as an estimate, never as what was charged
  elevenlabs_music  ElevenLabs Music           POST /v1/music                   prompt, music_length_ms 3000 to 600000, model_id, force_instrumental
                    cost: not published on the API page: the person must accept that it is unknown
  kie_suno          Suno through Kie.ai        POST /api/v1/jobs/createTask     model ai-music-api/generate, input{custom_mode, instrumental, model V6, prompt}; result by GET /api/v1/jobs/recordInfo
                    cost: not published: unknown. Kie keeps the files 14 days, so they are downloaded at once. (The reply format of this adapter follows the documentation and has not been run live.)
Suno has no official public API of its own: only the gateway above is offered, and only because the person asked for it.

Rights: none of the three providers' terms were found to grant commercial use of the output in a way FilmCrafter could verify (ElevenLabs Music's terms depend on the plan and have changed; Kie's say nothing).
So everything made here is saved with "commercial use: not known", generation asks the person to acknowledge that, and `audiolib.rights_report` lists anything unconfirmed that the film's plan uses.

Reuse: a sound made once is kept in the film's library with the exact settings that made it (`generation.key`); asking for the same thing again returns that sound and costs nothing. A variation is a
different request (its own number) and a new sound; earlier ones are never replaced.

  python -m filmcrafter_engine.audiogen <providers|estimate|generate|pending|check> <film_dir> --data '{...}'
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time

from . import audiolib as AL
from . import paidops as P
from . import safeio

ELEVEN = "https://api.elevenlabs.io"
KIE = "https://api.kie.ai"
CHECKED = "2026-10-14"
SFX_MIN, SFX_MAX = 0.5, 30.0
MUSIC_MIN_S, MUSIC_MAX_S = 3.0, 600.0
PROMPT_MAX = 1000
KIE_PROMPT_MAX = 3000
POLL_EVERY, POLL_FOR = 5, 360
MAX_DOWNLOAD = 60 * 1024 * 1024
ELEVEN_UNIT = "elevenlabs_credits"
KIE_UNIT = "kie_credits"

RIGHTS_NOTE = (f"Commercial rights for sound made this way were not established when it was made (checked {CHECKED}). "
               "Treat it as a draft until you have confirmed the provider's terms for your plan and use.")

PROVIDERS = {
    "elevenlabs_sfx": {"label": "ElevenLabs sound effects", "short": "ElevenLabs", "kind": "sfx", "provider": "elevenlabs", "unit": ELEVEN_UNIT, "model": "eleven_text_to_sound_v2", "cost_known": True,
                       "duration": [SFX_MIN, SFX_MAX], "loop": True, "variations": True, "instrumental": False, "key": "ELEVENLABS_KEY",
                       "cost_words": "about 11 credits per second you ask for, or about 100 credits when the length is left to the model (ElevenLabs' own figures for API use)",
                       "rights": "not_established"},
    "elevenlabs_music": {"label": "ElevenLabs Music", "short": "ElevenLabs", "kind": "music", "provider": "elevenlabs", "unit": ELEVEN_UNIT, "model": "music_v1", "cost_known": False,
                         "duration": [MUSIC_MIN_S, MUSIC_MAX_S], "loop": False, "variations": True, "instrumental": True, "key": "ELEVENLABS_KEY",
                         "cost_words": "ElevenLabs does not publish what a piece of music uses of your plan", "rights": "not_established"},
    "kie_suno": {"label": "Suno through Kie.ai", "short": "Kie.ai", "kind": "music", "provider": "kie", "unit": KIE_UNIT, "model": "V6", "cost_known": False, "duration": None, "loop": False,
                 "variations": True, "instrumental": True, "key": "KIE_KEY", "cost_words": "Kie.ai does not publish what a piece of music costs in credits (it reports the credits afterwards)", "rights": "not_established"},
}


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


def _text(v, limit: int = PROMPT_MAX) -> str:
    return " ".join(str(v if v is not None else "").replace("\x00", "").split())[:limit]


# ---------------------------------------------------------------- the provider calls (each one a single function so tests, and any future change, touch one place)

def _eleven_headers(accept: str) -> dict:
    from . import cast_voice as C
    return C._headers(accept)


def _eleven_post(path: str, accept: str = "audio/mpeg", timeout: int = 300, **kw):
    import requests
    return requests.post(f"{ELEVEN}{path}", headers=_eleven_headers(accept), timeout=timeout, **kw)


def _kie_headers() -> dict:
    key = os.environ.get("KIE_KEY")
    if not key:
        raise SystemExit("Add your Kie.ai key in Settings to make music with Suno through Kie.ai.")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _kie_post(path: str, **kw):
    import requests
    return requests.post(f"{KIE}{path}", headers=_kie_headers(), timeout=60, **kw)


def _kie_get(path: str, **kw):
    import requests
    return requests.get(f"{KIE}{path}", headers=_kie_headers(), timeout=60, **kw)


def _download(url: str) -> bytes:
    """One audio file from the address a provider gave us: https only, never a local or numeric address, size-limited."""
    import requests
    from urllib.parse import urlparse
    u = urlparse(str(url))
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host or host in ("localhost",) or host.replace(".", "").isdigit() or host.endswith(".local") or u.username:
        raise SystemExit("The provider gave an address FilmCrafter does not trust, so the file was not fetched.")
    r = requests.get(url, timeout=120, stream=True, allow_redirects=True)
    if not r.ok:
        raise SystemExit(f"The finished file could not be fetched (HTTP {r.status_code}).")
    data = b""
    for chunk in r.iter_content(65536):
        data += chunk
        if len(data) > MAX_DOWNLOAD:
            raise SystemExit("The finished file is larger than expected, so it was not kept.")
    return data


class _Reply:
    """A provider answer in the one shape the paid-operation runner reads (Kie answers HTTP 200 with its own status code inside)."""

    def __init__(self, status: int, body: dict | None, headers: dict | None = None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.ok = status < 400
        self.text = json.dumps(body)[:400] if body is not None else ""
        self.content = b""

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def _kie_reply(r) -> _Reply:
    try:
        body = r.json()
    except ValueError:
        body = None
    code = int(body.get("code", r.status_code)) if isinstance(body, dict) and str(body.get("code", "")).lstrip("-").isdigit() else r.status_code
    return _Reply(code if code >= 100 else r.status_code, body, getattr(r, "headers", None))


# ---------------------------------------------------------------- the rules for paying (the same as the voice tools: paidops)

def _ledger(d: str) -> P.Ledger:
    from . import cast_voice as C
    return C._ledger(d)


def _said(r) -> str:
    try:
        j = r.json()
        det = j.get("detail") if isinstance(j, dict) else None
        if isinstance(det, dict):
            return str(det.get("message") or det.get("status") or "")[:200]
        if isinstance(det, list) and det:
            return str(det[0].get("msg") or "")[:200]
        if isinstance(j, dict):
            return str(j.get("msg") or j.get("message") or det or "")[:200]
    except (ValueError, AttributeError):
        pass
    return ""


def _paid(d: str, spec: dict, *, action: str, area: str, key: str, estimate: dict, confirmed, unknown_ok, rights_ok, send, what: str):
    """One request that can use the person's plan or credits. Returns (reply, ledger entry). Raises SystemExit with plain words and leaves the ledger saying exactly how far it got."""
    label = spec["short"]
    L = _ledger(d)
    try:
        P.require_authorised(confirmed, what)
        if not spec["cost_known"]:
            P.require_accepted_unknown_cost(unknown_ok, what)
        if rights_ok is not True:
            raise SystemExit(f"Whether you may use {spec['label']} output in a released film is not established. To go ahead, confirm that you understand it is saved as 'commercial use: not known' "
                             "and that you will check the provider's terms before you release anything made with it. Nothing was sent.")
    except SystemExit as e:
        L.refused_record(provider=spec["provider"], area=area, action=action, reason=str(e), key=key)
        raise
    L.reconcile()
    op = L.begin(key=key, provider=spec["provider"], area=area, action=action, estimate=estimate)
    tries = 0
    while True:
        tries += 1
        L.mark(op["id"], P.SUBMITTED)
        try:
            r = send()
        except SystemExit:
            L.mark(op["id"], P.FAILED_BEFORE, note="Stopped before anything was sent.")
            raise
        except Exception as e:
            if P.classify_transport(e) == P.NOT_SENT:
                if tries <= 2:
                    L.mark(op["id"], P.CONFIRMED, note="Could not connect; trying again.")
                    time.sleep(2 * tries)
                    continue
                L.mark(op["id"], P.FAILED_BEFORE, note=f"Could not connect ({type(e).__name__}). Nothing was sent.")
                raise SystemExit(f"Could not reach {label}. Nothing was sent, so nothing was charged. Check your connection and try again.")
            L.mark(op["id"], P.UNCERTAIN, note=f"{type(e).__name__} while waiting for {label}'s answer.")
            raise SystemExit(f"{label} did not say whether it completed the request to {what}. It may or may not have used your plan. FilmCrafter has NOT sent it again. "
                             "Check your usage history there, then mark it 'not charged' or 'charged' in the usage list.")
        code = r.status_code
        rid = next((str(r.headers.get(k)) for k in ("request-id", "x-request-id") if r.headers.get(k)), None) if getattr(r, "headers", None) else None
        if r.ok:
            return r, op
        if code == 429:
            if tries <= 2:
                L.mark(op["id"], P.CONFIRMED, note=f"{label} asked us to slow down; trying again shortly.")
                time.sleep(2 * tries)
                continue
            L.mark(op["id"], P.REFUSED, provider_request_id=rid, note=f"{label} is busy.")
            raise SystemExit(f"{label} says it is too busy right now. Nothing was charged. Try again in a minute.")
        if 400 <= code < 500 and code != 408:
            said = _said(r)
            if code == 402:
                said = said or "not enough credits"
            L.mark(op["id"], P.REFUSED, provider_request_id=rid, note=(said or f"HTTP {code}")[:300])
            raise SystemExit(f"{label} refused the request{f': {said}' if said else f' (HTTP {code})'}. Nothing was charged.")
        L.mark(op["id"], P.UNCERTAIN, provider_request_id=rid, note=f"{label} answered HTTP {code}; it may or may not have done the work.")
        raise SystemExit(f"{label} answered with an error (HTTP {code}) and did not say whether it did the work. It may or may not have used your plan. FilmCrafter has NOT sent it again. "
                         "Check your usage history there, then mark it 'not charged' or 'charged' in the usage list.")


# ---------------------------------------------------------------- what is asked for

def providers() -> dict:
    """What can be made, by whom, what it would cost (in words), and what is known about the rights. Whether a key is present is all that is read of any key."""
    out = []
    for pid, s in PROVIDERS.items():
        out.append({"id": pid, "label": s["label"], "kind": s["kind"], "cost_known": s["cost_known"], "cost_words": s["cost_words"], "duration": s["duration"], "loop": s["loop"],
                    "instrumental": s["instrumental"], "has_key": bool(os.environ.get(s["key"])), "rights": s["rights"], "rights_note": RIGHTS_NOTE, "checked": CHECKED})
    return {"providers": out}


def _clean(p: dict) -> tuple[dict, dict]:
    pid = str(p.get("provider") or "")
    spec = PROVIDERS.get(pid)
    if not spec:
        raise SystemExit("Choose how to make it: sound effects or music.")
    prompt = _text(p.get("prompt"), KIE_PROMPT_MAX if pid == "kie_suno" else PROMPT_MAX)
    if len(prompt) < 3:
        raise SystemExit("Describe what you want to hear, in a few words.")
    limit = KIE_PROMPT_MAX if pid == "kie_suno" else PROMPT_MAX
    if len(" ".join(str(p.get("prompt") or "").split())) > limit:
        raise SystemExit(f"That description is longer than {limit} characters.")
    c = {"provider": pid, "prompt": prompt, "variation": max(0, min(int(p.get("variation") or 0), 99)), "model": spec["model"]}
    dur = p.get("duration")
    if dur not in (None, "", 0):
        try:
            dur = float(dur)
        except (TypeError, ValueError):
            raise SystemExit("The length must be a number of seconds.")
        lo, hi = spec["duration"] or (None, None)
        if lo is None:
            raise SystemExit("This provider chooses the length of the music.")
        if not (lo <= dur <= hi):
            raise SystemExit(f"The length must be between {lo:g} and {hi:g} seconds.")
        c["duration"] = round(dur, 2)
    if spec["loop"] and p.get("loop"):
        c["loop"] = True
    if spec["kind"] == "sfx" and p.get("influence") not in (None, ""):
        try:
            inf = float(p["influence"])
        except (TypeError, ValueError):
            raise SystemExit("How closely to follow the description is a number from 0 to 1.")
        if not (0 <= inf <= 1):
            raise SystemExit("How closely to follow the description is a number from 0 to 1.")
        c["influence"] = round(inf, 2)
    if spec["instrumental"]:
        c["instrumental"] = bool(p.get("instrumental", True))
    if pid == "elevenlabs_music" and p.get("model") in ("music_v1", "music_v2", "music_v2_5"):
        c["model"] = p["model"]
    return c, spec


def gen_key(c: dict) -> str:
    return hashlib.sha1(json.dumps(c, sort_keys=True).encode("utf-8"), usedforsecurity=False).hexdigest()[:20]


def find_made(d: str, key: str) -> dict | None:
    for a in AL.load(d)["assets"]:
        if (a.get("generation") or {}).get("key") == key:
            return a
    return None


def _estimate_of(spec: dict, c: dict) -> dict:
    """`amount` is the safe upper figure (the one a spending limit is checked against); `expected` is what earlier sounds really cost on this account, when that is known."""
    if c["provider"] == "elevenlabs_sfx":
        if c.get("duration"):
            top = round(c["duration"] * 11)
            from . import registry
            seen = registry.observed("elevenlabs_sfx_per_second")
            if seen and seen[0] < 11 * 0.9:
                exp = round(c["duration"] * seen[0])
                return {"unit": ELEVEN_UNIT, "amount": top, "expected": exp, "basis": f"about {exp} credits: your last {seen[1]} sounds cost about {seen[0]:g} credits per second (ElevenLabs' own figure is 11, so at most {top}). An estimate"}
            return {"unit": ELEVEN_UNIT, "amount": top, "basis": f"about 11 credits per second x {c['duration']:g} s (ElevenLabs' figure for API use; an estimate)"}
        return {"unit": ELEVEN_UNIT, "amount": 100, "basis": "about 100 credits when the model chooses the length (ElevenLabs' figure for API use; an estimate)"}
    return {"unit": spec["unit"], "amount": None, "basis": spec["cost_words"]}


def estimate(d: str, params: dict) -> dict:
    """What making this would cost (as words and, where the provider publishes it, an estimate), whether it is already in the library (then it is free), and what must be confirmed. Free; sends nothing."""
    AL._film(d)
    c, spec = _clean(params)
    key = gen_key(c)
    made = find_made(d, key)
    est = _estimate_of(spec, c)
    return {"provider": c["provider"], "label": spec["label"], "kind": spec["kind"], "key": key, "cached": made["id"] if made else None, "unit": est["unit"], "amount": 0 if made else est["amount"],
            "expected": None if made else est.get("expected"),
            "basis": "Already in the library: free." if made else est["basis"], "cost_known": spec["cost_known"], "needs_unknown_cost_accepted": (not spec["cost_known"]) and not made,
            "needs_rights_ack": not made, "rights_note": RIGHTS_NOTE, "has_key": bool(os.environ.get(spec["key"])), "params": c}


# ---------------------------------------------------------------- making it

def _name_of(c: dict, given: str | None) -> str:
    n = _text(given, 80) or _text(c["prompt"], 48)
    return n + (f" ({c['variation'] + 1})" if c["variation"] else "")


def _save(d: str, spec: dict, c: dict, key: str, data: bytes, ext: str, op: dict, name: str | None, category: str | None, links: dict, extra: dict | None = None) -> dict:
    """Check the bytes really are audio, then put them in the library with how they were made and what is known about the rights."""
    with tempfile.TemporaryDirectory() as td:
        tmp = os.path.join(td, f"made{ext}")
        with open(tmp, "wb") as f:
            f.write(data)
        gen = {"provider": c["provider"], "model": c["model"], "prompt": c["prompt"], "key": key, "variation": c["variation"], "made": int(time.time()), "ledger": op["id"],
               **{k: c[k] for k in ("duration", "loop", "influence", "instrumental") if k in c}, **(extra or {})}
        lic = {"source": f"Generated with {spec['label']}", "note": RIGHTS_NOTE, "commercial": "unknown"}
        r = AL.add_file(d, spec["kind"], tmp, category=category or ("custom"), source="generated", name=_name_of(c, name), description=c["prompt"], generation=gen, licence=lic, dedupe=False)
    if "asset" not in r:
        raise SystemExit(f"{spec['label']} sent something that is not playable audio ({r['skipped']}). It is not kept.")
    asset = r["asset"]
    if any(links.get(k) for k in ("places", "scenes", "props", "characters", "shots")):
        asset = next(a for a in AL.update(d, asset["id"], {k: links[k] for k in ("places", "scenes", "props", "characters", "shots") if links.get(k)})["assets"] if a["id"] == asset["id"])
    return asset


def _guard(provider: str, model: str, params: dict) -> None:
    """Never send a parameter the model is not known to take (the registry lists each one's inputs)."""
    from . import registry
    probs = registry.check_params(provider, model, params)
    if probs:
        raise SystemExit("Not sent (nothing was charged). " + " ".join(probs))


def generate(d: str, params: dict, confirmed=False, unknown_cost_accepted=False, rights_ack=False) -> dict:
    """Make a sound or music with a provider and keep it in the film's library. Free (and instant) when the same thing was made before. Otherwise it needs `confirmed`, `rights_ack`, and, when the
    cost is unknown, `unknown_cost_accepted`; it is recorded in the ledger before anything is sent; it is never retried when the outcome is unclear."""
    AL._film(d)
    c, spec = _clean(params)
    key = gen_key(c)
    made = find_made(d, key)
    if made:
        return {"asset": made, "cached": True, "cost": {"unit": spec["unit"], "amount": 0}, "note": "Already in the library: nothing was sent and nothing was charged."}
    est = _estimate_of(spec, c)
    links = {k: AL._list(params.get(k)) for k in ("places", "scenes", "props", "characters", "shots")}
    name, category = params.get("name"), params.get("category")
    if c["provider"] == "elevenlabs_sfx":
        body = {"text": c["prompt"], "model_id": spec["model"]}
        if c.get("duration"):
            body["duration_seconds"] = c["duration"]
        if "influence" in c:
            body["prompt_influence"] = c["influence"]
        if c.get("loop"):
            body["loop"] = True
        _guard("elevenlabs", spec["model"], body)
        r, op = _paid(d, spec, action="sfx", area="sound", key=P.op_key("sfx", key), estimate=est, confirmed=confirmed, unknown_ok=unknown_cost_accepted, rights_ok=rights_ack,
                      what="make that sound", send=lambda: _eleven_post("/v1/sound-generation", accept="audio/mpeg", params={"output_format": "mp3_44100_128"}, json=body))
        return _finish_audio(d, spec, c, key, r, op, name, category or "foley", links, est)
    if c["provider"] == "elevenlabs_music":
        body = {"prompt": c["prompt"], "model_id": c["model"], "force_instrumental": bool(c.get("instrumental"))}
        if c.get("duration"):
            body["music_length_ms"] = int(c["duration"] * 1000)
        _guard("elevenlabs", c["model"], body)
        r, op = _paid(d, spec, action="music", area="music", key=P.op_key("music", key), estimate=est, confirmed=confirmed, unknown_ok=unknown_cost_accepted, rights_ok=rights_ack,
                      what="make that music", send=lambda: _eleven_post("/v1/music", accept="audio/mpeg", timeout=600, params={"output_format": "mp3_44100_128"}, json=body))
        return _finish_audio(d, spec, c, key, r, op, name, category or "cue", links, est)
    body = {"model": "ai-music-api/generate", "input": {"custom_mode": False, "instrumental": bool(c.get("instrumental")), "model": c["model"], "prompt": c["prompt"]}}
    _guard("kie", "ai-music-api/generate", body["input"])
    r, op = _paid(d, spec, action="music", area="music", key=P.op_key("music", key), estimate=est, confirmed=confirmed, unknown_ok=unknown_cost_accepted, rights_ok=rights_ack,
                  what="make that music", send=lambda: _kie_reply(_kie_post("/api/v1/jobs/createTask", json=body)))
    task = str(((r.json() or {}).get("data") or {}).get("taskId") or "")
    if not task:
        _ledger(d).mark(op["id"], P.UNCERTAIN, note="Kie.ai accepted the request but gave no task number.")
        raise SystemExit("Kie.ai accepted the request but did not give a task number, so the result cannot be fetched. It may have used your credits. FilmCrafter has NOT sent it again.")
    _ledger(d).complete(op["id"], request_id=task)
    pend = {"task": task, "provider": c["provider"], "params": c, "key": key, "ledger": op["id"], "name": name, "category": category or "cue", "links": links, "at": int(time.time())}
    _pending_add(d, pend)
    return _poll_and_save(d, pend, wait=True)


def _finish_audio(d: str, spec: dict, c: dict, key: str, r, op: dict, name, category, links, est: dict) -> dict:
    from . import cast_voice as C
    data = getattr(r, "content", b"") or b""
    rid, reported = C._reported(r)
    L = _ledger(d)
    try:
        asset = _save(d, spec, c, key, data, ".mp3", op, name, category, links, {"estimate": est})
    except SystemExit:
        L.mark(op["id"], P.COMPLETED, note="The provider answered but what it sent was not usable audio. It was not kept; the request may still have been charged.")
        raise
    L.complete(op["id"], request_id=rid, actual_amount=reported, source="ElevenLabs response header" if reported is not None else None, asset=asset["file"])
    if reported and c.get("duration") and c["provider"] == "elevenlabs_sfx":
        from . import registry
        registry.observe("elevenlabs_sfx_per_second", reported / c["duration"])             # what this account really pays per second, so the next price shown is closer
    return {"asset": asset, "cached": False, "cost": {"unit": est["unit"], "estimate": est.get("expected") or est["amount"], "reported": reported, "basis": est["basis"]}, "note": "Saved to the library, waiting for your approval."}


# ---------------------------------------------------------------- a music task that is still being made (Kie.ai)

def _pending_path(d: str) -> str:
    return os.path.join(d, "audio", "pending.json")


def _pending_ok(x) -> bool:
    return isinstance(x, dict) and isinstance(x.get("tasks", []), list)


def _pending_add(d: str, p: dict) -> None:
    def change(data):
        data.setdefault("tasks", []).append(p)
        return data
    safeio.update_json(_pending_path(d), change, {"schema": 1, "tasks": []}, check=_pending_ok)


def _pending_drop(d: str, task: str) -> None:
    def change(data):
        data["tasks"] = [t for t in data.get("tasks", []) if t.get("task") != task]
        return data
    if os.path.isfile(_pending_path(d)):
        safeio.update_json(_pending_path(d), change, {"schema": 1, "tasks": []}, check=_pending_ok)


def pending(d: str) -> dict:
    AL._film(d)
    data = safeio.read_json(_pending_path(d), {"schema": 1, "tasks": []}, check=_pending_ok)
    return {"tasks": [{"task": t["task"], "provider": t["provider"], "prompt": t["params"]["prompt"], "at": t["at"]} for t in data.get("tasks", [])]}


def _tracks(info: dict) -> list[str]:
    """The finished audio addresses in a Kie.ai task record: `resultJson.resultUrls`, or the tracks of a Suno reply (`response.data[].audio_url`)."""
    urls: list[str] = []
    rj = info.get("resultJson")
    if isinstance(rj, str) and rj.strip():
        try:
            rj = json.loads(rj)
        except ValueError:
            rj = None
    if isinstance(rj, dict):
        urls += [u for u in rj.get("resultUrls", []) if isinstance(u, str)]
    resp = info.get("response")
    if isinstance(resp, dict):
        for t in (resp.get("data") or resp.get("sunoData") or []):
            if isinstance(t, dict) and isinstance(t.get("audio_url") or t.get("audioUrl"), str):
                urls.append(t.get("audio_url") or t.get("audioUrl"))
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:4]


def _poll_and_save(d: str, p: dict, wait: bool) -> dict:
    spec = PROVIDERS[p["provider"]]
    waited = 0
    while True:
        r = _kie_reply(_kie_get("/api/v1/jobs/recordInfo", params={"taskId": p["task"]}))
        info = (r.json() or {}).get("data") or {} if r.ok else {}
        state = str(info.get("state") or "").lower()
        if state == "success":
            break
        if state == "fail":
            _pending_drop(d, p["task"])
            _ledger(d).mark(p["ledger"], P.COMPLETED, note=f"Kie.ai could not make it: {_text(info.get('failMsg'), 200)}. Check your credits.")
            raise SystemExit(f"Kie.ai could not make that music ({_text(info.get('failMsg'), 160) or 'no reason given'}). Whether credits were kept is shown in your Kie.ai account.")
        if not wait or waited >= POLL_FOR:
            return {"pending": {"task": p["task"], "state": state or "waiting"}, "cached": False,
                    "note": "Kie.ai is still making it. It has been paid for; use Check again in a minute. The files are kept by Kie.ai for 14 days."}
        time.sleep(POLL_EVERY)
        waited += POLL_EVERY
    urls = _tracks(info)
    if not urls:
        raise SystemExit("Kie.ai says it finished but sent no audio address. Check again in a minute; it has been paid for.")
    c = p["params"]
    assets = []
    for i, u in enumerate(urls):
        data = _download(u)
        cc = {**c, "variation": c["variation"] + i} if i else c
        key = p["key"] if i == 0 else gen_key(cc)
        assets.append(_save(d, spec, cc, key, data, ".mp3", {"id": p["ledger"]}, p.get("name"), p.get("category"), p.get("links") or {}, {"task": p["task"], "track": i + 1, "of": len(urls)}))
    reported = info.get("creditsConsumed")
    _ledger(d).complete(p["ledger"], request_id=p["task"], actual_amount=float(reported) if isinstance(reported, (int, float)) else None, source="Kie.ai task details" if reported is not None else None,
                        asset=assets[0]["file"])
    _pending_drop(d, p["task"])
    return {"asset": assets[0], "assets": assets, "cached": False, "cost": {"unit": KIE_UNIT, "estimate": None, "reported": reported, "basis": "Kie.ai reported the credits after the task"},
            "note": f"{len(assets)} version{'s' if len(assets) != 1 else ''} saved to the library, waiting for your approval."}


def check(d: str, task: str) -> dict:
    """Look again for a music task that was still being made. Free: the task was already paid for."""
    AL._film(d)
    data = safeio.read_json(_pending_path(d), {"schema": 1, "tasks": []}, check=_pending_ok)
    p = next((t for t in data.get("tasks", []) if t.get("task") == str(task)), None)
    if not p:
        raise SystemExit("That music is not waiting for a result.")
    return _poll_and_save(d, p, wait=False)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="audiogen")
    ap.add_argument("action", choices=["providers", "estimate", "generate", "pending", "check", "rights"])
    ap.add_argument("film")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    try:
        x = json.loads(a.data or "{}")
        x = x if isinstance(x, dict) else {}
        d = os.path.abspath(a.film)
        if a.action == "providers":
            res = providers()
        elif a.action == "estimate":
            res = estimate(d, x)
        elif a.action == "generate":
            res = generate(d, x, x.get("confirmed") is True, x.get("unknown_cost_accepted") is True, x.get("rights_ack") is True)
        elif a.action == "pending":
            res = pending(d)
        elif a.action == "rights":
            res = AL.rights_report(d)
        else:
            res = check(d, x.get("task", ""))
        emit(event="result", data=res)
        return 0
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
