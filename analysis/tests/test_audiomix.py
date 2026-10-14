"""Stage E: mixing the planned sound into the film. Real audio, real ffmpeg, no provider. Checked by measuring the result: where each sound lands, how loud, how it fades, how music dips under a voice,
that nothing clips, that the originals are never touched, and that a long film is mixed in blocks (a flat amount of memory)."""
import hashlib
import json
import os
import tracemalloc

import numpy as np
import pytest
import soundfile as sf

from filmcrafter_engine import audiocues as Q, audiolib as AL, audiomix as M, bible, export as E, shots as S, story, voiceover as V

SCRIPT = "INT. KITCHEN - NIGHT\n\nRain on the roof. Sarah pours tea from the kettle.\n\nSARAH\nHe said he'd call.\n\nEXT. YARD - DAY\n\nChildren play in the schoolyard.\n"
RATE = M.RATE


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    S.breakdown(d)
    return d


def tone(path, secs, hz=1000, amp=0.3, rate=22050):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    t = np.arange(int(rate * secs)) / rate
    sf.write(path, (amp * np.sin(2 * np.pi * hz * t)).astype("float32"), rate)
    return path


def silence(path, secs):
    sf.write(path, np.zeros((int(RATE * secs), 2), dtype="float32"), RATE, subtype="PCM_16")
    return path


def asset(film, tmp_path, name, secs, hz=1000, amp=0.3, kind="sfx", category=None):
    return AL.import_files(film, kind, [tone(str(tmp_path / "src" / name), secs, hz, amp)], category)["assets"][-1]


def times(film, scene=1):
    out, at = {}, 0.0
    for s in sorted([x for x in S.view(film)["shots"] if x["scene"] == scene], key=lambda x: x["index"]):
        out[s["id"]] = (at, at + s["duration"])
        at += s["duration"]
    return out, at


def level(x, a, b):
    """RMS of the mixed file between seconds a and b (left channel)."""
    seg = x[int(a * RATE):int(b * RATE), 0]
    return float(np.sqrt(np.mean(np.square(seg)))) if len(seg) else 0.0


def mix(film, tmp_path, st=None, windows=None, base=None, scene=1):
    t, dur = times(film, scene)
    out = str(tmp_path / "mixed.wav")
    r = M.mix_cues(film, base or silence(str(tmp_path / "base.wav"), dur), t, dur, out, st, windows=windows)
    data = sf.read(out, dtype="float32", always_2d=True)[0] if r and r.get("path") else None
    return r, data, t, dur


def place(film, a, **kw):
    return Q.add(film, {"asset_id": a["id"], "scene": 1, **kw})["id"]


# ---------------------------------------------------------------- nothing planned: nothing touched

def test_a_film_with_no_plan_and_a_plan_with_nothing_approved_leave_the_soundtrack_alone(film, tmp_path):
    t, dur = times(film)
    base = silence(str(tmp_path / "base.wav"), dur)
    assert M.mix_cues(film, base, t, dur, str(tmp_path / "o.wav")) is None
    a = asset(film, tmp_path, "rain.wav", 2.0)
    Q.add(film, {"asset_id": a["id"], "scene": 1, "source": "director"})                       # only suggested
    Q.add(film, {"kind": "sfx", "scene": 1, "plan": {"description": "A kettle", "search": "k"}})  # approved, but no sound yet
    r = M.mix_cues(film, base, t, dur, str(tmp_path / "o.wav"))
    assert r["none"] is True and r["skipped"][0]["why"] == "It has no sound yet." and not os.path.exists(str(tmp_path / "o.wav"))
    assert M.mix_cues(str(tmp_path), base, t, dur, str(tmp_path / "o2.wav")) is None             # not a film at all


def test_the_exporters_render_folder_finds_its_film(film, tmp_path):
    assert M.film_of(film) == film
    os.makedirs(os.path.join(film, "render"))
    assert M.film_of(os.path.join(film, "render")) == film
    assert M.film_of(str(tmp_path)) is None and M.film_of(os.path.join(str(tmp_path), "render")) is None


# ---------------------------------------------------------------- where and how loud

def test_a_cue_lands_where_the_plan_says_at_the_level_asked_and_the_source_is_untouched(film, tmp_path):
    a = asset(film, tmp_path, "tone.wav", 1.0, 1000, 0.3)
    src = os.path.join(film, *a["file"].split("/"))
    before = hashlib.sha1(open(src, "rb").read()).hexdigest()
    sid = next(iter(times(film)[0]))
    place(film, a, shot=sid, start=0.5, gain_db=-6)
    r, x, t, dur = mix(film, tmp_path, {**M.settings(film), "ducking_db": 0})
    s0 = t[sid][0] + 0.5
    inside, outside = level(x, s0 + 0.1, s0 + 0.9), max(level(x, 0, s0 - 0.1), level(x, s0 + 1.2, dur))
    assert r["cues"] == 1 and outside < 0.002
    assert abs(inside - (0.3 / np.sqrt(2)) * 0.5) < 0.02                                         # 0.3 tone, -6 dB: about half the level
    assert hashlib.sha1(open(src, "rb").read()).hexdigest() == before


def test_fades_loops_and_a_cue_cut_short_behave(film, tmp_path):
    a = asset(film, tmp_path, "tone.wav", 4.0, 800, 0.4)
    sid = next(iter(times(film)[0]))
    place(film, a, shot=sid, start=0, duration=3, fade_in=1.0, fade_out=1.0)
    r, x, t, dur = mix(film, tmp_path, {**M.settings(film), "ducking_db": 0})
    assert level(x, 0.0, 0.1) < 0.05 * level(x, 1.2, 1.8) + 0.005 and level(x, 1.2, 1.8) > 0.2                  # it fades in
    assert level(x, 2.9, 3.0) < level(x, 1.5, 1.8) * 0.3 and level(x, 3.1, dur) < 0.002                          # and out, and stops after its 3 s
    loop = asset(film, tmp_path, "short.wav", 0.5, 600, 0.4, category="ambience")
    Q.update(film, Q.listing(film)["cues"][0]["id"], {"approval": "rejected"}) if False else None
    for c in Q.listing(film)["cues"]:
        Q.remove(film, c["id"])
    place(film, loop, shot=sid)                                                                     # an ambience loops by itself to fill its shot
    r, x, t, dur = mix(film, tmp_path, {**M.settings(film), "ducking_db": 0})
    a0, b0 = t[sid]
    assert level(x, a0 + 0.1, b0 - 0.1) > 0.2 and level(x, a0 + 1.4, a0 + 1.6) > 0.2 and level(x, b0 + 0.2, dur) < 0.002 if b0 + 0.2 < dur else True
    for c in Q.listing(film)["cues"]:
        Q.remove(film, c["id"])
    place(film, loop, shot=sid, loop=False)                                                         # not looped: it plays once and is done
    r, x, t, dur = mix(film, tmp_path, {**M.settings(film), "ducking_db": 0})
    assert level(x, a0 + 0.05, a0 + 0.4) > 0.2 and level(x, a0 + 0.8, a0 + 1.5) < 0.002


def test_a_scene_wide_cue_starts_with_the_scene_and_unplayable_cues_are_reported_not_hidden(film, tmp_path):
    a = asset(film, tmp_path, "tone.wav", 1.0)
    place(film, a, start=0.25)
    gone = place(film, a, shot=next(iter(times(film)[0])), start=1)
    os.remove(os.path.join(film, *a["file"].split("/")))                                              # the sound file goes missing
    r, x, t, dur = mix(film, tmp_path)
    assert r.get("none") and {s["why"] for s in r["skipped"]} == {"Its sound is missing from the library."} and len(r["skipped"]) == 2 and gone


# ---------------------------------------------------------------- music and ambience dip under voices

def voice_in(film, tmp_path, sid, secs=2.0):
    src = tone(str(tmp_path / "voice" / f"{sid}.wav"), secs, 300, 0.3)
    V.attach(film, sid, "Sarah", src)


def test_music_dips_under_a_voice_and_comes_back_while_effects_and_cues_set_to_off_do_not(film, tmp_path):
    sid = next(s["id"] for s in V.status(film)["shots"] if any(p["name"] == "Sarah" for p in s["people"]))
    voice_in(film, tmp_path, sid, 2.0)
    music = asset(film, tmp_path, "m.wav", 8.0, 500, 0.3, kind="music")
    sfx = asset(film, tmp_path, "s.wav", 8.0, 700, 0.3)
    t, dur = times(film)
    start = t[sid][0]
    cm = place(film, music, shot=sid, start=0, duration=min(6, t[sid][1] - start))
    st = {**M.settings(film), "ducking_db": -12.0, "duck_attack": 0.1, "duck_release": 0.3}
    r, x, t, dur = mix(film, tmp_path, st, windows=M.film_windows(film))
    spans = M.dialogue_spans(film, t, M.film_windows(film))
    assert spans and r["ducked"] is True
    vs, ve = spans[0][0] + 0.3, spans[0][1] - 0.3
    far = start + 2.8 if start + 2.8 + 0.5 < t[sid][1] else None
    ducked, free = level(x, vs, ve), level(x, start + 2.7, min(t[sid][1] - 0.1, start + 3.5)) if far else None
    assert free is None or abs(20 * np.log10(ducked / free) + 12) < 2.5                                      # about the 12 dB asked for
    Q.update(film, cm, {"ducking": "off"})
    r2, x2, *_ = mix(film, tmp_path, st, windows=M.film_windows(film))
    assert level(x2, vs, ve) > level(x, vs, ve) * 3.0 and r2["ducked"] is False
    Q.remove(film, cm)
    place(film, sfx, shot=sid, start=0, duration=2.0)                                                       # a sound effect does not dip by default
    r3, x3, *_ = mix(film, tmp_path, st, windows=M.film_windows(film))
    assert abs(level(x3, vs, ve) - (0.3 / np.sqrt(2))) < 0.03


# ---------------------------------------------------------------- nothing clips

def test_loud_sound_is_held_under_the_ceiling_and_the_report_says_it_was_loud(film, tmp_path):
    sid = next(iter(times(film)[0]))
    a, b = asset(film, tmp_path, "a.wav", 2.0, 440, 0.9), asset(film, tmp_path, "b.wav", 2.0, 660, 0.9)
    place(film, a, shot=sid)
    place(film, b, shot=sid)
    r, x, *_ = mix(film, tmp_path, {**M.settings(film), "ducking_db": 0, "peak_db": -2.0})
    assert r["peak_before_db"] > 0 and r["limiter"] is True
    assert float(np.max(np.abs(x))) <= 10 ** (-2.0 / 20) + 0.01 and float(np.max(np.abs(x))) > 0.5          # held under the ceiling, still loud


def test_a_loudness_target_brings_the_whole_film_to_it(film, tmp_path):
    sid = next(iter(times(film)[0]))
    a = asset(film, tmp_path, "a.wav", 6.0, 440, 0.05)
    place(film, a, shot=sid, start=0, duration=5.0)
    r, x, *_ = mix(film, tmp_path, {**M.settings(film), "ducking_db": 0, "target_lufs": -20.0, "peak_db": -1.5})
    got = E.measure_loudness(str(tmp_path / "mixed.wav"))
    assert r["target_lufs"] == -20.0 and got and abs(got["lufs"] + 20.0) < 2.5 and float(np.max(np.abs(x))) <= 10 ** (-1.5 / 20) + 0.01


# ---------------------------------------------------------------- mute, solo and the settings

def test_muted_cues_and_lanes_are_left_out_and_solo_only_narrows_the_preview(film, tmp_path):
    sid = next(iter(times(film)[0]))
    fx = asset(film, tmp_path, "fx.wav", 1.0, 700)
    mu = asset(film, tmp_path, "mu.wav", 1.0, 400, kind="music")
    c1, c2 = place(film, fx, shot=sid, start=0), place(film, mu, shot=sid, start=1.2)
    st = {**M.settings(film), "ducking_db": 0}
    assert mix(film, tmp_path, st)[0]["cues"] == 2
    Q.update(film, c1, {"muted": True})
    assert mix(film, tmp_path, st)[0]["cues"] == 1
    M.set_settings(film, {"mute_lanes": ["music"]})
    assert mix(film, tmp_path, M.settings(film))[0] is None                                              # every cue is in a muted lane: nothing is heard
    M.set_settings(film, {"mute_lanes": [], "solo": "music"})
    Q.update(film, c1, {"muted": False})
    assert mix(film, tmp_path, M.settings(film))[0]["cues"] == 2                                          # the film ignores solo
    p = M.preview(film, 1)
    assert p["cues"] == 2 and p["solo"] is None                                                           # the preview plays what the film will have unless a lane is asked for
    p2 = M.preview(film, 1, "sfx")
    assert p2["cues"] == 1 and p2["solo"] == "sfx" and os.path.isfile(os.path.join(film, *p2["file"].split("/")))
    assert c2 and Q.listing(film)['cues']


def test_the_settings_are_checked_saved_and_kept_through_a_restart(film):
    s = M.set_settings(film, {"ducking_db": -9, "target_lufs": -16, "peak_db": -1.5, "mute_lanes": ["music", "nonsense"], "solo": "sfx"})
    assert (s["ducking_db"], s["target_lufs"], s["peak_db"], s["mute_lanes"], s["solo"]) == (-9.0, -16.0, -1.5, ["music"], "sfx")
    assert M.settings(film) == s
    for bad in ({"ducking_db": 5}, {"ducking_db": "x"}, {"target_lufs": -3}, {"peak_db": 0}, {"solo": "guitar"}, {"duck_attack": 0}):
        with pytest.raises(SystemExit):
            M.set_settings(film, bad)
    assert M.set_settings(film, {"target_lufs": None})["target_lufs"] is None and M.settings(film)["peak_db"] == -1.5


# ---------------------------------------------------------------- a long film

def test_a_ten_minute_film_is_mixed_in_blocks_with_a_flat_amount_of_memory(film, tmp_path):
    minutes = 10
    dur = minutes * 60.0
    base = str(tmp_path / "long-base.wav")
    with sf.SoundFile(base, "w", RATE, 2, subtype="PCM_16") as w:
        for _ in range(minutes * 2):
            w.write(np.zeros((int(30 * RATE), 2), dtype="float32"))
    long_music = str(tmp_path / "long.wav")
    with sf.SoundFile(long_music, "w", 22050, 1, subtype="PCM_16") as w:                                       # a 5 minute piece: read a block at a time, not kept whole
        for k in range(10):
            t = np.arange(30 * 22050) / 22050
            w.write((0.3 * np.sin(2 * np.pi * (300 + 20 * k) * t)).astype("float32"))
    m = AL.import_files(film, "music", [long_music], "score")["assets"][0]
    sid = next(iter(times(film)[0]))
    Q.add(film, {"asset_id": m["id"], "scene": 1, "start": 5, "duration": 280})
    shot_times = {sid: (0.0, dur)}
    out = str(tmp_path / "long-out.wav")
    tracemalloc.start()
    r = M.mix_cues(film, base, shot_times, dur, out, {**M.settings(film), "ducking_db": 0})
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    info = sf.info(out)
    assert r["cues"] == 1 and abs(info.duration - dur) < 0.5 and info.samplerate == RATE
    assert peak < 150 * 1024 * 1024                                                                              # a ten-minute film does not need ten minutes of audio in memory
    seg = sf.read(out, start=int(100 * RATE), frames=RATE, dtype="float32", always_2d=True)[0]
    assert float(np.sqrt(np.mean(np.square(seg[:, 0])))) > 0.1
    seg_after = sf.read(out, start=int(400 * RATE), frames=RATE, dtype="float32", always_2d=True)[0]
    assert float(np.max(np.abs(seg_after))) < 0.001


# ---------------------------------------------------------------- the command line and the exporter's hook

def test_the_command_line_speaks_the_engine_format_and_only_knows_its_actions(film, capsys):
    assert M.main(["settings", film]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["ducking_db"] == -12.0
    with pytest.raises(SystemExit):
        M.main(["format_disk", film])
    assert M.main(["set_settings", film, "--data", json.dumps({"solo": "banjo"})]) == 1


def test_the_exporter_lays_the_plan_on_the_soundtrack_after_the_voices_and_reports_what_it_did():
    src = open(E.__file__, encoding="utf-8").read()
    assert src.index("voiceover.mix_into(") < src.index("audiomix.mix_cues(") < src.index('"-map", "0:v:0", "-map", "1:a:0"')
    assert "audio_cues_skipped" in src and "audio_cues_error" in src


# ---------------------------------------------------------------- the whole way: a film exported with its plan

@pytest.mark.integration
def test_a_film_is_exported_with_its_approved_cues_and_a_film_without_a_plan_exports_as_before(tmp_path):
    from filmcrafter_engine import make
    from filmcrafter_engine.shotsound import decode
    from tests.test_golden_film import SCRIPT as GOLD, _clip, _job
    d = story.create(str(tmp_path / "films"), "Plan", "screenplay", GOLD)["dir"]
    bible.seed(d)
    ids = [s["id"] for s in S.breakdown(d)["shots"]]
    make.sync(d)
    rd = make.render_dir(d)
    os.makedirs(os.path.join(rd, "media"), exist_ok=True)
    for i, sid in enumerate(ids):
        _clip(os.path.join(rd, "media", f"v{i}.mp4"), 2)
        _job(d, sid, f"v{i}", "video", f"media/v{i}.mp4")

    def spectrum_peak(x, a, b):
        seg = x[int(a * RATE):int(b * RATE), 0] if x.ndim == 2 else x[int(a * RATE):int(b * RATE)]
        f = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        return float(np.fft.rfftfreq(len(seg), 1 / RATE)[int(np.argmax(f))]), float(np.sqrt(np.mean(seg ** 2)))

    plain = E.build(rd, "preview")
    assert "audio_cues" not in plain
    x0 = decode(plain["path"], 2)
    assert float(np.sqrt(np.mean(x0 ** 2))) < 0.01                                                             # a silent film
    a = AL.import_files(d, "sfx", [tone(str(tmp_path / "src" / "hum.wav"), 4.0, 1000, 0.3)], "ambience")["assets"][0]
    Q.add(d, {"asset_id": a["id"], "shot": ids[0], "start": 0.5, "duration": 1.0, "gain_db": -6})
    Q.add(d, {"asset_id": a["id"], "shot": ids[1], "start": 0, "source": "director"})                          # only suggested: not in the film
    out = E.build(rd, "preview")
    assert out["audio_cues"] == 1 and out["audio_cues_skipped"] == []
    x1 = decode(out["path"], 2)
    freq, loud = spectrum_peak(x1, 0.6, 1.4)
    assert abs(freq - 1000) < 40 and loud > 0.1                                                                # the planned sound is in the finished film, where it was placed
    assert float(np.sqrt(np.mean(x1[int(2.2 * RATE):int(3.8 * RATE)] ** 2))) < 0.01                             # and nothing else is (the suggested cue is not)
    assert hashlib.sha1(open(os.path.join(d, *a["file"].split("/")), "rb").read()).hexdigest() == a["sha1"]    # the sound file is as it was
