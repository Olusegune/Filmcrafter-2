"""The golden path of a film, end to end, with no provider and no spend: story, Bible, shots, storyboard, keyframe, video, assembly with sound, export, then close and reopen.

The pictures and clips here are made locally (a colour card and a test pattern from FFmpeg); everything between them is the real code."""
import json
import os
import subprocess

import pytest

from filmcrafter_engine import bible, export, make, shots, story

pytestmark = pytest.mark.integration

SCRIPT = """INT. KITCHEN - MORNING

Sarah pours tea. A letter lies by the sink.

SARAH
He said he would call.

JOHN
Did you say something?

EXT. PLATFORM - NIGHT

Rain on the roof. A train waits.

SARAH
I am going.
"""


def _ffmpeg():
    from filmcrafter_engine import library
    return library._ffmpeg()


def _clip(path, seconds):
    subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=size=640x360:rate=24:duration={seconds}", "-pix_fmt", "yuv420p", path], check=True)


def _png(path):
    subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x334455:s=320x180", "-frames:v", "1", path], check=True)


def _job(d, sid, jid, kind, rel, purpose=None, n=1):
    path = os.path.join(make.render_dir(d), "jobs.json")
    data = json.load(open(path)) if os.path.exists(path) else {"schema_version": 1, "jobs": []}
    j = {"id": jid, "shot_id": sid, "plan": "production", "state": "ready", "kind": kind, "provider": "fal", "model": "m", "output": rel, "created": 100 + n, "updated": 100 + n, "frame": "start", "overrides": {}}
    if purpose:
        j["purpose"] = purpose
    data["jobs"].append(j)
    json.dump(data, open(path, "w"))


def test_a_film_from_a_screenplay_to_an_exported_file_and_back(tmp_path):
    # STORY: import, analyse, keep as it is, lock
    src = tmp_path / "last-train.fountain"
    src.write_text(SCRIPT, encoding="utf-8")
    d = story.create(str(tmp_path / "films"), "Last Train", "screenplay", SCRIPT, str(src))["dir"]
    story.as_is(d)
    assert story.lock(d)["story"]["locked"] == 1

    # BIBLE, CAST & WORLD: seeded from the story, then the person's own picture and style
    assert bible.seed(d)["added"] == {"characters": 2, "environments": 2}
    bible.update_rules(d, {"style": {"lane": "painterly animation"}, "rules": {"world": "A rainy town"}})
    sarah = tmp_path / "sarah.png"
    _png(str(sarah))
    bible.add_media(d, "character", "c_sarah", str(sarah), "Master", "master")

    # BREAKDOWN: shots with contracts, acting, camera and light
    r = shots.breakdown(d)
    ids = [s["id"] for s in r["shots"]]
    assert len(ids) >= 4
    shots.set_fields(d, ids[1], {"performance": {"emotional_intention": "Held-back dread"}})
    sug = shots.suggest(d, ids[1])
    shots.set_fields(d, ids[1], {"camera": {"angle": sug["camera"]["angle"], "movement": sug["camera"]["movement"]}, "lighting": {"description": sug["lighting"]["description"]}})

    # STORYBOARD + KEYFRAME + VIDEO: the render project is built; pictures and clips arrive (here made locally, as a provider would return them)
    s = make.sync(d)
    rd = s["render_dir"]
    assert s["shots"] == len(ids) and os.path.isfile(os.path.join(rd, "soundtrack.wav"))
    os.makedirs(os.path.join(rd, "media"), exist_ok=True)
    for i, sid in enumerate(ids):
        _png(os.path.join(rd, "media", f"sb{i}.png"))
        _png(os.path.join(rd, "media", f"kf{i}.png"))
        _clip(os.path.join(rd, "media", f"v{i}.mp4"), 2)
        _job(d, sid, f"sb{i}", "image", f"media/sb{i}.png", "storyboard", n=1)
        _job(d, sid, f"kf{i}", "image", f"media/kf{i}.png", "keyframe", n=2)
        _job(d, sid, f"v{i}", "video", f"media/v{i}.mp4", n=3)
        make.choose(d, sid, "storyboard", f"sb{i}")
        make.lock(d, sid, "storyboard")
        make.use_storyboard_as_reference(d, sid)
        make.choose(d, sid, "keyframe", f"kf{i}")
        make.lock(d, sid, "keyframe")
        make.choose(d, sid, "video", f"v{i}")
    st = make.status(d)
    assert st["counts"] == {"shots": len(ids), "storyboard": len(ids), "keyframe": len(ids), "video": len(ids)}

    # SOUND: a soundtrack the person brought
    music = tmp_path / "music.wav"
    subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=330:duration=30", str(music)], check=True)
    assert make.set_soundtrack(d, str(music))["soundtrack"]["kind"] == "file"

    # SAVE, CLOSE, REOPEN: everything is on disk, so a fresh read sees all of it
    again = make.status(d)
    assert again["counts"] == st["counts"] and story.status(d)["story"]["locked"] == 1
    assert len(bible.view(d)["characters"]) == 2 and all(c["locks"]["keyframe"] for c in (shots.get_shot(d, i)["shot"] for i in ids))

    # CONTINUE: a new story version does not disturb the locked story or the shots already made
    story.add_version(d, SCRIPT + "\nINT. TRAIN - NIGHT\n\nSarah sits.\n", "Added a scene")
    assert story.status(d)["story"]["locked"] == 1 and make.status(d)["counts"]["video"] == len(ids)

    # EXPORT: the film is assembled from the chosen takes over the soundtrack
    out = export.build(rd, "preview")
    assert os.path.isfile(out["path"]) and out["rendered"] == out["shots"] == len(ids) and not out["draft"]
    total = sum(float(c["generation"]["duration"]) for c in make._contracts(d))
    probe = subprocess.run([_ffmpeg(), "-i", out["path"]], capture_output=True, text=True)
    assert "Audio:" in probe.stderr and "Video:" in probe.stderr
    assert abs(out["duration"] - total) < 0.5


def test_a_silent_film_still_exports(tmp_path):
    d = story.create(str(tmp_path / "films"), "Quiet", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    ids = [s["id"] for s in shots.breakdown(d)["shots"]]
    make.sync(d)
    os.makedirs(os.path.join(make.render_dir(d), "media"), exist_ok=True)
    for i, sid in enumerate(ids):
        _clip(os.path.join(make.render_dir(d), "media", f"v{i}.mp4"), 2)
        _job(d, sid, f"v{i}", "video", f"media/v{i}.mp4")
    out = export.build(make.render_dir(d), "preview")
    assert os.path.isfile(out["path"]) and not out["draft"]
