"""Keeping a project in its chosen look: no drift to photorealism.

A project that says "feature 3D animation" can still end up with photographs, because the rest of a prompt keeps pulling the other way: a script's own VISUAL STYLE line ("cinematic
contemporary African realism"), the Director's shot wording ("photographic, 35mm film grain"), a Bible's world text ("realistic Lagos"). Image models weigh those words heavily, and the
Look is one sentence among many. The guard does two things for a stylised look (anything but photoreal CGI and live action):

  * it rewrites words that ask for a photograph in the text that comes from elsewhere (script style, Director wording, Bible), keeping the rest of the meaning, and
  * it adds one "style lock" sentence that is the last thing dropped when a prompt is too long, naming the look and what it is not.

The look chosen in the project always has the last word. Switch it off with `look.guard: false` in project.json.
"""
from __future__ import annotations

import re

REAL_LOOKS = {"photoreal-cgi", "live-action"}      # these ask for real-looking pictures: nothing is rewritten
UNSURE_LOOKS = {"auto", "custom", ""}               # "match the references": the references decide, so nothing is rewritten

# words that ask for a photograph, and what to say instead ("" drops the word)
REALIST = [
    (r"photo-?realism", "naturalistic detail"), (r"photo-?realistic(?:ally)?", ""), (r"hyper-?realistic", ""), (r"hyper-?realism", ""),
    (r"cinematic realism", "cinematic grounding"), (r"realism", "grounding"), (r"realistically", "believably"), (r"realistic", "believable"),
    (r"live[- ]action", ""), (r"documentary(?:[- ]style| footage| look)?", ""), (r"photographic(?:ally)?", ""), (r"photograph(?:s|y)?", ""),
    (r"film grain", ""), (r"(?:35|16|70) ?mm film(?: stock)?", ""), (r"shot on (?:arri|red|film|a cinema camera)\w*", ""), (r"dslr", ""),
    (r"skin pores", "skin detail"), (r"real actors", "the characters"), (r"real locations", "the locations"),
]
_RX = [(re.compile(r"\b" + p + r"\b", re.I), r) for p, r in REALIST]

LOCK_PRIORITY = 11            # above every other block (the highest of those is 10), so a prompt that has to be cut loses anything else first


def family(look_id: str | None) -> str:
    """'real' (asks for real-looking pictures), 'unsure' (match the references) or 'stylised' (a drawn, modelled or crafted look)."""
    lid = (look_id or "").lower()
    if lid in REAL_LOOKS:
        return "real"
    if lid in UNSURE_LOOKS:
        return "unsure"
    return "stylised"


def on(project: dict, look_id: str | None) -> bool:
    look = (project or {}).get("look")
    off = isinstance(look, dict) and look.get("guard") is False
    return family(look_id) == "stylised" and not off


def _tidy(text: str) -> str:
    out = re.sub(r"\s+([,.;:])", r"\1", text)                                      # "a  , b" -> "a, b"
    out = re.sub(r"([,;:])\s*([,;:.])", r"\2", out)                                # ", ," -> ","
    out = re.sub(r"\(\s*\)", "", out)
    out = re.sub(r"\b(a|an|the),\s+", r"\1 ", out, flags=re.I)                     # "A, believable close-up" -> "A believable close-up"
    out = re.sub(r"\b(with|and|or|of)\s+(and|or)\b", r"\1", out, flags=re.I)       # "with and visible skin" -> "with visible skin"
    out = re.sub(r"\b(with|of)\s+(?=[,.;])", "", out, flags=re.I)                  # "with." -> "."
    return re.sub(r"\s{2,}", " ", out).strip()


def sanitize(text: str, project: dict, look_id: str | None) -> str:
    """The text with every request for a photograph reworded or removed, when the guard is on for this project; otherwise unchanged."""
    if not text or not on(project, look_id):
        return text
    out = str(text)
    for rx, repl in _RX:
        out = rx.sub(repl, out)
    return _tidy(out)


def lock(project: dict, look: dict) -> str | None:
    """The style-lock sentence for a stylised look (the last thing dropped from a prompt), or None."""
    if not on(project, look.get("id")):
        return None
    lead = str(look.get("prompt") or "").split(":")[0].rstrip(".").strip()
    avoid = str(look.get("avoid") or "").strip().rstrip(".")
    base = f"Style lock: {lead}. This is not a photograph and not live-action footage."
    return base + (f" Never: {avoid}." if avoid else "")
