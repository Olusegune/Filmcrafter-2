"""The Lighting Designer: reads the mood of every shot (and of the sequence around it) and plans the light to match.

Light is how a picture feels. This reads each shot's mood from what is already known about it: the feeling the Director wrote, the words sung under it, what happens in it, how hard the
performance is pushed, how loud the song is at that moment and which part of the song it sits in. Then it designs the light for that mood: the kind of light (one of camera.py's terms),
its direction, how contrasty it is, how warm or cool, the colour of any accents, whether there are practical lamps or haze, and how the light moves. It plans a whole sequence at once,
so a scene keeps one light unless the mood really turns, and the song's loud parts get more contrast than its quiet ones. The scene's own setting is respected: a night scene is never
planned in daylight.

Everything here is free and runs on this computer. A plan is only a proposal: applying it writes ordinary camera choices (camera.json), never over a choice you made yourself unless you
ask, and one press of Undo puts the project back as it was.

  python -m filmcrafter_engine.lighting <plan|apply|undo|moods> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

# ----------------------------------------------------------------------------- moods

# id, label, valence (-1 dark .. +1 bright), arousal (0 still .. 1 intense), the words that point to it
MOODS = [
    ("joy", "Joy", 0.9, 0.7, r"joy|happy|elat|celebrat|playful|delight|exuber|cheer|giddy|carefree|laugh|dance|smil|bright|party|sunshine"),
    ("tenderness", "Tenderness", 0.6, 0.25, r"tender|love|intimate|affection|devotion|gentle|embrace|kiss|lullaby|soft|warmth|hold(?:s|ing)? (?:her|him|hands)|cradle"),
    ("desire", "Desire", 0.3, 0.55, r"desire|longing|yearn|passion|lust|seduc|crave|ache for|want(?:s|ed)? (?:her|him|you)|sensual"),
    ("calm", "Calm", 0.5, 0.1, r"calm|peace|serene|still|quiet|rest|sleep|breath|float|drift|silence|stillness"),
    ("nostalgia", "Nostalgia", 0.2, 0.3, r"nostalg|remember|memor|childhood|used to|years ago|old (?:house|photo|song)|those days|back then|young(?:er)?|past"),
    ("hope", "Hope", 0.7, 0.4, r"hope|dawn|sunrise|new day|begin|beginning|light (?:at|in)|tomorrow|relief|gratitude|rebirth|rise"),
    ("awe", "Awe", 0.6, 0.5, r"awe|wonder|reverence|vast|infinite|heaven|divine|cosmic|stars|miracle|glory|sublime"),
    ("triumph", "Triumph", 0.8, 0.8, r"triumph|pride|proud|victor|hero|swagger|conquer|crown|champion|power|unstoppable|rise up"),
    ("ecstasy", "Ecstasy", 0.7, 0.95, r"ecstas|euphori|frenzy|wild|rave|climax|explod|electric|crowd|roar|dancing floor|lose (?:myself|control)"),
    ("melancholy", "Melancholy", -0.3, 0.2, r"melanchol|sad|blue|wistful|rain|autumn|fading|empty|gray|grey|tear|sigh|bittersweet"),
    ("loneliness", "Loneliness", -0.5, 0.15, r"lonel|alone|isolat|abandon|solitude|nobody|no one|empty (?:room|street|bed)|by (?:himself|herself|myself)"),
    ("grief", "Grief", -0.8, 0.3, r"grief|griev|mourn|loss|lost (?:him|her|you)|funeral|goodbye|death|dead|widow|bereft|heartbreak|sorrow"),
    ("regret", "Regret", -0.5, 0.35, r"regret|guilt|shame|sorry|should have|too late|mistake|apolog|if only|remorse|confess"),
    ("tension", "Tension", -0.4, 0.65, r"tens|anxi|nervous|uneas|suspens|wait(?:ing)?|watch(?:ed|ing)|follow(?:ed|ing)|creep|hesitat|dread|breath held|ticking"),
    ("menace", "Menace", -0.8, 0.7, r"menac|threat|sinister|ominous|terror|fear|predator|haunt|stalk|shadow(?:s)? (?:move|creep)|blood|danger|evil|panic"),
    ("anger", "Anger", -0.6, 0.9, r"anger|rage|fury|furious|wrath|resent|scream|shout|fight|punch|smash|violent|confront|betray"),
    ("defiance", "Defiance", 0.1, 0.8, r"defian|stand(?:s|ing)? (?:up|tall|firm)|refuse|resist|rebel|fearless|resolve|determin|will not|never again|fight back"),
]
_RX = {m[0]: re.compile(m[4], re.I) for m in MOODS}
_META = {m[0]: m for m in MOODS}

# which part of the song a section label sounds like, for songs whose energy curve is missing
SECTION_LOUD = re.compile(r"chorus|hook|drop|final|climax|outro chorus|refrain", re.I)
SECTION_QUIET = re.compile(r"intro|verse|bridge|breakdown|outro|interlude|pre", re.I)

# ----------------------------------------------------------------------------- recipes

# per mood: the light term, direction of the key, the colour temperature (K), the colour of any accent, practical lamps, haze, and how the light moves
RECIPES = {
    "joy":        {"term": "golden", "alt": "daylight", "key": "wide, soft and from the front-side", "kelvin": 4800, "accent": "warm gold with a touch of sky blue", "practical": False, "haze": False, "motion": "steady"},
    "tenderness": {"term": "practical", "alt": "window", "key": "low and close, from one side", "kelvin": 3000, "accent": "amber", "practical": True, "haze": False, "motion": "steady"},
    "desire":     {"term": "practical", "alt": "neon", "key": "low from the side, half the face in shadow", "kelvin": 2700, "accent": "deep red and amber", "practical": True, "haze": True, "motion": "slow pulse"},
    "calm":       {"term": "overcast", "alt": "window", "key": "large and soft from a window", "kelvin": 5600, "accent": "pale neutral", "practical": False, "haze": False, "motion": "steady"},
    "nostalgia":  {"term": "golden", "alt": "window", "key": "low and warm, raking across the room", "kelvin": 3400, "accent": "faded amber with soft grain", "practical": True, "haze": True, "motion": "slow drift"},
    "hope":       {"term": "golden", "alt": "daylight", "key": "rising from behind the subject", "kelvin": 4500, "accent": "gold on the horizon", "practical": False, "haze": True, "motion": "slowly brightening"},
    "awe":        {"term": "haze", "alt": "rim", "key": "high beams from above and behind", "kelvin": 5200, "accent": "pale gold shafts through haze", "practical": False, "haze": True, "motion": "slow sweep"},
    "triumph":    {"term": "rim", "alt": "stage", "key": "strong from behind, outlining the subject", "kelvin": 5000, "accent": "gold rim with a cool fill", "practical": False, "haze": True, "motion": "swelling"},
    "ecstasy":    {"term": "neon", "alt": "stage", "key": "coloured light from every side, moving", "kelvin": 4000, "accent": "saturated magenta, cyan and gold", "practical": False, "haze": True, "motion": "pulsing with the beat"},
    "melancholy": {"term": "blue", "alt": "overcast", "key": "dim and soft from one side", "kelvin": 6800, "accent": "cool blue-grey, one warm lamp far away", "practical": True, "haze": False, "motion": "steady"},
    "loneliness": {"term": "lowkey", "alt": "moon", "key": "a single small source far from the subject", "kelvin": 6200, "accent": "cold blue, a lone warm window", "practical": True, "haze": False, "motion": "steady"},
    "grief":      {"term": "overcast", "alt": "blue", "key": "flat, grey and colourless from above", "kelvin": 7000, "accent": "desaturated, almost no colour", "practical": False, "haze": False, "motion": "steady"},
    "regret":     {"term": "split", "alt": "lowkey", "key": "warm on one side of the face, cold on the other", "kelvin": 4200, "accent": "warm past against a cold present", "practical": True, "haze": False, "motion": "steady"},
    "tension":    {"term": "hardkey", "alt": "lowkey", "key": "hard from the side, long shadows", "kelvin": 5600, "accent": "sickly green and cold white", "practical": False, "haze": False, "motion": "slow flicker"},
    "menace":     {"term": "underlit", "alt": "lowkey", "key": "from below and behind, the face half lost", "kelvin": 6500, "accent": "cold green and deep red", "practical": False, "haze": True, "motion": "unsteady flicker"},
    "anger":      {"term": "hardkey", "alt": "noon", "key": "harsh and direct, no fill", "kelvin": 5800, "accent": "hot red against white", "practical": False, "haze": False, "motion": "sharp pulses"},
    "defiance":   {"term": "rim", "alt": "hardkey", "key": "from behind and below, the subject standing against it", "kelvin": 5200, "accent": "steel blue with a warm edge", "practical": False, "haze": True, "motion": "steady, then swelling"},
}
CONTRAST_WORDS = ["soft, low contrast", "gentle contrast", "moderate contrast", "strong contrast", "deep shadows, very high contrast"]
DAYLIT = {"daylight", "golden", "highkey", "overcast", "noon", "dappled"}
NIGHTLIT = {"moon", "blue", "lowkey", "sodium", "stage"}


def kelvin_words(k: int) -> str:
    return "very warm" if k < 3200 else "warm" if k < 4300 else "neutral" if k < 5800 else "cool" if k < 6600 else "cold"


# ----------------------------------------------------------------------------- reading the mood

def _lines_under(shot: dict, lyrics: list[dict]) -> list[str]:
    own = [str(x) for x in shot.get("lyrics") or [] if x]
    if own:
        return own
    s, e = float(shot.get("start") or 0), float(shot.get("end") or 0)
    return [str(l.get("text", "")) for l in lyrics if l.get("start") is not None and s - 0.2 <= float(l["start"]) < e]


def energy_at(curve: list, t: float) -> float | None:
    """The song's loudness at a moment, 0..1 against its own range (None when there is no curve)."""
    pts = [(float(a), float(b)) for a, b in curve or [] if isinstance(a, (int, float)) and isinstance(b, (int, float))]
    if len(pts) < 2:
        return None
    lo, hi = min(v for _, v in pts), max(v for _, v in pts)
    near = min(pts, key=lambda p: abs(p[0] - t))[1]
    return 0.5 if hi - lo < 1e-9 else round((near - lo) / (hi - lo), 3)


def read_mood(shot: dict, lyric_lines: list[str] | None = None, song_energy: float | None = None, section: str = "") -> dict:
    """The mood of one shot, from everything known about it. Pure.

    The Director's own word for the feeling counts most; the shot's description and the sung words count less; loudness and performance intensity decide how intense the
    mood is, and break a tie between a dark and a bright reading of the same words.
    """
    weights = ((shot.get("emotion"), 3.0), (shot.get("purpose"), 1.0), (shot.get("expression"), 1.5), (shot.get("performance"), 1.0),
               (" ".join(str(b) for b in shot.get("beats") or []), 1.0), (shot.get("visual_prompt"), 0.5), (" ".join(lyric_lines or []), 1.5))
    scores = {k: 0.0 for k in _RX}
    for text, w in weights:
        t = str(text or "")
        if not t:
            continue
        for k, rx in _RX.items():
            n = len(rx.findall(t))
            if n:
                scores[k] += w * min(n, 3)
    try:
        intensity = max(1, min(10, int(shot.get("performance_intensity") or 5)))
    except (TypeError, ValueError):
        intensity = 5
    loud = song_energy if song_energy is not None else (0.8 if SECTION_LOUD.search(section or "") else 0.3 if SECTION_QUIET.search(section or "") else 0.5)
    arousal = round(0.6 * (intensity - 1) / 9 + 0.4 * loud, 3)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    best, top = ranked[0]
    if top <= 0:                                  # nothing in the words: the song and the performance decide
        best = "ecstasy" if arousal > 0.8 else "tension" if arousal > 0.65 else "calm" if arousal < 0.25 else "hope" if loud > 0.55 else "melancholy"
        basis = "the song and the performance (the shot names no feeling)"
        confidence = 0.2
    else:
        # two moods with the same words: the one nearer the shot's own arousal wins
        close = [k for k, v in ranked if v >= top - 0.01]
        best = min(close, key=lambda k: abs(_META[k][3] - arousal))
        basis = "the feeling and words of the shot"
        confidence = round(min(1.0, top / 6), 2)
    meta = _META[best]
    runner = [k for k, v in ranked if k != best and v > 0][:2]
    return {"mood": best, "label": meta[1], "valence": meta[2], "arousal": arousal, "intensity": intensity, "song_energy": round(loud, 2),
            "confidence": confidence, "also": runner, "basis": basis}


# ----------------------------------------------------------------------------- designing the light

def _setting(heading: str, env: str) -> str:
    h = f"{heading} {env}".lower()
    interior = bool(re.search(r"\bint\b|\binterior\b|room|kitchen|bedroom|house|hall|corridor|club|bar|studio|stage|station|office|car\b", h))
    night = bool(re.search(r"night|midnight|late|dark|moonlit|after hours", h))
    day = bool(re.search(r"\bday\b|morning|noon|afternoon|sunny|daylight", h))
    dusk = bool(re.search(r"dusk|sunset|golden hour|evening|dawn|sunrise", h))
    return ("night" if night else "dusk" if dusk else "day" if day else "") + ("-int" if interior else "-ext" if re.search(r"\bext\b|exterior|street|field|beach|forest|roof|road|park|city", h) else "")


def design(mood: str, arousal: float, heading: str = "", env: str = "") -> dict:
    """The light for a mood at an intensity, adapted to where and when the scene happens. Pure."""
    from .camera import LIGHTING, _wording
    r = RECIPES[mood]
    term, kelvin = r["term"], r["kelvin"]
    setting = _setting(heading, env)
    when, where = (setting.split("-") + [""])[:2]
    if when == "night" and term in DAYLIT:
        if _META[mood][2] < -0.2:                   # a dark mood at night stays cold and dim
            term = "lowkey" if where == "int" else "moon"
        else:
            term = "practical" if where == "int" else "moon"
            kelvin = min(kelvin, 3200) if where == "int" else 6800
    elif when == "day" and term in NIGHTLIT and mood not in ("menace", "tension", "loneliness"):
        term = "window" if where == "int" else r["alt"] if r["alt"] in DAYLIT else "overcast"
    elif when == "dusk" and term in ("daylight", "overcast", "highkey"):
        term = "golden"
    level = 0 if arousal < 0.2 else 1 if arousal < 0.4 else 2 if arousal < 0.6 else 3 if arousal < 0.8 else 4
    if mood in ("grief", "calm", "melancholy", "tenderness", "nostalgia"):
        level = min(level, 2)                       # these moods are never harsh, however loud the song
    if mood in ("anger", "menace", "tension", "defiance", "ecstasy"):
        level = max(level, 2)
    contrast = CONTRAST_WORDS[level]
    bits = [_wording("lighting", term), f"{kelvin_words(kelvin)} colour (about {kelvin} K)", f"key {r['key']}", contrast, f"colour accents: {r['accent']}"]
    if r["practical"] and term not in ("practical", "fire", "neon"):
        bits.append("visible practical lamps in frame")
    if r["haze"] and term != "haze":
        bits.append("a little haze to give the light shape")
    if r["motion"] != "steady":
        bits.append(f"the light moves: {r['motion']}")
    return {"term": term, "label": next((t[1] for t in LIGHTING if t[0] == term), term), "kelvin": kelvin, "contrast": contrast, "level": level, "key": r["key"], "accent": r["accent"], "motion": r["motion"],
            "practical": r["practical"], "haze": r["haze"], "wording": "; ".join(bits)}


# ----------------------------------------------------------------------------- planning a sequence

def _smooth(rows: list[dict]) -> None:
    """Within a scene keep the light steady: a shot's mood only changes the base light when the mood turns for at least two shots, or turns hard.
    The shot keeps its own mood for the reason it shows; only the choice of light term is held."""
    i = 0
    while i < len(rows):
        j = i
        while j < len(rows) and rows[j]["scene"] == rows[i]["scene"]:
            j += 1
        scene = rows[i:j]
        for k, r in enumerate(scene):
            r["held"] = False
            if k == 0 or k == len(scene) - 1:
                continue
            prev, nxt = scene[k - 1], scene[k + 1]
            hard = abs(r["valence"] - prev["design_mood_valence"]) > 1.0
            if r["mood"] != prev["design_mood"] and r["mood"] != nxt["mood"] and not hard and r["confidence"] < 0.5:
                r["design_mood"], r["design_mood_valence"], r["held"] = prev["design_mood"], prev["design_mood_valence"], True
        i = j


def plan(d: str) -> dict:
    """The mood and the planned light for every shot, scene by scene. Free; nothing is changed."""
    from .camera import _load, GROUPS
    from .planio import load_plan as _load_plan, _read
    _, plan_ = _load_plan(d)
    song = _read(os.path.join(d, "songmap.json")) or {}
    lyrics, curve = song.get("lyrics") or [], song.get("energy_curve") or []
    picks = _load(d)
    rows = []
    for sc in plan_.get("scenes", []):
        env = " ".join(str(v) for k, v in (sc.get("notes") or {}).items() if re.search(r"set|location|place|time|light", k, re.I))
        for sh in sc.get("shots", []):
            mid = (float(sh.get("start") or 0) + float(sh.get("end") or 0)) / 2
            m = read_mood(sh, _lines_under(sh, lyrics), energy_at(curve, mid), str(sh.get("section") or ""))
            mine = picks.get(sh.get("id")) or {}
            rows.append({"shot": sh["id"], "scene": sc.get("number"), "heading": sc.get("heading", ""), "env": env, "start": sh.get("start"), "end": sh.get("end"),
                         "section": sh.get("section", ""), **m, "design_mood": m["mood"], "design_mood_valence": m["valence"],
                         "user_set": bool(isinstance(mine, dict) and mine.get("lighting") and not mine.get("lighting_text")), "director": str(sh.get("lighting") or "")})
    _smooth(rows)
    out = []
    for r in rows:
        dsg = design(r["design_mood"], r["arousal"], r["heading"], r["env"])
        why = (f"{r['label']} (read from {r['basis']}"
               + (f"; the song is {'loud' if r['song_energy'] > 0.65 else 'quiet' if r['song_energy'] < 0.35 else 'moderate'} here" if r["song_energy"] is not None else "") + ")"
               + (f", held at {_META[r['design_mood']][1].lower()} to keep the scene's light steady" if r["held"] else "")
               + f" → {next(t[1] for t in GROUPS['lighting'] if t[0] == dsg['term']).lower()}, {kelvin_words(dsg['kelvin'])}, {dsg['contrast']}.")
        out.append({k: r[k] for k in ("shot", "scene", "start", "end", "section", "mood", "label", "valence", "arousal", "intensity", "confidence", "also", "held", "user_set", "director")}
                   | {"design": dsg, "why": why})
    scenes = []
    for sc in plan_.get("scenes", []):
        mine = [o for o in out if o["scene"] == sc.get("number")]
        if mine:
            scenes.append({"scene": sc.get("number"), "heading": sc.get("heading", ""), "from": mine[0]["label"], "to": mine[-1]["label"],
                           "arc": " → ".join(dict.fromkeys(o["label"] for o in mine)), "terms": sorted({o["design"]["term"] for o in mine})})
    return {"shots": out, "scenes": scenes, "count": len(out), "user_set": sum(1 for o in out if o["user_set"])}


# ----------------------------------------------------------------------------- applying, and undoing

def _undo_path(d: str) -> str:
    return os.path.join(d, "lighting_undo.json")


def apply(d: str, shot_ids: list[str] | None = None, overwrite: bool = False) -> dict:
    """Write the plan as camera choices. A shot whose lighting you chose yourself is left alone unless `overwrite`. Remembers what it replaced, for undo."""
    from . import camera
    p = plan(d)
    want = set(shot_ids) if shot_ids else None
    data = camera._load(d)
    before, changed, skipped = {}, [], []
    for r in p["shots"]:
        if want is not None and r["shot"] not in want:
            continue
        cur = data.get(r["shot"]) or {}
        if r["user_set"] and not overwrite:
            skipped.append(r["shot"])
            continue
        before[r["shot"]] = json.loads(json.dumps(cur)) if cur else None
        entry = {k: v for k, v in cur.items()}
        entry["lighting"] = r["design"]["term"]
        entry["lighting_text"] = r["design"]["wording"]
        entry["at"] = time.time()
        data[r["shot"]] = entry
        changed.append(r["shot"])
    if changed:
        undo = _read_json(_undo_path(d)) or {"stack": []}
        undo["stack"].append({"at": time.time(), "shots": before})
        undo["stack"] = undo["stack"][-10:]
        with open(_undo_path(d), "w", encoding="utf-8") as f:
            json.dump(undo, f, indent=1)
        camera._save(d, data)
    return {"changed": changed, "skipped": skipped, "undo": bool(changed)}


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def undo(d: str) -> dict:
    from . import camera
    u = _read_json(_undo_path(d)) or {"stack": []}
    if not u["stack"]:
        raise SystemExit("There is nothing to undo.")
    last = u["stack"].pop()
    data = camera._load(d)
    for sid, prev in last["shots"].items():
        if prev is None:
            data.pop(sid, None)
        else:
            data[sid] = prev
    camera._save(d, data)
    with open(_undo_path(d), "w", encoding="utf-8") as f:
        json.dump(u, f, indent=1)
    return {"restored": list(last["shots"]), "more": bool(u["stack"])}


def moods() -> list[dict]:
    """The moods the designer knows, for the screen's legend."""
    return [{"id": m[0], "label": m[1], "valence": m[2], "arousal": m[3], "term": RECIPES[m[0]]["term"], "kelvin": RECIPES[m[0]]["kelvin"]} for m in MOODS]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-lighting")
    ap.add_argument("action", choices=["plan", "apply", "undo", "moods"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        res = plan(a.project) if a.action == "plan" else apply(a.project, x.get("shots"), bool(x.get("overwrite"))) if a.action == "apply" \
            else undo(a.project) if a.action == "undo" else moods()
        print(json.dumps({"event": "result", "data": res}), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except Exception as e:
        print(json.dumps({"event": "error", "message": __import__("filmcrafter_engine.errtext", fromlist=["plain"]).plain(e)}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
