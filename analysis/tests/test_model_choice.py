"""Choosing the picture and video model: the blurbs, the list the pickers show, and the warning when one project's keyframes come from different models."""
import json
import os

import pytest

from filmcrafter_engine import modelblurbs as MB, router, routing as RT


def test_every_model_family_has_a_blurb_and_no_blurb_is_for_a_family_that_does_not_exist():
    assert set(MB.BLURBS) == set(router.FAMILIES)
    for key, b in MB.BLURBS.items():
        assert b["strength"] and b["consider"], key
        assert set(b) <= {"strength", "consider", "watch"}, key


def test_an_unknown_family_gets_an_empty_blurb_not_an_error():
    assert MB.blurb("no-such-model") == {"strength": "", "consider": "", "watch": ""}


def test_the_advice_says_why_to_stay_with_one_model():
    assert "one picture model" in MB.ONE_MODEL_ADVICE and "different" in MB.ONE_MODEL_ADVICE


def test_the_picker_list_carries_the_blurb_and_whether_the_model_sees_your_pictures(monkeypatch):
    monkeypatch.setattr(router, "available", lambda p: p in ("kie", "fal"))
    images = RT.models("image")
    assert images and all("strength" in r and r["family"] in router.FAMILIES for r in images)
    nb = next(r for r in images if r["family"] == "nano-banana" and r["provider"] == "kie")
    assert nb["sees_references"] is True and "reference" in nb["strength"].lower() and nb["verified"] is True
    videos = RT.models("video")
    assert videos and all(r["sees_references"] is None for r in videos)


def test_only_models_on_connected_providers_are_listed(monkeypatch):
    monkeypatch.setattr(router, "available", lambda p: False)
    assert RT.models("image") == [] and RT.models("video") == []


@pytest.fixture
def project(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    (d / "project.json").write_text(json.dumps({"title": "T"}))
    return str(d)


def jobs(d, *items):
    base = {"kind": "image", "state": "ready", "plan": "production"}
    json.dump({"jobs": [{**base, "id": f"j{i}", **it} for i, it in enumerate(items)]}, open(os.path.join(d, "jobs.json"), "w"))


NB = {"provider": "kie", "model": "google/nano-banana-edit"}
GPT = {"provider": "kie", "model": "gpt/gpt-image-2-5-flare-image-to-image"}


def test_one_model_is_consistent(project):
    jobs(project, {**NB}, {**NB}, {**NB})
    c = RT.consistency(project)
    assert c["mixed"] is False and c["advice"] == "" and c["image_models"] == [{"provider": "kie", "model": NB["model"], "label": "Nano Banana", "count": 3}]


def test_two_models_are_flagged_with_the_advice_and_the_counts(project):
    jobs(project, {**NB}, {**NB}, {**GPT})
    c = RT.consistency(project)
    assert c["mixed"] is True and c["pinned"] is False and "one picture model" in c["advice"]
    assert [(m["label"], m["count"]) for m in c["image_models"]] == [("Nano Banana", 2), ("GPT Image 2.5 Flare", 1)]


def test_a_pinned_picture_model_silences_the_warning(project):
    jobs(project, {**NB}, {**GPT})
    p = json.load(open(os.path.join(project, "project.json")))
    p["routing"] = {"pins": {"image": NB}}
    json.dump(p, open(os.path.join(project, "project.json"), "w"))
    c = RT.consistency(project)
    assert c["mixed"] is True and c["pinned"] is True and c["advice"] == ""


def test_end_frames_rejected_stills_failed_jobs_and_video_are_not_counted(project):
    jobs(project, {**NB}, {**GPT, "frame": "end"}, {**GPT, "rejected": True}, {**GPT, "state": "failed"}, {**GPT, "kind": "video"})
    assert RT.consistency(project)["mixed"] is False


def test_no_jobs_or_a_damaged_jobs_file_is_just_empty(project):
    assert RT.consistency(project) == {"image_models": [], "mixed": False, "pinned": False, "advice": ""}
    open(os.path.join(project, "jobs.json"), "w").write("{nope")
    assert RT.consistency(project)["image_models"] == []


def test_the_status_carries_the_consistency_and_the_pins(project, monkeypatch):
    monkeypatch.setattr(router, "available", lambda p: False)
    jobs(project, {**NB}, {**GPT})
    s = RT.status(project)
    assert s["consistency"]["mixed"] is True and s["pins"] == {}
