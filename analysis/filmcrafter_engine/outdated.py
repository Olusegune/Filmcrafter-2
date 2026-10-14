"""What in the film may be out of date because a voice or the planned sound changed after it was made. Free and read-only: it never changes, deletes or re-makes anything.

Three kinds of finding:
  takes   a video take was made to follow one voice recording (the exact recordings are kept with the take: `voice_ref`) and the shot's voice is not that any more (replaced, removed or added).
          A take made before this was recorded, or made without a recording, is not judged: nothing is claimed about it.
  cues    a planned sound (audio cue) whose sound was replaced or taken out, or whose shot changed length or is gone (see audiocues.py).
  film    the finished film was exported before the voices, the plan or the sounds last changed, so its sound may not match any more.

An approved or locked take is never touched: it is reported with a note that it is kept until you choose. What to do about a finding is always the person's choice and always shows its price first:
the Studio's own "Lip-sync this take..." (re-times the mouth to the new voice), or making a new take.

  python -m filmcrafter_engine.outdated report <film_dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

EXPORT_GRACE_S = 2.0


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


def _film(d: str) -> None:
    m = None
    try:
        with open(os.path.join(d, "film.json"), encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError):
        pass
    if not isinstance(m, dict) or "story" not in m:
        raise SystemExit("That isn't a FilmCrafter film.")


def current_voice(film: str, shot_id: str) -> list[dict]:
    """The recordings the shot has now, as the film itself holds them: [{sha1, speaker, source}]. Free; reads the files."""
    from . import voiceover as V
    st = next((s for s in V.status(film)["shots"] if s["id"] == shot_id), None)
    out = []
    for p in (st or {}).get("people", []):
        rec = p.get("recording")
        path = V.inside(film, rec["file"]) if rec else None
        if path and os.path.isfile(path):
            with open(path, "rb") as f:
                out.append({"sha1": hashlib.sha1(f.read(), usedforsecurity=False).hexdigest(), "speaker": p["name"], "source": rec.get("source") or "recording"})
    return out


def _take_findings(film: str) -> tuple[list[dict], int]:
    from . import library, make
    rd = make.render_dir(film)
    if not os.path.isfile(os.path.join(rd, "jobs.json")):
        return [], 0
    from .render import Store, _load_plan
    plan_name, plan = _load_plan(rd)
    jobs = Store(rd).jobs
    state = library.shot_state(rd)
    rows, unchecked = [], 0
    for sc in plan.get("scenes", []):
        for sh in sc.get("shots", []):
            sid = sh["id"]
            take = library.chosen_take(rd, sid, plan_name, jobs, state)
            if not take or take.get("provider") == "own" or take.get("media_kind") == "image" or take.get("kind", "video") not in ("video", "lipsync"):
                continue
            ref = take.get("voice_ref")
            if not ref:
                unchecked += 1
                continue
            then = sorted(r["sha1"] for r in ref.get("recordings", []))
            now = current_voice(film, sid)
            if sorted(r["sha1"] for r in now) == then:
                continue
            kept = bool(state.get(sid, {}).get("approved") or state.get(sid, {}).get("locked"))
            who = sorted({r["speaker"] for r in now} | {r.get("speaker") for r in ref.get("recordings", []) if r.get("speaker")})
            if not now:
                kind, why = "voice_removed", "The voice this take was made to follow has been taken off the shot."
            elif not then:
                kind, why = "voice_added", "A voice was added after this take was made without one."
            else:
                kind, why = "voice_changed", "The voice was replaced after this take was made, so the mouth may not match it."
            rows.append({"shot": sid, "take": take["id"], "kind": kind, "why": why, "speakers": [w for w in who if w], "kept": kept,
                         "options": ["lipsync_pass", "new_take"], "note": "This take is approved or locked: it is kept until you choose." if kept else ""})
    return rows, unchecked


def _latest_export(film: str) -> tuple[str | None, float]:
    from . import make
    folder = os.path.join(make.render_dir(film), "exports")
    best, t = None, 0.0
    if os.path.isdir(folder):
        for f in os.listdir(folder):
            p = os.path.join(folder, f)
            if f.lower().endswith(".mp4") and os.path.isfile(p) and os.path.getmtime(p) > t:
                best, t = f, os.path.getmtime(p)
    return best, t


def _changes_after(film: str, since: float) -> list[str]:
    """What about the film's sound was changed (by the app's own records) after `since`. Uses the times written inside the records, which survive copying a film."""
    from . import audiocues as Q
    from . import audiolib as AL
    out = []
    try:
        lst = Q.listing(film)
    except SystemExit:
        lst = {"cues": []}
    if any((c.get("updated") or 0) > since + EXPORT_GRACE_S for c in lst["cues"]):
        out.append("the planned sound")
    try:
        lib = AL.load(film)
        if any((a.get("updated") or 0) > since + EXPORT_GRACE_S for a in lib["assets"]):
            out.append("a sound in the library")
    except SystemExit:
        pass
    from . import voiceover as V
    try:
        meta = V._meta(film)
        if any((e.get("added") or 0) > since + EXPORT_GRACE_S for rows in meta.get("shots", {}).values() for e in rows if isinstance(e, dict)):
            out.append("a voice")
    except (SystemExit, OSError):
        pass
    return out


def report(film: str) -> dict:
    """Everything that may be out of date, and what is left alone. See the module words."""
    from . import audiocues as Q
    _film(film)
    takes, unchecked = _take_findings(film)
    cues = [{"id": c["id"], "scene": c["scene"], "shot": c["shot"], "name": c.get("asset_name") or (c.get("plan") or {}).get("description") or "A sound", "why": c["fresh"][0]["why"], "codes": [f["code"] for f in c["fresh"]]}
            for c in Q.listing(film)["cues"] if c["fresh"]]
    name, when = _latest_export(film)
    film_row = None
    if name:
        what = _changes_after(film, when)
        if what:
            film_row = {"export": name, "changed": what, "why": f"The finished film was exported before {', '.join(what)} changed, so its sound may not match any more. Export it again."}
    return {"takes": takes, "cues": cues, "film": film_row, "unchecked_takes": unchecked, "clean": not takes and not cues and not film_row}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="outdated")
    ap.add_argument("action", choices=["report"])
    ap.add_argument("film")
    a = ap.parse_args(argv)
    try:
        emit(event="result", data=report(os.path.abspath(a.film)))
        return 0
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
