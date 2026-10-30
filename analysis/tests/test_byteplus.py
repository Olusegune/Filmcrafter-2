"""BytePlus ModelArk, ByteDance's own Seedream API, as a direct picture provider.

The sizes, prices and request fields below are the ones BytePlus publishes (docs.byteplus.com/en/docs/modelark: Seedream tutorial, image tutorial, pricing; read 2026-10-30). Nothing here calls
BytePlus: the HTTP call is replaced, so no picture is made and nothing is charged. Whether the real service accepts these requests is NOT proved by these tests."""
import base64
import io
import json
import os

import pytest
import requests
from PIL import Image

from filmcrafter_engine import budget, diagnostics, modelinfo as MI, render as R, router, routing

PRO, FLASH, LITE, V45, V40 = ("dola-seedream-5-0-pro-260628", "dola-seedream-5-0-flash-260915", "seedream-5-0-260128", "seedream-4-5-251128", "seedream-4-0-250828")
KEY = "ark-test-key-1234567890"


def project(quality="standard", aspect="16:9"):
    return {"look": {"style": "auto"}, "quality": quality, "aspect_ratio": aspect}


def png_bytes(w=8, h=8, color=(200, 80, 40)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------- sizes: the film's shape inside each model's published pixel range

def test_every_size_is_inside_the_published_range_for_every_shape():
    for model, info in R.BYTEPLUS_MODELS.items():
        lo, hi = info["pixels"]
        for tier in ("draft", "standard", "high", "max"):
            for aspect in ("16:9", "21:9", "2.39:1", "1:1", "4:3", "3:2", "3:4", "9:16", "4:5"):
                w, h = map(int, R.byteplus_size(model, project(tier, aspect)).split("x"))
                assert lo <= w * h <= hi, (model, tier, aspect, w, h)
                assert w % 16 == 0 and h % 16 == 0 and 1 / 16 <= w / h <= 16


def test_the_tiers_map_to_the_published_levels():
    px = lambda m, t: (lambda s: s[0] * s[1])(tuple(map(int, R.byteplus_size(m, project(t)).split("x"))))
    assert px(PRO, "draft") < px(PRO, "standard") < px(PRO, "high") == px(PRO, "max") <= 4_624_220          # 1K, 1.5K, 2K: Pro has no 4K
    assert px(V45, "draft") == px(V45, "standard") < px(V45, "high") == px(V45, "max")                        # 2K, then 4K
    assert px(V45, "max") > 8_000_000 and px(LITE, "max") > 8_000_000 and px(V40, "max") > 8_000_000
    assert px(V45, "standard") > 3_686_400                                                                    # 4.5 starts at 2K: at least 2560x1440
    assert R.byteplus_size(PRO, project("max")) == "2720x1536" and R.byteplus_size(PRO, project("standard")) == "2048x1152"


# ---------------------------------------------------------------- the price: BytePlus's published table, exact for the size and references sent

def test_prices_are_the_published_ones():
    price = lambda m, size, refs=0: R.byteplus_price(m, {"size": size, "image_urls": ["x"] * refs})["usd"]
    assert price(PRO, "2048x1152") == 0.045 and price(PRO, "2720x1536") == 0.09                              # 1.5K or lower, then higher
    assert price(PRO, "2048x1152", refs=1) == 0.045 and price(PRO, "2048x1152", refs=4) == round(0.045 + 3 * 0.003, 4)   # the first reference is free
    assert price(FLASH, "2048x1152") == 0.018 and price(LITE, "5456x3072") == 0.035 and price(V45, "5456x3072") == 0.04 and price(V40, "2720x1536") == 0.03
    assert price(V45, "5456x3072", refs=9) == 0.04                                                            # references are free on the other models


def test_the_pro_price_changes_exactly_at_2_61_million_pixels():
    just_over = R.byteplus_price(PRO, {"size": "1920x1360"})["usd"]     # 2,611,200 pixels
    over = R.byteplus_price(PRO, {"size": "1616x1616"})["usd"]          # 2,611,456
    inside = R.byteplus_price(PRO, {"size": "1600x1600"})["usd"]        # 2,560,000
    assert inside == 0.045 and just_over == 0.09 and over == 0.09


def test_an_unknown_model_or_a_missing_size_is_never_priced_by_guessing():
    assert R.byteplus_price("not-a-model", {"size": "1024x1024"})["usd"] is None
    assert R.byteplus_price(PRO, {})["usd"] is None
    assert R.byteplus_price(V45, {})["usd"] == 0.04                                                           # a flat price needs no size


def test_the_estimate_sheet_is_exact_and_says_where_the_price_comes_from(tmp_path):
    d = film(tmp_path, "standard")
    e = R.estimate(d, ["S01-01"], "byteplus", PRO, "image")
    assert e["usd"] == 0.05 and "published price" in e["basis"] and e["unknown"] == 0                         # 4.5 cents, shown rounded UP to the cent (never as 4)
    assert R.estimate(film(tmp_path / "m", "max"), ["S01-01"], "byteplus", PRO, "image")["usd"] == 0.09
    assert R.estimate(film(tmp_path / "x", "max"), ["S01-01"], "byteplus", V45, "image")["usd"] == 0.04
    assert routing.batch_usd(d, ["S01-01"], "byteplus", PRO, "image") == 0.05


# ---------------------------------------------------------------- the model, its fields and its request

def test_the_manifest_has_the_published_reference_limits():
    pro, v45 = R.manifest("byteplus", PRO), R.manifest("byteplus", V45)
    refs = lambda m: next(f for f in m["inputs"] if f["name"] == m["roles"]["ref_images"])["max_items"]
    assert (refs(pro), refs(v45), refs(R.manifest("byteplus", LITE)), refs(R.manifest("byteplus", FLASH))) == (10, 14, 14, 10)
    assert pro["roles"]["prompt"] == "prompt" and pro["title"] == "Seedream 5.0 Pro"
    with pytest.raises(SystemExit):
        R.manifest("byteplus", "not-a-model")


def test_the_catalog_lists_the_five_models_and_marks_the_sizes():
    cat = {m["model"]: m for m in MI.decorate(R._catalog("byteplus", "image"), "byteplus", "image", "C:/")}
    assert set(cat) == set(R.BYTEPLUS_MODELS) and R._catalog("byteplus", "video") == []
    assert [cat[m]["max_size"] for m in (PRO, FLASH, LITE, V45, V40)] == ["2K", "2K", "4K", "4K", "4K"]
    assert cat[PRO]["rec"] == 0 and cat[V45]["rec"] == 1 and cat[LITE]["rec"] == 2 and cat[V40]["rec"] is None and cat[PRO]["text"] and not cat[V45]["text"]


def req(model, quality="standard", aspect="16:9", refs=None):
    man = R.manifest("byteplus", model)
    shot = {"id": "S01-01", "start": 0.0, "end": 2.0, "beats": ["A woman waits."], "performers": [], "framing": "wide", "camera_moves": [], "source_shots": ["S01-01"]}
    return man, R.compile_request(shot, None, {"meta": {}}, project(quality, aspect), man, refs or [])


def test_the_compiled_request_carries_the_films_shape_and_is_valid():
    man, payload = req(PRO, "max", "9:16")
    assert payload["size"] == "1536x2720" and "A woman waits" in payload["prompt"]
    assert R.validate_request(man, payload) == []


class Reply:
    def __init__(self, status=200, body=None, text=""):
        self.status_code, self._body, self.text, self.reason = status, body, text, "reason"

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def ok_reply(b64=None):
    return Reply(200, {"model": "m", "data": [{"b64_json": b64 or base64.b64encode(png_bytes()).decode(), "size": "8x8"}], "usage": {"generated_images": 1}})


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("BYTEPLUS_KEY", KEY)
    for var in ("USERPROFILE", "HOME"):
        monkeypatch.setenv(var, str(tmp_path / "home"))
    monkeypatch.setattr(R, "CACHE_DIR", str(tmp_path / "cache"))
    return tmp_path


def capture(monkeypatch, reply):
    seen = {}

    def post(url, headers=None, json=None, timeout=None, **kw):
        seen.update(url=url, headers=headers, body=json, timeout=timeout)
        if isinstance(reply, Exception):
            raise reply
        return reply
    monkeypatch.setattr(R.requests, "post", post)
    return seen


def test_the_request_is_what_byteplus_documents(home, monkeypatch):
    seen = capture(monkeypatch, ok_reply())
    p = R.BytePlusImages()
    out = p.submit(PRO, {"prompt": "A woman waits.", "size": "2048x1152"})
    b = seen["body"]
    assert seen["url"] == "https://ark.ap-southeast.bytepluses.com/api/v3/images/generations" and seen["headers"]["Authorization"] == f"Bearer {KEY}"
    assert (b["model"], b["prompt"], b["size"], b["response_format"], b["watermark"], b["output_format"]) == (PRO, "A woman waits.", "2048x1152", "b64_json", False, "png")
    assert "image" not in b and b["sequential_image_generation"] == "disabled" and b["stream"] is False and seen["timeout"] >= 120
    assert out["id"].startswith("inline-") and out["file"].endswith(".png") and os.path.getsize(out["file"]) > 0
    assert p.poll(PRO, out["id"], {"file": out["file"]}) == {"state": "done", "url": "file:" + out["file"]}


def test_the_4_series_asks_for_no_output_format_and_a_jpeg_is_saved_as_one(home, monkeypatch):
    buf = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buf, format="JPEG")
    seen = capture(monkeypatch, ok_reply(base64.b64encode(buf.getvalue()).decode()))
    out = R.BytePlusImages().submit(V45, {"prompt": "x", "size": "2720x1536"})
    assert "output_format" not in seen["body"] and out["file"].endswith(".jpg")


def test_references_go_inside_the_request_as_lower_case_base64_pictures(home, monkeypatch):
    one, two = home / "a.png", home / "b.jpg"
    one.write_bytes(png_bytes())
    Image.new("RGB", (8, 8)).save(two, format="JPEG")
    seen = capture(monkeypatch, ok_reply())
    R.BytePlusImages().submit(PRO, {"prompt": "x", "size": "1024x1024", "image_urls": ["file:" + str(one)]})
    assert seen["body"]["image"].startswith("data:image/png;base64,") and isinstance(seen["body"]["image"], str)
    R.BytePlusImages().submit(PRO, {"prompt": "x", "size": "1024x1024", "image_urls": ["file:" + str(one), "file:" + str(two), "https://example.com/c.png"]})
    img = seen["body"]["image"]
    assert isinstance(img, list) and img[0].startswith("data:image/png;base64,") and img[1].startswith("data:image/jpeg;base64,") and img[2] == "https://example.com/c.png"
    assert base64.b64decode(img[0].split(",", 1)[1]) == png_bytes()


def test_no_more_references_than_the_model_takes_are_sent(home, monkeypatch):
    pic = home / "a.png"
    pic.write_bytes(png_bytes())
    seen = capture(monkeypatch, ok_reply())
    R.BytePlusImages().submit(PRO, {"prompt": "x", "size": "1024x1024", "image_urls": ["file:" + str(pic)] * 14})
    assert len(seen["body"]["image"]) == 10


def test_a_large_or_unreadable_picture_is_sent_as_a_jpeg_copy(home, monkeypatch):
    pic = home / "big.png"
    pic.write_bytes(png_bytes(64, 64))
    seen = capture(monkeypatch, ok_reply())
    monkeypatch.setattr(os.path, "getsize", lambda p: 9 * 1024 * 1024)
    R.BytePlusImages().submit(PRO, {"prompt": "x", "size": "1024x1024", "image_urls": ["file:" + str(pic)]})
    assert seen["body"]["image"].startswith("data:image/jpeg;base64,")


# ---------------------------------------------------------------- failure: nothing is sent when it should not be, and the key never appears in a message

@pytest.mark.security
def test_a_missing_key_is_refused_before_anything_is_sent(monkeypatch):
    monkeypatch.delenv("BYTEPLUS_KEY", raising=False)
    with pytest.raises(SystemExit):
        R.BytePlusImages()


@pytest.mark.security
def test_bad_references_are_refused_before_anything_is_sent(home, monkeypatch):
    seen = capture(monkeypatch, ok_reply())
    for bad in ("http://example.com/a.png", "ftp://x/y.png", "data:image/png;base64,AAAA", str(home / "missing.png")):
        with pytest.raises(R.ProviderError) as e:
            R.BytePlusImages().submit(PRO, {"prompt": "x", "size": "1024x1024", "image_urls": [bad]})
        assert e.value.status == 400 and KEY not in str(e.value)
    notpic = home / "x.png"
    notpic.write_text("not a picture")
    with pytest.raises(R.ProviderError):
        R.BytePlusImages().submit(PRO, {"prompt": "x", "size": "1024x1024", "image_urls": [str(notpic)]})
    assert seen == {}                                                                                           # no request was made for any of them


@pytest.mark.security
@pytest.mark.parametrize("status,body,kind", [(401, {"error": {"code": "AuthenticationError", "message": "The API key in the request is missing or invalid."}}, "auth"),
                                              (429, {"error": {"code": "RateLimit", "message": "Too many requests."}}, "rate_limit"),
                                              (400, {"error": {"code": "InvalidParameter", "message": "size is invalid"}}, "invalid"),
                                              (500, {"error": {"message": "internal"}}, "service")])
def test_errors_keep_their_status_and_never_show_the_key(home, monkeypatch, status, body, kind):
    capture(monkeypatch, Reply(status, body))
    with pytest.raises(R.ProviderError) as e:
        R.BytePlusImages().submit(PRO, {"prompt": "x", "size": "1024x1024"})
    assert e.value.status == status and body["error"]["message"] in str(e.value) and KEY not in str(e.value)
    assert R.classify_error(str(e.value), status) == kind


def test_an_error_page_that_is_not_json_still_gives_a_plain_error(home, monkeypatch):
    capture(monkeypatch, Reply(502, None, "<html>Bad gateway</html>"))
    with pytest.raises(R.ProviderError) as e:
        R.BytePlusImages().submit(PRO, {"prompt": "x", "size": "1024x1024"})
    assert e.value.status == 502 and "Bad gateway" in str(e.value)


def test_a_picture_the_moderation_refused_or_an_empty_answer_is_an_error(home, monkeypatch):
    capture(monkeypatch, Reply(200, {"data": [{"error": {"code": "OutputImageSensitiveContentDetected", "message": "The result may contain sensitive information."}}]}))
    with pytest.raises(R.ProviderError) as e:
        R.BytePlusImages().submit(PRO, {"prompt": "x", "size": "1024x1024"})
    assert e.value.status == 422 and "sensitive" in str(e.value)
    capture(monkeypatch, Reply(200, {"data": []}))
    with pytest.raises(R.ProviderError) as e2:
        R.BytePlusImages().submit(PRO, {"prompt": "x", "size": "1024x1024"})
    assert e2.value.status == 422


def test_a_timeout_says_the_picture_may_still_have_been_billed(home, monkeypatch):
    capture(monkeypatch, requests.Timeout("slow"))
    with pytest.raises(R.ProviderError) as e:
        R.BytePlusImages().submit(PRO, {"prompt": "x", "size": "1024x1024"})
    assert e.value.status == 504 and "billed" in str(e.value) and KEY not in str(e.value)
    capture(monkeypatch, requests.ConnectionError("down"))
    with pytest.raises(R.ProviderError) as e2:
        R.BytePlusImages().submit(PRO, {"prompt": "x", "size": "1024x1024"})
    assert e2.value.status == 503


# ---------------------------------------------------------------- the whole way: queued, sent, finished, counted

def film(folder, quality):
    folder.mkdir(parents=True, exist_ok=True)
    d = folder / "p"
    d.mkdir(exist_ok=True)
    shot = {"id": "S01-01", "scene": 1, "number": 1, "start": 0.0, "end": 2.0, "beats": ["A woman waits."], "performers": [], "framing": "wide", "camera_moves": [], "source_shots": ["S01-01"]}
    json.dump({"meta": {}, "characters": [], "scenes": [{"number": 1, "heading": "INT.", "start": 0, "end": 2, "notes": {}, "shots": [shot]}]}, open(d / "production.json", "w"))
    json.dump({"title": "T", "song": "s.wav", "look": {"style": "auto"}, "quality": quality, "aspect_ratio": "16:9"}, open(d / "project.json", "w"))
    json.dump({"duration": 2.0, "lyrics": [], "sections": [], "beats": []}, open(d / "songmap.json", "w"))
    return str(d)


def test_a_queued_picture_is_sent_finished_and_counted_at_its_exact_price(home, monkeypatch):
    seen = capture(monkeypatch, ok_reply(base64.b64encode(png_bytes(64, 36)).decode()))
    monkeypatch.setattr("filmcrafter_engine.stills.after_still", lambda *a, **k: None)
    d = film(home / "film", "standard")
    R.enqueue(d, ["S01-01"], "byteplus", PRO, {}, kind="image")
    R.run(d, poll_every=0)
    j = R.Store(d).jobs[0]
    assert j["state"] == "ready" and j["provider"] == "byteplus" and j["estimate_usd"] == 0.045 and j["output"]
    assert seen["body"]["size"] == "2048x1152" and j["payload"]["size"] == "2048x1152"
    assert os.path.exists(os.path.join(d, j["output"]))
    spent = budget.spent(d)
    assert spent["byteplus_usd"] == 0.045 and spent["total_usd"] == 0.05 and spent["renders"] == 1       # the exact 4.5 cents is kept; the total is shown rounded up to the cent


def test_a_refused_send_costs_nothing_and_is_recorded_as_failed(home, monkeypatch):
    capture(monkeypatch, Reply(401, {"error": {"message": "The API key in the request is missing or invalid."}}))
    monkeypatch.setattr("filmcrafter_engine.stills.after_still", lambda *a, **k: None)
    d = film(home / "film", "standard")
    R.enqueue(d, ["S01-01"], "byteplus", PRO, {}, kind="image")
    R.run(d, poll_every=0)
    j = R.Store(d).jobs[0]
    assert j["state"] == "failed" and KEY not in json.dumps(j) and budget.spent(d)["byteplus_usd"] == 0.0


# ---------------------------------------------------------------- where it is known: routing, names, key, health check

def test_byteplus_is_a_known_provider_with_its_own_key_and_the_seedream_families(monkeypatch):
    assert router.KEY_ENV["byteplus"] == "BYTEPLUS_KEY" and router.PROVIDER_NAMES["byteplus"] == "BytePlus" and "byteplus" in router.PROVIDER_ORDER
    assert {router.FAMILIES[f]["byteplus"] for f in ("seedream-pro", "seedream", "seedream-flash")} == {PRO, V45, FLASH}
    assert router.find_family("make it with seedream 5 pro") == "seedream-pro" and router.find_provider("on byteplus please") == "byteplus"
    monkeypatch.delenv("BYTEPLUS_KEY", raising=False)
    assert router.available("byteplus") is False
    monkeypatch.setenv("BYTEPLUS_KEY", KEY)
    assert router.available("byteplus") is True
    assert R.default_model("byteplus", "image") == PRO
    with pytest.raises(SystemExit):
        R.default_model("byteplus", "video")


def test_the_health_check_does_not_pretend_to_test_the_key(monkeypatch):
    assert "byteplus" in diagnostics.KEY_VARS
    for k in diagnostics.KEY_VARS.values():
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("BYTEPLUS_KEY", KEY)
    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("no network call for BytePlus"))
    row = next(r for r in diagnostics.run(None)["providers"] if r["provider"] == "byteplus")
    assert row["status"] == "unverified" and "first picture tests it" in row["message"] and row["error_kind"] is None and KEY not in json.dumps(row)


def test_queued_big_prices_and_the_budget_use_the_exact_estimate(home):
    jobs = [{"id": "a", "state": "queued", "provider": "byteplus", "model": PRO, "kind": "image", "estimate_usd": 0.09}]
    d = film(home / "film", "max")
    json.dump({"jobs": jobs}, open(os.path.join(d, "jobs.json"), "w"))
    assert routing.pending_usd(d) == 0.09
