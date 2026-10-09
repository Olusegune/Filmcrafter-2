import json
import os
import subprocess
import sys

ENG = os.path.join(os.path.dirname(__file__), "..")


def run(code):
    return subprocess.run([sys.executable, "-c", code], cwd=ENG, capture_output=True, text=True)


def test_an_unexpected_crash_is_one_readable_line_for_the_app_and_keeps_the_trace(tmp_path):
    p = run("import filmcrafter_engine\nraise IndexError('list index out of range')")
    assert p.returncode == 1
    ev = json.loads(p.stdout.strip().splitlines()[-1])
    assert ev["event"] == "error" and "IndexError: list index out of range" in ev["message"] and "Nothing was lost" in ev["message"]
    assert "Traceback" in p.stderr                                                                    # the detail is still there for whoever debugs it


def test_malformed_input_to_a_command_is_reported_not_dumped(tmp_path):
    (tmp_path / "project.json").write_text("{}")
    p = subprocess.run([sys.executable, "-m", "filmcrafter_engine.refgen", "cards", str(tmp_path), "--data", "not json"], cwd=ENG, capture_output=True, text=True)
    ev = json.loads(p.stdout.strip().splitlines()[-1])
    assert p.returncode != 0 and ev["event"] == "error" and "JSONDecodeError" in ev["message"]


def test_a_normal_exit_and_a_deliberate_exit_are_untouched():
    assert run("import filmcrafter_engine").returncode == 0
    p = run("import filmcrafter_engine, sys\nsys.exit(3)")
    assert p.returncode == 3 and p.stdout == ""
