"""Shapes and icons as layers: what each draws, the outline and see-through options, rotation, the icon set matching the screen's copy, and the result on real video."""
import json
import os
import subprocess

import pytest
from PIL import Image

from filmcrafter_engine import overlays as O, shapes as S
from filmcrafter_engine.export import NO_WINDOW, ffmpeg

W, H = 640, 360


def draw(**kw):
    o = {"kind": "shape", "shape": "rect", "width": 0.5, "height": 0.5, "color": "#ff0000", **kw}
    return O.render_image("/nonexistent", o, W, H)


def test_a_rectangle_fills_the_size_asked_for_and_nothing_outside_it():
    im = draw()
    assert im.size == (320, 180) and im.getpixel((160, 90)) == (255, 0, 0, 255) and im.getpixel((2, 2))[3] == 255


def test_a_circle_leaves_its_corners_empty_and_a_rounded_box_only_the_very_corner():
    c = draw(shape="circle")
    assert c.getpixel((160, 90))[3] == 255 and c.getpixel((2, 2))[3] == 0
    r = draw(shape="rounded", radius=0.3)
    assert r.getpixel((0, 0))[3] == 0 and r.getpixel((40, 40))[3] == 255


def test_a_line_is_thin_and_opacity_makes_it_see_through():
    ln = draw(shape="line", width=0.8, height=None)
    assert ln.size[0] == 512 and ln.size[1] <= 4
    half = draw(opacity=0.5)
    assert 120 <= half.getpixel((160, 90))[3] <= 135


def test_an_outline_is_drawn_inside_the_box_and_an_unfilled_shape_is_hollow():
    both = draw(stroke="#00ff00", stroke_w=0.05, color="#0000ff")
    assert both.getpixel((3, 90))[:3] == (0, 255, 0) and both.getpixel((160, 90))[:3] == (0, 0, 255) and both.size == (320, 180)
    hollow = draw(stroke="#00ff00", stroke_w=0.05, filled=False)
    assert hollow.getpixel((3, 90))[:3] == (0, 255, 0) and hollow.getpixel((160, 90))[3] == 0


def test_rotation_turns_clockwise_and_the_picture_grows_to_hold_it():
    wide = draw(width=0.5, height=0.1)
    assert wide.size == (320, 36)
    turned = draw(width=0.5, height=0.1, rotation=90)
    assert turned.size == (36, 320)
    tilt = draw(width=0.5, height=0.1, rotation=45)
    assert tilt.size[0] == tilt.size[1] and tilt.size[0] > 200


def test_every_icon_draws_in_the_chosen_colour_inside_its_square():
    for name in S.ICONS:
        im = O.render_image("/x", {"kind": "icon", "icon": name, "width": 0.2, "color": "#ffd166"}, W, H)
        assert im.size == (128, 128), name
        px = [p for p in im.getdata() if p[3] > 250]
        assert len(px) > 600 and all(abs(p[0] - 255) < 3 and abs(p[1] - 209) < 3 for p in px[:50]), name
    star = O.render_image("/x", {"kind": "icon", "icon": "star", "width": 0.2, "color": "#ffffff"}, W, H)
    assert star.getpixel((64, 70))[3] == 255 and star.getpixel((2, 2))[3] == 0


def test_the_icon_outlines_are_the_same_in_the_engine_and_on_the_screen():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "src", "shapeIcons.json")
    if not os.path.exists(path):
        pytest.skip("the screen's copy is not in this checkout")
    assert json.load(open(path, encoding="utf-8")) == S.ICONS


def test_adding_and_updating_shapes_validates_and_clamps(tmp_path):
    d = str(tmp_path)
    out = O.add(d, {"kind": "shape", "shape": "circle", "width": 0.2, "height": 0.2, "x": 0.5, "y": 0.5, "start": 0, "end": 4, "opacity": 7, "rotation": 400})
    o = out[0]
    assert o["kind"] == "shape" and o["opacity"] == 1.0 and o["rotation"] == 180.0 and o["stroke"] == "#ffffff"
    out = O.update(d, o["id"], {"shape": "line", "stroke_w": 5, "filled": False})
    assert out[0]["shape"] == "line" and out[0]["stroke_w"] == 0.05 and out[0]["filled"] is False
    ic = O.add(d, {"kind": "icon", "icon": "heart", "start": 0, "end": 4})[1]
    assert ic["icon"] == "heart"
    with pytest.raises(SystemExit, match="rectangle, rounded box, circle or line"):
        O.add(d, {"kind": "shape", "shape": "blob", "start": 0, "end": 4})
    with pytest.raises(SystemExit, match="icons in the list"):
        O.add(d, {"kind": "icon", "icon": "skull", "start": 0, "end": 4})
    assert len(O.load(d)) == 2


def test_a_shape_and_an_icon_are_on_the_real_video_where_they_were_put(tmp_path):
    d = str(tmp_path / "p")
    os.makedirs(d)
    json.dump({"duration": 6.0, "sections": [], "lyrics": []}, open(os.path.join(d, "songmap.json"), "w"))
    O.add(d, {"kind": "shape", "shape": "rect", "width": 0.3, "height": 0.3, "x": 0.25, "y": 0.5, "color": "#ff0000", "start": 0, "end": 5, "fade": 0.1})
    O.add(d, {"kind": "icon", "icon": "diamond", "width": 0.2, "x": 0.75, "y": 0.5, "color": "#00ff00", "start": 0, "end": 5, "fade": 0.1})
    v = str(tmp_path / "film.mp4")
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0x303030:s=320x180:r=12:d=6", "-pix_fmt", "yuv420p", v], check=True, creationflags=NO_WINDOW)
    r = O.burn(d, v, 320, 180, fps=12, duration=6.0)
    assert not r.get("error") and r["count"] == 2
    png = str(tmp_path / "f.png")
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", "2", "-i", v, "-frames:v", "1", png], check=True, creationflags=NO_WINDOW)
    im = Image.open(png).convert("RGB")
    red, green = im.getpixel((80, 90)), im.getpixel((240, 90))
    assert red[0] > 200 and red[1] < 60 and green[1] > 180 and green[0] < 60                      # a red box on the left, a green diamond on the right
    assert abs(im.getpixel((160, 90))[0] - 0x30) < 12                                              # the film between them is untouched


def text(**kw):
    return O.render_image("/nonexistent", {"kind": "text", "text": "HELLO", "size": 0.2, "color": "#ff0000", **kw}, W, H)


def test_a_gradient_runs_the_way_css_draws_it():
    up = S.gradient((100, 100), (0, 0, 0), (255, 255, 255), 0)                  # 0 degrees: towards the top, so the second colour is at the top
    assert up.getpixel((50, 2))[0] > 240 and up.getpixel((50, 97))[0] < 15
    right = S.gradient((100, 100), (0, 0, 0), (255, 255, 255), 90)
    assert right.getpixel((97, 50))[0] > 240 and right.getpixel((2, 50))[0] < 15
    down = S.gradient((100, 100), (0, 0, 0), (255, 255, 255), 180)
    assert down.getpixel((50, 97))[0] > 240 and down.getpixel((50, 2))[0] < 15


def test_a_shape_can_be_filled_with_a_gradient():
    im = draw(gradient=True, color2="#0000ff", angle=180)
    assert im.getpixel((160, 4))[:3][0] > 230 and im.getpixel((160, 175))[2] > 230


def test_lettering_can_have_a_gradient_an_outline_a_rotation_and_a_scale():
    plain = text()
    reds = [p for p in plain.getdata() if p[3] > 250]
    assert reds and all(p[0] > 240 and p[1] < 20 for p in reds[:40])
    grad = text(gradient=True, color2="#0000ff", angle=180)
    gs = [p for p in grad.getdata() if p[3] > 250]
    assert any(p[0] > p[2] + 100 for p in gs) and any(p[2] > p[0] + 100 for p in gs)             # red towards the top, blue towards the bottom
    out = text(stroke="#00ff00", stroke_w=0.02)
    assert out.size[0] > plain.size[0] and any(p[1] > 200 and p[0] < 60 and p[3] > 250 for p in out.getdata())
    turned = text(rotation=90)
    assert turned.size[0] < turned.size[1] and abs(turned.size[1] - plain.size[0]) < 20                  # lying on its side
    big = text(scale=2)
    assert big.size[0] > plain.size[0] * 1.6 and big.size[1] > plain.size[1] * 1.6


def test_the_shadow_can_be_switched_off_and_a_picture_can_be_turned_and_made_see_through(tmp_path):
    shadowed = text()
    flat = text(shadow=False)
    assert flat.size[0] < shadowed.size[0] and flat.size[1] < shadowed.size[1]                          # no room kept for the soft shadow
    pic = tmp_path / "a.png"
    Image.new("RGB", (200, 100), (0, 0, 255)).save(pic)
    d = str(tmp_path)
    os_dir = os.path.join(d, "assets", "overlays")
    os.makedirs(os_dir)
    Image.open(pic).save(os.path.join(os_dir, "a.png"))
    base = {"kind": "image", "file": "assets/overlays/a.png", "width": 0.3, "shadow": False}
    plain = O.render_image(d, base, W, H)
    turned = O.render_image(d, {**base, "rotation": 90, "opacity": 0.5}, W, H)
    assert plain.size[0] > plain.size[1] and turned.size == plain.size[::-1] and turned.getpixel((20, 60))[3] in range(120, 136)
