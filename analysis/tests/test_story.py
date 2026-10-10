"""Films: a story-first project. Versions, lock, advice that never edits, and reading a screenplay."""
import json
import os

import pytest

from filmcrafter_engine import story

SCRIPT = """Title: Last Train

INT. KITCHEN - MORNING

Sarah pours tea. Her hands are not steady.

SARAH
(quietly)
He said he'd call.

JOHN (O.S.)
Did you say something?

EXT. PLATFORM - NIGHT

Rain on the roof. A train waits.

SARAH
I'm going.

JOHN
Then go.

CUT TO:

INT. TRAIN - NIGHT

Sarah sits. She looks at her phone. Nothing.
"""


def test_a_screenplay_is_read_into_scenes_places_and_speaking_characters():
    f = story.parse_screenplay(SCRIPT)
    headings = [s["heading"] for s in f["scenes"] if not s.get("implied")]
    assert headings == ["INT. KITCHEN - MORNING", "EXT. PLATFORM - NIGHT", "INT. TRAIN - NIGHT"]
    kitchen = next(s for s in f["scenes"] if "KITCHEN" in s["heading"])
    assert kitchen["int_ext"] == "INT" and kitchen["location"] == "KITCHEN" and kitchen["time"] == "MORNING"
    assert kitchen["characters"] == ["SARAH", "JOHN"]                        # (O.S.) is not part of the name
    names = [c["name"] for c in f["characters"]]
    assert set(names) == {"SARAH", "JOHN"} and names[0] == "SARAH"
    assert {l["name"] for l in f["locations"]} == {"KITCHEN", "PLATFORM", "TRAIN"}
    assert f["has_headings"] and f["seconds"] > 0


def test_a_transition_is_not_a_character():
    f = story.parse_screenplay(SCRIPT)
    assert "CUT TO:" not in [c["name"] for c in f["characters"]]


def test_a_script_without_headings_is_one_scene_and_says_so():
    f = story.parse_screenplay("A man walks into a bar.\n\nBARTENDER\nWhat'll it be?\n")
    assert len(f["scenes"]) == 1 and not f["has_headings"]
    a = story.analyze("screenplay", "A man walks into a bar.\n")
    assert any(r["id"] == "no-headings" for r in a["advice"])


def test_odd_input_never_throws():
    for text in ["", "\n\n\n", "INT.", "SARAH\n", "(((", "x" * 5000, "\x00\x01", "INT. A - B - C - D\n\nX\nY\n"]:
        story.analyze("screenplay", text)
    assert story.parse_outline("1. Opening\n2) Middle\n- End\nnot a line")[2]["heading"] == "End"


def test_creating_a_film_keeps_the_original_and_makes_version_one(tmp_path):
    src = tmp_path / "last train.fountain"
    src.write_text(SCRIPT, encoding="utf-8")
    r = story.create(str(tmp_path / "films"), "Last Train", "screenplay", SCRIPT, str(src))
    d = r["dir"]
    kept = os.path.join(d, "script", "original", "last train.fountain")
    assert os.path.isfile(kept) and open(kept, encoding="utf-8").read() == SCRIPT
    assert r["version"] == 1 and r["story"]["current"] == 1 and r["story"]["locked"] is None and r["story"]["as_is"] is None
    assert os.path.isfile(os.path.join(d, "Last Train.filmcrafter")) and story.is_film(d)
    assert len([s for s in r["found"]["scenes"] if not s.get("implied")]) == 3


def test_a_second_film_with_the_same_title_gets_its_own_folder(tmp_path):
    a = story.create(str(tmp_path), "Same", "idea", "A woman finds a door in her flat.")
    b = story.create(str(tmp_path), "Same", "idea", "A woman finds a door in her flat.")
    assert a["dir"] != b["dir"]


def test_an_empty_story_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="Add some story"):
        story.create(str(tmp_path), "X", "screenplay", "   \n")


def test_a_change_is_a_new_version_and_the_old_one_is_untouched(tmp_path):
    d = story.create(str(tmp_path), "T", "screenplay", SCRIPT)["dir"]
    before = open(story._vpath(d, 1), encoding="utf-8").read()
    r = story.add_version(d, SCRIPT.replace("He said he'd call.", "He never called."), "Sharper line")
    assert r["version"] == 2 and r["story"]["current"] == 2 and [v["version"] for v in r["versions"]] == [1, 2]
    assert open(story._vpath(d, 1), encoding="utf-8").read() == before
    assert story.status(d, 1)["text"] == SCRIPT and "never called" in r["text"]


def test_locking_pins_a_version_and_only_a_screenplay_can_be_locked(tmp_path):
    d = story.create(str(tmp_path), "T", "idea", "A woman finds a door in her flat.")["dir"]
    with pytest.raises(SystemExit, match="Only a screenplay"):
        story.lock(d)
    story.add_version(d, SCRIPT, "Written out", "screenplay")
    r = story.lock(d)
    assert r["story"]["locked"] == 2 and r["locked_here"] and r["story"]["lock_history"][0]["version"] == 2
    r = story.add_version(d, SCRIPT + "\nINT. HALL - DAY\n\nQuiet.\n", "Added a scene")
    assert r["story"]["locked"] == 2 and r["version"] == 3 and not r["locked_here"]      # the lock stays where it was
    assert story.status(d, 2)["locked_here"]
    r = story.lock(d)
    assert r["story"]["locked"] == 3 and [h["version"] for h in r["story"]["lock_history"]] == [2, 3]


def test_use_as_is_is_recorded_and_changes_nothing_in_the_script(tmp_path):
    d = story.create(str(tmp_path), "T", "screenplay", SCRIPT)["dir"]
    before = story.status(d)["text"]
    r = story.as_is(d)
    assert r["story"]["as_is"] == 1 and r["text"] == before


def test_advice_can_be_noted_or_dismissed_but_never_edits_the_script(tmp_path):
    d = story.create(str(tmp_path), "T", "screenplay", "A man walks.\n")["dir"]
    r = story.status(d)
    rid = r["advice"][0]["id"]
    text = r["text"]
    r = story.rec_set(d, 1, rid, "noted")
    assert next(x for x in r["advice"] if x["id"] == rid)["status"] == "noted" and r["text"] == text
    with pytest.raises(SystemExit):
        story.rec_set(d, 1, rid, "deleted")
    with pytest.raises(SystemExit, match="isn't in this version"):
        story.rec_set(d, 1, "nope", "dismissed")


def test_a_long_cast_in_a_short_script_is_pointed_out_as_production_load():
    names = ["ANA", "BEN", "CAL", "DEE", "EVE", "FAY"]
    text = "INT. ROOM - DAY\n\n" + "".join(f"{n}\nHello.\n\n" for n in names)
    a = story.analyze("screenplay", text)
    assert any(r["id"] == "cast-size" for r in a["advice"])


def test_a_logline_gets_a_next_step_not_a_verdict():
    a = story.analyze("idea", "A widow finds her husband's second phone.")
    assert a["rung"] == "logline" and any("synopsis" in r["text"] for r in a["advice"]) and a["scenes"] == []


def test_reading_files(tmp_path):
    t = tmp_path / "a.txt"
    t.write_bytes(b"INT. A - DAY\r\n\r\nX\r\n")
    r = story.read_document(str(t))
    assert "\r" not in r["text"] and r["name"] == "a.txt"
    bad = tmp_path / "a.exe"
    bad.write_bytes(b"MZ")
    with pytest.raises(SystemExit, match="Choose a text"):
        story.read_document(str(bad))
    empty = tmp_path / "e.md"
    empty.write_text("  \n", encoding="utf-8")
    with pytest.raises(SystemExit, match="No text"):
        story.read_document(str(empty))


def test_a_folder_that_is_not_a_film_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="isn't a FilmCrafter film"):
        story.status(str(tmp_path))
    assert not story.is_film(str(tmp_path))


def test_the_command_line_speaks_json(tmp_path, capsys):
    rc = story.main(["create", str(tmp_path), "--data", json.dumps({"title": "CLI", "kind": "idea", "text": "A lighthouse keeper hears a knock."})])
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0 and out["event"] == "result" and out["data"]["title"] == "CLI"
    rc = story.main(["status", str(tmp_path / "nope")])
    assert rc == 1 and json.loads(capsys.readouterr().out.strip().splitlines()[-1])["event"] == "error"


def test_simple_and_studio_are_the_same_film(tmp_path):
    d = story.create(str(tmp_path), "T", "screenplay", SCRIPT)["dir"]
    assert story.status(d)["mode"] == "simple"
    before = story.status(d)["text"]
    r = story.set_mode(d, "studio")
    assert r["mode"] == "studio" and r["text"] == before and r["story"] == story.status(d)["story"]
    assert story.set_mode(d, "simple")["mode"] == "simple"
    with pytest.raises(SystemExit, match="simple or studio"):
        story.set_mode(d, "expert")


TITLE_PAGE = 'SUMMIT SPROUT: "FROM SHAME TO LIVING\nWATER"\n\nANIMATED SHORT FILM - REVISED SCREENPLAY\n\nINT. SCHOOL - DAY\n\nChloe draws.\n\nCHLOE\nHello.\n'


def test_a_title_page_is_not_a_scene_or_a_character():
    f = story.parse_screenplay(TITLE_PAGE)
    assert [s["heading"] for s in f["scenes"]] == ["INT. SCHOOL - DAY"] and f["scenes"][0]["number"] == 1
    assert [c["name"] for c in f["characters"]] == ["CHLOE"]


def test_text_read_one_word_to_a_line_is_noticed_and_ordinary_text_is_not():
    broken = "\n\n".join(["INT.", "SCHOOL", "DAY"] * 40)
    assert story.looks_broken(broken) and story.words_per_line(broken) <= 1
    assert not story.looks_broken("INT. SCHOOL - DAY\n\nChloe sits alone with her sketchbook open on her lap.\n" * 80)
    assert not story.looks_broken("a\nb\nc")              # too little to say


def test_pdf_text_is_tidied_dashes_indents_and_blank_lines():
    raw = "        INT. SCHOOL � PLAYGROUND � DAY\r\n\r\n\r\n\r\n   carefully�not   tentatively\r\n"
    assert story.tidy_pdf_text(raw) == "INT. SCHOOL - PLAYGROUND - DAY\n\ncarefully-not tentatively"


def test_the_original_file_can_be_read_again_as_a_new_version(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("INT. ROOM - DAY\n\nA man waits.\n", encoding="utf-8")
    d = story.create(str(tmp_path / "films"), "T", "screenplay", "INT. ROOM - DAY\n\nA man waits.\n", str(src))["dir"]
    assert story.status(d)["original"] == "a.txt"
    with pytest.raises(SystemExit, match="same text"):
        story.reread_original(d)
    o = os.path.join(d, "script", "original", "a.txt")
    open(o, "w", encoding="utf-8").write("INT. ROOM - DAY\n\nA man waits by the window.\n")
    r = story.reread_original(d)
    assert r["version"] == 2 and "window" in r["text"] and r["versions"][1]["note"].startswith("Read from the original")
    assert "window" not in story.status(d, 1)["text"]                 # the first version is untouched


def test_a_film_made_from_typed_text_has_no_original_to_read_again(tmp_path):
    d = story.create(str(tmp_path), "T", "screenplay", "INT. ROOM - DAY\n\nA man waits.\n")["dir"]
    assert story.status(d)["original"] is None
    with pytest.raises(SystemExit, match="no original file"):
        story.reread_original(d)
