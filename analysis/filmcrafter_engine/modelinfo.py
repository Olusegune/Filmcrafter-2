"""What the model pickers say about each Kie model, beyond its name: whether it can SEE your reference pictures, whether it is good at clean text, whether it is recommended or new, and
which entries are tools (upscalers, background removal) rather than generators.

Why "can it see my pictures" matters most: a text-to-image model only reads words. Asked for a keyframe, it cannot see your character sheets, so faces and the whole look drift (a
3D project comes back photographic). The edit / image-to-image / reference variants of the same families can see them. The pickers show it, and put the ones that can first.

Everything here is read from a model's name; `model_audit` (run for real against Kie's published schemas) is what proves a model's inputs, and found that the Nano Banana 2, 2.1 and Pro
models name their reference-picture field `image_input`, which the app did not recognise, so they were being sent no pictures at all (fixed in render.ROLE_NAMES).
"""
from __future__ import annotations

import json
import os
import re
import time

FRESH_DAYS = 14

# entries in the picture list that are tools, not picture generators: they need a picture you already have, or a task id, and do something else to it
IMAGE_TOOLS = re.compile(r"upscale|remove-background|segment-map|grok-imagine-image-2-0/image-edit|layer-decomposition", re.I)
UPSCALE_TOOLS = re.compile(r"upscale", re.I)

# can the model take reference pictures? (names of the edit / image-to-image / remix / character / reference variants, and the Nano Banana family)
SEES = re.compile(r"midjourney|edit|image-to-image|remix|character|nano-?banana(?!$)|pro-image-to-image|reference|wan/2-7-image", re.I)
BLIND = re.compile(r"text-to-image|^google/nano-banana$|imagen4|^z-image/|^seedream/seedream$|flux2/(?:pro|flex)-text", re.I)
# models that draw words well (signs, titles, labels, lyrics on a wall)
TEXT_GOOD = re.compile(r"ideogram|gpt-image|gpt/gpt-image|qwen3|seedream/5-pro|seedream/4-5|nanobanana|nano-banana-2|pro-image-to-image|flux2/pro|wan/2-7-image-pro|recraft", re.I)

RECOMMENDED_IMAGE = ["google/nanobanana-2-1", "google/pro-image-to-image", "gpt/gpt-image-2-5-flare-image-to-image", "seedream/5-pro-image-to-image",
                     "flux2/pro-image-to-image", "google/nano-banana-edit", "ideogram/v3-edit"]
RECOMMENDED_VIDEO = ["kling/kling-3-0", "kling/v3-turbo-image-to-video", "kling/v3-omni-image-to-video", "bytedance/seedance-2", "bytedance/seedance-2-5",
                     "minimax-h3/image-to-video", "wan/3-0-video", "happyhorse-1-1/image-to-video"]
# picture-to-video: a video model that only takes text cannot start from your keyframe either
VIDEO_TEXT_ONLY = re.compile(r"text-to-video|/t2v", re.I)


def sees_pictures(slug: str, kind: str = "image") -> bool:
    """Can this model be given your character sheets / keyframe? Images: the edit-type variants. Video: anything that is not text-to-video."""
    s = slug or ""
    if kind == "video":
        return not VIDEO_TEXT_ONLY.search(s)
    if BLIND.search(s):
        return False
    return bool(SEES.search(s))


def good_at_text(slug: str) -> bool:
    return bool(TEXT_GOOD.search(slug or ""))


def is_image_tool(slug: str) -> bool:
    return bool(IMAGE_TOOLS.search(slug or ""))


def is_upscaler(slug: str) -> bool:
    return bool(UPSCALE_TOOLS.search(slug or ""))


def rank(slug: str, kind: str = "image") -> int | None:
    """Position in the recommended list (0 = first), or None."""
    lst = RECOMMENDED_VIDEO if kind == "video" else RECOMMENDED_IMAGE
    return lst.index(slug) if slug in lst else None


def _seen_path(cache_dir: str) -> str:
    return os.path.join(cache_dir, "models_seen.json")


def mark_fresh(items: list[dict], provider: str, kind: str, cache_dir: str, now: float | None = None) -> list[dict]:
    """Flag models that appeared in the provider's list within the last two weeks. The first time a list is ever seen nothing is new (everything would be): models are remembered with
    the day they were first seen, and only ones added later count."""
    now = time.time() if now is None else now
    key = f"{provider}|{kind}"
    try:
        with open(_seen_path(cache_dir), encoding="utf-8") as f:
            seen = json.load(f)
    except (OSError, ValueError):
        seen = {}
    book = seen.get(key)
    first_time = book is None
    book = dict(book or {})
    changed = False
    for it in items:
        if it["model"] not in book:
            book[it["model"]] = 0 if first_time else now          # 0: known from the start, never "new"
            changed = True
        it["fresh"] = bool(book[it["model"]]) and now - float(book[it["model"]]) < FRESH_DAYS * 86400
    if changed:
        seen[key] = book
        try:
            os.makedirs(cache_dir, exist_ok=True)
            with open(_seen_path(cache_dir), "w", encoding="utf-8") as f:
                json.dump(seen, f)
        except OSError:
            pass
    return items


def decorate(items: list[dict], provider: str, kind: str, cache_dir: str) -> list[dict]:
    """Add `sees` (can take your pictures), `text` (clean text), `rec` (recommended rank or null) and `fresh` to catalog entries, and order the list: recommended first, then models that
    can see pictures, then the rest, each group by name. Entries from other providers pass through with the same fields filled in as far as they can be known."""
    for it in items:
        slug = it["model"]
        it["sees"] = sees_pictures(slug, kind) if provider == "kie" else True
        it["text"] = good_at_text(slug) if provider == "kie" else False
        it["rec"] = rank(slug, kind) if provider == "kie" else None
    mark_fresh(items, provider, kind, cache_dir)
    return sorted(items, key=lambda it: (it["rec"] is None, it["rec"] if it["rec"] is not None else 0, not it["sees"], it.get("title", "")))
