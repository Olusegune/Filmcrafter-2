"""Exact edit time and the editing operations: whole ticks, a sequence that keeps its rules, and operations that are pure (they change a copy or nothing).
No file, provider or ffmpeg is used here."""
import ast
import copy
import os
import random

import pytest

from filmcrafter_engine import edit_ops as O, edit_time as T, sequence as Q

FT = T.FPS_24.frame_ticks


def fr(n):
    return n * FT


def seq(*clips, length=None, locked=False):
    cl = [{"id": f"c{i}", "shot": s, "start": fr(a), "source_in": fr(si), "duration": fr(du), "take": None} for i, (s, a, si, du) in enumerate(clips, 1)]
    out = {"fps": [24, 1], "length": fr(length) if length is not None else max((c["start"] + c["duration"] for c in cl), default=0), "next": len(cl) + 1,
           "tracks": [{"id": "V1", "kind": "video", "locked": locked, "hidden": False, "muted": False, "clips": cl}], "markers": [], "ranges": []}
    Q.validate(out)
    return out


def shape(s):
    return [(c["shot"], c["start"] // FT, c["source_in"] // FT, c["duration"] // FT) for c in s["tracks"][0]["clips"]]


# ---------------------------------------------------------------- time

@pytest.mark.parametrize("name", list(T.COMMON))
def test_every_common_frame_rate_is_a_whole_number_of_ticks(name):
    r = T.COMMON[name]
    assert r.exact and r.frame_ticks * r.num == T.TICKS_PER_SECOND * r.den


def test_the_tick_unit_has_the_factors_that_make_that_true():
    n, f = T.TICKS_PER_SECOND, {}
    for p in (2, 3, 5, 7):
        while n % p == 0:
            n //= p
            f[p] = f.get(p, 0) + 1
    assert n == 1 and f == {2: 12, 3: 4, 5: 6, 7: 2}


def test_frames_and_ticks_convert_exactly_and_round_the_way_they_say():
    for rate in T.COMMON.values():
        for n in (0, 1, 7, 1000, 123456):
            assert T.frame_at(T.tick_of_frame(n, rate), rate) == n
            assert T.frame_at(T.tick_of_frame(n, rate) + rate.frame_ticks - 1, rate) == n              # anywhere inside a frame is that frame
    ft = T.FPS_24.frame_ticks
    assert T.snap(ft + 5) == ft and T.snap_nearest(ft + 5) == ft and T.snap_nearest(2 * ft - 5) == 2 * ft
    assert T.snap_nearest(ft + ft // 2) == ft                                                          # exactly half way goes to the earlier frame


def test_seconds_come_in_once_rounded_to_a_frame_and_a_bad_time_is_refused():
    assert T.seconds_to_ticks(1) == 24 * FT and T.seconds_to_ticks("0.5") == 12 * FT and T.seconds_to_ticks(2.0) == 48 * FT
    assert T.seconds_to_ticks(1 / 24) == FT and T.seconds_to_ticks(0.0416) == FT
    for bad in (float("nan"), float("inf"), True, "x"):
        with pytest.raises((ValueError, ArithmeticError)):
            T.seconds_to_ticks(bad)
    assert T.FrameRate(48, 2) == T.FrameRate(24, 1) and T.FrameRate.of("junk") == T.FPS_24
    assert T.timecode(T.tick_of_frame(24 * 61 + 5)) == "00:01:01:05"


def test_the_edit_modules_do_no_arithmetic_on_time_in_floating_point():
    here = os.path.join(os.path.dirname(__file__), "..", "filmcrafter_engine")
    for name in ("edit_ops.py", "sequence.py"):
        tree = ast.parse(open(os.path.join(here, name), encoding="utf-8").read())
        for node in ast.walk(tree):
            assert not (isinstance(node, ast.Constant) and isinstance(node.value, float)), (name, node.lineno)
            assert not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)), (name, node.lineno)
            assert not (isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("float", "round")), (name, node.lineno)


# ---------------------------------------------------------------- the sequence

def test_a_stored_sequence_is_made_safe_and_whole_numbers_only():
    raw = {"fps": [24, 1], "tracks": [{"id": "V1", "kind": "video", "clips": [
        {"id": "a", "shot": "S1", "start": FT, "source_in": 0, "duration": FT * 2}, {"id": "b", "shot": "S2", "start": 1.5, "source_in": 0, "duration": FT},
        {"id": "c", "shot": "S3", "start": 7, "source_in": 0, "duration": FT}, {"id": "d", "shot": "S4", "start": -1, "source_in": 0, "duration": FT}, "junk"]},
        {"id": "X", "kind": "audio", "clips": []}], "markers": [{"id": "m1", "at": FT, "name": " a   b "}, {"id": "m2", "at": -5}]}
    c = Q.clean(raw)
    assert [x["id"] for x in c["tracks"][0]["clips"]] == ["a"] and len(c["tracks"]) == 1 and c["markers"] == [{"id": "m1", "at": FT, "name": "a b"}]
    assert Q.clean("nope") is None and Q.clean({"tracks": []}) is None


def test_the_rules_every_sequence_keeps_are_enforced():
    base = seq(("A", 0, 0, 10), ("B", 10, 0, 10))
    bad = copy.deepcopy(base)
    bad["tracks"][0]["clips"][1]["start"] = fr(5)
    for mutate, why in ((lambda s: s["tracks"][0]["clips"][1].update(start=fr(5)), "overlap"), (lambda s: s["tracks"][0]["clips"][0].update(duration=0), "empty"),
                        (lambda s: s["tracks"][0]["clips"][0].update(source_in=-FT), "before its own"), (lambda s: s["tracks"][0]["clips"][0].update(start=5), "whole frame"),
                        (lambda s: s["tracks"][0]["clips"][1].update(id="c1"), "same name")):
        s = copy.deepcopy(base)
        mutate(s)
        with pytest.raises(SystemExit):
            Q.validate(s)


def test_a_shot_with_no_clip_and_a_clip_with_no_shot_are_reported_not_hidden():
    s = seq(("A", 0, 0, 5), ("GONE", 5, 0, 5))
    assert Q.status(s, ["A", "NEW"]) == {"unplaced": ["NEW"], "orphans": ["c2"]}


# ---------------------------------------------------------------- the operations

def test_a_cut_makes_two_clips_that_together_are_the_one_it_replaced():
    s = seq(("A", 0, 0, 48))
    out = O.split(s, fr(20))
    assert shape(out) == [("A", 0, 0, 20), ("A", 20, 20, 28)]                       # the second half starts 20 frames into the take
    assert out["length"] == s["length"] and shape(s) == [("A", 0, 0, 48)]            # the original is untouched
    for bad in (0, fr(48), fr(60), 7):
        with pytest.raises(SystemExit):
            O.split(s, bad)


def test_a_regular_trim_changes_one_edge_and_leaves_the_rest_of_the_film_alone():
    s = seq(("A", 0, 0, 20), ("B", 20, 0, 20))
    assert shape(O.trim(s, "c1", "out", fr(15))) == [("A", 0, 0, 15), ("B", 20, 0, 20)]                      # a gap is left
    assert shape(O.trim(s, "c2", "in", fr(25))) == [("A", 0, 0, 20), ("B", 25, 5, 15)]
    assert shape(O.trim(O.trim(s, "c2", "in", fr(25)), "c2", "in", fr(22))) == [("A", 0, 0, 20), ("B", 22, 2, 18)]       # and can be brought back
    with pytest.raises(SystemExit, match="past the clip after"):
        O.trim(s, "c1", "out", fr(25))
    with pytest.raises(SystemExit, match="past the clip before"):
        O.trim(s, "c2", "in", fr(15))
    with pytest.raises(SystemExit, match="to nothing"):
        O.trim(s, "c1", "out", 0)
    with pytest.raises(SystemExit, match="no more of this clip"):
        O.trim(seq(("A", 5, 0, 10)), "c1", "in", fr(3))                              # the take has nothing before its first frame to bring back


def test_a_ripple_trim_moves_everything_after_it_and_changes_the_length():
    s = seq(("A", 0, 0, 20), ("B", 20, 0, 20))
    out = O.trim(s, "c1", "out", fr(15), ripple=True)
    assert shape(out) == [("A", 0, 0, 15), ("B", 15, 0, 20)] and out["length"] == fr(35)
    out = O.trim(s, "c1", "out", fr(30), ripple=True)
    assert shape(out) == [("A", 0, 0, 30), ("B", 30, 0, 20)] and out["length"] == fr(50)
    out = O.trim(s, "c1", "in", fr(6), ripple=True)                                  # the clip keeps its place, gives up its first 6 frames, and the film closes up
    assert shape(out) == [("A", 0, 6, 14), ("B", 14, 0, 20)] and out["length"] == fr(34)


def test_delete_leaves_a_gap_and_a_ripple_delete_closes_it():
    s = seq(("A", 0, 0, 10), ("B", 10, 0, 10), ("C", 20, 0, 10))
    assert shape(O.delete(s, "c2")) == [("A", 0, 0, 10), ("C", 20, 0, 10)]
    out = O.delete(s, "c2", ripple=True)
    assert shape(out) == [("A", 0, 0, 10), ("C", 10, 0, 10)] and out["length"] == fr(20)


def test_a_move_needs_room_and_a_ripple_move_makes_room_by_putting_the_clip_between_others():
    s = seq(("A", 0, 0, 10), ("B", 10, 0, 10), ("C", 20, 0, 10))
    with pytest.raises(SystemExit, match="no room"):
        O.move(s, "c3", fr(5))
    assert shape(O.move(s, "c3", fr(40))) == [("A", 0, 0, 10), ("B", 10, 0, 10), ("C", 40, 0, 10)]
    out = O.move(s, "c3", fr(2), ripple=True)                                        # dropped near the start: in front of B
    assert [x[0] for x in shape(out)] == ["A", "C", "B"] and out["length"] == s["length"]
    assert shape(out) == [("A", 0, 0, 10), ("C", 10, 0, 10), ("B", 20, 0, 10)]
    assert [x[0] for x in shape(O.move(s, "c1", fr(100), ripple=True))] == ["B", "C", "A"]


def test_a_roll_moves_the_cut_between_two_clips_and_nothing_else():
    s = seq(("A", 0, 5, 10), ("B", 10, 0, 10))
    assert shape(O.roll(s, "c1", fr(14))) == [("A", 0, 5, 14), ("B", 14, 4, 6)]
    assert shape(O.roll(seq(("A", 0, 5, 10), ("B", 10, 3, 10)), "c1", fr(7))) == [("A", 0, 5, 7), ("B", 7, 0, 13)]
    with pytest.raises(SystemExit, match="not touching"):
        O.roll(seq(("A", 0, 0, 5), ("B", 8, 0, 5)), "c1", fr(6))
    with pytest.raises(SystemExit, match="either clip empty"):
        O.roll(s, "c1", fr(20))
    with pytest.raises(SystemExit, match="no more of the clip after"):
        O.roll(s, "c1", fr(7))


def test_close_gap_and_place_and_markers_and_ranges_and_track_flags():
    s = seq(("A", 0, 0, 10), ("B", 15, 0, 10), length=30)
    out = O.close_gap(s, "c2")
    assert shape(out) == [("A", 0, 0, 10), ("B", 10, 0, 10)] and out["length"] == fr(25)
    with pytest.raises(SystemExit, match="no gap"):
        O.close_gap(out, "c2")
    placed = O.place(s, "C", fr(8))
    assert shape(placed)[-1] == ("C", 25, 0, 8)
    with pytest.raises(SystemExit, match="already in the film"):
        O.place(placed, "C", fr(8))
    m = O.marker_set(s, fr(12), "  the  turn ")
    assert m["markers"][0]["name"] == "the turn" and O.marker_set(m, fr(3), "x", "m3")["markers"][0]["at"] == fr(3)
    assert O.marker_remove(m, m["markers"][0]["id"])["markers"] == []
    r = O.range_set(s, fr(2), fr(9), "scene")
    assert r["ranges"][0]["end"] == fr(9)
    with pytest.raises(SystemExit):
        O.range_set(s, fr(9), fr(2))
    t = O.track_set(s, "V1", locked=True)
    for call in (lambda: O.split(t, fr(5)), lambda: O.trim(t, "c1", "out", fr(5)), lambda: O.delete(t, "c1"), lambda: O.move(t, "c1", fr(40)), lambda: O.place(t, "C", fr(3))):
        with pytest.raises(SystemExit, match="locked"):
            call()
    assert O.track_set(t, "V1", locked=False)["tracks"][0]["locked"] is False
    with pytest.raises(SystemExit):
        O.track_set(s, "V1")


def test_snapping_goes_to_the_nearest_point_within_reach_and_a_tie_to_the_earlier_one():
    pts = [fr(10), fr(20)]
    assert O.snap_to(pts, fr(11), fr(2)) == fr(10) and O.snap_to(pts, fr(15), fr(2)) == fr(15) and O.snap_to(pts, fr(15), fr(5)) == fr(10)


def test_an_operation_that_fails_changes_nothing_and_every_result_keeps_the_rules():
    rng = random.Random(7)
    s = seq(("A", 0, 0, 12), ("B", 12, 0, 12), ("C", 24, 0, 12), length=40)
    done = failed = 0
    for _ in range(600):
        before = copy.deepcopy(s)
        op = rng.choice(["split", "trim", "delete", "move", "roll", "close_gap"])
        ids = [c["id"] for c in s["tracks"][0]["clips"]]
        if len(ids) < 2:                                                          # start again rather than run out of clips
            s = seq(("A", 0, 0, 12), ("B", 12, 0, 12), ("C", 24, 0, 12), length=40)
            continue
        cid, at, rip = rng.choice(ids), fr(rng.randint(0, 80)), rng.random() < 0.5
        try:
            if op == "split":
                new = O.split(s, at)
            elif op == "trim":
                new = O.trim(s, cid, rng.choice(["in", "out"]), at, rip)
            elif op == "delete":
                new = O.delete(s, cid, rip)
            elif op == "move":
                new = O.move(s, cid, at, rip)
            elif op == "roll":
                new = O.roll(s, cid, at)
            else:
                new = O.close_gap(s, cid)
        except SystemExit:
            failed += 1
            assert s == before
            continue
        Q.validate(new)                                                           # every success keeps the rules
        assert s == before                                                        # and never changes what it was given
        assert new["length"] >= max((c["start"] + c["duration"] for c in new["tracks"][0]["clips"]), default=0)
        assert all(isinstance(c[k], int) for c in new["tracks"][0]["clips"] for k in ("start", "source_in", "duration"))
        if len(new["tracks"][0]["clips"]) < 40:
            s = new
        done += 1
    assert done > 100 and failed > 50                                              # the run really exercised both


def test_a_split_and_then_putting_it_back_loses_nothing_of_the_take():
    s = seq(("A", 3, 7, 30))
    cut = O.split(s, fr(20))
    a, b = cut["tracks"][0]["clips"]
    assert a["source_in"] == fr(7) and b["source_in"] == fr(7) + a["duration"] and a["duration"] + b["duration"] == fr(30) and b["start"] == a["start"] + a["duration"]
    assert b["start"] - b["source_in"] == a["start"] - a["source_in"]                      # both halves still show the same moment of the take at the same moment of the film
