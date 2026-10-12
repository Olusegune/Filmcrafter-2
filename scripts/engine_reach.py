"""Which engine modules can the app still reach? Starts from the modules the app shell runs (src-tauri/src/lib.rs: `filmcrafter_engine.<name>`),
follows every import between engine modules (including `from . import a as A`, imports inside functions, and `from .x import y`), and lists what is left.

    python scripts/engine_reach.py            # unreachable modules, with their size and how many tests mention them
    python scripts/engine_reach.py --why X    # who imports module X (so you know what to fix before deleting it)

A module that nothing reaches is a candidate for removal, never an automatic one: run the whole test suite after each removal.
"""
import glob
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ENG = os.path.join(ROOT, "analysis", "filmcrafter_engine")
mods = {os.path.basename(f)[:-3] for f in glob.glob(os.path.join(ENG, "*.py"))} - {"__init__"}
src = {m: open(os.path.join(ENG, m + ".py"), encoding="utf-8").read() for m in mods}


def imports(text: str) -> set[str]:
    found: set[str] = set()
    for m in re.finditer(r"^[ \t]*from \.(\w*) import ([^\n(]+|\([^)]*\))", text, re.M):
        if m.group(1):
            found.add(m.group(1))
        else:
            found |= {x.strip().split(" as ")[0].strip() for x in re.split(r"[,()\n]", m.group(2)) if x.strip()}
    for m in re.finditer(r"^[ \t]*from filmcrafter_engine(?:\.(\w+))? import ([^\n(]+|\([^)]*\))", text, re.M):
        if m.group(1):
            found.add(m.group(1))
        else:
            found |= {x.strip().split(" as ")[0].strip() for x in re.split(r"[,()\n]", m.group(2)) if x.strip()}
    found |= set(re.findall(r"^[ \t]*import filmcrafter_engine\.(\w+)", text, re.M))
    found |= set(re.findall(r"filmcrafter_engine\.(\w+)", text))
    return found & mods


edges = {m: imports(t) - {m} for m, t in src.items()}
rust = open(os.path.join(ROOT, "src-tauri", "src", "lib.rs"), encoding="utf-8").read()
roots = {m for m in re.findall(r"filmcrafter_engine\.(\w+)", rust) if m in mods}
seen: set[str] = set()
stack = list(roots)
while stack:
    m = stack.pop()
    if m not in seen:
        seen.add(m)
        stack += list(edges.get(m, ()))

if len(sys.argv) > 2 and sys.argv[1] == "--why":
    print(f"{sys.argv[2]} is imported by:", sorted(m for m, e in edges.items() if sys.argv[2] in e) or "nothing")
    sys.exit(0)

tests = "\n".join(open(f, encoding="utf-8").read() for f in glob.glob(os.path.join(ROOT, "analysis", "tests", "*.py")))
left = sorted(mods - seen - {"__main__"})
def mentions(m: str) -> int:
    """How many lines in the tests import or name this module."""
    return sum(1 for line in tests.splitlines() if re.search(r"\b" + m + r"\b", line) and ("import" in line or "filmcrafter_engine" in line))


for m in left:
    by = sorted(k for k, e in edges.items() if m in e) or "-"
    print(f"{m:22}{len(src[m].splitlines()):5} lines   in tests: {mentions(m):3}   imported by: {by}")
print(f"\n{len(seen)} reachable, {len(left)} not, of {len(mods)} modules; the shell runs {len(roots)} directly")
