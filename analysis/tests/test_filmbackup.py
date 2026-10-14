"""Film-level backups: the film's own records are snapshotted, verified before a restore, never deleted by a restore, and a damaged film.json is reported, not hidden."""
import json
import os
import zipfile

import pytest

from filmcrafter_engine import filmbackup, safeio, story


def film(tmp_path):
    d = tmp_path / "My Film"
    (d / "voice").mkdir(parents=True)
    (d / "script" / "versions").mkdir(parents=True)
    (d / "render").mkdir()
    (d / "shots_media").mkdir()
    j = lambda p, o: (d / p).write_text(json.dumps(o), encoding="utf-8")
    j("film.json", {"story": {"original": "v001"}, "title": "My Film"})
    j("voice/voice.json", {"shots": {"S01": {"file": "a.wav"}}})
    j("voice/cast.json", {"people": {"Lila": {"voice": "x"}}})
    j("voice/ledger.json", {"entries": [{"id": "1"}]})
    j("script/versions/v001.json", {"text": "INT. ROOM"})
    (d / "render" / "project.json").write_text("{}")
    (d / "shots_media" / "a.mp4").write_bytes(b"\0" * 100)
    (d / "voice" / "a.wav").write_bytes(b"RIFF")
    return str(d)


def names(d):
    with zipfile.ZipFile(os.path.join(d, "backups", filmbackup.list_backups(d)[0]["name"])) as z:
        return sorted(n[6:] for n in z.namelist() if n.startswith("files/"))


def test_a_snapshot_holds_the_records_and_not_the_media_or_the_render_project(tmp_path):
    d = film(tmp_path)
    r = filmbackup.make(d, "open")
    assert r["made"]
    assert names(d) == ["film.json", "script/versions/v001.json", "voice/cast.json", "voice/ledger.json", "voice/voice.json"]


def test_nothing_changed_means_no_new_snapshot_and_a_change_makes_one(tmp_path):
    d = film(tmp_path)
    assert filmbackup.make(d)["made"]
    assert not filmbackup.make(d)["made"]
    (tmp_path / "My Film" / "film.json").write_text(json.dumps({"story": {}, "title": "Renamed"}))
    assert filmbackup.make(d)["made"]
    assert len(filmbackup.list_backups(d)) == 2


def test_restore_puts_records_back_takes_an_undo_snapshot_and_deletes_nothing(tmp_path):
    d = film(tmp_path)
    filmbackup.make(d, "good")
    good = filmbackup.list_backups(d)[0]["name"]
    base = tmp_path / "My Film"
    (base / "film.json").write_text(json.dumps({"story": {}, "title": "Oops"}))
    (base / "voice" / "extra.json").write_text("{}")                  # made after the snapshot
    res = filmbackup.restore(d, good)
    assert json.loads((base / "film.json").read_text())["title"] == "My Film"
    assert (base / "voice" / "extra.json").exists()                    # not in the snapshot: not deleted
    assert (base / "voice" / "a.wav").exists() and (base / "shots_media" / "a.mp4").exists()
    assert res["undo"] and res["undo"] != good
    filmbackup.restore(d, res["undo"])                                 # the undo goes back to "Oops"
    assert json.loads((base / "film.json").read_text())["title"] == "Oops"


def test_the_voice_ledger_is_never_rolled_back(tmp_path):
    d = film(tmp_path)
    filmbackup.make(d)
    old = filmbackup.list_backups(d)[0]["name"]
    base = tmp_path / "My Film"
    (base / "voice" / "ledger.json").write_text(json.dumps({"entries": [{"id": "1"}, {"id": "2"}]}))
    res = filmbackup.restore(d, old)
    assert len(json.loads((base / "voice" / "ledger.json").read_text())["entries"]) == 2
    assert "voice/ledger.json" in res["kept_as_is"]


def test_a_damaged_snapshot_is_refused_and_changes_nothing(tmp_path):
    d = film(tmp_path)
    filmbackup.make(d)
    name = filmbackup.list_backups(d)[0]["name"]
    path = os.path.join(d, "backups", name)
    with zipfile.ZipFile(path) as z:
        items = {n: z.read(n) for n in z.namelist()}
    items["files/film.json"] = b'{"title": "tampered"}'
    with zipfile.ZipFile(path, "w") as z:
        for n, b in items.items():
            z.writestr(n, b)
    before = (tmp_path / "My Film" / "film.json").read_bytes()
    with pytest.raises(SystemExit, match="damaged"):
        filmbackup.restore(d, name)
    assert (tmp_path / "My Film" / "film.json").read_bytes() == before
    open(path, "wb").write(b"not a zip")
    with pytest.raises(SystemExit, match="can't be read"):
        filmbackup.restore(d, name)
    assert filmbackup.list_backups(d)[0].get("damaged")


def test_an_unsafe_path_inside_a_snapshot_is_refused(tmp_path):
    d = film(tmp_path)
    os.makedirs(os.path.join(d, "backups"))
    bad = os.path.join(d, "backups", "film-20250101-000000-000.zip")
    body = b"{}"
    import hashlib
    sha = hashlib.sha256(body).hexdigest()
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("backup.json", json.dumps({"files": {"../evil.json": {"sha256": sha}}}))
        z.writestr("files/../evil.json", body)
    with pytest.raises(SystemExit, match="unsafe"):
        filmbackup.restore(d, os.path.basename(bad))
    assert not (tmp_path / "evil.json").exists()


def test_only_the_newest_thirty_are_kept(tmp_path):
    d = film(tmp_path)
    for i in range(34):
        (tmp_path / "My Film" / "film.json").write_text(json.dumps({"story": {}, "n": i}))
        filmbackup.make(d)
    assert len(filmbackup.list_backups(d)) == filmbackup.KEEP


def test_not_a_film_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        filmbackup.make(str(tmp_path))


def test_a_damaged_film_json_is_reported_kept_and_recovered_from_its_bak_never_treated_as_new(tmp_path):
    d = film(tmp_path)
    p = os.path.join(d, "film.json")
    story._write(p, {"story": {"original": "v001"}, "title": "A"})
    story._write(p, {"story": {"original": "v001"}, "title": "B"})   # now there is a known-good .bak (A)
    open(p, "wb").write(b'{"story": {"orig')                           # cut off mid-write
    got = story._read(p)
    assert got["title"] == "A"                                         # recovered from the backup, not "isn't a film"
    assert any(f.startswith("film.json.corrupt-") for f in os.listdir(d))   # the damaged bytes are kept
    os.remove(p + ".bak")
    open(p, "wb").write(b"{broken")
    with pytest.raises(safeio.SafeIOError):
        story._read(p)
    assert open(p, "rb").read() == b"{broken"                          # left exactly as it was


def test_the_cli_reports_in_the_engine_event_format(tmp_path, capsys):
    d = film(tmp_path)
    assert filmbackup.main(["make", d, "cli"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["made"] is True
    assert filmbackup.main(["restore", d, "nope.zip"]) == 1
    assert "no longer exists" in capsys.readouterr().out
