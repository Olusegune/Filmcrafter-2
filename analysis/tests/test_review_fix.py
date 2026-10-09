"""Review > Fix. A flagged take is often a lip-synced version; fixing it must re-render the VIDEO under it, never ask a lip-sync model to draw a shot (which was queued, failed, and looked like nothing happened)."""
import json
import os

import pytest

from filmcrafter_engine import render as R
from tests.test_video_models import f, kie


def project(tmp_path):
    d = tmp_path / "p"
    d.mkdir(exist_ok=True)
    json.dump({"title": "T", "song": "song.wav"}, open(d / "project.json", "w"))
    json.dump({"duration": 20, "sections": []}, open(d / "songmap.json", "w"))
    shot = {"id": "S01-01", "start": 0, "end": 4, "beats": ["She waits."], "performers": ["Ada"], "description": "She waits."}
    json.dump({"meta": {}, "scenes": [{"number": 1, "heading": "INT.", "shots": [shot]}]}, open(d / "production.json", "w"))
    json.dump({"jobs": []}, open(d / "jobs.json", "w"))
    return str(d)


LIP = lambda: kie("volcengine/video-to-video-lip-sync", f("video_url", required=True), f("audio_url", required=True))
VID = lambda: kie("bytedance/seedance-2-fast", f("prompt", required=True), f("first_frame_url"), f("duration", "integer", minimum=4, maximum=15, required=True))
IMG = lambda: kie("google/nano-banana", f("prompt", required=True), f("image_urls", "array", items="string"))


@pytest.fixture
def models(monkeypatch):
    table = {"volcengine/video-to-video-lip-sync": LIP, "bytedance/seedance-2-fast": VID, "google/nano-banana": IMG}
    real = R.manifest
    monkeypatch.setattr(R, "manifest", lambda p, m: table[m]() if m in table else real(p, m))
    monkeypatch.setattr("filmcrafter_engine.routing.guard", lambda *a, **k: None)
    return table


def test_a_lip_sync_model_is_refused_for_drawing_a_shot_in_plain_words(tmp_path, models):
    d = project(tmp_path)
    with pytest.raises(SystemExit) as e:
        R.enqueue(d, ["S01-01"], "kie", "volcengine/video-to-video-lip-sync", {}, ["fix"], "video")
    msg = str(e.value)
    assert "can't render a shot as video" in msg and "lip-synced version of a take" in msg and "Choose a video model" in msg
    assert json.load(open(os.path.join(d, "jobs.json")))["jobs"] == []                       # nothing was queued


def test_a_lip_sync_model_is_refused_for_a_keyframe_too(tmp_path, models):
    d = project(tmp_path)
    with pytest.raises(SystemExit) as e:
        R.enqueue(d, ["S01-01"], "kie", "volcengine/video-to-video-lip-sync", {}, None, "image")
    assert "can't make a keyframe" in str(e.value) and "Choose an image model" in str(e.value)


def test_a_video_model_with_no_duration_setting_is_not_mistaken_for_a_lip_sync_model(tmp_path, monkeypatch):
    """Such a model looks like a picture model to the engine; it must still be allowed to render video."""
    d = project(tmp_path)
    fixed = kie("some/fixed-length-video", f("prompt", required=True), f("first_frame_url"))
    monkeypatch.setattr(R, "manifest", lambda p, m: fixed)
    monkeypatch.setattr("filmcrafter_engine.routing.guard", lambda *a, **k: None)
    assert R.enqueue(d, ["S01-01"], "kie", "some/fixed-length-video", {}, None, "video")[0]["kind"] == "video"


def test_the_right_kind_of_model_is_still_accepted_for_each_job(tmp_path, models):
    d = project(tmp_path)
    made = R.enqueue(d, ["S01-01"], "kie", "bytedance/seedance-2-fast", {}, ["Keep her in the green dress"], "video")
    assert len(made) == 1 and made[0]["kind"] == "video" and made[0]["fix_notes"] == ["Keep her in the green dress"]
    (tmp_path / "i").mkdir()
    d2 = project(tmp_path / "i")
    assert R.enqueue(d2, ["S01-01"], "kie", "google/nano-banana", {}, None, "image")[0]["kind"] == "image"


def test_a_lip_sync_pass_is_still_queued_the_normal_way(tmp_path, models):
    d = project(tmp_path)
    json.dump({"jobs": [{"id": "v1", "shot_id": "S01-01", "plan": "production", "provider": "kie", "model": "bytedance/seedance-2-fast", "kind": "video", "state": "ready", "output": "g/v1.mp4", "created": 1, "updated": 1, "attempts": 1, "overrides": {}}]}, open(os.path.join(d, "jobs.json"), "w"))
    made = R.enqueue(d, ["S01-01"], "kie", "volcengine/video-to-video-lip-sync", {}, None, "lipsync", "v1")
    assert made and made[0]["kind"] == "lipsync" and made[0]["source_job"] == "v1"
