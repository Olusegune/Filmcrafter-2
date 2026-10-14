"""Sound style and voice profiles live in the Bible (additive), never touch the assigned voice, and older Bibles still open."""
import json
import os

import pytest

from filmcrafter_engine import bible, cast_voice as C, story

SCRIPT = "INT. YARD - DAY\n\nA schoolyard.\n\nLILA\nIt looked weird.\n\nCHLOE\nI know.\n"


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "Night Market", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    return d


def test_an_older_bible_without_sound_keys_opens_with_empty_sound_style_and_no_profile(film):
    p = os.path.join(film, "bible", "bible.json")
    b = json.load(open(p, encoding="utf-8"))
    b.pop("sound_style", None)
    for c in b["characters"]:
        c.pop("voice_profile", None)
    json.dump(b, open(p, "w", encoding="utf-8"))
    v = bible.view(film)
    assert v["sound_style"]["music"]["genre"] == "" and set(v["sound_style"]) == {"sound", "music"}
    assert all("voice_profile" not in c for c in v["characters"])


def test_the_sound_style_is_saved_trimmed_limited_to_known_fields_and_keeps_a_history_copy(film):
    rev = bible.view(film)["rev"]
    v = bible.update_sound_style(film, {"sound_style": {"sound": {"philosophy": "  Quiet, close, human  ", "nonsense": "x"}, "music": {"genre": "Chamber", "silence": "Prefer silence in grief"}, "other": {"a": "b"}}})
    assert v["sound_style"]["sound"]["philosophy"] == "Quiet, close, human" and "nonsense" not in v["sound_style"]["sound"]
    assert v["sound_style"]["music"]["genre"] == "Chamber" and "other" not in v["sound_style"]
    assert v["rev"] == rev + 1 and os.path.isdir(os.path.join(film, "bible", "history"))
    again = bible.update_sound_style(film, {"sound_style": {"music": {"mood": "tender"}}})
    assert again["sound_style"]["music"]["genre"] == "Chamber" and again["sound_style"]["music"]["mood"] == "tender"      # a partial save keeps the rest
    assert bible.update_sound_style(film, {"sound_style": {"music": {"mood": "tender"}}})["rev"] == again["rev"]          # no change, no new revision


def test_a_voice_profile_is_kept_per_character_and_approval_is_only_set_by_the_person(film):
    lila = next(c for c in bible.view(film)["characters"] if c["name"].lower().startswith("lila"))
    v = bible.set_voice_profile(film, lila["id"], {"description": "Warm, a little tired", "age_range": "30s", "accent": "Northern", "pace": "slow", "unknown": "x"})
    c = next(x for x in v["characters"] if x["id"] == lila["id"])
    assert c["voice_profile"]["description"] == "Warm, a little tired" and c["voice_profile"]["approved"] is False and "unknown" not in c["voice_profile"]
    v = bible.set_voice_profile(film, lila["id"], {"approved": True})
    c = next(x for x in v["characters"] if x["id"] == lila["id"])
    assert c["voice_profile"]["approved"] is True and c["voice_profile"]["accent"] == "Northern"        # an edit that does not mention it keeps it
    other = next(x for x in v["characters"] if x["id"] != lila["id"])
    assert "voice_profile" not in other                                                                     # others are untouched
    with pytest.raises(SystemExit):
        bible.set_voice_profile(film, "../x", {})
    with pytest.raises(SystemExit):
        bible.set_voice_profile(film, "c-nobody", {})


def test_saving_a_profile_never_touches_the_assigned_voice_or_the_voice_files(film):
    V = C.V
    V.status(film)
    C.set_voice(film, "Lila", {"voice_id": "AbCdEfGh1234", "voice_name": "Warm", "model": "eleven_v4"})
    before = open(os.path.join(film, "voice", "cast.json"), "rb").read()
    lila = next(c for c in bible.view(film)["characters"] if c["name"].lower().startswith("lila"))
    bible.set_voice_profile(film, lila["id"], {"description": "x", "approved": True})
    assert open(os.path.join(film, "voice", "cast.json"), "rb").read() == before


def test_a_damaged_bible_is_not_mistaken_for_an_empty_one_when_saving_sound_style(film):
    p = os.path.join(film, "bible", "bible.json")
    if os.path.exists(p + ".bak"):
        os.remove(p + ".bak")
    open(p, "wb").write(b'{"characters": [')
    with pytest.raises(SystemExit, match="damaged"):
        bible.update_sound_style(film, {"sound_style": {"sound": {"philosophy": "x"}}})
    assert open(p, "rb").read() == b'{"characters": ['
