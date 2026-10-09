"""Build the onboarding artwork from the approved screen designs (one-off asset step; not shipped as code).

The designs have their UI baked in. We only use regions that contain no text or controls, remove the splash's
wordmark/tagline so they can be animated as real text, and make blurred mood backdrops in which no illustrated
text survives. Run: python scripts/make_onboarding_art.py "<folder with First.png … sixth.png>"
"""
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance

SRC = sys.argv[1]
OUT = os.path.join(os.path.dirname(__file__), "..", "public", "onboarding")
os.makedirs(OUT, exist_ok=True)


def load(name):
    return Image.open(os.path.join(SRC, name)).convert("RGB")


def save(im, name, width=None, q=84):
    if width and im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(os.path.join(OUT, name), quality=q, optimize=True, progressive=True)
    print(name, im.size)


def backdrop(im, name):
    """Mood only: heavily blurred and darkened, so no illustrated text or button can be read."""
    small = im.resize((480, round(im.height * 480 / im.width)), Image.LANCZOS).filter(ImageFilter.GaussianBlur(18))
    small = ImageEnhance.Brightness(small).enhance(0.55)
    save(small.resize((960, round(small.height * 2)), Image.BICUBIC), name, q=70)


# ---- splash: remove wordmark + tagline (animated as real text instead)
first = load("First.png")
a = cv2.cvtColor(np.array(first), cv2.COLOR_RGB2BGR)
mask = np.zeros(a.shape[:2], np.uint8)
mask[505:595, 440:1235] = 255   # PULSEFRAME wordmark
mask[598:648, 590:1090] = 255   # tagline
clean = cv2.inpaint(a, mask, 9, cv2.INPAINT_TELEA)
# soften the patched band so no smudge of letterforms remains
band = clean[495:660, 420:1255]
clean[495:660, 420:1255] = cv2.GaussianBlur(band, (0, 0), 6)
clean_im = Image.fromarray(cv2.cvtColor(clean, cv2.COLOR_BGR2RGB))
save(clean_im, "splash_scene.jpg", width=1440)
dark = ImageEnhance.Brightness(clean_im.filter(ImageFilter.GaussianBlur(6))).enhance(0.35)
save(dark, "splash_dark.jpg", width=1440, q=70)

# ---- step heroes: only the illustration side of each design (no copy, no controls)
save(load("Second.png").crop((1015, 0, 1672, 790)), "music_hero.jpg")
save(load("third.png").crop((925, 0, 1672, 800)), "lyrics_hero.jpg")
save(load("sixth.png").crop((990, 0, 1672, 290)), "assets_hero.jpg")
# illustrative galleries (shown only as clearly labelled examples until the project has its own images)
save(load("Fifth.png").crop((958, 128, 1537, 781)), "script_example.jpg")
save(load("fourth.png").crop((842, 283, 1604, 768)), "choreo_example.jpg")
six = load("sixth.png")
for name, box in {"character": (73, 398, 438, 578), "prop": (480, 398, 822, 576),
                  "set": (863, 398, 1215, 576), "wardrobe": (1257, 398, 1606, 578)}.items():
    save(six.crop(box), f"example_{name}.jpg")

# ---- mood backdrops
for src, name in [("Second.png", "bg_music.jpg"), ("third.png", "bg_lyrics.jpg"), ("Fifth.png", "bg_script.jpg"),
                  ("sixth.png", "bg_assets.jpg"), ("fourth.png", "bg_choreo.jpg"), ("First.png", "bg_review.jpg")]:
    backdrop(load(src), name)
