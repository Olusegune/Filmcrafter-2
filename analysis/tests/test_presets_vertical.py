"""The vertical version of a wide film: made as a separate file, never touching the original, keeping the part of each shot you chose and keeping captions clear of the bottom margin.
The footage is made here; nothing is rendered by a provider."""
import json
import os
import re
import subprocess

import pytest
from PIL import Image

from filmcrafter_engine import captions, export as E, presets as P, proxies
from tests.test_editing import build_film, ff

pytestmark = pytest.mark.integration

SHOTS = [("S01-01", 1, 0.0, 1.0), ("S01-02", 1, 1.0, 2.0), ("S02-01", 2, 2.0, 3.0)]


@pytest.fixture
def film(tmp_path):
    return build_film(tmp_path, SHOTS, 3.0)


def size_of(path):
    r = subprocess.run([E.ffmpeg(), "-hide_banner", "-i", path], capture_output=True, text=True, creationflags=E.NO_WINDOW)
    m = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})", r.stderr)
    return int(m.group(1)), int(m.group(2))


def frame(video, n, tmp_path, name):
    out = str(tmp_path / f"{name}.png")
    ff("-i", video, "-vf", f"select='eq(n,{n})'", "-frames:v", "1", out)
    return Image.open(out).convert("RGB")


def boundary(im):
    """The column where the take's bright left half gives way to its dark right half, found along the middle row where the grey crosses half way (the edge is soft after scaling)."""
    y = im.height // 2
    row = [im.getpixel((x, y))[0] for x in range(im.width)]
    half = (max(row) + min(row)) / 2
    return next((x for x in range(1, len(row)) if row[x] < half <= row[x - 1]), None)


# ---------------------------------------------------------------- a separate version

def test_the_vertical_version_is_a_separate_file_in_the_phone_shape_and_the_original_is_untouched(film, tmp_path):
    wide = E.build(film, "youtube")
    before = {n: open(os.path.join(film, n), "rb").read() for n in ("project.json", "production.json", "songmap.json")}
    wide_frame = frame(wide["path"], 3, tmp_path, "wide_before").tobytes()
    tall = E.build(film, "vertical")
    assert size_of(wide["path"]) == (1920, 1080) and size_of(tall["path"]) == (1080, 1920) and tall["path"] != wide["path"]
    assert frame(wide["path"], 3, tmp_path, "wide_after").tobytes() == wide_frame
    assert {n: open(os.path.join(film, n), "rb").read() for n in before} == before                  # the film's own records are as they were
    assert os.path.isfile(wide["path"])


# ---------------------------------------------------------------- the part of the picture you keep

def test_the_middle_is_kept_by_default_and_you_can_move_it_to_either_edge_per_shot(film, tmp_path):
    mid = boundary(frame(E.build(film, "vertical")["path"], 3, tmp_path, "mid"))
    P.reframe_set(film, "S01-01", 0.0)
    left = boundary(frame(E.build(film, "vertical")["path"], 3, tmp_path, "left"))
    P.reframe_set(film, "S01-01", 1.0)
    right = boundary(frame(E.build(film, "vertical")["path"], 3, tmp_path, "right"))
    assert abs(mid - 540) <= 6 and abs(left - 960) <= 6 and abs(right - 120) <= 6                   # the take's own centre line lands where each choice puts it
    other = boundary(frame(E.build(film, "vertical")["path"], 24 + 3, tmp_path, "other"))           # the next shot was not touched by the first shot's choice
    assert abs(other - 540) <= 6
    P.reframe_set(film, "S01-01", None)
    assert abs(boundary(frame(E.build(film, "vertical")["path"], 3, tmp_path, "back")) - 540) <= 6


def test_a_wide_export_ignores_the_vertical_choice(film, tmp_path):
    base = frame(E.build(film, "youtube")["path"], 3, tmp_path, "a").tobytes()
    P.reframe_set(film, "S01-01", 0.0)
    assert frame(E.build(film, "youtube")["path"], 3, tmp_path, "b").tobytes() == base


def test_the_choice_is_checked_kept_cleared_and_a_damaged_record_means_the_middle(film):
    assert P.reframe_for(film, "S01-01") == 0.5
    assert P.reframe_set(film, "S01-01", 0.25)["reframe"] == {"S01-01": 0.25}
    assert P.reframe_set(film, "S01-01", 0.5)["reframe"] == {}                                      # the middle is the default, so it is not kept
    for bad in (-0.1, 1.5, "left", True, float("nan")):
        with pytest.raises(SystemExit):
            P.reframe_set(film, "S01-01", bad)
    with pytest.raises(SystemExit):
        P.reframe_set(film, "../x", 0.2)
    P.reframe_set(film, "S01-02", 0.9)
    open(P._path(film), "w").write("{ damaged")
    assert P.reframe_for(film, "S01-02") == 0.5


# ---------------------------------------------------------------- captions kept clear of the bottom

def test_a_caption_is_kept_above_the_margin_the_delivery_asks_for_and_otherwise_left_alone():
    assert captions.safe_y(0.9, 0.05, 0.0) == 0.9
    assert captions.safe_y(0.9, 0.05, 0.2) == pytest.approx(0.775)
    assert captions.safe_y(0.5, 0.05, 0.2) == 0.5                                                   # a caption already clear is not moved
    assert captions.safe_y(0.9, 0.05, 0.99) == 0.05                                                 # never off the top


def test_the_margin_comes_from_the_delivery_you_applied_and_only_for_a_portrait_version(film):
    assert P.delivery_safe_bottom(film) == 0.0
    f, rd = film, film
    P.apply(rd, ["tiktok_story_short"])
    assert P.delivery_safe_bottom(rd) == 0.2
    P.undo(rd)
    P.apply(rd, ["documentary"])
    assert P.delivery_safe_bottom(rd) == 0.0                                                        # a wide delivery asks for no vertical margin
