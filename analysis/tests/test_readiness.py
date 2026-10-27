"""Is this film ready: one list in the order a film is made, one next step, nothing made or bought."""
import hashlib
import json
import os

import numpy as np
import pytest
import soundfile as sf

from filmcrafter_engine import audioplan as A, bible, make, readiness as R, shots as S, story, voiceover as V

SCRIPT = """INT. KITCHEN - NIGHT

Sarah pours tea.

SARAH
He said he would call and he never did and I keep waiting here every single night.

JOHN
Did you say something?
"""


@pytest.fixture
def film(tmp_path, monkeypatch):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    S.breakdown(d)
    monkeypatch.setattr(A, "_caps", lambda rd, tier: {"model": "Test", "ref_audio": True, "audio": True, "known": True})
    return d


def kinds(r):
    return [(i["step"], i["level"]) for i in r["items"]]


def test_a_story_with_no_shots_says_to_break_it_down_and_nothing_else_is_asked(tmp_path):
    d = story.create(str(tmp_path / "films"), "Empty", "screenplay", SCRIPT)["dir"]
    r = R.report(d)
    assert r["items"][0]["step"] == "story" and r["items"][0]["level"] == "fix" and r["next"]["step"] == "story" and not r["ready"]
    assert [i["step"] for i in r["items"]] == ["story"]


def test_a_short_shot_is_a_fix_with_a_one_click_length_and_it_comes_first(film):
    sid = next(s for s in S._index(film)["order"] if "He said" in json.dumps(S._contract(film, s)["dialogue"]))
    S.set_fields(film, sid, {"generation": {"duration": 2.0}})
    r = R.report(film)
    fixes = [i for i in r["items"] if i["step"] == "fix"]
    assert fixes and r["items"][0]["level"] == "fix" and r["next"]["step"] == "fix"
    f = fixes[0]["fix"]
    assert f["kind"] == "shot_seconds" and f["shot"] == sid and f["was"] == 2.0 and f["seconds"] > 2.0 and (f["seconds"] * 2) % 1 == 0, "a whole or half second"
    S.set_fields(film, sid, {"generation": {"duration": f["seconds"]}})
    assert not [i for i in R.report(film)["items"] if i["step"] == "fix"], "applying the length clears the fix"


def test_the_steps_follow_the_order_a_film_is_made_in(film):
    r = R.report(film)
    order = [i["step"] for i in r["items"] if i["level"] != "fix"]
    assert order == sorted(order, key=R.ORDER.index)
    assert "voices" in order and "keyframes" in order
    assert r["counts"]["look"] >= 2 and not r["ready"]


def test_lines_without_a_voice_are_counted_and_point_at_the_voice_screen(film):
    v = next(i for i in R.report(film)["items"] if i["step"] == "voices" and i["level"] == "look")
    assert "need a voice" in v["what"] or "needs a voice" in v["what"]
    assert v["go"] == "voice" and v["shot"]


def test_a_money_step_names_the_price_sheet_and_never_makes_anything(film):
    before = {}
    for r, _, fs in os.walk(film):
        for f in fs:
            p = os.path.join(r, f)
            if os.sep + "backups" + os.sep not in p and os.sep + "cache" + os.sep not in p:
                before[p] = hashlib.sha1(open(p, "rb").read()).hexdigest()
    make.sync(film)
    after_sync = {}
    for r, _, fs in os.walk(film):
        for f in fs:
            p = os.path.join(r, f)
            if os.sep + "backups" + os.sep not in p and os.sep + "cache" + os.sep not in p:
                after_sync[p] = hashlib.sha1(open(p, "rb").read()).hexdigest()
    rep = R.report(film)
    vid = next(i for i in rep["items"] if i["step"] == "video")
    assert vid["go"] == "make" and "price" in vid["why"] and "confirm" in vid["why"]
    again = {}
    for r, _, fs in os.walk(film):
        for f in fs:
            p = os.path.join(r, f)
            if os.sep + "backups" + os.sep not in p and os.sep + "cache" + os.sep not in p:
                again[p] = hashlib.sha1(open(p, "rb").read()).hexdigest()
    assert again == after_sync, "reading the list changes no file"


def test_the_module_cannot_spend_or_send():
    src = open(R.__file__, encoding="utf-8").read()
    for bad in ("import requests", "urllib", "socket", "subprocess", "paidops", "api_key", "queue_render", "enqueue", "speak("):
        assert bad not in src, bad


def test_the_command_line_speaks_json(film, capsys):
    assert R.main(["report", film]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["event"] == "result" and "items" in out["data"]
    assert R.main(["report", os.path.join(film, "nowhere")]) == 1
