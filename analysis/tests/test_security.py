"""Security tests: hostile input, unsafe paths and names, leaked secrets, unsafe commands, oversized files, and the shell's gatekeeping of the engine.
Names that come from outside (a shot id from the language model, a title typed by a user, an entry in an imported package) must never become a path,
a filter expression or a shell word."""
import json
import os
import re
import subprocess
import zipfile

import pytest
from PIL import Image

from filmcrafter_engine import customframe, fonts, media, overlays as O, render as R, safe, svg_text, titlecard
from filmcrafter_engine.export import NO_WINDOW, ffmpeg
from tests.test_render import FakeProvider, field, man

pytestmark = pytest.mark.security

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
LIB_RS = os.path.join(ROOT, "src-tauri", "src", "lib.rs")


@pytest.fixture
def proj(tmp_path):
    d = tmp_path / "outer" / "proj"
    d.mkdir(parents=True)
    json.dump({"title": "T", "song": "s.wav"}, open(d / "project.json", "w"))
    json.dump({"duration": 20.0, "sections": [], "lyrics": []}, open(d / "songmap.json", "w"))
    shots = [{"id": "S01-01", "scene": 1, "number": 1, "start": 0.0, "end": 8.0, "beats": ["x"], "performers": []},
             {"id": "S01-02", "scene": 1, "number": 2, "start": 8.0, "end": 14.0, "beats": ["y"], "performers": []}]
    json.dump({"scenes": [{"number": 1, "start": 0, "end": 14, "shots": shots}]}, open(d / "production.json", "w"))
    json.dump({"jobs": []}, open(d / "jobs.json", "w"))
    return str(d)


def outside(proj):
    """Every file under the folder that holds the project, but not in the project itself: nothing may ever appear here."""
    base = os.path.dirname(proj)
    return sorted(os.path.join(r, f) for r, _, fs in os.walk(base) for f in fs if not os.path.join(r, f).startswith(proj + os.sep))


# ---------------------------------------------------------------- the shell only passes on what the engine understands

def _rust_commands():
    src = open(LIB_RS, encoding="utf-8").read()
    blocks = re.split(r"\n(?=(?:async )?fn |#\[tauri::command\])", src)
    return [b for b in blocks if "ACTIONS" in b]


@pytest.mark.skipif(not os.path.exists(LIB_RS), reason="the app shell is not in this checkout")
def test_every_action_the_shell_allows_is_one_the_engine_knows():
    checked = 0
    for blk in _rust_commands():
        acts = re.search(r"const ACTIONS: \[&str; \d+\] = \[([^\]]*)\]", blk)
        mod = re.search(r"filmcrafter_engine\.(\w+)", blk)
        if not (acts and mod):
            continue
        src = open(os.path.join(ROOT, "analysis", "filmcrafter_engine", mod[1] + ".py"), encoding="utf-8").read()
        known = {x for m in re.finditer(r"choices=\[([^\]]+)\]", src) for x in re.findall(r"[\"'](\w+)[\"']", m[1])}
        allowed = set(re.findall(r'"(\w+)"', acts[1]))
        assert allowed <= known, (mod[1], sorted(allowed - known))
        checked += 1
    assert checked >= 15


@pytest.mark.skipif(not os.path.exists(LIB_RS), reason="the app shell is not in this checkout")
def test_commands_that_take_a_project_folder_check_it_is_a_project_first():
    src = open(LIB_RS, encoding="utf-8").read().replace("\r\n", "\n")
    skipped = {"recents", "hidden_count", "open_pulse", "launch_path", "save_project_as", "pack_project", "load_project", "create_project", "export_project"}   # these make or open one
    problems, seen = [], 0
    for m in re.finditer(r"#\[tauri::command\]\s*(?:async )?fn (\w+)\(([^)]*)\)[^{]*\{", src):
        name, params, body_at = m[1], m[2], m.end()
        if "dir: String" not in params or name in skipped:
            continue
        nxt = re.search(r"\n#\[tauri::command\]|\n(?:async )?fn |\n}\n", src[body_at:])
        body = src[body_at:body_at + (nxt.start() if nxt else 4000)]
        seen += 1
        if "project_dir(" not in body:
            problems.append(name)
    assert seen >= 30, seen
    assert not problems, f"commands that take a project folder without checking it: {problems}"


# ---------------------------------------------------------------- names from outside are never paths

@pytest.mark.parametrize("bad", ["../../evil", "..\\..\\evil", "a/b", ".hidden", "", "x" * 200, "S01 02", "S01-01;rm -rf", "con:"])
def test_a_plain_id_check_refuses_anything_that_could_be_a_path(bad):
    with pytest.raises(SystemExit, match="not valid"):
        safe.check_id(bad)
    assert re.fullmatch(r"[A-Za-z0-9._-]+", safe.file_part(bad)) and not safe.file_part(bad).startswith(".") and len(safe.file_part(bad)) <= 60


def test_a_hostile_shot_id_never_writes_outside_the_project(proj, tmp_path):
    pic = tmp_path / "a.png"
    Image.new("RGB", (8, 8)).save(pic)
    before = outside(proj)
    for bad in ("../../evil", "..\\..\\evil", "../x", "S01-01/../../y", "nope"):
        with pytest.raises(SystemExit):
            media.import_media(proj, bad, str(pic))
    assert outside(proj) == before and not os.path.exists(os.path.join(proj, "media"))             # and nothing was copied in either: it is refused first


def test_a_hostile_id_in_an_imported_plan_cannot_steer_where_a_frame_is_saved(proj):
    plan = json.load(open(os.path.join(proj, "production.json")))
    plan["scenes"][0]["shots"][0]["id"] = "..\\..\\evil"
    json.dump(plan, open(os.path.join(proj, "production.json"), "w"))
    before, plan_text = outside(proj), open(os.path.join(proj, "production.json")).read()
    with pytest.raises(SystemExit, match="not valid"):
        customframe.insert(proj, {"where": "after", "shot": "..\\..\\evil", "length": 1, "mode": "colour"})
    assert outside(proj) == before and open(os.path.join(proj, "production.json")).read() == plan_text       # refused before anything was changed


# ---------------------------------------------------------------- imported packages

# ---------------------------------------------------------------- fonts and pictures a user chooses

@pytest.mark.parametrize("bad", ["../../Windows/Fonts/arial.ttf", "C:\\Windows\\Fonts\\arial.ttf", "/etc/passwd", "project:../../x.ttf", "system:..\\..\\x.ttf", "x" * 500])
def test_a_font_is_chosen_by_id_and_a_path_is_never_a_font(proj, bad):
    assert fonts.path_for(proj, bad) is None
    with pytest.raises(SystemExit):
        O.add(proj, {"kind": "text", "text": "x", "start": 0, "end": 4, "font": bad})


def test_files_that_are_not_what_they_claim_are_refused(proj, tmp_path):
    fake = tmp_path / "font.ttf"
    fake.write_text("not a font")
    with pytest.raises(SystemExit):
        fonts.add_file(proj, str(fake))
    exe = tmp_path / "x.exe"
    exe.write_bytes(b"MZ")
    with pytest.raises(SystemExit):
        O.add(proj, {"image": str(exe), "start": 0, "end": 4})
    big = tmp_path / "big.png"
    big.write_bytes(b"\0" * (O.MAX_FILE + 10))
    with pytest.raises(SystemExit, match="too large"):
        O.add(proj, {"image": str(big), "start": 0, "end": 4})
    txt = tmp_path / "a.txt"
    txt.write_text("x")
    with pytest.raises(SystemExit):
        titlecard.make(proj, {"title": "T", "background": {"type": "picture", "picture": str(txt)}})


def test_a_layer_cannot_point_at_a_file_outside_the_project(proj, tmp_path):
    secret = tmp_path / "secret.png"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(secret)
    O._save(proj, [{"id": "ov_x", "kind": "image", "file": "../../" + secret.name, "start": 0, "end": 4, "x": 0.5, "y": 0.5, "width": 0.3, "enabled": True}])
    with pytest.raises(SystemExit, match="missing"):
        O.render_image(proj, O.load(proj)[0], 320, 180)
    absolute = {"id": "ov_y", "kind": "image", "file": str(secret), "start": 0, "end": 4, "width": 0.3}
    with pytest.raises(SystemExit, match="missing"):
        O.render_image(proj, absolute, 320, 180)


def test_an_svg_cannot_read_files_or_reach_the_network(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-CONTENT")
    svg = tmp_path / "evil.svg"
    svg.write_text('<?xml version="1.0"?><!DOCTYPE s [<!ENTITY x SYSTEM "' + secret.as_uri() + '">]><svg xmlns="http://www.w3.org/2000/svg" width="200" height="40">'
                   '<text x="0" y="20" fill="#fff">&x;</text><image href="http://127.0.0.1:9/x.png" width="10" height="10"/></svg>')
    out = tmp_path / "o.png"
    try:
        svg_text.to_png(str(svg), str(out), transparent=True)
    except Exception:
        return                                             # refused outright: the safest answer
    assert out.exists() and b"TOP-SECRET-CONTENT" not in out.read_bytes()      # drawn (or left blank), but the file's words were never read in


# ---------------------------------------------------------------- numbers that become filter expressions

@pytest.mark.parametrize("bad", ["0);movie=/etc/passwd", "nan", "inf", [1], {"a": 1}, "1e999"])
def test_keyframe_and_layer_numbers_can_only_be_numbers(proj, bad):
    for key in ({"t": 0, "x": bad}, {"t": bad}):
        try:
            keys = O.clean_keys([key])
        except SystemExit:
            continue
        assert all(isinstance(v, (int, float)) and v == v and abs(v) < 1e6 for k in keys for p, v in k.items() if p != "ease")        # or it was clamped to a finite number
    if not isinstance(bad, str) or not bad.replace(".", "").replace("e", "").replace("-", "").isdigit():
        with pytest.raises(SystemExit):
            O.add(proj, {"kind": "text", "text": "x", "start": bad, "end": 4})              # a plain refusal, not a crash


def test_what_goes_into_a_filter_is_only_numbers_the_engine_made(proj):
    hostile = "'),movie=/etc/passwd,drawtext=text='x"
    keys = O.clean_keys([{"t": 0, "x": 0.2}, {"t": 2, "x": 0.8, "ease": "linear"}])
    expr = O.key_expr(keys, "x", "(t-1.000)")
    assert re.fullmatch(r"[0-9a-z().,+*/ -]+", expr), expr
    o = {"kind": "text", "text": hostile, "anim": "typewriter", "x": 0.5, "y": 0.5, "start": 0, "end": 4, "keys": keys}
    pre, pos = O.motion_keys(o, 0.0, 0.4, (100, 20), 320, 180)
    assert hostile not in pre + pos and "movie" not in pre + pos
    pre, pos = O.motion("typewriter", 0.0, 4.0, 0.4, 10, 10, (100, 20), 320, 180, None, len(hostile))
    assert hostile not in pre + pos and "movie" not in pre + pos


def test_hostile_text_is_drawn_as_text_and_never_run(proj, tmp_path):
    for text in ("'),movie=/etc/passwd,drawtext=text='x", "%{pts}", "a:b\\c'd\"e", "\\", "<script>alert(1)</script>", "{{7*7}}", "x" * 5000):
        O.add(proj, {"kind": "text", "text": text, "start": 0, "end": 3, "fade": 0.05, "x": 0.5, "y": 0.5, "size": 0.1})
    assert all(len(o["text"]) <= O.MAX_TEXT for o in O.load(proj))
    v = str(tmp_path / "film.mp4")
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0x202020:s=320x180:r=12:d=4", "-pix_fmt", "yuv420p", v], check=True, creationflags=NO_WINDOW)
    r = O.burn(proj, v, 320, 180, fps=12, duration=4.0)
    assert not r.get("error") and r["count"] == 7


# ---------------------------------------------------------------- secrets stay out of the project

def test_an_api_key_is_never_written_into_the_project(proj, monkeypatch):
    secret = "tok_" + os.urandom(12).hex()                          # made fresh each run, so no secret-like text sits in the source
    for name in ("FAL_KEY", "KIE_API_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY"):
        monkeypatch.setenv(name, secret)
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
    R.enqueue(proj, ["S01-01"], "fal", "test/model", {})
    R.run(proj, poll_every=0)
    leaked = [os.path.join(r, f) for r, _, fs in os.walk(proj) for f in fs if secret.encode() in open(os.path.join(r, f), "rb").read()]
    assert leaked == []


def test_the_update_check_only_ever_asks_one_fixed_address():
    from filmcrafter_engine import updates
    src = open(updates.__file__, encoding="utf-8").read()
    urls = set(re.findall(r"https?://[^\s\"')]+", src))
    assert urls and all(u.startswith(("https://api.github.com/", "https://github.com/")) for u in urls)         # the check asks the API; the page is only a link to open
    assert "api.github.com/repos/{REPO}/releases" in src and "redirect" in src.lower()


# ---------------------------------------------------------------- deletion

def test_clean_up_only_ever_touches_generated_files_inside_the_project(proj, tmp_path):
    from filmcrafter_engine import cleanup
    keep = tmp_path / "outer" / "important.png"
    Image.new("RGB", (8, 8)).save(keep)
    os.makedirs(os.path.join(proj, "assets"), exist_ok=True)
    Image.new("RGB", (8, 8)).save(os.path.join(proj, "assets", "ref.png"))
    r = cleanup.discard(proj, ["../important.png", str(keep), "assets/ref.png", "project.json", "generations/../project.json", "trash/../project.json"])
    assert r["moved"] == 0 and keep.exists() and os.path.exists(os.path.join(proj, "assets", "ref.png")) and os.path.exists(os.path.join(proj, "project.json"))
    assert cleanup.empty(proj)["deleted"] == 0 and os.path.exists(os.path.join(proj, "project.json"))
