"""The twelve principles of animation (Frank Thomas and Ollie Johnston, "The Illusion of Life"), turned into direction a picture or video model can follow.

Each principle has plain wording for the person (`plain`) and prompt wording for the model (`video` for a moving shot, `still` for the first frame). For each shot, a few that fit what happens in it are chosen
(a jump gets anticipation and squash and stretch; a coat in the wind gets follow-through), so the prompt stays short and never lists all twelve.

Which principles apply depends on the look. Drawn and 3D looks use most of them; stop motion and clay use fewer; photorealistic live action keeps only the ones that are also good acting and camera
craft (staging, timing, secondary action, easing). The person can switch any of them on or off for the film (Rules & style); nothing is applied that they turned off.

Pure text: free, deterministic, nothing is sent anywhere.
"""
from __future__ import annotations

import re

FAMILIES = ("photoreal", "3d", "2d", "hybrid", "craft", "art")
FAMILY_NAMES = {"photoreal": "Photorealistic", "3d": "3D animation", "2d": "2D animation", "hybrid": "Hybrid 2D/3D", "craft": "Hands-on crafts", "art": "Art movements & experimental"}
FAMILY_BLURB = {
    "photoreal": "Looks like it was filmed: real light, real skin, real places.",
    "3d": "Computer-made characters and worlds, from storybook to cel-shaded.",
    "2d": "Drawn and painted: classic hand-drawn, anime, comic and watercolour.",
    "hybrid": "Mixed worlds: 3D with drawn accents, collage, paper theatre, parallax.",
    "craft": "Made by hand and shot frame by frame: stop motion, clay, paper, miniatures.",
    "art": "Painting movements, print and folk art, and experimental graphic looks.",
}

_STYLES: dict | None = None


def styles() -> dict:
    """styles.json by id (read once). Each look has a 'family' (photoreal, 3d, 2d, hybrid, craft, art, genre or auto)."""
    global _STYLES
    if _STYLES is None:
        import json
        import os
        with open(os.path.join(os.path.dirname(__file__), "styles.json"), encoding="utf-8") as f:
            _STYLES = {x["id"]: x for x in json.load(f)["styles"]}
    return _STYLES


def style_family(look_id: str) -> str:
    """The look's family as chosen in the picker: photoreal | 3d | 2d | hybrid | craft | art, or genre / auto."""
    return (styles().get(look_id or "") or {}).get("family", "auto")


def family(look_id: str) -> str:
    """Which set of principles applies: photoreal | 3d | craft | 2d. Drawn, hybrid, art and unknown looks count as 2D."""
    f = style_family(look_id)
    return f if f in ("photoreal", "3d", "craft") else "2d"


def P(id, name, plain, video, still, keywords, live=False, always=False, fams=("3d", "2d", "craft")):
    return dict(id=id, name=name, plain=plain, video=video, still=still, keywords=keywords, live=live, always=always, fams=list(fams))


PRINCIPLES = [
    P("squash-stretch", "Squash and stretch", "Soft things flatten on impact and lengthen in fast motion, keeping their volume. It gives weight and life.",
      "Soft bodies and objects squash on impact and stretch in fast motion while keeping their volume; the amount suits the style.",
      "The pose shows weight: a body compressing before a jump or lengthening in a reach, with its volume kept.",
      ["jump", "land", "bounce", "hit", "fall", "run", "throw", "ball", "fast", "leap", "slam", "drop"]),
    P("anticipation", "Anticipation", "A small move in the opposite direction prepares the big one: a crouch before a jump, a breath before a word.",
      "Each big move is prepared by a small opposite move first (a crouch before a jump, a breath before a word, a glance before a step), so the audience sees it coming.",
      "The pose is caught in the moment of preparation, just before the main action.",
      ["jump", "turn", "reach", "grab", "throw", "run", "stand", "speak", "say", "lunge", "kick", "spin", "start", "begin", "rise"], live=True),
    P("staging", "Staging", "One idea reads at once: a clear silhouette, the important thing clearest, nothing competing.",
      "Staged so one idea reads instantly: a strong silhouette, the important thing clearest, nothing in the frame competing with it.",
      "Staged so one idea reads instantly: a strong silhouette, the subject clearly the most important thing, nothing competing.",
      [], live=True, always=True, fams=("photoreal", "3d", "2d", "craft")),
    P("pose-to-pose", "Pose to pose", "Strong key poses first, then the in-between frames. Movements stay clear and designed.",
      "The movement passes through strong, clear key poses with smooth in-between motion, designed rather than random.",
      "A strong, clear key pose, the kind an animator would draw first.",
      ["dance", "fight", "gesture", "pose", "wave", "bow", "salute", "step"]),
    P("follow-through", "Follow-through and overlapping action", "When a move stops, loose parts (hair, cloth, a tail) keep going a beat longer and settle at different times.",
      "When a move stops, loose parts (hair, cloth, tails, straps, hands) keep moving a beat longer and settle at different times, so nothing stops all at once.",
      "Loose parts (hair, cloth) trail the body's move: they show where it came from.",
      ["hair", "cloth", "dress", "coat", "scarf", "cape", "wind", "stop", "land", "walk", "turn", "skirt", "cloak", "ribbon", "tail"], live=True),
    P("slow-in-out", "Slow in and slow out", "Movements ease in and out: gentle start, quick middle, soft landing. Nothing moves at one constant speed.",
      "Movement eases in and out: it starts gently, is quickest in the middle and settles softly, never at one mechanical constant speed.",
      "", [], live=True, always=True, fams=("photoreal", "3d", "2d", "craft")),
    P("arcs", "Arcs", "Natural movement travels along curves: a swinging arm, a turning head. Straight lines look mechanical.",
      "Natural motion travels along smooth arcs (a swinging arm, a turning head, a thrown object, a reaching hand), never in stiff straight lines.",
      "Limbs and the head are posed along flowing curves.",
      ["swing", "throw", "wave", "turn", "reach", "arm", "head", "hand", "toss", "dance", "pour", "sweep"], live=True),
    P("secondary-action", "Secondary action", "A small extra action supports the main one: a blink, a breath, a fidget. It adds life without stealing focus.",
      "A small secondary action supports the main one (a blink, a breath, a fidget, a glance away and back) without stealing focus.",
      "A small detail of life: a slightly parted mouth, a hand halfway through a fidget.",
      ["sit", "wait", "listen", "talk", "speak", "say", "think", "look", "stand", "watch"], live=True, always=True, fams=("photoreal", "3d", "2d", "craft")),
    P("timing", "Timing", "How long a moment lasts says what it means: heavy things are slow, light things fast, a held beat makes a decision felt.",
      "Timing carries the meaning: heavy things move slowly and light things quickly, and the important beat is held a moment before the next one.",
      "", [], live=True, always=True, fams=("photoreal", "3d", "2d", "craft")),
    P("exaggeration", "Exaggeration", "Push poses and faces a little past real life so the feeling reads clearly, while staying believable.",
      "Poses and expressions are pushed a little past real life so the feeling reads clearly, but stay believable.",
      "The pose and expression are pushed a little past real life so the feeling reads at a glance, but stay believable.",
      ["surprise", "angry", "joy", "shock", "scream", "laugh", "excited", "fear", "terrified", "furious", "delighted", "comic", "funny", "gasp"]),
    P("solid-drawing", "Solid drawing", "Bodies have weight and volume in three dimensions, and stay consistent from every angle.",
      "Bodies keep their weight, volume and proportions from every angle, with clear form and believable balance.",
      "The figure has clear three-dimensional form, balanced weight and consistent proportions.",
      [], always=True, fams=("3d", "2d", "craft")),
    P("appeal", "Appeal", "Characters are easy to read and good to look at: clear shapes, a face that holds interest, a design that stays the same.",
      "Characters stay appealing and easy to read: clear shapes, an expressive face, and a design that stays exactly the same.",
      "Characters are appealing and easy to read: clear shapes, an expressive face, a design that stays consistent.",
      [], live=True, always=True, fams=("photoreal", "3d", "2d", "craft")),
]
BY_ID = {p["id"]: p for p in PRINCIPLES}
IDS = tuple(p["id"] for p in PRINCIPLES)

# what each family switches on to begin with (the person can change it)
_CRAFT = {"anticipation", "staging", "follow-through", "slow-in-out", "secondary-action", "timing", "solid-drawing", "appeal", "arcs"}
_LIVE = {p["id"] for p in PRINCIPLES if p["live"]}


def defaults(look_id: str) -> list[str]:
    fam = family(look_id)
    if fam == "photoreal":
        return [i for i in IDS if i in _LIVE]
    if fam == "craft":
        return [i for i in IDS if i in _CRAFT]
    return [i for i in IDS if i != "pose-to-pose"]


def catalog(look_id: str) -> list[dict]:
    """The twelve for the Rules & style screen: what each is, whether it suits this look, and whether it is on by default."""
    fam = family(look_id)
    on = set(defaults(look_id))
    return [{"id": p["id"], "name": p["name"], "plain": p["plain"], "fits": fam in p["fams"] or (fam == "photoreal" and p["live"]), "default": p["id"] in on} for p in PRINCIPLES]


def clean(value) -> list[str] | None:
    """A saved selection made safe: only real ids, in the standard order. None (not set) means 'use the style's defaults'."""
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        raise SystemExit("The animation principles must be a list.")
    keep = {str(v) for v in value}
    return [i for i in IDS if i in keep]


def _shot_text(shot: dict) -> str:
    bits = [str(shot.get(k) or "") for k in ("visual_prompt", "description", "performance", "movement", "emotion", "choreography")]
    bits += [str(x) for x in (shot.get("beats") or [])]
    return " ".join(bits).lower()


def pick(project: dict, shot: dict, look_id: str, video: bool, limit: int | None = None) -> list[str]:
    """The principles that fit this shot and are switched on: the ones its words call for, then the ones that always help, up to a few."""
    chosen = (project.get("animation") or {}).get("principles")
    selected = list(defaults(look_id) if chosen is None else chosen)
    fam = family(look_id)
    text = _shot_text(shot)
    quiet = (project.get("performance") or {}).get("default") in ("restrained", "natural")      # a quiet acting profile and "push the poses" would pull against each other
    scored = []
    for n, p in enumerate(PRINCIPLES):
        if p["id"] not in selected:
            continue
        if quiet and chosen is None and p["id"] == "exaggeration":
            continue
        if fam == "photoreal" and not p["live"]:
            continue
        if not (p["video"] if video else p["still"]):
            continue
        hits = sum(1 for k in p["keywords"] if re.search(rf"\b{re.escape(k)}", text))
        if not hits and not p["always"]:
            continue
        scored.append((-(hits * 2 + (1 if p["always"] else 0)), n, p["id"]))
    scored.sort()
    cap = limit if limit is not None else (4 if video else 3)
    return [i for _, _, i in scored[:cap]]


def direction(project: dict, shot: dict, look_id: str, video: bool) -> str:
    """One short block for the prompt, or "" when nothing is switched on or nothing fits."""
    ids = pick(project, shot, look_id, video)
    if not ids:
        return ""
    parts = [BY_ID[i]["video" if video else "still"].rstrip(".") + "." for i in ids]
    head = "Animation craft: " if family(look_id) != "photoreal" else "Screen craft: "
    return head + " ".join(parts)
