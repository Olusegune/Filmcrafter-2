"""Voices for spoken scenes: each character gets a voice once (show-wide), each scene's dialogue becomes its track.

  dialogue.json (in the scene)  {"setting", "lines": [{"id", "character", "text", "emotion", "pause"}], "timings": [...]}
  show.json "voices"            {character: {"voice_id", "speed", "pitch", "emotion"}}

Generating a scene: every line is spoken with its character's voice (MiniMax Speech 02 HD on fal by default), the lines
are joined with their pauses into the scene's song.wav, and the exact start and end of every line, with who speaks it,
are written down. A line can instead use the user's own recording of it (an actor's take): it is copied into the scene, trimmed of
silence at its ends, brought to the loudness of the voiced lines, and costs nothing; its character needs no voice. Song analysis then uses those exact timings (analyze._apply_dialogue) instead of guessing, so shots
are cut on the lines and speaking close-ups get the usual lip-sync pass. Lines already spoken with the same voice and
text are reused (cached), so editing one line only pays for that line. Nothing is spent without a confirmed price.

A character's voice can come from MiniMax (the preset voices, on fal) or from ElevenLabs (any voice in your ElevenLabs library, found by
search). Each character picks one, so a show can mix them. ElevenLabs bills your own ElevenLabs plan by the character, so it is shown as
characters and credits, never as a dollar price PULSEFRAME can't know; MiniMax is priced from fal's list as before.

  python -m pulseframe_analysis.voices <action> <scene_or_show_dir> --data '{...}'
"""
from __future__ import annotations

import argparse
import hashlib
from .safe import sha1 as _sha1
import json
import os
import re
import subprocess
import sys
import time
import uuid

MODEL = "fal-ai/minimax/speech-02-hd"
VOICES = [  # MiniMax preset voices (fal schema, 2026-10-01)
    ("Wise_Woman", "Wise woman"), ("Friendly_Person", "Friendly person"), ("Inspirational_girl", "Inspirational girl"),
    ("Deep_Voice_Man", "Deep-voiced man"), ("Calm_Woman", "Calm woman"), ("Casual_Guy", "Casual guy"),
    ("Lively_Girl", "Lively girl"), ("Patient_Man", "Patient man"), ("Young_Knight", "Young knight"),
    ("Determined_Man", "Determined man"), ("Lovely_Girl", "Lovely girl"), ("Decent_Boy", "Decent boy"),
    ("Imposing_Manner", "Imposing manner"), ("Elegant_Man", "Elegant man"), ("Abbess", "Abbess"),
    ("Sweet_Girl_2", "Sweet girl"), ("Exuberant_Girl", "Exuberant girl"),
]
ELEVEN = "https://api.elevenlabs.io"
ELEVEN_MODELS = [("eleven_multilingual_v2", "Multilingual v2 (steady, best for long lines)"), ("eleven_flash_v2_5", "Flash v2.5 (fast, half the credits)"),
                 ("eleven_v3", "v3 (most expressive; accepts [sad], [laughs]... in the words)")]
ELEVEN_CREDITS = {"eleven_flash_v2_5": 0.5}          # credits per character; other models cost one
ELEVEN_VOICE_ID = re.compile(r"[A-Za-z0-9]{8,40}")
EMOTIONS = ("neutral", "happy", "sad", "angry", "fearful", "disgusted", "surprised")
RATE = 44100
LEAD_IN, TAIL, DEFAULT_PAUSE = 0.6, 1.2, 0.45
MAX_LINE = 1500
AUDIO_EXT = (".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg")
MAX_RECORDING_BYTES = 100_000_000
MAX_RECORDING_SECONDS = 180
EDGE_DB = -40          # silence at the ends of a recording: below this far under its own peak
EDGE_PAD = 0.08
NATIVE_WPS, NATIVE_MIN = 2.5, 1.0   # estimated speaking pace for a scene the video model speaks
DEFAULT_RMS = 0.08    # about -22 dBFS: the level recordings are brought to when no line is voiced


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data) -> None:
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _show_of(scene: str) -> str:
    s = os.path.dirname(os.path.dirname(os.path.abspath(scene)))
    if not os.path.isfile(os.path.join(s, "show.json")):
        raise SystemExit("This scene isn't part of a show.")
    return s


# ---------------------------------------------------------------- voices (show-wide)

def voices(show: str) -> dict:
    data = _read(os.path.join(show, "show.json"), {}) or {}
    return {"voices": data.get("voices") or {}, "presets": [{"id": i, "label": l} for i, l in VOICES], "emotions": list(EMOTIONS),
            "model": MODEL, "eleven_models": [{"id": i, "label": l} for i, l in ELEVEN_MODELS], "eleven_key": bool(os.environ.get("ELEVENLABS_KEY"))}


def _num(v, lo: float, hi: float, default: float) -> float:
    try:
        return min(hi, max(lo, float(v)))
    except (TypeError, ValueError):
        return default


def set_voice(show: str, character: str, v: dict) -> dict:
    character = (character or "").strip()
    if not character:
        raise SystemExit("Choose a character.")
    if v.get("provider") == "elevenlabs":
        vid = str(v.get("voice_id") or "")
        if not ELEVEN_VOICE_ID.fullmatch(vid):
            raise SystemExit("Choose a voice from your ElevenLabs library.")
        model = v.get("model") if v.get("model") in {i for i, _ in ELEVEN_MODELS} else ELEVEN_MODELS[0][0]
        clean = {"provider": "elevenlabs", "voice_id": vid, "voice_name": str(v.get("voice_name") or "")[:80], "model": model,
                 "stability": _num(v.get("stability"), 0, 1, 0.5), "similarity": _num(v.get("similarity"), 0, 1, 0.75),
                 "style": _num(v.get("style"), 0, 1, 0.0), "speed": _num(v.get("speed"), 0.7, 1.2, 1.0)}
    else:
        if v.get("voice_id") not in {i for i, _ in VOICES}:
            raise SystemExit("Choose one of the voices.")
        clean = {"voice_id": v["voice_id"], "speed": min(2.0, max(0.5, float(v.get("speed", 1.0)))),
                 "pitch": int(min(12, max(-12, int(v.get("pitch", 0))))), "emotion": v.get("emotion") if v.get("emotion") in EMOTIONS else None}
    path = os.path.join(show, "show.json")
    data = _read(path, {}) or {}
    data.setdefault("voices", {})[character] = clean
    _write(path, data)
    return voices(show)


# ---------------------------------------------------------------- dialogue (per scene)

def dialogue(scene: str) -> dict:
    return _read(os.path.join(scene, "dialogue.json"), {"setting": "", "lines": []}) or {"setting": "", "lines": []}


def set_dialogue(scene: str, x: dict) -> dict:
    """Replace the scene's lines (the editor sends the whole list). Each line: character, text, emotion, pause (s)."""
    cur = dialogue(scene)
    lines = []
    for ln in x.get("lines") or []:
        text = " ".join(str(ln.get("text") or "").split())[:MAX_LINE]
        who = str(ln.get("character") or "").strip()[:60]
        if not text and not who:
            continue
        if not who:
            raise SystemExit(f"Line {len(lines) + 1} needs a character.")
        if not text:
            raise SystemExit(f"Line {len(lines) + 1} ({who}) has no words.")
        emo = ln.get("emotion") if ln.get("emotion") in EMOTIONS else None
        pause = min(5.0, max(0.0, float(ln.get("pause", DEFAULT_PAUSE) or 0)))
        line = {"id": ln.get("id") or uuid.uuid4().hex[:8], "character": who, "text": text, "emotion": emo, "pause": pause}
        if ln.get("recording") and _recording_path(scene, ln):          # a recording stays only if its file is in the scene
            line["recording"] = ln["recording"]
            line["recording_name"] = str(ln.get("recording_name") or "")[:80]
        lines.append(line)
    cur["lines"] = lines
    if "native" in x:
        if x["native"] and any(ln.get("recording") for ln in lines):
            raise SystemExit("Your own recordings are used instead of a generated voice, so they can't be mixed with a scene the video model speaks. "
                             "Remove the recordings, or keep native dialogue off.")
        cur["native"] = bool(x["native"])
    elif cur.get("native") and any(ln.get("recording") for ln in lines):
        cur["native"] = False
    if "setting" in x:
        cur["setting"] = str(x["setting"] or "")[:1500]
    _write(os.path.join(scene, "dialogue.json"), cur)
    _cast_speakers(scene, {ln["character"] for ln in lines})
    return {**cur, "stale": _stale(scene, cur)}


def _within(base: str, path: str) -> bool:
    b, p = os.path.normcase(os.path.realpath(base)), os.path.normcase(os.path.realpath(path))
    try:
        return os.path.commonpath([b, p]) == b and p != b
    except ValueError:
        return False


def _recording_path(scene: str, ln: dict) -> str | None:
    """The file of a line's own recording, only if it is inside the scene's recordings folder and still there."""
    rel = ln.get("recording")
    if not rel:
        return None
    path = os.path.join(scene, rel)
    return path if os.path.isfile(path) and _within(os.path.join(scene, "recordings"), path) else None


def set_recording(scene: str, line_id: str, src: str) -> dict:
    """Use the user's own recording for one line. The file is copied into the scene (the original is never touched) and must be
    audio that can be read, up to three minutes."""
    import shutil
    d = dialogue(scene)
    ln = next((x for x in d["lines"] if x.get("id") == line_id), None)
    if not ln:
        raise SystemExit("Save the line first, then add its recording.")
    ext = os.path.splitext(src)[1].lower()
    if ext not in AUDIO_EXT or not os.path.isfile(src):
        raise SystemExit("Use an audio file (wav, mp3, m4a, flac, aac or ogg).")
    if os.path.getsize(src) > MAX_RECORDING_BYTES:
        raise SystemExit("That recording is too large (100 MB at most).")
    rel = f"recordings/{line_id}-{uuid.uuid4().hex[:6]}{ext}"
    dest = os.path.join(scene, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(src, dest)
    try:
        a = _decode(dest)
        if len(a) / RATE > MAX_RECORDING_SECONDS:
            raise SystemExit(f"That recording is longer than {MAX_RECORDING_SECONDS // 60} minutes; use one file per line.")
        if len(a) == 0 or float(abs(a).max()) < 1e-4:
            raise SystemExit("That recording is silent.")
    except BaseException:
        if os.path.exists(dest):
            os.remove(dest)
        raise
    ln["recording"] = rel
    ln["recording_name"] = os.path.basename(src)[:80]
    _write(os.path.join(scene, "dialogue.json"), d)
    return {**d, "stale": _stale(scene, d)}


def clear_recording(scene: str, line_id: str) -> dict:
    """Go back to the generated voice for this line. The copied recording stays in the scene's recordings folder."""
    d = dialogue(scene)
    ln = next((x for x in d["lines"] if x.get("id") == line_id), None)
    if not ln:
        raise SystemExit("That line isn't in the scene.")
    ln.pop("recording", None)
    ln.pop("recording_name", None)
    _write(os.path.join(scene, "dialogue.json"), d)
    return {**d, "stale": _stale(scene, d)}


def _trim_edges(a):
    """A recording without the silence before and after the words (a little breath is kept), so pauses are the ones the scene sets."""
    import numpy as np
    peak = float(np.max(np.abs(a))) if len(a) else 0.0
    if peak <= 0:
        return a
    loud = np.where(np.abs(a) > peak * 10 ** (EDGE_DB / 20))[0]
    pad = int(EDGE_PAD * RATE)
    return a[max(0, int(loud[0]) - pad): min(len(a), int(loud[-1]) + pad)]


def _rms(a) -> float:
    import numpy as np
    return float(np.sqrt(np.mean(np.square(a)))) if len(a) else 0.0


def _cast_speakers(scene: str, names: set[str]) -> None:
    """Everyone who speaks in a scene belongs to the show's cast, so they can be given a voice and a costume and appear in
    shots. Names already in the cast (in any capitals) are left alone."""
    try:
        show = _show_of(scene)
    except SystemExit:
        return
    from . import library, show as S
    cast = os.path.join(show, "cast")
    have = {(i.get("name") or "").strip().lower() for i in library.load(cast)[1]["items"] if i.get("kind") == "character"}
    added = False
    for name in sorted(names):
        if name.lower() not in have:
            library.upsert(cast, {"kind": "character", "name": name, "files": []})
            added = True
    if added:
        S.sync(show)


def _voice_for(show: str, character: str) -> dict:
    v = (_read(os.path.join(show, "show.json"), {}) or {}).get("voices", {}).get(character)
    if not v:
        raise SystemExit(f"{character} has no voice yet. Choose one under Voices.")
    return v


def _key(text: str, v: dict, emotion: str | None) -> str:
    if v.get("provider") == "elevenlabs":
        raw = json.dumps(["elevenlabs", v.get("model"), text, v.get("voice_id"), v.get("stability"), v.get("similarity"), v.get("style"), v.get("speed")], sort_keys=True)
        return _sha1(raw.encode("utf-8")).hexdigest()[:16]
    raw = json.dumps([MODEL, text, v.get("voice_id"), v.get("speed"), v.get("pitch"), emotion or v.get("emotion")], sort_keys=True)
    return _sha1(raw.encode("utf-8")).hexdigest()[:16]


def _cache(scene: str, key: str) -> str:
    return os.path.join(scene, "cache", "voice", f"{key}.mp3")


def _todo(scene: str) -> tuple[list[dict], list[dict]]:
    show = _show_of(scene)
    lines = dialogue(scene)["lines"]
    if not lines:
        raise SystemExit("Write the scene's dialogue first.")
    plan, todo = [], []
    for ln in lines:
        rec = _recording_path(scene, ln)
        if rec:
            plan.append({**ln, "recorded_file": rec})
            continue
        v = _voice_for(show, ln["character"])
        k = _key(ln["text"], v, ln.get("emotion"))
        item = {**ln, "voice": v, "key": k}
        plan.append(item)
        if not os.path.exists(_cache(scene, k)):
            todo.append(item)
    return plan, todo


def _stale(scene: str, d: dict) -> bool:
    """True when the lines changed since the scene's audio was made."""
    t = d.get("timings") or []
    if t and bool(d.get("native")) != bool(d.get("timings_native")):
        return True                       # the way the scene is spoken changed: its track must be made again
    return [(x.get("character"), x.get("text"), x.get("recording")) for x in t] != \
        [(x["character"], x["text"], x.get("recording")) for x in d.get("lines") or []]


def estimate(scene: str) -> dict:
    """What generating this scene costs: only lines not already spoken with the same voice and words are billed."""
    from .render import _fal_price
    if dialogue(scene).get("native"):
        n = len(dialogue(scene)["lines"])
        if not n:
            raise SystemExit("Write the scene's dialogue first.")
        return {"lines": 0, "characters": 0, "usd": 0.0, "model": "native", "native": True,
                "basis": f"The video model speaks the {n} line(s) itself, so no voice is generated or paid for here. Their timing is estimated "
                         "from the words until the shots are rendered."}
    _, todo = _todo(scene)
    if not todo:
        return {"lines": 0, "characters": 0, "usd": 0.0, "basis": "Every line uses a recording or is already voiced: nothing to pay.", "model": MODEL}
    eleven = [x for x in todo if x["voice"].get("provider") == "elevenlabs"]
    todo = [x for x in todo if x["voice"].get("provider") != "elevenlabs"]
    e_chars = sum(len(x["text"]) for x in eleven)
    e_credits = round(sum(len(x["text"]) * ELEVEN_CREDITS.get(x["voice"].get("model"), 1.0) for x in eleven))
    e_note = f"ElevenLabs: {e_chars:,} characters, about {e_credits:,} credits of your ElevenLabs plan" if eleven else ""
    if not todo:
        return {"lines": len(eleven), "characters": e_chars, "usd": 0.0, "basis": e_note + ". Billed by ElevenLabs to your plan, not in dollars here.",
                "model": "elevenlabs", "eleven_characters": e_chars, "eleven_credits": e_credits}
    chars = sum(len(x["text"]) for x in todo)
    price = _fal_price(MODEL)
    usd = None
    basis = "MiniMax Speech 02 HD on fal; price not published right now."
    if price:
        unit, per_unit = str(price.get("unit", "")).lower(), float(price.get("unit_price", 0))
        if "character" in unit:
            per = 1000 if "1000" in unit or "thousand" in unit else 1_000_000 if "million" in unit else 1
            usd = round(per_unit * chars / per, 3)
            basis = f"${per_unit} per {per:,} characters × {chars:,} characters"
        elif any(u in unit for u in ("request", "generation", "audio")):
            usd = round(per_unit * len(todo), 3)
            basis = f"${per_unit} per line × {len(todo)} lines"
        else:
            basis = f"MiniMax bills per {unit}."
    return {"lines": len(todo) + len(eleven), "characters": chars + e_chars, "usd": usd, "basis": basis + (f". {e_note}" if e_note else ""), "model": MODEL,
            "eleven_characters": e_chars, "eleven_credits": e_credits}


def _speak(text: str, v: dict, emotion: str | None, out: str) -> float:
    """One line of speech to an mp3, retrying a dropped connection or a busy service twice. Returns its length in seconds."""
    for attempt in range(3):
        try:
            return _speak_once(text, v, emotion, out)
        except SystemExit:
            raise
        except Exception as e:
            msg = str(e).lower()
            if attempt == 2 or any(k in msg for k in ("401", "403", "unauthor", "forbidden", "balance", "exhausted", "402", "400", "422", "quota")):
                raise
            time.sleep(2 * (attempt + 1))
    return 0.0


def _eleven_error(r) -> str:
    """One sentence from an ElevenLabs refusal ({"detail": {"status", "message"}} or a plain string)."""
    try:
        d = r.json().get("detail")
    except (ValueError, AttributeError):
        d = None
    if isinstance(d, dict):
        return f"{d.get('status', '')}: {d.get('message', '')}".strip(": ")[:300]
    if isinstance(d, list) and d:
        return str(d[0].get("msg") if isinstance(d[0], dict) else d[0])[:300]
    return (str(d) if d else (getattr(r, "text", "") or f"HTTP {getattr(r, 'status_code', '?')}"))[:300]


def _eleven_headers() -> dict:
    key = os.environ.get("ELEVENLABS_KEY")
    if not key:
        raise SystemExit("Add your ElevenLabs key in Settings to use ElevenLabs voices.")
    return {"xi-api-key": key, "Accept": "application/json"}


def eleven_voices(query: str = "", page_token: str | None = None) -> dict:
    """Search your ElevenLabs voice library (your own, saved and default voices). Names and labels only: nothing is played or downloaded."""
    import requests
    params = {"page_size": 50, "include_total_count": "false"}
    if query.strip():
        params["search"] = query.strip()[:80]
    if page_token:
        params["next_page_token"] = str(page_token)[:400]
    r = requests.get(f"{ELEVEN}/v2/voices", headers=_eleven_headers(), params=params, timeout=30)
    if r.status_code in (401, 403):
        raise SystemExit("ElevenLabs refused the key. Check it in Settings.")
    if not r.ok:
        raise SystemExit(f"ElevenLabs: {_eleven_error(r)}")
    data = r.json()
    voices = []
    for x in data.get("voices") or []:
        vid = str(x.get("voice_id") or "")
        if ELEVEN_VOICE_ID.fullmatch(vid):
            voices.append({"voice_id": vid, "name": str(x.get("name") or "")[:80], "category": str(x.get("category") or "")[:30],
                           "description": str(x.get("description") or "")[:200],
                           "labels": {str(k)[:30]: str(val)[:40] for k, val in list((x.get("labels") or {}).items())[:8]}})
    return {"voices": voices, "next": data.get("next_page_token") if data.get("has_more") else None}


def _speak_eleven(text: str, v: dict, out: str) -> float:
    import requests
    body = {"text": text, "model_id": v.get("model") or ELEVEN_MODELS[0][0],
            "voice_settings": {"stability": v.get("stability", 0.5), "similarity_boost": v.get("similarity", 0.75), "style": v.get("style", 0.0),
                               "speed": v.get("speed", 1.0), "use_speaker_boost": True}}
    r = requests.post(f"{ELEVEN}/v1/text-to-speech/{v['voice_id']}", headers={**_eleven_headers(), "Accept": "audio/mpeg"},
                      params={"output_format": "mp3_44100_128"}, json=body, timeout=180)
    if r.status_code in (401, 403):
        raise RuntimeError("401 unauthorized: ElevenLabs refused the key. Check it in Settings.")
    if r.status_code == 402 or "quota" in _eleven_error(r).lower() and not r.ok:
        raise RuntimeError(f"402 quota: {_eleven_error(r)}")
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {_eleven_error(r)}")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".part"
    with open(tmp, "wb") as f:
        f.write(r.content)
    os.replace(tmp, out)
    return 0.0


def _speak_once(text: str, v: dict, emotion: str | None, out: str) -> float:
    if v.get("provider") == "elevenlabs":
        return _speak_eleven(text, v, out)
    import fal_client
    import requests
    setting = {"voice_id": v["voice_id"], "speed": v.get("speed", 1.0), "pitch": v.get("pitch", 0)}
    if emotion or v.get("emotion"):
        setting["emotion"] = emotion or v.get("emotion")
    res = fal_client.subscribe(MODEL, arguments={"text": text, "voice_setting": setting, "output_format": "url"})
    url = (res.get("audio") or {}).get("url")
    if not url:
        raise SystemExit("The voice service returned no audio.")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    tmp = out + ".part"
    with open(tmp, "wb") as f:
        f.write(r.content)
    os.replace(tmp, out)
    return float(res.get("duration_ms") or 0) / 1000


def _decode(path: str):
    """An audio file as mono float32 samples at RATE."""
    import numpy as np
    from .export import ffmpeg
    r = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(RATE), "-"],
                       capture_output=True, creationflags=0x08000000 if sys.platform == "win32" else 0)
    if r.returncode:
        raise SystemExit(f"Couldn't read the voice audio: {r.stderr.decode(errors='ignore')[-200:]}")
    return np.frombuffer(r.stdout, dtype=np.float32)


def preview(show: str, character: str, text: str | None = None) -> dict:
    """Hear a character's voice on one short line (a few characters billed)."""
    v = _voice_for(show, character)
    text = (text or f"Hello, I'm {character}.").strip()[:200]
    k = _key(text, v, None)
    out = os.path.join(show, "cast", "cache", "voice", f"{k}.mp3")
    if not os.path.exists(out):
        _speak(text, v, None, out)
    return {"path": out}


def native_seconds(text: str) -> float:
    """About how long a line takes to say (2.5 words a second, at least a second): used to cut a native-dialogue scene before it is rendered."""
    return max(NATIVE_MIN, len(text.split()) / NATIVE_WPS)


def generate_native(scene: str) -> dict:
    """A scene the video model will speak itself: nothing is voiced or paid for. The lines get estimated timings and the scene a silent
    track of that length, so the Director can cut on the lines; the real sound comes from the rendered shots at export."""
    import numpy as np
    import soundfile as sf
    d = dialogue(scene)
    lines = d["lines"]
    if not lines:
        raise SystemExit("Write the scene's dialogue first.")
    timings, t = [], LEAD_IN
    for i, ln in enumerate(lines):
        dur = native_seconds(ln["text"])
        timings.append({"id": ln["id"], "character": ln["character"], "text": ln["text"], "start": round(t, 3), "end": round(t + dur, 3),
                        "recording": None, "estimated": True})
        t += dur + (ln.get("pause", DEFAULT_PAUSE) if i < len(lines) - 1 else TAIL)
    # not digital silence: song analysis divides by the signal's level and fails on a file with none
    silent = (np.random.default_rng(7).standard_normal(int(round(t * RATE))) * 0.002).astype(np.float32)
    tmp = os.path.join(scene, "song.tmp.wav")
    sf.write(tmp, np.stack([silent, silent], axis=1), RATE, subtype="PCM_16")
    os.replace(tmp, os.path.join(scene, "song.wav"))
    d["timings"], d["timings_native"], d["generated"] = timings, True, int(time.time())
    _write(os.path.join(scene, "dialogue.json"), d)
    p = _read(os.path.join(scene, "project.json"), {}) or {}
    p.update({"song": "song.wav", "state": "new" if p.get("state") in (None, "dialogue") else p["state"], "dialogue": True})
    _write(os.path.join(scene, "project.json"), p)
    return {"duration": round(len(silent) / RATE, 2), "lines": len(timings), "voiced": 0, "recorded": 0, "reused": 0, "native": True}


def generate(scene: str) -> dict:
    """Speak every line (reusing cached ones), join them with their pauses into song.wav, record exact timings."""
    import numpy as np
    import soundfile as sf
    if dialogue(scene).get("native"):
        return generate_native(scene)
    plan, todo = _todo(scene)
    for n, ln in enumerate(todo, 1):
        emit(event="progress", stage=f"voicing {ln['character']}: line {n} of {len(todo)}", progress=round(0.9 * n / max(1, len(todo)), 3))
        _speak(ln["text"], ln["voice"], ln.get("emotion"), _cache(scene, ln["key"]))
    emit(event="progress", stage="putting the scene together", progress=0.95)
    clips = [_decode(ln["recorded_file"]) if ln.get("recorded_file") else _decode(_cache(scene, ln["key"])) for ln in plan]
    voiced_rms = sorted(_rms(c) for c, ln in zip(clips, plan) if not ln.get("recorded_file") and _rms(c) > 0)
    target = voiced_rms[len(voiced_rms) // 2] if voiced_rms else DEFAULT_RMS          # recordings are brought to the voiced lines' level
    parts, timings, t = [np.zeros(int(LEAD_IN * RATE), dtype=np.float32)], [], LEAD_IN
    for i, ln in enumerate(plan):
        a = clips[i]
        if ln.get("recorded_file"):
            a = _trim_edges(a)
            r = _rms(a)
            if r > 0:
                a = np.clip(a * min(4.0, max(0.25, target / r)), -1.0, 1.0).astype(np.float32)
        dur = len(a) / RATE
        timings.append({"id": ln["id"], "character": ln["character"], "text": ln["text"], "start": round(t, 3), "end": round(t + dur, 3),
                        "recording": ln.get("recording")})
        parts.append(a)
        t += dur
        gap = ln.get("pause", DEFAULT_PAUSE) if i < len(plan) - 1 else TAIL
        parts.append(np.zeros(int(gap * RATE), dtype=np.float32))
        t += gap
    audio = np.concatenate(parts)
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = (audio / peak * 0.89).astype(np.float32)   # about -1 dBFS: the same loudness scene to scene
    tmp = os.path.join(scene, "song.tmp.wav")
    sf.write(tmp, np.stack([audio, audio], axis=1), RATE, subtype="PCM_16")
    os.replace(tmp, os.path.join(scene, "song.wav"))
    d = dialogue(scene)
    d["timings"] = timings
    d["timings_native"] = False
    d["generated"] = int(time.time())
    _write(os.path.join(scene, "dialogue.json"), d)
    p = _read(os.path.join(scene, "project.json"), {}) or {}
    p.update({"song": "song.wav", "state": "new" if p.get("state") in (None, "dialogue") else p["state"], "dialogue": True})
    _write(os.path.join(scene, "project.json"), p)
    recorded = sum(1 for ln in plan if ln.get("recorded_file"))
    return {"duration": round(len(audio) / RATE, 2), "lines": len(timings), "voiced": len(todo), "recorded": recorded,
            "reused": len(plan) - len(todo) - recorded}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="pulseframe-voices")
    ap.add_argument("action", choices=["voices", "set_voice", "dialogue", "set_dialogue", "estimate", "preview", "generate", "set_recording", "clear_recording", "eleven_voices"])
    ap.add_argument("target")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "voices":
            res = voices(a.target)
        elif a.action == "set_voice":
            res = set_voice(a.target, x.get("character", ""), x)
        elif a.action == "dialogue":
            d = dialogue(a.target)
            res = {**d, "stale": _stale(a.target, d)}
        elif a.action == "eleven_voices":
            res = eleven_voices(x.get("query", ""), x.get("page"))
        elif a.action == "set_recording":
            res = set_recording(a.target, x["line"], x["file"])
        elif a.action == "clear_recording":
            res = clear_recording(a.target, x["line"])
        elif a.action == "set_dialogue":
            res = set_dialogue(a.target, x)
        elif a.action == "estimate":
            res = estimate(a.target)
        elif a.action == "preview":
            res = preview(a.target, x["character"], x.get("text"))
        else:
            res = generate(a.target)
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
