"""The Smart Editor: explainable suggestions for the cut, kept away from anything the person wrote or asked for, previewable, accepted as one change and rejected for good.
Free and local; the footage is made here."""
import json
import os

import pytest

from filmcrafter_engine import acting as A, edit_time as T, editing as ED, export as E, grading as G, library, media, smart_editor as SE
from tests.test_editing import build_film, ff
from tests.test_proxies_recovery import big_clip

pytestmark = pytest.mark.integration

SHOTS = [("S01-01", 1, 0.0, 6.0), ("S01-02", 1, 6.0, 9.0), ("S02-01", 2, 9.0, 12.0)]


@pytest.fixture
def film(tmp_path):
    d = build_film(tmp_path, SHOTS, 12.0)
    plan = json.load(open(os.path.join(d, "production.json")))
    who = {"S01-01": ["Sarah"], "S01-02": ["John"], "S02-01": ["Sarah", "John"]}
    for sc in plan["scenes"]:
        for sh in sc["shots"]:
            sh["performers"] = who[sh["id"]]
    json.dump(plan, open(os.path.join(d, "production.json"), "w"))
    sm = json.load(open(os.path.join(d, "songmap.json")))
    sm["lyrics"] = [{"section": "Scene 1", "text": "Sarah: Hello there my dear old friend how are you", "start": 0.3, "end": 3.0},
                    {"section": "Scene 2", "text": "Sarah: Go now before they find us here", "start": 9.5, "end": 10.0}]            # 9 words in the first shot, 8 in the last (which fill it)
    json.dump(sm, open(os.path.join(d, "songmap.json"), "w"))
    media.import_media(d, "S01-02", big_clip(tmp_path, "long.mp4", "64x64", 6))                         # the listening shot has plenty of picture to spare
    return d


def titles(r):
    return [p["title"] for p in r["proposals"]]


def clip_frames(d, shot):
    return [c["frames"] for c in ED.get(d)["sequence"]["tracks"][0]["clips"] if c["shot"] == shot]


# ---------------------------------------------------------------- what it suggests, and why

def test_a_spoken_clip_that_runs_well_past_its_words_is_suggested_for_tightening_with_a_reason(film):
    r = SE.propose(film)
    p = next(x for x in r["proposals"] if x["kind"] == "tighten")
    assert p["title"] == "Tighten the end of S01-01" and p["clips"] == ["c1"] and p["shots"] == ["S01-01"]
    assert "9 spoken words" in p["why"] and "refuse it if the quiet is the point" in p["why"] and p["what"].startswith("End S01-01") and p["saves"] > 0.7
    assert p["ops"][0]["op"] == "trim" and p["ops"][0]["ripple"] is True and p["window"][0] >= 0
    assert r["recipe"]["id"] == "restrained_drama"


def test_a_listener_after_someone_spoke_is_suggested_a_little_more_time_only_when_there_is_picture_for_it(film, tmp_path):
    p = next(x for x in SE.propose(film)["proposals"] if x["kind"] == "react")
    assert p["shots"] == ["S01-02"] and "John" in p["why"] and "more picture" in p["why"] and p["saves"] < 0
    ff("-f", "lavfi", "-i", "color=c=black:s=64x64:r=24:d=3", "-pix_fmt", "yuv420p", str(tmp_path / "short.mp4"))
    media.import_media(film, "S01-02", str(tmp_path / "short.mp4"))                                      # a take with no spare picture
    assert not [x for x in SE.propose(film)["proposals"] if x["kind"] == "react"]


def test_looking_changes_nothing_and_the_same_cut_gives_the_same_suggestions(film):
    a, b = SE.propose(film), SE.propose(film)
    assert a == b
    assert ED.get(film)["stored"] is False and not os.path.exists(G._path(film)) and not os.path.exists(os.path.join(G.edit_dir(film), "proposals.json"))


# ---------------------------------------------------------------- what it leaves alone

def test_a_pause_you_asked_for_is_kept_and_the_editor_says_it_left_it_alone_on_purpose(film):
    A.nudge_set(film, "S01-01", "hold", 1)
    r = SE.propose(film)
    assert not [p for p in r["proposals"] if p["kind"] == "tighten"]
    k = next(x for x in r["kept"] if x["shot"] == "S01-01")
    assert "Kept the pause" in k["why"] and "hold the reaction longer" in k["why"]
    A.nudge_set(film, "S01-01", "hold", 0)
    A.nudge_set(film, "S01-01", "hesitant", 1)
    assert "hesitant" in next(x for x in SE.propose(film)["kept"] if x["shot"] == "S01-01")["why"]


def test_a_beat_you_wrote_in_the_tail_protects_it_but_a_draft_does_not(film):
    A.beats_set(film, "S01-01", [{"t0": 0, "t1": 5.5, "what": "She waits for him to answer"}], source="auto")
    assert [p for p in SE.propose(film)["proposals"] if p["kind"] == "tighten"]                      # a draft you never kept is not read
    A.beats_set(film, "S01-01", [{"t0": 0, "t1": 5.5, "what": "She waits for him to answer"}], source="you")
    r = SE.propose(film)
    assert not [p for p in r["proposals"] if p["kind"] == "tighten"] and "a beat you wrote" in r["kept"][0]["why"]


def test_a_locked_track_and_hidden_clips_are_not_touched(film):
    ED.run(film, "edit", {"op": "track_set", "track": "V1", "locked": True})
    assert SE.propose(film)["proposals"] == []


# ---------------------------------------------------------------- recipes

def test_a_montage_style_is_tighter_and_does_not_add_reaction_time_and_unbuilt_styles_are_refused(film):
    calm = next(p for p in SE.propose(film)["proposals"] if p["kind"] == "tighten")
    fast = SE.propose(film, "rhythmic_montage")
    quick = next(p for p in fast["proposals"] if p["kind"] == "tighten")
    assert quick["saves"] > calm["saves"] and not [p for p in fast["proposals"] if p["kind"] == "react"]
    with pytest.raises(SystemExit, match="not built"):
        SE.propose(film, "suspense")
    rs = SE.recipes()["recipes"]
    assert len(rs) == 10 and sum(1 for r in rs if r["built"]) == 3 and rs[0]["id"] == "restrained_drama"


# ---------------------------------------------------------------- accepting, rejecting, undoing

def test_accepting_changes_the_cut_by_exactly_the_suggestion_as_one_change_and_one_undo_takes_it_back(film):
    p = next(x for x in SE.propose(film)["proposals"] if x["kind"] == "tighten")
    before = clip_frames(film, "S01-01")[0]
    out = SE.accept(film, p["id"])
    after = clip_frames(film, "S01-01")[0]
    assert out["accepted"] == p["title"] and before - after == round(p["saves"] * 24) and ED.get(film)["sequence"]["length"] == T.tick_of_frame(12 * 24 - (before - after))
    assert ED.get(film)["history"][-1]["what"] == f"accepted: {p['title']}"
    ED.run(film, "undo", {})
    assert clip_frames(film, "S01-01")[0] == before and ED.get(film)["stored"] is False              # all the way back to never edited
    assert p["id"] in [x["id"] for x in SE.propose(film)["proposals"]]                              # and it is offered again, as the cut is as it was


def test_a_rejected_suggestion_stays_away_until_you_ask_for_them_back(film):
    p = next(x for x in SE.propose(film)["proposals"] if x["kind"] == "tighten")
    SE.reject(film, p["id"])
    assert p["id"] not in [x["id"] for x in SE.propose(film)["proposals"]]
    assert json.load(open(os.path.join(G.edit_dir(film), "proposals.json")))["rejected"] == [p["id"]]
    assert SE.reset_rejected(film)["cleared"] == 1
    assert p["id"] in [x["id"] for x in SE.propose(film)["proposals"]]
    assert ED.get(film)["stored"] is False                                                           # rejecting never touched the cut


def test_a_suggestion_that_no_longer_fits_the_cut_is_refused_not_applied(film):
    p = next(x for x in SE.propose(film)["proposals"] if x["kind"] == "tighten")
    ED.run(film, "edit", {"op": "trim", "clip": "c1", "edge": "out", "to": 5.0})                     # the person changed that clip meanwhile
    with pytest.raises(SystemExit, match="no longer applies"):
        SE.accept(film, p["id"])
    with pytest.raises(SystemExit, match="no longer applies"):
        SE.reject(film, "deadbeef00")


def test_accepting_the_listener_suggestion_makes_the_film_longer_by_exactly_that_much(film):
    p = next(x for x in SE.propose(film)["proposals"] if x["kind"] == "react")
    SE.accept(film, p["id"])
    assert clip_frames(film, "S01-02") == [72 + round(-p["saves"] * 24)]


# ---------------------------------------------------------------- the preview

def test_the_preview_is_two_real_clips_of_the_film_before_and_after_and_saves_nothing(film):
    p = next(x for x in SE.propose(film)["proposals"] if x["kind"] == "tighten")
    out = SE.preview(film, p["id"])
    a, b = (os.path.join(film, out[k]) for k in ("before", "after"))
    assert os.path.isfile(a) and os.path.isfile(b) and os.path.getsize(a) > 0 and os.path.getsize(b) > 0
    assert library._duration(b) < library._duration(a) - 0.3                                         # the tightened version is shorter
    assert ED.get(film)["stored"] is False and clip_frames(film, "S01-01") == [144]


# ---------------------------------------------------------------- asking in plain words

def test_a_plain_request_is_read_by_its_words_and_says_what_it_understood(film):
    t = SE.ask(film, "Tighten this scene")
    assert t["understood"] and "Tightening" in t["message"] and titles(t) == ["Tighten the end of S01-01"]
    r = SE.ask(film, "Give the audience more time to process her reaction")
    assert r["understood"] and titles(r) == ["Give S01-02 a little more time"]
    m = SE.ask(film, "make it punchy and tighten scene 1")
    assert m["recipe"]["id"] == "rhythmic_montage" and "In scene 1" in m["message"]
    only2 = SE.ask(film, "tighten scene 2")
    assert only2["understood"] and only2["proposals"] == []


def test_a_request_it_cannot_do_is_said_plainly_and_not_guessed_at(film):
    r = SE.ask(film, "make this transition more cinematic")
    assert r["understood"] is False and r["proposals"] == [] and "did not understand" in r["message"] and len(r["can"]) == 2
    with pytest.raises(SystemExit):
        SE.ask(film, "   ")


def test_the_door_speaks_json_and_its_action_list_is_the_one_the_shell_must_match(film, capsys):
    assert SE.main(["suggest", film]) == 0 and json.loads(capsys.readouterr().out.splitlines()[-1])["data"]["proposals"]
    assert SE.main(["accept", film, "--data", json.dumps({"id": "nope"})]) == 1 and "no longer applies" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="Unknown"):
        SE.run(film, "explode", {})
    src = open(SE.__file__, encoding="utf-8").read()
    for a in SE.ACTIONS:
        assert f'"{a}"' in src.split("choices=")[1].split("]")[0]
