"""Cleaning up unused videos and pictures: what counts as unused, what is never touched, the trash, restoring and emptying."""
import json
import os
import time

import pytest

from filmcrafter_engine import cleanup as C


def put(d, rel, data=b"x" * 100, age=3600):
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)
    t = time.time() - age
    os.utime(p, (t, t))
    return rel


def job(i, shot, out, state="ready", kind="video", **kw):
    return {"id": i, "shot_id": shot, "plan": "production", "state": state, "kind": kind, "output": out, "created": 1000 + len(i), **kw}


@pytest.fixture
def proj(tmp_path):
    d = str(tmp_path / "p")
    os.makedirs(d)
    json.dump({"scenes": [{"number": 1, "shots": [{"id": "S01-01"}, {"id": "S01-02"}]}]}, open(os.path.join(d, "production.json"), "w"))
    put(d, "generations/S01-01__a.mp4")                 # the take S01-01 uses (approved)
    put(d, "generations/S01-01__b.mp4")                 # an older take of it: unused
    put(d, "generations/S01-02__c.mp4")                 # S01-02 has one finished take and none approved: it is the one used
    put(d, "generations/S01-01__k1.png")                # the approved keyframe
    put(d, "generations/S01-01__k2.png")                # another keyframe version: unused
    put(d, "generations/lost.png")                      # not in the render list, named nowhere: unused
    put(d, "generations/sheet.png")                     # named in the library: kept
    put(d, "generations/fresh.mp4", age=5)              # made seconds ago: kept
    put(d, "generations/notes.txt")                     # not a picture or video: never touched
    json.dump({"jobs": [job("a", "S01-01", "generations/S01-01__a.mp4", keyframe_ref="project:generations/S01-01__k1.png"),
                        job("b", "S01-01", "generations/S01-01__b.mp4"), job("c", "S01-02", "generations/S01-02__c.mp4"),
                        job("k1", "S01-01", "generations/S01-01__k1.png", kind="image"), job("k2", "S01-01", "generations/S01-01__k2.png", kind="image")]},
              open(os.path.join(d, "jobs.json"), "w"))
    json.dump({"S01-01": {"approved": "a"}}, open(os.path.join(d, "shots.json"), "w"))
    json.dump({"production": {"S01-01": "project:generations/S01-01__k1.png"}}, open(os.path.join(d, "keyframes.json"), "w"))
    json.dump({"items": [{"file": "generations/sheet.png"}]}, open(os.path.join(d, "library.json"), "w"))
    return d


def paths(d):
    return sorted(i["path"] for i in C.scan(d)["items"])


def test_only_what_nothing_uses_is_offered(proj):
    assert paths(proj) == ["generations/S01-01__b.mp4", "generations/S01-01__k2.png", "generations/lost.png"]
    s = C.scan(proj)
    assert s["bytes"] == 300 and s["rendering"] == 0 and s["trash"]["files"] == 0
    it = next(i for i in s["items"] if i["name"] == "S01-01__b.mp4")
    assert it["kind"] == "video" and it["shot"] == "S01-01"


def test_removing_moves_to_the_trash_and_restoring_puts_it_back(proj):
    r = C.discard(proj, ["generations/S01-01__b.mp4", "generations/lost.png"])
    assert r["moved"] == 2 and r["skipped"] == [] and r["bytes"] == 200
    assert not os.path.exists(os.path.join(proj, "generations/S01-01__b.mp4"))
    assert r["scan"]["trash"]["files"] == 2 and paths(proj) == ["generations/S01-01__k2.png"]
    jobs = {j["id"]: j for j in json.load(open(os.path.join(proj, "jobs.json")))["jobs"]}
    assert jobs["b"]["state"] == "dismissed" and jobs["a"]["state"] == "ready"                     # the take no longer shows in the shot's list
    back = C.restore(proj)
    assert back["restored"] == 2 and os.path.isfile(os.path.join(proj, "generations/S01-01__b.mp4"))
    jobs = {j["id"]: j for j in json.load(open(os.path.join(proj, "jobs.json")))["jobs"]}
    assert jobs["b"]["state"] == "ready" and back["scan"]["trash"]["files"] == 0


def test_emptying_the_trash_deletes_for_good_and_only_the_trash(proj):
    C.discard(proj, ["generations/S01-01__b.mp4"])
    r = C.empty(proj)
    assert r["deleted"] == 1 and r["bytes"] == 100 and not os.listdir(os.path.join(proj, "trash"))
    assert os.path.isfile(os.path.join(proj, "generations/S01-01__a.mp4")) and os.path.isfile(os.path.join(proj, "generations/notes.txt"))


def test_the_engine_checks_again_and_never_removes_what_is_in_use_or_outside(proj, tmp_path):
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"keep")
    put(proj, "assets/refs/hero.png")
    asked = ["generations/S01-01__a.mp4", "generations/S01-01__k1.png", "generations/sheet.png", "generations/fresh.mp4", "generations/notes.txt", "assets/refs/hero.png",
             "../outside.png", str(outside), "generations/../project.json", "generations/lost.png"]
    r = C.discard(proj, asked)
    assert r["moved"] == 1 and len(r["skipped"]) == 9                                                  # only lost.png went
    for keep in ("generations/S01-01__a.mp4", "generations/S01-01__k1.png", "generations/sheet.png", "generations/fresh.mp4", "generations/notes.txt", "assets/refs/hero.png"):
        assert os.path.isfile(os.path.join(proj, keep))
    assert outside.read_bytes() == b"keep"


def test_nothing_is_removed_while_a_render_is_running(proj):
    jobs = json.load(open(os.path.join(proj, "jobs.json")))
    jobs["jobs"].append(job("run", "S01-02", None, state="running"))
    json.dump(jobs, open(os.path.join(proj, "jobs.json"), "w"))
    with pytest.raises(SystemExit, match="render is still running"):
        C.discard(proj, ["generations/lost.png"])
    assert os.path.isfile(os.path.join(proj, "generations/lost.png"))


def test_a_file_that_is_back_in_use_is_not_restored_over_and_an_empty_request_is_refused(proj):
    C.discard(proj, ["generations/lost.png"])
    put(proj, "generations/lost.png", b"new")                                                          # something new took its place
    r = C.restore(proj)
    assert r["restored"] == 0 and r["left"] == 1 and open(os.path.join(proj, "generations/lost.png"), "rb").read() == b"new"
    with pytest.raises(SystemExit, match="Choose what to remove"):
        C.discard(proj, [])


def test_a_link_is_never_followed_or_removed(proj, tmp_path):
    target = tmp_path / "precious.png"
    target.write_bytes(b"precious")
    link = os.path.join(proj, "generations", "link.png")
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("this system cannot make links")
    assert "generations/link.png" not in paths(proj)
    C.discard(proj, ["generations/link.png"])
    assert target.read_bytes() == b"precious"


def test_the_command_line_speaks_json(proj, capsys):
    assert C.main(["scan", proj]) == 0
    ev = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert ev["event"] == "result" and len(ev["data"]["items"]) == 3
    assert C.main(["discard", proj, "--data", json.dumps({"paths": []})]) == 1
    assert "Choose what to remove" in json.loads(capsys.readouterr().out.splitlines()[-1])["message"]
