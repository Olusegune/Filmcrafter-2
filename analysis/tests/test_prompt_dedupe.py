"""The same lock stated once: a character whose rules are given in full in the 'Locked design' block is not described again in 'Characters', and a reference label does not repeat
the notes (cut at 120 characters, so a lock could end mid-word) that block already states. Also the prompt trace the budget view reads."""
import json
import os

import pytest

from filmcrafter_engine import render as R
from tests.test_native_dialogue import SHOT, _talking, scene  # noqa: F401  (a project folder with one shot; a fixture)
from tests.test_render import field, man

LOCKED = ("Locked design, keep exactly: Beatrice Queen Bee Adeyemi: 60; dark brown skin; round face; arched eyebrows; curvy sturdy build; burgundy sculptural gele | "
          "Queen Bee reading glasses: Thin gold rectangular frame; 13 cm wide.")
PLAN = {"meta": {}, "characters": [{"name": "Beatrice Queen Bee Adeyemi", "appearance": "A 60-year-old woman with dark brown skin. Round face and arched eyebrows. More."},
                                   {"name": "Zara", "appearance": "A young woman with a rust gele. Calm eyes. More."}], "scenes": []}
SHOT_ = {"id": "S01-05", "start": 8.5, "end": 14.7, "performers": ["Beatrice Queen Bee Adeyemi", "Zara"], "description": "Close on Beatrice.", "locked_design": LOCKED}
REFS = [{"label": "reference for Beatrice Queen Bee Adeyemi (face, expressions, full-body turnaround) — Locked: 60; dark brown skin; round face; arched eyebrows; curvy sturdy build; burgundy sculptural gele; rectangular read",
         "url": "u1", "media": "image"},
        {"label": "reference for Zara (face) — a rust gele and a calm look", "url": "u2", "media": "image"}]


def with_refs():
    """A model that takes reference pictures and has a duration, so the References line is built."""
    return man(field("prompt", required=True), field("duration", enum=["4s", "6s", "8s"]), field("image_urls", "array", items="string"))


def build(shot=SHOT_, refs=REFS, trace=None, model=None, **kw):
    return R.compile_request(shot, None, PLAN, {"look": {"style": "auto"}}, model or with_refs(), refs, trace=trace, **kw)["prompt"]


def test_a_character_with_locks_is_named_not_described_a_second_time():
    p = build()
    assert "Characters: Beatrice Queen Bee Adeyemi; Zara (A young woman with a rust gele. Calm eyes)." in p
    assert "Beatrice Queen Bee Adeyemi (A 60-year-old" not in p


def test_without_a_locked_design_the_character_is_described_as_before():
    shot = {k: v for k, v in SHOT_.items() if k != "locked_design"}
    p = build(shot)
    assert "Beatrice Queen Bee Adeyemi (A 60-year-old woman with dark brown skin. Round face and arched eyebrows)" in p


def test_a_reference_label_loses_the_notes_the_locked_design_already_states():
    p = build()
    assert "the first reference image is the reference for Beatrice Queen Bee Adeyemi (face, expressions, full-body turnaround);" in p
    assert "— Locked: 60" not in p and "rectangular read" not in p                          # the fragment that used to end mid-word
    assert "reference for Zara (face) — a rust gele and a calm look" in p                    # Zara has no locks stated, so her label keeps its note


def test_the_locks_are_still_in_the_prompt_once_in_full():
    p = build()
    assert p.count("curvy sturdy build") == 1 and "13 cm wide" in p                        # said once, in the Locked design block


def test_the_trace_lists_every_block_and_whether_it_was_kept():
    trace = []
    prompt = build(trace=trace)
    assert trace and all(set(b) == {"priority", "text", "kept"} for b in trace)
    assert all(b["kept"] for b in trace) and " ".join(b["text"] for b in trace if b["kept"]) == prompt
    assert any(b["text"].startswith("Characters:") for b in trace) and any(b["text"].startswith("Locked design") for b in trace)


def test_the_trace_marks_what_the_length_limit_dropped(monkeypatch):
    monkeypatch.setattr(R, "known_prompt_limit", lambda m: 420)
    trace = []
    prompt = build(trace=trace)
    dropped = [b for b in trace if not b["kept"]]
    assert dropped and len(prompt.encode("utf-8")) <= 420
    assert min(b["priority"] for b in dropped) <= min(b["priority"] for b in trace if b["kept"])      # the lowest priorities go first


def test_the_preview_hands_the_blocks_to_the_screen(scene, monkeypatch):                    # noqa: F811
    plan = {"meta": {}, "characters": [], "scenes": [{"number": 1, "heading": "INT.", "shots": [{**SHOT, "start": 0.0, "end": 3.0}]}]}
    json.dump(plan, open(os.path.join(scene, "production.json"), "w"))
    json.dump({"title": "T", "look": {"style": "auto"}}, open(os.path.join(scene, "project.json"), "w"))
    monkeypatch.setattr(R, "manifest", lambda p, m: _talking())
    monkeypatch.setattr(R, "_reference_files", lambda *a, **k: [])
    out = R.preview(scene, "S01-01", "fal", "test/talker", None)
    assert out["prompt_blocks"] and out["payload"]["prompt"] == " ".join(b["text"] for b in out["prompt_blocks"] if b["kept"])
