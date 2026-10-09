"""Camera and lighting suggested by the feeling of a shot, for free.

A shot that is meant to feel like dread reads best in deep shadow with a camera that creeps closer; joy in warm, open light with a floating camera. The Director
writes each shot's emotion; this proposes lighting, camera movement, angle and focus to match, using only the terms of camera.py's vocabulary. It never overrules
a choice a person made, nor wording the Director already wrote for the same thing. Applying a suggestion writes it as a normal camera choice (camera.json), and clearing
that choice puts the Director's wording back.

  python -m pulseframe_analysis.camera suggest <project>
  python -m pulseframe_analysis.camera suggest_apply <project> --data '{"shots": ["S01-01"]}'
"""
from __future__ import annotations

import re

# (emotion words, {group: (term, calmer term for a quiet shot or None)}, why)
LOOKS = [
    (r"dread|fear|terror|anxi|tense|uneas|suspens|menac|panic|paranoi", {"lighting": ("lowkey", None), "movement": ("push", "static"), "angle": ("dutch", "eye")},
     "Fear and unease read in deep shadow and a camera that creeps closer."),
    (r"rage|anger|fury|furious|wrath|resent|defian|confront", {"lighting": ("hardkey", None), "movement": ("handheld", "push"), "angle": ("low", "eye")},
     "Anger reads in hard light, a restless camera and a looming low angle."),
    (r"grief|sad|sorrow|mourn|loss|lonel|heartbreak|despair|regret|melanchol", {"lighting": ("overcast", "blue"), "movement": ("static", None), "focus": ("shallow", None)},
     "Sorrow reads in flat, cool light and a camera that stays still and lets the face carry it."),
    (r"love|tender|intimate|longing|yearn|affection|romance|devotion|warmth", {"lighting": ("practical", "golden"), "movement": ("push", "dolly"), "focus": ("shallow", None)},
     "Tenderness reads in warm light, shallow focus and a slow drift toward the face."),
    (r"joy|joyful|happy|elat|celebrat|playful|delight|exuber|cheer|giddy|carefree", {"lighting": ("golden", "daylight"), "movement": ("gimbal", "dolly"), "angle": ("eye", None)},
     "Joy reads in warm, open light and a camera that floats and moves with the people."),
    (r"triumph|pride|proud|power|victor|resolve|determin|confident|hero|swagger", {"lighting": ("rim", None), "movement": ("crane", "push"), "angle": ("low", None)},
     "Triumph reads in backlight, a rising camera and a low, heroic angle."),
    (r"hope|wonder|awe|reverence|serene|peace|calm|relief|gratitude", {"lighting": ("golden", "overcast"), "movement": ("pull", "static"), "focus": ("soft", None)},
     "Hope and wonder read in golden light, a camera that widens and a soft glow."),
    (r"shame|embarrass|flustered|nervous|awkward|guilt|uncertain|hesitan|self-conscious", {"movement": ("handheld", "static"), "angle": ("eye", None), "focus": ("shallow", None)},
     "Awkwardness reads in a close, slightly unsteady camera at eye level."),
    (r"shock|surpris|startl|stunned|disbelief|astonish", {"movement": ("zoom", "push"), "lighting": ("hardkey", None)},
     "Shock reads in a sudden move toward the face and hard light."),
    (r"mischief|sly|scheming|smug|cunning|sarcas|teasing", {"lighting": ("lowkey", "practical"), "angle": ("low", None), "movement": ("track", "push")},
     "Mischief reads in shadow, a slightly low angle and a camera that follows closely."),
]
_RX = [(re.compile(r, re.I), m, w) for r, m, w in LOOKS]
FIELDS = ("lighting", "movement", "angle", "focus")
LOUD = 7                 # from this intensity a shot is loud enough for a restless move
QUIET = 4                # below this it is quiet: the calmer term is used


def _own_text(shot: dict, group: str) -> str:
    from .camera import FIELDS as SHOT_FIELDS
    if group == "movement":
        return " ".join([str(shot.get("camera_movement") or ""), ", ".join(str(m) for m in shot.get("camera_moves") or [])])
    if group in ("size", "angle"):
        return str(shot.get("framing") or "")
    return str(shot.get(SHOT_FIELDS[group]) or "")


def suggest_shot(shot: dict, picks: dict | None = None) -> dict | None:
    """What the feeling of this shot suggests, leaving out anything already chosen or already named by the Director. None when there is nothing to add."""
    from .camera import GROUPS, _wording, detect
    emotion = str(shot.get("emotion") or "").strip()
    if not emotion:
        return None
    try:
        intensity = int(shot.get("performance_intensity") or 5)
    except (TypeError, ValueError):
        intensity = 5
    look = next(((m, why) for rx, m, why in _RX if rx.search(emotion)), None)
    if not look:
        return None
    wants, why = look
    picks = picks or {}
    out = []
    for group in FIELDS:
        if group not in wants or picks.get(group) or detect(_own_text(shot, group), group):
            continue
        term, calm = wants[group]
        if calm and intensity < QUIET:
            term = calm
        elif calm and group == "movement" and intensity < LOUD and term in ("handheld", "zoom", "crane"):
            term = calm                                  # a restless move needs a loud shot
        label = next(t[1] for t in GROUPS[group] if t[0] == term)
        out.append({"group": group, "term": term, "label": label, "wording": _wording(group, term)})
    return {"shot": shot.get("id"), "emotion": emotion, "intensity": intensity, "why": why, "proposals": out} if out else None


def suggest(d: str) -> dict:
    """Free: suggestions for every shot that has a feeling and whose Director text and choices leave a gap."""
    from .camera import GROUPS, _load
    from .planio import load_plan as _load_plan
    try:
        _, plan = _load_plan(d)
    except SystemExit:
        return {"shots": [], "count": 0, "note": "There is no shot plan yet."}
    data = _load(d)
    rows = []
    for sc in plan.get("scenes", []):
        for sh in sc.get("shots", []):
            r = suggest_shot(sh, {g: v for g, v in (data.get(sh.get("id")) or {}).items() if g in GROUPS})
            if r:
                rows.append(r)
    return {"shots": rows, "count": len(rows), "note": "" if rows else "Every shot with a feeling already has its camera and lighting chosen, or has no feeling set."}


def suggest_apply(d: str, shot_ids: list[str]) -> dict:
    """Turn the suggestions for these shots into camera choices."""
    from .camera import set_picks
    todo = {r["shot"]: r for r in suggest(d)["shots"]}
    changed = []
    for sid in dict.fromkeys(s for s in (shot_ids or []) if isinstance(s, str)):
        r = todo.get(sid)
        if r:
            set_picks(d, [sid], {p["group"]: p["term"] for p in r["proposals"]})
            changed.append(sid)
    return {"changed": changed}
