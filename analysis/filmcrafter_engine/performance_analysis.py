"""The Performance Breakdown: for each scene, what it is for, what each person wants and is hiding, what is said against what is meant, and where the turns are.

A free, local DRAFT built from what the film already knows (the shot contracts' purpose, action, dialogue and dramatic beats; or, in a project that is not a film, the plan's shots). It
reads; it never writes to the screenplay, the shots or the Bible. Every field says where it came from and is editable:

  fields     {"value": text, "source": "auto" | "you", "from": where the draft came from}
  your edit  kept in <film>/performance/scenes.json and never replaced by a refresh; "reset" goes back to the draft, "accept" keeps the draft as yours

A draft never reaches a prompt. Only what you wrote or accepted does (`inner_text`), so a guess cannot quietly steer a paid render. Dialogue is quoted exactly and never changed: "what is
said" and "what is meant" are kept apart, and an automatic reading of what is meant says how sure it is and why.

  python -m filmcrafter_engine.performance_director breakdown_get | breakdown_set | breakdown_reset | breakdown_accept | beats_suggest ...
"""
from __future__ import annotations

import os
import re
import time

from . import character_performance as CP
from . import safeio

FILE = "scenes.json"
SCHEMA = 1
SCENE_FIELDS = ("purpose", "start", "end", "tension")
PERSON_FIELDS = ("wants", "obstacle", "outward", "inner", "hiding")
MAX = 400

# what people say when they are not saying it, and what a scene shows when something is underneath (words, not feelings: this can only suggest)
DEFLECTION = re.compile(r"\b(?:i'?m|i am)\s+(?:fine|ok|okay|alright|good|not (?:upset|angry|crying|sad|worried|scared|bothered))\b|\bit'?s\s+(?:fine|nothing|okay|ok|alright)\b|"
                        r"\bnever\s*mind\b|\bdon'?t worry\b|\bno,?\s+really\b|\bwhatever\b|\bi don'?t care\b", re.I)
DISTRESS = re.compile(r"\b(?:tears?|cry\w*|cried|trembl\w*|shak\w*|grief|griev\w*|devastat\w*|panic\w*|distress\w*|upset|hurt|ach\w*|broken|chok\w*|swallow\w*|numb|hollow|withdrawn|"
                      r"sobb?\w*|heartbr\w*|anguish\w*|fight(?:s|ing)? back|can'?t look|will not look|avoid\w* (?:his|her|their) (?:eyes|gaze))\b", re.I)


def _txt(v, n: int = MAX) -> str:
    return " ".join(str(v or "").split())[:n]


def _path(d: str) -> str:
    return os.path.join(CP.root(d), FILE)


def _stored(d: str) -> dict:
    try:
        s = safeio.read_json(_path(d), {})
    except SystemExit:
        s = {}
    return s if isinstance(s, dict) and isinstance(s.get("scenes"), dict) else {"schema": SCHEMA, "scenes": {}}


def _key(name: str) -> str:
    return " ".join(str(name or "").lower().split())


# ---------------------------------------------------------------- what the film knows, in one shape

def _inputs(d: str) -> tuple[list[dict], bool]:
    """[{number, heading, shots: [info]}] from the plan, each shot enriched from its contract when the project is a film; and whether contracts were found."""
    from . import acting
    plan = acting._plan(d)
    contracts: dict[str, dict] = {}
    f = CP.film_dir(d)
    if f:
        from . import make
        try:
            contracts = {c["id"]: c for c in make._contracts(f) if isinstance(c, dict) and c.get("id")}
        except Exception:
            contracts = {}
    scenes = []
    for sc in plan.get("scenes", []):
        shots = []
        for sh in sc.get("shots", []):
            if not isinstance(sh, dict) or not sh.get("id"):
                continue
            c = contracts.get(sh["id"]) or {}
            perf = c.get("performance") if isinstance(c.get("performance"), dict) else {}
            people = [p for p in sh.get("performers") or [] if isinstance(p, str)] or [x.get("name") for x in c.get("characters") or [] if isinstance(x, dict) and x.get("name")]
            dialogue = [{"speaker": _txt(x.get("speaker"), 60), "line": _txt(x.get("line"), 400)} for x in c.get("dialogue") or [] if isinstance(x, dict) and _txt(x.get("line"))]
            if not dialogue:
                dialogue = [{"speaker": "", "line": _txt(x, 400)} for x in sh.get("lyrics") or [] if _txt(x)]
            shots.append({"id": sh["id"], "seconds": max(0.5, float(sh.get("end", 0)) - float(sh.get("start", 0))), "people": people,
                          "intention": _txt(perf.get("emotional_intention") or sh.get("emotion"), 200), "purpose": _txt(c.get("story_purpose") or sh.get("purpose"), 300),
                          "action": _txt(c.get("action") or sh.get("description") or " ".join(sh.get("beats") or []), 400), "dialogue": dialogue,
                          "beats": [b for b in perf.get("beats") or [] if isinstance(b, dict)], "opening": _txt(c.get("opening_state"), 200), "closing": _txt(c.get("closing_state"), 200),
                          "expression": _txt(sh.get("expression"), 200), "performance": _txt(sh.get("performance"), 200)})
        scenes.append({"number": sc.get("number"), "heading": sc.get("heading") or f"Scene {sc.get('number')}", "shots": shots})
    return scenes, bool(contracts)


# ---------------------------------------------------------------- the draft

def _f(value: str, origin: str) -> dict:
    return {"value": _txt(value), "source": "auto", "from": origin if value else ""}


def _canon(name: str, names: list[str]) -> str:
    return next((n for n in names if _key(n) == _key(name)), name)


def _scene_draft(d: str, sc: dict, names: list[str]) -> dict:
    shots = sc["shots"]
    purposes = list(dict.fromkeys(s["purpose"] for s in shots if s["purpose"]))
    first = next((s for s in shots if s["intention"]), None)
    last = next((s for s in reversed(shots) if s["intention"]), None)
    start = (first["intention"], f"shot {first['id']}") if first else next(((s["opening"], f"shot {s['id']}") for s in shots if s["opening"]), ("", ""))
    end = (last["intention"], f"shot {last['id']}") if last and last is not first else next(((s["closing"], f"shot {s['id']}") for s in reversed(shots) if s["closing"]), ("", ""))
    people = list(dict.fromkeys(_canon(p, names) for s in shots for p in s["people"]))
    relations = []
    f = CP.film_dir(d)
    if f:
        from . import bible
        for c in bible.load(f).get("characters", []):
            nm = c["name"].title() if c["name"].isupper() else c["name"]
            if nm in people and _txt(c.get("relationships"), 240):
                relations.append(f"{nm}: {_txt(c['relationships'], 240)}")
    scene_fields = {"purpose": _f(" ".join(purposes)[:MAX], "the shots' story purposes"), "start": _f(start[0], start[1]), "end": _f(end[0], end[1]),
                    "tension": _f(" ".join(relations)[:MAX], "the cast notes")}
    persons = []
    turning, nonverbal, reactions, subtext = [], [], [], []
    for p in people:
        own = [(s, b) for s in shots for b in s["beats"] if _key(b.get("character")) == _key(p)]
        pick = lambda k: next((_txt(b.get(k)) for _, b in own if _txt(b.get(k))), "")
        wants, fear, need, hiding = pick("want"), pick("fear"), pick("need"), pick("hiding")
        outward = next((_txt(b.get("what")) for _, b in own if _txt(b.get("what"))), "") or next((s["expression"] or s["performance"] for s in shots if p in [_canon(x, names) for x in s["people"]] and (s["expression"] or s["performance"])), "")
        origin = lambda k, v: (f"the story beats of {', '.join(dict.fromkeys(s['id'] for s, b in own if _txt(b.get(k))))}" if v else "")
        persons.append({"name": p, "wants": _f(wants, origin("want", wants)), "obstacle": _f(fear, origin("fear", fear)), "outward": _f(outward, "what the shot shows" if outward else ""),
                        "inner": _f(need or fear, origin("need" if need else "fear", need or fear)), "hiding": _f(hiding, origin("hiding", hiding))})
    scene_text = [(s["id"], " ".join([s["action"], s["intention"], s["expression"], s["performance"]] + [_txt(b.get(k)) for b in s["beats"] for k in ("hiding", "subtext", "fear", "need")])) for s in shots]
    for s in shots:
        speakers = {_key(x["speaker"]) for x in s["dialogue"] if x["speaker"]}
        for b in s["beats"]:
            if _txt(b.get("turn")):
                turning.append({"shot": s["id"], "person": _canon(_txt(b.get("character"), 60), names), "what": _txt(b["turn"])})
        if s["people"] and not s["dialogue"] and s["action"]:
            nonverbal.append({"shot": s["id"], "what": _txt(s["action"], 200)})
        if speakers and s["dialogue"]:
            for p in s["people"]:
                if _key(p) not in speakers:
                    who = next((x["speaker"] for x in s["dialogue"] if x["speaker"]), "the speaker")
                    reactions.append({"shot": s["id"], "person": _canon(p, names), "what": f"listens to {who.title() if who.isupper() else who}"})
        found = next(((sid, m) for sid, text in sorted(scene_text, key=lambda t: t[0] != s["id"]) for m in [DISTRESS.search(text)] if m), None)     # this shot first, then the rest of the scene
        for i, x in enumerate(s["dialogue"]):
            who = _canon(x["speaker"], names) if x["speaker"] else (s["people"][0] if s["people"] else "")
            own_sub = next((_txt(b.get("subtext")) for b in s["beats"] if _txt(b.get("subtext")) and (not who or _key(b.get("character")) == _key(who))), "")
            hit = DEFLECTION.search(x["line"])
            if own_sub:
                subtext.append({"id": f"{s['id']}:{i}", "shot": s["id"], "person": who, "says": x["line"], "means": _f(own_sub, f"the story beat of {s['id']}"), "confidence": "high",
                                "why": "You wrote what this line means in the story beat."})
            elif hit:
                if found:
                    where = "the shot" if found[0] == s["id"] else f"shot {found[0]}"
                    subtext.append({"id": f"{s['id']}:{i}", "shot": s["id"], "person": who, "says": x["line"],
                                    "means": _f(f"{who or 'The speaker'} may be hiding how they really feel", f"the words of {where}"), "confidence": "medium",
                                    "why": f"The line (\"{hit.group(0)}\") is a deflection, and {where} mentions \"{found[1].group(0)}\". This is a reading, not a fact: say what it means."})
                else:
                    subtext.append({"id": f"{s['id']}:{i}", "shot": s["id"], "person": who, "says": x["line"], "means": _f("", ""), "confidence": "low",
                                    "why": f"The line (\"{hit.group(0)}\") often says less than it means, but nothing in the shot says what is underneath: write it here if it does."})
    return {"number": sc["number"], "heading": sc["heading"], "shots": [s["id"] for s in shots], "fields": scene_fields, "people": persons, "subtext": subtext,
            "turning_points": turning, "nonverbal": nonverbal, "reactions": reactions}


def _apply(draft: dict, mine: dict) -> dict:
    """Put the person's own edits over the draft: each edited field says source "you"."""
    mark = lambda cur, o: {"value": o["value"], "source": "you", "from": "your edit"} if isinstance(o, dict) and "value" in o else cur
    for k in SCENE_FIELDS:
        draft["fields"][k] = mark(draft["fields"][k], (mine.get("fields") or {}).get(k))
    for p in draft["people"]:
        for k in PERSON_FIELDS:
            p[k] = mark(p[k], ((mine.get("people") or {}).get(p["name"]) or {}).get(k))
    for s in draft["subtext"]:
        s["means"] = mark(s["means"], ((mine.get("subtext") or {}).get(s["id"]) or {}).get("means"))
        if s["means"]["source"] == "you":
            s["confidence"] = "high"
    return draft


def get(d: str) -> dict:
    scenes, has = _inputs(d)
    names = CP._people(d)
    stored = _stored(d)["scenes"]
    return {"has_contracts": has, "scenes": [_apply(_scene_draft(d, sc, names), stored.get(str(sc["number"])) or {}) for sc in scenes]}


# ---------------------------------------------------------------- your edits

def _scene(d: str, number) -> dict:
    n = next((s for s in get(d)["scenes"] if str(s["number"]) == str(number)), None)
    if not n:
        raise SystemExit("That scene is not in the film.")
    return n


def _check(scene: dict, path: str) -> tuple:
    """('fields', field) | ('people', name, field) | ('subtext', id): the place an edit goes, or a plain refusal."""
    parts = path.split(".", 2)
    if parts[0] in SCENE_FIELDS and len(parts) == 1:
        return ("fields", parts[0])
    if parts[0] == "people" and len(parts) == 3 and parts[2] in PERSON_FIELDS and any(p["name"] == parts[1] for p in scene["people"]):
        return ("people", parts[1], parts[2])
    if parts[0] == "subtext" and len(parts) == 2 and any(s["id"] == parts[1] for s in scene["subtext"]):
        return ("subtext", parts[1])
    raise SystemExit("That is not a part of this scene's breakdown.")


def _edit(d: str, scene: int, path: str, value, reset: bool = False) -> dict:
    sc = _scene(d, scene)
    where = _check(sc, path)
    text = _txt(value)

    def change(data):
        data = data if isinstance(data, dict) else {}
        scenes = data.get("scenes") if isinstance(data.get("scenes"), dict) else {}
        mine = scenes.setdefault(str(scene), {})
        node = mine
        steps = ("fields", where[1]) if where[0] == "fields" else ("people", where[1], where[2]) if where[0] == "people" else ("subtext", where[1], "means")
        for k in steps[:-1]:
            node = node.setdefault(k, {})
        if reset:
            node.pop(steps[-1], None)
        else:
            node[steps[-1]] = {"value": text, "source": "you", "updated": int(time.time())}
        data["scenes"], data["schema"] = scenes, SCHEMA
        return data
    os.makedirs(CP.root(d), exist_ok=True)
    safeio.update_json(_path(d), change, {})
    return _scene(d, scene)


def set_field(d: str, scene: int, path: str, value) -> dict:
    """Write your own words for one part of a scene (an empty text is your decision that it is blank). The dialogue is never touched."""
    return _edit(d, scene, path, value)


def reset_field(d: str, scene: int, path: str) -> dict:
    """Go back to the draft for one part."""
    return _edit(d, scene, path, "", reset=True)


def accept_field(d: str, scene: int, path: str) -> dict:
    """Keep the draft's words for one part as your own (so they may reach the prompts)."""
    sc = _scene(d, scene)
    where = _check(sc, path)
    cur = sc["fields"][where[1]] if where[0] == "fields" else next(p for p in sc["people"] if p["name"] == where[1])[where[2]] if where[0] == "people" else \
        next(s for s in sc["subtext"] if s["id"] == where[1])["means"]
    if not cur["value"]:
        raise SystemExit("There is nothing written here to keep yet.")
    return _edit(d, scene, path, cur["value"])


# ---------------------------------------------------------------- into the prompts: only what you wrote or accepted

def inner_text(d: str, shot: dict) -> str | None:
    """For the people in a shot whose outward and inner states you wrote: the difference between what shows and what is felt, as direction. A draft is never used."""
    try:
        data = get(d)
    except SystemExit:
        return None
    scene = next((s for s in data["scenes"] if shot.get("id") in s["shots"]), None)
    if not scene:
        return None
    lines = []
    for p in scene["people"]:
        if p["name"] not in [x for x in shot.get("performers") or [] if isinstance(x, str)]:
            continue
        out, inn, hid = (p[k]["value"] if p[k]["source"] == "you" else "" for k in ("outward", "inner", "hiding"))
        if out and inn:
            lines.append(f"{p['name']} shows {out.rstrip('.')} but is privately {inn.rstrip('.')}" + (f", hiding {hid.rstrip('.')}" if hid else "") + ".")
        elif inn:
            lines.append(f"{p['name']} is privately {inn.rstrip('.')}.")
    return ("Under the surface (show it only in small leaks such as the eyes, the breath and a held jaw; never say it): " + " ".join(lines))[:460] if lines else None


# ---------------------------------------------------------------- beats: a free starting point

CLAUSE = [("eyes", re.compile(r"\b(eyes?|gaze|blink\w*|look\w*|glanc\w*|stare\w*)\b", re.I)), ("breath", re.compile(r"\b(breath\w*|inhale\w*|exhale\w*|swallow\w*|sigh\w*)\b", re.I)),
          ("hands", re.compile(r"\b(hands?|fingers?|fidget\w*)\b", re.I)), ("face", re.compile(r"\b(lips?|brows?|jaw|cheeks?|smile\w*|nostrils?|mouth|face)\b", re.I)),
          ("posture", re.compile(r"\b(shoulders?|chin|weight|posture|stillness|hips?|squared)\b", re.I)), ("head", re.compile(r"\b(head|tilts?|nods?)\b", re.I))]


def _sort_clauses(text: str) -> dict:
    out: dict[str, list[str]] = {}
    for clause in [c.strip() for c in re.split(r",|;", text or "") if c.strip()]:
        for k, rx in CLAUSE:
            if rx.search(clause):
                out.setdefault(k, []).append(clause)
                break
    return {k: "; ".join(v[:2])[:120] for k, v in out.items()}


def suggest_beats(d: str, shot_id: str) -> dict:
    """Two or three beats for a shot, built here from the feeling, who is in the shot, whether the person is restrained, and what you wrote about outward and inner. Rule-based: a starting
    point to edit, never saved by itself, and every beat says it is automatic and not sure."""
    from . import acting, performance
    sh = acting._shot(d, shot_id)
    scenes, _ = _inputs(d)
    info = next((s for sc in scenes for s in sc["shots"] if s["id"] == shot_id), None)
    seconds = round(acting._seconds(sh), 2)
    people = [p for p in (info or {}).get("people") or sh.get("performers") or [] if isinstance(p, str)]
    if not people:
        return {"shot": shot_id, "seconds": seconds, "beats": [], "basis": "Nobody is in this shot, so there is nothing for a person to do."}
    who = people[0]
    other = next((p for p in people[1:]), "")
    feeling = _txt((info or {}).get("intention") or sh.get("emotion") or sh.get("expression"), 120)
    micro = _sort_clauses(performance.micro_for(feeling))
    style = CP._style(d, who) or "natural"
    scene = next((s for s in get(d)["scenes"] if shot_id in s["shots"]), None)
    person = next((p for p in (scene or {}).get("people", []) if p["name"] == who), {})
    out = person.get("outward", {}).get("value") if person.get("outward", {}).get("source") == "you" else ""
    inn = person.get("inner", {}).get("value") if person.get("inner", {}).get("source") == "you" else ""
    cuts = [0.0, round(seconds * 0.35, 2), round(seconds * 0.7, 2), seconds] if seconds > 2 else [0.0, round(seconds * 0.5, 2), seconds]
    plan = [("registers what is happening before reacting", {"eyes": f"toward {other}" if other else "to what matters here", "gaze": other or ""}, "the moment arrives")]
    if out and inn:
        plan.append((f"keeps {out.rstrip('.')} on the surface while {inn.rstrip('.')} shows in the smallest places", micro, "the surface holds, the feeling leaks"))
    else:
        plan.append((f"reacts{(': ' + feeling) if feeling else ''}, in a small readable way", micro, f"{feeling or 'the feeling'} begins to show"))
    if len(cuts) == 4:
        plan.append(("holds the moment still; the feeling stays in the eyes and the breath" if style == "restrained" else "lets a small physical release happen: a breath out, the shoulders settling",
                     {"breath": micro.get("breath", ""), "eyes": micro.get("eyes", "")}, "the feeling settles"))
    beats = []
    for i, (what, bits, change) in enumerate(plan[:len(cuts) - 1]):
        beat = {"t0": cuts[i], "t1": cuts[i + 1], "what": f"{who} {what}", "change": change, "source": "auto", "confidence": "low"}
        beat.update({k: v for k, v in bits.items() if v and k in acting.BEAT_TEXT})
        beats.append(beat)
    basis = f"A rule-based starting point from the feeling ({feeling or 'none named'}), {who}'s acting style ({style})" + (" and what you wrote about outward and inner" if out and inn else "") + ". Edit it freely; nothing is saved until you save."
    return {"shot": shot_id, "seconds": seconds, "beats": acting.clean_beats(beats, seconds), "basis": basis}
