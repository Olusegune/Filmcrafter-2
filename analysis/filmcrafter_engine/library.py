"""Reference library, shot versions and storyboard thumbnails.

Library (project.json "library", schema_version 2):
  items:   [{id, kind, name, files: [relpath], notes}]   kind: character | set | prop | wardrobe | lighting | style | video | audio
  assign:  {"project": [ids], "scenes": {"3": {"add": [ids], "remove": [ids]}}, "shots": {"S03-02": {"add": [], "remove": []}}}
A shot's references = project items, plus/minus its scene's changes, plus/minus its own. Characters are also
included automatically when they perform in the shot. The legacy "references" block is migrated once and kept.

Versions (shots.json): {shot_id: {"approved": job_id | None, "locked": bool}}. Regenerating never replaces
the approved take; a new take is only used after it is approved.
"""
from __future__ import annotations

import argparse
import hashlib
from .safe import sha1 as _sha1
import json
import os
import subprocess
import sys
import time
import uuid

from .shothistory import tracked

KINDS = ["character", "set", "prop", "wardrobe", "lighting", "style", "video", "audio"]
# order references are sent in when a model takes fewer than we have
PRIORITY = {"character": 0, "wardrobe": 1, "set": 2, "prop": 3, "lighting": 4, "style": 5, "video": 6, "audio": 7}
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif", ".jfif", ".ico", ".svg")
VIDEO_EXT = (".mp4", ".mov", ".webm", ".mkv", ".m4v")
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")
ACTIVE = ("queued", "submitting", "submitted")


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):   # the app went away: nobody to tell
        pass


def _read(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path: str, data) -> None:
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    for i in range(40):  # Windows: the target may be open in another process for a moment
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05 * (i + 1) if i < 10 else 0.5)
    os.replace(tmp, path)


def media_kind(path: str) -> str:
    """image, video or audio; anything else (a written spec, a PDF, a JSON file) is a "document" and is never sent as a reference."""
    e = os.path.splitext(path)[1].lower()
    return "video" if e in VIDEO_EXT else "audio" if e in AUDIO_EXT else "image" if e in IMAGE_EXT else "document"


# ---------------------------------------------------------------- library

def migrate(project: dict) -> dict:
    """Build the library from the older single-slot references. Idempotent; never deletes old data."""
    if isinstance(project.get("library"), dict):
        return project["library"]
    refs = project.get("references") or {}
    items = []
    for name, path in (refs.get("cast") or {}).items():
        items.append({"id": "c_" + _sha1(name.encode()).hexdigest()[:8], "kind": "character", "name": name,
                      "files": [path], "notes": ""})
    if refs.get("characters"):
        items.append({"id": "sheet_characters", "kind": "character", "name": "Character sheet", "files": [refs["characters"]],
                      "notes": "Combined sheet: used only when a performer has no image of their own.", "sheet": True})
    if refs.get("sets"):
        items.append({"id": "sheet_sets", "kind": "set", "name": "Sets and props sheet", "files": [refs["sets"]], "notes": "",
                      "sheet": True})
    lib = {"items": items, "assign": {"project": [i["id"] for i in items if i["kind"] != "character"], "scenes": {}, "shots": {}}}
    project["library"] = lib
    project["schema_version"] = max(2, project.get("schema_version") or 1)
    return lib


def sync_legacy(project: dict, lib: dict) -> bool:
    """Materials (the simple checklist) still writes the older slots; bring new ones into the library."""
    refs = project.get("references") or {}
    changed = False
    known = {f for i in lib["items"] for f in i.get("files") or []}
    for name, path in (refs.get("cast") or {}).items():
        if path in known:
            continue
        hit = next((i for i in lib["items"] if i["kind"] == "character" and i["name"].lower() == name.lower()), None)
        if hit:
            hit["files"] = [path]
        else:
            lib["items"].append({"id": "c_" + _sha1(name.encode()).hexdigest()[:8], "kind": "character",
                                 "name": name, "files": [path], "notes": ""})
        changed = True
    for slot, iid, kind, name in (("characters", "sheet_characters", "character", "Character sheet"),
                                  ("sets", "sheet_sets", "set", "Sets and props sheet")):
        path = refs.get(slot)
        if not path or path in known:
            continue
        hit = next((i for i in lib["items"] if i["id"] == iid), None)
        if hit:
            hit["files"] = [path]
        else:
            lib["items"].append({"id": iid, "kind": kind, "name": name, "files": [path], "notes": "", "sheet": True})
            if kind != "character":
                lib["assign"].setdefault("project", []).append(iid)
        changed = True
    return changed


def _mark_sheets(lib: dict) -> bool:
    """Combined sheets are collages: models copy their panels into single frames, so keyframes never get them."""
    changed = False
    for i in lib["items"]:
        if i["id"] in ("sheet_characters", "sheet_sets") and not i.get("sheet"):
            i["sheet"] = True
            changed = True
    return changed


def load(d: str) -> tuple[dict, dict]:
    p = _read(os.path.join(d, "project.json"), {})
    had = isinstance(p.get("library"), dict)
    lib = migrate(p)
    fixed = _mark_sheets(lib)
    if not had or sync_legacy(p, lib) or fixed:
        _write(os.path.join(d, "project.json"), p)
    return p, lib


def _apply(ids: list[str], change: dict | None) -> list[str]:
    change = change or {}
    out = [i for i in ids if i not in (change.get("remove") or [])]
    return out + [i for i in (change.get("add") or []) if i not in out]


def shot_items(lib: dict, shot: dict, scene_number) -> list[dict]:
    """Effective reference items for a shot, in send-priority order, each tagged with where it came from."""
    by_id = {i["id"]: i for i in lib.get("items", [])}
    a = lib.get("assign") or {}
    ids = list(a.get("project") or [])
    source = {i: "project" for i in ids}
    sc = (a.get("scenes") or {}).get(str(scene_number))
    ids = _apply(ids, sc)
    for i in (sc or {}).get("add") or []:
        source[i] = "scene"
    sh = (a.get("shots") or {}).get(shot["id"])
    ids = _apply(ids, sh)
    for i in (sh or {}).get("add") or []:
        source[i] = "shot"
    removed = set((sh or {}).get("remove") or []) | set((sc or {}).get("remove") or [])
    # performers bring their own character reference
    performers = [n.lower() for n in shot.get("performers") or []]
    for it in lib.get("items", []):
        if it["kind"] == "character" and not it.get("sheet") and it["name"].lower() in performers \
                and it["id"] not in ids and it["id"] not in removed:
            ids.append(it["id"])
            source[it["id"]] = "performer"
    chosen = [by_id[i] for i in ids if i in by_id]
    has_own = any(c["kind"] == "character" and not c.get("sheet") for c in chosen)
    if not has_own and performers and "sheet_characters" in by_id and "sheet_characters" not in removed \
            and "sheet_characters" not in ids:
        chosen.append(by_id["sheet_characters"])
        source["sheet_characters"] = "performer"
    if has_own:
        chosen = [c for c in chosen if not c.get("sheet") or c["kind"] != "character"]
    chosen.sort(key=lambda c: PRIORITY.get(c["kind"], 9))
    return [{**c, "from": source.get(c["id"], "project")} for c in chosen]


LABELS = {"character": "reference for {name} (face, expressions, full-body turnaround)",
          "set": "set / location reference: {name}", "prop": "prop reference: {name}",
          "wardrobe": "wardrobe reference: {name}", "lighting": "lighting reference: {name}",
          "style": "style reference: {name}", "video": "motion reference: {name}", "audio": "audio reference: {name}"}


def reference_files(d: str, project: dict, shot: dict | None, scene_number=None) -> list[dict]:
    """Files to send for a shot: [{label, path, kind, media}] — the render engine's single source of references."""
    project = json.loads(json.dumps(project))
    lib = migrate(project)
    sync_legacy(project, lib)
    _mark_sheets(lib)
    shot = shot or {"id": "", "performers": []}
    out, seen = [], {}
    for it in shot_items(lib, shot, scene_number if scene_number is not None else shot.get("scene")):
        label = LABELS.get(it["kind"], "{name}").format(name=it["name"])
        if it.get("sheet"):
            label = "character sheet (faces, turnarounds, outfits)" if it["kind"] == "character" else \
                "set and props sheet (locations, props, colour palette)"
        if it.get("notes"):
            label += f" — {it['notes'][:120]}"
        for f in it.get("files") or []:
            path = os.path.join(d, f)
            if not (os.path.exists(path) and media_kind(f) != "document"):
                continue
            at = seen.get(os.path.normcase(path))
            if at is not None:      # one picture shared by several people (a cast lineup): send it once, naming everyone it is for
                first = out[at]
                if first["kind"] == "character" and it["kind"] == "character" and not first.get("sheet") and it["name"] not in first["names"]:
                    first["names"].append(it["name"])
                    first["label"] = LABELS["character"].format(name=", ".join(first["names"])) + first["label"][len(LABELS["character"].format(name=", ".join(first["names"][:-1]))):]
                continue
            seen[os.path.normcase(path)] = len(out)
            out.append({"label": label, "path": path, "kind": it["kind"], "media": media_kind(f), "sheet": bool(it.get("sheet")), "names": [it["name"]]})
    return out


def fit_to_model(refs: list[dict], limits: dict) -> tuple[list[dict], list[str]]:
    """Keep what the model can take (limits: {"image": n, "video": n, "audio": n}); report what was dropped."""
    kept, dropped, used = [], [], {}
    for r in refs:
        m = r.get("media", "image")
        cap = limits.get(m, 0)
        if used.get(m, 0) < cap:
            kept.append(r)
            used[m] = used.get(m, 0) + 1
        else:
            dropped.append(r["label"].split(" — ")[0])
    return kept, dropped


def save_library(d: str, p: dict, lib: dict) -> dict:
    p["library"] = lib
    _write(os.path.join(d, "project.json"), p)
    return lib


def upsert(d: str, item: dict) -> dict:
    p, lib = load(d)
    if item.get("kind") not in KINDS:
        raise SystemExit("Choose what kind of reference this is.")
    if not (item.get("name") or "").strip():
        raise SystemExit("Give the reference a name.")
    item = {k: item.get(k) for k in ("id", "kind", "name", "files", "notes") if item.get(k) is not None}
    item["name"] = item["name"].strip()
    item["files"] = [f for f in item.get("files") or [] if os.path.exists(os.path.join(d, f))]
    existing = next((i for i in lib["items"] if i["id"] == item.get("id")), None)
    if existing:
        existing.update(item)
    else:
        item["id"] = item.get("id") or uuid.uuid4().hex[:10]
        lib["items"].append(item)
        if item["kind"] != "character":  # characters join shots they perform in; everything else starts project-wide
            lib["assign"].setdefault("project", []).append(item["id"])
    return save_library(d, p, lib)


def delete(d: str, item_id: str) -> dict:
    p, lib = load(d)
    lib["items"] = [i for i in lib["items"] if i["id"] != item_id]
    a = lib["assign"]
    a["project"] = [i for i in a.get("project", []) if i != item_id]
    for scope in ("scenes", "shots"):
        for ch in (a.get(scope) or {}).values():
            for k in ("add", "remove"):
                ch[k] = [i for i in ch.get(k, []) if i != item_id]
    return save_library(d, p, lib)


def assign(d: str, scope: str, key: str | None, item_id: str, on: bool) -> dict:
    """Turn a reference on or off at project, scene or shot level (scene/shot record overrides)."""
    p, lib = load(d)
    a = lib["assign"]
    if scope == "project":
        ids = a.setdefault("project", [])
        if on and item_id not in ids:
            ids.append(item_id)
        if not on and item_id in ids:
            ids.remove(item_id)
    else:
        ch = a.setdefault(scope + "s", {}).setdefault(str(key), {"add": [], "remove": []})
        add, rem = ch.setdefault("add", []), ch.setdefault("remove", [])
        for lst in (add, rem):
            if item_id in lst:
                lst.remove(item_id)
        (add if on else rem).append(item_id)
    return save_library(d, p, lib)


def reset(d: str, scope: str, key: str, item_id: str) -> dict:
    """Drop a scene/shot override so the item inherits again."""
    p, lib = load(d)
    ch = (lib["assign"].get(scope + "s") or {}).get(str(key))
    if ch:
        for k in ("add", "remove"):
            ch[k] = [i for i in ch.get(k, []) if i != item_id]
    return save_library(d, p, lib)


# ---------------------------------------------------------------- versions and status

def _plan(d: str) -> tuple[str, dict]:
    name = "directed" if os.path.exists(os.path.join(d, "directed.json")) else "production"
    return name, _read(os.path.join(d, f"{name}.json"), {"scenes": []})


def shot_state(d: str) -> dict:
    return _read(os.path.join(d, "shots.json"), {})


def set_shot(d: str, shot_id: str, **kw) -> dict:
    s = shot_state(d)
    s.setdefault(shot_id, {}).update(kw)
    _write(os.path.join(d, "shots.json"), s)
    return s[shot_id]


def _plan_shot_ids(d: str) -> list[str]:
    try:
        return [s["id"] for sc in _plan(d)[1]["scenes"] for s in sc["shots"]]
    except (OSError, KeyError, ValueError, TypeError):
        return []


@tracked("Approve take", lambda d, shot_id, *a, **k: [shot_id])
def approve(d: str, shot_id: str, job_id: str | None) -> dict:
    if shot_state(d).get(shot_id, {}).get("locked"):
        raise SystemExit(f"{shot_id} is locked. Unlock it to change the approved take.")
    if job_id:
        jobs = _read(os.path.join(d, "jobs.json"), {"jobs": []})["jobs"]
        j = next((x for x in jobs if x["id"] == job_id), None)
        if not j or j["state"] != "ready" or j["shot_id"] != shot_id or j.get("kind", "video") == "image":
            raise SystemExit("Only a finished video take of this shot can be approved.")
    return set_shot(d, shot_id, approved=job_id, approved_at=int(time.time()))


@tracked("Lock or unlock shot", lambda d, shot_id, *a, **k: [shot_id])
def lock(d: str, shot_id: str, on: bool = True) -> dict:
    return set_shot(d, shot_id, locked=bool(on))


def chosen_take(d: str, shot_id: str, plan_name: str, jobs: list[dict], state: dict | None = None) -> dict | None:
    """The take the video uses: the approved one; if none approved yet, the latest finished take."""
    st = (state if state is not None else shot_state(d)).get(shot_id, {})
    takes = [j for j in jobs if j["shot_id"] == shot_id and j["plan"] == plan_name and j["state"] == "ready"
             and j.get("output") and j.get("kind", "video") != "image" and os.path.exists(os.path.join(d, j["output"]))]
    if st.get("approved"):
        hit = next((j for j in takes if j["id"] == st["approved"]), None)
        if hit:
            return hit
    return max(takes, key=lambda j: j["created"], default=None)


def pending_keyframes(d: str, shots: list[str] | None = None) -> dict:
    """Newest finished keyframe for each shot that has none approved yet: {shot_id: project-relative image}."""
    plan_name, plan = _plan(d)
    ids = shots or [s["id"] for sc in plan["scenes"] for s in sc["shots"]]
    kfs = (_read(os.path.join(d, "keyframes.json"), {}) or {}).get(plan_name, {})
    jobs = _read(os.path.join(d, "jobs.json"), {"jobs": []})["jobs"]
    out = {}
    for sid in ids:
        if kfs.get(sid) or shot_state(d).get(sid, {}).get("locked"):
            continue
        imgs = [j for j in jobs if j["shot_id"] == sid and j["plan"] == plan_name and j.get("kind") == "image" and not j.get("rejected")
                and j.get("frame", "start") != "end"
                and j["state"] == "ready" and j.get("output") and os.path.exists(os.path.join(d, j["output"]))]
        if imgs:   # a still that passed the keyframe check beats a newer one that failed it
            rank = lambda j: ({True: 2, None: 1, False: 0}[(j.get("still_check") or {}).get("ok")], j["created"])
            out[sid] = max(imgs, key=rank)["output"]
    return out


@tracked("Approve keyframes", lambda d, shots=None, **k: list(shots) if shots else _plan_shot_ids(d))
def approve_keyframes(d: str, shots: list[str] | None = None) -> dict:
    """Approve the newest keyframe for every shot that has none yet. Never replaces an approved keyframe."""
    plan_name, _ = _plan(d)
    todo = pending_keyframes(d, shots)
    path = os.path.join(d, "keyframes.json")
    kf = _read(path, {}) or {}
    kf.setdefault(plan_name, {}).update({sid: "project:" + rel for sid, rel in todo.items()})
    _write(path, kf)
    return {"approved": sorted(todo)}


def keyframe_options(d: str, shots: list[str]) -> dict:
    """Every keyframe made for these shots, to choose from: {shot: {chosen, options: [...], active}}. Newest first."""
    plan_name, _ = _plan(d)
    kfs = (_read(os.path.join(d, "keyframes.json"), {}) or {}).get(plan_name, {})
    jobs = _read(os.path.join(d, "jobs.json"), {"jobs": []})["jobs"]
    out = {}
    for sid in shots:
        mine = [j for j in jobs if j["shot_id"] == sid and j["plan"] == plan_name and j.get("kind") == "image"
                and j.get("frame", "start") != "end"]
        opts = [{"job": j["id"], "image": j["output"], "model": j["model"], "provider": j["provider"], "created": j["created"],
                 "rejected": bool(j.get("rejected")), "check": (j.get("still_check") or {}).get("ok")}
                for j in mine if j["state"] == "ready" and j.get("output") and os.path.exists(os.path.join(d, j["output"]))]
        chosen = (kfs.get(sid) or "").removeprefix("project:") or None
        out[sid] = {"chosen": chosen, "options": sorted(opts, key=lambda o: -o["created"]),
                    "active": sum(1 for j in mine if j["state"] in ("queued", "submitting", "submitted")),
                    "failed": sum(1 for j in mine if j["state"] in ("failed", "uncertain"))}
    return out


@tracked("Choose keyframe", lambda d, shot_id, *a, **k: [shot_id])
def choose_keyframe(d: str, shot_id: str, job_id: str) -> dict:
    """Make this still the shot's keyframe (where its video starts). The earlier choice stays among the options."""
    if shot_state(d).get(shot_id, {}).get("locked"):
        raise SystemExit(f"{shot_id} is locked. Unlock it to change its keyframe.")
    plan_name, _ = _plan(d)
    jobs = _read(os.path.join(d, "jobs.json"), {"jobs": []})["jobs"]
    j = next((x for x in jobs if x["id"] == job_id and x["shot_id"] == shot_id and x.get("kind") == "image" and x["state"] == "ready"), None)
    if not j or not j.get("output"):
        raise SystemExit("Choose a finished keyframe of this shot.")
    path = os.path.join(d, "keyframes.json")
    kf = _read(path, {}) or {}
    kf.setdefault(plan_name, {})[shot_id] = "project:" + j["output"]
    _write(path, kf)
    set_keyframe_flag(d, job_id, rejected=False)
    return {"shot": shot_id, "keyframe": j["output"]}


def set_keyframe_flag(d: str, job_id: str, rejected: bool) -> dict:
    """Reject (or restore) one keyframe option. Nothing is deleted; a rejected still is only hidden from automatic picks."""
    path = os.path.join(d, "jobs.json")
    data = _read(path, {"jobs": []})
    j = next((x for x in data["jobs"] if x["id"] == job_id), None)
    if not j:
        raise SystemExit("That keyframe no longer exists.")
    j["rejected"] = rejected
    _write(path, data)
    return {"job": job_id, "rejected": rejected}


def _status(st: dict, takes: list[dict], images: list[dict]) -> str:
    if st.get("locked"):
        return "locked"
    if any(j["state"] in ("submitting", "submitted") for j in takes + images):
        return "generating"
    if any(j["state"] == "queued" for j in takes + images):
        return "queued"
    ready = [j for j in takes if j["state"] == "ready"]
    if st.get("approved") and any(j["id"] == st["approved"] for j in ready):
        # only takes that finished after the choice was made still need a look
        newer = [j for j in ready if j["id"] != st["approved"] and (j.get("finished") or j["created"]) > (st.get("approved_at") or 0)]
        return "needs_review" if newer else "ready"
    if ready:
        return "needs_review"
    latest = max(takes, key=lambda j: j["created"], default=None)
    if latest and latest["state"] in ("failed", "uncertain"):
        return "failed"
    return "planned"


# ---------------------------------------------------------------- thumbnails

def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def thumbnail(d: str, src_rel: str, at: float | None = None, width: int = 480) -> str | None:
    """Cached JPEG for an image or video (frame from the middle of a video). Returns project-relative path."""
    src = os.path.join(d, src_rel)
    if not os.path.exists(src):
        return None
    st = os.stat(src)
    key = _sha1(f"{src_rel}|{st.st_size}|{int(st.st_mtime)}|{at}|{width}".encode()).hexdigest()[:16]
    rel = f"thumbnails/{key}.jpg"
    out = os.path.join(d, rel)
    if os.path.exists(out):
        return rel
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if media_kind(src_rel) == "video":
        t = at if at is not None else 1.0
        args = [_ffmpeg(), "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1",
                "-vf", f"scale={width}:-2", "-q:v", "4", out]
        flags = 0x08000000 if os.name == "nt" else 0
        r = subprocess.run(args, capture_output=True, creationflags=flags)
        if r.returncode != 0 or not os.path.exists(out):
            return None
    else:
        from PIL import Image
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((width, width * 2))
            im.save(out, quality=82)
    return rel


def _duration(path: str) -> float | None:
    try:
        r = subprocess.run([_ffmpeg(), "-i", path], capture_output=True, text=True,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        import re
        m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None
    except OSError:
        return None


def _drift(project: dict, shot: dict):
    from .performance import drift_for
    return drift_for(project, shot)


def storyboard(d: str) -> dict:
    """Every shot with its status, thumbnail source, versions and references. Thumbnails are made on demand and cached."""
    plan_name, plan = _plan(d)
    jobs = _read(os.path.join(d, "jobs.json"), {"jobs": []})["jobs"]
    state = shot_state(d)
    kfs = (_read(os.path.join(d, "keyframes.json"), {}) or {}).get(plan_name, {})
    p, lib = load(d)
    story = (p.get("references") or {}).get("storyboard") or {}
    from .keyframeset import check_state, checks
    saved = checks(d)
    shots = []
    for sc in plan.get("scenes", []):
        for sh in sc.get("shots", []):
            sid = sh["id"]
            mine = [j for j in jobs if j["shot_id"] == sid and j["plan"] == plan_name and j["state"] != "dismissed"]
            takes = sorted([j for j in mine if j.get("kind", "video") != "image"], key=lambda j: j["created"])
            images = [j for j in mine if j.get("kind") == "image"]
            st = state.get(sid, {})
            chosen = chosen_take(d, sid, plan_name, jobs, state)
            kf = kfs.get(sid)
            kf_rel = kf[len("project:"):] if isinstance(kf, str) and kf.startswith("project:") else None
            thumb, source = None, "placeholder"
            if chosen:
                thumb, source = chosen["output"], "render"
            elif kf_rel and os.path.exists(os.path.join(d, kf_rel)):
                thumb, source = kf_rel, "keyframe"
            elif story.get(sid) and os.path.exists(os.path.join(d, story[sid])):
                thumb, source = story[sid], "storyboard"
            kf_job = next((j for j in sorted(images, key=lambda j: -j["created"]) if kf_rel and j.get("output") == kf_rel and j["state"] == "ready"), None)
            kf_check = check_state(saved.get(kf_rel) if kf_rel and saved.get(kf_rel) is not None else (kf_job or {}).get("still_check"))
            versions = [{"id": j["id"], "n": i + 1, "state": j["state"], "provider": j["provider"], "model": j["model"],
                         "output": j.get("output"), "kind": j.get("kind", "video"), "created": j["created"],
                         "error": j.get("error"), "error_kind": j.get("error_kind"), "cost": j.get("cost"),
                         "cost_unit": j.get("cost_unit"), "approved": st.get("approved") == j["id"],
                         "review": j.get("review"), "media_kind": j.get("media_kind"), "motion": j.get("motion")}
                        for i, j in enumerate(takes)]
            shots.append({
                "id": sid, "scene": sc.get("number"), "heading": sc.get("heading"), "start": sh["start"], "end": sh["end"],
                "framing": sh.get("framing"), "beat": " ".join(sh.get("beats") or [])[:220], "performers": sh.get("performers") or [],
                "status": _status(st, takes, images), "locked": bool(st.get("locked")), "approved": st.get("approved"), "end_mode": st.get("end_mode", "none"),
                "thumb_src": thumb, "thumb_source": source, "preview": chosen["output"] if chosen else None,
                "keyframe": kf_rel, "keyframe_check": kf_check, "keyframe_model": (kf_job or {}).get("model"), "versions": versions, "transition": st.get("transition", "cut"), "transition_s": st.get("transition_s"),
                "preview_kind": (chosen.get("media_kind") or "video") if chosen else None,
                "preview_motion": chosen.get("motion") if chosen else None,
                "preview_drift": _drift(p, {**sh, "scene": sh.get("scene", sc.get("number"))}) if chosen and chosen.get("media_kind") == "image" else None,
                "references": [{"id": i["id"], "kind": i["kind"], "name": i["name"], "from": i["from"]}
                               for i in shot_items(lib, sh, sc.get("number"))],
            })
    return {"plan": plan_name, "shots": shots, "library": lib}


def thumbs(d: str, srcs: list[str]) -> dict:
    """Make (or reuse) thumbnails for the given project files; {src: thumb_rel | None}."""
    out = {}
    for s in srcs:
        try:
            out[s] = thumbnail(d, s)
        except Exception:
            out[s] = None
    return out


BIBLE_FIELDS = ("world", "rules", "palette", "avoid")


def bible(d: str, new: dict | None = None) -> dict:
    """Production Bible basics: the world, its rules, the palette and what never appears. Every shot's prompt carries them."""
    path = os.path.join(d, "project.json")
    p = _read(path, {})
    b = {k: str((p.get("bible") or {}).get(k) or "") for k in BIBLE_FIELDS}
    if new is not None:
        b.update({k: str(new[k]).strip()[:1500] for k in BIBLE_FIELDS if k in new})
        p = _read(path, {})   # re-read: keep everything else as it is on disk
        p["bible"] = b
        _write(path, p)
    return b


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-library")
    ap.add_argument("action", choices=["storyboard", "thumbs", "library", "upsert", "delete", "assign", "reset",
                                       "approve", "approve_latest", "lock", "shot_refs",
                                       "pending_keyframes", "approve_keyframes", "bible",
                                       "keyframe_options", "choose_keyframe", "reject_keyframe"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    data = json.loads(a.data)
    d = a.project
    try:
        if a.action == "storyboard":
            res = storyboard(d)
        elif a.action == "bible":
            res = bible(d, data.get("bible"))
        elif a.action == "thumbs":
            res = thumbs(d, data.get("srcs") or [])
        elif a.action == "library":
            res = load(d)[1]
        elif a.action == "upsert":
            res = upsert(d, data)
        elif a.action == "delete":
            res = delete(d, data["id"])
        elif a.action == "assign":
            res = assign(d, data["scope"], data.get("key"), data["id"], bool(data.get("on", True)))
        elif a.action == "reset":
            res = reset(d, data["scope"], data["key"], data["id"])
        elif a.action == "approve":
            res = approve(d, data["shot"], data.get("job"))
        elif a.action == "approve_latest":  # Director Command: "use the latest version of the chorus"
            plan_name, _ = _plan(d)
            jobs = _read(os.path.join(d, "jobs.json"), {"jobs": []})["jobs"]
            res = {}
            for sid in data["shots"]:
                takes = [j for j in jobs if j["shot_id"] == sid and j["plan"] == plan_name and j["state"] == "ready"
                         and j.get("output") and j.get("kind", "video") != "image"]
                if takes and not shot_state(d).get(sid, {}).get("locked"):
                    res[sid] = approve(d, sid, max(takes, key=lambda j: j["created"])["id"])["approved"]
        elif a.action == "pending_keyframes":
            res = pending_keyframes(d, data.get("shots"))
        elif a.action == "approve_keyframes":
            res = approve_keyframes(d, data.get("shots"))
        elif a.action == "keyframe_options":
            res = keyframe_options(d, data.get("shots") or [])
        elif a.action == "choose_keyframe":
            res = choose_keyframe(d, data["shot"], data["job"])
        elif a.action == "reject_keyframe":
            res = set_keyframe_flag(d, data["job"], bool(data.get("on", True)))
        elif a.action == "lock":
            res = lock(d, data["shot"], bool(data.get("on", True)))
        else:
            p, lib = load(d)
            name, plan = _plan(d)
            sh, sc = next(((s, c) for c in plan["scenes"] for s in c["shots"] if s["id"] == data["shot"]), (None, None))
            if not sh:
                raise SystemExit("Shot not found.")
            res = shot_items(lib, sh, sc.get("number"))
        emit(event="result", data=res)
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=f"{type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
