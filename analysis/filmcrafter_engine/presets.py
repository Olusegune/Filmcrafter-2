"""Creative presets: named bundles of settings FilmCrafter already has (the film's look, its acting profile, a colour grade, an editing style, how it is delivered), that can be stacked, previewed
before they are applied, undone, saved as your own and shared as a file.

A preset is data, never code: a name, a type (production, visual, performance, editing, color, delivery), the settings it carries, and the other presets it INCLUDES (a production preset stacks the
visual, acting, editing, colour and delivery presets that suit it). The settings it can carry are exactly these, each checked when it is loaded:
  look          a look from the library (the film's visual style)                       -> the film's Bible
  acting        an acting profile (natural, restrained, expressive, dramatic, energetic) -> the film's performance settings
  grade         a colour grade (the Colour Studio's numbers)                             -> the film's grade
  editing       an editing style of the Smart Editor                                     -> the film's preferences
  delivery      the export version to make, margins kept clear for phones, captions      -> the film's preferences (never the film's own shape)
  aspect        the shape pictures are made in from now on                               -> the film (only on your say-so once pictures exist)
  duration_hint_s  a length to aim for (advice shown to you, never a limit)

RULES (what wins): the person's own choice beats every preset; a later preset in the stack beats an earlier one; a preset's own settings beat the ones it includes. Applying NEVER overwrites
a choice you already made: it is previewed first as a list (new, already so, or yours-and-different), and a different choice of yours is kept unless you tick it. Nothing is rendered, nothing is
regenerated and no provider is called: only settings change. What an application changed is recorded so it can be undone, and an undo puts back only what is still as the application left it.

  <film>/presets/state.json   {"schema": 1, "stack": [ids], "editing", "delivery", "duration_hint_s", "applied": [...], "favorites": [...], "recent": [...], "mine": {id: preset}}

  python -m filmcrafter_engine.presets <action> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

from . import safeio

SCHEMA = 1
TYPES = ("production", "visual", "performance", "editing", "color", "delivery")
KEYS = ("look", "acting", "grade", "editing", "delivery", "aspect", "duration_hint_s")
MAX_MINE, MAX_APPLIED, MAX_INCLUDES, MAX_DEPTH = 100, 30, 8, 3
MAX_FILE = 64 * 1024
FORMAT = "filmcrafter.preset"
ACTIONS = ("catalog", "plan", "apply", "undo", "save_mine", "delete_mine", "favorite", "export", "import_file", "stack_get", "reframe_set")
_ID = re.compile(r"^[a-z0-9][a-z0-9_\-]{1,59}$")
BUILTIN_FILE = os.path.join(os.path.dirname(__file__), "presets_builtin.json")


# ---------------------------------------------------------------- where it lives

def film_of(d: str) -> str | None:
    from . import character_performance as CP
    return CP.film_dir(d)


def root(d: str) -> str:
    return os.path.join(film_of(d) or os.path.abspath(d), "presets")


def _path(d: str) -> str:
    return os.path.join(root(d), "state.json")


def builtin() -> dict[str, dict]:
    with open(BUILTIN_FILE, encoding="utf-8") as f:
        return {p["id"]: p for p in json.load(f)["presets"]}


# ---------------------------------------------------------------- checking a setting

def _txt(v, n: int) -> str:
    return " ".join(str(v or "").split())[:n]


def clean_settings(raw) -> dict:
    """The settings of a preset made safe: only the known keys, each valid, anything else dropped (or SystemExit when a value is wrong, so a bad file says so)."""
    raw = raw if isinstance(raw, dict) else {}
    out: dict = {}
    if "look" in raw:
        from . import render
        lid = _txt(raw["look"], 60)
        s = render.styles().get(lid)
        if not s or s.get("family") in ("genre", "auto"):
            raise SystemExit(f"The look \"{lid}\" is not one of FilmCrafter's looks.")
        out["look"] = lid
    if "acting" in raw:
        from . import performance
        if raw["acting"] not in performance.PROFILES:
            raise SystemExit("That acting profile is not one of the choices.")
        out["acting"] = raw["acting"]
    if "grade" in raw:
        from . import grading
        g = grading.clean_grade(raw["grade"])
        g.pop("lut", None)                                   # a preset carries numbers, never a file: a LUT stays your own
        g.pop("off", None)
        if g:
            out["grade"] = g
    if "editing" in raw:
        from . import smart_editor
        r = smart_editor.RECIPES.get(raw["editing"] if isinstance(raw["editing"], str) else "")
        if not r or not r.get("built"):
            raise SystemExit("That editing style is not built yet.")
        out["editing"] = raw["editing"]
    if "delivery" in raw:
        from . import export
        dv = raw["delivery"] if isinstance(raw["delivery"], dict) else {}
        if dv.get("export") not in export.PRESETS or dv.get("export") == "preview":
            raise SystemExit("That delivery version is not one FilmCrafter makes.")
        safe = dv.get("safe") if isinstance(dv.get("safe"), dict) else {}
        num = lambda v, hi: round(max(0.0, min(hi, float(v))), 3) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v else 0.0
        out["delivery"] = {"export": dv["export"], "safe": {"top": num(safe.get("top"), 0.3), "bottom": num(safe.get("bottom"), 0.35), "side": num(safe.get("side"), 0.2)}, "captions": bool(dv.get("captions"))}
    if "aspect" in raw:
        from . import story
        if raw["aspect"] not in story.ASPECTS:
            raise SystemExit("That frame shape is not one of the choices.")
        out["aspect"] = raw["aspect"]
    if "duration_hint_s" in raw:
        v = raw["duration_hint_s"]
        if isinstance(v, bool) or not isinstance(v, int) or not 5 <= v <= 7200:
            raise SystemExit("A length to aim for is a whole number of seconds, 5 to 7200.")
        out["duration_hint_s"] = v
    return out


def clean_preset(raw, known: set[str] | None = None) -> dict:
    """A whole preset made safe (used for imports and your own). Raises SystemExit with a plain reason."""
    if not isinstance(raw, dict):
        raise SystemExit("This is not a preset.")
    pid = str(raw.get("id", ""))
    if not _ID.match(pid):
        raise SystemExit("A preset's id is lower-case letters, digits, - and _ (2 to 60 characters).")
    typ = raw.get("type")
    if typ not in TYPES and typ != "custom":
        raise SystemExit("That kind of preset is not one FilmCrafter knows.")
    name = _txt(raw.get("name"), 60)
    if not name:
        raise SystemExit("A preset needs a name.")
    inc = [x for x in (raw.get("includes") if isinstance(raw.get("includes"), list) else []) if isinstance(x, str) and _ID.match(x)][:MAX_INCLUDES]
    if known is not None and any(i not in known for i in inc):
        raise SystemExit("This preset includes another preset that is not here: " + ", ".join(i for i in inc if i not in known)[:120] + ".")
    out = {"id": pid, "type": typ, "group": _txt(raw.get("group"), 30) or ("Mine" if typ == "custom" else typ.capitalize()), "name": name, "description": _txt(raw.get("description"), 300), "use": _txt(raw.get("use"), 200),
           "version": raw.get("version") if isinstance(raw.get("version"), int) and not isinstance(raw.get("version"), bool) and 1 <= raw["version"] <= 999 else 1,
           "thumbnail": None, "includes": inc, "settings": clean_settings(raw.get("settings")),
           "complexity": raw.get("complexity") if isinstance(raw.get("complexity"), int) and 1 <= raw["complexity"] <= 5 else 1}
    if isinstance(raw.get("series"), str) and raw["series"] in ("micro_drama",):
        out["series"] = raw["series"]
    return out


# ---------------------------------------------------------------- the film's own record

def parse_state(s) -> dict:
    """The preset record made safe, from whatever was read."""
    s = s if isinstance(s, dict) else {}
    if isinstance(s.get("schema"), int) and not isinstance(s.get("schema"), bool) and s["schema"] > SCHEMA:
        raise SystemExit("This film's preset record was made by a newer FilmCrafter. Update FilmCrafter to open it; nothing has been changed.")
    mine = {}
    for k, v in (s.get("mine") if isinstance(s.get("mine"), dict) else {}).items():
        try:
            mine[str(k)] = clean_preset(v)
        except SystemExit:
            continue                                        # a damaged preset of yours is left out, not fatal
    ids = lambda x: [i for i in (x if isinstance(x, list) else []) if isinstance(i, str)][:200]
    return {"schema": SCHEMA, "stack": ids(s.get("stack")), "editing": s.get("editing") if isinstance(s.get("editing"), str) else None, "delivery": s.get("delivery") if isinstance(s.get("delivery"), dict) else None,
            "duration_hint_s": s.get("duration_hint_s") if isinstance(s.get("duration_hint_s"), int) and not isinstance(s.get("duration_hint_s"), bool) else None,
            "applied": [a for a in (s.get("applied") if isinstance(s.get("applied"), list) else []) if isinstance(a, dict)][-MAX_APPLIED:], "favorites": ids(s.get("favorites")), "recent": ids(s.get("recent"))[-12:],
            "mine": mine, "reframe": {str(k)[:40]: round(max(0.0, min(1.0, float(v))), 3) for k, v in (s.get("reframe") if isinstance(s.get("reframe"), dict) else {}).items()
                                      if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v}}


def load_state(d: str) -> dict:
    return parse_state(safeio.read_json(_path(d), {}))


def _write(d: str, change) -> dict:
    os.makedirs(root(d), exist_ok=True)

    def run(data):
        cur = parse_state(data)
        change(cur)
        return {k: v for k, v in cur.items()}
    safeio.update_json(_path(d), run, {})
    return load_state(d)


# ---------------------------------------------------------------- the catalog and the stack

def all_presets(d: str) -> dict[str, dict]:
    out = builtin()
    for k, v in load_state(d)["mine"].items():
        if k not in out:
            out[k] = {**v, "mine": True}
    return out


def expand(presets: dict[str, dict], ids: list[str]) -> list[str]:
    """The order settings are laid down in: each preset's included presets first, then the preset itself, later ones after earlier ones. A preset that includes itself, or goes deeper than
    three levels, is refused."""
    order: list[str] = []

    def visit(pid: str, depth: int, trail: tuple):
        if pid not in presets:
            raise SystemExit(f"The preset \"{pid}\" is not here.")
        if pid in trail:
            raise SystemExit("A preset cannot include itself.")
        if depth > MAX_DEPTH:
            raise SystemExit("Presets include presets too deeply.")
        for inc in presets[pid].get("includes", []):
            visit(inc, depth + 1, trail + (pid,))
        if pid not in order:
            order.append(pid)
    for i in ids:
        visit(i, 0, ())
    return order


def resolve(presets: dict[str, dict], ids: list[str]) -> dict:
    """The settings the stack asks for, key by key, with which preset asked: {key: {value, by}}. A later preset wins over an earlier one."""
    out: dict = {}
    for pid in expand(presets, ids):
        for k, v in presets[pid].get("settings", {}).items():
            if k in KEYS:
                out[k] = {"value": v, "by": pid}
    return out


# ---------------------------------------------------------------- what the film has now

def _has_pictures(d: str) -> bool:
    jobs = (safeio.read_json(os.path.join(d, "jobs.json"), {"jobs": []}) or {}).get("jobs", [])
    return any(isinstance(j, dict) and j.get("state") == "ready" for j in jobs)


def current(d: str) -> dict:
    """The film's present choice for each key: {key: {"value": ..., "set": bool}}. `set` is whether the person has made a choice (an automatic default is not one)."""
    from . import bible, grading, performance, story
    st = load_state(d)
    f = film_of(d)
    out: dict = {}
    if f:
        look = bible.effective_look(bible.load(f))
        out["look"] = {"value": look, "set": look not in ("auto", "", None)}
        out["aspect"] = {"value": story._manifest(f).get("aspect_ratio", "16:9"), "set": _has_pictures(d)}
    p = safeio.read_json(os.path.join(d, "project.json"), {}) or {}
    perf = performance.settings(p)
    out["acting"] = {"value": perf["default"], "set": perf["default"] != performance.DEFAULT}         # "natural" is where every film starts, so it is not a choice you made
    g = grading.load(d)["grades"]["film"]
    out["grade"] = {"value": g, "set": bool(g)}
    out["editing"] = {"value": st["editing"], "set": st["editing"] is not None}
    out["delivery"] = {"value": st["delivery"], "set": st["delivery"] is not None}
    out["duration_hint_s"] = {"value": st["duration_hint_s"], "set": st["duration_hint_s"] is not None}
    return out


def plan(d: str, stack: list[str], replace: list[str] | None = None) -> dict:
    """What applying this stack would do, key by key, WITHOUT doing anything: {changes: [{key, status, now, to, by}], stack, notes}.
    status: new (nothing chosen yet), same (already so), yours (you chose something different: kept unless you replace it), replace (you asked to replace it), unavailable (this film cannot take it)."""
    presets = all_presets(d)
    want = resolve(presets, stack)
    now = current(d)
    replace = set(replace or [])
    changes = []
    notes = []
    for k in KEYS:
        if k not in want:
            continue
        v, by = want[k]["value"], want[k]["by"]
        if k not in now:
            changes.append({"key": k, "status": "unavailable", "now": None, "to": v, "by": by, "why": "This project is not a film, so it has no look to set."})
            continue
        cur = now[k]
        if cur["value"] == v:
            st = "same"
        elif not cur["set"]:
            st = "new"
        else:
            st = "replace" if k in replace else "yours"
        changes.append({"key": k, "status": st, "now": cur["value"], "to": v, "by": by, "set": cur["set"]})
    if any(c["key"] == "aspect" and c["status"] in ("yours", "replace") for c in changes):
        notes.append("This film already has pictures made in its current shape. Changing the shape only affects pictures made from now on; the ones you have stay as they are.")
    delivery = next((c for c in changes if c["key"] == "delivery"), None)
    if delivery and delivery["to"]["export"] == "vertical":
        notes.append("Your film keeps its own shape. The vertical version is made as a separate export; the original is never changed.")
    notes.append("Nothing is regenerated and no provider is called: only settings change, and every change can be undone.")
    return {"stack": stack, "order": expand(presets, stack), "changes": changes, "notes": notes}


# ---------------------------------------------------------------- applying and undoing

def _set(d: str, key: str, value) -> None:
    from . import bible, grading, make, performance, story
    f = film_of(d)
    if key == "look":
        bible.update_rules(f, {"style": {"look": value}})
        make.sync(f)                                              # the render project follows the Bible; takes, jobs and approved keyframes there are never touched
    elif key == "aspect":
        story.set_aspect(f, value)
        make.sync(f)
    elif key == "acting":
        performance.set_(d, {"default": value})
    elif key == "grade":
        grading.set_grade(d, "film", None, value)
    # editing, delivery and the length to aim for live in the preset record itself (below)


def _unset(d: str, key: str, before) -> None:
    from . import grading, performance
    if key == "grade":
        grading.clear_grade(d, "film", None) if not before else grading.set_grade(d, "film", None, before)
    elif key == "acting":
        p = os.path.join(d, "project.json")
        proj = safeio.read_json(p, {}) or {}
        if before is None or before == performance.DEFAULT:
            perf = proj.get("performance") or {}
            perf.pop("default", None)
            if perf:
                proj["performance"] = perf
            else:
                proj.pop("performance", None)
            safeio.write_json(p, proj)
        else:
            performance.set_(d, {"default": before})
    else:
        _set(d, key, before)


def apply(d: str, stack: list[str], replace: list[str] | None = None) -> dict:
    pl = plan(d, stack, replace)
    todo = [c for c in pl["changes"] if c["status"] in ("new", "replace")]
    done = []
    for c in todo:
        k = c["key"]
        before = c["now"] if c.get("set") else None
        if k in ("look", "acting", "grade", "aspect"):
            _set(d, k, c["to"])
        done.append({"key": k, "before": before, "after": c["to"], "by": c["by"], "was_set": bool(c.get("set"))})

    def change(cur):
        for x in done:
            if x["key"] in ("editing", "delivery", "duration_hint_s"):
                cur[x["key"]] = x["after"]
        cur["stack"] = [s for s in stack if isinstance(s, str)][:20]
        cur["recent"] = ([r for r in cur["recent"] if r not in stack] + stack)[-12:]
        cur["applied"] = (cur["applied"] + [{"at": int(time.time()), "stack": cur["stack"], "changes": done, "kept": [c["key"] for c in pl["changes"] if c["status"] == "yours"]}])[-MAX_APPLIED:]
    _write(d, change)
    return {"changed": [x["key"] for x in done], "kept": [c["key"] for c in pl["changes"] if c["status"] == "yours"], "same": [c["key"] for c in pl["changes"] if c["status"] == "same"], "plan": pl}


def undo(d: str) -> dict:
    """Put back what the last application changed, but only where it is still as that application left it (a choice you made since is not touched)."""
    st = load_state(d)
    if not st["applied"]:
        raise SystemExit("There is nothing to undo.")
    last = st["applied"][-1]
    now = current(d)
    restored, skipped = [], []
    for x in reversed(last["changes"]):
        k = x["key"]
        cur = now.get(k, {}).get("value")
        if cur != x["after"]:
            skipped.append(k)
            continue
        if k in ("editing", "delivery", "duration_hint_s"):
            restored.append(k)
        else:
            _unset(d, k, x["before"])
            restored.append(k)

    def change(c):
        for k in restored:
            if k in ("editing", "delivery", "duration_hint_s"):
                before = next(x["before"] for x in last["changes"] if x["key"] == k)
                c[k] = before
        c["applied"] = c["applied"][:-1]
    _write(d, change)
    return {"restored": restored, "kept_as_changed_since": skipped}


# ---------------------------------------------------------------- yours, favourites, files

def catalog(d: str) -> dict:
    st = load_state(d)
    ps = all_presets(d)
    rows = []
    for p in ps.values():
        rows.append({**{k: p.get(k) for k in ("id", "type", "group", "name", "description", "use", "version", "thumbnail", "includes", "settings", "complexity", "series")}, "mine": bool(p.get("mine")),
                     "favorite": p["id"] in st["favorites"], "recent": p["id"] in st["recent"], "in_stack": p["id"] in st["stack"]})
    return {"presets": rows, "stack": st["stack"], "types": list(TYPES), "applied": len(st["applied"]), "current": {k: v for k, v in current(d).items()}, "is_film": film_of(d) is not None}


def save_mine(d: str, name: str, stack: list[str] | None = None) -> dict:
    """Keep your own preset: the settings of a stack you name, or, with no stack, of the choices the film has made now."""
    nm = _txt(name, 60)
    if not nm:
        raise SystemExit("Give the preset a name.")
    if stack:
        settings = {k: v["value"] for k, v in resolve(all_presets(d), stack).items()}
    else:
        settings = {k: v["value"] for k, v in current(d).items() if v["set"] and k not in ("aspect",)}
    if not settings:
        raise SystemExit("There is nothing chosen to keep yet.")
    base = re.sub(r"[^a-z0-9]+", "-", nm.lower()).strip("-")[:40] or "mine"
    pid, n = f"mine-{base}", 2
    ps = all_presets(d)
    while pid in ps:
        pid, n = f"mine-{base}-{n}", n + 1
    p = clean_preset({"id": pid, "type": "custom", "name": nm, "description": "Your own preset.", "settings": settings})

    def change(cur):
        if len(cur["mine"]) >= MAX_MINE:
            raise SystemExit("You have kept as many presets as FilmCrafter holds. Delete one first.")
        cur["mine"][pid] = p
    _write(d, change)
    return {"saved": pid, "catalog": catalog(d)}


def delete_mine(d: str, pid: str) -> dict:
    if pid not in load_state(d)["mine"]:
        raise SystemExit("That is not one of your own presets.")

    def change(cur):
        cur["mine"].pop(pid, None)
        cur["favorites"] = [f for f in cur["favorites"] if f != pid]
        cur["stack"] = [s for s in cur["stack"] if s != pid]
    _write(d, change)
    return catalog(d)


def favorite(d: str, pid: str, on: bool) -> dict:
    if pid not in all_presets(d):
        raise SystemExit("That preset is not here.")

    def change(cur):
        cur["favorites"] = [f for f in cur["favorites"] if f != pid] + ([pid] if on else [])
    _write(d, change)
    return catalog(d)


def export_preset(d: str, pid: str, path: str) -> dict:
    """Write one preset as a file you can share (settings only: no paths, no pictures, no keys)."""
    p = all_presets(d).get(pid)
    if not p:
        raise SystemExit("That preset is not here.")
    dest = os.path.abspath(str(path or ""))
    if not dest.lower().endswith(".json") or not os.path.isdir(os.path.dirname(dest)):
        raise SystemExit("Choose a .json file to save it as, in a folder that exists.")
    own = {k: p[k] for k in ("id", "type", "group", "name", "description", "use", "version", "complexity", "settings", "includes", "series") if k in p}
    own["includes"] = []                                       # a shared file carries its own settings, so it never needs another file to make sense
    own["settings"] = {k: v["value"] for k, v in resolve(all_presets(d), [pid]).items()}
    tmp = f"{dest}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"format": FORMAT, "schema": SCHEMA, "preset": own}, f, indent=1, ensure_ascii=False)
    os.replace(tmp, dest)
    return {"path": dest, "preset": pid}


def import_file(d: str, path: str) -> dict:
    p = os.path.realpath(str(path or ""))
    if not p.lower().endswith(".json") or not os.path.isfile(p):
        raise SystemExit("Choose a preset file (.json).")
    if os.path.getsize(p) > MAX_FILE:
        raise SystemExit("This file is too large to be a preset.")
    try:
        data = json.loads(open(p, encoding="utf-8-sig").read())
    except (OSError, ValueError):
        raise SystemExit("This file is not a preset file.")
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise SystemExit("This is not a FilmCrafter preset file.")
    if isinstance(data.get("schema"), int) and data["schema"] > SCHEMA:
        raise SystemExit("This preset was made by a newer FilmCrafter. Update FilmCrafter to use it.")
    raw = data.get("preset") if isinstance(data.get("preset"), dict) else {}
    raw = {**raw, "includes": [], "type": raw.get("type") if raw.get("type") in TYPES else "custom"}
    name = _txt(raw.get("name"), 60) or "Imported preset"
    ps = all_presets(d)
    pid = "mine-" + (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "imported")
    base, n = pid, 2
    while pid in ps:
        pid, n = f"{base}-{n}", n + 1
    clean = clean_preset({**raw, "id": pid, "type": "custom", "name": name, "description": raw.get("description") or "Imported."})
    if not clean["settings"]:
        raise SystemExit("This preset sets nothing FilmCrafter can use.")

    def change(cur):
        if len(cur["mine"]) >= MAX_MINE:
            raise SystemExit("You have kept as many presets as FilmCrafter holds. Delete one first.")
        cur["mine"][pid] = clean
    _write(d, change)
    return {"imported": pid, "name": name, "catalog": catalog(d)}


def reframe_set(d: str, shot: str, x) -> dict:
    """Which part of a wide picture the vertical version keeps for a shot: 0 is the left edge, 0.5 the middle (the default), 1 the right edge. None puts it back to the middle."""
    from .safe import check_id
    sid = check_id(shot, "shot")
    if x is not None and (isinstance(x, bool) or not isinstance(x, (int, float)) or x != x or not 0 <= x <= 1):
        raise SystemExit("The part of the picture to keep is between 0 (the left edge) and 1 (the right edge).")

    def change(cur):
        if x is None or abs(x - 0.5) < 0.0005:
            cur["reframe"].pop(sid, None)
        else:
            cur["reframe"][sid] = round(float(x), 3)
    _write(d, change)
    return stack_get(d)


def reframe_for(d: str, shot_id: str) -> float:
    """Where the vertical version looks in this shot (0.5, the middle, unless you chose). Reads only; a damaged record means the middle."""
    try:
        return load_state(d)["reframe"].get(shot_id, 0.5)
    except SystemExit:
        return 0.5


def delivery_safe_bottom(d: str) -> float:
    """The bottom margin kept clear for captions in a portrait version, from the delivery you applied (0 when none was)."""
    try:
        dv = load_state(d)["delivery"] or {}
    except SystemExit:
        return 0.0
    return float((dv.get("safe") or {}).get("bottom") or 0.0) if dv.get("export") in ("vertical", "portrait", "tall", "ultratall") else 0.0


def stack_get(d: str) -> dict:
    st = load_state(d)
    return {"stack": st["stack"], "reframe": st["reframe"], "editing": st["editing"], "delivery": st["delivery"], "duration_hint_s": st["duration_hint_s"], "applied": [{"at": a.get("at"), "stack": a.get("stack"), "changed": [c["key"] for c in a.get("changes", [])],
                                                                                                         "kept": a.get("kept", [])} for a in st["applied"]]}


def run(d: str, action: str, x: dict) -> dict:
    ids = lambda v: [i for i in (v if isinstance(v, list) else []) if isinstance(i, str) and len(i) <= 60][:20]
    if action == "catalog":
        return catalog(d)
    if action == "plan":
        return plan(d, ids(x.get("stack")), ids(x.get("replace")))
    if action == "apply":
        return apply(d, ids(x.get("stack")), ids(x.get("replace")))
    if action == "undo":
        return undo(d)
    if action == "save_mine":
        return save_mine(d, str(x.get("name", "")), ids(x.get("stack")) or None)
    if action == "delete_mine":
        return delete_mine(d, str(x.get("id", ""))[:60])
    if action == "favorite":
        return favorite(d, str(x.get("id", ""))[:60], bool(x.get("on")))
    if action == "export":
        return export_preset(d, str(x.get("id", ""))[:60], str(x.get("path", "")))
    if action == "import_file":
        return import_file(d, str(x.get("path", "")))
    if action == "stack_get":
        return stack_get(d)
    if action == "reframe_set":
        return reframe_set(d, str(x.get("shot", "")), x.get("x"))
    raise SystemExit("Unknown action.")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-presets")
    ap.add_argument("action", choices=["catalog", "plan", "apply", "undo", "save_mine", "delete_mine", "favorite", "export", "import_file", "stack_get", "reframe_set"])
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
        print(json.dumps({"event": "error", "message": f"{type(e).__name__}: {e}"}), flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
