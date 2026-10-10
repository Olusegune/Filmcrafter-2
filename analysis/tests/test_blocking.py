"""Blocking: the top-down plan of each shot, what it says to the prompts, and the line the camera must not cross."""
import json
import os

import pytest

from filmcrafter_engine import bible, blocking as BL, filmcheck, make, shots, story

SCRIPT = """INT. KITCHEN - MORNING

Sarah pours tea. John watches from the doorway.

SARAH
He said he would call.

JOHN
Did you say something?

SARAH
No. Nothing.

EXT. PLATFORM - NIGHT

Rain on the roof.
"""


def person(name, x, y, facing):
    return {"name": name, "x": x, "y": y, "facing": facing}


TWO = [person("Sarah", 30, 36, 0), person("John", 70, 36, 180)]


def plan(cam, people=TWO):
    return {"people": people, "props": [], "camera": cam}


def test_clean_keeps_numbers_in_the_room_wraps_angles_and_limits_lists():
    p = BL.clean({"people": [{"name": "  Sarah ", "x": -5, "y": 999, "facing": 450}] + [{"name": f"P{i}", "x": 1, "y": 1} for i in range(40)],
                  "props": [{"name": "cup", "x": "50", "y": "abc"}], "camera": {"x": 500, "y": -3, "aim": -90, "fov": 500}})
    assert p["people"][0] == {"name": "Sarah", "x": 0.0, "y": BL.H, "facing": 90.0}
    assert len(p["people"]) == BL.MAX_PEOPLE
    assert p["props"][0] == {"name": "cup", "x": 50.0, "y": BL.H / 2}
    assert p["camera"] == {"x": BL.W, "y": 0.0, "aim": 270.0, "fov": 120.0}
    assert BL.clean(None) is None
    assert BL.clean({"people": [{"name": ""}, "x", None]}) == {"people": [], "props": [], "camera": None}
    with pytest.raises(SystemExit):
        BL.clean("a plan")
    for bad in (float("nan"), float("inf"), None, "x"):
        assert BL.clean({"people": [{"name": "A", "x": bad, "y": bad, "facing": bad}]})["people"][0]["x"] == BL.W / 2


def test_a_wide_two_shot_puts_the_people_left_and_right_facing_each_other():
    c = {"characters": [{"name": "SARAH"}, {"name": "JOHN"}], "camera": {"framing": "wide"}, "dialogue": [], "props": []}
    p = BL.suggest(c)
    assert [x["name"] for x in p["people"]] == ["Sarah", "John"]
    assert p["people"][0]["x"] < p["people"][1]["x"]
    assert 255 < p["camera"]["aim"] < 285 and p["camera"]["y"] > BL.H - 8
    text = BL.describe(p)
    assert "Sarah screen-left, facing screen-right" in text and "John screen-right, facing screen-left" in text


def test_over_the_shoulder_sits_behind_one_person_and_says_so():
    c = {"characters": [{"name": "SARAH"}, {"name": "JOHN"}], "camera": {"framing": "over the shoulder"}, "dialogue": [{"speaker": "JOHN", "line": "Hi"}], "props": []}
    p = BL.suggest(c)
    sarah, john, cam = p["people"][0], p["people"][1], p["camera"]
    assert cam["x"] < sarah["x"]                                              # behind Sarah, looking past her at John
    assert abs(((BL._bearing(cam["x"], cam["y"], john["x"], john["y"]) - cam["aim"] + 180) % 360) - 180) < 3
    assert "over Sarah's shoulder" in BL.describe(p)


def test_a_close_up_is_on_the_speaker():
    c = {"characters": [{"name": "SARAH"}, {"name": "JOHN"}], "camera": {"framing": "close-up"}, "dialogue": [{"speaker": "JOHN", "line": "Hi"}], "props": []}
    p = BL.suggest(c)
    john, cam = p["people"][1], p["camera"]
    assert abs(cam["x"] - john["x"]) < 13 and abs(cam["y"] - john["y"]) < 13
    assert "Camera close on John" in BL.describe(p)


def test_the_people_stay_where_they_stood_in_the_shot_before():
    c = {"characters": [{"name": "SARAH"}, {"name": "JOHN"}, {"name": "ANNA"}], "camera": {"framing": "medium"}, "dialogue": [], "props": []}
    prev = plan({"x": 50, "y": 60, "aim": 270, "fov": 60}, [person("Sarah", 11, 22, 45), person("John", 80, 30, 200)])
    p = BL.suggest(c, prev)
    assert p["people"][0]["x"] == 11 and p["people"][1]["x"] == 80 and p["people"][2]["name"] == "Anna"


def test_the_camera_stays_on_the_scenes_side_of_the_line():
    c = {"characters": [{"name": "SARAH"}, {"name": "JOHN"}], "camera": {"framing": "over the shoulder"}, "dialogue": [{"speaker": "JOHN", "line": "Hi"}], "props": []}
    for want in (1, -1):
        p = BL.suggest(c, None, want)
        assert BL._side(p["camera"], p["people"][0], p["people"][1]) == want


def test_describe_leaves_out_what_the_camera_cannot_see():
    p = plan({"x": 50, "y": 60, "aim": 90, "fov": 50})                         # looking down the page, away from both
    assert BL.describe(p) == ""
    assert BL.describe(None) == "" and BL.describe({"people": TWO, "camera": None}) == ""


def test_crossing_the_line_is_found_only_within_a_scene():
    below = {"x": 50, "y": 62, "aim": 270, "fov": 60}
    above = {"x": 50, "y": 8, "aim": 90, "fov": 60}
    cons = [{"id": "S01-01", "scene": 1, "plan": plan(below)}, {"id": "S01-02", "scene": 1, "plan": plan(above)}, {"id": "S01-03", "scene": 1, "plan": plan(above)},
            {"id": "S02-01", "scene": 2, "plan": plan(below)}, {"id": "S01-04", "scene": 1}]
    found = BL.crossings(cons)
    assert [x["shot"] for x in found] == ["S01-02"] and found[0]["previous"] == "S01-01" and "Sarah" in found[0]["message"]
    assert BL.crossings([{"id": "a", "scene": 1, "plan": plan(below)}, {"id": "b", "scene": 1, "plan": plan(below)}]) == []
    assert BL.crossings([{"id": "a", "scene": 1, "plan": {"people": [TWO[0]], "camera": below}}]) == []
    assert BL.scene_side(cons, 1) == BL._side(above, *TWO) and BL.scene_side(cons, 1, before="S01-02") == BL._side(below, *TWO)


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    shots.breakdown(d)
    return d


def _ids(d):
    return [c["id"] for c in make._contracts(d)]


def test_a_plan_is_saved_cleaned_and_can_be_removed(film):
    sid = _ids(film)[0]
    r = shots.set_fields(film, sid, {"plan": {"people": [{"name": "Sarah", "x": 500, "y": 5, "facing": 0}], "camera": {"x": 50, "y": 60, "aim": 270}}})
    assert r["shot"]["plan"]["people"][0]["x"] == BL.W and r["shot"]["plan"]["camera"]["fov"] == 50
    assert shots.set_fields(film, sid, {"plan": None})["shot"]["plan"] is None
    with pytest.raises(SystemExit):
        shots.set_fields(film, sid, {"plan": "nope"})


def test_a_locked_storyboard_refuses_a_new_plan(film):
    sid = _ids(film)[0]
    make.sync(film)
    c = shots._contract(film, sid)
    c["locks"]["storyboard"] = True
    shots._write(shots._cpath(film, sid), c)
    with pytest.raises(SystemExit):
        shots.set_fields(film, sid, {"plan": {"people": [], "camera": {"x": 1, "y": 1, "aim": 1}}})


def test_the_view_suggests_carries_and_flags_the_line(film):
    ids = [i for i in _ids(film) if i.startswith("S01")]
    a, b = ids[0], ids[1]
    v = shots.blocking_view(film, a, "suggest")
    assert v["plan"] is None and v["suggested"]["camera"] and v["room"] == {"w": BL.W, "h": BL.H} and v["scene_shots"][0]["id"] == a
    shots.set_fields(film, a, {"plan": plan({"x": 50, "y": 62, "aim": 270, "fov": 60})})
    v2 = shots.blocking_view(film, b, "carry")
    assert v2["has_previous"] and v2["suggested"]["people"][0]["x"] == 30
    shots.set_fields(film, b, {"plan": plan({"x": 50, "y": 6, "aim": 90, "fov": 60})})
    v3 = shots.blocking_view(film, b)
    assert [x["shot"] for x in v3["crossings"]] == [b] and v3["text"]
    assert shots.blocking_view(film, a, "bogus")["suggested"] is None
    with pytest.raises(SystemExit):
        shots.blocking_view(film, "S99-99")


def test_the_plan_reaches_the_render_projects_continuity_notes_and_the_check(film):
    ids = [i for i in _ids(film) if i.startswith("S01")]
    shots.set_fields(film, ids[0], {"plan": plan({"x": 50, "y": 62, "aim": 270, "fov": 90})})
    shots.set_fields(film, ids[1], {"plan": plan({"x": 50, "y": 6, "aim": 90, "fov": 90})})
    rd = make.sync(film)["render_dir"]
    production = json.load(open(os.path.join(rd, "production.json")))
    notes = next(s for sc in production["scenes"] for s in sc["shots"] if s["id"] == ids[0])["continuity_notes"]
    assert any(n.startswith("Blocking as the camera sees it") for n in notes)
    found = filmcheck.run(film)
    assert any(f["kind"] == "direction" and f["shot"] == ids[1] and "other side of the line" in f["text"] for f in found["findings"])
