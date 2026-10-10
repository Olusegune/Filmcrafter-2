"""Making the film: the render project built from the shots and the Bible, and choosing and locking storyboard panels, keyframes and takes."""
import json
import os

import pytest

from filmcrafter_engine import bible, make, shots, story

SCRIPT = """INT. KITCHEN - MORNING

Sarah pours tea. A letter lies by the sink.

SARAH
He said he would call.

JOHN
Did you say something?

EXT. PLATFORM - NIGHT

Rain on the roof.

SARAH
I am going.
"""


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    bible.update_rules(d, {"style": {"lane": "painterly animation", "traits": "Oil paint texture"}, "rules": {"world": "A rainy town"}})
    pic = tmp_path / "sarah.png"
    pic.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 30)
    bible.add_media(d, "character", "c_sarah", str(pic), "Master", "master")
    shots.breakdown(d)
    shots.set_fields(d, "S01-02", {"performance": {"emotional_intention": "Held-back dread", "beats": [{"character": "Sarah", "what": "Holds the cup tightly", "hiding": "That she packed", "start": "Hopeful", "end": "Resolve"}]},
                                   "camera": {"framing": "over the shoulder", "angle": "low", "lens": "portrait (50mm)"}, "lighting": {"description": "Low window light"}})
    return d


def _image_job(d, sid, jid, purpose=None, state="ready", n=1):
    rd = make.render_dir(d)
    rel = f"media/{jid}.png"
    os.makedirs(os.path.join(rd, "media"), exist_ok=True)
    open(os.path.join(rd, rel), "wb").write(b"\x89PNG\r\n\x1a\n")
    path = os.path.join(rd, "jobs.json")
    data = json.load(open(path)) if os.path.exists(path) else {"schema_version": 1, "jobs": []}
    j = {"id": jid, "shot_id": sid, "plan": "production", "state": state, "kind": "image", "provider": "fal", "model": "m", "output": rel, "created": 100 + n, "updated": 100 + n, "frame": "start"}
    if purpose:
        j["purpose"] = purpose
    data["jobs"].append(j)
    json.dump(data, open(path, "w"))


def test_the_render_project_is_built_from_the_shots_and_the_bible(film):
    r = make.sync(film)
    rd = r["render_dir"]
    assert r["shots"] == len(make._contracts(film)) and r["look"] == "painterly" and r["references"] == 1
    plan = json.load(open(os.path.join(rd, "production.json")))
    shot = next(s for sc in plan["scenes"] for s in sc["shots"] if s["id"] == "S01-02")
    assert shot["framing"].startswith("Over the shoulder") and "low angle" in shot["framing"] and shot["lens"] == "portrait (50mm)" and shot["lighting"] == "Low window light"
    assert "Held-back dread" in shot["acting_beats"] and "That she packed" in shot["acting_beats"] and shot["performers"]
    assert plan["meta"]["VISUAL STYLE"].startswith("painterly animation") and plan["characters"][0]["name"] in ("Sarah", "John")
    starts = [s["start"] for sc in plan["scenes"] for s in sc["shots"]]
    assert starts == sorted(starts) and starts[0] == 0 and plan["scenes"][0]["shots"][0]["end"] > 0
    pj = json.load(open(os.path.join(rd, "project.json")))
    assert pj["aspect_ratio"] == "16:9" and pj["film"] is True
    assert any(i["name"] == "Sarah" and i["files"] for i in pj["library"]["items"])


def test_syncing_again_keeps_the_jobs_and_choices(film):
    make.sync(film)
    _image_job(film, "S01-01", "j1", "storyboard")
    make.choose(film, "S01-01", "storyboard", "j1")
    make.sync(film)
    s = make.status(film)
    assert next(x for x in s["shots"] if x["id"] == "S01-01")["storyboard"]["chosen"] == "media/j1.png"
    assert len(json.load(open(os.path.join(make.render_dir(film), "jobs.json")))["jobs"]) == 1


def test_a_film_with_no_shots_cannot_be_made(tmp_path):
    d = story.create(str(tmp_path), "T", "screenplay", SCRIPT)["dir"]
    with pytest.raises(SystemExit, match="no shots yet"):
        make.sync(d)


def test_storyboard_and_keyframe_options_are_kept_apart(film):
    make.sync(film)
    _image_job(film, "S01-01", "sb1", "storyboard", n=1)
    _image_job(film, "S01-01", "kf1", None, n=2)
    _image_job(film, "S01-01", "kf2", "keyframe", n=3, state="submitted")
    s = next(x for x in make.status(film)["shots"] if x["id"] == "S01-01")
    assert [o["job"] for o in s["storyboard"]["options"]] == ["sb1"]
    assert {o["job"] for o in s["keyframe"]["options"]} == {"kf1", "kf2"}
    assert make.status(film)["active"] == 1


def test_choosing_a_storyboard_panel_then_locking_it_protects_the_choice_and_the_framing(film):
    make.sync(film)
    _image_job(film, "S01-01", "sb1", "storyboard")
    _image_job(film, "S01-01", "sb2", "storyboard", n=2)
    with pytest.raises(SystemExit, match="Choose one first"):
        make.lock(film, "S01-01", "storyboard")
    make.choose(film, "S01-01", "storyboard", "sb1")
    s = make.lock(film, "S01-01", "storyboard")
    assert next(x for x in s["shots"] if x["id"] == "S01-01")["storyboard"]["locked"]
    with pytest.raises(SystemExit, match="locked"):
        make.choose(film, "S01-01", "storyboard", "sb2")
    with pytest.raises(SystemExit, match="storyboard is locked"):
        shots.set_fields(film, "S01-01", {"camera": {"framing": "close-up"}})
    make.lock(film, "S01-01", "storyboard", False)
    make.choose(film, "S01-01", "storyboard", "sb2")
    assert next(x for x in make.status(film)["shots"] if x["id"] == "S01-01")["storyboard"]["chosen"] == "media/sb2.png"


def test_a_keyframe_is_not_a_storyboard_panel_and_the_other_way_round(film):
    make.sync(film)
    _image_job(film, "S01-01", "sb1", "storyboard")
    _image_job(film, "S01-01", "kf1", "keyframe", n=2)
    with pytest.raises(SystemExit, match="isn't a keyframe"):
        make.choose(film, "S01-01", "keyframe", "sb1")
    with pytest.raises(SystemExit, match="isn't a storyboard"):
        make.choose(film, "S01-01", "storyboard", "kf1")
    with pytest.raises(SystemExit, match="finished one"):
        make.choose(film, "S01-01", "keyframe", "nope")


def test_choosing_a_keyframe_makes_it_the_start_of_the_video(film):
    make.sync(film)
    _image_job(film, "S01-01", "kf1", "keyframe")
    make.choose(film, "S01-01", "keyframe", "kf1")
    s = next(x for x in make.status(film)["shots"] if x["id"] == "S01-01")
    assert s["keyframe"]["chosen"] == "media/kf1.png"
    kf = json.load(open(os.path.join(make.render_dir(film), "keyframes.json")))
    assert kf["production"]["S01-01"] == "project:media/kf1.png"
    make.lock(film, "S01-01", "keyframe")
    with pytest.raises(SystemExit, match="keyframe for this shot is locked"):
        make.import_media(film, "S01-01", "keyframe", os.path.join(film, "film.json"))


def test_the_storyboard_panel_becomes_a_composition_reference_for_the_keyframe(film):
    make.sync(film)
    _image_job(film, "S01-01", "sb1", "storyboard")
    with pytest.raises(SystemExit, match="Choose a storyboard panel first"):
        make.use_storyboard_as_reference(film, "S01-01")
    make.choose(film, "S01-01", "storyboard", "sb1")
    make.use_storyboard_as_reference(film, "S01-01")
    lib = json.load(open(os.path.join(make.render_dir(film), "project.json")))["library"]
    item = next(i for i in lib["items"] if i["id"] == "fc-board-s01-01")
    assert item["files"] == ["media/sb1.png"] and "fc-board-s01-01" not in lib["assign"].get("project", [])
    assert "fc-board-s01-01" in lib["assign"]["shots"]["S01-01"]["add"]


def test_bringing_your_own_picture_or_video(film, tmp_path):
    pic = tmp_path / "board.png"
    pic.write_bytes(b"\x89PNG\r\n\x1a\n")
    s = make.import_media(film, "S01-01", "storyboard", str(pic))
    one = next(x for x in s["shots"] if x["id"] == "S01-01")
    assert one["storyboard"]["chosen"] and os.path.isfile(os.path.join(film, "storyboard", os.listdir(os.path.join(film, "storyboard"))[0])) and pic.exists()
    kf = tmp_path / "key.jpg"
    kf.write_bytes(b"\xff\xd8\xff")
    s = make.import_media(film, "S01-01", "keyframe", str(kf))
    assert next(x for x in s["shots"] if x["id"] == "S01-01")["keyframe"]["chosen"]
    bad = tmp_path / "x.exe"
    bad.write_bytes(b"MZ")
    with pytest.raises(SystemExit, match="Choose a PNG"):
        make.import_media(film, "S01-02", "storyboard", str(bad))
    with pytest.raises(SystemExit, match="can't be found"):
        make.import_media(film, "S01-02", "storyboard", str(tmp_path / "missing.png"))


def test_ids_from_outside_are_never_paths(film):
    make.sync(film)
    for bad in ("../../evil", "..\\x"):
        with pytest.raises(SystemExit, match="not valid"):
            make.choose(film, bad, "storyboard", "j")
        with pytest.raises(SystemExit, match="not valid"):
            make.lock(film, bad, "storyboard")


def test_tagging_marks_only_picture_jobs(film):
    make.sync(film)
    _image_job(film, "S01-01", "p1", None)
    s = make.tag(film, ["p1", "nope"], "storyboard")
    assert [o["job"] for o in next(x for x in s["shots"] if x["id"] == "S01-01")["storyboard"]["options"]] == ["p1"]
    with pytest.raises(SystemExit, match="Choose storyboard or keyframe"):
        make.tag(film, ["p1"], "video")


def test_the_command_line(film, capsys):
    assert make.main(["sync", film]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["event"] == "result" and out["data"]["shots"]
    assert make.main(["status", film]) == 0
    capsys.readouterr()
    assert make.main(["status", film + "-nope"]) == 1


def test_the_studio_timeline_reads_scenes_cuts_dialogue_and_the_soundtrack(film):
    make.sync(film)
    sm = json.load(open(os.path.join(make.render_dir(film), "songmap.json")))
    cons = make._contracts(film)
    assert sm["analyzer"] == "film" and abs(sm["duration"] - sum(c["generation"]["duration"] for c in cons)) < 0.05
    assert [s["label"] for s in sm["sections"]] == ["Scene 1", "Scene 2"] and sm["sections"][0]["start"] == 0 and abs(sm["sections"][-1]["end"] - sm["duration"]) < 0.05
    assert sm["downbeats"][0] == 0 and sm["downbeats"] == sorted(sm["downbeats"]) and len(sm["downbeats"]) == len(cons)      # the cuts are the grid
    assert any(l["text"].startswith("Sarah:") for l in sm["lyrics"]) and all(l["start"] < l["end"] for l in sm["lyrics"])    # the dialogue is the lane of words
    assert len(sm["peaks"]) == 2000 and set(sm["peaks"]) == {0.0}                                                            # silence is a flat line
    for k in ("beats", "energy_curve", "accents"):
        assert sm[k] == []
