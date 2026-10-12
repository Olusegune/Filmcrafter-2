"""On-screen text: when it shows, what it looks like, and that it really lands in the exported film. Real ffmpeg, no network."""
import json
import os
import subprocess

import numpy as np
import pytest
import soundfile as sf
from PIL import Image

from filmcrafter_engine import export as E, overlays as O, svg_text

TITLE_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="180" viewBox="0 0 1600 180"><text x="800" y="70" '
             'text-anchor="middle" font-weight="bold" font-size="44" fill="#d8b35b">I AM YOUR MOTHER!</text></svg>')
CHART_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="200" viewBox="0 0 1600 200">'
             '<text x="800" y="70" text-anchor="middle" font-size="44" fill="#d8b35b">QUEEN BEE</text>'
             '<text x="800" y="135" text-anchor="middle" font-size="44" fill="#d8b35b">SOLOMON</text></svg>')
SECTIONS = [{"label": "INTRO", "start": 0, "end": 10}, {"label": "VERSE", "start": 10, "end": 40}, {"label": "PRE-CHORUS", "start": 40, "end": 50},
            {"label": "CHORUS", "start": 50, "end": 80}, {"label": "VERSE", "start": 80, "end": 110}, {"label": "PRE-CHORUS", "start": 110, "end": 120},
            {"label": "CHORUS", "start": 120, "end": 150}, {"label": "BRIDGE", "start": 150, "end": 170}, {"label": "CHORUS", "start": 170, "end": 200}]


def _project(tmp_path, sections=SECTIONS, duration=200.0):
    d = tmp_path / "p"
    d.mkdir()
    (d / "project.json").write_text(json.dumps({"title": "T"}))
    (d / "songmap.json").write_text(json.dumps({"duration": duration, "sections": sections}))
    return str(d)


# ---------------------------------------------------------------- when

def test_a_token_names_a_section_by_kind_and_number():
    sm = {"sections": SECTIONS}
    assert O.section_span(sm, "chorus1") == (50, 80) and O.section_span(sm, "chorus2") == (120, 150)
    assert O.section_span(sm, "verse2") == (80, 110) and O.section_span(sm, "pre1") == (40, 50) and O.section_span(sm, "pre-chorus2") == (110, 120)
    assert O.section_span(sm, "bridge") == (150, 170) and O.section_span(sm, "final") == (170, 200)     # the last chorus
    assert O.section_span(sm, "chorus9") is None and O.section_span(sm, "nonsense") is None and O.section_span({}, "chorus1") is None
    assert O.section_span(sm, "Chorus 1") == (50, 80)


def test_overlays_in_one_section_are_staggered_and_stay_inside_it(tmp_path):
    d = _project(tmp_path)
    O._save(d, [{"id": f"o{i}", "kind": "text", "text": t, "section": "verse2", "enabled": True} for i, t in enumerate(["Emmanuel", "Tunde", "Zara"])]
              + [{"id": "solo", "kind": "text", "text": "Title", "section": "chorus1", "enabled": True}])
    r = {o["id"]: o for o in O.resolve(d)}
    trio = [r["o0"], r["o1"], r["o2"]]
    assert all(o["placed"] and 80 <= o["start"] < o["end"] <= 110 for o in trio)
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(trio, trio[1:]))                      # one after another, never piled up
    assert all(o["end"] - o["start"] <= O.SHOW_FOR + 1e-6 for o in trio)
    assert 50 <= r["solo"]["start"] < r["solo"]["end"] <= 80


def test_explicit_times_win_and_unplaceable_overlays_say_why(tmp_path):
    d = _project(tmp_path)
    O._save(d, [{"id": "a", "kind": "text", "text": "x", "section": "chorus1", "start": 12, "end": 15},
                {"id": "b", "kind": "text", "text": "x", "start": 20},
                {"id": "c", "kind": "text", "text": "x", "section": "chorus7"},
                {"id": "d", "kind": "text", "text": "x"},
                {"id": "e", "kind": "text", "text": "x", "start": 500, "end": 505}])
    r = {o["id"]: o for o in O.resolve(d)}
    assert (r["a"]["start"], r["a"]["end"]) == (12, 15) and (r["b"]["start"], r["b"]["end"]) == (20, 24)
    assert not r["c"]["placed"] and "chorus7" in r["c"]["reason"] and not r["d"]["placed"] and "no time" in r["d"]["reason"]
    assert not r["e"]["placed"] and "after the song ends" in r["e"]["reason"]
    no_song = tmp_path / "q"
    no_song.mkdir()
    O._save(str(no_song), [{"id": "z", "kind": "text", "text": "x", "section": "chorus1"}])
    assert "hasn't been analysed" in O.resolve(str(no_song))[0]["reason"]


# ---------------------------------------------------------------- editing is validated

def test_what_the_screen_sends_is_clamped_and_checked(tmp_path):
    d = _project(tmp_path)
    r = O.add(d, {"kind": "text", "text": "  Hello  ", "x": 5, "y": -2, "size": 9, "fade": 99, "color": "not a colour", "start": 1, "end": 3})
    o = r[0]
    assert o["text"] == "Hello" and (o["x"], o["y"], o["size"], o["fade"]) == (1.0, 0.0, 0.3, 2.0) and o["color"] == "#ffffff"
    with pytest.raises(SystemExit, match="Write the text"):
        O.add(d, {"kind": "text", "text": "   "})
    with pytest.raises(SystemExit, match="end must be after"):
        O.add(d, {"kind": "text", "text": "x", "start": 5, "end": 5})
    with pytest.raises(SystemExit, match="text, a sign, a picture, a colour, a shape or an icon"):
        O.add(d, {"kind": "video", "text": "x"})
    with pytest.raises(SystemExit, match="Choose the picture"):
        O.add(d, {"kind": "image", "text": "x"})
    long = O.add(d, {"kind": "text", "text": "x" * 5000})
    assert len(long[-1]["text"]) == O.MAX_TEXT
    u = O.update(d, o["id"], {"text": "Changed", "enabled": False, "y": 0.3})
    assert u[0]["text"] == "Changed" and u[0]["enabled"] is False and u[0]["y"] == 0.3 and u[0]["x"] == 1.0
    with pytest.raises(SystemExit, match="isn't in the project"):
        O.update(d, "nope", {"text": "x"})
    assert len(O.remove(d, o["id"])) == 1


def test_a_picture_is_copied_into_the_project_and_only_picture_types_are_taken(tmp_path):
    d = _project(tmp_path)
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (200, 100), (255, 0, 0, 255)).save(logo)
    r = O.add(d, {"image": str(logo), "width": 0.2, "start": 1, "end": 2})
    assert r[0]["kind"] == "image" and r[0]["file"].startswith("assets/overlays/") and os.path.exists(os.path.join(d, r[0]["file"])) and logo.exists()
    (tmp_path / "x.exe").write_bytes(b"MZ")
    with pytest.raises(SystemExit, match="PNG, JPG, WebP"):
        O.add(d, {"image": str(tmp_path / "x.exe")})
    with pytest.raises(SystemExit, match="PNG, JPG, WebP"):
        O.add(d, {"image": str(tmp_path / "missing.png")})


# ---------------------------------------------------------------- what it looks like

def test_text_and_signs_are_drawn_transparent_with_a_shadow(tmp_path):
    d = _project(tmp_path)
    t = O.render_image(d, {"kind": "text", "text": "I AM YOUR MOTHER!", "size": 0.08, "color": "#ffcc00"}, 1280, 720)
    assert t.mode == "RGBA" and t.getpixel((0, 0))[3] == 0                                           # transparent around the lettering
    opaque = [p for p in t.getdata() if p[3] > 240]
    assert any(abs(r - 255) < 12 and abs(g - 204) < 12 and b < 40 for r, g, b, a in opaque)           # the colour asked for
    assert any(a > 60 and r < 40 and g < 40 for r, g, b, a in t.getdata())                            # and a dark shadow around it
    assert t.height > 20 and t.width > t.height
    (tmp_path / "sign.svg").write_text(TITLE_SVG, encoding="utf-8")
    os.makedirs(os.path.join(d, "assets"), exist_ok=True)
    (tmp_path / "p" / "assets" / "sign.svg").write_text(TITLE_SVG, encoding="utf-8")
    s = O.render_image(d, {"kind": "svg", "file": "assets/sign.svg", "width": 0.5}, 1280, 720)
    assert s.mode == "RGBA" and abs(s.width - 640) < 40 and s.getpixel((0, 0))[3] == 0
    assert any(abs(r - 0xd8) < 30 and abs(g - 0xb3) < 30 and a > 240 for r, g, b, a in s.getdata())      # the sign's gold, as the package drew it


def test_a_sign_with_shapes_or_a_file_outside_the_project_is_refused(tmp_path):
    d = _project(tmp_path)
    os.makedirs(os.path.join(d, "assets"))
    open(os.path.join(d, "assets", "logo.svg"), "w").write('<svg xmlns="http://www.w3.org/2000/svg" width="9" height="9"><circle cx="4" cy="4" r="3"/></svg>')
    with pytest.raises(SystemExit, match="can't be drawn"):
        O.render_image(d, {"kind": "svg", "file": "assets/logo.svg"}, 1280, 720)
    outside = tmp_path / "outside.png"
    Image.new("RGBA", (10, 10)).save(outside)
    with pytest.raises(SystemExit, match="is missing"):
        O.render_image(d, {"kind": "image", "file": os.path.relpath(outside, d), "text": "x"}, 1280, 720)


# ---------------------------------------------------------------- it lands in the film

def _video(path, secs=4.0, color="blue", size="320x180"):
    subprocess.run([E.ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={color}:s={size}:r=24:d={secs}",
                    "-f", "lavfi", "-i", f"sine=frequency=330:duration={secs}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path],
                   check=True, creationflags=E.NO_WINDOW)


def _frame(video, t, out):
    subprocess.run([E.ffmpeg(), "-y", "-loglevel", "error", "-ss", str(t), "-i", video, "-frames:v", "1", out], check=True, creationflags=E.NO_WINDOW)
    return Image.open(out).convert("RGB")


def _bright(img, box=None):
    a = np.asarray(img.crop(box) if box else img).astype(int)
    return int((a.sum(axis=2) > 500).sum())


def test_text_appears_only_between_its_times_and_the_sound_is_kept(tmp_path):
    d = _project(tmp_path, sections=[], duration=4.0)
    video = str(tmp_path / "v.mp4")
    _video(video)
    O.add(d, {"kind": "text", "text": "BOUNDARIES?", "size": 0.14, "y": 0.5, "color": "#ffffff", "start": 1.0, "end": 3.0, "fade": 0.2})
    r = O.burn(d, video, 320, 180)
    assert r == {"count": 1, "captions": 0}
    before, during, after = (_frame(video, t, str(tmp_path / f"f{t}.png")) for t in (0.5, 2.0, 3.6))
    assert _bright(before) == 0 and _bright(after) == 0                                               # plain blue outside the window
    assert _bright(during) > 150                                                                      # white lettering in the middle of it
    info = subprocess.run([E.ffmpeg(), "-hide_banner", "-i", video], capture_output=True, text=True).stderr
    assert "Audio: aac" in info and "Duration: 00:00:04" in info.replace("Duration: 00:00:03.9", "Duration: 00:00:04")


def test_nothing_is_changed_when_there_is_no_text_or_it_cannot_be_drawn(tmp_path):
    d = _project(tmp_path, sections=[], duration=4.0)
    video = str(tmp_path / "v.mp4")
    _video(video)
    before = open(video, "rb").read()
    assert O.burn(d, video, 320, 180) == {"count": 0, "captions": 0} and open(video, "rb").read() == before
    O.add(d, {"kind": "text", "text": "off", "start": 1, "end": 2, "enabled": False})
    assert O.burn(d, video, 320, 180) == {"count": 0, "captions": 0} and open(video, "rb").read() == before             # a switched-off overlay is skipped
    items = O.load(d)
    items.append({"id": "bad", "kind": "image", "file": "assets/gone.png", "text": "gone", "start": 1, "end": 2, "enabled": True})
    O._save(d, items)
    r = O.burn(d, video, 320, 180)
    assert r["count"] == 0 and "is missing" in r["error"] and open(video, "rb").read() == before         # the film is never lost


def test_the_real_export_draws_the_text_and_reports_it(tmp_path):
    d = tmp_path / "e"
    (d / "generations").mkdir(parents=True)
    shots = [{"id": "S01-01", "start": 0.0, "end": 1.5, "beats": ["a"], "performers": []}, {"id": "S01-02", "start": 1.5, "end": 3.0, "beats": ["b"], "performers": []}]
    (d / "production.json").write_text(json.dumps({"scenes": [{"number": 1, "heading": "INT. ROOM", "shots": shots}]}))
    (d / "project.json").write_text(json.dumps({"title": "T", "song": "song.wav"}))
    (d / "songmap.json").write_text(json.dumps({"duration": 3.0, "sections": [{"label": "CHORUS", "start": 0, "end": 3}]}))
    t = np.linspace(0, 3, 132300, endpoint=False)
    sf.write(str(d / "song.wav"), (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), 44100)
    (d / "jobs.json").write_text(json.dumps({"jobs": []}))
    plain = E.build(str(d), "square")
    assert plain["overlays"] == 0
    base = _frame(plain["path"], 1.0, str(tmp_path / "a.png"))                                         # looked at now: the next export reuses the file name
    O.add(str(d), {"kind": "text", "text": "I AM YOUR MOTHER!", "section": "chorus1", "size": 0.09, "y": 0.5})
    r = E.build(str(d), "square")
    assert r["overlays"] == 1 and "overlay_error" not in r
    drawn = _frame(r["path"], 1.0, str(tmp_path / "b.png"))
    assert _bright(drawn) > _bright(base) + 500                                                       # the lettering is in the exported picture


# ---------------------------------------------------------------- from a Producer package

def test_a_preview_shows_the_overlay_where_it_will_sit(tmp_path):
    d = _project(tmp_path)
    r = O.add(d, {"kind": "text", "text": "Hello", "y": 0.2, "size": 0.12, "start": 1, "end": 2})
    p = O.preview(d, r[0]["id"])
    img = Image.open(os.path.join(d, p["path"])).convert("RGB")
    assert img.size == (960, 540)
    top, bottom = _bright(img, (0, 0, 960, 270)), _bright(img, (0, 270, 960, 540))
    assert top > 100 and bottom == 0                                                                  # in the upper half, as asked


def test_layers_can_be_named_reordered_and_duplicated(tmp_path):
    d = str(tmp_path)
    O.add(d, {"kind": "text", "text": "A", "start": 0, "end": 4, "name": "  Lower   third "})
    O.add(d, {"kind": "text", "text": "B", "start": 0, "end": 4})
    O.add(d, {"kind": "text", "text": "C", "start": 0, "end": 4})
    ids = [o["id"] for o in O.load(d)]
    assert O.load(d)[0]["name"] == "Lower third"
    assert [o["text"] for o in O.reorder(d, ids[0], "top")] == ["B", "C", "A"]                         # the last is drawn on top
    assert [o["text"] for o in O.reorder(d, ids[0], "down")] == ["B", "A", "C"]
    assert [o["text"] for o in O.reorder(d, ids[2], "bottom")] == ["C", "B", "A"]
    assert [o["text"] for o in O.reorder(d, ids[2], 1)] == ["B", "C", "A"]
    with pytest.raises(SystemExit, match="Choose up, down"):
        O.reorder(d, ids[0], "sideways")
    with pytest.raises(SystemExit, match="isn't in the project"):
        O.reorder(d, "nope", "up")
    out = O.duplicate(d, ids[0])
    assert [o["text"] for o in out] == ["B", "C", "A", "A"] and out[2]["id"] != out[3]["id"] and out[3]["name"] == "Lower third copy" and out[3]["y"] > out[2]["y"]
