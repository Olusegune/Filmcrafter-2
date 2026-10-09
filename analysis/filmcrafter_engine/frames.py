"""Start and end frames for every shot.

A video model that takes both a first and a last frame animates *between* them: the filmmaker decides exactly where a
shot starts and where it lands. Each shot has:

  start  its approved keyframe (Select & review), or the last frame of the previous shot's take ("continue",
         see continuity.chain)
  end    none | own (an end still made for this shot, an image you bring, or one of its stills)
              | next (the next shot's start frame, so this shot flows into the next one with no visible cut)

Models differ. Where a model can't take an end frame but the same family has a start+end version on the same
provider, a shot with an end frame is rendered on that version (shown, and priced, before anything is sent). Where
nothing in the family can, the end frame is not sent and the app says so up front; it never silently pretends.

  python -m filmcrafter_engine.frames <get|set|support|options|choose|use_image> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time

from .shothistory import tracked

PROJECT = "project:"

# Same family, same provider, a version that takes a last frame. Checked against the providers' own schemas.
END_VERSIONS = {
    ("fal", "fal-ai/kling-video/v3/turbo/pro/image-to-video"): "fal-ai/kling-video/v3/pro/image-to-video",
    ("fal", "fal-ai/veo3.1/fast/image-to-video"): "fal-ai/veo3.1/fast/first-last-frame-to-video",
    ("fal", "fal-ai/veo3.1/image-to-video"): "fal-ai/veo3.1/first-last-frame-to-video",
    ("fal", "bytedance/seedance-2.0/reference-to-video"): "bytedance/seedance-2.0/image-to-video",
    ("fal", "bytedance/seedance-2.0/fast/reference-to-video"): "bytedance/seedance-2.0/fast/image-to-video",
    ("fal", "fal-ai/minimax/hailuo-2.3/standard/image-to-video"): "fal-ai/minimax/hailuo-02/standard/image-to-video",
    ("fal", "fal-ai/minimax/hailuo-02-fast/image-to-video"): "fal-ai/minimax/hailuo-02/standard/image-to-video",
    ("fal", "fal-ai/pixverse/v5.5/image-to-video"): "fal-ai/pixverse/v5.5/transition",
}
# The schema says yes, but the provider refuses or ignores it in practice (until a real render proves otherwise).
NO_END_IN_PRACTICE: set[tuple[str, str]] = set()   # (Kie's Seedance 2 family was listed here; its own documentation describes first + last frame as a mode of its own, so it is now sent.
# What Kie refuses is reference pictures NEXT TO the first frame, which render.exclusive_inputs removes.)
# Proven with a real render that landed on its end frame (see docs/END_FRAMES.md). Others are offered, flagged as untested.
PROVEN_END: set[tuple[str, str]] = {
    ("kie", "hailuo/02-image-to-video-standard"),   # 2026-10-01: last frame matched the end frame (diff 1.9 vs 21 to the start)
    ("fal", "fal-ai/wan/v2.2-a14b/image-to-video/turbo"),          # 2026-10-01: 3.3 vs 19.8
    ("fal", "fal-ai/minimax/hailuo-02/standard/image-to-video"),   # 2026-10-01: via the automatic switch from Hailuo 2.3; 2.3 vs 21.3
    ("fal", "fal-ai/vidu/q3/image-to-video/turbo"),                # 2026-10-01: 0.8 vs 20.7
}


def is_proven(provider: str, model: str) -> bool:
    """Proven by the built-in list or by you (proof.py)."""
    from .proof import is_proven as _p
    return _p(provider, model)


END_MODES = ("none", "own", "next")
START_MODES = ("keyframe", "previous")


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data) -> None:
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _plan(d: str) -> tuple[str, dict]:
    from .library import _plan as lp
    return lp(d)


def _order(plan: dict) -> list[str]:
    """Every shot in film order (chaining crosses scene boundaries: the video is one continuous timeline)."""
    return [s["id"] for s in sorted((s for sc in plan.get("scenes", []) for s in sc["shots"]), key=lambda s: s["start"])]


def _shot_state(d: str) -> dict:
    return _read(os.path.join(d, "shots.json"), {}) or {}


def _exists(d: str, ref: str | None) -> str | None:
    if isinstance(ref, str) and ref.startswith(PROJECT) and os.path.exists(os.path.join(d, ref[len(PROJECT):])):
        return ref
    return None


def _continues(d: str, shot_id: str) -> bool:
    """True when this shot starts from the previous shot's last frame (continuity.chain)."""
    from .continuity import load
    return bool((load(d)["shots"].get(shot_id) or {}).get("continuous"))


def hands_on(d: str, shot_id: str) -> bool:
    """True when the shot after this one picks up where it ends: this shot lands on the next one's start (end mode "next"), or the next shot continues from its last frame."""
    _, plan = _plan(d)
    order = _order(plan)
    if shot_id not in order:
        return False
    if _shot_state(d).get(shot_id, {}).get("end_mode") == "next":
        return True
    i = order.index(shot_id)
    return i + 1 < len(order) and _continues(d, order[i + 1])


def _end_store(d: str) -> dict:
    return _read(os.path.join(d, "endframes.json"), {}) or {}


# ---------------------------------------------------------------- what a shot uses

def start_ref(d: str, plan_name: str, shot_id: str) -> str | None:
    """The shot's first frame: its approved keyframe (which `continue` also writes). `project:` ref or None."""
    kf = (_read(os.path.join(d, "keyframes.json"), {}) or {}).get(plan_name, {})
    return _exists(d, kf.get(shot_id))


def end_ref(d: str, plan_name: str, plan: dict, shot_id: str) -> str | None:
    """The shot's last frame as the video should land on it, or None."""
    st = _shot_state(d).get(shot_id, {})
    mode = st.get("end_mode", "none")
    if mode == "own":
        return _exists(d, (_end_store(d).get(plan_name) or {}).get(shot_id))
    if mode == "next":
        order = _order(plan)
        i = order.index(shot_id) if shot_id in order else -1
        if 0 <= i < len(order) - 1 and not _continues(d, order[i + 1]):   # never circular: see set_()
            return start_ref(d, plan_name, order[i + 1])
    return None


def get(d: str, shot_ids: list[str] | None = None) -> dict:
    plan_name, plan = _plan(d)
    order = _order(plan)
    st = _shot_state(d)
    out = {}
    for sid in shot_ids or order:
        s = st.get(sid, {})
        i = order.index(sid) if sid in order else -1
        nxt = order[i + 1] if 0 <= i < len(order) - 1 else None
        out[sid] = {"start": start_ref(d, plan_name, sid), "start_mode": "previous" if _continues(d, sid) else "keyframe",
                    "end": end_ref(d, plan_name, plan, sid), "end_mode": s.get("end_mode", "none"),
                    "end_state": s.get("end_state", ""), "next": nxt, "prev": order[i - 1] if i > 0 else None,
                    "next_has_start": bool(nxt and start_ref(d, plan_name, nxt))}
    return out


@tracked("Change end frame", lambda d, shot_id, *a, **k: [shot_id])
def set_(d: str, shot_id: str, data: dict) -> dict:
    """Change a shot's end mode / end description. Locked shots can't change. Nothing is ever deleted."""
    from .library import set_shot, shot_state
    if shot_state(d).get(shot_id, {}).get("locked"):
        raise SystemExit(f"{shot_id} is locked. Unlock it to change its frames.")
    _, plan = _plan(d)
    order = _order(plan)
    if shot_id not in order:
        raise SystemExit(f"Shot {shot_id} not found.")
    kw = {}
    if "end_mode" in data:
        mode = data["end_mode"]
        if mode not in END_MODES:
            raise SystemExit("End frame: choose none, own or next.")
        if mode == "next" and order.index(shot_id) == len(order) - 1:
            raise SystemExit("This is the last shot; there's no next shot to flow into.")
        if mode == "next" and _continues(d, order[order.index(shot_id) + 1]):
            raise SystemExit(f"{order[order.index(shot_id) + 1]} already continues from this shot's last frame, "
                             "so this shot can't also end on it. Use one or the other.")
        kw["end_mode"] = mode
    if "end_state" in data:
        kw["end_state"] = str(data["end_state"] or "")[:600]
    if kw:
        set_shot(d, shot_id, **kw)
    return get(d, [shot_id])[shot_id]


@tracked("Change start frame", lambda d, shot_id, *a, **k: [shot_id])
def set_start(d: str, shot_id: str, mode: str) -> dict:
    """keyframe: the shot starts on its approved keyframe. previous: on the last frame of the previous shot's take (free)."""
    from .continuity import chain, set_shot as cset
    from .library import shot_state
    if mode not in START_MODES:
        raise SystemExit("Start frame: choose keyframe or previous.")
    if shot_state(d).get(shot_id, {}).get("locked"):
        raise SystemExit(f"{shot_id} is locked. Unlock it to change its frames.")
    if mode == "previous":
        _, plan = _plan(d)
        order = _order(plan)
        i = order.index(shot_id) if shot_id in order else -1
        if i > 0 and _shot_state(d).get(order[i - 1], {}).get("end_mode") == "next":
            raise SystemExit(f"{order[i - 1]} is set to end on this shot's start, so this shot can't also start from its "
                             "last frame. Use one or the other.")
        chain(d, shot_id)
    else:
        cset(d, shot_id, {"continuous": False})
    return get(d, [shot_id])[shot_id]


@tracked("Flow shots together", lambda d, shot_ids=(), *a, **k: list(shot_ids or []))
def chain_shots(d: str, shot_ids: list[str]) -> dict:
    """Flow each selected shot into the next one (end = next shot's start). The last shot of the film is skipped."""
    _, plan = _plan(d)
    order = _order(plan)
    done, skipped = [], []
    for sid in shot_ids:
        try:
            set_(d, sid, {"end_mode": "next"})
            done.append(sid)
        except SystemExit as e:
            skipped.append({"shot": sid, "reason": str(e)})
    return {"chained": done, "skipped": skipped, "order": [s for s in order if s in shot_ids]}


# ---------------------------------------------------------------- end stills

def options(d: str, shot_ids: list[str]) -> dict:
    """End-frame stills made for these shots (image jobs marked frame=end), newest first, plus the chosen one."""
    plan_name, _ = _plan(d)
    jobs = _read(os.path.join(d, "jobs.json"), {"jobs": []})["jobs"]
    store = _end_store(d).get(plan_name) or {}
    out = {}
    for sid in shot_ids:
        mine = [j for j in jobs if j["shot_id"] == sid and j["plan"] == plan_name and j.get("kind") == "image" and j.get("frame") == "end"]
        opts = [{"job": j["id"], "image": j["output"], "model": j["model"], "created": j["created"], "rejected": bool(j.get("rejected"))}
                for j in mine if j["state"] == "ready" and j.get("output") and os.path.exists(os.path.join(d, j["output"]))]
        chosen = (_exists(d, store.get(sid)) or "")[len(PROJECT):] or None
        out[sid] = {"chosen": chosen, "options": sorted(opts, key=lambda o: -o["created"]),
                    "active": sum(1 for j in mine if j["state"] in ("queued", "submitting", "submitted"))}
    return out


def _store_end(d: str, shot_id: str, rel: str) -> dict:
    from .library import set_shot, shot_state
    if shot_state(d).get(shot_id, {}).get("locked"):
        raise SystemExit(f"{shot_id} is locked. Unlock it to change its frames.")
    plan_name, _ = _plan(d)
    path = os.path.join(d, "endframes.json")
    data = _end_store(d)
    data.setdefault(plan_name, {})[shot_id] = PROJECT + rel
    _write(path, data)
    set_shot(d, shot_id, end_mode="own")
    return get(d, [shot_id])[shot_id]


@tracked("Choose end frame", lambda d, shot_id, *a, **k: [shot_id])
def choose(d: str, shot_id: str, job_id: str) -> dict:
    """Use one of this shot's end stills (or any of its finished stills) as its end frame."""
    jobs = _read(os.path.join(d, "jobs.json"), {"jobs": []})["jobs"]
    j = next((x for x in jobs if x["id"] == job_id and x["shot_id"] == shot_id and x.get("kind") == "image" and x["state"] == "ready"), None)
    if not j or not j.get("output"):
        raise SystemExit("Choose a finished still of this shot.")
    return _store_end(d, shot_id, j["output"])


def _known_shot(d: str, shot_id: str) -> str:
    """The shot id itself when the plan has such a shot (it goes into file names, so nothing else is allowed), else a plain refusal."""
    _, plan = _plan(d)
    if shot_id not in _order(plan):
        raise SystemExit("That shot isn't in the plan.")
    return shot_id


@tracked("Use own end picture", lambda d, shot_id, *a, **k: [shot_id])
def use_image(d: str, shot_id: str, path: str) -> dict:
    """Bring your own end frame: the image is copied into the project (the original is never touched)."""
    _known_shot(d, shot_id)
    if not os.path.isfile(path):
        raise SystemExit("That image can't be found.")
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise SystemExit("Use a PNG, JPG or WebP image.")
    os.makedirs(os.path.join(d, "media"), exist_ok=True)
    rel = f"media/{shot_id}_end_{int(time.time())}{ext}"
    shutil.copy2(path, os.path.join(d, rel))
    return _store_end(d, shot_id, rel)


def end_still_prompt(shot: dict, end_state: str) -> dict:
    """The shot as an image prompt for its LAST frame (the keyframe prompt describes the first)."""
    how = (end_state or "").strip() or "the moment the shot's action completes"
    body = shot.get("visual_prompt") or " ".join(shot.get("beats", [])) or shot.get("description", "")
    return {**shot, "visual_prompt": f"The LAST frame of this shot, where the action lands: {how}. Same shot, same moment's "
                                     f"characters, wardrobe, set, lens and light as its first frame. Shot: {body}"}


# ---------------------------------------------------------------- which model can do it

def model_for(provider: str, model: str, wants_end: bool) -> dict:
    """{provider, model, swapped, supports_end} for a shot that does (or doesn't) have an end frame."""
    from .render import manifest
    if not wants_end:
        return {"provider": provider, "model": model, "swapped": False, "supports_end": None}
    try:
        if manifest(provider, model)["caps"].get("last_frame") and (provider, model) not in NO_END_IN_PRACTICE:
            return {"provider": provider, "model": model, "swapped": False, "supports_end": True,
                    "proven": is_proven(provider, model)}
    except BaseException:
        pass
    alt = END_VERSIONS.get((provider, model))
    if alt:
        try:
            if manifest(provider, alt)["caps"].get("last_frame"):
                return {"provider": provider, "model": alt, "swapped": True, "supports_end": True, "proven": is_proven(provider, alt)}
        except BaseException:
            pass
    return {"provider": provider, "model": model, "swapped": False, "supports_end": False}


def support(d: str, provider: str, model: str, shot_ids: list[str]) -> dict:
    """For the render about to happen: which shots land on an end frame, on which model, and which can't."""
    plan_name, plan = _plan(d)
    out = {"shots": {}, "unsupported": [], "swapped": []}
    for sid in shot_ids:
        end = end_ref(d, plan_name, plan, sid)
        m = model_for(provider, model, bool(end))
        out["shots"][sid] = {**m, "end": end}
        if end and not m["supports_end"]:
            out["unsupported"].append(sid)
        if m["swapped"]:
            out["swapped"].append(sid)
    try:
        from .render import manifest
        out["title"] = manifest(provider, model)["title"]
    except BaseException:
        out["title"] = model
    return out


@tracked("Use own start picture", lambda d, shot_id, *a, **k: [shot_id])
def use_start_image(d: str, shot_id: str, path: str) -> dict:
    """Bring your own start frame (a Midjourney picture, a photograph, a painting): copied into the project and made this shot's keyframe. The original is never touched."""
    from .library import shot_state
    _known_shot(d, shot_id)
    if shot_state(d).get(shot_id, {}).get("locked"):
        raise SystemExit(f"{shot_id} is locked. Unlock it to change its frames.")
    if not os.path.isfile(path):
        raise SystemExit("That image can't be found.")
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise SystemExit("Use a PNG, JPG or WebP image.")
    plan_name, _ = _plan(d)
    os.makedirs(os.path.join(d, "media"), exist_ok=True)
    rel = f"media/{shot_id}_start_{int(time.time())}{ext}"
    shutil.copy2(path, os.path.join(d, rel))
    kp = os.path.join(d, "keyframes.json")
    kf = _read(kp, {}) or {}
    kf.setdefault(plan_name, {})[shot_id] = PROJECT + rel
    _write(kp, kf)
    from .continuity import set_shot as cset
    cset(d, shot_id, {"continuous": False})
    return get(d, [shot_id])[shot_id]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-frames")
    ap.add_argument("action", choices=["get", "set", "start", "chain", "support", "options", "choose", "use_image", "use_start", "extend_info"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    d = a.project
    try:
        if a.action == "get":
            res = get(d, x.get("shots"))
        elif a.action == "set":
            res = set_(d, x["shot"], x)
        elif a.action == "start":
            res = set_start(d, x["shot"], x["mode"])
        elif a.action == "chain":
            res = chain_shots(d, x.get("shots") or [])
        elif a.action == "support":
            res = support(d, x["provider"], x["model"], x.get("shots") or [])
        elif a.action == "options":
            res = options(d, x.get("shots") or [])
        elif a.action == "choose":
            res = choose(d, x["shot"], x["job"])
        elif a.action == "use_start":
            res = use_start_image(d, x["shot"], x["path"])
        elif a.action == "extend_info":
            from .extend import info
            res = info(d, x["shot"])
        else:
            res = use_image(d, x["shot"], x["path"])
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
