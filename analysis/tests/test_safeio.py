"""safeio: a damaged file is never silently turned into an empty one; writes are atomic and never replace a good backup with a bad file; concurrent updates do not lose records."""
import json
import multiprocessing as mp
import os

import pytest

from filmcrafter_engine import safeio


def corrupt_copies(folder, name):
    return sorted(f for f in os.listdir(folder) if f.startswith(name + ".corrupt-"))


def write_raw(path, data: bytes):
    with open(path, "wb") as f:
        f.write(data)


# ---------------------------------------------------------------- reading: the cases are kept apart

def test_an_absent_file_gives_the_default_and_creates_nothing(tmp_path):
    p = str(tmp_path / "voice.json")
    assert safeio.read_json(p, {"shots": {}}) == {"shots": {}}
    assert os.listdir(tmp_path) == []
    assert safeio.inspect_json(p) == "absent"


def test_valid_empty_data_is_data_not_damage(tmp_path):
    p = str(tmp_path / "a.json")
    for text, want in (("{}", {}), ("[]", []), ("null", None), ("0", 0)):
        write_raw(p, text.encode())
        assert safeio.read_json(p, "DEFAULT") == want and safeio.inspect_json(p) == "ok"
    assert corrupt_copies(tmp_path, "a.json") == []


@pytest.mark.parametrize("bad", [b"", b"{", b'{"shots": {"S01-01": [', b"\xff\xfe\x00garbage", b"not json at all", b'{"a": 1}}'])
def test_damage_is_not_silently_an_empty_file(tmp_path, bad):
    p = str(tmp_path / "voice.json")
    write_raw(p, bad)
    with pytest.raises(safeio.SafeIOError) as e:
        safeio.read_json(p, {"shots": {}})
    assert e.value.kind == "corrupt" and "damaged" in str(e.value) and "voice.json.corrupt-" in str(e.value)
    assert open(p, "rb").read() == bad                                        # the file is exactly where it was
    kept = corrupt_copies(tmp_path, "voice.json")
    assert len(kept) == 1 and open(tmp_path / kept[0], "rb").read() == bad    # and its bytes are kept
    with pytest.raises(safeio.SafeIOError):                                   # reading again does not pile up copies
        safeio.read_json(p, {})
    assert len(corrupt_copies(tmp_path, "voice.json")) == 1


def test_a_damaged_file_is_restored_from_a_valid_backup_and_the_original_bytes_survive(tmp_path):
    p = str(tmp_path / "cast.json")
    safeio.write_json(p, {"people": {"lila": {"voice_id": "A"}}})
    safeio.write_json(p, {"people": {"lila": {"voice_id": "B"}}})            # now .bak holds the first version
    assert json.load(open(p + ".bak", encoding="utf-8"))["people"]["lila"]["voice_id"] == "A"
    write_raw(p, b'{"people": {"lila": {"voice')                              # a half-written file
    notes = []
    got = safeio.read_json(p, {}, notes=notes)
    assert got["people"]["lila"]["voice_id"] == "A"                          # the verified backup is used
    assert notes and "restored from its backup" in notes[0]
    assert json.load(open(p, encoding="utf-8")) == got                       # the file is whole again
    kept = corrupt_copies(tmp_path, "cast.json")
    assert open(tmp_path / kept[0], "rb").read() == b'{"people": {"lila": {"voice'      # the damaged bytes are kept
    assert json.load(open(p + ".bak", encoding="utf-8"))["people"]["lila"]["voice_id"] == "A"   # the backup was not touched


def test_a_damaged_backup_is_not_trusted(tmp_path):
    p = str(tmp_path / "x.json")
    write_raw(p, b"{bad")
    write_raw(p + ".bak", b"{also bad")
    with pytest.raises(safeio.SafeIOError) as e:
        safeio.read_json(p, {})
    assert e.value.kind == "corrupt"
    assert open(p, "rb").read() == b"{bad" and open(p + ".bak", "rb").read() == b"{also bad"


def test_a_backup_of_the_wrong_shape_is_not_used_either(tmp_path):
    p = str(tmp_path / "voice.json")
    write_raw(p, b"{bad")
    write_raw(p + ".bak", b'["a list, not a voice record"]')
    with pytest.raises(safeio.SafeIOError):
        safeio.read_json(p, {}, check=lambda d: isinstance(d, dict))


def test_valid_json_of_the_wrong_shape_is_refused_and_left_alone(tmp_path):
    p = str(tmp_path / "voice.json")
    write_raw(p, b'["not", "a", "voice", "record"]')
    with pytest.raises(safeio.SafeIOError) as e:
        safeio.read_json(p, {}, check=lambda d: isinstance(d, dict))
    assert e.value.kind == "unsupported" and corrupt_copies(tmp_path, "voice.json") == []        # nothing is quarantined: it is not damaged
    assert open(p, "rb").read() == b'["not", "a", "voice", "record"]'


def test_an_unreadable_file_is_reported_and_nothing_is_changed(tmp_path, monkeypatch):
    p = str(tmp_path / "a.json")
    write_raw(p, b"{}")
    real = open

    def deny(path, mode="r", *a, **k):
        if str(path) == p and "b" in mode and "w" not in mode:
            raise PermissionError(13, "Permission denied")
        return real(path, mode, *a, **k)

    monkeypatch.setattr("builtins.open", deny)
    with pytest.raises(safeio.SafeIOError) as e:
        safeio.read_json(p, {})
    monkeypatch.undo()
    assert e.value.kind == "unreadable" and "can't be read" in str(e.value)
    assert open(p, "rb").read() == b"{}" and corrupt_copies(tmp_path, "a.json") == []


def test_two_different_damaged_versions_get_two_copies_and_names_never_collide(tmp_path):
    p = str(tmp_path / "f.json")
    write_raw(p, b"{one")
    with pytest.raises(safeio.SafeIOError):
        safeio.read_json(p, {})
    write_raw(p, b"{two")
    with pytest.raises(safeio.SafeIOError):
        safeio.read_json(p, {})
    kept = corrupt_copies(tmp_path, "f.json")
    assert len(kept) == 2 and {open(tmp_path / k, "rb").read() for k in kept} == {b"{one", b"{two"}


# ---------------------------------------------------------------- writing

def test_a_save_keeps_the_previous_valid_version_as_the_backup(tmp_path):
    p = str(tmp_path / "v.json")
    safeio.write_json(p, {"n": 1})
    assert not os.path.exists(p + ".bak")                                     # nothing to back up the first time
    safeio.write_json(p, {"n": 2})
    safeio.write_json(p, {"n": 3})
    assert json.load(open(p, encoding="utf-8")) == {"n": 3} and json.load(open(p + ".bak", encoding="utf-8")) == {"n": 2}
    assert [f for f in os.listdir(tmp_path) if f.endswith((".tmp", ".lock"))] == []            # nothing left behind


def test_saving_the_same_data_again_changes_nothing(tmp_path):
    p = str(tmp_path / "v.json")
    safeio.write_json(p, {"n": 1})
    safeio.write_json(p, {"n": 2})
    safeio.write_json(p, {"n": 2})
    assert json.load(open(p + ".bak", encoding="utf-8")) == {"n": 1}          # the repeat did not push the backup forward


def test_a_good_backup_is_never_replaced_by_a_damaged_file(tmp_path):
    p = str(tmp_path / "v.json")
    safeio.write_json(p, {"n": 1})
    safeio.write_json(p, {"n": 2})                                            # .bak = n:1
    write_raw(p, b"{broken")                                                  # something damages the file, and a caller saves anyway
    safeio.write_json(p, {"n": 3})
    assert json.load(open(p + ".bak", encoding="utf-8")) == {"n": 1}          # the known-good backup survived
    kept = corrupt_copies(tmp_path, "v.json")
    assert len(kept) == 1 and open(tmp_path / kept[0], "rb").read() == b"{broken"   # and the damaged bytes were kept before being replaced


def test_data_that_cannot_be_saved_touches_nothing(tmp_path):
    p = str(tmp_path / "v.json")
    safeio.write_json(p, {"n": 1})
    before = open(p, "rb").read()
    with pytest.raises(TypeError):
        safeio.write_json(p, {"n": object()})
    assert open(p, "rb").read() == before and not os.path.exists(p + ".bak")
    assert [f for f in os.listdir(tmp_path) if f.endswith((".tmp", ".lock"))] == []


def test_an_interrupted_write_leaves_the_old_file_whole_and_no_litter(tmp_path, monkeypatch):
    p = str(tmp_path / "v.json")
    safeio.write_json(p, {"n": 1, "keep": "me"})
    real = os.replace

    def fail_the_swap(src, dst):
        if dst == p:
            raise OSError("the disk went away")
        return real(src, dst)

    monkeypatch.setattr(os, "replace", fail_the_swap)
    with pytest.raises(OSError):
        safeio.write_json(p, {"n": 2})
    monkeypatch.undo()
    assert json.load(open(p, encoding="utf-8")) == {"n": 1, "keep": "me"}     # unrelated metadata was not erased
    assert [f for f in os.listdir(tmp_path) if f.endswith((".tmp", ".lock"))] == []


def test_a_busy_replace_on_windows_is_retried(tmp_path, monkeypatch):
    p = str(tmp_path / "v.json")
    real, calls = os.replace, {"n": 0}

    def flaky(src, dst):
        if dst == p and calls["n"] < 3:
            calls["n"] += 1
            raise PermissionError(5, "in use")
        return real(src, dst)

    monkeypatch.setattr(os, "replace", flaky)
    safeio.write_json(p, {"ok": True})
    monkeypatch.undo()
    assert calls["n"] == 3 and json.load(open(p, encoding="utf-8")) == {"ok": True}


def test_text_survives_exactly(tmp_path):
    p = str(tmp_path / "t.json")
    data = {"line": "Où est-il ? — « Je l'sais. » 你好 🎬", "n": [1, 2.5, None, True]}
    safeio.write_json(p, data)
    assert safeio.read_json(p) == data


# ---------------------------------------------------------------- locking and concurrent updates

def _bump(args):
    path, who, times = args
    for i in range(times):
        def add(d):
            d["records"].append(f"{who}-{i}")
        safeio.update_json(path, add, {"records": []})
    return who


def test_concurrent_updates_from_several_processes_lose_nothing(tmp_path):
    p = str(tmp_path / "ledger.json")
    jobs = [(p, f"p{n}", 20) for n in range(4)]
    with mp.get_context("spawn").Pool(4) as pool:
        pool.map(_bump, jobs)
    got = safeio.read_json(p)["records"]
    assert len(got) == 80 and len(set(got)) == 80                             # every record from every process is there, once


def test_a_lock_left_by_a_dead_process_is_cleared_and_a_live_one_makes_others_wait(tmp_path):
    p = str(tmp_path / "v.json")
    write_raw(p + ".lock", b"99999")
    old = os.path.getmtime(p + ".lock") - 120
    os.utime(p + ".lock", (old, old))                                        # a lock from a long-dead process
    safeio.write_json(p, {"ok": 1})
    assert json.load(open(p, encoding="utf-8")) == {"ok": 1}
    write_raw(p + ".lock", b"1")                                              # a fresh lock: someone is saving right now
    with pytest.raises(safeio.SafeIOError) as e:
        with safeio.locked(p, timeout=0.2):
            pass
    assert e.value.kind == "busy"


def test_update_json_refuses_to_build_on_a_damaged_file(tmp_path):
    p = str(tmp_path / "ledger.json")
    write_raw(p, b'{"entries": [')
    with pytest.raises(safeio.SafeIOError):
        safeio.update_json(p, lambda d: d["entries"].append(1), {"entries": []})
    assert open(p, "rb").read() == b'{"entries": ['                           # not replaced by {"entries": [1]}
