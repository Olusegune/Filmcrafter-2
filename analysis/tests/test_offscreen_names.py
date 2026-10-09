"""People who are not in a shot are not named in its prompt. The project-wide rules (world, always, palette, never) used to be pasted unchanged into every shot, so the prompt of a
close-up of one woman also said 'Emmanuel is clean shaven; Mercy has no glasses', 'Mercy left, Patience center, Blessing right', and gave a colour to Solomon, Tunde and Zara:
a good way to get them drawn into the frame. The one deliberate exception is the continuity note, which names who a person is looking at, off screen."""
import pytest

from filmcrafter_engine import render as R
from tests.test_native_dialogue import _talking

CAST = ["Beatrice Queen Bee Adeyemi", "Dr Emmanuel Adeyemi", "Auntie Mercy", "Auntie Patience", "Auntie Blessing", "Solomon Adeyemi", "Tunde Adeyemi", "Zara Adeyemi"]
PLAN = {"meta": {}, "characters": [{"name": n} for n in CAST], "scenes": []}
RULES = ("Preserve faces, outfits, set geometry, eyelines and prop ownership. Queen's gold glasses stay above her forehead. Emmanuel is clean shaven; Mercy has no glasses. "
         "Never add new cast, change ages, mirror hand assignments, invent lyrics or bake readable text into generated shots.")
ALWAYS2 = ("Same home geometry: kitchen left, hall right, staircase right, three center chairs. Same morning; warm east-window light and coherent shadows. "
           "Queen glasses stay at gele front; never duplicate on nose. No new performers; all children are adults; outfits stay fixed. Tablet left hand, stylus right; staff left hand or parked in stand. "
           "Mercy left, Patience center, Blessing right in ensemble blocking. Prop states follow shot continuity notes; no teleporting.")
WORLD = ("A warm stylized 3D Afrobeat family satire. Beatrice Queen Bee Adeyemi turns care into a theatrical family government; Zara answers with calm mutual respect. "
         "Eight adult family performers remain in one morning-lit home. The room has a left kitchen doorway, right hall doorway, right staircase and three central chairs. "
         "Queen leads gesture-driven dance; the Aunties support her in Mercy–Patience–Blessing order. Solomon and the adult children use restrained acting.")
PALETTE = "emerald and burgundy with gold for Queen; cream/brown Solomon; blue/navy Emmanuel; mustard/charcoal Tunde; rust/navy Zara; plum Mercy; amber Patience; cobalt Blessing"
OFF = ["Emmanuel", "Mercy", "Patience", "Blessing", "Solomon", "Tunde", "Zara"]
CLOSEUP = {"id": "S01-05", "start": 8.5, "end": 14.7, "performers": ["Beatrice Queen Bee Adeyemi"], "description": "Close on Beatrice touching her glasses."}


def test_a_word_names_a_character_only_if_it_names_exactly_one():
    t = R._cast_tokens(PLAN)
    assert t["Beatrice"] == t["Queen"] == t["Bee"] == "Beatrice Queen Bee Adeyemi"          # her nickname counts
    assert t["Emmanuel"] == "Dr Emmanuel Adeyemi" and t["Mercy"] == "Auntie Mercy" and t["Zara"] == "Zara Adeyemi"
    assert "Adeyemi" not in t and "Auntie" not in t and "Dr" not in t                         # the family name and titles name nobody in particular


def test_a_close_up_keeps_the_set_the_light_and_its_own_person_and_drops_everyone_else():
    for text in (RULES, ALWAYS2, WORLD, PALETTE):
        out = R.for_this_shot(text, CLOSEUP, PLAN)
        for name in OFF:
            assert name not in out, (name, out)
    assert "Queen's gold glasses stay above her forehead" in R.for_this_shot(RULES, CLOSEUP, PLAN)
    assert "Never add new cast" in R.for_this_shot(RULES, CLOSEUP, PLAN)
    a = R.for_this_shot(ALWAYS2, CLOSEUP, PLAN)
    assert "Same home geometry" in a and "Same morning" in a and "Queen glasses stay at gele front" in a and "Tablet left hand, stylus right" in a
    assert R.for_this_shot(PALETTE, CLOSEUP, PLAN) == "emerald and burgundy with gold for Queen."
    w = R.for_this_shot(WORLD, CLOSEUP, PLAN)
    assert "Beatrice Queen Bee Adeyemi turns care into a theatrical family government" in w and "The room has a left kitchen doorway" in w


def test_a_shot_with_two_people_keeps_what_names_either():
    shot = {"id": "S01-06", "performers": ["Beatrice Queen Bee Adeyemi", "Auntie Mercy"]}
    out = R.for_this_shot(RULES, shot, PLAN)
    assert "Mercy has no glasses" in out and "clean shaven" not in out                        # "Emmanuel is clean shaven; Mercy has no glasses": Mercy is here, Emmanuel is not
    assert "Emmanuel" not in out and "Queen's gold glasses" in out
    assert "plum Mercy" in R.for_this_shot(PALETTE, shot, PLAN) and "Solomon" not in R.for_this_shot(PALETTE, shot, PLAN)


def test_a_shot_with_nobody_named_in_it_names_nobody():
    out = R.for_this_shot(ALWAYS2, {"id": "S01-01", "performers": []}, PLAN)
    assert "Same home geometry" in out and not any(n in out for n in OFF + ["Queen"])


def test_a_lowercase_word_is_not_mistaken_for_a_name():
    out = R.for_this_shot("Burgundy runner with gold trim and bee motifs. The queen of the hive is not a character.", {"id": "x", "performers": ["Auntie Mercy"]}, PLAN)
    assert "bee motifs" in out and "queen of the hive" in out                                 # only the capitalised name counts


def test_nothing_changes_when_no_one_is_named_in_the_plan_or_when_it_is_switched_off():
    assert R.for_this_shot(RULES, CLOSEUP, {"meta": {}, "characters": []}) == RULES
    assert R.for_this_shot(RULES, CLOSEUP, PLAN, {"bible_all_shots": True}) == RULES


def test_empty_text_stays_empty():
    assert R.for_this_shot("", CLOSEUP, PLAN) == ""
    assert R.for_this_shot("Emmanuel is clean shaven.", CLOSEUP, PLAN) == ""                  # and a block that is only about someone else vanishes


def prompt(shot, said=None):
    project = {"look": {"style": "auto"}, "bible": {"world": WORLD, "rules": RULES, "palette": PALETTE}}
    return R.compile_request(shot, None, PLAN, project, _talking(), [], said=said)["prompt"]


def test_the_whole_prompt_of_a_close_up_names_only_the_off_screen_person_the_continuity_note_does():
    shot = {**CLOSEUP, "continuity": "Beatrice Queen Bee Adeyemi looks screen-right toward Dr Emmanuel Adeyemi (off-screen)."}
    p = prompt(shot)
    assert p.count("Emmanuel") == 1 and "toward Dr Emmanuel Adeyemi (off-screen)" in p       # the eyeline: deliberate
    for name in OFF[1:]:
        assert name not in p, name
    assert "Queen's gold glasses stay above her forehead" in p and "The room has a left kitchen doorway" in p


def test_the_other_performers_do_not_lip_sync_line_stays_for_a_lone_speaker():
    """It names nobody, and it guards against background people moving their lips in a shot whose plan lists only one performer."""
    said = {"performer": "Beatrice Queen Bee Adeyemi", "lyrics": ["I knew that."], "spoken": True}
    assert "Other performers do not lip-sync" in prompt(CLOSEUP, said)
