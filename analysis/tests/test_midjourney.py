"""Midjourney through Kie.ai's Midjourney endpoint: the request, the polling, the catalog. Mocked (nothing is billed); a real render has not been run."""
import pytest

from filmcrafter_engine import modelinfo, render as R

MJ = "midjourney/mj-v7"


class Resp:
    def __init__(self, body, status=200):
        self._b, self.status_code, self.text, self.headers = body, status, str(body), {}

    def json(self):
        return self._b

    def raise_for_status(self):
        pass


@pytest.fixture
def kie(monkeypatch):
    monkeypatch.setenv("KIE_KEY", "test-key")
    sent = {}
    monkeypatch.setattr(R.requests, "post", lambda url, json=None, headers=None, timeout=0: sent.update(url=url, body=json, headers=headers) or Resp({"code": 200, "msg": "success", "data": {"taskId": "t1"}}))
    return R.Kie(), sent


def test_the_manifest_is_a_picture_model_that_takes_reference_pictures():
    m = R.manifest("kie", MJ)
    assert "Midjourney" in m["title"] and m["roles"]["prompt"] == "prompt" and m["roles"]["ref_images"] == "image_urls" and "duration" not in m["roles"]
    f = {x["name"]: x for x in m["inputs"]}
    assert f["speed"]["enum"] == ["relaxed", "fast", "turbo"] and "7" in f["version"]["enum"] and "16:9" in f["aspect_ratio"]["enum"] and f["prompt"]["required"]


def test_it_is_listed_with_the_kie_picture_models_and_can_see_pictures(monkeypatch, tmp_path):
    monkeypatch.setattr(R, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(R, "_catalog", lambda provider, kind="video": [{"provider": "kie", "model": "google/nanobanana-2-1", "category": "image", "title": "Nano Banana 2.1"}])
    items = R.catalog("kie", "image", refresh=True)
    mj = next(i for i in items if i["model"] == MJ)
    assert mj["sees"] is True and mj["text"] is False
    assert not any(i["model"] == MJ for i in R.catalog("kie", "video", refresh=True) if i.get("provider") == "kie")
    assert len([i for i in R.catalog("kie", "image") if i["model"] == MJ]) == 1               # from the cache too, once


def test_text_only_request_is_sent_to_the_midjourney_endpoint_as_txt2img(kie):
    k, sent = kie
    assert k.submit(MJ, {"prompt": "a man on a train platform", "aspect_ratio": "21:9", "speed": "turbo", "version": "7", "stylization": 250}) == {"id": "t1"}
    assert sent["url"] == "https://api.kie.ai/api/v1/mj/generate" and sent["headers"]["Authorization"] == "Bearer test-key"
    b = sent["body"]
    assert b["taskType"] == "mj_txt2img" and b["aspectRatio"] == "21:9" and b["speed"] == "turbo" and b["version"] == "7" and b["stylization"] == 250
    assert "fileUrls" not in b and b["enableTranslation"] is False


def test_reference_pictures_make_it_an_image_to_image_request(kie):
    k, sent = kie
    k.submit(MJ, {"prompt": "same man, older", "image_urls": ["https://x/a.png", "", None, "https://x/b.png"]})
    assert sent["body"]["taskType"] == "mj_img2img" and sent["body"]["fileUrls"] == ["https://x/a.png", "https://x/b.png"]


def test_other_kie_models_still_use_the_market_endpoint(kie):
    k, sent = kie
    k.submit("google/nanobanana-2-1", {"prompt": "x"})
    assert sent["url"].endswith("/jobs/createTask") and sent["body"]["model"] == "google/nanobanana-2-1"


def test_a_refused_request_says_nothing_was_charged(kie, monkeypatch):
    k, _ = kie
    monkeypatch.setattr(R.requests, "post", lambda *a, **kw: Resp({"code": 422, "msg": "prompt is required"}))
    with pytest.raises(R.RequestProblem) as e:
        k.submit(MJ, {"prompt": ""})
    assert "nothing was charged" in str(e.value) and "prompt is required" in str(e.value)


def test_a_response_with_no_task_id_is_an_error_not_a_silent_success(kie, monkeypatch):
    k, _ = kie
    monkeypatch.setattr(R.requests, "post", lambda *a, **kw: Resp({"code": 200, "data": {}}))
    with pytest.raises(RuntimeError):
        k.submit(MJ, {"prompt": "x"})


@pytest.mark.parametrize("data,state", [
    ({"successFlag": 0}, "running"),
    ({"successFlag": 1, "resultInfoJson": {"resultUrls": [{"resultUrl": "https://x/1.png"}, {"resultUrl": "https://x/2.png"}]}}, "done"),
    ({"successFlag": 1, "resultInfoJson": '{"resultUrls": ["https://x/1.png"]}'}, "done"),
    ({"successFlag": 1, "resultInfoJson": {"resultUrls": []}}, "failed"),
    ({"successFlag": 2, "errorMessage": "blocked by filter"}, "failed"),
    ({"successFlag": 3}, "failed"),
    ({}, "running"),
])
def test_polling_reads_every_shape_of_answer(kie, monkeypatch, data, state):
    k, _ = kie
    monkeypatch.setattr(R, "http_get", lambda url, params=None, headers=None, **kw: Resp({"code": 200, "data": data}))
    r = k.poll(MJ, "t1")
    assert r["state"] == state
    if state == "done":
        assert r["url"] == "https://x/1.png"
    if data.get("errorMessage"):
        assert "blocked by filter" in r["error"]


def test_the_polling_address_carries_the_task_id(kie, monkeypatch):
    k, _ = kie
    seen = {}
    monkeypatch.setattr(R, "http_get", lambda url, params=None, headers=None, **kw: seen.update(url=url, params=params) or Resp({"data": {"successFlag": 0}}))
    k.poll(MJ, "task-9")
    assert seen["url"] == "https://api.kie.ai/api/v1/mj/record-info" and seen["params"] == {"taskId": "task-9"}


def test_the_picture_picker_marks_it_as_seeing_pictures():
    assert modelinfo.sees_pictures(MJ, "image") is True
