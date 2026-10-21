"""Which of a character's sheet pictures go to which shot: identity pictures to every shot, expression, pose and outfit pictures only to the shots they fit."""
import os

import pytest
from PIL import Image

from filmcrafter_engine import bible, library, make, shots as S, sheetmatch as SM, story

SCRIPT = ("INT. KITCHEN - NIGHT\n\nSarah sits at the table, worried. She wrings the cloth in her hands.\n\nSARAH\n(trembling)\nHe said he would call.\n\n"
          "EXT. YARD - DAY\n\nSarah runs across the yard in her red coat, furious.\n")


def m(kind, label, path=None):
    return {"kind": kind, "label": label, "path": path or f"cast/s/{label.replace(' ', '_')}.png"}


def test_concepts_understand_near_words():
    assert "worried" in SM.concepts("She is anxious and uneasy")
    assert SM.concepts("A calm, composed face") == {"calm"}
    assert "running" in SM.concepts("he sprints across") and "sitting" in SM.concepts("seated at the table")
    assert SM.concepts("the kettle boils") == set()


def test_identity_pictures_come_first_and_moment_pictures_only_fill_free_places():
    media = [m("expression", "worried"), m("side", "side"), m("master", "turnaround"), m("front", "front"), m("back", "back"), m("three-quarter", "tq"), m("pose", "sitting")]
    ident = SM.identity(media)
    assert [x["kind"] for x in ident] == ["master", "front", "three-quarter", "side"]          # four, the best views; back and the moment pictures wait
    few = [m("front", "front"), m("expression", "worried"), m("pose", "sitting")]
    got = SM.identity(few)
    assert [x["kind"] for x in got] == ["front"], "pictures that say what moment they show are kept for that moment, not wasted as a face"
    assert [x["label"] for x in SM.identity([m("front", "front"), m("expression", "face 1")])] == ["front", "face 1"], "an unreadable expression picture still helps as a face when there is room"


def test_a_moment_picture_goes_only_to_a_shot_that_fits():
    media = [m("expression", "worried"), m("expression", "furious"), m("pose", "sitting"), m("wardrobe", "red coat")]
    cands = SM.moment_candidates(media)
    kitchen = "Sarah sits at the table. She is anxious, wringing a cloth."
    yard = "Sarah sprints across the yard in her red coat, enraged."
    k = {c["media"]["label"] for c in SM.pick_for_shot(cands, kitchen)}
    y = {c["media"]["label"] for c in SM.pick_for_shot(cands, yard)}
    assert k == {"worried", "sitting"}
    assert y == {"furious", "red coat"}
    assert SM.pick_for_shot(cands, "The kettle boils on the stove.") == []
    one = SM.pick_for_shot(SM.moment_candidates([m("expression", "worried"), m("expression", "anxious"), m("expression", "scared")]), kitchen)
    assert len(one) == 1, "at most one expression picture per shot"


def test_an_outfit_needs_its_own_words_not_one_shared_word():
    cands = SM.moment_candidates([m("wardrobe", "red coat")])
    assert SM.pick_for_shot(cands, "She wears a red dress") == []
    assert SM.pick_for_shot(cands, "She pulls her red coat tight")


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    S.breakdown(d)
    return d


def pic(path, color):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (200, 120), color).save(path)
    return path


def test_sync_sends_identity_to_all_and_moments_only_where_they_fit(film, tmp_path):
    ids = [c["id"] for c in make._contracts(film)]
    sarah = next(c for c in bible.load(film)["characters"] if c["name"].lower() == "sarah")
    for i, (kind, label, colour) in enumerate([("front", "front", (1, 1, 1)), ("side", "side", (2, 2, 2)), ("expression", "worried", (3, 3, 3)), ("expression", "furious", (4, 4, 4)),
                                               ("pose", "sitting", (5, 5, 5)), ("wardrobe", "red coat", (6, 6, 6))]):
        bible.add_media(film, "character", sarah["id"], pic(str(tmp_path / "in" / f"{label.replace(' ', '_')}.png"), colour), label=label, media_kind=kind)
    r = make.sync(film)
    rd = make.render_dir(film)
    assert r["moment_references"] >= 3
    p, lib = library.load(rd)
    by = {i["id"]: i for i in lib["items"]}
    ident = by["fc-" + sarah["id"]]
    assert len(ident["files"]) == 2, "identity: the front and the side"
    moments = [i for i in lib["items"] if i["id"].startswith("fc-sm-")]
    names = {i["name"] for i in moments}
    assert any("worried" in n for n in names) and any("furious" in n for n in names) and any("sitting" in n for n in names) and any("red_coat" in n or "red coat" in n for n in names)
    shots_assign = lib["assign"].get("shots") or {}
    kitchen = ids[0]
    yard = ids[-1]
    def attached(sid):
        return " ".join(by[i]["name"] for i in (shots_assign.get(sid) or {}).get("add", []) if i in by)
    assert "worried" in attached(kitchen) and "furious" not in attached(kitchen)
    assert "furious" in attached(yard) and "worried" not in attached(yard)
    # changing the words moves the picture: a rebuild never leaves a stale one behind
    before = {i["id"] for i in moments}
    make.sync(film)
    p, lib = library.load(rd)
    assert {i["id"] for i in lib["items"] if i["id"].startswith("fc-sm-")} == before


def test_a_film_with_no_sheets_is_unchanged(film):
    r = make.sync(film)
    assert r["moment_references"] == 0
