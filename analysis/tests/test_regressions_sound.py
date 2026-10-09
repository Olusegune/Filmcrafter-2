"""Regression: bugs found while the sound layers were built and checked, each kept from coming back. The real detail is in the comments."""
import json
import os

import numpy as np
import pytest
import soundfile as sf

from pulseframe_analysis import export as E, shotsound as SS
from tests.test_shotsound import RATE, exported, level, make_film, tone

pytestmark = pytest.mark.regression


def rms_db(x):
    return 20 * np.log10(float(np.sqrt(np.mean(np.square(x)))))


def left_channel(path):
    """The left channel exactly as stored, read by ffmpeg itself and not by the engine's own decoder (a test that used the engine's decoder would share its bug)."""
    import subprocess
    r = subprocess.run([E.ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", path, "-vn", "-af", "pan=mono|c0=c0", "-f", "f32le", "-ar", str(RATE), "-"], capture_output=True, check=True,
                       creationflags=E.NO_WINDOW)
    return np.frombuffer(r.stdout, dtype=np.float32)


def test_a_mono_song_keeps_its_level_when_it_is_decoded_for_the_mix(tmp_path):
    """ffmpeg's own mono-to-stereo upmix takes 3 dB off, so a mono song came out of the sound mix quieter than it went in. Found when a 0.3 tone read -16.5 dB instead of -13.5."""
    p = str(tmp_path / "mono.wav")
    tone(p, 220, 2.0, amp=0.3)
    mono = SS.decode(p, 1)
    both = SS.decode(p, 2)
    assert abs(rms_db(both[:, 0]) - rms_db(mono[:, 0])) < 0.1 and abs(rms_db(both[:, 1]) - rms_db(mono[:, 0])) < 0.1
    assert np.allclose(both[:, 0], both[:, 1])                                       # the same sound in both ears


def test_a_stereo_file_is_not_changed_by_the_mono_fix(tmp_path):
    p = str(tmp_path / "st.wav")
    t = np.arange(RATE * 2) / RATE
    sf.write(p, np.stack([0.3 * np.sin(2 * np.pi * 220 * t), 0.1 * np.sin(2 * np.pi * 330 * t)], axis=1).astype(np.float32), RATE)
    x = SS.decode(p, 2)
    assert abs(rms_db(x[:, 0]) - rms_db(0.3 * np.sin(2 * np.pi * 220 * t) + 1e-9)) < 0.2 and rms_db(x[:, 0]) > rms_db(x[:, 1]) + 8


def test_the_song_under_a_shot_nobody_touched_stays_at_full_level_in_the_mix(tmp_path):
    """The same bug seen from the film: with the model's sound on for shot 1, the song under shot 2 was 3 dB down. The old test only asked for 'not quiet' (> 0.15 of a 0.3 tone)."""
    d = make_film(tmp_path)
    left = lambda r: left_channel(r["path"])
    plain = left(E.build(d, "square"))
    SS.set_layer(d, "S01-01", "all", on=True)
    mixed = left(E.build(d, "square"))
    a, b = level(plain, 2.3, 3.7, 220), level(mixed, 2.3, 3.7, 220)
    assert abs(20 * np.log10(b / a)) < 0.5, (a, b)


def test_a_shot_nothing_was_changed_on_is_not_marked_changed(tmp_path):
    """The screen offered 'Back to how it was' on a shot that had never been touched, because the whole sound is off by default and 'off' looked like a change."""
    d = make_film(tmp_path)
    assert SS.get(d, "S01-01")["changed"] is False
    SS.set_layer(d, "S01-01", "all", on=True)
    assert SS.get(d, "S01-01")["changed"] is True
    SS.set_layer(d, "S01-01", "all", on=False)                                       # turning it back off is still a recorded choice
    assert SS.get(d, "S01-01")["changed"] is True
    assert SS.reset(d, "S01-01")["changed"] is False


def test_nothing_changed_means_the_song_file_itself_is_used(tmp_path):
    """The export must not re-encode or re-level a song nobody touched: the mixer steps aside and the film is built from the song file as it is."""
    d = make_film(tmp_path)
    items = [{"shot": "S01-01", "start": 0.0, "end": 2.0, "take": SS.take_for(d, "S01-01")}, {"shot": "S01-02", "start": 2.0, "end": 4.0, "take": SS.take_for(d, "S01-02")}]
    assert SS.mix_track(d, items, 4.0, os.path.join(d, "song.wav"), os.path.join(d, "m.wav")) is None
    assert not os.path.exists(os.path.join(d, "m.wav"))


def test_two_splits_never_share_a_temporary_file_name():
    """The project's rule (test_tmp_names): a name shared between processes lets one rename the other's file away. The separated sounds were first saved as voice.wav.tmp."""
    src = open(SS.__file__, encoding="utf-8").read()
    assert '".tmp"' not in src and "getpid" in src


def test_a_native_scene_still_gets_the_models_sound_with_the_song_left_out(tmp_path):
    """The sound mix replaced the native-dialogue track builder; the scene must sound as it always did."""
    d = make_film(tmp_path)
    json.dump({"lines": [], "native": True}, open(os.path.join(d, "dialogue.json"), "w"))
    x, r = exported(d)
    assert r["native_sound"] == 1 and level(x, 0.3, 1.7, 1000) > 0.1 and level(x, 0.3, 1.7, 220) < 0.01
