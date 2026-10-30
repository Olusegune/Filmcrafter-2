"""Which parts of a performance matter for ONE shot, and how to word them for the kind of character and the look.

The Performance Director keeps many things (beats, nudges, psychology, gestures); a prompt has room for few. This module picks the small piece that matters here and phrases it for:

  * the KIND of character (set by you, never guessed): a person, a stylised person, an animal, a robot, a creature. A robot has no face muscles to act with, an animal acts with ears, tail and
    posture; asking either to "furrow their brow" is wasted words, so the channels that can carry the feeling are named instead.
  * the LOOK's family (photoreal, 3D, 2D, craft ...): the same feeling reads differently on a clay face, a drawn face and a filmed face.
  * the EFFORT in the shot (lifting, running, climbing) and the physical INTERACTION (a hug, a handshake, passing an object): two categories that need their own lines to look believable.

Free, deterministic, sends nothing. A kind you did not choose adds nothing; effort and contact lines come only from words already in the shot.
"""
from __future__ import annotations

import re

KINDS = ("human", "stylised", "animal", "robot", "creature")
KIND_NAMES = {"human": "A person", "stylised": "A stylised person (cartoon, puppet)", "animal": "An animal", "robot": "A robot or machine", "creature": "A creature or monster"}

# what can carry a feeling for this kind of character, as direction
CHANNELS = {
    "human": "",
    "stylised": "{n}'s feeling reads in simple, clear shape changes: the brows, the eyelids, the mouth corners and the whole pose, readable from far away.",
    "animal": "{n} is an animal: the feeling shows in the ears, the tail, the weight of the body, the eyes and the breathing; never human facial expressions or hand gestures.",
    "robot": "{n} is a machine: the feeling shows in the head tilt, the pace of movement, small pauses, the light or sensor and the posture; no human facial muscles, no sweating or blushing.",
    "creature": "{n} is a creature: the feeling shows in the posture, the eyes, the breathing, the way the body leans toward or away, and what the limbs do; keep it physical, not human-faced.",
}

# how the same acting reads in each kind of look
FAMILY_WORDS = {
    "photoreal": "Keep it small and truthful, like real footage: micro-expressions, breath, held looks.",
    "3d": "Clear readable poses with soft, weighty motion; the eyes and brows lead.",
    "2d": "Clean readable silhouettes and strong eye and mouth shapes; hold the key pose a beat.",
    "hybrid": "Readable poses; let the drawn parts carry the emotion and the 3D parts the weight.",
    "craft": "Slightly stepped, hand-made motion; small posable-face changes and body tilts carry the feeling.",
    "art": "Let the feeling come through gesture and composition rather than fine facial detail.",
}

EFFORT = re.compile(r"\b(lift\w*|carr(?:y|ies|ied|ying)|heav(?:y|ily)|push\w*|pull\w*|drag\w*|climb\w*|haul\w*|struggl\w*|run\w*|sprint\w*|chas\w*|gasp\w*|exhaust\w*|pant\w*)\b", re.I)
CONTACT = re.compile(r"\b(hug\w*|embrac\w*|handshake|shake[s]? hands?|hold\w* hands?|touch\w*|grab\w*|pass(?:es|ed|ing)?\b|hand(?:s|ed|ing)? (?:over|him|her|them|it)|kiss\w*|help(?:s|ed|ing)? (?:him|her|them) up|carr(?:y|ies|ied|ying) (?:him|her|them))\b", re.I)

EFFORT_LINE = "Show the physical effort: the weight in the shoulders and arms, bracing, effortful breath; the body gives away how hard it is."
CONTACT_LINE = "Show the contact: where hands, arms or bodies meet and how much weight is shared; keep the touch believable and the hands anatomically clear."


def kind_of(d: str, name: str) -> str:
    """The kind of character you chose for this person ('' when none)."""
    from . import character_performance as CP
    k = CP.load(d)["people"].get(name, {}).get("kind", "")
    return k if k in KINDS else ""


def _shot_words(shot: dict) -> str:
    return " ".join(str(shot.get(k) or "") for k in ("description", "action", "performance", "movement", "visual_prompt", "emotion")) + " " + " ".join(
        str(b) for b in (shot.get("beats") or []) if isinstance(b, str))


def categories(shot: dict) -> list[str]:
    """Which extra categories this shot calls for, from its own words: 'effort', 'contact'."""
    text = _shot_words(shot)
    out = []
    if EFFORT.search(text):
        out.append("effort")
    if CONTACT.search(text):
        out.append("contact")
    return out


def text(d: str, shot: dict, family: str = "") -> str | None:
    """One short block for the prompt: the kind channels of the first non-human person in the shot, the look's wording when a kind was chosen, and the effort and contact lines the shot
    calls for. None when none of it applies, so a plain shot of a person costs no prompt room."""
    names = [x for x in shot.get("performers") or [] if isinstance(x, str)][:3]
    parts: list[str] = []
    non_human = [(n, kind_of(d, n)) for n in names]
    non_human = [(n, k) for n, k in non_human if k and k != "human"]
    for n, k in non_human[:2]:
        if CHANNELS.get(k):
            parts.append(CHANNELS[k].format(n=n))
    if non_human and FAMILY_WORDS.get(family):
        parts.append(FAMILY_WORDS[family])
    cats = categories(shot)
    if "effort" in cats:
        parts.append(EFFORT_LINE)
    if "contact" in cats and len(names) >= 2:
        parts.append(CONTACT_LINE)
    return " ".join(parts)[:520] if parts else None


def delivery_hint(d: str, shot_id: str, speaker: str, reads_tags: bool = False) -> dict | None:
    """A starting point for HOW a line is said, from the beats you wrote for the shot and its nudges. A suggestion to read and change, never applied on its own.
    None when you wrote nothing for the shot (a draft is not used)."""
    from . import acting
    try:
        e = acting.load(d)["beats"].get(shot_id) or {}
    except Exception:                                  # noqa: BLE001
        return None
    if e.get("source") != "you":
        return None
    beats = [b for b in e.get("beats") or [] if isinstance(b, dict) and b.get("what")]
    if not beats:
        return None
    first = beats[0]
    nudges = acting.load(d).get("nudges", {}).get(shot_id, {})
    words = []
    if "restrained" in nudges:
        words.append("quiet and held back")
    if "hesitant" in nudges:
        words.append("hesitant, with small pauses")
    if "vulnerable" in nudges:
        words.append("soft, a little unsteady")
    if "tense" in nudges:
        words.append("tight and controlled")
    if "playful" in nudges:
        words.append("light, with a smile in it")
    how = ", ".join(words) or "in step with the acting"
    tag = "[" + (words[0].split(",")[0] if words else "naturally") + "]"
    return {"shot": shot_id, "speaker": speaker, "hint": f"Say it {how}, while the shot has {speaker} {str(first['what']).rstrip('.').lower()}.",
            "tag": tag if reads_tags else None, "from": "your beats" + (" and directions" if words else "")}
