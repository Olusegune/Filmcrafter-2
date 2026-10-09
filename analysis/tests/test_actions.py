"""Director Command actions: parsing only (nothing is sent; the app confirms first)."""
import json

import pytest

from filmcrafter_engine import actions as A
from filmcrafter_engine import library as L


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "x")
    monkeypatch.delenv("KIE_KEY", raising=False)
    d = tmp_path / "p"
    d.mkdir()
    scenes = []
    t = 0.0
    for sc in range(1, 4):
        shots = []
        for n in range(1, 5):
            shots.append({"id": f"S{sc:02d}-{n:02d}", "start": t, "end": t + 2, "performers": [], "beats": ["x"]})
            t += 2
        scenes.append({"number": sc, "heading": f"Scene {sc}", "shots": shots})
    (d / "production.json").write_text(json.dumps({"scenes": scenes}))
    (d / "project.json").write_text(json.dumps({"title": "T"}))
    (d / "songmap.json").write_text(json.dumps({"sections": [
        {"label": "VERSE", "start": 0, "end": 8}, {"label": "CHORUS", "start": 8, "end": 16}, {"label": "CHORUS", "start": 16, "end": 24}]}))
    return str(d)


@pytest.mark.parametrize("note,kind,shots,model", [
    ("Regenerate shot 12 using Kling", "video", ["S03-04"], "fal-ai/kling-video/v3/turbo/pro/image-to-video"),
    ("render the second chorus with Veo", "video", ["S03-01", "S03-02", "S03-03", "S03-04"], "fal-ai/veo3.1/fast/image-to-video"),
    ("keyframes for scene 2", "image", ["S02-01", "S02-02", "S02-03", "S02-04"], "fal-ai/nano-banana/edit"),
    ("re-render S01-02 and 1-03 with wan", "video", ["S01-02", "S01-03"], "alibaba/wan-3.0/image-to-video"),
    ("render shots 2-3", "video", ["S01-02", "S01-03"], "bytedance/seedance-2.0/reference-to-video"),
    ("render this shot", "video", ["S02-01"], "bytedance/seedance-2.0/reference-to-video"),
])
def test_render_actions(proj, note, kind, shots, model):
    r = A.parse(proj, note, selected="S02-01")
    assert r["type"] == "action" and r["action"] == "render" and r["render_kind"] == kind
    assert r["shots"] == shots and r["model"] == model and r["billable"]


def test_notes_are_not_actions(proj):
    assert A.parse(proj, "make the second chorus warmer")["type"] == "direction"
    assert A.parse(proj, "less camera movement in the verse")["type"] == "direction"


def test_locked_shots_are_skipped_and_reported(proj):
    L.set_shot(proj, "S03-04", locked=True)
    r = A.parse(proj, "render the second chorus")
    assert "S03-04" not in r["shots"] and r["skipped"] == [{"id": "S03-04", "reason": "locked"}]
    assert A.parse(proj, "render shot 12")["type"] == "error"


def test_unavailable_provider_explains(proj):
    r = A.parse(proj, "render shot 1 with hailuo on kie")
    assert r["type"] == "error" and "Kie.ai" in r["message"]


def test_approve_keyframes_action(proj):
    import os
    from PIL import Image
    os.makedirs(os.path.join(proj, "generations"))
    Image.new("RGB", (8, 8)).save(os.path.join(proj, "generations", "a.png"))
    json.dump({"jobs": [{"id": "a", "shot_id": "S02-01", "plan": "production", "kind": "image", "state": "ready",
                         "output": "generations/a.png", "created": 1}]}, open(os.path.join(proj, "jobs.json"), "w"))
    r = A.parse(proj, "approve all keyframes")
    assert r["action"] == "approve_keyframes" and r["shots"] == ["S02-01"] and not r["billable"]
