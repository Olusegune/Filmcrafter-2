"""Layer styles and lyric layers.

A **template** is a few layers kept together (a title, a subtitle, an icon, lower-third text...) with their looks, places and timing *relative to each other*, so a whole title sequence
can be put down at any moment of any project in one go. The words stay editable afterwards. Pictures are not kept (they belong to one project). Templates live in `~/.filmcrafter/layer_templates.json`.

A **style** is how a layer looks and moves (colours, gradient, outline, shadow, size, scale, rotation, opacity, font, fade, movement, keyframes), saved under
a name for the whole computer (`~/.filmcrafter/layer_styles.json`), so a title style made in one project can be applied in the next.

**Lyric layers** make one text layer for every lyric line in the song map, timed to the line, all in one group: kinetic lyrics. Making them again replaces the
group; removing it takes them all away. They are ordinary layers afterwards (edit, restyle, reorder, delete any of them).

  python -m filmcrafter_engine.layerkit <styles|save|apply|delete_style|lyrics|lyrics_remove|templates|template_save|template_apply|template_delete> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid

from . import overlays as O

STYLES_PATH = os.path.join(os.path.expanduser("~"), ".filmcrafter", "layer_styles.json")
TEMPLATES_PATH = os.path.join(os.path.expanduser("~"), ".filmcrafter", "layer_templates.json")
MAX_TEMPLATES, MAX_TEMPLATE_LAYERS = 50, 60
MAX_STYLES = 100
GROUP = "lyrics:kinetic"
# what a style keeps; the first block means the same on any kind of layer, the second only on the same kind (a text size is not a picture width)
LOOK = ("color", "color2", "gradient", "angle", "stroke", "stroke_w", "shadow", "scale", "rotation", "opacity", "fade", "anim", "font", "keys", "glow", "glow_color", "blur")
SAME_KIND = ("size", "width", "height", "radius", "filled", "shape", "icon")
MOVES = ("fade", "rise", "drop", "slide_left", "slide_right", "zoom_in", "zoom_out", "pushin", "wipe", "typewriter", "bounce", "pop", "pulse", "accent")
Y = {"top": 0.14, "middle": 0.5, "bottom": 0.86}


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    for i in range(40):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == 39:
                raise
            time.sleep(0.05)


def _styles() -> list[dict]:
    got = _read(STYLES_PATH, {}).get("styles")
    return [s for s in (got if isinstance(got, list) else []) if isinstance(s, dict) and s.get("name")]


def list_styles() -> dict:
    return {"styles": [{"name": s["name"], "kind": s.get("kind", "text"), "saved": s.get("saved", 0), "has_keys": bool(s.get("look", {}).get("keys"))} for s in _styles()]}


def _name(raw) -> str:
    n = " ".join(str(raw or "").split())[:60]
    if not n:
        raise SystemExit("Give the style a name.")
    return n


def save_style(d: str, layer_id: str, name) -> dict:
    """Keep how this layer looks and moves under a name (the same name replaces the old style)."""
    n = _name(name)
    layer = next((o for o in O.load(d) if o.get("id") == layer_id), None)
    if not layer:
        raise SystemExit("That overlay isn't in the project.")
    look = {k: layer[k] for k in LOOK + SAME_KIND if layer.get(k) is not None}
    style = {"name": n, "kind": layer.get("kind", "text"), "look": look, "saved": int(time.time())}
    styles = [s for s in _styles() if s["name"].lower() != n.lower()]
    if len(styles) >= MAX_STYLES:
        raise SystemExit(f"You can keep {MAX_STYLES} styles at most. Delete one first.")
    styles.append(style)
    styles.sort(key=lambda s: s["name"].lower())
    _write(STYLES_PATH, {"schema": 1, "styles": styles})
    return list_styles()


def delete_style(name) -> dict:
    n = _name(name).lower()
    _write(STYLES_PATH, {"schema": 1, "styles": [s for s in _styles() if s["name"].lower() != n]})
    return list_styles()


def _look_for(style: dict, kind: str) -> dict:
    keep = LOOK + (SAME_KIND if style.get("kind") == kind else ())
    return {k: v for k, v in (style.get("look") or {}).items() if k in keep}


def apply_style(d: str, name, ids: list) -> dict:
    """Give these layers the saved style. Sizes carry over only between layers of the same kind; a font that is not available in this project is left out."""
    n = _name(name).lower()
    style = next((s for s in _styles() if s["name"].lower() == n), None)
    if not style:
        raise SystemExit("That style isn't saved.")
    if not isinstance(ids, list) or not ids:
        raise SystemExit("Choose a layer to style.")
    items = O.load(d)
    skipped_font = False
    for oid in ids:
        i = next((k for k, o in enumerate(items) if o.get("id") == oid), None)
        if i is None:
            raise SystemExit("That overlay isn't in the project.")
        patch = _look_for(style, items[i].get("kind", "text"))
        if patch.get("font"):
            try:
                from . import fonts
                fonts.check(d, patch["font"])
            except SystemExit:
                patch.pop("font")
                skipped_font = True
        items[i] = {**O._clean(d, patch, items[i]), "id": oid}
    O._save(d, items)
    return {"layers": O.resolve(d), "font_missing": skipped_font}


# ---------------------------------------------------------------- templates

def _templates() -> list[dict]:
    got = _read(TEMPLATES_PATH, {}).get("templates")
    return [t for t in (got if isinstance(got, list) else []) if isinstance(t, dict) and t.get("name") and isinstance(t.get("layers"), list)]


def list_templates() -> dict:
    return {"templates": [{"name": t["name"], "layers": len(t["layers"]), "seconds": t.get("seconds", 0), "saved": t.get("saved", 0)} for t in _templates()]}


def template_save(d: str, ids: list, name) -> dict:
    """Keep these layers together under a name: what they say, how they look and move, where they sit, and when, relative to the first of them."""
    n = _name(name)
    if not isinstance(ids, list) or not ids:
        raise SystemExit("Pick the layers to keep.")
    if len(ids) > MAX_TEMPLATE_LAYERS:
        raise SystemExit(f"A template can hold {MAX_TEMPLATE_LAYERS} layers at most.")
    by_id = {o["id"]: o for o in O.resolve(d)}
    picked = []
    for oid in ids:
        o = by_id.get(oid)
        if not o:
            raise SystemExit("That overlay isn't in the project.")
        if o.get("kind") in ("image", "svg") or o.get("cover"):
            raise SystemExit("A picture belongs to one project, so it cannot go in a template. Leave it out.")
        if not o.get("placed"):
            raise SystemExit("Every layer in a template needs a start and an end time.")
        picked.append(o)
    t0 = min(float(o["start"]) for o in picked)
    layers = []
    for o in picked:
        look = {k: o[k] for k in LOOK + SAME_KIND + ("kind", "text", "name", "x", "y", "width") if o.get(k) is not None}
        layers.append({"look": look, "offset": round(float(o["start"]) - t0, 3), "length": round(float(o["end"]) - float(o["start"]), 3)})
    seconds = round(max(l["offset"] + l["length"] for l in layers), 3)
    templates = [t for t in _templates() if t["name"].lower() != n.lower()]
    if len(templates) >= MAX_TEMPLATES:
        raise SystemExit(f"You can keep {MAX_TEMPLATES} templates at most. Delete one first.")
    templates.append({"name": n, "layers": layers, "seconds": seconds, "saved": int(time.time())})
    templates.sort(key=lambda t: t["name"].lower())
    _write(TEMPLATES_PATH, {"schema": 1, "templates": templates})
    return list_templates()


def template_delete(name) -> dict:
    n = _name(name).lower()
    _write(TEMPLATES_PATH, {"schema": 1, "templates": [t for t in _templates() if t["name"].lower() != n]})
    return list_templates()


def template_apply(d: str, name, at) -> dict:
    """Put the template's layers down starting at `at` seconds. They are ordinary layers, in a group of their own, so one use can be removed again."""
    n = _name(name).lower()
    tpl = next((t for t in _templates() if t["name"].lower() == n), None)
    if not tpl:
        raise SystemExit("That template isn't saved.")
    return put_template(d, tpl, at)


def put_template(d: str, tpl: dict, at) -> dict:
    """The layers of a template (yours, or a built-in one with its words filled in) put down from `at` seconds, as ordinary layers in a group of their own."""
    try:
        start = max(0.0, float(at))
    except (TypeError, ValueError):
        raise SystemExit("Choose the moment to put the template at.")
    items = O.load(d)
    if len(items) + len(tpl["layers"]) > O.MAX_OVERLAYS:
        raise SystemExit(f"That would pass {O.MAX_OVERLAYS} layers. Remove some layers first.")
    group = "tpl:" + re.sub(r"[^a-z0-9]+", "", tpl["name"].lower())[:16] + ":" + uuid.uuid4().hex[:4]
    made = []
    for l in tpl["layers"]:
        look = {k: v for k, v in (l.get("look") or {}).items() if k in LOOK + SAME_KIND + ("kind", "text", "name", "x", "y", "width")}
        if look.get("font"):
            try:
                from . import fonts
                fonts.check(d, look["font"])
            except SystemExit:
                look.pop("font")                                       # a font this project does not have: the default stands in
        o = O._clean(d, {**look, "start": round(start + float(l["offset"]), 3), "end": round(start + float(l["offset"]) + float(l["length"]), 3), "group": group})
        o["id"] = "ov_" + uuid.uuid4().hex[:8]
        made.append(o)
    O._save(d, items + made)
    return {"made": len(made), "group": group, "layers": O.resolve(d), "seconds": tpl.get("seconds", 0)}


def template_remove_group(d: str, group) -> dict:
    g = str(group or "")
    if not g.startswith("tpl:"):
        raise SystemExit("That is not a template group.")
    items = O.load(d)
    keep = [o for o in items if o.get("group") != g]
    O._save(d, keep)
    return {"removed": len(items) - len(keep), "layers": O.resolve(d)}


# ---------------------------------------------------------------- lyric layers

def _lines(d: str) -> list[dict]:
    sm = _read(os.path.join(d, "songmap.json"), {}) or {}
    out = []
    for ln in sm.get("lyrics") or []:
        text = " ".join(str(ln.get("text") or "").split())
        if text and ln.get("start") is not None:
            start = float(ln["start"])
            out.append({"text": text, "start": start, "end": float(ln.get("end") if ln.get("end") is not None else start + 2.0)})
    return sorted(out, key=lambda x: x["start"])


def lyrics_layers(d: str, spec: dict) -> dict:
    """One text layer per lyric line, timed to the line. `style` (a saved name) or `from_layer` (a layer id) sets how they look; otherwise movement, position, size and colour."""
    lines = _lines(d)
    if not lines:
        raise SystemExit("This song has no timed lyric lines yet. Listen to the song with its lyrics first.")
    items = [o for o in O.load(d) if o.get("group") != GROUP]
    if len(items) + len(lines) > O.MAX_OVERLAYS:
        raise SystemExit(f"That would be {len(lines)} layers and the project would pass {O.MAX_OVERLAYS}. Remove some layers first.")
    look: dict = {}
    if spec.get("from_layer"):
        src = next((o for o in O.load(d) if o.get("id") == spec["from_layer"]), None)
        if not src:
            raise SystemExit("That overlay isn't in the project.")
        look = {k: src[k] for k in LOOK + ("size",) if src.get(k) is not None and k != "keys"}
    elif spec.get("style"):
        style = next((s for s in _styles() if s["name"].lower() == _name(spec["style"]).lower()), None)
        if not style:
            raise SystemExit("That style isn't saved.")
        look = {k: v for k, v in _look_for({**style, "kind": "text"}, "text").items() if k != "keys"}
    else:
        move = spec.get("anim", "typewriter")
        if move not in MOVES:
            raise SystemExit("Choose one of the movements in the list.")
        look = {"anim": move, "color": spec.get("color") or "#ffffff", "size": spec.get("size", 0.07), "shadow": True}
    pos = spec.get("position", "bottom")
    if pos not in Y:
        raise SystemExit("Choose top, middle or bottom.")
    lead, hold = 0.05, 0.25
    made = []
    for i, ln in enumerate(lines):
        start = max(0.0, ln["start"] - lead)
        end = ln["end"] + hold
        if i + 1 < len(lines):
            nxt = max(0.0, lines[i + 1]["start"] - lead)       # one line at a time: this one goes before the next arrives
            end = min(end, nxt)
            end = max(end, min(start + 0.6, nxt))              # long enough to read, unless the next line comes sooner
        else:
            end = max(end, start + 0.6)
        end = max(end, start + 0.2)
        text = ln["text"].upper() if spec.get("upper") else ln["text"]
        o = O._clean(d, {**look, "kind": "text", "text": text, "start": round(start, 3), "end": round(end, 3), "x": 0.5, "y": Y[pos], "group": GROUP})
        o["id"] = "ov_" + uuid.uuid4().hex[:8]
        made.append(o)
    O._save(d, items + made)
    from . import captions
    on = bool(captions.load(d).get("enabled"))
    return {"made": len(made), "layers": O.resolve(d), "captions_on": on}


def lyrics_remove(d: str) -> dict:
    items = O.load(d)
    keep = [o for o in items if o.get("group") != GROUP]
    O._save(d, keep)
    return {"removed": len(items) - len(keep), "layers": O.resolve(d)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-layerkit")
    ap.add_argument("action", choices=["styles", "save", "apply", "delete_style", "lyrics", "lyrics_remove", "templates", "template_save", "template_apply", "template_delete", "template_remove", "builtin_list", "builtin_preview", "builtin_apply"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "styles":
            res = list_styles()
        elif a.action == "save":
            res = save_style(a.project, str(x.get("id") or ""), x.get("name"))
        elif a.action == "apply":
            res = apply_style(a.project, x.get("name"), x.get("ids"))
        elif a.action == "delete_style":
            res = delete_style(x.get("name"))
        elif a.action == "templates":
            res = list_templates()
        elif a.action == "template_save":
            res = template_save(a.project, x.get("ids"), x.get("name"))
        elif a.action == "template_apply":
            res = template_apply(a.project, x.get("name"), x.get("at"))
        elif a.action == "template_delete":
            res = template_delete(x.get("name"))
        elif a.action == "template_remove":
            res = template_remove_group(a.project, x.get("group"))
        elif a.action == "builtin_list":
            from . import motion_templates
            res = motion_templates.list_builtin()
        elif a.action == "builtin_preview":
            from . import motion_templates
            res = motion_templates.preview(a.project, str(x.get("id", "")), x.get("texts"))
        elif a.action == "builtin_apply":
            from . import motion_templates
            res = motion_templates.apply_builtin(a.project, str(x.get("id", "")), x.get("at"), x.get("texts"))
        elif a.action == "lyrics":
            res = lyrics_layers(a.project, x)
        else:
            res = lyrics_remove(a.project)
        emit(event="result", data=res)
        return 0
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
