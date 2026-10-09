"""Acceptance tests: the promises FilmCrafter makes to the people who use it, each written as a scenario in the user's words and traced to a requirement in
docs/ACCEPTANCE.md. They use the real engine and real ffmpeg; only the paid services are stood in for."""
import json
import os
import socket
import subprocess
import wave

import pytest
from PIL import Image

from filmcrafter_engine import cleanup, customframe, export as E, library as L, media, overlays as O, refgen, render as R
from tests.test_render import FakeProvider, field, man

pytestmark = pytest.mark.acceptance


def ff(*args):
    subprocess.run([E.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args], check=True, creationflags=E.NO_WINDOW)


@pytest.fixture
def film(tmp_path):
    """A 12 s project with three planned shots and a quiet song."""
    d = tmp_path / "film"
    d.mkdir()
    with wave.open(str(d / "song.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\0\0" * int(22050 * 12))
    json.dump({"title": "Film", "song": "song.wav", "aspect_ratio": "16:9"}, open(d / "project.json", "w"))
    json.dump({"duration": 12.0, "sections": [], "lyrics": []}, open(d / "songmap.json", "w"))
    shots = [{"id": f"S01-0{i}", "scene": 1, "number": i, "start": (i - 1) * 4.0, "end": i * 4.0, "beats": ["A moment."], "performers": []} for i in (1, 2, 3)]
    json.dump({"scenes": [{"number": 1, "heading": "INT. ROOM", "start": 0, "end": 12, "shots": shots}]}, open(d / "production.json", "w"))
    json.dump({"jobs": []}, open(d / "jobs.json", "w"))
    ff("-f", "lavfi", "-i", "color=c=0xcc0000:s=320x180:r=24:d=5", "-pix_fmt", "yuv420p", str(tmp_path / "red.mp4"))
    return str(d), tmp_path


@pytest.fixture
def offline(monkeypatch):
    """No network at all: any attempt to open a connection fails the test."""
    def refuse(*a, **k):
        raise AssertionError("the free path tried to use the network")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    import requests
    for name in ("get", "post", "put", "request"):
        monkeypatch.setattr(requests, name, refuse)


def plan(d):
    return {s["id"]: s for sc in json.load(open(os.path.join(d, "production.json")))["scenes"] for s in sc["shots"]}


def test_ACC01_everything_that_is_free_works_with_no_internet_and_never_calls_a_service(film, offline):
    """REQ-01: my own clips, layers, inserted frames and the export cost nothing and need no account or connection."""
    d, tmp = film
    media.import_media(d, "S01-02", str(tmp / "red.mp4"))
    customframe.insert(d, {"where": "before", "shot": "S01-03", "length": 1.5, "mode": "colour", "color": "#ffff00"})
    O.add(d, {"kind": "text", "text": "TITLE", "start": 0, "end": 6, "size": 0.15, "x": 0.5, "y": 0.5, "anim": "pop"})
    O.add(d, {"kind": "shape", "shape": "circle", "start": 2, "end": 9, "keys": [{"t": 0, "x": 0.2}, {"t": 3, "x": 0.8}]})
    out = E.build(d, "square")
    assert os.path.isfile(out["path"]) and out["overlays"] == 2


def test_ACC02_nothing_is_sent_to_a_paid_service_until_I_have_confirmed_the_price(film, monkeypatch):
    """REQ-02: a picture batch needs the price confirmed; a shot I have not described is never sent; a refusal sends nothing and charges nothing."""
    d, _ = film
    FakeProvider.submits, FakeProvider.submit_error = 0, None
    monkeypatch.setitem(R.PROVIDERS, "fal", FakeProvider)
    m = man(field("prompt", required=True), field("duration", enum=["5", "10"]))
    monkeypatch.setattr(R, "manifest", lambda provider, model, refresh=False: m)
    plan_json = json.load(open(os.path.join(d, "production.json")))
    plan_json["scenes"][0]["shots"][0]["beats"] = []
    json.dump(plan_json, open(os.path.join(d, "production.json"), "w"))
    assert R.enqueue(d, ["S01-01"], "fal", "test/model", {}) == [] and FakeProvider.submits == 0           # nothing described: nothing queued
    with pytest.raises(SystemExit, match="Confirm the price first: nothing was sent"):
        refgen.queue(d, ["whatever"], "fal", "test/model", confirmed=False)
    FakeProvider.submit_error = R.ProviderError("422: Input failed safety check", 422)
    R.enqueue(d, ["S01-02"], "fal", "test/model", {})
    R.run(d, poll_every=0)
    j = next(x for x in R.Store(d).jobs if x["shot_id"] == "S01-02")
    assert j["state"] != "ready" and not j.get("cost") and FakeProvider.submits == 0                          # refused: no take, no charge


def test_ACC03_a_new_render_never_replaces_the_take_I_chose(film, monkeypatch):
    """REQ-03: every render is kept as another version; the one I approved stays in the film until I choose another."""
    d, _ = film
    FakeProvider.submits, FakeProvider.submit_error = 0, None
    FakeProvider.poll_result = {"state": "done", "url": "https://cdn/out.mp4"}
    monkeypatch.setitem(R.PROVIDERS, "fal", FakeProvider)
    m = man(field("prompt", required=True), field("duration", enum=["5", "10"]))
    monkeypatch.setattr(R, "manifest", lambda provider, model, refresh=False: m)
    monkeypatch.setattr(R, "_review", lambda d, store, j: None)

    class Dl:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_content(self, n): yield b"\0" * 64
    monkeypatch.setattr(R.requests, "get", lambda url, **kw: Dl())
    R.enqueue(d, ["S01-01"], "fal", "test/model", {})
    R.run(d, poll_every=0)
    first = next(j for j in R.Store(d).jobs if j["shot_id"] == "S01-01")
    L.approve(d, "S01-01", first["id"])
    R.enqueue(d, ["S01-01"], "fal", "test/other", {})
    R.run(d, poll_every=0)
    ready = [j for j in R.Store(d).jobs if j["shot_id"] == "S01-01" and j["state"] == "ready"]
    assert len(ready) == 2 and all(os.path.isfile(os.path.join(d, j["output"])) for j in ready)               # both kept
    chosen = L.chosen_take(d, "S01-01", "production", R.Store(d).jobs)
    assert chosen["id"] == first["id"]                                                                       # and mine is still the one in the film


def test_ACC04_inserting_or_removing_a_frame_never_moves_the_rest_of_the_film(film):
    """REQ-04: the film stays in step with the song: shots after a change keep their times, and removing the frame gives the time back."""
    d, _ = film
    before = {k: (v["start"], v["end"]) for k, v in plan(d).items()}
    r = customframe.insert(d, {"where": "after", "shot": "S01-01", "length": 1.5, "mode": "colour"})
    after = plan(d)
    assert (after["S01-02"]["start"], after["S01-03"]["start"], after["S01-03"]["end"]) == (before["S01-02"][0], before["S01-03"][0], before["S01-03"][1])
    assert after["S01-01"]["end"] - after["S01-01"]["start"] >= 1.0 and max(s["end"] for s in after.values()) == 12.0
    customframe.remove(d, r["shot"])
    assert {k: (v["start"], v["end"]) for k, v in plan(d).items()} == before


def test_ACC05_I_can_always_get_back_what_I_cleaned_up_until_I_empty_the_trash(film):
    """REQ-05: removing unused files is a step I can undo; only emptying the trash deletes."""
    d, _ = film
    os.makedirs(os.path.join(d, "generations"))
    spare = os.path.join(d, "generations", "S01-01__old.mp4")
    open(spare, "wb").write(b"x" * 100)
    old = os.path.getmtime(spare) - 7200
    os.utime(spare, (old, old))
    assert [i["path"] for i in cleanup.scan(d)["items"]] == ["generations/S01-01__old.mp4"]
    cleanup.discard(d, ["generations/S01-01__old.mp4"])
    assert not os.path.exists(spare) and cleanup.scan(d)["trash"]["files"] == 1
    cleanup.restore(d)
    assert os.path.exists(spare)
    cleanup.discard(d, ["generations/S01-01__old.mp4"])
    cleanup.empty(d)
    assert not os.path.exists(spare) and cleanup.scan(d)["trash"]["files"] == 0


def test_ACC06_the_film_is_always_as_long_as_the_song_even_before_anything_is_rendered(film):
    """REQ-06: an export with nothing rendered still gives a complete film (slates stand in), so I can check the timing before I spend."""
    d, _ = film
    out = E.build(d, "square")
    p = subprocess.run([E.ffmpeg(), "-hide_banner", "-i", out["path"]], capture_output=True, text=True, creationflags=E.NO_WINDOW)
    import re
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", p.stderr)
    assert abs(float(m[1]) * 3600 + float(m[2]) * 60 + float(m[3]) - 12.0) < 0.5 and out["draft"]


@pytest.mark.parametrize("module,args", [
    ("cleanup", ["discard", "{d}", "--data", "{}"]), ("customframe", ["insert", "{d}", "--data", '{"shot": "nope", "length": 2, "mode": "colour"}']),
    ("titlecard", ["make", "{d}", "--data", '{"title": ""}']), ("overlays", ["update", "{d}", "--data", '{"id": "missing"}']),
])
def test_ACC07_when_something_cannot_be_done_I_am_told_in_plain_words_not_given_a_crash(film, capsys, module, args):
    """REQ-07: refusals are one readable sentence, never a stack trace or a technical class name."""
    import importlib
    d, _ = film
    mod = importlib.import_module(f"filmcrafter_engine.{module}")
    assert mod.main([a.replace("{d}", d) for a in args]) == 1
    msg = json.loads(capsys.readouterr().out.splitlines()[-1])["message"]
    assert msg and "Traceback" not in msg and "Error:" not in msg and "KeyError" not in msg and msg[0].isupper()


# ---------------------------------------------------------------- the sound of a shot, layers, and loudness (REQ-13 to REQ-16)

def test_ACC13_I_can_keep_trim_or_drop_the_sound_a_video_model_made_without_paying_to_render_again(tmp_path, monkeypatch):
    """As a director I hear a take whose sound I like in one shot and not in another. I keep it for one, split it and keep only the voices, then drop it, and change my mind:
    the film follows every time, no new render is queued, and the take file is exactly what the model returned."""
    import hashlib
    from filmcrafter_engine import shotsound as SS
    from tests.test_shotsound import fake_demucs, level, make_film
    fake_demucs(monkeypatch)
    d = make_film(tmp_path)
    jobs_file, take_file = os.path.join(d, "jobs.json"), os.path.join(d, "generations", "t1.mp4")
    before = (open(jobs_file, "rb").read(), hashlib.sha1(open(take_file, "rb").read()).hexdigest())
    film = lambda: SS.decode(E.build(d, "square")["path"], 1)[:, 0]
    assert level(film(), 0.3, 1.7, 1000) < 0.02                                          # by default the film is the song
    SS.set_layer(d, "S01-01", "all", on=True)
    assert level(film(), 0.3, 1.7, 1000) > 0.1                                           # kept for shot 1
    SS.split(d, "S01-01")
    SS.delete_layer(d, "S01-01", "other")
    x = film()
    assert level(x, 0.3, 1.7, 500) > 0.05 and level(x, 0.3, 1.7, 2000) < 0.02            # only the voices
    SS.delete_layer(d, "S01-01", "voice")
    assert level(film(), 0.3, 1.7, 500) < 0.02                                           # all of it gone
    SS.restore_layer(d, "S01-01", "voice")
    assert level(film(), 0.3, 1.7, 500) > 0.05                                           # and back
    assert (open(jobs_file, "rb").read(), hashlib.sha1(open(take_file, "rb").read()).hexdigest()) == before     # nothing was rendered, nothing was changed


def test_ACC14_my_song_is_never_changed_unless_i_choose_to_change_it(tmp_path):
    """As a musician I do not want FilmCrafter to touch my song's level behind my back: untouched, the film plays my song as it is; after I change a shot and go back, it is the same again."""
    from filmcrafter_engine import shotsound as SS
    from tests.test_shotsound import make_film
    d = make_film(tmp_path)
    ch = lambda: SS.decode(E.build(d, "square")["path"], 2)
    untouched = ch()
    assert SS.mix_track(d, [{"shot": "S01-01", "start": 0.0, "end": 2.0, "take": SS.take_for(d, "S01-01")}], 4.0, os.path.join(d, "song.wav"), os.path.join(d, "m.wav")) is None
    SS.set_layer(d, "S01-01", "all", on=True)
    SS.set_layer(d, "S01-01", "song", on=False)
    changed = ch()
    SS.reset(d, "S01-01")
    back = ch()
    rms = lambda x, a, b: float((x[int(a * 44100):int(b * 44100)] ** 2).mean() ** 0.5)
    assert abs(20 * __import__("math").log10(rms(back, 2.3, 3.7) / rms(untouched, 2.3, 3.7))) < 0.3          # the song under shot 2 is as it was
    assert abs(20 * __import__("math").log10(rms(back, 0.3, 1.7) / rms(untouched, 0.3, 1.7))) < 0.3          # and under shot 1, once I went back
    assert rms(changed, 0.3, 1.7) != pytest.approx(rms(untouched, 0.3, 1.7), rel=0.2)                          # while it was changed, it really was different


def test_ACC15_i_can_take_back_a_change_to_my_layers(tmp_path):
    """As an editor I add a title, rewrite it, then delete it by mistake. Undo brings back each step in turn, and redo goes forward again."""
    d = tmp_path / "p"
    d.mkdir()
    (d / "project.json").write_text(json.dumps({"title": "T"}))
    (d / "songmap.json").write_text(json.dumps({"duration": 30.0, "sections": []}))
    d = str(d)
    o = O.add(d, {"text": "FIRST", "start": 1, "end": 5})[-1]
    O.update(d, o["id"], {"text": "SECOND"})
    O.remove(d, o["id"])
    texts = lambda: [x.get("text") for x in O.load(d)]
    assert texts() == []
    O.undo(d)
    assert texts() == ["SECOND"]
    O.undo(d)
    assert texts() == ["FIRST"]
    O.redo(d)
    assert texts() == ["SECOND"]


def test_ACC16_i_am_told_how_loud_my_film_is_and_never_given_a_made_up_number(tmp_path):
    """As someone about to publish I want the film's loudness. A film with sound gets a real reading; one with none gets no number at all, not a zero."""
    from filmcrafter_engine import shotsound as SS
    from tests.test_shotsound import make_film, tone
    d = make_film(tmp_path)
    r = E.build(d, "square")["loudness"]
    assert r and -22 < r["lufs"] < -10 and r["true_peak_db"] is not None                  # a 0.3 sine: about -13.5 dB RMS
    import numpy as np
    import soundfile as sf
    sf.write(os.path.join(d, "song.wav"), np.zeros(44100 * 4, dtype=np.float32), 44100)
    assert E.build(d, "square")["loudness"] is None


# ---------------------------------------------------------------- layers on the timeline, transitions, and the free checks (REQ-17 to REQ-19)

def test_ACC17_a_layer_i_move_trim_or_hide_is_exactly_what_the_export_shows(tmp_path):
    """As an editor I drag a title to a new time, trim it, and hide another: the export shows the first where I put it, and the hidden one nowhere; hiding is kept, not deleting."""
    from filmcrafter_engine import overlays as OV
    from tests.test_shotsound import make_film
    d = make_film(tmp_path)
    a = OV.add(d, {"kind": "text", "text": "FIRST", "start": 0.2, "end": 1.0})[-1]
    b = OV.add(d, {"kind": "text", "text": "SECOND", "start": 0.2, "end": 1.0})[-1]
    OV.update(d, a["id"], {"start": 2.0, "end": 3.0})                                       # moved, as dragging does
    OV.update(d, b["id"], {"enabled": False})                                               # hidden, as the dot does
    shown = [(o["text"], o["start"], o["end"]) for o in OV.resolve(d) if o["enabled"] and o["placed"]]
    assert shown == [("FIRST", 2.0, 3.0)]
    assert len(OV.load(d)) == 2                                                             # the hidden layer is still in the project
    OV.update(d, b["id"], {"enabled": True})
    assert sorted(o["text"] for o in OV.resolve(d) if o["enabled"]) == ["FIRST", "SECOND"]


def test_ACC18_a_transition_never_changes_how_long_the_film_is(tmp_path):
    """As an editor I give three cuts three different transitions; the film is exactly as long as the song, and each shot enters the way I chose."""
    import subprocess
    from filmcrafter_engine import media as M
    from tests.test_media import _project, _img
    d = _project(tmp_path)
    subprocess.run([E.ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=8", os.path.join(d, "song.wav")], check=True)
    ids = [s["id"] for sc in json.load(open(os.path.join(d, "production.json")))["scenes"] for s in sc["shots"]]
    for i, sid in enumerate(ids):
        M.import_media(d, sid, _img(tmp_path, f"{i}.png", (200 - 40 * i, 30, 30 + 50 * i)), "none")
    for sid, kind in zip(ids[1:], ("zoom_through", "slide_left", "wipe_down")):
        M.set_transition(d, [sid], kind, 0.5)
    res = E.build(d, next(iter(E.PRESETS)))
    err = subprocess.run([E.ffmpeg(), "-hide_banner", "-i", res["path"]], capture_output=True, text=True).stderr
    assert "Duration: 00:00:08" in err or "Duration: 00:00:07.9" in err


def test_ACC19_the_free_checks_never_send_anything_anywhere(tmp_path, monkeypatch):
    """As someone watching the cost I want the dance-ready check, the sound check and the camera suggestions to stay on my computer: with the network switched off they still answer."""
    import socket
    from filmcrafter_engine import dance, looks
    from tests.test_dance import project, shot
    def no_network(*a, **k):
        raise AssertionError("a free check tried to use the network")
    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    d = project(tmp_path, [shot(1, 4.0, 8.0, emotion="dread", performance_intensity=8)])
    assert dance.check(d)["dance_shots"] == 1
    assert looks.suggest(d)["count"] == 1
