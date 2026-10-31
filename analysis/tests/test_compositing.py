"""Compositing: blend modes, masks and colour keys on layers. Checked on real pictures and real exports; nothing is generated or charged."""
import os
import shutil

import pytest
from PIL import Image

from filmcrafter_engine import composite as C, export as E, layerkit as K, overlays as O
from tests.test_editing import build_film, ff

pytestmark = pytest.mark.integration


@pytest.fixture
def film(tmp_path):
    return build_film(tmp_path, [("S01-01", 1, 0.0, 6.0), ("S01-02", 1, 6.0, 12.0)], 12.0)


def px(im, x, y):
    return im.convert("RGBA").getpixel((x, y))


# ---------------------------------------------------------------- what the screen may send

def test_a_blend_mode_is_one_of_a_fixed_list_and_never_typed_into_the_filter(film):
    o = O._clean(film, {"kind": "fill", "start": 0, "end": 2, "blend": "Multiply"})
    assert o["blend"] == "multiply"
    assert "blend" not in O._clean(film, {"blend": "normal"}, o)
    assert O._clean(film, {"blend": "soft light"}, o)["blend"] == "softlight"
    for bad in ("multiply;movie=/etc/passwd", "burn", "multiply,scale=1:1", "[x]", "../../x"):
        with pytest.raises(SystemExit, match="blend modes"):
            O._clean(film, {"blend": bad}, o)
    with pytest.raises(SystemExit):
        C.graph(1, "v0", "x=0:y=0", "multiply;evil", 0, 1, 64, 36, 24)                          # the graph builder refuses anything not on the list, whoever calls it


def test_mask_and_key_values_are_clamped_checked_and_removable(film):
    o = O._clean(film, {"kind": "image", "file": "x.png", "mask": "ellipse", "mask_size": 9, "mask_feather": -1, "key_color": "#00ff00", "key_tol": 5})
    assert o["mask"] == "ellipse" and o["mask_size"] == 1.0 and "mask_feather" not in o
    assert o["key_color"] == "#00ff00" and o["key_tol"] == 1.0 and o["key_soft"] == 0.15 and o["key_spill"] == 0.6
    with pytest.raises(SystemExit):
        O._clean(film, {"mask": "star"}, o)
    with pytest.raises(SystemExit):
        O._clean(film, {"mask_size": "big"}, o)
    cleared = O._clean(film, {"mask": "none", "key_color": ""}, o)
    assert not [k for k in cleared if k.startswith(("mask", "key_"))]
    assert C.signature(cleared) == []                                                          # a layer with neither keeps the cached picture it always had


def test_a_style_and_a_template_keep_the_compositing(film):
    assert {"blend", "mask", "mask_size", "mask_feather", "mask_invert", "key_color", "key_tol", "key_soft", "key_spill"} <= set(K.LOOK)


# ---------------------------------------------------------------- the key

def green_screen():
    im = Image.new("RGBA", (60, 40), (0, 255, 0, 255))
    for x in range(20, 40):
        for y in range(10, 30):
            im.putpixel((x, y), (200, 40, 40, 255))                                            # the subject: red
    im.putpixel((20, 20), (170, 120, 90))                                                      # an edge pixel with the screen's green leaking onto skin
    im.putpixel((2, 2), (0, 150, 0, 255))                                                      # the screen in shadow
    return im


def test_the_key_removes_the_screen_even_in_shadow_and_keeps_the_subject(film):
    o = {"key_color": "#00ff00", "key_tol": 0.35, "key_soft": 0.15, "key_spill": 0.6}
    out = C.apply_key(green_screen(), o, O._hex)
    assert px(out, 0, 0)[3] == 0 and px(out, 59, 39)[3] == 0
    assert px(out, 2, 2)[3] == 0                                                               # a darker green is still the green
    assert px(out, 30, 20)[3] == 255 and px(out, 30, 20)[:3] == (200, 40, 40)


def test_the_edge_is_soft_and_spill_is_taken_off_what_is_kept(film):
    hard = C.apply_key(green_screen(), {"key_color": "#00ff00", "key_tol": 0.2, "key_soft": 0.0, "key_spill": 0.0}, O._hex)
    soft = C.apply_key(green_screen(), {"key_color": "#00ff00", "key_tol": 0.2, "key_soft": 1.0, "key_spill": 0.0}, O._hex)
    alphas = {px(soft, x, y)[3] for x in range(60) for y in range(40)}
    assert len(alphas) > 3 and {px(hard, x, y)[3] for x in range(60) for y in range(40)} <= {0, 255} or len({px(hard, x, y)[3] for x in range(60) for y in range(40)}) < len(alphas)
    base = Image.new("RGBA", (4, 4), (150, 190, 120, 255))                                      # a pixel with too much green in it
    kept = {"key_color": "#00ff00", "key_tol": 0.0, "key_soft": 0.0}
    g0 = px(C.apply_key(base, {**kept, "key_spill": 0.0}, O._hex), 1, 1)[1]
    g1 = px(C.apply_key(base, {**kept, "key_spill": 1.0}, O._hex), 1, 1)[1]
    assert g0 == 190 and g1 < g0 and g1 >= (150 + 120) // 2 - 1


def test_a_key_is_used_on_a_picture_layer_and_only_when_set(film, tmp_path):
    src = str(tmp_path / "gs.png")
    green_screen().save(src)
    plain_layer = O.add(film, {"image": src, "width": 0.5, "shadow": False, "start": 0, "end": 2})[-1]
    keyed_layer = O._clean(film, {"key_color": "#00ff00"}, plain_layer)
    plain = O.render_png(film, plain_layer, 640, 360)[0]
    keyed = O.render_png(film, keyed_layer, 640, 360)[0]
    assert plain != keyed
    assert px(Image.open(plain), 2, 2)[3] == 255 and px(Image.open(keyed), 2, 2)[3] == 0


# ---------------------------------------------------------------- the mask

def test_a_mask_shows_the_layer_through_a_shape_and_can_be_turned_inside_out():
    im = Image.new("RGBA", (100, 60), (255, 255, 255, 255))
    ell = C.apply_mask(im, {"mask": "ellipse", "mask_size": 0.8})
    assert px(ell, 50, 30)[3] == 255 and px(ell, 1, 1)[3] == 0
    inv = C.apply_mask(im, {"mask": "ellipse", "mask_size": 0.8, "mask_invert": True})
    assert px(inv, 50, 30)[3] == 0 and px(inv, 1, 1)[3] == 255
    rect = C.apply_mask(im, {"mask": "rect", "mask_size": 0.5})
    assert px(rect, 50, 30)[3] == 255 and px(rect, 10, 30)[3] == 0 and px(rect, 40, 20)[3] == 255
    assert C.apply_mask(im, {}) is im


def test_a_soft_mask_fades_out_gradually_and_a_vignette_darkens_only_the_edges():
    im = Image.new("RGBA", (200, 120), (0, 0, 0, 255))
    hard = C.apply_mask(im, {"mask": "ellipse", "mask_size": 0.8, "mask_invert": True})
    soft = C.apply_mask(im, {"mask": "ellipse", "mask_size": 0.8, "mask_invert": True, "mask_feather": 0.8})
    ramp = [px(soft, x, 60)[3] for x in range(0, 100, 5)]
    assert ramp == sorted(ramp, reverse=True) and len(set(ramp)) > 5                            # from the dark edge in to the clear middle
    assert px(soft, 100, 60)[3] < 40 and px(soft, 2, 2)[3] > 200
    assert len({px(hard, x, 60)[3] for x in range(200)}) <= 2


def test_a_mask_changes_the_layers_picture_and_a_plain_layer_is_unchanged(film):
    base = {"kind": "fill", "color": "#000000", "start": 0, "end": 2}
    plain = O.render_png(film, O._clean(film, base), 320, 180)[0]
    masked = O.render_png(film, O._clean(film, {**base, "mask": "ellipse", "mask_invert": True, "mask_feather": 0.5}), 320, 180)[0]
    assert plain != masked and px(Image.open(masked), 160, 90)[3] < 30 and px(Image.open(plain), 160, 90)[3] == 255
    assert O.render_png(film, O._clean(film, base), 320, 180)[0] == plain


# ---------------------------------------------------------------- in the finished film

def frame_of(video, n, tmp_path, name):
    p = str(tmp_path / f"{name}.png")
    ff("-i", video, "-vf", f"select='eq(n,{n})'", "-frames:v", "1", p)
    return Image.open(p).convert("RGB")


def mean(im, box):
    px_ = list(im.crop(box).getdata())
    return tuple(sum(p[i] for p in px_) / len(px_) for i in range(3))


def test_multiply_and_screen_mix_with_the_picture_under_them_and_leave_the_rest_alone(film, tmp_path):
    plain = str(tmp_path / "plain.mp4")
    shutil.copy(E.build(film, "preview")["path"], plain)                                       # the film is named by the minute: keep this one before the next export replaces it
    colour = (224, 120, 40)
    for mode in ("multiply", "screen"):
        for o in O.load(film):
            O.remove(film, o["id"])
        O.add(film, {"kind": "fill", "color": "#%02x%02x%02x" % colour, "start": 4.0, "end": 8.0, "blend": mode, "anim": "fade", "fade": 0.2})
        made = str(tmp_path / f"{mode}.mp4")
        shutil.copy(E.build(film, "preview")["path"], made)
        base, mixed = frame_of(plain, 24 * 6, tmp_path, f"b{mode}"), frame_of(made, 24 * 6, tmp_path, f"m{mode}")       # 6 s: the layer is fully up
        box = (40, 30, 120, 70)
        b, m = mean(base, box), mean(mixed, box)
        want = [b[i] * colour[i] / 255 if mode == "multiply" else 255 - (255 - b[i]) * (255 - colour[i]) / 255 for i in range(3)]
        assert all(abs(m[i] - want[i]) < 9 for i in range(3)), (mode, b, m, want)           # the arithmetic of the mode, to within what an encoder changes
        assert sum(abs(m[i] - b[i]) for i in range(3)) > 20                                  # and it really did something
        early_a, early_b = frame_of(plain, 24 * 2, tmp_path, f"ea{mode}"), frame_of(made, 24 * 2, tmp_path, f"eb{mode}")
        assert max(abs(i - j) for p, q in zip(early_a.getdata(), early_b.getdata()) for i, j in zip(p, q)) < 25      # before the layer is up the film is the film


def test_a_blended_layer_with_its_own_shape_only_changes_the_picture_where_it_is(film, tmp_path):
    plain = str(tmp_path / "plain.mp4")
    shutil.copy(E.build(film, "preview")["path"], plain)
    O.add(film, {"kind": "shape", "shape": "circle", "x": 0.5, "y": 0.5, "width": 0.3, "color": "#ff0000", "filled": True, "start": 2.0, "end": 5.0, "blend": "multiply", "anim": "fade", "shadow": False})
    made = str(tmp_path / "made.mp4")
    shutil.copy(E.build(film, "preview")["path"], made)
    a, b = frame_of(plain, 24 * 4, tmp_path, "a"), frame_of(made, 24 * 4, tmp_path, "b")
    w, h = a.size
    centre, corner = (w // 2 - 8, h // 2 - 8, w // 2 + 8, h // 2 + 8), (2, 2, 30, 30)
    ca, cb, ka, kb = mean(a, centre), mean(b, centre), mean(a, corner), mean(b, corner)
    assert cb[1] < ca[1] - 10 and cb[2] < ca[2] - 10                                            # multiplied by red: green and blue go down in the circle
    assert all(abs(ka[i] - kb[i]) < 8 for i in range(3))                                        # and the corner is as it was


def test_normal_layers_and_blended_layers_can_be_mixed_in_one_film(film, tmp_path):
    O.add(film, {"kind": "text", "text": "Hello", "start": 1.0, "end": 9.0, "size": 0.1, "x": 0.5, "y": 0.2})
    O.add(film, {"kind": "fill", "color": "#3050a0", "start": 3.0, "end": 7.0, "blend": "softlight", "anim": "fade"})
    O.add(film, {"kind": "shape", "shape": "rounded", "x": 0.5, "y": 0.8, "width": 0.2, "color": "#ffffff", "filled": True, "start": 2.0, "end": 8.0, "blend": "screen"})
    out = E.build(film, "preview")
    assert not out.get("overlay_error") and out["overlays"] == 3 and os.path.getsize(out["path"]) > 1000
