"""The screenplay format for Import script: # headings for sections, CHARACTER NAME above the words. No network."""
import os

import pytest

from pulseframe_analysis import show as S, show_script as SS, voices as V

SCREENPLAY = """# THE FAMILY CIRCUS
## Episode 1: I AM YOUR MOTHER!

**Genre:** Musical comedy

### PRINCIPAL CHARACTERS

**BEATRICE "QUEEN BEE" ADEYEMI - Mother**
Elegant and formidable.

---

# COLD OPEN

### INT. ADEYEMI FAMILY HOME - MORNING

Sunlight streams through an immaculate living room.

**DING! DING! DING!**

QUEEN BEE (O.S.)
Children!

TUNDE
We're already downstairs.

QUEEN BEE
...

They are on my head?

PASTOR'S WIFE (angry)
Are you going to answer?

### MUSIC BEGINS.

---

# VERSE 1 - THE QUEEN ADDRESSES HER SUBJECTS

Queen Bee sings to her children.

QUEEN BEE
Nine months I carry you,
Now you tell me, "Mummy, no"?

TUNDE
Why did you keep that?

# PRE-CHORUS - THE GOVERNMENT IS REVEALED

QUEEN BEE
I don't control, I only guide!

# CHORUS - THE NATIONAL ANTHEM

QUEEN BEE
I AM YOUR MOTHER!

### TITLE CARD:

# I AM YOUR MOTHER!

A crown lands on the letter M.

# SCENE - ARTICLE ONE

Queen Bee opens the Constitution.

QUEEN BEE
Article One.
"Mummy is always right."

ZARA
Convenient.

# FINAL CHORUS - THE REVOLUTION BEGINS

QUEEN BEE
I AM YOUR MOTHER!

CHILDREN
Yes, we know!

# OUTRO

QUEEN BEE
Family meeting tomorrow.

ZARA
I'm busy.

### POST-CREDIT STINGER

INT. PASTOR'S HOME - NIGHT

PASTOR
Let us pray.

# END

QUEEN BEE
This is after the end and is never read.
"""


def _items(plan):
    return [(i["kind"], i["title"]) for a in plan["acts"] for i in a["items"]]


def test_a_screenplay_becomes_numbers_and_scenes_by_its_headings():
    plan = SS.parse(SCREENPLAY)
    assert plan["format"] == "screenplay" and plan["title"] == "The Family Circus"
    assert _items(plan) == [("scene", "Cold Open"), ("number", "Verse 1 – Chorus"), ("scene", "Article One"),
                            ("number", "Final Chorus"), ("scene", "Outro"), ("scene", "Post-credit Stinger")]
    assert plan["totals"] == {"acts": 1, "numbers": 2, "scenes": 4, "lines": 8}


def test_dialogue_setting_and_pauses_are_read_the_way_a_screenplay_means_them():
    cold = SS.parse(SCREENPLAY)["acts"][0]["items"][0]
    assert [(x["character"], x["text"], x["emotion"]) for x in cold["lines"]] == [
        ("Queen Bee", "Children!", None), ("Tunde", "We're already downstairs.", None), ("Pastor's Wife", "Are you going to answer?", "angry")]
    assert cold["setting"].startswith("INT. ADEYEMI FAMILY HOME - MORNING Sunlight streams")      # the slug line and action are the setting
    assert "DING" in cold["setting"] and "Title card" not in cold["setting"]
    art = SS.parse(SCREENPLAY)["acts"][0]["items"][2]
    assert art["lines"][0]["text"] == 'Article One. "Mummy is always right."'                     # a wrapped speech is one line
    stinger = SS.parse(SCREENPLAY)["acts"][0]["items"][5]
    assert stinger["setting"].startswith("INT. PASTOR'S HOME") and stinger["lines"][0]["character"] == "Pastor"


def test_music_sections_become_lyrics_with_section_tags_and_consecutive_ones_merge():
    song = SS.parse(SCREENPLAY)["acts"][0]["items"][1]
    assert song["lyrics"].split("\n")[0] == "[Verse 1]"
    assert "[Pre-chorus]" in song["lyrics"] and "[Chorus]" in song["lyrics"]
    assert 'Nine months I carry you,\nNow you tell me, "Mummy, no"?' in song["lyrics"]
    assert "Why did you keep that?" in song["lyrics"] and "sings to her children" not in song["lyrics"]    # action isn't sung
    assert "[Queen Bee]" not in song["lyrics"]                                                      # a [Name] would read as a new section
    from pulseframe_analysis.lyrics import parse_lyrics
    assert [x.tag for x in parse_lyrics(song["lyrics"])] == ["Verse 1", "Pre-chorus", "Chorus"]


def test_one_recorded_song_collects_all_the_music_into_one_number():
    plan = SS.parse(SCREENPLAY, one_song=True)
    assert _items(plan) == [("scene", "Cold Open"), ("number", "I Am Your Mother!"), ("scene", "Article One"),
                            ("scene", "Outro"), ("scene", "Post-credit Stinger")]
    lyrics = plan["acts"][0]["items"][1]["lyrics"]
    assert "[Verse 1]" in lyrics and "[Final Chorus]" in lyrics and "Yes, we know!" in lyrics


def test_the_title_card_and_the_end_marker_are_not_sections():
    plan = SS.parse(SCREENPLAY)
    assert "I Am Your Mother!" not in [t for _, t in _items(plan)]                                  # the title card is direction
    assert "never read" not in str(plan)
    assert plan["characters"] == ["Children", "Pastor", "Pastor's Wife", "Queen Bee", "Tunde", "Zara"]


def test_markers_still_win_and_text_with_no_structure_is_refused():
    assert "format" not in SS.parse("SONG: A\nla la\nSCENE: B\nADA: Hi.")                           # the marker format is unchanged
    with pytest.raises(SystemExit, match="# headings"):
        SS.parse("Just some words.\nAnd more.")


def test_acts_can_be_headings_in_a_screenplay():
    plan = SS.parse("# SHOW\n# ACT ONE: The Market\n# SCENE - OPEN\nADA\nHello.\n# ACT TWO\n# SCENE - CLOSE\nBEN\nBye.\n")
    assert [a["name"] for a in plan["acts"]] == ["Act One: The Market", "Act Two"]


def test_importing_a_screenplay_builds_the_show(show_dir):
    f = os.path.join(show_dir, "..", "play.md")
    open(f, "w", encoding="utf-8").write(SCREENPLAY)
    r = SS.import_script(show_dir, f, one_song=True)
    assert r["imported"]["numbers"] == 1 and r["imported"]["scenes"] == 4
    assert {"Queen Bee", "Tunde", "Zara"} <= set(r["characters"])
    items = {i["title"]: i for a in r["acts"] for i in a["items"]}
    assert items["I Am Your Mother!"]["song_pending"]
    assert V.dialogue(items["Cold Open"]["path"])["lines"][2]["emotion"] == "angry"


@pytest.fixture
def show_dir(tmp_path):
    return S.create(str(tmp_path / "shows"), "Family Circus")["dir"]
