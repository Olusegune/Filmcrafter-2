"""Overnight on ComfyUI: the whole video rendered while you sleep.

start()    queues a keyframe for every described shot without one: on ComfyUI (free), or in Hybrid mode on the cloud
           (cheap, and the model sees the character images). Cloud keyframes need confirming at their price first.
advance()  is called by the renderer whenever its queue empties: it approves the best new keyframes, queues a ComfyUI
           video for every shot that has a keyframe but no take, and when nothing is left, exports the video.
Videos always render on your own ComfyUI; the only possible cost is the confirmed Hybrid keyframes.

  python -m filmcrafter_engine.overnight <start|stop|status> <project>
"""
from __future__ import annotations

import json
import os
import sys
import time


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _set(d: str, **kw) -> dict:
    path = os.path.join(d, "project.json")
    p = _read(path, {})
    o = dict(p.get("overnight") or {})
    o.update(kw)
    p["overnight"] = o
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return o


def _flows() -> tuple[dict | None, dict | None]:
    from .routing import _comfy_flow
    return _comfy_flow("image"), _comfy_flow("video")


def status(d: str) -> dict:
    from .golden import status as gs
    img, vid = _flows()
    o = (_read(os.path.join(d, "project.json"), {}) or {}).get("overnight") or {}
    g = gs(d)
    src = _keyframe_source(d, img)
    return {**o, "comfy_image": (img or {}).get("title"), "comfy_video": (vid or {}).get("title"),
            "keyframes_from": (src or {}).get("provider"), "ready": bool(vid and src), "shots": g["total"], "with_video": len(g["video"])}


def _keyframe_source(d: str, img: dict | None) -> dict | None:
    """Where overnight keyframes come from: the cloud in Hybrid mode (cheap, sees the characters), else ComfyUI."""
    from .routing import pick, settings
    p = _read(os.path.join(d, "project.json"), {}) or {}
    if settings(p)["mode"] == "hybrid":
        k = pick(p, "image")
        return k if k.get("provider") else None
    return {"provider": "comfyui", "model": img["model"], "free": True} if img else None


def start(d: str, confirmed: bool = False) -> dict:
    from .golden import status as gs
    from .render import enqueue
    img, vid = _flows()
    src = _keyframe_source(d, img)
    if not (vid and src):
        raise SystemExit("Overnight needs ComfyUI running with a video workflow (and a keyframe source). Settings → ComfyUI → Find ComfyUI.")
    g = gs(d)
    todo = [s["id"] for s in g["shots"] if s["described"] and not s["locked"] and not s["keyframe"] and s["take"] == "none"]
    if todo and not src.get("free") and not confirmed:   # keyframes cost money in Hybrid: show the price first
        from .routing import batch_usd
        return {"needs_confirm": True, "keyframes": len(todo), "provider": src["provider"], "model": src["model"],
                "label": src.get("label"), "usd": batch_usd(d, todo, src["provider"], src["model"], "image"), **status(d)}
    made = enqueue(d, todo, src["provider"], src["model"], {}, [], kind="image") if todo else []
    _set(d, active=True, started=int(time.time()), finished=None, export=None, image=src["model"], video=vid["model"], log=[], video_tried=[])
    advanced = advance(d) if not made else False
    return {"keyframes_queued": len(made), "advanced": advanced, **status(d)}


def stop(d: str) -> dict:
    _set(d, active=False)
    return status(d)


def advance(d: str) -> bool:
    """Next overnight step once the queue is empty. True when new (free) work was queued."""
    from .golden import status as gs
    from .library import approve_keyframes, pending_keyframes
    from .render import ACTIVE, Store, enqueue
    o = (_read(os.path.join(d, "project.json"), {}) or {}).get("overnight") or {}
    if not o.get("active"):
        return False
    if any(j["state"] in ACTIVE for j in Store(d).jobs):
        return False
    if pending_keyframes(d):   # the best still of each shot (ones that passed the keyframe check first)
        approve_keyframes(d)
    g = gs(d)
    todo = [s["id"] for s in g["shots"] if s["keyframe"] and s["take"] == "none" and not s["locked"]]
    tried = set(o.get("video_tried") or [])
    todo = [t for t in todo if t not in tried]   # one attempt per shot overnight: a failure waits for you
    if todo:
        enqueue(d, todo, "comfyui", o["video"], {}, [], kind="video")
        _set(d, video_tried=sorted(tried | set(todo)))
        return True
    from .export import build
    p = _read(os.path.join(d, "project.json"), {})
    from .export import preset_for
    preset = preset_for(p.get("aspect_ratio"))
    try:
        out = build(d, preset)["path"]
    except Exception as e:   # the renders are safe; only the final cut failed
        out = None
        _set(d, error=f"The export failed: {e}")
    _set(d, active=False, finished=int(time.time()), export=out)
    return False


def main(argv: list[str]) -> int:
    try:
        res = start(argv[1], confirmed="--confirmed" in argv) if argv[0] == "start" else {"stop": stop, "status": status}[argv[0]](argv[1])
        print(json.dumps({"event": "result", "data": res}), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except Exception as e:
        print(json.dumps({"event": "error", "message": __import__("filmcrafter_engine.errtext", fromlist=["plain"]).plain(e)}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
