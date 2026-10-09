"""Working on the whole set of keyframes: the hands check, making new ones for the failures, redoing them on one picture model, and using the new ones (undoably)."""
import json
import os

import pytest
from PIL import Image

from pulseframe_analysis import keyframeset as KS, library as L, render as R, router, routing as RT, shothistory as H, stills as ST

NANO = ("kie", "google/nano-banana-edit")
GPT = ("kie", "gpt/gpt-image-2-5-flare-image-to-image")


def row(label, provider, model, price, sees=True):
    return {"label": label, "provider": provider, "model": model, "price_usd": price, "verified": True, "sees_references": sees}


def jread(d, name):
    p = os.path.join(d, name)
    return json.load(open(p)) if os.path.exists(p) else None


def job(i, shot, model, out, created=10, **kw):
    return {"id": i, "shot_id": shot, "plan": "production", "provider": model[0], "model": model[1], "kind": "image", "state": "ready", "output": out, "overrides": {}, "fix_notes": [],
            "created": created, "updated": created, **kw}


@pytest.fixture
def world(tmp_path, monkeypatch):
    d = tmp_path / "p"
    (d / "media").mkdir(parents=True)
    shots = [
        {"id": "S01-01", "scene": 1, "start": 0.0, "end": 4.0, "performers": ["Sege"], "beats": ["Sege holds Ada's hand."]},
        {"id": "S01-02", "scene": 1, "start": 4.0, "end": 8.0, "performers": ["Ada"], "beats": ["Ada looks up."]},
        {"id": "S01-03", "scene": 1, "start": 8.0, "end": 12.0, "performers": [], "beats": ["The sea at dawn."]},
        {"id": "S01-04", "scene": 1, "start": 12.0, "end": 16.0, "performers": ["Sege"], "beats": ["Sege waves."]},
    ]
    (d / "production.json").write_text(json.dumps({"meta": {}, "characters": [], "scenes": [{"number": 1, "heading": "INT.", "start": 0, "end": 16, "notes": {}, "shots": shots}]}))
    (d / "project.json").write_text(json.dumps({"title": "T", "routing": {"mode": "balanced"}}))
    for n in ("a", "b", "c", "own", "new1", "new2", "new1b"):
        Image.new("RGB", (32, 18), (len(n) * 30, 10, 10)).save(d / "media" / f"{n}.png")
    (d / "keyframes.json").write_text(json.dumps({"production": {"S01-01": "project:media/a.png", "S01-02": "project:media/b.png", "S01-03": "project:media/c.png", "S01-04": "project:media/own.png"}}))
    jobs = [job("i1", "S01-01", NANO, "media/a.png"), job("i2", "S01-02", GPT, "media/b.png"), job("i3", "S01-03", NANO, "media/c.png")]    # S01-04 is the person's own picture: no job
    (d / "jobs.json").write_text(json.dumps({"jobs": jobs}))
    monkeypatch.setattr(RT, "models", lambda kind: [row("Nano Banana", *NANO, 0.03), row("GPT Image 2.5 Flare", *GPT, 0.25), row("Blind", "kie", "kie/blind", 0.01, sees=False)])
    monkeypatch.setattr(RT, "batch_usd", lambda dd, shots, p, m, kind: round(0.1 * len(shots), 2))
    monkeypatch.setattr(router, "available", lambda p: True)
    monkeypatch.setattr(R, "emit", lambda **k: None)
    queued = []

    def enqueue(dd, shots, provider, model, overrides, notes, kind="video", source=None):
        made = [{"id": f"new{len(queued)}", "shot_id": s, "plan": "production", "provider": provider, "model": model, "kind": kind, "state": "queued", "overrides": overrides, "fix_notes": notes,
                 "created": 100 + len(queued), "updated": 100 + len(queued)} for s in shots]
        queued.extend(made)
        st = R.Store(dd)
        st.data["jobs"] += made
        st.save()
        return made

    monkeypatch.setattr(R, "enqueue", enqueue)
    monkeypatch.setattr(ST, "can_check", lambda: True)
    return {"dir": str(d), "queued": queued}


def result(ok, *problems, fix=""):
    return {"ok": ok, "problems": list(problems), "fix": fix, "model": "m", "anatomy_checked": True}


FAIL = result(False, {"kind": "anatomy", "severity": "major", "detail": "The held hands are fused."}, fix="Redraw the hands.")
LOOK = result(True, {"kind": "anatomy", "severity": "minor", "detail": "The left hand is soft."})
PASS = result(True)


def fake_check(by_shot):
    def check(d, j):
        r = by_shot[j["shot_id"]]
        if isinstance(r, Exception):
            raise r
        return dict(r)
    return check


# ---------------------------------------------------------------- the hands check

def test_the_plan_looks_at_shots_with_people_and_leaves_out_empty_ones(world):
    p = KS.check_plan(world["dir"])
    assert p["shots"] == ["S01-01", "S01-02", "S01-04"] and p["skipped"] == [{"shot": "S01-03", "reason": "nobody is in this shot"}]
    assert p["usd_est"] == 0.06 and p["can_check"] is True and p["unavailable"] == ""


def test_without_a_vision_brain_the_plan_says_so_and_the_run_refuses(world, monkeypatch):
    monkeypatch.setattr(ST, "can_check", lambda: False)
    p = KS.check_plan(world["dir"])
    assert p["can_check"] is False and "AI brain" in p["unavailable"]
    with pytest.raises(SystemExit, match="AI brain"):
        KS.check_run(world["dir"])


def test_the_run_keeps_each_result_by_picture_and_sorts_them(world, monkeypatch):
    monkeypatch.setattr(ST, "check", fake_check({"S01-01": FAIL, "S01-02": LOOK, "S01-04": PASS}))
    s = KS.check_run(world["dir"])
    assert s["checked"] == 3 and s["passed"] == 1 and s["errors"] == []
    assert s["failed"] == [{"shot": "S01-01", "kinds": ["anatomy"], "detail": "The held hands are fused."}] and s["look"] == [{"shot": "S01-02", "detail": "The left hand is soft."}]
    saved = jread(world["dir"], "keyframe_checks.json")
    assert set(saved) == {"media/a.png", "media/b.png", "media/own.png"} and saved["media/a.png"]["checked_at"] > 0
    assert KS.state_for(world["dir"]) == {"S01-01": "fail", "S01-02": "look", "S01-04": "pass"}


def test_checked_keyframes_are_not_checked_again_unless_asked(world, monkeypatch):
    monkeypatch.setattr(ST, "check", fake_check({"S01-01": PASS, "S01-02": PASS, "S01-04": PASS}))
    KS.check_run(world["dir"])
    p = KS.check_plan(world["dir"])
    assert p["shots"] == [] and p["already"] == ["S01-01", "S01-02", "S01-04"] and p["usd_est"] == 0
    assert KS.check_plan(world["dir"], again=True)["shots"] == ["S01-01", "S01-02", "S01-04"]
    assert KS.check_run(world["dir"])["checked"] == 0


def test_a_result_from_before_hands_were_checked_does_not_count_as_checked(world):
    j = jread(world["dir"], "jobs.json")
    j["jobs"][0]["still_check"] = {"ok": True, "problems": [], "fix": ""}
    json.dump(j, open(os.path.join(world["dir"], "jobs.json"), "w"))
    assert "S01-01" in KS.check_plan(world["dir"])["shots"] and KS.state_for(world["dir"])["S01-01"] == "pass"


def test_one_picture_failing_to_be_read_does_not_stop_the_rest_and_progress_is_kept(world, monkeypatch):
    monkeypatch.setattr(ST, "check", fake_check({"S01-01": RuntimeError("rate limited"), "S01-02": FAIL, "S01-04": SystemExit("no key")}))
    s = KS.check_run(world["dir"])
    assert s["checked"] == 1 and [e["shot"] for e in s["errors"]] == ["S01-01", "S01-04"] and s["failed"][0]["shot"] == "S01-02"
    assert set(jread(world["dir"], "keyframe_checks.json")) == {"media/b.png"}


def test_choosing_a_different_keyframe_means_the_old_result_no_longer_applies(world, monkeypatch):
    monkeypatch.setattr(ST, "check", fake_check({"S01-01": FAIL, "S01-02": PASS, "S01-04": PASS}))
    KS.check_run(world["dir"])
    kf = jread(world["dir"], "keyframes.json")
    kf["production"]["S01-01"] = "project:media/new1.png"
    json.dump(kf, open(os.path.join(world["dir"], "keyframes.json"), "w"))
    assert "S01-01" not in KS.state_for(world["dir"])


def test_the_timeline_cards_carry_the_result_and_the_model(world, monkeypatch):
    monkeypatch.setattr(ST, "check", fake_check({"S01-01": FAIL, "S01-02": LOOK, "S01-04": PASS}))
    KS.check_run(world["dir"])
    cards = {s["id"]: s for s in L.storyboard(world["dir"])["shots"]}
    assert (cards["S01-01"]["keyframe_check"], cards["S01-02"]["keyframe_check"], cards["S01-04"]["keyframe_check"], cards["S01-03"]["keyframe_check"]) == ("fail", "look", "pass", None)
    assert cards["S01-01"]["keyframe_model"] == NANO[1] and cards["S01-04"]["keyframe_model"] is None


def test_check_states():
    assert KS.check_state(None) is None and KS.check_state({"ok": None}) is None and KS.check_state("junk") is None
    assert KS.check_state(FAIL) == "fail" and KS.check_state(LOOK) == "look" and KS.check_state(PASS) == "pass"


# ---------------------------------------------------------------- making the failures again

def test_failed_keyframes_can_be_made_again_with_the_correction(world, monkeypatch):
    monkeypatch.setattr(ST, "check", fake_check({"S01-01": FAIL, "S01-02": PASS, "S01-04": FAIL}))
    KS.check_run(world["dir"])
    plan = KS.remake_plan(world["dir"])
    assert plan["shots"] == ["S01-01"] and plan["skipped"] == [{"shot": "S01-04", "reason": "not made by a model here (your own picture)"}] and plan["usd_est"] == 0.1
    r = KS.remake_run(world["dir"])
    (q,) = world["queued"]
    assert r["queued"] == 1 and (q["shot_id"], q["provider"], q["model"], q["kind"], q["fix_notes"]) == ("S01-01", NANO[0], NANO[1], "image", ["Redraw the hands."])
    jobs = {j["id"]: j for j in jread(world["dir"], "jobs.json")["jobs"]}
    assert jobs["new0"]["swap_in"] == "hands" and jread(world["dir"], "keyframes.json")["production"]["S01-01"] == "project:media/a.png"      # nothing is replaced yet


def test_nothing_to_make_again_says_so_and_locked_shots_are_left_alone(world, monkeypatch):
    with pytest.raises(SystemExit, match="No keyframe that failed"):
        KS.remake_run(world["dir"])
    monkeypatch.setattr(ST, "check", fake_check({"S01-01": FAIL, "S01-02": PASS, "S01-04": PASS}))
    KS.check_run(world["dir"])
    L.lock(world["dir"], "S01-01", True)
    assert KS.remake_plan(world["dir"])["skipped"] == [{"shot": "S01-01", "reason": "locked"}]
    with pytest.raises(SystemExit, match="No keyframe that failed"):
        KS.remake_run(world["dir"])


# ---------------------------------------------------------------- one picture model

def test_the_target_defaults_to_the_most_used_model_then_the_pinned_one(world):
    p = KS.remodel_plan(world["dir"])
    assert p["target"]["model"] == NANO[1] and p["shots"] == ["S01-02"] and p["from"] == [{"shot": "S01-02", "from": GPT[1]}]
    assert p["skipped"] == [{"shot": "S01-04", "reason": "your own picture"}] and p["usd_est"] == 0.1
    assert [(u["model"], u["count"]) for u in p["used"]] == [(NANO[1], 2), (GPT[1], 1)]
    proj = jread(world["dir"], "project.json")
    proj["routing"]["pins"] = {"image": {"provider": GPT[0], "model": GPT[1]}}
    json.dump(proj, open(os.path.join(world["dir"], "project.json"), "w"))
    q = KS.remodel_plan(world["dir"])
    assert q["target"]["model"] == GPT[1] and q["shots"] == ["S01-01", "S01-03"]


def test_a_model_given_explicitly_wins(world):
    assert KS.remodel_plan(world["dir"], *GPT)["target"]["model"] == GPT[1]


def test_unknown_unavailable_or_blind_models_are_refused(world):
    with pytest.raises(SystemExit, match="isn't in PULSEFRAME's list"):
        KS.remodel_plan(world["dir"], "kie", "nonsense/model")
    with pytest.raises(SystemExit, match="can't see your character pictures"):
        KS.remodel_plan(world["dir"], "kie", "kie/blind")


def test_redoing_on_one_model_queues_tagged_pictures_and_pins_the_model(world):
    r = KS.remodel_run(world["dir"])
    assert r["queued"] == 1 and r["target"]["model"] == NANO[1] and [q["shot_id"] for q in world["queued"]] == ["S01-02"]
    assert world["queued"][0]["model"] == NANO[1] and jread(world["dir"], "jobs.json")["jobs"][-1]["swap_in"] == "model"
    assert jread(world["dir"], "project.json")["routing"]["pins"]["image"] == {"provider": NANO[0], "model": NANO[1]}
    assert jread(world["dir"], "keyframes.json")["production"]["S01-02"] == "project:media/b.png"                 # the old keyframe stays until the new one is used


def test_only_the_shots_asked_for_are_redone_and_pinning_is_optional(world):
    with pytest.raises(SystemExit, match="already on that model"):
        KS.remodel_run(world["dir"], shots=["S01-01"])
    KS.remodel_run(world["dir"], shots=["S01-02"], pin=False)
    assert "pins" not in jread(world["dir"], "project.json")["routing"]


def test_a_service_without_a_key_is_refused_before_anything_is_queued(world, monkeypatch):
    monkeypatch.setattr(router, "available", lambda p: False)
    monkeypatch.setattr(RT, "models", lambda kind: [row("Nano Banana", *NANO, 0.03), row("GPT", *GPT, 0.25)])
    with pytest.raises(SystemExit, match="Add your Kie.ai key"):
        KS.remodel_run(world["dir"])
    assert world["queued"] == []


def test_everything_already_on_one_model_has_nothing_to_redo(world):
    jobs = jread(world["dir"], "jobs.json")
    jobs["jobs"][1]["model"], jobs["jobs"][1]["provider"] = NANO[1], NANO[0]
    json.dump(jobs, open(os.path.join(world["dir"], "jobs.json"), "w"))
    assert KS.remodel_plan(world["dir"])["shots"] == []
    with pytest.raises(SystemExit, match="already on that model"):
        KS.remodel_run(world["dir"])


# ---------------------------------------------------------------- using the new ones

def add_jobs(world, *extra):
    j = jread(world["dir"], "jobs.json")
    j["jobs"] += list(extra)
    json.dump(j, open(os.path.join(world["dir"], "jobs.json"), "w"))


def test_the_status_counts_what_is_making_ready_and_failed(world):
    add_jobs(world, job("n1", "S01-02", NANO, "media/new1.png", swap_in="model"), job("n2", "S01-01", NANO, "media/new2.png", swap_in="hands", still_check=FAIL),
            job("n3", "S01-04", NANO, None, swap_in="model", state="queued"), job("n4", "S01-03", NANO, None, swap_in="model", state="failed"))
    s = KS.swap_status(world["dir"])
    assert (s["making"], s["ready"], s["failed"]) == (1, 1, 2) and s["shots_ready"] == ["S01-02"]
    assert s["reasons"]["model"] == {"making": 1, "ready": 1, "failed": 1} and s["reasons"]["hands"] == {"making": 0, "ready": 0, "failed": 1}


def test_using_the_new_keyframes_swaps_them_in_clears_the_tag_and_can_be_undone(world):
    add_jobs(world, job("n1", "S01-02", NANO, "media/new1.png", created=50, swap_in="model"), job("n2", "S01-02", NANO, "media/new1b.png", created=60, swap_in="model"))
    r = KS.apply_swaps(world["dir"])
    assert r == {"applied": ["S01-02"], "skipped": []}
    assert jread(world["dir"], "keyframes.json")["production"]["S01-02"] == "project:media/new1b.png"                 # the newest
    assert all(not j.get("swap_in") and j.get("swap_applied") for j in jread(world["dir"], "jobs.json")["jobs"] if j["id"] in ("n1", "n2"))
    assert KS.swap_status(world["dir"])["ready"] == 0
    assert H.entries(world["dir"])["undo"][0]["label"].startswith("Use new keyframes")
    H.undo(world["dir"])
    assert jread(world["dir"], "keyframes.json")["production"]["S01-02"] == "project:media/b.png"


def test_a_locked_shot_and_a_picture_that_failed_its_check_are_not_swapped(world):
    add_jobs(world, job("n1", "S01-02", NANO, "media/new1.png", swap_in="model"), job("n2", "S01-01", NANO, "media/new2.png", swap_in="hands", still_check=FAIL))
    L.lock(world["dir"], "S01-02", True)
    r = KS.apply_swaps(world["dir"])
    assert r["applied"] == [] and {s["shot"]: s["reason"] for s in r["skipped"]} == {"S01-02": "locked", "S01-01": "the new picture failed its check"}
    assert jread(world["dir"], "keyframes.json")["production"]["S01-01"] == "project:media/a.png"


def test_only_the_shots_asked_for_are_swapped_and_nothing_to_swap_leaves_no_history(world):
    add_jobs(world, job("n1", "S01-02", NANO, "media/new1.png", swap_in="model"), job("n2", "S01-01", NANO, "media/new2.png", swap_in="model"))
    before = H.entries(world["dir"])["undo_count"]
    assert KS.apply_swaps(world["dir"], ["S01-03"]) == {"applied": [], "skipped": []} and H.entries(world["dir"])["undo_count"] == before
    assert KS.apply_swaps(world["dir"], ["S01-01"])["applied"] == ["S01-01"]
    assert jread(world["dir"], "keyframes.json")["production"]["S01-02"] == "project:media/b.png"


def test_a_picture_file_that_has_gone_is_never_swapped_in(world):
    add_jobs(world, job("n1", "S01-02", NANO, "media/missing.png", swap_in="model"))
    assert KS.apply_swaps(world["dir"])["applied"] == []


def test_an_automatic_remake_of_a_new_keyframe_stays_part_of_the_swap(world, monkeypatch):
    add_jobs(world, job("n1", "S01-02", NANO, "media/new1.png", swap_in="model"))
    monkeypatch.setattr(ST, "check", lambda d, j: ST.settle({"ok": False, "problems": [{"kind": "text", "severity": "major", "detail": "A title."}], "fix": "No text."}, "m"))
    store = R.Store(world["dir"])
    ST.after_still(world["dir"], store, next(j for j in store.jobs if j["id"] == "n1"))
    assert world["queued"] and world["queued"][0]["fix_notes"] == ["No text.", "One single continuous camera frame; no panels, inset portraits or lettering anywhere."]
    assert jread(world["dir"], "jobs.json")["jobs"][-1]["swap_in"] == "model"


# ---------------------------------------------------------------- paths from a project file

def test_a_keyframe_or_job_path_that_leads_outside_the_project_is_never_used(world, tmp_path):
    outside = tmp_path / "outside.png"
    Image.new("RGB", (8, 8)).save(outside)
    kf = jread(world["dir"], "keyframes.json")
    kf["production"]["S01-01"] = "project:../outside.png"
    kf["production"]["S01-02"] = "project:" + str(outside)
    json.dump(kf, open(os.path.join(world["dir"], "keyframes.json"), "w"))
    assert [c["rel"] for c in KS.current(world["dir"])][:2] == [None, None]
    assert "S01-01" not in KS.check_plan(world["dir"])["shots"] and "S01-02" not in KS.check_plan(world["dir"])["shots"]
    add_jobs(world, job("n1", "S01-03", NANO, "../outside.png", swap_in="model"), job("n2", "S01-04", NANO, str(outside), swap_in="model"))
    assert KS.apply_swaps(world["dir"])["applied"] == []
    assert jread(world["dir"], "keyframes.json")["production"]["S01-03"] == "project:media/c.png"


def test_inside_accepts_only_real_files_in_the_project(world):
    assert KS.inside(world["dir"], "media/a.png") is True
    for bad in ("media/none.png", "media", "../x", "", None, 3, "/etc/passwd", "C:/Windows/win.ini"):
        assert KS.inside(world["dir"], bad) is False, bad


# ---------------------------------------------------------------- the flagged list

def test_the_plan_lists_the_flagged_keyframes_failures_first_with_what_is_wrong(world, monkeypatch):
    monkeypatch.setattr(ST, "check", fake_check({"S01-01": LOOK, "S01-02": FAIL, "S01-04": PASS}))
    KS.check_run(world["dir"])
    f = KS.check_plan(world["dir"])["flagged"]
    assert [(x["shot"], x["state"], x["image"]) for x in f] == [("S01-02", "fail", "media/b.png"), ("S01-01", "look", "media/a.png")]
    assert f[0]["detail"] == "The held hands are fused." and f[1]["detail"] == "The left hand is soft." and f[0]["locked"] is False


def test_nothing_is_flagged_before_a_check_or_after_a_clean_one(world, monkeypatch):
    assert KS.check_plan(world["dir"])["flagged"] == []
    monkeypatch.setattr(ST, "check", fake_check({"S01-01": PASS, "S01-02": PASS, "S01-04": PASS}))
    KS.check_run(world["dir"])
    assert KS.check_plan(world["dir"])["flagged"] == []
