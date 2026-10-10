"""Optional writing help, part two: the next step of a story, and one shot's acting, camera and light. It proposes; nothing changes by itself."""
import json

import pytest

from filmcrafter_engine import assist, bible, shots, story

SCRIPT = """INT. KITCHEN - MORNING

Sarah pours tea. A letter lies by the sink.

SARAH
He said he would call.

JOHN
Did you say something?
"""


def _fake(monkeypatch, out, seen=None):
    def call(client, model, system, user, name, schema):
        (seen if seen is not None else []).append({"system": system, "user": json.loads(user), "schema": schema})
        return out
    monkeypatch.setattr(assist, "_call", call)
    import filmcrafter_engine.llm as L
    import filmcrafter_engine.director as D
    monkeypatch.setattr(L, "client", lambda: object())
    monkeypatch.setattr(D, "resolve_model", lambda c, m: "test-model")


def test_the_next_step_of_a_story_goes_one_rung_up_the_ladder(tmp_path):
    for kind, nxt in (("idea", "synopsis"), ("synopsis", "treatment"), ("treatment", "outline"), ("outline", "screenplay")):
        d = story.create(str(tmp_path), "T" + kind, kind, "Some story text here that is long enough to be a story.")["dir"]
        assert assist.next_step(d) == nxt
    sp = story.create(str(tmp_path), "SP", "screenplay", SCRIPT)["dir"]
    with pytest.raises(SystemExit, match="already a screenplay"):
        assist.next_step(sp)
    with pytest.raises(SystemExit, match="already a screenplay"):
        assist.brief(sp, "story")


def test_the_story_brief_carries_the_whole_story_and_the_rules_for_the_step(tmp_path):
    d = story.create(str(tmp_path), "T", "synopsis", "A widow finds a second phone and follows it to a lighthouse.")["dir"]
    br = assist.brief(d, "story")
    assert "second phone" in br["source"] and br["task"] == "write the treatment" and "scene by scene" in br["instructions"]


def test_a_suggested_next_step_is_returned_with_its_kind_and_nothing_is_saved(tmp_path, monkeypatch):
    d = story.create(str(tmp_path), "T", "idea", "A widow finds a second phone.")["dir"]
    seen = []
    _fake(monkeypatch, {"text": "A widow, Mara, finds a second phone in her late husband's coat. She follows its one contact to a lighthouse."}, seen)
    r = assist.suggest(d, "story")
    assert r["proposal"]["kind"] == "synopsis" and r["proposal"]["text"].startswith("A widow, Mara") and r["estimate"]["calls"] == 1
    assert [v["version"] for v in story.status(d)["versions"]] == [1]                       # only proposed: no version was made
    assert "Stay faithful" in seen[0]["system"]


def test_a_screenplay_step_costs_more_than_a_synopsis_step(tmp_path, monkeypatch):
    import filmcrafter_engine.llm as L
    monkeypatch.setattr(L, "is_local", lambda: False)
    monkeypatch.setattr(L, "price_per_mtok", lambda: None)
    a = story.create(str(tmp_path), "A", "idea", "A widow finds a second phone.")["dir"]
    b = story.create(str(tmp_path), "B", "outline", "1. INT. KITCHEN: she finds it.\n2. EXT. SEA: she follows it.")["dir"]
    assert assist.estimate(b, "story")["usd"] > assist.estimate(a, "story")["usd"] and assist.estimate(a, "story")["sends"] == "your whole story so far"


def test_a_shot_brief_has_the_shot_the_people_and_their_part_of_the_story(tmp_path):
    d = story.create(str(tmp_path), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    bible.upsert(d, "character", {"id": "c_sarah", "physical": "Tall, grey eyes", "arc": "From waiting to leaving"})
    ids = [s["id"] for s in shots.breakdown(d)["shots"]]
    sid = next(i for i in ids if shots.get_shot(d, i)["shot"]["dialogue"])
    br = assist.brief(d, "shot", sid)
    assert br["task"] == "plan this shot" and br["shot"]["id"] == sid and any(p["name"].lower() == "sarah" and p["physical"] == "Tall, grey eyes" for p in br["people"])
    assert "pours tea" in br["scene_text"] or "He said he would call" in br["scene_text"]


def test_a_shot_suggestion_keeps_only_real_camera_words_and_never_touches_the_contract(tmp_path, monkeypatch):
    d = story.create(str(tmp_path), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    sid = shots.breakdown(d)["shots"][1]["id"]
    before = open(shots._cpath(d, sid), encoding="utf-8").read()
    _fake(monkeypatch, {"emotional_intention": "Held-back dread", "micro_animation": "A slow breath, a swallow",
                        "beats": [{"character": "Sarah", "what": "Holds the cup too tightly", "want": "He calls", "need": "To accept", "fear": "Being alone", "hiding": "That she packed", "subtext": "Stay",
                                   "start": "Hopeful", "turn": "Doubt", "end": "Resolve"}, {"character": "x", "what": "", "want": "", "need": "", "fear": "", "hiding": "", "subtext": "", "start": "", "turn": "", "end": ""}],
                        "camera": {"framing": "close-up", "angle": "teleport", "lens": "portrait (50mm)", "movement": "locked off", "focus": "shallow", "why": "Her face is where the story is."},
                        "lighting": {"description": "Low window light", "why": "Soft light keeps it quiet."}})
    r = assist.suggest(d, "shot", sid)["proposal"]
    assert r["emotional_intention"] == "Held-back dread" and len(r["beats"]) == 1 and r["beats"][0]["hiding"] == "That she packed"
    assert r["camera"] == {"framing": "close-up", "lens": "portrait (50mm)", "movement": "locked off", "focus": "shallow", "why": "Her face is where the story is."}      # the invented angle is dropped
    assert r["lighting"]["description"] == "Low window light"
    assert open(shots._cpath(d, sid), encoding="utf-8").read() == before
    c = shots.set_fields(d, sid, {"performance": {k: r[k] for k in ("emotional_intention", "beats", "micro_animation")}, "camera": r["camera"], "lighting": r["lighting"]})["shot"]
    assert c["camera"]["framing"] == "close-up" and c["performance"]["beats"][0]["what"].startswith("Holds")        # and what it proposes is exactly what the contract accepts


def test_odd_answers_for_the_new_kinds_never_break_it():
    for kind in ("story", "shot"):
        for out in (None, {}, [], "text", {"text": None}, {"camera": 5}, {"beats": "x"}, {"lighting": []}):
            assert isinstance(assist.clean(kind, out), dict)
