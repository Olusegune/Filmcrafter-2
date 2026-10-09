"""Director Command actions: render / keyframe / lip-sync / lock / use-latest, parsed from plain English.

"Regenerate shot 12 using Kling", "render the second chorus on fal with Veo", "keyframes for scene 4",
"re-render all failed shots", "lock this shot". Parsing is local (free, predictable) and nothing runs here:
the app shows what would happen and the estimated price, and acts only after you confirm. Notes that aren't
actions ("make the chorus warmer") go to the Director (re-direction), as before.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

from . import router
from .library import _plan, chosen_take, shot_state

VERB = re.compile(r"^\s*(please\s+)?(?P<verb>re-?generate|re-?render|render|redo|re-?do|generate|make|create|lip-?sync|lock|unlock|"
                  r"approve|use)\b", re.I)
ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "last": -1, "final": -1,
       "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5}
SECTION_WORDS = ["pre-chorus", "chorus", "verse", "bridge", "intro", "outro", "hook", "breakdown", "drop", "interlude", "post-chorus"]


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _num_list(s: str) -> list[int]:
    """"12", "3, 5 and 9", "12-15", "12 to 15" -> numbers."""
    out = []
    for m in re.finditer(r"(\d+)(?:\s*(?:-|–|to|through)\s*(\d+))?", s):
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        out += list(range(min(a, b), max(a, b) + 1))
    return out


def targets(d: str, text: str, selected: str | None, playhead: float | None) -> tuple[list[str], str]:
    """Shot ids the note points at, and a human description of them."""
    _, plan = _plan(d)
    shots = sorted((s for sc in plan["scenes"] for s in sc["shots"]), key=lambda s: s["start"])
    ids = [s["id"] for s in shots]
    t = text.lower()
    # explicit ids: S04-02, 4-02
    explicit = [f"S{int(a):02d}-{int(b):02d}" for a, b in re.findall(r"\bs?(\d{1,2})-(\d{2})\b", t)]
    explicit = [i for i in explicit if i in ids]
    if explicit:
        return explicit, ", ".join(explicit)
    if re.search(r"\b(this|selected|current)\s+shot\b|\bit\b", t) and selected in ids:
        return [selected], selected
    if re.search(r"\b(shot|shots)\s+(at|under)\s+the\s+playhead\b", t) and playhead is not None:
        hit = next((s["id"] for s in shots if s["start"] <= playhead < s["end"]), None)
        if hit:
            return [hit], hit
    m = re.search(r"\bshots?\s+((?:\d+\s*(?:-|–|to|through|,|and|&)?\s*)+)", t)
    if m:
        nums = _num_list(m.group(1))
        got = [ids[n - 1] for n in nums if 1 <= n <= len(ids)]
        if got:
            return got, f"shot{'s' if len(got) > 1 else ''} {m.group(1).strip()} ({', '.join(got)})"
    m = re.search(r"\bscenes?\s+((?:\d+\s*(?:-|–|to|through|,|and|&)?\s*)+)", t)
    if m:
        nums = set(_num_list(m.group(1)))
        got = [s["id"] for sc in plan["scenes"] if sc["number"] in nums for s in sc["shots"]]
        if got:
            return got, f"scene {m.group(1).strip()}"
    sm = _read(os.path.join(d, "songmap.json"), {}) or {}
    for word in SECTION_WORDS:
        mm = re.search(rf"\b(?:(first|second|third|fourth|fifth|last|final|1st|2nd|3rd|4th|5th)\s+)?{word}s?(?:\s+(\d+))?\b", t)
        if not mm:
            continue
        secs = [s for s in sm.get("sections", []) if re.sub(r"[\s_]+", "-", s["label"].lower()).startswith(word)
                and not (word == "chorus" and "pre" in s["label"].lower())]
        if not secs:
            continue
        n = ORD[mm.group(1)] if mm.group(1) else int(mm.group(2)) if mm.group(2) else None
        if n is None:
            pick = secs
        elif n == -1:
            pick = secs[-1:]
        else:
            pick = secs[n - 1:n]
        got = [s["id"] for s in shots if any(p["start"] <= s["start"] < p["end"] for p in pick)]
        if got:
            return got, (mm.group(0) if n is not None else f"every {word}")
    st = shot_state(d)
    jobs = (_read(os.path.join(d, "jobs.json"), {"jobs": []}) or {"jobs": []})["jobs"]
    plan_name, _ = _plan(d)
    if re.search(r"\bfailed\b", t):
        latest = {}
        for j in sorted(jobs, key=lambda j: j["created"]):
            if j["plan"] == plan_name and j.get("kind", "video") != "image" and j["state"] != "dismissed":
                latest[j["shot_id"]] = j
        got = [i for i in ids if latest.get(i, {}).get("state") in ("failed", "uncertain")]
        return got, "failed shots"
    if re.search(r"\b(unrendered|remaining|missing|not rendered|empty)\b", t):
        got = [i for i in ids if not chosen_take(d, i, plan_name, jobs, st)]
        return got, "shots without a video yet"
    if re.search(r"\b(all|every|everything|whole video)\b", t):
        return ids, "every shot"
    return [], ""


def parse(d: str, text: str, selected: str | None = None, playhead: float | None = None) -> dict:
    m = VERB.match(text)
    noun = re.match(r"^\s*(new\s+)?(keyframes?|stills?|renders?|takes?|versions?|lip-?sync)\s+(for|of|on)\b", text, re.I)
    if not m and not noun:
        return {"type": "direction"}
    verb = m.group("verb").lower().replace("-", "") if m else "render"
    t = text.lower()
    if verb in ("make", "create", "generate") and not re.search(r"\b(keyframes?|stills?|renders?|videos?|takes?|versions?|lip-?sync)\b", t):
        return {"type": "direction"}  # "make the chorus warmer" is a note, not an action
    ids, what = targets(d, text, selected, playhead)
    if not ids and what:
        return {"type": "error", "message": f"There are no {what} right now."}
    if not ids:
        return {"type": "error", "message": "Which shots? Say e.g. “shot 12”, “S04-02”, “scene 4”, “the second chorus”, "
                                            "“this shot” or “all failed shots”."}
    st = shot_state(d)
    locked = [i for i in ids if st.get(i, {}).get("locked")]
    if verb in ("lock", "unlock"):
        return {"type": "action", "action": verb, "shots": ids, "what": what, "billable": False,
                "summary": f"{verb.title()} {what}."}
    if verb in ("approve", "use") and re.search(r"\bkeyframes?\b", t):
        from .library import pending_keyframes
        todo = sorted(pending_keyframes(d, ids))
        if not todo:
            return {"type": "error", "message": f"No new keyframes to approve for {what}."}
        return {"type": "action", "action": "approve_keyframes", "shots": todo, "what": what, "billable": False,
                "summary": f"Approve the newest keyframe for {len(todo)} shot{'s' if len(todo) > 1 else ''} in {what}. "
                           "Shots that already have an approved keyframe keep it."}
    if verb in ("approve", "use"):
        return {"type": "action", "action": "approve_latest", "shots": [i for i in ids if i not in locked], "what": what,
                "skipped": [{"id": i, "reason": "locked"} for i in locked], "billable": False,
                "summary": f"Use the newest finished version for {what}. This replaces the version currently in the video."}
    kind = "lipsync" if verb == "lipsync" or re.search(r"\blip-?sync\b", t) else \
        "image" if re.search(r"\b(keyframes?|stills?|first frames?|images?)\b", t) else "video"
    todo = [i for i in ids if i not in locked]
    skipped = [{"id": i, "reason": "locked"} for i in locked]
    family = router.find_family(text)
    provider = router.find_provider(text)
    try:
        if kind == "lipsync":
            from .render import AUTO_LIPSYNC
            p = provider or next((x for x in ("fal", "kie") if router.available(x)), None)
            if not p or p not in AUTO_LIPSYNC:
                raise SystemExit("Lip-sync needs a fal.ai or Kie.ai key in Settings.")
            route = {"provider": p, "model": AUTO_LIPSYNC[p], "label": "Lip-sync", "verified": router.VERIFIED.get((p, AUTO_LIPSYNC[p]))}
        else:
            if family and router.FAMILIES[family]["kind"] == "image":
                kind = "image"
            if kind == "image" and family and router.FAMILIES[family]["kind"] != "image":
                family = None  # "keyframe with Kling" makes no sense: use the image model
            route = router.route(family, provider, kind)
    except SystemExit as e:
        return {"type": "error", "message": str(e)}
    sources = {}
    if kind == "lipsync":
        plan_name, _ = _plan(d)
        jobs = (_read(os.path.join(d, "jobs.json"), {"jobs": []}) or {"jobs": []})["jobs"]
        for i in list(todo):
            take = chosen_take(d, i, plan_name, jobs, st)
            if take:
                sources[i] = take["id"]
            else:
                todo.remove(i)
                skipped.append({"id": i, "reason": "no finished video to lip-sync"})
    if not todo:
        return {"type": "error", "message": "Nothing to do: " + "; ".join(f"{s['id']} ({s['reason']})" for s in skipped)}
    warning = None
    if kind == "video":  # start-frame models without a keyframe animate the reference image itself
        from .render import approved_keyframe, capabilities, manifest
        try:
            man = manifest(route["provider"], route["model"])
            caps = man.get("caps") or capabilities(man["inputs"], man["roles"])
            plan_name, _ = _plan(d)
            missing = [i for i in todo if not approved_keyframe(d, plan_name, i)]
            if caps["first_frame"] and not caps["image_refs"] and missing:
                warning = (f"{route['label']} starts from a single image. {len(missing)} of these shots have no approved keyframe, "
                           "so it would animate a reference image instead. Make keyframes first (say “keyframes for …”), "
                           "or use Seedance, which takes several references.")
        except (SystemExit, Exception):
            pass
    noun = {"video": "Render", "image": "Make keyframes for", "lipsync": "Lip-sync"}[kind]
    return {"type": "action", "action": "render", "render_kind": kind, "shots": todo, "skipped": skipped, "what": what,
            "provider": route["provider"], "model": route["model"], "label": route["label"], "verified": route["verified"],
            "sources": sources, "billable": route["provider"] != "comfyui", "warning": warning,
            "summary": f"{noun} {what} with {route['label']} on {router.PROVIDER_NAMES[route['provider']]}."
                       + (" New versions are added; the versions in the video stay until you choose." if kind != "image" else "")}


def main(argv):
    ap = argparse.ArgumentParser(prog="pulseframe-actions")
    ap.add_argument("project"); ap.add_argument("--note", required=True)
    ap.add_argument("--selected"); ap.add_argument("--playhead", type=float)
    a = ap.parse_args(argv)
    try:
        print(json.dumps({"event": "result", "data": parse(a.project, a.note, a.selected, a.playhead)}), flush=True)
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except Exception as e:
        print(json.dumps({"event": "error", "message": f"{type(e).__name__}: {e}"}), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
