"""Setup wizard engine: probing real audio, video soundtracks, choreography data and its use in shot prompts."""
import json
import os
import subprocess
import wave

import numpy as np
import pytest

from pulseframe_analysis import onboarding as O
from pulseframe_analysis import render as R


def _tone(path, seconds=2.0, sr=22050):
    t = np.arange(int(sr * seconds)) / sr
    x = (np.sin(2 * np.pi * 220 * t) * np.linspace(0, 1, len(t)) * 20000).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(x.tobytes())


def test_probe_reads_duration_and_a_real_waveform(tmp_path):
    p = str(tmp_path / "a.wav"); _tone(p)
    r = O.probe(p)
    assert abs(r["duration"] - 2.0) < 0.05 and len(r["peaks"]) == 600 and r["kind"] == "audio"
    assert r["peaks"][10] < r["peaks"][-10]            # the tone fades in: the waveform shows it


def test_probe_rejects_unsupported_and_silent_files(tmp_path):
    bad = tmp_path / "a.pdf"; bad.write_text("x")
    with pytest.raises(SystemExit):
        O.probe(str(bad))
    vid = str(tmp_path / "v.mp4")
    subprocess.run([O.ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1", vid], check=True,
                   creationflags=O.NO_WINDOW)
    with pytest.raises(SystemExit, match="no audio"):
        O.probe(vid)


def test_video_soundtrack_can_become_the_master_audio(tmp_path):
    a = str(tmp_path / "a.wav"); _tone(a, 1.5)
    vid = str(tmp_path / "v.mp4")
    subprocess.run([O.ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1.5", "-i", a,
                    "-shortest", "-c:a", "aac", vid], check=True, creationflags=O.NO_WINDOW)
    assert O.probe(vid)["kind"] == "video"
    out = O.extract(vid, str(tmp_path / "song.wav"))
    assert abs(out["duration"] - 1.5) < 0.1


def test_choreography_is_structured_and_reaches_shot_prompts(tmp_path):
    d = str(tmp_path)
    with pytest.raises(SystemExit):
        O.choreo_set(d, {"mode": "dance!"})
    O.choreo_set(d, {"mode": "written", "style": "Afrobeats", "notes": "Loose, joyful footwork.",
                     "sections": [{"section": "[Chorus]", "performers": ["Amara"], "notes": "Amara leads a shoulder roll on the hook"},
                                  {"section": "Verse", "notes": ""}]})
    c = O.choreo_get(d)
    assert c["mode"] == "written" and len(c["sections"]) == 1 and not c["precise"]
    chorus = {"id": "S01-01", "section": "CHORUS", "performers": ["Amara"]}
    m = O.movement_for(d, chorus)
    assert "Afrobeats" in m and "shoulder roll" in m
    assert O.movement_for(d, {"id": "x", "section": "CHORUS", "performers": []}) is None   # nobody to move
    assert "shoulder roll" not in O.movement_for(d, {"id": "y", "section": "VERSE", "performers": ["Amara"]})
    shot = R._with_movement(d, chorus)
    assert shot["choreography"] == m


def test_no_choreography_changes_nothing(tmp_path):
    O.choreo_set(str(tmp_path), {"mode": "none"})
    assert R._with_movement(str(tmp_path), {"id": "a", "performers": ["X"]}) == {"id": "a", "performers": ["X"]}
