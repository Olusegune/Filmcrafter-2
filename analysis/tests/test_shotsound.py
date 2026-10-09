"""Sound layers: a take's own sound kept apart from its picture, switched on, turned down, deleted or split per shot, and mixed under the film at export
without rendering anything again. The song is 220 Hz, the take's whole sound 1000 Hz, its 'voice' 500 Hz and its 'effects' 2000 Hz, so the film's mix can be
read back by frequency."""
import json
import os
import subprocess

import numpy as np
import pytest
import soundfile as sf

from filmcrafter_engine import export as E, shotsound as SS

pytestmark = pytest.mark.integration

RATE = 44100


def tone(path, freq, secs, amp=0.3):
    t = np.linspace(0, secs, int(RATE * secs), endpoint=False)
    sf.write(path, (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32), RATE)


def clip(path, secs, freq):
    cmd = [E.ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=gray:s=160x90:r=24:d={secs}"]
    if freq:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency={freq}:duration={secs}", "-c:a", "aac", "-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", path]
    subprocess.run(cmd, check=True, creationflags=E.NO_WINDOW)


def level(x, t0, t1, freq):
    """How much of `freq` is in x between t0 and t1 (0..1 of full scale)."""
    seg = x[int(t0 * RATE): int(t1 * RATE)]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) / (len(seg) / 4)
    k = int(round(freq * len(seg) / RATE))
    return float(spec[max(0, k - 2): k + 3].max())


def make_film(tmp_path):
    """Two 2 s shots on a 4 s, 220 Hz song: shot 1's take has a 1000 Hz sound, shot 2's has none. Shared by the other sound test files."""
    d = tmp_path / "film"
    (d / "generations").mkdir(parents=True)
    shots = [{"id": "S01-01", "scene": 1, "number": 1, "start": 0.0, "end": 2.0, "beats": ["a"], "performers": []},
             {"id": "S01-02", "scene": 1, "number": 2, "start": 2.0, "end": 4.0, "beats": ["b"], "performers": []}]
    json.dump({"scenes": [{"number": 1, "heading": "INT. ROOM", "start": 0, "end": 4, "shots": shots}]}, open(d / "production.json", "w"))
    json.dump({"title": "T", "song": "song.wav"}, open(d / "project.json", "w"))
    json.dump({"duration": 4.0, "lyrics": [], "sections": []}, open(d / "songmap.json", "w"))
    tone(str(d / "song.wav"), 220, 4.0)
    clip(str(d / "generations" / "t1.mp4"), 2.0, 1000)       # a take with sound
    clip(str(d / "generations" / "t2.mp4"), 2.0, None)       # a take with none
    jobs = [{"id": f"j{i}", "shot_id": f"S01-0{i}", "plan": "production", "state": "ready", "output": f"generations/t{i}.mp4", "created": i, "kind": "video",
             "provider": "fal", "model": "test/talker"} for i in (1, 2)]
    json.dump({"jobs": jobs}, open(d / "jobs.json", "w"))
    return str(d)


@pytest.fixture
def film(tmp_path):
    return make_film(tmp_path)


def exported(d, window=None):
    r = E.build(d, "square", window)
    return SS.decode(r["path"], 1)[:, 0], r


def fake_demucs(monkeypatch):
    """Stands in for Demucs: 'voice' is a 500 Hz tone, everything else 2000 Hz."""
    def run(mix, out, device):
        base = os.path.join(out, "htdemucs", "mix")
        os.makedirs(base, exist_ok=True)
        tone(os.path.join(base, "vocals.wav"), 500, 2.0)
        tone(os.path.join(base, "no_vocals.wav"), 2000, 2.0)
    monkeypatch.setattr(SS, "_demucs", run)


def test_a_take_starts_with_its_sound_off_and_the_film_is_just_the_song(film):
    g = SS.get(film, "S01-01")
    assert g["has_audio"] and [l["id"] for l in g["layers"]] == ["song", "all"]
    assert [l["on"] for l in g["layers"]] == [True, False]
    x, r = exported(film)
    assert level(x, 0.3, 1.7, 220) > 0.15 and level(x, 0.3, 1.7, 1000) < 0.02
    assert "shot_sound" not in r


def test_switching_a_takes_sound_on_mixes_it_into_that_shot_only_and_turns_the_song_down(film):
    SS.set_layer(film, "S01-01", "all", on=True)
    x, r = exported(film)
    assert level(x, 0.3, 1.7, 1000) > 0.1                                   # the take's sound is there under shot 1
    assert level(x, 0.3, 1.7, 220) < level(x, 2.3, 3.7, 220) * 0.6          # the song ducks under it
    assert level(x, 2.3, 3.7, 1000) < 0.02                                  # shot 2 has no take sound: the song alone
    assert r["shot_sound"] == 1


def test_deleting_the_layer_takes_it_out_and_restoring_brings_it_back(film):
    SS.set_layer(film, "S01-01", "all", on=True)
    g = SS.delete_layer(film, "S01-01", "all")
    assert g["layers"][1]["removed"] and not g["layers"][1]["on"]
    x, _ = exported(film)
    assert level(x, 0.3, 1.7, 1000) < 0.02 and level(x, 0.3, 1.7, 220) > 0.15      # and the song is back to full
    SS.restore_layer(film, "S01-01", "all")
    x, _ = exported(film)
    assert level(x, 0.3, 1.7, 1000) > 0.1


def test_the_volume_of_a_layer_and_of_the_song_can_be_set(film):
    SS.set_layer(film, "S01-01", "all", on=True, gain=0.5)
    quiet, _ = exported(film)
    SS.set_layer(film, "S01-01", "all", gain=1.5)
    loud, _ = exported(film)
    assert level(loud, 0.3, 1.7, 1000) > level(quiet, 0.3, 1.7, 1000) * 1.5
    SS.set_layer(film, "S01-01", "song", gain=1.0)                                # an explicit level beats the automatic ducking
    x, _ = exported(film)
    assert level(x, 0.3, 1.7, 220) > 0.15


def test_the_song_can_be_turned_off_under_a_shot(film):
    SS.set_layer(film, "S01-02", "song", on=False)
    x, _ = exported(film)
    assert level(x, 2.3, 3.7, 220) < 0.01 and level(x, 0.3, 1.7, 220) > 0.15


def test_splitting_gives_voices_and_effects_that_can_be_chosen_apart(film, monkeypatch):
    fake_demucs(monkeypatch)
    g = SS.split(film, "S01-01")
    assert g["split"] and [l["id"] for l in g["layers"]] == ["song", "voice", "other"] and all(l["on"] for l in g["layers"])
    SS.delete_layer(film, "S01-01", "other")                                       # keep the voices, lose the effects
    x, _ = exported(film)
    assert level(x, 0.3, 1.7, 500) > 0.05 and level(x, 0.3, 1.7, 2000) < 0.02 and level(x, 0.3, 1.7, 1000) < 0.02
    SS.restore_layer(film, "S01-01", "other")
    SS.set_layer(film, "S01-01", "voice", on=False)                                # and the other way round
    x, _ = exported(film)
    assert level(x, 0.3, 1.7, 2000) > 0.05 and level(x, 0.3, 1.7, 500) < 0.02


def test_a_split_is_remembered_and_not_redone(film, monkeypatch):
    calls = []
    fake_demucs(monkeypatch)
    real = SS._demucs
    monkeypatch.setattr(SS, "_demucs", lambda *a: (calls.append(1), real(*a)))
    SS.split(film, "S01-01")
    SS.reset(film, "S01-01")
    SS.split(film, "S01-01")
    assert len(calls) == 1


def test_a_different_take_starts_fresh(film, monkeypatch):
    fake_demucs(monkeypatch)
    SS.split(film, "S01-01")
    clip(os.path.join(film, "generations", "t1b.mp4"), 2.0, 1500)
    jobs = json.load(open(os.path.join(film, "jobs.json")))
    jobs["jobs"].append({"id": "j9", "shot_id": "S01-01", "plan": "production", "state": "ready", "output": "generations/t1b.mp4", "created": 9, "kind": "video",
                         "provider": "fal", "model": "test/talker"})
    json.dump(jobs, open(os.path.join(film, "jobs.json"), "w"))
    g = SS.get(film, "S01-01")
    assert not g["split"] and [l["id"] for l in g["layers"]] == ["song", "all"] and not g["layers"][1]["on"]


def test_a_take_with_no_sound_has_nothing_to_split_or_mix(film):
    g = SS.get(film, "S01-02")
    assert not g["has_audio"] and g["silent"]
    with pytest.raises(SystemExit, match="no audible sound"):
        SS.split(film, "S01-02")
    SS.set_layer(film, "S01-02", "all", on=True)
    x, _ = exported(film)
    assert level(x, 2.3, 3.7, 220) > 0.15                                           # nothing to add, so no ducking either


def test_a_preview_has_the_same_sound_for_its_part_of_the_film(film):
    SS.set_layer(film, "S01-02", "all", on=True)                                    # shot 2 has no sound: shot 1's is the one to hear
    SS.set_layer(film, "S01-01", "all", on=True)
    x, r = exported(film, (0.5, 1.5))
    assert r["preview"] and level(x, 0.1, 0.9, 1000) > 0.1


def test_a_native_scene_keeps_the_models_sound_and_a_shot_can_be_silenced(film):
    json.dump({"lines": [], "native": True}, open(os.path.join(film, "dialogue.json"), "w"))
    x, r = exported(film)
    assert r["native_sound"] == 1 and level(x, 0.3, 1.7, 1000) > 0.1 and level(x, 0.3, 1.7, 220) < 0.01
    SS.delete_layer(film, "S01-01", "all")
    x, _ = exported(film)
    assert level(x, 0.3, 1.7, 1000) < 0.02


def test_a_picture_or_your_own_clip_has_no_model_sound(film):
    jobs = json.load(open(os.path.join(film, "jobs.json")))
    jobs["jobs"][0]["provider"] = "own"
    json.dump(jobs, open(os.path.join(film, "jobs.json"), "w"))
    g = SS.get(film, "S01-01")
    assert g["layers"] == [] and "your own clips" in g["note"]


def test_unknown_shots_and_layers_are_refused(film):
    with pytest.raises(SystemExit, match="no video take"):
        SS.set_layer(film, "S99-99", "all", on=True)
    with pytest.raises(SystemExit, match="Unknown"):
        SS.set_layer(film, "S01-01", "../../x", on=True)
    with pytest.raises(SystemExit, match="Split"):
        SS.set_layer(film, "S01-01", "voice", on=True)


def test_the_command_line_answers_in_json(film, capsys):
    assert SS.main(["get", film, "--data", json.dumps({"shot": "S01-01"})]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["event"] == "result" and out["data"]["shot"] == "S01-01"
    assert SS.main(["set", film, "--data", json.dumps({"shot": "S01-01", "layer": "nope"})]) == 1
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["event"] == "error"


def test_the_real_separator_runs_on_a_take(film):
    pytest.importorskip("demucs")
    g = SS.split(film, "S01-01")
    assert g["split"]
    work = os.path.join(film, "cache", "sound", SS.take_key(film, SS.take_for(film, "S01-01")))
    for n in ("voice.wav", "other.wav"):
        assert os.path.getsize(os.path.join(work, n)) > 1000


def test_a_shot_is_only_marked_changed_once_something_was_set(film):
    assert SS.get(film, "S01-01")["changed"] is False
    assert SS.overview(film) == {}
    SS.set_layer(film, "S01-01", "all", on=True)
    assert SS.get(film, "S01-01")["changed"] is True
    assert SS.overview(film) == {"S01-01": True}
    assert SS.reset(film, "S01-01")["changed"] is False


# ---------------------------------------------------------------- how loud things are

def test_levels_tell_how_loud_each_layer_is_under_the_shot(film):
    g = SS.levels(film, "S01-01")
    assert g["seconds"] == 2.0 and g["layers"]["song"] is not None and g["layers"]["all"] is None       # the take's own sound is off: only the song
    assert -14 < g["layers"]["song"] < -10                                                              # a 0.3 sine is about -13.5 dB RMS
    SS.set_layer(film, "S01-01", "all", on=True)
    g = SS.levels(film, "S01-01")
    assert g["layers"]["all"] is not None and g["layers"]["song"] < -13.5 - 6                           # the song is turned down under it (40% is -8 dB)
    assert -26 < g["layers"]["all"] < -20                                                               # the take is brought to about -22 dB
    assert g["mix_db"] is not None and g["peak_db"] is not None and g["peak_db"] > g["mix_db"]


def test_a_layer_set_to_double_is_about_six_decibels_louder(film):
    SS.set_layer(film, "S01-01", "all", on=True, gain=1.0)
    a = SS.levels(film, "S01-01")["layers"]["all"]
    SS.set_layer(film, "S01-01", "all", gain=2.0)
    b = SS.levels(film, "S01-01")["layers"]["all"]
    assert 5.5 < b - a < 6.5


def test_levels_of_a_take_with_no_sound_or_no_take_are_empty(film):
    SS.set_layer(film, "S01-02", "all", on=True)
    assert SS.levels(film, "S01-02")["layers"]["all"] is None
    assert SS.levels(film, "S99-99")["layers"] == {} and SS.levels(film, "S99-99")["mix_db"] is None


def test_the_levels_of_a_split_take_are_per_part(film, monkeypatch):
    fake_demucs(monkeypatch)
    SS.split(film, "S01-01")
    g = SS.levels(film, "S01-01")
    assert set(g["layers"]) == {"song", "voice", "other"} and g["layers"]["voice"] is not None and g["layers"]["other"] is not None
    SS.delete_layer(film, "S01-01", "other")
    assert SS.levels(film, "S01-01")["layers"]["other"] is None


def test_the_exported_film_reports_its_loudness(film):
    _, r = exported(film)
    L = r["loudness"]
    assert L is not None and -20 < L["lufs"] < -10 and L["true_peak_db"] is not None            # a 0.3 sine song
    quiet = film + "_q"
    import shutil
    shutil.copytree(film, quiet)
    tone(os.path.join(quiet, "song.wav"), 220, 4.0, amp=0.03)
    shutil.rmtree(os.path.join(quiet, "cache"), ignore_errors=True)
    _, rq = exported(quiet)
    assert 17 < L["lufs"] - rq["loudness"]["lufs"] < 23                                         # a tenth of the amplitude is 20 dB quieter


def test_a_silent_film_has_no_loudness(tmp_path):
    from filmcrafter_engine.export import measure_loudness
    p = str(tmp_path / "s.wav")
    sf.write(p, np.zeros(RATE * 2, dtype=np.float32), RATE)
    assert measure_loudness(p) is None
