"""Hostile and clumsy input, thrown at every place where what the screen (or a file the person opened) sends becomes a setting. The rule being checked is the same everywhere: the answer is either a clean
result or a plain refusal (SystemExit with a reason). Never another kind of failure (a crash, a stack trace on screen), and never a value that was not checked. Seeded, so a failure can be repeated."""
import json
import random

import pytest
from PIL import Image

from filmcrafter_engine import composite as C, layerkit as K, motion_templates as M, overlays as O, presets as P
from tests.test_editing import build_film

pytestmark = pytest.mark.integration

NASTY = [None, True, False, 0, -1, 1, 7, 2 ** 70, -2 ** 70, 0.5, -0.5, 1e999, -1e999, float("nan"), "", " ", "x" * 20000, "../../etc/passwd", "..\\..\\windows", "a;b", "0x10", "1e3", "nan", "inf", "\x00", "😀", "#zzz", "#12345g",
         "#00ff00; movie=x", "multiply", "ellipse", "none", "normal", "fade", "text", "clip", "image", "{name}", "%s%n", "' OR 1=1 --", "<script>alert(1)</script>", "$(rm -rf /)", "`id`", [], {}, [1, 2, 3], ["a"] * 500, {"a": 1},
         {"a": {"b": {"c": [1, {"d": None}]}}}, [[[[[[[]]]]]]], {"x": "y" * 5000}]


def deep(n=60):
    v: object = 1
    for _ in range(n):
        v = {"k": v}
    return v


POOL = NASTY + [deep()]


def pick(rng):
    return rng.choice(POOL)


OVERLAY_FIELDS = ["kind", "text", "section", "start", "end", "x", "y", "size", "width", "height", "fade", "color", "color2", "anim", "cover", "group", "font", "shape", "icon", "glow", "glow_color", "blur", "stroke",
                  "stroke_w", "opacity", "rotation", "radius", "scale", "angle", "filled", "gradient", "shadow", "keys", "name", "enabled", "blend", "mask", "mask_size", "mask_feather", "mask_invert", "key_color",
                  "key_tol", "key_soft", "key_spill", "in_s", "loop", "id", "file", "src_w", "src_h", "src_dur", "video", "image"]


@pytest.fixture
def film(tmp_path):
    return build_film(tmp_path, [("S01-01", 1, 0.0, 6.0), ("S01-02", 1, 6.0, 12.0)], 12.0)


def only_refusals(fn, *a):
    """Run `fn`; a clean result or a plain refusal is fine, anything else is the bug."""
    try:
        return fn(*a)
    except SystemExit as e:
        assert isinstance(e.code, (str, type(None))) and (e.code is None or len(str(e.code)) < 400), "a refusal must be a short plain reason"
        return None


def test_the_layer_validator_only_ever_answers_or_refuses(film):
    rng = random.Random(20261105)
    cleaned = 0
    for _ in range(1500):
        x = {k: pick(rng) for k in rng.sample(OVERLAY_FIELDS, rng.randint(0, 12))}
        if rng.random() < 0.5:
            x["kind"] = rng.choice(["text", "image", "clip", "fill", "shape", "icon", "svg"])
        o = only_refusals(O._clean, film, x)
        if o is not None:
            cleaned += 1
            for k in ("x", "y", "width", "fade", "size"):                                       # whatever got through is inside its range
                assert isinstance(o[k], (int, float)) and not isinstance(o[k], bool) and o[k] == o[k] and abs(o[k]) != float("inf")
            for k in ("start", "end", "in_s", "glow", "blur", "opacity", "key_tol", "mask_size", "mask_feather"):
                if o.get(k) is not None:
                    assert isinstance(o[k], (int, float)) and not isinstance(o[k], bool) and o[k] == o[k] and abs(o[k]) != float("inf"), (k, o[k])
            assert o["kind"] in ("text", "svg", "image", "clip", "fill", "shape", "icon")
            assert o.get("blend") in (None, *C.BLENDS) and o.get("mask") in (None, *C.MASKS)
            json.dumps(o)                                                                         # it can be saved
    assert cleaned > 100                                                                          # the fuzz is not just being refused: plenty of mixes were valid


def test_adding_and_updating_layers_with_hostile_input_never_corrupts_the_project(film):
    rng = random.Random(7)
    for _ in range(400):
        x = {k: pick(rng) for k in rng.sample(OVERLAY_FIELDS, rng.randint(0, 10))}
        x["kind"] = rng.choice(["text", "fill", "shape", "icon"])
        only_refusals(O.add, film, x)
    items = O.load(film)
    assert len(items) <= O.MAX_OVERLAYS
    for o in items:
        json.dumps(o)
        assert o["id"].startswith("ov_") and o["kind"] in ("text", "fill", "shape", "icon")
    for o in items[:30]:
        for _ in range(8):
            only_refusals(O.update, film, o["id"], {k: pick(rng) for k in rng.sample(OVERLAY_FIELDS, rng.randint(1, 6)) if k not in ("kind", "id", "file", "video", "image")})
    assert len(O.load(film)) == len(items)                                                        # nothing was lost or duplicated by bad updates
    O.resolve(film)                                                                               # and the whole list still reads


def test_the_compositing_values_only_answer_or_refuse(film):
    rng = random.Random(11)
    im = Image.new("RGBA", (40, 30), (10, 200, 30, 255))
    for _ in range(600):
        o: dict = {}
        x = {k: pick(rng) for k in rng.sample(["blend", "mask", "mask_size", "mask_feather", "mask_invert", "key_color", "key_tol", "key_soft", "key_spill"], rng.randint(1, 6))}
        if only_refusals(C.clean, x, o, O._hex) is None and not o:
            continue
        out = only_refusals(C.apply_mask, im, o)
        key = only_refusals(C.apply_key, im, o, O._hex)
        for r in (out, key):
            if r is not None:
                assert r.size == im.size and r.mode == "RGBA"
        if o.get("blend"):
            assert only_refusals(C.graph, 1, "v0", "x=0:y=0", o["blend"], 0.0, 1.0, 64, 36, 24)[1] == "v1"
        assert isinstance(C.signature(o), list)


def test_motion_graphic_words_are_only_ever_words(film):
    rng = random.Random(3)
    for _ in range(300):
        tid = rng.choice([t["id"] for t in M.BUILTIN] + [pick(rng) if isinstance(pick(rng), str) else "x"])
        texts = rng.choice([pick(rng), {s: pick(rng) for s in ("name", "role", "title", "line", "text", "quote", "who", "number", "what", "end", "label", "place")}])
        t = only_refusals(M.build, tid, texts)
        if t:
            for l in t["layers"]:
                assert "{" not in str(l["look"].get("text", "")) or "{" in json.dumps(texts)            # a placeholder is never left unfilled by accident
                assert len(str(l["look"].get("text", ""))) <= M.SLOT_MAX + 8
                O._clean(film, {**l["look"], "start": 1.0, "end": 2.0})                                 # and every layer is valid by the same checks as one you make


def test_the_preset_actions_only_answer_or_refuse_and_leave_the_film_readable(film):
    d, rd = film if isinstance(film, tuple) else (film, film)
    rng = random.Random(5)
    ids = list(P.builtin())
    for _ in range(300):
        action = rng.choice(["catalog", "plan", "favorite", "save_mine", "delete_mine", "stack_get", "reframe_set", "set_pending"])
        x = {k: pick(rng) for k in rng.sample(["stack", "replace", "id", "on", "name", "shot", "x", "setup"], rng.randint(0, 5))}
        if rng.random() < 0.5:
            x["stack"] = rng.sample(ids, rng.randint(0, 4)) + ([pick(rng)] if rng.random() < 0.5 else [])
        only_refusals(P.run, d, action, x)
    st = P.load_state(d)                                                                          # the record is still one the program can read, and within its limits
    assert len(st["pending"]) <= P.MAX_PENDING and len(st["mine"]) <= P.MAX_MINE and all(isinstance(i, str) for i in st["stack"])
    P.catalog(d)


def test_layer_templates_refuse_what_is_not_a_layer_template(film):
    rng = random.Random(9)
    for _ in range(200):
        action = rng.choice(["styles", "save", "apply", "delete_style", "templates", "template_save", "template_apply", "template_delete", "template_remove", "builtin_list", "builtin_apply", "builtin_preview"])
        x = {k: pick(rng) for k in rng.sample(["ids", "name", "at", "group", "id", "texts", "layers", "style"], rng.randint(0, 5))}
        only_refusals(lambda: K.main([action, film, "--data", json.dumps(x, default=str)]))
