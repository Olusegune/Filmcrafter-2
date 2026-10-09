"""Video models that failed on real renders (Kie): a field name with a stray space, limits only written in words, frame fields given a character sheet."""
import pytest

from filmcrafter_engine import model_audit as A, render as R


def f(name, type="string", **kw):
    return {"name": name, "type": type, "items": kw.get("items"), "enum": kw.get("enum"), "default": kw.get("default"), "minimum": kw.get("minimum"),
            "maximum": kw.get("maximum"), "max_items": kw.get("max_items"), "max_length": kw.get("max_length"), "description": kw.get("description", ""),
            "required": kw.get("required", False)}


def kie(model, *fields):
    return R._finish("kie", model, "Test", "image-to-video", list(fields))


SHEETY = [{"label": "approved keyframe", "url": "https://x/keyframe.png", "keyframe": True}, {"label": "cast sheet", "url": "https://x/char_sheet.png"}]
SHOT = {"id": "S01-01", "start": 0, "end": 3, "beats": ["She rings the bell."], "performers": ["Beatrice"]}


def build(m, refs):
    p = R.compile_request(SHOT, None, {"meta": {}}, {"look": {"style": "auto"}}, m, refs)
    return R.exclusive_inputs(m["provider"], m["model"], R.fill_required(m, p, refs))


def test_a_field_name_with_a_stray_space_is_read_and_sent_without_it():
    m = kie("happyhorse/image-to-video", f("prompt", required=True, max_length=5000), f("image_urls ", "array", items="string", max_items=1, required=True,
            description="First-frame image URL list. Exactly one image is required."), f("duration", "integer", minimum=3, maximum=15))
    assert m["roles"]["ref_images"] == "image_urls" and "image_urls " not in [i["name"] for i in m["inputs"]]
    p = build(m, SHEETY)
    assert p["image_urls"] == ["https://x/keyframe.png"] and "image_urls " not in p
    assert R.validate_request(m, p) == []


def test_limits_written_only_in_the_description_are_honoured():
    m = kie("grok-imagine/image-to-video", f("prompt", description="Optional.\n- Maximum length: 5000 characters\n- English"),
            f("duration", "string", description="The duration (in seconds) (6-30). (Minimum: 6, Maximum: 30, Step: 1)"), f("image_urls", "array", items="string", max_items=7))
    prompt = next(i for i in m["inputs"] if i["name"] == "prompt")
    dur = next(i for i in m["inputs"] if i["name"] == "duration")
    assert prompt["max_length"] == 5000 and (dur["minimum"], dur["maximum"]) == (6, 30)
    shot = dict(SHOT, beats=["A very long beat. " * 400])
    p = R.compile_request(shot, None, {"meta": {}}, {"look": {"style": "auto"}}, m, SHEETY)
    assert len(p["prompt"].encode()) <= 5000
    assert int(p["duration"]) >= 6                                         # a 3-second shot is asked for at least the model's 6


def test_seedance_15_gets_only_the_keyframe_and_an_end_frame_never_a_character_sheet():
    m = kie("bytedance/seedance-1.5-pro", f("prompt", required=True, max_length=20000), f("input_urls", "array", items="string", max_items=2, description="Accepts 0-2 images"),
            f("aspect_ratio", enum=["16:9", "9:16"], required=True), f("duration", "number", required=True, minimum=4, maximum=12))
    assert R.frames_only(m)
    assert build(m, SHEETY)["input_urls"] == ["https://x/keyframe.png"]
    both = build(m, SHEETY + [{"label": "end frame", "url": "https://x/end.png", "endframe": True}])
    assert both["input_urls"] == ["https://x/keyframe.png", "https://x/end.png"]
    no_kf = build(m, [{"label": "cast sheet", "url": "https://x/char_sheet.png"}])
    assert "input_urls" not in no_kf                                       # no keyframe and nothing required: text-to-video, not a video of a sheet


def test_a_model_that_says_first_frame_is_treated_as_frames_even_if_unlisted():
    m = kie("some/new-model", f("prompt", required=True), f("image_urls", "array", items="string", max_items=1, description="First-frame image."), f("duration", "integer"))
    assert R.frames_only(m)
    assert build(m, SHEETY)["image_urls"] == ["https://x/keyframe.png"]
    refs_model = kie("some/ref-model", f("prompt", required=True), f("image_urls", "array", items="string", max_items=4, description="Reference images."), f("duration", "integer"))
    assert not R.frames_only(refs_model)
    assert len(build(refs_model, SHEETY)["image_urls"]) == 2               # a real reference model still gets the cast sheet


def test_a_model_that_must_have_a_first_frame_still_gets_one():
    m = kie("some/needs-image", f("prompt", required=True), f("image_urls", "array", items="string", max_items=1, required=True, description="First-frame image."), f("duration", "integer"))
    assert build(m, [{"label": "cast sheet", "url": "https://x/char_sheet.png"}])["image_urls"] == ["https://x/char_sheet.png"]


def test_kie_refusing_a_request_is_reported_as_nothing_charged(monkeypatch):
    class Resp:
        status_code = 200
        def json(self): return {"code": 422, "msg": "image_urls is required"}
    monkeypatch.setenv("KIE_KEY", "k")
    monkeypatch.setattr(R.requests, "post", lambda *a, **k: Resp())
    with pytest.raises(R.RequestProblem, match="nothing was charged.*image_urls is required"):
        R.Kie().submit("x/y", {"prompt": "p"})


def test_the_audit_flags_a_sheet_in_a_frame_field_and_passes_a_good_model():
    good = kie("bytedance/seedance-1.5-pro", f("prompt", required=True, max_length=20000), f("input_urls", "array", items="string", max_items=2),
               f("aspect_ratio", enum=["16:9", "9:16"], required=True), f("duration", "number", required=True, minimum=4, maximum=12))
    assert A.audit_one(good) == [] and A.audit_one(good, with_end=True) == []
    bad = R._finish("kie", "x/y", "t", "image-to-video", [f("prompt", required=True, max_length=10), f("image_urls", "array", items="string", max_items=1, description="First-frame image."),
                                                           f("duration", "integer")])
    assert not [p for p in A.audit_one(bad) if "first/last frame" in p]    # frames-only handling keeps sheets out
    assert A.audit_one(bad) == [] or all("prompt" in p for p in A.audit_one(bad))


def test_multi_reference_models_keep_their_references_and_single_picture_models_get_the_keyframe():
    wan3 = kie("wan/3-0-video", f("prompt", required=True), f("image_urls", "array", items="string", max_items=10,
               description="Reference images for the all-purpose reference mode, with up to 10 images. Correspond to Image1... If you want a first frame, use first_frame instead."),
               f("duration", "integer"))
    assert not R.frames_only(wan3) and len(build(wan3, SHEETY)["image_urls"]) == 2
    kling = kie("kling-2.6/image-to-video", f("prompt", required=True), f("image_urls", "array", items="string", max_items=1, required=True,
                description="Image URLs for video generation."), f("duration", "integer"))
    assert R.frames_only(kling) and build(kling, SHEETY)["image_urls"] == ["https://x/keyframe.png"]


def test_tools_that_are_not_video_generators_stay_out_of_the_video_picker():
    gone = ["grok-imagine/upscale", "grok-imagine/extend", "kling/motion-control", "kling/ai-avatar-pro", "wan/2-7-videoedit", "happyhorse/video-edit", "wan/2-6-video-to-video",
            "omnihuman-1-5/human-identification", "omnihuman-1-5/subject-detection", "topaz/video-upscale", "pixverse/extend", "infinitalk/from-audio", "wan/2-2-animate-move",
            "kling/v3-omni-transformation", "gemini-omni-audio", "pixverse/transition", "volcengine/video-to-video-lip-sync"]
    kept = ["bytedance/seedance-1-5-pro", "kling/v3-turbo-image-to-video", "happyhorse/image-to-video", "grok-imagine/image-to-video", "wan/2-6-image-to-video", "hailuo/02-image-to-video-standard",
            "kling/v3-omni-reference-to-video", "omnihuman-1-5", "wan/2-2-a14b-speech-to-video-turbo", "bytedance/seedance-2"]
    assert not [m for m in gone if R.kie_makes_video(m)]
    assert all(R.kie_makes_video(m) for m in kept)


def seedance2(model):
    return kie(model, f("prompt", required=True), f("first_frame_url", description="First frame image url. Cannot be used simultaneously with reference_image_urls, reference_video_urls, or reference_audio_urls."),
               f("last_frame_url"), f("reference_image_urls", "array", items="string", max_items=9), f("reference_video_urls", "array", items="string", max_items=3),
               f("reference_audio_urls", "array", items="string", max_items=3), f("duration", "integer", minimum=4, maximum=15), f("generate_audio", "boolean"))


@pytest.mark.parametrize("model", ["bytedance/seedance-2", "bytedance/seedance-2-fast", "bytedance/seedance-2-mini", "bytedance/seedance-2-5"])
def test_the_whole_seedance_2_family_sends_the_first_frame_or_the_references_never_both(model):
    m = seedance2(model)
    refs = SHEETY + [{"label": "end frame", "url": "https://x/end.png", "endframe": True}]
    p = build(m, refs)
    assert p["first_frame_url"] == "https://x/keyframe.png"
    assert not any(k in p for k in ("reference_image_urls", "reference_video_urls", "reference_audio_urls"))
    assert p["last_frame_url"] == "https://x/end.png"                      # the model's own two-frame mode: both frames go, the references do not
    assert A.audit_one(m) == [] and A.audit_one(m, True) == []


def test_a_model_not_on_the_list_is_still_caught_when_its_docs_say_the_first_frame_excludes_references():
    m = seedance2("new/family-model")
    p = {"prompt": "x", "first_frame_url": "k.png", "reference_image_urls": ["a.png"], "reference_audio_urls": ["s.mp3"], "last_frame_url": "e.png"}
    out = R.exclusive_inputs("kie", "new/family-model", dict(p), m)
    assert out == {"prompt": "x", "first_frame_url": "k.png", "last_frame_url": "e.png"}       # references go; an end frame is left to the model
    assert R.exclusive_inputs("kie", "new/family-model", {"prompt": "x", "reference_image_urls": ["a.png"]}, m) == {"prompt": "x", "reference_image_urls": ["a.png"]}


# ---------------------------------------------------------------- prices
@pytest.mark.parametrize("unit,expected", [("1m tokens", 1_000_000), ("1M_tokens", 1_000_000), ("million tokens", 1_000_000), ("1k tokens", 1_000), ("1000 tokens", 1_000),
                                           ("1,000 tokens", 1_000), ("token", 1), ("tokens", 1), ("seconds", None), ("", None)])
def test_token_units_are_read_as_what_they_are(unit, expected):
    assert R.token_unit(unit) == expected


def test_a_per_million_token_price_is_cents_per_shot_not_thousands_of_dollars(monkeypatch):
    """fal's Seedance 1.5 Pro showed $103,680 for a 4-second shot: 86,400 tokens priced as if each token cost the per-million price."""
    m = R._finish("fal", "fal-ai/bytedance/seedance/v1.5/pro/image-to-video", "t", "image-to-video",
                  [f("prompt", required=True), f("duration", "integer"), f("resolution", enum=["720p", "1080p"]), f("aspect_ratio", enum=["16:9"])])
    monkeypatch.setattr(R, "_fal_price", lambda model: {"unit": "1m tokens", "unit_price": 1.2})
    e = R.estimate_payload("fal", m["model"], m, {"duration": 4, "resolution": "720p", "aspect_ratio": "16:9"})
    assert 0.05 < e["usd"] < 0.2, e
    monkeypatch.setattr(R, "_fal_price", lambda model: {"unit": "weird unit", "unit_price": 9999.0})
    assert R.estimate_payload("fal", m["model"], m, {"duration": 4})["usd"] is None             # an unknown unit is not guessed
    monkeypatch.setattr(R, "_fal_price", lambda model: {"unit": "second", "unit_price": 500.0})
    e = R.estimate_payload("fal", m["model"], m, {"duration": 4})
    assert e["usd"] is None and "could not be worked out" in e["basis"]                           # an absurd total is never shown


# ---------------------------------------------------------------- what a character says or sings
import json
import os


def musical(tmp_path, beats, lyrics, project=None):
    d = tmp_path / "p"
    d.mkdir(exist_ok=True)
    json.dump({"title": "T", "song": "song.wav", **(project or {})}, open(d / "project.json", "w"))
    json.dump({"duration": 20, "lyrics": lyrics, "sections": []}, open(d / "songmap.json", "w"))
    shot = {"id": "S01-01", "start": 4.5, "end": 5.7, "beats": beats, "performers": ["Beatrice"], "performance": "She holds the stair."}
    return str(d), shot


SILENT = lambda: kie("bytedance/seedance-1.5-pro", f("prompt", required=True, max_length=20000), f("input_urls", "array", items="string", max_items=2),
                     f("aspect_ratio", enum=["16:9"], required=True), f("duration", "number", required=True, minimum=4, maximum=12), f("generate_audio", "boolean"))


def test_a_line_the_character_calls_is_in_the_prompt_even_when_the_model_cannot_take_the_voice(tmp_path):
    d, shot = musical(tmp_path, ["Queen Bee calls down from the staircase."], [{"text": "Children!", "start": 4.5, "end": 5.1}, {"text": "Come downstairs!", "start": 5.5, "end": 7.8}])
    m = SILENT()
    said = R._said_for(d, shot, {"meta": {}}, m)
    assert said and said["performer"] == "Beatrice" and said["lyrics"] == ["Children!"]            # the next line only just starts as this shot ends
    p = R.compile_request(shot, None, {"meta": {}}, {"look": {"style": "auto"}}, m, SHEETY, said=said)["prompt"]
    assert "Beatrice voices these words" in p and "Children!" in p and "lips and jaw shape each word" in p
    assert "Other performers do not lip-sync" in p and "Performers do not lip-sync." not in p.replace("Other performers do not lip-sync.", "")
    assert "has no sound" in p                                                                     # the voice is the song laid over it later
    bare = R.compile_request(shot, None, {"meta": {}}, {"look": {"style": "auto"}}, m, SHEETY)["prompt"]
    assert "Children!" not in bare and "Performers do not lip-sync." in bare                        # how it was before


def test_no_line_is_added_when_nothing_is_voiced_or_the_model_takes_the_recorded_voice(tmp_path, monkeypatch):
    d, shot = musical(tmp_path, ["Queen Bee watches the room in silence."], [{"text": "Children!", "start": 4.5, "end": 5.1}])
    assert R._said_for(d, shot, {"meta": {}}, SILENT()) is None                                    # nobody is shown voicing it
    d, shot = musical(tmp_path, ["Queen Bee calls down."], [{"text": "Children!", "start": 4.5, "end": 5.1}])
    with_audio = kie("some/audio-model", f("prompt", required=True), f("reference_audio_urls", "array", items="string", max_items=3), f("duration", "integer"))
    sentinel = {"performer": "Beatrice", "lyrics": ["Children!"], "url": "https://x/a.mp3"}
    monkeypatch.setattr(R, "_sung_for", lambda *a, **k: sentinel)                                     # the song clip itself needs a real song file; not under test
    sung, said = R._voice(d, shot, {"meta": {}}, with_audio, None, True)
    assert sung is sentinel and said is None                                                       # that model is sent the vocal instead of a description
    d, shot = musical(tmp_path, ["Queen Bee calls down."], [{"text": "Children!", "start": 4.5, "end": 5.1}], {"lip_sync": "off"})
    assert R._said_for(d, shot, {"meta": {}}, SILENT()) is None                                    # the project turned lip sync off
    d, shot = musical(tmp_path, ["Queen Bee calls down."], [{"text": "Later words", "start": 12.0, "end": 13.0}])
    assert R._said_for(d, shot, {"meta": {}}, SILENT()) is None                                    # a lyric that is not under this shot


def test_a_named_speaker_is_spoken_and_calls_and_shouts_count_as_voicing(tmp_path):
    d, shot = musical(tmp_path, ["Queen Bee shouts for the children."], [{"text": "Children!", "start": 4.5, "end": 5.1, "performer": "Beatrice"}])
    said = R._said_for(d, shot, {"meta": {}}, SILENT())
    assert said["spoken"] is True
    p = R.compile_request(shot, None, {"meta": {}}, {"look": {"style": "auto"}}, SILENT(), SHEETY, said=said)["prompt"]
    assert "Beatrice speaks these words" in p


def test_the_bible_reaches_the_prompt_as_plain_visual_rules():
    flat = ("# I Am Your Mother — Production Bible A warm stylized 3D Afrobeat family satire. Never bake readable text into generated shots. "
            "## Text to add in editing FAMILY GOVERNMENT; FAMILY CONSTITUTION; DEBT. Phone messages are optional editing inserts. Existing SVGs are human editing resources. .")
    out = R.bible_text(flat)
    assert out.startswith("A warm stylized 3D Afrobeat family satire") and "FAMILY GOVERNMENT" not in out and "SVG" not in out and "#" not in out and "Production Bible" not in out
    assert R.bible_text("Plain text with a SVG logo file. Keep the room the same.") == "Keep the room the same"
    assert R.bible_text("") == "" and R.bible_text(None) == ""
    m = SILENT()
    shot = {"id": "S01-01", "start": 0, "end": 3, "beats": ["She rings the bell."], "performers": ["Beatrice"]}
    p = R.compile_request(shot, None, {"meta": {}}, {"look": {"style": "auto"}, "bible": {"world": flat}}, m, SHEETY)["prompt"]
    assert "World: A warm stylized 3D Afrobeat family satire" in p and "FAMILY CONSTITUTION" not in p and "##" not in p


def test_a_line_that_barely_touches_a_shot_belongs_to_the_next_one(tmp_path):
    d, shot = musical(tmp_path, ["Queen Bee calls down."], [{"text": "Children!", "start": 4.5, "end": 5.1}, {"text": "Come downstairs!", "start": 5.5, "end": 7.8}])
    assert R.singing(d, shot, {"meta": {}})["lyrics"] == ["Children!"]                               # 0.16 s of a 2.3 s line is not this shot's
    long = {"text": "A very long held line", "start": 3.0, "end": 9.0}
    d, shot = musical(tmp_path, ["Queen Bee sings."], [long])
    assert R.singing(d, shot, {"meta": {}})["lyrics"] == ["A very long held line"]                   # a line held across several shots is in each of them
    assert R._belongs({"start": 5.5, "end": 7.8}, {"start": 4.5, "end": 5.7}) is False
    assert R._belongs({"start": 5.2, "end": 5.4}, {"start": 4.5, "end": 5.7}) is True               # a short line fully inside it
    assert R._belongs({"start": 5.5, "end": 5.9}, {"start": 4.5, "end": 5.7}) is True               # half of a short line is heard: still this shot's


def test_the_recorded_voice_wording_says_speaks_for_a_call_and_sings_for_a_song(tmp_path):
    with_audio = kie("bytedance/seedance-2", f("prompt", required=True), f("reference_audio_urls", "array", items="string", max_items=3), f("duration", "integer"))
    sung = {"performer": "Beatrice", "lyrics": ["Children!"], "url": "https://x/a.mp3"}
    called = dict(SHOT, beats=["Queen Bee calls down."], performers=["Beatrice"])
    sings = dict(SHOT, beats=["Queen Bee sings the chorus."], performers=["Beatrice"])
    p1 = R.compile_request(called, None, {"meta": {}}, {"look": {"style": "auto"}}, with_audio, SHEETY, sung=sung)["prompt"]
    p2 = R.compile_request(sings, None, {"meta": {}}, {"look": {"style": "auto"}}, with_audio, SHEETY, sung=sung)["prompt"]
    assert "Beatrice speaks along to" in p1 and "sings along" not in p1
    assert "Beatrice sings along to" in p2


def test_bible_lists_keep_their_own_punctuation():
    out = R.bible_text("Queen leads gesture-driven dance; the Aunties support her. Palette: emerald for Queen; cream/brown Solomon; blue/navy Emmanuel.")
    assert ";." not in out and "; the Aunties" in out and "emerald for Queen; cream/brown Solomon; blue/navy Emmanuel" in out


def test_a_model_that_cannot_take_voice_beside_a_first_frame_is_described_not_pointed_at_missing_audio(tmp_path, monkeypatch):
    d, shot = musical(tmp_path, ["Queen Bee calls down."], [{"text": "Children!", "start": 4.5, "end": 5.1}])
    sentinel = {"performer": "Beatrice", "lyrics": ["Children!"], "url": "https://x/a.mp3"}
    monkeypatch.setattr(R, "_sung_for", lambda *a, **k: sentinel)
    family = seedance2("bytedance/seedance-2-mini")
    sung, said = R._voice(d, shot, {"meta": {}}, family, None, True)                               # keyframe = first frame: the recorded voice cannot go with it
    assert sung is None and said and said["lyrics"] == ["Children!"]
    sung, said = R._voice(d, shot, {"meta": {}}, family, None, False)                              # no keyframe: audio is allowed
    assert sung is sentinel and said is None


def test_the_song_clip_under_a_shot_uploads_as_audio_and_a_refused_file_says_so(tmp_path, monkeypatch):
    d = str(tmp_path)
    clip = tmp_path / "clip.mp3"
    clip.write_bytes(b"ID3fake")

    class Prov:
        name = "kie"
        def upload(self, path):
            return "https://cdn/" + os.path.basename(path)
    assert R._upload_cached(d, Prov(), str(clip)) == "https://cdn/clip.mp3"                          # before: left out as "not a picture", then IndexError
    odd = tmp_path / "notes.xyz"
    odd.write_bytes(b"x")
    with pytest.raises(R.RequestProblem, match="nothing was charged"):
        R._upload_cached(d, Prov(), str(odd))


# ---------------------------------------------------------------- picture limits a model does not spell out
def test_a_picture_list_described_in_the_singular_holds_one_picture():
    m = kie("kling/v3-turbo-image-to-video", f("prompt", required=True), f("image_urls", "array", items="string", required=True,
            description="URL of the image to be used for the video (File URL after upload; Accepted types: image/jpeg, image/png; Max size: 10.0MB)"), f("duration", "integer"))
    field = next(i for i in m["inputs"] if i["name"] == "image_urls")
    assert field["max_items"] == 1 and R.frames_only(m)
    assert build(m, SHEETY)["image_urls"] == ["https://x/keyframe.png"]                               # not the keyframe plus the cast sheet


def test_up_to_n_images_in_the_description_is_a_limit():
    m = kie("some/two", f("prompt"), f("image_urls", "array", items="string", description="Image URLs, supports up to 2 images, single image size not exceeding 20 MB."), f("duration", "integer"))
    assert next(i for i in m["inputs"] if i["name"] == "image_urls")["max_items"] == 2
    many = kie("some/many", f("prompt"), f("image_urls", "array", items="string", description="Multiple reference images can be uploaded."), f("duration", "integer"))
    assert not next(i for i in many["inputs"] if i["name"] == "image_urls").get("max_items")


def test_a_limit_a_provider_states_is_remembered_and_nothing_is_billed(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "LEARNED_LIMITS", str(tmp_path / "learned.json"))
    monkeypatch.setattr(R, "CACHE_DIR", str(tmp_path))

    class Resp:
        status_code = 200
        def json(self): return {"code": 422, "msg": "image_urls supports at most 1 files"}
    monkeypatch.setenv("KIE_KEY", "k")
    monkeypatch.setattr(R.requests, "post", lambda *a, **k: Resp())
    with pytest.raises(R.RequestProblem, match="takes at most 1 picture.*nothing was charged.*Send again"):
        R.Kie().submit("new/model", {"prompt": "p"})
    m = kie("new/model", f("prompt", required=True), f("image_urls", "array", items="string", description="Reference images."), f("duration", "integer"))
    assert next(i for i in m["inputs"] if i["name"] == "image_urls")["max_items"] == 1                 # the next request is right
    assert R.frames_only(m) and build(m, SHEETY)["image_urls"] == ["https://x/keyframe.png"]
    assert R.learned_limit("kie", "other/model", "image_urls") is None


def test_a_sung_line_under_a_medium_shot_is_voiced_even_when_the_shot_never_says_sings(tmp_path):
    line = [{"text": "Don't you forget!", "start": 4.4, "end": 6.0}]
    d, shot = musical(tmp_path, ["Queen Bee places a gentle hand on Emmanuel's cheek."], line)
    assert R.singing(d, {**shot, "framing": "Medium two-shot 50 mm"}, {"meta": {}})["lyrics"] == ["Don't you forget!"]
    assert R.singing(d, {**shot, "framing": "Wide establishing shot"}, {"meta": {}}) is None            # no mouth is assumed in a wide shot
    assert R.singing(d, {**shot, "framing": "Medium"}, {"meta": {}}) is not None
    short = [{"text": "Oh", "start": 5.4, "end": 5.8}]
    other = tmp_path.parent / (tmp_path.name + "_x")
    other.mkdir()
    d, shot = musical(other, ["She waits."], short)
    assert R.singing(d, {**shot, "framing": "Medium"}, {"meta": {}}) is None                           # barely heard: not enough to ask for a mouth


def test_switching_the_takes_sound_on_asks_for_the_words_not_a_hum(tmp_path):
    d, shot = musical(tmp_path, ["Queen Bee places a hand on his cheek."], [{"text": "Don't you forget!", "start": 4.4, "end": 6.0}])
    shot["framing"] = "Medium two-shot 50 mm"
    m = seedance2("bytedance/seedance-2-fast")
    said = R.singing(d, shot, {"meta": {}})
    plain = R.compile_request(shot, None, {"meta": {}}, {"look": {"style": "auto"}}, m, [], None, None, None, None, said)["prompt"]
    assert "no sound" in plain and "Performers do not lip-sync" not in plain.replace("Other performers", "")
    loud = R.compile_request(shot, None, {"meta": {}}, {"look": {"style": "auto"}}, m, [], {"generate_audio": True}, None, None, None, said)["prompt"]
    assert 'Beatrice sings: "Don\'t you forget!"' in loud and "No humming" in loud and "has no sound" not in loud and "do not lip-sync" not in loud


def volcengine_lipsync():
    return kie("volcengine/video-to-video-lip-sync", f("mode", enum=["lite", "basic"], required=True, description="Service mode for lip-sync generation."),
               f("video_url", required=True), f("audio_url", required=True), f("separate_vocal", "boolean"), f("open_scenedet", "boolean"))


def test_the_kie_lip_sync_pass_sends_the_service_mode_it_requires(tmp_path, monkeypatch):
    (tmp_path / "gen").mkdir()
    monkeypatch.setattr(R, "take_duration", lambda p: 4.5)
    monkeypatch.setattr(R, "song_slice", lambda d, shot, secs, vocals_only=False: str(tmp_path / "vocal.wav"))
    (tmp_path / "vocal.wav").write_bytes(b"x")
    man = volcengine_lipsync()
    take = {"output": "gen/take.mp4"}
    two = {"id": "S03-03", "start": 49.6, "end": 54.1, "performers": ["Beatrice", "Emmanuel"], "framing": "Medium two-shot 50 mm"}
    p = R.compile_lipsync(str(tmp_path), man, two, take, None)
    assert p["mode"] == "basic" and p["open_scenedet"] is True and p["video_url"].endswith("gen/take.mp4")          # before: "Needs a value for mode"
    solo = {**two, "performers": ["Beatrice"], "framing": "Close-up on her face"}
    assert R.compile_lipsync(str(tmp_path), man, solo, take, None)["mode"] == "lite"
    assert R.compile_lipsync(str(tmp_path), man, solo, take, {"mode": "basic"})["mode"] == "basic"                  # a pinned choice wins
