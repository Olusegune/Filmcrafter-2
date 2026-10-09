"""ComfyUI provider against a fake local ComfyUI server (no real ComfyUI; this proves the wiring, not a real model)."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PIL import Image

from pulseframe_analysis import comfy as C
from pulseframe_analysis import render as R
from pulseframe_analysis import router

WORKFLOW = {
    "3": {"class_type": "KSampler", "inputs": {"seed": "{{seed}}", "positive": ["6", 0], "negative": ["7", 0]}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}"}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{negative}}, blurry"}},
    "10": {"class_type": "LoadImage", "inputs": {"image": "{{image}}"}},
    "20": {"class_type": "WanImageToVideo", "inputs": {"width": "{{width}}", "height": "{{height}}", "length": "{{frames}}"}},
    "30": {"class_type": "SaveVideo", "inputs": {"filename_prefix": "pf"}},
}


class Fake(BaseHTTPRequestHandler):
    prompts = []
    uploads = []

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path == "/system_stats":
            return self._json({"devices": [{"name": "Fake GPU"}]})
        if self.path == "/queue":
            return self._json({"queue_pending": [], "queue_running": []})
        if self.path.startswith("/history/"):
            rid = self.path.split("/")[-1]
            return self._json({rid: {"status": {"status_str": "success"},
                                     "outputs": {"30": {"videos": [{"filename": "pf_0001.mp4", "subfolder": "", "type": "output"}]}}}})
        if self.path.startswith("/view"):
            b = b"\0" * 128
            self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
            return
        self._json({}, 404)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/upload/image":
            Fake.uploads.append(len(body))
            return self._json({"name": "start.png", "subfolder": "", "type": "input"})
        if self.path == "/prompt":
            Fake.prompts.append(json.loads(body)["prompt"])
            return self._json({"prompt_id": f"p{len(Fake.prompts)}"})
        self._json({}, 404)


@pytest.fixture
def server(monkeypatch, tmp_path):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("COMFYUI_URL", f"http://127.0.0.1:{srv.server_address[1]}")
    monkeypatch.setattr(C, "HOME", str(tmp_path / "comfy"))
    monkeypatch.setattr(C, "FLOWS", str(tmp_path / "comfy" / "workflows"))
    monkeypatch.setattr(C, "CONFIG", str(tmp_path / "comfy" / "config.json"))
    Fake.prompts, Fake.uploads = [], []
    wf = tmp_path / "wan i2v.json"
    wf.write_text(json.dumps(WORKFLOW))
    C.add_workflow(str(wf))
    yield srv
    srv.shutdown()


@pytest.fixture
def project(tmp_path):
    d = tmp_path / "proj"
    (d / "assets" / "refs").mkdir(parents=True)
    Image.new("RGB", (64, 36)).save(d / "assets" / "refs" / "sege.png")
    shot = {"id": "S01-01", "scene": 1, "start": 0.0, "end": 3.0, "beats": ["A man waits on a platform."], "performers": ["Sege"],
            "framing": "medium", "camera_moves": [], "source_shots": ["S01-01"]}
    (d / "production.json").write_text(json.dumps({"meta": {}, "characters": [], "scenes": [
        {"number": 1, "heading": "EXT. PLATFORM", "start": 0, "end": 3, "notes": {}, "shots": [shot]}]}))
    (d / "project.json").write_text(json.dumps({"title": "T", "aspect_ratio": "2.39:1", "look": {"style": "auto"},
                                                "references": {"cast": {"Sege": "assets/refs/sege.png"}}}))
    (d / "songmap.json").write_text(json.dumps({"duration": 3.0, "lyrics": [], "sections": [], "beats": []}))
    return str(d)


def test_workflow_is_listed_with_its_placeholders(server):
    w = C.workflows()
    assert w[0]["model"] == "wan-i2v" and w[0]["kind"] == "video" and "prompt" in w[0]["placeholders"]
    assert C.check()["connected"] and C.check()["device"] == "Fake GPU"


def test_rejects_ui_format_workflows(tmp_path, server):
    bad = tmp_path / "ui.json"
    bad.write_text(json.dumps({"nodes": [], "links": []}))
    with pytest.raises(SystemExit):
        C.add_workflow(str(bad))


def test_full_render_through_comfyui(server, project, monkeypatch):
    monkeypatch.setattr(R, "_review", lambda d, store, j: None)
    R.enqueue(project, ["S01-01"], "comfyui", None, {"seed": 42})
    R.run(project, poll_every=0)
    j = R.Store(project).jobs[0]
    assert j["state"] == "ready" and j["output"].endswith(".mp4") and j["cost"] == 0, j
    g = Fake.prompts[0]
    assert "waits on a platform" in g["6"]["inputs"]["text"] and g["3"]["inputs"]["seed"] == 42
    assert g["10"]["inputs"]["image"] == "start.png" and Fake.uploads
    w, h = g["20"]["inputs"]["width"], g["20"]["inputs"]["height"]
    assert w == 1024 and abs(w / h - 2.39) < 0.1 and w % 16 == 0 and h % 16 == 0
    assert g["20"]["inputs"]["length"] == round(3.5 * 24) + 1  # shot + half-second trim handle, not a whole-second round-up
    assert g["7"]["inputs"]["text"].endswith(", blurry")


def test_prompt_goes_to_positive_node_without_placeholders():
    g = {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": "old negative"}},
         "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "old positive"}},
         "3": {"class_type": "KSampler", "inputs": {"positive": ["2", 0], "negative": ["1", 0]}}}
    out = C.fill(g, {"prompt": "new"}, None, {"max_side": 512, "fps": 24})
    assert out["2"]["inputs"]["text"] == "new" and out["1"]["inputs"]["text"] == "old negative"


def test_router_by_name(monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setenv("KIE_KEY", "k")
    r = router.route(router.find_family("regenerate shot 12 using Kling"))
    assert r["provider"] == "kie" and r["model"] == "kling-2.6/image-to-video" and r["verified"]
    with pytest.raises(SystemExit):
        router.route("ltx")  # LTX is only on fal: tells you which key is needed
    assert router.find_provider("render it on fal") == "fal"
