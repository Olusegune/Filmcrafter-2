"""Keyframe check: catch a bad still before anyone pays for video made from it.

Each finished keyframe is compared (by the vision model of the configured AI brain) with the shot it is for and
the clean reference images of the people in it. It fails for what breaks a video: collage/panel layouts, visible
text or banners, the wrong people, framing far from the request, or missing performers. A failed still is re-made
once, automatically, with the specific correction; nothing is ever re-made twice.
"""
from __future__ import annotations

import json
import os

from .anatomy import LOOK_FOR, with_fix

CHECK_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["ok", "problems", "fix"],
    "properties": {
        "ok": {"type": "boolean"},
        "problems": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["kind", "severity", "detail"],
            "properties": {"kind": {"type": "string", "enum": ["collage", "text", "identity", "framing", "missing", "artifact", "anatomy", "look"]},
                           "severity": {"type": "string", "enum": ["minor", "major"]},
                           "detail": {"type": "string"}}}},
        "fix": {"type": "string", "description": "One instruction to add to the image prompt that fixes the problems (empty if ok)."},
    },
}

SYSTEM = """You check keyframes (single stills) for an animated music video before they are animated.
You see: reference images of the characters (labelled), then the keyframe, then the shot it is for.
Fail the still ONLY for problems that would ruin the video:
- collage: split screen, panels, inset portraits, a reference-sheet or storyboard layout instead of one camera frame,
  or a picture that doesn't fill the frame (white or coloured borders or margins around it)
- text: text laid OVER the picture (titles, captions, subtitles, watermarks, logos, a reference-sheet banner).
  Writing that naturally belongs in the scene (station or shop signs, labels on objects, a letter a character holds)
  is fine unless the shot says otherwise, or it is garbled nonsense filling the frame
- identity: a named performer clearly isn't the person in their reference (face, skin tone, hair, age) or is a different ethnicity
- missing: a performer who must be in the shot isn't visible
- framing: framing is far from the request (e.g. a wide shot when an extreme close-up of an eye was asked)
- artifact: melting objects or a face that is obviously malformed
- """ + LOOK_FOR + """
- look: clearly a different rendering style (e.g. photoreal when the project is animated)
Give every problem a severity. "major" fails the still. "minor" is only listed so the filmmaker can see it: use it for hands that are plausible but soft, never for the other kinds
(collage, text, identity, missing, framing and look are always major). Hands or limbs that are clearly wrong are major.
Small differences are fine: say ok. Be strict about collages and overlaid text; they always fail.
A title card the shot itself asks for is not a failure."""


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def check(d: str, job: dict) -> dict:
    """Check one finished keyframe job. Returns {ok, problems, fix, model} or raises (the caller records it)."""
    from .director import DEFAULT_MODEL, resolve_model
    from .library import load, shot_items
    from .llm import client as brain
    from .render import _load_plan, _shot, resolve_look
    from .review import _image
    project = _read(os.path.join(d, "project.json"), {})
    _, plan = _load_plan(d) if job.get("plan") == "directed" else ("production", _read(os.path.join(d, "production.json"), {}))
    shot, scene = _shot(plan, job["shot_id"])
    _, lib = load(d)
    content = []
    for it in shot_items(lib, shot, (scene or {}).get("number")):
        if it["kind"] == "character" and not it.get("sheet") and it.get("files"):
            p = os.path.join(d, it["files"][0])
            if os.path.exists(p):
                content += [{"type": "input_text", "text": f"Reference for {it['name']}:"},
                            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{_image(p, 512)}"}]
    content += [{"type": "input_text", "text": "The keyframe to check:"},
                {"type": "input_image", "image_url": f"data:image/jpeg;base64,{_image(os.path.join(d, job['output']), 1024)}"},
                {"type": "input_text", "text": "The shot: " + json.dumps({
                    "description": shot.get("visual_prompt") or " ".join(shot.get("beats", [])),
                    "performers": shot.get("performers", []), "framing": shot.get("framing"), "lens": shot.get("lens"),
                    "look": resolve_look(project)["prompt"][:300]}, ensure_ascii=False)}]
    c = brain()
    model = resolve_model(c, DEFAULT_MODEL, vision=True)
    r = c.responses.create(model=model, input=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}],
                           text={"format": {"type": "json_schema", "name": "still_check", "schema": CHECK_SCHEMA, "strict": True}})
    return settle(json.loads(r.output_text), model)


def settle(out: dict, model: str = "") -> dict:
    """Apply the checker's verdict: only a major problem fails the still (a minor one, a soft hand, is kept in the list so it is shown), and an anatomy failure carries the standard correction."""
    problems = [p for p in out.get("problems") or [] if isinstance(p, dict)]
    major = [p for p in problems if p.get("kind") != "anatomy" or p.get("severity") != "minor"]
    out["problems"] = problems
    out["ok"] = (not major) if problems else bool(out.get("ok", True))
    if any(p.get("kind") == "anatomy" for p in major):
        out["fix"] = with_fix(out.get("fix", ""))
    elif out["ok"]:
        out["fix"] = ""
    out["model"] = model
    out["anatomy_checked"] = True            # this check looked at hands and limbs on purpose (older results did not)
    return out


def can_check() -> bool:
    from .llm import config
    b = config()
    return bool(os.environ.get("PULSEFRAME_OPENAI_KEY")) if b["provider"] == "openai" else bool(b["vision_model"])


def after_still(d: str, store, job: dict) -> None:
    """Called when a keyframe finishes: check it, and re-make a failed one once with the correction."""
    from .director import openai_error
    from .render import emit, enqueue
    if job.get("hand_fix"):   # a fixed part of a keyframe: lay it into the picture first, then check the whole picture (never re-made automatically: that would be a new, paid keyframe)
        from .handfix import finish
        try:
            finish(d, store, job)
        except (SystemExit, Exception) as e:
            store.update(job, state="failed", error=f"Couldn't lay the fixed hand into the picture: {e}", error_kind="service")
            return
    if not can_check():
        return
    emit(event="progress", stage=f"checking keyframe {job['shot_id']}")
    try:
        res = check(d, job)
    except Exception as e:  # never break rendering; the still stays usable, marked unchecked
        store.update(job, still_check={"ok": None, "error": openai_error(e)})
        return
    store.update(job, still_check=res)
    if res["ok"] or job.get("remake_of") or job.get("hand_fix"):
        return
    kinds = {p["kind"] for p in res["problems"]}
    notes = [res["fix"]] if res["fix"] else []
    if kinds & {"collage", "text"}:
        notes.append("One single continuous camera frame; no panels, inset portraits or lettering anywhere.")
    try:
        made = enqueue(d, [job["shot_id"]], job["provider"], job["model"], job.get("overrides") or {}, notes, kind="image")
    except SystemExit as e:   # the budget or Local First said no: keep the still, just don't re-make it
        emit(event="progress", stage=f"keyframe {job['shot_id']} not re-made: {e}")
        return
    for m in made:   # the runner's store picks the new job up on this save (merge)
        store.update(m, remake_of=job["id"], **({"swap_in": job["swap_in"]} if job.get("swap_in") else {}))   # a re-made keyframe that was itself a swap stays one
    emit(event="progress", stage=f"re-making keyframe {job['shot_id']}: {', '.join(sorted(kinds))}")
