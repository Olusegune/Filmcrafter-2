"""Optional writing help for Cast & World: suggestions for a character, a place, a prop, or the world and its style, written from your story and what the Bible already says.

It only ever PROPOSES. Nothing here changes the Bible: the app shows the suggestion next to what you have, and you choose which parts to use. A field you already filled in is shown as
yours and is not touched unless you pick the suggestion for it. The price (free on a local model) is shown, and confirmed, before anything is sent.

  python -m filmcrafter_engine.assist <estimate|suggest> <film_dir> --data '{"kind": "character", "id": "c_sarah"}'
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from . import bible as B
from . import story

KINDS = ("character", "environment", "prop", "world", "story", "shot")
NEXT_STEP = {"idea": "synopsis", "synopsis": "treatment", "treatment": "outline", "outline": "screenplay"}   # the development ladder, one step at a time
STORY_LIMIT = 40000
STORY_CHARS = 12000
LIMIT = 1500

CHAR_FIELDS = ("role", "age", "physical", "relationships", "arc", "voice", "notes")
ENV_FIELDS = ("description", "notes")

SYSTEM = {
    "character": "You help a screenwriter and film director build a character sheet for an animated or live-action film. Use ONLY what the story shows and sensible, modest inferences from it; "
                 "where the story is silent, suggest something plain and fitting, and keep it short. Never change the plot, never invent new characters or events. "
                 "Write what a picture-maker needs: face, build, age, hair, how they carry themselves, usual clothes. Plain words, no flourish.",
    "environment": "You help a film director define a place so it looks the same in every shot. Use ONLY what the story shows plus modest, fitting inference. "
                   "Describe what the camera would see: materials, scale, colours, light sources, and where the doors, windows, landmarks and furniture are, so the place can be kept consistent. Plain words.",
    "prop": "You help a film director define an object that must look the same every time it appears. Use the story. Describe its size, material, colour, wear and how it is held. Plain words.",
    "story": "You help a writer take their story one step further along the way to a screenplay. Stay faithful to everything in the source: keep its characters, events, order, names and ending; "
             "add only what the next step needs, and keep it clear and plain. Do not add commentary or alternatives: write the step itself.",
    "shot": "You help a film director plan ONE shot of a scene: what the audience should feel, how each person plays it (what they want, need, fear and hide, shown through behaviour, never by naming the feeling), "
            "the small living motion that comes from that feeling, and the camera and light that serve it, each with a reason. Use only the story and the Bible given; never invent people, props, places or dialogue.",
    "world": "You help a film director write the rules of the world and the visual approach of a film, from its story. Be specific and brief. Choose the visual style that best fits the story and its audience. "
             "Never change the plot. Plain words, no flourish.",
}


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


def _text(v, limit: int = LIMIT) -> str:
    return str(v if v is not None else "").replace("\x00", "").strip()[:limit]


def _schema(props: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


def _s() -> dict:
    return {"type": "string"}


STEP_RULES = {
    "synopsis": "Write a synopsis: one to three short paragraphs, present tense, covering the whole story from beginning to end including the ending.",
    "treatment": "Write a treatment: the story told in present-tense prose, scene by scene, with the main images, actions and turning points, about one paragraph per scene.",
    "outline": "Write a scene outline: a numbered list, one line per scene, each saying where it happens and what happens that matters. Format: 1. INT. PLACE - TIME: what happens.",
    "screenplay": "Write the screenplay in standard format: a scene heading (INT. or EXT. PLACE - TIME) before every scene, action in short present-tense paragraphs, character names in capitals before their dialogue, "
                  "parentheticals only where needed. Keep every event, line and name from the source; do not shorten the story.",
}


def schema_for(kind: str) -> dict:
    if kind == "story":
        return _schema({"text": _s()})
    if kind == "shot":
        from .shots import ANGLE, FOCUS, FRAMING, LENS, MOVEMENT
        beat = _schema({k: _s() for k in ("character", "what", "want", "need", "fear", "hiding", "subtext", "start", "turn", "end")})

        def en(opts):
            return {"type": "string", "enum": list(opts)}
        return _schema({"emotional_intention": _s(), "beats": {"type": "array", "items": beat}, "micro_animation": _s(),
                        "camera": _schema({"framing": en(FRAMING), "angle": en(ANGLE), "lens": en(LENS), "movement": en(MOVEMENT), "focus": en(FOCUS), "why": _s()}),
                        "lighting": _schema({"description": _s(), "why": _s()})})
    if kind == "character":
        return _schema({**{k: _s() for k in CHAR_FIELDS}, "wardrobe": {"type": "array", "items": _schema({"name": _s(), "notes": _s()})},
                        "states": {"type": "array", "items": _schema({"label": _s(), "age": _s(), "notes": _s()})}})
    if kind == "environment":
        return _schema({**{k: _s() for k in ENV_FIELDS}, "spatial": _schema({k: _s() for k in B.SPATIAL_FIELDS})})
    if kind == "prop":
        return _schema({"notes": _s()})
    return _schema({"rules": _schema({k: _s() for k in B.RULE_FIELDS}), "philosophy": _schema({k: _s() for k in B.PHILOSOPHY_FIELDS}),
                    "style": _schema({"lane": {"type": "string", "enum": list(B.STYLE_LANES)}, "traits": _s()})})


def _story_text(d: str) -> str:
    m = story._manifest(d)
    n = m["story"].get("locked") or m["story"]["current"]
    rec = story._read(story._vpath(d, int(n))) or {}
    return str(rec.get("text", ""))


def _excerpts(text: str, names: list[str], limit: int = 4500) -> str:
    """The parts of the story that mention this person or place, so the model sees how they appear."""
    out, used = [], 0
    for para in re.split(r"\n\s*\n", text):
        if any(n and re.search(re.escape(n), para, re.I) for n in names):
            out.append(para.strip())
            used += len(para)
            if used >= limit:
                break
    return "\n\n".join(out)[:limit]


def next_step(d: str) -> str:
    """The step after this story on the way to a screenplay: idea, synopsis, treatment, outline, screenplay."""
    k = story._manifest(d)["story"]["kind"]
    if k not in NEXT_STEP:
        raise SystemExit("This is already a screenplay: there is no next step to write.")
    return NEXT_STEP[k]


def _entry(b: dict, kind: str, id_: str) -> dict:
    key = B.LISTKEY[kind]
    it = next((x for x in b[key] if x["id"] == id_), None)
    if not it:
        raise SystemExit(f"That {kind} isn't in the Bible.")
    return it


def brief(d: str, kind: str, id_: str | None = None) -> dict:
    """What would be sent: the story, the parts about this entry, and what the Bible already holds. Nothing else leaves the computer."""
    if kind not in KINDS:
        raise SystemExit("Choose character, environment, prop or world.")
    if kind == "story":
        target = next_step(d)
        return {"task": f"write the {target}", "instructions": STEP_RULES[target], "source_kind": story._manifest(d)["story"]["kind"], "source": _story_text(d)[:STORY_LIMIT],
                "cast_so_far": [c["name"] for c in B.load(d)["characters"]][:30]}
    if kind == "shot":
        from . import shots as S
        c = S._contract(d, B.check_id(id_ or "", "shot"))
        bb = B.load(d)
        names = {p["name"].lower() for p in c["characters"]}
        people = [x for x in bb["characters"] if x["name"].lower() in names]
        return {"task": "plan this shot", "shot": {k: c[k] for k in ("id", "story_purpose", "action", "dialogue", "blocking", "opening_state", "closing_state", "continuity")},
                "people": [{k: x[k] for k in ("name", "role", "age", "physical", "arc", "voice") if x.get(k)} for x in people], "place": {"name": c["environment"]["name"]},
                "style": bb["style"]["lane"], "tone": bb["rules"].get("tone", ""),
                "scene_text": _excerpts(_story_text(d), [p["name"] for p in c["characters"]] + [c["environment"]["name"]], 3000),
                "already_written": {"feeling": c["performance"]["emotional_intention"], "beats": c["performance"]["beats"], "camera": {k: v for k, v in c["camera"].items() if v}}}
    b = B.load(d)
    text = _story_text(d)
    ctx = {"title": story._manifest(d)["title"], "style": b["style"]["lane"], "world": b["rules"].get("world", ""), "tone": b["rules"].get("tone", "")}
    if kind == "world":
        return {"task": "world", "context": ctx, "story": text[:STORY_CHARS], "characters": [c["name"] for c in b["characters"]][:30], "places": [e["name"] for e in b["environments"]][:30],
                "already_written": {"rules": {k: v for k, v in b["rules"].items() if v}, "philosophy": {k: v for k, v in b["philosophy"].items() if v}, "style": b["style"]["traits"]}}
    it = _entry(b, kind, B.check_id(id_ or "", kind))
    names = [it["name"], it["name"].upper()]
    mine = {k: v for k, v in it.items() if k in CHAR_FIELDS + ENV_FIELDS + ("spatial",) and v}
    return {"task": kind, "name": it["name"], "context": ctx, "story_excerpts": _excerpts(text, names), "story_start": text[:1500],
            "other_characters": [c["name"] for c in b["characters"] if c["id"] != it["id"]][:20], "already_written": mine}


def estimate(d: str, kind: str, id_: str | None = None) -> dict:
    """The price of one suggestion: free on a local model, otherwise a few cents from the size of the request. Nothing is sent."""
    from .acting import _estimate
    br = brief(d, kind, id_)
    out_tokens = {"story": 3500 if (kind == "story" and next_step(d) == "screenplay") else 1200, "shot": 900}.get(kind, 700)
    sends = {"world": "your story and the names in your Bible", "story": "your whole story so far", "shot": "this shot, the people in it and the part of the story it comes from"}.get(
        kind, "your story and what the Bible already says about this")
    return {**_estimate(len(json.dumps(br, ensure_ascii=False)) + len(SYSTEM[kind]), 1, out_tokens), "kind": kind, "id": id_, "sends": sends}


def _call(client, model: str, system: str, user: str, name: str, schema: dict) -> dict:
    resp = client.responses.create(model=model, input=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                                   text={"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}})
    return json.loads(resp.output_text)


def clean(kind: str, out: dict) -> dict:
    """Keep only the fields we asked for, trimmed and limited. Anything else the model wrote is dropped."""
    out = out if isinstance(out, dict) else {}
    if kind == "story":
        t = _text(out.get("text"), 60000)
        return {"text": t} if t else {}
    if kind == "shot":
        from .shots import ANGLE, FOCUS, FRAMING, LENS, MOVEMENT
        res = {}
        if _text(out.get("emotional_intention")):
            res["emotional_intention"] = _text(out["emotional_intention"])
        beat_keys = ("character", "what", "want", "need", "fear", "hiding", "subtext", "start", "turn", "end")
        beats = [{k: _text(b.get(k), 600) for k in beat_keys} for b in (out.get("beats") or []) if isinstance(b, dict) and _text(b.get("what"), 600)][:6]
        if beats:
            res["beats"] = beats
        if _text(out.get("micro_animation")):
            res["micro_animation"] = _text(out["micro_animation"])
        cam = out.get("camera") if isinstance(out.get("camera"), dict) else {}
        c2 = {k: cam[k] for k, allowed in (("framing", FRAMING), ("angle", ANGLE), ("lens", LENS), ("movement", MOVEMENT), ("focus", FOCUS)) if cam.get(k) in allowed}
        if _text(cam.get("why")):
            c2["why"] = _text(cam["why"])
        if c2:
            res["camera"] = c2
        lit = out.get("lighting") if isinstance(out.get("lighting"), dict) else {}
        l2 = {k: _text(lit.get(k)) for k in ("description", "why") if _text(lit.get(k))}
        if l2:
            res["lighting"] = l2
        return res
    if kind == "character":
        res = {k: _text(out.get(k)) for k in CHAR_FIELDS if _text(out.get(k))}
        res["wardrobe"] = [{"name": _text(w.get("name"), 80), "notes": _text(w.get("notes"))} for w in (out.get("wardrobe") or []) if isinstance(w, dict) and _text(w.get("name"), 80)][:6]
        res["states"] = [{"label": _text(s.get("label"), 80), "age": _text(s.get("age"), 40), "notes": _text(s.get("notes"))} for s in (out.get("states") or []) if isinstance(s, dict) and _text(s.get("label"), 80)][:6]
        return {k: v for k, v in res.items() if v}
    if kind == "environment":
        res = {k: _text(out.get(k)) for k in ENV_FIELDS if _text(out.get(k))}
        sp = {k: _text((out.get("spatial") or {}).get(k)) for k in B.SPATIAL_FIELDS if isinstance(out.get("spatial"), dict) and _text((out.get("spatial") or {}).get(k))}
        if sp:
            res["spatial"] = sp
        return res
    if kind == "prop":
        return {"notes": _text(out.get("notes"))} if _text(out.get("notes")) else {}
    res: dict = {}
    for sec, fields in (("rules", B.RULE_FIELDS), ("philosophy", B.PHILOSOPHY_FIELDS)):
        sub = {k: _text((out.get(sec) or {}).get(k)) for k in fields if isinstance(out.get(sec), dict) and _text((out.get(sec) or {}).get(k))}
        if sub:
            res[sec] = sub
    st = out.get("style") if isinstance(out.get("style"), dict) else {}
    s2 = {}
    if st.get("lane") in B.STYLE_LANES:
        s2["lane"] = st["lane"]
    if _text(st.get("traits")):
        s2["traits"] = _text(st["traits"])
    if s2:
        res["style"] = s2
    return res


def suggest(d: str, kind: str, id_: str | None = None) -> dict:
    """Ask the configured brain (OpenAI, OpenRouter, Ollama or LM Studio) for a suggestion. Returns it; changes nothing."""
    from .director import DEFAULT_MODEL, openai_error, resolve_model
    from .llm import client as make_client
    br = brief(d, kind, id_)
    cl = make_client()
    model = resolve_model(cl, DEFAULT_MODEL)
    emit(event="progress", stage="writing a suggestion", progress=0.3)
    try:
        out = _call(cl, model, SYSTEM[kind], json.dumps(br, ensure_ascii=False), "suggestion", schema_for(kind))
    except SystemExit:
        raise
    except Exception as e:
        raise SystemExit(openai_error(e))
    emit(event="progress", stage="done", progress=1.0)
    prop = clean(kind, out)
    if kind == "story" and prop:
        prop["kind"] = next_step(d)
    return {"kind": kind, "id": id_, "proposal": prop, "model": str(model), "estimate": estimate(d, kind, id_)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-assist")
    ap.add_argument("action", choices=["estimate", "suggest"])
    ap.add_argument("target")
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        fn = estimate if a.action == "estimate" else suggest
        emit(event="result", data=fn(a.target, x.get("kind", ""), x.get("id")))
        return 0
    except SystemExit as e:
        emit(event="error", message=str(e))
        return 1
    except Exception as e:
        emit(event="error", message=f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
