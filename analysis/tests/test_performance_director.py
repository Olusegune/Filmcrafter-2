"""The Performance Director, first part (free, local): what a person wants and hides, the scene Performance Breakdown, acting beats version 2, nudges, and the rule that the engine itself
refuses the two AI actions without the person's yes. Nothing here calls an AI or a provider."""
import hashlib
import json
import os

import pytest

from filmcrafter_engine import acting as A, bible, make, shots, story
from filmcrafter_engine import character_performance as CP, performance_analysis as PA, performance_director as PD, render as R
from tests.test_render import field, man

SCRIPT = """INT. KITCHEN - MORNING

Sarah pours tea. Her hands are shaking and she will not look at him.

SARAH
I'm fine.

JOHN
You don't look fine.

EXT. PLATFORM - NIGHT

Rain on the roof. John waits alone.
"""


@pytest.fixture
def film(tmp_path):
    f = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(f)
    shots.breakdown(f)
    rd = make.sync(f)["render_dir"]
    return f, rd


def shot_ids(rd):
    plan = json.load(open(os.path.join(rd, "production.json")))
    return [s["id"] for sc in plan["scenes"] for s in sc["shots"]]


def script_hash(f):
    h = hashlib.sha1()
    for root, _, files in sorted(os.walk(os.path.join(f, "script"))):
        for n in sorted(files):
            h.update(open(os.path.join(root, n), "rb").read())
    return h.hexdigest()


def prompt_for(rd, sid, quality="standard"):
    plan = json.load(open(os.path.join(rd, "production.json")))
    project = json.load(open(os.path.join(rd, "project.json")))
    shot, scene = R._shot(plan, sid)
    shot = R._with_movement(rd, shot)
    m = man(field("prompt", required=True), field("image_url"), field("duration", enum=["5"]))
    return R.compile_request(shot, scene, plan, project, m, [])["prompt"]


# ---------------------------------------------------------------- where things live

def test_a_film_keeps_its_files_in_the_film_and_a_plain_project_in_itself(film, tmp_path):
    f, rd = film
    assert CP.film_dir(rd) == os.path.abspath(f) and CP.root(rd) == os.path.join(os.path.abspath(f), "performance")
    plain = tmp_path / "song"
    plain.mkdir()
    assert CP.film_dir(str(plain)) is None and CP.root(str(plain)) == os.path.join(os.path.abspath(plain), "performance")


# ---------------------------------------------------------------- B: words that hide a feeling

def test_a_deflection_with_distress_around_it_is_flagged_as_a_reading_and_the_words_are_kept_exactly(film):
    f, rd = film
    before = script_hash(f)
    sc = PA.get(rd)["scenes"][0]
    hit = next(s for s in sc["subtext"] if s["says"] == "I'm fine.")
    assert hit["person"].lower() == "sarah" and hit["confidence"] == "medium" and hit["means"]["source"] == "auto"
    assert "shaking" in hit["why"] or "shak" in hit["why"] and "reading, not a fact" in hit["why"]
    assert script_hash(f) == before                                                     # the screenplay was only read
    assert not any(s["says"] == "You don't look fine." for s in sc["subtext"] if s["confidence"] == "medium")


def test_a_deflection_with_nothing_underneath_says_so_instead_of_guessing(film):
    f, rd = film
    sc = PA.get(rd)["scenes"][1]
    assert sc["subtext"] == []                                                          # no line there, and nothing is invented for it


def test_your_reading_replaces_the_draft_and_survives_a_refresh(film):
    f, rd = film
    sid = PA.get(rd)["scenes"][0]["subtext"][0]["id"]
    out = PD.run(rd, "breakdown_set", {"scene": 1, "path": f"subtext.{sid}", "value": "She is terrified he will leave."})
    hit = next(s for s in out["subtext"] if s["id"] == sid)
    assert hit["means"] == {"value": "She is terrified he will leave.", "source": "you", "from": "your edit"} and hit["confidence"] == "high" and hit["says"] == "I'm fine."
    assert next(s for s in PA.get(rd)["scenes"][0]["subtext"] if s["id"] == sid)["means"]["source"] == "you"
    back = PD.run(rd, "breakdown_reset", {"scene": 1, "path": f"subtext.{sid}"})
    assert next(s for s in back["subtext"] if s["id"] == sid)["means"]["source"] == "auto"


def test_accepting_the_draft_makes_it_yours_and_an_empty_draft_cannot_be_accepted(film):
    f, rd = film
    sc = PA.get(rd)["scenes"][0]
    sid = sc["subtext"][0]["id"]
    out = PD.run(rd, "breakdown_accept", {"scene": 1, "path": f"subtext.{sid}"})
    assert next(s for s in out["subtext"] if s["id"] == sid)["means"]["source"] == "you"
    with pytest.raises(SystemExit):
        PD.run(rd, "breakdown_accept", {"scene": 2, "path": "tension"})                # nothing is written there


def test_every_part_of_a_scene_can_be_written_by_you(film):
    f, rd = film
    name = PA.get(rd)["scenes"][0]["people"][0]["name"]
    PD.run(rd, "breakdown_set", {"scene": 1, "path": "purpose", "value": "She cannot ask him to stay."})
    PD.run(rd, "breakdown_set", {"scene": 1, "path": f"people.{name}.outward", "value": "calm and polite"})
    out = PD.run(rd, "breakdown_set", {"scene": 1, "path": f"people.{name}.inner", "value": "panicking"})
    assert out["fields"]["purpose"]["source"] == "you" and out["people"][0]["outward"]["value"] == "calm and polite" and out["people"][0]["inner"]["source"] == "you"
    stored = json.load(open(os.path.join(f, "performance", "scenes.json")))
    assert stored["schema"] == 1 and stored["scenes"]["1"]["fields"]["purpose"]["value"] == "She cannot ask him to stay."


# ---------------------------------------------------------------- a draft never reaches a prompt; what you wrote does

def test_a_draft_never_reaches_a_prompt_but_your_outward_and_inner_do(film):
    f, rd = film
    sid = shot_ids(rd)[0]
    sc = PA.get(rd)["scenes"][0]
    name = sc["people"][0]["name"]
    assert "Under the surface" not in prompt_for(rd, sid)
    PD.run(rd, "breakdown_set", {"scene": 1, "path": f"people.{name}.outward", "value": "calm and polite"})
    assert "Under the surface" not in prompt_for(rd, sid)                               # both halves are needed to say what differs; one alone is only a note
    PD.run(rd, "breakdown_set", {"scene": 1, "path": f"people.{name}.inner", "value": "panicking"})
    p = prompt_for(rd, sid)
    assert f"{name} shows calm and polite but is privately panicking" in p and "never say it" in p
    PD.run(rd, "breakdown_reset", {"scene": 1, "path": f"people.{name}.inner"})
    assert "Under the surface" not in prompt_for(rd, sid)


# ---------------------------------------------------------------- what a person wants, fears and hides

def test_a_profile_is_saved_apart_from_the_cast_and_shown_beside_what_the_cast_says(film):
    f, rd = film
    name = CP.get(rd)["people"][0]["name"]
    out = CP.set_fields(rd, name, {"desire": "to be taken seriously", "fears": "being left", "stress": "goes very polite", "unknown": "dropped"})
    me = next(p for p in out["people"] if p["name"] == name)
    assert me["profile"]["desire"] == "to be taken seriously" and me["profile"]["stress"] == "goes very polite" and "unknown" not in me["profile"]
    saved = json.load(open(os.path.join(f, "performance", "characters.json")))
    assert saved["schema"] == 1 and set(saved["people"][name]) == {"desire", "fears", "stress", "updated"}
    assert "role" in me["known"] or me["known"] == {} or isinstance(me["known"], dict)
    assert next(p for p in CP.set_fields(rd, name, {"fears": ""})["people"] if p["name"] == name)["profile"]["fears"] == ""
    assert CP.clear(rd, name) and name not in json.load(open(os.path.join(f, "performance", "characters.json")))["people"]


def test_what_you_wrote_about_a_person_reaches_the_prompt_as_one_short_dropped_first_line(film):
    f, rd = film
    sid = next(s for s in shot_ids(rd))
    plan = json.load(open(os.path.join(rd, "production.json")))
    who = next(s for sc in plan["scenes"] for s in sc["shots"] if s["id"] == sid)["performers"][0]
    assert "About the people" not in prompt_for(rd, sid)
    CP.set_fields(rd, who, {"desire": "to be taken seriously", "stress": "goes very polite"})
    p = prompt_for(rd, sid)
    assert f"{who} wants to be taken seriously, under pressure goes very polite." in p and "never state it" in p
    shot = {"id": sid, "performers": [who]}
    assert len(CP.prompt_text(rd, shot)) <= 420
    assert CP.prompt_text(rd, {"id": sid, "performers": ["Nobody"]}) is None


@pytest.mark.security
def test_bad_people_scenes_paths_and_a_damaged_file_are_refused_and_nothing_is_written(film):
    f, rd = film
    for bad in ("Nobody", "", "../x"):
        with pytest.raises(SystemExit):
            CP.set_fields(rd, bad, {"desire": "x"})
    with pytest.raises(SystemExit):
        CP.set_fields(rd, CP.get(rd)["people"][0]["name"], {"nothing": "known"})
    for scene in (None, True, "", "999"):
        with pytest.raises(SystemExit):
            PD.run(rd, "breakdown_set", {"scene": scene, "path": "purpose", "value": "x"})
    for path in ("evil", "people.Nobody.wants", "people.x", "subtext.nope", "purpose.extra", "../x"):
        with pytest.raises(SystemExit):
            PD.run(rd, "breakdown_set", {"scene": 1, "path": path, "value": "x"})
    assert not os.path.exists(os.path.join(f, "performance"))
    os.makedirs(os.path.join(f, "performance"))
    open(os.path.join(f, "performance", "characters.json"), "w").write("{ not json")
    assert CP.load(rd)["people"] == {}                                                  # reading a damaged file does not crash
    with pytest.raises(SystemExit):
        CP.set_fields(rd, CP.get(rd)["people"][0]["name"], {"desire": "x"})
    assert open(os.path.join(f, "performance", "characters.json")).read() == "{ not json"


def test_long_text_is_bounded(film):
    f, rd = film
    name = CP.get(rd)["people"][0]["name"]
    out = CP.set_fields(rd, name, {"desire": "x" * 5000})
    assert len(next(p for p in out["people"] if p["name"] == name)["profile"]["desire"]) == 320
    sc = PD.run(rd, "breakdown_set", {"scene": 1, "path": "purpose", "value": "y" * 5000})
    assert len(sc["fields"]["purpose"]["value"]) == 400


# ---------------------------------------------------------------- beats, version 2

def test_a_version_1_file_opens_unchanged_and_what_this_version_does_not_know_is_kept(film, tmp_path):
    f, rd = film
    sid = shot_ids(rd)[0]
    open(os.path.join(rd, "acting.json"), "w").write(json.dumps({"beats": {sid: {"beats": [{"t0": 0, "t1": 1, "what": "She looks up", "face": "tired"}], "source": "you"}}, "future": {"keep": [1, 2]}}))
    assert A.beats_get(rd, sid)["beats"][0] == {"t0": 0.0, "t1": 1.0, "what": "She looks up", "face": "tired"}
    A.beats_set(rd, sid, [{"t0": 0, "t1": 1, "what": "She looks up", "gaze": "at the door", "change": "dread to relief", "link": "line 1", "continues": True, "source": "you", "confidence": "high", "bogus": 1}])
    saved = json.load(open(os.path.join(rd, "acting.json")))
    assert saved["schema"] == 2 and saved["future"] == {"keep": [1, 2]}
    b = saved["beats"][sid]["beats"][0]
    assert b["gaze"] == "at the door" and b["change"] == "dread to relief" and b["continues"] is True and b["confidence"] == "high" and "bogus" not in b
    assert "gaze: at the door" in A.beats_text(rd, {"id": sid, "start": 0, "end": 4}, "video")


def test_a_beat_that_carries_on_is_said_at_the_start_of_the_next_shot_only(film):
    f, rd = film
    ids = shot_ids(rd)
    plan = json.load(open(os.path.join(rd, "production.json")))
    same = [s["id"] for s in plan["scenes"][0]["shots"]]
    if len(same) < 2:
        pytest.skip("the sample scene has one shot")
    A.beats_set(rd, same[0], [{"t0": 0, "t1": 1, "what": "She stands very still", "continues": True}])
    nxt = next(s for s in plan["scenes"][0]["shots"] if s["id"] == same[1])
    first = plan["scenes"][0]["shots"][0]
    assert A.carry_text(rd, nxt).startswith("Carrying on from the shot before: She stands very still.") and A.carry_text(rd, first) is None
    A.beats_set(rd, same[0], [{"t0": 0, "t1": 1, "what": "She stands very still"}])
    assert A.carry_text(rd, nxt) is None


# ---------------------------------------------------------------- nudges: named choices with a specific effect

def test_each_nudge_adds_its_own_direction_and_can_be_turned_off(film):
    f, rd = film
    sid = shot_ids(rd)[0]
    assert "Direction for this shot" not in prompt_for(rd, sid)
    out = PD.run(rd, "nudge_set", {"shot": sid, "nudge": "restrained", "level": 1})
    assert next(n for n in out["nudges"] if n["id"] == "restrained")["level"] == 1 and "Underplay it:" in prompt_for(rd, sid)
    PD.run(rd, "nudge_set", {"shot": sid, "nudge": "restrained", "level": 2})
    assert "Underplay it strongly" in prompt_for(rd, sid) and "Underplay it:" not in prompt_for(rd, sid)
    PD.run(rd, "nudge_set", {"shot": sid, "nudge": "eyes", "level": 1})
    p = prompt_for(rd, sid)
    assert "Let the eyes carry the feeling" in p and "Underplay it strongly" in p
    PD.run(rd, "nudge_set", {"shot": sid, "nudge": "restrained", "level": 0})
    PD.run(rd, "nudge_set", {"shot": sid, "nudge": "eyes", "level": 0})
    assert "Direction for this shot" not in prompt_for(rd, sid) and "nudges" not in json.load(open(os.path.join(rd, "acting.json")))


def test_every_control_in_the_brief_is_a_named_structured_choice():
    labels = {v["label"] for v in A.NUDGES.values()}
    assert {"More restrained", "More vulnerable", "More hesitant", "More playful", "More tension", "Less exaggerated", "Hold the reaction longer", "Reduce body movement",
            "Let the eyes tell the story"} <= labels
    assert all(v.get("text") for v in A.NUDGES.values())


def test_holding_the_reaction_moves_the_last_beat_and_turning_it_off_puts_the_times_back(film):
    f, rd = film
    sid = shot_ids(rd)[0]
    plan = json.load(open(os.path.join(rd, "production.json")))
    secs = next(s for sc in plan["scenes"] for s in sc["shots"] if s["id"] == sid)
    secs = round(secs["end"] - secs["start"], 2)
    A.beats_set(rd, sid, [{"t0": 0, "t1": secs / 2, "what": "She listens"}, {"t0": secs / 2, "t1": secs, "what": "She looks away"}])
    before = [(b["t0"], b["t1"]) for b in A.beats_get(rd, sid)["beats"]]
    out = PD.run(rd, "nudge_set", {"shot": sid, "nudge": "hold", "level": 1})
    after = [(b["t0"], b["t1"]) for b in out["beats"]["beats"]]
    assert after[1][0] < before[1][0] and after[0][1] < before[0][1] and after[1][1] == before[1][1]            # the last beat starts sooner
    assert all(t1 - t0 >= 0.3 for t0, t1 in after) and "Hold the final reaction" in prompt_for(rd, sid)
    back = PD.run(rd, "nudge_set", {"shot": sid, "nudge": "hold", "level": 0})
    assert [(b["t0"], b["t1"]) for b in back["beats"]["beats"]] == before


def test_holding_needs_no_beats_and_a_bad_nudge_or_shot_is_refused(film):
    f, rd = film
    sid = shot_ids(rd)[0]
    assert PD.run(rd, "nudge_set", {"shot": sid, "nudge": "hold", "level": 1})["beats"]["beats"] == []
    for bad in ("nope", "", None):
        with pytest.raises(SystemExit):
            PD.run(rd, "nudge_set", {"shot": sid, "nudge": bad, "level": 1})
    with pytest.raises(SystemExit):
        PD.run(rd, "nudge_set", {"shot": "S99-99", "nudge": "eyes", "level": 1})


# ---------------------------------------------------------------- a free starting point for beats

def test_suggested_beats_are_automatic_small_and_never_saved(film):
    f, rd = film
    sid = shot_ids(rd)[0]
    out = PD.run(rd, "beats_suggest", {"shot": sid})
    assert 2 <= len(out["beats"]) <= 3 and out["basis"].startswith("A rule-based starting point")
    assert all(b["source"] == "auto" and b["confidence"] == "low" and 0 <= b["t0"] < b["t1"] <= out["seconds"] for b in out["beats"])
    assert [b["t0"] for b in out["beats"]] == sorted(b["t0"] for b in out["beats"])
    assert not os.path.exists(os.path.join(rd, "acting.json")) or sid not in json.load(open(os.path.join(rd, "acting.json")))["beats"]


def test_suggested_beats_use_what_you_wrote_about_outward_and_inner(film):
    f, rd = film
    sid = shot_ids(rd)[0]
    name = PA.get(rd)["scenes"][0]["people"][0]["name"]
    PD.run(rd, "breakdown_set", {"scene": 1, "path": f"people.{name}.outward", "value": "calm and polite"})
    PD.run(rd, "breakdown_set", {"scene": 1, "path": f"people.{name}.inner", "value": "panicking"})
    out = PD.run(rd, "beats_suggest", {"shot": sid})
    assert any("keeps calm and polite on the surface while panicking shows" in b["what"] for b in out["beats"]) and "outward and inner" in out["basis"]


# ---------------------------------------------------------------- the engine refuses the two AI actions without the person's yes

@pytest.mark.security
def test_the_ai_actions_are_refused_without_the_engines_own_confirmation(film, monkeypatch):
    f, rd = film
    sid = shot_ids(rd)[0]
    monkeypatch.setattr(A, "_client", lambda: pytest.fail("the AI brain must not be reached without a confirmation"))
    for call in (lambda: A.beats_write(rd, [sid]), lambda: A.arc_write(rd), lambda: A.beats_write(rd, [sid], confirmed="yes"), lambda: A.arc_write(rd, confirmed=1)):
        with pytest.raises(SystemExit) as e:
            call()
        assert "needs your confirmation" in str(e.value)


@pytest.mark.security
def test_the_command_line_needs_a_real_true_too(film, capsys):
    f, rd = film
    sid = shot_ids(rd)[0]
    for data in ({"shots": [sid]}, {"shots": [sid], "confirmed": "true"}, {"shots": [sid], "confirmed": 1}):
        assert A.main(["beats_write", rd, "--data", json.dumps(data)]) == 1
        assert "needs your confirmation" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["message"]
    assert A.main(["arc_write", rd, "--data", "{}"]) == 1


def test_the_free_estimates_still_need_no_confirmation(film):
    f, rd = film
    sid = shot_ids(rd)[0]
    assert A.beats_estimate(rd, [sid])["shots"] == [sid]


def test_the_command_line_speaks_json(film, capsys):
    f, rd = film
    assert PD.main(["characters_get", rd]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["fields"][0] == "personality"
    assert PD.main(["character_set", rd, "--data", json.dumps({"person": "Nobody", "fields": {"desire": "x"}})]) == 1
    assert json.loads(capsys.readouterr().out)["event"] == "error"
    with pytest.raises(SystemExit):
        PD.main(["delete_everything", rd])
