"""Before FilmCrafter itself is updated: keep what an update could ever put at risk. Free, local, and it only ever ADDS copies.

  for each film the person has opened lately   a snapshot of the film's own records (script versions, Bible, cast, voices, notes, the audio plan: filmbackup.make), labelled with the version
                                               about to be installed; skipped when nothing changed since the last snapshot
  the app's own settings                       copied into  ~/.filmcrafter/before-update-<version>/   (the recent-films list and the writing-AI choice; never a key: keys live in the
                                               Windows Credential Manager and are not copied anywhere)

Films themselves live in Documents\\FilmCrafter, outside the program folder, so installing a new version does not touch them; the snapshot is for the unlikely case that a new version (or a
failed install) misbehaves. A snapshot of one film failing does not stop the others, and nothing is deleted or overwritten.

  python -m filmcrafter_engine.preupdate snapshot --data '{"version": "0.25.0", "films": ["C:/.../My Film"], "settings": ["C:/.../recent.json"]}'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time

from . import safeio

HOME = os.path.join(os.path.expanduser("~"), ".filmcrafter")
ENV = "FILMCRAFTER_HOME"


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


def _home() -> str:
    return os.environ.get(ENV) or HOME


def snapshot(version: str, films: list, settings: list | None = None) -> dict:
    """Snapshot each film's records and copy the app's settings files. Returns what was done, film by film, in plain words."""
    from . import filmbackup
    ver = re.sub(r"\.{2,}", "_", re.sub(r"[^0-9A-Za-z._-]+", "_", str(version or "unknown"))).lstrip("._")[:40] or "unknown"
    rows = []
    for f in list(films or [])[:50]:
        p = os.path.abspath(str(f))
        if not os.path.isfile(os.path.join(p, "film.json")):
            rows.append({"film": os.path.basename(p), "ok": False, "why": "Not a FilmCrafter film (or not there), so it was left alone."})
            continue
        if safeio.inspect_json(os.path.join(p, "film.json")) != "ok":
            rows.append({"film": os.path.basename(p), "ok": False, "why": "Its film.json is damaged, so no snapshot was made (the damaged file was left exactly as it is)."})
            continue
        try:
            r = filmbackup.make(p, f"before update {ver}")
            rows.append({"film": os.path.basename(p), "ok": True, "made": r["made"], "why": "A snapshot of its records was made." if r["made"] else "Nothing had changed since its last snapshot."})
        except SystemExit as e:                                      # a damaged record in one film must not stop the others
            rows.append({"film": os.path.basename(p), "ok": False, "why": str(e)})
        except OSError as e:
            rows.append({"film": os.path.basename(p), "ok": False, "why": f"{type(e).__name__}: {e}"})
    kept = []
    dest = os.path.join(_home(), f"before-update-{ver}")
    for s in (list(settings or []) + [os.path.join(_home(), "llm.json")])[:20]:             # the writing-AI choice (never a key) goes along with whatever the app names
        src = os.path.abspath(str(s))
        if not os.path.isfile(src) or os.path.getsize(src) > 5 * 1024 * 1024 or not src.lower().endswith(".json"):
            continue
        os.makedirs(dest, exist_ok=True)
        target = os.path.join(dest, os.path.basename(src))
        if os.path.exists(target):
            target = os.path.join(dest, f"{int(time.time())}-{os.path.basename(src)}")                 # never over an earlier copy
        shutil.copyfile(src, target)
        kept.append(os.path.basename(target))
    ok = sum(1 for r in rows if r["ok"])
    return {"version": ver, "films": rows, "settings": kept, "settings_folder": dest if kept else None,
            "summary": f"{ok} of {len(rows)} film{'s' if len(rows) != 1 else ''} have a snapshot of their records" + (f"; {len(kept)} settings file{'s' if len(kept) != 1 else ''} copied" if kept else "") + ". Your films themselves are not touched by an update."}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="preupdate")
    ap.add_argument("action", choices=["snapshot"])
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    try:
        x = json.loads(a.data or "{}")
        x = x if isinstance(x, dict) else {}
        emit(event="result", data=snapshot(x.get("version", ""), x.get("films") or [], x.get("settings") or []))
        return 0
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
