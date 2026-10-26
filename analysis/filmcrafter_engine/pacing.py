"""Pacing: how the film's shots are cut together, and where the rhythm works against the story.

A film is made of its cuts. Too many long shots in a row feel slow, too many short ones feel frantic, a run of identical shot sizes feels flat, a line of dialogue that has no time to be said feels
rushed, a monologue with no cutaway feels static. This reads the shots as they are now (their lengths, sizes, dialogue and the transitions between them) and reports, scene by scene and for the film,
the rhythm and the places worth another look, each with a reason and a suggestion. It is advice only: it reads, it changes nothing.

  fix    a shot cannot do what it is meant to (not enough time for its own dialogue)
  look   worth a look (a very long or very short shot, four of the same size in a row, transitions used on every cut)
  note   for information (a scene much faster or slower than the rest, no wide shot to open a scene, a long exchange with no close-ups)

Free, local and read-only.

  python -m filmcrafter_engine.pacing report <film_dir>
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys

from . import safeio

WORDS_PER_SECOND = 2.5
DIALOGUE_PAD = 0.8                 # a breath before and after
MIN_SHOT = 1.2
LONG_SHOT = 12.0
RUN_SAME = 4
MONOLOGUE = 8.0
FAST, SLOW = 0.6, 1.6              # a scene whose average shot is below or above this share of the film's is called out
TRANSITION_SHARE = 0.3
ACTION_WORDS = re.compile(r"fight|chase|run|race|punch|kick|crash|explo|leap|jump|sprint|struggle|battle|escape", re.I)
SIZES_WIDE = ("establishing", "wide", "extreme wide")
SIZES_CLOSE = ("close-up", "extreme close-up", "over the shoulder")


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


def _film(d: str) -> None:
    m = safeio.read_json(os.path.join(d, "film.json"), None)
    if not isinstance(m, dict) or "story" not in m:
        raise SystemExit("That isn't a FilmCrafter film.")


def _contracts(d: str) -> list[dict]:
    from . import shots as S
    out = []
    for sid in S._index(d).get("order", []):
        c = S._read(S._cpath(d, sid))
        if isinstance(c, dict):
            out.append(c)
    return out


def _transitions(d: str) -> dict:
    """Which shots are entered with something other than a cut (the render project's shot state; none when nothing was chosen yet)."""
    try:
        from . import library, make
        rd = make.render_dir(d)
        if not os.path.isdir(rd):
            return {}
        return {sid: v.get("transition", "cut") for sid, v in (library.shot_state(rd) or {}).items() if isinstance(v, dict)}
    except Exception:
        return {}


def _needed(c: dict) -> float:
    words = sum(len(str(x.get("line", "")).split()) for x in c.get("dialogue") or [])
    return words / WORDS_PER_SECOND + DIALOGUE_PAD if words else 0.0


def report(d: str) -> dict:
    _film(d)
    cons = _contracts(d)
    if not cons:
        raise SystemExit("There are no shots yet. Break the story down first.")
    trans = _transitions(d)
    durs = [float((c.get("generation") or {}).get("duration") or 3.0) for c in cons]
    film_asl = statistics.mean(durs)
    findings: list[dict] = []

    def add(level: str, shot: str | None, scene: int | None, what: str, why: str, tip: str):
        findings.append({"level": level, "shot": shot, "scene": scene, "what": what, "why": why, "tip": tip})
    scenes: dict[int, list[tuple[dict, float]]] = {}
    for c, dur in zip(cons, durs):
        scenes.setdefault(int(c["scene"]), []).append((c, dur))
    for n, rows in scenes.items():
        for c, dur in rows:
            need = _needed(c)
            fr = (c.get("camera") or {}).get("framing") or ""
            action = ACTION_WORDS.search(" ".join(str(c.get(k) or "") for k in ("action", "title", "story_purpose")))
            if need and dur < need * 0.9:
                add("fix", c["id"], n, f"{c['id']} lasts {dur:.1f} s but its dialogue needs about {need:.1f} s.", "People speak at about 2.5 words a second, with a breath either side; a shorter shot means the voice is cut off or hurried.",
                    f"Lengthen the shot to {need:.1f} s, or cut the line.")
            elif dur < MIN_SHOT and fr != "insert" and not action:
                add("look", c["id"], n, f"{c['id']} is only {dur:.1f} s long.", "A shot under about a second and a quarter is hard to read unless it is a deliberate flash.", "Lengthen it, or join it to the shot before.")
            elif dur > LONG_SHOT and not action and not c.get("dialogue"):
                add("look", c["id"], n, f"{c['id']} holds for {dur:.1f} s with no dialogue.", "Long silent holds work when something changes in them; otherwise they sag.", "Shorten it, or give it a camera move or a change of action.")
            if len(c.get("dialogue") or []) and dur > MONOLOGUE and len({x.get("speaker") for x in c["dialogue"]}) == 1 and need > MONOLOGUE * 0.8:
                add("note", c["id"], n, f"{c['id']} is a long speech ({dur:.0f} s) in one shot.", "A single static shot for a long speech loses attention; a cutaway to the listener refreshes it.", "Add a reaction shot or an insert in the middle.")
        sizes = [((c.get("camera") or {}).get("framing") or "") for c, _ in rows]
        run = 1
        for i in range(1, len(rows)):
            run = run + 1 if sizes[i] and sizes[i] == sizes[i - 1] else 1
            if run == RUN_SAME:
                add("look", rows[i][0]["id"], n, f"{RUN_SAME} {sizes[i] or 'same-size'} shots in a row in scene {n}.", "The same shot size repeated makes the scene feel flat; changing size is how a cut says something.", "Change one to a wider or closer size.")
        lens = [dur for _, dur in rows]
        for i in range(len(lens) - RUN_SAME + 1):
            w = lens[i:i + RUN_SAME]
            if len(rows) > RUN_SAME and max(w) - min(w) <= 0.1 * statistics.mean(w):
                add("note", rows[i][0]["id"], n, f"Shots {rows[i][0]['id']} to {rows[i + RUN_SAME - 1][0]['id']} are all about {statistics.mean(w):.1f} s.", "Shots of identical length feel mechanical; rhythm comes from varying how long the eye stays.", "Make one shorter or longer.")
                break
        if len(rows) >= 3 and sizes[0] and sizes[0].lower() not in SIZES_WIDE:
            add("note", rows[0][0]["id"], n, f"Scene {n} does not open on a wide shot.", "A wide first shot tells the audience where they are before the cuts get closer.", "Make the first shot wide or establishing, or add one.")
        speakers = {x.get("speaker") for c, _ in rows for x in c.get("dialogue") or []}
        talking = [s for s in sizes if s]
        if len(speakers) >= 2 and sum(1 for c, _ in rows if c.get("dialogue")) >= 4 and not any(s.lower() in SIZES_CLOSE for s in talking):
            add("note", None, n, f"Scene {n} has a long exchange and no close-ups or over-the-shoulder shots.", "Conversation is carried by faces; staying wide keeps the audience at a distance.", "Cut in to close-ups for the key lines.")
    # the rhythm of each scene against the film
    out_scenes = []
    for n, rows in scenes.items():
        ds = [dur for _, dur in rows]
        asl = statistics.mean(ds)
        out_scenes.append({"number": n, "shots": len(rows), "seconds": round(sum(ds), 1), "asl": round(asl, 1), "shortest": round(min(ds), 1), "longest": round(max(ds), 1), "bars": [{"id": c["id"], "seconds": round(dur, 1)} for c, dur in rows]})
        if len(scenes) >= 3 and len(rows) >= 3 and (asl < film_asl * FAST or asl > film_asl * SLOW):
            fast = asl < film_asl
            add("note", rows[0][0]["id"], n, f"Scene {n} is {'faster' if fast else 'slower'} than the rest of the film (average shot {asl:.1f} s, against {film_asl:.1f} s).",
                "A change of pace should be a choice: a faster scene builds tension, a slower one lets a moment breathe.", "Keep it if it is on purpose; otherwise even it out.")
    cuts = [c["id"] for c in cons[1:]]
    nonc = [sid for sid in cuts if trans.get(sid, "cut") not in ("cut", "")]
    if cuts and len(nonc) / len(cuts) > TRANSITION_SHARE:
        add("look", None, None, f"{len(nonc)} of {len(cuts)} cuts use a transition effect.", "Most cuts in a film are plain cuts: an effect on every join stops meaning anything and slows the pace.", "Keep effects for changes of time or place.")
    rank = {"fix": 0, "look": 1, "note": 2}
    findings.sort(key=lambda f: (rank[f["level"]], f["scene"] or 0, f["shot"] or ""))
    return {"film": {"shots": len(cons), "seconds": round(sum(durs), 1), "asl": round(film_asl, 1), "shortest": round(min(durs), 1), "longest": round(max(durs), 1)},
            "scenes": sorted(out_scenes, key=lambda s: s["number"]), "findings": findings,
            "counts": {k: sum(1 for f in findings if f["level"] == k) for k in ("fix", "look", "note")},
            "note": "Advice only: the report reads the shots as they are and changes nothing. Cutting is a choice; keep what is on purpose."}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="pacing")
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
