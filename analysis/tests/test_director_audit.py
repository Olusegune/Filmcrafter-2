"""What the Director merged or dropped, the risks in a merge, and splitting one back. No network."""
import json
import os

import pytest

from filmcrafter_engine import director as D, director_audit as A


def _prod():
    def shot(i, sid, ext, people, cue, start, end, text):
        return {"id": sid, "external_id": ext, "source_shots": [ext], "performers": people, "lyrics": cue, "start": start, "end": end,
                "description": text, "framing": "medium"}
    return {"scenes": [
        {"number": 1, "heading": "A", "shots": [shot(1, "S01-01", "shot_001", ["Ada"], ["Hello"], 0, 4, "Ada waves."),
                                                shot(2, "S01-02", "shot_002", ["Ada"], [], 4, 8, "Ada sits.")]},
        {"number": 2, "heading": "B", "shots": [shot(3, "S02-01", "shot_003", ["Ada", "Zara"], ["No."], 8, 10, "Zara says no."),
                                                shot(4, "S02-02", "shot_004", ["Queen"], ["BOUNDARIES?"], 10, 12, "Queen gasps."),
                                                shot(5, "S02-03", "shot_005", ["Ben"], [], 12, 15, "Ben looks up."),
                                                shot(6, "S02-04", "shot_006", ["Ben"], [], 15, 18, "Ben stands.")]}]}


def _directed(merge_ids=(("S02-01", ["S02-01", "S02-02"]),)):
    """The Director named planned shots by their app ids (S02-01), as it often does for a Producer package."""
    def d(sid, src, start, end, people):
        return {"id": sid, "source_shots": src, "beats": ["x"] * len(src), "start": start, "end": end, "duration_seconds": end - start,
                "performers": people, "visual_prompt": "merged text", "framing": "wide"}
    return {"scenes": [
        {"number": 1, "director_note": "Kept all.", "shots": [d("S01-01", ["S01-01"], 0, 4, ["Ada"]), d("S01-02", ["S01-02"], 4, 8, ["Ada"])]},
        {"number": 2, "director_note": "Merged S02-01 and S02-02 so the short beat has time.",
         "shots": [d("S02-01", ["S02-01", "S02-02"], 8, 12, ["Ada", "Queen"]), d("S02-02", ["S02-03", "S02-04"], 12, 15.2, ["Ben"])]}]}


@pytest.fixture
def proj(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    (d / "production.json").write_text(json.dumps(_prod()))
    (d / "directed.json").write_text(json.dumps(_directed()))
    return str(d)


def test_the_audit_lists_every_merge_with_the_reasons_to_look_twice(proj):
    a = A.audit(proj)
    assert (a["planned"], a["directed"], a["drops"], a["uncovered"], a["ok"]) == (6, 4, [], [], False)
    first, second = a["merges"]
    assert first["shot"] == "S02-01" and first["check"]
    assert any("different people" in r for r in first["risks"]) and any("two separate lyric" in r for r in first["risks"]) and not any("under 2 seconds" in r for r in first["risks"])
    assert [s["id"] for s in first["sources"]] == ["S02-01", "S02-02"] and first["sources"][1]["cue"] == ["BOUNDARIES?"]
    assert "Merged S02-01" in first["note"]
    assert second["shot"] == "S02-02" and [s["id"] for s in second["sources"]] == ["S02-03", "S02-04"]
    assert second["risks"] == ["each of the 2 actions gets under 2 seconds"] or second["risks"] == []         # same person, no lines: only the time can matter


def test_dropped_beats_and_uncovered_shots_are_reported(proj):
    d = json.load(open(os.path.join(proj, "directed.json")))
    d["scenes"][0]["shots"][1]["dropped_beats"] = ["Ada sits."]
    d["scenes"][1]["shots"][1]["source_shots"] = ["S02-03"]                                         # S02-04 is no longer carried by anything
    json.dump(d, open(os.path.join(proj, "directed.json"), "w"))
    a = A.audit(proj)
    assert a["drops"] == [{"shot": "S01-02", "beats": ["Ada sits."]}] and [u["id"] for u in a["uncovered"]] == ["S02-04"]


def test_both_kinds_of_source_id_count_as_the_same_beat(tmp_path):
    d = tmp_path / "q"
    d.mkdir()
    (d / "production.json").write_text(json.dumps(_prod()))
    dd = _directed()
    for sc in dd["scenes"]:
        for s in sc["shots"]:
            s["source_shots"] = [{"S01-01": "shot_001", "S01-02": "shot_002", "S02-01": "shot_003", "S02-02": "shot_004", "S02-03": "shot_005", "S02-04": "shot_006"}[x] for x in s["source_shots"]]
    (d / "directed.json").write_text(json.dumps(dd))
    assert [m["shot"] for m in A.audit(str(d))["merges"]] == ["S02-01", "S02-02"] and A.audit(str(d))["uncovered"] == []


def test_splitting_restores_the_beats_without_renumbering_anything(proj):
    r = A.split(proj, "S02-01")
    assert r["split"] == ["S02-01", "S02-01b"] and os.path.exists(os.path.join(proj, r["backup"]))
    assert "keeps any keyframe or take" in r["note"]
    d = json.load(open(os.path.join(proj, "directed.json")))
    ids = [s["id"] for sc in d["scenes"] for s in sc["shots"]]
    assert ids == ["S01-01", "S01-02", "S02-01", "S02-01b", "S02-02"]                              # nothing else moved or was renamed
    a, b = d["scenes"][1]["shots"][:2]
    assert (a["start"], b["end"]) == (8, 12) and a["end"] == b["start"] and a["end"] - a["start"] >= A.MIN_SHOT and b["end"] - b["start"] >= A.MIN_SHOT
    assert a["performers"] == ["Ada", "Zara"] and b["performers"] == ["Queen"] and b["visual_prompt"] == "Queen gasps." and b["split_from"] == "S02-01"
    assert a["source_shots"] == ["shot_003"] and b["source_shots"] == ["shot_004"] and a["id"] == "S02-01"
    assert [m["shot"] for m in A.audit(proj)["merges"]] == ["S02-02"]                              # that merge is gone, the other remains
    with pytest.raises(SystemExit, match="isn't a merge"):
        A.split(proj, "S02-01")


def test_a_shot_too_short_to_split_is_refused_and_nothing_changes(proj):
    d = json.load(open(os.path.join(proj, "directed.json")))
    d["scenes"][1]["shots"][0].update(start=8, end=10.0, duration_seconds=2.0)
    json.dump(d, open(os.path.join(proj, "directed.json"), "w"))
    before = open(os.path.join(proj, "directed.json")).read()
    with pytest.raises(SystemExit, match="too short"):
        A.split(proj, "S02-01")
    with pytest.raises(SystemExit, match="isn't in the directed plan"):
        A.split(proj, "S99-01")
    assert open(os.path.join(proj, "directed.json")).read() == before and not [f for f in os.listdir(proj) if "before-split" in f]


def test_the_director_check_accepts_a_planned_shots_own_id_as_a_source():
    scene = {"number": 2, "shots": [{"id": "S02-01", "source_shots": ["shot_003"]}, {"id": "S02-02", "source_shots": ["shot_004"]}]}
    shots = [{"id": "S02-01", "source_shots": ["S02-01", "S02-02"], "beats": ["a", "b"], "start": 0, "end": 4}]
    assert D.validate(scene, shots)[0].startswith("S02-01: unknown source shots")                    # before: a false alarm on every shot
    D.normalize_sources(scene, shots)
    assert shots[0]["source_shots"] == ["shot_003", "shot_004"] and D.validate(scene, shots) == []
    ok = [{"id": "S02-01", "source_shots": ["shot_003"], "beats": ["a"], "start": 0, "end": 4}]
    D.normalize_sources(scene, ok)
    assert ok[0]["source_shots"] == ["shot_003"]                                                    # ids already right are left alone
    script = {"number": 1, "shots": [{"id": "S01-01", "source_shots": ["S01-01"]}]}                  # a script plan: app id == source id
    s2 = [{"id": "S01-01", "source_shots": ["S01-01"], "beats": ["a"], "start": 0, "end": 4}]
    D.normalize_sources(script, s2)
    assert s2[0]["source_shots"] == ["S01-01"]
