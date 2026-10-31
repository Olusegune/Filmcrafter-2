"""Hand a film to a professional editor: the cut as an EDL, OpenTimelineIO and Final Cut Pro XML (which DaVinci Resolve and Final Cut read), a shot manifest, subtitles and the soundtrack.

The film is never trapped here. This writes one folder:

  <Film>/exports/interchange/<title> <time>/
      <title>.edl            CMX 3600, 24 fps (Premiere Pro, Resolve, Avid)
      <title>.otio           OpenTimelineIO
      <title>.fcpxml         Final Cut Pro XML 1.9 (DaVinci Resolve, Final Cut Pro)
      shots.csv, shots.json  every shot: scene, framing, length, which take, who made it, what it cost
      <title>.srt            the dialogue as subtitles (timed within each shot by the length of each line)
      media/                 the chosen take of each shot, copied (so the folder can be moved)
      audio/                 the soundtrack, copied

Only shots with a take are placed on the timeline; a shot with none is listed in the manifest with `take: null` so nothing is silently missing.

  python -m filmcrafter_engine.interchange write <film_dir>
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
import time
from xml.sax.saxutils import escape

from .safe import file_name, file_part

FPS = 24


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


def tc(frames: int, fps: int = FPS) -> str:
    """Frames as non-drop timecode HH:MM:SS:FF."""
    frames = max(0, int(frames))
    f = frames % fps
    s = frames // fps
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{f:02d}"


def srt_time(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def gather(d: str) -> dict:
    """The cut: every shot in order with its length, and the take chosen for it (if any)."""
    from . import make, shots
    shots._film(d)
    st = make.status(d)
    byid = {s["id"]: s for s in st["shots"]}
    rows, t = [], 0
    for c in make._contracts(d):
        dur = max(1, int(round(float(c["generation"]["duration"]) * FPS)))
        s = byid.get(c["id"], {})
        takes = (s.get("video") or {}).get("takes", [])
        take = next((x for x in takes if x["approved"] and x["ok"]), None) or next((x for x in takes if x["ok"]), None)
        rows.append({"id": c["id"], "scene": c["scene"], "title": c["title"] or c["story_purpose"], "framing": c["camera"]["framing"], "frames": dur, "start": t, "take": take, "dialogue": c["dialogue"], "lead": float((c.get("sound_cut") or {}).get("lead", 0.0)), "tail": float((c.get("sound_cut") or {}).get("tail", 0.0))})
        t += dur
    return {"rows": rows, "total": t, "soundtrack": st.get("soundtrack", {}), "render_dir": make.render_dir(d)}


def edl(title: str, rows: list[dict], media_rel: dict[str, str] | None = None) -> str:
    out = [f"TITLE: {title}", "FCM: NON-DROP FRAME", ""]
    n = 0
    for r in rows:
        if not r["take"]:
            continue
        n += 1
        reel = re.sub(r"[^A-Z0-9]", "", r["id"].upper())[:8].ljust(8)
        out.append(f"{n:03d}  {reel} V     C        {tc(0)} {tc(r['frames'])} {tc(r['start'])} {tc(r['start'] + r['frames'])}")
        clip = os.path.basename((media_rel or {}).get(r["id"]) or r["take"]["video"] or "")          # the name of the copy in the hand-off folder, which is what the editor must find
        out.append(f"* FROM CLIP NAME: {clip}")
        out.append(f"* COMMENT: {r['id']} scene {r['scene']} {r['framing']}")
        out.append("")
    return "\n".join(out)


def otio(title: str, rows: list[dict], media_rel: dict[str, str], audio_rel: str | None, total: int, tracks_in: list[dict] | None = None) -> dict:
    def rt(v: int) -> dict:
        return {"OTIO_SCHEMA": "RationalTime.1", "rate": FPS, "value": v}

    def rng(start: int, dur: int) -> dict:
        return {"OTIO_SCHEMA": "TimeRange.1", "start_time": rt(start), "duration": rt(dur)}
    video, cursor = [], 0
    for r in rows:
        if r["start"] > cursor:
            video.append({"OTIO_SCHEMA": "Gap.1", "name": "", "source_range": rng(0, r["start"] - cursor), "metadata": {}, "effects": [], "markers": []})
            cursor = r["start"]
        if r["take"]:
            video.append({"OTIO_SCHEMA": "Clip.1", "name": f"{r['id']} {r['title']}"[:80], "source_range": rng(0, r["frames"]), "metadata": {"filmcrafter": {"shot": r["id"], "scene": r["scene"], "framing": r["framing"]}},
                          "media_reference": {"OTIO_SCHEMA": "ExternalReference.1", "target_url": media_rel[r["id"]], "available_range": rng(0, r["frames"]), "metadata": {}, "name": os.path.basename(media_rel[r["id"]])},
                          "effects": [], "markers": []})
        else:
            video.append({"OTIO_SCHEMA": "Gap.1", "name": f"{r['id']} (no take yet)", "source_range": rng(0, r["frames"]), "metadata": {}, "effects": [], "markers": []})
        cursor += r["frames"]
    tracks = [{"OTIO_SCHEMA": "Track.1", "name": "Video", "kind": "Video", "children": video, "metadata": {}, "effects": [], "markers": []}]
    if audio_rel:
        tracks.append({"OTIO_SCHEMA": "Track.1", "name": "Soundtrack", "kind": "Audio", "metadata": {}, "effects": [], "markers": [], "children": [
            {"OTIO_SCHEMA": "Clip.1", "name": "Soundtrack", "source_range": rng(0, total), "metadata": {}, "effects": [], "markers": [],
             "media_reference": {"OTIO_SCHEMA": "ExternalReference.1", "target_url": audio_rel, "metadata": {}, "name": os.path.basename(audio_rel)}}]})
    for t in tracks_in or []:                                     # one audio track for each person's voice, and for effects, ambience and music, every clip at its frame
        kids, cur = [], 0
        for c in t["clips"]:
            if c["start"] > cur:
                kids.append({"OTIO_SCHEMA": "Gap.1", "name": "", "source_range": rng(0, c["start"] - cur), "metadata": {}, "effects": [], "markers": []})
            ref = {"OTIO_SCHEMA": "ExternalReference.1", "target_url": c["file"], "available_range": rng(0, c["source_frames"]), "metadata": {}, "name": os.path.basename(c["file"] or "")}
            kids.append({"OTIO_SCHEMA": "Clip.1", "name": c["name"][:80], "source_range": rng(c.get("source_start", 0), c["frames"]),
                         "metadata": {"filmcrafter": {"gain_db": c["gain_db"], "fade_in": c["fade_in"], "fade_out": c["fade_out"], "note": c["note"]}}, "media_reference": ref, "effects": [], "markers": []})
            cur = c["start"] + c["frames"]
        tracks.append({"OTIO_SCHEMA": "Track.1", "name": t["name"], "kind": "Audio", "children": kids, "metadata": {"filmcrafter": {"role": t["role"]}}, "effects": [], "markers": []})
    return {"OTIO_SCHEMA": "Timeline.1", "name": title, "global_start_time": rt(0), "metadata": {"generator": "FilmCrafter"},
            "tracks": {"OTIO_SCHEMA": "Stack.1", "name": "tracks", "children": tracks, "metadata": {}, "effects": [], "markers": []}}


def fcpxml(title: str, rows: list[dict], media_rel: dict[str, str], total: int, w: int, h: int, tracks_in: list[dict] | None = None) -> str:
    def f(frames: int) -> str:
        return f"{frames}/{FPS}s"
    assets, clips = [], []
    for i, r in enumerate((x for x in rows if x["take"]), 1):
        aid = f"r{i + 1}"
        assets.append(f'    <asset id="{aid}" name="{escape(r["id"])}" start="0s" duration="{f(r["frames"])}" hasVideo="1" format="r1"><media-rep kind="original-media" src="{escape(media_rel[r["id"]])}"/></asset>')
        clips.append(f'          <asset-clip ref="{aid}" offset="{f(r["start"])}" name="{escape(r["id"] + " " + r["title"][:50])}" start="0s" duration="{f(r["frames"])}"/>')
    first = next((x for x in rows if x["take"]), None)
    if first and tracks_in:                                       # the voices, effects, ambience and music hang under the first picture on lanes of their own (negative lanes are audio)
        lane, n = 0, len(assets)
        held: list[str] = []
        for t in tracks_in:
            lane -= 1
            for c in t["clips"]:
                n += 1
                aid = f"r{n + 1}"
                assets.append(f'    <asset id="{aid}" name="{escape(c["name"][:60])}" start="0s" duration="{f(c["source_frames"])}" hasAudio="1" audioSources="1" audioChannels="2" audioRate="48000"><media-rep kind="original-media" src="{escape(c["file"] or "")}"/></asset>')
                vol = f'<adjust-volume amount="{c["gain_db"]}dB"/>' if c["gain_db"] else ""
                held.append(f'            <asset-clip ref="{aid}" lane="{lane}" offset="{f(c["start"] - first["start"])}" name="{escape(t["name"] + ": " + c["name"][:40])}" start="{f(c.get("source_start", 0))}" duration="{f(c["frames"])}" audioRole="{escape(t["role"])}">{vol}</asset-clip>')
        clips[0] = clips[0][:-2] + ">" + "\n".join(held) + "\n          </asset-clip>"
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<fcpxml version="1.9">\n  <resources>\n'
            f'    <format id="r1" name="FFVideoFormat{h}p{FPS}" frameDuration="1/{FPS}s" width="{w}" height="{h}"/>\n' + "\n".join(assets) + "\n  </resources>\n"
            f'  <library>\n    <event name="{escape(title)}">\n      <project name="{escape(title)}">\n        <sequence format="r1" duration="{f(total)}" tcStart="0s" tcFormat="NDF">\n          <spine>\n'
            + "\n".join(clips) + "\n          </spine>\n        </sequence>\n      </project>\n    </event>\n  </library>\n</fcpxml>\n")


def srt(rows: list[dict]) -> str:
    out, n = [], 0
    for r in rows:
        lines = [x for x in r["dialogue"] if x.get("line")]
        words = sum(max(1, len(x["line"].split())) for x in lines)
        if not lines or not words:
            continue
        t = r["start"] / FPS
        span = r["frames"] / FPS
        for x in lines:
            share = span * max(1, len(x["line"].split())) / words
            n += 1
            out.append(f"{n}\n{srt_time(t)} --> {srt_time(t + share)}\n{x['speaker'].title()}: {x['line']}\n")
            t += share
    return "\n".join(out)


def write(d: str) -> dict:
    g = gather(d)
    rows, rd = g["rows"], g["render_dir"]
    if not rows:
        raise SystemExit("There are no shots yet.")
    m = _read(os.path.join(d, "film.json"), {})
    title = file_part(m.get("title", "Film").replace(" ", "_"), 30)                       # short, so the folder, the files and the sounds inside stay well under Windows's 260-character path limit
    pretty = m.get("title", "Film")
    out = os.path.join(d, "exports", "interchange", f"{title} {time.strftime('%Y-%m-%d %H%M%S')}")
    os.makedirs(os.path.join(out, "media"), exist_ok=True)
    media_rel: dict[str, str] = {}
    for r in rows:
        if r["take"] and r["take"].get("video"):
            src = os.path.join(rd, r["take"]["video"])
            if os.path.isfile(src):
                name = f"{file_part(r['id'])}{os.path.splitext(src)[1].lower()}"
                shutil.copyfile(src, os.path.join(out, "media", name))
                media_rel[r["id"]] = "media/" + name
            else:
                r["take"] = None
    for r in rows:
        if r["id"] not in media_rel:
            r["take"] = None
    audio_rel = None
    snd = os.path.join(rd, (g["soundtrack"] or {}).get("file", "")) if (g["soundtrack"] or {}).get("file") else None
    if snd and os.path.isfile(snd):
        os.makedirs(os.path.join(out, "audio"), exist_ok=True)
        audio_rel = "audio/" + file_name(os.path.basename(snd), 60)
        shutil.copyfile(snd, os.path.join(out, audio_rel))
    from . import editortracks, voiceover                           # your own recordings, one file per person per shot, and the planned sound: laid on tracks of their own, copied beside them
    voice_rel: dict[str, list[str]] = {}
    for r in rows:
        for v in voiceover.for_shot(rd, r["id"]):
            os.makedirs(os.path.join(out, "audio", "voice"), exist_ok=True)
            rel = "audio/voice/" + file_name(f"{r['id']}-{v['key']}{os.path.splitext(v['path'])[1].lower()}", 70)
            shutil.copyfile(voiceover.inside(rd, v["path"]), os.path.join(out, rel))
            voice_rel.setdefault(r["id"], []).append(rel)
    tracks = editortracks.audio_tracks(d, rd, rows, FPS, g["total"], out)
    pj = _read(os.path.join(rd, "project.json"), {})
    aspect = pj.get("aspect_ratio", "16:9")
    w, h = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "2.39:1": (1920, 804), "21:9": (1920, 804)}.get(aspect, (1920, 1080))
    files = {}
    with open(os.path.join(out, f"{title}.edl"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(edl(pretty, rows, media_rel))
    files["edl"] = f"{title}.edl"
    with open(os.path.join(out, f"{title}.otio"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(otio(pretty, rows, media_rel, audio_rel, g["total"], tracks), fh, indent=2)
    files["otio"] = f"{title}.otio"
    with open(os.path.join(out, f"{title}.fcpxml"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(fcpxml(pretty, rows, media_rel, g["total"], w, h, tracks))
    files["fcpxml"] = f"{title}.fcpxml"
    text = srt(rows)
    if text:
        with open(os.path.join(out, f"{title}.srt"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        files["srt"] = f"{title}.srt"
    table = [{"shot": r["id"], "scene": r["scene"], "title": r["title"], "framing": r["framing"], "seconds": round(r["frames"] / FPS, 2), "start_timecode": tc(r["start"]),
              "take": media_rel.get(r["id"]), "provider": (r["take"] or {}).get("provider"), "model": (r["take"] or {}).get("model"), "cost": (r["take"] or {}).get("cost"),
              "approved": bool((r["take"] or {}).get("approved")), "voice": ";".join(voice_rel.get(r["id"], []))} for r in rows]
    with open(os.path.join(out, "shots.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"film": pretty, "fps": FPS, "shots": table}, fh, indent=2)
    with open(os.path.join(out, "shots.csv"), "w", encoding="utf-8", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(table[0].keys()))
        wr.writeheader()
        wr.writerows(table)
    files["manifest"] = "shots.csv"
    if voice_rel:
        files["voiceover"] = "audio/voice"
    placed = sum(1 for r in rows if r["take"])
    from . import handoffcheck                                       # the folder is read back as an editor would, and each track is written as one finished file
    try:
        stems = handoffcheck.write_stems(out, tracks, g["total"] / FPS)
    except Exception:                                                # the stems are extra: the timelines stand without them
        stems = []
    if stems:
        files["stems"] = "audio/stems"
    problems = handoffcheck.check(out, files, placed, g["total"])
    from . import editing as _editing
    if _editing.hand_off_note(rd):
        problems.append(_editing.hand_off_note(rd))
    handoffcheck.save_report(out, problems)
    return {"dir": out, "problems": problems, "stems": stems, "files": files, "shots": len(rows), "placed": placed, "missing": [r["id"] for r in rows if not r["take"]], "audio": audio_rel, "audio_tracks": [{"name": t["name"], "clips": len(t["clips"])} for t in tracks], "seconds": round(g["total"] / FPS, 1)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-interchange")
    ap.add_argument("action", choices=["write"])
    ap.add_argument("target")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    try:
        emit(event="result", data=write(a.target))
        return 0
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
