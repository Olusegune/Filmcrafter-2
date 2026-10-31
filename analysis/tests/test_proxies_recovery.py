"""Preview copies (proxies) for the Studio's player, and what happens when the film's edit record is damaged. Free and local; the footage is made here."""
import json
import os
import subprocess

import pytest
from PIL import Image

from filmcrafter_engine import editing as ED, export as E, grading as G, library, media, proxies as P, safeio
from tests.test_editing import build_film, ff, index_at

pytestmark = pytest.mark.integration


def big_clip(tmp_path, name="big.mp4", size="1280x960", seconds=3):
    clip = tmp_path / name
    ff("-f", "lavfi", "-i", f"color=c=black:s={size}:r=24:d={seconds}", "-vf", "geq=lum='if(lt(X,640),36+25*mod(N,8),36+25*mod(floor(N/8),8))':cb=128:cr=128,format=yuv420p", "-pix_fmt", "yuv420p", str(clip))
    return str(clip)


@pytest.fixture
def film(tmp_path):
    d = build_film(tmp_path)                                       # three small coded takes
    media.import_media(d, "S01-02", big_clip(tmp_path))            # and one that is big
    return d


# ---------------------------------------------------------------- preview copies

def test_only_a_big_clip_is_given_a_copy_and_the_status_says_which(film):
    st = P.status(film)
    rows = {r["shot"]: r for r in st["rows"]}
    assert st["big"] == 1 and rows["S01-02"]["big"] and not rows["S01-01"]["big"] and not rows["S02-01"]["big"]
    assert st["ready"] == 0 and not os.path.exists(P.folder(film))                 # looking makes nothing


def test_a_copy_is_made_small_named_from_its_take_and_found_again(film):
    out = P.build(film)
    assert out["made"] == 1 and out["ready"] == 1
    rel = next(r for r in out["rows"] if r["shot"] == "S01-02")["proxy"]
    assert rel.startswith("cache/proxies/") and rel.endswith(".mp4")
    assert P.lines_of(os.path.join(film, rel)) == 540 and os.path.getsize(os.path.join(film, rel)) > 0
    assert P.build(film)["made"] == 0                                              # asking again makes nothing more
    assert [r["proxy"] for r in P.status(film)["rows"] if r["big"]] == [rel]


def test_a_changed_take_gets_a_new_copy_and_the_old_one_is_not_used_for_it(film, tmp_path):
    P.build(film)
    take = next(r for r in P.status(film)["rows"] if r["shot"] == "S01-02")
    first = take["proxy"]
    path = os.path.join(film, take["output"])
    big_clip(tmp_path, "other.mp4", "1280x960", 4)
    with open(path, "wb") as f:
        f.write(open(tmp_path / "other.mp4", "rb").read())
    again = next(r for r in P.status(film)["rows"] if r["shot"] == "S01-02")
    assert again["proxy"] is None                                                  # the old copy is for the old take
    assert P.build(film)["made"] == 1 and next(r for r in P.status(film)["rows"] if r["shot"] == "S01-02")["proxy"] != first


def test_the_board_offers_the_copy_to_the_player_only_when_there_is_one(film):
    shot = lambda: next(s for s in library.storyboard(film)["shots"] if s["id"] == "S01-02")
    assert shot()["preview_proxy"] is None and shot()["preview"].endswith(".mp4")
    P.build(film)
    assert shot()["preview_proxy"].startswith("cache/proxies/") and shot()["preview"] == next(r for r in P.status(film)["rows"] if r["shot"] == "S01-02")["output"]       # the take itself is still named


def test_the_export_never_reads_a_copy_and_the_film_is_the_same_with_or_without_them(film, tmp_path):
    src = open(E.__file__, encoding="utf-8").read()
    assert "proxies" not in src and "cache/proxies" not in src
    before = E.build(film, "preview")["path"]
    want = [index_at(before, k, tmp_path) for k in (0, 47, 48, 60, 95, 96, 140)]
    P.build(film)
    after = E.build(film, "preview")["path"]
    assert [index_at(after, k, tmp_path) for k in (0, 47, 48, 60, 95, 96, 140)] == want


def test_clearing_removes_only_the_copies(film):
    P.build(film)
    keep = os.path.join(film, "cache", "proxies", "notes.txt")
    open(keep, "w").write("mine")
    out = P.clear(film)
    assert out["removed"] == 1 and out["ready"] == 0 and os.path.isfile(keep)
    assert all(os.path.isfile(os.path.join(film, r["output"])) for r in out["rows"])             # the takes are still there


def test_a_missing_take_and_a_bad_action_are_refused_and_the_door_speaks_json(film, capsys):
    with pytest.raises(SystemExit, match="not there"):
        P.make(film, "takes/nothing.mp4")
    with pytest.raises(SystemExit, match="Unknown"):
        P.run(film, "explode", {})
    assert P.main(["status", film]) == 0 and json.loads(capsys.readouterr().out.splitlines()[-1])["data"]["big"] == 1
    src = open(P.__file__, encoding="utf-8").read()
    for a in P.ACTIONS:
        assert f'"{a}"' in src.split("choices=")[1].split("]")[0]


# ---------------------------------------------------------------- a damaged edit record

def test_a_damaged_edit_record_is_put_back_from_its_backup_and_the_person_is_told(film):
    ED.run(film, "edit", {"op": "split", "at": 1.0})
    ED.run(film, "edit", {"op": "marker_set", "at": 2.0, "name": "keep"})                          # two changes, so there is a backup of the first
    path = G._path(film)
    assert os.path.isfile(path + ".bak")
    open(path, "w").write("{ this is not json")
    got = ED.get(film)
    assert got["stored"] is True and any("restored from its backup" in n for n in got["notes"])
    assert len(got["sequence"]["tracks"][0]["clips"]) == 4                                          # the cut came back (the split is in it)
    assert any(f.startswith("edit.json.corrupt-") for f in os.listdir(os.path.dirname(path)))       # and the damaged bytes are kept


def test_a_damaged_record_with_no_backup_stops_everything_instead_of_reading_as_never_edited(film):
    ED.run(film, "edit", {"op": "split", "at": 1.0})                                                # one change: no backup yet
    path = G._path(film)
    for f in (path + ".bak",):
        if os.path.exists(f):
            os.remove(f)
    open(path, "w").write("{ this is not json")
    for call in (lambda: ED.get(film), lambda: G.state(film), lambda: E.build(film, "preview"), lambda: ED.run(film, "edit", {"op": "split", "at": 3.0}), lambda: G.set_grade(film, "film", None, {"exposure": 0.2})):
        with pytest.raises(SystemExit, match="damaged"):
            call()
    assert open(path).read() == "{ this is not json"                                                # nothing was written over it
