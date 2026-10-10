"""The film's kind of look (photorealistic, 3D, 2D, crafts) and the twelve principles of animation: what they are, what is saved, and what reaches the prompts."""
import json
import os

import pytest

from filmcrafter_engine import animation_principles as AP
from filmcrafter_engine import bible, make, render as R, shots, story

SCRIPT = """INT. KITCHEN - MORNING

Sarah jumps off the step, her coat flaring, and lands laughing.

SARAH
He said he would call.

EXT. PLATFORM - NIGHT

Rain on the roof.
"""


def field(name, type="string", **kw):
    return {"name": name, "type": type, "items": kw.get("items"), "enum": kw.get("enum"), "default": kw.get("default"), "minimum": None, "maximum": None, "max_items": None,
            "max_length": None, "description": kw.get("description", ""), "required": kw.get("required", False)}


def still_model():
    return R._finish("fal", "t/i", "Still", "text-to-image", [field("prompt")])


def video_model():
    return R._finish("fal", "t/v", "Video", "image-to-video", [field("prompt"), field("image_url", description="Start image"), field("duration", enum=["5"])])


def build(shot, man, look="feature-3d", project=None):
    s = {"id": "S01-01", "start": 0.0, "end": 4.0, "performers": ["Sarah"], "beats": ["x"], **shot}
    return R.compile_request(s, None, {"meta": {}}, {"look": {"style": look}, **(project or {})}, man, [])


JUMP = {"visual_prompt": "Sarah jumps off the step, her coat flaring, and lands laughing", "performance": "surprised joy"}


def test_there_are_twelve_and_each_has_words_for_a_person_and_for_the_model():
    assert len(AP.PRINCIPLES) == 12 == len(set(AP.IDS))
    for p in AP.PRINCIPLES:
        assert p["name"] and p["plain"] and (p["video"] or p["still"]), p["id"]
        assert set(p["fams"]) <= set(AP.FAMILIES)


def test_every_look_belongs_to_a_family_and_the_three_main_ones_are_there():
    from filmcrafter_engine import make as M
    styles = {s["id"] for s in json.load(open(R.STYLES_PATH, encoding="utf-8"))["styles"]}
    fams = {AP.style_family(i) for i in styles}
    assert set(AP.FAMILIES) <= fams and fams <= set(AP.FAMILIES) | {"genre", "auto"}
    assert AP.family("live-action") == "photoreal" and AP.family("feature-3d") == "3d" and AP.family("hand-drawn-2d") == "2d" and AP.family("claymation") == "craft"
    for lane, look in M.LOOK_FOR_LANE.items():
        assert look in styles, lane


def test_a_jump_gets_anticipation_squash_and_follow_through_in_an_animated_look():
    text = AP.direction({}, JUMP, "feature-3d", True)
    assert text.startswith("Animation craft:")
    assert "prepared by a small opposite move" in text and "squash" in text.lower()
    ids = AP.pick({}, JUMP, "hand-drawn-2d", True)
    assert {"anticipation", "squash-stretch"} <= set(ids) and len(ids) <= 4


def test_photoreal_keeps_only_screen_craft_and_never_squash_or_exaggeration():
    ids = AP.pick({}, JUMP, "live-action", True)
    assert ids and "squash-stretch" not in ids and "exaggeration" not in ids and "solid-drawing" not in ids
    assert AP.direction({}, JUMP, "live-action", True).startswith("Screen craft:")


def test_what_the_person_switched_off_is_never_added():
    off = {"animation": {"principles": []}}
    assert AP.direction(off, JUMP, "feature-3d", True) == ""
    only = {"animation": {"principles": ["anticipation"]}}
    assert AP.pick(only, JUMP, "feature-3d", True) == ["anticipation"]


def test_a_still_gets_pose_wording_not_motion_wording():
    t = AP.direction({}, JUMP, "feature-3d", False)
    assert t and "keep moving a beat longer" not in t and "eases in and out" not in t


def test_clean_keeps_only_real_ids_in_order():
    assert AP.clean(None) is None
    assert AP.clean(["timing", "nope", "appeal", "timing"]) == ["timing", "appeal"]
    with pytest.raises(SystemExit):
        AP.clean("timing")


def test_the_prompts_carry_the_craft_for_video_and_for_stills_and_use_only_my_words_skips_it():
    v = build(JUMP, video_model())["prompt"]
    assert "Animation craft:" in v
    assert "Animation craft:" in build(JUMP, still_model())["prompt"]
    assert "Screen craft:" in build(JUMP, video_model(), look="live-action")["prompt"]
    mine = build({**JUMP, "custom_prompt": "Sarah jumps.", "prompt_only": True}, video_model())["prompt"]
    assert "Animation craft:" not in mine
    off = build(JUMP, video_model(), project={"animation": {"principles": []}})["prompt"]
    assert "Animation craft:" not in off


@pytest.fixture
def film(tmp_path):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    return d


def test_the_bible_offers_families_and_saves_a_style_within_one(film):
    v = bible.view(film)
    assert [f["id"] for f in v["families"]] == ["photoreal", "3d", "2d", "hybrid", "craft", "art"] and v["family"] == ""
    assert sum(len(f["lanes"]) for f in v["families"]) == len(v["lanes"]) == len(set(v["lanes"]))
    assert all(f["looks"] for f in v["families"]) and len(v["genres"]) >= 10
    v = bible.update_rules(film, {"style": {"lane": "feature 3D"}})
    assert v["family"] == "3d" and v["style"]["lane"] == "feature 3D" and v["principles_custom"] is False
    assert "anticipation" in v["principles_on"] and len(v["principles"]) == 12
    assert bible.update_rules(film, {"style": {"lane": "photoreal CGI"}})["family"] == "photoreal"
    with pytest.raises(SystemExit):
        bible.update_rules(film, {"style": {"lane": "made up"}})


def test_principles_are_saved_cleaned_and_can_return_to_the_styles_choice(film):
    bible.update_rules(film, {"style": {"lane": "hand-drawn 2D"}})
    v = bible.update_rules(film, {"style": {"principles": ["timing", "bogus", "anticipation"]}})
    assert v["principles_custom"] and v["principles_on"] == ["anticipation", "timing"]
    v = bible.update_rules(film, {"style": {"principles": None}})
    assert not v["principles_custom"] and "squash-stretch" in v["principles_on"]


def test_the_film_carries_the_look_and_the_principles_into_the_render_project(film):
    bible.update_rules(film, {"style": {"lane": "feature 3D", "principles": ["anticipation", "timing"]}})
    shots.breakdown(film)
    rd = make.sync(film)["render_dir"]
    pj = json.load(open(os.path.join(rd, "project.json")))
    assert pj["look"]["style"] == "feature-3d" and pj["animation"] == {"principles": ["anticipation", "timing"]}
    bible.update_rules(film, {"style": {"principles": None}})
    pj = json.load(open(os.path.join(make.sync(film)["render_dir"], "project.json")))
    assert "animation" not in pj


# ---------------------------------------------------------------- the looks, strongly injected

def test_every_look_has_strong_wording_and_a_family():
    sty = AP.styles()
    assert len(sty) >= 100
    for k, v in sty.items():
        assert v["family"] in set(AP.FAMILIES) | {"genre", "auto"}, k
        assert len(v["prompt"]) > 60 and v["avoid"] and v["description"], k
        assert ":" in v["prompt"], k                 # the part before the first colon is the look's name, which leads the prompt and the style lock


def test_photoreal_looks_are_never_reworded_and_drawn_looks_always_are():
    from filmcrafter_engine import styleguard as SG
    for k, v in AP.styles().items():
        if v["family"] == "photoreal":
            assert SG.family(k) == "real", k
    assert SG.family("hyperreal") == "real" and SG.family("claymation") == "stylised" and SG.family("g-epic-fantasy") == "stylised"
    assert "photograph" not in SG.sanitize("a photographic portrait", {"look": {"style": "claymation"}}, "claymation")
    assert "photographic" in SG.sanitize("a photographic portrait", {"look": {"style": "hyperreal"}}, "hyperreal")


def test_the_look_leads_the_still_and_the_video_and_is_locked():
    for m in (still_model(), video_model()):
        p = build(JUMP, m, look="claymation")["prompt"]
        assert p.startswith("Claymation."), p[:60]
        assert "Look: Claymation:" in p and "Style lock: Claymation." in p and "Never: smooth CGI surfaces" in p
    mine = build({**JUMP, "custom_prompt": "Sarah jumps.", "prompt_only": True}, video_model(), look="claymation")["prompt"]
    assert not mine.startswith("Claymation.")


def test_a_genre_feel_is_layered_on_the_look_and_never_replaces_it():
    look = R.resolve_look({"look": {"style": "stop-motion", "genre": "g-biblical-epic"}})
    assert look["id"] == "stop-motion" and look["prompt"].startswith("Stop-motion animation:") and "Biblical epic feel" in look["prompt"]
    assert "modern objects" in look["avoid"] and "photorealistic humans" in look["avoid"]
    p = build(JUMP, video_model(), look="stop-motion", project={"look": {"style": "stop-motion", "genre": "g-biblical-epic"}})["prompt"]
    assert p.startswith("Stop-motion animation.") and "Biblical epic feel" in p
    assert R.resolve_look({"look": {"style": "stop-motion", "genre": "hyperreal"}})["prompt"].count("Hyperrealistic") == 0     # only real genre layers are accepted


COOGLER = {"name": "Ryan Coogler", "camera": "Long moving takes that follow people through a place", "light": "Warm natural light on skin",
           "movement": "Groups moving and laughing together", "editing": "Hold the take as long as it plays"}


def test_a_directors_approach_and_a_look_reach_every_prompt_together():
    proj = {"look": {"style": "stop-motion"}, "direction_brief": COOGLER}
    for m in (still_model(), video_model()):
        p = build(JUMP, m, look="stop-motion", project=proj)["prompt"]
        assert "Directing approach (camera: Long moving takes" in p and "light: Warm natural light on skin" in p
        assert "Stop-motion animation" in p and "Style lock: Stop-motion animation." in p
        assert "Ryan Coogler" not in p                # traits, never a living filmmaker's name, go to the model
    assert "Directing approach" not in build(JUMP, video_model(), look="stop-motion", project={"look": {"style": "stop-motion"}})["prompt"]
    own = build({**JUMP, "custom_prompt": "Sarah jumps.", "prompt_only": True}, video_model(), look="stop-motion", project=proj)["prompt"]
    assert "Directing approach" not in own


def test_applying_a_direction_keeps_the_look_and_adds_the_approach(tmp_path):
    from filmcrafter_engine import directions_library as DL
    d = tmp_path / "r"
    d.mkdir()
    (d / "project.json").write_text(json.dumps({"title": "P", "look": {"style": "stop-motion"}}))
    r = DL.apply(str(d), "ryan-coogler")
    pj = json.load(open(d / "project.json"))
    assert pj["look"]["style"] == "stop-motion" and not any(c.startswith("look:") for c in r["changed"])
    assert pj["direction_brief"]["camera"] and pj["direction_brief"]["name"] == "Ryan Coogler"


def test_the_exact_look_and_genre_are_saved_validated_and_carried(film):
    v = bible.update_rules(film, {"style": {"look": "hyperreal"}})
    assert v["look"] == "hyperreal" and v["family"] == "photoreal" and v["style"]["lane"] == "Hyperrealism"
    for bad in ({"look": "g-epic-fantasy"}, {"look": "nope"}, {"genre": "hyperreal"}):
        with pytest.raises(SystemExit):
            bible.update_rules(film, {"style": bad})
    v = bible.update_rules(film, {"style": {"look": "claymation", "genre": "g-dark-fantasy"}})
    assert v["genre"] == "g-dark-fantasy" and v["family"] == "craft"
    shots.breakdown(film)
    pj = json.load(open(os.path.join(make.sync(film)["render_dir"], "project.json")))
    assert pj["look"] == {"style": "claymation", "genre": "g-dark-fantasy"}
    v = bible.update_rules(film, {"style": {"genre": ""}})
    assert v["genre"] == ""
    v = bible.update_rules(film, {"style": {"lane": "feature 3D"}})            # picking a broad lane afterwards replaces the exact look
    assert v["look"] == "feature-3d"


def test_a_quiet_acting_profile_drops_exaggeration_unless_the_person_chose_it():
    shot = {"visual_prompt": "She screams in shock", "performance": "fear"}
    assert "exaggeration" in AP.pick({}, shot, "feature-3d", True)
    assert "exaggeration" not in AP.pick({"performance": {"default": "restrained"}}, shot, "feature-3d", True)
    assert "exaggeration" in AP.pick({"performance": {"default": "restrained"}, "animation": {"principles": ["exaggeration"]}}, shot, "feature-3d", True)
