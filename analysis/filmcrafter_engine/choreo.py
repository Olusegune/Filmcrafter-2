"""Choreography Engine: designs (or follows) dance movement for the characters who dance, on the song's beat,
and places it shot by shot so it can be injected into keyframe (a pose) and video (the motion) prompts.

Sources, in order of authority: the user's uploaded sheet (text/PDF/MD) and written cues > the chosen style and
notes > what the music (tempo, sections, energy), lyrics and script suggest. Acting-led shots stay acting-led.
AI video follows this as direction: style, energy and key moves, not frame-exact steps.

  python -m filmcrafter_engine.choreo design <project> [--notes "..."]   (OpenAI)
  python -m filmcrafter_engine.choreo clear <project>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from .onboarding import choreo_get

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["concept", "dancers", "sections", "shots"],
    "properties": {
        "concept": {"type": "string", "description": "Two sentences: the movement idea for this video and how it serves the story."},
        "dancers": {"type": "array", "items": {"type": "string"}, "description": "Character names who dance (exactly as given)."},
        "sections": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["section", "feel", "counts"],
            "properties": {
                "section": {"type": "string", "description": "Section name exactly as given, e.g. 'Chorus 2'."},
                "feel": {"type": "string"},
                "counts": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["counts", "move"],
                    "properties": {"counts": {"type": "string", "description": "e.g. '1-8', '9-16'"}, "move": {"type": "string"}}}}}}},
        "shots": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["shot_id", "dancing", "pose", "motion", "energy"],
            "properties": {
                "shot_id": {"type": "string"},
                "dancing": {"type": "boolean", "description": "False for acting-led shots and shots without dancers."},
                "pose": {"type": "string", "description": "The freeze-frame pose at the start of the shot, visible to camera (for the keyframe). Empty if not dancing."},
                "motion": {"type": "string", "description": "What the dancers' bodies do across the shot, on the beat. Empty if not dancing."},
                "energy": {"type": "integer", "minimum": 1, "maximum": 10}}}}},
}

SYSTEM = """You are the choreographer of a music video. Design movement for the characters who dance.
Rules:
- Follow the user's choreography sheet and cues exactly where they cover a section; fill the rest in the same style.
- Only characters named as dancers (or who clearly dance in the script/brief) dance. Acting-led, intimate or
  story-critical shots stay acting-led: set dancing=false there. Never make every shot a dance shot unless asked.
- Move on the music: counts are 8-counts at the given BPM; energy follows the sections (verses restrained, choruses open up).
- Describe moves concretely and camera-visibly (body parts, direction, level, formation), in plain language a
  video model can render: e.g. "both dancers drop into a low bounce, shoulders rolling back on 1 and 5, arms loose".
- Respect framing: in close-ups describe upper-body/face-level movement only; in wides, footwork and formation.
- Keep continuity between neighbouring shots. No stunts, flips or contact that looks unsafe.
- pose = the exact starting pose of the shot (a still); motion = what happens over the shot."""


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _plan(d: str) -> tuple[str, dict]:
    name = "directed" if os.path.exists(os.path.join(d, "directed.json")) else "production"
    return name, _read(os.path.join(d, f"{name}.json"), {"scenes": []})


def numbered_sections(song_map: dict) -> list[dict]:
    """'Chorus 2' needs numbered sections; also used to find a shot's section by time."""
    out, seen = [], {}
    for s in song_map.get("sections", []):
        group = (s.get("group") or "").strip()
        # "Verse"/"Chorus" beat bare letter groups ("A", "B") that songs mapped without lyrics get
        label = (group if len(group) > 2 else s.get("label") or group or "Section").strip()
        base = label.rstrip("0123456789 ").title() or "Section"
        seen[base] = seen.get(base, 0) + 1
        out.append({"name": f"{base} {seen[base]}", "base": base, "start": s["start"], "end": s["end"],
                    "energy": s.get("energy"), "mood": s.get("mood")})
    return out


def section_at(sections: list[dict], t: float) -> dict | None:
    return next((s for s in sections if s["start"] <= t < s["end"]), sections[-1] if sections else None)


def sheet_text(d: str, files: list[str]) -> str:
    """Readable text from uploaded sheets (TXT/MD/PDF). Videos and images are noted, not interpreted."""
    from .script_import import read_text
    parts = []
    for f in files:
        p = os.path.join(d, f)
        ext = os.path.splitext(f)[1].lower()
        if ext in (".txt", ".md", ".pdf") and os.path.exists(p):
            try:
                parts.append(f"[{os.path.basename(f)}]\n{read_text(p)[:6000]}")
            except Exception:
                pass
        else:
            parts.append(f"[{os.path.basename(f)}: reference {'video' if ext in ('.mp4', '.mov', '.m4v', '.webm') else 'image'} "
                         f"supplied by the user; match its style and energy]")
    return "\n\n".join(parts)


def brief(d: str, notes: str = "") -> dict:
    sm = _read(os.path.join(d, "songmap.json"))
    if not sm:
        raise SystemExit("FilmCrafter needs to listen to the song first.")
    name, plan = _plan(d)
    shots = [s for sc in plan.get("scenes", []) for s in sc.get("shots", [])]
    if not shots:
        raise SystemExit("Plan the shots first (a script or a creative direction); choreography is placed shot by shot.")
    secs = numbered_sections(sm)
    c = choreo_get(d)
    lyr = sm.get("lyrics") or []
    return {
        "bpm": round(sm.get("bpm") or 0, 1), "seconds_per_8_count": round(8 * 60 / (sm.get("bpm") or 120), 2),
        "style": c.get("style"), "user_notes": c.get("notes") or "", "extra_notes": notes,
        "user_cues": c.get("sections") or [], "sheet": sheet_text(d, c.get("files") or []),
        "characters": [{"name": ch.get("name"), "appearance": (ch.get("appearance") or "")[:200]} for ch in plan.get("characters", [])],
        "story": {k: v for k, v in (plan.get("meta") or {}).items() if k in ("LOGLINE", "TITLE", "GENRE", "TONE")},
        "sections": [{"name": s["name"], "start": round(s["start"], 2), "end": round(s["end"], 2), "energy": s["energy"], "mood": s["mood"],
                      "lyrics": [l["text"] for l in lyr if l.get("start") is not None and s["start"] <= l["start"] < s["end"]][:6]} for s in secs],
        "shots": [{"id": s["id"], "start": round(s["start"], 2), "end": round(s["end"], 2),
                   "section": (section_at(secs, (s["start"] + s["end"]) / 2) or {}).get("name"),
                   "performers": s.get("performers", []), "framing": s.get("framing"),
                   "what": (s.get("visual_prompt") or " ".join(s.get("beats", [])))[:200]} for s in shots],
    }


def design(d: str, notes: str = "") -> dict:
    from .director import DEFAULT_MODEL, _client, resolve_model
    b = brief(d, notes)
    client = _client()
    model = resolve_model(client, DEFAULT_MODEL)
    print(json.dumps({"event": "progress", "stage": "choreographing", "progress": 0.2}), flush=True)
    resp = client.responses.create(
        model=model, input=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(b, ensure_ascii=False)}],
        text={"format": {"type": "json_schema", "name": "choreography", "schema": SCHEMA, "strict": True}},
    )
    out = json.loads(resp.output_text)
    return save_plan(d, out, model, b)


def save_plan(d: str, out: dict, model: str, b: dict) -> dict:
    ids = {s["id"] for s in b["shots"]}
    shots = {s["shot_id"]: {k: s[k] for k in ("dancing", "pose", "motion", "energy")} for s in out["shots"]
             if s["shot_id"] in ids and s["dancing"] and s["motion"].strip()}
    plan = {"concept": out["concept"], "dancers": out["dancers"], "sections": out["sections"], "shots": shots,
            "bpm": b["bpm"], "model": model, "made": int(time.time()),
            "source": "sheet" if b["sheet"] or b["user_cues"] else "designed"}
    c = choreo_get(d)
    c["plan"] = plan
    if c.get("mode") in (None, "none"):
        c["mode"] = "ai"
    tmp = os.path.join(d, f"choreography.json.{os.getpid()}.tmp")
    json.dump(c, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(d, "choreography.json"))
    return plan


def clear(d: str) -> dict:
    c = choreo_get(d)
    c.pop("plan", None)
    tmp = os.path.join(d, f"choreography.json.{os.getpid()}.tmp")
    json.dump(c, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(d, "choreography.json"))
    return c


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-choreo")
    ap.add_argument("action", choices=["design", "clear"])
    ap.add_argument("project")
    ap.add_argument("--notes", default="")
    a = ap.parse_args(argv)
    try:
        res = design(a.project, a.notes) if a.action == "design" else clear(a.project)
        print(json.dumps({"event": "result", "data": res}, ensure_ascii=False), flush=True)
        return 0
    except SystemExit as e:
        print(json.dumps({"event": "error", "message": str(e)}), flush=True)
    except Exception as e:
        from .director import openai_error
        print(json.dumps({"event": "error", "message": openai_error(e)}), flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
