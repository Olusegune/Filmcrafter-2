"""Acting depth: timed beats per shot, an emotional arc per character, signature gestures, and how they reach the prompt. The AI brain is a stand-in that records what it was
asked and answers from a script, so nothing is sent anywhere and nothing costs anything."""
import json
import os
from types import SimpleNamespace

import pytest

from filmcrafter_engine import acting as A, director, llm, performance as PF, render as R
from tests.test_render import field, man

SHOTS = [{"id": "S01-01", "scene": 1, "number": 1, "start": 0.0, "end": 4.0, "section": "Verse 1", "performers": ["Beatrice", "Zara"], "description": "Beatrice looks over the room.",
          "emotion": "stern", "performance_intensity": 4, "performance": "She waits.", "expression": "A raised brow.", "framing": "close", "lens": "75 mm"},
         {"id": "S01-02", "scene": 1, "number": 2, "start": 4.0, "end": 9.0, "performers": ["Beatrice"], "description": "She touches her glasses.", "emotion": "embarrassed realization",
          "performance_intensity": 7, "lyrics": ["I knew that."]},
         {"id": "S01-03", "scene": 1, "number": 3, "start": 22.0, "end": 26.0, "performers": ["Beatrice"], "description": "A wide view of the family.", "emotion": "warm"}]
PLAN = {"meta": {}, "characters": [{"name": "Beatrice", "appearance": "A 60-year-old woman.", "motivation": "Order", "acting_notes": "Proud"}, {"name": "Zara", "appearance": "A young woman."}],
        "scenes": [{"number": 1, "heading": "INT.", "shots": SHOTS}]}
SONG = {"duration": 60.0, "sections": [{"start": 0, "end": 20, "group": "Verse", "mood": "tense", "energy": 0.3}, {"start": 20, "end": 40, "group": "Chorus", "mood": "bright", "energy": 0.9},
                                        {"start": 40, "end": 60, "group": "Outro", "mood": "calm", "energy": 0.2}],
        "lyrics": [{"text": "Line one", "start": 2.0, "end": 4.0}, {"text": "Hook line", "start": 25.0, "end": 27.0}]}


@pytest.fixture
def d(tmp_path):
    d = str(tmp_path)
    json.dump(PLAN, open(os.path.join(d, "production.json"), "w"))
    json.dump(SONG, open(os.path.join(d, "songmap.json"), "w"))
    json.dump({"title": "T", "song": "song.wav", "performance": {"default": "natural", "scenes": {}, "characters": {}, "shots": {}}}, open(os.path.join(d, "project.json"), "w"))
    return d


class FakeBrain:
    """Records what it was asked and answers from a script (a list of JSON strings, or exceptions to raise)."""
    def __init__(self, answers):
        self.answers, self.asked = list(answers), []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.asked.append(kw)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return SimpleNamespace(output_text=a if isinstance(a, str) else json.dumps(a))


@pytest.fixture
def brain(monkeypatch):
    def use(answers, local=False):
        b = FakeBrain(answers)
        monkeypatch.setattr(A, "_client", lambda: b)
        monkeypatch.setattr(director, "resolve_model", lambda c, w, vision=False: "test-model")
        monkeypatch.setattr(llm, "is_local", lambda: local)
        return b
    return use


# ---------------------------------------------------------------- beats

def test_beats_are_cleaned_into_order_inside_the_shot_without_overlap():
    raw = [{"t0": 3, "t1": 4, "what": "third"}, {"t0": 0, "t1": 2.5, "what": "first", "eyes": "toward Emmanuel"}, {"t0": 2, "t1": 3.5, "what": "second", "breath": "held"},
           {"t0": 1, "t1": 2, "what": ""}, "junk", None, {"t0": "x", "t1": float("nan"), "what": "weird times"}, {"t0": 99, "t1": 100, "what": "after the shot"}]
    out = A.clean_beats(raw, 4.0)
    assert [b["what"] for b in out] == ["first", "second", "third"]                    # "weird times" has no readable start and no room is left after "third"
    assert all(a["t1"] <= b["t0"] + 1e-9 for a, b in zip(out, out[1:])) and all(0 <= b["t0"] < b["t1"] <= 4.0 for b in out)
    assert out[0]["eyes"] == "toward Emmanuel" and out[1]["breath"] == "held" and "eyes" not in out[1]


def test_a_beat_with_no_readable_start_follows_the_others_if_there_is_room():
    out = A.clean_beats([{"t0": "later", "t1": "soon", "what": "unreadable times"}, {"t0": 0, "t1": 1, "what": "first"}], 6.0)
    assert [b["what"] for b in out] == ["first", "unreadable times"] and out[1]["t0"] >= out[0]["t1"]
    assert [b["what"] for b in A.clean_beats([{"what": "no times at all"}], 6.0)] == ["no times at all"]


def test_beats_are_bounded():
    raw = [{"t0": i * 0.3, "t1": i * 0.3 + 0.3, "what": "x" * 500, "hands": "h" * 500} for i in range(20)]
    out = A.clean_beats(raw, 10.0)
    assert len(out) == A.MAX_BEATS and all(len(b["what"]) <= 240 and len(b["hands"]) <= 120 for b in out)
    assert A.clean_beats("nope", 4.0) == [] and A.clean_beats(None, 4.0) == []


def test_beats_are_saved_read_back_and_cleared(d):
    got = A.beats_set(d, "S01-02", [{"t0": 0, "t1": 2, "what": "She lifts her hand to the glasses", "eyes": "down, then away"}, {"t0": 2, "t1": 5, "what": "A tight smile"}])
    assert got["seconds"] == 5.0 and got["source"] == "you" and [b["what"] for b in got["beats"]] == ["She lifts her hand to the glasses", "A tight smile"]
    assert A.beats_get(d, "S01-02")["beats"][0]["eyes"] == "down, then away"
    assert A.beats_clear(d, "S01-02")["beats"] == []


def test_beats_need_a_shot_in_the_plan_and_something_to_do(d):
    with pytest.raises(SystemExit, match="not in the plan"):
        A.beats_set(d, "S99-99", [{"t0": 0, "t1": 1, "what": "x"}])
    with pytest.raises(SystemExit, match="at least one beat"):
        A.beats_set(d, "S01-01", [{"what": ""}])
    with pytest.raises(SystemExit):
        A.beats_get(d, "../../x")


def test_beats_become_a_timed_sequence_for_a_video_and_the_opening_moment_for_a_keyframe(d):
    A.beats_set(d, "S01-02", [{"t0": 0, "t1": 2, "what": "She lifts her hand to the glasses.", "eyes": "toward Emmanuel", "breath": "held"}, {"t0": 2, "t1": 5, "what": "A tight smile"}])
    shot = SHOTS[1]
    v = A.beats_text(d, shot, "video")
    assert v == "Performance beats, in order: 0 to 2 s: She lifts her hand to the glasses (eyes: toward Emmanuel; breath: held); 2 to 5 s: A tight smile."
    assert A.beats_text(d, shot, "image") == "Opening moment: She lifts her hand to the glasses (eyes: toward Emmanuel; breath: held)."
    assert A.beats_text(d, SHOTS[0], "video") is None


def test_a_long_set_of_beats_drops_the_detail_before_it_drops_a_beat(d):
    A.beats_set(d, "S01-02", [{"t0": i * 0.8, "t1": i * 0.8 + 0.7, "what": "w" * 120, "face": "f" * 120, "eyes": "e" * 120, "hands": "h" * 120, "breath": "b" * 120} for i in range(6)])
    t = A.beats_text(d, SHOTS[1], "video")
    assert t.count(" s: ") == 6 and len(t) < 900 and "eyes:" not in t


# ---------------------------------------------------------------- arc

def test_an_arc_keeps_only_the_songs_own_sections_in_song_order_once_each():
    names = ["Verse 1", "Chorus 1", "Outro 1"]
    out = A.clean_arc([{"section": "outro 1", "emotion": "warm", "intensity": 99}, {"section": "Verse 1", "emotion": "stern", "intensity": -4}, {"section": "verse 1", "emotion": "dup"},
                       {"section": "Bridge 1", "emotion": "unknown section"}, {"section": "Chorus 1", "emotion": ""}, "junk"], names)
    assert [(p["section"], p["emotion"], p["intensity"]) for p in out] == [("Verse 1", "stern", 1), ("Outro 1", "warm", 10)]


def test_an_arc_is_set_per_character_and_cleared_with_no_points(d):
    got = A.arc_set(d, "Beatrice", [{"section": "Verse 1", "emotion": "stern", "intensity": 4}, {"section": "Chorus 1", "emotion": "flustered", "intensity": 7}])
    assert got["sections"] == ["Verse 1", "Chorus 1", "Outro 1"] and [p["emotion"] for p in got["arcs"]["Beatrice"]["points"]] == ["stern", "flustered"] and got["arcs"]["Zara"]["points"] == []
    assert A.arc_set(d, "Beatrice", [])["arcs"]["Beatrice"]["points"] == []
    with pytest.raises(SystemExit, match="not in the plan"):
        A.arc_set(d, "Nobody", [{"section": "Verse 1", "emotion": "x"}])


def test_the_prompt_says_where_a_person_is_in_their_arc(d):
    A.arc_set(d, "Beatrice", [{"section": "Verse 1", "emotion": "stern", "intensity": 4}, {"section": "Chorus 1", "emotion": "flustered", "intensity": 7}, {"section": "Outro 1", "emotion": "warm", "intensity": 3}])
    assert A.arc_text(d, SHOTS[0]) == "Emotional arc: Beatrice is stern at this point of the story (about 4/10), heading towards flustered."          # the shot's section is named
    assert A.arc_text(d, SHOTS[2]) == "Emotional arc: Beatrice is flustered at this point of the story (about 7/10), coming from stern, heading towards warm."   # found by time
    assert A.arc_text(d, {**SHOTS[0], "performers": ["Zara"]}) is None                                                                                       # nobody here has an arc


def test_a_shot_outside_the_arcs_sections_gets_no_arc_line(d):
    A.arc_set(d, "Beatrice", [{"section": "Chorus 1", "emotion": "flustered", "intensity": 7}])
    assert A.arc_text(d, SHOTS[0]) is None


# ---------------------------------------------------------------- business

def test_gestures_are_cleaned_and_limited(d):
    items = [{"when": "flustered", "do": "touches the front of her gele"}] * 12 + [{"when": "", "do": "x"}, "junk"]
    got = A.business_set(d, "Beatrice", items)
    assert len(got["business"]["Beatrice"]) == A.MAX_GESTURES
    with pytest.raises(SystemExit, match="not in the plan"):
        A.business_set(d, "Nobody", items)


def test_the_gesture_that_fits_the_moment_is_the_one_suggested(d):
    A.business_set(d, "Beatrice", [{"when": "angry", "do": "folds her arms"}, {"when": "embarrassed", "do": "touches the front of her gele"}, {"when": "proud", "do": "lifts her chin"}])
    t = A.business_text(d, SHOTS[1])
    assert "touches the front of her gele" in t and "folds her arms" not in t and t.startswith("Signature gestures (use one only if it fits this moment): Beatrice, when embarrassed")


def test_with_no_match_the_first_gesture_is_offered_and_with_none_nothing(d):
    A.business_set(d, "Beatrice", [{"when": "angry", "do": "folds her arms"}, {"when": "proud", "do": "lifts her chin"}])
    assert "folds her arms" in A.business_text(d, SHOTS[2]) and "lifts her chin" not in A.business_text(d, SHOTS[2])
    assert A.business_text(d, {**SHOTS[2], "performers": ["Zara"]}) is None


# ---------------------------------------------------------------- the file travels with a project: read it defensively

def test_a_damaged_acting_file_is_ignored(d):
    for junk in ("{bad", "[]", "null", '{"beats": 5, "arc": [], "business": "x"}', '{"beats": {"S01-02": "x"}, "arc": {"Beatrice": [1]}, "business": {"Beatrice": {}}}'):
        open(os.path.join(d, A.FILE), "w").write(junk)
        assert A.load(d) == {"beats": {}, "arc": {}, "business": {}}
        assert A.beats_get(d, "S01-02")["beats"] == [] and A.arc_text(d, SHOTS[0]) is None and A.business_text(d, SHOTS[1]) is None


# ---------------------------------------------------------------- the AI: price first

def test_a_local_brain_costs_nothing_and_an_online_one_has_a_rough_price(d, brain):
    brain([], local=True)
    e = A.beats_estimate(d, ["S01-01", "S01-02"])
    assert e["usd"] == 0.0 and e["local"] and e["calls"] == 2
    brain([], local=False)
    one, two = A.beats_estimate(d, ["S01-01"]), A.beats_estimate(d, ["S01-01", "S01-02"])
    assert 0 < one["usd"] < 0.1 and two["usd"] > one["usd"] and not two["local"] and "estimate" in two["note"]


def test_the_estimate_skips_shots_that_already_have_beats_unless_asked(d, brain):
    brain([])
    A.beats_set(d, "S01-01", [{"t0": 0, "t1": 2, "what": "mine"}])
    assert A.beats_estimate(d, ["S01-01", "S01-02"])["shots"] == ["S01-02"]
    assert A.beats_estimate(d, ["S01-01", "S01-02"], overwrite=True)["shots"] == ["S01-01", "S01-02"]
    with pytest.raises(SystemExit, match="at least one shot"):
        A.beats_estimate(d, ["S99-99"])


def test_the_director_writes_beats_one_shot_at_a_time_and_marks_them_as_its_own(d, brain):
    good = {"beats": [{"t0": 0, "t1": 2, "what": "Her eyes sweep the room", "face": "a raised brow", "eyes": "left to right", "hands": "", "breath": "slow"},
                      {"t0": 2, "t1": 4, "what": "She settles on Zara", "face": "", "eyes": "steady", "hands": "", "breath": ""}]}
    b = brain([good, good])
    out = A.beats_write(d, ["S01-01", "S01-02"], notes="keep it small")
    assert out["written"] == ["S01-01", "S01-02"] and out["failed"] == {} and len(b.asked) == 2
    got = A.beats_get(d, "S01-01")
    assert got["source"] == "director" and got["beats"][0]["what"] == "Her eyes sweep the room" and got["beats"][0]["breath"] == "slow" and "hands" not in got["beats"][0]
    asked = json.loads(b.asked[0]["input"][1]["content"])
    assert asked["director_notes"] == "keep it small" and asked["people"][0]["name"] == "Beatrice" and asked["seconds"] == 4.0 and asked["framing"] == "close"
    assert b.asked[0]["model"] == "test-model" and b.asked[0]["text"]["format"]["strict"] is True


def test_one_shot_failing_does_not_lose_the_others(d, brain):
    good = {"beats": [{"t0": 0, "t1": 2, "what": "ok", "face": "", "eyes": "", "hands": "", "breath": ""}]}
    brain([Exception("Error code: 429 - rate limit"), good])
    out = A.beats_write(d, ["S01-01", "S01-02"])
    assert out["written"] == ["S01-02"] and "S01-01" in out["failed"] and "limiting requests" in out["failed"]["S01-01"]
    assert A.beats_get(d, "S01-01")["beats"] == []


def test_a_shot_the_director_answered_badly_for_is_reported_not_saved(d, brain):
    brain([{"beats": [{"t0": 0, "t1": 1, "what": "", "face": "", "eyes": "", "hands": "", "breath": ""}]}])
    out = A.beats_write(d, ["S01-01"])
    assert out["written"] == [] and "S01-01" in out["failed"] and A.beats_get(d, "S01-01")["beats"] == []


def test_beats_you_wrote_are_not_replaced_unless_you_say_so(d, brain):
    b = brain([{"beats": [{"t0": 0, "t1": 2, "what": "theirs", "face": "", "eyes": "", "hands": "", "breath": ""}]}])
    A.beats_set(d, "S01-01", [{"t0": 0, "t1": 2, "what": "mine"}])
    out = A.beats_write(d, ["S01-01"])
    assert out["written"] == [] and b.asked == [] and A.beats_get(d, "S01-01")["beats"][0]["what"] == "mine"
    out = A.beats_write(d, ["S01-01"], overwrite=True)
    assert out["written"] == ["S01-01"] and A.beats_get(d, "S01-01")["beats"][0]["what"] == "theirs"


def test_at_most_twelve_shots_are_written_in_one_go(d, brain):
    shots = [{**SHOTS[0], "id": f"S09-{i:02d}", "start": i * 1.0, "end": i * 1.0 + 1.0} for i in range(1, 21)]
    json.dump({**PLAN, "scenes": [{"number": 9, "heading": "INT.", "shots": shots}]}, open(os.path.join(d, "production.json"), "w"))
    brain([])
    assert len(A.beats_estimate(d, [s["id"] for s in shots])["shots"]) == A.SHOTS_PER_CALL


def test_the_director_writes_an_arc_on_the_songs_sections_for_the_characters_asked(d, brain):
    b = brain([{"characters": [{"name": "Beatrice", "points": [{"section": "Verse 1", "emotion": "stern", "intensity": 4, "note": "keeping order"},
                                                                {"section": "Bridge 9", "emotion": "ignored", "intensity": 5, "note": ""},
                                                                {"section": "chorus 1", "emotion": "flustered", "intensity": 12, "note": ""}]},
                               {"name": "Stranger", "points": [{"section": "Verse 1", "emotion": "x", "intensity": 3, "note": ""}]}]}])
    out = A.arc_write(d, ["Beatrice"])
    assert out["written"] == ["Beatrice"]
    pts = out["arcs"]["Beatrice"]["points"]
    assert [(p["section"], p["intensity"]) for p in pts] == [("Verse 1", 4), ("Chorus 1", 10)] and out["arcs"]["Beatrice"]["source"] == "director" and out["arcs"]["Zara"]["points"] == []
    asked = json.loads(b.asked[0]["input"][1]["content"])
    assert [s["name"] for s in asked["sections"]] == ["Verse 1", "Chorus 1", "Outro 1"] and asked["sections"][0]["lyric_lines"] == ["Line one"] and asked["characters"][0]["name"] == "Beatrice"


def test_an_arc_needs_a_listened_to_song(d, brain):
    brain([])
    os.remove(os.path.join(d, "songmap.json"))
    with pytest.raises(SystemExit, match="not been listened to"):
        A.arc_write(d)
    with pytest.raises(SystemExit, match="not been listened to"):
        A.arc_set(d, "Beatrice", [{"section": "Verse 1", "emotion": "x"}])


def test_an_online_failure_while_writing_an_arc_is_explained_in_words(d, brain):
    brain([Exception("Error code: 429 - {'error': {'type': 'insufficient_quota', 'code': 'credit_balance_exhausted'}}")])
    with pytest.raises(SystemExit, match="out of credits"):
        A.arc_write(d)


# ---------------------------------------------------------------- feeling-specific micro-motion

def test_the_micro_motion_belongs_to_the_feeling():
    assert "eyes drop and flick away" in PF.micro_for("Embarrassed realization softened by maternal dignity.")
    assert "jaw tightens" in PF.micro_for("furious")
    assert PF.micro_for("") == "" and PF.micro_for("a feeling no table knows") == ""
    assert PF.micro_for("embarrassed, sad, angry").count(";") == 1                       # two feelings at most, so the line stays short


def test_a_style_adds_the_feelings_motion_to_its_own_for_a_video_but_not_a_keyframe():
    project = {"performance": {"default": "natural"}}
    shot = {"id": "x", "performers": ["Beatrice"], "emotion": "embarrassed realization", "expression": "tight smile"}
    v, i = PF.direction(project, shot, video=True), PF.direction(project, shot, video=False)
    assert "blinks" in v["extra"] and "For this feeling: eyes drop and flick away" in v["extra"]
    assert "For this feeling" not in i["extra"]
    assert "For this feeling" not in PF.direction(project, {**shot, "emotion": "calm", "expression": ""}, video=True)["extra"]


# ---------------------------------------------------------------- the Director follows the arcs

def test_the_directors_brief_carries_the_arcs_of_the_people_in_the_scene(d):
    A.arc_set(d, "Beatrice", [{"section": "Verse 1", "emotion": "stern", "intensity": 4}, {"section": "Chorus 1", "emotion": "flustered", "intensity": 7}])
    A.arc_set(d, "Zara", [{"section": "Verse 1", "emotion": "calm", "intensity": 2}])
    plan = json.load(open(os.path.join(d, "production.json")))
    scene = {**plan["scenes"][0], "start": 0.0, "end": 26.0, "fields": {}, "notes": {}, "characters": ["Beatrice"], "sung_lines": []}
    scene["shots"] = [SHOTS[1], SHOTS[2]]                                           # only Beatrice is in this scene
    brief = json.loads(director.scene_brief({**plan, "meta": {}, "characters": []}, scene, {**SONG, "bpm": 100, "lyrics": []}, director.arcs_of(d)))
    assert list(brief["emotional_arcs"]) == ["Beatrice"] and [p["emotion"] for p in brief["emotional_arcs"]["Beatrice"]] == ["stern", "flustered"]
    assert "emotional_arcs" in director.SYSTEM and "do not\n  reset" in director.SYSTEM.replace("  ", "  ")


def test_without_arcs_the_directors_brief_is_unchanged(d):
    plan = json.load(open(os.path.join(d, "production.json")))
    scene = {**plan["scenes"][0], "start": 0.0, "end": 26.0, "fields": {}, "notes": {}, "characters": ["Beatrice"], "sung_lines": []}
    assert "emotional_arcs" not in json.loads(director.scene_brief({**plan, "meta": {}, "characters": []}, scene, {**SONG, "bpm": 100, "lyrics": []}, director.arcs_of(d)))
    assert director.arcs_of(os.path.join(d, "nowhere")) == {}


# ---------------------------------------------------------------- the prompt

def video_model():
    return man(field("prompt", required=True), field("duration", enum=["4s", "6s", "8s"]), field("image_urls", "array", items="string"))


def still_model():
    return man(field("prompt", required=True), field("image_urls", "array", items="string"))


def prompt(d, shot, model=None, **kw):
    shot = R._with_movement(d, dict(shot))
    return R.compile_request(shot, None, PLAN, json.load(open(os.path.join(d, "project.json"))), model or video_model(), [], **kw)["prompt"]


def test_the_video_prompt_carries_the_beats_the_arc_and_the_gesture(d):
    A.beats_set(d, "S01-02", [{"t0": 0, "t1": 3, "what": "She lifts her hand to the glasses"}, {"t0": 3, "t1": 5, "what": "A tight smile"}])
    A.arc_set(d, "Beatrice", [{"section": "Verse 1", "emotion": "stern", "intensity": 4}, {"section": "Chorus 1", "emotion": "flustered", "intensity": 7}])
    A.business_set(d, "Beatrice", [{"when": "embarrassed", "do": "touches the front of her gele"}])
    shot = {**SHOTS[1], "section": "Chorus 1"}
    p = prompt(d, shot)
    assert "Performance beats, in order: 0 to 3 s: She lifts her hand to the glasses; 3 to 5 s: A tight smile." in p
    assert "Emotional arc: Beatrice is flustered at this point of the story (about 7/10), coming from stern." in p
    assert "Signature gestures (use one only if it fits this moment): Beatrice, when embarrassed: touches the front of her gele." in p
    assert "For this feeling: eyes drop and flick away" in p


def test_a_keyframe_prompt_gets_the_opening_moment_not_the_timeline(d):
    A.beats_set(d, "S01-02", [{"t0": 0, "t1": 3, "what": "She lifts her hand to the glasses"}, {"t0": 3, "t1": 5, "what": "A tight smile"}])
    p = prompt(d, SHOTS[1], still_model())
    assert "Opening moment: She lifts her hand to the glasses." in p and "Performance beats" not in p and "A tight smile" not in p


def test_when_the_prompt_is_too_long_the_beats_outlast_the_gesture(d, monkeypatch):
    A.beats_set(d, "S01-02", [{"t0": 0, "t1": 3, "what": "She lifts her hand to the glasses"}])
    A.business_set(d, "Beatrice", [{"when": "embarrassed", "do": "touches the front of her gele"}])
    wide = prompt(d, SHOTS[1])
    monkeypatch.setattr(R, "known_prompt_limit", lambda m: len(wide.encode("utf-8")) - 150)      # more than the small 'Avoid' line: the gesture has to go too
    tight = prompt(d, SHOTS[1])
    assert "Performance beats" in tight and "Signature gestures" not in tight


def test_a_project_with_none_of_it_has_the_same_prompt_as_before(d):
    p = prompt(d, SHOTS[0])
    assert "Performance beats" not in p and "Emotional arc" not in p and "Signature gestures" not in p and "Opening moment" not in p


# ---------------------------------------------------------------- the command line

def test_the_command_line_answers_in_json(d, capsys):
    assert A.main(["beats_set", d, "--data", json.dumps({"shot": "S01-01", "beats": [{"t0": 0, "t1": 2, "what": "x"}]})]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["data"]["beats"][0]["what"] == "x"
    assert A.main(["get", d]) == 0
    got = json.loads(capsys.readouterr().out.strip().splitlines()[-1])["data"]
    assert got["beats_shots"] == ["S01-01"] and "Beatrice" in got["business"]
    assert A.main(["beats_set", d, "--data", json.dumps({"shot": "S99", "beats": []})]) == 1
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["event"] == "error"
    assert A.main(["beats_set", d, "--data", "[1, 2]"]) == 1                          # data that is not an object is an error in words, not a crash
