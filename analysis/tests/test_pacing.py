"""Pacing: the rhythm of a film's cuts, found from the shots' lengths, sizes and dialogue. Advice only: nothing is changed."""
import hashlib
import json
import os

import pytest

from filmcrafter_engine import bible, pacing as P, shots as S, story

SCRIPT = "INT. KITCHEN - NIGHT\n\nSarah pours tea.\n\nSARAH\nHe said he would call.\n"


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    S.breakdown(d)
    return d


def make_film(film, rows):
    """Replace the film's shots with these: (scene, framing, seconds, dialogue words or 0)."""
    idx = S._index(film)
    for sid in idx["order"]:
        S._archive(film, sid)
    idx["order"] = []
    counts: dict[int, int] = {}
    for scene, framing, secs, words in rows:
        counts[scene] = counts.get(scene, 0) + 1
        sid = f"S{scene:02d}-{counts[scene]:02d}"
        c = S._blank(sid, {"number": scene, "location": "ROOM", "time": "NIGHT"}, counts[scene], 1)
        c["camera"]["framing"] = framing
        c["generation"]["duration"] = secs
        c["edited"] = True
        if words:
            c["dialogue"] = [{"speaker": "SARAH" if counts[scene] % 2 else "JOHN", "line": " ".join(["word"] * words), "paren": ""}]
        S._write(S._cpath(film, sid), c)
        idx["order"].append(sid)
    S._save_index(film, idx)


def kinds(r):
    return [(f["level"], f["shot"], f["what"]) for f in r["findings"]]


def test_a_shot_too_short_for_its_own_dialogue_is_a_fault(film):
    make_film(film, [(1, "wide", 4, 0), (1, "close-up", 2.0, 20), (1, "close-up", 10.0, 20)])
    r = P.report(film)
    bad = [f for f in r["findings"] if f["level"] == "fix"]
    assert [f["shot"] for f in bad] == ["S01-02"] and "needs about" in bad[0]["what"] and "2.5 words a second" in bad[0]["why"]


def test_very_short_and_very_long_shots_are_worth_a_look_but_an_insert_or_action_is_not(film):
    make_film(film, [(1, "wide", 4, 0), (1, "medium", 0.8, 0), (1, "insert", 0.8, 0), (1, "medium", 14, 0), (1, "close-up", 3, 0)])
    r = P.report(film)
    looks = {f["shot"]: f["what"] for f in r["findings"] if f["level"] == "look"}
    assert "S01-02" in looks and "S01-03" not in looks and "S01-04" in looks and "holds for 14.0 s" in looks["S01-04"]


def test_four_of_the_same_size_in_a_row_is_flagged_once_per_run(film):
    make_film(film, [(1, "wide", 4, 0)] + [(1, "medium", 3 + i, 0) for i in range(5)] + [(1, "close-up", 3, 0)])
    r = P.report(film)
    runs = [f for f in r["findings"] if "in a row" in f["what"]]
    assert len(runs) == 1 and runs[0]["level"] == "look"


def test_identical_lengths_are_a_note_and_a_scene_that_does_not_open_wide_is_a_note(film):
    make_film(film, [(1, "close-up", 3.0, 0), (1, "medium", 3.0, 0), (1, "wide", 3.05, 0), (1, "close-up", 2.95, 0), (1, "medium", 3.0, 0)])
    r = P.report(film)
    text = " ".join(f["what"] for f in r["findings"] if f["level"] == "note")
    assert "all about 3.0 s" in text and "does not open on a wide shot" in text


def test_a_long_exchange_with_no_close_up_and_a_long_speech_in_one_shot(film):
    make_film(film, [(1, "wide", 4, 0)] + [(1, "medium", 4, 8)] * 4)
    assert any("no close-ups" in f["what"] for f in P.report(film)["findings"])
    make_film(film, [(1, "wide", 4, 0), (1, "close-up", 12, 28), (1, "medium", 3, 0)])
    assert any("long speech" in f["what"] for f in P.report(film)["findings"])


def test_a_scene_much_faster_than_the_rest_is_called_out_and_the_rhythm_is_reported(film):
    make_film(film, [(1, "wide", 6, 0), (1, "medium", 6, 0), (1, "close-up", 6, 0), (2, "wide", 6, 0), (2, "medium", 6, 0), (2, "close-up", 6, 0),
                     (3, "wide", 1.5, 0), (3, "medium", 1.5, 0), (3, "close-up", 1.5, 0), (3, "medium", 1.5, 0)])
    r = P.report(film)
    assert any("Scene 3 is faster" in f["what"] for f in r["findings"])
    assert r["film"]["shots"] == 10 and [s["number"] for s in r["scenes"]] == [1, 2, 3]
    s3 = r["scenes"][2]
    assert s3["asl"] == 1.5 and len(s3["bars"]) == 4 and s3["seconds"] == 6.0
    assert r["counts"] == {k: sum(1 for f in r["findings"] if f["level"] == k) for k in ("fix", "look", "note")}


def test_findings_are_ordered_faults_first_and_each_has_a_reason_and_a_tip(film):
    make_film(film, [(1, "medium", 3, 0)] * 4 + [(1, "close-up", 1.0, 12)])
    r = P.report(film)
    levels = [f["level"] for f in r["findings"]]
    assert levels == sorted(levels, key=lambda x: {"fix": 0, "look": 1, "note": 2}[x])
    assert all(f["why"] and f["tip"] and f["what"] for f in r["findings"])


def test_transitions_on_most_cuts_are_flagged(film, monkeypatch):
    make_film(film, [(1, "wide", 4, 0), (1, "medium", 4, 0), (1, "close-up", 4, 0), (1, "medium", 4, 0)])
    monkeypatch.setattr(P, "_transitions", lambda d: {"S01-02": "dissolve", "S01-03": "wipe_left", "S01-04": "cut"})
    assert any("use a transition effect" in f["what"] for f in P.report(film)["findings"])
    monkeypatch.setattr(P, "_transitions", lambda d: {"S01-02": "cut"})
    assert not any("transition effect" in f["what"] for f in P.report(film)["findings"])


def test_it_changes_nothing_and_needs_shots(film, tmp_path):
    def h():
        return sorted((os.path.join(r, f), hashlib.sha1(open(os.path.join(r, f), "rb").read()).hexdigest()) for r, _, fs in os.walk(film) for f in fs if os.sep + "cache" + os.sep not in os.path.join(r, f))
    before = h()
    P.report(film)
    assert h() == before
    empty = story.create(str(tmp_path / "e"), "E", "screenplay", SCRIPT)["dir"]
    with pytest.raises(SystemExit, match="no shots"):
        P.report(empty)


def test_the_command_line_speaks_json(film, capsys):
    assert P.main(["report", film]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["event"] == "result" and out["data"]["film"]["shots"] >= 1
