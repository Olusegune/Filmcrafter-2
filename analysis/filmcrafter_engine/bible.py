"""The Production Bible, Cast and World of a film: the one source of truth the rest of the film is made from.

  <Film>/bible/bible.json      rules, philosophy, style profile, characters (with states, wardrobe, pictures), environments (with spatial notes), props
  <Film>/bible/history/        a copy of the Bible before each change (the newest 30)
  <Film>/cast/<id>/            a character's pictures
  <Film>/world/<id>/           an environment's pictures
  <Film>/props/<id>/           a prop's pictures

The Bible is seeded from the story (speaking characters and places) and then belongs to the person: seeding only adds, nothing is ever deleted
(removing an entry moves it to the history), and the pictures you bring are copied in untouched.

  python -m filmcrafter_engine.bible <action> <film_dir> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time

from .safe import check_id, file_part

SCHEMA = 1
KINDS = ("character", "environment", "prop")
FOLDER = {"character": "cast", "environment": "world", "prop": "props"}
LISTKEY = {"character": "characters", "environment": "environments", "prop": "props"}
STYLE_LANES = ("photoreal cinematic", "stylized 3D", "graphic 3D", "2D animation", "painterly animation", "anime-inspired", "graphic comic-inspired animation",
               "stop motion", "clay", "miniature", "mixed media", "experimental animation")
MEDIA_KINDS = ("master", "front", "three-quarter", "side", "back", "expression", "pose", "wardrobe", "reference", "other")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
MAX_IMAGE_BYTES = 25 * 1024 * 1024
KEEP_HISTORY = 30

RULE_FIELDS = ("world", "tone", "rules", "avoid")
PHILOSOPHY_FIELDS = ("visual", "cinematography", "lighting", "acting", "colour", "continuity")
CHARACTER_FIELDS = ("name", "role", "age", "physical", "relationships", "arc", "voice", "notes")
SPATIAL_FIELDS = ("entrances", "exits", "doors", "windows", "landmarks", "furniture", "blocking", "camera_zones", "lighting", "day_night")
ENV_FIELDS = ("name", "description", "notes")
PROP_FIELDS = ("name", "notes")
LIMIT = 4000


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
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _text(v, limit: int = LIMIT) -> str:
    return str(v if v is not None else "").replace("\x00", "").strip()[:limit]


def _empty() -> dict:
    return {"schema": SCHEMA, "rev": 0, "updated": 0,
            "rules": {k: "" for k in RULE_FIELDS}, "philosophy": {k: "" for k in PHILOSOPHY_FIELDS},
            "style": {"lane": "", "notes": "", "traits": "", "references": []},
            "characters": [], "environments": [], "props": []}


def _path(d: str) -> str:
    return os.path.join(d, "bible", "bible.json")


def _film(d: str) -> None:
    m = _read(os.path.join(d, "film.json"))
    if not isinstance(m, dict) or "story" not in m:
        raise SystemExit("That isn't a FilmCrafter film.")


def load(d: str) -> dict:
    _film(d)
    b = _read(_path(d))
    base = _empty()
    if not isinstance(b, dict):
        return base
    for k, v in base.items():
        b.setdefault(k, v)
    return b


def _save(d: str, b: dict, before: dict | None) -> dict:
    """Write the Bible, keeping a copy of what it was."""
    if before is not None and before.get("rev", 0) > 0:
        hist = os.path.join(d, "bible", "history")
        os.makedirs(hist, exist_ok=True)
        _write(os.path.join(hist, f"rev{before['rev']:04d}.json"), before)
        for old in sorted(os.listdir(hist))[:-KEEP_HISTORY]:
            try:
                os.remove(os.path.join(hist, old))
            except OSError:
                pass
    b["rev"] = int(b.get("rev", 0)) + 1
    b["updated"] = int(time.time())
    _write(_path(d), b)
    return b


def _id(kind: str, name: str, taken: set[str]) -> str:
    stem = {"character": "c", "environment": "e", "prop": "p"}[kind] + "_" + file_part(re.sub(r"\s+", "-", name.lower()), 40).strip("-_.") or "x"
    out, n = stem, 2
    while out in taken:
        out, n = f"{stem}-{n}", n + 1
    return out


def _find(b: dict, kind: str, id_: str) -> dict:
    for it in b[LISTKEY[kind]]:
        if it["id"] == id_:
            return it
    raise SystemExit(f"That {kind} isn't in the Bible.")


# ---------------------------------------------------------------- seeding from the story

def seed(d: str) -> dict:
    """Add the story's speaking characters and places that the Bible does not have yet. Existing entries are never changed or removed."""
    from . import story
    m = story._manifest(d)
    st = story.status(d, m["story"]["current"])
    found = st["found"]
    b = load(d)
    before = json.loads(json.dumps(b))
    names = {c["name"].lower(): c for c in b["characters"]}
    envs = {e["name"].lower(): e for e in b["environments"]}
    added = {"characters": 0, "environments": 0}
    taken_c = {c["id"] for c in b["characters"]}
    taken_e = {e["id"] for e in b["environments"]}
    for c in found.get("characters", []):
        title = c["name"].title()
        if title.lower() in names or c["name"].lower() in names:
            names.get(title.lower(), names.get(c["name"].lower()))["scenes"] = c.get("scenes", [])
            continue
        cid = _id("character", title, taken_c)
        taken_c.add(cid)
        entry = {"id": cid, "name": title, "role": "", "age": "", "physical": "", "relationships": "", "arc": "", "voice": "", "notes": "",
                 "wardrobe": [], "states": [{"id": "s1", "label": "Default", "notes": ""}], "media": [], "scenes": c.get("scenes", []), "source": "story"}
        b["characters"].append(entry)
        names[title.lower()] = entry
        added["characters"] += 1
    for p in found.get("locations", []):
        title = p["name"].title()
        if title.lower() in envs:
            envs[title.lower()]["scenes"] = p.get("scenes", [])
            continue
        eid = _id("environment", title, taken_e)
        taken_e.add(eid)
        times = sorted({s.get("time", "") for s in found.get("scenes", []) if s.get("location") == p["name"] and s.get("time")})
        entry = {"id": eid, "name": title, "description": "", "notes": "", "spatial": {k: "" for k in SPATIAL_FIELDS},
                 "states": [{"id": "s1", "label": (times[0].title() if times else "Default"), "notes": ""}], "media": [], "scenes": p.get("scenes", []), "source": "story"}
        b["environments"].append(entry)
        envs[title.lower()] = entry
        added["environments"] += 1
    if added["characters"] or added["environments"] or b != before:
        b = _save(d, b, before)
    return {**view(d), "added": added}


# ---------------------------------------------------------------- editing

def update_rules(d: str, data: dict) -> dict:
    b = load(d)
    before = json.loads(json.dumps(b))
    for sec, fields in (("rules", RULE_FIELDS), ("philosophy", PHILOSOPHY_FIELDS)):
        for k, v in (data.get(sec) or {}).items():
            if k in fields:
                b[sec][k] = _text(v)
    st = data.get("style") or {}
    if "lane" in st:
        lane = _text(st["lane"], 80)
        if lane and lane not in STYLE_LANES:
            raise SystemExit("Choose one of the listed visual styles.")
        b["style"]["lane"] = lane
    for k in ("notes", "traits"):
        if k in st:
            b["style"][k] = _text(st[k])
    if "references" in st:
        b["style"]["references"] = [_text(r, 300) for r in (st["references"] or [])][:20]
    if b != before:
        _save(d, b, before)
    return view(d)


def upsert(d: str, kind: str, item: dict) -> dict:
    """Make or change a character, environment or prop. Only the known fields are taken, each trimmed and limited."""
    if kind not in KINDS:
        raise SystemExit("Choose character, environment or prop.")
    b = load(d)
    before = json.loads(json.dumps(b))
    lst = b[LISTKEY[kind]]
    fields = {"character": CHARACTER_FIELDS, "environment": ENV_FIELDS, "prop": PROP_FIELDS}[kind]
    iid = item.get("id")
    if iid:
        cur = _find(b, kind, check_id(iid, kind))
    else:
        name = _text(item.get("name"), 80)
        if not name:
            raise SystemExit("Give it a name.")
        cur = {"id": _id(kind, name, {x["id"] for x in lst}), "media": [], "scenes": [], "source": "manual"}
        if kind == "character":
            cur.update({k: "" for k in CHARACTER_FIELDS} | {"wardrobe": [], "states": [{"id": "s1", "label": "Default", "notes": ""}]})
        elif kind == "environment":
            cur.update({k: "" for k in ENV_FIELDS} | {"spatial": {k: "" for k in SPATIAL_FIELDS}, "states": [{"id": "s1", "label": "Default", "notes": ""}]})
        else:
            cur.update({k: "" for k in PROP_FIELDS} | {"states": [{"id": "s1", "label": "Default", "notes": ""}]})
        lst.append(cur)
    for k in fields:
        if k in item:
            cur[k] = _text(item[k], 80 if k == "name" else LIMIT)
    if kind == "environment" and isinstance(item.get("spatial"), dict):
        for k in SPATIAL_FIELDS:
            if k in item["spatial"]:
                cur["spatial"][k] = _text(item["spatial"][k])
    if not cur.get("name"):
        raise SystemExit("Give it a name.")
    _save(d, b, before)
    return {**view(d), "id": cur["id"]}


def remove(d: str, kind: str, id_: str) -> dict:
    """Take an entry out of the Bible. The Bible as it was is kept in the history, and the entry's pictures stay on disk."""
    if kind not in KINDS:
        raise SystemExit("Choose character, environment or prop.")
    b = load(d)
    before = json.loads(json.dumps(b))
    it = _find(b, kind, check_id(id_, kind))
    b[LISTKEY[kind]] = [x for x in b[LISTKEY[kind]] if x is not it]
    _save(d, b, before)
    return view(d)


def _state_id(states: list[dict]) -> str:
    n = 1
    ids = {s["id"] for s in states}
    while f"s{n}" in ids:
        n += 1
    return f"s{n}"


def add_state(d: str, kind: str, id_: str, label: str, notes: str = "", wardrobe: str = "", age: str = "") -> dict:
    """A related state of the same thing: the character at another age or in another outfit, the place by night, the prop broken. It stays the same canonical entry."""
    if kind not in KINDS:
        raise SystemExit("Choose character, environment or prop.")
    b = load(d)
    before = json.loads(json.dumps(b))
    it = _find(b, kind, check_id(id_, kind))
    label = _text(label, 80)
    if not label:
        raise SystemExit("Name the state, for example Age 28 or Night.")
    if any(s["label"].lower() == label.lower() for s in it["states"]):
        raise SystemExit("There is already a state with that name.")
    st = {"id": _state_id(it["states"]), "label": label, "notes": _text(notes)}
    if kind == "character":
        st["wardrobe"] = _text(wardrobe, 200)
        st["age"] = _text(age, 40)
    it["states"].append(st)
    _save(d, b, before)
    return {**view(d), "state": st["id"]}


def remove_state(d: str, kind: str, id_: str, state: str) -> dict:
    b = load(d)
    before = json.loads(json.dumps(b))
    it = _find(b, kind, check_id(id_, kind))
    if len(it["states"]) <= 1:
        raise SystemExit("Keep at least one state.")
    it["states"] = [s for s in it["states"] if s["id"] != state]
    _save(d, b, before)
    return view(d)


def add_wardrobe(d: str, id_: str, name: str, notes: str = "") -> dict:
    b = load(d)
    before = json.loads(json.dumps(b))
    ch = _find(b, "character", check_id(id_, "character"))
    name = _text(name, 80)
    if not name:
        raise SystemExit("Name the outfit.")
    n = 1
    ids = {w["id"] for w in ch["wardrobe"]}
    while f"w{n}" in ids:
        n += 1
    ch["wardrobe"].append({"id": f"w{n}", "name": name, "notes": _text(notes)})
    _save(d, b, before)
    return view(d)


def add_media(d: str, kind: str, id_: str, file: str, label: str = "reference", media_kind: str = "reference") -> dict:
    """Bring a picture for a character, place or prop. It is copied into the film untouched; the original stays where it is."""
    if kind not in KINDS:
        raise SystemExit("Choose character, environment or prop.")
    b = load(d)
    before = json.loads(json.dumps(b))
    it = _find(b, kind, check_id(id_, kind))
    src = os.path.abspath(str(file or ""))
    if not src.lower().endswith(IMAGE_EXT) or not os.path.isfile(src):
        raise SystemExit("Choose a PNG, JPG or WebP picture.")
    if os.path.getsize(src) > MAX_IMAGE_BYTES:
        raise SystemExit("That picture is larger than 25 MB.")
    media_kind = media_kind if media_kind in MEDIA_KINDS else "reference"
    folder = os.path.join(d, FOLDER[kind], it["id"])
    os.makedirs(folder, exist_ok=True)
    base, ext = os.path.splitext(os.path.basename(src))
    name = f"{file_part(base, 50)}{ext.lower()}"
    out, n = os.path.join(folder, name), 2
    while os.path.exists(out):
        out = os.path.join(folder, f"{file_part(base, 50)}-{n}{ext.lower()}")
        n += 1
    shutil.copyfile(src, out)
    rel = os.path.relpath(out, d).replace(os.sep, "/")
    it["media"].append({"path": rel, "kind": media_kind, "label": _text(label, 80) or media_kind})
    _save(d, b, before)
    return view(d)


def remove_media(d: str, kind: str, id_: str, path: str) -> dict:
    """Take a picture off the entry. The file stays in the film folder."""
    b = load(d)
    before = json.loads(json.dumps(b))
    it = _find(b, kind, check_id(id_, kind))
    it["media"] = [m for m in it["media"] if m["path"] != path]
    _save(d, b, before)
    return view(d)


# ---------------------------------------------------------------- reading

def view(d: str) -> dict:
    b = load(d)
    need = []
    if not b["style"]["lane"]:
        need.append("Choose a visual style.")
    if not b["characters"]:
        need.append("Add the characters.")
    if not b["environments"]:
        need.append("Add the places.")
    pics = sum(1 for c in b["characters"] if c["media"])
    return {**b, "lanes": list(STYLE_LANES), "media_kinds": list(MEDIA_KINDS), "need": need,
            "counts": {"characters": len(b["characters"]), "environments": len(b["environments"]), "props": len(b["props"]), "characters_with_pictures": pics}}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-bible")
    ap.add_argument("action", choices=["get", "seed", "update_rules", "upsert", "remove", "add_state", "remove_state", "add_wardrobe", "add_media", "remove_media"])
    ap.add_argument("target")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    d = a.target
    try:
        if a.action == "get":
            res = view(d)
        elif a.action == "seed":
            res = seed(d)
        elif a.action == "update_rules":
            res = update_rules(d, x)
        elif a.action == "upsert":
            res = upsert(d, x.get("kind", ""), x.get("item") or {})
        elif a.action == "remove":
            res = remove(d, x.get("kind", ""), x.get("id", ""))
        elif a.action == "add_state":
            res = add_state(d, x.get("kind", ""), x.get("id", ""), x.get("label", ""), x.get("notes", ""), x.get("wardrobe", ""), x.get("age", ""))
        elif a.action == "remove_state":
            res = remove_state(d, x.get("kind", ""), x.get("id", ""), x.get("state", ""))
        elif a.action == "add_wardrobe":
            res = add_wardrobe(d, x.get("id", ""), x.get("name", ""), x.get("notes", ""))
        elif a.action == "add_media":
            res = add_media(d, x.get("kind", ""), x.get("id", ""), x.get("file", ""), x.get("label", "reference"), x.get("media_kind", "reference"))
        else:
            res = remove_media(d, x.get("kind", ""), x.get("id", ""), x.get("path", ""))
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
