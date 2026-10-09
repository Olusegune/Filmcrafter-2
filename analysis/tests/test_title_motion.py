"""Title motion, checked on real video: the pictures are drawn into a generated clip and measured frame by frame."""
import json
import os
import subprocess

import pytest
from PIL import Image

from filmcrafter_engine import overlays as O
from filmcrafter_engine.export import NO_WINDOW, ffmpeg

W, H, FPS = 320, 180, 12


def clip(path, color="0x303030", seconds=4):
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:s={W}x{H}:r={FPS}:d={seconds}", "-pix_fmt", "yuv420p", str(path)],
                   check=True, creationflags=NO_WINDOW)


def frame(video, t, out):
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t}", "-i", video, "-frames:v", "1", out], check=True, creationflags=NO_WINDOW)
    return Image.open(out).convert("L")


def bbox(im, lo=170):
    """Box around the bright pixels (the white title on the dark clip), or None."""
    mask = im.point(lambda v: 255 if v > lo else 0)
    return mask.getbbox()


def center(b):
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


@pytest.fixture
def made(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    json.dump({"title": "T", "song": "song.wav"}, open(d / "project.json", "w"))
    json.dump({"duration": 4.0, "sections": [], "lyrics": []}, open(d / "songmap.json", "w"))

    def run(anim, start=1.0, end=3.5, **extra):
        for f in ("overlays.json",):
            if (d / f).exists():
                (d / f).unlink()
        O.add(str(d), {"kind": "text", "text": "TITLE", "start": start, "end": end, "x": 0.5, "y": 0.5, "size": 0.2, "fade": 0.3, "anim": anim, **extra})
        v = tmp_path / f"{anim}.mp4"
        clip(v)
        r = O.burn(str(d), str(v), W, H, fps=FPS, duration=4.0)
        assert not r.get("error"), r
        return str(v)
    return run, tmp_path


def at(video, tmp, t):
    return bbox(frame(video, t, str(tmp / f"f{t}.png")))


def test_a_plain_fade_appears_holds_still_and_goes(made):
    run, tmp = made
    v = run("fade")
    assert at(v, tmp, 0.5) is None and at(v, tmp, 3.9) is None                               # not before it starts, gone after it ends
    a, b = at(v, tmp, 1.6), at(v, tmp, 3.0)
    assert a and b and a == b                                                               # settled: it does not move


def test_rise_starts_lower_and_settles_into_place(made):
    run, tmp = made
    v = run("rise")
    early, late = at(v, tmp, 1.2), at(v, tmp, 2.6)
    assert early and late and center(early)[1] > center(late)[1] + 3 and abs(center(early)[0] - center(late)[0]) < 2


def test_drop_starts_higher_and_settles_into_place(made):
    run, tmp = made
    v = run("drop")
    early, late = at(v, tmp, 1.2), at(v, tmp, 2.6)
    assert early and late and center(early)[1] < center(late)[1] - 3


@pytest.mark.parametrize("anim,sign", [("slide_left", 1), ("slide_right", -1)])
def test_slides_come_in_from_the_side_and_settle(made, anim, sign):
    run, tmp = made
    v = run(anim)
    early, late = at(v, tmp, 1.2), at(v, tmp, 2.6)
    assert early and late and sign * (center(early)[0] - center(late)[0]) > 5 and abs(center(early)[1] - center(late)[1]) < 2


def test_zoom_in_grows_to_full_size_around_the_same_centre(made):
    run, tmp = made
    v = run("zoom_in")
    early, late = at(v, tmp, 1.2), at(v, tmp, 2.6)
    assert early and late and (early[2] - early[0]) < (late[2] - late[0]) - 4
    assert abs(center(early)[0] - center(late)[0]) < 3 and abs(center(early)[1] - center(late)[1]) < 3


def test_zoom_out_starts_big_and_settles(made):
    run, tmp = made
    v = run("zoom_out")
    early, late = at(v, tmp, 1.2), at(v, tmp, 2.6)
    assert early and late and (early[2] - early[0]) > (late[2] - late[0]) + 4


def test_a_slow_push_in_keeps_growing_all_the_way(made):
    run, tmp = made
    v = run("pushin")
    a, b, c = at(v, tmp, 1.5), at(v, tmp, 2.4), at(v, tmp, 3.1)
    wa, wb, wc = (x[2] - x[0] for x in (a, b, c))
    assert wa < wb < wc


def test_an_unknown_movement_is_refused_when_set_and_a_plain_fade_when_stored(made, tmp_path):
    run, _ = made
    d = str(tmp_path / "p")
    run("fade")
    with pytest.raises(SystemExit, match="movements in the list"):
        O.add(d, {"kind": "text", "text": "x", "start": 0, "end": 2, "anim": "spin"})
    assert O.motion("spin", 0, 2, 0.3, 10, 10, (50, 20), W, H) == ("", "x=10:y=10")              # a stored value nobody can set still draws safely


def test_a_colour_backdrop_and_a_cover_picture_fill_the_frame(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    json.dump({"title": "T", "song": "s.wav"}, open(d / "project.json", "w"))
    json.dump({"duration": 4.0, "sections": [], "lyrics": []}, open(d / "songmap.json", "w"))
    fill = O.add(str(d), {"kind": "fill", "color": "#202060", "color2": "#aa3300", "start": 0, "end": 3, "cover": True})[0]
    png, size = O.render_png(str(d), fill, W, H)
    im = Image.open(png).convert("RGB")
    assert size == (W, H) and im.getpixel((10, 2))[2] > im.getpixel((10, H - 3))[2] and im.getpixel((10, H - 3))[0] > im.getpixel((10, 2))[0]    # a gradient from top to bottom
    pic = tmp_path / "wide.png"
    Image.new("RGB", (1000, 300), (200, 50, 50)).save(pic)
    cover = O.add(str(d), {"image": str(pic), "kind": "image", "cover": True, "start": 0, "end": 3, "anim": "pushin"})[-1]
    png, size = O.render_png(str(d), cover, W, H)
    assert size == (W, H)                                                                             # cropped to fill, never letterboxed
    assert O._position(cover, size, W, H) == (0, 0)


# ---------------------------------------------------------------- stage 3: wipe, typewriter, bounce, pop, pulse
def _film(d, path, seconds=8):
    from filmcrafter_engine.export import NO_WINDOW, ffmpeg
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x202020:s=320x180:r=12:d={seconds}", "-pix_fmt", "yuv420p", path],
                   check=True, creationflags=NO_WINDOW)


def _frame(path, t, out):
    from filmcrafter_engine.export import NO_WINDOW, ffmpeg
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", str(t), "-i", path, "-frames:v", "1", out], check=True, creationflags=NO_WINDOW)
    return Image.open(out).convert("RGB")


def _bright(im):
    return im.convert("L").point(lambda v: 255 if v > 160 else 0).getbbox()


def _burned(tmp_path, overlay, songmap=None):
    d = str(tmp_path / "p")
    os.makedirs(d)
    json.dump({"duration": 8.0, "sections": [], "lyrics": [], **(songmap or {})}, open(os.path.join(d, "songmap.json"), "w"))
    O.add(d, {"start": 1, "end": 6, "fade": 0.05, **overlay})
    v = str(tmp_path / "film.mp4")
    _film(d, v)
    r = O.burn(d, v, 320, 180, fps=12, duration=8.0)
    assert not r.get("error") and r["count"] == 1, r
    return v


def test_a_wipe_reveals_the_lettering_from_the_left(tmp_path):
    v = _burned(tmp_path, {"kind": "text", "text": "WIPE", "size": 0.3, "x": 0.5, "y": 0.5, "anim": "wipe", "color": "#ffffff", "shadow": False})
    early = _bright(_frame(v, 1.35, str(tmp_path / "a.png")))
    late = _bright(_frame(v, 4.0, str(tmp_path / "b.png")))
    assert late and (early is None or (early[2] - early[0]) < (late[2] - late[0]) * 0.8)             # only part of the width at first, all of it later
    assert early is None or early[0] <= late[0] + 3                                                    # and it grows rightwards from the left edge


def test_a_typewriter_shows_more_of_the_text_as_time_passes(tmp_path):
    v = _burned(tmp_path, {"kind": "text", "text": "TYPEWRITER", "size": 0.2, "x": 0.5, "y": 0.5, "anim": "typewriter", "color": "#ffffff", "shadow": False})
    widths = [(_bright(_frame(v, t, str(tmp_path / f"t{t}.png"))) or (0, 0, 0, 0)) for t in (1.1, 1.5, 4.0)]
    w = [b[2] - b[0] for b in widths]
    assert w[0] <= w[1] <= w[2] and w[2] > w[0] + 40


def test_a_bounce_comes_from_above_and_ends_in_place(tmp_path):
    v = _burned(tmp_path, {"kind": "shape", "shape": "rect", "width": 0.2, "height": 0.2, "x": 0.5, "y": 0.6, "anim": "bounce", "color": "#ffffff", "fade": 0.05})
    start = _bright(_frame(v, 1.05, str(tmp_path / "a.png")))
    end = _bright(_frame(v, 4.0, str(tmp_path / "b.png")))
    assert start and end and start[1] < end[1] - 8                                                      # higher at the start
    assert abs((end[1] + end[3]) / 2 - 0.6 * 180) < 4                                                    # settled where it was put


def test_a_pop_grows_from_small_and_a_pulse_swells_on_the_beat(tmp_path):
    v = _burned(tmp_path, {"kind": "shape", "shape": "rect", "width": 0.3, "height": 0.3, "x": 0.5, "y": 0.5, "anim": "pop", "color": "#ffffff", "fade": 0.05})
    first, later = _bright(_frame(v, 1.1, str(tmp_path / "a.png"))), _bright(_frame(v, 4.0, str(tmp_path / "b.png")))
    assert later and (first is None or (first[2] - first[0]) < (later[2] - later[0]) * 0.6)
    sm = {"bpm": 60.0, "downbeats": [0.0, 4.0], "beats": [0.0, 1.0, 2.0, 3.0, 4.0]}                      # one beat a second, on the second
    p = _burned(tmp_path / "pulse", {"kind": "shape", "shape": "rect", "width": 0.3, "height": 0.3, "x": 0.5, "y": 0.5, "anim": "pulse", "color": "#ffffff", "fade": 0.05}, sm) \
        if (tmp_path / "pulse").mkdir() is None else None
    on_beat, off_beat = _bright(_frame(p, 3.02, str(tmp_path / "c.png"))), _bright(_frame(p, 3.9, str(tmp_path / "d.png")))
    assert on_beat and off_beat and (on_beat[2] - on_beat[0]) > (off_beat[2] - off_beat[0]) + 2          # larger just after the beat than just before the next


def test_the_new_movements_are_in_the_list_and_old_projects_keep_working():
    assert {"wipe", "typewriter", "bounce", "pop", "pulse"} <= set(O.ANIMS) and all(a in O.ANIM_NAMES for a in O.ANIMS)
    assert O.beat_grid("/nonexistent") is None


def test_a_layer_swells_on_each_strong_hit_the_song_map_found(tmp_path):
    """'accent': a layer swells 8% on every accent in the song map and settles over a third of a second."""
    hits = [2.0, 3.5]
    v = _burned(tmp_path, {"kind": "shape", "shape": "rect", "width": 0.3, "height": 0.3, "x": 0.5, "y": 0.5, "anim": "accent", "color": "#ffffff", "fade": 0.05},
                {"accents": hits})

    def width(t):
        b = _bright(_frame(v, t, str(tmp_path / f"w{t}.png")))
        return b[2] - b[0]
    on, settled, before = width(2.0), width(2.6), width(1.5)
    assert on > settled + 3 and abs(settled - before) <= 1                                            # larger just after a hit; back to its own size between hits
    assert width(3.5) > width(3.0) + 3                                                                # and again on the second one


def test_accent_needs_hits_and_leaves_the_layer_still_without_them(tmp_path):
    assert "accent" in O.ANIMS and O.ANIM_NAMES["accent"]
    pre, pos = O.motion("accent", 1.0, 5.0, 0.4, 10, 10, (100, 20), 320, 180, None, 0, None)
    assert pre == "" and pos == "x=10:y=10"
    pre, pos = O.motion("accent", 1.0, 5.0, 0.4, 10, 10, (100, 20), 320, 180, None, 0, [9.0])         # none of them near this layer
    assert pre == "" and pos == "x=10:y=10"
