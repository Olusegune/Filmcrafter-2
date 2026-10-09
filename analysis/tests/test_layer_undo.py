"""Undo and redo for the layers (on-screen text, pictures, shapes): every change keeps the layers as they were, in the engine's own copy."""
import json
import os

import pytest

from filmcrafter_engine import layerkit as LK, overlays as O

pytestmark = pytest.mark.integration


@pytest.fixture
def proj(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    (d / "project.json").write_text(json.dumps({"title": "T"}))
    (d / "songmap.json").write_text(json.dumps({"duration": 60.0, "sections": [], "lyrics": [
        {"text": "one", "start": 1.0, "end": 3.0}, {"text": "two", "start": 4.0, "end": 6.0}]}))
    return str(d)


def texts(d):
    return [o.get("text") for o in O.load(d)]


def test_nothing_to_undo_or_redo_at_the_start(proj):
    assert O.history(proj) == {"can_undo": False, "can_redo": False, "undo": 0, "redo": 0}
    with pytest.raises(SystemExit, match="nothing to undo"):
        O.undo(proj)
    with pytest.raises(SystemExit, match="nothing to redo"):
        O.redo(proj)


def test_an_added_layer_can_be_undone_and_redone(proj):
    O.add(proj, {"text": "HELLO", "start": 1, "end": 5})
    assert texts(proj) == ["HELLO"] and O.history(proj)["can_undo"]
    O.undo(proj)
    assert texts(proj) == [] and O.history(proj)["can_redo"]
    O.redo(proj)
    assert texts(proj) == ["HELLO"]


def test_an_edit_and_a_removal_are_each_one_step(proj):
    o = O.add(proj, {"text": "A", "start": 1, "end": 5})[-1]
    O.update(proj, o["id"], {"text": "B"})
    O.remove(proj, o["id"])
    assert texts(proj) == []
    O.undo(proj)
    assert texts(proj) == ["B"]
    O.undo(proj)
    assert texts(proj) == ["A"]
    O.undo(proj)
    assert texts(proj) == []
    assert not O.history(proj)["can_undo"]


def test_a_new_change_ends_the_redo_trail(proj):
    O.add(proj, {"text": "A", "start": 1, "end": 5})
    O.undo(proj)
    O.add(proj, {"text": "B", "start": 1, "end": 5})
    assert not O.history(proj)["can_redo"]
    with pytest.raises(SystemExit):
        O.redo(proj)


def test_lyrics_as_layers_is_one_undo_not_one_per_line(proj):
    O.add(proj, {"text": "KEEP", "start": 1, "end": 5})
    LK.lyrics_layers(proj, {})
    assert len(O.load(proj)) > 1
    O.undo(proj)
    assert texts(proj) == ["KEEP"]


def test_only_the_last_forty_changes_are_kept(proj):
    for i in range(O.UNDO_KEEP + 8):
        O.add(proj, {"text": f"L{i}", "start": 1, "end": 5})
    assert O.history(proj)["undo"] == O.UNDO_KEEP


def test_a_damaged_history_file_is_ignored_not_fatal(proj):
    O.add(proj, {"text": "A", "start": 1, "end": 5})
    open(O._history_path(proj), "w").write("{not json")
    assert O.history(proj)["can_undo"] is False
    O.add(proj, {"text": "B", "start": 1, "end": 5})
    assert texts(proj) == ["A", "B"]


def test_the_command_line_answers_in_json(proj, capsys):
    O.add(proj, {"text": "A", "start": 1, "end": 5})
    assert O.main(["history", proj]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["data"]["can_undo"] is True
    assert O.main(["undo", proj]) == 0
    assert texts(proj) == []
    assert O.main(["undo", proj]) == 1
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["event"] == "error"


def test_the_history_is_not_part_of_the_project_file_list(proj):
    O.add(proj, {"text": "A", "start": 1, "end": 5})
    assert os.path.exists(O._history_path(proj)) and os.path.dirname(O._history_path(proj)).endswith("cache")
