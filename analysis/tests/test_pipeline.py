"""Lyrics alignment, script import and export assembly (no network, no GPU)."""
import json
import os
import subprocess
import wave

import pytest
from PIL import Image

from filmcrafter_engine import export as E
from filmcrafter_engine import library as L
from filmcrafter_engine import script_import as S


# ------------------------------------------------------------------ lyrics

# ------------------------------------------------------------------ script import

SCRIPT = """TITLE: Exit Plan LOGLINE: A man learns to stay. VISUAL STYLE: warm amber vs cold cyan
CHARACTER: SEGE ARCHETYPE: Wounded Hero APPEARANCE: A Nigerian man. MOTIVATION: To stay. ACTING NOTES: Restrained.
CHARACTER: AMARA ARCHETYPE: Ally APPEARANCE: A Nigerian woman. MOTIVATION: Honesty. ACTING NOTES: Stillness.
INT. BEDROOM - NIGHT LOGLINE: He wakes. CHARACTER(S): Sege, Amara DIALOGUE: I wake before the light
SHOTS: SHOT 1: Close-up on Sege's eye opening. SHOT 2: Wide shot of the bedroom, Amara asleep.
EXT. ROOFTOP - DAWN LOGLINE: He stays. CHARACTER(S): Sege DIALOGUE: I stay
SHOTS: SHOT 1: Wide shot of Sege at sunrise. END CARD: EXIT PLAN FADE OUT."""


def test_parse_script_meta_characters_scenes_shots():
    meta, chars, scenes = S.parse_script(SCRIPT)
    assert meta["TITLE"].startswith("Exit Plan") and meta["END CARD"].startswith("EXIT PLAN")
    assert [c.name for c in chars] == ["Sege", "Amara"]
    assert [s.heading for s in scenes] == ["INT. BEDROOM - NIGHT", "EXT. ROOFTOP - DAWN"]
    assert len(scenes[0].shots) == 2 and scenes[0].shots[0].performers == ["Sege"]
    assert "Amara" in scenes[0].shots[1].performers


def test_time_shots_cut_on_beats_and_cover_the_scene():
    _, _, scenes = S.parse_script(SCRIPT)
    sm = {"duration": 20.0, "downbeats": [0, 2, 4, 6, 8, 10, 12, 14, 16, 18], "beats": [i * 0.5 for i in range(41)],
          "lyrics": [{"text": "I wake before the light", "start": 1.0, "end": 3.0},
                     {"text": "I stay", "start": 12.3, "end": 14.0}],
          "sections": [{"start": 0, "end": 20, "group": "VERSE"}], "accents": []}
    S.anchor_scenes(scenes, sm)
    assert scenes[0].start == 0.0 and scenes[0].end == 12 and scenes[1].end == 20.0
    S.time_shots(scenes, sm)
    a, b = scenes[0].shots
    assert a.start == 0.0 and a.end == b.start and b.end == 12 and (a.end * 2) == int(a.end * 2)  # on the half-beat grid
    assert a.lyrics == ["I wake before the light"]


# ------------------------------------------------------------------ export

def _clip(path, seconds, color):
    subprocess.run([E.ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={color}:s=320x180:r=24:d={seconds}",
                    "-pix_fmt", "yuv420p", path], check=True, creationflags=E.NO_WINDOW)


def _song(path, seconds):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
        w.writeframes(b"\0\0" * int(22050 * seconds))


def _frames(path):
    p = subprocess.run([E.ffmpeg(), "-hide_banner", "-i", path, "-map", "0:v:0", "-c", "copy", "-f", "null", "-"],
                       capture_output=True, text=True, creationflags=E.NO_WINDOW)
    import re
    return int(re.findall(r"frame=\s*(\d+)", p.stderr)[-1])


@pytest.fixture
def exp_proj(tmp_path):
    d = tmp_path / "e"
    (d / "generations").mkdir(parents=True)
    shots = [{"id": "S01-01", "start": 0.0, "end": 1.5, "beats": ["a"], "performers": []},
             {"id": "S01-02", "start": 1.5, "end": 3.0, "beats": ["b"], "performers": []}]
    (d / "production.json").write_text(json.dumps({"scenes": [{"number": 1, "heading": "INT. ROOM", "shots": shots}]}))
    (d / "project.json").write_text(json.dumps({"title": "T", "song": "song.wav"}))
    (d / "songmap.json").write_text(json.dumps({"duration": 3.0}))
    _song(str(d / "song.wav"), 3.0)
    _clip(str(d / "generations" / "S01-01__old.mp4"), 2, "red")
    _clip(str(d / "generations" / "S01-01__new.mp4"), 2, "blue")
    jobs = [{"id": "old", "shot_id": "S01-01", "plan": "production", "state": "ready", "output": "generations/S01-01__old.mp4",
             "created": 1, "kind": "video"},
            {"id": "new", "shot_id": "S01-01", "plan": "production", "state": "ready", "output": "generations/S01-01__new.mp4",
             "created": 2, "kind": "video"}]
    (d / "jobs.json").write_text(json.dumps({"jobs": jobs}))
    return str(d)


def test_export_is_frame_exact_draft_with_slates(exp_proj):
    r = E.build(exp_proj, "square")
    assert r["draft"] and r["rendered"] == 1 and r["shots"] == 2        # S01-02 has no take: a slate stands in
    assert _frames(r["path"]) == 72                                      # 3.0 s × 24 fps exactly


def test_export_uses_the_approved_version(exp_proj):
    L.approve(exp_proj, "S01-01", "old")
    r = E.build(exp_proj, "square")
    first = os.path.join(os.path.dirname(r["path"]), "f.png")
    subprocess.run([E.ffmpeg(), "-y", "-loglevel", "error", "-i", r["path"], "-frames:v", "1", first], check=True,
                   creationflags=E.NO_WINDOW)
    px = Image.open(first).convert("RGB").getpixel((10, 10))
    assert px[0] > 150 and px[2] < 100                                   # red = the approved (older) take, not the newest


def test_script_import_refuses_to_replace_a_plan_with_nothing(tmp_path, capsys):
    sm = tmp_path / "sm.json"
    sm.write_text(json.dumps({"duration": 20.0, "downbeats": [0, 4, 8, 12, 16], "beats": [i * 0.5 for i in range(41)],
                              "lyrics": [], "sections": [{"start": 0, "end": 20, "group": "VERSE"}], "accents": []}))
    story = tmp_path / "story.txt"; story.write_text("Just a vibe: a man walks home through Lagos at night.")
    out = tmp_path / "production.json"; out.write_text('{"keep": true}')
    assert S.main([str(story), str(sm), str(out)]) == 1
    assert json.loads(out.read_text()) == {"keep": True} and "No scenes" in capsys.readouterr().out
    good = tmp_path / "script.txt"; good.write_text(SCRIPT)
    assert S.main([str(good), str(sm), str(out)]) == 0
    assert len(json.loads(out.read_text())["scenes"]) == 2


def test_adopting_a_script_archives_the_old_plan_and_its_takes(tmp_path):
    d = tmp_path / "p"; d.mkdir()
    (d / "songmap.json").write_text(json.dumps({"duration": 20.0, "downbeats": [0, 4, 8, 12, 16], "beats": [i * 0.5 for i in range(41)],
                                                "lyrics": [], "sections": [{"start": 0, "end": 20, "group": "VERSE"}], "accents": []}))
    (d / "production.json").write_text(json.dumps({"scenes": [{"number": 1, "shots": [{"id": "S01-01"}]}]}))
    (d / "directed.json").write_text(json.dumps({"scenes": []}))
    (d / "jobs.json").write_text(json.dumps({"jobs": [{"id": "a", "shot_id": "S01-01", "plan": "directed", "state": "ready", "created": 1}]}))
    (d / "keyframes.json").write_text(json.dumps({"directed": {"S01-01": "project:x.png"}}))
    (d / "shots.json").write_text(json.dumps({"S01-01": {"approved": "a"}}))
    bad = tmp_path / "vibe.txt"; bad.write_text("just a feeling")
    with pytest.raises(SystemExit):
        S.adopt(str(d), str(bad))
    assert (d / "directed.json").exists()                         # nothing changed
    good = tmp_path / "s.txt"; good.write_text(SCRIPT)
    r = S.adopt(str(d), str(good))
    assert r["shots"] >= 3 and len(r["archived"]) == 2
    assert not (d / "directed.json").exists() and not (d / "shots.json").exists()
    job = json.loads((d / "jobs.json").read_text())["jobs"][0]
    assert job["plan"].startswith("directed.before-")               # old take no longer attaches to the new S01-01
    assert list(json.loads((d / "keyframes.json").read_text())) == [job["plan"]]
    assert len(json.loads((d / "production.json").read_text())["scenes"]) == 2


def test_every_part_of_the_exported_film_carries_the_same_colour_labels(exp_proj):
    """A real export had an untagged opening (a slate) followed by shots tagged HD (Rec. 709, studio range): the settings changed part-way through the file and ffmpeg
    had to reset its filters there. The slate and the shot are now labelled alike."""
    L.approve(exp_proj, "S01-01", "old")
    r = E.build(exp_proj, "square")                                                   # S01-01 has a take, S01-02 is a slate
    seen = []
    for t in (0.2, 2.5):
        p = subprocess.run([E.ffmpeg(), "-hide_banner", "-ss", str(t), "-i", r["path"], "-frames:v", "1", "-vf", "showinfo", "-f", "null", "-"],
                           capture_output=True, text=True, creationflags=E.NO_WINDOW)
        import re
        seen.append(re.search(r"color_range:(\w+) color_space:(\w+)", p.stderr).groups())
    assert seen[0] == seen[1] == ("tv", "bt709")


def test_a_preview_is_just_the_part_asked_for_with_its_layers_and_sound_and_leaves_the_full_export_alone(exp_proj):
    """A preview of a few seconds: small, quick, the right length, the song's sound for that part, and layers drawn where they belong in it."""
    from filmcrafter_engine import overlays as O
    L.approve(exp_proj, "S01-01", "old")                                                       # 0-1.5 s a red clip; 1.5-3.0 s a slate
    O.add(exp_proj, {"kind": "shape", "shape": "rect", "width": 0.5, "height": 0.5, "x": 0.5, "y": 0.5, "color": "#00ff00", "start": 1.6, "end": 2.9, "fade": 0.05, "shadow": False})
    r = E.build(exp_proj, "preview", window=(1.0, 2.5))
    assert r["preview"] and (r["width"], r["height"]) == (640, 360) and r["window"] == [1.0, 2.5] and r["overlays"] == 1
    assert os.path.dirname(r["path"]).endswith("previews") and not [f for f in os.listdir(os.path.join(exp_proj, "exports")) if f.endswith(".mp4")]
    assert _frames(r["path"]) == 36                                                              # 1.5 s at 24 fps, exactly
    p = subprocess.run([E.ffmpeg(), "-hide_banner", "-i", r["path"]], capture_output=True, text=True, creationflags=E.NO_WINDOW)
    assert "Audio:" in p.stderr
    px = {}
    for name, t in (("red", 0.2), ("slate_with_layer", 1.2)):                                   # preview time 0.2 s is film time 1.2 s (red clip); 1.2 s is film time 2.2 s (slate + green box)
        out = os.path.join(os.path.dirname(r["path"]), f"{name}.png")
        subprocess.run([E.ffmpeg(), "-y", "-loglevel", "error", "-ss", str(t), "-i", r["path"], "-frames:v", "1", out], check=True, creationflags=E.NO_WINDOW)
        px[name] = Image.open(out).convert("RGB").getpixel((320, 180))
    assert px["red"][0] > 150 and px["red"][1] < 90                                              # the red clip is still on at film time 1.2 s
    assert px["slate_with_layer"][1] > 200 and px["slate_with_layer"][0] < 80                    # the layer, placed by film time, is up at film time 2.2 s
    with pytest.raises(SystemExit, match="half a second"):
        E.build(exp_proj, "preview", window=(5.0, 6.0))
