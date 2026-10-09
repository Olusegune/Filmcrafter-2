"""Subtitles, chapters, intermissions, ambience and the show budget, with real ffmpeg and no network."""
import json
import os
import re
import subprocess

import numpy as np
import pytest
import soundfile as sf

from filmcrafter_engine import export as E, show as S, show_finish as F
from filmcrafter_engine.export import ffmpeg


def _wav(path, secs=1.0, amp=0.2):
    t = np.linspace(0, secs, int(44100 * secs), endpoint=False)
    sf.write(str(path), (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32), 44100)
    return str(path)


def _info(path):
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", path], capture_output=True, text=True)
    return r.stderr


def _mean_db(path):
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", path, "-af", "volumedetect", "-vn", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else -91.0


@pytest.fixture
def show(tmp_path):
    return S.create(str(tmp_path / "shows"), "Night Market")["dir"]


@pytest.fixture
def fake_build(monkeypatch):
    """Stands in for each item's own export: a short blue film of the item's song length, with silent sound."""
    def build(d, preset):
        p = json.load(open(os.path.join(d, "project.json")))
        secs = float(json.load(open(os.path.join(d, "length.json")))["s"]) if os.path.exists(os.path.join(d, "length.json")) else 2.0
        out = os.path.join(d, "exports", f"{p['show_item']['id']}.mp4")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        F._run(["-f", "lavfi", "-t", str(secs), "-i", "color=c=blue:s=320x180:r=24", "-f", "lavfi", "-t", str(secs), "-i", "anullsrc=r=48000:cl=stereo",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", out])
        return {"path": out}
    monkeypatch.setattr(E, "build", build)


def _scene(show, tmp_path, title, lines, secs=3.0, act=None):
    r = S.add_scene(show, title, act=act)
    d = r["dir"]
    _wav(os.path.join(d, "song.wav"), secs)
    json.dump({"lines": [{"character": c, "text": t} for c, t, _, _ in lines],
               "timings": [{"character": c, "text": t, "start": a, "end": b} for c, t, a, b in lines]}, open(os.path.join(d, "dialogue.json"), "w"))
    json.dump({"s": secs}, open(os.path.join(d, "length.json"), "w"))
    return r


def _number(show, tmp_path, title, lyrics, secs=4.0, act=None):
    r = S.add_number(show, _wav(tmp_path / f"{title}.wav", secs), title, act=act)
    json.dump({"duration": secs, "lyrics": [{"section": "Verse", "text": t, "start": a, "end": b} for t, a, b in lyrics]},
              open(os.path.join(r["dir"], "songmap.json"), "w"))
    json.dump({"s": secs}, open(os.path.join(r["dir"], "length.json"), "w"))
    return r


# ---------------------------------------------------------------- pure helpers

def test_srt_and_chapter_formats():
    assert F._clock(3725.5) == "01:02:05,500" and F._clock(-3) == "00:00:00,000"
    assert F.chapter_list([(0, "Opening"), (75, "Act 2 · Scene"), (3700, "Finale")]) == "0:00 Opening\n1:15 Act 2 · Scene\n1:01:40 Finale\n"
    assert F._clean("a\n\nb --> c") == "a b -> c"
    assert F._meta_escape("a=b;c#d\\e") == "a\\=b\\;c\\#d\\\\e"


def test_budget_summary_math():
    b = F.budget_summary(100.0, 50.0, 10, 20)
    assert b["rate_per_shot"] == 5.0 and b["estimate_remaining_usd"] == 100.0 and b["estimate_over"] and not b["over"] and not b["near"]
    assert b["remaining_usd"] == 50.0
    assert F.budget_summary(100.0, 85.0, 10, 0)["near"] and F.budget_summary(100.0, 100.0, 10, 0)["over"]
    none = F.budget_summary(None, 12.0, 2, 30)                                       # no cap, too few renders for a rate
    assert none["rate_per_shot"] is None and none["estimate_remaining_usd"] is None and not none["over"]


# ---------------------------------------------------------------- intermissions

def test_intermission_cards_are_added_edited_and_bounded(show):
    r = S.add_intermission(show, "  Intermission \n 15 minutes ", seconds=500, subtitle="Please return to your seats")
    row = r["acts"][0]["items"][0]
    assert row["kind"] == "intermission" and row["title"] == "Intermission 15 minutes" and row["duration"] == F.MAX_CARD and row["problems"] == []
    st = S.set_card(show, r["item"], seconds=0.1)
    assert st["acts"][0]["items"][0]["duration"] == F.MIN_CARD
    with pytest.raises(SystemExit, match="isn't an intermission"):
        S.set_card(show, S.add_scene(show, "Talk")["item"], title="x")
    S.sync(show)                                                                     # a card has no cast to receive


def test_intermission_export_joins_with_the_rest(show, tmp_path, fake_build):
    _number(show, tmp_path, "Opening", [("Hello night", 0.5, 1.5)], secs=2.0)
    S.add_intermission(show, "Intermission", seconds=2.5)
    _number(show, tmp_path, "Finale", [("Goodbye", 0.2, 1.0)], secs=2.0)
    r = S.export(show)
    assert abs(r["duration"] - 6.5) < 0.6 and r["items"] == 3
    assert not os.path.exists(os.path.join(show, "exports", ".work"))               # scratch files are cleaned up
    info = _info(r["path"])
    assert "Video:" in info and "Audio:" in info


# ---------------------------------------------------------------- subtitles and chapters

def test_subtitles_and_chapters_follow_the_running_order(show, tmp_path, fake_build):
    S.add_act(show, "Act 2")
    _scene(show, tmp_path, "Closing time", [("Ada", "Fresh bread!", 0.5, 1.5), ("Ben", "Two,\n\nplease --> now", 1.8, 2.8)], secs=3.0, act=0)
    _number(show, tmp_path, "Opening Number", [("The lamps come on", 1.0, 3.0)], secs=4.0, act=0)
    _number(show, tmp_path, "Last Dance", [("Hello, night", 0.0, 1.0)], secs=2.0, act=1)
    r = S.export(show)
    srt = open(r["subtitles"], encoding="utf-8").read()
    assert "Ada: Fresh bread!" in srt and "Ben: Two, please -> now" in srt and "-->" in srt.split("\n")[1]
    assert "00:00:00,500 --> 00:00:01,500" in srt                                    # the scene starts the film
    assert re.search(r"00:00:0[34],\d{3} --> 00:00:0[56],\d{3}\nThe lamps come on", srt)  # the number begins after the 3 s scene
    chapters = open(r["chapters"], encoding="utf-8").read().splitlines()
    assert chapters[0] == "0:00 Act 1 · Closing time" and chapters[1].endswith("Opening Number") and chapters[2].endswith("Act 2 · Last Dance")
    info = _info(r["path"])
    assert r["embedded"] and info.count("Chapter #") == 3 and "Subtitle: mov_text" in info


def test_hostile_text_cannot_break_the_files_or_ffmpeg(show, tmp_path, fake_build):
    _scene(show, tmp_path, "x=y;#\\ \"quotes\" 'and' [CHAPTER]", [("Evil", "\"; rm -rf / ; ' -i /etc/passwd [CHAPTER] title=x", 0.2, 1.2)], secs=2.0)
    r = S.export(show)
    assert r["embedded"] and "embed_error" not in r
    assert _info(r["path"]).count("Chapter #") == 1
    assert "rm -rf" in open(r["subtitles"], encoding="utf-8").read()                # shown as text, never run


def test_subtitles_and_chapters_can_be_turned_off(show, tmp_path, fake_build):
    _scene(show, tmp_path, "Talk", [("Ada", "Hi", 0.2, 1.0)], secs=2.0)
    r = S.export(show, subtitles=False, chapters=False)
    assert "subtitles" not in r and "chapters" not in r
    assert not [f for f in os.listdir(os.path.join(show, "exports")) if f.endswith((".srt", ".txt"))]


# ---------------------------------------------------------------- ambience

def test_ambience_is_validated_and_only_for_scenes_and_cards(show, tmp_path):
    scene = S.add_scene(show, "Talk")["item"]
    num = S.add_number(show, _wav(tmp_path / "n.wav"), "Song")["item"]
    amb = _wav(tmp_path / "rain.wav", 1.0, 0.5)
    with pytest.raises(SystemExit, match="scene or an intermission"):
        S.set_ambience(show, num, amb)
    (tmp_path / "x.exe").write_bytes(b"MZ")
    with pytest.raises(SystemExit, match="audio file"):
        S.set_ambience(show, scene, str(tmp_path / "x.exe"))
    with pytest.raises(SystemExit, match="Choose an audio file"):
        S.set_ambience(show, scene)
    st = S.set_ambience(show, scene, amb, volume_db=-99)
    row = next(i for a in st["acts"] for i in a["items"] if i["id"] == scene)
    assert row["ambience"]["volume_db"] == -40.0 and os.path.exists(os.path.join(row["path"], row["ambience"]["file"])) and os.path.exists(amb)
    S.set_ambience(show, scene, clear=True)
    assert "ambience" not in next(i for a in S.status(show)["acts"] for i in a["items"] if i["id"] == scene)


def test_ambience_is_mixed_under_the_scene_when_exported(show, tmp_path, fake_build):
    scene = _scene(show, tmp_path, "Rain", [("Ada", "It rains.", 0.2, 1.0)], secs=3.0)
    quiet = S.export(show)
    assert _mean_db(quiet["path"]) < -80                                            # the stand-in scene is silent
    S.set_ambience(show, scene["item"], _wav(tmp_path / "rain.wav", 0.5, 0.6), volume_db=-12)   # shorter than the scene: it loops
    loud = S.export(show)
    assert _mean_db(loud["path"]) > -40 and abs(loud["duration"] - 3.0) < 0.5


def test_a_card_can_have_music_under_it(show, tmp_path, fake_build):
    card = S.add_intermission(show, "Intermission", seconds=3)["item"]
    S.set_ambience(show, card, _wav(tmp_path / "music.wav", 1.0, 0.6), volume_db=-10)
    r = S.export(show)
    assert _mean_db(r["path"]) > -40 and abs(r["duration"] - 3.0) < 0.5


# ---------------------------------------------------------------- budget

def test_the_show_budget_counts_every_items_spend(show, tmp_path):
    a = S.add_number(show, _wav(tmp_path / "a.wav"), "A")
    b = S.add_number(show, _wav(tmp_path / "b.wav"), "B")
    for d, n in ((a["dir"], 3), (b["dir"], 2)):
        json.dump({"jobs": [{"id": f"j{i}", "state": "ready", "provider": "fal", "estimate_usd": 1.5} for i in range(n)]}, open(os.path.join(d, "jobs.json"), "w"))
    st = S.status(show)
    assert st["budget"]["spent_usd"] == 7.5 and st["budget"]["cap_usd"] is None and not st["budget"]["over"]
    st = S.set_budget(show, 9)
    assert st["budget"]["cap_usd"] == 9.0 and st["budget"]["near"] and st["budget"]["remaining_usd"] == 1.5
    assert S.set_budget(show, 7)["budget"]["over"]
    assert S.set_budget(show, None)["budget"]["cap_usd"] is None
    for bad in (-5, "abc", 10_000_000):
        with pytest.raises((SystemExit, ValueError)):
            S.set_budget(show, bad)


def test_an_ambience_path_outside_the_item_is_ignored(show, tmp_path, fake_build):
    scene = _scene(show, tmp_path, "Rain", [("Ada", "It rains.", 0.2, 1.0)], secs=2.0)
    loud = _wav(tmp_path / "loud.wav", 1.0, 0.9)
    data = json.load(open(os.path.join(show, "show.json")))
    data["items"][scene["item"]]["ambience"] = {"file": os.path.relpath(loud, scene["dir"]), "volume_db": 0}
    json.dump(data, open(os.path.join(show, "show.json"), "w"))
    assert _mean_db(S.export(show)["path"]) < -80                                    # the file outside the item was not mixed in
