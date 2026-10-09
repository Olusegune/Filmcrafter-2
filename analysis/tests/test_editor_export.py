"""Send to Premiere Pro / DaVinci Resolve: a Final Cut Pro XML import file with the film and its shots. Parsed back by an independent reader."""
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pytest
import soundfile as sf

from pulseframe_analysis import editor_export as X, export as E


def _clip(path, secs, sound, color="gray"):
    cmd = [E.ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={color}:s=160x90:r=24:d={secs}"]
    if sound:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}", "-c:a", "aac", "-shortest"]
    subprocess.run(cmd + ["-c:v", "libx264", "-pix_fmt", "yuv420p", path], check=True, creationflags=E.NO_WINDOW)


@pytest.fixture
def project(tmp_path):
    d = tmp_path / "My Film & Co"                                     # spaces and an ampersand in the path
    (d / "generations").mkdir(parents=True)
    shots = [{"id": "S01-01", "start": 0.0, "end": 1.5, "beats": ["a"], "performers": []}, {"id": "S01-02", "start": 1.5, "end": 3.0, "beats": ["b"], "performers": []},
             {"id": "S01-03", "start": 3.0, "end": 4.0, "beats": ["c"], "performers": []}]
    json.dump({"scenes": [{"number": 1, "heading": "INT.", "shots": shots}]}, open(d / "production.json", "w"))
    json.dump({"title": 'Mother <&> "Queen"', "song": "song.wav"}, open(d / "project.json", "w"))
    json.dump({"duration": 4.0, "sections": []}, open(d / "songmap.json", "w"))
    t = np.linspace(0, 4, 176400, endpoint=False)
    sf.write(str(d / "song.wav"), (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), 44100)
    _clip(str(d / "generations" / "a&b.mp4"), 1.5, False, "red")     # an XML character in a file name
    _clip(str(d / "generations" / "t2.mp4"), 1.0, False, "green")        # shorter than its 1.5 s shot
    jobs = [{"id": f"j{i}", "shot_id": f"S01-0{i}", "plan": "production", "state": "ready", "output": ("generations/a&b.mp4" if i == 1 else "generations/t2.mp4"), "created": 1, "kind": "video",
             "provider": "fal"} for i in (1, 2)]                           # shot 3 has no take yet
    json.dump({"jobs": jobs}, open(d / "jobs.json", "w"))
    r = E.build(str(d), "square")
    return str(d), r["path"]


def _ids(root):
    return [e.get("id") for e in root.iter("clipitem")]


def test_both_editors_get_a_well_formed_file_with_a_bin_and_two_timelines(project):
    d, film = project
    out = {}
    for target, app in (("premiere", "Premiere Pro"), ("resolve", "DaVinci Resolve")):
        r = X.package(d, target)
        out[target] = r
        assert os.path.basename(r["path"]).endswith(f" - {app}.xml") and os.path.dirname(r["path"]) == r["folder"] and r["film"] == os.path.basename(film)
        assert r["sequences"] == 2 and r["shot_clips"] == 2 and r["missing"] == ["S01-03"] and ".xml file" in r["steps"]
        text = open(r["path"], encoding="utf-8").read()
        assert text.startswith("<?xml") and "<!DOCTYPE xmeml>" in text.split("\n")[1]
        root = ET.parse(r["path"]).getroot()                                                              # parses: the odd characters were escaped
        assert root.tag == "xmeml" and root.get("version") == "4"
        assert root.find("project/name").text == "Mother  Queen - PULSEFRAME"                              # characters a file name can't hold are dropped from the title
        assert [s.find("name").text for s in root.iter("sequence")] == ["Mother  Queen: finished film", "Mother  Queen: shots (to re-edit)"]
        assert "S01-01 - a&b.mp4" in [c.find("name").text for c in root.iter("clipitem")]                  # the & was escaped in the file and read back whole
        assert "a&amp;b.mp4" in text and "a&b.mp4" not in text
        assert len(set(_ids(root))) == len(_ids(root))                                                     # every clip id is unique
    assert out["premiere"]["path"] != out["resolve"]["path"]


def test_the_shots_sit_at_their_place_and_a_short_take_is_not_stretched(project):
    d, film = project
    root = ET.parse(X.package(d, "premiere")["path"]).getroot()
    seqs = list(root.iter("sequence"))
    film_seq, shots_seq = seqs
    fv = film_seq.find("media/video/track/clipitem")
    assert (fv.find("start").text, fv.find("end").text, fv.find("in").text) == ("0", "96", "0")            # 4 s at 24 fps
    clips = shots_seq.findall("media/video/track/clipitem")
    assert [(c.find("start").text, c.find("end").text) for c in clips] == [("0", "36"), ("36", "60")]      # 1.5 s, then 1.0 s (the take's own length)
    assert all(c.find("in").text == "0" for c in clips)
    sound = shots_seq.find("media/audio/track/clipitem")
    assert (sound.find("start").text, sound.find("end").text) == ("0", "96")                                # the film's own soundtrack runs the whole way
    files = [f for f in root.iter("file") if f.find("pathurl") is not None]
    assert len({f.get("id") for f in files}) == len(files) == 3                                           # each media file is defined once
    assert all(f.find("pathurl").text.startswith("file://localhost/") and " " not in f.find("pathurl").text for f in files)


def test_an_independent_reader_finds_the_same_timelines(project):
    otio = pytest.importorskip("opentimelineio")
    if "fcp_xml" not in otio.adapters.available_adapter_names():
        pytest.skip("no FCP XML reader installed")
    d, film = project
    r = X.package(d, "resolve")
    tl = otio.adapters.read_from_file(r["path"], "fcp_xml")
    timelines = list(tl.find_children(descended_from_type=otio.schema.Timeline)) if hasattr(tl, "find_children") and not isinstance(tl, otio.schema.Timeline) else [tl]
    assert len(timelines) == 2
    film_tl = next(t for t in timelines if "finished film" in t.name)
    shots_tl = next(t for t in timelines if "shots" in t.name)
    v = film_tl.video_tracks()[0]
    assert len(v) == 1 and v[0].duration().to_seconds() == pytest.approx(4.0, abs=0.05)
    sv = shots_tl.video_tracks()[0]
    clips = [c for c in sv if isinstance(c, otio.schema.Clip)]
    assert len(clips) == 2
    starts = [sv.range_of_child(c).start_time.to_seconds() for c in clips]
    assert starts == [pytest.approx(0.0, abs=0.05), pytest.approx(1.5, abs=0.05)]
    assert [c.media_reference.target_url.endswith(("a%26b.mp4", "a&b.mp4", "t2.mp4")) for c in clips] == [True, True]


def test_it_will_not_package_what_is_not_a_film_in_this_projects_exports(project, tmp_path):
    d, film = project
    with pytest.raises(SystemExit, match="Choose Premiere Pro or DaVinci Resolve"):
        X.package(d, "avid")
    outside = tmp_path / "other.mp4"
    _clip(str(outside), 1.0, True)
    with pytest.raises(SystemExit, match="this project's exports"):
        X.package(d, "premiere", str(outside))
    with pytest.raises(SystemExit, match="this project's exports"):
        X.package(d, "premiere", os.path.join(d, "exports", "..", "..", "other.mp4"))
    with pytest.raises(SystemExit, match="this project's exports"):
        X.package(d, "premiere", os.path.join(d, "project.json"))
    empty = tmp_path / "empty"
    empty.mkdir()
    json.dump({"title": "T"}, open(empty / "project.json", "w"))
    with pytest.raises(SystemExit, match="Export the film first"):
        X.package(str(empty), "resolve")


def test_a_project_without_shots_still_gets_the_finished_film_timeline(tmp_path):
    d = tmp_path / "bare"
    (d / "exports").mkdir(parents=True)
    json.dump({"title": "Bare"}, open(d / "project.json", "w"))
    _clip(str(d / "exports" / "Bare.mp4"), 2.0, True)
    r = X.package(str(d), "premiere")
    assert r["sequences"] == 1 and r["shot_clips"] == 0
    root = ET.parse(r["path"]).getroot()
    assert len(list(root.iter("sequence"))) == 1 and root.find(".//clipitem/link") is not None          # picture and sound are linked


def test_a_windows_path_is_written_the_way_premiere_writes_it():
    assert X._url(r"C:\Users\Ada Lovelace\My Films\a&b.mp4") == "file://localhost/C%3a/Users/Ada%20Lovelace/My%20Films/a%26b.mp4" or sys.platform != "win32"
    assert X._timebase(23.976) == (24, True) and X._timebase(24.0) == (24, False) and X._timebase(29.97) == (30, True) and X._timebase(25) == (25, False)
