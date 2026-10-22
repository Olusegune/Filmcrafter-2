"""Picture care: asking the picture and video models for natural skin, true colour and a clean image.

AI pictures and video have habits of their own: a yellow, orange or golden cast over everything (very common in some image models, whose pictures drift warm), skin that looks waxy, smooth or
airbrushed, and a layer of noise or grain. Wording cannot remove them, but it lowers the odds a good deal, and it costs nothing:

  guard      one line added to every picture and video request: neutral white balance, real skin with its texture, a clean image. It is left out of the colour part when the shot is meant to be
             warm (golden hour, firelight, a candle, a sunset, a warm look), so a sunset still looks like a sunset.
  negative   the same things as words to avoid, for the models that take a negative prompt.

It is on by default, and can be switched off for a film (Colour match → While pictures are made). The pictures that are already made are not changed by this: Colour match can take a cast
out of them when the film is put together (colormatch.py).

Pure text: free, deterministic, nothing is sent anywhere.
"""
from __future__ import annotations

import re

PRIORITY = 6                                   # below the anatomy line (8) and the look (high), above the loose extras: dropped first when the prompt is too long

WARM_ON_PURPOSE = re.compile(r"golden hour|golden[- ]hour|magic hour|sunset|sunrise|dusk|dawn|candle|candlelight|firelight|fire light|campfire|fireplace|lantern|tungsten|warm light|warm glow|warm tone|"
                             r"amber|sepia|vintage|nostalg|golden light|golden glow|incandescent|bonfire|sodium", re.I)

COLOUR_LINE = ("Natural, true-to-life colour with a neutral white balance: whites look white and skin shows its real tone, with no yellow, orange, sepia or golden cast over the picture. ")
SKIN_LINE = ("People have natural skin with visible pores, fine lines and small imperfections, never smooth, waxy, plastic or airbrushed. ")
CLEAN_LINE = ("The image is clean and sharp with fine natural detail: no digital noise, heavy grain, smearing or over-sharpening. ")
# the background: fine repeating patterns (a chain-link fence, mesh, brick, leaves, grass) are what image models smear, so they are kept soft or simple
PATTERN_LINE = ("Fine repeating patterns in the background, such as fences, mesh, brick, leaves and grass, are kept soft or simple: never sharp, noisy or moire. ")
SOFT_LINE = ("The background is gently out of focus (shallow depth of field), so it never competes with the people.")

NEG_COLOUR = ["yellow tint", "yellow cast", "golden cast", "orange cast", "sepia tone", "warm colour cast"]
NEG_SKIN = ["waxy skin", "plastic skin", "airbrushed skin", "oversmoothed skin", "doll-like skin"]
NEG_CLEAN = ["digital noise", "heavy film grain", "oversharpened", "smeared detail"]
NEG_BACKGROUND = ["moire pattern", "noisy background", "aliased mesh", "sharp tangled fence"]


def enabled(project: dict) -> bool:
    pc = (project or {}).get("picture_care")
    return True if not isinstance(pc, dict) else bool(pc.get("on", True))


def _text(shot: dict) -> str:
    out: list[str] = []
    for k in ("visual_prompt", "lighting", "light", "mood", "description", "beats", "note", "custom_prompt", "time_of_day", "setting"):
        v = shot.get(k)
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            out += [str(x) for x in v.values() if isinstance(x, str)]
        elif isinstance(v, (list, tuple)):
            out += [x for x in v if isinstance(x, str)]
    return " ".join(out)


def wants_warm(shot: dict, project: dict | None = None, look_prompt: str = "") -> bool:
    """True when the shot or the film's look is warm on purpose: then the colour part of the care is left out for this shot."""
    return bool(WARM_ON_PURPOSE.search(_text(shot) + " " + str(look_prompt or "")))


def guard(shot: dict, project: dict, look_prompt: str = "") -> dict | None:
    """The picture-care line for this shot ({"text", "priority"}), or None when it is switched off for the film."""
    if not enabled(project):
        return None
    people = bool(shot.get("performers"))
    parts = ([] if wants_warm(shot, project, look_prompt) else [COLOUR_LINE]) + ([SKIN_LINE] if people else []) + [CLEAN_LINE, PATTERN_LINE]
    soft = soft_background(shot)
    if soft:
        parts.append(SOFT_LINE)
    return {"text": "".join(parts).rstrip(), "priority": PRIORITY, "warm_kept": wants_warm(shot, project, look_prompt), "soft_background": soft}


def soft_background(shot: dict) -> bool:
    """True for a shot about people (not a wide or establishing view) where nobody chose the focus: the background is asked to be softly out of focus, which also hides what image models smear."""
    if not shot.get("performers") or shot.get("focus"):
        return False
    framing = str(shot.get("framing") or "").lower()
    if framing.startswith(("wide", "establishing", "extreme wide")):
        return False
    return not re.search(r"deep focus|everything in focus|sharp background", _text(shot), re.I)


def negative(base: str, shot: dict, project: dict, look_prompt: str = "") -> str:
    """The negative prompt with the picture-care words added (not repeated, and the colour words left out for a shot that is warm on purpose)."""
    g = guard(shot, project, look_prompt)
    if not g:
        return base
    terms = ([] if g["warm_kept"] else NEG_COLOUR) + (NEG_SKIN if shot.get("performers") else []) + NEG_CLEAN + NEG_BACKGROUND
    have = {t.strip().lower() for t in base.split(",")}
    extra = [t for t in terms if t.lower() not in have]
    return ", ".join(x for x in (base, ", ".join(extra)) if x)
