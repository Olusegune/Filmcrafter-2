"""Write the look library into the guide, from the data (analysis/filmcrafter_engine/styles.json), so the guide can never disagree with the app.

  python scripts/make_look_docs.py        rewrites the 'The look library' section of docs/GETTING_STARTED.md

A test (src/__tests__/help.test.tsx) fails if the guide is missing any look; run this after adding one.
"""
from __future__ import annotations

import json
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
GUIDE = os.path.join(ROOT, "docs", "GETTING_STARTED.md")
STYLES = os.path.join(ROOT, "analysis", "filmcrafter_engine", "styles.json")
HEAD = "## The look library"
FAMILIES = [("photoreal", "Photorealistic"), ("3d", "3D animation"), ("2d", "2D animation"), ("hybrid", "Hybrid 2D/3D"), ("craft", "Hands-on crafts"), ("art", "Art movements & experimental"), ("genre", "Genre feels (layered on a look)")]


def section() -> str:
    styles = json.load(open(STYLES, encoding="utf-8"))["styles"]
    out = [HEAD, "",
           "Every look the app offers, by kind of film. Pick the kind, then the look, in **Cast & World > Rules & style > Visual style**; the genre feels are added on top of any look. "
           "The same looks are in the Studio's **Looks** button (left rail). This list is written from the app's own data.", ""]
    for fam, title in FAMILIES:
        items = [s for s in styles if s.get("family") == fam]
        if not items:
            continue
        out += [f"### {title}", "", "| Look | What it is |", "|---|---|"]
        out += [f"| **{s['name']}** | {s['description'].strip()} |" for s in items]
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main() -> None:
    g = open(GUIDE, encoding="utf-8").read()
    new = section()
    if HEAD in g:
        a = g.index(HEAD)
        rest = g[a + len(HEAD):]
        nxt = rest.find("\n## ")
        g = g[:a] + new + (rest[nxt:] if nxt >= 0 else "")
        g = g.replace(new + "\n## ", new + "\n## ", 1)
    else:
        marker = "## Keyboard shortcuts"
        a = g.index(marker)
        g = g[:a] + new + "\n" + g[a:]
    open(GUIDE, "w", encoding="utf-8", newline="\n").write(g)
    print(f"wrote {sum(1 for s in json.load(open(STYLES, encoding='utf-8'))['styles'] if s.get('family') not in ('auto',))} looks into the guide")


if __name__ == "__main__":
    main()
