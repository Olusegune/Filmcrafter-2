"""What would be different if this shot were rendered again: the request that made its last take compared with the request that would be sent now. Free; nothing is sent anywhere.

A video model gives a different take every time, so a re-render is only worth paying for when something it is told or shown has changed. This lists exactly what has: the model, the first frame,
the pictures and the song's vocal it is given, the length, and each sentence of the prompt that was added or removed.
"""
from __future__ import annotations

import re

MAX_LINES = 8
MAX_LEN = 170


def sentences(text: str) -> list[str]:
    """A prompt as its sentences, whitespace tidied, in order."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(])", " ".join(str(text or "").split()))
    return [p.strip() for p in parts if p.strip()]


def prompt_diff(old: str, new: str) -> tuple[list[str], list[str]]:
    """(added, removed) sentences. Order changes alone are not a change: the model reads the same sentences."""
    a, b = sentences(old), sentences(new)
    sa, sb = set(a), set(b)
    return [x for x in b if x not in sa], [x for x in a if x not in sb]


def _short(s: str) -> str:
    return s if len(s) <= MAX_LEN else s[: MAX_LEN - 1].rstrip() + "…"


def _present(payload: dict, key) -> int:
    v = payload.get(key) if key else None
    return len(v) if isinstance(v, list) else (1 if v else 0)


def compare(take: dict, now: dict, man: dict) -> list[dict]:
    """The differences between the stored request of a take (job record) and the request that would be sent now (a preview). Each: {kind, text}."""
    old = take.get("payload") or {}
    new = now.get("payload") or {}
    roles = man.get("roles") or {}
    out: list[dict] = []
    if take.get("model") and now.get("manifest", {}).get("model") and take["model"] != now["manifest"]["model"]:
        out.append({"kind": "model", "text": f"A different model: the take was made with {take['model']}, the next would use {now['manifest']['title'] or now['manifest']['model']}."})
    k_old, k_new = take.get("keyframe_ref"), now.get("keyframe")
    if (k_old or None) != (k_new or None):
        out.append({"kind": "keyframe", "text": "A different keyframe." if (k_old and k_new) else ("The keyframe was removed." if k_old else "There is now an approved keyframe; the take was made without one.")})
    first = roles.get("first_frame")
    if bool(old.get(first)) != bool(new.get(first)) and first:
        out.append({"kind": "first_frame", "text": "The keyframe is now sent as the first frame." if new.get(first) else "The keyframe is no longer the first frame (it goes as a reference picture)."})
    audio = roles.get("ref_audio")
    if audio and bool(_present(old, audio)) != bool(_present(new, audio)):
        out.append({"kind": "audio", "text": "The song's vocal is now sent for the mouth to follow." if _present(new, audio) else "The song's vocal is no longer sent."})
    imgs = roles.get("ref_images")
    if imgs and _present(old, imgs) != _present(new, imgs):
        out.append({"kind": "references", "text": f"{_present(new, imgs)} reference picture{'s' if _present(new, imgs) != 1 else ''} are sent now, {_present(old, imgs)} before."})
    dur = roles.get("duration")
    if dur and old.get(dur) is not None and new.get(dur) is not None and str(old[dur]) != str(new[dur]):
        out.append({"kind": "length", "text": f"The take length changed from {old[dur]} to {new[dur]} s."})
    added, removed = prompt_diff(str(old.get(roles.get("prompt", "prompt")) or ""), str(new.get(roles.get("prompt", "prompt")) or ""))
    for s in removed[:MAX_LINES]:
        out.append({"kind": "prompt_removed", "text": _short(s)})
    for s in added[:MAX_LINES]:
        out.append({"kind": "prompt_added", "text": _short(s)})
    more = max(0, len(added) - MAX_LINES) + max(0, len(removed) - MAX_LINES)
    if more:
        out.append({"kind": "prompt_more", "text": f"…and {more} more prompt change{'s' if more != 1 else ''}."})
    return out


def since_last_take(d: str, shot_id: str, provider: str | None = None, model: str | None = None, overrides: dict | None = None) -> dict:
    from .render import Store, _load_plan, preview
    plan_name, _ = _load_plan(d)
    store = Store(d)
    takes = [j for j in store.jobs if j.get("shot_id") == shot_id and j.get("plan") == plan_name and j.get("state") == "ready" and j.get("kind", "video") == "video" and j.get("payload")]
    if not takes:
        return {"has_take": False, "same": False, "changes": [], "note": "This shot has no rendered take yet."}
    take = max(takes, key=lambda j: j.get("created", 0))
    if not (provider and model):
        provider, model = take.get("provider"), take.get("model")
    now = preview(d, shot_id, provider, model, overrides or {})
    changes = compare(take, now, now["manifest"])
    return {"has_take": True, "take": {"id": take["id"], "model": take.get("model"), "created": take.get("created")}, "same": not changes, "changes": changes,
            "note": "" if changes else "Nothing the model is told or shown has changed since this take, so a new render would look much the same (every render still varies a little)."}
