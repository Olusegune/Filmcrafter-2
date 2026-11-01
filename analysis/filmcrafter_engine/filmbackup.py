"""Backups of a film's own records (not its pictures, video or audio, and not the render project, which has its own snapshots in packer.py).

What is kept: every small record of the film folder: film.json and the .filmcrafter document, the script versions, the Bible (cast, world, history), shots, the voice records
(voice.json, cast.json, the voice ledger), recording notes, and any other .json / .md file the film keeps, found by walking the folder (so records added in later versions are covered
without a list to maintain). Left out: media, caches, previews, the `render` project, other projects nested inside the film, and `backups` itself. Files over 8 MB are left out.

  <film>/backups/film-<time>.zip   a snapshot: `backup.json` (what is inside, with a SHA-256 for each file, and why it was made) plus the files

A snapshot is skipped when nothing changed since the last one. The newest 30 are kept. A snapshot is checked (readable zip, every file matches its SHA-256) before it is restored;
a restore first takes a snapshot of the current state (so it can be undone), writes each file with one atomic replace, never deletes a file that is not in the snapshot, and never
puts back the voice ledger (it records what was spent: going back in time must not hide spending). Nothing here touches the network or the media.

  python -m filmcrafter_engine.filmbackup make|list|verify|restore <film_dir> [name]
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import zipfile

from . import safeio

KEEP = 30
MAX_FILE = 8 * 1024 * 1024
SKIP_DIRS = {"cache", "thumbnails", "__pycache__", "backups", "render", "_previews", "_generated", "_removed", "_takes", "node_modules"}
KINDS = (".json", ".md", ".filmcrafter")
_TEMP = re.compile(r"\.tmp(\.|$)")
NEVER_RESTORED = {"voice/ledger.json"}           # the record of what was spent


def _looks_like_project(path: str) -> bool:
    from .packer import looks_like_project
    return looks_like_project(path)


def _files(d: str) -> list[str]:
    """Relative paths (forward slashes) of the film's records."""
    out: list[str] = []
    for root, dirs, files in os.walk(d):
        keep = []
        for x in dirs:
            if x in SKIP_DIRS or x.endswith(".corrupt") or (root != d and _looks_like_project(os.path.join(root, x))):
                continue
            keep.append(x)
        dirs[:] = keep
        for f in files:
            low = f.lower()
            if not low.endswith(KINDS) or _TEMP.search(low) or low.endswith(".lock") or ".corrupt-" in low:
                continue
            p = os.path.join(root, f)
            try:
                if os.path.getsize(p) > MAX_FILE:
                    continue
            except OSError:
                continue
            out.append(os.path.relpath(p, d).replace(os.sep, "/"))
    return sorted(out)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _read(d: str, rel: str) -> bytes | None:
    try:
        with open(os.path.join(d, *rel.split("/")), "rb") as fh:
            return fh.read()
    except OSError:
        return None


def _root(d: str) -> str:
    return os.path.join(d, "backups")


def _is_film(d: str) -> bool:
    return os.path.isfile(os.path.join(d, "film.json"))


def list_backups(d: str) -> list[dict]:
    root = _root(d)
    out = []
    for f in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        if f.startswith("film-") and f.endswith(".zip"):
            try:
                with zipfile.ZipFile(os.path.join(root, f)) as z:
                    meta = json.loads(z.read("backup.json"))
                out.append({"name": f, "at": meta.get("at", 0), "reason": meta.get("reason", ""), "files": len(meta.get("files", {})), "digest": meta.get("digest", ""), "_ns": meta.get("at_ns", 0)})
            except (OSError, KeyError, ValueError, zipfile.BadZipFile):
                out.append({"name": f, "at": 0, "reason": "", "files": 0, "digest": "", "damaged": True, "_ns": 0})
    out.sort(key=lambda b: (b["_ns"], b["name"]), reverse=True)
    for b in out:
        b.pop("_ns", None)
    return out


def make(d: str, reason: str = "auto") -> dict:
    """Take a snapshot unless nothing changed since the last one."""
    if not _is_film(d):
        raise SystemExit("That isn't a FilmCrafter film.")
    inventory: dict[str, tuple[bytes, str]] = {}
    for rel in _files(d):
        raw = _read(d, rel)
        if raw is not None:
            inventory[rel] = (raw, _sha(raw))
    digest = _sha("\n".join(f"{k}:{v[1]}" for k, v in sorted(inventory.items())).encode())
    prev = [b for b in list_backups(d) if not b.get("damaged")]
    if prev and prev[0]["digest"] == digest:
        return {"made": False, "latest": prev[0]["name"], "count": len(prev)}
    root = _root(d)
    os.makedirs(root, exist_ok=True)
    now = time.time()
    stem = "film-" + time.strftime("%Y%m%d-%H%M%S", time.localtime(now)) + f"-{int(now * 1000) % 1000:03d}"
    name, n = stem + ".zip", 1
    while os.path.exists(os.path.join(root, name)):
        name, n = f"{stem}-{n}.zip", n + 1
    meta = {"format": 1, "at": int(now), "at_ns": time.time_ns(), "reason": reason, "digest": digest, "files": {k: {"sha256": v[1], "bytes": len(v[0])} for k, v in inventory.items()}}
    tmp = os.path.join(root, name + ".part")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("backup.json", json.dumps(meta))
            for rel, (raw, _h) in inventory.items():
                z.writestr("files/" + rel, raw)
        os.replace(tmp, os.path.join(root, name))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    for old in list_backups(d)[KEEP:]:
        try:
            os.remove(os.path.join(root, old["name"]))
        except OSError:
            pass
    return {"made": True, "latest": name, "count": min(len(prev) + 1, KEEP), "files": len(inventory)}


def verify(d: str, name: str) -> dict:
    """Is the snapshot whole? Returns its files, or raises with plain words."""
    path = os.path.join(_root(d), os.path.basename(name))
    if not os.path.isfile(path):
        raise SystemExit("That backup no longer exists.")
    try:
        with zipfile.ZipFile(path) as z:
            meta = json.loads(z.read("backup.json"))
            files = meta["files"]
            for rel, info in files.items():
                if not _safe_rel(rel):
                    raise SystemExit("That backup holds an unsafe path, so it was not used.")
                if _sha(z.read("files/" + rel)) != info["sha256"]:
                    raise SystemExit(f"That backup is damaged ({rel} does not match). Nothing was changed.")
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        raise SystemExit("That backup can't be read, so nothing was changed.")
    return {"name": os.path.basename(name), "files": sorted(files), "at": meta.get("at", 0), "reason": meta.get("reason", "")}


def _safe_rel(rel: str) -> bool:
    parts = rel.split("/")
    return bool(rel) and not rel.startswith(("/", "\\")) and ":" not in rel and ".." not in parts and "\\" not in rel and all(parts) and rel.lower().endswith(KINDS)


def restore(d: str, name: str) -> dict:
    """Put a snapshot's files back. The snapshot is checked first; the present state is snapshotted so this can be undone; nothing the snapshot lacks is deleted."""
    info = verify(d, name)
    before = make(d, "before restore")
    path = os.path.join(_root(d), os.path.basename(name))
    real = os.path.realpath(d)
    done = 0
    skipped = []
    with zipfile.ZipFile(path) as z:
        for rel in info["files"]:
            if rel in NEVER_RESTORED:
                skipped.append(rel)
                continue
            target = os.path.realpath(os.path.join(d, *rel.split("/")))
            if not target.startswith(real + os.sep):
                raise SystemExit("That backup holds an unsafe path, so it was not used.")
            data = z.read("files/" + rel)
            if rel.lower().endswith(".json"):
                try:
                    json.loads(data.decode("utf-8-sig"))
                except ValueError:
                    skipped.append(rel)              # a damaged record inside a snapshot is never put back over a file that might be fine
                    continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            safeio._swap_in(target, data)
            done += 1
    return {"restored": os.path.basename(name), "files": done, "kept_as_is": skipped, "undo": before.get("latest")}


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="filmbackup")
    ap.add_argument("action", choices=["make", "list", "verify", "restore"])
    ap.add_argument("film")
    ap.add_argument("name", nargs="?", default="")
    a = ap.parse_args(argv)
    try:
        d = os.path.abspath(a.film)
        if a.action == "make":
            res = make(d, a.name or "auto")
        elif a.action == "list":
            res = {"backups": list_backups(d)}
        elif not a.name:
            raise SystemExit("Choose which backup.")
        elif a.action == "verify":
            res = verify(d, a.name)
        else:
            res = restore(d, a.name)
        print(json.dumps({"event": "result", "data": res}), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except OSError as e:
        print(json.dumps({"event": "error", "message": __import__("filmcrafter_engine.errtext", fromlist=["plain"]).plain(e)}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
