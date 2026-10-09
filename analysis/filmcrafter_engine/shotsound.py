"""Sound layers for each shot: the sound a video model made inside a take, kept apart from the picture so it can be switched on, turned down or deleted
per shot without rendering the video again.

A shot has up to four sound layers:
  song   the recorded song under this shot (always there; turned down automatically while the take's own sound plays, unless you set a level)
  all    everything the video model made for this take (voice, effects and music together) - until the take is split
  voice  the voices in the take             \\ after a split (Demucs, on this computer, free); they replace `all`
  other  the sound effects and music        /

Nothing here changes a take: the layers are applied only when the film is put together. By default a take's own sound is *not* in the film (the song is the
soundtrack), except in a native-dialogue scene, where each take's whole sound is (the way it always was).

  python -m filmcrafter_engine.shotsound <get|set|delete|restore|reset|split|overview> <project> --data '{"shot": "S01-02", ...}'
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

SOUND = "sound.json"
RATE = 44100
FADE = 0.04                 # seconds: a clip's edges fade so a cut never clicks
TARGET_RMS = 0.08           # about -22 dBFS: a shot's own sound is brought near the same loudness as the others
SILENT_RMS = 0.003          # below this a take has no audible sound
DUCK = 0.4                  # the song's level under a shot whose own sound is playing, when no level has been chosen
LABELS = {"song": "Song", "all": "Sound from the video model", "voice": "Voices", "other": "Sound effects and music"}
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


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


def _write(path: str, data) -> None:
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    for i in range(40):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == 39:
                raise
            time.sleep(0.05)


def _ffmpeg() -> str:
    from .export import ffmpeg
    return ffmpeg()


def _num(v, default, lo: float, hi: float):
    """A number from a file that anyone could have edited (or a package could carry): finite and inside lo..hi, else the default."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return default if x != x or x in (float("inf"), float("-inf")) else min(hi, max(lo, x))


def load(d: str) -> dict:
    """The saved settings, with anything of the wrong shape dropped: this file travels with a project, so it is not trusted."""
    s = _read(os.path.join(d, SOUND), {})
    s = s if isinstance(s, dict) else {}
    shots = {str(k): v for k, v in (s.get("shots") if isinstance(s.get("shots"), dict) else {}).items() if isinstance(v, dict)}
    probe = {str(k): v for k, v in (s.get("probe") if isinstance(s.get("probe"), dict) else {}).items() if isinstance(v, dict)}
    return {"shots": shots, "probe": probe}


def save(d: str, s: dict) -> None:
    _write(os.path.join(d, SOUND), s)


# ---------------------------------------------------------------- the take a shot uses, and what is in it

def take_for(d: str, shot_id: str) -> dict | None:
    """The take the film uses for this shot (the approved one, else the latest), or None."""
    from .library import chosen_take
    plan_name = "directed" if os.path.exists(os.path.join(d, "directed.json")) else "production"
    jobs = (_read(os.path.join(d, "jobs.json"), {"jobs": []}) or {"jobs": []})["jobs"]
    return chosen_take(d, shot_id, plan_name, jobs)


def _is_video(t: dict | None) -> bool:
    return bool(t and t.get("output") and t.get("media_kind") != "image" and t.get("provider") != "own"
                and str(t["output"]).lower().endswith((".mp4", ".mov", ".webm", ".m4v")))


def take_key(d: str, take: dict) -> str:
    p = os.path.join(d, take["output"])
    try:
        st = os.stat(p)
        stamp = [st.st_mtime_ns, st.st_size]
    except OSError:
        stamp = [0, 0]
    return hashlib.sha1(json.dumps([take["output"], stamp]).encode(), usedforsecurity=False).hexdigest()[:12]


def _is_mono(path: str) -> bool:
    import re
    err = subprocess.run([_ffmpeg(), "-hide_banner", "-i", path], capture_output=True, text=True, creationflags=NO_WINDOW).stderr
    return bool(re.search(r"Audio:[^\n]*,\s*(mono|1 channels)\b", err))


def decode(path: str, channels: int = 2, start: float | None = None, seconds: float | None = None):
    """An audio or video file's sound as float32 samples at RATE, shaped (n, channels). Empty when it has none. `start` and `seconds` read only that part.
    A mono source is copied into both channels at the same level (ffmpeg's own upmix would take 3 dB off it)."""
    import numpy as np
    cut = (["-ss", f"{start:.3f}"] if start else []) + (["-t", f"{seconds:.3f}"] if seconds else [])
    pan = ["-af", "pan=stereo|c0=c0|c1=c0"] if channels == 2 and _is_mono(path) else []
    r = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", *cut, "-i", path, "-vn", *pan, "-f", "f32le", "-ac", str(channels), "-ar", str(RATE), "-"],
                       capture_output=True, creationflags=NO_WINDOW)
    if r.returncode:
        return np.zeros((0, channels), dtype=np.float32)
    x = np.frombuffer(r.stdout, dtype=np.float32)
    return x[: len(x) // channels * channels].reshape(-1, channels).copy()


def _rms(x) -> float:
    import numpy as np
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


def probe(d: str, take: dict, s: dict | None = None) -> dict:
    """{'has_audio', 'rms', 'seconds'} for a take's own sound, remembered by file."""
    s = s if s is not None else load(d)
    key = take_key(d, take)
    hit = s["probe"].get(key)
    if hit and isinstance(hit.get("has_audio"), bool):
        return {"has_audio": hit["has_audio"], "rms": _num(hit.get("rms"), 0.0, 0.0, 10.0), "seconds": _num(hit.get("seconds"), 0.0, 0.0, 1e6)}
    x = decode(os.path.join(d, take["output"]), 1)
    rms = _rms(x)
    res = {"has_audio": bool(len(x)) and rms >= SILENT_RMS, "rms": round(rms, 5), "seconds": round(len(x) / RATE, 2)}
    s["probe"][key] = res
    return res


# ---------------------------------------------------------------- layer settings

def _default(layer: str, native: bool) -> dict:
    if layer == "song":
        return {"on": True, "gain": None, "removed": False}
    return {"on": bool(native) if layer == "all" else True, "gain": 1.0, "removed": False}


def _entry(d: str, s: dict, shot_id: str, take: dict | None) -> dict:
    """The saved settings for a shot, but only if they were made for the take it uses now (another take starts fresh)."""
    e = s["shots"].get(shot_id) or {}
    if take and e.get("take") == take_key(d, take):
        return e
    return {}


def _layer(e: dict, layer: str, native: bool) -> dict:
    out = _default(layer, native)
    saved = (e.get("layers") if isinstance(e.get("layers"), dict) else {}).get(layer)
    if isinstance(saved, dict):
        if "on" in saved:
            out["on"] = saved["on"] is True
        if "removed" in saved:
            out["removed"] = saved["removed"] is True
        if "gain" in saved:
            out["gain"] = None if saved["gain"] is None and layer == "song" else _num(saved["gain"], out["gain"], 0.0, 2.0)
    return out


def _split_files(d: str, e: dict) -> dict | None:
    """The separated sounds of this shot's take, only if both are files inside this project's own sound cache (a project from elsewhere cannot point at other files)."""
    sp = e.get("split")
    if not isinstance(sp, dict):
        return None
    base = os.path.realpath(os.path.join(d, "cache", "sound"))
    for k in ("voice", "other"):
        rel = sp.get(k)
        if not isinstance(rel, str) or not rel:
            return None
        p = os.path.realpath(os.path.join(d, rel))
        try:
            if os.path.commonpath([base, p]) != base or p == base or not os.path.isfile(p):
                return None
        except ValueError:                      # another drive
            return None
    return {"voice": sp["voice"], "other": sp["other"]}


def _native(d: str) -> bool:
    from .render import native_mode
    return native_mode(d)


def effective(d: str, shot_id: str, take: dict | None, native: bool, s: dict | None = None) -> dict:
    """What the film will use for this shot: {'split': {...}|None, 'layers': {id: {on, gain, removed}}, 'sources': [(layer, path)], 'song_gain': float}."""
    s = s if s is not None else load(d)
    e = _entry(d, s, shot_id, take)
    sp = _split_files(d, e)
    ids = ["voice", "other"] if sp else ["all"]
    layers = {i: _layer(e, i, native) for i in ids}
    live = _is_video(take) and (s["probe"].get(take_key(d, take), {}).get("has_audio", True) if take else False)
    sources = []
    if live:
        for i in ids:
            L = layers[i]
            if L["on"] and not L["removed"] and (L["gain"] is None or L["gain"] > 0):
                sources.append((i, os.path.join(d, sp[i]) if sp else os.path.join(d, take["output"])))
    song = _layer(e, "song", native)
    if song["removed"] or not song["on"]:
        song_gain = 0.0
    elif song["gain"] is not None:
        song_gain = float(song["gain"])
    else:
        song_gain = DUCK if sources and not native else 1.0
    layers["song"] = song
    return {"split": sp, "layers": layers, "sources": sources, "song_gain": song_gain}


def customised(d: str) -> bool:
    """True when any shot has settings that change the mix from what it would be untouched (so the export has to mix)."""
    return bool(load(d)["shots"])


# ---------------------------------------------------------------- what the app shows

def get(d: str, shot_id: str) -> dict:
    s = load(d)
    take = take_for(d, shot_id)
    native = _native(d)
    res: dict = {"shot": shot_id, "native": native, "take": None, "has_audio": False, "silent": False, "split": False, "changed": False, "layers": []}
    if not take:
        res["note"] = "This shot has no video take yet."
        return res
    res["take"] = {"id": take["id"], "model": take.get("model"), "output": take["output"]}
    if not _is_video(take):
        res["note"] = "This take is a picture or one of your own clips, so it has no sound from a video model."
        return res
    p = probe(d, take, s)
    save(d, s)
    res["has_audio"] = p["has_audio"]
    res["silent"] = not p["has_audio"]
    eff = effective(d, shot_id, take, native, s)
    res["split"] = bool(eff["split"])
    res["changed"] = bool(_entry(d, s, shot_id, take).get("layers"))          # something has been set for this take (so there is something to go back from)
    order = ["song"] + (["voice", "other"] if eff["split"] else ["all"])
    for i in order:
        L = eff["layers"][i]
        row = {"id": i, "label": LABELS[i], "on": bool(L["on"]) and not L["removed"], "gain": L["gain"], "removed": bool(L["removed"])}
        if i == "song":
            row["effective_gain"] = eff["song_gain"]
            row["auto"] = L["gain"] is None
        elif not p["has_audio"]:
            row["note"] = "This take has no audible sound."
        res["layers"].append(row)
    return res


def _db(x) -> float | None:
    import numpy as np
    r = _rms(x)
    return round(20 * float(np.log10(r)), 1) if r > 1e-5 else None


def _span(d: str, shot_id: str) -> tuple[float, float] | None:
    for name in ("directed", "production"):
        plan = _read(os.path.join(d, f"{name}.json"))
        if plan:
            for sc in plan.get("scenes", []):
                for sh in sc.get("shots", []):
                    if sh.get("id") == shot_id:
                        return float(sh["start"]), float(sh["end"])
            return None
    return None


def levels(d: str, shot_id: str) -> dict:
    """How loud each layer will be in the film under this shot, in dB below full scale (RMS over the shot), and the mix of them all with its peak.
    Free and quick: it reads only this shot's part of the song and of the take. A layer that is off or silent is None."""
    import numpy as np
    take = take_for(d, shot_id)
    span = _span(d, shot_id)
    out: dict = {"shot": shot_id, "layers": {}, "mix_db": None, "peak_db": None, "seconds": None}
    if not take or not span or span[1] <= span[0]:
        return out
    start, end = span
    n = int(round((end - start) * RATE))
    out["seconds"] = round(end - start, 2)
    s = load(d)
    native = _native(d)
    eff = effective(d, shot_id, take, native, s)
    mix = np.zeros((n, 2), dtype=np.float32)
    project = _read(os.path.join(d, "project.json"), {}) or {}
    song = os.path.join(d, project.get("song", "song.wav"))
    if not native and os.path.exists(song):
        x = decode(song, 2, start, end - start)[:n] * np.float32(eff["song_gain"])
        mix[: len(x)] += x
        out["layers"]["song"] = _db(x)
    elif not native:
        out["layers"]["song"] = None
    else:
        out["layers"]["song"] = None
    if _is_video(take):
        whole = decode(os.path.join(d, take["output"]), 1)[:n]
        r = _rms(whole)
        level = min(3.0, max(0.4, TARGET_RMS / r)) if r >= SILENT_RMS else 0.0
        ids = ["voice", "other"] if eff["split"] else ["all"]
        for lid in ids:
            L = eff["layers"][lid]
            live = any(src[0] == lid for src in eff["sources"])
            if not live or not level:
                out["layers"][lid] = None
                continue
            path = os.path.join(d, eff["split"][lid]) if eff["split"] else os.path.join(d, take["output"])
            x = decode(path, 2)[:n] * np.float32(level * (1.0 if L["gain"] is None else float(L["gain"])))
            mix[: len(x)] += x
            out["layers"][lid] = _db(x)
    out["mix_db"] = _db(mix)
    out["peak_db"] = round(20 * float(np.log10(max(1e-5, float(np.max(np.abs(mix)))))), 1) if n else None
    return out


def overview(d: str) -> dict:
    """Shots whose sound has been changed: {shot_id: True}. Cheap: reads one small file."""
    return {sid: True for sid, e in load(d)["shots"].items() if e.get("layers")}


# ---------------------------------------------------------------- changes

def _touch(d: str, shot_id: str) -> tuple[dict, dict, dict]:
    take = take_for(d, shot_id)
    if not take:
        raise SystemExit("This shot has no video take yet.")
    s = load(d)
    key = take_key(d, take)
    e = s["shots"].get(shot_id)
    if not e or e.get("take") != key:
        e = {"take": key, "layers": {}}
        s["shots"][shot_id] = e
    e.setdefault("layers", {})
    return s, e, take


def _check_layer(layer: str, e: dict, d: str) -> None:
    if layer not in LABELS:
        raise SystemExit("Unknown sound layer.")
    if layer in ("voice", "other") and not _split_files(d, e):
        raise SystemExit("Split this take's sound first.")
    if layer == "all" and _split_files(d, e):
        raise SystemExit("This take's sound is split into voices and effects; use those layers.")


def set_layer(d: str, shot_id: str, layer: str, on: bool | None = None, gain: float | None | str = "keep") -> dict:
    s, e, take = _touch(d, shot_id)
    _check_layer(layer, e, d)
    cur = _layer(e, layer, _native(d))
    if on is not None:
        cur["on"] = bool(on)
        if on:
            cur["removed"] = False
    if gain != "keep":
        if gain is None and layer != "song":
            raise SystemExit("Only the song's level can be automatic.")
        cur["gain"] = None if gain is None else min(2.0, max(0.0, float(gain)))
    e["layers"][layer] = cur
    save(d, s)
    return get(d, shot_id)


def delete_layer(d: str, shot_id: str, layer: str) -> dict:
    """Take a layer out of this shot's sound. Reversible with `restore`; the take and the separated files are not touched."""
    s, e, take = _touch(d, shot_id)
    _check_layer(layer, e, d)
    cur = _layer(e, layer, _native(d))
    cur.update({"on": False, "removed": True})
    e["layers"][layer] = cur
    save(d, s)
    return get(d, shot_id)


def restore_layer(d: str, shot_id: str, layer: str) -> dict:
    s, e, take = _touch(d, shot_id)
    _check_layer(layer, e, d)
    cur = _layer(e, layer, _native(d))
    cur.update({"on": True, "removed": False})
    e["layers"][layer] = cur
    save(d, s)
    return get(d, shot_id)


def reset(d: str, shot_id: str) -> dict:
    s = load(d)
    s["shots"].pop(shot_id, None)
    save(d, s)
    return get(d, shot_id)


# ---------------------------------------------------------------- splitting a take's sound (Demucs, on this computer)

def _demucs(mix: str, out: str, device: str | None) -> None:
    cmd = [sys.executable, "-m", "demucs", "--two-stems", "vocals", "-n", "htdemucs", "-o", out, *(["-d", device] if device else []), mix]
    p = subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW)
    if p.returncode:
        tail = (p.stderr or "").strip().splitlines()[-1:] or ["no message"]
        if "No module named" in (p.stderr or ""):
            raise SystemExit("The sound separator (Demucs) is not installed in this copy of the engine.")
        raise RuntimeError(tail[0][:240])


def split(d: str, shot_id: str) -> dict:
    """Separate the voices from the sound effects and music in this shot's take. Free; takes seconds. Voices come out as 'Voices', everything else as
    'Sound effects and music' (Demucs is built for songs, so a loud effect can leave a trace in the voice layer)."""
    take = take_for(d, shot_id)
    if not take:
        raise SystemExit("This shot has no video take yet.")
    if not _is_video(take):
        raise SystemExit("Only a take from a video model has sound to split.")
    s = load(d)
    p = probe(d, take, s)
    if not p["has_audio"]:
        save(d, s)
        raise SystemExit("This take has no audible sound to split.")
    key = take_key(d, take)
    work = os.path.join(d, "cache", "sound", key)
    voice, other = os.path.join(work, "voice.wav"), os.path.join(work, "other.wav")
    if not (os.path.exists(voice) and os.path.exists(other)):
        os.makedirs(work, exist_ok=True)
        emit(event="progress", stage=f"separating the sound of {shot_id}", progress=0.1)
        mix = os.path.join(work, "mix.wav")
        r = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", os.path.join(d, take["output"]), "-vn", "-ac", "2", "-ar", str(RATE),
                            "-c:a", "pcm_s16le", mix], capture_output=True, text=True, creationflags=NO_WINDOW)
        if r.returncode:
            raise SystemExit("Couldn't read the sound of this take.")
        sep = os.path.join(work, "sep")
        try:
            _demucs(mix, sep, None)
        except RuntimeError:
            shutil.rmtree(sep, ignore_errors=True)
            emit(event="progress", stage="separating on the processor instead", progress=0.3)
            _demucs(mix, sep, "cpu")      # the graphics card could not do it (memory): the processor can, more slowly
        base = os.path.join(sep, "htdemucs", "mix")
        try:
            shutil.copyfile(os.path.join(base, "vocals.wav"), voice + f".{os.getpid()}.tmp")
            shutil.copyfile(os.path.join(base, "no_vocals.wav"), other + f".{os.getpid()}.tmp")
        except OSError:
            raise SystemExit("The separator finished but did not produce its files.")
        os.replace(voice + f".{os.getpid()}.tmp", voice)
        os.replace(other + f".{os.getpid()}.tmp", other)
        shutil.rmtree(sep, ignore_errors=True)
        try:
            os.remove(mix)
        except OSError:
            pass
    s, e, _ = _touch(d, shot_id)
    was_on = _layer(e, "all", _native(d))
    e["split"] = {"voice": os.path.relpath(voice, d).replace(os.sep, "/"), "other": os.path.relpath(other, d).replace(os.sep, "/")}
    # splitting means you want to hear and choose: both parts start on (unless the whole sound had been deleted)
    keep = not was_on["removed"]
    for i in ("voice", "other"):
        e["layers"][i] = {"on": keep, "gain": was_on["gain"] if was_on["gain"] is not None else 1.0, "removed": not keep}
    save(d, s)
    emit(event="progress", stage="done", progress=1.0)
    return get(d, shot_id)


# ---------------------------------------------------------------- the film's mix

def _fade(x, n: int):
    import numpy as np
    n = min(len(x) // 2, n)
    if n:
        ramp = np.linspace(0, 1, n, dtype=np.float32)[:, None]
        x[:n] *= ramp
        x[-n:] *= ramp[::-1]
    return x


def mix_track(d: str, items: list[dict], duration: float, song_path: str | None, out: str) -> dict | None:
    """The film's soundtrack, mixed from the song and each shot's own sound layers.
    items: [{'shot': id, 'start': s, 'end': s, 'take': job}] for the shots drawn into the film (start/end are where each sits on the whole song).
    song_path: the recorded song, or None when the soundtrack is only the shots' own sound (a native-dialogue scene).
    Returns None when nothing here differs from just laying the song under the film (the caller then uses the song file as it is);
    otherwise writes a WAV to `out` and returns {'path', 'with_sound', 'silent', 'layers'}."""
    import numpy as np
    import soundfile as sf
    s = load(d)
    native = song_path is None
    plan = []
    for it in items:
        take = it.get("take")
        if take and _is_video(take) and take_key(d, take) not in s["probe"]:
            probe(d, take, s)
        plan.append((it, effective(d, it["shot"], take, _native(d), s)))
    save(d, s)
    custom = any(e["sources"] for _, e in plan if not native) or any(abs(e["song_gain"] - 1.0) > 1e-6 for _, e in plan if not native)
    if not native and not custom:
        return None
    total = int(round(duration * RATE))
    if native:
        track = np.zeros((total, 2), dtype=np.float32)
    else:
        song = decode(song_path, 2)[:total]
        track = np.zeros((total, 2), dtype=np.float32)
        track[: len(song)] = song
        env = np.ones(total, dtype=np.float32)
        for it, e in plan:
            if abs(e["song_gain"] - 1.0) > 1e-6:
                env[max(0, int(round(it["start"] * RATE))): min(total, int(round(it["end"] * RATE)))] = e["song_gain"]
        w = int(0.06 * RATE)                         # level changes glide over a few hundredths of a second instead of clicking
        if w > 1 and np.any(env != 1.0):
            pad = np.pad(env, (w // 2, w - w // 2 - 1), mode="edge")
            env = np.convolve(pad, np.ones(w, dtype=np.float32) / w, mode="valid")[:total]
        track *= env[:, None]
    used = silent = 0
    layers = 0
    for it, e in plan:
        if not e["sources"]:
            silent += 1
            continue
        i0, i1 = int(round(it["start"] * RATE)), min(total, int(round(it["end"] * RATE)))
        if i1 <= i0:
            continue
        whole = decode(os.path.join(d, it["take"]["output"]), 1)[: i1 - i0]
        r = _rms(whole)
        if r < SILENT_RMS:
            silent += 1
            continue
        level = min(3.0, max(0.4, TARGET_RMS / r))      # one level for the whole take, so voices and effects keep their balance
        for lid, path in e["sources"]:
            x = decode(path, 2)[: i1 - i0].copy()
            if len(x) < 2:
                continue
            g = e["layers"][lid]["gain"]
            x *= level * (1.0 if g is None else float(g))
            x = _fade(x, int(FADE * RATE))
            track[i0:i0 + len(x)] += x
            layers += 1
        used += 1
    peak = float(np.max(np.abs(track))) if total else 0.0
    if peak > 0.95:
        track *= 0.95 / peak
    sf.write(out, track, RATE, subtype="PCM_16")
    return {"path": out, "with_sound": used, "silent": silent, "layers": layers}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-shotsound")
    ap.add_argument("action", choices=["get", "set", "delete", "restore", "reset", "split", "overview", "levels"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "overview":
            res = overview(a.project)
        else:
            sid = str(x.get("shot") or "")
            if not sid:
                raise SystemExit("Say which shot.")
            if a.action == "get":
                res = get(a.project, sid)
            elif a.action == "set":
                res = set_layer(a.project, sid, str(x.get("layer", "")), x.get("on"), x["gain"] if "gain" in x else "keep")
            elif a.action == "delete":
                res = delete_layer(a.project, sid, str(x.get("layer", "")))
            elif a.action == "restore":
                res = restore_layer(a.project, sid, str(x.get("layer", "")))
            elif a.action == "reset":
                res = reset(a.project, sid)
            elif a.action == "levels":
                res = levels(a.project, sid)
            else:
                res = split(a.project, sid)
        emit(event="result", data=res)
        return 0
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
