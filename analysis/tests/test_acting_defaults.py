"""Acting defaults: a new project starts with the Natural acting style (so micro-motion is in the prompt from the first render), and the closing note of a shot's acting direction never
contradicts the intensity the shot was directed at (it used to say 'heightened and visible' and then 'no mugging or exaggerated poses')."""
import os
import re

import pytest

from filmcrafter_engine import performance as PF, render as R

SCRIPT = "\n".join(["INT. KITCHEN - MORNING", "", "Sarah pours tea.", "", "SARAH", "Hello.", ""])


def test_a_new_film_is_created_with_the_natural_acting_style(tmp_path):
    import json
    from filmcrafter_engine import bible, make, shots, story
    d = story.create(str(tmp_path), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    shots.breakdown(d)
    pj = json.load(open(os.path.join(make.sync(d)["render_dir"], "project.json")))
    assert pj["performance"]["default"] == "natural" and pj["lip_sync_mode"] == "auto"
    pj["performance"]["default"] = "dramatic"                                  # a choice the person made is never reset by the next sync
    json.dump(pj, open(os.path.join(make.render_dir(d), "project.json"), "w"))
    assert json.load(open(os.path.join(make.sync(d)["render_dir"], "project.json")))["performance"]["default"] == "dramatic"


def test_a_project_with_that_default_gets_the_micro_motion_in_its_video_prompts():
    project = {"performance": {"default": "natural", "scenes": {}, "characters": {}, "shots": {}}}
    shot = {"id": "S01-01", "performers": ["Ada"], "performance_intensity": 5}
    d = PF.direction(project, shot, video=True)
    assert d and d["id"] == "natural" and "blinks" in d["extra"] and "breathing" in d["extra"]
    assert PF.direction({}, shot, video=True) is None                                # a project that never chose one is unchanged: nothing is added behind its back


def test_a_chosen_default_is_what_the_panel_button_writes(tmp_path):
    import json
    d = str(tmp_path)
    json.dump({"title": "T"}, open(os.path.join(d, "project.json"), "w"))
    got = PF.set_(d, {"default": "natural"})
    assert got["set"] is True and got["default"] == "natural"
    assert json.load(open(os.path.join(d, "project.json")))["performance"]["default"] == "natural"


@pytest.mark.parametrize("n,gentle", [(None, True), (1, True), (4, True), (5, True), (6, False), (7, False), (8, False), (10, False), ("x", True)])
def test_the_closing_note_agrees_with_the_intensity(n, gentle):
    note = R.default_play(n)
    assert ("no mugging or exaggerated poses" in note) is gentle
    assert "never mugging" in note or "no mugging" in note                            # nobody is ever asked to mug


def test_a_heightened_shot_is_not_told_to_avoid_exaggerated_poses():
    shot = {"emotion": "embarrassed realization", "performance_intensity": 7, "performers": ["Beatrice"], "performance": "She touches the glasses."}
    text = R.acting_direction(shot, {"characters": []})
    assert "heightened and visible" in text and "exaggerated poses" not in text


def test_a_quiet_shot_keeps_the_truthful_note():
    shot = {"emotion": "calm", "performance_intensity": 2, "performers": ["Beatrice"], "performance": "She waits."}
    text = R.acting_direction(shot, {"characters": []})
    assert "restrained" in text and "no mugging or exaggerated poses" in text


def test_a_chosen_acting_style_still_replaces_the_default_note():
    shot = {"emotion": "joy", "performance_intensity": 9, "performers": ["Beatrice"], "performance": "She dances."}
    text = R.acting_direction(shot, {"characters": []}, play="Play it with energy: bodies move with the beat.")
    assert text.endswith("Play it with energy: bodies move with the beat.") and "Commit fully" not in text
