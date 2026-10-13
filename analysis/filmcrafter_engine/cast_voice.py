"""Custom voices with ElevenLabs, right inside a film: give each person a voice (pick one from your ElevenLabs library, design a new one from a description, or clone one from
your own recording) and have the app speak a written line in it as that person's voice for a shot.

  voice/cast.json   {"people": {key: {"name", "voice_id", "voice_name", "model", "stability", "similarity", "style", "speed", "made": "library|design|clone"}}}
  voice/_previews/  the audio of designed-voice previews (so you can hear them)
  voice/_generated/ lines already spoken (the same voice, model and words are never paid for twice)

Nothing is spent unless the call says `confirmed: true`, which the screen sends only after showing the characters and credits and getting a yes. ElevenLabs bills your own plan by the
character, so it is shown as characters and credits, never as a dollar price this app cannot know. A spoken line is attached through `voiceover.attach` like any recording (so the shot
is lengthened to hold it, a recording it replaces is archived, never deleted) and is marked `source: elevenlabs` so it can be told from your own voice and replaced by it later.
Cloning needs a plan with instant voice cloning and the speaker's consent: the call refuses without `consent: true`.

  python -m filmcrafter_engine.cast_voice <action> <film_dir> --data '{...}'
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time

from . import voiceover as V
from .safe import file_name

ELEVEN = "https://api.elevenlabs.io"
MODELS = [("eleven_v4", "Eleven v4 (most expressive: put [laughs], [whispers], [sad]... in the words)"),
          ("eleven_v4_turbo", "Eleven v4 Turbo (expressive, half the credits)"),
          ("eleven_v3", "Eleven v3 (expressive, less steady than v4)"),
          ("eleven_multilingual_v2", "Multilingual v2 (steady, best for long lines; no tags)"),
          ("eleven_flash_v2_5", "Flash v2.5 (fast, half the credits; no tags)")]
TAGGED = {"eleven_v4", "eleven_v4_turbo", "eleven_v3"}     # models that read [tags] in the words as direction (the others would speak them aloud)
CREDITS = {"eleven_flash_v2_5": 0.5, "eleven_v4_turbo": 0.5}            # credits per character (ElevenLabs' own cost multipliers, read from its model list on 2026-10-13); other models cost one
VOICE_ID = re.compile(r"[A-Za-z0-9]{8,40}")
PREVIEW_ID = re.compile(r"[A-Za-z0-9_-]{6,120}")
MAX_LINE = 1500
MAX_SAMPLE_BYTES = 30 * 1024 * 1024
MAX_SAMPLES = 5
MAX_PREVIEW_BYTES = 8 * 1024 * 1024


def emit(**kw) -> None:
    V.emit(**kw)


# ---------------------------------------------------------------- talking to ElevenLabs

def _headers(accept: str = "application/json") -> dict:
    key = os.environ.get("ELEVENLABS_KEY")
    if not key:
        raise SystemExit("Add your ElevenLabs key in Settings to use ElevenLabs voices.")
    return {"xi-api-key": key, "Accept": accept}


def _error(r) -> str:
    """One sentence from an ElevenLabs refusal ({"detail": {"status", "message"}}, a list of validation errors, or plain text)."""
    try:
        d = r.json().get("detail")
    except (ValueError, AttributeError):
        d = None
    if isinstance(d, dict):
        return f"{d.get('status', '')}: {d.get('message', '')}".strip(": ")[:300]
    if isinstance(d, list) and d:
        return str(d[0].get("msg") if isinstance(d[0], dict) else d[0])[:300]
    return (str(d) if d else (getattr(r, "text", "") or f"HTTP {getattr(r, 'status_code', '?')}"))[:300]


def _check(r, what: str):
    """The reply, or a plain sentence saying why ElevenLabs said no."""
    if r.status_code in (401, 403):
        try:
            d = r.json().get("detail")
        except (ValueError, AttributeError):
            d = None
        if isinstance(d, dict) and d.get("status") == "missing_permissions":      # the key is real but this key may not do that: say which permission, so it can be switched on
            raise SystemExit(f"Your ElevenLabs key is missing a permission: {str(d.get('message') or '')[:200]} Switch it on for this key under API Keys on elevenlabs.io.")
        raise SystemExit("ElevenLabs refused the key, or your plan does not include this. Check the key in Settings and your ElevenLabs plan.")
    if r.status_code == 402 or (not r.ok and "quota" in _error(r).lower()):
        raise SystemExit(f"Your ElevenLabs plan is out of characters: {_error(r)}")
    if not r.ok:
        raise SystemExit(f"ElevenLabs could not {what}: {_error(r)}")
    return r


def _get(path: str, **kw):
    import requests
    return requests.get(f"{ELEVEN}{path}", headers=_headers(), timeout=30, **kw)


def _post(path: str, accept: str = "application/json", timeout: int = 180, **kw):
    import requests
    return requests.post(f"{ELEVEN}{path}", headers=_headers(accept), timeout=timeout, **kw)


# ---------------------------------------------------------------- what a film has

def _path(d: str) -> str:
    return os.path.join(d, "voice", "cast.json")


def _cast(d: str) -> dict:
    c = V._read(_path(d), None)
    return c if isinstance(c, dict) and isinstance(c.get("people"), dict) else {"schema": 1, "people": {}}


def _num(v, lo: float, hi: float, default: float) -> float:
    try:
        return min(hi, max(lo, float(v)))
    except (TypeError, ValueError):
        return default


def _model(m) -> str:
    return m if m in {i for i, _ in MODELS} else MODELS[0][0]


def subscription() -> dict:
    """The plan: characters used and left, and whether it can clone. Free to ask."""
    r = _check(_get("/v1/user/subscription"), "read your plan")
    j = r.json()
    used, limit = int(j.get("character_count") or 0), int(j.get("character_limit") or 0)
    return {"tier": str(j.get("tier") or ""), "used": used, "limit": limit, "left": max(0, limit - used), "can_clone": bool(j.get("can_use_instant_voice_cloning")),
            "slots_used": int(j.get("voice_slots_used") or 0), "slots": int(j.get("voice_limit") or 0)}


def status(d: str, with_plan: bool = False) -> dict:
    """The key, the models, and each person's voice; with `with_plan` also the plan (one free call to ElevenLabs, so cards that only need the voices do not ask for it)."""
    V._film(d)
    has = bool(os.environ.get("ELEVENLABS_KEY"))
    out = {"key": has, "models": [{"id": i, "label": l} for i, l in MODELS], "people": _cast(d)["people"], "plan": None, "plan_error": ""}
    if has and with_plan:
        try:
            out["plan"] = subscription()
        except SystemExit as e:
            out["plan_error"] = str(e)
    return out


def library(query: str = "", page_token: str | None = None) -> dict:
    """Search your ElevenLabs voice library (your own, saved and default voices). Names and labels only: nothing is played, made or paid for."""
    params = {"page_size": 50, "include_total_count": "false"}
    if str(query or "").strip():
        params["search"] = str(query).strip()[:80]
    if page_token:
        params["next_page_token"] = str(page_token)[:400]
    data = _check(_get("/v2/voices", params=params), "list your voices").json()
    voices = []
    for x in data.get("voices") or []:
        vid = str(x.get("voice_id") or "")
        if VOICE_ID.fullmatch(vid):
            voices.append({"voice_id": vid, "name": str(x.get("name") or "")[:80], "category": str(x.get("category") or "")[:30], "description": str(x.get("description") or "")[:200],
                           "labels": {str(k)[:30]: str(v)[:40] for k, v in list((x.get("labels") or {}).items())[:8]}, "preview_url": str(x.get("preview_url") or "")[:300]})
    return {"voices": voices, "next": data.get("next_page_token") if data.get("has_more") else None}


def _sample_host_ok(url: str) -> bool:
    """Only ElevenLabs' own sample links: https, on elevenlabs.io (or a subdomain) or on the public ElevenLabs bucket of Google Storage."""
    from urllib.parse import urlparse
    u = urlparse(str(url or ""))
    host = (u.hostname or "").lower()
    if u.scheme != "https" or u.username or u.password or (u.port not in (None, 443)):
        return False
    if host == "elevenlabs.io" or host.endswith(".elevenlabs.io"):
        return True
    return host == "storage.googleapis.com" and u.path.startswith("/eleven-")


def sample(d: str, url: str) -> dict:
    """Fetch one library voice's sample into the film (voice/_previews) so it can be played here: the app's security policy only plays local audio. Free: nothing is made or paid for.
    Only ElevenLabs' own links are fetched, over https, never redirected elsewhere, at most 3 MB; the ElevenLabs key goes only to elevenlabs.io."""
    import requests
    V._film(d)
    if not _sample_host_ok(url):
        raise SystemExit("That is not an ElevenLabs sample.")
    name = "lib-" + hashlib.sha1(str(url).encode("utf-8")).hexdigest()[:16]
    folder = os.path.join(d, "voice", "_previews")
    for ext in (".mp3", ".wav"):
        if os.path.isfile(os.path.join(folder, name + ext)):
            return {"file": f"voice/_previews/{name}{ext}", "cached": True}
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    headers = {"Accept": "audio/*"}
    if host == "elevenlabs.io" or host.endswith(".elevenlabs.io"):
        headers["xi-api-key"] = _headers()["xi-api-key"]
    r = requests.get(url, headers=headers, timeout=30, stream=True, allow_redirects=False)
    if r.status_code in (301, 302, 303, 307, 308):
        raise SystemExit("That sample moved somewhere else, so it was not fetched.")
    if not r.ok:
        raise SystemExit(f"Could not fetch that sample (HTTP {r.status_code}).")
    data = b""
    for chunk in r.iter_content(65536):
        data += chunk
        if len(data) > 3 * 1024 * 1024:
            raise SystemExit("That sample is larger than expected, so it was not kept.")
    if len(data) < 200:
        raise SystemExit("That sample is empty.")
    ext = ".wav" if "wav" in str(r.headers.get("Content-Type", "")).lower() or data[:4] == b"RIFF" else ".mp3"
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name + ext), "wb") as f:
        f.write(data)
    return {"file": f"voice/_previews/{name}{ext}", "cached": False}


def _person(d: str, who: str) -> tuple[str, str]:
    name = str(who or "").strip()[:60]
    k = V.key_of(name)
    if not k:
        raise SystemExit("Choose who this voice is for.")
    return k, V.pretty(name)


def set_voice(d: str, who: str, v: dict, made: str = "library") -> dict:
    """Give a person one of your ElevenLabs voices."""
    V._film(d)
    k, name = _person(d, who)
    vid = str(v.get("voice_id") or "")
    if not VOICE_ID.fullmatch(vid):
        raise SystemExit("Choose a voice from your ElevenLabs library.")
    cast = _cast(d)
    cast["people"][k] = {"name": name, "voice_id": vid, "voice_name": str(v.get("voice_name") or "")[:80], "model": _model(v.get("model")),
                         "stability": _num(v.get("stability"), 0, 1, 0.5), "similarity": _num(v.get("similarity"), 0, 1, 0.75), "style": _num(v.get("style"), 0, 1, 0.0),
                         "speed": _num(v.get("speed"), 0.7, 1.2, 1.0), "made": made if made in ("library", "design", "clone") else "library"}
    os.makedirs(os.path.join(d, "voice"), exist_ok=True)
    V._write(_path(d), cast)
    return {"person": name, "voice": cast["people"][k]}


def clear_voice(d: str, who: str) -> dict:
    """Take a voice off a person. The voice stays in your ElevenLabs library; lines already spoken stay attached."""
    V._film(d)
    k, name = _person(d, who)
    cast = _cast(d)
    cast["people"].pop(k, None)
    V._write(_path(d), cast)
    return {"person": name}


# ---------------------------------------------------------------- making a new voice

def design(d: str, description: str, text: str = "") -> dict:
    """Ask ElevenLabs for a few voices that fit a description, as audio you can listen to. Uses a little of your plan's characters (the screen asks first). Saves nothing as a voice yet."""
    V._film(d)
    desc = " ".join(str(description or "").split())[:1000]
    if len(desc) < 20:
        raise SystemExit("Describe the voice in a sentence or two (at least 20 characters): age, sound, accent, mood.")
    body: dict = {"voice_description": desc}
    sample = " ".join(str(text or "").split())
    if 100 <= len(sample) <= 1000:
        body["text"] = sample
    else:
        body["auto_generate_text"] = True
    j = _check(_post("/v1/text-to-voice/design", json=body), "design that voice").json()
    folder = os.path.join(d, "voice", "_previews")
    os.makedirs(folder, exist_ok=True)
    previews = []
    for p in (j.get("previews") or [])[:6]:
        pid = str(p.get("generated_voice_id") or "")
        if not PREVIEW_ID.fullmatch(pid):
            continue
        raw = base64.b64decode(p.get("audio_base_64") or "", validate=False)
        if not raw or len(raw) > MAX_PREVIEW_BYTES:
            continue
        ext = ".wav" if "wav" in str(p.get("media_type") or "") else ".mp3"
        rel = f"voice/_previews/{file_name(pid, 80)}{ext}"
        with open(os.path.join(d, *rel.split("/")), "wb") as f:
            f.write(raw)
        previews.append({"id": pid, "file": rel, "seconds": round(float(p.get("duration_secs") or 0), 1)})
    if not previews:
        raise SystemExit("ElevenLabs sent no voices back. Try describing the voice differently.")
    return {"previews": previews, "text": str(j.get("text") or sample)[:1000]}


def design_save(d: str, who: str, generated_voice_id: str, name: str, description: str, model: str | None = None) -> dict:
    """Keep one previewed voice: it becomes a voice in your ElevenLabs library (it takes one voice slot of your plan) and is given to the person."""
    V._film(d)
    pid = str(generated_voice_id or "")
    if not PREVIEW_ID.fullmatch(pid):
        raise SystemExit("Choose one of the voices you heard.")
    nm = str(name or "").strip()[:80] or f"{_person(d, who)[1]} (FilmCrafter)"
    desc = " ".join(str(description or "").split())[:1000] or "A voice made in FilmCrafter."
    j = _check(_post("/v1/text-to-voice", json={"voice_name": nm, "voice_description": desc, "generated_voice_id": pid}), "keep that voice").json()
    return set_voice(d, who, {"voice_id": j.get("voice_id"), "voice_name": nm, "model": model}, made="design")


def clone(d: str, who: str, name: str, files: list, consent: bool = False, remove_noise: bool = False, model: str | None = None) -> dict:
    """Make a voice from your own recordings (instant cloning): it takes one voice slot of your plan and is given to the person. Only for a voice you have the right to clone."""
    V._film(d)
    if consent is not True:
        raise SystemExit("Confirm that you have the right to clone this voice (it is yours, or the speaker has agreed).")
    paths = []
    for f in list(files or [])[:MAX_SAMPLES]:
        p = os.path.abspath(str(f))
        if not os.path.isfile(p) or not p.lower().endswith(V.AUDIO_EXT):
            raise SystemExit("Use WAV, MP3, M4A, FLAC, AAC or OGG recordings of the voice.")
        if os.path.getsize(p) > MAX_SAMPLE_BYTES:
            raise SystemExit("A sample is larger than 30 MB. Use a shorter clean recording (a minute or two is plenty).")
        paths.append(p)
    if not paths:
        raise SystemExit("Choose one or more recordings of the voice (a minute or two of clean speech works best).")
    nm = str(name or "").strip()[:80] or f"{_person(d, who)[1]} (cloned in FilmCrafter)"
    handles = [open(p, "rb") for p in paths]
    try:
        r = _post("/v1/voices/add", data={"name": nm, "remove_background_noise": "true" if remove_noise else "false", "description": "Cloned in FilmCrafter from the owner's recordings."},
                  files=[("files", (os.path.basename(p), h)) for p, h in zip(paths, handles)])
    finally:
        for h in handles:
            h.close()
    j = _check(r, "clone that voice").json()
    out = set_voice(d, who, {"voice_id": j.get("voice_id"), "voice_name": nm, "model": model}, made="clone")
    out["requires_verification"] = bool(j.get("requires_verification"))
    return out


# ---------------------------------------------------------------- speaking a line

def _line(d: str, shot: str, speaker: str, text: str | None) -> tuple[str, str, str, dict]:
    """(shot id, person name, the words, that person's voice), refusing anything that cannot be spoken."""
    from .safe import check_id
    V._film(d)
    sid = check_id(shot, "shot")
    k, name = _person(d, speaker)
    voice = _cast(d)["people"].get(k)
    if not voice:
        raise SystemExit(f"{name} has no voice yet. Choose, design or clone one first.")
    st = next((s for s in V.status(d)["shots"] if s["id"] == sid), None)
    mine = next((p for p in (st or {}).get("people", []) if p["key"] == k), None)
    words = " ".join(str(text if text is not None else " ".join((mine or {}).get("lines") or [])).split())
    if not words:
        raise SystemExit(f"{name} has no written line in {sid}. Type what they say.")
    if len(words) > MAX_LINE:
        raise SystemExit(f"That line is longer than {MAX_LINE} characters. Split it across shots.")
    return sid, name, words, voice


def _cache(d: str, sid: str, words: str, voice: dict) -> str:
    raw = json.dumps([voice.get("model"), voice.get("voice_id"), words, voice.get("stability"), voice.get("similarity"), voice.get("style"), voice.get("speed")], sort_keys=True)
    return os.path.join(d, "voice", "_generated", f"{sid}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}.mp3")


def estimate(d: str, items: list) -> dict:
    """What speaking these lines would use of your plan, per line and in total. Free. Lines already spoken in the same voice cost nothing."""
    rows, total_chars, total_credits = [], 0, 0
    for it in (items or [])[:200]:
        try:
            sid, name, words, voice = _line(d, it.get("shot"), it.get("speaker"), it.get("text"))
        except SystemExit as e:
            rows.append({"shot": str(it.get("shot") or ""), "speaker": str(it.get("speaker") or ""), "ok": False, "why": str(e)})
            continue
        cached = os.path.isfile(_cache(d, sid, words, voice))
        credits = 0 if cached else round(len(words) * CREDITS.get(voice.get("model"), 1.0))
        rows.append({"shot": sid, "speaker": name, "ok": True, "characters": len(words), "credits": credits, "cached": cached, "text": words})
        total_chars += 0 if cached else len(words)
        total_credits += credits
    return {"rows": rows, "characters": total_chars, "credits": total_credits,
            "basis": f"{total_chars:,} characters, about {total_credits:,} credits of your ElevenLabs plan. Billed by ElevenLabs to your plan, not in dollars here."}


def _speak_to(path: str, words: str, voice: dict) -> None:
    body = {"text": words, "model_id": _model(voice.get("model")),
            "voice_settings": {"stability": voice.get("stability", 0.5), "similarity_boost": voice.get("similarity", 0.75), "style": voice.get("style", 0.0),
                               "speed": voice.get("speed", 1.0), "use_speaker_boost": True}}
    r = None
    for attempt in range(3):                                   # a dropped connection or a busy service is tried twice more; a refusal is not
        try:
            r = _post(f"/v1/text-to-speech/{voice['voice_id']}", accept="audio/mpeg", params={"output_format": "mp3_44100_128"}, json=body)
        except SystemExit:
            raise
        except Exception:
            if attempt == 2:
                raise SystemExit("Could not reach ElevenLabs. Check your connection and try again; nothing was attached.")
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code in (429, 500, 502, 503) and attempt < 2:
            time.sleep(2 * (attempt + 1))
            continue
        break
    _check(r, "speak that line")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(r.content)
    os.replace(tmp, path)


def _sidecar(path: str) -> str:
    return path[:-4] + ".json"


def _attach_generated(d: str, sid: str, name: str, path: str, voice: dict) -> dict:
    """Attach a spoken line as the person's voice in the shot, marked as spoken by ElevenLabs. Attaching the take that is already attached changes nothing (so nothing is archived for no reason)."""
    k = V.key_of(name)
    gen = os.path.basename(path)
    cur = next((e for e in V._meta(d)["shots"].get(sid, []) if e.get("key") == k), None)
    if cur and cur.get("gen") == gen and os.path.isfile(os.path.join(d, *str(cur.get("file", "")).split("/"))):
        return {"shot": sid, "speaker": V.pretty(name), "seconds": cur.get("seconds"), "notes": [], "replaced": False, "unchanged": True}
    res = V.attach(d, sid, name, path, fit=True)
    meta = V._meta(d)
    for e in meta["shots"].get(sid, []):
        if e.get("key") == k:
            e["source"] = "elevenlabs"
            e["gen"] = gen
            e["name"] = f"{name} (ElevenLabs, {voice.get('voice_name') or 'voice'})"[:120]
    V._write(os.path.join(d, "voice", "voice.json"), meta)
    return res


def speak(d: str, shot: str, speaker: str, text: str | None = None, confirmed: bool = False) -> dict:
    """Speak a line in the person's voice and attach it to the shot as theirs. `text` is what to say (default: their written line); with a model that reads [tags], direction such as
    [whispers] or [laughs] can sit in it. The shot's own written dialogue is never changed, so the direction never reaches a picture or video prompt. Only with `confirmed: true`,
    after the screen has shown the price; a line already spoken in the same voice is free. Every spoken version is kept as a take (see `takes`)."""
    sid, name, words, voice = _line(d, shot, speaker, text)
    path = _cache(d, sid, words, voice)
    spent = 0
    if not os.path.isfile(path):
        if confirmed is not True:
            raise SystemExit("Speaking a line uses your ElevenLabs plan. Confirm the price first.")
        _speak_to(path, words, voice)
        spent = round(len(words) * CREDITS.get(voice.get("model"), 1.0))
        V._write(_sidecar(path), {"shot": sid, "key": V.key_of(name), "speaker": name, "text": words, "model": voice.get("model"), "voice_id": voice.get("voice_id"),
                                  "voice_name": voice.get("voice_name"), "at": int(time.time())})
    res = _attach_generated(d, sid, name, path, voice)
    return {**res, "characters": len(words), "credits": spent, "cached": spent == 0, "take": os.path.relpath(path, d).replace(os.sep, "/")}


def takes(d: str, shot: str, speaker: str) -> dict:
    """Every version of this line that has been spoken (newest first), and which one is attached now. Free."""
    from .safe import check_id
    V._film(d)
    sid = check_id(shot, "shot")
    k, name = _person(d, speaker)
    folder = os.path.join(d, "voice", "_generated")
    cur = next((e.get("gen") for e in V._meta(d)["shots"].get(sid, []) if e.get("key") == k), None)
    out = []
    for f in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not f.endswith(".mp3") or not f.startswith(sid + "-"):
            continue
        meta = V._read(_sidecar(os.path.join(folder, f)), None)
        if not isinstance(meta, dict) or meta.get("key") != k:
            continue
        out.append({"file": f"voice/_generated/{f}", "text": str(meta.get("text") or "")[:1500], "model": meta.get("model"), "voice_name": str(meta.get("voice_name") or "")[:80],
                    "at": int(meta.get("at") or 0), "current": f == cur})
    out.sort(key=lambda t: -t["at"])
    return {"takes": out[:30], "person": name, "shot": sid}


def use_take(d: str, shot: str, speaker: str, file: str) -> dict:
    """Switch to one of the takes already spoken (free: nothing is sent). The take it replaces is archived in voice/_removed, never deleted."""
    from .safe import check_id
    V._film(d)
    sid = check_id(shot, "shot")
    k, name = _person(d, speaker)
    rel = str(file or "")
    path = V.inside(d, rel)
    if not path or not rel.startswith(f"voice/_generated/{sid}-") or not rel.endswith(".mp3") or not os.path.isfile(path):
        raise SystemExit("That take is not one of this line's.")
    meta = V._read(_sidecar(path), None)
    if not isinstance(meta, dict) or meta.get("key") != k:
        raise SystemExit("That take is not one of this line's.")
    voice = {"voice_name": meta.get("voice_name")}
    return {**_attach_generated(d, sid, name, path, voice), "take": rel}


def preview(d: str, who: str, text: str = "", confirmed: bool = False) -> dict:
    """Hear a person's voice say a few words (not attached to any shot). Uses a few characters of your plan; only with `confirmed: true`."""
    V._film(d)
    k, name = _person(d, who)
    voice = _cast(d)["people"].get(k)
    if not voice:
        raise SystemExit(f"{name} has no voice yet.")
    words = " ".join(str(text or "").split())[:200] or f"Hello, I'm {name}. This is how I sound."
    path = _cache(d, "preview", words, voice)
    spent = 0
    if not os.path.isfile(path):
        if confirmed is not True:
            raise SystemExit("A sample uses a few characters of your ElevenLabs plan. Confirm first.")
        _speak_to(path, words, voice)
        spent = round(len(words) * CREDITS.get(voice.get("model"), 1.0))
    return {"file": os.path.relpath(path, d).replace(os.sep, "/"), "text": words, "characters": len(words), "credits": spent}


# ---------------------------------------------------------------- command line

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["status", "library", "set", "clear", "design", "design_save", "clone", "estimate", "speak", "preview", "takes", "use_take", "sample"])
    ap.add_argument("target")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    d = os.path.abspath(a.target)
    try:
        x = json.loads(a.data or "{}")
        x = x if isinstance(x, dict) else {}
        if a.action == "status":
            res = status(d, x.get("plan") is True)
        elif a.action == "library":
            res = library(x.get("query", ""), x.get("page"))
        elif a.action == "set":
            res = set_voice(d, x.get("person", ""), x.get("voice") or {})
        elif a.action == "clear":
            res = clear_voice(d, x.get("person", ""))
        elif a.action == "design":
            res = design(d, x.get("description", ""), x.get("text", ""))
        elif a.action == "design_save":
            res = design_save(d, x.get("person", ""), x.get("generated_voice_id", ""), x.get("name", ""), x.get("description", ""), x.get("model"))
        elif a.action == "clone":
            res = clone(d, x.get("person", ""), x.get("name", ""), x.get("files") or [], x.get("consent") is True, x.get("remove_noise") is True, x.get("model"))
        elif a.action == "estimate":
            res = estimate(d, x.get("items") or [])
        elif a.action == "speak":
            res = speak(d, x.get("shot", ""), x.get("speaker", ""), x.get("text"), x.get("confirmed") is True)
        elif a.action == "sample":
            res = sample(d, x.get("url", ""))
        elif a.action == "takes":
            res = takes(d, x.get("shot", ""), x.get("speaker", ""))
        elif a.action == "use_take":
            res = use_take(d, x.get("shot", ""), x.get("speaker", ""), x.get("file", ""))
        else:
            res = preview(d, x.get("person", ""), x.get("text", ""), x.get("confirmed") is True)
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
