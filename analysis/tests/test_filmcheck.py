"""The Continuity Director for a film: advisory findings, never blocking, with your decisions kept."""
import json
import os

import pytest

from filmcrafter_engine import bible, filmcheck, shots, story

SCRIPT = """INT. KITCHEN - MORNING

Sarah pours tea. A letter lies by the sink.

SARAH
He said he would call.

JOHN
Did you say something?

SARAH
No.
"""


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    shots.breakdown(d)
    return d


def _ids(d):
    return [s["id"] for s in shots.view(d)["shots"]]


def test_a_person_with_no_pictures_may_drift(film):
    r = filmcheck.run(film)
    f = [x for x in r["findings"] if x["kind"] == "identity"]
    assert f and all(x["severity"] == "likely" and "may change" in x["text"] for x in f)
    assert len({x["other"] for x in f}) == len(f)                       # once for each person, not once for each shot


def test_the_finding_goes_away_when_the_picture_is_added(film, tmp_path):
    pic = tmp_path / "p.png"
    pic.write_bytes(b"\x89PNG\r\n\x1a\n")
    for cid in ("c_sarah", "c_john"):
        bible.add_media(film, "character", cid, str(pic))
    assert not [x for x in filmcheck.run(film)["findings"] if x["kind"] == "identity"]


def test_a_changed_outfit_between_neighbouring_shots_is_pointed_out_with_a_may(film):
    ids = _ids(film)
    a, b = [i for i in ids if i.startswith("S01")][1:3]
    bible.add_wardrobe(film, "c_sarah", "Red coat")
    bible.add_wardrobe(film, "c_sarah", "Blue dress")
    ca = shots.get_shot(film, a)["shot"]["characters"]
    cb = shots.get_shot(film, b)["shot"]["characters"]
    sa = next(x for x in ca if x["name"] == "SARAH"); sb = next(x for x in cb if x["name"] == "SARAH")
    sa["wardrobe_id"], sb["wardrobe_id"] = "w1", "w2"
    shots.set_fields(film, a, {"characters": ca})
    shots.set_fields(film, b, {"characters": cb})
    f = [x for x in filmcheck.run(film)["findings"] if x["kind"] == "character"]
    assert f and "may have changed outfit" in f[0]["text"] and f[0]["shot"] == b and f[0]["severity"] == "likely"


def test_light_and_place_changes_in_one_scene_are_looked_at(film):
    a, b = _ids(film)[:2]
    shots.set_fields(film, a, {"lighting": {"time": "Morning"}})
    shots.set_fields(film, b, {"lighting": {"time": "Night"}, "environment": {"name": "Garden", "id": ""}})
    kinds = {x["kind"] for x in filmcheck.run(film)["findings"]}
    assert {"light", "place"} <= kinds


def test_how_a_shot_begins_can_be_taken_from_how_the_last_one_ended(film):
    a, b = _ids(film)[:2]
    shots.set_fields(film, a, {"closing_state": "Sarah holds the cup with both hands."})
    f = next(x for x in filmcheck.run(film)["findings"] if x["kind"] == "state")
    assert f["shot"] == b and f["apply"] == {"opening_state": "Sarah holds the cup with both hands."}
    r = filmcheck.apply(film, f["id"])
    assert shots.get_shot(film, b)["shot"]["opening_state"] == "Sarah holds the cup with both hands."
    assert not [x for x in r["findings"] if x["kind"] == "state"]


def test_a_disappearing_prop_is_a_note(film):
    a, b = _ids(film)[:2]
    shots.set_fields(film, a, {"props": [{"name": "letter", "state": "sealed"}]})
    shots.set_fields(film, b, {"action": "She looks at the letter."})
    assert any(x["kind"] == "prop" and x["severity"] == "note" for x in filmcheck.run(film)["findings"])


def test_dialogue_without_a_stated_feeling_is_a_note(film):
    assert any(x["kind"] == "performance" for x in filmcheck.run(film)["findings"])
    for i in _ids(film):
        shots.set_fields(film, i, {"performance": {"emotional_intention": "Held-back"}})
    assert not any(x["kind"] == "performance" for x in filmcheck.run(film)["findings"])


def test_your_decisions_are_kept_when_the_checks_run_again(film):
    f = filmcheck.run(film)["findings"][0]
    r = filmcheck.decide(film, f["id"], "dismissed")
    assert next(x for x in r["findings"] if x["id"] == f["id"])["status"] == "dismissed" and r["open"] == len(r["findings"]) - 1
    assert next(x for x in filmcheck.run(film)["findings"] if x["id"] == f["id"])["status"] == "dismissed"
    r = filmcheck.decide(film, f["id"], "open")
    assert next(x for x in r["findings"] if x["id"] == f["id"])["status"] == "open"
    with pytest.raises(SystemExit):
        filmcheck.decide(film, f["id"], "deleted")
    with pytest.raises(SystemExit, match="isn't there"):
        filmcheck.decide(film, "nope", "noted")


def test_nothing_in_the_film_changes_by_checking(film):
    before = {i: open(shots._cpath(film, i), encoding="utf-8").read() for i in _ids(film)}
    filmcheck.run(film)
    assert before == {i: open(shots._cpath(film, i), encoding="utf-8").read() for i in _ids(film)}


def test_every_finding_says_may_or_gives_a_plain_observation(film):
    for f in filmcheck.run(film)["findings"]:
        assert f["severity"] in filmcheck.SEVERITIES and f["text"] and f["status"] == "open"
        assert "definitely" not in f["text"].lower() and "is wrong" not in f["text"].lower()


def test_a_folder_that_is_not_a_film_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="isn't a FilmCrafter film"):
        filmcheck.run(str(tmp_path))


def test_the_command_line(film, capsys):
    assert filmcheck.main(["check", film]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["event"] == "result" and "findings" in out["data"]
    assert filmcheck.main(["check", film + "-nope"]) == 1
