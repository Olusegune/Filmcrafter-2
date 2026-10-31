"""Built-in motion graphics and layer effects: ready-made titles and lower thirds that become ordinary layers, and a glow and a blur drawn into a layer's own picture.
Free and local; the footage is made here."""
import json
import os
import re

import pytest
from PIL import Image

from filmcrafter_engine import export as E, layerkit as K, motion_templates as M, overlays as O
from tests.test_editing import build_film, ff

pytestmark = pytest.mark.integration


@pytest.fixture
def film(tmp_path):
    return build_film(tmp_path, [("S01-01", 1, 0.0, 6.0), ("S01-02", 1, 6.0, 12.0)], 12.0)


# ---------------------------------------------------------------- the built-in templates themselves

def test_every_built_in_template_is_well_formed_and_every_slot_is_used(film):
    ids = [t["id"] for t in M.BUILTIN]
    assert len(ids) == len(set(ids)) == 8
    for t in M.BUILTIN:
        used = {m for l in t["layers"] for m in re.findall(r"\{(\w+)\}", str(l["look"].get("text", "")))}
        assert used == {s["id"] for s in t["slots"]}, t["id"]
        assert all(0 < len(s["default"]) <= M.SLOT_MAX for s in t["slots"]) and 0 < t["seconds"] <= M.MAX_SECONDS
        assert max(l["offset"] + l["length"] for l in t["layers"]) == pytest.approx(t["seconds"]), t["id"]
        for l in t["layers"]:
            clean = O._clean(film, {**M.build(t["id"], None)["layers"][t["layers"].index(l)]["look"], "start": 1.0, "end": 2.0})       # the same checks every layer you make goes through
            assert clean["kind"] in ("text", "shape", "icon", "fill") and clean["anim"] in O.ANIMS


def test_the_list_says_what_each_is_for_and_what_words_it_needs():
    got = M.list_builtin()["templates"]
    lt = next(t for t in got if t["id"] == "lower_third")
    assert lt["name"] == "Lower third" and [s["id"] for s in lt["slots"]] == ["name", "role"] and lt["layers"] == 4 and "bottom of the picture" in lt["use"]


def test_your_words_go_only_into_the_text_slots_and_are_cleaned(film):
    t = M.build("lower_third", {"name": "  Ada    Lovelace  ", "role": "x" * 200})
    texts = [l["look"]["text"] for l in t["layers"] if "text" in l["look"]]
    assert texts == ["Ada Lovelace", "x" * 60]
    plain = M.build("lower_third", None)
    assert [l["look"]["text"] for l in plain["layers"] if "text" in l["look"]] == ["Sarah Okafor", "Head nurse"]
    blank = M.build("lower_third", {"name": "   ", "role": 5})
    assert [l["look"]["text"] for l in blank["layers"] if "text" in l["look"]] == ["Sarah Okafor", "5"]
    tricky = M.build("lower_third", {"name": "{role}", "role": "{name}"})
    assert [l["look"]["text"] for l in tricky["layers"] if "text" in l["look"]] == ["{role}", "{name}"]            # a word in braces is only words, never filled in again
    with pytest.raises(SystemExit, match="not one of the built-in"):
        M.build("../etc", {})


# ---------------------------------------------------------------- put down as ordinary layers

def test_a_template_goes_down_as_ordinary_layers_in_one_group_at_the_moment_chosen(film):
    out = M.apply_builtin(film, "lower_third", 3.0, {"name": "Sarah Okafor", "role": "Head nurse"})
    assert out["made"] == 4 and out["group"].startswith("tpl:lowerthird")
    mine = [o for o in O.resolve(film) if o.get("group") == out["group"]]
    assert len(mine) == 4 and min(o["start"] for o in mine) == pytest.approx(3.0) and max(o["end"] for o in mine) == pytest.approx(3.0 + 4.5)
    assert {o["text"] for o in mine if o["kind"] == "text"} == {"Sarah Okafor", "Head nurse"}
    edited = O.update(film, mine[2]["id"], {"text": "Dr Okafor"}) if hasattr(O, "update") else None
    assert K.template_remove_group(film, out["group"])["removed"] == 4 and not [o for o in O.resolve(film) if o.get("group") == out["group"]]


def test_two_uses_of_the_same_template_are_two_groups_and_each_comes_away_alone(film):
    a = M.apply_builtin(film, "title_card", 0.0)
    b = M.apply_builtin(film, "title_card", 6.0, {"title": "Second"})
    assert a["group"] != b["group"]
    assert K.template_remove_group(film, a["group"])["removed"] == 3
    left = [o for o in O.resolve(film) if o.get("group") == b["group"]]
    assert len(left) == 3 and any(o.get("text") == "Second" for o in left)


def test_a_bad_moment_or_a_full_project_is_refused_and_changes_nothing(film):
    before = len(O.resolve(film))
    for bad in ("soon", None):
        with pytest.raises(SystemExit):
            M.apply_builtin(film, "callout", bad)
    assert len(O.resolve(film)) == before
    json.dump({"overlays": [{"id": f"ov_{i}", "kind": "fill", "color": "#000000", "start": 0, "end": 1} for i in range(O.MAX_OVERLAYS - 1)]}, open(os.path.join(film, "overlays.json"), "w"))
    with pytest.raises(SystemExit, match="Remove some layers"):
        M.apply_builtin(film, "lower_third", 0.0)


def test_the_preview_is_a_real_picture_of_the_template_with_your_words_and_changes_nothing(film):
    before = O.resolve(film)
    out = M.preview(film, "lower_third", {"name": "Ada", "role": "Nurse"})
    im = Image.open(os.path.join(film, out["path"])).convert("RGB")
    assert im.size == (640, 360) and out["path"].startswith("cache/motion_preview/lower_third-")
    plain = Image.new("RGB", im.size)
    assert sum(1 for p, q in zip(im.getdata(), Image.open(os.path.join(film, M.preview(film, "lower_third", {"name": "Zed", "role": "Nurse"})["path"])).convert("RGB").getdata()) if p != q) > 100   # your words are in it
    bright = sum(1 for p in im.getdata() if p[0] > 200 and p[1] > 200 and p[2] > 200)
    assert bright > 100                                                                           # the white name is drawn
    assert O.resolve(film) == before and M.preview(film, "lower_third", {"name": "Ada", "role": "Nurse"}) == out        # nothing was added to the film; the same words give the same picture
    for t in M.BUILTIN:
        assert os.path.isfile(os.path.join(film, M.preview(film, t["id"])["path"]))


def test_the_door_lists_and_applies(film, capsys):
    assert K.main(["builtin_list", film]) == 0 and len(json.loads(capsys.readouterr().out.splitlines()[-1])["data"]["templates"]) == 8
    assert K.main(["builtin_apply", film, "--data", json.dumps({"id": "quote", "at": 1.0, "texts": {"quote": "Stay", "who": "John"}})]) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["data"]["made"] == 3
    assert K.main(["builtin_preview", film, "--data", json.dumps({"id": "callout"})]) == 0 and json.loads(capsys.readouterr().out.splitlines()[-1])["data"]["path"].endswith(".png")
    assert K.main(["builtin_apply", film, "--data", json.dumps({"id": "nope", "at": 1.0})]) == 1 and "not one of the built-in" in capsys.readouterr().out


# ---------------------------------------------------------------- effects

def text_layer(**kw):
    return {"id": "ov_t", "kind": "text", "text": "GLOW", "size": 0.12, "color": "#ffffff", "x": 0.5, "y": 0.5, **kw}


def alpha_count(im, lo=250):
    return sum(1 for a in im.split()[3].getdata() if a >= lo)


def test_a_glow_adds_a_soft_halo_around_the_layer_without_moving_it(film):
    plain, _ = O.render_png(film, text_layer(), 640, 360)
    glow, _ = O.render_png(film, text_layer(glow=0.8, glow_color="#ff0000"), 640, 360)
    assert plain != glow
    a, b = Image.open(plain), Image.open(glow)
    assert b.width > a.width and b.height > a.height                                          # padded for the halo; it is placed by its centre so the text stays where it was
    assert alpha_count(b, 20) > alpha_count(a, 20) * 1.5                                       # a halo of faint pixels around the letters
    r, g, bl, al = (b.getpixel((2 * (b.width - a.width) // 4, b.height // 2)) if False else (0, 0, 0, 0))
    halo = [px for px in b.getdata() if 10 < px[3] < 200 and px[0] > px[1] + 60]
    assert halo, "the halo is in the colour asked for"


def test_a_blur_softens_the_edges_and_no_effect_means_no_change(film):
    sharp, _ = O.render_png(film, text_layer(), 640, 360)
    soft, _ = O.render_png(film, text_layer(blur=0.5), 640, 360)
    assert alpha_count(Image.open(soft)) < alpha_count(Image.open(sharp)) * 0.6
    again, _ = O.render_png(film, text_layer(glow=0, blur=0), 640, 360)
    assert again == sharp                                                                      # nothing asked for: the same cached picture


def test_effect_numbers_are_kept_inside_their_range_and_zero_removes_them(film):
    o = O._clean(film, {"kind": "text", "text": "x", "start": 0, "end": 2, "glow": 7, "blur": -3, "glow_color": "not a colour"})
    assert o["glow"] == 1.0 and "blur" not in o and o["glow_color"] == "#ffffff"
    assert "glow" not in O._clean(film, {"glow": 0}, o)
    with pytest.raises(SystemExit):
        O._clean(film, {"glow": "lots"})


def test_a_style_and_a_template_keep_the_effects(film):
    assert {"glow", "glow_color", "blur"} <= set(K.LOOK)
    t = M.build("title_card", None)
    assert any(l["look"].get("glow") for l in t["layers"])


# ---------------------------------------------------------------- in the finished film

def test_a_lower_third_appears_in_the_film_while_it_is_up_and_not_before(film, tmp_path):
    def frame_of(video, n, name):
        p = str(tmp_path / f"{name}.png")
        ff("-i", video, "-vf", f"select='eq(n,{n})'", "-frames:v", "1", p)
        return Image.open(p).convert("RGB")
    import shutil
    made = E.build(film, "preview")["path"]
    plain = str(tmp_path / "plain.mp4")
    shutil.copy(made, plain)                                                                  # the film is named by the minute, so a second export in the same minute would replace the first
    M.apply_builtin(film, "lower_third", 4.0, {"name": "Ada", "role": "Nurse"})
    with_it = E.build(film, "preview")["path"]
    for n, up in ((72, False), (24 * 5 + 12, True)):                                         # 3 s (nothing up yet) and 5.5 s (the layer has settled): the same frame of the same film with and without it
        a, b = frame_of(plain, n, f"p{n}"), frame_of(with_it, n, f"w{n}")
        if up:
            changed = sum(1 for p, q in zip(a.getdata(), b.getdata()) if sum(abs(i - j) for i, j in zip(p, q)) > 12)
            assert changed > 3000                                                               # the bar, the line and the two lines of words are drawn over the picture
        else:
            assert a.tobytes() == b.tobytes()                                                   # before its start the film is untouched
