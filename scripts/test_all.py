"""Run every kind of check in one go and print one table: type checks, screen tests, the app shell's tests, the engine's tests by type, and the security scans.

  python scripts/test_all.py                 everything that is installed
  python scripts/test_all.py --quick         skip the slow engine types (integration, e2e)
  PF_PYTHON=path\\to\\python.exe python scripts/test_all.py     the Python that has the engine's requirements (pytest, ffmpeg wrapper, ...)

A step whose tool is not installed is reported as SKIPPED with the reason, never as passed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PY = os.environ.get("PF_PYTHON") or sys.executable
NPX = shutil.which("npx") or shutil.which("npx.cmd")
NPM = shutil.which("npm") or shutil.which("npm.cmd")
CARGO = shutil.which("cargo")
RAFTER = shutil.which("rafter") or shutil.which("rafter.cmd")


def step(name: str, cmd: list[str] | None, cwd: str = ROOT, why_not: str = "") -> tuple[str, str, float, str]:
    if not cmd:
        return name, "SKIPPED", 0.0, why_not
    t = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
        out = (p.stdout + p.stderr).strip().splitlines()
        return name, "PASSED" if p.returncode == 0 else "FAILED", time.time() - t, "\n".join(out[-6:]) if p.returncode else (out[-1] if out else "")
    except Exception as e:                              # a missing program or a timeout is a failure to run, not a pass
        return name, "FAILED", time.time() - t, f"{type(e).__name__}: {e}"


def has_module(name: str) -> bool:
    return subprocess.run([PY, "-c", f"import {name}"], capture_output=True).returncode == 0


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")      # scanner output has symbols the Windows console code page cannot show
    quick = "--quick" in argv
    analysis = os.path.join(ROOT, "analysis")
    pytest_ok = has_module("pytest")
    kinds = ["unit", "regression", "security", "acceptance"] + ([] if quick else ["integration", "e2e"])
    rows = [
        step("Types (tsc)", [NPX, "tsc", "--noEmit"] if NPX else None, why_not="npx not found"),
        step("Screen tests (vitest)", [NPX, "vitest", "run"] if NPX else None, why_not="npx not found"),
        step("App shell tests (cargo test)", [CARGO, "test", "--quiet"] if CARGO else None, os.path.join(ROOT, "src-tauri"), "cargo not found"),
    ]
    for kind in kinds:
        rows.append(step(f"Engine: {kind}", [PY, "-m", "pytest", "-q", "-m", kind, "-p", "no:cacheprovider"] if pytest_ok else None, analysis, f"pytest is not installed for {PY}"))
    rows += [
        step("Scan: secrets (rafter)", [RAFTER, "secrets", "."] if RAFTER else None, why_not="rafter not found"),
        step("Scan: Python code (bandit, medium and up)", [PY, "-m", "bandit", "-q", "-r", "pulseframe_analysis", "-ll"] if has_module("bandit") else None, analysis, "bandit is not installed (pip install bandit)"),
        step("Scan: Python packages (pip-audit)", [PY, "-m", "pip_audit", "-r", "requirements-engine.txt", "--no-deps", "--disable-pip"] if has_module("pip_audit") else None, analysis, "pip-audit is not installed (pip install pip-audit)"),
        step("Scan: npm packages (npm audit)", [NPM, "audit", "--omit=dev"] if NPM else None, why_not="npm not found"),
    ]
    width = max(len(r[0]) for r in rows)
    print()
    for name, status, secs, note in rows:
        print(f"{name:<{width}}  {status:<8} {secs:6.1f}s  {note.splitlines()[-1] if note else ''}")
    failed = [r for r in rows if r[1] == "FAILED"]
    skipped = [r for r in rows if r[1] == "SKIPPED"]
    print(f"\n{len(rows) - len(failed) - len(skipped)} passed, {len(failed)} failed, {len(skipped)} skipped")
    for name, _, _, note in failed:
        print(f"\n--- {name}\n{note}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
