"""A look for one scene or one shot: shot beats scene beats film; older projects and unknown looks behave as before; the look reaches the prompt and is recorded on each job; and
changing a look never renders, charges or touches a take."""
import json
import os

import pytest

from filmcrafter_engine import render as R
from filmcrafter_engine import stylebible as SB

FILM = {"style": "stop-motion"}


def field(name, **kw):
    return {"name": name, "type": "string", "items": None, "enum": None, "default": None, "minimum": None, "maximum": None, "max_items": None, "max_length": None,
            "description": "", "required": kw.get("required", False)}


def model():
    return R._finish("fal", "t/img", "Img", "text-to-image", [field("prompt", required=True)])


def shot(sid, scene):
    return {"id": sid, "scene": scene, "number": 1, "start": 0.0, "end": 2.0, "beats": ["A woman waits."], "performers": [], "framing": "wide", "camera_moves": [], "source_shots": [sid]}


def project(folder, look=None):
    folder.mkdir(parents=True, exist_ok=True)
    d = folder / "p"
    d.mkdir()
    by_scene = {6: [shot("S06-02", 6), shot("S06-03", 6)], 5: [shot("S05-01", 5)]}
    plan = {"meta": {}, "characters": [], "scenes": [{"number": n, "heading": f"INT. ROOM {n}", "start": 0, "end": 2, "notes": {}, "shots": v} for n, v in by_scene.items()]}
    json.dump(plan, open(d / "production.json", "w"))
    json.dump({"title": "T", "song": "song.wav", **({"look": look} if look is not None else {})}, open(d / "project.json", "w"))
    json.dump({"duration": 2.0, "lyrics": [], "sections": [], "beats": []}, open(d / "songmap.json", "w"))
    return str(d)


def prompt_for(d, sid):
    p = json.load(open(os.path.join(d, "project.json")))
    plan = json.load(open(os.path.join(d, "production.json")))
    s, sc = R._shot(plan, sid)
    return R.compile_request(s, sc, plan, p, model(), [])["prompt"]


def saved_look(d):
    return json.load(open(d + "/project.json"))["look"]


# ---------------------------------------------------------------- the order: shot, then scene, then film

def test_a_shot_beats_its_scene_which_beats_the_film():
    p = {"look": {**FILM, "scenes": {"6": "live-action"}, "shots": {"S06-02": "anime"}}}
    assert R.resolve_look(p, 6, "S06-02")["id"] == "anime"
    assert R.resolve_look(p, 6, "S06-03")["id"] == "live-action"
    assert R.resolve_look(p, 5, "S05-01")["id"] == "stop-motion"
    assert R.resolve_look(p, 6)["id"] == "live-action" and R.resolve_look(p)["id"] == "stop-motion"


def test_an_older_project_without_the_keys_behaves_exactly_as_before():
    for look in ({"style": "stop-motion"}, {"style": "stop-motion", "genre": "g-biblical-epic", "notes": "keep her red coat"}, "a hand-painted storybook", None):
        p = {"look": look} if look is not None else {}
        assert R.resolve_look(p, 3, "S03-01") == R.resolve_look(p)


def test_an_unknown_look_id_is_ignored_and_the_next_level_is_used():
    p = {"look": {**FILM, "scenes": {"6": "live-action"}, "shots": {"S06-02": "no-such-look"}}}
    assert R.resolve_look(p, 6, "S06-02")["id"] == "live-action"
    assert R.resolve_look({"look": {**FILM, "scenes": {"6": 5}, "shots": {"S06-02": ["x"]}}}, 6, "S06-02")["id"] == "stop-motion"
    genre = next(k for k, v in R.styles().items() if v.get("family") == "genre")
    assert R.resolve_look({"look": {**FILM, "shots": {"S06-02": genre}}}, 6, "S06-02")["id"] == "stop-motion"      # a genre feel is layered, never a look of its own


def test_the_films_notes_still_apply_in_a_look_of_its_own():
    r = R.resolve_look({"look": {**FILM, "notes": "keep her red coat", "shots": {"S06-02": "anime"}}}, 6, "S06-02")
    assert r["id"] == "anime" and r["prompt"].endswith("keep her red coat") and r["avoid"] == R.styles()["anime"]["avoid"]


# ---------------------------------------------------------------- the prompt and the job

def test_the_look_reaches_the_compiled_prompt(tmp_path):
    d = project(tmp_path, {**FILM, "shots": {"S06-02": "anime"}})
    own = R.styles()["anime"]["prompt"].split(":")[0].rstrip(".")
    assert own in prompt_for(d, "S06-02")
    assert own not in prompt_for(d, "S06-03")


def test_each_job_records_the_look_it_is_made_in(tmp_path, monkeypatch):
    d = project(tmp_path, {**FILM, "scenes": {"6": "live-action"}, "shots": {"S06-02": "anime"}})
    monkeypatch.setattr(R, "manifest", lambda provider, model_id, refresh=False: model())
    R.enqueue(d, ["S06-02", "S06-03", "S05-01"], "fal", "t/img", {}, kind="image")
    got = {j["shot_id"]: j["look"] for j in R.Store(d).jobs}
    assert got == {"S06-02": "anime", "S06-03": "live-action", "S05-01": "stop-motion"}


# ---------------------------------------------------------------- setting and clearing

def test_a_shot_and_a_scene_can_be_set_read_and_cleared(tmp_path):
    d = project(tmp_path, FILM)
    r = SB.set_shot(d, "S06-02", "anime")
    assert r["shots"] == {"S06-02": "anime"} and r["style"]["id"] == "stop-motion"
    r = SB.set_scene(d, 6, "live-action")
    assert {s["scene"]: s["style"] for s in r["scenes"]} == {6: "live-action", 5: None}
    assert saved_look(d) == {**FILM, "scenes": {"6": "live-action"}, "shots": {"S06-02": "anime"}}
    assert SB.set_shot(d, "S06-02", None)["shots"] == {} and "shots" not in saved_look(d)
    SB.set_scene(d, 6, None)
    assert saved_look(d) == FILM
    SB.set_scene(d, 6, "stop-motion")                                                  # the film's own look as a scene's look is just "same as the film"
    assert saved_look(d) == FILM


def test_setting_a_look_keeps_the_rest_of_the_films_look(tmp_path):
    keep = {"style": "stop-motion", "genre": "g-biblical-epic", "notes": "n", "bible": {"x": 1}}
    d = project(tmp_path, keep)
    SB.set_shot(d, "S06-02", "anime")
    assert saved_look(d) == {**keep, "shots": {"S06-02": "anime"}}


def test_a_project_with_no_look_or_a_text_look_can_still_get_one(tmp_path):
    d = project(tmp_path / "a")
    assert SB.set_shot(d, "S06-02", "anime")["style"]["id"] == "auto"
    d = project(tmp_path / "b", "a hand-painted storybook")
    SB.set_shot(d, "S06-02", "anime")
    assert saved_look(d) == {"style": "auto", "notes": "a hand-painted storybook", "shots": {"S06-02": "anime"}}


@pytest.mark.security
def test_a_bad_shot_id_scene_or_look_is_refused_and_nothing_is_written(tmp_path):
    d = project(tmp_path, FILM)
    before = open(d + "/project.json", "rb").read()
    for bad in ("../x", "..", "", "a/b", "a\\b", "S01 02", "x" * 80, None, 7):
        with pytest.raises(SystemExit):
            SB.set_shot(d, bad, "anime")
    for bad in (-1, 10 ** 6, "6", None, True, 1.5):
        with pytest.raises(SystemExit):
            SB.set_scene(d, bad, "anime")
    genre = next(k for k, v in R.styles().items() if v.get("family") == "genre")
    for bad in ("no-such-look", "../x", 5, ["anime"], genre):
        with pytest.raises(SystemExit):
            SB.set_shot(d, "S06-02", bad)
    assert open(d + "/project.json", "rb").read() == before


def test_the_library_offered_has_no_genre_feels(tmp_path):
    ids = {s["id"] for s in SB.read(project(tmp_path, FILM))["styles"]}
    assert "anime" in ids and not any(R.styles()[i].get("family") == "genre" for i in ids)


# ---------------------------------------------------------------- money: a look is a setting, never a render

def test_changing_a_look_never_queues_a_job_or_touches_a_take(tmp_path, monkeypatch):
    d = project(tmp_path, FILM)
    take = {"id": "j1", "shot_id": "S06-02", "plan": "production", "kind": "video", "state": "ready", "look": "stop-motion", "output": "generations/a.mp4", "cost": 0.4}
    json.dump({"jobs": [take]}, open(d + "/jobs.json", "w"))
    before = open(d + "/jobs.json", "rb").read()
    monkeypatch.setattr(R, "enqueue", lambda *a, **k: pytest.fail("a look must never queue a render"))
    monkeypatch.setattr(R, "run", lambda *a, **k: pytest.fail("a look must never start a render"))
    SB.set_shot(d, "S06-02", "anime")
    SB.set_scene(d, 6, "live-action")
    SB.set_shot(d, "S06-02", None)
    assert open(d + "/jobs.json", "rb").read() == before


def test_the_command_line_speaks_json_and_refuses_unknown_actions(tmp_path, capsys):
    d = project(tmp_path, FILM)
    assert SB.main(["set_shot", d, "--data", json.dumps({"shot": "S06-02", "style": "anime"})]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["shots"] == {"S06-02": "anime"}
    assert SB.main(["set_shot", d, "--data", json.dumps({"shot": "../x", "style": "anime"})]) == 1
    assert json.loads(capsys.readouterr().out)["event"] == "error"
    with pytest.raises(SystemExit):
        SB.main(["delete", d])


# ---------------------------------------------------------------- found by QA

SCRIPT = """INT. KITCHEN - MORNING

Sarah jumps off the step, her coat flaring, and lands laughing.

EXT. PLATFORM - NIGHT

Rain on the roof.
"""


@pytest.mark.regression
def test_remaking_the_render_project_keeps_the_looks_of_scenes_and_shots(tmp_path):
    """make.sync rebuilds the render project's look from the Bible every time; it used to drop look.scenes and look.shots with it."""
    from filmcrafter_engine import bible, make, shots, story
    film = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(film)
    shots.breakdown(film)
    rd = make.sync(film)["render_dir"]
    first = json.load(open(os.path.join(rd, "production.json")))["scenes"][0]["shots"][0]["id"]
    SB.set_shot(rd, first, "anime")
    SB.set_scene(rd, 2, "live-action")
    bible.update_rules(film, {"style": {"lane": "feature 3D"}})                      # the film's look changes, then the render project is made again
    pj = json.load(open(os.path.join(make.sync(film)["render_dir"], "project.json")))
    assert pj["look"]["style"] == "feature-3d"
    assert pj["look"]["shots"] == {first: "anime"} and pj["look"]["scenes"] == {"2": "live-action"}


@pytest.mark.security
def test_a_folder_that_is_not_a_project_is_refused_and_nothing_is_created(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    for call in (lambda: SB.set_shot(str(empty), "S01-01", "anime"), lambda: SB.set_scene(str(empty), 1, "anime")):
        with pytest.raises(SystemExit):
            call()
    assert os.listdir(empty) == []
    assert SB.read(str(empty))["shots"] == {}                                              # reading is harmless


def test_a_damaged_project_file_is_left_alone_and_said_so(tmp_path):
    d = project(tmp_path, FILM)
    open(d + "/project.json", "w").write("{ not json")
    with pytest.raises(SystemExit):
        SB.set_shot(d, "S06-02", "anime")
    assert open(d + "/project.json").read() == "{ not json"                                  # not replaced by defaults: the filmmaker's file is kept as it is


@pytest.mark.integration
def test_the_app_calls_it_as_a_process_and_parallel_changes_are_not_lost(tmp_path):
    """The app runs `python -m filmcrafter_engine.stylebible` once per click; two clicks at the same moment must both land."""
    import subprocess
    import sys
    d = project(tmp_path, FILM)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {**os.environ, "PYTHONPATH": root, "PYTHONIOENCODING": "utf-8"}
    ids = [f"S09-{n:02d}" for n in range(1, 9)]
    procs = [subprocess.Popen([sys.executable, "-m", "filmcrafter_engine.stylebible", "set_shot", d, "--data", json.dumps({"shot": sid, "style": "anime"})],
                              cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for sid in ids]
    outs = [p.communicate(timeout=120) for p in procs]
    assert all(p.returncode == 0 for p in procs), outs
    assert all(json.loads(o[0].strip().splitlines()[-1])["event"] == "result" for o in outs)
    assert saved_look(d)["shots"] == {sid: "anime" for sid in ids}


# ---------------------------------------------------------------- a look of its own is applied to the characters too (the references show them in the film's look)

def restyle_request(look, refs=None, shot_id="S06-02", scene=6, performers=("Sarah",)):
    man = R._finish("fal", "t/img", "Img", "image-to-image", [field("prompt", required=True), {**field("image_urls"), "type": "array", "items": "string"}])
    sh = {"id": shot_id, "scene": scene, "number": 1, "start": 0.0, "end": 2.0, "beats": ["A girl draws on a bench."], "performers": list(performers), "framing": "medium", "camera_moves": [], "source_shots": [shot_id]}
    plan = {"meta": {}, "characters": [{"name": "Sarah", "appearance": "A girl with braids in a bun, green shirt, denim overalls"}], "scenes": [{"number": scene, "heading": "EXT.", "shots": [sh]}]}
    refs = refs if refs is not None else [{"label": "reference for Sarah (face, expressions, full-body turnaround)", "url": "u1"}, {"label": "set and props sheet (locations, props, colour palette)", "url": "u2"}]
    return R.compile_request(sh, {"number": scene}, plan, {"look": look, "aspect_ratio": "16:9"}, man, refs)["prompt"]


FILM_3D = {"style": "feature-3d"}


@pytest.mark.regression
def test_a_shot_in_a_look_of_its_own_restyles_the_characters_too_not_only_the_set():
    """Low-poly was applied to the tree and not to the girl: the prompt told the model to keep her skin, face, hair and clothes identical to the references, which are in the film's look."""
    p = restyle_request({**FILM_3D, "shots": {"S06-02": "low-poly"}})
    assert "keep who they are (face shape, features, hair design, build, skin tone, outfit design)" in p and "draw them entirely in this look" in p
    assert "Whole-picture style, no exceptions" in p and "the characters' bodies, faces, hair and clothes included" in p
    assert "Take only each character's identity from them" in p and "not their rendering style" in p
    assert "THE SHOT IS WRONG" in p and "not their lighting, colour grade, depth of field, framing or rendering" in p
    assert "(take what it shows, not how it is drawn)" in p
    assert "identical skin tone, face, hair and clothes" not in p and "Match the characters' faces, hair and wardrobe exactly" not in p
    assert "the characters drawn in a different style from the rest of the picture" in p


def test_a_scene_in_a_look_of_its_own_is_restyled_the_same_way():
    p = restyle_request({**FILM_3D, "scenes": {"6": "low-poly"}})
    assert "Whole-picture style, no exceptions" in p and "identical skin tone" not in p


def test_a_shot_in_the_films_own_look_is_written_exactly_as_before():
    for look in (FILM_3D, {**FILM_3D, "shots": {"S09-09": "low-poly"}}, {**FILM_3D, "shots": {"S06-02": "no-such-look"}}):
        p = restyle_request(look)
        assert "identical skin tone, face, hair and clothes" in p and "Match the characters' faces, hair and wardrobe exactly" in p
        assert "Whole-picture style" not in p and "take what it shows" not in p and "keep who they are" not in p


def test_keeping_the_cast_changes_only_the_world():
    p = restyle_request({**FILM_3D, "shots": {"S06-02": "low-poly"}, "keep_cast": {"S06-02": True}})
    assert "Only the setting is in this look" in p and "the characters keep their own rendering from the reference pictures" in p
    assert "identical skin tone, face, hair and clothes" in p and "Whole-picture style" not in p and "take what it shows" not in p
    other = restyle_request({**FILM_3D, "shots": {"S06-02": "low-poly"}, "keep_cast": {"S01-01": True}})
    assert "Whole-picture style, no exceptions" in other                                  # another shot's choice does not apply here


def test_the_shot_before_is_used_fully_when_it_is_in_the_same_look_and_only_for_layout_when_it_is_not():
    prev = lambda look: [{"label": "reference for Sarah (face)", "url": "u1"}, {"label": "the previous shot of this scene (match its set and light)", "url": "u3", "kind": "continuity", "look": look}]
    look = {**FILM_3D, "shots": {"S06-02": "low-poly"}}
    same = restyle_request(look, prev("low-poly"))
    other = restyle_request(look, prev("feature-3d"))
    assert "match its set and light) (use only its set layout" not in same and "the previous shot of this scene (match its set and light)" in same
    assert "(use only its set layout and light; redraw everything in the new look)" in other


def test_the_wording_leaves_the_prompt_budget_alone(tmp_path):
    p = restyle_request({**FILM_3D, "shots": {"S06-02": "low-poly"}})
    assert len(p) < len(restyle_request(FILM_3D)) + 900                                   # a few sentences, not a rewrite


# ---------------------------------------------------------------- keep the cast: set, read, clear

def test_keeping_the_cast_is_a_setting_per_shot_that_is_saved_read_and_cleared(tmp_path):
    d = project(tmp_path, {**FILM, "shots": {"S06-02": "anime"}})
    r = SB.set_keep_cast(d, "S06-02", True)
    assert r["keep_cast"] == {"S06-02": True} and saved_look(d)["keep_cast"] == {"S06-02": True} and saved_look(d)["shots"] == {"S06-02": "anime"}
    assert SB.set_keep_cast(d, "S06-02", False)["keep_cast"] == {} and "keep_cast" not in saved_look(d)
    SB.set_keep_cast(d, "S06-03", True)
    assert SB.set_keep_cast(d, "S06-03", "yes")["keep_cast"] == {}                         # only a real true keeps it


@pytest.mark.security
def test_keeping_the_cast_refuses_bad_ids_and_folders_and_never_renders(tmp_path, monkeypatch):
    d = project(tmp_path, FILM)
    before = open(d + "/project.json", "rb").read()
    monkeypatch.setattr(R, "enqueue", lambda *a, **k: pytest.fail("a setting must never queue a render"))
    for bad in ("../x", "", None, 7, "a b"):
        with pytest.raises(SystemExit):
            SB.set_keep_cast(d, bad, True)
    empty = tmp_path / "nothing"
    empty.mkdir()
    with pytest.raises(SystemExit):
        SB.set_keep_cast(str(empty), "S01-01", True)
    assert open(d + "/project.json", "rb").read() == before and os.listdir(empty) == []


def test_the_command_line_sets_keep_cast(tmp_path, capsys):
    d = project(tmp_path, FILM)
    assert SB.main(["set_shot_options", d, "--data", json.dumps({"shot": "S06-02", "keep_cast": True})]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["keep_cast"] == {"S06-02": True}
