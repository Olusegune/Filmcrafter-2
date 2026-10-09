"""Script to show, numbers waiting for a song, and costumes per act. No network."""
import json
import os

import numpy as np
import pytest
import soundfile as sf
from PIL import Image

from filmcrafter_engine import library, show as S, show_script as SS, voices as V

SCRIPT = """TITLE: Night Market

Some notes the writer left at the top.

ACT 1: The Market
SCENE: Closing time
(Ada wipes the counter as the lamps come on.)
ADA (happy): Fresh bread, still warm!
BEN: I'll take two,
and a smile if you have one.
ADA (smugly): Smiles are extra.

SONG: Opening Number
[Verse 1]
The lamps come on

[Chorus]
Hello, night

ACT TWO
Scene 3 - The quarrel
BEN (angry): You sold my place.
Act natural, said Ada.
SONG 2: Last Dance
"""


def _wav(path, secs=1.0):
    t = np.linspace(0, secs, int(44100 * secs), endpoint=False)
    sf.write(str(path), (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), 44100)
    return str(path)


@pytest.fixture
def show(tmp_path):
    return S.create(str(tmp_path / "shows"), "Night Market")["dir"]


def test_a_script_becomes_acts_numbers_and_scenes():
    plan = SS.parse(SCRIPT)
    assert plan["title"] == "Night Market"
    assert [a["name"] for a in plan["acts"]] == ["Act 1: The Market", "Act Two"]
    first = plan["acts"][0]["items"]
    assert [(i["kind"], i["title"]) for i in first] == [("scene", "Closing time"), ("number", "Opening Number")]
    scene = first[0]
    assert scene["setting"] == "Ada wipes the counter as the lamps come on."
    assert [(x["character"], x["emotion"]) for x in scene["lines"]] == [("Ada", "happy"), ("Ben", None), ("Ada", None)]
    assert scene["lines"][1]["text"] == "I'll take two, and a smile if you have one."     # a wrapped line joins the one before
    assert scene["lines"][2]["text"].startswith("(smugly) ")                              # an emotion we don't have stays as words
    assert first[1]["lyrics"] == "[Verse 1]\nThe lamps come on\n\n[Chorus]\nHello, night"
    assert plan["characters"] == ["Ada", "Ben"]
    assert plan["totals"] == {"acts": 2, "numbers": 2, "scenes": 2, "lines": 4}


def test_a_sentence_that_starts_with_act_is_not_a_new_act():
    plan = SS.parse(SCRIPT)
    assert len(plan["acts"]) == 2
    quarrel = plan["acts"][1]["items"][0]
    assert quarrel["title"] == "The quarrel" and quarrel["lines"][0]["text"] == "You sold my place. Act natural, said Ada."


def test_a_script_with_nothing_to_import_is_refused_and_odd_input_is_bounded(tmp_path):
    with pytest.raises(SystemExit, match="No SONG or SCENE"):
        SS.parse("Just some words.\nAnd more.")
    many = "\n".join(f"SONG: Number {i}" for i in range(SS.MAX_ITEMS + 1))
    with pytest.raises(SystemExit, match="more than"):
        SS.parse(many)
    big = tmp_path / "big.txt"
    big.write_bytes(b"a" * (SS.MAX_BYTES + 1))
    with pytest.raises(SystemExit, match="too large"):
        SS.read_script(str(big))
    binary = tmp_path / "x.txt"
    binary.write_bytes(b"\x00\x01\x02" * 100)
    with pytest.raises(SystemExit, match="text file"):
        SS.read_script(str(binary))
    exe = tmp_path / "x.exe"
    exe.write_bytes(b"MZ")
    with pytest.raises(SystemExit, match="text, Markdown or PDF"):
        SS.read_script(str(exe))
    with pytest.raises(SystemExit, match="can't be found"):
        SS.read_script(str(tmp_path / "missing.txt"))


def test_long_text_is_clamped_and_titles_cannot_make_paths(show, tmp_path):
    f = tmp_path / "s.txt"
    f.write_text("SCENE: ../../evil\nADA: " + "x" * 5000 + "\nSONG: ..\\..\\worse\nla\n", encoding="utf-8")
    plan = SS.preview(str(f))
    assert len(plan["acts"][0]["items"][0]["lines"][0]["text"]) == SS.MAX_LINE
    SS.import_script(show, str(f))
    for root, dirs, _ in os.walk(show):
        assert os.path.realpath(root).startswith(os.path.realpath(show))
    assert not os.path.exists(os.path.join(os.path.dirname(show), "evil"))
    assert all(os.path.dirname(i["path"]).endswith("items") for a in S.status(show)["acts"] for i in a["items"])


def test_songs_are_matched_by_name_only_when_the_match_is_clear(tmp_path):
    songs = tmp_path / "songs"
    songs.mkdir()
    _wav(songs / "opening_number.wav")
    _wav(songs / "Last Dance (final mix).mp3")
    _wav(songs / "last dance (demo).mp3")                    # two near matches: not clear, so not used
    (songs / "notes.txt").write_text("not audio")
    f = tmp_path / "s.txt"
    f.write_text(SCRIPT, encoding="utf-8")
    plan = SS.preview(str(f), str(songs))
    songs_by_title = {i["title"]: i["song"] for a in plan["acts"] for i in a["items"] if i["kind"] == "number"}
    assert songs_by_title["Opening Number"].endswith("opening_number.wav") and songs_by_title["Last Dance"] is None
    assert plan["totals"]["songs_matched"] == 1 and plan["totals"]["songs_missing"] == 1
    with pytest.raises(SystemExit, match="songs folder"):
        SS.preview(str(f), str(tmp_path / "nope"))


def test_importing_builds_the_show_and_adds_the_cast(show, tmp_path):
    songs = tmp_path / "songs"
    songs.mkdir()
    _wav(songs / "Opening Number.wav")
    f = tmp_path / "s.txt"
    f.write_text(SCRIPT, encoding="utf-8")
    r = SS.import_script(show, str(f), str(songs))
    assert r["imported"]["numbers"] == 2 and r["imported"]["scenes"] == 2 and r["imported"]["characters_added"] == 2
    assert r["imported"]["songs_matched"] == 1 and r["imported"]["songs_missing"] == 1
    assert [a["name"] for a in r["acts"]] == ["Act 1: The Market", "Act Two"]        # the empty first act was reused, not left behind
    assert set(r["characters"]) == {"Ada", "Ben"}
    items = {i["title"]: i for a in r["acts"] for i in a["items"]}
    assert items["Closing time"]["lines"] == 3 and "The dialogue hasn't been voiced yet." in items["Closing time"]["problems"]
    assert items["Opening Number"]["has_audio"] and not items["Opening Number"]["song_pending"]
    assert items["Last Dance"]["song_pending"] and "No song attached yet. Use Attach song." in items["Last Dance"]["problems"]
    d = V.dialogue(items["Closing time"]["path"])
    assert d["setting"].startswith("Ada wipes") and d["lines"][0]["emotion"] == "happy"
    assert open(os.path.join(items["Opening Number"]["path"], "lyrics.txt"), encoding="utf-8").read().startswith("[Verse 1]")
    # Importing again adds more; it never touches or replaces what is there.
    r2 = SS.import_script(show, str(f))
    assert len([i for a in r2["acts"] for i in a["items"]]) == 8 and r2["imported"]["characters_added"] == 0


def test_a_number_without_a_song_waits_for_one_and_blocks_export(show, tmp_path):
    item = S.add_number(show, None, "Waiting")["item"]
    assert S.status(show)["acts"][0]["items"][0]["song_pending"]
    with pytest.raises(SystemExit, match="Waiting: attach its song first"):
        S.export(show)
    song = _wav(tmp_path / "w.wav")
    st = S.attach_song(show, item, song)
    row = st["acts"][0]["items"][0]
    assert row["has_audio"] and not row["song_pending"] and os.path.exists(song)         # the original is untouched
    with pytest.raises(SystemExit, match="already has a song"):
        S.attach_song(show, item, song)
    with pytest.raises(SystemExit, match="can't be found"):
        S.attach_song(show, S.add_number(show, None, "Two")["item"], str(tmp_path / "gone.wav"))
    pending = S.add_number(show, None, "Three")["item"]
    (tmp_path / "x.exe").write_bytes(b"MZ")
    with pytest.raises(SystemExit, match="audio file"):
        S.attach_song(show, pending, str(tmp_path / "x.exe"))
    scene = S.add_scene(show, "Talk")["item"]
    with pytest.raises(SystemExit, match="isn't a number"):
        S.attach_song(show, scene, song)


def test_a_costume_changes_one_act_and_never_the_cast(show, tmp_path):
    cast = os.path.join(show, "cast")
    os.makedirs(os.path.join(cast, "assets"), exist_ok=True)
    Image.new("RGB", (8, 8), "red").save(os.path.join(cast, "assets", "ada.png"))
    Image.new("RGB", (8, 8), "blue").save(tmp_path / "gown.png")
    library.upsert(cast, {"kind": "character", "name": "Ada", "files": ["assets/ada.png"], "notes": "baker"})
    a = S.add_number(show, _wav(tmp_path / "a.wav"), "One")
    S.add_act(show, "Act 2")
    b = S.add_number(show, _wav(tmp_path / "b.wav"), "Two", act=1)
    st = S.set_costume(show, 1, "Ada", str(tmp_path / "gown.png"), "a blue ball gown")
    assert st["acts"][1]["costumes"]["Ada"]["note"] == "a blue ball gown" and st["acts"][0]["costumes"] == {}

    def ada(d):
        return next(i for i in library.load(d)[1]["items"] if i["name"] == "Ada")
    one, two = ada(a["dir"]), ada(b["dir"])
    assert "costume" not in one and "costume" in two
    assert os.path.basename(one["files"][0]) == "ada.png" and os.path.basename(two["files"][0]).startswith("Ada-act2")
    assert "ball gown" in two["notes"] and "baker" in two["notes"] and "ball gown" not in one.get("notes", "")
    assert ada(cast)["files"] == ["assets/ada.png"]                                           # the cast is untouched
    S.set_costume(show, 1, "Ada", clear=True)
    assert "costume" not in ada(b["dir"]) and os.path.basename(ada(b["dir"])["files"][0]) == "ada.png"
    with pytest.raises(SystemExit, match="PNG, JPG or WebP"):
        S.set_costume(show, 0, "Ada", str(tmp_path / "a.wav"))
    with pytest.raises(SystemExit, match="image or write a note"):
        S.set_costume(show, 0, "Ada")
    with pytest.raises(SystemExit, match="No such act"):
        S.set_costume(show, 7, "Ada", note="x")


def test_a_costume_file_outside_the_cast_folder_is_ignored(show, tmp_path):
    cast = os.path.join(show, "cast")
    os.makedirs(os.path.join(cast, "assets"), exist_ok=True)
    Image.new("RGB", (8, 8)).save(os.path.join(cast, "assets", "ada.png"))
    library.upsert(cast, {"kind": "character", "name": "Ada", "files": ["assets/ada.png"]})
    secret = tmp_path / "secret.png"
    Image.new("RGB", (8, 8), "green").save(secret)
    a = S.add_number(show, _wav(tmp_path / "a.wav"), "One")
    data = json.load(open(os.path.join(show, "show.json")))
    data["acts"][0]["costumes"] = {"Ada": {"file": os.path.relpath(secret, cast), "note": ""}}
    json.dump(data, open(os.path.join(show, "show.json"), "w"))
    S.sync(show)
    it = next(i for i in library.load(a["dir"])[1]["items"] if i["name"] == "Ada")
    assert [os.path.basename(f) for f in it["files"]] == ["ada.png"]
    assert not os.path.exists(os.path.join(a["dir"], "assets", "cast", "secret.png"))
