"""Director Engine: production plan (script import) -> fully directed Shot Contracts.

One structured-output call per scene. The model receives the scene's verbatim
script data, its timed shots, flags, the song context and the character bible,
and returns revised shots with complete direction. Hard constraints (scene time
span, beat-grid cuts, no invented story) are re-validated here, never trusted.

Key: handed over by the app from the OS credential store (FILMCRAFTER_OPENAI_KEY, this process only).
Model: FILMCRAFTER_DIRECTOR_MODEL env var or --model; not hard-coded in logic.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

DEFAULT_MODEL = os.environ.get("FILMCRAFTER_DIRECTOR_MODEL", "gpt-5")

SHOT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["source_shots", "beats", "dropped_beats", "duration_seconds", "purpose", "performers", "emotion",
                 "performance_intensity", "performance", "expression", "movement", "framing", "lens",
                 "camera_movement", "camera_energy", "lighting", "environment", "wardrobe", "continuity",
                 "sync_event", "visual_prompt"],
    "properties": {
        "source_shots": {"type": "array", "items": {"type": "string"},
                         "description": "Script shot ids (e.g. S05-06) whose beats this shot covers, in order."},
        "beats": {"type": "array", "items": {"type": "string"},
                  "description": "Story beats this shot shows, copied from the script beats."},
        "dropped_beats": {"type": "array", "items": {"type": "string"},
                          "description": "Script beats deliberately left out of this shot, if any."},
        "duration_seconds": {"type": "number"},
        "purpose": {"type": "string", "description": "Narrative/emotional job of the shot in one sentence."},
        "performers": {"type": "array", "items": {"type": "string"}},
        "emotion": {"type": "string"},
        "performance_intensity": {"type": "integer", "description": "1 (barely) to 10 (maximum)."},
        "performance": {"type": "string", "description": "Acting direction: intention, body language, gaze."},
        "expression": {"type": "string", "description": "Facial expression and its change within the shot."},
        "movement": {"type": "string", "description": "Physical action / blocking. Not dance unless scripted."},
        "framing": {"type": "string"},
        "lens": {"type": "string"},
        "camera_movement": {"type": "string"},
        "camera_energy": {"type": "string", "enum": ["still", "gentle", "moderate", "kinetic"]},
        "lighting": {"type": "string"},
        "environment": {"type": "string"},
        "wardrobe": {"type": "string"},
        "continuity": {"type": "string"},
        "sync_event": {"type": "string", "description": "What lands on a musical accent or lyric, or empty."},
        "visual_prompt": {"type": "string",
                          "description": "Renderer-neutral visual description of the shot, present tense, "
                                         "concrete, no camera jargon the image would not show."},
    },
}
SCENE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["director_note", "shots"],
    "properties": {
        "director_note": {"type": "string",
                          "description": "Brief note on choices made, especially any dropped or reshaped beats."},
        "shots": {"type": "array", "items": SHOT_SCHEMA},
    },
}

SYSTEM = """You are the Director Engine of FilmCrafter, a music-video production studio.
You direct one scene at a time from a writer's script. The writer is the creative authority:
- Never invent new story events, characters, locations or props. Use the script's beats and notes.
- Keep the scene's order of beats. You may merge beats into one continuous shot, or drop a beat
  only when there is not enough time to show it clearly; record every drop in dropped_beats and
  explain it in director_note. Prefer dropping repetitive beats over emotionally essential ones.
- Every shot needs at least ~0.8s per beat it shows and at least 1.5s total; flagged shots in the
  input are too dense and must be fixed.
- Shot durations must sum to the scene duration. Cuts are placed on beats by the software.
- Follow the scene's production notes (camera, lighting, performance, audio, VFX, continuity)
  and the character bible (appearance, acting notes). Performance means acting, not dancing.
- visual_prompt describes what the frame shows (characters by name and look, wardrobe, setting,
  light, action), so a video model can render it. Keep the stated visual style.
- If emotional_arcs are given, each shot's emotion and performance_intensity follow where its people are in their arc for the song section the shot sits in; do not
  reset a character's feeling from shot to shot.
- {CAMERA}"""
from .camera import director_vocabulary_text  # noqa: E402  (the same named choices the shot's camera picker offers)
SYSTEM = SYSTEM.replace("{CAMERA}", director_vocabulary_text())


def _is_local() -> bool:
    try:
        from .llm import is_local
        return is_local()
    except Exception:
        return False


def openai_error(e: Exception) -> str:
    """One clear sentence for OpenAI failures (quota, key, rate limit), else the original error."""
    t = f"{type(e).__name__}: {e}"
    low = t.lower()
    if "insufficient_quota" in low or "credit_balance_exhausted" in low or "no credits remaining" in low:
        return ("Your OpenAI account is out of credits. Add credits at platform.openai.com → Settings → Billing, "
                "then try again (the key itself is fine).")
    if "invalid_api_key" in low or "incorrect api key" in low or "authenticationerror" in low:
        try:
            from .llm import config
            if config()["provider"] == "openrouter":
                return "OpenRouter rejected the key. Check it in Settings."
        except Exception:
            pass
        return "OpenAI rejected the key. Check it in Settings."
    if ("connection" in low or "refused" in low or "connecterror" in low) and _is_local():
        from .llm import NAMES, config
        c = config()
        return f"{NAMES[c['provider']]} isn't answering at {c['base_url']}. Start it (and load the model), or switch back to OpenAI in Settings."
    if "model" in low and ("not found" in low or "404" in low) and _is_local():
        from .llm import config
        return f"The local server doesn't have the model “{config()['model']}”. Pull/load it, or pick another in Settings."
    if "ratelimit" in low or "429" in low:
        return "OpenAI is limiting requests right now. Wait a minute and try again."
    return t


def _client():
    """OpenAI, or a local model (Ollama / LM Studio) behind the same interface. See llm.py."""
    from .llm import client
    return client()


# A plan that came from somewhere else (a Producer package) may not carry every field a script-made shot has.
SHOT_DEFAULTS = {"source_shots": [], "beats": [], "framing": "", "camera_moves": [], "performers": [], "lyrics": [], "sync_accents": [], "flags": []}


def arcs_of(project_dir: str) -> dict:
    """The characters' emotional arcs ({name: [{section, emotion, intensity, note}]}) as the Director should see them, or {} (never an error: an arc only helps)."""
    try:
        from . import acting
        return {n: acting.clean_arc(v.get("points"), [s["name"] for s in acting.sections(project_dir)]) for n, v in acting.load(project_dir)["arc"].items()}
    except Exception:
        return {}


def scene_brief(plan: dict, scene: dict, song_map: dict, arcs: dict | None = None) -> str:
    lyric_idx = scene.get("sung_lines", [])
    here = {p for sh in scene["shots"] for p in sh.get("performers") or []} | set(scene.get("characters") or [])
    arcs = {n: pts for n, pts in (arcs or {}).items() if pts and n in here}
    return json.dumps({
        **({"emotional_arcs": arcs} if arcs else {}),
        "project": plan["meta"],
        "characters": plan["characters"],
        "scene": {k: scene[k] for k in ("number", "heading", "fields", "notes", "characters", "start", "end")},
        "scene_duration_seconds": round(scene["end"] - scene["start"], 2),
        "bpm": song_map["bpm"],
        "song_sections_in_scene": [s for s in song_map["sections"]
                                   if s["start"] < scene["end"] and s["end"] > scene["start"]],
        "lyrics_in_scene": [song_map["lyrics"][i] for i in lyric_idx],
        "planned_shots": [{k: sh.get(k, SHOT_DEFAULTS.get(k)) for k in ("id", "source_shots", "beats", "framing", "camera_moves",
                                                                       "performers", "start", "end", "lyrics", "sync_accents", "flags")}
                          for sh in scene["shots"]],
    }, ensure_ascii=False)


def direct_scene(client, model: str, plan: dict, scene: dict, song_map: dict, arcs: dict | None = None) -> dict:
    resp = client.responses.create(
        model=model,
        input=[{"role": "system", "content": SYSTEM},
               {"role": "user", "content": scene_brief(plan, scene, song_map, arcs)}],
        text={"format": {"type": "json_schema", "name": "directed_scene", "schema": SCENE_SCHEMA, "strict": True}},
    )
    return json.loads(resp.output_text)


def retime(scene: dict, shots: list[dict], beats: list[float]) -> None:
    """Scale model durations to the scene span and snap cuts to the beat grid."""
    a0, a1 = scene["start"], scene["end"]
    total = sum(max(0.5, s["duration_seconds"]) for s in shots) or 1.0
    t, cuts = a0, [a0]
    for s in shots[:-1]:
        t += (a1 - a0) * max(0.5, s["duration_seconds"]) / total
        cuts.append(min((b for b in beats if cuts[-1] < b < a1), key=lambda b: abs(b - t), default=t))
    cuts.append(a1)
    for k, (s, a, b) in enumerate(zip(shots, cuts[:-1], cuts[1:]), 1):
        s["id"] = f"S{scene['number']:02d}-{k:02d}"
        s["scene"], s["number"] = scene["number"], k
        s["start"], s["end"] = round(a, 3), round(b, 3)
        s["duration_seconds"] = round(b - a, 3)
        s["performance_intensity"] = max(1, min(10, int(s.get("performance_intensity", 5))))
        s.setdefault("renderer", "auto")
        s.setdefault("state", "planned")


def normalize_sources(scene: dict, shots: list[dict]) -> None:
    """The model sometimes names a planned shot by its own id (S05-04) instead of the source id the plan lists for it (a Producer
    package's shot_028). Both mean the same beat, so the id is replaced by the planned shot's own source ids, and the order check
    and the audit of what was merged work the same for scripts and packages."""
    planned = {sh["id"]: sh for sh in scene["shots"]}
    listed = {sid for sh in scene["shots"] for sid in sh["source_shots"]}
    for s in shots:
        out: list[str] = []
        for sid in s.get("source_shots") or []:
            out += planned[sid]["source_shots"] if sid in planned and sid not in listed else [sid]
        s["source_shots"] = list(dict.fromkeys(out))


def validate(scene: dict, shots: list[dict]) -> list[str]:
    known = {sid for sh in scene["shots"] for sid in sh["source_shots"]}
    issues = []
    for s in shots:
        unknown = set(s["source_shots"]) - known
        if unknown:
            issues.append(f"{s['id']}: unknown source shots {sorted(unknown)}")
        if s["end"] - s["start"] < 1.45:
            issues.append(f"{s['id']}: under 1.5s")
        if s["beats"] and (s["end"] - s["start"]) / len(s["beats"]) < 0.75:
            issues.append(f"{s['id']}: overloaded ({len(s['beats'])} beats)")
    covered = [sid for s in shots for sid in s["source_shots"]]
    order = [sid for sh in scene["shots"] for sid in sh["source_shots"]]
    if [x for x in order if x in covered] != [x for x in covered if x in order]:
        issues.append("beat order changed")
    return issues


PREFERRED = ("gpt-5", "gpt-4.1", "gpt-4o")  # families that support strict structured outputs


def resolve_model(client, wanted: str, vision: bool = False) -> str:
    """Use the requested model if this account has it; otherwise the newest preferred family member.
    A local brain always uses the model chosen in Settings (its vision model for take review)."""
    from .llm import local_model
    local = local_model(client, vision)
    if local:
        return local
    try:
        ids = {m.id for m in client.models.list()}
    except Exception:
        return wanted  # listing not permitted: let the call itself report problems
    newer = sorted(i for i in ids if re.fullmatch(re.escape(wanted) + r"\.\d+", i))  # gpt-5 -> gpt-5.1
    if newer:
        return newer[-1]
    if wanted in ids:
        return wanted
    for family in PREFERRED:
        cands = sorted(i for i in ids if i == family or (i.startswith((family + "-", family + ".")) and not any(
            x in i for x in ("mini", "nano", "audio", "realtime", "search", "transcribe", "tts", "image"))))
        if cands:
            return cands[-1]
    raise SystemExit(f"No suitable OpenAI model available (wanted {wanted}).")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="filmcrafter-director")
    p.add_argument("plan")
    p.add_argument("song_map")
    p.add_argument("--out", required=True)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--scenes", help="comma-separated scene numbers (default: all)")
    a = p.parse_args(argv)
    with open(a.plan, encoding="utf-8") as f:
        plan = json.load(f)
    with open(a.song_map, encoding="utf-8") as f:
        song_map = json.load(f)
    want = {int(x) for x in a.scenes.split(",")} if a.scenes else None
    client = _client()
    a.model = resolve_model(client, a.model)
    arcs = arcs_of(os.path.dirname(os.path.abspath(a.plan)))
    out = {"schema_version": 1, "model": a.model, "meta": plan["meta"], "characters": plan["characters"],
           "scenes": []}
    for scene in plan["scenes"]:
        if want and scene["number"] not in want:
            continue
        print(json.dumps({"event": "progress", "stage": f"directing scene {scene['number']} of {len(plan['scenes'])}"}),
              flush=True)
        try:
            directed = direct_scene(client, a.model, plan, scene, song_map, arcs)
        except Exception as e:  # surface a readable reason to the app instead of a traceback
            print(json.dumps({"event": "error", "message": f"Scene {scene['number']}: {openai_error(e)}"}), flush=True)
            return 1
        normalize_sources(scene, directed["shots"])
        retime(scene, directed["shots"], song_map["beats"])
        issues = validate(scene, directed["shots"])
        out["scenes"].append({**{k: scene[k] for k in ("number", "heading", "start", "end", "notes")},
                              "director_note": directed["director_note"], "issues": issues,
                              "shots": directed["shots"]})
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
