import json
import os

import pytest

from filmcrafter_engine import directions_library as DL
from filmcrafter_engine import performance, render


def _proj(tmp_path, text="", project=None):
    """A render project, inside a film when there is story text (film.json one level up, the story as its script)."""
    root = tmp_path / "Film"
    d = root / "render"
    d.mkdir(parents=True)
    (d / "project.json").write_text(json.dumps(project or {"title": "P", "look": {"style": "auto"}}))
    if text:
        (d / "project.json").write_text(json.dumps({**(project or {"title": "P", "look": {"style": "auto"}}), "onboarding": {"stage": "done", "concept_notes": text}}))
    return str(d)


def _plain(tmp_path, monkeypatch):
    """One of the user's own directions, which has no 'avoid' note."""
    monkeypatch.setattr(DL, "USER_LIB", str(tmp_path / "u.json"))
    return DL.save({"name": "Plain", "summary": "Simple", "palette": ["grey"], "look": "live-action", "acting": "natural"})["saved"]


def test_library_entries_are_complete_and_unique():
    ids = [x["id"] for x in DL.LIBRARY]
    assert len(ids) == len(set(ids)) >= 40
    styles = {s["id"] for s in json.load(open(render.STYLES_PATH, encoding="utf-8"))["styles"]}
    regions = {x["region"] for x in DL.LIBRARY}
    assert {"North America", "Latin America", "Europe", "Asia", "Africa", "Middle East", "Oceania"} <= regions
    for x in DL.LIBRARY:
        for f in DL.FIELDS + ("name", "origin", "palette", "tags", "known_for", "genres", "respect"):
            assert x.get(f), (x["id"], f)
        assert x["look"] in styles and x["acting"] in performance.PROFILES, x["id"]
    names = {x["name"] for x in DL.LIBRARY}
    assert {"Brad Bird", "Hayao Miyazaki", "Ryan Coogler"} <= names


def test_no_song_or_music_video_words_remain():
    for x in DL.LIBRARY:
        blob = json.dumps(x).lower()
        assert "bpm" not in x and "music video" not in blob and "afrobeats" not in blob, x["id"]


def test_match_follows_the_story_not_a_tempo(tmp_path):
    soft = _proj(tmp_path / "a", "A quiet family drama. A grandmother and a child share a gentle memory of summer, in silence, and say goodbye.")
    top = [m["id"] for m in DL.match(soft)["matches"]][:8]
    assert any(i in top for i in ("hayao-miyazaki", "hirokazu-kore-eda", "isao-takahata", "satyajit-ray"))
    wild = _proj(tmp_path / "b", "An epic war. The hero leads a battle, a chase and a fight across the kingdom; an escape, an explosion, a crowd.")
    r = DL.match(wild)
    assert r["story"]["energy"] == "high" and r["story"]["words"] > 10
    assert "ss-rajamouli" in [m["id"] for m in r["matches"]] or "akira-kurosawa" in [m["id"] for m in r["matches"]]
    assert all(m["why"] for m in r["matches"][:3])


def test_match_with_no_story_is_empty_not_wrong(tmp_path):
    assert DL.match(_proj(tmp_path))["matches"] == []


def test_apply_fills_brief_bible_look_acting_but_keeps_own(tmp_path):
    d = _proj(tmp_path, project={"title": "P", "look": {"style": "anime"}, "bible": {"world": "Mine"},
                                 "onboarding": {"concept_notes": "set in Lagos"}})
    r = DL.apply(d, "ryan-coogler")
    p = json.load(open(os.path.join(d, "project.json")))
    assert p["onboarding"]["concept_notes"].startswith("Creative direction: Ryan Coogler")
    assert "set in Lagos" in p["onboarding"]["concept_notes"]
    assert p["bible"]["world"] == "Mine" and "gold" in p["bible"]["palette"]
    assert p["look"]["style"] == "anime" and p["performance"]["default"] == "dramatic"
    assert p["direction"]["id"] == "ryan-coogler" and "look: live-action" not in r["changed"]
    DL.apply(d, "wes-anderson")   # a second direction replaces the first brief, not stacks on it
    notes = json.load(open(os.path.join(d, "project.json")))["onboarding"]["concept_notes"]
    assert notes.count("Creative direction:") == 1 and "Wes Anderson" in notes and "set in Lagos" in notes
    with pytest.raises(SystemExit):
        DL.apply(d, "nope")


def test_save_and_delete_own_direction(tmp_path, monkeypatch):
    monkeypatch.setattr(DL, "USER_LIB", str(tmp_path / "u.json"))
    r = DL.save({"name": "Grandma's Kitchen", "summary": "Warm memories", "palette": ["cream", "", "red"], "look": "painterly"})
    assert r["saved"] == "my-grandma-s-kitchen"
    mine = [x for x in DL.all_directions() if x.get("custom")]
    assert mine[0]["palette"] == ["cream", "red"] and mine[0]["camera"] == "—"
    DL.delete("my-grandma-s-kitchen")
    assert not [x for x in DL.all_directions() if x.get("custom")]
    with pytest.raises(SystemExit):
        DL.save({"name": ""})


def test_apply_never_reopens_the_setup_wizard(tmp_path):
    d = _proj(tmp_path)
    DL.apply(d, "wes-anderson")
    assert json.load(open(os.path.join(d, "project.json")))["onboarding"]["stage"] == "done"


def test_second_direction_replaces_what_the_first_filled_but_not_user_edits(tmp_path, monkeypatch):
    d = _proj(tmp_path)
    DL.apply(d, "wong-kar-wai")
    p = json.load(open(os.path.join(d, "project.json")))
    p["bible"]["avoid"] = "my own rule"          # the user edits one field
    json.dump(p, open(os.path.join(d, "project.json"), "w"))
    DL.apply(d, "pedro-almodovar")
    p = json.load(open(os.path.join(d, "project.json")))
    assert "red" in p["bible"]["palette"] and p["performance"]["default"] == "dramatic"
    assert p["bible"]["avoid"] == "my own rule"
    DL.apply(d, _plain(tmp_path, monkeypatch))   # has no avoid note: my own stays
    assert json.load(open(os.path.join(d, "project.json")))["bible"]["avoid"] == "my own rule"


def test_earlier_direction_entry_is_cleared_when_new_has_none(tmp_path, monkeypatch):
    d = _proj(tmp_path)
    DL.apply(d, "wes-anderson")
    DL.apply(d, _plain(tmp_path, monkeypatch))
    assert json.load(open(os.path.join(d, "project.json")))["bible"]["avoid"] == ""
