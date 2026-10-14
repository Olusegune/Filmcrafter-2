"""Stage F: nothing that depends on a voice or the planned sound is left looking current when it is not. The takes remember which voice they followed; the report names what changed after;
nothing is changed, deleted or re-made by the report; an approved take is kept. No provider is used."""
import json
import os
import time

import numpy as np
import pytest
import soundfile as sf

from filmcrafter_engine import audiocues as Q, audiolib as AL, bible, make, outdated as O, shots as S, story, voiceover as V
from tests.test_golden_film import SCRIPT, _clip, _job

pytestmark = pytest.mark.integration


def wav(path, secs=1.5, hz=300):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    t = np.arange(int(22050 * secs)) / 22050
    sf.write(path, (0.3 * np.sin(2 * np.pi * hz * t)).astype("float32"), 22050)
    return path


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    S.breakdown(d)
    make.sync(d)
    return d


def speaking_shot(film):
    return next(s["id"] for s in V.status(film)["shots"] if any(p["name"] == "Sarah" for p in s["people"]))


def take(film, sid, jid="v1", with_voice=True):
    """A finished video take for the shot, recorded the way the renderer records it (the exact voice it followed)."""
    rd = make.render_dir(film)
    os.makedirs(os.path.join(rd, "media"), exist_ok=True)
    _clip(os.path.join(rd, "media", f"{jid}.mp4"), 2)
    _job(film, sid, jid, "video", f"media/{jid}.mp4")
    p = os.path.join(rd, "jobs.json")
    data = json.load(open(p))
    j = next(x for x in data["jobs"] if x["id"] == jid)
    if with_voice:
        make.sync(film)                                                  # the render project holds its own copy of the voice, as it does when a take is sent
        j["voice_ref"] = V.clip_record(rd, sid)
    json.dump(data, open(p, "w"))
    return jid


def test_the_voice_a_take_followed_is_recorded_exactly_and_empty_for_a_shot_without_one(film, tmp_path):
    sid = speaking_shot(film)
    rd = make.render_dir(film)
    make.sync(film)
    assert V.clip_record(rd, sid) is None
    V.attach(film, sid, "Sarah", wav(str(tmp_path / "v" / "a.wav")))
    make.sync(film)
    r = V.clip_record(rd, sid)
    assert len(r["recordings"]) == 1 and r["recordings"][0]["speaker"] == "Sarah" and len(r["recordings"][0]["sha1"]) == 40 and r["digest"] and r["seconds"] > 1
    assert V.clip_record(rd, sid)["digest"] == r["digest"]                                 # the same voice gives the same record


def test_the_renderer_keeps_the_voice_with_the_take_it_sends(film):
    src = open(os.path.join(os.path.dirname(O.__file__), "render.py"), encoding="utf-8").read()
    assert "voice_ref=voice_ref" in src and "_vo.clip_record(d, j[\"shot_id\"])" in src and 'j.get("kind") == "lipsync" or (sung and sung.get("voiceover"))' in src


def test_a_replaced_voice_is_noticed_and_the_take_is_left_exactly_as_it_was(film, tmp_path):
    sid = speaking_shot(film)
    V.attach(film, sid, "Sarah", wav(str(tmp_path / "v" / "a.wav"), 1.5, 300))
    jid = take(film, sid)
    assert O.report(film)["clean"] is True
    jobs_before = open(os.path.join(make.render_dir(film), "jobs.json"), "rb").read()
    V.attach(film, sid, "Sarah", wav(str(tmp_path / "v" / "b.wav"), 1.7, 450))             # a new recording replaces it
    r = O.report(film)
    assert r["clean"] is False and len(r["takes"]) == 1
    row = r["takes"][0]
    assert row["shot"] == sid and row["take"] == jid and row["kind"] == "voice_changed" and "mouth may not match" in row["why"] and row["speakers"] == ["Sarah"]
    assert row["options"] == ["lipsync_pass", "new_take"] and row["kept"] is False
    assert open(os.path.join(make.render_dir(film), "jobs.json"), "rb").read() == jobs_before    # reporting changed nothing


def test_a_removed_or_added_voice_is_named_for_what_it_is(film, tmp_path):
    sid = speaking_shot(film)
    V.attach(film, sid, "Sarah", wav(str(tmp_path / "v" / "a.wav")))
    take(film, sid)
    V.remove(film, sid, "Sarah")
    assert O.report(film)["takes"][0]["kind"] == "voice_removed"
    other = next(s["id"] for s in V.status(film)["shots"] if s["id"] != sid and any(p["lines"] for p in s["people"]))
    jid = take(film, other, "v2", with_voice=False)
    j = json.load(open(os.path.join(make.render_dir(film), "jobs.json")))
    next(x for x in j["jobs"] if x["id"] == jid)["voice_ref"] = {"digest": "x", "recordings": []}
    json.dump(j, open(os.path.join(make.render_dir(film), "jobs.json"), "w"))
    person = next(p["name"] for s in V.status(film)["shots"] if s["id"] == other for p in s["people"] if p["lines"])
    V.attach(film, other, person, wav(str(tmp_path / "v" / "c.wav")))
    kinds = {t["shot"]: t["kind"] for t in O.report(film)["takes"]}
    assert kinds[other] == "voice_added"


def test_a_take_made_before_this_was_recorded_is_not_judged_and_is_counted_honestly(film, tmp_path):
    sid = speaking_shot(film)
    V.attach(film, sid, "Sarah", wav(str(tmp_path / "v" / "a.wav")))
    take(film, sid, with_voice=False)
    V.attach(film, sid, "Sarah", wav(str(tmp_path / "v" / "b.wav"), 1.7, 450))
    r = O.report(film)
    assert r["takes"] == [] and r["unchecked_takes"] == 1 and r["clean"] is True              # nothing is claimed about a take that carries no record


def test_an_approved_take_is_reported_with_a_note_and_never_replaced(film, tmp_path):
    sid = speaking_shot(film)
    V.attach(film, sid, "Sarah", wav(str(tmp_path / "v" / "a.wav")))
    jid = take(film, sid)
    from filmcrafter_engine import library
    library.approve(make.render_dir(film), sid, jid)
    V.attach(film, sid, "Sarah", wav(str(tmp_path / "v" / "b.wav"), 1.7, 450))
    row = O.report(film)["takes"][0]
    assert row["take"] == jid and row["kept"] is True and "kept until you choose" in row["note"]
    assert library.shot_state(make.render_dir(film))[sid]["approved"] == jid                  # still approved, still the take in use


# ---------------------------------------------------------------- the planned sound and the finished film

def test_a_replaced_sound_is_flagged_on_its_cue_and_the_cue_is_untouched(film, tmp_path):
    a = AL.import_files(film, "sfx", [wav(str(tmp_path / "s" / "k.wav"), 1.0, 700)])["assets"][0]
    cid = Q.add(film, {"asset_id": a["id"], "scene": 1})["id"]
    assert O.report(film)["cues"] == []
    lib = json.load(open(os.path.join(film, "audio", "library.json")))
    lib["assets"][0]["sha1"] = "0" * 40                                                       # the sound is replaced by different content
    json.dump(lib, open(os.path.join(film, "audio", "library.json"), "w"))
    r = O.report(film)
    assert [c["id"] for c in r["cues"]] == [cid] and r["cues"][0]["codes"] == ["asset_changed"] and r["clean"] is False
    assert Q.listing(film)["cues"][0]["made_from"]["asset_sha1"] == a["sha1"]                 # still as it was set up


def test_a_film_exported_before_its_sound_changed_says_so_and_a_fresh_export_is_clean(film, tmp_path):
    rd = make.render_dir(film)
    os.makedirs(os.path.join(rd, "exports"), exist_ok=True)
    out = os.path.join(rd, "exports", "film.mp4")
    open(out, "wb").write(b"x" * 100)
    a = AL.import_files(film, "sfx", [wav(str(tmp_path / "s" / "k.wav"), 1.0, 700)])["assets"][0]
    cid = Q.add(film, {"asset_id": a["id"], "scene": 1})["id"]
    assert O.report(film)["film"] is None                                                      # the plan was made before the export: nothing to say
    os.utime(out, (time.time() - 3600, time.time() - 3600))                                    # the export is an hour old
    r = O.report(film)
    assert r["film"] and r["film"]["export"] == "film.mp4" and "the planned sound" in r["film"]["changed"] and "Export it again" in r["film"]["why"]
    os.utime(out, None)
    assert O.report(film)["film"] is None
    assert cid


def test_a_film_with_nothing_made_reports_clean_and_the_command_line_speaks_the_engine_format(film, capsys):
    assert O.report(film)["clean"] is True
    assert O.main(["report", film]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["clean"] is True
    with pytest.raises(SystemExit):
        O.main(["delete_everything", film])
