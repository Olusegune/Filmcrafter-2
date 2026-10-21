"""Which pictures from a character's sheets go to which shot.

A character can have many pictures: a turnaround, front, side and back views, a set of expressions, a set of poses, outfits. Sending all of them to every shot wastes the few reference
slots a video model has, and an angry face sent to a calm shot pulls the picture the wrong way. So:

  identity   the pictures that say WHO the person is (turnaround, front, three-quarter, side, back): sent for every shot the person is in, at most `IDENTITY_MAX`
  moment     an expression, pose or outfit picture: sent only for a shot whose words match what the picture shows (a "worried" picture for a shot where she is worried,
             a "sitting" picture for a shot where she sits, a "red coat" picture for a shot that names the red coat), at most one of each kind per person per shot

What a picture shows is read from the words in its label and file name (`worried`, `sitting`, `red coat`): nothing is looked at, nothing is sent anywhere, and a picture whose
words match nothing is kept as an identity picture only if there is room, never thrown away. Pure text: free and deterministic.
"""
from __future__ import annotations

import os
import re

IDENTITY_MAX = 4
IDENTITY_ORDER = ("master", "front", "three-quarter", "side", "back", "reference", "other", "expression", "pose", "wardrobe")
MOMENT_KINDS = ("expression", "pose", "wardrobe")

# words that mean the same thing, so "anxious" in a shot finds a picture named "worried"
CONCEPTS: dict[str, tuple[str, ...]] = {
    "worried": ("worried", "worry", "anxious", "anxiety", "nervous", "afraid", "fear", "fearful", "scared", "frightened", "uneasy", "tense", "dread", "panic"),
    "angry": ("angry", "anger", "rage", "furious", "fury", "mad", "livid", "irate", "enraged", "enrage", "incensed", "snarl", "scowl", "glare", "shouting"),
    "sad": ("sad", "sadness", "cry", "crying", "tears", "tearful", "grief", "grieving", "sorrow", "mourning", "weeping", "heartbroken", "despair"),
    "happy": ("happy", "joy", "joyful", "smile", "smiling", "laugh", "laughing", "delighted", "cheerful", "grin", "grinning", "glad", "elated"),
    "surprised": ("surprised", "surprise", "shock", "shocked", "stunned", "startled", "astonished", "gasp"),
    "calm": ("calm", "serene", "peaceful", "relaxed", "composed", "neutral", "still"),
    "determined": ("determined", "resolve", "resolved", "defiant", "defiance", "steely", "fierce", "focused", "stern"),
    "tired": ("tired", "exhausted", "weary", "sleepy", "drained", "spent"),
    "disgust": ("disgust", "disgusted", "revulsion", "contempt", "scorn", "sneer"),
    "tender": ("tender", "love", "loving", "affection", "warm", "gentle", "soft", "fond"),
    "sitting": ("sitting", "sit", "sits", "seated", "sat", "perched"),
    "standing": ("standing", "stand", "stands", "stood", "upright"),
    "walking": ("walking", "walk", "walks", "strolling", "stride", "striding", "pacing", "paces"),
    "running": ("running", "run", "runs", "ran", "sprint", "sprints", "sprinting", "sprinted", "dash", "dashes", "dashing", "chasing", "fleeing", "flees", "fled", "racing", "races", "raced"),
    "kneeling": ("kneeling", "kneel", "kneels", "knelt", "crouching", "crouch", "crouches"),
    "lying": ("lying", "lies", "lie", "asleep", "sleeping", "reclining", "collapsed", "fallen"),
    "fighting": ("fighting", "fight", "punch", "punching", "kick", "kicking", "strike", "striking", "brawl", "combat", "block", "dodge"),
    "reaching": ("reaching", "reach", "reaches", "grabbing", "grab", "grabs", "pointing", "point", "points"),
    "jumping": ("jumping", "jump", "jumps", "leaping", "leap", "leaps", "vault"),
    "embracing": ("embracing", "hug", "hugging", "hugs", "embrace", "holding"),
    "looking": ("looking", "gaze", "gazing", "stare", "staring", "watching", "peering"),
}
_WORD = {w: c for c, ws in CONCEPTS.items() for w in ws}
_NOISE = {"the", "a", "an", "of", "and", "or", "in", "on", "with", "view", "sheet", "ref", "reference", "expression", "expressions", "pose", "poses", "outfit", "wardrobe", "costume",
          "front", "side", "back", "master", "img", "image", "pic", "picture", "final", "new", "v1", "v2", "v3", "copy"}


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", str(text or "").lower()) if t]


def concepts(text: str) -> set[str]:
    """The feelings and poses a piece of text is about, by the words it uses."""
    return {_WORD[t] for t in _tokens(text) if t in _WORD}


def words(text: str) -> set[str]:
    """The plain words of a label that are not noise or numbers (an outfit's name: 'red', 'coat')."""
    return {t for t in _tokens(text) if t not in _NOISE and not t.isdigit() and len(t) > 2 and t not in _WORD}


def label_text(m: dict) -> str:
    stem = os.path.splitext(os.path.basename(str(m.get("path") or "")))[0]
    return f"{m.get('label') or ''} {stem}"


def identity(media: list[dict], limit: int = IDENTITY_MAX) -> list[dict]:
    """The pictures that say who the person is, best first: the turnaround and the main views before anything else, then whatever is left (a moment picture only fills a free place)."""
    def rank(m):
        k = m.get("kind") or "reference"
        return IDENTITY_ORDER.index(k) if k in IDENTITY_ORDER else len(IDENTITY_ORDER)
    pool = sorted(media, key=rank)
    ident = [m for m in pool if (m.get("kind") or "reference") not in MOMENT_KINDS][:limit]
    if len(ident) < limit:                                       # no room is wasted: a moment picture with no matching words still helps as a face
        ident += [m for m in pool if m not in ident and not (concepts(label_text(m)) or (m.get("kind") == "wardrobe" and words(label_text(m))))][:limit - len(ident)]
    return ident[:limit]


def moment_candidates(media: list[dict]) -> list[dict]:
    """The expression, pose and outfit pictures that say what they show in their words, each with the concepts (or outfit words) it matches."""
    out = []
    for m in media:
        k = m.get("kind")
        if k not in MOMENT_KINDS:
            continue
        txt = label_text(m)
        c, w = concepts(txt), words(txt)
        if k == "wardrobe" and w:
            out.append({"media": m, "kind": k, "concepts": set(), "words": w})
        elif c:
            out.append({"media": m, "kind": k, "concepts": c, "words": set()})
    return out


def shot_text(c: dict) -> str:
    """What a shot says about the moment: what happens, how it is played, what the person says and how."""
    perf = c.get("performance") or {}
    bits = [c.get("title"), c.get("story_purpose"), c.get("action"), c.get("blocking"), c.get("opening_state"), c.get("closing_state"), perf.get("emotional_intention"), perf.get("micro_animation")]
    for b in perf.get("beats") or []:
        bits += [b.get("what"), b.get("subtext"), b.get("start"), b.get("turn"), b.get("end"), b.get("want"), b.get("fear")]
    for d in c.get("dialogue") or []:
        bits += [d.get("paren")]
    return " ".join(str(x) for x in bits if x)


def pick_for_shot(candidates: list[dict], text: str) -> list[dict]:
    """At most one picture of each kind for this shot: the one whose words match the shot best. A picture is only sent when something really matches."""
    sc, sw = concepts(text), set(_tokens(text))
    best: dict[str, tuple[int, dict]] = {}
    for cand in candidates:
        score = len(cand["concepts"] & sc) * 2 + len(cand["words"] & sw)
        if cand["kind"] == "wardrobe" and cand["words"] and not (cand["words"] <= sw or len(cand["words"] & sw) * 2 > len(cand["words"])):
            score = 0                                              # an outfit is sent when the shot names it, not on one shared word like "red"
        if score > 0 and score > best.get(cand["kind"], (0, None))[0]:
            best[cand["kind"]] = (score, cand)
    return [v[1] for v in best.values()]
