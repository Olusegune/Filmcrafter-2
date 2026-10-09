"""The in-app Producer: a plan from a song, written as a plugin package and imported by the same importer. The language model is a stand-in."""
import json
import os

import pytest

from filmcrafter_engine import library, producer_import as PI, producer_plan as P, refgen

LYRICS = """[Verse 1]
Nine months I carry you
School fees and uniform
[Chorus]
I AM YOUR MOTHER
Don't you forget
"""


@pytest.fixture
def proj(tmp_path):
    d = tmp_path / "p"
    (d / "assets").mkdir(parents=True)
    json.dump({"title": "I Am Your Mother", "song": "song.wav", "lyrics": "lyrics.txt", "aspect_ratio": "16:9", "state": "ready"}, open(d / "project.json", "w"))
    (d / "lyrics.txt").write_text(LYRICS, encoding="utf-8")
    json.dump({"duration": 40.0, "bpm": 100, "beats": [i * 0.6 for i in range(60)], "accents": [],
               "sections": [{"label": "VERSE", "group": "Verse 1", "start": 0.0, "end": 16.0, "energy": 3, "mood": "tender"},
                            {"label": "CHORUS", "group": "Chorus", "start": 16.0, "end": 40.0, "energy": 8, "mood": "triumphant"}],
               "lyrics": [{"section": "VERSE", "text": "Nine months I carry you", "start": 2.0, "end": 5.0},
                          {"section": "VERSE", "text": "School fees and uniform", "start": 9.0, "end": 12.0},
                          {"section": "CHORUS", "text": "I AM YOUR MOTHER", "start": 18.0, "end": 21.0},
                          {"section": "CHORUS", "text": "Don't you forget", "start": 30.0, "end": 33.0}]},
              open(d / "songmap.json", "w"))
    return str(d)


ASSETS = {
    "visual_style": "Stylized 3D feature animation, warm light.", "world": "A Lagos family home in morning light.", "always": "Same faces and outfits.",
    "palette": "Emerald #0E5A45: Queen outfit", "never_show": "Extra people.", "rules": ["Same room geometry.", "Morning light throughout."] + ["x"] * 12,
    "characters": [
        {"name": "Beatrice Queen Bee", "role": "Mother", "identity": ["60; dark brown skin", "burgundy gele"], "outfit": "Emerald iro and buba, gold trim",
         "performance": "Grand, theatrical.", "classification": "featured dance"},
        {"name": "beatrice queen bee", "role": "dup", "identity": [], "outfit": "dup", "performance": "", "classification": "featured dance"},      # a duplicate name
        {"name": "Zara", "role": "Daughter", "identity": ["28; brown skin"], "outfit": "Terracotta blouse", "performance": "Calm.", "classification": "bogus value"},
        {"name": "Tunde", "role": "Son", "identity": ["30"], "outfit": "Mustard shirt", "performance": "", "classification": "acting only, restrained"},
    ],
    "props": [{"name": "Brass bell", "description": "18 cm brass handbell", "owner": "beatrice queen bee"}, {"name": "Brass bell", "description": "dup", "owner": ""},
              {"name": "Constitution", "description": "Giant burgundy book", "owner": "Nobody Known"}],
    "environments": [{"name": "Family home", "layout": "Kitchen left, hall right, staircase right.", "light": "East morning light.", "variant_of": ""},
                     {"name": "Family home, pageantry", "layout": "Same room, red runner.", "light": "Gold spotlight.", "variant_of": "family home"}],
    "dance": [{"character": "Beatrice Queen Bee", "moves": [{"name": f"Move {i}", "song_section": "Verse 1", "lyric_cue": "", "action": "step", "footwork": "f", "arms": "a",
                                                           "torso": "t", "head_gaze": "g", "energy": 99 if i == 0 else 5} for i in range(12)]},
              {"character": "Tunde", "moves": [{"name": "Should be ignored", "song_section": "Chorus", "lyric_cue": "", "action": "x", "footwork": "", "arms": "", "torso": "", "head_gaze": "", "energy": 5}]}],
}


def shots_for(user):
    out = []
    for sec in user["sections"]:
        for k in range(sec["target_shots"]):
            line = sec["lines"][k] if k < len(sec["lines"]) else ""
            out.append({"section_index": sec["section_index"], "sequence": f"{sec['name']} beat", "lyric_cue": line, "environment": "family home",
                        "characters": ["Beatrice Queen Bee", "zara", "Tunde", "Ghost Person", "Beatrice Queen Bee", "Zara"], "props": ["brass bell", "Constitution", "Mystery"],
                        "action": f"Queen calls to the children ({sec['name']} {k}).", "performance": "Queen: commanding.", "expression": "Queen: tight smile.",
                        "framing": "Medium close-up 50 mm", "camera": "Slow push-in", "lighting": "Warm morning", "continuity": ["Bell in right hand"]})
    return {"shots": out}


@pytest.fixture
def fake(monkeypatch):
    calls = []

    def _ask(name, schema, system, user):
        calls.append((name, user))
        return {**ASSETS, "_model": "fake-model"} if name == "assets" else shots_for(user)
    monkeypatch.setattr(P, "_ask", _ask)
    return calls


# ---------------------------------------------------------------- what the planner is given

def test_the_planner_needs_a_listened_song_and_is_given_real_lines_with_their_times(proj, tmp_path):
    b = P.brief(proj)
    s = b["sections"]
    assert [x["name"] for x in s] == ["Verse 1", "Chorus"] and s[0]["lines"] == ["Nine months I carry you", "School fees and uniform"] and s[0]["line_times"] == [2.0, 9.0]
    assert s[1]["lines"][0] == "I AM YOUR MOTHER" and b["supplied"] == [] and b["script"] == {}
    empty = tmp_path / "e"
    empty.mkdir()
    json.dump({"title": "T"}, open(empty / "project.json", "w"))
    with pytest.raises(SystemExit, match="listened"):
        P.brief(str(empty))


def test_pictures_you_supplied_are_noticed_but_a_planners_own_output_is_not(proj):
    open(os.path.join(proj, "assets", "bea.png"), "wb").write(b"\x89PNG")
    p, lib = library.load(proj)
    lib["items"] += [{"id": "lib1", "kind": "character", "name": "Beatrice Queen Bee", "files": ["assets/bea.png"], "notes": "60; dark brown skin"},
                     {"id": "lib2", "kind": "prop", "name": "No picture", "files": [], "notes": ""},
                     {"id": "lib3", "kind": "character", "name": "Made by import", "files": ["assets/bea.png"], "notes": "", "external_id": "char_x"}]
    library.save_library(proj, p, lib)
    assert [x["name"] for x in P.supplied(proj)] == ["Beatrice Queen Bee"]


# ---------------------------------------------------------------- the cast, props and places

def test_the_models_answer_becomes_clean_ids_and_limits(proj, fake):
    v = P.plan_assets(proj, notes="  theatrical  ", cast="small", dance="lots")
    a = v["assets"]
    assert [c["name"] for c in a["characters"]] == ["Beatrice Queen Bee", "Zara", "Tunde"] and [c["id"] for c in a["characters"]] == ["char_beatrice_queen_bee", "char_zara", "char_tunde"]
    assert a["characters"][1]["classification"] == "acting only, restrained"                            # an unknown classification is not trusted
    assert [p["name"] for p in a["props"]] == ["Brass bell", "Constitution"] and a["props"][0]["owner"] == "char_beatrice_queen_bee" and a["props"][1]["owner"] == ""
    assert [e["id"] for e in a["environments"]] == ["env_family_home", "env_family_home_pageantry"] and a["environments"][1]["variant_of"] == "env_family_home"
    assert len(a["rules"]) == 8 and all(len(r) <= 200 for r in a["rules"])
    dance = {e["character_id"]: e for e in a["choreography"]}
    assert len(dance["char_beatrice_queen_bee"]["moves"]) == P.MAX_MOVES and dance["char_beatrice_queen_bee"]["moves"][0]["energy"] == 10     # capped and clamped
    assert "char_tunde" in dance and dance["char_tunde"]["moves"] == [] and dance["char_tunde"]["classification"] == "acting only, restrained"    # a non-dancer's moves are ignored
    assert v["stage"] == "assets" and v["model"] == "fake-model" and v["counts"] == {"people": 3, "props": 2, "places": 2, "dancers": 1, "shots": 0}
    name, user = fake[0]
    assert name == "assets" and user["cast_size"] == "2 to 4 named people" and user["dance_amount"] == "lots" and user["artist_notes"] == "theatrical"


def test_supplied_people_keep_their_exact_names_and_are_linked_not_redrawn(proj, fake):
    open(os.path.join(proj, "assets", "bea.png"), "wb").write(b"\x89PNG")
    p, lib = library.load(proj)
    lib["items"].append({"id": "lib1", "kind": "character", "name": "Beatrice Queen-Bee Adeyemi", "files": ["assets/bea.png"], "notes": "60; dark brown skin"})
    library.save_library(proj, p, lib)
    a = P.plan_assets(proj)["assets"]
    bea = a["characters"][0]
    assert bea["name"] == "Beatrice Queen-Bee Adeyemi" and bea["library_id"] == "lib1" and "library_id" not in a["characters"][1]       # a close spelling is matched to the real name
    assert fake[0][1]["supplied"][0]["name"] == "Beatrice Queen-Bee Adeyemi"


def test_no_cast_and_no_song_are_refused_plainly(proj, monkeypatch):
    monkeypatch.setattr(P, "_ask", lambda *a, **k: {**ASSETS, "characters": []})
    with pytest.raises(SystemExit, match="cast"):
        P.plan_assets(proj)
    with pytest.raises(SystemExit, match="Choose one of the directions"):
        P.plan_assets(proj, index=5)


def test_a_revision_keeps_the_ids_of_everything_that_kept_its_name(proj, fake, monkeypatch):
    first = P.plan_assets(proj)["assets"]
    P.plan_shots(proj)
    revised = {**ASSETS, "characters": [dict(ASSETS["characters"][0], performance="More theatrical!"), dict(ASSETS["characters"][2]),
                                        {"name": "Auntie Mercy", "role": "Aunt", "identity": ["55"], "outfit": "Plum", "performance": "", "classification": "group dance choreography"}]}
    monkeypatch.setattr(P, "_ask", lambda name, *a, **k: revised)
    v = P.revise_assets(proj, "make Queen Bee more theatrical, add an aunt")
    ids = {c["name"]: c["id"] for c in v["assets"]["characters"]}
    assert ids["Beatrice Queen Bee"] == first["characters"][0]["id"] and ids["Zara"] == "char_zara" and "Auntie Mercy" in ids and "Tunde" not in ids
    assert v["assets"]["characters"][0]["performance"] == "More theatrical!" and v["shots_stale"] is True and v["history"][-1]["what"].startswith("revised")
    with pytest.raises(SystemExit, match="what you'd like"):
        P.revise_assets(proj, "   ")
    monkeypatch.setattr(P, "_ask", lambda *a, **k: {**ASSETS, "characters": []})
    with pytest.raises(SystemExit, match="whole cast"):
        P.revise_assets(proj, "remove everyone")


def test_cards_can_be_edited_by_hand_and_removed_safely(proj, fake):
    P.plan_assets(proj)
    v = P.edit_asset(proj, "characters", "char_zara", {"name": "Zara A.", "identity": ["28", "brown skin", ""], "classification": "nonsense", "role": "x" * 500})
    z = next(c for c in v["assets"]["characters"] if c["id"] == "char_zara")
    assert z["name"] == "Zara A." and z["identity"] == ["28", "brown skin"] and z["classification"] == "acting only, restrained" and len(z["role"]) == 500
    v = P.edit_asset(proj, "characters", "char_zara", {"name": "Tunde"})
    assert next(c for c in v["assets"]["characters"] if c["id"] == "char_zara")["name"] == "Zara A."                                          # a name already taken is refused quietly
    v = P.edit_asset(proj, "world", "", {"world": "A new world", "rules": "a; b; c"})
    assert v["assets"]["world"] == "A new world" and v["assets"]["rules"] == ["a", "b", "c"]
    with pytest.raises(SystemExit, match="isn't a card"):
        P.edit_asset(proj, "bogus", "x", {})
    with pytest.raises(SystemExit, match="any more"):
        P.edit_asset(proj, "props", "prop_ghost", {})
    P.plan_shots(proj)
    v = P.remove_asset(proj, "environments", "env_family_home")
    assert [e["id"] for e in v["assets"]["environments"]] == ["env_family_home_pageantry"] and v["assets"]["environments"][0]["variant_of"] == ""
    assert {s["environment_id"] for s in P.load(proj)["shots"]} == {"env_family_home_pageantry"}                      # no shot is left pointing at a deleted place
    v = P.remove_asset(proj, "characters", "char_beatrice_queen_bee")
    shot = P.load(proj)["shots"][0]
    assert "char_beatrice_queen_bee" not in shot["character_ids"] and "wardrobe_beatrice_queen_bee" not in shot["wardrobe_ids"] and "choreo_beatrice_queen_bee" not in shot["choreography_ids"]
    assert v["shots_stale"] is False
    assert all(c["id"] != "char_beatrice_queen_bee" for c in v["assets"]["characters"]) and all(e["character_id"] != "char_beatrice_queen_bee" for e in v["assets"]["choreography"])
    assert next(p for p in v["assets"]["props"] if p["name"] == "Brass bell")["owner"] == ""
    P.remove_asset(proj, "characters", "char_zara")
    with pytest.raises(SystemExit, match="at least one person"):
        P.remove_asset(proj, "characters", "char_tunde")


# ---------------------------------------------------------------- the shot list

def test_shots_are_matched_to_real_ids_capped_and_laid_on_the_songs_own_lines(proj, fake):
    P.plan_assets(proj)
    v = P.plan_shots(proj)
    plan = P.load(proj)
    shots = plan["shots"]
    assert len(shots) == 4 + 6 and v["stage"] == "shots" and v["counts"]["shots"] == 10                  # 16 s and 24 s at about 4 s a shot
    sh = shots[0]
    assert sh["character_ids"] == ["char_beatrice_queen_bee", "char_zara", "char_tunde"] and sh["wardrobe_ids"] == ["wardrobe_beatrice_queen_bee", "wardrobe_zara", "wardrobe_tunde"]
    assert sh["prop_ids"] == ["prop_brass_bell", "prop_constitution"]                                          # "Ghost Person" and "Mystery" are not in the cast: dropped
    assert sh["environment_id"] == "env_family_home" and sh["choreography_ids"] == ["choreo_beatrice_queen_bee"] and sh["song_section"] == "Verse 1"
    assert shots[0]["lyric_cue"] == "Nine months I carry you" and shots[0]["start_seconds"] == 0.0
    starts = [s["start_seconds"] for s in shots]
    assert starts == sorted(starts) and all(b - a >= 1.0 for a, b in zip(starts, starts[1:]))
    assert shots[0]["start_seconds"] == 0.0                                                                     # the first shot opens the section
    assert next(s for s in shots if s["lyric_cue"] == "School fees and uniform")["start_seconds"] == 9.0          # a shot on a line starts where that line is sung
    assert next(s for s in shots if s["lyric_cue"] == "Don't you forget")["start_seconds"] == 30.0
    assert shots[-1]["end_seconds"] == 40.0 and all(s["end_seconds"] > s["start_seconds"] for s in shots)
    assert all(s["id"] == f"shot_{i + 1:03d}" for i, s in enumerate(shots)) and all(len(s["character_ids"]) <= 4 and len(s["prop_ids"]) <= 2 for s in shots)
    assert fake[1][0] == "shots" and fake[1][1]["roster"]["people"][0]["name"] == "Beatrice Queen Bee"
    dance_free = [s for s in shots if s["song_section"] == "Chorus"]
    assert dance_free[0]["choreography_ids"] == []                                                              # her moves are for Verse 1 only


def test_an_invented_lyric_a_bad_section_and_too_few_shots_are_handled(proj, monkeypatch):
    monkeypatch.setattr(P, "_ask", lambda name, schema, system, user: {**ASSETS} if name == "assets" else {"shots": [
        {**shots_for({"sections": [{"section_index": 0, "name": "Verse 1", "target_shots": 1, "lines": []}]})["shots"][0], "lyric_cue": "Nine months I carried you!"},
        {**shots_for({"sections": [{"section_index": 0, "name": "Verse 1", "target_shots": 1, "lines": []}]})["shots"][0], "lyric_cue": "A line that was never sung", "section_index": 7},
        {**shots_for({"sections": [{"section_index": 0, "name": "Verse 1", "target_shots": 1, "lines": []}]})["shots"][0], "section_index": "zero"}]})
    P.plan_assets(proj)
    v = P.plan_shots(proj)
    s = P.load(proj)["shots"]
    assert s[0]["lyric_cue"] == "Nine months I carry you"                                                       # a near miss is snapped to the real line
    assert all(x["lyric_cue"] in ("", "Nine months I carry you", "I AM YOUR MOTHER", "Don't you forget", "School fees and uniform") for x in s)
    assert len(s) >= 2 and any("No shots were planned" in w or "longer than" in w for w in v["warnings"])         # the chorus got nothing, and that is said


def test_planning_shots_needs_the_cast_first_and_a_changed_cast_blocks_the_build(proj, fake):
    with pytest.raises(SystemExit, match="cast first"):
        P.plan_shots(proj)
    P.plan_assets(proj)
    P.plan_shots(proj)
    P.edit_asset(proj, "characters", "char_zara", {"role": "Sister"})
    assert P.view(proj)["shots_stale"] is False                                                                  # rewording a card never forces a re-plan (and its cost)
    P.revise_assets(proj, "change the cast")
    assert P.view(proj)["shots_stale"] is True
    with pytest.raises(SystemExit, match="Plan the shots again"):
        P.build(proj)


def test_a_long_song_is_planned_in_several_calls_that_remember_the_last_shots(tmp_path, fake):
    d = tmp_path / "long"
    d.mkdir()
    json.dump({"title": "Long", "song": "s.wav", "lyrics": "lyrics.txt"}, open(d / "project.json", "w"))
    (d / "lyrics.txt").write_text("[Verse]\nla\n")
    json.dump({"duration": 240.0, "sections": [{"label": "VERSE", "group": f"Part {i}", "start": i * 40.0, "end": (i + 1) * 40.0, "energy": 5, "mood": "m"} for i in range(6)], "lyrics": []},
              open(d / "songmap.json", "w"))
    P.plan_assets(str(d))
    fake.clear()
    v = P.plan_shots(str(d))
    asked = [c for c in fake if c[0] == "shots"]
    assert len(asked) >= 3 and v["counts"]["shots"] == 60 and asked[0][1]["previous_shots"] == [] and len(asked[1][1]["previous_shots"]) == 3
    assert all(sum(s["target_shots"] for s in c[1]["sections"]) <= P.CHUNK_SHOTS + 10 for c in asked)


# ---------------------------------------------------------------- the package and the import

def test_the_package_is_the_plugins_format_with_a_prompt_for_every_picture(proj, fake):
    P.plan_assets(proj)
    P.plan_shots(proj)
    root = P.write_package(proj, P.load(proj))
    m = json.load(open(os.path.join(root, "filmcrafter_manifest.json")))
    assert m["schema_version"] == "1.0" and m["project"]["aspect_ratio"] == "16:9" and m["project"]["visual_style"].startswith("Stylized 3D") and m["project"]["producer_mode"] == "in_app"
    assert {k: len(v) for k, v in m["assets"].items()} == {"characters": 3, "wardrobe": 3, "props": 2, "environments": 2, "references": 0}
    assert m["continuity"]["world"] and m["continuity"]["never_show"] and len(m["continuity"]["rules"]) == 8 and len(m["shots"]) == 10
    assert all(not k.startswith("_") for sh in m["shots"] for k in sh)
    q = m["assets"]["characters"][0]
    assert q["canonical"] and q["files"] == ["assets/characters/char_beatrice_queen_bee_SPEC.md"] and q["locked_rules"] == ["60; dark brown skin", "burgundy gele"]
    w = m["assets"]["wardrobe"][0]
    assert w["owner_character_id"] == q["id"] and w["files"] == q["files"] and w["locked_rules"] == ["Emerald iro and buba, gold trim"]       # the outfit is drawn on its owner's sheet
    spec = open(os.path.join(root, q["files"][0]), encoding="utf-8").read()
    assert "VISUAL GENERATION PROMPT" in spec and "White background character sheet of Beatrice Queen Bee" in spec and "Emerald iro and buba" in spec and "LOCKED IDENTITY" in spec
    assert "Prop reference sheet on white: Brass bell" in open(os.path.join(root, m["assets"]["props"][0]["files"][0]), encoding="utf-8").read()
    assert "Wide establishing view of Family home" in open(os.path.join(root, m["assets"]["environments"][0]["files"][0]), encoding="utf-8").read()
    assert open(os.path.join(root, "sources", "lyrics.txt"), encoding="utf-8").read().startswith("[Verse 1]")
    info = PI.inspect(root)
    assert info["counts"]["characters"] == 3 and info["counts"]["shots"] == 10 and info["missing"] == [] and info["shots_with_cues"] >= 4


def test_building_imports_everything_places_the_shots_and_leaves_pictures_to_the_generator(proj, fake):
    P.plan_assets(proj)
    P.plan_shots(proj)
    r = P.build(proj)
    assert r["report"]["imported"]["assets"] == 10 and r["report"]["imported"]["shots"] == 10 and r["view"]["stage"] == "built"
    p, lib = library.load(proj)
    names = {i["name"]: i for i in lib["items"]}
    assert names["Beatrice Queen Bee"]["external_id"] == "char_beatrice_queen_bee" and names["Beatrice Queen Bee"]["locked_rules"] == ["60; dark brown skin", "burgundy gele"]
    assert names["Beatrice Queen Bee outfit"]["owner"] == "char_beatrice_queen_bee" and names["Family home"]["kind"] == "set"
    proj_json = json.load(open(os.path.join(proj, "project.json")))
    assert proj_json["bible"]["world"].startswith("A Lagos family home") and proj_json["bible"]["palette"].startswith("Emerald") and proj_json["bible"]["avoid"] == "Extra people."
    assert proj_json["bible"]["rules"].startswith("Same faces and outfits.") and proj_json["producer_plan"]["mode"] == "in_app"
    prod = json.load(open(os.path.join(proj, "production.json")))
    allshots = [s for sc in prod["scenes"] for s in sc["shots"]]
    assert len(allshots) == 10 and allshots[0]["start"] == 0.0 and abs(next(s for s in allshots if s["lyrics"] == ["Don't you forget"])["start"] - 30.0) < 0.5
    assert "Beatrice Queen Bee" in allshots[0]["performers"] and "Move 0" in allshots[0]["movement"]
    cands = {c["name"]: c for c in refgen.candidates(proj)}
    assert {"Beatrice Queen Bee", "Brass bell", "Family home"} <= set(cands) and cands["Zara"]["prompt_from"] == "the spec's own prompt"
    assert "White background character sheet of Zara" in cands["Zara"]["prompt"] and "Prop reference sheet" in cands["Brass bell"]["prompt"]
    assert all(w["kind"] != "wardrobe" for w in r["report"]["without_images"]) and len(r["report"]["without_images"]) == 7        # people, props and places; not the outfits


def test_a_supplied_person_is_reused_not_duplicated_and_keeps_their_pictures(proj, fake):
    open(os.path.join(proj, "assets", "bea.png"), "wb").write(b"\x89PNG")
    p, lib = library.load(proj)
    lib["items"].append({"id": "lib1", "kind": "character", "name": "Beatrice Queen Bee", "files": ["assets/bea.png"], "notes": "60; dark brown skin"})
    library.save_library(proj, p, lib)
    P.plan_assets(proj)
    P.plan_shots(proj)
    r = P.build(proj)
    _, lib = library.load(proj)
    beas = [i for i in lib["items"] if i["name"] == "Beatrice Queen Bee"]
    assert len(beas) == 1 and beas[0]["id"] == "lib1" and beas[0]["external_id"] == "char_beatrice_queen_bee" and beas[0]["files"] == ["assets/bea.png"]
    assert "Beatrice Queen Bee" not in [w["name"] for w in r["report"]["without_images"]]
    assert "Beatrice Queen Bee" not in {c["name"] for c in refgen.candidates(proj)}                                  # she already has a picture: it is not remade
    m = json.load(open(os.path.join(proj, "producer", "package", "filmcrafter_manifest.json")))
    assert m["assets"]["characters"][0]["files"] == [] and not os.path.exists(os.path.join(proj, "producer", "package", "assets", "characters", "char_beatrice_queen_bee_SPEC.md"))


def test_building_again_updates_in_place_and_never_overwrites_a_project_that_has_renders(proj, fake):
    P.plan_assets(proj)
    P.plan_shots(proj)
    P.build(proj)
    n = len(library.load(proj)[1]["items"])
    P.edit_asset(proj, "world", "", {"world": "A different world"})
    P.build(proj)
    assert len(library.load(proj)[1]["items"]) == n and json.load(open(os.path.join(proj, "project.json")))["bible"]["world"] == "A different world"
    json.dump({"jobs": [{"id": "j1", "shot_id": "S01-01", "state": "ready"}]}, open(os.path.join(proj, "jobs.json"), "w"))
    with pytest.raises(SystemExit, match="already has renders"):
        P.build(proj)
    assert P.build(proj, force=True)["view"]["stage"] == "built"                                                       # only when asked for in so many words
    assert any(f.startswith("production.before-") for f in os.listdir(proj))                                          # the earlier plan is kept, never deleted


def test_a_plugin_packages_own_bible_fields_now_reach_the_production_bible(tmp_path):
    d = tmp_path / "pj"
    d.mkdir()
    json.dump({"title": "T", "song": "s.wav"}, open(d / "project.json", "w"))
    pk = tmp_path / "pk"
    pk.mkdir()
    json.dump({"schema_version": "1.0", "project": {"title": "T"}, "song": {}, "assets": {"characters": [], "wardrobe": [], "props": [], "environments": [], "references": []},
               "choreography": [], "shots": [], "qa": {},
               "continuity": {"rules": ["Same room."], "world": "  A warm   family home. " * 100, "always": "Eight named adults.", "palette": "Emerald #0E5A45", "never_show": "Extra people."}},
              open(pk / "m.json", "w"))
    PI.apply(str(d), str(pk))
    b = json.load(open(d / "project.json"))["bible"]
    assert b["world"].startswith("A warm family home.") and len(b["world"]) <= 800 and b["rules"].startswith("Eight named adults. Same room.") and b["palette"] == "Emerald #0E5A45" and b["avoid"] == "Extra people."


def test_the_command_line_speaks_json_and_reports_plain_errors(proj, fake, capsys):
    assert P.main(["get", proj]) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["data"]["stage"] == "start"
    assert P.main(["assets", proj, "--data", json.dumps({"cast": "small"})]) == 0
    assert P.main(["shots", proj]) == 0
    capsys.readouterr()
    assert P.main(["build", proj, "--data", json.dumps({"force": True})]) == 0
    out = [json.loads(l) for l in capsys.readouterr().out.splitlines() if l.startswith("{")]
    assert out[-1]["event"] == "result" and out[-1]["data"]["view"]["stage"] == "built"
    assert P.main(["remove", proj, "--data", json.dumps({"group": "props", "id": "prop_nope"})]) == 0               # removing nothing is harmless
    assert P.main(["revise", proj, "--data", json.dumps({"instruction": ""})]) == 1
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["event"] == "error"
    assert P.main(["reset", proj]) == 0 and P.view(proj)["stage"] == "start"


# ---------------------------------------------------------------- safety

def test_a_hand_edited_plan_cannot_make_the_package_write_outside_its_folder(proj, fake):
    P.plan_assets(proj)
    P.plan_shots(proj)
    plan = json.load(open(os.path.join(proj, "producer", "plan.json"), encoding="utf-8"))
    plan["assets"]["props"][0]["id"] = "../../../escape"
    json.dump(plan, open(os.path.join(proj, "producer", "plan.json"), "w", encoding="utf-8"))
    with pytest.raises(SystemExit, match="unsafe id"):
        P.build(proj)
    assert not os.path.exists(os.path.join(proj, "..", "escape_SPEC.md")) and not os.path.exists(os.path.join(proj, "producer", "package"))


def test_one_model_answer_has_a_known_upper_bound_and_the_answer_is_only_data(proj, monkeypatch):
    seen = {}

    class R:
        output_text = json.dumps({**ASSETS, "characters": ASSETS["characters"][:1]})

    class C:
        class responses:
            @staticmethod
            def create(**kw):
                seen.update(kw)
                return R()
    import filmcrafter_engine.director as D
    monkeypatch.setattr(D, "_client", lambda: C())
    monkeypatch.setattr(D, "resolve_model", lambda c, m: "m")
    P.plan_assets(proj)
    assert seen["max_output_tokens"] == P.MAX_OUTPUT_TOKENS == 24_000 and seen["text"]["format"]["strict"] is True
    assert [m["role"] for m in seen["input"]] == ["system", "user"]                                       # the song, lyrics and notes are never joined into the instructions
    assert "Nine months I carry you" in seen["input"][1]["content"] and "Nine months" not in seen["input"][0]["content"]


# ---------------------------------------------------------------- phase 3: one-card revision and export
def test_a_one_card_revision_cannot_touch_anything_else(proj, fake, monkeypatch):
    first = P.plan_assets(proj)["assets"]
    zara = next(c for c in first["characters"] if c["name"] == "Zara")
    sneaky = {**ASSETS, "world": "CHANGED WORLD", "characters": [dict(ASSETS["characters"][0], performance="SNEAKY"), dict(ASSETS["characters"][2], outfit="Plum gown"),
                                                                 dict(ASSETS["characters"][3])],
              "environments": [dict(ASSETS["environments"][0], layout="CHANGED")], "props": []}
    monkeypatch.setattr(P, "_ask", lambda name, *a, **k: sneaky)
    v = P.revise_assets(proj, "give her a plum gown", only={"group": "characters", "id": zara["id"]})["assets"]
    assert next(c for c in v["characters"] if c["id"] == zara["id"])["outfit"] == "Plum gown"
    assert next(c for c in v["characters"] if c["name"] == "Beatrice Queen Bee")["performance"] != "SNEAKY"
    assert v["world"] == first["world"] and [e["layout"] for e in v["environments"]] == [e["layout"] for e in first["environments"]]
    assert [p["name"] for p in v["props"]] == [p["name"] for p in first["props"]]
    with pytest.raises(SystemExit, match="isn't in the plan"):
        P.revise_assets(proj, "x", only={"group": "characters", "id": "nobody"})
    with pytest.raises(SystemExit, match="isn't in the plan"):
        P.revise_assets(proj, "x", only={"group": "../../etc", "id": "x"})


def test_exporting_makes_a_pfproducer_that_carries_the_pictures_and_opens_again(proj, fake, tmp_path):
    import zipfile
    from PIL import Image
    P.plan_assets(proj)
    P.plan_shots(proj)
    with pytest.raises(SystemExit, match="Build the project first"):
        P.export_package(proj, str(tmp_path / "x.pfproducer"))
    P.build(proj)
    p, lib = library.load(proj)
    bell = next(i for i in lib["items"] if i["name"] == "Brass bell")
    Image.new("RGB", (20, 20), (9, 9, 9)).save(os.path.join(proj, "bell.png"))
    refgen.own(proj, bell["id"], "bell.png")
    with pytest.raises(SystemExit, match=r"\.pfproducer"):
        P.export_package(proj, str(tmp_path / "x.zip"))
    with pytest.raises(SystemExit, match="folder that exists"):
        P.export_package(proj, str(tmp_path / "nope" / "x.pfproducer"))
    out = P.export_package(proj, str(tmp_path / "show.pfproducer"))
    assert out["pictures"] == 1 and os.path.getsize(out["path"]) == out["bytes"] and not os.path.exists(out["path"] + ".part")
    z = zipfile.ZipFile(out["path"])
    m = json.loads(z.read("filmcrafter_manifest.json"))
    bell_entry = next(p for p in m["assets"]["props"] if p["name"] == "Brass bell")
    assert bell_entry["files"][0] == f"assets/pictures/{bell_entry['id']}.png" and bell_entry["files"][0] in z.namelist()
    assert any(n.endswith("PRODUCTION_BIBLE.md") for n in z.namelist())
    d2 = os.path.join(str(tmp_path), "other")                                                       # it opens in another project like any plugin package
    os.makedirs(d2)
    json.dump({"title": "Copy", "song": "s.wav", "state": "ready"}, open(os.path.join(d2, "project.json"), "w"))
    PI.apply(d2, out["path"])
    names = {i["name"]: i for i in library.load(d2)[1]["items"]}
    assert any(f.endswith(".png") for f in names["Brass bell"]["files"])


# ---------------------------------------------------------------- phase 4: shot list review
def test_a_section_is_approved_edited_and_approved_again(proj, fake):
    P.plan_assets(proj)
    v = P.plan_shots(proj)
    secs = list(dict.fromkeys(s["section"] for s in v["shots"]))
    assert v["approved"] == [] and len(secs) == 2
    v = P.approve_sections(proj, [secs[0]])
    assert v["approved"] == [secs[0]]
    shot = next(s for s in v["shots"] if s["section"] == secs[0])
    other = next(e for e in v["assets"]["environments"] if e["id"] != shot["place_id"])
    v = P.edit_shot(proj, shot["id"], {"action": "  A new action  ", "camera": "Slow push-in", "environment_id": other["id"], "prop_ids": ["nope", v["assets"]["props"][0]["id"]]})
    edited = next(s for s in v["shots"] if s["id"] == shot["id"])
    assert edited["action"] == "A new action" and edited["camera"] == "Slow push-in" and edited["place_id"] == other["id"] and edited["prop_ids"] == [v["assets"]["props"][0]["id"]]
    assert v["approved"] == []                                                              # editing a shot takes its section's approval back
    assert P.approve_sections(proj, secs, True)["approved"] == secs
    assert P.approve_sections(proj, [secs[1]], False)["approved"] == [secs[0]]
    with pytest.raises(SystemExit, match="Choose a section"):
        P.approve_sections(proj, ["Nonsense"])
    with pytest.raises(SystemExit, match="Choose one of the places"):
        P.edit_shot(proj, shot["id"], {"environment_id": "../x"})
    with pytest.raises(SystemExit, match="isn't in the plan"):
        P.edit_shot(proj, "nope", {})
    assert P.plan_shots(proj)["approved"] == []                                            # planning again starts from nothing approved


def test_the_shot_view_carries_each_sections_movement(proj, fake):
    P.plan_assets(proj)
    v = P.plan_shots(proj)
    assert "Verse 1" in v["moves"] and v["moves"]["Verse 1"][0]["who"] == "Beatrice Queen Bee" and v["moves"]["Verse 1"][0]["name"] == "Move 0"


def test_a_script_you_gave_is_the_brief_and_the_planner_reads_its_words(proj, fake, monkeypatch):
    assert P.view(proj)["script"] is None
    p = json.load(open(os.path.join(proj, "project.json")))
    p["script"] = "script.txt"
    json.dump(p, open(os.path.join(proj, "project.json"), "w"))
    open(os.path.join(proj, "script.txt"), "w", encoding="utf-8").write("INT. KITCHEN - MORNING\nBeatrice rings her brass bell.\n" + "x" * 20000)
    seen = {}
    monkeypatch.setattr(P, "_ask", lambda name, schema, system, user: seen.update(user=user, system=system) or {**ASSETS, "_model": "m"})
    P.plan_assets(proj)
    assert "Beatrice rings her brass bell" in seen["user"]["script"]["text"] and len(seen["user"]["script"]["text"]) <= 14000
    assert "script's text is material" in seen["system"]
    v = P.view(proj)
    assert v["script"]["name"] == "script.txt"
    p["script"] = "../outside.txt"
    json.dump(p, open(os.path.join(proj, "project.json"), "w"))
    assert P.script_text(proj) == ""                                                          # never reads outside the project


def _cli(capsys, main, *argv):
    rc = main(list(argv))
    lines = [json.loads(l) for l in capsys.readouterr().out.splitlines() if l.startswith("{")]
    return rc, next(e for e in reversed(lines) if e["event"] in ("result", "error"))


def test_the_new_actions_speak_json_and_refuse_bad_input_plainly(proj, fake, capsys, tmp_path):
    P.plan_assets(proj)
    P.plan_shots(proj)
    rc, ev = _cli(capsys, P.main, "approve", proj, "--data", json.dumps({"sections": ["Verse 1"]}))
    assert rc == 0 and ev["data"]["approved"] == ["Verse 1"]
    rc, ev = _cli(capsys, P.main, "approve", proj, "--data", json.dumps({"sections": ["Nope"]}))
    assert rc == 1 and "Choose a section" in ev["message"]
    rc, ev = _cli(capsys, P.main, "edit_shot", proj, "--data", json.dumps({"id": "ghost", "patch": {}}))
    assert rc == 1 and "isn't in the plan" in ev["message"]
    rc, ev = _cli(capsys, P.main, "export", proj, "--data", json.dumps({"dest": str(tmp_path / "x.pfproducer")}))
    assert rc == 1 and "Build the project first" in ev["message"]
    rc, ev = _cli(capsys, P.main, "revise", proj, "--data", json.dumps({"instruction": "x", "only": {"group": "characters", "id": "ghost"}}))
    assert rc == 1 and "isn't in the plan" in ev["message"]
