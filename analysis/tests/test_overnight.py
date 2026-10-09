import json
import os

import pytest

from pulseframe_analysis import export, overnight as O, render, routing


def _proj(tmp_path):
    d = tmp_path / "P"
    d.mkdir()
    shots = [{"id": f"S01-0{i}", "scene": 1, "start": i - 1, "end": i, "beats": ["x"], "performers": []} for i in (1, 2)]
    (d / "production.json").write_text(json.dumps({"scenes": [{"number": 1, "shots": shots}]}))
    (d / "project.json").write_text(json.dumps({"title": "P"}))
    (d / "jobs.json").write_text(json.dumps({"jobs": []}))
    return str(d)


@pytest.fixture
def comfy(monkeypatch):
    monkeypatch.setattr(routing, "_comfy_flow", lambda k: {"model": f"pulseframe-{k}", "title": k})
    monkeypatch.setattr(render, "manifest", lambda p, m: {"model": m, "roles": {}, "inputs": []})


def test_start_needs_both_workflows(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "_comfy_flow", lambda k: None)
    with pytest.raises(SystemExit, match="ComfyUI"):
        O.start(_proj(tmp_path))


def test_full_overnight_flow_is_free_and_ends_in_export(tmp_path, comfy, monkeypatch):
    d = _proj(tmp_path)
    r = O.start(d)
    jobs = json.load(open(os.path.join(d, "jobs.json")))["jobs"]
    assert r["keyframes_queued"] == 2 and all(j["provider"] == "comfyui" and j["kind"] == "image" for j in jobs)
    # keyframes finish
    for j in jobs:
        j.update(state="ready", output=f"g/{j['id']}.png")
        os.makedirs(os.path.join(d, "g"), exist_ok=True)
        open(os.path.join(d, j["output"]), "wb").write(b"x")
    json.dump({"jobs": jobs}, open(os.path.join(d, "jobs.json"), "w"))
    assert O.advance(d) is True   # approved + videos queued
    jobs = json.load(open(os.path.join(d, "jobs.json")))["jobs"]
    vids = [j for j in jobs if j["kind"] == "video"]
    assert len(vids) == 2 and all(j["provider"] == "comfyui" for j in vids)
    # videos fail: no second attempt, it exports what there is and stops
    for j in vids:
        j["state"] = "failed"
    json.dump({"jobs": jobs}, open(os.path.join(d, "jobs.json"), "w"))
    monkeypatch.setattr(export, "build", lambda d_, preset: {"path": "out.mp4"})
    assert O.advance(d) is False
    st = O.status(d)
    assert st["active"] is False and st["export"] == "out.mp4"


def test_advance_does_nothing_when_not_active(tmp_path):
    assert O.advance(_proj(tmp_path)) is False


def test_hybrid_picks_kie_keyframes_and_comfy_videos(monkeypatch):
    monkeypatch.setenv("KIE_KEY", "k")
    monkeypatch.setattr(routing, "_comfy_flow", lambda k: {"model": f"pulseframe-{k}", "title": k} if k == "video" else None)
    monkeypatch.setattr(routing, "shot_price", lambda p, m: 0.02 if "nano-banana" in m else 0.03)
    proj = {"routing": {"mode": "hybrid"}}
    img, vid = routing.pick(proj, "image"), routing.pick(proj, "video")
    assert img["provider"] == "kie" and img["model"] == "google/nano-banana-edit"
    assert vid["provider"] == "comfyui" and vid["free"]


def test_hybrid_overnight_asks_before_paying_for_keyframes(tmp_path, monkeypatch):
    monkeypatch.setenv("KIE_KEY", "k")
    monkeypatch.setattr(routing, "_comfy_flow", lambda k: {"model": "pulseframe-video", "title": "v"} if k == "video" else None)
    monkeypatch.setattr(routing, "shot_price", lambda p, m: 0.02)
    monkeypatch.setattr(routing, "batch_usd", lambda *a: 0.04)
    monkeypatch.setattr(render, "manifest", lambda p, m: {"model": m, "roles": {}, "inputs": []})
    d = _proj(tmp_path)
    p = json.load(open(os.path.join(d, "project.json")))
    p["routing"] = {"mode": "hybrid"}
    json.dump(p, open(os.path.join(d, "project.json"), "w"))
    r = O.start(d)
    assert r["needs_confirm"] and r["keyframes"] == 2 and r["usd"] == 0.04
    assert json.load(open(os.path.join(d, "jobs.json")))["jobs"] == []   # nothing queued without the yes
    r = O.start(d, confirmed=True)
    jobs = json.load(open(os.path.join(d, "jobs.json")))["jobs"]
    assert r["keyframes_queued"] == 2 and all(j["provider"] == "kie" and j["kind"] == "image" for j in jobs)
