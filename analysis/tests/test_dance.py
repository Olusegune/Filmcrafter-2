"""Dance-ready: the beat line in a dance shot's prompt, and the free check that a shot can be danced in."""
import json
import os

import pytest

from filmcrafter_engine import dance as D
from filmcrafter_engine import onboarding as O


def project(tmp_path, shots, choreo=None, bpm=120, **extra):
    d = tmp_path / "p"
    d.mkdir(exist_ok=True)
    json.dump({"title": "T", "song": "song.wav", **extra}, open(d / "project.json", "w"))
    json.dump({"duration": 40, "bpm": bpm, "downbeats": [0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0], "accents": [4.5, 5.0, 9.0],
               "sections": [{"start": 0, "end": 20, "label": "CHORUS"}]}, open(d / "songmap.json", "w"))
    json.dump({"meta": {}, "scenes": [{"number": 1, "heading": "INT.", "shots": shots}]}, open(d / "production.json", "w"))
    json.dump(choreo or {"mode": "ai", "style": "Afrobeats", "notes": "Joyful, grounded.", "files": [], "sections": []}, open(d / "choreography.json", "w"))
    return str(d)


def shot(i, start, end, framing="wide shot", **kw):
    return {"id": f"S01-{i:02d}", "scene": 1, "start": start, "end": end, "framing": framing, "performers": ["Ada"], "description": "Ada dances across the room.", **kw}


# ---------------------------------------------------------------- the beat line
def test_the_beat_line_counts_beats_and_bars_and_says_whether_the_shot_starts_on_the_downbeat(tmp_path):
    d = project(tmp_path, [shot(1, 4.0, 8.0)])
    line = D.beat_line(d, shot(1, 4.0, 8.0))
    assert "8 beats (2 bars) at 120 BPM" in line and "starts on the downbeat" in line
    assert "strong hits at 0.5 s, 1 s in" in line                                              # the accents at 4.5 and 5.0
    assert "starts between downbeats" in D.beat_line(d, shot(1, 4.9, 7.0))


def test_no_beat_line_when_the_tempo_or_the_shot_is_unknown(tmp_path):
    d = project(tmp_path, [shot(1, 4.0, 8.0)], bpm=0)
    assert D.beat_line(d, shot(1, 4.0, 8.0)) is None
    d = project(tmp_path, [shot(1, 4.0, 8.0)])
    assert D.beat_line(d, shot(1, 8.0, 8.0)) is None
    assert D.beat_line(str(tmp_path / "nowhere"), shot(1, 4.0, 8.0)) is None


def test_a_dance_shot_prompt_carries_the_beat_line_but_a_keyframe_does_not(tmp_path):
    d = project(tmp_path, [shot(1, 4.0, 8.0)])
    video = O.movement_for(d, shot(1, 4.0, 8.0), "video")
    assert video.startswith("Choreography") and "Beat: 8 beats (2 bars) at 120 BPM" in video
    assert "Beat:" not in (O.movement_for(d, shot(1, 4.0, 8.0), "image") or "")               # a still has no beat


def test_a_designed_plan_gets_the_beat_line_too(tmp_path):
    plan = {"mode": "ai", "style": "Afrobeats", "plan": {"bpm": 120, "shots": {"S01-01": {"dancing": True, "pose": "arms wide", "motion": "a low bounce", "energy": 7}}}}
    d = project(tmp_path, [shot(1, 4.0, 8.0)], plan)
    v = O.movement_for(d, shot(1, 4.0, 8.0), "video")
    assert "a low bounce" in v and "Beat: 8 beats" in v


def test_a_shot_that_is_not_dancing_gets_no_beat_line(tmp_path):
    d = project(tmp_path, [shot(1, 4.0, 8.0, description="Mercy unrolls the runner.")])
    v = O.movement_for(d, shot(1, 4.0, 8.0, description="Mercy unrolls the runner."), "video")
    assert "Beat:" not in v and "action described above always wins" in v


# ---------------------------------------------------------------- the check
def test_a_good_dance_shot_has_no_issues(tmp_path):
    d = project(tmp_path, [shot(1, 4.0, 8.0)])
    r = D.check(d)
    assert r["dance_shots"] == 1 and r["clean"] == 1 and r["shots"][0]["issues"] == []


@pytest.mark.parametrize("kw,kind", [({"framing": "close-up"}, "close"), ({"framing": "medium close-up on her face"}, "close"), ({"performers": []}, "nobody")])
def test_the_check_names_what_hides_the_dance(tmp_path, kw, kind):
    d = project(tmp_path, [shot(1, 4.0, 8.0, **kw)], {"mode": "ai", "style": "Afrobeats", "notes": "", "files": [], "sections": []})
    kinds = [i["kind"] for r in D.check(d)["shots"] for i in r["issues"]]
    assert kind in kinds


def test_the_check_flags_short_long_and_off_beat_shots_and_says_how_to_fix_them(tmp_path):
    d = project(tmp_path, [shot(1, 4.0, 5.0), shot(2, 6.0, 17.0), shot(3, 8.3, 10.0)])
    by = {r["shot"]: {i["kind"]: i for i in r["issues"]} for r in D.check(d)["shots"]}
    assert "short" in by["S01-01"] and "at least 1.5 s" in by["S01-01"]["short"]["fix"]
    assert "long" in by["S01-02"] and "Split" in by["S01-02"]["long"]["fix"]
    assert "off_beat" in by["S01-03"] and "Move the start of the shot to 8.50 s" in by["S01-03"]["off_beat"]["fix"]
    assert "off_beat" not in by["S01-01"] and "off_beat" not in by["S01-02"]


def test_only_dance_shots_are_checked_and_the_override_is_honoured(tmp_path):
    plain = shot(2, 8.0, 10.0, description="Mercy unrolls the runner.", framing="close-up")
    d = project(tmp_path, [shot(1, 4.0, 8.0), plain])
    assert [r["shot"] for r in D.check(d)["shots"]] == ["S01-01"]
    d = project(tmp_path, [shot(1, 4.0, 8.0), plain], dance_shots={"S01-02": "on", "S01-01": "off"})
    assert [r["shot"] for r in D.check(d)["shots"]] == ["S01-02"]                              # "always" brings a shot in, "never" takes one out


def test_a_project_with_no_dance_or_no_plan_says_what_to_do(tmp_path):
    d = project(tmp_path, [shot(1, 4.0, 8.0, description="She waits.")])
    assert "No shot is a dance shot yet" in D.check(d)["note"]
    empty = tmp_path / "e"
    empty.mkdir()
    assert D.check(str(empty))["shots"] == []


def test_without_a_tempo_the_check_says_it_could_not_compare_with_the_beat(tmp_path):
    d = project(tmp_path, [shot(1, 4.3, 8.0)], bpm=0)
    r = D.check(d)
    assert "tempo is not known" in r["note"] and not any(i["kind"] == "off_beat" for s in r["shots"] for i in s["issues"])


def test_hostile_numbers_do_not_crash_the_check(tmp_path):
    d = project(tmp_path, [shot(1, "soon", None), shot(2, float("nan"), 3)])
    D.check(d)


# ---------------------------------------------------------------- damaged song maps must never hang or crash the dance check

import time as _time

import pytest as _pytest

from filmcrafter_engine import dance as _D


@_pytest.mark.parametrize("bpm", [1e9, 0.0001, -5, "fast", None, float("nan"), float("inf"), 600, 29])
def test_an_impossible_tempo_means_no_grid_and_returns_at_once(bpm):
    t = _time.time()
    b, downs, beats = _D._grid({"bpm": bpm, "duration": 240, "downbeats": [0.5]})
    assert beats == [] and _time.time() - t < 1


def test_a_normal_tempo_still_makes_a_grid_and_a_very_long_duration_is_capped():
    assert len(_D._grid({"bpm": 120, "duration": 10, "downbeats": []})[2]) == 21
    assert len(_D._grid({"bpm": 120, "duration": 1e12})[2]) < 30000


def test_junk_in_the_song_map_and_the_shot_is_ignored_not_fatal():
    assert _D._grid({"bpm": 120, "duration": 10, "downbeats": ["a", 3, None, 1.0]})[1] == [1.0, 3.0]
    issues = _D.check_shot({"start": "a", "end": None, "framing": None, "performers": None}, [])
    assert [i["kind"] for i in issues] == ["nobody"]
    assert _D.beat_line("/no/such/folder", {"start": 1, "end": 2}) is None
