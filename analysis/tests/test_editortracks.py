"""The editor hand-off carries sound on tracks: each person's voice on a track of their own at its real place on the film, and the approved effects, ambience and music on theirs."""
import json
import os
import xml.etree.ElementTree as ET

import numpy as np
import pytest
import soundfile as sf

from filmcrafter_engine import audiocues as Q, audiolib as AL, bible, editortracks as T, interchange as X, make, shots as S, story, voiceover as V

SCRIPT = """INT. KITCHEN - MORNING

Sarah pours tea.

SARAH
He said he would call.

JOHN
Did you say something?
"""
FPS = X.FPS


def tone(path, secs, rate=22050):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sf.write(path, (0.3 * np.sin(np.arange(int(rate * secs)) / 20)).astype("float32"), rate)
    return path


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "Last Train", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    S.breakdown(d)
    sid = next(s for s in S._index(d)["order"] if "He said" in json.dumps(S._contract(d, s)["dialogue"]))
    S.set_fields(d, sid, {"dialogue": [{"speaker": "SARAH", "line": "He said he would call."}, {"speaker": "JOHN", "line": "Did you say something?"}], "generation": {"duration": 6.0}})
    for who, secs in (("Sarah", 2.0), ("John", 1.5)):
        V.attach(d, sid, who, tone(str(tmp_path / f"{who}.wav"), secs))
    make.sync(d)
    return d, sid


def rows_of(d):
    return X.gather(d)["rows"]


def test_each_person_gets_a_track_and_the_second_speaker_follows_the_first(film):
    d, sid = film
    rd = make.render_dir(d)
    row = next(r for r in rows_of(d) if r["id"] == sid)
    tracks = T.voice_tracks(rd, [row], FPS)
    assert [t["name"] for t in tracks] == ["Voice John", "Voice Sarah"]
    sarah = next(t for t in tracks if "Sarah" in t["name"])["clips"][0]
    john = next(t for t in tracks if "John" in t["name"])["clips"][0]
    assert sarah["start"] == row["start"] and sarah["frames"] == 2 * FPS
    assert john["start"] == row["start"] + 2 * FPS + int(round(V.GAP * FPS)) and john["frames"] == int(1.5 * FPS)


def test_a_j_cut_starts_the_voice_before_its_picture_and_an_l_cut_lets_it_run_on(film):
    d, sid = film
    rd = make.render_dir(d)
    row = dict(next(r for r in rows_of(d) if r["id"] == sid))
    row["start"] = 10 * FPS                                                       # as if it sat later in the film
    row["lead"] = 1.0
    sarah = next(t for t in T.voice_tracks(rd, [row], FPS) if "Sarah" in t["name"])["clips"][0]
    assert sarah["start"] == 9 * FPS
    row["lead"], row["tail"], row["frames"] = 0.0, 2.0, 1 * FPS                   # a shot shorter than its lines, with an L cut
    john = next(t for t in T.voice_tracks(rd, [row], FPS) if "John" in t["name"])
    assert john["clips"][0]["frames"] <= 3 * FPS - (2 * FPS + int(round(V.GAP * FPS))) + 1, "the voice is cut where the shot and its tail end"


def test_a_shot_with_no_recording_adds_no_track(film):
    d, sid = film
    rd = make.render_dir(d)
    others = [r for r in rows_of(d) if r["id"] != sid]
    assert T.voice_tracks(rd, others, FPS) == []


def cue(d, tmp_path, kind, secs, **kw):
    a = AL.import_files(d, kind, [tone(str(tmp_path / "src" / f"{kind}.wav"), secs)])["assets"][-1]
    made = Q.add(d, {"asset_id": a["id"], "scene": 1, "kind": kind, **kw})
    Q.approve(d, made["id"], "approved")
    return made["id"]


def test_approved_effects_and_music_get_their_own_tracks_and_a_loop_fills_its_time(film, tmp_path):
    d, sid = film
    rows = rows_of(d)
    total = sum(r["frames"] for r in rows)
    cue(d, tmp_path, "sfx", 1.0, shot=sid, start=0.5)
    cue(d, tmp_path, "music", 2.0, loop=True)
    names = [t["name"] for t in T.cue_tracks(d, rows, FPS, total)]
    assert names == ["Sound effects", "Music"]
    music = next(t for t in T.cue_tracks(d, rows, FPS, total) if t["role"] == "music")
    assert len(music["clips"]) >= 2 and music["clips"][0]["start"] == 0, "a loop is laid end to end"
    assert all(a["start"] + a["frames"] == b["start"] for a, b in zip(music["clips"], music["clips"][1:]))
    sfx = next(t for t in T.cue_tracks(d, rows, FPS, total) if t["role"] == "sfx")["clips"][0]
    row = next(r for r in rows if r["id"] == sid)
    assert sfx["start"] == row["start"] + int(round(0.5 * FPS))


def test_a_cue_that_is_not_approved_is_not_on_a_track(film, tmp_path):
    d, sid = film
    a = AL.import_files(d, "sfx", [tone(str(tmp_path / "src" / "x.wav"), 1.0)])["assets"][-1]
    Q.add(d, {"asset_id": a["id"], "scene": 1, "kind": "sfx", "shot": sid, "approval": "suggested"})
    assert T.cue_tracks(d, rows_of(d), FPS, 240) == []


def test_clips_on_one_track_never_overlap_and_a_trimmed_one_keeps_its_place_in_the_sound(film, tmp_path):
    d, sid = film
    rd = make.render_dir(d)
    rows = rows_of(d)
    cue(d, tmp_path, "sfx", 2.0, shot=sid, start=0.0)
    cue(d, tmp_path, "sfx", 2.0, shot=sid, start=1.0)
    for t in T.audio_tracks(d, rd, rows, FPS, sum(r["frames"] for r in rows)):
        for a, b in zip(t["clips"], t["clips"][1:]):
            assert a["start"] + a["frames"] <= b["start"]
    sfx = next(t for t in T.audio_tracks(d, rd, rows, FPS, 999) if t["role"] == "sfx")["clips"]
    assert len(sfx) == 2 and sfx[1].get("source_start", 0) > 0 and sfx[0].get("source_start", 0) == 0


def test_the_hand_off_writes_the_tracks_into_otio_and_final_cut_xml_and_copies_the_sounds(film, tmp_path):
    d, sid = film
    rd = make.render_dir(d)
    os.makedirs(os.path.join(rd, "media"), exist_ok=True)
    jobs = []
    for i, s in enumerate(S._index(d)["order"]):
        open(os.path.join(rd, "media", f"v{i}.mp4"), "wb").write(b"\x00\x00\x00\x18ftypmp42")
        jobs.append({"id": f"v{i}", "shot_id": s, "plan": "production", "state": "ready", "kind": "video", "provider": "kie", "model": "wan", "output": f"media/v{i}.mp4", "created": 1 + i, "updated": 2 + i})
    json.dump({"schema_version": 1, "jobs": jobs}, open(os.path.join(rd, "jobs.json"), "w"))
    cue(d, tmp_path, "sfx", 1.0, shot=sid, start=0.5)
    res = X.write(d)
    out = res["dir"]
    assert {t["name"] for t in res["audio_tracks"]} == {"Voice Sarah", "Voice John", "Sound effects"}
    otio = json.load(open(os.path.join(out, res["files"]["otio"]), encoding="utf-8"))
    audio = {t["name"]: t for t in otio["tracks"]["children"] if t["kind"] == "Audio"}
    assert {"Voice Sarah", "Voice John", "Sound effects"} <= set(audio)
    clip = next(c for c in audio["Voice Sarah"]["children"] if c["OTIO_SCHEMA"] == "Clip.1")
    assert os.path.isfile(os.path.join(out, clip["media_reference"]["target_url"])) and clip["source_range"]["duration"]["value"] == 2 * FPS
    gap = audio["Voice Sarah"]["children"][0]
    assert gap["OTIO_SCHEMA"] == "Gap.1" or clip is audio["Voice Sarah"]["children"][0]
    root = ET.parse(os.path.join(out, res["files"]["fcpxml"])).getroot()               # well-formed, and the audio hangs on negative lanes
    lanes = {c.get("lane") for c in root.iter("asset-clip") if c.get("lane")}
    assert lanes and all(int(x) < 0 for x in lanes)
    assert any(a.get("hasAudio") == "1" for a in root.iter("asset"))
    ids = {a.get("id") for a in root.iter("asset")}
    assert all(c.get("ref") in ids for c in root.iter("asset-clip"))


def test_a_film_with_no_recordings_or_cues_writes_the_same_hand_off_as_before(tmp_path):
    d = story.create(str(tmp_path / "films"), "Quiet", "screenplay", "INT. ROOM - DAY\n\nRain falls.\n")["dir"]
    bible.seed(d)
    S.breakdown(d)
    make.sync(d)
    assert T.audio_tracks(d, make.render_dir(d), rows_of(d), FPS, 240) == []


def test_the_premiere_and_resolve_file_gets_a_third_timeline_with_the_sound_on_tracks(film, tmp_path):
    import subprocess
    from filmcrafter_engine import editor_export as EX, export as E
    d, sid = film
    rd = make.render_dir(d)
    os.makedirs(os.path.join(rd, "media"), exist_ok=True)
    os.makedirs(os.path.join(rd, "exports"), exist_ok=True)

    def clip(path, secs, sound):
        cmd = [E.ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=gray:s=160x90:r=24:d={secs}"]
        if sound:
            cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}", "-c:a", "aac", "-shortest"]
        subprocess.run(cmd + ["-c:v", "libx264", "-pix_fmt", "yuv420p", path], check=True, creationflags=E.NO_WINDOW)
    jobs = []
    for i, s in enumerate(S._index(d)["order"]):
        clip(os.path.join(rd, "media", f"v{i}.mp4"), 3.0, False)
        jobs.append({"id": f"v{i}", "shot_id": s, "plan": "production", "state": "ready", "kind": "video", "provider": "kie", "model": "wan", "output": f"media/v{i}.mp4", "created": 1 + i, "updated": 2 + i})
    json.dump({"schema_version": 1, "jobs": jobs}, open(os.path.join(rd, "jobs.json"), "w"))
    filmfile = os.path.join(rd, "exports", "film.mp4")
    clip(filmfile, 12.0, True)
    cue(d, tmp_path, "sfx", 1.0, shot=sid, start=0.5)
    r = EX.package(rd, "premiere", filmfile)
    assert r["sequences"] == 3 and set(r["sound_tracks"]) == {"Voice Sarah", "Voice John", "Sound effects"}
    root = ET.parse(r["path"]).getroot()
    seqs = {s.find("name").text: s for s in root.iter("sequence")}
    third = next(v for k, v in seqs.items() if k.endswith("shots with sound by track"))
    audio_tracks = third.findall("media/audio/track")
    assert len(audio_tracks) == 3 and all(len(t.findall("clipitem")) >= 1 for t in audio_tracks)
    ids = [c.get("id") for c in root.iter("clipitem")]
    assert len(set(ids)) == len(ids)
