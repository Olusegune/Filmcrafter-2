"""A damaged shot or production record is reported with its bytes kept, never mistaken for a missing one and replaced (Phase 1: the safe record layer reaches shots, make and continuity)."""
import os

import pytest

from filmcrafter_engine import bible, make, shots as S, story

SCRIPT = "INT. KITCHEN - NIGHT\n\nSarah pours tea.\n\nSARAH\nHe said he'd call.\n"


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    S.breakdown(d)
    return d


def test_a_damaged_shot_contract_is_reported_and_left_exactly_as_it_is(film):
    sid = S.view(film)["shots"][0]["id"]
    p = S._cpath(film, sid)
    if os.path.exists(p + ".bak"):
        os.remove(p + ".bak")
    open(p, "wb").write(b'{"id": "S01-01", "scene"')
    with pytest.raises(SystemExit, match="damaged"):
        S.set_fields(film, sid, {"title": "New title"})
    assert open(p, "rb").read() == b'{"id": "S01-01", "scene"'
    assert any(f.startswith("contract.json.corrupt-") for f in os.listdir(os.path.dirname(p)))


def test_a_good_backup_of_a_shot_is_used_when_the_record_is_damaged(film):
    sid = S.view(film)["shots"][0]["id"]
    S.set_fields(film, sid, {"title": "One"})
    S.set_fields(film, sid, {"title": "Two"})                       # the first title is now the known-good .bak
    p = S._cpath(film, sid)
    open(p, "wb").write(b"{broken")
    assert S._contract(film, sid)["title"] == "One"


def test_saving_records_does_not_leave_temporary_files_or_locks_behind(film):
    sid = S.view(film)["shots"][0]["id"]
    S.set_fields(film, sid, {"title": "Quiet"})
    left = [f for f in os.listdir(os.path.dirname(S._cpath(film, sid))) if f.endswith((".tmp", ".lock"))]
    assert left == []
