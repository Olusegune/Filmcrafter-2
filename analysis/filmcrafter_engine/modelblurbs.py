"""What each model family is good for, in a sentence a filmmaker can use to choose, and why to stay with one.

These come from what FilmCrafter itself knows (which models see your reference pictures, which draw clean text, which take a start and an end picture, which can speak, which a real render
has proved) and from each model's published features. They say what a model is for; they do not rank the pictures it makes, because that depends on your project. Prices are not written
here: the picker shows the real price per shot next to each blurb.

Keys are the family names in router.FAMILIES (a test checks that every family has a blurb).
"""
from __future__ import annotations

# strength: what it is good at. consider: when to pick it. watch: the honest catch (may be empty).
BLURBS: dict[str, dict[str, str]] = {
    # ---- pictures (keyframes, end frames, character sheets)
    "gpt-image": {"strength": "Follows detailed instructions closely and draws clean, readable text (signs, titles, labels). Sees your character sheets.",
                  "consider": "For hero shots, anything with writing in it, and projects where the prompt is long and specific.", "watch": "Costs the most of the picture models."},
    "gpt-image-sunburst": {"strength": "Another model in the GPT Image 2.5 line: the same instruction-following, reads your character sheets.",
                           "consider": "If you like how GPT Image 2.5 Flare follows a prompt and want to compare a sibling on one shot first.", "watch": "Try one shot before using it for the whole project."},
    "nano-banana": {"strength": "Keeps people looking like themselves from your reference pictures, at a low price. FilmCrafter's Balanced choice.",
                    "consider": "For a whole project on a budget, and when the same characters appear in many shots.", "watch": "Check hands and faces on important shots."},
    "seedream": {"strength": "Good all-round pictures with clean text, and it reads reference pictures.",
                 "consider": "A balanced alternative when you want a different look from Nano Banana at a modest price.", "watch": ""},
    "seedream-pro": {"strength": "ByteDance's best Seedream: sharp detail, clean text (including in many languages), and up to 10 reference pictures. Goes up to 2K.",
                     "consider": "For hero keyframes. Directly from BytePlus the price is published, so the price shown before you render is exact.",
                     "watch": "It has no 4K on any provider: for 4K choose Seedream 4.5 or 5.0 Lite."},
    "seedream-flash": {"strength": "A fast, cheap Seedream for drafts and quick look-tests.",
                       "consider": "To try a look or a whole storyboard cheaply before spending on a better model.", "watch": "Expect less fine detail than the full models."},
    "qwen-edit": {"strength": "Edits from your reference pictures and keeps faces and layout steady, at a very low price.",
                  "consider": "For low-cost keyframes of characters you have already designed.", "watch": "Less polished than the premium picture models."},
    "flux-klein": {"strength": "A small, quick, inexpensive model that can see your reference pictures.",
                   "consider": "For drafts and rough boards.", "watch": "A small model: expect less fine detail, and check hands and faces more closely."},
    # ---- video
    "seedance": {"strength": "Takes a start AND an end picture, can also use reference pictures, video and sound, and can speak lines. FilmCrafter's Premium video choice.",
                 "consider": "For shots that must land on an end frame, shots with sung or spoken lines, and the best motion.", "watch": "Costs more per shot."},
    "kling": {"strength": "Kling 3.0 takes a start and an end picture, and Kling 2.6 can speak lines.",
              "consider": "As an alternative look to Seedance, and for shots built on a start and an end picture.", "watch": "Which Kling you get depends on the provider."},
    "veo": {"strength": "Makes its own sound and speech along with the picture.",
            "consider": "For scenes where people speak or sing, and film-like shots.", "watch": "Priced as a premium model."},
    "hailuo": {"strength": "A moderate price. Its Hailuo 02 version is proven in FilmCrafter to land on an end picture.",
               "consider": "A dependable middle choice for start-and-end shots.", "watch": ""},
    "wan": {"strength": "Low price. FilmCrafter's Balanced video choice.",
            "consider": "For a whole video on a budget.", "watch": ""},
    "ltx": {"strength": "Fast generation from a start picture.",
            "consider": "For quick tests of movement.", "watch": ""},
    "vidu-turbo": {"strength": "The lowest-priced video model proven in FilmCrafter to land on its end picture.",
                   "consider": "To test a shot, or to make many shots very cheaply.", "watch": "A quick, low-cost model: look closely at the shots that matter."},
    "pixverse": {"strength": "Low price, with a version made for moving from a start picture to an end picture.",
                 "consider": "For inexpensive transformations and transitions.", "watch": ""},
    "wan-turbo": {"strength": "A cheap, quick Wan; proven in FilmCrafter to land on an end picture.",
                  "consider": "For cheap tests and drafts.", "watch": "Less polished than Wan 3.0."},
    "hailuo-fast": {"strength": "A lower-priced Hailuo for drafts.",
                    "consider": "To check a shot's idea before paying for the full model.", "watch": ""},
}

ONE_MODEL_ADVICE = ("Use one picture model for the whole project. Two models draw people, light and colour differently, so mixing them across keyframes can make a character look "
                    "different from shot to shot. If you do switch part-way, redo the earlier keyframes on the new model, or keep the two apart: one for the whole cast, one for "
                    "scenery only.")


def blurb(family: str) -> dict:
    return {**{"strength": "", "consider": "", "watch": ""}, **BLURBS.get(family, {})}
