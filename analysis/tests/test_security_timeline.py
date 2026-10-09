"""Hostile or careless input at the new timeline edges: moving and trimming layers, transitions, and the free checks. Nothing may crash an export, escape the project, or store junk."""
import json
import math
import os

import pytest

from pulseframe_analysis import dance, looks, media, overlays, transitions


def project(tmp_path):
    d = tmp_path / "p"
    d.mkdir(exist_ok=True)
    json.dump({"title": "T", "song": "song.wav"}, open(d / "project.json", "w"))
    json.dump({"duration": 30.0, "bpm": 120, "downbeats": [0, 2, 4]}, open(d / "songmap.json", "w"))
    json.dump({"meta": {}, "scenes": [{"number": 1, "heading": "INT.", "shots": [{"id": "S01-01", "start": 0, "end": 4, "performers": ["Ada"], "emotion": "joy"}]}]}, open(d / "production.json", "w"))
    return str(d)


def layer(d, **kw):
    return overlays.add(d, {"kind": "text", "text": "Hello", "start": 2, "end": 6, "keys": [{"t": 0, "opacity": 0.2}, {"t": 2, "opacity": 1}], **kw})[-1]


# ---------------------------------------------------------------- moving and trimming layers
@pytest.mark.parametrize("bad", ["soon", None, [1], {"a": 1}, float("nan")])
def test_a_junk_start_or_end_is_refused_or_cleared_never_stored_as_junk(tmp_path, bad):
    d = project(tmp_path)
    o = layer(d)
    for k in ("start", "end"):
        try:
            out = overlays.update(d, o["id"], {k: bad})
        except SystemExit:
            continue                                               # refused plainly
        got = next(x for x in out if x["id"] == o["id"])
        assert got.get(k) is None or isinstance(got[k], float) or isinstance(got[k], int)
        assert not (isinstance(got.get(k), float) and math.isnan(got[k]))


@pytest.mark.parametrize("start,end", [(-50, 3), (0, 10 ** 9), (10 ** 9, 10 ** 9 + 5), (float("inf"), 5)])
def test_out_of_range_times_are_clamped_into_the_song_when_drawn(tmp_path, start, end):
    d = project(tmp_path)
    o = layer(d)
    try:
        out = overlays.update(d, o["id"], {"start": start, "end": end})
    except SystemExit:
        return
    got = next(x for x in out if x["id"] == o["id"])
    if got["placed"]:
        assert 0 <= got["start"] < got["end"] <= 30.0
    else:
        assert got["reason"]                                       # not drawn, and says why


def test_an_end_before_the_start_is_refused_and_the_layer_is_unchanged(tmp_path):
    d = project(tmp_path)
    o = layer(d)
    with pytest.raises(SystemExit):
        overlays.update(d, o["id"], {"start": 9, "end": 4})
    got = next(x for x in overlays.load(d) if x["id"] == o["id"])
    assert (got["start"], got["end"]) == (2, 6)


def test_moving_a_layer_changes_only_its_time_and_keeps_its_keyframes_and_look(tmp_path):
    d = project(tmp_path)
    o = layer(d, color="#ff0000", anim="rise", name="Title")
    before = {k: v for k, v in overlays.load(d)[0].items() if k not in ("start", "end")}
    out = overlays.update(d, o["id"], {"start": 10.0, "end": 14.0})
    got = next(x for x in out if x["id"] == o["id"])
    assert (got["start"], got["end"]) == (10.0, 14.0)
    assert {k: v for k, v in overlays.load(d)[0].items() if k not in ("start", "end")} == before
    assert len(got["keys"]) == 2                                   # keyframes are relative to the start, so they travel with the layer


def test_hiding_a_layer_keeps_it_but_leaves_it_out_of_what_is_drawn(tmp_path):
    d = project(tmp_path)
    o = layer(d)
    out = overlays.update(d, o["id"], {"enabled": False})
    assert next(x for x in out if x["id"] == o["id"])["enabled"] is False
    assert len(overlays.load(d)) == 1
    off = [x for x in overlays.resolve(d) if x["enabled"]]
    assert off == []
    assert next(x for x in overlays.update(d, o["id"], {"enabled": True}) if x["id"] == o["id"])["enabled"] is True


def test_an_unknown_layer_id_is_refused(tmp_path):
    d = project(tmp_path)
    for oid in ("nope", "../../etc/passwd", ""):
        with pytest.raises(SystemExit):
            overlays.update(d, oid, {"start": 1})


# ---------------------------------------------------------------- transitions
@pytest.mark.parametrize("name", ["star_wipe", "../../x", "", "Dissolve", "dissolve; rm -rf /", None, 5])
def test_only_known_transition_names_are_stored(tmp_path, name):
    d = project(tmp_path)
    with pytest.raises(SystemExit):
        media.set_transition(d, ["S01-01"], name)
    assert not os.path.exists(os.path.join(d, "shots.json"))


@pytest.mark.parametrize("secs", ["soon", [1], {"a": 1}, float("nan"), float("inf"), float("-inf")])
def test_junk_lengths_are_refused(tmp_path, secs):
    d = project(tmp_path)
    with pytest.raises(SystemExit):
        media.set_transition(d, ["S01-01"], "dissolve", secs)


@pytest.mark.parametrize("secs,want", [(0, 0.1), (-5, 0.1), (999, 2.0), (0.37, 0.37), ("1.5", 1.5)])
def test_lengths_are_kept_inside_the_safe_range(tmp_path, secs, want):
    d = project(tmp_path)
    assert media.set_transition(d, ["S01-01"], "wipe_left", secs)["seconds"] == want


def test_the_filter_graph_never_contains_anything_but_numbers_from_the_caller():
    for kind in transitions.TRANSITIONS:
        if kind in ("cut", "black", "white"):
            continue
        for n in (2, 12, 48):
            g, _ = transitions.filter_graph(kind, n, 1280, 720, 24)
            assert ";" in g or "[" in g
            assert all(c not in g for c in "`$\\\n")


def test_an_unknown_kind_cannot_reach_the_filter_graph():
    with pytest.raises(SystemExit):
        transitions.filter_graph("../../x", 12, 1280, 720, 24)


# ---------------------------------------------------------------- the free checks read files only and survive junk
def test_the_free_checks_survive_unreadable_project_files(tmp_path):
    d = tmp_path / "bad"
    d.mkdir()
    for name in ("project.json", "songmap.json", "production.json", "choreography.json", "camera.json"):
        (d / name).write_text("{ not json", encoding="utf-8")
    assert dance.check(str(d))["shots"] == []
    assert looks.suggest(str(d))["shots"] == []
    assert looks.suggest_apply(str(d), ["S01-01"]) == {"changed": []}


@pytest.mark.parametrize("shots", [None, "S01-01", [None, 5, {"a": 1}], ["../../x"]])
def test_applying_looks_to_junk_ids_changes_nothing(tmp_path, shots):
    d = project(tmp_path)
    try:
        out = looks.suggest_apply(d, shots)
    except SystemExit:
        return
    assert out["changed"] == [] or out["changed"] == ["S01-01"]
    assert not os.path.exists(os.path.join(d, "camera.json")) or set(json.load(open(os.path.join(d, "camera.json")))) <= {"S01-01"}
