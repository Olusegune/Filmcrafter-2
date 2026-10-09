"""Seedance chaining: a shot whose next shot continues from it asks the provider for its true last frame, keeps it, and the next shot starts exactly there."""
import io
import json
import os
import subprocess

import pytest
from PIL import Image

from filmcrafter_engine import continuity as CT, frames as FR, render as R
from filmcrafter_engine.export import ffmpeg


def F(name, type="string", **kw):
    return {"name": name, "type": type, "items": None, "enum": kw.get("enum"), "default": kw.get("default"), "minimum": None, "maximum": None, "max_items": None, "max_length": None,
            "description": kw.get("description", ""), "required": kw.get("required", False)}


def seedance(with_field=True):
    fields = [F("prompt", required=True), F("first_frame_url"), F("last_frame_url"), F("duration", "integer")]
    if with_field:
        fields.append(F("return_last_frame", "boolean", description="Whether to return the last frame of the video as an image."))
    return R._finish("kie", "bytedance/seedance-2", "Seedance 2.0", "", fields)


def png(color, size=(64, 36)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, "PNG")
    return b.getvalue()


@pytest.fixture
def project(tmp_path):
    d = tmp_path / "p"
    (d / "media").mkdir(parents=True)
    (d / "generations").mkdir()
    shots = [{"id": f"S01-0{i}", "scene": 1, "number": i, "start": (i - 1) * 4.0, "end": i * 4.0, "beats": [f"beat {i}"], "performers": [], "framing": "wide", "camera_moves": [],
              "source_shots": [f"S01-0{i}"]} for i in (1, 2, 3)]
    (d / "production.json").write_text(json.dumps({"meta": {}, "characters": [], "scenes": [{"number": 1, "heading": "INT. ROOM", "start": 0, "end": 12, "notes": {}, "shots": shots}]}))
    (d / "project.json").write_text(json.dumps({"title": "T", "song": "s.wav", "aspect_ratio": "16:9"}))
    (d / "songmap.json").write_text(json.dumps({"duration": 12.0, "lyrics": [], "sections": [], "beats": []}))
    for i in (1, 2, 3):
        Image.new("RGB", (64, 36), (i * 40, 0, 0)).save(d / "media" / f"kf{i}.png")
    (d / "keyframes.json").write_text(json.dumps({"production": {f"S01-0{i}": f"project:media/kf{i}.png" for i in (1, 2, 3)}}))
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=red:size=64x36:rate=12:duration=2", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(d / "generations" / "t1.mp4")], check=True)
    take = {"id": "t1", "shot_id": "S01-01", "plan": "production", "provider": "kie", "model": "bytedance/seedance-2", "kind": "video", "state": "ready", "output": "generations/t1.mp4",
            "overrides": {}, "fix_notes": [], "created": 100, "updated": 130, "attempts": 1, "provider_job_id": "r0", "error": None, "cost": None, "shot_start": 0, "shot_end": 4}
    (d / "jobs.json").write_text(json.dumps({"jobs": [take]}))
    return str(d)


def rgb(path):
    return Image.open(path).convert("RGB").getpixel((5, 5))


# ---------------------------------------------------------------- when to ask

def test_the_field_is_found_only_when_it_is_a_yes_or_no_input():
    assert R.last_frame_field(seedance()) == "return_last_frame"
    assert R.last_frame_field(seedance(False)) is None
    odd = R._finish("kie", "x/y", "x", "", [F("prompt", required=True), F("return_last_frame", "string"), F("duration", "integer")])
    assert R.last_frame_field(odd) is None


def test_a_shot_hands_on_when_it_lands_on_the_next_start_or_the_next_continues_from_it(project):
    assert not FR.hands_on(project, "S01-01") and not FR.hands_on(project, "S01-03")
    FR.set_(project, "S01-01", {"end_mode": "next"})
    assert FR.hands_on(project, "S01-01") and not FR.hands_on(project, "S01-02")
    CT.set_shot(project, "S01-03", {"continuous": True})
    assert FR.hands_on(project, "S01-02") and not FR.hands_on(project, "S01-03") and not FR.hands_on(project, "S09-09")


class Fake:
    name = "kie"
    sent = []
    poll_result = {"state": "done", "url": "https://cdn/out.mp4"}

    def upload(self, path):
        return "https://cdn/" + os.path.basename(path)

    def submit(self, model, payload):
        Fake.sent.append(payload)
        return {"id": "r1"}

    def poll(self, model, rid, meta=None):
        return Fake.poll_result


@pytest.fixture
def fake(monkeypatch):
    Fake.sent, Fake.poll_result = [], {"state": "done", "url": "https://cdn/out.mp4"}
    monkeypatch.setitem(R.PROVIDERS, "kie", Fake)
    monkeypatch.setattr(R, "manifest", lambda provider, model, refresh=False: seedance())
    monkeypatch.setattr(R, "_review", lambda d, store, j: None)
    served = {"last": png((0, 0, 255))}

    class Resp:
        status_code = 200

        def __init__(self, url):
            self.url, self.content = url, served["last"] if "last" in url else b"\0" * 64

        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self):
            if "broken" in self.url:
                raise R.requests.HTTPError("404")
        def iter_content(self, n): yield self.content
    monkeypatch.setattr(R.requests, "get", lambda url, **kw: Resp(url))
    return served


def jobs_of(project):
    return {j["id"]: j for j in R.Store(project).jobs}


def test_it_asks_for_the_last_frame_only_when_the_next_shot_needs_it(project, fake):
    R.enqueue(project, ["S01-02"], "kie", "bytedance/seedance-2", {}, [], "video")
    R.run(project, poll_every=0)
    assert "return_last_frame" not in Fake.sent[0]                              # nothing follows from S01-02
    Fake.sent.clear()
    CT.set_shot(project, "S01-03", {"continuous": True})
    R.enqueue(project, ["S01-02"], "kie", "bytedance/seedance-2", {}, [], "video")
    R.run(project, poll_every=0)
    assert Fake.sent[0]["return_last_frame"] is True


def test_a_model_without_the_input_is_never_sent_it(project, fake, monkeypatch):
    monkeypatch.setattr(R, "manifest", lambda provider, model, refresh=False: seedance(False))
    CT.set_shot(project, "S01-03", {"continuous": True})
    R.enqueue(project, ["S01-02"], "kie", "bytedance/seedance-2", {}, [], "video")
    R.run(project, poll_every=0)
    assert "return_last_frame" not in Fake.sent[0]


# ---------------------------------------------------------------- keeping it

def test_the_providers_last_frame_is_downloaded_with_the_take(project, fake):
    CT.set_shot(project, "S01-03", {"continuous": True})
    Fake.poll_result = {"state": "done", "url": "https://cdn/out.mp4", "last_frame_url": "https://cdn/last.jpg"}
    R.enqueue(project, ["S01-02"], "kie", "bytedance/seedance-2", {}, [], "video")
    R.run(project, poll_every=0)
    job = next(j for j in jobs_of(project).values() if j["shot_id"] == "S01-02")
    assert job["state"] == "ready" and job["last_frame_image"] == f"media/S01-02_last_{job['id']}.png" and rgb(os.path.join(project, job["last_frame_image"])) == (0, 0, 255)


def test_a_last_frame_that_cannot_be_fetched_never_fails_the_take(project, fake):
    Fake.poll_result = {"state": "done", "url": "https://cdn/out.mp4", "last_frame_url": "https://cdn/broken.jpg"}
    R.enqueue(project, ["S01-02"], "kie", "bytedance/seedance-2", {}, [], "video")
    R.run(project, poll_every=0)
    job = next(j for j in jobs_of(project).values() if j["shot_id"] == "S01-02")
    assert job["state"] == "ready" and "last_frame_image" not in job


def test_kie_hands_back_the_last_frame_address_when_there_is_one(monkeypatch):
    monkeypatch.setenv("KIE_KEY", "k")
    k = R.Kie()

    def reply(result):
        class Resp:
            status_code = 200
            headers = {}
            def json(self): return {"code": 200, "data": {"state": "success", "resultJson": json.dumps(result), "creditsConsumed": 40}}
            def raise_for_status(self): pass
        return Resp()
    monkeypatch.setattr(R, "http_get", lambda *a, **kw: reply({"resultUrls": ["https://x/v.mp4"], "lastFrameUrl": "https://x/l.jpg"}))
    assert k.poll("bytedance/seedance-2", "t")["last_frame_url"] == "https://x/l.jpg"
    monkeypatch.setattr(R, "http_get", lambda *a, **kw: reply({"resultUrls": ["https://x/v.mp4"], "last_frame_url": "https://x/m.jpg"}))
    assert k.poll("bytedance/seedance-2", "t")["last_frame_url"] == "https://x/m.jpg"
    monkeypatch.setattr(R, "http_get", lambda *a, **kw: reply({"resultUrls": ["https://x/v.mp4"], "lastFrameUrl": "javascript:alert(1)"}))
    assert "last_frame_url" not in k.poll("bytedance/seedance-2", "t")
    monkeypatch.setattr(R, "http_get", lambda *a, **kw: reply({"resultUrls": ["https://x/v.mp4"]}))
    assert "last_frame_url" not in k.poll("bytedance/seedance-2", "t")


# ---------------------------------------------------------------- using it

def test_the_next_shot_starts_on_the_exact_frame_the_provider_returned(project):
    Image.new("RGB", (64, 36), (0, 0, 255)).save(os.path.join(project, "media", "exact.png"))
    jobs = json.load(open(os.path.join(project, "jobs.json")))
    jobs["jobs"][0]["last_frame_image"] = "media/exact.png"
    json.dump(jobs, open(os.path.join(project, "jobs.json"), "w"))
    r = CT.chain(project, "S01-02")
    assert rgb(os.path.join(project, r["keyframe"])) == (0, 0, 255)                # not the red of the video itself


def test_without_a_saved_frame_it_still_reads_the_video(project):
    r = CT.chain(project, "S01-02")
    px = rgb(os.path.join(project, r["keyframe"]))
    assert px[0] > 150 and px[2] < 100                                              # red


def test_a_lip_synced_take_uses_the_frame_saved_for_the_video_under_it(project):
    Image.new("RGB", (64, 36), (0, 255, 0)).save(os.path.join(project, "media", "exact.png"))
    data = json.load(open(os.path.join(project, "jobs.json")))
    data["jobs"][0]["last_frame_image"] = "media/exact.png"
    lip = {**data["jobs"][0], "id": "l1", "kind": "lipsync", "source_job": "t1", "created": 200, "updated": 230, "last_frame_image": None}
    data["jobs"].append(lip)
    json.dump(data, open(os.path.join(project, "jobs.json"), "w"))
    r = CT.chain(project, "S01-02")
    assert rgb(os.path.join(project, r["keyframe"])) == (0, 255, 0)


def test_a_saved_frame_that_has_gone_is_ignored(project):
    data = json.load(open(os.path.join(project, "jobs.json")))
    data["jobs"][0]["last_frame_image"] = "media/gone.png"
    json.dump(data, open(os.path.join(project, "jobs.json"), "w"))
    assert CT.saved_last_frame(project, data["jobs"][0], data["jobs"]) is None
    assert CT.chain(project, "S01-02")["keyframe"].startswith("media/")


def test_a_chain_of_job_links_that_loops_does_not_hang(project):
    a = {"id": "a", "source_job": "b"}
    b = {"id": "b", "source_job": "a"}
    assert CT.saved_last_frame(project, a, [a, b]) is None


# ---------------------------------------------------------------- a latent bug found on the way: slow frame rates

def test_the_last_frame_of_a_slow_frame_rate_clip_is_found(tmp_path):
    from filmcrafter_engine.export import last_frame_png
    for rate in (6, 12, 24, 60):
        v, o = str(tmp_path / f"c{rate}.mp4"), str(tmp_path / f"o{rate}.png")
        subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c=red:size=64x36:rate={rate}:duration=2", "-pix_fmt", "yuv420p", "-c:v", "libx264", v], check=True)
        assert last_frame_png(v, o), rate
        assert Image.open(o).size == (64, 36)


def test_a_file_that_is_not_a_video_has_no_last_frame(tmp_path):
    from filmcrafter_engine.export import last_frame_png
    bad = tmp_path / "x.mp4"
    bad.write_bytes(b"nope")
    assert last_frame_png(str(bad), str(tmp_path / "o.png")) is False
