"""Places that nobody described.

An image model is told only "Lincoln Middle School, Playground, Day" if that is all the film says about a place. It then invents the fence, the trees, the tables and the building from scratch, and
invents them differently in every shot: that is where a messy, inconsistent, smeared background comes from. A place with a short description, its layout and a picture gives the model something to
keep to.

  status   the places that shots happen in, and which of them have no description, no layout and no picture. Free and read-only.
  draft    for those places only, a first description taken from the story's own words (the action lines of the scenes that happen there). Free; it never overwrites a description that exists;
           the person reads and changes it in Cast & World (the writing helper there can improve it, price first).

  python -m filmcrafter_engine.placecare <status|draft> <film_dir>
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

from . import safeio

MAX_DRAFT = 480


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


def _film(d: str) -> None:
    m = safeio.read_json(os.path.join(d, "film.json"), None)
    if not isinstance(m, dict) or "story" not in m:
        raise SystemExit("That isn't a FilmCrafter film.")


def _undescribed(e: dict) -> bool:
    spatial = e.get("spatial") or {}
    return not (e.get("description") or "").strip() and not any(str(v).strip() for v in spatial.values()) and not e.get("media")


def status(d: str) -> dict:
    """{"places": [{"id", "name", "scenes", "has_description", "has_layout", "has_picture"}], "missing": [ids]}: only places that some scene happens in."""
    from . import bible as B
    _film(d)
    b = B.load(d)
    out = []
    for e in b["environments"]:
        if not e.get("scenes"):
            continue
        spatial = e.get("spatial") or {}
        out.append({"id": e["id"], "name": e["name"], "scenes": e["scenes"], "has_description": bool((e.get("description") or "").strip()),
                    "has_layout": any(str(v).strip() for v in spatial.values()), "has_picture": bool(e.get("media")), "missing": _undescribed(e)})
    return {"places": out, "missing": [p["id"] for p in out if p["missing"]]}


def _story_scenes(d: str) -> list[dict]:
    from . import shots as S
    from . import story
    m = S._film(d)
    ver = m["story"].get("locked") or m["story"]["current"]
    rec = S._read(story._vpath(d, int(ver)))
    if not rec or rec.get("kind") != "screenplay":
        return []
    return S.scene_blocks(rec["text"])


def _words(scene: dict) -> str:
    """The scene's action lines, without who speaks or what is said: what the place looks like and what happens in it."""
    lines = []
    for b in scene["blocks"]:
        if b["type"] == "action":
            lines += b["lines"]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def draft(d: str) -> dict:
    """Fill in a first description for each undescribed place, from the story. Never replaces anything that is there."""
    from . import bible as B
    _film(d)
    st = status(d)
    todo = set(st["missing"])
    if not todo:
        return {**st, "filled": [], "note": "Every place already has a description, a layout or a picture."}
    by_no = {sc["number"]: sc for sc in _story_scenes(d)}
    filled = []
    for e in B.load(d)["environments"]:
        if e["id"] not in todo or not _undescribed(e):
            continue
        text = " ".join(w for w in (_words(by_no[n]) for n in e.get("scenes", []) if n in by_no) if w)
        if not text:
            continue
        cut = text[:MAX_DRAFT]
        stop = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
        cut = cut[:stop + 1] if stop >= 120 else cut.rsplit(" ", 1)[0] if len(text) > MAX_DRAFT else cut
        B.upsert(d, "environment", {"id": e["id"], "description": f"From the story: {cut}"})
        filled.append({"id": e["id"], "name": e["name"], "description": f"From the story: {cut}"})
    return {**status(d), "filled": filled, "note": "These are the story's own words about each place: read them, then add what the story does not say (the fence, the buildings, where things are)."}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="placecare")
    ap.add_argument("action", choices=["status", "draft"])
    ap.add_argument("film")
    a = ap.parse_args(argv)
    try:
        d = os.path.abspath(a.film)
        emit(event="result", data=status(d) if a.action == "status" else draft(d))
        return 0
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=__import__("filmcrafter_engine.errtext", fromlist=["plain"]).plain(e))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
