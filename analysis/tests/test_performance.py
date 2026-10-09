import json
import os
import subprocess

import pytest
from PIL import Image

from filmcrafter_engine import export, media
from filmcrafter_engine import performance as P
from filmcrafter_engine import render as R


def _man(video=True):
    ins = [{"name": "prompt", "type": "string", "required": True}]
    roles = {"prompt": "prompt"}
    if video:
        ins.append({"name": "duration", "type": "string", "enum": ["5"]})
        roles["duration"] = "duration"
    return {"roles": roles, "inputs": ins, "model": "m", "title": "m"}


SHOT = {"id": "S01-02", "scene": 1, "start": 0, "end": 2, "beats": ["She waits."], "performers": ["Ada"],
        "emotion": "dread", "performance_intensity": 6}


def test_no_profile_leaves_prompts_unchanged():
    p = R.compile_request(SHOT, None, {"meta": {}}, {"look": {"style": "auto"}}, _man(), [])["prompt"]
    assert "Let the feeling read" in p and "Intensity: about" not in p                  # intensity 6: the middle tier
    quiet = dict(SHOT, performance_intensity=3)
    q = R.compile_request(quiet, None, {"meta": {}}, {"look": {"style": "auto"}}, _man(), [])["prompt"]
    assert "Play it truthfully" in q and "Let the feeling read" not in q                # a quiet shot stays truthful


def test_resolution_order_shot_scene_character_project():
    proj = {"performance": {"default": "natural", "characters": {"Ada": "expressive"}}}
    assert P.resolve(proj, SHOT) == ("expressive", "character:Ada")
    proj["performance"]["scenes"] = {"1": "dramatic"}
    assert P.resolve(proj, SHOT)[0] == "dramatic"
    proj["performance"]["shots"] = {"S01-02": "restrained"}
    assert P.resolve(proj, SHOT) == ("restrained", "shot")


def test_profile_text_reaches_video_and_still_prompts():
    proj = {"look": {"style": "auto"}, "performance": {"default": "restrained"}}
    v = R.compile_request(SHOT, None, {"meta": {}}, proj, _man(True), [])["prompt"]
    assert "Underplay it" in v and "Intensity: about 4/10" in v and "slow blinks" in v and "Play it truthfully" not in v
    s = R.compile_request(SHOT, None, {"meta": {}}, proj, _man(False), [])["prompt"]
    assert "Composed, contained expression" in s and "slow blinks" not in s


def test_set_validates_and_clears(tmp_path):
    d = tmp_path / "P"
    d.mkdir()
    (d / "project.json").write_text(json.dumps({"title": "P"}))
    P.set_(str(d), {"default": "energetic", "shots": {"S01-01": "dramatic"}})
    assert P.get(str(d))["shots"] == {"S01-01": "dramatic"}
    P.set_(str(d), {"shots": {"S01-01": "inherit"}})
    assert P.get(str(d))["shots"] == {} and P.get(str(d))["default"] == "energetic"
    with pytest.raises(SystemExit):
        P.set_(str(d), {"default": "wild"})


def test_drift_only_for_people_and_in_filter():
    proj = {"performance": {"default": "energetic"}}
    assert P.drift_for(proj, {"id": "x", "performers": []}) is None
    dr = P.drift_for(proj, SHOT)
    f = export.ken_burns("zoom_in", 48, 320, 180, dr)
    assert "sin(2*PI*on/" in f and f"{dr['amp']}" in f


def test_micro_animated_still_exports(tmp_path):
    """Real ffmpeg: a moving still with the energetic drift renders the right number of frames and actually moves."""
    ff = export.ffmpeg()
    img = tmp_path / "a.png"
    im = Image.new("RGB", (640, 360))
    for x in range(640):
        for y in range(0, 360, 8):
            im.putpixel((x, y), (x % 256, 80, 200))
    im.save(img)
    out = str(tmp_path / "o.mp4")
    vf = export.ken_burns("none", 48, 320, 180, P.PROFILES["energetic"]["drift"])
    subprocess.run([ff, "-y", "-loglevel", "error", "-loop", "1", "-framerate", "24", "-i", str(img), "-vf", vf,
                    "-frames:v", "48", "-pix_fmt", "yuv420p", out], check=True)
    a, b = str(tmp_path / "a1.png"), str(tmp_path / "b1.png")
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", out, "-vf", "select=eq(n\,0)", "-frames:v", "1", a], check=True)
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", out, "-vf", "select=eq(n\,12)", "-frames:v", "1", b], check=True)
    assert Image.open(a).tobytes() != Image.open(b).tobytes()
