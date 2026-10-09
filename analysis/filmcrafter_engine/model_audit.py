"""Would FilmCrafter send a request this video model accepts? An offline check, model by model, that spends nothing.

For one model's own schema it builds the request FilmCrafter would send for a typical shot (an approved keyframe plus the cast sheet, a place and a
prop as references, with and without an end frame) and checks it against what the model says it takes:

  - every required input is filled
  - every key sent really is one of the model's inputs (no stray spaces or invented names)
  - the prompt fits the model's text limit, the duration its range, the references its count
  - a picture field that means FIRST/LAST FRAME is never given a character sheet
  - values are among the allowed choices

  python -m filmcrafter_engine.model_audit [kie|fal] [--kind video|image] [--limit N]      (reads the providers' public schemas; sends no render)

For picture models (keyframes) it checks the same things, and also whether the model can SEE the character sheet and the set: a text-to-image model cannot, so it can only describe the
people and the style in words, which is where drift to a different look and a different face comes from. Those models are listed as "blind" rather than as problems.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from . import render as R

REFS = [{"label": "approved keyframe", "url": "https://x/keyframe.png", "keyframe": True},
        {"label": "Beatrice's character sheet", "url": "https://x/char_sheet.png"},
        {"label": "the family home", "url": "https://x/home.png"},
        {"label": "the brass bell", "url": "https://x/bell.png"}]
END = {"label": "end frame", "url": "https://x/end.png", "endframe": True}
SHOT = {"id": "S01-01", "start": 0.0, "end": 3.2, "beats": ["Beatrice raises the bell and rings it, looking straight at her family."],
        "performers": ["Beatrice"], "framing": "medium shot, 35 mm", "lens": "35 mm"}
PLAN = {"meta": {"TITLE": "Audit"}, "characters": [{"name": "Beatrice", "appearance": "A 60-year-old woman with dark brown skin, a burgundy gele and gold earrings. " * 3}]}
PROJECT = {"look": {"style": "auto"}, "aspect_ratio": "16:9", "quality": "standard", "bible": {"world": "A Lagos family home in morning light. " * 8, "rules": "Same faces and outfits in every shot. " * 5, "avoid": "Extra people."}}
SHEET = "char_sheet"
IMAGE_WORDS = ("image", "frame", "input_urls", "ref")


def audit_one(man: dict, with_end: bool = False) -> list[str]:
    """Problems found for one model (empty = this model looks right)."""
    if (man.get("caps") or {}).get("kind") != "video":
        return []
    refs = list(REFS) + ([END] if with_end else [])
    try:
        payload = R.compile_request(SHOT, None, PLAN, PROJECT, man, refs)
        payload = R.fill_required(man, payload, refs)
        payload = R.exclusive_inputs(man.get("provider", ""), man.get("model", ""), payload, man)
    except SystemExit as e:
        return [f"could not build a request: {e}"]
    except Exception as e:
        return [f"crashed building a request: {type(e).__name__}: {e}"]
    problems = list(R.validate_request(man, payload))
    names = {f["name"] for f in man["inputs"]}
    for k in payload:
        if k not in names:
            problems.append(f"sends “{k}”, which is not one of the model's inputs")
        if k != k.strip():
            problems.append(f"input name “{k}” has stray spaces")
    roles = man.get("roles") or {}
    p = payload.get(roles.get("prompt", "prompt")) or ""
    lim = next((f.get("max_length") for f in man["inputs"] if f["name"] == roles.get("prompt", "prompt")), None) or R.known_prompt_limit(man.get("model", ""))
    if lim and len(str(p).encode("utf-8")) > lim:
        problems.append(f"prompt is {len(str(p).encode('utf-8'))} bytes; the model allows {lim}")
    if not p:
        problems.append("no prompt was sent")
    if "ref_images" in roles and R.frames_only(man):
        sent = payload.get(roles["ref_images"])
        sent = sent if isinstance(sent, list) else [sent] if sent else []
        if any(SHEET in str(u) or "home.png" in str(u) or "bell.png" in str(u) for u in sent):
            problems.append("a picture field that means first/last frame was given a reference picture (it would start or end on it)")
    if R.exclusive_by_docs(man) and payload.get(roles.get("first_frame", "")):
        also = [k for r in ("ref_images", "ref_videos", "ref_audio") if (k := roles.get(r)) and payload.get(k)]
        if also:
            problems.append(f"sends a first frame together with {', '.join(also)}, which the model's documentation says cannot be combined")
    for role in ("first_frame",):
        if role in roles and payload.get(roles[role]) and SHEET in str(payload[roles[role]]):
            problems.append("the first frame is a character sheet, not the keyframe")
    return problems


STYLE_PROJECT = {**PROJECT, "look": {"style": "feature-3d"}}
STYLE_PLAN = {**PLAN, "meta": {"TITLE": "Audit", "VISUAL STYLE": "Cinematic contemporary realism with film grain."}}


def audit_image(man: dict) -> tuple[list[str], bool]:
    """(problems, blind) for one picture model: the request FilmCrafter would send for a keyframe, with the cast sheet and a place as references, in a stylised look."""
    if (man.get("caps") or {}).get("kind") == "video" or (man.get("caps") or {}).get("kind") == "lipsync":
        return [], False
    refs = [{"label": "Beatrice's character sheet", "url": "https://x/char_sheet.png"}, {"label": "the family home", "url": "https://x/home.png"}]
    try:
        payload = R.compile_request(SHOT, None, STYLE_PLAN, STYLE_PROJECT, man, refs)
        payload = R.fill_required(man, payload, refs)
    except SystemExit as e:
        return [f"could not build a request: {e}"], False
    except Exception as e:
        return [f"crashed building a request: {type(e).__name__}: {e}"], False
    problems = list(R.validate_request(man, payload))
    names = {f["name"] for f in man["inputs"]}
    for k in payload:
        if k not in names:
            problems.append(f"sends “{k}”, which is not one of the model's inputs")
        if k != k.strip():
            problems.append(f"input name “{k}” has stray spaces")
    roles = man.get("roles") or {}
    p = str(payload.get(roles.get("prompt", "prompt")) or "")
    lim = next((f.get("max_length") for f in man["inputs"] if f["name"] == roles.get("prompt", "prompt")), None) or R.known_prompt_limit(man.get("model", ""))
    if lim and len(p.encode("utf-8")) > lim:
        problems.append(f"prompt is {len(p.encode('utf-8'))} bytes; the model allows {lim}")
    if not p:
        problems.append("no prompt was sent")
    if "Style lock" not in p:
        problems.append("the style lock was cut from the prompt (a short prompt limit): the look can drift")
    if re.search(r"\bfilm grain\b|\bcinematic realism\b", p, re.I):
        problems.append("a request for realism reached a stylised prompt")
    blind = not any(k in roles for k in ("ref_images", "first_frame"))
    return problems, blind


def run(provider: str, limit: int | None = None, kind: str = "video") -> dict:
    if kind == "image":
        return run_images(provider, limit)
    models = [m for m in R.catalog(provider, "video")]
    if limit:
        models = models[:limit]
    report = {"provider": provider, "checked": 0, "ok": 0, "problems": {}, "unreadable": {}}
    for m in models:
        try:
            man = R.manifest(provider, m["model"])
        except (SystemExit, Exception) as e:
            report["unreadable"][m["model"]] = str(e)[:160]
            continue
        report["checked"] += 1
        found = audit_one(man) + [x + " (with an end frame)" for x in audit_one(man, True) if x not in audit_one(man)]
        if found:
            report["problems"][m["model"]] = found
        else:
            report["ok"] += 1
    return report


def run_images(provider: str, limit: int | None = None) -> dict:
    models = [m for m in R.catalog(provider, "image")]
    if limit:
        models = models[:limit]
    report = {"provider": provider, "kind": "image", "checked": 0, "ok": 0, "problems": {}, "unreadable": {}, "blind": []}
    for m in models:
        try:
            man = R.manifest(provider, m["model"])
        except (SystemExit, Exception) as e:
            report["unreadable"][m["model"]] = str(e)[:160]
            continue
        if (man.get("caps") or {}).get("kind") != "image":
            continue                                        # a tool in the picture list (upscale, background removal, layers) rather than a generator
        report["checked"] += 1
        found, blind = audit_image(man)
        if blind:
            report["blind"].append(m["model"])
        if found:
            report["problems"][m["model"]] = found
        else:
            report["ok"] += 1
    return report


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-model-audit")
    ap.add_argument("provider", nargs="?", default="kie", choices=["kie", "fal"])
    ap.add_argument("--kind", default="video", choices=["video", "image"])
    ap.add_argument("--limit", type=int)
    a = ap.parse_args(argv)
    r = run(a.provider, a.limit, a.kind)
    print(json.dumps(r, indent=1, ensure_ascii=False))
    return 0 if not r["problems"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
