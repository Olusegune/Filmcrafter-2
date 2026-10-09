"""End to end: one whole journey, from an audio file to a finished film, using the real engine code and real ffmpeg. Only the paid services are stood in for
(a fake renderer that hands back a real short clip). The journey: a song is listened to -> a shot plan is made on the bars -> one shot is rendered, one is the
user's own clip, one a moving still -> a frame is inserted -> layers (text, a shape with keyframes, an icon) are added -> an unused take is cleaned up and
brought back -> the film is exported -> the exported file is checked: its length, its sound, and what is on screen at known moments."""
import json
import os
import subprocess

import pytest
from PIL import Image

from filmcrafter_engine import analyze, cleanup, customframe, export as E, library as L, media, overlays as O, render as R
from tests.test_render import FakeProvider, field, man

pytestmark = pytest.mark.e2e

SECONDS = 16.0


def ff(*args):
    subprocess.run([E.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args], check=True, creationflags=E.NO_WINDOW)


@pytest.fixture(scope="module")
def parts(tmp_path_factory):
    """A 16 s click track at 120 bpm (the 'song'), a green clip (what the fake renderer returns) and a red clip (the user's own)."""
    d = tmp_path_factory.mktemp("parts")
    import numpy as np
    import soundfile as sf
    sr = 22050
    t = np.arange(int(sr * SECONDS)) / sr
    clicks = np.zeros_like(t)
    for beat in np.arange(0, SECONDS, 0.5):                           # 120 bpm: a short decaying burst on every beat, stronger on the bar
        i = int(beat * sr)
        n = min(len(t) - i, int(0.08 * sr))
        gain = 1.0 if round(beat / 0.5) % 4 == 0 else 0.6
        clicks[i:i + n] += gain * np.sin(2 * np.pi * 1000 * t[:n]) * np.exp(-t[:n] * 60)
    sf.write(str(d / "song.wav"), (0.8 * clicks).astype("float32"), sr)
    ff("-f", "lavfi", "-i", "color=c=0x00aa00:s=320x180:r=24:d=6", "-pix_fmt", "yuv420p", str(d / "green.mp4"))
    ff("-f", "lavfi", "-i", "color=c=0xcc0000:s=320x180:r=24:d=6", "-pix_fmt", "yuv420p", str(d / "red.mp4"))
    return d


@pytest.fixture
def journey(parts, tmp_path, monkeypatch):
    d = tmp_path / "film"
    d.mkdir()
    (d / "song.wav").write_bytes((parts / "song.wav").read_bytes())
    (d / "project.json").write_text(json.dumps({"title": "Journey", "song": "song.wav", "aspect_ratio": "16:9"}))
    green = (parts / "green.mp4").read_bytes()

    class Download:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_content(self, n): yield green

    FakeProvider.submits, FakeProvider.submit_error = 0, None
    FakeProvider.poll_result = {"state": "done", "url": "https://cdn/out.mp4"}
    monkeypatch.setitem(R.PROVIDERS, "fal", FakeProvider)
    m = man(field("prompt", required=True), field("duration", enum=["5", "10"]))
    monkeypatch.setattr(R, "manifest", lambda provider, model, refresh=False: m)
    monkeypatch.setattr(R, "_review", lambda d, store, j: None)
    monkeypatch.setattr(R.requests, "get", lambda url, **kw: Download())
    return str(d), parts


def frame(video, t, out):
    ff("-ss", str(t), "-i", video, "-frames:v", "1", out)
    return Image.open(out).convert("RGB")


def probe(video):
    p = subprocess.run([E.ffmpeg(), "-hide_banner", "-i", video], capture_output=True, text=True, creationflags=E.NO_WINDOW)
    import re
    dur = re.search(r"Duration: (\d+):(\d+):([\d.]+)", p.stderr)
    return float(dur[1]) * 3600 + float(dur[2]) * 60 + float(dur[3]), "Audio:" in p.stderr, "Video:" in p.stderr


def test_a_song_becomes_a_finished_film(journey, tmp_path):
    d, parts = journey

    # 1. the song is listened to, and a shot plan is cut on the bars (no AI involved)
    assert analyze.main([os.path.join(d, "song.wav"), "--out", os.path.join(d, "songmap.json")]) == 0
    sm = json.load(open(os.path.join(d, "songmap.json")))
    assert abs(sm["duration"] - SECONDS) < 0.5 and sm["bpm"] > 0
    made = media.plan_from_song(d, bars=1)
    plan = json.load(open(os.path.join(d, "production.json")))
    shots = [s for sc in plan["scenes"] for s in sc["shots"]]
    assert made["shots"] == len(shots) >= 4 and shots[0]["start"] == 0.0
    first, second, third = shots[0]["id"], shots[1]["id"], shots[2]["id"]

    # 2. three ways to fill shots: a rendered take, the user's own clip, a moving still
    assert R.enqueue(d, [first], "fal", "test/model", {}) == []              # a shot with nothing described yet is never sent (it would pay for a blank prompt)
    plan["scenes"][0]["shots"][0]["beats"] = ["A man waits on a platform."]       # the user writes what the shot should show
    json.dump(plan, open(os.path.join(d, "production.json"), "w"))
    R.enqueue(d, [first], "fal", "test/model", {})
    R.run(d, poll_every=0)
    take = next(j for j in R.Store(d).jobs if j["shot_id"] == first)
    assert take["state"] == "ready" and os.path.isfile(os.path.join(d, take["output"]))
    media.import_media(d, second, str(parts / "red.mp4"))
    still = tmp_path / "still.png"
    Image.new("RGB", (320, 180), (0, 0, 200)).save(still)
    media.import_media(d, third, str(still), motion="zoom_in")
    L.approve(d, first, take["id"])

    # 3. a second take of the first shot exists that nothing uses: clean-up finds it, moves it to the trash, and brings it back
    R.enqueue(d, [first], "fal", "test/other", {})
    R.run(d, poll_every=0)
    jobs = [j for j in R.Store(d).jobs if j["shot_id"] == first and j["state"] == "ready"]
    assert len(jobs) == 2
    for j in jobs:                                                      # a take counts as new for ten minutes: age both so the engine may offer the spare
        t = os.path.getmtime(os.path.join(d, j["output"])) - 7200
        os.utime(os.path.join(d, j["output"]), (t, t))
    spare = next(j for j in jobs if j["id"] != take["id"])
    listed = {i["path"] for i in cleanup.scan(d)["items"]}
    assert spare["output"] in listed and take["output"] not in listed
    cleanup.discard(d, [spare["output"]])
    assert not os.path.exists(os.path.join(d, spare["output"]))
    assert cleanup.restore(d)["restored"] == 1 and os.path.exists(os.path.join(d, spare["output"]))

    # 4. a colour card is inserted after the first shot, using time the song already has: the film stays as long as the song
    last_end = max(s["end"] for s in shots)
    card = customframe.insert(d, {"where": "after", "shot": first, "length": 1.0, "mode": "colour", "color": "#ffff00"})
    plan = json.load(open(os.path.join(d, "production.json")))
    ends = [s["end"] for sc in plan["scenes"] for s in sc["shots"]]
    assert max(ends) == last_end and card["trimmed"]["shot"] == first

    # 5. layers: a title, a shape that travels, an icon that pulses to the beat
    O.add(d, {"kind": "text", "text": "HELLO", "size": 0.2, "x": 0.5, "y": 0.2, "start": 1, "end": 12, "anim": "typewriter", "color": "#ffffff", "shadow": False, "fade": 0.05})
    O.add(d, {"kind": "shape", "shape": "rect", "width": 0.1, "height": 0.2, "x": 0.5, "y": 0.75, "color": "#ffffff", "start": 6, "end": 14, "fade": 0.05,
              "keys": [{"t": 0, "x": 0.2, "ease": "linear"}, {"t": 4, "x": 0.8}]})
    O.add(d, {"kind": "icon", "icon": "star", "width": 0.1, "x": 0.9, "y": 0.1, "color": "#ffd166", "start": 2, "end": 14, "anim": "pulse"})

    # 6. the film is exported
    out = E.build(d, "square")
    video = out["path"]
    secs, has_audio, has_video = probe(video)
    assert has_audio and has_video and abs(secs - SECONDS) < 0.5, (secs, has_audio, has_video)
    assert out.get("draft") is not None

    # 7. what is on screen at known moments
    t_red = (shots[1]["start"] + shots[1]["end"]) / 2
    px = frame(video, t_red, str(tmp_path / "red.png")).getpixel((300, 170))
    assert px[0] > 150 and px[1] < 80, px                               # the user's own red clip in its shot
    mid_card = (card["start"] + card["end"]) / 2
    cp = frame(video, mid_card, str(tmp_path / "card.png")).getpixel((300, 170))
    assert cp[0] > 200 and cp[1] > 200 and cp[2] < 90, cp               # the yellow card
    w = frame(video, 9.0, str(tmp_path / "late.png"))
    bright = w.convert("L").point(lambda v: 255 if v > 200 else 0)
    assert bright.crop((0, 0, w.width, int(w.height * 0.4))).getbbox()                                      # the title is up, in the top part
    low = bright.crop((0, int(w.height * 0.55), w.width, w.height)).getbbox()                               # the travelling box, along the bottom
    expected = 0.2 + 0.6 * (0.75 * 0.75 * (3 - 2 * 0.75))                                                   # 3 s into its 4 s journey, easing in and out
    assert low and abs((low[0] + low[2]) / 2 / w.width - expected) < 0.06, (low, expected)
