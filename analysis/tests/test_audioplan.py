"""The sound plan: voice-over lines are kept from the script, every shot gets the route its voice will take with a reason, the plan is free and read-only, and Apply only sets the shot's own on/off setting."""
import hashlib
import json
import os

import numpy as np
import pytest
import soundfile as sf

from filmcrafter_engine import audioplan as A, bible, make, shots as S, story, voiceover as V

SCRIPT = """INT. KITCHEN - NIGHT

Sarah pours tea. Rain on the roof.

SARAH (V.O.)
I remember that night.

EXT. YARD - DAY

Children play.

JOHN (O.S.)
Come on in!

NARRATOR
It was the last summer.

INT. HALL - DAY

Sarah and John face each other.

SARAH
He said he would call.

JOHN
Did you say something?
"""


@pytest.fixture
def film(tmp_path, monkeypatch):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    S.breakdown(d)
    monkeypatch.setattr(A, "_caps", lambda rd, tier: {"model": "Test model", "ref_audio": True, "audio": True, "known": True})
    return d


def row(r, sid):
    return next(x for x in r["shots"] if x["shot"] == sid)


def shot_with(film, word):
    for sid in S._index(film)["order"]:
        if word in json.dumps(S._contract(film, sid)["dialogue"]):
            return sid
    raise AssertionError(word)


def test_a_voice_over_mark_in_the_script_is_kept_on_the_line_and_is_not_thrown_away(film):
    lines = [x for sid in S._index(film)["order"] for x in S._contract(film, sid)["dialogue"]]
    by = {x["speaker"]: x for x in lines}
    assert by["SARAH"].get("ext") == "V.O." or any(x["speaker"] == "SARAH" and x.get("ext") == "V.O." for x in lines)
    assert any(x["speaker"] == "JOHN" and x.get("ext") == "O.S." for x in lines)
    assert any(x["speaker"] == "NARRATOR" and not x.get("ext") for x in lines)
    assert any(x["speaker"] == "SARAH" and not x.get("ext") for x in lines), "an ordinary line has no mark"


def test_which_lines_are_voice_over():
    assert A.is_voice_over({"speaker": "SARAH", "ext": "V.O."}) and A.is_voice_over({"speaker": "JOHN", "ext": "O.S."})
    assert A.is_voice_over({"speaker": "NARRATOR"}) and A.is_voice_over({"speaker": "Voice over"}) and A.is_voice_over({"speaker": "V.O."})
    assert not A.is_voice_over({"speaker": "SARAH"}) and not A.is_voice_over({"speaker": "SARAH", "ext": ""})


def test_every_shot_gets_a_route_and_a_reason(film):
    r = A.report(film)
    assert len(r["shots"]) == len(S._index(film)["order"]) and r["model"] == "Test model"
    assert all(x["route"] in ("none", "voice_over", "needs_voice", "audio_in", "post_sync", "native") and x["why"] for x in r["shots"])
    assert row(r, shot_with(film, "I remember that night"))["route"] == "voice_over"
    assert row(r, shot_with(film, "Come on in"))["route"] == "voice_over"
    assert row(r, shot_with(film, "last summer"))["route"] == "voice_over"
    talk = row(r, shot_with(film, "He said he would call"))
    assert talk["route"] == "needs_voice" and "no voice yet" in talk["why"]
    quiet = [x for x in r["shots"] if not x["lines"]]
    assert quiet and all(x["route"] == "none" and "nothing is spent on sound" in x["why"] for x in quiet)
    assert sum(r["counts"].values()) == len(r["shots"])


def record(film, tmp_path, sid, who):
    p = str(tmp_path / f"{who}_{sid}.wav")
    sf.write(p, (0.3 * np.sin(np.arange(22050 * 2) / 20)).astype("float32"), 22050)
    V.import_recordings(film, [{"file": p, "shot": sid, "speaker": who}]) if hasattr(V, "import_recordings") else V.attach(film, sid, who, p)


def test_with_voices_the_route_follows_what_the_model_can_take(film, tmp_path, monkeypatch):
    sid = shot_with(film, "He said he would call")
    S.set_fields(film, sid, {"dialogue": [{"speaker": "SARAH", "line": "He said he would call."}, {"speaker": "JOHN", "line": "Did you say something?"}], "generation": {"duration": 8.0}})
    for who in ("Sarah", "John"):
        record(film, tmp_path, sid, who)
    assert row(A.report(film), sid)["route"] == "audio_in" and "one after the other" in row(A.report(film), sid)["why"]
    monkeypatch.setattr(A, "_caps", lambda rd, tier: {"model": "No-audio model", "ref_audio": False, "audio": False, "known": True})
    r = row(A.report(film), sid)
    assert r["route"] == "post_sync" and "laid over the picture" in r["why"]
    monkeypatch.setattr(A, "_caps", lambda rd, tier: {"model": "Native model", "ref_audio": False, "audio": True, "known": True})
    d = os.path.join(make.render_dir(film))
    os.makedirs(d, exist_ok=True)
    json.dump({"native": True}, open(os.path.join(d, "dialogue.json"), "w"))
    assert row(A.report(film), sid)["route"] == "native"


def test_a_shot_too_short_for_its_lines_and_a_crowd_are_warned(film):
    sid = shot_with(film, "He said he would call")
    S.set_fields(film, sid, {"generation": {"duration": 1.0}})
    assert any("its lines need about" in w for w in row(A.report(film), sid)["warnings"])
    S.set_fields(film, sid, {"dialogue": [{"speaker": n, "line": "Hello there friend."} for n in ("A", "B", "C", "D")]})
    assert any("4 people speak in one shot" in w for w in row(A.report(film), sid)["warnings"])


def test_the_lines_that_still_need_a_voice_are_counted_and_priced_offline(film, monkeypatch):
    r = A.report(film)
    assert r["lines_to_speak"] == sum(1 for x in r["shots"] for l in x["lines"] if not l["has_voice"]) and r["lines_to_speak"] >= 5
    assert r["tts_credits"] >= 0 and r["tts_unpriced"] >= 0


def test_the_tries_to_allow_for_come_from_the_tier_and_can_be_set_per_film(film):
    assert A.report(film, "draft")["keep_rate"] == 0.6 and A.report(film, "draft")["tries"] == pytest.approx(1.67, abs=0.01)
    assert A.report(film, "final")["keep_rate"] == 0.85
    assert A.report(film, "nonsense")["tier"] == "draft"
    rd = make.render_dir(film)
    os.makedirs(rd, exist_ok=True)
    json.dump({"audio_plan": {"keep_final": 0.5}}, open(os.path.join(rd, "project.json"), "w"))
    assert A.report(film, "final")["tries"] == 2.0


def snapshot(film):
    out = {}
    for r, _, fs in os.walk(film):
        for f in fs:
            p = os.path.join(r, f)
            if os.sep + "cache" + os.sep not in p and os.sep + "backups" + os.sep not in p:
                out[p] = hashlib.sha1(open(p, "rb").read()).hexdigest()
    return out


def test_the_report_changes_nothing(film):
    before = snapshot(film)
    A.report(film)
    assert snapshot(film) == before


def test_apply_marks_only_voice_over_shots_off_and_never_over_a_choice_of_yours(film):
    vo = shot_with(film, "I remember that night")
    mine = shot_with(film, "Come on in")
    A.set_setting(film, mine, "on")
    res = A.apply(film)
    assert vo in res["changed"] and mine not in res["changed"]
    pj = json.load(open(os.path.join(make.render_dir(film), "project.json")))
    assert pj["sing_shots"][vo] == "off" and pj["sing_shots"][mine] == "on"
    assert row(res, vo)["setting"] == "off" and not row(res, vo)["differs"]
    assert A.apply(film)["changed"] == [], "applying twice changes nothing more"
    A.set_setting(film, vo, "auto")
    assert vo not in json.load(open(os.path.join(make.render_dir(film), "project.json")))["sing_shots"]
    with pytest.raises(SystemExit, match="auto, on or off"):
        A.set_setting(film, vo, "maybe")
    with pytest.raises(SystemExit, match="not valid"):
        A.set_setting(film, "../../x", "off")


def test_the_module_cannot_spend_or_send():
    src = open(A.__file__, encoding="utf-8").read()
    for bad in ("import requests", "urllib", "socket", "subprocess", "paidops", "api_key", "speak("):
        assert bad not in src, bad


def test_the_command_line_speaks_json(film, capsys):
    assert A.main(["report", film]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["event"] == "result" and out["data"]["shots"]
    assert A.main(["set", film, "--data", json.dumps({"shot": "../../x", "value": "off"})]) == 1
