"""Reference images in types a provider can't take: converted when that is safe, otherwise left out. No network."""
import os

import pytest
from PIL import Image

from filmcrafter_engine import render as R, svg_text

TITLE = ('<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="180" viewBox="0 0 1600 180"><text x="800" y="70" '
         'text-anchor="middle" font-family="DejaVu Sans, Arial, sans-serif" font-weight="bold" font-size="44" fill="#d8b35b">I AM YOUR MOTHER!</text></svg>')
CHART = ('<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="200" viewBox="0 0 1600 200">'
         '<text x="800" y="70" text-anchor="middle" font-size="44" fill="#d8b35b">QUEEN BEE — CEO</text>'
         '<text x="800" y="135" text-anchor="middle" font-size="44" fill="#d8b35b">SOLOMON — CEREMONIAL CHAIRMAN</text></svg>')


def _write(tmp_path, name, text, binary=False):
    p = tmp_path / name
    p.write_bytes(text if binary else text.encode("utf-8"))
    return str(p)


def test_a_text_sign_svg_is_drawn_as_a_png_with_its_colour(tmp_path):
    out = svg_text.to_png(_write(tmp_path, "t.svg", TITLE), str(tmp_path / "t.png"))
    im = Image.open(out)
    assert im.size == (1600, 180) and im.format == "PNG"
    px = [im.getpixel((x, y)) for x in range(500, 1100) for y in range(30, 80)]
    assert any(abs(r - 0xd8) < 30 and abs(g - 0xb3) < 30 and abs(b - 0x5b) < 40 for r, g, b in px)       # the gold lettering is there
    assert im.getpixel((5, 5)) == svg_text.BACKGROUND


def test_a_multi_line_sign_scales_to_its_viewbox(tmp_path):
    out = svg_text.to_png(_write(tmp_path, "c.svg", CHART.replace('width="1600" height="200"', 'width="800" height="100"')), str(tmp_path / "c.png"))
    assert Image.open(out).size == (800, 100)


@pytest.mark.parametrize("svg,why", [
    ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><circle cx="5" cy="5" r="4"/></svg>', "circle"),
    ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><image href="http://x/y.png"/></svg>', "image"),
    ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><text x="1" y="9" onload="x()">hi</text></svg>', "scripts"),
    ('<svg xmlns="http://www.w3.org/2000/svg" width="99999" height="10"><text x="1" y="9">hi</text></svg>', "canvas"),
    ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>', "nothing"),
    ('<!DOCTYPE svg [<!ENTITY a "aaaa">]><svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><text>&a;</text></svg>', "DOCTYPE"),
    ("not xml at all", "not valid"),
])
def test_anything_beyond_text_signs_is_refused_not_guessed_at(tmp_path, svg, why):
    with pytest.raises(svg_text.Unsupported):
        svg_text.to_png(_write(tmp_path, "x.svg", svg), str(tmp_path / "x.png"))


def test_a_huge_svg_is_refused_without_being_parsed(tmp_path):
    with pytest.raises(svg_text.Unsupported, match="too large"):
        svg_text.to_png(_write(tmp_path, "big.svg", "<svg>" + " " * svg_text.MAX_BYTES + "</svg>"), str(tmp_path / "big.png"))


def test_references_are_made_safe_to_upload_or_left_out(tmp_path):
    d = str(tmp_path)
    png = str(tmp_path / "a.png")
    Image.new("RGB", (8, 8)).save(png)
    gif = str(tmp_path / "b.gif")
    Image.new("P", (8, 8)).save(gif)
    svg = _write(tmp_path, "sign.svg", TITLE)
    cplx = _write(tmp_path, "logo.svg", '<svg xmlns="http://www.w3.org/2000/svg" width="9" height="9"><path d="M0 0L9 9"/></svg>')
    pdf = _write(tmp_path, "sheet.pdf", b"%PDF-1.4", binary=True)
    assert R._plain_reference(d, {"path": png, "label": "x"})["path"] == png                     # accepted types go as they are
    assert R._plain_reference(d, {"path": gif, "label": "x"})["path"].endswith(".png")
    made = R._plain_reference(d, {"path": svg, "label": "sign"})
    assert made["label"] == "sign" and Image.open(made["path"]).size == (1600, 180) and os.path.exists(svg)
    assert R._plain_reference(d, {"path": cplx, "label": "x"}) is None and R._plain_reference(d, {"path": pdf, "label": "x"}) is None
    assert R._plain_reference(d, {"path": "clip.mp4", "label": "x", "media": "video"})["path"] == "clip.mp4"   # not an image: untouched


def test_one_unreadable_reference_no_longer_fails_the_upload(tmp_path, capsys):
    class Provider:
        name = "kie"

        def __init__(self):
            self.sent = []

        def upload(self, path):
            self.sent.append(os.path.basename(path))
            assert path.lower().endswith((".png", ".jpg", ".jpeg", ".webp")), path             # what Kie refused before
            return "https://files/" + os.path.basename(path)

    d = str(tmp_path)
    png = str(tmp_path / "queen.png")
    Image.new("RGB", (8, 8), "red").save(png)
    svg = _write(tmp_path, "TEXT_TITLE.svg", TITLE)
    pdf = _write(tmp_path, "notes.pdf", b"%PDF-1.4", binary=True)
    p = Provider()
    out = R._uploaded(d, p, [{"label": "Queen", "path": png}, {"label": "Title sign", "path": svg}, {"label": "Notes", "path": pdf}])
    assert [o["label"] for o in out] == ["Queen", "Title sign"] and len(p.sent) == 2
    assert "left out 1 reference" in capsys.readouterr().out
