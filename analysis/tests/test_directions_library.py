import json
import os

import pytest

from pulseframe_analysis import directions_library as DL
from pulseframe_analysis import performance, render


def _proj(tmp_path, bpm=112, energy=0.8, mood="Euphoric", project=None):
    d = tmp_path / "P"
    d.mkdir()
    (d / "project.json").write_text(json.dumps(project or {"title": "P", "look": {"style": "auto"}}))
    (d / "songmap.json").write_text(json.dumps({"bpm": bpm, "energy_curve": [[0, energy], [1, energy]],
                                                "sections": [{"start": 0, "end": 1, "mood": mood}]}))
    return str(d)


def test_library_entries_are_complete_and_unique():
    ids = [x["id"] for x in DL.LIBRARY]
    assert len(ids) == len(set(ids)) >= 25
    styles = {s["id"] for s in json.load(open(render.STYLES_PATH, encoding="utf-8"))["styles"]}
    regions = {x["region"] for x in DL.LIBRARY}
    assert {"Africa", "Asia", "Europe", "Americas", "Oceania"} <= regions
    for x in DL.LIBRARY:
        for f in DL.FIELDS + ("name", "origin", "palette", "tags"):
            assert x.get(f), (x["id"], f)
        assert x["look"] in styles and x["acting"] in performance.PROFILES


def test_match_prefers_fitting_tempo_energy_and_mood(tmp_path):
    d = _proj(tmp_path, bpm=112, energy=0.8, mood="Euphoric")
    top = [m["id"] for m in DL.match(d)["matches"]]
    assert "amapiano-house-party" in top[:4]
    d2 = _proj(tmp_path / "b", bpm=70, energy=0.2, mood="Intimate") if os.makedirs(tmp_path / "b") is None else None
    low = [m["id"] for m in DL.match(d2)["matches"]]
    assert "amapiano-house-party" not in low[:6]


def test_apply_fills_brief_bible_look_acting_but_keeps_own(tmp_path):
    d = _proj(tmp_path, project={"title": "P", "look": {"style": "anime"}, "bible": {"world": "Mine"},
                                 "onboarding": {"concept_notes": "set in Lagos"}})
    r = DL.apply(d, "lagos-nights")
    p = json.load(open(os.path.join(d, "project.json")))
    assert p["onboarding"]["concept_notes"].startswith("Creative direction: Lagos Nights")
    assert "set in Lagos" in p["onboarding"]["concept_notes"]
    assert p["bible"]["world"] == "Mine" and "amber" in p["bible"]["palette"]
    assert p["look"]["style"] == "anime" and p["performance"]["default"] == "expressive"
    assert p["direction"]["id"] == "lagos-nights" and "look: live-action" not in r["changed"]
    DL.apply(d, "nordic-noir")   # a second direction replaces the first brief, not stacks on it
    notes = json.load(open(os.path.join(d, "project.json")))["onboarding"]["concept_notes"]
    assert notes.count("Creative direction:") == 1 and "Nordic Noir" in notes and "set in Lagos" in notes
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
    DL.apply(d, "nordic-noir")
    assert json.load(open(os.path.join(d, "project.json")))["onboarding"]["stage"] == "done"



def test_second_direction_replaces_what_the_first_filled_but_not_user_edits(tmp_path):
    d = _proj(tmp_path)
    DL.apply(d, "french-new-wave")
    p = json.load(open(os.path.join(d, "project.json")))
    p["bible"]["avoid"] = "my own rule"          # the user edits one field
    json.dump(p, open(os.path.join(d, "project.json"), "w"))
    DL.apply(d, "telenovela-gloss")
    p = json.load(open(os.path.join(d, "project.json")))
    assert "wine red" in p["bible"]["palette"] and p["performance"]["default"] == "dramatic"
    assert p["bible"]["avoid"] == "my own rule"
    DL.apply(d, "lagos-nights")
    DL.apply(d, "nordic-noir")   # has no avoid note: my own stays, a direction's would be cleared
    assert json.load(open(os.path.join(d, "project.json")))["bible"]["avoid"] == "my own rule"


def test_earlier_direction_entry_is_cleared_when_new_has_none(tmp_path):
    d = _proj(tmp_path)
    DL.apply(d, "lagos-nights")
    DL.apply(d, "nordic-noir")
    assert json.load(open(os.path.join(d, "project.json")))["bible"]["avoid"] == ""


def test_half_time_is_labelled(tmp_path):
    d = _proj(tmp_path, bpm=120, energy=0.5, mood="Tender")
    m = {x["id"]: x for x in DL.match(d, limit=40)["matches"]}
    assert any("half-time" in w for w in m["telenovela-gloss"]["why"])
