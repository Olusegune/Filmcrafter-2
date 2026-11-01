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
    assert out == {"pending": ["vertical_micro_drama"], "setup": {}}
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


# ---------------------------------------------------------------- the setup chosen on Home (length, episodes, extra presets)

def test_a_length_chosen_on_home_becomes_your_own_last_preset_and_wins_over_the_presets_before_it(film):
    d, rd = film
    out = P.run(d, "set_pending", {"stack": ["vertical_micro_drama", "punchy_social_cut"], "setup": {"length": 45, "episodes": 12}})
    assert out == {"pending": ["vertical_micro_drama", "punchy_social_cut", P.SETUP_ID], "setup": {"episodes": 12}}
    cat = P.catalog(rd)
    assert cat["pending"][-1] == P.SETUP_ID and cat["setup"] == {"episodes": 12}
    mine = next(p for p in cat["presets"] if p["id"] == P.SETUP_ID)
    assert mine["mine"] and mine["settings"] == {"duration_hint_s": 45}
    P.apply(rd, cat["pending"])
    assert P.load_state(rd)["duration_hint_s"] == 45                                              # not the 90 seconds the vertical preset aims for


def test_choosing_again_replaces_the_earlier_setup_and_no_length_leaves_no_leftover(tmp_path):
    d = new_film(tmp_path)
    P.run(d, "set_pending", {"stack": ["documentary"], "setup": {"length": 120}})
    assert P.SETUP_ID in P.load_state(d)["mine"]
    out = P.run(d, "set_pending", {"stack": ["documentary"], "setup": {}})
    assert out == {"pending": ["documentary"], "setup": {}} and P.SETUP_ID not in P.load_state(d)["mine"]


def test_a_bad_length_or_episode_count_is_refused_and_nothing_is_recorded(tmp_path):
    d = new_film(tmp_path)
    for bad in ({"length": 4}, {"length": 99999}, {"length": "long"}, {"length": True}, {"length": 1.5}, {"episodes": 0}, {"episodes": 61}, {"episodes": "ten"}):
        with pytest.raises(SystemExit):
            P.run(d, "set_pending", {"stack": ["documentary"], "setup": bad})
    assert P.load_state(d)["pending"] == [] and P.load_state(d)["setup"] == {}


def test_the_setup_preset_cannot_be_forged_through_the_list_and_old_records_still_load(tmp_path):
    d = new_film(tmp_path)
    out = P.run(d, "set_pending", {"stack": [P.SETUP_ID, "documentary"]})
    assert out["pending"] == ["documentary"]
    assert P.parse_state({"schema": 1, "setup": {"episodes": "x", "junk": 1}})["setup"] == {}
    assert P.parse_state({"schema": 1, "setup": "no"})["setup"] == {}
