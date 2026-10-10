"""Regression tests for the render pipeline (mocked providers; nothing is billed).

Each test pins a real failure found while auditing live generation:
- Director Mode model switches failed when fal's catalog rate-limited anonymous schema reads (429)
- models with required inputs FilmCrafter didn't send were rejected by the provider
- Veo durations written as "4s" crashed request building
- a 429 while *sending* left jobs stuck in "submitting" forever
- errors surfaced as raw text instead of an actionable category
"""
import json
import os
import shutil
import tempfile

import pytest
import requests

from filmcrafter_engine import render as R


def field(name, type="string", **kw):
    return {"name": name, "type": type, "items": kw.get("items"), "enum": kw.get("enum"), "default": kw.get("default"),
            "minimum": kw.get("minimum"), "maximum": kw.get("maximum"), "max_items": kw.get("max_items"),
            "max_length": kw.get("max_length"), "description": kw.get("description", ""), "required": kw.get("required", False)}


def man(*fields, title="Test model"):
    return R._finish("fal", "test/model", title, "image-to-video", list(fields))


# ------------------------------------------------------------------ requests: required inputs + validation

def test_fill_required_uses_defaults_enums_booleans_and_images():
    m = man(field("prompt", required=True), field("quality", enum=["360p", "540p"], required=True),
            field("prompt_expansion_mode", enum=["off", "auto"], default="auto", required=True),
            field("audio", "boolean", required=True), field("image_url", required=True, description="Start image"))
    p = R.fill_required(m, {"prompt": "x"}, [{"label": "Sege", "url": "https://cdn/sege.png"}])
    assert p["quality"] == "360p" and p["prompt_expansion_mode"] == "auto" and p["audio"] is False
    assert p["image_url"] == "https://cdn/sege.png"
    assert R.validate_request(m, p) == []


def test_validation_blocks_what_cannot_be_supplied():
    m = man(field("prompt", required=True), field("video_url", required=True, description="Source video"),
            field("aspect_ratio", enum=["16:9", "9:16"]))
    problems = R.validate_request(m, {"prompt": "x", "aspect_ratio": "21:9"})
    assert any("Needs a video" in p and "video_url" in p for p in problems)
    assert any("aspect_ratio" in p and "21:9" in p for p in problems)


def test_stray_spaces_in_documented_field_names_still_map_roles():
    """A trailing space in a model's documented field name is a typo in the docs: the role is found and the name is sent without it
    (Kie's happyhorse/image-to-video refused "image_urls " as a missing required field)."""
    m = man(field("prompt"), field("image_urls ", "array", items="string"))
    assert m["roles"]["ref_images"] == "image_urls"


def test_boolean_named_audio_is_not_treated_as_an_audio_file():
    m = man(field("prompt"), field("audio", "boolean"))
    assert "src_audio" not in m["roles"]


@pytest.mark.parametrize("enum,need,expect", [(["4s", "6s", "8s"], 3.0, "4s"), (["4", "6", "8"], 5.0, "6"), (["5", "10"], 12.0, "10")])
def test_duration_enums_with_units(enum, need, expect):
    assert R._duration_value(field("duration", enum=enum), need) == expect


# ------------------------------------------------------------------ errors

@pytest.mark.parametrize("text,status,kind", [
    ("Unauthorized", 401, "auth"), ("Insufficient credits", 400, "credits"),
    ("403: User is locked. Reason: TOP_UP.", 403, "credits"), ("403: User is locked. Reason: TOP_UP.", None, "credits"), ("Model not found", 404, "unavailable"),
    ("Too Many Requests", 429, "rate_limit"), ("Input failed safety check", 422, "policy"),
    ("field 'duration' invalid", 422, "invalid"), ("upstream exploded", 502, "service")])
def test_error_classification(text, status, kind):
    assert R.classify_error(text, status) == kind
    assert R.ERROR_KINDS[kind] in R.describe_error(text, status)


# ------------------------------------------------------------------ network: metadata reads retry, submits never do

def test_http_get_retries_rate_limits(monkeypatch):
    calls = []

    class Resp:
        def __init__(self, code):
            self.status_code, self.headers = code, {"Retry-After": "0"}

    def fake_get(url, **kw):
        calls.append(url)
        return Resp(429 if len(calls) < 3 else 200)
    monkeypatch.setattr(R.requests, "get", fake_get)
    monkeypatch.setattr(R.time, "sleep", lambda s: None)
    assert R.http_get("https://api.fal.ai/v1/models").status_code == 200 and len(calls) == 3


def test_fal_schema_reads_are_authenticated(monkeypatch):
    monkeypatch.setenv("FAL_KEY", "k")
    assert R._fal_headers()["Authorization"] == "Key k"


# ------------------------------------------------------------------ job lifecycle with a mock provider

@pytest.fixture
def project(tmp_path):
    d = tmp_path / "proj"
    d.mkdir()
    shot = {"id": "S01-01", "scene": 1, "number": 1, "start": 0.0, "end": 2.0, "beats": ["A man waits."], "performers": [],
            "framing": "wide", "camera_moves": [], "source_shots": ["S01-01"]}
    plan = {"meta": {}, "characters": [], "scenes": [{"number": 1, "heading": "EXT. PLATFORM", "start": 0, "end": 2, "notes": {}, "shots": [shot]}]}
    (d / "production.json").write_text(json.dumps(plan))
    (d / "project.json").write_text(json.dumps({"title": "T", "song": "song.wav", "aspect_ratio": "16:9"}))
    (d / "songmap.json").write_text(json.dumps({"duration": 2.0, "lyrics": [], "sections": [], "beats": []}))
    return str(d)


class FakeProvider:
    name = "fal"
    submits = 0
    submit_error = None
    poll_result = {"state": "done", "url": "https://cdn/out.mp4"}

    def upload(self, path):
        return "https://cdn/" + os.path.basename(path)

    def submit(self, model, payload):
        if FakeProvider.submit_error:
            raise FakeProvider.submit_error
        FakeProvider.submits += 1
        return {"id": f"r{FakeProvider.submits}"}

    def poll(self, model, rid, meta=None):
        return FakeProvider.poll_result


@pytest.fixture
def fake(monkeypatch):
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
    return FakeProvider


def test_happy_path_and_no_duplicates(project, fake):
    R.enqueue(project, ["S01-01"], "fal", "test/model", {})
    R.enqueue(project, ["S01-01"], "fal", "test/model", {})  # same shot + model while active: ignored
    R.run(project, poll_every=0)
    jobs = R.Store(project).jobs
    assert len(jobs) == 1 and jobs[0]["state"] == "ready" and fake.submits == 1
    assert os.path.exists(os.path.join(project, jobs[0]["output"]))


def test_rate_limit_while_sending_requeues_instead_of_sticking(project, fake):
    R.enqueue(project, ["S01-01"], "fal", "test/model", {})
    # the provider rate-limits the first sends, then accepts
    import threading
    fake.submit_error = R.ProviderError("429: Too Many Requests", 429)
    t = threading.Timer(0.5, lambda: setattr(fake, "submit_error", None))
    t.start()
    R.run(project, poll_every=0)
    t.cancel()
    j = R.Store(project).jobs[0]
    assert j["state"] == "ready" and fake.submits == 1


def test_server_error_while_sending_is_uncertain_not_resent(project, fake):
    R.enqueue(project, ["S01-01"], "fal", "test/model", {})
    fake.submit_error = R.ProviderError("502: bad gateway", 502)
    R.run(project, poll_every=0)
    j = R.Store(project).jobs[0]
    assert j["state"] == "uncertain" and fake.submits == 0


def test_crash_mid_send_is_never_resent(project, fake):
    R.enqueue(project, ["S01-01"], "fal", "test/model", {})
    store = R.Store(project)
    store.jobs[0]["state"] = "submitting"
    store.save()
    R.run(project, poll_every=0)
    assert R.Store(project).jobs[0]["state"] == "uncertain" and fake.submits == 0


def test_provider_failure_is_classified(project, fake):
    fake.poll_result = {"state": "failed", "error": "Your input was flagged by our content moderation system"}
    R.enqueue(project, ["S01-01"], "fal", "test/model", {})
    R.run(project, poll_every=0)
    j = R.Store(project).jobs[0]
    assert j["state"] == "failed" and j["error_kind"] == "policy" and "content filter" in j["error"]


def test_request_problems_block_before_billing(project, fake, monkeypatch):
    m = man(field("prompt", required=True), field("mask_image_url", required=True))
    monkeypatch.setattr(R, "manifest", lambda provider, model, refresh=False: m)
    R.enqueue(project, ["S01-01"], "fal", "test/model", {})
    R.run(project, poll_every=0)
    j = R.Store(project).jobs[0]
    assert j["state"] == "failed" and j["error_kind"] == "missing_input" and "nothing was charged" in j["error"]
    assert fake.submits == 0


def test_kie_doc_with_referenced_input_schema(monkeypatch):
    md = """# Some model
```yaml
openapi: 3.0.1
paths:
  /api/v1/jobs/createTask:
    post:
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Req'
components:
  schemas:
    Req:
      type: object
      properties:
        model: {type: string, enum: [vendor/model-x]}
        input: {$ref: '#/components/schemas/Inp'}
    Inp:
      type: object
      required: [prompt]
      properties:
        prompt: {type: string}
        image_urls : {type: array, items: {type: string}}
```"""

    class Resp:
        status_code, text, headers = 200, md, {}
    monkeypatch.setattr(R, "http_get", lambda url, **kw: Resp())
    m = R.kie_manifest("vendor/model-x", doc="https://docs/x.md")
    assert m["model"] == "vendor/model-x" and "prompt" in m["roles"]


def test_kie_model_renamed_inside_its_doc_is_found_again(monkeypatch, tmp_path):
    monkeypatch.setattr(R, "CACHE_DIR", str(tmp_path))
    calls = []

    def fake_kie(model, doc=None):
        calls.append(model)
        if model != "kling/image-to-video":
            raise SystemExit("not found")
        return R._finish("kie", "kling-2.6/image-to-video", "Kling", "", [field("prompt")])
    monkeypatch.setattr(R, "kie_manifest", fake_kie)
    assert R.manifest("kie", "kling/image-to-video")["model"] == "kling-2.6/image-to-video"
    os.remove(os.path.join(str(tmp_path), "kie__kling-2.6_image-to-video.json"))  # force a fresh lookup by resolved id
    assert R.manifest("kie", "kling-2.6/image-to-video")["model"] == "kling-2.6/image-to-video"
    assert calls[-1] == "kling/image-to-video"


def test_keyframe_prompts_lead_with_framing():
    m = man(field("prompt", required=True), field("image_urls", "array", items="string"))
    m["roles"].pop("duration", None)
    shot = {"id": "S01-01", "start": 0, "end": 2, "beats": ["He wakes."], "performers": ["Sege"],
            "framing": "extreme close-up on one eye", "lens": "macro"}
    p = R.compile_request(shot, None, {"meta": {}}, {"look": {"style": "auto"}}, m, [])
    assert p["prompt"].index("extreme close-up on one eye") < p["prompt"].index("He wakes.")


def test_characters_are_described_not_just_named():
    m = man(field("prompt", required=True), field("duration", enum=["5"]))
    plan = {"meta": {}, "characters": [{"name": "Sege", "appearance": "A Nigerian man in his late thirties. Medium-dark skin. Beard."}]}
    shot = {"id": "S01-01", "start": 0, "end": 2, "beats": ["x"], "performers": ["Sege"]}
    p = R.compile_request(shot, None, plan, {"look": {"style": "auto"}}, m, [])["prompt"]
    assert "Sege (A Nigerian man in his late thirties. Medium-dark skin)" in p


def test_concurrent_writers_do_not_lose_updates(project, fake):
    """The renderer and the app's review both write jobs.json: neither may undo the other."""
    R.enqueue(project, ["S01-01"], "fal", "test/model", {})
    a, b = R.Store(project), R.Store(project)
    a.update(a.jobs[0], state="submitted", provider_job_id="r1")
    b.update(b.jobs[0], review={"reviewed": True})            # b still holds the stale 'queued' copy of other fields
    j = R.Store(project).jobs[0]
    assert j["review"] == {"reviewed": True} and j["state"] == "submitted" and j["provider_job_id"] == "r1"
    extra = {**j, "id": "other"}
    c = R.Store(project); c.data["jobs"].append(extra); c.save()
    a.update(a.jobs[0], state="ready")
    assert {x["id"] for x in R.Store(project).jobs} == {j["id"], "other"}


def test_write_retries_when_windows_holds_the_file(tmp_path, monkeypatch):
    calls = []
    real = os.replace

    def flaky(src, dst):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError(5, "Access is denied")
        real(src, dst)
    monkeypatch.setattr(R.os, "replace", flaky)
    monkeypatch.setattr(R.time, "sleep", lambda s: None)
    R._write(str(tmp_path / "jobs.json"), {"jobs": []})
    assert len(calls) == 3 and json.load(open(tmp_path / "jobs.json")) == {"jobs": []}


def test_out_of_credits_pauses_instead_of_failing_everything(project, fake, monkeypatch):
    plan = json.load(open(os.path.join(project, "production.json")))
    sh = plan["scenes"][0]["shots"][0]
    plan["scenes"][0]["shots"].append({**sh, "id": "S01-02", "start": 2.0, "end": 4.0})
    json.dump(plan, open(os.path.join(project, "production.json"), "w"))
    R.enqueue(project, ["S01-01", "S01-02"], "fal", "test/model", {})
    fake.submit_error = R.ProviderError("403: User is locked. Reason: TOP_UP.", 403)
    R.run(project, poll_every=0)
    jobs = R.Store(project).jobs
    assert [j["state"] for j in jobs] == ["queued", "queued"] and fake.submits == 0
    assert jobs[0]["error_kind"] == "credits" and "credits" in jobs[0]["error"]
    fake.submit_error = None                     # topped up: the next run sends them
    R.run(project, poll_every=0)
    assert [j["state"] for j in R.Store(project).jobs] == ["ready", "ready"]


def test_an_unexpected_error_fails_one_job_not_the_run(project, fake, monkeypatch):
    plan = json.load(open(os.path.join(project, "production.json")))
    sh = plan["scenes"][0]["shots"][0]
    plan["scenes"][0]["shots"].append({**sh, "id": "S01-02", "start": 2.0, "end": 4.0})
    json.dump(plan, open(os.path.join(project, "production.json"), "w"))
    real = R.compile_request
    monkeypatch.setattr(R, "compile_request", lambda shot, *a, **k: (_ for _ in ()).throw(ValueError("boom")) if shot["id"] == "S01-01" else real(shot, *a, **k))
    R.enqueue(project, ["S01-01", "S01-02"], "fal", "test/model", {})
    R.run(project, poll_every=0)
    states = {j["shot_id"]: j["state"] for j in R.Store(project).jobs}
    assert states == {"S01-01": "failed", "S01-02": "ready"}


def test_openai_size_mapping_skips_auto():
    shot = {"id": "S01-01", "start": 0, "end": 2, "beats": ["x"], "performers": []}
    proj = {"look": {"style": "auto"}, "aspect_ratio": "2.39:1"}
    new = R.compile_request(shot, None, {"meta": {}}, proj, R.openai_manifest("gpt-image-2.5-flare"), [])
    assert new["size"] == "1536x640"                       # GPT Image 2.5 takes any size: a 2.39:1 project gets a 2.39:1 picture, never "auto"
    old = R.compile_request(shot, None, {"meta": {}}, proj, R.openai_manifest("gpt-image-1.5"), [])
    assert old["size"] == "1536x1024"                      # the older model has three fixed shapes (the keyframe is trimmed to 2.39:1 afterwards)


def test_production_bible_reaches_every_prompt():
    m = man(field("prompt", required=True), field("duration", enum=["5"]))
    shot = {"id": "S01-01", "start": 0, "end": 2, "beats": ["x"]}
    proj = {"look": {"style": "auto"}, "bible": {"world": "Lagos at night", "rules": "The suitcase is brown leather",
                                                  "palette": "", "avoid": "text on screen"}}
    p = R.compile_request(shot, None, {"meta": {}}, proj, m, [])["prompt"]
    assert "World: Lagos at night." in p and "Always: The suitcase is brown leather." in p and "Never show: text on screen." in p
    assert "Palette:" not in p


def test_review_catch_up_yields_to_new_renders(tmp_path, monkeypatch):
    d = str(tmp_path)
    jobs = [{"id": "t1", "shot_id": "S1", "plan": "production", "provider": "fal", "model": "m", "state": "ready", "output": "a.mp4", "created": 1, "updated": 1},
            {"id": "q1", "shot_id": "S2", "plan": "production", "provider": "fal", "model": "m", "state": "queued", "output": None, "created": 2, "updated": 2}]
    open(os.path.join(d, "jobs.json"), "w").write(json.dumps({"jobs": jobs}))
    seen = []
    monkeypatch.setattr(R, "_review", lambda d_, s, j: seen.append(j["id"]))
    assert R.review_pending(d, yield_to_renders=True) is True and seen == []
    assert R.review_pending(d) is False and seen == ["t1"]


def test_fal_price_keeps_last_known_price_when_lookup_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("FAL_KEY", "k")
    (tmp_path / "fal_prices.json").write_text(json.dumps({"m": {"price": {"unit": "seconds", "unit_price": 0.1}, "at": 0}}))
    class Bad:
        ok = False
        def json(self):
            return {}
    monkeypatch.setattr(R.requests, "get", lambda *a, **k: Bad())
    assert R._fal_price("m") == {"unit": "seconds", "unit_price": 0.1}


def test_expired_uploads_are_uploaded_again(tmp_path, monkeypatch):
    d = str(tmp_path)
    f = tmp_path / "a.png"
    f.write_bytes(b"img")
    import hashlib, time as _t
    key = "kie:" + hashlib.sha256(b"img").hexdigest()[:16]
    os.makedirs(os.path.join(d, "cache"))
    open(os.path.join(d, "cache", "uploads.json"), "w").write(json.dumps({key: {"url": "https://old/a.png", "at": int(_t.time()) - 7200}}))
    class P:
        name = "kie"
        def upload(self, path):
            return "https://new/a.png"
    monkeypatch.setattr(R, "_still_there", lambda url: False)
    assert R._uploaded(d, P(), [{"label": "x", "path": str(f)}])[0]["url"] == "https://new/a.png"
    monkeypatch.setattr(R, "_still_there", lambda url: True)
    assert R._uploaded(d, P(), [{"label": "x", "path": str(f)}])[0]["url"] == "https://new/a.png"   # fresh one reused


def test_seedance_on_kie_sends_first_frame_or_references_not_both():
    p = {"first_frame_url": "k.png", "reference_image_urls": ["a.png"], "prompt": "x"}
    assert R.exclusive_inputs("kie", "bytedance/seedance-2", dict(p)) == {"first_frame_url": "k.png", "prompt": "x"}
    assert R.exclusive_inputs("fal", "bytedance/seedance-2.0/reference-to-video", dict(p)) == p
    refs_only = {"reference_image_urls": ["a.png"]}
    assert R.exclusive_inputs("kie", "bytedance/seedance-2", dict(refs_only)) == refs_only


def test_recheck_asks_provider_again_without_resubmitting(tmp_path):
    d = str(tmp_path)
    open(os.path.join(d, "jobs.json"), "w").write(json.dumps({"jobs": [
        {"id": "a", "shot_id": "S1", "plan": "production", "provider": "kie", "model": "m", "state": "failed",
         "provider_job_id": "T1", "error": "Unexpected error: OSError", "created": 1, "updated": 1}]}))
    j = R.resolve(d, "a", "recheck")
    assert j["state"] == "submitted" and j["provider_job_id"] == "T1" and j["error"] is None


def test_renderer_exits_quietly_when_app_is_gone(monkeypatch):
    import builtins
    def broken(*a, **k):
        raise OSError(22, "Invalid argument")
    monkeypatch.setattr(builtins, "print", broken)
    exited = []
    monkeypatch.setattr(R.os, "_exit", lambda code: exited.append(code))
    R.emit(event="progress", stage="x")
    assert exited == [0]


def test_known_prompt_limits_are_measured_in_bytes():
    m = man(field("prompt", required=True), field("duration", enum=["5"]))
    m["model"] = "fal-ai/pixverse/v5.5/image-to-video"
    shot = {"id": "S1", "start": 0, "end": 2, "beats": ["“quoted” — " * 400], "performers": []}
    p = R.compile_request(shot, None, {"meta": {}}, {"look": {"style": "auto"}}, m, [])["prompt"]
    assert len(p.encode("utf-8")) <= 2000


def test_pixverse_on_kie_gets_one_image():
    p = R.exclusive_inputs("kie", "pixverse/image-to-video", {"image_urls": ["k", "a", "b"]})
    assert p["image_urls"] == ["k"]


def test_huge_images_are_uploaded_scaled_down(tmp_path):
    from PIL import Image
    big = tmp_path / "big.png"
    Image.new("RGB", (6336, 2688), (10, 20, 30)).save(big)
    small = tmp_path / "small.png"
    Image.new("RGB", (1024, 512)).save(small)
    out = R._upload_size(str(tmp_path), str(big))
    assert out != str(big) and max(Image.open(out).size) == 3840
    assert R._upload_size(str(tmp_path), str(small)) == str(small)


def test_http_errors_from_client_libraries_are_explained():
    from filmcrafter_engine import render as R

    class Resp:
        status_code = 403
        text = '{"detail": "User is locked. Reason: Exhausted balance."}'

    class HTTPStatusError(Exception):
        response = Resp()

    said, status = R.http_detail(HTTPStatusError("Client error '403 Forbidden' for url 'https://rest.fal.ai/storage/auth/token'"))
    assert status == 403 and "Exhausted balance" in said and R.classify_error(said, status) == "credits"
    assert R.http_detail(ValueError("plain"))[1] is None


def test_a_picture_with_no_reference_uses_the_text_only_model_of_the_same_family(project, fake, monkeypatch):
    assert R.text_only_model("google/nano-banana-edit", True) == "google/nano-banana-edit"
    assert R.text_only_model("google/nano-banana-edit", False) == "google/nano-banana"
    assert R.text_only_model("fal-ai/nano-banana/edit", False) == "fal-ai/nano-banana"
    assert R.text_only_model("some/other-model", False) == "some/other-model"
    seen = []
    monkeypatch.setattr(R, "manifest", lambda provider, model, refresh=False: (seen.append(model), R._finish("fal", model, "Picture", "text-to-image", [field("prompt", required=True)]))[1])
    R.enqueue(project, ["S01-01"], "fal", "google/nano-banana-edit", {"_variants": 1}, [], "image")
    R.run(project, poll_every=0)
    j = R.Store(project).jobs[0]
    assert j["model"] == "google/nano-banana" and j["swapped_from"] == "google/nano-banana-edit" and j["state"] == "ready"
    assert "google/nano-banana" in seen
