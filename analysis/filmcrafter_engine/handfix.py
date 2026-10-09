"""Fix only the bad hand: redraw one small part of a keyframe and leave the rest of the picture exactly as it is.

How it works, in plain words
  1. You mark the hand (drag a box on the keyframe), or FilmCrafter finds the hands that look wrong (locate: a vision model, a few cents).
  2. A crop of that part, with some of its surroundings so the hand keeps its light and skin tone, goes to a picture model that can see pictures, with one instruction: redraw the hands
     with correct anatomy and change nothing else. It is an ordinary keyframe job (priced and confirmed like any other).
  3. When it comes back, the fixed crop is blended into the original keyframe through a soft edge (finish). The result is a NEW picture beside the old one, tagged to be swapped in:
     nothing is replaced until you press Use the new keyframe (keyframeset.apply_swaps), and that can be undone.

What it cannot do: it can't promise the hand will come out right (try a few versions), and it only changes the box you mark, so a hand that spills out of the box is only partly fixed.
Locked shots, shots with no approved keyframe and models that can't see pictures are refused. The original keyframe is never touched.

  python -m filmcrafter_engine.handfix <plan|queue|locate> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from . import anatomy
from .keyframeset import current, inside
from .safe import file_part

MIN_BOX = 0.03             # a box smaller than this (of the picture's width or height) is a slip of the mouse, not a hand
PAD = 0.30                 # context kept around the marked box on each side
MIN_SIDE = 512             # the crop is enlarged to at least this on its short side so the model has detail to work with
MAX_SCALE = 4.0
MAX_VARIANTS = 3
MAX_BOXES = 4

INSTRUCTION = ("Redraw ONLY the hands in this picture with correct anatomy: exactly five distinct fingers on each visible hand, natural joints and proportions. Where hands hold each other, "
               "show every finger separately, with one hand clearly in front of the other. Keep everything else exactly as it is: the same skin tone, clothes, background, light, framing and "
               "size. Do not add, remove or move anything else.")


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def norm_box(box) -> list[float]:
    """[x0, y0, x1, y1] as fractions of the picture, put in order and kept inside it, or a plain-words refusal."""
    try:
        x0, y0, x1, y1 = (float(v) for v in box)
    except (TypeError, ValueError):
        raise SystemExit("Draw a box around the hand.")
    if not all(v == v and abs(v) != float("inf") for v in (x0, y0, x1, y1)):
        raise SystemExit("Draw a box around the hand.")
    x0, x1 = sorted((min(1.0, max(0.0, x0)), min(1.0, max(0.0, x1))))
    y0, y1 = sorted((min(1.0, max(0.0, y0)), min(1.0, max(0.0, y1))))
    if x1 - x0 < MIN_BOX or y1 - y0 < MIN_BOX:
        raise SystemExit("That box is too small. Draw it around the whole hand.")
    return [x0, y0, x1, y1]


def _keyframe(d: str, shot_id: str) -> dict:
    c = next((c for c in current(d) if c["shot"] == shot_id), None)
    if not c:
        raise SystemExit(f"Shot {shot_id} isn't in this project.")
    if c["locked"]:
        raise SystemExit(f"{shot_id} is locked. Unlock it to change its keyframe.")
    if not c["rel"]:
        raise SystemExit("This shot has no approved keyframe to fix.")
    return c


def padded_pixels(box: list[float], size: tuple[int, int]) -> list[int]:
    """The marked box with its surroundings, in pixels of the picture."""
    w, h = size
    x0, y0, x1, y1 = box
    px, py = (x1 - x0) * PAD, (y1 - y0) * PAD
    out = [max(0, int((x0 - px) * w)), max(0, int((y0 - py) * h)), min(w, int(round((x1 + px) * w))), min(h, int(round((y1 + py) * h)))]
    return out


def prepare(d: str, shot_id: str, box) -> dict:
    """Cut the crop that goes to the model. Returns {crop, box (pixels), source, size}."""
    from PIL import Image
    c = _keyframe(d, shot_id)
    box = norm_box(box)
    os.makedirs(os.path.join(d, "media"), exist_ok=True)
    with Image.open(os.path.join(d, c["rel"])) as im:
        im = im.convert("RGB")
        px = padded_pixels(box, im.size)
        if px[2] - px[0] < 8 or px[3] - px[1] < 8:
            raise SystemExit("That box is too small. Draw it around the whole hand.")
        crop = im.crop(tuple(px))
    scale = min(MAX_SCALE, max(1.0, MIN_SIDE / min(crop.size)))
    if scale > 1.0:
        crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.LANCZOS)
    rel = f"media/{file_part(shot_id)}_handcrop_{int(time.time() * 1000)}.png"
    crop.save(os.path.join(d, rel))
    return {"crop": rel, "box": px, "source": c["rel"], "size": list(crop.size)}


def _model(d: str, shot_id: str, provider=None, model=None) -> dict:
    """The picture model for the fix: the one asked for, else the one that made the keyframe, else the pinned one, else the cheapest proven model that can see pictures."""
    from .routing import models
    rows = [m for m in models("image") if m.get("sees_references")]
    if provider and model:
        row = next((m for m in rows if m["provider"] == provider and m["model"] == model), None)
        if not row:
            raise SystemExit("That model can't be used for this: it isn't in FilmCrafter's list, you have no key for it, or it can't see pictures.")
        return row
    c = _keyframe(d, shot_id)
    for want in ((c["provider"], c["model"]), tuple(((_read(os.path.join(d, "project.json"), {}) or {}).get("routing", {}).get("pins") or {}).get("image", {}).get(k) for k in ("provider", "model"))):
        row = next((m for m in rows if (m["provider"], m["model"]) == want), None)
        if row:
            return row
    proven = sorted([m for m in rows if m["verified"] and m["price_usd"] is not None], key=lambda m: m["price_usd"])
    if not proven:
        raise SystemExit("No picture model that can see pictures is available. Add a Kie.ai, fal.ai or OpenAI key in Settings.")
    return proven[0]


def plan(d: str, shot_id: str, variants: int = 1, provider=None, model=None) -> dict:
    """Which model would make the fix and about what it costs. Free."""
    from .routing import batch_usd
    row = _model(d, shot_id, provider, model)
    n = max(1, min(MAX_VARIANTS, int(variants or 1)))
    return {"model": {"provider": row["provider"], "model": row["model"], "label": row["label"], "price_usd": row["price_usd"]}, "variants": n,
            "usd_est": round(batch_usd(d, [shot_id], row["provider"], row["model"], "image") * n, 2)}


def queue(d: str, shot_id: str, box, note: str = "", variants: int = 1, provider=None, model=None) -> dict:
    """Queue the fix: 1 to 3 versions of the crop on the chosen model. They arrive as new keyframes waiting to be used."""
    from .keyframeset import _need_key
    from .render import enqueue
    row = _model(d, shot_id, provider, model)
    _need_key(row["provider"])
    prep = prepare(d, shot_id, box)
    extra = " ".join(str(note or "").split())[:300]
    spec = {**prep, "instruction": INSTRUCTION + (f" Also: {extra}." if extra else ""), "marked": norm_box(box)}
    made = enqueue(d, [shot_id], row["provider"], row["model"], {"_variants": max(1, min(MAX_VARIANTS, int(variants or 1))), "_hand_fix": spec, "_swap_in": "handfix"}, [], kind="image")
    if not made:
        raise SystemExit("Nothing was queued: the shot is locked, or the same fix is already being made.")
    from .routing import batch_usd
    return {"queued": len(made), "jobs": made, "model": row["label"], "usd_est": round(batch_usd(d, [shot_id], row["provider"], row["model"], "image") * len(made), 2)}


# ---------------------------------------------------------------- putting the fixed part back

def blend(original, fixed, px: list[int]):
    """The original with `fixed` laid into the box `px` through a soft edge, so the join can't be seen. Both are PIL images; returns a new one."""
    from PIL import Image, ImageFilter, ImageOps
    x0, y0, x1, y1 = px
    bw, bh = x1 - x0, y1 - y0
    piece = ImageOps.fit(fixed.convert("RGB"), (bw, bh), Image.LANCZOS)         # the model may return a slightly different shape: fit it to the box
    feather = max(6, int(0.14 * min(bw, bh)))
    mask = Image.new("L", (bw, bh), 0)
    inner = Image.new("L", (max(1, bw - 2 * feather), max(1, bh - 2 * feather)), 255)
    mask.paste(inner, (feather, feather))
    mask = mask.filter(ImageFilter.GaussianBlur(feather / 2.0))
    out = original.convert("RGB").copy()
    out.paste(piece, (x0, y0), mask)
    return out


def finish(d: str, store, job: dict) -> None:
    """Called when a hand-fix job's crop has come back: lay it into the keyframe and make that the job's picture. Nothing is replaced; the original keyframe is untouched."""
    from PIL import Image
    hf = job.get("hand_fix") or {}
    if hf.get("placed") or not job.get("output") or not inside(d, hf.get("source")) or not inside(d, job["output"]):
        return
    px = hf.get("box")
    if not (isinstance(px, list) and len(px) == 4 and all(isinstance(v, int) for v in px)):
        raise SystemExit("The fix doesn't say where it goes.")
    with Image.open(os.path.join(d, hf["source"])) as base, Image.open(os.path.join(d, job["output"])) as fixed:
        px = [max(0, px[0]), max(0, px[1]), min(base.width, px[2]), min(base.height, px[3])]
        if px[2] - px[0] < 8 or px[3] - px[1] < 8:
            raise SystemExit("The marked box is outside the picture.")
        result = blend(base, fixed, px)
    rel = f"media/{file_part(job['shot_id'])}_handfix_{file_part(job['id'])}.png"
    result.save(os.path.join(d, rel))
    store.update(job, output=rel, crop_output=job["output"], hand_fix={**hf, "placed": True})


# ---------------------------------------------------------------- finding the hands

LOCATE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["hands"],
    "properties": {"hands": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["x0", "y0", "x1", "y1", "why"],
        "properties": {"x0": {"type": "number"}, "y0": {"type": "number"}, "x1": {"type": "number"}, "y1": {"type": "number"}, "why": {"type": "string"}}}}},
}
LOCATE_SYSTEM = ("You look at one picture from an animated music video and find the hands (and anything else of the body) that are drawn wrongly: " + anatomy.LOOK_FOR + " "
                 "Give each one a box around the WHOLE hand or limb that is wrong, as fractions of the picture from its top-left corner (0 to 1: x0 left, y0 top, x1 right, y1 bottom), and say "
                 "in a few words what is wrong. Where two hands hold each other, give one box around both. If nothing is wrong, give an empty list. Do not invent problems.")


def locate(d: str, shot_id: str) -> dict:
    """Ask the AI brain's vision model where the wrong-looking hands are. A few cents. The boxes are suggestions: the person adjusts them."""
    import base64
    from .director import DEFAULT_MODEL, resolve_model
    from .llm import client as brain
    from .review import _image
    from .stills import can_check
    c = _keyframe(d, shot_id)
    if not can_check():
        raise SystemExit("Finding hands needs an AI brain that can look at pictures: add an OpenAI key in Settings, or set up a local model that can see. You can still draw the box yourself.")
    cl = brain()
    mdl = resolve_model(cl, DEFAULT_MODEL, vision=True)
    r = cl.responses.create(model=mdl, input=[{"role": "system", "content": LOCATE_SYSTEM},
                                               {"role": "user", "content": [{"type": "input_text", "text": "The picture:"},
                                                                            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{_image(os.path.join(d, c['rel']), 1024)}"}]}],
                            text={"format": {"type": "json_schema", "name": "hand_boxes", "schema": LOCATE_SCHEMA, "strict": True}})
    return {"boxes": clean_boxes(json.loads(r.output_text)), "model": mdl}


def clean_boxes(out) -> list[dict]:
    """The model's boxes, kept only when they make sense, and at most four."""
    boxes = []
    for h in (out or {}).get("hands") or []:
        try:
            b = norm_box([h["x0"], h["y0"], h["x1"], h["y1"]])
        except (SystemExit, KeyError, TypeError):
            continue
        boxes.append({"box": b, "why": " ".join(str(h.get("why", "")).split())[:160]})
    return boxes[:MAX_BOXES]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-handfix")
    ap.add_argument("action", choices=["plan", "queue", "locate"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    d = a.project
    try:
        res = (plan(d, x["shot"], x.get("variants", 1), x.get("provider"), x.get("model")) if a.action == "plan" else
               queue(d, x["shot"], x.get("box"), x.get("note", ""), x.get("variants", 1), x.get("provider"), x.get("model")) if a.action == "queue" else locate(d, x["shot"]))
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
