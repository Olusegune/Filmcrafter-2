import os

import pytest

import filmcrafter_engine as P


def test_a_save_survives_a_file_that_is_briefly_locked(tmp_path, monkeypatch):
    calls, real = {"n": 0}, P._replace

    def flaky(src, dst, *a, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(32, "in use")
        return real(src, dst)
    monkeypatch.setattr(P, "_replace", flaky)
    monkeypatch.setattr(P._time, "sleep", lambda s: None)
    (tmp_path / "a.tmp").write_text("x")
    P._replace_with_retry(str(tmp_path / "a.tmp"), str(tmp_path / "a"))
    assert calls["n"] == 3 and (tmp_path / "a").read_text() == "x"


def test_a_file_that_stays_locked_still_reports_the_error(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_replace", lambda *a, **k: (_ for _ in ()).throw(PermissionError(32, "in use")))
    monkeypatch.setattr(P._time, "sleep", lambda s: None)
    with pytest.raises(PermissionError):
        P._replace_with_retry("a", "b")
