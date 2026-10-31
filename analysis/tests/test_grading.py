"""Colour Studio: a grade for a shot, a scene or the film, and .cube LUTs. Free and local; it changes the film only when it is put together, never the takes.

Part of this is pure (numbers in, filter text out), part runs the bundled ffmpeg on small pictures to prove that a number in the grade really moves the exported picture."""
import json
import os
import re
import subprocess
import wave

import pytest
from PIL import Image

from filmcrafter_engine import export as E, grading as G, media

GREY = {"S01-01": "0x808080", "S01-02": "0x808080", "S02-01": "0x808080"}


def ff(*args):
    subprocess.run([E.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args], check=True, creationflags=E.NO_WINDOW)


@pytest.fixture
def film(tmp_path):
    d = tmp_path / "film"
    d.mkdir()
    with wave.open(str(d / "song.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\0\0" * int(22050 * 6))
    json.dump({"title": "T", "song": "song.wav", "aspect_ratio": "16:9"}, open(d / "project.json", "w"))
    json.dump({"duration": 6.0, "sections": [], "lyrics": []}, open(d / "songmap.json", "w"))
    sc = lambda n, ids: {"number": n, "heading": f"SCENE {n}", "start": 0, "end": 6, "shots": [{"id": i, "scene": n, "number": k, "start": s, "end": s + 2.0, "beats": ["x"], "performers": []} for k, (i, s) in enumerate(ids, 1)]}
    json.dump({"scenes": [sc(1, [("S01-01", 0.0), ("S01-02", 2.0)]), sc(2, [("S02-01", 4.0)])]}, open(d / "production.json", "w"))
    json.dump({"jobs": []}, open(d / "jobs.json", "w"))
    for sid, col in GREY.items():
        clip = tmp_path / f"{sid}.mp4"
        ff("-f", "lavfi", "-i", f"color=c={col}:s=320x180:r=24:d=3", "-pix_fmt", "yuv420p", str(clip))
        media.import_media(str(d), sid, str(clip))
    return str(d)


def pixel(video, t, tmp_path, name):
    out = str(tmp_path / f"{name}.png")
    ff("-ss", str(t), "-i", video, "-frames:v", "1", out)
    return Image.open(out).convert("RGB").getpixel((160, 90))


IDENTITY_3D = "LUT_3D_SIZE 2\n" + "\n".join(f"{r} {g} {b}" for b in (0, 1) for g in (0, 1) for r in (0, 1)) + "\n"
WARM_3D = "TITLE \"Warm\"\nLUT_3D_SIZE 2\n" + "\n".join(f"{min(1, r + 0.2)} {g} {max(0, b - 0.2)}" for b in (0, 1) for g in (0, 1) for r in (0, 1)) + "\n"


def cube_file(tmp_path, text, name="x.cube"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------- the numbers

def test_a_grade_keeps_only_known_numbers_inside_their_limits_and_drops_the_defaults():
    g = G.clean_grade({"exposure": 99, "contrast": "0.5", "saturation": 0, "bogus": 3, "hue": float("nan"), "lift_rgb": [0.1, "x", 5], "gain_rgb": [0, 0, 0], "lut": {"id": "../../etc/passwd!!!!", "intensity": 1}})
    assert g == {"exposure": 3.0, "contrast": 0.5, "lift_rgb": [0.1, 0.0, 1.0]}
    assert G.clean_grade("nonsense") == {} and G.clean_grade({"lut": {"id": "0123456789abcdef", "intensity": 9}})["lut"] == {"id": "0123456789abcdef", "intensity": 1.0}


def test_a_grade_with_nothing_set_adds_nothing_at_all():
    assert G.grade_chain({}) == "" and G.grade_chain(G.clean_grade({"contrast": 0})) == "" and G.grade_chain({"off": True, "exposure": 1.0}) == ""


def test_the_chain_is_only_numbers_made_here_and_goes_to_rgb_and_back_with_the_hd_matrix_written_out():
    chain = G.grade_chain(G.clean_grade({"exposure": 0.5, "saturation": -0.3, "hue": 10, "vibrance": 0.2, "temperature": 0.1}))
    assert chain.startswith(G.TO_RGB) and chain.endswith(G.TO_YUV)
    assert "bt709" in G.TO_RGB and "bt709" in G.TO_YUV
    body = chain[len(G.TO_RGB) + 1: -len(G.TO_YUV) - 1]
    assert re.fullmatch(r"lutrgb=r='[a-z0-9_.+\-*/(),% ]+':g='[a-z0-9_.+\-*/(),% ]+':b='[a-z0-9_.+\-*/(),% ]+',colorchannelmixer=(rr|rg|rb|gr|gg|gb|br|bg|bb|[=:\d.\-])+,vibrance=intensity=-?[\d.]+", body), body


def test_the_file_name_in_a_filter_is_escaped_for_a_windows_drive():
    assert G._fesc("C:\\Users\\me\\x.cube") == "'C\\:/Users/me/x.cube'"


@pytest.mark.parametrize("folder", ["plain", "Sarah's film", "a b", "a,b", "a;b", "a[b]", "a=b", "caf\u00e9"])
def test_a_lut_is_read_from_a_folder_whatever_the_name_holds(tmp_path, folder):
    d = tmp_path / folder
    d.mkdir()
    (d / "x.cube").write_text(WARM_3D, encoding="utf-8", newline="\n")
    src = str(tmp_path / "in.png")
    ff("-f", "lavfi", "-i", "color=c=0x808080:s=32x32", "-frames:v", "1", src)
    out = str(tmp_path / "o.png")
    ff("-i", src, "-vf", f"scale=out_color_matrix=bt709,format=gbrp16le,lut3d=file={G._fesc(str(d / 'x.cube'))},format=rgb24", "-frames:v", "1", out)
    p = Image.open(out).convert("RGB").getpixel((16, 16))
    assert p[0] > p[2] + 20                                                                               # the warm LUT was really applied


def test_a_grade_that_pushes_the_picture_out_of_range_is_said_plainly():
    assert G.swing(G.clean_grade({"exposure": 2.0}))["clipped_whites"] is True
    assert G.swing(G.clean_grade({"exposure": -2.0, "contrast": 0.8}))["crushed_blacks"] is True
    assert G.swing(G.clean_grade({"saturation": 0.2})) == {"clipped_whites": False, "crushed_blacks": False}


# ---------------------------------------------------------------- the real pictures

def run_chain(tmp_path, chain, src_col="0x808080", name="o"):
    src = str(tmp_path / f"{name}_in.png")
    ff("-f", "lavfi", "-i", f"color=c={src_col}:s=64x64", "-frames:v", "1", src)
    out = str(tmp_path / f"{name}.png")
    ff("-i", src, "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p," + chain + ",scale=in_range=tv:in_color_matrix=bt709:out_range=pc:out_color_matrix=bt709,format=rgb24", "-frames:v", "1", out)
    return Image.open(out).convert("RGB").getpixel((32, 32))


@pytest.mark.parametrize("grade,test", [({"exposure": 1.0}, lambda base, p: sum(p) > sum(base) + 60), ({"exposure": -1.0}, lambda base, p: sum(p) < sum(base) - 60),
                                         ({"temperature": 0.6}, lambda base, p: p[0] > p[2] + 20), ({"temperature": -0.6}, lambda base, p: p[2] > p[0] + 20),
                                         ({"tint": 0.8}, lambda base, p: p[1] < p[0] - 5), ({"lift_rgb": [0, 0, 0.8]}, lambda base, p: p[2] > p[0] + 5),
                                         ({"gamma": 0.8}, lambda base, p: sum(p) > sum(base) + 30), ({"gain": 0.8}, lambda base, p: sum(p) > sum(base) + 30)])
def test_each_number_moves_the_picture_the_way_its_name_says(tmp_path, grade, test):
    base = run_chain(tmp_path, "null", name="base")
    assert test(base, run_chain(tmp_path, G.grade_chain(G.clean_grade(grade)), name="g"))


def test_saturation_all_the_way_down_is_grey_and_a_hue_turn_moves_red_towards_green(tmp_path):
    p = run_chain(tmp_path, G.grade_chain(G.clean_grade({"saturation": -1.0})), "0xc03030", "grey")
    assert max(p) - min(p) <= 3
    red = run_chain(tmp_path, "null", "0xc03030", "red")
    turned = run_chain(tmp_path, G.grade_chain(G.clean_grade({"hue": 120})), "0xc03030", "turned")
    assert red[0] > red[1] + 60 and turned[1] > turned[0]


def test_a_natural_picture_goes_to_rgb_and_back_without_changing_by_more_than_a_few_levels(tmp_path):
    src = str(tmp_path / "in.png")
    ff("-f", "lavfi", "-i", "gradients=size=160x90:rate=1:c0=0x3a5f8a:c1=0xd9b27c:x0=0:y0=0:x1=160:y1=90", "-frames:v", "1", src)
    pre = "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,"
    tail = ",scale=in_range=tv:in_color_matrix=bt709:out_range=pc:out_color_matrix=bt709,format=rgb24"
    a, b = str(tmp_path / "a.png"), str(tmp_path / "b.png")
    ff("-i", src, "-vf", pre.rstrip(",") + tail, "-frames:v", "1", a)
    ff("-i", src, "-vf", pre + G.TO_RGB + "," + G.TO_YUV + tail, "-frames:v", "1", b)
    pa, pb = Image.open(a).convert("RGB").getdata(), Image.open(b).convert("RGB").getdata()
    diffs = [max(abs(x - y) for x, y in zip(p, q)) for p, q in zip(pa, pb)]
    assert max(diffs) <= 4 and sum(diffs) / len(diffs) < 0.6


# ---------------------------------------------------------------- LUTs

def test_a_valid_cube_is_read_and_each_kind_of_bad_file_is_refused_with_a_reason():
    ok = G.parse_cube(WARM_3D)
    assert ok["dims"] == 3 and ok["size"] == 2 and len(ok["rows"]) == 8 and ok["title"] == "Warm"
    bad = {"no size": "0 0 0\n", "wrong count": "LUT_3D_SIZE 2\n0 0 0\n", "domain": "DOMAIN_MAX 2 2 2\nLUT_3D_SIZE 2\n" + "0 0 0\n" * 8, "nan": "LUT_3D_SIZE 2\n" + "nan 0 0\n" + "0 0 0\n" * 7,
           "range": "LUT_3D_SIZE 2\n" + "9 0 0\n" + "0 0 0\n" * 7, "huge": "LUT_3D_SIZE 500\n", "word": "LUT_3D_SIZE 2\nRUN calc.exe\n", "two sizes": "LUT_3D_SIZE 2\nLUT_1D_SIZE 4\n", "input range": "LUT_3D_INPUT_RANGE 0 2\n"}
    for why, text in bad.items():
        with pytest.raises(SystemExit):
            G.parse_cube(text)


def test_a_lut_is_copied_in_by_the_hash_of_its_content_and_importing_it_again_adds_nothing(film, tmp_path):
    s = G.lut_import(film, cube_file(tmp_path, WARM_3D), "Warm look")
    assert len(s["luts"]) == 1 and s["luts"][0]["name"] == "Warm look" and s["luts"][0]["kind"] == "creative"
    again = G.lut_import(film, cube_file(tmp_path, WARM_3D, "copy.cube"), "Warm look")
    assert len(again["luts"]) == 1
    assert os.path.isfile(os.path.join(G.edit_dir(film), "luts", s["luts"][0]["id"] + ".cube"))


def test_a_lut_file_that_is_not_a_cube_or_is_too_large_or_has_an_unknown_space_is_refused(film, tmp_path):
    (tmp_path / "x.txt").write_text(WARM_3D)
    for args in ((str(tmp_path / "x.txt"),), (str(tmp_path / "missing.cube"),)):
        with pytest.raises(SystemExit, match="Choose a .cube"):
            G.lut_import(film, *args)
    with pytest.raises(SystemExit, match="colour space"):
        G.lut_import(film, cube_file(tmp_path, WARM_3D), "x", "creative", "rec709", "ntsc")
    with pytest.raises(SystemExit, match="creative or technical"):
        G.lut_import(film, cube_file(tmp_path, WARM_3D), "x", "magic")


def test_a_lut_for_log_or_hdr_footage_is_kept_but_never_applied_to_rec709_pictures(film, tmp_path):
    lid = G.lut_import(film, cube_file(tmp_path, WARM_3D), "Log to 709", "technical", "log", "rec709")["luts"][0]["id"]
    with pytest.raises(SystemExit, match="expects log footage"):
        G.set_grade(film, "film", None, {"lut": {"id": lid, "intensity": 1}})
    lid2 = G.lut_import(film, cube_file(tmp_path, IDENTITY_3D, "b.cube"), "709 to P3", "technical", "rec709", "dci_p3")["luts"][0]["id"]
    with pytest.raises(SystemExit, match="makes dci_p3"):
        G.set_grade(film, "film", None, {"lut": {"id": lid2, "intensity": 1}})


def test_lut_intensity_blends_the_lut_with_the_identity_and_zero_is_the_identity(film, tmp_path):
    lid = G.lut_import(film, cube_file(tmp_path, WARM_3D))["luts"][0]["id"]
    half, dims = G._lut_file(film, lid, 0.5)
    rows = G.parse_cube(open(half).read())["rows"]
    assert dims == 3 and abs(rows[0][0] - 0.1) < 1e-5 and abs(rows[0][2] - 0.0) < 1e-5 and abs(rows[7][2] - 0.9) < 1e-5            # red lifted by 0.2 at the start, blue lowered by 0.2 at the end, halved
    zero, _ = G._lut_file(film, lid, 0.0)
    assert G.parse_cube(open(zero).read())["rows"] == G.parse_cube(IDENTITY_3D)["rows"]
    full, _ = G._lut_file(film, lid, 1.0)
    assert full.endswith(lid + ".cube")


def test_a_lut_in_use_cannot_be_removed_and_a_free_one_can(film, tmp_path):
    lid = G.lut_import(film, cube_file(tmp_path, WARM_3D))["luts"][0]["id"]
    G.set_grade(film, "scene", 1, {"lut": {"id": lid, "intensity": 0.8}})
    with pytest.raises(SystemExit, match="used by a grade"):
        G.lut_remove(film, lid)
    G.clear_grade(film, "scene", 1)
    assert G.lut_remove(film, lid)["luts"] == [] and not os.path.exists(os.path.join(G.edit_dir(film), "luts", lid + ".cube"))


def test_favourites_float_to_the_top_of_the_library(film, tmp_path):
    a = G.lut_import(film, cube_file(tmp_path, WARM_3D), "Zed")["luts"][0]["id"]
    G.lut_import(film, cube_file(tmp_path, IDENTITY_3D, "b.cube"), "Alpha")
    assert [x["name"] for x in G.state(film)["luts"]] == ["Alpha", "Zed"]
    assert [x["name"] for x in G.lut_favorite(film, a, True)["luts"]] == ["Zed", "Alpha"]


# ---------------------------------------------------------------- scopes, presets, undo

def test_a_scope_has_one_grade_and_setting_it_again_replaces_it_instead_of_stacking(film):
    G.set_grade(film, "shot", "S01-01", {"exposure": 1.0})
    s = G.set_grade(film, "shot", "S01-01", {"contrast": 0.3})
    assert s["grades"]["shots"]["S01-01"] == {"contrast": 0.3}
    assert G.clear_grade(film, "shot", "S01-01")["grades"]["shots"] == {}


def test_the_film_then_the_scene_then_the_shot_are_put_on_in_that_order(film):
    G.set_grade(film, "film", None, {"exposure": 0.2})
    G.set_grade(film, "scene", 1, {"contrast": 0.2})
    G.set_grade(film, "shot", "S01-01", {"saturation": -0.2})
    assert [s for s, _ in G.effective(film, "S01-01", 1)] == ["film", "scene", "shot"]
    assert [s for s, _ in G.effective(film, "S01-02", 1)] == ["film", "scene"]
    assert [s for s, _ in G.effective(film, "S02-01", 2)] == ["film"]
    assert G.filter_for(film, "S01-01", 1).count("lutrgb") == 2


def test_a_scope_that_is_not_a_scope_or_has_no_key_is_refused(film):
    for args in (("planet", "x"), ("scene", ""), ("shot", "../x")):
        with pytest.raises(SystemExit):
            G.set_grade(film, args[0], args[1], {"exposure": 1})


def test_a_saved_look_can_be_applied_to_another_scope_and_deleted(film):
    G.set_grade(film, "scene", 1, {"exposure": 0.4, "tint": 0.1})
    G.preset_save(film, "Soft evening", "scene", 1)
    s = G.preset_apply(film, "Soft evening", "scene", 2)
    assert s["grades"]["scenes"]["2"] == {"exposure": 0.4, "tint": 0.1} and [p["name"] for p in s["presets"]] == ["Soft evening"]
    assert G.preset_delete(film, "Soft evening")["presets"] == []
    with pytest.raises(SystemExit, match="nothing set"):
        G.preset_save(film, "Empty", "shot", "S01-02")


def test_undo_puts_back_the_last_change_and_says_when_there_is_nothing_to_undo(film):
    with pytest.raises(SystemExit, match="nothing to undo"):
        G.undo(film)
    G.set_grade(film, "film", None, {"exposure": 0.5})
    G.set_grade(film, "film", None, {"exposure": 1.5})
    assert G.undo(film)["grades"]["film"] == {"exposure": 0.5}
    assert G.undo(film)["grades"]["film"] == {}


def test_nothing_is_written_until_something_is_changed_and_a_newer_files_extra_keys_survive(film):
    assert not os.path.exists(G._path(film)) and G.state(film)["grades"]["film"] == {}
    assert not os.path.exists(G._path(film))
    os.makedirs(G.edit_dir(film))
    json.dump({"schema": 9, "future": {"a": 1}}, open(G._path(film), "w"))
    G.set_grade(film, "film", None, {"exposure": 0.1})
    assert json.load(open(G._path(film)))["future"] == {"a": 1}


def test_it_lives_in_the_film_not_in_the_render_project(tmp_path):
    f = tmp_path / "MyFilm"
    (f / "render").mkdir(parents=True)
    json.dump({"title": "x"}, open(f / "film.json", "w"))
    assert G.edit_dir(str(f / "render")) == str(f / "edit")


# ---------------------------------------------------------------- the film

def test_the_export_applies_the_grade_by_scope_and_only_to_the_shots_it_is_for(film, tmp_path):
    plain = E.build(film, "preview")
    base = pixel(plain["path"], 1.0, tmp_path, "plain")
    G.set_grade(film, "scene", 1, {"exposure": 1.0})
    graded = E.build(film, "preview")
    s1, s2 = pixel(graded["path"], 1.0, tmp_path, "s1"), pixel(graded["path"], 5.0, tmp_path, "s2")                 # shot S01-01 is in scene 1, S02-01 in scene 2
    assert sum(s1) > sum(base) + 60
    assert s2 == pixel(plain["path"], 5.0, tmp_path, "s2plain")                                                     # scene 2 is untouched
    G.set_grade(film, "scene", 1, {})
    assert pixel(E.build(film, "preview")["path"], 1.0, tmp_path, "back") == base                                  # taking the grade off gives the picture back
    assert media.__name__                                                                                            # the takes themselves were never changed


def test_a_lut_changes_the_exported_picture_and_a_missing_lut_stops_with_a_plain_message(film, tmp_path):
    base = pixel(E.build(film, "preview")["path"], 1.0, tmp_path, "plain")
    lid = G.lut_import(film, cube_file(tmp_path, WARM_3D))["luts"][0]["id"]
    G.set_grade(film, "film", None, {"lut": {"id": lid, "intensity": 1.0}})
    warm = pixel(E.build(film, "preview")["path"], 1.0, tmp_path, "warm")
    assert warm[0] > base[0] + 20 and warm[2] < base[2] - 20
    G.set_grade(film, "film", None, {"lut": {"id": lid, "intensity": 0.5}})
    half = pixel(E.build(film, "preview")["path"], 1.0, tmp_path, "half")
    assert base[0] < half[0] < warm[0]
    os.remove(os.path.join(G.edit_dir(film), "luts", lid + ".cube"))
    with pytest.raises(SystemExit, match="missing"):
        E.build(film, "preview")


def test_the_preview_frame_comes_through_the_same_filter_text_as_the_export(film, tmp_path):
    G.set_grade(film, "shot", "S01-01", {"exposure": 1.0})
    res = G.preview(film, "S01-01")
    b, a = (Image.open(os.path.join(film, res[k])).convert("RGB").getpixel((100, 60)) for k in ("before", "after"))
    assert sum(a) > sum(b) + 60
    exported = pixel(E.build(film, "preview")["path"], 1.0, tmp_path, "exp")
    assert max(abs(x - y) for x, y in zip(a, exported)) <= 6                                                        # the preview agrees with the exported film
    unsaved = G.preview(film, "S01-02", {"exposure": -1.0})                                                         # a grade being edited, not saved
    assert sum(Image.open(os.path.join(film, unsaved["after"])).convert("RGB").getpixel((100, 60))) < sum(Image.open(os.path.join(film, unsaved["before"])).convert("RGB").getpixel((100, 60))) - 60
    assert "S01-02" not in G.state(film)["grades"]["shots"]


def test_the_door_speaks_json_and_refuses_an_unknown_action(film, capsys):
    assert G.main(["state", film]) == 0 and json.loads(capsys.readouterr().out.splitlines()[-1])["data"]["revision"] == 0
    assert G.main(["set_grade", film, "--data", json.dumps({"scope": "film", "grade": {"exposure": 0.2}})]) == 0
    assert G.main(["set_grade", film, "--data", json.dumps({"scope": "planet"})]) == 1 and "film, a scene or a shot" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="Unknown"):
        G.run(film, "explode", {})
    assert set(G.ACTIONS) == {"state", "set_grade", "clear_grade", "lut_import", "lut_remove", "lut_favorite", "preset_save", "preset_apply", "preset_delete", "undo", "preview"}
