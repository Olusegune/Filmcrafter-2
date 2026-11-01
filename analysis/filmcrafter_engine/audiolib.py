"""The film's sound and music libraries: sound effects (foley, ambience, weather, ...) and music, as reusable assets with stable ids.

  <Film>/audio/library.json            the asset records (written with safeio: atomic, locked, a damaged file is never turned into an empty one)
  <Film>/audio/sfx/<id>.<ext>          a sound effect's file
  <Film>/audio/music/<id>.<ext>        a music file
  <Film>/audio/_removed/               what was taken out of the library (files are moved here, never deleted)

Stage A of the creative-production expansion: organising, importing, previewing and describing audio. Nothing here calls a provider or costs anything. The same records are what
later stages (cues on the timeline, the sound director, generation) refer to by `id`; an asset's id never changes (not on rename, not on re-approval), and a generated asset will
carry its provider, model and prompt in `generation` (empty for an imported file).

An asset: {id, kind: sfx|music, name, description, category, file, original_name, sha1, bytes, seconds, source: imported|generated, tags[], places[], props[], characters[], scenes[],
shots[], genre, mood, tempo, generation{}, licence{source, note, commercial: yes|no|unknown}, approval: pending|approved|rejected, added, updated}

  python -m filmcrafter_engine.audiolib <list|import|update|approve|remove|restore> <film_dir> --data '{...}'
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid

from . import safeio

KINDS = ("sfx", "music")
CATEGORIES = {
    "sfx": ("foley", "ambience", "weather", "nature", "mechanical", "vehicles", "human", "creatures", "fantasy_scifi", "transitions", "custom"),
    "music": ("score", "theme", "cue", "suspense", "transition", "climax", "song", "credits", "custom"),
}
CATEGORY_NAMES = {"foley": "Foley", "ambience": "Environmental ambience", "weather": "Weather", "nature": "Nature", "mechanical": "Mechanical", "vehicles": "Vehicles", "human": "Human activity",
                  "creatures": "Creature sounds", "fantasy_scifi": "Fantasy and science fiction", "transitions": "Transitions", "custom": "Custom",
                  "score": "Background score", "theme": "Character or recurring theme", "cue": "Scene cue", "suspense": "Suspense", "transition": "Dramatic transition",
                  "climax": "Emotional climax", "song": "Song", "credits": "End-credit music"}
AUDIO_EXT = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac")
MAX_BYTES = 200 * 1024 * 1024
MAX_SECONDS = 60 * 60
APPROVALS = ("pending", "approved", "rejected")
COMMERCIAL = ("yes", "no", "unknown")
SOURCES = ("imported", "generated")
LIST_FIELDS = ("tags", "places", "props", "characters", "scenes", "shots")
TEXT_FIELDS = ("name", "description", "genre", "mood", "tempo")
KEEP_REMOVED = 500
ID = re.compile(r"^a-(sfx|music)-[0-9a-f]{8}$")
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


# ---------------------------------------------------------------- the file and its record

def _film(d: str) -> None:
    m = safeio.read_json(os.path.join(d, "film.json"), None)
    if not isinstance(m, dict) or "story" not in m:
        raise SystemExit("That isn't a FilmCrafter film.")


def _path(d: str) -> str:
    return os.path.join(d, "audio", "library.json")


def _empty() -> dict:
    return {"schema": 1, "assets": [], "removed": []}


def _ok(data) -> bool:
    return isinstance(data, dict) and isinstance(data.get("assets", []), list) and isinstance(data.get("removed", []), list)


def _normal(data: dict) -> dict:
    data.setdefault("schema", 1)
    data.setdefault("assets", [])
    data.setdefault("removed", [])
    return data


def load(d: str) -> dict:
    _film(d)
    return _normal(safeio.read_json(_path(d), _empty(), check=_ok))


def _text(v, limit: int = 2000) -> str:
    return str(v if v is not None else "").replace("\x00", "").strip()[:limit]


def _list(v, limit: int = 40) -> list[str]:
    if isinstance(v, str):
        v = re.split(r"[,\n]", v)
    out: list[str] = []
    for x in v or []:
        t = _text(x, 80)
        if t and t.lower() not in [o.lower() for o in out]:
            out.append(t)
    return out[:limit]


def _id(kind: str, taken: set[str]) -> str:
    while True:
        i = f"a-{kind}-{uuid.uuid4().hex[:8]}"
        if i not in taken:
            return i


def _find(data: dict, asset_id: str) -> dict:
    if not ID.match(str(asset_id or "")):
        raise SystemExit("That sound or music id is not valid.")
    for a in data["assets"]:
        if a["id"] == asset_id:
            return a
    raise SystemExit("That sound or music is not in this film's library.")


# ---------------------------------------------------------------- reading an audio file

def _ffmpeg() -> str:
    from .export import ffmpeg
    return ffmpeg()


def probe(path: str) -> dict:
    """Whether this is real audio FilmCrafter can use, and how long it is. Judged from the file's content, not its name. Reads only."""
    if not os.path.isfile(path):
        return {"ok": False, "why": "That file is not there."}
    if not path.lower().endswith(AUDIO_EXT):
        return {"ok": False, "why": "Use a WAV, MP3, M4A, FLAC, OGG or AAC file."}
    size = os.path.getsize(path)
    if size > MAX_BYTES:
        return {"ok": False, "why": "That audio file is larger than 200 MB."}
    if size < 100:
        return {"ok": False, "why": "That file is empty."}
    try:
        err = subprocess.run([_ffmpeg(), "-hide_banner", "-i", path], capture_output=True, text=True, creationflags=NO_WINDOW, timeout=60).stderr
    except (OSError, subprocess.SubprocessError):
        return {"ok": False, "why": "FilmCrafter could not read that file."}
    if not re.search(r"Stream #\d+:\d+.*: Audio:", err):
        return {"ok": False, "why": "That file has no sound FilmCrafter can read."}
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    seconds = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    if seconds <= 0:
        return {"ok": False, "why": "That file has no length FilmCrafter can read."}
    if seconds > MAX_SECONDS:
        return {"ok": False, "why": "That audio is longer than an hour. Use shorter pieces."}
    return {"ok": True, "seconds": round(seconds, 2), "bytes": size}


def _sha1(path: str) -> str:
    h = hashlib.sha1(usedforsecurity=False)
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- actions

def list_assets(d: str, kind: str | None = None) -> dict:
    data = load(d)
    assets = [a for a in data["assets"] if not kind or a["kind"] == kind]
    for a in assets:
        a["exists"] = os.path.isfile(os.path.join(d, *a["file"].split("/")))
    return {"assets": assets, "removed": len(data["removed"]), "removed_items": [{"id": r["id"], "kind": r["kind"], "name": r["name"], "removed_at": r.get("removed_at", 0)} for r in data["removed"]], "categories": {k: [{"id": c, "name": CATEGORY_NAMES[c]} for c in v] for k, v in CATEGORIES.items()},
            "counts": {k: sum(1 for a in data["assets"] if a["kind"] == k) for k in KINDS}}


def add_file(d: str, kind: str, src: str, *, category: str | None = None, source: str = "imported", name: str | None = None, description: str = "", generation: dict | None = None,
             licence: dict | None = None, dedupe: bool = True, tags: list | None = None) -> dict:
    """Copy one audio file into the library as a new asset. Returns {"asset": ...} or {"skipped": why, "id": ...}. The source file is never moved or changed. The file is checked as audio first.
    `source` is imported or generated; a generated asset carries how it was made (provider, model, prompt, settings) in `generation`."""
    _film(d)
    if kind not in KINDS:
        raise SystemExit("Choose sound effects or music.")
    if source not in SOURCES:
        raise SystemExit("The source is imported or generated.")
    cat = category if category in CATEGORIES[kind] else "custom"
    src = os.path.abspath(str(src))
    info = probe(src)
    if not info["ok"]:
        return {"skipped": info["why"]}
    digest = _sha1(src)
    ext = os.path.splitext(src)[1].lower()
    folder = os.path.join(d, "audio", kind)
    os.makedirs(folder, exist_ok=True)
    holder: dict = {}

    def change(data):
        data = _normal(data)
        same = next((a for a in data["assets"] if a["kind"] == kind and a.get("sha1") == digest), None) if dedupe else None
        if same:
            holder["dup"] = same
            return data
        aid = _id(kind, {a["id"] for a in data["assets"]} | {a["id"] for a in data["removed"]})
        dest = os.path.join(folder, aid + ext)
        tmp = dest + f".{os.getpid()}.tmp"
        try:
            shutil.copyfile(src, tmp)
            os.replace(tmp, dest)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        title = (name or re.sub(r"[_]+", " ", os.path.splitext(os.path.basename(src))[0])).strip()[:80] or "Untitled"
        now = int(time.time())
        lic = {"source": "", "note": "", "commercial": "unknown", **(licence or {})}
        asset = {"id": aid, "kind": kind, "name": title, "description": _text(description), "category": cat, "file": f"audio/{kind}/{aid}{ext}", "original_name": os.path.basename(src)[:200],
                 "sha1": digest, "bytes": info["bytes"], "seconds": info["seconds"], "source": source, "tags": _list(tags or []), "places": [], "props": [], "characters": [],
                 "scenes": [], "shots": [], "genre": "", "mood": "", "tempo": "", "generation": generation or {}, "licence": lic, "approval": "pending", "added": now, "updated": now}
        data["assets"].append(asset)
        holder["asset"] = asset
        return data

    safeio.update_json(_path(d), change, _empty(), check=_ok)
    if "dup" in holder:
        return {"skipped": f"Already in the library as \u201c{holder['dup']['name']}\u201d.", "id": holder["dup"]["id"]}
    return {"asset": holder["asset"]}


def import_files(d: str, kind: str, files: list, category: str | None = None) -> dict:
    """Copy audio files into the film's library. The originals are never moved or changed. A file already in the library (same content, same kind) is not added twice."""
    _film(d)
    if kind not in KINDS:
        raise SystemExit("Choose sound effects or music.")
    if not isinstance(files, list) or not files:
        raise SystemExit("Choose at least one audio file.")
    added, skipped = [], []
    for f in files[:50]:
        r = add_file(d, kind, str(f), category=category)
        if "asset" in r:
            added.append(r["asset"]["id"])
        else:
            skipped.append({"file": os.path.basename(str(f)), "why": r["skipped"], **({"id": r["id"]} if "id" in r else {})})
    return {**list_assets(d), "added": added, "skipped": skipped}


def rights_report(d: str) -> dict:
    """Which sounds and music the film's plan uses whose commercial use is not known or not allowed, so nothing goes into a released film unnoticed. Free; changes nothing."""
    from . import audiocues as Q
    _film(d)
    lib = load(d)
    used = {c["asset_id"] for c in (Q.listing(d)["cues"]) if c.get("asset_id") and c.get("approval") != "rejected"}
    rows = []
    for a in lib["assets"]:
        if a["id"] not in used and not a.get("generation"):
            continue
        com = (a.get("licence") or {}).get("commercial", "unknown")
        if com != "yes":
            rows.append({"id": a["id"], "name": a["name"], "kind": a["kind"], "commercial": com, "in_plan": a["id"] in used, "source": a["source"],
                         "why": "Commercial use is not allowed." if com == "no" else "Commercial use is not known: confirm the rights before releasing the film."})
    return {"assets": rows, "blocking": [r for r in rows if r["in_plan"]], "ok": not any(r["in_plan"] for r in rows)}


def update(d: str, asset_id: str, data: dict) -> dict:
    """Describe and link an asset. Only the known fields are taken. The id, file and content never change."""
    _film(d)

    def change(lib):
        lib = _normal(lib)
        a = _find(lib, asset_id)
        for k in TEXT_FIELDS:
            if k in data:
                a[k] = _text(data[k], 80 if k == "name" else 2000)
        if not a["name"]:
            raise SystemExit("Give it a name.")
        if "category" in data:
            if data["category"] not in CATEGORIES[a["kind"]]:
                raise SystemExit("Choose one of the listed categories.")
            a["category"] = data["category"]
        for k in LIST_FIELDS:
            if k in data:
                a[k] = _list(data[k])
        if isinstance(data.get("licence"), dict):
            lic = data["licence"]
            cur = a.setdefault("licence", {"source": "", "note": "", "commercial": "unknown"})
            if "source" in lic:
                cur["source"] = _text(lic["source"], 300)
            if "note" in lic:
                cur["note"] = _text(lic["note"], 1000)
            if "commercial" in lic:
                if lic["commercial"] not in COMMERCIAL:
                    raise SystemExit("Commercial use is yes, no or not known.")
                cur["commercial"] = lic["commercial"]
        a["updated"] = int(time.time())
        return lib

    safeio.update_json(_path(d), change, _empty(), check=_ok)
    return list_assets(d)


def approve(d: str, asset_id: str, state: str) -> dict:
    """The person's decision about an asset: approved, rejected, or back to pending. Never done by anything else."""
    _film(d)
    if state not in APPROVALS:
        raise SystemExit("Choose approved, rejected or pending.")

    def change(lib):
        lib = _normal(lib)
        a = _find(lib, asset_id)
        a["approval"] = state
        a["updated"] = int(time.time())
        return lib

    safeio.update_json(_path(d), change, _empty(), check=_ok)
    return list_assets(d)


def remove(d: str, asset_id: str) -> dict:
    """Take an asset out of the library. Its file is moved to audio/_removed (not deleted) and the record is kept so it can be restored."""
    _film(d)
    moved: dict = {}

    def change(lib):
        lib = _normal(lib)
        a = _find(lib, asset_id)
        src = os.path.join(d, *a["file"].split("/"))
        if os.path.isfile(src):
            trash = os.path.join(d, "audio", "_removed")
            os.makedirs(trash, exist_ok=True)
            dest = os.path.join(trash, os.path.basename(src))
            n = 1
            while os.path.exists(dest):
                base, ext = os.path.splitext(os.path.basename(src))
                dest, n = os.path.join(trash, f"{base}-{n}{ext}"), n + 1
            shutil.move(src, dest)
            moved["to"] = dest
        lib["assets"] = [x for x in lib["assets"] if x["id"] != asset_id]
        lib["removed"].append({**a, "removed_at": int(time.time()), "removed_file": os.path.basename(moved.get("to", ""))})
        lib["removed"] = lib["removed"][-KEEP_REMOVED:]
        return lib

    safeio.update_json(_path(d), change, _empty(), check=_ok)
    return list_assets(d)


def restore(d: str, asset_id: str) -> dict:
    _film(d)

    def change(lib):
        lib = _normal(lib)
        rec = next((r for r in lib["removed"] if r["id"] == asset_id), None)
        if not rec:
            raise SystemExit("That sound or music was not removed.")
        if any(a["id"] == asset_id for a in lib["assets"]):
            raise SystemExit("It is already back in the library.")
        dest = os.path.join(d, *rec["file"].split("/"))
        held = os.path.join(d, "audio", "_removed", rec.get("removed_file") or "")
        if rec.get("removed_file") and os.path.isfile(held):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(held, dest)
        a = {k: v for k, v in rec.items() if k not in ("removed_at", "removed_file")}
        lib["assets"].append(a)
        lib["removed"] = [r for r in lib["removed"] if r["id"] != asset_id]
        return lib

    safeio.update_json(_path(d), change, _empty(), check=_ok)
    return list_assets(d)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="audiolib")
    ap.add_argument("action", choices=["list", "import", "update", "approve", "remove", "restore"])
    ap.add_argument("film")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    try:
        x = json.loads(a.data or "{}")
        d = os.path.abspath(a.film)
        if a.action == "list":
            _film(d)
            res = list_assets(d, x.get("kind"))
        elif a.action == "import":
            res = import_files(d, x.get("kind", ""), x.get("files") or [], x.get("category"))
        elif a.action == "update":
            res = update(d, x.get("id", ""), x)
        elif a.action == "approve":
            res = approve(d, x.get("id", ""), x.get("state", ""))
        elif a.action == "remove":
            res = remove(d, x.get("id", ""))
        else:
            res = restore(d, x.get("id", ""))
        emit(event="result", data=res)
        return 0
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=__import__("filmcrafter_engine.errtext", fromlist=["plain"]).plain(e))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
