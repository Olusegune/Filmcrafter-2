"""The sound plan: for every shot with dialogue, how its voice will be made, why, and what it will take.

FilmCrafter already has all the parts of a film's voice: your own recordings, spoken lines from your ElevenLabs voices, a video model that follows a recording, a lip-sync pass for a mouth, a model
that speaks for itself, and a mix at export. What was missing was one place that says, shot by shot, which of them applies, so that nobody pays for sound they do not need and nobody is surprised.
This reads the film as it is and answers, for each shot:

  none          nobody speaks: the picture is made without a voice and nothing is spent on sound
  voice_over    a narrator or a voice that is not on screen (V.O., O.S., a narrator): the picture is made silent, with no lip-sync, and the voice is mixed in at export
  needs_voice   somebody on screen speaks and there is no voice for the line yet (record it, or speak it with the character's voice, price first)
  audio_in      one or more people on screen speak, and the video model can be given the recording to follow, so the mouth follows it
  post_sync     the recording is laid over the picture at export; the mouth is matched by the picture's own motion, or a lip-sync pass if you want one (price first)
  native        two or more people speak and the video model makes its own sound (the scene's native dialogue switch speaks for them)

It also checks each line against its shot (a shot too short for its line), counts the lines that still need a voice and what speaking them would use of your plan, and says how many tries to
allow for. The route it names is what the film does today by its existing rules; the only thing it can change is the shot's "someone on screen sings or speaks this" setting (auto, on, off),
which was already yours to set, and only when you ask. Free and local: it makes and buys nothing.

  python -m filmcrafter_engine.audioplan <report|apply|set> <film_dir> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

from . import safeio

VO_EXT = ("V.O.", "O.S.")
VO_NAME = re.compile(r"^(narrator|narration|voice[- ]?over|announcer|v\.?o\.?)$", re.I)
KEEP = {"draft": 0.6, "final": 0.85}            # the share of generations kept; the plan allows for 1 / keep tries
SETTINGS = ("auto", "on", "off")
MAX_SPEAKERS = 3


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


def _film(d: str) -> None:
    m = safeio.read_json(os.path.join(d, "film.json"), None)
    if not isinstance(m, dict) or "story" not in m:
        raise SystemExit("That isn't a FilmCrafter film.")


def is_voice_over(line: dict) -> bool:
    """A line nobody on screen speaks: marked V.O. or O.S. in the script, or said by a narrator."""
    return str(line.get("ext") or "").upper() in VO_EXT or bool(VO_NAME.match(str(line.get("speaker") or "").strip()))


def _caps(rd: str, tier: str) -> dict:
    """What the video model Auto would use can take: {"model", "ref_audio", "audio"}; all False when it cannot be told (nothing is guessed)."""
    out = {"model": "", "ref_audio": False, "audio": False, "known": False}
    try:
        from . import render, routing
        project = safeio.read_json(os.path.join(rd, "project.json"), {}) or {}
        pk = routing.pick(project, "video")
        if not pk.get("provider"):
            return out
        man = render.manifest(pk["provider"], pk["model"])
        roles = man.get("roles") or {}
        return {"model": pk.get("label") or pk["model"], "ref_audio": "ref_audio" in roles, "audio": "audio" in roles, "known": True}
    except Exception:
        return out


def _setting(rd: str, sid: str) -> str:
    v = ((safeio.read_json(os.path.join(rd, "project.json"), {}) or {}).get("sing_shots") or {}).get(sid)
    return v if v in ("on", "off") else "auto"


def report(d: str, tier: str = "draft") -> dict:
    from . import cast_voice, make, shots as S, voiceover
    _film(d)
    tier = tier if tier in KEEP else "draft"
    rd = make.render_dir(d)
    cons = {sid: S._read(S._cpath(d, sid)) for sid in S._index(d).get("order", [])}
    cons = {k: v for k, v in cons.items() if isinstance(v, dict)}
    if not cons:
        raise SystemExit("There are no shots yet. Break the story down first.")
    vs = {s["id"]: s for s in voiceover.status(d)["shots"]}
    caps = _caps(rd, tier)
    native = bool((safeio.read_json(os.path.join(rd, "dialogue.json"), {}) or {}).get("native"))
    rows, speak_items = [], []
    for sid, c in cons.items():
        dl = [x for x in c.get("dialogue") or [] if str(x.get("line") or "").strip()]
        v = vs.get(sid)
        people = {p["key"]: p for p in (v or {}).get("people", [])}
        lines = []
        for x in dl:
            key = voiceover.key_of(x["speaker"])
            rec = (people.get(key) or {}).get("recording")
            lines.append({"speaker": voiceover.pretty(x["speaker"]), "line": x["line"], "voice_over": is_voice_over(x), "has_voice": bool(rec), "source": (rec or {}).get("source", "")})
        onscreen = [x for x in lines if not x["voice_over"]]
        speakers = sorted({x["speaker"] for x in onscreen})
        warnings: list[str] = []
        missing = [x for x in lines if not x["has_voice"]]
        if not lines:
            route, why = "none", "Nobody speaks, so the picture is made without a voice and nothing is spent on sound."
        elif not onscreen:
            route, why = "voice_over", "A voice-over: nobody on screen is speaking. The picture is made silent with no lip-sync, and the voice is mixed in when the film is exported."
        elif any(not x["has_voice"] for x in onscreen):
            route, why = "needs_voice", "Somebody on screen speaks and a line has no voice yet: record it, or speak it with the character's voice (the price is shown first)."
        elif len(speakers) >= 2 and native and caps["audio"]:
            route, why = "native", "Two or more people speak and this scene's dialogue is spoken by the video model, which makes its own sound."
        elif caps["ref_audio"]:
            route, why = "audio_in", ("The video model is given the recording of " + " and ".join(speakers) + (", one after the other," if len(speakers) > 1 else "") + " so the mouth follows it.")
        else:
            route, why = "post_sync", "The recording is laid over the picture when the film is exported. " + ("The model cannot be given a recording, so the mouth follows the words in the picture; a lip-sync pass can match it better (price first)." if caps["known"] else "")
        if len(speakers) > MAX_SPEAKERS:
            warnings.append(f"{len(speakers)} people speak in one shot: video models handle a conversation of two or three at most. Consider splitting the shot.")
        for n in (v or {}).get("notes", []):
            warnings.append(n)
        secs = float((c.get("generation") or {}).get("duration") or 3.0)
        need = sum(len(str(x["line"]).split()) for x in lines) / 2.5 + 0.8 if lines else 0.0
        if lines and secs < need * 0.9:
            warnings.append(f"The shot lasts {secs:.1f} s but its lines need about {need:.1f} s.")
        for x in missing:
            speak_items.append({"shot": sid, "speaker": x["speaker"], "text": x["line"]})
        current = _setting(rd, sid)
        rec_setting = "off" if route == "voice_over" else "auto"
        rows.append({"shot": sid, "scene": c["scene"], "title": c.get("title", ""), "seconds": secs, "lines": lines, "speakers": speakers, "route": route, "why": why, "warnings": warnings,
                     "setting": current, "recommended_setting": rec_setting, "differs": route == "voice_over" and current != "off"})
    credits = 0
    unpriced = 0
    try:
        est = cast_voice.estimate(d, speak_items) if speak_items else {"rows": [], "credits": 0}
        credits = int(est.get("credits") or 0)
        unpriced = sum(1 for r in est.get("rows", []) if not r.get("ok"))
    except SystemExit:
        unpriced = len(speak_items)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["route"]] = counts.get(r["route"], 0) + 1
    keep = float((safeio.read_json(os.path.join(rd, "project.json"), {}) or {}).get("audio_plan", {}).get("keep_" + tier, KEEP[tier])) if os.path.isfile(os.path.join(rd, "project.json")) else KEEP[tier]
    keep = min(1.0, max(0.2, keep))
    return {"tier": tier, "model": caps["model"], "model_known": caps["known"], "model_takes_recording": caps["ref_audio"], "model_makes_sound": caps["audio"], "native_scene": native,
            "shots": rows, "counts": counts, "lines_to_speak": len(speak_items), "tts_credits": credits, "tts_unpriced": unpriced,
            "keep_rate": keep, "tries": round(1 / keep, 2),
            "note": "The route is what the film does today by its existing rules. Nothing here makes or buys anything; the only thing Apply changes is the shot's own on or off setting for who speaks on screen."}


def set_setting(d: str, shot: str, value: str) -> dict:
    """The shot's 'someone on screen speaks this' setting: auto, on or off (what the Video tab's lip-sync note already offers)."""
    from . import make
    from .safe import check_id
    _film(d)
    sid = check_id(shot, "shot")
    if value not in SETTINGS:
        raise SystemExit("Choose auto, on or off.")
    path = os.path.join(make.render_dir(d), "project.json")
    if not os.path.isfile(path):
        make.sync(d)
    pj = safeio.read_json(path, {}) or {}
    ss = dict(pj.get("sing_shots") or {})
    if value == "auto":
        ss.pop(sid, None)
    else:
        ss[sid] = value
    pj["sing_shots"] = ss
    safeio.write_json(path, pj)
    return {"shot": sid, "setting": value}


def apply(d: str, tier: str = "draft") -> dict:
    """Mark the voice-over shots 'off' (nobody on screen speaks). A shot you already set yourself is never changed; nothing else is touched."""
    r = report(d, tier)
    done = []
    for row in r["shots"]:
        if row["route"] == "voice_over" and row["setting"] == "auto":
            set_setting(d, row["shot"], "off")
            done.append(row["shot"])
    return {"changed": done, **report(d, tier)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="audioplan")
    ap.add_argument("action", choices=["report", "apply", "set"])
    ap.add_argument("film")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    try:
        x = json.loads(a.data or "{}")
        x = x if isinstance(x, dict) else {}
        d = os.path.abspath(a.film)
        if a.action == "report":
            res = report(d, x.get("tier", "draft"))
        elif a.action == "apply":
            res = apply(d, x.get("tier", "draft"))
        else:
            set_setting(d, x.get("shot", ""), x.get("value", ""))
            res = report(d, x.get("tier", "draft"))
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
