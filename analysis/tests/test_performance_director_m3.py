"""Performance Director, steps three to five (free, local): the kind of character, what a shot's prompt needs, the honest model labels, the delivery hint and the emotional arc flags.
Nothing here calls an AI or a provider."""
import json
import os

import pytest

from filmcrafter_engine import acting as A, character_performance as CP, emotional_continuity as EC, model_capabilities as MC
from filmcrafter_engine import performance_director as PD, performance_prompts as PP, render as R
from tests.test_performance_director import film, prompt_for, shot_ids  # noqa: F401  (the same small film)


# ---------------------------------------------------------------- the kind of character

def test_a_kind_is_saved_only_when_it_is_one_of_the_known_kinds(film):
    f, rd = film
    CP.set_fields(rd, "Sarah", {"kind": "robot"})
    assert CP.get(rd)["people"][0]["profile"]["kind"] == "robot"
    with pytest.raises(SystemExit):
        CP.set_fields(rd, "Sarah", {"kind": "wizard"})
    assert CP.get(rd)["people"][0]["profile"]["kind"] == "robot"                 # the refused one changed nothing
    CP.set_fields(rd, "Sarah", {"kind": ""})
    assert CP.get(rd)["people"][0]["profile"]["kind"] == ""


def test_nothing_is_added_for_a_person_or_when_no_kind_was_chosen(film):
    f, rd = film
    assert PP.text(rd, {"performers": ["Sarah"], "description": "She stands by the window."}) is None
    CP.set_fields(rd, "Sarah", {"kind": "human"})
    assert PP.text(rd, {"performers": ["Sarah"], "description": "She stands by the window."}, "2d") is None


@pytest.mark.parametrize("kind,word", [("robot", "no human facial muscles"), ("animal", "ears, the tail"), ("creature", "creature"), ("stylised", "shape changes")])
def test_a_non_human_kind_names_the_channels_that_can_carry_the_feeling(film, kind, word):
    f, rd = film
    CP.set_fields(rd, "Sarah", {"kind": kind})
    out = PP.text(rd, {"performers": ["Sarah"], "description": "She waits."}, "")
    assert word in out and "Sarah" in out


def test_the_look_family_changes_the_wording_for_a_non_human(film):
    f, rd = film
    CP.set_fields(rd, "Sarah", {"kind": "robot"})
    shot = {"performers": ["Sarah"], "description": "She waits."}
    clay, filmed = PP.text(rd, shot, "craft"), PP.text(rd, shot, "photoreal")
    assert "hand-made" in clay and "hand-made" not in filmed and "truthful" in filmed


def test_effort_and_contact_lines_come_only_from_the_shots_own_words(film):
    f, rd = film
    assert "physical effort" in PP.text(rd, {"performers": ["Sarah"], "description": "She drags the heavy trunk up the stairs."})
    assert PP.text(rd, {"performers": ["Sarah"], "description": "She is quiet."}) is None
    both = PP.text(rd, {"performers": ["Sarah", "John"], "description": "John hugs Sarah."})
    assert "contact" in both
    assert PP.text(rd, {"performers": ["Sarah"], "description": "She hugs the pillow."}) is None        # contact needs two people


def test_it_reaches_the_prompt_and_is_cut_first_when_there_is_no_room(film):
    f, rd = film
    CP.set_fields(rd, "Sarah", {"kind": "robot"})
    assert "no human facial muscles" in prompt_for(rd, shot_ids(rd)[0])


# ---------------------------------------------------------------- honest model labels

def test_only_a_recorded_real_render_is_called_tested_and_acting_is_never_verified():
    d = MC.describe("fal", "fal-ai/kling-video/v3/turbo/pro/image-to-video")
    rows = {r["feature"]: r for r in d["features"]}
    assert rows["renders"]["status"] == "tested" and "QA render" in rows["renders"]["source"]
    assert all(rows[k]["status"] == "unverified" for k in ("follows_emotion_prompt", "holds_gaze", "timed_beats", "keeps_face_across_shots"))
    u = {r["feature"]: r for r in MC.describe("fal", "not-a-model")["features"]}
    assert u["renders"]["status"] == "unverified" and not MC.describe("fal", "not-a-model")["known"]
    assert "not verified" in MC.summary("fal", "not-a-model")


def test_a_speech_model_that_reads_tags_is_documented_and_one_that_does_not_is_unsupported():
    on = {r["feature"]: r for r in MC.describe("elevenlabs", "eleven_v4")["features"]}
    off = {r["feature"]: r for r in MC.describe("elevenlabs", "eleven_multilingual_v2")["features"]}
    assert on["direction_tags"]["status"] == "documented" and off["direction_tags"]["status"] == "unsupported"


# ---------------------------------------------------------------- the delivery hint

def test_a_delivery_hint_comes_only_from_beats_you_wrote(film):
    f, rd = film
    sid = shot_ids(rd)[0]
    assert PP.delivery_hint(rd, sid, "Sarah") is None
    A.beats_set(rd, sid, [{"t0": 0, "t1": 1, "what": "She looks away"}], source="auto")
    assert PP.delivery_hint(rd, sid, "Sarah") is None                              # a draft is not used
    A.beats_set(rd, sid, [{"t0": 0, "t1": 1, "what": "She looks away"}], source="you")
    A.nudge_set(rd, sid, "restrained", 1)
    h = PP.delivery_hint(rd, sid, "Sarah", reads_tags=True)
    assert "quiet and held back" in h["hint"] and "looks away" in h["hint"] and h["tag"] == "[quiet and held back]"
    assert PP.delivery_hint(rd, sid, "Sarah", reads_tags=False)["tag"] is None


# ---------------------------------------------------------------- the emotional arc

def pts(*rows):
    return [{"section": f"S{i}", "emotion": e, "intensity": n} for i, (e, n) in enumerate(rows, 1)]


def kinds(track):
    return sorted(f["kind"] for f in EC.flags_for("Sarah", track))


def test_a_sudden_swing_a_stall_and_a_stretch_at_full_strength_are_each_pointed_at():
    assert "abrupt" in kinds(pts(("calm", 2), ("furious", 8)))
    assert "abrupt" not in kinds(pts(("calm", 2), ("uneasy", 5)))
    assert "abrupt" not in kinds(pts(("calm", 2), ("calm", 8)))                      # the same feeling getting stronger is a build, not a jump
    assert "flat" in kinds(pts(("numb", 4), ("numb", 4), ("numb", 4)))
    assert "flat" not in kinds(pts(("numb", 4), ("numb", 5), ("numb", 4)))
    assert "nonstop" in kinds(pts(("angry", 8), ("afraid", 9), ("desperate", 10)))
    assert "unrested" in kinds(pts(("furious", 9), ("calm", 2)))
    assert kinds(pts(("calm", 3), ("curious", 5), ("hopeful", 6))) == []


def test_a_flag_can_be_dismissed_and_brought_back_and_a_bad_id_is_refused(film):
    f, rd = film
    names = A.arc_get(rd)["sections"]
    assert len(names) >= 2
    A.arc_set(rd, "Sarah", [{"section": names[0], "emotion": "calm", "intensity": 1}, {"section": names[1], "emotion": "furious", "intensity": 9}])
    got = EC.get(rd)
    sarah = next(p for p in got["people"] if p["name"] == "Sarah")
    assert [x["kind"] for x in sarah["flags"]] == ["abrupt"]
    fid = sarah["flags"][0]["id"]
    after = next(p for p in EC.dismiss(rd, fid)["people"] if p["name"] == "Sarah")
    assert after["flags"] == [] and after["dismissed"] == 1
    back = next(p for p in EC.dismiss(rd, fid, undo=True)["people"] if p["name"] == "Sarah")
    assert len(back["flags"]) == 1
    with pytest.raises(SystemExit):
        EC.dismiss(rd, "not a flag")
    assert os.path.isfile(os.path.join(CP.root(rd), "emotion.json"))


def test_the_arc_view_is_empty_not_broken_for_a_film_with_no_arcs(film):
    f, rd = film
    got = EC.get(rd)
    assert all(p["track"] == [] and p["flags"] == [] for p in got["people"])


# ---------------------------------------------------------------- the one door

def test_the_new_actions_go_through_the_one_door_and_are_in_the_allow_list(film):
    f, rd = film
    for a in ("kind_options", "continuity_get", "continuity_dismiss", "model_labels", "delivery_hint"):
        assert a in PD.ACTIONS
    assert PD.run(rd, "kind_options", {})["kinds"][0]["id"] == "human"
    assert PD.run(rd, "continuity_get", {})["people"] is not None
    out = PD.run(rd, "model_labels", {"provider": "fal", "model": "fal-ai/nano-banana/edit"})
    assert out["features"][0]["status"] == "tested"
    assert PD.run(rd, "delivery_hint", {"shot": shot_ids(rd)[0], "speaker": "Sarah"})["hint"] is None
    with pytest.raises(SystemExit):
        PD.run(rd, "continuity_dismiss", {"flag": "nope"})
