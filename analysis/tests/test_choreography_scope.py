"""Dance direction only where a shot is about dancing. Notes written for a song section used to reach every shot of it where those people appear, so a shot of a woman unrolling a
runner was also told to 'enter in color order' and 'carry no object'. Now: a shot whose own text is not about dancing is told the action wins and gets no dance pose in its keyframe;
a person can say 'always' or 'never' for a shot; and a designed choreography plan is untouched."""
import json
import os

import pytest

from pulseframe_analysis import onboarding as OB, performance as PF, render as R

NOTES = ("[Producer] Auntie Mercy (group dance choreography): Assembly Step: Enter in color order and form rear line, Mercy left Patience center Blessing right.; "
         "Short forward walking steps; Carry no object during final formation; Upright; Queen; West doorway to north platform")
RUNNER = {"id": "S01-03", "scene": 1, "number": 3, "start": 8.5, "end": 10.2, "section": "Verse 1", "performers": ["Auntie Mercy", "Beatrice"],
          "description": "Auntie Mercy unrolls a red runner across the floor toward the foreground while Beatrice watches.",
          "beats": ["Auntie Mercy unrolls a red runner across the floor."], "performance": "Mercy focuses on the runner with practical determination.",
          "movement": "Mercy unrolls the red runner forward across the floor; Beatrice remains watchful and composed."}
DANCE = {**RUNNER, "id": "S01-04", "description": "Auntie Mercy and the aunties dance the assembly step in formation to the beat.", "beats": ["The aunties dance in formation."],
         "performance": "Joyful, rehearsed.", "movement": "Short forward steps in a line."}


@pytest.fixture
def d(tmp_path):
    d = str(tmp_path)
    json.dump({"title": "T", "song": "song.wav"}, open(os.path.join(d, "project.json"), "w"))
    OB.choreo_set(d, {"mode": "written", "sections": [{"section": "Verse 1", "performers": ["Auntie Mercy"], "notes": NOTES}]})
    return d


def set_dance(d, mapping):
    PF.set_(d, {"dance": mapping})


# ---------------------------------------------------------------- which shots are about dancing

@pytest.mark.parametrize("text,yes", [("They dance in formation", True), ("a choreographed entrance", True), ("grooving to the beat", True), ("swaying with the music", True),
                                      ("she moves on the beat", True), ("the routine begins", True), ("unrolls a red runner", False), ("steps toward the door", False),
                                      ("carries a tray of food", False), ("a wide shot of the room", False), ("", False)])
def test_a_shot_is_about_dancing_when_its_own_text_says_so(text, yes):
    assert OB.is_dance_shot({"description": text}) is yes


def test_the_song_section_a_shot_sits_in_says_nothing_about_that_shot():
    assert OB.is_dance_shot({"section": "Dance break", "description": "She unrolls a runner."}) is False


# ---------------------------------------------------------------- what the prompt is told

def test_a_shot_that_is_not_dancing_is_told_the_action_wins(d):
    v = OB.movement_for(d, RUNNER, "video")
    assert v.startswith("Dance direction for this song section applies only if this shot's action is dancing") and "always wins" in v
    assert not v.startswith("Choreography:") and len(v) < 160                          # one sentence: a hint, not a second script
    assert "Assembly" not in v and "color order" not in v and "Carry no object" not in v   # and none of the steps, which in a shot about something else only confuse


def test_a_shot_with_no_text_at_all_keeps_the_full_direction(d):
    """Nothing says it is not about dancing, so it is treated as before (shots made by hand, or planned before anyone described them)."""
    bare = {"id": "S01-09", "scene": 1, "start": 0.0, "end": 2.0, "section": "Verse 1", "performers": ["Auntie Mercy"]}
    assert OB.movement_for(d, bare, "video").startswith("Choreography: ") and OB.movement_for(d, bare, "image").startswith("Movement direction: ")


def test_a_keyframe_of_a_shot_that_is_not_dancing_gets_no_dance_pose(d):
    assert OB.movement_for(d, RUNNER, "image") is None


def test_a_dance_shot_gets_the_full_direction(d):
    assert OB.movement_for(d, DANCE, "video").startswith("Choreography: ") and "Assembly Step" in OB.movement_for(d, DANCE, "video")
    assert OB.movement_for(d, DANCE, "image").startswith("Movement direction: ")


def test_always_gives_a_shot_the_full_direction_and_never_removes_it(d):
    set_dance(d, {"S01-03": "on", "S01-04": "off"})
    assert OB.movement_for(d, RUNNER, "video").startswith("Choreography: ")
    assert OB.movement_for(d, RUNNER, "image").startswith("Movement direction: ")
    assert OB.movement_for(d, DANCE, "video") is None and OB.movement_for(d, DANCE, "image") is None


def test_automatic_puts_a_shot_back_to_deciding_for_itself(d):
    set_dance(d, {"S01-03": "on"})
    set_dance(d, {"S01-03": "auto"})
    assert OB.movement_for(d, RUNNER, "video").startswith("Dance direction for this song section applies only")
    assert OB.dance_override(d, "S01-03") == "auto"


def test_other_people_are_not_affected(d):
    other = {**RUNNER, "performers": ["Solomon"]}
    assert OB.movement_for(d, other, "video") is None                                  # the notes were written for Mercy only (unchanged behaviour)


def test_a_designed_choreography_plan_is_untouched(d):
    c = OB.choreo_get(d)
    c["plan"] = {"bpm": 120, "shots": {"S01-03": {"dancing": True, "pose": "arms up", "motion": "the aunties pulse in a line", "energy": 5}}}
    json.dump(c, open(os.path.join(d, "choreography.json"), "w"))
    assert OB.movement_for(d, RUNNER, "video").startswith("Choreography (dance, on the beat at 120 BPM): the aunties pulse")      # the plan said this shot dances
    assert OB.movement_for(d, {**RUNNER, "id": "S01-09"}, "video") is None                                                   # a plan exists and this shot is acting-led


def test_the_style_that_means_no_dance_still_means_no_dance(d):
    OB.choreo_set(d, {"mode": "written", "style": "Minimal performance (no dance)", "sections": [{"section": "Verse 1", "performers": ["Auntie Mercy"], "notes": NOTES}]})
    set_dance(d, {"S01-03": "on"})
    assert OB.movement_for(d, RUNNER, "video") is None


# ---------------------------------------------------------------- the choice is stored safely

def test_choosing_dance_direction_does_not_switch_acting_on_for_the_project(d):
    before = json.load(open(os.path.join(d, "project.json")))
    got = PF.set_(d, {"dance": {"S01-03": "off"}})
    after = json.load(open(os.path.join(d, "project.json")))
    assert "performance" not in after and after["dance_shots"] == {"S01-03": "off"}       # no acting profile appeared, so no prompt text changed elsewhere
    assert got["dance"] == {"S01-03": "off"} and "performance" not in before


def test_a_bad_choice_is_refused_and_changes_nothing(d):
    with pytest.raises(SystemExit, match="automatic, always or never"):
        PF.set_(d, {"dance": {"S01-03": "maybe"}})
    assert "dance_shots" not in json.load(open(os.path.join(d, "project.json")))


def test_a_damaged_project_file_means_automatic(d):
    open(os.path.join(d, "project.json"), "w").write("{not json")
    assert OB.dance_override(d, "S01-03") == "auto"
    json.dump({"dance_shots": ["x"]}, open(os.path.join(d, "project.json"), "w"))
    assert OB.dance_override(d, "S01-03") == "auto"


# ---------------------------------------------------------------- the whole prompt, as the render builds it

def test_the_runner_shots_prompt_no_longer_contradicts_its_action(d, monkeypatch):
    from tests.test_native_dialogue import _talking
    shot = R._with_movement(d, dict(RUNNER))
    req = R.compile_request(shot, None, {"meta": {}, "characters": [], "scenes": []}, {"look": {"style": "auto"}}, _talking(), [])
    prompt = req["prompt"]
    assert "Dance direction for this song section applies only if this shot's action is dancing" in prompt
    assert "Choreography: " not in prompt and "Carry no object" not in prompt and "color order" not in prompt
    assert "unrolls a red runner" in prompt                                                # the action is still there, first
