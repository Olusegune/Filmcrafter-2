"""The Production Bible, Cast and World: seeded from the story, then the person's."""
import json
import os

import pytest

from filmcrafter_engine import bible, story

SCRIPT = """INT. KITCHEN - MORNING

Sarah pours tea.

SARAH
He said he'd call.

JOHN
Did you say something?

EXT. PLATFORM - NIGHT

Rain.

SARAH
I'm going.
"""


@pytest.fixture
def film(tmp_path):
    return story.create(str(tmp_path), "T", "screenplay", SCRIPT)["dir"]


def test_seeding_adds_the_stories_characters_and_places(film):
    r = bible.seed(film)
    assert r["added"] == {"characters": 2, "environments": 2}
    v = bible.view(film)
    assert {c["name"] for c in v["characters"]} == {"Sarah", "John"}
    assert {e["name"] for e in v["environments"]} == {"Kitchen", "Platform"}
    sarah = next(c for c in v["characters"] if c["name"] == "Sarah")
    assert sarah["scenes"] == [1, 2] and sarah["states"][0]["label"] == "Default" and sarah["source"] == "story"
    kitchen = next(e for e in v["environments"] if e["name"] == "Kitchen")
    assert kitchen["states"][0]["label"] == "Morning" and set(kitchen["spatial"]) == set(bible.SPATIAL_FIELDS)


def test_seeding_again_changes_nothing_the_person_wrote(film):
    bible.seed(film)
    v = bible.view(film)
    sid = next(c["id"] for c in v["characters"] if c["name"] == "Sarah")
    bible.upsert(film, "character", {"id": sid, "physical": "Tall, grey eyes", "age": "28"})
    rev = bible.view(film)["rev"]
    r = bible.seed(film)
    assert r["added"] == {"characters": 0, "environments": 0}
    sarah = next(c for c in bible.view(film)["characters"] if c["id"] == sid)
    assert sarah["physical"] == "Tall, grey eyes" and sarah["age"] == "28"
    assert bible.view(film)["rev"] == rev


def test_a_new_version_of_the_story_brings_new_people_without_touching_the_old(film):
    bible.seed(film)
    story.add_version(film, SCRIPT + "\nINT. TRAIN - NIGHT\n\nCONDUCTOR\nTickets.\n")
    r = bible.seed(film)
    assert r["added"]["characters"] == 1 and {c["name"] for c in bible.view(film)["characters"]} == {"Sarah", "John", "Conductor"}


def test_a_removed_entry_is_kept_in_the_history(film):
    bible.seed(film)
    v = bible.view(film)
    jid = next(c["id"] for c in v["characters"] if c["name"] == "John")
    bible.remove(film, "character", jid)
    assert "John" not in {c["name"] for c in bible.view(film)["characters"]}
    hist = os.listdir(os.path.join(film, "bible", "history"))
    assert hist and any("John" in open(os.path.join(film, "bible", "history", h), encoding="utf-8").read() for h in hist)


def test_one_character_can_have_related_states(film):
    bible.seed(film)
    sid = next(c["id"] for c in bible.view(film)["characters"] if c["name"] == "Sarah")
    bible.add_state(film, "character", sid, "Age 8", "Hair in plaits", age="8")
    r = bible.add_state(film, "character", sid, "Age 70", age="70")
    sarah = next(c for c in r["characters"] if c["id"] == sid)
    assert [s["label"] for s in sarah["states"]] == ["Default", "Age 8", "Age 70"] and sarah["states"][1]["age"] == "8"
    assert len([c for c in r["characters"] if c["name"] == "Sarah"]) == 1                   # states of one character, not three characters
    with pytest.raises(SystemExit, match="already a state"):
        bible.add_state(film, "character", sid, "age 8")
    with pytest.raises(SystemExit, match="Name the state"):
        bible.add_state(film, "character", sid, "  ")
    bible.remove_state(film, "character", sid, "s2")
    with pytest.raises(SystemExit, match="at least one"):
        for st in [s["id"] for s in next(c for c in bible.view(film)["characters"] if c["id"] == sid)["states"]]:
            bible.remove_state(film, "character", sid, st)


def test_wardrobe_and_places_and_props(film):
    bible.seed(film)
    v = bible.view(film)
    sid = next(c["id"] for c in v["characters"] if c["name"] == "Sarah")
    r = bible.add_wardrobe(film, sid, "Red coat", "Wool, torn pocket")
    assert next(c for c in r["characters"] if c["id"] == sid)["wardrobe"][0]["name"] == "Red coat"
    eid = next(e["id"] for e in v["environments"] if e["name"] == "Kitchen")
    r = bible.upsert(film, "environment", {"id": eid, "spatial": {"doors": "One, left of the stove", "bogus": "x"}})
    assert next(e for e in r["environments"] if e["id"] == eid)["spatial"]["doors"] == "One, left of the stove"
    assert "bogus" not in next(e for e in r["environments"] if e["id"] == eid)["spatial"]
    r = bible.upsert(film, "prop", {"name": "The letter", "notes": "Cream envelope"})
    assert r["props"][0]["name"] == "The letter" and r["id"].startswith("p_")
    with pytest.raises(SystemExit, match="Give it a name"):
        bible.upsert(film, "prop", {"name": "  "})


def test_rules_philosophy_and_style(film):
    r = bible.update_rules(film, {"rules": {"world": "A town where it always rains", "evil": "x"}, "philosophy": {"lighting": "Motivated, low key"},
                                  "style": {"lane": "painterly animation", "notes": "Oil paint look", "references": ["a", "b"]}})
    assert r["rules"]["world"].startswith("A town") and "evil" not in r["rules"] and r["philosophy"]["lighting"] == "Motivated, low key"
    assert r["style"]["lane"] == "painterly animation" and r["style"]["references"] == ["a", "b"]
    assert "Choose a visual style." not in r["need"]
    with pytest.raises(SystemExit, match="listed visual styles"):
        bible.update_rules(film, {"style": {"lane": "whatever"}})


def test_text_is_trimmed_and_limited(film):
    r = bible.upsert(film, "character", {"name": "  " + "x" * 500 + "  ", "notes": "y" * 9000})
    c = r["characters"][0]
    assert len(c["name"]) == 80 and len(c["notes"]) == bible.LIMIT


def test_bringing_a_picture_copies_it_in_and_leaves_the_original(film, tmp_path):
    bible.seed(film)
    sid = next(c["id"] for c in bible.view(film)["characters"] if c["name"] == "Sarah")
    pic = tmp_path / "sarah front.png"
    pic.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 20)
    r = bible.add_media(film, "character", sid, str(pic), "Front view", "front")
    m = next(c for c in r["characters"] if c["id"] == sid)["media"][0]
    assert m["kind"] == "front" and m["path"].startswith(f"cast/{sid}/") and os.path.isfile(os.path.join(film, m["path"]))
    assert pic.exists()
    r = bible.add_media(film, "character", sid, str(pic))
    assert len(next(c for c in r["characters"] if c["id"] == sid)["media"]) == 2        # the same name gets its own file
    bad = tmp_path / "x.exe"
    bad.write_bytes(b"MZ")
    with pytest.raises(SystemExit, match="Choose a PNG"):
        bible.add_media(film, "character", sid, str(bad))
    r = bible.remove_media(film, "character", sid, m["path"])
    assert len(next(c for c in r["characters"] if c["id"] == sid)["media"]) == 1 and os.path.isfile(os.path.join(film, m["path"]))


def test_ids_from_outside_are_never_paths(film):
    with pytest.raises(SystemExit, match="not valid"):
        bible.upsert(film, "character", {"id": "../../evil", "name": "x"})
    with pytest.raises(SystemExit, match="not valid"):
        bible.add_media(film, "character", "..\\x", "a.png")


def test_the_history_keeps_the_newest_copies(film):
    for i in range(40):
        bible.update_rules(film, {"rules": {"world": f"w{i}"}})
    assert len(os.listdir(os.path.join(film, "bible", "history"))) == bible.KEEP_HISTORY


def test_a_folder_that_is_not_a_film_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="isn't a FilmCrafter film"):
        bible.view(str(tmp_path))


def test_the_command_line_speaks_json(film, capsys):
    rc = bible.main(["seed", film])
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0 and out["event"] == "result" and out["data"]["added"]["characters"] == 2
