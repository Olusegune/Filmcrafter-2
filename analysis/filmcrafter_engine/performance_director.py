"""The Performance Director: one door to the free, local parts of directing a performance.

  characters_get | character_set | character_clear          what a person wants, fears and hides            (character_performance.py)
  breakdown_get | breakdown_set | breakdown_reset | breakdown_accept   the scene-by-scene Performance Breakdown   (performance_analysis.py)
  beats_suggest                                             a free starting point for a shot's beats        (performance_analysis.py)
  nudges_get | nudge_set                                    More restrained, Hold the reaction longer...    (acting.py)

Everything here is free, runs on this computer and sends nothing anywhere. Timed beats, arcs and gestures stay in acting.py; the acting profile stays in performance.py; the screenplay, the
shots and the Bible are only ever read.

  python -m filmcrafter_engine.performance_director <action> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import sys

ACTIONS = ("characters_get", "character_set", "character_clear", "breakdown_get", "breakdown_set", "breakdown_reset", "breakdown_accept", "beats_suggest", "nudges_get", "nudge_set")


def run(d: str, action: str, x: dict) -> dict:
    from . import acting, character_performance as CP, performance_analysis as PA
    if action == "characters_get":
        return CP.get(d)
    if action == "character_set":
        return CP.set_fields(d, str(x.get("person", "")), x.get("fields") if isinstance(x.get("fields"), dict) else {})
    if action == "character_clear":
        return CP.clear(d, str(x.get("person", "")))
    if action == "breakdown_get":
        return PA.get(d)
    if action in ("breakdown_set", "breakdown_reset", "breakdown_accept"):
        scene, path = x.get("scene"), str(x.get("path", ""))
        if isinstance(scene, bool) or not isinstance(scene, (int, str)) or not str(scene).strip():
            raise SystemExit("That scene is not valid.")
        return {"breakdown_set": lambda: PA.set_field(d, scene, path, x.get("value")), "breakdown_reset": lambda: PA.reset_field(d, scene, path),
                "breakdown_accept": lambda: PA.accept_field(d, scene, path)}[action]()
    shot = str(x.get("shot", ""))
    if action == "beats_suggest":
        return PA.suggest_beats(d, shot)
    if action == "nudges_get":
        return acting.nudges_get(d, shot)
    if action == "nudge_set":
        return acting.nudge_set(d, shot, str(x.get("nudge", "")), x.get("level", 1))
    raise SystemExit("Unknown action.")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-performance-director")
    ap.add_argument("action", choices=["characters_get", "character_set", "character_clear", "breakdown_get", "breakdown_set", "breakdown_reset", "breakdown_accept", "beats_suggest", "nudges_get", "nudge_set"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    try:
        x = json.loads(a.data)
        print(json.dumps({"event": "result", "data": run(a.project, a.action, x if isinstance(x, dict) else {})}, ensure_ascii=False), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
    except Exception as e:                       # noqa: BLE001
        print(json.dumps({"event": "error", "message": f"{type(e).__name__}: {e}"}), flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
