"""The film's sound and music libraries (Stage A): import, describe, link, approve and remove audio without any provider, never deleting a file, never changing a stable id."""
import json
import os
import zipfile

import numpy as np
import pytest
import soundfile as sf

from filmcrafter_engine import audiolib as A, bible, filmbackup, packer, story

SCRIPT = "INT. YARD - DAY\n\nA schoolyard.\n\nLILA\nIt looked weird.\n\nCHLOE\nI know.\n"


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "Night Market", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    return d


def audio(tmp_path, name="rain.wav", secs=1.0, hz=220):
    p = tmp_path / "src" / name
    p.parent.mkdir(exist_ok=True)
    t = np.arange(int(22050 * secs)) / 22050
    sf.write(str(p), (0.3 * np.sin(2 * np.pi * hz * t)).astype("float32"), 22050)
    return str(p)


def lib(d):
    return json.load(open(os.path.join(d, "audio", "library.json"), encoding="utf-8"))


# ---------------------------------------------------------------- importing

def test_an_imported_sound_is_copied_into_the_film_with_a_stable_id_and_the_original_is_untouched(film, tmp_path):
    src = audio(tmp_path, "Rain_on_roof.wav", 1.5)
    before = open(src, "rb").read()
    r = A.import_files(film, "sfx", [src], "weather")
    a = r["assets"][0]
    assert r["added"] == [a["id"]] and a["id"].startswith("a-sfx-") and a["kind"] == "sfx" and a["category"] == "weather"
    assert a["name"] == "Rain on roof" and abs(a["seconds"] - 1.5) < 0.1 and a["source"] == "imported" and a["approval"] == "pending"
    assert a["licence"]["commercial"] == "unknown" and a["generation"] == {}
    assert os.path.isfile(os.path.join(film, *a["file"].split("/"))) and a["file"].startswith("audio/sfx/")
    assert open(src, "rb").read() == before and os.path.isfile(src)


def test_the_same_file_twice_is_not_added_twice_but_can_be_in_both_libraries(film, tmp_path):
    src = audio(tmp_path)
    first = A.import_files(film, "sfx", [src])
    again = A.import_files(film, "sfx", [src])
    assert len(again["assets"]) == 1 and again["added"] == [] and "Already in the library" in again["skipped"][0]["why"]
    assert again["skipped"][0]["id"] == first["added"][0]
    both = A.import_files(film, "music", [src])
    assert both["counts"] == {"sfx": 1, "music": 1}


def test_what_is_not_real_audio_is_refused_by_content_not_by_name(film, tmp_path):
    fake = tmp_path / "src" / "pretend.wav"
    fake.parent.mkdir(exist_ok=True)
    fake.write_bytes(b"MZ" + b"\0" * 5000)                                  # a program with a .wav name
    text = tmp_path / "src" / "notes.txt"
    text.write_text("hello" * 100)
    empty = tmp_path / "src" / "empty.wav"
    empty.write_bytes(b"")
    r = A.import_files(film, "music", [str(fake), str(text), str(empty), str(tmp_path / "nope.wav")])
    assert r["added"] == [] and len(r["skipped"]) == 4 and r["assets"] == []
    assert not os.path.exists(os.path.join(film, "audio", "library.json")) or lib(film)["assets"] == []


def test_a_huge_file_and_a_wrong_kind_are_refused(film, tmp_path, monkeypatch):
    src = audio(tmp_path)
    monkeypatch.setattr(A, "MAX_BYTES", 100)
    assert "larger than 200 MB" in A.import_files(film, "sfx", [src])["skipped"][0]["why"]
    monkeypatch.undo()
    with pytest.raises(SystemExit, match="sound effects or music"):
        A.import_files(film, "dialogue", [src])
    with pytest.raises(SystemExit, match="at least one"):
        A.import_files(film, "sfx", [])
    with pytest.raises(SystemExit, match="isn't a FilmCrafter film"):
        A.import_files(str(tmp_path), "sfx", [src])


# ---------------------------------------------------------------- describing, linking, approving

def test_describe_link_and_approve_never_change_the_id_or_the_file(film, tmp_path):
    a = A.import_files(film, "music", [audio(tmp_path, "theme.wav")], "theme")["assets"][0]
    r = A.update(film, a["id"], {"name": "Lila theme", "description": "A music box", "category": "theme", "genre": "chamber", "mood": "tender", "tempo": "72 bpm",
                                 "characters": ["Lila", "lila", " Chloe "], "places": "Yard, Kitchen", "scenes": [1, 2], "tags": ["theme"],
                                 "licence": {"source": "my own", "note": "composed by me", "commercial": "yes"}})
    b = r["assets"][0]
    assert b["id"] == a["id"] and b["file"] == a["file"] and b["sha1"] == a["sha1"]
    assert b["name"] == "Lila theme" and b["characters"] == ["Lila", "Chloe"] and b["places"] == ["Yard", "Kitchen"] and b["scenes"] == ["1", "2"]
    assert b["licence"] == {"source": "my own", "note": "composed by me", "commercial": "yes"}
    assert A.approve(film, a["id"], "approved")["assets"][0]["approval"] == "approved"
    assert A.update(film, a["id"], {"name": "Renamed"})["assets"][0]["approval"] == "approved"       # editing a description does not undo the person's decision
    assert A.approve(film, a["id"], "rejected")["assets"][0]["approval"] == "rejected"
    for bad in ({"category": "weather"}, {"name": ""}, {"licence": {"commercial": "maybe"}}):
        with pytest.raises(SystemExit):
            A.update(film, a["id"], bad)
    with pytest.raises(SystemExit):
        A.approve(film, a["id"], "great")
    for bad_id in ("../x", "a-sfx-zzzz", "", "a-music-00000000"):
        with pytest.raises(SystemExit):
            A.approve(film, bad_id, "approved")


def test_removing_moves_the_file_aside_and_it_can_be_restored(film, tmp_path):
    a = A.import_files(film, "sfx", [audio(tmp_path)])["assets"][0]
    path = os.path.join(film, *a["file"].split("/"))
    r = A.remove(film, a["id"])
    assert r["assets"] == [] and r["removed"] == 1 and not os.path.exists(path)
    assert len(os.listdir(os.path.join(film, "audio", "_removed"))) == 1   # the file is kept
    back = A.restore(film, a["id"])
    assert back["assets"][0]["id"] == a["id"] and os.path.isfile(path) and os.listdir(os.path.join(film, "audio", "_removed")) == []
    with pytest.raises(SystemExit):
        A.restore(film, a["id"])


def test_a_new_id_is_never_a_removed_id(film, tmp_path):
    a = A.import_files(film, "sfx", [audio(tmp_path)])["assets"][0]
    A.remove(film, a["id"])
    b = A.import_files(film, "sfx", [audio(tmp_path, "other.wav", 2.0, 440)])["assets"][0]
    assert b["id"] != a["id"]


# ---------------------------------------------------------------- safety and compatibility

def test_a_damaged_library_is_kept_and_never_replaced_by_an_empty_one(film, tmp_path):
    A.import_files(film, "sfx", [audio(tmp_path)])
    p = os.path.join(film, "audio", "library.json")
    if os.path.exists(p + ".bak"):
        os.remove(p + ".bak")
    open(p, "wb").write(b'{"assets": [{"id"')
    with pytest.raises(SystemExit, match="damaged"):
        A.import_files(film, "sfx", [audio(tmp_path, "b.wav", 2.0, 330)])
    assert open(p, "rb").read() == b'{"assets": [{"id"'                    # untouched
    assert any(f.startswith("library.json.corrupt-") for f in os.listdir(os.path.dirname(p)))


def test_a_film_with_no_audio_opens_as_before_and_gets_no_files_until_used(film):
    r = A.list_assets(film)
    assert r["assets"] == [] and r["counts"] == {"sfx": 0, "music": 0}
    assert not os.path.exists(os.path.join(film, "audio"))


def test_the_library_travels_in_a_backup_and_a_filmpack_and_ids_survive(film, tmp_path):
    a = A.import_files(film, "music", [audio(tmp_path, "t.wav")])["assets"][0]
    filmbackup.make(film)
    bk = filmbackup.list_backups(film)[0]["name"]
    with zipfile.ZipFile(os.path.join(film, "backups", bk)) as z:
        names = z.namelist()
    assert "files/audio/library.json" in names
    out = packer.pack(film, str(tmp_path / "pack"))
    root = tmp_path / "root"
    root.mkdir()
    d2 = packer.unpack(out["path"], str(root))["dir"]
    b = A.list_assets(d2)["assets"][0]
    assert b["id"] == a["id"] and b["exists"]
    os.remove(os.path.join(film, "audio", "library.json"))                  # lose it, then restore the snapshot
    filmbackup.restore(film, bk)
    assert A.list_assets(film)["assets"][0]["id"] == a["id"]


def test_two_imports_at_once_keep_both(film, tmp_path):
    import multiprocessing as mp
    s1, s2 = audio(tmp_path, "a.wav", 1.0, 220), audio(tmp_path, "b.wav", 1.0, 440)
    ctx = mp.get_context("spawn")
    ps = [ctx.Process(target=_import_in_process, args=(film, s)) for s in (s1, s2)]
    [p.start() for p in ps]
    [p.join(120) for p in ps]
    assert len(A.list_assets(film)["assets"]) == 2


def _import_in_process(film, src):
    from filmcrafter_engine import audiolib
    audiolib.import_files(film, "sfx", [src])


def test_the_command_line_speaks_the_engine_format_and_refuses_unknown_actions(film, capsys):
    assert A.main(["list", film]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["assets"] == []
    with pytest.raises(SystemExit):
        A.main(["delete_everything", film])
    assert A.main(["approve", film, "--data", json.dumps({"id": "a-sfx-00000000", "state": "approved"})]) == 1
    assert "not in this film's library" in capsys.readouterr().out
