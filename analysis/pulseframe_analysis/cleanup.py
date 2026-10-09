"""Clean up a project: find the videos and pictures nothing uses any more, move them to a trash folder inside the project, restore them, or empty it.

Only files in the project's `generations` folder are ever considered, and only files that are in none of these: the take each shot uses (the approved
one, or the latest while none is approved), an approved keyframe, a finished or running job's output, anything named in the project's settings files
(references, overlays, library, shots), anything made in the last ten minutes. The list is worked out again by the engine at the moment of removal, so
what the screen showed earlier is never trusted. Removing is two steps: files first go to `trash/<batch>/` and can be put back; only **empty** deletes
them for good. Nothing is removed while a render is running.

  python -m pulseframe_analysis.cleanup <scan|discard|restore|empty> <project> --data '{"paths": [...]}'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import uuid

GEN = "generations"
TRASH = "trash"
VIDEO_EXT = (".mp4", ".mov", ".webm", ".m4v")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
AUDIO_EXT = (".mp3", ".wav", ".m4a")
KNOWN_EXT = VIDEO_EXT + IMAGE_EXT + AUDIO_EXT
RECENT_SECONDS = 600
TERMINAL = ("ready", "failed", "dismissed", "cancelled", "canceled")
BATCH = re.compile(r"^\d{14}-[0-9a-f]{6}$")
MAX_JSON = 8 * 1024 * 1024


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


def _write(path: str, data) -> None:
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    for i in range(40):                     # Windows: the target may be open in another process for a moment
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == 39:
                raise
            time.sleep(0.05)


def _inside(base: str, path: str) -> bool:
    b, p = os.path.normcase(os.path.realpath(base)), os.path.normcase(os.path.realpath(path))
    try:
        return os.path.commonpath([b, p]) == b and p != b
    except ValueError:
        return False


def _rel(d: str, path: str) -> str:
    return os.path.relpath(path, d).replace(os.sep, "/")


def _kind(path: str) -> str:
    e = os.path.splitext(path)[1].lower()
    return "video" if e in VIDEO_EXT else "image" if e in IMAGE_EXT else "audio"


def _plans(d: str) -> list[dict]:
    out = []
    for name in ("directed", "production"):
        p = _read(os.path.join(d, f"{name}.json"))
        if isinstance(p, dict):
            out.append({"name": name, "plan": p})
    return out


def _jobs(d: str) -> list[dict]:
    j = _read(os.path.join(d, "jobs.json"), {"jobs": []})
    return [x for x in (j.get("jobs") if isinstance(j, dict) else []) or [] if isinstance(x, dict)]


def _setting_text(d: str) -> str:
    """The text of the project's settings files (not the job list), to find any file they name."""
    chunks: list[str] = []
    for root, dirs, files in os.walk(d):
        rel = os.path.relpath(root, d)
        top = rel.split(os.sep)[0]
        if top in (GEN, TRASH, "backups", "exports", "thumbnails", "node_modules") or rel.count(os.sep) >= 3:
            dirs[:] = []
            continue
        for f in files:
            if f.lower().endswith(".json") and not (rel == "." and f == "jobs.json"):
                p = os.path.join(root, f)
                try:
                    if os.path.getsize(p) <= MAX_JSON:
                        with open(p, encoding="utf-8", errors="ignore") as fh:
                            chunks.append(fh.read())
                except OSError:
                    pass
    return "\n".join(chunks)


def in_use(d: str, jobs: list[dict]) -> dict[str, str]:
    """{project-relative path: why it stays}."""
    use: dict[str, str] = {}
    try:
        from . import library as L
        state = L.shot_state(d)
        for p in _plans(d):
            for sc in p["plan"].get("scenes", []):
                for s in sc.get("shots", []):
                    t = L.chosen_take(d, s["id"], p["name"], jobs, state)
                    if t and t.get("output"):
                        use[t["output"].replace("\\", "/")] = "used in the video"
                        if t.get("keyframe_ref"):
                            use[str(t["keyframe_ref"]).removeprefix("project:").replace("\\", "/")] = "the picture the used video started from"
    except Exception:
        pass
    kf = _read(os.path.join(d, "keyframes.json"), {}) or {}
    for plan in kf.values():
        for ref in (plan.values() if isinstance(plan, dict) else []):
            if isinstance(ref, str):
                use[ref.removeprefix("project:").replace("\\", "/")] = "an approved keyframe"
    for j in jobs:
        out = str(j.get("output") or "").replace("\\", "/")
        if out and j.get("state") not in TERMINAL:
            use[out] = "still rendering"
    return use


def trash_info(d: str) -> dict:
    root = os.path.join(d, TRASH)
    files = size = batches = 0
    if os.path.isdir(root):
        for b in os.listdir(root):
            m = _read(os.path.join(root, b, "manifest.json"))
            if BATCH.match(b) and isinstance(m, dict):
                batches += 1
                for e in m.get("files", []):
                    files += 1
                    size += int(e.get("size") or 0)
    return {"batches": batches, "files": files, "bytes": size}


def _active(jobs: list[dict]) -> int:
    return sum(1 for j in jobs if j.get("state") not in TERMINAL)


def scan(d: str) -> dict:
    gen = os.path.join(d, GEN)
    jobs = _jobs(d)
    use = in_use(d, jobs)
    named = _setting_text(d)
    by_out = {str(j.get("output") or "").replace("\\", "/"): j for j in jobs if j.get("output")}
    now = time.time()
    items = []
    kept = 0
    if os.path.isdir(gen):
        for root, dirs, files in os.walk(gen, followlinks=False):
            for f in files:
                p = os.path.join(root, f)
                if os.path.islink(p) or os.path.splitext(f)[1].lower() not in KNOWN_EXT or not _inside(gen, p):
                    continue
                rel = _rel(d, p)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if rel in use or f in named or now - st.st_mtime < RECENT_SECONDS:
                    kept += 1
                    continue
                j = by_out.get(rel) or {}
                items.append({"path": rel, "name": f, "kind": _kind(f), "size": st.st_size, "shot": j.get("shot_id"), "model": (j.get("model") or "").split("/")[-1] or None,
                              "created": int(j.get("created") or st.st_mtime), "cost": j.get("cost"), "cost_unit": j.get("cost_unit"),
                              "what": ("a finished take" if _kind(f) == "video" else "a picture") + ("" if j else " not in the render list")})
    items.sort(key=lambda x: (x["kind"], x["shot"] or "", -x["created"]))
    return {"items": items, "bytes": sum(i["size"] for i in items), "kept": kept, "rendering": _active(jobs), "trash": trash_info(d)}


def discard(d: str, paths: list) -> dict:
    """Move these files to a trash batch. Each one is checked again here: it must still be unused, inside generations, and an ordinary file."""
    jobs_all = _read(os.path.join(d, "jobs.json"), {"jobs": []})
    jobs = [x for x in (jobs_all.get("jobs") if isinstance(jobs_all, dict) else []) or [] if isinstance(x, dict)]
    if _active(jobs):
        raise SystemExit("A render is still running. Wait for it to finish, then clean up.")
    if not isinstance(paths, list) or not paths:
        raise SystemExit("Choose what to remove.")
    allowed = {i["path"]: i for i in scan(d)["items"]}
    batch = time.strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
    dest_root = os.path.join(d, TRASH, batch)
    moved, skipped = [], []
    for raw in paths[:5000]:
        rel = str(raw).replace("\\", "/")
        item = allowed.get(rel)
        if not item:
            skipped.append({"path": rel, "why": "it is in use, or no longer there"})
            continue
        src = os.path.join(d, rel)
        dst = os.path.join(dest_root, rel)
        if os.path.islink(src) or not os.path.isfile(src) or not _inside(os.path.join(d, GEN), src):
            skipped.append({"path": rel, "why": "not an ordinary file in the project"})
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            for i in range(10):
                try:
                    os.replace(src, dst)
                    break
                except PermissionError:
                    if i == 9:
                        raise
                    time.sleep(0.1)
        except OSError:
            skipped.append({"path": rel, "why": "another program is using it"})
            continue
        entry = {"path": rel, "size": item["size"], "jobs": []}
        for j in jobs:
            if str(j.get("output") or "").replace("\\", "/") == rel and j.get("state") != "dismissed":
                entry["jobs"].append({"id": j.get("id"), "state": j.get("state")})
                j["state"] = "dismissed"
        moved.append(entry)
    if moved:
        _write(os.path.join(dest_root, "manifest.json"), {"batch": batch, "at": int(time.time()), "files": moved})
        _write(os.path.join(d, "jobs.json"), jobs_all)
    return {"moved": len(moved), "bytes": sum(e["size"] for e in moved), "skipped": skipped, "scan": scan(d)}


def restore(d: str) -> dict:
    """Put every file in the trash back where it came from (a file whose place is taken again is left in the trash)."""
    root = os.path.join(d, TRASH)
    jobs_all = _read(os.path.join(d, "jobs.json"), {"jobs": []})
    jobs = [x for x in (jobs_all.get("jobs") if isinstance(jobs_all, dict) else []) or [] if isinstance(x, dict)]
    back = left = 0
    for b in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        folder = os.path.join(root, b)
        m = _read(os.path.join(folder, "manifest.json"))
        if not BATCH.match(b) or not isinstance(m, dict) or os.path.islink(folder):
            continue
        rest = []
        for e in m.get("files", []):
            rel = str(e.get("path") or "").replace("\\", "/")
            src, dst = os.path.join(folder, rel), os.path.join(d, rel)
            if not (os.path.isfile(src) and _inside(os.path.join(d, GEN), dst)) or os.path.exists(dst):
                rest.append(e)
                left += 1
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(src, dst)
            back += 1
            for jr in e.get("jobs", []):
                for j in jobs:
                    if j.get("id") == jr.get("id") and j.get("state") == "dismissed":
                        j["state"] = jr.get("state") or "ready"
        if rest:
            _write(os.path.join(folder, "manifest.json"), {**m, "files": rest})
        else:
            shutil.rmtree(folder, ignore_errors=True)
    if back:
        _write(os.path.join(d, "jobs.json"), jobs_all)
    return {"restored": back, "left": left, "scan": scan(d)}


def empty(d: str) -> dict:
    """Delete everything in the trash for good. Only batch folders this module made are touched."""
    root = os.path.join(d, TRASH)
    freed = files = 0
    for b in os.listdir(root) if os.path.isdir(root) else []:
        folder = os.path.join(root, b)
        if not BATCH.match(b) or os.path.islink(folder) or not os.path.isdir(folder) or not _inside(root, folder):
            continue
        m = _read(os.path.join(folder, "manifest.json")) or {}
        for e in m.get("files", []):
            files += 1
            freed += int(e.get("size") or 0)
        shutil.rmtree(folder, ignore_errors=True)
    return {"deleted": files, "bytes": freed, "scan": scan(d)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="pulseframe-cleanup")
    ap.add_argument("action", choices=["scan", "discard", "restore", "empty"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "scan":
            res = scan(a.project)
        elif a.action == "discard":
            res = discard(a.project, x.get("paths"))
        elif a.action == "restore":
            res = restore(a.project)
        else:
            res = empty(a.project)
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
