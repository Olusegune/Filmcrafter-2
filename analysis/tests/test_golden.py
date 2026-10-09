import json
import os
import time

import pytest

from pulseframe_analysis import golden, lipsync_check, render, routing, supervisor as SV


def _project(tmp_path, jobs, kf=None, project=None):
    d = tmp_path / "P"
    d.mkdir()
    shots = [{"id": f"S01-0{i}", "scene": 1, "start": 2 * (i - 1), "end": 2 * i, "beats": ["x"], "performers": ["Ada"]} for i in (1, 2, 3)]
    (d / "production.json").write_text(json.dumps({"scenes": [{"number": 1, "shots": shots}]}))
    (d / "project.json").write_text(json.dumps(project or {"title": "P"}))
    (d / "jobs.json").write_text(json.dumps({"jobs": jobs}))
    for j in jobs:
        if j.get("output"):
            p = os.path.join(d, j["output"])
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(b"x")
    if kf:
        (d / "keyframes.json").write_text(json.dumps({"production": kf}))
        for ref in kf.values():
            p = os.path.join(d, ref[8:])
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(b"k")
    return str(d)


def J(i, shot, **kw):
    return {"id": i, "shot_id": shot, "plan": "production", "provider": "kie", "model": "m", "state": "ready", "created": 1,
            "output": f"g/{i}.mp4", **kw}


def test_status_classifies_takes_and_stale(tmp_path):
    d = _project(tmp_path, [J("v", "S01-01", keyframe_ref="project:k/old.png"),
                            J("s", "S01-02", provider="own", media_kind="image", model=golden.STILL_MODEL, output="k/b.png")],
                 kf={"S01-01": "project:k/new.png", "S01-02": "project:k/b.png"})
    s = golden.status(d)
    assert s["video"] == ["S01-01"] and s["still"] == ["S01-02"] and s["none"] == ["S01-03"]
    assert s["stale"] == ["S01-01"]


def _age(d, job, seconds):
    """Make a take's file look `seconds` old, as it would be if it had been rendered then."""
    p = os.path.join(d, job["output"])
    t = time.time() - seconds
    os.utime(p, (t, t))


def test_stale_by_time_for_older_takes(tmp_path):
    job = J("v", "S01-01", created=int(time.time()) - 3600)
    d = _project(tmp_path, [job], kf={"S01-01": "project:k/a.png"})
    _age(d, job, 3600)                                            # rendered an hour ago; the keyframe was written just now
    assert golden.status(d)["stale"] == ["S01-01"]
    (tmp_path / "b").mkdir()
    job2 = J("v", "S01-01", created=int(time.time()) + 3600)
    d2 = _project(tmp_path / "b", [job2], kf={"S01-01": "project:k/a.png"})
    assert golden.status(d2)["stale"] == []


def test_a_copied_project_does_not_make_every_older_take_look_out_of_date(tmp_path):
    """Save As, a backup or another computer stamps every file with the copy time: that is not evidence that a keyframe changed."""
    now = int(time.time())
    jobs = [J("a", "S01-01", created=now - 7200), J("b", "S01-02", created=now - 7200), J("c", "S01-03", created=now - 7200)]
    d = _project(tmp_path, jobs, kf={"S01-01": "project:k/a.png", "S01-02": "project:k/b.png", "S01-03": "project:k/c.png"})
    assert golden.status(d)["stale"] == []                         # every file was just written, keyframes and takes alike
    for j in jobs:                                                 # the keyframe files a minute newer than the takes' files: still the same copy
        t = time.time()
        os.utime(os.path.join(d, j["output"]), (t, t))
    assert golden.status(d)["stale"] == []


def test_a_keyframe_changed_long_after_an_older_take_was_made_is_still_caught(tmp_path):
    job = J("v", "S01-01", created=int(time.time()) - 86400)
    d = _project(tmp_path, [job], kf={"S01-01": "project:k/a.png"})
    _age(d, job, 86400)
    assert golden.status(d)["stale"] == ["S01-01"]
    t = time.time() - 600                                          # a keyframe ten minutes older than now but a day newer than the take
    os.utime(os.path.join(d, "k/a.png"), (t, t))
    assert golden.status(d)["stale"] == ["S01-01"]


def test_a_take_that_recorded_its_keyframe_is_judged_by_that_not_by_time(tmp_path):
    job = J("v", "S01-01", created=int(time.time()) - 86400, keyframe_ref="project:k/a.png")
    d = _project(tmp_path, [job], kf={"S01-01": "project:k/a.png"})
    _age(d, job, 86400)
    assert golden.status(d)["stale"] == []                         # the same keyframe, however new its file
    job2 = J("v", "S01-01", keyframe_ref="project:k/old.png")
    (tmp_path / "c").mkdir()
    d2 = _project(tmp_path / "c", [job2], kf={"S01-01": "project:k/a.png"})
    assert golden.status(d2)["stale"] == ["S01-01"]


def test_supervisor_offers_stale_regenerate_and_groups(tmp_path):
    rv = {"reviewed": True, "status": "needs_attention", "issues": [{"kind": "framing", "severity": "major", "detail": "wide", "fix": "closer"}]}
    d = _project(tmp_path, [J("a", "S01-01", review=rv), J("b", "S01-02", review=rv), J("c", "S01-03", keyframe_ref="project:k/x.png")],
                 kf={"S01-03": "project:k/y.png"})
    l = SV.listing(d)
    assert any(i["source"] == "keyframe changed" and i["shot"] == "S01-03" for i in l["items"])
    g = next(g for g in l["groups"] if g["title"] == "Framing in the take")
    assert g["shots"] == ["S01-01", "S01-02"] and g["action"] == "fix"


def test_decide_many_fixes_each_with_its_note(tmp_path, monkeypatch):
    rv = {"reviewed": True, "status": "needs_attention", "issues": [{"kind": "framing", "severity": "major", "detail": "wide", "fix": "closer"}]}
    d = _project(tmp_path, [J("a", "S01-01", review=rv), J("b", "S01-02", review=rv)])
    monkeypatch.setattr(render, "manifest", lambda p, m: {"model": m or "x", "roles": {}, "inputs": []})
    g = SV.listing(d)["groups"][0]
    r = SV.decide_many(d, g["items"], "fix", "kie", "wan/3-0-video")
    assert sorted(r["batch"]["done"]) == ["S01-01", "S01-02"]
    q = [j for j in json.load(open(os.path.join(d, "jobs.json")))["jobs"] if j["state"] == "queued"]
    assert len(q) == 2 and all(j["fix_notes"] == ["closer"] for j in q)


def test_budget_counts_queued_work(tmp_path, monkeypatch):
    d = _project(tmp_path, [J("q", "S01-01", state="queued", estimate_usd=4.0, output=None)], project={"title": "P", "routing": {"budget_usd": 5}})
    monkeypatch.setattr(routing, "batch_usd", lambda *a: 2.0)
    assert routing.pending_usd(d) == 4.0
    with pytest.raises(SystemExit, match="Over budget"):
        routing.guard(d, ["S01-02"], "fal", "m", "video")


def test_split_fills_kie_then_fal(tmp_path, monkeypatch):
    d = _project(tmp_path, [])
    from pulseframe_analysis import budget
    monkeypatch.setattr(budget, "balance", lambda p: {"known": True, "amount": 150.0} if p == "kie" else {"known": True, "amount": 20.0})
    monkeypatch.setattr(render, "estimate", lambda d_, s, p, m, k: {"kie_credits_est": 70} if p == "kie" else {"usd": 0.25})
    r = golden.split(d, ["S01-01", "S01-02", "S01-03"], "video", {"kie": "wan/3-0-video", "fal": "alibaba/wan-3.0/image-to-video"})
    assert r["kie"] == ["S01-01", "S01-02"] and r["fal"] == ["S01-03"] and r["kie_credits"] == 140 and r["fal_usd"] == 0.25 and r["needed"]


def test_lipsync_moments_sample_words_and_a_pause():
    shot = {"start": 10.0, "end": 14.0}
    m = lipsync_check.moments(shot, [{"text": "my mind dey pack bag", "start": 10.2, "end": 12.0}])
    sung = [x for x in m if x[1].startswith("sung")]
    assert 1 <= len(sung) <= 3 and all(0 <= t <= 4 for t, _ in m)
    assert any(l.startswith("pause") and t >= 2.0 for t, l in m)


def test_lipsync_off_becomes_major_finding(tmp_path, monkeypatch):
    d = _project(tmp_path, [J("a", "S01-01", lipsync_check={"verdict": "off", "detail": "closed mouth on words", "fix": "sync"})])
    monkeypatch.setenv("FAL_KEY", "k")
    it = next(i for i in SV.listing(d)["items"] if i["source"] == "lip-sync check")
    assert it["severity"] == "major" and it["kind"] == "lipsync" and it["render"]["provider"] == "fal"
    SV.decide(d, it["id"], "accept")
    assert not any(i["source"] == "lip-sync check" for i in SV.listing(d)["items"])
