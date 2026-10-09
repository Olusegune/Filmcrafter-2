"""Local Model Manager: what runs on this computer, and getting the right models.

Ollama: installed models with their size, download (pull) and remove, and which one plans / sees.
LM Studio: loaded models (downloads happen in LM Studio itself). ComfyUI: server, GPU and workflows.
Everything here is local; downloads come from Ollama's own library through the Ollama app.

  python -m pulseframe_analysis.localmodels <action> --data '{...}'   actions: status | pull | delete | use
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

import requests

_NOWIN = 0x08000000 if sys.platform == "win32" else 0
OLLAMA = "http://127.0.0.1:11434"
LMSTUDIO = "http://127.0.0.1:1234/v1"
RECOMMENDED = [   # file sizes are Ollama's, rounded; hardware.fit() says which ones this computer runs well
    {"name": "qwen2.5vl:3b", "role": "both", "size_gb": 3.2, "why": "Smallest model that plans and sees: for computers with little graphics memory."},
    {"name": "qwen2.5vl:7b", "role": "both", "size_gb": 6.0, "why": "Plans and sees: directions, Director, keyframe and continuity checks."},
    {"name": "gemma3:4b", "role": "both", "size_gb": 3.3, "why": "Small and quick; writes well and can see images."},
    {"name": "gemma3:12b", "role": "both", "size_gb": 8.1, "why": "Strong writing, and it can see images."},
    {"name": "llama3.2-vision:11b", "role": "both", "size_gb": 7.8, "why": "Good at describing pictures; plans well too."},
    {"name": "qwen3:8b", "role": "planning", "size_gb": 5.2, "why": "Careful planning and long scripts; can't see images."},
    {"name": "llama3.1:8b", "role": "planning", "size_gb": 4.9, "why": "Fast planning and writing; can't see images."},
    {"name": "qwen3:14b", "role": "planning", "size_gb": 9.3, "why": "Better plans and structure than the 8B; can't see images."},
    {"name": "mistral-small3.1", "role": "both", "size_gb": 15.0, "why": "Plans and sees with a very good eye; needs a big graphics card."},
    {"name": "gemma3:27b", "role": "both", "size_gb": 17.0, "why": "The best local writer here, and it sees images; needs a big graphics card."},
    {"name": "llava:7b", "role": "vision", "size_gb": 4.7, "why": "Small vision model for checks only."},
    {"name": "moondream", "role": "vision", "size_gb": 1.7, "why": "Tiny: only for quick picture checks on weak computers."},
]
ROLE_WORDS = {"both": "plans and sees", "planning": "plans", "vision": "sees"}
VISION_HINT = ("vl", "llava", "vision", "gemma3", "minicpm-v", "moondream", "pixtral")


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):   # the app went away: nobody to tell
        pass


def _ollama() -> dict:
    try:
        r = requests.get(OLLAMA + "/api/tags", timeout=3)
        r.raise_for_status()
        models = [{"name": m["name"], "size_gb": round(m.get("size", 0) / 1e9, 1),
                   "vision": any(h in m["name"].lower() for h in VISION_HINT),
                   "family": (m.get("details") or {}).get("family"), "params": (m.get("details") or {}).get("parameter_size")}
                  for m in r.json().get("models", [])]
        return {"running": True, "models": sorted(models, key=lambda m: m["name"])}
    except (requests.RequestException, ValueError):
        return {"running": False, "models": []}


def _lmstudio() -> dict:
    try:
        r = requests.get(LMSTUDIO + "/models", timeout=3)
        r.raise_for_status()
        return {"running": True, "models": [{"name": m["id"], "vision": any(h in m["id"].lower() for h in VISION_HINT)}
                                            for m in r.json().get("data", [])]}
    except (requests.RequestException, ValueError):
        return {"running": False, "models": []}


def _lms() -> str | None:
    p = os.path.join(os.path.expanduser("~"), ".lmstudio", "bin", "lms.exe" if sys.platform == "win32" else "lms")
    return p if os.path.exists(p) else None


def _installed() -> dict:
    local = os.environ.get("LOCALAPPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Local"))
    pf = os.environ.get("ProgramFiles", "C:\\Program Files")
    ollama = next((p for p in (os.path.join(local, "Programs", "Ollama", "ollama app.exe"), os.path.join(pf, "Ollama", "ollama app.exe"),
                               "/Applications/Ollama.app") if os.path.exists(p)), None)
    lmstudio = next((p for p in (os.path.join(pf, "LM Studio", "LM Studio.exe"), os.path.join(local, "Programs", "LM Studio", "LM Studio.exe"),
                                 os.path.join(local, "Programs", "lm-studio", "LM Studio.exe"), "/Applications/LM Studio.app") if os.path.exists(p)), None)
    return {"ollama": ollama, "lmstudio": lmstudio, "lms": _lms()}


def start(which: str) -> dict:
    """Start Ollama, or LM Studio's local API server (headless, through its own lms tool)."""
    inst = _installed()
    if which == "ollama":
        if not inst["ollama"]:
            raise SystemExit("Ollama isn't installed. It's free from ollama.com.")
        subprocess.Popen([inst["ollama"]] if not inst["ollama"].endswith(".app") else ["open", inst["ollama"]])
    elif which == "lmstudio":
        if inst["lms"]:
            subprocess.run([inst["lms"], "server", "start"], capture_output=True, timeout=60, creationflags=_NOWIN)
        elif inst["lmstudio"]:
            subprocess.Popen([inst["lmstudio"]])
        else:
            raise SystemExit("LM Studio isn't installed. It's free from lmstudio.ai.")
    else:
        raise SystemExit("Start what?")
    return status()


def lms_get(name: str) -> dict:
    """Download a model into LM Studio (its own lms tool; progress is LM Studio's)."""
    if not _lms():
        raise SystemExit("LM Studio's command-line tool (lms) wasn't found. Open LM Studio once, then try again.")
    if not re.match(r"^[\w.\-/@:]+$", name or ""):
        raise SystemExit("Enter a model name, e.g. qwen2.5-vl-7b-instruct.")
    p = subprocess.run([_lms(), "get", name, "--yes"], capture_output=True, text=True, timeout=7200, creationflags=_NOWIN)
    if p.returncode:
        raise SystemExit(f"LM Studio couldn't download {name}: {(p.stderr or p.stdout).strip()[-300:]}")
    return status()


def status() -> dict:
    from . import comfy
    from .llm import config
    try:
        cs = comfy.check()
    except Exception:
        cs = {"connected": False, "workflows": []}
    from . import hardware
    hw = hardware.report()
    o = _ollama()
    for m in o["models"]:
        m["fit"] = hardware.fit(m["size_gb"], hw)
    have = {m["name"] for m in o["models"]} | {m["name"].split(":latest")[0] for m in o["models"]}
    rec = [{**r, "installed": r["name"] in have, "fit": hardware.fit(r["size_gb"], hw), "fit_note": hardware.FIT_WORDS[hardware.fit(r["size_gb"], hw)]} for r in RECOMMENDED]
    rank = {"great": 0, "slow": 1, "unknown": 2, "too_big": 3}
    rec.sort(key=lambda r: (rank[r["fit"]], r["role"] != "both", -r["size_gb"] if r["fit"] == "great" else r["size_gb"]))   # what fits first: models that plan and see, biggest first
    return {"ollama": o, "lmstudio": _lmstudio(), "comfyui": cs, "brain": config(), "installed": _installed(), "hardware": hw,
            "recommended": rec, "ollama_loaded": loaded()}


def pull(name: str) -> dict:
    """Download a model through the Ollama app, reporting progress."""
    if not re.match(r"^[\w.\-/]+(:[\w.\-]+)?$", name or ""):
        raise SystemExit("Enter a model name from the Ollama library, e.g. qwen2.5vl:7b.")
    if not _ollama()["running"]:
        raise SystemExit("Ollama isn't running. Install it from ollama.com and open it, then try again.")
    known = next((r for r in RECOMMENDED if r["name"] == name), None)
    if known:
        from . import hardware
        free = hardware.report().get("disk_free_gb")
        if free is not None and known["size_gb"] + 2 > free:
            raise SystemExit(f"Not enough disk space for {name}: it needs about {known['size_gb']:g} GB and {free:g} GB is free. Remove a model you don't use, or free some space.")
    try:
        with requests.post(OLLAMA + "/api/pull", json={"model": name, "stream": True}, stream=True, timeout=(5, 600)) as r:
            if r.status_code >= 400:
                raise SystemExit(f"Ollama couldn't download {name}: {r.text[:200]}")
            last = -1
            for line in r.iter_lines():
                if not line:
                    continue
                m = json.loads(line)
                if m.get("error"):
                    raise SystemExit(f"Ollama couldn't download {name}: {m['error']}")
                if m.get("total"):
                    pct = int(m.get("completed", 0) * 100 / m["total"])
                    if pct != last:
                        last = pct
                        emit(event="progress", stage=f"downloading {name}", progress=pct / 100)
                elif m.get("status"):
                    emit(event="progress", stage=m["status"])
    except requests.RequestException as e:
        raise SystemExit(f"Lost contact with Ollama while downloading ({type(e).__name__}).")
    return status()


def loaded() -> list[dict]:
    """Ollama models sitting in memory right now (they hold graphics memory until they time out)."""
    try:
        r = requests.get(OLLAMA + "/api/ps", timeout=3)
        r.raise_for_status()
        return [{"name": m.get("name"), "gb": round((m.get("size") or 0) / 1e9, 1), "gpu_gb": round((m.get("size_vram") or 0) / 1e9, 1)} for m in r.json().get("models", [])]
    except (requests.RequestException, ValueError):
        return []


def unload(name: str) -> dict:
    """Free the graphics memory a model is holding (ComfyUI and Ollama share the card): Ollama's keep_alive 0."""
    try:
        requests.post(OLLAMA + "/api/generate", json={"model": name, "keep_alive": 0}, timeout=30)
    except requests.RequestException:
        raise SystemExit("Ollama isn't running.")
    return status()


def _test_png() -> str:
    """A 64x64 picture, left half red and right half blue, made on the spot (some vision models refuse tiny images)."""
    import base64
    import struct
    import zlib
    row = bytes([0]) + bytes([220, 40, 40]) * 32 + bytes([40, 60, 220]) * 32
    raw = row * 64

    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    png = bytes([137]) + b"PNG" + bytes([13, 10, 26, 10]) + chunk(b"IHDR", struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0)) \
        + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    return base64.b64encode(png).decode()


def friendly(msg: str, server: str = "ollama") -> str:
    """Plain words for the errors local servers give."""
    m = (msg or "").lower()
    if "not found" in m and "model" in m:
        return "That model isn't downloaded yet. Download it first, then try again."
    if "out of memory" in m or "cuda" in m and "memory" in m or "requires more system memory" in m:
        return "The computer ran out of memory loading that model. Choose a smaller one (the list marks which fit), or close other programs that use the graphics card."
    if "no models loaded" in m or "model_not_found" in m or "no model" in m:
        return "LM Studio has no model loaded. Load one in LM Studio (or use its Download button here), then try again."
    return (msg or "")[:300]


def test(server: str = "ollama", name: str | None = None, vision: bool = False) -> dict:
    """Ask the chosen local model a tiny question (and, if it should see, to say which colours are in a 2x2 picture). Proves the whole path works."""
    import time
    from .llm import DEFAULT_URLS, config
    c = config()
    model = name or (c.get("vision_model") if vision else c.get("model")) or ""
    if not model:
        raise SystemExit("Choose a model first (press Use next to one).")
    base = DEFAULT_URLS.get(server) or DEFAULT_URLS["ollama"]
    content: object = "Reply with the single word: ready"
    if vision:
        content = [{"type": "text", "text": "Which two colours are in this tiny picture? Answer in a few words."},
                   {"type": "image_url", "image_url": {"url": "data:image/png;base64," + _test_png()}}]
    t0 = time.time()
    try:
        r = requests.post(base.rstrip("/") + "/chat/completions", json={"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": 40, "stream": False}, timeout=300)
    except requests.ConnectionError:
        raise SystemExit(f"{'Ollama' if server == 'ollama' else 'LM Studio'} isn't running. Start it above, then test again.")
    except requests.RequestException as e:
        raise SystemExit(f"The test didn't finish ({type(e).__name__}). The model may still be loading: try again in a minute.")
    if r.status_code >= 400:
        raise SystemExit(friendly(r.text, server))
    try:
        answer = (r.json()["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, ValueError):
        raise SystemExit("The server answered, but not in a form PULSEFRAME understands.")
    secs = round(time.time() - t0, 1)
    out = {"ok": bool(answer), "model": model, "seconds": secs, "answer": answer[:200], "vision": vision}
    if vision:
        low = answer.lower()
        out["saw"] = "red" in low and "blue" in low
        if not out["saw"]:
            out["note"] = "It answered but didn't name red and blue, so it may not be able to see images. Pick a model marked 'sees images' for this job."
    return out


def delete(name: str) -> dict:
    try:
        r = requests.delete(OLLAMA + "/api/delete", json={"model": name}, timeout=30)
    except requests.RequestException:
        raise SystemExit("Ollama isn't running.")
    if r.status_code >= 400:
        raise SystemExit(f"Ollama couldn't remove {name}: {r.text[:200]}")
    return status()


def use(name: str, role: str, server: str = "ollama") -> dict:
    """Make a local model the AI brain's planning model, vision model, or both."""
    from .llm import DEFAULT_URLS, config, save
    c = config()
    if c["provider"] != server:
        c = {"provider": server, "base_url": DEFAULT_URLS[server], "model": "", "vision_model": ""}
    if role in ("planning", "both"):
        c["model"] = name
    if role in ("vision", "both"):
        c["vision_model"] = name
    if not c["model"]:
        c["model"] = name
    save(c)
    return status()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="pulseframe-localmodels")
    ap.add_argument("action", choices=["status", "pull", "delete", "use", "start", "lms_get", "unload", "test"])
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        res = {"status": status, "pull": lambda: pull(x.get("name", "")), "delete": lambda: delete(x.get("name", "")),
               "use": lambda: use(x.get("name", ""), x.get("role", "both"), x.get("server", "ollama")),
               "start": lambda: start(x.get("which", "")), "lms_get": lambda: lms_get(x.get("name", "")), "unload": lambda: unload(x.get("name", "")),
               "test": lambda: test(x.get("server", "ollama"), x.get("name"), bool(x.get("vision")))}[a.action]()
        print(json.dumps({"event": "result", "data": res}), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
        return 1
    except Exception as e:
        print(json.dumps({"event": "error", "message": f"{type(e).__name__}: {e}"}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
