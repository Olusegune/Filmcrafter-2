"""Retry a failed render on a cheaper model: when it is offered, what is offered, what is never offered, and that nothing is sent without the click (or the project's own setting)."""
import json
import os

import pytest

from pulseframe_analysis import frames as FR, render as R, retrycheap as RC, routing as RT


def row(label, provider, model, price, verified=True, sees=None, strength=""):
    return {"label": label, "provider": provider, "model": model, "price_usd": price, "verified": verified, "family": label.lower(), "strength": strength, "sees_references": sees}


VIDEO_MODELS = [row("Cheap", "fal", "fal/cheap", 0.2, strength="Low price."), row("Middle", "kie", "kie/middle", 0.5), row("Unproven", "fal", "fal/unproven", 0.1, verified=False),
                row("Unpriced", "kie", "kie/unpriced", None), row("Failed", "kie", "kie/failed", 1.0), row("Pricey", "fal", "fal/pricey", 2.0)]
IMAGE_MODELS = [row("Sees", "kie", "kie/sees", 0.03, sees=True), row("Blind", "kie", "kie/blind", 0.01, sees=False), row("Pricey", "kie", "kie/pricey", 0.3, sees=True)]


@pytest.fixture
def world(tmp_path, monkeypatch):
    d = tmp_path / "p"
    d.mkdir()
    (d / "project.json").write_text(json.dumps({"title": "T", "routing": {"mode": "balanced"}}))
    monkeypatch.setattr(RT, "models", lambda kind: VIDEO_MODELS if kind == "video" else IMAGE_MODELS)
    monkeypatch.setattr(RT, "shot_price", lambda p, m: {"kie/failed": 1.0, "kie/image-failed": 0.1}.get(m))
    monkeypatch.setattr(FR, "_plan", lambda dd: ("production", {"scenes": []}))
    monkeypatch.setattr(FR, "end_ref", lambda *a, **k: None)
    queued = []

    def enqueue(dd, shots, provider, model, overrides, notes, kind="video", source=None):
        made = [{"id": f"new{len(queued)}", "shot_id": s, "provider": provider, "model": model, "kind": kind, "state": "queued", "overrides": overrides, "fix_notes": notes,
                 "created": 1, "updated": 1} for s in shots]
        queued.extend(made)
        store = R.Store(dd)
        store.data["jobs"] += made
        store.save()
        return made

    monkeypatch.setattr(R, "enqueue", enqueue)
    monkeypatch.setattr(R, "emit", lambda **k: None)
    return {"dir": str(d), "queued": queued}


def put(world, **over):
    j = {"id": "j1", "shot_id": "S01-01", "plan": "production", "provider": "kie", "model": "kie/failed", "kind": "video", "state": "failed", "error_kind": "service",
         "error": "The provider had an internal error.", "overrides": {"x": 1}, "fix_notes": ["Keep the beard."], "created": 100, "updated": 200, **over}
    json.dump({"jobs": [j]}, open(os.path.join(world["dir"], "jobs.json"), "w"))
    return j


def turn_auto_on(world):
    p = json.load(open(os.path.join(world["dir"], "project.json")))
    p["routing"]["auto_retry"] = True
    json.dump(p, open(os.path.join(world["dir"], "project.json"), "w"))


# ---------------------------------------------------------------- what is offered

def test_a_failed_video_is_offered_the_proven_cheaper_models_cheapest_first(world):
    put(world)
    o = RC.options(world["dir"], "j1")
    assert o["can"] is True and o["original_usd"] == 1.0 and o["failed_model"] == "kie/failed"
    assert [(x["label"], x["price_usd"], x["cheaper"], x["saves_usd"]) for x in o["options"]] == [("Cheap", 0.2, True, 0.8), ("Middle", 0.5, True, 0.5)]
    assert o["options"][0]["strength"] == "Low price." and o["auto"] is False


def test_never_the_failed_model_an_unproven_one_an_unpriced_one_or_a_dearer_one(world):
    put(world)
    got = {x["model"] for x in RC.options(world["dir"], "j1")["options"]}
    assert got.isdisjoint({"kie/failed", "fal/unproven", "kie/unpriced", "fal/pricey"})


def test_at_most_three_are_offered(world, monkeypatch):
    monkeypatch.setattr(RT, "models", lambda kind: [row(f"M{i}", "fal", f"fal/m{i}", 0.1 + i * 0.1) for i in range(6)])
    put(world)
    assert len(RC.options(world["dir"], "j1")["options"]) == 3


@pytest.mark.parametrize("kind,part", [("policy", "content filter"), ("auth", "your account"), ("credits", "your account"), ("something_else", "isn't one")])
def test_some_failures_are_never_sent_to_another_model(world, kind, part):
    put(world, error_kind=kind)
    o = RC.options(world["dir"], "j1")
    assert o["can"] is False and part in o["reason"] and o["options"] == []


@pytest.mark.parametrize("kind", ["unavailable", "invalid", "missing_input", "service", "timeout", "rate_limit", "download"])
def test_these_failures_can_be_tried_elsewhere(world, kind):
    put(world, error_kind=kind)
    assert RC.options(world["dir"], "j1")["can"] is True


def test_a_render_that_may_be_running_or_billed_is_not_sent_anywhere_else(world):
    put(world, state="uncertain")
    assert "may already be running or billed" in RC.options(world["dir"], "j1")["reason"]


def test_only_failed_unretried_videos_and_pictures_qualify(world):
    for over, part in (({"state": "ready"}, "Only a failed"), ({"retried_as": "x"}, "already been retried"), ({"kind": "lipsync"}, "Only a video or a keyframe"), ({"kind": "asset"}, "Only a video or a keyframe")):
        put(world, **over)
        assert part in RC.options(world["dir"], "j1")["reason"], over


def test_an_unknown_job_says_so(world):
    put(world)
    with pytest.raises(SystemExit, match="no longer exists"):
        RC.options(world["dir"], "nope")


def test_when_the_failed_models_price_is_not_known_nothing_is_called_cheaper(world, monkeypatch):
    monkeypatch.setattr(RT, "shot_price", lambda p, m: None)
    put(world)
    o = RC.options(world["dir"], "j1")
    assert o["can"] is True and o["original_usd"] is None and all(x["cheaper"] is None and x["saves_usd"] is None for x in o["options"])


def test_a_shot_that_lands_on_an_end_frame_only_goes_to_models_that_take_one(world, monkeypatch):
    monkeypatch.setattr(FR, "end_ref", lambda *a, **k: "project:media/end.png")
    monkeypatch.setattr(FR, "model_for", lambda provider, model, wants: {"supports_end": model == "kie/middle"})
    put(world)
    assert [x["model"] for x in RC.options(world["dir"], "j1")["options"]] == ["kie/middle"]


def test_no_cheaper_model_says_why(world, monkeypatch):
    monkeypatch.setattr(RT, "models", lambda kind: [row("Pricey", "fal", "fal/pricey", 2.0)])
    put(world)
    o = RC.options(world["dir"], "j1")
    assert o["can"] is False and "No cheaper model" in o["reason"]


def test_pictures_skip_models_that_cannot_see_your_character_pictures_and_carry_the_one_model_warning(world):
    put(world, kind="image", model="kie/image-failed")
    o = RC.options(world["dir"], "j1")
    assert [x["model"] for x in o["options"]] == ["kie/sees"] and "one picture model" in o["options"][0]["warning"]


# ---------------------------------------------------------------- sending

def test_retry_queues_the_shot_on_the_chosen_model_and_marks_both_jobs(world):
    put(world)
    r = RC.retry(world["dir"], "j1", "fal", "fal/cheap")
    assert r["model"] == "fal/cheap" and r["price_usd"] == 0.2 and len(r["jobs"]) == 1
    (q,) = world["queued"]
    assert (q["shot_id"], q["provider"], q["model"], q["overrides"], q["fix_notes"]) == ("S01-01", "fal", "fal/cheap", {}, ["Keep the beard."])      # the old model's private settings do not follow
    jobs = {j["id"]: j for j in json.load(open(os.path.join(world["dir"], "jobs.json")))["jobs"]}
    assert jobs["j1"]["retried_as"] == "new0" and jobs["new0"]["retry_of"] == "j1" and "Retried on Cheap" in jobs["new0"]["retry_note"] and "auto_retried" not in jobs["new0"]


def test_only_a_model_that_was_offered_can_be_chosen(world):
    put(world)
    for provider, model in (("fal", "fal/pricey"), ("kie", "kie/failed"), ("fal", "fal/unproven"), ("evil", "../../x"), ("", "")):
        with pytest.raises(SystemExit, match="Choose one of the models offered"):
            RC.retry(world["dir"], "j1", provider, model)
    assert world["queued"] == []


def test_a_job_can_only_be_retried_once(world):
    put(world)
    RC.retry(world["dir"], "j1", "fal", "fal/cheap")
    with pytest.raises(SystemExit, match="already been retried"):
        RC.retry(world["dir"], "j1", "kie", "kie/middle")


def test_a_refusal_from_the_budget_or_the_mode_leaves_the_failed_job_alone(world, monkeypatch):
    put(world)
    def refuse(*a, **k):
        raise SystemExit("Over budget: nothing was sent.")
    monkeypatch.setattr(R, "enqueue", refuse)
    with pytest.raises(SystemExit, match="Over budget"):
        RC.retry(world["dir"], "j1", "fal", "fal/cheap")
    assert "retried_as" not in json.load(open(os.path.join(world["dir"], "jobs.json")))["jobs"][0]


# ---------------------------------------------------------------- by itself (off unless the project turns it on)

def test_nothing_happens_by_itself_unless_the_project_turned_it_on(world):
    put(world)
    store = R.Store(world["dir"])
    assert RC.after_failure(world["dir"], store, store.jobs[0]) is None and world["queued"] == []


def test_with_it_on_a_failed_video_goes_once_to_the_cheapest_model(world):
    turn_auto_on(world)
    put(world)
    store = R.Store(world["dir"])
    assert RC.after_failure(world["dir"], store, store.jobs[0]) == "Cheap"
    assert [q["model"] for q in world["queued"]] == ["fal/cheap"]
    jobs = {j["id"]: j for j in json.load(open(os.path.join(world["dir"], "jobs.json")))["jobs"]}
    assert jobs["new0"]["auto_retried"] is True
    assert RC.after_failure(world["dir"], R.Store(world["dir"]), jobs["j1"]) is None and len(world["queued"]) == 1       # not again


def test_by_itself_never_for_pictures_never_for_a_retry_and_never_when_nothing_is_known_to_be_cheaper(world, monkeypatch):
    turn_auto_on(world)
    for over in ({"kind": "image", "model": "kie/image-failed"}, {"retry_of": "j0"}):
        put(world, **over)
        store = R.Store(world["dir"])
        assert RC.after_failure(world["dir"], store, store.jobs[0]) is None
    monkeypatch.setattr(RT, "shot_price", lambda p, m: None)
    put(world)
    store = R.Store(world["dir"])
    assert RC.after_failure(world["dir"], store, store.jobs[0]) is None and world["queued"] == []


def test_by_itself_it_gives_up_quietly_when_the_budget_says_no(world, monkeypatch):
    turn_auto_on(world)
    put(world)
    def refuse(*a, **k):
        raise SystemExit("Over budget")
    monkeypatch.setattr(R, "enqueue", refuse)
    store = R.Store(world["dir"])
    assert RC.after_failure(world["dir"], store, store.jobs[0]) is None


def test_by_itself_never_for_a_content_filter_refusal(world):
    turn_auto_on(world)
    put(world, error_kind="policy")
    store = R.Store(world["dir"])
    assert RC.after_failure(world["dir"], store, store.jobs[0]) is None and world["queued"] == []


def test_the_renderer_only_looks_at_failures_from_its_own_run_and_once(world):
    jobs = [{"id": "old", "state": "failed", "updated": 50}, {"id": "new", "state": "failed", "updated": 150}, {"id": "seen", "state": "failed", "updated": 150, "auto_retry_checked": True},
            {"id": "ok", "state": "ready", "updated": 150}, {"id": "none", "state": "failed"}]
    assert [j["id"] for j in RC.due(jobs, 100)] == ["new"]


def test_the_setting_is_off_by_default_and_can_be_turned_on_and_off(world):
    assert RT.status(world["dir"])["auto_retry"] is False
    assert RT.set_(world["dir"], {"auto_retry": True})["auto_retry"] is True
    assert RT.set_(world["dir"], {"auto_retry": False})["auto_retry"] is False
