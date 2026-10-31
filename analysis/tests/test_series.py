"""The series plan for a micro-drama: an editable scaffold made free and locally from an idea, that marks what is a suggestion and what is yours, reports plainly and never spends anything."""
import json
import os

import pytest

from filmcrafter_engine import series as S
from tests.test_performance_director import film  # noqa: F401  (a small film with a cast)

IDEA = "A young nurse discovers the hospital where she works is hiding a name. She cannot trust anyone."


def test_a_ten_episode_plan_of_ninety_seconds_is_made_from_one_idea_without_spending_anything(film, monkeypatch):
    f, rd = film
    import requests
    for fn in ("get", "post", "put", "request"):
        monkeypatch.setattr(requests, fn, lambda *a, **k: (_ for _ in ()).throw(AssertionError("a provider was called")))
    out = S.create(rd, IDEA)
    plan = out["plan"]
    assert len(plan["episodes"]) == 10 and all(e["seconds"] == 90 for e in plan["episodes"]) and plan["preset"] == "vertical_micro_drama"
    assert plan["season"]["logline"]["value"] == "A young nurse discovers the hospital where she works is hiding a name."
    assert "not a story written for you" in out["note"]
    for e in plan["episodes"]:
        assert e["hook"]["value"] and e["ending"]["value"] and all(e[k]["source"] == "scaffold" for k in ("hook", "escalation", "turning_point", "ending"))
        assert e["budget_usd"] is None


def test_the_shape_of_the_season_is_an_opening_a_turn_in_the_middle_a_low_point_and_a_close(film):
    f, rd = film
    roles = [e["role"] for e in S.create(rd, IDEA, 10)["plan"]["episodes"]]
    assert roles[0] == "opening" and roles[-1] == "close" and roles[-2] == "lowest point" and roles[4] == "turn" and roles[1] == "building" and roles[6] == "pressure"
    assert [S.role_of(n, 1) for n in (1,)] == ["opening"] and S.role_of(2, 2) == "close"


def test_the_people_and_places_already_in_the_film_are_read_and_the_hero_is_the_first_person(film):
    f, rd = film
    plan = S.create(rd, IDEA)["plan"]
    assert "Sarah" in plan["cast"] and plan["hero"] == plan["cast"][0] and plan["hero"] in plan["episodes"][0]["hook"]["value"]


def test_what_you_write_is_yours_and_a_suggestion_can_be_put_back(film):
    f, rd = film
    S.create(rd, IDEA)
    out = S.set_episode(rd, 2, {"hook": "Nadia hears her name on a call she was never meant to hear.", "title": "The call"})
    e = out["plan"]["episodes"][1]
    assert e["hook"] == {"value": "Nadia hears her name on a call she was never meant to hear.", "source": "you"} and e["title"] == "The call" and e["ending"]["source"] == "scaffold"
    back = S.reset_field(rd, 2, "hook")["plan"]["episodes"][1]
    assert back["hook"]["source"] == "scaffold" and "Nadia" not in back["hook"]["value"]


def test_changing_the_number_of_episodes_keeps_what_you_wrote_and_reshapes_the_rest(film):
    f, rd = film
    S.create(rd, IDEA, 10)
    S.set_episode(rd, 3, {"turning_point": "She finds the file.", "title": "The file"})
    out = S.resize(rd, 6)["plan"]["episodes"]
    assert len(out) == 6 and out[2]["turning_point"]["value"] == "She finds the file." and out[2]["title"] == "The file" and out[-1]["role"] == "close"
    up = S.resize(rd, 12)["plan"]["episodes"]
    assert len(up) == 12 and up[2]["turning_point"]["source"] == "you" and up[-1]["role"] == "close"
    for bad in (0, 61, "ten", True):
        with pytest.raises(SystemExit):
            S.resize(rd, bad)


def test_a_season_can_be_one_episode_and_lengths_are_advice_not_limits(film):
    f, rd = film
    out = S.create(rd, IDEA, 1, 45)["plan"]
    assert len(out["episodes"]) == 1 and out["episodes"][0]["seconds"] == 45 and out["episodes"][0]["role"] == "opening"
    assert S.set_episode(rd, 1, {"seconds": 150})["plan"]["episodes"][0]["seconds"] == 150
    assert S.set_episode(rd, 1, {"seconds": 5})["plan"]["episodes"][0]["seconds"] == 90                  # an impossible length falls back to the default, never to a crash


def test_the_report_says_what_is_still_a_suggestion_and_warns_about_formula_and_budgets(film):
    f, rd = film
    S.create(rd, IDEA, 5)
    r = S.report(rd)
    assert r["episodes"] == 5 and r["total_seconds"] == 450 and r["written"] == 0
    assert sum(1 for n in r["notes"] if n["level"] == "todo") == 5 and any("cliffhanger is a choice" in n["what"] for n in r["notes"]) is False       # not every episode is a cliffhanger by default
    for n in range(1, 6):
        S.set_episode(rd, n, {"cliffhanger": True, "hook": "H", "ending": "E", "budget_usd": 3})
    S.set_season(rd, {"season_budget_usd": 10})
    r = S.report(rd)
    assert any("cliffhanger is a choice" in n["what"] for n in r["notes"]) and any("over the season" in n["what"] for n in r["notes"]) and r["budget_total_usd"] == 15 and r["written"] == 5
    assert not any(n["level"] == "todo" for n in r["notes"])


def test_a_character_who_only_appears_late_in_your_writing_is_pointed_out(film):
    f, rd = film
    S.create(rd, IDEA, 4)
    S.set_episode(rd, 3, {"hook": "Sarah arrives at the hospital."})
    notes = S.report(rd)["notes"]
    assert any("Sarah first appears in your plan in episode 3" in n["what"] for n in notes)


def test_it_can_be_exported_as_a_document_that_marks_the_suggestions(film, tmp_path):
    f, rd = film
    S.create(rd, IDEA, 3)
    S.set_episode(rd, 1, {"hook": "A name on a chart."})
    out = S.export_markdown(rd, str(tmp_path / "plan.md"))
    text = open(out["path"], encoding="utf-8").read()
    assert text.startswith("# Series plan") and "A name on a chart." in text and "_(suggestion)_" in text and text.count("## ") == 3
    with pytest.raises(SystemExit, match="Choose a .md"):
        S.export_markdown(rd, str(tmp_path / "plan.txt"))


def test_a_bad_request_is_refused_and_a_plan_is_never_started_over_without_asking(film):
    f, rd = film
    for call in (lambda: S.create(rd, ""), lambda: S.create(rd, IDEA, 0), lambda: S.create(rd, IDEA, 10, 5), lambda: S.set_episode(rd, 1, {}), lambda: S.report(rd)):
        with pytest.raises(SystemExit):
            call()
    S.create(rd, IDEA)
    with pytest.raises(SystemExit, match="already has a series plan"):
        S.create(rd, IDEA)
    with pytest.raises(SystemExit, match="not in the plan"):
        S.set_episode(rd, 99, {"hook": "x"})
    with pytest.raises(SystemExit, match="not there"):
        S.reset_field(rd, 1, "title")


def test_a_plan_from_a_newer_version_is_refused_and_damaged_numbers_are_made_safe(film):
    f, rd = film
    S.create(rd, IDEA, 3)
    data = json.load(open(S._path(rd)))
    data["episodes"][0]["budget_usd"] = "lots"
    data["episodes"][1]["seconds"] = True
    data["episodes"].append("junk")
    json.dump(data, open(S._path(rd), "w"))
    eps = S.load(rd)["episodes"]
    assert eps[0]["budget_usd"] is None and eps[1]["seconds"] == 90 and len(eps) == 3
    json.dump({**data, "schema": 9}, open(S._path(rd), "w"))
    with pytest.raises(SystemExit, match="newer FilmCrafter"):
        S.get(rd)


def test_the_door_speaks_json_and_its_action_list_is_the_one_the_shell_must_match(film, capsys):
    f, rd = film
    assert S.main(["get", rd]) == 0 and json.loads(capsys.readouterr().out.splitlines()[-1])["data"]["exists"] is False
    assert S.main(["create", rd, "--data", json.dumps({"idea": IDEA, "episodes": 4})]) == 0
    assert S.main(["set_episode", rd, "--data", json.dumps({"n": "one"})]) == 1 and "which episode" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="Unknown"):
        S.run(rd, "explode", {})
    src = open(S.__file__, encoding="utf-8").read()
    for a in S.ACTIONS:
        assert f'"{a}"' in src.split("choices=")[1].split("]")[0]
