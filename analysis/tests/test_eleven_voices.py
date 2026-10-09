"""ElevenLabs voices beside MiniMax: choosing, searching, speaking, pricing, and a scene that mixes both. No network."""
import hashlib
import io
import json
import os

import numpy as np
import pytest
import soundfile as sf

from filmcrafter_engine import show as S, voices as V

VID = "21m00Tcm4TlvDq8ikWAM"


@pytest.fixture
def show(tmp_path):
    return S.create(str(tmp_path / "shows"), "Night Market")["dir"]


class Resp:
    def __init__(self, status=200, body=None, content=b"", text=""):
        self.status_code, self._body, self.content, self.text = status, body, content, text
        self.ok = status < 400

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def _wav_bytes(secs=0.6, rate=24000):
    buf = io.BytesIO()
    t = np.linspace(0, secs, int(rate * secs), endpoint=False)
    sf.write(buf, (0.3 * np.sin(2 * np.pi * 300 * t)).astype(np.float32), rate, format="WAV")
    return buf.getvalue()


def test_an_elevenlabs_voice_is_chosen_checked_and_clamped(show):
    V.set_voice(show, "Ada", {"provider": "elevenlabs", "voice_id": VID, "voice_name": "Rachel", "model": "eleven_v3", "stability": 9, "similarity": -1,
                              "style": "x", "speed": 5})
    v = V.voices(show)["voices"]["Ada"]
    assert v == {"provider": "elevenlabs", "voice_id": VID, "voice_name": "Rachel", "model": "eleven_v3", "stability": 1.0, "similarity": 0.0, "style": 0.0, "speed": 1.2}
    for bad in ("", "short", "has space in it!", "../../x", VID + "!!"):
        with pytest.raises(SystemExit, match="ElevenLabs library"):
            V.set_voice(show, "Ben", {"provider": "elevenlabs", "voice_id": bad})
    V.set_voice(show, "Ben", {"provider": "elevenlabs", "voice_id": VID, "model": "not-a-model"})
    assert V.voices(show)["voices"]["Ben"]["model"] == "eleven_multilingual_v2"                  # an unknown model falls back to the default
    V.set_voice(show, "Cy", {"voice_id": "Wise_Woman"})                                           # MiniMax still works as before
    assert V.voices(show)["voices"]["Cy"]["voice_id"] == "Wise_Woman" and "provider" not in V.voices(show)["voices"]["Cy"]


def test_existing_minimax_cache_keys_are_unchanged_so_nothing_is_paid_twice():
    v = {"voice_id": "Wise_Woman", "speed": 1.0, "pitch": 0, "emotion": None}
    old = hashlib.sha1(json.dumps([V.MODEL, "Hello", "Wise_Woman", 1.0, 0, None], sort_keys=True).encode()).hexdigest()[:16]
    assert V._key("Hello", v, None) == old
    e1 = {"provider": "elevenlabs", "voice_id": VID, "model": "eleven_v3", "stability": .5, "similarity": .75, "style": 0, "speed": 1}
    assert V._key("Hello", e1, None) != old and V._key("Hello", e1, None) != V._key("Hello", {**e1, "speed": 1.1}, None)


def test_the_voice_search_sends_the_key_and_returns_only_names_and_labels(monkeypatch):
    seen = {}

    def get(url, headers=None, params=None, timeout=None):
        seen.update(url=url, headers=headers, params=params)
        return Resp(200, {"voices": [{"voice_id": VID, "name": "Rachel", "category": "premade", "description": "Calm", "labels": {"accent": "american", "gender": "female"},
                                      "preview_url": "https://example.invalid/x.mp3"}, {"voice_id": "bad id!", "name": "junk"}],
                          "has_more": True, "next_page_token": "tok"})
    monkeypatch.setattr("requests.get", get)
    monkeypatch.delenv("ELEVENLABS_KEY", raising=False)
    with pytest.raises(SystemExit, match="Add your ElevenLabs key"):
        V.eleven_voices("calm")
    monkeypatch.setenv("ELEVENLABS_KEY", "sk_test")
    r = V.eleven_voices("  calm woman ", "page2")
    assert seen["url"] == "https://api.elevenlabs.io/v2/voices" and seen["headers"]["xi-api-key"] == "sk_test"
    assert seen["params"]["search"] == "calm woman" and seen["params"]["next_page_token"] == "page2" and seen["params"]["page_size"] == 50
    assert r["voices"] == [{"voice_id": VID, "name": "Rachel", "category": "premade", "description": "Calm", "labels": {"accent": "american", "gender": "female"}}]
    assert r["next"] == "tok" and "preview_url" not in json.dumps(r)                              # nothing is fetched from a URL the API names
    monkeypatch.setattr("requests.get", lambda *a, **k: Resp(401, {"detail": {"status": "invalid_api_key", "message": "bad"}}))
    with pytest.raises(SystemExit, match="refused the key"):
        V.eleven_voices()


def test_a_line_is_spoken_with_the_right_request_and_errors_are_plain(monkeypatch, tmp_path):
    monkeypatch.setenv("ELEVENLABS_KEY", "sk_test")
    sent = {}

    def post(url, headers=None, params=None, json=None, timeout=None):
        sent.update(url=url, headers=headers, params=params, body=json)
        return Resp(200, content=_wav_bytes())
    monkeypatch.setattr("requests.post", post)
    v = {"provider": "elevenlabs", "voice_id": VID, "model": "eleven_flash_v2_5", "stability": .4, "similarity": .8, "style": .1, "speed": 1.1}
    out = str(tmp_path / "x" / "line.mp3")
    V._speak("Where were you?", v, "angry", out)
    assert sent["url"] == f"https://api.elevenlabs.io/v1/text-to-speech/{VID}" and sent["headers"]["xi-api-key"] == "sk_test"
    assert sent["params"] == {"output_format": "mp3_44100_128"}
    assert sent["body"]["text"] == "Where were you?" and sent["body"]["model_id"] == "eleven_flash_v2_5"
    assert sent["body"]["voice_settings"] == {"stability": .4, "similarity_boost": .8, "style": .1, "speed": 1.1, "use_speaker_boost": True}
    assert os.path.getsize(out) > 100
    for status, body, why in ((401, {"detail": {"status": "invalid_api_key", "message": "no"}}, "refused the key"),
                              (402, {"detail": {"status": "quota_exceeded", "message": "You have 0 credits"}}, "quota")):
        monkeypatch.setattr("requests.post", lambda *a, _s=status, _b=body, **k: Resp(_s, _b))
        slept = []
        monkeypatch.setattr(V.time, "sleep", lambda s_: slept.append(s_))
        with pytest.raises(RuntimeError, match=why):
            V._speak("Hi", v, None, out)
        assert slept == []                                                                         # a refused key or an empty quota is never retried


def test_a_busy_service_is_retried_and_the_key_never_appears_in_an_error(monkeypatch, tmp_path):
    monkeypatch.setenv("ELEVENLABS_KEY", "sk_secret_value")
    n = {"i": 0}

    def post(*a, **k):
        n["i"] += 1
        return Resp(429, {"detail": "rate limited"}) if n["i"] < 3 else Resp(200, content=_wav_bytes())
    monkeypatch.setattr("requests.post", post)
    monkeypatch.setattr(V.time, "sleep", lambda s: None)
    V._speak("Hi", {"provider": "elevenlabs", "voice_id": VID}, None, str(tmp_path / "a.mp3"))
    assert n["i"] == 3
    monkeypatch.setattr("requests.post", lambda *a, **k: Resp(500, {"detail": "boom"}))
    with pytest.raises(RuntimeError) as e:
        V._speak("Hi", {"provider": "elevenlabs", "voice_id": VID}, None, str(tmp_path / "b.mp3"))
    assert "sk_secret_value" not in str(e.value)


def test_a_scene_can_mix_both_providers_and_each_is_priced_its_own_way(show, monkeypatch):
    scene = S.add_scene(show, "Quarrel")["dir"]
    V.set_dialogue(scene, {"lines": [{"character": "Ada", "text": "Where were you?"}, {"character": "Ben", "text": "Waiting for you, " + "x" * 20}]})
    V.set_voice(show, "Ada", {"provider": "elevenlabs", "voice_id": VID, "model": "eleven_flash_v2_5"})
    V.set_voice(show, "Ben", {"voice_id": "Deep_Voice_Man"})
    monkeypatch.setattr("filmcrafter_engine.render._fal_price", lambda m: {"unit": "character", "unit_price": 0.0001})
    e = V.estimate(scene)
    assert e["lines"] == 2 and e["eleven_characters"] == len("Where were you?") and e["eleven_credits"] == round(len("Where were you?") * 0.5)
    assert e["usd"] is not None and "ElevenLabs" in e["basis"] and "credits" in e["basis"]
    monkeypatch.setenv("ELEVENLABS_KEY", "sk_test")
    monkeypatch.setattr("requests.post", lambda *a, **k: Resp(200, content=_wav_bytes()))
    real = V._speak_once

    def fake(text, v, emotion, out):
        if v.get("provider") == "elevenlabs":
            return real(text, v, emotion, out)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, "wb").write(_wav_bytes(0.8))
        return 0.8
    monkeypatch.setattr(V, "_speak_once", fake)
    r = V.generate(scene)
    t = V.dialogue(scene)["timings"]
    assert r["voiced"] == 2 and t[1]["start"] > t[0]["end"]
    assert V.estimate(scene)["lines"] == 0                                                         # both are cached now: nothing more to pay


def test_a_scene_with_only_elevenlabs_voices_reports_credits_not_dollars(show):
    scene = S.add_scene(show, "Solo")["dir"]
    V.set_dialogue(scene, {"lines": [{"character": "Ada", "text": "Twelve chars"}]})
    V.set_voice(show, "Ada", {"provider": "elevenlabs", "voice_id": VID})
    e = V.estimate(scene)
    assert e["usd"] == 0.0 and e["eleven_credits"] == 12 and "not in dollars" in e["basis"]
