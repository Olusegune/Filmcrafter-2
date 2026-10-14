"""A whole film in one file (.filmpack): everything that was made travels, nothing is lost, nothing is written outside the new folder."""
import json
import os
import zipfile

import pytest

from filmcrafter_engine import bible, make, packer, shots, story, voiceover

SCRIPT = "INT. YARD - DAY\n\nA schoolyard.\n\nLILA\nIt looked weird.\n\nCHLOE\nI know.\n"


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "Night Market", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    shots.breakdown(d)
    make.sync(d)
    rd = os.path.join(d, "render")
    os.makedirs(os.path.join(rd, "generations"), exist_ok=True)
    open(os.path.join(rd, "generations", "take.mp4"), "wb").write(b"video-bytes" * 100)         # what was paid for
    os.makedirs(os.path.join(rd, "cache"), exist_ok=True)
    open(os.path.join(rd, "cache", "rebuildable.bin"), "wb").write(b"x")
    os.makedirs(os.path.join(d, "voice", "S01-02"), exist_ok=True)
    open(os.path.join(d, "voice", "S01-02", "lila.wav"), "wb").write(b"RIFFxxxx")
    return d


def test_a_film_is_packed_whole_and_opened_as_a_new_film(film, tmp_path):
    out = packer.pack(film, str(tmp_path / "Night Market"))
    assert out["path"].endswith(".filmpack") and out["files"] > 10 and out["title"] == "Night Market"
    with zipfile.ZipFile(out["path"]) as z:
        names = z.namelist()
    assert "filmpack.json" in names and "project/film.json" in names
    assert "project/render/generations/take.mp4" in names and "project/voice/S01-02/lila.wav" in names and "project/render/project.json" in names
    assert not any("/cache/" in n for n in names)                                                   # rebuildable caches stay behind
    root = tmp_path / "other computer"
    root.mkdir()
    got = packer.unpack(out["path"], str(root))
    d2 = got["dir"]
    assert os.path.basename(d2) == "Night Market" and os.path.isfile(os.path.join(d2, "film.json"))
    assert open(os.path.join(d2, "render", "generations", "take.mp4"), "rb").read() == b"video-bytes" * 100
    assert os.path.isfile(os.path.join(d2, "voice", "S01-02", "lila.wav"))
    st = voiceover.status(d2)
    assert st["people"] >= 2                                                                          # the film reads as a film after the move


def test_opening_the_same_pack_twice_never_overwrites_and_renames_the_copy(film, tmp_path):
    out = packer.pack(film, str(tmp_path / "x"))
    root = tmp_path / "root"
    root.mkdir()
    a = packer.unpack(out["path"], str(root))["dir"]
    b = packer.unpack(out["path"], str(root))["dir"]
    assert a != b and os.path.basename(b) == "Night Market (2)"
    assert json.load(open(os.path.join(b, "film.json"), encoding="utf-8"))["title"] == "Night Market (2)"
    assert json.load(open(os.path.join(a, "film.json"), encoding="utf-8"))["title"] == "Night Market"


def test_a_render_project_and_a_file_from_an_earlier_version_still_open(tmp_path):
    proj = tmp_path / "old"
    proj.mkdir()
    (proj / "project.json").write_text(json.dumps({"title": "Old"}))
    (proj / "jobs.json").write_text("{}")
    old = tmp_path / "old.pulse"
    with zipfile.ZipFile(old, "w") as z:
        z.writestr("pulse.json", json.dumps({"format": 1, "title": "Old"}))                            # the earlier name of the info file
        z.write(proj / "project.json", "project/project.json")
    root = tmp_path / "r"
    root.mkdir()
    assert os.path.isfile(os.path.join(packer.unpack(str(old), str(root))["dir"], "project.json"))


def test_a_file_that_is_not_a_film_or_climbs_out_of_its_folder_is_refused(tmp_path):
    bad = tmp_path / "bad.filmpack"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("filmpack.json", json.dumps({"format": 1, "title": "Evil"}))
        z.writestr("project/film.json", "{}")
        z.writestr("project/../../escaped.txt", "x")
    root = tmp_path / "r"
    root.mkdir()
    with pytest.raises(SystemExit, match="unsafe path"):
        packer.unpack(str(bad), str(root))
    assert not (tmp_path / "escaped.txt").exists()
    empty = tmp_path / "empty.filmpack"
    with zipfile.ZipFile(empty, "w") as z:
        z.writestr("filmpack.json", json.dumps({"format": 1, "title": "Nothing"}))
    with pytest.raises(SystemExit, match="no film inside"):
        packer.unpack(str(empty), str(root))
    junk = tmp_path / "junk.filmpack"
    junk.write_bytes(b"not a zip")
    with pytest.raises(SystemExit, match="readable"):
        packer.unpack(str(junk), str(root))
    with pytest.raises(SystemExit, match="isn't a FilmCrafter film"):
        packer.pack(str(tmp_path), str(tmp_path / "z"))


# ---------------------------------------------------------------- opening a file that is not what it claims (Phase 0 limits)

def _hostile(path, extra):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("filmpack.json", json.dumps({"format": 1, "title": "Evil"}))
        z.writestr("project/film.json", json.dumps({"story": {}, "title": "Evil"}))
        for name, data in extra:
            z.writestr(name, data)
    return str(path)


@pytest.mark.parametrize("name,why", [("project/../../outside.txt", "unsafe path"), ("project/C:/x.txt", "unsafe path"),
                                      ("project/voice/./x.wav", "unsafe path"), ("project/bad. /x.txt", "unsafe path"), ("project//x", "unsafe path")])
def test_hostile_paths_are_refused_before_anything_is_written(tmp_path, name, why):
    pack = _hostile(tmp_path / "e.filmpack", [(name, b"x")])
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(SystemExit, match=why):
        packer.unpack(pack, str(root))
    assert os.listdir(root) == [] and not (tmp_path / "outside.txt").exists()


def test_a_link_inside_a_film_file_is_refused(tmp_path):
    p = str(tmp_path / "l.filmpack")
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("filmpack.json", json.dumps({"format": 1, "title": "L"}))
        z.writestr("project/film.json", "{}")
        info = zipfile.ZipInfo("project/link")
        info.external_attr = (0o120777) << 16
        z.writestr(info, "C:/Windows")
    root = tmp_path / "r"
    root.mkdir()
    with pytest.raises(SystemExit, match="link"):
        packer.unpack(p, str(root))
    assert os.listdir(root) == []


def test_too_many_items_and_an_expansion_bomb_and_too_little_disk_are_refused(tmp_path, monkeypatch):
    root = tmp_path / "r"
    root.mkdir()
    monkeypatch.setattr(packer, "MAX_ENTRIES", 5)
    pack = _hostile(tmp_path / "m.filmpack", [(f"project/f{i}.txt", b"x") for i in range(10)])
    with pytest.raises(SystemExit, match="more than 5 items"):
        packer.unpack(pack, str(root))
    monkeypatch.setattr(packer, "MAX_ENTRIES", 200_000)
    monkeypatch.setattr(packer, "RATIO_FLOOR", 1000)
    pack = _hostile(tmp_path / "b.filmpack", [("project/zeros.bin", b"\0" * 5_000_000)])                 # compresses to a few KB
    with pytest.raises(SystemExit, match="expands far more"):
        packer.unpack(pack, str(root))
    monkeypatch.setattr(packer, "RATIO_FLOOR", 10**12)
    monkeypatch.setattr(packer, "DISK_MARGIN", 10**18)                                                  # pretend the disk is nearly full
    with pytest.raises(SystemExit, match="is free here"):
        packer.unpack(pack, str(root))
    assert os.listdir(root) == []


def test_a_file_that_lies_about_its_size_is_stopped_and_what_was_written_is_removed(tmp_path, monkeypatch):
    pack = _hostile(tmp_path / "s.filmpack", [("project/big.bin", b"abc" * 1000)])
    real = zipfile.ZipFile.getinfo

    def lying(self, name):
        i = real(self, name)
        if name == "project/big.bin":
            i.file_size = 10                                             # claims 10 bytes, holds 3000
        return i
    monkeypatch.setattr(zipfile.ZipFile, "getinfo", lying)
    root = tmp_path / "r"
    root.mkdir()
    with pytest.raises(SystemExit, match="do not match|is damaged"):
        packer.unpack(pack, str(root))
    assert os.listdir(root) == []                                         # the half-made folder is gone; nothing of the user's was touched


def test_a_real_film_still_opens_after_the_limits(film, tmp_path):
    out = packer.pack(film, str(tmp_path / "ok"))
    root = tmp_path / "r2"
    root.mkdir()
    assert os.path.isfile(os.path.join(packer.unpack(out["path"], str(root))["dir"], "film.json"))
