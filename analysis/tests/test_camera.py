"""The per-shot camera picker: a vocabulary the Director shares, your choices written over its wording, and what reaches the prompt."""
import json
import os

import pytest

from filmcrafter_engine import camera as C, command, director, render as R


def field(name, type="string", **kw):
    return {"name": name, "type": type, "items": None, "enum": kw.get("enum"), "default": None, "minimum": None, "maximum": None,
            "max_items": None, "max_length": None, "description": "", "required": False}


def _video():
    return R._finish("fal", "t/v", "Video", "image-to-video", [field("prompt"), field("duration", enum=["4s", "6s", "8s"])])


def _still():
    return R._finish("fal", "t/i", "Still", "text-to-image", [field("prompt")])


SHOT = {"id": "S01-01", "start": 0.0, "end": 4.0, "beats": ["Ada looks up"], "performers": [], "visual_prompt": "Ada at the window",
        "framing": "Medium close-up, low angle", "lens": "85mm portrait lens", "camera_movement": "slow push-in", "camera_energy": "gentle",
        "lighting": "golden hour glow with long shadows"}


@pytest.fixture
def d(tmp_path):
    p = tmp_path / "p"
    p.mkdir()
    json.dump({"scenes": [{"number": 1, "heading": "INT. ROOM", "shots": [dict(SHOT), {**SHOT, "id": "S01-02", "start": 4.0, "end": 8.0, "framing": "Wide shot"}]}]},
              open(p / "production.json", "w"))
    json.dump({"title": "T"}, open(p / "project.json", "w"))
    json.dump({"jobs": []}, open(p / "jobs.json", "w"))
    return str(p)


def _prompt(shot, man):
    return R.compile_request(shot, None, {"meta": {}}, {"look": {"style": "auto"}}, man, [])["prompt"]


# ---------------------------------------------------------------- the vocabulary

def test_the_vocabulary_is_complete_and_every_term_is_recognised_as_itself():
    v = C.vocab()
    assert set(v) == {"size", "angle", "movement", "lens", "lighting", "focus", "energy"}
    for g, grp in v.items():
        ids = [t["id"] for t in grp["terms"]]
        assert len(ids) == len(set(ids)) and grp["label"] and all(t["label"] for t in grp["terms"]), g
    assert {"rack", "follow", "shallow", "deep"} <= {t["id"] for t in v["focus"]["terms"]} and {"low", "dutch", "ots", "pov", "overhead"} <= {t["id"] for t in v["angle"]["terms"]}
    assert {"golden", "lowkey", "rim", "neon"} <= {t["id"] for t in v["lighting"]["terms"]} and {"handheld", "crane", "whip", "orbit"} <= {t["id"] for t in v["movement"]["terms"]}
    for g, terms in C.GROUPS.items():
        if g == "energy":
            continue
        for tid, label, wording, _rx in terms:
            assert wording and C.detect(wording, g) == tid, f"{g}/{tid}: what we send must read back as the same choice (got {C.detect(wording, g)})"
    assert {t["id"] for t in v["movement"]["terms"] if t["video_only"]} == {t[0] for t in C.MOVEMENT} and {t["id"] for t in v["focus"]["terms"] if t["video_only"]} == {"rack", "follow"}


def test_the_directors_own_wording_is_recognised():
    assert C.detect("Medium close-up, low angle", "size") == "medium_close" and C.detect("Medium close-up, low angle", "angle") == "low"
    assert C.detect("Extreme close-up on her eyes", "size") == "extreme_close" and C.detect("Wide establishing shot", "size") == "extreme_wide"
    assert C.detect("Close-up", "size") == "close" and C.detect("medium shot", "size") == "medium" and C.detect("", "size") is None and C.detect(None, "angle") is None
    assert C.detect("overhead view", "angle") == "overhead" and C.detect("Dutch angle", "angle") == "dutch" and C.detect("over-the-shoulder two-shot", "angle") == "ots"
    assert C.detect("Steadicam follows her down the corridor", "movement") == "gimbal" and C.detect("whip pan to the door", "movement") == "whip"
    assert C.detect("rack focus from the glass to her eyes", "focus") == "rack" and C.detect("neon signs and coloured gels", "lighting") == "neon"
    assert C.detect("nothing about a camera at all", "movement") is None


def test_the_director_and_the_director_command_are_given_the_same_vocabulary():
    for text in (director.SYSTEM, command.SYSTEM):
        assert "{CAMERA}" not in text and "rack focus" in text.lower() and "low angle" in text and "golden hour" in text and "steadicam" in text.lower()
    assert "vary sizes and angles" in director.SYSTEM


# ---------------------------------------------------------------- choosing

def test_a_shot_shows_what_the_director_chose_and_what_you_changed(d):
    g = C.get(d, "S01-01")
    assert g["picked"] == {} and g["changed_since_take"] is False
    assert g["detected"] == {"size": "medium_close", "angle": "low", "movement": "push", "lens": "portrait", "lighting": "golden", "focus": None, "energy": "gentle"}
    assert g["director"]["framing"] == "Medium close-up, low angle"
    r = C.set_picks(d, ["S01-01"], {"angle": "high", "lighting": "neon"})
    assert r["shot"]["picked"] == {"angle": "high", "lighting": "neon"} and r["shot"]["effective"]["lighting"].startswith("coloured neon")
    assert "medium close-up" in r["shot"]["effective"]["framing"] and "high angle" in r["shot"]["effective"]["framing"] and "low angle" not in r["shot"]["effective"]["framing"]


def test_choices_are_checked_cleared_and_can_cover_many_shots(d):
    with pytest.raises(SystemExit, match="isn't a"):
        C.set_picks(d, ["S01-01"], {"angle": "sideways"})
    with pytest.raises(SystemExit, match="S09-99"):
        C.set_picks(d, ["S09-99"], {"angle": "low"})
    with pytest.raises(SystemExit, match="Choose a shot"):
        C.set_picks(d, [], {"angle": "low"})
    assert C.picked(d, "S01-01") == {}                                                                  # a refused choice changed nothing
    C.set_picks(d, ["S01-01", "S01-02", "S01-01"], {"lens": "anamorphic", "focus": "shallow"})
    assert C.picked(d, "S01-01") == C.picked(d, "S01-02") == {"lens": "anamorphic", "focus": "shallow"}
    C.set_picks(d, ["S01-01"], {"lens": ""})                                                            # clearing one group keeps the others
    assert C.picked(d, "S01-01") == {"focus": "shallow"} and C.picked(d, "S01-02")["lens"] == "anamorphic"
    C.set_picks(d, ["S01-01"], {"focus": None})
    assert "S01-01" not in json.load(open(os.path.join(d, "camera.json")))                              # nothing left: no empty entry
    C.reset(d, ["S01-02"])
    assert C.picked(d, "S01-02") == {} and not json.load(open(os.path.join(d, "camera.json")))


def test_choices_replace_the_directors_wording_and_clearing_puts_it_back(d):
    shot = json.load(open(os.path.join(d, "production.json")))["scenes"][0]["shots"][0]
    assert C.apply(d, shot) is shot                                                                     # nothing chosen: untouched
    C.set_picks(d, ["S01-01"], {"size": "extreme_close", "movement": "handheld", "lens": "fisheye", "lighting": "rim", "energy": "kinetic", "focus": "rack"})
    a = C.apply(d, shot)
    assert a["framing"].startswith("extreme close-up on a detail") and "low angle looking up" in a["framing"]   # size chosen, the Director's angle kept
    assert a["camera_movement"].startswith("handheld") and a["camera_moves"] == [] and a["lens"].startswith("fisheye") and a["lighting"].startswith("strong rim")
    assert a["camera_energy"] == "kinetic" and "focus" not in a and "racks focus" in a["focus_motion"].replace("then racks", "racks")
    assert shot["framing"] == "Medium close-up, low angle" and "focus_motion" not in shot                 # a copy: the plan is never changed
    C.reset(d, ["S01-01"])
    assert C.apply(d, shot) is shot


# ---------------------------------------------------------------- what the prompt says

def test_the_prompt_carries_the_choices_and_rack_focus_only_goes_to_video(d):
    shot = json.load(open(os.path.join(d, "production.json")))["scenes"][0]["shots"][0]
    C.set_picks(d, ["S01-01"], {"size": "close", "angle": "dutch", "movement": "orbit", "lens": "anamorphic", "lighting": "lowkey", "focus": "rack"})
    s = R._with_movement(d, shot)
    video = _prompt(s, _video())
    assert "Camera: close-up on the face, Dutch angle" in video and "camera arcs around the subject" in video and "anamorphic lens with oval bokeh" in video
    assert "Lighting: low-key chiaroscuro" in video and "Focus: starts with the foreground sharp" in video
    still = _prompt(s, _still())
    assert "Focus:" not in still and "racks focus" not in still and "Dutch angle" in still               # a still can't pull focus over time
    C.set_picks(d, ["S01-01"], {"focus": "shallow"})
    s2 = R._with_movement(d, shot)
    assert "Focus: shallow depth of field" in _prompt(s2, _still()) and "Focus: shallow depth of field" in _prompt(s2, _video())     # a shallow focus works for both
    off = _prompt(shot, _video())
    assert "Focus:" not in off and "Medium close-up, low angle" in off                                    # no choices: exactly as before


def test_a_changed_camera_is_flagged_against_the_last_take(d):
    jobs = [{"id": "j1", "shot_id": "S01-01", "plan": "production", "state": "ready", "kind": "video", "created": 1000, "output": "x.mp4"}]
    json.dump({"jobs": jobs}, open(os.path.join(d, "jobs.json"), "w"))
    assert C.get(d, "S01-01")["changed_since_take"] is False
    C.set_picks(d, ["S01-01"], {"angle": "high"})                                                       # chosen now, after the take at t=1000
    assert C.get(d, "S01-01")["changed_since_take"] is True
    jobs[0]["created"] = 9_999_999_999                                                                  # a newer take already uses it
    json.dump({"jobs": jobs}, open(os.path.join(d, "jobs.json"), "w"))
    assert C.get(d, "S01-01")["changed_since_take"] is False
