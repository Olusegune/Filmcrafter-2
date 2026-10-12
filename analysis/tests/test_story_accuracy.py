"""The right people, places and pictures reach each shot: a title page is not a speaker, an action shot names who is in it,
a model with few picture slots gives each person one before anyone gets a second, and a long file name keeps its extension.
(Found by a user's real screenplay: the all-capitals title became a character, shot 1 'Summit Sprout speaks', and the people with long picture names were never sent.)"""
import json
import pytest
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


# ---------------------------------------------------------------- the usual ways screenplays are typed

def _scenes_and_speakers(t):
    p = story.parse_screenplay(t)
    sc = shots.scene_blocks(t)
    return [s["heading"] for s in p["scenes"]], [c["name"] for c in p["characters"]], [b["speaker"] for s in sc for b in s["blocks"] if b["type"] == "dialogue"]


def test_numbered_scene_headings_are_scenes():
    heads, chars, speakers = _scenes_and_speakers("1  INT. KITCHEN - DAY  1\n\nSarah cooks.\n\nSARAH\nHi.\n\n2A  EXT. YARD - DAY  2A\n\nBirds.\n")
    assert heads == ["INT. KITCHEN - DAY", "EXT. YARD - DAY"] and chars == ["SARAH"] and speakers == ["SARAH"]


def test_a_number_that_is_part_of_the_place_is_kept():
    heads, _, _ = _scenes_and_speakers("EXT. HIGHWAY 61 - DAY\n\nCars.\n\n3  INT. DINER 2 - NIGHT  3\n\nPie.\n")
    assert heads == ["EXT. HIGHWAY 61 - DAY", "INT. DINER 2 - NIGHT"]
    assert story.parse_screenplay("EXT. HIGHWAY 61 - DAY\n\nCars.\n")["scenes"][0]["location"] == "HIGHWAY 61"


def test_a_forced_character_cue_is_a_speaker():
    _, chars, speakers = _scenes_and_speakers(".SNOWY FIELD\n\nWind.\n\n@mcCoy\nHello.\n")
    assert chars == ["mcCoy"] and speakers == ["mcCoy"]


def test_title_page_with_author_and_contact_lines_is_not_a_scene_or_a_person():
    t = 'THE LONG NIGHT\n\nWritten by\nA. Writer\n\nDraft 2\nContact: a@b.com\n\nFADE IN:\n\nINT. KITCHEN - NIGHT\n\nSARAH stands at the sink.\n\nSARAH\nWho is there?\n\nJOHN (O.S.)\nIt is me.\n'
    heads, chars, speakers = _scenes_and_speakers(t)
    assert heads == ["INT. KITCHEN - NIGHT"] and set(chars) == {"SARAH", "JOHN"} and speakers == ["SARAH", "JOHN"]


def test_voice_over_and_contd_notes_do_not_make_new_people():
    _, chars, speakers = _scenes_and_speakers("INT. CAR - NIGHT\n\nA car moves.\n\nSARAH (V.O.)\nI left.\n\nSARAH (CONT'D)\nI never came back.\n\nJOHN (O.S.)\nWait!\n")
    assert chars == ["SARAH", "JOHN"] and speakers == ["SARAH", "SARAH", "JOHN"]


def test_a_pronoun_after_a_line_of_dialogue_is_about_the_speaker(tmp_path):
    t = "INT. YARD - DAY\n\nA schoolyard.\n\nLILA\nIt looked weird.\n\nShe wrinkles her nose.\n\nChloe keeps drawing.\n\nShe does not look up.\n\nCHLOE\nI heard you.\n"
    d = story.create(str(tmp_path), "T", "screenplay", t)["dir"]
    bible.seed(d)
    shots.breakdown(d)
    seen = {}
    for sid in os.listdir(os.path.join(d, "shots")):
        f = os.path.join(d, "shots", sid, "contract.json")
        if os.path.isfile(f):
            c = json.load(open(f, encoding="utf-8"))
            seen[c["action"][:8]] = [x["name"] for x in c["characters"]]
    assert seen["She wrin"] == ["LILA"]
    assert seen["Chloe ke"] == ["CHLOE"]
    assert seen["She does"] == ["CHLOE"]                                   # the last person the story named


# ---------------------------------------------------------------- props: the ones the cast list holds reach only the shots that show them

PROP_SCRIPT = "INT. KITCHEN - DAY\n\nSarah pours tea.\n\nSARAH\nHe said he would call.\n\nA letter lies by the sink. Sarah picks up the letter.\n\nJOHN\nWho is it from?\n\nThe kettle whistles.\n"


def _film_with_props(tmp_path):
    from PIL import Image
    d = story.create(str(tmp_path / "f"), "T", "screenplay", PROP_SCRIPT)["dir"]
    bible.seed(d)
    for name in ("Letter", "Kettle", "Spare Key"):
        bible.upsert(d, "prop", {"name": name, "description": f"the {name.lower()}"})
    for p in bible.load(d)["props"]:
        img = tmp_path / f"{p['id']}.png"
        Image.new("RGB", (16, 16), (200, 100, 50)).save(img)
        bible.add_media(d, "prop", p["id"], str(img))
    shots.breakdown(d)
    return d


def test_the_props_a_shots_action_names_are_in_the_shot(tmp_path):
    d = _film_with_props(tmp_path)
    got = {}
    for sid in os.listdir(os.path.join(d, "shots")):
        f = os.path.join(d, "shots", sid, "contract.json")
        if os.path.isfile(f):
            c = json.load(open(f, encoding="utf-8"))
            got[c["action"][:10]] = [x["name"] for x in c["props"]]
    assert got["A letter l"] == ["Letter"] and got["The kettle"] == ["Kettle"] and got["Sarah pour"] == []
    assert all(x["prop_id"] for sid in os.listdir(os.path.join(d, "shots")) if os.path.isfile(os.path.join(d, "shots", sid, "contract.json"))
               for x in json.load(open(os.path.join(d, "shots", sid, "contract.json"), encoding="utf-8"))["props"])        # linked to the cast list


def test_naming_props_finds_whole_names_and_plurals_only():
    assert shots._props_in("She holds two letters and a Spare Key.", ["Letter", "Spare Key", "Key"]) == ["Letter", "Spare Key", "Key"]
    assert shots._props_in("The keyboard clatters.", ["Key"]) == [] and shots._props_in("Nothing here.", ["Letter"]) == []
    assert shots._props_in("A letter.", ["", "ab"]) == []


def test_a_prop_picture_goes_only_to_the_shots_that_name_it_and_the_prompt_says_so(tmp_path):
    d = _film_with_props(tmp_path)
    make.sync(d)
    rd = os.path.join(d, "render")
    plan = json.load(open(os.path.join(rd, "production.json"), encoding="utf-8"))
    by = {s["visual_prompt"][:10]: s["id"] for sc in plan["scenes"] for s in sc["shots"]}
    from filmcrafter_engine import library as L
    pj = json.load(open(os.path.join(rd, "project.json"), encoding="utf-8"))
    def names(sid):
        sh, sc = render._shot(plan, sid)
        return [r["label"] for r in L.reference_files(rd, pj, sh, sc["number"]) if "prop reference" in r["label"]]
    assert any("Letter" in x for x in names(by["A letter l"])) and not any("Kettle" in x for x in names(by["A letter l"]))
    assert not any("Letter" in x or "Kettle" in x for x in names(by["Sarah pour"]))        # not sent to a shot that does not show it
    assert any("Kettle" in x for x in names(by["The kettle"]))
    assert "Props: Letter." in next(s["visual_prompt"] for sc in plan["scenes"] for s in sc["shots"] if s["id"] == by["A letter l"])


def test_a_prop_no_shot_names_still_goes_everywhere_as_before(tmp_path):
    d = _film_with_props(tmp_path)
    make.sync(d)
    rd = os.path.join(d, "render")
    plan = json.load(open(os.path.join(rd, "production.json"), encoding="utf-8"))
    pj = json.load(open(os.path.join(rd, "project.json"), encoding="utf-8"))
    from filmcrafter_engine import library as L
    sid = plan["scenes"][0]["shots"][0]["id"]
    sh, sc = render._shot(plan, sid)
    assert any("Spare Key" in r["label"] for r in L.reference_files(rd, pj, sh, sc["number"]))


# ---------------------------------------------------------------- a long Word screenplay is read whole

def test_a_word_screenplay_is_read_in_full(tmp_path):
    import zipfile
    p = tmp_path / "long.docx"
    paras = "".join(f"<w:p><w:r><w:t>Line {i} of the screenplay with some words in it.</w:t></w:r></w:p>" for i in range(600))
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document xmlns:w="x"><w:body>{paras}</w:body></w:document>')
    r = story.read_document(str(p))
    assert len(r["text"]) > 29000 and "Line 599 of the screenplay" in r["text"]          # it used to stop after 6,000 characters, and said nothing
    with pytest.raises(SystemExit, match="Word file"):
        (tmp_path / "bad.docx").write_bytes(b"not a zip")
        story.read_document(str(tmp_path / "bad.docx"))


# ---------------------------------------------------------------- "two friends in tow": the scene's numbered friends are in the shot

def test_plural_friends_are_the_scenes_numbered_friends():
    group = ["FRIEND #1", "FRIEND #2"]
    assert shots._named_in("The camera finds Lila approaching with two friends in tow.", ["LILA", "FRIEND #1", "FRIEND #2"], group) == ["LILA", "FRIEND #1", "FRIEND #2"]
    assert shots._named_in("Her friend waves.", ["LILA", "FRIEND #1"], ["FRIEND #1"]) == []                        # one friend, unnumbered: not guessed
    assert shots._named_in("Friend #2 laughs.", ["FRIEND #1", "FRIEND #2"], ["FRIEND #1", "FRIEND #2"]) == ["FRIEND #2"]
    assert shots._named_in("Friends cheer.", ["FRIEND #1"], []) == []                                              # not in this scene's group


def test_a_shot_of_lila_and_her_friends_has_all_three(tmp_path):
    script = "INT. YARD - DAY\n\nA schoolyard.\n\nThe camera finds Lila approaching with two friends in tow.\n\nLILA\nHi.\n\nFRIEND #1\nHey.\n\nFRIEND #2\nHello.\n"
    d = story.create(str(tmp_path / "f"), "T", "screenplay", script)["dir"]
    bible.seed(d)
    shots.breakdown(d)
    for sid in os.listdir(os.path.join(d, "shots")):
        f = os.path.join(d, "shots", sid, "contract.json")
        if os.path.isfile(f):
            c = json.load(open(f, encoding="utf-8"))
            if c["action"].startswith("The camera finds"):
                assert [x["name"] for x in c["characters"]] == ["LILA", "FRIEND #1", "FRIEND #2"]
                return
    raise AssertionError("the shot was not made")


# ---------------------------------------------------------------- the previous shot is a reference only for the people it shares

def test_the_previous_shots_picture_is_not_sent_to_a_shot_of_other_people(tmp_path):
    from filmcrafter_engine import continuity as CO
    d = tmp_path / "p"
    (d / "gen").mkdir(parents=True)
    (d / "gen" / "kf.png").write_bytes(b"x")
    (d / "keyframes.json").write_text(json.dumps({"production": {"S01-02": "project:gen/kf.png"}}))
    (d / "continuity.json").write_text(json.dumps({"scenes": {"1": {"enabled": True}}}))
    plan = {"scenes": [{"number": 1, "shots": [{"id": "S01-02", "start": 0, "performers": ["Chloe"]}, {"id": "S01-03", "start": 3, "performers": ["Lila", "Friend #1"]},
                                               {"id": "S01-04", "start": 6, "performers": ["Chloe", "Lila"]}]}]}
    shared: list = []
    assert CO.previous_keyframe(str(d), "production", plan, "S01-03", shared) is None and shared == []          # nobody in common: nothing to copy from
    assert CO.previous_keyframe(str(d), "production", plan, "S01-03") is not None                              # the older call is unchanged
    assert CO.previous_keyframe(str(d), "production", plan, "S01-04", shared).endswith("kf.png") and shared == ["Chloe"]
