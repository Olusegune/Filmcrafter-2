"""Editing the film's cut, end to end: the door, the film's edit record, one undo for cuts and grades alike, and real exports of frame-numbered footage that prove a trim, a split or a
ripple lands on exactly the frame it should. Free and local: the footage is made here, nothing is rendered by a provider."""
import json
import os
import subprocess
import wave

import pytest
from PIL import Image

from filmcrafter_engine import edit_time as T, editing as ED, export as E, grading as G, media, sequence_derive as D

pytestmark = pytest.mark.integration

# a take that says which of its frames is which: the left half is grey level N mod 8 and the right half level (N div 8) mod 8, 25 grey steps apart, so a frame's number survives compression; a gap is black
SHOTS = [("S01-01", 1, 0.0, 2.0), ("S01-02", 1, 2.0, 4.0), ("S02-01", 2, 4.0, 6.0)]
FRAMES = 48


def ff(*args):
    subprocess.run([E.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args], check=True, creationflags=E.NO_WINDOW)


def build_film(tmp_path, shots=SHOTS, duration=6.0):
    d = tmp_path / "film"
    d.mkdir()
    with wave.open(str(d / "song.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\0\0" * int(22050 * (duration + 1)))
    json.dump({"title": "T", "song": "song.wav", "aspect_ratio": "16:9"}, open(d / "project.json", "w"))
    json.dump({"duration": duration, "sections": [], "lyrics": []}, open(d / "songmap.json", "w"))
    scenes = {}
    for i, (sid, sc, a, b) in enumerate(shots, 1):
        scenes.setdefault(sc, []).append({"id": sid, "scene": sc, "number": i, "start": a, "end": b, "beats": ["x"], "performers": []})
    json.dump({"scenes": [{"number": n, "heading": f"SCENE {n}", "start": 0, "end": duration, "shots": sh} for n, sh in scenes.items()]}, open(d / "production.json", "w"))
    json.dump({"jobs": []}, open(d / "jobs.json", "w"))
    clip = tmp_path / "coded.mp4"
    ff("-f", "lavfi", "-i", "color=c=black:s=64x64:r=24:d=3", "-vf", "geq=lum='if(lt(X,32),36+25*mod(N,8),36+25*mod(floor(N/8),8))':cb=128:cr=128,format=yuv420p", "-pix_fmt", "yuv420p", str(clip))
    for sid, *_ in shots:
        media.import_media(str(d), sid, str(clip))
    return str(d)


@pytest.fixture
def film(tmp_path):
    return build_film(tmp_path)


def index_at(video, frame, tmp_path):
    """Which frame of the coded take is on screen at this frame of the exported film: its number, or -9 for black."""
    out = str(tmp_path / f"f{frame}.png")
    ff("-i", video, "-vf", f"select='eq(n,{frame})'", "-frames:v", "1", out)
    im = Image.open(out).convert("RGB")
    level = lambda x: round((16 + im.getpixel((x, im.height // 2))[0] * 219 / 255 - 36) / 25)
    return 8 * level(3 * im.width // 4) + level(im.width // 4)


def clips(d):
    return [(c["shot"], c["start_frame"], c["source_in"] // T.FPS_24.frame_ticks, c["frames"]) for c in ED.get(d)["sequence"]["tracks"][0]["clips"]]


# ---------------------------------------------------------------- reading and conforming

def test_looking_at_a_film_that_was_never_edited_writes_nothing_and_reads_the_plan_as_the_export_always_has(tmp_path):
    odd = [("S01-01", 1, 0.0, 2.04), ("S01-02", 1, 2.04, 4.1), ("S02-01", 2, 4.1, 5.99)]               # times that are not whole frames
    d = build_film(tmp_path, odd, 6.0)
    got = ED.get(d)
    assert got["stored"] is False and not os.path.exists(os.path.join(d, "..", "edit")) and not os.path.exists(os.path.join(G.edit_dir(d), "edit.json"))
    legacy, cursor = [], 0
    for sid, _, a, b in odd:                                                                       # the export's own rule, written out
        f0, f1 = max(cursor, round(a * 24)), min(round(6.0 * 24), round(b * 24))
        legacy.append((sid, f0, f1 - f0))
        cursor = max(cursor, f1)
    assert [(c[0], c[1], c[3]) for c in clips(d)] == legacy
    assert got["sequence"]["length"] == T.tick_of_frame(144) and got["unplaced"] == [] and got["orphans"] == []


def test_the_first_edit_conforms_the_cut_once_and_keeps_the_grades(film):
    G.set_grade(film, "film", None, {"exposure": 0.2})
    assert ED.get(film)["stored"] is False
    res = ED.run(film, "edit", {"op": "split", "at": 1.0})
    assert res["stored"] is True and [(c[0], c[1], c[3]) for c in clips(film)][:2] == [("S01-01", 0, 24), ("S01-01", 24, 24)]
    rec = json.load(open(G._path(film)))
    assert rec["schema"] == 2 and rec["grades"]["film"] == {"exposure": 0.2} and "sequence" in rec
    assert [h["what"] for h in rec["history"]][-1] == "cut a clip"


# ---------------------------------------------------------------- the exported film

def test_a_film_that_was_never_edited_exports_every_frame_in_its_place(film, tmp_path):
    out = E.build(film, "preview")["path"]
    assert [index_at(out, k, tmp_path) for k in (0, 1, 23, 47)] == [0, 1, 23, 47]
    assert [index_at(out, k, tmp_path) for k in (48, 49, 95)] == [0, 1, 47]                         # the second shot starts its take again


def test_cutting_a_clip_in_two_changes_nothing_that_is_seen(film, tmp_path):
    before = E.build(film, "preview")["path"]
    want = [index_at(before, k, tmp_path) for k in (0, 10, 23, 24, 25, 47, 48, 100)]
    ED.run(film, "edit", {"op": "split", "at": 1.0})
    after = E.build(film, "preview")["path"]
    assert [index_at(after, k, tmp_path) for k in (0, 10, 23, 24, 25, 47, 48, 100)] == want
    assert want[:6] == [0, 10, 23, 24, 25, 47]
    assert [index_at(after, k, tmp_path) for k in (23, 24, 25)] == [23, 24, 25]                      # the cut is invisible: the take carries straight on


def test_a_trim_shows_exactly_the_frames_asked_for_and_leaves_a_black_gap_where_it_was_taken_from(film, tmp_path):
    ED.run(film, "edit", {"op": "trim", "clip": "c1", "edge": "in", "to": 0.5})                       # 12 frames given up from the start of the first clip, the film not closed up
    out = E.build(film, "preview")["path"]
    assert [index_at(out, k, tmp_path) for k in (0, 11)] == [-9, -9]                                   # black where the picture was taken away
    assert [index_at(out, k, tmp_path) for k in (12, 13, 47)] == [12, 13, 47]                           # and the frame that was at 12 is still at 12
    assert index_at(out, 48, tmp_path) == 0                                                              # the next shot did not move


def test_a_ripple_trim_closes_up_and_the_film_gets_shorter_by_exactly_that_many_frames(film, tmp_path):
    ED.run(film, "edit", {"op": "trim", "clip": "c1", "edge": "in", "to": 0.5, "ripple": True})
    res = E.build(film, "preview")
    out = res["path"]
    assert res["duration"] == pytest.approx(5.5)
    assert [index_at(out, k, tmp_path) for k in (0, 1, 35)] == [12, 13, 47]                              # the clip now begins at its own frame 12
    assert [index_at(out, k, tmp_path) for k in (36, 37)] == [0, 1]                                      # the next shot follows straight on, 12 frames earlier
    assert ED.get(film)["sequence"]["length"] == T.tick_of_frame(132)


def test_a_ripple_delete_brings_the_later_shots_forward(film, tmp_path):
    ED.run(film, "edit", {"op": "delete", "clip": "c2", "ripple": True})
    res = E.build(film, "preview")
    assert res["duration"] == pytest.approx(4.0) and res["shots"] == 2
    assert [index_at(res["path"], k, tmp_path) for k in (0, 47, 48, 95)] == [0, 47, 0, 47]


def test_a_shot_that_is_not_in_the_cut_is_said_so_and_can_be_placed_back(film, tmp_path):
    ED.run(film, "edit", {"op": "delete", "clip": "c3"})                                              # leaves a gap and the shot unplaced
    got = ED.get(film)
    assert got["unplaced"] == ["S02-01"]
    res = E.build(film, "preview")
    assert any("S02-01" in n and "not in the cut" in n for n in res["edit_notes"])
    back = ED.run(film, "place_missing", {})
    assert back["unplaced"] == [] and [c[0] for c in clips(film)][-1] == "S02-01"
    assert "edit_notes" not in E.build(film, "preview")
    with pytest.raises(SystemExit, match="Every shot already"):
        ED.run(film, "place_missing", {})


def test_a_clip_whose_shot_left_the_plan_is_left_out_with_a_note_and_nothing_is_lost(film, tmp_path):
    ED.run(film, "edit", {"op": "split", "at": 1.0})
    plan = json.load(open(os.path.join(film, "production.json")))
    plan["scenes"][1]["shots"] = []
    json.dump(plan, open(os.path.join(film, "production.json"), "w"))
    got = ED.get(film)
    assert got["orphans"] == ["c3"]
    res = E.build(film, "preview")
    assert any("S02-01" in n and "no longer in the plan" in n for n in res["edit_notes"])
    assert any(c["shot"] == "S02-01" for c in json.load(open(G._path(film)))["sequence"]["tracks"][0]["clips"])          # the record keeps it


def test_a_hidden_track_is_black_and_a_locked_one_cannot_be_edited(film, tmp_path):
    ED.run(film, "edit", {"op": "track_set", "track": "V1", "locked": True})
    with pytest.raises(SystemExit, match="locked"):
        ED.run(film, "edit", {"op": "split", "at": 1.0})
    ED.run(film, "edit", {"op": "track_set", "track": "V1", "locked": False, "hidden": True})
    out = E.build(film, "preview")["path"]
    assert index_at(out, 10, tmp_path) == -9


# ---------------------------------------------------------------- one undo for the cut and the grade

def test_one_history_undoes_and_redoes_a_cut_and_a_grade_alike(film):
    ED.run(film, "edit", {"op": "split", "at": 1.0})
    G.set_grade(film, "film", None, {"exposure": 0.4})
    ED.run(film, "edit", {"op": "trim", "clip": "c4", "edge": "out", "to": 1.5})
    assert [c[3] for c in clips(film)][:2] == [24, 12]
    r = ED.run(film, "undo", {})
    assert [c[3] for c in clips(film)][:2] == [24, 24] and r["can_redo"] and G.state(film)["grades"]["film"] == {"exposure": 0.4}
    ED.run(film, "undo", {})
    assert G.state(film)["grades"]["film"] == {}
    ED.run(film, "undo", {})
    assert ED.get(film)["stored"] is False                                                               # all the way back to a film that was never edited
    ED.run(film, "redo", {})
    ED.run(film, "redo", {})
    ED.run(film, "redo", {})
    assert [c[3] for c in clips(film)][:2] == [24, 12] and G.state(film)["grades"]["film"] == {"exposure": 0.4}
    with pytest.raises(SystemExit, match="nothing to do again"):
        ED.run(film, "redo", {})
    ED.run(film, "undo", {})
    ED.run(film, "edit", {"op": "marker_set", "at": 1.0, "name": "turn"})                                # a new edit ends the redo
    with pytest.raises(SystemExit, match="nothing to do again"):
        ED.run(film, "redo", {})


# ---------------------------------------------------------------- the door

def test_times_are_taken_in_seconds_and_land_on_whole_frames(film):
    ED.run(film, "edit", {"op": "split", "at": 0.51})                                                    # 12.24 frames is 12
    assert clips(film)[:2] == [("S01-01", 0, 0, 12), ("S01-01", 12, 12, 36)]
    for bad in ({"op": "split", "at": "soon"}, {"op": "split", "at": -1}, {"op": "trim", "clip": "c1", "edge": "middle", "to": 1}, {"op": "explode"}, {"op": "delete", "clip": "nope"},
                {"op": "move", "clip": 5, "to": 1}, {"op": "trim", "clip": "c1", "edge": "out", "to": 1, "ripple": "yes"}):
        with pytest.raises(SystemExit):
            ED.run(film, "edit", bad)


def test_snap_goes_to_a_cut_or_a_marker_within_a_few_frames(film):
    ED.run(film, "edit", {"op": "marker_set", "at": 1.0, "name": "m"})
    s = ED.run(film, "snap", {"at": 2.1})
    assert s["snapped"] and s["at"] == pytest.approx(2.0)
    assert ED.run(film, "snap", {"at": 1.05})["at"] == pytest.approx(1.0)
    assert ED.run(film, "snap", {"at": 3.0})["snapped"] is False
    assert ED.run(film, "snap", {"at": 3.0, "points": [3.1]})["at"] == pytest.approx(74 / 24)             # the point itself is rounded to its frame


def test_the_command_line_speaks_json_and_its_action_list_is_the_one_the_shell_must_match(film, capsys):
    assert ED.main(["sequence_get", film]) == 0 and json.loads(capsys.readouterr().out.splitlines()[-1])["data"]["stored"] is False
    assert ED.main(["edit", film, "--data", json.dumps({"op": "nonsense"})]) == 1 and "Unknown edit" in capsys.readouterr().out
    src = open(ED.__file__, encoding="utf-8").read()
    for a in ED.ACTIONS:
        assert f'"{a}"' in src.split("choices=")[1].split("]")[0]


def test_the_hand_off_files_say_the_cut_is_not_in_them_once_the_film_has_been_edited(film):
    assert ED.hand_off_note(film) is None
    ED.run(film, "edit", {"op": "split", "at": 1.0})
    assert "do not include those edits" in ED.hand_off_note(film)
