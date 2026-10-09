"""Extend a take: when a shot is longer than the video model can make in one go (the rest of the shot would hold the last frame), render the missing seconds as a
continuation that starts on the take's last frame, and join the two into one longer take. The result is a new take like any other: Review checks it, the swap flow offers it,
and the old take is never touched.

  info(d, shot_id)     what the shot needs: take length, shot length, the shortfall, the model's longest clip, and advice (free)
  last_frame(d, take)  the take's final frame as a project picture (free)
  join(base, clip, out)  one video from the take followed by the new part (free)

Queueing goes through render.enqueue with the private overrides `_extend_of` (the take) and `_extend_seconds`; see render.py.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time

NOWIN = 0x08000000 if sys.platform == "win32" else 0
MIN_EXTEND_S = 2.0               # a shortfall smaller than this is not worth a paid render: the last frame holds
CHANGE_WORDS = re.compile(r"\b(into|becomes?|turns? into|transforms?|morphs?|dissolves? into|fades? into|disappears? into|melts? into|ages?|grows? (?:up|old))\b", re.I)


def video_behind(jobs: list[dict], take: dict) -> dict:
    """A lip-synced take was made by a model that cannot draw: the video to extend is the one under it."""
    cur = take
    for _ in range(6):
        if cur.get("kind") != "lipsync" or not cur.get("source_job"):
            break
        nxt = next((x for x in jobs if x["id"] == cur["source_job"]), None)
        if not nxt:
            break
        cur = nxt
    return cur


def last_frame(d: str, take: dict) -> str:
    """The take's last frame as `project:media/…png` (what a video model takes as its first frame)."""
    from .export import ffmpeg
    from .safe import file_part
    src = os.path.join(d, take["output"])
    if not os.path.exists(src):
        raise SystemExit("The take to extend is missing from the project.")
    os.makedirs(os.path.join(d, "media"), exist_ok=True)
    rel = f"media/{file_part(take['shot_id'])}_end_of_{file_part(take['id'])}.png"
    out = os.path.join(d, rel)
    if not os.path.exists(out):
        from .export import last_frame_png
        if not last_frame_png(src, out):
            raise SystemExit("Couldn't read the last frame of that take.")
    return "project:" + rel


def join(base: str, clip: str, out: str) -> str:
    """The take followed by the new part, as one video. The new part is brought to the take's size and frame rate, and its first frame (the take's last) is dropped so nothing repeats."""
    from .editor_export import probe
    from .export import ffmpeg
    pb = probe(base)
    if not pb["video"]:
        raise SystemExit("The original take can't be read as a video.")
    w, h, fps = pb["w"] - pb["w"] % 2, pb["h"] - pb["h"] % 2, round(pb["fps"], 3)
    graph = (f"[0:v]fps={fps},scale={w}:{h},setsar=1,format=yuv420p[a];"
             f"[1:v]trim=start_frame=1,setpts=PTS-STARTPTS,fps={fps},scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[b];"
             f"[a][b]concat=n=2:v=1:a=0[v]")
    p = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", base, "-i", clip, "-filter_complex", graph, "-map", "[v]",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-movflags", "+faststart", out], capture_output=True, text=True, creationflags=NOWIN)
    if p.returncode or not os.path.exists(out):
        raise SystemExit("Couldn't join the new part to the take: " + (p.stderr or "ffmpeg failed").strip()[-240:])
    return out


def _duration_field(man: dict) -> dict | None:
    roles = man.get("roles") or {}
    name = roles.get("duration")
    return next((f for f in man.get("inputs", []) if f["name"] == name), None) if name else None


def clip_seconds(man: dict, want: float) -> float | None:
    """The clip length this model will really make for `want` seconds: the smallest it allows that covers it, never above its longest. None when the model has no length setting."""
    from .render import _duration_value
    f = _duration_field(man)
    if not f:
        return None
    v = _duration_value(f, max(0.5, want) - 0.5)
    try:
        return float(str(v).rstrip("s"))
    except (TypeError, ValueError):
        return None


def longest_clip(man: dict) -> float | None:
    f = _duration_field(man)
    if not f:
        return None
    from .render import _duration_value
    v = _duration_value(f, 10_000)
    try:
        return float(str(v).rstrip("s"))
    except (TypeError, ValueError):
        return None


def info(d: str, shot_id: str) -> dict:
    """What extending this shot would do, and whether it is worth it. Free."""
    from . import frames
    from .editor_export import probe
    from .library import chosen_take, shot_state
    from .render import _load_plan, _read, _shot, manifest
    plan_name, plan = _load_plan(d)
    shot, _scene = _shot(plan, shot_id)
    jobs = _read(os.path.join(d, "jobs.json"), {"jobs": []})["jobs"]
    take = chosen_take(d, shot_id, plan_name, jobs, shot_state(d))
    shot_s = round(float(shot["end"]) - float(shot["start"]), 2)
    out: dict = {"shot": shot_id, "shot_seconds": shot_s, "can_extend": False, "advice": []}
    end_set = bool(frames.end_ref(d, plan_name, plan, shot_id))
    text = " ".join(str(x) for x in (shot.get("visual_prompt"), shot.get("description"), *(shot.get("beats") or [])) if x)
    if CHANGE_WORDS.search(text) and not end_set:
        out["advice"].append("This shot changes who or what is on screen. Set an end frame (Frames, “where it lands”) with the changed look: a model that is shown where the shot must end completes the change, which extending alone will not.")
    if not take:
        out["reason"] = "This shot has no finished take yet."
        return out
    src = video_behind(jobs, take)
    if (src.get("kind") or "video") != "video" or not src.get("output"):
        out["reason"] = "This take can't be extended."
        return out
    pr = probe(os.path.join(d, take["output"]))
    take_s = round(pr["duration"], 2)
    man = manifest(src["provider"], src["model"])
    longest = longest_clip(man)
    short = round(shot_s - take_s, 2)
    out.update({"take": take["id"], "source_take": src["id"], "provider": src["provider"], "model": src["model"], "take_seconds": take_s,
                "short_seconds": max(0.0, short), "model_longest": longest, "lip_synced": take is not src})
    if longest is None:
        out["reason"] = "This model has no length setting, so it can't make a continuation."
    elif short < MIN_EXTEND_S:
        out["reason"] = f"The take already covers the shot (it is {take_s:g} s; the shot is {shot_s:g} s)."
    elif src["provider"] == "comfyui" and not man.get("caps", {}).get("first_frame", True):
        out["reason"] = "This local workflow doesn't take a start picture."
    else:
        add = clip_seconds(man, short)
        out.update({"can_extend": True, "suggest_seconds": add, "will_cover": round(take_s + (add or 0), 2), "estimate_usd": _estimate(d, plan, shot, _scene, src, man, add)})
        if add is not None and take_s + add < shot_s - 0.25:
            out["advice"].append(f"One continuation of {add:g} s (this model's longest) still leaves {round(shot_s - take_s - add, 1)} s short; extend again afterwards, or shorten the shot.")
        if take is not src:
            out["advice"].append("This take is lip-synced. The extension is made from its last frame; the joined take is lip-synced again afterwards.")
    return out


def _estimate(d: str, plan: dict, shot: dict, scene: dict | None, src: dict, man: dict, seconds: float | None) -> float | None:
    """What the continuation alone would cost, from the provider's price for a clip of that length (None when the provider doesn't say). Free."""
    if not seconds:
        return None
    try:
        from .render import _read, compile_request, estimate_payload
        project = _read(os.path.join(d, "project.json"), {})
        short = {**shot, "end": float(shot["start"]) + seconds}
        payload = compile_request(short, scene, plan, project, man, [])
        e = estimate_payload(src["provider"], src["model"], man, payload)
        return e.get("usd")
    except Exception:
        return None
