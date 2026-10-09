"""Camera and lighting suggested by the feeling of a shot: the right look for the feeling, never over a person's choice or the Director's own words, and applied as ordinary camera choices."""
import json
import os

import pytest

from filmcrafter_engine import camera as C
from filmcrafter_engine import looks as L


def shot(i=1, emotion="dread", intensity=8, **kw):
    return {"id": f"S01-{i:02d}", "scene": 1, "start": i * 2.0, "end": i * 2.0 + 2, "framing": "", "emotion": emotion, "performance_intensity": intensity,
            "performers": ["Ada"], "beats": ["She waits."], **kw}


def project(tmp_path, shots):
    d = tmp_path / "p"
    d.mkdir(exist_ok=True)
    json.dump({"title": "T", "song": "song.wav"}, open(d / "project.json", "w"))
    json.dump({"duration": 20, "bpm": 120, "sections": []}, open(d / "songmap.json", "w"))
    json.dump({"meta": {}, "scenes": [{"number": 1, "heading": "INT.", "shots": shots}]}, open(d / "production.json", "w"))
    return str(d)


def terms(r):
    return {p["group"]: p["term"] for p in r["proposals"]}


@pytest.mark.parametrize("emotion,lighting", [("dread", "lowkey"), ("a quiet grief", "overcast"), ("tender, longing", "practical"), ("joy", "golden"), ("defiant rage", "hardkey"), ("triumph", "rim")])
def test_the_feeling_picks_the_light_that_reads_that_way(emotion, lighting):
    r = L.suggest_shot(shot(emotion=emotion, intensity=8))
    assert terms(r)["lighting"] == lighting and r["why"]


def test_a_quiet_shot_gets_the_calmer_choice_and_a_loud_one_the_restless_choice():
    assert terms(L.suggest_shot(shot(emotion="rage", intensity=9)))["movement"] == "handheld"
    assert terms(L.suggest_shot(shot(emotion="rage", intensity=5)))["movement"] == "push"                 # restless needs a loud shot
    assert terms(L.suggest_shot(shot(emotion="dread", intensity=2)))["movement"] == "static"
    assert terms(L.suggest_shot(shot(emotion="dread", intensity=2)))["angle"] == "eye"
    assert terms(L.suggest_shot(shot(emotion="dread", intensity=9)))["angle"] == "dutch"
    assert terms(L.suggest_shot(shot(emotion="joy", intensity=2)))["lighting"] == "daylight"


def test_every_suggested_term_is_in_the_camera_vocabulary_and_comes_with_its_wording():
    for _, wants, _ in L.LOOKS:
        for group, (term, calm) in wants.items():
            for t in (term, calm):
                if t:
                    assert any(x[0] == t for x in C.GROUPS[group]), (group, t)
    r = L.suggest_shot(shot())
    assert all(p["wording"] and p["label"] for p in r["proposals"])


def test_what_the_director_already_wrote_is_left_alone():
    r = L.suggest_shot(shot(lighting="low-key chiaroscuro lighting", camera_movement="slow push-in"))
    assert "lighting" not in terms(r) and "movement" not in terms(r)                                       # both already named
    assert "angle" in terms(r)


def test_a_persons_own_choice_is_never_overruled():
    r = L.suggest_shot(shot(), {"lighting": "neon", "movement": "orbit"})
    assert "lighting" not in terms(r) and "movement" not in terms(r)
    assert L.suggest_shot(shot(), {"lighting": "neon", "movement": "orbit", "angle": "high"}) is None      # nothing left to add


@pytest.mark.parametrize("emotion", ["", None, "   ", "indifferent", 5])
def test_no_feeling_or_an_unknown_one_suggests_nothing_and_never_crashes(emotion):
    assert L.suggest_shot(shot(emotion=emotion)) is None


def test_junk_intensity_does_not_crash():
    assert L.suggest_shot(shot(intensity="very"))
    assert L.suggest_shot(shot(intensity=None))


def test_the_whole_project_is_read_and_a_note_explains_when_there_is_nothing(tmp_path):
    d = project(tmp_path, [shot(1, "dread"), shot(2, "joy"), shot(3, "")])
    r = L.suggest(d)
    assert r["count"] == 2 and [x["shot"] for x in r["shots"]] == ["S01-01", "S01-02"]
    empty = project(tmp_path / "e" if (tmp_path / "e").mkdir() is None else tmp_path, [shot(1, "")])
    assert "no feeling set" in L.suggest(empty)["note"]
    assert L.suggest(str(tmp_path / "nowhere"))["shots"] == []


def test_applying_writes_ordinary_camera_choices_and_then_nothing_is_left_to_suggest(tmp_path):
    d = project(tmp_path, [shot(1, "dread", 8), shot(2, "joy", 8)])
    out = L.suggest_apply(d, ["S01-01"])
    assert out == {"changed": ["S01-01"]}
    saved = json.load(open(os.path.join(d, "camera.json")))
    assert saved["S01-01"]["lighting"] == "lowkey" and saved["S01-01"]["movement"] == "push" and "S01-02" not in saved
    assert [x["shot"] for x in L.suggest(d)["shots"]] == ["S01-02"]                                            # the applied shot has nothing left
    C.reset(d, ["S01-01"])
    assert L.suggest(d)["count"] == 2                                                                           # clearing the choice brings the suggestion back


def test_applying_to_a_shot_with_no_suggestion_or_a_bad_id_changes_nothing(tmp_path):
    d = project(tmp_path, [shot(1, "")])
    assert L.suggest_apply(d, ["S01-01", "S99-99", 5, None]) == {"changed": []}
    assert not os.path.exists(os.path.join(d, "camera.json"))


def test_a_suggested_choice_reaches_the_prompt(tmp_path):
    from filmcrafter_engine import render as R
    d = project(tmp_path, [shot(1, "dread", 8)])
    L.suggest_apply(d, ["S01-01"])
    sh = json.load(open(os.path.join(d, "production.json")))["scenes"][0]["shots"][0]
    out = C.apply(d, sh)
    assert "low-key" in out.get("lighting", "") and "push" in (out.get("camera_movement") or "")


def test_the_engine_and_the_app_agree_on_the_actions():
    lib = open(os.path.join(os.path.dirname(__file__), "..", "..", "src-tauri", "src", "lib.rs"), encoding="utf-8").read()
    assert '"suggest", "suggest_apply"' in lib
    assert 'choices=["vocab", "get", "set", "reset", "suggest", "suggest_apply"]' in open(C.__file__, encoding="utf-8").read()
