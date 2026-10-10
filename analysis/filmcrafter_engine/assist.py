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

KINDS = ("character", "environment", "prop", "world")
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


def schema_for(kind: str) -> dict:
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
    return {**_estimate(len(json.dumps(br, ensure_ascii=False)) + len(SYSTEM[kind]), 1, 700), "kind": kind, "id": id_,
            "sends": "your story and what the Bible already says about this" if kind != "world" else "your story and the names in your Bible"}


def _call(client, model: str, system: str, user: str, name: str, schema: dict) -> dict:
    resp = client.responses.create(model=model, input=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                                   text={"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}})
    return json.loads(resp.output_text)


def clean(kind: str, out: dict) -> dict:
    """Keep only the fields we asked for, trimmed and limited. Anything else the model wrote is dropped."""
    out = out if isinstance(out, dict) else {}
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
    return {"kind": kind, "id": id_, "proposal": clean(kind, out), "model": str(model), "estimate": estimate(d, kind, id_)}


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
