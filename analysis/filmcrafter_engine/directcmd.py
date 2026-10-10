"""The Director Command (Ctrl/Cmd+K): a plain sentence about the shot you are on, turned into a change you look at before it is applied.

It understands everyday phrases: a feeling ("make this more claustrophobic"), a framing, angle or camera move, "move the camera behind her", "John should still be holding the letter",
"use the previous shot's closing state", and "keep ... but ..." to leave parts alone. When it doesn't understand, it says so and shows what it does understand; it never guesses.
Nothing is applied here: it returns the proposed change, and the app applies it only when you press the button.
"""
from __future__ import annotations

import copy
import re

from . import shots

FEELING_WORDS = {"claustrophobic": "Claustrophobic, tense", "tense": "Tense", "scary": "Fear, dread", "frightening": "Fear, dread", "afraid": "Fear", "sad": "Sad, held-back", "lonely": "Lonely",
                 "melancholy": "Sad, quiet", "calm": "Calm", "peaceful": "Peaceful", "warm": "Warm, tender", "tender": "Tender", "intimate": "Intimate", "joyful": "Joy", "happy": "Joy",
                 "playful": "Playful", "angry": "Anger, confrontation", "intense": "Tense, intense"}
MOVE_WORDS = {"handheld": "handheld", "locked off": "locked off", "static": "locked off", "push in": "push in", "pull out": "pull out", "dolly": "dolly", "tracking": "tracking",
              "crane": "crane", "orbit": "orbit", "rack focus": "rack focus"}
ANGLE_WORDS = {"low angle": "low", "high angle": "high", "dutch": "dutch", "overhead": "overhead", "eye level": "eye level", "eye-level": "eye level"}
FRAME_WORDS = {"extreme close-up": "extreme close-up", "extreme close up": "extreme close-up", "close-up": "close-up", "close up": "close-up", "over the shoulder": "over the shoulder",
               "over-the-shoulder": "over the shoulder", "point of view": "point of view", "pov": "point of view", "establishing": "establishing", "wide shot": "wide", "wide": "wide",
               "medium shot": "medium", "medium": "medium", "insert": "insert"}
PARTS = (("performance", ("performance", "acting")), ("camera", ("camera",)), ("lighting", ("lighting", "light")))
HELP = ('Try: "make this shot more claustrophobic", "close-up, low angle, handheld", "move the camera behind her", "John should still be holding the letter", '
        '"use the previous shot\'s closing state", "keep the performance but make it a wide shot".')


def _split_keep(t: str) -> tuple[str, set[str]]:
    """'keep X but Y' / 'keep everything except Y' -> (the part that asks for changes, the parts to leave alone)."""
    m = re.search(r"\bkeep\b(.*)", t)
    if not m:
        return t, set()
    head, tail = t[:m.start()], m.group(1)
    parts = re.split(r"\bbut\b|\bexcept\b", tail, maxsplit=1)
    kept_part, rest = parts[0], (parts[1] if len(parts) > 1 else "")
    keep: set[str] = set()
    if "everything" in kept_part or "all" in kept_part.split():
        keep = {p for p, _ in PARTS}
        for part, words in PARTS:                                  # "everything except the lighting": the named part is the one to change
            if any(w in rest for w in words):
                keep.discard(part)
    else:
        for part, words in PARTS:
            if any(w in kept_part for w in words):
                keep.add(part)
    return (head + " " + rest).strip(), keep


def command(d: str, sid: str, text: str) -> dict:
    c = shots._contract(d, sid)
    t = shots._text(text, 400).lower()
    if not t:
        raise SystemExit("Say what you want changed.")
    body, keep = _split_keep(t)
    patch: dict = {}
    lines: list[str] = []

    def cam(**kw) -> None:
        patch.setdefault("camera", {}).update(kw)

    for w, v in FEELING_WORDS.items():
        if re.search(rf"\b{w}\b", body):
            probe = copy.deepcopy(c)
            probe["performance"]["emotional_intention"] = v
            sug = shots.suggest_for(probe)
            patch.setdefault("performance", {})["emotional_intention"] = v
            cam(**{k: sug["camera"][k] for k in ("angle", "movement", "focus", "lens") if sug["camera"].get(k)}, why=sug["camera"]["why"])
            patch.setdefault("lighting", {}).update({"description": sug["lighting"]["description"], "why": sug["lighting"]["why"]})
            lines += [f"The audience should feel: {v}.", f"Camera: {sug['camera']['angle']} angle, {sug['camera']['movement']}, {sug['camera']['focus']} focus.", f"Light: {sug['lighting']['description']}"]
            break
    for w, v in sorted(FRAME_WORDS.items(), key=lambda x: -len(x[0])):
        if re.search(rf"(?<![a-z-]){re.escape(w)}(?![a-z-])", body):
            cam(framing=v)
            lines.append(f"Framing: {v}.")
            break
    for w, v in ANGLE_WORDS.items():
        if w in body:
            cam(angle=v)
            lines.append(f"Angle: {v}.")
            break
    for w, v in MOVE_WORDS.items():
        if re.search(rf"\b{re.escape(w)}\b", body):
            cam(movement=v)
            lines.append(f"Camera movement: {v}.")
            break
    if re.search(r"\bshallow (depth|focus)", body):
        cam(focus="shallow")
        lines.append("Shallow focus.")
    elif re.search(r"\bdeep (depth|focus)", body):
        cam(focus="deep")
        lines.append("Deep focus.")
    mb = re.search(r"camera (?:to )?behind (?:the )?([a-z']+)", body) or re.search(r"\bbehind (her|him|them)\b", body)
    if mb:
        who = mb.group(1)
        names = [p["name"].title() for p in c["characters"]]
        who = (names[0] if names else "the main character") if who in ("her", "him", "them") else next((n for n in names if n.lower() == who), who.title())
        cam(position=f"Behind {who}", framing="over the shoulder")
        lines.append(f"Camera: behind {who}, over the shoulder.")
    mh = re.search(r"\b([a-z]+) should still be (?:holding|wearing|carrying) (?:the |a |an )?([a-z' ]+?)\s*$", body)
    if mh:
        who, thing = mh.group(1).title(), mh.group(2).strip()
        patch["props"] = list(c["props"]) + [{"name": thing, "prop_id": None, "state": f"held by {who}"}]
        patch["continuity"] = (c["continuity"] + f" {who} is still holding the {thing}.").strip()
        lines.append(f"{who} is still holding the {thing}: added to the props and the continuity notes.")
    if re.search(r"previous shot'?s? (closing|end|last)", body):
        order = shots._index(d)["order"]
        i = order.index(c["id"]) if c["id"] in order else 0
        prev = shots._contract(d, order[i - 1]) if i > 0 else None
        if prev and prev["closing_state"].strip():
            patch["opening_state"] = prev["closing_state"].strip()
            lines.append(f"This shot begins as {prev['id']} ended: \"{prev['closing_state'].strip()[:100]}\".")
        else:
            lines.append("The shot before doesn't say how it ends, so there is nothing to carry over.")
    skipped = [k for k in ("performance", "camera", "lighting") if k in keep and k in patch]
    for k in skipped:
        patch.pop(k)
        lines.append(f"Kept the {k} as it is.")
    if not patch:
        return {"understood": False, "shot": c["id"], "summary": lines, "patch": {}, "skipped": skipped, "help": HELP}
    return {"understood": True, "shot": c["id"], "summary": lines, "patch": patch, "skipped": skipped}
