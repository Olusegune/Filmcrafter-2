"""Compose: motion-control takes (a motion video + a character picture), pictures-as-references takes, a direction note. Mock provider; real ffmpeg for the videos."""
import json
import os
import subprocess

import pytest
from PIL import Image

from filmcrafter_engine import compose as CO, render as R
from filmcrafter_engine.export import ffmpeg


def F(name, type="string", **kw):
    return {"name": name, "type": type, "items": kw.get("items"), "enum": kw.get("enum"), "default": kw.get("default"), "minimum": None, "maximum": None,
            "max_items": kw.get("max_items"), "max_length": kw.get("max_length"), "description": kw.get("description", ""), "required": kw.get("required", False)}


def kling_v3():
    return R._finish("kie", "kling/motion-control-v3", "Kling-3.0 motion-control", "", [
        F("prompt", max_length=2500, description="(Optional) Text prompt words"), F("input_urls", "array", items="string", required=True, description="(Required) Include a URL of an image"),
        F("video_urls", "array", items="string", required=True, description="(Required) Include a video URL"), F("mode", description="(Optional) std: Standard Mode (720p). pro: Professional Mode (1080p)"),
        F("character_orientation", description="video: Refer to video (recommended); image: Refer to image"), F("background_source", description="input_video or input_image")])


def kling_26():
    return R._finish("kie", "kling/motion-control", "Kling 2.6 motion-control", "", [
        F("prompt", max_length=2500), F("input_urls", "array", items="string", required=True), F("video_urls", "array", items="string", required=True),
        F("character_orientation", enum=["image", "video"], required=True), F("mode", enum=["720p", "1080p"], required=True)])


def clip(path, seconds, rate=12):
    p = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=160x90:rate={rate}:duration={seconds}", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path)],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return str(path)


@pytest.fixture
def project(tmp_path):
    d = tmp_path / "p"
    (d / "media").mkdir(parents=True)
    shot = {"id": "S01-01", "scene": 1, "number": 1, "start": 0.0, "end": 8.0, "beats": ["She dances."], "performers": ["Amara"], "framing": "wide", "camera_moves": [], "source_shots": ["S01-01"]}
    (d / "production.json").write_text(json.dumps({"meta": {}, "characters": [], "scenes": [{"number": 1, "heading": "INT. ROOM", "start": 0, "end": 8, "notes": {}, "shots": [shot]}]}))
    (d / "project.json").write_text(json.dumps({"title": "T", "song": "s.wav", "aspect_ratio": "16:9"}))
    (d / "songmap.json").write_text(json.dumps({"duration": 8.0, "lyrics": [], "sections": [], "beats": []}))
    Image.new("RGB", (64, 36), (200, 30, 30)).save(d / "media" / "kf.png")
    (d / "keyframes.json").write_text(json.dumps({"production": {"S01-01": "project:media/kf.png"}}))
    (d / "jobs.json").write_text(json.dumps({"jobs": []}))
    return str(d)


@pytest.fixture
def video(tmp_path):
    return clip(tmp_path / "dance.mp4", 6)


# ---------------------------------------------------------------- the motion video and the character

def test_a_fresh_shot_asks_for_a_motion_video_and_uses_its_keyframe_as_the_character(project):
    s = CO.state(project, "S01-01")
    assert not s["ready"] and s["image"] == "media/kf.png" and s["image_is_start"] and s["missing"] == ["a motion video"] and s["shot_seconds"] == 8.0


def test_a_good_video_is_copied_into_the_project_and_measured(project, video):
    s = CO.set_motion(project, "S01-01", {"video_path": video})
    assert s["ready"] and 5.5 < s["video_seconds"] < 6.5 and s["video"].startswith("media/S01-01_motion_") and os.path.exists(os.path.join(project, s["video"])) and os.path.exists(video)


def test_a_motion_video_shorter_than_the_shot_says_what_will_happen(project, video):
    s = CO.set_motion(project, "S01-01", {"video_path": video})
    assert any("hold the final frame" in n for n in s["notes"])


def test_a_longer_video_is_trimmed_and_facing_the_picture_has_a_ten_second_limit(project, tmp_path):
    plan = json.load(open(os.path.join(project, "production.json")))
    plan["scenes"][0]["shots"][0]["end"] = 4.0
    json.dump(plan, open(os.path.join(project, "production.json"), "w"))
    s = CO.set_motion(project, "S01-01", {"video_path": clip(tmp_path / "long.mp4", 12), "orientation": "image"})
    assert any("trimmed to the shot" in n for n in s["notes"]) and any("10 seconds" in n for n in s["notes"])


@pytest.mark.parametrize("make,why", [(lambda t: clip(t / "short.mp4", 2), "3 to 30 seconds"), (lambda t: str(t / "nope.mp4"), "can't be found"), (lambda t: str(t / "a.avi"), "MP4 or MOV")])
def test_bad_videos_are_refused_in_plain_words(project, tmp_path, make, why):
    path = make(tmp_path)
    if path.endswith(".avi"):
        open(path, "w").write("x")
    with pytest.raises(SystemExit) as e:
        CO.set_motion(project, "S01-01", {"video_path": path})
    assert why in str(e.value)


def test_a_file_that_is_not_a_video_is_refused(project, tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(SystemExit) as e:
        CO.set_motion(project, "S01-01", {"video_path": str(bad)})
    assert "can't be read as a video" in str(e.value)


def test_your_own_character_picture_replaces_the_keyframe_until_you_go_back(project, tmp_path, video):
    img = tmp_path / "me.jpg"
    Image.new("RGB", (32, 32)).save(img)
    s = CO.set_motion(project, "S01-01", {"video_path": video, "image_path": str(img)})
    assert s["image"].startswith("media/S01-01_character_") and not s["image_is_start"]
    s = CO.set_motion(project, "S01-01", {"image_from_start": True})
    assert s["image"] == "media/kf.png" and s["image_is_start"]
    with pytest.raises(SystemExit):
        CO.set_motion(project, "S01-01", {"image_path": str(tmp_path / "a.gif")})


def test_settings_are_checked_and_kept(project):
    s = CO.set_motion(project, "S01-01", {"orientation": "image", "quality": "std", "background": "image", "note": "x" * 900})
    assert (s["orientation"], s["quality"], s["background"]) == ("image", "std", "image") and len(s["note"]) == 600
    for bad in ({"orientation": "sideways"}, {"quality": "ultra"}):
        with pytest.raises(SystemExit):
            CO.set_motion(project, "S01-01", bad)


def test_a_locked_shot_is_not_changed_and_clearing_forgets_the_motion(project, video):
    from filmcrafter_engine import library as L
    CO.set_motion(project, "S01-01", {"video_path": video})
    assert CO.clear_motion(project, "S01-01")["video"] is None
    L.set_shot(project, "S01-01", locked=True)
    with pytest.raises(SystemExit) as e:
        CO.set_motion(project, "S01-01", {"video_path": video})
    assert "locked" in str(e.value)


# ---------------------------------------------------------------- what is sent

def test_kling_3_motion_request_is_the_picture_the_video_and_the_settings():
    m = kling_v3()
    p = R.compile_motion("/nowhere", m, {}, {"video": "media/v.mp4", "image": "media/c.png", "orientation": "video", "quality": "pro", "note": "Slow and graceful."})
    assert p["video_urls"] == ["project:media/v.mp4"] and p["input_urls"] == ["project:media/c.png"]
    assert p["mode"] == "pro" and p["character_orientation"] == "video" and p["background_source"] == "input_video"
    assert p["prompt"].startswith("Slow and graceful.") and "keeps exactly the face" in p["prompt"]


def test_kling_2_6_motion_uses_the_models_own_words_for_quality_and_facing():
    p = R.compile_motion("/nowhere", kling_26(), {}, {"video": "v.mp4", "image": "c.png", "orientation": "image", "quality": "std"})
    assert p["mode"] == "720p" and p["character_orientation"] == "image"
    assert R.compile_motion("/nowhere", kling_26(), {}, {"video": "v.mp4", "image": "c.png", "quality": "pro"})["mode"] == "1080p"


def test_the_background_can_come_from_the_picture_and_the_prompt_is_never_over_the_limit():
    p = R.compile_motion("/nowhere", kling_v3(), {}, {"video": "v.mp4", "image": "c.png", "background": "image", "note": "é" * 3000})
    assert p["background_source"] == "input_image" and len(p["prompt"].encode("utf-8")) <= 2500


def test_a_model_without_a_picture_and_a_video_input_cannot_be_used_for_motion():
    m = R._finish("kie", "x/y", "Plain", "", [F("prompt", required=True), F("duration", "integer")])
    with pytest.raises(SystemExit) as e:
        R.compile_motion("/nowhere", m, {}, {"video": "v.mp4", "image": "c.png"})
    assert "can't be used for motion control" in str(e.value)


def test_which_models_are_motion_models():
    for slug in ("kling/motion-control-v3", "kling-3.0/motion-control", "kling/motion-control", "wan/2-2-animate-move", "wan/2-2-animate-replace"):
        assert R.is_motion_model(slug) and not R.kie_makes_video(slug), slug
    assert not R.is_motion_model("kling-3.0/video") and R.kie_makes_video("kling-3.0/video")


# ---------------------------------------------------------------- queueing and rendering with a mock provider

class Fake:
    name = "kie"
    sent = []

    def upload(self, path):
        return "https://cdn/" + os.path.basename(path)

    def submit(self, model, payload):
        Fake.sent.append(payload)
        return {"id": "r1"}

    def poll(self, model, rid, meta=None):
        return {"state": "done", "url": "https://cdn/out.mp4"}


@pytest.fixture
def fake(monkeypatch):
    Fake.sent = []
    monkeypatch.setitem(R.PROVIDERS, "kie", Fake)
    monkeypatch.setattr(R, "manifest", lambda provider, model, refresh=False: kling_v3() if "motion" in model else R._finish("kie", model, "V", "", [
        F("prompt", required=True), F("first_frame_url", description="First frame"), F("reference_image_urls", "array", items="string", max_items=9), F("duration", "integer")]))
    monkeypatch.setattr(R, "_review", lambda d, store, j: None)

    class Dl:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_content(self, n): yield b"\0" * 64
    monkeypatch.setattr(R.requests, "get", lambda url, **kw: Dl())
    return Fake


def test_a_motion_take_uploads_the_two_files_and_sends_only_the_motion_request(project, video, fake):
    CO.set_motion(project, "S01-01", {"video_path": video, "quality": "pro", "note": "Keep it elegant."})
    made = CO.queue_motion(project, "S01-01", "kie", "kling/motion-control-v3")
    assert made[0]["motion"]["video"].endswith(".mp4") and made[0]["motion"]["image"] == "media/kf.png" and made[0]["kind"] == "video"
    R.run(project, poll_every=0)
    job = R.Store(project).jobs[0]
    assert job["state"] == "ready", job.get("error")
    sent = fake.sent[0]
    assert sent["video_urls"][0].startswith("https://cdn/") and sent["input_urls"][0].startswith("https://cdn/") and sent["mode"] == "pro" and "Keep it elegant." in sent["prompt"]
    assert not any(k in sent for k in ("first_frame_url", "duration", "reference_image_urls"))


def test_queueing_without_the_pieces_says_what_is_still_needed(project, fake):
    with pytest.raises(SystemExit) as e:
        CO.queue_motion(project, "S01-01", "kie", "kling/motion-control-v3")
    assert "a motion video" in str(e.value)


def test_an_ordinary_model_cannot_be_used_for_a_motion_take_and_a_vanished_file_is_caught(project, video, fake):
    CO.set_motion(project, "S01-01", {"video_path": video})
    with pytest.raises(SystemExit) as e:
        CO.queue_motion(project, "S01-01", "kie", "bytedance/seedance-2")
    assert "isn't a motion-control model" in str(e.value)
    os.remove(os.path.join(project, CO.state(project, "S01-01")["video"]))
    with pytest.raises(SystemExit) as e:
        CO.queue_motion(project, "S01-01", "kie", "kling/motion-control-v3")
    assert "a motion video" in str(e.value)


def test_a_references_only_take_sends_no_start_frame_and_remembers_it(project, fake):
    made = R.enqueue(project, ["S01-01"], "kie", "bytedance/seedance-2", {"_refs_only": True}, [], "video")
    assert made[0]["refs_only"] is True
    R.run(project, poll_every=0)
    job = R.Store(project).jobs[0]
    assert job["state"] == "ready" and "first_frame_url" not in fake.sent[0] and job["keyframe_ref"] is None


def test_an_ordinary_take_still_starts_on_the_keyframe(project, fake):
    R.enqueue(project, ["S01-01"], "kie", "bytedance/seedance-2", {}, [], "video")
    R.run(project, poll_every=0)
    assert fake.sent[0]["first_frame_url"].startswith("https://cdn/") and R.Store(project).jobs[0]["keyframe_ref"] == "project:media/kf.png"


def test_a_direction_note_goes_into_the_prompt_for_that_take_only(project, fake):
    R.enqueue(project, ["S01-01"], "kie", "bytedance/seedance-2", {"_note": "  Hold the look, then turn away.  "}, [], "video")
    R.run(project, poll_every=0)
    assert "Direction for this take: Hold the look, then turn away." in fake.sent[0]["prompt"]
    assert R.Store(project).jobs[0]["note"] == "Hold the look, then turn away."


def test_the_pickers_list_the_right_models_for_each_way(monkeypatch, project):
    cat = {"video": [{"provider": "kie", "model": m, "title": m} for m in ("bytedance/seedance-2", "kling-3.0/video", "happyhorse/reference-to-video", "kling/v3-turbo-image-to-video")],
           "motion": [{"provider": "kie", "model": "kling/motion-control-v3", "title": "Kling 3 motion"}]}
    monkeypatch.setattr(R, "catalog", lambda provider, kind="video", refresh=False: cat[kind])
    m = CO.models(project, "kie")
    assert {x["model"] for x in m["start_end"]} >= {"bytedance/seedance-2", "kling-3.0/video"} and "kling/v3-turbo-image-to-video" not in {x["model"] for x in m["start_end"]}
    assert {x["model"] for x in m["references"]} == {"bytedance/seedance-2", "happyhorse/reference-to-video"}
    assert [x["model"] for x in m["motion"]] == ["kling/motion-control-v3"]


def test_a_shot_id_that_is_not_in_the_plan_cannot_make_files(project, video):
    for bad in ("../../outside", "S09-09"):
        with pytest.raises(SystemExit):
            CO.set_motion(project, bad, {"video_path": video})
    assert not any("motion" in n for n in os.listdir(os.path.join(project, "media")))


# ---------------------------------------------------------------- the motion library (saved on this computer, used in any project)

@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_an_empty_library_lists_nothing(home):
    assert CO.lib_list() == []


def test_a_motion_is_saved_with_a_name_a_length_and_a_small_picture(home, video):
    m = CO.lib_add(video, "  Dance  \n  one  ")
    assert m["name"] == "Dance one" and 5.5 < m["seconds"] < 6.5 and m["thumb"].startswith("data:image/jpeg;base64,") and (m["width"], m["height"]) == (160, 90) and m["already"] is False
    assert [x["id"] for x in CO.lib_list()] == [m["id"]] and os.path.exists(video)                       # the original is never touched
    assert os.path.exists(os.path.join(CO.lib_dir(), m["id"] + ".mp4"))


def test_the_same_video_saved_twice_is_kept_once(home, video, tmp_path):
    a = CO.lib_add(video)
    import shutil
    twin = tmp_path / "copy.mp4"
    shutil.copy(video, twin)
    b = CO.lib_add(str(twin), "another name")
    assert b["id"] == a["id"] and b["already"] is True and len(CO.lib_list()) == 1


def test_only_good_videos_are_saved(home, tmp_path):
    for bad, why in ((clip(tmp_path / "short.mp4", 2), "3 to 30 seconds"), (str(tmp_path / "gone.mp4"), "can't be found")):
        with pytest.raises(SystemExit) as e:
            CO.lib_add(bad)
        assert why in str(e.value)
    assert CO.lib_list() == []


def test_a_motion_is_renamed_and_removed(home, video):
    m = CO.lib_add(video)
    assert CO.lib_rename(m["id"], "Slow walk\x00\x07")[0]["name"] == "Slow walk"
    assert CO.lib_rename(m["id"], "   ")[0]["name"] == "Slow walk"                 # a blank name keeps the old one
    assert CO.lib_remove(m["id"]) == []
    assert not [f for f in os.listdir(CO.lib_dir()) if f not in ("index.json", ".trash")]       # gone from the library (kept in the trash so Remove can be undone)
    with pytest.raises(SystemExit) as e:
        CO.lib_remove(m["id"])
    assert "isn't in the library" in str(e.value)


def test_a_missing_file_drops_its_entry_instead_of_breaking_the_list(home, video):
    a, b = CO.lib_add(video), CO.lib_add(clip(os.path.join(os.path.dirname(video), "other.mp4"), 7))
    os.remove(os.path.join(CO.lib_dir(), a["id"] + ".mp4"))
    assert [x["id"] for x in CO.lib_list()] == [b["id"]]


def test_a_saved_motion_is_copied_into_the_shot_when_used(home, project, video):
    m = CO.lib_add(video)
    s = CO.lib_use(project, "S01-01", m["id"])
    assert s["video"].startswith("media/S01-01_motion_") and os.path.exists(os.path.join(project, s["video"])) and 5.5 < s["video_seconds"] < 6.5
    assert os.path.exists(os.path.join(CO.lib_dir(), m["id"] + ".mp4"))                        # still in the library for the next shot


def test_the_shots_own_motion_can_be_saved_to_the_library(home, project, video):
    with pytest.raises(SystemExit) as e:
        CO.lib_add_from_shot(project, "S01-01")
    assert "no motion video" in str(e.value)
    CO.set_motion(project, "S01-01", {"video_path": video})
    m = CO.lib_add_from_shot(project, "S01-01")
    assert m["name"] == "S01-01 motion" and len(CO.lib_list()) == 1


def test_ids_from_outside_cannot_reach_other_files(home, video, project):
    CO.lib_add(video)
    for bad in ("../index", "..\\..\\x", "abcdefghij", ""):
        for fn in (lambda b: CO.lib_remove(b), lambda b: CO.lib_use(project, "S01-01", b), lambda b: CO.lib_rename(b, "x")):
            with pytest.raises(SystemExit):
                fn(bad)
    assert len(CO.lib_list()) == 1


def test_a_damaged_index_is_ignored(home, video):
    os.makedirs(CO.lib_dir())
    open(os.path.join(CO.lib_dir(), "index.json"), "w").write("{not json")
    assert CO.lib_list() == []
    assert CO.lib_add(video)["already"] is False
