"""Action choreography: a fight, a chase or a sports moment planned beat by beat as shots a video model can really make.

Video models are good at one clear thing in a short shot and poor at long, precise, many-person physical sequences. So this plans an action scene the way an action editor cuts it: the geography
first, then short shots where one thing happens (a swing, a dodge, a hand on a rail), each followed by the reaction or a cutaway, with the momentum swinging from one side to the other and ending where
the story needs it. A blow and its landing are separate shots (the cut sells the contact; the model never has to draw two bodies colliding), and what each person is carrying (a split lip, a torn sleeve,
a limp) is carried forward so the next shot stays the same person.

  types      the kinds of action scene it can plan, with what each is good for
  generate   a plan for a scene: the beats, their camera, length, sound and who has the upper hand. Free and deterministic: the same inputs give the same plan. Nothing is sent anywhere.
  update     change a beat's words, length or camera, or the opening and closing lines (your edits are kept)
  apply      add the beats to the film as NEW shots after a shot you choose. No existing shot is changed, locked work is never touched, a plan is applied once.
  list / remove   the plans kept with the film; removing one moves it aside, never deletes it.

Violence is kept to what a general-audience film would show: impact, reaction and consequence, never gore.

  <Film>/choreography/<id>.json         one plan
  <Film>/choreography/_removed/         plans taken out

  python -m filmcrafter_engine.choreography <action> <film_dir> --data '{...}'
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import sys
import time
import uuid

from . import safeio
from .safe import check_id

SCHEMA = 1
MIN_BEATS, MAX_BEATS = 4, 14
INTENSITY = ("grounded", "heightened")
OUTCOMES = ("a_wins", "b_wins", "draw", "interrupted")
TEXT_MAX = 600

TYPES: dict[str, dict] = {
    "fight": {"label": "Fist fight", "blurb": "Two people, no weapons: a scuffle that turns serious. Grounded fights look like effort, not choreography.", "needs_b": True,
              "good_for": "Close, handheld shots with the blow and the reaction in separate cuts."},
    "armed": {"label": "Armed duel", "blurb": "A blade, a staff or a bat on each side, or one weapon against bare hands. Contact is implied by the cut and the sound.", "needs_b": True,
              "good_for": "Tight shots on the weapon and the footwork; long exchanges are cut short."},
    "chase": {"label": "Foot chase", "blurb": "One person runs, another follows, through streets, stairs or a crowd. The obstacle of the moment is the story.", "needs_b": True,
              "good_for": "Tracking shots along the run, then a cutaway to the obstacle."},
    "vehicle": {"label": "Vehicle chase", "blurb": "Cars, bikes or boats. The vehicle and the road are the characters; faces are cut in for the stakes.", "needs_b": True,
                "good_for": "Wide shots of the vehicles with close inserts on faces, hands and wheels."},
    "sport": {"label": "Sports moment", "blurb": "The decisive point of a game or race: the build-up, the play, the crowd, the result.", "needs_b": False,
              "good_for": "A clear sequence of plays, with the crowd as reaction."},
}

# Each type's middle beats, in order: (key, kind, actor, framing, movement, angle, lens, seconds). kind: action | reaction | insert.  actor: lead (whoever has the momentum) | other | both | none
_FIGHT = [
    ("posture", "action", "both", "medium", "handheld", "eye level", "normal (35mm)", 4.0),
    ("strike", "action", "lead", "medium", "handheld", "eye level", "normal (35mm)", 3.0),
    ("land", "reaction", "other", "close-up", "handheld", "eye level", "portrait (50mm)", 2.5),
    ("scramble", "action", "other", "medium", "handheld", "low", "normal (35mm)", 3.5),
    ("hands", "insert", "none", "insert", "locked off", "eye level", "macro", 2.0),
    ("clinch", "action", "both", "over the shoulder", "handheld", "eye level", "portrait (50mm)", 3.5),
    ("strike", "action", "lead", "medium", "handheld", "low", "normal (35mm)", 3.0),
    ("land", "reaction", "other", "close-up", "handheld", "eye level", "portrait (50mm)", 2.5),
    ("breath", "insert", "none", "extreme close-up", "locked off", "eye level", "portrait (50mm)", 2.0),
    ("turn", "action", "other", "medium", "handheld", "eye level", "normal (35mm)", 3.5),
    ("strike", "action", "lead", "close-up", "handheld", "eye level", "portrait (50mm)", 2.5),
    ("land", "reaction", "other", "wide", "handheld", "high", "wide (24mm)", 3.0),
]
_ARMED = [
    ("posture", "action", "both", "medium", "subject tracking", "eye level", "normal (35mm)", 4.0),
    ("strike", "action", "lead", "medium", "handheld", "eye level", "normal (35mm)", 3.0),
    ("hands", "insert", "none", "insert", "locked off", "eye level", "macro", 2.0),
    ("land", "reaction", "other", "close-up", "handheld", "eye level", "portrait (50mm)", 2.5),
    ("scramble", "action", "other", "wide", "tracking", "low", "wide (24mm)", 3.5),
    ("strike", "action", "lead", "over the shoulder", "handheld", "eye level", "portrait (50mm)", 3.0),
    ("land", "reaction", "other", "close-up", "handheld", "eye level", "portrait (50mm)", 2.5),
    ("feet", "insert", "none", "insert", "tracking", "low", "normal (35mm)", 2.0),
    ("clinch", "action", "both", "close-up", "handheld", "eye level", "portrait (50mm)", 3.5),
    ("turn", "action", "other", "medium", "handheld", "eye level", "normal (35mm)", 3.5),
    ("strike", "action", "lead", "close-up", "handheld", "low", "portrait (50mm)", 2.5),
    ("land", "reaction", "other", "wide", "handheld", "high", "wide (24mm)", 3.0),
]
_CHASE = [
    ("bolt", "action", "other", "wide", "tracking", "eye level", "wide (24mm)", 4.0),
    ("run", "action", "other", "medium", "tracking", "low", "normal (35mm)", 3.5),
    ("look_back", "reaction", "other", "close-up", "tracking", "eye level", "portrait (50mm)", 2.0),
    ("obstacle", "action", "other", "wide", "locked off", "eye level", "wide (24mm)", 3.5),
    ("feet", "insert", "none", "insert", "tracking", "low", "normal (35mm)", 2.0),
    ("gain", "action", "lead", "medium", "tracking", "eye level", "normal (35mm)", 3.5),
    ("shortcut", "action", "other", "medium", "handheld", "eye level", "normal (35mm)", 3.0),
    ("look_back", "reaction", "other", "close-up", "handheld", "eye level", "portrait (50mm)", 2.0),
    ("obstacle", "action", "lead", "wide", "pan", "high", "wide (24mm)", 3.5),
    ("lunge", "action", "lead", "medium", "handheld", "eye level", "normal (35mm)", 2.5),
    ("breath", "insert", "none", "extreme close-up", "locked off", "eye level", "portrait (50mm)", 2.0),
    ("corner", "action", "other", "medium", "tracking", "eye level", "normal (35mm)", 3.0),
]
_VEHICLE = [
    ("launch", "action", "other", "wide", "tracking", "low", "wide (24mm)", 4.0),
    ("wheel", "insert", "none", "insert", "locked off", "low", "macro", 2.0),
    ("run", "action", "other", "wide", "tracking", "eye level", "wide (24mm)", 4.0),
    ("look_back", "reaction", "other", "close-up", "handheld", "eye level", "portrait (50mm)", 2.0),
    ("obstacle", "action", "other", "wide", "locked off", "high", "wide (24mm)", 3.5),
    ("gain", "action", "lead", "medium", "tracking", "eye level", "normal (35mm)", 3.5),
    ("hands_wheel", "insert", "none", "insert", "handheld", "eye level", "macro", 2.0),
    ("shortcut", "action", "other", "wide", "crane", "high", "wide (24mm)", 4.0),
    ("look_back", "reaction", "other", "close-up", "handheld", "eye level", "portrait (50mm)", 2.0),
    ("lunge", "action", "lead", "wide", "tracking", "low", "wide (24mm)", 3.0),
    ("breath", "insert", "none", "extreme close-up", "locked off", "eye level", "portrait (50mm)", 2.0),
    ("corner", "action", "other", "wide", "tracking", "eye level", "wide (24mm)", 3.5),
]
_SPORT = [
    ("posture", "action", "both", "medium", "locked off", "eye level", "normal (35mm)", 4.0),
    ("crowd", "reaction", "none", "wide", "pan", "high", "wide (24mm)", 2.5),
    ("play", "action", "lead", "medium", "subject tracking", "eye level", "telephoto (85mm+)", 3.5),
    ("hands", "insert", "none", "insert", "locked off", "eye level", "macro", 2.0),
    ("scramble", "action", "other", "wide", "tracking", "eye level", "wide (24mm)", 3.5),
    ("play", "action", "lead", "close-up", "subject tracking", "low", "portrait (50mm)", 3.0),
    ("look_back", "reaction", "other", "close-up", "handheld", "eye level", "portrait (50mm)", 2.0),
    ("crowd", "reaction", "none", "wide", "locked off", "high", "wide (24mm)", 2.5),
    ("turn", "action", "other", "medium", "subject tracking", "eye level", "telephoto (85mm+)", 3.5),
    ("play", "action", "lead", "wide", "tracking", "low", "wide (24mm)", 3.5),
    ("breath", "insert", "none", "extreme close-up", "locked off", "eye level", "portrait (50mm)", 2.0),
    ("land", "reaction", "other", "close-up", "handheld", "eye level", "portrait (50mm)", 2.5),
]
MIDDLES = {"fight": _FIGHT, "armed": _ARMED, "chase": _CHASE, "vehicle": _VEHICLE, "sport": _SPORT}

# the words: {a} is who acts, {b} who it happens to (the other side), {place} where, {w} the weapon or vehicle, {mod} a manner that depends on the intensity
VERBS: dict[str, dict[str, list[str]]] = {
    "fight": {
        "posture": ["{a} and {b} circle each other, {mod} weight on the back foot", "{a} squares up to {b}; neither looks away", "{a} drops a bag and rolls a shoulder as {b} steps in"],
        "strike": ["{a} throws a {mod} right hand at {b}'s jaw", "{a} drives a knee into {b}'s ribs", "{a} shoves {b} hard, back into the nearest wall", "{a} ducks a swing and lands a short punch to {b}'s body"],
        "land": ["{b}'s head snaps to the side and {b} staggers a step", "{b} folds around the blow and gasps", "{b} hits the wall, slides, and pushes up again"],
        "scramble": ["{a} scrambles for footing, one hand on the ground", "{a} backs away, hands up, looking for room", "{a} spits and wipes a sleeve across the mouth"],
        "hands": ["a fist clenches, knuckles white", "fingers grip a torn sleeve", "a hand finds a bruised rib"],
        "clinch": ["{a} and {b} lock together, forehead to forehead, straining", "{a} gets an arm around {b}'s neck; {b} twists to break it", "{a} and {b} grapple for the same wrist"],
        "breath": ["{a}'s chest heaves; sweat on the lip", "{b}'s eyes, wide and fixed", "a ragged breath, a flinch"],
        "turn": ["{a} slips under an arm and ends up behind {b}", "{a} uses {b}'s own weight and spins {b} around", "{a} finds a gap and takes it"],
    },
    "armed": {
        "posture": ["{a} lifts {w} and takes a slow step toward {b}", "{a} and {b} measure the distance, {w} between them", "{a} flexes a grip on {w}; {b} sidesteps"],
        "strike": ["{a} swings {w} in a {mod} arc at {b}", "{a} thrusts {w} at {b}'s guard", "{a} brings {w} down toward {b}; {b} turns it aside"],
        "hands": ["knuckles tighten on {w}", "a thumb slides along the edge of {w}", "{w} trembles in a held grip"],
        "land": ["{b} catches the blow on the guard and is pushed back", "{b} twists away; {w} just misses", "{b} grunts as the impact rings through the arms"],
        "scramble": ["{a} stumbles backward over loose ground, {w} still up", "{a} rolls aside and comes up breathing hard"],
        "feet": ["boots shift on the ground, finding the line", "a heel slides, dust kicks up"],
        "clinch": ["{a} and {b} lock against each other, {w} between their faces", "{a} presses {w} against {b}'s guard, close and shaking"],
        "turn": ["{a} knocks {w} from {b}'s hands and it skids away", "{a} slips inside {b}'s reach"],
        "breath": ["{a}'s eyes track {w}; a drop of sweat falls", "{b}'s jaw set, breathing through the nose"],
    },
    "chase": {
        "bolt": ["{a} bursts out of cover and runs; {b} sees and gives chase", "{a} runs, {mod} strides, through {place}", "{a} looks over a shoulder and breaks into a sprint"],
        "run": ["{a} sprints through {place}, {b} a few strides behind", "{a} weaves through the crowd, shoving past", "{a} takes the stairs three at a time"],
        "look_back": ["{a} glances back: {b} is closer", "{a}'s face: breath tearing, eyes darting", "{b} does not slow down"],
        "obstacle": ["{a} vaults a low wall and lands running", "{a} drags a bin into {b}'s path", "{a} ducks under a barrier as {b} hits it"],
        "feet": ["shoes slap wet ground", "a foot skids on a turn, recovers", "feet pounding stairs"],
        "gain": ["{b} gains a stride on {a}", "{b} closes the gap, an arm outstretched", "{b} cuts a corner and is suddenly nearer"],
        "shortcut": ["{a} slips through a gap {b} cannot fit", "{a} cuts through a doorway and pulls it shut behind", "{a} drops from a low ledge into the lane"],
        "lunge": ["{b} lunges and catches {a}'s sleeve", "{b} dives for {a}'s collar and misses by a hand", "{a} stumbles; {b} is right there"],
        "breath": ["a ragged breath, steam in the air", "{a}'s eyes, wide, searching for the way out"],
        "corner": ["{a} swings around a corner and is gone", "{a} slides across a hood and keeps going", "{a} turns into an alley and slows to listen"],
    },
    "vehicle": {
        "launch": ["{a} floors it; {w} lurches forward, tyres biting", "{w} bursts out of {place}, {b} close behind"],
        "wheel": ["a wheel throws grit as it bites", "tyre tread flicks across wet road"],
        "run": ["{a}'s {w} tears through {place}, {b} in the mirror", "{w} weaves through traffic, a {mod} line"],
        "look_back": ["{a}'s eyes flick to the mirror: {b} is closer", "{b}'s jaw, set; the road reflected in the glass"],
        "obstacle": ["{a} swerves around a stopped truck; {b} brakes and slides", "{a} threads a narrow gap between two vans"],
        "gain": ["{b} pulls alongside {a}; the two vehicles almost touch", "{b} closes up on {a}'s tail"],
        "hands_wheel": ["hands tight on the wheel, knuckles pale", "a hand slams the gearstick"],
        "shortcut": ["{a} cuts through a car park and out the far side", "{a} takes the ramp and drops onto the lower road"],
        "lunge": ["{b} swings in and clips {a}'s bumper; both fight the wheel", "{b} noses ahead of {a}"],
        "breath": ["a bead of sweat; eyes locked on the road", "{a} exhales, and grips tighter"],
        "corner": ["{a} drifts around a corner; {b} follows, wide", "{w} skids around the bend, controls it, and goes on"],
    },
    "sport": {
        "posture": ["{a} settles into position, eyes fixed on the play", "{a} bounces on the toes; the whole place holds its breath"],
        "crowd": ["the crowd, on its feet, noise rising", "a child grips a rail; the stand blurs behind"],
        "play": ["{a} makes a {mod} move and breaks free", "{a} drives forward, ball under control", "{a} reads the play and moves first"],
        "hands": ["fingers tighten on the ball", "a hand chalked and ready"],
        "scramble": ["the pack scrambles; {a} fights for the loose ball", "{b} closes in as {a} is boxed against the line"],
        "look_back": ["{b} reads {a} and shifts to cover", "{a}'s eyes find the open space"],
        "turn": ["{a} spins away from {b} and makes room", "{a} fakes one way and goes the other"],
        "breath": ["a ragged breath, a bead of sweat", "{a}'s eyes, locked on the target"],
        "land": ["the moment lands: the ball is away", "the shot is gone; everything waits"],
    },
}
OPENERS = {
    "fight": ["{place}: {a} and {b}, a few paces apart. The space they have to fight in, and what is behind each of them.", "{a} and {b} face each other in {place}, a tension that has gone past words."],
    "armed": ["{place}: {a} and {b}, {w} in hand. The ground between them, and the nearest cover.", "{a} faces {b} in {place}, {w} raised; the only sound is breathing."],
    "chase": ["{place}: {a} on the run, {b} not far behind. The route they will take is plain to see.", "{a} breaks from cover in {place} as {b} spots them."],
    "vehicle": ["{place}: {a}'s {w} and {b} behind. The road stretching ahead.", "{a} and {b} at either end of {place}, engines catching."],
    "sport": ["{place}: the deciding moment. {a} in position, the crowd waiting.", "{a} walks into the deciding moment in {place}."],
}
CLOSERS = {
    "a_wins": {"fight": ["{a} stands over {b}, breathing hard; it is over", "{b} stays down; {a} steps back, shaking out a hand"],
               "armed": ["{a} holds {w} at {b}'s throat; the fight has ended", "{b}'s weapon on the ground; {a} stands over, panting"],
               "chase": ["{a} slips out of sight; {b} stops, bent over, empty-handed", "{a} reaches the safe place and shuts the door"],
               "vehicle": ["{a}'s {w} pulls clear of {b} and is gone around the bend", "{b} brakes; {a}'s tail lights shrink"],
               "sport": ["{a} has done it; the stands erupt", "{a} falls to the knees as the noise breaks"]},
    "b_wins": {"fight": ["{b} stands over {a}, breathing hard; it is over", "{a} stays down; {b} steps back"],
               "armed": ["{b} holds {w} at {a}'s throat; the fight has ended", "{a}'s weapon on the ground; {b} stands over, panting"],
               "chase": ["{b} catches {a} by the arm; the run is over", "{a} slows, hands up, cornered"],
               "vehicle": ["{b} forces {a}'s {w} to a halt; the engines tick", "{a} brakes hard against a blocked road; {b} stops behind"],
               "sport": ["{b} has done it; {a} watches, hands on the head", "{b} takes it in the last moment; {a} stands stunned"]},
    "draw": {"fight": ["{a} and {b} fall apart, exhausted; neither can finish it", "both stagger back, breathing hard; it ends in a stalemate"],
             "armed": ["{a} and {b} lower their weapons at the same moment, spent", "{a} and {b} stand apart, {w} drooping"],
             "chase": ["{a} and {b} both stop, bent double; the trail has gone cold", "the chase ends in a dead end for both"],
             "vehicle": ["{a} and {b} both brake at the edge of the road, engines ticking", "the two vehicles stop apart, drivers staring"],
             "sport": ["the whistle: it ends level, and nobody quite believes it", "{a} and {b} shake hands, neither with a win"]},
    "interrupted": {"fight": ["a shout from off-screen; {a} and {b} freeze, then drag apart", "a siren in the distance: {a} lets go of {b}, and both look toward it"],
                    "armed": ["a voice from the dark; {a} and {b} both turn, {w} lowered", "a light swings across the scene; {a} and {b} stop"],
                    "chase": ["something huge arrives: a train, a gate, a crowd; {a} and {b} stop dead", "a shot rings out; {a} and {b} both go still"],
                    "vehicle": ["a barrier, a flash of light; {a} and {b} both brake", "a train crosses, and the chase stops"],
                    "sport": ["the lights go out; the crowd falls silent", "an official steps in and stops play"]},
}
MODS = {"grounded": {"fight": "heavy", "armed": "clumsy, desperate", "chase": "ragged", "vehicle": "tight", "sport": "quick"},
        "heightened": {"fight": "sweeping", "armed": "sweeping", "chase": "flying", "vehicle": "daring", "sport": "brilliant"}}
HURTS = ["a split lip", "a bruised cheek", "a torn sleeve", "grit in the hair", "a limp", "a hand held to the ribs", "scuffed knuckles", "a cut brow"]
SOUNDS = {"strike": "a sharp exhale and a dull thud of impact", "land": "a grunt, cloth scuffing on the ground", "scramble": "scuffing feet, heavy breath", "clinch": "straining breath, fabric tearing",
          "posture": "wind, slow footsteps, a held breath", "hands": "creaking grip, a held breath", "breath": "ragged breathing, a heartbeat", "turn": "quick feet, a sharp breath",
          "bolt": "feet pounding, a shout", "run": "pounding feet, ragged breath", "look_back": "breath, footfalls closing", "obstacle": "a crash, a metal clang", "feet": "wet footfalls, a skid",
          "gain": "footfalls closing, a shout", "shortcut": "a door slam, a drop and a thud", "lunge": "a scrabble of cloth and a gasp", "corner": "a skid, a breath, then quiet",
          "launch": "engine roar, tyres biting", "wheel": "tyre squeal, grit", "hands_wheel": "creak of leather, the engine", "play": "crowd noise rising, shoes on the court", "crowd": "a roar, a chant rising",
          "establish": "the place: wind, distance, a held breath", "aftermath": "silence settling, breathing slowing"}
BEAT_FIELDS = ("text", "seconds", "framing", "movement", "angle", "lens", "sound", "title")


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


def _text(v, limit: int = TEXT_MAX) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()[:limit]


def _dir(d: str) -> str:
    return os.path.join(d, "choreography")


def _path(d: str, pid: str) -> str:
    return os.path.join(_dir(d), f"{check_id(pid, 'plan')}.json")


def _film(d: str) -> None:
    m = safeio.read_json(os.path.join(d, "film.json"), None)
    if not isinstance(m, dict) or "story" not in m:
        raise SystemExit("That isn't a FilmCrafter film.")


def types() -> dict:
    return {"types": [{"id": k, "label": v["label"], "blurb": v["blurb"], "needs_b": v["needs_b"], "good_for": v["good_for"]} for k, v in TYPES.items()],
            "outcomes": [{"id": "a_wins", "label": "The first side wins"}, {"id": "b_wins", "label": "The other side wins"}, {"id": "draw", "label": "Neither wins"}, {"id": "interrupted", "label": "It is interrupted"}],
            "intensity": [{"id": "grounded", "label": "Grounded: effort, mistakes, real weight"}, {"id": "heightened", "label": "Heightened: stylish, sweeping"}],
            "limits": {"min_beats": MIN_BEATS, "max_beats": MAX_BEATS},
            "advice": ["Each shot holds one clear thing. A blow and its landing are separate shots: the cut sells the contact.", "Short shots (2 to 5 seconds) are what video models do best.",
                       "Contact between two people is the hardest thing for a model to draw, so it is cut around: the swing, then the reaction.", "Keep one person screen-left and the other screen-right unless you cut away before they swap."]}


# ---------------------------------------------------------------- the plan

def _pick(rng: random.Random, pool: list[str]) -> str:
    return pool[rng.randrange(len(pool))]


def _fill(text: str, **kw) -> str:
    return text.format(**{k: v for k, v in kw.items()})


def _first(names: list[str]) -> str:
    return names[0] if names else "someone"


def _scene_info(d: str, scene: int) -> dict:
    from . import shots as S
    idx = S._index(d)
    cons = [S._read(S._cpath(d, sid)) for sid in idx.get("order", [])]
    cons = [c for c in cons if isinstance(c, dict) and int(c.get("scene", 0)) == int(scene)]
    if not cons:
        raise SystemExit("That scene isn't in the film yet. Break the story down first.")
    place = next((c["environment"]["name"] for c in cons if (c.get("environment") or {}).get("name")), "")
    names = []
    for c in cons:
        for x in c.get("characters") or []:
            if x.get("name") and x["name"] not in names:
                names.append(x["name"])
    return {"shots": [c["id"] for c in cons], "last": cons[-1]["id"], "place": place.title() if place else "the scene", "characters": names}


def _clean_names(v) -> list[str]:
    out = []
    for x in (v or []) if isinstance(v, list) else [v] if v else []:
        t = _text(x, 60)
        if t and t not in out:
            out.append(t)
    return out[:4]


def generate(d: str, p: dict) -> dict:
    """Plan an action scene. Free; nothing is sent. The same inputs give the same plan."""
    _film(d)
    t = str(p.get("type") or "")
    if t not in TYPES:
        raise SystemExit("Choose what kind of action scene this is.")
    try:
        scene = int(p.get("scene"))
    except (TypeError, ValueError):
        raise SystemExit("Choose the scene it happens in.")
    info = _scene_info(d, scene)
    a_names, b_names = _clean_names(p.get("side_a")), _clean_names(p.get("side_b"))
    if not a_names:
        raise SystemExit("Say who is in the action (at least one person on the first side).")
    if TYPES[t]["needs_b"] and not b_names:
        raise SystemExit("Say who is on the other side (the opponent, or the one being chased or chasing).")
    if set(a_names) & set(b_names):
        raise SystemExit("A person can only be on one side.")
    n = max(MIN_BEATS, min(MAX_BEATS, int(p.get("beats") or 8)))
    inten = p.get("intensity") if p.get("intensity") in INTENSITY else "grounded"
    outcome = p.get("outcome") if p.get("outcome") in OUTCOMES else "a_wins"
    place = _text(p.get("place"), 80) or info["place"]
    weapon = _text(p.get("weapon"), 40) or ("a staff" if t == "armed" else "the car" if t == "vehicle" else "")
    seed = "|".join([str(scene), t, ",".join(a_names), ",".join(b_names), str(n), inten, outcome, place, weapon, str(p.get("variation") or 0)])
    rng = random.Random(hashlib.sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest())
    A, B = _first(a_names), _first(b_names) if b_names else "the crowd"
    where = place if ("'" in place or place.lower().startswith(("the ", "a ", "an "))) else "the " + place.lower()
    mod = MODS[inten][t]
    mid = MIDDLES[t]
    want = n - 2
    seq = [mid[i % len(mid)] for i in range(want)]
    # the momentum: even at first, then it swings, then it settles with the winner
    winner = {"a_wins": "A", "b_wins": "B", "draw": "even", "interrupted": "even"}[outcome]
    beats = [{"kind": "establish", "key": "establish", "actor": "none", "framing": "establishing", "movement": "crane" if t == "vehicle" else "pull out" if t == "chase" else "locked off", "angle": "high" if t in ("vehicle", "sport") else "eye level",
              "lens": "wide (24mm)", "seconds": 4.0, "momentum": "even"}]
    for i, (key, kind, actor, fr, mv, an, ln, sec) in enumerate(seq):
        pos = i / max(1, want - 1)
        if pos < 0.34:
            mom = "even"
        elif pos < 0.67:
            mom = "B" if (i % 2 == 0 and winner != "B") else "A" if winner != "A" else "B"
        else:
            mom = winner if winner != "even" else ("A" if i % 2 else "B")
        beats.append({"kind": kind, "key": key, "actor": actor, "framing": fr, "movement": mv, "angle": an, "lens": ln, "seconds": sec, "momentum": mom})
    beats.append({"kind": "aftermath", "key": "aftermath", "actor": "none", "framing": "wide" if outcome != "interrupted" else "medium", "movement": "pull out" if outcome != "interrupted" else "locked off", "angle": "high" if outcome != "interrupted" else "eye level",
                  "lens": "wide (24mm)", "seconds": 4.0, "momentum": winner})
    hurts = {A: [], B: []}
    last_attacker = None
    out = []
    for i, b in enumerate(beats):
        who_lead = {"A": A, "B": B, "even": A if i % 2 == 0 else B}[b["momentum"]]
        who_other = B if who_lead == A else A
        key = b["key"]
        if b["kind"] == "establish":
            text = _fill(_pick(rng, OPENERS[t]), a=A, b=B, place=place, w=weapon)
            actor = None
        elif b["kind"] == "aftermath":
            pool = CLOSERS[outcome][t]
            text = _fill(_pick(rng, pool), a=A, b=B, place=place, w=weapon)
            actor = who_lead if outcome in ("a_wins", "b_wins") else None
        else:
            if t in ("chase", "vehicle", "sport"):                        # A is the runner (or the player), B the pursuer (or the opponent): fixed, whoever has the momentum
                a_, b_ = A, B
                actor = B if key in ("gain", "lunge") else A if b["actor"] != "none" else None
            else:                                                       # a fight: who attacks, who is hit, follows the momentum
                attacker = last_attacker or who_lead
                if key == "land":
                    a_, b_ = attacker, (B if attacker == A else A)
                    actor = b_
                elif key == "scramble":
                    a_, b_ = (B if attacker == A else A), attacker
                    actor = a_
                elif key == "posture":
                    a_, b_, actor = A, B, None
                else:
                    a_, b_ = who_lead, who_other
                    actor = a_ if b["actor"] != "none" else None
                if b["kind"] == "action" and key in ("strike", "clinch", "turn"):
                    last_attacker = a_
                if key == "land":
                    hurts[b_ if b_ in hurts else B].append(HURTS[rng.randrange(len(HURTS))])
                    hurts[b_] = list(dict.fromkeys(hurts[b_]))[:3]
            pool = VERBS[t].get(key) or VERBS[t].get("posture") or next(iter(VERBS[t].values()))
            text = _fill(_pick(rng, pool), a=a_, b=b_, place=where, w=weapon, mod=mod)
        carry = "; ".join(f"{n_} has {' and '.join(v)}" for n_, v in hurts.items() if v and n_ in (A, B) and (n_ != "the crowd"))
        if i > 0 and carry and b["kind"] not in ("insert",):
            text = text + f" (Carrying: {carry}.)"
        out.append({"n": i + 1, "phase": key, "kind": b["kind"], "actor": actor, "momentum": b["momentum"], "text": _text(text), "seconds": b["seconds"] if inten == "grounded" else round(max(2.0, b["seconds"] - 0.5), 1),
                    "framing": b["framing"], "movement": b["movement"], "angle": b["angle"], "lens": b["lens"], "sound": SOUNDS.get(key, SOUNDS["posture"]),
                    "title": f"{TYPES[t]['label']} {i + 1}/{n}", "carrying": carry})
    people = a_names + b_names
    geography = (f"{A} enters screen-left and {B} screen-right and they stay that way: {A} left, {B} right. Cross the line only on a cutaway." if b_names else f"{A} moves left to right across the frame.")
    warnings = ["Video models draw one clear action well and long sequences badly: keep each shot to the single thing in its text.",
                "Contact is cut around on purpose: the blow and the landing are separate shots, so no model has to draw two bodies colliding."]
    if len(a_names) > 1 or len(b_names) > 1:
        warnings.append("More than one person on a side: the plan follows the first named person of each side; add the others as extras in the shot text if you want them seen.")
    if t in ("fight", "armed"):
        warnings.append("Violence is kept to impact, reaction and consequence: no gore.")
    pid = "ch-" + uuid.uuid4().hex[:8]
    plan = {"schema": SCHEMA, "id": pid, "created": int(time.time()), "type": t, "scene": scene, "place": place, "weapon": weapon, "sides": {"a": a_names, "b": b_names}, "intensity": inten, "outcome": outcome,
            "geography": geography, "people": people, "beats": out, "seconds": round(sum(b["seconds"] for b in out), 1), "warnings": warnings, "after": info["last"], "applied": [], "status": "draft",
            "request": {k: p.get(k) for k in ("type", "scene", "side_a", "side_b", "beats", "intensity", "outcome", "place", "weapon", "variation")}}
    os.makedirs(_dir(d), exist_ok=True)
    safeio.write_json(_path(d, pid), plan, backup=False)
    return plan


def load(d: str, pid: str) -> dict:
    p = safeio.read_json(_path(d, pid), None)
    if not isinstance(p, dict) or not isinstance(p.get("beats"), list):
        raise SystemExit("That plan isn't there.")
    return p


def list_plans(d: str) -> dict:
    _film(d)
    out = []
    try:
        names = sorted(os.listdir(_dir(d)))
    except OSError:
        names = []
    for f in names:
        if f.endswith(".json") and f.startswith("ch-"):
            p = safeio.read_json(os.path.join(_dir(d), f), None)
            if isinstance(p, dict) and isinstance(p.get("beats"), list):
                out.append({k: p.get(k) for k in ("id", "created", "type", "scene", "outcome", "seconds", "status", "applied")} | {"beats": len(p["beats"])})
    out.sort(key=lambda x: -(x.get("created") or 0))
    return {"plans": out}


def update(d: str, pid: str, patch: dict) -> dict:
    """Change the words, length or camera of beats, or the geography line. A plan that has been applied is a record: change the shots instead."""
    _film(d)
    p = load(d, pid)
    if p.get("applied"):
        raise SystemExit("This plan has already been added to the film. Change the shots themselves, or plan it again.")
    from . import shots as S
    for ch in patch.get("beats") or []:
        n = int(ch.get("n") or 0)
        b = next((x for x in p["beats"] if x["n"] == n), None)
        if not b:
            continue
        if "text" in ch:
            b["text"] = _text(ch["text"]) or b["text"]
        if "title" in ch:
            b["title"] = _text(ch["title"], 100) or b["title"]
        if "sound" in ch:
            b["sound"] = _text(ch["sound"], 200)
        if "seconds" in ch:
            try:
                b["seconds"] = round(max(1.0, min(8.0, float(ch["seconds"]))), 1)
            except (TypeError, ValueError):
                raise SystemExit("The length must be a number of seconds.")
        for k, allowed in (("framing", S.FRAMING), ("movement", S.MOVEMENT), ("angle", S.ANGLE), ("lens", S.LENS)):
            if k in ch:
                if ch[k] not in allowed:
                    raise SystemExit(f"Choose a {k} from the list.")
                b[k] = ch[k]
    if "geography" in patch:
        p["geography"] = _text(patch["geography"], 400)
    p["seconds"] = round(sum(b["seconds"] for b in p["beats"]), 1)
    safeio.write_json(_path(d, pid), p, backup=False)
    return p


def apply(d: str, pid: str, after: str | None = None) -> dict:
    """Add the beats to the film as new shots, after `after` (default the scene's last shot). Existing shots are never changed; a plan is applied once."""
    from . import shots as S
    _film(d)
    p = load(d, pid)
    if p.get("applied"):
        raise SystemExit("This plan is already in the film.")
    info = _scene_info(d, p["scene"])
    anchor = after if after in info["shots"] else info["last"]
    before = {sid: open(S._cpath(d, sid), "rb").read() for sid in info["shots"]}
    made = []
    prev = anchor
    A, B = (p["sides"]["a"] or [""])[0], (p["sides"]["b"] or [""])[0]
    for b in p["beats"]:
        res = S.add(d, p["scene"], prev)
        sid = res["id"]
        who = [x for x in (A, B) if x and (b["kind"] in ("establish", "aftermath", "action", "reaction") or x == b.get("actor"))]
        beat = {"character": b.get("actor") or "", "what": b["text"], "start": "", "turn": "", "end": ""}
        patch = {"title": b["title"], "story_purpose": f"{TYPES[p['type']]['label']}: {b['phase'].replace('_', ' ')}", "action": b["text"],
                 "characters": [{"name": n} for n in dict.fromkeys(p["people"] if b["kind"] == "establish" else who)],
                 "camera": {"framing": b["framing"], "movement": b["movement"], "angle": b["angle"], "lens": b["lens"]},
                 "generation": {"duration": b["seconds"], "notes": f"Action choreography {p['id']}, beat {b['n']} of {len(p['beats'])}. One clear thing in this shot; keep it short."},
                 "blocking": p["geography"], "sound": b["sound"], "continuity": b.get("carrying") or "",
                 "performance": {"emotional_intention": {"A": f"{A} has the upper hand", "B": f"{B} has the upper hand", "even": "evenly matched, tense"}.get(b["momentum"], ""),
                                 "beats": [beat] if b.get("actor") else []}}
        S.set_fields(d, sid, patch)
        made.append(sid)
        prev = sid
    for sid, raw in before.items():                        # the shots that were there are exactly as they were
        if open(S._cpath(d, sid), "rb").read() != raw:
            raise SystemExit("An existing shot changed while adding the action: nothing more was done. Please report this.")
    p["applied"], p["status"], p["after"] = made, "applied", anchor
    safeio.write_json(_path(d, pid), p, backup=False)
    return {"plan": p, "added": made, "after": anchor}


def remove(d: str, pid: str) -> dict:
    _film(d)
    src = _path(d, pid)
    if not os.path.isfile(src):
        raise SystemExit("That plan isn't there.")
    os.makedirs(os.path.join(_dir(d), "_removed"), exist_ok=True)
    dst = os.path.join(_dir(d), "_removed", f"{pid}-{int(time.time())}.json")
    shutil.move(src, dst)
    return {"removed": pid}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="choreography")
    ap.add_argument("action", choices=["types", "generate", "update", "apply", "list", "remove", "get"])
    ap.add_argument("film")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    try:
        x = json.loads(a.data or "{}")
        x = x if isinstance(x, dict) else {}
        d = os.path.abspath(a.film)
        if a.action == "types":
            res = types()
        elif a.action == "generate":
            res = generate(d, x)
        elif a.action == "update":
            res = update(d, x.get("id", ""), x)
        elif a.action == "apply":
            res = apply(d, x.get("id", ""), x.get("after"))
        elif a.action == "list":
            res = list_plans(d)
        elif a.action == "get":
            _film(d)
            res = load(d, x.get("id", ""))
        else:
            res = remove(d, x.get("id", ""))
        emit(event="result", data=res)
        return 0
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
