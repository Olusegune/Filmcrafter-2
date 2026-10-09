"""End to end: the sound of a shot, from an audio file to a finished film. A song is listened to and cut into shots; a (stand-in) video model returns a take that has its own
sound; the film is exported with the song only; then the model's sound is kept for one shot, split into voices and effects, trimmed, previewed and exported again, and the
film's loudness is read. Along the way nothing is rendered a second time and the take is never touched. Real engine code and real ffmpeg; only the paid renderer and the
separator are stood in for."""
import hashlib
import json
import os
import subprocess

import numpy as np
import pytest

from pulseframe_analysis import analyze, export as E, layerkit, media, overlays as O, render as R, shotsound as SS
from tests.test_e2e_journey import SECONDS, ff, parts  # noqa: F401  (the 16 s click-track song; a fixture)
from tests.test_render import FakeProvider, field, man
from tests.test_shotsound import fake_demucs, level

pytestmark = pytest.mark.e2e

MODEL = 700          # Hz: the stand-in model's sound. The song is a 1000 Hz click track, so the two can be told apart in the film


@pytest.fixture
def journey(parts, tmp_path, monkeypatch):                                            # noqa: F811
    d = tmp_path / "film"
    d.mkdir()
    (d / "song.wav").write_bytes((parts / "song.wav").read_bytes())
    (d / "project.json").write_text(json.dumps({"title": "Sound journey", "song": "song.wav", "aspect_ratio": "16:9"}))
    voiced = tmp_path / "voiced.mp4"                                                  # what the stand-in renderer returns: a clip with a sound of its own
    ff("-f", "lavfi", "-i", "color=c=0x00aa00:s=320x180:r=24:d=6", "-f", "lavfi", "-i", f"sine=frequency={MODEL}:duration=6", "-c:v", "libx264", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-shortest", str(voiced))
    clip = voiced.read_bytes()

    class Download:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_content(self, n): yield clip

    FakeProvider.submits, FakeProvider.submit_error = 0, None
    FakeProvider.poll_result = {"state": "done", "url": "https://cdn/out.mp4"}
    monkeypatch.setitem(R.PROVIDERS, "fal", FakeProvider)
    m = man(field("prompt", required=True), field("duration", enum=["5", "10"]))
    monkeypatch.setattr(R, "manifest", lambda provider, model, refresh=False: m)
    monkeypatch.setattr(R, "_review", lambda d, store, j: None)
    monkeypatch.setattr(R.requests, "get", lambda url, **kw: Download())
    fake_demucs(monkeypatch)
    return str(d)


def audio_of(path):
    return SS.decode(path, 1)[:, 0]


def sha(path):
    return hashlib.sha1(open(path, "rb").read()).hexdigest()


def test_the_models_sound_is_mine_to_keep_split_trim_and_measure_without_rendering_again(journey):
    d = journey

    # 1. the song is listened to and cut into shots; the first shot is described and rendered once, by the stand-in model
    assert analyze.main([os.path.join(d, "song.wav"), "--out", os.path.join(d, "songmap.json")]) == 0
    media.plan_from_song(d, bars=1)
    plan = json.load(open(os.path.join(d, "production.json")))
    shots = [s for sc in plan["scenes"] for s in sc["shots"]]
    first, second = shots[0], shots[1]
    plan["scenes"][0]["shots"][0]["beats"] = ["A man speaks on a platform."]
    json.dump(plan, open(os.path.join(d, "production.json"), "w"))
    R.enqueue(d, [first["id"]], "fal", "test/model", {})
    R.run(d, poll_every=0)
    store = R.Store(d)
    take = next(j for j in store.jobs if j["shot_id"] == first["id"])
    assert take["state"] == "ready"
    jobs_before, take_hash = len(store.jobs), sha(os.path.join(d, take["output"]))
    a0, a1 = first["start"] + 0.3, first["end"] - 0.3

    # 2. exported untouched, the film is the song: none of the model's sound is in it, and the loudness is reported
    film = E.build(d, "square")
    x = audio_of(film["path"])
    assert level(x, a0, a1, MODEL) < 0.02                                  # the model's sound is not there
    assert film["loudness"] is not None and "shot_sound" not in film

    # 3. the sound panel for the shot: the take has sound, it is off, the song is whole
    g = SS.get(d, first["id"])
    assert g["has_audio"] and [l["id"] for l in g["layers"]] == ["song", "all"] and not g["layers"][1]["on"] and not g["changed"]

    # 4. keep the model's sound for this shot only: it is in the film under that shot, and only there
    SS.set_layer(d, first["id"], "all", on=True)
    film2 = E.build(d, "square")
    y = audio_of(film2["path"])
    assert level(y, a0, a1, MODEL) > 0.1 and level(y, second["start"] + 0.3, second["end"] - 0.3, MODEL) < 0.02
    assert film2["shot_sound"] == 1 and abs(film2["duration"] - film["duration"]) < 0.01
    lv = SS.levels(d, first["id"])
    assert lv["layers"]["all"] is not None and lv["peak_db"] < 0

    # 5. split it, drop the effects, keep the voices: the film follows
    SS.split(d, first["id"])
    SS.delete_layer(d, first["id"], "other")
    z = audio_of(E.build(d, "square")["path"])
    assert level(z, a0, a1, 500) > 0.05 and level(z, a0, a1, 2000) < 0.02 and level(z, a0, a1, MODEL) < 0.02
    SS.restore_layer(d, first["id"], "other")
    SS.set_layer(d, first["id"], "voice", on=False)
    w = audio_of(E.build(d, "square")["path"])
    assert level(w, a0, a1, 2000) > 0.05 and level(w, a0, a1, 500) < 0.02

    # 6. the preview of that part has the same sound, and layers on top do not change the film's sound
    SS.set_layer(d, first["id"], "voice", on=True)
    pre = E.build(d, "youtube", (first["start"], first["end"]))
    assert pre["preview"] and level(audio_of(pre["path"]), 0.3, first["end"] - first["start"] - 0.3, 500) > 0.05
    O.add(d, {"kind": "text", "text": "HELLO", "size": 0.2, "x": 0.5, "y": 0.2, "start": 1, "end": 8, "color": "#ffffff", "fade": 0.05})
    v = audio_of(E.build(d, "square")["path"])
    assert level(v, a0, a1, 500) > 0.05 and level(v, a0, a1, 2000) > 0.05

    # 7. a change to the layers can be taken back, and everything above cost nothing and changed no take
    O.undo(d)
    assert O.load(d) == []
    O.redo(d)
    assert len(O.load(d)) == 1
    assert SS.reset(d, first["id"])["changed"] is False
    back = audio_of(E.build(d, "square")["path"])
    assert level(back, a0, a1, MODEL) < 0.02 and level(back, a0, a1, 500) < 0.02       # back to the song alone
    store = R.Store(d)
    assert len(store.jobs) == jobs_before and sha(os.path.join(d, take["output"])) == take_hash
