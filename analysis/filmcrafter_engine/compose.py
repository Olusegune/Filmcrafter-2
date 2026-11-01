"""Compose a shot three ways, each one screen: start and end pictures, reference pictures, or a motion video that drives your character.

  start and end   a first picture and a last picture; the model animates between them (frames.py; the models that take both are listed in docs/END_FRAMES.md)
  references      pictures of the people, places and things as references, with no start frame (the model invents the opening)
  motion          a reference VIDEO says how the character moves (a dance, a walk, a performance); a picture says who the character is (Kling Motion Control, Wan Animate)

This module keeps what a shot's motion take is made of (the video, the character picture, how to face, how sharp, whose background), checks the video, and queues the take through
render.enqueue so that price, budget and the renderer work exactly as for any other take.

  python -m filmcrafter_engine.compose <state|set_motion|clear_motion|models|queue_motion> <project> --data '{...}'
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

from .shothistory import tracked

NOWIN = 0x08000000 if sys.platform == "win32" else 0
MOTION_EXT = (".mp4", ".mov")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
MIN_S, MAX_S = 3.0, 30.0           # the motion models take a reference video of this length
MAX_VIDEO_MB = 100
ORIENTATIONS = ("video", "image")
QUALITIES = ("std", "pro")
REFS_RX = re.compile(r"reference|r2v|seedance-2|omni", re.I)     # models whose picture input is references, not frames


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _path(d: str) -> str:
    return os.path.join(d, "compose.json")


def _save(d: str, data: dict) -> None:
    tmp = _path(d) + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, _path(d))


def _shot(d: str, shot_id: str) -> tuple[str, dict, dict]:
    from .planio import find_shot, load_plan
    name, plan = load_plan(d)
    sh, sc = find_shot(plan, shot_id)
    return name, sh, sc


def _start_ref(d: str, shot_id: str) -> str | None:
    """The shot's start frame (its approved keyframe) as a project-relative file, if it has one."""
    from . import frames
    plan_name, _ = frames._plan(d)
    ref = frames.start_ref(d, plan_name, shot_id)
    return ref[len("project:"):] if ref else None


def _check_video(path: str) -> float:
    """The seconds of a motion video, or a plain-words refusal."""
    from .editor_export import probe
    if os.path.splitext(path)[1].lower() not in MOTION_EXT:
        raise SystemExit("Use an MP4 or MOV video.")
    if not os.path.isfile(path):
        raise SystemExit("That video can't be found.")
    if os.path.getsize(path) > MAX_VIDEO_MB * 1_000_000:
        raise SystemExit(f"That video is over {MAX_VIDEO_MB} MB. Shorten or compress it first.")
    pr = probe(path)
    if not pr["video"] or pr["duration"] <= 0:
        raise SystemExit("That file can't be read as a video.")
    if not MIN_S <= pr["duration"] <= MAX_S:
        raise SystemExit(f"The motion video is {pr['duration']:.1f} s. Motion control needs {MIN_S:g} to {MAX_S:g} seconds.")
    return round(pr["duration"], 2)


def state(d: str, shot_id: str) -> dict:
    """What this shot's motion take would be made of, and what to tell the user about it. Free."""
    name, sh, _sc = _shot(d, shot_id)
    cfg = ((_read(_path(d), {}) or {}).get(shot_id) or {}).get("motion") or {}
    shot_s = round(float(sh.get("end", 0)) - float(sh.get("start", 0)), 2)
    start = _start_ref(d, shot_id)
    image = cfg.get("image") if cfg.get("image") and os.path.isfile(os.path.join(d, cfg["image"])) else None
    video = cfg.get("video") if cfg.get("video") and os.path.isfile(os.path.join(d, cfg["video"])) else None
    out = {"shot": shot_id, "shot_seconds": shot_s, "video": video, "video_seconds": cfg.get("video_seconds") if video else None, "image": image or start,
           "image_is_start": not image and bool(start), "orientation": cfg.get("orientation", "video"), "quality": cfg.get("quality", "pro"),
           "background": cfg.get("background", "video"), "note": cfg.get("note", ""), "notes": []}
    if video and out["video_seconds"]:
        diff = out["video_seconds"] - shot_s
        if diff < -0.5:
            out["notes"].append(f"The motion video is {out['video_seconds']:g} s but the shot is {shot_s:g} s, so the last {-diff:.1f} s will hold the final frame. Extend the take, or choose a longer video.")
        elif diff > 0.5:
            out["notes"].append(f"The motion video is {out['video_seconds']:g} s but the shot is {shot_s:g} s: the take will be trimmed to the shot when the film is built.")
        if out["orientation"] == "image" and out["video_seconds"] > 10:
            out["notes"].append("Facing the picture limits the take to 10 seconds on some models; the video is longer.")
    out["prompt"] = prompt_get(d, shot_id)
    out["ready"] = bool(out["video"] and out["image"])
    out["missing"] = [x for x, ok in (("a motion video", bool(out["video"])), ("a character picture (make a keyframe or bring one)", bool(out["image"]))) if not ok]
    return out


@tracked("Change motion", lambda d, shot_id, *a, **k: [shot_id])
def set_motion(d: str, shot_id: str, data: dict) -> dict:
    from .library import shot_state
    from .safe import file_part
    _shot(d, shot_id)                                  # raises unless the plan has this shot: the id is then safe to use in file names
    if shot_state(d).get(shot_id, {}).get("locked"):
        raise SystemExit(f"{shot_id} is locked. Unlock it to change how it is made.")
    all_ = _read(_path(d), {}) or {}
    cfg = dict((all_.get(shot_id) or {}).get("motion") or {})
    os.makedirs(os.path.join(d, "media"), exist_ok=True)
    if data.get("video_path"):
        src = data["video_path"]
        secs = _check_video(src)
        rel = f"media/{file_part(shot_id)}_motion_{int(time.time())}{os.path.splitext(src)[1].lower()}"
        shutil.copy2(src, os.path.join(d, rel))
        cfg.update(video=rel, video_seconds=secs)
    if data.get("image_path"):
        src = data["image_path"]
        if not os.path.isfile(src):
            raise SystemExit("That picture can't be found.")
        if os.path.splitext(src)[1].lower() not in IMAGE_EXT:
            raise SystemExit("Use a PNG, JPG or WebP picture.")
        rel = f"media/{file_part(shot_id)}_character_{int(time.time())}{os.path.splitext(src)[1].lower()}"
        shutil.copy2(src, os.path.join(d, rel))
        cfg["image"] = rel
    if data.get("image_from_start"):
        cfg.pop("image", None)
    if "orientation" in data:
        if data["orientation"] not in ORIENTATIONS:
            raise SystemExit("Face the video or the picture.")
        cfg["orientation"] = data["orientation"]
    if "quality" in data:
        if data["quality"] not in QUALITIES:
            raise SystemExit("Quality is standard or high.")
        cfg["quality"] = data["quality"]
    if "background" in data:
        cfg["background"] = "image" if data["background"] == "image" else "video"
    if "note" in data:
        cfg["note"] = str(data["note"] or "")[:600]
    all_.setdefault(shot_id, {})["motion"] = cfg
    _save(d, all_)
    return state(d, shot_id)


@tracked("Clear motion", lambda d, shot_id, *a, **k: [shot_id])
def clear_motion(d: str, shot_id: str) -> dict:
    all_ = _read(_path(d), {}) or {}
    (all_.get(shot_id) or {}).pop("motion", None)
    _save(d, all_)
    return state(d, shot_id)


# ---------------------------------------------------------------- the motion library

# Motion videos you want to use more than once (a rehearsal clip, a walk cycle, a dance move) live on this computer, outside any one project, and are copied into a shot only when used.


def lib_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".filmcrafter", "motion")


def _lib_index() -> list[dict]:
    items = _read(os.path.join(lib_dir(), "index.json"), []) or []
    return [i for i in items if isinstance(i, dict) and isinstance(i.get("id"), str) and re.fullmatch(r"[0-9a-f]{10}", i["id"])
            and _plain(i.get("file")) and (not i.get("thumb") or _plain(i.get("thumb")))]


def _plain(name) -> bool:
    """A bare file name: no folders, no way out of the library folder."""
    return isinstance(name, str) and bool(name) and os.path.basename(name) == name and name not in (".", "..") and "\\" not in name and ":" not in name


def _lib_save(items: list[dict]) -> None:
    os.makedirs(lib_dir(), exist_ok=True)
    tmp = os.path.join(lib_dir(), f"index.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=1)
    os.replace(tmp, os.path.join(lib_dir(), "index.json"))


def _clean_name(text: str, fallback: str = "Motion") -> str:
    t = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text or "")).strip()
    return (re.sub(r"\s+", " ", t)[:60]) or fallback


LIB_MAX = 300
TAGS_MAX, TAG_LEN = 8, 24


def _clean_tags(tags) -> list[str]:
    """Up to 8 short lower-case words or phrases, no control characters, no repeats. Anything that isn't a list of text gives none."""
    out: list[str] = []
    for t in tags if isinstance(tags, (list, tuple)) else []:
        if not isinstance(t, str):
            continue
        c = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]+", " ", t)).strip().lower()[:TAG_LEN].strip()
        if c and c not in out:
            out.append(c)
    return out[:TAGS_MAX]


def _fingerprint(path: str) -> str:
    import hashlib
    h = hashlib.sha1(usedforsecurity=False)
    h.update(str(os.path.getsize(path)).encode())
    with open(path, "rb") as f:
        h.update(f.read(8 << 20))
    return h.hexdigest()


def _thumb(video: str, out: str) -> bool:
    from .export import ffmpeg
    for t in ("0.5", "0"):
        p = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", t, "-i", video, "-frames:v", "1", "-vf", "scale=240:-2", "-q:v", "4", out],
                           capture_output=True, text=True, creationflags=NOWIN)
        if p.returncode == 0 and os.path.exists(out):
            return True
    return False


def _data_url(path: str) -> str | None:
    import base64
    try:
        with open(path, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    except OSError:
        return None


def lib_list() -> list[dict]:
    """The saved motions, newest first, with a small picture of each. An entry whose file has gone is left out (and forgotten)."""
    items = _lib_index()
    alive = [i for i in items if os.path.isfile(os.path.join(lib_dir(), i.get("file", "")))]
    if len(alive) != len(items):
        _lib_save(alive)
    return [{"id": i["id"], "name": i.get("name", "Motion"), "seconds": i.get("seconds"), "width": i.get("width"), "height": i.get("height"), "added": i.get("added"),
             "tags": _clean_tags(i.get("tags")), "path": os.path.join(lib_dir(), i["file"]),
             "thumb": _data_url(os.path.join(lib_dir(), i["thumb"])) if i.get("thumb") else None} for i in sorted(alive, key=lambda x: -(x.get("added") or 0))][:LIB_MAX]


def lib_add(path: str, name: str | None = None) -> dict:
    """Save a motion video to the library (copied; the original is never touched). The same video added twice is kept once."""
    from .editor_export import probe
    secs = _check_video(path)
    fp = _fingerprint(path)
    items = _lib_index()
    same = next((i for i in items if i.get("fp") == fp and os.path.isfile(os.path.join(lib_dir(), i.get("file", "")))), None)
    if same:
        return {**next(x for x in lib_list() if x["id"] == same["id"]), "already": True}
    import uuid
    os.makedirs(lib_dir(), exist_ok=True)
    mid = uuid.uuid4().hex[:10]
    ext = os.path.splitext(path)[1].lower()
    shutil.copy2(path, os.path.join(lib_dir(), mid + ext))
    thumb = mid + ".jpg" if _thumb(os.path.join(lib_dir(), mid + ext), os.path.join(lib_dir(), mid + ".jpg")) else None
    pr = probe(path)
    items.append({"id": mid, "name": _clean_name(name or os.path.splitext(os.path.basename(path))[0]), "file": mid + ext, "thumb": thumb, "seconds": secs, "width": pr["w"], "height": pr["h"],
                  "added": int(time.time()), "fp": fp, "tags": []})
    _lib_save(items)
    return {**next(x for x in lib_list() if x["id"] == mid), "already": False}


def lib_add_from_shot(d: str, shot_id: str, name: str | None = None) -> dict:
    st = state(d, shot_id)
    if not st["video"]:
        raise SystemExit("This shot has no motion video to save yet.")
    return lib_add(os.path.join(d, st["video"]), name or f"{shot_id} motion")


def _lib_item(item_id: str) -> dict:
    it = next((i for i in _lib_index() if i["id"] == item_id), None)
    if not it:
        raise SystemExit("That motion isn't in the library any more.")
    return it


def lib_rename(item_id: str, name: str) -> list[dict]:
    items = _lib_index()
    _lib_item(item_id)
    for i in items:
        if i["id"] == item_id:
            i["name"] = _clean_name(name, i.get("name", "Motion"))
    _lib_save(items)
    return lib_list()


def lib_tag(item_id: str, tags) -> list[dict]:
    """Replace a motion's tags (cleaned: at most 8, short, lower case)."""
    items = _lib_index()
    _lib_item(item_id)
    for i in items:
        if i["id"] == item_id:
            i["tags"] = _clean_tags(tags)
    _lib_save(items)
    return lib_list()


# Moving the library between computers: one .zip with a manifest and the videos. Reading it is a trust boundary, so it is never unpacked wholesale: only the manifest and the files the
# manifest names, under names we generate ourselves, each checked as a real motion video before it is kept; sizes and counts are capped; ids, pictures and fingerprints are made here.
PACK_FORMAT = "filmcrafter-motion-library"
PACK_MAX_ENTRIES = 2 * LIB_MAX + 1
PACK_MAX_MANIFEST = 2_000_000
PACK_MAX_TOTAL = 3_000_000_000
_PACK_FILE = re.compile(r"[0-9a-f]{10}\.(?:mp4|mov)")


def lib_export(dest: str, ids=None) -> dict:
    """Write the library (or the chosen motions) to a .zip. The library itself is untouched."""
    import zipfile
    if not isinstance(dest, str) or not dest.strip():
        raise SystemExit("Choose where to save the library.")
    if not dest.lower().endswith(".zip"):
        dest += ".zip"
    want = set(ids) if isinstance(ids, list) else None
    items = [i for i in _lib_index() if (want is None or i["id"] in want) and os.path.isfile(os.path.join(lib_dir(), i.get("file", "")))]
    if not items:
        raise SystemExit("There is nothing in the library to export.")
    if os.path.realpath(dest).startswith(os.path.realpath(lib_dir()) + os.sep):
        raise SystemExit("Save the export outside the library folder.")
    manifest = {"format": PACK_FORMAT, "version": 1, "items": [{"file": i["file"], "name": i.get("name", "Motion"), "tags": _clean_tags(i.get("tags")), "seconds": i.get("seconds"),
                                                                   "width": i.get("width"), "height": i.get("height")} for i in items]}
    tmp = dest + f".{os.getpid()}.tmp"
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
            z.writestr("manifest.json", json.dumps(manifest, indent=1))
            for i in items:
                z.write(os.path.join(lib_dir(), i["file"]), i["file"])
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return {"path": dest, "count": len(items)}


def _read_pack_manifest(z) -> list[dict]:
    try:
        info = z.getinfo("manifest.json")
    except KeyError:
        raise SystemExit("That isn't a FilmCrafter motion library: it has no manifest.")
    if info.file_size > PACK_MAX_MANIFEST:
        raise SystemExit("That motion library's manifest is too large.")
    try:
        m = json.loads(z.read(info).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise SystemExit("That motion library's manifest can't be read.")
    if not isinstance(m, dict) or m.get("format") != PACK_FORMAT or m.get("version") != 1 or not isinstance(m.get("items"), list):
        raise SystemExit("That isn't a FilmCrafter motion library.")
    return [i for i in m["items"] if isinstance(i, dict)][:LIB_MAX]


def lib_import(src: str) -> dict:
    """Add the motions in an exported library .zip. Each is checked like any added video; ones already here (the same video) are skipped. Nothing outside the library folder is written."""
    import uuid
    import zipfile
    if not isinstance(src, str) or not os.path.isfile(src):
        raise SystemExit("That file can't be found.")
    try:
        z = zipfile.ZipFile(src)
    except (zipfile.BadZipFile, OSError):
        raise SystemExit("That isn't a zip file FilmCrafter can read.")
    added, skipped, bad = [], 0, 0
    with z:
        infos = z.infolist()
        if len(infos) > PACK_MAX_ENTRIES:
            raise SystemExit("That motion library has too many files.")
        by_name = {i.filename: i for i in infos}
        if sum(i.file_size for i in infos) > PACK_MAX_TOTAL:
            raise SystemExit("That motion library is too large.")
        entries = _read_pack_manifest(z)
        os.makedirs(lib_dir(), exist_ok=True)
        for e in entries:
            if len(_lib_index()) >= LIB_MAX:
                raise SystemExit(f"The library is full ({LIB_MAX} motions). Remove some first.")
            fn = e.get("file")
            zi = by_name.get(fn) if isinstance(fn, str) and _PACK_FILE.fullmatch(fn) else None
            if zi is None or zi.is_dir() or zi.file_size > MAX_VIDEO_MB * 1_000_000:
                bad += 1
                continue
            ext = os.path.splitext(fn)[1]
            tmp = os.path.join(lib_dir(), f"import.{os.getpid()}{ext}")
            try:
                n = 0
                with z.open(zi) as r, open(tmp, "wb") as w:             # copied in pieces and counted, whatever the zip says its size is
                    while chunk := r.read(1 << 20):
                        n += len(chunk)
                        if n > MAX_VIDEO_MB * 1_000_000:
                            raise SystemExit("too large")
                        w.write(chunk)
                secs = _check_video(tmp)
                fp = _fingerprint(tmp)
                items = _lib_index()
                if any(i.get("fp") == fp and os.path.isfile(os.path.join(lib_dir(), i.get("file", ""))) for i in items):
                    skipped += 1
                    continue
                from .editor_export import probe
                pr = probe(tmp)
                mid = uuid.uuid4().hex[:10]
                os.replace(tmp, os.path.join(lib_dir(), mid + ext))
                thumb = mid + ".jpg" if _thumb(os.path.join(lib_dir(), mid + ext), os.path.join(lib_dir(), mid + ".jpg")) else None
                items.append({"id": mid, "name": _clean_name(e.get("name")), "file": mid + ext, "thumb": thumb, "seconds": secs, "width": pr["w"], "height": pr["h"],
                              "added": int(time.time()), "fp": fp, "tags": _clean_tags(e.get("tags"))})
                _lib_save(items)
                added.append(mid)
            except SystemExit:
                bad += 1
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
    return {"added": len(added), "skipped": skipped, "refused": bad, "items": lib_list()}


TRASH_MAX = 20           # removed motions kept so Remove can be undone; the oldest are deleted for good beyond this


def _trash_dir() -> str:
    return os.path.join(lib_dir(), ".trash")


def _trash_index() -> list[dict]:
    items = _read(os.path.join(_trash_dir(), "index.json"), []) or []
    return [i for i in items if isinstance(i, dict) and isinstance(i.get("id"), str) and re.fullmatch(r"[0-9a-f]{10}", i["id"])
            and _plain(i.get("file")) and (not i.get("thumb") or _plain(i.get("thumb")))]


def _trash_save(items: list[dict]) -> None:
    os.makedirs(_trash_dir(), exist_ok=True)
    tmp = os.path.join(_trash_dir(), f"index.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=1)
    os.replace(tmp, os.path.join(_trash_dir(), "index.json"))


def _inside(base: str, name) -> str | None:
    """The full path of a plain file name inside `base`, or None when the name would lead anywhere else."""
    if not isinstance(name, str) or not name or os.path.basename(name) != name or name in (".", ".."):
        return None
    p = os.path.realpath(os.path.join(base, name))
    return p if p.startswith(os.path.realpath(base) + os.sep) else None


def lib_remove(item_id: str) -> list[dict]:
    """Take a motion out of the library. Its files go to a hidden trash (the last 20 are kept) so that lib_restore can bring it back."""
    it = _lib_item(item_id)
    os.makedirs(_trash_dir(), exist_ok=True)
    for key in ("file", "thumb"):
        src, dst = _inside(lib_dir(), it.get(key)), _inside(_trash_dir(), it.get(key))
        if src and dst and os.path.isfile(src):
            os.replace(src, dst)
    trash = [t for t in _trash_index() if t["id"] != item_id] + [it]
    for old in trash[:-TRASH_MAX]:                                         # the oldest are gone for good
        for key in ("file", "thumb"):
            p = _inside(_trash_dir(), old.get(key))
            if p and os.path.isfile(p):
                os.remove(p)
    _trash_save(trash[-TRASH_MAX:])
    _lib_save([i for i in _lib_index() if i["id"] != item_id])
    return lib_list()


def lib_restore(item_id: str) -> list[dict]:
    """Bring back a motion that was removed (undo for Remove)."""
    it = next((t for t in _trash_index() if t["id"] == item_id), None)
    if not it:
        raise SystemExit("That motion can't be brought back any more.")
    if any(i.get("fp") and i.get("fp") == it.get("fp") for i in _lib_index()):      # the same video was added again meanwhile
        _trash_save([t for t in _trash_index() if t["id"] != item_id])
        return lib_list()
    for key in ("file", "thumb"):
        src, dst = _inside(_trash_dir(), it.get(key)), _inside(lib_dir(), it.get(key))
        if src and dst and os.path.isfile(src):
            os.replace(src, dst)
    _lib_save([i for i in _lib_index() if i["id"] != item_id] + [it])
    _trash_save([t for t in _trash_index() if t["id"] != item_id])
    return lib_list()


def lib_use(d: str, shot_id: str, item_id: str) -> dict:
    """Use a saved motion for this shot: it is copied into the project like any motion video you choose."""
    it = _lib_item(item_id)
    return set_motion(d, shot_id, {"video_path": os.path.join(lib_dir(), it["file"])})


# ---------------------------------------------------------------- the prompt for a take

PROMPT_MAX = 4000


def prompt_get(d: str, shot_id: str) -> dict:
    """{mode: auto | mine, text, only}: FilmCrafter writes the prompt from the shot (auto), or the filmmaker's own words say what happens (mine)."""
    p = ((_read(_path(d), {}) or {}).get(shot_id) or {}).get("prompt") or {}
    return {"mode": "mine" if p.get("mode") == "mine" and str(p.get("text") or "").strip() else "auto", "text": str(p.get("text") or ""), "only": bool(p.get("only"))}


@tracked("Change take prompt", lambda d, shot_id, *a, **k: [shot_id])
def prompt_set(d: str, shot_id: str, data: dict) -> dict:
    _shot(d, shot_id)
    all_ = _read(_path(d), {}) or {}
    cur = dict((all_.get(shot_id) or {}).get("prompt") or {})
    if "mode" in data:
        if data["mode"] not in ("auto", "mine"):
            raise SystemExit("Choose FilmCrafter's prompt or your own.")
        cur["mode"] = data["mode"]
    if "text" in data:
        cur["text"] = str(data["text"] or "")[:PROMPT_MAX]
    if "only" in data:
        cur["only"] = bool(data["only"])
    all_.setdefault(shot_id, {})["prompt"] = cur
    _save(d, all_)
    return prompt_get(d, shot_id)


def prompt_limit(d: str, provider: str, model: str) -> int:
    """The longest prompt this model takes (from its own description; 0 when it doesn't say). Reads the saved schema only."""
    from . import render
    path = os.path.join(render.CACHE_DIR, f"{provider}__{re.sub(r'[^A-Za-z0-9._-]+', '_', model)}.json")
    m = _read(path)
    if not m or "inputs" not in m:
        return render.known_prompt_limit(model)
    f = next((x for x in m["inputs"] if x["name"] == "prompt"), None)
    return int((f or {}).get("max_length") or render.known_prompt_limit(model) or 0)


def prompt_lint(d: str, shot_id: str, text: str, provider: str = "", model: str = "") -> dict:
    from . import promptwriter
    ctx = {**promptwriter.context(d, shot_id), "limit": prompt_limit(d, provider, model) if model else 0}
    return {"issues": promptwriter.lint(text, ctx), "limit": ctx["limit"], "seconds": ctx["seconds"]}


def prompt_write(d: str, shot_id: str, intent: str, provider: str = "", model: str = "") -> dict:
    from . import promptwriter
    return promptwriter.write(d, shot_id, intent, prompt_limit(d, provider, model) if model else 0)


def prompt_recipes(d: str, shot_id: str) -> list[dict]:
    from . import promptwriter
    from .planio import find_shot, load_plan
    return promptwriter.recipes(find_shot(load_plan(d)[1], shot_id)[0])


def prompt_preview(d: str, shot_id: str, provider: str, model: str, data: dict) -> dict:
    """The words that would really be sent for this take (nothing is sent; free): the prompt, how long it is, and anything that was left out to fit."""
    from . import render
    ov = {}
    if data.get("text") and data.get("mode") == "mine":
        ov["_prompt"], ov["_prompt_only"] = str(data["text"])[:PROMPT_MAX], bool(data.get("only"))
    if data.get("note"):
        ov["_note"] = str(data["note"])[:600]
    if data.get("refs_only"):
        ov["_refs_only"] = True
    r = render.preview(d, shot_id, provider, model, ov, "video")
    man = r["manifest"]
    text = str((r["payload"] or {}).get((man.get("roles") or {}).get("prompt", "prompt")) or "")
    blocks = r.get("prompt_blocks") or []
    return {"prompt": text, "chars": len(text.encode("utf-8")), "limit": prompt_limit(d, provider, model), "left_out": [b["text"][:90] for b in blocks if not b.get("kept")]}


def models(d: str, provider: str, refresh: bool = False) -> dict:
    """The models for each way of composing, for the pickers: end-frame models, reference models, motion models. Kie.ai's lists; cached."""
    from . import render
    video = render.catalog(provider, "video", refresh)
    return {"start_end": [m for m in video if _takes_end(provider, m["model"])], "references": [m for m in video if REFS_RX.search(m["model"])],
            "motion": render.catalog(provider, "motion", refresh)}


def _takes_end(provider: str, model: str) -> bool:
    """Whether a model takes a first AND a last frame, from its own cached schema only (never fetched here, so listing is quick; an unread model is simply not listed)."""
    from . import frames, render
    path = os.path.join(render.CACHE_DIR, f"{provider}__{re.sub(r'[^A-Za-z0-9._-]+', '_', model)}.json")
    m = _read(path)
    if not m or "inputs" not in m:
        return (provider, model) in frames.PROVEN_END or model in KNOWN_END
    try:
        return bool(render._finish(m["provider"], m["model"], m["title"], m.get("category", ""), m["inputs"])["caps"].get("last_frame"))
    except Exception:
        return False


# Kie models documented to take a first and a last frame (docs/END_FRAMES.md), for models whose schema is not saved on this computer yet.
KNOWN_END = {"bytedance/seedance-2", "bytedance/seedance-2-fast", "bytedance/seedance-2-mini", "bytedance/seedance-2-5", "kling-3.0/video", "kling/kling-3-0", "hailuo/02-image-to-video-standard",
             "hailuo/02-image-to-video-pro", "kling/v2-1-pro", "kling/v2-5-turbo-image-to-video-pro", "wan/3-0-video", "minimax-h3/image-to-video"}


def queue_motion(d: str, shot_id: str, provider: str, model: str) -> list[dict]:
    from . import render
    st = state(d, shot_id)
    if not st["ready"]:
        raise SystemExit("Still needed: " + " and ".join(st["missing"]) + ".")
    motion = {"video": st["video"], "image": st["image"], "orientation": st["orientation"], "quality": st["quality"], "background": st["background"], "note": st["note"]}
    return render.enqueue(d, [shot_id], provider, model, {"_motion": motion}, [], "video")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-compose")
    ap.add_argument("action", choices=["state", "set_motion", "clear_motion", "models", "queue_motion", "library_list", "library_add", "library_rename", "library_remove", "library_restore", "library_use", "library_tag", "library_export", "library_import", "prompt_set", "prompt_write", "prompt_lint", "prompt_recipes", "prompt_preview"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        res = state(a.project, x["shot"]) if a.action == "state" else set_motion(a.project, x["shot"], x) if a.action == "set_motion" else \
            clear_motion(a.project, x["shot"]) if a.action == "clear_motion" else models(a.project, x.get("provider", "kie"), bool(x.get("refresh"))) if a.action == "models" else \
            lib_list() if a.action == "library_list" else (lib_add_from_shot(a.project, x["shot"], x.get("name")) if x.get("shot") and not x.get("path") else lib_add(x.get("path", ""), x.get("name"))) if a.action == "library_add" else \
            lib_rename(x.get("id", ""), x.get("name", "")) if a.action == "library_rename" else lib_tag(x.get("id", ""), x.get("tags")) if a.action == "library_tag" else \
            lib_export(x.get("path", ""), x.get("ids")) if a.action == "library_export" else lib_import(x.get("path", "")) if a.action == "library_import" else lib_remove(x.get("id", "")) if a.action == "library_remove" else lib_restore(x.get("id", "")) if a.action == "library_restore" else lib_use(a.project, x["shot"], x.get("id", "")) if a.action == "library_use" else \
            prompt_set(a.project, x["shot"], x) if a.action == "prompt_set" else prompt_write(a.project, x["shot"], x.get("intent", ""), x.get("provider", ""), x.get("model", "")) if a.action == "prompt_write" else \
            prompt_lint(a.project, x["shot"], x.get("text", ""), x.get("provider", ""), x.get("model", "")) if a.action == "prompt_lint" else prompt_recipes(a.project, x["shot"]) if a.action == "prompt_recipes" else \
            prompt_preview(a.project, x["shot"], x["provider"], x["model"], x) if a.action == "prompt_preview" else queue_motion(a.project, x["shot"], x["provider"], x["model"])
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
