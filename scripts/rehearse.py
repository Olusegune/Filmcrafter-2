"""A dress rehearsal on a real project: copy it, add the things the newer features make (an intro title card, a layer for every lyric line, a travelling shape, an icon
that pulses), export the whole film, and check the result. Your project is never written to: everything happens in a copy.

  python scripts/rehearse.py "C:\\path\\to\\My Project" [--keep] [--preset youtube]

It checks that the film is as long as the song, has sound, that every layer was drawn, and writes a few frames next to the report so you can look at them.
The shots must already have takes (or they show slates). It costs nothing: no service is called.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "analysis"))

SKIP = {"backups", "thumbnails", "exports", "trash", "cache"}


def say(msg: str) -> None:
    print(msg, flush=True)


def copy_project(src: str, dst: str) -> None:
    def ignore(folder, names):
        return [n for n in names if os.path.normpath(folder) == os.path.normpath(src) and n in SKIP]
    shutil.copytree(src, dst, ignore=ignore)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="rehearse")
    ap.add_argument("project")
    ap.add_argument("--keep", action="store_true", help="keep the copy and its export instead of deleting it")
    ap.add_argument("--preset", default=None, help="export format (youtube, vertical, square, cinema); default: the project's shape")
    a = ap.parse_args(argv)
    src = os.path.abspath(a.project)
    if not os.path.isfile(os.path.join(src, "project.json")):
        say("That folder is not a PULSEFRAME project (no project.json).")
        return 2

    from pulseframe_analysis import export as E, layerkit, overlays as O, titlecard

    work = tempfile.mkdtemp(prefix="pf_rehearsal_")
    d = os.path.join(work, "project")
    problems: list[str] = []
    try:
        t0 = time.time()
        copy_project(src, d)
        say(f"copied the project in {time.time() - t0:.0f} s")
        sm = json.load(open(os.path.join(d, "songmap.json"), encoding="utf-8"))
        duration = float(sm["duration"])
        lines = len([x for x in sm.get("lyrics", []) if x.get("start") is not None])
        say(f"song {duration:.1f} s, {lines} timed lyric lines")

        if titlecard.state(d)["gap"]:
            titlecard.make(d, {"title": "REHEARSAL", "subtitle": "a dress rehearsal", "anim": "pop", "color": "#ffd166", "background": {"type": "colour", "color": "#2a0a12", "color2": "#8a1c2c"}})
        made = layerkit.lyrics_layers(d, {"anim": "typewriter", "position": "bottom", "size": 0.06})["made"] if lines else 0
        mid = duration / 2
        O.add(d, {"kind": "shape", "shape": "rounded", "width": 0.12, "height": 0.04, "x": 0.5, "y": 0.5, "color": "#ffd166", "start": mid - 5, "end": mid + 5,
                  "keys": [{"t": 0, "x": 0.1}, {"t": 10, "x": 0.9}]})
        O.add(d, {"kind": "icon", "icon": "crown", "width": 0.06, "x": 0.92, "y": 0.1, "color": "#ffd166", "start": 2, "end": min(duration, 20), "anim": "pulse"})
        layers = len([o for o in O.load(d) if o.get("enabled", True)])
        say(f"{layers} layers ({made} lyric layers)")

        preset = a.preset or E.preset_for(json.load(open(os.path.join(d, "project.json"), encoding="utf-8")).get("aspect_ratio"))
        t0 = time.time()
        out = E.build(d, preset)
        secs = time.time() - t0
        film = out["path"]
        p = subprocess.run([E.ffmpeg(), "-hide_banner", "-i", film], capture_output=True, text=True, encoding="utf-8", errors="replace")
        m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", p.stderr)
        length = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0
        say(f"exported {preset} in {secs:.0f} s: {length:.1f} s long, {os.path.getsize(film) / 1e6:.0f} MB, {out.get('overlays', 0)} layers drawn, "
            f"{'with sound' if 'Audio:' in p.stderr else 'NO SOUND'}, {out.get('rendered', 0)} of {out.get('shots', 0)} shots had takes")
        if abs(length - duration) > 0.6:
            problems.append(f"the film is {length:.1f} s but the song is {duration:.1f} s")
        if "Audio:" not in p.stderr:
            problems.append("the film has no sound")
        if out.get("overlay_error"):
            problems.append(f"the layers were not drawn: {out['overlay_error']}")
        elif out.get("overlays", 0) != layers:
            problems.append(f"{layers} layers were set up but {out.get('overlays', 0)} were drawn")
        looks = os.path.join(work, "frames")
        os.makedirs(looks, exist_ok=True)
        for frac in (0.01, 0.1, 0.3, 0.5, 0.8):
            t = round(duration * frac, 2)
            subprocess.run([E.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", str(t), "-i", film, "-frames:v", "1", "-vf", "scale=640:-1", os.path.join(looks, f"at-{t}.png")], check=False)
        say(f"frames to look at: {looks}")
    finally:
        if a.keep:
            say(f"kept: {work}")
        else:
            shutil.rmtree(os.path.join(work, "project"), ignore_errors=True)
            say(f"(the copy was deleted; the sample frames are still in {work})")
    if problems:
        say("PROBLEMS: " + "; ".join(problems))
        return 1
    say("the rehearsal passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
