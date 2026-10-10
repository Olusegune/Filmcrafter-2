"""The Director Command: plain phrases become a change you approve; nothing is applied by it, and what it doesn't understand it says."""
import pytest

from filmcrafter_engine import bible, directcmd, shots, story

SCRIPT = """INT. KITCHEN - MORNING

Sarah pours tea.

SARAH
He said he would call.

JOHN
Did you say something?
"""


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    shots.breakdown(d)
    return d


def _talk(d):
    return next(s["id"] for s in shots.view(d)["shots"] if s["has_dialogue"])


def test_a_feeling_brings_the_camera_and_light_that_serve_it_with_reasons(film):
    r = directcmd.command(film, _talk(film), "Make this shot more claustrophobic")
    assert r["understood"] and r["patch"]["performance"]["emotional_intention"].startswith("Claustrophobic")
    assert r["patch"]["camera"]["angle"] == "low" and r["patch"]["camera"]["movement"] == "handheld" and r["patch"]["camera"]["why"]
    assert r["patch"]["lighting"]["description"] and r["summary"]


def test_nothing_is_applied_by_the_command_itself(film):
    sid = _talk(film)
    before = open(shots._cpath(film, sid), encoding="utf-8").read()
    directcmd.command(film, sid, "make it more tense")
    assert open(shots._cpath(film, sid), encoding="utf-8").read() == before


def test_the_proposed_change_can_be_applied_through_the_contract(film):
    sid = _talk(film)
    r = directcmd.command(film, sid, "close-up, low angle, handheld")
    assert r["patch"]["camera"] == {"framing": "close-up", "angle": "low", "movement": "handheld"}
    c = shots.set_fields(film, sid, r["patch"])["shot"]
    assert c["camera"]["framing"] == "close-up" and c["camera"]["angle"] == "low"


def test_move_the_camera_behind_her_uses_the_person_in_the_shot(film):
    sid = _talk(film)
    r = directcmd.command(film, sid, "Move the camera behind her")
    assert r["patch"]["camera"]["position"].startswith("Behind ") and r["patch"]["camera"]["framing"] == "over the shoulder"


def test_someone_should_still_be_holding_something(film):
    sid = _talk(film)
    r = directcmd.command(film, sid, "John should still be holding the letter")
    assert r["patch"]["props"][-1]["name"] == "letter" and "John" in r["patch"]["props"][-1]["state"] and "holding the letter" in r["patch"]["continuity"]


def test_the_previous_shots_closing_state_is_carried_over(film):
    ids = [s["id"] for s in shots.view(film)["shots"]]
    shots.set_fields(film, ids[0], {"closing_state": "Sarah holds the cup"})
    r = directcmd.command(film, ids[1], "use the previous shot's closing state")
    assert r["patch"]["opening_state"] == "Sarah holds the cup"
    none = directcmd.command(film, ids[0], "use the previous shot's closing state")
    assert not none["understood"] and "nothing to carry over" in none["summary"][0]


def test_keep_the_performance_but_change_something_else(film):
    sid = _talk(film)
    r = directcmd.command(film, sid, "Keep the performance but make it a wide shot, more tense")
    assert "performance" not in r["patch"] and r["patch"]["camera"]["framing"] == "wide" and "performance" in r["skipped"]
    r2 = directcmd.command(film, sid, "Keep everything except the lighting, make it more tense")
    assert set(r2["patch"]) <= {"lighting"} and r2["patch"]["lighting"]["description"]


def test_what_it_does_not_understand_it_says(film):
    r = directcmd.command(film, _talk(film), "make it pop and add a unicorn")
    assert not r["understood"] and r["patch"] == {} and "Try:" in r["help"]
    with pytest.raises(SystemExit, match="Say what"):
        directcmd.command(film, _talk(film), "   ")


def test_odd_input_never_throws(film):
    for t in ["x" * 500, "keep", "keep but", "behind", "\x00\x01", "should still be holding", "keep everything except"]:
        directcmd.command(film, _talk(film), t)


def test_through_the_shots_command_line(film, capsys):
    import json
    rc = shots.main(["command", film, "--data", json.dumps({"id": _talk(film), "text": "low angle"})])
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0 and out["data"]["patch"]["camera"]["angle"] == "low"
