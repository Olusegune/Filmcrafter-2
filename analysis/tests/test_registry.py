"""Stage G: the AI model registry. Provider lists are faked (no network). Checked: the built-in models always answer, a discovery that fails changes nothing, a model that disappears is marked and
never removed, the credit multipliers ElevenLabs states are used, unsupported parameters are refused, and the models behind a film are reported without ever being replaced."""
import json
import os

import pytest

from filmcrafter_engine import audiolib as AL, bible, cast_voice as C, make, registry as R, shots as S, story
from tests.test_golden_film import SCRIPT, _clip, _job

pytestmark = pytest.mark.unit


@pytest.fixture
def reg(tmp_path):
    return str(tmp_path / "registry.json")


ELEVEN = [{"model_id": "eleven_v4", "name": "Eleven v4", "can_do_text_to_speech": True, "model_rates": {"character_cost_multiplier": 1.0}, "languages": [{"language_id": "en", "name": "English"}]},
          {"model_id": "eleven_flash_v2_5", "name": "Flash v2.5", "can_do_text_to_speech": True, "model_rates": {"character_cost_multiplier": 0.25}},
          {"model_id": "eleven_v5_preview", "name": "Eleven v5 (preview)", "can_do_text_to_speech": True, "token_cost_factor": 0.3, "requires_alpha_access": True},
          {"model_id": "eleven_sts_v2", "name": "Speech to speech", "can_do_text_to_speech": False}]
KIE = [{"kind": "video", "family": "Seedance", "title": "Seedance 2", "doc": "https://docs.kie.ai/market/bytedance/seedance-2.md"},
       {"kind": "image", "family": "Google", "title": "Nano Banana 2.1", "doc": "https://docs.kie.ai/market/google/nanobanana-2-1.md"}]


# ---------------------------------------------------------------- the built-in models

def test_the_built_in_models_always_answer_with_their_facts_and_a_check_date(reg):
    ms = R.all_models(reg)
    keys = {R.key(m["provider"], m["model"]) for m in ms}
    assert {"elevenlabs/eleven_v4", "elevenlabs/eleven_text_to_sound_v2", "elevenlabs/music_v1", "kie/ai-music-api/generate"} <= keys
    sfx = R.lookup("elevenlabs", "eleven_text_to_sound_v2", reg)
    assert sfx["media"] == "sfx" and sfx["price"]["known"] and sfx["capabilities"]["duration_seconds"] == [0.5, 30] and sfx["verified"] and sfx["deprecation"]["status"] == "active"
    music = R.lookup("elevenlabs", "music_v1", reg)
    assert music["price"]["known"] is False and "not established" in music["deprecation"]["note"]                       # no price and no rights are invented
    assert R.lookup("elevenlabs", "nonsense", reg) is None
    assert all(m["media"] in R.MEDIA and m["deprecation"]["status"] in R.DEPRECATION for m in ms)


def test_the_credit_multipliers_written_into_the_app_agree_with_the_registrys_built_in_list():
    for model, mult in C.CREDITS.items():
        assert R.credit_multiplier(model, "nope.json") == mult
    assert R.credit_multiplier("eleven_v4", "nope.json") == 1.0 and R.credit_multiplier("music_v1", "nope.json") is None


# ---------------------------------------------------------------- discovery

def test_a_discovery_keeps_the_providers_own_words_and_its_credit_multipliers(reg):
    r = R.refresh(["elevenlabs"], {"elevenlabs": lambda: ELEVEN}, reg)
    assert r["results"]["elevenlabs"] == {"ok": True, "models": 3}                                                      # the one that cannot speak is not a speech model
    assert R.credit_multiplier("eleven_flash_v2_5", reg) == 0.25 and R.credit_multiplier("eleven_v5_preview", reg) == 0.3
    new = R.lookup("elevenlabs", "eleven_v5_preview", reg)
    assert new["source"] == "discovered" and new["capabilities"]["requires_alpha_access"] is True and new["verified"] and new["price"]["source"] == "ElevenLabs GET /v1/models"
    assert R.lookup("elevenlabs", "eleven_v4", reg)["name"] == "Eleven v4" and R.status(reg)["providers"]["elevenlabs"]["stale"] is False


def test_the_multiplier_elevenlabs_states_is_what_a_price_is_worked_out_from(reg, tmp_path, monkeypatch):
    monkeypatch.setenv(R.ENV, reg)
    d = story.create(str(tmp_path / "films"), "T", "screenplay", "INT. YARD - DAY\n\nA yard.\n\nLILA\nIt looked weird.\n", None)["dir"]
    bible.seed(d)
    S.breakdown(d)
    C.set_voice(d, "Lila", {"voice_id": "AbCdEfGh1234", "voice_name": "Warm", "model": "eleven_flash_v2_5"})
    sid = next(s["id"] for s in __import__("filmcrafter_engine.voiceover", fromlist=["x"]).status(d)["shots"] if s["people"])
    before = C.estimate(d, [{"shot": sid, "speaker": "Lila"}])["credits"]
    R.refresh(["elevenlabs"], {"elevenlabs": lambda: ELEVEN}, reg)
    after = C.estimate(d, [{"shot": sid, "speaker": "Lila"}])["credits"]
    assert before == round(16 * 0.5) and after == round(16 * 0.25)


def test_a_failed_discovery_changes_nothing_says_so_and_the_rest_carry_on(reg):
    R.refresh(["elevenlabs"], {"elevenlabs": lambda: ELEVEN}, reg)
    saved = open(reg, "rb").read()

    def down():
        raise ConnectionError("no network")
    r = R.refresh(["elevenlabs", "kie"], {"elevenlabs": down, "kie": lambda: KIE}, reg)
    assert r["results"]["elevenlabs"]["ok"] is False and "ConnectionError" in r["results"]["elevenlabs"]["error"] and r["results"]["kie"]["ok"] is True
    assert R.credit_multiplier("eleven_flash_v2_5", reg) == 0.25                                                          # what it had is kept
    assert R.status(reg)["providers"]["elevenlabs"]["last_error"] and R.lookup("kie", "bytedance/seedance-2", reg)["media"] == "video"
    assert R.refresh(["elevenlabs"], {"elevenlabs": lambda: ELEVEN}, reg)["results"]["elevenlabs"]["ok"] is True
    assert R.status(reg)["providers"]["elevenlabs"]["last_error"] is None                                                 # a good refresh clears the note
    assert saved                                                                                                          # (the file existed before the failure)


def test_an_empty_or_odd_answer_is_a_failure_not_a_reason_to_mark_everything_gone(reg):
    R.refresh(["elevenlabs"], {"elevenlabs": lambda: ELEVEN}, reg)
    for odd in (lambda: [], lambda: "<html>", lambda: None, lambda: {"detail": "nope"}):
        r = R.refresh(["elevenlabs"], {"elevenlabs": odd}, reg)
        assert r["results"]["elevenlabs"]["ok"] is False
    assert R.lookup("elevenlabs", "eleven_v5_preview", reg)["availability"] == "available"


def test_a_model_that_is_no_longer_listed_is_marked_never_removed_and_comes_back_when_it_does(reg):
    R.refresh(["elevenlabs"], {"elevenlabs": lambda: ELEVEN}, reg)
    R.refresh(["elevenlabs"], {"elevenlabs": lambda: ELEVEN[:2]}, reg)
    gone = R.lookup("elevenlabs", "eleven_v5_preview", reg)
    assert gone and gone["availability"] == "not_listed" and gone["deprecation"]["status"] == "possibly_retired"
    assert R.lookup("elevenlabs", "eleven_v4", reg)["availability"] == "available"
    R.refresh(["elevenlabs"], {"elevenlabs": lambda: ELEVEN}, reg)
    assert R.lookup("elevenlabs", "eleven_v5_preview", reg)["availability"] == "available"


def test_a_deprecation_a_provider_announced_is_never_forgotten_by_a_quieter_list(reg):
    R.refresh(["elevenlabs"], {"elevenlabs": lambda: ELEVEN}, reg)

    def mark(data):
        data["models"]["elevenlabs/eleven_v5_preview"]["deprecation"] = {"status": "deprecated", "note": "Replaced by v5.", "replacement": "eleven_v5"}
        return data
    R._save(mark, reg)
    R.refresh(["elevenlabs"], {"elevenlabs": lambda: ELEVEN}, reg)
    assert R.lookup("elevenlabs", "eleven_v5_preview", reg)["deprecation"]["status"] == "deprecated"


def test_kie_and_openrouter_lists_are_folded_in_with_their_own_facts(reg):
    R.refresh(["kie", "openrouter"], {"kie": lambda: KIE, "openrouter": lambda: {"prices": {"openai/gpt-x": {"in": 1.0, "out": 3.0}}, "vision_capable": ["openai/gpt-x"], "structured": []}}, reg)
    k = R.lookup("kie", "google/nanobanana-2-1", reg)
    assert k["media"] == "image" and k["name"] == "Nano Banana 2.1" and k["price"]["known"] is False
    o = R.lookup("openrouter", "openai/gpt-x", reg)
    assert o["media"] == "llm" and o["capabilities"]["vision"] is True and o["price"]["value"] == {"in": 1.0, "out": 3.0}
    assert R.refresh(["nonsense"], {}, reg)["results"]["nonsense"]["ok"] is False


def test_the_registry_file_is_apart_from_films_and_a_damaged_one_never_breaks_anything(reg):
    assert R.PATH.endswith(os.path.join(".filmcrafter", "registry.json"))
    R.refresh(["elevenlabs"], {"elevenlabs": lambda: ELEVEN}, reg)
    open(reg, "wb").write(b'{"models": {"elevenlabs/eleven_v4": ')
    assert R.lookup("elevenlabs", "eleven_v4", reg)["name"] == "Eleven v4" and R.status(reg)["models"] >= 10               # the built-in list still answers
    assert any(f.startswith("registry.json.corrupt-") for f in os.listdir(os.path.dirname(reg)))                          # and the damaged bytes were kept


# ---------------------------------------------------------------- what a request may carry

def test_a_parameter_the_model_is_not_known_to_take_is_refused_and_a_missing_one_named(reg):
    ok = {"text": "x", "model_id": "eleven_text_to_sound_v2", "duration_seconds": 2}
    assert R.check_params("elevenlabs", "eleven_text_to_sound_v2", ok, reg) == []
    probs = R.check_params("elevenlabs", "eleven_text_to_sound_v2", {**ok, "seed": 5, "voice": "x"}, reg)
    assert len(probs) == 2 and "“seed” is not something Sound effects v2 takes." in probs
    assert R.check_params("elevenlabs", "music_v1", {"model_id": "music_v1"}, reg) == ["Eleven Music v1 needs “prompt”."]
    assert R.check_params("fal", "anything", {"x": 1}, reg) == []                                                          # a model with no listed inputs keeps its own checks


def test_the_generation_adapter_sends_only_parameters_the_registry_lists(tmp_path, monkeypatch):
    import filmcrafter_engine.audiogen as AG
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    sent = []
    monkeypatch.setenv("ELEVENLABS_KEY", "k")
    monkeypatch.setattr(AG, "_eleven_post", lambda path, **kw: sent.append(kw) or (_ for _ in ()).throw(AssertionError("must not be sent")))
    monkeypatch.setattr(R, "check_params", lambda *a, **k: ["“seed” is not something Sound effects v2 takes."])
    with pytest.raises(SystemExit, match="Not sent \\(nothing was charged\\)"):
        AG.generate(d, {"provider": "elevenlabs_sfx", "prompt": "a kettle clicking"}, confirmed=True, rights_ack=True)
    assert sent == []


# ---------------------------------------------------------------- the models behind a film (reported, never replaced)

def film_with_models(tmp_path):
    d = story.create(str(tmp_path / "films"), "T", "screenplay", SCRIPT)["dir"]
    bible.seed(d)
    ids = [s["id"] for s in S.breakdown(d)["shots"]]
    make.sync(d)
    rd = make.render_dir(d)
    os.makedirs(os.path.join(rd, "media"), exist_ok=True)
    _clip(os.path.join(rd, "media", "v0.mp4"), 2)
    _job(d, ids[0], "v0", "video", "media/v0.mp4")
    p = os.path.join(rd, "jobs.json")
    data = json.load(open(p))
    data["jobs"][0].update(provider="kie", model="old/video-model")
    json.dump(data, open(p, "w"))
    C.set_voice(d, "Sarah", {"voice_id": "AbCdEfGh1234", "voice_name": "Warm", "model": "eleven_v4"})
    return d


def test_a_film_reports_the_models_behind_its_work_and_warns_about_the_ones_that_went_away_without_changing_anything(tmp_path, reg, monkeypatch):
    monkeypatch.setenv(R.ENV, reg)
    d = film_with_models(tmp_path)
    open(os.path.join(tmp_path, "src.wav"), "wb").write(b"")
    import numpy as np
    import soundfile as sf
    sf.write(str(tmp_path / "s.wav"), (0.3 * np.sin(np.arange(22050) / 5.0)).astype("float32"), 22050)
    AL.add_file(d, "sfx", str(tmp_path / "s.wav"), source="generated", generation={"provider": "elevenlabs_sfx", "model": "eleven_text_to_sound_v2"})
    before = {f: open(os.path.join(d, *f.split("/")), "rb").read() for f in ("voice/cast.json", "audio/library.json")}
    r = R.in_use(d, reg)
    names = {(m["provider"], m["model"]) for m in r["models"]}
    assert {("elevenlabs", "eleven_v4"), ("elevenlabs", "eleven_text_to_sound_v2"), ("kie", "old/video-model")} <= names
    warn = {(w["provider"], w["model"]): w for w in r["warnings"]}
    assert set(warn) == {("kie", "old/video-model")} and warn[("kie", "old/video-model")]["why"] == "FilmCrafter has no record of this model."          # unknown, not condemned
    R.refresh(["elevenlabs"], {"elevenlabs": lambda: ELEVEN}, reg)
    R.refresh(["elevenlabs"], {"elevenlabs": lambda: [ELEVEN[1]]}, reg)                                                                              # eleven_v4 vanishes from a later list
    again = {(w["provider"], w["model"]): w for w in R.in_use(d, reg)["warnings"]}
    gone = again[("elevenlabs", "eleven_v4")]
    assert "no longer in the provider's list" in gone["why"] and gone["approved"] is True and "will not be swapped" in gone["note"] and "Nothing was replaced" in gone["note"]
    assert {f: open(os.path.join(d, *f.split("/")), "rb").read() for f in before} == before                                                           # not one record changed
    assert C._cast(d)["people"]["sarah"]["model"] == "eleven_v4"


def test_the_command_line_speaks_the_engine_format_and_only_knows_its_actions(reg, monkeypatch, capsys):
    monkeypatch.setenv(R.ENV, reg)
    assert R.main(["status"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["models"] >= 10
    assert R.main(["check", "--data", json.dumps({"provider": "elevenlabs", "model": "music_v1", "params": {"prompt": "x", "bad": 1}})]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["problems"]
    assert R.main(["in_use"]) == 1
    with pytest.raises(SystemExit):
        R.main(["delete_everything"])
