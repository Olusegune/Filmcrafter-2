"""Films: a story-first project. The script is versioned, never rewritten behind your back, and can be locked.

  <Film>/film.json                  title, aspect ratio, stage, which script version is current / locked, whether the story was kept as it is
  <Film>/<Title>.filmcrafter        the double-clickable document (points at film.json)
  <Film>/script/original/           the file you brought, byte for byte
  <Film>/script/versions/vNNN.json  one record per version: text, kind, note, parent, fingerprint, locked
  <Film>/script/analysis/vNNN.json  what was found in that version, and the advice with your decision on each piece

Reading a story is free and local. Advice is advice: nothing here edits the script. A change to the story is a new version.
A locked version is never changed (to move on, write a new version and lock that).

  python -m filmcrafter_engine.story <action> <film_dir> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time

from .safe import sha1

SCHEMA = 1
KINDS = ("screenplay", "idea", "synopsis", "treatment", "outline")
LADDER = ("logline", "synopsis", "treatment", "beats", "outline", "screenplay")        # the development ladder, from a spark to a script
KIND_RUNG = {"idea": "logline", "synopsis": "synopsis", "treatment": "treatment", "outline": "outline", "screenplay": "screenplay"}
TEXT_EXT = (".txt", ".md", ".fountain", ".text")
DOC_EXT = (".pdf", ".docx")
MAX_TEXT = 600_000                 # characters kept per version: a feature-length screenplay is about 150,000
MAX_FILE_BYTES = 25 * 1024 * 1024
LINES_PER_PAGE = 55                # a screenplay page is about a minute of film: the usual rule of thumb, nothing more

SLUG = re.compile(r"^\s*(?:\.(?=[A-Za-z0-9])|(?:INT|EXT|EST|INT\.?/EXT|EXT\.?/INT|I/E)[\. ])", re.I)
CUE_NOTE = re.compile(r"\s*\((?:V\.?O\.?|O\.?S\.?|O\.?C\.?|CONT'?D\.?|CONT\.?|FILTERED|ON PHONE|ON RADIO)[^)]*\)\s*", re.I)
TRANSITION = re.compile(r"^\s*(?:[A-Z ]+ TO:|FADE (?:IN|OUT)\.?|CUT TO BLACK\.?|SMASH CUT\.?|MATCH CUT\.?|DISSOLVE TO:)\s*$")


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


def _slug(title: str) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", title).strip().rstrip(".")
    return re.sub(r"\s+", " ", s)[:60] or "Untitled"


def is_film(path: str) -> bool:
    p = str(path or "")
    return os.path.isfile(os.path.join(p, "film.json")) or os.path.basename(p).lower() == "film.json"


def _manifest(d: str) -> dict:
    m = _read(os.path.join(d, "film.json"))
    if not isinstance(m, dict) or "story" not in m:
        raise SystemExit("That isn't a FilmCrafter film.")
    return m


def _vpath(d: str, n: int, sub: str = "versions") -> str:
    return os.path.join(d, "script", sub, f"v{n:03d}.json")


# ---------------------------------------------------------------- reading the story

def _norm(text: str) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("﻿", "").replace("\x00", "")[:MAX_TEXT]


def read_document(path: str) -> dict:
    """The words in a file the user chose. Plain text keeps every line exactly; PDF and Word are read for their text."""
    p = os.path.abspath(str(path or ""))
    low = p.lower()
    if not low.endswith(TEXT_EXT + DOC_EXT) or not os.path.isfile(p):
        raise SystemExit("Choose a text, Markdown, Fountain, PDF or Word (.docx) file.")
    if os.path.getsize(p) > MAX_FILE_BYTES:
        raise SystemExit("That file is larger than 25 MB.")
    if low.endswith(TEXT_EXT):
        with open(p, encoding="utf-8-sig", errors="replace") as f:
            text = f.read(MAX_TEXT + 1)
    elif low.endswith(".pdf"):
        text = _pdf_text(p)
    else:
        from . import onboarding
        text = onboarding.doc_text(p)["text"]
    text = _norm(text)
    if not text.strip():
        raise SystemExit("No text was found in that file.")
    return {"name": os.path.basename(p), "text": text, "truncated": len(text) >= MAX_TEXT}


def words_per_line(text: str) -> float:
    """The middle number of words on a line: about 1 when a file was read one word to a line, 8 to 15 for ordinary writing."""
    n = sorted(len(l.split()) for l in str(text).split("\n") if l.strip())
    return float(n[len(n) // 2]) if n else 0.0


def looks_broken(text: str) -> bool:
    """Text that was read one word to a line (a common fault of some PDFs), so it needs reading again."""
    lines = [l for l in str(text).split("\n") if l.strip()]
    return len(lines) >= 60 and words_per_line(text) <= 1.5


REPLACEMENT = "\ufffd"


def tidy_pdf_text(text: str) -> str:
    """Repair what a PDF reader leaves behind: the dash that comes out as a replacement mark, indents from the page layout, runs of spaces, and extra blank lines."""
    t = str(text).replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"(?<=\S)" + REPLACEMENT + r"(?=\S)", "-", t)         # carefully<mark>not  ->  carefully-not
    t = t.replace(" " + REPLACEMENT + " ", " - ").replace(REPLACEMENT, "-")
    t = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in t.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _pdf_text(path: str) -> str:
    """The words in a PDF, in reading order. The layout reader keeps each printed line together; the plain reader is the fallback (and wins only if it gives longer lines)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise SystemExit("PDF files can't be read here. Paste the text instead, or choose a text or Word file.")
    try:
        reader = PdfReader(path)
        if getattr(reader, "is_encrypted", False):
            raise SystemExit("That PDF is protected. Paste the text instead.")
        layout, plain = [], []
        for pg in reader.pages:
            try:
                layout.append(pg.extract_text(extraction_mode="layout") or "")
            except Exception:
                layout.append("")
            plain.append(pg.extract_text() or "")
    except SystemExit:
        raise
    except Exception:
        raise SystemExit("That PDF couldn't be read. If it is a scan or protected, paste the text instead.")
    a, b = tidy_pdf_text("\n\n".join(layout)), tidy_pdf_text("\n\n".join(plain))
    best = a if words_per_line(a) >= words_per_line(b) else b
    return best


# ---------------------------------------------------------------- finding the scenes

def _is_cue(line: str, prev_blank: bool, nxt: str | None) -> bool:
    s = line.strip()
    if not prev_blank or not s or nxt is None or not nxt.strip():
        return False
    if SLUG.match(s) or TRANSITION.match(s) or s.startswith(("(", "[", "#", "=", ">")):
        return False
    name = CUE_NOTE.sub("", s).strip().lstrip("@")
    if not name or len(name) > 40 or not re.search(r"[A-Z]", name):
        return False
    return name == name.upper() and not re.search(r"[a-z]", name) and not re.search(r"[.!?]\s*$", name.strip("()"))


def _heading_parts(h: str) -> dict:
    s = h.strip().lstrip(".").strip()
    m = re.match(r"(?i)^(int\.?/ext|ext\.?/int|i/e|int|ext|est)[\. ]+", s)
    tag = m.group(1).lower() if m else ""
    kind = "INT/EXT" if "/" in tag else ("EXT" if tag == "est" else tag.upper())
    rest = s[m.end():].strip() if m else s
    place, _, when = rest.partition(" - ")
    if not when and " – " in rest:
        place, _, when = rest.partition(" – ")
    return {"int_ext": kind, "location": place.strip(" -").strip().upper(), "time": when.strip().upper()}


def parse_screenplay(text: str) -> dict:
    """Scenes, speaking characters and rough length from a screenplay (Fountain-style or the usual typed layout). Tolerant: a script with no scene headings is one scene."""
    lines = _norm(text).split("\n")
    scenes: list[dict] = []
    cur: dict | None = None

    def new_scene(heading: str, at: int) -> dict:
        return {"number": len(scenes) + 1, "heading": heading.strip().lstrip(".").strip(), **_heading_parts(heading), "line": at,
                "characters": [], "dialogue_lines": 0, "action_lines": 0, "words": 0, "speeches": 0}

    has_headings = any(SLUG.match(x.strip()) for x in lines)
    prev_blank, in_dialogue, speaker = True, False, ""
    for i, raw in enumerate(lines):
        s = raw.strip()
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if not s:
            prev_blank, in_dialogue = True, False
            continue
        if SLUG.match(s) and prev_blank:
            cur = new_scene(s, i)
            scenes.append(cur)
            prev_blank, in_dialogue = False, False
            continue
        if cur is None:
            cur = {"number": 1, "heading": "Opening", "int_ext": "", "location": "", "time": "", "line": i, "characters": [], "dialogue_lines": 0,
                   "action_lines": 0, "words": 0, "speeches": 0, "implied": True}
            scenes.append(cur)
        if not in_dialogue and not (cur.get("implied") and has_headings) and _is_cue(raw, prev_blank, nxt):          # lines before the first scene heading are a title page, not people speaking
            speaker = CUE_NOTE.sub("", s).strip().lstrip("@").strip()
            if speaker not in cur["characters"]:
                cur["characters"].append(speaker)
            cur["speeches"] += 1
            in_dialogue = True
        elif in_dialogue:
            if not (s.startswith("(") and s.endswith(")")):
                cur["dialogue_lines"] += 1
                cur["words"] += len(s.split())
        elif TRANSITION.match(s):
            pass
        else:
            cur["action_lines"] += 1
            cur["words"] += len(s.split())
        prev_blank = False
    if len(scenes) > 1 and scenes[0].get("implied"):                    # a title page is not a scene
        scenes = scenes[1:]
        for i, sc in enumerate(scenes, 1):
            sc["number"] = i
    chars: dict[str, dict] = {}
    places: dict[str, list[int]] = {}
    for sc in scenes:
        n_lines = sc["dialogue_lines"] + sc["action_lines"]
        sc["seconds"] = round(max(3.0, n_lines / LINES_PER_PAGE * 60.0), 1)
        for c in sc["characters"]:
            e = chars.setdefault(c, {"name": c, "scenes": [], "first_scene": sc["number"]})
            e["scenes"].append(sc["number"])
        if sc["location"]:
            places.setdefault(sc["location"], []).append(sc["number"])
    for c in chars.values():
        c["scene_count"] = len(c["scenes"])
    return {"scenes": scenes, "characters": [c for _, c in sorted(enumerate(chars.values()), key=lambda ic: (-ic[1]["scene_count"], ic[0]))],
            "locations": [{"name": k, "scenes": v} for k, v in places.items()],
            "seconds": round(sum(sc["seconds"] for sc in scenes), 1), "has_headings": any(not sc.get("implied") for sc in scenes)}


def parse_outline(text: str) -> list[dict]:
    """Numbered or bulleted lines of an outline, as scene stubs."""
    out = []
    for line in _norm(text).split("\n"):
        m = re.match(r"^\s*(?:\d+[\.\)]|[-*•]|scene\s+\d+[:.\-]?)\s+(.+\S)\s*$", line, re.I)
        if m:
            out.append({"number": len(out) + 1, "heading": m.group(1)[:160], "int_ext": "", "location": "", "time": "", "characters": [],
                        "dialogue_lines": 0, "action_lines": 0, "words": len(m.group(1).split()), "seconds": 0.0})
    return out


# ---------------------------------------------------------------- advice (never an edit)

def _advice(kind: str, text: str, found: dict) -> list[dict]:
    """Observations about structure, pacing, visual storytelling and production load. Each is something to look at, never a verdict."""
    recs: list[dict] = []

    def add(id_: str, topic: str, text_: str, scene: int | None = None) -> None:
        recs.append({"id": id_, "topic": topic, "text": text_, "scene": scene, "status": "open"})

    words = len(text.split())
    if kind == "screenplay":
        scenes = found["scenes"]
        if not found["has_headings"]:
            add("no-headings", "structure", "No scene headings (INT. or EXT.) were found, so the whole text is treated as one scene. Adding headings lets FilmCrafter plan scene by scene.")
        for sc in scenes:
            if sc["dialogue_lines"] + sc["action_lines"] <= 1 and not sc.get("implied"):
                add(f"thin-{sc['number']}", "structure", f"Scene {sc['number']} ({sc['heading']}) has almost nothing in it. Is it a transition, or is something missing?", sc["number"])
            lines = sc["dialogue_lines"] + sc["action_lines"]
            if lines >= 18 and sc["dialogue_lines"] / max(1, lines) >= 0.8:
                add(f"talky-{sc['number']}", "visual storytelling", f"Scene {sc['number']} is almost all dialogue. A look, a gesture or an object could carry some of it.", sc["number"])
            if sc["seconds"] >= 180:
                add(f"long-{sc['number']}", "pacing", f"Scene {sc['number']} runs about {sc['seconds'] / 60:.1f} minutes. It may be worth splitting where the emotion turns.", sc["number"])
        spoken = [c for c in found["characters"]]
        if len(spoken) >= 6 and found["seconds"] <= 300:
            add("cast-size", "production", f"{len(spoken)} speaking characters in about {found['seconds'] / 60:.1f} minutes is a lot to keep consistent. Combining minor roles would make the film easier to produce.")
        if len(found["locations"]) >= 6 and found["seconds"] <= 300:
            add("locations", "production", f"{len(found['locations'])} locations in about {found['seconds'] / 60:.1f} minutes. Fewer places means fewer sets to keep consistent.")
        if found["seconds"] > 180:
            add("length", "production", f"About {found['seconds'] / 60:.1f} minutes of script. The first pass works best on one scene or a short of 1 to 3 minutes; you can start with one scene.")
    else:
        rung = KIND_RUNG.get(kind, "logline")
        if kind == "idea" and words > 60:
            add("long-idea", "structure", "This is long for a logline. If it is the whole story, call it a synopsis; a logline is one or two sentences.")
        if kind in ("idea", "synopsis") and words < 8:
            add("short", "structure", "Very short. A sentence about who wants what, and what stands in the way, gives the next steps something to work from.")
        nxt = LADDER[min(len(LADDER) - 1, LADDER.index(rung) + 1)]
        add("next-rung", "structure", f"This is at the {rung} stage. The next step on the way to a screenplay is the {nxt}.")
    return recs


def analyze(kind: str, text: str) -> dict:
    kind = kind if kind in KINDS else "idea"
    text = _norm(text)
    if kind == "screenplay":
        found = parse_screenplay(text)
    elif kind == "outline":
        sc = parse_outline(text)
        found = {"scenes": sc, "characters": [], "locations": [], "seconds": 0.0, "has_headings": bool(sc)}
    else:
        found = {"scenes": [], "characters": [], "locations": [], "seconds": 0.0, "has_headings": False}
    found["kind"] = kind
    found["words"] = len(text.split())
    found["pages"] = round(found["seconds"] / 60.0, 1) if kind == "screenplay" else 0
    found["advice"] = _advice(kind, text, found)
    found["rung"] = KIND_RUNG.get(kind, "logline")
    return found


def preview(kind: str, text: str) -> dict:
    """What would be found in this text: nothing is written."""
    a = analyze(kind, text)
    return {"kind": a["kind"], "words": a["words"], "scenes": len(a["scenes"]), "characters": len(a["characters"]), "locations": len(a["locations"]),
            "seconds": a["seconds"], "has_headings": a["has_headings"]}


# ---------------------------------------------------------------- the film

def _save_version(d: str, n: int, kind: str, text: str, note: str, parent: int | None, origin: str) -> dict:
    text = _norm(text)
    rec = {"version": n, "kind": kind, "text": text, "note": str(note or "")[:300], "parent": parent, "origin": origin,
           "created": int(time.time()), "fingerprint": sha1(text.encode("utf-8")).hexdigest()[:16], "locked": False}
    _write(_vpath(d, n), rec)
    a = analyze(kind, text)
    _write(_vpath(d, n, "analysis"), {"version": n, "found": {k: v for k, v in a.items() if k != "advice"}, "advice": a["advice"]})
    return rec


# The shapes a film's frame can take (the same list as the shell's project settings): from ultra-wide cinema to vertical phone video.
ASPECTS = ("16:9", "21:9", "2.39:1", "4:3", "1:1", "4:5", "3:4", "9:16", "9:21")


def _aspect(value) -> str:
    v = str(value if value is not None else "16:9").strip()
    if v not in ASPECTS:
        raise SystemExit("Choose one of the listed frame shapes: " + ", ".join(ASPECTS) + ".")
    return v


def create(root: str, title: str, kind: str, text: str, source_file: str | None = None, aspect_ratio: str = "16:9") -> dict:
    kind = kind if kind in KINDS else "idea"
    aspect_ratio = _aspect(aspect_ratio)
    text = _norm(text)
    if not text.strip():
        raise SystemExit("Add some story first: paste it, or choose a file.")
    title = str(title or "").strip()[:120] or "Untitled film"
    os.makedirs(root, exist_ok=True)
    base = _slug(title)
    d, n = os.path.join(root, base), 2
    while os.path.exists(d):
        d, n = os.path.join(root, f"{base} {n}"), n + 1
    for sub in ("script/original", "script/versions", "script/analysis", "bible", "cast", "world", "scenes", "shots", "exports"):
        os.makedirs(os.path.join(d, *sub.split("/")), exist_ok=True)
    kept = None
    if source_file and source_file.lower().endswith(TEXT_EXT + DOC_EXT) and os.path.isfile(source_file) and os.path.getsize(source_file) <= MAX_FILE_BYTES:
        kept = os.path.basename(source_file)[:100] or "story"
        kept = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", kept)
        shutil.copyfile(source_file, os.path.join(d, "script", "original", kept))      # the file you brought, untouched
    else:
        with open(os.path.join(d, "script", "original", "story.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        kept = "story.txt"
    _save_version(d, 1, kind, text, "As supplied", None, "imported" if source_file else "written")
    m = {"schema": SCHEMA, "title": title, "created": int(time.time()), "aspect_ratio": aspect_ratio, "mode": "simple", "stage": "story",
         "story": {"kind": kind, "current": 1, "locked": None, "lock_history": [], "as_is": None, "original": kept}}
    _write(os.path.join(d, "film.json"), m)
    _write(os.path.join(d, f"{base}.filmcrafter"), {"film": True, "manifest": "film.json"})
    return {"dir": d, **status(d)}


def _versions(d: str) -> list[dict]:
    out = []
    folder = os.path.join(d, "script", "versions")
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        rec = _read(os.path.join(folder, name))
        if isinstance(rec, dict) and "version" in rec:
            out.append({k: rec[k] for k in ("version", "kind", "note", "parent", "origin", "created", "fingerprint", "locked")} | {"words": len(rec.get("text", "").split())})
    return out


def status(d: str, version: int | None = None) -> dict:
    m = _manifest(d)
    st = m["story"]
    n = int(version or st["current"])
    rec = _read(_vpath(d, n))
    if not rec:
        raise SystemExit("That version of the story doesn't exist.")
    an = _read(_vpath(d, n, "analysis")) or {"found": {}, "advice": []}
    return {"title": m["title"], "aspect_ratio": m["aspect_ratio"], "mode": m.get("mode", "simple"), "stage": m["stage"], "created": m["created"],
            "story": st, "version": n, "text": rec["text"], "kind": rec["kind"], "note": rec.get("note", ""), "locked_here": bool(rec.get("locked")),
            "found": an["found"], "advice": an["advice"], "versions": _versions(d), "looks_broken": looks_broken(rec["text"]),
            "original": _original_file(d)}


def _original_file(d: str) -> str | None:
    name = (_read(os.path.join(d, "film.json"), {}) or {}).get("story", {}).get("original")
    p = os.path.join(d, "script", "original", name or "")
    return name if name and os.path.isfile(p) and name != "story.txt" else None


def reread_original(d: str) -> dict:
    """Read the file you brought again, with the current reader, as a NEW version. Nothing existing is changed: the earlier version stays as it was."""
    _manifest(d)
    name = _original_file(d)
    if not name:
        raise SystemExit("This film has no original file to read again.")
    r = read_document(os.path.join(d, "script", "original", name))
    cur = _read(_vpath(d, _manifest(d)["story"]["current"])) or {}
    if r["text"].strip() == str(cur.get("text", "")).strip():
        raise SystemExit("Reading the file again gives the same text, so there is nothing new.")
    return add_version(d, r["text"], "Read from the original file again", "screenplay")


def add_version(d: str, text: str, note: str = "", kind: str | None = None) -> dict:
    """A change to the story is a new version. Nothing existing is touched."""
    m = _manifest(d)
    st = m["story"]
    text = _norm(text)
    if not text.strip():
        raise SystemExit("A version needs some text.")
    vs = _versions(d)
    n = (vs[-1]["version"] if vs else 0) + 1
    parent = st["current"]
    k = kind if kind in KINDS else (_read(_vpath(d, parent)) or {}).get("kind", st["kind"])
    _save_version(d, n, k, text, note or "Revised", parent, "written")
    st["current"], st["kind"], st["as_is"] = n, k, None            # a new version has had no decision yet
    _write(os.path.join(d, "film.json"), m)
    return status(d)


def set_current(d: str, version: int) -> dict:
    m = _manifest(d)
    if not _read(_vpath(d, int(version))):
        raise SystemExit("That version of the story doesn't exist.")
    m["story"]["current"] = int(version)
    rec = _read(_vpath(d, int(version)))
    m["story"]["kind"] = rec["kind"]
    _write(os.path.join(d, "film.json"), m)
    return status(d)


def lock(d: str, version: int | None = None) -> dict:
    """Story Lock: this version is the story the rest of the film is made from. It is never edited; later changes are new versions."""
    m = _manifest(d)
    st = m["story"]
    n = int(version or st["current"])
    rec = _read(_vpath(d, n))
    if not rec:
        raise SystemExit("That version of the story doesn't exist.")
    if rec["kind"] != "screenplay":
        raise SystemExit("Only a screenplay can be locked. This is still a " + KIND_RUNG.get(rec["kind"], rec["kind"]) + ": write the screenplay (or paste it) as a new version first.")
    rec["locked"] = True
    rec["locked_at"] = int(time.time())
    _write(_vpath(d, n), rec)
    st["locked"] = n
    st["lock_history"] = [*st.get("lock_history", []), {"version": n, "at": rec["locked_at"]}]
    st["as_is"] = st.get("as_is") or n
    _write(os.path.join(d, "film.json"), m)
    return status(d)


def as_is(d: str, version: int | None = None) -> dict:
    """Use this story as it is: every piece of advice is set aside and the script is untouched."""
    m = _manifest(d)
    n = int(version or m["story"]["current"])
    if not _read(_vpath(d, n)):
        raise SystemExit("That version of the story doesn't exist.")
    m["story"]["as_is"] = n
    _write(os.path.join(d, "film.json"), m)
    return status(d)


def set_aspect(d: str, aspect_ratio: str) -> dict:
    """The shape of the film's frame. Every picture and video made from here on is asked for in this shape (the render project follows on the next sync); what was made stays as it was."""
    m = _manifest(d)
    m["aspect_ratio"] = _aspect(aspect_ratio)
    _write(os.path.join(d, "film.json"), m)
    return status(d)


def set_mode(d: str, mode: str) -> dict:
    """Simple mode hides the detailed workspaces; Studio mode shows them. Same film either way: nothing is lost by switching."""
    if mode not in ("simple", "studio"):
        raise SystemExit("Choose simple or studio.")
    m = _manifest(d)
    m["mode"] = mode
    _write(os.path.join(d, "film.json"), m)
    return status(d)


def rec_set(d: str, version: int, rec_id: str, state: str) -> dict:
    """Mark a piece of advice: noted (I'll deal with it in a new version), or dismissed. The script is not changed."""
    if state not in ("open", "noted", "dismissed"):
        raise SystemExit("Choose noted, dismissed or open.")
    _manifest(d)
    p = _vpath(d, int(version), "analysis")
    an = _read(p)
    if not an:
        raise SystemExit("That version of the story doesn't exist.")
    hit = False
    for r in an["advice"]:
        if r["id"] == str(rec_id):
            r["status"], hit = state, True
    if not hit:
        raise SystemExit("That note isn't in this version.")
    _write(p, an)
    return status(d, int(version))


# ---------------------------------------------------------------- command line

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-story")
    ap.add_argument("action", choices=["create", "status", "preview", "read_file", "add_version", "set_current", "lock", "as_is", "rec_set", "set_mode", "set_aspect", "reread"])
    ap.add_argument("target")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "create":
            res = create(a.target, x.get("title", ""), x.get("kind", "idea"), x.get("text", ""), x.get("file"), x.get("aspect_ratio", "16:9"))
        elif a.action == "preview":
            res = preview(x.get("kind", "idea"), x.get("text", ""))
        elif a.action == "read_file":
            res = read_document(x["file"])
        elif a.action == "status":
            res = status(a.target, x.get("version"))
        elif a.action == "add_version":
            res = add_version(a.target, x.get("text", ""), x.get("note", ""), x.get("kind"))
        elif a.action == "set_current":
            res = set_current(a.target, int(x["version"]))
        elif a.action == "lock":
            res = lock(a.target, x.get("version"))
        elif a.action == "as_is":
            res = as_is(a.target, x.get("version"))
        elif a.action == "reread":
            res = reread_original(a.target)
        elif a.action == "set_mode":
            res = set_mode(a.target, str(x.get("mode", "")))
        elif a.action == "set_aspect":
            res = set_aspect(a.target, x.get("aspect_ratio"))
        else:
            res = rec_set(a.target, int(x["version"]), x["id"], x["state"])
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
