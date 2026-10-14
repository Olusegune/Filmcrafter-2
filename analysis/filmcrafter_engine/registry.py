"""The AI model registry: one place that says, for every model FilmCrafter can use, who offers it, what it is for, what it takes and gives, what it costs (or that nobody has said), whether it is still
there, and when that was last checked. It extends the providers FilmCrafter already talks to; it replaces none of them.

  built in (this file)           the models whose behaviour is written into the app: the known-good fallbacks, always available
  discovered (official lists)    ElevenLabs GET /v1/models (with its credit multipliers), Kie.ai's published model index, OpenRouter's model list, each read when the person asks, kept in
                                 ~/.filmcrafter/registry.json (NOT in a film and NOT with the app: models change on their own schedule, the app on another)
  seen in your films             a model that a take, a voice or a generated sound of a film was made with is looked up here too, so an old film never loses the meaning of its own records

Rules this keeps:
  * a discovery that fails (no network, a changed page) changes nothing and says so: the registry keeps what it had and the built-in list is always there;
  * a model that a later successful discovery no longer lists is marked "not listed" (and, only when the provider says so, deprecated or retired): never removed, because films refer to it;
  * nothing here ever changes a film: a model used by an approved take, a chosen voice or an approved sound is only REPORTED (`in_use`), never replaced;
  * `check_params` refuses to send a parameter the model is not known to take (for the models whose inputs are listed here; the video and picture models keep their own checked schemas in render.py).

  python -m filmcrafter_engine.registry <status|list|refresh|in_use|check> [film_dir] --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from . import safeio

SCHEMA = 1
PATH = os.path.join(os.path.expanduser("~"), ".filmcrafter", "registry.json")
ENV = "FILMCRAFTER_REGISTRY"          # tests (and anyone who wants it elsewhere) can point the registry at another file
STALE_DAYS = 14
MEDIA = ("speech", "sfx", "music", "image", "video", "llm", "audio_tool")
DEPRECATION = ("active", "deprecated", "retired", "possibly_retired", "unknown")
TODAY_CHECKED = "2026-10-14"


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


def _entry(provider: str, model: str, name: str, media: str, *, caps=None, inputs=None, outputs=None, price=None, availability="available", deprecation="active", note="", verified=TODAY_CHECKED,
           source="builtin") -> dict:
    return {"provider": provider, "model": model, "name": name, "media": media, "capabilities": caps or {}, "inputs": inputs or {"required": [], "optional": []}, "outputs": outputs or [],
            "price": price or {"known": False, "unit": None, "value": None, "source": None}, "availability": availability, "deprecation": {"status": deprecation, "note": note, "replacement": None},
            "verified": verified, "source": source}


def _ratio(v: float | None, source: str) -> dict:
    return {"known": v is not None, "unit": "elevenlabs_credits_per_character", "value": v, "source": source if v is not None else None}


# The fallbacks: what the app's own code is written against, checked against the providers' documentation on TODAY_CHECKED. Always available, whatever discovery does.
BUILTIN: list[dict] = [
    _entry("elevenlabs", "eleven_v4", "Eleven v4", "speech", caps={"direction_tags": True, "languages": "many"}, outputs=["mp3"], price=_ratio(1.0, "built in (ElevenLabs model list, 2026-10-13)")),
    _entry("elevenlabs", "eleven_v4_turbo", "Eleven v4 Turbo", "speech", caps={"direction_tags": True}, outputs=["mp3"], price=_ratio(0.5, "built in (ElevenLabs model list, 2026-10-13)")),
    _entry("elevenlabs", "eleven_v3", "Eleven v3", "speech", caps={"direction_tags": True}, outputs=["mp3"], price=_ratio(1.0, "built in (ElevenLabs model list, 2026-10-13)")),
    _entry("elevenlabs", "eleven_multilingual_v2", "Multilingual v2", "speech", caps={"direction_tags": False}, outputs=["mp3"], price=_ratio(1.0, "built in (ElevenLabs model list, 2026-10-13)")),
    _entry("elevenlabs", "eleven_flash_v2_5", "Flash v2.5", "speech", caps={"direction_tags": False}, outputs=["mp3"], price=_ratio(0.5, "built in (ElevenLabs model list, 2026-10-13)")),
    _entry("elevenlabs", "eleven_text_to_sound_v2", "Sound effects v2", "sfx", caps={"loop": True, "duration_seconds": [0.5, 30]}, outputs=["mp3", "pcm", "opus"],
           inputs={"required": ["text"], "optional": ["duration_seconds", "prompt_influence", "loop", "model_id"]},
           price={"known": True, "unit": "elevenlabs_credits_per_second", "value": 11, "source": "ElevenLabs help centre: 11 credits per second for a set duration, 100 per generation when the model chooses (API use)"}),
    _entry("elevenlabs", "music_v1", "Eleven Music v1", "music", caps={"instrumental": True, "length_seconds": [3, 600]}, outputs=["mp3", "pcm", "opus"],
           inputs={"required": ["prompt"], "optional": ["music_length_ms", "model_id", "force_instrumental", "seed"]}, note="Commercial rights depend on the plan and the terms (checked 2026-10-14): not established."),
    _entry("elevenlabs", "music_v2", "Eleven Music v2", "music", caps={"instrumental": True, "length_seconds": [3, 600]}, outputs=["mp3", "pcm", "opus"],
           inputs={"required": ["prompt"], "optional": ["music_length_ms", "model_id", "force_instrumental", "seed"]}),
    _entry("elevenlabs", "music_v2_5", "Eleven Music v2.5", "music", caps={"instrumental": True, "length_seconds": [3, 600]}, outputs=["mp3", "pcm", "opus"],
           inputs={"required": ["prompt"], "optional": ["music_length_ms", "model_id", "force_instrumental", "seed"]}),
    _entry("kie", "ai-music-api/generate", "Suno through Kie.ai", "music", caps={"instrumental": True, "tracks_per_request": 2}, outputs=["mp3"],
           inputs={"required": ["custom_mode", "instrumental", "model"], "optional": ["prompt", "style", "title", "negative_tags", "lyrics", "callBackUrl"]},
           note="Kie keeps the files 14 days. The price and the commercial rights are not stated by Kie (checked 2026-10-14)."),
]
KIE_SUNO_MODELS = ("V6", "V6_MINI", "V6_WILD")


def key(provider: str, model: str) -> str:
    return f"{provider}/{model}"


# ---------------------------------------------------------------- the file (separate from the app and from every film)

def _empty() -> dict:
    return {"schema": SCHEMA, "models": {}, "refreshed": {}, "errors": {}}


def _ok(x) -> bool:
    return isinstance(x, dict) and isinstance(x.get("models", {}), dict)


def _where(path: str | None) -> str:
    return path or os.environ.get(ENV) or PATH


def load(path: str | None = None) -> dict:
    """The saved registry; an unreadable or unsupported file never breaks anything (the built-in list still answers), and a damaged one is kept by safeio, not replaced."""
    try:
        data = safeio.read_json(_where(path), _empty(), check=_ok)
    except SystemExit:
        return _empty()
    data.setdefault("models", {}), data.setdefault("refreshed", {}), data.setdefault("errors", {})
    return data


def _save(change, path: str | None = None) -> dict:
    return safeio.update_json(_where(path), change, _empty(), check=_ok)


def all_models(path: str | None = None) -> list[dict]:
    """Every known model: the built-in ones, overlaid with what discovery learned (a built-in's own words win where they were written by hand), in a stable order."""
    saved = load(path)["models"]
    out = {key(e["provider"], e["model"]): dict(e) for e in BUILTIN}
    for k, e in saved.items():
        if k in out:
            b = out[k]
            b["availability"], b["verified"] = e.get("availability", b["availability"]), e.get("verified", b["verified"])
            if e.get("deprecation", {}).get("status") not in (None, "active", "unknown"):
                b["deprecation"] = e["deprecation"]
            if e.get("price", {}).get("known") and not b["price"].get("known"):
                b["price"] = e["price"]
            if e.get("price", {}).get("known") and e.get("source") == "discovered" and b["media"] == "speech":
                b["price"] = e["price"]                                              # ElevenLabs' own multiplier, as it says today, wins over the one written in
        else:
            out[k] = e
    return sorted(out.values(), key=lambda e: (e["provider"], e["media"], e["model"]))


def lookup(provider: str, model: str, path: str | None = None) -> dict | None:
    return next((e for e in all_models(path) if e["provider"] == provider and e["model"] == model), None)


def credit_multiplier(model: str, path: str | None = None) -> float | None:
    """ElevenLabs credits per character for a speech model, as ElevenLabs last said (discovered) or as written into the app; None when unknown."""
    e = lookup("elevenlabs", model, path)
    if e and e["media"] == "speech" and e["price"].get("known") and isinstance(e["price"].get("value"), (int, float)):
        return float(e["price"]["value"])
    return None


# ---------------------------------------------------------------- discovery (each provider's own list; an injected `fetch` keeps tests and failures harmless)

def discover_elevenlabs(fetch) -> list[dict]:
    """ElevenLabs GET /v1/models: speech models, with the credit multiplier ElevenLabs states for each (model_rates.character_cost_multiplier)."""
    rows = fetch()
    out = []
    for m in rows if isinstance(rows, list) else []:
        if not isinstance(m, dict) or not m.get("model_id") or not m.get("can_do_text_to_speech"):
            continue
        rate = (m.get("model_rates") or {}).get("character_cost_multiplier")
        mult = float(rate) if isinstance(rate, (int, float)) else (float(m["token_cost_factor"]) if isinstance(m.get("token_cost_factor"), (int, float)) else None)
        out.append(_entry("elevenlabs", str(m["model_id"])[:80], str(m.get("name") or m["model_id"])[:80], "speech",
                          caps={"direction_tags": None, "languages": len(m.get("languages") or []), "max_characters": m.get("maximum_text_length_per_request"), "style": m.get("can_use_style"),
                                "speaker_boost": m.get("can_use_speaker_boost"), "requires_alpha_access": bool(m.get("requires_alpha_access"))}, outputs=["mp3"],
                          price=_ratio(mult, "ElevenLabs GET /v1/models"), source="discovered", verified=time.strftime("%Y-%m-%d")))
    return out


def discover_kie(fetch) -> list[dict]:
    """Kie.ai's published model index (the app's own reader of it): video and picture models, names only (their inputs are read and checked one at a time by render.manifest)."""
    out = []
    for r in fetch() or []:
        if not isinstance(r, dict) or not r.get("doc"):
            continue
        slug = str(r["doc"]).split("/market/", 1)[-1].removesuffix(".md")
        out.append(_entry("kie", slug[:120], str(r.get("title") or slug)[:100], "video" if r.get("kind") == "video" else "image", caps={"family": r.get("family")}, source="discovered",
                          verified=time.strftime("%Y-%m-%d")))
    return out


def discover_openrouter(fetch) -> list[dict]:
    """OpenRouter's model list with its prices (US dollars per million tokens): the writing AIs."""
    r = fetch()
    out = []
    for mid, p in ((r or {}).get("prices") or {}).items():
        out.append(_entry("openrouter", str(mid)[:120], str(mid)[:120], "llm", caps={"vision": mid in set((r or {}).get("vision_capable", [])), "structured": mid in set((r or {}).get("structured", []))},
                          price={"known": True, "unit": "usd_per_million_tokens", "value": {"in": p.get("in"), "out": p.get("out")}, "source": "OpenRouter model list"}, source="discovered",
                          verified=time.strftime("%Y-%m-%d")))
    return out


DISCOVERERS = {"elevenlabs": discover_elevenlabs, "kie": discover_kie, "openrouter": discover_openrouter}


def _real_fetch(provider: str):
    if provider == "elevenlabs":
        def f():
            from . import cast_voice as C
            return C._check(C._get("/v1/models"), "list ElevenLabs' models").json()
        return f
    if provider == "kie":
        from .render import _kie_index
        return _kie_index
    from .llm import openrouter_models
    return openrouter_models


def refresh(providers: list[str] | None = None, fetchers: dict | None = None, path: str | None = None) -> dict:
    """Ask each provider for its model list and fold the answer in. A provider that cannot be reached (or whose answer is not what was expected) changes nothing and is reported; the others go on.
    A model that was known before and is missing from a SUCCESSFUL list is marked 'not listed', never removed."""
    results = {}
    for p in providers or list(DISCOVERERS):
        if p not in DISCOVERERS:
            results[p] = {"ok": False, "error": "Unknown provider."}
            continue
        try:
            found = DISCOVERERS[p]((fetchers or {}).get(p) or _real_fetch(p))
            if not found:
                raise ValueError("the list came back empty")
        except SystemExit as e:
            results[p] = {"ok": False, "error": str(e) or "stopped"}
            continue
        except Exception as e:
            results[p] = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:160]}"}
            continue
        now = int(time.time())
        seen = {key(e["provider"], e["model"]) for e in found}

        def change(data, _p=p, _found=found, _seen=seen, _now=now):
            data = {**_empty(), **data}
            for e in _found:
                old = data["models"].get(key(e["provider"], e["model"]), {})
                if (old.get("deprecation") or {}).get("status") in ("deprecated", "retired"):
                    e["deprecation"] = old["deprecation"]                       # what a provider said is never forgotten because a later list is quiet
                data["models"][key(e["provider"], e["model"])] = e
            for k, e in list(data["models"].items()):
                if e.get("provider") == _p and k not in _seen and e.get("source") == "discovered":
                    e["availability"] = "not_listed"
                    if (e.get("deprecation") or {}).get("status") in (None, "active", "unknown"):
                        e["deprecation"] = {"status": "possibly_retired", "note": "No longer in the provider's list.", "replacement": None}
            data["refreshed"][_p] = _now
            data["errors"].pop(_p, None)
            return data
        _save(change, path)
        results[p] = {"ok": True, "models": len(found)}
    failed = {p: r["error"] for p, r in results.items() if not r["ok"]}
    if failed:
        def note(data):
            data = {**_empty(), **data}
            data["errors"].update({p: {"error": e, "at": int(time.time())} for p, e in failed.items()})
            return data
        _save(note, path)
    return {"results": results, "kept": "Anything that could not be refreshed keeps what it had; the built-in models are always available."}


def observe(kind: str, value: float, path: str | None = None) -> None:
    """Remember what something really cost, as the provider reported it (for example credits per second of a sound effect). The last ten are kept, on this computer, apart from every film."""
    if not isinstance(value, (int, float)) or value <= 0:
        return

    def change(data):
        data = {**_empty(), **data}
        obs = data.setdefault("observed", {})
        obs[kind] = (obs.get(kind, []) + [round(float(value), 4)])[-10:]
        return data
    try:
        _save(change, path)
    except SystemExit:
        pass


def observed(kind: str, path: str | None = None) -> tuple[float, int] | None:
    """(the middle of what it really cost, how many times that was seen) once there are at least two sightings, else None."""
    vals = sorted((load(path).get("observed") or {}).get(kind, []))
    if len(vals) < 2:
        return None
    mid = vals[len(vals) // 2] if len(vals) % 2 else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2
    return round(mid, 3), len(vals)


def status(path: str | None = None) -> dict:
    data = load(path)
    now = time.time()
    return {"models": len(all_models(path)), "providers": {p: {"refreshed": data["refreshed"].get(p), "stale": (not data["refreshed"].get(p)) or (now - data["refreshed"][p]) > STALE_DAYS * 86400,
                                                              "last_error": (data["errors"].get(p) or {}).get("error")} for p in DISCOVERERS},
            "note": "Model lists are kept on this computer, apart from the app: refreshing them never changes a film."}


# ---------------------------------------------------------------- what the registry lets a request carry

def check_params(provider: str, model: str, params: dict, path: str | None = None) -> list[str]:
    """Problems in a request's parameters for a model whose inputs are listed here: a missing required one, or one the model is not known to take. [] when fine or when nothing is listed for it
    (then the caller's own checks apply). Never changes the request."""
    e = lookup(provider, model, path)
    if not e or not (e["inputs"]["required"] or e["inputs"]["optional"]):
        return []
    allowed = set(e["inputs"]["required"]) | set(e["inputs"]["optional"])
    probs = [f"“{k}” is not something {e['name']} takes." for k in params if k not in allowed]
    probs += [f"{e['name']} needs “{k}”." for k in e["inputs"]["required"] if k not in params]
    return probs


# ---------------------------------------------------------------- the models a film was made with (reported, never replaced)

def in_use(film: str, path: str | None = None) -> dict:
    """The models behind a film's takes, chosen voices and generated sounds, each with what the registry says about it today, and a warning when it is deprecated, retired, no longer listed or
    unknown. Nothing is changed: a model behind an approved or chosen asset is never swapped by this."""
    from . import audiolib as AL
    from . import cast_voice as C
    from . import library, make
    rows: dict[str, dict] = {}

    def add(provider: str, model: str, what: str, approved: bool) -> None:
        r = rows.setdefault(key(provider, model), {"provider": provider, "model": model, "used_for": [], "approved": False})
        r["used_for"].append(what)
        r["approved"] = r["approved"] or approved

    rd = make.render_dir(film)
    if os.path.isfile(os.path.join(rd, "jobs.json")):
        from .render import Store, _load_plan
        plan_name, plan = _load_plan(rd)
        jobs, state = Store(rd).jobs, library.shot_state(rd)
        for sc in plan.get("scenes", []):
            for sh in sc.get("shots", []):
                t = library.chosen_take(rd, sh["id"], plan_name, jobs, state)
                if t and t.get("provider") not in (None, "own"):
                    add(t["provider"], t["model"], f"the take in use for {sh['id']}", bool(state.get(sh["id"], {}).get("approved")))
    for k, v in C._cast(film)["people"].items():
        add("elevenlabs", v.get("model") or "", f"{v.get('name') or k}'s voice", True)
    for a in AL.load(film)["assets"]:
        g = a.get("generation") or {}
        if g.get("provider") and g.get("model"):
            add({"kie_suno": "kie", "elevenlabs_sfx": "elevenlabs", "elevenlabs_music": "elevenlabs"}.get(g["provider"], g["provider"]), g["model"] if g["provider"] != "kie_suno" else "ai-music-api/generate",
                f"the sound “{a['name']}”", a.get("approval") == "approved")
    out, warn = [], []
    for r in rows.values():
        e = lookup(r["provider"], r["model"], path)
        st = e["deprecation"]["status"] if e else "unknown"
        avail = e["availability"] if e else "unknown"
        bad = st in ("deprecated", "retired", "possibly_retired") or avail == "not_listed" or e is None
        row = {**r, "name": e["name"] if e else r["model"], "deprecation": st, "availability": avail, "known": e is not None, "verified": e["verified"] if e else None}
        out.append(row)
        if bad:
            warn.append({**{k: row[k] for k in ("provider", "model", "name", "used_for", "approved")},
                         "why": ("FilmCrafter has no record of this model." if e is None else "The provider has retired it." if st == "retired" else "The provider says it is going away." if st == "deprecated"
                                 else "It is no longer in the provider's list."),
                         "note": "Nothing was replaced. Work already made with it is kept as it is." + (" It is behind approved work, so it will not be swapped for another model." if r["approved"] else "")})
    return {"models": sorted(out, key=lambda r: (r["provider"], r["model"])), "warnings": warn}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="registry")
    ap.add_argument("action", choices=["status", "list", "refresh", "in_use", "check"])
    ap.add_argument("film", nargs="?", default="")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    try:
        x = json.loads(a.data or "{}")
        x = x if isinstance(x, dict) else {}
        if a.action == "status":
            res = status()
        elif a.action == "list":
            res = {"models": [e for e in all_models() if not x.get("media") or e["media"] == x["media"]]}
        elif a.action == "refresh":
            res = refresh(x.get("providers"))
        elif a.action == "check":
            res = {"problems": check_params(str(x.get("provider", "")), str(x.get("model", "")), x.get("params") or {})}
        else:
            if not a.film:
                raise SystemExit("Choose a film.")
            res = in_use(os.path.abspath(a.film))
        emit(event="result", data=res)
        return 0
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
