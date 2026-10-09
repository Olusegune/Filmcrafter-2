"""Local AI: hardware reading, which models fit, tests of Ollama / LM Studio, ComfyUI health and plain-words errors."""
import base64
import zlib

import pytest

from filmcrafter_engine import comfy, comfy_setup as CS, hardware as H, localmodels as LM


def hw(kind="gpu", model_gb=12, ram=32):
    return {"kind": kind, "model_gb": model_gb, "ram_gb": ram}


# ---------------------------------------------------------------- hardware

def test_nvidia_smi_output_is_read_in_gigabytes():
    g = H.parse_nvidia_smi("NVIDIA GeForce RTX 3060, 12288, 1024\nNVIDIA GeForce RTX 4090, 24564, 0\n")
    assert [x["name"] for x in g] == ["NVIDIA GeForce RTX 3060", "NVIDIA GeForce RTX 4090"]
    assert g[0]["vram_gb"] == 12.0 and g[0]["used_gb"] == 1.0 and g[1]["vram_gb"] == 24.0


@pytest.mark.parametrize("text", ["", "\n", "garbage", "name only", "a, notanumber, 1"])
def test_nvidia_smi_noise_gives_no_gpus(text):
    assert H.parse_nvidia_smi(text) == []


def test_fit_on_a_graphics_card():
    h = hw("gpu", 12, 32)
    assert H.fit(6.0, h) == "great"            # 6 * 1.25 = 7.5 <= 12
    assert H.fit(9.3, h) == "great"            # 11.6 <= 12
    assert H.fit(15.0, h) == "slow"            # 18.75: spills into memory, still runs
    assert H.fit(60.0, h) == "too_big"
    assert H.fit(0, h) == "unknown"


def test_fit_with_a_small_card_and_with_no_card():
    assert H.fit(6.0, hw("gpu", 6, 16)) == "slow"
    assert H.fit(6.0, hw("gpu", 4, 6)) == "too_big"
    cpu = hw("cpu", 6, 16)
    assert H.fit(4.9, cpu) == "slow" and H.fit(15.0, cpu) == "too_big"
    assert H.fit(6.0, hw("unified", 20, 32)) == "great"


def test_report_always_has_a_plain_summary_and_a_budget(monkeypatch):
    monkeypatch.setattr(H, "_gpus", lambda: [])
    monkeypatch.setattr(H, "_ram_gb", lambda: 16.0)
    r = H.report()
    assert r["kind"] == "cpu" and r["model_gb"] == 6.4 and "slowly" in r["summary"]
    monkeypatch.setattr(H, "_gpus", lambda: [{"name": "NVIDIA RTX 3060", "vram_gb": 12.0, "used_gb": 0, "vendor": "nvidia"}])
    r = H.report()
    assert r["kind"] == "gpu" and r["model_gb"] == 12.0 and "12 GB of video memory" in r["summary"]
    monkeypatch.setattr(H, "_gpus", lambda: [{"name": "Apple M2", "vram_gb": None, "used_gb": 0, "vendor": "apple"}])
    assert H.report()["kind"] == "unified"


def test_a_card_whose_memory_cannot_be_read_still_gives_an_answer(monkeypatch):
    monkeypatch.setattr(H, "_gpus", lambda: [{"name": "AMD Radeon RX 6700", "vram_gb": None, "used_gb": 0, "vendor": "amd"}])
    monkeypatch.setattr(H, "_ram_gb", lambda: 32.0)
    r = H.report()
    assert r["kind"] == "cpu" and "AMD Radeon RX 6700" in r["summary"]


# ---------------------------------------------------------------- the model list

def test_the_catalogue_is_sane():
    names = [r["name"] for r in LM.RECOMMENDED]
    assert len(names) == len(set(names)) and len(names) >= 10
    for r in LM.RECOMMENDED:
        assert r["role"] in LM.ROLE_WORDS and r["size_gb"] > 0 and r["why"]
    assert {r["role"] for r in LM.RECOMMENDED} == {"both", "planning", "vision"}
    assert any(r["size_gb"] <= 3.5 and r["role"] == "both" for r in LM.RECOMMENDED), "weak computers need a small model that plans and sees"


def test_status_marks_fit_and_puts_what_fits_first(monkeypatch):
    monkeypatch.setattr(LM, "_ollama", lambda: {"running": True, "models": [{"name": "qwen2.5vl:7b", "size_gb": 6.0, "vision": True}]})
    monkeypatch.setattr(LM, "_lmstudio", lambda: {"running": False, "models": []})
    monkeypatch.setattr(LM, "loaded", lambda: [])
    monkeypatch.setattr(H, "report", lambda path=None: {**hw("gpu", 8, 16), "summary": "x", "disk_free_gb": 100})
    monkeypatch.setattr(comfy, "check", lambda: {"connected": False, "workflows": []})
    s = LM.status()
    fits = [r["fit"] for r in s["recommended"]]
    assert fits == sorted(fits, key=lambda f: {"great": 0, "slow": 1, "unknown": 2, "too_big": 3}[f])
    assert next(r for r in s["recommended"] if r["name"] == "qwen2.5vl:7b")["installed"] is True
    assert next(r for r in s["recommended"] if r["name"] == "gemma3:27b")["fit"] in ("slow", "too_big")
    assert s["ollama"]["models"][0]["fit"] == "great" and s["hardware"]["summary"] == "x"


def test_a_download_that_will_not_fit_the_disk_is_refused_before_it_starts(monkeypatch):
    monkeypatch.setattr(LM, "_ollama", lambda: {"running": True, "models": []})
    monkeypatch.setattr(H, "report", lambda path=None: {"disk_free_gb": 5.0})
    called = []
    monkeypatch.setattr(LM.requests, "post", lambda *a, **k: called.append(1))
    with pytest.raises(SystemExit) as e:
        LM.pull("gemma3:27b")
    assert "Not enough disk space" in str(e.value) and not called


# ---------------------------------------------------------------- the test button

class Resp:
    def __init__(self, status, body):
        self.status_code, self._b, self.text = status, body, str(body)

    def json(self):
        return self._b


def chat(answer):
    return Resp(200, {"choices": [{"message": {"content": answer}}]})


def test_the_test_picture_is_a_real_png_with_red_left_and_blue_right():
    raw = base64.b64decode(LM._test_png())
    assert raw[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
    idat = raw[raw.index(b"IDAT") + 4:]
    pix = zlib.decompress(idat[:int.from_bytes(raw[raw.index(b"IDAT") - 4:raw.index(b"IDAT")], "big")])
    assert pix[1:4] == bytes([220, 40, 40]) and pix[1 + 32 * 3:4 + 32 * 3] == bytes([40, 60, 220])


def test_planning_test_reports_the_answer_and_the_time(monkeypatch):
    monkeypatch.setattr("filmcrafter_engine.llm.config", lambda: {"provider": "ollama", "model": "qwen3:8b", "vision_model": ""})
    seen = {}
    monkeypatch.setattr(LM.requests, "post", lambda url, json=None, timeout=0: seen.update(url=url, body=json) or chat("ready"))
    r = LM.test("ollama")
    assert r["ok"] and r["model"] == "qwen3:8b" and r["answer"] == "ready" and "11434" in seen["url"]
    assert isinstance(seen["body"]["messages"][0]["content"], str)


def test_vision_test_sends_the_picture_and_checks_the_colours(monkeypatch):
    monkeypatch.setattr("filmcrafter_engine.llm.config", lambda: {"provider": "ollama", "model": "a", "vision_model": "qwen2.5vl:7b"})
    seen = {}
    monkeypatch.setattr(LM.requests, "post", lambda url, json=None, timeout=0: seen.update(body=json) or chat("Red on the left and blue on the right"))
    r = LM.test("ollama", vision=True)
    assert r["saw"] is True and r["model"] == "qwen2.5vl:7b"
    assert any(p.get("type") == "image_url" for p in seen["body"]["messages"][0]["content"])
    monkeypatch.setattr(LM.requests, "post", lambda url, json=None, timeout=0: chat("I can't see any image"))
    r = LM.test("ollama", vision=True)
    assert r["saw"] is False and "may not be able to see" in r["note"]


def test_test_errors_are_in_plain_words(monkeypatch):
    monkeypatch.setattr("filmcrafter_engine.llm.config", lambda: {"provider": "ollama", "model": "m", "vision_model": ""})
    monkeypatch.setattr(LM.requests, "post", lambda *a, **k: (_ for _ in ()).throw(LM.requests.ConnectionError()))
    with pytest.raises(SystemExit) as e:
        LM.test("ollama")
    assert "isn't running" in str(e.value)
    monkeypatch.setattr(LM.requests, "post", lambda *a, **k: Resp(404, "model 'm' not found"))
    with pytest.raises(SystemExit) as e:
        LM.test("ollama")
    assert "isn't downloaded" in str(e.value)
    monkeypatch.setattr("filmcrafter_engine.llm.config", lambda: {"provider": "ollama", "model": "", "vision_model": ""})
    with pytest.raises(SystemExit) as e:
        LM.test("ollama")
    assert "Choose a model" in str(e.value)


def test_friendly_server_errors():
    assert "ran out of memory" in LM.friendly("CUDA error: out of memory")
    assert "no model loaded" in LM.friendly("No models loaded", "lmstudio").lower()
    assert LM.friendly("something odd") == "something odd"


def test_unload_asks_ollama_to_forget_the_model(monkeypatch):
    sent = {}
    monkeypatch.setattr(LM.requests, "post", lambda url, json=None, timeout=0: sent.update(url=url, body=json))
    monkeypatch.setattr(LM, "status", lambda: {"ok": 1})
    assert LM.unload("qwen2.5vl:7b") == {"ok": 1}
    assert sent["body"] == {"model": "qwen2.5vl:7b", "keep_alive": 0} and sent["url"].endswith("/api/generate")


# ---------------------------------------------------------------- ComfyUI in plain words

@pytest.mark.parametrize("raw,needle", [
    ("CUDA out of memory. Tried to allocate 2.00 GiB", "ran out of memory"),
    ("Value not in list: ckpt_name: 'x.safetensors' not in [...]", "isn't installed"),
    ("invalid prompt: missing_node_type Wan22ImageToVideoLatent", "missing a node"),
    ("required_input_missing: clip", "isn't connected"),
    ("Connection aborted.", "stopped answering"),
])
def test_comfy_errors_say_what_to_do(raw, needle):
    out = comfy.friendly(raw)
    assert needle in out and raw[:40] in out


def test_unknown_comfy_errors_pass_through_and_empty_is_safe():
    assert comfy.friendly("something unrelated") == "something unrelated"
    assert comfy.friendly(None) == ""


def test_health_advice_is_specific():
    t = [{"id": "x", "title": "Video (Wan 2.2)", "ready": False, "missing": ["wan2.2_vae.safetensors (vae)"]}]
    a = CS.advise(6.0, 5.0, t)
    assert any("8 GB" in x or "tight" in x for x in a) and any("Download" in x and "wan2.2_vae" in x for x in a)
    assert any("holding it" in x for x in CS.advise(12.0, 1.5, []))
    assert any("Everything is ready" in x for x in CS.advise(12.0, 10.0, [{"id": "k", "title": "K", "ready": True, "missing": []}]))
    assert CS.advise(0, 0, []) == []


def test_health_when_comfy_is_not_there(monkeypatch):
    monkeypatch.setattr(CS, "_get", lambda *a, **k: None)
    h = CS.health("http://127.0.0.1:9")
    assert h["connected"] is False and "Find ComfyUI" in h["advice"][0]


def test_comfy_test_refuses_without_an_image_model(monkeypatch):
    monkeypatch.setattr(CS, "health", lambda url=None: {"connected": True, "templates": [{"id": "filmcrafter-keyframes", "ready": False}], "advice": []})
    with pytest.raises(SystemExit) as e:
        CS.test("http://127.0.0.1:8188")
    assert "no image model" in str(e.value).lower()
