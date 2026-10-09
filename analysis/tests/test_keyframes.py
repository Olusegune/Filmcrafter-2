"""Keyframes on layers: cleaning, the curve itself, and the result on real video matching the curve."""
import json
import os
import subprocess

import pytest
from PIL import Image

from pulseframe_analysis import overlays as O
from pulseframe_analysis.export import NO_WINDOW, ffmpeg


def test_keys_are_checked_sorted_and_clamped():
    keys = O.clean_keys([{"t": 2, "x": 0.9, "ease": "linear"}, {"t": 0, "x": 0.1, "opacity": 7, "scale": 0}, {"t": 2, "x": 0.8}])
    assert [k["t"] for k in keys] == [0.0, 2.0] and keys[0]["opacity"] == 1.0 and keys[0]["scale"] == 0.05 and keys[1]["x"] == 0.8        # the later key at the same moment wins
    assert O.clean_keys(None) == [] and O.clean_keys([]) == []
    with pytest.raises(SystemExit, match="12 keyframes"):
        O.clean_keys([{"t": i} for i in range(13)])
    with pytest.raises(SystemExit, match="easings in the list"):
        O.clean_keys([{"t": 0, "ease": "wobble"}])
    with pytest.raises(SystemExit, match="needs a time"):
        O.clean_keys([{"x": 0.5}])
    with pytest.raises(SystemExit, match="must be a number"):
        O.clean_keys([{"t": 0, "x": "left"}])


# the same cases are checked against the screen's copy of the curve in src/__tests__/overlayKeys.test.ts
VECTORS = [
    ([{"t": 0, "x": 0.2, "ease": "linear"}, {"t": 2, "x": 0.8}], 1.0, {"x": 0.5}),
    ([{"t": 0, "x": 0.0, "ease": "ease_in"}, {"t": 2, "x": 1.0}], 1.0, {"x": 0.25}),
    ([{"t": 0, "x": 0.0, "ease": "ease_out"}, {"t": 2, "x": 1.0}], 1.0, {"x": 0.75}),
    ([{"t": 0, "x": 0.0, "ease": "ease_in_out"}, {"t": 2, "x": 1.0}], 0.5, {"x": 0.15625}),
    ([{"t": 0, "x": 0.0, "ease": "hold"}, {"t": 2, "x": 1.0}], 1.9, {"x": 0.0}),
    ([{"t": 1, "x": 0.3}, {"t": 3, "x": 0.7}], 0.0, {"x": 0.3}),
    ([{"t": 1, "x": 0.3}, {"t": 3, "x": 0.7}], 9.0, {"x": 0.7}),
    ([{"t": 0, "x": 0.1, "ease": "linear"}, {"t": 1, "scale": 2}, {"t": 2, "x": 0.5}], 1.0, {"x": 0.3, "scale": 2.0}),       # a key that leaves a property out does not touch it
]


@pytest.mark.parametrize("keys,t,want", VECTORS)
def test_the_curve_matches_the_agreed_values(keys, t, want):
    got = O.eval_keys(O.clean_keys(keys), t)
    assert got.keys() == want.keys() and all(abs(got[k] - want[k]) < 1e-3 for k in want)


def test_the_ffmpeg_expression_says_the_same_as_the_curve():
    # the expression is checked on real frames below; here its shape: nested ifs of the layer's own clock, none for a property no key sets
    keys = O.clean_keys([{"t": 0, "x": 0.2, "ease": "linear"}, {"t": 2, "x": 0.8}])
    e = O.key_expr(keys, "x", "(t-1.000)")
    assert e.startswith("if(lt((t-1.000),0.000),0.2000,") and "0.8000" in e and O.key_expr(keys, "y", "(t-1.000)") is None


def _frame(v, t, out):
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", str(t), "-i", v, "-frames:v", "1", out], check=True, creationflags=NO_WINDOW)
    return Image.open(out).convert("RGB")


def _box(im, thresh=160):
    return im.convert("L").point(lambda p: 255 if p > thresh else 0).getbbox()


def _film(tmp_path, layer, seconds=8):
    d = str(tmp_path / "p")
    os.makedirs(d)
    json.dump({"duration": float(seconds), "sections": [], "lyrics": []}, open(os.path.join(d, "songmap.json"), "w"))
    O.add(d, {"start": 1, "end": 6, "fade": 0.05, **layer})
    v = str(tmp_path / "film.mp4")
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x202020:s=320x180:r=12:d={seconds}", "-pix_fmt", "yuv420p", v],
                   check=True, creationflags=NO_WINDOW)
    r = O.burn(d, v, 320, 180, fps=12, duration=float(seconds))
    assert not r.get("error") and r["count"] == 1, r
    return v


def test_a_layer_travels_where_its_keyframes_say(tmp_path):
    v = _film(tmp_path, {"kind": "shape", "shape": "rect", "width": 0.1, "height": 0.2, "x": 0.5, "y": 0.5, "color": "#ffffff", "shadow": False,
                         "keys": [{"t": 0, "x": 0.2, "y": 0.5, "ease": "linear"}, {"t": 2, "x": 0.8, "y": 0.5}]})
    for t, want in ((1.5, 0.2 + 0.6 * 0.25), (2.0, 0.5), (3.0, 0.8), (5.0, 0.8)):             # a quarter of the way, half way, arrived, and still there
        b = _box(_frame(v, t, str(tmp_path / f"f{t}.png")))
        assert b and abs((b[0] + b[2]) / 2 - want * 320) < 7, (t, b)


def test_scale_rotation_and_opacity_keys_change_what_is_drawn(tmp_path):
    v = _film(tmp_path, {"kind": "shape", "shape": "rect", "width": 0.2, "height": 0.1, "x": 0.5, "y": 0.5, "color": "#ffffff", "fade": 0.05,
                         "keys": [{"t": 0, "scale": 1, "rotation": 0, "opacity": 1, "ease": "linear"}, {"t": 2, "scale": 2, "rotation": 90, "opacity": 0.5}]})
    start = _box(_frame(v, 1.1, str(tmp_path / "a.png")))
    end = _box(_frame(v, 4.0, str(tmp_path / "b.png")), thresh=80)
    assert start and end
    assert (start[2] - start[0]) > (start[3] - start[1]) * 1.5                                    # wide at first
    assert (end[3] - end[1]) > (end[2] - end[0]) * 1.2 and (end[3] - end[1]) > (start[3] - start[1]) * 1.6   # on its side and about twice the size by the end
    px = _frame(v, 4.0, str(tmp_path / "c.png")).getpixel((160, 90))
    assert 110 < px[0] < 190                                                                       # half see-through over the dark film (about 0x20 + half of the rest)


def test_a_layer_with_keys_ignores_its_preset_and_survives_an_update(tmp_path):
    d = str(tmp_path)
    o = O.add(d, {"kind": "text", "text": "Hi", "start": 0, "end": 4, "anim": "typewriter", "keys": [{"t": 0, "x": 0.1}, {"t": 2, "x": 0.9}]})[0]
    assert len(o["keys"]) == 2
    out = O.update(d, o["id"], {"text": "Hello"})[0]
    assert out["text"] == "Hello" and len(out["keys"]) == 2
    assert "keys" not in O.update(d, o["id"], {"keys": []})[0]


def test_a_film_with_many_layers_is_drawn_in_slices_that_join_seamlessly(tmp_path, monkeypatch):
    """A real 3 minute film with 87 layers needed about 17 GB of memory in one pass. With many layers each pass now draws only the layers that are up during
    its slice; the slices are joined without re-encoding and the sound is kept. A travelling shape must not jump where two slices meet."""
    monkeypatch.setattr(O, "BATCH", 2)
    monkeypatch.setattr(O, "SLICE", 2.0)
    monkeypatch.setattr(O, "MIN_SLICE", 0.5)
    d = str(tmp_path / "p")
    os.makedirs(d)
    json.dump({"duration": 8.0, "sections": [], "lyrics": [], "bpm": 120.0, "downbeats": [0.0]}, open(os.path.join(d, "songmap.json"), "w"))
    O.add(d, {"kind": "shape", "shape": "rect", "width": 0.1, "height": 0.2, "x": 0.5, "y": 0.75, "color": "#ffffff", "start": 0.5, "end": 7.5, "fade": 0.05,
              "keys": [{"t": 0, "x": 0.2, "ease": "linear"}, {"t": 7, "x": 0.8}]})
    for i in range(6):
        O.add(d, {"kind": "text", "text": f"L{i}", "start": 0.4 + i * 1.2, "end": 1.4 + i * 1.2, "size": 0.15, "x": 0.5, "y": 0.2, "fade": 0.05, "shadow": False})
    v = str(tmp_path / "film.mp4")
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0x202020:s=320x180:r=12:d=8", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
                    "-t", "8", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", v], check=True, creationflags=NO_WINDOW)
    def frames(path):
        p = subprocess.run([ffmpeg(), "-hide_banner", "-i", path, "-map", "0:v:0", "-c", "copy", "-f", "null", "-"], capture_output=True, text=True, creationflags=NO_WINDOW)
        import re
        return int(re.findall(r"frame=\s*(\d+)", p.stderr)[-1]), "Audio:" in p.stderr
    before = frames(v)
    assert before[0] == 96
    assert len(O._passes([o for o in O.resolve(d)], 96, 12)) >= 3
    r = O.burn(d, v, 320, 180, fps=12, duration=8.0)
    assert not r.get("error") and r["count"] == 7, r
    assert frames(v) == before and frames(v)[1]                                                       # the same number of frames, and the sound is still there
    seq = tmp_path / "seq"
    seq.mkdir()
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", v, str(seq / "f%03d.png")], check=True, creationflags=NO_WINDOW)
    assert len(list(seq.iterdir())) == 96                                                              # decoding gives every frame too: no join drops or repeats one
    for i in range(1, 97):
        t = (i - 1) / 12
        low = Image.open(seq / f"f{i:03d}.png").convert("L").crop((0, 100, 320, 180)).point(lambda p: 255 if p > 200 else 0).getbbox()
        if 0.6 <= t <= 7.4:                                                                            # the shape is up (it fades in and out over a twentieth of a second)
            want = (0.2 + 0.6 * (t - 0.5) / 7) * 320
            assert low and abs((low[0] + low[2]) / 2 - want) < 2.5, (i, t, low, want)                # on both sides of every join, one smooth line
    top = _box(_frame(v, 1.0, str(tmp_path / "top.png")).crop((0, 0, 320, 70)), thresh=200)
    assert top                                                                                         # the first line is up at 1.0 s
