"""Nano Banana 2.1 (released 2026-10-06): the Google default, the lists, and which of its endpoints can see your pictures."""
from filmcrafter_engine import modelinfo as M
from filmcrafter_engine import render as R
from filmcrafter_engine import router


def test_google_makes_pictures_with_nano_banana_2_1_by_default_and_lists_it_first():
    assert R.AUTO_IMAGE["google"] == "gemini-nano-banana-2.1"
    assert router.FAMILIES["nano-banana"]["google"] == "gemini-nano-banana-2.1"
    names = [m["model"] for m in R._catalog("google", "image")]
    assert names[0] == "gemini-nano-banana-2.1"
    assert "gemini-3.1-flash-image" in names          # still listed until Google retires it on 2026-10-29


def test_its_manifest_offers_4k_and_the_extreme_shapes_the_older_model_lacks():
    man = R.google_manifest("gemini-nano-banana-2.1")
    fields = {f["name"]: f for f in man["inputs"]}
    assert man["title"] == "Nano Banana 2.1"
    assert fields["image_size"]["enum"] == ["1K", "2K", "4K"]
    assert {"1:4", "4:1", "1:8", "8:1", "21:9"} <= set(fields["aspect_ratio"]["enum"])
    assert fields["image_urls"]["max_items"] == 14
    assert "1:8" not in R.google_manifest("gemini-3.1-flash-image")["inputs"][2]["enum"]


def test_the_editing_endpoints_see_your_pictures_and_the_text_only_ones_do_not():
    assert M.sees_pictures("nano-banana-2-1", "image")                 # Kie's real id (read from its doc)
    assert M.sees_pictures("google/nano-banana-2.1/edit", "image")     # fal edit
    assert M.sees_pictures("gemini-nano-banana-2.1", "image")          # Google
    assert not M.sees_pictures("google/nano-banana-2.1", "image")      # fal text-to-image
