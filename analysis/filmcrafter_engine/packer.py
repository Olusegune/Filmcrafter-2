""".filmpack: a whole film in one file, for sharing, archiving or moving to another computer.

The working film stays a folder (fast, safe while rendering, easy to recover). A .filmpack file is a zip of that
folder: the story, cast, shots, your recordings, every picture and video made, and the render project, minus caches that
are rebuilt on their own. Opening one unpacks it into the FilmCrafter projects folder under a new name, so it never
overwrites anything. (A render project on its own, and files made by earlier versions with the extension .pulse, are read too.)

  python -m filmcrafter_engine.packer pack <film_or_project_dir> <dest.filmpack>
  python -m filmcrafter_engine.packer unpack <file.filmpack> <projects_root>
  python -m filmcrafter_engine.packer backup|backups|restore <project_dir> [name]

Backups are automatic snapshots of the project's decisions (plan, shots, keyframe choices, approvals, library, Bible):
the small .json files, not the media. Media is never deleted, so a snapshot is enough to go back to any earlier state.
The newest 20 are kept in <project>/backups; a restore first snapshots the current state, so it can be undone.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import zipfile

FORMAT = 1
SKIP_DIRS = {"cache", "thumbnails", "__pycache__", "backups"}
KEEP_BACKUPS = 20
SKIP_FILES = re.compile(r"(\.tmp|\.lock|\.part\.mp4|\.tmp\.mp4)$", re.I)
STORED = {".mp4", ".mov", ".webm", ".m4v", ".png", ".jpg", ".jpeg", ".webp", ".mp3", ".m4a", ".flac", ".zip", ".pdf"}


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):   # the app went away: nobody to tell
        pass


PROJECT_MARKS = ("project.json", "directed.json", "production.json", "jobs.json", "songmap.json", "commands.json", "shots.json")


def looks_like_project(path: str) -> bool:
    """A folder that is (or was being made into) a project: it has project.json, a .filmcrafter file, or at least two of a project's own files. A copy that stopped part way (the
    path got too long, or the disk filled) still counts, which is why project.json alone is not the test."""
    try:
        names = os.listdir(path)
    except OSError:
        return False
    if "project.json" in names or "film.json" in names or any(n.lower().endswith(".filmcrafter") for n in names):
        return True
    return sum(1 for n in PROJECT_MARKS if n in names) >= 2


def is_film_dir(d: str) -> bool:
    return os.path.isfile(os.path.join(d, "film.json"))


def _files(d: str, nested: list | None = None, film: bool = False):
    """Every file of the project, except rebuildable caches and any other project that sits inside this one (a copy saved into the project folder by mistake): packing those would
    pack the project many times over, and when the copies contain each other the paths grow past what Windows allows. `nested` collects the folders left out."""
    for root, dirs, files in os.walk(d):
        keep = []
        for x in dirs:
            if x in SKIP_DIRS:
                continue
            sub = os.path.join(root, x)
            if film and root == d and x == "render":                  # a film's own render project is part of the film: its pictures and videos are what was paid for
                keep.append(x)
                continue
            if looks_like_project(sub):
                if nested is not None:
                    nested.append(os.path.relpath(sub, d).replace(os.sep, "/"))
                continue
            keep.append(x)
        dirs[:] = keep
        for f in files:
            if not SKIP_FILES.search(f):
                yield os.path.join(root, f)


def pack(d: str, dest: str) -> dict:
    film = is_film_dir(d)
    if not film and not os.path.exists(os.path.join(d, "project.json")):
        raise SystemExit("That isn't a FilmCrafter film.")
    if not dest.lower().endswith((".filmpack", ".pulse")):
        dest += ".filmpack"
    left_out: list[str] = []
    files, sizes = [], {}
    for f in _files(d, left_out, film):
        try:
            sizes[f] = os.path.getsize(f)
        except OSError:
            continue                                 # a file that cannot be read (gone, or a path too long for Windows) is left out, not fatal
        files.append(f)
    total = sum(sizes.values()) or 1
    title = (json.load(open(os.path.join(d, "film.json" if film else "project.json"), encoding="utf-8")).get("title") or "Film")
    tmp, done = dest + ".part", 0
    with zipfile.ZipFile(tmp, "w", allowZip64=True) as z:
        z.writestr("filmpack.json", json.dumps({"format": FORMAT, "kind": "film" if film else "render", "title": title, "packed": int(time.time()), "files": len(files)}))
        for f in files:
            rel = os.path.relpath(f, d).replace(os.sep, "/")
            comp = zipfile.ZIP_STORED if os.path.splitext(f)[1].lower() in STORED else zipfile.ZIP_DEFLATED
            z.write(f, "project/" + rel, compress_type=comp)
            done += sizes[f]
            emit(event="progress", stage="packing", progress=round(done / total, 3))
    os.replace(tmp, dest)
    return {"path": dest, "files": len(files), "bytes": os.path.getsize(dest), "title": title, "left_out": left_out}


def _unique(root: str, name: str) -> str:
    base = re.sub(r'[<>:"/\\|?*]+', " ", name).strip() or "Project"
    cand, n = os.path.join(root, base), 2
    while os.path.exists(cand):
        cand, n = os.path.join(root, f"{base} ({n})"), n + 1
    return cand


MAX_ENTRIES = 200_000                  # a film with thousands of takes is well under this
MAX_RATIO = 500                        # media is already compressed (deflate itself cannot exceed ~1000:1); beyond this a big file is a zip bomb, not a film
RATIO_FLOOR = 512 * 1024 * 1024        # ... judged only when it is big enough to matter
DISK_MARGIN = 512 * 1024 * 1024        # always leave this much free


def _check_archive(z: zipfile.ZipFile, names: list[str], root: str) -> None:
    """Refuse an archive that is not a film before writing anything: too many entries, entries that expand absurdly, links, odd names, or more than the disk can hold."""
    import shutil
    import stat
    if len(names) > MAX_ENTRIES:
        raise SystemExit(f"That file has more than {MAX_ENTRIES:,} items, which is not a film file, so it was not opened.")
    seen = set()
    total = 0
    for n in names:
        info = z.getinfo(n)
        rel = n[len("project/"):]
        parts = rel.split("/")
        if "\\" in rel or ":" in rel or rel.startswith("/") or ".." in parts or any(p in ("", ".") for p in parts) or any(p.rstrip(" .") != p for p in parts):
            raise SystemExit("That file contains an unsafe path and was not opened.")
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise SystemExit("That file contains a link, which a film never does, so it was not opened.")
        low = rel.lower()
        if low in seen:
            raise SystemExit("That file lists the same item twice, so it was not opened.")
        seen.add(low)
        if info.file_size > RATIO_FLOOR and info.compress_size and info.file_size / info.compress_size > MAX_RATIO:
            raise SystemExit("That file expands far more than a film does (it may be unsafe), so it was not opened.")
        total += info.file_size
    try:
        free = shutil.disk_usage(root if os.path.isdir(root) else os.path.dirname(root) or ".").free
    except OSError:
        free = None
    if free is not None and total + DISK_MARGIN > free:
        gb = lambda x: f"{x / 1e9:.1f} GB"
        raise SystemExit(f"This film needs {gb(total)} and only {gb(free)} is free here, so it was not opened. Free some space and try again.")


def _discard(dest: str) -> None:
    import shutil
    try:
        shutil.rmtree(dest)
    except OSError:
        pass


def unpack(path: str, root: str) -> dict:
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        raise SystemExit("That file isn't a readable film file.")
    with z:
        meta = None
        for meta_name in ("filmpack.json", "pulse.json"):                        # pulse.json: files made by earlier versions
            try:
                meta = json.loads(z.read(meta_name))
                break
            except KeyError:
                continue
        if meta is None:
            raise SystemExit("That file isn't a FilmCrafter film file.")
        if meta.get("format", 0) > FORMAT:
            raise SystemExit("This file was made by a newer FilmCrafter. Update the app to open it.")
        names = [n for n in z.namelist() if n.startswith("project/") and not n.endswith("/")]
        if "project/film.json" not in names and "project/project.json" not in names:
            raise SystemExit("That file has no film inside.")
        _check_archive(z, names, root)
        dest = _unique(root, meta.get("title") or os.path.splitext(os.path.basename(path))[0])
        real = os.path.realpath(dest)
        total = sum(z.getinfo(n).file_size for n in names) or 1
        done = 0
        try:
            for n in names:
                target = os.path.realpath(os.path.join(dest, n[len("project/"):]))
                if not target.startswith(real + os.sep):   # never write outside the new project folder
                    raise SystemExit("That file contains an unsafe path and was not opened.")
                os.makedirs(os.path.dirname(target), exist_ok=True)
                allowed = z.getinfo(n).file_size
                wrote = 0
                with z.open(n) as src, open(target, "wb") as out:
                    while chunk := src.read(1 << 20):
                        wrote += len(chunk)
                        if wrote > allowed:                  # the file says it is smaller than it is
                            raise SystemExit("That file is not a valid FilmCrafter film file (its contents do not match what it says), so it was not opened.")
                        out.write(chunk)
                done += allowed
                emit(event="progress", stage="unpacking", progress=round(done / total, 3))
        except zipfile.BadZipFile:
            _discard(dest)
            raise SystemExit("That film file is damaged (part of it does not match what it says), so it was not opened.")
        except BaseException:
            _discard(dest)                                   # the folder was made by this call and holds only what this call wrote
            raise
    name = os.path.basename(dest)
    if name != meta.get("title"):   # opened next to an existing copy: give this one its own name
        pj = os.path.join(dest, "film.json" if os.path.isfile(os.path.join(dest, "film.json")) else "project.json")
        p = json.load(open(pj, encoding="utf-8"))
        p["title"] = name
        with open(pj, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=2, ensure_ascii=False)
    return {"dir": dest, "title": name}


def _state_files(d: str) -> list[str]:
    return sorted(f for f in os.listdir(d) if f.endswith((".json", ".md")) and os.path.isfile(os.path.join(d, f)))


def _digest(d: str) -> str:
    from .safe import sha1 as _sha1
    import hashlib
    h = _sha1()
    for f in _state_files(d):
        h.update(f.encode())
        with open(os.path.join(d, f), "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


def backups(d: str) -> list[dict]:
    root = os.path.join(d, "backups")
    out = []
    for f in sorted(os.listdir(root), reverse=True) if os.path.isdir(root) else []:
        if f.endswith(".zip"):
            try:
                with zipfile.ZipFile(os.path.join(root, f)) as z:
                    meta = json.loads(z.read("backup.json"))
            except (OSError, KeyError, ValueError, zipfile.BadZipFile):
                continue
            out.append({"name": f, **meta})
    seq = lambda b: (b.get("at_ns") or b.get("at", 0) * 10**9, b["name"])
    return sorted(out, key=seq, reverse=True)   # newest first, exact even within one millisecond


def backup(d: str, reason: str = "auto") -> dict:
    """Snapshot the project's state files. Skipped when nothing changed since the last snapshot."""
    if not os.path.exists(os.path.join(d, "project.json")):
        raise SystemExit("That isn't a FilmCrafter project.")
    digest = _digest(d)
    prev = backups(d)
    if prev and prev[0].get("digest") == digest:
        return {"made": False, "latest": prev[0]["name"], "count": len(prev)}
    root = os.path.join(d, "backups")
    os.makedirs(root, exist_ok=True)
    now = time.time()
    stem = time.strftime("%Y%m%d-%H%M%S", time.localtime(now)) + f"-{int(now * 1000) % 1000:03d}"
    name, n = stem + ".zip", 1
    while os.path.exists(os.path.join(root, name)):   # two snapshots in the same millisecond never overwrite each other
        name, n = f"{stem}-{n}.zip", n + 1
    files = _state_files(d)
    tmp = os.path.join(root, name + ".part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("backup.json", json.dumps({"at": int(now), "at_ns": max(time.time_ns(), (prev[0].get("at_ns") or 0) + 1 if prev else 0), "reason": reason, "digest": digest, "files": files}))
        for f in files:
            z.write(os.path.join(d, f), f)
    os.replace(tmp, os.path.join(root, name))
    for old in backups(d)[KEEP_BACKUPS:]:
        os.remove(os.path.join(root, old["name"]))
    return {"made": True, "latest": name, "count": min(len(prev) + 1, KEEP_BACKUPS)}


def restore(d: str, name: str) -> dict:
    """Go back to a snapshot. The current state is snapshotted first, so this can be undone."""
    path = os.path.join(d, "backups", os.path.basename(name))
    if not os.path.isfile(path):
        raise SystemExit("That backup no longer exists.")
    with zipfile.ZipFile(path) as z:
        meta = json.loads(z.read("backup.json"))
        files = [f for f in meta["files"] if f == os.path.basename(f) and f.endswith((".json", ".md"))]
        before = backup(d, "before restore")
        for f in files:
            tmp = os.path.join(d, f + f".{os.getpid()}.tmp")
            with open(tmp, "wb") as out:
                out.write(z.read(f))
            os.replace(tmp, os.path.join(d, f))
    return {"restored": name, "files": len(files), "undo": before["latest"]}


def main(argv: list[str]) -> int:
    try:
        if argv[0] in ("backup", "backups", "restore"):
            res = backup(argv[1], argv[2] if len(argv) > 2 else "auto") if argv[0] == "backup" else                 {"backups": backups(argv[1])} if argv[0] == "backups" else restore(argv[1], argv[2])
        else:
            res = pack(argv[1], argv[2]) if argv[0] == "pack" else unpack(argv[1], argv[2])
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
