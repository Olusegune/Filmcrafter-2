"""Your own recorded voices, attached to the people in each shot.

You record the lines; FilmCrafter makes the picture speak them. A recording is named for the person and the shot (CHLOE_S01-04.wav, S01-04_Chloe.mp3,
or just S01-04.wav when only one person speaks there). Nothing is guessed silently: `match` shows what each file would be attached to, and `import_files`
attaches only what the person confirmed.

Where things live
  <film>/voice/voice.json                     what is attached to which shot and person (length, loudness, the file's own name)
  <film>/voice/<shot>/<person>.<ext>          the recording, copied in (your original is never touched, never changed)
  <film>/voice/_removed/                      what was replaced or removed: nothing is ever deleted
  <film>/render/assets/voice/                 copies for the render project (made by make.sync)
  <film>/render/voiceover.json                what the render project reads (made by make.sync)

For the video model the shot's recordings become one reference audio clip (the keyframe goes along as a reference picture, so the mouth follows the voice);
at export the recordings are laid on the film at their shots, and they, not the video model's own sound, are what is heard.
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

from .safe import check_id, file_name, file_part

AUDIO_EXT = (".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg")
MAX_BYTES = 200 * 1024 * 1024
MAX_MINUTES = 20            # a recording is a line or a scene, not a feature: and it is read whole into memory
LONG = 15.0                 # seconds: video models take only so much reference audio
GAP = 0.25                  # seconds between two people's recordings in one shot
FIT_MARGIN = 0.4            # seconds of air after a recording when a shot is lengthened to hold it
SILENT_RMS = 0.003
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
NOISE = {"take", "final", "vo", "voice", "voiceover", "audio", "wav", "mp3", "m4a", "new", "edit", "edited", "fixed", "mix", "dialogue", "dialog", "line", "record", "recording", "rec", "copy", "of", "the", "and"}
SHOT_ID = re.compile(r"(?<![A-Za-z0-9])S(\d{1,3})[-_ .]?(\d{1,3})(?![0-9])", re.I)


def emit(**kw) -> None:
    try:
        print(json.dumps(kw, ensure_ascii=False), flush=True)
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
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def inside(base: str, rel: object) -> str | None:
    """The full path of `rel` (written with slashes, relative to `base`) when it stays inside `base`, else None. A film's own files are trusted only
    this far: a voice.json from somewhere else (a shared folder) must not be able to point at, copy or upload a file outside the film."""
    s = str(rel or "")
    if not s or s.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", s) or ".." in re.split(r"[\\/]", s):
        return None
    full = os.path.realpath(os.path.join(base, *s.split("/")))
    root = os.path.realpath(base)
    return full if full == root or full.startswith(root + os.sep) else None


def key_of(name: str) -> str:
    """A person's name as a plain key: 'Friend #1' -> 'friend-1', 'CHLOE DAD' -> 'chloe-dad'."""
    return re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")


def pretty(name: str) -> str:
    n = str(name or "").strip()
    return n.title() if n.isupper() else n


def _film(d: str) -> None:
    if not os.path.isfile(os.path.join(d, "film.json")):
        raise SystemExit("That isn't a FilmCrafter film.")


def _meta(d: str) -> dict:
    m = _read(os.path.join(d, "voice", "voice.json"), None)
    return m if isinstance(m, dict) and isinstance(m.get("shots"), dict) else {"schema": 1, "shots": {}}


def _contracts(d: str) -> dict[str, dict]:
    from . import make
    return {c["id"]: c for c in make._contracts(d)}


def _speakers_of(c: dict) -> list[str]:
    """The people in a shot who speak or may speak: those with a line, then the others in the shot."""
    out: list[str] = []
    for n in [x.get("speaker") for x in c.get("dialogue") or []] + [x.get("name") for x in c.get("characters") or []]:
        if n and key_of(n) not in [key_of(o) for o in out]:
            out.append(str(n))
    return out


def shot_id_in(name: str) -> str | None:
    """The shot a file name points at: S1-4, S01_04, s01-04 all mean S01-04."""
    m = SHOT_ID.search(name)
    return f"S{int(m.group(1)):02d}-{int(m.group(2)):02d}" if m else None


# ---------------------------------------------------------------- reading a recording

def probe(path: str) -> dict:
    """Length and loudness of a recording, or why it cannot be used. Reads the file; changes nothing."""
    from . import shotsound
    import numpy as np
    if not os.path.isfile(path):
        return {"ok": False, "why": "That file is not there."}
    if not path.lower().endswith(AUDIO_EXT):
        return {"ok": False, "why": "Use a WAV, MP3, M4A, FLAC, AAC or OGG file."}
    if os.path.getsize(path) > MAX_BYTES:
        return {"ok": False, "why": "That audio file is larger than 200 MB."}
    from .render import take_duration
    if take_duration(path) > MAX_MINUTES * 60:
        return {"ok": False, "why": f"That recording is longer than {MAX_MINUTES} minutes. Use one file per shot or scene."}
    x = shotsound.decode(path, 1)
    if not len(x):
        return {"ok": False, "why": "That file has no sound FilmCrafter can read."}
    rms = float(np.sqrt(np.mean(np.square(x))))
    peak = float(np.max(np.abs(x)))
    if rms < SILENT_RMS:
        return {"ok": False, "why": "That recording is silent."}
    return {"ok": True, "seconds": round(len(x) / shotsound.RATE, 2), "rms_db": round(20 * np.log10(max(rms, 1e-6)), 1), "peak_db": round(20 * np.log10(max(peak, 1e-6)), 1)}


def _notes(seconds: float, peak_db: float, shot_seconds: float) -> list[str]:
    out = []
    if seconds > LONG:
        out.append(f"{seconds:.1f} s is longer than a video model can follow ({LONG:.0f} s): split the shot")
    elif seconds + 0.2 > shot_seconds:
        out.append(f"{seconds:.1f} s recording, {shot_seconds:.1f} s shot: the shot is lengthened to hold it")
    if peak_db > -0.3:
        out.append("clipped: the loudest peak reaches the maximum")
    return out


# ---------------------------------------------------------------- matching file names to shots and people

def match(d: str, files: list[str]) -> list[dict]:
    """What each file would be attached to. Free; changes nothing. Each row: file, name, shot, speaker, status and a plain note.
    status: ok, replace (ok, and it replaces a recording), ambiguous, no_shot, no_speaker, not_in_shot, duplicate, bad_file."""
    _film(d)
    cons = _contracts(d)
    cast = {}
    for c in cons.values():
        for n in _speakers_of(c):
            cast.setdefault(key_of(n), pretty(n))
    meta = _meta(d)
    rows, seen = [], set()
    for f in files[:500]:
        path = os.path.abspath(str(f))
        base = os.path.basename(path)
        row = {"file": path, "name": base, "shot": None, "speaker": None, "status": "bad_file", "note": "", "seconds": None}
        info = probe(path)
        if not info["ok"]:
            row["note"] = info["why"]
            rows.append(row)
            continue
        row["seconds"] = info["seconds"]
        stem = os.path.splitext(base)[0]
        sid = shot_id_in(stem)
        if not sid:
            row.update(status="no_shot", note="The name has no shot in it (like S01-04). Choose the shot.")
            rows.append(row)
            continue
        if sid not in cons:
            row.update(shot=sid, status="no_shot", note=f"There is no shot {sid} in this film.")
            rows.append(row)
            continue
        row["shot"] = sid
        rest = [t for t in re.split(r"[^a-z0-9]+", SHOT_ID.sub(" ", stem, count=1).lower()) if t]
        inshot = {key_of(n): pretty(n) for n in _speakers_of(cons[sid])}
        pick = None
        for pool in (inshot, cast):                                      # the people in the shot first; then anyone in the film
            hits = [(k, v) for k, v in pool.items() if _tokens_in(k.split("-"), rest)]
            if hits:
                pick = max(hits, key=lambda kv: len(kv[0]))             # 'chloe-dad' beats 'chloe'
                break
        leftover = [t for t in rest if t not in NOISE and not t.isdigit() and not re.fullmatch(r"v\d+|take\d*|t\d+", t)]
        if pick is None and leftover:
            row.update(status="no_speaker", note=f"I don't know who \"{' '.join(leftover)}\" is. Choose who is speaking.")
            rows.append(row)
            continue
        if pick is None:
            speakers = list(inshot.values())
            speaking = [pretty(x["speaker"]) for x in cons[sid].get("dialogue") or [] if x.get("speaker")]
            only = list(dict.fromkeys(speaking)) or speakers
            if len(only) == 1:
                pick = (key_of(only[0]), only[0])
            elif len(only) > 1:
                row.update(status="ambiguous", note="Several people speak in this shot. Choose who this is: " + ", ".join(only) + ".")
                rows.append(row)
                continue
            else:
                row.update(status="no_speaker", note="Nobody is named in this shot. Choose who is speaking.")
                rows.append(row)
                continue
        k, who = pick
        row["speaker"] = who
        if k not in inshot:
            row.update(status="not_in_shot", note=f"{who} is not in {sid}. Choose another person, or add them to the shot first.")
        elif (sid, k) in seen:
            row.update(status="duplicate", note=f"Another file in this batch is already for {who} in {sid}.")
        else:
            seen.add((sid, k))
            had = k in {e["key"] for e in meta["shots"].get(sid, [])}
            notes = _notes(info["seconds"], info["peak_db"], float(cons[sid]["generation"].get("duration") or 3.0))
            row.update(status="replace" if had else "ok", note=("Replaces the recording now attached. " if had else "") + ("; ".join(notes)))
        rows.append(row)
    return rows


def _tokens_in(needle: list[str], hay: list[str]) -> bool:
    n = len(needle)
    return n > 0 and any(hay[i:i + n] == needle for i in range(len(hay) - n + 1))


# ---------------------------------------------------------------- attaching

def attach(d: str, shot: str, speaker: str, file: str, fit: bool = True) -> dict:
    """Copy a recording into the film as `speaker`'s voice in `shot`. A recording already there is moved to voice/_removed, not deleted.
    With `fit`, a shot shorter than its recording is lengthened to hold it (never shortened)."""
    _film(d)
    sid = check_id(shot, "shot")
    cons = _contracts(d)
    if sid not in cons:
        raise SystemExit(f"There is no shot {sid} in this film.")
    who = str(speaker or "").strip()[:60]
    k = key_of(who)
    if not k:
        raise SystemExit("Choose who is speaking.")
    src = os.path.abspath(str(file))
    info = probe(src)
    if not info["ok"]:
        raise SystemExit(info["why"])
    meta = _meta(d)
    entries = meta["shots"].setdefault(sid, [])
    ext = os.path.splitext(src)[1].lower()
    rel = f"voice/{sid}/{file_name(k + ext, 60)}"
    dst = os.path.join(d, *rel.split("/"))
    old = next((e for e in entries if e["key"] == k), None)
    if old:
        _archive(d, old["file"])
        entries.remove(old)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
    entry = {"key": k, "speaker": pretty(who), "file": rel, "name": os.path.basename(src), "seconds": info["seconds"], "rms_db": info["rms_db"], "peak_db": info["peak_db"], "added": int(time.time())}
    entries.append(entry)
    entries.sort(key=lambda e: _order(cons[sid], e["key"]))
    _write(os.path.join(d, "voice", "voice.json"), meta)
    out = {"shot": sid, "speaker": entry["speaker"], "seconds": info["seconds"], "notes": _notes(info["seconds"], info["peak_db"], float(cons[sid]["generation"].get("duration") or 3.0)), "replaced": bool(old)}
    if fit:
        need = round(-(-(sum(e["seconds"] for e in entries) + GAP * (len(entries) - 1) + FIT_MARGIN) * 2 // 1) / 2, 1)
        if need > float(cons[sid]["generation"].get("duration") or 3.0) and need <= 30.0:
            from . import shots
            shots.set_fields(d, sid, {"generation": {"duration": need}})
            out["lengthened_to"] = need
    return out


def _order(c: dict, k: str) -> int:
    ks = [key_of(x.get("speaker")) for x in c.get("dialogue") or []]
    return ks.index(k) if k in ks else 99


def _archive(d: str, rel: str) -> None:
    src = inside(d, rel)
    if src and os.path.isfile(src):
        stem, ext = os.path.splitext(file_part(os.path.basename(src)))
        dst = os.path.join(d, "voice", "_removed", f"{int(time.time())}-{stem}{ext}")
        n = 1
        while os.path.exists(dst):                                  # two in the same second: never write over one that was kept
            n += 1
            dst = os.path.join(d, "voice", "_removed", f"{int(time.time())}-{stem}-{n}{ext}")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)


def import_files(d: str, items: list[dict], fit: bool = True) -> dict:
    """Attach what the person confirmed: [{file, shot, speaker}]. Every item is checked again; one that cannot be attached is reported, the rest still are."""
    done, failed = [], []
    for it in (items or [])[:500]:
        try:
            done.append(attach(d, it.get("shot"), it.get("speaker"), it.get("file"), fit))
        except SystemExit as e:
            failed.append({"file": os.path.basename(str(it.get("file") or "")), "shot": it.get("shot"), "why": str(e)})
    from . import make
    try:
        make.sync(d)
    except SystemExit:
        pass
    return {"attached": done, "failed": failed, "status": status(d)}


def remove(d: str, shot: str, speaker: str) -> dict:
    _film(d)
    sid = check_id(shot, "shot")
    k = key_of(speaker)
    meta = _meta(d)
    entries = meta["shots"].get(sid, [])
    hit = next((e for e in entries if e["key"] == k), None)
    if hit:
        _archive(d, hit["file"])
        entries.remove(hit)
        if not entries:
            meta["shots"].pop(sid, None)
        _write(os.path.join(d, "voice", "voice.json"), meta)
        from . import make
        try:
            make.sync(d)
        except SystemExit:
            pass
    return status(d)


# ---------------------------------------------------------------- what the screen shows

def status(d: str) -> dict:
    """Every shot where someone speaks (or has a recording): who, what they say, and whether their voice is attached."""
    _film(d)
    cons = _contracts(d)
    meta = _meta(d)
    shots, lines, recorded, problems = [], 0, 0, 0
    for sid, c in cons.items():
        dl = [x for x in c.get("dialogue") or [] if x.get("line")]
        have = {e["key"]: e for e in meta["shots"].get(sid, []) if isinstance(e, dict) and e.get("key") and (lambda p: bool(p) and os.path.isfile(p))(inside(d, e.get("file")))}
        if not dl and not have:
            continue
        people: dict[str, dict] = {}
        for x in dl:
            p = people.setdefault(key_of(x["speaker"]), {"name": pretty(x["speaker"]), "key": key_of(x["speaker"]), "lines": [], "recording": None})
            p["lines"].append(x["line"])
        for k, e in have.items():
            people.setdefault(k, {"name": e["speaker"], "key": k, "lines": [], "recording": None})["recording"] = {f: e[f] for f in ("file", "name", "seconds", "rms_db", "peak_db")}
        secs = float(c["generation"].get("duration") or 3.0)
        notes = []
        for k, e in have.items():
            notes += [f"{e['speaker']}: {n}" for n in _notes(e["seconds"], e["peak_db"], secs)]
        lines += len(people)
        recorded += sum(1 for p in people.values() if p["recording"])
        problems += len(notes)
        others = [pretty(n) for n in _speakers_of(c) if key_of(n) not in people]               # in the shot, nothing to say there: a voice can still be attached
        shots.append({"id": sid, "scene": c["scene"], "title": c.get("title", ""), "seconds": secs, "people": list(people.values()), "others": others, "notes": notes})
    return {"shots": shots, "people": lines, "recorded": recorded, "missing": lines - recorded, "problems": problems}


# ---------------------------------------------------------------- for the render project (made by make.sync)

def to_render(d: str, rd: str) -> int:
    """Copy the recordings into the render project and write what it reads. Returns how many recordings there are."""
    meta = _meta(d)
    cons = _contracts(d)
    out, n = {}, 0
    folder = os.path.join(rd, "assets", "voice")
    for sid, entries in meta["shots"].items():
        if sid not in cons:
            continue
        c = cons[sid]
        rows = []
        for e in entries:
            src = inside(d, e.get("file")) if isinstance(e, dict) else None
            if not src or not os.path.isfile(src) or not e.get("key"):
                continue
            os.makedirs(folder, exist_ok=True)
            name = file_name(f"{sid}-{e['key']}{os.path.splitext(src)[1].lower()}", 70)
            dst = os.path.join(folder, name)
            if not os.path.isfile(dst) or os.path.getmtime(dst) < os.path.getmtime(src) or os.path.getsize(dst) != os.path.getsize(src):
                shutil.copyfile(src, dst)
            says = " ".join(x["line"] for x in c.get("dialogue") or [] if key_of(x.get("speaker")) == e["key"] and x.get("line"))
            rows.append({"speaker": e["speaker"], "key": e["key"], "path": f"assets/voice/{name}", "seconds": e["seconds"], "line": says})
            n += 1
        if rows:
            out[sid] = rows
    _write(os.path.join(rd, "voiceover.json"), {"schema": 1, "shots": out})
    return n


# ---------------------------------------------------------------- for rendering (these read the render project)

def for_shot(d: str, shot_id: str) -> list[dict]:
    """The recordings attached to a shot, in speaking order, that are really there. [] for a shot with none."""
    m = _read(os.path.join(d, "voiceover.json"), {}) or {}
    rows = (m.get("shots") or {}).get(str(shot_id), [])
    return [r for r in rows if isinstance(r, dict) and (lambda p: bool(p) and os.path.isfile(p))(inside(d, r.get("path")))]


def slice_for(d: str, shot_id: str, seconds: float) -> str:
    """One audio clip for the shot: its recordings in order with a short gap, cut to at most `seconds`. Cached; the recordings are never changed."""
    from .export import ffmpeg
    rows = for_shot(d, shot_id)
    if not rows:
        raise SystemExit(f"Shot {shot_id} has no recording.")
    files = [inside(d, r["path"]) for r in rows]
    tag = hashlib.sha1("|".join(f"{f}:{os.path.getsize(f)}:{os.path.getmtime(f)}" for f in files).encode() + f"{seconds:.2f}".encode()).hexdigest()[:12]
    out_dir = os.path.join(d, "cache", "voice")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{file_part(shot_id)}_{tag}.mp3")
    if os.path.isfile(out):
        return out
    cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"]
    for f in files:
        cmd += ["-i", f]
    if len(files) == 1:
        graph = "[0:a]aresample=44100,aformat=channel_layouts=stereo[a]"
    else:
        parts = [f"[{i}:a]aresample=44100,aformat=channel_layouts=stereo,apad=pad_dur={GAP}[p{i}]" for i in range(len(files))]
        graph = ";".join(parts) + ";" + "".join(f"[p{i}]" for i in range(len(files))) + f"concat=n={len(files)}:v=0:a=1[a]"
    cmd += ["-filter_complex", graph, "-map", "[a]", "-t", f"{max(0.5, seconds):.3f}", "-b:a", "192k", out + ".part.mp3"]
    subprocess.run(cmd, check=True, creationflags=NO_WINDOW)
    os.replace(out + ".part.mp3", out)
    return out


def mix_into(d: str, base_path: str, items: list[dict], duration: float, out: str) -> dict | None:
    """The film's sound with the recordings laid on it: items [{shot, start, end}] (where each shot sits on the film, in seconds). The recordings are not
    changed in level (they are yours, mastered as you want), only guarded against clipping where they add up. None when no shot here has a recording."""
    import numpy as np
    import soundfile as sf
    from . import shotsound
    rate = shotsound.RATE
    placed = [(it, for_shot(d, it["shot"])) for it in items]
    placed = [(it, rows) for it, rows in placed if rows]
    if not placed:
        return None
    total = int(round(duration * rate))
    track = np.zeros((total, 2), dtype=np.float32)
    base = shotsound.decode(base_path, 2)[:total]
    track[: len(base)] = base
    n = 0
    for it, rows in placed:
        at = int(round(it["start"] * rate))
        stop = min(total, int(round(it["end"] * rate)))
        for r in rows:
            x = shotsound.decode(inside(d, r["path"]) or "", 2)
            x = x[: max(0, stop - at)]
            if len(x) and at < total:
                track[at:at + len(x)] += x
                n += 1
            at += len(x) + int(GAP * rate)
    peak = float(np.max(np.abs(track))) if total else 0.0
    if peak > 0.98:
        track *= 0.98 / peak
    sf.write(out, track, rate, subtype="PCM_16")
    return {"path": out, "recordings": n}


# ---------------------------------------------------------------- command line

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["status", "match", "import", "remove"])
    ap.add_argument("target")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    d = os.path.abspath(a.target)
    try:
        x = json.loads(a.data or "{}")
        x = x if isinstance(x, dict) else {}
        if a.action == "status":
            res = status(d)
        elif a.action == "match":
            res = {"rows": match(d, [str(f) for f in x.get("files") or []])}
        elif a.action == "import":
            res = import_files(d, x.get("items") or [], x.get("fit", True) is not False)
        else:
            res = remove(d, x.get("shot", ""), x.get("speaker", ""))
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
