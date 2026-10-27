"""The film's sound as separate tracks for a professional editor: each person's voice on a track of their own, and the planned sound effects, ambience and music on theirs.

The hand-off used to carry the picture and one soundtrack, with the recordings left in a folder to be lined up by hand. This works out where every recording and every approved cue sits on
the film, to the frame, by the same rules the exported film is mixed with (the same lead and tail of a J or L cut, the same gap between two people in a shot, the same cues that are heard),
so the editor opens on a timeline that already sounds like the film. It reads; the only thing it writes is the copies of the sounds it is asked to copy into the hand-off folder.

A track is {"name", "role", "clips": [{"name", "file", "start", "frames", "source_frames", "gain_db", "fade_in", "fade_out", "note"}]}; times are frames at the hand-off's frame rate.
"""
from __future__ import annotations

import math
import os
import shutil

from .safe import file_name

ROLE_NAMES = {"dialogue": "Dialogue", "sfx": "Sound effects", "ambience": "Ambience", "music": "Music"}


def _frames(seconds: float, fps: int) -> int:
    return max(0, int(round(float(seconds) * fps)))


def voice_tracks(rd: str, rows: list[dict], fps: int, copy_to: str | None = None) -> list[dict]:
    """One track per person who has a recording. `rows` are the cut ([{id, start, frames, lead, tail}]); lead and tail are the shot's J and L cut in seconds."""
    from . import voiceover
    by: dict[str, dict] = {}
    for r in rows:
        recs = voiceover.for_shot(rd, r["id"])
        if not recs:
            continue
        at = max(0, _frames(r["start"] / fps - max(0.0, float(r.get("lead") or 0.0)), fps))
        stop = _frames((r["start"] + r["frames"]) / fps + max(0.0, float(r.get("tail") or 0.0)), fps)
        for v in recs:
            frames = min(_frames(v.get("seconds") or 0, fps), max(0, stop - at))
            if frames <= 0:
                continue
            name = v.get("speaker") or v.get("key") or "Voice"
            rel = None
            if copy_to:
                rel = "audio/voice/" + file_name(f"{r['id']}-{v['key']}{os.path.splitext(v['path'])[1].lower()}", 70)
                os.makedirs(os.path.join(copy_to, "audio", "voice"), exist_ok=True)
                if not os.path.isfile(os.path.join(copy_to, rel)):
                    shutil.copyfile(voiceover.inside(rd, v["path"]), os.path.join(copy_to, rel))
            t = by.setdefault(v["key"], {"name": f"Voice {name}", "role": "dialogue", "clips": []})
            t["clips"].append({"name": f"{r['id']} {name}", "file": rel, "path": voiceover.inside(rd, v["path"]), "start": at, "frames": frames, "source_frames": _frames(v.get("seconds") or 0, fps), "gain_db": 0.0,
                               "fade_in": 0.0, "fade_out": 0.0, "note": (v.get("line") or "")[:120]})
            at += frames + _frames(voiceover.GAP, fps)
    return sorted(by.values(), key=lambda t: t["name"].lower())


def cue_tracks(film: str, rows: list[dict], fps: int, total_frames: int, copy_to: str | None = None) -> list[dict]:
    """One track for each kind of approved cue that is heard in the film: sound effects, ambience, music. A looping cue is laid end to end to fill its time."""
    from . import audiomix
    times = {r["id"]: (r["start"] / fps, (r["start"] + r["frames"]) / fps) for r in rows}
    try:
        placed, _skipped = audiomix.placements(film, times, total_frames / fps)
    except (SystemExit, OSError, ValueError, KeyError):
        return []
    by: dict[str, dict] = {}
    for p in placed:
        role = p.get("lane") if p.get("lane") in ROLE_NAMES else "sfx"
        rel = None
        if copy_to:
            rel = "audio/cues/" + file_name(f"{p['cue']}{os.path.splitext(p['path'])[1].lower()}", 70)
            os.makedirs(os.path.join(copy_to, "audio", "cues"), exist_ok=True)
            if not os.path.isfile(os.path.join(copy_to, rel)):
                shutil.copyfile(p["path"], os.path.join(copy_to, rel))
        at, end = _frames(p["start"], fps), _frames(p["end"], fps)
        one = max(1, _frames(p["asset_seconds"], fps))
        t = by.setdefault(role, {"name": ROLE_NAMES[role], "role": role, "clips": []})
        gain = round(20 * math.log10(p["gain"]), 2) if p.get("gain") and p["gain"] > 0 else 0.0
        n = 0
        while at < end and n < 500:
            frames = min(one, end - at)
            t["clips"].append({"name": str(p["cue"]), "file": rel, "path": p["path"], "start": at, "frames": frames, "source_frames": one, "gain_db": gain,
                               "fade_in": p["fade_in"] if n == 0 else 0.0, "fade_out": p["fade_out"] if at + frames >= end else 0.0, "note": "loops" if p.get("loop") else ""})
            at += frames
            n += 1
            if not p.get("loop"):
                break
    return [by[k] for k in ROLE_NAMES if k in by]


def audio_tracks(film: str, rd: str, rows: list[dict], fps: int, total_frames: int, copy_to: str | None = None) -> list[dict]:
    """Dialogue first, then effects, ambience and music; each track's clips in time order, and none overlapping another on the same track."""
    out = voice_tracks(rd, rows, fps, copy_to) + cue_tracks(film, rows, fps, total_frames, copy_to)
    for t in out:
        t["clips"].sort(key=lambda c: c["start"])
        cur = 0
        for c in t["clips"]:                       # a track plays one sound at a time: a later clip starts where the earlier ends (a second track is the editor's choice)
            c.setdefault("source_start", 0)
            if c["start"] < cur:
                cut = cur - c["start"]
                c["frames"] = max(0, c["frames"] - cut)
                c["source_start"] = cut
                c["start"] = cur
            cur = c["start"] + c["frames"]
        t["clips"] = [c for c in t["clips"] if c["frames"] > 0]
    return [t for t in out if t["clips"]]
