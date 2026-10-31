"""Starting a film from a preset on Home: the choice is remembered when the film is made, and the film itself is not changed until the person previews and applies it in Presets (a preset sets up the
render project, which a new film does not have yet). Free and local; no provider is called."""
import hashlib
import json
import os

import pytest

from filmcrafter_engine import presets as P, story
from tests.test_performance_director import film  # noqa: F401  (a small film with a render project)

pytestmark = pytest.mark.integration


def new_film(tmp_path):
    r = story.create(str(tmp_path), "A Short One", "idea", "A girl waits for a train that never comes.", None, "16:9")
    return r["dir"] if isinstance(r, dict) and "dir" in r else r


def digest(path):
    return hashlib.sha1(open(path, "rb").read()).hexdigest()


def test_choosing_a_preset_on_home_only_remembers_it_and_changes_nothing_in_the_film(tmp_path):
    d = new_film(tmp_path)
    before = digest(os.path.join(d, "film.json"))
    out = P.run(d, "set_pending", {"stack": ["vertical_micro_drama"]})
    assert out == {"pending": ["vertical_micro_drama"]}
    assert digest(os.path.join(d, "film.json")) == before                                        # the story, the frame, the Bible: untouched
    assert P.load_state(d)["pending"] == ["vertical_micro_drama"] and P.load_state(d)["stack"] == [] and P.load_state(d)["applied"] == []
    assert not os.path.exists(os.path.join(d, "render"))                                         # no render project was made either


def test_only_presets_that_exist_can_be_remembered_and_only_a_few(tmp_path):
    d = new_film(tmp_path)
    for bad in ([], ["../../etc/passwd"], ["nope"], [None], "vertical_micro_drama"):
        with pytest.raises(SystemExit, match="Choose a preset"):
            P.run(d, "set_pending", {"stack": bad})
    assert P.run(d, "set_pending", {"stack": ["nope", "documentary"]})["pending"] == ["documentary"]
    many = list(P.builtin())[:12]
    assert len(P.run(d, "set_pending", {"stack": many})["pending"]) == P.MAX_PENDING


def test_the_remembered_choice_shows_in_the_catalog_and_is_cleared_once_it_is_applied(film):
    d, film = film
    P.run(d, "set_pending", {"stack": ["vertical_micro_drama", "documentary"]})
    assert P.catalog(film)["pending"] == ["vertical_micro_drama", "documentary"]                 # the same record, seen from the render project the Presets sheet opens
    P.apply(film, ["vertical_micro_drama"])
    assert P.catalog(film)["pending"] == ["documentary"]                                          # what was applied is no longer waiting; what was not, still is
    P.apply(film, ["documentary"])
    assert P.catalog(film)["pending"] == []


def test_a_film_with_no_pending_choice_and_an_older_record_load_as_before(film):
    d, film = film
    path = os.path.join(d, "presets", "state.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump({"schema": 1, "stack": ["documentary"], "favorites": ["documentary"]}, open(path, "w"))      # a record written before pending existed
    st = P.load_state(film)
    assert st["pending"] == [] and st["stack"] == ["documentary"] and st["favorites"] == ["documentary"]


def test_every_preset_shown_on_home_exists_and_has_a_picture():
    b = P.builtin()
    for pid in ("vertical_micro_drama", "animated_short", "storybook_2_5d_style", "historical_explainer", "documentary", "youtube_shorts"):
        assert pid in b and b[pid]["thumbnail"], pid
