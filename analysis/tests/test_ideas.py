"""Four finishing touches: a season becomes one film per episode (free), the screen colour is found for you, and (in the app) a film's own picture on Home and a ready screen after export. This file is the engine side:
the season's films and the screen-colour finder, on real films and real pictures. Nothing here is generated or charged."""
import json
import os

import pytest
from PIL import Image

from filmcrafter_engine import overlays as O, presets as P, series as S, story
from tests.test_editing import build_film, ff
from tests.test_performance_director import film  # noqa: F401  (a small film with a render project)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------- a season becomes films

def season(film, episodes=4):
    f, rd = film
    P.run(rd, "set_pending", {"stack": ["vertical_micro_drama", "punchy_social_cut"]})
    S.create(rd, "A nurse learns the hospital hides a second set of books", episodes, 75, "mystery_micro_drama", "Sarah")
    return f, rd


def test_every_episode_gets_its_own_film_with_its_outline_and_the_seasons_presets(film):
    f, rd = season(film)
    out = S.run(rd, "make_films", {})
    assert [m["n"] for m in out["made"]] == [1, 2, 3, 4] and out["kept"] == [] and out["folder"] == os.path.dirname(f)
    for m in out["made"]:
        assert os.path.isfile(os.path.join(m["dir"], "film.json")) and os.path.dirname(m["dir"]) == os.path.dirname(f)
        text = open(os.path.join(m["dir"], "script", "original", "story.txt"), encoding="utf-8").read()
        assert f"EPISODE" not in text.split("\n")[0] and "THIS EPISODE" in text and "Sarah" in text and f"episode {m['n']} of 4" in text
        st = P.load_state(m["dir"])
        assert st["pending"][:2] == ["vertical_micro_drama", "punchy_social_cut"] and st["pending"][-1] == P.SETUP_ID    # the season's presets, then this episode's own length
        assert st["mine"][P.SETUP_ID]["settings"] == {"duration_hint_s": 75}
    assert json.load(open(os.path.join(out["made"][0]["dir"], "film.json")))["story"]["kind"] == "outline"


def test_asked_again_it_makes_only_what_is_missing_and_never_touches_a_film_that_exists(film):
    f, rd = season(film)
    first = S.run(rd, "make_films", {})
    keep = first["made"][0]["dir"]
    note = os.path.join(keep, "script", "original", "story.txt")
    open(note, "a", encoding="utf-8").write("\nMY OWN LINE")
    import shutil
    shutil.rmtree(first["made"][2]["dir"])                                                         # the person deleted episode 3's film
    again = S.run(rd, "make_films", {})
    assert [m["n"] for m in again["made"]] == [3] and [m["n"] for m in again["kept"]] == [1, 2, 4]
    assert "MY OWN LINE" in open(note, encoding="utf-8").read()                                    # an existing film is not rewritten
    assert S.run(rd, "make_films", {})["made"] == []                                               # and a third time makes nothing


def test_without_a_plan_or_outside_a_film_it_refuses_and_makes_nothing(film, tmp_path):
    f, rd = film
    with pytest.raises(SystemExit, match="season plan first"):
        S.run(rd, "make_films", {})
    before = set(os.listdir(os.path.dirname(f)))
    assert set(os.listdir(os.path.dirname(f))) == before


def test_no_paid_call_is_possible_from_making_the_episode_films():
    src = open(S.__file__, encoding="utf-8").read()
    for bad in ("render", "requests", "queue", "provider", "http", "api_key"):
        assert bad not in src.split("def make_films")[1].split("def run")[0].lower().replace("rendering", ""), bad


# ---------------------------------------------------------------- finding the screen colour

def picture(path, bg, subject=(200, 40, 40), size=(120, 80)):
    im = Image.new("RGB", size, bg)
    for x in range(40, 80):
        for y in range(20, 60):
            im.putpixel((x, y), subject)
    im.save(path)
    return path


@pytest.fixture
def film_dir(tmp_path):
    return build_film(tmp_path, [("S01-01", 1, 0.0, 6.0)], 6.0)


def test_a_green_screen_is_found_by_its_edges_even_when_lit_unevenly(film_dir, tmp_path):
    im = Image.new("RGB", (120, 80))
    for x in range(120):
        for y in range(80):
            im.putpixel((x, y), (10, 120 + x, 40))                                                  # green, darker on the left and brighter on the right
    for x in range(40, 80):
        for y in range(20, 60):
            im.putpixel((x, y), (200, 40, 40))
    src = str(tmp_path / "gs.png")
    im.save(src)
    o = O.add(film_dir, {"image": src, "start": 0, "end": 3})[-1]
    r = O.key_suggest(film_dir, o["id"])
    assert r["found"] and r["kind"] == "green" and r["sure"] >= 0.9
    red, green, blue = (int(r["color"][i:i + 2], 16) for i in (1, 3, 5))
    assert green > red + 60 and green > blue + 60                                                   # a green, not the subject's red


def test_a_blue_screen_is_found_too_and_a_picture_with_no_screen_says_so(film_dir, tmp_path):
    a = O.add(film_dir, {"image": picture(str(tmp_path / "b.png"), (20, 40, 210)), "start": 0, "end": 3})[-1]
    assert O.key_suggest(film_dir, a["id"])["kind"] == "blue"
    b = O.add(film_dir, {"image": picture(str(tmp_path / "g.png"), (120, 120, 120)), "start": 0, "end": 3})[-1]
    r = O.key_suggest(film_dir, b["id"])
    assert r["found"] is False and "could not see a green or blue screen" in r["message"]
    c = O.add(film_dir, {"image": picture(str(tmp_path / "r.png"), (200, 40, 40), (40, 200, 40)), "start": 0, "end": 3})[-1]
    assert O.key_suggest(film_dir, c["id"])["found"] is False                                      # a green subject in the middle of a red frame is not a screen


def test_a_video_clip_is_looked_at_by_its_first_frame_and_nothing_is_changed(film_dir, tmp_path):
    clip = str(tmp_path / "gs.mp4")
    ff("-f", "lavfi", "-i", "color=c=0x00b140:s=160x90:r=24:d=1", "-vf", "drawbox=x=50:y=20:w=60:h=50:color=0xd02020:t=fill,format=yuv420p", "-c:v", "libx264", "-pix_fmt", "yuv420p", clip)
    o = O.add(film_dir, {"video": clip, "start": 0})[-1]
    before = json.dumps(O.load(film_dir), sort_keys=True)
    r = O.key_suggest(film_dir, o["id"])
    red, green = int(r["color"][1:3], 16), int(r["color"][3:5], 16)
    assert r["found"] and r["kind"] == "green" and green > red + 60
    assert json.dumps(O.load(film_dir), sort_keys=True) == before                                   # it only looked


def test_what_cannot_have_a_colour_cut_out_is_refused_plainly(film_dir):
    t = O.add(film_dir, {"kind": "text", "text": "x", "start": 0, "end": 2})[-1]
    with pytest.raises(SystemExit, match="picture or a video clip"):
        O.key_suggest(film_dir, t["id"])
    with pytest.raises(SystemExit, match="isn't in the project"):
        O.key_suggest(film_dir, "ov_nope")
    with pytest.raises(SystemExit):
        O.key_suggest(film_dir, ["a"])


# ---------------------------------------------------------------- the vertical version offered on the ready screen

def test_the_vertical_version_is_a_separate_file_and_the_film_just_made_is_not_touched(film_dir):
    import hashlib
    from filmcrafter_engine import export as E
    wide = E.build(film_dir, "youtube")
    digest = lambda p: hashlib.sha1(open(p, "rb").read()).hexdigest()
    before = digest(wide["path"])
    tall = E.build(film_dir, "vertical")
    assert tall["path"] != wide["path"] and os.path.isfile(tall["path"]) and os.path.isfile(wide["path"])
    assert (tall["width"], tall["height"]) == (1080, 1920) and (wide["width"], wide["height"]) == (1920, 1080)
    assert digest(wide["path"]) == before                                                           # the film that was ready is byte for byte what it was
    assert "TikTok" in os.path.basename(tall["path"]) and "YouTube" in os.path.basename(wide["path"])
