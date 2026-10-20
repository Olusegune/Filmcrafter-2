"""Your own production materials: storyboards, asset sheets, shot lists and notes that guide how the film is made.

A filmmaker often arrives with more than a script: a storyboard (pictures, one per shot, or a PDF of them), character and location sheets, a shot list in a spreadsheet, a style note. This reads
what the person points at, works out where each piece belongs, shows that as a plan, and only puts it into the film once the person has looked at the plan.

  scan    free, read-only. Looks at files, folders, .zip and .pdf; writes nothing into the film (only a plan and the unpacked copies under cache/). Returns the plan.
  apply   puts the ticked items into the film: storyboard panels go to their shots (and can become the composition reference for the hero frame), pictures go to the cast, places and props
          they belong to (new entries are made only when asked), a shot list fills in the shots' fields, notes are kept and can be added to the Bible. A snapshot of the film's records is taken first.
  history what was brought in, and when.

Never spends anything and never sends anything anywhere. It never replaces approved work: a locked storyboard is left alone, a panel already chosen for a shot is replaced only when the person
ticks that, and a shot list never overwrites a field the person has written unless they tick it. Originals stay where they are: everything is copied in.

  python -m filmcrafter_engine.materials scan|apply|history <film_dir> --data '{...}'
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sys
import time
import uuid
import zipfile

from . import safeio
from .safe import file_part

IMG = (".png", ".jpg", ".jpeg", ".webp")
TEXT = (".md", ".txt")
TABLE = (".csv", ".tsv")
WANTED = IMG + TEXT + TABLE + (".pdf",)
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_FILES = 2000
MAX_ZIP_ENTRIES = 5000
MAX_ZIP_TOTAL = 3 * 1024 ** 3
MAX_ZIP_FILE = 200 * 1024 * 1024
MAX_RATIO = 500
MAX_PDF_PAGES = 300
MAX_NOTE = 200_000
MAX_ROWS = 2000
MIN_SIDE = 64
TOKEN = re.compile(r"^[0-9a-f]{12}$")

STORYBOARD_WORDS = {"storyboard", "storyboards", "board", "boards", "panel", "panels", "sb", "thumbnail", "thumbnails", "thumbs", "layouts", "animatic"}
KIND_WORDS = {
    "character": {"character", "characters", "char", "chars", "cast", "people", "turnaround", "turnarounds", "wardrobe", "costume", "costumes", "outfit", "outfits"},
    "environment": {"location", "locations", "environment", "environments", "place", "places", "set", "sets", "world", "setting", "settings", "background", "backgrounds", "locale"},
    "prop": {"prop", "props", "object", "objects", "item", "items"},
}
VIEW_WORDS = {"front": "front", "side": "side", "profile": "side", "back": "back", "rear": "back", "three": "three-quarter", "quarter": "three-quarter", "34": "three-quarter",
              "turnaround": "master", "sheet": "master", "master": "master", "model": "master", "expression": "expression", "expressions": "expression", "pose": "pose", "poses": "pose",
              "wardrobe": "wardrobe", "costume": "wardrobe", "outfit": "wardrobe"}
NOISE = {"ref", "reference", "refs", "references", "final", "new", "old", "copy", "img", "image", "images", "pic", "picture", "photo", "design", "art", "concept", "v1", "v2", "v3", "of", "the", "a", "and"}
NOTE_TARGETS = (("tone", {"tone", "mood", "style", "look", "feel", "voice"}), ("world", {"world", "setting", "lore", "universe", "background"}), ("rules", {"rules", "bible", "continuity", "must"}),
                ("avoid", {"avoid", "dont", "never", "donts"}))
BIBLE_FIELD_ROOM = 3900          # the Bible keeps each rule field to 4,000 characters

FRAMING_WORDS = {"establishing": "establishing", "est": "establishing", "master": "wide", "wide": "wide", "ws": "wide", "ews": "wide", "long": "wide", "ls": "wide", "full": "wide", "medium": "medium", "med": "medium",
                 "ms": "medium", "mid": "medium", "waist": "medium", "mcu": "medium", "close": "close-up", "closeup": "close-up", "cu": "close-up", "ecu": "extreme close-up", "xcu": "extreme close-up",
                 "extreme close up": "extreme close-up", "extreme closeup": "extreme close-up", "extreme close-up": "extreme close-up", "close up": "close-up", "close-up": "close-up", "ots": "over the shoulder",
                 "over the shoulder": "over the shoulder", "over-the-shoulder": "over the shoulder", "pov": "point of view", "point of view": "point of view", "insert": "insert", "detail": "insert", "cutaway": "insert"}
ANGLE_WORDS = {"eye": "eye level", "eye level": "eye level", "eye-level": "eye level", "level": "eye level", "low": "low", "low angle": "low", "high": "high", "high angle": "high", "dutch": "dutch", "canted": "dutch",
               "overhead": "overhead", "top": "overhead", "birds eye": "overhead", "bird's eye": "overhead"}
MOVE_WORDS = {"static": "locked off", "locked": "locked off", "locked off": "locked off", "lock off": "locked off", "still": "locked off", "none": "locked off", "push": "push in", "push in": "push in",
              "dolly in": "push in", "zoom in": "push in", "pull": "pull out", "pull out": "pull out", "dolly out": "pull out", "zoom out": "pull out", "pan": "pan", "tilt": "tilt", "dolly": "dolly",
              "track": "tracking", "tracking": "tracking", "orbit": "orbit", "arc": "orbit", "crane": "crane", "jib": "crane", "handheld": "handheld", "hand held": "handheld", "hand-held": "handheld",
              "rack focus": "rack focus", "rack": "rack focus", "follow": "subject tracking", "subject tracking": "subject tracking"}
LENS_WORDS = {"wide": "wide (24mm)", "24": "wide (24mm)", "24mm": "wide (24mm)", "28": "wide (24mm)", "28mm": "wide (24mm)", "35": "normal (35mm)", "35mm": "normal (35mm)", "normal": "normal (35mm)",
              "50": "portrait (50mm)", "50mm": "portrait (50mm)", "portrait": "portrait (50mm)", "85": "telephoto (85mm+)", "85mm": "telephoto (85mm+)", "100": "telephoto (85mm+)", "100mm": "telephoto (85mm+)",
              "telephoto": "telephoto (85mm+)", "tele": "telephoto (85mm+)", "macro": "macro"}

COLUMNS = {
    "id": {"id", "shot id", "shot_id", "shotid"},
    "scene": {"scene", "sc", "scene number", "scene no", "scene #", "scene_number"},
    "shot": {"shot", "sh", "shot number", "shot no", "shot #", "shot_number", "number", "no", "#"},
    "title": {"title", "name", "shot name"},
    "action": {"action", "description", "what happens", "visual", "visuals", "shot description", "content", "story"},
    "framing": {"framing", "shot size", "size", "shot type", "type", "shot_size"},
    "angle": {"angle", "camera angle"},
    "lens": {"lens", "focal length"},
    "movement": {"movement", "camera movement", "move", "camera move", "camera", "motion"},
    "duration": {"duration", "length", "seconds", "dur", "secs", "time", "runtime"},
    "dialogue": {"dialogue", "dialog", "line", "lines", "vo", "voiceover", "voice over"},
    "speaker": {"speaker", "who speaks", "dialogue by"},
    "characters": {"characters", "character", "cast", "who", "people"},
    "location": {"location", "place", "setting", "environment", "int/ext"},
    "lighting": {"lighting", "light"},
    "sound": {"sound", "audio", "sfx", "music", "sound notes"},
    "notes": {"notes", "note", "comments", "comment", "director notes", "direction"},
}


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


# ---------------------------------------------------------------- small helpers

def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def _natural(s: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s.lower())]


def _sha(path: str) -> str:
    h = hashlib.sha1(usedforsecurity=False)
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _text(v, limit: int = 4000) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()[:limit]


def _staging(d: str, token: str) -> str:
    return os.path.join(d, "cache", "materials", token)


def _plan_path(d: str, token: str) -> str:
    return os.path.join(d, "cache", "materials", f"{token}.plan.json")


def _film(d: str) -> None:
    m = safeio.read_json(os.path.join(d, "film.json"), None)
    if not isinstance(m, dict) or "story" not in m:
        raise SystemExit("That isn't a FilmCrafter film.")


# ---------------------------------------------------------------- collecting the files

def _unzip(zpath: str, into: str, problems: list[str]) -> list[tuple[str, str]]:
    """The wanted files of a .zip, unpacked under `into`. Refuses odd paths, too many entries, a zip bomb; unpacks only what could matter."""
    out: list[tuple[str, str]] = []
    try:
        z = zipfile.ZipFile(zpath)
    except (OSError, zipfile.BadZipFile):
        problems.append(f"{os.path.basename(zpath)} is not a readable zip file, so it was skipped.")
        return out
    with z:
        infos = z.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            problems.append(f"{os.path.basename(zpath)} holds more than {MAX_ZIP_ENTRIES:,} items, so it was not opened.")
            return out
        if sum(i.file_size for i in infos) > MAX_ZIP_TOTAL:
            problems.append(f"{os.path.basename(zpath)} would unpack to more than 3 GB, so it was not opened.")
            return out
        for i, info in enumerate(infos):
            name = info.filename.replace("\\", "/")
            if info.is_dir():
                continue
            parts = [p for p in name.split("/") if p]
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in parts or any(p.startswith("__MACOSX") for p in parts) or os.path.basename(name).startswith("."):
                continue
            if not name.lower().endswith(WANTED):
                continue
            if info.file_size > MAX_ZIP_FILE or (info.file_size > 1 << 20 and info.compress_size and info.file_size / info.compress_size > MAX_RATIO):
                problems.append(f"{name} in {os.path.basename(zpath)} was skipped (it is too big or unusually compressed).")
                continue
            dst = os.path.join(into, f"{i:05d}", file_part(os.path.basename(name), 100))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with z.open(info) as src, open(dst, "wb") as f:
                shutil.copyfileobj(src, f, 1 << 20)
            out.append((dst, "/".join([os.path.splitext(os.path.basename(zpath))[0]] + parts)))
    return out


def _pdf_pages(path: str, rel: str, into: str, problems: list[str]) -> list[tuple[str, str]]:
    """One picture per page, from the biggest picture embedded in the page. Pages drawn as lines or text cannot be turned into a picture here, and are said so."""
    try:
        from pypdf import PdfReader
        r = PdfReader(path)
        if r.is_encrypted:
            problems.append(f"{os.path.basename(path)} is locked with a password, so it was skipped.")
            return []
        pages = list(r.pages)[:MAX_PDF_PAGES]
    except Exception:
        problems.append(f"{os.path.basename(path)} could not be read as a PDF, so it was skipped.")
        return []
    out, empty = [], []
    stem = file_part(os.path.splitext(os.path.basename(path))[0], 40)
    os.makedirs(into, exist_ok=True)
    for n, page in enumerate(pages, 1):
        try:
            best = max(page.images, key=lambda im: len(im.data), default=None)
        except Exception:
            best = None
        ext = os.path.splitext(best.name)[1].lower() if best else ""
        if best is None or ext not in IMG or len(best.data) > MAX_IMAGE_BYTES:
            empty.append(n)
            continue
        dst = os.path.join(into, f"{stem}-p{n:03d}{ext}")
        with open(dst, "wb") as f:
            f.write(best.data)
        out.append((dst, f"{rel}/page {n:03d}"))
    if empty:
        shown = ", ".join(str(n) for n in empty[:12]) + (" and more" if len(empty) > 12 else "")
        problems.append(f"{os.path.basename(path)}: page {shown} has no picture inside it (it is drawn as lines or text). Export those pages as pictures (PNG or JPG) and bring them in as files.")
    return out


def _collect(d: str, token: str, sources: list[str], problems: list[str]) -> list[dict]:
    stage = _staging(d, token)
    found: list[tuple[str, str]] = []
    for s in sources:
        s = os.path.abspath(str(s or ""))
        if os.path.isdir(s):
            base = os.path.basename(s.rstrip("\\/")) or "folder"
            for root, dirs, files in os.walk(s):
                dirs[:] = sorted(x for x in dirs if not x.startswith("."))
                for f in sorted(files):
                    if f.startswith(".") or not f.lower().endswith(WANTED + (".zip",)):
                        continue
                    p = os.path.join(root, f)
                    found.append((p, "/".join([base] + os.path.relpath(p, s).replace(os.sep, "/").split("/"))))
                if len(found) > MAX_FILES:
                    break
        elif os.path.isfile(s):
            found.append((s, os.path.basename(s)))
        else:
            problems.append(f"{os.path.basename(s) or s} could not be found.")
    files: list[dict] = []
    for p, rel in found:
        low = p.lower()
        if low.endswith(".zip"):
            sub = _unzip(p, os.path.join(stage, f"zip-{len(files)}"), problems)
            found_in = sub
        elif low.endswith(".pdf"):
            found_in = _pdf_pages(p, rel, os.path.join(stage, f"pdf-{len(files)}"), problems)
        else:
            found_in = [(p, rel)]
        for fp, frel in found_in:
            files.append({"path": fp, "rel": frel.replace("\\", "/")})
            if len(files) > MAX_FILES:
                problems.append(f"More than {MAX_FILES:,} files were found; only the first {MAX_FILES:,} are used.")
                return files[:MAX_FILES]
    return files


def _size_ok(path: str) -> bool:
    try:
        return os.path.getsize(path) <= MAX_IMAGE_BYTES
    except OSError:
        return False


def _image_info(path: str) -> tuple[int, int] | None:
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


# ---------------------------------------------------------------- reading the film

def _shots(d: str) -> list[dict]:
    from . import shots as S
    idx = S._index(d)
    out = []
    for sid in idx.get("order", []):
        c = S._read(S._cpath(d, sid))
        if isinstance(c, dict):
            out.append(c)
    return out


def _board(d: str) -> dict:
    return safeio.read_json(os.path.join(d, "storyboard.json"), {}) or {}


# ---------------------------------------------------------------- classifying a picture

def _classify(rel: str) -> tuple[str, str]:
    """('storyboard' | 'character' | 'environment' | 'prop' | 'unsorted', why). The nearest folder name wins, then the file name."""
    parts = rel.lower().replace("\\", "/").split("/")
    stem = os.path.splitext(parts[-1])[0]
    for name in reversed(parts):
        toks = set(_tokens(os.path.splitext(name)[0]))
        for kind, words in KIND_WORDS.items():
            if toks & words:
                return kind, f"its name says {kind}"
        if toks & STORYBOARD_WORDS:
            return "storyboard", "its name says storyboard"
    if re.search(r"\bs\d{1,3}[-_ ]\d{1,3}\b", stem) or re.search(r"\b(?:shot|sh)[-_ ]?\d+", stem) or re.search(r"\b(?:scene|sc)[-_ ]?\d+", stem):
        return "storyboard", "its name names a shot"
    return "unsorted", "its name does not say what it is"


def _shot_for(name: str, shots: list[dict]) -> tuple[dict | None, str]:
    stem = os.path.splitext(os.path.basename(name))[0].lower()
    m = re.search(r"\bs(\d{1,3})[-_ ]?(\d{1,3})\b", stem)
    by_pos = {(c["scene"], c["index"]): c for c in shots}
    if m:
        c = by_pos.get((int(m.group(1)), int(m.group(2))))
        if c:
            return c, "the file name"
    m = re.search(r"(?:scene|sc)[-_ ]?(\d+)\D{0,4}(?:shot|sh)[-_ ]?(\d+)", stem)
    if m:
        c = by_pos.get((int(m.group(1)), int(m.group(2))))
        if c:
            return c, "the file name"
    m = re.fullmatch(r"(?:\D*?)(?:shot|sh)[-_ ]?0*(\d+)(?:\D.*)?", stem)
    if m and 1 <= int(m.group(1)) <= len(shots):
        return shots[int(m.group(1)) - 1], "the file name (shot number in the film)"
    return None, ""


def _asset_name(rel: str, kind: str) -> tuple[str, str]:
    """(name, media kind) for a character, place or prop picture: the folder under the kind folder if there is one, else the file name without the words that only describe the picture."""
    parts = rel.replace("\\", "/").split("/")
    stem = os.path.splitext(parts[-1])[0]
    view = "reference"
    for t in _tokens(stem):
        if t in VIEW_WORDS:
            view = VIEW_WORDS[t]
            break
    kindwords = KIND_WORDS[kind] if kind in KIND_WORDS else set()
    folder = ""
    for i in range(len(parts) - 2, -1, -1):
        if set(_tokens(parts[i])) & kindwords and i + 1 < len(parts) - 1:
            folder = parts[i + 1]
            break
    base = folder or stem
    keep = [t for t in _tokens(base) if t not in kindwords and t not in VIEW_WORDS and t not in NOISE and not t.isdigit()]
    return " ".join(w.capitalize() for w in keep), view


def _match_entry(name: str, entries: list[dict]) -> tuple[dict | None, bool]:
    """(entry, ambiguous): the Bible entry a name belongs to, by whole words."""
    want = set(_tokens(name))
    if not want:
        return None, False
    exact = [e for e in entries if set(_tokens(e["name"])) == want]
    if len(exact) == 1:
        return exact[0], False
    part = [e for e in entries if want <= set(_tokens(e["name"])) or set(_tokens(e["name"])) <= want]
    if len(part) == 1:
        return part[0], False
    return None, len(part) > 1


# ---------------------------------------------------------------- shot list

def _read_table(path: str) -> list[dict] | None:
    raw = open(path, "rb").read(5_000_000)
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            text = ""
    if not text.strip():
        return None
    try:
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel_tab if path.lower().endswith(".tsv") else csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2:
        return None
    head = [re.sub(r"\s+", " ", c.strip().lower()) for c in rows[0]]
    col: dict[str, int] = {}
    for key, names in COLUMNS.items():
        for i, h in enumerate(head):
            if h in names and key not in col:
                col[key] = i
    if not ({"action", "framing", "movement", "title", "dialogue", "duration"} & set(col)) or not ({"id", "shot", "scene"} & set(col)):
        return None
    out = []
    for r in rows[1:MAX_ROWS + 1]:
        out.append({k: (r[i].strip() if i < len(r) else "") for k, i in col.items()})
    return out


def _norm(table: dict[str, str], value: str) -> str:
    v = re.sub(r"\s+", " ", value.strip().lower()).strip(" .")
    return table.get(v) or table.get(v.replace("-", " ")) or ""


def _row_patch(row: dict) -> tuple[dict, list[str]]:
    """The patch a row asks for, and the camera words that were not in the lists (kept as a note instead of being lost)."""
    patch: dict = {}
    extra: list[str] = []
    if row.get("title"):
        patch["title"] = _text(row["title"], 120)
    if row.get("action"):
        patch["action"] = _text(row["action"])
    if row.get("sound"):
        patch["sound"] = _text(row["sound"])
    cam: dict = {}
    for key, tab, label in (("framing", FRAMING_WORDS, "Framing"), ("angle", ANGLE_WORDS, "Angle"), ("lens", LENS_WORDS, "Lens"), ("movement", MOVE_WORDS, "Movement")):
        if row.get(key):
            n = _norm(tab, row[key])
            if n:
                cam[key] = n
            else:
                extra.append(f"{label}: {row[key]}")
    if cam:
        patch["camera"] = cam
    if row.get("lighting"):
        patch["lighting"] = {"description": _text(row["lighting"])}
    gen: dict = {}
    if row.get("duration"):
        m = re.search(r"(\d+(?:[.,]\d+)?)", row["duration"].replace(",", "."))
        if m:
            gen["duration"] = float(m.group(1))
    notes = " | ".join(x for x in ([row["notes"]] if row.get("notes") else []) + extra if x)
    if notes:
        gen["notes"] = _text(notes)
    if gen:
        patch["generation"] = gen
    if row.get("dialogue"):
        patch["dialogue"] = [{"speaker": _text(row.get("speaker"), 60) or _text((row.get("characters") or "").split(",")[0], 60), "line": _text(row["dialogue"]), "paren": ""}]
    if row.get("characters"):
        names = [n.strip() for n in re.split(r"[,;/&]|\band\b", row["characters"]) if n.strip()]
        patch["characters"] = [{"name": n} for n in names[:20]]
    if row.get("location"):
        patch["environment"] = {"name": _text(row["location"], 80)}
    return patch, extra


def _differences(c: dict | None, patch: dict) -> tuple[list[dict], list[str]]:
    """[{field, label, old, new}] for what would change, and the labels of fields that already hold something the person may have written."""
    changes, over = [], []
    drafted = c is None or not c.get("edited")

    def add(label: str, old, new, empty_like: tuple = ("", None, [], 3.0, "locked off", "eye level")):
        if new in ("", None, []) or old == new:
            return
        changes.append({"label": label, "old": old if old not in (None, []) else "", "new": new})
        if old not in empty_like and not drafted:
            over.append(label)
    cur = c or {}
    for k, label in (("title", "Title"), ("action", "What happens"), ("sound", "Sound note")):
        if k in patch:
            add(label, cur.get(k, ""), patch[k])
    for k, v in (patch.get("camera") or {}).items():
        add(k.capitalize(), (cur.get("camera") or {}).get(k, ""), v)
    if "lighting" in patch:
        add("Lighting", (cur.get("lighting") or {}).get("description", ""), patch["lighting"]["description"])
    g = patch.get("generation") or {}
    if "duration" in g:
        add("Length (s)", (cur.get("generation") or {}).get("duration", 3.0), g["duration"])
    if "notes" in g:
        add("Notes", (cur.get("generation") or {}).get("notes", ""), g["notes"])
    if "dialogue" in patch:
        old = " / ".join(f"{x.get('speaker', '')}: {x.get('line', '')}" for x in cur.get("dialogue", []))
        add("Dialogue", old, " / ".join(f"{x['speaker']}: {x['line']}" for x in patch["dialogue"]))
    if "characters" in patch:
        old = ", ".join(x["name"] for x in cur.get("characters", []))
        add("Characters", old, ", ".join(x["name"] for x in patch["characters"]))
    if "environment" in patch:
        add("Place", (cur.get("environment") or {}).get("name", ""), patch["environment"]["name"])
    return changes, over


# ---------------------------------------------------------------- the plan

def _items(d: str, files: list[dict], choices: dict) -> tuple[list[dict], list[str]]:
    """The plan's items for these files, with the person's choices (`as`, `target`, `on`) applied. Pure reading: the film and the files are not changed."""
    from . import bible as B
    problems: list[str] = []
    shots = _shots(d)
    bible = B.load(d)
    board = _board(d)
    items: list[dict] = []
    used_boards: dict[str, str] = {}

    def choice(iid: str) -> dict:
        v = choices.get(iid)
        return v if isinstance(v, dict) else {}

    pictures, tables, notes = [], [], []
    for f in files:
        low = f["path"].lower()
        iid = "f" + hashlib.sha1(f["rel"].encode("utf-8"), usedforsecurity=False).hexdigest()[:10]
        f["id"] = iid
        if low.endswith(IMG):
            pictures.append(f)
        elif low.endswith(TABLE):
            tables.append(f)
        elif low.endswith(TEXT):
            notes.append(f)

    # ---- pictures
    unmatched_boards: list[dict] = []
    for f in sorted(pictures, key=lambda x: _natural(x["rel"])):
        ch = choice(f["id"])
        info = _image_info(f["path"])
        item = {"id": f["id"], "file": f["path"], "rel": f["rel"], "on": True, "blocked": "", "notes": []}
        if not _size_ok(f["path"]) or info is None:
            item.update({"type": "skip", "title": f["rel"], "on": False, "blocked": "This picture is too big (over 25 MB) or can't be read as a picture."})
            items.append(item)
            continue
        if min(info) < MIN_SIDE:
            item.update({"type": "skip", "title": f["rel"], "on": False, "blocked": "This picture is tiny, so it was left out."})
            items.append(item)
            continue
        kind, why = _classify(f["rel"])
        if ch.get("as") in ("storyboard", "character", "environment", "prop", "skip"):
            kind, why = ch["as"], "you chose this"
        item["size"] = list(info)
        item["why"] = why
        if kind == "skip":
            item.update({"type": "skip", "title": f["rel"], "on": False})
        elif kind == "storyboard":
            item["type"] = "storyboard"
            target = None
            if ch.get("target"):
                target = next((c for c in shots if c["id"] == ch["target"]), None)
                item["how"] = "you chose this shot"
            else:
                target, how = _shot_for(f["rel"], shots)
                item["how"] = how
            if target is None:
                unmatched_boards.append(item)
            else:
                item["shot"] = target["id"]
            item["title"] = f["rel"]
            items.append(item)
        elif kind == "unsorted":
            item.update({"type": "unsorted", "title": f["rel"], "on": False, "blocked": "Say what this picture is: a storyboard panel, or a picture of a character, a place or a prop."})
            items.append(item)
        else:
            name, view = _asset_name(f["rel"], kind)
            if ch.get("new_name"):
                name = _text(ch["new_name"], 80)
            entries = bible[B.LISTKEY[kind]]
            entry, ambiguous = _match_entry(name, entries)
            if ch.get("target"):
                entry = next((e for e in entries if e["id"] == ch["target"]), None)
            item.update({"type": "asset", "kind": kind, "name": name, "media_kind": view, "title": f["rel"], "entry": entry["id"] if entry else None,
                         "entry_name": entry["name"] if entry else "", "create": entry is None and bool(name)})
            if entry is None and not name:
                item.update({"on": False, "blocked": "Say whose picture this is."})
            elif ambiguous:
                item.update({"on": False, "blocked": f"More than one {kind} could be \"{name}\": choose which."})
            elif entry:
                try:
                    digest = _sha(f["path"])
                    existing = set()
                    for m in entry.get("media", []):
                        p = os.path.join(d, m.get("path", ""))
                        if os.path.isfile(p):
                            existing.add(_sha(p))
                    if digest in existing:
                        item.update({"on": False, "blocked": f"{entry['name']} already has this exact picture."})
                except OSError:
                    pass
            items.append(item)
    # pictures that name no shot: matched in order, but only when the counts agree (otherwise the person says which)
    taken = {i["shot"] for i in items if i["type"] == "storyboard" and i.get("shot")}
    free = [c for c in shots if c["id"] not in taken]
    if unmatched_boards:
        if len(unmatched_boards) == len(free):
            for it, c in zip(unmatched_boards, free):
                it["shot"], it["how"] = c["id"], "their order"
        else:
            for it in unmatched_boards:
                it.update({"on": False, "blocked": f"{len(unmatched_boards)} pictures and {len(free)} shots without one: say which shot this belongs to."})
    for it in items:
        if it["type"] != "storyboard" or not it.get("shot"):
            continue
        c = next(x for x in shots if x["id"] == it["shot"])
        it["shot_label"] = f"{c['id']}" + (f" · {c['title']}" if c.get("title") and c["title"] != "New shot" else "")
        if it["shot"] in used_boards:
            it.update({"on": False, "blocked": f"{used_boards[it['shot']]} is already going to this shot: only one panel is kept for a shot."})
            continue
        used_boards[it["shot"]] = it["rel"]
        if c.get("locks", {}).get("storyboard"):
            it.update({"on": False, "blocked": "This shot's storyboard is locked. Unlock it first."})
        elif board.get(it["shot"]):
            it.update({"on": False, "replaces": True, "notes": ["This shot already has a chosen panel. Tick to use this one instead; the old one stays in the film."]})
    # ---- shot lists
    for f in tables:
        ch = choice(f["id"])
        rows = _read_table(f["path"])
        if rows is None:
            items.append({"id": f["id"], "type": "skip", "title": f["rel"], "on": False, "blocked": "This table has no shot or scene column that FilmCrafter can use, so it was left out.", "notes": []})
            continue
        by_pos = {(c["scene"], c["index"]): c for c in shots}
        by_id = {c["id"].lower(): c for c in shots}
        scene_count: dict[int, int] = {}
        for c in shots:
            scene_count[c["scene"]] = scene_count.get(c["scene"], 0) + 1
        for n, row in enumerate(rows, 1):
            iid = f"{f['id']}r{n}"
            rc = choice(iid)
            c = None
            if row.get("id"):
                c = by_id.get(row["id"].strip().lower())
            if c is None and row.get("shot"):
                sh = re.search(r"\d+", row["shot"])
                sc = re.search(r"\d+", row.get("scene", ""))
                if sh and sc:
                    c = by_pos.get((int(sc.group()), int(sh.group())))
                elif sh and 1 <= int(sh.group()) <= len(shots) and not row.get("scene"):
                    c = shots[int(sh.group()) - 1]
            patch, extra = _row_patch(row)
            sc_num = int(re.search(r"\d+", row["scene"]).group()) if re.search(r"\d+", row.get("scene", "") or "") else None
            label = row.get("id") or ("scene " + row["scene"] + ", " if row.get("scene") else "") + "shot " + row.get("shot", str(n))
            if c is None:
                if sc_num is not None and sc_num in scene_count and patch:
                    changes, _ = _differences(None, patch)
                    items.append({"id": iid, "type": "newshot", "scene": sc_num, "title": f"New shot in scene {sc_num} ({label})", "patch": patch, "changes": changes, "on": bool(rc.get("on", False)),
                                  "blocked": "", "notes": ["There is no such shot yet. Tick to add one to the scene."], "rel": f["rel"]})
                else:
                    items.append({"id": iid, "type": "skip", "title": f"{f['rel']}: {label}", "on": False, "blocked": "No shot in the film matches this row.", "notes": []})
                continue
            changes, over = _differences(c, patch)
            if not changes:
                continue
            it = {"id": iid, "type": "shotrow", "shot": c["id"], "title": f"{c['id']}" + (f" · {c['title']}" if c.get("title") and c["title"] != "New shot" else ""), "patch": patch, "changes": changes,
                  "on": not over, "blocked": "", "notes": [f"This replaces what is written for: {', '.join(over)}. Tick to allow it."] if over else [], "rel": f["rel"]}
            if c.get("locks", {}).get("storyboard") and any(k in patch for k in ("camera", "characters", "environment")):
                it.update({"on": False, "blocked": "This shot's storyboard is locked, so its framing can't change."})
            items.append(it)
    # ---- notes
    bible_rules = bible.get("rules", {})
    for f in notes:
        try:
            with open(f["path"], "rb") as fh:
                raw = fh.read(MAX_NOTE + 1)
            text = raw[:MAX_NOTE].decode("utf-8-sig", "replace").strip()
        except OSError:
            continue
        if not text:
            continue
        toks = set(_tokens(os.path.splitext(os.path.basename(f["rel"]))[0]))
        target = next((t for t, words in NOTE_TARGETS if toks & words), "keep")
        ch = choice(f["id"])
        if ch.get("target") in ("keep", "world", "tone", "rules", "avoid"):
            target = ch["target"]
        it = {"id": f["id"], "type": "note", "file": f["path"], "rel": f["rel"], "title": f["rel"], "target": target, "excerpt": text[:300], "length": len(text), "on": True, "blocked": "", "notes": []}
        if target != "keep":
            room = BIBLE_FIELD_ROOM - len(bible_rules.get(target, ""))
            if len(text) > room:
                it.update({"target": "keep", "notes": [f"Too long to add to the Bible's {target} (it holds {BIBLE_FIELD_ROOM:,} characters): it is kept as a note instead."]})
        items.append(it)
    return items, problems


def _public(it: dict) -> dict:
    """What the screen needs: the item without its patch, with the picture's path so it can be shown."""
    out = {k: v for k, v in it.items() if k not in ("file", "patch")}
    if it.get("type") in ("storyboard", "asset", "unsorted") and it.get("file"):
        out["preview"] = it["file"]
    return out


def scan(d: str, sources: list[str]) -> dict:
    """Read the chosen files and say where each would go. Free; the film is not changed."""
    _film(d)
    if not isinstance(sources, list) or not sources:
        raise SystemExit("Choose some files or a folder first.")
    token = uuid.uuid4().hex[:12]
    problems: list[str] = []
    files = _collect(d, token, [str(s) for s in sources][:50], problems)
    if not files:
        raise SystemExit("Nothing FilmCrafter can use was found there. It reads pictures (PNG, JPG, WebP), PDFs with pictures in them, shot lists (CSV or TSV), notes (TXT or Markdown) and zip files holding those.")
    items, more = _items(d, files, {})
    problems += more
    os.makedirs(os.path.dirname(_plan_path(d, token)), exist_ok=True)
    safeio.write_json(_plan_path(d, token), {"token": token, "at": int(time.time()), "sources": [os.path.basename(str(s).rstrip("\\/")) for s in sources][:50],
                                             "files": [{"path": f["path"], "rel": f["rel"], "size": os.path.getsize(f["path"]), "mtime": int(os.path.getmtime(f["path"]))} for f in files if os.path.isfile(f["path"])]}, backup=False)
    _tidy(d, keep=token)
    return {"token": token, "items": [_public(i) for i in items], "problems": problems, "shots": [{"id": c["id"], "scene": c["scene"], "title": c.get("title", "")} for c in _shots(d)],
            "counts": _counts(items), "enums": {"storyboard": "storyboard", "kinds": ["storyboard", "character", "environment", "prop", "skip"]},
            "note": "Nothing has been added to the film yet. Look through the plan, change what is not right, then choose Bring it in."}


def _counts(items: list[dict]) -> dict:
    c: dict = {}
    for i in items:
        if i["on"] and not i["blocked"]:
            c[i["type"]] = c.get(i["type"], 0) + 1
    return c


def _tidy(d: str, keep: str) -> None:
    """Unpacked copies and plans of earlier scans are cache: remove the ones older than a day (and never the one in use)."""
    base = os.path.join(d, "cache", "materials")
    try:
        for name in os.listdir(base):
            p = os.path.join(base, name)
            if keep in name or time.time() - os.path.getmtime(p) < 86400:
                continue
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
    except OSError:
        pass


# ---------------------------------------------------------------- applying

def _load_plan(d: str, token: str) -> tuple[dict, list[dict]]:
    if not TOKEN.match(str(token or "")):
        raise SystemExit("That plan is not valid. Choose the files again.")
    plan = safeio.read_json(_plan_path(d, token), None)
    if not isinstance(plan, dict) or not isinstance(plan.get("files"), list):
        raise SystemExit("That plan has expired. Choose the files again.")
    stage = os.path.abspath(_staging(d, token))
    files = []
    for f in plan["files"]:
        p = str(f.get("path", ""))
        files.append({"path": p, "rel": f.get("rel", ""), "was": (f.get("size"), f.get("mtime")), "staged": os.path.abspath(p).startswith(stage + os.sep)})
    return plan, files


def apply(d: str, token: str, choices: dict) -> dict:
    """Put the ticked items into the film. One item that cannot be done never stops the others; each is reported."""
    from . import bible as B, filmbackup, make as M, shots as S
    _film(d)
    plan, files = _load_plan(d, token)
    choices = choices if isinstance(choices, dict) else {}
    changed = []
    for f in files:
        try:
            if (os.path.getsize(f["path"]), int(os.path.getmtime(f["path"]))) != tuple(f["was"]):
                changed.append(f["rel"])
        except OSError:
            changed.append(f["rel"])
    items, _ = _items(d, [dict(f) for f in files if f["rel"] not in changed], choices)
    ticked = {k: bool(v.get("on")) for k, v in choices.items() if isinstance(v, dict) and "on" in v}
    chosen = [i for i in items if (ticked.get(i["id"], i["on"])) and not i["blocked"]]
    if not chosen:
        return {"applied": [], "skipped": [], "failed": [], "changed_since_scan": changed, "message": "Nothing was ticked, so nothing was added."}
    try:
        snap = filmbackup.make(d, "before bringing in materials")
    except SystemExit:
        snap = {}
    applied, failed = [], []
    refs = bool(choices.get("_options", {}).get("reference", True)) if isinstance(choices.get("_options"), dict) else True
    made_entries: dict[tuple[str, str], str] = {}

    def done(it: dict, what: str):
        applied.append({"id": it["id"], "type": it["type"], "title": it.get("title", ""), "what": what})

    for it in chosen:
        try:
            if it["type"] == "storyboard":
                M.import_media(d, it["shot"], "storyboard", it["file"])
                if refs:
                    try:
                        M.use_storyboard_as_reference(d, it["shot"])
                    except SystemExit:
                        pass
                done(it, f"Panel for {it['shot']}" + (" (also the framing reference for its hero picture)" if refs else ""))
            elif it["type"] == "asset":
                kind, eid = it["kind"], it.get("entry")
                if not eid:
                    key = (kind, it["name"].lower())
                    eid = made_entries.get(key)
                    if not eid:
                        res = B.upsert(d, kind, {"name": it["name"]})
                        eid = res["id"]
                        made_entries[key] = eid
                B.add_media(d, kind, eid, it["file"], label=os.path.splitext(os.path.basename(it["rel"]))[0][:80], media_kind=it["media_kind"])
                done(it, f"Picture for {it.get('entry_name') or it['name']}" + (" (new entry)" if it.get("create") else ""))
            elif it["type"] == "shotrow":
                S.set_fields(d, it["shot"], it["patch"])
                done(it, f"Updated {it['shot']}: " + ", ".join(c["label"] for c in it["changes"]))
            elif it["type"] == "newshot":
                res = S.add(d, it["scene"])
                S.set_fields(d, res["id"], it["patch"])
                done(it, f"Added {res['id']}")
            elif it["type"] == "note":
                folder = os.path.join(d, "materials", "notes")
                os.makedirs(folder, exist_ok=True)
                dst = os.path.join(folder, file_part(os.path.basename(it["rel"]), 80))
                n = 2
                while os.path.exists(dst):
                    stem, ext = os.path.splitext(file_part(os.path.basename(it["rel"]), 80))
                    dst = os.path.join(folder, f"{stem}-{n}{ext}")
                    n += 1
                shutil.copyfile(it["file"], dst)
                what = "Kept as a note"
                if it["target"] != "keep":
                    text = open(it["file"], "rb").read(MAX_NOTE).decode("utf-8-sig", "replace").strip()
                    cur = B.load(d)["rules"].get(it["target"], "")
                    B.update_rules(d, {"rules": {it["target"]: (cur + "\n\n" if cur else "") + text}})
                    what = f"Added to the Bible's {it['target']} (and kept as a note)"
                done(it, what)
        except SystemExit as e:
            failed.append({"id": it["id"], "title": it.get("title", ""), "why": str(e)})
        except Exception as e:                              # one bad file must not stop the rest
            failed.append({"id": it["id"], "title": it.get("title", ""), "why": f"{type(e).__name__}: {e}"})
    log = safeio.read_json(os.path.join(d, "materials", "imports.json"), {"imports": []}) or {"imports": []}
    log.setdefault("imports", []).append({"at": int(time.time()), "sources": plan.get("sources", []), "backup": snap.get("name", ""), "applied": [{k: a[k] for k in ("type", "title", "what")} for a in applied], "failed": len(failed)})
    log["imports"] = log["imports"][-200:]
    os.makedirs(os.path.join(d, "materials"), exist_ok=True)
    safeio.write_json(os.path.join(d, "materials", "imports.json"), log)
    skipped = [{"id": i["id"], "title": i.get("title", ""), "why": i["blocked"] or "not ticked"} for i in items if i not in chosen]
    return {"applied": applied, "failed": failed, "skipped": skipped, "changed_since_scan": changed, "backup": snap.get("name", ""),
            "message": f"{len(applied)} added to the film" + (f", {len(failed)} could not be added" if failed else "") + ". Nothing was bought or sent anywhere."}


def review(d: str, token: str, choices: dict) -> dict:
    """The plan again, as it would be with the person's choices (a picture's kind, its shot, a name). Free; nothing is changed."""
    _film(d)
    plan, files = _load_plan(d, token)
    gone = [f["rel"] for f in files if not os.path.isfile(f["path"])]
    items, problems = _items(d, [dict(f) for f in files if f["rel"] not in gone], choices if isinstance(choices, dict) else {})
    return {"token": token, "items": [_public(i) for i in items], "problems": problems + [f"{r} is no longer there." for r in gone], "counts": _counts(items)}


def history(d: str) -> dict:
    _film(d)
    log = safeio.read_json(os.path.join(d, "materials", "imports.json"), {"imports": []}) or {"imports": []}
    return {"imports": list(reversed(log.get("imports", [])))[:50]}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="materials")
    ap.add_argument("action", choices=["scan", "apply", "review", "history"])
    ap.add_argument("film")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    try:
        x = json.loads(a.data or "{}")
        x = x if isinstance(x, dict) else {}
        d = os.path.abspath(a.film)
        if a.action == "scan":
            res = scan(d, x.get("sources") or [])
        elif a.action == "apply":
            res = apply(d, x.get("token", ""), x.get("choices") or {})
        elif a.action == "review":
            res = review(d, x.get("token", ""), x.get("choices") or {})
        else:
            res = history(d)
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
