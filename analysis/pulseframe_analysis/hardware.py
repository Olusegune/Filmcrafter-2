"""What this computer can run: graphics card and its memory, system memory, free disk. Used to say which local models will be quick, slow or too big.

  python -m pulseframe_analysis.hardware     prints the report as JSON

Nothing is installed or changed; it only reads (nvidia-smi when there is one, the operating system otherwise).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

_NOWIN = 0x08000000 if sys.platform == "win32" else 0
OVERHEAD = 1.25          # a model needs its file size plus working memory (context, activations)


def parse_nvidia_smi(text: str) -> list[dict]:
    """`nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader,nounits` → [{name, vram_gb, used_gb}]."""
    out = []
    for line in (text or "").strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            total = float(parts[1]) / 1024
            used = float(parts[2]) / 1024 if len(parts) > 2 else 0.0
        except ValueError:
            continue
        out.append({"name": parts[0], "vram_gb": round(total, 1), "used_gb": round(used, 1), "vendor": "nvidia"})
    return out


def _run(cmd: list[str], timeout: float = 6) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=_NOWIN)
        return p.stdout if p.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _ram_gb() -> float | None:
    try:
        if sys.platform == "win32":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                            ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("ae", ctypes.c_ulonglong)]
            m = MS()
            m.l = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.total / 1e9, 1)
        if sys.platform == "darwin":
            return round(int(_run(["sysctl", "-n", "hw.memsize"]).strip()) / 1e9, 1)
        with open("/proc/meminfo", encoding="utf-8") as f:
            return round(int(f.readline().split()[1]) * 1024 / 1e9, 1)
    except (OSError, ValueError, IndexError, AttributeError):
        return None


def _gpus() -> list[dict]:
    g = parse_nvidia_smi(_run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"]))
    if g:
        return g
    if sys.platform == "darwin":
        chip = _run(["sysctl", "-n", "machdep.cpu.brand_string"]).strip()
        if chip.startswith("Apple"):
            return [{"name": chip, "vram_gb": None, "used_gb": 0, "vendor": "apple"}]   # unified memory: shares the RAM
    if sys.platform == "win32":
        names = [n.strip() for n in _run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name"]).splitlines() if n.strip()]
        return [{"name": n, "vram_gb": None, "used_gb": 0, "vendor": "amd" if "radeon" in n.lower() else "intel" if "intel" in n.lower() else "other"} for n in names]
    return []


def report(path: str | None = None) -> dict:
    gpus = _gpus()
    ram = _ram_gb()
    try:
        free = round(shutil.disk_usage(path or os.path.expanduser("~")).free / 1e9, 1)
    except OSError:
        free = None
    best = max((g for g in gpus if g.get("vram_gb")), key=lambda g: g["vram_gb"], default=None)
    apple = next((g for g in gpus if g["vendor"] == "apple"), None)
    if best:
        budget, kind = best["vram_gb"], "gpu"
    elif apple and ram:
        budget, kind = round(ram * 0.65, 1), "unified"
    else:
        budget, kind = round((ram or 8) * 0.4, 1), "cpu"
    return {"gpus": gpus, "gpu": (best or (gpus[0] if gpus else None)), "ram_gb": ram, "disk_free_gb": free, "model_gb": budget, "kind": kind,
            "summary": summary(gpus, ram, budget, kind)}


def summary(gpus: list[dict], ram: float | None, budget: float, kind: str) -> str:
    ram_s = f"{ram:g} GB memory" if ram else "unknown memory"
    if kind == "gpu":
        g = max((x for x in gpus if x.get("vram_gb")), key=lambda x: x["vram_gb"])
        return f"{g['name']} with {g['vram_gb']:g} GB of video memory, {ram_s}"
    if kind == "unified":
        return f"{gpus[0]['name']}, {ram_s} shared with the graphics"
    if gpus:
        return f"{gpus[0]['name']} (its memory couldn't be read), {ram_s}: models will run on the processor, slowly"
    return f"No dedicated graphics card found, {ram_s}: models will run on the processor, slowly"


def fit(size_gb: float, hw: dict) -> str:
    """How a model of this file size will run here: great (fits in fast memory), slow (spills to the processor), too_big, or unknown."""
    if not size_gb:
        return "unknown"
    need = size_gb * OVERHEAD
    ram = hw.get("ram_gb") or 0
    budget = hw.get("model_gb") or 0
    if hw.get("kind") in ("gpu", "unified"):
        if need <= budget:
            return "great"
        return "slow" if need <= budget + ram * 0.5 else "too_big"
    return "slow" if need <= ram * 0.6 else "too_big"


FIT_WORDS = {"great": "Runs fast on your computer", "slow": "Will run, but slowly (part of it spills to the processor)",
             "too_big": "Too big for this computer", "unknown": ""}


if __name__ == "__main__":
    print(json.dumps(report()))
