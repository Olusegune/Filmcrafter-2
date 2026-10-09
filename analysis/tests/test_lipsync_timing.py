"""The free sound-timing check: does the sound in a take follow the song's vocal, and is it in time? Synthetic vocals with a known delay, then real ffmpeg files."""
import json
import os
import subprocess
import wave

import numpy as np
import pytest

from filmcrafter_engine import export, lipsync_check as L

RATE = L.RATE


def vocal(seconds=6.0, seed=1):
    """Noise bursts like sung words: loud for a few tenths of a second, then a gap."""
    rng = np.random.default_rng(seed)
    n = int(seconds * RATE)
    env = np.zeros(n)
    t = 0.2
    while t < seconds - 0.4:
        w = rng.uniform(0.2, 0.6)
        env[int(t * RATE):int((t + w) * RATE)] = rng.uniform(0.4, 1.0)
        t += w + rng.uniform(0.15, 0.5)
    return (env * rng.standard_normal(n) * 0.3).astype(np.float32)


def delayed(a, seconds):
    k = int(seconds * RATE)
    return np.concatenate([np.zeros(k, dtype=np.float32), a])[: len(a)] if k >= 0 else np.concatenate([a[-k:], np.zeros(-k, dtype=np.float32)])


def test_the_same_sound_is_in_time():
    v = vocal()
    r = L.compare(v, v * 0.5)
    assert r["verdict"] == "in_time" and r["correlation"] > 0.9 and abs(r["lag_ms"]) <= 20


@pytest.mark.parametrize("delay,verdict,sign", [(0.25, "late", 1), (-0.25, "early", -1)])
def test_a_shifted_copy_is_reported_early_or_late_by_about_the_shift(delay, verdict, sign):
    v = vocal()
    r = L.compare(v, delayed(v, delay))
    assert r["verdict"] == verdict and abs(r["lag_ms"] - delay * 1000) <= 40 and r["lag_ms"] * sign > 0


def test_a_different_sound_of_its_own_is_not_taken_for_the_vocal():
    r = L.compare(vocal(seed=1), vocal(seed=7))
    assert r["verdict"] in ("own_audio", "loose") and r["correlation"] < 0.5


def test_silence_in_the_take_or_in_the_vocal_is_said_plainly():
    z = np.zeros(RATE * 4, dtype=np.float32)
    assert L.compare(vocal(), z)["verdict"] == "no_audio"
    assert L.compare(z, vocal())["verdict"] == "no_vocal"
    assert L.compare(vocal(), np.zeros(0, dtype=np.float32))["verdict"] == "no_audio"
    assert L.compare(vocal(), (np.ones(RATE * 4) * 0.2).astype(np.float32))["verdict"] in ("no_vocal", "no_audio", "own_audio")   # a steady hum is not a performance


def test_a_clip_too_short_to_judge_is_not_a_crash():
    assert L.compare(vocal(0.1), vocal(0.1))["verdict"] in ("no_audio", "no_vocal")


def make_take(path, audio, secs):
    wav = path + ".wav"
    with wave.open(wav, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes((np.clip(audio, -1, 1) * 32000).astype("<i2").tobytes() if audio is not None else b"")
    args = [export.ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=gray:s=160x90:r=24:d={secs}"]
    args += ["-i", wav] if audio is not None else []
    args += ["-pix_fmt", "yuv420p", "-shortest", path]
    subprocess.run(args, check=True)


def project_with_take(tmp_path, take_audio):
    d = tmp_path / "p"
    (d / "generations").mkdir(parents=True)
    v = vocal(8.0)
    with wave.open(str(d / "song.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes((np.concatenate([np.zeros(RATE * 2, dtype=np.float32), v]) * 32000).astype("<i2").tobytes())      # the vocal starts 2 s into the song
    make_take(str(d / "generations" / "t.mp4"), take_audio, 5)
    return str(d)


def test_a_real_take_whose_sound_is_the_vocal_is_in_time(tmp_path):
    v = vocal(8.0)
    d = project_with_take(tmp_path, v[: 5 * RATE])
    shot = {"id": "S01-01", "start": 2.0, "end": 7.0}
    r = L.timing_shot(d, shot, {"output": "generations/t.mp4"})
    assert r["verdict"] == "in_time" and r["against"] == "song", r


def test_a_real_take_with_its_own_sound_or_none(tmp_path):
    d = project_with_take(tmp_path, vocal(5.0, seed=9))
    assert L.timing_shot(d, {"id": "S01-01", "start": 2.0, "end": 7.0}, {"output": "generations/t.mp4"})["verdict"] in ("own_audio", "loose")
    (tmp_path / "q").mkdir()
    d = project_with_take(tmp_path / "q", None)
    assert L.timing_shot(d, {"id": "S01-01", "start": 2.0, "end": 7.0}, {"output": "generations/t.mp4"})["verdict"] == "no_audio"


def test_the_engine_and_the_app_agree_on_the_action_name():
    lib = open(os.path.join(os.path.dirname(__file__), "..", "..", "src-tauri", "src", "lib.rs"), encoding="utf-8").read()
    assert '"timing"' in lib
    import argparse
    src = open(L.__file__, encoding="utf-8").read()
    assert 'choices=["run", "count", "timing"]' in src
