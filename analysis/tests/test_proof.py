"""Proving a video model from a take you already have: the measure, the verdict, what is remembered, and that the screen cannot claim a result."""
import json
import os
import subprocess

import pytest
from PIL import Image

from pulseframe_analysis import frames as FR, proof as PR
from pulseframe_analysis.export import ffmpeg


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def video(path, hex_colour):
    p = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x{hex_colour}:size=64x36:rate=12:duration=2", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path)],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


def make(tmp_path, take_colour="C80000", end_colour=(200, 0, 0), start_colour=(20, 20, 20), model="hailuo/new-model", with_end=True):
    d = tmp_path / "p"
    (d / "media").mkdir(parents=True)
    (d / "generations").mkdir()
    shot = {"id": "S01-01", "scene": 1, "number": 1, "start": 0.0, "end": 4.0, "beats": ["b"], "performers": [], "framing": "wide", "camera_moves": [], "source_shots": ["S01-01"]}
    (d / "production.json").write_text(json.dumps({"meta": {}, "characters": [], "scenes": [{"number": 1, "heading": "INT.", "start": 0, "end": 4, "notes": {}, "shots": [shot]}]}))
    (d / "project.json").write_text(json.dumps({"title": "T", "song": "s.wav", "aspect_ratio": "16:9"}))
    (d / "songmap.json").write_text(json.dumps({"duration": 4.0, "lyrics": [], "sections": [], "beats": []}))
    Image.new("RGB", (64, 36), start_colour).save(d / "media" / "kf.png")
    Image.new("RGB", (64, 36), end_colour).save(d / "media" / "end.png")
    (d / "keyframes.json").write_text(json.dumps({"production": {"S01-01": "project:media/kf.png"}}))
    if with_end:
        (d / "shots.json").write_text(json.dumps({"S01-01": {"end_mode": "own"}}))
        (d / "endframes.json").write_text(json.dumps({"production": {"S01-01": "project:media/end.png"}}))
    video(d / "generations" / "t1.mp4", take_colour)
    take = {"id": "t1", "shot_id": "S01-01", "plan": "production", "provider": "kie", "model": model, "kind": "video", "state": "ready", "output": "generations/t1.mp4",
            "overrides": {}, "fix_notes": [], "created": 100, "updated": 130, "attempts": 1, "provider_job_id": "r0", "error": None, "cost": None, "shot_start": 0, "shot_end": 4}
    (d / "jobs.json").write_text(json.dumps({"jobs": [take]}))
    return str(d)


# ---------------------------------------------------------------- the verdict

def test_the_verdict_from_the_two_distances():
    assert PR.verdict(21.0, 1.9) == "landed"            # the Hailuo 02 numbers in docs/END_FRAMES.md
    assert PR.verdict(19.8, 3.3) == "landed"
    assert PR.verdict(20.0, 18.0) == "missed"           # barely nearer the end
    assert PR.verdict(40.0, 15.0) == "missed"           # nearer, but not close
    assert PR.verdict(2.0, 0.5) == "unclear"            # start and end look alike: nothing is shown


def test_the_difference_is_zero_for_the_same_picture_and_large_for_opposites(tmp_path):
    Image.new("RGB", (80, 45), (255, 255, 255)).save(tmp_path / "w.png")
    Image.new("RGB", (30, 20), (255, 255, 255)).save(tmp_path / "w2.png")
    Image.new("RGB", (80, 45), (0, 0, 0)).save(tmp_path / "k.png")
    assert PR.difference(str(tmp_path / "w.png"), str(tmp_path / "w2.png")) == 0
    assert PR.difference(str(tmp_path / "w.png"), str(tmp_path / "k.png")) == 255


# ---------------------------------------------------------------- checking a take

def test_a_take_that_lands_on_its_end_picture(tmp_path):
    r = PR.check(make(tmp_path), "S01-01")
    assert r["ok"] and r["verdict"] == "landed" and r["end_diff"] < r["start_diff"] * 0.5 and r["model"] == "hailuo/new-model" and r["proven"] is False


def test_a_take_that_misses_its_end_picture(tmp_path):
    r = PR.check(make(tmp_path, end_colour=(0, 0, 200)), "S01-01")
    assert r["ok"] and r["verdict"] == "missed"


def test_a_shot_without_an_end_picture_or_a_take_says_why(tmp_path):
    assert "start and an end" in PR.check(make(tmp_path, with_end=False), "S01-01")["reason"]
    d = make(tmp_path / "x")
    os.remove(os.path.join(d, "generations", "t1.mp4"))
    assert "no finished video take" in PR.check(d, "S01-01")["reason"]


# ---------------------------------------------------------------- remembering a model

def test_marking_a_model_proven_makes_the_warning_go_away(tmp_path):
    d = make(tmp_path)
    assert FR.is_proven("kie", "hailuo/new-model") is False
    rep = PR.record(d, "S01-01", "looked right")
    assert [(r["provider"], r["model"]) for r in rep["yours"]] == [("kie", "hailuo/new-model")] and rep["yours"][0]["note"] == "looked right"
    assert PR.is_proven("kie", "hailuo/new-model") and FR.is_proven("kie", "hailuo/new-model")
    assert PR.check(d, "S01-01")["proven"] is True


def test_the_built_in_models_are_proven_without_a_record():
    p, m = sorted(FR.PROVEN_END)[0]
    assert PR.is_proven(p, m) and PR.report()["yours"] == [] and len(PR.report()["built_in"]) == len(FR.PROVEN_END)


def test_a_take_that_missed_cannot_be_recorded(tmp_path):
    with pytest.raises(SystemExit, match="did not land"):
        PR.record(make(tmp_path, end_colour=(0, 0, 200)), "S01-01")
    assert PR.report()["yours"] == []


def test_a_shot_that_cannot_be_checked_cannot_be_recorded(tmp_path):
    with pytest.raises(SystemExit, match="start and an end"):
        PR.record(make(tmp_path, with_end=False), "S01-01")


def test_recording_twice_keeps_one_entry_and_forgetting_removes_it(tmp_path):
    d = make(tmp_path)
    PR.record(d, "S01-01")
    assert len(PR.record(d, "S01-01")["yours"]) == 1
    assert PR.forget("kie", "hailuo/new-model")["yours"] == [] and not PR.is_proven("kie", "hailuo/new-model")


def test_a_damaged_or_hostile_record_file_is_ignored(tmp_path):
    os.makedirs(os.path.dirname(PR.store_path()))
    open(PR.store_path(), "w").write("{not json")
    assert PR.report()["yours"] == []
    json.dump([{"provider": "kie", "model": "../../etc/passwd\n"}, {"provider": 5, "model": "x"}, "junk", {"provider": "kie", "model": "ok/model"}], open(PR.store_path(), "w"))
    assert [(r["provider"], r["model"]) for r in PR.report()["yours"]] == [("kie", "ok/model")]
    json.dump({"not": "a list"}, open(PR.store_path(), "w"))
    assert PR.report()["yours"] == []


def test_a_model_name_that_is_not_a_plain_name_is_not_recorded(tmp_path):
    d = make(tmp_path, model="bad name\nwith newline")
    with pytest.raises(SystemExit, match="doesn't name its model"):
        PR.record(d, "S01-01")


def test_the_note_is_cleaned_and_short(tmp_path):
    rep = PR.record(make(tmp_path), "S01-01", "a\x00b\n" + "n" * 500)
    assert "\n" not in rep["yours"][0]["note"] and len(rep["yours"][0]["note"]) <= 200
