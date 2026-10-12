"""Local AI (Ollama / LM Studio) through a fake OpenAI-compatible server: structured output, fallbacks,
reasoning-trace stripping, model listing, and a real engine (the Choreography Engine) running on it."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from filmcrafter_engine import llm as L


class Fake(BaseHTTPRequestHandler):
    schema_ok = True     # does this "server" support response_format json_schema?
    reply = "{}"
    calls = []

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path.endswith("/models"):
            return self._json({"data": [{"id": "qwen2.5:14b"}, {"id": "llava:13b"}, {"id": "deepseek-r1:14b"}]})
        self._json({}, 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        Fake.calls.append(body)
        rf = (body.get("response_format") or {}).get("type")
        if rf == "json_schema" and not Fake.schema_ok:
            return self._json({"error": {"message": "response_format json_schema not supported"}}, 400)
        self._json({"id": "x", "object": "chat.completion", "created": 0, "model": body["model"],
                    "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": Fake.reply}}]})


@pytest.fixture
def server(monkeypatch, tmp_path):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(L, "CONFIG", str(tmp_path / "llm.json"))
    Fake.calls, Fake.schema_ok = [], True
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    yield url
    srv.shutdown()


def test_settings_validate_and_default(server, tmp_path):
    assert L.config()["provider"] == "openai" and not L.is_local()
    with pytest.raises(SystemExit):
        L.save({"provider": "ollama", "base_url": server})            # no model chosen
    c = L.save({"provider": "ollama", "base_url": server, "model": "qwen2.5:14b"})
    assert c["base_url"] == server + "/v1" and L.is_local()


def test_model_listing_flags_vision_models(server):
    r = L.list_models({"provider": "lmstudio", "base_url": server})
    assert r["models"] == ["deepseek-r1:14b", "llava:13b", "qwen2.5:14b"] and r["vision_capable"] == ["llava:13b"]


def test_structured_output_and_think_stripping(server):
    L.save({"provider": "ollama", "base_url": server, "model": "deepseek-r1:14b"})
    Fake.reply = '<think>let me plan the shot…</think>\n```json\n{"shot": "dawn over Lagos", "energy": 6}\n```'
    r = L.test({})
    assert r["sample"] == {"shot": "dawn over Lagos", "energy": 6} and r["model"] == "deepseek-r1:14b"
    assert Fake.calls[0]["response_format"]["type"] == "json_schema"


def test_falls_back_to_json_mode_when_schema_unsupported(server):
    L.save({"provider": "lmstudio", "base_url": server, "model": "qwen2.5:14b"})
    Fake.schema_ok, Fake.reply = False, '{"shot": "a wide", "energy": 3}'
    assert L.test({})["sample"]["energy"] == 3
    assert Fake.calls[-1]["response_format"]["type"] == "json_object" and "JSON Schema" in Fake.calls[-1]["messages"][0]["content"]


def test_vision_review_needs_a_vision_model(server):
    L.save({"provider": "ollama", "base_url": server, "model": "qwen2.5:14b"})
    with pytest.raises(SystemExit, match="see images"):
        L.local_model(L.client(), vision=True)
    L.save({"provider": "ollama", "base_url": server, "model": "qwen2.5:14b", "vision_model": "llava:13b"})
    assert L.local_model(L.client(), vision=True) == "llava:13b"


def test_offline_local_server_is_explained(monkeypatch, tmp_path):
    from filmcrafter_engine.director import openai_error
    monkeypatch.setattr(L, "CONFIG", str(tmp_path / "llm.json"))
    L.save({"provider": "ollama", "base_url": "http://127.0.0.1:9", "model": "qwen2.5:14b"})
    assert "Ollama isn't answering" in openai_error(Exception("APIConnectionError: Connection error."))
