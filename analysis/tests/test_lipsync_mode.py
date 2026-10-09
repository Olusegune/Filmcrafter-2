"""Mouths that follow the music. On the Seedance 2 family a first frame and reference audio cannot be sent together, so with a keyframe as the first frame the song was never sent and the
mouth could only follow the words in the prompt. The project can now choose 'follow the song's audio': the keyframe goes as a reference picture, the isolated vocal is sent, and the
mouth follows the music. Also: when audio is sent it is the clean vocal, not the whole mix. Checked on requests, not on a real render: whether a model keeps its promise is learned from one."""
import json
import os

import pytest

from pulseframe_analysis import render as R
from tests.test_video_models import f, kie, musical

SEEDANCE = "bytedance/seedance-2-fast"
PLAN = {"meta": {}}
KF = "project:assets/kf.png"


def seedance():
    return kie(SEEDANCE, f("prompt", required=True, max_length=20000), f("first_frame_url"), f("reference_image_urls", "array", items="string", max_items=9),
               f("reference_audio_urls", "array", items="string", max_items=3), f("duration", "integer", minimum=4, maximum=15, required=True), f("generate_audio", "boolean"))


def project(tmp_path, **extra):
    return musical(tmp_path, ["Queen Bee calls down from the staircase."], [{"text": "Children!", "start": 4.5, "end": 5.1}], extra)


# ---------------------------------------------------------------- who the mode applies to

def test_the_default_still_describes_the_words_when_the_keyframe_is_the_first_frame(tmp_path):
    d, shot = project(tmp_path)
    sung, said = R._voice(d, shot, PLAN, seedance(), None, True)
    assert sung is None and said and said["lyrics"] == ["Children!"]                      # as before: the words, not the music


def test_in_audio_first_mode_the_song_is_sent_even_with_a_keyframe(tmp_path, monkeypatch):
    d, shot = project(tmp_path, lip_sync_mode="audio_first")
    sentinel = {"performer": "Beatrice", "lyrics": ["Children!"], "url": "(upload) a.mp3"}
    monkeypatch.setattr(R, "_sung_for", lambda *a, **k: sentinel)
    sung, said = R._voice(d, shot, PLAN, seedance(), None, True)
    assert sung is sentinel and said is None


@pytest.mark.parametrize("why,project_extra,model", [
    ("lip-sync is off", {"lip_sync": "off"}, "seedance"),
    ("the model cannot follow audio", {}, "silent"),
    ("the model accepts a first frame and audio together", {}, "both"),
])
def test_the_mode_does_not_apply_where_it_makes_no_sense(tmp_path, why, project_extra, model):
    d, shot = project(tmp_path, lip_sync_mode="audio_first", **project_extra)
    man = {"seedance": seedance(),
           "silent": kie(SEEDANCE, f("prompt", required=True), f("first_frame_url"), f("duration", "integer")),
           "both": kie("some/other-model", f("prompt", required=True), f("first_frame_url"), f("reference_audio_urls", "array", items="string"), f("duration", "integer"))}[model]
    assert R.audio_first(d, json.load(open(os.path.join(d, "project.json"))), shot, PLAN, man) is False, why


def test_the_mode_needs_a_sung_line_under_the_shot(tmp_path):
    d, shot = musical(tmp_path, ["Queen Bee watches."], [{"text": "Later", "start": 12.0, "end": 13.0}], {"lip_sync_mode": "audio_first"})
    assert R.audio_first(d, json.load(open(os.path.join(d, "project.json"))), shot, PLAN, seedance()) is False


def test_the_mode_applies_to_a_sung_shot_on_a_model_that_cannot_take_both(tmp_path):
    d, shot = project(tmp_path, lip_sync_mode="audio_first")
    assert R.audio_first(d, json.load(open(os.path.join(d, "project.json"))), shot, PLAN, seedance()) is True
    (tmp_path / "other").mkdir()
    d2, shot2 = project(tmp_path / "other")
    assert R.audio_first(d2, json.load(open(os.path.join(d2, "project.json"))), shot2, PLAN, seedance()) is False            # not chosen


# ---------------------------------------------------------------- what is sent

def test_the_keyframe_is_a_reference_picture_in_this_mode_and_the_first_frame_otherwise():
    as_first = R._with_keyframe([], KF)
    as_ref = R._with_keyframe([], KF, first=False)
    assert as_first[0]["keyframe"] is True and "start from this frame" in as_first[0]["label"]
    assert "keyframe" not in as_ref[0] and as_ref[0]["media"] == "image" and "open the shot like this frame" in as_ref[0]["label"]
    assert R._with_keyframe([], None, first=False) == []


def request(first):
    shot = {"id": "S01-01", "start": 4.5, "end": 5.7, "beats": ["She calls."], "performers": ["Beatrice"]}
    refs = R._with_keyframe([{"label": "reference for Beatrice", "url": "https://x/beatrice.png", "media": "image"}], "https://x/kf.png", first=first)
    sung = {"performer": "Beatrice", "lyrics": ["Children!"], "url": "https://x/vocal.mp3"}
    m = seedance()
    p = R.compile_request(shot, None, PLAN, {"look": {"style": "auto"}}, m, refs, sung=sung if not first else None)
    return R.exclusive_inputs("kie", SEEDANCE, R.fill_required(m, p, refs), m)


def test_with_the_keyframe_as_first_frame_no_audio_goes_out():
    p = request(first=True)
    assert p.get("first_frame_url") == "https://x/kf.png" and "reference_audio_urls" not in p and "reference_image_urls" not in p


def test_in_audio_first_mode_the_audio_and_the_keyframe_as_a_reference_go_out_with_no_first_frame():
    p = request(first=False)
    assert "first_frame_url" not in p
    assert p["reference_audio_urls"] == ["https://x/vocal.mp3"]
    assert p["reference_image_urls"][0] == "https://x/kf.png" and "https://x/beatrice.png" in p["reference_image_urls"]      # the keyframe comes first among the references
    assert "reference audio" in p["prompt"] and "the first reference image is the approved keyframe for this shot" in p["prompt"]


# ---------------------------------------------------------------- the vocal, not the mix

def test_the_audio_sent_is_the_isolated_vocal_unless_the_project_asks_for_the_mix(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(R, "song_slice", lambda d, shot, seconds, vocals_only=False: (seen.append(vocals_only), os.path.join(d, "clip.mp3"))[1])
    for extra, want in (({}, True), ({"lip_sync_audio": "vocals"}, True), ({"lip_sync_audio": "mix"}, False)):
        (tmp_path / str(len(seen))).mkdir()
        d, shot = project(tmp_path / str(len(seen)), **extra)
        sung = R._sung_for(d, shot, PLAN, seedance(), None)
        assert sung and sung["url"].endswith("clip.mp3") and seen[-1] is want, extra


def test_without_a_separated_vocal_the_slice_is_the_whole_song(tmp_path):
    d, shot = project(tmp_path)
    assert R._vocal_stem(d) is None
    import wave
    with wave.open(os.path.join(d, "song.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\0\0" * 22050 * 8)
    p = R.song_slice(d, shot, 1.2, vocals_only=True)
    assert os.path.exists(p) and p.endswith("_mix.mp3")                                    # nothing to isolate: the song itself, so it still works


# ---------------------------------------------------------------- what the screen is told

def preview(tmp_path, monkeypatch, **extra):
    d = tmp_path / "pv"
    d.mkdir(exist_ok=True)
    shot = {"id": "S01-01", "scene": 1, "number": 1, "start": 4.5, "end": 5.7, "beats": ["Queen Bee calls down."], "performers": ["Beatrice"], "description": "Queen Bee calls down."}
    json.dump({"meta": {}, "characters": [], "scenes": [{"number": 1, "heading": "INT.", "shots": [shot]}]}, open(d / "production.json", "w"))
    json.dump({"title": "T", "song": "song.wav", "look": {"style": "auto"}, **extra}, open(d / "project.json", "w"))
    json.dump({"duration": 20, "lyrics": [{"text": "Children!", "start": 4.5, "end": 5.1}], "sections": []}, open(d / "songmap.json", "w"))
    json.dump({"production": {"S01-01": KF}}, open(d / "keyframes.json", "w"))
    os.makedirs(d / "assets", exist_ok=True)
    (d / "assets" / "kf.png").write_bytes(b"png")                                              # an approved keyframe is only one if its file exists
    monkeypatch.setattr(R, "manifest", lambda p, m: seedance())
    monkeypatch.setattr(R, "_reference_files", lambda *a, **k: [])
    monkeypatch.setattr(R, "song_slice", lambda *a, **k: str(d / "clip.mp3"))
    return R.preview(str(d), "S01-01", "kie", SEEDANCE, None)


def test_the_preview_says_when_the_keyframe_is_why_the_music_is_not_followed(tmp_path, monkeypatch):
    out = preview(tmp_path, monkeypatch)
    assert out["keyframe_blocks_audio"] is True and out["lip_sync"] is False and out["audio_first"] is False
    assert out["payload"].get("first_frame_url")


def test_the_preview_in_audio_first_mode_sends_the_song_and_no_first_frame(tmp_path, monkeypatch):
    out = preview(tmp_path, monkeypatch, lip_sync_mode="audio_first")
    assert out["audio_first"] is True and out["lip_sync"] is True and out["keyframe_blocks_audio"] is False
    assert not out["payload"].get("first_frame_url") and out["payload"].get("reference_audio_urls")


def test_the_preview_of_a_project_with_lip_sync_off_does_not_nag(tmp_path, monkeypatch):
    out = preview(tmp_path, monkeypatch, lip_sync="off")
    assert out["keyframe_blocks_audio"] is False and out["lip_sync"] is False


# ---------------------------------------------------------------- auto: only where a mouth is watched

def auto(tmp_path, framing, lines=None, mode="auto", **extra):
    lines = lines or [{"text": "Children, come downstairs", "start": 4.4, "end": 5.8}]
    d, shot = musical(tmp_path, ["Queen Bee calls down from the staircase."], lines, {"lip_sync_mode": mode, **extra})
    shot["framing"] = framing
    return d, shot, json.load(open(os.path.join(d, "project.json")))


@pytest.mark.parametrize("framing,expected", [("close-up", True), ("medium close-up", True), ("medium shot", True), ("wide shot", False), ("establishing wide", False), ("over the shoulder of Emmanuel", False), ("", False)])
def test_auto_follows_the_audio_only_where_a_mouth_is_shown(tmp_path, framing, expected):
    d, shot, project_ = auto(tmp_path, framing)
    assert R.audio_first(d, project_, shot, PLAN, seedance()) is expected


def test_auto_needs_a_second_of_vocal_under_the_shot(tmp_path):
    d, shot, project_ = auto(tmp_path, "close-up", [{"text": "Hey", "start": 4.5, "end": 5.0}])
    shot["performance"] = "She sings."
    assert R.audio_first(d, project_, shot, PLAN, seedance()) is False


def test_auto_is_off_when_lip_sync_is_off_or_the_model_takes_both(tmp_path):
    d, shot, project_ = auto(tmp_path, "close-up", lip_sync="off")
    assert R.audio_first(d, project_, shot, PLAN, seedance()) is False
    (tmp_path / "x").mkdir()
    d, shot, project_ = auto(tmp_path / "x", "close-up")
    both = kie("some/other-model", f("prompt", required=True), f("first_frame_url"), f("reference_audio_urls", "array", items="string"), f("duration", "integer"))
    assert R.audio_first(d, project_, shot, PLAN, both) is False


def test_the_explicit_modes_are_unchanged_by_auto(tmp_path):
    d, shot, project_ = auto(tmp_path, "wide shot", mode="audio_first")
    assert R.audio_first(d, project_, shot, PLAN, seedance()) is True                       # "always" still means every sung shot
    (tmp_path / "y").mkdir()
    d, shot, project_ = auto(tmp_path / "y", "close-up", mode="first_frame")
    assert R.audio_first(d, project_, shot, PLAN, seedance()) is False


def test_new_projects_start_in_auto_and_the_setting_accepts_it():
    lib = open(os.path.join(os.path.dirname(__file__), "..", "..", "src-tauri", "src", "lib.rs"), encoding="utf-8").read()
    assert '"lip_sync_mode": "auto"' in lib                                                    # a new project's default
    assert '"auto" => "auto"' in lib                                                           # and the settings command keeps it


# ---------------------------------------------------------------- what the model is given, as pictures

def test_the_preview_lists_what_the_model_is_given_with_the_keyframe_as_the_first_frame(tmp_path, monkeypatch):
    out = preview(tmp_path, monkeypatch)
    ins = out["inputs"]
    assert ins[0]["role"] == "first_frame" and ins[0]["sent"] is True and ins[0]["path"] == "assets/kf.png"
    assert "Starts from this frame" in ins[0]["label"]
    assert not any(i["role"] == "audio" for i in ins)                                          # the song is not sent in this mode


def test_in_audio_first_mode_the_keyframe_is_a_reference_picture_and_the_vocal_is_listed(tmp_path, monkeypatch):
    out = preview(tmp_path, monkeypatch, lip_sync_mode="audio_first")
    ins = out["inputs"]
    assert [i["role"] for i in ins] == ["reference", "audio"]
    assert ins[0]["sent"] is True and "approved keyframe" in ins[0]["label"] and ins[0]["path"] == "assets/kf.png"
    assert "vocal" in ins[1]["label"] and "Beatrice" in ins[1]["label"]


def test_a_reference_picture_the_model_will_not_take_beside_a_first_frame_is_listed_as_not_sent():
    man = seedance()
    refs = [{"label": "approved keyframe for this exact shot: start from this frame", "url": KF, "keyframe": True},
            {"label": "reference for Beatrice (face, expressions, full-body turnaround)", "url": "(upload) b.png", "media": "image", "path": "assets/b.png"}]
    payload = {"prompt": "x", "first_frame_url": KF}                                           # the Seedance 2 family drops the reference pictures beside a first frame
    ins = R.model_inputs(refs, payload, man, None)
    assert [(i["role"], i["sent"]) for i in ins] == [("first_frame", True), ("reference", False)]
    assert ins[1]["label"] == "reference for Beatrice"
    payload = {"prompt": "x", "reference_image_urls": ["(upload) b.png"]}
    assert [(i["role"], i["sent"]) for i in R.model_inputs(refs[1:], payload, man, None)] == [("reference", True)]


def test_a_model_that_takes_only_so_many_pictures_shows_the_rest_as_not_sent():
    man = seedance()
    refs = [{"label": f"reference for P{i}", "url": f"(upload) p{i}.png", "media": "image", "path": f"assets/p{i}.png"} for i in range(3)]
    ins = R.model_inputs(refs, {"prompt": "x", "reference_image_urls": ["a", "b"]}, man, None)
    assert [i["sent"] for i in ins] == [True, True, False]


def test_audio_and_video_references_are_not_pictures_and_an_empty_request_lists_nothing():
    man = seedance()
    refs = [{"label": "a clip", "url": "(upload) c.mp4", "media": "video", "path": "assets/c.mp4"}]
    assert R.model_inputs(refs, {"prompt": "x"}, man, None) == []
    assert R.model_inputs([], {}, man, {"performer": "Beatrice"}) == []
