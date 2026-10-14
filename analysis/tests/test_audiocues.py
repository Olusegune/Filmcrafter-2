"""Stage C: audio cues. A scene gets a planned, editable soundscape from the film's own sound library without any generation or payment; cues are stored once, point at stable asset ids,
notice when they may be out of date, and are never deleted."""
import json
import os
import zipfile

import numpy as np
import pytest
import soundfile as sf

from filmcrafter_engine import assist, audiocues as Q, audiolib as A, bible, filmbackup, shots as S, story, voiceover as V

SCRIPT = "INT. KITCHEN - NIGHT\n\nRain on the roof. Sarah pours tea from the kettle.\n\nSARAH\nHe said he'd call.\n\nEXT. YARD - DAY\n\nChildren play in the schoolyard.\n"


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    S.breakdown(d)
    return d


def wav(tmp_path, name, secs=1.0, hz=220):
    p = tmp_path / "src" / name
    p.parent.mkdir(exist_ok=True)
    t = np.arange(int(22050 * secs)) / 22050
    sf.write(str(p), (0.3 * np.sin(2 * np.pi * hz * t)).astype("float32"), 22050)
    return str(p)


def asset(film, tmp_path, kind="sfx", name="rain.wav", secs=2.0, hz=220, **upd):
    a = A.import_files(film, kind, [wav(tmp_path, name, secs, hz)], upd.pop("category", None))["assets"][-1]
    if upd:
        A.update(film, a["id"], upd)
    return A.list_assets(film)["assets"][-1] if not upd else next(x for x in A.list_assets(film)["assets"] if x["id"] == a["id"])


def first_shot(film, scene=1):
    return next(s for s in S.view(film)["shots"] if s["scene"] == scene)


# ---------------------------------------------------------------- placing cues

def test_a_sound_is_placed_in_a_shot_with_its_timing_level_and_fades_and_the_asset_is_untouched(film, tmp_path):
    a = asset(film, tmp_path, name="Rain.wav", category="ambience", tags=["rain"])
    s = first_shot(film)
    before = open(os.path.join(film, *a["file"].split("/")), "rb").read()
    r = Q.add(film, {"asset_id": a["id"], "shot": s["id"], "start": 0.5, "duration": 3, "gain_db": -12, "fade_in": 0.5, "fade_out": 1, "note": "under the whole shot"})
    c = next(x for x in r["cues"] if x["id"] == r["id"])
    assert c["kind"] == "ambience" and c["loop"] is True and c["scene"] == 1 and c["shot"] == s["id"] and c["approval"] == "approved" and c["source"] == "manual"
    assert (c["start"], c["duration"], c["gain_db"], c["fade_in"], c["fade_out"], c["ducking"]) == (0.5, 3.0, -12.0, 0.5, 1.0, "auto")
    assert c["asset_name"] == a["name"] and c["fresh"] == [] and c["made_from"]["asset_sha1"] == a["sha1"] and c["made_from"]["shot_seconds"] == s["duration"]
    assert open(os.path.join(film, *a["file"].split("/")), "rb").read() == before
    assert r["counts"]["cues"] == 1


def test_a_scene_wide_cue_and_a_planned_cue_that_still_needs_a_sound(film, tmp_path):
    a = asset(film, tmp_path, "music", "theme.wav", 5.0, category="theme")
    r = Q.add(film, {"asset_id": a["id"], "scene": 1, "gain_db": -18})
    m = next(x for x in r["cues"] if x["id"] == r["id"])
    assert m["kind"] == "music" and m["shot"] is None and m["scene"] == 1 and m["loop"] is False
    p = Q.add(film, {"kind": "sfx", "scene": 1, "plan": {"description": "A kettle clicking off", "search": "kettle"}})
    plan = next(x for x in p["cues"] if x["id"] == p["id"])
    assert plan["asset_id"] is None and plan["needs_sound"] is True and p["counts"]["needs_sound"] == 1
    given = Q.update(film, plan["id"], {"asset_id": asset(film, tmp_path, "sfx", "kettle.wav", 1.5, hz=330)["id"]})
    g = next(x for x in given["cues"] if x["id"] == plan["id"])
    assert g["needs_sound"] is False and g["asset_name"] and "plan" not in g and given["counts"]["needs_sound"] == 0


def test_bad_places_times_and_levels_are_refused_and_nothing_is_saved(film, tmp_path):
    a = asset(film, tmp_path)
    cases = [{"asset_id": a["id"], "shot": "S99-99"}, {"asset_id": a["id"], "scene": 77}, {"asset_id": "a-sfx-00000000", "scene": 1}, {"scene": 1},
             {"asset_id": a["id"], "scene": 1, "start": -1}, {"asset_id": a["id"], "scene": 1, "gain_db": 40}, {"asset_id": a["id"], "scene": 1, "fade_in": 999},
             {"asset_id": a["id"], "scene": 1, "ducking": "maybe"}, {"asset_id": a["id"]}, {"asset_id": a["id"], "scene": 1, "duration": "long"}]
    for bad in cases:
        with pytest.raises(SystemExit):
            Q.add(film, bad)
    assert not os.path.exists(os.path.join(film, "audio", "cues.json")) or Q.listing(film)["cues"] == []


def test_changing_a_cue_keeps_its_id_and_a_removed_cue_can_come_back(film, tmp_path):
    a = asset(film, tmp_path)
    cid = Q.add(film, {"asset_id": a["id"], "scene": 1})["id"]
    r = Q.update(film, cid, {"start": 1.5, "gain_db": -6, "loop": True, "ducking": "off", "note": "softer"})
    c = next(x for x in r["cues"] if x["id"] == cid)
    assert (c["start"], c["gain_db"], c["loop"], c["ducking"], c["note"]) == (1.5, -6.0, True, "off", "softer")
    assert Q.remove(film, cid)["cues"] == []
    assert len(Q.listing(film)["removed"]) == 1
    assert next(x for x in Q.restore(film, cid)["cues"])["id"] == cid
    with pytest.raises(SystemExit):
        Q.restore(film, cid)
    for bad in ("../x", "q-zzzz", ""):
        with pytest.raises(SystemExit):
            Q.update(film, bad, {})


def test_approval_is_the_persons_decision_and_a_rejected_cue_stays_listed(film, tmp_path):
    a = asset(film, tmp_path)
    cid = Q.add(film, {"asset_id": a["id"], "scene": 1, "source": "director"})["id"]
    assert next(x for x in Q.listing(film)["cues"] if x["id"] == cid)["approval"] == "suggested" and Q.listing(film)["counts"]["suggested"] == 1
    assert next(x for x in Q.approve(film, cid, "approved")["cues"] if x["id"] == cid)["approval"] == "approved"
    assert next(x for x in Q.approve(film, cid, "rejected")["cues"] if x["id"] == cid)["approval"] == "rejected"
    with pytest.raises(SystemExit):
        Q.approve(film, cid, "great")


# ---------------------------------------------------------------- noticing what may be out of date (never changing it)

def test_a_replaced_sound_a_longer_shot_and_a_removed_sound_are_flagged_and_the_cue_is_left_alone(film, tmp_path):
    a = asset(film, tmp_path, "sfx", "kettle.wav", 1.5)
    s = first_shot(film)
    cid = Q.add(film, {"asset_id": a["id"], "shot": s["id"], "start": 0.5})["id"]
    snapshot = json.dumps([x for x in Q.listing(film)["cues"]][0]["made_from"])
    c = S._contract(film, s["id"])
    c["generation"]["duration"] = s["duration"] + 3
    S._write(S._cpath(film, s["id"]), c)
    f = next(x for x in Q.listing(film)["cues"] if x["id"] == cid)["fresh"]
    assert [x["code"] for x in f] == ["timing_changed"] and "may need adjusting" in f[0]["why"]
    lib = json.load(open(os.path.join(film, "audio", "library.json")))
    lib["assets"][0]["sha1"] = "0" * 40
    json.dump(lib, open(os.path.join(film, "audio", "library.json"), "w"))
    f = next(x for x in Q.listing(film)["cues"] if x["id"] == cid)["fresh"]
    assert {x["code"] for x in f} == {"timing_changed", "asset_changed"}
    A.remove(film, a["id"])
    f = next(x for x in Q.listing(film)["cues"] if x["id"] == cid)["fresh"]
    assert "asset_removed" in {x["code"] for x in f}
    assert json.dumps(next(x for x in Q.listing(film)["cues"] if x["id"] == cid)["made_from"]) == snapshot            # nothing was rewritten behind the person's back
    ok = Q.refresh(film, cid)
    assert next(x for x in ok["cues"] if x["id"] == cid)["made_from"]["shot_seconds"] == s["duration"] + 3


def test_a_deleted_shot_is_flagged_not_deleted_with_it(film, tmp_path):
    a = asset(film, tmp_path)
    shot = [x for x in S.view(film)["shots"] if x["scene"] == 1][-1]
    cid = Q.add(film, {"asset_id": a["id"], "shot": shot["id"]})["id"]
    S.delete(film, shot["id"])
    c = next(x for x in Q.listing(film)["cues"] if x["id"] == cid)
    assert "shot_gone" in {x["code"] for x in c["fresh"]}


# ---------------------------------------------------------------- the library is searched first

def test_matching_looks_at_names_tags_places_scenes_and_never_offers_a_rejected_sound(film, tmp_path):
    rain = asset(film, tmp_path, "sfx", "Rain on roof.wav", 3.0, category="ambience", tags=["rain", "night"], places=["Kitchen"], scenes=[1])
    asset(film, tmp_path, "sfx", "Door slam.wav", 1.0, hz=330, tags=["door"])
    bad = asset(film, tmp_path, "sfx", "Rain heavy.wav", 2.5, hz=440, tags=["rain"])
    A.approve(film, bad["id"], "rejected")
    lib = A.load(film)
    rows = Q.match_assets(lib, "ambience", "rain falling steady", ["Kitchen"], 1)
    assert rows[0]["asset_id"] == rain["id"] and "rain" in rows[0]["why"] and all(r["asset_id"] != bad["id"] for r in rows)
    assert Q.match_assets(lib, "music", "rain") == []                                   # a sound effect is not offered as music
    assert Q.match_assets(lib, "sfx", "spaceship") == []


def test_quick_ideas_are_free_local_and_find_what_is_already_in_the_library(film, tmp_path):
    rain = asset(film, tmp_path, "sfx", "Rain.wav", 3.0, category="ambience", tags=["rain"])
    s = first_shot(film)
    S.set_fields(film, s["id"], {"sound": "A kettle clicks off, quietly"})
    r = Q.quick_ideas(film, 1)
    whats = [i["what"] for i in r["ideas"]]
    assert "A kettle clicks off, quietly" in whats[0] and r["source"] == "quick"
    ideas = {i["what"]: i for i in r["ideas"]}
    assert "Rain falling" in ideas and ideas["Rain falling"]["matches"][0]["asset_id"] == rain["id"]
    assert not os.path.exists(os.path.join(film, "audio", "cues.json"))                    # suggestions are not saved
    with pytest.raises(SystemExit):
        Q.quick_ideas(film, 99)
    y = Q.quick_ideas(film, 2)
    assert any("Children" in i["what"] for i in y["ideas"])


# ---------------------------------------------------------------- the sound director (the writing AI)

def fake_ai(monkeypatch, out, seen=None):
    def call(client, model, system, user, name, schema):
        if seen is not None:
            seen.append({"system": system, "user": json.loads(user)})
        return out
    monkeypatch.setattr(assist, "_call", call)
    import filmcrafter_engine.director as D
    import filmcrafter_engine.llm as L
    monkeypatch.setattr(L, "client", lambda: object())
    monkeypatch.setattr(D, "resolve_model", lambda c, m: "test-model")


def test_the_director_sees_the_scene_the_style_and_the_library_and_only_proposes(film, tmp_path, monkeypatch):
    rain = asset(film, tmp_path, "sfx", "Rain.wav", 3.0, category="ambience", tags=["rain"])
    bible.update_sound_style(film, {"sound_style": {"sound": {"philosophy": "Quiet and close"}, "music": {"genre": "Chamber"}}})
    s = first_shot(film)
    seen = []
    fake_ai(monkeypatch, {"cues": [
        {"kind": "ambience", "what": "Rain on the roof", "shot": "", "loop": True, "why": "It is raining.", "search": "rain roof"},
        {"kind": "sfx", "what": "Kettle", "shot": s["id"], "loop": True, "why": "She pours tea.", "search": "kettle"},                 # loop is only for ambience
        {"kind": "laser", "what": "Nonsense", "shot": "", "loop": False, "why": "", "search": ""},                                       # unknown kind: dropped
        {"kind": "music", "what": "", "shot": "", "loop": False, "why": "", "search": ""},                                               # empty: dropped
        {"kind": "sfx", "what": "Door", "shot": "S99-99", "loop": False, "why": "x", "search": "door"}]}, seen)
    est = Q.director_estimate(film, 1)
    assert "usd" in est and "library" in est["sends"] and not seen                                                                     # the price is known before anything is sent
    r = Q.director_suggest(film, 1)
    b = seen[0]["user"]
    assert b["place"] == "Kitchen" and b["sound_style"]["philosophy"] == "Quiet and close" and b["sound_style"]["music_genre"] == "Chamber" and b["already_in_the_library"][0]["id"] == rain["id"]
    assert "Quiet is a choice" in seen[0]["system"]
    assert [i["what"] for i in r["ideas"]] == ["Rain on the roof", "Kettle", "Door"]
    assert r["ideas"][0]["matches"][0]["asset_id"] == rain["id"] and r["ideas"][0]["loop"] is True and r["ideas"][1]["loop"] is False and r["ideas"][1]["shot"] == s["id"] and r["ideas"][2]["shot"] is None
    assert not os.path.exists(os.path.join(film, "audio", "cues.json"))                                                                 # nothing was saved


# ---------------------------------------------------------------- dialogue is listed, not copied

def test_dialogue_shows_up_beside_the_cues_without_being_copied(film, tmp_path):
    sid = next(x["id"] for x in V.status(film)["shots"] if any(p["name"] == "Sarah" for p in x["people"]))
    src = wav(tmp_path, "sarah.wav", 1.2)
    V.attach(film, sid, "Sarah", src)
    r = Q.listing(film, 1)
    assert [x["speaker"] for x in r["dialogue"]] == ["Sarah"] and r["dialogue"][0]["derived"] is True and r["dialogue"][0]["file"].startswith("voice/")
    assert r["cues"] == [] and not os.path.exists(os.path.join(film, "audio", "cues.json"))


# ---------------------------------------------------------------- safety and compatibility

def test_a_film_with_no_cues_opens_as_before_and_a_damaged_cue_file_is_never_replaced(film, tmp_path):
    assert Q.listing(film)["cues"] == [] and not os.path.exists(os.path.join(film, "audio"))
    a = asset(film, tmp_path)
    Q.add(film, {"asset_id": a["id"], "scene": 1})
    p = os.path.join(film, "audio", "cues.json")
    if os.path.exists(p + ".bak"):
        os.remove(p + ".bak")
    open(p, "wb").write(b'{"cues": [{"id"')
    with pytest.raises(SystemExit, match="damaged"):
        Q.add(film, {"asset_id": a["id"], "scene": 1})
    assert open(p, "rb").read() == b'{"cues": [{"id"'


def test_cues_travel_in_a_backup_and_a_restore_brings_them_back(film, tmp_path):
    a = asset(film, tmp_path)
    cid = Q.add(film, {"asset_id": a["id"], "scene": 1})["id"]
    filmbackup.make(film)
    bk = filmbackup.list_backups(film)[0]["name"]
    with zipfile.ZipFile(os.path.join(film, "backups", bk)) as z:
        assert "files/audio/cues.json" in z.namelist()
    os.remove(os.path.join(film, "audio", "cues.json"))
    filmbackup.restore(film, bk)
    assert Q.listing(film)["cues"][0]["id"] == cid


def test_two_cues_added_at_once_are_both_kept(film, tmp_path):
    import multiprocessing as mp
    a = asset(film, tmp_path)
    ctx = mp.get_context("spawn")
    ps = [ctx.Process(target=_add_in_process, args=(film, a["id"], i)) for i in range(3)]
    [p.start() for p in ps]
    [p.join(120) for p in ps]
    assert len(Q.listing(film)["cues"]) == 3


def _add_in_process(film, asset_id, i):
    from filmcrafter_engine import audiocues
    audiocues.add(film, {"asset_id": asset_id, "scene": 1, "start": i})


def test_the_command_line_speaks_the_engine_format_and_only_knows_its_actions(film, tmp_path, capsys):
    assert Q.main(["list", film]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["cues"] == []
    with pytest.raises(SystemExit):
        Q.main(["format_disk", film])
    assert Q.main(["add", film, "--data", json.dumps({"scene": 1})]) == 1
    assert "Choose a sound" in capsys.readouterr().out
