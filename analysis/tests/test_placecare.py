"""Backgrounds: places nobody described, soft backgrounds for people shots, the fine patterns models smear, and fewer character sheets when two people share a shot."""
import json
import os

import pytest
from PIL import Image

from filmcrafter_engine import bible, library as L, picturecare as PC, placecare as P, shots as S, story

SCRIPT = ("INT. KITCHEN - NIGHT\n\nRain on the roof. Sarah pours tea from the kettle. The window is fogged.\n\nSARAH\nHe said he would call.\n\n"
          "EXT. SCHOOLYARD - DAY\n\nA chain-link fence runs along the field. Blue picnic tables stand under one big tree. Children play on the grass.\n\nJOHN\nCome on.\n")


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    S.breakdown(d)
    return d


def test_places_that_shots_happen_in_are_listed_with_what_they_lack(film):
    st = P.status(film)
    assert len(st["places"]) == 2 and set(st["missing"]) == {p["id"] for p in st["places"]}
    assert all(not p["has_description"] and not p["has_picture"] and p["missing"] for p in st["places"])


def test_a_description_a_layout_or_a_picture_each_count(film, tmp_path):
    ids = [p["id"] for p in P.status(film)["places"]]
    bible.upsert(film, "environment", {"id": ids[0], "description": "A small, warm kitchen."})
    pic = tmp_path / "yard.png"
    Image.new("RGB", (80, 50), (10, 90, 10)).save(pic)
    bible.add_media(film, "environment", ids[1], str(pic), "the yard", "master")
    assert P.status(film)["missing"] == []
    bible.remove_media(film, "environment", ids[1], bible.load(film)["environments"][1]["media"][0]["path"])
    assert P.status(film)["missing"] == [ids[1]]
    bible.upsert(film, "environment", {"id": ids[1], "spatial": {"landmarks": "A fence on the left."}})
    assert P.status(film)["missing"] == []


def test_a_first_description_comes_from_the_story_and_never_replaces_one(film):
    ids = {p["name"].lower(): p["id"] for p in P.status(film)["places"]}
    kitchen = next(i for n, i in ids.items() if "kitchen" in n)
    bible.upsert(film, "environment", {"id": kitchen, "description": "My own words."})
    r = P.draft(film)
    assert [f["name"].lower() for f in r["filled"]] == [n for n in ids if "schoolyard" in n]
    yard = next(e for e in bible.load(film)["environments"] if "schoolyard" in e["name"].lower())
    assert yard["description"].startswith("From the story:") and "chain-link fence" in yard["description"] and "SARAH" not in yard["description"] and len(yard["description"]) < 520
    assert next(e for e in bible.load(film)["environments"] if e["id"] == kitchen)["description"] == "My own words."
    assert P.draft(film)["filled"] == [], "nothing left to fill: running it again changes nothing"


def test_the_command_line_speaks_json(film, capsys):
    assert P.main(["status", film]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["event"] == "result" and len(out["data"]["places"]) == 2


# ---------------------------------------------------------------- the background wording

def test_a_shot_about_people_asks_for_a_soft_background_unless_the_focus_was_chosen_or_it_is_a_wide_view():
    base = {"performers": ["Sege"], "beats": ["Sege waits."], "framing": "Medium"}
    assert PC.guard(base, {})["soft_background"] and "out of focus" in PC.guard(base, {})["text"]
    assert not PC.guard({**base, "focus": "rack focus"}, {})["soft_background"], "the person chose the focus"
    assert not PC.guard({**base, "framing": "Wide"}, {})["soft_background"], "a wide view is about the place"
    assert not PC.guard({**base, "framing": "Establishing"}, {})["soft_background"]
    assert not PC.guard({**base, "beats": ["Sege waits, in deep focus."]}, {})["soft_background"]
    assert not PC.guard({"performers": [], "beats": ["The sea."], "framing": "Medium"}, {})["soft_background"]


def test_fine_patterns_are_asked_to_stay_soft_in_every_shot_and_the_negative_says_so():
    g = PC.guard({"performers": [], "beats": ["A fence."], "framing": "Wide"}, {})
    assert "fences, mesh, brick, leaves and grass" in g["text"] and "moire" in g["text"]
    n = PC.negative("text", {"performers": [], "beats": ["A fence."]}, {})
    assert "moire pattern" in n and "noisy background" in n


# ---------------------------------------------------------------- fewer sheets when two people share a shot

def _library_project(tmp_path, names):
    d = tmp_path / "p"
    (d / "assets" / "refs").mkdir(parents=True)
    items = []
    for n in names:
        files = []
        for k in range(4):
            f = d / "assets" / "refs" / f"{n}-{k}.png"
            Image.new("RGB", (64, 36), (k * 40, 60, 90)).save(f)
            files.append(f"assets/refs/{n}-{k}.png")
        items.append({"id": "fc-" + n, "kind": "character", "name": n.title(), "files": files, "notes": ""})
    pj = {"title": "T", "schema_version": 2, "library": {"items": items, "assign": {"project": [], "scenes": {}, "shots": {}}}}
    (d / "project.json").write_text(json.dumps(pj))
    return str(d), pj


def test_one_person_gets_up_to_four_sheets_two_people_get_two_each(tmp_path):
    d, pj = _library_project(tmp_path, ["chloe", "lila"])
    one = L.reference_files(d, pj, {"id": "S01-01", "performers": ["Chloe"], "scene": 1})
    two = L.reference_files(d, pj, {"id": "S01-02", "performers": ["Chloe", "Lila"], "scene": 1})
    assert len([r for r in one if r["names"] == ["Chloe"]]) == 4
    assert len([r for r in two if r["names"] == ["Chloe"]]) == 2 and len([r for r in two if r["names"] == ["Lila"]]) == 2
    assert [os.path.basename(r["path"]) for r in two if r["names"] == ["Chloe"]] == ["chloe-0.png", "chloe-1.png"], "the first two (the best views) are the ones kept"
