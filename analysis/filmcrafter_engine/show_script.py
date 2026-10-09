"""Script to show: turn a musical's script (text, Markdown, Fountain-style or PDF) into the acts, numbers and spoken scenes
of a show.

The script is plain lines. Markers go at the start of a line (any capitals):

  TITLE: My Musical              optional, first
  ACT 1                          starts an act (ACT ONE: The Market works too)
  SCENE: The Market              a spoken scene; the lines after it are dialogue
  ADA (happy): Fresh bread!      a spoken line (the emotion is optional)
  (Ada wipes the counter.)       a stage direction: kept as the scene's setting
  SONG: Opening Number           a number (NUMBER: works too); the lines after it are its lyrics
  [Verse 1] ...                  lyrics are kept exactly as written

A script written the screenplay way is read too (no markers needed). Markdown headings (# ...) are the sections: VERSE, PRE-CHORUS,
CHORUS, BRIDGE, DANCE BREAK and the like are music (consecutive ones become one number); SCENE, COLD OPEN, OUTRO and any heading
without a musical word are spoken scenes. A character's name in capitals on its own line, with the words directly under it, is a
spoken line in a scene and a sung line in a number. ## and ### headings and action paragraphs become the scene's setting, and
`# END` stops the reading.

Nothing is spent and nothing is run: the script is read as data. Reading is bounded (file size, pages, items, lines,
text length), every title becomes a folder name only through show._slug, and the importer only adds to a show, it never
deletes. Songs are not in a script, so a number starts without audio until a recorded song is attached (or matched by
name from a folder of songs).

  python -m filmcrafter_engine.show <preview_script|import_script> <show_dir> --data '{"file": "...", "songs_dir": "..."}'
"""
from __future__ import annotations

import os
import re

MAX_BYTES = 2_000_000
MAX_PDF_BYTES = 20_000_000
MAX_PAGES = 400
MAX_ITEMS = 300
MAX_LINES = 5000
MAX_LINE = 1500
MAX_WARNINGS = 20
AUDIO = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg"}
TEXT = {".txt", ".md", ".fountain", ".text", ""}

_ACT = re.compile(r"^act\s+(\d{1,3}|[ivxlc]{1,6}|one|two|three|four|five|six|seven|eight|nine|ten)\b\s*(?:[:\-–—]\s*(.{1,50}))?$", re.I)
_SCENE = re.compile(r"^scene\s*(?:\d+\s*)?[:\-–—]\s*(.{1,80})$", re.I)
_SONG = re.compile(r"^(?:song|number)\s*(?:\d+\s*)?[:\-–—]\s*(.{1,80})$", re.I)
_TITLE = re.compile(r"^title\s*:\s*(.{1,80})$", re.I)
_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9'.\- ]{0,38}?)\s*(?:\(([^)\n]{1,30})\))?\s*:\s*(\S.*)$")
_DIRECTION = re.compile(r"^[(\[](.*)[)\]]$")


def read_script(path: str) -> str:
    """The script's text. Plain text files and PDFs only, within fixed size and page limits."""
    if not os.path.isfile(path):
        raise SystemExit("That script file can't be found.")
    ext = os.path.splitext(path)[1].lower()
    size = os.path.getsize(path)
    if ext == ".pdf":
        if size > MAX_PDF_BYTES:
            raise SystemExit("That PDF is too large to read as a script (20 MB at most).")
        try:
            from pypdf import PdfReader
        except ImportError:
            raise SystemExit("Reading PDFs needs the FilmCrafter engine's PDF component. Save the script as a text file instead.")
        pages = PdfReader(path).pages
        if len(pages) > MAX_PAGES:
            raise SystemExit(f"That script has {len(pages)} pages; {MAX_PAGES} is the most FilmCrafter reads.")
        return "\n".join(p.extract_text() or "" for p in pages)
    if ext not in TEXT:
        raise SystemExit("Use a text, Markdown or PDF file for the script.")
    if size > MAX_BYTES:
        raise SystemExit("That script file is too large (2 MB of text at most).")
    with open(path, "rb") as f:
        raw = f.read(MAX_BYTES + 1)
    if b"\x00" in raw[:4096]:
        raise SystemExit("That doesn't look like a text file.")
    return raw.decode("utf-8-sig", errors="replace")


def _name(raw: str) -> str:
    raw = " ".join(raw.split())
    return " ".join(w[:1] + w[1:].lower() for w in raw.split()) if raw.isupper() else raw


def _emotion(raw: str | None) -> str | None:
    from .voices import EMOTIONS
    e = (raw or "").strip().lower()
    return e if e in EMOTIONS else None


def parse(text: str, one_song: bool = False) -> dict:
    """The script as {title, acts: [{name, items: [number | scene]}], characters, warnings, totals}. Pure: no files, no network.
    Marker scripts (SONG: / SCENE:) are read as written; anything else is read as a screenplay with # headings."""
    lines = [x.strip() for x in text.splitlines()]
    if any(_SONG.match(x) or _SCENE.match(x) for x in lines):
        return _parse_markers(text)
    plan = _parse_screenplay(text, one_song)
    if plan is None:
        raise SystemExit("No SONG or SCENE found. Start a number with \"SONG: Title\" and a scene with \"SCENE: Title\", or use # headings "
                         "such as # VERSE 1, # CHORUS and # SCENE for the sections of a screenplay.")
    return plan


def _parse_markers(text: str) -> dict:
    warnings: list[str] = []

    def warn(msg: str) -> None:
        if len(warnings) < MAX_WARNINGS:
            warnings.append(msg)

    title, acts, cur, item = "", [], None, None
    chars: dict[str, str] = {}
    ignored = total_lines = 0

    def new_act(name: str):
        nonlocal cur
        cur = {"name": name[:60], "items": []}
        acts.append(cur)

    def new_item(kind: str, name: str):
        nonlocal item
        if cur is None:
            new_act("Act 1")
        if sum(len(a["items"]) for a in acts) >= MAX_ITEMS:
            raise SystemExit(f"That script has more than {MAX_ITEMS} numbers and scenes; split it into several scripts.")
        item = {"kind": kind, "title": " ".join(name.split())[:80] or ("Song" if kind == "number" else "Scene")}
        item.update({"lyrics": []} if kind == "number" else {"setting": "", "lines": []})
        cur["items"].append(item)

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if item and item["kind"] == "number" and item["lyrics"] and item["lyrics"][-1] != "":
                item["lyrics"].append("")
            continue
        if m := _TITLE.match(line):
            title = title or " ".join(m.group(1).split())
        elif m := _ACT.match(line):
            g = m.group(1)
            num = g.upper() if re.fullmatch(r"[ivxlc]{1,6}", g, re.I) else g.title()
            new_act(f"Act {num}" + (f": {' '.join(m.group(2).split())}" if m.group(2) else ""))
            item = None
        elif m := _SONG.match(line):
            new_item("number", m.group(1))
        elif m := _SCENE.match(line):
            new_item("scene", m.group(1))
        elif item is None:
            ignored += 1
        elif item["kind"] == "number":
            item["lyrics"].append(line[:MAX_LINE])
        else:
            total_lines += 1
            if total_lines > MAX_LINES:
                raise SystemExit(f"That script has more than {MAX_LINES} lines of dialogue; split it into several scripts.")
            d = _DIRECTION.match(line)
            m = None if d else _LINE.match(line)
            if d:
                item["setting"] = (item["setting"] + " " + d.group(1).strip()).strip()[:1500]
            elif m:
                who = _name(m.group(1))
                key = who.lower()
                chars.setdefault(key, who)
                item["lines"].append({"character": chars[key], "text": m.group(3).strip()[:MAX_LINE], "emotion": _emotion(m.group(2))})
                if m.group(2) and not item["lines"][-1]["emotion"]:
                    item["lines"][-1]["text"] = f"({m.group(2).strip()}) " + item["lines"][-1]["text"]
            elif item["lines"]:                      # a wrapped line continues the one before it
                item["lines"][-1]["text"] = (item["lines"][-1]["text"] + " " + line)[:MAX_LINE]
            else:
                item["setting"] = (item["setting"] + " " + line).strip()[:1500]
    if ignored:
        warn(f"{ignored} line{'s' if ignored != 1 else ''} before the first SONG or SCENE {'were' if ignored != 1 else 'was'} ignored.")
    for a in acts:
        for it in a["items"]:
            if it["kind"] == "number":
                it["lyrics"] = "\n".join(it["lyrics"]).strip()
            elif not it["lines"]:
                warn(f"The scene \"{it['title']}\" has no spoken lines.")
    acts = [a for a in acts if a["items"]]
    if not acts:
        raise SystemExit("No SONG or SCENE found. Start a number with \"SONG: Title\" and a scene with \"SCENE: Title\".")
    items = [i for a in acts for i in a["items"]]
    return {"title": title, "acts": acts, "characters": sorted(chars.values()), "warnings": warnings,
            "totals": {"acts": len(acts), "numbers": sum(i["kind"] == "number" for i in items),
                       "scenes": sum(i["kind"] == "scene" for i in items), "lines": sum(len(i.get("lines", [])) for i in items)}}


_HEAD = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_CUE = re.compile(r"^([A-Z][A-Z0-9'.\- ]{1,38}?)\s*(?:\(([^)\n]{1,20})\))?$")
_MUSICAL = re.compile(r"\b(verse|pre-?chorus|chorus|bridge|dance break|refrain|hook|reprise|finale|interlude|song|number|anthem)\b", re.I)
_SPOKEN = re.compile(r"\b(scene|cold open|intro|outro|stinger|epilogue|prologue|credits?)\b", re.I)
_OWN_SCENE = re.compile(r"stinger|post-credit|epilogue|prologue|cold open", re.I)
_SLUG = re.compile(r"^(?:INT|EXT)\.", re.I)
_OFFSCREEN = re.compile(r"^(?:O\.?S\.?|V\.?O\.?|O\.?C\.?|CONT.?D|OFF)$", re.I)
_DASH = re.compile(r"\s+[\u2014\u2013-]+\s+|\s*:\s+")


def _md(line: str) -> str:
    """A line without markdown emphasis or quote marks, with curly quotes made plain."""
    return line.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"').replace("**", "").replace("__", "").strip().lstrip(">").strip("*_ ")


def _heading_parts(text: str) -> tuple[str, str]:
    """('VERSE 1', 'THE QUEEN ADDRESSES HER SUBJECTS') from 'VERSE 1 \u2014 THE QUEEN ADDRESSES HER SUBJECTS'."""
    bits = _DASH.split(_md(text), maxsplit=1)
    return bits[0].strip(), (bits[1].strip() if len(bits) > 1 else "")


def _nice(text: str) -> str:
    text = " ".join(text.split())
    return " ".join(w[:1] + w[1:].lower() for w in text.split()) if text.isupper() else text


def _parse_screenplay(text: str, one_song: bool) -> dict | None:
    """Sections from # headings; see the module notes. Returns None when the text has no headings and no character cues."""
    warnings: list[str] = []
    chars: dict[str, str] = {}
    title = subtitle = ""
    acts: list[dict] = []
    sections: list[dict] = []
    cur: dict | None = None
    act_name = "Act 1"
    dialogue_lines = 0

    def close() -> None:
        nonlocal cur
        if cur is not None:
            sections.append(cur)
        cur = None

    def open_section(heading: str) -> None:
        nonlocal cur
        close()
        key, rest = _heading_parts(heading)
        musical = bool(_MUSICAL.search(key)) and not _SPOKEN.search(key)
        label = _nice(key) + (f": {_nice(rest)}" if rest and not key.lower() == "scene" else "")
        name = _nice(rest) if key.lower() == "scene" and rest else label
        cur = {"musical": musical, "title": name[:80], "tag": _nice(key)[:60], "lyrics": [], "lines": [], "setting": "", "act": act_name,
               "heard": False}

    def say(extra: str) -> None:
        if cur is not None and not cur["musical"]:
            cur["setting"] = (cur["setting"] + " " + extra).strip()[:1500]

    blocks: list[list[str]] = []
    block: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or re.fullmatch(r"\s*(?:-{3,}|\*{3,}|_{3,})\s*", line):
            if block:
                blocks.append(block)
            block = []
        elif _HEAD.match(line.strip()):
            if block:
                blocks.append(block)
            blocks.append([line.strip()])
            block = []
        else:
            block.append(line.strip())
    if block:
        blocks.append(block)

    cues = 0
    title_card = False
    for b in blocks:
        h = _HEAD.match(b[0]) if len(b) == 1 else None
        if h:
            level, head = len(h.group(1)), _md(h.group(2))
            if level == 1:
                if not title:
                    title = head
                    continue
                if head.upper() == "END":
                    break
                if title_card:                       # "### TITLE CARD:" then "# I AM YOUR MOTHER!": the card, not a new section
                    title_card = False
                    say(f"Title card: {head}")
                    continue
                if (a := _ACT.match(head)):
                    close()
                    act_name = f"Act {a.group(1).upper() if re.fullmatch(r'[ivxlc]{1,6}', a.group(1), re.I) else a.group(1).title()}" + (f": {a.group(2)}" if a.group(2) else "")
                    continue
                open_section(head)
            elif level == 2 and cur is None:
                subtitle = re.sub(r"^episode\s*\d+\s*[:\-\u2014]\s*", "", head, flags=re.I)
            elif level == 3 and _OWN_SCENE.search(head) and not _SLUG.match(head) and (cur is not None or sections):
                open_section(head)
            elif cur is not None:
                title_card = bool(re.search(r"title card", head, re.I))
                say(head)
            continue
        if cur is None:
            continue
        title_card = False
        lines = [_md(x) for x in b if _md(x)]
        if not lines:
            continue
        m = _CUE.match(lines[0]) if len(lines) >= 2 else None
        if m and not re.search(r"[a-z]", m.group(1)) and not re.search(r"[.!?:;,]$", lines[0]):
            name = _name(m.group(1))
            key = name.lower()
            chars.setdefault(key, name)
            words = [x for x in lines[1:] if not _DIRECTION.match(x) and re.search(r"\w", x)]   # "..." alone is a pause, not a line
            if not words:
                continue
            cues += 1
            cur["heard"] = True
            if cur["musical"]:
                cur["lyrics"] += [x[:MAX_LINE] for x in words] + [""]
            else:
                dialogue_lines += 1
                if dialogue_lines > MAX_LINES:
                    raise SystemExit(f"That script has more than {MAX_LINES} lines of dialogue; split it into several scripts.")
                emo = _emotion(m.group(2)) if m.group(2) and not _OFFSCREEN.match(m.group(2).strip()) else None
                cur["lines"].append({"character": chars[key], "text": " ".join(words)[:MAX_LINE], "emotion": emo})
        else:
            say(" ".join(lines))
    close()
    if not sections or not (cues or any(s["musical"] for s in sections)):
        return None

    # Consecutive music sections become one number (or all of them, when the music is one recorded song).
    items_by_act: dict[str, list[dict]] = {}
    order: list[str] = []
    number: dict | None = None
    one: dict | None = None
    nice_title = _name(subtitle or title)

    def push(act: str, it: dict) -> None:
        if act not in items_by_act:
            items_by_act[act] = []
            order.append(act)
        items_by_act[act].append(it)

    def flush_number() -> None:
        nonlocal number
        number = None

    for sec in sections:
        if sec["musical"]:
            tag = f"[{sec['tag']}]"
            body = "\n".join(x for x in sec["lyrics"]).strip()
            chunk = tag + ("\n" + body if body else "")
            if one_song and one is not None:
                one["lyrics"] += "\n\n" + chunk
                one["_tags"].append(sec["tag"])
            elif number is not None and not one_song:
                number["lyrics"] += "\n\n" + chunk
                number["_tags"].append(sec["tag"])
            else:
                number = {"kind": "number", "title": sec["title"], "lyrics": chunk, "_tags": [sec["tag"]]}
                if one_song:
                    one = number
                push(sec["act"], number)
        else:
            flush_number()
            push(sec["act"], {"kind": "scene", "title": sec["title"], "setting": sec["setting"], "lines": sec["lines"]})
            if not sec["lines"] and len(warnings) < MAX_WARNINGS:
                warnings.append(f"The scene \"{sec['title']}\" has no spoken lines.")
    for a in items_by_act.values():
        for it in a:
            if it["kind"] == "number":
                tags = it.pop("_tags")
                it["title"] = nice_title if one_song and nice_title else (tags[0] if len(tags) == 1 else f"{tags[0]} \u2013 {tags[-1]}")
    acts = [{"name": n, "items": items_by_act[n]} for n in order]
    items = [i for a in acts for i in a["items"]]
    if len(items) > MAX_ITEMS:
        raise SystemExit(f"That script has more than {MAX_ITEMS} numbers and scenes; split it into several scripts.")
    return {"title": title and _nice(title), "acts": acts, "characters": sorted(chars.values()), "warnings": warnings,
            "format": "screenplay",
            "totals": {"acts": len(acts), "numbers": sum(i["kind"] == "number" for i in items), "scenes": sum(i["kind"] == "scene" for i in items),
                       "lines": sum(len(i.get("lines", [])) for i in items)}}


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def match_songs(plan: dict, songs_dir: str | None) -> dict[str, str]:
    """{number title: audio file} from a folder of songs, by name. Only a single clear match counts; the folder isn't
    searched below its top level and a file that resolves outside the folder (a link) is skipped."""
    if not songs_dir:
        return {}
    if not os.path.isdir(songs_dir):
        raise SystemExit("That songs folder can't be found.")
    root = os.path.realpath(songs_dir)
    files = []
    for n in sorted(os.listdir(songs_dir))[:2000]:
        p = os.path.join(songs_dir, n)
        if os.path.splitext(n)[1].lower() in AUDIO and os.path.isfile(p) and os.path.realpath(p).startswith(root + os.sep):
            files.append((_key(os.path.splitext(n)[0]), p))
    out = {}
    for a in plan["acts"]:
        for it in a["items"]:
            if it["kind"] != "number" or not _key(it["title"]):
                continue
            k = _key(it["title"])
            exact = [p for fk, p in files if fk == k]
            near = exact or [p for fk, p in files if fk and (k in fk or fk in k)]
            if len(near) == 1:
                out[it["title"]] = near[0]
    return out


def preview(file: str, songs_dir: str | None = None, one_song: bool = False) -> dict:
    plan = parse(read_script(file), one_song)
    songs = match_songs(plan, songs_dir)
    for a in plan["acts"]:
        for it in a["items"]:
            if it["kind"] == "number":
                it["song"] = songs.get(it["title"])
    plan["totals"]["songs_matched"] = len(songs)
    plan["totals"]["songs_missing"] = plan["totals"]["numbers"] - len(songs)
    return plan


def import_script(show: str, file: str, songs_dir: str | None = None, one_song: bool = False) -> dict:
    """Add the script's acts, numbers and scenes to the show. Existing items are never touched. The script is read again
    here, so what is imported is what the file says now, whatever a screen showed earlier."""
    from . import library, show as S, voices
    plan = preview(file, songs_dir, one_song)
    data = S._show(show)
    if data["items"] and not data["acts"]:
        raise SystemExit("This show has no acts.")
    if len(data["items"]) + plan["totals"]["numbers"] + plan["totals"]["scenes"] > 1000:
        raise SystemExit("A show can hold 1,000 numbers and scenes at most.")
    # Characters first, so every voice and dialogue line has someone to belong to.
    cast = os.path.join(show, "cast")
    have = {(i.get("name") or "").strip().lower() for i in library.load(cast)[1]["items"] if i.get("kind") == "character"}
    added = 0
    for name in plan["characters"]:
        if name.lower() not in have:
            library.upsert(cast, {"kind": "character", "name": name, "files": []})
            added += 1
    reuse_empty = len(data["acts"]) == 1 and not data["acts"][0]["items"]
    made = {"numbers": 0, "scenes": 0}
    for n, a in enumerate(plan["acts"]):
        if n == 0 and reuse_empty:
            S.rename(show, None, a["name"], act=0)
            act = 0
        else:
            act = len(S._show(show)["acts"])
            S.add_act(show, a["name"])
        for it in a["items"]:
            if it["kind"] == "number":
                S.add_number(show, it.get("song"), it["title"], lyrics=it["lyrics"] or None, act=act)
                made["numbers"] += 1
            else:
                r = S.add_scene(show, it["title"], it["setting"], act=act)
                if it["lines"]:
                    voices.set_dialogue(r["dir"], {"setting": it["setting"], "lines": it["lines"]})
                made["scenes"] += 1
    return {**S.status(show), "imported": {**made, "characters_added": added, "songs_matched": plan["totals"]["songs_matched"],
                                          "songs_missing": plan["totals"]["songs_missing"], "warnings": plan["warnings"]}}
