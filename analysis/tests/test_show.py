"""Shows (numbers and spoken scenes with one cast) and voices (dialogue to a timed scene track). No network."""
import json
import os

import numpy as np
import pytest
import soundfile as sf
from PIL import Image

from filmcrafter_engine import library, render as R, show as S, voices as V


def _song(tmp_path, secs=3.0, name="song.wav"):
    p = tmp_path / name
    t = np.linspace(0, secs, int(44100 * secs), endpoint=False)
    sf.write(p, (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), 44100)
    return str(p)


@pytest.fixture
def show(tmp_path):
    return S.create(str(tmp_path / "shows"), "Night Market")["dir"]


def test_create_a_show_with_a_cast_project(show):
    st = S.status(show)
    assert st["title"] == "Night Market" and st["acts"][0]["name"] == "Act 1" and st["acts"][0]["items"] == []
    assert os.path.isfile(os.path.join(show, "cast", "project.json"))
    assert S.is_show(show) and not S.is_show(os.path.join(show, "cast"))


def test_numbers_are_normal_projects_and_the_original_song_is_untouched(show, tmp_path):
    song = _song(tmp_path)
    r = S.add_number(show, song, "Opening", lyrics="[Verse]\nHello night")
    p = json.load(open(os.path.join(r["dir"], "project.json")))
    assert p["song"] == "song.wav" and p["lyrics"] == "lyrics.txt" and p["show_item"]["kind"] == "number"
    assert os.path.exists(song) and os.path.exists(os.path.join(r["dir"], "song.wav"))
    with pytest.raises(SystemExit, match="can't be found"):
        S.add_number(show, str(tmp_path / "missing.mp3"), "Nope")


def test_add_an_existing_project_by_copying_it(show, tmp_path):
    src = tmp_path / "Old"
    (src / "cache").mkdir(parents=True)
    (src / "project.json").write_text(json.dumps({"title": "Old Song", "song": "song.wav"}))
    (src / "cache" / "big.bin").write_bytes(b"x" * 10)
    r = S.add_existing(show, str(src))
    assert json.load(open(src / "project.json")) == {"title": "Old Song", "song": "song.wav"}     # original untouched
    assert not os.path.exists(os.path.join(r["dir"], "cache", "big.bin"))                       # caches not copied


def test_one_cast_reaches_every_item_and_follows_changes(show, tmp_path):
    cast = os.path.join(show, "cast")
    os.makedirs(os.path.join(cast, "assets"), exist_ok=True)
    Image.new("RGB", (16, 16)).save(os.path.join(cast, "assets", "ada.png"))
    a = S.add_number(show, _song(tmp_path), "One")["dir"]
    b = S.add_scene(show, "Two", "A rooftop at dusk")["dir"]
    ada = library.upsert(cast, {"kind": "character", "name": "Ada", "files": ["assets/ada.png"]})
    library.bible(cast, {"world": "A city that never sleeps"})
    S.sync(show)
    for d in (a, b):
        _, lib = library.load(d)
        it = next(i for i in lib["items"] if i["name"] == "Ada")
        assert it["from_show"] and os.path.exists(os.path.join(d, it["files"][0]))
        assert library.bible(d)["world"] == "A city that never sleeps"
    library.upsert(a, {"kind": "prop", "name": "Lantern", "files": []})                         # item-only reference survives
    library.delete(cast, next(i["id"] for i in library.load(cast)[1]["items"] if i["name"] == "Ada"))
    S.sync(show)
    names = {i["name"] for i in library.load(a)[1]["items"]}
    assert "Ada" not in names and "Lantern" in names
    assert ada


def test_running_order_acts_and_removal_keeps_files(show, tmp_path):
    ids = [S.add_number(show, _song(tmp_path, name=f"s{i}.wav"), f"Song {i}")["item"] for i in range(3)]
    S.add_act(show, "Act 2")
    S.set_act(show, ids[2], 1)
    S.move(show, ids[0], +1)
    st = S.status(show)
    assert [i["id"] for i in st["acts"][0]["items"]] == [ids[1], ids[0]] and [i["id"] for i in st["acts"][1]["items"]] == [ids[2]]
    S.move(show, ids[0], +1)                                                                      # crosses into Act 2
    assert [i["id"] for i in S.status(show)["acts"][1]["items"]][0] == ids[0]
    d = S.status(show)["acts"][0]["items"][0]["path"]
    S.remove(show, ids[1])
    assert not os.path.exists(d) and len(os.listdir(os.path.join(show, "removed"))) == 1


def test_transitions_are_validated(show, tmp_path):
    i = S.add_number(show, _song(tmp_path), "Solo")["item"]
    S.set_transition(show, i, "black")
    assert S.status(show)["acts"][0]["items"][0]["transition"] == "black"
    with pytest.raises(SystemExit):
        S.set_transition(show, i, "wipe")
    with pytest.raises(SystemExit, match="last item"):
        S.set_transition(show, i, "flow")


# ---------------------------------------------------------------- voices

def _fake_speak(calls):
    def speak(text, v, emotion, out):
        calls.append((text, v["voice_id"], emotion))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        secs = 0.5 + 0.01 * len(text)
        t = np.linspace(0, secs, int(24000 * secs), endpoint=False)
        sf.write(out.replace(".mp3", ".wav"), (0.3 * np.sin(2 * np.pi * 300 * t)).astype(np.float32), 24000)
        os.replace(out.replace(".mp3", ".wav"), out)   # ffmpeg reads it by content, whatever the name
        return secs
    return speak


def test_scene_dialogue_becomes_a_timed_track_and_only_changed_lines_are_paid(show, monkeypatch):
    scene = S.add_scene(show, "Rooftop")["dir"]
    with pytest.raises(SystemExit, match="dialogue first"):
        V.estimate(scene)
    V.set_dialogue(scene, {"lines": [{"character": "Ada", "text": "Where were you?"}, {"character": "Ben", "text": "Waiting.", "pause": 1.0}]})
    with pytest.raises(SystemExit, match="has no voice"):
        V.generate(scene)
    V.set_voice(show, "Ada", {"voice_id": "Calm_Woman"})
    V.set_voice(show, "Ben", {"voice_id": "Deep_Voice_Man", "speed": 9})
    assert V.voices(show)["voices"]["Ben"]["speed"] == 2.0                                        # clamped
    calls = []
    monkeypatch.setattr(V, "_speak", _fake_speak(calls))
    monkeypatch.setattr("filmcrafter_engine.render._fal_price", lambda m: None)
    assert V.estimate(scene)["lines"] == 2
    r = V.generate(scene)
    t = V.dialogue(scene)["timings"]
    assert r["voiced"] == 2 and [x["character"] for x in t] == ["Ada", "Ben"]
    assert t[0]["start"] == pytest.approx(V.LEAD_IN, abs=0.01) and t[1]["start"] > t[0]["end"] + V.DEFAULT_PAUSE - 0.01
    info = sf.info(os.path.join(scene, "song.wav"))
    assert info.channels == 2 and info.duration == pytest.approx(t[-1]["end"] + V.TAIL, abs=0.05)
    assert not V.set_dialogue(scene, {"lines": V.dialogue(scene)["lines"]})["stale"]
    lines = V.dialogue(scene)["lines"]
    lines[1]["text"] = "Waiting for you."
    assert V.set_dialogue(scene, {"lines": lines})["stale"]
    assert V.estimate(scene)["lines"] == 1                                                        # Ada's line is reused
    calls.clear()
    assert V.generate(scene)["reused"] == 1 and len(calls) == 1


def test_dialogue_validation(show):
    scene = S.add_scene(show, "S")["dir"]
    with pytest.raises(SystemExit, match="needs a character"):
        V.set_dialogue(scene, {"lines": [{"text": "hi"}]})
    with pytest.raises(SystemExit, match="no words"):
        V.set_dialogue(scene, {"lines": [{"character": "Ada", "text": "  "}]})
    with pytest.raises(SystemExit, match="Choose one of the voices"):
        V.set_voice(show, "Ada", {"voice_id": "Robot"})


def test_analysis_uses_exact_dialogue_timings(tmp_path):
    from filmcrafter_engine import analyze as A
    d = tmp_path / "scene"
    d.mkdir()
    (d / "dialogue.json").write_text(json.dumps({"timings": [{"character": "Ada", "text": "Hi", "start": 0.6, "end": 1.2},
                                                             {"character": "Ben", "text": "Hey", "start": 1.7, "end": 2.1}]}))
    sm = A.analyze(_song(tmp_path, 3.0))
    assert A._apply_dialogue(sm, str(d))
    assert [l["performer"] for l in sm.lyrics] == ["Ada", "Ben"] and sm.lyrics[1]["start"] == 1.7
    assert sm.sections[0].label == "Scene" and sm.analyzer.endswith("dialogue-exact")


def test_spoken_lines_lipsync_the_speaker_not_whoever_is_first(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    (d / "songmap.json").write_text(json.dumps({"lyrics": [{"text": "Hey", "start": 1.0, "end": 2.0, "performer": "Ben"}]}))
    shot = {"start": 0, "end": 3, "performers": ["Ada", "Ben"], "beats": ["they talk"]}
    assert R.singing(str(d), shot, {})["performer"] == "Ben"
    assert R.singing(str(d), {**shot, "performers": ["Ada"]}, {}) is None                        # Ben is off-screen


# ---------------------------------------------------------------- robustness

def test_an_item_pointing_outside_the_show_is_refused_and_never_moved(show, tmp_path):
    victim = tmp_path / "precious"
    victim.mkdir()
    (victim / "keep.txt").write_text("x")
    i = S.add_number(show, _song(tmp_path), "Solo")["item"]
    data = json.load(open(os.path.join(show, "show.json")))
    data["items"][i]["dir"] = "../../precious"
    json.dump(data, open(os.path.join(show, "show.json"), "w"))
    with pytest.raises(SystemExit, match="outside"):
        S.remove(show, i)
    assert (victim / "keep.txt").exists()
    assert S.status(show)["acts"][0]["items"][0]["state"] == "broken"          # shown, not a crash


def test_a_damaged_show_file_recovers_from_the_last_good_copy(show, tmp_path):
    S.add_number(show, _song(tmp_path), "Solo")
    S.add_act(show, "Act 2")                                                    # a second save, so a .bak exists
    open(os.path.join(show, "show.json"), "w").write("{ not json")
    st = S.status(show)
    assert st["title"] == "Night Market" and len(st["acts"]) in (1, 2)
    assert json.load(open(os.path.join(show, "show.json")))["title"] == "Night Market"


def test_acts_validate_and_only_empty_acts_can_be_removed(show, tmp_path):
    with pytest.raises(SystemExit, match="at least one"):
        S.remove_act(show, 0)
    i = S.add_number(show, _song(tmp_path), "Solo")["item"]
    S.add_act(show, "Act 2")
    with pytest.raises(SystemExit, match="elsewhere"):
        S.remove_act(show, 0)
    with pytest.raises(SystemExit, match="No such act"):
        S.set_act(show, i, 5)
    with pytest.raises(SystemExit, match="No such act"):
        S.rename(show, None, "Nope", act=9)
    with pytest.raises(SystemExit, match="isn't in the show"):
        S.set_act(show, "ghost", 1)
    S.remove_act(show, 1)
    assert [a["name"] for a in S.status(show)["acts"]] == ["Act 1"]


def test_the_last_item_never_keeps_a_transition_into_nothing(show, tmp_path):
    a = S.add_number(show, _song(tmp_path, name="a.wav"), "A")["item"]
    b = S.add_number(show, _song(tmp_path, name="b.wav"), "B")["item"]
    S.set_transition(show, a, "black")
    S.move(show, a, +1)                                                         # A is now last: black into nothing
    items = {i["id"]: i for i in S.status(show)["acts"][0]["items"]}
    assert items[a]["transition"] == "cut" and items[b]["transition"] == "cut"


def test_status_says_what_is_wrong_with_each_item(show, tmp_path):
    scene = S.add_scene(show, "Quarrel")
    num = S.add_number(show, _song(tmp_path), "Song")
    items = {i["id"]: i for i in S.status(show)["acts"][0]["items"]}
    assert "No dialogue written yet." in items[scene["item"]]["problems"]
    assert "Not analysed yet." in items[num["item"]]["problems"]
    V.set_dialogue(scene["dir"], {"lines": [{"character": "Ada", "text": "Hello."}]})
    items = {i["id"]: i for i in S.status(show)["acts"][0]["items"]}
    assert "The dialogue hasn't been voiced yet." in items[scene["item"]]["problems"]


def test_export_names_every_unfinished_item_before_doing_any_work(show, tmp_path):
    S.add_scene(show, "Quarrel")
    S.add_number(show, _song(tmp_path), "Song")
    os.remove(os.path.join(S.status(show)["acts"][0]["items"][1]["path"], "song.wav"))
    with pytest.raises(SystemExit) as e:
        S.export(show)
    assert "Quarrel: voice the dialogue first." in str(e.value) and "Song: the song file is missing." in str(e.value)
    assert os.listdir(os.path.join(show, "exports")) == []


def test_a_dropped_connection_is_retried_but_a_refused_key_is_not(monkeypatch, tmp_path):
    calls = {"n": 0}

    def flaky(text, v, emotion, out):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("connection reset")
        return 1.0
    monkeypatch.setattr(V, "_speak_once", flaky)
    monkeypatch.setattr(V.time, "sleep", lambda s: None)
    assert V._speak("Hi", {"voice_id": "Wise_Woman"}, None, str(tmp_path / "a.mp3")) == 1.0 and calls["n"] == 3
    calls["n"] = 0
    monkeypatch.setattr(V, "_speak_once", lambda *a: (_ for _ in ()).throw(RuntimeError("403 Forbidden")))
    with pytest.raises(RuntimeError):
        V._speak("Hi", {"voice_id": "Wise_Woman"}, None, str(tmp_path / "b.mp3"))


def test_people_who_speak_in_a_scene_join_the_cast_once(show):
    a = S.add_scene(show, "Cold open")["dir"]
    V.set_dialogue(a, {"lines": [{"character": "Queen Bee", "text": "Children!"}, {"character": "Tunde", "text": "We are downstairs."}]})
    assert set(S.status(show)["characters"]) == {"Queen Bee", "Tunde"}
    b = S.add_scene(show, "Next")["dir"]
    V.set_dialogue(b, {"lines": [{"character": "queen bee", "text": "Again."}, {"character": "Zara", "text": "No."}]})   # same person, other capitals
    assert sorted(S.status(show)["characters"]) == ["Queen Bee", "Tunde", "Zara"]
    names = {i["name"] for i in library.load(b)[1]["items"]}
    assert {"Queen Bee", "Tunde", "Zara"} <= names                                    # and they reach every scene
