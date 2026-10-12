"""Your own recorded voices, attached to the people in each shot: naming, matching, attaching, the render request, and the sound at export."""
import json
import os

import numpy as np
import pytest
import soundfile as sf

from filmcrafter_engine import bible, make, render, shots, story, voiceover as V

SCRIPT = "INT. YARD - DAY\n\nA schoolyard.\n\nLILA\nIt looked weird.\n\nCHLOE\n(quietly)\nI know.\n\nLILA\nSee?\n\nEXT. ROAD - NIGHT\n\nRain.\n\nCHLOE DAD\nGet in.\n"


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    shots.breakdown(d)
    return d


def tone(tmp_path, name, secs, freq=220.0):
    t = np.arange(int(44100 * secs)) / 44100
    p = str(tmp_path / name)
    sf.write(p, (0.3 * np.sin(2 * np.pi * freq * t)).astype("float32"), 44100)
    return p


def rows(film, tmp_path, *files):
    return {os.path.basename(r["file"]): r for r in V.match(film, [str(tmp_path / f) for f in files])}


def first_shot_with(film, speaker):
    return next(s["id"] for s in V.status(film)["shots"] if any(p["name"].lower() == speaker.lower() for p in s["people"]))


# ---------------------------------------------------------------- names

def test_a_shot_id_is_found_however_it_is_typed():
    assert [V.shot_id_in(x) for x in ("S01-04", "s1_4", "CHLOE_S01-04_take2", "x S2.10 y", "S001-004")] == ["S01-04", "S01-04", "S01-04", "S02-10", "S01-04"]
    assert V.shot_id_in("nothing here") is None and V.shot_id_in("S1-2345") is None


def test_files_are_matched_to_the_person_and_shot_in_their_names(film, tmp_path):
    sid = first_shot_with(film, "Lila")
    for n in (f"LILA_{sid}.wav", f"{sid}_lila.wav", f"Lila {sid} take 3.wav"):
        tone(tmp_path, n, 1.0)
    got = rows(film, tmp_path, f"LILA_{sid}.wav", f"{sid}_lila.wav", f"Lila {sid} take 3.wav")
    for r in got.values():
        assert r["status"] in ("ok", "duplicate") and r["speaker"] == "Lila" and r["shot"] == sid
    assert [r["status"] for r in got.values()].count("ok") == 1                      # the same person in the same shot twice in one batch: the second is flagged


def test_the_longer_name_wins_and_nothing_is_guessed(film, tmp_path):
    dad = next(s["id"] for s in V.status(film)["shots"] if any(p["name"] == "Chloe Dad" for p in s["people"]))
    tone(tmp_path, f"chloe_dad_{dad}.wav", 1)
    tone(tmp_path, f"{dad}_zed.wav", 1)
    tone(tmp_path, "no_shot_in_name.wav", 1)
    tone(tmp_path, "S09-09_lila.wav", 1)
    got = rows(film, tmp_path, f"chloe_dad_{dad}.wav", f"{dad}_zed.wav", "no_shot_in_name.wav", "S09-09_lila.wav")
    assert got[f"chloe_dad_{dad}.wav"]["speaker"] == "Chloe Dad" and got[f"chloe_dad_{dad}.wav"]["status"] == "ok"
    assert got[f"{dad}_zed.wav"]["status"] == "no_speaker" and "zed" in got[f"{dad}_zed.wav"]["note"]      # a name nobody has is asked about, not replaced by the only speaker
    assert got["no_shot_in_name.wav"]["status"] == "no_shot"
    assert got["S09-09_lila.wav"]["status"] == "no_shot"


def test_a_file_with_only_a_shot_belongs_to_the_one_person_who_speaks_there(film, tmp_path):
    dad = next(s["id"] for s in V.status(film)["shots"] if any(p["name"] == "Chloe Dad" for p in s["people"]))
    tone(tmp_path, f"{dad}.wav", 1)
    assert rows(film, tmp_path, f"{dad}.wav")[f"{dad}.wav"]["speaker"] == "Chloe Dad"


def test_a_person_who_is_not_in_the_shot_is_said_so(film, tmp_path):
    dad = next(s["id"] for s in V.status(film)["shots"] if any(p["name"] == "Chloe Dad" for p in s["people"]))
    tone(tmp_path, f"lila_{dad}.wav", 1)
    r = rows(film, tmp_path, f"lila_{dad}.wav")[f"lila_{dad}.wav"]
    assert r["status"] == "not_in_shot" and "not in" in r["note"]


def test_bad_files_are_refused_with_a_reason_and_match_changes_nothing(film, tmp_path):
    (tmp_path / "S01-02_lila.txt").write_text("hello")
    sf.write(str(tmp_path / "S01-02_chloe.wav"), np.zeros(44100, dtype="float32"), 44100)
    (tmp_path / "S01-02_lila.mp3").write_bytes(b"not audio at all")
    before = sorted(os.listdir(film))
    got = rows(film, tmp_path, "S01-02_lila.txt", "S01-02_chloe.wav", "S01-02_lila.mp3", "missing.wav")
    assert all(r["status"] == "bad_file" for r in got.values())
    assert "Use a WAV" in got["S01-02_lila.txt"]["note"] and "silent" in got["S01-02_chloe.wav"]["note"]
    assert sorted(os.listdir(film)) == before and not os.path.exists(os.path.join(film, "voice"))


# ---------------------------------------------------------------- attaching

def test_attaching_copies_the_recording_and_lengthens_a_short_shot(film, tmp_path):
    sid = first_shot_with(film, "Lila")
    src = tone(tmp_path, f"LILA_{sid}.wav", 6.1)
    before = open(src, "rb").read()
    out = V.attach(film, sid, "Lila", src)
    assert out["lengthened_to"] and out["lengthened_to"] >= 6.5 and out["seconds"] == 6.1
    assert shots._contract(film, sid)["generation"]["duration"] == out["lengthened_to"]
    assert open(src, "rb").read() == before                                            # your file is untouched
    st = V.status(film)
    shot = next(s for s in st["shots"] if s["id"] == sid)
    lila = next(p for p in shot["people"] if p["name"] == "Lila")
    assert lila["recording"]["seconds"] == 6.1 and st["recorded"] == 1 and st["missing"] == st["people"] - 1
    assert os.path.isfile(os.path.join(film, *lila["recording"]["file"].split("/")))


def test_a_shot_is_never_shortened_and_a_long_line_is_reported(film, tmp_path):
    sid = first_shot_with(film, "Lila")
    shots.set_fields(film, sid, {"generation": {"duration": 12}})
    out = V.attach(film, sid, "Lila", tone(tmp_path, "a.wav", 2.0))
    assert "lengthened_to" not in out and shots._contract(film, sid)["generation"]["duration"] == 12
    long = V.attach(film, sid, "Lila", tone(tmp_path, "b.wav", 16.0), fit=False)
    assert any("longer than a video model" in n for n in long["notes"])


def test_replacing_keeps_the_old_recording_and_removing_deletes_nothing(film, tmp_path):
    sid = first_shot_with(film, "Lila")
    V.attach(film, sid, "Lila", tone(tmp_path, "one.wav", 1.0))
    again = V.attach(film, sid, "Lila", tone(tmp_path, "two.wav", 1.5))
    assert again["replaced"] is True
    kept = os.listdir(os.path.join(film, "voice", "_removed"))
    assert len(kept) == 1
    V.remove(film, sid, "Lila")
    assert V.status(film)["recorded"] == 0 and len(os.listdir(os.path.join(film, "voice", "_removed"))) == 2


def test_import_attaches_what_can_be_and_reports_the_rest(film, tmp_path):
    sid = first_shot_with(film, "Lila")
    good = tone(tmp_path, "g.wav", 1.0)
    res = V.import_files(film, [{"file": good, "shot": sid, "speaker": "Lila"}, {"file": str(tmp_path / "gone.wav"), "shot": sid, "speaker": "Lila"}, {"file": good, "shot": "../../evil", "speaker": "Lila"}])
    assert len(res["attached"]) == 1 and len(res["failed"]) == 2
    assert any("not valid" in f["why"] for f in res["failed"])
    assert res["status"]["recorded"] == 1


def test_nothing_from_outside_can_choose_where_a_file_goes(film, tmp_path):
    sid = first_shot_with(film, "Lila")
    src = tone(tmp_path, "x.wav", 1.0)
    for bad in ("../../outside", "a/b", "C:\\x", ""):
        with pytest.raises(SystemExit):
            V.attach(film, bad, "Lila", src)
    V.attach(film, sid, "../../../evil\\name", src)
    base = os.path.dirname(film)
    inside = [os.path.join(r, f) for r, _, fs in os.walk(film) for f in fs]
    assert all(p.startswith(film + os.sep) for p in inside)
    assert all(".." not in os.path.relpath(p, film) for p in inside)
    assert not [f for f in os.listdir(base) if f.endswith(".wav")]


# ---------------------------------------------------------------- the render project and the request

@pytest.fixture
def voiced(film, tmp_path):
    sid = first_shot_with(film, "Lila")
    V.import_files(film, [{"file": tone(tmp_path, "lila.wav", 3.0), "shot": sid, "speaker": "Lila"}])
    return film, os.path.join(film, "render"), sid


def test_the_render_project_gets_the_recording_and_reads_it_back(voiced):
    film, rd, sid = voiced
    rows_ = V.for_shot(rd, sid)
    assert len(rows_) == 1 and rows_[0]["speaker"] == "Lila" and rows_[0]["line"] == "It looked weird." and rows_[0]["path"].startswith("assets/voice/")
    assert V.for_shot(rd, "S09-09") == []


def test_a_recorded_shot_is_spoken_by_the_recording(voiced):
    film, rd, sid = voiced
    plan = json.load(open(os.path.join(rd, "production.json"), encoding="utf-8"))
    shot, _ = render._shot(plan, sid)
    s = render.singing(rd, shot, plan)
    assert s["voiceover"] and s["spoken"] and s["performer"] == "Lila"
    other = next(x["id"] for sc in plan["scenes"] for x in sc["shots"] if x["id"] != sid)
    assert not (render.singing(rd, render._shot(plan, other)[0], plan) or {}).get("voiceover")


def test_the_video_request_carries_the_recording_and_says_who_speaks(voiced):
    film, rd, sid = voiced
    r = render.preview(rd, sid, "kie", "bytedance/seedance-2", {}, "video")
    man = r["manifest"]
    audio = r["payload"].get(man["roles"]["ref_audio"])
    assert audio and str(audio[0]).endswith(".mp3")
    prompt = r["payload"][man["roles"]["prompt"]]
    assert "Lila speaks along to the reference audio" in prompt and "It looked weird." in prompt
    shown = [x for x in r["inputs"] if x["role"] == "audio"] if "inputs" in r else []
    assert not shown or "Your recording of Lila" in shown[0]["label"]


def test_the_recording_beats_native_speech_and_the_shot_without_one_is_untouched(voiced):
    film, rd, sid = voiced
    man = render.manifest("kie", "bytedance/seedance-2")
    plan = json.load(open(os.path.join(rd, "production.json"), encoding="utf-8"))
    shot, _ = render._shot(plan, sid)
    assert render.native_for(rd, shot, man) is None
    assert render.audio_first(rd, {"lip_sync_mode": "auto", "lip_sync": "auto"}, shot, plan, man) is True
    assert render.audio_first(rd, {"lip_sync_mode": "auto", "lip_sync": "off"}, shot, plan, man) is False


def test_a_slice_is_one_clip_cut_to_the_shot_and_cached(voiced):
    film, rd, sid = voiced
    a = V.slice_for(rd, sid, 2.0)
    assert a.endswith(".mp3") and os.path.getsize(a) > 0
    assert V.slice_for(rd, sid, 2.0) == a
    assert V.slice_for(rd, sid, 3.5) != a


def test_two_people_in_one_shot_become_one_clip_in_speaking_order(film, tmp_path):
    sid = first_shot_with(film, "Lila")                                                    # Lila speaks to Chloe: both are in the shot
    names = ["Lila", "Chloe"]
    V.import_files(film, [{"file": tone(tmp_path, "a.wav", 1.0), "shot": sid, "speaker": names[0]}, {"file": tone(tmp_path, "b.wav", 1.0, 440), "shot": sid, "speaker": names[1]}])
    rd = os.path.join(film, "render")
    assert len(V.for_shot(rd, sid)) == 2
    clip = V.slice_for(rd, sid, 5.0)
    x, rate = sf.read(clip)
    assert 2.0 < len(x) / rate < 3.2                                                       # two seconds of voice and the gap between them


# ---------------------------------------------------------------- the sound at export

def test_the_recordings_are_laid_on_the_film_at_their_shots(voiced, tmp_path):
    film, rd, sid = voiced
    base = str(tmp_path / "base.wav")
    sf.write(base, np.zeros(44100 * 10, dtype="float32"), 44100)
    out = V.mix_into(rd, base, [{"shot": sid, "start": 4.0, "end": 8.0}, {"shot": "S09-09", "start": 0.0, "end": 2.0}], 10.0, str(tmp_path / "mix.wav"))
    assert out and out["recordings"] == 1
    x, rate = sf.read(out["path"])
    assert abs(x[: int(3.9 * rate)]).max() == 0 and abs(x[int(4.2 * rate): int(6.8 * rate)]).max() > 0.2   # silence before the shot, the voice inside it
    assert abs(x[int(7.5 * rate):]).max() == 0                                                              # the 3 s recording has ended
    assert V.mix_into(rd, base, [{"shot": "S09-09", "start": 0.0, "end": 2.0}], 10.0, str(tmp_path / "none.wav")) is None


def test_a_recording_is_cut_at_the_end_of_its_shot_and_never_clips(voiced, tmp_path):
    film, rd, sid = voiced
    base = str(tmp_path / "base.wav")
    sf.write(base, (0.9 * np.ones(44100 * 6)).astype("float32"), 44100)
    out = V.mix_into(rd, base, [{"shot": sid, "start": 1.0, "end": 2.0}], 6.0, str(tmp_path / "mix.wav"))
    x, rate = sf.read(out["path"])
    assert abs(x).max() <= 0.98 + 1e-3 and len(x) == 6 * rate


def test_the_command_line_speaks_json(film, tmp_path, capsys):
    sid = first_shot_with(film, "Lila")
    f = tone(tmp_path, f"LILA_{sid}.wav", 1.0)
    assert V.main(["match", film, "--data", json.dumps({"files": [f]})]) == 0
    res = json.loads(capsys.readouterr().out.strip().splitlines()[-1])["data"]
    assert res["rows"][0]["status"] == "ok"
    assert V.main(["import", film, "--data", json.dumps({"items": [{"file": f, "shot": sid, "speaker": "Lila"}]})]) == 0
    capsys.readouterr()
    assert V.main(["status", "nowhere-at-all"]) == 1


def test_the_editor_hand_off_carries_each_recording_named_for_its_shot_and_person(voiced, tmp_path):
    from filmcrafter_engine import interchange
    film, rd, sid = voiced
    res = interchange.write(film)
    out = res["dir"]
    got = os.listdir(os.path.join(out, "audio", "voice"))
    assert got == [f"{sid}-lila.wav"] and res["files"]["voiceover"] == "audio/voice"
    assert f"audio/voice/{sid}-lila.wav" in open(os.path.join(out, "shots.csv"), encoding="utf-8").read()


def test_the_exported_film_plays_the_recording_at_its_shot(voiced):
    from filmcrafter_engine import export, shotsound
    film, rd, sid = voiced
    res = export.build(rd, "preview")                                       # no takes yet: the shots are picture cards, and still speak
    plan = json.load(open(os.path.join(rd, "production.json"), encoding="utf-8"))
    start = next(s["start"] for sc in plan["scenes"] for s in sc["shots"] if s["id"] == sid)
    x = shotsound.decode(res["path"], 1)
    assert len(x)
    inside = x[int((start + 0.3) * shotsound.RATE): int((start + 2.5) * shotsound.RATE)]
    before = x[: max(1, int((start - 0.1) * shotsound.RATE))] if start > 0.2 else x[:0]
    assert float(np.abs(inside).max()) > 0.1 and (not len(before) or float(np.abs(before).max()) < 0.01)
    assert res["voiceovers"] == 1


# ---------------------------------------------------------------- a film from somewhere else is not trusted to point outside itself

@pytest.mark.parametrize("bad", ["../secret.wav", "..\\secret.wav", "voice/../../secret.wav", "/etc/passwd", "\\\\server\\share\\x.wav", "C:/Windows/x.wav", "C:x.wav", "", None])
def test_a_path_that_leaves_the_film_is_never_followed(tmp_path, bad):
    assert V.inside(str(tmp_path), bad) is None


def test_a_path_inside_the_film_is_followed(tmp_path):
    assert V.inside(str(tmp_path), "voice/S01-02/lila.wav") == os.path.realpath(str(tmp_path / "voice" / "S01-02" / "lila.wav"))


def test_a_hostile_voice_json_cannot_make_the_film_copy_or_send_a_file_from_outside(film, tmp_path):
    secret = tmp_path / "secret.wav"
    sf.write(str(secret), (0.3 * np.ones(44100)).astype("float32"), 44100)
    sid = first_shot_with(film, "Lila")
    os.makedirs(os.path.join(film, "voice"), exist_ok=True)
    json.dump({"schema": 1, "shots": {sid: [{"key": "lila", "speaker": "Lila", "file": "../../../" + str(secret).replace("\\", "/").lstrip("/"), "name": "x", "seconds": 1.0, "rms_db": -10, "peak_db": -3}]}},
              open(os.path.join(film, "voice", "voice.json"), "w"))
    assert V.status(film)["recorded"] == 0
    rd = os.path.join(film, "render")
    os.makedirs(rd, exist_ok=True)
    assert V.to_render(film, rd) == 0 and not os.path.isdir(os.path.join(rd, "assets", "voice"))
    json.dump({"schema": 1, "shots": {sid: [{"speaker": "Lila", "key": "lila", "path": "../../" + secret.name, "seconds": 1.0, "line": ""}]}}, open(os.path.join(rd, "voiceover.json"), "w"))
    assert V.for_shot(rd, sid) == []


def test_an_endless_recording_is_refused(tmp_path, monkeypatch):
    from filmcrafter_engine import render as R
    src = tmp_path / "long.wav"
    sf.write(str(src), (0.3 * np.ones(4410)).astype("float32"), 44100)
    monkeypatch.setattr(R, "take_duration", lambda p: 3 * 3600.0)
    info = V.probe(str(src))
    assert not info["ok"] and "20 minutes" in info["why"]


# ---------------------------------------------------------------- two people, one shot (phase 3)

@pytest.fixture
def two(film, tmp_path):
    sid = first_shot_with(film, "Lila")                                                   # Lila speaks to Chloe: both are in the shot
    V.import_files(film, [{"file": tone(tmp_path, "a.wav", 2.0), "shot": sid, "speaker": "Lila"}, {"file": tone(tmp_path, "b.wav", 1.5, 440), "shot": sid, "speaker": "Chloe"}])
    return film, os.path.join(film, "render"), sid


def test_each_person_has_a_window_in_the_shots_one_clip(two):
    film, rd, sid = two
    w = V.windows(rd, sid)
    assert [x["speaker"] for x in w] == ["Lila", "Chloe"]
    assert w[0]["start"] == 0.0 and w[0]["end"] == 2.0
    assert w[1]["start"] == pytest.approx(2.0 + V.GAP, abs=0.01) and w[1]["end"] == pytest.approx(2.0 + V.GAP + 1.5, abs=0.01)
    assert shots._contract(film, sid)["generation"]["duration"] >= 2.0 + V.GAP + 1.5 + V.FIT_MARGIN - 0.5     # the shot was lengthened to hold both


def test_the_prompt_says_who_speaks_when_and_that_the_others_listen(two):
    film, rd, sid = two
    r = render.preview(rd, sid, "kie", "bytedance/seedance-2", {}, "video")
    p = r["payload"][r["manifest"]["roles"]["prompt"]]
    assert "Lila and Chloe speak in turn" in p and "Lila from 0.0 to 2.0 s" in p and "then Chloe from 2.2 to 3.8 s" in p
    assert "others listen with their mouths closed" in p
    assert len(r["payload"][r["manifest"]["roles"]["ref_audio"]]) == 1                    # one clip: the order and the gaps are in it
    assert any("recordings of Lila and Chloe" in x["label"] for x in r.get("inputs", []) if x["role"] == "audio") or "inputs" not in r


def test_one_person_keeps_the_single_speaker_wording(voiced):
    film, rd, sid = voiced
    r = render.preview(rd, sid, "kie", "bytedance/seedance-2", {}, "video")
    p = r["payload"][r["manifest"]["roles"]["prompt"]]
    assert "speak in turn" not in p and "Lila speaks along to the reference audio" in p


def test_a_file_with_no_shot_in_its_name_goes_to_the_shot_being_looked_at(film, tmp_path):
    sid = first_shot_with(film, "Lila")
    tone(tmp_path, "lila_final.wav", 1.0)
    tone(tmp_path, "take.wav", 1.0)
    got = {os.path.basename(r["file"]): r for r in V.match(film, [str(tmp_path / "lila_final.wav"), str(tmp_path / "take.wav")], sid)}
    assert got["lila_final.wav"]["shot"] == sid and got["lila_final.wav"]["speaker"] == "Lila" and got["lila_final.wav"]["status"] == "ok"
    assert got["take.wav"]["shot"] == sid                                                  # the shot is known; who is not guessed past two people
    assert V.match(film, [str(tmp_path / "lila_final.wav")], "../../x")[0]["status"] == "no_shot"         # a hint that is not a shot of this film is ignored


# ---------------------------------------------------------------- the lip-sync pass after the take (phase 4)

def test_the_lip_sync_pass_follows_your_recording_when_the_shot_has_one(voiced, monkeypatch):
    film, rd, sid = voiced
    man = render.manifest("kie", "volcengine/video-to-video-lip-sync")
    take = {"output": "gen/take.mp4"}
    os.makedirs(os.path.join(rd, "gen"), exist_ok=True)
    monkeypatch.setattr(render, "take_duration", lambda p: 2.5)
    plan = json.load(open(os.path.join(rd, "production.json"), encoding="utf-8"))
    shot, _ = render._shot(plan, sid)
    p = render.compile_lipsync(rd, man, shot, take, None)
    audio = p[man["roles"]["src_audio"]]
    assert audio.startswith("project:cache/voice/") and audio.endswith(".mp3")                 # the recording, cut to the take's length, not the song
    assert p.get("separate_vocal") in (False, None)
