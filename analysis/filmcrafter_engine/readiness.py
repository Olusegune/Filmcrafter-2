"""Is this film ready? One list, and the one next step.

FilmCrafter already checks many things in many places: the cast, the shots, voices, pacing, the keyframes, the takes. This reads them all once and says, in the order a film is made, what is
still open and what to do next, so nobody has to know which sheet to open. It is the golden path in one place:

  story -> shots -> cast pictures -> fixes (a shot too short for its line) -> voices -> keyframes -> video -> approve -> export

  fix    the film will go wrong without it (no shots, a shot too short for what is said)
  look   worth doing before spending money (a person with no picture, lines with no voice, no keyframes)
  note   for information (a take not approved yet, the film is ready)

Free, local and read-only: nothing here makes or buys anything, and a step that costs money says so and sends you to the place where the price is shown first. A part that cannot be read is
left out of the list and named under "unread", never guessed.

  python -m filmcrafter_engine.readiness report <film_dir>
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

from . import safeio

ORDER = ["story", "cast", "fix", "voices", "keyframes", "video", "approve", "export"]
SECONDS_STEP = 0.5


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


def _film(d: str) -> None:
    m = safeio.read_json(os.path.join(d, "film.json"), None)
    if not isinstance(m, dict) or "story" not in m:
        raise SystemExit("That isn't a FilmCrafter film.")


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _round_up(seconds: float) -> float:
    return math.ceil(seconds / SECONDS_STEP - 1e-9) * SECONDS_STEP


def report(d: str) -> dict:
    from . import audioplan, make, pacing
    _film(d)
    items: list[dict] = []
    unread: list[str] = []

    def add(step: str, level: str, what: str, why: str, go: str, shot: str | None = None, fix: dict | None = None) -> None:
        items.append({"step": step, "level": level, "what": what, "why": why, "go": go, "shot": shot, "fix": fix})

    prog = make.progress(d)
    n_shots = prog["shots"]["count"]
    if not n_shots:
        add("story", "fix", "The story has not been broken into shots yet.", "Shots are what every picture, voice and video is made from.", "shots")
    chars = prog["cast"]["characters"]
    pictured = prog["cast"]["pictures"]
    if chars and pictured < chars:
        add("cast", "look", f"{_plural(chars - pictured, 'person has', 'people have')} no picture yet.", "Without a picture the model invents a face for each shot, and it changes from shot to shot.", "cast")

    plan = None
    if n_shots:
        try:
            plan = audioplan.report(d)
        except SystemExit:
            unread.append("sound plan")
        try:
            pace = pacing.report(d)
        except SystemExit:
            pace = None
            unread.append("pacing")
        need = {s["shot"]: s for s in (plan or {"shots": []})["shots"]}
        for f in (pace or {"findings": []})["findings"]:
            if f["level"] != "fix":
                continue
            fix = None
            row = need.get(f["shot"] or "")
            if row and row["lines"]:
                words = sum(len(str(x["line"]).split()) for x in row["lines"])
                want = _round_up(words / 2.5 + 0.8)
                if want > row["seconds"]:
                    fix = {"kind": "shot_seconds", "shot": row["shot"], "seconds": want, "was": row["seconds"], "label": f"Lengthen {row['shot']} to {want:g} s"}
            add("fix", "fix", f["what"], f["why"], "shots", f["shot"], fix)
        if plan:
            missing = [s for s in plan["shots"] if s["route"] == "needs_voice"]
            if missing:
                lines = sum(1 for s in missing for x in s["lines"] if not x["has_voice"] and not x["voice_over"])
                add("voices", "look", f"{_plural(lines, 'line still needs', 'lines still need')} a voice, in {_plural(len(missing), 'shot', 'shots')}.",
                    "Record each line, or speak it with the person's voice; the price is shown before anything is spent.", "voice", missing[0]["shot"])
            differ = [s for s in plan["shots"] if s["differs"]]
            if differ:
                add("voices", "note", f"{_plural(len(differ), 'voice-over shot is', 'voice-over shots are')} not set to silent on screen.",
                    "Nobody on screen speaks a voice-over, so the picture can be made without lip-sync. The Sound plan sets it in one click.", "soundplan", differ[0]["shot"])
        st = make.status(d) if os.path.isfile(os.path.join(make.render_dir(d), "production.json")) else None
        if st is None:
            add("keyframes", "note", "The film has not been prepared for making yet.", "Open Make to prepare it. This costs nothing.", "make")
        else:
            no_kf = [s for s in st["shots"] if not s["keyframe"]["chosen"]]
            no_vid = [s for s in st["shots"] if not any(t["ok"] for t in s["video"]["takes"])]
            unapproved = [s for s in st["shots"] if any(t["ok"] for t in s["video"]["takes"]) and not s["video"]["approved"]]
            if no_kf:
                add("keyframes", "look", f"{_plural(len(no_kf), 'shot has', 'shots have')} no keyframe.", "A keyframe fixes the look of a shot before the video is made, so a poor one is cheap to replace.", "make", no_kf[0]["id"])
            if no_vid:
                add("video", "look", f"{_plural(len(no_vid), 'shot has', 'shots have')} no video yet.", "Making video is paid. Open Make: the price of the batch is shown first, and nothing is made until you confirm.", "make", no_vid[0]["id"])
            if unapproved:
                add("approve", "note", f"{_plural(len(unapproved), 'shot has a take', 'shots have takes')} that you have not approved.", "The newest good take is used until you approve one.", "make", unapproved[0]["id"])
            if not no_vid and not any(i["level"] == "fix" for i in items):
                add("export", "note", "Every shot has a video. The film is ready to export.", "Export puts the picture, the voices and the planned sound together.", "export")
    rank = {s: i for i, s in enumerate(ORDER)}
    items.sort(key=lambda i: (0 if i["level"] == "fix" else 1, rank.get(i["step"], 99)))
    nxt = next((i for i in items if i["level"] != "note"), items[0] if items else None)
    counts = {k: sum(1 for i in items if i["level"] == k) for k in ("fix", "look", "note")}
    return {"items": items, "next": nxt, "counts": counts, "ready": not counts["fix"] and not counts["look"] and bool(n_shots), "shots": n_shots, "unread": unread,
            "note": "This only reads the film. Anything that costs money shows its price first, in the place where it is made."}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="readiness")
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
        emit(event="error", message=__import__("filmcrafter_engine.errtext", fromlist=["plain"]).plain(e))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
