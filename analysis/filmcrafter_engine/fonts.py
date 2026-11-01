"""Fonts for captions and on-screen text: pick one installed on this computer, or add a font file of your own.

A font is named by a short id, never a path:

  ""                 the default (Segoe UI Bold, then Arial Bold, then DejaVu Sans Bold)
  "system:<file>"    a font installed on this computer, by its file name (Arial-Bold.ttf)
  "project:<file>"   a font file you added to this project (copied into <project>/fonts, so the project keeps working if the font is
                     later uninstalled or the project moves to another computer)

An id is only ever looked up in the computer's font folders or the project's own fonts folder, by plain file name, so nothing a user
types can point at another file. Fonts are read by Pillow only (never a command line). An added file must be a .ttf or .otf under 20 MB
that Pillow can open. A font that has gone missing falls back to the default, so an export never fails because of one.

  python -m filmcrafter_engine.fonts <list|add> <project> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys

EXT = (".ttf", ".otf")
MAX_FONT_BYTES = 20_000_000
MAX_INSTALLED = 2000
PROJECT_DIR = "fonts"
INDEX_PATH = os.path.join(os.path.expanduser("~"), ".filmcrafter", "fonts-index.json")
_PLAIN = re.compile(r"[^\\/:*?\"<>|\x00-\x1f]{1,120}")


def font_dirs() -> list[str]:
    if sys.platform == "win32":
        root = os.environ.get("SystemRoot", r"C:\Windows")
        return [os.path.join(root, "Fonts"), os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")]
    if sys.platform == "darwin":
        return ["/System/Library/Fonts", "/Library/Fonts", os.path.expanduser("~/Library/Fonts")]
    return ["/usr/share/fonts", os.path.expanduser("~/.local/share/fonts"), os.path.expanduser("~/.fonts")]


FONT_DIRS: list[str] | None = None          # tests point this at a folder of their own


def _dirs() -> list[str]:
    return FONT_DIRS if FONT_DIRS is not None else font_dirs()


def _files() -> dict[str, str]:
    """Every .ttf/.otf in the computer's font folders (a few levels down): {file name: full path}."""
    out: dict[str, str] = {}
    for base in _dirs():
        if not base or not os.path.isdir(base):
            continue
        root_depth = base.rstrip(os.sep).count(os.sep)
        for cur, sub, names in os.walk(base):
            if cur.rstrip(os.sep).count(os.sep) - root_depth >= 3:
                sub[:] = []
            for n in names:
                if n.lower().endswith(EXT) and n not in out:
                    out[n] = os.path.join(cur, n)
    return out


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _names(path: str) -> tuple[str, str] | None:
    """(family, style) of a font file, or None if Pillow can't open it."""
    from PIL import ImageFont
    try:
        fam, style = ImageFont.truetype(path, 12).getname()
        return str(fam)[:80], str(style or "Regular")[:40]
    except Exception:
        return None


def installed() -> list[dict]:
    """The fonts installed on this computer, by family name: [{id, name, file}]. Remembered between runs (only new or changed files are read)."""
    files = _files()
    idx = _read(INDEX_PATH, {}) or {}
    fresh: dict[str, list] = {}
    for n, p in files.items():
        try:
            stamp = os.path.getmtime(p)
        except OSError:
            continue
        hit = idx.get(p)
        if hit and hit[0] == stamp:
            fresh[p] = hit
            continue
        nm = _names(p)
        fresh[p] = [stamp, nm[0], nm[1]] if nm else [stamp, "", ""]
    if fresh != idx:
        try:
            os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
            tmp = INDEX_PATH + f".{os.getpid()}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(fresh, f)
            os.replace(tmp, INDEX_PATH)
        except OSError:
            pass
    out = []
    for n, p in files.items():
        _, fam, style = fresh.get(p, [0, "", ""])
        if fam:
            out.append({"id": f"system:{n}", "name": fam if style.lower() in ("regular", "normal", "book") else f"{fam} {style}", "file": n})
    out.sort(key=lambda x: x["name"].lower())
    return out[:MAX_INSTALLED]


def project_fonts(d: str) -> list[dict]:
    base = os.path.join(d, PROJECT_DIR)
    out = []
    for n in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        p = os.path.join(base, n)
        if n.lower().endswith(EXT) and os.path.isfile(p):
            nm = _names(p)
            if nm:
                out.append({"id": f"project:{n}", "name": nm[0] if nm[1].lower() in ("regular", "normal", "book") else f"{nm[0]} {nm[1]}", "file": n})
    return out


def listing(d: str) -> dict:
    return {"installed": installed(), "project": project_fonts(d), "default": "Segoe UI Bold"}


def path_for(d: str, spec: str | None) -> str | None:
    """The file a font id names, or None (the default, or a font that is gone)."""
    spec = (spec or "").strip()
    if ":" not in spec:
        return None
    where, name = spec.split(":", 1)
    if not _PLAIN.fullmatch(name) or name in (".", "..") or not name.lower().endswith(EXT):
        return None
    if where == "project":
        p = os.path.join(d, PROJECT_DIR, name)
        return p if os.path.isfile(p) else None
    if where == "system":
        return _files().get(name)
    return None


def check(d: str, spec) -> str:
    """A font id the screen sent, validated: "" (default) or an id that names a font that exists now."""
    spec = str(spec or "").strip()
    if not spec:
        return ""
    if not path_for(d, spec):
        raise SystemExit("That font isn't available on this computer. Choose another, or add the font file.")
    return spec


def signature(d: str, spec: str | None) -> str:
    """What a drawn picture depends on besides the id: the file's size and time, so replacing a font file redraws it."""
    p = path_for(d, spec)
    try:
        return f"{spec}|{os.path.getsize(p)}|{os.path.getmtime(p)}" if p else ""
    except OSError:
        return ""


def load(d: str, spec: str | None, size: int):
    """The font at a size; the default when none is chosen or the chosen one can't be read."""
    from PIL import ImageFont
    p = path_for(d, spec)
    if p:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"):          # no font chosen (or it would not open): a bold system font
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def add_file(d: str, src: str) -> dict:
    """Copy a font file you chose into the project (it must open as a font) and return its id."""
    src = str(src or "")
    name = os.path.basename(src)
    if not name.lower().endswith(EXT) or not os.path.isfile(src):
        raise SystemExit("Choose a font file (.ttf or .otf).")
    if os.path.getsize(src) > MAX_FONT_BYTES:
        raise SystemExit("That font file is too large (20 MB at most).")
    nm = _names(src)
    if not nm:
        raise SystemExit("That file isn't a font FilmCrafter can read.")
    safe = re.sub(r"[^\w.\- ]+", "_", name)[:100]
    if not _PLAIN.fullmatch(safe):
        safe = "font" + os.path.splitext(name)[1].lower()
    os.makedirs(os.path.join(d, PROJECT_DIR), exist_ok=True)
    shutil.copy2(src, os.path.join(d, PROJECT_DIR, safe))
    return {"id": f"project:{safe}", "name": nm[0] if nm[1].lower() in ("regular", "normal", "book") else f"{nm[0]} {nm[1]}", "file": safe}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-fonts")
    ap.add_argument("action", choices=["list", "add"])
    ap.add_argument("project")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        res = add_file(a.project, x.get("file", "")) if a.action == "add" else listing(a.project)
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
