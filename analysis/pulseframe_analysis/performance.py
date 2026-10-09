"""Performance profiles and micro-animation.

A profile sets how big the acting is (Natural, Restrained, Expressive, Dramatic, Energetic) and the small living
motion that keeps a frame from looking frozen: blinks, breathing, weight shifts, hair and fabric. It is chosen for the
project and can be overridden per scene, per character and per shot (shot > scene > character > project).

It reaches renders as prompt text (how to play it, how much, and the micro-motion for video), and moving stills as a
free micro-animation in the export and preview (a gentle breathing drift sized by the profile).

  python -m pulseframe_analysis.performance <action> <project> --data '{...}'   actions: get | set
"""
from __future__ import annotations

import argparse
import json
import os
import sys

PROFILES = {
    "natural": {
        "label": "Natural", "blurb": "Truthful, everyday acting. Small motivated gestures; the default.", "scale": 1.0,
        "play": "Play it truthfully: motivated small gestures, eyes that think before they move, breathing that matches the "
                "emotion; no mugging or exaggerated poses.",
        "micro": "Keep people alive between actions: natural blinks every few seconds, visible breathing in chest and shoulders, "
                 "small weight shifts, hair and loose fabric moving slightly.",
        "still": "Relaxed, believable expression and posture, caught mid-thought.",
        "drift": {"amp": 0.006, "period": 5.5},
    },
    "restrained": {
        "label": "Restrained", "blurb": "Held back, internal. Emotion shows in the eyes and breath, not the face.", "scale": 0.6,
        "play": "Underplay it: emotion held inside and leaking through the eyes, jaw and breath; almost no gesture; stillness "
                "is the performance. Never mug or pose.",
        "micro": "Near-stillness with life in it: slow blinks, slow controlled breathing, a swallow, a tightening jaw, the "
                 "smallest shift of the eyes; nothing large moves.",
        "still": "Composed, contained expression; the feeling is in the eyes, the face barely moves.",
        "drift": {"amp": 0.003, "period": 7.0},
    },
    "expressive": {
        "label": "Expressive", "blurb": "Open and readable. Clear faces and gestures, still grounded.", "scale": 1.3,
        "play": "Play it openly: readable faces, full gestures that come from the feeling, bodies that respond to each other; "
                "grounded and believable, never cartoonish.",
        "micro": "Lively micro-motion: frequent natural blinks, visible breathing, expressive hands, head tilts and weight "
                 "shifts, hair and clothes reacting to movement.",
        "still": "Open, readable expression and a clear gesture that shows the feeling.",
        "drift": {"amp": 0.009, "period": 4.5},
    },
    "dramatic": {
        "label": "Dramatic", "blurb": "Heightened, cinematic. Big emotional beats, strong poses, held moments.", "scale": 1.6,
        "play": "Heighten it for the big screen: strong emotional beats, deliberate poses held for effect, tears, clenched "
                "hands, turns to camera light; committed and intense but still human.",
        "micro": "Charged stillness between beats: heavy breathing, trembling hands, eyes glistening, a slow turn of the "
                 "head, fabric and hair caught in movement.",
        "still": "A heightened, emotionally charged expression and a strong, deliberate pose.",
        "drift": {"amp": 0.012, "period": 6.0},
    },
    "energetic": {
        "label": "Energetic", "blurb": "High energy for up-tempo songs: movement, rhythm, performance to camera.", "scale": 1.5,
        "play": "Play it with energy: bodies move with the beat, big confident gestures, performing to camera, joy or attitude "
                "in every line; fast reactions.",
        "micro": "Constant rhythmic life: bouncing on the beat, head nods, shoulders and hands moving to the music, hair "
                 "and clothes in motion.",
        "still": "Mid-movement, full of energy: an energetic pose caught on the beat.",
        "drift": {"amp": 0.014, "period": 2.0},
    },
}
DEFAULT = "natural"

# What a face and body do when they feel something, so the small motion between actions belongs to the moment and is not the same for every shot of a style.
EMOTION_MICRO = [
    (r"embarrass|sheepish|shy|bashful|awkward|flustered", "eyes drop and flick away, a small swallow, lips press into a tight smile, a hand drifts to the face or collar"),
    (r"anger|angry|furious|rage|irritat|annoy|indignan", "jaw tightens, nostrils flare, breath short and held, a stillness before the move"),
    (r"sad|grief|sorrow|heartbr|mourn|loss|tearful", "eyes glisten, a slow heavy blink, the lower lip trembles, shoulders sink on the breath"),
    (r"joy|happy|delight|glee|elat|cheer|laugh", "cheeks lift and eyes crinkle, quick light breaths, small bounces of weight, the head tips back a little"),
    (r"fear|afraid|anxious|nervous|worr|dread|panic", "eyes widen and dart, breath shallow and quick, fingers fidget, a swallow"),
    (r"proud|dignity|dignified|stern|authorit|command|regal", "chin lifts, a slow measured blink, a steady gaze, shoulders squared, stillness that holds the room"),
    (r"surpris|shock|realiz|realis|startl|astonish|stunned", "eyes widen and brows jump, a sharp small inhale, a beat of stillness before the reaction"),
    (r"love|tender|warm|affection|fond|gentle|maternal", "soft eyes, a slow easy breath, the head tilts, a small smile that arrives late"),
    (r"contempt|disdain|scorn|smug|sceptic|skeptic|doubt|suspic", "one brow lifts, a lip corner tightens, a slow look away and back"),
    (r"tired|weary|exhaust|bored|resign", "heavy blinks, slow breath, weight sinks into one hip, movements a little late"),
    (r"determin|resolve|focus|intent|purpose", "eyes fixed on the task, a steady breath, small precise movements, the jaw set"),
]


def micro_for(emotion: str) -> str:
    """The behaviours that belong to a feeling ("embarrassed realization" -> eyes dropping, a swallow, a tight smile), or '' when the feeling is not one this knows."""
    import re
    found = []
    for pat, text in EMOTION_MICRO:
        if re.search(pat, str(emotion or ""), re.I) and text not in found:
            found.append(text)
    return "; ".join(found[:2])


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data):
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def settings(project: dict) -> dict:
    p = project.get("performance") or {}
    return {"default": p.get("default") if p.get("default") in PROFILES else DEFAULT,
            "scenes": dict(p.get("scenes") or {}), "characters": dict(p.get("characters") or {}), "shots": dict(p.get("shots") or {}),
            "set": bool(p)}


def resolve(project: dict, shot: dict) -> tuple[str, str]:
    """(profile id, where it came from) for a shot: shot > scene > character (first performer that has one) > project."""
    s = settings(project)
    if s["shots"].get(shot.get("id")) in PROFILES:
        return s["shots"][shot["id"]], "shot"
    if s["scenes"].get(str(shot.get("scene"))) in PROFILES:
        return s["scenes"][str(shot["scene"])], "scene"
    for n in shot.get("performers") or []:
        if s["characters"].get(n) in PROFILES:
            return s["characters"][n], f"character:{n}"
    return s["default"], "project"


def direction(project: dict, shot: dict, video: bool) -> dict | None:
    """The profile's prompt text for a shot, or None when the project never chose one (keeps old prompts unchanged)."""
    if not (project.get("performance") or {}):
        return None
    pid, _ = resolve(project, shot)
    prof = PROFILES[pid]
    out = {"id": pid, "play": prof["play"]}
    if shot.get("performers"):
        lvl = shot.get("performance_intensity")
        if isinstance(lvl, (int, float)) and prof["scale"] != 1.0:
            adj = max(1, min(10, round(lvl * prof["scale"])))
            out["play"] += f" Intensity: about {adj}/10 ({prof['label'].lower()} performance)."
        feel = micro_for(" ".join(str(shot.get(k) or "") for k in ("emotion", "expression")))
        out["extra"] = (prof["micro"] + (f" For this feeling: {feel}." if feel else "")) if video else prof["still"]
    return out


def drift_for(project: dict, shot: dict) -> dict | None:
    """Micro-animation for a moving still: only when the shot has people (a landscape doesn't breathe)."""
    if not (project.get("performance") or {}) or not shot.get("performers"):
        return None
    return PROFILES[resolve(project, shot)[0]]["drift"]


def get(d: str) -> dict:
    p = _read(os.path.join(d, "project.json"), {})
    dance = {str(k): v for k, v in (p.get("dance_shots") or {}).items() if v in ("on", "off")}
    return {"profiles": [{"id": k, "label": v["label"], "blurb": v["blurb"]} for k, v in PROFILES.items()], **settings(p), "dance": dance}


def set_(d: str, data: dict) -> dict:
    path = os.path.join(d, "project.json")
    p = _read(path, {})
    cur = settings(p)
    cur.pop("set", None)
    if "default" in data:
        if data["default"] not in PROFILES:
            raise SystemExit("Unknown performance profile.")
        cur["default"] = data["default"]
    for scope in ("scenes", "characters", "shots"):
        for k, v in (data.get(scope) or {}).items():
            if v in (None, "", "inherit"):
                cur[scope].pop(str(k), None)
            elif v in PROFILES:
                cur[scope][str(k)] = v
            else:
                raise SystemExit("Unknown performance profile.")
    p = _read(path, {})
    if cur.get("scenes") or cur.get("characters") or cur.get("shots") or "default" in data or p.get("performance"):
        p["performance"] = cur
    # dance direction per shot ("on" always, "off" never, "auto" = the shot's own text decides). Kept apart from the acting profile: choosing it must not switch acting on for the project.
    if "dance" in data:
        dance = dict(p.get("dance_shots") or {})
        for k, v in (data.get("dance") or {}).items():
            if v in (None, "", "auto"):
                dance.pop(str(k), None)
            elif v in ("on", "off"):
                dance[str(k)] = v
            else:
                raise SystemExit("Choose automatic, always or never.")
        p["dance_shots"] = dance
    _write(path, p)
    return get(d)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="pulseframe-performance")
    ap.add_argument("action", choices=["get", "set"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    try:
        res = get(a.project) if a.action == "get" else set_(a.project, json.loads(a.data))
        print(json.dumps({"event": "result", "data": res}), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except Exception as e:
        print(json.dumps({"event": "error", "message": f"{type(e).__name__}: {e}"}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
