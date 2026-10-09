"""Using your own recording for a line instead of a generated voice. No network."""
import os

import numpy as np
import pytest
import soundfile as sf

from pulseframe_analysis import show as S, voices as V
from tests.test_show import _fake_speak


@pytest.fixture
def show(tmp_path):
    return S.create(str(tmp_path / "shows"), "Night Market")["dir"]


def _take(path, amp=0.1, lead=1.0, tone=0.5, tail=1.0, rate=44100):
    """An actor's take: silence, a tone (the words), silence."""
    t = np.linspace(0, tone, int(rate * tone), endpoint=False)
    x = np.concatenate([np.zeros(int(rate * lead)), amp * np.sin(2 * np.pi * 250 * t), np.zeros(int(rate * tail))]).astype(np.float32)
    sf.write(str(path), x, rate)
    return str(path)


def _scene(show, lines):
    d = S.add_scene(show, "Quarrel")["dir"]
    return d, V.set_dialogue(d, {"lines": lines})["lines"]


def test_a_recording_is_copied_in_checked_and_attached_to_its_line(show, tmp_path):
    scene, lines = _scene(show, [{"character": "Ada", "text": "Where were you?"}])
    take = _take(tmp_path / "ada.wav")
    r = V.set_recording(scene, lines[0]["id"], take)
    ln = r["lines"][0]
    assert ln["recording"].startswith("recordings/") and ln["recording_name"] == "ada.wav" and os.path.exists(take)      # the original stays
    assert os.path.exists(os.path.join(scene, ln["recording"]))
    with pytest.raises(SystemExit, match="Save the line first"):
        V.set_recording(scene, "nope", take)
    (tmp_path / "x.exe").write_bytes(b"MZ")
    with pytest.raises(SystemExit, match="audio file"):
        V.set_recording(scene, lines[0]["id"], str(tmp_path / "x.exe"))
    with pytest.raises(SystemExit, match="audio file"):
        V.set_recording(scene, lines[0]["id"], str(tmp_path / "missing.wav"))
    sf.write(str(tmp_path / "quiet.wav"), np.zeros(4410, dtype=np.float32), 44100)
    with pytest.raises(SystemExit, match="silent"):
        V.set_recording(scene, lines[0]["id"], str(tmp_path / "quiet.wav"))


def test_size_and_length_are_limited_and_a_refused_file_leaves_nothing_behind(show, tmp_path, monkeypatch):
    scene, lines = _scene(show, [{"character": "Ada", "text": "Hi."}])
    take = _take(tmp_path / "ada.wav")
    monkeypatch.setattr(V, "MAX_RECORDING_BYTES", 1000)
    with pytest.raises(SystemExit, match="too large"):
        V.set_recording(scene, lines[0]["id"], take)
    monkeypatch.setattr(V, "MAX_RECORDING_BYTES", 100_000_000)
    monkeypatch.setattr(V, "MAX_RECORDING_SECONDS", 1)
    with pytest.raises(SystemExit, match="longer than"):
        V.set_recording(scene, lines[0]["id"], take)
    assert not os.path.isdir(os.path.join(scene, "recordings")) or os.listdir(os.path.join(scene, "recordings")) == []
    assert "recording" not in V.dialogue(scene)["lines"][0]


def test_a_recorded_line_is_free_needs_no_voice_and_is_trimmed_and_levelled(show, tmp_path, monkeypatch):
    scene, lines = _scene(show, [{"character": "Ada", "text": "Where were you?"}, {"character": "Ben", "text": "Waiting for you."}])
    V.set_voice(show, "Ben", {"voice_id": "Deep_Voice_Man"})                          # Ada has no voice: her line is recorded
    V.set_recording(scene, lines[0]["id"], _take(tmp_path / "ada.wav", amp=0.1))
    calls = []
    monkeypatch.setattr(V, "_speak", _fake_speak(calls))
    monkeypatch.setattr("pulseframe_analysis.render._fal_price", lambda m: None)
    assert V.estimate(scene)["lines"] == 1                                            # only Ben's line is billed
    r = V.generate(scene)
    assert r["voiced"] == 1 and r["recorded"] == 1 and len(calls) == 1 and calls[0][0] == "Waiting for you."
    t = V.dialogue(scene)["timings"]
    assert t[0]["recording"].startswith("recordings/") and t[1]["recording"] is None
    assert t[0]["end"] - t[0]["start"] == pytest.approx(0.5 + 2 * V.EDGE_PAD, abs=0.05)   # the silence either side is gone
    song, rate = sf.read(os.path.join(scene, "song.wav"))
    mono = song[:, 0]
    seg = lambda a, b: mono[int(a * rate): int(b * rate)]
    rec_rms, voiced_rms = V._rms(seg(t[0]["start"], t[0]["end"])), V._rms(seg(t[1]["start"], t[1]["end"]))
    assert 0.6 < rec_rms / voiced_rms < 1.4                                           # the recording sits at the voiced line's level
    assert not V.set_dialogue(scene, {"lines": V.dialogue(scene)["lines"]})["stale"]


def test_a_scene_of_only_recordings_needs_no_voices_and_costs_nothing(show, tmp_path, monkeypatch):
    scene, lines = _scene(show, [{"character": "Ada", "text": "One."}, {"character": "Ben", "text": "Two."}])
    for i, ln in enumerate(lines):
        V.set_recording(scene, ln["id"], _take(tmp_path / f"t{i}.wav", amp=0.2))
    monkeypatch.setattr(V, "_speak", lambda *a: (_ for _ in ()).throw(AssertionError("nothing should be voiced")))
    e = V.estimate(scene)
    assert e["lines"] == 0 and e["usd"] == 0.0
    r = V.generate(scene)
    assert r["recorded"] == 2 and r["voiced"] == 0 and sf.info(os.path.join(scene, "song.wav")).duration > 1.0
    assert S.status(show)["acts"][0]["items"][0]["problems"] == ["Not analysed yet."]     # voiced; it only awaits analysis in the Studio


def test_a_recording_survives_editing_but_a_stray_path_does_not(show, tmp_path):
    scene, lines = _scene(show, [{"character": "Ada", "text": "Hi."}])
    r = V.set_recording(scene, lines[0]["id"], _take(tmp_path / "ada.wav"))
    kept = V.set_dialogue(scene, {"lines": r["lines"]})["lines"][0]
    assert kept["recording"] == r["lines"][0]["recording"] and kept["recording_name"] == "ada.wav"
    outside = _take(tmp_path / "outside.wav")
    for bad in ("../../outside.wav", os.path.relpath(outside, scene), "dialogue.json", "recordings/../dialogue.json", "recordings/missing.wav"):
        out = V.set_dialogue(scene, {"lines": [{**r["lines"][0], "recording": bad}]})["lines"][0]
        assert "recording" not in out, bad


def test_changing_or_removing_a_recording_makes_the_scene_stale_again(show, tmp_path, monkeypatch):
    scene, lines = _scene(show, [{"character": "Ada", "text": "Hi."}])
    V.set_recording(scene, lines[0]["id"], _take(tmp_path / "a.wav"))
    V.generate(scene)
    assert not V._stale(scene, V.dialogue(scene))
    V.set_recording(scene, lines[0]["id"], _take(tmp_path / "b.wav", tone=0.7))             # a better take
    assert V._stale(scene, V.dialogue(scene))
    V.generate(scene)
    assert not V._stale(scene, V.dialogue(scene))
    r = V.clear_recording(scene, lines[0]["id"])
    assert "recording" not in r["lines"][0] and r["stale"]                                    # back to a generated voice: voice it again
    with pytest.raises(SystemExit, match="has no voice"):
        V.generate(scene)
    assert len(os.listdir(os.path.join(scene, "recordings"))) == 2                            # the takes are kept, never deleted
