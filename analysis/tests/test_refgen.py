"""Making the pictures a package only described: candidates, price gate, jobs, download check, and choosing the result. No network."""
import json
import os
import shutil

import pytest
from PIL import Image

from filmcrafter_engine import library, producer_import as PI, refgen, render as R
from tests.test_producer_import import _project

SPEC = """# Solomon

LOCKED IDENTITY
64; deep brown skin; tall lean build.

VISUAL GENERATION PROMPT
Stylized 3D feature animation. White background character sheet of Solomon: oval face, round glasses.
Second line of the same paragraph.

STATUS
Written design lock.
"""
PROP_SPEC = "# Bell\n\nPROMPT\nProp reference sheet on white: small brass handbell.\n\nNOTES\nignored"


def _package(tmp_path):
    pk = tmp_path / "pkg"
    (pk / "assets").mkdir(parents=True)
    Image.new("RGB", (64, 64), (10, 200, 10)).save(pk / "assets" / "CAST.png")
    Image.new("RGB", (64, 64), (200, 10, 10)).save(pk / "assets" / "CARA.png")
    Image.new("RGB", (64, 64), (10, 10, 200)).save(pk / "assets" / "HOME.png")
    (pk / "assets" / "SOLOMON_SPEC.md").write_text(SPEC, encoding="utf-8")
    (pk / "assets" / "ADA_SPEC.md").write_text(SPEC.replace("Solomon", "Ada"), encoding="utf-8")
    (pk / "assets" / "BELL_SPEC.md").write_text(PROP_SPEC, encoding="utf-8")
    m = {"schema_version": "1.0", "project": {"id": "p", "title": "T", "visual_style": "3D"}, "song": {},
         "assets": {"characters": [{"id": "c_sol", "name": "Solomon", "kind": "character", "files": ["assets/SOLOMON_SPEC.md", "assets/CAST.png"]},
                                   {"id": "c_ada", "name": "Ada", "kind": "character", "files": ["assets/ADA_SPEC.md", "assets/CAST.png"]},
                                   {"id": "c_cara", "name": "Cara", "kind": "character", "files": ["assets/CARA.png"]}],
                    "environments": [{"id": "e_home", "name": "Home", "kind": "environment", "files": ["assets/HOME.png"]}],
                    "wardrobe": [{"id": "w_ada", "name": "Ada outfit", "kind": "wardrobe", "owner_character_id": "c_ada", "files": ["assets/ADA_SPEC.md"]}],
                    "props": [{"id": "p_bell", "name": "Bell", "kind": "prop", "locked_rules": ["18 cm brass"], "files": ["assets/BELL_SPEC.md"]},
                              {"id": "p_cup", "name": "Coffee cup", "kind": "prop", "locked_rules": ["white ceramic mug"], "files": []}],
                    "references": []},
         "choreography": [], "shots": [], "continuity": {}, "qa": {}}
    (pk / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    return str(pk)


@pytest.fixture
def proj(tmp_path):
    d = _project(tmp_path)
    PI.apply(d, _package(tmp_path))
    return d


def test_the_prompt_comes_from_the_specs_own_section():
    item = {"files": ["x.md"]}
    d = os.path.dirname(__file__)
    assert refgen.spec_prompt(d, {"files": []}) is None
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        open(os.path.join(t, "a.md"), "w", encoding="utf-8").write(SPEC)
        open(os.path.join(t, "b.md"), "w", encoding="utf-8").write(PROP_SPEC)
        open(os.path.join(t, "c.md"), "w", encoding="utf-8").write("# nothing here")
        assert refgen.spec_prompt(t, {"files": ["a.md"]}).startswith("Stylized 3D feature animation. White background character sheet of Solomon")
        assert "Second line of the same paragraph." in refgen.spec_prompt(t, {"files": ["a.md"]}) and "STATUS" not in refgen.spec_prompt(t, {"files": ["a.md"]})
        assert refgen.spec_prompt(t, {"files": ["b.md"]}) == "Prop reference sheet on white: small brass handbell."
        assert refgen.spec_prompt(t, {"files": ["c.md"]}) is None
        assert refgen.spec_prompt(t, {"files": ["../" + os.path.basename(t) + "/a.md"]}) is not None      # inside the project: fine
        assert refgen.spec_prompt(t, {"files": ["../../../../Windows/win.ini"]}) is None                    # outside it: never read
    assert item


def test_only_what_is_really_missing_is_offered(proj):
    c = {x["name"]: x for x in refgen.candidates(proj)}
    assert set(c) == {"Solomon", "Ada", "Bell", "Coffee cup"}                  # Cara and Home have pictures; Ada's outfit is on her sheet
    assert c["Solomon"]["reason"] == "only a group picture" and c["Bell"]["reason"] == "no picture"
    assert c["Solomon"]["prompt_from"] == "the spec's own prompt" and c["Coffee cup"]["prompt_from"] == "built from the item's notes"
    assert "white ceramic mug" in c["Coffee cup"]["prompt"] and "No text, labels" in c["Coffee cup"]["prompt"]
    assert c["Solomon"]["refs"] and c["Solomon"]["refs"][0]["path"].endswith("CAST.png") and not c["Bell"]["refs"]
    assert [x["kind"] for x in refgen.candidates(proj)] == ["character", "character", "prop", "prop"]       # people first


def test_nothing_is_queued_without_the_price_being_confirmed(proj):
    ids = [c["id"] for c in refgen.candidates(proj)]
    with pytest.raises(SystemExit, match="Confirm the price"):
        refgen.queue(proj, ids, "kie", "m", confirmed=False)
    assert not [j for j in R.Store(proj).jobs if j.get("kind") == "asset"]
    with pytest.raises(SystemExit, match="at most"):
        refgen.queue(proj, ids * 30, "kie", "m", confirmed=True)


def test_local_first_and_the_project_budget_are_respected(proj, monkeypatch):
    ids = [c["id"] for c in refgen.candidates(proj)][:2]
    monkeypatch.setattr(refgen, "estimate", lambda d, i, p, m, *a: {"count": 2, "usd": 5.0, "model": "m", "title": "M"})
    p = json.load(open(os.path.join(proj, "project.json")))
    p["routing"] = {"mode": "local"}
    json.dump(p, open(os.path.join(proj, "project.json"), "w"))
    with pytest.raises(SystemExit, match="Local First"):
        refgen.queue(proj, ids, "kie", "m", confirmed=True)
    p["routing"] = {"mode": "balanced", "budget_usd": 3}
    json.dump(p, open(os.path.join(proj, "project.json"), "w"))
    with pytest.raises(SystemExit, match="Over budget"):
        refgen.queue(proj, ids, "kie", "m", confirmed=True)


class FakeKie:
    name = "kie"
    sent = []
    source = None
    n = 0

    def upload(self, path):
        return "https://files/" + os.path.basename(path)

    def submit(self, model, payload):
        FakeKie.sent.append(payload)
        return {"id": f"task{len(FakeKie.sent)}"}

    def poll(self, model, rid, meta=None):
        FakeKie.n += 1
        copy = f"{FakeKie.source}.{FakeKie.n}.png"                  # the runner moves the file it is given
        shutil.copy(FakeKie.source, copy)
        return {"state": "done", "url": "file:" + copy, "cost": 4, "cost_unit": "credits"}


def _fake_manifest(provider, model, refresh=False):
    fields = [{"name": "prompt", "type": "string", "required": True, "items": None, "enum": None, "default": None, "minimum": None, "maximum": None,
               "max_items": None, "max_length": None, "description": ""},
              {"name": "image_urls", "type": "array", "items": "string", "enum": None, "default": None, "minimum": None, "maximum": None,
               "max_items": 4, "max_length": None, "description": "", "required": False},
              {"name": "aspect_ratio", "type": "string", "enum": ["1:1", "3:2", "16:9"], "default": None, "minimum": None, "maximum": None,
               "max_items": None, "max_length": None, "description": "", "required": False, "items": None}]
    return R._finish("kie", "fake/model", "Fake model", "image-to-image", fields)


@pytest.fixture
def wired(proj, monkeypatch, tmp_path):
    FakeKie.sent = []
    src = tmp_path / "made.png"
    Image.new("RGB", (32, 32), (250, 250, 0)).save(src)
    FakeKie.source = str(src)
    monkeypatch.setitem(R.PROVIDERS, "kie", FakeKie)
    monkeypatch.setattr(R, "manifest", _fake_manifest)
    monkeypatch.setattr(R, "estimate_payload", lambda *a: {"usd": 0.02, "basis": "test"})
    return proj


def test_a_picture_is_made_downloaded_checked_and_only_then_chosen(wired):
    cands = {c["name"]: c for c in refgen.candidates(wired)}
    res = refgen.queue(wired, [cands["Solomon"]["id"], cands["Bell"]["id"]], "kie", "fake/model", confirmed=True)
    assert res["queued"] == 2 and res["estimate"]["count"] == 2
    R.run(wired, poll_every=0)
    st = refgen.status(wired)
    jobs = {j["asset_name"]: j for j in st["jobs"]}
    assert jobs["Solomon"]["state"] == "ready" and jobs["Bell"]["state"] == "ready" and jobs["Solomon"]["cost"] == 4
    out = os.path.join(wired, jobs["Solomon"]["output"])
    assert os.path.exists(out) and os.path.dirname(out).endswith("generations") and ":" not in os.path.basename(out)
    sent = {p["prompt"][:30]: p for p in FakeKie.sent}
    sol = next(p for p in FakeKie.sent if "Solomon" in p["prompt"])
    assert "No text, labels" in sol["prompt"] and sol["aspect_ratio"] == "3:2" and sol["image_urls"] == ["https://files/CAST.png"]
    bell = next(p for p in FakeKie.sent if "handbell" in p["prompt"])
    assert "image_urls" not in bell and bell["aspect_ratio"] == "1:1"                           # a prop gets no group picture to copy
    assert sent
    # nothing changed in the library until the picture is chosen
    before = {i["name"]: i["files"] for i in library.load(wired)[1]["items"]}
    assert any(f.endswith("CAST.png") for f in before["Solomon"])
    refgen.use(wired, jobs["Solomon"]["id"])
    after = {i["name"]: i["files"] for i in library.load(wired)[1]["items"]}
    assert after["Solomon"][0] == jobs["Solomon"]["output"] and not any(f.endswith("CAST.png") for f in after["Solomon"])
    assert any(f.endswith("SOLOMON_SPEC.md") for f in after["Solomon"])                          # his written spec stays
    assert any(f.endswith("CAST.png") for f in after["Ada"])                                     # the group picture stays for everyone else
    assert [c["name"] for c in refgen.candidates(wired)].count("Solomon") == 0                  # and he is no longer missing a picture


def test_something_that_is_not_a_picture_is_never_offered(wired, tmp_path):
    bad = tmp_path / "html.png"
    bad.write_text("<html>not an image</html>")
    FakeKie.source = str(bad)
    cid = next(c["id"] for c in refgen.candidates(wired) if c["name"] == "Bell")
    refgen.queue(wired, [cid], "kie", "fake/model", confirmed=True)
    R.run(wired, poll_every=0)
    j = refgen.status(wired)["jobs"][0]
    assert j["state"] == "failed" and "isn't a picture" in j["error"]
    assert not [f for f in os.listdir(os.path.join(wired, "generations")) if f.startswith("asset_")]
    with pytest.raises(SystemExit, match="isn't ready"):
        refgen.use(wired, j["id"])


def test_the_same_picture_is_not_queued_twice_and_a_discarded_one_is_hidden(wired):
    cid = next(c["id"] for c in refgen.candidates(wired) if c["name"] == "Bell")
    assert refgen.queue(wired, [cid], "kie", "fake/model", confirmed=True)["queued"] == 1
    assert refgen.queue(wired, [cid], "kie", "fake/model", confirmed=True)["queued"] == 0
    R.run(wired, poll_every=0)
    jid = refgen.status(wired)["jobs"][0]["id"]
    refgen.discard(wired, jid)
    assert refgen.status(wired)["jobs"] == []


def _model_manifests(provider, model, refresh=False):
    """An editing model that refuses a request with no input picture, and its text-to-image sibling."""
    base = {"name": "prompt", "type": "string", "required": True, "items": None, "enum": None, "default": None, "minimum": None, "maximum": None,
            "max_items": None, "max_length": None, "description": ""}
    edit_in = {**base, "name": "image_urls", "type": "array", "items": "string", "max_items": 4, "required": True}
    if model.endswith("-edit") or model.endswith("image-to-image"):
        return R._finish("kie", model, "Edit " + model, "image-to-image", [base, edit_in])
    if model in ("g/nano-banana", "gpt/x-text-to-image"):
        return R._finish("kie", model, "Text " + model, "text-to-image", [base])
    raise SystemExit(f"Kie model not found: {model}")


def test_a_picture_with_nothing_to_edit_uses_the_text_to_image_version(monkeypatch):
    monkeypatch.setattr(R, "manifest", _model_manifests)
    assert refgen.effective_model("kie", "g/nano-banana-edit", has_refs=False) == "g/nano-banana"          # a prop: no picture to edit
    assert refgen.effective_model("kie", "g/nano-banana-edit", has_refs=True) == "g/nano-banana-edit"       # a character: the group picture to match
    assert refgen.effective_model("kie", "gpt/x-image-to-image", has_refs=False) == "gpt/x-text-to-image"
    assert refgen.effective_model("kie", "g/nano-banana", has_refs=False) == "g/nano-banana"                # already text-to-image
    assert refgen.effective_model("kie", "other/model-edit", has_refs=False) == "other/model-edit"          # no sibling: kept, and its own check explains


def test_each_picture_is_queued_on_the_model_that_can_make_it_and_priced_that_way(proj, monkeypatch):
    monkeypatch.setattr(R, "manifest", _model_manifests)
    monkeypatch.setattr(R, "estimate_payload", lambda *a: {"usd": 0.03, "basis": "test"})
    monkeypatch.setattr(R, "kie_cost_memory", lambda: {"g/nano-banana-edit": 4})
    cands = {c["name"]: c for c in refgen.candidates(proj)}
    est = refgen.estimate(proj, [cands["Solomon"]["id"], cands["Bell"]["id"]], "kie", "g/nano-banana-edit")
    assert {u["model"]: u["count"] for u in est["uses"]} == {"g/nano-banana-edit": 1, "g/nano-banana": 1}
    assert est["kie_credits_est"] == 8                                       # the text version is priced like the edit one when it has no history
    refgen.queue(proj, [cands["Solomon"]["id"], cands["Bell"]["id"]], "kie", "g/nano-banana-edit", confirmed=True)
    jobs = {j["asset_name"]: j for j in R.Store(proj).jobs if j.get("kind") == "asset"}
    assert jobs["Solomon"]["model"] == "g/nano-banana-edit" and jobs["Bell"]["model"] == "g/nano-banana"
