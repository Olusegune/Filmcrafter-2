"""The motion library, 1.27: tags, search data, and moving the library between computers in a .zip (a trust boundary: nothing is unpacked wholesale)."""
import json
import os
import subprocess
import zipfile

import pytest

from filmcrafter_engine import compose as CO
from filmcrafter_engine.export import ffmpeg

pytestmark = pytest.mark.security


def make_clip(path, seconds=5, colour="red"):
    p = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}:size=160x90:rate=12:duration={seconds}", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path)],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return str(path)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return tmp_path / "home"


@pytest.fixture
def two(tmp_path, home):
    a = CO.lib_add(make_clip(tmp_path / "a.mp4", 5, "red"), "Walk")
    b = CO.lib_add(make_clip(tmp_path / "b.mp4", 6, "blue"), "Dance")
    return a, b


def manifest(items):
    return json.dumps({"format": CO.PACK_FORMAT, "version": 1, "items": items})


def pack(path, entries):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return str(path)


# ---------------------------------------------------------------- tags

def test_tags_are_cleaned_and_limited():
    assert CO._clean_tags([" Walk ", "walk", "SLOW  step", "", 5, None, "x" * 40, *[f"t{i}" for i in range(20)]]) == ["walk", "slow step", "x" * 24, "t0", "t1", "t2", "t3", "t4"]
    assert CO._clean_tags("walk") == [] and CO._clean_tags(None) == [] and CO._clean_tags({"a": 1}) == []
    assert CO._clean_tags(["a\x00b\x1fc"]) == ["a b c"]


def test_a_new_motion_has_no_tags_and_tags_can_be_set_and_cleared(two):
    a, _ = two
    assert a["tags"] == []
    listed = CO.lib_tag(a["id"], ["Walk", "slow", "walk"])
    assert next(x for x in listed if x["id"] == a["id"])["tags"] == ["walk", "slow"]
    assert next(x for x in CO.lib_tag(a["id"], []) if x["id"] == a["id"])["tags"] == []


def test_tagging_a_motion_that_is_gone_says_so(home):
    with pytest.raises(SystemExit, match="isn't in the library"):
        CO.lib_tag("0123456789", ["x"])


def test_the_list_carries_the_file_for_the_hover_picture(two):
    a, _ = two
    assert os.path.isfile(a["path"]) and os.path.dirname(a["path"]) == CO.lib_dir()


def test_an_old_index_without_tags_still_lists(two):
    idx = os.path.join(CO.lib_dir(), "index.json")
    items = json.load(open(idx))
    for i in items:
        i.pop("tags", None)
    json.dump(items, open(idx, "w"))
    assert all(x["tags"] == [] for x in CO.lib_list())


# ---------------------------------------------------------------- export and import

def test_export_then_import_on_another_computer_keeps_names_and_tags(tmp_path, two, monkeypatch):
    a, b = two
    CO.lib_tag(a["id"], ["walk", "slow"])
    out = CO.lib_export(str(tmp_path / "lib"))
    assert out["count"] == 2 and out["path"].endswith("lib.zip") and zipfile.is_zipfile(out["path"])
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "other"))
    monkeypatch.setenv("HOME", str(tmp_path / "other"))
    r = CO.lib_import(out["path"])
    assert (r["added"], r["skipped"], r["refused"]) == (2, 0, 0)
    got = {x["name"]: x for x in r["items"]}
    assert set(got) == {"Walk", "Dance"} and got["Walk"]["tags"] == ["walk", "slow"] and got["Dance"]["thumb"].startswith("data:image/jpeg")
    assert len({x["id"] for x in r["items"]}) == 2                                          # ids are made here, never taken from the file
    assert all(os.path.isfile(x["path"]) for x in r["items"])


def test_importing_the_same_library_twice_adds_nothing(tmp_path, two):
    out = CO.lib_export(str(tmp_path / "lib.zip"))
    r = CO.lib_import(out["path"])
    assert (r["added"], r["skipped"]) == (0, 2) and len(r["items"]) == 2


def test_export_can_be_limited_to_chosen_motions(tmp_path, two):
    a, _ = two
    assert CO.lib_export(str(tmp_path / "one.zip"), [a["id"]])["count"] == 1
    with zipfile.ZipFile(tmp_path / "one.zip") as z:
        assert sorted(z.namelist()) == sorted(["manifest.json", a["id"] + ".mp4"])


def test_export_refuses_an_empty_library_and_the_library_folder(tmp_path, home):
    with pytest.raises(SystemExit, match="nothing in the library"):
        CO.lib_export(str(tmp_path / "x.zip"))


def test_export_will_not_write_inside_the_library(tmp_path, two):
    with pytest.raises(SystemExit, match="outside the library"):
        CO.lib_export(os.path.join(CO.lib_dir(), "x.zip"))


# ---------------------------------------------------------------- hostile files

def test_a_file_that_is_not_a_zip_or_not_there(tmp_path, home):
    bad = tmp_path / "x.zip"
    bad.write_text("nope")
    with pytest.raises(SystemExit, match="zip"):
        CO.lib_import(str(bad))
    with pytest.raises(SystemExit, match="can't be found"):
        CO.lib_import(str(tmp_path / "missing.zip"))


@pytest.mark.parametrize("entries,message", [
    ({"readme.txt": "hi"}, "no manifest"),
    ({"manifest.json": "{not json"}, "can't be read"),
    ({"manifest.json": json.dumps({"format": "other", "version": 1, "items": []})}, "isn't a FilmCrafter"),
    ({"manifest.json": json.dumps({"format": CO.PACK_FORMAT, "version": 2, "items": []})}, "isn't a FilmCrafter"),
    ({"manifest.json": json.dumps({"format": CO.PACK_FORMAT, "version": 1, "items": "x"})}, "isn't a FilmCrafter"),
    ({"manifest.json": json.dumps([1, 2])}, "isn't a FilmCrafter"),
])
def test_a_damaged_or_foreign_manifest_is_refused(tmp_path, home, entries, message):
    with pytest.raises(SystemExit, match=message):
        CO.lib_import(pack(tmp_path / "p.zip", entries))


def test_names_that_try_to_leave_the_folder_are_refused_and_nothing_is_written_outside(tmp_path, home):
    good = open(make_clip(tmp_path / "g.mp4"), "rb").read()
    names = ["../evil.mp4", "..\\evil.mp4", "/abs.mp4", "C:/abs.mp4", "sub/0123456789.mp4", "0123456789.exe", "0123456789.MP4", "manifest.json", 7, None]
    items = [{"file": n, "name": "x"} for n in names]
    entries = {"manifest.json": manifest(items), "../evil.mp4": good, "0123456789.exe": good, "sub/0123456789.mp4": good}
    r = CO.lib_import(pack(tmp_path / "p.zip", entries))
    assert (r["added"], r["refused"]) == (0, len(names))
    assert not (tmp_path / "evil.mp4").exists() and CO.lib_list() == []
    assert [f for f in os.listdir(CO.lib_dir()) if f != "index.json"] == []


def test_a_listed_file_that_is_not_a_video_is_refused(tmp_path, home):
    r = CO.lib_import(pack(tmp_path / "p.zip", {"manifest.json": manifest([{"file": "0123456789.mp4", "name": "fake"}]), "0123456789.mp4": b"MZ not a video at all"}))
    assert (r["added"], r["refused"]) == (0, 1) and CO.lib_list() == []
    assert [f for f in os.listdir(CO.lib_dir()) if f != "index.json"] == []                  # the temporary copy is cleaned up


def test_a_listed_file_that_is_missing_from_the_zip_is_refused(tmp_path, home):
    r = CO.lib_import(pack(tmp_path / "p.zip", {"manifest.json": manifest([{"file": "0123456789.mp4", "name": "ghost"}])}))
    assert (r["added"], r["refused"]) == (0, 1)


def test_names_tags_and_other_fields_from_the_file_are_cleaned(tmp_path, home):
    clip = open(make_clip(tmp_path / "g.mp4"), "rb").read()
    item = {"file": "0123456789.mp4", "name": "  \x00Evil\n name " + "z" * 200, "tags": ["OK", 5, "a" * 99, *["t"] * 3], "seconds": 9999, "width": "x", "id": "../../x", "thumb": "../../x.jpg", "fp": "boom"}
    r = CO.lib_import(pack(tmp_path / "p.zip", {"manifest.json": manifest([item]), "0123456789.mp4": clip}))
    (m,) = r["items"]
    assert r["added"] == 1 and len(m["name"]) <= 60 and "\n" not in m["name"] and m["tags"] == ["ok", "a" * 24, "t"]
    assert 4.5 < m["seconds"] < 5.5 and (m["width"], m["height"]) == (160, 90)                # measured here, not taken from the file
    assert m["id"] != "../../x" and os.path.dirname(m["path"]) == CO.lib_dir()


def test_too_many_files_in_a_zip_is_refused(tmp_path, home):
    entries = {f"f{i}.txt": "x" for i in range(CO.PACK_MAX_ENTRIES + 1)}
    entries["manifest.json"] = manifest([])
    with pytest.raises(SystemExit, match="too many files"):
        CO.lib_import(pack(tmp_path / "p.zip", entries))


def test_a_declared_size_over_the_limit_is_refused(tmp_path, home, monkeypatch):
    monkeypatch.setattr(CO, "PACK_MAX_TOTAL", 1000)
    with pytest.raises(SystemExit, match="too large"):
        CO.lib_import(pack(tmp_path / "p.zip", {"manifest.json": manifest([]), "pad.bin": b"0" * 5000}))


def test_an_oversize_video_is_refused_whatever_the_zip_says(tmp_path, home, monkeypatch):
    monkeypatch.setattr(CO, "MAX_VIDEO_MB", 0)
    clip = open(make_clip(tmp_path / "g.mp4"), "rb").read()
    r = CO.lib_import(pack(tmp_path / "p.zip", {"manifest.json": manifest([{"file": "0123456789.mp4", "name": "big"}]), "0123456789.mp4": clip}))
    assert (r["added"], r["refused"]) == (0, 1)


def test_a_full_library_stops_the_import(tmp_path, two, monkeypatch):
    out = CO.lib_export(str(tmp_path / "lib.zip"))
    monkeypatch.setattr(CO, "LIB_MAX", 2)
    with pytest.raises(SystemExit, match="library is full"):
        CO.lib_import(out["path"])


# ---------------------------------------------------------------- Remove can be undone

def test_a_removed_motion_can_be_brought_back_with_its_tags_and_picture(two):
    a, _ = two
    CO.lib_tag(a["id"], ["walk"])
    assert [x["name"] for x in CO.lib_remove(a["id"])] == ["Dance"]
    assert not os.path.exists(a["path"]) and os.path.exists(os.path.join(CO.lib_dir(), ".trash", a["id"] + ".mp4"))
    back = {x["id"]: x for x in CO.lib_restore(a["id"])}
    assert a["id"] in back and back[a["id"]]["tags"] == ["walk"] and back[a["id"]]["thumb"].startswith("data:image/jpeg") and os.path.isfile(back[a["id"]]["path"])
    assert [f for f in os.listdir(os.path.join(CO.lib_dir(), ".trash")) if f != "index.json"] == []                  # nothing is left behind in the trash


def test_restoring_twice_or_something_never_removed_says_so(two):
    a, _ = two
    CO.lib_remove(a["id"])
    CO.lib_restore(a["id"])
    with pytest.raises(SystemExit, match="can't be brought back"):
        CO.lib_restore(a["id"])
    with pytest.raises(SystemExit, match="can't be brought back"):
        CO.lib_restore("0123456789")


def test_the_trash_keeps_only_the_last_few_and_deletes_the_oldest_for_good(tmp_path, home, monkeypatch):
    monkeypatch.setattr(CO, "TRASH_MAX", 2)
    ids = []
    for i, colour in enumerate(("red", "blue", "green")):
        ids.append(CO.lib_add(make_clip(tmp_path / f"c{i}.mp4", 5, colour), f"c{i}")["id"])
    for i in ids:
        CO.lib_remove(i)
    left = {f for f in os.listdir(os.path.join(CO.lib_dir(), ".trash")) if f != "index.json"}
    assert not any(f.startswith(ids[0]) for f in left) and any(f.startswith(ids[1]) for f in left) and any(f.startswith(ids[2]) for f in left)
    with pytest.raises(SystemExit):
        CO.lib_restore(ids[0])


def test_restoring_a_motion_whose_video_was_added_again_does_not_duplicate_it(tmp_path, home):
    path = make_clip(tmp_path / "a.mp4", 5, "red")
    first = CO.lib_add(path, "one")
    CO.lib_remove(first["id"])
    CO.lib_add(path, "again")
    assert len(CO.lib_restore(first["id"])) == 1


def test_a_hostile_trash_or_library_index_cannot_reach_other_files(two, tmp_path):
    a, _ = two
    outside = tmp_path / "outside.txt"
    outside.write_text("keep")
    os.makedirs(os.path.join(CO.lib_dir(), ".trash"), exist_ok=True)
    json.dump([{"id": "0123456789", "name": "x", "file": "../../outside.txt", "thumb": "../index.json", "fp": "zz"}], open(os.path.join(CO.lib_dir(), ".trash", "index.json"), "w"))
    with pytest.raises(SystemExit, match="can't be brought back"):
        CO.lib_restore("0123456789")
    assert outside.read_text() == "keep" and os.path.isfile(a["path"]) and {x["id"] for x in CO.lib_list()} == {a["id"], two[1]["id"]}
    idx = json.load(open(os.path.join(CO.lib_dir(), "index.json")))
    idx.append({"id": "abcdef0123", "name": "evil", "file": "../../outside.txt", "thumb": None})
    json.dump(idx, open(os.path.join(CO.lib_dir(), "index.json"), "w"))
    assert "abcdef0123" not in {x["id"] for x in CO.lib_list()}
