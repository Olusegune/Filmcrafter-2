import json
import os
import zipfile

import pytest

from filmcrafter_engine import packer


def _proj(tmp_path):
    d = tmp_path / "Song"
    (d / "generations").mkdir(parents=True)
    (d / "cache").mkdir()
    (d / "project.json").write_text(json.dumps({"title": "My Song"}))
    (d / "generations" / "a.mp4").write_bytes(b"\x00" * 5000)
    (d / "cache" / "big.bin").write_bytes(b"x" * 100)
    (d / "jobs.json.lock").write_text("")
    return str(d)


def test_pack_and_unpack_round_trip_without_caches(tmp_path):
    d = _proj(tmp_path)
    r = packer.pack(d, str(tmp_path / "out"))
    assert r["path"].endswith("out.filmpack") and r["files"] == 2
    root = tmp_path / "projects"
    root.mkdir()
    u = packer.unpack(r["path"], str(root))
    assert os.path.basename(u["dir"]) == "My Song"
    assert open(os.path.join(u["dir"], "generations", "a.mp4"), "rb").read() == b"\x00" * 5000
    assert not os.path.exists(os.path.join(u["dir"], "cache"))
    second = packer.unpack(r["path"], str(root))
    assert os.path.basename(second["dir"]) == "My Song (2)" and second["title"] == "My Song (2)"   # never overwrites
    assert json.load(open(os.path.join(second["dir"], "project.json")))["title"] == "My Song (2)"


def test_rejects_unsafe_and_foreign_files(tmp_path):
    bad = tmp_path / "bad.pulse"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("pulse.json", json.dumps({"format": 1, "title": "X"}))
        z.writestr("project/project.json", "{}")
        z.writestr("project/../../evil.txt", "x")
    with pytest.raises(SystemExit, match="unsafe"):
        packer.unpack(str(bad), str(tmp_path))
    (tmp_path / "notzip.pulse").write_text("hello")
    with pytest.raises(SystemExit):
        packer.unpack(str(tmp_path / "notzip.pulse"), str(tmp_path))
    newer = tmp_path / "new.pulse"
    with zipfile.ZipFile(newer, "w") as z:
        z.writestr("pulse.json", json.dumps({"format": 99}))
    with pytest.raises(SystemExit, match="newer"):
        packer.unpack(str(newer), str(tmp_path))


def test_backups_snapshot_skip_unchanged_restore_and_undo(tmp_path):
    from filmcrafter_engine import packer as P
    d = tmp_path / "proj"
    (d / "generations").mkdir(parents=True)
    (d / "project.json").write_text('{"title": "A"}')
    (d / "generations" / "take.mp4").write_bytes(b"x" * 10)
    first = P.backup(str(d))
    assert first["made"] and P.backup(str(d))["made"] is False        # nothing changed: no new snapshot
    (d / "project.json").write_text('{"title": "B"}')
    assert P.backup(str(d), "saved")["made"]
    old = P.backups(str(d))[-1]["name"]
    r = P.restore(str(d), old)
    assert (d / "project.json").read_text() == '{"title": "A"}'
    assert (d / "generations" / "take.mp4").exists()                  # media untouched
    P.restore(str(d), r["undo"])                                      # the restore itself can be undone
    assert (d / "project.json").read_text() == '{"title": "B"}'
    with __import__("pytest").raises(SystemExit):
        P.restore(str(d), "../../evil.zip")


def test_backups_keep_the_newest_20_and_stay_out_of_pulse_files(tmp_path):
    from filmcrafter_engine import packer as P
    d = tmp_path / "proj"
    d.mkdir()
    for i in range(23):
        (d / "project.json").write_text('{"title": "%d"}' % i)
        P.backup(str(d))
    assert len(P.backups(str(d))) == 20
    out = P.pack(str(d), str(tmp_path / "x.pulse"))
    import zipfile
    assert not any("backups/" in n for n in zipfile.ZipFile(out["path"]).namelist())
