"""Inserting a custom frame: where it goes, what it takes from its neighbour, and that it is an ordinary shot with its own take or keyframe."""
import json
import os

import pytest
from PIL import Image

from pulseframe_analysis import customframe as CF


@pytest.fixture
def proj(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    json.dump({"title": "T", "song": "s.wav"}, open(d / "project.json", "w"))
    json.dump({"duration": 30.0, "sections": [], "lyrics": []}, open(d / "songmap.json", "w"))
    shots = [{"id": "S01-01", "scene": 1, "number": 1, "start": 3.0, "end": 8.0, "beats": ["x"], "performers": []},
             {"id": "S01-02", "scene": 1, "number": 2, "start": 8.0, "end": 14.0, "beats": ["y"], "performers": []}]
    json.dump({"scenes": [{"number": 1, "start": 3.0, "end": 14.0, "shots": shots}]}, open(d / "production.json", "w"))
    json.dump({"jobs": []}, open(d / "jobs.json", "w"))
    return str(d)


def plan(d):
    return {s["id"]: s for sc in json.load(open(os.path.join(d, "production.json")))["scenes"] for s in sc["shots"]}


def test_a_frame_uses_the_empty_stretch_before_the_first_shot_without_cutting_anything(proj):
    r = CF.insert(proj, {"where": "before", "shot": "S01-01", "length": 2, "mode": "generate", "prompt": "Gold dust drifts"})
    p = plan(proj)
    assert r["trimmed"] is None and (r["start"], r["end"]) == (1.0, 3.0) and (p["S01-01"]["start"], p["S01-01"]["end"]) == (3.0, 8.0)
    new = p[r["shot"]]
    assert new["custom"] and new["visual_prompt"].endswith("No text, no letters, no logos.") and new["beats"] == ["Gold dust drifts"] and r["shot"] == "S01-01c1"


def test_what_the_gap_cannot_give_is_cut_from_the_neighbour_which_keeps_a_second(proj):
    r = CF.insert(proj, {"where": "after", "shot": "S01-01", "length": 2, "mode": "generate", "prompt": "A held title"})
    p = plan(proj)
    assert r["trimmed"] == {"shot": "S01-01", "by": 2.0} and (r["start"], r["end"]) == (6.0, 8.0)
    assert (p["S01-01"]["start"], p["S01-01"]["end"]) == (3.0, 6.0) and p["S01-01"]["duration_seconds"] == 3.0 and p["S01-02"]["start"] == 8.0     # nothing after it moves
    with pytest.raises(SystemExit, match="cannot give up"):
        CF.insert(proj, {"where": "after", "shot": "S01-01", "length": 5, "mode": "generate", "prompt": "Too long"})


def test_after_the_last_shot_it_uses_the_end_of_the_song(proj):
    r = CF.insert(proj, {"where": "after", "shot": "S01-02", "length": 4, "mode": "generate", "prompt": "Outro"})
    assert (r["start"], r["end"]) == (14.0, 18.0) and r["trimmed"] is None


def test_a_colour_card_is_a_shot_with_its_own_approved_take(proj):
    r = CF.insert(proj, {"where": "before", "shot": "S01-01", "length": 1.5, "mode": "colour", "color": "#102040", "color2": "#aa3300"})
    jobs = json.load(open(os.path.join(proj, "jobs.json")))["jobs"]
    j = next(x for x in jobs if x["shot_id"] == r["shot"])
    assert j["provider"] == "own" and j["media_kind"] == "image" and j["state"] == "ready" and j["cost"] == 0
    assert json.load(open(os.path.join(proj, "shots.json")))[r["shot"]]["approved"] == j["id"]
    assert Image.open(os.path.join(proj, "assets/refs", f"card-{r['shot']}.png")).size == (1920, 1080)


def test_your_own_picture_and_clip_become_takes_and_a_generated_frame_can_start_from_a_picture(proj, tmp_path):
    pic = tmp_path / "a.png"
    Image.new("RGB", (640, 360), (20, 60, 120)).save(pic)
    r = CF.insert(proj, {"where": "before", "shot": "S01-01", "length": 1, "mode": "picture", "file": str(pic), "motion": "pan_left"})
    j = next(x for x in json.load(open(os.path.join(proj, "jobs.json")))["jobs"] if x["shot_id"] == r["shot"])
    assert j["motion"] == "pan_left"
    g = CF.insert(proj, {"where": "after", "shot": "S01-02", "length": 2, "mode": "generate", "prompt": "Slow push in", "picture": str(pic)})
    kf = json.load(open(os.path.join(proj, "keyframes.json")))["production"][g["shot"]]
    assert g["keyframe"] and kf == f"project:assets/refs/frame-{g['shot']}.png"


def test_refusals_leave_the_plan_untouched(proj, tmp_path):
    before = open(os.path.join(proj, "production.json")).read()
    txt = tmp_path / "a.txt"
    txt.write_text("x")
    for bad, why in (({"shot": "S01-01", "length": 2, "mode": "generate", "prompt": " "}, "Describe what"), ({"shot": "S01-01", "length": 0.1, "mode": "colour"}, "between"),
                     ({"shot": "nope", "length": 2, "mode": "colour"}, "Choose the shot"), ({"shot": "S01-01", "length": 2, "mode": "picture", "file": str(txt)}, "Use an image"),
                     ({"shot": "S01-01", "length": 2, "mode": "clip"}, "Choose the clip"), ({"shot": "S01-01", "length": 2, "mode": "spin"}, "generated, colour"),
                     ({"shot": "S01-01", "length": 2, "mode": "colour", "where": "beside"}, "before or after")):
        with pytest.raises(SystemExit, match=why):
            CF.insert(proj, {"where": "before", **bad})
    assert open(os.path.join(proj, "production.json")).read() == before


def test_a_locked_shot_is_not_shortened(proj):
    json.dump({"S01-01": {"locked": True}}, open(os.path.join(proj, "shots.json"), "w"))
    with pytest.raises(SystemExit, match="locked"):
        CF.insert(proj, {"where": "after", "shot": "S01-01", "length": 2, "mode": "colour"})
    r = CF.insert(proj, {"where": "before", "shot": "S01-01", "length": 2, "mode": "colour"})              # the empty stretch is free to use
    assert r["trimmed"] is None


def test_the_command_line_speaks_json(proj, capsys):
    assert CF.main(["state", proj]) == 0
    ev = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert [s["id"] for s in ev["data"]["shots"]] == ["S01-01", "S01-02"]
    assert CF.main(["insert", proj, "--data", json.dumps({"shot": "S01-01", "length": 2, "mode": "generate", "prompt": ""})]) == 1


def test_removing_a_frame_gives_back_the_time_it_took_and_lets_go_of_its_take(proj):
    r = CF.insert(proj, {"where": "after", "shot": "S01-01", "length": 2, "mode": "colour"})
    assert (plan(proj)["S01-01"]["end"]) == 6.0
    out = CF.remove(proj, r["shot"])
    p = plan(proj)
    assert r["shot"] not in p and out["gave_back"] == {"shot": "S01-01", "by": 2.0} and (p["S01-01"]["start"], p["S01-01"]["end"]) == (3.0, 8.0)
    assert p["S01-01"]["duration_seconds"] == 5.0
    jobs = json.load(open(os.path.join(proj, "jobs.json")))["jobs"]
    assert all(j["state"] == "dismissed" for j in jobs if j["shot_id"] == r["shot"])
    assert r["shot"] not in json.load(open(os.path.join(proj, "shots.json")))


def test_a_frame_that_used_empty_time_leaves_the_neighbour_alone_and_a_planned_shot_cannot_be_removed(proj):
    r = CF.insert(proj, {"where": "before", "shot": "S01-01", "length": 2, "mode": "generate", "prompt": "Dust"})
    out = CF.remove(proj, r["shot"])
    assert out["gave_back"] is None and plan(proj)["S01-01"]["start"] == 3.0
    with pytest.raises(SystemExit, match="Only a frame you added"):
        CF.remove(proj, "S01-01")
    assert "S01-01" in plan(proj)


def test_no_time_is_given_back_to_a_neighbour_that_has_moved_since(proj):
    r = CF.insert(proj, {"where": "after", "shot": "S01-01", "length": 2, "mode": "colour"})
    p = json.load(open(os.path.join(proj, "production.json")))
    p["scenes"][0]["shots"][0]["end"] = 5.0                                                        # the neighbour was re-timed by hand
    json.dump(p, open(os.path.join(proj, "production.json"), "w"))
    assert CF.remove(proj, r["shot"])["gave_back"] is None and plan(proj)["S01-01"]["end"] == 5.0
