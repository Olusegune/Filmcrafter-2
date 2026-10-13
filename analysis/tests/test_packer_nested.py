"""Packing a project that has copies of itself inside it (a Save As into the project's own folder) must work: the copies are left out, and their depth never reaches the file system."""
import json
import os
import sys
import zipfile

import pytest

from filmcrafter_engine import packer


def make_project(root, name="Exit Plan", extra=None):
    d = os.path.join(root, name)
    os.makedirs(os.path.join(d, "assets"), exist_ok=True)
    json.dump({"title": name}, open(os.path.join(d, "project.json"), "w"))
    open(os.path.join(d, "assets", "a.png"), "wb").write(b"x")
    open(os.path.join(d, "commands.json"), "w").write("{}")
    for k, v in (extra or {}).items():
        os.makedirs(os.path.dirname(os.path.join(d, k)), exist_ok=True)
        open(os.path.join(d, k), "w").write(v)
    return d


def names(path):
    return sorted(n for n in zipfile.ZipFile(path).namelist() if n not in ("pulse.json", "filmpack.json"))


def test_a_copy_inside_the_project_is_left_out_and_reported(tmp_path):
    d = make_project(str(tmp_path))
    make_project(d, "Exit Plan copy")                                                       # what Save As into its own folder leaves behind
    r = packer.pack(d, str(tmp_path / "out.pulse"))
    assert r["left_out"] == ["Exit Plan copy"]
    assert names(r["path"]) == ["project/assets/a.png", "project/commands.json", "project/project.json"]


def test_copies_inside_copies_are_left_out_as_one(tmp_path):
    d = make_project(str(tmp_path))
    inner = make_project(d, "copy")
    make_project(inner, "copy")
    r = packer.pack(d, str(tmp_path / "o.pulse"))
    assert r["left_out"] == ["copy"] and r["files"] == 3


@pytest.mark.skipif(sys.platform != "win32", reason="the 260-character limit is Windows'")
def test_a_chain_of_copies_longer_than_windows_allows_does_not_break_packing(tmp_path):
    """The reported failure: ...\\Exit Plan video By Uncle Sege 8 copy\\Exit Plan video By Uncle Sege 8 copy\\... five deep, then WinError 3 on commands.json."""
    d = make_project(str(tmp_path), "Exit Plan By Uncle Sege 8")
    deep = "\\\\?\\" + d                                                                  # the extended form can make paths of any length
    for _ in range(6):
        deep = os.path.join(deep, "Exit Plan video By Uncle Sege 8 copy")
        os.makedirs(os.path.join(deep, "assets"), exist_ok=True)
        open(os.path.join(deep, "project.json"), "w").write('{"title": "copy"}')
        open(os.path.join(deep, "commands.json"), "w").write("{}")
    assert len(deep) > 260
    r = packer.pack(d, str(tmp_path / "Exit Plan By Uncle Sege 8.pulse"))
    assert r["left_out"] == ["Exit Plan video By Uncle Sege 8 copy"]
    assert len(names(r["path"])) == 3


def test_folders_that_are_not_projects_are_still_packed(tmp_path):
    d = make_project(str(tmp_path), extra={"exports/film.mp4": "v", "notes/readme.txt": "n"})
    r = packer.pack(d, str(tmp_path / "o.pulse"))
    assert r["left_out"] == []
    assert "project/exports/film.mp4" in names(r["path"]) and "project/notes/readme.txt" in names(r["path"])


def test_the_usual_rebuildable_folders_are_still_skipped(tmp_path):
    d = make_project(str(tmp_path), extra={"cache/x.bin": "c", "thumbnails/t.png": "t", "backups/b.json": "b"})
    r = packer.pack(d, str(tmp_path / "o.pulse"))
    assert not any(n.startswith(("project/cache", "project/thumbnails", "project/backups")) for n in names(r["path"]))


def test_a_folder_with_no_project_is_refused_in_plain_words(tmp_path):
    (tmp_path / "x").mkdir()
    with pytest.raises(SystemExit) as e:
        packer.pack(str(tmp_path / "x"), str(tmp_path / "o.pulse"))
    assert "isn't a FilmCrafter film" in str(e.value)


def test_a_copy_that_stopped_part_way_without_project_json_is_still_recognised_and_left_out(tmp_path):
    """The reported case: the first copy had a .filmcrafter file, directed.json and commands.json but no project.json yet."""
    d = make_project(str(tmp_path))
    part = os.path.join(d, "Exit Plan copy")
    os.makedirs(os.path.join(part, "assets"))
    for n in ("directed.json", "commands.json", "Exit Plan.filmcrafter"):
        open(os.path.join(part, n), "w").write("{}")
    r = packer.pack(d, str(tmp_path / "o.pulse"))
    assert r["left_out"] == ["Exit Plan copy"] and r["files"] == 3


@pytest.mark.parametrize("files,expected", [(["project.json"], True), (["a.filmcrafter"], True), (["directed.json", "commands.json"], True), (["directed.json"], False), (["notes.txt", "song.wav"], False), ([], False)])
def test_what_counts_as_a_project_folder(tmp_path, files, expected):
    f = tmp_path / "f"
    f.mkdir()
    for n in files:
        (f / n).write_text("x")
    assert packer.looks_like_project(str(f)) is expected
    assert packer.looks_like_project(str(tmp_path / "nowhere")) is False


def test_a_file_that_cannot_be_read_is_left_out_not_fatal(tmp_path, monkeypatch):
    d = make_project(str(tmp_path))
    real = os.path.getsize
    monkeypatch.setattr(packer.os.path, "getsize", lambda p: (_ for _ in ()).throw(FileNotFoundError(3, "gone")) if str(p).endswith("commands.json") else real(p))
    r = packer.pack(d, str(tmp_path / "o.pulse"))
    assert "project/commands.json" not in names(r["path"]) and "project/project.json" in names(r["path"])
