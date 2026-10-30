"""OpenRouter as the AI brain: one key, hundreds of cheaper models. Settings, the client, the price list and the cost estimates."""
import json
import os
import types

import pytest

from filmcrafter_engine import acting, llm


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    path = tmp_path / "llm.json"
    monkeypatch.setattr(llm, "CONFIG", str(path))
    monkeypatch.setattr(llm, "MODELS_CACHE", str(tmp_path / "openrouter_models.json"))
    monkeypatch.delenv("FILMCRAFTER_OPENROUTER_KEY", raising=False)
    monkeypatch.delenv("FILMCRAFTER_OPENAI_KEY", raising=False)
    return path


def use(cfg_path, **kw):
    cfg_path.write_text(json.dumps({"provider": "openrouter", "model": "google/gemini-2.5-flash", "vision_model": "google/gemini-2.5-flash", **kw}))


# ---------------------------------------------------------------- settings
def test_openrouter_is_a_choice_with_its_own_address_and_needs_a_model(cfg):
    with pytest.raises(SystemExit) as e:
        llm.save({"provider": "openrouter", "model": ""})
    assert "Choose which model to use" in str(e.value)
    out = llm.save({"provider": "openrouter", "model": "deepseek/deepseek-chat-v3.1", "vision_model": "google/gemini-2.5-flash"})
    assert out["provider"] == "openrouter" and out["base_url"] == "https://openrouter.ai/api/v1" and out["model"] == "deepseek/deepseek-chat-v3.1"


def test_openrouter_is_only_reached_over_https_and_junk_addresses_are_refused(cfg):
    with pytest.raises(SystemExit):
        llm.save({"provider": "openrouter", "model": "m", "base_url": "http://evil.example.com/v1"})
    with pytest.raises(SystemExit):
        llm.save({"provider": "openrouter", "model": "m", "base_url": "not a url"})
    assert llm.save({"provider": "openrouter", "model": "m", "base_url": "https://openrouter.ai/api"})["base_url"].endswith("/v1")


def test_an_unknown_brain_is_refused_naming_all_four(cfg):
    with pytest.raises(SystemExit) as e:
        llm.save({"provider": "claude-direct", "model": "x"})
    assert "OpenAI, OpenRouter, Ollama or LM Studio" in str(e.value)


def test_the_local_brains_and_openai_are_unchanged(cfg):
    assert llm.save({"provider": "ollama", "model": "qwen3:14b"})["base_url"] == "http://127.0.0.1:11434/v1"
    assert llm.save({"provider": "lmstudio", "model": "gemma3"})["base_url"] == "http://127.0.0.1:1234/v1"
    assert llm.save({"provider": "openai"})["base_url"] == ""


def test_the_key_is_never_written_to_the_settings_file(cfg, monkeypatch):
    monkeypatch.setenv("FILMCRAFTER_OPENROUTER_KEY", "sk-or-secret-123")
    llm.save({"provider": "openrouter", "model": "m"})
    assert "secret" not in cfg.read_text() and "key" not in cfg.read_text().lower()


# ---------------------------------------------------------------- what kind of brain it is
def test_openrouter_is_a_paid_cloud_brain_not_a_free_local_one(cfg):
    use(cfg)
    assert llm.is_local() is False and llm.uses_openai() is False
    cfg.write_text(json.dumps({"provider": "ollama", "model": "m"}))
    assert llm.is_local() is True
    cfg.write_text(json.dumps({"provider": "openai"}))
    assert llm.uses_openai() is True and llm.is_local() is False


def test_the_brain_can_look_at_pictures_only_when_it_has_what_it_needs(cfg, monkeypatch):
    use(cfg)
    assert llm.visual_ready() is False                                      # no OpenRouter key yet
    monkeypatch.setenv("FILMCRAFTER_OPENROUTER_KEY", "k")
    assert llm.visual_ready() is True
    use(cfg, vision_model="")
    assert llm.visual_ready() is False                                      # a key but no model that sees images
    cfg.write_text(json.dumps({"provider": "openai"}))
    assert llm.visual_ready() is False
    monkeypatch.setenv("FILMCRAFTER_OPENAI_KEY", "k")
    assert llm.visual_ready() is True
    cfg.write_text(json.dumps({"provider": "ollama", "model": "m"}))
    assert llm.visual_ready() is True


# ---------------------------------------------------------------- the client
def test_the_client_uses_the_openrouter_address_the_key_and_identifies_the_app(cfg, monkeypatch):
    use(cfg)
    monkeypatch.setenv("FILMCRAFTER_OPENROUTER_KEY", "sk-or-test")
    c = llm.client()
    assert c.routed is True and c.local is False
    assert str(c._oa.base_url).startswith("https://openrouter.ai/api/v1") and c._oa.api_key == "sk-or-test"
    assert c._oa.default_headers.get("X-Title") == "FilmCrafter"
    assert llm.local_model(c) == "google/gemini-2.5-flash" and llm.local_model(c, vision=True) == "google/gemini-2.5-flash"


def test_without_a_key_the_client_says_where_to_add_it(cfg, monkeypatch):
    use(cfg)
    monkeypatch.setattr("keyring.get_password", lambda *a, **k: None)
    with pytest.raises(SystemExit) as e:
        llm.client()
    assert "Add your OpenRouter key in Settings" in str(e.value)


def test_a_missing_vision_model_is_explained_with_an_openrouter_example(cfg, monkeypatch):
    use(cfg, vision_model="")
    monkeypatch.setenv("FILMCRAFTER_OPENROUTER_KEY", "k")
    with pytest.raises(SystemExit) as e:
        llm.local_model(llm.client(), vision=True)
    assert "OpenRouter model that can see images" in str(e.value) and "google/gemini-2.5-flash" in str(e.value)


def test_openai_still_uses_its_own_client_and_key(cfg, monkeypatch):
    cfg.write_text(json.dumps({"provider": "openai"}))
    monkeypatch.setenv("FILMCRAFTER_OPENAI_KEY", "sk-test")
    c = llm.client()
    assert not hasattr(c, "cfg") and llm.local_model(c) is None


def test_the_openrouter_rejection_message_names_openrouter(cfg):
    from filmcrafter_engine.director import openai_error
    use(cfg)
    assert "OpenRouter rejected the key" in openai_error(RuntimeError("AuthenticationError: invalid_api_key"))
    cfg.write_text(json.dumps({"provider": "openai"}))
    assert "OpenAI rejected the key" in openai_error(RuntimeError("AuthenticationError: invalid_api_key"))


# ---------------------------------------------------------------- the price list
def resp(rows):
    r = types.SimpleNamespace(json=lambda: {"data": rows}, raise_for_status=lambda: None)
    return lambda: r


ROWS = [
    {"id": "openai/gpt-5", "pricing": {"prompt": "0.00000125", "completion": "0.00001"}, "architecture": {"input_modalities": ["text", "image"]}, "supported_parameters": ["structured_outputs"]},
    {"id": "deepseek/deepseek-chat-v3.1", "pricing": {"prompt": "0.0000002", "completion": "0.0000008"}, "architecture": {"input_modalities": ["text"]}, "supported_parameters": ["response_format"]},
    {"id": "google/gemini-2.5-flash", "pricing": {"prompt": "0.0000003", "completion": "0.0000025"}, "architecture": {"input_modalities": ["text", "image"]}, "supported_parameters": ["structured_outputs"]},
    {"id": "meta/free-one:free", "pricing": {"prompt": "0", "completion": "0"}, "architecture": {"input_modalities": ["text"]}, "supported_parameters": []},
    {"id": "odd/no-price", "pricing": {}},
    {"id": "", "pricing": {"prompt": "1"}}, {"id": 5}, "junk", None,
]


def test_the_list_is_cheapest_first_with_prices_in_dollars_per_million_tokens(cfg):
    r = llm.openrouter_models(resp([x for x in ROWS if isinstance(x, dict)]))
    assert r["models"] == ["meta/free-one:free", "deepseek/deepseek-chat-v3.1", "google/gemini-2.5-flash", "openai/gpt-5"]
    assert r["prices"]["deepseek/deepseek-chat-v3.1"] == {"in": 0.2, "out": 0.8} and r["prices"]["openai/gpt-5"] == {"in": 1.25, "out": 10.0}
    assert r["prices"]["meta/free-one:free"] == {"in": 0.0, "out": 0.0}
    assert r["vision_capable"] == ["google/gemini-2.5-flash", "openai/gpt-5"]
    assert r["structured"] == ["deepseek/deepseek-chat-v3.1", "google/gemini-2.5-flash", "openai/gpt-5"]
    assert "odd/no-price" not in r["models"]


def test_junk_rows_in_the_list_are_skipped_not_fatal(cfg):
    r = llm.openrouter_models(resp([x for x in ROWS if isinstance(x, dict)]))               # includes a row with no price, an empty id and a numeric id
    assert len(r["models"]) == 4
    assert llm.openrouter_models(resp([]))["models"] == []


def test_the_chosen_models_price_is_known_after_the_list_was_fetched_and_never_guessed(cfg):
    use(cfg, model="deepseek/deepseek-chat-v3.1")
    assert llm.price_per_mtok() is None                                           # no list fetched yet
    llm.openrouter_models(resp([x for x in ROWS if isinstance(x, dict)]))
    assert llm.price_per_mtok() == (0.2, 0.8)
    use(cfg, model="not/listed")
    assert llm.price_per_mtok() is None
    cfg.write_text(json.dumps({"provider": "openai"}))
    assert llm.price_per_mtok() is None


def test_a_damaged_price_file_is_ignored(cfg):
    use(cfg)
    open(llm.MODELS_CACHE, "w").write("{ not json")
    assert llm.price_per_mtok() is None


# ---------------------------------------------------------------- what an AI step costs
def test_an_ai_step_on_openrouter_is_priced_from_the_models_own_price(cfg):
    use(cfg, model="deepseek/deepseek-chat-v3.1")
    llm.openrouter_models(resp([x for x in ROWS if isinstance(x, dict)]))
    cheap = acting._estimate(8000, 1, 700)
    cfg.write_text(json.dumps({"provider": "openai"}))
    openai = acting._estimate(8000, 1, 700)
    assert cheap["local"] is False and cheap["usd"] > 0 and "OpenRouter's price" in cheap["note"]
    assert cheap["usd"] < openai["usd"] / 4 and "rough estimate" in openai["note"]


def test_a_local_brain_is_still_free_and_openrouter_is_never_called_free(cfg):
    cfg.write_text(json.dumps({"provider": "ollama", "model": "m"}))
    assert acting._estimate(8000, 1, 700)["usd"] == 0.0 and acting._estimate(8000, 1, 700)["local"] is True
    use(cfg)
    assert acting._estimate(8000, 1, 700)["local"] is False


# ---------------------------------------------------------------- the app shell
def test_the_key_is_kept_in_the_keychain_and_the_engine_gets_it_only_when_it_is_the_chosen_brain():
    lib = open(os.path.join(os.path.dirname(__file__), "..", "..", "src-tauri", "src", "lib.rs"), encoding="utf-8").read()
    assert '"elevenlabs", "openrouter", "byteplus"]' in lib                                                  # a provider whose key can be saved and read
    assert 'brain_provider() == "openrouter"' in lib and 'FILMCRAFTER_OPENROUTER_KEY' in lib
    assert 'matches!(brain_provider().as_str(), "ollama" | "lmstudio")' in lib                    # OpenRouter is not "local": it needs its key
