import json

import pytest

from filmcrafter_engine import comfy, comfy_setup as CS


def info(ckpts=(), unets=(), clips=(), vaes=(), nodes_ok=True):
    i = {"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [list(ckpts)]}}},
         "UNETLoader": {"input": {"required": {"unet_name": [list(unets)]}}},
         "CLIPLoader": {"input": {"required": {"clip_name": [list(clips)]}}},
         "VAELoader": {"input": {"required": {"vae_name": [list(vaes)]}}}}
    if nodes_ok:
        i.update({n: {} for n in ("Wan22ImageToVideoLatent", "CreateVideo", "SaveVideo", "ModelSamplingSD3")})
    return i


def test_plan_ready_when_models_present():
    p = {x["id"]: x for x in CS.plan(info(["juggernautXL_v9.safetensors"], ["wan2.2_ti2v_5B_fp16.safetensors"],
                                          ["umt5_xxl_fp8_e4m3fn_scaled.safetensors"], ["wan2.2_vae.safetensors"]))}
    assert p["filmcrafter-keyframes"]["ready"] and p["filmcrafter-keyframes"]["uses"] == "juggernautXL_v9.safetensors"
    v = p["filmcrafter-video-wan22"]
    assert v["ready"] and v["graph"]["1"]["inputs"]["unet_name"] == "wan2.2_ti2v_5B_fp16.safetensors"
    assert v["graph"]["4"]["inputs"]["image"] == "{{image}}" and v["graph"]["12"]["class_type"] == "SaveVideo"


def test_plan_names_missing_files_and_old_comfy():
    p = {x["id"]: x for x in CS.plan(info(nodes_ok=False))}
    assert not p["filmcrafter-keyframes"]["ready"] and "checkpoint" in p["filmcrafter-keyframes"]["missing"][0]
    miss = " ".join(p["filmcrafter-video-wan22"]["missing"])
    assert "newer ComfyUI" in miss and "wan2.2_ti2v_5B" in miss and "umt5" in miss and "wan2.2_vae" in miss


def test_templates_fill_into_runnable_graphs():
    g = CS.wan22_template("u", "c", "v")
    filled = comfy.fill(g, {"prompt": "a hug", "aspect_ratio": "21:9", "duration": 5}, "kf.png", {"max_side": 1024, "fps": 24})
    assert filled["5"]["inputs"]["text"] == "a hug" and filled["4"]["inputs"]["image"] == "kf.png"
    assert filled["8"]["inputs"]["length"] == 121 and (filled["8"]["inputs"]["length"] - 1) % 4 == 0
    assert isinstance(filled["8"]["inputs"]["width"], int) and comfy._kind(g) == "video"
    assert comfy._kind(CS.still_template("x")) == "image"


def test_setup_writes_only_ready_templates(tmp_path, monkeypatch):
    monkeypatch.setattr(comfy, "FLOWS", str(tmp_path / "flows"))
    monkeypatch.setattr(comfy, "CONFIG", str(tmp_path / "c.json"))
    monkeypatch.setattr(comfy, "HOME", str(tmp_path))
    class R:
        def json(self):
            return info(["sdxl.safetensors"])
    monkeypatch.setattr(CS, "_get", lambda url, timeout=2.0: R())
    res = CS.setup("http://127.0.0.1:8000")
    assert [w["model"] for w in res["workflows"]] == ["filmcrafter-keyframes"]
    assert {t["id"]: t["ready"] for t in res["templates"]} == {"filmcrafter-keyframes": True, "filmcrafter-video-wan22": False}


def test_detect_nothing_running_and_start_is_restricted(monkeypatch):
    monkeypatch.setattr(CS, "_get", lambda url, timeout=2.0: None)
    monkeypatch.setattr(CS, "installs", lambda: [])
    assert CS.detect()["running"] == []
    with pytest.raises(SystemExit):
        CS.start("C:/Windows/System32/cmd.exe")


def test_downloads_plan_puts_files_in_comfys_folders(tmp_path, monkeypatch):
    folders = {"checkpoints": [str(tmp_path / "ck")], "diffusion_models": [str(tmp_path / "dm")], "text_encoders": [str(tmp_path / "te")],
               "vae": [str(tmp_path / "vae")]}
    class R:
        def json(self):
            return folders
    monkeypatch.setattr(CS, "_get", lambda url, timeout=2.0: R())
    (tmp_path / "vae").mkdir()
    (tmp_path / "vae" / "wan2.2_vae.safetensors").write_bytes(b"x")   # already there: not downloaded again
    p = CS.downloads(["filmcrafter-keyframes", "filmcrafter-video-wan22"], "http://x")
    names = {f["name"] for f in p["files"]}
    assert names == {"sd_xl_base_1.0.safetensors", "wan2.2_ti2v_5B_fp16.safetensors", "umt5_xxl_fp8_e4m3fn_scaled.safetensors"}
    assert p["gb"] == pytest.approx(23.7, abs=0.1)


def test_desktop_port_lock_is_read(tmp_path, monkeypatch):
    lock = tmp_path / "Comfy Desktop" / "port-locks"
    lock.mkdir(parents=True)
    (lock / "port-8765.json").write_text("{}")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert CS._desktop_ports() == [8765]
