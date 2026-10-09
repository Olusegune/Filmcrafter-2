"""Project-creation helpers for the setup wizard: probe a song, take a video's soundtrack, transcribe lyrics,
and keep choreography as structured production data.

  probe <file>                      -> {duration, peaks[600], title, artist, kind, has_audio}
  extract <video> <out.wav>         -> {path, duration}
  transcribe <project>              -> {lines:[{text,start,end}], text}   (vocal stem + Whisper; minutes)
  choreo_get / choreo_set <project> -> choreography.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

import numpy as np

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
MODES = ["none", "upload", "written", "style", "ai"]
STYLES = ["Contemporary", "Hip-hop", "Afrobeats", "Amapiano", "Ballet", "Jazz", "K-pop", "Latin", "Street / freestyle",
          "Ballroom", "Traditional / cultural", "Minimal performance (no dance)"]


def emit(**kw) -> None:
    try:
        print(json.dumps(kw, ensure_ascii=False), flush=True)
    except (OSError, ValueError):   # the app went away: nobody to tell
        pass


def ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _meta(path: str) -> dict:
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", path], capture_output=True, text=True, errors="replace",
                       creationflags=NO_WINDOW)
    txt = r.stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", txt)
    tags = {}
    for key in ("title", "artist"):
        t = re.search(rf"^\s*{key}\s*:\s*(.+)$", txt, re.M | re.I)
        if t:
            tags[key] = t.group(1).strip()
    return {"duration": int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None,
            "has_audio": "Audio:" in txt, "has_video": bool(re.search(r"Video: (?!mjpeg|png)", txt)), **tags}


def probe(path: str, bins: int = 600) -> dict:
    """What the Upload Music step shows: real duration and a waveform of the actual file."""
    if not os.path.exists(path):
        raise SystemExit("That file can't be found.")
    ext = os.path.splitext(path)[1].lower()
    if ext not in AUDIO_EXT | VIDEO_EXT:
        raise SystemExit("Use an audio file (MP3, WAV, M4A, FLAC) or a video with a soundtrack (MP4, MOV).")
    meta = _meta(path)
    if not meta["has_audio"]:
        raise SystemExit("This file has no audio track FilmCrafter can read.")
    raw = subprocess.run([ffmpeg(), "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "4000", "-f", "s16le", "-"],
                         capture_output=True, creationflags=NO_WINDOW).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if not len(x):
        raise SystemExit("The audio couldn't be decoded. The file may be damaged or use an unusual codec.")
    duration = meta["duration"] or len(x) / 4000
    edges = np.linspace(0, len(x), bins + 1).astype(int)
    peaks = [float(np.abs(x[a:b]).max()) if b > a else 0.0 for a, b in zip(edges[:-1], edges[1:])]
    top = max(peaks) or 1.0
    return {"duration": round(duration, 3), "peaks": [round(p / top, 3) for p in peaks],
            "title": meta.get("title"), "artist": meta.get("artist"),
            "kind": "video" if ext in VIDEO_EXT else "audio", "has_audio": True}


def extract(video: str, out: str) -> dict:
    """The soundtrack of a video as the master audio (only when the user chooses it)."""
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    r = subprocess.run([ffmpeg(), "-y", "-v", "error", "-i", video, "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", out],
                       capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW)
    if r.returncode or not os.path.exists(out):
        raise SystemExit(f"Couldn't take the audio from that video. {r.stderr.strip()[:200]}")
    return {"path": out, "duration": _meta(out)["duration"]}


def transcribe(d: str) -> dict:
    """Lyrics heard in the song: vocal stem first (music confuses speech models), then Whisper with timings.
    The stem is cached where the analysis looks for it, so it isn't separated twice."""
    from .lyrics import _enable_cuda_dlls, separate_vocals
    project = json.load(open(os.path.join(d, "project.json"), encoding="utf-8"))
    song = os.path.join(d, project.get("song", "song.wav"))
    emit(event="progress", stage="isolating the vocal", progress=0.1)
    vocals = separate_vocals(song, os.path.join(d, "cache", "stems"))
    emit(event="progress", stage="listening to the words", progress=0.55)
    _enable_cuda_dlls()
    from faster_whisper import WhisperModel
    try:
        model = WhisperModel("large-v3", device="cuda", compute_type="float16")
    except Exception:
        model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(vocals, vad_filter=True, condition_on_previous_text=False)
    lines, text, last_end = [], [], None
    for seg in segments:
        t = seg.text.strip()
        if not t:
            continue
        if last_end is not None and seg.start - last_end > 2.5:
            text.append("")  # a pause becomes a stanza break
        lines.append({"text": t, "start": round(seg.start, 2), "end": round(seg.end, 2)})
        text.append(t)
        last_end = seg.end
        emit(event="progress", stage="listening to the words", progress=min(0.95, 0.55 + 0.4 * seg.end / max(1.0, _meta(song)["duration"] or 1)))
    if not lines:
        raise SystemExit("No sung words were heard. For instrumentals, skip this step.")
    out = {"lines": lines, "text": "\n".join(text), "made": int(time.time())}
    json.dump(out, open(os.path.join(d, "cache", "transcript.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out


# ---------------------------------------------------------------- choreography

def choreo_get(d: str) -> dict:
    try:
        return json.load(open(os.path.join(d, "choreography.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {"mode": None, "style": None, "notes": "", "files": [], "sections": [], "precise": False}


def choreo_set(d: str, data: dict) -> dict:
    """Structured choreography: a mode, an overall style, free notes, reference files and per-section cues
    ({section, performers, notes}). `precise` is only true for time-aligned material; AI video treats all of
    this as direction, not exact steps."""
    if data.get("mode") not in MODES:
        raise SystemExit("Choose how the movement should be decided.")
    files = [f for f in data.get("files") or [] if os.path.exists(os.path.join(d, f))]
    sections = [{"section": str(s.get("section", "")).strip(), "performers": [p for p in s.get("performers") or [] if p],
                 "notes": str(s.get("notes", "")).strip()} for s in data.get("sections") or [] if str(s.get("notes", "")).strip()]
    out = {"mode": data["mode"], "style": data.get("style") if data.get("style") in STYLES else None,
           "notes": str(data.get("notes") or "").strip()[:4000], "files": files, "sections": sections,
           "precise": bool(data.get("precise")) and data["mode"] == "upload", "updated": int(time.time())}
    if data["mode"] != "none" and choreo_get(d).get("plan"):
        out["plan"] = choreo_get(d)["plan"]   # a designed plan survives edits to the setup (redesign to refresh it)
    tmp = os.path.join(d, f"choreography.json.{os.getpid()}.tmp")
    json.dump(out, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(d, "choreography.json"))
    return out


def _shot_section(d: str, shot: dict) -> str:
    """A shot's song section ('Chorus 2'), from the plan if recorded, else from its time on the song map."""
    if shot.get("section"):
        return str(shot["section"])
    try:
        from .choreo import numbered_sections, section_at
        sm = json.load(open(os.path.join(d, "songmap.json"), encoding="utf-8"))
        sec = section_at(numbered_sections(sm), (shot.get("start", 0) + shot.get("end", 0)) / 2)
        return sec["name"] if sec else ""
    except (OSError, ValueError, KeyError):
        return ""


_DANCE_WORDS = re.compile(r"\b(danc\w*|choreograph\w*|groov\w*|sway\w*|twirl\w*|shimmy\w*|strut\w*|footwork|formation|routine|(?:to|on|with) the (?:beat|rhythm|music))\b", re.I)


def _shot_text(shot: dict) -> str:
    return (" ".join(str(shot.get(k) or "") for k in ("description", "performance", "movement", "visual_prompt", "purpose")) + " " + " ".join(str(b) for b in shot.get("beats") or [])).strip()


def is_dance_shot(shot: dict) -> bool:
    """Does this shot's own text describe dancing? (Its action, performance, movement and prompt: not the song section it sits in, which says nothing about this shot.)"""
    return bool(_DANCE_WORDS.search(_shot_text(shot)))


def dance_override(d: str, shot_id: str | None) -> str:
    """'on' (always give this shot the dance direction), 'off' (never), or 'auto' (the default). Chosen per shot in the Acting panel; kept in project.json as dance_shots."""
    try:
        with open(os.path.join(d, "project.json"), encoding="utf-8") as f:
            v = (json.load(f).get("dance_shots") or {}).get(shot_id or "")
    except (OSError, ValueError, AttributeError):
        return "auto"
    return v if v in ("on", "off") else "auto"


def _beat(d: str, shot: dict) -> str:
    """The beat structure of a dance shot (beats, bars, whether it starts on a downbeat), as a sentence to append; empty when the tempo is unknown."""
    from .dance import beat_line
    line = beat_line(d, shot)
    return f" {line}" if line else ""


def movement_for(d: str, shot: dict, kind: str = "video") -> str | None:
    """Choreography for one shot's prompt. kind="image": the starting pose (keyframes); "video": the motion.
    A designed plan (Choreography Engine) wins; otherwise style + cues matching the shot's section."""
    c = choreo_get(d)
    if c.get("mode") in (None, "none") or not shot.get("performers"):
        return None
    if c.get("style") == "Minimal performance (no dance)":
        return None
    mode = dance_override(d, shot.get("id"))
    if mode == "off":
        return None
    planned = ((c.get("plan") or {}).get("shots") or {}).get(shot.get("id", ""))
    if planned:
        if kind == "image":
            return f"Dance pose, caught mid-move: {planned['pose'].rstrip('.')}." if planned.get("pose") else None
        bpm = (c.get("plan") or {}).get("bpm")
        tempo = f", on the beat at {round(bpm)} BPM" if bpm else ", on the beat"
        style = f"{c['style']} " if c.get("style") else ""
        return f"Choreography ({style}dance{tempo}): {planned['motion'].rstrip('.')}." + _beat(d, shot)
    if (c.get("plan") or {}).get("shots") is not None:
        return None   # a designed plan exists and this shot is acting-led
    parts = []
    if c.get("style"):
        parts.append(f"{c['style']} movement")
    sec = _shot_section(d, shot).lower()
    for s in c.get("sections") or []:
        name = s["section"].lower().strip("[] ")
        if name and name.split()[0] in sec and (not s["performers"] or set(s["performers"]) & set(shot["performers"])):
            parts.append(s["notes"])
    if c.get("notes") and len(parts) < 3:
        parts.append(c["notes"][:300])
    if c.get("mode") == "ai" and not parts:
        parts.append("choreographed to the beat, movement that fits the song's energy")
    if not parts:
        return None
    if mode != "on" and _shot_text(shot) and not is_dance_shot(shot):      # a shot with no text at all is not known to be anything else: it keeps the full direction
        # Notes written for a song section reach every shot of it where these people appear, including shots that are about something else (a person unrolling a runner is not
        # doing the entrance step). A keyframe must not start in a dance pose, and a video is told the action it was given always wins.
        if kind == "image":
            return None
        return "Dance direction for this song section applies only if this shot's action is dancing; the action described above always wins."
    return ("Movement direction: " if kind == "image" else "Choreography: ") + "; ".join(p.rstrip(".") for p in parts) + "." + (_beat(d, shot) if kind == "video" else "")


DOC_EXT = (".pdf", ".docx", ".txt", ".md", ".fountain")
MAX_DOC_BYTES = 25 * 1024 * 1024
MAX_DOC_CHARS = 6000


def doc_text(path: str) -> dict:
    """The words in a document the user chose (PDF, Word, text), so choreography notes can be read from it. Nothing is copied into the project."""
    import re
    path = os.path.abspath(str(path or ""))
    if not path.lower().endswith(DOC_EXT) or not os.path.isfile(path):
        raise SystemExit("Choose a PDF, Word (.docx), text or Markdown file.")
    if os.path.getsize(path) > MAX_DOC_BYTES:
        raise SystemExit("That document is larger than 25 MB.")
    low = path.lower()
    try:
        if low.endswith(".pdf"):
            from pypdf import PdfReader
            text = "\n".join(p.extract_text() or "" for p in PdfReader(path).pages)
        elif low.endswith(".docx"):
            import zipfile
            with zipfile.ZipFile(path) as z:
                xml = z.read("word/document.xml").decode("utf-8", "replace")
            text = re.sub(r"<w:p[ >/]", "\n<w:p ", xml)
            text = re.sub(r"<[^>]+>", "", text)
            text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'")
        else:
            text = open(path, encoding="utf-8-sig", errors="replace").read()
    except SystemExit:
        raise
    except Exception:
        raise SystemExit("That document couldn't be read. If it is a scan or protected, paste the key notes instead.")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    if not text:
        raise SystemExit("No text was found in that document (a scan? paste the key notes instead).")
    return {"name": os.path.basename(path), "text": text[:MAX_DOC_CHARS], "truncated": len(text) > MAX_DOC_CHARS}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-onboarding")
    ap.add_argument("action", choices=["probe", "extract", "transcribe", "choreo_get", "choreo_set", "styles", "doc_text"])
    ap.add_argument("target", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    try:
        if a.action == "probe":
            res = probe(a.target)
        elif a.action == "extract":
            res = extract(a.target, a.out)
        elif a.action == "transcribe":
            res = transcribe(a.target)
        elif a.action == "doc_text":
            res = doc_text(a.target)
        elif a.action == "choreo_get":
            res = choreo_get(a.target)
        elif a.action == "choreo_set":
            res = choreo_set(a.target, json.loads(a.data))
        else:
            res = {"styles": STYLES}
        emit(event="result", data=res)
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=f"{type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
