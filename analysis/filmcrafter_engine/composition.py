"""Composition: where things sit in the frame (thirds, headroom, look room, balance), written as direction for the picture model and drawn as a guide for the person.

Image and video models place people near the centre unless they are told otherwise, and a centred, tightly cropped, evenly lit frame is what makes AI films look like AI films. A film-school frame
puts the subject on a third, leaves look room in front of a face, keeps headroom suited to the shot size, puts a horizon on a third and layers a wide shot into foreground, middle and back.
This turns a shot's size, who is in it, where they stand and which way they face (from the blocking plan) into those few plain sentences. It is advice: it reads the shot, writes a line into the
request, and changes nothing in the film. It is left out when the shot has a storyboard panel (the panel is the composition).

  guide     the sentences, the points to draw on a thirds grid, and the reasons, for one shot. Free; deterministic.
  line      the same sentences as one line for a request (what the render engine adds)

Pure text and arithmetic: nothing is sent anywhere.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

PRIORITY = 6
THIRD_A, THIRD_B = 1 / 3, 2 / 3

# "Sarah screen-left, facing screen-right" (blocking.describe) and the Continuity Director's "Sarah screen-left facing right"
_PERSON = re.compile(r"([A-Z][\w'.-]*(?: [A-Z][\w'.-]*)?) (screen-left|screen-right|centre|left|right|center)(?:,| ) ?(facing (?:screen-)?(?:right|left)|facing the camera|facing camera|facing away(?: from the camera)?)")


def size_of(framing: str) -> str:
    """The shot size, from the words of the framing: extreme_wide | wide | full | medium | medium_close | close | extreme_close | insert | ots | pov."""
    f = str(framing or "").lower()
    for key, rx in (("ots", r"over[- ]the[- ]shoulder|\bots\b"), ("pov", r"point[- ]of[- ]view|\bpov\b"), ("insert", r"insert|detail"), ("extreme_close", r"extreme close|\becu\b"),
                    ("medium_close", r"medium close|\bmcu\b"), ("close", r"close"), ("extreme_wide", r"establishing|extreme wide"), ("wide", r"\bwide\b|long shot"), ("full", r"full"), ("medium", r"medium")):
        if re.search(rx, f):
            return key
    return "medium"


def people_from_text(text: str) -> list[dict]:
    """Who stands where and which way they face, from the blocking words: [{name, side: left|right|centre, facing: left|right|camera|away}]."""
    seen, out = set(), []
    for m in _PERSON.finditer(str(text or "")):
        name, side, face = m.group(1), m.group(2), m.group(3)
        if name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "side": "left" if side.endswith("left") else "right" if side.endswith("right") else "centre",
                    "facing": "right" if face.endswith("right") else "left" if face.endswith("left") else "away" if "away" in face else "camera"})
    return out


def guide(framing: str, performers: list[str] | None = None, blocking_text: str = "", angle: str = "") -> dict:
    """{"size", "lines": [{"text", "why"}], "points": [{"name", "x", "y"}], "horizon": y|None, "text": one line for a request}. x and y are fractions of the frame (0 left/top)."""
    size = size_of(framing)
    names = [p for p in (performers or []) if p]
    located = people_from_text(blocking_text)
    byname = {p["name"].lower(): p for p in located}
    people = [byname.get(n.lower(), {"name": n, "side": "centre", "facing": "camera"}) for n in names] or located
    lines: list[dict] = []
    points: list[dict] = []
    horizon = None

    def add(text: str, why: str):
        lines.append({"text": text, "why": why})

    def look_room(p: dict) -> float:
        """The vertical third a person is placed on: opposite to the way they face, so there is room in front of the face."""
        if p["facing"] == "right":
            return THIRD_A
        if p["facing"] == "left":
            return THIRD_B
        return THIRD_A if p["side"] == "left" else THIRD_B if p["side"] == "right" else THIRD_A

    if size in ("wide", "extreme_wide"):
        horizon = THIRD_B if "low" in str(angle).lower() or "from below" in str(angle).lower() else THIRD_A
        add("The horizon sits on a third of the frame, never across the middle.", "A horizon in the middle cuts the picture in two; a third makes either the land or the sky the subject.")
        add("Layered depth: something in the foreground, the people in the middle distance, the place behind them.", "Layers read as depth; a flat wide shot reads as a backdrop.")
        for p in people[:3]:
            points.append({"name": p["name"], "x": round(look_room(p), 3), "y": 0.62})
        if people:
            add("The people are small in the frame and sit on a third, with open space around them.", "A small figure in a large space says where they are.")
    elif size in ("full", "medium", "medium_close"):
        if len(people) == 1:
            p = people[0]
            x = look_room(p)
            points.append({"name": p["name"], "x": round(x, 3), "y": THIRD_A})
            add(f"{p['name']} sits on the {'left' if x < 0.5 else 'right'} third of the frame, with their eyes on the upper third line.", "Eyes on the upper third and the body on a vertical third is the classic balanced portrait.")
            if p["facing"] in ("left", "right"):
                add(f"Leave look room on the {'right' if p['facing'] == 'right' else 'left'}: more space in front of the face than behind the head.", "A face with no room to look into feels trapped.")
        elif len(people) >= 2:
            a, b = people[0], people[1]
            ax, bx = (THIRD_A, THIRD_B) if a["side"] != "right" else (THIRD_B, THIRD_A)
            points += [{"name": a["name"], "x": round(ax, 3), "y": THIRD_A}, {"name": b["name"], "x": round(bx, 3), "y": THIRD_A}]
            add(f"{a['name']} and {b['name']} fill opposite thirds of the frame, facing in towards each other, with a clear gap between them.", "Two people on opposite thirds balance the frame and make their distance the story.")
            add("Both faces are visible and their eyes are on the upper third line.", "Readable faces carry the scene.")
            if len(people) >= 3:
                add("Everyone else is grouped into the gaps in a loose triangle, never in a straight line.", "A triangle gives a group depth and a clear order.")
        else:
            add("The subject sits on a third of the frame, not in the middle.", "Off-centre placement is what makes a frame feel composed.")
        add("Headroom is small: a little space above the head, never cutting off the top of it." if size != "full" else "Headroom is modest and the feet are not cut off.", "Too much space above the head makes a person look small; none at all feels cramped.")
    elif size in ("close", "extreme_close"):
        p = people[0] if people else None
        x = look_room(p) if p else THIRD_A
        points.append({"name": p["name"] if p else "Subject", "x": round(x, 3), "y": THIRD_A})
        add("The eyes sit on the upper third line, with just enough headroom; the frame may crop the top of the head or the chin but never the eyes." if size == "close" else
            "The detail (the eyes, the lips, the hands) sits on one of the thirds' crossing points, filling the frame.", "A close-up is about the eyes; an extreme close-up is about one thing.")
        if p and p["facing"] in ("left", "right"):
            add(f"Leave look room on the {'right' if p['facing'] == 'right' else 'left'}, in front of the face.", "Space in front of a face lets the thought go somewhere.")
    elif size == "ots":
        side = people[0]["side"] if people else "left"
        edge = "left" if side != "right" else "right"
        add(f"The near person's shoulder and the back of their head are in the {edge} foreground, soft and cropped at the frame's edge; the other person's face sits on the opposite third, sharp.", "The foreground shoulder gives depth and says whose view this is.")
        points.append({"name": people[1]["name"] if len(people) > 1 else "Face", "x": THIRD_B if edge == "left" else THIRD_A, "y": THIRD_A})
    elif size == "pov":
        add("What the character is looking at sits on a third, with a little of the surroundings around it; the frame shakes or moves as their head would.", "A point-of-view shot is the person's attention, so the thing they look at is the subject.")
        points.append({"name": "What they see", "x": THIRD_B, "y": THIRD_A})
    else:                                         # insert
        add("The object fills most of the frame and sits on a third, with a soft, simple background.", "An insert is one idea; nothing else competes.")
        points.append({"name": "The detail", "x": THIRD_A, "y": THIRD_B})
    line = ("Composition: " + " ".join(x["text"] for x in lines)) if lines else ""
    return {"size": size, "lines": lines, "points": points, "horizon": horizon, "text": line, "grid": [round(THIRD_A, 3), round(THIRD_B, 3)]}


def enabled(project: dict) -> bool:
    c = (project or {}).get("composition")
    return True if not isinstance(c, dict) else bool(c.get("on", True))


def line_for(shot: dict, project: dict, refs: list[dict] | None = None) -> dict | None:
    """The composition line for a request ({"text", "priority"}), or None: off for the film, nobody in a non-wide shot, or a storyboard panel is the composition."""
    if not enabled(project):
        return None
    if any(str(r.get("label", "")).lower().startswith("storyboard") or "composition reference" in str(r.get("label", "")).lower() for r in (refs or [])):
        return None
    notes = shot.get("continuity_notes")
    text = " ".join([str(shot.get("continuity") or "")] + ([str(x) for x in notes] if isinstance(notes, list) else [str(notes or "")]) + [str(shot.get("blocking") or "")])
    g = guide(shot.get("framing") or "", shot.get("performers") or [], text, shot.get("framing") or "")
    if not g["lines"] or (not shot.get("performers") and g["size"] not in ("wide", "extreme_wide", "insert")):
        return None
    return {"text": g["text"], "priority": PRIORITY}


# ---------------------------------------------------------------- for a film's shot (the screen) and the switch

def for_shot(d: str, shot_id: str) -> dict:
    """The guide for one shot of a film, from its contract and its blocking plan, plus whether the film asks for it in the prompts."""
    from . import blocking, make
    from . import shots as S
    c = S._contract(d, shot_id)
    cam = c.get("camera") or {}
    text = " ".join([str(c.get("blocking") or ""), blocking.describe(c.get("plan")), str(c.get("continuity") or "")])
    g = guide(", ".join(x for x in (str(cam.get("framing") or ""), str(cam.get("angle") or "")) if x), [x["name"] for x in c.get("characters") or []], text, cam.get("angle") or "")
    pj = S._read(os.path.join(make.render_dir(d), "project.json")) or {}
    return {**g, "shot": shot_id, "in_prompt": enabled(pj)}


def set_enabled(d: str, on: bool) -> dict:
    from . import make, safeio
    rd = make.render_dir(d)
    os.makedirs(rd, exist_ok=True)
    path = os.path.join(rd, "project.json")
    pj = safeio.read_json(path, {}) or {}
    pj["composition"] = {"on": bool(on)}
    safeio.write_json(path, pj)
    return {"in_prompt": bool(on)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="composition")
    ap.add_argument("action", choices=["guide", "set"])
    ap.add_argument("film")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    try:
        x = json.loads(a.data or "{}")
        x = x if isinstance(x, dict) else {}
        d = os.path.abspath(a.film)
        from .safe import check_id
        res = for_shot(d, check_id(x.get("shot", ""), "shot")) if a.action == "guide" else set_enabled(d, x.get("on", True) is not False)
        print(json.dumps({"event": "result", "data": res}), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except Exception as e:
        print(json.dumps({"event": "error", "message": f"{type(e).__name__}: {e}"}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
