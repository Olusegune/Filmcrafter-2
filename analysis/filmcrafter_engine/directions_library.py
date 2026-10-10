"""Worldwide creative-direction library: great filmmakers.

Filmmakers from around the world (North America, Latin America, Europe, Asia, Africa, the Middle East, Oceania), each turned into a working visual brief:
camera, light, palette, editing rhythm, movement, design, a suggested look and acting profile, and what to avoid. Entries describe visual approaches, never copies of a film;
each carries a respect note so a direction is used with care.

Browse and filter, rank against your story (its genre, mood and energy, found in the script; free and deterministic), and apply one to a project:
it becomes the brief for the writing and picture helpers, fills the Production Bible, and sets the look and acting profile (only where you haven't set your own).
Your own directions can be saved to the library too.

  python -m filmcrafter_engine.directions_library <action> [project] --data '{...}'
  actions: list | match | apply | save | delete
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

from .filmmakers import LIBRARY

USER_LIB = os.path.join(os.path.expanduser("~"), ".filmcrafter", "directions.json")

FIELDS = ("summary", "camera", "light", "editing", "movement", "design")


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _user() -> list[dict]:
    return [{**x, "custom": True} for x in (_read(USER_LIB, {}) or {}).get("directions", [])]


def all_directions() -> list[dict]:
    return list(LIBRARY) + _user()


def _film_dir(d: str) -> str | None:
    """The film folder: the project itself, or the one above its render project."""
    for c in (d, os.path.dirname(os.path.abspath(d))):
        if os.path.isfile(os.path.join(c, "film.json")):
            return c
    return None


def _story_text(d: str) -> str:
    fd = _film_dir(d)
    if fd:
        try:
            from . import story
            return story.status(fd)["text"]
        except (SystemExit, Exception):
            pass
    p = _read(os.path.join(d, "project.json"), {}) or {}
    return " ".join(str(x) for x in ((p.get("onboarding") or {}).get("concept_notes"), p.get("title")) if x)


# words in a story that suggest a mood (tags) or a genre; every hit is a small vote
STORY_WORDS = {
    "tags": {
        "romantic": ["love", "kiss", "heart", "romance", "date", "wedding"], "tender": ["gentle", "tender", "hug", "mother", "grandmother", "child"],
        "joyful": ["laugh", "joy", "celebrate", "party", "dance", "smile", "summer"], "melancholic": ["grief", "lonely", "loss", "miss", "goodbye", "memory", "sad"],
        "dark": ["murder", "dark", "fear", "blood", "death", "shadow", "kill"], "tense": ["chase", "danger", "threat", "tension", "escape", "secret", "afraid"],
        "epic": ["war", "king", "kingdom", "battle", "hero", "legend", "empire", "journey"], "family": ["family", "mother", "father", "sister", "brother", "daughter", "son", "home"],
        "dreamy": ["dream", "wonder", "float", "magic", "sky", "stars"], "mystical": ["spirit", "ghost", "myth", "ritual", "magic", "ancestor"],
        "whimsical": ["quirky", "funny", "odd", "silly", "adventure"], "contemplative": ["silence", "quiet", "wait", "listen", "slowly"],
        "energetic": ["run", "race", "fight", "fast", "crowd", "street"], "triumphant": ["win", "victory", "champion", "triumph", "rise"],
        "emotional": ["cry", "tears", "forgive", "truth", "confess"], "spiritual": ["pray", "faith", "god", "soul", "temple"], "night": ["night", "midnight", "neon"],
    },
    "genres": {
        "animation": ["animated", "cartoon", "animation"], "family": ["family", "children", "kids"], "fantasy": ["dragon", "witch", "magic", "kingdom", "fairy"],
        "science fiction": ["space", "robot", "alien", "future", "planet", "ship"], "romance": ["love", "romance", "kiss"], "comedy": ["comedy", "funny", "joke", "laugh"],
        "thriller": ["thriller", "murder", "chase", "detective", "spy"], "horror": ["horror", "haunted", "monster", "scream"], "drama": ["drama", "family", "struggle", "loss"],
        "action": ["fight", "chase", "explosion", "battle"], "history": ["war", "king", "century", "history"], "coming-of-age": ["school", "teenager", "growing", "first love"],
        "documentary": ["documentary", "interview"], "sports": ["game", "team", "coach", "match", "boxing", "football"], "myth": ["legend", "myth", "god", "hero"],
    },
}
HIGH = ["chase", "fight", "run", "race", "battle", "escape", "explosion", "crowd", "scream"]
LOW = ["quiet", "silence", "slowly", "wait", "gentle", "memory", "listen", "sleep", "whisper"]


def match(d: str, limit: int = 6) -> dict:
    """Rank filmmakers for this story: mood tags, genre and energy found in its words. Free; no AI."""
    text = _story_text(d).lower()
    words = re.findall(r"[a-z']+", text)
    n = max(1, len(words))
    has = lambda w: sum(1 for x in words if x == w or x.startswith(w)) if " " not in w else text.count(w)   # noqa: E731
    votes = {k: sum(has(w) for w in ws) for k, ws in STORY_WORDS["tags"].items()}
    gvotes = {k: sum(has(w) for w in ws) for k, ws in STORY_WORDS["genres"].items()}
    hi, lo = sum(has(w) for w in HIGH), sum(has(w) for w in LOW)
    level = "high" if hi > lo * 1.5 and hi >= 2 else "low" if lo > hi * 1.5 and lo >= 2 else "mid"
    top_tags = [k for k, v in sorted(votes.items(), key=lambda kv: -kv[1]) if v][:4]
    top_genres = [k for k, v in sorted(gvotes.items(), key=lambda kv: -kv[1]) if v][:3]
    ranked = []
    for x in all_directions():
        tag_hit = [t for t in x.get("tags", []) if votes.get(t)]
        gen_hit = [g for g in x.get("genres", []) if gvotes.get(g)]
        tag_s = min(1.0, sum(votes[t] for t in tag_hit) / max(3.0, n / 60))
        gen_s = min(1.0, sum(gvotes[g] for g in gen_hit) / max(3.0, n / 80))
        en_s = 1.0 if x.get("energy") == level else 0.5 if "mid" in (x.get("energy"), level) else 0.0
        score = round(tag_s * 0.45 + gen_s * 0.4 + en_s * 0.15, 3) if (tag_s or gen_s) else 0.0
        why = []
        if gen_hit:
            why.append("genre: " + ", ".join(gen_hit[:2]))
        if tag_hit:
            why.append("mood: " + ", ".join(tag_hit[:3]))
        if text.strip() and en_s >= 1:
            why.append(f"{level} energy")
        ranked.append({"id": x["id"], "score": score, "why": why})
    ranked.sort(key=lambda r: -r["score"])
    return {"story": {"energy": level, "moods": top_tags, "genres": top_genres, "words": len(words)}, "matches": [r for r in ranked if r["score"] > 0][:limit]}


def brief(x: dict) -> str:
    parts = [f"Creative direction: {x['name']} ({x['origin']}). {x['summary']}",
             f"Camera: {x['camera']}", f"Light: {x['light']}", f"Palette: {', '.join(x['palette'])}.",
             f"Editing: {x['editing']}", f"Movement: {x['movement']}", f"Design: {x['design']}"]
    if x.get("avoid"):
        parts.append(f"Avoid: {x['avoid']}")
    if x.get("respect"):
        parts.append(f"With care: {x['respect']}")
    return "\n".join(parts)


def apply(d: str, did: str, parts: list[str] | None = None, overwrite: bool = False) -> dict:
    """Use a direction for a project. parts: brief, bible, look, acting (default all). Your own settings are kept
    unless overwrite is true."""
    x = next((y for y in all_directions() if y["id"] == did), None)
    if not x:
        raise SystemExit("That direction isn't in the library.")
    parts = parts or ["brief", "bible", "look", "acting"]
    path = os.path.join(d, "project.json")
    p = _read(path, {})
    changed = []
    filled = dict((p.get("direction") or {}).get("filled") or {})   # what earlier directions wrote

    def mine(key, value):   # the user's own value: set, and not what a direction put there
        return bool(value) and filled.get(key) != value
    new_filled = {}
    if "brief" in parts:
        ob = dict(p.get("onboarding") or {"stage": "done"})   # no setup wizard in progress: never start one
        notes = ob.get("concept_notes") or ""
        notes = re.sub(r"(?s)Creative direction: .*?(?=\n\n|\Z)", "", notes).strip()   # replace an earlier library direction
        ob["concept_notes"] = (brief(x) + ("\n\n" + notes if notes else ""))[:2000]
        ob["direction_id"] = x["id"]
        p["onboarding"] = ob
        changed.append("brief for the directions and treatment")
    if "bible" in parts:
        b = dict(p.get("bible") or {})
        new = {"world": f"{x['summary']} {x['design']}", "palette": ", ".join(x["palette"]), "avoid": x.get("avoid", "")}
        for k, v in new.items():
            if not v and b.get(k) and filled.get(f"bible.{k}") == b.get(k):
                b[k] = ""   # the earlier direction's entry, and this one has none
                continue
            if v and (overwrite or not mine(f"bible.{k}", b.get(k))):
                b[k] = v[:1500]
                new_filled[f"bible.{k}"] = b[k]
                changed.append(f"bible: {k}")
        b.setdefault("rules", "")
        p["bible"] = b
    if "look" in parts and x.get("look"):
        cur = p.get("look")
        style = cur.get("style") if isinstance(cur, dict) else cur
        if overwrite or not style or style == "auto" or not mine("look", style):
            p["look"] = {**(cur if isinstance(cur, dict) else {}), "style": x["look"]}
            new_filled["look"] = x["look"]
            changed.append(f"look: {x['look']}")
    if "acting" in parts and x.get("acting"):
        perf = dict(p.get("performance") or {})
        if overwrite or not mine("acting", perf.get("default")):
            perf["default"] = x["acting"]
            new_filled["acting"] = x["acting"]
            perf.setdefault("scenes", {}), perf.setdefault("characters", {}), perf.setdefault("shots", {})
            p["performance"] = perf
            changed.append(f"acting: {x['acting']}")
    p["direction"] = {"id": x["id"], "name": x["name"], "applied": int(time.time()), "filled": {**filled, **new_filled}}
    cur = _read(path, {})   # keep anything written meanwhile
    cur.update({k: p[k] for k in ("onboarding", "bible", "look", "performance", "direction") if k in p})
    _write(path, cur)
    return {"applied": x["id"], "name": x["name"], "changed": changed}


def save(data: dict) -> dict:
    name = (data.get("name") or "").strip()
    if not name or not (data.get("summary") or "").strip():
        raise SystemExit("A direction needs a name and a summary.")
    lib = _read(USER_LIB, {}) or {}
    items = lib.get("directions", [])
    did = "my-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    entry = {"id": did, "name": name[:60], "region": "My directions", "origin": (data.get("origin") or "My own").strip()[:80],
             "tags": [t.strip().lower() for t in (data.get("tags") or []) if t.strip()][:8], "genres": [],
             "energy": data.get("energy") if data.get("energy") in ("low", "mid", "high") else "mid",
             "palette": [c.strip() for c in (data.get("palette") or []) if c.strip()][:6] or ["—"],
             "look": data.get("look") or "", "acting": data.get("acting") or "", "avoid": data.get("avoid") or "", "respect": ""}
    for f in FIELDS:
        entry[f] = (data.get(f) or "").strip()[:600] or "—"
    items = [i for i in items if i["id"] != did] + [entry]
    _write(USER_LIB, {"directions": items})
    return {"saved": did}


def delete(did: str) -> dict:
    lib = _read(USER_LIB, {}) or {}
    lib["directions"] = [i for i in lib.get("directions", []) if i["id"] != did]
    _write(USER_LIB, lib)
    return {"deleted": did}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-directions")
    ap.add_argument("action", choices=["list", "match", "apply", "save", "delete"])
    ap.add_argument("project", nargs="?")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "list":
            p = _read(os.path.join(a.project, "project.json"), {}) if a.project else {}
            res = {"directions": all_directions(), "current": (p.get("direction") or {}).get("id")}
        elif a.action == "match":
            res = match(a.project)
        elif a.action == "apply":
            res = apply(a.project, x["id"], x.get("parts"), bool(x.get("overwrite")))
        elif a.action == "save":
            res = save(x)
        else:
            res = delete(x["id"])
        print(json.dumps({"event": "result", "data": res}), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except Exception as e:
        print(json.dumps({"event": "error", "message": f"{type(e).__name__}: {e}"}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
