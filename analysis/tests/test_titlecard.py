"""The intro title card: its parts, replacing and removing it, the preview, the optional intro shot, and the result on real video."""
import json
import os
import subprocess

import pytest
from PIL import Image

from pulseframe_analysis import overlays as O, titlecard as TC
from pulseframe_analysis.export import NO_WINDOW, ffmpeg


@pytest.fixture
def proj(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    json.dump({"title": "I Am Your Mother", "song": "s.wav"}, open(d / "project.json", "w"))
    json.dump({"duration": 20.0, "sections": [], "lyrics": []}, open(d / "songmap.json", "w"))
    shots = [{"id": f"S01-0{i}", "scene": 1, "number": i, "start": 4.5 + (i - 1) * 3.0, "end": 4.5 + i * 3.0, "beats": ["x"], "performers": []} for i in (1, 2, 3)]
    json.dump({"scenes": [{"number": 1, "start": 4.5, "end": 13.5, "shots": shots}]}, open(d / "production.json", "w"))
    return str(d)


def parts(d):
    return [o for o in O.load(d) if o.get("group") == TC.GROUP]


def test_the_card_goes_in_the_part_before_the_first_shot_only_when_there_is_room(proj, tmp_path):
    assert TC.gap(proj) == (0.0, 4.5)
    d2 = tmp_path / "q"
    d2.mkdir()
    json.dump({"scenes": [{"number": 1, "shots": [{"id": "S01-01", "start": 1.0, "end": 3.0}]}]}, open(d2 / "production.json", "w"))
    assert TC.gap(str(d2)) is None
    st = TC.state(proj)
    assert st["gap"] == (0.0, 4.5) and st["card"] is None and st["title"] == "I Am Your Mother"


def test_a_title_and_subtitle_become_two_overlays_with_the_chosen_movement(proj):
    st = TC.make(proj, {"title": "  I Am Your Mother  ", "subtitle": "A family musical", "anim": "zoom_in", "color": "#ffd166", "size": 0.1})
    p = parts(proj)
    assert [o["kind"] for o in p] == ["text", "text"] and p[0]["text"] == "I Am Your Mother" and p[0]["anim"] == "zoom_in" and p[0]["color"] == "#ffd166"
    assert p[1]["text"] == "A family musical" and p[1]["anim"] == "fade" and p[1]["start"] > p[0]["start"] and p[1]["y"] > p[0]["y"]      # the subtitle comes in after the title, below it
    assert 0 < p[0]["start"] < 1 and 3.5 < p[0]["end"] < 4.5                                                                             # inside the intro, with a margin
    assert st["card"]["title"] == "I Am Your Mother" and st["card"]["subtitle"] == "A family musical" and st["card"]["anim"] == "zoom_in"


def test_making_the_card_again_replaces_it_and_removing_it_leaves_other_text_alone(proj):
    O.add(proj, {"kind": "text", "text": "FAMILY GOVERNMENT", "start": 30, "end": 34})
    TC.make(proj, {"title": "One", "subtitle": "x"})
    TC.make(proj, {"title": "Two"})
    assert [o["text"] for o in parts(proj)] == ["Two"] and len(O.load(proj)) == 2
    st = TC.remove(proj)
    assert st["card"] is None and [o["text"] for o in O.load(proj)] == ["FAMILY GOVERNMENT"]


def test_a_colour_or_gradient_backdrop_sits_under_the_title(proj):
    TC.make(proj, {"title": "T", "background": {"type": "colour", "color": "#101820", "color2": "#aa3300"}})
    p = parts(proj)
    assert [o["kind"] for o in p] == ["fill", "text"] and p[0]["cover"] and p[0]["color2"] == "#aa3300" and p[0]["fade"] == 0.6      # first in the list = drawn first = underneath
    assert TC.state(proj)["card"]["background"] == {"type": "colour", "color": "#101820", "color2": "#aa3300"}


def test_a_picture_backdrop_is_copied_into_the_project_and_pushes_in_slowly(proj, tmp_path):
    pic = tmp_path / "art é.png"
    Image.new("RGB", (800, 300), (180, 40, 40)).save(pic)
    TC.make(proj, {"title": "T", "background": {"type": "picture", "picture": str(pic)}})
    back = parts(proj)[0]
    assert back["kind"] == "image" and back["cover"] and back["anim"] == "pushin" and back["file"].startswith("assets/overlays/card-") and os.path.isfile(os.path.join(proj, back["file"]))
    again = TC.state(proj)["card"]["background"]
    assert again["type"] == "picture" and again["file"] == back["file"]
    TC.make(proj, {"title": "T2", "background": again})                                                                                # redesigned without choosing the picture again
    assert parts(proj)[0]["file"] == back["file"]


def test_what_is_not_allowed_is_refused_plainly(proj, tmp_path):
    for bad, why in (({"title": "  "}, "Write the title"), ({"title": "T", "anim": "spin"}, "movements in the list"), ({"title": "T", "background": {"type": "video"}}, "black, colour or picture"),
                     ({"title": "T", "start": 1, "end": 1.5}, "at least a second"), ({"title": "T", "background": {"type": "picture", "picture": str(tmp_path / "nope.png")}}, "PNG, JPG or WebP")):
        with pytest.raises(SystemExit, match=why):
            TC.make(proj, bad)
    txt = tmp_path / "not.png"
    txt.write_text("not a picture")
    with pytest.raises(SystemExit, match="does not open as a picture"):
        TC.make(proj, {"title": "T", "background": {"type": "picture", "picture": str(txt)}})
    assert parts(proj) == []                                                                                                          # nothing half-made


def test_the_preview_shows_the_settled_card_and_changes_nothing(proj):
    r = TC.preview(proj, {"title": "HELLO", "subtitle": "world", "background": {"type": "colour", "color": "#102040"}})
    im = Image.open(os.path.join(proj, r["path"])).convert("RGB")
    assert im.size == (960, 540) and im.getpixel((5, 5))[2] > im.getpixel((5, 5))[0]                                                  # blue-ish backdrop
    bright = im.convert("L").point(lambda v: 255 if v > 200 else 0).getbbox()
    assert bright and 350 < (bright[0] + bright[2]) / 2 < 610                                                                          # the title is centred
    assert O.load(proj) == []


def test_an_intro_shot_is_an_ordinary_shot_before_the_first_one(proj):
    r = TC.intro_shot(proj, {"prompt": "Golden light moves across burgundy fabric, slow push in"})
    plan = json.load(open(os.path.join(proj, "production.json")))
    first = plan["scenes"][0]["shots"][0]
    assert r["shot"] == "S01-00" and first["id"] == "S01-00" and (first["start"], first["end"]) == (0.0, 4.5) and plan["scenes"][0]["start"] == 0.0
    assert "No text, no letters" in first["visual_prompt"] and first["beats"] and first["performers"] == [] and not r["keyframe"]
    assert [s["id"] for s in plan["scenes"][0]["shots"]][:2] == ["S01-00", "S01-01"]
    assert TC.gap(proj) is None                                                                                                        # the room is used: no more gap, and another intro is refused
    with pytest.raises(SystemExit, match="no room"):
        TC.intro_shot(proj, {"prompt": "again"})


def test_an_intro_shot_can_start_from_your_picture_as_its_approved_keyframe(proj, tmp_path):
    pic = tmp_path / "start.jpg"
    Image.new("RGB", (640, 360), (20, 60, 120)).save(pic)
    r = TC.intro_shot(proj, {"prompt": "Slow push in", "picture": str(pic)})
    kf = json.load(open(os.path.join(proj, "keyframes.json")))["production"]["S01-00"]
    assert r["keyframe"] and kf == "project:assets/refs/intro-S01-00.png" and Image.open(os.path.join(proj, kf[8:])).format == "PNG"
    with pytest.raises(SystemExit, match="Describe what|no room"):
        TC.intro_shot(proj, {"prompt": "  "})


def test_an_intro_shot_needs_a_description(proj):
    with pytest.raises(SystemExit, match="Describe what"):
        TC.intro_shot(proj, {"prompt": "  "})


def test_the_card_is_on_the_real_video_and_the_film_goes_back_to_normal_after_it(proj, tmp_path):
    TC.make(proj, {"title": "HELLO", "anim": "rise", "background": {"type": "colour", "color": "#1a3a8a"}, "size": 0.2})
    v = tmp_path / "film.mp4"
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0x303030:s=320x180:r=12:d=6", "-pix_fmt", "yuv420p", str(v)], check=True, creationflags=NO_WINDOW)
    r = O.burn(proj, str(v), 320, 180, fps=12, duration=6.0)
    assert not r.get("error") and r["count"] == 2

    def px(t):
        out = str(tmp_path / f"f{t}.png")
        subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", str(t), "-i", str(v), "-frames:v", "1", out], check=True, creationflags=NO_WINDOW)
        return Image.open(out).convert("RGB")
    mid = px(2.5)
    assert mid.getpixel((5, 5))[2] > 100 > mid.getpixel((5, 5))[0]                                                                     # the blue backdrop is up
    assert mid.convert("L").point(lambda v: 255 if v > 200 else 0).getbbox()                                                          # and the title on it
    after = px(5.0)
    assert abs(after.getpixel((5, 5))[0] - 0x30) < 10 and abs(after.getpixel((5, 5))[2] - 0x30) < 10                                  # the film itself again once the card is over


def test_the_command_line_speaks_json(proj, capsys):
    assert TC.main(["make", proj, "--data", json.dumps({"title": "Hi"})]) == 0
    ev = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert ev["event"] == "result" and ev["data"]["card"]["title"] == "Hi"
    assert TC.main(["make", proj, "--data", json.dumps({"title": ""})]) == 1
    assert "Write the title" in json.loads(capsys.readouterr().out.splitlines()[-1])["message"]


def test_a_card_over_an_intro_shot_uses_that_shots_time(proj):
    assert TC.state(proj)["span"] == (0.0, 4.5)
    TC.intro_shot(proj, {"prompt": "Gold dust drifts"})
    st = TC.state(proj)
    assert st["gap"] is None and st["span"] == (0.0, 4.5)                                          # no gap any more, but the card still knows where it goes
    TC.make(proj, {"title": "Hello"})
    t = parts(proj)[0]
    assert 0 < t["start"] < 1 and 3.5 < t["end"] < 4.5
