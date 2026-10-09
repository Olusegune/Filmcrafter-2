import json
import os

import pytest

from filmcrafter_engine import budget, localmodels, render, routing


def _proj(tmp_path, routing_cfg=None):
    d = tmp_path / "P"
    d.mkdir()
    p = {"title": "P"}
    if routing_cfg:
        p["routing"] = routing_cfg
    (d / "project.json").write_text(json.dumps(p))
    (d / "jobs.json").write_text(json.dumps({"jobs": [{"provider": "fal", "state": "ready", "estimate_usd": 4.0, "shot_id": "x"}]}))
    return str(d)


def test_default_mode_is_premium_and_unchanged():
    s = routing.settings({})
    assert s["mode"] == "premium" and s["budget_usd"] is None and not s["chosen"]


def test_pick_follows_mode(monkeypatch):
    monkeypatch.setenv("KIE_KEY", "k")
    monkeypatch.setenv("FAL_KEY", "k")
    monkeypatch.setenv("FILMCRAFTER_OPENAI_KEY", "k")
    assert routing.pick({"routing": {"mode": "balanced"}}, "video")["model"] == "wan/3-0-video"
    assert routing.pick({"routing": {"mode": "balanced"}}, "image")["model"] == "google/nano-banana-edit"
    assert routing.pick({"routing": {"mode": "premium"}}, "video")["model"] == "bytedance/seedance-2"          # Kie.ai first, where both have it
    assert routing.pick({"routing": {"mode": "premium"}}, "image")["provider"] == "kie"
    assert routing.pick({"routing": {"mode": "premium"}}, "video")["provider"] == "kie"


def test_premium_falls_back_to_fal_or_openai_when_there_is_no_kie_key(monkeypatch):
    monkeypatch.delenv("KIE_KEY", raising=False)
    monkeypatch.setenv("FAL_KEY", "k")
    monkeypatch.setenv("FILMCRAFTER_OPENAI_KEY", "k")
    assert routing.pick({"routing": {"mode": "premium"}}, "video")["provider"] == "fal"
    assert routing.pick({"routing": {"mode": "premium"}}, "image")["provider"] == "openai"


def test_local_mode_without_comfy_offers_free_path(monkeypatch):
    monkeypatch.setattr(routing, "_comfy_flow", lambda kind: None)
    r = routing.pick({"routing": {"mode": "local"}}, "video")
    assert r["provider"] is None and "moving stills" in r["reason"]


def test_local_mode_refuses_cloud_but_allows_comfy(tmp_path):
    d = _proj(tmp_path, {"mode": "local"})
    with pytest.raises(SystemExit, match="Local First"):
        routing.guard(d, ["S01-01"], "fal", "m", "video")
    routing.guard(d, ["S01-01"], "comfyui", "wf", "video")


def test_budget_refuses_batch_that_does_not_fit(tmp_path, monkeypatch):
    d = _proj(tmp_path, {"mode": "balanced", "budget_usd": 5})
    monkeypatch.setattr(routing, "batch_usd", lambda *a: 2.0)
    with pytest.raises(SystemExit, match=r"spent \$4.00 of its \$5.00"):
        routing.guard(d, ["a", "b"], "fal", "m", "video")
    monkeypatch.setattr(routing, "batch_usd", lambda *a: 0.5)
    routing.guard(d, ["a"], "fal", "m", "video")


def test_unknown_price_counts_high(tmp_path, monkeypatch):
    d = _proj(tmp_path)
    monkeypatch.setattr(render, "estimate", lambda *a, **k: {"usd": None, "usd_known": 0, "unknown": 3})
    assert routing.batch_usd(d, ["a", "b", "c"], "openai", "m", "image") == pytest.approx(0.75)


def test_enqueue_is_guarded(tmp_path, monkeypatch):
    d = _proj(tmp_path, {"mode": "local"})
    (tmp_path / "P" / "production.json").write_text(json.dumps({"scenes": [{"number": 1, "shots": [
        {"id": "S01-01", "start": 0, "end": 2, "beats": ["x"]}]}]}))
    monkeypatch.setattr(render, "manifest", lambda p, m: {"model": m or "x", "roles": {}, "inputs": []})
    with pytest.raises(SystemExit, match="Local First"):
        render.enqueue(d, ["S01-01"], "fal", "x", {})
    assert json.load(open(tmp_path / "P" / "jobs.json"))["jobs"][0]["shot_id"] == "x"   # nothing queued


def test_set_validates_budget(tmp_path, monkeypatch):
    d = _proj(tmp_path)
    monkeypatch.setattr(routing, "online", lambda timeout=2.0: False)
    s = routing.set_(d, {"mode": "balanced", "budget_usd": "25"})
    assert s["mode"] == "balanced" and s["budget_usd"] == 25 and s["remaining_usd"] == 21 and s["online"] is False
    assert routing.set_(d, {"budget_usd": ""})["budget_usd"] is None
    with pytest.raises(SystemExit):
        routing.set_(d, {"budget_usd": "lots"})


def test_local_models_status_when_nothing_runs(monkeypatch):
    import requests
    def boom(*a, **k):
        raise requests.ConnectionError()
    monkeypatch.setattr(requests, "get", boom)
    s = localmodels.status()
    assert s["ollama"]["running"] is False and s["recommended"][0]["installed"] is False
    with pytest.raises(SystemExit, match="e.g."):
        localmodels.pull("bad name; rm")



def test_cheapest_picks_lowest_real_price_among_proven(monkeypatch):
    monkeypatch.setenv("KIE_KEY", "k")
    monkeypatch.setenv("FAL_KEY", "k")
    prices = {("kie", "hailuo/2-3-image-to-video-standard"): 0.15, ("kie", "wan/3-0-video"): 0.35, ("fal", "alibaba/wan-3.0/image-to-video"): 0.25,
              ("kie", "google/nano-banana-edit"): 0.02, ("fal", "fal-ai/nano-banana/edit"): 0.04, ("fal", "fal-ai/ltx-2.3/image-to-video"): 0.01}
    monkeypatch.setattr(routing, "shot_price", lambda p, m: prices.get((p, m)))
    v = routing.pick({"routing": {"mode": "cheapest"}}, "video")
    assert (v["provider"], v["model"], v["price_usd"]) == ("kie", "hailuo/2-3-image-to-video-standard", 0.15)   # LTX isn't proven
    assert routing.pick({"routing": {"mode": "cheapest"}}, "image")["model"] == "google/nano-banana-edit"


def test_shot_price_units(monkeypatch):
    from filmcrafter_engine import render
    monkeypatch.setattr(render, "kie_cost_memory", lambda: {"m": 30})
    assert routing.shot_price("kie", "m") == 0.15
    monkeypatch.setattr(render, "_fal_price", lambda m: {"unit": "seconds", "unit_price": 0.05})
    assert routing.shot_price("fal", "x") == 0.25


def test_pinned_model_wins_over_mode_but_not_local(tmp_path, monkeypatch):
    monkeypatch.setenv("KIE_KEY", "k")
    monkeypatch.setattr(routing, "shot_price", lambda p, m: 0.1)
    proj = {"routing": {"mode": "premium", "pins": {"video": {"provider": "kie", "model": "hailuo/2-3-image-to-video-standard"}}}}
    v = routing.pick(proj, "video")
    assert v["pinned"] and v["model"] == "hailuo/2-3-image-to-video-standard"
    proj["routing"]["mode"] = "local"
    monkeypatch.setattr(routing, "_comfy_flow", lambda k: None)
    assert routing.pick(proj, "video")["provider"] is None


def test_set_pin_validates_and_clears(tmp_path, monkeypatch):
    d = _proj(tmp_path)
    monkeypatch.setattr(routing, "online", lambda timeout=2.0: True)
    routing.set_(d, {"pin": {"kind": "video", "provider": "kie", "model": "wan/3-0-video"}})
    assert json.load(open(os.path.join(d, "project.json")))["routing"]["pins"]["video"]["model"] == "wan/3-0-video"
    with pytest.raises(SystemExit):
        routing.set_(d, {"pin": {"kind": "video", "provider": "kie", "model": "made-up"}})
    routing.set_(d, {"pin": {"kind": "video", "clear": True}})
    assert json.load(open(os.path.join(d, "project.json")))["routing"]["pins"] == {}


def test_models_list_sorted_by_price(monkeypatch):
    monkeypatch.setenv("FAL_KEY", "k")
    monkeypatch.delenv("KIE_KEY", raising=False)
    prices = {"fal-ai/vidu/q3/image-to-video/turbo": 0.04, "fal-ai/pixverse/v5.5/image-to-video": 0.05}
    monkeypatch.setattr(routing, "shot_price", lambda p, m: prices.get(m, 0.9))
    rows = routing.models("video")
    assert rows[0]["model"] == "fal-ai/vidu/q3/image-to-video/turbo" and all(r["provider"] == "fal" for r in rows)
