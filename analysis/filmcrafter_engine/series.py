"""A series plan for a micro-drama: a season of short episodes, laid out as an EDITABLE plan, free and local.

What it is, plainly: a scaffold. From your idea and the number of episodes it lays out the shape a serialized story usually has (an opening that hooks, building pressure, a turn in the middle, the
lowest point, a close) and, for each episode, a hook, an escalation, a turning point and an ending, each with a starting suggestion in plain words that uses your idea and the characters and places
already in your film. It does NOT write your story: every suggestion is marked as a suggestion until you write or keep it, nothing is sent anywhere, no provider is called and nothing is charged.
Making the episodes (the shots, the pictures, the video) is a separate step, and each costly step shows its price first.

  <film>/presets/series.json
    {"schema": 1, "idea": str, "preset": id, "episodes": [..N], "season": {logline, genre, tone, rules, ending: {value, source}},
     "cast": [names read from the film's Cast & World], "places": [...],
     "episode": {"n", "title", "seconds", "role", "hook", "escalation", "turning_point", "ending", "cliffhanger": bool, "continuity": {value, source}, "budget_usd": number|null}}

Each text field is {"value", "source": "scaffold"|"you"}. Episode lengths are advice (60, 90 or 120 by default), never a limit; one cliffhanger in every episode is flagged as formula, not required.

  python -m filmcrafter_engine.series <action> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

from . import safeio

SCHEMA = 1
MAX_EPISODES = 60
FIELDS = ("hook", "escalation", "turning_point", "ending", "continuity")
SEASON_FIELDS = ("logline", "tone", "rules", "ending")
MAX_TEXT = 400
ACTIONS = ("get", "create", "set_season", "set_episode", "reset_field", "resize", "report", "export_markdown", "make_films")

# the shape of a season, as a role for episode n of N
def role_of(n: int, total: int) -> str:
    if n == 1:
        return "opening"
    if n == total:
        return "close"
    if total >= 4 and n == total - 1:
        return "lowest point"
    if total >= 3 and n == (total + 1) // 2:
        return "turn"
    return "building" if n < (total + 1) / 2 else "pressure"


GUIDE = {
    "opening": ("Open on the moment that makes someone stay: {hero} wants something and cannot have it.", "Show what {hero} wants and what is in the way.", "A choice or a surprise that sets the whole season going.", "End on a question the next episode answers."),
    "building": ("Start where the last episode left off, with a small new problem for {hero}.", "Make it cost {hero} something to keep going.", "A discovery that changes what {hero} thinks is true.", "Close the scene, open a worry."),
    "turn": ("Begin with the consequence of the last episode.", "Pull the ground from under {hero}: what they believed is not so.", "The reversal: the story now points somewhere else.", "End on what {hero} does about it."),
    "pressure": ("Open with the pressure on {hero} higher than before.", "Take away an easy way out.", "A secret, a deadline or a betrayal comes due.", "End with less hope than the start."),
    "lowest point": ("Open at the lowest: {hero} has lost what they fought for.", "Let it be quiet and true: no help is coming.", "The moment {hero} decides who they are.", "End with one small reason to go on."),
    "close": ("Open with the cost of the last choice.", "Pay off the promises the season made.", "The answer to the question from episode 1.", "A close that fits: not necessarily a cliffhanger."),
}
GENRE = {"romantic": " Keep the feeling close: looks, silences, what is not said.", "mystery": " Plant a clue and hide one thing.", "fantasy": " Let the world's rules matter to the choice.", "animated": " Let the acting be big and clear.", "drama": ""}


def _txt(v, n: int = MAX_TEXT) -> str:
    return " ".join(str(v or "").split())[:n]


def _field(value: str, source: str = "scaffold") -> dict:
    return {"value": _txt(value), "source": source if source in ("scaffold", "you") else "scaffold"}


def _path(d: str) -> str:
    from . import presets
    return os.path.join(presets.root(d), "series.json")


def _genre(preset: str) -> str:
    return next((g for g in ("romantic", "mystery", "fantasy", "animated") if g in (preset or "")), "drama")


def _film_cast(d: str) -> tuple[list[str], list[str]]:
    """The people and places already in the film's Cast & World (read only)."""
    from . import bible, presets
    f = presets.film_of(d)
    if not f:
        return [], []
    try:
        b = bible.load(f)
    except SystemExit:
        return [], []
    names = [c["name"].title() if c["name"].isupper() else c["name"] for c in b.get("characters", []) if c.get("name")][:12]
    places = [e["name"] for e in b.get("environments", []) if e.get("name")][:12]
    return names, places


def _episode(n: int, total: int, seconds: int, hero: str, genre: str, idea_words: str) -> dict:
    role = role_of(n, total)
    g = GUIDE[role]
    fill = lambda s: s.format(hero=hero)
    extra = GENRE[genre]
    return {"n": n, "title": f"Episode {n}", "seconds": seconds, "role": role, "hook": _field(fill(g[0])), "escalation": _field(fill(g[1]) + extra), "turning_point": _field(fill(g[2])),
            "ending": _field(fill(g[3])), "cliffhanger": role not in ("close",) and n % 3 != 0, "continuity": _field(""), "budget_usd": None}


def _clean(raw) -> dict | None:
    """A stored plan made safe. None when there is none."""
    if not isinstance(raw, dict) or not isinstance(raw.get("episodes"), list):
        return None
    if isinstance(raw.get("schema"), int) and not isinstance(raw.get("schema"), bool) and raw["schema"] > SCHEMA:
        raise SystemExit("This film's series plan was made by a newer FilmCrafter. Update FilmCrafter to open it; nothing has been changed.")
    fld = lambda v: _field(v.get("value"), v.get("source")) if isinstance(v, dict) else _field("")
    season = raw.get("season") if isinstance(raw.get("season"), dict) else {}
    eps = []
    for e in raw["episodes"][:MAX_EPISODES]:
        if not isinstance(e, dict) or not isinstance(e.get("n"), int):
            continue
        secs = e.get("seconds") if isinstance(e.get("seconds"), int) and not isinstance(e.get("seconds"), bool) and 10 <= e["seconds"] <= 3600 else 90
        bud = e.get("budget_usd")
        eps.append({"n": e["n"], "title": _txt(e.get("title"), 80) or f"Episode {e['n']}", "seconds": secs, "role": e.get("role") if e.get("role") in GUIDE else "building",
                    **{k: fld(e.get(k)) for k in FIELDS if k != "continuity"}, "continuity": fld(e.get("continuity")), "cliffhanger": bool(e.get("cliffhanger")),
                    "budget_usd": round(float(bud), 2) if isinstance(bud, (int, float)) and not isinstance(bud, bool) and bud == bud and 0 <= bud <= 100000 else None})
    eps.sort(key=lambda x: x["n"])
    return {"schema": SCHEMA, "idea": _txt(raw.get("idea"), 1200), "preset": _txt(raw.get("preset"), 60), "hero": _txt(raw.get("hero"), 60), "episodes": eps,
            "season": {"logline": fld(season.get("logline")), "genre": _txt(season.get("genre"), 40), "tone": fld(season.get("tone")), "rules": fld(season.get("rules")), "ending": fld(season.get("ending")),
                       "season_budget_usd": round(float(season["season_budget_usd"]), 2) if isinstance(season.get("season_budget_usd"), (int, float)) and not isinstance(season.get("season_budget_usd"), bool) and season["season_budget_usd"] >= 0 else None},
            "films": {str(k)[:4]: v[:600] for k, v in list((raw.get("films") if isinstance(raw.get("films"), dict) else {}).items())[:MAX_EPISODES] if isinstance(v, str)},
            "cast": [_txt(x, 60) for x in (raw.get("cast") or []) if isinstance(x, str)][:12], "places": [_txt(x, 60) for x in (raw.get("places") or []) if isinstance(x, str)][:12]}


def load(d: str) -> dict | None:
    return _clean(safeio.read_json(_path(d), None))


def _save(d: str, plan: dict) -> None:
    os.makedirs(os.path.dirname(_path(d)), exist_ok=True)
    safeio.write_json(_path(d), plan)


def get(d: str) -> dict:
    plan = load(d)
    return {"plan": plan, "exists": plan is not None, "note": NOTE}


NOTE = ("This is a plan to edit, not a story written for you. The suggestions are marked until you write or keep them. Nothing is sent anywhere and nothing is charged; making the episodes is a "
        "separate step that shows its price first.")


def create(d: str, idea: str, episodes: int = 10, seconds: int = 90, preset: str = "vertical_micro_drama", hero: str = "") -> dict:
    if load(d) is not None:
        raise SystemExit("This film already has a series plan. Change it, or delete series.json from its presets folder to start again.")
    idea = _txt(idea, 1200)
    if not idea:
        raise SystemExit("Say the idea in a sentence or two.")
    if isinstance(episodes, bool) or not isinstance(episodes, int) or not 1 <= episodes <= MAX_EPISODES:
        raise SystemExit(f"A season has 1 to {MAX_EPISODES} episodes.")
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not 10 <= seconds <= 3600:
        raise SystemExit("An episode length is a whole number of seconds, 10 to 3600.")
    cast, places = _film_cast(d)
    who = _txt(hero, 60) or (cast[0] if cast else "your hero")
    genre = _genre(preset)
    first = re.split(r"(?<=[.!?])\s+", idea)[0][:200]
    plan = {"schema": SCHEMA, "idea": idea, "preset": _txt(preset, 60), "hero": who, "cast": cast, "places": places,
            "season": {"logline": _field(first), "genre": genre, "tone": _field(""), "rules": _field(""), "ending": _field("How does the season end, and what does it say?"), "season_budget_usd": None},
            "episodes": [_episode(n, episodes, seconds, who, genre, first) for n in range(1, episodes + 1)]}
    plan["episodes"][0]["title"] = "Episode 1: the hook"
    _save(d, plan)
    return get(d)


def _need(d: str) -> dict:
    plan = load(d)
    if plan is None:
        raise SystemExit("There is no series plan yet. Make one first.")
    return plan


def set_season(d: str, data: dict) -> dict:
    plan = _need(d)
    for k in SEASON_FIELDS:
        if k in data:
            plan["season"][k] = _field(data[k], "you")
    if "genre" in data:
        plan["season"]["genre"] = _txt(data["genre"], 40)
    if "season_budget_usd" in data:
        v = data["season_budget_usd"]
        plan["season"]["season_budget_usd"] = None if v in (None, "") else v
    _save(d, _clean(plan))
    return get(d)


def set_episode(d: str, n: int, data: dict) -> dict:
    plan = _need(d)
    ep = next((e for e in plan["episodes"] if e["n"] == n), None)
    if ep is None:
        raise SystemExit("That episode is not in the plan.")
    for k in FIELDS:
        if k in data:
            ep[k] = _field(data[k], "you")                              # whatever you write is yours, even if you wrote the suggestion back
    if "title" in data:
        ep["title"] = _txt(data["title"], 80) or ep["title"]
    if "seconds" in data:
        ep["seconds"] = data["seconds"]
    if "cliffhanger" in data:
        ep["cliffhanger"] = bool(data["cliffhanger"])
    if "budget_usd" in data:
        ep["budget_usd"] = data["budget_usd"]
    _save(d, _clean(plan))
    return get(d)


def reset_field(d: str, n: int, key: str) -> dict:
    """Put a field back to the suggestion (drops what you wrote there)."""
    plan = _need(d)
    ep = next((e for e in plan["episodes"] if e["n"] == n), None)
    if ep is None or key not in FIELDS:
        raise SystemExit("That part of the plan is not there.")
    fresh = _episode(n, len(plan["episodes"]), ep["seconds"], plan["hero"] or "your hero", plan["season"]["genre"], "")
    ep[key] = fresh[key] if key != "continuity" else _field("")
    _save(d, _clean(plan))
    return get(d)


def resize(d: str, episodes: int) -> dict:
    """More or fewer episodes. What you wrote is kept; the roles of the unwritten ones follow the new shape."""
    plan = _need(d)
    if isinstance(episodes, bool) or not isinstance(episodes, int) or not 1 <= episodes <= MAX_EPISODES:
        raise SystemExit(f"A season has 1 to {MAX_EPISODES} episodes.")
    cur = {e["n"]: e for e in plan["episodes"]}
    secs = plan["episodes"][-1]["seconds"] if plan["episodes"] else 90
    out = []
    for n in range(1, episodes + 1):
        fresh = _episode(n, episodes, secs, plan["hero"] or "your hero", plan["season"]["genre"], "")
        old = cur.get(n)
        if old:
            for k in FIELDS:
                if old[k]["source"] == "you":
                    fresh[k] = old[k]
            fresh.update({"title": old["title"], "seconds": old["seconds"], "budget_usd": old["budget_usd"]})
            if any(old[k]["source"] == "you" for k in FIELDS) or old["title"] != f"Episode {n}":
                fresh["cliffhanger"] = old["cliffhanger"]
        out.append(fresh)
    plan["episodes"] = out
    _save(d, _clean(plan))
    return get(d)


def report(d: str) -> dict:
    """A plain continuity and readiness report: what is empty, who and where is mentioned, formula warnings, and the budget you set. It reads the plan and the film's cast; it changes nothing."""
    plan = _need(d)
    eps = plan["episodes"]
    notes = []
    mine = lambda e, k: e[k]["source"] == "you" and e[k]["value"]
    for e in eps:
        empty = [k.replace("_", " ") for k in ("hook", "ending") if not mine(e, k)]
        if empty:
            notes.append({"level": "todo", "episode": e["n"], "what": f"Episode {e['n']}: write your own {' and '.join(empty)} (the suggestion is only a starting point)."})
    cliff = sum(1 for e in eps if e["cliffhanger"])
    if len(eps) >= 4 and cliff == len(eps):
        notes.append({"level": "advice", "episode": None, "what": "Every episode is marked as ending on a cliffhanger. A cliffhanger is a choice, not a rule: a quiet close in a few episodes can hit harder."})
    text = lambda e: " ".join(e[k]["value"] for k in FIELDS if e[k]["source"] == "you").lower()
    seen = {c: [e["n"] for e in eps if c.lower() in text(e)] for c in plan["cast"]}
    for c, where in seen.items():
        if where and where[0] > 1:
            notes.append({"level": "advice", "episode": where[0], "what": f"{c} first appears in your plan in episode {where[0]}. Set them up earlier if the audience should know them by then."})
    places = {p: [e["n"] for e in eps if p.lower() in text(e)] for p in plan["places"]}
    spent = [e["budget_usd"] for e in eps if e["budget_usd"] is not None]
    cap = plan["season"].get("season_budget_usd")
    if cap is not None and spent and sum(spent) > cap:
        notes.append({"level": "warn", "episode": None, "what": f"The episode budgets add up to ${sum(spent):.2f}, over the season's ${cap:.2f}."})
    secs = sum(e["seconds"] for e in eps)
    return {"episodes": len(eps), "total_seconds": secs, "written": sum(1 for e in eps if any(e[k]["source"] == "you" for k in FIELDS)), "cliffhangers": cliff, "cast": seen, "places": places,
            "budget_total_usd": round(sum(spent), 2) if spent else None, "season_budget_usd": cap, "notes": notes}


def export_markdown(d: str, path: str) -> dict:
    plan = _need(d)
    dest = os.path.abspath(str(path or ""))
    if not dest.lower().endswith(".md") or not os.path.isdir(os.path.dirname(dest)):
        raise SystemExit("Choose a .md file to save it as, in a folder that exists.")
    s = plan["season"]
    lines = [f"# Series plan", "", f"**Idea:** {plan['idea']}", "", f"**Logline:** {s['logline']['value']}", f"**Genre:** {s['genre']}  |  **Episodes:** {len(plan['episodes'])}", ""]
    mark = lambda f: f["value"] + ("" if f["source"] == "you" else "  _(suggestion)_")
    for e in plan["episodes"]:
        lines += [f"## {e['title']}  ({e['seconds']} s, {e['role']})", "", f"- **Hook:** {mark(e['hook'])}", f"- **Escalation:** {mark(e['escalation'])}", f"- **Turning point:** {mark(e['turning_point'])}",
                  f"- **Ending:** {mark(e['ending'])}{'  (cliffhanger)' if e['cliffhanger'] else ''}", f"- **Continuity:** {e['continuity']['value'] or '-'}", ""]
    tmp = f"{dest}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    os.replace(tmp, dest)
    return {"path": dest}


def _outline(plan: dict, e: dict, season: str) -> str:
    """The story of one episode, as a plain outline made from the plan: yours to edit, and kept exactly as given once the film is made."""
    s = plan["season"]
    lines = [f"{season.upper()}: {e['title']}", f"(An outline made from the season plan: episode {e['n']} of {len(plan['episodes'])}, about {e['seconds']} seconds. Change any of it.)", ""]
    for label, v in (("The idea of the season", plan.get("idea")), ("Logline", s["logline"]["value"]), ("Tone", s["tone"]["value"]), ("Rules of this world", s["rules"]["value"]), ("The hero", plan.get("hero")),
                     ("Where the season is going", s["ending"]["value"])):
        if v:
            lines.append(f"{label}: {v}")
    lines += ["", f"THIS EPISODE ({e['role']})"]
    for label, key in (("It opens", "hook"), ("It builds", "escalation"), ("The turn", "turning_point"), ("It ends", "ending"), ("Carried over from before", "continuity")):
        if e[key]["value"]:
            lines.append(f"{label}: {e[key]['value']}")
    if e["cliffhanger"]:
        lines.append("It ends on a cliffhanger.")
    return "\n".join(lines)


def make_films(d: str) -> dict:
    """One film for each episode of the season plan, in the folder this film is in: each starts as an outline made from the plan, with the season's presets remembered for it (to preview and apply in Presets) and the
    episode's length. Free: only text and settings are written, nothing is generated or charged, and no film that already exists is touched; asked again, it makes only the episodes that have no film yet."""
    from . import presets, story
    plan = load(d)
    if plan is None:
        raise SystemExit("Make the season plan first.")
    f = presets.film_of(d) or (os.path.abspath(d) if os.path.isfile(os.path.join(d, "film.json")) else None)
    if not f:
        raise SystemExit("This is not a film.")
    root = os.path.dirname(os.path.abspath(f))
    m = story._manifest(f)
    season = str(m.get("title") or "Season")[:80]
    st = presets.load_state(d)
    stack = [p for p in (st["stack"] or st["pending"] or ([plan["preset"]] if plan["preset"] else [])) if p != presets.SETUP_ID]
    films = dict(plan.get("films") or {})
    made, kept = [], []
    for e in plan["episodes"]:
        key = str(e["n"])
        have = films.get(key)
        if have and os.path.isfile(os.path.join(have, "film.json")):
            kept.append({"n": e["n"], "title": e["title"], "dir": have})
            continue
        r = story.create(root, f"{season} - {e['title']}", "outline", _outline(plan, e, season), None, str(m.get("aspect_ratio") or "16:9"))
        if stack:
            try:
                presets.set_pending(r["dir"], stack, {"length": e["seconds"]})
            except SystemExit:
                pass                                                  # the film is made either way; Presets can still be used by hand
        films[key] = r["dir"]
        made.append({"n": e["n"], "title": e["title"], "dir": r["dir"]})
    plan["films"] = films
    _save(d, plan)
    return {"made": made, "kept": kept, "folder": root}


def run(d: str, action: str, x: dict) -> dict:
    n = x.get("n")
    if action == "get":
        return get(d)
    if action == "create":
        return create(d, str(x.get("idea", "")), x.get("episodes", 10), x.get("seconds", 90), str(x.get("preset", "vertical_micro_drama")), str(x.get("hero", "")))
    if action == "set_season":
        return set_season(d, x if isinstance(x, dict) else {})
    if action == "set_episode":
        if isinstance(n, bool) or not isinstance(n, int):
            raise SystemExit("Say which episode.")
        return set_episode(d, n, {k: v for k, v in x.items() if k != "n"})
    if action == "reset_field":
        if isinstance(n, bool) or not isinstance(n, int):
            raise SystemExit("Say which episode.")
        return reset_field(d, n, str(x.get("key", "")))
    if action == "resize":
        return resize(d, x.get("episodes"))
    if action == "report":
        return report(d)
    if action == "export_markdown":
        return export_markdown(d, str(x.get("path", "")))
    if action == "make_films":
        return make_films(d)
    raise SystemExit("Unknown action.")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-series")
    ap.add_argument("action", choices=["get", "create", "set_season", "set_episode", "reset_field", "resize", "report", "export_markdown", "make_films"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    try:
        x = json.loads(a.data)
        print(json.dumps({"event": "result", "data": run(a.project, a.action, x if isinstance(x, dict) else {})}, ensure_ascii=False), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
    except Exception as e:                       # noqa: BLE001
        print(json.dumps({"event": "error", "message": __import__("filmcrafter_engine.errtext", fromlist=["plain"]).plain(e)}), flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
