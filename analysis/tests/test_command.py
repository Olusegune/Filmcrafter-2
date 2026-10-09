"""Director Command: a plain-language note re-directs only the shots it is about, can be undone, and never changes story or timing."""
import json
import os

import pytest

from pulseframe_analysis import command as CM


@pytest.fixture
def proj(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    json.dump({"title": "T", "song": "s.wav"}, open(d / "project.json", "w"))
    json.dump({"duration": 30, "sections": [{"label": "VERSE", "start": 0, "end": 10, "energy": 3, "mood": "x"}, {"label": "CHORUS", "start": 10, "end": 20, "energy": 8, "mood": "y"},
                                             {"label": "CHORUS", "start": 20, "end": 30, "energy": 9, "mood": "z"}], "lyrics": []}, open(d / "songmap.json", "w"))
    shots = [{"id": f"S01-0{i}", "scene": 1, "start": i * 6.0, "end": i * 6.0 + 6.0, "beats": [f"Beat {i}"], "performers": ["Mara"], "framing": "Wide", "emotion": "calm",
              "performance_intensity": 3, "visual_prompt": f"Frame {i}", "revised": None} for i in range(5)]
    json.dump({"scenes": [{"number": 1, "shots": shots}], "characters": [{"name": "Mara", "acting_notes": "restrained"}]}, open(d / "production.json", "w"))
    return str(d)


class Resp:
    def __init__(self, data): self.output_text = json.dumps(data)


class Fake:
    """First call answers which shots the note is about; the second answers the edits."""
    def __init__(self, scope, out): self.queue = [{"shot_ids": scope}, out]; self.seen = []
    @property
    def responses(self):
        outer = self
        class R:
            @staticmethod
            def create(**kw):
                outer.seen.append(kw)
                return Resp(outer.queue.pop(0))
        return R


def wire(monkeypatch, scope, out):
    f = Fake(scope, out)
    monkeypatch.setattr(CM, "_client", lambda: f)
    monkeypatch.setattr(CM, "resolve_model", lambda c, m, **k: "fake")
    return f


def shots_of(d):
    path = os.path.join(d, "directed.json")                 # commands edit the directed plan, seeded from production.json the first time
    path = path if os.path.exists(path) else os.path.join(d, "production.json")
    return {s["id"]: s for sc in json.load(open(path))["scenes"] for s in sc["shots"]}


def test_a_note_changes_only_the_chosen_shots_and_only_direction_fields(proj, monkeypatch):
    wire(monkeypatch, ["S01-03", "S01-04"], {"summary": "More energy in the last chorus.", "not_done": "", "changes": [
        {"shot_id": "S01-03", "edits": [{"field": "emotion", "value": "ecstatic"}, {"field": "performance_intensity", "value": "99"}]},
        {"shot_id": "S01-04", "edits": [{"field": "framing", "value": "Low angle wide"}]},
        {"shot_id": "S01-00", "edits": [{"field": "emotion", "value": "sneaky: outside the scope"}]}]})        # the model strayed outside the scope
    r = CM.run(proj, "Make the last chorus more energetic", None, None)
    s = shots_of(proj)
    assert sorted(r["changed"]) == ["S01-03", "S01-04"] and r["id"]
    assert s["S01-03"]["emotion"] == "ecstatic" and s["S01-03"]["performance_intensity"] == 10                  # clamped to 1..10
    assert s["S01-04"]["framing"] == "Low angle wide" and s["S01-00"]["emotion"] == "calm"
    assert s["S01-03"]["revised"] and s["S01-03"]["start"] == 18.0 and s["S01-03"]["beats"] == ["Beat 3"]       # timing and story untouched


def test_the_model_is_told_the_numbered_sections_and_the_selection(proj, monkeypatch):
    f = wire(monkeypatch, [], {})
    CM.run(proj, "second chorus brighter", "S01-02", 12.5)
    brief = json.loads(f.seen[0]["input"][1]["content"])
    assert [x["name"] for x in brief["sections"]] == ["Verse 1", "Chorus 1", "Chorus 2"] and brief["selected_shot"] == "S01-02" and brief["playhead_seconds"] == 12.5


def test_a_note_that_matches_no_shot_changes_nothing(proj, monkeypatch):
    wire(monkeypatch, ["no-such-shot"], {})
    r = CM.run(proj, "do something odd", None, None)
    assert r["changed"] == [] and r["id"] is None and "No shots matched" in r["summary"]
    assert shots_of(proj)["S01-00"]["emotion"] == "calm"
    assert not os.path.exists(os.path.join(proj, "commands.json"))                                       # nothing happened, nothing to undo


def test_an_unusable_intensity_is_skipped_not_fatal(proj, monkeypatch):
    wire(monkeypatch, ["S01-01"], {"summary": "s", "not_done": "", "changes": [{"shot_id": "S01-01", "edits": [{"field": "performance_intensity", "value": "very high"}, {"field": "emotion", "value": "fierce"}]}]})
    CM.run(proj, "fiercer", None, None)
    s = shots_of(proj)["S01-01"]
    assert s["emotion"] == "fierce" and s["performance_intensity"] == 3


def test_a_command_can_be_undone_once_and_restores_added_fields_too(proj, monkeypatch):
    wire(monkeypatch, ["S01-02"], {"summary": "s", "not_done": "", "changes": [{"shot_id": "S01-02", "edits": [{"field": "lighting", "value": "Golden hour"}, {"field": "emotion", "value": "joy"}]}]})
    r = CM.run(proj, "warmer", None, None)
    assert shots_of(proj)["S01-02"]["lighting"] == "Golden hour"
    out = CM.undo(proj, r["id"])
    s = shots_of(proj)["S01-02"]
    assert out["restored"] == ["S01-02"] and "lighting" not in s and s["emotion"] == "calm" and not s.get("revised")
    with pytest.raises(SystemExit, match="Nothing to undo"):
        CM.undo(proj, r["id"])
    with pytest.raises(SystemExit, match="Nothing to undo"):
        CM.undo(proj, "nope")


def test_the_history_keeps_what_was_asked_and_what_could_not_be_done(proj, monkeypatch):
    wire(monkeypatch, ["S01-01"], {"summary": "Warmer light.", "not_done": "Changing the song is not possible here.", "changes": [{"shot_id": "S01-01", "edits": [{"field": "lighting", "value": "Warm"}]}]})
    r = CM.run(proj, "warmer light and a faster song", None, None)
    assert r["not_done"].startswith("Changing the song")
    hist = json.load(open(os.path.join(proj, "commands.json")))["commands"]
    assert hist[0]["note"] == "warmer light and a faster song" and hist[0]["model"] == "fake"
