"""Send the film to Adobe Premiere Pro or DaVinci Resolve: one import file that fills the bin and builds the timelines.

Neither editor can be driven from outside reliably (Resolve's scripting only works in the paid Studio edition while it is running, and
Premiere has no stable external hook), but both import Final Cut Pro XML ("xmeml") natively. This writes one such file:

  <project>/exports/<title> - editor/<title> - Premiere Pro.xml      (or "... - DaVinci Resolve.xml")

with a bin of two timelines:

  <title>: finished film            the exported film as one clip, picture and sound, ready to trim, grade or add to
  <title>: shots (to re-edit)       every shot's chosen take laid out at its place in the song, over the film's own soundtrack
                                    (without the captions and text, which are drawn into the film), so any shot can be re-cut

The media is referenced where it is (nothing is copied or moved), so the files must stay where they are, or be relinked. Names and
paths go into the file only as XML text and attribute values (escaped by the XML library), and the film must be a video inside this
project's own exports folder.

  python -m filmcrafter_engine.editor_export package <project> --data '{"target": "premiere"|"resolve", "film": "<path>"}'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
TARGETS = {"premiere": ("Premiere Pro", "File > Import, choose the .xml file. The bin \"{bin}\" appears in the Project panel with its timelines; double-click one to open it."),
           "resolve": ("DaVinci Resolve", "File > Import > Timeline, choose the .xml file (leave \"Automatically import source clips into media pool\" on). "
                                          "The timelines and their clips appear in the Media Pool.")}
FILM_EXT = (".mp4", ".mov", ".m4v")
MAX_CLIPS = 2000


def _ffmpeg() -> str:
    from .export import ffmpeg
    return ffmpeg()


def probe(path: str) -> dict:
    """What an editor needs to know about a media file: duration (s), frame rate, size and whether it has sound."""
    err = subprocess.run([_ffmpeg(), "-hide_banner", "-i", path], capture_output=True, text=True, creationflags=NO_WINDOW).stderr
    dur = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    vid = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", err)
    fps = re.search(r"([\d.]+) fps", err)
    aud = re.search(r"Audio:.*?(\d+) Hz", err)
    return {"duration": int(dur.group(1)) * 3600 + int(dur.group(2)) * 60 + float(dur.group(3)) if dur else 0.0,
            "fps": float(fps.group(1)) if fps else 24.0, "w": int(vid.group(1)) if vid else 0, "h": int(vid.group(2)) if vid else 0,
            "video": bool(vid), "audio": bool(aud), "rate": int(aud.group(1)) if aud else 48000}


def _timebase(fps: float) -> tuple[int, bool]:
    """xmeml writes a whole timebase plus an 'ntsc' flag: 23.976 is 24 + ntsc, 29.97 is 30 + ntsc."""
    tb = round(fps)
    return tb, abs(fps - tb) > 0.01


def _url(path: str) -> str:
    p = os.path.abspath(path).replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", p):
        p = p[0] + "%3a" + urllib.parse.quote(p[2:], safe="/")      # C:/x -> C%3a/x, the way Premiere writes it
    else:
        p = urllib.parse.quote(p, safe="/")
    return "file://localhost" + (p if p.startswith("/") else "/" + p)


def _sub(parent, tag, text=None, **attrs):
    e = ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items()})
    if text is not None:
        e.text = str(text)
    return e


def _rate(parent, fps: float):
    tb, ntsc = _timebase(fps)
    r = _sub(parent, "rate")
    _sub(r, "timebase", tb)
    _sub(r, "ntsc", "TRUE" if ntsc else "FALSE")


def _file(parent, ids: dict, path: str, info: dict):
    """The first use of a file defines it in full; later uses just point at it."""
    if path in ids:
        return _sub(parent, "file", id=ids[path])
    fid = ids[path] = f"file-{len(ids) + 1}"
    f = _sub(parent, "file", id=fid)
    _sub(f, "name", os.path.basename(path))
    _sub(f, "pathurl", _url(path))
    _rate(f, info["fps"])
    _sub(f, "duration", max(1, round(info["duration"] * info["fps"])))
    tc = _sub(f, "timecode")
    _rate(tc, info["fps"])
    _sub(tc, "string", "00:00:00:00")
    _sub(tc, "frame", 0)
    _sub(tc, "displayformat", "NDF")
    media = _sub(f, "media")
    if info["video"]:
        sc = _sub(_sub(media, "video"), "samplecharacteristics")
        _rate(sc, info["fps"])
        _sub(sc, "width", info["w"])
        _sub(sc, "height", info["h"])
    if info["audio"]:
        audio = _sub(media, "audio")
        sc = _sub(audio, "samplecharacteristics")
        _sub(sc, "depth", 16)
        _sub(sc, "samplerate", info["rate"])
        _sub(audio, "channelcount", 2)
    return f


def _clip(track, ids: dict, n: list, name: str, path: str, info: dict, seq_fps: float, start: float, length: float, kind: str, link_to: str | None = None, src_in: float = 0.0):
    """One clip on a track: placed at `start` seconds for `length` seconds, taken from the start of its file."""
    tb, _ = _timebase(seq_fps)
    s = round(start * tb)
    e = s + max(1, round(length * tb))
    ftb, _ = _timebase(info["fps"])
    n[0] += 1
    cid = f"clipitem-{n[0]}"
    c = _sub(track, "clipitem", id=cid)
    _sub(c, "name", name)
    _sub(c, "enabled", "TRUE")
    _sub(c, "duration", max(1, round(info["duration"] * info["fps"])))
    _rate(c, info["fps"])
    _sub(c, "start", s)
    _sub(c, "end", e)
    _sub(c, "in", round(src_in * ftb))
    _sub(c, "out", round(src_in * ftb) + max(1, round(length * ftb)))
    _file(c, ids, path, info)
    if kind == "audio":
        st = _sub(c, "sourcetrack")
        _sub(st, "mediatype", "audio")
        _sub(st, "trackindex", 1)
    if link_to:
        for ref, mt, idx in ((link_to, "video", 1), (cid, "audio", 1)):
            ln = _sub(c, "link")
            _sub(ln, "linkclipref", ref)
            _sub(ln, "mediatype", mt)
            _sub(ln, "trackindex", idx)
            _sub(ln, "clipindex", 1)
    return cid, e


def _sequence(parent, sid: str, name: str, fps: float, w: int, h: int, length_s: float):
    seq = _sub(parent, "sequence", id=sid)
    _sub(seq, "name", name)
    tb, _ = _timebase(fps)
    _sub(seq, "duration", max(1, round(length_s * tb)))
    _rate(seq, fps)
    tc = _sub(seq, "timecode")
    _rate(tc, fps)
    _sub(tc, "string", "00:00:00:00")
    _sub(tc, "frame", 0)
    _sub(tc, "displayformat", "NDF")
    media = _sub(seq, "media")
    video = _sub(media, "video")
    fmt = _sub(_sub(video, "format"), "samplecharacteristics")
    _rate(fmt, fps)
    _sub(fmt, "width", w)
    _sub(fmt, "height", h)
    _sub(fmt, "pixelaspectratio", "square")
    _sub(fmt, "fielddominance", "none")
    return seq, _sub(video, "track"), _sub(_sub(media, "audio"), "track")


def latest_film(d: str) -> str | None:
    base = os.path.join(d, "exports")
    films = [os.path.join(base, f) for f in os.listdir(base) if f.lower().endswith(FILM_EXT) and not f.endswith((".part.mp4", ".overlay.mp4"))] if os.path.isdir(base) else []
    return max(films, key=os.path.getmtime) if films else None


def _inside(base: str, path: str) -> bool:
    b, p = os.path.normcase(os.path.realpath(base)), os.path.normcase(os.path.realpath(path))
    try:
        return os.path.commonpath([b, p]) == b and p != b
    except ValueError:
        return False


def _takes(d: str) -> tuple[list[dict], list[str]]:
    """The chosen take of every shot, in time order, as [{id, start, end, path}], and the ids of shots with no video take yet."""
    plan_name = "directed" if os.path.exists(os.path.join(d, "directed.json")) else "production"
    try:
        with open(os.path.join(d, f"{plan_name}.json"), encoding="utf-8") as f:
            plan = json.load(f)
        with open(os.path.join(d, "jobs.json"), encoding="utf-8") as f:
            jobs = json.load(f)["jobs"]
    except (OSError, ValueError, KeyError):
        return [], []
    from .library import chosen_take, shot_state
    state = shot_state(d)
    shots = sorted((sh for sc in plan.get("scenes", []) for sh in sc.get("shots", [])), key=lambda s: s["start"])
    out, missing = [], []
    for sh in shots:
        t = chosen_take(d, sh["id"], plan_name, jobs, state)
        p = os.path.join(d, t["output"]) if t else None
        if t and p and t.get("media_kind") != "image" and os.path.isfile(p):
            out.append({"id": sh["id"], "start": float(sh["start"]), "end": float(sh["end"]), "path": p})
        else:
            missing.append(sh["id"])
    return out[:MAX_CLIPS], missing


def _stems(d: str, takes: list[dict]) -> list[dict]:
    """The film's sound as separate tracks (each person's voice, effects, ambience, music) for a sequence of its own: [{name, clips: [{name, path, start, length, src_in}]}] in seconds.
    Nothing when the project is not a film, or has no recordings or approved cues."""
    try:
        from . import audiomix, editortracks
        film = audiomix.film_of(d)
        plan_name = "directed" if os.path.exists(os.path.join(d, "directed.json")) else "production"
        with open(os.path.join(d, f"{plan_name}.json"), encoding="utf-8") as f:
            plan = json.load(f)
    except (ImportError, OSError, ValueError):
        return []
    if not film:
        return []
    fps = 24
    rows = [{"id": sh["id"], "start": round(float(sh["start"]) * fps), "frames": max(1, round((float(sh["end"]) - float(sh["start"])) * fps)),
             "lead": float(sh.get("dialogue_lead") or 0.0), "tail": float(sh.get("dialogue_tail") or 0.0)}
            for sc in plan.get("scenes", []) for sh in sc.get("shots", [])]
    if not rows:
        return []
    total = max(r["start"] + r["frames"] for r in rows)
    try:
        tracks = editortracks.audio_tracks(film, d, rows, fps, total)
    except (SystemExit, OSError, ValueError, KeyError):
        return []
    return [{"name": t["name"], "clips": [{"name": c["name"], "path": c["path"], "start": c["start"] / fps, "length": c["frames"] / fps, "src_in": c.get("source_start", 0) / fps}
                                          for c in t["clips"] if c.get("path") and os.path.isfile(c["path"])]} for t in tracks]


def package(d: str, target: str, film: str | None = None) -> dict:
    if target not in TARGETS:
        raise SystemExit("Choose Premiere Pro or DaVinci Resolve.")
    film = film or latest_film(d)
    if not film or not os.path.isfile(film):
        raise SystemExit("Export the film first (Export, on the left), then send it to your editor.")
    exports = os.path.join(d, "exports")
    if not film.lower().endswith(FILM_EXT) or not _inside(exports, film):
        raise SystemExit("Choose a film from this project's exports.")
    fi = probe(film)
    if not fi["video"] or fi["duration"] <= 0:
        raise SystemExit("FilmCrafter can't read that film. Export it again.")
    try:
        with open(os.path.join(d, "project.json"), encoding="utf-8") as f:
            title = json.load(f).get("title", "FilmCrafter")
    except (OSError, ValueError):
        title = "FilmCrafter"
    safe = "".join(c for c in str(title) if c.isalnum() or c in " -_").strip() or "FilmCrafter"
    app, steps = TARGETS[target]
    bin_name = f"{safe} (FilmCrafter)"

    root = ET.Element("xmeml", {"version": "4"})
    proj = _sub(root, "project")
    _sub(proj, "name", f"{safe} - FilmCrafter")
    bin_ = _sub(_sub(proj, "children"), "bin")
    _sub(bin_, "name", bin_name)
    kids = _sub(bin_, "children")
    ids: dict[str, str] = {}
    n = [0]
    fps, w, h = fi["fps"], fi["w"], fi["h"]

    seq, vt, at = _sequence(kids, "sequence-1", f"{safe}: finished film", fps, w, h, fi["duration"])
    vid, _ = _clip(vt, ids, n, os.path.basename(film), film, fi, fps, 0, fi["duration"], "video")
    if fi["audio"]:
        _clip(at, ids, n, os.path.basename(film), film, fi, fps, 0, fi["duration"], "audio", link_to=vid)

    takes, missing = _takes(d)
    clips = 0
    stems: list[dict] = []
    if takes:
        seq2, vt2, at2 = _sequence(kids, "sequence-2", f"{safe}: shots (to re-edit)", fps, w, h, fi["duration"])
        for t in takes:
            ti = probe(t["path"])
            if not ti["video"] or ti["duration"] <= 0:
                missing.append(t["id"])
                continue
            length = max(0.04, min(t["end"] - t["start"], ti["duration"], fi["duration"] - t["start"]))
            if t["start"] >= fi["duration"]:
                continue
            _clip(vt2, ids, n, f"{t['id']} - {os.path.basename(t['path'])}", t["path"], ti, fps, t["start"], length, "video")
            clips += 1
        if fi["audio"]:
            _clip(at2, ids, n, os.path.basename(film) + " (sound)", film, fi, fps, 0, fi["duration"], "audio")
        stems = [t for t in _stems(d, takes) if t["clips"]]
        if stems:                                                # the same shots over the sound split into tracks: a voice per person, effects, ambience and music
            seq3, vt3, at3 = _sequence(kids, "sequence-3", f"{safe}: shots with sound by track", fps, w, h, fi["duration"])
            for t in takes:
                ti = probe(t["path"])
                if ti["video"] and ti["duration"] > 0 and t["start"] < fi["duration"]:
                    _clip(vt3, ids, n, f"{t['id']} - {os.path.basename(t['path'])}", t["path"], ti, fps, t["start"], max(0.04, min(t["end"] - t["start"], ti["duration"], fi["duration"] - t["start"])), "video")
            audio_el = seq3.find("media/audio")
            for k, t in enumerate(stems):
                track = at3 if k == 0 else _sub(audio_el, "track")
                for c in t["clips"]:
                    if c["start"] >= fi["duration"]:
                        continue
                    ai = probe(c["path"])
                    if ai["audio"] and ai["duration"] > 0:
                        _clip(track, ids, n, f"{t['name']}: {c['name']}", c["path"], ai, fps, c["start"], min(c["length"], fi["duration"] - c["start"]), "audio", src_in=c["src_in"])
    ET.indent(root)
    out_dir = os.path.join(exports, f"{safe} - editor")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{safe} - {app}.xml")
    tmp = out + ".part"
    ET.ElementTree(root).write(tmp, encoding="UTF-8", xml_declaration=True)
    with open(tmp, "r+", encoding="utf-8") as f:                 # the doctype line editors expect, after the XML declaration
        body = f.read()
        f.seek(0)
        f.write(body.replace("?>", "?>\n<!DOCTYPE xmeml>", 1))
    os.replace(tmp, out)
    return {"path": out, "folder": out_dir, "target": target, "app": app, "film": os.path.basename(film), "sequences": (3 if stems else 2) if takes else 1, "sound_tracks": [t["name"] for t in stems] if takes else [],
            "shot_clips": clips, "missing": sorted(set(missing)), "steps": steps.format(bin=bin_name)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-editor-export")
    ap.add_argument("action", choices=["package"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        res = package(a.project, x.get("target", ""), x.get("film"))
        print(json.dumps({"event": "result", "data": res}), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except Exception as e:
        print(json.dumps({"event": "error", "message": f"{type(e).__name__}: {e}"}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
