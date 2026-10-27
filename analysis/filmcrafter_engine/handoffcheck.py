"""Read a finished hand-off folder back and say, in plain words, whether it will open cleanly in an editor, and write the film's sound as one finished file per track.

The hand-off is only worth sending if the editor opens it without a surprise. After it is written, this reads the files again as an editor would, not as FilmCrafter wrote them:

  - every file a timeline points at is really in the folder
  - no track plays two sounds at once, and none runs past the end of the film
  - the Final Cut XML is well-formed, every clip refers to something it defines, and every lane is where an editor expects it
  - the EDL has one event for each shot that has a take

It returns a list of problems (empty is good). Each is a sentence a person can act on. It never raises: a check that cannot run says so. `write_stems` also gives each track as one stereo WAV
(voices, effects, ambience, music), for an editor who would rather bring in finished files than a timeline, and for After Effects, which has no timeline import.
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET

from . import safeio

SLACK_FRAMES = 1


def _rv(t: dict) -> float:
    return float((t or {}).get("value") or 0)


def check(out: str, files: dict[str, str], placed: int, total_frames: int) -> list[str]:
    problems: list[str] = []
    try:
        otio = json.load(open(os.path.join(out, files["otio"]), encoding="utf-8"))
        for track in otio["tracks"]["children"]:
            cur = 0.0
            for c in track["children"]:
                dur = _rv(c["source_range"]["duration"])
                if c["OTIO_SCHEMA"].startswith("Clip"):
                    ref = c.get("media_reference") or {}
                    url = ref.get("target_url")
                    if not url or not os.path.isfile(os.path.join(out, *url.split("/"))):
                        problems.append(f"{track['name']}: the sound or picture for \"{c['name']}\" is not in the folder.")
                    avail = _rv((ref.get("available_range") or {}).get("duration")) if ref.get("available_range") else None
                    if avail is not None and _rv(c["source_range"]["start_time"]) + dur > avail + SLACK_FRAMES:
                        problems.append(f"{track['name']}: \"{c['name']}\" is longer than its sound.")
                cur += dur
            if cur > total_frames + SLACK_FRAMES + 1:
                problems.append(f"{track['name']} runs {round((cur - total_frames) / 24, 1)} s past the end of the film.")
    except (OSError, ValueError, KeyError, TypeError) as e:
        problems.append(f"The OpenTimelineIO file could not be read back ({type(e).__name__}).")
    try:
        root = ET.parse(os.path.join(out, files["fcpxml"])).getroot()
        assets = {a.get("id"): a for a in root.iter("asset")}
        for c in root.iter("asset-clip"):
            if c.get("ref") not in assets:
                problems.append(f"Final Cut XML: \"{c.get('name')}\" points at something that is not defined.")
        for a in assets.values():
            rep = a.find("media-rep")
            if rep is not None and rep.get("src") and not os.path.isfile(os.path.join(out, *rep.get("src").split("/"))):
                problems.append(f"Final Cut XML: the file for \"{a.get('name')}\" is not in the folder.")
        lanes: dict[str, list[tuple[int, int]]] = {}
        for c in root.iter("asset-clip"):
            if c.get("lane"):
                num = lambda s: int(str(s).split("/")[0])          # noqa: E731  frames: "120/24s"
                lanes.setdefault(c.get("lane"), []).append((num(c.get("offset")), num(c.get("offset")) + num(c.get("duration"))))
        for lane, spans in lanes.items():
            spans.sort()
            if any(b[0] < a[1] - SLACK_FRAMES for a, b in zip(spans, spans[1:])):
                problems.append(f"Final Cut XML: two sounds overlap on lane {lane}.")
    except (OSError, ET.ParseError, ValueError, TypeError) as e:
        problems.append(f"The Final Cut XML could not be read back ({type(e).__name__}).")
    try:
        events = sum(1 for line in open(os.path.join(out, files["edl"]), encoding="utf-8") if line[:3].isdigit() and " V " in line)
        if events != placed:
            problems.append(f"The EDL has {events} picture events but {placed} shots have a take.")
    except OSError:
        problems.append("The EDL could not be read back.")
    return problems


def write_stems(out: str, tracks: list[dict], seconds: float) -> list[str]:
    """One stereo WAV per track at its real place on the film: `audio/stems/<track>.wav`. Returns the relative names. A track whose sounds cannot be read is left out, not guessed."""
    import numpy as np
    import soundfile as sf
    from . import shotsound
    from .safe import file_name
    rate = shotsound.RATE
    total = int(round(seconds * rate))
    done: list[str] = []
    for t in tracks:
        mix = np.zeros((total, 2), dtype=np.float32)
        used = 0
        for c in t["clips"]:
            path = c.get("path")
            if not path or not os.path.isfile(path):
                continue
            try:
                x = shotsound.decode(path, 2)
            except Exception:
                continue
            a = int(round(c.get("source_start", 0) / 24 * rate))
            n = int(round(c["frames"] / 24 * rate))
            x = x[a:a + n]
            if not len(x):
                continue
            x = x * float(10 ** (float(c.get("gain_db") or 0) / 20))
            fi, fo = int(float(c.get("fade_in") or 0) * rate), int(float(c.get("fade_out") or 0) * rate)
            if fi > 1:
                x[:fi] *= np.linspace(0, 1, min(fi, len(x)), dtype=np.float32)[:, None]
            if fo > 1:
                x[-fo:] *= np.linspace(1, 0, min(fo, len(x)), dtype=np.float32)[:, None]
            at = int(round(c["start"] / 24 * rate))
            if at >= total:
                continue
            x = x[: total - at]
            mix[at:at + len(x)] += x
            used += 1
        if not used:
            continue
        peak = float(np.max(np.abs(mix)))
        if peak > 0.98:
            mix *= 0.98 / peak
        rel = "audio/stems/" + file_name(t["name"].replace(" ", "_") + ".wav", 40)
        os.makedirs(os.path.join(out, "audio", "stems"), exist_ok=True)
        sf.write(os.path.join(out, *rel.split("/")), mix, rate, subtype="PCM_16")
        done.append(rel)
    return done


def save_report(out: str, problems: list[str]) -> None:
    safeio.write_json(os.path.join(out, "handoff-check.json"), {"problems": problems, "ok": not problems})
