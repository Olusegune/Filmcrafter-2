import json

from filmcrafter_engine import diagnostics as dg


def _proj(tmp_path, jobs):
    d = tmp_path / "Song"
    d.mkdir()
    (d / "jobs.json").write_text(json.dumps({"jobs": jobs}))
    return str(tmp_path)


def test_no_key_is_unavailable(tmp_path, monkeypatch):
    for v in dg.KEY_VARS.values():
        monkeypatch.delenv(v, raising=False)
    rows = {r["provider"]: r for r in dg.run(str(tmp_path))["providers"]}
    assert rows["fal"]["status"] == "unavailable" and rows["fal"]["recovery"] == dg.RECOVERY["no_key"]


def test_signed_in_without_real_render_is_unverified(tmp_path, monkeypatch):
    for v in dg.KEY_VARS.values():
        monkeypatch.setenv(v, "k")
    monkeypatch.setattr(dg, "_probe", lambda p, k: ("ok", "Signed in.", 200))
    root = _proj(tmp_path, [{"provider": "kie", "state": "ready", "shot_id": "S01-01", "model": "m", "updated": 5}])
    rows = {r["provider"]: r for r in dg.run(root)["providers"]}
    assert rows["kie"]["status"] == "verified"
    assert rows["openai"]["status"] == "unverified"


def test_history_classifies_last_failure(tmp_path):
    root = _proj(tmp_path, [
        {"provider": "fal", "state": "failed", "error": "Exhausted balance", "updated": 1},
        {"provider": "fal", "state": "failed", "error": "HTTP 401 unauthorized", "updated": 9},
    ])
    h = dg.history(root)["fal"]
    assert h["failed"] == 2 and h["last_fail"]["error_kind"] == "auth"
    assert "Keys" in h["last_fail"]["recovery"]


def test_credit_refusal_is_blocked_and_bad_key_unavailable(tmp_path, monkeypatch):
    for v in dg.KEY_VARS.values():
        monkeypatch.setenv(v, "k")
    monkeypatch.setattr(dg, "_probe", lambda p, k: ("error", "insufficient balance", 402) if p == "fal" else ("error", "invalid", 401))
    rows = {r["provider"]: r for r in dg.run(str(tmp_path))["providers"]}
    assert rows["fal"]["status"] == "blocked"
    assert rows["kie"]["status"] == "unavailable" and rows["kie"]["error_kind"] == "auth"


def test_output_never_contains_key(tmp_path, monkeypatch):
    for v in dg.KEY_VARS.values():
        monkeypatch.setenv(v, "sk-SECRET123")
    monkeypatch.setattr(dg, "_probe", lambda p, k: ("ok", "Signed in.", 200))
    assert "SECRET123" not in json.dumps(dg.run(str(tmp_path)))


def test_history_includes_recent_projects_elsewhere(tmp_path):
    other = tmp_path / "elsewhere" / "Song B"
    other.mkdir(parents=True)
    (other / "jobs.json").write_text(json.dumps({"jobs": [{"provider": "kie", "state": "ready", "updated": 3}]}))
    root = _proj(tmp_path, [])
    assert dg.history(root, [str(other), str(other)])["kie"]["ready"] == 1
