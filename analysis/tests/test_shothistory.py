"""Undo and redo for the changes made to a shot: what is recorded, what is put back, and that a damaged or hostile journal cannot do anything else."""
import json
import os
import subprocess

import pytest
from PIL import Image

from pulseframe_analysis import compose as CO, frames as FR, library as L, shothistory as H
from pulseframe_analysis.export import ffmpeg


def jread(d, name):
    p = os.path.join(d, name)
    return json.load(open(p)) if os.path.exists(p) else None


@pytest.fixture
def project(tmp_path):
    d = tmp_path / "p"
    (d / "media").mkdir(parents=True)
    (d / "generations").mkdir()
    shots = [{"id": f"S01-0{i}", "scene": 1, "number": i, "start": (i - 1) * 4.0, "end": i * 4.0, "beats": [f"beat {i}"], "performers": [], "framing": "wide", "camera_moves": [],
              "source_shots": [f"S01-0{i}"]} for i in (1, 2, 3)]
    (d / "production.json").write_text(json.dumps({"meta": {}, "characters": [], "scenes": [{"number": 1, "heading": "INT. ROOM", "start": 0, "end": 12, "notes": {}, "shots": shots}]}))
    (d / "project.json").write_text(json.dumps({"title": "T", "song": "s.wav", "aspect_ratio": "16:9"}))
    (d / "songmap.json").write_text(json.dumps({"duration": 12.0, "lyrics": [], "sections": [], "beats": []}))
    for i in (1, 2, 3):
        Image.new("RGB", (64, 36), (i * 40, 0, 0)).save(d / "media" / f"kf{i}.png")
    Image.new("RGB", (64, 36), (9, 9, 9)).save(d / "media" / "alt.png")
    (d / "keyframes.json").write_text(json.dumps({"production": {"S01-01": "project:media/kf1.png", "S01-02": "project:media/kf2.png"}}))
    for t in ("t1", "t2"):
        subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=red:size=64x36:rate=12:duration=2", "-pix_fmt", "yuv420p", "-c:v", "libx264",
                        str(d / "generations" / f"{t}.mp4")], check=True)
    def take(i, shot, n):
        return {"id": i, "shot_id": shot, "plan": "production", "provider": "kie", "model": "m", "kind": "video", "state": "ready", "output": f"generations/{i}.mp4", "overrides": {},
                "fix_notes": [], "created": n, "updated": n, "attempts": 1, "provider_job_id": i, "error": None, "cost": None, "shot_start": 0, "shot_end": 4}
    img = {**take("i1", "S01-02", 5), "kind": "image", "output": "media/alt.png"}
    (d / "jobs.json").write_text(json.dumps({"jobs": [take("t1", "S01-01", 100), take("t2", "S01-01", 200), img]}))
    return str(d)


def labels(d, which="undo"):
    return [e["label"] for e in H.entries(d)[which]]


# ---------------------------------------------------------------- what is recorded and put back

def test_approving_a_take_can_be_undone_and_redone(project):
    L.approve(project, "S01-01", "t1")
    assert jread(project, "shots.json")["S01-01"]["approved"] == "t1" and labels(project) == ["Approve take · S01-01"]
    r = H.undo(project)
    assert r["label"] == "Approve take · S01-01" and "S01-01" not in (jread(project, "shots.json") or {}) and labels(project) == [] and labels(project, "redo") == ["Approve take · S01-01"]
    H.redo(project)
    assert jread(project, "shots.json")["S01-01"]["approved"] == "t1"


def test_undo_goes_back_to_the_previous_value_not_to_nothing(project):
    L.approve(project, "S01-01", "t1")
    L.approve(project, "S01-01", "t2")
    H.undo(project)
    assert jread(project, "shots.json")["S01-01"]["approved"] == "t1"
    H.undo(project)
    assert "S01-01" not in jread(project, "shots.json")


def test_lock_and_unlock_are_undoable(project):
    L.lock(project, "S01-03", True)
    assert jread(project, "shots.json")["S01-03"]["locked"] is True
    H.undo(project)
    assert "S01-03" not in jread(project, "shots.json")


def test_changing_the_end_frame_settings_is_undoable(project):
    FR.set_(project, "S01-01", {"end_mode": "own", "end_state": "a bright light"})
    FR.set_(project, "S01-01", {"end_state": "the room is empty"})
    assert jread(project, "shots.json")["S01-01"]["end_state"] == "the room is empty"
    H.undo(project)
    assert jread(project, "shots.json")["S01-01"]["end_state"] == "a bright light"
    H.undo(project)
    assert "S01-01" not in jread(project, "shots.json")


def test_starting_from_the_previous_shot_puts_back_the_keyframe_and_the_continuity_setting(project):
    L.approve(project, "S01-01", "t1")
    kf_before = jread(project, "keyframes.json")
    FR.set_start(project, "S01-02", "previous")
    assert jread(project, "keyframes.json") != kf_before and jread(project, "continuity.json")["shots"]["S01-02"]["continuous"] is True
    H.undo(project)
    assert jread(project, "keyframes.json") == kf_before and "S01-02" not in jread(project, "continuity.json")["shots"]


def test_choosing_a_keyframe_is_undoable(project):
    L.choose_keyframe(project, "S01-02", "i1")
    assert jread(project, "keyframes.json")["production"]["S01-02"] == "project:media/alt.png"
    H.undo(project)
    assert jread(project, "keyframes.json")["production"]["S01-02"] == "project:media/kf2.png"


def test_approving_all_pending_keyframes_is_one_step_that_covers_every_shot(project):
    # shots 1 and 2 have keyframes; shot 3 gets a finished keyframe picture that is waiting to be approved
    jobs = jread(project, "jobs.json")
    jobs["jobs"].append({**jobs["jobs"][2], "id": "i3", "shot_id": "S01-03", "output": "media/kf3.png", "created": 6})
    json.dump(jobs, open(os.path.join(project, "jobs.json"), "w"))
    L.approve_keyframes(project)
    assert jread(project, "keyframes.json")["production"]["S01-03"] == "project:media/kf3.png" and len(H.entries(project)["undo"]) == 1
    H.undo(project)
    assert "S01-03" not in jread(project, "keyframes.json")["production"]


def test_the_motion_of_a_shot_is_undoable_and_clearing_it_too(project, tmp_path):
    clip = tmp_path / "m.mp4"
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:size=160x90:rate=12:duration=5", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(clip)], check=True)
    CO.set_motion(project, "S01-01", {"video_path": str(clip)})
    assert "video" in jread(project, "compose.json")["S01-01"]["motion"]
    CO.clear_motion(project, "S01-01")
    assert labels(project) == ["Clear motion · S01-01", "Change motion · S01-01"]
    H.undo(project)
    assert "video" in jread(project, "compose.json")["S01-01"]["motion"]
    H.undo(project)
    assert "motion" not in (jread(project, "compose.json") or {}).get("S01-01", {})
    assert any(f.endswith(".mp4") for f in os.listdir(os.path.join(project, "media")))          # the copied video is never deleted


# ---------------------------------------------------------------- what is not recorded

def test_a_change_that_fails_leaves_no_entry(project):
    L.lock(project, "S01-01", True)
    assert len(H.entries(project)["undo"]) == 1
    with pytest.raises(SystemExit):
        L.approve(project, "S01-01", "t1")                                     # locked: refused
    assert len(H.entries(project)["undo"]) == 1 and jread(project, "shots.json")["S01-01"].get("approved") is None


def test_a_change_that_changes_nothing_leaves_no_entry(project):
    L.lock(project, "S01-01", True)
    L.lock(project, "S01-01", True)
    assert len(H.entries(project)["undo"]) == 1


def test_nothing_to_undo_or_redo_says_so(project):
    with pytest.raises(SystemExit, match="nothing to undo"):
        H.undo(project)
    with pytest.raises(SystemExit, match="nothing to redo"):
        H.redo(project)


def test_a_new_change_ends_the_redo_trail(project):
    L.approve(project, "S01-01", "t1")
    H.undo(project)
    assert labels(project, "redo")
    L.approve(project, "S01-01", "t2")
    assert labels(project, "redo") == []


def test_the_list_is_newest_first_and_capped(project, monkeypatch):
    monkeypatch.setattr(H, "MAX_ENTRIES", 5)
    for i in range(8):
        L.lock(project, "S01-01", i % 2 == 0)
    e = H.entries(project)
    assert e["undo_count"] == 5 and len(e["undo"]) == 5 and e["undo"][0]["at"] >= e["undo"][-1]["at"]


def test_a_damaged_journal_is_just_empty(project):
    open(os.path.join(project, "undo.json"), "w").write("{not json")
    assert H.entries(project)["undo_count"] == 0
    json.dump(["x", 1], open(os.path.join(project, "undo.json"), "w"))
    assert H.entries(project)["undo_count"] == 0
    L.approve(project, "S01-01", "t1")                                         # and recording works again
    assert H.entries(project)["undo_count"] == 1


# ---------------------------------------------------------------- a journal from someone else's project

HOSTILE = [
    {"f": "jobs.json", "k": ["S01-01"], "b": {"x": 1}},                              # not one of the settings files
    {"f": "../../etc/passwd", "k": ["a"], "b": {"x": 1}},
    {"f": "shots.json", "k": ["../x"], "b": {"x": 1}},                               # a key that leads elsewhere
    {"f": "shots.json", "k": ["a", "b"], "b": {"x": 1}},                             # wrong depth
    {"f": "shots.json", "k": ["S01-01"], "b": "not a dict"},
    {"f": "shots.json", "k": ["S01-01"], "b": {"big": "x" * 60000}},                 # too large
    {"f": "keyframes.json", "k": ["production", "S01-01"], "b": "C:/Windows/win.ini"},
    {"f": "keyframes.json", "k": ["production", "S01-01"], "b": "project:../../secret.png"},
    {"f": "keyframes.json", "k": ["production", "S01-01"], "b": "project:C:/x.png"},
    {"f": "keyframes.json", "k": ["production", "S01-01"], "b": {"not": "a string"}},
    {"f": "continuity.json", "k": ["scenes", "1"], "b": {"x": 1}},                    # only the "shots" part may change
    {"f": "shots.json", "k": "S01-01", "b": {"x": 1}},
    "not even a dict",
]


@pytest.mark.security
@pytest.mark.parametrize("change", HOSTILE)
def test_a_hostile_entry_is_refused_and_changes_nothing(project, change):
    L.approve(project, "S01-01", "t1")
    before = {n: jread(project, n) for n in ("shots.json", "keyframes.json", "jobs.json", "continuity.json")}
    j = json.load(open(os.path.join(project, "undo.json")))
    j["undo"][-1]["changes"] = [change]
    json.dump(j, open(os.path.join(project, "undo.json"), "w"))
    with pytest.raises(SystemExit, match="damaged"):
        H.undo(project)
    assert {n: jread(project, n) for n in before} == before and len(H.entries(project)["undo"]) == 1


@pytest.mark.security
def test_one_bad_change_among_good_ones_applies_none_of_them(project):
    L.approve(project, "S01-01", "t1")
    j = json.load(open(os.path.join(project, "undo.json")))
    j["undo"][-1]["changes"].append({"f": "jobs.json", "k": ["x"], "b": {}})
    json.dump(j, open(os.path.join(project, "undo.json"), "w"))
    with pytest.raises(SystemExit):
        H.undo(project)
    assert jread(project, "shots.json")["S01-01"]["approved"] == "t1"


def test_a_label_from_the_file_is_shortened_and_the_values_are_not_run_as_anything(project):
    L.approve(project, "S01-01", "t1")
    j = json.load(open(os.path.join(project, "undo.json")))
    j["undo"][-1]["label"] = "x" * 1000
    json.dump(j, open(os.path.join(project, "undo.json"), "w"))
    assert len(H.entries(project)["undo"][0]["label"]) <= 120
