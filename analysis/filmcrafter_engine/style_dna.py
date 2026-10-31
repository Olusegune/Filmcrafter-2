"""Style DNA: a look described as structured parts (how people are built, how surfaces look, how light and shadow behave, how the camera and the animation move, what must never appear), and the
model-specific wording that is made FROM those parts, rather than a style name used as the whole prompt.

A look in styles.json may carry a `dna` block (and may `inherit` another look's). `compile_dna` turns it into the text fields the render already uses:
  prompt          the short style line that goes into every picture and video prompt
  figures         how the people themselves are built in this look (used when a shot is restyled, see render.py)
  figures_avoid   what the people must not look like
  avoid           what the whole picture must not look like
The compiled text is stored beside the DNA in styles.json and a test keeps the two in step, so nothing else has to know about DNA.

Cinematic Storybook 2.5D and its six variations are defined here. They are written from the general visual grammar of the owner's own five reference pictures (tall narrow stylised figures,
trim bands of repeating geometric pattern, matte painted flat shapes with fine dry-brush grain, graphic cast shadows, a sand and terracotta palette cooled with dusty blue, layered blocky
architecture, warm shafts of light against cool shadow, restrained motion). No character, scene or picture from them is reproduced, and the pictures themselves are not part of the product. These
are visual variations, not historically verified reconstructions.

  python -m filmcrafter_engine.style_dna            prints the entries that styles.json should hold (the test compares them)
"""
from __future__ import annotations

import json
import sys

FIELDS = ("character_design", "body_proportions", "facial_proportions", "line_weight", "outline", "surface_texture", "palette", "shadow_construction", "lighting", "rendering_material",
          "background_design", "environmental_depth", "camera_language", "animation_style", "motion_frequency", "expressiveness", "post_treatment", "negatives")
FIELD_NAMES = {"character_design": "Character design", "body_proportions": "Body proportions", "facial_proportions": "Facial proportions", "line_weight": "Line weight", "outline": "Outline",
               "surface_texture": "Surface texture", "palette": "Palette", "shadow_construction": "Shadow construction", "lighting": "Lighting", "rendering_material": "Rendering material",
               "background_design": "Background design", "environmental_depth": "Environmental depth", "camera_language": "Camera language", "animation_style": "Animation style",
               "motion_frequency": "Motion frequency", "expressiveness": "Character expressiveness", "post_treatment": "Post-production treatment", "negatives": "What to avoid"}
MAX_FIELD = 360
MAX_PROMPT = 760

STORYBOOK = {
    "character_design": "stylised angular human figures, simplified but expressive, readable as a silhouette; simple draped clothing trimmed with bands of repeating geometric pattern",
    "body_proportions": "elongated: small head on a long neck, narrow shoulders, long slim arms, hands and legs",
    "facial_proportions": "large readable eyes with small dark pupils, strong simple brow, nose and jaw planes, small quiet mouth; feeling carried by the eyes and brows",
    "line_weight": "no heavy outlines: shapes are defined by edges of flat colour, with a few thin dark accent lines for folds, brows and hands",
    "outline": "none, or very thin and irregular; never a uniform thick contour",
    "surface_texture": "matte painted flat shapes with fine dry-brush grain and subtle paper texture; hatched marks for fabric folds; no gloss",
    "palette": "warm sand, ochre, terracotta and cream, cooled with dusty blue, turquoise and slate in shadow and sky; small accents of red and cobalt in trim and pottery",
    "shadow_construction": "graphic shadow shapes: hard-edged flat cast shadows (palm fronds, beams, window grids) across floors and walls, the shaded side of forms one flat cooler tone",
    "lighting": "one clear motivated light, often low sun through a window or doorway making visible shafts with floating dust; warm light against cool shadow",
    "rendering_material": "flat painted shapes with a tactile grain; mud-brick, plaster, woven reed, linen and pottery all read as matte",
    "background_design": "simplified blocky architecture in layered planes; patterned pots, baskets, awnings and rugs as set dressing; painted ornament bands",
    "environmental_depth": "2D illustration with 3D-like depth: foreground framing objects, midground action, background buildings and distant haze, with gentle atmospheric perspective that lightens and cools the distance",
    "camera_language": "composed like an illustrated storybook frame: clear staging, wide establishing views, foreground objects framing the action, restrained slow push-ins and parallax drifts",
    "animation_style": "limited, deliberate animation: held poses, slow gestures, small eye and brow changes; the camera and the light do most of the moving",
    "motion_frequency": "low: animated on twos or threes with long holds",
    "expressiveness": "restrained but readable: posture, eyes and brows, not broad grimaces",
    "post_treatment": "soft matte finish, a fine gentle grain, light bloom only in the light shafts; no overall colour wash",
    "negatives": ("waxy or plastic skin, glossy surfaces, photorealistic skin and hair, a uniform yellow or golden tint over everything, heavy bloom, random texture noise, inconsistent proportions between shots, "
                  "face morphing, smooth 3D-render faces, thick black outlines, text, logos or a video player interface in the frame"),
}

BASE_ID = "cinematic-storybook-25d"
# id -> (name, description, overrides of the base DNA)
VARIANTS = {
    BASE_ID: ("Cinematic Storybook 2.5D", "Illustrated storybook frames with layered depth: tall stylised figures, matte painted shapes, graphic shadows and warm light shafts.", {}),
    "historical-storybook": ("Storybook: historical", "The storybook look for the ancient and historical world: mud-brick towns, rivers, temples. A visual interpretation, not a reconstruction.", {
        "background_design": "mud-brick and white-plaster towns, riverbanks with reeds and sails, temples with painted ornament bands; woven mats, clay pots and linen as set dressing",
        "character_design": "stylised angular human figures in simple wrapped linen and tunics with geometric trim; jewellery and hair shown as simple graphic shapes",
        "palette": "warm sand, ochre, terracotta and cream with river blue and turquoise; small accents of red, cobalt and gold in trim"}),
    "biblical-epic-illustration": ("Storybook: epic illustration", "The storybook look at epic scale: robed figures, vast desert and sky, dramatic light. A visual interpretation, not a reconstruction.", {
        "background_design": "monumental simple architecture and wide desert, hills and skies; tents, stone steps, simple furnishings; scale shown by small figures against vast shapes",
        "lighting": "dramatic motivated light: low sun, firelight and torchlight, strong shafts and long graphic shadows; deep cool shadow against a warm key",
        "camera_language": "wide, composed frames with figures small against the land, low angles, slow push-ins; stillness and scale over rapid cutting",
        "palette": "deep ochre, burnt sienna and cream with night indigo and slate; sparing accents of crimson and gold"}),
    "modern-urban-storybook": ("Storybook: modern urban", "The storybook look in a present-day city: contemporary clothes and streets, the same figures and matte painted shapes.", {
        "background_design": "simplified blocky city streets, shopfronts, stairs, balconies and rooftops with no readable signs; bikes, market stalls, wires and plants as set dressing",
        "character_design": "stylised angular human figures in contemporary clothing with clean geometric details; bags, headphones and sneakers drawn as simple flat shapes",
        "palette": "warm concrete and brick, teal, mustard and coral with cool blue shadow; small accents of red and cobalt in clothing"}),
    "african-folktale-illustration": ("Storybook: folktale illustration", "The storybook look for village and folk tales: compounds, open land, woven and patterned cloth, told as an illustrated story.", {
        "background_design": "village compounds of earth walls and thatch, open land with large trees, courtyards, market mats and gourds; woven and printed cloth pattern as ornament",
        "character_design": "stylised angular human figures in wrapped cloth and simple garments with bold printed pattern bands; hair and head wraps as clear graphic shapes",
        "palette": "earth red, ochre and cream with saturated indigo and deep green; small accents of yellow and turquoise in cloth pattern"}),
    "fantasy-storybook": ("Storybook: fantasy", "The storybook look for invented lands: towers, floating lights, simplified creatures, twilight colour.", {
        "background_design": "invented simplified towers, bridges, floating stones and forests in layered planes; lanterns, banners and creatures drawn as clean flat shapes",
        "lighting": "twilight or magical light kept to a few clear shapes: lantern glow, soft shafts and glowing edges, with the rest quiet and cool",
        "palette": "twilight teal, violet and slate with warm amber light; small accents of coral and gold for magic",
        "negatives": "waxy or plastic skin, glossy surfaces, photorealistic detail, an overall colour wash, heavy bloom across the whole frame, inconsistent proportions between shots, face morphing, smooth 3D-render faces, thick black outlines, text or logos in the frame"}),
    "educational-documentary-illustration": ("Storybook: educational documentary", "The storybook look for explainers: clear staging, calm light, room left for labels, maps and graphics.", {
        "background_design": "clean simplified places with clear readable shapes and uncluttered planes; maps, cutaways and diagrams drawn in the same flat painted style",
        "lighting": "even, soft, readable light with gentle shadows; nothing dramatic that would hide a detail the viewer must see",
        "camera_language": "clear, steady, well-framed views with empty space left for labels, captions and graphics; slow, even pans and push-ins",
        "palette": "warm sand, cream and terracotta with calm blue and teal; one clear accent colour for what the viewer should notice"}),
}


def merged(entry_dna: dict, base: dict | None = None) -> dict:
    out = dict(base or {})
    out.update({k: v for k, v in (entry_dna or {}).items() if k in FIELDS and isinstance(v, str) and v.strip()})
    return {k: " ".join(out[k].split())[:MAX_FIELD * 2] for k in FIELDS if out.get(k)}


def _t(s: str) -> str:
    return s.strip().rstrip(".").strip()


def compile_dna(name: str, dna: dict) -> dict:
    """The text the render uses, made from the DNA. Short on purpose: it goes into every prompt."""
    d = dna
    prompt = (f"{name}: {_t(d.get('character_design', ''))}; {_t(d.get('surface_texture', ''))}; palette {_t(d.get('palette', ''))}; {_t(d.get('lighting', ''))}; "
              f"{_t(d.get('shadow_construction', ''))}; {_t(d.get('environmental_depth', ''))}; {_t(d.get('animation_style', ''))}.")
    prompt = " ".join(prompt.split())
    if len(prompt) > MAX_PROMPT:
        prompt = " ".join(f"{name}: {_t(d.get('character_design', ''))}; {_t(d.get('surface_texture', ''))}; palette {_t(d.get('palette', ''))}; {_t(d.get('lighting', ''))}; "
                          f"{_t(d.get('environmental_depth', ''))}.".split())
    figures = f"{_t(d.get('character_design', ''))}; {_t(d.get('body_proportions', ''))}; {_t(d.get('facial_proportions', ''))}; {_t(d.get('line_weight', ''))}; {_t(d.get('rendering_material', ''))}"
    neg = [x.strip() for x in d.get("negatives", "").split(",") if x.strip()]
    return {"prompt": prompt, "figures": " ".join(figures.split()), "figures_avoid": ", ".join(neg[:6]), "avoid": d.get("negatives", "")}


def entries() -> list[dict]:
    """The styles.json entries of the storybook looks, with their DNA and the wording compiled from it."""
    out = []
    for sid, (name, desc, over) in VARIANTS.items():
        dna = merged(over, STORYBOOK)
        out.append({"id": sid, "name": name, "group": "Hybrid 2D/3D", "description": desc, **{k: v for k, v in compile_dna(name, dna).items() if k in ("prompt", "avoid")},
                    "family": "hybrid", **{k: v for k, v in compile_dna(name, dna).items() if k in ("figures", "figures_avoid")}, "dna": ({"inherits": BASE_ID, **{k: v for k, v in over.items()}} if sid != BASE_ID else dna)})
    return out


def full_dna(styles_by_id: dict, sid: str) -> dict:
    """A look's whole DNA: its own parts over the look it inherits (one level)."""
    s = styles_by_id[sid].get("dna") or {}
    base = styles_by_id[s["inherits"]].get("dna") if s.get("inherits") in styles_by_id else None
    return merged({k: v for k, v in s.items() if k != "inherits"}, merged(base or {}))


if __name__ == "__main__":
    json.dump(entries(), sys.stdout, indent=2, ensure_ascii=False)
