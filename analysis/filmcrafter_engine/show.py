"""Shows: a musical (or any multi-song production) made of numbers and spoken scenes, with one cast and one world.

  <Show>/show.json   title, acts, item order, transitions, look, aspect ratio, routing, character voices
  <Show>/cast/       a normal project with no song: the shared Reference library and Production Bible, edited with the
                     usual Library and Bible screens
  <Show>/items/NN …/ each item is a normal FilmCrafter project: a number (a song) or a spoken scene (its generated
                     dialogue becomes its track), so the whole song workflow works on it unchanged
  <Show>/exports/    the whole show, an act, or an item

The cast, Bible, look, aspect ratio and routing are synced from the show into every item (cast images copied, so an item
also works on its own). Items are never deleted: removing one moves it to <Show>/removed/.

  python -m filmcrafter_engine.show <action> <show_dir> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid

SCHEMA = 1
TRANSITIONS = ("cut", "black", "flow")
SYNCED = ("look", "aspect_ratio", "routing")
SKIP_COPY = {"cache", "exports", "backups", "thumbnails", "__pycache__"}


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


def _slug(title: str) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", title).strip().rstrip(".")
    return re.sub(r"\s+", " ", s)[:60] or "Untitled"


def is_show(path: str) -> bool:
    return os.path.isfile(os.path.join(path, "show.json"))


def _show(s: str) -> dict:
    data = _read(os.path.join(s, "show.json"))
    if not data:
        data = _read(os.path.join(s, "show.json.bak"))    # a damaged show.json falls back to the last good copy
        if data:
            _write(os.path.join(s, "show.json"), data)
    if not data:
        raise SystemExit("That isn't a FilmCrafter show.")
    data.setdefault("acts", [{"name": "Act 1", "items": []}])
    data.setdefault("items", {})
    data.setdefault("voices", {})
    return data


def _save(s: str, data: dict) -> dict:
    data["modified"] = int(time.time())
    path = os.path.join(s, "show.json")
    if os.path.isfile(path) and _read(path):
        shutil.copy2(path, path + ".bak")                  # the last good copy, never replaced by an unreadable one
    _write(path, data)
    return data


def _order(data: dict) -> list[str]:
    return [i for a in data["acts"] for i in a["items"] if i in data["items"]]


def _inside(base: str, path: str) -> bool:
    b, p = os.path.normcase(os.path.realpath(base)), os.path.normcase(os.path.realpath(path))
    try:
        return os.path.commonpath([b, p]) == b and p != b
    except ValueError:
        return False


def item_dir(s: str, data: dict, item_id: str) -> str:
    """An item's folder. It must sit inside <Show>/items: a hand-edited show.json can't point the show at other folders."""
    d = os.path.normpath(os.path.join(s, data["items"][item_id]["dir"]))
    root = os.path.normcase(os.path.realpath(os.path.join(s, "items")))
    real = os.path.normcase(os.path.realpath(d))
    try:
        inside = os.path.commonpath([root, real]) == root and real != root
    except ValueError:                                  # a different drive
        inside = False
    if not inside:
        raise SystemExit(f"{data['items'][item_id].get('title', 'An item')} points outside the show's items folder.")
    return d


# ---------------------------------------------------------------- create

def create(root: str, title: str, aspect_ratio: str = "16:9") -> dict:
    os.makedirs(root, exist_ok=True)
    base = _slug(title)
    s, n = os.path.join(root, base), 2
    while os.path.exists(s):
        s, n = os.path.join(root, f"{base} {n}"), n + 1
    for sub in ("items", "exports", "removed", os.path.join("cast", "assets")):
        os.makedirs(os.path.join(s, sub), exist_ok=True)
    _write(os.path.join(s, "cast", "project.json"), {"schema_version": 2, "title": f"{title}: cast", "show_cast": True,
                                                     "state": "cast", "look": {"style": "auto"}, "aspect_ratio": aspect_ratio})
    data = {"schema": SCHEMA, "title": title, "created": int(time.time()), "aspect_ratio": aspect_ratio,
            "look": {"style": "auto"}, "acts": [{"name": "Act 1", "items": []}], "items": {}, "voices": {}}
    _save(s, data)
    return {"dir": s, **status(s)}


def _new_item_dir(s: str, data: dict, title: str) -> str:
    n = len(data["items"]) + 1
    rel = os.path.join("items", f"{n:02d} {_slug(title)}")
    while os.path.exists(os.path.join(s, rel)):
        n += 1
        rel = os.path.join("items", f"{n:02d} {_slug(title)}")
    for sub in ("assets", "generations", "thumbnails", "cache", "exports"):
        os.makedirs(os.path.join(s, rel, sub), exist_ok=True)
    return rel


def _place(data: dict, item_id: str, act: int | None) -> None:
    a = data["acts"][act if act is not None and 0 <= act < len(data["acts"]) else len(data["acts"]) - 1]
    a["items"].append(item_id)


def add_number(s: str, song: str | None, title: str, lyrics: str | None = None, act: int | None = None) -> dict:
    """A song: a normal project inside the show (the song is copied; the original is never touched). Without a song file
    (a number made from a script) it waits for one: see attach_song."""
    if song and not os.path.isfile(song):
        raise SystemExit("That song file can't be found.")
    data = _show(s)
    rel = _new_item_dir(s, data, title)
    d = os.path.join(s, rel)
    p = {"schema_version": 1, "title": title, "created": int(time.time()), "state": "new", "look": data.get("look", {"style": "auto"})}
    if song:
        ext = os.path.splitext(song)[1].lower() or ".wav"
        shutil.copy2(song, os.path.join(d, f"song{ext}"))
        p.update({"song": f"song{ext}", "source_song": song})
    else:
        p.update({"song": "", "song_pending": True})
    if lyrics and lyrics.strip():
        with open(os.path.join(d, "lyrics.txt"), "w", encoding="utf-8") as f:
            f.write(lyrics)
        p["lyrics"] = "lyrics.txt"
    item_id = uuid.uuid4().hex[:8]
    p["show_item"] = {"id": item_id, "kind": "number"}
    _write(os.path.join(d, "project.json"), p)
    data["items"][item_id] = {"kind": "number", "title": title, "dir": rel.replace(os.sep, "/"), "transition": "cut"}
    _place(data, item_id, act)
    _save(s, data)
    sync(s)
    return {**status(s), "item": item_id, "dir": d}


def attach_song(s: str, item_id: str, song: str) -> dict:
    """Give a number that was made from a script its recorded song (copied in; the original is never touched)."""
    data = _show(s)
    if item_id not in data["items"] or data["items"][item_id]["kind"] != "number":
        raise SystemExit("That isn't a number in the show.")
    if not os.path.isfile(song):
        raise SystemExit("That song file can't be found.")
    if os.path.splitext(song)[1].lower() not in (".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg"):
        raise SystemExit("Use an audio file (mp3, wav, m4a, flac, aac or ogg).")
    d = item_dir(s, data, item_id)
    p = _read(os.path.join(d, "project.json"), {}) or {}
    if not p.get("song_pending"):
        raise SystemExit("This number already has a song.")
    ext = os.path.splitext(song)[1].lower() or ".wav"
    shutil.copy2(song, os.path.join(d, f"song{ext}"))
    p.update({"song": f"song{ext}", "source_song": song})
    p.pop("song_pending", None)
    _write(os.path.join(d, "project.json"), p)
    return status(s)


def add_existing(s: str, project: str, act: int | None = None) -> dict:
    """An existing song project, copied in (the original stays exactly as it is)."""
    src = _read(os.path.join(project, "project.json"))
    if not src:
        raise SystemExit("That isn't a FilmCrafter project.")
    data = _show(s)
    title = src.get("title") or os.path.basename(project)
    rel = _new_item_dir(s, data, title)
    d = os.path.join(s, rel)
    shutil.copytree(project, d, dirs_exist_ok=True, ignore=lambda _p, names: [n for n in names if n in SKIP_COPY or n.endswith(".filmcrafter")])
    for sub in ("cache", "exports", "thumbnails"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    item_id = uuid.uuid4().hex[:8]
    p = _read(os.path.join(d, "project.json"), {})
    p["show_item"] = {"id": item_id, "kind": "number"}
    _write(os.path.join(d, "project.json"), p)
    data["items"][item_id] = {"kind": "number", "title": title, "dir": rel.replace(os.sep, "/"), "transition": "cut"}
    _place(data, item_id, act)
    _save(s, data)
    sync(s)
    return {**status(s), "item": item_id, "dir": d}


def add_scene(s: str, title: str, setting: str = "", act: int | None = None) -> dict:
    """A spoken scene: dialogue first (voices.py turns it into the scene's track), then the usual Studio."""
    data = _show(s)
    rel = _new_item_dir(s, data, title)
    d = os.path.join(s, rel)
    item_id = uuid.uuid4().hex[:8]
    _write(os.path.join(d, "project.json"), {"schema_version": 1, "title": title, "song": "song.wav", "created": int(time.time()),
                                             "state": "dialogue", "look": data.get("look", {"style": "auto"}),
                                             "show_item": {"id": item_id, "kind": "scene"}, "scene_setting": setting})
    _write(os.path.join(d, "dialogue.json"), {"setting": setting, "lines": []})
    data["items"][item_id] = {"kind": "scene", "title": title, "dir": rel.replace(os.sep, "/"), "transition": "cut"}
    _place(data, item_id, act)
    _save(s, data)
    sync(s)
    return {**status(s), "item": item_id, "dir": d}


def add_intermission(s: str, title: str, seconds: float = 8.0, subtitle: str = "", act: int | None = None) -> dict:
    """An intermission: a title card (white on black, fading in and out) between acts or numbers. Music can be put under it
    with set_ambience. It is made when the show is exported, so it costs nothing."""
    from .show_finish import MAX_CARD, MIN_CARD
    data = _show(s)
    title = " ".join(str(title).split())[:80] or "Intermission"
    rel = _new_item_dir(s, data, title)
    d = os.path.join(s, rel)
    item_id = uuid.uuid4().hex[:8]
    _write(os.path.join(d, "project.json"), {"schema_version": 1, "title": title, "created": int(time.time()), "state": "intermission",
                                             "show_item": {"id": item_id, "kind": "intermission"}})
    data["items"][item_id] = {"kind": "intermission", "title": title, "dir": rel.replace(os.sep, "/"), "transition": "cut",
                              "seconds": min(MAX_CARD, max(MIN_CARD, float(seconds))), "subtitle": " ".join(str(subtitle).split())[:120]}
    _place(data, item_id, act)
    _tidy(data)
    _save(s, data)
    return {**status(s), "item": item_id, "dir": d}


def set_card(s: str, item_id: str, title: str | None = None, seconds: float | None = None, subtitle: str | None = None) -> dict:
    """Change an intermission's card: its title, its subtitle or how long it is shown."""
    from .show_finish import MAX_CARD, MIN_CARD
    data = _show(s)
    meta = data["items"].get(item_id)
    if not meta or meta["kind"] != "intermission":
        raise SystemExit("That isn't an intermission.")
    if title is not None:
        meta["title"] = " ".join(str(title).split())[:80] or "Intermission"
    if subtitle is not None:
        meta["subtitle"] = " ".join(str(subtitle).split())[:120]
    if seconds is not None:
        meta["seconds"] = min(MAX_CARD, max(MIN_CARD, float(seconds)))
    _save(s, data)
    return status(s)


def set_ambience(s: str, item_id: str, file: str | None = None, volume_db: float = -18.0, clear: bool = False) -> dict:
    """Ambience or underscore under a spoken scene or an intermission: an audio file that loops under the item's own sound at a
    set level. It is mixed in when the show is exported; the item's own track is never changed."""
    from .show_finish import check_ambience
    data = _show(s)
    meta = data["items"].get(item_id)
    if not meta or meta["kind"] not in ("scene", "intermission"):
        raise SystemExit("Ambience goes under a spoken scene or an intermission.")
    if clear:
        meta.pop("ambience", None)
    else:
        cur = dict(meta.get("ambience") or {})
        db = check_ambience(file, volume_db) if file else min(0.0, max(-40.0, float(volume_db)))
        if file:
            d = item_dir(s, data, item_id)
            os.makedirs(os.path.join(d, "assets"), exist_ok=True)
            rel = f"assets/ambience-{uuid.uuid4().hex[:6]}{os.path.splitext(file)[1].lower()}"
            shutil.copy2(file, os.path.join(d, rel))
            cur["file"] = rel
        if not cur.get("file"):
            raise SystemExit("Choose an audio file for the ambience.")
        cur["volume_db"] = db
        meta["ambience"] = cur
    _save(s, data)
    return status(s)


def set_budget(s: str, usd: float | None) -> dict:
    """A spending cap for the whole show, in US dollars (nothing or 0 removes it). It is a guide on the show screen and the limit
    the show's overnight render stops at; each item's own renders still ask for confirmation at their price."""
    data = _show(s)
    if usd in (None, "", 0):
        data.pop("budget_usd", None)
    else:
        v = float(usd)
        if not 0 < v <= 1_000_000:
            raise SystemExit("Enter a budget in dollars, above 0.")
        data["budget_usd"] = round(v, 2)
    _save(s, data)
    return status(s)


# ---------------------------------------------------------------- arrange

def move(s: str, item_id: str, delta: int) -> dict:
    """Move an item earlier (-1) or later (+1) in the running order, across act boundaries."""
    data = _show(s)
    order = _order(data)
    if item_id not in order:
        raise SystemExit("That item isn't in the show.")
    i = order.index(item_id)
    j = max(0, min(len(order) - 1, i + delta))
    if i == j:
        return status(s)
    flat = [(ai, x) for ai, a in enumerate(data["acts"]) for x in a["items"] if x in data["items"]]
    target_act, cur_act = flat[j][0], flat[i][0]
    for a in data["acts"]:
        if item_id in a["items"]:
            a["items"].remove(item_id)
    acts = data["acts"][target_act]["items"]
    if target_act != cur_act:   # crossing into the next (or previous) act: become its first (or last) item
        acts.insert(0 if delta > 0 else len(acts), item_id)
    else:
        other = order[j]
        pos = acts.index(other) if other in acts else len(acts)
        acts.insert(pos + (1 if delta > 0 else 0), item_id)
    _tidy(data)
    _save(s, data)
    return status(s)


def set_act(s: str, item_id: str, act: int) -> dict:
    data = _show(s)
    if not 0 <= act < len(data["acts"]):
        raise SystemExit("No such act.")
    if item_id not in data["items"]:
        raise SystemExit("That item isn't in the show.")
    for a in data["acts"]:
        if item_id in a["items"]:
            a["items"].remove(item_id)
    data["acts"][act]["items"].append(item_id)
    _tidy(data)
    _save(s, data)
    return status(s)


def remove_act(s: str, act: int) -> dict:
    """Take away an act. Only an empty act can go, so no number or scene is ever lost with it."""
    data = _show(s)
    if not 0 <= act < len(data["acts"]):
        raise SystemExit("No such act.")
    if data["acts"][act]["items"]:
        raise SystemExit("Move this act's numbers and scenes elsewhere first.")
    if len(data["acts"]) == 1:
        raise SystemExit("A show needs at least one act.")
    data["acts"].pop(act)
    _save(s, data)
    return status(s)


COSTUME_EXT = {".png", ".jpg", ".jpeg", ".webp"}
MAX_COSTUME = 25_000_000


def set_costume(s: str, act: int, character: str, image: str | None = None, note: str = "", clear: bool = False) -> dict:
    """A character's costume for one act: its reference image (and a note) replace the cast image for every item in
    that act, so a change of clothes is one setting, not a copy of the show. The cast itself is never changed."""
    data = _show(s)
    if not 0 <= act < len(data["acts"]):
        raise SystemExit("No such act.")
    character = (character or "").strip()
    if not character:
        raise SystemExit("Choose a character.")
    costumes = data["acts"][act].setdefault("costumes", {})
    if clear:
        costumes.pop(character, None)
    else:
        entry = dict(costumes.get(character) or {})
        if image:
            ext = os.path.splitext(image)[1].lower()
            if ext not in COSTUME_EXT or not os.path.isfile(image):
                raise SystemExit("Use a PNG, JPG or WebP image for the costume.")
            if os.path.getsize(image) > MAX_COSTUME:
                raise SystemExit("That image is too large (25 MB at most).")
            rel = f"assets/costumes/{_slug(character)}-act{act + 1}-{uuid.uuid4().hex[:6]}{ext}"
            os.makedirs(os.path.join(s, "cast", "assets", "costumes"), exist_ok=True)
            shutil.copy2(image, os.path.join(s, "cast", rel))
            entry["file"] = rel
        entry["note"] = (note or "").strip()[:300]
        if not entry.get("file") and not entry["note"]:
            raise SystemExit("Choose an image or write a note for the costume.")
        costumes[character] = entry
    if not costumes:
        data["acts"][act].pop("costumes", None)
    _save(s, data)
    sync(s)
    return status(s)


def _tidy(data: dict) -> None:
    """The last item has nothing to hand over to, so a leftover 'flow' or 'black' on it goes back to a cut."""
    order = _order(data)
    if order and data["items"][order[-1]].get("transition") != "cut":
        data["items"][order[-1]]["transition"] = "cut"


def add_act(s: str, name: str | None = None) -> dict:
    data = _show(s)
    data["acts"].append({"name": (name or f"Act {len(data['acts']) + 1}").strip()[:60], "items": []})
    _save(s, data)
    return status(s)


def rename(s: str, item_id: str | None, title: str, act: int | None = None) -> dict:
    data = _show(s)
    title = title.strip()[:80]
    if not title:
        raise SystemExit("Give it a name.")
    if act is not None:
        if not 0 <= act < len(data["acts"]):
            raise SystemExit("No such act.")
        data["acts"][act]["name"] = title
    elif item_id in data["items"]:
        data["items"][item_id]["title"] = title
        p = _read(os.path.join(item_dir(s, data, item_id), "project.json"), {})
        p["title"] = title
        _write(os.path.join(item_dir(s, data, item_id), "project.json"), p)
    else:
        data["title"] = title
    _save(s, data)
    return status(s)


def set_transition(s: str, item_id: str, kind: str) -> dict:
    """How this item hands over to the next: cut, through black, or flow (its last shot ends on the next item's first frame)."""
    if kind not in TRANSITIONS:
        raise SystemExit("Choose cut, black or flow.")
    data = _show(s)
    order = _order(data)
    if item_id not in order:
        raise SystemExit("That item isn't in the show.")
    data["items"][item_id]["transition"] = kind
    _save(s, data)
    if kind == "flow":
        _flow_across(s, data, item_id)
    return status(s)


def _flow_across(s: str, data: dict, item_id: str) -> None:
    """Flow: the last shot of this item gets the next item's first keyframe as its end frame (frames.py, 'own')."""
    order = _order(data)
    i = order.index(item_id)
    if i == len(order) - 1:
        raise SystemExit("This is the last item; there's nothing after it to flow into.")
    a, b = item_dir(s, data, item_id), item_dir(s, data, order[i + 1])
    from . import frames
    try:
        _, plan_a = frames._plan(a)
        name_b, plan_b = frames._plan(b)
    except Exception:
        raise SystemExit("Both items need a shot plan before they can flow into each other.")
    last, first = frames._order(plan_a)[-1:], frames._order(plan_b)[:1]
    start = frames.start_ref(b, name_b, first[0]) if first else None
    if not (last and start):
        raise SystemExit("The next item needs a keyframe on its first shot before this item can flow into it.")
    frames.use_image(a, last[0], os.path.join(b, start[len(frames.PROJECT):]))


def remove(s: str, item_id: str) -> dict:
    """Take an item out of the show. Its folder is kept in <Show>/removed/ (nothing is deleted)."""
    data = _show(s)
    if item_id not in data["items"]:
        raise SystemExit("That item isn't in the show.")
    src = item_dir(s, data, item_id)
    dst = os.path.join(s, "removed", f"{int(time.time())} {os.path.basename(src)}")
    if os.path.exists(src):
        shutil.move(src, dst)
    for a in data["acts"]:
        if item_id in a["items"]:
            a["items"].remove(item_id)
    data["items"].pop(item_id)
    _tidy(data)
    _save(s, data)
    return status(s)


# ---------------------------------------------------------------- one cast, one world

def set_settings(s: str, x: dict) -> dict:
    data = _show(s)
    for k in SYNCED:
        if k in x:
            data[k] = x[k]
    _save(s, data)
    sync(s)
    return status(s)


def sync(s: str) -> dict:
    """Push the show's cast, Bible, look, aspect ratio and routing into every item. Cast images are copied in, so each
    item also stands on its own. Items the cast no longer has are taken out of the item's library (their files stay)."""
    from . import library
    data = _show(s)
    cast_dir = os.path.join(s, "cast")
    _, cast = library.load(cast_dir)
    cast_bible = library.bible(cast_dir)
    synced = 0
    act_of = {i: a for a in data["acts"] for i in a["items"]}
    for item_id in _order(data):
        d = item_dir(s, data, item_id)
        if data["items"][item_id]["kind"] == "intermission" or not os.path.isfile(os.path.join(d, "project.json")):
            continue
        p, lib = library.load(d)
        keep = [i for i in lib["items"] if not str(i.get("id", "")).startswith("show-")]
        costumes = (act_of.get(item_id) or {}).get("costumes") or {}
        for it in cast["items"]:
            cos = next((c for n, c in costumes.items() if n.strip().lower() == str(it.get("name", "")).strip().lower()), None)
            if cos and cos.get("file") and not _inside(cast_dir, os.path.join(cast_dir, cos["file"])):
                cos = {**cos, "file": None}                      # a costume image must live in the show's cast folder
            if cos:      # this act's costume stands in for the cast image
                it = {**it, "files": [cos["file"]] if cos.get("file") else it.get("files"),
                      "notes": " ".join(x for x in (it.get("notes"), f"Costume for this act: {cos['note']}" if cos.get("note") else "") if x)}
            files = []
            for f in it.get("files") or []:
                src = os.path.join(cast_dir, f)
                if not os.path.exists(src):
                    continue
                rel = f"assets/cast/{os.path.basename(f)}"
                os.makedirs(os.path.join(d, "assets", "cast"), exist_ok=True)
                dst = os.path.join(d, rel)
                if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
                    shutil.copy2(src, dst)
                files.append(rel)
            keep.append({**{k: v for k, v in it.items() if k != "files"}, "id": f"show-{it['id']}", "files": files, "from_show": True,
                         **({"costume": True} if cos else {})})
        lib["items"] = keep
        library.save_library(d, p, lib)
        p = _read(os.path.join(d, "project.json"), {})
        if not (p.get("bible_own")):
            p["bible"] = cast_bible
        for k in SYNCED:
            if k in data and not p.get(f"{k}_own"):
                p[k] = data[k]
        _write(os.path.join(d, "project.json"), p)
        synced += 1
    return {"synced": synced}


# ---------------------------------------------------------------- status and export

def _cost(d: str) -> dict:
    jobs = (_read(os.path.join(d, "jobs.json"), {"jobs": []}) or {}).get("jobs", [])
    usd = sum(float(j["cost"]) for j in jobs if j.get("cost") and (j.get("cost_unit") or "usd") != "credits")
    credits = sum(float(j["cost"]) for j in jobs if j.get("cost") and j.get("cost_unit") == "credits")
    return {"usd": round(usd, 2), "kie_credits": round(credits)}


def _problems(meta: dict, p: dict, dlg: dict, has_audio: bool, analysed: bool, directed: bool, last: bool) -> list[str]:
    """Plain-language things that would stop or spoil the export of this item (shown on the show screen)."""
    out = []
    if not p:
        return ["Its project file is missing. Restore the folder or remove the item."]
    if meta["kind"] == "scene":
        if not dlg.get("lines"):
            out.append("No dialogue written yet.")
        elif not has_audio or not dlg.get("timings"):
            out.append("The dialogue hasn't been voiced yet.")
        elif [(t.get("character"), t.get("text")) for t in dlg["timings"]] != [(x["character"], x["text"]) for x in dlg["lines"]]:
            out.append("The dialogue changed since it was voiced. Voice it again so the track matches.")
    elif p.get("song_pending"):
        out.append("No song attached yet. Use Attach song.")
    elif not has_audio:
        out.append("The song file is missing.")
    if has_audio and not analysed:
        out.append("Not analysed yet.")
    elif analysed and not directed:
        out.append("No shot plan yet.")
    if meta.get("transition") == "flow" and last:
        out.append("It flows into nothing: it is the last item.")
    return out


def status(s: str) -> dict:
    from .library import chosen_take, shot_state
    data = _show(s)
    acts = []
    total = 0.0
    for ai, a in enumerate(data["acts"]):
        items = []
        for item_id in a["items"]:
            meta = data["items"].get(item_id)
            if not meta:
                continue
            try:
                d = item_dir(s, data, item_id)
            except SystemExit as e:
                items.append({"id": item_id, **meta, "path": "", "state": "broken", "duration": 0, "shots": 0, "rendered": 0, "analysed": False,
                              "cost": {"usd": 0, "kie_credits": 0}, "lines": 0, "has_audio": False, "problems": [str(e)],
                              "song_pending": False})
                continue
            p = _read(os.path.join(d, "project.json"), {}) or {}
            if meta["kind"] == "intermission":
                total += float(meta.get("seconds") or 0)
                items.append({"id": item_id, **meta, "path": d, "state": "intermission", "duration": float(meta.get("seconds") or 0), "shots": 0,
                              "rendered": 0, "analysed": False, "cost": {"usd": 0, "kie_credits": 0}, "lines": 0, "has_audio": True,
                              "problems": [] if p else ["Its project file is missing. Restore the folder or remove the item."], "song_pending": False})
                continue
            sm = _read(os.path.join(d, "songmap.json"), {}) or {}
            plan = _read(os.path.join(d, "directed.json")) or _read(os.path.join(d, "production.json")) or {}
            plan_name = "directed" if os.path.exists(os.path.join(d, "directed.json")) else "production"
            shots = [x for sc in plan.get("scenes", []) for x in sc.get("shots", [])]
            jobs = (_read(os.path.join(d, "jobs.json"), {"jobs": []}) or {}).get("jobs", [])
            st = shot_state(d) if os.path.exists(os.path.join(d, "project.json")) else {}
            rendered = sum(1 for x in shots if chosen_take(d, x["id"], plan_name, jobs, st))
            dur = float(sm.get("duration") or 0)
            total += dur
            dlg = _read(os.path.join(d, "dialogue.json"), {}) or {}
            has_audio = bool(p.get("song")) and os.path.exists(os.path.join(d, p["song"]))
            problems = _problems(meta, p, dlg, has_audio, bool(sm), bool(shots), a["items"][-1] == item_id and ai == len(data["acts"]) - 1)
            items.append({"id": item_id, **meta, "path": d, "state": p.get("state", "new"), "duration": round(dur, 1),
                          "shots": len(shots), "rendered": rendered, "analysed": bool(sm), "cost": _cost(d),
                          "lines": len(dlg.get("lines") or []), "has_audio": has_audio, "problems": problems,
                          "song_pending": bool(p.get("song_pending"))})
        acts.append({"index": ai, "name": a["name"], "items": items, "costumes": a.get("costumes") or {}})
    from .budget import spent as _spent
    from .show_finish import budget_summary
    every = [i for a in acts for i in a["items"] if i["kind"] != "intermission" and i["path"]]
    usd = sum(_spent(i["path"])["total_usd"] for i in every)
    budget = budget_summary(data.get("budget_usd"), usd, sum(i["rendered"] for i in every), sum(max(0, i["shots"] - i["rendered"]) for i in every))
    cast = _read(os.path.join(s, "cast", "project.json"), {}) or {}
    chars = [i["name"] for i in ((cast.get("library") or {}).get("items") or []) if i.get("kind") == "character"]
    return {"dir": s, "title": data["title"], "acts": acts, "duration": round(total, 1), "voices": data["voices"],
            "characters": chars, "look": data.get("look"), "aspect_ratio": data.get("aspect_ratio"),
            "routing": data.get("routing"), "cast_dir": os.path.join(s, "cast"), "budget": budget}


def export(s: str, preset: str = "youtube", act: int | None = None, subtitles: bool = True, chapters: bool = True) -> dict:
    """The whole show (or one act) as one film: each item is exported, then joined with its transitions. Next to the film come
    subtitles (the spoken lines and the lyrics, also embedded) and chapters (one per number, scene or intermission)."""
    from . import show_finish as F
    from .export import FPS, PRESETS, build, ffmpeg
    data = _show(s)
    ids = data["acts"][act]["items"] if act is not None else _order(data)
    ids = [i for i in ids if i in data["items"]]
    if not ids:
        raise SystemExit("Add numbers or scenes to the show first.")
    blocked = []
    for item_id in ids:
        try:
            d = item_dir(s, data, item_id)
        except SystemExit as e:
            blocked.append(str(e))
            continue
        p = _read(os.path.join(d, "project.json"), {}) or {}
        kind, title = data["items"][item_id]["kind"], data["items"][item_id]["title"]
        if not p:
            blocked.append(f"{title}: its project file is missing.")
        elif kind == "intermission":
            continue
        elif not (p.get("song") and os.path.exists(os.path.join(d, p["song"]))):
            blocked.append(f"{title}: " + ("voice the dialogue first." if kind == "scene" else
                                           "attach its song first." if p.get("song_pending") else "the song file is missing."))
    if blocked:
        raise SystemExit("The show can't be exported yet. " + " ".join(blocked))
    parts, cues, entries, at = [], [], [], 0.0
    work = os.path.join(s, "exports", ".work")
    os.makedirs(work, exist_ok=True)
    act_of = {i: a["name"] for a in data["acts"] for i in a["items"]}
    first_in_act = {a["items"][0] for a in data["acts"] if a["items"]}
    pre = PRESETS[preset]
    for k, item_id in enumerate(ids):
        d = item_dir(s, data, item_id)
        meta = data["items"][item_id]
        emit(event="progress", stage=f"exporting {meta['title']}", progress=round(k / (len(ids) + 1), 3))
        try:
            if meta["kind"] == "intermission":
                path = F.intermission_clip(os.path.join(work, f"{item_id}.mp4"), meta["title"], meta.get("subtitle", ""), meta.get("seconds", 8), pre["w"], pre["h"], FPS)
            else:
                path = build(d, preset)["path"]
        except SystemExit as e:
            raise SystemExit(f"{meta['title']}: {e}")
        amb = meta.get("ambience")
        if amb and amb.get("file") and _inside(d, os.path.join(d, amb["file"])) and os.path.exists(os.path.join(d, amb["file"])):
            path = F.mix_ambience(path, os.path.join(d, amb["file"]), float(amb.get("volume_db", -18)), os.path.join(work, f"{item_id}-amb.mp4"), _duration(path))
        dur = _duration(path)
        title = meta["title"] if item_id not in first_in_act or len(data["acts"]) < 2 else f"{act_of[item_id]} \u00b7 {meta['title']}"
        entries.append((at, title))
        cues += [(at + a, at + b, text) for a, b, text in F.item_cues(d, meta["kind"])]
        at += dur
        parts.append((item_id, path))
    emit(event="progress", stage="joining the show", progress=round(len(ids) / (len(ids) + 1), 3))
    fade = 0.6
    w, h, fps = _video_format(parts[0][1])      # every item is brought to the first item's size and frame rate
    inputs, chains, labels = [], [], []
    for n, (item_id, path) in enumerate(parts):
        inputs += ["-i", path]
        dur = _duration(path)
        black_out = data["items"][item_id].get("transition") == "black" and n < len(parts) - 1
        black_in = n > 0 and data["items"][parts[n - 1][0]].get("transition") == "black"
        v = (f"[{n}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
             f"fps={fps},settb=AVTB,setpts=PTS-STARTPTS")
        a = f"[{n}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS"
        if black_in:
            v += f",fade=t=in:st=0:d={fade}"
            a += f",afade=t=in:st=0:d={fade}"
        if black_out:
            v += f",fade=t=out:st={max(0.0, dur - fade):.3f}:d={fade}"
            a += f",afade=t=out:st={max(0.0, dur - fade):.3f}:d={fade}"
        chains += [v + f"[v{n}]", a + f"[a{n}]"]
        labels.append(f"[v{n}][a{n}]")
    graph = ";".join(chains) + ";" + "".join(labels) + f"concat=n={len(parts)}:v=1:a=1[v][a]"
    name = _slug(data["title"] + (f" - {data['acts'][act]['name']}" if act is not None else ""))
    out = os.path.join(s, "exports", f"{name} {time.strftime('%Y-%m-%d %H%M')}.mp4")
    cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k",
           "-movflags", "+faststart", out]
    r = subprocess.run(cmd, capture_output=True, text=True, creationflags=0x08000000 if sys.platform == "win32" else 0)
    if r.returncode or not os.path.exists(out):
        raise SystemExit("Joining the show failed: " + (r.stderr or "")[-300:])
    total = _duration(out)
    extras = F.add_subtitles_and_chapters(out, entries, cues, total, subtitles, chapters) if (subtitles or chapters) else {}
    shutil.rmtree(work, ignore_errors=True)
    return {"path": out, "items": len(parts), "duration": round(total, 1), **extras}


def _video_format(path: str) -> tuple[int, int, str]:
    from .export import ffmpeg
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", path], capture_output=True, text=True,
                       creationflags=0x08000000 if sys.platform == "win32" else 0)
    m = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})", r.stderr or "")
    f = re.search(r"([\d.]+) fps", r.stderr or "")
    w, h = (int(m.group(1)), int(m.group(2))) if m else (1920, 1080)
    return w - w % 2, h - h % 2, f.group(1) if f else "30"


def _duration(path: str) -> float:
    from .export import ffmpeg
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", path], capture_output=True, text=True,
                       creationflags=0x08000000 if sys.platform == "win32" else 0)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr or "")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-show")
    ap.add_argument("action", choices=["create", "status", "add_number", "add_existing", "add_scene", "move", "set_act", "add_act",
                                       "rename", "transition", "remove", "remove_act", "settings", "sync", "export", "attach_song", "set_costume",
                                       "preview_script", "import_script", "add_intermission", "set_card", "set_ambience", "set_budget"])
    ap.add_argument("target")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    s = a.target
    try:
        if a.action == "create":
            res = create(s, x["title"], x.get("aspect_ratio", "16:9"))
        elif a.action == "status":
            res = status(s)
        elif a.action == "add_number":
            res = add_number(s, x["song"], x["title"], x.get("lyrics"), x.get("act"))
        elif a.action == "add_existing":
            res = add_existing(s, x["project"], x.get("act"))
        elif a.action == "add_scene":
            res = add_scene(s, x["title"], x.get("setting", ""), x.get("act"))
        elif a.action == "move":
            res = move(s, x["item"], int(x["delta"]))
        elif a.action == "set_act":
            res = set_act(s, x["item"], int(x["act"]))
        elif a.action == "add_act":
            res = add_act(s, x.get("name"))
        elif a.action == "rename":
            res = rename(s, x.get("item"), x["title"], x.get("act"))
        elif a.action == "transition":
            res = set_transition(s, x["item"], x["kind"])
        elif a.action == "remove":
            res = remove(s, x["item"])
        elif a.action == "add_intermission":
            res = add_intermission(s, x.get("title", "Intermission"), float(x.get("seconds", 8)), x.get("subtitle", ""), x.get("act"))
        elif a.action == "set_card":
            res = set_card(s, x["item"], x.get("title"), x.get("seconds"), x.get("subtitle"))
        elif a.action == "set_ambience":
            res = set_ambience(s, x["item"], x.get("file"), float(x.get("volume_db", -18)), bool(x.get("clear")))
        elif a.action == "set_budget":
            res = set_budget(s, x.get("usd"))
        elif a.action == "attach_song":
            res = attach_song(s, x["item"], x["song"])
        elif a.action == "set_costume":
            res = set_costume(s, int(x["act"]), x["character"], x.get("image"), x.get("note", ""), bool(x.get("clear")))
        elif a.action == "preview_script":
            from . import show_script
            res = show_script.preview(x["file"], x.get("songs_dir"), bool(x.get("one_song")))
        elif a.action == "import_script":
            from . import show_script
            res = show_script.import_script(s, x["file"], x.get("songs_dir"), bool(x.get("one_song")))
        elif a.action == "remove_act":
            res = remove_act(s, int(x["act"]))
        elif a.action == "settings":
            res = set_settings(s, x)
        elif a.action == "sync":
            res = {**sync(s), **status(s)}
        else:
            res = export(s, x.get("preset", "youtube"), x.get("act"), x.get("subtitles", True) is not False, x.get("chapters", True) is not False)
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
