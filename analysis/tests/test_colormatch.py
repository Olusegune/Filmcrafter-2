"""Colour matching between shots: which shots are off, the correction that moves them towards the others, and that the export applies it (and only it) when asked."""
import json
import os
import subprocess
import wave

import pytest
from PIL import Image

from pulseframe_analysis import colormatch as CM, export as E, media

pytestmark = pytest.mark.integration


def ff(*args):
    subprocess.run([E.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args], check=True, creationflags=E.NO_WINDOW)


COLOURS = {"S01-01": "0x707070", "S01-02": "0x787878", "S01-03": "0x808080", "S01-04": "0x2040c0"}      # three similar greys and one strong blue


@pytest.fixture
def film(tmp_path):
    d = tmp_path / "film"
    d.mkdir()
    with wave.open(str(d / "song.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\0\0" * int(22050 * 8))
    json.dump({"title": "T", "song": "song.wav", "aspect_ratio": "16:9"}, open(d / "project.json", "w"))
    json.dump({"duration": 8.0, "sections": [], "lyrics": []}, open(d / "songmap.json", "w"))
    shots = [{"id": sid, "scene": 1, "number": i, "start": (i - 1) * 2.0, "end": i * 2.0, "beats": ["x"], "performers": []} for i, sid in enumerate(COLOURS, 1)]
    json.dump({"scenes": [{"number": 1, "heading": "INT. ROOM", "start": 0, "end": 8, "shots": shots}]}, open(d / "production.json", "w"))
    json.dump({"jobs": []}, open(d / "jobs.json", "w"))
    for sid, col in COLOURS.items():
        clip = tmp_path / f"{sid}.mp4"
        ff("-f", "lavfi", "-i", f"color=c={col}:s=320x180:r=24:d=3", "-pix_fmt", "yuv420p", str(clip))
        media.import_media(str(d), sid, str(clip))
    return str(d)


def pixel(video, t, tmp_path, name):
    out = str(tmp_path / f"{name}.png")
    ff("-ss", str(t), "-i", video, "-frames:v", "1", out)
    return Image.open(out).convert("RGB").getpixel((160, 90))


def test_the_shot_that_is_off_is_found_and_the_ones_that_match_are_left_alone(film):
    s = CM.analyze(film)
    assert s["adjusted"] == 1 and s["rows"][0]["shot"] == "S01-04" and s["rows"][0]["adjusted"] and s["rows"][0]["distance"] > 0.2
    assert [r["adjusted"] for r in s["rows"][1:]] == [False, False, False]
    assert s["enabled"] is False                                                                   # looking never changes the film: it has to be turned on


def test_the_correction_moves_the_shot_towards_the_others_and_never_further_than_asked(film):
    CM.analyze(film, strength=1.0)
    fix = json.load(open(os.path.join(film, "grade.json")))["shots"]["S01-04"]
    assert all(0.75 <= fix[c][0] <= 1.35 for c in "yuv")                                          # no channel is stretched or squeezed too far
    soft = CM.analyze(film, strength=0.3)
    half = json.load(open(os.path.join(film, "grade.json")))["shots"]["S01-04"]
    assert abs(half["u"][1]) < abs(fix["u"][1]) and soft["strength"] == 0.3                        # a lower strength is a smaller push


def test_a_chosen_reference_shot_sets_what_the_others_are_matched_to(film):
    CM.analyze(film, reference="S01-04")
    g = json.load(open(os.path.join(film, "grade.json")))
    assert g["reference"] == "S01-04" and "S01-04" not in g["shots"] and set(g["shots"]) == {"S01-01", "S01-02", "S01-03"}
    s = CM.set_options(film, {"reference": ""})                                                    # back to the typical shot
    assert s["reference"] is None and s["rows"][0]["shot"] == "S01-04"


def test_the_export_applies_the_correction_only_when_it_is_on(film, tmp_path):
    CM.analyze(film, strength=1.0)
    plain = E.build(film, "preview")
    before = pixel(plain["path"], 7.0, tmp_path, "before")                                         # S01-04 spans 6-8 s
    assert before[2] > before[0] + 60                                                              # strongly blue
    CM.set_options(film, {"enabled": True})
    graded = E.build(film, "preview")
    after = pixel(graded["path"], 7.0, tmp_path, "after")
    ref = pixel(graded["path"], 1.0, tmp_path, "ref")                                              # a grey shot
    assert sum(abs(a - r) for a, r in zip(after, ref)) < sum(abs(b - r) for b, r in zip(before, ref)) * 0.6        # clearly closer to the greys
    assert pixel(graded["path"], 1.0, tmp_path, "grey_after") == pixel(plain["path"], 1.0, tmp_path, "grey_before")   # a shot that was fine is untouched
    CM.set_options(film, {"enabled": False})
    off = E.build(film, "preview")
    assert pixel(off["path"], 7.0, tmp_path, "off") == before


def test_it_needs_something_to_compare_and_can_be_cleared(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    json.dump({"title": "T"}, open(d / "project.json", "w"))
    json.dump({"scenes": [{"number": 1, "shots": [{"id": "S01-01", "start": 0, "end": 2}]}]}, open(d / "production.json", "w"))
    with pytest.raises(SystemExit, match="at least two shots"):
        CM.analyze(str(d))
    with pytest.raises(SystemExit, match="Look at the shots first"):
        CM.set_options(str(d), {"enabled": True})
    assert CM.clear(str(d))["rows"] == [] and CM.filter_for(str(d), "S01-01") == ""


def test_the_filter_is_only_numbers_and_the_command_line_speaks_json(film, capsys):
    CM.analyze(film)
    CM.set_options(film, {"enabled": True})
    f = CM.filter_for(film, "S01-04")
    import re
    assert re.fullmatch(r"lutyuv=y='clip\(val\*[\d.]+\+\(-?[\d.]+\),16,235\)':u='clip\(val\*[\d.]+\+\(-?[\d.]+\),16,240\)':v='clip\(val\*[\d.]+\+\(-?[\d.]+\),16,240\)'", f), f
    assert CM.main(["state", film]) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["data"]["adjusted"] == 1
