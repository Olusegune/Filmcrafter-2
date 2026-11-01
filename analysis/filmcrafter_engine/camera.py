"""Camera and lighting you choose, shot by shot: shot size, angle, movement, lens, lighting, focus (including rack focus).

The Director writes each shot's framing, lens, movement and lighting as free text. This gives you named choices on top of that, and the
Director the same vocabulary to write with. A choice replaces the Director's wording for that one thing when the prompt is built; the
Director's plan itself is never changed, and clearing a choice puts the Director's wording back.

  <project>/camera.json   {shot_id: {"size", "angle", "movement", "lens", "lighting", "focus", "energy": <term id>, "at": <time>}}

Each term has a plain label, the wording sent to the video model, and (for the Director's own text) words that identify it, so the
picker can show which term the Director already chose. Movement and rack focus only mean something over time, so they are sent to
video models and left out of still keyframes.

  python -m filmcrafter_engine.camera <vocab|get|set|reset> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

# (id, label, wording sent to the model, regex that recognises it in the Director's text)
SIZE = [
    ("extreme_wide", "Extreme wide", "extreme wide establishing shot, the people tiny in the space", r"extreme wide|establishing|\bews\b|aerial wide"),
    ("wide", "Wide", "wide shot showing the whole space and the people in it", r"\bwide\b|\bws\b|long shot"),
    ("full", "Full body", "full shot, the whole body head to toe", r"full shot|full[- ]body|\bfs\b|head to toe"),
    ("medium", "Medium", "medium shot, waist up", r"medium shot|\bms\b|waist[- ]up|\bmid shot|\bmedium\b(?! close)"),
    ("medium_close", "Medium close-up", "medium close-up, chest up", r"medium close|\bmcu\b|chest[- ]up|head and shoulders"),
    ("close", "Close-up", "close-up on the face", r"(?<!medium )(?<!extreme )close[- ]up|\bcu\b|tight on"),
    ("extreme_close", "Extreme close-up", "extreme close-up on a detail (eyes, lips or hands)", r"extreme close|\becu\b|macro detail"),
    ("insert", "Insert / detail", "insert shot of a single object or detail", r"insert|\bdetail shot|cutaway"),
]
ANGLE = [
    ("eye", "Eye level", "camera at eye level, neutral angle", r"eye[- ]level|neutral angle"),
    ("low", "Low angle", "low angle looking up, the subject imposing", r"low[- ]angle|from below|hero low|looking up"),
    ("high", "High angle", "high angle looking down, the subject smaller", r"high[- ]angle|from above(?! overhead)|looking down"),
    ("overhead", "Overhead", "overhead top-down view, straight down", r"overhead|top[- ]down|bird'?s[- ]eye|god'?s[- ]eye"),
    ("dutch", "Tilted (Dutch)", "Dutch angle, the horizon tilted for unease", r"dutch|canted|tilted horizon|tilted angle"),
    ("ots", "Over the shoulder", "over-the-shoulder, the foreground shoulder soft and the face in focus", r"over[- ]the[- ]shoulder|\bots\b"),
    ("pov", "Point of view", "point-of-view shot from the character's eyes", r"\bpov\b|point[- ]of[- ]view|first[- ]person"),
]
MOVEMENT = [
    ("static", "Locked off", "locked-off static camera, no movement", r"locked[- ]off|static camera|\bstatic\b|tripod|still camera"),
    ("push", "Slow push in", "slow push-in toward the subject", r"push[- ]in|push in|dolly in|slow zoom in|move in|creep"),
    ("pull", "Pull back", "slow pull-back that widens the frame", r"pull[- ]back|pullback|pull out|dolly out|zoom out"),
    ("whip", "Whip pan", "fast whip pan with motion blur", r"whip[- ]pan|swish pan"),
    ("zoom", "Snap zoom", "sudden snap zoom into the subject", r"snap zoom|crash zoom|rapid zoom"),
    ("gimbal", "Steadicam / gimbal", "smooth Steadicam move floating through the space", r"steadicam|gimbal|floating move"),
    ("handheld", "Handheld", "handheld camera with natural, organic movement", r"handheld|hand[- ]held|shaky"),
    ("orbit", "Orbit / arc", "camera arcs around the subject", r"orbit|arc(s|ing)? around|circl(e|ing) (the|around)|360"),
    ("crane", "Crane", "sweeping crane move rising or descending", r"crane|jib|boom (up|down)"),
    ("drone", "Drone / aerial", "aerial drone move high over the scene", r"drone|aerial"),
    ("tilt", "Tilt", "smooth tilt up or down", r"\btilt (up|down)|tilting"),
    ("pan", "Pan", "smooth pan across the scene", r"\bpan\b|panning|pans (left|right)"),
    ("track", "Tracking / follow", "tracking shot following the subject at their pace", r"tracking|follow(ing)? shot|trucking|tracks (her|him|them|the)"),
    ("dolly", "Dolly", "smooth dolly move alongside the action", r"\bdolly\b(?! in| out)|dolly (left|right|along)"),
]
LENS = [
    ("ultrawide", "Ultra-wide 16mm", "16mm ultra-wide lens with strong perspective", r"16 ?mm|ultra[- ]wide"),
    ("wide_lens", "Wide 24mm", "24mm wide-angle lens", r"\b2[0-8] ?mm|wide[- ]angle"),
    ("normal", "Natural 35-50mm", "35mm lens, a natural field of view", r"\b(35|40|50) ?mm|natural lens|normal lens"),
    ("portrait", "Portrait 85mm", "85mm portrait lens, flattering compression", r"\b(75|85|100) ?mm|portrait lens"),
    ("tele", "Telephoto 135mm+", "135mm telephoto lens, compressed background", r"\b(135|150|200|300) ?mm|telephoto|long lens"),
    ("anamorphic", "Anamorphic", "anamorphic lens with oval bokeh and horizontal flares", r"anamorphic"),
    ("fisheye", "Fisheye", "fisheye lens with a curved, distorted edge", r"fisheye"),
    ("macro", "Macro", "macro lens, extreme detail at very close range", r"macro"),
    ("tiltshift", "Tilt-shift", "tilt-shift lens, a thin plane of focus like a miniature", r"tilt[- ]shift"),
]
LIGHTING = [
    ("daylight", "Natural daylight", "natural daylight, soft and even", r"daylight|natural light|sunlit|available light"),
    ("golden", "Golden hour", "golden hour sunlight, warm low rays and long shadows", r"golden hour|magic hour|sunset|sunrise|warm low sun"),
    ("blue", "Blue hour / dusk", "blue hour dusk light, cool and soft", r"blue hour|dusk|twilight"),
    ("overcast", "Soft overcast", "soft overcast light, no hard shadows", r"overcast|soft light|diffused"),
    ("highkey", "High key", "bright high-key lighting, few shadows", r"high[- ]key|bright and clean|clean high"),
    ("lowkey", "Low key / chiaroscuro", "low-key chiaroscuro lighting, deep shadows and a single pool of light", r"low[- ]key|chiaroscuro|deep shadows|moody dark"),
    ("rim", "Rim / backlit", "strong rim light and backlight outlining the subject", r"rim[- ]?light|rim[- ]lit|backlit|backlight|contre[- ]jour"),
    ("silhouette", "Silhouette", "the subject in silhouette against a bright background", r"silhouette"),
    ("hardkey", "Single hard key", "one hard key light with sharp shadows", r"hard key|single key|hard light|harsh light"),
    ("neon", "Neon / coloured gels", "coloured neon and gel lighting, saturated magenta and cyan", r"neon|gel(s|led)?|coloured light|colored light"),
    ("practical", "Warm practicals", "warm practical lamps and tungsten glow", r"practical|tungsten|lamp ?light|string lights"),
    ("fire", "Candle / firelight", "flickering candlelight or firelight, warm and intimate", r"candle|firelight|fire ?light|bonfire"),
    ("moon", "Moonlight / night", "cool moonlit night, deep blue shadows", r"moonlight|moonlit|night exterior|night scene"),
    ("haze", "Volumetric haze", "volumetric haze with visible beams of light", r"volumetric|haze|god rays|light shafts|smoke"),
    ("stage", "Stage spotlight", "theatrical stage spotlight with a dark surround", r"spotlight|stage light|follow ?spot|stage lighting"),
    ("window", "Soft window light", "soft window light falling across the room, gentle shadows", r"window light|light from the window|through the (?:window|blinds|curtains)"),
    ("noon", "Hard midday sun", "hard midday sun, short sharp shadows and bright highlights", r"midday sun|noon sun|harsh sun|overhead sun|high sun"),
    ("dappled", "Dappled light", "dappled light through leaves, moving spots of sun and shade", r"dappled|through (?:the )?leaves|leaf shadows"),
    ("split", "Warm and cool split", "split lighting, warm on one side of the face and cold on the other", r"split light|warm and cool|warm against cool|teal and orange"),
    ("fluorescent", "Cold fluorescent", "cold flat fluorescent light, greenish and unflattering", r"fluorescent|strip light|neon tube|office light"),
    ("toplight", "Top light / interrogation", "one lamp from directly above, eyes lost in shadow, an interrogation-room look", r"top ?light|overhead lamp|interrogation|from directly above"),
    ("underlit", "Under-lit / ominous", "under-lit, light from below throwing the face into unnatural shadow", r"under[- ]?lit|lit from below|uplight|up-light|flashlight under"),
    ("sodium", "Sodium streetlamp", "orange sodium-vapour street lighting with deep blue-black shadows", r"sodium|streetlamp|street lamp|street light|orange street"),
]
FOCUS = [
    ("shallow", "Shallow focus", "shallow depth of field, a sharp subject and creamy blurred background", r"shallow (focus|depth)|bokeh|creamy background"),
    ("deep", "Deep focus", "deep focus, everything from foreground to background sharp", r"deep focus|deep depth|everything in focus"),
    ("soft", "Soft / dreamy", "soft dreamy focus with a gentle glow", r"soft focus|dreamy|halation|diffusion"),
    ("rack", "Rack focus", "starts with the foreground sharp and the background soft, then racks focus smoothly to the subject behind", r"rack focus|pull focus|focus pull|racks? focus"),
    ("follow", "Follow focus", "focus follows the moving performer and stays sharp on them", r"follow focus|focus follows|tracks focus"),
]
ENERGY = [("still", "Still", "", r"^still$"), ("gentle", "Gentle", "", r"^gentle$"), ("moderate", "Moderate", "", r"^moderate$"), ("kinetic", "Kinetic", "", r"^kinetic$")]
VIDEO_ONLY = {"movement": {t[0] for t in MOVEMENT}, "focus": {"rack", "follow"}}      # only meaningful over time
GROUPS = {"size": SIZE, "angle": ANGLE, "movement": MOVEMENT, "lens": LENS, "lighting": LIGHTING, "focus": FOCUS, "energy": ENERGY}
GROUP_LABELS = {"size": "Shot size", "angle": "Angle", "movement": "Movement", "lens": "Lens", "lighting": "Lighting", "focus": "Focus", "energy": "Energy"}
FIELDS = {"size": "framing", "angle": "framing", "movement": "camera_movement", "lens": "lens", "lighting": "lighting", "focus": "focus", "energy": "camera_energy"}
_RX = {g: [(t[0], re.compile(t[3], re.I)) for t in terms] for g, terms in GROUPS.items()}


def vocab() -> dict:
    """The choices, for the picker and the Director: {group: {label, terms: [{id, label, video_only}]}}."""
    return {g: {"label": GROUP_LABELS[g], "terms": [{"id": t[0], "label": t[1], "video_only": t[0] in VIDEO_ONLY.get(g, ())} for t in terms]}
            for g, terms in GROUPS.items()}


def director_vocabulary_text() -> str:
    """One compact paragraph of the same terms, for the Director's instructions."""
    def names(terms):
        return ", ".join(t[1].lower() for t in terms)
    return ("Write framing, lens, camera movement and lighting with concrete cinematography terms. Shot sizes: " + names(SIZE) + ". Angles: " + names(ANGLE)
            + ". Movements: " + names(MOVEMENT) + ". Lenses: " + names(LENS) + ". Lighting: " + names(LIGHTING) + ". Focus: " + names(FOCUS)
            + ". Use a rack focus when attention moves from one subject to another in a shot, and vary sizes and angles across a scene instead of repeating one.")


def detect(text: str, group: str) -> str | None:
    """Which term of a group the Director's wording already names (the first that matches), or None."""
    text = str(text or "")
    for tid, rx in _RX[group]:
        if rx.search(text):
            return tid
    return None


def _wording(group: str, tid: str) -> str:
    return next((t[2] for t in GROUPS[group] if t[0] == tid), "")


def _path(d: str) -> str:
    return os.path.join(d, "camera.json")


def _load(d: str) -> dict:
    try:
        with open(_path(d), encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def _save(d: str, data: dict) -> None:
    tmp = _path(d) + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, _path(d))


def _valid(group: str, tid) -> str | None:
    if tid in (None, ""):
        return None
    if group not in GROUPS or not any(t[0] == tid for t in GROUPS[group]):
        raise SystemExit(f"\"{tid}\" isn't a {GROUP_LABELS.get(group, group).lower()} choice.")
    return tid


def picked(d: str, shot_id: str) -> dict:
    return {k: v for k, v in (_load(d).get(shot_id) or {}).items() if k in GROUPS}


def apply(d: str, shot: dict) -> dict:
    """The shot with your choices written over the Director's wording (a copy; nothing is saved). Used when a prompt is built."""
    p = picked(d, shot.get("id", ""))
    if not p:
        return shot
    out = dict(shot)
    if "size" in p or "angle" in p:
        # one framing sentence from the chosen size and angle; a part you didn't choose keeps what the Director chose, if it named one
        parts = []
        for g in ("size", "angle"):
            tid = p.get(g) or detect(shot.get("framing", ""), g)
            if tid:
                parts.append(_wording(g, tid))
        out["framing"] = ", ".join(parts) or shot.get("framing", "")
    if "movement" in p:
        out["camera_movement"] = _wording("movement", p["movement"])
        out["camera_moves"] = []
    if "lens" in p:
        out["lens"] = _wording("lens", p["lens"])
    if "lighting" in p:
        # a lighting plan (lighting.py) writes a fuller description with the choice; a lighting you pick yourself later replaces it
        out["lighting"] = ((_load(d).get(shot.get("id", "")) or {}).get("lighting_text")) or _wording("lighting", p["lighting"])
    if "energy" in p:
        out["camera_energy"] = p["energy"]
    if "focus" in p:
        w = _wording("focus", p["focus"])
        if p["focus"] in VIDEO_ONLY["focus"]:
            out["focus_motion"] = w        # sent to video models only
            out.pop("focus", None)
        else:
            out["focus"] = w
    return out


def get(d: str, shot_id: str) -> dict:
    from .planio import find_shot as _shot, load_plan as _load_plan
    _, plan = _load_plan(d)
    shot, _sc = _shot(plan, shot_id)
    if not shot:
        raise SystemExit("That shot isn't in the plan.")
    p = picked(d, shot_id)
    director = {"framing": shot.get("framing", ""), "lens": shot.get("lens", ""),
                "movement": shot.get("camera_movement") or ", ".join(shot.get("camera_moves") or []), "lighting": shot.get("lighting", ""),
                "energy": shot.get("camera_energy", "")}
    detected = {"size": detect(director["framing"], "size"), "angle": detect(director["framing"], "angle"), "movement": detect(director["movement"], "movement"),
                "lens": detect(director["lens"], "lens"), "lighting": detect(director["lighting"], "lighting"),
                "focus": detect(" ".join([director["movement"], shot.get("visual_prompt", ""), director["lens"]]), "focus"),
                "energy": director["energy"] if any(director["energy"] == t[0] for t in ENERGY) else None}
    eff = apply(d, shot)
    at = (_load(d).get(shot_id) or {}).get("at")
    jobs = []
    try:
        with open(os.path.join(d, "jobs.json"), encoding="utf-8") as f:
            jobs = json.load(f).get("jobs", [])
    except (OSError, ValueError):
        pass
    takes = [j for j in jobs if j.get("shot_id") == shot_id and j.get("state") == "ready" and j.get("kind", "video") != "image"]
    newest = max((float(j.get("created") or 0) for j in takes), default=0)
    return {"shot": shot_id, "picked": p, "detected": detected, "director": director, "effective": {"framing": eff.get("framing", ""),
            "movement": eff.get("camera_movement", ""), "lens": eff.get("lens", ""), "lighting": eff.get("lighting", ""),
            "focus": eff.get("focus") or eff.get("focus_motion") or ""},
            "changed_since_take": bool(p and at and takes and newest < at)}


def set_picks(d: str, shot_ids: list[str], picks: dict) -> dict:
    """Set (or, with "" / null, clear) any of the groups on one or more shots."""
    from .planio import find_shot as _shot, load_plan as _load_plan
    _, plan = _load_plan(d)
    ids = [s for s in dict.fromkeys(shot_ids or []) if isinstance(s, str)][:400]
    if not ids:
        raise SystemExit("Choose a shot.")
    for s in ids:
        if not _shot(plan, s)[0]:
            raise SystemExit(f"{s} isn't in the plan.")
    clean = {}
    for g, v in (picks or {}).items():
        if g in GROUPS:
            clean[g] = _valid(g, v)
    data = _load(d)
    for s in ids:
        cur = {k: v for k, v in (data.get(s) or {}).items() if k in GROUPS}
        text = (data.get(s) or {}).get("lighting_text")
        if text and "lighting" not in clean:
            cur["lighting_text"] = text                 # the plan's wording stays with its choice until you pick another light
        for g, v in clean.items():
            if v is None:
                cur.pop(g, None)
            else:
                cur[g] = v
        if "lighting" not in cur:
            cur.pop("lighting_text", None)
        if cur:
            data[s] = {**cur, "at": time.time()}
        else:
            data.pop(s, None)
    _save(d, data)
    return {"changed": ids, "shot": get(d, ids[0])}


def reset(d: str, shot_ids: list[str]) -> dict:
    data = _load(d)
    for s in shot_ids or []:
        data.pop(s, None)
    _save(d, data)
    return {"changed": list(shot_ids or [])}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-camera")
    ap.add_argument("action", choices=["vocab", "get", "set", "reset", "suggest", "suggest_apply"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "vocab":
            res = vocab()
        elif a.action == "get":
            res = get(a.project, x["shot"])
        elif a.action == "set":
            res = set_picks(a.project, x.get("shots") or [x.get("shot")], x.get("picks") or {})
        elif a.action == "suggest":
            from .looks import suggest
            res = suggest(a.project)
        elif a.action == "suggest_apply":
            from .looks import suggest_apply
            res = suggest_apply(a.project, x.get("shots") or [])
        else:
            res = reset(a.project, x.get("shots") or [x.get("shot")])
        print(json.dumps({"event": "result", "data": res}), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except Exception as e:
        print(json.dumps({"event": "error", "message": __import__("filmcrafter_engine.errtext", fromlist=["plain"]).plain(e)}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
