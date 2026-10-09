"""The take reviewer: technical checks on real (generated) video files, and how a result becomes a status. No network."""
import os
import subprocess

import pytest

from filmcrafter_engine import review as RV
from filmcrafter_engine.export import NO_WINDOW, ffmpeg


def make(path, source, seconds):
    sep = ":" if "=" in source else "="
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"{source}{sep}duration={seconds}:size=160x90:rate=12" if source.startswith("testsrc") else f"{source}:d={seconds}:s=160x90:r=12",
                    "-pix_fmt", "yuv420p", str(path)], check=True, creationflags=NO_WINDOW)
    return str(path)


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("clips")
    return {"good": make(d / "good.mp4", "testsrc2", 3), "black": make(d / "black.mp4", "color=c=black", 3), "still": make(d / "still.mp4", "color=c=0x336699", 3), "short": make(d / "short.mp4", "testsrc2", 1)}


def kinds(issues):
    return [(i["severity"], i["detail"].split(" ")[0]) for i in issues]


def test_a_healthy_take_has_no_technical_issues(clips):
    assert RV.technical(clips["good"], 2.0) == []


def test_a_take_shorter_than_its_shot_is_a_major_problem(clips):
    out = RV.technical(clips["short"], 3.0)
    assert out and out[0]["severity"] == "major" and "needs 3.0s" in out[0]["detail"]


def test_black_frames_in_the_used_part_are_reported_and_long_ones_are_major(clips):
    out = RV.technical(clips["black"], 2.0)
    assert any("Black frames" in i["detail"] for i in out)
    assert any(i["severity"] == "major" for i in out if "Black" in i["detail"])


def test_a_frozen_picture_is_a_minor_problem(clips):
    out = RV.technical(clips["still"], 2.5)
    assert any("freezes" in i["detail"] and i["severity"] == "minor" for i in out)


def test_a_file_that_is_not_a_video_cannot_be_read(tmp_path):
    bad = tmp_path / "x.mp4"
    bad.write_bytes(b"not a video at all")
    out = RV.technical(str(bad), 2.0)
    assert len(out) == 1 and out[0]["severity"] == "major" and "can't be read" in out[0]["detail"]
    assert RV.technical(str(tmp_path / "missing.mp4"), 1.0)[0]["detail"] == "The video file can't be read."


def test_frames_are_taken_only_from_the_part_that_will_be_used(clips):
    frames = RV._frames(clips["good"], 2.0, n=3)
    assert len(frames) == 3 and all(isinstance(f, str) and len(f) > 100 for f in frames)


def job_for(clips, name):
    return {"output": os.path.relpath(clips[name], os.path.dirname(clips[name]))}


def test_a_review_without_a_vision_key_is_technical_only_and_says_so(clips, monkeypatch):
    monkeypatch.setattr(RV, "visual", lambda *a, **k: None)
    d = os.path.dirname(clips["good"])
    r = RV.review_job(d, job_for(clips, "good"), {}, {"start": 0, "end": 2})
    assert r["status"] == "good" and r["visual"] is None and r["summary"] == "Looks good." and r["fixes"] == [] and r["reviewed"] is True


def test_a_major_technical_problem_skips_the_paid_visual_check(clips, monkeypatch):
    called = []
    monkeypatch.setattr(RV, "visual", lambda *a, **k: called.append(1))
    d = os.path.dirname(clips["short"])
    r = RV.review_job(d, job_for(clips, "short"), {}, {"start": 0, "end": 3})
    assert r["status"] == "needs_attention" and not called


def test_visual_findings_decide_the_status_and_collect_the_fixes(clips, monkeypatch):
    issue = {"kind": "wardrobe", "severity": "minor", "detail": "Glasses are on her nose.", "fix": "Glasses stay above the forehead."}
    monkeypatch.setattr(RV, "visual", lambda *a, **k: {"verdict": "minor", "summary": "Close, but the glasses moved.", "issues": [issue], "model": "m"})
    d = os.path.dirname(clips["good"])
    r = RV.review_job(d, job_for(clips, "good"), {}, {"start": 0, "end": 2})
    assert r["status"] == "minor" and r["summary"] == "Close, but the glasses moved." and r["fixes"] == ["Glasses stay above the forehead."]
    major = dict(issue, severity="major")
    monkeypatch.setattr(RV, "visual", lambda *a, **k: {"verdict": "needs_attention", "summary": "s", "issues": [major], "model": "m"})
    assert RV.review_job(d, job_for(clips, "good"), {}, {"start": 0, "end": 2})["status"] == "needs_attention"


def test_a_failing_visual_check_never_breaks_rendering(clips, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("model unavailable")
    monkeypatch.setattr(RV, "visual", boom)
    d = os.path.dirname(clips["good"])
    r = RV.review_job(d, job_for(clips, "good"), {}, {"start": 0, "end": 2})
    assert r["status"] == "unchecked" and "not checked visually" in r["summary"] and r["visual"] is None
