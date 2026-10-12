"""Audit of a film folder: does the right thing reach every shot?  (Free: nothing is sent anywhere; your film is not changed, only its derived render folder is refreshed, as the app does.)

    python scripts/audit_film.py "<film folder>" [--provider kie] [--kind image|video] [--model <id>]

For every shot it builds the prompt the app would send and checks, among other things, that:
  - every person the shot names is in the prompt, and has a reference picture (that exists, and is a picture)
  - the setting is in the prompt; the look is; the shape of the frame is asked for
  - no quoted speech (models draw it as subtitles), no title-page text, no leftover template words
  - the shot is in the right scene, its people are in the cast, and no shot is empty
It prints one line per problem and a summary; exit code 1 when any shot has a problem.
"""
import argparse
import contextlib
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "analysis"))
from filmcrafter_engine import make, render, shots  # noqa: E402


def quiet(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


def audit(film: str, provider: str = "kie", kind: str = "image", model: str | None = None) -> tuple[list[str], dict]:
    problems: list[str] = []
    quiet(make.sync, film)                                                   # the render project is derived from the film; refresh it
    rd = os.path.join(film, "render")
    pj = json.load(open(os.path.join(rd, "project.json"), encoding="utf-8"))
    order = shots._index(film)["order"]
    title = (json.load(open(os.path.join(film, "film.json"), encoding="utf-8")).get("title") or "").lower()
    stats = {"shots": len(order), "with_people": 0, "people_refs_ok": 0, "prompts": 0}
    cast = {x["name"].lower() for x in pj.get("library", {}).get("items", []) if x["kind"] == "character"}
    for sid in order:
        c = shots._contract(film, sid)
        names = [x["name"] for x in c["characters"]]
        where = c["environment"].get("name") or ""
        try:
            r = quiet(render.preview, rd, sid, provider, model, {}, kind)
        except SystemExit as e:
            problems.append(f"{sid}: cannot build the prompt ({e})")
            continue
        prompt = str(r["payload"].get(r["manifest"]["roles"].get("prompt", "prompt")) or "")
        stats["prompts"] += 1
        low = prompt.lower()
        refs = r.get("references") or []
        labels = " ".join(x["label"] for x in refs).lower()
        if not prompt.strip():
            problems.append(f"{sid}: the prompt is empty")
            continue
        if names:
            stats["with_people"] += 1
        for n in names:
            pretty = n.title() if n.isupper() else n
            if pretty.lower() not in low:
                problems.append(f"{sid}: {pretty} is in the shot but not in the prompt")
            if n.lower() not in cast:
                problems.append(f"{sid}: {pretty} is not in the cast")
            elif pretty.lower() not in labels and kind == "image":
                problems.append(f"{sid}: {pretty} has no reference picture in this prompt")
            else:
                stats["people_refs_ok"] += 1
        if kind == "image" and not refs:                                           # a picture with nothing to look at must not go to a model that insists on one
            from filmcrafter_engine import refgen
            use = render.text_only_model(r["manifest"]["model"], False)
            if refgen._needs_input_image(render.manifest(provider, use)):
                problems.append(f"{sid}: no reference picture, and {use} needs one (it would be refused)")
        for x in refs:
            if not x.get("path"):
                continue                                                           # a reference that is only a link (nothing local to check)
            full = x["path"] if os.path.isabs(x["path"]) else os.path.join(rd, x["path"])
            if not os.path.isfile(full) or os.path.splitext(full)[1].lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                problems.append(f"{sid}: reference is not a picture file: {os.path.basename(x['path'])}")
        if where and where.lower() not in low and c["environment"].get("name"):
            problems.append(f"{sid}: the setting '{where}' is not in the prompt")
        if kind == "image" and re.search(r"[\"“”][^\"“”]{12,}[\"“”]", prompt):
            problems.append(f"{sid}: the prompt quotes speech (models draw it as subtitles)")
        if title and len(title) > 8 and title in low.replace("\n", " "):
            problems.append(f"{sid}: the film's title text is in the prompt")
        if re.search(r"\{[a-z_]+\}|None|undefined|\bNaN\b", prompt):
            problems.append(f"{sid}: leftover template text in the prompt")
        if "look:" not in low:
            problems.append(f"{sid}: no Look in the prompt")
        if not c["action"].strip() and not c["dialogue"] and not names:
            problems.append(f"{sid}: the shot has nothing in it (no action, no words, no people)")
        if kind == "video":                                                         # a shot with your own recording must carry it, and say who speaks along to it
            from filmcrafter_engine import voiceover
            mine = voiceover.for_shot(rd, sid)
            roles = r["manifest"].get("roles") or {}
            if mine and "ref_audio" in roles:
                if not r["payload"].get(roles["ref_audio"]):
                    problems.append(f"{sid}: has a recording but the video request does not carry it")
                if "speaks along" not in low:
                    problems.append(f"{sid}: has a recording but the prompt does not say who speaks along to it")
            stats["recordings"] = stats.get("recordings", 0) + len(mine)
        sc = c["scene"]
        if not sid.startswith(f"S{sc:02d}-"):
            problems.append(f"{sid}: its id does not match its scene ({sc})")
    return problems, stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("film")
    ap.add_argument("--provider", default="kie")
    ap.add_argument("--kind", default="image", choices=["image", "video"])
    ap.add_argument("--model", default=None, help="check with this model instead of the automatic one")
    a = ap.parse_args()
    probs, st = audit(a.film, a.provider, a.kind, a.model)
    for p in probs:
        print("  !! " + p)
    print(f"{st['shots']} shots, {st['prompts']} prompts built, {st['with_people']} with people, {len(probs)} problem(s).")
    sys.exit(1 if probs else 0)
