"""Custom voices with ElevenLabs inside a film: giving a person a voice, designing and cloning one, and speaking a line, with every call to ElevenLabs faked. Nothing is spent here."""
import base64
import io
import json
import os

import numpy as np
import pytest
import soundfile as sf

from filmcrafter_engine import bible, cast_voice as C, shots, story, voiceover as V

SCRIPT = "INT. YARD - DAY\n\nA schoolyard.\n\nLILA\nIt looked weird.\n\nCHLOE\n(quietly)\nI know.\n\nLILA\nSee?\n"
VID = "AbCdEfGh1234"


def wav_bytes(secs=1.5):
    t = np.arange(int(22050 * secs)) / 22050
    b = io.BytesIO()
    sf.write(b, (0.3 * np.sin(2 * np.pi * 220 * t)).astype("float32"), 22050, format="WAV")
    return b.getvalue()


class Reply:
    def __init__(self, status=200, body=None, content=b"", headers=None):
        self.status_code, self._body, self.content, self.text = status, body, content, json.dumps(body) if body is not None else ""
        self.ok = status < 400

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


@pytest.fixture
def film(tmp_path, monkeypatch):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    shots.breakdown(d)
    monkeypatch.setenv("ELEVENLABS_KEY", "test-key-not-real")
    return d


@pytest.fixture
def calls(monkeypatch):
    """Every request that would have gone to ElevenLabs, and the replies to give."""
    log, replies = [], {}

    def post(path, accept="application/json", timeout=180, **kw):
        log.append(("POST", path, kw))
        r = replies.get(path)
        return r() if callable(r) else (r or Reply(200, {}))

    def get(path, **kw):
        log.append(("GET", path, kw))
        r = replies.get(path)
        return r() if callable(r) else (r or Reply(200, {}))

    monkeypatch.setattr(C, "_post", post)
    monkeypatch.setattr(C, "_get", get)
    monkeypatch.setattr(C.time, "sleep", lambda s: None)
    return log, replies


def lila_shot(film):
    return next(s["id"] for s in V.status(film)["shots"] if any(p["name"] == "Lila" for p in s["people"]))


def give_voice(film, who="Lila", **kw):
    return C.set_voice(film, who, {"voice_id": VID, "voice_name": "Warm", **kw})


# ---------------------------------------------------------------- the key and the plan

def test_without_a_key_nothing_is_asked_and_the_screen_is_told(film, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_KEY")
    st = C.status(film)
    assert st["key"] is False and st["plan"] is None
    with pytest.raises(SystemExit, match="Add your ElevenLabs key"):
        C.library()


def test_cards_do_not_ask_for_the_plan_only_the_plan_view_does(film, calls):
    log, replies = calls
    C.status(film)
    assert log == []


def test_a_key_that_lacks_one_permission_is_told_which(film, calls):
    log, replies = calls
    replies["/v1/user/subscription"] = Reply(401, {"detail": {"status": "missing_permissions", "message": "The API key you used is missing the permission user_read to execute this operation."}})
    err = C.status(film, with_plan=True)["plan_error"]
    assert "missing a permission" in err and "user_read" in err and "refused the key" not in err


def test_the_plan_shows_characters_left_and_whether_cloning_is_allowed(film, calls):
    log, replies = calls
    replies["/v1/user/subscription"] = Reply(200, {"tier": "starter", "character_count": 1200, "character_limit": 30000, "can_use_instant_voice_cloning": True, "voice_slots_used": 3, "voice_limit": 10})
    st = C.status(film, with_plan=True)
    assert st["plan"]["left"] == 28800 and st["plan"]["can_clone"] is True and st["plan"]["slots"] == 10


def test_a_refused_key_or_a_missing_plan_feature_is_said_in_plain_words(film, calls):
    log, replies = calls
    replies["/v1/user/subscription"] = Reply(401, {"detail": {"status": "invalid_api_key", "message": "bad"}})
    assert "refused the key" in C.status(film, with_plan=True)["plan_error"]


# ---------------------------------------------------------------- giving a person a voice

def test_a_voice_from_the_library_is_given_to_a_person_and_remembered(film):
    out = give_voice(film, model="eleven_flash_v2_5", speed=5, stability=-3)
    assert out["voice"]["model"] == "eleven_flash_v2_5" and out["voice"]["speed"] == 1.2 and out["voice"]["stability"] == 0     # limits are kept
    assert C.status(film)["people"]["lila"]["voice_id"] == VID
    C.clear_voice(film, "Lila")
    assert "lila" not in C.status(film)["people"]


def test_a_voice_id_that_is_not_one_is_refused(film):
    for bad in ("", "../../x", "a b", "short"):
        with pytest.raises(SystemExit, match="Choose a voice"):
            C.set_voice(film, "Lila", {"voice_id": bad})


def test_the_library_search_keeps_only_real_voices(film, calls):
    log, replies = calls
    replies["/v2/voices"] = Reply(200, {"voices": [{"voice_id": VID, "name": "Warm", "labels": {"accent": "british"}}, {"voice_id": "../bad", "name": "x"}], "has_more": False})
    got = C.library("warm")
    assert [v["voice_id"] for v in got["voices"]] == [VID] and log[0][2]["params"]["search"] == "warm"


# ---------------------------------------------------------------- designing and cloning

def test_a_designed_voice_is_heard_first_and_only_then_kept(film, calls):
    log, replies = calls
    replies["/v1/text-to-voice/design"] = Reply(200, {"previews": [{"generated_voice_id": "prev_abc123", "audio_base_64": base64.b64encode(wav_bytes()).decode(), "media_type": "audio/mpeg", "duration_secs": 1.5},
                                                                   {"generated_voice_id": "../evil", "audio_base_64": "AAAA", "media_type": "audio/mpeg"}], "text": "Sample"})
    out = C.design(film, "A warm older woman with a gentle northern accent, kind and a little tired.", confirmed=True, unknown_cost_accepted=True)
    assert [p["id"] for p in out["previews"]] == ["prev_abc123"] and os.path.isfile(os.path.join(film, *out["previews"][0]["file"].split("/")))
    assert log[0][2]["json"]["auto_generate_text"] is True
    assert not os.path.exists(C._path(film))                                      # hearing it makes no voice
    replies["/v1/text-to-voice"] = Reply(200, {"voice_id": VID})
    saved = C.design_save(film, "Lila", "prev_abc123", "Lila's voice", "warm", confirmed=True)
    assert saved["voice"]["made"] == "design" and C.status(film)["people"]["lila"]["voice_id"] == VID
    assert next(c for c in log if c[1] == "/v1/text-to-voice")[2]["json"]["generated_voice_id"] == "prev_abc123"


def test_a_description_must_say_something_and_a_preview_id_cannot_be_a_path(film, calls):
    with pytest.raises(SystemExit, match="Describe the voice"):
        C.design(film, "nice")
    with pytest.raises(SystemExit, match="Choose one of the voices"):
        C.design_save(film, "Lila", "../../etc", "x", "y")


def test_cloning_needs_consent_and_a_real_audio_file_and_sends_nothing_otherwise(film, calls, tmp_path):
    log, replies = calls
    sample = tmp_path / "me.wav"
    sample.write_bytes(wav_bytes())
    with pytest.raises(SystemExit, match="right to clone"):
        C.clone(film, "Lila", "Me", [str(sample)], consent=False, confirmed=True)
    with pytest.raises(SystemExit, match="WAV, MP3"):
        C.clone(film, "Lila", "Me", [str(tmp_path / "notes.txt")], consent=True, confirmed=True)
    big = tmp_path / "big.wav"
    big.write_bytes(b"0" * (C.MAX_SAMPLE_BYTES + 1))
    with pytest.raises(SystemExit, match="30 MB"):
        C.clone(film, "Lila", "Me", [str(big)], consent=True, confirmed=True)
    assert log == []
    replies["/v1/voices/add"] = Reply(200, {"voice_id": VID, "requires_verification": False})
    out = C.clone(film, "Lila", "Me", [str(sample)], consent=True, confirmed=True)
    assert out["voice"]["made"] == "clone" and log[0][1] == "/v1/voices/add" and log[0][2]["data"]["name"] == "Me"


# ---------------------------------------------------------------- speaking a line

def test_the_price_is_in_characters_and_credits_and_a_line_already_spoken_costs_nothing(film, calls):
    sid = lila_shot(film)
    give_voice(film, model="eleven_flash_v2_5")
    est = C.estimate(film, [{"shot": sid, "speaker": "Lila"}, {"shot": sid, "speaker": "Nobody"}])
    ok = est["rows"][0]
    assert ok["ok"] and ok["characters"] == len(ok["text"]) and ok["credits"] == round(len(ok["text"]) * 0.5) and "not in dollars" in est["basis"]
    assert est["rows"][1]["ok"] is False and "no voice yet" in est["rows"][1]["why"]


def test_nothing_is_spoken_or_paid_for_without_a_confirmed_yes(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    with pytest.raises(SystemExit, match="Confirm the price"):
        C.speak(film, sid, "Lila")
    assert [c for c in log if "text-to-speech" in c[1]] == []


def test_a_confirmed_line_is_spoken_attached_marked_and_never_paid_for_twice(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    replies[f"/v1/text-to-speech/{VID}"] = Reply(200, content=wav_bytes(1.5))
    out = C.speak(film, sid, "Lila", confirmed=True)
    assert out["credits"] > 0 and out["cached"] is False
    rec = next(p for s in V.status(film)["shots"] if s["id"] == sid for p in s["people"] if p["name"] == "Lila")["recording"]
    assert rec["source"] == "elevenlabs" and "ElevenLabs" in rec["name"]
    sent = next(c for c in log if "text-to-speech" in c[1])[2]["json"]
    assert sent["text"] == "It looked weird." and sent["model_id"] == "eleven_v4"
    again = C.speak(film, sid, "Lila", confirmed=False)                           # same voice, same words: free, and needs no yes
    assert again["credits"] == 0 and again["cached"] is True
    assert len([c for c in log if "text-to-speech" in c[1]]) == 1


def test_your_own_recording_can_replace_a_spoken_one_and_the_spoken_one_is_kept(film, calls, tmp_path):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    replies[f"/v1/text-to-speech/{VID}"] = Reply(200, content=wav_bytes(1.5))
    C.speak(film, sid, "Lila", confirmed=True)
    mine = tmp_path / "mine.wav"
    mine.write_bytes(wav_bytes(1.2))
    V.attach(film, sid, "Lila", str(mine))
    rec = next(p for s in V.status(film)["shots"] if s["id"] == sid for p in s["people"] if p["name"] == "Lila")["recording"]
    assert "source" not in rec
    assert os.listdir(os.path.join(film, "voice", "_removed"))


def test_a_slow_down_is_tried_again_but_an_ambiguous_failure_and_a_refusal_are_not(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    seq = [Reply(429, {"detail": "slow down"}), Reply(200, content=wav_bytes())]            # 429: ElevenLabs did not accept it, so trying again is safe
    replies[f"/v1/text-to-speech/{VID}"] = lambda: seq.pop(0)
    C.speak(film, sid, "Lila", confirmed=True)
    assert len([c for c in log if "text-to-speech" in c[1]]) == 2
    give_voice(film, who="Chloe")
    csid = next(s["id"] for s in V.status(film)["shots"] if any(p["name"] == "Chloe" for p in s["people"]))
    replies[f"/v1/text-to-speech/{VID}"] = Reply(402, {"detail": {"status": "quota_exceeded", "message": "out"}})
    with pytest.raises(SystemExit, match="out of characters"):
        C.speak(film, csid, "Chloe", confirmed=True)


def test_a_person_with_no_voice_or_no_line_is_refused_before_anything_is_sent(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    with pytest.raises(SystemExit, match="no voice yet"):
        C.speak(film, sid, "Lila", confirmed=True)
    give_voice(film)
    with pytest.raises(SystemExit, match="longer than"):
        C.speak(film, sid, "Lila", text="x" * 2000, confirmed=True)
    assert log == []


def test_every_spoken_version_is_kept_as_a_take_and_switching_is_free_and_archives_not_deletes(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    replies[f"/v1/text-to-speech/{VID}"] = Reply(200, content=wav_bytes(1.5))
    first = C.speak(film, sid, "Lila", confirmed=True)
    second = C.speak(film, sid, "Lila", text="[whispers] It looked weird.", confirmed=True)
    sent = [c[2]["json"]["text"] for c in log if "text-to-speech" in c[1]]
    assert sent == ["It looked weird.", "[whispers] It looked weird."]                  # the direction rides in the spoken text only
    got = C.takes(film, sid, "Lila")["takes"]
    assert [t["text"] for t in got] == ["[whispers] It looked weird.", "It looked weird."] and [t["current"] for t in got] == [True, False]
    n_calls = len(log)
    back = C.use_take(film, sid, "Lila", first["take"])
    assert len(log) == n_calls and back["take"] == first["take"]                          # switching costs nothing and sends nothing
    assert [t["current"] for t in C.takes(film, sid, "Lila")["takes"]] == [False, True]
    assert os.listdir(os.path.join(film, "voice", "_removed"))
    # the shot's written dialogue is untouched, so a picture or video prompt never sees the direction
    dl = next(c for c in V._contracts(film).values() if c["id"] == sid)["dialogue"]
    assert all("[" not in (x.get("line") or "") for x in dl)


def test_attaching_the_take_that_is_already_attached_changes_nothing(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    replies[f"/v1/text-to-speech/{VID}"] = Reply(200, content=wav_bytes(1.5))
    C.speak(film, sid, "Lila", confirmed=True)
    removed = os.path.join(film, "voice", "_removed")
    before = os.listdir(removed) if os.path.isdir(removed) else []
    again = C.speak(film, sid, "Lila")
    assert again["cached"] and (os.listdir(removed) if os.path.isdir(removed) else []) == before


def test_a_take_from_another_line_or_a_path_cannot_be_used(film, calls):
    log, replies = calls
    sid = lila_shot(film)
    give_voice(film)
    replies[f"/v1/text-to-speech/{VID}"] = Reply(200, content=wav_bytes(1.5))
    C.speak(film, sid, "Lila", confirmed=True)
    for bad in ("../../x.mp3", "voice/lila.mp3", "voice/_generated/../voice.json", "voice/_generated/S09-09-abc.mp3", ""):
        with pytest.raises(SystemExit, match="not one of this line"):
            C.use_take(film, sid, "Lila", bad)


class Streamed:
    def __init__(self, status=200, data=b"x" * 5000, headers=None):
        self.status_code, self.ok, self._d, self.headers = status, status < 400, data, headers or {}

    def iter_content(self, n):
        for i in range(0, len(self._d), n):
            yield self._d[i:i + n]


def test_a_library_sample_is_fetched_into_the_film_only_from_elevenlabs_links_and_cached(film, monkeypatch):
    import requests
    seen = []
    monkeypatch.setattr(requests, "get", lambda url, **kw: (seen.append((url, kw)), Streamed())[1])
    ok = "https://storage.googleapis.com/eleven-public-prod/premade/voices/abc/preview.mp3"
    out = C.sample(film, ok)
    assert out["file"].startswith("voice/_previews/lib-") and out["cached"] is False and os.path.isfile(os.path.join(film, *out["file"].split("/")))
    assert "xi-api-key" not in seen[0][1]["headers"] and seen[0][1]["allow_redirects"] is False        # the key goes only to ElevenLabs' own host
    assert C.sample(film, ok)["cached"] is True and len(seen) == 1
    C.sample(film, "https://api.us.elevenlabs.io/v1/voices/x/preview")
    assert seen[1][1]["headers"]["xi-api-key"] == "test-key-not-real"


def test_a_sample_link_that_is_not_elevenlabs_is_refused_and_a_redirect_or_a_huge_file_is_not_followed(film, monkeypatch):
    import requests
    calls = []
    monkeypatch.setattr(requests, "get", lambda url, **kw: (calls.append(url), Streamed(302))[1])
    for bad in ("http://storage.googleapis.com/eleven-x/a.mp3", "https://evil.example/a.mp3", "https://storage.googleapis.com/other-bucket/a.mp3",
                "https://elevenlabs.io.evil.com/a.mp3", "https://user:pw@elevenlabs.io/a.mp3", "https://elevenlabs.io:8443/a.mp3", "file:///C:/Windows/win.ini", ""):
        with pytest.raises(SystemExit, match="not an ElevenLabs sample"):
            C.sample(film, bad)
    assert calls == []
    with pytest.raises(SystemExit, match="moved somewhere else"):
        C.sample(film, "https://storage.googleapis.com/eleven-public-prod/a.mp3")
    monkeypatch.setattr(requests, "get", lambda url, **kw: Streamed(200, b"x" * (4 * 1024 * 1024)))
    with pytest.raises(SystemExit, match="larger than expected"):
        C.sample(film, "https://storage.googleapis.com/eleven-public-prod/big.mp3")


def test_the_command_line_only_does_what_the_shell_may_ask(film, capsys):
    with pytest.raises(SystemExit):
        C.main(["format_disk", film])
    C.main(["status", film])
    assert '"event": "result"' in capsys.readouterr().out
