"""Native dialogue: a spoken scene whose lines the video model speaks itself. Nothing is voiced or billed; the export uses each take's sound."""
import json
import os
import subprocess

import numpy as np
import pytest
import soundfile as sf

from filmcrafter_engine import export as E, render as R, shotsound

RATE = shotsound.RATE


def _decode(path):
    return shotsound.decode(path, 1)[:, 0]


def _dlg(scene, data):
    """The scene's dialogue switch and lines, as the render reads them (dialogue.json)."""
    json.dump(data, open(os.path.join(scene, "dialogue.json"), "w"))


def field(name, type="string", **kw):
    return {"name": name, "type": type, "items": kw.get("items"), "enum": kw.get("enum"), "default": kw.get("default"), "minimum": None, "maximum": None,
            "max_items": None, "max_length": None, "description": kw.get("description", ""), "required": kw.get("required", False)}


def _talking():
    return R._finish("fal", "test/talker", "Talker 1", "image-to-video", [field("prompt"), field("duration", enum=["4s", "6s", "8s"]), field("generate_audio", "boolean")])


def _mute():
    return R._finish("fal", "test/mute", "Mute 1", "image-to-video", [field("prompt"), field("duration", enum=["4s", "6s", "8s"])])


LINES = [{"character": "Ada", "text": "Where were you last night?"}, {"character": "Ben", "text": "Out. Walking. Thinking."}]


@pytest.fixture
def scene(tmp_path):
    sc = tmp_path / "scene"
    sc.mkdir()
    _dlg(str(sc), {"lines": LINES})
    return str(sc)


def _songmap(d, lyrics):
    json.dump({"duration": 8, "lyrics": lyrics}, open(os.path.join(d, "songmap.json"), "w"))


SHOT = {"id": "S01-01", "start": 0.6, "end": 3.0, "beats": ["Ada confronts Ben"], "performers": ["Ada", "Ben"]}
PLAN = {"meta": {}, "characters": [{"name": "Ada", "appearance": "tall. red coat"}, {"name": "Ben", "appearance": "short. blue hat"}], "scenes": []}


# ---------------------------------------------------------------- the switch and the free track

# ---------------------------------------------------------------- what the model is asked

def test_a_shot_where_people_speak_asks_the_model_to_say_it_with_sound_on(scene):
    _dlg(scene, {"lines": LINES, "native": True})
    _songmap(scene, [{"text": 'Where were "you"?', "start": 0.6, "end": 2.0, "performer": "Ada"}, {"text": "Out.", "start": 2.2, "end": 2.8, "performer": "Ben"},
                     {"text": "Later line", "start": 5.0, "end": 6.0, "performer": "Ada"}])
    man = _talking()
    n = R.native_for(scene, SHOT, man)
    assert n == {"lines": [{"who": "Ada", "text": "Where were 'you'?", "how": ""}, {"who": "Ben", "text": "Out.", "how": ""}]}   # only the lines under this shot; quotes can't break the prompt
    p = R.compile_request(SHOT, None, PLAN, {"look": {"style": "auto"}}, man, [], native=n)
    assert p["generate_audio"] is True
    assert "Ada says: \"Where were 'you'?\" Then Ben says: \"Out.\"" in p["prompt"] and "no background music" in p["prompt"]
    assert "Performers do not lip-sync" not in p["prompt"]
    assert "in turn, while the others listen with their mouths closed" in p["prompt"] and "no subtitles, captions or written words" in p["prompt"]
    solo = R.compile_request(SHOT, None, PLAN, {"look": {"style": "auto"}}, man, [], native={"lines": [n["lines"][0]]})["prompt"]
    assert "in turn" not in solo                                                                       # nobody to take turns with
    off = R.compile_request(SHOT, None, PLAN, {"look": {"style": "auto"}}, man, [])
    assert off["generate_audio"] is False and "says:" not in off["prompt"]                            # every other scene still renders silent
    assert R.native_problem(scene, SHOT, man) is None and R.native_for(scene, {**SHOT, "start": 6.5, "end": 8.0}, man) is None


def test_a_lines_emotion_becomes_how_it_is_said(scene):
    _dlg(scene, {"lines": [{"character": "Ada", "text": "Where were you?", "emotion": "angry"}, {"character": "Ben", "text": "Out.", "emotion": "neutral"}], "native": True})
    _songmap(scene, [{"text": "Where were you?", "start": 0.6, "end": 2.0, "performer": "Ada"}, {"text": "Out.", "start": 2.2, "end": 2.8, "performer": "Ben"}])
    n = R.native_for(scene, SHOT, _talking())
    assert [x["how"] for x in n["lines"]] == ["angrily", ""]                                           # neutral adds nothing
    p = R.compile_request(SHOT, None, PLAN, {"look": {"style": "auto"}}, _talking(), [], native=n)["prompt"]
    assert 'Ada says angrily: "Where were you?" Then Ben says: "Out."' in p


def test_a_shot_with_more_speech_than_it_holds_is_flagged_in_the_price_sheet(scene, monkeypatch):
    words = " ".join(["word"] * 20)                                                                    # about eight seconds of speech
    _dlg(scene, {"lines": [{"character": "Ada", "text": words}], "native": True})
    _songmap(scene, [{"text": words, "start": 0.6, "end": 8.6, "performer": "Ada"}])
    plan = {"meta": {}, "characters": [], "scenes": [{"number": 1, "heading": "INT.", "shots": [{**SHOT, "start": 0.6, "end": 3.0}]}]}
    json.dump(plan, open(os.path.join(scene, "production.json"), "w"))
    json.dump({"title": "T", "look": {"style": "auto"}}, open(os.path.join(scene, "project.json"), "w"))
    monkeypatch.setattr(R, "manifest", lambda p, m: _talking())
    monkeypatch.setattr(R, "_reference_files", lambda *a, **k: [])
    monkeypatch.setattr(R, "_fal_price", lambda m: {"unit": "second", "unit_price": 0.2})
    e = R.estimate(scene, ["S01-01"], "fal", "test/talker")
    assert e["native_shots"] == 1 and e["native_crowded"] == ["S01-01"] and "more speech than" in e["native_note"]


def test_a_model_that_cannot_make_sound_is_refused_before_anything_is_sent(scene):
    _dlg(scene, {"lines": LINES, "native": True})
    _songmap(scene, [{"text": "Hello", "start": 0.6, "end": 2.0, "performer": "Ada"}])
    man = _mute()
    assert R.native_for(scene, SHOT, man) is None
    why = R.native_problem(scene, SHOT, man)
    assert "Mute 1" in why and "turn native dialogue off" in why
    assert R.native_problem(scene, {**SHOT, "start": 6.0, "end": 7.0}, man) is None                  # a shot where nobody speaks can still be made silently
    _dlg(scene, {"lines": LINES, "native": False})
    assert R.native_problem(scene, SHOT, man) is None                                                 # and a normal scene is not affected at all


def test_the_lip_sync_pass_and_the_recorded_voice_are_not_used_for_a_native_scene(scene):
    _songmap(scene, [{"text": "Hello", "start": 0.6, "end": 2.0, "performer": "Ada"}])
    proj = {"lip_sync": "closeups"}
    close = {**SHOT, "framing": "close-up"}
    assert R.wants_lipsync_pass(scene, proj, PLAN, close) is True
    _dlg(scene, {"lines": LINES, "native": True})
    assert R.wants_lipsync_pass(scene, proj, PLAN, close) is False
    man = R._finish("fal", "test/talker", "Talker", "image-to-video", [field("prompt"), field("generate_audio", "boolean"), field("audio_urls", "array", items="string")])
    assert R._sung_for(scene, SHOT, PLAN, man) is None


# ---------------------------------------------------------------- the sound in the export

def _clip(path, secs, sound):
    cmd = [E.ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=gray:s=160x90:r=24:d={secs}"]
    if sound:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}", "-c:a", "aac", "-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", path]
    subprocess.run(cmd, check=True, creationflags=E.NO_WINDOW)


def test_the_track_is_each_shots_own_sound_laid_at_its_shot_and_silent_elsewhere(tmp_path):
    a, b, c = (str(tmp_path / n) for n in ("a.mp4", "b.mp4", "c.mp4"))
    _clip(a, 3.0, True)                                       # speaks for longer than its 1.5 s shot: must be cut to it
    _clip(b, 1.5, False)                                      # a take with no sound at all
    _clip(c, 1.0, True)
    out = str(tmp_path / "n.wav")
    r = E.native_track(str(tmp_path), [(0.0, 1.5, a), (1.5, 3.0, b), (3.0, 4.0, c)], 5.0, out)
    assert r["with_sound"] == 2 and r["silent"] == 1
    x = _decode(out)
    rate = RATE
    assert len(x) == 5 * rate
    seg = lambda t0, t1: float(np.sqrt(np.mean(x[int(t0 * rate):int(t1 * rate)] ** 2)))
    assert seg(0.2, 1.3) > 0.03 and seg(1.7, 2.9) < 0.001 and seg(3.2, 3.9) > 0.03 and seg(4.2, 4.9) < 0.001
    assert float(np.abs(x).max()) <= 0.96                                                              # never clips


def test_a_native_scene_exports_with_the_models_sound_not_the_placeholder(tmp_path):
    d = tmp_path / "n"
    (d / "generations").mkdir(parents=True)
    shots = [{"id": "S01-01", "start": 0.0, "end": 1.5, "beats": ["a"], "performers": []}, {"id": "S01-02", "start": 1.5, "end": 3.0, "beats": ["b"], "performers": []}]
    json.dump({"scenes": [{"number": 1, "heading": "INT. ROOM", "shots": shots}]}, open(d / "production.json", "w"))
    json.dump({"title": "T", "song": "song.wav"}, open(d / "project.json", "w"))
    json.dump({"duration": 3.0, "lyrics": [], "sections": []}, open(d / "songmap.json", "w"))
    json.dump({"lines": [], "native": True}, open(d / "dialogue.json", "w"))
    sf.write(str(d / "song.wav"), np.zeros(132300, dtype=np.float32), 44100)                           # the silent placeholder
    _clip(str(d / "generations" / "t1.mp4"), 1.5, True)
    _clip(str(d / "generations" / "t2.mp4"), 1.5, False)
    jobs = [{"id": f"j{i}", "shot_id": f"S01-0{i}", "plan": "production", "state": "ready", "output": f"generations/t{i}.mp4", "created": 1, "kind": "video",
             "provider": "fal"} for i in (1, 2)]
    json.dump({"jobs": jobs}, open(d / "jobs.json", "w"))
    r = E.build(str(d), "square")
    assert r["native_sound"] == 1 and r["native_silent"] == 1 and not r["draft"]
    x = _decode(r["path"])
    seg = lambda t0, t1: float(np.sqrt(np.mean(x[int(t0 * RATE):int(t1 * RATE)] ** 2)))
    assert seg(0.2, 1.3) > 0.03 and seg(1.8, 2.9) < 0.001


def test_an_ordinary_scene_still_gets_its_song_and_reports_nothing_native(tmp_path):
    d = tmp_path / "o"
    (d / "generations").mkdir(parents=True)
    json.dump({"scenes": [{"number": 1, "heading": "INT.", "shots": [{"id": "S01-01", "start": 0.0, "end": 2.0, "beats": ["a"], "performers": []}]}]}, open(d / "production.json", "w"))
    json.dump({"title": "T", "song": "song.wav"}, open(d / "project.json", "w"))
    json.dump({"duration": 2.0, "sections": []}, open(d / "songmap.json", "w"))
    t = np.linspace(0, 2, 88200, endpoint=False)
    sf.write(str(d / "song.wav"), (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), 44100)
    json.dump({"jobs": []}, open(d / "jobs.json", "w"))
    r = E.build(str(d), "square")
    assert "native_sound" not in r
    x = _decode(r["path"])
    assert float(np.sqrt(np.mean(x[8000:80000] ** 2))) > 0.1
