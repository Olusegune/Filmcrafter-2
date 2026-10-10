"""Make a small sample hand-off folder with REAL video clips, to try in DaVinci Resolve, Premiere Pro or Final Cut.

A tiny film is built (three scenes), each shot gets a coloured clip with its id on it (made by FFmpeg, nothing is sent anywhere), and the same hand-off FilmCrafter writes for a real film
is written next to it: the EDL, OpenTimelineIO, Final Cut Pro XML, the shot manifest, subtitles and the copied clips.

  python scripts/make_handoff_sample.py [output folder]          (default: ./handoff-sample)

Then import it:
  DaVinci Resolve:  File > Import > Timeline > Import AAF, EDL, XML...  and choose the .fcpxml (or the .edl)
  Premiere Pro:     File > Import... and choose the .xml (Final Cut Pro XML), or the .edl
  Final Cut Pro:    File > Import > XML...  and choose the .fcpxml
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "analysis"))

from filmcrafter_engine import bible, interchange, make, shots, story  # noqa: E402

SCRIPT = "\n".join(["INT. KITCHEN - MORNING", "", "Sarah pours tea. Her hands are not steady.", "", "SARAH", "(quietly)", "He said he would call.", "", "JOHN", "Did you say something?", "",
                    "EXT. PLATFORM - NIGHT", "", "Rain on the roof. A train waits.", "", "SARAH", "I am going.", "", "INT. TRAIN - NIGHT", "", "Sarah sits. She looks at her phone. Nothing.", ""])
COLOURS = ["0x3b4a6b", "0x6b3b4a", "0x4a6b3b", "0x6b5a3b", "0x3b6b64", "0x5a3b6b", "0x6b3b3b", "0x3b5a6b"]


def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def clip(path: str, seconds: float, colour: str, label: str) -> None:
    text = label.replace(":", "\\:")
    vf = f"drawtext=text='{text}':fontcolor=white:fontsize=72:x=(w-text_w)/2:y=(h-text_h)/2" if os.path.exists("C:/Windows/Fonts/arial.ttf") else "null"
    if "drawtext" in vf:
        vf = vf.replace("drawtext=", "drawtext=fontfile='C\\:/Windows/Fonts/arial.ttf':")
    cmd = [ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={colour}:s=1280x720:r=24:d={seconds}", "-vf", vf, "-pix_fmt", "yuv420p", "-c:v", "libx264", path]
    subprocess.run(cmd, check=True)


def main(out: str) -> None:
    work = tempfile.mkdtemp(prefix="fc-sample-")
    d = story.create(work, "Last Train", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    ids = [s["id"] for s in shots.breakdown(d)["shots"]]
    make.sync(d)
    rd = make.render_dir(d)
    os.makedirs(os.path.join(rd, "media"), exist_ok=True)
    contracts = {c["id"]: c for c in make._contracts(d)}
    jobs = []
    for i, sid in enumerate(ids):
        seconds = float(contracts[sid]["generation"]["duration"])
        rel = f"media/v{i}.mp4"
        clip(os.path.join(rd, rel), seconds, COLOURS[i % len(COLOURS)], sid)
        jobs.append({"id": f"v{i}", "shot_id": sid, "plan": "production", "state": "ready", "kind": "video", "provider": "sample", "model": "sample", "output": rel,
                     "created": 1 + i, "updated": 1 + i, "approved": True})
    json.dump({"schema_version": 1, "jobs": jobs}, open(os.path.join(rd, "jobs.json"), "w"))
    res = interchange.write(d)
    if os.path.exists(out):
        shutil.rmtree(out)
    shutil.copytree(res["dir"], out)
    shutil.rmtree(work, ignore_errors=True)
    print(f"{len(ids)} shots, hand-off written to {out}")
    for f in sorted(os.listdir(out)):
        print("  ", f)


if __name__ == "__main__":
    main(os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.abspath("handoff-sample"))
