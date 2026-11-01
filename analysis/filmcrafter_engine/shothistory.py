"""Undo for the changes you make to a shot (approve a take, choose a keyframe, set an end frame, change the motion, lock).

Each tracked change writes down, in `undo.json` in the project, exactly which small settings it changed and what they were before and after. Undo puts the old values back; redo puts the new
ones back. Nothing here deletes a picture, a video or a take: those stay in the project, and a change only moves a pointer to them. Pointers are all that is saved, so the journal is small.

  tracked(label, ids)   decorator for an engine function whose first argument is the project folder; `ids(d, *args, **kw)` says which shots it touches
  entries(d)            what can be undone / redone, newest first
  undo(d) / redo(d)     step back / forward one change

`undo.json` may come from a project someone else sent you, so nothing in it is trusted: every address and value is checked before it is applied (see _valid).

  python -m filmcrafter_engine.shothistory <list|undo|redo> <project>
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import re
import sys
import time
import uuid

FILE = "undo.json"
MAX_ENTRIES = 100
MAX_VALUE_BYTES = 50_000
# file -> (how many keys deep a setting sits, what it holds): shots.json[shot] and compose.json[shot] hold settings; keyframes.json[plan][shot] and endframes.json[plan][shot] hold a
# picture in the project; continuity.json["shots"][shot] holds the shot's continuity settings
SHAPES = {"shots.json": (1, "dict"), "compose.json": (1, "dict"), "keyframes.json": (2, "ref"), "endframes.json": (2, "ref"), "continuity.json": (2, "dict")}
KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.\-]{0,99}")
_depth = 0                      # a tracked change that calls another tracked change is one change, not two


def _read(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path: str, data) -> None:
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


# ---------------------------------------------------------------- looking at the settings

def capture(d: str, shot_ids: list[str]) -> dict:
    """{(file, *keys): value} for every setting of these shots that exists right now."""
    out: dict = {}
    for fn, (depth, _kind) in SHAPES.items():
        data = _read(os.path.join(d, fn), {})
        if not isinstance(data, dict):
            continue
        if depth == 1:
            for sid in shot_ids:
                if sid in data:
                    out[(fn, sid)] = data[sid]
        else:
            for plan, per in data.items():
                if isinstance(per, dict) and (fn != "continuity.json" or plan == "shots"):
                    for sid in shot_ids:
                        if sid in per:
                            out[(fn, plan, sid)] = per[sid]
    return out


def _diff(before: dict, after: dict) -> list[dict]:
    changes = []
    for addr in sorted(set(before) | set(after), key=str):
        b, a = before.get(addr, _MISSING), after.get(addr, _MISSING)
        if b != a:
            changes.append({"f": addr[0], "k": list(addr[1:]), **({"b": b} if b is not _MISSING else {}), **({"a": a} if a is not _MISSING else {})})
    return changes


class _Missing:
    def __repr__(self):
        return "<missing>"


_MISSING = _Missing()


# ---------------------------------------------------------------- the journal

def _journal(d: str) -> dict:
    j = _read(os.path.join(d, FILE), {})
    if not isinstance(j, dict):
        j = {}
    return {"undo": [e for e in j.get("undo", []) if isinstance(e, dict)][-MAX_ENTRIES:], "redo": [e for e in j.get("redo", []) if isinstance(e, dict)][-MAX_ENTRIES:]}


def _label(label: str, shot_ids: list[str]) -> str:
    return f"{label} · {shot_ids[0]}" if len(shot_ids) == 1 else f"{label} · {len(shot_ids)} shots" if shot_ids else label


def tracked(label: str, ids):
    """Record the change a function makes. Nothing is recorded when it raises or changes nothing."""
    def wrap(fn):
        @functools.wraps(fn)
        def inner(d, *args, **kw):
            global _depth
            if _depth or not isinstance(d, str):
                return fn(d, *args, **kw)
            try:
                shot_ids = [s for s in ids(d, *args, **kw) if isinstance(s, str)]
            except Exception:
                shot_ids = []
            before = capture(d, shot_ids)
            _depth += 1
            try:
                res = fn(d, *args, **kw)
            finally:
                _depth -= 1
            try:
                changes = _diff(before, capture(d, shot_ids))
                if changes:
                    j = _journal(d)
                    j["undo"].append({"id": uuid.uuid4().hex[:10], "at": int(time.time()), "label": _label(label, shot_ids), "changes": changes})
                    j["redo"] = []                      # a new change ends the redo trail
                    _write(os.path.join(d, FILE), {"undo": j["undo"][-MAX_ENTRIES:], "redo": []})
            except OSError:
                pass                                    # the change is made; failing to note it must never fail it
            return res
        return inner
    return wrap


def entries(d: str) -> dict:
    j = _journal(d)
    view = lambda es: [{"id": str(e.get("id", "")), "at": e.get("at"), "label": str(e.get("label", "Change"))[:120]} for e in reversed(es[-20:])]
    return {"undo": view(j["undo"]), "redo": view(j["redo"]), "undo_count": len(j["undo"]), "redo_count": len(j["redo"])}


# ---------------------------------------------------------------- applying one

def _valid(change) -> bool:
    """A change is only applied if it names one of our settings files, plain keys at the right depth, and a value of the right kind and size."""
    if not isinstance(change, dict) or change.get("f") not in SHAPES:
        return False
    k = change.get("k")
    depth, kind = SHAPES[change["f"]]
    if not isinstance(k, list) or len(k) != depth or not all(isinstance(x, str) and KEY.fullmatch(x) for x in k):
        return False
    if change["f"] == "continuity.json" and k[0] != "shots":
        return False
    for side in ("b", "a"):
        if side not in change:
            continue
        v = change[side]
        if kind == "ref":
            if v != "" and not (isinstance(v, str) and v.startswith("project:") and ".." not in v and ":" not in v[8:] and not v[8:].startswith(("/", "\\")) and len(v) < 400):
                return False
        elif not isinstance(v, dict) or len(json.dumps(v)) > MAX_VALUE_BYTES:
            return False
    return True


def _set(data: dict, keys: list[str], present: bool, value) -> None:
    node = data
    for key in keys[:-1]:
        if present:
            node = node.setdefault(key, {})
            if not isinstance(node, dict):
                raise SystemExit("A settings file is damaged, so that change can't be undone.")
        else:
            node = node.get(key)
            if not isinstance(node, dict):
                return
    if present:
        node[keys[-1]] = value
    else:
        node.pop(keys[-1], None)


def _apply(d: str, changes: list[dict], side: str) -> None:
    if not all(_valid(c) for c in changes):
        raise SystemExit("This project's change history is damaged, so that change can't be undone.")
    files: dict[str, dict] = {}
    for c in changes:
        files.setdefault(c["f"], _read(os.path.join(d, c["f"]), {}) or {})
        if not isinstance(files[c["f"]], dict):
            raise SystemExit("A settings file is damaged, so that change can't be undone.")
    for c in changes:
        _set(files[c["f"]], c["k"], side in c, c.get(side))
    for fn, data in files.items():
        _write(os.path.join(d, fn), data)


def _step(d: str, src: str, dst: str, side: str, nothing: str) -> dict:
    j = _journal(d)
    if not j[src]:
        raise SystemExit(nothing)
    e = j[src][-1]
    _apply(d, e.get("changes") or [], side)
    j[src].pop()
    j[dst].append(e)
    _write(os.path.join(d, FILE), {"undo": j["undo"][-MAX_ENTRIES:], "redo": j["redo"][-MAX_ENTRIES:]})
    return {"label": str(e.get("label", "Change"))[:120], **entries(d)}


def undo(d: str) -> dict:
    """Put the settings of the latest change back as they were."""
    return _step(d, "undo", "redo", "b", "There is nothing to undo.")


def redo(d: str) -> dict:
    """Make the change that was just undone again."""
    return _step(d, "redo", "undo", "a", "There is nothing to redo.")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-shothistory")
    ap.add_argument("action", choices=["list", "undo", "redo"])
    ap.add_argument("project")
    a = ap.parse_args(argv)
    try:
        res = entries(a.project) if a.action == "list" else undo(a.project) if a.action == "undo" else redo(a.project)
        print(json.dumps({"event": "result", "data": res}), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except Exception as e:
        print(json.dumps({"event": "error", "message": __import__("filmcrafter_engine.errtext", fromlist=["plain"]).plain(e)}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
