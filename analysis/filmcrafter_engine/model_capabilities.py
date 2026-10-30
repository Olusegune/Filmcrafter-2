"""What each model is known to do for a performance, and HOW we know it.

Every claim carries one of four labels, and a source:
  tested       a real render of this model was recorded (router.VERIFIED); says only that it renders, not that its acting is good
  documented   the provider's own published description (the model registry); says what it accepts, not how well it does it
  unverified   nothing recorded: do not rely on it
  unsupported  the provider says it does not

Nothing here is ever "verified" for acting quality, eye lines or emotion: no recorded evaluation of those exists, so they are always `unverified`. The labels only move when a real run is
recorded, and that needs your say-so and your credits.

Free and local; nothing is sent.
"""
from __future__ import annotations

# what a performance asks of a model, none of which has a recorded evaluation
ACTING_CLAIMS = (("follows_emotion_prompt", "Follows a written emotion"), ("holds_gaze", "Keeps a gaze direction"), ("timed_beats", "Follows timed beats inside one clip"),
                 ("keeps_face_across_shots", "Keeps the same face across shots"))


def _entry(provider: str, model: str) -> dict | None:
    from . import registry
    try:
        return registry.lookup(provider, model)
    except Exception:                                  # noqa: BLE001  a damaged registry file must not stop a screen
        return None


def describe(provider: str, model: str) -> dict:
    from . import router
    tested = router.VERIFIED.get((provider, model))
    ent = _entry(provider, model)
    caps = (ent or {}).get("capabilities") or {}
    rows = [{"feature": "renders", "label": "Makes the picture or video", "status": "tested" if tested else "unverified", "source": tested or "no recorded real render"}]
    if "direction_tags" in caps:
        ok = bool(caps["direction_tags"])
        rows.append({"feature": "direction_tags", "label": "Reads [tags] such as [whispers] as direction", "status": "documented" if ok else "unsupported",
                     "source": f"model registry, checked {(ent or {}).get('verified', 'unknown')}"})
    for key, label in (("native_audio", "Makes its own sound"), ("first_frame", "Starts from a picture"), ("last_frame", "Ends on a picture"), ("image_refs", "Takes reference pictures")):
        if key in caps:
            rows.append({"feature": key, "label": label, "status": "documented" if caps[key] else "unsupported", "source": f"model registry, checked {(ent or {}).get('verified', 'unknown')}"})
    rows += [{"feature": k, "label": label, "status": "unverified", "source": "no recorded evaluation"} for k, label in ACTING_CLAIMS]
    return {"provider": provider, "model": model, "known": ent is not None or bool(tested), "features": rows}


def summary(provider: str, model: str) -> str:
    """One honest line for a screen: what is tested and what is not."""
    d = describe(provider, model)
    t = [r["label"] for r in d["features"] if r["status"] == "tested"]
    return ("Tested: " + ", ".join(t) + ". " if t else "Not tested here. ") + "Acting quality is not verified for any model."
