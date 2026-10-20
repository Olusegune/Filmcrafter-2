"""Check the finished film file: is it the film that was asked for?

After an export the file is read back once, start to finish, and compared with what the export meant to make. It catches the faults that otherwise only show when someone watches the whole film:
a picture or sound shorter or longer than it should be, no sound at all, a silent film where voices or cues were laid, a black stretch, a frozen stretch.

  fix    the film is wrong (not readable, no picture, the wrong length, sound and picture out of step)
  look   worth a look (a long black or frozen stretch, silent sound, no sound)
  note   for information

Free, local and read-only: it only reads the file it is given. It never raises: a check that cannot run says so and the film is kept.
"""
from __future__ import annotations

import re
import subprocess
import sys

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
LENGTH_SLACK = 0.12          # seconds the picture may differ from the length asked for (about three frames)
SOUND_SLACK = 0.35           # seconds the sound may differ from the picture (the audio codec pads a little)
BLACK_MIN = 1.0              # a black stretch this long is worth a look
FREEZE_MIN = 2.5             # so is a frozen one
TIMEOUT = 900


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _seconds(h: str, m: str, s: str) -> float:
    return int(h) * 3600 + int(m) * 60 + float(s)


def _pairs(starts: list[float], ends: list[float], durations: list[float] | None = None) -> list[tuple[float, float]]:
    out = []
    for i, a in enumerate(starts):
        b = ends[i] if i < len(ends) else (a + durations[i] if durations and i < len(durations) else None)
        if b is not None:
            out.append((round(a, 2), round(b, 2)))
    return out


def verify(path: str, expected_seconds: float, *, fps: int = 24, expect_sound: bool | None = None, draft: bool = False) -> dict:
    """What the finished file really holds, and what is wrong with it. `expect_sound` is True when the export laid voices, cues or a song; `draft` is True when some shots are slates (a frozen
    picture is then expected and is not called a fault)."""
    findings: list[dict] = []

    def add(level: str, what: str, where: tuple[float, float] | None = None):
        findings.append({"level": level, "what": what, **({"from": where[0], "to": where[1]} if where else {})})
    try:
        p = subprocess.run([_ffmpeg(), "-hide_banner", "-nostats", "-i", path, "-vf", f"blackdetect=d={BLACK_MIN}:pix_th=0.05,freezedetect=n=-60dB:d={FREEZE_MIN}",
                            "-af", "silencedetect=n=-60dB:d=2", "-f", "null", "-"], capture_output=True, text=True, creationflags=NO_WINDOW, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": None, "checked": False, "findings": [{"level": "note", "what": f"The finished film could not be checked ({type(e).__name__})."}]}
    err = p.stderr or ""
    video = re.search(r"Stream #\d+:\d+[^:]*: Video: [^\n]*?(\d{2,5})x(\d{2,5})", err)
    audio = re.search(r"Stream #\d+:\d+[^:]*: Audio:", err)
    if p.returncode != 0 or not video:
        return {"ok": False, "checked": True, "findings": [{"level": "fix", "what": "The finished file could not be read as a film with a picture."}]}
    frames = [int(x) for x in re.findall(r"frame=\s*(\d+)", err)]
    times = re.findall(r"time=(\d+):(\d+):(\d+\.\d+)", err)
    got = _seconds(*times[-1]) if times else None
    out = {"checked": True, "width": int(video.group(1)), "height": int(video.group(2)), "frames": frames[-1] if frames else None, "has_sound": bool(audio)}
    # the picture's own length, from its frame count (the last time= is the longer of picture and sound)
    pic = (frames[-1] / fps) if frames else got
    if pic is not None:
        out["picture_seconds"] = round(pic, 2)
        if expected_seconds and abs(pic - expected_seconds) > LENGTH_SLACK:
            add("fix", f"The picture is {pic:.2f} s long but the film should be {expected_seconds:.2f} s.")
        if got is not None and audio and abs(got - pic) > SOUND_SLACK:
            add("fix", f"The sound ends {abs(got - pic):.2f} s {'after' if got > pic else 'before'} the picture.")
    if not audio:
        add("look" if expect_sound else "note", "The film has no sound track." if expect_sound else "The film has no sound.")
    end_of_film = pic if pic is not None else got
    black_s, black_e = [float(x) for x in re.findall(r"black_start:([\d.]+)", err)], [float(x) for x in re.findall(r"black_end:([\d.]+)", err)]
    if len(black_s) > len(black_e) and end_of_film is not None:
        black_e.append(end_of_film)                          # a stretch that runs to the end of the film has no end line of its own
    black = _pairs(black_s, black_e)
    for a, b in black[:10]:
        add("look", f"The picture is black from {a:.1f} s to {b:.1f} s.", (a, b))
    fr_s, fr_e = [float(x) for x in re.findall(r"freeze_start:\s*([\d.]+)", err)], [float(x) for x in re.findall(r"freeze_end:\s*([\d.]+)", err)]
    if len(fr_s) > len(fr_e) and end_of_film is not None:
        fr_e.append(end_of_film)
    freeze = _pairs(fr_s, fr_e)
    if freeze and not draft:
        for a, b in freeze[:10]:
            add("look", f"The picture does not move from {a:.1f} s to {b:.1f} s.", (a, b))
    elif freeze and draft:
        add("note", f"{len(freeze)} still stretch{'es' if len(freeze) > 1 else ''} (expected: some shots are still slates in this draft).")
    if audio:
        sil_s = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", err)]
        sil_e = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", err)]
        silent = _pairs([max(0.0, x) for x in sil_s], sil_e)
        if sil_s and len(sil_e) < len(sil_s) and got is not None:
            silent.append((round(max(0.0, sil_s[-1]), 2), round(got, 2)))
        total = sum(b - a for a, b in silent)
        if got and silent and total >= got * 0.97:
            add("look", "The sound is silent all the way through.")
        elif silent and total >= 5 and got and total >= got * 0.4:
            add("note", f"{total:.0f} s of the film is silent ({total / got * 100:.0f}%).")
    rank = {"fix": 0, "look": 1, "note": 2}
    findings.sort(key=lambda f: (rank[f["level"]], f.get("from", 0)))
    out["findings"] = findings
    out["ok"] = not any(f["level"] == "fix" for f in findings)
    return out
