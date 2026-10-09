import json
import os

import pytest

from filmcrafter_engine import render, supervisor as SV


def _project(tmp_path, jobs, keyframes=None):
    d = tmp_path / "P"
    d.mkdir()
    shots = [{"id": f"S01-0{i}", "scene": 1, "start": i, "end": i + 1, "beats": ["x"], "performers": []} for i in (1, 2, 3)]
    (d / "production.json").write_text(json.dumps({"scenes": [{"number": 1, "shots": shots}]}))
    (d / "project.json").write_text(json.dumps({"title": "P"}))
    (d / "jobs.json").write_text(json.dumps({"jobs": jobs}))
    for j in jobs:
        if j.get("output"):
            os.makedirs(os.path.dirname(os.path.join(d, j["output"])), exist_ok=True)
            open(os.path.join(d, j["output"]), "wb").write(b"x")
    if keyframes:
        (d / "keyframes.json").write_text(json.dumps({"production": keyframes}))
    return str(d)


def J(i, shot, **kw):
    return {"id": i, "shot_id": shot, "plan": "production", "provider": "kie", "model": "m", "state": "ready", "created": 1,
            "output": f"g/{i}.mp4", **kw}


REVIEW = {"reviewed": True, "status": "needs_attention", "issues": [{"kind": "framing", "severity": "major", "detail": "Too wide", "fix": "Go closer"}]}


def test_collects_all_sources(tmp_path):
    d = _project(tmp_path, [
        J("a", "S01-01", review=REVIEW),
        J("k", "S01-02", kind="image", output="g/k.png", still_check={"ok": False, "problems": [{"kind": "text", "detail": "Watermark"}], "fix": "No text"}),
        J("f", "S01-02", state="failed", output=None, error="Exhausted balance", error_kind="credits", created=5),
    ], keyframes={"S01-02": "project:g/k.png"})
    items = SV.listing(d)["items"]
    titles = {(i["shot"], i["title"]) for i in items}
    assert ("S01-01", "Framing in the take") in titles
    assert ("S01-02", "Keyframe: text") in titles
    assert ("S01-02", "Render failed") in titles
    cov = next(i for i in items if i["source"] == "coverage")
    assert "S01-02" in cov["detail"] and "S01-03" in cov["detail"]
    s = SV.listing(d)["summary"]
    assert s["major"] >= 3 and s["ready"] is False


def test_accept_marks_review_and_clears(tmp_path):
    d = _project(tmp_path, [J("a", "S01-01", review=REVIEW)])
    it = next(i for i in SV.listing(d)["items"] if i["source"] == "take review")
    SV.decide(d, it["id"], "accept")
    assert not any(i["source"] == "take review" for i in SV.listing(d)["items"])   # accepted reviews don't come back
    assert json.load(open(os.path.join(d, "jobs.json")))["jobs"][0]["review"]["accepted"] is True


def test_ignore_is_remembered(tmp_path):
    d = _project(tmp_path, [J("a", "S01-01", review=REVIEW)])
    it = SV.listing(d)["items"][0]
    r = SV.decide(d, it["id"], "ignore", note="intended")
    assert next(i for i in r["items"] if i["id"] == it["id"])["status"] == "ignore"
    with pytest.raises(SystemExit):
        SV.decide(d, "nope", "ignore")


def test_fix_queues_with_the_correction(tmp_path, monkeypatch):
    d = _project(tmp_path, [J("a", "S01-01", review=REVIEW)])
    monkeypatch.setattr(render, "manifest", lambda p, m: {"model": m or "x", "roles": {}, "inputs": []})
    it = next(i for i in SV.listing(d)["items"] if i["source"] == "take review")
    r = SV.decide(d, it["id"], "fix", "kie", "wan/3-0-video")
    new = [j for j in json.load(open(os.path.join(d, "jobs.json")))["jobs"] if j["state"] == "queued"]
    assert new and new[0]["fix_notes"] == ["Go closer"]
    assert next(i for i in r["items"] if i["id"] == it["id"])["status"] == "working"
    with pytest.raises(SystemExit):
        SV.decide(d, it["id"], "fix")   # no provider


def test_fix_respects_budget(tmp_path, monkeypatch):
    d = _project(tmp_path, [J("a", "S01-01", review=REVIEW)])
    p = json.load(open(os.path.join(d, "project.json")))
    p["routing"] = {"mode": "local"}
    json.dump(p, open(os.path.join(d, "project.json"), "w"))
    monkeypatch.setattr(render, "manifest", lambda pv, m: {"model": m or "x", "roles": {}, "inputs": []})
    it = next(i for i in SV.listing(d)["items"] if i["source"] == "take review")
    with pytest.raises(SystemExit, match="Local First"):
        SV.decide(d, it["id"], "regenerate", "kie", "wan/3-0-video")


def test_own_media_is_never_flagged(tmp_path):
    d = _project(tmp_path, [J("o", "S01-01", provider="own", review=REVIEW)])
    assert not any(i["source"] == "take review" for i in SV.listing(d)["items"])


def test_reopen_undoes_a_decision(tmp_path):
    d = _project(tmp_path, [J("a", "S01-01", review=REVIEW)])
    it = SV.listing(d)["items"][0]
    SV.decide(d, it["id"], "ignore")
    r = SV.decide(d, it["id"], "reopen")
    assert next(i for i in r["items"] if i["id"] == it["id"])["status"] == "open"


# ---------------------------------------------------------------- stretches of the song no shot covers
def _timed(tmp_path, spans, duration):
    d = tmp_path / f"T{len(os.listdir(tmp_path))}"
    d.mkdir()
    shots = [{"id": f"S01-{i:02d}", "scene": 1, "start": a, "end": b, "beats": ["x"], "performers": []} for i, (a, b) in enumerate(spans, 1)]
    (d / "production.json").write_text(json.dumps({"scenes": [{"number": 1, "shots": shots}]}))
    (d / "project.json").write_text(json.dumps({"title": "T"}))
    (d / "songmap.json").write_text(json.dumps({"duration": duration, "sections": [], "lyrics": []}))
    (d / "jobs.json").write_text(json.dumps({"jobs": []}))
    return str(d)


def gaps(d):
    return [(i["title"], i["shot"], i["actions"]) for i in SV.collect(d) if i["source"] == "timeline"]


def test_a_black_intro_a_hole_in_the_middle_and_a_black_ending_are_all_reported(tmp_path):
    g = gaps(_timed(tmp_path, [(4.5, 10.0), (10.0, 15.0), (20.0, 30.0)], 40.0))
    assert [t for t, _, _ in g] == ["Black stretch in the film: 0:00.0 to 0:04.5", "Black stretch in the film: 0:15.0 to 0:20.0", "Black stretch in the film: 0:30.0 to 0:40.0"]
    assert g[0][1] == "S01-01" and g[1][1] == "S01-02" and g[2][1] == "S01-03"                        # each points at the nearest shot
    assert g[0][2] == ["card", "title", "accept", "ignore"] and g[1][2] == g[2][2] == ["accept", "ignore"]            # only the intro can take a title card


def test_a_fully_covered_song_and_tiny_gaps_are_not_reported(tmp_path):
    assert gaps(_timed(tmp_path, [(0.0, 10.0), (10.0, 20.0), (20.0, 30.0)], 30.0)) == []
    assert gaps(_timed(tmp_path, [(0.4, 10.0), (10.5, 20.0), (20.0, 29.4)], 30.0)) == []              # under a second is a cut, not a hole


def test_overlapping_shots_do_not_hide_a_later_gap(tmp_path):
    g = gaps(_timed(tmp_path, [(0.0, 12.0), (8.0, 10.0), (20.0, 30.0)], 30.0))
    assert [t for t, _, _ in g] == ["Black stretch in the film: 0:12.0 to 0:20.0"]


# ---------------------------------------------------------------- a title card over the black intro
def test_a_title_over_the_intro_counts_as_filling_it(tmp_path):
    d = _timed(tmp_path, [(4.5, 20.0), (20.0, 30.0)], 30.0)
    assert [t for t, _, _ in gaps(d)] == ["Black stretch in the film: 0:00.0 to 0:04.5"]
    json.dump({"overlays": [{"id": "t1", "kind": "text", "text": "Title", "start": 0.3, "end": 4.2, "x": 0.5, "y": 0.5, "size": 0.09, "fade": 0.5, "enabled": True}]}, open(os.path.join(d, "overlays.json"), "w"))
    assert gaps(d) == []                                                                               # on purpose: no warning
    json.dump({"overlays": [{"id": "t1", "kind": "text", "text": "Title", "start": 0.3, "end": 4.2, "enabled": False}]}, open(os.path.join(d, "overlays.json"), "w"))
    assert len(gaps(d)) == 1                                                                           # a hidden title fills nothing
    json.dump({"overlays": [{"id": "t1", "kind": "text", "text": "Brief", "start": 0.0, "end": 1.0, "enabled": True}]}, open(os.path.join(d, "overlays.json"), "w"))
    assert len(gaps(d)) == 1                                                                           # a one-second flash does not fill 4.5 s


def test_the_title_card_action_adds_the_projects_title_and_clears_the_warning(tmp_path):
    d = _timed(tmp_path, [(4.5, 30.0)], 30.0)
    item = next(i for i in SV.collect(d) if i["source"] == "timeline")
    assert item["actions"][:2] == ["card", "title"]
    SV.decide(d, item["id"], "title")
    ov = json.load(open(os.path.join(d, "overlays.json")))["overlays"]
    assert len(ov) == 1 and ov[0]["text"] == "T" and ov[0]["kind"] == "text" and 0 < ov[0]["start"] < 1 and 3.5 < ov[0]["end"] < 4.5 and ov[0]["x"] == 0.5 and ov[0]["y"] == 0.5
    assert gaps(d) == []


def test_only_a_gap_at_the_very_start_offers_a_title(tmp_path):
    d = _timed(tmp_path, [(0.0, 10.0), (20.0, 30.0)], 30.0)
    mid = next(i for i in SV.collect(d) if i["source"] == "timeline")
    assert "title" not in mid["actions"]
    with pytest.raises(SystemExit, match="isn't available"):
        SV.decide(d, mid["id"], "title")
    d2 = _timed(tmp_path, [(1.0, 30.0)], 30.0)
    assert gaps(d2)[0][2] == ["accept", "ignore"]                                                      # a one-second lead-in is too short for a card
