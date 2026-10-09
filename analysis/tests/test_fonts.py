"""Fonts for captions and on-screen text: chosen by id (never a path), added from a file, used by both, and never able to break an export."""
import glob
import json
import os
import sys

import pytest
from PIL import Image

from filmcrafter_engine import captions as C, fonts as F, overlays as O


def _real_fonts():
    pats = ([r"C:\Windows\Fonts\*.ttf"] if sys.platform == "win32" else
            ["/usr/share/fonts/**/*.ttf", "/System/Library/Fonts/Supplemental/*.ttf", "/Library/Fonts/*.ttf"])
    found = []
    for p in pats:
        found += glob.glob(p, recursive=True)
    names = {os.path.basename(f).lower(): f for f in found}
    pairs = [("arial.ttf", "times.ttf"), ("arial.ttf", "cour.ttf"), ("dejavusans.ttf", "dejavuserif.ttf"), ("arial.ttf", "georgia.ttf")]
    for a, b in pairs:
        if a in names and b in names:
            return names[a], names[b]
    return None


REAL = _real_fonts()
pytestmark = pytest.mark.skipif(REAL is None, reason="two different real fonts are needed")


@pytest.fixture
def fontdir(tmp_path, monkeypatch):
    import shutil
    base = tmp_path / "installed"
    base.mkdir()
    shutil.copy(REAL[0], base / "Plain-One.ttf")
    shutil.copy(REAL[1], base / "Other-Two.ttf")
    (base / "notes.txt").write_text("not a font")
    (base / "broken.ttf").write_bytes(b"this is not a font file at all" * 50)
    monkeypatch.setattr(F, "FONT_DIRS", [str(base)])
    monkeypatch.setattr(F, "INDEX_PATH", str(tmp_path / "fonts-index.json"))
    return base


def _project(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    json.dump({"duration": 20.0, "sections": [{"label": "VERSE", "start": 0, "end": 10}, {"label": "CHORUS", "start": 10, "end": 20}],
               "lyrics": [{"section": "VERSE", "text": "Nine months I carry you", "start": 1.0, "end": 4.0},
                          {"section": "CHORUS", "text": "I AM YOUR MOTHER", "start": 11.0, "end": 14.0}]}, open(d / "songmap.json", "w"))
    return str(d)


def _pixels(path):
    with Image.open(path) as im:
        return im.convert("RGBA").tobytes()


def test_installed_fonts_are_listed_by_family_and_unreadable_files_are_left_out(fontdir):
    got = F.installed()
    assert sorted(f["file"] for f in got) == ["Other-Two.ttf", "Plain-One.ttf"]                      # the text file and the broken font are not offered
    assert all(f["id"] == f"system:{f['file']}" and f["name"] for f in got)
    assert os.path.exists(F.INDEX_PATH) and F.installed() == got                                      # remembered, and the same the second time


def test_a_font_is_only_ever_found_by_a_plain_file_name_in_a_known_folder(fontdir, tmp_path):
    d = _project(tmp_path)
    assert F.path_for(d, "system:Plain-One.ttf") == str(fontdir / "Plain-One.ttf")
    outside = tmp_path / "secret.ttf"
    outside.write_bytes(open(REAL[0], "rb").read())
    for bad in ("", None, "Plain-One.ttf", "system:../secret.ttf", "system:..\\secret.ttf", "system:" + str(outside), "system:sub/Plain-One.ttf",
                "system:Plain-One.txt", "project:../secret.ttf", "other:Plain-One.ttf", "system:", "system:nothere.ttf", "system:a\x00.ttf"):
        assert F.path_for(d, bad) is None, bad
    assert F.check(d, "") == "" and F.check(d, "system:Plain-One.ttf") == "system:Plain-One.ttf"
    with pytest.raises(SystemExit, match="isn't available"):
        F.check(d, "system:../secret.ttf")


def test_a_font_file_can_be_added_to_the_project_and_bad_ones_are_refused(fontdir, tmp_path):
    d = _project(tmp_path)
    r = F.add_file(d, str(fontdir / "Other-Two.ttf"))
    assert r["id"] == "project:Other-Two.ttf" and os.path.exists(os.path.join(d, "fonts", "Other-Two.ttf"))
    assert F.path_for(d, r["id"]) == os.path.join(d, "fonts", "Other-Two.ttf") and [f["id"] for f in F.listing(d)["project"]] == [r["id"]]
    for bad, why in ((fontdir / "notes.txt", "Choose a font file"), (fontdir / "broken.ttf", "isn't a font"), (tmp_path / "missing.ttf", "Choose a font file")):
        with pytest.raises(SystemExit, match=why):
            F.add_file(d, str(bad))
    big = tmp_path / "big.ttf"
    big.write_bytes(open(REAL[0], "rb").read())
    old = F.MAX_FONT_BYTES
    F.MAX_FONT_BYTES = 1000
    try:
        with pytest.raises(SystemExit, match="too large"):
            F.add_file(d, str(big))
    finally:
        F.MAX_FONT_BYTES = old


def test_on_screen_text_is_drawn_in_the_chosen_font_and_the_cache_follows_it(fontdir, tmp_path):
    d = _project(tmp_path)
    O.add(d, {"kind": "text", "text": "I AM YOUR MOTHER", "size": 0.1, "start": 0, "end": 3})
    o = O.load(d)[0]
    plain, _ = O.render_png(d, o, 960, 540)
    one, _ = O.render_png(d, {**o, "font": "system:Plain-One.ttf"}, 960, 540)
    two, _ = O.render_png(d, {**o, "font": "system:Other-Two.ttf"}, 960, 540)
    assert len({_pixels(plain), _pixels(one), _pixels(two)}) == 3 and len({plain, one, two}) == 3        # three looks, three cached files
    O.update(d, o["id"], {"font": "system:Other-Two.ttf"})
    assert O.load(d)[0]["font"] == "system:Other-Two.ttf"
    with pytest.raises(SystemExit, match="isn't available"):
        O.update(d, o["id"], {"font": "system:ghost.ttf"})
    assert O.load(d)[0]["font"] == "system:Other-Two.ttf"                                               # a refused font changes nothing


def test_a_font_that_has_gone_missing_falls_back_to_the_default_instead_of_failing(fontdir, tmp_path):
    d = _project(tmp_path)
    O.add(d, {"kind": "text", "text": "Hello", "size": 0.1, "start": 0, "end": 3})
    o = O.load(d)[0]
    default, _ = O.render_png(d, o, 960, 540)
    gone, _ = O.render_png(d, {**o, "font": "system:uninstalled.ttf"}, 960, 540)
    assert _pixels(default) == _pixels(gone)
    (fontdir / "Plain-One.ttf").write_bytes(b"corrupt" * 200)                                           # a font that has since gone bad
    broken, _ = O.render_png(d, {**o, "font": "system:Plain-One.ttf"}, 960, 540)
    assert _pixels(default) == _pixels(broken)


def test_caption_fonts_layer_film_then_section_then_line(fontdir, tmp_path):
    d = _project(tmp_path)
    assert C.get(d)["style"]["font"] == "" and all(x["look"]["font"] == "" for x in C.get(d)["lines"])
    C.set_style(d, {"font": "system:Plain-One.ttf"})
    C.set_section(d, "CHORUS", {"font": "system:Other-Two.ttf"})
    fonts = {x["section"]: x["look"]["font"] for x in C.get(d)["lines"]}
    assert fonts == {"VERSE": "system:Plain-One.ttf", "CHORUS": "system:Other-Two.ttf"}                 # the section beats the film
    key = next(x["key"] for x in C.get(d)["lines"] if x["section"] == "CHORUS")
    C.edit(d, key, {"font": "system:Plain-One.ttf"})
    assert next(x for x in C.get(d)["lines"] if x["key"] == key)["look"]["font"] == "system:Plain-One.ttf"   # the line beats its section
    C.edit(d, key, {"font": ""})
    assert next(x for x in C.get(d)["lines"] if x["key"] == key)["look"]["font"] == "system:Other-Two.ttf"
    for call in (lambda: C.set_style(d, {"font": "system:ghost.ttf"}), lambda: C.set_section(d, "VERSE", {"font": "../x.ttf"}), lambda: C.edit(d, key, {"font": "system:ghost.ttf"})):
        with pytest.raises(SystemExit, match="isn't available"):
            call()


def test_captions_are_drawn_in_their_font(fontdir, tmp_path):
    d = _project(tmp_path)
    ln = C.lines(d)[0]
    a = C._frame_png(d, ln, C.load(d)["style"], 960, 540)
    b = C._frame_png(d, {**ln, "look": {}}, {**C.load(d)["style"], "font": "system:Other-Two.ttf"}, 960, 540)       # no line look: the film's font applies
    c = C._frame_png(d, {**ln, "look": {"font": "system:Plain-One.ttf"}}, C.load(d)["style"], 960, 540)
    assert len({_pixels(a), _pixels(b), _pixels(c)}) == 3
    C.set_style(d, {"font": "system:Other-Two.ttf"})
    assert C.preview(d)["path"].endswith("preview.png")


def test_a_project_font_survives_the_original_being_uninstalled(fontdir, tmp_path):
    d = _project(tmp_path)
    fid = F.add_file(d, str(fontdir / "Other-Two.ttf"))["id"]
    C.set_style(d, {"font": fid})
    before = _pixels(C._frame_png(d, C.lines(d)[0], C.load(d)["style"], 960, 540))
    os.remove(fontdir / "Other-Two.ttf")                                                                # uninstalled from the computer
    F.installed()
    after_dir = os.path.join(d, "cache", "captions")
    for f in os.listdir(after_dir):
        os.remove(os.path.join(after_dir, f))                                                           # force a redraw
    after = _pixels(C._frame_png(d, C.lines(d)[0], C.load(d)["style"], 960, 540))
    assert before == after
