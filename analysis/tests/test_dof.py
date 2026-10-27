"""Depth of field chosen like an aperture, and J and L cuts for a shot's dialogue: the choices are checked, kept in the shot, reach the request and the export, and change no other shot."""
import re

import pytest

from filmcrafter_engine import bible, dof as D, export as E, make, picturecare as PC, render as R, shots as S, story

SCRIPT = "INT. KITCHEN - NIGHT\n\nSarah pours tea.\n\nSARAH\nHe said he would call.\n\nJOHN\nDid you say something?\n"


def field(name, **kw):
    return {"name": name, "type": "string", "items": None, "enum": None, "default": None, "minimum": None, "maximum": None, "max_items": None, "max_length": None, "description": "", "required": False}


def build(shot, project=None, trace=None):
    man = R._finish("fal", "t/i", "Still", "text-to-image", [field("prompt")])
    s = {"id": "S01-01", "start": 0.0, "end": 4.0, "performers": ["Sarah"], "beats": ["Sarah waits."], "framing": "Medium", **shot}
    return R.compile_request(s, None, {"meta": {}}, project or {"look": {"style": "auto"}}, man, [], trace=trace)["prompt"]


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    S.breakdown(d)
    return d


def test_each_level_says_what_is_sharp_and_the_aperture_it_matches():
    assert [x["id"] for x in D.levels()] == ["very shallow", "shallow", "medium", "deep"]
    assert [x["aperture"] for x in D.levels()] == ["f/1.4", "f/2.8", "f/5.6", "f/11"]
    for k, v in D.LEVELS.items():
        assert v["aperture"] in v["text"] and v["label"].startswith(k.capitalize()), k
    assert D.line({"dof": "deep"})["text"].startswith("Deep focus") and D.line({}) is None and D.line({"dof": "nonsense"}) is None


def test_the_choice_reaches_the_request_and_replaces_the_automatic_soft_background():
    auto = build({})
    assert "gently out of focus" in auto and "f/" not in auto
    deep = build({"dof": "deep"})
    assert "everything from the foreground to the far background is sharp" in deep and "gently out of focus" not in deep, "a chosen depth of field stands in place of the automatic one"
    shallow = build({"dof": "very shallow"})
    assert "f/1.4" in shallow and "gently out of focus" not in shallow
    trace = []
    build({"dof": "shallow"}, trace=trace)
    dof = next(b for b in trace if "f/2.8" in b["text"])
    assert dof["priority"] > 6, "it outlasts the general picture-care line when a prompt is too long"
    assert not PC.guard({"performers": ["S"], "framing": "Medium", "dof": "deep"}, {})["soft_background"]


def test_a_shot_keeps_its_depth_of_field_and_only_the_listed_ones_are_accepted(film):
    sid = S._index(film)["order"][0]
    S.set_fields(film, sid, {"camera": {"dof": "shallow"}})
    assert S._contract(film, sid)["camera"]["dof"] == "shallow"
    assert make.sync(film)["shots"] >= 1
    shot = next(s for sc in make._read(make.render_dir(film) + "/production.json")["scenes"] for s in sc["shots"] if s["id"] == sid)
    assert shot["dof"] == "shallow"
    S.set_fields(film, sid, {"camera": {"dof": ""}})
    assert S._contract(film, sid)["camera"]["dof"] == ""
    with pytest.raises(SystemExit, match="depth of field"):
        S.set_fields(film, sid, {"camera": {"dof": "blurry"}})
    assert "dof" in S.view(film)["enums"] and S.view(film)["enums"]["dof"] == list(S.DOF)


def test_a_lead_and_a_tail_are_numbers_of_seconds_kept_in_range_and_reach_the_export(film):
    ids = S._index(film)["order"]
    S.set_fields(film, ids[0], {"sound_cut": {"lead": 0.5}})
    S.set_fields(film, ids[0], {"sound_cut": {"tail": "1.2"}})
    assert S._contract(film, ids[0])["sound_cut"] == {"lead": 0.5, "tail": 1.2}, "one change keeps the other"
    S.set_fields(film, ids[0], {"sound_cut": {"lead": 99, "tail": -4}})
    assert S._contract(film, ids[0])["sound_cut"] == {"lead": S.CUT_MAX, "tail": 0.0}
    with pytest.raises(SystemExit, match="number of seconds"):
        S.set_fields(film, ids[0], {"sound_cut": {"lead": "soon"}})
    S.set_fields(film, ids[0], {"sound_cut": {"lead": 0.8, "tail": 0.4}})
    make.sync(film)
    shot = next(s for sc in make._read(make.render_dir(film) + "/production.json")["scenes"] for s in sc["shots"] if s["id"] == ids[0])
    assert (shot["dialogue_lead"], shot["dialogue_tail"]) == (0.8, 0.4)
    other = next(s for sc in make._read(make.render_dir(film) + "/production.json")["scenes"] for s in sc["shots"] if s["id"] == ids[1])
    assert (other["dialogue_lead"], other["dialogue_tail"]) == (0.0, 0.0), "no other shot changes"
    src = open(E.__file__, encoding="utf-8").read()
    assert re.search(r'"lead": float\(sh\.get\("dialogue_lead"\) or 0\.0\), "tail": float\(sh\.get\("dialogue_tail"\) or 0\.0\)', src), "the export hands the lead and the tail to the voice mix"
