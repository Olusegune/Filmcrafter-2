"""What the model pickers say about each Kie model, and two parsing bugs that the real-schema audit found: the Nano Banana family's `image_input` (references never sent) and a doc whose
description holds a code fence (Kling 3.0 looked unreadable)."""
import json
import os

import pytest

from filmcrafter_engine import modelinfo as M
from filmcrafter_engine import render as R


# ---------------------------------------------------------------- the two real bugs
def test_nano_banana_2_1_pro_and_2_get_your_reference_pictures_through_image_input():
    fields = [{"name": "prompt", "type": "string", "required": True}, {"name": "image_input", "type": "array", "items": "string", "max_items": 10},
              {"name": "aspect_ratio", "type": "string"}, {"name": "resolution", "type": "string"}, {"name": "output_format", "type": "string"}]
    fields = [{"enum": None, "default": None, "minimum": None, "maximum": None, "max_length": None, "description": "", "items": None, "max_items": None, **f} for f in fields]
    man = R._finish("kie", "google/nanobanana-2-1", "Google - Nano Banana 2.1", "", fields)
    assert man["roles"]["ref_images"] == "image_input"
    p = R.compile_request({"id": "S1", "start": 0, "end": 4, "performers": ["Sege"], "beats": ["He looks up."]}, None, {"meta": {}}, {"look": {"style": "feature-3d"}}, man,
                          [{"label": "reference for Sege", "url": "https://x/sege.png"}, {"label": "the set", "url": "https://x/set.png"}])
    assert p["image_input"] == ["https://x/sege.png", "https://x/set.png"]                    # before the fix: no pictures at all, and the model drew from words alone


def test_a_doc_with_a_code_fence_inside_its_description_is_read_in_full():
    md = """# Kling 3.0

## OpenAPI Specification

```yaml
openapi: 3.0.1
paths:
  /api/v1/jobs/createTask:
    post:
      description: >-
        Example request:

        ```json
        {"model": "kling-3.0/video"}
        ```

        More text after the example.
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                model:
                  type: string
                  enum: [kling-3.0/video]
                input:
                  type: object
                  properties:
                    prompt: {type: string}
```

## Notes
"""
    blocks = R.yaml_blocks(md)
    assert len(blocks) == 1 and "requestBody" in blocks[0] and "prompt: {type: string}" in blocks[0]
    import yaml
    assert yaml.safe_load(blocks[0])["paths"]["/api/v1/jobs/createTask"]["post"]["requestBody"]


def test_ordinary_docs_and_several_blocks_still_work():
    md = "```yaml\na: 1\n```\ntext\n```yaml\nb: 2\n```\n```json\n{}\n```\n"
    assert R.yaml_blocks(md) == ["a: 1\n", "b: 2\n"]
    assert R.yaml_blocks("no code here") == []


# ---------------------------------------------------------------- can the model see my pictures?
@pytest.mark.parametrize("slug,kind,sees", [
    ("google/nanobanana-2-1", "image", True), ("google/nanobanana2", "image", True), ("google/pro-image-to-image", "image", True), ("google/nano-banana-edit", "image", True),
    ("google/nano-banana", "image", False), ("google/imagen4", "image", False), ("seedream/5-pro-text-to-image", "image", False), ("seedream/5-pro-image-to-image", "image", True),
    ("gpt/gpt-image-2-5-flare-text-to-image", "image", False), ("gpt/gpt-image-2-5-flare-image-to-image", "image", True), ("flux2/pro-text-to-image", "image", False),
    ("flux2/pro-image-to-image", "image", True), ("ideogram/v3-edit", "image", True), ("ideogram/v3-text-to-image", "image", False), ("qwen3/text-to-image", "image", False),
    ("qwen3/image-to-image", "image", True), ("z-image/z-image", "image", False), ("wan/2-7-image", "image", True),
    ("kling/kling-3-0", "video", True), ("kling/text-to-video", "video", False), ("bytedance/seedance-2", "video", True), ("minimax-h3/text-to-video", "video", False)])
def test_which_models_can_see_your_pictures(slug, kind, sees):
    assert M.sees_pictures(slug, kind) is sees


def test_which_models_are_good_at_clean_text():
    for yes in ("ideogram/v3-text-to-image", "gpt/gpt-image-2-5-flare-image-to-image", "google/nanobanana-2-1", "qwen3/image-to-image", "seedream/5-pro-image-to-image"):
        assert M.good_at_text(yes), yes
    for no in ("google/imagen4-fast", "z-image/z-image", "seedream/seedream"):
        assert not M.good_at_text(no), no


@pytest.mark.parametrize("slug,tool", [("topaz/image-upscale", True), ("recraft/crisp-upscale", True), ("recraft/remove-background", True), ("grok-imagine-image-2-0/segment-map", True),
                                       ("grok-imagine-image-2-0/image-edit", True), ("seedream/5-pro-layer-decomposition", True),
                                       ("qwen/image-edit", False), ("google/nanobanana-2-1", False), ("grok-imagine-image-2-0/image-to-image", False), ("ideogram/v3-edit", False)])
def test_tools_are_told_apart_from_picture_generators(slug, tool):
    assert M.is_image_tool(slug) is tool


# ---------------------------------------------------------------- ordering and "new"
def item(model, title="X"):
    return {"provider": "kie", "model": model, "title": title, "category": "image"}


def test_recommended_models_come_first_in_their_own_order_then_models_that_can_see_pictures_then_the_rest(tmp_path):
    items = [item("qwen3/text-to-image", "B text only"), item("flux2/flex-image-to-image", "C sees"), item("google/nano-banana-edit", "Edit"), item("google/nanobanana-2-1", "NB 2.1"), item("ideogram/v3-text-to-image", "A text only")]
    out = M.decorate(items, "kie", "image", str(tmp_path))
    assert [i["model"] for i in out] == ["google/nanobanana-2-1", "google/nano-banana-edit", "flux2/flex-image-to-image", "ideogram/v3-text-to-image", "qwen3/text-to-image"]
    assert out[0]["rec"] == 0 and out[1]["rec"] == 5 and out[2]["rec"] is None and out[2]["sees"] is True and out[3]["sees"] is False


def test_the_first_time_a_list_is_seen_nothing_is_new_and_a_model_added_later_is(tmp_path):
    first = M.decorate([item("a/one"), item("a/two")], "kie", "image", str(tmp_path))
    assert not any(i["fresh"] for i in first)
    later = M.decorate([item("a/one"), item("a/two"), item("a/three")], "kie", "image", str(tmp_path))
    assert {i["model"]: i["fresh"] for i in later} == {"a/one": False, "a/two": False, "a/three": True}


def test_a_new_model_stops_being_new_after_two_weeks_and_lists_are_kept_apart(tmp_path):
    d = str(tmp_path)
    M.decorate([item("a/one")], "kie", "image", d)
    M.mark_fresh([item("a/one"), item("a/new")], "kie", "image", d, now=1000.0)
    assert M.mark_fresh([item("a/one"), item("a/new")], "kie", "image", d, now=1000.0 + 13 * 86400)[1]["fresh"] is True
    assert M.mark_fresh([item("a/one"), item("a/new")], "kie", "image", d, now=1000.0 + 15 * 86400)[1]["fresh"] is False
    assert M.mark_fresh([item("b/video")], "kie", "video", d, now=2000.0)[0]["fresh"] is False          # another list's first sight


def test_a_damaged_seen_file_is_started_again_not_fatal(tmp_path):
    open(os.path.join(str(tmp_path), "models_seen.json"), "w").write("{ not json")
    assert M.mark_fresh([item("a/one")], "kie", "image", str(tmp_path))[0]["fresh"] is False


def test_other_providers_pass_through_with_nothing_claimed(tmp_path):
    out = M.decorate([{"provider": "fal", "model": "fal-ai/x", "title": "X", "category": "image"}], "fal", "image", str(tmp_path))
    assert out[0]["sees"] is True and out[0]["text"] is False and out[0]["rec"] is None


# ---------------------------------------------------------------- the catalog
def test_the_kie_picture_list_has_no_tools_and_the_upscale_list_has_only_upscalers(tmp_path, monkeypatch):
    index = [{"kind": "image", "family": "Topaz", "title": "Topaz - Image Upscale", "doc": "https://docs.kie.ai/market/topaz/image-upscale.md"},
             {"kind": "image", "family": "Google", "title": "Google - Nano Banana 2.1", "doc": "https://docs.kie.ai/market/google/nanobanana-2-1.md"},
             {"kind": "image", "family": "Recraft", "title": "Recraft - Remove Background", "doc": "https://docs.kie.ai/market/recraft/remove-background.md"},
             {"kind": "video", "family": "Topaz", "title": "Topaz - Video Upscale", "doc": "https://docs.kie.ai/market/topaz/video-upscale.md"},
             {"kind": "video", "family": "Kling", "title": "Kling 3.0", "doc": "https://docs.kie.ai/market/kling/kling-3-0.md"}]
    monkeypatch.setattr(R, "_kie_index", lambda: index)
    monkeypatch.setattr(R, "CACHE_DIR", str(tmp_path))
    imgs = [m["model"] for m in R.catalog("kie", "image", refresh=True)]
    assert imgs == ["google/nanobanana-2-1", "midjourney/mj-v7"]        # Midjourney is added to Kie's picture models (render.py)
    ups = sorted(m["model"] for m in R.catalog("kie", "upscale", refresh=True))
    assert ups == ["topaz/image-upscale", "topaz/video-upscale"]
    vids = [m["model"] for m in R.catalog("kie", "video", refresh=True)]
    assert vids == ["kling/kling-3-0"]                                                          # the upscaler is not offered as a video generator


def test_an_older_saved_picture_list_that_still_holds_tools_is_cleaned(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "CACHE_DIR", str(tmp_path))
    json.dump([item("topaz/image-upscale"), item("google/nanobanana-2-1")], open(os.path.join(str(tmp_path), "catalog__kie__image.json"), "w"))
    assert [m["model"] for m in R.catalog("kie", "image")] == ["google/nanobanana-2-1", "midjourney/mj-v7"]


# the 25 picture models on Kie that the real-schema audit found cannot take reference pictures (run: python -m filmcrafter_engine.model_audit kie --kind image)
AUDITED_TEXT_ONLY = ["flux2/pro-text-to-image", "flux2/flex-text-to-image", "gpt/gpt-image-2-5-flare-text-to-image", "gpt/gpt-image-2-5-sunburst-text-to-image", "gpt-image/1-5-text-to-image",
                     "gpt/gpt-image-2-text-to-image", "google/nano-banana", "google/imagen4", "google/imagen4-fast", "google/imagen4-ultra", "grok-imagine/text-to-image",
                     "grok-imagine-image-2-0/text-to-image", "ideogram/v3-text-to-image", "qwen/text-to-image", "qwen2-1/text-to-image", "qwen2/text-to-image", "qwen3-pro/text-to-image",
                     "qwen3/text-to-image", "seedream/seedream", "seedream/seedream-v4-text-to-image", "seedream/4-5-text-to-image", "seedream/5-flash-text-to-image",
                     "seedream/5-lite-text-to-image", "seedream/5-pro-text-to-image", "z-image/z-image"]
AUDITED_SEES = ["google/nanobanana2", "google/nanobanana-2-1", "google/pro-image-to-image", "google/nano-banana-edit", "google/nano-banana-2-lite", "flux2/pro-image-to-image", "flux2/flex-image-to-image",
                "gpt/gpt-image-2-5-flare-image-to-image", "gpt/gpt-image-2-5-sunburst-image-to-image", "gpt-image/1-5-image-to-image", "gpt/gpt-image-2-image-to-image", "ideogram/v3-edit",
                "ideogram/v3-remix", "ideogram/character", "ideogram/character-edit", "ideogram/character-remix", "qwen/image-to-image", "qwen/image-edit", "qwen2/image-edit", "qwen2-1/image-to-image",
                "qwen3/image-to-image", "qwen3-pro/image-to-image", "seedream/seedream-v4-edit", "seedream/4-5-edit", "seedream-5-lite-image-to-image", "seedream/5-pro-image-to-image",
                "seedream/5-flash-image-to-image", "grok-imagine-image-2-0/image-to-image", "grok-imagine/image-to-image", "wan/2-7-image", "wan/2-7-image-pro"]


@pytest.mark.parametrize("slug", AUDITED_TEXT_ONLY)
def test_every_model_the_audit_found_text_only_is_marked_so(slug):
    assert M.sees_pictures(slug) is False, slug


@pytest.mark.parametrize("slug", AUDITED_SEES)
def test_every_model_the_audit_found_able_to_see_pictures_is_marked_so(slug):
    assert M.sees_pictures(slug) is True, slug
