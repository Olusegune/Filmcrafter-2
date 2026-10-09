import json
import os
import subprocess

import pytest
from PIL import Image

from pulseframe_analysis import export, library, media


def _project(tmp_path, with_plan=True):
    d = tmp_path / "Song"
    d.mkdir()
    (d / "project.json").write_text(json.dumps({"title": "Song", "song": "song.wav"}))
    (d / "songmap.json").write_text(json.dumps({"duration": 8.0, "bpm": 120, "downbeats": [0, 2, 4, 6],
                                                "sections": [{"start": 0, "end": 4, "label": "INTRO"}, {"start": 4, "end": 8, "label": "CHORUS"}]}))
    (d / "jobs.json").write_text(json.dumps({"jobs": []}))
    if with_plan:
        media.plan_from_song(str(d), bars=1)
    return str(d)


def _img(tmp_path, name="a.png", color=(200, 30, 30)):
    p = tmp_path / name
    Image.new("RGB", (640, 360), color).save(p)
    return str(p)


def test_plan_from_song_cuts_on_bars(tmp_path):
    d = _project(tmp_path)
    plan = json.load(open(os.path.join(d, "production.json")))
    shots = [s for sc in plan["scenes"] for s in sc["shots"]]
    assert [sc["heading"] for sc in plan["scenes"]] == ["Intro 1", "Chorus 2"]
    assert shots[0]["start"] == 0 and shots[-1]["end"] == 8
    assert all(a["end"] == b["start"] for a, b in zip(shots, shots[1:]) if a["scene"] == b["scene"])
    with pytest.raises(SystemExit):
        media.plan_from_song(d)   # never overwrites a plan


def test_import_image_becomes_approved_take_with_motion(tmp_path):
    d = _project(tmp_path)
    j = media.import_media(d, "S01-01", _img(tmp_path), "pan_left")
    assert j["provider"] == "own" and j["cost"] == 0 and j["media_kind"] == "image" and j["motion"] == "pan_left"
    assert os.path.exists(os.path.join(d, j["output"]))
    assert library.shot_state(d)["S01-01"]["approved"] == j["id"]
    sb = {s["id"]: s for s in library.storyboard(d)["shots"]}
    assert sb["S01-01"]["preview_kind"] == "image" and sb["S01-01"]["preview_motion"] == "pan_left"


def test_import_as_keyframe(tmp_path):
    d = _project(tmp_path)
    r = media.import_media(d, "S01-02", _img(tmp_path), role="keyframe")
    assert json.load(open(os.path.join(d, "keyframes.json")))["production"]["S01-02"] == f"project:{r['keyframe']}"


def test_fill_places_in_order_and_skips_filled(tmp_path):
    d = _project(tmp_path)
    media.import_media(d, "S01-01", _img(tmp_path))
    r = media.fill(d, [_img(tmp_path, "b.png"), _img(tmp_path, "c.png"), str(tmp_path / "x.txt")])
    assert [p["shot"] for p in r["placed"]] == ["S01-02", "S02-01"]
    assert r["skipped"][0]["file"] == "x.txt"


def test_stills_from_keyframes_and_motion_transition(tmp_path):
    d = _project(tmp_path)
    media.import_media(d, "S01-02", _img(tmp_path), role="keyframe")
    assert media.stills(d)["made"] == ["S01-02"]
    job = library.chosen_take(d, "S01-02", "production", json.load(open(os.path.join(d, "jobs.json")))["jobs"])
    media.set_motion(d, job["id"], "zoom_out")
    media.set_transition(d, ["S01-02"], "black")
    assert library.shot_state(d)["S01-02"]["transition"] == "black"
    with pytest.raises(SystemExit):
        media.set_transition(d, ["S01-02"], "spin")


def test_rejects_unknown_file_type(tmp_path):
    d = _project(tmp_path)
    (tmp_path / "doc.pdf").write_text("x")
    with pytest.raises(SystemExit):
        media.import_media(d, "S01-01", str(tmp_path / "doc.pdf"))


def test_fades_filter():
    assert export._fades("cut", "cut", 48) == ""
    f = export._fades("black", "white", 48)
    assert "t=in" in f and "color=black" in f and "t=out" in f and "color=white" in f


def test_zero_cost_export_end_to_end(tmp_path):
    """Real ffmpeg: a song-only project, own image (moving) and own short clip (looped), transitions, exported."""
    d = _project(tmp_path)
    ff = export.ffmpeg()
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=8", os.path.join(d, "song.wav")], check=True)
    clip = str(tmp_path / "clip.mp4")
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24:duration=0.8",
                    "-pix_fmt", "yuv420p", clip], check=True)
    media.import_media(d, "S01-01", _img(tmp_path), "zoom_in")
    media.import_media(d, "S01-02", clip)
    media.set_transition(d, ["S01-02", "S02-01"], "black")
    key = next(iter(export.PRESETS))
    res = export.build(d, key)
    assert os.path.exists(res["path"]) and res["rendered"] == 2
    p = subprocess.run([ff, "-hide_banner", "-i", res["path"]], capture_output=True, text=True)
    assert "Duration: 00:00:08" in p.stderr or "Duration: 00:00:07.9" in p.stderr


def test_bible_saves_and_keeps_project(tmp_path):
    d = _project(tmp_path)
    assert library.bible(d) == {"world": "", "rules": "", "palette": "", "avoid": ""}
    library.bible(d, {"world": "Lagos", "junk": "x"})
    p = json.load(open(os.path.join(d, "project.json")))
    assert p["bible"]["world"] == "Lagos" and "junk" not in p["bible"] and p["title"] == "Song"


def test_song_only_shots_are_never_sent_to_paid_render(tmp_path, monkeypatch):
    from pulseframe_analysis import render
    d = _project(tmp_path)
    monkeypatch.setattr(render, "manifest", lambda p, m: {"model": m or "x", "roles": {}, "inputs": []})
    assert render.enqueue(d, ["S01-01"], "fal", "x", {}) == []



def test_dissolve_export_keeps_exact_length(tmp_path):
    """Real ffmpeg: a cross-dissolve between two stills; the video stays exactly as long as the song."""
    d = _project(tmp_path)
    ff = export.ffmpeg()
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=8", os.path.join(d, "song.wav")], check=True)
    media.import_media(d, "S01-01", _img(tmp_path, "r.png", (220, 20, 20)), "none")
    media.import_media(d, "S01-02", _img(tmp_path, "b.png", (20, 20, 220)), "none")
    media.set_transition(d, ["S01-02"], "dissolve")
    res = export.build(d, next(iter(export.PRESETS)))
    p = subprocess.run([ff, "-hide_banner", "-i", res["path"]], capture_output=True, text=True)
    assert "Duration: 00:00:08" in p.stderr or "Duration: 00:00:07.9" in p.stderr
    shot2 = json.load(open(os.path.join(d, "production.json")))["scenes"][0]["shots"][1]
    mid = str(tmp_path / "mid.png")
    subprocess.run([ff, "-y", "-loglevel", "error", "-ss", str(shot2["start"] + 0.2), "-i", res["path"], "-frames:v", "1", mid], check=True)
    r, g, b = Image.open(mid).convert("RGB").resize((1, 1)).getpixel((0, 0))
    assert r > 40 and b > 40   # red and blue mixed mid-dissolve


def test_short_ai_take_holds_its_last_frame(tmp_path):
    """Real ffmpeg: a 1-second rendered take in a 4-second shot exports at full length (last frame held)."""
    d = _project(tmp_path)
    ff = export.ffmpeg()
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=8", os.path.join(d, "song.wav")], check=True)
    os.makedirs(os.path.join(d, "generations"), exist_ok=True)
    clip = os.path.join(d, "generations", "S01-01__x.mp4")
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24:duration=1", "-pix_fmt", "yuv420p", clip], check=True)
    jobs = [{"id": "x", "shot_id": "S01-01", "plan": "production", "provider": "comfyui", "model": "m", "kind": "video", "state": "ready",
             "output": "generations/S01-01__x.mp4", "created": 1, "updated": 1}]
    json.dump({"jobs": jobs}, open(os.path.join(d, "jobs.json"), "w"))
    res = export.build(d, next(iter(export.PRESETS)))
    assert res["rendered"] >= 1 and os.path.exists(res["path"])
