"""The size of a picture a model is asked for: High and Max ask for the largest size the model offers (2K for Seedream 5 Pro, 4K for Seedream 4.5), Draft and Standard keep the basic
size, and a price learned at one size is never shown for another. Provider settings used here are the ones their published schemas list (read 2026-10-30), not a real render."""
import json
import os

import pytest

from filmcrafter_engine import modelinfo as MI
from filmcrafter_engine import render as R
from filmcrafter_engine import routing as RT


def field(name, type="string", **kw):
    return {"name": name, "type": type, "items": kw.get("items"), "enum": kw.get("enum"), "default": kw.get("default"), "minimum": None, "maximum": None, "max_items": None,
            "max_length": None, "description": "", "required": kw.get("required", False)}


def kie_seedream(model="seedream/4-5-edit"):
    return R._finish("kie", model, "Seedream", "image-to-image", [field("prompt", required=True), field("image_urls", "array", items="string"),
                                                                    field("aspect_ratio", enum=["1:1", "16:9", "9:16"], required=True), field("quality", enum=["basic", "high"], required=True)])


def fal_seedream(top="auto_2K"):
    enum = ["square_hd", "square", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9", "auto_1K", "auto_1.5K", "auto_2K"] + (["auto_4K"] if top == "auto_4K" else [])
    return R._finish("fal", "bytedance/seedream/v5/pro/edit", "Seedream 5 Pro", "image-to-image", [field("prompt", required=True), field("image_urls", "array", items="string"),
                                                                                                   field("image_size", "object", enum=enum, default="auto_2K")])


def project(quality, aspect="16:9"):
    return {"look": {"style": "auto"}, "quality": quality, "aspect_ratio": aspect}


def req(man, quality, aspect="16:9", **kw):
    shot = {"id": "S01-01", "start": 0.0, "end": 2.0, "beats": ["A woman waits."], "performers": [], "framing": "wide", "camera_moves": [], "source_shots": ["S01-01"]}
    return R.compile_request(shot, None, {"meta": {}}, project(quality, aspect), man, [], kw.get("overrides"))


# ---------------------------------------------------------------- resolution words: 1K, 2K, 4K

@pytest.mark.regression
def test_a_model_that_names_its_sizes_in_k_gets_the_small_one_for_a_draft():
    """Nano Banana Pro on Kie (1K, 2K, 4K) was asked for 4K at every tier, a draft included."""
    f = field("resolution", enum=["1K", "2K", "4K"], default="1K")
    assert {t: R._pick_quality(f, t) for t in ("draft", "standard", "high", "max")} == {"draft": "1K", "standard": "1K", "high": "4K", "max": "4K"}
    f2 = field("resolution", enum=["1K", "2K"], default="1K")
    assert [R._pick_quality(f2, t) for t in ("draft", "standard", "high", "max")] == ["1K", "1K", "2K", "2K"]


def test_video_resolutions_are_chosen_as_before():
    f = field("resolution", enum=["720p", "1080p", "4k"], default="720p")
    assert [R._pick_quality(f, t) for t in ("draft", "standard", "high", "max")] == ["720p", "720p", "1080p", "4k"]


def test_k_words_are_read():
    assert (R._k("4K"), R._k("auto_1.5K"), R._k("2k"), R._k("1080p"), R._k("landscape_16_9"), R._k(None)) == (4.0, 1.5, 2.0, None, None, None)


# ---------------------------------------------------------------- Kie: basic or high

def test_kie_seedream_asks_for_high_only_at_high_and_max():
    man = kie_seedream()
    for tier, want, key in (("draft", "basic", ""), ("standard", "basic", ""), ("high", "high", "quality=high"), ("max", "high", "quality=high")):
        assert req(man, tier)["quality"] == want, tier
        assert R.picture_size_plan(man, project(tier))["key"] == key, tier


def test_a_pin_from_director_mode_still_wins():
    assert req(kie_seedream(), "max", overrides={"quality": "basic"})["quality"] == "basic"


def test_other_quality_words_are_left_alone():
    gpt = R._finish("kie", "gpt/x", "GPT", "image-to-image", [field("prompt", required=True), field("quality", enum=["low", "medium", "high", "auto"], default="high")])
    assert R.picture_size_plan(gpt, project("max")) == {"payload": {}, "key": ""}


# ---------------------------------------------------------------- fal: an exact width and height

def test_fal_seedream_5_pro_gets_2k_in_the_films_shape_and_4_5_gets_4k():
    assert req(fal_seedream(), "max")["image_size"] == {"width": 2048, "height": 1152}
    assert req(fal_seedream(), "high", aspect="9:16")["image_size"] == {"width": 1152, "height": 2048}
    assert req(fal_seedream("auto_4K"), "max")["image_size"] == {"width": 4096, "height": 2304}
    assert R.picture_size_plan(fal_seedream(), project("max"))["key"] == "size=2K" and R.picture_size_plan(fal_seedream("auto_4K"), project("max"))["key"] == "size=4K"


def test_fal_stays_at_its_basic_preset_at_draft_and_standard():
    for tier in ("draft", "standard"):
        assert req(fal_seedream(), tier)["image_size"] == "landscape_16_9"
        assert R.picture_size_plan(fal_seedream(), project(tier))["key"] == ""


def test_the_size_stays_inside_what_fal_accepts():
    """5 Pro: at most 4,624,220 pixels in all; 4.5: each side 1920 to 4096 or 2560x1440 to 4096x4096 pixels in all (from the published schemas)."""
    for aspect in ("16:9", "21:9", "2.39:1", "1:1", "4:3", "9:16", "3:4"):
        d = req(fal_seedream(), "max", aspect)["image_size"]
        assert 921_600 <= d["width"] * d["height"] <= 4_624_220, (aspect, d)
        d = req(fal_seedream("auto_4K"), "max", aspect)["image_size"]
        assert max(d["width"], d["height"]) <= 4096 and d["width"] * d["height"] >= 921_600, (aspect, d)
    assert R.validate_request(fal_seedream(), req(fal_seedream(), "max")) == []


def test_a_model_with_its_own_aspect_setting_keeps_it_and_gets_no_size_object():
    man = R._finish("fal", "x/y", "Y", "image-to-image", [field("prompt", required=True), field("aspect_ratio", enum=["16:9", "1:1"]), field("image_size", "object", enum=["auto_2K"])])
    assert "image_size" not in R.picture_size_plan(man, project("max"))["payload"]


def test_video_models_are_not_touched():
    vid = R._finish("fal", "v/v", "V", "image-to-video", [field("prompt"), field("duration", enum=["5"]), field("quality", enum=["basic", "high"])])
    assert R.picture_size_plan(vid, project("max")) == {"payload": {}, "key": ""}


# ---------------------------------------------------------------- money: a price is only ever shown for the size it was learned at

@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(R, "KIE_COST_SEED", {"seedream/4-5-edit": 7})
    return tmp_path


def film(tmp_path, quality, jobs=None):
    d = tmp_path / "p"
    d.mkdir(exist_ok=True)
    shot = {"id": "S01-01", "scene": 1, "number": 1, "start": 0.0, "end": 2.0, "beats": ["A woman waits."], "performers": [], "framing": "wide", "camera_moves": [], "source_shots": ["S01-01"]}
    json.dump({"meta": {}, "characters": [], "scenes": [{"number": 1, "heading": "INT.", "start": 0, "end": 2, "notes": {}, "shots": [shot]}]}, open(d / "production.json", "w"))
    json.dump({"title": "T", "song": "s.wav", "look": {"style": "auto"}, "quality": quality, "aspect_ratio": "16:9"}, open(d / "project.json", "w"))
    json.dump({"duration": 2.0, "lyrics": [], "sections": [], "beats": []}, open(d / "songmap.json", "w"))
    json.dump({"jobs": jobs or []}, open(d / "jobs.json", "w"))
    return str(d)


def test_a_bigger_size_is_not_priced_from_the_basic_size(cache, monkeypatch):
    man = kie_seedream()
    monkeypatch.setattr(R, "manifest", lambda provider, model, refresh=False: man)
    basic = R.estimate(film(cache, "standard"), ["S01-01"], "kie", "seedream/4-5-edit", "image")
    assert basic["kie_credits_est"] == 7 and "size_unpriced" not in basic                       # the basic size is priced
    big = R.estimate(film(cache, "max"), ["S01-01"], "kie", "seedream/4-5-edit", "image")
    assert big.get("size_unpriced") is True and "kie_credits_est" not in big and "Not priced yet at this size" in big["basis"]


def test_the_price_of_a_big_picture_is_learned_apart_and_the_basic_price_is_kept(cache, monkeypatch):
    man = kie_seedream()
    monkeypatch.setattr(R, "manifest", lambda provider, model, refresh=False: man)
    R.remember_kie_cost("seedream/4-5-edit", 18, "quality=high")
    mem = R.kie_cost_memory()
    assert mem["seedream/4-5-edit|quality=high"] == 18 and mem["seedream/4-5-edit"] == 7
    big = R.estimate(film(cache, "max"), ["S01-01"], "kie", "seedream/4-5-edit", "image")
    assert big["kie_credits_est"] == 18 and "size_unpriced" not in big
    assert R.estimate(film(cache, "standard"), ["S01-01"], "kie", "seedream/4-5-edit", "image")["kie_credits_est"] == 7


def test_finished_jobs_at_one_size_never_price_another(cache):
    jobs = [{"provider": "kie", "model": "m", "cost": 5}, {"provider": "kie", "model": "m", "cost": 20, "size_key": "quality=high"}, {"provider": "kie", "model": "m", "cost": 9, "size_key": "quality=high"}]
    assert R.kie_credits_for(jobs, "m", "") == 5
    assert R.kie_credits_for(jobs, "m", "quality=high") == 20                                   # the middle of 9 and 20, rounded up
    assert R.kie_credits_for(jobs, "m", "resolution=4K") is None
    assert R.kie_credits_for([], "other", "") is None


def test_each_picture_job_records_its_size(cache, monkeypatch):
    man = kie_seedream()
    monkeypatch.setattr(R, "manifest", lambda provider, model, refresh=False: man)
    for tier, key in (("standard", None), ("max", "quality=high")):
        d = film(cache, tier)
        R.enqueue(d, ["S01-01"], "kie", "seedream/4-5-edit", {}, kind="image")
        job = R.Store(d).jobs[-1]
        assert job.get("size_key") == key
        os.remove(os.path.join(d, "jobs.json"))


def test_queued_big_pictures_count_at_their_own_price_or_a_high_one(cache, monkeypatch, tmp_path):
    d = film(cache, "max", [{"id": "a", "state": "queued", "provider": "kie", "model": "seedream/4-5-edit", "kind": "image", "size_key": "quality=high"},
                            {"id": "b", "state": "queued", "provider": "kie", "model": "seedream/4-5-edit", "kind": "image"}])
    assert RT.pending_usd(d) == round(RT.FALLBACK_BIG_PICTURE_USD + 7 * __import__("filmcrafter_engine.budget", fromlist=["x"]).KIE_USD_PER_CREDIT, 2)


def test_an_unpriced_big_size_raises_the_batch_figure(monkeypatch):
    monkeypatch.setattr("filmcrafter_engine.render.estimate", lambda *a, **k: {"usd": None, "usd_known": 0, "unknown": 2, "size_unpriced": True})
    assert RT.batch_usd("d", ["a", "b"], "kie", "m", "image") == round(2 * RT.FALLBACK_BIG_PICTURE_USD, 2)
    monkeypatch.setattr("filmcrafter_engine.render.estimate", lambda *a, **k: {"usd": None, "usd_known": 0, "unknown": 2})
    assert RT.batch_usd("d", ["a", "b"], "kie", "m", "image") == round(2 * RT.FALLBACK_USD["image"], 2)


def test_fal_is_priced_on_the_pixels_that_will_be_asked_for(monkeypatch):
    monkeypatch.setattr(R, "_fal_price", lambda model: {"unit": "megapixel", "unit_price": 0.01})
    man = fal_seedream()
    big = R.estimate_payload("fal", man["model"], man, {"image_size": {"width": 4096, "height": 2304}})
    small = R.estimate_payload("fal", man["model"], man, {"image_size": "landscape_16_9"})
    assert big["usd"] == round(0.01 * 4096 * 2304 / 1e6, 3) and small["usd"] == round(0.01 * 1.05, 3) and big["usd"] > 8 * small["usd"]


# ---------------------------------------------------------------- the model list

def test_the_largest_size_is_named_only_where_the_providers_publish_it():
    assert [MI.max_size(s) for s in ("seedream/5-pro-image-to-image", "bytedance/seedream/v5/pro/edit", "seedream/4-5-edit", "fal-ai/bytedance/seedream/v4.5/edit")] == ["2K", "2K", "4K", "4K"]
    assert [MI.max_size(s) for s in ("seedream/5-flash-image-to-image", "bytedance/seedream/v5/lite/edit", "google/nanobanana-2-1", "")] == [None, None, None, None]
    assert MI.max_size("seedream/4-5-edit", "video") is None


def test_fal_seedream_5_pro_is_recommended_and_says_how_big_it_goes(tmp_path):
    items = [{"model": "bytedance/seedream/v5/pro/edit", "title": "Seedream 5.0 Pro Image Editing", "category": "image-to-image"},
             {"model": "bytedance/seedream/v5/lite/edit", "title": "Seedream", "category": "image-to-image"}]
    out = {i["model"]: i for i in MI.decorate(items, "fal", "image", str(tmp_path))}
    assert out["bytedance/seedream/v5/pro/edit"]["rec"] == 0 and out["bytedance/seedream/v5/pro/edit"]["max_size"] == "2K"
    assert out["bytedance/seedream/v5/lite/edit"]["rec"] is None and "max_size" not in out["bytedance/seedream/v5/lite/edit"]
    kie = MI.decorate([{"model": "seedream/5-pro-image-to-image", "title": "t", "category": "image"}], "kie", "image", str(tmp_path))[0]
    assert kie["rec"] is not None and kie["max_size"] == "2K"
