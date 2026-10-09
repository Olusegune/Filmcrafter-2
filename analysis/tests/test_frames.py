"""Start and end frames: modes, seamless chaining, no circular chains, the model switch, and what is really sent."""
import json
import os

import pytest
from PIL import Image

from pulseframe_analysis import frames as FR
from pulseframe_analysis import library as L
from pulseframe_analysis import render as R


def F(**kw):
    return {"description": "", **kw}


def _video(model, last=True):
    fields = [F(name="prompt", type="string"), F(name="image_url", type="string"),
              F(name="duration", type="string", enum=["5"])]
    if last:
        fields.append(F(name="end_image_url", type="string"))
    return R._finish("fal", model, model, "", fields)


@pytest.fixture
def proj(tmp_path):
    d = tmp_path / "p"
    (d / "media").mkdir(parents=True)
    shots = [{"id": f"S01-0{i}", "start": (i - 1) * 2.0, "end": i * 2.0, "performers": [], "beats": [f"beat {i}"]} for i in (1, 2, 3)]
    (d / "project.json").write_text(json.dumps({"title": "T", "schema_version": 2}))
    (d / "production.json").write_text(json.dumps({"scenes": [{"number": 1, "heading": "EXT", "shots": shots}]}))
    kf = {}
    for i in (1, 2, 3):
        Image.new("RGB", (32, 18), (i * 40, 0, 0)).save(d / "media" / f"kf{i}.png")
        kf[f"S01-0{i}"] = f"project:media/kf{i}.png"
    (d / "keyframes.json").write_text(json.dumps({"production": kf}))
    (d / "jobs.json").write_text(json.dumps({"jobs": []}))
    return str(d)


def test_no_end_frame_by_default(proj):
    g = FR.get(proj)
    assert g["S01-01"]["end_mode"] == "none" and g["S01-01"]["end"] is None
    assert g["S01-01"]["start"] == "project:media/kf1.png" and g["S01-01"]["next"] == "S01-02" and g["S01-03"]["next"] is None


def test_next_mode_lands_on_the_next_shots_start_and_follows_it(proj):
    FR.set_(proj, "S01-01", {"end_mode": "next"})
    assert FR.get(proj)["S01-01"]["end"] == "project:media/kf2.png"
    kf = json.load(open(os.path.join(proj, "keyframes.json")))
    kf["production"]["S01-02"] = "project:media/kf3.png"          # the next shot's start changes...
    json.dump(kf, open(os.path.join(proj, "keyframes.json"), "w"))
    assert FR.get(proj)["S01-01"]["end"] == "project:media/kf3.png"  # ...and this shot's end follows it


def test_last_shot_cannot_flow_into_nothing(proj):
    with pytest.raises(SystemExit, match="last shot"):
        FR.set_(proj, "S01-03", {"end_mode": "next"})


def test_chaining_never_becomes_circular(proj):
    from pulseframe_analysis import continuity
    continuity.set_shot(proj, "S01-02", {"continuous": True})        # S01-02 starts from S01-01's last frame
    with pytest.raises(SystemExit, match="one or the other"):
        FR.set_(proj, "S01-01", {"end_mode": "next"})
    continuity.set_shot(proj, "S01-02", {"continuous": False})
    FR.set_(proj, "S01-01", {"end_mode": "next"})
    with pytest.raises(SystemExit, match="one or the other"):
        FR.set_start(proj, "S01-02", "previous")


def test_chain_selected_skips_the_last_shot(proj):
    r = FR.chain_shots(proj, ["S01-01", "S01-02", "S01-03"])
    assert r["chained"] == ["S01-01", "S01-02"] and r["skipped"][0]["shot"] == "S01-03"


def test_own_end_frame_from_an_image_you_bring(proj, tmp_path):
    src = tmp_path / "mine.jpg"
    Image.new("RGB", (32, 18)).save(src)
    g = FR.use_image(proj, "S01-02", str(src))
    assert g["end_mode"] == "own" and g["end"].startswith("project:media/S01-02_end_") and src.exists()
    with pytest.raises(SystemExit, match="PNG, JPG"):
        FR.use_image(proj, "S01-02", str(proj) + "/project.json")


def test_locked_shot_frames_cannot_change(proj):
    L.set_shot(proj, "S01-01", locked=True)
    with pytest.raises(SystemExit, match="locked"):
        FR.set_(proj, "S01-01", {"end_mode": "next"})


def test_end_stills_are_options_for_the_end_never_the_start(proj):
    out = "generations/S01-01__e1.png"
    os.makedirs(os.path.join(proj, "generations"), exist_ok=True)
    Image.new("RGB", (32, 18)).save(os.path.join(proj, out))
    kf = json.load(open(os.path.join(proj, "keyframes.json")))
    kf["production"].pop("S01-01")
    json.dump(kf, open(os.path.join(proj, "keyframes.json"), "w"))
    job = {"id": "e1", "shot_id": "S01-01", "plan": "production", "kind": "image", "frame": "end", "state": "ready",
           "output": out, "created": 5, "provider": "fal", "model": "m"}
    json.dump({"jobs": [job]}, open(os.path.join(proj, "jobs.json"), "w"))
    assert L.pending_keyframes(proj) == {} and L.keyframe_options(proj, ["S01-01"])["S01-01"]["options"] == []
    assert [o["job"] for o in FR.options(proj, ["S01-01"])["S01-01"]["options"]] == ["e1"]
    assert FR.choose(proj, "S01-01", "e1")["end"] == "project:" + out


def test_model_switches_to_the_start_end_version_only_when_needed(monkeypatch):
    mans = {"turbo": _video("turbo", last=False), "pro": _video("pro"), "plain": _video("plain", last=False), "both": _video("both")}
    monkeypatch.setattr(R, "manifest", lambda p, m, *a, **k: mans[m])
    monkeypatch.setitem(FR.END_VERSIONS, ("fal", "turbo"), "pro")
    assert FR.model_for("fal", "turbo", False)["model"] == "turbo"                       # no end frame: untouched
    assert FR.model_for("fal", "both", True) == {"provider": "fal", "model": "both", "swapped": False, "supports_end": True, "proven": False}
    assert FR.model_for("fal", "turbo", True) == {"provider": "fal", "model": "pro", "swapped": True, "supports_end": True, "proven": False}
    assert FR.model_for("fal", "plain", True)["supports_end"] is False                   # said plainly, never faked
    monkeypatch.setitem(mans, "bytedance/seedance-2", _video("bytedance/seedance-2"))
    assert FR.model_for("kie", "bytedance/seedance-2", True)["supports_end"] is True       # its own first + last frame mode (its references are what Kie refuses beside a first frame)
    assert FR.model_for("kie", "bytedance/seedance-2", True)["proven"] is False             # said plainly: not yet proven with a real render


def test_end_frame_goes_to_the_last_frame_input_and_nowhere_else():
    man = _video("both")
    refs = [{"label": "kf", "url": "START", "keyframe": True}, {"label": "end frame", "url": "END", "endframe": True}]
    p = R.compile_request({"id": "S", "start": 0, "end": 5, "beats": ["x"]}, None, {"scenes": []}, {}, man, refs)
    assert p["image_url"] == "START" and p["end_image_url"] == "END"
    p2 = R.compile_request({"id": "S", "start": 0, "end": 5, "beats": ["x"]}, None, {"scenes": []}, {}, _video("plain", last=False), refs)
    assert "END" not in json.dumps(p2)                                                      # never smuggled in as a reference


def test_enqueue_renders_end_frame_shots_on_the_start_end_version(proj, monkeypatch):
    mans = {"turbo": _video("turbo", last=False), "pro": _video("pro")}
    monkeypatch.setattr(R, "manifest", lambda p, m, *a, **k: mans[m])
    monkeypatch.setitem(FR.END_VERSIONS, ("fal", "turbo"), "pro")
    monkeypatch.setattr("pulseframe_analysis.routing.guard", lambda *a, **k: None)
    FR.set_(proj, "S01-01", {"end_mode": "next"})
    jobs = {j["shot_id"]: j for j in R.enqueue(proj, ["S01-01", "S01-02"], "fal", "turbo", {})}
    assert jobs["S01-01"]["model"] == "pro" and jobs["S01-01"]["swapped_from"] == "turbo"
    assert jobs["S01-01"]["end_frame"] == "project:media/kf2.png"
    assert jobs["S01-02"]["model"] == "turbo" and "end_frame" not in jobs["S01-02"]
    assert R.enqueue(proj, ["S01-01"], "fal", "turbo", {}) == []                            # never queued twice


def test_end_still_prompt_describes_where_the_shot_lands():
    p = FR.end_still_prompt({"visual_prompt": "She runs to the door"}, "her hand on the handle, looking back")
    assert p["visual_prompt"].startswith("The LAST frame") and "hand on the handle" in p["visual_prompt"]
    assert "She runs to the door" in p["visual_prompt"]


# ---------------------------------------------------------------- bringing your own start frame (Midjourney, a photograph, anything)

def test_your_own_image_becomes_the_start_frame_and_is_copied_into_the_project(proj, tmp_path):
    mj = tmp_path / "midjourney_grid_upscaled.png"
    Image.new("RGB", (64, 36), (9, 99, 199)).save(mj)
    g = FR.use_start_image(proj, "S01-02", str(mj))
    assert g["start"].startswith("project:media/S01-02_start_") and g["start_mode"] == "keyframe"
    assert os.path.exists(os.path.join(proj, g["start"][len("project:"):])) and os.path.exists(mj)       # a copy: the original is untouched
    kf = json.load(open(os.path.join(proj, "keyframes.json")))["production"]
    assert kf["S01-02"] == g["start"] and kf["S01-01"] == "project:media/kf1.png"                          # only that shot changed


def test_your_own_start_frame_replaces_a_continue_from_previous_start(proj, tmp_path):
    from pulseframe_analysis import continuity as CT
    CT.set_shot(proj, "S01-02", {"continuous": True})
    assert FR.get(proj)["S01-02"]["start_mode"] == "previous"
    img = tmp_path / "x.jpg"
    Image.new("RGB", (32, 18)).save(img)
    assert FR.use_start_image(proj, "S01-02", str(img))["start_mode"] == "keyframe"


@pytest.mark.parametrize("name,why", [("missing.png", "can't be found"), ("notes.txt", "PNG, JPG or WebP")])
def test_a_bad_start_image_is_refused_in_plain_words(proj, tmp_path, name, why):
    p = tmp_path / name
    if name != "missing.png":
        p.write_text("hi")
    with pytest.raises(SystemExit) as e:
        FR.use_start_image(proj, "S01-01", str(p))
    assert why in str(e.value)


def test_a_locked_shot_keeps_its_start_frame(proj, tmp_path):
    L.set_shot(proj, "S01-01", locked=True)
    img = tmp_path / "x.png"
    Image.new("RGB", (32, 18)).save(img)
    with pytest.raises(SystemExit) as e:
        FR.use_start_image(proj, "S01-01", str(img))
    assert "locked" in str(e.value)
    assert json.load(open(os.path.join(proj, "keyframes.json")))["production"]["S01-01"] == "project:media/kf1.png"


# ---------------------------------------------------------------- the models that really have start + end frames on Kie.ai

def _seedance(model="bytedance/seedance-2"):
    fields = [F(name="prompt", type="string", required=True), F(name="first_frame_url", type="string", description="First frame image url"),
              F(name="last_frame_url", type="string", description="End frame image url. last_frame_url cannot be passed alone; first_frame_url must be provided together with it."),
              F(name="reference_image_urls", type="array", items="string", max_items=9, description="Reference images. Mutually exclusive with first/last frames."),
              F(name="duration", type="integer", minimum=4, maximum=15), F(name="aspect_ratio", type="string", enum=["16:9", "9:16"])]
    return R._finish("kie", model, "Seedance 2.0", "", fields)


def _kling3():
    fields = [F(name="prompt", type="string", required=True),
              F(name="image_urls", type="array", items="string",
                description="First and last frame image URLs. Optional. When multi_shots is false: if length is 2, index 0 is the first frame and index 1 is the last frame; if length is 1, the array item serves as the first frame."),
              F(name="sound", type="boolean", required=True), F(name="duration", type="string", required=True), F(name="mode", type="string", enum=["std", "pro", "4K"], required=True),
              F(name="multi_shots", type="boolean", required=True), F(name="aspect_ratio", type="string", enum=["16:9", "9:16", "1:1"])]
    return R._finish("kie", "kling-3.0/video", "Kling 3.0", "", fields)


def _compile(man, refs, kf="https://u/kf.png", end="https://u/end.png"):
    shot = {"id": "S1", "start": 0.0, "end": 5.0, "beats": ["A boy becomes an old man."], "performers": []}
    allrefs = ([{"label": "keyframe", "url": kf, "keyframe": True}] if kf else []) + ([{"label": "end", "url": end, "endframe": True}] if end else []) + refs
    p = R.compile_request(shot, None, {"meta": {}, "characters": [], "scenes": []}, {}, man, allrefs)
    return R.exclusive_inputs(man["provider"], man["model"], R.fill_required(man, p, allrefs), man)


SHEETS = [{"label": "character sheet", "url": "https://u/sheet.png"}, {"label": "set", "url": "https://u/set.png"}]


def test_kie_seedance_sends_the_first_and_last_frame_together_and_drops_the_references():
    for model in ("bytedance/seedance-2", "bytedance/seedance-2-fast", "bytedance/seedance-2-mini", "bytedance/seedance-2-5"):
        p = _compile(_seedance(model), SHEETS)
        assert p["first_frame_url"] == "https://u/kf.png" and p["last_frame_url"] == "https://u/end.png", model
        assert "reference_image_urls" not in p, model


def test_kie_seedance_never_sends_a_last_frame_without_its_first_frame():
    p = _compile(_seedance(), SHEETS, kf=None)
    assert "last_frame_url" not in p and "first_frame_url" not in p


def test_a_start_only_seedance_shot_is_unchanged():
    p = _compile(_seedance(), SHEETS, end=None)
    assert p["first_frame_url"] == "https://u/kf.png" and "last_frame_url" not in p and "reference_image_urls" not in p


def test_kling_3_is_recognised_as_taking_a_first_and_a_last_frame_through_its_picture_list():
    m = _kling3()
    assert R.frame_list_size(m) == 2 and m["caps"]["first_frame"] and m["caps"]["last_frame"] and m["caps"]["image_refs"] == 0


def test_kling_3_gets_exactly_the_start_and_end_pictures_and_never_a_character_sheet():
    p = _compile(_kling3(), SHEETS)
    assert p["image_urls"] == ["https://u/kf.png", "https://u/end.png"] and p["multi_shots"] is False
    assert _compile(_kling3(), SHEETS, end=None)["image_urls"] == ["https://u/kf.png"]


def test_kling_3_is_supported_for_start_and_end_without_a_model_swap(monkeypatch):
    monkeypatch.setattr(R, "manifest", lambda p, m, *a, **k: _kling3())
    r = FR.model_for("kie", "kling-3.0/video", True)
    assert r["supports_end"] is True and r["swapped"] is False and r["model"] == "kling-3.0/video"


def test_a_picture_list_that_is_plain_references_is_not_mistaken_for_frames():
    f = [F(name="prompt", type="string"), F(name="image_urls", type="array", items="string", max_items=9, description="Reference images of the characters."), F(name="duration", type="integer")]
    m = R._finish("kie", "x/y", "x", "", f)
    assert R.frame_list_size(m) == 0 and not m["caps"]["last_frame"]


# ---------------------------------------------------------------- a shot id never reaches a file name unless the plan has that shot

@pytest.mark.parametrize("bad", ["../../outside", "S01-01/../../x", "..\\..\\x", "S99-99", ""])
def test_a_shot_id_that_is_not_in_the_plan_cannot_make_files(proj, tmp_path, bad):
    img = tmp_path / "x.png"
    Image.new("RGB", (32, 18)).save(img)
    for fn in (FR.use_image, FR.use_start_image):
        with pytest.raises(SystemExit) as e:
            fn(proj, bad, str(img))
        assert "isn't in the plan" in str(e.value)
    assert os.listdir(os.path.join(proj, "media")) == [f"kf{i}.png" for i in (1, 2, 3)]
    assert not os.path.exists(os.path.join(os.path.dirname(proj), "outside"))
