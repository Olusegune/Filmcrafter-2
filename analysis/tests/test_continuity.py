import json
import os
import subprocess

import pytest
from PIL import Image

from filmcrafter_engine import continuity as C
from filmcrafter_engine import export, media


def _project(tmp_path):
    d = tmp_path / "P"
    d.mkdir()
    shots = [
        {"id": "S01-01", "scene": 1, "start": 0, "end": 2, "performers": ["Ada", "Ben"], "framing": "wide two-shot", "beats": ["a"]},
        {"id": "S01-02", "scene": 1, "start": 2, "end": 4, "performers": ["Ada"], "framing": "close-up", "beats": ["b"]},
        {"id": "S01-03", "scene": 1, "start": 4, "end": 6, "performers": ["Ada"], "framing": "tight close up", "beats": ["c"]},
    ]
    plan = {"meta": {}, "characters": [], "scenes": [{"number": 1, "heading": "KITCHEN", "notes": {"CONTINUITY": "Ada wears a red scarf"},
                                                       "shots": shots}]}
    (d / "production.json").write_text(json.dumps(plan))
    (d / "project.json").write_text(json.dumps({"title": "P", "song": "song.wav"}))
    (d / "jobs.json").write_text(json.dumps({"jobs": []}))
    return str(d), shots


def test_derive_blocks_leads_facing_each_other_and_keeps_edits(tmp_path):
    d, _ = _project(tmp_path)
    b = C.derive(d)["scenes"]["1"]["blocking"]
    assert b == {"Ada": {"side": "left", "facing": "right"}, "Ben": {"side": "right", "facing": "left"}}
    C.set_scene(d, "1", {"blocking": {"Ada": {"side": "right", "facing": "left"}, "Ben": {"side": "left", "facing": "right"}}})
    assert C.derive(d)["scenes"]["1"]["blocking"]["Ada"]["side"] == "right"   # user edit survives
    with pytest.raises(SystemExit):
        C.set_scene(d, "1", {"blocking": {"Ada": {"side": "up", "facing": "left"}}})


def test_direction_has_axis_eyeline_and_wardrobe(tmp_path):
    d, shots = _project(tmp_path)
    assert C.direction(d, shots[1]) == ""          # nothing until continuity is set up
    C.derive(d)
    t = C.direction(d, shots[1])
    assert "Ada screen-left facing right" in t and "180-degree" in t
    assert "Ada looks screen-right toward Ben (off-screen)" in t and "red scarf" in t


def test_prompt_carries_continuity(tmp_path):
    from filmcrafter_engine import render as R
    d, shots = _project(tmp_path)
    C.derive(d)
    shot = R._with_movement(d, shots[0])
    man = {"roles": {"prompt": "prompt", "duration": "duration"}, "inputs": [{"name": "prompt", "type": "string", "required": True},
           {"name": "duration", "type": "string", "enum": ["5"]}], "model": "m", "title": "m"}
    p = R.compile_request(shot, None, {"meta": {}}, {"look": {"style": "auto"}}, man, [])["prompt"]
    assert "180-degree rule" in p


def test_rules_find_jump_cut_and_missing_reference(tmp_path):
    d, _ = _project(tmp_path)
    C.derive(d)
    kinds = {(i["shot"], i["kind"]) for i in C.check(d)["issues"]}
    assert ("S01-03", "jump cut") in kinds
    C.set_shot(d, "S01-03", {"continuous": True})
    kinds = {(i["shot"], i["kind"]) for i in C.check(d)["issues"]}
    assert ("S01-03", "jump cut") not in kinds and ("S01-03", "first frame") in kinds


def test_previous_keyframe_reference_needs_setup(tmp_path):
    d, _ = _project(tmp_path)
    img = tmp_path / "k.png"
    Image.new("RGB", (64, 36), (9, 9, 9)).save(img)
    media.import_media(d, "S01-01", str(img), role="keyframe")
    assert C.previous_keyframe(d, "production", json.load(open(os.path.join(d, "production.json"))), "S01-02") is None
    C.derive(d)
    p = C.previous_keyframe(d, "production", json.load(open(os.path.join(d, "production.json"))), "S01-02")
    assert p and p.endswith(".png")


def test_chain_takes_last_frame_of_previous_clip(tmp_path):
    d, _ = _project(tmp_path)
    clip = str(tmp_path / "c.mp4")
    subprocess.run([export.ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:size=160x90:rate=24:duration=1",
                    "-pix_fmt", "yuv420p", clip], check=True)
    media.import_media(d, "S01-01", clip)
    r = C.chain(d, "S01-02")
    assert r["from"] == "S01-01" and os.path.exists(os.path.join(d, r["keyframe"]))
    px = Image.open(os.path.join(d, r["keyframe"])).convert("RGB").getpixel((10, 10))
    assert px[0] > 200 and px[1] < 60
    kf = json.load(open(os.path.join(d, "keyframes.json")))["production"]["S01-02"]
    assert "_from_S01-01" in kf and C.load(d)["shots"]["S01-02"]["continuous"]
    with pytest.raises(SystemExit):
        C.chain(d, "S01-01")    # first shot of the scene
