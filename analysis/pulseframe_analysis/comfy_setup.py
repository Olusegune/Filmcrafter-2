"""ComfyUI without the nodes: find it, start it, and install ready-made PULSEFRAME workflows.

detect()   finds a running ComfyUI on the usual ports (8188 classic/portable, 8000 ComfyUI Desktop, ...) and, if none
           is running, installed copies it could start (ComfyUI Desktop, the portable build, common folders).
start()    launches an installed copy.
setup()    reads what the running ComfyUI has (nodes and model files) and writes ready-made workflows for it:
             - Keyframes: text-to-image with any image checkpoint (SDXL, SD 1.5, ...)
             - Video: Wan 2.2 5B image-to-video (starts from the approved keyframe; runs on ordinary GPUs)
           Each template says exactly which model file is missing when it can't be installed yet.

  python -m pulseframe_analysis.comfy_setup <detect|start|setup> --data '{...}'
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys

import requests

PORTS = [8188, 8000, 8189, 8288, 8001]
HOSTS = ["127.0.0.1", "localhost"]


def _get(url: str, timeout: float = 2.0):
    try:
        r = requests.get(url, timeout=timeout)
        return r if r.status_code == 200 else None
    except requests.RequestException:
        return None


def _desktop_ports() -> list[int]:
    """Comfy Desktop writes the port it runs on (port-locks/port-8188.json)."""
    roaming = os.environ.get("APPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Roaming"))
    out = []
    for p in glob.glob(os.path.join(roaming, "Comfy Desktop", "port-locks", "port-*.json")) + \
            glob.glob(os.path.join(roaming, "ComfyUI", "port-locks", "port-*.json")):
        try:
            out.append(int(os.path.basename(p)[5:-5]))
        except ValueError:
            pass
    return out


def running() -> list[dict]:
    found = []
    for port in list(dict.fromkeys(_desktop_ports() + PORTS)):
        for host in HOSTS:
            r = _get(f"http://{host}:{port}/system_stats", 1.5)
            if r is not None:
                try:
                    s = r.json()
                except ValueError:
                    continue
                dev = (s.get("devices") or [{}])[0]
                found.append({"url": f"http://{host}:{port}", "version": (s.get("system") or {}).get("comfyui_version"),
                              "device": dev.get("name"), "vram_gb": round((dev.get("vram_total") or 0) / 1e9, 1)})
                break
    return found


def find_start_script(root: str) -> str | None:
    from .comfy_install import find_start_script as f
    return f(root)


def installed_here() -> list[str]:
    from .comfy_install import registry
    return [p for p in registry() if os.path.isdir(p)]


def installs() -> list[dict]:
    """Installed ComfyUI copies we know how to start (nothing is run here)."""
    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
    out = []
    pf = [os.environ.get("ProgramFiles", "C:\\Program Files"), os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")]
    desktop_exes = [os.path.join(local, "Programs", n, "ComfyUI.exe") for n in ("ComfyUI", "@comfyorgcomfyui-electron", "comfyui-electron")]
    desktop_exes += [os.path.join(b, "Comfy Desktop", "Comfy Desktop.exe") for b in pf + [os.path.join(local, "Programs")]]
    desktop_exes += [os.path.join(b, "ComfyUI", "ComfyUI.exe") for b in pf]
    desktop_exes += ["/Applications/ComfyUI.app", "/Applications/Comfy Desktop.app"]
    for exe in desktop_exes:
        if os.path.exists(exe):
            out.append({"kind": "ComfyUI Desktop", "path": exe, "start": exe})
    roots = [home, os.path.join(home, "Documents"), os.path.join(home, "Desktop"), os.path.join(home, "Downloads"), "C:\\", "D:\\", "E:\\"]
    # Stability Matrix keeps ComfyUI in <root>/Stability Matrix/Packages/ComfyUI*
    for r in ("C:\\", "D:\\", "E:\\", home, local):
        for p in glob.glob(os.path.join(r, "Stability Matrix", "Packages", "ComfyUI*")) + glob.glob(os.path.join(r, "StabilityMatrix", "Data", "Packages", "ComfyUI*")):
            if os.path.isdir(p):
                out.append({"kind": "ComfyUI (Stability Matrix)", "path": p, "start": None,
                            "hint": "Start it from Stability Matrix, then press Find ComfyUI."})
    seen = set()
    for p in installed_here():     # copies PULSEFRAME installed itself, wherever the user chose to put them
        seen.add(p.lower())
        bat = find_start_script(p)
        if bat:
            out.append({"kind": "ComfyUI portable (installed by PULSEFRAME)", "path": p, "start": bat})
    for r in roots:
        for pat in ("ComfyUI_windows_portable*", "ComfyUI*", "*/ComfyUI_windows_portable*"):
            for p in glob.glob(os.path.join(r, pat)):
                if not os.path.isdir(p) or p.lower() in seen:
                    continue
                seen.add(p.lower())
                bat = find_start_script(p)
                if bat:
                    out.append({"kind": "ComfyUI portable", "path": p, "start": bat})
                elif os.path.exists(os.path.join(p, "main.py")) and os.path.isdir(os.path.join(p, "comfy")):
                    out.append({"kind": "ComfyUI (from source)", "path": p, "start": None})
    return out


def detect() -> dict:
    from . import comfy
    run = running()
    if run:
        comfy.set_config(url=run[0]["url"])   # remember where it is
    return {"running": run, "installs": [] if run else installs(), "configured_url": comfy.config()["url"]}


def start(path: str) -> dict:
    """Start an installed copy (the user pressed the button). Returns immediately; call detect() again in a moment."""
    ok = {i["start"] for i in installs() if i["start"]}
    if path not in ok:
        raise SystemExit("That isn't a ComfyUI copy PULSEFRAME found on this computer.")
    if path.endswith(".app"):
        subprocess.Popen(["open", path])
    elif path.lower().endswith(".bat"):
        subprocess.Popen(["cmd", "/c", "start", "", path], cwd=os.path.dirname(path), creationflags=0x08000000)
    else:
        subprocess.Popen([path], cwd=os.path.dirname(path), creationflags=0x00000008 if sys.platform == "win32" else 0)
    return {"started": path}


# ---------------------------------------------------------------- ready-made workflows

def _options(info: dict, node: str, field: str) -> list[str]:
    try:
        spec = info[node]["input"]["required"][field][0]
        return list(spec) if isinstance(spec, list) else []
    except (KeyError, IndexError, TypeError):
        return []


def _pick(options: list[str], *needles: str) -> str | None:
    low = [(o, o.lower()) for o in options]
    for n in needles:
        hit = next((o for o, l in low if n in l), None)
        if hit:
            return hit
    return None


def still_template(ckpt: str) -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{negative}}", "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": "{{width}}", "height": "{{height}}", "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
                                                    "seed": "{{seed}}", "steps": 28, "cfg": 6.0, "sampler_name": "dpmpp_2m",
                                                    "scheduler": "karras", "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "pulseframe_still"}},
    }


def wan22_template(unet: str, clip: str, vae: str) -> dict:
    """Wan 2.2 TI2V 5B, image-to-video from the approved keyframe (the layout of ComfyUI's own template)."""
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": clip, "type": "wan", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "4": {"class_type": "LoadImage", "inputs": {"image": "{{image}}"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{negative}}", "clip": ["2", 0]}},
        "7": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
        "8": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["3", 0], "start_image": ["4", 0], "width": "{{width}}",
                                                                   "height": "{{height}}", "length": "{{frames}}", "batch_size": 1}},
        "9": {"class_type": "KSampler", "inputs": {"model": ["7", 0], "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["8", 0],
                                                    "seed": "{{seed}}", "steps": 20, "cfg": 5.0, "sampler_name": "uni_pc",
                                                    "scheduler": "simple", "denoise": 1.0}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}},
        "11": {"class_type": "CreateVideo", "inputs": {"images": ["10", 0], "fps": "{{fps}}"}},
        "12": {"class_type": "SaveVideo", "inputs": {"video": ["11", 0], "filename_prefix": "pulseframe_take", "format": "mp4", "codec": "h264"}},
    }


WAN_FILES = {"unet": "wan2.2_ti2v_5B_fp16.safetensors (diffusion_models)", "clip": "umt5_xxl_fp8_e4m3fn_scaled.safetensors (text_encoders)",
             "vae": "wan2.2_vae.safetensors (vae)"}


def plan(info: dict) -> list[dict]:
    """What ready-made workflows this ComfyUI can run, from its node list and model files. Pure: no network."""
    out = []
    ckpts = _options(info, "CheckpointLoaderSimple", "ckpt_name")
    ck = _pick(ckpts, "xl", "juggernaut", "realvis", "dreamshaper", "sd_xl", "v1-5", "") if ckpts else None
    out.append({"id": "pulseframe-keyframes", "title": "PULSEFRAME keyframes (image)", "kind": "image",
                "ready": bool(ck), "uses": ck, "graph": still_template(ck) if ck else None,
                "missing": [] if ck else ["any image checkpoint in models/checkpoints (for example an SDXL model)"]})
    needs_nodes = [n for n in ("UNETLoader", "CLIPLoader", "VAELoader", "Wan22ImageToVideoLatent", "CreateVideo", "SaveVideo", "ModelSamplingSD3")
                   if n not in info]
    unets, clips, vaes = (_options(info, "UNETLoader", "unet_name"), _options(info, "CLIPLoader", "clip_name"), _options(info, "VAELoader", "vae_name"))
    u, c, v = _pick(unets, "ti2v_5b", "wan2.2_ti2v", "ti2v"), _pick(clips, "umt5"), _pick(vaes, "wan2.2_vae", "wan2_2_vae")
    missing = []
    if needs_nodes:
        missing.append("a newer ComfyUI (update it: missing " + ", ".join(needs_nodes) + ")")
    for key, have in (("unet", u), ("clip", c), ("vae", v)):
        if not have:
            missing.append(WAN_FILES[key])
    ready = not missing
    out.append({"id": "pulseframe-video-wan22", "title": "PULSEFRAME video (Wan 2.2 5B, from the keyframe)", "kind": "video",
                "ready": ready, "uses": ", ".join(x for x in (u, c, v) if x), "graph": wan22_template(u, c, v) if ready else None,
                "missing": missing})
    return out


def setup(url: str | None = None) -> dict:
    from . import comfy
    base = (url or comfy.config()["url"]).rstrip("/")
    r = _get(base + "/object_info", 30)
    if r is None:
        raise SystemExit(f"ComfyUI isn't answering at {base}. Start it, then press Find ComfyUI.")
    items = plan(r.json())
    os.makedirs(comfy.FLOWS, exist_ok=True)
    for it in items:
        if it["ready"]:
            with open(os.path.join(comfy.FLOWS, it["id"] + ".json"), "w", encoding="utf-8") as f:
                json.dump(it["graph"], f, indent=1)
    return {"url": base, "templates": [{k: v for k, v in it.items() if k != "graph"} for it in items], "workflows": comfy.workflows()}


MODEL_FILES = {
    "pulseframe-keyframes": [("checkpoints", "sd_xl_base_1.0.safetensors",
                              "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors", 6.94)],
    "pulseframe-video-wan22": [
        ("diffusion_models", "wan2.2_ti2v_5B_fp16.safetensors",
         "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors", 10.0),
        ("text_encoders", "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
         "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", 6.74),
        ("vae", "wan2.2_vae.safetensors",
         "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan2.2_vae.safetensors", 1.41)],
}


def _folders(base: str) -> dict:
    r = _get(base + "/internal/folder_paths", 10)
    if r is None:
        raise SystemExit("ComfyUI isn't answering. Start it, then try again.")
    return r.json()


def downloads(templates: list[str], url: str | None = None) -> dict:
    """What would be downloaded (and where), for the price line: nothing is fetched here."""
    from . import comfy
    base = (url or comfy.config()["url"]).rstrip("/")
    folders = _folders(base)
    files = []
    for t in templates:
        for key, name, src, gb in MODEL_FILES.get(t, []):
            dests = folders.get(key) or folders.get({"diffusion_models": "unet", "text_encoders": "clip"}.get(key, key)) or []
            if not dests:
                raise SystemExit(f"ComfyUI has no {key} folder.")
            have = any(os.path.exists(os.path.join(p, name)) for p in dests)
            if not have:
                files.append({"folder": dests[0], "name": name, "url": src, "gb": gb})
    import shutil
    need = sum(f["gb"] for f in files)
    free = None
    if files:
        probe = files[0]["folder"]
        while probe and not os.path.exists(probe) and os.path.dirname(probe) != probe:   # the folder may not exist yet
            probe = os.path.dirname(probe)
        free = shutil.disk_usage(probe).free / 1e9
    return {"files": files, "gb": round(need, 1), "free_gb": round(free, 1) if free else None}


def download(templates: list[str], url: str | None = None) -> dict:
    """Download the missing model files into ComfyUI's model folders (resumable), then set the workflows up."""
    plan_ = downloads(templates, url)
    if plan_["free_gb"] is not None and plan_["gb"] + 2 > plan_["free_gb"]:
        raise SystemExit(f"Not enough disk space: {plan_['gb']} GB needed, {plan_['free_gb']} GB free.")
    total = sum(f["gb"] for f in plan_["files"]) * 1e9 or 1
    done_before = 0.0
    for f in plan_["files"]:
        os.makedirs(f["folder"], exist_ok=True)
        dest = os.path.join(f["folder"], f["name"])
        part = dest + ".pulseframe-part"
        have = os.path.getsize(part) if os.path.exists(part) else 0
        headers = {"Range": f"bytes={have}-"} if have else {}
        with requests.get(f["url"], stream=True, timeout=(10, 120), headers=headers) as r:
            if r.status_code not in (200, 206):
                raise SystemExit(f"Download of {f['name']} failed ({r.status_code}).")
            mode = "ab" if r.status_code == 206 else "wb"
            got = have if mode == "ab" else 0
            with open(part, mode) as out:
                for chunk in r.iter_content(4 << 20):
                    out.write(chunk)
                    got += len(chunk)
                    print(json.dumps({"event": "progress", "stage": f"downloading {f['name']}",
                                      "progress": round((done_before + got) / total, 3)}), flush=True)
        os.replace(part, dest)
        done_before += f["gb"] * 1e9
    return setup(url)


def health(url: str | None = None) -> dict:
    """One honest look at ComfyUI: is it up, how much graphics memory is free, what is queued, which ready-made workflows can run, and what to do next."""
    from . import comfy
    base = (url or comfy.config()["url"]).rstrip("/")
    r = _get(base + "/system_stats", 4)
    if r is None:
        return {"url": base, "connected": False, "advice": [f"ComfyUI isn't answering at {base}. Press Find ComfyUI (it can start an installed copy for you)."]}
    j = r.json()
    dev = (j.get("devices") or [{}])[0]
    total, free = (dev.get("vram_total") or 0) / 1e9, (dev.get("vram_free") or 0) / 1e9
    q = _get(base + "/queue", 4)
    qj = q.json() if q is not None else {}
    info = _get(base + "/object_info", 30)
    templates = [{k: v for k, v in it.items() if k != "graph"} for it in plan(info.json())] if info is not None else []
    out = {"url": base, "connected": True, "version": (j.get("system") or {}).get("comfyui_version"), "device": dev.get("name"),
           "vram_gb": round(total, 1), "vram_free_gb": round(free, 1), "running": len(qj.get("queue_running", [])), "waiting": len(qj.get("queue_pending", [])),
           "templates": templates, "advice": advise(total, free, templates)}
    return out


def advise(total_gb: float, free_gb: float, templates: list[dict]) -> list[str]:
    """Plain next steps from a health reading. Pure."""
    a = []
    if total_gb and total_gb < 6:
        a.append(f"Your card has {total_gb:.0f} GB of video memory. Pictures will work at modest sizes; video needs about 8 GB, so use a cloud model for video.")
    elif total_gb and total_gb < 8:
        a.append(f"{total_gb:.0f} GB is tight for video. Keep shots short, or use a cloud model for video.")
    if total_gb and free_gb and free_gb < min(4.0, total_gb * 0.4):
        a.append(f"Only {free_gb:.1f} GB of the card is free: another program (often an Ollama model) is holding it. Settings → Models on this computer → Free memory.")
    for t in templates:
        if not t.get("ready"):
            a.append(f"{t['title']}: " + "; ".join(t.get("missing") or ["not ready"]) + ". The Download button gets the model files for you.")
    if templates and all(t.get("ready") for t in templates) and not a:
        a.append("Everything is ready. Press “Make a test picture” to prove it end to end.")
    return a


def test(url: str | None = None) -> dict:
    """Render one small picture with the ready-made keyframe workflow, free, to prove the whole path works."""
    import time
    from . import comfy
    base = (url or comfy.config()["url"]).rstrip("/")
    h = health(base)
    if not h["connected"]:
        raise SystemExit(h["advice"][0])
    keyframes = next((t for t in h["templates"] if t["id"] == "pulseframe-keyframes"), None)
    if not keyframes or not keyframes["ready"]:
        raise SystemExit("There's no image model in ComfyUI yet. Press Download under the ready-made workflows (about 7 GB), then test again.")
    setup(base)
    old = os.environ.get("COMFYUI_URL")
    os.environ["COMFYUI_URL"] = base
    try:
        c = comfy.ComfyUI()
        c.cfg = {**c.cfg, "max_side": 512}
        t0 = time.time()
        sub = c.submit("pulseframe-keyframes", {"prompt": "a small brass lantern glowing on a dark wooden table, cinematic still", "negative_prompt": "text, watermark",
                                                 "aspect_ratio": "1:1", "seed": 7})
        while time.time() - t0 < 240:
            p = c.poll("pulseframe-keyframes", sub["id"])
            if p["state"] == "done":
                return {"ok": True, "seconds": round(time.time() - t0, 1), "url": p["url"]}
            if p["state"] == "failed":
                raise SystemExit(p["error"])
            print(json.dumps({"event": "progress", "stage": "making the test picture"}), flush=True)
            time.sleep(1.5)
        raise SystemExit("The test picture took more than four minutes. The first render loads the model into memory and can be slow; try once more.")
    finally:
        if old is None:
            os.environ.pop("COMFYUI_URL", None)
        else:
            os.environ["COMFYUI_URL"] = old


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="pulseframe-comfy-setup")
    ap.add_argument("action", choices=["detect", "start", "setup", "downloads", "download", "health", "test"])
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        res = detect() if a.action == "detect" else start(x.get("path", "")) if a.action == "start" else \
            downloads(x.get("templates") or [], x.get("url")) if a.action == "downloads" else \
            download(x.get("templates") or [], x.get("url")) if a.action == "download" else health(x.get("url")) if a.action == "health" else \
            test(x.get("url")) if a.action == "test" else setup(x.get("url"))
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
