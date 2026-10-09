"""What the render loop records for the Render queue, and cancelling a render that has not been sent."""
import pytest

from pulseframe_analysis import render as R


@pytest.mark.parametrize("res,detail,progress", [
    ({"detail": "in queue", "progress": 0.4}, "in queue", 0.4),
    ({"detail": "rendering", "progress": 40}, "rendering", 0.4),       # some providers say percent
    ({"progress": 100}, None, 1.0),
    ({"progress": 250}, None, 1.0),                                      # never above 1
    ({"progress": -3}, None, None),
    ({"progress": True}, None, None),
    ({"progress": "half"}, None, None),
    ({}, None, None),
    ({"detail": "x" * 200}, "x" * 80, None),
])
def test_live_progress_is_normalised(res, detail, progress):
    assert R.live_progress(res) == {"detail": detail, "progress": progress}


class FakeStore:
    def __init__(self, jobs):
        self.jobs, self.updates = jobs, []

    def update(self, j, **kw):
        j.update(kw)
        self.updates.append(kw)


class Prov:
    def __init__(self, res):
        self.res = res

    def poll(self, *a, **k):
        return self.res


def job(**kw):
    return {"id": "j1", "shot_id": "S01-01", "model": "m", "provider_job_id": "p", "state": "submitted", **kw}


def test_a_changed_progress_is_saved_on_the_job_and_an_unchanged_one_is_not():
    j = job()
    s = FakeStore([j])
    R._check("d", s, Prov({"state": "running", "detail": "in queue", "progress": 0.2}), j)
    assert s.updates == [{"detail": "in queue", "progress": 0.2}]
    R._check("d", s, Prov({"state": "running", "detail": "in queue", "progress": 0.2}), j)
    assert len(s.updates) == 1                                           # the same reading is not written again
    R._check("d", s, Prov({"state": "running", "detail": "in queue", "progress": 0.5}), j)
    assert s.updates[-1]["progress"] == 0.5


def test_cancel_only_works_before_anything_is_sent(tmp_path, monkeypatch):
    jobs = {"q": {"id": "q", "state": "queued"}, "s": {"id": "s", "state": "submitted"}, "r": {"id": "r", "state": "ready"}}

    class St(FakeStore):
        def __init__(self, d):
            super().__init__(list(jobs.values()))
    monkeypatch.setattr(R, "Store", St)
    assert R.resolve(str(tmp_path), "q", "cancel")["state"] == "dismissed"
    assert "Cancelled" in jobs["q"]["error"]
    for jid in ("s", "r"):
        with pytest.raises(SystemExit) as e:
            R.resolve(str(tmp_path), jid, "cancel")
        assert "Can't cancel" in str(e.value)
