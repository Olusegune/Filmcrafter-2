"""ComfyUI provider: your own machine (or a server you run) renders with your own workflows. No per-render cost.

Setup (Settings → ComfyUI): the server address (default http://127.0.0.1:8188) and one or more workflows exported
from ComfyUI with "Save (API Format)". In the workflow, type these placeholders into any text/number field:

  {{prompt}}  {{negative}}  {{image}}  (the start frame / first reference, uploaded for you)
  {{seed}}  {{width}}  {{height}}  {{frames}}  {{fps}}  {{duration}}

A workflow without {{prompt}} gets the shot's prompt in its first positive CLIPTextEncode node; without {{image}},
its first LoadImage node receives the start frame. The first video/image the workflow saves becomes the take.
"""
from __future__ import annotations

import json
import os
import random
import re
import uuid

import requests

HOME = os.path.join(os.path.expanduser("~"), ".filmcrafter", "comfyui")
CONFIG = os.path.join(HOME, "config.json")
FLOWS = os.path.join(HOME, "workflows")
PH = re.compile(r"\{\{\s*(prompt|negative|image|seed|width|height|frames|fps|duration)\s*\}\}")
ASPECTS = ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "2.39:1", "4:5"]


def config() -> dict:
    try:
        with open(CONFIG, encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    return {"url": (os.environ.get("COMFYUI_URL") or c.get("url") or "http://127.0.0.1:8188").rstrip("/"),
            "max_side": int(c.get("max_side") or 1024), "fps": int(c.get("fps") or 24)}


def set_config(url: str | None = None, max_side: int | None = None, fps: int | None = None) -> dict:
    os.makedirs(HOME, exist_ok=True)
    c = {k: v for k, v in config().items()}
    if url is not None:
        if not re.match(r"^https?://[^\s/]+(:\d+)?/?$", url.strip()):
            raise SystemExit("Enter an address like http://127.0.0.1:8188")
        c["url"] = url.strip().rstrip("/")
    if max_side:
        c["max_side"] = int(max_side)
    if fps:
        c["fps"] = int(fps)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=2)
    return c


def reachable(timeout: float = 1.5) -> bool:
    try:
        return requests.get(config()["url"] + "/system_stats", timeout=timeout).status_code == 200
    except requests.RequestException:
        return False


def check() -> dict:
    """Settings: is the server there, what GPU, which workflows."""
    url = config()["url"]
    try:
        r = requests.get(url + "/system_stats", timeout=3)
        r.raise_for_status()
        dev = (r.json().get("devices") or [{}])[0]
        return {"url": url, "connected": True, "device": dev.get("name"), "workflows": workflows()}
    except (requests.RequestException, ValueError) as e:
        return {"url": url, "connected": False, "error": f"No ComfyUI at {url} ({type(e).__name__}). Start ComfyUI, then try again.",
                "workflows": workflows()}


def friendly(msg: str | None) -> str:
    """ComfyUI's errors in plain words, with the thing to do about each. Unknown errors pass through unchanged."""
    m = (msg or "")
    low = m.lower()
    if "out of memory" in low or "oom" in low.split() or "allocation on device" in low:
        return ("Your graphics card ran out of memory. Make the picture smaller (Settings → ComfyUI → size), close programs that use the card, "
                "or unload a local AI model (Settings → Models on this computer → Free memory). Original message: " + m[:160])
    if "value_not_in_list" in low or "not in list" in low:
        return ("This workflow names a model file that isn't installed in ComfyUI. Press “Check ComfyUI and update workflows” in Settings to rebuild "
                "the ready-made ones for the files you have, or download the missing models there. Original message: " + m[:160])
    if "missing_node_type" in low or "node type" in low and "not found" in low or "no node" in low:
        return ("ComfyUI is missing a node this workflow needs. Update ComfyUI (ComfyUI Desktop: Settings → About → Update; "
                "portable: run update/update_comfyui). Custom nodes can be added with ComfyUI-Manager. Original message: " + m[:160])
    if "required_input_missing" in low or "required input is missing" in low:
        return "A box in the workflow isn't connected to anything. Re-export it from ComfyUI with Workflow → Export (API), or use the ready-made ones. Original message: " + m[:160]
    if "connection" in low and ("refused" in low or "aborted" in low):
        return "ComfyUI stopped answering (it may have crashed or been closed). Start it again and retry. Original message: " + m[:160]
    return m


def _load(model: str) -> dict:
    path = os.path.join(FLOWS, f"{model}.json")
    if not os.path.exists(path):
        raise SystemExit(f"ComfyUI workflow “{model}” isn't in FilmCrafter. Add it in Settings → ComfyUI.")
    with open(path, encoding="utf-8") as f:
        g = json.load(f)
    if not isinstance(g, dict) or not all(isinstance(n, dict) and "class_type" in n for n in g.values()):
        raise SystemExit("That file isn't a ComfyUI API-format workflow. In ComfyUI use Workflow → Export (API).")
    return g


def _placeholders(g: dict) -> set[str]:
    return {m.group(1) for n in g.values() for v in (n.get("inputs") or {}).values() if isinstance(v, str) for m in PH.finditer(v)}


def _kind(g: dict) -> str:
    types = " ".join(n["class_type"] for n in g.values()).lower()
    return "video" if any(k in types for k in ("video", "vhs_", "animatediff", "wan", "ltx", "hunyuan", "frames")) else "image"


BUILT_IN_TITLES = {"filmcrafter-keyframes": "ComfyUI · SDXL keyframes", "filmcrafter-video-wan22": "ComfyUI · Wan 2.2 video"}


def workflows() -> list[dict]:
    out = []
    if not os.path.isdir(FLOWS):
        return out
    for name in sorted(os.listdir(FLOWS)):
        if not name.endswith(".json"):
            continue
        model = name[:-5]
        try:
            g = _load(model)
        except SystemExit:
            continue
        out.append({"model": model, "title": BUILT_IN_TITLES.get(model) or model.replace("_", " ").replace("-", " "), "kind": _kind(g),
                    "placeholders": sorted(_placeholders(g))})
    return out


def add_workflow(path: str, name: str | None = None) -> dict:
    with open(path, encoding="utf-8") as f:
        g = json.load(f)
    if not isinstance(g, dict) or not g or not all(isinstance(n, dict) and "class_type" in n for n in g.values()):
        raise SystemExit("That file isn't a ComfyUI API-format workflow. In ComfyUI use Workflow → Export (API).")
    model = re.sub(r"[^A-Za-z0-9_-]+", "-", (name or os.path.splitext(os.path.basename(path))[0])).strip("-") or "workflow"
    os.makedirs(FLOWS, exist_ok=True)
    with open(os.path.join(FLOWS, f"{model}.json"), "w", encoding="utf-8") as f:
        json.dump(g, f, indent=1)
    return next(w for w in workflows() if w["model"] == model)


def remove_workflow(model: str) -> list[dict]:
    p = os.path.join(FLOWS, f"{model}.json")
    if os.path.exists(p):
        os.remove(p)
    return workflows()


def manifest(model: str) -> dict:
    """A FilmCrafter manifest for a workflow, so ComfyUI shots use the same Shot Contract as cloud models."""
    from .render import _finish
    g = _load(model)
    ph = _placeholders(g)
    kind = _kind(g)

    def F(name, typ, desc, **kw):
        return {"name": name, "type": typ, "items": None, "enum": kw.get("enum"), "default": kw.get("default"),
                "minimum": kw.get("minimum"), "maximum": kw.get("maximum"), "max_items": None, "max_length": None,
                "description": desc, "required": kw.get("required", False)}
    fields = [F("prompt", "string", "What the shot shows (placed into {{prompt}} or the first positive text node)", required=True),
              F("negative_prompt", "string", "What to avoid ({{negative}})"),
              F("seed", "integer", "Seed ({{seed}}); empty = random")]
    has_image = "image" in ph or any(n["class_type"] == "LoadImage" for n in g.values())
    if has_image:
        fields.append(F("image_url", "string", "Start frame / reference image ({{image}} or the first LoadImage node)"))
    fields.append(F("aspect_ratio", "string", "Frame shape → {{width}} × {{height}}", enum=ASPECTS, default="16:9"))
    if kind == "video":
        # the ready-made Wan 2.2 5B workflow is made for 5-second clips (121 frames); longer shots hold their last frame
        cap = 5 if model.startswith("filmcrafter-video") else 20
        fields.append({**F("duration", "number", "Seconds → {{frames}} at {{fps}}", minimum=1, maximum=cap, default=5), "exact": True})
    m = _finish("comfyui", model, f"ComfyUI · {model}", f"workflow-{kind}", fields)
    m["comfy_kind"] = kind
    return m


def _dims(aspect: str, max_side: int) -> tuple[int, int]:
    a, b = (float(x) for x in (aspect or "16:9").split(":"))
    w, h = (max_side, max_side * b / a) if a >= b else (max_side * a / b, max_side)
    return int(round(w / 16) * 16), int(round(h / 16) * 16)


def fill(g: dict, payload: dict, image_name: str | None, cfg: dict) -> dict:
    """Put the shot's values into the workflow graph (a copy)."""
    g = json.loads(json.dumps(g))
    w, h = _dims(payload.get("aspect_ratio") or "16:9", cfg["max_side"])
    dur = float(payload.get("duration") or 5)
    fps = cfg["fps"]
    seed = payload.get("seed")
    vals = {"prompt": payload.get("prompt", ""), "negative": payload.get("negative_prompt", ""), "image": image_name or "",
            "seed": int(seed) if seed not in (None, "") else random.randint(0, 2 ** 31 - 1), "width": w, "height": h,
            "frames": int(round(dur * fps / 4)) * 4 + 1, "fps": fps, "duration": dur}   # 4n+1: what Wan-style models need
    ph = _placeholders(g)
    for n in g.values():
        for k, v in list((n.get("inputs") or {}).items()):
            if not isinstance(v, str):
                continue
            whole = PH.fullmatch(v.strip())
            if whole:
                n["inputs"][k] = vals[whole.group(1)]
            elif PH.search(v):
                n["inputs"][k] = PH.sub(lambda m: str(vals[m.group(1)]), v)
    if "prompt" not in ph:  # first text-encode node fed into a "positive" input
        pos = {str(n["inputs"]["positive"][0]) for n in g.values() if isinstance((n.get("inputs") or {}).get("positive"), list)}
        node = next((g[i] for i in pos if i in g and "text" in g[i].get("inputs", {})), None) or \
            next((n for n in g.values() if n["class_type"] == "CLIPTextEncode"), None)
        if node:
            node["inputs"]["text"] = vals["prompt"]
    if "image" not in ph and image_name:
        node = next((n for n in g.values() if n["class_type"] == "LoadImage"), None)
        if node:
            node["inputs"]["image"] = image_name
    return g


class ComfyUI:
    name = "comfyui"

    def __init__(self):
        self.cfg = config()
        self.url = self.cfg["url"]
        self.h = {}
        if not reachable():
            raise SystemExit(f"ComfyUI isn't running at {self.url}. Start it, or change the address in Settings → ComfyUI.")

    def upload(self, path: str) -> str:
        from .render import _raise
        with open(path, "rb") as f:
            r = requests.post(self.url + "/upload/image", files={"image": (os.path.basename(path), f)},
                              data={"overwrite": "true", "type": "input"}, timeout=120)
        _raise(r)
        j = r.json()
        return "comfy:" + (f"{j['subfolder']}/" if j.get("subfolder") else "") + j["name"]

    def submit(self, model: str, payload: dict) -> dict:
        from .render import ProviderError, _raise
        img = payload.get("image_url")
        name = img[len("comfy:"):] if isinstance(img, str) and img.startswith("comfy:") else None
        graph = fill(_load(model), payload, name, self.cfg)
        r = requests.post(self.url + "/prompt", json={"prompt": graph, "client_id": "filmcrafter-" + uuid.uuid4().hex[:8]}, timeout=60)
        if r.status_code == 400:  # ComfyUI explains which node is wrong
            j = r.json()
            errs = "; ".join(f"{v.get('class_type')}: {e.get('message')} {e.get('details', '')}".strip()
                             for v in (j.get("node_errors") or {}).values() for e in v.get("errors", []))
            raise ProviderError(friendly(f"invalid workflow: {errs or j.get('error', {}).get('message', r.text[:200])} ({json.dumps(j.get('node_errors') or {})[:200]})"), 400)
        _raise(r)
        return {"id": r.json()["prompt_id"]}

    def poll(self, model: str, rid: str, meta: dict | None = None) -> dict:
        from .render import http_get
        r = http_get(f"{self.url}/history/{rid}", timeout=30)
        h = (r.json() or {}).get(rid) if r.status_code == 200 else None
        if not h:
            q = http_get(self.url + "/queue", timeout=30).json()
            pos = next((i for i, it in enumerate(q.get("queue_pending", [])) if it[1] == rid), None)
            return {"state": "running", "detail": "rendering" if pos is None else f"waiting (#{pos + 1})"}
        st = h.get("status") or {}
        if st.get("status_str") == "error":
            msg = next((m[1].get("exception_message") for m in st.get("messages", []) if m[0] == "execution_error"), None)
            return {"state": "failed", "error": friendly(msg) if msg else "The workflow failed in ComfyUI."}
        files = []
        for out in (h.get("outputs") or {}).values():
            for key in ("videos", "gifs", "images"):
                files += [(key, f) for f in out.get(key) or [] if f.get("type") == "output"]
        files.sort(key=lambda x: {"videos": 0, "gifs": 1, "images": 2}[x[0]])
        if not files:
            return {"state": "failed", "error": "The workflow finished but saved no image or video. Add a Save node."}
        f = files[0][1]
        from urllib.parse import urlencode
        url = f"{self.url}/view?" + urlencode({"filename": f["filename"], "subfolder": f.get("subfolder", ""), "type": "output"})
        return {"state": "done", "url": url, "cost": 0, "cost_unit": "local"}
