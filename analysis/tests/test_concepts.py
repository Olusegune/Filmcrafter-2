"""Three directions, the treatment and the timed shot plan. The language model is a stand-in; nothing leaves the computer."""
import json
import os

import pytest

from pulseframe_analysis import concepts as C

SECTIONS = [{"label": "INTRO", "group": "Intro", "start": 0.0, "end": 8.0, "energy": 3, "mood": "calm"},
            {"label": "VERSE", "group": "Verse 1", "start": 8.0, "end": 24.0, "energy": 5, "mood": "tender"},
            {"label": "CHORUS", "group": "Chorus", "start": 24.0, "end": 40.0, "energy": 9, "mood": "triumphant"}]
LYRICS = [{"section": "VERSE", "text": "Nine months I carry you", "start": 9.0, "end": 12.0}, {"section": "CHORUS", "text": "I AM YOUR MOTHER", "start": 25.0, "end": 28.0}]


@pytest.fixture
def proj(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    json.dump({"title": "Song", "artist": "A", "song": "song.wav", "look": {"style": "auto"}}, open(d / "project.json", "w"))
    json.dump({"duration": 40.0, "bpm": 100, "beats": [i * 0.6 for i in range(66)], "downbeats": [i * 2.4 for i in range(17)], "accents": [], "sections": SECTIONS, "lyrics": LYRICS},
              open(d / "songmap.json", "w"))
    return str(d)


def concept(i, look="stylized_3d"):
    return {"title": f"Idea {i}", "narrative_level": "hybrid", "premise": "p", "hero_frame": "h", "mood": "m", "performance_approach": "pa", "environment": "e",
            "movement": "mv", "palette": ["red"], "suggested_look": look}


class Resp:
    def __init__(self, data): self.output_text = json.dumps(data)


class Client:
    def __init__(self, data): self.data = data; self.calls = []
    class _R:
        pass
    @property
    def responses(self):
        outer = self
        class R:
            @staticmethod
            def create(**kw):
                outer.calls.append(kw)
                return Resp(outer.data)
        return R


def wire(monkeypatch, data):
    c = Client(data)
    monkeypatch.setattr(C, "_client", lambda: c)
    monkeypatch.setattr(C, "resolve_model", lambda client, m, **k: "fake-model")
    return c


def test_the_song_brief_carries_the_sections_lyrics_and_nothing_secret(proj):
    b = C.song_brief(proj)
    assert b["title"] == "Song" and b["bpm"] == 100 and [s["label"] for s in b["sections"]] == ["INTRO", "VERSE", "CHORUS"]
    assert b["lyrics_by_section"]["VERSE"] == ["Nine months I carry you"] and "api" not in json.dumps(b).lower()


def test_three_directions_are_trimmed_to_three_and_unknown_looks_become_auto(proj, monkeypatch):
    c = wire(monkeypatch, {"concepts": [concept(1), concept(2, "not_a_look"), concept(3), concept(4)]})
    out = C.directions(proj, "warm and funny")
    assert len(out["concepts"]) == 3 and out["concepts"][1]["suggested_look"] == "auto" and out["model"] == "fake-model"
    saved = json.load(open(os.path.join(proj, "concepts.json")))
    assert saved["concepts"][0]["title"] == "Idea 1"
    user = json.loads(c.calls[0]["input"][1]["content"])
    assert user["artist_notes"] == "warm and funny" and "look_ids" in user and c.calls[0]["text"]["format"]["strict"] is True


def test_a_direction_must_be_chosen_before_the_treatment(proj, monkeypatch):
    wire(monkeypatch, {})
    with pytest.raises(SystemExit, match="Choose one of the three directions"):
        C.treatment(proj, 0)
    json.dump({"concepts": [concept(1)]}, open(os.path.join(proj, "concepts.json"), "w"))
    with pytest.raises(SystemExit, match="Choose one of the three directions"):
        C.treatment(proj, 5)


def scene(first, last, shots=("Wide of the room.", "Close-up of Mara singing."), chars=("Mara",)):
    return {"first_section": first, "last_section": last, "heading": "INT. HOME - DAY", "setting": "s", "atmosphere": "a", "characters": list(chars), "action": "She sings.",
            "camera": "c", "lighting": "l", "performance": "p", "vfx": "", "continuity": "", "shots": list(shots)}


def treatment_data(scenes):
    return {"title": "T", "logline": "L", "visual_style": "vs", "characters": [{"name": "Mara", "archetype": "lead", "appearance": "a", "motivation": "m", "acting_notes": "n"}], "scenes": scenes}


def test_scenes_cover_the_whole_song_in_order_and_the_last_one_runs_to_the_end(proj, monkeypatch):
    json.dump({"concepts": [concept(1)]}, open(os.path.join(proj, "concepts.json"), "w"))
    wire(monkeypatch, treatment_data([scene(0, 0), scene(1, 1)]))                                   # the model forgot the chorus
    out = C.treatment(proj, 0)
    plan = json.load(open(os.path.join(proj, "production.json")))
    assert out["scenes"] == 2 and out["shots"] >= 2
    assert plan["scenes"][0]["start"] == 0.0 and plan["scenes"][-1]["end"] == 40.0
    assert plan["scenes"][0]["end"] == plan["scenes"][1]["start"]                                    # contiguous
    ids = [s["id"] for sc in plan["scenes"] for s in sc["shots"]]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    dlg = plan["scenes"][1]["fields"]["DIALOGUE"]
    assert "Nine months" in dlg and "I AM YOUR MOTHER" in dlg                                       # lyrics land in the scene they are sung in (last scene runs to the end)


def test_out_of_range_overlapping_and_reversed_sections_cannot_break_the_plan(proj):
    t = treatment_data([scene(2, 0), scene(0, 99), scene(1, 1), scene(-5, -1)])
    plan = C.build_plan(proj, concept(1), t)
    assert plan["scenes"] and plan["scenes"][0]["start"] == 0.0 and plan["scenes"][-1]["end"] == 40.0
    starts = [s["start"] for s in plan["scenes"]]
    assert starts == sorted(starts)


def test_a_scene_with_no_shots_gets_one_from_its_action(proj):
    plan = C.build_plan(proj, concept(1), treatment_data([scene(0, 2, shots=())]))
    assert len(plan["scenes"]) == 1 and len(plan["scenes"][0]["shots"]) >= 1


def test_a_song_map_without_sections_is_a_clear_error_not_a_crash(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    json.dump({"title": "S", "song": "s.wav"}, open(d / "project.json", "w"))
    json.dump({"duration": 10.0, "sections": [], "lyrics": [], "beats": [], "downbeats": []}, open(d / "songmap.json", "w"))
    try:
        plan = C.build_plan(str(d), concept(1), treatment_data([scene(0, 0)]))
        assert plan["scenes"] == []                      # nothing to place the scenes on: an empty plan, which the caller reports
    except SystemExit as e:
        assert "section" in str(e).lower()


def test_the_treatment_refuses_to_write_an_empty_plan(tmp_path, monkeypatch):
    d = tmp_path / "e"
    d.mkdir()
    json.dump({"title": "S", "song": "s.wav"}, open(d / "project.json", "w"))
    json.dump({"duration": 10.0, "sections": [], "lyrics": [], "beats": [], "downbeats": []}, open(d / "songmap.json", "w"))
    json.dump({"concepts": [concept(1)]}, open(d / "concepts.json", "w"))
    wire(monkeypatch, treatment_data([scene(0, 0)]))
    with pytest.raises(SystemExit, match="no sections yet"):
        C.treatment(str(d), 0)
    assert not os.path.exists(d / "production.json")
