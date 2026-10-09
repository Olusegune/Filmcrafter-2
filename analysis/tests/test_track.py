"""How each model has done in this project: counted from what was recorded, nothing invented."""
import json
import os

import pytest

from filmcrafter_engine import track as T


def job(i, model="seedance-2", state="ready", **kw):
    return {"id": f"j{i}", "shot_id": f"S01-{i:02d}", "plan": "production", "provider": "kie", "model": model, "kind": "video", "state": state, "created": i, "cost": 0.5, "cost_unit": "usd", **kw}


def test_takes_failures_and_cost_are_counted_per_model():
    r = T.tally([job(1), job(2), job(3, state="failed", error_kind="service"), job(4, state="failed", error_kind="credits"), job(5, state="failed", error_kind="service"), job(6, model="kling")])
    m = r["kie|seedance-2"]
    assert (m["takes"], m["failed"], m["cost"]) == (2, 3, 1.0) and m["failures"] == {"service": 2, "credits": 1}
    assert r["kie|kling"]["takes"] == 1


def test_only_finished_paid_video_takes_count():
    r = T.tally([job(1, state="queued"), job(2, state="submitting"), job(3, kind="image"), job(4, media_kind="image"), job(5, provider="own"), job(6, model="")])
    assert r == {}


def test_review_and_sound_verdicts_are_tallied_and_only_ready_takes_count_for_them():
    r = T.tally([job(1, review={"verdict": "good"}, audio_timing={"verdict": "in_time"}), job(2, review={"verdict": "needs_attention"}, audio_timing={"verdict": "own_audio"}),
                 job(3, audio_timing={"verdict": "in_time"}), job(4, state="failed", audio_timing={"verdict": "in_time"})])
    m = r["kie|seedance-2"]
    assert m["reviews"] == {"good": 1, "needs_attention": 1} and m["sound"] == {"in_time": 2, "own_audio": 1} and m["sung"] == 3


@pytest.mark.parametrize("cost,unit,expect", [(0.5, "credits", 0.0), ("soon", "usd", 0.0), (float("nan"), "usd", 0.0), (None, "usd", 0.0), (2, None, 2.0)])
def test_cost_counts_only_real_dollar_amounts(cost, unit, expect):
    assert T.tally([job(1, cost=cost, cost_unit=unit)])["kie|seedance-2"]["cost"] == expect


def test_junk_records_do_not_crash():
    assert T.tally([None, 5, "x", {}, {"model": "m", "kind": "video"}, {"model": "m", "state": "ready", "review": "good", "audio_timing": "x"}])["|m"]["takes"] == 1


def test_a_project_with_no_renders_has_no_rows(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    assert T.stats(str(d), check=False) == {"models": [], "checked_now": 0}


def test_busiest_model_comes_first(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    json.dump({"jobs": [job(1, model="a"), job(2, model="b"), job(3, model="b"), job(4, model="b", state="failed")]}, open(d / "jobs.json", "w"))
    assert [m["model"] for m in T.stats(str(d), check=False)["models"]] == ["b", "a"]


def test_the_sound_check_runs_on_unchecked_sung_takes_only_and_is_limited(tmp_path):
    from tests.test_lipsync_timing import project_with_take, vocal
    d = project_with_take(tmp_path, vocal(5.0)[: 5 * 8000])
    json.dump({"meta": {}, "scenes": [{"number": 1, "heading": "INT.", "shots": [{"id": "S01-01", "start": 2.0, "end": 7.0, "performers": ["Ada"], "framing": "close-up", "beats": ["She sings."], "description": "She sings."}]}]}, open(os.path.join(d, "production.json"), "w"))
    json.dump({"duration": 20, "lyrics": [{"text": "la la la", "start": 2.0, "end": 7.0}], "sections": []}, open(os.path.join(d, "songmap.json"), "w"))
    json.dump({"title": "T", "song": "song.wav"}, open(os.path.join(d, "project.json"), "w"))
    json.dump({"jobs": [{"id": "t1", "shot_id": "S01-01", "plan": "production", "provider": "kie", "model": "m", "kind": "video", "state": "ready", "output": "generations/t.mp4", "created": 1, "updated": 1, "cost": 1.0, "cost_unit": "usd"}]}, open(os.path.join(d, "jobs.json"), "w"))
    assert T.check_sound(d, limit=0) == 0
    assert T.check_sound(d) == 1
    assert T.check_sound(d) == 0                                                              # already checked: not repeated
    got = json.load(open(os.path.join(d, "jobs.json")))["jobs"][0]
    assert got["audio_timing"]["verdict"] in ("in_time", "late", "early", "loose", "own_audio", "no_audio", "no_vocal")


def test_the_engine_and_the_app_agree_on_the_action_name():
    lib = open(os.path.join(os.path.dirname(__file__), "..", "..", "src-tauri", "src", "lib.rs"), encoding="utf-8").read()
    assert "async fn track(" in lib and "filmcrafter_engine.track" in lib and 'action != "stats"' in lib
    assert 'choices=["stats"]' in open(T.__file__, encoding="utf-8").read()
