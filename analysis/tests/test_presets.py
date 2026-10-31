"""Creative presets: a stack of named settings that is previewed before it is applied, never overwrites what the person chose, can be undone, saved, shared and checked.
Free and local: no provider is called and nothing is regenerated."""
import json
import os

import pytest

from filmcrafter_engine import bible, grading, performance, presets as P, story
from tests.test_performance_director import film  # noqa: F401  (a small film with a render project)


def keys(plan):
    return {c["key"]: c["status"] for c in plan["changes"]}


# ---------------------------------------------------------------- the built-in presets

def test_every_built_in_preset_is_valid_and_its_includes_and_thumbnails_exist():
    b = P.builtin()
    assert len(b) == 35 and sum(1 for p in b.values() if p["type"] == "production") == 17
    for pid, p in b.items():
        assert P.clean_preset(p, set(b))["settings"] == p["settings"], pid
        if p["thumbnail"]:
            assert os.path.isfile(os.path.join(os.path.dirname(__file__), "..", "..", "public", p["thumbnail"])), pid
    for p in b.values():
        for inc in p["includes"]:
            assert b[inc]["type"] != "production"                                    # a production preset stacks layer presets, never another production one


def test_the_pack_s_eighteen_presets_are_all_here_by_their_own_ids():
    b = P.builtin()
    ids = ["vertical_micro_drama", "tiktok_story_short", "youtube_shorts", "instagram_reels", "animated_short", "historical_explainer", "commercial_product", "documentary", "romantic_micro_drama",
           "mystery_micro_drama", "fantasy_micro_drama", "animated_micro_drama", "hook_reveal", "mini_story", "educational_quick", "cinematic_teaser", "inspirational_short", "storybook_2_5d_style"]
    assert all(i in b for i in ids) and b["vertical_micro_drama"]["settings"] == {"aspect": "9:16", "duration_hint_s": 90}


def test_a_stack_lays_included_presets_first_and_a_later_preset_beats_an_earlier_one():
    b = P.builtin()
    assert P.expand(b, ["vertical_micro_drama"]) == ["restrained_emotional_acting", "suspenseful_character_drama", "muted_cinematic_contrast", "vertical_social_9_16", "vertical_micro_drama"]
    r = P.resolve(b, ["vertical_micro_drama", "expressive_animation_acting"])
    assert r["acting"] == {"value": "expressive", "by": "expressive_animation_acting"} and r["delivery"]["by"] == "vertical_social_9_16"
    r2 = P.resolve(b, ["expressive_animation_acting", "vertical_micro_drama"])
    assert r2["acting"]["by"] == "restrained_emotional_acting"                    # the included preset came later in the stack here, so it wins


def test_a_preset_that_includes_itself_or_goes_too_deep_or_is_missing_is_refused():
    b = {"a": {"includes": ["a"], "settings": {}}, "x1": {"includes": ["x2"]}, "x2": {"includes": ["x3"]}, "x3": {"includes": ["x4"]}, "x4": {"includes": ["x5"]}, "x5": {"includes": []}}
    for ids, why in ((["a"], "include itself"), (["x1"], "too deeply"), (["nothing"], "not here")):
        with pytest.raises(SystemExit, match=why):
            P.expand(b, ids)


# ---------------------------------------------------------------- previewing and applying

def test_the_preview_says_what_is_new_and_changes_nothing(film):
    f, rd = film
    before = open(os.path.join(rd, "project.json"), "rb").read()
    pl = P.plan(rd, ["animated_micro_drama"])
    assert keys(pl) == {"look": "new", "acting": "new", "editing": "new", "delivery": "new", "aspect": "new", "duration_hint_s": "new"}
    assert any("Nothing is regenerated" in n for n in pl["notes"]) and any("separate export" in n for n in pl["notes"])
    assert open(os.path.join(rd, "project.json"), "rb").read() == before and not os.path.exists(P._path(rd))


def test_applying_sets_what_the_stack_asks_for_and_nothing_else_and_calls_no_provider(film, monkeypatch):
    f, rd = film
    import requests
    for fn in ("get", "post", "put", "request"):
        monkeypatch.setattr(requests, fn, lambda *a, **k: (_ for _ in ()).throw(AssertionError("a provider was called")))
    jobs_before = open(os.path.join(rd, "jobs.json"), "rb").read() if os.path.exists(os.path.join(rd, "jobs.json")) else None
    out = P.apply(rd, ["vertical_micro_drama", "storybook_2_5d_style"])
    assert sorted(out["changed"]) == ["acting", "aspect", "delivery", "duration_hint_s", "editing", "grade", "look"] and out["kept"] == []
    assert bible.effective_look(bible.load(f)) == "cinematic-storybook-25d"
    assert performance.settings(json.load(open(os.path.join(rd, "project.json"))))["default"] == "restrained"
    assert grading.load(rd)["grades"]["film"]["contrast"] == 0.15
    assert story._manifest(f)["aspect_ratio"] == "9:16"
    st = P.load_state(rd)
    assert st["editing"] == "restrained_drama" and st["delivery"]["export"] == "vertical" and st["duration_hint_s"] == 90 and st["stack"] == ["vertical_micro_drama", "storybook_2_5d_style"]
    assert json.load(open(os.path.join(rd, "project.json")))["look"]["style"] == "cinematic-storybook-25d"          # the render project follows
    assert (open(os.path.join(rd, "jobs.json"), "rb").read() if os.path.exists(os.path.join(rd, "jobs.json")) else None) == jobs_before


def test_a_choice_you_already_made_is_kept_unless_you_say_otherwise(film):
    f, rd = film
    bible.update_rules(f, {"style": {"look": "claymation"}})
    grading.set_grade(rd, "film", None, {"exposure": 0.3})
    pl = P.plan(rd, ["vertical_micro_drama", "storybook_2_5d_style"])
    k = keys(pl)
    assert k["look"] == "yours" and k["grade"] == "yours" and k["acting"] == "new"
    out = P.apply(rd, ["vertical_micro_drama", "storybook_2_5d_style"])
    assert sorted(out["kept"]) == ["grade", "look"]
    assert bible.effective_look(bible.load(f)) == "claymation" and grading.load(rd)["grades"]["film"] == {"exposure": 0.3}
    again = P.apply(rd, ["vertical_micro_drama", "storybook_2_5d_style"], replace=["look"])
    assert "look" in again["changed"] and "grade" not in again["changed"]
    assert bible.effective_look(bible.load(f)) == "cinematic-storybook-25d" and grading.load(rd)["grades"]["film"] == {"exposure": 0.3}


def test_once_pictures_exist_the_frame_shape_is_yours_and_is_not_changed_without_asking(film):
    f, rd = film
    json.dump({"jobs": [{"id": "j1", "state": "ready", "shot_id": "S01-01", "plan": "production", "output": "x.mp4"}]}, open(os.path.join(rd, "jobs.json"), "w"))
    assert keys(P.plan(rd, ["vertical_micro_drama"]))["aspect"] == "yours"
    assert "aspect" not in P.apply(rd, ["vertical_micro_drama"])["changed"] and story._manifest(f)["aspect_ratio"] == "16:9"
    pl = P.plan(rd, ["vertical_micro_drama"], ["aspect"])
    assert any("the ones you have stay as they are" in n for n in pl["notes"])


def test_the_same_stack_applied_twice_changes_nothing_the_second_time(film):
    f, rd = film
    P.apply(rd, ["tiktok_story_short"])
    out = P.apply(rd, ["tiktok_story_short"])
    assert out["changed"] == [] and "delivery" in out["same"]


# ---------------------------------------------------------------- undo

def test_undo_puts_back_what_the_application_changed(film):
    f, rd = film
    P.apply(rd, ["vertical_micro_drama", "storybook_2_5d_style"])
    out = P.undo(rd)
    assert out["kept_as_changed_since"] == [] and "look" in out["restored"]
    assert bible.effective_look(bible.load(f)) in ("auto", "", None) or bible.effective_look(bible.load(f)) != "cinematic-storybook-25d"
    assert grading.load(rd)["grades"]["film"] == {} and story._manifest(f)["aspect_ratio"] == "16:9"
    st = P.load_state(rd)
    assert st["editing"] is None and st["delivery"] is None and st["applied"] == []
    with pytest.raises(SystemExit, match="nothing to undo"):
        P.undo(rd)


def test_undo_leaves_alone_anything_you_changed_since(film):
    f, rd = film
    P.apply(rd, ["vertical_micro_drama"])
    grading.set_grade(rd, "film", None, {"exposure": 0.9})                           # you changed the grade after the preset put its own there
    out = P.undo(rd)
    assert "grade" in out["kept_as_changed_since"] and grading.load(rd)["grades"]["film"] == {"exposure": 0.9}
    assert "acting" in out["restored"]


# ---------------------------------------------------------------- your own, favourites, files

def test_you_can_keep_your_own_preset_from_the_choices_the_film_has_made(film):
    f, rd = film
    with pytest.raises(SystemExit, match="nothing chosen"):
        P.save_mine(rd, "Empty")
    P.apply(rd, ["mystery_micro_drama"])
    out = P.save_mine(rd, "My mystery look")
    pid = out["saved"]
    mine = next(p for p in out["catalog"]["presets"] if p["id"] == pid)
    assert pid == "mine-my-mystery-look" and mine["mine"] and mine["type"] == "custom" and mine["settings"]["acting"] == "restrained" and "aspect" not in mine["settings"]
    assert P.save_mine(rd, "My mystery look")["saved"] == "mine-my-mystery-look-2"
    assert P.delete_mine(rd, pid)["presets"] and pid not in [p["id"] for p in P.catalog(rd)["presets"]]
    with pytest.raises(SystemExit, match="not one of your own"):
        P.delete_mine(rd, "vertical_micro_drama")


def test_favourites_and_recent_follow_what_you_do(film):
    f, rd = film
    c = P.favorite(rd, "documentary", True)
    assert next(p for p in c["presets"] if p["id"] == "documentary")["favorite"] is True
    assert not next(p for p in P.favorite(rd, "documentary", False)["presets"] if p["id"] == "documentary")["favorite"]
    with pytest.raises(SystemExit, match="not here"):
        P.favorite(rd, "nope", True)
    P.apply(rd, ["hook_reveal"])
    assert next(p for p in P.catalog(rd)["presets"] if p["id"] == "hook_reveal")["recent"] is True


def test_a_preset_goes_out_as_a_file_and_comes_back_in_as_the_same_settings_and_never_carries_a_path(film, tmp_path):
    f, rd = film
    out = P.export_preset(rd, "vertical_micro_drama", str(tmp_path / "vmd.json"))
    data = json.load(open(out["path"]))
    assert data["format"] == "filmcrafter.preset" and data["preset"]["includes"] == [] and data["preset"]["settings"]["delivery"]["export"] == "vertical" and data["preset"]["settings"]["acting"] == "restrained"
    assert str(tmp_path) not in json.dumps(data)
    back = P.import_file(rd, out["path"])
    mine = next(p for p in back["catalog"]["presets"] if p["id"] == back["imported"])
    assert mine["mine"] and mine["settings"] == data["preset"]["settings"]
    assert P.import_file(rd, out["path"])["imported"] != back["imported"]                      # importing twice makes two, never overwrites
    with pytest.raises(SystemExit, match="Choose a .json file"):
        P.export_preset(rd, "vertical_micro_drama", str(tmp_path / "x.txt"))


def test_a_file_that_is_not_a_good_preset_is_refused_with_a_reason_and_changes_nothing(film, tmp_path):
    f, rd = film
    def write(name, text):
        (tmp_path / name).write_text(text, encoding="utf-8")
        return str(tmp_path / name)
    good = {"format": "filmcrafter.preset", "schema": 1, "preset": {"name": "x", "settings": {"look": "claymation"}}}
    bad = {"not json": "{ nope", "wrong format": json.dumps({"format": "other"}), "newer": json.dumps({**good, "schema": 9}), "unknown look": json.dumps({**good, "preset": {"name": "x", "settings": {"look": "no-such-look"}}}),
           "bad acting": json.dumps({**good, "preset": {"name": "x", "settings": {"acting": "wild"}}}), "bad aspect": json.dumps({**good, "preset": {"name": "x", "settings": {"aspect": "7:3"}}}),
           "bad delivery": json.dumps({**good, "preset": {"name": "x", "settings": {"delivery": {"export": "../../x"}}}}), "empty": json.dumps({**good, "preset": {"name": "x", "settings": {}}}),
           "unbuilt editing": json.dumps({**good, "preset": {"name": "x", "settings": {"editing": "suspense"}}}), "huge": " " * 70000}
    why = {"not json": "not a preset file", "wrong format": "not a FilmCrafter preset", "newer": "newer FilmCrafter", "unknown look": "not one of FilmCrafter's looks", "bad acting": "acting profile",
           "bad aspect": "frame shape", "bad delivery": "delivery version", "empty": "sets nothing", "unbuilt editing": "not built yet", "huge": "too large"}
    for name, text in bad.items():
        with pytest.raises(SystemExit, match=why[name]):
            P.import_file(rd, write(name.replace(" ", "_") + ".json", text))
    with pytest.raises(SystemExit, match="Choose a preset file"):
        P.import_file(rd, str(tmp_path / "missing.json"))
    assert P.load_state(rd)["mine"] == {}
    assert P.import_file(rd, write("good.json", json.dumps(good)))["imported"] == "mine-x"


def test_a_preset_cannot_carry_a_lut_or_run_anything(film):
    f, rd = film
    s = P.clean_settings({"grade": {"exposure": 0.2, "lut": {"id": "0123456789abcdef", "intensity": 1}, "off": True}, "unknown": "rm -rf", "look": "claymation"})
    assert s == {"grade": {"exposure": 0.2}, "look": "claymation"}


# ---------------------------------------------------------------- a project that is not a film, the record, the door

def test_a_project_that_is_not_a_film_says_a_look_is_not_available_rather_than_failing(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    json.dump({"title": "T"}, open(d / "project.json", "w"))
    pl = P.plan(str(d), ["storybook_2_5d_style", "restrained_emotional_acting"])
    assert keys(pl) == {"look": "unavailable", "acting": "new"}
    assert P.apply(str(d), ["storybook_2_5d_style", "restrained_emotional_acting"])["changed"] == ["acting"]


def test_a_record_from_a_newer_version_is_refused_and_a_damaged_preset_of_yours_is_skipped(film):
    f, rd = film
    os.makedirs(P.root(rd), exist_ok=True)
    json.dump({"schema": 9, "mine": {}}, open(P._path(rd), "w"))
    for call in (lambda: P.catalog(rd), lambda: P.apply(rd, ["hook_reveal"]), lambda: P.favorite(rd, "documentary", True)):
        with pytest.raises(SystemExit, match="newer FilmCrafter"):
            call()
    json.dump({"schema": 1, "mine": {"mine-ok": {"id": "mine-ok", "type": "custom", "name": "Fine", "settings": {"look": "claymation"}}, "mine-bad": {"id": "mine-bad", "type": "custom", "name": "Bad", "settings": {"look": "zzz"}}}},
              open(P._path(rd), "w"))
    assert list(P.load_state(rd)["mine"]) == ["mine-ok"]


def test_the_door_speaks_json_and_its_action_list_is_the_one_the_shell_must_match(film, capsys):
    f, rd = film
    assert P.main(["catalog", rd]) == 0 and len(json.loads(capsys.readouterr().out.splitlines()[-1])["data"]["presets"]) == 35
    assert P.main(["plan", rd, "--data", json.dumps({"stack": ["nope"]})]) == 1 and "not here" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="Unknown"):
        P.run(rd, "explode", {})
    src = open(P.__file__, encoding="utf-8").read()
    for a in P.ACTIONS:
        assert f'"{a}"' in src.split("choices=")[1].split("]")[0]
