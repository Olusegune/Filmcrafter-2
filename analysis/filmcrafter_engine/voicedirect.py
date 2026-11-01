"""Directing voices: the spoken version of a line, natural-delivery suggestions, voice-casting suggestions, voicing a whole scene, and the scene table read.

  <Film>/voice/performance.json   the person's own spoken version of a line (kept apart from the screenplay): {lines: {shot: {person_key: {text, note, pronunciation, written, source, updated}}}}

The screenplay and the shot's written dialogue are never changed by anything here. A spoken version exists only when the person made it (typed it, or accepted a suggestion); it is what
"Speak it" says by default, and the written line stays beside it so a later change to the screenplay is noticed ("the written line has changed since").

Suggestions (natural delivery for a line, a voice for a character) come from the configured writing AI, with the price shown and confirmed first, and they only ever propose. Matching
voices to a description is done on this computer from the labels ElevenLabs already gives each library voice: free. Voicing a scene needs one explicit yes with a spending cap, speaks only
the lines that have no recording, keeps every line that worked even if another fails, and stops at once if a charge is unclear.

  python -m filmcrafter_engine.voicedirect <action> <film_dir> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

from . import paidops as P
from . import safeio
from . import voiceover as V

MAX_TEXT = 1500
NOTE_MAX = 400
SUGGESTIONS = 3
FILLERS = {"uh", "um", "er", "erm", "hmm", "ah", "oh", "well", "like", "you", "know", "i", "mean"}
TAG = re.compile(r"\[[^\]]*\]")
GENDERS = {"male": ("male", "man", "men", "boy", "he", "his", "father", "dad", "grandfather", "grandpa", "uncle"), "female": ("female", "woman", "women", "girl", "she", "her", "mother", "mum", "mom", "grandmother", "grandma", "aunt")}
AGES = {"young": ("young", "child", "kid", "teen", "teenager", "boy", "girl", "twenties", "20s", "student"), "middle_aged": ("middle", "thirties", "forties", "fifties", "30s", "40s", "50s", "adult"),
        "old": ("old", "elderly", "aged", "sixties", "seventies", "eighties", "60s", "70s", "80s", "grandfather", "grandmother", "grandpa", "grandma")}


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


def _text(v, limit: int = MAX_TEXT) -> str:
    return " ".join(str(v if v is not None else "").replace("\x00", "").split())[:limit]


# ---------------------------------------------------------------- the spoken version of a line

def _path(d: str) -> str:
    return os.path.join(d, "voice", "performance.json")


def _ok(data) -> bool:
    return isinstance(data, dict) and isinstance(data.get("lines", {}), dict)


def _load(d: str) -> dict:
    data = safeio.read_json(_path(d), {"schema": 1, "lines": {}}, check=_ok)
    data.setdefault("lines", {})
    return data


def performance_text(d: str, shot: str, key: str) -> str:
    """The person's own spoken version of this person's line in this shot, or '' when there is none (then the written line is spoken)."""
    if not os.path.isfile(_path(d)):
        return ""
    e = (_load(d)["lines"].get(shot) or {}).get(key)
    return _text(e.get("text")) if isinstance(e, dict) else ""


def _written(d: str, sid: str, key: str) -> tuple[str, str]:
    st = next((s for s in V.status(d)["shots"] if s["id"] == sid), None)
    mine = next((p for p in (st or {}).get("people", []) if p["key"] == key), None)
    if not mine or not mine.get("lines"):
        raise SystemExit("That person has no written line in that shot.")
    return " ".join(mine["lines"]), mine["name"]


def get_performance(d: str) -> dict:
    """Every spoken version, with whether the written line has changed since it was made. Free."""
    V._film(d)
    out = []
    for sid, people in sorted(_load(d)["lines"].items()):
        for key, e in people.items():
            if not isinstance(e, dict):
                continue
            try:
                now, name = _written(d, sid, key)
            except SystemExit:
                now, name = None, e.get("speaker", key)
            out.append({"shot": sid, "key": key, "speaker": name, "text": e.get("text", ""), "note": e.get("note", ""), "pronunciation": e.get("pronunciation", ""),
                        "written": e.get("written", ""), "source": e.get("source", "person"), "updated": e.get("updated", 0),
                        "written_changed": now is not None and _text(now) != _text(e.get("written", "")), "line_gone": now is None})
    return {"lines": out}


def set_performance(d: str, shot: str, speaker: str, text: str, note: str = "", pronunciation: str = "", source: str = "person") -> dict:
    """Save the spoken version of a line. The screenplay is not touched. This is the person's act (typing it, or accepting a suggestion)."""
    from .safe import check_id
    V._film(d)
    sid = check_id(shot, "shot")
    key = V.key_of(speaker)
    written, name = _written(d, sid, key)
    words = " ".join(str(text or "").replace("\x00", "").split())            # not cut short: a line that is too long is refused, never silently trimmed
    if not words:
        raise SystemExit("Write what is spoken, or clear the spoken version to use the written line.")
    from .cast_voice import MAX_LINE
    if len(words) > MAX_LINE:
        raise SystemExit(f"That is longer than {MAX_LINE} characters. Split it across shots.")

    def change(data):
        data.setdefault("schema", 1)
        data.setdefault("lines", {})
        data["lines"].setdefault(sid, {})[key] = {"speaker": name, "text": words, "note": _text(note, NOTE_MAX), "pronunciation": _text(pronunciation, NOTE_MAX), "written": _text(written),
                                                  "source": "assistant" if source == "assistant" else "person", "updated": int(time.time())}
        return data
    safeio.update_json(_path(d), change, {"schema": 1, "lines": {}}, check=_ok)
    return get_performance(d)


def clear_performance(d: str, shot: str, speaker: str) -> dict:
    """Go back to speaking the written line. The written line was never changed."""
    from .safe import check_id
    V._film(d)
    sid, key = check_id(shot, "shot"), V.key_of(speaker)
    if os.path.isfile(_path(d)):
        def change(data):
            (data.get("lines") or {}).get(sid, {}).pop(key, None)
            if sid in data.get("lines", {}) and not data["lines"][sid]:
                data["lines"].pop(sid)
            return data
        safeio.update_json(_path(d), change, {"schema": 1, "lines": {}}, check=_ok)
    return get_performance(d)


# ---------------------------------------------------------------- suggestions (the writing AI proposes; nothing is changed)

def _schema(props: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


NATURAL_SYSTEM = ("You help a film director make written dialogue sound like a real person speaking it, without changing what the character means. Offer up to three alternatives of the SAME line. "
                  "Keep the character's intent, facts, names and every important word. You may add small human touches: a short pause (an ellipsis), a hesitation, a half-finished start, a breath, "
                  "a nervous laugh, a sigh. Do not add new information, do not make the line longer than about a third more, do not change who it is spoken to, and do not rewrite the plot. "
                  "If the speaking model reads [tags], you may use square-bracket directions like [sighs], [laughs nervously], [whispers] placed where they happen; if it does not, use only punctuation "
                  "and plain words. For each alternative say in one short sentence what changed and why.")
NATURAL_SCHEMA = _schema({"suggestions": {"type": "array", "items": _schema({"text": {"type": "string"}, "why": {"type": "string"}})}})

VOICE_SYSTEM = ("You help a film director decide what a character should SOUND like, from the story and the character sheet. Use only what the story shows plus modest, fitting inference; if the "
                "story is silent, suggest something plain and short. Describe a voice (age and range, accent, texture, pace, emotional range, usual delivery) the way a casting director would, in plain "
                "words. Also give a few search terms for finding a matching voice in a voice library: gender (male, female or neutral), age (young, middle_aged or old), an accent if one is implied, and up to "
                "four descriptive words (for example warm, raspy, calm, gentle). Never name a real actor or copy a real person's voice.")
VOICE_SCHEMA = _schema({"description": {"type": "string"}, "age_range": {"type": "string"}, "accent": {"type": "string"}, "timbre": {"type": "string"}, "pace": {"type": "string"},
                        "emotional_range": {"type": "string"}, "delivery": {"type": "string"}, "notes": {"type": "string"},
                        "search": _schema({"gender": {"type": "string"}, "age": {"type": "string"}, "accent": {"type": "string"}, "descriptors": {"type": "array", "items": {"type": "string"}}})})


def _words_of(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", TAG.sub(" ", str(text or "").lower()))


def natural_brief(d: str, shot: str, speaker: str) -> dict:
    """What would be sent: the line, who says it, a little of what is around it, and whether the voice reads [tags]. Nothing else leaves the computer."""
    from . import bible as B
    from . import cast_voice as C
    from .safe import check_id
    V._film(d)
    sid, key = check_id(shot, "shot"), V.key_of(speaker)
    written, name = _written(d, sid, key)
    spoken = performance_text(d, sid, key)
    shots = V.status(d)["shots"]
    idx = next((i for i, s in enumerate(shots) if s["id"] == sid), 0)
    around = [{"shot": s["id"], "speaker": p["name"], "line": " ".join(p["lines"])[:300]} for s in shots[max(0, idx - 2): idx + 3] for p in s["people"] if p["lines"]][:8]
    ch = next((c for c in B.load(d)["characters"] if V.key_of(c["name"]) == key), {})
    voice = C._cast(d)["people"].get(key) or {}
    return {"task": "alternatives of one spoken line", "speaker": name, "written_line": written, "current_spoken_version": spoken or None, "around": around,
            "character": {k: ch.get(k) for k in ("role", "age", "arc", "voice", "notes") if ch.get(k)}, "voice_profile": {k: v for k, v in (ch.get("voice_profile") or {}).items() if v and k != "approved"},
            "model_reads_tags": voice.get("model") in C.TAGGED}


def natural_estimate(d: str, shot: str, speaker: str) -> dict:
    from .acting import _estimate
    br = natural_brief(d, shot, speaker)
    return {**_estimate(len(json.dumps(br, ensure_ascii=False)) + len(NATURAL_SYSTEM), 1, 500), "sends": "this line, who says it, the lines around it and the character's notes"}


def clean_natural(out: dict, original: str, tagged: bool) -> list[dict]:
    """Keep the suggestions that are usable: trimmed, untagged when the voice cannot read tags, not the same as the original, within the length limit, each marked with the words it adds."""
    from .cast_voice import MAX_LINE
    orig_words = set(_words_of(original)) | FILLERS
    seen = {_text(original).lower()}
    res = []
    for s in (out.get("suggestions") or []):
        t = _text(s.get("text") if isinstance(s, dict) else "")
        if not tagged:
            t = _text(TAG.sub(" ", t))
        if not t or t.lower() in seen or len(t) > MAX_LINE or len(TAG.sub("", t)) > max(40, int(len(original) * 1.6)):
            continue
        seen.add(t.lower())
        added = sorted({w for w in _words_of(t) if w not in orig_words})
        res.append({"text": t, "why": _text(s.get("why"), 240), "adds_words": added, "keeps_meaning_check": "Check it still says what you mean." + (f" It adds: {', '.join(added)}." if added else "")})
        if len(res) >= SUGGESTIONS:
            break
    return res


def natural_suggest(d: str, shot: str, speaker: str) -> dict:
    """Ask the configured writing AI for natural-sounding alternatives of one line. Returns them; saves nothing; the screenplay is never touched."""
    from . import assist as A
    from .director import DEFAULT_MODEL, openai_error, resolve_model
    from .llm import client as make_client
    br = natural_brief(d, shot, speaker)
    cl = make_client()
    model = resolve_model(cl, DEFAULT_MODEL)
    emit(event="progress", stage="listening for a more natural way to say it", progress=0.3)
    try:
        out = A._call(cl, model, NATURAL_SYSTEM, json.dumps(br, ensure_ascii=False), "natural_line", NATURAL_SCHEMA)
    except SystemExit:
        raise
    except Exception as e:
        raise SystemExit(openai_error(e))
    return {"shot": shot, "speaker": br["speaker"], "original": br["written_line"], "suggestions": clean_natural(out, br["written_line"], br["model_reads_tags"]), "model": str(model),
            "estimate": natural_estimate(d, shot, speaker)}


# ---------------------------------------------------------------- finding a voice for a character

def _character(d: str, char_id: str) -> dict:
    from . import bible as B
    from .safe import check_id
    b = B.load(d)
    return B._find(b, "character", check_id(char_id, "character"))


def voices_brief(d: str, char_id: str) -> dict:
    from . import assist as A
    from . import bible as B
    ch = _character(d, char_id)
    b = B.load(d)
    text = A._story_text(d)
    return {"task": "what this character should sound like", "name": ch["name"], "character": {k: ch.get(k) for k in ("role", "age", "physical", "relationships", "arc", "voice", "notes") if ch.get(k)},
            "voice_profile_so_far": {k: v for k, v in (ch.get("voice_profile") or {}).items() if v and k != "approved"}, "tone": b["rules"].get("tone", ""),
            "story_excerpts": A._excerpts(text, [ch["name"], ch["name"].upper()]), "other_characters": [c["name"] for c in b["characters"] if c["id"] != ch["id"]][:20]}


def voices_estimate(d: str, char_id: str) -> dict:
    from .acting import _estimate
    br = voices_brief(d, char_id)
    return {**_estimate(len(json.dumps(br, ensure_ascii=False)) + len(VOICE_SYSTEM), 1, 600), "sends": "your story and what the Bible says about this character"}


def clean_profile(out: dict) -> dict:
    from .bible import VOICE_PROFILE_FIELDS
    prof = {k: _text(out.get(k), 600) for k in VOICE_PROFILE_FIELDS}
    s = out.get("search") or {}
    g = _text(s.get("gender"), 20).lower()
    a = _text(s.get("age"), 20).lower().replace("-", "_").replace(" ", "_")
    prof["search"] = {"gender": g if g in ("male", "female", "neutral") else "", "age": a if a in ("young", "middle_aged", "old") else "", "accent": _text(s.get("accent"), 40).lower(),
                      "descriptors": [w for w in (_text(x, 24).lower() for x in (s.get("descriptors") or [])[:4]) if w]}
    return prof


def wanted_from_text(*parts: str) -> dict:
    """What to look for in a voice library, read from plain words about the character (no AI): gender, age, accent and a few descriptive words."""
    words = set(_words_of(" ".join(parts)))
    gender = next((g for g, ws in GENDERS.items() if words & set(ws)), "")
    if words & set(GENDERS["male"]) and words & set(GENDERS["female"]):
        gender = ""
    age = next((a for a in ("old", "young", "middle_aged") if words & set(AGES[a])), "")
    return {"gender": gender, "age": age, "accent": "", "descriptors": []}


def score_voice(v: dict, wanted: dict) -> tuple[float, list[str]]:
    """How well a library voice fits what was asked for, from the labels and description ElevenLabs gives it. Higher is better; the reasons are plain words. Free and local."""
    labels = {str(k).lower(): str(x).lower().replace("-", " ").replace("_", " ") for k, x in (v.get("labels") or {}).items()}
    hay = " ".join([v.get("description", "").lower(), v.get("name", "").lower(), *labels.values()])
    score, why = 0.0, []
    g = wanted.get("gender")
    if g and labels.get("gender") == g:
        score += 3
        why.append(g)
    elif g and labels.get("gender") and labels.get("gender") != g:
        score -= 3
    a = (wanted.get("age") or "").replace("_", " ")
    if a and a in labels.get("age", ""):
        score += 3
        why.append(a.replace("middle aged", "middle-aged") + " voice")
    elif a and labels.get("age") and a not in labels.get("age", ""):
        score -= 1
    ac = (wanted.get("accent") or "").lower()
    if ac and ac in hay:
        score += 2
        why.append(f"{ac} accent")
    for w in wanted.get("descriptors") or []:
        if w and w.lower() in hay:
            score += 1
            why.append(w)
    return score, why


def match_voices(wanted: dict, voices: list[dict], limit: int = 8) -> list[dict]:
    rows = []
    for v in voices:
        s, why = score_voice(v, wanted)
        if s > 0:
            rows.append({"voice": v, "score": round(s, 1), "why": why})
    rows.sort(key=lambda r: -r["score"])
    return rows[:limit]


def _library_for(wanted: dict) -> tuple[list[dict], str]:
    """Voices from the person's ElevenLabs library (a few free searches); ([], a plain note) when there is no key or it cannot be reached."""
    from . import cast_voice as C
    seen: dict[str, dict] = {}
    queries = ["", *([wanted["accent"]] if wanted.get("accent") else []), *(wanted.get("descriptors") or [])[:2]]
    try:
        for q in queries:
            for v in C.library(q)["voices"]:
                seen.setdefault(v["voice_id"], v)
    except SystemExit as e:
        return list(seen.values()), str(e)
    except Exception as e:
        return list(seen.values()), f"The voice library could not be reached ({type(e).__name__})."
    return list(seen.values()), ""


def voices_match(d: str, char_id: str, wanted: dict | None = None) -> dict:
    """Free: voices from your library that fit the character's saved voice profile and notes (or the `wanted` terms given). Changes nothing."""
    ch = _character(d, char_id)
    prof = ch.get("voice_profile") or {}
    w = wanted or wanted_from_text(prof.get("description", ""), prof.get("age_range", ""), ch.get("age", ""), ch.get("role", ""), ch.get("voice", ""), ch.get("notes", ""))
    if not wanted:
        w["accent"] = _text(prof.get("accent"), 40).lower()
        w["descriptors"] = [x for x in _words_of(" ".join([prof.get("description", ""), prof.get("timbre", ""), ch.get("voice", "")])) if len(x) > 3][:4]
    voices, note = _library_for(w)
    return {"character": ch["name"], "wanted": w, "matches": match_voices(w, voices), "searched": len(voices), "note": note, "approved": bool(prof.get("approved"))}


def voices_suggest(d: str, char_id: str) -> dict:
    """Ask the writing AI what the character should sound like, then look for matching voices in your library (free). Proposes only: the profile is not saved, no voice is chosen, and an
    approved voice is never touched."""
    from . import assist as A
    from .director import DEFAULT_MODEL, openai_error, resolve_model
    from .llm import client as make_client
    br = voices_brief(d, char_id)
    cl = make_client()
    model = resolve_model(cl, DEFAULT_MODEL)
    emit(event="progress", stage="thinking about the voice", progress=0.3)
    try:
        out = A._call(cl, model, VOICE_SYSTEM, json.dumps(br, ensure_ascii=False), "voice_profile", VOICE_SCHEMA)
    except SystemExit:
        raise
    except Exception as e:
        raise SystemExit(openai_error(e))
    prof = clean_profile(out)
    voices, note = _library_for(prof["search"])
    ch = _character(d, char_id)
    return {"character": ch["name"], "proposal": {k: v for k, v in prof.items() if k != "search"}, "wanted": prof["search"], "matches": match_voices(prof["search"], voices), "searched": len(voices),
            "note": note, "approved": bool((ch.get("voice_profile") or {}).get("approved")), "model": str(model), "estimate": voices_estimate(d, char_id)}


# ---------------------------------------------------------------- a whole scene

def _scene_shots(d: str, scene: int) -> list[dict]:
    shots = [s for s in V.status(d)["shots"] if int(s.get("scene") or 0) == int(scene)]
    if not shots:
        raise SystemExit("That scene has no spoken lines.")
    return shots


def scene_plan(d: str, scene: int) -> dict:
    """Who speaks in this scene, which of them have a voice, which lines already have a recording, what is missing, and what speaking the missing ones would use. Free; sends nothing."""
    from . import bible as B
    from . import cast_voice as C
    V._film(d)
    shots = _scene_shots(d, scene)
    cast = C._cast(d)["people"]
    approved = {V.key_of(c["name"]): bool((c.get("voice_profile") or {}).get("approved")) for c in B.load(d)["characters"]}
    lines, speakers = [], {}
    for s in shots:
        for p in s["people"]:
            if not p["lines"]:
                continue
            voice = cast.get(p["key"])
            rec = p.get("recording")
            sp = speakers.setdefault(p["key"], {"name": p["name"], "key": p["key"], "voice": (voice or {}).get("voice_name") or None, "has_voice": bool(voice), "approved": approved.get(p["key"], False), "lines": 0})
            sp["lines"] += 1
            text = performance_text(d, s["id"], p["key"]) or " ".join(p["lines"])
            state = ("spoken" if rec.get("source") == "elevenlabs" else "recorded") if rec else ("missing" if voice else "no_voice")
            lines.append({"shot": s["id"], "speaker": p["name"], "key": p["key"], "text": text, "written": " ".join(p["lines"]), "spoken_version": bool(performance_text(d, s["id"], p["key"])),
                          "state": state, "seconds": (rec or {}).get("seconds")})
    todo = [{"shot": x["shot"], "speaker": x["speaker"]} for x in lines if x["state"] == "missing"]
    est = C.estimate(d, todo) if todo else {"rows": [], "characters": 0, "credits": 0, "basis": "Nothing to speak."}
    by = {(r["shot"], r["speaker"]): r for r in est["rows"]}
    for x in lines:
        r = by.get((x["shot"], x["speaker"]))
        if r and r.get("ok"):
            x["characters"], x["credits"], x["cached"] = r["characters"], r["credits"], r["cached"]
        elif r:
            x["why"] = r.get("why")
    return {"scene": int(scene), "speakers": list(speakers.values()), "lines": lines, "missing": len(todo), "no_voice": sorted({x["speaker"] for x in lines if x["state"] == "no_voice"}),
            "estimate": {"characters": est["characters"], "credits": est["credits"], "basis": est["basis"]}}


def scene_voice(d: str, scene: int, confirmed=False, cap_credits=None, items: list | None = None) -> dict:
    """Speak the scene's lines that have no recording, each in its person's voice. One yes and a spending cap in credits cover the whole scene: if the price is above the cap nothing is sent;
    the lines run one by one; a line that fails does not undo the ones that worked; and if a charge is unclear the rest are not attempted."""
    from . import cast_voice as C
    P.require_authorised(confirmed, "voice this scene")
    try:
        cap = float(cap_credits)
    except (TypeError, ValueError):
        cap = 0.0
    if cap <= 0:
        raise SystemExit("Set a spending cap (in ElevenLabs credits) for this scene first. Nothing was sent.")
    plan = scene_plan(d, scene)
    want = {(i.get("shot"), V.key_of(i.get("speaker"))) for i in (items or [])} if items else None
    todo = [x for x in plan["lines"] if x["state"] == "missing" and (want is None or (x["shot"], x["key"]) in want)]
    if not todo:
        return {"scene": int(scene), "results": [], "spent_credits": 0, "cap": cap, "done": 0, "failed": 0, "stopped": None, "note": "Every line in this scene already has a voice."}
    total = sum(x.get("credits", 0) for x in todo)
    if total > cap:
        raise SystemExit(f"Voicing these lines would use about {total:,} credits, which is above your cap of {cap:,.0f}. Nothing was sent. Raise the cap, or voice fewer lines.")
    results, spent, stopped = [], 0.0, None
    for x in todo:
        if stopped:
            results.append({"shot": x["shot"], "speaker": x["speaker"], "ok": False, "attempted": False, "why": stopped})
            continue
        need = x.get("credits", 0)
        if spent + need > cap + 1e-9:
            results.append({"shot": x["shot"], "speaker": x["speaker"], "ok": False, "attempted": False, "why": "Skipped: it would pass your cap."})
            continue
        try:
            r = C.speak(d, x["shot"], x["speaker"], None, True)
            spent += r.get("credits", 0)
            results.append({"shot": x["shot"], "speaker": x["speaker"], "ok": True, "attempted": True, "credits": r.get("credits", 0), "take": r.get("take"), "seconds": r.get("seconds")})
        except SystemExit as e:
            results.append({"shot": x["shot"], "speaker": x["speaker"], "ok": False, "attempted": True, "why": str(e)})
            last = (C._ledger(d).entries() or [{}])[-1]
            if last.get("status") == P.UNCERTAIN:
                stopped = "Stopped: a charge is unclear, so nothing more was sent. Check your ElevenLabs usage, say whether it was charged, then continue."
    return {"scene": int(scene), "results": results, "spent_credits": spent, "cap": cap, "done": sum(1 for r in results if r["ok"]), "failed": sum(1 for r in results if not r["ok"] and r["attempted"]),
            "stopped": stopped}


def table_read(d: str, scene: int) -> dict:
    """The scene's dialogue in order, with the recording or spoken take for each line where there is one, so the whole scene can be listened to before any video is made. Free."""
    V._film(d)
    shots = _scene_shots(d, scene)
    out, total = [], 0.0
    for s in shots:
        for p in s["people"]:
            if not p["lines"]:
                continue
            rec = p.get("recording")
            sec = float((rec or {}).get("seconds") or 0)
            total += sec
            out.append({"shot": s["id"], "speaker": p["name"], "key": p["key"], "text": performance_text(d, s["id"], p["key"]) or " ".join(p["lines"]), "file": (rec or {}).get("file"),
                        "seconds": sec or None, "source": (rec or {}).get("source") or ("recording" if rec else None)})
    return {"scene": int(scene), "lines": out, "seconds": round(total, 2), "silent": sum(1 for x in out if not x["file"])}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="voicedirect")
    ap.add_argument("action", choices=["performance", "performance_set", "performance_clear", "natural_estimate", "natural_suggest", "voices_estimate", "voices_suggest", "voices_match",
                                       "scene_plan", "scene_voice", "table_read"])
    ap.add_argument("target")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    d = os.path.abspath(a.target)
    try:
        x = json.loads(a.data or "{}")
        x = x if isinstance(x, dict) else {}
        act = a.action
        if act == "performance":
            res = get_performance(d)
        elif act == "performance_set":
            res = set_performance(d, x.get("shot", ""), x.get("speaker", ""), x.get("text", ""), x.get("note", ""), x.get("pronunciation", ""), x.get("source", "person"))
        elif act == "performance_clear":
            res = clear_performance(d, x.get("shot", ""), x.get("speaker", ""))
        elif act == "natural_estimate":
            res = natural_estimate(d, x.get("shot", ""), x.get("speaker", ""))
        elif act == "natural_suggest":
            res = natural_suggest(d, x.get("shot", ""), x.get("speaker", ""))
        elif act == "voices_estimate":
            res = voices_estimate(d, x.get("id", ""))
        elif act == "voices_suggest":
            res = voices_suggest(d, x.get("id", ""))
        elif act == "voices_match":
            res = voices_match(d, x.get("id", ""))
        elif act == "scene_plan":
            res = scene_plan(d, x.get("scene", 0))
        elif act == "scene_voice":
            res = scene_voice(d, x.get("scene", 0), x.get("confirmed") is True, x.get("cap_credits"), x.get("items"))
        else:
            res = table_read(d, x.get("scene", 0))
        emit(event="result", data=res)
        return 0
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=__import__("filmcrafter_engine.errtext", fromlist=["plain"]).plain(e))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
