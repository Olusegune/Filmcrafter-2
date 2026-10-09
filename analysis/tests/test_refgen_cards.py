"""The Pictures step: one card per picture, making a card again with a note, owners' sheets as references, dance sheets, the spend cap, own pictures."""
import json
import os
import shutil

import pytest
from PIL import Image

from pulseframe_analysis import library, refgen, render as R
from tests.test_refgen import FakeKie, proj, wired  # noqa: F401  (fixtures)


def _card(wired, name):
    return next(c for c in refgen.cards(wired)["cards"] if c["name"] == name)


def _make(wired, name, **kw):
    cid = next(c["id"] for c in refgen.candidates(wired, kw.get("redo", ()), kw.get("notes")) if c["name"] == name)
    refgen.queue(wired, [cid], "kie", "fake/model", confirmed=True, **kw)
    R.run(wired, poll_every=0)
    return cid


def test_every_picture_is_one_card_with_its_state(wired):
    cards = {c["name"]: c for c in refgen.cards(wired)["cards"]}
    assert cards["Cara"]["state"] == "yours" and cards["Cara"]["yours"] and cards["Home"]["state"] == "yours"
    assert cards["Solomon"]["state"] == "missing" and cards["Solomon"]["picture"] is None          # only in a group picture
    assert cards["Bell"]["state"] == "missing" and "handbell" in cards["Bell"]["prompt"]
    assert "Ada outfit" not in cards                                                              # drawn on Ada's own sheet
    assert [c["kind"] for c in refgen.cards(wired)["cards"]][:1] == ["character"]


def test_a_made_picture_waits_for_approval_then_is_approved(wired):
    cid = _make(wired, "Solomon")
    c = _card(wired, "Solomon")
    assert c["state"] == "waiting" and c["pending"]["output"].startswith("generations/")
    refgen.use(wired, c["pending"]["job"])
    c = _card(wired, "Solomon")
    assert c["state"] == "approved" and not c["yours"] and c["picture"].startswith("generations/") and c["pending"] is None


def test_a_card_can_be_made_again_with_a_note_and_sees_its_current_picture(wired):
    _make(wired, "Solomon")
    refgen.use(wired, _card(wired, "Solomon")["pending"]["job"])
    cid = _card(wired, "Solomon")["id"]
    assert cid not in [c["id"] for c in refgen.candidates(wired)]                      # not offered unless asked for
    again = next(c for c in refgen.candidates(wired, [cid], {cid: "older, warmer  glasses"}) if c["id"] == cid)
    assert "Change from the current version: older, warmer glasses." in again["prompt"]
    assert again["refs"][0]["path"].startswith("generations/") and "current version" in again["refs"][0]["label"]
    FakeKie.sent.clear()
    refgen.queue(wired, [cid], "kie", "fake/model", confirmed=True, redo=[cid], notes={cid: "older, warmer"})
    R.run(wired, poll_every=0)
    assert "older, warmer" in FakeKie.sent[-1]["prompt"] and len(FakeKie.sent[-1]["image_urls"]) == 1
    assert _card(wired, "Solomon")["state"] == "waiting" and _card(wired, "Solomon")["picture"].startswith("generations/")   # the old one stays until you choose


def test_a_note_is_short_plain_text_and_your_own_picture_is_never_remade(wired):
    cara = _card(wired, "Cara")["id"]
    assert cara not in [c["id"] for c in refgen.candidates(wired, [cara], {cara: "x"})]
    _make(wired, "Bell")
    refgen.use(wired, _card(wired, "Bell")["pending"]["job"])
    bid = _card(wired, "Bell")["id"]
    long = refgen.candidates(wired, [bid], {bid: "word " * 400})[0]["prompt"]
    assert len(long) <= refgen.MAX_PROMPT and long.count("word") <= refgen.MAX_NOTE // 5 + 1


def test_a_prop_is_shown_its_owners_approved_sheet(wired):
    _make(wired, "Solomon")
    refgen.use(wired, _card(wired, "Solomon")["pending"]["job"])
    p, lib = library.load(wired)
    sol = next(i for i in lib["items"] if i["name"] == "Solomon")
    bell = next(i for i in lib["items"] if i["name"] == "Bell")
    bell["owner"] = sol["external_id"]
    library.save_library(wired, p, lib)
    c = next(c for c in refgen.candidates(wired) if c["name"] == "Bell")
    assert c["owner"] == "Solomon" and c["owner_ready"] and c["refs"][0]["path"].startswith("generations/") and "Solomon" in c["refs"][0]["label"]
    assert _card(wired, "Bell")["owner_ready"] is True


def test_a_prop_is_marked_as_waiting_for_an_owner_who_has_no_picture_yet(wired):
    p, lib = library.load(wired)
    sol = next(i for i in lib["items"] if i["name"] == "Solomon")
    next(i for i in lib["items"] if i["name"] == "Bell")["owner"] = sol["external_id"]
    library.save_library(wired, p, lib)
    c = _card(wired, "Bell")
    assert c["owner"] == "Solomon" and c["owner_ready"] is False                      # the screen makes people first


def test_the_spend_cap_stops_a_batch_before_anything_is_sent(wired):
    cid = next(c["id"] for c in refgen.candidates(wired) if c["name"] == "Bell")
    with pytest.raises(SystemExit, match="over your limit"):
        refgen.queue(wired, [cid], "kie", "fake/model", confirmed=True, cap_usd=0.001)
    assert refgen.status(wired)["jobs"] == []
    assert refgen.queue(wired, [cid], "kie", "fake/model", confirmed=True, cap_usd=1.0)["queued"] == 1


def test_a_draft_asks_for_low_quality_only_where_the_model_has_it(wired, monkeypatch):
    def with_quality(provider, model, refresh=False):
        m = R.manifest.__wrapped__(provider, model) if hasattr(R.manifest, "__wrapped__") else None
        return m
    from tests.test_refgen import _fake_manifest
    base = _fake_manifest("kie", "fake/model")
    q = dict(base["inputs"][0], name="quality", enum=["low", "medium", "high"], required=False)
    drafty = dict(base, inputs=base["inputs"] + [q], roles=dict(base["roles"]))
    cid = next(c["id"] for c in refgen.candidates(wired) if c["name"] == "Bell")
    j = {"asset_prompt": "x", "asset_refs": [], "asset_draft": True}
    assert refgen.build_payload(wired, None, j, drafty)["quality"] == "low"
    assert "quality" not in refgen.build_payload(wired, None, dict(j, asset_draft=False), drafty)
    assert "quality" not in refgen.build_payload(wired, None, j, base)                # a model without the choice is left alone
    assert cid


def test_a_picture_of_your_own_replaces_a_made_one_and_is_checked(wired, tmp_path):
    _make(wired, "Bell")
    refgen.use(wired, _card(wired, "Bell")["pending"]["job"])
    bid = _card(wired, "Bell")["id"]
    mine = os.path.join(wired, "mine.png")
    Image.new("RGB", (40, 40), (1, 2, 3)).save(mine)
    out = refgen.own(wired, bid, "mine.png")
    c = next(x for x in out["cards"] if x["id"] == bid)
    assert c["state"] == "yours" and c["picture"] == "mine.png" and c["yours"]
    item = next(i for i in library.load(wired)[1]["items"] if i["id"] == bid)
    assert any(f.endswith("BELL_SPEC.md") for f in item["files"]) and not item.get("generated_from_spec")
    open(os.path.join(wired, "fake.png"), "w").write("not a picture")
    with pytest.raises(SystemExit, match="does not open"):
        refgen.own(wired, bid, "fake.png")
    with pytest.raises(SystemExit, match="in this project"):
        refgen.own(wired, bid, "../outside.png")
    with pytest.raises(SystemExit, match="in this project"):
        refgen.own(wired, bid, os.path.join(str(tmp_path), "x.png"))


def _plan_with_dancer(d):
    os.makedirs(os.path.join(d, "producer"), exist_ok=True)
    plan = {"assets": {"visual_style": "Stylized 3D.", "characters": [{"id": "c_sol", "name": "Solomon"}],
                       "choreography": [{"id": "chor_sol", "character_id": "c_sol", "classification": "featured dance choreography",
                                         "moves": [{"name": "Open", "action": "arms wide"}, {"name": "Turn", "action": "spins on one foot"}]},
                                        {"id": "../bad", "character_id": "c_sol", "classification": "group dance choreography", "moves": [{"name": "x", "action": "y"}]},
                                        {"id": "act_sol", "character_id": "c_sol", "classification": "acting only, restrained", "moves": [{"name": "x", "action": "y"}]}]}}
    json.dump(plan, open(os.path.join(d, "producer", "plan.json"), "w"))


def test_a_dancer_gets_a_dance_sheet_made_after_the_person_and_added_to_the_choreography(wired):
    _plan_with_dancer(wired)
    sheets = [c for c in refgen.candidates(wired) if c["kind"] == "choreo"]
    assert [c["id"] for c in sheets] == ["choreo_chor_sol"]                              # no unsafe id, no acting-only entry
    assert "2 pose panels" in sheets[0]["prompt"] and "Panel 1: Open, arms wide." in sheets[0]["prompt"] and not sheets[0]["owner_ready"]
    _make(wired, "Solomon")
    refgen.use(wired, _card(wired, "Solomon")["pending"]["job"])
    sheet = next(c for c in refgen.candidates(wired) if c["kind"] == "choreo")
    assert sheet["owner_ready"] and sheet["refs"][0]["path"].startswith("generations/") and "Solomon" in sheet["refs"][0]["label"]
    FakeKie.sent.clear()
    refgen.queue(wired, ["choreo_chor_sol"], "kie", "fake/model", confirmed=True)
    R.run(wired, poll_every=0)
    c = _card(wired, "Solomon: dance sheet")
    assert c["state"] == "waiting" and c["kind"] == "choreo"
    refgen.use(wired, c["pending"]["job"])
    ch = json.load(open(os.path.join(wired, "choreography.json"), encoding="utf-8"))
    assert ch["mode"] == "upload" and ch["files"] == [_card(wired, "Solomon: dance sheet")["picture"]]
    assert _card(wired, "Solomon: dance sheet")["state"] == "approved"
    assert "choreo_chor_sol" not in [x["id"] for x in refgen.candidates(wired)]


def test_a_spend_limit_that_is_not_a_real_amount_never_lets_a_batch_through(wired):
    cid = next(c["id"] for c in refgen.candidates(wired) if c["name"] == "Bell")
    for bad in (float("nan"), -1, "abc", float("inf")):
        with pytest.raises(SystemExit, match="not a valid amount"):
            refgen.queue(wired, [cid], "kie", "fake/model", confirmed=True, cap_usd=bad)
    assert refgen.status(wired)["jobs"] == []


def test_the_refgen_command_line_serves_cards_and_refuses_a_bad_picture(wired, capsys):
    def run(*a):
        rc = refgen.main(list(a))
        lines = [json.loads(l) for l in capsys.readouterr().out.splitlines() if l.startswith('{"event": "result"') or l.startswith('{"event": "error"')]
        return rc, lines[-1]
    rc, ev = run("cards", wired)
    assert rc == 0 and {c["name"] for c in ev["data"]["cards"]} >= {"Solomon", "Bell", "Cara"}
    rc, ev = run("own", wired, "--data", json.dumps({"id": "nope", "file": "missing.png"}))
    assert rc == 1 and "in this project" in ev["message"]
    rc, ev = run("estimate", wired, "--data", json.dumps({"ids": [], "provider": "kie", "model": "fake/model"}))
    assert rc == 1 and "at least one" in ev["message"]


def test_pictures_can_be_made_free_on_comfyui_even_when_local_first_is_on(wired, monkeypatch):
    class FakeComfy(FakeKie):
        name = "comfyui"
    monkeypatch.setitem(R.PROVIDERS, "comfyui", FakeComfy)
    p = json.load(open(os.path.join(wired, "project.json")))
    p["routing"] = {"mode": "local"}                                                    # Local First: nothing may go to paid cloud services
    json.dump(p, open(os.path.join(wired, "project.json"), "w"))
    cid = next(c["id"] for c in refgen.candidates(wired) if c["name"] == "Bell")
    monkeypatch.setattr(R, "estimate_payload", lambda prov, *a: {"usd": 0.0 if prov == "comfyui" else 0.02, "basis": "test"})      # ComfyUI never bills
    est = refgen.estimate(wired, [cid], "comfyui", "fake/model")
    assert est["usd"] == 0.0
    with pytest.raises(SystemExit, match="Local First"):
        refgen.queue(wired, [cid], "kie", "fake/model", confirmed=True)             # a cloud provider is still refused
    assert refgen.queue(wired, [cid], "comfyui", "fake/model", confirmed=True, cap_usd=0)["queued"] == 1   # free fits even a $0 limit


def test_comfyui_is_never_priced():
    assert R.estimate_payload("comfyui", "any", {}, {})["usd"] == 0.0
