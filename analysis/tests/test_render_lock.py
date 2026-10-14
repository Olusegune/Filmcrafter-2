"""The render job store's lock holds up under many processes at once (on Windows a lock file being deleted at that instant used to refuse re-creation with 'permission denied')."""
import json
import multiprocessing as mp
import os

from filmcrafter_engine import render


def _count(args):
    path, n = args
    for _ in range(n):
        with render._FileLock(path):
            cur = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {"n": 0}
            cur["n"] += 1
            json.dump(cur, open(path, "w", encoding="utf-8"))
    return True


def test_six_processes_taking_the_job_lock_together_lose_nothing_and_never_fail(tmp_path):
    path = str(tmp_path / "jobs.json")
    with mp.get_context("spawn").Pool(6) as pool:
        assert all(pool.map(_count, [(path, 25)] * 6))
    assert json.load(open(path, encoding="utf-8"))["n"] == 150
