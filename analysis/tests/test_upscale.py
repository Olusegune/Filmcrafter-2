"""Upscaling keyframes and takes (Topaz, Recraft, others): the right file in the right field, the result put where it belongs, the original kept and restorable, and a paid run never lost."""
import json
import os

import pytest
from PIL import Image

from filmcrafter_engine import library
from filmcrafter_engine import render as R
from filmcrafter_engine import upscale as U
from tests.test_video_models import f, kie

TOPAZ_IMG = lambda: kie("topaz/image-upscale", f("image_url", required=True), f("upscale_factor", enum=["1", "2", "4"], required=True))
TOPAZ_VID = lambda: kie("topaz/video-upscale", f("video_url", required=True), f("upscale_factor", enum=["1", "2", "4"]))
RECRAFT = lambda: kie("recraft/crisp-upscale", f("image", required=True))
FAL_ARRAY = lambda: kie("fal-ai/seedvr/upscale/image", f("image_urls", "array", items="string", required=True), f("scale", "number", minimum=1, maximum=4))


class Fake:
    name = "kie"

    def __init__(self, out, polls=("done",), fail=None):
        self.out, self.polls, self.fail, self.submitted, self.uploaded = out, list(polls), fail, [], []

    def upload(self, path):
        self.uploaded.append(path)
        return "https://x/" + os.path.basename(path)

    def submit(self, model, payload):
        if self.fail:
            raise R.RequestProblem(self.fail)
        self.submitted.append((model, payload))
        return {"id": "task1"}

    def poll(self, model, rid, meta=None):
        s = self.polls.pop(0) if self.polls else "done"
        if s == "running":
            return {"state": "running", "detail": "queued"}
        if s == "failed":
            return {"state": "failed", "error": "The server is busy, please try again later"}
        return {"state": "done", "url": "file:" + self.out, "cost": 6, "cost_unit": "credits"}


@pytest.fixture
def proj(tmp_path, monkeypatch):
    d = tmp_path / "p"
    (d / "assets").mkdir(parents=True)
    (d / "generations").mkdir()
    Image.new("RGB", (64, 36), (200, 30, 30)).save(d / "assets" / "kf.png")
    (d / "generations" / "v1.mp4").write_bytes(b"video")
    json.dump({"title": "T", "song": "song.wav", "aspect_ratio": "16:9"}, open(d / "project.json", "w"))
    json.dump({"meta": {}, "scenes": [{"number": 1, "heading": "INT.", "shots": [{"id": "S01-01", "start": 0, "end": 4, "beats": ["She waits."], "performers": ["Ada"], "description": "She waits."}]}]}, open(d / "production.json", "w"))
    json.dump({"production": {"S01-01": "project:assets/kf.png"}}, open(d / "keyframes.json", "w"))
    json.dump({"jobs": [{"id": "v1", "shot_id": "S01-01", "plan": "production", "provider": "kie", "model": "bytedance/seedance-2", "kind": "video", "state": "ready", "output": "generations/v1.mp4",
                         "created": 1, "updated": 1, "attempts": 1, "overrides": {}, "keyframe_ref": "project:assets/kf.png", "shot_start": 0, "shot_end": 4}]}, open(d / "jobs.json", "w"))
    table = {"topaz/image-upscale": TOPAZ_IMG, "topaz/video-upscale": TOPAZ_VID, "recraft/crisp-upscale": RECRAFT, "fal-ai/seedvr/upscale/image": FAL_ARRAY}
    monkeypatch.setattr(R, "manifest", lambda prov, model, refresh=False: table[model]())
    monkeypatch.setattr(U.R, "emit", lambda **k: None)
    out = tmp_path / "result.png"
    Image.new("RGB", (256, 144), (30, 200, 30)).save(out)
    return str(d), str(out)


def keyframe(d):
    return json.load(open(os.path.join(d, "keyframes.json")))["production"]["S01-01"]


# ---------------------------------------------------------------- the request
def test_the_file_goes_in_the_field_that_takes_it_and_the_factor_in_the_field_that_takes_a_size():
    assert U.build_payload(TOPAZ_IMG(), "image", "https://x/a.png", 4) == {"image_url": "https://x/a.png", "upscale_factor": "4"}
    assert U.build_payload(TOPAZ_IMG(), "image", "https://x/a.png", 2)["upscale_factor"] == "2"
    assert U.build_payload(RECRAFT(), "image", "https://x/a.png", 4) == {"image": "https://x/a.png"}                 # no factor field: none sent
    assert U.build_payload(TOPAZ_VID(), "video", "https://x/a.mp4", 2) == {"video_url": "https://x/a.mp4", "upscale_factor": "2"}
    assert U.build_payload(FAL_ARRAY(), "image", "https://x/a.png", 4) == {"image_urls": ["https://x/a.png"], "scale": 4}   # a list field gets a list; a number field a number


@pytest.mark.parametrize("enum,want,expect", [(["1", "2", "4"], 4, "4"), (["1", "2", "4"], 2, "2"), (["2x", "4x"], 4, "4x"), (["2", "4"], 3, "2"), (["1"], 4, "1"), (["fast", "slow"], 2, "fast")])
def test_the_factor_is_the_nearest_the_tool_offers(enum, want, expect):
    assert U._pick_factor(f("upscale_factor", enum=enum), want) == expect


def test_a_numeric_factor_is_kept_inside_the_tools_range():
    assert U._pick_factor(f("scale", "integer", minimum=1, maximum=3), 4) == 3
    assert U._pick_factor(f("scale", "number", minimum=2, maximum=8), 4) == 4.0
    assert U._pick_factor(f("scale", "string"), 4) == "4"


def test_a_tool_with_no_input_for_the_file_is_refused_in_plain_words():
    with pytest.raises(SystemExit) as e:
        U.build_payload(kie("x/y", f("prompt", required=True)), "image", "https://x/a.png", 2)
    assert "no input for a image" in str(e.value) or "no input for a" in str(e.value)


def test_other_required_inputs_get_the_tools_own_default():
    man = kie("x/y", f("image_url", required=True), f("mode", enum=["fast", "best"], required=True), f("denoise", "number", default=0.3, required=True), f("note"))
    assert U.build_payload(man, "image", "u", 2) == {"image_url": "u", "mode": "fast", "denoise": 0.3}


def test_tools_say_whether_their_provider_key_is_set(monkeypatch):
    monkeypatch.setenv("KIE_KEY", "k")
    monkeypatch.delenv("FAL_KEY", raising=False)
    t = {x["id"]: x for x in U.tools()}
    assert t["kie-topaz-image"]["ready"] is True and t["fal-topaz-image"]["ready"] is False
    assert all(x["media"] == "video" for x in U.tools("video")) and {x["media"] for x in U.tools("image")} == {"image"}
    assert t["kie-topaz-image"]["factors"] == [2, 4]
    assert [x["id"] for x in U.tools()][:3] == ["kie-topaz-image", "kie-recraft-image", "kie-topaz-video"]          # Kie first


# ---------------------------------------------------------------- a keyframe
def test_an_upscaled_keyframe_becomes_the_approved_one_and_the_original_is_kept(proj):
    d, out = proj
    p = Fake(out)
    run = U.run_one(d, "kie-topaz-image", "keyframe", "S01-01", None, 4, provider=p, poll_s=0)
    assert run["state"] == "ready" and run["cost"] == 6
    assert p.submitted == [("topaz/image-upscale", {"image_url": "https://x/kf.png", "upscale_factor": "4"})]
    assert keyframe(d).startswith("project:generations/S01-01__up4x_") and keyframe(d).endswith(".png")
    assert os.path.exists(os.path.join(d, "assets", "kf.png"))                                                         # the original picture is untouched
    assert Image.open(os.path.join(d, keyframe(d)[len("project:"):])).size == (256, 144)


def test_takes_made_from_the_old_keyframe_are_not_marked_out_of_date(proj):
    d, out = proj
    U.run_one(d, "kie-topaz-image", "keyframe", "S01-01", None, 2, provider=Fake(out), poll_s=0)
    take = next(j for j in R.Store(d).jobs if j["id"] == "v1")
    assert take["keyframe_ref"] == keyframe(d)                                                                          # still matches: it is the same picture, sharper
    from filmcrafter_engine import golden
    assert golden.status(d)["stale"] == []


def test_undoing_a_keyframe_upscale_brings_the_original_back(proj):
    d, out = proj
    U.run_one(d, "kie-topaz-image", "keyframe", "S01-01", None, 2, provider=Fake(out), poll_s=0)
    r = U.revert(d, "S01-01", "keyframe")
    assert r["restored"] == "project:assets/kf.png" and keyframe(d) == "project:assets/kf.png"
    with pytest.raises(SystemExit):
        U.revert(d, "S01-01", "keyframe")                                                                               # already undone: nothing to undo


def test_a_shot_with_no_approved_keyframe_cannot_be_upscaled(proj):
    d, out = proj
    json.dump({"production": {}}, open(os.path.join(d, "keyframes.json"), "w"))
    with pytest.raises(SystemExit) as e:
        U.start(d, "kie-topaz-image", "keyframe", "S01-01", None, 2, Fake(out))
    assert "no approved keyframe" in str(e.value)


# ---------------------------------------------------------------- a take
def test_an_upscaled_take_is_added_chosen_for_export_and_the_original_take_can_be_chosen_again(proj):
    d, out = proj
    mp4 = os.path.join(os.path.dirname(out), "up.mp4")
    open(mp4, "wb").write(b"bigger video")
    run = U.run_one(d, "kie-topaz-video", "take", None, "v1", 2, provider=Fake(mp4), poll_s=0)
    assert run["state"] == "ready" and run["job"]
    jobs = {j["id"]: j for j in R.Store(d).jobs}
    new = jobs[run["job"]]
    assert new["kind"] == "video" and new["tool"] == "upscale" and new["upscaled_from"] == "v1" and new["state"] == "ready" and new["output"].endswith(".mp4")
    assert library.shot_state(d)["S01-01"]["approved"] == new["id"]
    assert os.path.exists(os.path.join(d, "generations", "v1.mp4"))                                                    # the first take is still there
    U.revert(d, "S01-01", "take")
    assert library.shot_state(d)["S01-01"]["approved"] == "v1"


def test_only_a_finished_video_take_can_be_upscaled(proj):
    d, out = proj
    for job, why in (("nope", "finished take"), (None, "finished take")):
        with pytest.raises(SystemExit) as e:
            U.start(d, "kie-topaz-video", "take", None, job, 2, Fake(out))
        assert why in str(e.value)


def test_a_picture_tool_is_refused_for_a_take_and_the_other_way_round(proj):
    d, out = proj
    with pytest.raises(SystemExit) as a:
        U.start(d, "kie-topaz-image", "take", None, "v1", 2, Fake(out))
    assert "upscales pictures" in str(a.value)
    with pytest.raises(SystemExit) as b:
        U.start(d, "kie-topaz-video", "keyframe", "S01-01", None, 2, Fake(out))
    assert "upscales videos" in str(b.value)
    with pytest.raises(SystemExit):
        U.start(d, "no-such-tool", "keyframe", "S01-01", None, 2, Fake(out))


# ---------------------------------------------------------------- failure, and a paid run never lost
def test_a_provider_that_fails_changes_nothing_and_says_so(proj):
    d, out = proj
    run = U.run_one(d, "kie-topaz-image", "keyframe", "S01-01", None, 2, provider=Fake(out, polls=("running", "failed")), poll_s=0)
    assert run["state"] == "failed" and "busy" in run["error"].lower()
    assert keyframe(d) == "project:assets/kf.png"


def test_a_request_the_provider_refuses_is_reported_and_nothing_is_queued_as_waiting(proj):
    d, out = proj
    with pytest.raises(SystemExit) as e:
        U.start(d, "kie-topaz-image", "keyframe", "S01-01", None, 2, Fake(out, fail="Kie.ai refused this request, so nothing was charged."))
    assert "nothing was charged" in str(e.value)
    assert [r["state"] for r in U.load(d)] == ["failed"]


def test_a_run_is_saved_the_moment_it_is_accepted_and_resume_finishes_it_later(proj):
    d, out = proj
    p = Fake(out, polls=("running",))
    run = U.start(d, "kie-topaz-image", "keyframe", "S01-01", None, 2, p)
    assert [r["state"] for r in U.load(d)] == ["submitted"] and U.load(d)[0]["task"] == "task1"          # on disk before anyone waits
    U.finish(d, run, p, wait=False)                                                                       # one look: still running
    assert U.load(d)[0]["state"] == "submitted" and keyframe(d) == "project:assets/kf.png"
    later = U.resume(d, Fake(out))                                                                        # the app was closed and opened again
    assert later["finished"] == 1 and keyframe(d).startswith("project:generations/")


def test_resume_leaves_finished_and_failed_runs_alone(proj):
    d, out = proj
    U.run_one(d, "kie-topaz-image", "keyframe", "S01-01", None, 2, provider=Fake(out), poll_s=0)
    before = json.load(open(os.path.join(d, "upscales.json")))
    assert U.resume(d, Fake(out))["finished"] == 0
    assert json.load(open(os.path.join(d, "upscales.json"))) == before


def test_a_file_that_is_not_a_picture_is_not_taken_for_one(proj, tmp_path):
    d, out = proj
    bad = str(tmp_path / "bad.png")
    open(bad, "wb").write(b"not a picture")
    with pytest.raises(SystemExit) as e:
        U.run_one(d, "kie-topaz-image", "keyframe", "S01-01", None, 2, provider=Fake(bad), poll_s=0)
    assert "isn't a picture" in str(e.value)
    assert keyframe(d) == "project:assets/kf.png" and not [n for n in os.listdir(os.path.join(d, "generations")) if n.startswith("S01-01__up")]


# ---------------------------------------------------------------- hostile input
@pytest.mark.parametrize("ref", ["project:../../outside.png", "project:/etc/passwd", "../x.png", "project:assets/missing.png"])
def test_a_keyframe_path_that_leaves_the_project_or_is_missing_is_refused(proj, ref):
    d, out = proj
    json.dump({"production": {"S01-01": ref}}, open(os.path.join(d, "keyframes.json"), "w"))
    with pytest.raises(SystemExit):
        U.start(d, "kie-topaz-image", "keyframe", "S01-01", None, 2, Fake(out))


@pytest.mark.parametrize("factor", ["x", "999", -1, None, "2; rm", 3.5])
def test_a_junk_factor_falls_back_to_two(proj, factor):
    d, out = proj
    p = Fake(out)
    U.start(d, "kie-topaz-image", "keyframe", "S01-01", None, factor, p)
    assert p.submitted[0][1]["upscale_factor"] == "2"


def test_an_unreadable_runs_file_is_started_again_not_fatal(proj):
    d, out = proj
    open(os.path.join(d, "upscales.json"), "w").write("{ not json")
    assert U.load(d) == [] and U.status(d)["runs"] == []
    json.dump({"a": 1}, open(os.path.join(d, "upscales.json"), "w"))
    assert U.load(d) == []


def test_the_engine_and_the_app_agree_on_the_action_names():
    lib = open(os.path.join(os.path.dirname(__file__), "..", "..", "src-tauri", "src", "lib.rs"), encoding="utf-8").read()
    assert "filmcrafter_engine.upscale" in lib and '"tools", "status", "resume", "revert", "run"' in lib
    assert 'choices=["tools", "status", "resume", "revert", "run"]' in open(U.__file__, encoding="utf-8").read()
