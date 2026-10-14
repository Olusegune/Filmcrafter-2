"""Before an update: films' records and the app's settings are copied, nothing is touched or deleted, one bad film does not stop the others, and no key is ever copied."""
import json
import os

import pytest

from filmcrafter_engine import bible, filmbackup, preupdate as U, story

SCRIPT = "INT. KITCHEN - NIGHT\n\nSarah pours tea.\n\nSARAH\nHe said he'd call.\n"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv(U.ENV, str(tmp_path / "home"))
    return tmp_path / "home"


def film(tmp_path, name):
    d = story.create(str(tmp_path / "films"), name, "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    return d


def test_each_films_records_are_snapshotted_with_the_version_and_the_films_are_not_changed(tmp_path, home):
    a, b = film(tmp_path, "One"), film(tmp_path, "Two")
    before = open(os.path.join(a, "film.json"), "rb").read()
    r = U.snapshot("0.25.0", [a, b])
    assert [x["ok"] for x in r["films"]] == [True, True] and all(x["made"] for x in r["films"]) and r["summary"].startswith("2 of 2 films")
    assert filmbackup.list_backups(a)[0]["reason"] == "before update 0.25.0"
    assert open(os.path.join(a, "film.json"), "rb").read() == before and len(filmbackup.list_backups(a)) == 1
    again = U.snapshot("0.25.0", [a, b])
    assert [x["made"] for x in again["films"]] == [False, False] and len(filmbackup.list_backups(a)) == 1             # nothing changed: nothing piled up


def test_a_damaged_or_missing_film_is_reported_and_the_others_still_get_theirs(tmp_path, home):
    good, bad = film(tmp_path, "Good"), film(tmp_path, "Bad")
    open(os.path.join(bad, "film.json"), "wb").write(b'{"story": {')
    notfilm = tmp_path / "plain"
    notfilm.mkdir()
    r = U.snapshot("0.25.0", [bad, str(notfilm), str(tmp_path / "gone"), good])
    by = {x["film"]: x for x in r["films"]}
    assert by["Good"]["ok"] is True and by["plain"]["ok"] is False and by["gone"]["ok"] is False and by["Bad"]["ok"] is False
    assert open(os.path.join(bad, "film.json"), "rb").read() == b'{"story": {'                                        # the damaged file was not changed


def test_settings_are_copied_never_over_an_earlier_copy_and_nothing_that_could_hold_a_key_is(tmp_path, home):
    s1 = tmp_path / "recent.json"
    s1.write_text('["C:/films/One"]')
    big = tmp_path / "big.json"
    big.write_bytes(b"x" * (6 * 1024 * 1024))
    other = tmp_path / "secret.txt"
    other.write_text("sk_not_a_real_key")
    r = U.snapshot("0.25.0", [], [str(s1), str(big), str(other), str(tmp_path / "missing.json")])
    assert r["settings"] == ["recent.json"] and os.path.isfile(os.path.join(r["settings_folder"], "recent.json"))
    assert r["summary"].startswith("0 of 0 films") and "1 settings file copied" in r["summary"]
    s1.write_text('["C:/films/Two"]')
    r2 = U.snapshot("0.25.0", [], [str(s1)])
    assert len(os.listdir(r2["settings_folder"])) == 2 and json.load(open(os.path.join(r2["settings_folder"], "recent.json"))) == ["C:/films/One"]    # the first copy is still the first


def test_the_version_is_made_safe_for_a_folder_name_and_the_command_line_speaks_the_engine_format(tmp_path, home, capsys):
    r = U.snapshot("../../evil 1.0", [], [])
    assert "evil" in r["version"] and ".." not in r["version"] and "/" not in r["version"] and "\\" not in r["version"]
    assert U.main(["snapshot", "--data", json.dumps({"version": "1.2.3", "films": []})]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["version"] == "1.2.3"
    with pytest.raises(SystemExit):
        U.main(["format_disk"])
