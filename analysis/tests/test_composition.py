"""Composition: thirds, headroom and look room from the shot's size, people and blocking; reaching the request; switched off per film; left out when a storyboard panel is the composition."""
import json
import os

import pytest

from filmcrafter_engine import bible, composition as C, make, render as R, shots as S, story

SCRIPT = ("INT. KITCHEN - NIGHT\n\nSarah pours tea. Rain on the roof.\n\nSARAH\nHe said he would call.\n\nJOHN\nDid you say something?\n")


def field(name, type="string", **kw):
    return {"name": name, "type": type, "items": None, "enum": kw.get("enum"), "default": None, "minimum": None, "maximum": None, "max_items": None,
            "max_length": kw.get("max_length"), "description": kw.get("description", ""), "required": False}


def still():
    return R._finish("fal", "t/i", "Still", "text-to-image", [field("prompt")])


def build(shot, project=None, refs=None):
    s = {"id": "S01-01", "start": 0.0, "end": 4.0, "performers": [], "beats": ["x"], **shot}
    return R.compile_request(s, None, {"meta": {}}, project or {"look": {"style": "auto"}}, still(), refs or [])


def test_the_shot_size_is_read_from_the_framing_words():
    for words, size in (("Close-up", "close"), ("Extreme close-up", "extreme_close"), ("Medium close-up", "medium_close"), ("Medium, low angle", "medium"), ("Wide", "wide"), ("Establishing", "extreme_wide"),
                        ("Over the shoulder", "ots"), ("Point of view", "pov"), ("Insert", "insert"), ("Full body", "full"), ("", "medium")):
        assert C.size_of(words) == size, words


def test_people_and_which_way_they_face_are_read_from_the_blocking_words():
    p = C.people_from_text("Blocking as the camera sees it: Sarah screen-left, facing screen-right; John screen-right, facing screen-left.")
    assert [(x["name"], x["side"], x["facing"]) for x in p] == [("Sarah", "left", "right"), ("John", "right", "left")]
    q = C.people_from_text("Blocking (keep across the scene): Lila screen-right facing left; Chloe screen-left facing right.")
    assert [(x["name"], x["side"], x["facing"]) for x in q] == [("Lila", "right", "left"), ("Chloe", "left", "right")]
    assert C.people_from_text("nothing here") == []


def test_one_person_is_placed_opposite_the_way_they_face_so_there_is_look_room():
    g = C.guide("Close-up", ["Sarah"], "Sarah screen-left, facing screen-right")
    assert g["points"][0]["x"] == pytest.approx(1 / 3, abs=0.01) and "look room on the right" in g["text"]
    g = C.guide("Medium", ["John"], "John screen-right, facing screen-left")
    assert g["points"][0]["x"] == pytest.approx(2 / 3, abs=0.01) and g["points"][0]["y"] == pytest.approx(1 / 3, abs=0.01)
    assert "upper third" in g["text"] and "Headroom" in g["text"]


def test_two_people_take_opposite_thirds_facing_in():
    g = C.guide("Medium", ["Sarah", "John"], "Sarah screen-left, facing screen-right; John screen-right, facing screen-left")
    xs = {p["name"]: p["x"] for p in g["points"]}
    assert xs["Sarah"] < 0.4 < 0.6 < xs["John"] and "opposite thirds" in g["text"]
    flipped = C.guide("Medium", ["Sarah", "John"], "Sarah screen-right, facing screen-left; John screen-left, facing screen-right")
    assert {p["name"]: p["x"] for p in flipped["points"]}["Sarah"] > 0.6, "the screen sides in the blocking are kept"
    three = C.guide("Medium", ["A", "B", "C"], "")
    assert "triangle" in three["text"]


def test_a_wide_shot_gets_a_horizon_on_a_third_and_layers_and_a_low_angle_moves_it():
    g = C.guide("Wide", ["Sarah"], "", "eye level")
    assert g["horizon"] == pytest.approx(1 / 3, abs=0.01) and "Layered depth" in g["text"] and "never across the middle" in g["text"]
    assert C.guide("Wide", ["Sarah"], "", "low angle")["horizon"] == pytest.approx(2 / 3, abs=0.01)


def test_every_size_gives_a_sentence_with_a_reason():
    for fr in ("Extreme close-up", "Close-up", "Medium close-up", "Medium", "Full", "Wide", "Establishing", "Over the shoulder", "Point of view", "Insert"):
        g = C.guide(fr, ["Sarah", "John"], "")
        assert g["lines"] and all(x["text"] and x["why"] for x in g["lines"]), fr
        assert all(0 <= p["x"] <= 1 and 0 <= p["y"] <= 1 for p in g["points"])


def test_it_reaches_the_request_and_can_be_switched_off_or_replaced_by_a_storyboard_panel():
    shot = {"performers": ["Sarah"], "beats": ["Sarah waits."], "framing": "Close-up", "continuity_notes": ["Blocking as the camera sees it: Sarah screen-left, facing screen-right."]}
    p = build(shot)["prompt"]
    assert "Composition:" in p and "look room on the right" in p
    assert "Composition:" not in build(shot, {"look": {"style": "auto"}, "composition": {"on": False}})["prompt"]
    assert "Composition:" not in build(shot, refs=[{"label": "composition reference: Storyboard S01-01", "url": "u"}])["prompt"], "a storyboard panel is the composition"
    assert "Composition:" not in build({"performers": [], "beats": ["The kettle."], "framing": "Medium"})["prompt"], "nobody in a medium shot: nothing to place"
    assert "Composition:" in build({"performers": [], "beats": ["The street."], "framing": "Wide"})["prompt"]


def test_it_is_dropped_before_the_hands_line_when_the_prompt_is_too_long():
    trace = []
    s = {"id": "S01-01", "start": 0.0, "end": 4.0, "performers": ["Sarah"], "beats": ["Sarah holds his hand."], "framing": "Close-up"}
    R.compile_request(s, None, {"meta": {}}, {"look": {"style": "auto"}}, still(), [], trace=trace)
    comp = next(b for b in trace if b["text"].startswith("Composition:"))
    hands = next(b for b in trace if "finger" in b["text"].lower())
    assert comp["priority"] < hands["priority"]


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    S.breakdown(d)
    return d


def test_the_guide_for_a_films_shot_and_the_film_wide_switch(film):
    sid = S._index(film)["order"][0]
    S.set_fields(film, sid, {"camera": {"framing": "close-up"}})
    g = C.for_shot(film, sid)
    assert g["shot"] == sid and g["size"] == "close" and g["in_prompt"] is True and g["lines"]
    assert C.set_enabled(film, False) == {"in_prompt": False}
    assert C.for_shot(film, sid)["in_prompt"] is False
    assert json.load(open(os.path.join(make.render_dir(film), "project.json")))["composition"] == {"on": False}
    C.set_enabled(film, True)
    assert C.for_shot(film, sid)["in_prompt"] is True


def test_the_command_line_speaks_json_and_refuses_a_bad_id(film, capsys):
    sid = S._index(film)["order"][0]
    assert C.main(["guide", film, "--data", json.dumps({"shot": sid})]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["event"] == "result"
    assert C.main(["guide", film, "--data", json.dumps({"shot": "../../x"})]) == 1
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["event"] == "error"
