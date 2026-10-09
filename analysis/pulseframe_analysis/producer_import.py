"""Import a PULSEFRAME Producer package (ChatGPT plugin) into a project, using the app's existing structures.

A package is a ZIP, a folder, or a manifest JSON (schema "PULSEFRAME Production Manifest" 1.0) plus the media it names.
Nothing here creates a second workflow: every part lands where the app already keeps it.

  assets.characters/wardrobe/props/environments/references -> Reference library items (files copied into
      assets/producer/; canonical flag and locked/flexible rules kept in full and sent with every shot that uses them)
  continuity.rules / known_exceptions / production_bible   -> Production Bible (Always / World)
  choreography (dance classifications)                     -> choreography sheets + per-section notes for that character
  choreography (acting/performance classifications)        -> the character's acting profile + acting notes
  project.visual_style / aspect_ratio                      -> the project's look notes / frame
  shots                                                    -> the shot plan (production.json), placed on the song by
      their own times when known, else their lyric cue, else their song section, cut on the beat; the plugin's shot id
      is kept as external_id. Shots wait until the song has been analysed ("pending").
  qa + everything missing                                  -> an import report (shown in the Production Supervisor)

  python -m pulseframe_analysis.producer_import <inspect|apply|plan> <package|project> [<package>]
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile

KIND = {"characters": "character", "wardrobe": "wardrobe", "props": "prop", "environments": "set", "references": "style"}
DANCE = re.compile(r"danc|choreo|groove|footwork", re.I)
ACTING_PROFILE = {"restrained": "restrained", "subtle": "restrained", "dramatic": "dramatic", "energetic": "energetic",
                  "expressive": "expressive"}


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data):
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# ---------------------------------------------------------------- reading a package

def _is_manifest(data) -> bool:
    return isinstance(data, dict) and "schema_version" in data and isinstance(data.get("project"), dict) and "assets" in data


MAX_PACKAGE_BYTES, MAX_PACKAGE_FILES = 6 * 1024 ** 3, 20_000


def open_package(path: str) -> tuple[str, str, dict]:
    """-> (package root folder, manifest path, manifest). ZIPs are extracted to a temporary folder."""
    if not os.path.exists(path):
        raise SystemExit("That package can't be found.")
    root = path
    if os.path.isfile(path) and path.lower().endswith((".zip", ".pfproducer")):   # .pfproducer: a Producer ZIP that opens in PULSEFRAME
        root = tempfile.mkdtemp(prefix="pf_producer_")
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            if len(infos) > MAX_PACKAGE_FILES or sum(i.file_size for i in infos) > MAX_PACKAGE_BYTES:      # a "zip bomb": small to send, huge to open
                raise SystemExit("That package is too large to open (more than 6 GB or 20,000 files).")
            base = os.path.realpath(root)
            for n in z.namelist():
                if not os.path.realpath(os.path.join(root, n)).startswith(base + os.sep) and n.strip("/"):
                    raise SystemExit("That package contains an unsafe path and was not opened.")
            z.extractall(root)
    elif os.path.isfile(path):
        data = _read(path)
        if not _is_manifest(data):
            raise SystemExit("That file isn't a PULSEFRAME production manifest (schema_version, project and assets).")
        return os.path.dirname(path), path, data
    found = []
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.lower().endswith(".json") and "schema" not in f.lower():
                data = _read(os.path.join(dirpath, f))
                if _is_manifest(data):
                    found.append((os.path.join(dirpath, f), data))
    if not found:
        raise SystemExit("No production manifest was found in that package.")
    found.sort(key=lambda x: (x[0].count(os.sep), "example" in x[0].lower()))   # prefer the top-level, non-example one
    return root, found[0][0], found[0][1]


def resolve(root: str, manifest_path: str, rel: str | None) -> str | None:
    """A file named in the manifest: relative to the manifest, then to each folder above it up to the package root
    (the plugin's own example writes paths from its skill folder)."""
    if not rel:
        return None
    if os.path.isabs(rel):
        return rel if os.path.exists(rel) else None
    here = os.path.dirname(os.path.abspath(manifest_path))
    top = os.path.abspath(root)
    while True:
        cand = os.path.normpath(os.path.join(here, rel))
        if os.path.exists(cand):
            return cand
        if os.path.normcase(here) == os.path.normcase(top) or os.path.dirname(here) == here:
            break
        here = os.path.dirname(here)
    for dirpath, _, files in os.walk(top):   # last resort: the same file name anywhere in the package
        if os.path.basename(rel) in files:
            return os.path.join(dirpath, os.path.basename(rel))
    return None


VISUAL_KINDS = ("character", "wardrobe", "prop", "environment")


def without_images(m: dict) -> list[dict]:
    """Characters, outfits, props and places that have no picture in the package (only written specs): they reach the prompts as
    words, but a model has nothing to look at for them until an image is added."""
    from .library import media_kind
    allit = {it.get("id"): it for g in KIND for it in (m.get("assets") or {}).get(g) or []}
    out = []
    for group, kind in KIND.items():
        for it in (m.get("assets") or {}).get(group) or []:
            if (it.get("kind") or kind) not in VISUAL_KINDS or any(media_kind(f) == "image" for f in it.get("files") or []):
                continue
            owner = allit.get(it.get("owner_character_id"))
            if kind == "wardrobe" and owner and any(media_kind(f) == "image" for f in owner.get("files") or []) \
                    and set(it.get("files") or []) <= set(owner.get("files") or []):
                continue          # the outfit is drawn on its owner's sheet (the same spec describes both)
            out.append({"name": it.get("name") or it.get("id"), "kind": it.get("kind") or kind})
    return out


MAX_LYRICS = 100_000


def package_lyrics(root: str, mpath: str, m: dict) -> str:
    """The lyrics text a package carries (song.lyrics_file, else a "lyrics" reference), so the song can be aligned to them: a shot's
    lyric cue is placed by finding that line in the analysed lyrics. Plain text only; a PDF is not read."""
    song = m.get("song") or {}
    refs = [song.get("lyrics_file")] + [f for it in (m.get("assets") or {}).get("references") or []
                                        if it.get("kind") == "lyrics" for f in it.get("files") or []]
    for rel in refs:
        p = resolve(root, mpath, rel) if rel else None
        if p and p.lower().endswith((".txt", ".md")) and os.path.getsize(p) <= MAX_LYRICS:
            try:
                text = open(p, encoding="utf-8-sig").read()
            except (OSError, UnicodeDecodeError):
                continue
            # markdown a plugin may add: a "**Style:** ..." line is not a lyric, and **bold** marks are not words
            lines = [re.sub(r"\*\*|__", "", ln) for ln in text.splitlines() if not re.match(r"^\s*\*\*[^*]+:\*\*", ln)]
            return "\n".join(lines).strip() + "\n"
    return ""


def inspect(path: str) -> dict:
    """What a package contains and what is missing, without changing anything."""
    root, mpath, m = open_package(path)
    a = m.get("assets") or {}
    missing, files = [], 0
    for group in KIND:
        for it in a.get(group) or []:
            for f in it.get("files") or []:
                files += 1
                if not resolve(root, mpath, f):
                    missing.append({"asset": it.get("name") or it.get("id"), "file": f})
    for c in m.get("choreography") or []:
        if c.get("visual_sheet") and not resolve(root, mpath, c["visual_sheet"]):
            missing.append({"asset": f"choreography {c.get('id')}", "file": c["visual_sheet"]})
    song = (m.get("song") or {})
    song_file = resolve(root, mpath, song.get("source")) if song.get("source") else None
    return {"title": (m.get("project") or {}).get("title") or "Imported production", "schema_version": m.get("schema_version"),
            "counts": {g: len(a.get(g) or []) for g in KIND} | {"choreography": len(m.get("choreography") or []),
                                                              "shots": len(m.get("shots") or [])},
            "files": files, "missing": missing, "without_images": without_images(m), "song_file": song_file, "song_known": bool(song_file),
            "lyrics_text": package_lyrics(root, mpath, m),
            "shots_with_cues": sum(1 for x in m.get("shots") or [] if x.get("lyric_cue")),
            "readiness": (m.get("qa") or {}).get("readiness"), "qa_report": (m.get("qa") or {}).get("report"),
            "manifest": mpath}


# ---------------------------------------------------------------- applying a package to a project

def _copy(d: str, src: str) -> str:
    dest_dir = os.path.join(d, "assets", "producer")
    os.makedirs(dest_dir, exist_ok=True)
    name = re.sub(r"[^\w.\-]+", "_", os.path.basename(src))
    dest = os.path.join(dest_dir, name)
    if not os.path.exists(dest):
        shutil.copy2(src, dest)
    return f"assets/producer/{name}"


def _text(root, mpath, ref) -> str:
    p = resolve(root, mpath, ref)
    if not p:
        return ""
    if p.lower().endswith((".md", ".txt")):
        try:
            return open(p, encoding="utf-8").read()
        except OSError:
            return ""
    return ""


def apply(d: str, path: str) -> dict:
    """Bring a package into project `d`. Safe to run again: items are updated by their plugin id, not duplicated."""
    from . import library
    root, mpath, m = open_package(path)
    report = {"at": int(time.time()), "package": os.path.basename(path), "missing_files": [], "unknown_refs": [], "without_images": without_images(m),
              "untimed_shots": [], "readiness": (m.get("qa") or {}).get("readiness"), "qa_report": (m.get("qa") or {}).get("report"),
              "imported": {}}
    # keep the manifest with the project (the plan step and later re-imports read it)
    os.makedirs(os.path.join(d, "assets", "producer"), exist_ok=True)
    _write(os.path.join(d, "assets", "producer", "manifest.json"), m)

    # 1. assets -> reference library (by plugin id: re-import updates, never duplicates)
    p, lib = library.load(d)
    by_ext = {i.get("external_id"): i for i in lib["items"] if i.get("external_id")}
    ids = {}   # plugin asset id -> (library id, name, kind, item)
    n = 0
    for group, kind in KIND.items():
        for it in (m.get("assets") or {}).get(group) or []:
            files = []
            for f in it.get("files") or []:
                src = resolve(root, mpath, f)
                if src:
                    files.append(_copy(d, src))
                else:
                    report["missing_files"].append({"asset": it.get("name") or it.get("id"), "file": f})
            k = it.get("kind") if it.get("kind") in library.KINDS else kind
            locked, flexible = it.get("locked_rules") or [], it.get("flexible_rules") or []
            notes = " ".join(x for x in ([f"Locked: {'; '.join(locked)}."] if locked else []) +
                             ([f"May vary: {'; '.join(flexible)}."] if flexible else []) + [it.get("description") or ""] if x).strip()
            item = by_ext.get(it["id"]) or {"id": f"pf_{re.sub(r'[^a-z0-9]+', '_', it['id'].lower())}"[:40]}
            item.update({"kind": k, "name": it.get("name") or it["id"], "files": files or item.get("files") or [], "notes": notes,
                         "external_id": it["id"], "canonical": bool(it.get("canonical")), "locked_rules": locked,
                         "owner": it.get("owner_character_id") or "",
                         "flexible_rules": flexible})
            if item not in lib["items"]:
                lib["items"].append(item)
            ids[it["id"]] = (item["id"], item["name"], k, item)
            n += 1
    library.save_library(d, p, lib)
    report["imported"]["assets"] = n
    try:   # the package's text signs become on-screen text, timed by the song section each one names
        from . import overlays
        report["imported"]["overlays"] = len([o for o in overlays.sync_package(d) if o.get("source") == "package"])
    except Exception:
        pass

    # 2. project: frame, look notes, continuity -> Production Bible
    p = _read(os.path.join(d, "project.json"), {})
    proj = m.get("project") or {}
    if proj.get("aspect_ratio"):
        p["aspect_ratio"] = proj["aspect_ratio"]
    if proj.get("visual_style"):
        look = p.get("look") if isinstance(p.get("look"), dict) else {"style": "auto"}
        look["notes"] = proj["visual_style"]
        p["look"] = look
    cont = m.get("continuity") or {}
    bible = dict(p.get("bible") or {})
    # Only world rules go in the Bible: a character's locked design travels with the shots that character is in
    # (in the Bible it reaches every shot, and models then draw that character into shots they aren't in).
    rules = list(cont.get("rules") or [])
    if rules:
        bible["rules"] = " ".join(r.rstrip(".") + "." for r in rules)[:1500]
    if cont.get("known_exceptions"):
        bible["rules"] = (bible.get("rules", "") + " Exceptions: " + "; ".join(cont["known_exceptions"]) + ".")[:1500]
    world = _text(root, mpath, cont.get("production_bible"))
    if world:
        bible["world"] = re.sub(r"\s+", " ", world)[:1500]
        src = resolve(root, mpath, cont["production_bible"])
        _copy(d, src)
    elif cont.get("production_bible") and not resolve(root, mpath, cont["production_bible"]):
        report["missing_files"].append({"asset": "Production Bible", "file": cont["production_bible"]})
    # the plugin's own bible fields (continuity.world / always / palette / never_show), when a package writes them: each lands in its own
    # Production Bible field, kept short because they travel with every prompt
    clip = lambda text, n: re.sub(r"\s+", " ", str(text)).strip()[:n]
    if cont.get("world"):
        bible["world"] = clip(cont["world"], 800)
    if cont.get("always"):
        bible["rules"] = clip(f"{cont['always']} {bible.get('rules', '')}", 800)
    if cont.get("palette"):
        bible["palette"] = clip(cont["palette"], 600)
    if cont.get("never_show"):
        bible["avoid"] = clip(cont["never_show"], 700)
    for k in ("world", "rules", "palette", "avoid"):
        bible.setdefault(k, "")
    p["bible"] = bible
    p["producer_import"] = report
    p["producer_package"] = os.path.abspath(path)
    _write(os.path.join(d, "project.json"), p)

    # 3. choreography -> dancers: sheets + section notes; everyone else: acting profile + notes
    from .onboarding import choreo_get, choreo_set
    from .performance import set_ as perf_set
    ch = choreo_get(d)
    sections = [s for s in ch.get("sections") or [] if not str(s.get("notes", "")).startswith("[Producer]")]   # re-import replaces
    files = list(ch.get("files") or [])
    perf_chars = {}
    for c in m.get("choreography") or []:
        who = ids.get(c.get("character_id"))
        if not who:
            report["unknown_refs"].append({"where": f"choreography {c.get('id')}", "ref": c.get("character_id")})
            continue
        name = who[1]
        spec = _text(root, mpath, c.get("written_spec")) if c.get("written_spec") else ""
        if c.get("visual_sheet"):
            src = resolve(root, mpath, c["visual_sheet"])
            if src:
                rel = _copy(d, src)
                if rel not in files:
                    files.append(rel)
            else:
                report["missing_files"].append({"asset": f"choreography sheet for {name}", "file": c["visual_sheet"]})
        if DANCE.search(c.get("classification") or ""):
            by_sec = {}
            for mv in c.get("moves") or []:
                txt = mv.get("name", "")
                detail = "; ".join(str(mv[k]) for k in ("action", "footwork", "arms", "torso", "head_gaze", "travel") if mv.get(k))
                by_sec.setdefault(mv.get("song_section") or "whole song", []).append(f"{txt}{': ' + detail if detail else ''}")
            for sec, moves in by_sec.items():
                sections.append({"section": sec, "performers": [name],
                                 "notes": f"[Producer] {name} ({c.get('classification')}): " + ", then ".join(moves)})
            if spec:
                sections.append({"section": "whole song", "performers": [name], "notes": f"[Producer] {name}: {spec[:600]}"})
        else:
            prof = next((v for k, v in ACTING_PROFILE.items() if k in (c.get("classification") or "").lower()), "natural")
            perf_chars[name] = prof
            item = who[3]
            extra = (spec or c.get("classification") or "").strip()
            if extra and extra not in (item.get("notes") or ""):
                item["notes"] = ((item.get("notes") or "") + f" Acting: {extra[:600]}").strip()
    mode = ch.get("mode") if ch.get("mode") not in (None, "none") else ("upload" if files else "written" if sections else "none")
    choreo_set(d, {**ch, "mode": mode, "files": files, "sections": sections})
    if perf_chars:
        perf_set(d, {"characters": perf_chars})
    if any(v[3].get("notes") for v in ids.values()):
        p2, lib2 = library.load(d)
        for it in lib2["items"]:
            ext = it.get("external_id")
            if ext in ids:
                it["notes"] = ids[ext][3].get("notes", it.get("notes"))
        library.save_library(d, p2, lib2)
    report["imported"]["choreography"] = len(m.get("choreography") or [])
    report["imported"]["acting_profiles"] = perf_chars

    # 4. shots: placed on the song now, or as soon as the song has been listened to
    report["imported"]["shots_in_package"] = len(m.get("shots") or [])
    p = _read(os.path.join(d, "project.json"), {})
    p["producer_import"] = report
    p["producer_pending"] = bool(m.get("shots"))
    _write(os.path.join(d, "project.json"), p)
    if m.get("shots") and os.path.exists(os.path.join(d, "songmap.json")):
        return plan(d)
    return report


# ---------------------------------------------------------------- shots -> the shot plan

def _norm(s: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", (s or "").lower()))


def _anchor(sh: dict, sm: dict, used_sections: dict) -> float | None:
    if isinstance(sh.get("start_seconds"), (int, float)):
        return float(sh["start_seconds"])
    cue = _norm(sh.get("lyric_cue"))
    if cue:
        for ln in sm.get("lyrics") or []:
            t = _norm(ln.get("text"))
            if ln.get("start") is not None and t and (cue in t or t in cue):
                return float(ln["start"])
    sec = _norm(sh.get("song_section"))
    if sec:
        hits = [s for s in sm.get("sections") or [] if _norm(s.get("label")) and (_norm(s.get("label")) in sec or sec.split()[0] == _norm(s.get("label")).split()[0])]
        k = used_sections.get(sec, 0)
        if hits:
            used_sections[sec] = k + 1
            return float(hits[min(k, len(hits) - 1)]["start"])
    return None


def plan(d: str) -> dict:
    """Build production.json from the imported shots, keeping the plugin ids. Needs the song map."""
    m = _read(os.path.join(d, "assets", "producer", "manifest.json"))
    sm = _read(os.path.join(d, "songmap.json"))
    p = _read(os.path.join(d, "project.json"), {})
    report = p.get("producer_import") or {}
    if not m or not m.get("shots"):
        return report
    if not sm:
        raise SystemExit("The song hasn't been listened to yet; the shots will be placed when it has.")
    from . import library
    _, lib = library.load(d)
    by_ext = {i.get("external_id"): i for i in lib["items"] if i.get("external_id")}
    dur, beats = float(sm["duration"]), sorted(sm.get("beats") or [])
    shots = m["shots"]
    used, anchors = {}, []
    for sh in shots:
        anchors.append(_anchor(sh, sm, used))
    report["untimed_shots"] = [sh["id"] for sh, a in zip(shots, anchors) if a is None]
    # fill gaps: shots without an anchor share the time between their neighbours evenly; keep order monotonic
    times = list(anchors)
    if times[0] is None:
        times[0] = 0.0
    i = 0
    while i < len(times):
        if times[i] is None:
            j = i
            while j < len(times) and times[j] is None:
                j += 1
            lo = times[i - 1]
            hi = times[j] if j < len(times) else dur
            step = (hi - lo) / (j - i + 1)
            for k in range(i, j):
                times[k] = lo + step * (k - i + 1)
            i = j
        else:
            if i and times[i] <= times[i - 1]:
                times[i] = times[i - 1] + 1.0
            i += 1
    snap = lambda t: min(beats, key=lambda b: abs(b - t)) if beats and abs(min(beats, key=lambda b: abs(b - t)) - t) < 0.4 else t
    starts = [round(snap(t), 3) for t in times]
    ends = [round(float(sh["end_seconds"]), 3) if isinstance(sh.get("end_seconds"), (int, float)) else None for sh in shots]
    for k in range(len(shots)):
        nxt = starts[k + 1] if k + 1 < len(shots) else dur
        ends[k] = min(ends[k] or nxt, nxt) if ends[k] else nxt
        if ends[k] <= starts[k]:
            ends[k] = starts[k] + 1.0

    # scenes: by sequence_id, else each change of environment starts a new scene
    scenes, cur_key = [], object()
    for sh, a, b in zip(shots, starts, ends):
        key = sh.get("sequence_id") or sh.get("environment_id") or "scene"
        if not scenes or key != cur_key:
            env = by_ext.get(sh.get("environment_id"))
            scenes.append({"number": len(scenes) + 1, "heading": (env or {}).get("name") or sh.get("sequence_id") or f"Scene {len(scenes) + 1}",
                           "fields": {}, "notes": {}, "characters": [], "sung_lines": [], "start": a, "end": b, "shots": [],
                           "external_id": sh.get("sequence_id")})
            cur_key = key
        sc = scenes[-1]
        names = []
        for cid in sh.get("character_ids") or []:
            it = by_ext.get(cid)
            if it:
                names.append(it["name"])
            else:
                report.setdefault("unknown_refs", []).append({"where": f"shot {sh['id']}", "ref": cid})
        for ref in (sh.get("wardrobe_ids") or []) + (sh.get("prop_ids") or []) + (sh.get("reference_assets") or []) + \
                ([sh["environment_id"]] if sh.get("environment_id") else []):
            if ref not in by_ext:
                report.setdefault("unknown_refs", []).append({"where": f"shot {sh['id']}", "ref": ref})
        env = by_ext.get(sh.get("environment_id"))
        wardrobe = [by_ext[w] for w in sh.get("wardrobe_ids") or [] if w in by_ext]
        moves = []
        for cid in sh.get("choreography_ids") or []:
            c = next((x for x in m.get("choreography") or [] if x.get("id") == cid), None)
            if c:
                who = by_ext.get(c.get("character_id"), {}).get("name", "")
                names_ = [mv.get("name") for mv in c.get("moves") or [] if not sh.get("song_section") or
                          not mv.get("song_section") or _norm(mv["song_section"]) == _norm(sh["song_section"])]
                if names_:
                    moves.append(f"{who}: {', then '.join(n for n in names_ if n)}")
        n = len(sc["shots"]) + 1
        sid = f"S{sc['number']:02d}-{n:02d}"
        shot = {"id": sid, "scene": sc["number"], "number": n, "external_id": sh["id"], "source_shots": [sh["id"]],
                "description": sh.get("action") or "", "beats": [sh["action"]] if sh.get("action") else [],
                "framing": sh.get("framing") or "", "camera_moves": [], "camera_movement": sh.get("camera") or "",
                "performers": names, "performance": sh.get("performance") or "", "lighting": sh.get("lighting") or "",
                "environment": ((env or {}).get("name", "") + (". " + env["notes"] if (env or {}).get("notes") else "")).strip(". ")
                               + (f" ({sh['scene']})" if sh.get("scene") and env else ""),
                "expression": sh.get("expression") or "",
                "wardrobe": "; ".join(w["name"] + (f" ({w['notes']})" if w.get("notes") else "") for w in wardrobe),
                "movement": "; ".join(moves), "continuity_notes": sh.get("continuity_notes") or [],
                "start": a, "end": b, "section": sh.get("song_section") or "", "lyrics": [sh["lyric_cue"]] if sh.get("lyric_cue") else [],
                "sync_accents": [round(float(x), 3) for x in sm.get("accents") or [] if a <= x < b],
                "timing": "from the package" if isinstance(sh.get("start_seconds"), (int, float)) else
                          "lyric cue" if sh.get("lyric_cue") else "song section" if sh.get("song_section") else "estimated",
                "renderer": "auto", "state": "planned", "flags": [] if sh.get("action") else ["no action described"]}
        sc["shots"].append(shot)
        sc["end"] = b
        for nm in names:
            if nm not in sc["characters"]:
                sc["characters"].append(nm)
        # the shot's own references: turn them on for this shot only
        for ref in (sh.get("wardrobe_ids") or []) + (sh.get("prop_ids") or []) + (sh.get("reference_assets") or []) + \
                ([sh["environment_id"]] if sh.get("environment_id") else []):
            it = by_ext.get(ref)
            if it:
                library.assign(d, "shot", sid, it["id"], True)
    chars = [{"name": it["name"], "appearance": it.get("notes") or "", "acting_notes": ""}
             for it in lib["items"] if it.get("external_id") and it["kind"] == "character"]
    prod = {"schema_version": 1, "meta": {"source": "PULSEFRAME Producer", "project_id": (m.get("project") or {}).get("id")},
            "characters": chars, "scenes": scenes}
    # an existing plan is kept under a timestamp, as when a new script is adopted (never deleted)
    if os.path.exists(os.path.join(d, "production.json")):
        os.replace(os.path.join(d, "production.json"), os.path.join(d, f"production.before-{time.strftime('%Y%m%d-%H%M%S')}.json"))
    _write(os.path.join(d, "production.json"), prod)
    report["imported"]["shots"] = sum(len(s["shots"]) for s in scenes)
    report["imported"]["scenes"] = len(scenes)
    p = _read(os.path.join(d, "project.json"), {})
    p["producer_import"] = report
    p["producer_pending"] = False
    _write(os.path.join(d, "project.json"), p)
    return report


def main(argv: list[str]) -> int:
    try:
        if argv[0] == "inspect":
            res = inspect(argv[1])
        elif argv[0] == "apply":
            res = apply(argv[1], argv[2])
        elif argv[0] == "plan":
            res = plan(argv[1])
        else:
            raise SystemExit("Use inspect, apply or plan.")
        print(json.dumps({"event": "result", "data": res}, ensure_ascii=False), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except Exception as e:
        print(json.dumps({"event": "error", "message": f"{type(e).__name__}: {e}"}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
