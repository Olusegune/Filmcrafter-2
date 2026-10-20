"""Checking the finished film: real ffmpeg, real files made on the spot. A good film passes; a black stretch, a frozen stretch, a wrong length, missing or silent sound are each found."""
import subprocess

import pytest

from filmcrafter_engine import exportcheck as X

FF = X._ffmpeg()


def make(path, seconds=6, fps=24, size="320x180", video="testsrc2", audio="sine=frequency=440", extra_vf=None, sound=True):
    src = f"{video}{':' if '=' in video else '='}size={size}:rate={fps}:duration={seconds}"
    cmd = [FF, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", src]
    if sound:
        cmd += ["-f", "lavfi", "-i", f"{audio}:duration={seconds}"]
    if extra_vf:
        cmd += ["-vf", extra_vf]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-shortest"] if sound else ["-an"]) + [str(path)]
    subprocess.run(cmd, check=True)
    return str(path)


def levels(r):
    return [(f["level"], f["what"]) for f in r["findings"]]


def test_a_good_film_passes_cleanly(tmp_path):
    r = X.verify(make(tmp_path / "ok.mp4"), 6.0, expect_sound=True)
    assert r["ok"] is True and r["has_sound"] and r["width"] == 320 and r["frames"] == 144, r
    assert not [f for f in r["findings"] if f["level"] in ("fix", "look")], levels(r)


def test_a_wrong_length_is_a_fault(tmp_path):
    r = X.verify(make(tmp_path / "short.mp4", seconds=5), 6.0, expect_sound=True)
    assert r["ok"] is False and any("should be 6.00 s" in w for _, w in levels(r))


def test_a_black_stretch_is_found_where_it_is(tmp_path):
    p = make(tmp_path / "black.mp4", extra_vf="drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,2,4.5)'")
    r = X.verify(p, 6.0, expect_sound=True)
    black = [f for f in r["findings"] if "black" in f["what"]]
    assert black and 1.5 < black[0]["from"] < 2.5 and black[0]["to"] > 4.0, r["findings"]


def test_a_frozen_stretch_is_a_look_in_a_finished_film_and_a_note_in_a_draft(tmp_path):
    p = make(tmp_path / "freeze.mp4", video="color=c=blue", extra_vf=None)       # a picture that never changes
    r = X.verify(p, 6.0, expect_sound=True)
    assert any("does not move" in w for _, w in levels(r))
    d = X.verify(p, 6.0, expect_sound=True, draft=True)
    assert not any("does not move" in w for _, w in levels(d)) and any(l == "note" and "still" in w for l, w in levels(d))


def test_no_sound_is_said_and_silent_sound_is_a_look(tmp_path):
    none = X.verify(make(tmp_path / "mute.mp4", sound=False), 6.0, expect_sound=True)
    assert any(l == "look" and "no sound track" in w for l, w in levels(none))
    quiet = X.verify(make(tmp_path / "quiet.mp4", audio="anullsrc=r=44100:cl=stereo"), 6.0, expect_sound=True)
    assert any("silent all the way" in w for _, w in levels(quiet)), levels(quiet)
    plain = X.verify(make(tmp_path / "mute2.mp4", sound=False), 6.0, expect_sound=False)
    assert all(l == "note" for l, _ in levels(plain) if "sound" in _)


def test_a_file_that_is_not_a_film_is_a_fault_and_nothing_raises(tmp_path):
    p = tmp_path / "x.mp4"
    p.write_bytes(b"not a film")
    r = X.verify(str(p), 6.0)
    assert r["ok"] is False and r["findings"][0]["level"] == "fix"
    r = X.verify(str(tmp_path / "missing.mp4"), 6.0)
    assert r["ok"] is False
