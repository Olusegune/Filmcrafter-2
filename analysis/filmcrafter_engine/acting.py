"""Acting depth: what a performer does moment by moment, how a character's feeling travels through the story, and the habits that make a character themselves.

  beats     A shot's performance as 1 to 6 timed beats ("0 to 2 s: she touches the glasses frame; eyes toward Emmanuel; breath held"). Written by you, or by the Director on
            request (an AI call: the price is shown first, nothing is sent until you say so). They go into the video prompt as a timed sequence, and the first one into the
            keyframe prompt as the opening moment.
  arc       A character's emotion section by section across the song ("Verse 1: stern, 4/10  ->  Chorus 1: flustered, 7/10  ->  Outro: warm, 3/10"). Each shot's prompt says where
            its people are in their arc, so the feeling progresses instead of starting over every shot.
  business  A character's signature gestures ("when flustered: touches the front of her gele"). One that fits the moment is suggested in the prompt.

Everything is kept in <project>/acting.json, a file that can travel with a project from somewhere else, so it is read defensively: wrong shapes are dropped and every text and
number is bounded.

  python -m filmcrafter_engine.acting <action> <project> --data '{...}'
  actions: get | beats_set | beats_clear | beats_estimate | beats_write | arc_set | arc_clear | arc_estimate | arc_write | business_set
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

FILE = "acting.json"
MAX_BEATS, MAX_POINTS, MAX_GESTURES = 6, 24, 8
SHOTS_PER_CALL = 12
# A rough price for the AI brain (OpenAI list prices per million tokens, as of writing): shown as an estimate, never as a promise. A local model costs nothing.
IN_USD_PER_MTOK, OUT_USD_PER_MTOK = 1.25, 10.0


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


def _write(path: str, data) -> None:
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    for i in range(40):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == 39:
                raise
            time.sleep(0.05)


def _txt(v, n: int) -> str:
    return " ".join(str(v or "").split())[:n]


def _num(v, default: float, lo: float, hi: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return default if x != x or x in (float("inf"), float("-inf")) else min(hi, max(lo, x))


# ---------------------------------------------------------------- the file

def load(d: str) -> dict:
    s = _read(os.path.join(d, FILE), {})
    s = s if isinstance(s, dict) else {}
    group = lambda k: {str(a): b for a, b in (s.get(k) if isinstance(s.get(k), dict) else {}).items() if isinstance(b, (dict, list))}
    return {"beats": {k: v for k, v in group("beats").items() if isinstance(v, dict)},
            "arc": {k: v for k, v in group("arc").items() if isinstance(v, dict)},
            "business": {k: v for k, v in group("business").items() if isinstance(v, list)}}


def save(d: str, s: dict) -> None:
    _write(os.path.join(d, FILE), s)


def _plan(d: str) -> dict:
    for name in ("directed", "production"):
        p = _read(os.path.join(d, f"{name}.json"))
        if isinstance(p, dict) and p.get("scenes"):
            return p
    raise SystemExit("This project has no shot plan yet.")


def _shots(plan: dict) -> dict[str, dict]:
    return {sh["id"]: sh for sc in plan.get("scenes", []) for sh in sc.get("shots", []) if isinstance(sh, dict) and sh.get("id")}


def _shot(d: str, shot_id: str) -> dict:
    sh = _shots(_plan(d)).get(str(shot_id))
    if not sh:
        raise SystemExit("That shot is not in the plan.")
    return sh


def _seconds(shot: dict) -> float:
    return max(0.5, float(shot.get("end", 0)) - float(shot.get("start", 0)))


def _characters(plan: dict) -> dict[str, dict]:
    return {c["name"]: c for c in plan.get("characters", []) if isinstance(c, dict) and c.get("name")}


# ---------------------------------------------------------------- beats

def _is_zero(v) -> bool:
    try:
        return float(v) == 0.0
    except (TypeError, ValueError):
        return False


def clean_beats(raw, seconds: float) -> list[dict]:
    """1 to 6 beats, in time order, inside the shot, each with something to do. Anything else in the list is ignored."""
    out, loose = [], []
    for b in raw if isinstance(raw, list) else []:
        if not isinstance(b, dict) or not _txt(b.get("what"), 240):
            continue
        start = _num(b.get("t0"), -1.0, -1.0, seconds)                  # -1: no readable start
        t0 = max(0.0, start)
        t1 = _num(b.get("t1"), min(seconds, t0 + 1.0), 0.0, seconds)
        beat = {"t0": round(t0, 2), "t1": round(max(t1, min(seconds, t0 + 0.3)), 2), "what": _txt(b.get("what"), 240),
                **{k: _txt(b.get(k), 120) for k in ("face", "eyes", "hands", "breath") if _txt(b.get(k), 120)}}
        (loose if start < 0 and not _is_zero(b.get("t0")) else out).append(beat)
    out.sort(key=lambda x: x["t0"])
    out += loose                                                       # these follow the others in the order given
    last = 0.0
    for b in out:                                                      # beats do not overlap: each starts where the one before ended, at the earliest
        b["t0"] = round(max(b["t0"], last), 2)
        b["t1"] = round(min(seconds, max(b["t1"], b["t0"] + 0.3)), 2)
        last = b["t1"]
    return [b for b in out if b["t0"] < seconds][:MAX_BEATS]


def beats_get(d: str, shot_id: str) -> dict:
    sh = _shot(d, shot_id)
    e = load(d)["beats"].get(shot_id) or {}
    return {"shot": shot_id, "seconds": round(_seconds(sh), 2), "beats": clean_beats(e.get("beats"), _seconds(sh)), "source": e.get("source") if e.get("source") in ("you", "director") else None}


def beats_set(d: str, shot_id: str, beats: list, source: str = "you") -> dict:
    sh = _shot(d, shot_id)
    cleaned = clean_beats(beats, _seconds(sh))
    if not cleaned:
        raise SystemExit("Write at least one beat: what the person does, and when.")
    s = load(d)
    s["beats"][shot_id] = {"beats": cleaned, "source": source, "updated": int(time.time())}
    save(d, s)
    return beats_get(d, shot_id)


def beats_clear(d: str, shot_id: str) -> dict:
    _shot(d, shot_id)
    s = load(d)
    s["beats"].pop(shot_id, None)
    save(d, s)
    return beats_get(d, shot_id)


def _detail(b: dict) -> str:
    bits = [f"{k}: {b[k]}" for k in ("face", "eyes", "hands", "breath") if b.get(k)]
    return f" ({'; '.join(bits)})" if bits else ""


def beats_text(d: str, shot: dict, kind: str = "video") -> str | None:
    """The shot's beats as prompt text: a timed sequence for a video, the opening moment for a keyframe. None when it has none."""
    e = load(d)["beats"].get(shot.get("id"))
    if not e:
        return None
    beats = clean_beats(e.get("beats"), _seconds(shot))
    if not beats:
        return None
    if kind == "image":
        b = beats[0]
        return f"Opening moment: {b['what'].rstrip('.')}{_detail(b)}."
    text = "Performance beats, in order: " + "; ".join(f"{b['t0']:g} to {b['t1']:g} s: {b['what'].rstrip('.')}{_detail(b)}" for b in beats) + "."
    return text if len(text) <= 900 else "Performance beats, in order: " + "; ".join(f"{b['t0']:g} to {b['t1']:g} s: {b['what'].rstrip('.')}" for b in beats) + "."


# ---------------------------------------------------------------- the arc

def sections(d: str) -> list[dict]:
    from .choreo import numbered_sections
    sm = _read(os.path.join(d, "songmap.json"), {}) or {}
    return numbered_sections(sm) if isinstance(sm, dict) else []


def clean_arc(raw, names: list[str]) -> list[dict]:
    """Points on the song's own sections (an unknown section is dropped), in song order, at most one per section; intensity 1 to 10."""
    by = {n.lower(): n for n in names}
    seen, out = set(), []
    for p in raw if isinstance(raw, list) else []:
        if not isinstance(p, dict):
            continue
        sec = by.get(_txt(p.get("section"), 60).lower())
        if not sec or sec in seen or not _txt(p.get("emotion"), 80):
            continue
        seen.add(sec)
        out.append({"section": sec, "emotion": _txt(p.get("emotion"), 80), "intensity": int(round(_num(p.get("intensity"), 5, 1, 10))), "note": _txt(p.get("note"), 160)})
    out.sort(key=lambda x: names.index(x["section"]))
    return out[:MAX_POINTS]


def arc_get(d: str) -> dict:
    plan = _plan(d)
    names = [s["name"] for s in sections(d)]
    chars = _characters(plan)
    stored = load(d)["arc"]
    return {"sections": names, "characters": list(chars),
            "arcs": {c: {"points": clean_arc((stored.get(c) or {}).get("points"), names), "source": (stored.get(c) or {}).get("source")} for c in chars}}


def arc_set(d: str, character: str, points: list, source: str = "you") -> dict:
    if character not in _characters(_plan(d)):
        raise SystemExit("That character is not in the plan.")
    names = [s["name"] for s in sections(d)]
    if not names:
        raise SystemExit("The song has not been listened to yet, so it has no sections to put an arc on.")
    cleaned = clean_arc(points, names)
    s = load(d)
    if cleaned:
        s["arc"][character] = {"points": cleaned, "source": source, "updated": int(time.time())}
    else:
        s["arc"].pop(character, None)
    save(d, s)
    return arc_get(d)


def _section_of(d: str, shot: dict, names: list[dict]) -> str | None:
    from .choreo import section_at
    if shot.get("section"):
        want = str(shot["section"]).lower().strip("[] ")
        hit = next((s["name"] for s in names if s["name"].lower() == want or s["base"].lower() == want), None)
        if hit:
            return hit
    mid = (float(shot.get("start", 0)) + float(shot.get("end", 0))) / 2
    sec = section_at(names, mid)
    return sec["name"] if sec else None


def arc_text(d: str, shot: dict) -> str | None:
    """Where each person in the shot is in their arc, in a line for the prompt. None when nobody in it has an arc, or the shot's section is not on their arc."""
    performers = [p for p in shot.get("performers") or [] if isinstance(p, str)]
    stored = load(d)["arc"]
    if not performers or not any(p in stored for p in performers):
        return None
    names = sections(d)
    sec = _section_of(d, shot, names)
    order = [s["name"] for s in names]
    if not sec:
        return None
    lines = []
    for p in performers[:3]:
        pts = clean_arc((stored.get(p) or {}).get("points"), order)
        here = next((x for x in pts if x["section"] == sec), None)
        if not here:
            continue
        i = pts.index(here)
        parts = [f"{p} is {here['emotion']} at this point of the story (about {here['intensity']}/10)"]
        if i > 0:
            parts.append(f"coming from {pts[i - 1]['emotion']}")
        if i + 1 < len(pts):
            parts.append(f"heading towards {pts[i + 1]['emotion']}")
        lines.append(", ".join(parts) + ".")
    return ("Emotional arc: " + " ".join(lines)) if lines else None


# ---------------------------------------------------------------- business

def clean_business(raw) -> list[dict]:
    out = []
    for g in raw if isinstance(raw, list) else []:
        if isinstance(g, dict) and _txt(g.get("when"), 60) and _txt(g.get("do"), 160):
            out.append({"when": _txt(g.get("when"), 60), "do": _txt(g.get("do"), 160)})
    return out[:MAX_GESTURES]


def business_set(d: str, character: str, items: list) -> dict:
    if character not in _characters(_plan(d)):
        raise SystemExit("That character is not in the plan.")
    s = load(d)
    cleaned = clean_business(items)
    if cleaned:
        s["business"][character] = cleaned
    else:
        s["business"].pop(character, None)
    save(d, s)
    return get(d)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", (text or "").lower())}


def business_text(d: str, shot: dict) -> str | None:
    """One or two of each person's signature gestures: the ones whose 'when' shares a word with the shot's emotion, expression, performance or action; else the first."""
    stored = load(d)["business"]
    mood = _words(" ".join(str(shot.get(k) or "") for k in ("emotion", "expression", "performance", "description", "movement")))
    lines = []
    for p in [x for x in shot.get("performers") or [] if isinstance(x, str)][:3]:
        items = clean_business(stored.get(p))
        if not items:
            continue
        fit = [g for g in items if _words(g["when"]) & mood]
        for g in (fit or items[:1])[:2]:
            lines.append(f"{p}, when {g['when'].rstrip('.')}: {g['do'].rstrip('.')}.")
    return ("Signature gestures (use one only if it fits this moment): " + " ".join(lines)) if lines else None


# ---------------------------------------------------------------- AI: price first, then write

def _client():
    from .director import _client as c
    return c()


def _estimate(prompt_chars: int, calls: int, out_tokens: int) -> dict:
    from .llm import is_local, price_per_mtok
    if is_local():
        return {"calls": calls, "usd": 0.0, "local": True, "note": "Your local model does the writing: free."}
    tok_in = prompt_chars / 4 + 350
    price = price_per_mtok()                                  # OpenRouter: the real price of the model chosen
    pin, pout = price if price else (IN_USD_PER_MTOK, OUT_USD_PER_MTOK)
    usd = calls * (tok_in * pin + out_tokens * pout) / 1e6
    note = "From OpenRouter's price for the model you chose and the size of the request." if price else "A rough estimate from the size of the request; your provider's own price applies."
    return {"calls": calls, "usd": round(usd, 4), "local": False, "note": note}


BEATS_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["beats"], "properties": {"beats": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["t0", "t1", "what", "face", "eyes", "hands", "breath"],
    "properties": {"t0": {"type": "number"}, "t1": {"type": "number"}, "what": {"type": "string"}, "face": {"type": "string"}, "eyes": {"type": "string"},
                   "hands": {"type": "string"}, "breath": {"type": "string"}}}}}}

BEATS_SYSTEM = """You are an acting coach for an animated film. For ONE shot, write 2 to 4 timed performance beats that a video model can show.
Each beat: what the person does (one concrete physical action), and where it helps, the face, the eyes (where they look, when they move), the hands, the breath.
Rules: stay inside the shot's duration and in time order; a close framing needs small, readable actions (eyes, brow, mouth, a hand), a wide framing needs bigger ones;
show the feeling through behaviour, not by naming it; use the character's signature gestures only where they fit; follow their emotional arc; never invent dialogue,
cast, props or camera moves; no more than one idea per beat; plain words."""


def _beats_brief(d: str, shot: dict, plan: dict) -> dict:
    chars = _characters(plan)
    stored = load(d)
    people = []
    for n in [x for x in shot.get("performers") or [] if isinstance(x, str)][:3]:
        c = chars.get(n, {})
        people.append({"name": n, "look": _txt(c.get("appearance"), 200), "acting_notes": _txt(c.get("acting_notes"), 200),
                       "signature_gestures": clean_business(stored["business"].get(n))})
    return {"shot": shot.get("id"), "seconds": round(_seconds(shot), 2), "what_happens": _txt(shot.get("description") or " ".join(shot.get("beats") or []), 400),
            "framing": _txt(shot.get("framing"), 80), "lens": _txt(shot.get("lens"), 60), "purpose": _txt(shot.get("purpose"), 200), "emotion": _txt(shot.get("emotion"), 100),
            "intensity_1_to_10": shot.get("performance_intensity"), "performance": _txt(shot.get("performance"), 300), "expression": _txt(shot.get("expression"), 300),
            "movement": _txt(shot.get("movement"), 300), "lines_in_this_shot": [_txt(x, 160) for x in shot.get("lyrics") or []][:4], "people": people,
            "arc": arc_text(d, shot)}


def _pick_shots(d: str, ids, overwrite: bool) -> list[dict]:
    plan = _plan(d)
    shots = _shots(plan)
    have = load(d)["beats"]
    want = [str(i) for i in (ids or []) if str(i) in shots]
    if not want:
        raise SystemExit("Choose at least one shot.")
    todo = [shots[i] for i in want if overwrite or i not in have]
    return todo[:SHOTS_PER_CALL]


def beats_estimate(d: str, shot_ids, overwrite: bool = False) -> dict:
    plan = _plan(d)
    todo = _pick_shots(d, shot_ids, overwrite)
    chars = sum(len(json.dumps(_beats_brief(d, s, plan), ensure_ascii=False)) + len(BEATS_SYSTEM) for s in todo)
    return {**_estimate(chars, len(todo), 350), "shots": [s["id"] for s in todo]}


def beats_write(d: str, shot_ids, notes: str = "", overwrite: bool = False) -> dict:
    """Ask the Director for beats, one shot at a time. Beats you wrote yourself are kept unless `overwrite`."""
    from .director import DEFAULT_MODEL, openai_error, resolve_model
    plan = _plan(d)
    todo = _pick_shots(d, shot_ids, overwrite)
    if not todo:
        return {"written": [], "skipped": [str(i) for i in shot_ids or []], "note": "Those shots already have beats; choose to replace them to write new ones."}
    client = _client()
    model = resolve_model(client, DEFAULT_MODEL)
    done, failed = [], {}
    for i, shot in enumerate(todo):
        emit(event="progress", stage=f"writing beats for {shot['id']}", progress=round(i / len(todo), 3))
        brief = _beats_brief(d, shot, plan)
        if notes.strip():
            brief["director_notes"] = _txt(notes, 400)
        try:
            resp = client.responses.create(model=model, input=[{"role": "system", "content": BEATS_SYSTEM}, {"role": "user", "content": json.dumps(brief, ensure_ascii=False)}],
                                           text={"format": {"type": "json_schema", "name": "beats", "schema": BEATS_SCHEMA, "strict": True}})
            beats_set(d, shot["id"], json.loads(resp.output_text).get("beats"), "director")
            done.append(shot["id"])
        except SystemExit as e:
            failed[shot["id"]] = str(e)
        except Exception as e:                                         # one shot failing does not lose the others
            failed[shot["id"]] = openai_error(e)
    emit(event="progress", stage="done", progress=1.0)
    return {"written": done, "failed": failed, "model": model}


ARC_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["characters"], "properties": {"characters": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["name", "points"], "properties": {"name": {"type": "string"}, "points": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["section", "emotion", "intensity", "note"],
        "properties": {"section": {"type": "string"}, "emotion": {"type": "string"}, "intensity": {"type": "integer"}, "note": {"type": "string"}}}}}}}}}

ARC_SYSTEM = """You are the story editor of an animated music film. For each character given, write their emotional arc across the song's sections: one point per
section they are present in, using the section names exactly as given. Each point: the feeling in two or three words, an intensity from 1 (barely) to 10 (overwhelming),
and one short note on what drives it. The arc must move: a character should not feel the same in every section unless the story needs it; peaks belong to the song's loud
sections and quiet sections stay small. Use only the characters and sections given; do not invent either."""


def _arc_brief(d: str, characters: list[str]) -> dict:
    plan = _plan(d)
    chars = _characters(plan)
    sm = _read(os.path.join(d, "songmap.json"), {}) or {}
    secs = sections(d)
    lines: dict[str, list[str]] = {}
    for ln in sm.get("lyrics") or []:
        if isinstance(ln, dict) and ln.get("text") and ln.get("start") is not None:
            sec = _section_of(d, {"start": ln["start"], "end": ln["start"]}, secs)
            if sec and len(lines.setdefault(sec, [])) < 3:
                lines[sec].append(_txt(ln["text"], 120))
    treat = _read(os.path.join(d, "treatment.json"), {}) or {}
    concept = treat.get("concept") if isinstance(treat, dict) and isinstance(treat.get("concept"), dict) else {}
    return {"story": _txt(concept.get("premise"), 500), "sections": [{"name": s["name"], "mood": s.get("mood"), "energy": s.get("energy"), "lyric_lines": lines.get(s["name"], [])} for s in secs],
            "characters": [{"name": n, "look": _txt(chars[n].get("appearance"), 200), "motivation": _txt(chars[n].get("motivation"), 200), "acting_notes": _txt(chars[n].get("acting_notes"), 200)}
                           for n in characters]}


def arc_estimate(d: str, characters=None) -> dict:
    chars = [c for c in (characters or list(_characters(_plan(d)))) if c in _characters(_plan(d))]
    if not chars:
        raise SystemExit("Choose at least one character.")
    return {**_estimate(len(json.dumps(_arc_brief(d, chars), ensure_ascii=False)) + len(ARC_SYSTEM), 1, 120 * len(chars) + 100), "characters": chars}


def arc_write(d: str, characters=None, notes: str = "") -> dict:
    from .director import DEFAULT_MODEL, openai_error, resolve_model
    allc = _characters(_plan(d))
    chars = [c for c in (characters or list(allc)) if c in allc]
    if not chars:
        raise SystemExit("Choose at least one character.")
    if not sections(d):
        raise SystemExit("The song has not been listened to yet, so it has no sections to put an arc on.")
    client = _client()
    model = resolve_model(client, DEFAULT_MODEL)
    brief = _arc_brief(d, chars)
    if notes.strip():
        brief["director_notes"] = _txt(notes, 400)
    emit(event="progress", stage="writing the emotional arc", progress=0.2)
    try:
        resp = client.responses.create(model=model, input=[{"role": "system", "content": ARC_SYSTEM}, {"role": "user", "content": json.dumps(brief, ensure_ascii=False)}],
                                       text={"format": {"type": "json_schema", "name": "arc", "schema": ARC_SCHEMA, "strict": True}})
        out = json.loads(resp.output_text)
    except Exception as e:
        raise SystemExit(openai_error(e))
    names = [s["name"] for s in sections(d)]
    s = load(d)
    written = []
    for c in out.get("characters") or []:
        if isinstance(c, dict) and c.get("name") in chars:
            pts = clean_arc(c.get("points"), names)
            if pts:
                s["arc"][c["name"]] = {"points": pts, "source": "director", "updated": int(time.time())}
                written.append(c["name"])
    save(d, s)
    emit(event="progress", stage="done", progress=1.0)
    return {"written": written, "model": model, **arc_get(d)}


# ---------------------------------------------------------------- the screen's view

def get(d: str) -> dict:
    s = load(d)
    plan = _plan(d)
    chars = list(_characters(plan))
    return {"business": {c: clean_business(s["business"].get(c)) for c in chars}, "beats_shots": sorted(k for k, v in s["beats"].items() if clean_beats(v.get("beats"), 3600)),
            "arc": arc_get(d)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-acting")
    ap.add_argument("action", choices=["get", "beats_get", "beats_set", "beats_clear", "beats_estimate", "beats_write", "arc_set", "arc_clear", "arc_estimate", "arc_write", "business_set"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    try:
        x = json.loads(a.data)
        x = x if isinstance(x, dict) else {}
        d, act = a.project, a.action
        if act == "get":
            res = get(d)
        elif act == "beats_get":
            res = beats_get(d, str(x.get("shot", "")))
        elif act == "beats_set":
            res = beats_set(d, str(x.get("shot", "")), x.get("beats"))
        elif act == "beats_clear":
            res = beats_clear(d, str(x.get("shot", "")))
        elif act == "beats_estimate":
            res = beats_estimate(d, x.get("shots"), bool(x.get("overwrite")))
        elif act == "beats_write":
            res = beats_write(d, x.get("shots"), str(x.get("notes", "")), bool(x.get("overwrite")))
        elif act == "arc_set":
            res = arc_set(d, str(x.get("character", "")), x.get("points"))
        elif act == "arc_clear":
            res = arc_set(d, str(x.get("character", "")), [])
        elif act == "arc_estimate":
            res = arc_estimate(d, x.get("characters"))
        elif act == "arc_write":
            res = arc_write(d, x.get("characters"), str(x.get("notes", "")))
        else:
            res = business_set(d, str(x.get("character", "")), x.get("items"))
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
