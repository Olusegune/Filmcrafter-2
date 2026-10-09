"""Reference library inheritance, provider limits, migration, versions and thumbnails (no network)."""
import json
import os
import time

import pytest
from PIL import Image

from filmcrafter_engine import library as L
from filmcrafter_engine import render as R


def F(**kw):
    return {"description": "", **kw}


@pytest.fixture
def proj(tmp_path):
    d = tmp_path / "p"
    (d / "assets" / "refs").mkdir(parents=True)
    for n in ("sege", "amara", "sheet", "sets", "cup", "neon"):
        Image.new("RGB", (64, 36), (40, 60, 90)).save(d / "assets" / "refs" / f"{n}.png")
    (d / "project.json").write_text(json.dumps({"title": "T", "schema_version": 1, "references": {
        "cast": {"Sege": "assets/refs/sege.png", "Amara": "assets/refs/amara.png"},
        "characters": "assets/refs/sheet.png", "sets": "assets/refs/sets.png"}}))
    shots = [{"id": "S01-01", "start": 0, "end": 2, "performers": ["Sege"], "beats": ["x"]},
             {"id": "S01-02", "start": 2, "end": 4, "performers": [], "beats": ["y"]}]
    (d / "production.json").write_text(json.dumps({"scenes": [{"number": 1, "heading": "EXT", "shots": shots}]}))
    return str(d)


def ids(d, sid):
    p, lib = L.load(d)
    plan = json.load(open(os.path.join(d, "production.json")))
    sh = next(s for s in plan["scenes"][0]["shots"] if s["id"] == sid)
    return [i["id"] for i in L.shot_items(lib, sh, 1)]


def test_migration_keeps_old_references_and_is_idempotent(proj):
    p, lib = L.load(proj)
    assert p["schema_version"] == 2 and p["references"]["sets"] == "assets/refs/sets.png"
    assert {i["name"] for i in lib["items"]} == {"Sege", "Amara", "Character sheet", "Sets and props sheet"}
    assert L.load(proj)[1] == lib


def test_performers_bring_their_own_reference_not_the_sheet(proj):
    got = ids(proj, "S01-01")
    names = {i["id"]: i["name"] for i in L.load(proj)[1]["items"]}
    assert [names[i] for i in got] == ["Sege", "Sets and props sheet"]


def test_inheritance_project_scene_shot(proj):
    L.upsert(proj, {"kind": "prop", "name": "Coffee cup", "files": ["assets/refs/cup.png"]})
    L.upsert(proj, {"kind": "lighting", "name": "Neon", "files": ["assets/refs/neon.png"]})
    lib = L.load(proj)[1]
    cup = next(i["id"] for i in lib["items"] if i["name"] == "Coffee cup")
    neon = next(i["id"] for i in lib["items"] if i["name"] == "Neon")
    assert cup in ids(proj, "S01-02")                      # project-wide by default
    L.assign(proj, "scene", 1, cup, False)                 # scene removes it
    assert cup not in ids(proj, "S01-02")
    L.assign(proj, "shot", "S01-02", cup, True)            # a shot adds it back
    assert cup in ids(proj, "S01-02") and cup not in ids(proj, "S01-01")
    L.reset(proj, "shot", "S01-02", cup)
    assert cup not in ids(proj, "S01-02")
    L.delete(proj, neon)
    assert neon not in ids(proj, "S01-02")


def test_provider_limits_keep_priority_order():
    refs = [{"label": "character a", "media": "image"}, {"label": "character b", "media": "image"},
            {"label": "set", "media": "image"}, {"label": "move", "media": "video"}]
    kept, dropped = L.fit_to_model(refs, {"image": 2, "video": 0, "audio": 0})
    assert [r["label"] for r in kept] == ["character a", "character b"] and dropped == ["set", "move"]


def test_ref_limits_account_for_the_keyframe():
    m = R._finish("fal", "x", "X", "", [F(**{"name": "prompt", "type": "string"}), F(**{"name": "image_urls", "type": "array", "max_items": 4}),
                                        F(**{"name": "duration", "type": "string", "enum": ["5"]})])
    assert R.ref_limits(m, keyframe=True)["image"] == 3 and R.ref_limits(m, keyframe=False)["image"] == 4
    m2 = R._finish("fal", "x", "X", "", [F(**{"name": "prompt", "type": "string"}), F(**{"name": "image_url", "type": "string"}),
                                         F(**{"name": "duration", "type": "string", "enum": ["5"]})])
    assert R.ref_limits(m2, keyframe=True)["image"] == 0 and R.ref_limits(m2, keyframe=False)["image"] == 1
    assert m2["caps"]["first_frame"] and m2["caps"]["kind"] == "video"


def _job(d, jid, state="ready", created=1, kind="video"):
    out = f"generations/S01-01__{jid}.png"
    os.makedirs(os.path.join(d, "generations"), exist_ok=True)
    Image.new("RGB", (32, 18)).save(os.path.join(d, out))
    return {"id": jid, "shot_id": "S01-01", "plan": "production", "state": state, "output": out if state == "ready" else None,
            "created": created, "kind": kind, "provider": "fal", "model": "m"}


def test_versions_regenerating_keeps_the_approved_take(proj):
    jobs = [_job(proj, "a", created=1), _job(proj, "b", created=2)]
    json.dump({"jobs": jobs}, open(os.path.join(proj, "jobs.json"), "w"))
    assert L.chosen_take(proj, "S01-01", "production", jobs)["id"] == "b"   # nothing approved: latest
    L.approve(proj, "S01-01", "a")
    assert L.chosen_take(proj, "S01-01", "production", jobs)["id"] == "a"   # approved wins over newer
    sb = {s["id"]: s for s in L.storyboard(proj)["shots"]}
    assert sb["S01-01"]["status"] == "ready" and sb["S01-01"]["thumb_source"] == "render"
    jobs.append({**_job(proj, "c", created=int(time.time()) + 5)})   # a new take arrives after the choice
    json.dump({"jobs": jobs}, open(os.path.join(proj, "jobs.json"), "w"))
    assert L.storyboard(proj)["shots"][0]["status"] == "needs_review"
    assert L.chosen_take(proj, "S01-01", "production", jobs)["id"] == "a"
    assert sb["S01-02"]["status"] == "planned" and sb["S01-02"]["thumb_source"] == "placeholder"
    L.set_shot(proj, "S01-01", locked=True)
    with pytest.raises(SystemExit):
        L.approve(proj, "S01-01", "b")
    assert L.storyboard(proj)["shots"][0]["status"] == "locked"


def test_locked_shots_are_not_requeued(proj, monkeypatch):
    L.set_shot(proj, "S01-01", locked=True)
    m = R._finish("fal", "test/model", "T", "", [F(**{"name": "prompt", "type": "string"})])
    monkeypatch.setattr(R, "manifest", lambda *a, **k: m)
    assert R.enqueue(proj, ["S01-01"], "fal", "test/model", {}) == []


def test_thumbnails_are_cached(proj):
    t1 = L.thumbnail(proj, "assets/refs/sege.png")
    t2 = L.thumbnail(proj, "assets/refs/sege.png")
    assert t1 == t2 and os.path.exists(os.path.join(proj, t1))
    assert L.thumbnail(proj, "missing.png") is None


def test_materials_checklist_additions_reach_the_library(proj):
    L.load(proj)
    p = json.load(open(os.path.join(proj, "project.json")))
    p["references"]["cast"]["Young Sege"] = "assets/refs/cup.png"
    json.dump(p, open(os.path.join(proj, "project.json"), "w"))
    assert "Young Sege" in {i["name"] for i in L.load(proj)[1]["items"]}


def test_keyframes_never_get_the_sets_sheet(proj):
    from filmcrafter_engine import render as R
    p = json.load(open(os.path.join(proj, "project.json")))
    shot = {"id": "S01-01", "performers": ["Sege"]}
    files = R._reference_files(proj, p, shot)
    assert any(f["label"].startswith("set and props") for f in files)       # videos still get it
    assert all(not f["label"].startswith("set and props") for f in files
               if not f["label"].startswith("set and props"))                # label is what the image filter keys on


def test_approve_all_keyframes_keeps_existing_approvals(proj):
    jobs = [_job(proj, "k1", created=1, kind="image"), _job(proj, "k2", created=2, kind="image")]
    json.dump({"jobs": jobs}, open(os.path.join(proj, "jobs.json"), "w"))
    assert L.pending_keyframes(proj) == {"S01-01": jobs[1]["output"]}
    assert L.approve_keyframes(proj) == {"approved": ["S01-01"]}
    kf = json.load(open(os.path.join(proj, "keyframes.json")))["production"]
    assert kf["S01-01"] == "project:" + jobs[1]["output"]
    json.dump({"jobs": jobs + [_job(proj, "k3", created=3, kind="image")]}, open(os.path.join(proj, "jobs.json"), "w"))
    assert L.approve_keyframes(proj) == {"approved": []}      # never replaces an approved keyframe


def test_sheets_are_not_sent_when_a_keyframe_sets_the_scene(proj, monkeypatch):
    from filmcrafter_engine import render as R
    p = json.load(open(os.path.join(proj, "project.json")))
    files = R._reference_files(proj, p, {"id": "S01-01", "performers": ["Sege"]})
    assert any(f["sheet"] for f in files) and any(not f["sheet"] for f in files)
    kf = [f for f in files if not f["sheet"]]
    assert all(f["label"].startswith("reference for") for f in kf)


def test_keyframe_options_choose_and_reject(proj):
    jobs = [_job(proj, "k1", created=1, kind="image"), _job(proj, "k2", created=2, kind="image"),
            {**_job(proj, "k3", created=3, kind="image"), "state": "queued", "output": None}]
    json.dump({"jobs": jobs}, open(os.path.join(proj, "jobs.json"), "w"))
    o = L.keyframe_options(proj, ["S01-01", "S01-02"])
    assert [x["job"] for x in o["S01-01"]["options"]] == ["k2", "k1"] and o["S01-01"]["active"] == 1
    assert o["S01-01"]["chosen"] is None and o["S01-02"]["options"] == []
    L.set_keyframe_flag(proj, "k2", rejected=True)                   # a rejected still is never picked automatically
    assert L.pending_keyframes(proj) == {"S01-01": jobs[0]["output"]}
    L.choose_keyframe(proj, "S01-01", "k2")                          # ...but you can still choose it yourself
    assert L.keyframe_options(proj, ["S01-01"])["S01-01"]["chosen"] == jobs[1]["output"]
    assert not json.load(open(os.path.join(proj, "jobs.json")))["jobs"][1]["rejected"]
    L.choose_keyframe(proj, "S01-01", "k1")                          # changing your mind replaces the choice, keeps the files
    assert L.keyframe_options(proj, ["S01-01"])["S01-01"]["chosen"] == jobs[0]["output"]
    assert os.path.exists(os.path.join(proj, jobs[1]["output"]))
    with pytest.raises(SystemExit):
        L.choose_keyframe(proj, "S01-01", "k3")                      # not finished yet
    L.set_shot(proj, "S01-01", locked=True)
    with pytest.raises(SystemExit, match="locked"):
        L.choose_keyframe(proj, "S01-01", "k2")


def test_keyframe_variants_queue_several_options_once(proj, monkeypatch):
    m = R._finish("fal", "test/model", "T", "", [F(**{"name": "prompt", "type": "string"})])
    monkeypatch.setattr(R, "manifest", lambda *a, **k: m)
    monkeypatch.setattr("filmcrafter_engine.routing.guard", lambda *a, **k: None)
    made = R.enqueue(proj, ["S01-01"], "fal", "test/model", {"_variants": 3}, kind="image")
    assert len(made) == 3 and all("_variants" not in j["overrides"] for j in made)
    assert R.enqueue(proj, ["S01-01"], "fal", "test/model", {"_variants": 3}, kind="image") == []   # never doubled
    assert len(R.enqueue(proj, ["S01-02"], "fal", "test/model", {"_variants": 3}, kind="video")) == 1  # videos: one take
