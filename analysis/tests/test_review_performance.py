"""The reviewer judges the acting: it is told what the shot asked of its performers (feeling, strength, expression, timed beats, arc), sees frames labelled with their time in the
shot, and may report a 'performance' issue. The AI is a stand-in; nothing is sent and nothing costs anything."""
import json
import os

import pytest

from filmcrafter_engine import acting as A, director, llm, review as RV
from tests.test_acting import FakeBrain, PLAN, SHOTS, SONG

SHOT = {**SHOTS[1], "id": "S01-02", "start": 4.0, "end": 8.0}


@pytest.fixture
def d(tmp_path):
    d = str(tmp_path)
    json.dump(PLAN, open(os.path.join(d, "production.json"), "w"))
    json.dump(SONG, open(os.path.join(d, "songmap.json"), "w"))
    json.dump({"title": "T"}, open(os.path.join(d, "project.json"), "w"))
    return d


@pytest.fixture
def seen(monkeypatch):
    """Stand in for the vision model and for the frame grabber; returns what the reviewer sent."""
    log = {"frames_asked": [], "brain": None}

    def use(answer):
        b = FakeBrain([answer])
        log["brain"] = b
        monkeypatch.setattr(llm, "client", lambda: b)
        monkeypatch.setattr(llm, "is_local", lambda: True)
        monkeypatch.setattr(llm, "visual_ready", lambda: True)
        monkeypatch.setattr(director, "resolve_model", lambda c, w, vision=False: "test-vision")
        monkeypatch.setattr(RV, "_frames_at", lambda path, need, n=3: (log["frames_asked"].append(n), [(round(need * (i + 0.5) / n, 2), "QUJD") for i in range(n)])[1])
        return log
    return use


GOOD = {"verdict": "good", "summary": "Looks right.", "issues": []}


def asked_content(log):
    return log["brain"].asked[0]["input"][1]["content"]


def test_nobody_in_the_shot_means_nothing_is_asked_of_acting(d):
    assert RV.performance_brief(d, {**SHOT, "performers": []}) is None
    assert RV.performance_brief(d, {"id": "x", "start": 0, "end": 2, "performers": ["Beatrice"]}) is None          # people, but nothing was asked of them


def test_the_brief_carries_the_feeling_the_beats_and_the_arc(d):
    A.beats_set(d, "S01-02", [{"t0": 0, "t1": 2, "what": "She lifts her hand to the glasses", "eyes": "down"}, {"t0": 2, "t1": 4, "what": "A tight smile"}])
    A.arc_set(d, "Beatrice", [{"section": "Verse 1", "emotion": "stern", "intensity": 4}, {"section": "Chorus 1", "emotion": "flustered", "intensity": 7}])
    b = RV.performance_brief(d, {**SHOT, "section": "Chorus 1"})
    assert b["emotion"] == "embarrassed realization" and b["intensity_1_to_10"] == 7
    assert b["beats"][0] == {"from_s": 0.0, "to_s": 2.0, "what": "She lifts her hand to the glasses", "eyes": "down"} and b["beats"][1]["what"] == "A tight smile"
    assert "flustered" in b["arc"]


def test_the_reviewer_sees_five_labelled_frames_and_the_acting_asked_for(d, seen):
    log = seen(GOOD)
    A.beats_set(d, "S01-02", [{"t0": 0, "t1": 4, "what": "She touches the frame"}])
    out = RV.visual(d, {}, SHOT, "take.mp4", 4.0)
    assert out["verdict"] == "good" and out["model"] == "test-vision" and log["frames_asked"] == [5]
    c = asked_content(log)
    texts = [x["text"] for x in c if x["type"] == "input_text"]
    assert sum(1 for x in c if x["type"] == "input_image") == 5
    assert "Frame at 0.4 s of 4 s:" in texts and "Frame at 3.6 s of 4 s:" in texts                                     # each frame says when in the shot it is
    brief = json.loads(next(t for t in texts if t.startswith("Shot contract: ")).split("Shot contract: ")[1].split("\nFrames")[0])
    assert brief["acting_asked_for"]["emotion"] == "embarrassed realization" and brief["acting_asked_for"]["beats"][0]["what"] == "She touches the frame"


def test_a_shot_nobody_acts_in_keeps_the_three_frames_and_asks_nothing_of_acting(d, seen):
    log = seen(GOOD)
    RV.visual(d, {}, {**SHOT, "performers": []}, "take.mp4", 4.0)
    assert log["frames_asked"] == [3]
    texts = [x["text"] for x in asked_content(log) if x["type"] == "input_text"]
    assert "acting_asked_for" not in next(t for t in texts if t.startswith("Shot contract: "))


def test_the_instructions_define_a_performance_issue_and_say_when_not_to_report_one():
    s = RV.SYSTEM
    assert "- performance:" in s and "frozen" in s and "labelled with their time" in s and "report nothing about acting when nobody is in the shot" in s
    assert "performance" in RV.ISSUE_SCHEMA["properties"]["issues"]["items"]["properties"]["kind"]["enum"]


def test_the_issue_schema_stays_strict_every_property_required():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False and set(node["required"]) == set(node["properties"]), node
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(RV.ISSUE_SCHEMA)


def test_a_performance_issue_decides_the_status_and_its_fix_is_collected(d, monkeypatch, tmp_path):
    take = tmp_path / "t.mp4"
    take.write_bytes(b"x")
    monkeypatch.setattr(RV, "technical", lambda path, need: [])
    issue = {"kind": "performance", "severity": "minor", "detail": "Her face stays blank through the realization.", "fix": "Her eyes widen and her mouth tightens into an embarrassed smile."}
    monkeypatch.setattr(RV, "visual", lambda *a, **k: {"verdict": "minor", "summary": "Stiff.", "issues": [issue], "model": "m"})
    r = RV.review_job(str(tmp_path), {"output": "t.mp4"}, {}, SHOT)
    assert r["status"] == "minor" and r["fixes"] == [issue["fix"]] and r["issues"][0]["kind"] == "performance"
