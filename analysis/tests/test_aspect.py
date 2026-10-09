"""A 21:9 (or 2.39:1) project gets 21:9 keyframes: exact sizes for GPT Image 2/2.5, a trim for models that can't, and the right export preset."""
import io
import json
import os

import pytest
from PIL import Image

from pulseframe_analysis import render as R

ASPECTS = ["2.39:1", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "4:5", "3:2"]


def _png(w, h, fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 80, 40)).save(buf, format=fmt)
    return buf.getvalue()


# ---------------------------------------------------------------- exact sizes for the flexible models

@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("quality", ["draft", "standard", "high", "max"])
def test_every_size_asked_of_a_flexible_model_is_one_the_model_accepts(aspect, quality):
    w, h = (int(x) for x in R.flex_size(aspect, quality).split("x"))
    assert w % 16 == 0 and h % 16 == 0 and max(w, h) <= 3840 and 655_360 <= w * h <= 8_294_400 and max(w, h) / min(w, h) <= 3.0
    assert abs(w / h - R.ratio_of(aspect)) / R.ratio_of(aspect) < 0.03                              # and it is the shape that was asked for


def test_the_wide_projects_get_wide_sizes_not_three_two():
    assert R.flex_size("21:9", "standard") == "1536x656" and R.flex_size("2.39:1", "high") == "1920x800" and R.flex_size("9:16", "standard").endswith("x1536")
    assert R.flex_size("21:9", "standard") != "1536x1024"
    assert R.flex_size("5:1", "standard").split("x") == ["1536", "512"]                              # never wider than the 3:1 the model allows
    assert R.flex_size("garbage", "unknown") == R.flex_size("16:9", "standard")                       # unreadable input falls back to 16:9


def test_only_the_newer_models_take_any_size():
    for m in ("gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst"):
        f = {x["name"]: x for x in R.openai_manifest(m)["inputs"]}["size"]
        assert f.get("flex") and not f.get("enum")
    old = {x["name"]: x for x in R.openai_manifest("gpt-image-1.5")["inputs"]}["size"]
    assert not old.get("flex") and old["enum"] == ["1536x1024", "1024x1024", "1024x1536", "auto"]


@pytest.mark.parametrize("model,aspect,quality,expect", [
    ("gpt-image-2.5-flare", "21:9", "standard", "1536x656"), ("gpt-image-2.5-flare", "2.39:1", "high", "1920x800"),
    ("gpt-image-2", "9:16", "draft", "720x1280"), ("gpt-image-1.5", "21:9", "standard", "1536x1024")])
def test_the_request_asks_for_the_projects_shape(model, aspect, quality, expect):
    p = R.compile_request({"id": "S", "start": 0, "end": 4, "beats": ["x"]}, None, {"meta": {}}, {"look": {"style": "auto"}, "aspect_ratio": aspect, "quality": quality},
                          R.openai_manifest(model), [])
    assert p["size"] == expect


# ---------------------------------------------------------------- trimming what a model made in another shape

def test_a_picture_in_the_wrong_shape_is_trimmed_to_the_project_and_the_original_kept(tmp_path):
    path = str(tmp_path / "k.png")
    open(path, "wb").write(_png(1536, 1024))
    assert R.fit_to_aspect(path, "2.39:1") is True
    with Image.open(path) as im:
        assert im.size[0] == 1536 and abs(im.size[0] / im.size[1] - 2.39) < 0.01
    with Image.open(str(tmp_path / "k.uncropped.png")) as im:
        assert im.size == (1536, 1024)                                                                 # nothing is thrown away
    tall = str(tmp_path / "t.png")
    open(tall, "wb").write(_png(1024, 1536))
    assert R.fit_to_aspect(tall, "16:9") is True
    with Image.open(tall) as im:
        assert im.size[0] == 1024 and abs(im.size[0] / im.size[1] - 16 / 9) < 0.01


def test_a_picture_already_the_right_shape_or_unreadable_is_left_alone(tmp_path):
    ok = str(tmp_path / "ok.png")
    open(ok, "wb").write(_png(1920, 804))
    before = open(ok, "rb").read()
    assert R.fit_to_aspect(ok, "2.39:1") is False and open(ok, "rb").read() == before and not os.path.exists(str(tmp_path / "ok.uncropped.png"))
    assert R.fit_to_aspect(ok, "16:9") is True                                                         # but 2.39 is not 16:9
    bad = str(tmp_path / "bad.png")
    open(bad, "wb").write(b"not a picture")
    assert R.fit_to_aspect(bad, "21:9") is False and open(bad, "rb").read() == b"not a picture"
    assert R.fit_to_aspect(str(tmp_path / "missing.png"), "21:9") is False and R.fit_to_aspect(ok, None) is False and R.fit_to_aspect(ok, "nonsense") is False
    jpg = str(tmp_path / "j.jpg")
    open(jpg, "wb").write(_png(1600, 1000, "JPEG"))
    assert R.fit_to_aspect(jpg, "21:9") is True and Image.open(jpg).format == "JPEG"


# ---------------------------------------------------------------- the whole job

class Fake:
    name = "fal"

    def upload(self, path):
        return "https://cdn/" + os.path.basename(path)

    def submit(self, model, payload):
        return {"id": "r1"}

    def poll(self, model, rid, meta=None):
        return {"state": "done", "url": "https://cdn/k.png"}


def test_a_finished_keyframe_job_is_fitted_to_a_cinema_project(tmp_path, monkeypatch):
    d = tmp_path / "p"
    d.mkdir()
    shot = {"id": "S01-01", "scene": 1, "number": 1, "start": 0.0, "end": 2.0, "beats": ["A man waits."], "performers": [], "framing": "wide", "camera_moves": [], "source_shots": ["S01-01"]}
    json.dump({"meta": {}, "characters": [], "scenes": [{"number": 1, "heading": "EXT.", "start": 0, "end": 2, "notes": {}, "shots": [shot]}]}, open(d / "production.json", "w"))
    json.dump({"title": "T", "song": "song.wav", "aspect_ratio": "21:9"}, open(d / "project.json", "w"))
    json.dump({"duration": 2.0, "lyrics": [], "sections": [], "beats": []}, open(d / "songmap.json", "w"))
    monkeypatch.setitem(R.PROVIDERS, "fal", Fake)
    m = R._finish("fal", "test/img", "Img", "", [{"name": "prompt", "type": "string", "description": "", "required": True, "enum": None, "default": None, "items": None,
                                                   "minimum": None, "maximum": None, "max_items": None, "max_length": None}])
    monkeypatch.setattr(R, "manifest", lambda provider, model, refresh=False: m)
    monkeypatch.setattr("pulseframe_analysis.stills.after_still", lambda *a, **k: None)

    class Dl:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_content(self, n): yield _png(1536, 1024)
    monkeypatch.setattr(R.requests, "get", lambda url, **kw: Dl())
    R.enqueue(str(d), ["S01-01"], "fal", "test/img", {}, kind="image")
    R.run(str(d), poll_every=0)
    j = R.Store(str(d)).jobs[0]
    assert j["state"] == "ready" and j["kind"] == "image"
    with Image.open(os.path.join(str(d), j["output"])) as im:
        assert abs(im.size[0] / im.size[1] - 21 / 9) < 0.02                                             # the keyframe is the shape that was chosen
    assert any(f.endswith(".uncropped.png") for f in os.listdir(d / "generations"))


# ---------------------------------------------------------------- the export that follows

def test_a_21_9_project_exports_as_cinema_by_default():
    from pulseframe_analysis import export
    for ratio, preset in (("21:9", "cinema"), ("2.39:1", "cinema"), ("16:9", "youtube"), ("9:16", "vertical"), ("1:1", "square"), ("4:3", "youtube"), (None, "youtube")):
        assert export.preset_for(ratio) == preset
    assert export.preset_for("21:9") in export.PRESETS
