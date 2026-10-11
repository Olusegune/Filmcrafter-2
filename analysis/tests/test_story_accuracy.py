"""The right people, places and pictures reach each shot: a title page is not a speaker, an action shot names who is in it,
a model with few picture slots gives each person one before anyone gets a second, and a long file name keeps its extension.
(Found by a user's real screenplay: the all-capitals title became a character, shot 1 'Summit Sprout speaks', and the people with long picture names were never sent.)"""
import json
import os

from filmcrafter_engine import bible, library as L, make, render, shots, story
from filmcrafter_engine.safe import file_name

TITLED = """MY FILM: "THE LONG
NAME"

A SHORT FILM

INT. SCHOOL YARD - DAY

Chloe sits alone under an oak. A bell rings.

LILA
She eats the weirdest stuff.

Lila turns away, then glances at Chloe.

CHLOE
(quietly)
I know.

Ethan Park walks past with a ball. He nods at Ms. Wen.

MS. WEN
Walk, please.
"""


def test_a_title_in_capitals_before_the_first_scene_is_not_a_speaker():
    sc = shots.scene_blocks(TITLED)
    assert sc[0]["heading"].startswith("INT. SCHOOL YARD")
    assert not any(b["type"] == "dialogue" and "FILM" in b["speaker"] for s in sc for b in s["blocks"])
    p = story.parse_screenplay(TITLED)
    assert [c["name"] for c in p["characters"]] == ["LILA", "CHLOE", "MS. WEN"] or set(c["name"] for c in p["characters"]) == {"LILA", "CHLOE", "MS. WEN"}
    assert len(p["scenes"]) == 1


def test_a_script_with_no_scene_headings_still_finds_its_speakers():
    sc = shots.scene_blocks("MARA\nHello.\n\nJO\nHi.\n")
    assert [b["speaker"] for b in sc[0]["blocks"] if b["type"] == "dialogue"] == ["MARA", "JO"]
    assert len(story.parse_screenplay("MARA\nHello.\n\nJO\nHi.\n")["characters"]) == 2


def test_an_action_shot_names_the_people_the_action_names(tmp_path):
    d = story.create(str(tmp_path), "T", "screenplay", TITLED)["dir"]
    bible.seed(d)
    shots.breakdown(d)
    by_text = {}
    for sid in os.listdir(os.path.join(d, "shots")):
        f = os.path.join(d, "shots", sid, "contract.json")
        if os.path.isfile(f):
            c = json.load(open(f, encoding="utf-8"))
            by_text[c["action"][:12]] = [x["name"] for x in c["characters"]]
    assert by_text["Chloe sits a"] == ["CHLOE"]
    assert by_text["Lila turns a"] == ["LILA", "CHLOE"]                  # in the order the action names them
    assert by_text["Ethan Park w"] == ["MS. WEN"] or "MS. WEN" in by_text["Ethan Park w"]


def test_naming_people_in_action_ignores_crowds_and_partial_words():
    names = ["CHLOE", "FRIEND #1", "WOMAN #1", "TEACHER WEN", "SAMARITAN WOMAN"]
    assert shots._named_in("A woman waits. Friends laugh.", names) == []           # no number: not any one of them
    assert shots._named_in("Wen frowns at Chloe.", names) == ["TEACHER WEN", "CHLOE"]   # a last name only one person has
    assert shots._named_in("Chloeville is far away.", names) == []                  # a whole word only


def test_a_model_with_few_slots_gives_each_person_one_picture_first():
    refs = [{"label": "Lila", "names": ["Lila"], "media": "image"}] * 0 + [
        {"label": f"Lila {i}", "names": ["Lila"], "media": "image"} for i in range(3)] + [
        {"label": "Friend", "names": ["Friend"], "media": "image"}]
    kept, dropped = L.fit_to_model(refs, {"image": 2, "video": 0, "audio": 0})
    assert [r["label"] for r in kept] == ["Lila 0", "Friend"]                       # the first person's spare pictures do not crowd out the second person
    assert dropped == ["Lila 1", "Lila 2"]
    kept, _ = L.fit_to_model(refs, {"image": 9, "video": 0, "audio": 0})
    assert [r["label"] for r in kept] == [r["label"] for r in refs]               # nothing is reordered when everything fits


def test_a_long_file_name_keeps_its_extension_and_stays_distinct():
    a = "Untitled-20250928-004735-8950-undefinedx-a-very-long-name-from-a-chat-tool.png"
    b = "Untitled-20250928-004735-8950-undefinedx-a-very-long-name-from-a-chat-tool-2.png"
    fa, fb = file_name(a, 48), file_name(b, 48)
    assert fa.endswith(".png") and fb.endswith(".png") and len(fa) <= 48 and len(fb) <= 48
    assert fa != fb
    assert file_name("Chloe.png", 48) == "Chloe.png"
    assert file_name("a b/c?.JPG", 48) == "a_b_c_.JPG"
    assert file_name("noext", 48) == "noext" and file_name("", 48) == "x"


def test_pictures_with_long_names_reach_the_render_project_and_the_prompt(tmp_path):
    from PIL import Image
    d = story.create(str(tmp_path), "T", "screenplay", TITLED)["dir"]
    bible.seed(d)
    shots.breakdown(d)
    src = tmp_path / ("Untitled-20250928-004735-8950-" + "x" * 60 + ".png")
    Image.new("RGB", (32, 32), (120, 60, 40)).save(src)
    chloe = next(c for c in bible.load(d)["characters"] if c["name"].upper() == "CHLOE")
    bible.add_media(d, "character", chloe["id"], str(src))
    make.sync(d)
    rd = os.path.join(d, "render")
    files = os.listdir(os.path.join(rd, "assets", "refs"))
    assert files and all(f.endswith(".png") for f in files)                         # a long name used to lose its extension, and the picture was never sent
    p = json.load(open(os.path.join(rd, "project.json"), encoding="utf-8"))
    me = next(i for i in p["library"]["items"] if i["name"] == "Chloe")
    assert me["files"] and all(os.path.isfile(os.path.join(rd, f)) for f in me["files"])
    refs = L.reference_files(rd, p, {"id": "S01-02", "performers": ["Chloe"]}, 1)
    assert [r["names"] for r in refs] == [["Chloe"]]


def test_references_beyond_the_sixth_are_not_all_called_the_sixth():
    from filmcrafter_engine import render as R
    src = open(R.__file__, encoding="utf-8").read()
    assert '"seventh", "eighth", "ninth", "tenth"' in src and "ordinal[min(i, 5)]" not in src
