"""Provider router: model families by name, which providers carry them, and what has been verified live.

"Regenerate shot 12 using Kling" -> family "kling" -> the provider you have a key for -> a concrete model id.
`verified` records models that produced a real render end to end (date + provider); everything else is
schema-checked only. Never mark a model verified from mocked tests.
"""
from __future__ import annotations

import os
import re

# family -> {provider: model id}; order = preference when several providers are available
FAMILIES: dict[str, dict] = {
    "seedance": {"label": "Seedance 2", "kind": "video", "fal": "bytedance/seedance-2.0/reference-to-video", "kie": "bytedance/seedance-2"},
    "kling": {"label": "Kling", "kind": "video", "fal": "fal-ai/kling-video/v3/turbo/pro/image-to-video", "kie": "kling-2.6/image-to-video"},
    "veo": {"label": "Veo 3.1", "kind": "video", "fal": "fal-ai/veo3.1/fast/image-to-video", "google": "veo-3.1-fast-generate-preview"},
    "hailuo": {"label": "MiniMax Hailuo 2.3", "kind": "video", "fal": "fal-ai/minimax/hailuo-2.3/standard/image-to-video",
               "kie": "hailuo/2-3-image-to-video-standard"},
    "wan": {"label": "Wan 3.0", "kind": "video", "fal": "alibaba/wan-3.0/image-to-video", "kie": "wan/3-0-video"},
    "ltx": {"label": "LTX 2.3", "kind": "video", "fal": "fal-ai/ltx-2.3/image-to-video"},
    "gpt-image": {"label": "GPT Image 2.5 Flare", "kind": "image", "openai": "gpt-image-2.5-flare",
                  "fal": "openai/gpt-image-2.5/flare/edit", "kie": "gpt/gpt-image-2-5-flare-image-to-image"},
    "gpt-image-sunburst": {"label": "GPT Image 2.5 Sunburst", "kind": "image", "openai": "gpt-image-2.5-sunburst",
                           "fal": "openai/gpt-image-2.5/sunburst/edit", "kie": "gpt/gpt-image-2-5-sunburst-image-to-image"},
    # budget models (priced from fal's list and Kie's real charges, Sept 2026)
    "vidu-turbo": {"label": "Vidu Q3 Turbo", "kind": "video", "fal": "fal-ai/vidu/q3/image-to-video/turbo"},
    "pixverse": {"label": "PixVerse 5.5", "kind": "video", "fal": "fal-ai/pixverse/v5.5/image-to-video", "kie": "pixverse/image-to-video"},
    "wan-turbo": {"label": "Wan 2.2 Turbo", "kind": "video", "fal": "fal-ai/wan/v2.2-a14b/image-to-video/turbo",
                  "kie": "wan/2-2-a14b-image-to-video-turbo"},
    "hailuo-fast": {"label": "Hailuo 02 Fast", "kind": "video", "fal": "fal-ai/minimax/hailuo-02-fast/image-to-video",
                    "kie": "hailuo/02-image-to-video-standard"},
    "flux-klein": {"label": "FLUX.2 Klein", "kind": "image", "fal": "fal-ai/flux-2/klein/4b/edit"},
    "seedream-flash": {"label": "Seedream 5 Flash", "kind": "image", "fal": "bytedance/seedream/v5/flash/edit"},
    "seedream": {"label": "Seedream 4.5", "kind": "image", "fal": "fal-ai/bytedance/seedream/v4.5/edit", "kie": "seedream/4-5-edit"},
    "qwen-edit": {"label": "Qwen Image Edit", "kind": "image", "fal": "fal-ai/qwen-image-edit-2511", "kie": "qwen2/image-edit"},
    "nano-banana": {"label": "Nano Banana", "kind": "image", "fal": "fal-ai/nano-banana/edit", "kie": "google/nano-banana-edit",
                    "google": "gemini-nano-banana-2.1"},
}
ALIASES = {
    "seedance": "seedance", "bytedance": "seedance", "kling": "kling", "veo": "veo", "google veo": "veo",
    "hailuo": "hailuo", "minimax": "hailuo", "wan": "wan", "ltx": "ltx", "lightricks": "ltx",
    "gpt image": "gpt-image", "gpt-image": "gpt-image", "openai image": "gpt-image", "flare": "gpt-image",
    "sunburst": "gpt-image-sunburst", "gpt image sunburst": "gpt-image-sunburst",
    "nano banana": "nano-banana", "nanobanana": "nano-banana", "gemini image": "nano-banana",
    "vidu": "vidu-turbo", "pixverse": "pixverse", "wan turbo": "wan-turbo", "wan 2.2": "wan-turbo", "hailuo fast": "hailuo-fast",
    "flux": "flux-klein", "klein": "flux-klein", "seedream flash": "seedream-flash", "seedream": "seedream", "qwen": "qwen-edit",
}
# Real end-to-end renders (not mocks). Update only after a live test.
VERIFIED = {  # where the real render happened
    ("fal", "fal-ai/kling-video/v3/turbo/pro/image-to-video"): "QA render, shot S04-02",
    ("fal", "fal-ai/veo3.1/fast/image-to-video"): "QA render, shot S04-02",
    ("fal", "alibaba/wan-3.0/image-to-video"): "QA render, shot S04-02",
    ("fal", "fal-ai/minimax/hailuo-2.3/standard/image-to-video"): "QA render, shot S04-02",
    ("fal", "fal-ai/nano-banana/edit"): "Exit Plan keyframes",
    ("fal", "fal-ai/nano-banana-pro/edit"): "Exit Plan keyframes",
    ("fal", "bytedance/seedance-2.0/reference-to-video"): "Exit Plan takes",
    ("fal", "fal-ai/sync-lipsync/v3"): "Exit Plan lip-sync pass",
    ("kie", "bytedance/seedance-2"): "Exit Plan takes",
    ("kie", "hailuo/2-3-image-to-video-standard"): "QA render, shot S04-02",
    ("kie", "google/nano-banana-edit"): "QA render, shot S04-02",
    ("kie", "kling-2.6/image-to-video"): "QA render, shot S04-02",
    ("openai", "gpt-image-2.5-flare"): "QA keyframe, shot S05-01",
    ("fal", "openai/gpt-image-2.5/flare/edit"): "QA keyframe, shot S05-01",
    ("kie", "gpt/gpt-image-2-5-flare-image-to-image"): "QA keyframe, shot S05-01",
    ("kie", "wan/3-0-video"): "Exit Plan takes",
    # budget models, one real test render each on Exit Plan S04-02 (30 Sep 2026)
    ("fal", "fal-ai/flux-2/klein/4b/edit"): "model test S04-02",
    ("fal", "bytedance/seedream/v5/flash/edit"): "model test S04-02",
    ("kie", "seedream/4-5-edit"): "model test S04-02 (6.5 credits)",
    ("fal", "fal-ai/qwen-image-edit-2511"): "model test S04-02",
    ("fal", "fal-ai/vidu/q3/image-to-video/turbo"): "model test S04-02",
    ("fal", "fal-ai/wan/v2.2-a14b/image-to-video/turbo"): "model test S04-02",
    ("fal", "fal-ai/minimax/hailuo-02-fast/image-to-video"): "model test S04-02",
    ("kie", "hailuo/02-image-to-video-standard"): "model test S04-02 (30 credits)",
    ("kie", "qwen2/image-edit"): "model test S04-02 (5.6 credits)",
    ("kie", "pixverse/image-to-video"): "model test S04-02 (28.8 credits)",
}
PROVIDER_ORDER = ["fal", "kie", "google", "openai", "comfyui"]
PROVIDER_NAMES = {"fal": "fal.ai", "kie": "Kie.ai", "google": "Google", "openai": "OpenAI", "comfyui": "ComfyUI"}
KEY_ENV = {"fal": "FAL_KEY", "kie": "KIE_KEY", "google": "GEMINI_API_KEY", "openai": "FILMCRAFTER_OPENAI_KEY"}


def available(provider: str) -> bool:
    if provider == "comfyui":
        from . import comfy
        return comfy.reachable()
    return bool(os.environ.get(KEY_ENV.get(provider, "")))


def find_family(text: str) -> str | None:
    t = text.lower()
    for alias in sorted(ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", t):
            return ALIASES[alias]
    return None


def find_provider(text: str) -> str | None:
    t = text.lower()
    for p, words in {"fal": ["fal"], "kie": ["kie"], "google": ["google", "gemini api"], "openai": ["openai directly", "on openai", "with openai"], "comfyui": ["comfy", "comfyui", "local", "locally", "my gpu", "my machine"]}.items():
        if any(re.search(rf"\b{w}\b", t) for w in words):
            return p
    return None


def route(family: str | None, provider: str | None = None, kind: str = "video") -> dict:
    """-> {provider, model, label, verified} or raise SystemExit with what to do."""
    from . import render
    if provider == "comfyui":
        from . import comfy
        flows = comfy.workflows()
        if not flows:
            raise SystemExit("No ComfyUI workflows yet. Add one in Settings → ComfyUI.")
        return {"provider": "comfyui", "model": flows[0]["model"], "label": flows[0]["title"], "verified": None}
    if family is None:
        auto = render.AUTO_IMAGE if kind == "image" else render.AUTO
        order = [provider] if provider else PROVIDER_ORDER
        for p in order:
            if p in auto and available(p):
                return {"provider": p, "model": auto[p], "label": "Auto", "verified": VERIFIED.get((p, auto[p]))}
        raise SystemExit("Add a fal.ai or Kie.ai key in Settings to render.")
    fam = FAMILIES[family]
    carriers = [p for p in PROVIDER_ORDER if p in fam]
    if provider:
        if provider not in fam:
            raise SystemExit(f"{fam['label']} isn't available on {PROVIDER_NAMES[provider]}. "
                             f"Try: {', '.join(PROVIDER_NAMES[p] for p in carriers)}.")
        carriers = [provider]
    for p in carriers:
        if available(p):
            return {"provider": p, "model": fam[p], "label": fam["label"], "verified": VERIFIED.get((p, fam[p]))}
    raise SystemExit(f"{fam['label']} needs a {' or '.join(PROVIDER_NAMES[p] for p in carriers)} key in Settings.")


def equivalent(provider: str, model: str, kind: str = "video", to: str | None = None) -> dict | None:
    """The same model family on another provider (for the budget guard's fallback), else that provider's Auto."""
    from . import render
    fam = next((f for f in FAMILIES.values() if f.get(provider) == model), None)
    order = [to] if to else [p for p in PROVIDER_ORDER if p not in (provider, "comfyui")]
    for p in order:
        if not available(p):
            continue
        if fam and fam.get(p):
            return {"provider": p, "model": fam[p], "label": fam["label"], "same_family": True}
        auto = {"image": render.AUTO_IMAGE, "lipsync": render.AUTO_LIPSYNC}.get(kind, render.AUTO)
        if auto.get(p):
            return {"provider": p, "model": auto[p], "label": "Auto", "same_family": False}
    return None


def status() -> list[dict]:
    """Provider overview for Settings: connected?, families carried, verified models."""
    out = []
    for p in PROVIDER_ORDER:
        out.append({"provider": p, "name": PROVIDER_NAMES[p], "connected": available(p),
                    "families": [f["label"] for f in FAMILIES.values() if p in f],
                    "verified": sorted(m for (pp, m) in VERIFIED if pp == p)})
    return out


def main(argv) -> int:
    import json
    import sys
    from . import comfy
    try:
        action = argv[0] if argv else "status"
        data = json.loads(argv[1]) if len(argv) > 1 else {}
        if action == "status":
            res = {"providers": status(), "comfyui": comfy.check()}
        elif action == "comfy_config":
            comfy.set_config(data.get("url"), data.get("max_side"), data.get("fps"))
            res = comfy.check()
        elif action == "comfy_add":
            comfy.add_workflow(data["path"], data.get("name"))
            res = comfy.check()
        elif action == "comfy_remove":
            comfy.remove_workflow(data["model"])
            res = comfy.check()
        else:
            raise SystemExit("Unknown action.")
        print(json.dumps({"event": "result", "data": res}), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
    except Exception as e:
        print(json.dumps({"event": "error", "message": f"{type(e).__name__}: {e}"}), flush=True)
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
