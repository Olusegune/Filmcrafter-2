"""Help for writing the prompt of a start-and-end-frame shot: recipes for the shots only two frames make possible, a checker that says what is likely to go wrong, and a writer
that turns a plain description into a prompt that works (with the AI brain when there is one, with a careful template when there isn't).

A model that is given a first and a last picture already knows where the shot starts and where it ends. What it needs from the words is what HAPPENS between them: one clear cause
and effect, in order, at a pace that fits the seconds. The best prompts say that and nothing else. The common mistakes are describing only the pictures, packing in more events than
the seconds hold, telling the model what NOT to do, and putting words in quotes (which models like to draw as written text).

  recipes(shot)          ready-made descriptions of common transitions, with the shot's people filled in
  lint(text, ctx)        what is likely to go wrong with this prompt (free; runs as you type)
  write(d, shot, intent) a prompt from your own plain words
"""
from __future__ import annotations

import json
import os
import re

CHANGE_VERBS = re.compile(r"\b(becomes?|turns?|turning|dissolv\w*|fad\w+|opens?|opening|walks?|moves?|moving|rises?|rising|falls?|falling|grows?|growing|appears?|disappear\w*|vanish\w*|glows?|glowing|spreads?|"
                          r"melts?|morphs?|transforms?|shifts?|slides?|reaches?|lifts?|drops?|spins?|steps?|leans?|embraces?|hugs?|kisses?|smiles?|closes?|blooms?|absorb\w*|merges?|swirls?|flows?|"
                          r"scatters?|burns?|lights?|sweeps?|pulls?|pushes?|runs?|dances?|looks?|stands?|sits?|ages?|grows? (?:old|up)|shrinks?|unfolds?)\b", re.I)
NEGATIONS = re.compile(r"\b(no|not|don'?t|doesn'?t|never|without|nothing|avoid|can'?t|won'?t)\b", re.I)
SEQUENCE = re.compile(r"\b(then|next|after that|afterwards|suddenly|finally|meanwhile|as soon as|until|before)\b", re.I)
CUTS = re.compile(r"\b(cut to|cuts to|scene change|new scene|jump cut|montage|split screen)\b", re.I)
VANISH = re.compile(r"\b(disappear\w*|vanish\w*|dissolv\w*|fades? away|fades? out|melts? away|evaporat\w*)\b", re.I)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s.strip()]


def lint(text: str, ctx: dict | None = None) -> list[dict]:
    """What is likely to go wrong with this prompt. [{level: "problem"|"warn"|"tip", text}], most important first. Pure."""
    ctx = ctx or {}
    t = (text or "").strip()
    out: list[dict] = []
    add = lambda level, msg: out.append({"level": level, "text": msg})
    seconds = float(ctx.get("seconds") or 0)
    limit = int(ctx.get("limit") or 0)
    if not t:
        add("problem", "Nothing written yet. Say what happens between the first picture and the last.")
        return out
    if len(t) < 25:
        add("warn", "Very short. Say what happens, in order, between the two pictures: who does what, and what changes.")
    if limit:
        n = len(t.encode("utf-8"))
        if n > limit:
            add("problem", f"{n} characters; this model takes {limit}. The end would be cut off.")
        elif n > limit * 0.9:
            add("warn", f"{n} of {limit} characters: very close to this model's limit.")
    if not CHANGE_VERBS.search(t):
        add("warn", "It describes how things look but not what happens. The two pictures already show the look; use the words for the change between them.")
    if CUTS.search(t):
        add("problem", "One take cannot cut. Describe one continuous movement from the first picture to the last.")
    if len(NEGATIONS.findall(t)) >= 3:
        add("warn", "Mostly things NOT to do. Models often do what the words name, so say what you want to see instead.")
    if re.search(r"[\"“”][^\"“”]{2,}[\"“”]", t) and not ctx.get("speech"):
        add("warn", "Words in quotes may be drawn on the picture as written text. Describe the action instead, or leave the quote out.")
    if seconds:
        beats = 1 + len(SEQUENCE.findall(t)) + max(0, len([s for s in _sentences(t) if CHANGE_VERBS.search(s)]) - 1)
        if beats > seconds * 0.9 + 1:
            add("warn", f"About {beats} separate things happen in {seconds:g} seconds. The model will rush or skip some. Keep the ones that matter, or make the shot longer.")
    if VANISH.search(t) and not re.search(r"\b(into|toward|towards|absorb\w*|merg\w*|inside|through|behind|away)\b", t, re.I):
        add("tip", "Something vanishes. Say where it goes or what takes its place (into light, into the other person, out of frame): a clear cause makes a smooth change.")
    if ctx.get("has_end") and ctx.get("end_state"):
        words = [w for w in re.findall(r"[a-z]{5,}", str(ctx["end_state"]).lower())][:8]
        if words and not any(w in t.lower() for w in words):
            add("tip", "Your description of how the shot ends isn't reflected in this prompt. The last picture shows it, but the words should lead there.")
    if not out:
        add("tip", "Looks good: it says what happens, in order, and fits the length.")
    rank = {"problem": 0, "warn": 1, "tip": 2}
    return sorted(out, key=lambda x: rank[x["level"]])


# ---------------------------------------------------------------- recipes

# {A} is the person or thing that changes, {B} the other person or place in the shot
RECIPES = [
    {"id": "absorb", "title": "Dissolves into light, absorbed", "blurb": "One figure dissolves into a bright light that is drawn into another (a farewell, a memory, a spirit).",
     "text": "{A} and {B} stand close, {A} held in {B}'s arms. A soft, bright light begins to glow in {B}'s chest and slowly grows. {A} dissolves into the light, which is drawn gently into {B}'s chest. The glow fades until only {B} remains, still and calm."},
    {"id": "age", "title": "Ages in front of us", "blurb": "The same person, older, with no cut: time passes on their face.",
     "text": "{A} stays in place, looking ahead. Slowly and continuously, time passes on {A}'s face: the skin lines, the hair greys, the eyes grow tired and wise. The pose, the clothes and the background stay the same; only the years change."},
    {"id": "dissolve", "title": "Turns into particles", "blurb": "A figure breaks into drifting particles (ash, petals, sparks, mist) and is gone.",
     "text": "{A} stands still. Their edges begin to break into small drifting particles that lift and scatter on the air, until the whole figure has become a cloud that thins to nothing. {B} and the background do not move."},
    {"id": "approach", "title": "Walks into the close-up", "blurb": "A person walks toward the camera and ends in a close-up on the last picture.",
     "text": "{A} walks steadily toward the camera. The camera holds still and the frame fills with {A} until the shot settles on their face, calm and direct."},
    {"id": "turn", "title": "Turns to face us", "blurb": "A person turns from the background toward the camera.",
     "text": "{A} slowly turns from the window toward the camera, the light moving across their face, until they look straight into the lens."},
    {"id": "appear", "title": "Something appears", "blurb": "An object or person fades into an empty place.",
     "text": "The place is empty and quiet. Gradually, light gathers in the middle of the frame and {A} takes shape there, solid and still, as if they had always been standing in it."},
    {"id": "reach", "title": "Reaches out and touches", "blurb": "Two hands, two people, or a person and an object come together.",
     "text": "{A} reaches slowly toward {B}. Their hands meet and hold. The camera stays steady as the moment settles."},
    {"id": "match", "title": "Move smoothly to the last picture", "blurb": "No special event: the shot simply moves from the first picture to the last.",
     "text": "A single continuous movement from the first frame to the last: {A} moves naturally from where they start to where they end, with the same people, clothes, place and light throughout."},
]


def _names(shot: dict) -> tuple[str, str]:
    p = [str(x) for x in (shot.get("performers") or []) if x]
    return (p[0] if p else "the first person"), (p[1] if len(p) > 1 else "the other person")


def recipes(shot: dict) -> list[dict]:
    """The recipes with the shot's people filled in (generic words when the shot names fewer than two)."""
    a, b = _names(shot)
    return [{"id": r["id"], "title": r["title"], "blurb": r["blurb"], "text": r["text"].replace("{A}", a).replace("{B}", b)} for r in RECIPES]


def recipe_for(intent: str) -> str | None:
    """The recipe a plain description is most like, if any."""
    t = (intent or "").lower()
    light = re.search(r"\b(light|glow|glowing|bright|radiance)\b", t)
    if VANISH.search(t) and light:
        return "absorb"
    if re.search(r"\b(older|aged?|years|grow(?:s|n)? old|elderly|younger)\b", t) and re.search(r"\b(becomes?|turns? into|changes?|morphs?|time|ages?)\b", t):
        return "age"
    if re.search(r"\b(ash|petals?|sparks?|particles?|dust|mist|smoke)\b", t) and (VANISH.search(t) or re.search(r"\b(turns? (?:to|into)|drifts? away|scatter\w*|crumbl\w*|blows? away|breaks? (?:apart|into))\b", t)):
        return "dissolve"
    return None


# ---------------------------------------------------------------- writing

SYSTEM = (
    "You write the text prompt for an AI video model that is given a FIRST picture and a LAST picture and must animate between them. The pictures already show how the shot looks at the "
    "start and the end, so do not describe their look at length. Describe what HAPPENS between them: one clear cause and effect, in order, at a pace that fits the number of seconds. "
    "Rules: plain present tense; use the characters' names exactly as given and never re-describe their faces, clothes or the place; one continuous take with no cuts; say what you want to "
    "see rather than what to avoid; no quotation marks; no on-screen text; at most one significant event per two seconds; if something vanishes say where it goes or what takes its "
    "place; end on the final picture's state. Keep to the character limit given. Answer in JSON with: prompt (the text), why (one sentence on how you read the description), and tips "
    "(0 to 3 short suggestions to make the shot work better, such as making the shot longer or choosing a different end picture).")
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["prompt", "why", "tips"],
          "properties": {"prompt": {"type": "string"}, "why": {"type": "string"}, "tips": {"type": "array", "items": {"type": "string"}}}}


def context(d: str, shot_id: str) -> dict:
    """What is known about the shot that the writer needs. Free."""
    from . import frames
    from .planio import find_shot, load_plan
    name, plan = load_plan(d)
    sh, _sc = find_shot(plan, shot_id)
    try:
        fr = frames.get(d, [shot_id])[shot_id]
    except SystemExit:
        fr = {}
    seconds = round(float(sh.get("end", 0)) - float(sh.get("start", 0)), 1)
    return {"shot": shot_id, "performers": sh.get("performers") or [], "beats": sh.get("beats") or [], "emotion": sh.get("emotion", ""), "framing": sh.get("framing", ""),
            "seconds": seconds, "has_start": bool(fr.get("start")), "has_end": bool(fr.get("end")), "end_state": fr.get("end_state", "")}


def template(intent: str, ctx: dict) -> dict:
    """A careful prompt from plain words, with no AI: a matching recipe when the description is like one, else the description cleaned into ordered sentences."""
    a, b = _names({"performers": ctx.get("performers")})
    rid = recipe_for(intent)
    if rid:
        r = next(x for x in RECIPES if x["id"] == rid)
        return {"prompt": r["text"].replace("{A}", a).replace("{B}", b), "why": f"Your description is like “{r['title']}”, so this starts from that recipe with the shot's people filled in. Edit the names and details to match.", "tips": []}
    parts = [p.strip(" ,;") for p in re.split(r"[.;]|,?\s+(?:and then|then|after that|and)\s+", intent or "") if p and p.strip(" ,;")]
    words = ["", "Then ", "Then ", "Finally, "]
    sentences = [(words[min(i, len(words) - 1)] + (p[0].lower() + p[1:] if i and p else p[:1].upper() + p[1:] if p else p)).rstrip(".") + "." for i, p in enumerate(parts)]
    if ctx.get("end_state"):
        sentences.append(f"The shot ends with {str(ctx['end_state']).strip().rstrip('.')}.")
    sentences.append("The movement is smooth and continuous from the first picture to the last.")
    return {"prompt": " ".join(sentences), "why": "Your description put into order, one event at a time. (No AI brain is set up, so this is a careful template; set one in Settings for a full rewrite.)", "tips": []}


def write(d: str, shot_id: str, intent: str, limit: int = 0) -> dict:
    """A prompt from the filmmaker's own plain words. Uses the AI brain when one is set up (free on a local model; the price is small and the same as other writing), else the template."""
    intent = (intent or "").strip()[:2000]
    if not intent:
        raise SystemExit("Describe in your own words what happens in the shot.")
    ctx = {**context(d, shot_id), "limit": limit or 0}
    out = None
    source = "template"
    try:
        from .director import _client, DEFAULT_MODEL, resolve_model
        from .llm import config
        c = _client()
        model = resolve_model(c, DEFAULT_MODEL)
        brief = {"description": intent, "characters_in_the_shot": ctx["performers"], "seconds": ctx["seconds"], "has_first_picture": ctx["has_start"], "has_last_picture": ctx["has_end"],
                 "how_the_shot_ends": ctx["end_state"], "character_limit": limit or 1500, "mood": ctx["emotion"]}
        resp = c.responses.create(model=model, input=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(brief, ensure_ascii=False)}],
                                  text={"format": {"type": "json_schema", "name": "frame_prompt", "schema": SCHEMA, "strict": True}})
        j = json.loads(resp.output_text)
        if isinstance(j.get("prompt"), str) and j["prompt"].strip():
            out = {"prompt": j["prompt"].strip(), "why": str(j.get("why") or ""), "tips": [str(t) for t in (j.get("tips") or [])][:3]}
            source = "ai"
    except BaseException as e:                       # no key, no local model, a refusal or a network fault: the template still helps; never lose the user's words
        if isinstance(e, KeyboardInterrupt):
            raise
    if out is None:
        out = template(intent, ctx)
    if limit and len(out["prompt"].encode("utf-8")) > limit:
        out["prompt"] = out["prompt"].encode("utf-8")[:limit].decode("utf-8", "ignore").rsplit(" ", 1)[0].rstrip(",;") + "."
    return {**out, "source": source, "issues": lint(out["prompt"], ctx)}
