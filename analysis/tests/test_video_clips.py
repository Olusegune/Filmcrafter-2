"""Video clips as layers: a clip put over the film (a picture-in-picture, a green-screen subject), trimmed, looped, mixed and keyed. Checked on real encoded video (noisy, chroma-subsampled, compressed like
footage is) through the real export; the file checks are the ones that keep a bad or hostile file out. Nothing here is generated or charged."""
import json
import os
import shutil

import pytest
from PIL import Image

from filmcrafter_engine import export as E, overlays as O
from tests.test_editing import build_film, ff

pytestmark = pytest.mark.integration

GREEN, RED = "0x00b140", "0xd02020"


@pytest.fixture
def film(tmp_path):
    return build_film(tmp_path, [("S01-01", 1, 0.0, 6.0), ("S01-02", 1, 6.0, 12.0)], 12.0)


def green_screen(path, seconds=3):
    """A green screen with a red subject in the middle, with sensor noise, compressed and chroma-subsampled like real footage."""
    ff("-f", "lavfi", "-i", f"color=c={GREEN}:s=320x180:r=24:d={seconds}", "-vf", f"drawbox=x=110:y=50:w=100:h=80:color={RED}:t=fill,noise=alls=10:allf=t,format=yuv420p",
       "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p", path)
    return path


def red_then_blue(path):
    ff("-f", "lavfi", "-i", "color=c=red:s=320x180:r=24:d=1", "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=24:d=2", "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0,format=yuv420p",
       "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", path)
    return path


def frame_of(video, n, tmp_path, name):
    p = str(tmp_path / f"{name}.png")
    ff("-i", video, "-vf", f"select='eq(n,{n})'", "-frames:v", "1", p)
    return Image.open(p).convert("RGB")


def mean(im, fx0, fy0, fx1, fy1):
    w, h = im.size
    px = list(im.crop((int(fx0 * w), int(fy0 * h), int(fx1 * w), int(fy1 * h))).get_flattened_data() if hasattr(im, "get_flattened_data") else im.crop((int(fx0 * w), int(fy0 * h), int(fx1 * w), int(fy1 * h))).getdata())
    return tuple(sum(p[i] for p in px) / len(px) for i in range(3))


def made(film, tmp_path, name):
    out = str(tmp_path / f"{name}.mp4")
    shutil.copy(E.build(film, "preview")["path"], out)
    return out


def clip_layer(film, src, **kw):
    return O.add(film, {"video": src, "width": 1.0, "x": 0.5, "y": 0.5, "start": 1.0, "end": 4.0, "anim": "fade", "fade": 0.2, **kw})[-1]


# ---------------------------------------------------------------- what may be added

def test_a_real_clip_is_copied_in_with_its_size_and_length_and_the_original_is_untouched(film, tmp_path):
    src = green_screen(str(tmp_path / "gs.mp4"))
    before = open(src, "rb").read()
    o = clip_layer(film, src)
    assert o["kind"] == "clip" and o["file"].startswith("assets/overlays/") and os.path.isfile(os.path.join(film, o["file"]))
    assert (o["src_w"], o["src_h"]) == (320, 180) and 2.9 < o["src_dur"] < 3.1
    assert open(src, "rb").read() == before and o["text"] == "gs.mp4"


def test_without_an_end_a_clip_plays_to_its_end_but_never_longer_than_ten_seconds(film, tmp_path):
    src = green_screen(str(tmp_path / "gs.mp4"))
    o = O.add(film, {"video": src, "start": 2.0})[-1]
    assert o["end"] == pytest.approx(2.0 + o["src_dur"], abs=0.01)
    long_ = str(tmp_path / "long.mp4")
    ff("-f", "lavfi", "-i", "color=c=gray:s=64x36:r=12:d=30", "-c:v", "libx264", "-pix_fmt", "yuv420p", long_)
    assert O.add(film, {"video": long_, "start": 0.0})[-1]["end"] == pytest.approx(10.0)


def test_things_that_are_not_usable_video_are_refused_with_a_plain_reason_and_nothing_is_added(film, tmp_path):
    before = O.load(film)
    text = tmp_path / "fake.mp4"
    text.write_text("not a video at all")
    audio = str(tmp_path / "audio.mp4")
    ff("-f", "lavfi", "-i", "sine=frequency=440:d=1", "-c:a", "aac", audio)
    exe = tmp_path / "x.exe"
    exe.write_bytes(b"MZ")
    for bad, why in ((str(text), "picture FilmCrafter can read"), (audio, "picture FilmCrafter can read"), (str(exe), "MP4, MOV"), (str(tmp_path / "gone.mp4"), "MP4, MOV"), (str(tmp_path), "MP4, MOV")):
        with pytest.raises(SystemExit, match=why):
            O.add(film, {"video": bad, "start": 0})
    assert O.load(film) == before
    assert not os.path.isdir(os.path.join(film, "assets", "overlays")) or not os.listdir(os.path.join(film, "assets", "overlays"))


def test_a_huge_file_and_too_many_clips_are_refused(film, tmp_path, monkeypatch):
    src = green_screen(str(tmp_path / "gs.mp4"), 1)
    monkeypatch.setattr(O, "MAX_CLIP", 100)
    with pytest.raises(SystemExit, match="too large"):
        O.add(film, {"video": src, "start": 0})
    monkeypatch.undo()
    for _ in range(O.MAX_CLIPS):
        O.add(film, {"video": src, "start": 0})
    with pytest.raises(SystemExit, match="video clips at most"):
        O.add(film, {"video": src, "start": 0})


def test_what_a_clip_cannot_do_yet_is_said_not_silently_ignored(film, tmp_path):
    o = clip_layer(film, green_screen(str(tmp_path / "gs.mp4")))
    for bad in ({"glow": 0.5}, {"blur": 0.4}, {"mask": "ellipse"}):
        with pytest.raises(SystemExit, match="not available for video clips"):
            O.update(film, o["id"], bad)
    ok = O.update(film, o["id"], {"key_color": "#00b140", "blend": "screen", "opacity": 0.8, "in_s": 0.5, "loop": True, "rotation": 30})
    got = next(x for x in ok if x["id"] == o["id"])
    assert got["key_color"] == "#00b140" and got["blend"] == "screen" and got["in_s"] == 0.5 and got["loop"] is True and "rotation" not in got
    assert "loop" not in next(x for x in O.update(film, o["id"], {"loop": False}) if x["id"] == o["id"])
    with pytest.raises(SystemExit):
        O.update(film, o["id"], {"in_s": "soon"})


def test_a_tampered_project_cannot_make_a_clip_read_a_file_outside_it(film, tmp_path):
    src = green_screen(str(tmp_path / "gs.mp4"), 1)
    outside = tmp_path / "secret.mp4"
    shutil.copy(src, outside)
    o = clip_layer(film, src)
    items = json.load(open(os.path.join(film, "overlays.json")))
    for entry in (items["overlays"] if isinstance(items, dict) else items):
        if entry["id"] == o["id"]:
            entry["file"] = "../secret.mp4"
    json.dump(items, open(os.path.join(film, "overlays.json"), "w"))
    with pytest.raises(SystemExit, match="is missing"):
        O.clip_path(film, next(x for x in O.load(film) if x["id"] == o["id"]))
    for entry in (items["overlays"] if isinstance(items, dict) else items):
        entry["file"] = "overlays.json"                                                  # not a video extension either
    json.dump(items, open(os.path.join(film, "overlays.json"), "w"))
    with pytest.raises(SystemExit, match="is missing"):
        O.clip_path(film, next(x for x in O.load(film) if x["id"] == o["id"]))


def test_the_filters_only_contain_numbers_and_a_parsed_colour(film):
    base = {"src_w": 320, "src_h": 180, "width": 0.5}
    vf = O.clip_filters({**base, "key_color": "#00b140; movie=/etc/passwd", "key_tol": 9, "key_spill": -3, "opacity": 0.5}, 320, 180, 24)
    assert ";" not in vf and "movie" not in vf and "passwd" not in vf
    assert "chromakey=color=0x" in vf and "similarity=0.400" in vf and "despill" not in vf and "aa=0.500" in vf
    assert "despill=type=green" in O.clip_filters({**base, "key_color": "#00ff00"}, 320, 180, 24)
    assert "despill=type=blue" in O.clip_filters({**base, "key_color": "#0000ff"}, 320, 180, 24)
    assert "despill" not in O.clip_filters({**base, "key_color": "#ff0000"}, 320, 180, 24)           # spill is a green or blue screen's problem
    for bad in ({"src_w": 0, "src_h": 9}, {"src_w": "320", "src_h": 180}, {"src_w": 99999, "src_h": 9}, {}):
        with pytest.raises(SystemExit):
            O.clip_size(bad, 640)
    w, h = O.clip_size(base, 641)
    assert w % 2 == 0 and h % 2 == 0 and abs(w / h - 320 / 180) < 0.05


def test_the_first_frame_picture_is_cut_out_like_the_film_will_be(film, tmp_path):
    o = clip_layer(film, green_screen(str(tmp_path / "gs.mp4")), width=0.5)
    plain, size = O.render_png(film, o, 640, 360)
    keyed, _ = O.render_png(film, O._clean(film, {"key_color": "#00b140"}, o), 640, 360)
    assert size == (320, 180) and plain != keyed
    a, b = Image.open(plain).convert("RGBA"), Image.open(keyed).convert("RGBA")
    assert a.getpixel((5, 5))[3] == 255 and b.getpixel((5, 5))[3] == 0 and b.getpixel((160, 90))[3] == 255          # the screen is gone, the subject stays


# ---------------------------------------------------------------- in the finished film

def test_a_clip_covers_the_film_while_it_is_up_and_a_key_lets_the_film_show_through(film, tmp_path):
    src = green_screen(str(tmp_path / "gs.mp4"))
    plain = made(film, tmp_path, "plain")
    o = clip_layer(film, src)
    covered = made(film, tmp_path, "covered")
    O.update(film, o["id"], {"key_color": "#00b140", "key_tol": 0.35, "key_soft": 0.15, "key_spill": 0.6})
    keyed = made(film, tmp_path, "keyed")
    n = 24 * 2 + 12                                                                         # 2.5 s: the clip is fully up
    base, cov, key = (frame_of(v, n, tmp_path, t) for v, t in ((plain, "b"), (covered, "c"), (keyed, "k")))
    corner = (0.02, 0.05, 0.12, 0.2)
    g = mean(cov, *corner)
    assert g[1] > g[0] + 60 and g[1] > g[2] + 60                                              # without the key: a green screen over the picture
    k, b = mean(key, *corner), mean(base, *corner)
    assert all(abs(k[i] - b[i]) < 22 for i in range(3)), (k, b)                               # with it: the film as it was, where the screen was
    s = mean(key, 0.46, 0.4, 0.54, 0.6)
    assert s[0] > 140 and s[1] < 100 and s[2] < 100, s                                        # and the red subject stays
    w, h = key.size                                                                          # no green fringe around the subject's edge, though the screen was noisy
    ring = [key.getpixel((x, y)) for x in range(int(w * 0.33) - 3, int(w * 0.33) + 4) for y in range(int(h * 0.3), int(h * 0.7))]
    green = [p for p in ring if p[1] > p[0] + 45 and p[1] > p[2] + 45]
    assert len(green) <= len(ring) * 0.06, len(green)
    early_a, early_b = frame_of(plain, 12, tmp_path, "ea"), frame_of(keyed, 12, tmp_path, "eb")      # 0.5 s: before it starts
    late_a, late_b = frame_of(plain, 24 * 5, tmp_path, "la"), frame_of(keyed, 24 * 5, tmp_path, "lb")  # 5 s: after it has ended
    for x, y in ((early_a, early_b), (late_a, late_b)):
        assert all(abs(p - q) < 25 for p, q in zip(mean(x, 0, 0, 1, 1), mean(y, 0, 0, 1, 1)))


def test_a_clip_starts_where_asked_in_its_own_time(film, tmp_path):
    src = red_then_blue(str(tmp_path / "rb.mp4"))
    o = clip_layer(film, src)
    first = frame_of(made(film, tmp_path, "from0"), 24 * 1 + 14, tmp_path, "f0")                  # 1.6 s: 0.6 s into the clip
    O.update(film, o["id"], {"in_s": 1.0})
    later = frame_of(made(film, tmp_path, "from1"), 24 * 1 + 14, tmp_path, "f1")
    r, b = mean(first, 0.3, 0.3, 0.7, 0.7), mean(later, 0.3, 0.3, 0.7, 0.7)
    assert r[0] > r[2] + 80 and b[2] > b[0] + 80, (r, b)                                        # the first second is red, then it is blue


def test_a_short_clip_ends_unless_it_is_looped(film, tmp_path):
    src = red_then_blue(str(tmp_path / "rb.mp4"))
    plain = made(film, tmp_path, "plain")
    o = clip_layer(film, src, end=6.0)
    O.update(film, o["id"], {"in_s": 0.0})
    short = O.load(film)
    n = 24 * 5                                                                                # 5 s: the 3-second clip, started at 1 s, ended at 4 s
    ended = frame_of(made(film, tmp_path, "ended"), n, tmp_path, "e")
    assert all(abs(p - q) < 25 for p, q in zip(mean(ended, 0, 0, 1, 1), mean(frame_of(plain, n, tmp_path, "pl"), 0, 0, 1, 1)))
    O.update(film, o["id"], {"loop": True})
    looped = frame_of(made(film, tmp_path, "looped"), n, tmp_path, "lp")
    m = mean(looped, 0.3, 0.3, 0.7, 0.7)
    assert max(m[0], m[2]) > 150, m                                                           # still showing: the clip began again
    assert short


def test_a_clip_can_be_mixed_with_the_picture_and_sits_with_other_layers(film, tmp_path):
    src = green_screen(str(tmp_path / "gs.mp4"))
    O.add(film, {"kind": "text", "text": "Hello", "start": 0.5, "end": 5.0, "size": 0.1, "x": 0.5, "y": 0.2})
    c = clip_layer(film, src, width=0.5, key_color="#00b140", blend="screen")
    O.add(film, {"kind": "fill", "color": "#3050a0", "start": 2.0, "end": 6.0, "blend": "softlight", "anim": "fade"})
    out = E.build(film, "preview")
    assert not out.get("overlay_error") and out["overlays"] == 3 and os.path.getsize(out["path"]) > 1000
    assert next(x for x in O.load(film) if x["id"] == c["id"])["blend"] == "screen"


def test_a_clip_with_a_missing_file_stops_the_overlay_pass_with_a_reason_but_not_the_film(film, tmp_path):
    src = green_screen(str(tmp_path / "gs.mp4"))
    o = clip_layer(film, src)
    os.remove(os.path.join(film, o["file"]))
    out = E.build(film, "preview")
    assert os.path.isfile(out["path"]) and "missing" in (out.get("overlay_error") or "")                # the film is still made; what went wrong is said


def test_no_number_the_screen_sends_may_be_nan_or_infinite_anywhere(film, tmp_path):
    o = clip_layer(film, green_screen(str(tmp_path / "gs.mp4"), 1), key_color="#00b140", mask=None)
    for k in ("start", "end", "x", "y", "width", "in_s", "opacity", "fade", "key_tol", "key_soft", "key_spill"):
        for bad in ("nan", "inf", "-inf", float("inf"), float("nan"), "1e999"):
            with pytest.raises(SystemExit):
                O.update(film, o["id"], {k: bad})
    t = O.add(film, {"kind": "text", "text": "x", "start": 0, "end": 2})[-1]
    for k in ("glow", "blur", "mask_size", "mask_feather", "size", "scale", "rotation", "stroke_w"):
        for bad in ("nan", "inf", float("inf")):
            with pytest.raises(SystemExit):
                O.update(film, t["id"], {k: bad, **({"mask": "ellipse"} if k.startswith("mask") else {})})


def test_a_video_that_will_not_be_read_in_time_is_refused_or_left_out_with_a_reason_not_waited_for_forever(film, tmp_path, monkeypatch):
    import subprocess
    src = green_screen(str(tmp_path / "gs.mp4"), 1)
    real = subprocess.run

    def slow(cmd, *a, **k):
        raise subprocess.TimeoutExpired(cmd, k.get("timeout", 1))
    o = clip_layer(film, src)
    monkeypatch.setattr(subprocess, "run", slow)
    with pytest.raises(SystemExit, match="took too long"):
        O.render_png(film, {**o, "in_s": 0.3}, 640, 360)                                       # the first-frame picture
    with pytest.raises(SystemExit, match="picture FilmCrafter can read"):
        O.add(film, {"video": src, "start": 0})                                                # describing the file
    monkeypatch.setattr(subprocess, "run", real)
