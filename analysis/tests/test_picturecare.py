"""Picture care: asking the models for natural skin, neutral colour and a clean image, leaving a warm look warm, and reaching the real request."""
from filmcrafter_engine import picturecare as PC, render as R


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


def test_it_is_on_by_default_and_can_be_switched_off_for_a_film():
    assert PC.enabled({}) is True and PC.enabled({"picture_care": {"on": True}}) is True
    assert PC.enabled({"picture_care": {"on": False}}) is False
    assert PC.guard({"performers": ["Sege"]}, {"picture_care": {"on": False}}) is None


def test_the_line_asks_for_neutral_colour_real_skin_and_a_clean_image():
    g = PC.guard({"performers": ["Sege"], "beats": ["Sege looks at the sea."]}, {})
    t = g["text"].lower()
    assert "neutral white balance" in t and "no yellow" in t and "pores" in t and "waxy" in t and "no digital noise" in t
    assert g["priority"] < 8, "it is dropped before the anatomy line when a prompt is too long"
    empty = PC.guard({"performers": [], "beats": ["The empty street."]}, {})["text"].lower()
    assert "pores" not in empty and "neutral white balance" in empty, "no people: nothing about skin"


def test_a_shot_that_is_warm_on_purpose_keeps_its_warmth():
    for words in ("A golden hour walk on the beach.", "Candlelight on her face.", "The sunset over the river.", "A warm glow from the fireplace.", "a sepia flashback"):
        g = PC.guard({"performers": ["Sege"], "beats": [words]}, {})
        assert g["warm_kept"] and "no yellow" not in g["text"].lower() and "pores" in g["text"].lower(), words
    cold = PC.guard({"performers": ["Sege"], "beats": ["A grey morning."], "lighting": {"description": "flat overcast light"}}, {})
    assert not cold["warm_kept"]
    assert PC.guard({"performers": [], "beats": ["A room."]}, {}, "Warm tones, golden hour light.")["warm_kept"], "a warm look keeps the warmth in every shot"


def test_the_negative_prompt_gets_the_words_once_and_a_warm_shot_keeps_its_colour():
    base = "text, subtitles, watermark"
    n = PC.negative(base, {"performers": ["Sege"], "beats": ["A grey morning."]}, {})
    assert n.startswith(base) and "yellow tint" in n and "waxy skin" in n and "digital noise" in n
    assert PC.negative(n, {"performers": ["Sege"], "beats": ["A grey morning."]}, {}) == n, "not repeated"
    warm = PC.negative(base, {"performers": ["Sege"], "beats": ["Sunset on the pier."]}, {})
    assert "yellow tint" not in warm and "waxy skin" in warm
    assert PC.negative(base, {"performers": []}, {"picture_care": {"on": False}}) == base


def test_it_reaches_the_request_for_a_picture_and_for_a_video():
    shot = {"performers": ["Sege"], "beats": ["Sege looks at the sea."]}
    for man in (still_model(), video_model()):
        p = build(shot, man)
        prompt = next(v for k, v in p.items() if k == "prompt")
        assert "neutral white balance" in prompt and "waxy" in prompt, prompt[-400:]
    off = build(shot, still_model(), project={"look": {"style": "auto"}, "picture_care": {"on": False}})["prompt"]
    assert "neutral white balance" not in off
    p = build(shot, video_model(negative=True))
    assert "yellow tint" in p["negative_prompt"] and "fused fingers" in p["negative_prompt"]
    warm = build({"performers": ["Sege"], "beats": ["Sege at sunset."]}, video_model(negative=True))
    assert "yellow tint" not in warm["negative_prompt"] and "waxy skin" in warm["negative_prompt"]


def test_it_gives_way_to_the_hands_line_but_not_to_loose_extras_when_the_prompt_is_too_long():
    trace = []
    build({"performers": ["Sege"], "beats": ["Sege holds her hand."]}, still_model(), trace=trace)
    care = next(b for b in trace if "neutral white balance" in b["text"])
    hands = next(b for b in trace if "five" in b["text"].lower() or "finger" in b["text"].lower())
    assert care["priority"] < hands["priority"], "a prompt that must lose something loses the picture-care line before the hands line"
    assert care["priority"] > 4, "and keeps it ahead of the plain 'avoid' extras"
