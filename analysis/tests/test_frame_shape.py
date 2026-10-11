"""The shape of a film's frame (16:9, 21:9, 9:16...): chosen when the film is made, changed later, and followed by the render project."""
import json
import os
import re

import pytest

from filmcrafter_engine import bible, make, shots, story

SCRIPT = "INT. KITCHEN - MORNING\n\nSarah pours tea.\n\nSARAH\nHello.\n"
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def _film(tmp_path, aspect=None):
    kw = {} if aspect is None else {"aspect_ratio": aspect}
    return story.create(str(tmp_path), "T", "screenplay", SCRIPT, **kw)["dir"]


def test_a_film_starts_widescreen_unless_told_otherwise(tmp_path):
    assert story.status(_film(tmp_path))["aspect_ratio"] == "16:9"


@pytest.mark.parametrize("shape", story.ASPECTS)
def test_every_listed_shape_can_be_chosen_when_the_film_is_made(tmp_path, shape):
    d = _film(tmp_path / shape.replace(":", "x"), shape)
    assert story.status(d)["aspect_ratio"] == shape


def test_an_unknown_shape_is_refused_before_anything_is_made(tmp_path):
    for bad in ("7:3", "", "wide", "16/9", "0:0"):
        with pytest.raises(SystemExit):
            story.create(str(tmp_path), "T", "screenplay", SCRIPT, aspect_ratio=bad)
    assert not os.listdir(tmp_path)


def test_the_shape_can_be_changed_later_and_the_render_project_follows(tmp_path):
    d = _film(tmp_path)
    bible.seed(d)
    shots.breakdown(d)
    rd = make.sync(d)["render_dir"]
    assert json.load(open(os.path.join(rd, "project.json")))["aspect_ratio"] == "16:9"
    assert story.set_aspect(d, "9:16")["aspect_ratio"] == "9:16"
    assert json.load(open(os.path.join(d, "film.json")))["aspect_ratio"] == "9:16"
    assert json.load(open(os.path.join(make.sync(d)["render_dir"], "project.json")))["aspect_ratio"] == "9:16"
    with pytest.raises(SystemExit):
        story.set_aspect(d, "5:1")
    assert story.status(d)["aspect_ratio"] == "9:16"                       # a refused change leaves the film as it was


def test_the_command_line_sets_the_shape(tmp_path, capsys):
    d = _film(tmp_path)
    assert story.main(["set_aspect", d, "--data", json.dumps({"aspect_ratio": "21:9"})]) == 0
    assert '"21:9"' in capsys.readouterr().out
    assert story.main(["set_aspect", d, "--data", json.dumps({"aspect_ratio": "nope"})]) == 1


def test_the_engine_the_shell_and_the_screens_offer_the_same_shapes():
    rs = open(os.path.join(ROOT, "src-tauri", "src", "lib.rs"), encoding="utf-8").read()
    shell = re.search(r"const ASPECTS: \[&str; \d+\] = \[(.*?)\];", rs, re.S).group(1)
    assert set(re.findall(r'"([^"]+)"', shell)) == set(story.ASPECTS)
    ts = open(os.path.join(ROOT, "src", "frame.ts"), encoding="utf-8").read()
    shown = set(re.findall(r'\["(\d+(?:\.\d+)?:\d+(?:\.\d+)?)", "', ts.split("export const QUALITY")[0]))
    assert shown and shown <= set(story.ASPECTS)
    assert {"16:9", "21:9", "9:16", "1:1"} <= shown                       # the ones people ask for are offered
