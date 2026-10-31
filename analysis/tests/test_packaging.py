"""The installed app only has the engine files the installer lists. A data file the engine reads that is not on that list works on the development machine and fails in the installed app (the presets
library once did exactly this). This test makes that impossible: every file in the engine folder is either a Python file (bundled by the pattern) or named in the installer's resource list."""
import json
import os

HERE = os.path.dirname(__file__)
ENGINE = os.path.join(HERE, "..", "filmcrafter_engine")
CONF = os.path.join(HERE, "..", "..", "src-tauri", "tauri.conf.json")


def resources():
    return json.load(open(CONF, encoding="utf-8"))["bundle"]["resources"]


def test_every_data_file_in_the_engine_folder_is_in_the_installer():
    listed = {os.path.normpath(os.path.join(os.path.dirname(CONF), k)) for k in resources() if "*" not in k}
    wildcard = "../analysis/filmcrafter_engine/*.py" in resources()
    missing = []
    for name in sorted(os.listdir(ENGINE)):
        path = os.path.normpath(os.path.join(ENGINE, name))
        if os.path.isdir(path) or name.endswith((".pyc", ".pyo")) or name == "__pycache__":
            continue
        if name.endswith(".py") and wildcard:
            continue
        if path not in listed:
            missing.append(name)
    assert not missing, f"not in src-tauri/tauri.conf.json resources, so missing from the installed app: {missing}"


def test_every_resource_the_installer_lists_exists():
    base = os.path.dirname(CONF)
    for src in resources():
        if "*" in src or src.startswith("icons/"):
            continue
        assert os.path.exists(os.path.normpath(os.path.join(base, src))), src


def test_the_preset_thumbnails_the_library_shows_are_frontend_files_the_build_carries():
    pub = os.path.join(HERE, "..", "..", "public")
    builtin = json.load(open(os.path.join(ENGINE, "presets_builtin.json"), encoding="utf-8"))["presets"]
    for p in builtin:
        if p.get("thumbnail"):
            assert os.path.isfile(os.path.join(pub, p["thumbnail"])), p["id"]
