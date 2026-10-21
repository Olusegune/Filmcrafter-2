"""Action choreography: plans are valid, deterministic, safe for a video model, never touch existing shots, and are applied once."""
import json
import os

import pytest

from filmcrafter_engine import bible, choreography as C, shots as S, story

SCRIPT = ("INT. WAREHOUSE - NIGHT\n\nMara and Dov face off among the crates.\n\nMARA\nGive it back.\n\nDOV\nCome and get it.\n\n"
          "EXT. YARD - DAY\n\nChildren play in the schoolyard.\n")


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    S.breakdown(d)
    return d


def ask(**kw):
    base = {"type": "fight", "scene": 1, "side_a": ["Mara"], "side_b": ["Dov"], "beats": 8, "outcome": "a_wins", "intensity": "grounded"}
    base.update(kw)
    return base


def bytes_of(film):
    return {sid: open(S._cpath(film, sid), "rb").read() for sid in S._index(film)["order"]}


def test_the_kinds_of_action_are_listed_with_advice():
    t = C.types()
    assert {x["id"] for x in t["types"]} == {"fight", "armed", "chase", "vehicle", "sport"}
    assert all(x["blurb"] and x["good_for"] for x in t["types"]) and t["advice"] and {o["id"] for o in t["outcomes"]} == set(C.OUTCOMES)


@pytest.mark.parametrize("kind", list(C.TYPES))
@pytest.mark.parametrize("outcome", list(C.OUTCOMES))
def test_every_plan_is_valid_for_every_kind_and_outcome(film, kind, outcome):
    p = C.generate(film, ask(type=kind, outcome=outcome, beats=9))
    assert len(p["beats"]) == 9 and p["beats"][0]["kind"] == "establish" and p["beats"][-1]["kind"] == "aftermath"
    for b in p["beats"]:
        assert b["framing"] in S.FRAMING and b["movement"] in S.MOVEMENT and b["angle"] in S.ANGLE and b["lens"] in S.LENS, b
        assert 1.5 <= b["seconds"] <= 6.0 and b["text"] and len(b["text"]) < C.TEXT_MAX and "{" not in b["text"] and "}" not in b["text"]
    assert p["seconds"] == round(sum(b["seconds"] for b in p["beats"]), 1)


def test_the_same_request_gives_the_same_plan_and_a_variation_gives_another(film):
    a, b = C.generate(film, ask()), C.generate(film, ask())
    assert [x["text"] for x in a["beats"]] == [x["text"] for x in b["beats"]] and a["id"] != b["id"]
    c = C.generate(film, ask(variation=1))
    assert [x["text"] for x in a["beats"]] != [x["text"] for x in c["beats"]]


def test_a_contact_is_never_two_action_shots_in_a_row_without_a_cut_to_a_reaction_or_a_detail(film):
    for kind in ("fight", "armed"):
        for n in range(4, 15):
            p = C.generate(film, ask(type=kind, beats=n))
            mids = [b for b in p["beats"][1:-1]]
            run = 0
            for b in mids:
                run = run + 1 if b["kind"] == "action" else 0
                assert run <= 3, (kind, n, [x["kind"] for x in mids])


def test_the_momentum_ends_with_the_winner_and_the_closing_line_names_the_result(film):
    a = C.generate(film, ask(outcome="a_wins"))
    b = C.generate(film, ask(outcome="b_wins"))
    assert a["beats"][-1]["momentum"] == "A" and b["beats"][-1]["momentum"] == "B"
    assert a["beats"][0]["momentum"] == "even"
    assert "Mara" in a["beats"][-1]["text"] and "Dov" in b["beats"][-1]["text"]


def test_who_was_hurt_is_carried_forward_and_only_the_person_hit(film):
    p = C.generate(film, ask(beats=12))
    first_land = next(i for i, b in enumerate(p["beats"]) if b["phase"] == "land")
    assert not any(b["carrying"] for b in p["beats"][:first_land])
    later = [b for b in p["beats"][first_land + 1:] if b["carrying"]]
    assert later and all("has" in b["carrying"] for b in later)


def test_the_people_are_checked(film):
    with pytest.raises(SystemExit, match="who is in the action"):
        C.generate(film, ask(side_a=[]))
    with pytest.raises(SystemExit, match="other side"):
        C.generate(film, ask(side_b=[]))
    with pytest.raises(SystemExit, match="one side"):
        C.generate(film, ask(side_b=["Mara"]))
    C.generate(film, ask(type="sport", side_b=[]))                           # a sports moment needs no opponent
    with pytest.raises(SystemExit):
        C.generate(film, ask(type="dance"))
    with pytest.raises(SystemExit, match="isn't in the film"):
        C.generate(film, ask(scene=9))


def test_the_beat_count_is_kept_in_range(film):
    assert len(C.generate(film, ask(beats=1))["beats"]) == C.MIN_BEATS
    assert len(C.generate(film, ask(beats=99))["beats"]) == C.MAX_BEATS


def test_editing_a_beat_keeps_the_rest_valid(film):
    p = C.generate(film, ask())
    q = C.update(film, p["id"], {"beats": [{"n": 2, "text": "Mara kicks the crate open.", "seconds": 3.5, "framing": "close-up"}], "geography": "Mara on the left."})
    assert q["beats"][1]["text"] == "Mara kicks the crate open." and q["beats"][1]["framing"] == "close-up" and q["geography"] == "Mara on the left."
    assert q["seconds"] == round(sum(b["seconds"] for b in q["beats"]), 1)
    with pytest.raises(SystemExit, match="framing"):
        C.update(film, p["id"], {"beats": [{"n": 2, "framing": "arty"}]})
    with pytest.raises(SystemExit, match="number of seconds"):
        C.update(film, p["id"], {"beats": [{"n": 2, "seconds": "long"}]})
    assert C.update(film, p["id"], {"beats": [{"n": 2, "seconds": 99}]})["beats"][1]["seconds"] == 8.0


def test_applying_adds_new_shots_after_the_scene_and_changes_no_existing_shot(film):
    S.set_fields(film, S._index(film)["order"][0], {"action": "My own words."})                 # an edited shot
    before = bytes_of(film)
    n_before = len(before)
    p = C.generate(film, ask(beats=6))
    r = C.apply(film, p["id"])
    assert len(r["added"]) == 6 and len(S._index(film)["order"]) == n_before + 6
    after = bytes_of(film)
    assert all(after[sid] == raw for sid, raw in before.items()), "no existing shot changed"
    order = S._index(film)["order"]
    scene1 = [sid for sid in order if S._contract(film, sid)["scene"] == 1]
    assert scene1[-6:] == r["added"], "the new shots sit at the end of the scene, in order"
    c = S._contract(film, r["added"][2])
    assert c["edited"] and c["action"] == p["beats"][2]["text"] and c["camera"]["framing"] == p["beats"][2]["framing"] and c["generation"]["duration"] == p["beats"][2]["seconds"]
    assert "Mara" in json.dumps(c["characters"]) and p["geography"] in c["blocking"] and "Action choreography" in c["generation"]["notes"]
    with pytest.raises(SystemExit, match="already in the film"):
        C.apply(film, p["id"])
    with pytest.raises(SystemExit, match="already been added"):
        C.update(film, p["id"], {"geography": "x"})


def test_applying_after_a_chosen_shot_puts_them_there(film):
    order = S._index(film)["order"]
    scene1 = [sid for sid in order if S._contract(film, sid)["scene"] == 1]
    p = C.generate(film, ask(beats=4))
    r = C.apply(film, p["id"], scene1[0])
    new_order = S._index(film)["order"]
    i = new_order.index(scene1[0])
    assert new_order[i + 1:i + 5] == r["added"]


def test_plans_are_listed_and_removing_moves_them_aside(film):
    p = C.generate(film, ask())
    q = C.generate(film, ask(type="chase", outcome="draw"))
    assert {x["id"] for x in C.list_plans(film)["plans"]} == {p["id"], q["id"]}
    C.remove(film, p["id"])
    assert {x["id"] for x in C.list_plans(film)["plans"]} == {q["id"]}
    assert os.listdir(os.path.join(film, "choreography", "_removed"))
    with pytest.raises(SystemExit):
        C.load(film, p["id"])
    with pytest.raises(SystemExit, match="not valid"):
        C.load(film, "../../etc/passwd")


def test_nothing_in_the_module_can_spend_or_send_and_it_keeps_to_what_a_general_film_shows():
    src = open(C.__file__, encoding="utf-8").read()
    for bad in ("import requests", "urllib", "socket", "subprocess", "paidops", "api_key"):
        assert bad not in src, bad
    text = " ".join(" ".join(v) for t in C.VERBS.values() for v in t.values()).lower() + " ".join(C.HURTS).lower()
    for gore in ("blood", "gore", "entrails", "severed", "decapit", "brains"):
        assert gore not in text, gore
