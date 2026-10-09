"""Anatomy: asking for correct hands and limbs, telling the checkers to look at them, and what a flagged picture does."""
from filmcrafter_engine import anatomy as A, render as R, review as RV, stills as ST


def field(name, type="string", **kw):
    return {"name": name, "type": type, "items": kw.get("items"), "enum": kw.get("enum"), "default": kw.get("default"), "minimum": None, "maximum": None, "max_items": None,
            "max_length": kw.get("max_length"), "description": kw.get("description", ""), "required": kw.get("required", False)}


def still_model():
    return R._finish("fal", "t/i", "Still", "text-to-image", [field("prompt")])


def video_model(negative=False):
    f = [field("prompt"), field("image_url", description="Start image"), field("duration", enum=["5"])]
    if negative:
        f.append(field("negative_prompt", description="What to avoid."))
    return R._finish("fal", "t/v", "Video", "image-to-video", f)


def build(shot, man, project=None, **kw):
    s = {"id": "S01-01", "start": 0.0, "end": 4.0, "performers": [], "beats": ["x"], **shot}
    return R.compile_request(s, None, {"meta": {}}, project or {"look": {"style": "auto"}}, man, [], **kw)


# ---------------------------------------------------------------- the guard

def test_nobody_in_the_shot_needs_no_guard():
    assert A.guard({"performers": [], "beats": ["The empty street at dawn."]}) is None


def test_people_get_the_basic_line_and_hands_at_work_get_the_stronger_one():
    basic = A.guard({"performers": ["Sege"], "beats": ["Sege looks at the sea."]})
    assert basic["text"] == A.BASIC and basic["hands"] is False
    for words in ("Sege holds her hand", "they clasp hands", "she reaches toward him", "a hug", "Sege plays the guitar", "fingers on the glass", "wrists bound"):
        g = A.guard({"performers": ["Sege"], "beats": [words]})
        assert g["text"] == A.HANDS and g["hands"] is True and g["priority"] > basic["priority"], words


def test_hands_without_a_named_performer_and_close_framing_both_count():
    assert A.guard({"performers": [], "beats": ["A hand turns the key."]})["hands"] is True
    assert A.guard({"performers": ["Sege"], "beats": ["Sege looks."], "framing": "Extreme close-up on the face"})["hands"] is True
    assert A.guard({"performers": [], "beats": ["The sea."], "framing": "Close-up on the waves"}) is None


def test_odd_values_in_the_shot_never_break_it():
    assert A.guard({"performers": ["A"], "beats": [None, 5, {"x": 1}], "visual_prompt": 3, "choreography": {"a": 1}})["hands"] is False


def test_the_negative_prompt_gets_the_anatomy_terms_once():
    shot = {"performers": ["Sege"]}
    n = A.negative("text, subtitles", shot)
    assert "fused fingers" in n and n.startswith("text, subtitles")
    assert A.negative(n, shot) == n
    assert A.negative("text", {"performers": [], "beats": ["sea"]}) == "text"
    assert "extra fingers" in A.negative("", shot)


def test_the_fix_is_added_once():
    assert A.ANATOMY_FIX in A.with_fix("")
    once = A.with_fix("Keep the beard")
    assert once.startswith("Keep the beard.") and once.count(A.ANATOMY_FIX) == 1 and A.with_fix(once) == once


# ---------------------------------------------------------------- in the prompt

def test_hands_in_the_shot_put_the_hands_line_in_a_keyframe_and_a_video_prompt():
    shot = {"performers": ["Sege", "Ada"], "beats": ["Sege takes Ada a hand."], "visual_prompt": "They walk through the market holding hands."}
    assert A.HANDS in build(shot, still_model())["prompt"]
    assert A.HANDS in build(shot, video_model())["prompt"]


def test_an_empty_scene_gets_no_anatomy_line():
    p = build({"beats": ["Dawn over the sea."], "visual_prompt": "Dawn over the sea."}, still_model())["prompt"]
    assert A.HANDS not in p and A.BASIC not in p


def test_use_only_my_words_leaves_the_line_out():
    shot = {"performers": ["Sege"], "beats": ["Sege holds a cup."], "custom_prompt": "Sege lifts the cup and drinks.", "prompt_only": True}
    p = build(shot, video_model())["prompt"]
    assert A.HANDS not in p and A.BASIC not in p


def test_a_model_with_a_negative_prompt_is_told_what_to_avoid_even_without_a_look_to_avoid():
    shot = {"performers": ["Sege"], "beats": ["Sege waves."]}
    p = build(shot, video_model(negative=True), project={"look": "A watercolour film."})
    assert "fused fingers" in p["negative_prompt"]
    p2 = build({"performers": [], "beats": ["The sea."]}, video_model(negative=True), project={"look": "A watercolour film."})
    assert "negative_prompt" not in p2


# ---------------------------------------------------------------- the checkers

def test_both_checkers_know_the_anatomy_kind_and_what_to_look_for():
    assert "anatomy" in ST.CHECK_SCHEMA["properties"]["problems"]["items"]["properties"]["kind"]["enum"]
    assert "anatomy" in RV.ISSUE_SCHEMA["properties"]["issues"]["items"]["properties"]["kind"]["enum"]
    for text in (ST.SYSTEM, RV.SYSTEM):
        assert "Count the fingers" in text and "fused" in text
    assert "severity" in ST.CHECK_SCHEMA["properties"]["problems"]["items"]["required"]


def settle(*problems, ok=False, fix=""):
    return ST.settle({"ok": ok, "problems": list(problems), "fix": fix}, "m")


def test_clearly_wrong_hands_fail_the_still_and_carry_the_correction():
    r = settle({"kind": "anatomy", "severity": "major", "detail": "The held hands are fused."}, fix="Keep the light.")
    assert r["ok"] is False and r["fix"].startswith("Keep the light.") and A.ANATOMY_FIX in r["fix"] and r["model"] == "m"


def test_soft_hands_are_flagged_but_do_not_fail_the_still():
    r = settle({"kind": "anatomy", "severity": "minor", "detail": "The left hand is soft."}, ok=True, fix="whatever")
    assert r["ok"] is True and r["fix"] == "" and r["problems"][0]["severity"] == "minor"


def test_a_checker_that_says_failed_for_minor_hands_alone_is_not_believed_over_its_own_list():
    assert settle({"kind": "anatomy", "severity": "minor", "detail": "soft"}, ok=False)["ok"] is True


def test_other_problems_always_fail_whatever_severity_is_claimed():
    for kind in ("collage", "text", "identity", "framing", "missing", "artifact", "look"):
        assert settle({"kind": kind, "severity": "minor", "detail": "x"}, ok=True)["ok"] is False, kind


def test_a_minor_hand_next_to_a_major_problem_still_fails_and_gets_no_anatomy_fix():
    r = settle({"kind": "anatomy", "severity": "minor", "detail": "soft"}, {"kind": "text", "severity": "major", "detail": "title"}, fix="No text.")
    assert r["ok"] is False and r["fix"] == "No text."


def test_a_pass_with_nothing_wrong_and_a_bare_fail_are_left_alone():
    assert settle(ok=True)["ok"] is True
    assert settle(ok=False, fix="x")["ok"] is False and settle(ok=False, fix="x")["fix"] == "x"


def test_rubbish_in_the_problem_list_is_ignored():
    r = ST.settle({"ok": True, "problems": ["x", 3, None, {"kind": "anatomy", "severity": "minor", "detail": "d"}], "fix": ""})
    assert r["ok"] is True and len(r["problems"]) == 1
