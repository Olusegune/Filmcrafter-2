"""Security for the sound layers and the layers' undo history: hostile shot and layer names, a settings file or history that arrived inside a project from somewhere else, and
files outside the project that must never be read into a film or written to."""
import json
import os

import numpy as np
import pytest
import soundfile as sf

from filmcrafter_engine import export as E, overlays as O, shotsound as SS
from tests.test_regressions_sound import left_channel
from tests.test_shotsound import exported, level, make_film, tone

pytestmark = pytest.mark.security

HOSTILE_IDS = ["../../evil", "..\\..\\evil", "../x", "S01-01/../../y", "S01-01;rm -rf", "", "con:", "x" * 300, "S01 01", "nope"]
HOSTILE_LAYERS = ["../../x", "..\\x", "all/../../x", "", "song;rm", "ALL", "split", "x" * 300]


def outside(d):
    """Every file under the folder that holds the project but not in the project: nothing may ever appear here."""
    base = os.path.dirname(d)
    return sorted(os.path.join(r, f) for r, _, fs in os.walk(base) for f in fs if not os.path.join(r, f).startswith(d + os.sep))


def project_files(d):
    return sorted(os.path.relpath(os.path.join(r, f), d) for r, _, fs in os.walk(d) for f in fs)


@pytest.mark.parametrize("bad", HOSTILE_IDS)
def test_a_hostile_shot_id_is_refused_and_writes_nothing_anywhere(tmp_path, bad):
    d = make_film(tmp_path)
    before_out, before_in = outside(d), project_files(d)
    for call in (lambda: SS.set_layer(d, bad, "all", on=True), lambda: SS.delete_layer(d, bad, "all"), lambda: SS.restore_layer(d, bad, "all"), lambda: SS.split(d, bad)):
        with pytest.raises(SystemExit):
            call()
    assert SS.get(d, bad)["take"] is None and SS.levels(d, bad)["layers"] == {}
    assert outside(d) == before_out and project_files(d) == before_in             # not even a settings file was created


@pytest.mark.parametrize("bad", HOSTILE_LAYERS)
def test_a_hostile_layer_name_is_refused(tmp_path, bad):
    d = make_film(tmp_path)
    before = outside(d)
    for call in (lambda: SS.set_layer(d, "S01-01", bad, on=True), lambda: SS.delete_layer(d, "S01-01", bad), lambda: SS.restore_layer(d, "S01-01", bad)):
        with pytest.raises(SystemExit):
            call()
    assert outside(d) == before and not os.path.exists(os.path.join(d, "sound.json"))


def test_a_settings_file_cannot_point_the_film_at_a_sound_elsewhere_on_the_computer(tmp_path, tmp_path_factory):
    """A project arrives from someone else (a .pulse or .pfproducer): its sound.json says the 'voices' are a file outside the project. The film must not mix that file in."""
    d = make_film(tmp_path)
    secret = tmp_path_factory.mktemp("elsewhere") / "private.wav"
    tone(str(secret), 3000, 4.0, amp=0.5)                                          # a sound that is not in the project at all
    take = SS.take_for(d, "S01-01")
    key = SS.take_key(d, take)
    for hostile in ({"voice": str(secret), "other": str(secret)}, {"voice": os.path.relpath(str(secret), d), "other": os.path.relpath(str(secret), d)},
                    {"voice": "generations/t1.mp4", "other": "generations/t1.mp4"}, {"voice": "song.wav", "other": "song.wav"}):
        json.dump({"shots": {"S01-01": {"take": key, "split": hostile, "layers": {"voice": {"on": True}, "other": {"on": True}, "all": {"on": True}}}}, "probe": {}},
                  open(os.path.join(d, "sound.json"), "w"))
        g = SS.get(d, "S01-01")
        assert g["split"] is False and [l["id"] for l in g["layers"]] == ["song", "all"], hostile       # treated as not split at all
        x, _ = exported(d)
        assert level(x, 0.3, 1.7, 3000) < 0.02, hostile                                                    # the private sound is not in the film


def test_damaged_numbers_in_a_settings_file_cannot_crash_or_blast_the_mix(tmp_path):
    d = make_film(tmp_path)
    key = SS.take_key(d, SS.take_for(d, "S01-01"))
    for gain in (1e9, -5, "loud", None, [1], {"a": 1}, float("nan"), float("inf")):
        json.dump({"shots": {"S01-01": {"take": key, "layers": {"all": {"on": True, "gain": gain}, "song": {"gain": gain}}}}, "probe": {}}, open(os.path.join(d, "sound.json"), "w"))
        g = SS.get(d, "S01-01")
        for row in g["layers"]:
            assert row["gain"] is None or 0.0 <= row["gain"] <= 2.0, (gain, row)
        x = left_channel(E.build(d, "square")["path"])                             # a channel as stored (a mono downmix of two equal channels would add 3 dB itself)
        assert np.isfinite(x).all() and float(np.abs(x).max()) <= 1.05, (gain, float(np.abs(x).max()))      # the mix is held under full scale; AAC may overshoot a hair


def test_a_settings_file_that_is_not_even_json_is_ignored(tmp_path):
    d = make_film(tmp_path)
    for junk in ("{not json", "[1,2,3]", "null", "\x00\x01", ""):
        open(os.path.join(d, "sound.json"), "w").write(junk)
        assert SS.get(d, "S01-01")["changed"] is False
        SS.set_layer(d, "S01-01", "all", on=True)                                  # and the next real choice replaces the junk
        assert SS.get(d, "S01-01")["changed"] is True
        os.remove(os.path.join(d, "sound.json"))


def test_a_hostile_history_file_cannot_put_anything_but_layers_back(tmp_path):
    """The undo history travels with the project. Undo replays only what the engine itself saved: junk in the file is ignored, and the layers' own file-path checks still apply."""
    d = tmp_path / "p"
    d.mkdir()
    (d / "project.json").write_text(json.dumps({"title": "T"}))
    (d / "songmap.json").write_text(json.dumps({"duration": 30.0, "sections": []}))
    d = str(d)
    O.add(d, {"text": "KEEP", "start": 1, "end": 5})
    os.makedirs(os.path.join(d, "cache"), exist_ok=True)
    json.dump({"undo": ["rm -rf /", 5, None, {"id": "x"}, [1, 2, "a"], [{"id": "ok", "kind": "text", "text": "FROM HISTORY", "start": 1, "end": 2}]], "redo": "no"}, open(O._history_path(d), "w"))
    assert O.history(d)["undo"] == 1
    O.undo(d)
    assert [o.get("text") for o in O.load(d)] == ["FROM HISTORY"]                 # a well-formed snapshot is replayed as a list of layers, nothing else is
    assert not os.path.exists(os.path.join(os.path.dirname(d), "x"))


def test_nothing_the_sound_layers_do_leaves_the_project_folder(tmp_path, monkeypatch):
    from tests.test_shotsound import fake_demucs
    fake_demucs(monkeypatch)
    d = make_film(tmp_path)
    before = outside(d)
    SS.get(d, "S01-01")
    SS.set_layer(d, "S01-01", "all", on=True, gain=1.5)
    SS.split(d, "S01-01")
    SS.delete_layer(d, "S01-01", "other")
    SS.levels(d, "S01-01")
    E.build(d, "square")
    E.build(d, "youtube", (0.0, 2.0))
    SS.reset(d, "S01-01")
    assert outside(d) == before
