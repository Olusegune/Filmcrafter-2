"""Fix only the bad hand: marking the part, the crop, the model, the request that is sent, laying the fixed part back, and that the original keyframe is never touched."""
import io
import json
import os

import pytest
from PIL import Image

from filmcrafter_engine import handfix as HF, keyframeset as KS, render as R, router, routing as RT, shothistory as H, stills as ST

MODEL = ("kie", "kie/edit-model")
RED, BLUE = (200, 30, 30), (30, 30, 220)


def F(name, type="string", **kw):
    return {"name": name, "type": type, "items": kw.get("items"), "enum": None, "default": None, "minimum": None, "maximum": None, "max_items": kw.get("max_items"), "max_length": None,
            "description": kw.get("description", ""), "required": kw.get("required", False)}


def row(label, model, price, sees=True, verified=True, provider="kie"):
    return {"label": label, "provider": provider, "model": model, "price_usd": price, "verified": verified, "sees_references": sees}


def jread(d, name):
    p = os.path.join(d, name)
    return json.load(open(p)) if os.path.exists(p) else None


@pytest.fixture
def world(tmp_path, monkeypatch):
    d = tmp_path / "p"
    (d / "media").mkdir(parents=True)
    shot = {"id": "S01-01", "scene": 1, "start": 0.0, "end": 4.0, "performers": ["Sege", "Ada"], "framing": "Medium shot, low angle", "lens": "35mm",
            "beats": ["Sege holds Ada's hand."], "visual_prompt": "Sege and Ada walk through the market holding hands at golden hour."}
    (d / "production.json").write_text(json.dumps({"meta": {}, "characters": [], "scenes": [{"number": 1, "heading": "EXT. MARKET", "start": 0, "end": 4, "notes": {}, "shots": [shot]}]}))
    (d / "project.json").write_text(json.dumps({"title": "T", "look": {"style": "auto"}, "routing": {"mode": "balanced"}}))
    Image.new("RGB", (400, 300), RED).save(d / "media" / "kf.png")
    (d / "keyframes.json").write_text(json.dumps({"production": {"S01-01": "project:media/kf.png"}}))
    old = {"id": "i1", "shot_id": "S01-01", "plan": "production", "provider": MODEL[0], "model": MODEL[1], "kind": "image", "state": "ready", "output": "media/kf.png", "overrides": {},
           "fix_notes": [], "created": 10, "updated": 10}
    (d / "jobs.json").write_text(json.dumps({"jobs": [old]}))
    monkeypatch.setattr(RT, "models", lambda kind: [row("Edit model", MODEL[1], 0.05), row("Blind", "kie/blind", 0.01, sees=False), row("Unproven", "kie/new", 0.02, verified=False),
                                                    row("Pricey", "kie/pricey", 0.3)] if kind == "image" else [])
    monkeypatch.setattr(RT, "batch_usd", lambda dd, shots, p, m, kind: round({"kie/edit-model": 0.05, "kie/pricey": 0.3}.get(m, 0.1) * len(shots), 2))
    monkeypatch.setattr(router, "available", lambda p: True)
    monkeypatch.setattr(ST, "can_check", lambda: False)
    monkeypatch.setattr(R, "_review", lambda dd, store, j: None)
    return str(d)


# ---------------------------------------------------------------- marking the part

def test_a_box_is_put_in_order_and_kept_inside_the_picture():
    assert HF.norm_box([0.6, 0.7, 0.2, 0.3]) == [0.2, 0.3, 0.6, 0.7]
    assert HF.norm_box([-1, -1, 2, 2]) == [0.0, 0.0, 1.0, 1.0]
    assert HF.norm_box(["0.1", "0.1", "0.5", "0.5"]) == [0.1, 0.1, 0.5, 0.5]


@pytest.mark.parametrize("bad", [None, "x", [], [0.1, 0.2], [0.1, 0.2, 0.3], [0.5, 0.5, 0.5, 0.5], [0.1, 0.1, 0.11, 0.9], [float("nan")] * 4, [float("inf"), 0, 1, 1], [None] * 4, {"a": 1}])
def test_a_box_that_is_not_a_hand_sized_box_is_refused(bad):
    with pytest.raises(SystemExit, match="box"):
        HF.norm_box(bad)


def test_the_crop_keeps_some_of_the_surroundings():
    assert HF.padded_pixels([0.4, 0.4, 0.6, 0.6], (1000, 500)) == [340, 170, 660, 330]
    assert HF.padded_pixels([0.0, 0.0, 0.1, 0.1], (1000, 500)) == [0, 0, 130, 65]            # never past the edge
    assert HF.padded_pixels([0.9, 0.9, 1.0, 1.0], (1000, 500)) == [870, 435, 1000, 500]


def test_the_crop_is_cut_enlarged_and_saved_and_the_keyframe_is_untouched(world):
    before = open(os.path.join(world, "media", "kf.png"), "rb").read()
    p = HF.prepare(world, "S01-01", [0.4, 0.4, 0.6, 0.6])
    assert p["source"] == "media/kf.png" and p["box"] == [136, 102, 264, 198]
    with Image.open(os.path.join(world, p["crop"])) as im:
        assert list(im.size) == p["size"] == [512, 384]                       # 128 x 96 pixels, enlarged by the most it is allowed (4x)
    big = HF.prepare(world, "S01-01", [0.0, 0.0, 1.0, 1.0])
    with Image.open(os.path.join(world, big["crop"])) as im:
        assert min(im.size) >= HF.MIN_SIDE and list(im.size) == big["size"]   # a large part is enlarged only as far as needed (here, not at all)
    assert open(os.path.join(world, "media", "kf.png"), "rb").read() == before


def test_a_shot_that_cannot_be_fixed_says_why(world):
    from filmcrafter_engine import library as L
    with pytest.raises(SystemExit, match="isn't in this project"):
        HF.prepare(world, "S09-09", [0.1, 0.1, 0.5, 0.5])
    kf = jread(world, "keyframes.json")
    kf["production"].pop("S01-01")
    json.dump(kf, open(os.path.join(world, "keyframes.json"), "w"))
    with pytest.raises(SystemExit, match="no approved keyframe"):
        HF.prepare(world, "S01-01", [0.1, 0.1, 0.5, 0.5])
    kf["production"]["S01-01"] = "project:media/kf.png"
    json.dump(kf, open(os.path.join(world, "keyframes.json"), "w"))
    L.lock(world, "S01-01", True)
    with pytest.raises(SystemExit, match="locked"):
        HF.prepare(world, "S01-01", [0.1, 0.1, 0.5, 0.5])


# ---------------------------------------------------------------- the model

def test_the_model_is_the_one_that_made_the_keyframe_when_it_can_see_pictures(world):
    assert HF.plan(world, "S01-01")["model"]["model"] == MODEL[1]


def test_a_blind_or_unknown_model_is_refused_when_asked_for(world):
    for m in ("kie/blind", "nonsense"):
        with pytest.raises(SystemExit, match="can't be used"):
            HF.plan(world, "S01-01", provider="kie", model=m)
    assert HF.plan(world, "S01-01", provider="kie", model="kie/pricey")["model"]["model"] == "kie/pricey"


def test_without_a_usable_keyframe_model_the_pinned_one_then_the_cheapest_proven_is_used(world, monkeypatch):
    jobs = jread(world, "jobs.json")
    jobs["jobs"][0]["model"] = "kie/blind"
    json.dump(jobs, open(os.path.join(world, "jobs.json"), "w"))
    assert HF.plan(world, "S01-01")["model"]["model"] == MODEL[1]                        # cheapest proven that can see
    p = jread(world, "project.json")
    p["routing"]["pins"] = {"image": {"provider": "kie", "model": "kie/pricey"}}
    json.dump(p, open(os.path.join(world, "project.json"), "w"))
    assert HF.plan(world, "S01-01")["model"]["model"] == "kie/pricey"
    monkeypatch.setattr(RT, "models", lambda kind: [row("Blind", "kie/blind", 0.01, sees=False)])
    with pytest.raises(SystemExit, match="No picture model"):
        HF.plan(world, "S01-01")


def test_the_plan_prices_the_versions(world):
    assert HF.plan(world, "S01-01")["usd_est"] == 0.05
    p = HF.plan(world, "S01-01", variants=3)
    assert p["variants"] == 3 and p["usd_est"] == 0.15
    assert HF.plan(world, "S01-01", variants=99)["variants"] == HF.MAX_VARIANTS and HF.plan(world, "S01-01", variants=0)["variants"] == 1


# ---------------------------------------------------------------- blending

def test_the_fixed_part_is_blended_in_with_a_soft_edge_and_the_rest_is_unchanged():
    base = Image.new("RGB", (200, 150), RED)
    out = HF.blend(base, Image.new("RGB", (300, 300), BLUE), [50, 40, 150, 110])             # the model returned a different shape: it is fitted
    assert out.size == base.size and base.getpixel((100, 75)) == RED                           # the original is not changed
    assert out.getpixel((100, 75)) == BLUE
    assert out.getpixel((10, 10)) == RED and out.getpixel((190, 140)) == RED and out.getpixel((49, 75)) == RED
    edge = out.getpixel((52, 75))
    assert edge != RED and edge != BLUE and edge[2] > RED[2]                                   # a soft join, not a hard one


# ---------------------------------------------------------------- the whole journey

class Fake:
    name = "kie"
    sent = []
    uploads = []

    def upload(self, path):
        Fake.uploads.append(os.path.basename(path))
        return "https://cdn/" + os.path.basename(path)

    def submit(self, model, payload):
        Fake.sent.append(payload)
        return {"id": "r1"}

    def poll(self, model, rid, meta=None):
        return {"state": "done", "url": "https://cdn/fixed.png"}


@pytest.fixture
def journey(world, monkeypatch):
    Fake.sent, Fake.uploads = [], []
    monkeypatch.setitem(R.PROVIDERS, "kie", Fake)
    monkeypatch.setattr(R, "manifest", lambda provider, model, refresh=False: R._finish("kie", model, "Edit", "", [F("prompt", required=True), F("image_urls", "array", items="string", max_items=8,
                                                                                                                             description="Input images to edit")]))

    class Dl:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_content(self, n):
            b = io.BytesIO()
            Image.new("RGB", (640, 480), BLUE).save(b, "PNG")
            yield b.getvalue()
    monkeypatch.setattr(R.requests, "get", lambda url, **kw: Dl())
    return world


def test_the_fix_goes_out_as_one_crop_and_one_instruction_and_comes_back_laid_into_the_picture(journey):
    d = journey
    r = HF.queue(d, "S01-01", [0.4, 0.4, 0.6, 0.6], note="the left hand is the wrong one", variants=1)
    assert r["queued"] == 1 and r["model"] == "Edit model" and r["usd_est"] == 0.05
    queued = jread(d, "jobs.json")["jobs"][-1]
    assert queued["hand_fix"]["instruction"].startswith("Redraw ONLY the hands") and "left hand is the wrong one" in queued["hand_fix"]["instruction"] and queued["swap_in"] == "handfix"
    R.run(d, poll_every=0)
    sent = Fake.sent[0]
    assert len(Fake.uploads) == 1 and "handcrop" in Fake.uploads[0] and len(sent["image_urls"]) == 1          # only the crop is sent, no character sheets
    assert "Redraw ONLY the hands" in sent["prompt"] and "golden hour" not in sent["prompt"] and "Medium shot" not in sent["prompt"]   # the shot's own prompt and framing are left out
    job = next(j for j in jread(d, "jobs.json")["jobs"] if j.get("hand_fix"))
    assert job["state"] == "ready" and job["hand_fix"]["placed"] is True and job["output"].startswith("media/S01-01_handfix_") and job["crop_output"] != job["output"]
    with Image.open(os.path.join(d, job["output"])) as out:
        assert out.size == (400, 300) and out.getpixel((200, 150)) == BLUE and out.getpixel((5, 5)) == RED
    with Image.open(os.path.join(d, "media", "kf.png")) as orig:
        assert orig.getpixel((200, 150)) == RED                                                                # the original keyframe is untouched
    assert jread(d, "keyframes.json")["production"]["S01-01"] == "project:media/kf.png"                       # and still the approved one


def test_the_fixed_keyframe_waits_and_is_used_with_one_undoable_step(journey):
    d = journey
    HF.queue(d, "S01-01", [0.4, 0.4, 0.6, 0.6])
    R.run(d, poll_every=0)
    s = KS.swap_status(d)
    assert s["ready"] == 1 and s["reasons"]["handfix"]["ready"] == 1
    r = KS.apply_swaps(d)
    assert r["applied"] == ["S01-01"]
    new = jread(d, "keyframes.json")["production"]["S01-01"]
    assert new.startswith("project:media/S01-01_handfix_")
    H.undo(d)
    assert jread(d, "keyframes.json")["production"]["S01-01"] == "project:media/kf.png"


def test_several_versions_can_be_asked_for_and_each_is_laid_in(journey):
    d = journey
    r = HF.queue(d, "S01-01", [0.4, 0.4, 0.6, 0.6], variants=2)
    assert r["queued"] == 2 and r["usd_est"] == 0.1
    R.run(d, poll_every=0)
    outs = [j["output"] for j in jread(d, "jobs.json")["jobs"] if j.get("hand_fix")]
    assert len(outs) == 2 and len(set(outs)) == 2 and all(o.startswith("media/S01-01_handfix_") for o in outs)


def test_a_fix_is_not_remade_automatically_when_the_picture_still_fails_its_check(journey, monkeypatch):
    d = journey
    monkeypatch.setattr(ST, "can_check", lambda: True)
    monkeypatch.setattr(ST, "check", lambda dd, j: ST.settle({"ok": False, "problems": [{"kind": "anatomy", "severity": "major", "detail": "Still fused."}], "fix": ""}, "m"))
    HF.queue(d, "S01-01", [0.4, 0.4, 0.6, 0.6])
    R.run(d, poll_every=0)
    jobs = jread(d, "jobs.json")["jobs"]
    assert len([j for j in jobs if j["kind"] == "image"]) == 2                          # the old keyframe and the one fix: no paid re-make was queued
    fix = next(j for j in jobs if j.get("hand_fix"))
    assert fix["still_check"]["ok"] is False and KS.swap_status(d)["ready"] == 0       # and a picture that fails its check is not offered as ready


def test_a_locked_shot_or_a_service_without_a_key_queues_nothing(journey, monkeypatch):
    from filmcrafter_engine import library as L
    d = journey
    monkeypatch.setattr(router, "available", lambda p: False)
    with pytest.raises(SystemExit, match="Add your"):
        HF.queue(d, "S01-01", [0.4, 0.4, 0.6, 0.6])
    monkeypatch.setattr(router, "available", lambda p: True)
    L.lock(d, "S01-01", True)
    with pytest.raises(SystemExit, match="locked"):
        HF.queue(d, "S01-01", [0.4, 0.4, 0.6, 0.6])
    assert len(jread(d, "jobs.json")["jobs"]) == 1


# ---------------------------------------------------------------- laying it in safely

def test_finish_ignores_paths_that_lead_outside_the_project_and_boxes_that_make_no_sense(journey, tmp_path):
    d = journey
    outside = tmp_path / "outside.png"
    Image.new("RGB", (50, 50), BLUE).save(outside)
    store = R.Store(d)
    base = {"id": "h1", "shot_id": "S01-01", "output": "media/kf.png", "hand_fix": {"source": "media/kf.png", "box": [10, 10, 100, 100]}}
    for bad in ({"output": "../outside.png"}, {"output": str(outside)}, {"hand_fix": {"source": "../outside.png", "box": [10, 10, 100, 100]}}, {"hand_fix": {"source": str(outside), "box": [1, 1, 99, 99]}}):
        j = {**base, **bad}
        HF.finish(d, store, j)
        assert j["output"] == bad.get("output", "media/kf.png") and not j["hand_fix"].get("placed")
    for box in (None, [1, 2, 3], ["a", 2, 3, 4], [1.5, 2, 3, 4], [10, 10, 12, 12], [500, 500, 600, 600]):
        j = {**base, "hand_fix": {"source": "media/kf.png", "box": box}}
        with pytest.raises(SystemExit):
            HF.finish(d, store, j)
    assert not [f for f in os.listdir(os.path.join(d, "media")) if "handfix" in f]


def test_finish_does_nothing_twice(journey):
    d = journey
    HF.queue(d, "S01-01", [0.4, 0.4, 0.6, 0.6])
    R.run(d, poll_every=0)
    store = R.Store(d)
    job = next(j for j in store.jobs if j.get("hand_fix"))
    first = job["output"]
    HF.finish(d, store, job)
    assert job["output"] == first and len([f for f in os.listdir(os.path.join(d, "media")) if "handfix" in f]) == 1


# ---------------------------------------------------------------- finding the hands

def test_the_models_boxes_are_kept_only_when_they_make_sense_and_at_most_four():
    out = {"hands": [{"x0": 0.1, "y0": 0.1, "x1": 0.3, "y1": 0.4, "why": "  fused \n fingers "}, {"x0": 0.5, "y0": 0.5, "x1": 0.5, "y1": 0.5, "why": "a dot"},
                     {"x0": "bad", "y0": 0, "x1": 1, "y1": 1, "why": "x"}, {"y0": 0}, {"x0": 0.9, "y0": 0.9, "x1": 0.2, "y1": 0.2, "why": "x" * 400}, *[{"x0": 0.1, "y0": 0.1, "x1": 0.4, "y1": 0.4, "why": "n"}] * 6]}
    boxes = HF.clean_boxes(out)
    assert len(boxes) == HF.MAX_BOXES and boxes[0] == {"box": [0.1, 0.1, 0.3, 0.4], "why": "fused fingers"} and boxes[1]["box"] == [0.2, 0.2, 0.9, 0.9] and len(boxes[1]["why"]) == 160
    assert HF.clean_boxes(None) == [] and HF.clean_boxes({"hands": "x"}) == [] and HF.clean_boxes({}) == []


def test_finding_hands_needs_an_ai_brain_that_can_look(world):
    with pytest.raises(SystemExit, match="draw the box yourself"):
        HF.locate(world, "S01-01")
