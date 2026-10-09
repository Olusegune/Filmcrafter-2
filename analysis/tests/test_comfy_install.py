"""One-click ComfyUI: picking the build, the plan, a resumable checked download, unpacking (with the tar that ships with Windows), registering the copy. Nothing big is downloaded."""
import hashlib
import os
import shutil
import sys

import pytest
import requests

from filmcrafter_engine import comfy_install as CI, comfy_setup as CS

FIXTURE = os.path.join(os.path.dirname(__file__), "data", "portable_min.7z")
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="the unpacking tool is Windows' own tar")

ASSETS = [{"name": "ComfyUI_windows_portable_amd.7z", "size": 1_621_312_076, "browser_download_url": "https://github.com/Comfy-Org/ComfyUI/releases/download/v9.9/ComfyUI_windows_portable_amd.7z", "digest": "sha256:" + "a" * 64},
          {"name": "ComfyUI_windows_portable_intel.7z", "size": 1_436_509_991, "browser_download_url": "https://github.com/Comfy-Org/ComfyUI/releases/download/v9.9/ComfyUI_windows_portable_intel.7z", "digest": "sha256:" + "b" * 64},
          {"name": "ComfyUI_windows_portable_nvidia.7z", "size": 2_003_629_308, "browser_download_url": "https://github.com/Comfy-Org/ComfyUI/releases/download/v9.9/ComfyUI_windows_portable_nvidia.7z", "digest": "sha256:" + "C" * 64},
          {"name": "ComfyUI_windows_portable_nvidia_cu126.7z", "size": 1_895_335_518, "browser_download_url": "https://github.com/Comfy-Org/ComfyUI/releases/download/v9.9/ComfyUI_windows_portable_nvidia_cu126.7z"},
          {"name": "source.zip", "size": 5}]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------- choosing the build

def test_each_graphics_card_gets_its_own_build_and_the_checksum_is_read():
    n = CI.pick_asset(ASSETS, "nvidia")
    assert n["name"] == "ComfyUI_windows_portable_nvidia.7z" and n["url"] == "https://github.com/Comfy-Org/ComfyUI/releases/download/v9.9/ComfyUI_windows_portable_nvidia.7z" and n["sha256"] == "c" * 64      # the plain NVIDIA build, never the cu126 one
    assert CI.pick_asset(ASSETS, "amd")["name"].endswith("amd.7z") and CI.pick_asset(ASSETS, "intel")["size"] == 1_436_509_991


def test_a_missing_build_or_an_unknown_card_is_none_and_a_missing_checksum_is_tolerated():
    assert CI.pick_asset(ASSETS, "apple") is None and CI.pick_asset([], "nvidia") is None and CI.pick_asset([{"name": "x"}], "nvidia") is None
    assert CI.pick_asset(ASSETS[:4], "nvidia")["sha256"] == "c" * 64
    assert CI.pick_asset([{"name": "ComfyUI_windows_portable_amd.7z", "size": 1, "browser_download_url": "https://github.com/Comfy-Org/ComfyUI/releases/download/v9.9/a.7z"}], "amd")["sha256"] is None


def test_the_start_script_prefers_a_graphics_card_over_the_processor(tmp_path):
    for n in ("run_cpu.bat", "run_nvidia_gpu.bat", "notes.txt"):
        (tmp_path / n).write_text("")
    assert os.path.basename(CI.find_start_script(str(tmp_path))) == "run_nvidia_gpu.bat"
    (tmp_path / "run_nvidia_gpu.bat").unlink()
    assert os.path.basename(CI.find_start_script(str(tmp_path))) == "run_cpu.bat"
    (tmp_path / "run_cpu.bat").unlink()
    assert CI.find_start_script(str(tmp_path)) is None
    (tmp_path / "run_amd_gpu.bat").write_text("")
    assert os.path.basename(CI.find_start_script(str(tmp_path))) == "run_amd_gpu.bat"


def test_room_is_counted_for_the_download_the_folder_and_the_models_after():
    assert CI.space_needed_gb(2_003_629_308) == pytest.approx(2.0 * 4.4 + 4.0, abs=0.2)


# ---------------------------------------------------------------- the plan

class FakeResp:
    def __init__(self, body, status=200):
        self._b, self.status_code = body, status

    def json(self):
        return self._b

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


@pytest.fixture
def winplan(home, monkeypatch):
    from filmcrafter_engine import hardware as H
    monkeypatch.setattr(sys, "platform", "win32")
    gpu = {"name": "NVIDIA RTX 3060", "vram_gb": 12.0, "vendor": "nvidia"}
    monkeypatch.setattr(H, "report", lambda path=None: {"gpu": gpu, "ram_gb": 32.0})
    monkeypatch.setattr(CI.requests, "get", lambda url, **kw: FakeResp({"tag_name": "v9.9", "assets": ASSETS}))
    monkeypatch.setattr(CI, "_free_gb", lambda p: 500.0)
    return gpu


def test_a_good_plan_says_what_where_how_big_and_from_which_source(winplan, home):
    p = CI.plan()
    assert p["ok"] and p["vendor"] == "nvidia" and p["tag"] == "v9.9" and p["asset"]["name"].endswith("nvidia.7z")
    assert p["download_gb"] == 2.0 and p["dest"] == str(home / "FilmCrafter ComfyUI") and "github.com" in p["source"] and p["warnings"] == []


def test_a_small_card_or_a_non_nvidia_card_gets_an_honest_warning(winplan):
    winplan.update(vram_gb=4.0)
    assert any("video needs about 8 GB" in w for w in CI.plan()["warnings"])
    winplan.update(vendor="amd", vram_gb=16.0)
    p = CI.plan()
    assert p["asset"]["name"].endswith("amd.7z") and any("AMD" in w for w in p["warnings"])


def test_no_supported_card_means_no_install_and_says_why(winplan):
    winplan.update(vendor="other")
    p = CI.plan()
    assert not p["ok"] and "nothing to run on" in p["reason"]


def test_not_enough_disk_or_a_busy_folder_is_refused_before_anything_is_downloaded(winplan, home, monkeypatch):
    monkeypatch.setattr(CI, "_free_gb", lambda p: 5.0)
    assert "Not enough disk space" in CI.plan()["reason"]
    monkeypatch.setattr(CI, "_free_gb", lambda p: 500.0)
    busy = home / "mine"
    busy.mkdir()
    (busy / "photo.jpg").write_text("x")
    p = CI.plan(str(busy))
    assert not p["ok"] and "other files" in p["reason"]


def test_github_being_unreachable_or_having_no_build_is_explained(winplan, monkeypatch):
    monkeypatch.setattr(CI.requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError()))
    assert "Couldn't reach GitHub" in CI.plan()["reason"]
    monkeypatch.setattr(CI.requests, "get", lambda *a, **k: FakeResp({"tag_name": "v1", "assets": []}))
    p = CI.plan()
    assert not p["ok"] and "no Windows build" in p["reason"] and p["manual_url"]


def test_other_systems_are_pointed_to_the_official_app(home, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    p = CI.plan()
    assert not p["ok"] and "Mac" in p["reason"] and p["manual_url"].startswith("https://www.comfy.org")


def test_an_existing_install_is_recognised_instead_of_downloaded_again(winplan, home):
    root = home / "FilmCrafter ComfyUI" / "ComfyUI_windows_portable"
    (root / "ComfyUI").mkdir(parents=True)
    (root / "run_nvidia_gpu.bat").write_text("")
    p = CI.plan()
    assert p["installed"] and p["path"] == str(root) and p["start"].endswith("run_nvidia_gpu.bat")


# ---------------------------------------------------------------- the download

class Stream:
    def __init__(self, data, status=200, fail_after=None):
        self.data, self.status_code, self.fail_after = data, status, fail_after

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_content(self, n):
        for i in range(0, len(self.data), 4):
            if self.fail_after is not None and i >= self.fail_after:
                raise requests.ConnectionError()
            yield self.data[i:i + 4]


def asset_for(data: bytes, **kw):
    return {"name": "c.7z", "size": len(data), "url": "https://x/c.7z", "sha256": hashlib.sha256(data).hexdigest(), **kw}


def test_a_good_download_is_checked_and_kept_under_its_real_name(tmp_path, monkeypatch):
    data = b"0123456789abcdef" * 8
    monkeypatch.setattr(CI.requests, "get", lambda url, **kw: Stream(data))
    out = CI.download(asset_for(data), str(tmp_path / "dl"))
    assert open(out, "rb").read() == data and not os.path.exists(out + ".part")


def test_an_interrupted_download_resumes_from_where_it_stopped(tmp_path, monkeypatch):
    data = bytes(range(64))
    calls = []

    def fake_get(url, headers=None, **kw):
        calls.append((headers or {}).get("Range"))
        if len(calls) == 1:
            return Stream(data, fail_after=20)
        have = int(calls[-1].split("=")[1].rstrip("-"))
        return Stream(data[have:], status=206)
    monkeypatch.setattr(CI.requests, "get", fake_get)
    with pytest.raises(SystemExit) as e:
        CI.download(asset_for(data), str(tmp_path / "dl"))
    assert "carry on where it stopped" in str(e.value)
    out = CI.download(asset_for(data), str(tmp_path / "dl"))
    assert calls[1] and calls[1].startswith("bytes=") and open(out, "rb").read() == data


def test_a_download_that_does_not_match_the_checksum_is_thrown_away(tmp_path, monkeypatch):
    data = b"x" * 40
    monkeypatch.setattr(CI.requests, "get", lambda url, **kw: Stream(data))
    with pytest.raises(SystemExit) as e:
        CI.download(asset_for(data, sha256="0" * 64), str(tmp_path / "dl"))
    assert "didn't match GitHub's checksum" in str(e.value) and not os.listdir(tmp_path / "dl")


def test_a_short_download_and_a_refusal_are_reported_in_plain_words(tmp_path, monkeypatch):
    data = b"y" * 40
    monkeypatch.setattr(CI.requests, "get", lambda url, **kw: Stream(data[:20]))
    with pytest.raises(SystemExit) as e:
        CI.download(asset_for(data), str(tmp_path / "dl"))
    assert "stopped early" in str(e.value)
    monkeypatch.setattr(CI.requests, "get", lambda url, **kw: Stream(b"", status=403))
    with pytest.raises(SystemExit) as e:
        CI.download(asset_for(data), str(tmp_path / "dl2"))
    assert "403" in str(e.value)


def test_a_finished_download_is_not_fetched_twice(tmp_path, monkeypatch):
    data = b"z" * 16
    (tmp_path / "dl").mkdir()
    (tmp_path / "dl" / "c.7z").write_bytes(data)
    monkeypatch.setattr(CI.requests, "get", lambda *a, **k: pytest.fail("downloaded again"))
    assert CI.download(asset_for(data), str(tmp_path / "dl")).endswith("c.7z")


# ---------------------------------------------------------------- unpacking and the whole install

@windows_only
def test_the_windows_tar_unpacks_a_real_7z_into_a_portable_folder(tmp_path):
    assert CI.extractor() is not None
    CI.unpack(FIXTURE, str(tmp_path / "out"), os.path.getsize(FIXTURE))
    root = CI.find_portable(str(tmp_path / "out"))
    assert root and CI.find_start_script(root).endswith("run_nvidia_gpu.bat") and os.path.exists(os.path.join(root, "ComfyUI", "main.py"))


@windows_only
def test_a_damaged_archive_fails_in_plain_words(tmp_path):
    bad = tmp_path / "bad.7z"
    bad.write_bytes(b"not an archive")
    with pytest.raises(SystemExit) as e:
        CI.unpack(str(bad), str(tmp_path / "out"), 14)
    assert "Unpacking failed" in str(e.value) and "press Install again" in str(e.value)


def test_with_no_unpacker_it_says_what_to_install_and_keeps_the_download(tmp_path, monkeypatch):
    monkeypatch.setattr(CI, "extractor", lambda: None)
    with pytest.raises(SystemExit) as e:
        CI.unpack("a.7z", str(tmp_path), 1)
    assert "7-Zip" in str(e.value) and "download is kept" in str(e.value)


@windows_only
def test_install_end_to_end_registers_the_copy_and_makes_it_startable(winplan, home, monkeypatch):
    shutil.copy(FIXTURE, home / "pkg.7z")
    monkeypatch.setattr(CI, "download", lambda a, folder: str(home / "pkg.7z"))
    r = CI.install()
    assert r["installed"] and r["start"].endswith("run_nvidia_gpu.bat") and r["tag"] == "v9.9"
    assert CI.registry() == [r["path"]] and not os.path.exists(str(home / "FilmCrafter ComfyUI") + ".download")
    assert any(i["start"] == r["start"] for i in CS.installs())                      # Find ComfyUI can now start it
    assert CI.install()["installed"]                                                  # asking again is harmless


@windows_only
def test_a_failed_unpack_leaves_no_half_folder_and_keeps_the_download(winplan, home, monkeypatch):
    (home / "dl").mkdir()
    (home / "dl" / "c.7z").write_bytes(b"junk")
    monkeypatch.setattr(CI, "download", lambda a, folder: str(home / "dl" / "c.7z"))
    with pytest.raises(SystemExit):
        CI.install()
    assert not os.path.exists(home / "FilmCrafter ComfyUI") and os.path.exists(home / "dl" / "c.7z")


def test_install_refuses_when_the_plan_says_no(winplan, home, monkeypatch):
    monkeypatch.setattr(CI, "_free_gb", lambda p: 1.0)
    monkeypatch.setattr(CI, "download", lambda *a: pytest.fail("must not download"))
    with pytest.raises(SystemExit) as e:
        CI.install()
    assert "Not enough disk space" in str(e.value)


def test_the_registry_survives_junk_and_does_not_repeat_itself(home):
    assert CI.registry() == []
    CI.remember(r"C:\a")
    CI.remember(r"C:\A")
    CI.remember(r"C:\b")
    assert CI.registry() == [r"C:\A", r"C:\b"]
    open(CI._registry_path(), "w").write("{broken")
    assert CI.registry() == []


def test_finding_comfyui_also_recognises_amd_and_intel_portable_builds(home, monkeypatch):
    root = home / "ComfyUI_windows_portable"
    root.mkdir()
    (root / "run_amd_gpu.bat").write_text("")
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData" / "Local"))
    assert any(i["start"].endswith("run_amd_gpu.bat") for i in CS.installs())


# ---------------------------------------------------------------- what it will and will not download

def test_only_files_from_comfyuis_own_github_releases_are_ever_downloaded():
    evil = [{"name": "ComfyUI_windows_portable_nvidia.7z", "size": 5, "browser_download_url": "https://evil.example/ComfyUI_windows_portable_nvidia.7z", "digest": "sha256:" + "a" * 64}]
    assert CI.pick_asset(evil, "nvidia") is None
    lookalike = [{**evil[0], "browser_download_url": "https://github.com.evil.example/Comfy-Org/ComfyUI/releases/download/v1/x.7z"}]
    assert CI.pick_asset(lookalike, "nvidia") is None
    assert CI.pick_asset([{**evil[0], "browser_download_url": None}], "nvidia") is None
    old = [{**evil[0], "browser_download_url": "https://github.com/comfyanonymous/ComfyUI/releases/download/v1/ComfyUI_windows_portable_nvidia.7z"}]
    assert CI.pick_asset(old, "nvidia")["url"].startswith("https://github.com/comfyanonymous/")


def test_a_build_with_no_published_checksum_is_not_installed(winplan, monkeypatch):
    nocheck = [{**a, "digest": None} for a in ASSETS]
    monkeypatch.setattr(CI.requests, "get", lambda url, **kw: FakeResp({"tag_name": "v9.9", "assets": nocheck}))
    p = CI.plan()
    assert not p["ok"] and "checksum" in p["reason"] and p["manual_url"]
