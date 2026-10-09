"""Choreography Engine: brief from music/lyrics/script/sheet, saved plan, and injection into still + video prompts."""
import json
import types

import pytest

from filmcrafter_engine import choreo as C
from filmcrafter_engine import onboarding as O
from filmcrafter_engine import render as R


@pytest.fixture
def proj(tmp_path):
    d = tmp_path / "p"; d.mkdir()
    (d / "songmap.json").write_text(json.dumps({"bpm": 120, "duration": 16, "sections": [
        {"start": 0, "end": 8, "group": "Verse", "energy": 4, "mood": "Intimate"},
        {"start": 8, "end": 16, "group": "Chorus", "energy": 8, "mood": "Joyful"}],
        "lyrics": [{"text": "We move tonight", "start": 8.5, "end": 10}]}))
    shots = [{"id": "S01-01", "start": 0, "end": 8, "performers": ["Amara"], "framing": "close-up", "beats": ["She listens."]},
             {"id": "S01-02", "start": 8, "end": 16, "performers": ["Amara", "Sege"], "framing": "wide", "beats": ["They dance."]}]
    (d / "directed.json").write_text(json.dumps({"meta": {"LOGLINE": "Two people dance at dawn."},
        "characters": [{"name": "Amara", "appearance": "A woman."}, {"name": "Sege", "appearance": "A man."}],
        "scenes": [{"number": 1, "shots": shots}]}))
    (d / "sheet.txt").write_text("Chorus: 1-8 shoulder roll, 9-16 step-touch right.")
    O.choreo_set(str(d), {"mode": "upload", "style": "Afrobeats", "files": ["sheet.txt"]})
    return str(d)


def test_brief_uses_music_lyrics_story_and_the_sheet(proj):
    b = C.brief(proj)
    assert b["bpm"] == 120 and b["seconds_per_8_count"] == 4.0
    assert [s["name"] for s in b["sections"]] == ["Verse 1", "Chorus 1"] and b["sections"][1]["lyrics"] == ["We move tonight"]
    assert b["shots"][1]["section"] == "Chorus 1" and "shoulder roll" in b["sheet"]


def test_design_saves_a_plan_and_injects_pose_and_motion(proj, monkeypatch):
    fake = {"concept": "Joy breaks out in the chorus.", "dancers": ["Amara", "Sege"],
            "sections": [{"section": "Chorus 1", "feel": "open, joyful", "counts": [{"counts": "1-8", "move": "shoulder roll"}]}],
            "shots": [{"shot_id": "S01-01", "dancing": False, "pose": "", "motion": "", "energy": 3},
                      {"shot_id": "S01-02", "dancing": True, "pose": "both mid shoulder-roll, knees bent, facing camera",
                       "motion": "they roll shoulders on 1 and 5 then step-touch right together", "energy": 8}]}

    class Client:
        responses = types.SimpleNamespace(create=lambda **kw: types.SimpleNamespace(output_text=json.dumps(fake)))
    import filmcrafter_engine.director as D
    monkeypatch.setattr(D, "_client", lambda: Client())
    monkeypatch.setattr(D, "resolve_model", lambda c, m: "test-model")
    plan = C.design(proj)
    assert list(plan["shots"]) == ["S01-02"] and plan["source"] == "sheet"
    shot = {"id": "S01-02", "start": 8, "end": 16, "performers": ["Amara", "Sege"]}
    assert "on the beat at 120 BPM" in O.movement_for(proj, shot, "video")
    assert O.movement_for(proj, shot, "image").startswith("Dance pose")
    assert O.movement_for(proj, {"id": "S01-01", "start": 0, "end": 8, "performers": ["Amara"]}) is None  # acting-led
    # the plan survives setup edits, and reaches both prompts
    O.choreo_set(proj, {"mode": "upload", "style": "Afrobeats", "files": ["sheet.txt"], "notes": "joyful"})
    s = R._with_movement(proj, shot)
    img = R.compile_request(s, None, {"meta": {}}, {"look": {"style": "auto"}},
                            R._finish("fal", "i", "I", "", [{"name": "prompt", "type": "string", "description": ""}]), [])
    vid = R.compile_request(s, None, {"meta": {}}, {"look": {"style": "auto"}},
                            R._finish("fal", "v", "V", "", [{"name": "prompt", "type": "string", "description": ""},
                                                          {"name": "duration", "type": "string", "enum": ["5"], "description": ""}]), [])
    assert "mid shoulder-roll" in img["prompt"] and "step-touch" not in img["prompt"]
    assert "step-touch right" in vid["prompt"]
    assert "plan" not in C.clear(proj)


def test_cues_match_sections_found_by_time(tmp_path):
    d = tmp_path / "q"; d.mkdir()
    (d / "songmap.json").write_text(json.dumps({"sections": [{"start": 0, "end": 10, "group": "Chorus"}]}))
    O.choreo_set(str(d), {"mode": "written", "sections": [{"section": "Chorus", "notes": "big arm waves"}]})
    assert "big arm waves" in O.movement_for(str(d), {"id": "a", "start": 2, "end": 4, "performers": ["X"]})


def test_needs_a_plan_and_a_song_map(tmp_path):
    with pytest.raises(SystemExit):
        C.brief(str(tmp_path))


def test_openai_out_of_credits_is_explained():
    from filmcrafter_engine.director import openai_error
    e = Exception("Error code: 429 - {'error': {'type': 'insufficient_quota', 'code': 'credit_balance_exhausted'}}")
    assert "out of credits" in openai_error(e) and "Billing" in openai_error(e)
    assert "Wait a minute" in openai_error(Exception("RateLimitError: 429 too many requests"))
