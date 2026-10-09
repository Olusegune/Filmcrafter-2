"""Keyframe check: failed stills are re-made once with the correction; passing or unchecked ones are left alone."""
import json
import os

import pytest
from PIL import Image

from filmcrafter_engine import render as R
from filmcrafter_engine import stills as ST


@pytest.fixture
def proj(tmp_path, monkeypatch):
    d = tmp_path / "p"; (d / "generations").mkdir(parents=True)
    shot = {"id": "S01-01", "scene": 1, "start": 0.0, "end": 2.0, "beats": ["He waits."], "performers": [], "framing": "wide"}
    (d / "production.json").write_text(json.dumps({"meta": {}, "characters": [], "scenes": [{"number": 1, "shots": [shot]}]}))
    (d / "project.json").write_text(json.dumps({"title": "T"}))
    Image.new("RGB", (64, 36)).save(d / "generations" / "k.png")
    monkeypatch.setattr(ST, "can_check", lambda: True)
    m = R._finish("fal", "img/model", "I", "", [{"name": "prompt", "type": "string", "description": "", "required": True}])
    monkeypatch.setattr(R, "manifest", lambda *a, **k: m)
    return str(d)


def _job(d):
    j = {"id": "k1", "shot_id": "S01-01", "plan": "production", "provider": "fal", "model": "img/model", "kind": "image",
         "state": "ready", "output": "generations/k.png", "created": 1, "overrides": {}}
    json.dump({"jobs": [j]}, open(os.path.join(d, "jobs.json"), "w"))
    s = R.Store(d)
    return s, s.jobs[0]


def test_failed_still_is_remade_once_with_the_fix(proj, monkeypatch):
    monkeypatch.setattr(ST, "check", lambda d, j: {"ok": False, "problems": [{"kind": "collage", "detail": "split panels"}], "fix": "One frame only."})
    s, j = _job(proj)
    ST.after_still(proj, s, j)
    jobs = R.Store(proj).jobs
    assert len(jobs) == 2 and jobs[1]["remake_of"] == "k1" and jobs[1]["state"] == "queued"
    assert "One frame only." in jobs[1]["fix_notes"] and any("no panels" in n for n in jobs[1]["fix_notes"])
    s2 = R.Store(proj); remake = s2.jobs[1]
    ST.after_still(proj, s2, {**remake, "state": "ready", "output": "generations/k.png"})   # the remake fails too: no third try
    assert len(R.Store(proj).jobs) == 2


def test_passing_still_is_kept(proj, monkeypatch):
    monkeypatch.setattr(ST, "check", lambda d, j: {"ok": True, "problems": [], "fix": ""})
    s, j = _job(proj)
    ST.after_still(proj, s, j)
    jobs = R.Store(proj).jobs
    assert len(jobs) == 1 and jobs[0]["still_check"]["ok"] is True


def test_check_failure_marks_unchecked_without_blocking(proj, monkeypatch):
    monkeypatch.setattr(ST, "check", lambda d, j: (_ for _ in ()).throw(RuntimeError("insufficient_quota")))
    s, j = _job(proj)
    ST.after_still(proj, s, j)
    c = R.Store(proj).jobs[0]["still_check"]
    assert c["ok"] is None and "out of credits" in c["error"]


def test_approval_prefers_the_still_that_passed(tmp_path):
    from filmcrafter_engine import library as L
    d = tmp_path / "q"; (d / "g").mkdir(parents=True)
    for n in ("a", "b"):
        Image.new("RGB", (8, 8)).save(d / "g" / f"{n}.png")
    (d / "production.json").write_text(json.dumps({"scenes": [{"number": 1, "shots": [{"id": "S01-01", "start": 0, "end": 1}]}]}))
    (d / "jobs.json").write_text(json.dumps({"jobs": [
        {"id": "a", "shot_id": "S01-01", "plan": "production", "kind": "image", "state": "ready", "output": "g/a.png", "created": 1, "still_check": {"ok": True}},
        {"id": "b", "shot_id": "S01-01", "plan": "production", "kind": "image", "state": "ready", "output": "g/b.png", "created": 2, "still_check": {"ok": False}}]}))
    assert L.pending_keyframes(str(d)) == {"S01-01": "g/a.png"}


def test_budget_reroutes_unsent_jobs_to_the_same_family(tmp_path, monkeypatch):
    from filmcrafter_engine import budget as B, router
    monkeypatch.setenv("KIE_KEY", "k"); monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    d = tmp_path / "r"; d.mkdir()
    (d / "production.json").write_text(json.dumps({"scenes": [{"number": 1, "shots": [{"id": "S01-01", "start": 0, "end": 2, "beats": ["x"], "performers": []}]}]}))
    (d / "project.json").write_text("{}")
    (d / "jobs.json").write_text(json.dumps({"jobs": [{"id": "q", "shot_id": "S01-01", "plan": "production", "provider": "fal",
        "model": "fal-ai/kling-video/v3/turbo/pro/image-to-video", "kind": "video", "state": "queued", "created": 1, "fix_notes": ["tighter"]}]}))
    m = R._finish("kie", "kling-2.6/image-to-video", "K", "", [{"name": "prompt", "type": "string", "description": ""}])
    monkeypatch.setattr(R, "manifest", lambda *a, **k: m)
    r = B.reroute(str(d), "fal")
    assert r["moved"] == [{"shot": "S01-01", "to": "kie", "model": "kling-2.6/image-to-video", "same_family": True}]
    jobs = R.Store(str(d)).jobs
    assert jobs[0]["state"] == "dismissed" and jobs[1]["provider"] == "kie" and jobs[1]["fix_notes"] == ["tighter"]


def test_budget_fits():
    from filmcrafter_engine import budget as B
    v = B.fits({"fal": 4.0, "kie": 500}, {"fal": {"known": True, "amount": -2, "unit": "usd"}, "kie": {"known": True, "amount": 400, "unit": "credits"}})
    assert v["fal"]["fits"] is None and "may be refused" in v["fal"]["reason"]   # undocumented figure: warn only
    assert v["kie"] == {"fits": False, "short": 100.0}
