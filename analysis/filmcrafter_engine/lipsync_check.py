"""Lip-sync check: in shots where someone sings, does the mouth move with the vocal?

For each singing shot's take in use, frames are sampled while words are sung and, where the shot has one, during a
pause; the AI brain's vision model compares mouth shapes with what should be happening at each moment. One call
per shot (OpenAI costs a little; a local vision model is free). Results are stored on the take and appear in the
Production Supervisor, where a failing shot can get a lip-sync pass.

  python -m filmcrafter_engine.lipsync_check run <project> --data '{"shots": [...]}'   (default: every singing shot)
  python -m filmcrafter_engine.lipsync_check timing <project> --data '{"shots": [...]}'  (free, on this computer: is the take's sound the song's vocal, and is it in time?)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["verdict", "detail", "fix"],
    "properties": {"verdict": {"type": "string", "enum": ["in_sync", "off", "no_face", "unclear"]},
                   "detail": {"type": "string"}, "fix": {"type": "string"}},
}
SYSTEM = """You check lip-sync in frames from one shot of an animated music video.
Each frame is labelled with what the vocal is doing at that instant: a sung word (the mouth should be open or shaping it)
or a pause (the mouth should be closed or at rest). Judge only the singer's mouth.
- in_sync: the mouth matches the labels in most frames
- off: the mouth is closed while words are sung, or moving/open during pauses, in several frames
- no_face: the singer's mouth isn't visible (back of head, too small, hidden) so lip-sync doesn't matter
- unclear: you can't tell
Keep detail to one sentence naming the frames; fix is one instruction for a re-render (empty if in_sync)."""


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _frame(video: str, t: float) -> str | None:
    from .export import NO_WINDOW, ffmpeg
    out = os.path.join(tempfile.gettempdir(), f"pf_ls_{os.getpid()}_{int(t * 1000)}.jpg")
    p = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(0.0, t):.3f}", "-i", video,
                        "-frames:v", "1", "-vf", "scale=640:-2", out], capture_output=True, creationflags=NO_WINDOW)
    if p.returncode or not os.path.exists(out):
        return None
    with open(out, "rb") as f:
        b = base64.b64encode(f.read()).decode()
    os.remove(out)
    return b


def moments(shot: dict, lines: list[dict]) -> list[tuple[float, str]]:
    """(time inside the take, label): up to 3 sung moments and 1 pause."""
    s0, s1 = shot["start"], shot["end"]
    out = []
    for l in lines:
        a, b = max(s0, l["start"]), min(s1, l.get("end") or l["start"] + 1)
        if b - a > 0.25:
            words = l["text"].split()
            for k in (0.3, 0.7):
                if len([m for m in out if m[1] != "pause"]) < 3:
                    t = a + (b - a) * k
                    w = words[min(len(words) - 1, int(len(words) * (t - l["start"]) / max(0.01, (l.get("end") or t) - l["start"])))] if words else ""
                    out.append((round(t - s0, 2), f'sung word "{w}"'))
    sung = [(max(s0, l["start"]), min(s1, l.get("end") or l["start"])) for l in lines]
    t = s0 + 0.15
    while t < s1 - 0.15:   # the first gap of at least half a second
        if all(not (a - 0.1 <= t <= b + 0.1) for a, b in sung):
            out.append((round(t - s0, 2), "pause (no vocal)"))
            break
        t += 0.25
    return out


def check_shot(d: str, shot: dict, plan: dict, take: dict, client, model: str) -> dict:
    sm = _read(os.path.join(d, "songmap.json"), {}) or {}
    lines = [l for l in sm.get("lyrics", []) if l.get("start") is not None and l["start"] < shot["end"] and (l.get("end") or l["start"]) > shot["start"]]
    content = [{"type": "input_text", "text": f"Singer: {', '.join(shot.get('performers') or [])}. Frames in order:"}]
    n = 0
    for t, label in moments(shot, lines):
        b = _frame(os.path.join(d, take["output"]), t)
        if b:
            content += [{"type": "input_text", "text": f"At {t:.2f}s: {label}"},
                        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{b}"}]
            n += 1
    if n < 2:
        return {"verdict": "unclear", "detail": "Not enough frames to judge.", "fix": "", "frames": n}
    r = client.responses.create(model=model, input=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}],
                                text={"format": {"type": "json_schema", "name": "lipsync", "schema": SCHEMA, "strict": True}})
    out = json.loads(r.output_text)
    out.update({"frames": n, "model": model})
    return out


# ---------------------------------------------------------------- free timing check: is the sound in the take the song's vocal, in time with it?
RATE = 8000
HOP = 160                      # 20 ms envelope steps
MAX_LAG_S = 0.5


def _samples(path: str, start: float, seconds: float):
    """Mono float samples at RATE from `start` for `seconds` (empty if the file has no audio)."""
    import numpy as np
    from .export import NO_WINDOW, ffmpeg
    p = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0, start):.3f}", "-t", f"{seconds:.3f}", "-i", path, "-vn", "-f", "f32le", "-ac", "1", "-ar", str(RATE), "-"],
                       capture_output=True, creationflags=NO_WINDOW)
    return np.frombuffer(p.stdout, dtype=np.float32) if p.returncode == 0 else np.zeros(0, dtype=np.float32)


def _envelope(a):
    import numpy as np
    n = len(a) // HOP
    if n < 10:
        return np.zeros(0)
    e = np.sqrt(np.mean(np.square(a[: n * HOP].reshape(n, HOP)), axis=1))
    return e


def compare(ref, take) -> dict:
    """How well the take's loudness over time follows the vocal's, and by how much it is early or late. Pure: two sample arrays at RATE.
    lag_ms is positive when the take is LATE (its sound comes after the vocal)."""
    import numpy as np
    er, et = _envelope(ref), _envelope(take)
    if len(et) == 0 or float(np.max(et)) < 1e-4:
        return {"verdict": "no_audio", "detail": "This take has no sound of its own to compare."}
    if len(er) == 0 or float(np.max(er)) < 1e-4:
        return {"verdict": "no_vocal", "detail": "There is no vocal under this shot to compare with."}
    n = min(len(er), len(et))
    er, et = er[:n], et[:n]
    # loudness in decibels so a quiet word counts as much as a loud one; remove each one's average
    r = 20 * np.log10(er + 1e-4); t = 20 * np.log10(et + 1e-4)
    r = np.clip(r, r.max() - 40, None); t = np.clip(t, t.max() - 40, None)
    r -= r.mean(); t -= t.mean()
    if float(np.std(r)) < 1e-6 or float(np.std(t)) < 1e-6:
        return {"verdict": "no_vocal", "detail": "The sound is too even to compare."}
    maxlag = int(MAX_LAG_S * RATE / HOP)
    best, best_lag = -2.0, 0
    for lag in range(-maxlag, maxlag + 1):
        a, b = (r[: n - lag], t[lag:]) if lag >= 0 else (r[-lag:], t[: n + lag])
        if len(a) < 10:
            continue
        c = float(np.corrcoef(a, b)[0, 1])
        if c > best:
            best, best_lag = c, lag
    lag_ms = round(best_lag * HOP / RATE * 1000)
    out = {"correlation": round(best, 2), "lag_ms": lag_ms}
    if best >= 0.5 and abs(lag_ms) <= 80:
        out.update(verdict="in_time", detail="The take's sound follows the vocal and is in time with it.")
    elif best >= 0.5:
        out.update(verdict="late" if lag_ms > 0 else "early", detail=f"The take's sound follows the vocal but comes {abs(lag_ms)} ms {'late' if lag_ms > 0 else 'early'}.")
    elif best >= 0.3:
        out.update(verdict="loose", detail="The take's sound only loosely follows the vocal.")
    else:
        out.update(verdict="own_audio", detail="The take's sound does not follow the song's vocal: the model made its own, and the mouth follows that.")
    return out


def timing_shot(d: str, shot: dict, take: dict) -> dict:
    from .render import _vocal_stem, take_duration
    project = _read(os.path.join(d, "project.json"), {}) or {}
    video = os.path.join(d, take["output"])
    secs = min(take_duration(video) or (shot["end"] - shot["start"]), shot["end"] - shot["start"])
    ref_src = _vocal_stem(d) or os.path.join(d, project.get("song", "song.wav"))
    if not os.path.exists(ref_src):
        return {"verdict": "no_vocal", "detail": "The song file is missing."}
    res = compare(_samples(ref_src, shot["start"], secs), _samples(video, 0.0, secs))
    res["against"] = "vocal" if _vocal_stem(d) else "song"
    return res


def timing(d: str, shots: list[str] | None = None) -> dict:
    """Free and local: for each singing shot in use, how closely the sound in its take follows the song's vocal. No AI, nothing sent anywhere."""
    from .library import chosen_take, shot_state
    from .render import Store, _load_plan, singing
    plan_name, plan = _load_plan(d)
    store, state = Store(d), shot_state(d)
    rows = []
    for sc in plan.get("scenes", []):
        for sh in sc["shots"]:
            if shots and sh["id"] not in shots:
                continue
            t = chosen_take(d, sh["id"], plan_name, store.jobs, state)
            if t and t.get("media_kind") != "image" and singing(d, sh, plan):
                res = timing_shot(d, sh, t)
                j = next(x for x in store.jobs if x["id"] == t["id"])
                store.update(j, audio_timing=res)
                rows.append({"shot": sh["id"], **res})
    return {"checked": len(rows), "rows": rows,
            "note": "" if rows else "No shot in use shows someone singing."}


def run(d: str, shots: list[str] | None = None) -> dict:
    from .director import DEFAULT_MODEL, openai_error, resolve_model
    from .library import chosen_take, shot_state
    from .llm import client as brain
    from .render import Store, _load_plan, singing
    plan_name, plan = _load_plan(d)
    store = Store(d)
    state = shot_state(d)
    targets = []
    for sc in plan.get("scenes", []):
        for sh in sc["shots"]:
            if shots and sh["id"] not in shots:
                continue
            t = chosen_take(d, sh["id"], plan_name, store.jobs, state)
            if t and t.get("media_kind") != "image" and singing(d, sh, plan):
                targets.append((sh, t))
    if not targets:
        return {"checked": 0, "off": [], "errors": [], "note": "No shot in use shows someone singing."}
    c = brain()
    model = resolve_model(c, DEFAULT_MODEL, vision=True)
    off, errors, done = [], [], 0
    for i, (sh, t) in enumerate(targets):
        print(json.dumps({"event": "progress", "stage": f"checking lip-sync {sh['id']}", "progress": round(i / len(targets), 3)}), flush=True)
        try:
            res = check_shot(d, sh, plan, t, c, model)
        except Exception as e:
            errors.append(f"{sh['id']}: {openai_error(e)}")
            if len(errors) >= 2 and not done:
                break
            continue
        done += 1
        j = next(x for x in store.jobs if x["id"] == t["id"])
        store.update(j, lipsync_check=res)
        if res["verdict"] == "off":
            off.append(sh["id"])
    return {"checked": done, "of": len(targets), "off": off, "errors": errors, "model": model}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-lipsync-check")
    ap.add_argument("action", choices=["run", "count", "timing"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "count":   # free: how many shots would be checked (for the price line)
            from .library import chosen_take, shot_state
            from .render import Store, _load_plan, singing
            pn, plan = _load_plan(a.project)
            jobs, st = Store(a.project).jobs, shot_state(a.project)
            n = sum(1 for sc in plan.get("scenes", []) for sh in sc["shots"]
                    if (t := chosen_take(a.project, sh["id"], pn, jobs, st)) and t.get("media_kind") != "image" and singing(a.project, sh, plan))
            res = {"shots": n}
        elif a.action == "timing":
            res = timing(a.project, x.get("shots"))
        else:
            res = run(a.project, x.get("shots"))
        print(json.dumps({"event": "result", "data": res}), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except Exception as e:
        print(json.dumps({"event": "error", "message": f"{type(e).__name__}: {e}"}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
