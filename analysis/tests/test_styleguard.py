"""Never drift to photorealism: a project in a stylised look keeps it, even when the script, the Director or the Bible ask for realism."""
import re

import pytest

from pulseframe_analysis import render as R
from pulseframe_analysis import styleguard as SG
from tests.test_video_models import f, kie

IMG = lambda limit=None: kie("google/nano-banana-edit", f("prompt", required=True, **({"max_length": limit} if limit else {})), f("image_urls", "array", items="string", max_items=8))
PLAN = {"meta": {"VISUAL STYLE": "Cinematic contemporary African realism interrupted by restrained psychological surrealism. Warm amber sunlight represents safety."}, "characters": []}
SHOT = {"id": "S01-01", "start": 0, "end": 4, "performers": ["Sege"], "framing": "close-up", "visual_prompt": "A photographic, realistic close-up of Sege with film grain and visible skin pores, 35mm film look."}


def without_lock(text):
    """The prompt minus the style-lock sentences, which name what the look is NOT (and so contain the words 'photorealism' and 'realistic' on purpose)."""
    return re.sub(r"Style lock:.*?\bNever:[^.]*\.|Style lock:[^.]*\.[^.]*\.", "", text, flags=re.S)


def has(word, text):
    return re.search(r"\b" + word, text, re.I) is not None


def prompt(look, plan=PLAN, shot=SHOT, model=None, project_extra=None):
    project = {"look": look, **(project_extra or {})}
    return R.compile_request(shot, None, plan, project, model or IMG(), [])["prompt"]


# ---------------------------------------------------------------- the words
@pytest.mark.parametrize("text,expect_gone", [
    ("contemporary African realism", "realism"), ("a photorealistic face", "photoreal"), ("live-action footage", "live-action"), ("documentary style", "documentary"),
    ("shot on ARRI Alexa", "ARRI"), ("heavy film grain", "film grain"), ("35mm film stock", "35mm"), ("a hyper-realistic portrait", "hyper"), ("a photograph of a boy", "photograph"),
])
def test_requests_for_a_photograph_are_removed_for_a_stylised_look(text, expect_gone):
    out = SG.sanitize(text, {"look": {"style": "feature-3d"}}, "feature-3d")
    assert expect_gone.lower() not in out.lower(), out


def test_the_rest_of_the_meaning_is_kept_and_the_punctuation_is_tidy():
    out = SG.sanitize("Cinematic contemporary African realism interrupted by restrained psychological surrealism. Warm amber sunlight, film grain, represents safety.", {"look": {"style": "feature-3d"}}, "feature-3d")
    assert "contemporary African" in out and "psychological surrealism" in out and "Warm amber sunlight" in out and "safety" in out
    assert ",," not in out and " ," not in out and "  " not in out and ", ." not in out


def test_a_removed_adjective_does_not_leave_broken_grammar():
    out = SG.sanitize("A photographic, realistic close-up of Sege with film grain and visible skin pores.", {"look": {"style": "feature-3d"}}, "feature-3d")
    assert out.startswith("A believable close-up of Sege") and "with and" not in out and "visible skin detail" in out


@pytest.mark.parametrize("look_id,fam", [("feature-3d", "stylised"), ("anime", "stylised"), ("claymation", "stylised"), ("rotoscope", "stylised"), ("photoreal-cgi", "real"), ("live-action", "real"), ("auto", "unsure"), ("custom", "unsure"), (None, "unsure")])
def test_which_looks_are_stylised(look_id, fam):
    assert SG.family(look_id) == fam


def test_nothing_is_rewritten_for_a_look_that_asks_for_realism_or_for_the_references():
    for lid in ("photoreal-cgi", "live-action", "auto"):
        assert SG.sanitize("a realistic photograph, film grain", {"look": {"style": lid}}, lid) == "a realistic photograph, film grain"


def test_the_guard_can_be_switched_off_in_the_project():
    p = {"look": {"style": "feature-3d", "guard": False}}
    assert SG.sanitize("realistic", p, "feature-3d") == "realistic" and SG.lock(p, {"id": "feature-3d", "prompt": "x", "avoid": ""}) is None


def test_junk_text_does_not_crash():
    for t in (None, "", 5, ["a"]):
        SG.sanitize(t, {"look": {"style": "feature-3d"}}, "feature-3d")


# ---------------------------------------------------------------- the prompt
def test_a_3d_project_prompt_has_no_request_for_realism_anywhere_and_says_what_it_is_not():
    p = prompt({"style": "feature-3d", "notes": "Match the character sheet exactly."})
    for bad in ("realism", "realistic", "photographic", "film grain", "skin pores", "35mm"):
        assert not has(bad, without_lock(p)), (bad, p)
    assert "Style lock: High-end 3D animated feature film style" in p
    assert "not a photograph and not live-action footage" in p and "photorealistic humans" in p            # what the look says to avoid is in the lock


def test_the_same_shot_in_a_live_action_project_keeps_its_wording():
    p = prompt({"style": "live-action"})
    assert "photographic" in p and "film grain" in p and "Style lock" not in p


def test_a_project_on_match_the_references_keeps_everything_and_gets_no_lock():
    p = prompt({"style": "auto"})
    assert "photographic" in p and "Style lock" not in p


def test_the_style_lock_is_the_last_thing_dropped_when_the_prompt_has_to_be_cut():
    trace = []
    R.compile_request(SHOT, None, PLAN, {"look": {"style": "feature-3d"}}, IMG(limit=400), [], trace=trace)
    lock = [b for b in trace if b["text"].startswith("Style lock")]
    assert lock and lock[0]["kept"] and lock[0]["priority"] == SG.LOCK_PRIORITY
    assert any(not b["kept"] for b in trace), "the test only means something if something was cut"


def test_the_bible_and_the_directors_wording_are_cleaned_too():
    project = {"look": {"style": "stylized-3d"}, "bible": {"world": "A realistic, documentary-style Lagos.", "rules": "Photorealistic skin; hyper-realistic fabric.", "palette": "amber"}}
    out = without_lock(R.compile_request(SHOT, None, PLAN, project, IMG(), [])["prompt"])
    for bad in ("realistic", "documentary", "photoreal", "hyper"):
        assert not has(bad, out), bad
    assert "lagos" in out.lower() and "amber" in out.lower()


def test_a_video_prompt_is_guarded_the_same_way():
    vid = kie("bytedance/seedance-2-fast", f("prompt", required=True), f("first_frame_url"), f("duration", "integer", minimum=4, maximum=15, required=True))
    p = R.compile_request(SHOT, None, PLAN, {"look": {"style": "feature-3d"}}, vid, [])["prompt"]
    assert "Style lock" in p and not has("realism", without_lock(p)) and "film grain" not in p.lower()


def test_the_plain_avoid_line_is_not_repeated_beside_the_lock():
    assert prompt({"style": "feature-3d"}).count("photorealistic humans") == 1


def test_a_look_chosen_in_the_project_wins_over_a_script_that_says_realism():
    """The reported project: look feature-3d, script VISUAL STYLE 'contemporary African realism'."""
    p = prompt({"style": "feature-3d", "notes": "Match the character sheet exactly: same character designs, skin tones, hair and outfits."})
    assert "African" in p and not has("realism", without_lock(p))
