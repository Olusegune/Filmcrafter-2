"""Lyric captions: the lines, your edits to them, the subtitles file, and that they really appear in the exported film. Real ffmpeg."""
import json
import os
import subprocess

import numpy as np
import pytest
import soundfile as sf
from PIL import Image

from filmcrafter_engine import captions as C, export as E, overlays as O

LYRICS = [{"section": "Verse", "text": "Nine months I carry you,", "start": 0.4, "end": 1.2},
          {"section": "Verse", "text": "Now you tell me, \"Mummy, no\"?", "start": 1.5, "end": 2.0},
          {"section": "Chorus", "text": "I AM YOUR MOTHER!", "start": 2.2, "end": 2.9},
          {"section": "Chorus", "text": "I AM YOUR MOTHER!", "start": 3.4, "end": 3.9}]


def _project(tmp_path, lyrics=LYRICS, duration=4.5):
    d = tmp_path / "p"
    d.mkdir()
    (d / "project.json").write_text(json.dumps({"title": "T", "song": "song.wav"}))
    (d / "songmap.json").write_text(json.dumps({"duration": duration, "lyrics": lyrics}))
    return str(d)


# ---------------------------------------------------------------- the lines

def test_lines_come_from_the_song_map_and_never_run_into_each_other(tmp_path):
    d = _project(tmp_path)
    ls = C.lines(d)
    assert [x["text"] for x in ls] == [x["text"] for x in LYRICS] and all(not x["hidden"] and not x["edited"] for x in ls)
    assert all(a["end"] <= b["start"] - C.GAP + 1e-6 for a, b in zip(ls, ls[1:]))                 # a caption ends before the next begins
    assert all(x["end"] - x["start"] >= C.MIN_SHOW - 1e-6 or x is ls[1] for x in ls)             # and stays long enough to read when there is room
    assert len({x["key"] for x in ls}) == 4                                                       # the repeated line still has its own key
    assert ls[2]["key"].endswith("-1") and ls[3]["key"].endswith("-2")


def test_an_edit_follows_its_line_and_survives_a_new_analysis(tmp_path):
    d = _project(tmp_path)
    key = C.lines(d)[0]["key"]
    C.edit(d, key, {"text": "Nine months I carried you"})
    C.edit(d, C.lines(d)[1]["key"], {"hidden": True})
    ls = C.lines(d)
    assert ls[0]["text"] == "Nine months I carried you" and ls[0]["edited"] and ls[0]["original"] == "Nine months I carry you," and ls[1]["hidden"]
    moved = [{**x, "start": x["start"] + 0.7, "end": x["end"] + 0.7} for x in reversed(LYRICS)]      # analysed again: other timings, other order
    (tmp_path / "p" / "songmap.json").write_text(json.dumps({"duration": 6.0, "lyrics": moved}))
    again = {x["original"]: x for x in C.lines(d)}
    assert again["Nine months I carry you,"]["text"] == "Nine months I carried you" and again["Now you tell me, \"Mummy, no\"?"]["hidden"]
    C.edit(d, again["Nine months I carry you,"]["key"], {"reset": True})
    assert {x["original"]: x for x in C.lines(d)}["Nine months I carry you,"]["text"] == "Nine months I carry you,"          # put back as it was


def test_what_is_sent_is_checked(tmp_path):
    d = _project(tmp_path)
    k = C.lines(d)[0]["key"]
    with pytest.raises(SystemExit, match="Write the caption"):
        C.edit(d, k, {"text": "   "})
    with pytest.raises(SystemExit, match="end must be after"):
        C.edit(d, k, {"start": 2, "end": 1})
    with pytest.raises(SystemExit, match="isn't in the song"):
        C.edit(d, "nope-1", {"text": "x"})
    g = C.set_style(d, {"size": 9, "y": -3, "color": "red", "enabled": True, "names": 1})
    assert g["style"]["size"] == 0.15 and g["style"]["y"] == 0.05 and g["style"]["color"] == "#ffffff" and g["enabled"] and g["style"]["names"] is True
    assert C.edit(d, k, {"start": 0.1, "end": 0.9})["lines"][0]["start"] == 0.1


def test_a_song_without_timed_lyrics_says_what_to_do(tmp_path):
    d = _project(tmp_path, lyrics=[])
    g = C.get(d)
    assert not g["available"] and "no timed lyrics" in g["reason"]
    empty = tmp_path / "e"
    empty.mkdir()
    assert "hasn't been analysed" in C.get(str(empty))["reason"]


def test_a_spoken_scene_can_show_who_is_speaking(tmp_path):
    d = _project(tmp_path, lyrics=[{"section": "Scene", "text": "Where were you?", "start": 0.5, "end": 1.5, "performer": "Ada"},
                                   {"section": "Scene", "text": "Waiting.", "start": 2.0, "end": 2.6, "performer": "Ben"}])
    st = C.load(d)["style"]
    assert [C.caption_text(o, st) for o in C.lines(d)] == ["Where were you?", "Waiting."]
    C.set_style(d, {"names": True, "uppercase": True})
    st = C.load(d)["style"]
    assert [C.caption_text(o, st) for o in C.lines(d)] == ["Ada: WHERE WERE YOU?", "Ben: WAITING."]


# ---------------------------------------------------------------- the stream and the subtitles file

def test_the_track_holds_each_caption_for_its_time_and_covers_the_whole_film(tmp_path):
    d = _project(tmp_path)
    assert C.track(d, 320, 180, 4.5) is None                                                       # off until you turn it on
    C.set_style(d, {"enabled": True})
    C.edit(d, C.lines(d)[1]["key"], {"hidden": True})
    lst = C.track(d, 320, 180, 4.5)
    rows = [x for x in open(lst, encoding="utf-8").read().splitlines() if x.startswith("duration")]
    total = sum(float(x.split()[1]) for x in rows)
    assert total >= 4.5 and len(rows) >= 7                                                         # blank, line, blank ... 3 visible lines
    pngs = [x for x in open(lst, encoding="utf-8").read().splitlines() if x.startswith("file") and "blank" not in x]
    assert len(pngs) == 3                                                                          # three captions (the repeated last file is a blank)


def test_subtitles_are_written_next_to_the_film_with_your_edits(tmp_path):
    d = _project(tmp_path)
    video = str(tmp_path / "film.mp4")
    open(video, "wb").write(b"x")
    assert C.write_srt(d, video) is None                                                           # off
    C.set_style(d, {"enabled": True})
    C.edit(d, C.lines(d)[0]["key"], {"text": "Nine months I carried you"})
    C.edit(d, C.lines(d)[1]["key"], {"hidden": True})
    srt = open(C.write_srt(d, video), encoding="utf-8").read()
    assert srt.startswith("1\n00:00:00,400 -->") and "Nine months I carried you" in srt and "Mummy" not in srt and srt.count("I AM YOUR MOTHER!") == 2
    C.set_style(d, {"srt": False})
    assert C.write_srt(d, video) is None


# ---------------------------------------------------------------- it lands in the film

def _frame(video, t, out):
    subprocess.run([E.ffmpeg(), "-y", "-loglevel", "error", "-ss", str(t), "-i", video, "-frames:v", "1", out], check=True, creationflags=E.NO_WINDOW)
    return Image.open(out).convert("RGB")


def _bottom_bright(img):
    a = np.asarray(img.crop((0, int(img.height * 0.78), img.width, img.height))).astype(int)
    return int((a.sum(axis=2) > 600).sum())


def _exp_project(tmp_path, lyrics=LYRICS):
    d = tmp_path / "e"
    (d / "generations").mkdir(parents=True)
    shots = [{"id": "S01-01", "start": 0.0, "end": 2.25, "beats": ["a"], "performers": []}, {"id": "S01-02", "start": 2.25, "end": 4.5, "beats": ["b"], "performers": []}]
    (d / "production.json").write_text(json.dumps({"scenes": [{"number": 1, "heading": "INT. ROOM", "shots": shots}]}))
    (d / "project.json").write_text(json.dumps({"title": "T", "song": "song.wav"}))
    (d / "songmap.json").write_text(json.dumps({"duration": 4.5, "lyrics": lyrics}))
    t = np.linspace(0, 4.5, 198450, endpoint=False)
    sf.write(str(d / "song.wav"), (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), 44100)
    (d / "jobs.json").write_text(json.dumps({"jobs": []}))
    return str(d)


def test_the_real_export_shows_each_line_only_while_it_is_sung(tmp_path):
    d = _exp_project(tmp_path)
    plain = E.build(d, "square")
    assert plain["captions"] == 0 and plain["subtitles"] is None
    base = {t: _frame(plain["path"], t, str(tmp_path / f"base{t}.png")) for t in (0.8, 2.5, 3.1)}
    C.set_style(d, {"enabled": True, "size": 0.06})
    C.edit(d, C.lines(d)[2]["key"], {"hidden": True})                                              # hide the first "I AM YOUR MOTHER!"
    r = E.build(d, "square")
    assert r["captions"] == 1 and r["overlays"] == 0 and r["subtitles"].endswith(".srt") and "overlay_error" not in r
    on = _frame(r["path"], 0.8, str(tmp_path / "on0.8.png"))                                       # "Nine months I carry you," is being sung
    hidden = _frame(r["path"], 2.5, str(tmp_path / "on2.5.png"))                                   # a hidden line: no caption
    gap = _frame(r["path"], 3.1, str(tmp_path / "on3.1.png"))                                      # between lines
    assert _bottom_bright(on) > _bottom_bright(base[0.8]) + 150
    assert abs(_bottom_bright(hidden) - _bottom_bright(base[2.5])) < 60 and abs(_bottom_bright(gap) - _bottom_bright(base[3.1])) < 60
    last = _frame(r["path"], 3.6, str(tmp_path / "on3.6.png"))
    assert _bottom_bright(last) > _bottom_bright(base[3.1]) + 150                                  # the second "I AM YOUR MOTHER!" shows


def test_captions_and_on_screen_text_appear_together(tmp_path):
    d = _exp_project(tmp_path)
    plain = E.build(d, "square")
    base_top = _frame(plain["path"], 0.8, str(tmp_path / "b.png"))
    C.set_style(d, {"enabled": True, "size": 0.06})
    O.add(d, {"kind": "text", "text": "SIGN", "size": 0.12, "y": 0.2, "start": 0.2, "end": 1.2})
    r = E.build(d, "square")
    assert r["captions"] == 1 and r["overlays"] == 1
    f = _frame(r["path"], 0.8, str(tmp_path / "t.png"))
    top = lambda im: int((np.asarray(im.crop((0, 0, im.width, int(im.height * 0.4)))).astype(int).sum(axis=2) > 600).sum())
    assert top(f) > top(base_top) + 150 and _bottom_bright(f) > _bottom_bright(base_top) + 150      # the sign up top and the lyric at the bottom


# ---------------------------------------------------------------- a section's look and a single line's look

def test_look_is_layered_film_then_section_then_line(tmp_path):
    d = _project(tmp_path)
    ls = C.lines(d)
    assert all(x["look"] == {"size": 0.05, "y": 0.9, "color": "#ffffff", "font": ""} and x["own"] == {} for x in ls)
    g = C.set_section(d, "chorus", {"size": 0.09, "color": "#FFCC00"})                              # every chorus line: bigger and yellow
    assert g["sections"] == {"CHORUS": {"size": 0.09, "color": "#ffcc00"}} and g["section_names"] == ["CHORUS", "VERSE"]
    ls = C.lines(d)
    assert ls[0]["look"]["size"] == 0.05 and ls[2]["look"] == {"size": 0.09, "y": 0.9, "color": "#ffcc00", "font": ""}
    C.edit(d, ls[3]["key"], {"color": "#ff0000", "y": 0.2})                                         # one chorus line: red and up top
    last = C.lines(d)[3]
    assert last["look"] == {"size": 0.09, "y": 0.2, "color": "#ff0000", "font": ""} and last["own"] == {"color": "#ff0000", "y": 0.2}
    C.set_style(d, {"size": 0.07})                                                                  # the film's own size changes: verses follow, the chorus doesn't
    ls = C.lines(d)
    assert ls[0]["look"]["size"] == 0.07 and ls[2]["look"]["size"] == 0.09
    C.edit(d, ls[3]["key"], {"color": "", "y": None})                                               # empty = inherit again
    assert C.lines(d)[3]["look"] == {"size": 0.09, "y": 0.9, "color": "#ffcc00", "font": ""} and not C.lines(d)[3]["edited"]
    C.set_section(d, "CHORUS", {"reset": True})
    assert C.lines(d)[2]["look"]["size"] == 0.07


def test_looks_are_clamped_and_bad_values_ignored(tmp_path):
    d = _project(tmp_path)
    C.set_section(d, "verse", {"size": 9, "y": -4, "color": "not-a-colour"})
    assert C.load(d)["sections"]["VERSE"] == {"size": 0.15, "y": 0.05}                              # clamped; the bad colour inherits instead
    with pytest.raises(SystemExit, match="Choose a section"):
        C.set_section(d, "  ", {"size": 0.05})
    C.edit(d, C.lines(d)[0]["key"], {"size": 0.001, "color": "zzz"})
    assert C.lines(d)[0]["own"] == {"size": 0.02}


def test_the_export_draws_each_line_in_its_own_look(tmp_path):
    d = _exp_project(tmp_path)
    plain = E.build(d, "square")
    base = {t: _frame(plain["path"], t, str(tmp_path / f"b{t}.png")) for t in (0.8, 2.5)}
    C.set_style(d, {"enabled": True, "size": 0.04})
    C.set_section(d, "chorus", {"size": 0.1})
    r = E.build(d, "square")
    verse = _bottom_bright(_frame(r["path"], 0.8, str(tmp_path / "v.png"))) - _bottom_bright(base[0.8])
    chorus = _bottom_bright(_frame(r["path"], 2.5, str(tmp_path / "c.png"))) - _bottom_bright(base[2.5])
    assert verse > 100 and chorus > 2 * verse                                                       # the same words are far larger in the chorus
