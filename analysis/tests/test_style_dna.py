"""Style DNA and the Cinematic Storybook 2.5D looks: a look described as structured parts, with the wording the render uses made from them (not a style name used as the prompt)."""
import json
import os

import pytest

from filmcrafter_engine import render as R, style_dna as S
from tests.test_stylebible import FILM_3D, restyle_request

IDS = list(S.VARIANTS)


@pytest.fixture(scope="module")
def lib():
    return R.styles()


def test_the_storybook_looks_exist_with_a_family_group_and_their_dna(lib):
    assert len(IDS) == 7 and IDS[0] == "cinematic-storybook-25d"
    for sid in IDS:
        s = lib[sid]
        assert s["family"] == "hybrid" and s["group"] == "Hybrid 2D/3D" and s["name"] and s["description"] and isinstance(s.get("dna"), dict)
    assert {lib[i]["dna"].get("inherits") for i in IDS[1:]} == {"cinematic-storybook-25d"}
    assert [lib[i]["name"] for i in IDS[1:]][0].startswith("Storybook")


def test_what_styles_json_holds_is_exactly_what_the_dna_compiles_to(lib):
    for e in S.entries():
        stored = lib[e["id"]]
        for k in ("name", "group", "description", "prompt", "avoid", "family", "figures", "figures_avoid"):
            assert stored[k] == e[k], (e["id"], k)
        assert stored["dna"] == e["dna"]


def test_a_variation_is_the_base_with_its_own_parts_over_it_and_nothing_else_lost(lib):
    base = S.full_dna(lib, "cinematic-storybook-25d")
    assert set(base) == set(S.FIELDS)
    fantasy = S.full_dna(lib, "fantasy-storybook")
    assert fantasy["palette"] != base["palette"] and "violet" in fantasy["palette"]
    assert fantasy["body_proportions"] == base["body_proportions"] and fantasy["facial_proportions"] == base["facial_proportions"]       # the people stay the same people in every variation
    assert set(fantasy) == set(S.FIELDS)


def test_the_wording_is_built_from_many_parts_of_the_dna_not_a_name(lib):
    p = lib["cinematic-storybook-25d"]["prompt"]
    for part in ("angular", "dry-brush", "palette", "shafts", "atmospheric perspective"):
        assert part in p
    assert p != lib["cinematic-storybook-25d"]["name"] and 300 < len(p) <= 900
    fig = lib["cinematic-storybook-25d"]["figures"]
    assert "small head on a long neck" in fig and "large readable eyes" in fig


def test_the_things_to_avoid_name_the_failures_the_owner_listed(lib):
    for sid in IDS:
        neg = lib[sid]["avoid"].lower()
        for w in ("waxy", "glossy", "photoreal", "face morphing", "text"):
            assert w in neg, (sid, w)
    assert "yellow" in lib["cinematic-storybook-25d"]["avoid"] and "bloom" in lib["cinematic-storybook-25d"]["avoid"]


def test_the_looks_describe_a_visual_grammar_and_name_no_character_film_or_person(lib):
    banned = ("pharaoh", "tutankhamun", "cleopatra", "ramses", "moses", "jesus", "disney", "pixar", "ghibli", "youtube", "documentary film")
    for sid in IDS:
        text = json.dumps(lib[sid]).lower()
        for w in banned:
            assert w not in text.replace("no pixar", ""), (sid, w)
    assert "not a historical reconstruction" in lib["historical-storybook"]["description"].lower() or "not a reconstruction" in lib["historical-storybook"]["description"].lower()


def test_a_film_in_the_look_has_its_wording_in_every_shot_and_a_restyled_shot_has_how_the_people_are_built():
    film = restyle_request({"style": "cinematic-storybook-25d"})
    assert "Cinematic Storybook 2.5D" in film and "dry-brush" in film
    shot = restyle_request({**FILM_3D, "shots": {"S06-02": "cinematic-storybook-25d"}})
    assert "small head on a long neck" in shot and "Whole-picture style" in shot
    assert "uniform yellow or golden tint" in shot                                  # the avoid list reaches the picture
    kept = restyle_request({**FILM_3D, "shots": {"S06-02": "cinematic-storybook-25d"}, "keep_cast": {"S06-02": True}})
    assert "small head on a long neck" not in kept


def test_every_part_is_text_inside_a_limit_and_a_bad_dna_is_cleaned():
    out = S.merged({"palette": "x" * 5000, "unknown": "y", "outline": 7, "lighting": "  soft   light "})
    assert set(out) == {"palette", "lighting"} and out["lighting"] == "soft light" and len(out["palette"]) <= S.MAX_FIELD * 2
    assert S.compile_dna("N", {})["prompt"].startswith("N:")
