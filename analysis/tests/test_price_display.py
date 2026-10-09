"""Prices shown for a model: the engine's estimate for a Kie model gives credits and the dollar figure for the same credits, and the list's per-5-second price is the same
quantity for every model (so models can be compared with each other, not with a shot of another length)."""
import json
import os

import pytest

from pulseframe_analysis import render as R, routing
from pulseframe_analysis.budget import KIE_USD_PER_CREDIT
from tests.test_native_dialogue import SHOT, _talking, scene  # noqa: F401  (a project folder with one shot; a fixture)


@pytest.fixture
def priced(scene, monkeypatch):                                                    # noqa: F811
    plan = {"meta": {}, "characters": [], "scenes": [{"number": 1, "heading": "INT.", "shots": [{**SHOT, "start": 8.48, "end": 10.18}]}]}
    json.dump(plan, open(os.path.join(scene, "production.json"), "w"))
    json.dump({"title": "T", "look": {"style": "auto"}}, open(os.path.join(scene, "project.json"), "w"))
    monkeypatch.setattr(R, "manifest", lambda p, m: _talking())
    monkeypatch.setattr(R, "_reference_files", lambda *a, **k: [])
    monkeypatch.delenv("KIE_KEY", raising=False)                                   # no balance lookup, no network
    return scene


def test_a_kie_estimate_gives_credits_and_the_dollars_they_are_worth(priced, monkeypatch):
    monkeypatch.setattr(R, "kie_cost_memory", lambda: {"test/talker": 99.0})
    e = R.estimate(priced, ["S01-01"], "kie", "test/talker")
    assert e["kie_credits_est"] == 99
    assert e["kie_usd_est"] == pytest.approx(99 * KIE_USD_PER_CREDIT, abs=0.006)          # 99 credits is about 50 cents


def test_the_dollar_figure_scales_with_the_number_of_shots(priced, monkeypatch):
    plan = json.load(open(os.path.join(priced, "production.json")))
    two = [{**SHOT, "id": "S01-01", "start": 0.0, "end": 2.0}, {**SHOT, "id": "S01-02", "start": 2.0, "end": 4.0}]
    plan["scenes"][0]["shots"] = two
    json.dump(plan, open(os.path.join(priced, "production.json"), "w"))
    monkeypatch.setattr(R, "kie_cost_memory", lambda: {"test/talker": 50.0})
    one = R.estimate(priced, ["S01-01"], "kie", "test/talker")
    both = R.estimate(priced, ["S01-01", "S01-02"], "kie", "test/talker")
    assert both["kie_credits_est"] == 2 * one["kie_credits_est"] and both["kie_usd_est"] == pytest.approx(2 * one["kie_usd_est"], abs=0.011)


def test_a_model_with_no_history_has_no_kie_figures_at_all(priced, monkeypatch):
    monkeypatch.setattr(R, "kie_cost_memory", lambda: {})
    e = R.estimate(priced, ["S01-01"], "kie", "test/talker")
    assert "kie_credits_est" not in e and "kie_usd_est" not in e


def test_the_lists_price_is_for_the_same_shot_length_for_every_model(monkeypatch):
    """The ladder compares models with each other, so every row must be priced for the same length: SHOT_SECONDS."""
    monkeypatch.setattr(R, "_fal_price", lambda m: {"unit": "second", "unit_price": 0.14})
    assert routing.SHOT_SECONDS == 5
    assert routing.shot_price("fal", "any/model") == pytest.approx(0.14 * 5)                         # Kling at 14 cents a second is 70 cents per 5 s, whatever the shot is
    monkeypatch.setattr(R, "_fal_price", lambda m: {"unit": "second", "unit_price": 0.0})
    assert routing.shot_price("fal", "free/model") == 0.0                                             # a zero price is free
    monkeypatch.setattr(R, "_fal_price", lambda m: None)
    assert routing.shot_price("fal", "unknown/model") is None                                         # no price at all is not the same as free
