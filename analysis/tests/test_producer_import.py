import json
import os
import shutil
import zipfile

import pytest
from PIL import Image

from pulseframe_analysis import library, performance, producer_import as PI, render as R
from pulseframe_analysis.onboarding import choreo_get

HERE = os.path.dirname(__file__)
PLUGIN_ZIP = os.path.join(HERE, "fixtures", "PULSEFRAME_Producer_v1.0.0.zip")
SONGMAP = {"duration": 40.0, "bpm": 120, "beats": [i * 0.5 for i in range(81)], "downbeats": [i * 2.0 for i in range(21)],
           "sections": [{"start": 0, "end": 10, "label": "INTRO"}, {"start": 10, "end": 25, "label": "VERSE"},
                        {"start": 25, "end": 40, "label": "CHORUS"}],
           "lyrics": [{"text": "We ride the night", "start": 12.2, "end": 14.0}, {"text": "Stars fall down", "start": 26.1, "end": 28.0}]}


def _project(tmp_path, name="P", songmap=True):
    d = tmp_path / name
    d.mkdir()
    (d / "project.json").write_text(json.dumps({"title": "P", "song": "song.wav", "look": {"style": "auto"}}))
    (d / "jobs.json").write_text(json.dumps({"jobs": []}))
    if songmap:
        (d / "songmap.json").write_text(json.dumps(SONGMAP))
    return str(d)


def _minimal_package(tmp_path):
    pk = tmp_path / "pkg"
    (pk / "media").mkdir(parents=True)
    Image.new("RGB", (64, 64), (200, 50, 50)).save(pk / "media" / "ada.png")
    Image.new("RGB", (64, 64), (50, 50, 200)).save(pk / "media" / "roof.png")
    (pk / "bible.md").write_text("A rain-soaked city at night. Neon reflections everywhere.")
    m = {"schema_version": "1.0",
         "project": {"id": "p1", "title": "Night Ride", "aspect_ratio": "21:9", "visual_style": "neo-noir 3D animation"},
         "song": {"source": None, "timing_confidence": "unknown"},
         "assets": {"characters": [{"id": "char_ada", "name": "Ada", "kind": "character", "canonical": True, "files": ["media/ada.png"],
                                    "locked_rules": ["red bob haircut", "silver jacket"], "flexible_rules": ["expression"]},
                                   {"id": "char_ben", "name": "Ben", "kind": "character", "files": ["media/missing.png"]}],
                    "environments": [{"id": "env_roof", "name": "Rooftop", "kind": "environment", "files": ["media/roof.png"]}],
                    "wardrobe": [], "props": [], "references": []},
         "choreography": [{"id": "ch_ada", "character_id": "char_ada", "classification": "featured dance",
                           "moves": [{"id": "m1", "name": "Rain Spin", "song_section": "Chorus", "action": "spins with arms out"}]},
                          {"id": "ch_ben", "character_id": "char_ben", "classification": "acting only, restrained"}],
         "shots": [{"id": "SH_010", "song_section": "Intro", "environment_id": "env_roof", "character_ids": ["char_ada"],
                    "action": "Ada looks over the city", "framing": "wide", "camera": "slow crane up", "lighting": "neon rim light",
                    "performance": "calm, searching", "continuity_notes": ["jacket zipped"]},
                   {"id": "SH_020", "lyric_cue": "We ride the night", "environment_id": "env_roof", "character_ids": ["char_ada", "char_ben"],
                    "action": "They walk to the edge", "framing": "medium two-shot"},
                   {"id": "SH_030", "song_section": "Chorus", "environment_id": "env_roof", "character_ids": ["char_ada"],
                    "action": "Ada dances in the rain", "choreography_ids": ["ch_ada"], "framing": "full shot"},
                   {"id": "SH_040", "character_ids": ["char_ghost"], "action": "Empty roof"}],
         "continuity": {"production_bible": "bible.md", "rules": ["It is always raining"], "known_exceptions": ["the flashback is dry"]},
         "qa": {"readiness": "READY WITH WARNINGS", "report": "The sheet for Ben is still missing."}}
    (pk / "manifest.json").write_text(json.dumps(m))
    return str(pk)


def test_type7_example_from_the_real_plugin_zip_imports_as_not_ready(tmp_path):
    info = PI.inspect(PLUGIN_ZIP)
    assert info["title"] == "Type 7" and info["readiness"] == "NOT READY" and info["missing"] == []   # paths resolve
    d = _project(tmp_path)
    rep = PI.apply(d, PLUGIN_ZIP)
    _, lib = library.load(d)
    names = {i["name"] for i in lib["items"]}
    assert {"Neo Dude", "Child"} <= names and all(os.path.exists(os.path.join(d, f)) for i in lib["items"] for f in i["files"])
    ch = choreo_get(d)
    assert len(ch["files"]) == 2 and any("Galaxy Turn" in s["notes"] for s in ch["sections"])
    assert rep["readiness"] == "NOT READY" and not os.path.exists(os.path.join(d, "production.json"))   # no shots: nothing forced


def test_minimal_package_maps_everything_and_reaches_the_prompt(tmp_path):
    d = _project(tmp_path)
    rep = PI.apply(d, _minimal_package(tmp_path))
    p = json.load(open(os.path.join(d, "project.json")))
    assert p["aspect_ratio"] == "21:9" and p["look"]["notes"] == "neo-noir 3D animation"
    assert "always raining" in p["bible"]["rules"] and "Neon" in p["bible"]["world"]
    assert "red bob haircut" not in p["bible"]["rules"]   # locked design goes only to shots with that character
    assert rep["missing_files"] == [{"asset": "Ben", "file": "media/missing.png"}]
    assert {"where": "shot SH_040", "ref": "char_ghost"} in rep["unknown_refs"]
    assert performance.get(d)["characters"]["Ben"] == "restrained"
    plan = json.load(open(os.path.join(d, "production.json")))
    shots = [s for sc in plan["scenes"] for s in sc["shots"]]
    assert [s["external_id"] for s in shots] == ["SH_010", "SH_020", "SH_030", "SH_040"]
    by = {s["external_id"]: s for s in shots}
    assert by["SH_010"]["start"] == 0 and by["SH_020"]["start"] == 12.0 and by["SH_030"]["start"] == 25.0   # section / lyric / beat
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(shots, shots[1:]))
    assert "Rain Spin" in by["SH_030"]["movement"] and by["SH_010"]["environment"].startswith("Rooftop")
    # the imported instructions reach the real request
    m = {"roles": {"prompt": "prompt", "duration": "duration"}, "inputs": [{"name": "prompt", "type": "string", "required": True},
         {"name": "duration", "type": "string", "enum": ["5"]}], "model": "m", "title": "m"}
    project = json.load(open(os.path.join(d, "project.json")))
    sh = R._with_movement(d, by["SH_010"])
    prompt = R.compile_request(sh, None, plan, project, m, [])["prompt"]
    for bit in ("Ada looks over the city", "slow crane up", "neon rim light", "calm, searching", "jacket zipped",
                "red bob haircut", "Rooftop", "always raining"):
        assert bit in prompt, bit
    refs = [r["label"] for r in R._reference_files(d, project, by["SH_010"], plan["scenes"][0])]
    assert any("Ada" in r for r in refs) and any("Rooftop" in r for r in refs)


def test_shots_wait_for_the_song_then_place(tmp_path):
    d = _project(tmp_path, songmap=False)
    PI.apply(d, _minimal_package(tmp_path))
    assert json.load(open(os.path.join(d, "project.json")))["producer_pending"] is True
    assert not os.path.exists(os.path.join(d, "production.json"))
    open(os.path.join(d, "songmap.json"), "w").write(json.dumps(SONGMAP))
    PI.plan(d)
    assert json.load(open(os.path.join(d, "project.json")))["producer_pending"] is False
    assert os.path.exists(os.path.join(d, "production.json"))


def test_reimport_updates_instead_of_duplicating_and_stays_editable(tmp_path):
    d = _project(tmp_path)
    pk = _minimal_package(tmp_path)
    PI.apply(d, pk)
    PI.apply(d, pk)
    _, lib = library.load(d)
    assert sum(1 for i in lib["items"] if i["name"] == "Ada") == 1
    assert sum(1 for s in choreo_get(d)["sections"] if "Rain Spin" in s["notes"]) == 1
    ada = next(i["id"] for i in lib["items"] if i["name"] == "Ada")
    library.upsert(d, {"id": ada, "kind": "character", "name": "Ada R.", "files": [], "notes": "edited"})
    assert any(i["name"] == "Ada R." for i in library.load(d)[1]["items"])
    assert any(f.startswith("production.before-") for f in os.listdir(d))   # earlier plan kept, never deleted


def test_zip_with_unsafe_path_is_refused(tmp_path):
    z = tmp_path / "bad.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("manifest.json", json.dumps({"schema_version": "1.0", "project": {"id": "x", "title": "x"}, "assets": {}}))
        f.writestr("../../evil.txt", "x")
    with pytest.raises(SystemExit, match="unsafe"):
        PI.open_package(str(z))


def test_import_report_shows_in_the_supervisor(tmp_path):
    from pulseframe_analysis import supervisor
    d = _project(tmp_path)
    PI.apply(d, _minimal_package(tmp_path))
    items = [i for i in supervisor.listing(d)["items"] if i["source"] == "production package"]
    titles = [i["title"] for i in items]
    assert "Missing file: Ben" in titles and any(t.startswith("Unknown reference char_ghost") for t in titles)
    assert any("READY WITH WARNINGS" in t for t in titles)


def test_locked_design_only_reaches_shots_with_that_character(tmp_path):
    d = _project(tmp_path)
    PI.apply(d, _minimal_package(tmp_path))
    plan = json.load(open(os.path.join(d, "production.json")))
    by = {s["external_id"]: s for sc in plan["scenes"] for s in sc["shots"]}
    project = json.load(open(os.path.join(d, "project.json")))
    m = {"roles": {"prompt": "prompt", "duration": "duration"}, "inputs": [{"name": "prompt", "type": "string", "required": True},
         {"name": "duration", "type": "string", "enum": ["5"]}], "model": "m", "title": "m"}
    with_ada = R.compile_request(R._with_movement(d, by["SH_010"]), None, plan, project, m, [])["prompt"]
    without = R.compile_request(R._with_movement(d, by["SH_040"]), None, plan, project, m, [])["prompt"]
    assert "red bob haircut" in with_ada and "red bob haircut" not in without


def test_pfproducer_file_opens_like_the_zip(tmp_path):
    p = tmp_path / "Type 7.pfproducer"
    shutil.copy(PLUGIN_ZIP, p)
    assert PI.inspect(str(p))["title"] == "Type 7"


def test_imported_shots_can_be_directed(tmp_path):
    """Direction reads every shot of the plan: an imported plan must carry every field it needs (it once lacked sync_accents)."""
    from pulseframe_analysis import director
    d = _project(tmp_path)
    sm = dict(SONGMAP, accents=[1.0, 5.5, 13.0, 26.5, 30.0])
    open(os.path.join(d, "songmap.json"), "w").write(json.dumps(sm))
    PI.apply(d, _minimal_package(tmp_path))
    plan = json.load(open(os.path.join(d, "production.json")))
    shots = [s for sc in plan["scenes"] for s in sc["shots"]]
    assert all(isinstance(s["sync_accents"], list) for s in shots)
    assert any(s["sync_accents"] for s in shots) and all(a >= s["start"] and a < s["end"] for s in shots for a in s["sync_accents"])
    for sc in plan["scenes"]:
        brief = json.loads(director.scene_brief(plan, sc, sm))
        assert len(brief["planned_shots"]) == len(sc["shots"])
    # a plan imported before the fix has no sync_accents; it must direct too, without being re-imported
    for s in shots:
        s.pop("sync_accents")
    for sc in plan["scenes"]:
        assert all(x["sync_accents"] == [] for x in json.loads(director.scene_brief(plan, sc, sm))["planned_shots"])


def _package_with_specs(tmp_path):
    """A package like the real plugin makes: written specs beside a few pictures, one lineup shared by everyone."""
    pk = tmp_path / "specpkg"
    (pk / "assets").mkdir(parents=True)
    Image.new("RGB", (64, 64), (10, 200, 10)).save(pk / "assets" / "CAST_MASTER.png")
    Image.new("RGB", (64, 64), (10, 10, 200)).save(pk / "assets" / "HOME.png")
    for name in ("ADA", "BEN", "BELL", "HOME"):
        (pk / "assets" / f"{name}_SPEC.md").write_text(f"# {name}\nLOCKED IDENTITY ...")
    (pk / "docs").mkdir()
    (pk / "docs" / "notes.pdf").write_bytes(b"%PDF-1.4")
    m = {"schema_version": "1.0", "project": {"id": "p", "title": "Spec package"}, "song": {},
         "assets": {"characters": [{"id": "char_ada", "name": "Ada", "kind": "character", "files": ["assets/ADA_SPEC.md", "assets/CAST_MASTER.png"]},
                                   {"id": "char_ben", "name": "Ben", "kind": "character", "files": ["assets/BEN_SPEC.md", "assets/CAST_MASTER.png"]}],
                    "environments": [{"id": "env_home", "name": "Home", "kind": "environment", "files": ["assets/HOME_SPEC.md", "assets/HOME.png"]}],
                    "wardrobe": [{"id": "w_ada", "name": "Ada outfit", "kind": "wardrobe", "files": ["assets/ADA_SPEC.md"]}],
                    "props": [{"id": "prop_bell", "name": "Bell", "kind": "prop", "files": ["assets/BELL_SPEC.md"]}],
                    "references": [{"id": "ref_notes", "name": "Notes", "kind": "style", "files": ["docs/notes.pdf"]}]},
         "choreography": [],
         "shots": [{"id": "SH_1", "song_section": "Intro", "environment_id": "env_home", "character_ids": ["char_ada", "char_ben"],
                    "wardrobe_ids": ["w_ada"], "prop_ids": ["prop_bell"], "reference_assets": ["char_ada", "char_ben", "prop_bell", "env_home"],
                    "action": "They meet", "expression": "wary, then amused", "scene": "Home dressed for the party"}],
         "continuity": {}, "qa": {"readiness": "NOT READY"}}
    (pk / "manifest.json").write_text(json.dumps(m))
    return str(pk)


def test_written_specs_and_documents_are_never_sent_as_images(tmp_path):
    d = _project(tmp_path)
    PI.apply(d, _package_with_specs(tmp_path))
    plan = json.load(open(os.path.join(d, "production.json")))
    project = json.load(open(os.path.join(d, "project.json")))
    shot = plan["scenes"][0]["shots"][0]
    refs = library.reference_files(d, project, shot, 1)
    names = sorted(os.path.basename(r["path"]) for r in refs)
    assert names == ["CAST_MASTER.png", "HOME.png"]                                       # no .md spec, no .pdf, nothing but pictures
    assert all(r["media"] == "image" for r in refs)
    assert library.media_kind("x.md") == "document" and library.media_kind("x.pdf") == "document" and library.media_kind("x.json") == "document"
    assert library.media_kind("a.PNG") == "image" and library.media_kind("a.svg") == "image" and library.media_kind("a.mp4") == "video"
    kept = [f for it in project["library"]["items"] for f in it["files"] if f.endswith(".md")]
    assert kept                                                                            # the specs stay in the project; they just aren't references


def test_one_shared_picture_is_sent_once_and_names_everyone_in_it(tmp_path):
    d = _project(tmp_path)
    PI.apply(d, _package_with_specs(tmp_path))
    plan = json.load(open(os.path.join(d, "production.json")))
    project = json.load(open(os.path.join(d, "project.json")))
    refs = library.reference_files(d, project, plan["scenes"][0]["shots"][0], 1)
    cast = [r for r in refs if r["path"].endswith("CAST_MASTER.png")]
    assert len(cast) == 1 and cast[0]["label"].startswith("reference for Ada, Ben (face, expressions, full-body turnaround)")


def test_assets_with_no_picture_are_reported_before_and_after_import(tmp_path):
    pk = _package_with_specs(tmp_path)
    missing = {x["name"] for x in PI.inspect(pk)["without_images"]}
    assert missing == {"Ada outfit", "Bell"}                                                # characters share the lineup; outfit and prop have words only
    d = _project(tmp_path)
    assert {x["name"] for x in PI.apply(d, pk)["without_images"]} == missing


def test_expression_and_the_set_variant_reach_the_shot(tmp_path):
    d = _project(tmp_path)
    PI.apply(d, _package_with_specs(tmp_path))
    shot = json.load(open(os.path.join(d, "production.json")))["scenes"][0]["shots"][0]
    assert shot["expression"] == "wary, then amused" and shot["environment"].endswith("(Home dressed for the party)")
    from pulseframe_analysis import render as R
    lines = R.compile_request(R._with_movement(d, shot), None, {"scenes": []}, json.load(open(os.path.join(d, "project.json"))),
                              {"roles": {"prompt": "prompt"}, "inputs": [{"name": "prompt", "type": "string", "required": True}], "model": "m", "title": "m"}, [])["prompt"]
    assert "wary, then amused" in lines


def test_the_packages_lyrics_travel_with_it_so_cues_can_be_placed(tmp_path):
    pk = _package_with_specs(tmp_path)
    m = json.load(open(os.path.join(pk, "manifest.json")))
    os.makedirs(os.path.join(pk, "sources"))
    open(os.path.join(pk, "sources", "lyrics.txt"), "w", encoding="utf-8").write("[Verse 1]\nWe ride the night\nStars fall down\n")
    open(os.path.join(pk, "sources", "lyrics.pdf"), "wb").write(b"%PDF-1.4")
    m["song"]["lyrics_file"] = "sources/lyrics.txt"
    m["shots"][0]["lyric_cue"] = "We ride the night"
    json.dump(m, open(os.path.join(pk, "manifest.json"), "w"))
    info = PI.inspect(pk)
    assert info["lyrics_text"].startswith("[Verse 1]") and "Stars fall down" in info["lyrics_text"] and info["shots_with_cues"] == 1
    open(os.path.join(pk, "sources", "lyrics.txt"), "w", encoding="utf-8").write("**Style:** Afrobeat" + chr(10) * 2 + "[Verse 1]" + chr(10) + "We **ride** the night" + chr(10))
    cleaned = PI.inspect(pk)["lyrics_text"]
    assert "Style" not in cleaned and "**" not in cleaned and "We ride the night" in cleaned      # a plugin's markdown is not lyrics
    m["song"]["lyrics_file"] = "sources/lyrics.pdf"                                     # a PDF is not read as text
    json.dump(m, open(os.path.join(pk, "manifest.json"), "w"))
    assert PI.inspect(pk)["lyrics_text"] == ""
