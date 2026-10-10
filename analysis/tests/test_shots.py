"""Scenes and shots: a director's first draft, Shot Contracts, and editing that never loses work."""
import json
import os

import pytest

from filmcrafter_engine import bible, shots, story

SCRIPT = """INT. KITCHEN - MORNING

Sarah pours tea. Her hands are not steady. A letter lies by the sink.

SARAH
(quietly)
He said he would call.

JOHN
Did you say something?

SARAH
No.

EXT. PLATFORM - NIGHT

Rain on the roof. A train waits.

SARAH
I am going.
"""


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    return d


def test_the_script_is_read_into_scenes_of_action_and_dialogue():
    sc = shots.scene_blocks(SCRIPT)
    assert [s["number"] for s in sc] == [1, 2]
    kinds = [b["type"] for b in sc[0]["blocks"]]
    assert kinds == ["action", "dialogue", "dialogue", "dialogue"]
    assert sc[0]["blocks"][1]["speaker"] == "SARAH" and sc[0]["blocks"][1]["paren"] == "quietly"


def test_a_breakdown_drafts_shots_for_every_scene_with_a_wide_to_open(film):
    r = shots.breakdown(film)
    ids = [s["id"] for s in r["shots"]]
    assert ids[0] == "S01-01" and any(i.startswith("S02-") for i in ids) and len(r["made"]) == len(ids)
    first = shots.get_shot(film, "S01-01")["shot"]
    assert first["camera"]["framing"] in ("wide", "establishing") and "Kitchen" in first["story_purpose"] and first["status"] == "draft" and not first["edited"]
    exch = [shots.get_shot(film, i)["shot"] for i in ids if i.startswith("S01-")]
    assert any(c["camera"]["framing"] == "over the shoulder" for c in exch)                       # two people talking get coverage
    assert all(c["generation"]["duration"] >= 2 for c in exch)


def test_shots_are_linked_to_the_bible_by_name(film):
    shots.breakdown(film)
    dlg = next(c for c in (shots.get_shot(film, s["id"])["shot"] for s in shots.view(film)["shots"]) if c["dialogue"])
    sarah = next(x for x in dlg["characters"] if x["name"] == "SARAH")
    assert sarah["character_id"] == "c_sarah" and sarah["state_id"] == "s1"
    assert dlg["environment"]["id"] == "e_kitchen"


def test_running_a_breakdown_again_changes_nothing(film):
    a = shots.breakdown(film)
    shots.set_fields(film, "S01-01", {"story_purpose": "Mine"})
    b = shots.breakdown(film)
    assert b["made"] == [] and [s["id"] for s in b["shots"]] == [s["id"] for s in a["shots"]]
    assert shots.get_shot(film, "S01-01")["shot"]["story_purpose"] == "Mine"


def test_redoing_a_scene_replaces_untouched_drafts_but_never_edited_shots(film):
    shots.breakdown(film)
    r = shots.breakdown(film, 2)
    assert r["made"] and all(m.startswith("S02-") for m in r["made"])
    shots.set_fields(film, "S02-01", {"title": "Edited"})
    with pytest.raises(SystemExit, match="have been edited"):
        shots.breakdown(film, 2)
    assert shots.get_shot(film, "S02-01")["shot"]["title"] == "Edited"


def test_only_a_screenplay_can_be_broken_down(tmp_path):
    d = story.create(str(tmp_path), "T", "idea", "A widow finds a phone.")["dir"]
    with pytest.raises(SystemExit, match="Break down a screenplay"):
        shots.breakdown(d)


def test_the_contract_takes_only_known_fields_and_camera_words_from_the_lists(film):
    shots.breakdown(film)
    r = shots.set_fields(film, "S01-01", {"camera": {"framing": "close-up", "movement": "dolly", "lens": "macro", "focus": "shallow", "position": "behind her"},
                                          "lighting": {"description": "Window light"}, "bogus": "x", "generation": {"duration": 4.46}})
    c = r["shot"]
    assert c["camera"]["framing"] == "close-up" and c["camera"]["position"] == "behind her" and c["generation"]["duration"] == 4.5 and "bogus" not in c and c["edited"]
    for bad in ({"camera": {"framing": "dramatic"}}, {"camera": {"movement": "teleport"}}, {"generation": {"duration": "long"}}):
        with pytest.raises(SystemExit):
            shots.set_fields(film, "S01-01", bad)
    r = shots.set_fields(film, "S01-01", {"story_purpose": "x" * 9000})
    assert len(r["shot"]["story_purpose"]) == shots.LIMIT


def test_performance_beats_carry_what_the_character_wants_needs_fears_and_hides(film):
    shots.breakdown(film)
    beat = {"character": "Sarah", "what": "Holds the cup too tightly", "want": "He calls", "need": "To accept he will not", "fear": "Being alone", "hiding": "That she packed", "subtext": "Stay",
            "start": "Hopeful", "turn": "Doubt", "end": "Resolve", "x": "no"}
    r = shots.set_fields(film, "S01-02", {"performance": {"emotional_intention": "Held-back dread", "beats": [beat], "micro_animation": "Slow breath, a swallow before she speaks"}})
    b = r["shot"]["performance"]["beats"][0]
    assert b["hiding"] == "That she packed" and "x" not in b and r["shot"]["performance"]["micro_animation"].startswith("Slow breath")


def test_a_locked_storyboard_protects_the_framing(film):
    shots.breakdown(film)
    c = shots.get_shot(film, "S01-01")["shot"]
    c["locks"]["storyboard"] = True
    shots._write(shots._cpath(film, "S01-01"), c)
    with pytest.raises(SystemExit, match="storyboard is locked"):
        shots.set_fields(film, "S01-01", {"camera": {"framing": "wide"}})
    shots.set_fields(film, "S01-01", {"sound": "Rain"})                                # words that do not change the picture are fine


def test_adding_duplicating_moving_merging_splitting_and_removing(film):
    shots.breakdown(film)
    n = len(shots.view(film)["shots"])
    r = shots.add(film, 1)
    assert len(r["shots"]) == n + 1 and shots.get_shot(film, r["id"])["shot"]["edited"]
    r2 = shots.duplicate(film, "S01-01")
    assert r2["id"] != "S01-01" and len(r2["shots"]) == n + 2
    order = [s["id"] for s in r2["shots"]]
    r3 = shots.move(film, order[0], 1)
    assert [s["id"] for s in r3["shots"]][:2] == [order[1], order[0]]
    before = len(r3["shots"])
    first_two = [s["id"] for s in r3["shots"] if s["scene"] == 1][:2]
    m = shots.merge(film, first_two[0])
    assert len(m["shots"]) == before - 1
    removed = shots.delete(film, "S02-01")
    assert "S02-01" not in [s["id"] for s in removed["shots"]]
    assert os.listdir(os.path.join(film, "shots", "_removed"))                            # kept, not deleted
    with pytest.raises(SystemExit, match="doesn't exist"):
        shots.delete(film, "S99-99")


def test_split_cuts_dialogue_or_action_in_two(film):
    shots.breakdown(film)
    sid = next(s["id"] for s in shots.view(film)["shots"] if len(shots.get_shot(film, s["id"])["shot"]["dialogue"]) >= 2 or ". " in shots.get_shot(film, s["id"])["shot"]["action"])
    before = len(shots.view(film)["shots"])
    r = shots.split(film, sid)
    assert len(r["shots"]) == before + 1
    with pytest.raises(SystemExit, match="nothing to split"):
        shots.split(film, shots.add(film, 2)["id"])


def test_suggestions_come_with_a_reason_and_are_not_applied(film):
    shots.breakdown(film)
    shots.set_fields(film, "S01-02", {"performance": {"emotional_intention": "Held-back dread"}})
    s = shots.suggest(film, "S01-02")
    assert s["camera"]["framing"] == "over the shoulder" and s["camera"]["angle"] == "low" and s["camera"]["movement"] == "handheld" and "Tension" in s["camera"]["why"] and s["lighting"]["why"]
    assert shots.get_shot(film, "S01-02")["shot"]["camera"]["angle"] == "eye level"        # only a suggestion
    night = shots.suggest(film, next(i["id"] for i in shots.view(film)["shots"] if i["scene"] == 2))
    assert "Moon" in night["lighting"]["description"] or "street" in night["lighting"]["description"]


def test_ids_from_outside_are_never_paths(film):
    shots.breakdown(film)
    for bad in ("../../evil", "..\\x", "a/b"):
        with pytest.raises(SystemExit, match="not valid"):
            shots.get_shot(film, bad)


def test_the_command_line(film, capsys):
    rc = shots.main(["breakdown", film])
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0 and out["data"]["made"]
    assert shots.main(["shot", film, "--data", json.dumps({"id": "S01-01"})]) == 0
    capsys.readouterr()
    assert shots.main(["get", film + "-nope"]) == 1
