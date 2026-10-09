"""Transitions between shots, on real clips: red shot then blue shot. Each kind is checked by where red and blue are a moment into the transition, and that the shot keeps its exact length."""
import json
import os
import shutil
import subprocess

import pytest
from PIL import Image

from pulseframe_analysis import export, media, transitions as T

FF = export.ffmpeg()
W, H, FPS = 320, 180, export.FPS
LONG = 2.0


def clip(path, color, secs=LONG):
    subprocess.run([FF, "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={color}:s={W}x{H}:r={FPS}:d={secs}", "-pix_fmt", "yuv420p", path], check=True)


def frame_at(path, t, out):
    subprocess.run([FF, "-y", "-loglevel", "error", "-ss", str(t), "-i", path, "-frames:v", "1", out], check=True)
    return Image.open(out).convert("RGB")


def at(img, fx, fy):
    return img.getpixel((int(fx * (W - 1)), int(fy * (H - 1))))


def red(p):
    return p[0] > 150 and p[2] < 90


def blue(p):
    return p[2] > 150 and p[0] < 90


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("tr")
    clip(str(d / "red.mp4"), "red")
    clip(str(d / "blue.mp4"), "blue")
    return d


def entered(clips, kind, secs=1.0, name=None):
    cur = str(clips / f"{name or kind}.mp4")
    shutil.copy(clips / "blue.mp4", cur)
    enc = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p", "-an"]
    T.enter(export._run, str(clips / "red.mp4"), cur, round(LONG * FPS), enc, kind, secs, W, H, FPS)
    return cur


def frames_of(path):
    out = subprocess.run([FF, "-hide_banner", "-i", path, "-map", "0:v:0", "-c", "copy", "-f", "null", "-"], capture_output=True, text=True).stderr
    return int(out.rsplit("frame=", 1)[1].split()[0])


# the picture a third of the way through a one-second transition (0.5 s in): what each kind shows on each side
EXPECT = {
    "wipe_right": [((0.15, 0.5), blue), ((0.85, 0.5), red)],
    "wipe_left": [((0.85, 0.5), blue), ((0.15, 0.5), red)],
    "wipe_down": [((0.5, 0.15), blue), ((0.5, 0.85), red)],
    "wipe_up": [((0.5, 0.85), blue), ((0.5, 0.15), red)],
    "slide_left": [((0.15, 0.5), red), ((0.85, 0.5), blue)],
    "slide_right": [((0.85, 0.5), red), ((0.15, 0.5), blue)],
    "slide_up": [((0.5, 0.15), red), ((0.5, 0.85), blue)],
    "slide_down": [((0.5, 0.85), red), ((0.5, 0.15), blue)],
    "whip_left": [((0.25, 0.5), red), ((0.97, 0.5), blue)],          # eased: most of the old picture is still there half way, then it is gone fast
    "whip_right": [((0.75, 0.5), red), ((0.03, 0.5), blue)],
}


@pytest.mark.parametrize("kind", sorted(EXPECT))
def test_each_directional_transition_moves_the_old_picture_the_way_it_says(clips, kind):
    p = entered(clips, kind)
    img = frame_at(p, 0.5, str(clips / f"{kind}_mid.png"))
    for (fx, fy), want in EXPECT[kind]:
        px = at(img, fx, fy)
        assert want(px), (kind, (fx, fy), px)


@pytest.mark.parametrize("kind", [k for k in T.TRANSITIONS if k not in ("cut", "black", "white")])
def test_every_transition_ends_on_the_new_shot_and_keeps_its_length(clips, kind):
    p = entered(clips, kind)
    assert frames_of(p) == round(LONG * FPS)                                              # nothing shifted or overlapped in time
    early = frame_at(p, 0.0, str(clips / f"{kind}_0.png"))
    late = frame_at(p, 1.5, str(clips / f"{kind}_late.png"))
    assert blue(at(late, 0.5, 0.5)) and blue(at(late, 0.1, 0.1)) and blue(at(late, 0.9, 0.9)), "after the transition only the new shot is on screen"
    assert red(at(early, 0.5, 0.5)), "the old picture is still all there on the first frame"


def test_a_dissolve_and_a_zoom_through_mix_the_two_pictures_part_way(clips):
    for kind in ("dissolve", "zoom_through"):
        p = entered(clips, kind)
        px = at(frame_at(p, 0.5, str(clips / f"{kind}_m.png")), 0.5, 0.5)
        assert px[0] > 40 and px[2] > 40, (kind, px)


def test_a_longer_transition_is_still_underway_when_a_short_one_has_finished(clips):
    short = entered(clips, "wipe_right", 0.25, "w_short")
    long_ = entered(clips, "wipe_right", 1.0, "w_long")
    s = frame_at(short, 0.5, str(clips / "s.png"))
    l = frame_at(long_, 0.5, str(clips / "l.png"))
    assert blue(at(s, 0.9, 0.5)) and red(at(l, 0.9, 0.5))


def test_a_transition_never_takes_more_than_half_of_a_short_shot():
    assert T.frames_for("dissolve", 2.0, 12, 24) == 6
    assert T.frames_for("dissolve", None, 100, 24) == 12
    assert T.frames_for("whip_left", None, 100, 24) == 6


def test_lengths_are_kept_inside_what_looks_right_and_junk_is_refused():
    assert T.clean_seconds("dissolve", 0) == T.MIN_S
    assert T.clean_seconds("dissolve", 99) == T.MAX_S
    assert T.clean_seconds("dissolve", None) is None and T.clean_seconds("dissolve", "") is None
    for bad in ("soon", float("nan"), float("inf")):
        with pytest.raises(SystemExit):
            T.clean_seconds("dissolve", bad)


def test_every_catalogue_entry_has_a_label_a_group_and_a_default_length():
    assert T.TRANSITIONS[0] == "cut" and len(T.TRANSITIONS) == len(set(T.TRANSITIONS))
    for k, (label, group, secs) in T.CATALOG.items():
        assert label and group and secs >= 0
        if k != "cut":
            assert T.MIN_S <= secs <= T.MAX_S


def test_the_dips_fade_the_shot_itself_for_the_chosen_length():
    assert T.fades("cut", "cut", 48, 24) == ""
    assert "fade=t=in:s=0:n=7:color=black" in T.fades("black", "cut", 48, 24)                 # 0.3 s
    assert "fade=t=in:s=0:n=12:color=white" in T.fades("white", "cut", 48, 24, tin_s=0.5)
    assert "fade=t=out:s=36:n=12:color=black" in T.fades("cut", "black", 48, 24, tout_s=0.5)


def test_an_unknown_transition_is_refused_where_it_is_set(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    with pytest.raises(SystemExit):
        media.set_transition(str(d), ["S01-01"], "star_wipe")
    with pytest.raises(SystemExit):
        media.set_transition(str(d), ["S01-01"], "dissolve", "soon")


def test_the_length_is_stored_with_the_shot_and_shown_on_the_board(tmp_path):
    from tests.test_media import _project, _img
    d = _project(tmp_path)
    media.import_media(d, "S01-01", _img(tmp_path, "r.png"), "none")
    media.import_media(d, "S01-02", _img(tmp_path, "b.png", (20, 20, 220)), "none")
    res = media.set_transition(d, ["S01-02"], "wipe_left", 0.8)
    assert res == {"shots": ["S01-02"], "transition": "wipe_left", "seconds": 0.8}
    from pulseframe_analysis import library
    st = library.shot_state(d)["S01-02"]
    assert st["transition"] == "wipe_left" and st["transition_s"] == 0.8
    shot = next(s for s in library.storyboard(d)["shots"] if s["id"] == "S01-02")
    assert shot["transition"] == "wipe_left" and shot["transition_s"] == 0.8


def test_an_export_with_a_new_transition_is_exactly_as_long_as_the_song(tmp_path):
    from tests.test_media import _project, _img
    d = _project(tmp_path)
    subprocess.run([FF, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=8", os.path.join(d, "song.wav")], check=True)
    media.import_media(d, "S01-01", _img(tmp_path, "r.png", (220, 20, 20)), "none")
    media.import_media(d, "S01-02", _img(tmp_path, "b.png", (20, 20, 220)), "none")
    media.set_transition(d, ["S01-02"], "wipe_right", 1.0)
    res = export.build(d, next(iter(export.PRESETS)))
    err = subprocess.run([FF, "-hide_banner", "-i", res["path"]], capture_output=True, text=True).stderr
    assert "Duration: 00:00:08" in err or "Duration: 00:00:07.9" in err
    shot2 = json.load(open(os.path.join(d, "production.json")))["scenes"][0]["shots"][1]
    img = frame_at(res["path"], shot2["start"] + 0.5, str(tmp_path / "x.png"))
    px_left, px_right = img.getpixel((int(img.width * 0.1), img.height // 2)), img.getpixel((int(img.width * 0.9), img.height // 2))
    assert px_left[2] > 150 and px_right[0] > 150, (px_left, px_right)                          # blue has wiped in from the left, red is still at the right


def test_changing_only_the_length_makes_the_shot_render_again(tmp_path):
    """The cache key of a shot's part includes the transition's length, so a longer wipe is not served from the old file."""
    from tests.test_media import _project, _img
    d = _project(tmp_path)
    subprocess.run([FF, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=8", os.path.join(d, "song.wav")], check=True)
    media.import_media(d, "S01-01", _img(tmp_path, "r.png", (220, 20, 20)), "none")
    media.import_media(d, "S01-02", _img(tmp_path, "b.png", (20, 20, 220)), "none")
    media.set_transition(d, ["S01-02"], "wipe_right", 0.3)
    a = export.build(d, next(iter(export.PRESETS)))
    shutil.copy(a["path"], tmp_path / "first.mp4")                                           # both exports are named by the minute: keep the first
    a = {"path": str(tmp_path / "first.mp4")}
    media.set_transition(d, ["S01-02"], "wipe_right", 1.5)
    b = export.build(d, next(iter(export.PRESETS)))
    ia = frame_at(a["path"], 2.0 + 0.7, str(tmp_path / "a.png"))
    ib = frame_at(b["path"], 2.0 + 0.7, str(tmp_path / "b.png"))
    assert blue(ia.getpixel((int(ia.width * 0.9), ia.height // 2))) and red(ib.getpixel((int(ib.width * 0.9), ib.height // 2)))
