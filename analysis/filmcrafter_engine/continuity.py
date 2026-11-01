"""Continuity Director: keep shots of a scene consistent with each other.

Per scene it keeps blocking (who is screen-left or screen-right and which way they face, so the camera respects the
180-degree line and eyelines match), the wardrobe and the light. These go into every prompt of the scene. The previous
shot's approved keyframe is sent as a reference when making a keyframe, a shot can start from the last frame of the
shot before it, and a cross-shot review finds breaks (free rules, plus an optional AI look at the scene's frames).

Stored in continuity.json; the user's edits are never overwritten by the automatic defaults.

  python -m filmcrafter_engine.continuity <action> <project> --data '{...}'
  actions: get | set | derive | chain | check | ai_check
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

from . import safeio

SIDES = ("left", "center", "right")
FACING = ("left", "right", "camera", "away")


def _read(path, default=None):
    """Absent -> default. A damaged file is never mistaken for an absent one (see safeio): its bytes are kept and the last good copy is used, or the person is told."""
    return safeio.read_json(path, default)


def _write(path, data) -> None:
    safeio.write_json(path, data)


def _plan(d: str) -> tuple[str, dict]:
    name = "directed" if os.path.exists(os.path.join(d, "directed.json")) else "production"
    return name, _read(os.path.join(d, f"{name}.json"), {"scenes": []})


def load(d: str) -> dict:
    c = _read(os.path.join(d, "continuity.json"), {}) or {}
    c.setdefault("scenes", {})
    c.setdefault("shots", {})
    return c


def save(d: str, c: dict) -> dict:
    _write(os.path.join(d, "continuity.json"), c)
    return c


# ---------------------------------------------------------------- defaults from the plan

def _default_scene(sc: dict) -> dict:
    """Blocking from who appears first; wardrobe and light from the scene's first shots and notes."""
    order = []
    for sh in sc.get("shots", []):
        for n in sh.get("performers") or []:
            if n not in order:
                order.append(n)
    blocking = {}
    for i, n in enumerate(order):
        # the two leads face each other across the line; anyone else stays in the middle ground
        side = "left" if i == 0 else "right" if i == 1 else "center"
        blocking[n] = {"side": side, "facing": "right" if side == "left" else "left" if side == "right" else "camera"}
    first = lambda k: next((sh.get(k) for sh in sc.get("shots", []) if sh.get(k)), "")
    notes = sc.get("notes") or {}
    return {"enabled": True, "blocking": blocking,
            "wardrobe": (notes.get("CONTINUITY") or first("wardrobe") or "")[:600],
            "light": (first("lighting") or notes.get("LIGHTING") or "")[:400], "auto": True}


def derive(d: str) -> dict:
    """Fill in missing scenes (and new performers) from the plan; keeps everything the user has set. A scene the person never touched (auto) follows the plan as it is now, and a
    performer who is no longer in any shot of a scene is dropped from its blocking (a person who left the story must not keep steering the picture of the shots that are left)."""
    _, plan = _plan(d)
    c = load(d)
    for sc in plan.get("scenes", []):
        key = str(sc.get("number"))
        dflt = _default_scene(sc)
        cur = c["scenes"].get(key)
        if not cur:
            c["scenes"][key] = dflt
            continue
        if cur.get("auto") is True:
            c["scenes"][key] = {**dflt, "enabled": cur.get("enabled", True)}
            continue
        for n, b in dflt["blocking"].items():
            cur.setdefault("blocking", {}).setdefault(n, b)
        for n in [n for n in (cur.get("blocking") or {}) if n not in dflt["blocking"]]:
            cur["blocking"].pop(n, None)
    return save(d, c)


def set_scene(d: str, scene: str, data: dict) -> dict:
    c = load(d)
    cur = c["scenes"].setdefault(str(scene), {"enabled": True, "blocking": {}, "wardrobe": "", "light": ""})
    for k in ("enabled", "wardrobe", "light"):
        if k in data:
            cur[k] = data[k]
    for n, b in (data.get("blocking") or {}).items():
        if b.get("side") not in SIDES or b.get("facing") not in FACING:
            raise SystemExit("Blocking needs a side (left, center, right) and a facing (left, right, camera, away).")
        cur.setdefault("blocking", {})[n] = {"side": b["side"], "facing": b["facing"]}
    cur["auto"] = False
    return save(d, c)


def set_shot(d: str, shot_id: str, data: dict) -> dict:
    c = load(d)
    cur = c["shots"].setdefault(shot_id, {})
    if "continuous" in data:
        cur["continuous"] = bool(data["continuous"])
    return save(d, c)


# ---------------------------------------------------------------- prompts

def _scene_of(d: str, shot: dict) -> dict | None:
    c = _read(os.path.join(d, "continuity.json"))
    if not c:
        return None
    s = (c.get("scenes") or {}).get(str(shot.get("scene")))
    return s if s and s.get("enabled", True) else None


def direction(d: str, shot: dict) -> str:
    """The continuity sentence for a shot's prompt ('' when the scene has none)."""
    s = _scene_of(d, shot)
    if not s:
        return ""
    block = s.get("blocking") or {}
    here = [n for n in shot.get("performers") or [] if n in block]
    parts = []
    if here:
        pos = [f"{n} screen-{block[n]['side']}" + (f" facing {block[n]['facing']}" if block[n]["facing"] in ("left", "right") else
                                                   " facing camera" if block[n]["facing"] == "camera" else " facing away")
               for n in here if block[n]["side"] != "center"]
        if pos:
            parts.append("Blocking (keep across the scene): " + "; ".join(pos) + ".")
        leads = [n for n, b in block.items() if b["side"] in ("left", "right")]
        if len(leads) >= 2:
            parts.append("Keep the camera on the same side of the line between " + " and ".join(leads[:2]) +
                         " as the rest of the scene (180-degree rule); screen directions never flip.")
        # eyelines: toward the partner, on screen or off
        for n in here:
            other = next((m for m in leads if m != n), None)
            if other and block[n]["side"] in ("left", "right"):
                look = "right" if block[n]["side"] == "left" else "left"
                where = "" if other in here else " (off-screen)"
                parts.append(f"{n} looks screen-{look} toward {other}{where}.")
    if s.get("wardrobe") and not shot.get("wardrobe"):
        parts.append(f"Wardrobe and props stay the same all scene: {s['wardrobe'].rstrip('.')}.")
    if s.get("light") and not shot.get("lighting"):
        parts.append(f"Same light as the rest of the scene: {s['light'].rstrip('.')}.")
    return " ".join(parts)


def previous_keyframe(d: str, plan_name: str, plan: dict, shot_id: str, shared_with: list | None = None) -> str | None:
    """The approved keyframe of the shot before this one in the same scene (a reference for matching set, light and wardrobe).
    With `shared_with` (filled in, it receives the names of the people in both shots): only a previous shot that shows at least one of the same people counts, because a picture of
    other people is copied onto the people of this shot (a friend drawn in someone else's clothes)."""
    kfs = (_read(os.path.join(d, "keyframes.json"), {}) or {}).get(plan_name, {})
    for sc in plan.get("scenes", []):
        ids = [s["id"] for s in sorted(sc["shots"], key=lambda x: x["start"])]
        if shot_id in ids:
            s = load(d)["scenes"].get(str(sc.get("number")))
            if not s or not s.get("enabled", True):   # only once continuity is set up for the scene
                return None
            people = {s["id"]: [str(x) for x in s.get("performers") or []] for s in sc["shots"]}
            for prev in reversed(ids[:ids.index(shot_id)]):
                ref = kfs.get(prev)
                if isinstance(ref, str) and ref.startswith("project:") and os.path.exists(os.path.join(d, ref[8:])):
                    if shared_with is not None:
                        both = [n for n in people.get(shot_id, []) if n.lower() in {x.lower() for x in people.get(prev, [])}]
                        if not both:
                            continue
                        shared_with[:] = both
                    return os.path.join(d, ref[8:])
            return None
    return None


# ---------------------------------------------------------------- first/last frame

def saved_last_frame(d: str, take: dict, jobs: list[dict]) -> str | None:
    """The last frame a provider returned for this take, or for the video a lip-synced take was made from; None when there isn't one on disk."""
    cur = take
    for _ in range(6):
        rel = cur.get("last_frame_image")
        if rel and os.path.isfile(os.path.join(d, rel)):
            return rel
        nxt = next((x for x in jobs if x["id"] == cur.get("source_job")), None) if cur.get("source_job") else None
        if not nxt:
            return None
        cur = nxt
    return None


def chain(d: str, shot_id: str) -> dict:
    """Start this shot from the last frame of the previous shot's take (free): it becomes this shot's keyframe."""
    from .export import ffmpeg
    from .library import chosen_take, shot_state
    plan_name, plan = _plan(d)
    for sc in plan.get("scenes", []):
        ids = [s["id"] for s in sorted(sc["shots"], key=lambda x: x["start"])]
        if shot_id in ids:
            break
    else:
        raise SystemExit(f"Shot {shot_id} not found.")
    i = ids.index(shot_id)
    if i == 0:
        raise SystemExit("This is the first shot of its scene; there's no shot before it to continue from.")
    prev = ids[i - 1]
    jobs = _read(os.path.join(d, "jobs.json"), {"jobs": []})["jobs"]
    take = chosen_take(d, prev, plan_name, jobs, shot_state(d))
    if not take:
        raise SystemExit(f"{prev} has no finished take yet to continue from.")
    os.makedirs(os.path.join(d, "media"), exist_ok=True)
    from .safe import file_part
    rel = f"media/{file_part(shot_id)}_from_{file_part(prev)}_{int(time.time())}.png"
    src = os.path.join(d, take["output"])
    exact = saved_last_frame(d, take, jobs)
    if exact:                                   # the provider handed back the true last frame: better than reading it from the compressed video
        from PIL import Image
        Image.open(os.path.join(d, exact)).convert("RGB").save(os.path.join(d, rel))
    elif take.get("media_kind") == "image":
        from PIL import Image
        Image.open(src).convert("RGB").save(os.path.join(d, rel))
    else:
        from .export import last_frame_png
        if not last_frame_png(src, os.path.join(d, rel)):
            raise SystemExit("Couldn't read the last frame of the previous take.")
    kp = os.path.join(d, "keyframes.json")
    kf = _read(kp, {}) or {}
    kf.setdefault(plan_name, {})[shot_id] = f"project:{rel}"
    _write(kp, kf)
    set_shot(d, shot_id, {"continuous": True})
    return {"shot": shot_id, "from": prev, "keyframe": rel}


# ---------------------------------------------------------------- review

def _size(framing: str) -> str | None:
    f = (framing or "").lower()
    for k, words in (("extreme close-up", ("extreme close", "ecu", "macro")), ("close-up", ("close-up", "close up", "closeup", "tight")),
                     ("medium", ("medium", "mid shot", "waist", "over-the-shoulder", "over the shoulder", "two-shot")),
                     ("wide", ("wide", "establishing", "full shot", "long shot", "overhead", "aerial"))):
        if any(w in f for w in words):
            return k
    return None


def check(d: str) -> dict:
    """Free rules: jump cuts, blocking gaps, performers without a reference, continuous shots not yet chained."""
    from .library import load as load_lib
    plan_name, plan = _plan(d)
    c = load(d)
    kfs = (_read(os.path.join(d, "keyframes.json"), {}) or {}).get(plan_name, {})
    _, lib = load_lib(d)
    has_ref = {i["name"].lower() for i in lib.get("items", []) if i["kind"] == "character" and i.get("files")}
    issues = []
    add = lambda sid, kind, detail, fix, sev="warning": issues.append(
        {"shot": sid, "kind": kind, "detail": detail, "fix": fix, "severity": sev, "source": "rules"})
    for sc in plan.get("scenes", []):
        shots = sorted(sc["shots"], key=lambda x: x["start"])
        scene = c["scenes"].get(str(sc.get("number"))) or {}
        block = scene.get("blocking") or {}
        for a, b in zip(shots, shots[1:]):
            sa, sb = _size(a.get("framing")), _size(b.get("framing"))
            if sa and sa == sb and set(a.get("performers") or []) == set(b.get("performers") or []) and (a.get("performers")) \
                    and not (c["shots"].get(b["id"]) or {}).get("continuous"):
                add(b["id"], "jump cut", f"{a['id']} and {b['id']} are both {sa}s of the same people back to back; the cut will jump.",
                    "Change the size or angle of one of them, or mark it continuous.")
        for sh in shots:
            for n in sh.get("performers") or []:
                if scene and n not in block:
                    add(sh["id"], "blocking", f"{n} has no place in the scene's blocking.", "Set where they stand in Continuity.")
                if has_ref and n.lower() not in has_ref:
                    add(sh["id"], "identity", f"No reference image for {n}; their face and clothes may drift between shots.",
                        "Add a character image for them in the Reference library.", "info")
            if (c["shots"].get(sh["id"]) or {}).get("continuous"):
                ref = kfs.get(sh["id"]) or ""
                if "_from_" not in ref:
                    add(sh["id"], "first frame", "Marked continuous, but it doesn't start from the previous shot's last frame yet.",
                        "Use 'Start from the end of the previous shot'.", "info")
    seen, out = set(), []
    for i in issues:   # one note per shot and kind
        k = (i["shot"], i["kind"], i["detail"])
        if k not in seen:
            seen.add(k)
            out.append(i)
    ai = [x for x in (c.get("review") or {}).get("issues", []) if x.get("source") == "ai"]
    return {"issues": out + ai, "checked": {"rules": int(time.time()), "ai": (c.get("review") or {}).get("ai_at")}}


AI_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["issues"],
    "properties": {"issues": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["shot", "kind", "detail", "fix"],
        "properties": {"shot": {"type": "string"},
                       "kind": {"type": "string", "enum": ["wardrobe", "hair", "props", "lighting", "screen direction", "eyeline",
                                                           "axis", "set", "identity", "time of day"]},
                       "detail": {"type": "string"}, "fix": {"type": "string"}}}}},
}
AI_SYSTEM = """You are a script supervisor checking continuity across the frames of ONE scene of an animated music video.
You get the scene's blocking, wardrobe and light, then its frames in order, each labelled with its shot id.
Report only real continuity breaks BETWEEN shots: wardrobe, hair, props, lighting or time of day changing without reason,
a character's screen side or eyeline flipping (crossing the 180-degree line), the set changing, or a person not looking like themselves.
Intentional changes the scene describes (a flashback, a costume change, a new location) are fine. Do not judge beauty or composition.
Name the shot that breaks continuity (the later one). If nothing breaks, return no issues."""


def _frame(d: str, plan_name: str, sh: dict, kfs: dict, jobs: list) -> str | None:
    from .library import chosen_take, shot_state
    t = chosen_take(d, sh["id"], plan_name, jobs, shot_state(d))
    if t and t.get("media_kind") == "image":
        return os.path.join(d, t["output"])
    ref = kfs.get(sh["id"])
    if isinstance(ref, str) and ref.startswith("project:") and os.path.exists(os.path.join(d, ref[8:])):
        return os.path.join(d, ref[8:])
    return None


def ai_check(d: str, scenes: list | None = None) -> dict:
    """One vision call per scene over its keyframes. Uses the AI brain (OpenAI, or a local vision model for free)."""
    from .director import DEFAULT_MODEL, openai_error, resolve_model
    from .llm import client as brain
    from .review import _image
    plan_name, plan = _plan(d)
    c = derive(d)
    kfs = (_read(os.path.join(d, "keyframes.json"), {}) or {}).get(plan_name, {})
    jobs = _read(os.path.join(d, "jobs.json"), {"jobs": []})["jobs"]
    cl = brain()
    model = resolve_model(cl, DEFAULT_MODEL, vision=True)
    found, calls, errors = [], 0, []
    for sc in plan.get("scenes", []):
        if scenes and sc.get("number") not in scenes and str(sc.get("number")) not in map(str, scenes):
            continue
        frames = [(sh["id"], f) for sh in sorted(sc["shots"], key=lambda x: x["start"])
                  if (f := _frame(d, plan_name, sh, kfs, jobs))]
        if len(frames) < 2:
            continue
        s = c["scenes"].get(str(sc.get("number"))) or {}
        content = [{"type": "input_text", "text": "Scene: " + json.dumps({
            "heading": sc.get("heading"), "blocking": s.get("blocking"), "wardrobe": s.get("wardrobe"), "light": s.get("light"),
            "notes": (sc.get("notes") or {}).get("CONTINUITY", "")}, ensure_ascii=False)}]
        for sid, f in frames[:12]:
            content += [{"type": "input_text", "text": f"Shot {sid}:"},
                        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{_image(f, 512)}"}]
        try:
            r = cl.responses.create(model=model, input=[{"role": "system", "content": AI_SYSTEM}, {"role": "user", "content": content}],
                                    text={"format": {"type": "json_schema", "name": "continuity", "schema": AI_SCHEMA, "strict": True}})
            calls += 1
            ids = {sid for sid, _ in frames}
            for i in json.loads(r.output_text)["issues"]:
                if i["shot"] in ids:
                    found.append({**i, "severity": "warning", "source": "ai", "scene": sc.get("number")})
        except Exception as e:
            errors.append(f"Scene {sc.get('number')}: {openai_error(e)}")
            if len(errors) >= 2 and not calls:
                break
    c = load(d)
    keep = [x for x in (c.get("review") or {}).get("issues", []) if scenes and x.get("scene") not in scenes]
    c["review"] = {"issues": keep + found, "ai_at": int(time.time()), "model": model}
    save(d, c)
    return {"issues": found, "calls": calls, "errors": errors, "model": model}


def get(d: str) -> dict:
    derive(d)
    _, plan = _plan(d)
    c = load(d)
    return {"scenes": [{"number": sc.get("number"), "heading": sc.get("heading"), **c["scenes"].get(str(sc.get("number")), {}),
                        "shots": [{"id": s["id"], "performers": s.get("performers") or [], "framing": s.get("framing") or "",
                                   "continuous": bool((c["shots"].get(s["id"]) or {}).get("continuous"))}
                                  for s in sorted(sc["shots"], key=lambda x: x["start"])]}
                       for sc in plan.get("scenes", [])],
            "review": c.get("review") or {}}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-continuity")
    ap.add_argument("action", choices=["get", "set", "derive", "chain", "check", "ai_check", "shot"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    d = a.project
    try:
        if a.action == "get":
            res = get(d)
        elif a.action == "set":
            res = set_scene(d, x["scene"], x)
        elif a.action == "shot":
            res = set_shot(d, x["shot"], x)
        elif a.action == "derive":
            res = derive(d)
        elif a.action == "chain":
            res = chain(d, x["shot"])
        elif a.action == "check":
            derive(d)
            res = check(d)
        else:
            res = ai_check(d, x.get("scenes"))
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
