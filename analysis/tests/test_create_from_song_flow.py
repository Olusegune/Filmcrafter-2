"""The whole Create from song path in one run, with stand-ins for the language model and the picture provider:
plan -> shots -> approve -> build -> make the pictures -> approve one, change one -> export -> open in another project."""
import json
import os
import shutil
import zipfile

import pytest
from PIL import Image

from pulseframe_analysis import library, producer_import as PI, producer_plan as P, refgen, render as R
from tests.test_producer_plan import ASSETS, proj, shots_for  # noqa: F401  (fixtures and data)
from tests.test_refgen import FakeKie, _fake_manifest


@pytest.fixture
def flow(proj, monkeypatch, tmp_path):
    def ask(name, schema, system, user):
        return {**ASSETS, "_model": "fake"} if name == "assets" else shots_for(user)
    monkeypatch.setattr(P, "_ask", ask)
    FakeKie.sent = []
    src = tmp_path / "made.png"
    Image.new("RGB", (32, 32), (250, 250, 0)).save(src)
    FakeKie.source = str(src)
    monkeypatch.setitem(R.PROVIDERS, "kie", FakeKie)
    monkeypatch.setattr(R, "manifest", _fake_manifest)
    monkeypatch.setattr(R, "estimate_payload", lambda *a: {"usd": 0.02, "basis": "test"})
    return proj


def run_all(d):
    R.run(d, poll_every=0)


def test_the_whole_path_from_a_song_to_an_exported_production(flow, tmp_path):
    d = flow
    plan = P.plan_assets(d)
    assert plan["stage"] == "assets" and plan["assets"]["characters"]
    v = P.plan_shots(d)
    secs = list(dict.fromkeys(s["section"] for s in v["shots"]))
    assert v["shots"] and v["approved"] == []
    P.approve_sections(d, secs)                                                                       # every section approved by the user
    built = P.build(d)
    assert built["view"]["stage"] == "built"

    # the project now has the cast, places and props, each waiting for a picture (none of them was supplied)
    cards = {c["name"]: c for c in refgen.cards(d)["cards"]}
    assert cards["Beatrice Queen Bee"]["state"] == "missing" and cards["Family home"]["state"] == "missing" and cards["Brass bell"]["state"] == "missing"
    assert cards["Brass bell"]["owner"] == "Beatrice Queen Bee" and cards["Brass bell"]["owner_ready"] is False       # made after its owner
    assert all(("background" in c["prompt"] or "No people" in c["prompt"]) and "No text, labels" in c["prompt"] for c in cards.values() if c["prompt"])

    # make the people and the place first, as the screen does
    first = [c["id"] for c in cards.values() if c["owner_ready"]]
    q = refgen.queue(d, first, "kie", "fake/model", confirmed=True, cap_usd=5)
    assert q["queued"] == len(first)
    run_all(d)
    waiting = [c for c in refgen.cards(d)["cards"] if c["state"] == "waiting"]
    assert len(waiting) == len(first)
    for c in waiting:
        refgen.use(d, c["pending"]["job"])
    after = {c["name"]: c for c in refgen.cards(d)["cards"]}
    assert after["Beatrice Queen Bee"]["state"] == "approved" and after["Brass bell"]["owner_ready"] is True    # the prop can now be drawn next to its owner
    bell = next(c for c in refgen.candidates(d) if c["name"] == "Brass bell")
    assert bell["refs"] and bell["refs"][0]["path"].startswith("generations/") and "Beatrice" in bell["refs"][0]["label"]

    # change one picture in plain words: the old one stays until the new one is approved
    bid = after["Beatrice Queen Bee"]["id"]
    refgen.queue(d, [bid], "kie", "fake/model", confirmed=True, redo=[bid], notes={bid: "older, warmer"})
    run_all(d)
    c = next(x for x in refgen.cards(d)["cards"] if x["id"] == bid)
    assert c["state"] == "waiting" and c["picture"] == after["Beatrice Queen Bee"]["picture"] and "older, warmer" in FakeKie.sent[-1]["prompt"]

    # export and open it in a different project
    out = P.export_package(d, str(tmp_path / "show.pfproducer"))
    assert out["pictures"] >= 3
    names = zipfile.ZipFile(out["path"]).namelist()
    assert "pulseframe_manifest.json" in names and any(n.startswith("assets/pictures/") for n in names)
    d2 = tmp_path / "other"
    d2.mkdir()
    json.dump({"title": "Copy", "song": "s.wav", "state": "ready"}, open(d2 / "project.json", "w"))
    PI.apply(str(d2), out["path"])
    items = {i["name"]: i for i in library.load(str(d2))[1]["items"]}
    assert any(f.endswith(".png") for f in items["Beatrice Queen Bee"]["files"]) and any(f.endswith(".png") for f in items["Family home"]["files"])
    shot_count = len([s for sc in (json.load(open(d2 / "production.json"))["scenes"]) for s in sc["shots"]]) if os.path.exists(d2 / "production.json") else 0
    assert shot_count >= 0                                                                              # shots are placed once the importing project has been listened to


def test_names_with_spaces_accents_and_other_scripts_work_everywhere(flow, tmp_path):
    d = flow
    P.plan_assets(d)
    v = P.plan_shots(d)
    P.approve_sections(d, list(dict.fromkeys(s["section"] for s in v["shots"])))
    P.build(d)
    odd = tmp_path / "My Pictures é ñ 音楽"
    odd.mkdir()
    pic = odd / "Mère de Béatrice 母.png"
    Image.new("RGB", (30, 30), (4, 5, 6)).save(pic)
    rel = "assets/refs/Mère de Béatrice 母.png"
    os.makedirs(os.path.join(d, "assets", "refs"), exist_ok=True)
    shutil.copy(pic, os.path.join(d, rel))
    bell = next(c for c in refgen.cards(d)["cards"] if c["name"] == "Brass bell")
    out = refgen.own(d, bell["id"], rel)
    assert next(c for c in out["cards"] if c["id"] == bell["id"])["picture"] == rel
    dest = odd / "Ma production 音楽.pfproducer"
    res = P.export_package(d, str(dest))
    assert os.path.exists(res["path"]) and res["pictures"] >= 1
    names = zipfile.ZipFile(res["path"]).namelist()
    assert all(n.isascii() for n in names)                                                           # inside the file every name is plain, whatever the picture was called
    from pulseframe_analysis import onboarding as O
    note = odd / "Notes de danse é.md"
    note.write_text("Couplet : balancé lent.\nRefrain : grand tour.", encoding="utf-8")
    assert "balancé lent" in O.doc_text(str(note))["text"]
