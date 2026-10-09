"""The light plan reader must behave exactly like the rendering module's, and must not load it."""
import json
import subprocess
import sys

import pytest

from pulseframe_analysis import planio, render


def plan(tmp_path, **files):
    d = tmp_path / "p"
    d.mkdir(exist_ok=True)
    for name, data in files.items():
        (d / f"{name}.json").write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return str(d)


SC = {"scenes": [{"number": 1, "shots": [{"id": "S01-01"}, {"id": "S01-02"}]}]}


@pytest.mark.parametrize("files", [{"production": SC}, {"directed": SC, "production": {"scenes": []}}, {"directed": "{ not json", "production": SC}, {"directed": {}, "production": SC}])
def test_it_picks_the_same_plan_as_the_rendering_module(tmp_path, files):
    d = plan(tmp_path, **files)
    assert planio.load_plan(d) == render._load_plan(d)


def test_both_refuse_a_project_with_no_plan_in_the_same_words(tmp_path):
    d = plan(tmp_path)
    with pytest.raises(SystemExit) as a:
        planio.load_plan(d)
    with pytest.raises(SystemExit) as b:
        render._load_plan(d)
    assert str(a.value) == str(b.value)


def test_it_finds_shots_like_the_rendering_module_and_refuses_a_missing_one(tmp_path):
    assert planio.find_shot(SC, "S01-02") == render._shot(SC, "S01-02")
    with pytest.raises(SystemExit) as a:
        planio.find_shot(SC, "S09-09")
    with pytest.raises(SystemExit) as b:
        render._shot(SC, "S09-09")
    assert str(a.value) == str(b.value)


@pytest.mark.parametrize("module,args", [("camera", ["vocab"]), ("looks", None), ("dance", ["check"])])
def test_the_quick_actions_do_not_load_the_rendering_module(tmp_path, module, args):
    code = {"camera": "import pulseframe_analysis.camera as m; m.vocab(); m.get; import sys; print('pulseframe_analysis.render' in sys.modules)",
            "looks": "import pulseframe_analysis.looks as m, json, sys; d=sys.argv[1]; m.suggest(d); print('pulseframe_analysis.render' in sys.modules)",
            "dance": "import pulseframe_analysis.dance as m, sys; m.check(sys.argv[1]); print('pulseframe_analysis.render' in sys.modules)"}[module]
    d = plan(tmp_path, production={"scenes": [{"number": 1, "shots": [{"id": "S01-01", "start": 0, "end": 2, "emotion": "joy"}]}]})
    out = subprocess.run([sys.executable, "-c", code, d], capture_output=True, text=True, cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    assert out.stdout.strip().splitlines()[-1] == "False", out.stderr[-300:]
