"""Reading the shot plan without loading the rendering engine. The small actions the screens ask for all the time (camera choices, dance and look checks) only need the plan, and the rendering
module takes a quarter of a second to import: this keeps them quick. Same rules as render._load_plan and render._shot, which tests keep in step."""
from __future__ import annotations

import json
import os


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load_plan(d: str) -> tuple[str, dict]:
    for name in ("directed", "production"):
        p = _read(os.path.join(d, f"{name}.json"))
        if p:
            return name, p
    raise SystemExit("This project has no shot plan yet.")


def find_shot(plan: dict, shot_id: str) -> tuple[dict, dict]:
    for sc in plan["scenes"]:
        for sh in sc["shots"]:
            if sh["id"] == shot_id:
                return sh, sc
    raise SystemExit(f"Shot {shot_id} not found.")
