"""Unit tests for the sound layers' own rules: no ffmpeg, no audio, only the logic that decides what is on, how loud, and what a damaged file may do."""
import json
import os
import subprocess

import pytest

from filmcrafter_engine import export as E, overlays as O, shotsound as SS


def take(name="t.mp4", **kw):
    return {"id": "j1", "output": f"generations/{name}", "provider": "fal", "model": "m", "kind": "video", **kw}


@pytest.fixture
def d(tmp_path):
    (tmp_path / "generations").mkdir()
    (tmp_path / "generations" / "t.mp4").write_bytes(b"not really a video: only its name and size matter here")
    return str(tmp_path)


def save(d, shot, layers=None, split=None, key=None):
    s = {"shots": {shot: {"take": key or SS.take_key(d, take()), "layers": layers or {}, **({"split": split} if split else {})}}, "probe": {}}
    json.dump(s, open(os.path.join(d, "sound.json"), "w"))


# ---------------------------------------------------------------- numbers from a file anyone could have edited

@pytest.mark.parametrize("v,want", [(1, 1.0), ("0.5", 0.5), (9, 2.0), (-3, 0.0), (1e9, 2.0), (float("nan"), 1.0), (float("inf"), 1.0), ("loud", 1.0), (None, 1.0), ([1], 1.0), ({}, 1.0)])
def test_a_number_is_finite_and_inside_its_range_or_the_default(v, want):
    assert SS._num(v, 1.0, 0.0, 2.0) == want


def test_a_settings_file_of_the_wrong_shape_loads_as_nothing(d):
    for text in ("[]", "null", '"x"', "{not json", '{"shots": [], "probe": 3}', '{"shots": {"S01": 5, "S02": []}, "probe": {"k": "v"}}'):
        open(os.path.join(d, "sound.json"), "w").write(text)
        assert SS.load(d) == {"shots": {}, "probe": {}}, text


def test_layers_of_the_wrong_type_fall_back_to_their_defaults():
    e = {"layers": {"all": {"on": "yes", "gain": "loud", "removed": 1}, "song": {"gain": float("nan")}}}
    L = SS._layer(e, "all", native=False)
    assert L == {"on": False, "gain": 1.0, "removed": False}                      # only a real True counts
    assert SS._layer(e, "song", native=False)["gain"] is None                    # a damaged song level means "automatic", not a number
    assert SS._layer({"layers": "oops"}, "all", native=False) == {"on": False, "gain": 1.0, "removed": False}
    assert SS._layer({"layers": {"all": {"gain": 99}}}, "all", native=False)["gain"] == 2.0


# ---------------------------------------------------------------- what is on, and how loud the song is under it

def test_by_default_the_models_sound_is_off_and_the_song_is_untouched(d):
    eff = SS.effective(d, "S01-01", take(), native=False)
    assert eff["sources"] == [] and eff["song_gain"] == 1.0 and eff["split"] is None


def test_a_spoken_scene_has_the_models_sound_on_by_default_and_no_song(d):
    eff = SS.effective(d, "S01-01", take(), native=True)
    assert [s[0] for s in eff["sources"]] == ["all"] and eff["song_gain"] == 1.0         # the song is not played there at all, so there is nothing to turn down


def test_the_song_ducks_under_the_models_sound_unless_a_level_was_chosen(d):
    save(d, "S01-01", {"all": {"on": True}})
    assert SS.effective(d, "S01-01", take(), False)["song_gain"] == SS.DUCK
    save(d, "S01-01", {"all": {"on": True}, "song": {"gain": 0.9}})
    assert SS.effective(d, "S01-01", take(), False)["song_gain"] == 0.9
    save(d, "S01-01", {"all": {"on": True}, "song": {"on": False}})
    assert SS.effective(d, "S01-01", take(), False)["song_gain"] == 0.0
    save(d, "S01-01", {"all": {"on": True}, "song": {"removed": True}})
    assert SS.effective(d, "S01-01", take(), False)["song_gain"] == 0.0


def test_a_removed_or_silenced_layer_is_not_a_source(d):
    save(d, "S01-01", {"all": {"on": True, "removed": True}})
    assert SS.effective(d, "S01-01", take(), False)["sources"] == []
    save(d, "S01-01", {"all": {"on": True, "gain": 0.0}})
    assert SS.effective(d, "S01-01", take(), False)["sources"] == []


def test_a_take_known_to_have_no_sound_adds_nothing_and_does_not_duck_the_song(d):
    k = SS.take_key(d, take())
    s = {"shots": {"S01-01": {"take": k, "layers": {"all": {"on": True}}}}, "probe": {k: {"has_audio": False, "rms": 0.0, "seconds": 2.0}}}
    json.dump(s, open(os.path.join(d, "sound.json"), "w"))
    eff = SS.effective(d, "S01-01", take(), False)
    assert eff["sources"] == [] and eff["song_gain"] == 1.0


def test_settings_made_for_another_take_are_not_used(d):
    save(d, "S01-01", {"all": {"on": True}}, key="a-different-take")
    assert SS.effective(d, "S01-01", take(), False)["sources"] == []


def test_a_take_key_changes_when_the_file_does(d):
    a = SS.take_key(d, take())
    p = os.path.join(d, "generations", "t.mp4")
    open(p, "ab").write(b"more")
    assert SS.take_key(d, take()) != a


def test_only_a_video_models_take_has_sound(d):
    assert SS._is_video(take()) and not SS._is_video(take(provider="own")) and not SS._is_video(take(media_kind="image")) and not SS._is_video(take("x.png")) and not SS._is_video(None)


# ---------------------------------------------------------------- the separated sounds must be this project's own files

def test_a_split_that_points_outside_the_projects_sound_cache_is_ignored(d, tmp_path_factory):
    out = tmp_path_factory.mktemp("elsewhere") / "secret.wav"
    out.write_bytes(b"RIFF")
    cache = os.path.join(d, "cache", "sound", "k")
    os.makedirs(cache)
    inside = os.path.join(cache, "voice.wav")
    open(inside, "wb").write(b"RIFF")
    open(os.path.join(cache, "other.wav"), "wb").write(b"RIFF")
    good = {"voice": "cache/sound/k/voice.wav", "other": "cache/sound/k/other.wav"}
    assert SS._split_files(d, {"split": good}) == good
    for bad in ({"voice": str(out), "other": "cache/sound/k/other.wav"}, {"voice": "../../secret.wav", "other": "cache/sound/k/other.wav"},
                {"voice": "cache/sound/k/../../../generations/t.mp4", "other": "cache/sound/k/other.wav"}, {"voice": "cache/sound", "other": "cache/sound/k/other.wav"},
                {"voice": "cache/sound/k/missing.wav", "other": "cache/sound/k/other.wav"}, {"voice": 5, "other": None}, {"voice": "cache/sound/k/voice.wav"}, "oops", []):
        assert SS._split_files(d, {"split": bad}) is None, bad


# ---------------------------------------------------------------- the loudness reading

SUMMARY = """  Integrated loudness:
    I:         {i} LUFS
    Threshold: -33.0 LUFS

  Loudness range:
    LRA:         5.3 LU

  True peak:
    Peak:       -1.2 dBFS
"""


def fake_ffmpeg(monkeypatch, stderr):
    monkeypatch.setattr(E.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", stderr))
    monkeypatch.setattr(E, "ffmpeg", lambda: "ffmpeg")


def test_the_loudness_reading_is_taken_from_the_summary(monkeypatch):
    fake_ffmpeg(monkeypatch, "noise\n[Parsed_ebur128_0] Summary:\n\n" + SUMMARY.format(i="-14.2"))
    assert E.measure_loudness("x.mp4") == {"lufs": -14.2, "range_lu": 5.3, "true_peak_db": -1.2}


def test_a_silent_or_unreadable_film_has_no_loudness(monkeypatch):
    fake_ffmpeg(monkeypatch, "Summary:\n\n" + SUMMARY.format(i="-70.0"))
    assert E.measure_loudness("x.mp4") is None
    fake_ffmpeg(monkeypatch, "Summary:\n\n" + SUMMARY.format(i="-inf"))
    assert E.measure_loudness("x.mp4") is None
    fake_ffmpeg(monkeypatch, "no summary here")
    assert E.measure_loudness("x.mp4") is None


# ---------------------------------------------------------------- the layers' undo history

def test_the_undo_history_ignores_anything_that_is_not_a_list_of_layers(tmp_path):
    d = str(tmp_path)
    os.makedirs(os.path.join(d, "cache"))
    for text in ('{"undo": 5, "redo": "x"}', '{"undo": [1, "a", null, [1, 2], [{"id": "ok"}]], "redo": [{"id": "not a list"}]}', "[]", "null", "{bad"):
        open(O._history_path(d), "w").write(text)
        h = O._history(d)
        assert h["redo"] == [] and all(isinstance(x, list) and all(isinstance(o, dict) for o in x) for x in h["undo"]), text
    open(O._history_path(d), "w").write('{"undo": [1, [{"id": "ok"}], [3]], "redo": []}')
    assert O._history(d)["undo"] == [[{"id": "ok"}]]
