"""Optional writing help for Cast & World: it proposes, you choose; nothing changes by itself."""
import json

import pytest

from filmcrafter_engine import assist, bible, story

SCRIPT = """INT. KITCHEN - MORNING

Sarah pours tea. Her hands are not steady. A letter lies by the sink.

SARAH
He said he would call.

JOHN
Did you say something?

EXT. PLATFORM - NIGHT

Rain on the roof.

SARAH
I am going.
"""


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    return d


class FakeClient:
    def __init__(self, out):
        self.out, self.sent = out, []

    class responses:   # noqa: N801
        pass


def _fake(monkeypatch, out, seen):
    def call(client, model, system, user, name, schema):
        seen.append({"system": system, "user": json.loads(user), "schema": schema})
        return out
    monkeypatch.setattr(assist, "_call", call)
    import filmcrafter_engine.llm as L
    import filmcrafter_engine.director as D
    monkeypatch.setattr(L, "client", lambda: object())
    monkeypatch.setattr(D, "resolve_model", lambda c, m: "test-model")


def test_what_would_be_sent_is_the_story_the_parts_about_the_entry_and_the_bible_only(film):
    br = assist.brief(film, "character", "c_sarah")
    assert br["name"] == "Sarah" and "pours tea" in br["story_excerpts"] and "He said he would call" in br["story_excerpts"]
    assert "Rain on the roof" not in br["story_excerpts"] or "SARAH" in br["story_excerpts"]
    assert br["other_characters"] == ["John"] and br["already_written"] == {}
    w = assist.brief(film, "world")
    assert w["characters"] == ["Sarah", "John"] and "pours tea" in w["story"]


def test_what_you_already_wrote_goes_along_so_the_suggestion_builds_on_it(film):
    bible.upsert(film, "character", {"id": "c_sarah", "physical": "Tall, grey eyes"})
    assert assist.brief(film, "character", "c_sarah")["already_written"] == {"physical": "Tall, grey eyes"}


def test_the_price_is_shown_before_anything_is_sent_and_is_free_on_a_local_model(film, monkeypatch):
    import filmcrafter_engine.llm as L
    monkeypatch.setattr(L, "is_local", lambda: True)
    e = assist.estimate(film, "character", "c_sarah")
    assert e["usd"] == 0.0 and e["local"] and "story" in e["sends"]
    monkeypatch.setattr(L, "is_local", lambda: False)
    monkeypatch.setattr(L, "price_per_mtok", lambda: None)
    e = assist.estimate(film, "world")
    assert e["usd"] > 0 and not e["local"] and e["calls"] == 1


def test_a_suggestion_is_returned_and_the_bible_is_not_changed(film, monkeypatch):
    seen = []
    _fake(monkeypatch, {"role": "Lead", "age": "28", "physical": "Tall, dark hair tied back", "relationships": "John's partner", "arc": "From waiting to leaving", "voice": "Low", "notes": "",
                        "wardrobe": [{"name": "Red coat", "notes": "Wool"}], "states": [{"label": "Age 8", "age": "8", "notes": "Plaits"}], "evil": "x"}, seen)
    rev = bible.view(film)["rev"]
    r = assist.suggest(film, "character", "c_sarah")
    assert r["proposal"]["physical"].startswith("Tall") and r["proposal"]["wardrobe"][0]["name"] == "Red coat" and "evil" not in r["proposal"] and "notes" not in r["proposal"]
    assert r["model"] == "test-model" and r["estimate"]["calls"] == 1
    assert bible.view(film)["rev"] == rev and bible.view(film)["characters"][0]["physical"] == ""        # only proposed
    assert seen[0]["schema"]["properties"]["wardrobe"] and "Never change the plot" in seen[0]["system"]


def test_a_place_and_a_prop_and_the_world(film, monkeypatch):
    seen = []
    _fake(monkeypatch, {"description": "A narrow kitchen", "notes": "", "spatial": {"doors": "Left of the stove", "windows": "Over the sink", "bogus": "x", **{k: "" for k in bible.SPATIAL_FIELDS if k not in ("doors", "windows")}}}, seen)
    r = assist.suggest(film, "environment", "e_kitchen")
    assert r["proposal"] == {"description": "A narrow kitchen", "spatial": {"windows": "Over the sink", "doors": "Left of the stove"}} or r["proposal"]["spatial"]["doors"] == "Left of the stove"
    _fake(monkeypatch, {"notes": "Cream envelope, sealed"}, seen)
    assert assist.suggest(film, "prop", bible.upsert(film, "prop", {"name": "Letter"})["id"])["proposal"] == {"notes": "Cream envelope, sealed"}
    _fake(monkeypatch, {"rules": {"world": "A rainy town", "tone": "", "rules": "", "avoid": "Neon"}, "philosophy": {k: ("Soft" if k == "lighting" else "") for k in bible.PHILOSOPHY_FIELDS},
                        "style": {"lane": "painterly animation", "traits": "Oil paint"}}, seen)
    w = assist.suggest(film, "world")["proposal"]
    assert w["rules"] == {"world": "A rainy town", "avoid": "Neon"} and w["philosophy"] == {"lighting": "Soft"} and w["style"] == {"lane": "painterly animation", "traits": "Oil paint"}


def test_a_style_that_is_not_on_the_list_is_dropped_and_text_is_limited(film, monkeypatch):
    _fake(monkeypatch, {"rules": {"world": "w" * 9000, "tone": "", "rules": "", "avoid": ""}, "philosophy": {k: "" for k in bible.PHILOSOPHY_FIELDS}, "style": {"lane": "hyper-realistic neon", "traits": ""}}, [])
    w = assist.suggest(film, "world")["proposal"]
    assert "style" not in w and len(w["rules"]["world"]) == assist.LIMIT


def test_odd_answers_never_break_it():
    for kind in assist.KINDS:
        for out in (None, {}, [], "text", {"role": None}, {"spatial": "x"}, {"rules": 5}):
            assert isinstance(assist.clean(kind, out), dict)


def test_unknown_kinds_and_ids_are_refused(film):
    with pytest.raises(SystemExit, match="Choose character"):
        assist.brief(film, "weather")
    with pytest.raises(SystemExit, match="not valid"):
        assist.brief(film, "character", "../../evil")
    with pytest.raises(SystemExit, match="isn't in the Bible"):
        assist.brief(film, "character", "c_nobody")


def test_the_command_line(film, capsys):
    assert assist.main(["estimate", film, "--data", json.dumps({"kind": "world"})]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["event"] == "result"
    assert assist.main(["estimate", film, "--data", json.dumps({"kind": "nope"})]) == 1
