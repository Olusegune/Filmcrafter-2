"""The prompt for a start-and-end-frame shot: the checker, the recipes, the writer (with and without an AI brain), what the render really sends, and where it is kept."""
import json
import os

import pytest
from PIL import Image

from pulseframe_analysis import compose as CO, promptwriter as P, render as R

LITTLE_OLD = ("little sege hugging older sege, and then there is bright light in older sege's chest and little sege disappears")


def kinds(issues):
    return [i["level"] for i in issues]


def has(issues, needle):
    return any(needle in i["text"] for i in issues)


# ---------------------------------------------------------------- the checker

def test_an_empty_prompt_is_a_problem_and_a_very_short_one_a_warning():
    assert kinds(P.lint("")) == ["problem"] and has(P.lint("   "), "Nothing written yet")
    assert has(P.lint("A man."), "Very short")


def test_a_prompt_with_no_change_in_it_is_told_to_describe_what_happens():
    assert has(P.lint("A man in a grey coat on a rainy street at night, cinematic."), "not what happens")
    assert not has(P.lint("The man walks into the rain and turns to look back."), "not what happens")


def test_a_prompt_over_the_models_limit_is_a_problem_and_near_it_a_warning():
    t = "The man walks into the rain. " * 10
    n = len(t.strip().encode("utf-8"))
    assert kinds(P.lint(t, {"limit": 100}))[0] == "problem" and has(P.lint(t, {"limit": 100}), f"{n} characters; this model takes 100")
    assert has(P.lint(t, {"limit": n + 5}), "very close")
    assert not has(P.lint(t, {"limit": 3000}), "characters")


def test_cuts_are_refused_negations_and_quotes_are_flagged():
    assert has(P.lint("She walks in. Cut to the street where he waits.", {}), "cannot cut")
    assert has(P.lint("No hands, no text, never blurry, nothing moves but her eyes.", {}), "NOT to do")
    assert has(P.lint('He says "I am here" and walks away.', {}), "written text")
    assert not has(P.lint('He says "I am here" and walks away.', {"speech": True}), "written text")


def test_too_many_events_for_the_seconds_is_said():
    busy = "He stands. Then he walks. Then he turns. Then he runs. Then he jumps. Then he falls. Then he rises."
    assert has(P.lint(busy, {"seconds": 3}), "in 3 seconds")
    assert not has(P.lint("He walks slowly to the window and looks out.", {"seconds": 5}), "in 5 seconds")


def test_something_that_vanishes_should_go_somewhere():
    assert has(P.lint("The little boy disappears from the room."), "where it goes")
    assert not has(P.lint("The little boy dissolves into the light."), "where it goes")


def test_the_end_pictures_description_should_be_reflected_in_the_words():
    ctx = {"has_end": True, "end_state": "older Sege standing alone, calm, light gone"}
    assert has(P.lint("The boy hugs the man and then runs away quickly.", ctx), "isn't reflected")
    assert not has(P.lint("The boy hugs older Sege, who is left standing alone and calm.", ctx), "isn't reflected")


def test_a_good_prompt_is_told_so_and_problems_sort_first():
    assert P.lint("The man walks slowly to the window and looks out.", {"seconds": 5})[0]["level"] == "tip"
    out = P.lint("No no no. Cut to a wide shot.", {})
    assert out == sorted(out, key=lambda i: {"problem": 0, "warn": 1, "tip": 2}[i["level"]])


# ---------------------------------------------------------------- the recipes and the template writer

def test_the_recipes_use_the_shots_people_and_generic_words_when_it_names_fewer():
    r = {x["id"]: x for x in P.recipes({"performers": ["Little Sege", "Older Sege"]})}
    assert "Little Sege dissolves into the light" in r["absorb"]["text"] and "{A}" not in r["absorb"]["text"]
    assert "the first person" in P.recipes({"performers": []})[0]["text"] and "the other person" in P.recipes({"performers": ["Sege"]})[0]["text"]
    assert {"absorb", "age", "dissolve", "match"} <= set(r) and all(x["title"] and x["blurb"] for x in r.values())


def test_every_recipe_passes_its_own_checker():
    for r in P.recipes({"performers": ["Amara", "Sege"]}):
        bad = [i for i in P.lint(r["text"], {"seconds": 6, "limit": 1500}) if i["level"] == "problem"]
        assert not bad, (r["id"], bad)


def test_the_users_example_is_recognised_as_dissolving_into_light():
    assert P.recipe_for(LITTLE_OLD) == "absorb"
    assert P.recipe_for("she becomes an old woman as the years pass") == "age"
    assert P.recipe_for("the dancer turns to ash and drifts away") == "dissolve"
    assert P.recipe_for("a man walks to a door") is None


def test_the_template_turns_the_example_into_a_clear_ordered_prompt():
    ctx = {"performers": ["Little Sege", "Older Sege"], "seconds": 6, "end_state": "", "has_end": True}
    t = P.template(LITTLE_OLD, ctx)
    assert "Little Sege dissolves into the light" in t["prompt"] and "drawn gently into Older Sege's chest" in t["prompt"] and "like" in t["why"]
    assert not [i for i in P.lint(t["prompt"], ctx) if i["level"] == "problem"]


def test_the_template_puts_plain_words_in_order_and_ends_on_the_end_picture():
    t = P.template("a man walks to the door and opens it and looks out", {"performers": ["Sege"], "end_state": "he stands in the doorway, backlit"})
    s = t["prompt"]
    assert s.startswith("A man walks to the door.") and "Then opens it." in s and "ends with he stands in the doorway, backlit." in s and s.rstrip().endswith("last.")


# ---------------------------------------------------------------- the writer with and without a brain

@pytest.fixture
def project(tmp_path):
    d = tmp_path / "p"
    (d / "media").mkdir(parents=True)
    shot = {"id": "S01-01", "scene": 1, "number": 1, "start": 0.0, "end": 6.0, "beats": ["The boy hugs the man."], "performers": ["Little Sege", "Older Sege"], "framing": "medium",
            "camera_moves": [], "source_shots": [], "emotion": "grief and release", "visual_prompt": "Two figures embrace in a bare room."}
    (d / "production.json").write_text(json.dumps({"meta": {}, "characters": [], "scenes": [{"number": 1, "heading": "INT. ROOM - NIGHT", "start": 0, "end": 6, "notes": {}, "shots": [shot]}]}))
    (d / "project.json").write_text(json.dumps({"title": "T", "song": "s.wav", "aspect_ratio": "16:9"}))
    (d / "songmap.json").write_text(json.dumps({"duration": 6.0, "lyrics": [], "sections": [], "beats": []}))
    Image.new("RGB", (64, 36), (9, 9, 9)).save(d / "media" / "kf.png")
    (d / "keyframes.json").write_text(json.dumps({"production": {"S01-01": "project:media/kf.png"}}))
    (d / "jobs.json").write_text(json.dumps({"jobs": []}))
    return str(d)


def test_the_context_has_the_people_the_seconds_and_what_the_pictures_are(project):
    c = P.context(project, "S01-01")
    assert c["performers"] == ["Little Sege", "Older Sege"] and c["seconds"] == 6.0 and c["has_start"] and not c["has_end"] and c["emotion"] == "grief and release"


def test_without_a_brain_the_writer_still_helps_and_says_so(project, monkeypatch):
    monkeypatch.setattr("pulseframe_analysis.director._client", lambda: (_ for _ in ()).throw(SystemExit("Add your OpenAI key in Settings")))
    w = P.write(project, "S01-01", LITTLE_OLD)
    assert w["source"] == "template" and "Little Sege dissolves into the light" in w["prompt"] and isinstance(w["issues"], list)


def test_with_a_brain_its_words_are_used_and_checked(project, monkeypatch):
    seen = {}

    class Resp:
        output_text = json.dumps({"prompt": "Little Sege and Older Sege embrace. Light blooms in Older Sege's chest and Little Sege dissolves into it.", "why": "A farewell by absorption.", "tips": ["Make the shot 6 s or longer."]})

    class Client:
        class responses:
            @staticmethod
            def create(model, input, text):
                seen["system"], seen["brief"] = input[0]["content"], json.loads(input[1]["content"])
                return Resp
    monkeypatch.setattr("pulseframe_analysis.director._client", lambda: Client)
    monkeypatch.setattr("pulseframe_analysis.director.resolve_model", lambda c, m: "test-model")
    w = P.write(project, "S01-01", LITTLE_OLD, 900)
    assert w["source"] == "ai" and w["prompt"].startswith("Little Sege and Older Sege embrace.") and w["tips"] == ["Make the shot 6 s or longer."]
    assert seen["brief"]["seconds"] == 6.0 and seen["brief"]["character_limit"] == 900 and seen["brief"]["characters_in_the_shot"] == ["Little Sege", "Older Sege"]
    assert "HAPPENS between them" in seen["system"] and "no cuts" in seen["system"]


def test_a_broken_brain_answer_falls_back_to_the_template(project, monkeypatch):
    class Client:
        class responses:
            @staticmethod
            def create(model, input, text):
                class R_:
                    output_text = "not json"
                return R_
    monkeypatch.setattr("pulseframe_analysis.director._client", lambda: Client)
    monkeypatch.setattr("pulseframe_analysis.director.resolve_model", lambda c, m: "m")
    assert P.write(project, "S01-01", LITTLE_OLD)["source"] == "template"


def test_the_writer_never_goes_over_the_models_limit_and_needs_some_words(project, monkeypatch):
    monkeypatch.setattr("pulseframe_analysis.director._client", lambda: (_ for _ in ()).throw(SystemExit("no key")))
    w = P.write(project, "S01-01", LITTLE_OLD, 120)
    assert len(w["prompt"].encode("utf-8")) <= 120 and w["prompt"].endswith(".")
    with pytest.raises(SystemExit) as e:
        P.write(project, "S01-01", "   ")
    assert "Describe in your own words" in str(e.value)


# ---------------------------------------------------------------- kept per shot, and what the render sends

def test_the_prompt_choice_is_kept_per_shot_and_comes_back_with_the_state(project):
    assert CO.prompt_get(project, "S01-01") == {"mode": "auto", "text": "", "only": False}
    assert CO.prompt_set(project, "S01-01", {"mode": "mine", "text": "Little Sege dissolves into light.", "only": True}) == {"mode": "mine", "text": "Little Sege dissolves into light.", "only": True}
    assert CO.state(project, "S01-01")["prompt"]["text"].startswith("Little Sege")
    assert CO.prompt_set(project, "S01-01", {"mode": "auto"})["mode"] == "auto"
    assert CO.prompt_set(project, "S01-01", {"text": "x" * 9000})["text"] == "x" * 4000
    with pytest.raises(SystemExit):
        CO.prompt_set(project, "S01-01", {"mode": "both"})
    with pytest.raises(SystemExit):
        CO.prompt_set(project, "S09-09", {"mode": "mine"})


def test_mine_with_no_words_is_the_same_as_auto(project):
    assert CO.prompt_set(project, "S01-01", {"mode": "mine", "text": "   "})["mode"] == "auto"


def video_man():
    F = lambda name, type="string", **kw: {"name": name, "type": type, "items": None, "enum": kw.get("enum"), "default": None, "minimum": None, "maximum": None, "max_items": None,
                                           "max_length": kw.get("max_length"), "description": kw.get("description", ""), "required": kw.get("required", False)}
    return R._finish("kie", "bytedance/seedance-2", "Seedance 2.0", "", [F("prompt", required=True, max_length=20000), F("first_frame_url"), F("last_frame_url"), F("duration", "integer")])


def build(project, **shot_extra):
    from pulseframe_analysis.planio import find_shot, load_plan
    _, plan = load_plan(project)
    sh, sc = find_shot(plan, "S01-01")
    sh = {**sh, "acting_beats": "ACTING-BEATS-TEXT", "arc_text": "ARC-TEXT", "continuity": "CONTINUITY-TEXT", "lighting": "warm lamp", "environment": "a bare room", "wardrobe": "grey coat",
          "choreography": "CHOREO-TEXT", **shot_extra}
    return R.compile_request(sh, sc, plan, {"title": "T", "aspect_ratio": "16:9"}, video_man(), [], None)["prompt"]


def test_your_words_replace_what_the_shot_does_and_its_competing_acting(project):
    auto = build(project)
    assert "Two figures embrace in a bare room." in auto and "ACTING-BEATS-TEXT" in auto and "CHOREO-TEXT" in auto
    mine = build(project, custom_prompt="Little Sege dissolves into the light.")
    assert mine.startswith("Little Sege dissolves into the light.")
    assert "Two figures embrace in a bare room." not in mine and "ACTING-BEATS-TEXT" not in mine and "ARC-TEXT" not in mine and "CHOREO-TEXT" not in mine
    assert "Characters: Little Sege" in mine and "Camera:" in mine and "Setting: a bare room" in mine and "Lighting: warm lamp" in mine and "Look:" in mine and "CONTINUITY-TEXT" in mine


def test_only_my_words_also_leaves_out_camera_set_light_wardrobe_and_characters(project):
    t = build(project, custom_prompt="Little Sege dissolves into the light.", prompt_only=True)
    assert t.startswith("Little Sege dissolves into the light.")
    for gone in ("Camera:", "Setting:", "Lighting:", "Wardrobe:", "Characters:", "CONTINUITY-TEXT"):
        assert gone not in t, gone
    assert "Look:" in t and "No on-screen text" in t                      # the look, the style lock and the no-text rule always stay


def test_the_custom_prompt_is_for_video_only_and_a_still_ignores_it(project):
    from pulseframe_analysis.planio import find_shot, load_plan
    _, plan = load_plan(project)
    sh, sc = find_shot(plan, "S01-01")
    still = R._finish("kie", "google/nanobanana-2-1", "NB", "", [{"name": "prompt", "type": "string", "items": None, "enum": None, "default": None, "minimum": None, "maximum": None,
                                                                     "max_items": None, "max_length": None, "description": "", "required": True}])
    out = R.compile_request({**sh, "custom_prompt": "SOMETHING ELSE ENTIRELY"}, sc, plan, {"title": "T"}, still, [], None)["prompt"]
    assert "SOMETHING ELSE ENTIRELY" not in out and "Two figures embrace in a bare room." in out


class Fake:
    name = "kie"
    sent = []

    def upload(self, path):
        return "https://cdn/" + os.path.basename(path)

    def submit(self, model, payload):
        Fake.sent.append(payload)
        return {"id": "r1"}

    def poll(self, model, rid, meta=None):
        return {"state": "done", "url": "https://cdn/out.mp4"}


def test_the_words_travel_with_the_job_and_are_what_is_sent(project, monkeypatch):
    Fake.sent = []
    monkeypatch.setitem(R.PROVIDERS, "kie", Fake)
    monkeypatch.setattr(R, "manifest", lambda provider, model, refresh=False: video_man())
    monkeypatch.setattr(R, "_review", lambda d, store, j: None)

    class Dl:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_content(self, n): yield b"\0" * 8
    monkeypatch.setattr(R.requests, "get", lambda url, **kw: Dl())
    made = R.enqueue(project, ["S01-01"], "kie", "bytedance/seedance-2", {"_prompt": "  Little Sege dissolves into the light.  ", "_prompt_only": False}, [], "video")
    assert made[0]["custom_prompt"] == "Little Sege dissolves into the light." and made[0]["prompt_only"] is False
    R.run(project, poll_every=0)
    assert Fake.sent[0]["prompt"].startswith("Little Sege dissolves into the light.") and "Two figures embrace in a bare room." not in Fake.sent[0]["prompt"]
    assert "_prompt" not in made[0]["overrides"]


def test_the_preview_shows_exactly_the_words_that_would_be_sent(project, monkeypatch):
    monkeypatch.setattr(R, "manifest", lambda provider, model, refresh=False: video_man())
    p = CO.prompt_preview(project, "S01-01", "kie", "bytedance/seedance-2", {"mode": "mine", "text": "Little Sege dissolves into the light.", "only": True})
    assert p["prompt"].startswith("Little Sege dissolves into the light.") and "Camera:" not in p["prompt"] and p["chars"] == len(p["prompt"].encode()) and isinstance(p["left_out"], list)
    auto = CO.prompt_preview(project, "S01-01", "kie", "bytedance/seedance-2", {"mode": "auto"})
    assert "Two figures embrace in a bare room." in auto["prompt"]
    assert "Direction for this take: Slow." in CO.prompt_preview(project, "S01-01", "kie", "bytedance/seedance-2", {"mode": "auto", "note": "Slow"})["prompt"]
