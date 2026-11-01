"""Every door the screen uses to reach the engine (a module run as `python -m filmcrafter_engine.<name> <action> <project> --data {...}`), given hostile data for every action it has. What the person would see
is the message the door prints, so the rule is: an error is a plain sentence, never a Python error name or a file path of ours. Actions that write to a path the person chose, make video or call a provider are not
thrown at here (they have their own tests). Seeded, so a failure can be repeated."""
import importlib
import json
import random
import re

import pytest

from tests.test_fuzz_validators import POOL
from tests.test_performance_director import film  # noqa: F401  (a small film with a render project)

pytestmark = pytest.mark.integration

# door -> which folder it takes: the film itself ("f") or its render project ("r")
DOORS = {"overlays": "r", "layerkit": "r", "presets": "r", "series": "r", "grading": "r", "editing": "f", "smart_editor": "f", "performance": "r", "acting": "r", "story": "f", "bible": "f",
         "camera": "r", "captions": "r", "choreography": "r", "colormatch": "r", "composition": "r", "continuity": "r", "customframe": "r", "directions_library": "r", "frames": "r", "golden": "r", "lighting": "r",
         "shotsound": "r", "stylebible": "f", "titlecard": "r", "track": "r", "shots": "f", "audioplan": "r", "audiocues": "r", "materials": "f"}
SKIP = {"export", "import_file", "export_markdown", "make", "preview_proxy", "proxies", "backup", "restore", "render", "speak", "design", "clone", "queue", "create", "import_lut", "lut", "import", "save_as", "open", "pack",
        "preview", "upload", "analyze", "estimate", "suggest_llm", "describe"}
RAW = re.compile(r"\b(TypeError|KeyError|AttributeError|ValueError|IndexError|ZeroDivisionError|OverflowError|RecursionError|UnicodeError|JSONDecodeError|Traceback|NoneType|object is not|unhashable|C:\\\\Users|site-packages)\b")


def actions_of(mod):
    src = open(mod.__file__, encoding="utf-8").read()
    m = re.search(r"add_argument\(\"action\", choices=\[(.*?)\]", src, re.S)
    return [a for a in re.findall(r"\"([a-z_0-9]+)\"", m.group(1))] if m else []


@pytest.mark.parametrize("door", sorted(DOORS))
def test_the_door_answers_hostile_data_with_a_result_or_a_plain_sentence(door, film, capsys):
    f, rd = film
    mod = importlib.import_module(f"filmcrafter_engine.{door}")
    acts = [a for a in actions_of(mod) if a not in SKIP]
    if not acts:
        pytest.skip("no actions found for this door")
    rng = random.Random(hash(door) & 0xFFFF)
    raw: list[str] = []
    answered = refused = 0
    for _ in range(120):
        action = rng.choice(acts)
        keys = ["id", "ids", "name", "shot", "scene", "at", "start", "end", "value", "stack", "text", "kind", "x", "y", "n", "data", "key", "op", "clip", "by", "seconds", "scope", "grade", "look", "acting"]
        data = {k: rng.choice(POOL) for k in rng.sample(keys, rng.randint(0, 6))}
        project = rd if DOORS[door] == "r" else f
        try:
            mod.main([action, project, "--data", json.dumps(data, default=str)])
        except SystemExit:
            pass                                                                                    # argparse itself (a bad action name) is not what is tested here
        out = capsys.readouterr().out
        for line in out.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("event") == "error":
                refused += 1
                if RAW.search(str(ev.get("message", ""))):
                    raw.append(f"{action} {json.dumps(data, default=str)[:140]} -> {ev['message'][:160]}")
            elif ev.get("event") == "result":
                answered += 1
    assert not raw, "\n".join(raw[:8])
    assert answered + refused > 0                                                                  # the door was reached and said something
