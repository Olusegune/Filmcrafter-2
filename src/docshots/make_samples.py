"""Makes the sample pictures and clips the screenshot harness uses (soft cinematic gradients with silhouettes; nothing from a real project).

  analysis/.venv/Scripts/python src/docshots/make_samples.py

Writes src/docshots/img/s1.png ... s6.png and v1.mp4 ... v3.mp4 (ffmpeg comes with the engine's imageio-ffmpeg). They are only read by the harness (docshots.html), never by the app.
"""
import math
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "img")
SCENES = [
    ((22, 28, 58), (214, 124, 76), (46, 38, 60)),     # dusk
    ((14, 54, 66), (232, 176, 98), (28, 40, 44)),     # teal and amber
    ((54, 36, 92), (240, 132, 150), (36, 24, 56)),    # violet and rose
    ((20, 36, 70), (120, 170, 222), (22, 30, 52)),    # cold blue
    ((70, 42, 30), (244, 190, 110), (44, 28, 22)),    # warm room
    ((18, 48, 40), (170, 214, 150), (20, 36, 30)),    # green night
]


def lerp(a, b, t):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


def still(n: int, size=(960, 540)) -> Image.Image:
    top, bottom, dark = SCENES[n % len(SCENES)]
    w, h = size
    im = Image.new("RGB", size, top)
    d = ImageDraw.Draw(im)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=lerp(top, bottom, (y / h) ** 1.4))
    glow = Image.new("RGB", size, (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gx, gy = int(w * (0.25 + 0.5 * ((n * 37) % 100) / 100)), int(h * 0.38)
    gd.ellipse([gx - 160, gy - 160, gx + 160, gy + 160], fill=lerp(bottom, (255, 255, 255), 0.25))
    glow = glow.filter(ImageFilter.GaussianBlur(70))
    from PIL import ImageChops
    im = ImageChops.add(im, glow, 1.0, 0)
    d = ImageDraw.Draw(im)
    d.rectangle([0, int(h * 0.82), w, h], fill=dark)                      # the floor
    for k, fx in enumerate((0.38, 0.6)):                                  # two figures
        x, base = int(w * fx), int(h * 0.82)
        s = 1.0 if k == 0 else 0.88
        d.ellipse([x - 46 * s, base - 330 * s, x + 46 * s, base - 238 * s], fill=lerp(dark, (120, 84, 62), 0.55))
        d.rounded_rectangle([x - 78 * s, base - 240 * s, x + 78 * s, base], radius=int(30 * s), fill=lerp(dark, (84, 92, 70), 0.45 + 0.1 * k))
    return im.filter(ImageFilter.GaussianBlur(0.6))


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    for i in range(6):
        still(i).save(os.path.join(OUT, f"s{i + 1}.png"))
    try:
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        print("no ffmpeg: pictures only")
        return 0
    for i in range(3):
        src = os.path.join(OUT, f"s{i + 1}.png")
        subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-i", src, "-t", "4", "-vf", "zoompan=z='1+0.0008*on':d=100:s=640x360:fps=25",
                        "-pix_fmt", "yuv420p", "-c:v", "libx264", os.path.join(OUT, f"v{i + 1}.mp4")], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
