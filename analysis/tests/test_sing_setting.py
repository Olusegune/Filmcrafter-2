"""Who sings. A song narrated by someone who is not on screen (a man remembering his childhood) must not get a child's mouth lip-synced to a grown man's voice, and the person has the last word."""
import json
import os

import pytest

from filmcrafter_engine import render as R
from tests.test_lipsync_mode import preview

PLAN = {"characters": [{"name": "Sege"}], "meta": {}}


def project(tmp_path, performers, framing="Low medium shot, close enough for the face", project_extra=None, lyrics=None, description="", plan=PLAN):
    d = tmp_path / "p"
    d.mkdir(exist_ok=True)
    json.dump({"title": "T", "song": "song.wav", **(project_extra or {})}, open(d / "project.json", "w"))
    json.dump({"duration": 20, "lyrics": lyrics or [{"text": "How to read a face", "start": 4.0, "end": 6.5}], "sections": []}, open(d / "songmap.json", "w"))
    shot = {"id": "S02-05", "start": 4.0, "end": 6.0, "performers": performers, "framing": framing, "description": description, "beats": []}
    return str(d), shot, plan


def sings(*a, **k):
    d, shot, plan = project(*a, **k)
    return R.singing(d, shot, plan)


def test_the_lead_in_a_medium_shot_is_taken_to_sing_the_vocal(tmp_path):
    r = sings(tmp_path, ["Sege"])
    assert r and r["performer"] == "Sege" and r["lyrics"] == ["How to read a face"]


def test_someone_else_on_screen_is_not_assumed_to_sing_it(tmp_path):
    """The reported case: Young Sege and 'indistinct adult figures' while the grown man narrates."""
    assert sings(tmp_path, ["Young Sege", "indistinct adult figures"]) is None


def test_unless_the_shots_own_words_say_someone_sings_or_speaks(tmp_path):
    r = sings(tmp_path, ["Young Sege"], description="The boy sings along under his breath.")
    assert r and r["performer"] == "Young Sege"


def test_a_shot_marked_as_singing_always_does_even_a_wide_one_without_the_lead(tmp_path):
    assert sings(tmp_path, ["Young Sege"], framing="wide shot", project_extra={"sing_shots": {"S02-05": "on"}})["performer"] == "Young Sege"


def test_a_shot_marked_as_not_singing_never_does_even_the_lead_in_a_close_up(tmp_path):
    assert sings(tmp_path, ["Sege"], framing="close-up", project_extra={"sing_shots": {"S02-05": "off"}}) is None


def test_a_project_whose_vocalist_is_off_screen_sings_nowhere_unless_a_shot_says_so(tmp_path):
    assert sings(tmp_path, ["Sege"], project_extra={"vocalist": "offscreen"}) is None
    assert sings(tmp_path, ["Sege"], project_extra={"vocalist": "offscreen", "sing_shots": {"S02-05": "on"}})["performer"] == "Sege"
    assert sings(tmp_path, ["Sege"], project_extra={"vocalist": "onscreen"}) is not None


def test_a_choice_for_another_shot_changes_nothing_here(tmp_path):
    assert sings(tmp_path, ["Young Sege"], project_extra={"sing_shots": {"S09-09": "on"}}) is None
    assert sings(tmp_path, ["Sege"], project_extra={"sing_shots": {"S09-09": "off"}}) is not None


@pytest.mark.parametrize("junk", [None, "yes", 5, ["on"], {"S02-05": 1}])
def test_junk_in_the_settings_file_is_ignored(tmp_path, junk):
    d, shot, plan = project(tmp_path, ["Sege"], project_extra={"sing_shots": junk})
    assert R.sing_setting(d, shot["id"]) == "auto"
    assert R.singing(d, shot, plan) is not None


def test_spoken_lines_tagged_with_their_speaker_are_not_affected_by_the_off_screen_setting(tmp_path):
    lines = [{"text": "Children!", "start": 4.0, "end": 5.5, "performer": "Beatrice"}]
    d, shot, plan = project(tmp_path, ["Beatrice"], project_extra={"vocalist": "offscreen"}, lyrics=lines)
    r = R.singing(d, shot, plan)
    assert r and r["spoken"] is True and r["performer"] == "Beatrice"


def test_a_project_with_no_known_lead_behaves_as_before(tmp_path):
    assert sings(tmp_path, ["Someone"], plan={"characters": [], "meta": {}})["performer"] == "Someone"


def test_the_vocal_under_a_shot_is_measured_whoever_sings_it(tmp_path):
    d, shot, _ = project(tmp_path, ["Young Sege"])
    assert R._vocal_heard(d, shot) == 2.0
    assert R._vocal_heard(str(tmp_path / "nowhere"), shot) == 0.0


def test_the_preview_says_what_was_chosen_and_how_much_vocal_is_heard(tmp_path, monkeypatch):
    out = preview(tmp_path, monkeypatch, sing_shots={"S01-01": "off"})
    assert out["sing_setting"] == "off" and out["vocal_heard"] > 0 and out["lip_sync"] is False and out["singing"] is None
    (tmp_path / "x").mkdir()
    assert preview(tmp_path / "x", monkeypatch)["sing_setting"] == "auto"


def test_the_app_accepts_the_two_settings():
    lib = open(os.path.join(os.path.dirname(__file__), "..", "..", "src-tauri", "src", "lib.rs"), encoding="utf-8").read()
    assert '"offscreen" } else { "onscreen"' in lib or 'v == "offscreen"' in lib
    assert 'settings["sing_shot"]' in lib and '["auto", "on", "off"]' in lib
