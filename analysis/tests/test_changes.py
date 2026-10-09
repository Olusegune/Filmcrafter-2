"""What changed since the last take: exactly the differences in what the model is told and shown, nothing else."""
import json
import os

import pytest

from pulseframe_analysis import changes as C
from tests.test_lipsync_mode import preview, seedance

MAN = seedance()


def take(payload, **kw):
    return {"id": "j1", "model": "bytedance/seedance-2-fast", "keyframe_ref": "project:assets/kf.png", "payload": payload, **kw}


def now(payload, kf="project:assets/kf.png", model="bytedance/seedance-2-fast"):
    return {"payload": payload, "keyframe": kf, "manifest": {"model": model, "title": "Seedance 2 Fast"}}


def kinds(rows):
    return [r["kind"] for r in rows]


# ---------------------------------------------------------------- prompt sentences
def test_sentences_split_on_full_stops_and_ignore_whitespace():
    assert C.sentences("She waits.  The light is low.\nShe breathes! Why?") == ["She waits.", "The light is low.", "She breathes!", "Why?"]
    assert C.sentences("") == [] and C.sentences(None) == []


def test_only_sentences_added_or_removed_count_not_their_order():
    added, removed = C.prompt_diff("A one. B two. C three.", "C three. A one. D four.")
    assert added == ["D four."] and removed == ["B two."]
    assert C.prompt_diff("A one. B two.", "B two. A one.") == ([], [])


# ---------------------------------------------------------------- the comparison
def test_an_identical_request_has_no_changes():
    p = {"prompt": "She waits. The light is low.", "first_frame_url": "x", "duration": 4}
    assert C.compare(take(p), now(dict(p)), MAN) == []


def test_a_new_sentence_and_a_removed_one_are_listed_as_such():
    r = C.compare(take({"prompt": "She waits. The light is low."}), now({"prompt": "She waits. A low-key light. Camera: slow push."}), MAN)
    assert [(x["kind"], x["text"]) for x in r] == [("prompt_removed", "The light is low."), ("prompt_added", "A low-key light."), ("prompt_added", "Camera: slow push.")]


def test_a_different_keyframe_or_none_at_all_is_said_plainly():
    p = {"prompt": "x"}
    assert kinds(C.compare(take(p), now(p, kf="project:assets/other.png"), MAN)) == ["keyframe"]
    assert "A different keyframe" in C.compare(take(p), now(p, kf="project:assets/other.png"), MAN)[0]["text"]
    assert "removed" in C.compare(take(p), now(p, kf=None), MAN)[0]["text"]
    assert "made without one" in C.compare(take(p, keyframe_ref=None), now(p), MAN)[0]["text"]


def test_moving_the_keyframe_from_first_frame_to_reference_and_the_vocal_arriving_are_both_reported():
    old = {"prompt": "x", "first_frame_url": "project:assets/kf.png"}
    new = {"prompt": "x", "reference_image_urls": ["a"], "reference_audio_urls": ["v.mp3"]}
    r = C.compare(take(old), now(new), MAN)
    assert set(kinds(r)) == {"first_frame", "audio", "references"}
    assert any("no longer the first frame" in x["text"] for x in r) and any("vocal is now sent" in x["text"] for x in r)


def test_reference_counts_length_and_model_changes_are_reported():
    r = C.compare(take({"prompt": "x", "reference_image_urls": ["a", "b"], "duration": 4}), now({"prompt": "x", "reference_image_urls": ["a"], "duration": 6}, model="other/model"), MAN)
    assert set(kinds(r)) == {"references", "length", "model"}
    assert any("1 reference picture are sent now, 2 before" in x["text"] for x in r)
    assert any("from 4 to 6 s" in x["text"] for x in r)


def test_a_long_list_of_prompt_changes_is_cut_and_counted_and_long_sentences_are_shortened():
    new = " ".join(f"New sentence number {i}." for i in range(12)) + " " + ("Word " * 60).strip() + "."
    r = C.compare(take({"prompt": "Old."}), now({"prompt": new}), MAN)
    assert sum(1 for x in r if x["kind"] == "prompt_added") == C.MAX_LINES
    assert r[-1]["kind"] == "prompt_more" and "5 more prompt changes" in r[-1]["text"]
    assert all(len(x["text"]) <= C.MAX_LEN + 40 for x in r)


def test_a_take_without_a_stored_request_does_not_crash_the_comparison():
    r = C.compare({"id": "j0"}, now({"prompt": "Anything."}), MAN)
    assert "prompt_added" in kinds(r)


# ---------------------------------------------------------------- against a real project
def project_with_take(tmp_path, monkeypatch, **extra):
    first = preview(tmp_path, monkeypatch, **extra)
    d = str(tmp_path / "pv")
    json.dump({"jobs": [{"id": "j1", "shot_id": "S01-01", "plan": "production", "provider": "kie", "model": "bytedance/seedance-2-fast", "kind": "video", "state": "ready", "output": "g/j1.mp4",
                         "created": 100, "updated": 100, "payload": first["payload"], "keyframe_ref": "project:assets/kf.png", "attempts": 1, "overrides": {}}]}, open(os.path.join(d, "jobs.json"), "w"))
    return d


def test_a_shot_with_no_take_says_so(tmp_path, monkeypatch):
    preview(tmp_path, monkeypatch)
    r = C.since_last_take(str(tmp_path / "pv"), "S01-01")
    assert r["has_take"] is False and "no rendered take" in r["note"]


def test_nothing_changed_since_the_last_take(tmp_path, monkeypatch):
    d = project_with_take(tmp_path, monkeypatch)
    r = C.since_last_take(d, "S01-01", "kie", "bytedance/seedance-2-fast")
    assert r["has_take"] and r["same"] is True and r["changes"] == [] and "look much the same" in r["note"]


def test_switching_to_follow_the_song_is_reported_as_what_changed(tmp_path, monkeypatch):
    d = project_with_take(tmp_path, monkeypatch)
    p = json.load(open(os.path.join(d, "project.json")))
    p["lip_sync_mode"] = "audio_first"
    json.dump(p, open(os.path.join(d, "project.json"), "w"))
    r = C.since_last_take(d, "S01-01", "kie", "bytedance/seedance-2-fast")
    assert r["same"] is False
    assert {"first_frame", "audio"} <= set(kinds(r["changes"]))


def test_editing_the_shots_beats_shows_up_as_prompt_sentences(tmp_path, monkeypatch):
    d = project_with_take(tmp_path, monkeypatch)
    plan = json.load(open(os.path.join(d, "production.json")))
    plan["scenes"][0]["shots"][0]["beats"] = ["Queen Bee throws the door open."]
    json.dump(plan, open(os.path.join(d, "production.json"), "w"))
    r = C.since_last_take(d, "S01-01", "kie", "bytedance/seedance-2-fast")
    assert any(x["kind"] == "prompt_added" and "throws the door open" in x["text"] for x in r["changes"])
    assert any(x["kind"] == "prompt_removed" and "calls down" in x["text"] for x in r["changes"])
