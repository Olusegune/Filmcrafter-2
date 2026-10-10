"""Blocking: a top-down plan of each shot. Where people stand and face, where the camera is and what it looks at, and the line the camera must not cross.

A plan lives in the shot's contract (`plan`) and is drawn as a floor plan in Shots. The room is a box 100 wide and 70 deep (x runs right, y runs down the page, so y = 0 is the far wall).
A facing or aim is a compass angle in degrees: 0 looks right, 90 looks down the page, 180 looks left, 270 looks up the page.

  suggest     a sensible plan from who is in the shot, its framing and the shot before it (free, rule-based)
  describe    the plan in plain words as the camera sees it: who is screen-left, who faces whom, what the camera is over, for the shot's prompts
  crossings   shots where the camera moves to the other side of the line between two people, so they may swap sides on screen (the 180-degree rule)

Nothing here is sent anywhere. A plan is advice for the pictures and the prompts; the person can change every number.
"""
from __future__ import annotations

import math

W, H = 100.0, 70.0
MAX_PEOPLE, MAX_PROPS = 12, 16
DEFAULT_FOV = {"establishing": 80, "wide": 65, "medium": 50, "close-up": 35, "extreme close-up": 22, "over the shoulder": 40, "point of view": 55, "insert": 28}


def _num(v, lo, hi, default):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f or f in (float("inf"), float("-inf")):
        return default
    return max(lo, min(hi, f))


def _name(v, n=60) -> str:
    return str(v if v is not None else "").replace("\x00", "").strip()[:n]


def _deg(v, default=0.0) -> float:
    return round(_num(v, -1e6, 1e6, default) % 360.0, 1)


def clean(plan) -> dict | None:
    """A plan made safe: numbers kept inside the room, angles 0 to 360, names trimmed, lists limited. None for 'no plan'."""
    if plan is None:
        return None
    if not isinstance(plan, dict):
        raise SystemExit("A blocking plan must be an object.")
    people = []
    for p in (plan.get("people") or [])[:MAX_PEOPLE]:
        if isinstance(p, dict) and _name(p.get("name")):
            people.append({"name": _name(p.get("name")), "x": round(_num(p.get("x"), 0, W, W / 2), 1), "y": round(_num(p.get("y"), 0, H, H / 2), 1), "facing": _deg(p.get("facing"), 90)})
    props = []
    for p in (plan.get("props") or [])[:MAX_PROPS]:
        if isinstance(p, dict) and _name(p.get("name")):
            props.append({"name": _name(p.get("name")), "x": round(_num(p.get("x"), 0, W, W / 2), 1), "y": round(_num(p.get("y"), 0, H, H / 2), 1)})
    cam = plan.get("camera")
    camera = None
    if isinstance(cam, dict):
        camera = {"x": round(_num(cam.get("x"), 0, W, W / 2), 1), "y": round(_num(cam.get("y"), 0, H, H - 4), 1), "aim": _deg(cam.get("aim"), 270),
                  "fov": round(_num(cam.get("fov"), 10, 120, 50), 0)}
    return {"people": people, "props": props, "camera": camera}


# ---------------------------------------------------------------- geometry

def _bearing(ax, ay, bx, by) -> float:
    return math.degrees(math.atan2(by - ay, bx - ax)) % 360.0


def _unit(dx, dy):
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > 1e-9 else (0.0, 1.0)


def _side(cam, a, b) -> int:
    """Which side of the line from person a to person b the camera is on: +1, -1, or 0 on the line."""
    v = (b["x"] - a["x"]) * (cam["y"] - a["y"]) - (b["y"] - a["y"]) * (cam["x"] - a["x"])
    return 1 if v > 1e-6 else -1 if v < -1e-6 else 0


def _reflect(p, a, b):
    """The point p mirrored across the line through a and b."""
    ux, uy = _unit(b["x"] - a["x"], b["y"] - a["y"])
    dx, dy = p[0] - a["x"], p[1] - a["y"]
    t = dx * ux + dy * uy
    fx, fy = a["x"] + t * ux, a["y"] + t * uy
    return (2 * fx - p[0], 2 * fy - p[1])


def _clampxy(x, y):
    return (max(2.0, min(W - 2.0, x)), max(2.0, min(H - 2.0, y)))


def _pair(plan):
    ppl = (plan or {}).get("people") or []
    return (ppl[0], ppl[1]) if len(ppl) >= 2 else None


# ---------------------------------------------------------------- suggest

def _layout(names, prev) -> list[dict]:
    """Where each person stands: where they stood in the shot before when they were there, otherwise two facing each other across the room."""
    old = {p["name"]: p for p in ((prev or {}).get("people") or [])}
    n = len(names)
    out = []
    for i, nm in enumerate(names):
        if nm in old:
            out.append(dict(old[nm]))
            continue
        if n == 1:
            x, y, f = W / 2, H * 0.52, 90.0
        elif i == 0:
            x, y, f = W * 0.30, H * 0.52, 0.0
        elif i == 1:
            x, y, f = W * 0.70, H * 0.52, 180.0
        else:
            ang = math.radians(200 + (i - 2) * 50)
            x, y = W / 2 + 22 * math.cos(ang), H * 0.34 + 10 * math.sin(ang)
            f = _bearing(x, y, W / 2, H * 0.52)
        out.append({"name": nm, "x": round(x, 1), "y": round(y, 1), "facing": round(f, 1)})
    return out


def suggest(contract: dict, prev: dict | None = None, ref_side: int | None = None) -> dict:
    """A plan for this shot from its people, its framing and the shot before it. ref_side keeps the camera on the same side of the line as the scene so far."""
    names = [_name(c.get("name")) for c in (contract.get("characters") or []) if _name(c.get("name"))]
    names = [n.title() if n.isupper() else n for n in names]
    framing = (contract.get("camera") or {}).get("framing") or "medium"
    people = _layout(names, prev)
    props = [dict(p) for p in ((prev or {}).get("props") or [])]
    for i, p in enumerate(contract.get("props") or []):
        nm = _name(p.get("name"))
        if nm and not any(q["name"] == nm for q in props) and len(props) < MAX_PROPS:
            props.append({"name": nm, "x": round(W * (0.2 + 0.15 * (i % 5)), 1), "y": round(H * 0.2, 1)})
    fov = DEFAULT_FOV.get(framing, 50)
    speakers = [_name(d.get("speaker")).title() for d in (contract.get("dialogue") or []) if _name(d.get("speaker"))]
    by = {p["name"]: p for p in people}
    first_speaker = next((by[s] for s in speakers if s in by), None)
    cx = sum(p["x"] for p in people) / len(people) if people else W / 2
    cy = sum(p["y"] for p in people) / len(people) if people else H * 0.5
    if framing in ("establishing", "wide") or not people:
        cam = (W / 2, H - 3.0 if framing == "wide" else H - 2.0)
        aim = _bearing(cam[0], cam[1], cx, cy)
    elif framing == "medium":
        cam = (cx, min(H - 2.0, cy + 20.0))
        aim = _bearing(cam[0], cam[1], cx, cy)
    elif framing in ("close-up", "extreme close-up"):
        subj = first_speaker or people[0]
        other = next((p for p in people if p is not subj), None)
        dist = 12.0 if framing == "close-up" else 7.0
        ux, uy = 0.0, 1.0
        if other:
            ox, oy = _unit(subj["x"] - other["x"], subj["y"] - other["y"])
            ux, uy = _unit(ux + 0.5 * ox, uy + 0.5 * oy)
        cam = (subj["x"] + dist * ux, subj["y"] + dist * uy)
        aim = _bearing(cam[0], cam[1], subj["x"], subj["y"])
    elif framing == "over the shoulder" and len(people) >= 2:
        target = first_speaker or people[1]
        near = next((p for p in people if p is not target), people[0])
        ux, uy = _unit(near["x"] - target["x"], near["y"] - target["y"])
        cam = (near["x"] + 13.0 * ux, near["y"] + 13.0 * uy + 4.0)
        aim = _bearing(cam[0], cam[1], target["x"], target["y"])
    elif framing == "point of view" and people:
        eye = people[0]
        cam = (eye["x"], eye["y"])
        aim = eye["facing"]
    elif framing == "insert":
        tx, ty = (props[0]["x"], props[0]["y"]) if props else (cx, cy)
        cam = (tx, min(H - 2.0, ty + 14.0))
        aim = _bearing(cam[0], cam[1], tx, ty)
    else:
        cam = (cx, min(H - 2.0, cy + 18.0))
        aim = _bearing(cam[0], cam[1], cx, cy)
    cam = _clampxy(*cam)
    pair = _pair({"people": people})
    if pair and ref_side and framing != "point of view":
        s = _side({"x": cam[0], "y": cam[1]}, *pair)
        if s and s != ref_side:                                    # keep the camera on the scene's side of the line
            cam = _clampxy(*_reflect(cam, *pair))
            target = people[1] if framing == "over the shoulder" and len(people) > 1 and not first_speaker else None
            aim = _bearing(cam[0], cam[1], *( (target["x"], target["y"]) if target else (cx, cy) ))
            if framing in ("close-up", "extreme close-up"):
                subj = first_speaker or people[0]
                aim = _bearing(cam[0], cam[1], subj["x"], subj["y"])
            if framing == "over the shoulder":
                tg = first_speaker or people[1]
                aim = _bearing(cam[0], cam[1], tg["x"], tg["y"])
    return clean({"people": people, "props": props, "camera": {"x": cam[0], "y": cam[1], "aim": aim, "fov": fov}})


# ---------------------------------------------------------------- in words

def describe(plan: dict | None) -> str:
    """The plan as the camera sees it, for the prompt: '' when there is no plan with a camera."""
    if not plan or not plan.get("camera") or not plan.get("people"):
        return ""
    cam = plan["camera"]
    th = math.radians(cam["aim"])
    fx, fy = math.cos(th), math.sin(th)
    rx, ry = -math.sin(th), math.cos(th)
    half = math.tan(math.radians(max(10.0, cam["fov"]) / 2.0))
    seen = []
    for p in plan["people"]:
        vx, vy = p["x"] - cam["x"], p["y"] - cam["y"]
        fwd, lat = vx * fx + vy * fy, vx * rx + vy * ry
        if fwd <= 1.0 or abs(lat) / (fwd * half) > 1.25:
            continue                                             # behind the camera or outside the frame
        pos = lat / (fwd * half)
        where = "screen-left" if pos < -0.34 else "screen-right" if pos > 0.34 else "centre"
        gx, gy = math.cos(math.radians(p["facing"])), math.sin(math.radians(p["facing"]))
        toward = -(gx * fx + gy * fy)
        across = gx * rx + gy * ry
        face = "facing the camera" if toward > 0.75 else "facing away from the camera" if toward < -0.75 else "facing screen-right" if across > 0 else "facing screen-left"
        seen.append((fwd, p["name"], where, face))
    if not seen:
        return ""
    seen.sort()
    bits = [f"{n} {w}, {f}" for _, n, w, f in seen]
    depth = ""
    if len(seen) >= 2 and seen[-1][0] / max(seen[0][0], 1.0) > 1.6:
        depth = f" ({seen[0][1]} nearest the camera, {seen[-1][1]} furthest)"
    where_cam = ""
    people = {p["name"]: p for p in plan["people"]}
    for p in plan["people"]:
        d = math.hypot(p["x"] - cam["x"], p["y"] - cam["y"])
        if d < 24 and any(q is not p and abs(((_bearing(cam["x"], cam["y"], q["x"], q["y"]) - cam["aim"] + 180) % 360) - 180) < cam["fov"] / 2 for q in plan["people"]):
            where_cam = f" Camera over {p['name']}'s shoulder."
            break
    if not where_cam:
        near = min(plan["people"], key=lambda p: math.hypot(p["x"] - cam["x"], p["y"] - cam["y"]))
        if math.hypot(near["x"] - cam["x"], near["y"] - cam["y"]) < 18 and near["name"] in people:
            where_cam = f" Camera close on {near['name']}."
    return "Blocking as the camera sees it: " + "; ".join(bits) + "." + depth + where_cam


# ---------------------------------------------------------------- the line

def crossings(contracts: list[dict]) -> list[dict]:
    """Shots, in order within each scene, where the camera is on the other side of the line between the first two people than in the shot before: they may swap sides on screen."""
    out = []
    last: dict[int, tuple[int, str]] = {}
    for c in contracts:
        plan = c.get("plan")
        if not plan or not plan.get("camera"):
            continue
        pair = _pair(plan)
        if not pair:
            continue
        side = _side(plan["camera"], *pair)
        if not side:
            continue
        scene = c.get("scene")
        if scene in last and last[scene][0] != side:
            a, b = pair[0]["name"], pair[1]["name"]
            out.append({"shot": c["id"], "previous": last[scene][1], "message": f"The camera is on the other side of the line between {a} and {b} than in {last[scene][1]}, so they may swap sides on screen.",
                        "fix": "Move the camera back to the other side of the dashed line, or cut away to an insert or a wide shot first."})
        last[scene] = (side, c["id"])
    return out


def scene_side(contracts: list[dict], scene: int, before: str | None = None) -> int | None:
    """The side of the line the scene's camera has been on so far (None until a shot with a camera and two people has a plan)."""
    side = None
    for c in contracts:
        if c.get("scene") != scene:
            continue
        if before is not None and c["id"] == before:
            break
        plan = c.get("plan")
        pair = _pair(plan) if plan and plan.get("camera") else None
        if pair:
            side = _side(plan["camera"], *pair) or side
    return side
