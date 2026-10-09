"""Making a song with ElevenLabs Music: the plan from your lyrics, the request, the saved file, and plain errors. No network."""
import io
import os

import numpy as np
import pytest
import soundfile as sf

from pulseframe_analysis import songgen as G

LYRICS = """[Intro - Spoken]
Children!
Come downstairs!

[Verse 1]
Nine months I carry you,
Now you tell me, "Mummy, no"?
School fees, uniform, Christmas shoe,
After everything I do for you?

[Chorus]
I AM YOUR MOTHER!
Don't you forget!
"""


class Resp:
    def __init__(self, status=200, body=None, content=b""):
        self.status_code, self._body, self.content = status, body, content
        self.ok = status < 400
        self.text = ""

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def _mp3ish(secs=1.2, rate=24000):
    buf = io.BytesIO()
    t = np.linspace(0, secs, int(rate * secs), endpoint=False)
    sf.write(buf, (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), rate, format="WAV")
    return buf.getvalue() + b"\0" * 1000


@pytest.fixture
def songs(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "SONGS_DIR", str(tmp_path / "songs"))
    monkeypatch.setenv("ELEVENLABS_KEY", "sk_test")
    return tmp_path / "songs"


def test_style_words_are_cleaned_and_limited():
    assert G.tags(" Afrobeat, highlife ;  gospel\nafrobeat ,, ") == ["Afrobeat", "highlife", "gospel"]
    assert len(G.tags(",".join(f"t{i}" for i in range(50)))) == G.MAX_TAGS and G.tags(None) == [] and G.tags(["a", "A", "b"]) == ["a", "b"]
    assert len(G.tags("x" * 500)[0]) == 80


def test_tagged_lyrics_become_a_section_by_section_plan():
    r = G.build_plan(LYRICS, "Afrobeat, highlife, theatrical", "metal")
    p = r["plan"]
    assert [s["section_name"] for s in p["sections"]] == ["Intro - Spoken", "Verse 1", "Chorus"]
    assert [len(s["lines"]) for s in p["sections"]] == [2, 4, 2] and p["sections"][1]["lines"][1] == 'Now you tell me, "Mummy, no"?'
    assert p["positive_global_styles"] == ["Afrobeat", "highlife", "theatrical"] and p["negative_global_styles"] == ["metal"]
    assert [s["duration_ms"] for s in p["sections"]] == [int(2 * G.PER_LINE_MS + G.BED_MS), int(4 * G.PER_LINE_MS + G.BED_MS), int(2 * G.PER_LINE_MS + G.BED_MS)]
    assert r["seconds"] == round(sum(s["duration_ms"] for s in p["sections"]) / 1000) and r["sections"][1] == {"name": "Verse 1", "lines": 4, "seconds": 15}
    assert all(G.MIN_SECTION_MS <= s["duration_ms"] <= G.MAX_SECTION_MS for s in p["sections"])


def test_long_lines_and_long_sections_are_split_to_what_the_model_takes():
    long_line = "word " * 80                                                                          # 400 characters
    r = G.build_plan("[Verse]\n" + long_line + "\n" + "\n".join(f"line {i}" for i in range(35)))
    s = r["plan"]["sections"]
    assert [x["section_name"] for x in s] == ["Verse", "Verse (2)"] and len(s[0]["lines"]) == G.MAX_LINES and len(s[1]["lines"]) == 37 - G.MAX_LINES
    assert all(len(ln) <= G.MAX_LINE for x in s for ln in x["lines"]) and r["warnings"]
    quiet = G.build_plan("[Intro]\n[Verse]\nHello there")
    assert quiet["plan"]["sections"][0]["lines"] == [] and quiet["plan"]["sections"][0]["duration_ms"] == G.BED_MS * 4     # an instrumental part keeps its time


def test_lyrics_that_cannot_work_are_refused_before_anything_is_sent():
    for bad in ("", "   \n\n", "[Verse]\n[Chorus]\n"):
        with pytest.raises(SystemExit, match="Add your lyrics"):
            G.build_plan(bad)
    huge = "\n".join(f"[Verse {i}]\n" + "\n".join(f"la la {j}" for j in range(30)) for i in range(4))     # about six minutes
    with pytest.raises(SystemExit, match="at most 5 minutes"):
        G.build_plan(huge)


def test_a_described_song_is_requested_saved_and_checked(songs, monkeypatch):
    sent = {}

    def post(url, headers=None, params=None, json=None, timeout=None):
        sent.update(url=url, headers=headers, params=params, body=json)
        return Resp(200, content=_mp3ish())
    monkeypatch.setattr("requests.post", post)
    r = G.make("describe", prompt="  A warm highlife song about a proud mother  ", style="Afrobeat, gospel", seconds=9999, instrumental=True, model="nope")
    assert sent["url"] == "https://api.elevenlabs.io/v1/music" and sent["headers"]["xi-api-key"] == "sk_test" and sent["params"] == {"output_format": "mp3_44100_128"}
    b = sent["body"]
    assert b["model_id"] == "music_v2_5" and b["music_length_ms"] == G.MAX_PROMPT_MS and b["force_instrumental"] is True and "composition_plan" not in b
    assert b["prompt"] == "A warm highlife song about a proud mother Style: Afrobeat, gospel."
    assert os.path.dirname(r["path"]) == str(songs) and r["path"].endswith(".mp3") and os.path.exists(r["path"]) and 1.0 < r["seconds"] < 1.5
    with pytest.raises(SystemExit, match="Describe the song"):
        G.make("describe", prompt="  ")
    with pytest.raises(SystemExit, match="Choose to make the song"):
        G.make("sing")


def test_a_lyrics_song_sends_the_plan_and_no_prompt(songs, monkeypatch):
    sent = {}
    monkeypatch.setattr("requests.post", lambda url, **k: (sent.update(body=k["json"]), Resp(200, content=_mp3ish()))[1])
    G.make("lyrics", lyrics=LYRICS, style="Afrobeat", model="music_v2")
    b = sent["body"]
    assert b["model_id"] == "music_v2" and "prompt" not in b and [s["section_name"] for s in b["composition_plan"]["sections"]] == ["Intro - Spoken", "Verse 1", "Chorus"]
    assert b["composition_plan"]["positive_global_styles"] == ["Afrobeat"] and "music_length_ms" not in b


def test_refusals_are_explained_in_plain_words_and_the_key_never_leaks(songs, monkeypatch):
    cases = [(401, {"detail": {"status": "invalid_api_key", "message": "bad key"}}, "paid plan"),
             (402, {"detail": {"status": "quota_exceeded", "message": "You have 0 credits left"}}, "out of credits"),
             (422, {"detail": {"status": "bad_prompt", "message": "Copyrighted material was detected in the prompt"}}, "Copyrighted material"),
             (500, {"detail": "boom"}, "didn't make the song")]
    for status, body, why in cases:
        monkeypatch.setattr("requests.post", lambda *a, _s=status, _b=body, **k: Resp(_s, _b))
        with pytest.raises(SystemExit) as e:
            G.make("describe", prompt="x")
        assert why in str(e.value) and "sk_test" not in str(e.value)
    monkeypatch.setattr("requests.post", lambda *a, **k: Resp(200, content=b"<html>not music</html>" * 100))
    with pytest.raises(SystemExit, match="isn't a song"):
        G.make("describe", prompt="x")
    assert not [f for f in os.listdir(songs) if f.endswith((".mp3", ".part"))]                        # nothing bad is left behind
    monkeypatch.delenv("ELEVENLABS_KEY")
    with pytest.raises(SystemExit, match="Add your ElevenLabs key"):
        G.make("describe", prompt="x")


def test_a_busy_service_is_asked_again_once_and_a_second_busy_is_reported(songs, monkeypatch):
    calls = {"n": 0}

    def post(*a, **k):
        calls["n"] += 1
        return Resp(429, {"detail": "busy"}) if calls["n"] == 1 else Resp(200, content=_mp3ish())
    monkeypatch.setattr("requests.post", post)
    monkeypatch.setattr(G.time, "sleep", lambda s: None)
    assert G.make("describe", prompt="x")["path"]
    assert calls["n"] == 2
    monkeypatch.setattr("requests.post", lambda *a, **k: Resp(429, {"detail": "busy"}))
    with pytest.raises(SystemExit, match="didn't make the song"):
        G.make("describe", prompt="x")
