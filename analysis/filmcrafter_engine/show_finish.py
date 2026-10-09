"""The finishing touches of a show: subtitles and chapters, intermission cards, ambience under a scene, and the show budget.

All of it is local: ffmpeg and Pillow, no network, nothing billed. Text from a script or a dialogue line reaches ffmpeg only
as data in a file (an .srt or an ffmetadata file, escaped for that format) or is drawn by Pillow, never placed in a filter
or a command line, so a line of dialogue can't change what ffmpeg runs. Files the user adds (ambience) are limited to audio
extensions and a size, and are copied in, never moved.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
AUDIO = (".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg")
MAX_AMBIENCE = 300_000_000
KIE_USD_PER_CREDIT = 0.005
MIN_CARD, MAX_CARD = 2.0, 60.0


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _run(args: list[str]) -> None:
    from .export import ffmpeg
    r = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True, text=True, creationflags=NO_WINDOW)
    if r.returncode:
        raise RuntimeError((r.stderr.strip().splitlines() or ["ffmpeg failed"])[-1])


# ---------------------------------------------------------------- subtitles and chapters

def _clock(t: float, comma: bool = True) -> str:
    t = max(0.0, t)
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{',' if comma else '.'}{ms:03d}"


def _clean(text: str) -> str:
    """One caption's text: single spaces, no blank lines (they end a cue) and no cue-timing arrows."""
    return " ".join(str(text).replace("-->", "->").split())[:300]


def item_cues(item_dir: str, kind: str, names: bool = True) -> list[tuple[float, float, str]]:
    """(start, end, text) seconds within one item: the spoken lines of a scene (with who says them), or a number's lyrics."""
    out = []
    if kind == "scene":
        for t in (_read(os.path.join(item_dir, "dialogue.json"), {}) or {}).get("timings") or []:
            if t.get("text"):
                who = _clean(t.get("character") or "")
                out.append((float(t["start"]), float(t["end"]), f"{who}: {_clean(t['text'])}" if names and who else _clean(t["text"])))
    elif kind == "number":
        for ln in (_read(os.path.join(item_dir, "songmap.json"), {}) or {}).get("lyrics") or []:
            if ln.get("text") and ln.get("end") is not None:
                out.append((float(ln["start"]), float(ln["end"]), _clean(ln["text"])))
    return [c for c in out if c[1] > c[0] and c[2]]


def write_srt(path: str, cues: list[tuple[float, float, str]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for n, (a, b, text) in enumerate(cues, 1):
            f.write(f"{n}\n{_clock(a)} --> {_clock(b)}\n{text}\n\n")


def chapter_list(entries: list[tuple[float, str]]) -> str:
    """YouTube-style chapters: 'm:ss Title' lines, the first at 0:00."""
    lines = []
    for t, title in entries:
        s = int(round(t))
        stamp = f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"
        lines.append(f"{stamp} {_clean(title)}")
    return "\n".join(lines) + "\n"


def _meta_escape(text: str) -> str:
    return re.sub(r"([=;#\\])", r"\\\1", _clean(text))


def write_chapters_meta(path: str, entries: list[tuple[float, str]], total: float) -> None:
    """An ffmpeg metadata file with one chapter per entry, each ending where the next begins."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(";FFMETADATA1\n")
        for i, (t, title) in enumerate(entries):
            end = entries[i + 1][0] if i + 1 < len(entries) else total
            f.write(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={int(t * 1000)}\nEND={max(int(end * 1000), int(t * 1000) + 1)}\ntitle={_meta_escape(title)}\n")


def add_subtitles_and_chapters(film: str, entries: list[tuple[float, str]], cues: list[tuple[float, float, str]], total: float,
                               want_subs: bool = True, want_chapters: bool = True) -> dict:
    """Write the sidecar .srt and chapters .txt next to the film and, when it works, embed both in the mp4. The film itself is
    never lost: if embedding fails the original stays as it was and the sidecars are still written."""
    base = os.path.splitext(film)[0]
    out: dict = {"subtitles": None, "chapters": None, "cues": len(cues), "embedded": False}
    srt = base + ".srt"
    if want_subs and cues:
        write_srt(srt, cues)
        out["subtitles"] = srt
    if want_chapters and entries:
        with open(base + " chapters.txt", "w", encoding="utf-8") as f:
            f.write(chapter_list(entries))
        out["chapters"] = base + " chapters.txt"
    if not (out["subtitles"] or out["chapters"]):
        return out
    meta, tmp = base + ".chapters.ffmeta", film + ".embed.mp4"
    try:
        args = ["-i", film]
        maps = ["-map", "0:v", "-map", "0:a"]
        if out["chapters"]:
            write_chapters_meta(meta, entries, total)
            args += ["-i", meta]
        if out["subtitles"]:
            args += ["-i", srt]
            maps += ["-map", str(len([a for a in args if a == "-i"]) - 1) + ":0"]
        _run([*args, *maps, "-map_metadata", "-1" if not out["chapters"] else "1", "-map_chapters", "1" if out["chapters"] else "-1",
              "-c", "copy", *(["-c:s", "mov_text", "-metadata:s:s:0", "language=eng"] if out["subtitles"] else []),
              "-movflags", "+faststart", tmp])
        os.replace(tmp, film)
        out["embedded"] = True
    except Exception as e:
        out["embed_error"] = str(e)[:200]
    finally:
        for f in (meta, tmp):
            if os.path.exists(f):
                os.remove(f)
    return out


# ---------------------------------------------------------------- intermission cards

def _font(size: int):
    from PIL import ImageFont
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _wrap(draw, text: str, font, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and draw.textlength(trial, font=font) > width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + ([cur] if cur else [])


def intermission_card(path: str, title: str, subtitle: str, w: int, h: int) -> None:
    """A title card as a PNG: white text on black, centred. Drawn by Pillow, so the text never goes through ffmpeg."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(img)
    big, small = _font(max(24, h // 10)), _font(max(16, h // 20))
    t_lines, s_lines = _wrap(d, title, big, int(w * 0.8)), _wrap(d, subtitle, small, int(w * 0.8)) if subtitle else []
    gap = h // 24
    rows = [(x, big, (255, 255, 255), 0) for x in t_lines] + [(x, small, (200, 200, 200), gap if i == 0 else 0) for i, x in enumerate(s_lines)]
    total = sum(f.size * 1.2 + before for _, f, _, before in rows)
    y = (h - total) / 2
    for text, font, color, before in rows:
        y += before
        d.text(((w - d.textlength(text, font=font)) / 2, y), text, font=font, fill=color)
        y += font.size * 1.2
    img.save(path)


def intermission_clip(out: str, title: str, subtitle: str, seconds: float, w: int, h: int, fps: int) -> str:
    """The card as a short film with silent stereo sound (so it joins the others), fading in and out."""
    seconds = min(MAX_CARD, max(MIN_CARD, float(seconds)))
    png = out + ".card.png"
    try:
        intermission_card(png, title, subtitle, w, h)
        fade = min(0.8, seconds / 4)
        _run(["-loop", "1", "-framerate", str(fps), "-t", f"{seconds:.3f}", "-i", png,
              "-f", "lavfi", "-t", f"{seconds:.3f}", "-i", "anullsrc=r=48000:cl=stereo",
              "-vf", f"fade=t=in:st=0:d={fade:.2f},fade=t=out:st={seconds - fade:.2f}:d={fade:.2f},format=yuv420p",
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-shortest", out])
    finally:
        if os.path.exists(png):
            os.remove(png)
    return out


# ---------------------------------------------------------------- ambience

def check_ambience(src: str, volume_db: float) -> float:
    if os.path.splitext(src)[1].lower() not in AUDIO or not os.path.isfile(src):
        raise SystemExit("Use an audio file (mp3, wav, m4a, flac, aac or ogg).")
    if os.path.getsize(src) > MAX_AMBIENCE:
        raise SystemExit("That audio file is too large (300 MB at most).")
    return min(0.0, max(-40.0, float(volume_db)))


def mix_ambience(part: str, ambience: str, volume_db: float, out: str, duration: float) -> str:
    """Lay an ambience or underscore file under a part's own sound: it loops to the length of the part and sits at
    volume_db. The part's picture is copied untouched."""
    _run(["-i", part, "-stream_loop", "-1", "-i", ambience,
          "-filter_complex", f"[1:a]volume={volume_db:.1f}dB,aformat=channel_layouts=stereo[b];[0:a]aformat=channel_layouts=stereo[a];"
                             f"[a][b]amix=inputs=2:duration=first:normalize=0[m]",
          "-map", "0:v", "-map", "[m]", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-t", f"{duration:.3f}", out])
    return out


# ---------------------------------------------------------------- budget

def budget_summary(cap_usd: float | None, spent_usd: float, rendered: int, remaining_shots: int) -> dict:
    """Where the show stands against its cap: spent, left, a warning from 80%, and a rough cost for the shots still to render at
    the rate so far (only once a few have been rendered, and only as a guide)."""
    rate = round(spent_usd / rendered, 3) if rendered >= 3 and spent_usd > 0 else None
    est = round(rate * remaining_shots, 2) if rate is not None else None
    out = {"cap_usd": cap_usd, "spent_usd": round(spent_usd, 2), "rate_per_shot": rate, "remaining_shots": remaining_shots,
           "estimate_remaining_usd": est, "remaining_usd": None, "over": False, "near": False, "estimate_over": False}
    if cap_usd:
        out["remaining_usd"] = round(cap_usd - spent_usd, 2)
        out["over"] = spent_usd >= cap_usd
        out["near"] = not out["over"] and spent_usd >= 0.8 * cap_usd
        out["estimate_over"] = est is not None and spent_usd + est > cap_usd
    return out
