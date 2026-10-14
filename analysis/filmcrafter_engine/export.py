"""Export: assemble rendered takes on the song's timeline into one finished video (PRD §31, §71 EXPORT).

The master song is the clock. Every shot occupies exactly [start, end) of the song, converted to
whole frames from absolute times (not by summing durations), so cuts never drift off the beat.
Each take is trimmed from its head to the shot length and crop-filled to the preset frame. Shots
without a finished take become storyboard slates, so a draft cut can be exported at any time.
The song is muxed untouched (re-encoded once to AAC) and the video is cut to the song's length.
"""
from __future__ import annotations

import argparse
import hashlib
from .safe import sha1 as _sha1
from . import transitions
import json
import os
import subprocess
import sys
import time
import textwrap

FPS = 24
ENCODING = 2        # raise when how the parts are encoded changes, so parts made earlier are made again (2: all parts carry the same colour labels)
PRESETS = {
    "youtube": {"label": "YouTube 16:9", "w": 1920, "h": 1080},
    "vertical": {"label": "TikTok / Reels 9:16", "w": 1080, "h": 1920},
    "square": {"label": "Square 1:1", "w": 1080, "h": 1080},
    "cinema": {"label": "Cinema 2.39:1", "w": 1920, "h": 804},
    "widescreen": {"label": "Ultra-wide 21:9", "w": 2520, "h": 1080},
    "standard": {"label": "Classic 4:3", "w": 1440, "h": 1080},
    "portrait": {"label": "Portrait 4:5", "w": 1080, "h": 1350},
    "tall": {"label": "Tall portrait 3:4", "w": 1080, "h": 1440},
    "ultratall": {"label": "Ultra-tall 9:21", "w": 1080, "h": 2520},
    "preview": {"label": "Preview 16:9", "w": 640, "h": 360},          # small and quick, for checking a piece of the film
}
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
PRESET_FOR_ASPECT = {"16:9": "youtube", "21:9": "widescreen", "2.39:1": "cinema", "4:3": "standard", "1:1": "square", "4:5": "portrait", "3:4": "tall", "9:16": "vertical", "9:21": "ultratall"}


def preset_for(aspect: str | None) -> str:
    """The export format that matches a project's shape (one for each shape a film can take), YouTube otherwise."""
    return PRESET_FOR_ASPECT.get(aspect or "", "youtube")


def emit(**kw) -> None:
    try:
        print(json.dumps(kw, ensure_ascii=False), flush=True)
    except (OSError, ValueError):   # the app went away: nobody to tell
        pass


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def last_frame_png(src: str, out: str) -> bool:
    """Save the final frame of a video as a picture. Asking for "the last 0.08 s" finds nothing in a clip whose frames are longer than that (a 12 fps take), so it asks again for a little more each
    time. True when a picture was written."""
    for back in ("-0.1", "-0.3", "-1.0", "-3.0"):
        if os.path.exists(out):
            os.remove(out)
        p = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-sseof", back, "-i", src, "-frames:v", "1", "-update", "1", out],
                           capture_output=True, text=True, creationflags=NO_WINDOW)
        if p.returncode == 0 and os.path.exists(out):
            return True
    return False


def _run(args: list[str]) -> None:
    p = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args],
                       capture_output=True, text=True, creationflags=NO_WINDOW)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip().splitlines()[-1] if p.stderr.strip() else "ffmpeg failed")


def _read(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def slate(path: str, w: int, h: int, shot: dict, scene: dict | None) -> None:
    """Storyboard card for a shot that has no finished take yet."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (w, h), (12, 15, 20))
    d = ImageDraw.Draw(im)

    def font(size, bold=False):
        for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), "arial.ttf", "DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    u = min(w, h) / 1080
    pad = int(90 * u)
    y = int(h * 0.30)
    d.text((pad, pad), shot["id"], font=font(int(34 * u), True), fill=(138, 201, 255))
    if scene:
        d.text((pad, y), scene["heading"].upper(), font=font(int(26 * u)), fill=(104, 114, 129))
        y += int(56 * u)
    text = shot.get("visual_prompt") or " ".join(shot.get("beats", [])) or shot.get("description", "")
    chars = max(20, int((w - 2 * pad) / (22 * u)))
    for line in textwrap.wrap(text, chars)[:8]:
        d.text((pad, y), line, font=font(int(40 * u)), fill=(244, 247, 250))
        y += int(56 * u)
    d.text((pad, h - pad - int(30 * u)), "Not rendered yet", font=font(int(26 * u)), fill=(232, 180, 92))
    im.save(path)


FADE_S = 0.3


def _fades(tin: str, tout: str, frames: int, tin_s=None, tout_s=None) -> str:
    """How a shot enters (and the next one leaves it): a dip to black or a flash of white (0.3 s unless a length was chosen)."""
    return transitions.fades(tin, tout, frames, FPS, tin_s, tout_s)


DISSOLVE_S = 0.5


def _dissolve(prev: str, cur: str, frames: int, enc: list[str]) -> None:
    """The previous shot's final frame fades out over the start of this one (a cross-dissolve that keeps every cut
    exactly on its frame: nothing is shifted or overlapped in time)."""
    n = max(2, min(round(DISSOLVE_S * FPS), frames // 2))
    last = cur + ".last.png"
    _run(["-sseof", "-0.1", "-i", prev, "-frames:v", "1", "-update", "1", last])
    tmp = cur + ".dx.mp4"
    _run(["-i", cur, "-loop", "1", "-framerate", str(FPS), "-i", last, "-filter_complex",
          f"[1:v]format=rgba,fade=t=out:s=0:n={n}:alpha=1,trim=end_frame={n}[ov];[0:v][ov]overlay=eof_action=pass,format=yuv420p",
          "-frames:v", str(frames), *enc, tmp])
    os.replace(tmp, cur)
    os.remove(last)


def _enter(prev: str, cur: str, frames: int, enc: list[str], kind: str, chosen, w: int, h: int) -> None:
    """Every transition except the cut and the two dips: the previous shot's last frame is taken away over the start of this one."""
    transitions.enter(_run, prev, cur, frames, enc, kind, chosen, w, h, FPS)


def ken_burns(motion: str | None, frames: int, w: int, h: int, drift: dict | None = None) -> str:
    """A slow camera move over a still: zoom in/out or pan, ending exactly on the shot's last frame.
    drift (performance micro-animation): a gentle breathing push and sway, sized by the performance profile."""
    n = max(1, frames - 1)
    W, H = w * 2, h * 2   # work at double size so the move stays smooth
    pre = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    z, x, y = "1", cx, cy
    if motion == "zoom_in":
        z = f"1+0.18*on/{n}"
    elif motion == "zoom_out":
        z = f"1.18-0.18*on/{n}"
    elif motion in ("pan_left", "pan_right", "pan_up", "pan_down"):
        z = "1.18"
        t = f"on/{n}" if motion in ("pan_right", "pan_down") else f"(1-on/{n})"
        if motion in ("pan_left", "pan_right"):
            x = f"(iw-iw/zoom)*{t}"
        else:
            y = f"(ih-ih/zoom)*{t}"
    if drift:
        a, per = float(drift["amp"]), max(0.5, float(drift["period"])) * FPS
        z = f"({z})+{a}*(1+sin(2*PI*on/{per}))/2"          # breathing: never below the move's own zoom
        x = f"({x})+iw*{a / 3:.5f}*sin(2*PI*on/{per * 1.7:.1f})"   # a slow sway at a different rhythm
    return (f"{pre},zoompan=z='{z}':x='{x}':y='{y}':d=1:s={w}x{h}:fps={FPS},"
            f"setsar=1,scale=out_color_matrix=bt709:out_range=tv,format=yuv420p")       # a picture is converted with the HD colour matrix the file is labelled with


NATIVE_RATE = 44100
NATIVE_FADE = 0.04          # seconds: a clip's edges fade so a cut never clicks
NATIVE_TARGET_RMS = 0.08    # about -22 dBFS: every shot's speech is brought near the same loudness


def _has_audio(path: str) -> bool:
    err = subprocess.run([ffmpeg(), "-hide_banner", "-i", path], capture_output=True, text=True, creationflags=NO_WINDOW).stderr
    return "Audio:" in err


def native_track(d: str, clips: list[tuple[float, float, str]], duration: float, out: str) -> dict:
    """The soundtrack of a scene the video model spoke itself: each rendered shot's own sound, cut to its shot and laid at its start,
    brought to a common loudness, with silence where a shot has no sound (a still, a model without sound, a gap).
    clips: [(start_s, end_s, take_path)]. Returns {"path", "with_sound", "silent"}."""
    import numpy as np
    import soundfile as sf
    from .shotsound import _rms, decode
    total = int(round(duration * NATIVE_RATE))
    track = np.zeros(total, dtype=np.float32)
    used = 0
    for a, b, src in clips:
        if not _has_audio(src):
            continue
        x = decode(src, 1)[:, 0]                  # mono; a file that cannot be read gives nothing and the shot stays silent
        i0, i1 = int(round(a * NATIVE_RATE)), min(total, int(round(b * NATIVE_RATE)))
        x = x[: max(0, i1 - i0)].copy()
        if len(x) < 2 or _rms(x) < 0.003:       # nothing audible: leave the shot silent
            continue
        x *= min(3.0, max(0.4, NATIVE_TARGET_RMS / _rms(x)))
        n = min(len(x) // 2, int(NATIVE_FADE * NATIVE_RATE))
        if n:
            ramp = np.linspace(0, 1, n, dtype=np.float32)
            x[:n] *= ramp
            x[-n:] *= ramp[::-1]
        track[i0:i0 + len(x)] += x
        used += 1
    peak = float(np.max(np.abs(track))) if total else 0.0
    if peak > 0.95:
        track *= 0.95 / peak
    sf.write(out, np.stack([track, track], axis=1), NATIVE_RATE, subtype="PCM_16")
    return {"path": out, "with_sound": used, "silent": len(clips) - used}


def build(d: str, preset_key: str, window: tuple[float, float] | None = None) -> dict:
    """The film. `window` (seconds, start and end): only that part, drawn with its layers, captions and the sound for it (a preview)."""
    preset = PRESETS[preset_key]
    w, h = preset["w"], preset["h"]
    project = _read(os.path.join(d, "project.json"), {})
    song_map = _read(os.path.join(d, "songmap.json"))
    plan_name = "directed" if os.path.exists(os.path.join(d, "directed.json")) else "production"
    plan = _read(os.path.join(d, f"{plan_name}.json"))
    if not song_map or not plan:
        raise SystemExit("This project needs a song map and a shot plan before it can be exported.")
    jobs = _read(os.path.join(d, "jobs.json"), {"jobs": []})["jobs"]
    from .library import chosen_take, shot_state
    state = shot_state(d)  # the approved take per shot; otherwise the latest finished take
    takes: dict[str, dict] = {}
    for sid in {j["shot_id"] for j in jobs}:
        t = chosen_take(d, sid, plan_name, jobs, state)
        if t:
            takes[sid] = t

    duration = song_map["duration"]
    total_frames = round(duration * FPS)
    shots = sorted(((sh, sc) for sc in plan["scenes"] for sh in sc["shots"]), key=lambda x: x[0]["start"])
    work = os.path.join(d, "cache", "export", preset_key)
    os.makedirs(work, exist_ok=True)

    # Timeline of segments in whole frames; gaps (if any) are filled with black.
    segments, cursor = [], 0
    for sh, sc in shots:
        f0, f1 = max(cursor, round(sh["start"] * FPS)), min(total_frames, round(sh["end"] * FPS))
        if f0 > cursor:
            segments.append(("gap", None, None, f0 - cursor))
        if f1 > f0:
            segments.append(("shot", sh, sc, f1 - f0))
        cursor = max(cursor, f1)
    if cursor < total_frames:
        segments.append(("gap", None, None, total_frames - cursor))

    base = 0                                   # in a preview: the frame the assembled pieces start at
    win = None
    if window:
        lo, hi = max(0.0, float(window[0])), min(float(duration), float(window[1]))
        if hi - lo < 0.5:
            raise SystemExit("A preview needs at least half a second of the film.")
        win = (lo, hi)
        fa, fb = round(lo * FPS), round(hi * FPS)
        kept, pos = [], 0
        for seg in segments:
            end = pos + seg[3]
            if end > fa and pos < fb:
                if not kept:
                    base = pos
                kept.append(seg)
            pos = end
        segments = kept
    transition_of = {sh["id"]: state.get(sh["id"], {}).get("transition", "cut") for sh, _ in shots}
    transition_len = {sh["id"]: state.get(sh["id"], {}).get("transition_s") for sh, _ in shots}
    shot_segs = [s for s in segments if s[0] == "shot"]
    next_of = {a[1]["id"]: b[1]["id"] for a, b in zip(shot_segs, shot_segs[1:])}
    vf_fill = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={FPS},format=yuv420p")
    # every part is labelled the same way (HD colour, studio range): parts labelled differently made players and ffmpeg re-set themselves where one met the next
    enc = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv", "-an"]
    parts, rendered = [], 0
    mix_items: list[dict] = []                            # each shot's take and where its shot sits on the film: its own sound is mixed from this (Sound layers)
    vo_items: list[dict] = []                             # where each shot sits on the film, for the person's own recordings (a shot with no picture yet still speaks)
    from .render import native_mode
    native = native_mode(d)
    for i, (kind, sh, sc, frames) in enumerate(segments):
        emit(event="progress", stage="assembling", progress=round(i / max(1, len(segments)) * 0.9, 3),
             detail=sh["id"] if sh else "gap")
        take = takes.get(sh["id"]) if sh else None
        src = os.path.join(d, take["output"]) if take else None
        if src and not os.path.exists(src):
            src = None
        tin = transition_of.get(sh["id"], "cut") if sh else "cut"
        tout = transition_of.get(next_of.get(sh["id"]), "cut") if sh else "cut"
        tin_s = transition_len.get(sh["id"]) if sh else None
        tout_s = transition_len.get(next_of.get(sh["id"])) if sh else None
        motion = take.get("motion") if take and take.get("media_kind") == "image" else None
        from .performance import drift_for
        drift = drift_for(project, sh) if motion is not None else None
        own_clip = bool(take and take.get("provider") == "own" and take.get("media_kind") != "image")
        from . import colormatch
        grade = colormatch.filter_for(d, sh["id"]) if sh else ""        # a colour correction for this shot (Colour match), applied here and never to the take itself
        key = _sha1(json.dumps([ENCODING, grade, kind, sh and sh["id"], src, src and os.path.getmtime(src), frames, w, h, tin, tout, tin_s, tout_s, motion, own_clip, drift, parts[-1] if tin not in ("cut", "black", "white") and parts else None,
                                       sh and (sh.get("visual_prompt") or sh.get("beats"))], default=str).encode()).hexdigest()[:12]
        out = os.path.join(work, f"{i:04d}_{key}.mp4")
        if not os.path.exists(out):
            fades = _fades(tin, tout, frames, tin_s, tout_s)
            if src and take.get("media_kind") == "image":
                _run(["-loop", "1", "-framerate", str(FPS), "-i", src, "-vf", ken_burns(motion, frames, w, h, drift) + (f",{grade}" if grade else "") + fades,
                      "-frames:v", str(frames), *enc, out + ".tmp.mp4"])
            elif src:
                loop = ["-stream_loop", "-1"] if own_clip else []   # your own short clip repeats to fill the shot
                hold = "" if own_clip else ",tpad=stop_mode=clone:stop=-1"   # a take shorter than its shot holds its last frame
                _run([*loop, "-i", src, "-vf", vf_fill + (f",{grade}" if grade else "") + hold + fades, "-frames:v", str(frames), *enc, out + ".tmp.mp4"])
            else:
                img = out + ".png"
                if sh:
                    slate(img, w, h, sh, sc)
                else:
                    from PIL import Image
                    Image.new("RGB", (w, h), (0, 0, 0)).save(img)
                _run(["-loop", "1", "-framerate", str(FPS), "-i", img, "-vf", f"setsar=1,scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
                      "-frames:v", str(frames), *enc, out + ".tmp.mp4"])
                os.remove(img)
            if tin not in ("cut", "black", "white") and parts:   # dissolve, wipe, slide, whip or zoom from the end of the previous shot
                _enter(parts[-1], out + ".tmp.mp4", frames, enc, tin, tin_s, w, h)
            _check_frames(out + ".tmp.mp4", frames)
            os.replace(out + ".tmp.mp4", out)
        rendered += 1 if src else 0
        if sh:
            at = (base + sum(s[3] for s in segments[:i])) / FPS
            vo_items.append({"shot": sh["id"], "start": at, "end": at + frames / FPS})
        if src and sh and take.get("media_kind") != "image" and take.get("provider") != "own":
            start = (base + sum(s[3] for s in segments[:i])) / FPS      # the shot's place on the whole song, in whole frames like its picture
            mix_items.append({"shot": sh["id"], "start": start, "end": start + frames / FPS, "take": take})
        parts.append(out)

    emit(event="progress", stage="adding the song", progress=0.93)
    listfile = os.path.join(work, "concat.txt")
    with open(listfile, "w", encoding="utf-8") as f:
        for p in parts:
            f.write(f"file '{p.replace(os.sep, '/')}'\n")
    title = "".join(c for c in project.get("title", "FilmCrafter") if c.isalnum() or c in " -_").strip() or "FilmCrafter"
    stamp = time.strftime("%Y-%m-%d %H%M")
    status = "" if rendered == sum(1 for s in segments if s[0] == "shot") else " (draft)"
    out_path = os.path.join(d, "exports", f"{title} - {preset['label'].split(' ')[0]} - {stamp}{status}.mp4")
    if win:
        out_path = os.path.join(d, "exports", "previews", f"preview {win[0]:.1f}-{win[1]:.1f} s {stamp}.mp4")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    song = os.path.join(d, project.get("song", "song.wav"))
    sound = {}
    from . import shotsound   # the song plus any of the shots' own sound the person has switched on (a native-dialogue scene: only the shots' own sound)
    emit(event="progress", stage="mixing the sound", progress=0.92)
    mixed = shotsound.mix_track(d, mix_items, duration, None if native else song, os.path.join(work, "mix.wav"))
    if mixed:
        sound, song = mixed, mixed["path"]
    from . import voiceover                                   # the person's own recorded voices are laid on the film: they, not the video model's sound, are heard
    voiced = voiceover.mix_into(d, song, vo_items, duration, os.path.join(work, "voiced.wav"))
    if voiced:
        song = voiced["path"]
    planned = None
    try:                                                      # the planned soundscape (approved audio cues) is laid on top; a film with none is not touched
        from . import audiomix
        emit(event="progress", stage="adding the planned sound", progress=0.945)
        planned = audiomix.mix_cues(d, song, {it["shot"]: (it["start"], it["end"]) for it in vo_items}, duration, os.path.join(work, "cues.wav"))
        if planned and planned.get("path"):
            song = planned["path"]
    except SystemExit:
        raise
    except Exception as e:                                    # never lose the film over its extra sound: say so and carry on with the soundtrack as it was
        planned = {"error": f"The planned sound could not be mixed ({type(e).__name__}); the film was made without it."}
    length = sum(s[3] for s in segments) / FPS if win else duration
    _run(["-f", "concat", "-safe", "0", "-i", listfile] + (["-ss", f"{base / FPS:.4f}"] if win else []) + ["-i", song,
          "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k",
          "-t", f"{length:.3f}", "-movflags", "+faststart", out_path + ".part.mp4"])
    os.replace(out_path + ".part.mp4", out_path)
    from . import overlays   # on-screen text, drawn over the finished picture (one more pass, only when there is any)
    from . import captions
    if any(o.get("enabled", True) for o in overlays.load(d)) or captions.load(d)["enabled"]:
        emit(event="progress", stage="adding on-screen text", progress=0.97)
    ov = overlays.burn(d, out_path, w, h, FPS, length, origin=base / FPS)
    if win:                                    # cut the assembled pieces down to exactly the part asked for
        cut = out_path + ".cut.mp4"
        _run(["-ss", f"{win[0] - base / FPS:.4f}", "-i", out_path, "-t", f"{win[1] - win[0]:.3f}", "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p",
              "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", cut])
        os.replace(cut, out_path)
        emit(event="progress", stage="done", progress=1.0)
        return {"path": out_path, "preset": preset["label"], "width": w, "height": h, "fps": FPS, "duration": win[1] - win[0], "window": list(win), "shots": 0, "rendered": 0, "draft": True,
                "loudness": measure_loudness(out_path),
                "overlays": ov.get("count", 0), "captions": ov.get("captions", 0), "subtitles": None, "preview": True, **({"overlay_error": ov["error"]} if ov.get("error") else {})}
    srt = captions.write_srt(d, out_path)
    loud = measure_loudness(out_path)
    emit(event="progress", stage="done", progress=1.0)
    shot_count = sum(1 for s in segments if s[0] == "shot")
    return {"path": out_path, "preset": preset["label"], "width": w, "height": h, "fps": FPS,
            "duration": duration, "shots": shot_count, "rendered": rendered, "draft": rendered < shot_count, "loudness": loud,
            **({"voiceovers": voiced["recordings"]} if voiced else {}),
            **({"audio_cues": planned["cues"], "audio_cues_skipped": planned.get("skipped", []), "audio_ducked": planned.get("ducked", False)} if planned and planned.get("path") else {}),
            **({"audio_cues_error": planned["error"]} if planned and planned.get("error") else {}),
            **({"native_sound": sound["with_sound"], "native_silent": sound["silent"]} if sound and native else {}),
            **({"shot_sound": sound["with_sound"], "sound_layers": sound["layers"]} if sound and not native else {}),
            "overlays": ov.get("count", 0), "captions": ov.get("captions", 0), "subtitles": srt,
            **({"overlay_error": ov["error"]} if ov.get("error") else {})}


def measure_loudness(path: str) -> dict | None:
    """How loud the finished film sounds: integrated loudness (LUFS, the unit streaming sites level to), loudness range (LU) and true peak (dBFS).
    None when the film has no sound or it is silent."""
    import re
    p = subprocess.run([ffmpeg(), "-hide_banner", "-nostats", "-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True, creationflags=NO_WINDOW)
    tail = p.stderr.split("Summary:")[-1] if "Summary:" in p.stderr else ""
    num = lambda label, unit: (lambda m: float(m.group(1)) if m else None)(re.search(label + r":\s+(-?[\d.]+|-inf)\s+" + unit, tail))
    i, lra, peak = num("I", "LUFS"), num("LRA", "LU"), num("Peak", "dBFS")
    if i is None or i < -69:                                  # -70 is what the meter reads for silence
        return None
    return {"lufs": round(i, 1), "range_lu": round(lra, 1) if lra is not None else None, "true_peak_db": round(peak, 1) if peak is not None else None}


def _check_frames(path: str, want: int) -> None:
    """Guard against off-by-one-frame drift, which would accumulate into lost sync."""
    p = subprocess.run([ffmpeg(), "-hide_banner", "-i", path, "-map", "0:v:0", "-c", "copy", "-f", "null", "-"],
                       capture_output=True, text=True, creationflags=NO_WINDOW)
    import re
    m = re.findall(r"frame=\s*(\d+)", p.stderr)
    got = int(m[-1]) if m else want
    if got != want:
        raise RuntimeError(f"Segment has {got} frames, expected {want}.")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="filmcrafter-export")
    p.add_argument("project")
    p.add_argument("--preset", choices=list(PRESETS), default="youtube")
    p.add_argument("--window", help="start,end in seconds: export only that part (a preview)")
    a = p.parse_args(argv)
    try:
        win = tuple(float(x) for x in a.window.split(",")) if a.window else None
        if win and len(win) != 2:
            raise SystemExit("Give the preview as start,end in seconds.")
        emit(event="result", data=build(a.project, "preview" if win and a.preset == "youtube" else a.preset, win))
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=f"{type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
