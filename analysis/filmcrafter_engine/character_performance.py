"""Character psychology: what a person wants, fears and hides, how they speak and carry themselves, and what they do under pressure.

This is a LAYER over the cast, not a replacement for it. The Bible (bible.py) stays the record of who a person is and looks like; the acting profile (performance.py) stays the record of how
big their acting is; their signature gestures (acting.py, `business`) stay where they are. This file holds only what none of those hold, and shows the others beside it.

  <film>/performance/characters.json     {"schema": 1, "people": {name: {personality, desire, fears, triggers, contradictions, defenses, speech_rhythm, carriage, stress, state_now}}}

(For a project that is not a film the folder sits in the project itself.) Everything is optional and is only ever written by the person: nothing here is guessed. A filled field reaches the
prompts as one short line that is the first thing dropped when a prompt is too long; the screenplay and the Bible are never changed.

  python -m filmcrafter_engine.performance_director characters_get | character_set | character_clear ...
"""
from __future__ import annotations

import os
import time

from . import safeio

from .performance_prompts import KINDS

FILE = "characters.json"
SCHEMA = 1
FIELDS = {"personality": 320, "desire": 320, "fears": 320, "triggers": 320, "contradictions": 320, "defenses": 320, "speech_rhythm": 200, "carriage": 240, "stress": 320, "state_now": 160, "kind": 20}


def film_dir(d: str) -> str | None:
    """The film a render project belongs to (the render project lives in <film>/render), else None."""
    d = os.path.abspath(d)
    parent = os.path.dirname(d)
    return parent if os.path.basename(d) == "render" and os.path.isfile(os.path.join(parent, "film.json")) else None


def root(d: str) -> str:
    """Where the Performance Director keeps its files: in the film, or in the project when there is no film."""
    return os.path.join(film_dir(d) or os.path.abspath(d), "performance")


def _txt(v, n: int) -> str:
    return " ".join(str(v or "").split())[:n]


def _path(d: str) -> str:
    return os.path.join(root(d), FILE)


def load(d: str) -> dict:
    """The stored profiles, read defensively: wrong shapes are dropped, a damaged file reads as empty (and is never overwritten by a read)."""
    try:
        s = safeio.read_json(_path(d), {})
    except SystemExit:
        s = {}
    s = s if isinstance(s, dict) else {}
    people = {}
    for name, p in (s.get("people") if isinstance(s.get("people"), dict) else {}).items():
        if isinstance(p, dict):
            people[str(name)] = {k: _txt(p.get(k), n) for k, n in FIELDS.items() if _txt(p.get(k), n) and (k != "kind" or _txt(p.get(k), n) in KINDS)}
    return {"schema": SCHEMA, "people": people}


def _people(d: str) -> list[str]:
    from . import acting
    try:
        return list(acting._characters(acting._plan(d)))
    except SystemExit:
        pass
    f = film_dir(d)
    if f:
        from . import bible
        return [c["name"].title() if c["name"].isupper() else c["name"] for c in bible.load(f).get("characters", [])]
    return []


def _known(d: str, name: str) -> dict:
    """What the cast already says about this person (read only), so it is shown beside the profile and never typed twice."""
    f = film_dir(d)
    out = {}
    if f:
        from . import bible
        for c in bible.load(f).get("characters", []):
            if c["name"].lower() == name.lower():
                out = {k: _txt(c.get(k), 240) for k in ("role", "age", "relationships", "arc", "notes") if _txt(c.get(k), 240)}
                states = [{"label": s.get("label", ""), "age": s.get("age", "")} for s in c.get("states", []) if s.get("age")]
                if states:
                    out["stages"] = states
                break
    from . import acting
    try:
        plan_c = acting._characters(acting._plan(d)).get(name) or {}
    except SystemExit:
        plan_c = {}
    for k in ("motivation", "acting_notes"):
        if _txt(plan_c.get(k), 240):
            out[k] = _txt(plan_c.get(k), 240)
    return out


def _style(d: str, name: str) -> str:
    """The acting style set for this person in the Acting screen ('' when none was set for them)."""
    from . import performance
    try:
        import json
        with open(os.path.join(d, "project.json"), encoding="utf-8") as fh:
            p = json.load(fh)
    except (OSError, ValueError):
        return ""
    return performance.settings(p)["characters"].get(name, "") if isinstance(p, dict) else ""


def get(d: str) -> dict:
    from . import acting
    stored = load(d)["people"]
    try:
        gestures = acting.load(d)["business"]
    except Exception:
        gestures = {}
    return {"fields": [k for k in FIELDS if k != "kind"], "people": [{"name": n, "profile": {k: stored.get(n, {}).get(k, "") for k in FIELDS}, "known": _known(d, n), "style": _style(d, n),
                                                "gestures": acting.clean_business(gestures.get(n))} for n in _people(d)]}


def set_fields(d: str, person: str, fields: dict) -> dict:
    """Save the fields given for one person (an empty text clears that field). Fields not given are left as they are."""
    if person not in _people(d):
        raise SystemExit("That person is not in the film.")
    if not isinstance(fields, dict) or not any(k in FIELDS for k in fields):
        raise SystemExit("Nothing to save.")
    cleaned = {k: _txt(v, FIELDS[k]) for k, v in fields.items() if k in FIELDS}
    if cleaned.get("kind") and cleaned["kind"] not in KINDS:
        raise SystemExit("That kind of character is not one of the choices.")

    def change(data):
        data = data if isinstance(data, dict) else {}
        people = data.get("people") if isinstance(data.get("people"), dict) else {}
        mine = dict(people.get(person) or {})
        for k, v in cleaned.items():
            if v:
                mine[k] = v
            else:
                mine.pop(k, None)
        if any(k in FIELDS and mine.get(k) for k in mine):
            mine["updated"] = int(time.time())
            people[person] = mine
        else:
            people.pop(person, None)
        data["people"] = people
        data["schema"] = SCHEMA
        return data
    os.makedirs(root(d), exist_ok=True)
    safeio.update_json(_path(d), change, {})
    return get(d)


def clear(d: str, person: str) -> dict:
    if person not in _people(d):
        raise SystemExit("That person is not in the film.")

    def change(data):
        data = data if isinstance(data, dict) else {}
        if isinstance(data.get("people"), dict):
            data["people"].pop(person, None)
        return data
    if os.path.exists(_path(d)):
        safeio.update_json(_path(d), change, {})
    return get(d)


def prompt_text(d: str, shot: dict) -> str | None:
    """One short line about the people in a shot (what they want, fear and do under pressure), to colour the acting. None when nothing is written about them."""
    stored = load(d)["people"]
    lines = []
    for n in [x for x in shot.get("performers") or [] if isinstance(x, str)][:2]:
        p = stored.get(n)
        if not p:
            continue
        bits = []
        if p.get("desire"):
            bits.append(f"wants {p['desire'].rstrip('.')}")
        if p.get("fears"):
            bits.append(f"is afraid of {p['fears'].rstrip('.')}")
        if p.get("stress"):
            bits.append(f"under pressure {p['stress'].rstrip('.')}")
        if p.get("state_now"):
            bits.append(f"right now is {p['state_now'].rstrip('.')}")
        if bits:
            lines.append(f"{n} " + ", ".join(bits) + ".")
    return ("About the people (let it colour the acting; never state it): " + " ".join(lines))[:420] if lines else None
