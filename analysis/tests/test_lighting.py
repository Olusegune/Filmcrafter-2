"""The Lighting Designer: mood reading, light design, sequence planning, applying and undoing."""
import json
import os

import pytest

from pulseframe_analysis import camera as C, lighting as L


def shot(i, emotion="", start=0.0, end=3.0, **kw):
    return {"id": f"S01-{i:02d}", "scene": 1, "number": i, "start": start, "end": end, "beats": kw.pop("beats", []), "performers": [], "framing": "medium", "camera_moves": [],
            "source_shots": [], "emotion": emotion, **kw}


@pytest.fixture
def project(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    s1 = [shot(1, "grief, quiet loss", 0, 3, performance_intensity=3, section="verse"),
          shot(2, "", 3, 6, beats=["She stares at the wall."], section="verse"),                 # nothing named: the song decides
          shot(3, "grief and sorrow", 6, 9, performance_intensity=3, section="verse")]
    s2 = [shot(4, "joy, celebration, dancing", 9, 12, performance_intensity=9, section="chorus"),
          shot(5, "rage", 12, 15, performance_intensity=10, section="chorus")]
    plan = {"meta": {}, "characters": [], "scenes": [
        {"number": 1, "heading": "INT. KITCHEN - NIGHT", "start": 0, "end": 9, "notes": {"Set": "a bare kitchen, one lamp"}, "shots": s1},
        {"number": 2, "heading": "EXT. STREET - DAY", "start": 9, "end": 15, "notes": {}, "shots": s2}]}
    for sc in plan["scenes"]:
        for sh in sc["shots"]:
            sh["id"] = f"S{sc['number']:02d}-{sh['number']:02d}"
    (d / "production.json").write_text(json.dumps(plan))
    curve = [[t, 0.2 if t < 9 else 0.95] for t in range(0, 16)]
    (d / "songmap.json").write_text(json.dumps({"duration": 15, "energy_curve": curve, "sections": [], "beats": [],
                                                "lyrics": [{"text": "goodbye my love", "start": 6.5, "end": 8}]}))
    return str(d)


# ---------------------------------------------------------------- reading the mood

def test_the_directors_word_counts_most():
    assert L.read_mood({"emotion": "rage", "beats": ["She smiles."]})["mood"] == "anger"
    assert L.read_mood({"emotion": "tender longing, intimate"})["mood"] in ("tenderness", "desire")


def test_sung_words_and_the_action_count_too():
    assert L.read_mood({"emotion": "", "beats": ["He stands alone in an empty room."]})["mood"] == "loneliness"
    assert L.read_mood({"emotion": ""}, ["goodbye, I lost him"])["mood"] == "grief"


def test_with_no_words_the_song_and_the_performance_decide():
    loud = L.read_mood({"performance_intensity": 10}, [], 1.0, "final chorus")
    quiet = L.read_mood({"performance_intensity": 1}, [], 0.0, "verse")
    assert loud["mood"] == "ecstasy" and loud["confidence"] <= 0.2 and "names no feeling" in loud["basis"]
    assert quiet["mood"] == "calm"
    assert loud["arousal"] > quiet["arousal"]


def test_two_readings_of_the_same_words_are_split_by_how_intense_the_shot_is():
    calm = L.read_mood({"emotion": "calm and joy", "performance_intensity": 1}, [], 0.0)
    wild = L.read_mood({"emotion": "calm and joy", "performance_intensity": 10}, [], 1.0)
    assert calm["mood"] == "calm" and wild["mood"] == "joy"


def test_bad_numbers_never_crash():
    assert L.read_mood({"emotion": "joy", "performance_intensity": "lots"})["intensity"] == 5
    assert 0 <= L.read_mood({"emotion": ""}, None, None, "")["arousal"] <= 1


def test_energy_is_read_against_the_songs_own_range():
    curve = [[0, 10], [5, 20], [10, 30]]
    assert L.energy_at(curve, 0) == 0.0 and L.energy_at(curve, 10) == 1.0 and L.energy_at(curve, 5) == 0.5
    assert L.energy_at([], 3) is None and L.energy_at([[0, 1]], 3) is None
    assert L.energy_at([[0, 1], [1, 1]], 0.5) == 0.5


# ---------------------------------------------------------------- designing the light

def test_every_recipe_uses_real_light_terms():
    ids = {t[0] for t in C.LIGHTING}
    assert {m[0] for m in L.MOODS} == set(L.RECIPES)
    for mood, r in L.RECIPES.items():
        assert r["term"] in ids and r["alt"] in ids, mood
        assert 2000 <= r["kelvin"] <= 8000


def test_a_dark_mood_at_night_stays_cold_and_a_bright_one_goes_warm():
    grief = L.design("grief", 0.2, "INT. KITCHEN - NIGHT")
    joy = L.design("joy", 0.7, "INT. CLUB - NIGHT")
    assert grief["term"] == "lowkey" and grief["kelvin"] >= 6000
    assert joy["term"] == "practical" and joy["kelvin"] <= 3200


def test_daylight_scenes_never_get_moonlight_unless_the_mood_is_dark():
    assert L.design("melancholy", 0.2, "INT. ROOM - DAY")["term"] == "window"
    assert L.design("menace", 0.7, "INT. ROOM - DAY")["term"] == "underlit"
    assert L.design("joy", 0.5, "EXT. FIELD - DUSK")["term"] == "golden"


def test_the_songs_loud_parts_get_more_contrast_but_gentle_moods_stay_gentle():
    assert L.design("tension", 0.9)["level"] > L.design("tension", 0.3)["level"] - 1
    assert L.design("grief", 0.95)["level"] <= 2 and L.design("tenderness", 0.95)["level"] <= 2
    assert L.design("anger", 0.1)["level"] >= 2


def test_the_wording_names_the_light_the_colour_the_direction_and_the_contrast():
    w = L.design("menace", 0.7)["wording"]
    assert "light from below" in w and "K)" in w and "key from below" in w and "contrast" in w and "haze" in w and "flicker" in w


# ---------------------------------------------------------------- planning a sequence

def test_the_plan_covers_every_shot_and_describes_each_scene(project):
    p = L.plan(project)
    assert p["count"] == 5 and [s["shot"] for s in p["shots"]] == ["S01-01", "S01-02", "S01-03", "S02-04", "S02-05"]
    first = p["shots"][0]
    assert first["mood"] == "grief" and first["design"]["term"] == "lowkey" and "grief" in first["why"].lower()
    assert p["scenes"][0]["heading"].startswith("INT. KITCHEN") and p["scenes"][1]["arc"] == "Joy → Anger"


def test_a_shot_with_no_feeling_inherits_its_scenes_mood_instead_of_flickering(project):
    p = {s["shot"]: s for s in L.plan(project)["shots"]}
    assert p["S01-02"]["held"] is True and p["S01-02"]["design"]["term"] == p["S01-01"]["design"]["term"]


def test_the_loud_chorus_is_planned_with_more_contrast_than_the_quiet_verse(project):
    p = {s["shot"]: s for s in L.plan(project)["shots"]}
    assert p["S02-05"]["design"]["level"] > p["S01-01"]["design"]["level"]
    assert p["S02-04"]["design"]["term"] in ("golden", "daylight")                    # joy in a daytime street


def test_a_shot_whose_light_you_chose_is_marked_and_left_alone(project):
    C.set_picks(project, ["S01-01"], {"lighting": "neon"})
    p = {s["shot"]: s for s in L.plan(project)["shots"]}
    assert p["S01-01"]["user_set"] is True
    r = L.apply(project)
    assert "S01-01" in r["skipped"] and "S01-01" not in r["changed"]
    assert C.picked(project, "S01-01")["lighting"] == "neon"


# ---------------------------------------------------------------- applying and undoing

def test_apply_writes_camera_choices_with_the_fuller_wording(project):
    r = L.apply(project)
    assert len(r["changed"]) == 5 and r["undo"]
    pick = C.picked(project, "S01-01")
    assert pick["lighting"] == "lowkey"
    from pulseframe_analysis.planio import find_shot, load_plan
    sh, _ = find_shot(load_plan(project)[1], "S01-01")
    out = C.apply(project, sh)["lighting"]
    assert "about" in out and "K)" in out and "chiaroscuro" in out        # the term's own words, plus the plan's colour, direction and contrast


def test_applied_plans_are_not_mistaken_for_your_own_choices(project):
    L.apply(project)
    assert L.plan(project)["user_set"] == 0
    r = L.apply(project)
    assert len(r["changed"]) == 5 and not r["skipped"]


def test_picking_a_light_yourself_replaces_the_plans_wording(project):
    L.apply(project)
    C.set_picks(project, ["S01-01"], {"lens": "portrait"})                  # another choice keeps the plan's light
    assert json.load(open(os.path.join(project, "camera.json")))["S01-01"]["lighting_text"]
    C.set_picks(project, ["S01-01"], {"lighting": "neon"})
    entry = json.load(open(os.path.join(project, "camera.json")))["S01-01"]
    assert entry["lighting"] == "neon" and "lighting_text" not in entry
    C.set_picks(project, ["S01-02"], {"lighting": ""})                      # clearing the light clears the plan's wording too
    assert "lighting_text" not in (json.load(open(os.path.join(project, "camera.json"))).get("S01-02") or {})


def test_overwrite_replaces_your_own_choice_and_undo_gives_it_back(project):
    C.set_picks(project, ["S01-01"], {"lighting": "neon"})
    L.apply(project, ["S01-01"], overwrite=True)
    assert C.picked(project, "S01-01")["lighting"] == "lowkey"
    assert L.undo(project)["restored"] == ["S01-01"]
    assert C.picked(project, "S01-01")["lighting"] == "neon"


def test_undo_unwinds_in_order_and_refuses_when_there_is_nothing(project):
    with pytest.raises(SystemExit) as e:
        L.undo(project)
    assert "nothing to undo" in str(e.value)
    L.apply(project, ["S01-01"])
    L.apply(project, ["S02-04", "S02-05"])
    assert L.undo(project)["more"] is True
    assert set(json.load(open(os.path.join(project, "camera.json")))) == {"S01-01"}
    assert L.undo(project)["more"] is False
    assert not json.load(open(os.path.join(project, "camera.json")))


def test_applying_to_chosen_shots_touches_only_those(project):
    r = L.apply(project, ["S02-05"])
    assert r["changed"] == ["S02-05"] and set(json.load(open(os.path.join(project, "camera.json")))) == {"S02-05"}


def test_new_light_terms_are_in_the_pickers_vocabulary_and_detected_from_wording():
    ids = {t["id"] for t in C.vocab()["lighting"]["terms"]}
    assert {"window", "noon", "dappled", "split", "fluorescent", "toplight", "underlit", "sodium"} <= ids
    assert C.detect("lit by a sodium streetlamp", "lighting") == "sodium"
    assert C.detect("soft window light", "lighting") == "window"


def test_moods_listing_is_complete():
    m = L.moods()
    assert len(m) == len(L.MOODS) and all({"id", "label", "term", "kelvin"} <= set(x) for x in m)
