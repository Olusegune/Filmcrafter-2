"""Anatomy: the part of a picture or video that models get wrong most often (hands, fingers, limbs, teeth), and what PULSEFRAME does about it.

  prevent   a short instruction goes into the prompt when people are in the shot, a stronger one when hands hold, touch or do something (guard), and models that take a negative
            prompt are told what to avoid (NEGATIVE). This lowers the odds; it can't remove them: no model is reliable on hands.
  flag      the keyframe check (stills.py) and the take review (review.py) look at hands and limbs on purpose, as a problem of their own ("anatomy"), and say what is wrong.
  fix       a flagged keyframe is re-made once with the correction (ANATOMY_FIX) before any video is paid for; a flagged take is fixed from Review with the same correction.

What this module cannot do is look at a picture itself: that needs a vision model, which the check uses when one is set up (a few cents), and the free path is to look yourself, so the
guard and the wording of what to look for (LOOK_FOR) are shown in plain words.
"""
from __future__ import annotations

import re

# words in a shot that put hands to work or in contact with something or someone
HANDS_RX = re.compile(
    r"\b(hold(?:s|ing)?|held|hands?|fingers?|grip(?:s|ping)?|clasp(?:s|ing)?|clutch(?:es|ing)?|touch(?:es|ing)?|reach(?:es|ing)?|embrac(?:e|es|ing)|hug(?:s|ging)?|"
    r"wav(?:e|es|ing)|point(?:s|ing)?|clap(?:s|ping)?|carr(?:y|ies|ying)|cradl(?:e|es|ing)|lift(?:s|ing)?|pull(?:s|ing)?|push(?:es|ing)?|"
    r"play(?:s|ing)? (?:the )?(?:guitar|piano|drums?|keys|violin|bass|saxophone|trumpet)|writ(?:e|es|ing)|paint(?:s|ing)?|dance(?:s|ing)? together|"
    r"lock(?:s|ed|ing)? arms|link(?:s|ed|ing)? arms|palms?|wrists?|fists?|knuckles?|thumbs?)\b", re.I)
CLOSE_FRAMING = re.compile(r"close|insert|detail|\becu\b|macro", re.I)

BASIC = ("Natural human anatomy: two arms and two legs, five separate fingers on each hand, natural joints, no extra, missing or fused fingers or limbs.")
HANDS = ("Hands are drawn with care and are clearly readable: five separate fingers on each hand, natural joints and proportions. Where hands hold or touch, every finger is "
         "distinct and overlaps the other hand believably: no fused, melted, doubled or missing fingers.")
# for models that take a negative prompt
NEGATIVE = "extra fingers, missing fingers, fused fingers, deformed hands, malformed hands, extra limbs, extra arms, extra legs, distorted anatomy, distorted face"

# what the checks look for, in the checker's words (shared by the keyframe check and the take review)
LOOK_FOR = ("anatomy: look closely at every visible hand and at any place where hands hold, touch or overlap something or someone. Count the fingers on each hand: report a hand that "
            "has more or fewer than five, fingers that are fused, merged into a mass, bent the wrong way or of impossible length, or hands that blur into the other person's hand or "
            "sleeve. Also report extra, missing or twisted arms and legs, a face with mismatched or misplaced eyes, and teeth that are fused or the wrong number. Report only what you can "
            "actually see: a hand that is out of frame, hidden or small and far away is not a problem. A hand that is plausible but soft is minor; fingers clearly wrong are major.")

# the correction added to a redo
ANATOMY_FIX = ("Redraw the hands and any limbs with correct anatomy: exactly five distinct fingers on each visible hand, natural joints and proportions, and where hands hold each other "
               "show each finger separately, with one hand clearly in front of the other. No fused, extra or missing fingers or limbs.")


def _text(shot: dict) -> str:
    out: list[str] = []
    for k in ("visual_prompt", "beats", "description", "performance", "movement", "business", "choreography", "custom_prompt", "note"):
        v = shot.get(k)
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, (list, tuple)):
            out += [x for x in v if isinstance(x, str)]
    return " ".join(out)


def guard(shot: dict) -> dict | None:
    """The anatomy line for this shot, or None when nobody is in it. {"text", "priority", "hands"}: `hands` is true when hands are doing something, so the stronger wording is used."""
    people = bool(shot.get("performers"))
    text = _text(shot)
    hands = bool(HANDS_RX.search(text)) or bool(CLOSE_FRAMING.search(str(shot.get("framing") or "")) and people)
    if not (people or hands):
        return None
    return {"text": HANDS if hands else BASIC, "priority": 8 if hands else 5, "hands": hands}


def negative(base: str, shot: dict) -> str:
    """The negative prompt with the anatomy terms added when people are in the shot (not repeated if already there)."""
    if not guard(shot):
        return base
    have = {t.strip().lower() for t in base.split(",")}
    extra = [t.strip() for t in NEGATIVE.split(",") if t.strip().lower() not in have]
    return ", ".join([base, *extra]) if base and extra else ", ".join(extra) if extra else base


def with_fix(fix: str) -> str:
    """The checker's own fix, plus the standard anatomy correction (once)."""
    fix = (fix or "").strip()
    return fix if ANATOMY_FIX in fix else (fix.rstrip(".") + ". " if fix else "") + ANATOMY_FIX
