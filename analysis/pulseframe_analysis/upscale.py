"""Sharper, larger pictures and videos: Topaz, Recraft and others, through Kie (first choice) or fal.

Two things can be upscaled:
  * a shot's approved keyframe (a picture): the upscaled picture becomes the approved keyframe, the original is kept, and `revert` brings it back. Takes already made from the old keyframe
    are not marked out of date: it is the same picture, only sharper.
  * a finished take (a video): the upscaled file is added as a new take of the shot and chosen for export; `revert` chooses the take it came from again.

The tool's own inputs are read from its published schema (render.manifest), so the right field gets the file and the right factor gets the size, whatever each tool calls them.
Nothing is sent without being asked for, and each run is written to upscales.json the moment the provider accepts it, so a paid run is never lost if the app closes: `resume` picks it up.

  python -m pulseframe_analysis.upscale tools|status|resume|revert|run <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid

from . import render as R

# (id, provider, model, media, label, blurb). Kie first: it is the preferred provider. A tool is only offered when its provider's key is set.
TOOLS = [
    ("kie-topaz-image", "kie", "topaz/image-upscale", "image", "Topaz · picture", "Topaz Gigapixel quality: the usual first choice for faces and detail. 2× or 4×."),
    ("kie-recraft-image", "kie", "recraft/crisp-upscale", "image", "Recraft · crisp", "Clean, crisp edges; good for illustration and 3D renders."),
    ("kie-topaz-video", "kie", "topaz/video-upscale", "video", "Topaz · video", "Topaz Video AI quality for a finished take. 2× or 4×."),
    ("fal-topaz-image", "fal", "fal-ai/topaz/upscale/image", "image", "Topaz · picture (fal)", "Topaz on fal.ai."),
    ("fal-clarity-image", "fal", "fal-ai/clarity-upscaler", "image", "Clarity · picture (fal)", "Adds fine detail while it enlarges: closest to Magnific's look."),
    ("fal-seedvr-image", "fal", "fal-ai/seedvr/upscale/image", "image", "SeedVR · picture (fal)", "Faithful restoration; keeps what is there."),
    ("fal-recraft-image", "fal", "fal-ai/recraft/upscale/crisp", "image", "Recraft · crisp (fal)", "Recraft on fal.ai."),
    ("fal-topaz-video", "fal", "fal-ai/topaz/upscale/video", "video", "Topaz · video (fal)", "Topaz on fal.ai."),
    ("fal-seedvr-video", "fal", "fal-ai/seedvr/upscale/video", "video", "SeedVR · video (fal)", "Restoration for a finished take."),
]
KEY_ENV = {"kie": "KIE_KEY", "fal": "FAL_KEY"}
FACTORS = (2, 4)
POLL_S = 4.0
GIVE_UP_S = 25 * 60
FACTOR_NAME = re.compile(r"^(upscale_factor|scale_factor|upscaling_factor|scale|factor|upscale)$", re.I)
MEDIA_NAME = {"image": re.compile(r"^(image_url|image|input_image|input_image_url|image_urls|url)$", re.I), "video": re.compile(r"^(video_url|video|input_video|input_video_url|url)$", re.I)}


def emit(**kw) -> None:
    R.emit(**kw)


def _path(d: str) -> str:
    return os.path.join(d, "upscales.json")


def load(d: str) -> list[dict]:
    data = R._read(_path(d), []) or []
    return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []


def _save(d: str, items: list[dict]) -> None:
    R._write(_path(d), items)


def tool(tool_id: str) -> dict:
    t = next((x for x in TOOLS if x[0] == tool_id), None)
    if not t:
        raise SystemExit("Choose one of the upscalers in the list.")
    return {"id": t[0], "provider": t[1], "model": t[2], "media": t[3], "label": t[4], "blurb": t[5]}


def tools(media: str | None = None) -> list[dict]:
    """The upscalers, with whether the key for each is set (the key reaches the engine only when asked for)."""
    out = []
    for t in TOOLS:
        if media and t[3] != media:
            continue
        out.append({"id": t[0], "provider": t[1], "model": t[2], "media": t[3], "label": t[4], "blurb": t[5], "ready": bool(os.environ.get(KEY_ENV[t[1]])), "factors": list(FACTORS)})
    return out


# ---------------------------------------------------------------- the request, read from the tool's own schema
def build_payload(man: dict, media: str, url: str, factor: int) -> dict:
    """The tool's request: the file in the field that takes it, the factor in the field that takes a size, anything else required set to the tool's own default."""
    fields = {f["name"]: f for f in man["inputs"]}
    target = next((f for f in man["inputs"] if MEDIA_NAME[media].match(f["name"]) and f.get("type") in ("string", "array")), None) \
        or next((f for f in man["inputs"] if f.get("required") and f.get("type") in ("string", "array") and re.search(media + r"|url", f["name"], re.I)), None)
    if not target:
        raise SystemExit(f"{man.get('title') or man.get('model')} has no input for a {media}, so it can't be used here.")
    payload: dict = {target["name"]: [url] if target.get("type") == "array" else url}
    fac = next((f for f in man["inputs"] if FACTOR_NAME.match(f["name"])), None)
    if fac:
        payload[fac["name"]] = _pick_factor(fac, factor)
    for f in man["inputs"]:                                   # anything else it requires: its own default
        if f["name"] not in payload and f.get("required"):
            if f.get("default") is not None:
                payload[f["name"]] = f["default"]
            elif f.get("enum"):
                payload[f["name"]] = f["enum"][0]
    return {k: v for k, v in payload.items() if v is not None and k in fields}


def _pick_factor(f: dict, factor: int):
    enum = f.get("enum")
    typ = f.get("type")
    if enum:
        def num(v):
            try:
                return float(str(v).lower().replace("x", ""))
            except ValueError:
                return None
        scored = [(abs(n - factor), i, v) for i, v in enumerate(enum) if (n := num(v)) is not None and n >= 1]
        if scored:
            return min(scored)[2]
        return enum[0]
    lo, hi = f.get("minimum"), f.get("maximum")
    v = float(factor)
    if lo is not None:
        v = max(v, float(lo))
    if hi is not None:
        v = min(v, float(hi))
    return int(v) if typ == "integer" else (v if typ == "number" else str(int(v)))


# ---------------------------------------------------------------- sources
def _keyframe_ref(d: str, plan_name: str, shot: str) -> str | None:
    return ((R._read(os.path.join(d, "keyframes.json"), {}) or {}).get(plan_name) or {}).get(shot) or None


def _local(d: str, ref: str) -> str:
    rel = ref[len(R.PROJECT_MEDIA):] if ref.startswith(R.PROJECT_MEDIA) else ref
    path = os.path.normpath(os.path.join(d, rel))
    if not path.startswith(os.path.normpath(d) + os.sep) and path != os.path.normpath(d):
        raise SystemExit("That file is not inside the project.")
    if not os.path.isfile(path):
        raise SystemExit("That picture or video isn't in the project any more.")
    return path


def _plan_name(d: str) -> str:
    return R._load_plan(d)[0]


def start(d: str, tool_id: str, kind: str, shot: str | None = None, job: str | None = None, factor: int = 2, provider=None) -> dict:
    """Send one picture or video to an upscaler. Returns the saved run (state 'submitted'); `finish` waits for it."""
    t = tool(tool_id)
    if kind not in ("keyframe", "take") or t["media"] != ("image" if kind == "keyframe" else "video"):
        raise SystemExit(f"{t['label']} upscales {'pictures' if t['media'] == 'image' else 'videos'}: choose {'a keyframe' if t['media'] == 'image' else 'a take'} to match.")
    factor = int(factor) if str(factor).isdigit() and int(factor) in FACTORS else 2
    plan_name = _plan_name(d)
    if kind == "keyframe":
        if not shot:
            raise SystemExit("Choose a shot.")
        ref = _keyframe_ref(d, plan_name, str(shot))
        if not ref:
            raise SystemExit(f"{shot} has no approved keyframe to upscale.")
        src_path, src_id = _local(d, ref), ref
    else:
        store = R.Store(d)
        src = next((j for j in store.jobs if j.get("id") == job and j.get("state") == "ready" and j.get("output") and (j.get("kind", "video") != "image")), None)
        if not src:
            raise SystemExit("Choose a finished take to upscale.")
        shot, src_path, src_id = src["shot_id"], _local(d, src["output"]), src["id"]
    man = R.manifest(t["provider"], t["model"])
    p = provider or R.PROVIDERS[t["provider"]]()
    url = R._upload_cached(d, p, src_path)
    payload = build_payload(man, t["media"], url, factor)
    problems = R.validate_request(man, payload)
    if problems:
        raise SystemExit(f"Not sent (nothing was charged). {man['title']}: " + "; ".join(problems) + ".")
    run = {"id": uuid.uuid4().hex[:10], "tool": t["id"], "provider": t["provider"], "model": man["model"], "kind": kind, "shot": shot, "plan": plan_name, "source": src_id,
           "factor": factor, "state": "queued", "created": int(time.time()), "task": None, "meta": None, "output": None, "error": None, "cost": None}
    items = load(d)
    items.append(run)
    _save(d, items)
    emit(event="progress", stage=f"sending {shot} to {t['label']}")
    try:
        sub = p.submit(man["model"], payload)
    except R.RequestProblem as e:
        run.update(state="failed", error=str(e))
        _save(d, items)
        raise SystemExit(str(e))
    run.update(state="submitted", task=sub.pop("id"), meta=sub, submitted=int(time.time()))
    _save(d, items)
    return run


def _update(d: str, run: dict, **kw) -> None:
    items = load(d)
    for it in items:
        if it.get("id") == run["id"]:
            it.update(kw)
    run.update(kw)
    _save(d, items)


def finish(d: str, run: dict, provider=None, wait: bool = True, poll_s: float = POLL_S) -> dict:
    """Wait for the provider, download the result and put it where it belongs. With wait=False, look once."""
    p = provider or R.PROVIDERS[run["provider"]]()
    began = time.time()
    while True:
        res = p.poll(run["model"], run["task"], run.get("meta"))
        if res["state"] == "failed":
            _update(d, run, state="failed", error=R.describe_error(res.get("error") or "The upscale failed."))
            return run
        if res["state"] == "done":
            break
        emit(event="progress", stage=f"upscaling {run['shot']}", detail=res.get("detail"))
        if not wait or time.time() - began > GIVE_UP_S:
            return run
        time.sleep(poll_s)
    out = _download(d, run, res, p)
    if run["kind"] == "keyframe":
        _use_keyframe(d, run, out)
    else:
        _add_take(d, run, out, res)
    _update(d, run, state="ready", output=os.path.relpath(out, d).replace(os.sep, "/"), cost=res.get("cost"), cost_unit=res.get("cost_unit"), finished=int(time.time()))
    return run


def _download(d: str, run: dict, res: dict, p) -> str:
    import requests
    url = res.get("url") or ""
    ext = os.path.splitext(url.split("?")[0])[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm"):
        ext = ".png" if run["kind"] == "keyframe" else ".mp4"
    out_dir = os.path.join(d, "generations")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{re.sub(r'[^A-Za-z0-9._-]+', '_', str(run['shot']))}__up{run['factor']}x_{run['id']}{ext}")
    emit(event="progress", stage=f"downloading the upscaled {run['shot']}")
    if url.startswith("file:"):
        import shutil
        shutil.copyfile(url[5:], out)
    else:
        with requests.get(url, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(out + ".part", "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        os.replace(out + ".part", out)
    if run["kind"] == "keyframe":
        from .refgen import verify_picture
        try:
            verify_picture(out)
        except Exception:
            os.remove(out)
            raise SystemExit("The upscaler sent back something that isn't a picture. It may still have been billed: check your provider dashboard.")
    return out


def _use_keyframe(d: str, run: dict, out: str) -> None:
    """The upscaled picture becomes the approved keyframe. Takes made from the old one are the same picture, so they are not marked out of date."""
    path = os.path.join(d, "keyframes.json")
    data = R._read(path, {}) or {}
    new = R.PROJECT_MEDIA + os.path.relpath(out, d).replace(os.sep, "/")
    plan = data.setdefault(run["plan"], {})
    plan[run["shot"]] = new
    R._write(path, data)
    store = R.Store(d)
    for j in store.jobs:
        if j.get("shot_id") == run["shot"] and j.get("keyframe_ref") == run["source"]:
            store.update(j, keyframe_ref=new)


def _add_take(d: str, run: dict, out: str, res: dict) -> None:
    """The upscaled video is a new take of the shot, chosen for export; the take it came from is kept and can be chosen again."""
    store = R.Store(d)
    src = next((j for j in store.jobs if j.get("id") == run["source"]), {})
    job = {"id": uuid.uuid4().hex[:12], "shot_id": run["shot"], "plan": run["plan"], "source_shots": src.get("source_shots", []), "shot_start": src.get("shot_start"), "shot_end": src.get("shot_end"),
           "provider": run["provider"], "model": run["model"], "kind": "video", "tool": "upscale", "upscaled_from": run["source"], "source_job": run["source"], "overrides": {}, "fix_notes": [],
           "look": src.get("look"), "state": "ready", "provider_job_id": run["task"], "attempts": 1, "created": int(time.time()), "updated": int(time.time()), "output": os.path.relpath(out, d).replace(os.sep, "/"),
           "error": None, "cost": res.get("cost"), "cost_unit": res.get("cost_unit"), "finished": int(time.time()), "review": {"reviewed": True, "status": "good", "accepted": True, "summary": "Upscaled from a take you chose."}}
    store.jobs.append(job)
    store.save()
    from .library import approve
    approve(d, run["shot"], job["id"])
    run["job"] = job["id"]


def run_one(d: str, tool_id: str, kind: str, shot: str | None = None, job: str | None = None, factor: int = 2, provider=None, poll_s: float = POLL_S) -> dict:
    run = start(d, tool_id, kind, shot, job, factor, provider)
    return finish(d, run, provider, True, poll_s)


def resume(d: str, provider=None) -> dict:
    """Look once at every upscale that was sent and not finished (the app was closed, say) and finish the ones that are done."""
    done, waiting, failed = 0, 0, 0
    for run in load(d):
        if run.get("state") not in ("submitted",):
            continue
        try:
            r = finish(d, run, provider, False)
        except SystemExit:
            failed += 1
            continue
        done += r["state"] == "ready"
        waiting += r["state"] == "submitted"
        failed += r["state"] == "failed"
    return {"finished": done, "waiting": waiting, "failed": failed, "runs": load(d)[-20:]}


def revert(d: str, shot: str, kind: str) -> dict:
    """Back to the picture or take that was upscaled."""
    runs = [r for r in load(d) if r.get("shot") == shot and r.get("kind") == kind and r.get("state") == "ready"]
    if not runs:
        raise SystemExit("There is no upscale of this shot to undo.")
    last = runs[-1]
    if kind == "keyframe":
        path = os.path.join(d, "keyframes.json")
        data = R._read(path, {}) or {}
        (data.setdefault(last["plan"], {}))[shot] = last["source"]
        R._write(path, data)
    else:
        from .library import approve
        approve(d, shot, last["source"])
    items = load(d)
    for it in items:
        if it.get("id") == last["id"]:
            it["state"] = "undone"
    _save(d, items)
    return {"shot": shot, "kind": kind, "restored": last["source"]}


def status(d: str, shot: str | None = None) -> dict:
    runs = [r for r in load(d) if not shot or r.get("shot") == shot]
    return {"runs": runs[-30:], "upscaled_keyframes": sorted({r["shot"] for r in load(d) if r.get("kind") == "keyframe" and r.get("state") == "ready"})}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="pulseframe-upscale")
    ap.add_argument("action", choices=["tools", "status", "resume", "revert", "run"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "tools":
            res = {"tools": tools(x.get("media"))}
        elif a.action == "status":
            res = status(a.project, x.get("shot"))
        elif a.action == "resume":
            res = resume(a.project)
        elif a.action == "revert":
            res = revert(a.project, str(x["shot"]), str(x["kind"]))
        else:
            res = run_one(a.project, str(x["tool"]), str(x["kind"]), x.get("shot"), x.get("job"), x.get("factor", 2))
        print(json.dumps({"event": "result", "data": res}, ensure_ascii=False), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except Exception as e:
        print(json.dumps({"event": "error", "message": R.describe_error(e) if hasattr(R, "describe_error") else f"{type(e).__name__}: {e}"}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
