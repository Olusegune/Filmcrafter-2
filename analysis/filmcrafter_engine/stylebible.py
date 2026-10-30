"""Art direction: a look for one scene or one shot.

A film has one look. This lets one scene (a memory) or one shot (a dream) be played in another, without touching the rest. Everything is kept in `project.json` under `look`:

    look.scenes  {"6": "live-action"}     a scene's own look; the film's look everywhere else
    look.shots   {"S06-02": "claymation"} one shot's own look; beats its scene's look

Order of precedence, strongest first (what a later prompt line may not override):
    1. the shot's own look
    2. the scene's own look
    3. the film's look
A look id that is not in the library is ignored (`render.own_look_id`), and a project without these keys behaves exactly as before.

Nothing here renders anything or changes a picture that was approved. It only changes what the NEXT picture or take is made from; a new take still shows its price first. Each queued job
records the look it was made in (`job["look"]`), which is how the app notices that a shot's take was made in another look than the one it has now.

  python -m filmcrafter_engine.stylebible <read|set_scene|set_shot> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import safeio

PRECEDENCE = ["The shot's own look", "The scene's own look", "The film's look"]
MAX_SCENE = 9999


def _project_path(d: str) -> str:
    return os.path.join(d, "project.json")


def _look_of(project: dict) -> dict:
    look = project.get("look")
    if isinstance(look, dict):
        return look
    return {"style": "auto", **({"notes": look} if isinstance(look, str) and look else {})}      # an early project kept its look as free text


def _choosable(style: str | None) -> str | None:
    """The look id when it can be a scene's or a shot's own look (None clears it). A genre feel is only ever layered on a look, never a look of its own."""
    from . import render
    if style is None or style == "":
        return None
    lib = render.styles()
    if not isinstance(style, str) or style not in lib or lib[style].get("family") == "genre":
        raise SystemExit("That look is not in the library.")
    return style


def _scenes(d: str) -> list[dict]:
    """[{scene, heading}] from the shot plan (directed, else production); [] when there is none yet."""
    for name in ("directed.json", "production.json"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            try:
                plan = safeio.read_json(p, {})
            except SystemExit:
                return []
            return [{"scene": s.get("number"), "heading": s.get("heading")} for s in (plan.get("scenes") or []) if isinstance(s, dict)]
    return []


def read(d: str) -> dict:
    """{style{id,name,prompt}, styles[], scenes[{scene, heading, style}], shots{}, precedence[]}. Free; changes nothing."""
    from . import render
    project = safeio.read_json(_project_path(d), {})
    look = _look_of(project)
    cur = render.resolve_look(project)
    lib = render.styles()
    own_scenes = look.get("scenes") if isinstance(look.get("scenes"), dict) else {}
    own_shots = look.get("shots") if isinstance(look.get("shots"), dict) else {}
    return {"style": {"id": cur["id"], "name": lib.get(cur["id"], {}).get("name", cur["id"]), "prompt": cur["prompt"]},
            "styles": [{"id": s["id"], "name": s.get("name", s["id"]), "group": s.get("group", ""), "description": s.get("description", "")}
                       for s in lib.values() if s.get("family") != "genre"],
            "scenes": [{**s, "style": render.own_look_id({"scenes": own_scenes}, scene=s["scene"])} for s in _scenes(d)],
            "shots": {k: v for k, v in own_shots.items() if isinstance(v, str) and render.own_look_id({"shots": own_shots}, shot=k)},
            "precedence": PRECEDENCE}


def _set(d: str, table: str, key: str, style: str | None, clear_if_film: bool) -> dict:
    if not os.path.isfile(_project_path(d)):
        raise SystemExit("This folder is not a project.")          # never make a project file out of nothing
    def change(project):
        if not isinstance(project, dict):
            raise SystemExit("This project file is not readable.")
        look = _look_of(project)
        mine = dict(look.get(table) or {}) if isinstance(look.get(table), dict) else {}
        if style and not (clear_if_film and style == look.get("style")):
            mine[key] = style
        else:
            mine.pop(key, None)
        if mine:
            look[table] = mine
        else:
            look.pop(table, None)
        project["look"] = look
        return project
    safeio.update_json(_project_path(d), change, {})
    return read(d)


def set_scene(d: str, scene: int, style: str | None) -> dict:
    """Play one scene in another look (None goes back to the film's look). Choosing the film's own look just clears it."""
    if isinstance(scene, bool) or not isinstance(scene, int) or not 0 <= scene <= MAX_SCENE:
        raise SystemExit("That scene number is not valid.")
    return _set(d, "scenes", str(scene), _choosable(style), clear_if_film=True)


def set_shot(d: str, shot: str, style: str | None) -> dict:
    """Play one shot in another look than its scene's and the film's (None goes back). The id goes through the same plain-id check as every shot id from outside."""
    from .safe import check_id
    sid = check_id(shot if isinstance(shot, str) else "")           # a number or a list from the app is refused, not turned into text
    return _set(d, "shots", sid, _choosable(style), clear_if_film=False)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-stylebible")
    ap.add_argument("action", choices=["read", "set_scene", "set_shot"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    try:
        x = json.loads(a.data)
        if not isinstance(x, dict):
            raise SystemExit("Bad request.")
        res = {"read": lambda: read(a.project), "set_scene": lambda: set_scene(a.project, x.get("scene"), x.get("style")),
               "set_shot": lambda: set_shot(a.project, x.get("shot"), x.get("style"))}[a.action]()
        print(json.dumps({"event": "result", "data": res}, ensure_ascii=False), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
    except Exception as e:                       # noqa: BLE001
        print(json.dumps({"event": "error", "message": f"{type(e).__name__}: {e}"}), flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
