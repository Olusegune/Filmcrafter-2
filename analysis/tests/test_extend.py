"""Extend a take: a continuation from the last frame, joined to the original; nothing billed (mock provider), real ffmpeg."""
import json
import os
import subprocess

import pytest

from pulseframe_analysis import extend as E, render as R
from pulseframe_analysis.editor_export import probe
from pulseframe_analysis.export import ffmpeg


def field(name, type="string", **kw):
    return {"name": name, "type": type, "items": None, "enum": kw.get("enum"), "default": kw.get("default"), "minimum": kw.get("minimum"), "maximum": kw.get("maximum"),
            "max_items": None, "max_length": None, "description": "", "required": kw.get("required", False)}


def clip(path, seconds, size="320x180", rate=24):
    p = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate={rate}:duration={seconds}",
                        "-pix_fmt", "yuv420p", "-c:v", "libx264", path], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return path


@pytest.fixture
def project(tmp_path):
    d = tmp_path / "proj"
    (d / "generations").mkdir(parents=True)
    shot = {"id": "S01-01", "scene": 1, "number": 1, "start": 0.0, "end": 12.0, "beats": ["Young Sege turns into old Sege."], "performers": [], "framing": "wide", "camera_moves": [], "source_shots": ["S01-01"]}
    plan = {"meta": {}, "characters": [], "scenes": [{"number": 1, "heading": "INT. ROOM", "start": 0, "end": 12, "notes": {}, "shots": [shot]}]}
    (d / "production.json").write_text(json.dumps(plan))
    (d / "project.json").write_text(json.dumps({"title": "T", "song": "song.wav", "aspect_ratio": "16:9"}))
    (d / "songmap.json").write_text(json.dumps({"duration": 12.0, "lyrics": [], "sections": [], "beats": []}))
    clip(str(d / "generations" / "base.mp4"), 8)
    base = {"id": "base", "shot_id": "S01-01", "plan": "production", "provider": "fal", "model": "test/model", "kind": "video", "state": "ready", "output": "generations/base.mp4",
            "overrides": {}, "fix_notes": [], "created": 100, "updated": 160, "submitted": 110, "attempts": 1, "provider_job_id": "r0", "error": None, "cost": None,
            "shot_start": 0.0, "shot_end": 12.0, "source_shots": ["S01-01"]}
    (d / "jobs.json").write_text(json.dumps({"jobs": [base]}))
    return str(d)


class Fake:
    name = "fal"
    sent = []

    def upload(self, path):
        return "https://cdn/" + os.path.basename(path)

    def submit(self, model, payload):
        Fake.sent.append(payload)
        return {"id": "r9"}

    def poll(self, model, rid, meta=None):
        return {"state": "done", "url": "https://cdn/new.mp4"}


@pytest.fixture
def fake(monkeypatch, tmp_path):
    Fake.sent = []
    monkeypatch.setitem(R.PROVIDERS, "fal", Fake)
    m = R._finish("fal", "test/model", "Test", "image-to-video", [field("prompt", required=True), field("duration", enum=["4", "6", "8"])])
    monkeypatch.setattr(R, "manifest", lambda provider, model, refresh=False: m)
    monkeypatch.setattr(E, "manifest", lambda *a, **k: m, raising=False)
    monkeypatch.setattr(R, "_review", lambda d, store, j: None)
    new = clip(str(tmp_path / "new.mp4"), 4, size="640x360", rate=30)       # a different size and frame rate, as real providers give
    data = open(new, "rb").read()

    class Dl:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_content(self, n): yield data
    monkeypatch.setattr(R.requests, "get", lambda url, **kw: Dl())
    return Fake


# ---------------------------------------------------------------- the advice

def test_info_reports_the_shortfall_and_what_one_continuation_covers(project, fake):
    i = E.info(project, "S01-01")
    assert i["can_extend"] and i["take"] == "base" and i["shot_seconds"] == 12.0
    assert 7.9 < i["take_seconds"] < 8.1 and 3.8 < i["short_seconds"] < 4.1
    assert i["model_longest"] == 8.0 and i["suggest_seconds"] == 4.0 and 11.9 < i["will_cover"] < 12.1


def test_a_shot_that_changes_who_is_on_screen_is_told_to_set_an_end_frame(project, fake):
    i = E.info(project, "S01-01")
    assert any("end frame" in a for a in i["advice"])


def test_no_advice_to_extend_when_the_take_already_covers_the_shot(project, fake):
    plan = json.load(open(os.path.join(project, "production.json")))
    plan["scenes"][0]["shots"][0]["end"] = 8.5
    json.dump(plan, open(os.path.join(project, "production.json"), "w"))
    i = E.info(project, "S01-01")
    assert not i["can_extend"] and "already covers" in i["reason"]


def test_a_shot_with_no_take_cannot_be_extended(project, fake):
    json.dump({"jobs": []}, open(os.path.join(project, "jobs.json"), "w"))
    i = E.info(project, "S01-01")
    assert not i["can_extend"] and "no finished take" in i["reason"]


def test_a_lip_synced_take_is_extended_from_the_video_under_it(project, fake):
    jobs = json.load(open(os.path.join(project, "jobs.json")))
    jobs["jobs"].append({**jobs["jobs"][0], "id": "lip", "kind": "lipsync", "source_job": "base", "model": "lip/model", "created": 200, "output": "generations/base.mp4"})
    json.dump(jobs, open(os.path.join(project, "jobs.json"), "w"))
    i = E.info(project, "S01-01")
    assert i["can_extend"] and i["source_take"] == "base" and i["model"] == "test/model" and i["lip_synced"]
    assert any("lip-synced" in a for a in i["advice"])


# ---------------------------------------------------------------- the pieces

def test_last_frame_is_a_real_picture_named_for_the_take(project, fake):
    ref = E.last_frame(project, {"id": "base", "shot_id": "S01-01", "output": "generations/base.mp4"})
    assert ref.startswith("project:media/") and os.path.getsize(os.path.join(project, ref[len("project:"):])) > 500
    assert E.last_frame(project, {"id": "base", "shot_id": "S01-01", "output": "generations/base.mp4"}) == ref


def test_join_makes_one_video_of_both_parts_at_the_originals_size_and_rate(tmp_path):
    a, b = clip(str(tmp_path / "a.mp4"), 3), clip(str(tmp_path / "b.mp4"), 2, size="640x360", rate=30)
    out = E.join(a, b, str(tmp_path / "j.mp4"))
    p = probe(out)
    assert (p["w"], p["h"]) == (320, 180) and abs(p["fps"] - 24) < 0.5
    assert 4.8 < p["duration"] < 5.1                      # 3 s + 2 s, minus the repeated first frame


def test_join_fails_in_plain_words_for_an_unreadable_take(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(SystemExit) as e:
        E.join(str(bad), str(bad), str(tmp_path / "o.mp4"))
    assert "can't be read" in str(e.value) or "Couldn't join" in str(e.value)


# ---------------------------------------------------------------- the whole path

def test_extend_renders_the_missing_seconds_and_joins_them_without_touching_the_original(project, fake):
    seen = {}
    real = R.compile_request

    def spy(shot, *a, **k):
        seen["continues"] = shot.get("continues")
        seen["text"] = real(shot, *a, **k)
        return seen["text"]
    R.compile_request = spy
    try:
        made = R.enqueue(project, ["S01-01"], "fal", "test/model", {"_extend_of": "base", "_extend_seconds": 4})
        assert len(made) == 1 and made[0]["extend_of"] == "base" and made[0]["overrides"]["duration"] == "4"
        R.run(project, poll_every=0)
    finally:
        R.compile_request = real
    jobs = {j["id"]: j for j in R.Store(project).jobs}
    new = next(j for j in jobs.values() if j.get("extend_of"))
    assert new["state"] == "ready", new.get("error")
    assert seen["continues"] is True and "continues straight on" in seen["text"]["prompt"]
    assert fake.sent[0]["duration"] == "4"
    p = probe(os.path.join(project, new["output"]))
    assert 11.5 < p["duration"] < 12.2                     # 8 s + 4 s
    assert os.path.exists(os.path.join(project, new["extension_part"]))
    assert jobs["base"]["output"] == "generations/base.mp4" and probe(os.path.join(project, "generations/base.mp4"))["duration"] < 8.2
    state = json.load(open(os.path.join(project, "shots.json")))
    assert state["S01-01"]["approved"] == "base"          # the take in the video stays until the longer one is swapped in


def test_extension_is_not_double_queued_and_needs_a_finished_take(project, fake):
    with pytest.raises(SystemExit) as e:
        R.enqueue(project, ["S01-01"], "fal", "test/model", {"_extend_of": "nope", "_extend_seconds": 4})
    assert "gone or isn't finished" in str(e.value)
    R.enqueue(project, ["S01-01"], "fal", "test/model", {"_extend_of": "base", "_extend_seconds": 4})
    assert R.enqueue(project, ["S01-01"], "fal", "test/model", {"_extend_of": "base", "_extend_seconds": 4}) == []


def test_a_join_that_fails_keeps_the_billed_clip_and_says_so(project, fake, monkeypatch):
    monkeypatch.setattr(E, "join", lambda *a, **k: (_ for _ in ()).throw(SystemExit("Couldn't join: boom")))
    R.enqueue(project, ["S01-01"], "fal", "test/model", {"_extend_of": "base", "_extend_seconds": 4})
    R.run(project, poll_every=0)
    j = next(x for x in R.Store(project).jobs if x.get("extend_of"))
    assert j["state"] == "failed" and "could not be joined" in j["error"] and "billed" in j["error"]
    assert os.path.exists(os.path.join(project, "generations", "S01-01__" + j["id"] + ".mp4"))
