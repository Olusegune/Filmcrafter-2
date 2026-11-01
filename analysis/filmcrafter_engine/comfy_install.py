"""Install ComfyUI for people who are afraid of it: one button, no terminal, no Python, no git.

On Windows ComfyUI publishes a "portable" build for each kind of graphics card (NVIDIA, AMD, Intel): a folder that holds its own Python and everything it needs, so nothing is
installed on the system and removing it is deleting one folder. This downloads the official build from ComfyUI's own GitHub releases, checks it against the checksum GitHub publishes,
unpacks it with the tar that ships with Windows (it reads 7z), and hands the start script to comfy_setup, which starts it, finds it and sets up the ready-made workflows.

  plan     free: which build suits this computer, how big it is, where it would go, whether there is room (reads one web page; downloads nothing)
  install  downloads, checks, unpacks (resumable: run it again after an interruption)

  python -m filmcrafter_engine.comfy_install <plan|install> --data '{"dest": "..."}'

Mac and Linux are not covered (ComfyUI has an official Mac app, and Linux users have their own tools); the plan says so and gives the address.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

import requests

RELEASE_API = "https://api.github.com/repos/comfyanonymous/ComfyUI/releases/latest"
SOURCE = "github.com/comfyanonymous/ComfyUI (releases)"
ASSETS = {"nvidia": re.compile(r"^ComfyUI_windows_portable_nvidia\.7z$"), "amd": re.compile(r"^ComfyUI_windows_portable_amd\.7z$"),
          "intel": re.compile(r"^ComfyUI_windows_portable_intel\.7z$")}
TRUSTED_PREFIX = "https://github.com/Comfy-Org/ComfyUI/releases/download/"
TRUSTED_PREFIXES = (TRUSTED_PREFIX, "https://github.com/comfyanonymous/ComfyUI/releases/download/")
UNPACKED_PER_PACKED = 3.4        # the archive is about this much smaller than the folder it makes
SPARE_GB = 4.0                   # room left over for the models you will download next
MIN_VRAM_GB = 6.0
NOWIN = 0x08000000 if sys.platform == "win32" else 0
UA = {"User-Agent": "FilmCrafter", "Accept": "application/vnd.github+json"}
MAC_URL = "https://www.comfy.org/download"


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


def _registry_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".filmcrafter", "comfyui", "installs.json")


def registry() -> list[str]:
    """Folders of ComfyUI copies this app installed (so it can start them wherever they were put)."""
    try:
        with open(_registry_path(), encoding="utf-8") as f:
            return [p for p in json.load(f) if isinstance(p, str)]
    except (OSError, ValueError):
        return []


def remember(path: str) -> None:
    os.makedirs(os.path.dirname(_registry_path()), exist_ok=True)
    cur = [p for p in registry() if p.lower() != path.lower()] + [path]
    with open(_registry_path(), "w", encoding="utf-8") as f:
        json.dump(cur, f)


def default_dest() -> str:
    return os.path.join(os.path.expanduser("~"), "FilmCrafter ComfyUI")


def pick_asset(assets: list[dict], vendor: str) -> dict | None:
    """The release file for this kind of graphics card, from GitHub's list. Pure."""
    rx = ASSETS.get(vendor)
    a = next((x for x in assets if rx and rx.match(x.get("name", ""))), None)
    if not a:
        return None
    digest = str(a.get("digest") or "")
    url = a.get("browser_download_url")
    if not isinstance(url, str) or not url.startswith(TRUSTED_PREFIXES):       # only ever download from ComfyUI's own repository on github.com
        return None
    return {"name": a["name"], "size": int(a.get("size") or 0), "url": url, "sha256": digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else None}


def find_start_script(root: str) -> str | None:
    """The batch file that starts a portable ComfyUI: a graphics-card one when there is one, else the processor one."""
    bats = sorted(glob.glob(os.path.join(root, "run_*.bat")))
    gpu = [b for b in bats if "gpu" in os.path.basename(b).lower()]
    cpu = [b for b in bats if "cpu" in os.path.basename(b).lower()]
    return (gpu or cpu or [None])[0]


def find_portable(dest: str) -> str | None:
    """The unpacked ComfyUI folder under `dest` (the archive holds one folder, ComfyUI_windows_portable), if it is there."""
    for p in (os.path.join(dest, "ComfyUI_windows_portable"), dest):
        if os.path.isdir(p) and find_start_script(p) and os.path.isdir(os.path.join(p, "ComfyUI")):
            return p
    return None


def space_needed_gb(size_bytes: int) -> float:
    return round(size_bytes / 1e9 * (1 + UNPACKED_PER_PACKED) + SPARE_GB, 1)


def _free_gb(path: str) -> float | None:
    probe = path
    while probe and not os.path.exists(probe) and os.path.dirname(probe) != probe:
        probe = os.path.dirname(probe)
    try:
        return round(shutil.disk_usage(probe).free / 1e9, 1)
    except OSError:
        return None


def plan(dest: str | None = None, vendor: str | None = None) -> dict:
    """What would be installed, where, and whether it can be. Reads one web page; downloads nothing."""
    from . import hardware
    dest = os.path.abspath(dest or default_dest())
    out: dict = {"dest": dest, "source": SOURCE, "ok": False, "warnings": [], "reason": ""}
    if sys.platform != "win32":
        out["reason"] = "One-click install is for Windows. On a Mac, ComfyUI has an official app you can download."
        out["manual_url"] = MAC_URL
        return out
    existing = find_portable(dest)
    if existing:
        out.update({"installed": True, "path": existing, "start": find_start_script(existing), "reason": "ComfyUI is already installed there."})
        return out
    hw = hardware.report(dest)
    gpu = hw.get("gpu") or {}
    v = vendor or (gpu.get("vendor") if gpu.get("vendor") in ASSETS else None)
    out.update({"gpu": gpu.get("name"), "vendor": v, "vram_gb": gpu.get("vram_gb"), "ram_gb": hw.get("ram_gb")})
    if not v:
        out["reason"] = "No NVIDIA, AMD or Intel graphics card was found, so ComfyUI would have nothing to run on. Use a cloud model for video instead."
        return out
    if gpu.get("vram_gb") and gpu["vram_gb"] < MIN_VRAM_GB:
        out["warnings"].append(f"Your card has {gpu['vram_gb']:g} GB of video memory. Pictures will work at modest sizes; video needs about 8 GB.")
    if v == "amd":
        out["warnings"].append("AMD cards work with ComfyUI on Windows, but support is newer and some models are slower than on NVIDIA.")
    if v == "intel":
        out["warnings"].append("Intel graphics are supported but slow; this is best for small pictures.")
    try:
        r = requests.get(RELEASE_API, headers=UA, timeout=20)
        r.raise_for_status()
        rel = r.json()
    except (requests.RequestException, ValueError) as e:
        out["reason"] = f"Couldn't reach GitHub to find the latest ComfyUI ({type(e).__name__}). Check the internet connection and try again."
        return out
    a = pick_asset(rel.get("assets") or [], v)
    if not a or not a["url"] or not a["size"]:
        out["reason"] = f"ComfyUI's latest release has no Windows build for {v.upper()} cards. Download ComfyUI from {MAC_URL}."
        out["manual_url"] = MAC_URL
        return out
    if not a["sha256"]:
        out["reason"] = "GitHub didn't publish a checksum for this ComfyUI build, so it can't be verified. It was not downloaded; use ComfyUI Desktop from comfy.org instead."
        out["manual_url"] = MAC_URL
        return out
    need = space_needed_gb(a["size"])
    free = _free_gb(dest)
    out.update({"tag": rel.get("tag_name"), "asset": a, "download_gb": round(a["size"] / 1e9, 1), "need_gb": need, "free_gb": free})
    if free is not None and free < need:
        out["reason"] = f"Not enough disk space: about {need:g} GB is needed (the download, the unpacked folder, and room for models) and {free:g} GB is free. Choose another folder or free some space."
        return out
    if os.path.exists(dest) and os.listdir(dest):
        out["reason"] = "That folder already has other files in it. Choose an empty folder, or leave the default."
        return out
    out["ok"] = True
    return out


# ---------------------------------------------------------------- doing it

def _sha256(path: str, total: int) -> str:
    h, done = hashlib.sha256(), 0
    last = -1
    with open(path, "rb") as f:
        while True:
            b = f.read(8 << 20)
            if not b:
                break
            h.update(b)
            done += len(b)
            pct = int(done * 100 / max(1, total))
            if pct != last and pct % 5 == 0:
                last = pct
                emit(event="progress", stage="checking the download", progress=round(0.62 + 0.05 * done / max(1, total), 3))
    return h.hexdigest()


def download(a: dict, folder: str) -> str:
    """Download the archive to `folder`, resuming a partial one, and check its size and checksum. Returns the finished file's path."""
    os.makedirs(folder, exist_ok=True)
    final = os.path.join(folder, a["name"])
    part = final + ".part"
    if os.path.exists(final) and os.path.getsize(final) == a["size"]:
        return final
    have = os.path.getsize(part) if os.path.exists(part) else 0
    if have > a["size"]:
        os.remove(part)
        have = 0
    headers = {**UA, **({"Range": f"bytes={have}-"} if have else {})}
    try:
        with requests.get(a["url"], stream=True, timeout=(15, 120), headers=headers) as r:
            if r.status_code not in (200, 206):
                raise SystemExit(f"GitHub didn't send the download ({r.status_code}). Try again in a minute.")
            mode, got = ("ab", have) if r.status_code == 206 else ("wb", 0)
            last = -1
            with open(part, mode) as f:
                for chunk in r.iter_content(4 << 20):
                    f.write(chunk)
                    got += len(chunk)
                    pct = int(got * 100 / a["size"])
                    if pct != last:
                        last = pct
                        emit(event="progress", stage="downloading ComfyUI", progress=round(0.6 * got / a["size"], 3))
    except requests.RequestException as e:
        raise SystemExit(f"The download was interrupted ({type(e).__name__}). Press Install again and it will carry on where it stopped.")
    if os.path.getsize(part) != a["size"]:
        raise SystemExit("The download stopped early. Press Install again and it will carry on where it stopped.")
    if a.get("sha256") and _sha256(part, a["size"]) != a["sha256"]:
        os.remove(part)
        raise SystemExit("The downloaded file didn't match GitHub's checksum, so it was thrown away. Press Install again to download it afresh.")
    os.replace(part, final)
    return final


def extractor() -> list[str] | None:
    """The program that unpacks a .7z: the tar that ships with Windows (it reads 7z), else 7-Zip if it is installed."""
    sysroot = os.environ.get("SystemRoot", "C:\\Windows")
    tar = os.path.join(sysroot, "System32", "tar.exe")
    if os.path.exists(tar):
        return [tar, "-xf"]
    for z in (os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "7-Zip", "7z.exe"), shutil.which("7z") or ""):
        if z and os.path.exists(z):
            return [z, "x", "-y"]
    return None


def _folder_bytes(path: str) -> int:
    n = 0
    for root, _d, files in os.walk(path):
        for f in files:
            try:
                n += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return n


def unpack(archive: str, dest: str, packed_bytes: int) -> None:
    ex = extractor()
    if not ex:
        raise SystemExit("Nothing on this computer can unpack a .7z file. Install the free 7-Zip (7-zip.org) and press Install again; the download is kept.")
    os.makedirs(dest, exist_ok=True)
    cmd = ex + [archive, "-C", dest] if ex[0].lower().endswith("tar.exe") else ex + [f"-o{dest}", archive]
    stop = threading.Event()
    expected = packed_bytes * UNPACKED_PER_PACKED

    def watch():                                    # the unpacker says nothing while it works: watch the folder grow
        last = -1
        while not stop.wait(2.0):
            pct = min(99, int(_folder_bytes(dest) * 100 / expected))
            if pct != last:
                last = pct
                emit(event="progress", stage="unpacking ComfyUI", progress=round(0.67 + 0.3 * pct / 100, 3))
    t = threading.Thread(target=watch, daemon=True)
    t.start()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, creationflags=NOWIN, timeout=3 * 3600)
    finally:
        stop.set()
    if p.returncode:
        raise SystemExit("Unpacking failed: " + ((p.stderr or p.stdout or "no message").strip()[-300:]) + " The download is kept; press Install again.")


def install(dest: str | None = None, vendor: str | None = None) -> dict:
    p = plan(dest, vendor)
    if p.get("installed"):
        return p
    if not p["ok"]:
        raise SystemExit(p["reason"] or "ComfyUI can't be installed here.")
    a, dest = p["asset"], p["dest"]
    emit(event="progress", stage="starting", progress=0.0)
    archive = download(a, os.path.join(dest + ".download"))
    try:
        unpack(archive, dest, a["size"])
    except SystemExit:
        shutil.rmtree(dest, ignore_errors=True)       # a half-unpacked folder is worse than none; the download stays
        raise
    root = find_portable(dest)
    if not root:
        shutil.rmtree(dest, ignore_errors=True)
        raise SystemExit("ComfyUI unpacked, but its start script wasn't where it should be. The download is kept; press Install again.")
    shutil.rmtree(dest + ".download", ignore_errors=True)            # the 2 GB archive has done its job
    remember(root)
    emit(event="progress", stage="done", progress=1.0)
    return {"installed": True, "path": root, "start": find_start_script(root), "tag": p.get("tag"), "dest": dest}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-comfy-install")
    ap.add_argument("action", choices=["plan", "install"])
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        res = plan(x.get("dest"), x.get("vendor")) if a.action == "plan" else install(x.get("dest"), x.get("vendor"))
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
