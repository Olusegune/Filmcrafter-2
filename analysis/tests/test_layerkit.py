"""Layer styles (saved once, used in any project) and lyric layers (one layer per lyric line, timed to it)."""
import json
import subprocess

import pytest
from PIL import Image

from pulseframe_analysis import layerkit as K, overlays as O
from pulseframe_analysis.export import NO_WINDOW, ffmpeg

MISSING = "isn.t in the project"       # the engine's plain sentence, matched without caring about the apostrophe
NOT_SAVED = "isn.t saved"


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.setattr(K, "STYLES_PATH", str(tmp_path / "home" / "layer_styles.json"))
    d = tmp_path / "p"
    d.mkdir()
    json.dump({"title": "T"}, open(d / "project.json", "w"))
    lyrics = [{"text": "First line of the song", "start": 2.0, "end": 4.0}, {"text": "second line", "start": 4.5, "end": 6.0}, {"text": "  third   line  ", "start": 6.1, "end": 6.2},
              {"text": "", "start": 7.0, "end": 8.0}]
    json.dump({"duration": 20.0, "sections": [], "lyrics": lyrics}, open(d / "songmap.json", "w"))
    return str(d)


def test_a_style_is_saved_under_a_name_applied_to_other_layers_and_deleted(proj):
    O.add(proj, {"kind": "text", "text": "Title", "start": 0, "end": 4, "color": "#ffd166", "gradient": True, "color2": "#ff6b6b", "angle": 90, "stroke": "#000000", "stroke_w": 0.01,
                 "anim": "pop", "size": 0.12, "scale": 1.5, "rotation": -5, "shadow": False})
    O.add(proj, {"kind": "text", "text": "Other", "start": 5, "end": 9})
    O.add(proj, {"kind": "shape", "shape": "rect", "start": 5, "end": 9, "width": 0.2, "height": 0.1})
    ids = [o["id"] for o in O.load(proj)]
    assert K.save_style(proj, ids[0], "  Gold   pop ")["styles"][0]["name"] == "Gold pop"
    K.save_style(proj, ids[0], "gold POP")                                                           # the same name replaces it
    assert len(K.list_styles()["styles"]) == 1
    out = K.apply_style(proj, "Gold Pop", [ids[1], ids[2]])["layers"]
    text, shape = out[1], out[2]
    assert (text["color"], text["anim"], text["size"], text["scale"], text["rotation"], text["shadow"], text["gradient"]) == ("#ffd166", "pop", 0.12, 1.5, -5.0, False, True)
    assert shape["color"] == "#ffd166" and shape["anim"] == "pop" and shape["height"] == 0.1 and shape["width"] == 0.2          # looks carry over; a text size does not become a width
    assert text["text"] == "Other" and (text["start"], text["end"]) == (5.0, 9.0)                    # what it says and when are not part of a style
    assert K.delete_style("gold pop")["styles"] == []
    with pytest.raises(SystemExit, match=NOT_SAVED):
        K.apply_style(proj, "gold pop", ids[:1])


def test_a_style_refuses_blank_names_unknown_layers_and_too_many(proj, monkeypatch):
    O.add(proj, {"kind": "text", "text": "A", "start": 0, "end": 4})
    oid = O.load(proj)[0]["id"]
    with pytest.raises(SystemExit, match="Give the style a name"):
        K.save_style(proj, oid, "  ")
    with pytest.raises(SystemExit, match=MISSING):
        K.save_style(proj, "nope", "x")
    monkeypatch.setattr(K, "MAX_STYLES", 2)
    K.save_style(proj, oid, "a")
    K.save_style(proj, oid, "b")
    with pytest.raises(SystemExit, match="at most"):
        K.save_style(proj, oid, "c")


def test_a_font_this_project_does_not_have_is_left_out_not_an_error(proj):
    O.add(proj, {"kind": "text", "text": "A", "start": 0, "end": 4})
    oid = O.load(proj)[0]["id"]
    K.save_style(proj, oid, "x")
    styles = json.load(open(K.STYLES_PATH))
    styles["styles"][0]["look"]["font"] = "project:gone.ttf"
    json.dump(styles, open(K.STYLES_PATH, "w"))
    out = K.apply_style(proj, "x", [oid])
    assert out["font_missing"] is True and not out["layers"][0].get("font")


def test_one_layer_is_made_for_each_timed_lyric_line_and_they_do_not_overlap(proj):
    out = K.lyrics_layers(proj, {"anim": "pop", "position": "middle", "size": 0.09, "color": "#ffffff", "upper": True})
    layers = out["layers"]
    assert out["made"] == 3 and [o["text"] for o in layers] == ["FIRST LINE OF THE SONG", "SECOND LINE", "THIRD LINE"]          # the empty line is skipped; spaces are tidied
    assert all(o["group"] == K.GROUP and o["anim"] == "pop" and o["y"] == 0.5 and o["kind"] == "text" for o in layers)
    assert layers[0]["start"] == pytest.approx(1.95) and layers[0]["end"] <= layers[1]["start"] + 1e-6 and layers[1]["end"] <= layers[2]["start"] + 1e-6
    assert all(o["end"] - o["start"] >= 0.6 - 1e-6 for o in layers)                                    # a very short line still stays up long enough to read


def test_making_them_again_replaces_the_group_and_leaves_other_layers_alone_and_they_can_be_removed(proj):
    O.add(proj, {"kind": "text", "text": "Title", "start": 0, "end": 4})
    K.lyrics_layers(proj, {})
    again = K.lyrics_layers(proj, {"anim": "wipe"})
    assert again["made"] == 3 and len(O.load(proj)) == 4 and all(o["anim"] == "wipe" for o in O.load(proj) if o.get("group") == K.GROUP)
    gone = K.lyrics_remove(proj)
    assert gone["removed"] == 3 and [o["text"] for o in O.load(proj)] == ["Title"]


def test_lyric_layers_can_copy_a_layer_or_a_saved_style_and_refuse_bad_requests(proj):
    O.add(proj, {"kind": "text", "text": "Model", "start": 0, "end": 4, "color": "#ff0000", "stroke": "#00ff00", "stroke_w": 0.01, "anim": "bounce", "size": 0.11})
    oid = O.load(proj)[0]["id"]
    out = K.lyrics_layers(proj, {"from_layer": oid})["layers"]
    lyric = [o for o in out if o.get("group") == K.GROUP]
    assert all(o["color"] == "#ff0000" and o["stroke"] == "#00ff00" and o["anim"] == "bounce" and o["size"] == 0.11 for o in lyric)
    K.save_style(proj, oid, "model")
    assert K.lyrics_layers(proj, {"style": "model"})["made"] == 3
    for bad, why in (({"anim": "spin"}, "movements in the list"), ({"position": "left"}, "top, middle or bottom"), ({"style": "nope"}, NOT_SAVED), ({"from_layer": "nope"}, MISSING)):
        with pytest.raises(SystemExit, match=why):
            K.lyrics_layers(proj, bad)


def test_no_lyrics_and_too_many_layers_are_refused_plainly(proj, tmp_path, monkeypatch):
    d2 = tmp_path / "q"
    d2.mkdir()
    json.dump({"duration": 5, "lyrics": []}, open(d2 / "songmap.json", "w"))
    with pytest.raises(SystemExit, match="no timed lyric lines"):
        K.lyrics_layers(str(d2), {})
    monkeypatch.setattr(O, "MAX_OVERLAYS", 2)
    with pytest.raises(SystemExit, match="pass 2"):
        K.lyrics_layers(proj, {})
    assert O.load(proj) == []                                                                          # nothing half-made


def test_lyric_layers_appear_in_the_film_line_by_line(proj, tmp_path):
    K.lyrics_layers(proj, {"anim": "fade", "position": "middle", "size": 0.2, "upper": True})
    v = str(tmp_path / "film.mp4")
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0x202020:s=320x180:r=12:d=8", "-pix_fmt", "yuv420p", v], check=True, creationflags=NO_WINDOW)
    r = O.burn(proj, v, 320, 180, fps=12, duration=8.0)
    assert not r.get("error") and r["count"] == 3

    def bright(t):
        out = str(tmp_path / f"f{t}.png")
        subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", str(t), "-i", v, "-frames:v", "1", out], check=True, creationflags=NO_WINDOW)
        return Image.open(out).convert("L").point(lambda p: 255 if p > 200 else 0).getbbox()
    assert bright(0.5) is None and bright(3.0) is not None and bright(5.5) is not None and bright(7.6) is None      # nothing before the first line, text during lines, nothing after


def test_the_command_line_speaks_json(proj, capsys):
    assert K.main(["lyrics", proj, "--data", "{}"]) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["data"]["made"] == 3
    assert K.main(["save", proj, "--data", json.dumps({"id": "nope", "name": "x"})]) == 1
    assert "in the project" in json.loads(capsys.readouterr().out.splitlines()[-1])["message"]


def test_a_film_with_two_hundred_layers_is_drawn_without_hitting_the_command_line_limit(proj, tmp_path):
    """A real project with 79 lyric lines plus other layers failed to export on Windows (WinError 206: the filter graph was longer than a command line may be)."""
    for i in range(200):
        O.add(proj, {"kind": "text", "text": f"L{i}", "start": 0.5 + (i % 7) * 0.1, "end": 3.0, "size": 0.05, "x": 0.1 + (i % 9) * 0.1, "y": 0.1 + (i % 8) * 0.1, "fade": 0.05})
    v = str(tmp_path / "film.mp4")
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0x202020:s=320x180:r=12:d=4", "-pix_fmt", "yuv420p", v], check=True, creationflags=NO_WINDOW)
    r = O.burn(proj, v, 320, 180, fps=12, duration=4.0)
    assert not r.get("error") and r["count"] == 200
    assert not [f for f in __import__("os").listdir(tmp_path) if f.endswith(".graph.txt")]                  # the temporary graph file is cleaned up


MISSING_TPL = "isn.t saved"


def test_a_few_layers_are_kept_as_a_template_and_put_down_anywhere_with_their_timing_relative_to_each_other(proj, monkeypatch, tmp_path):
    monkeypatch.setattr(K, "TEMPLATES_PATH", str(tmp_path / "home" / "layer_templates.json"))
    O.add(proj, {"kind": "text", "text": "TITLE", "start": 10, "end": 14, "x": 0.5, "y": 0.4, "size": 0.12, "color": "#ffd166", "anim": "pop", "gradient": True, "color2": "#ff6b6b"})
    O.add(proj, {"kind": "text", "text": "subtitle", "start": 11, "end": 14, "x": 0.5, "y": 0.55, "size": 0.05, "anim": "fade"})
    O.add(proj, {"kind": "icon", "icon": "crown", "start": 10.5, "end": 14, "x": 0.5, "y": 0.2, "width": 0.1, "color": "#ffd166", "anim": "zoom_in"})
    ids = [o["id"] for o in O.load(proj)]
    assert K.template_save(proj, ids, "  Title   sequence ")["templates"] == [{"name": "Title sequence", "layers": 3, "seconds": 4.0, "saved": pytest.approx(K.list_templates()["templates"][0]["saved"])}]
    out = K.template_apply(proj, "title sequence", 14)
    assert out["made"] == 3
    made = [o for o in out["layers"] if o.get("group", "").startswith("tpl:")]
    assert [(o["start"], o["end"]) for o in made] == [(14.0, 18.0), (15.0, 18.0), (14.5, 18.0)]       # the same gaps between them, from the new moment
    assert made[0]["text"] == "TITLE" and made[0]["anim"] == "pop" and made[0]["gradient"] is True and made[2]["icon"] == "crown"
    assert len({o["group"] for o in made}) == 1
    again = K.template_apply(proj, "Title sequence", 15)
    assert len({o["group"] for o in again["layers"] if o.get("group", "").startswith("tpl:")}) == 2    # each use is its own group
    gone = K.template_remove_group(proj, made[0]["group"])
    assert gone["removed"] == 3 and len(gone["layers"]) == 6
    assert K.template_delete("title sequence")["templates"] == []
    with pytest.raises(SystemExit, match=MISSING_TPL):
        K.template_apply(proj, "title sequence", 0)


def test_templates_refuse_pictures_unplaced_layers_blank_names_and_bad_groups(proj, monkeypatch, tmp_path):
    monkeypatch.setattr(K, "TEMPLATES_PATH", str(tmp_path / "home" / "layer_templates.json"))
    pic = tmp_path / "a.png"
    Image.new("RGB", (8, 8)).save(pic)
    O.add(proj, {"image": str(pic), "start": 0, "end": 4})
    O.add(proj, {"kind": "text", "text": "x", "section": "chorus1"})
    O.add(proj, {"kind": "text", "text": "ok", "start": 1, "end": 3})
    pic_id, sec_id, ok_id = [o["id"] for o in O.load(proj)]
    with pytest.raises(SystemExit, match="picture belongs to one project"):
        K.template_save(proj, [pic_id], "x")
    with pytest.raises(SystemExit, match="start and an end"):
        K.template_save(proj, [sec_id], "x")
    with pytest.raises(SystemExit, match="Give the style a name"):
        K.template_save(proj, [ok_id], " ")
    with pytest.raises(SystemExit, match="Pick the layers"):
        K.template_save(proj, [], "x")
    with pytest.raises(SystemExit, match="not a template group"):
        K.template_remove_group(proj, "lyrics:kinetic")
    assert len(O.load(proj)) == 3


def test_a_template_with_a_font_this_project_lacks_still_applies(proj, monkeypatch, tmp_path):
    monkeypatch.setattr(K, "TEMPLATES_PATH", str(tmp_path / "home" / "layer_templates.json"))
    O.add(proj, {"kind": "text", "text": "x", "start": 1, "end": 3})
    oid = O.load(proj)[0]["id"]
    K.template_save(proj, [oid], "t")
    data = json.load(open(K.TEMPLATES_PATH))
    data["templates"][0]["layers"][0]["look"]["font"] = "project:gone.ttf"
    json.dump(data, open(K.TEMPLATES_PATH, "w"))
    out = K.template_apply(proj, "t", 5)
    assert out["made"] == 1 and not out["layers"][-1].get("font")
