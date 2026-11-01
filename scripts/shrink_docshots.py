"""Makes the pictures docs/img/<name>.png that scripts/docshots-scenes.mjs wrote smaller (256 colours, which these flat screens do not miss): python scripts/shrink_docshots.py [name ...]"""
import os
import sys

from PIL import Image

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "img")
NAMES = ["home-new", "home-welcome", "home-presets", "home-preset-details", "newfilm-setup", "guide-path", "motion-graphics", "mix-effects", "video-clip-layer", "presets-sheet", "color-studio", "smart-editor", "export-ready", "season-films"]
for n in sys.argv[1:] or NAMES:
    p = os.path.join(ROOT, f"{n}.png")
    before = os.path.getsize(p)
    Image.open(p).convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG).save(p, optimize=True)
    print(f"{n}: {before // 1024} KB -> {os.path.getsize(p) // 1024} KB")
