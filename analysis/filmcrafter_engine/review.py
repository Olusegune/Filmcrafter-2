"""Review (PRD §27): check each finished take and surface only useful feedback.

Two tiers:
  technical  — always, local and free: long enough for its shot, no black/frozen stretches, decodable.
  visual     — when an OpenAI key is available: frames from the part of the take that will actually be
               used, compared against the character sheet, the shot contract and the project look.
Results are stored on the job (`review`) so they survive restarts and never cost twice.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import tempfile

from .anatomy import LOOK_FOR, with_fix
from .export import NO_WINDOW, ffmpeg

ISSUE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["verdict", "issues", "summary"],
    "properties": {
        "verdict": {"type": "string", "enum": ["good", "minor", "needs_attention"]},
        "summary": {"type": "string", "description": "One short sentence a director would say about the take."},
        "issues": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["kind", "severity", "detail", "fix"],
            "properties": {
                "kind": {"type": "string", "enum": ["character", "wardrobe", "environment", "look", "action",
                                                   "artifact", "anatomy", "text", "framing", "performance"]},
                "severity": {"type": "string", "enum": ["minor", "major"]},
                "detail": {"type": "string", "description": "What is wrong, in plain words, e.g. 'Sege has no beard'."},
                "fix": {"type": "string", "description": "A short instruction to add to the render prompt to fix it."},
            }}},
    },
}

SYSTEM = """You are the continuity supervisor on an animated music video.
You see: the project's character sheet, then frames sampled from one rendered shot.
Judge only what matters to a viewer. Report an issue only when you can see it:
- character: a named performer doesn't match the sheet (face, hair, beard, skin tone, age, proportions)
- wardrobe: clothing differs from the sheet or the shot's continuity notes
- environment: the setting contradicts the shot description
- look: the rendering style differs from the requested look
- action: the frames don't show what the shot describes
- artifact: melting objects, a malformed face, flicker
- """ + LOOK_FOR + """
- text: visible text, subtitles or watermarks
- framing: framing clearly differs from the requested framing
- performance: the acting is not what the shot asks for. The shot contract may give the intended emotion, its strength, the expression and the timed beats; the frames are
  labelled with their time in the shot. Report it when a performer's face or body clearly shows another feeling than the intended one, when a beat that should be visible
  at its time is not, or when a performer is frozen (the same blank face and pose in every frame) in a shot that describes a change. Judge only what the frames show; a
  performer who is simply facing away, small in frame or out of frame is not a performance issue; report nothing about acting when nobody is in the shot.
Minor = noticeable but usable. Major = would break the video. If the take is usable, say good."""


def _probe(path: str) -> dict:
    p = subprocess.run([ffmpeg(), "-hide_banner", "-i", path, "-vf", "blackdetect=d=0.4:pix_th=0.08,freezedetect=n=0.003:d=1.2",
                        "-an", "-f", "null", "-"], capture_output=True, text=True, creationflags=NO_WINDOW)
    err = p.stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    size = re.search(r"Video: .*?, (\d{2,5})x(\d{2,5})", err)
    return {"duration": dur, "width": int(size.group(1)) if size else 0, "height": int(size.group(2)) if size else 0,
            "black": [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)],
            "frozen": [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", err)],
            "decodes": p.returncode == 0 and dur > 0}


def technical(path: str, need: float) -> list[dict]:
    info = _probe(path)
    issues = []
    if not info["decodes"]:
        return [{"kind": "technical", "severity": "major", "detail": "The video file can't be read.", "fix": ""}]
    if info["duration"] + 0.05 < need:
        issues.append({"kind": "technical", "severity": "major",
                       "detail": f"Take is {info['duration']:.1f}s but the shot needs {need:.1f}s.", "fix": ""})
    used_black = [b for b in info["black"] if b[0] < need]
    if used_black:
        issues.append({"kind": "technical", "severity": "major" if used_black[0][1] - used_black[0][0] > 0.8 else "minor",
                       "detail": f"Black frames at {used_black[0][0]:.1f}s.", "fix": ""})
    if any(f < need for f in info["frozen"]):
        issues.append({"kind": "technical", "severity": "minor", "detail": "The picture freezes inside the part that's used.", "fix": ""})
    return issues


def _frames_at(path: str, need: float, n: int = 3) -> list[tuple[float, str]]:
    """(seconds into the shot, JPEG as base64) for n frames spread over the part of the take that ends up in the edit."""
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n):
            t = need * (i + 0.5) / n
            f = os.path.join(tmp, f"f{i}.jpg")
            subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", path,
                            "-frames:v", "1", "-vf", "scale=768:-2", "-q:v", "4", f], creationflags=NO_WINDOW)
            if os.path.exists(f):
                out.append((round(t, 2), base64.b64encode(open(f, "rb").read()).decode()))
    return out


def _frames(path: str, need: float, n: int = 3) -> list[str]:
    return [b for _, b in _frames_at(path, need, n)]


def performance_brief(d: str, shot: dict) -> dict | None:
    """What the shot asks of its performers, for the reviewer: the emotion and its strength, the expression and movement, the timed beats and where each person is in their arc.
    None when nobody is in the shot or nothing is asked of them (then the reviewer is told not to judge acting)."""
    if not shot.get("performers"):
        return None
    try:
        from . import acting
        beats = acting.clean_beats((acting.load(d)["beats"].get(shot.get("id")) or {}).get("beats"), max(0.5, shot["end"] - shot["start"]))
        arc = acting.arc_text(d, shot)
    except Exception:
        beats, arc = [], None
    ask = {"emotion": shot.get("emotion"), "intensity_1_to_10": shot.get("performance_intensity"), "performance": shot.get("performance"), "expression": shot.get("expression"),
           "movement": shot.get("movement"), "beats": [{"from_s": b["t0"], "to_s": b["t1"], "what": b["what"], **{k: b[k] for k in ("face", "eyes", "hands", "breath") if b.get(k)}} for b in beats],
           "arc": arc}
    return {k: v for k, v in ask.items() if v not in (None, "", [])} or None


def _image(path: str, max_w: int = 1024) -> str:
    from PIL import Image
    import io
    im = Image.open(path).convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, round(max_w * im.height / im.width)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82)
    return base64.b64encode(buf.getvalue()).decode()


def visual(d: str, project: dict, shot: dict, take: str, need: float) -> dict | None:
    from .llm import client as brain, visual_ready
    if not visual_ready():
        return None
    from .director import DEFAULT_MODEL, resolve_model
    from .render import resolve_look
    client = brain()
    model = resolve_model(client, DEFAULT_MODEL, vision=True)
    content = []
    sheet = (project.get("references") or {}).get("characters")
    if sheet and os.path.exists(os.path.join(d, sheet)):
        content += [{"type": "input_text", "text": "Character sheet:"},
                    {"type": "input_image", "image_url": f"data:image/jpeg;base64,{_image(os.path.join(d, sheet))}"}]
    acting_ask = performance_brief(d, shot)
    brief = {"shot": shot.get("visual_prompt") or " ".join(shot.get("beats", [])),
             "performers": shot.get("performers", []), "framing": shot.get("framing"),
             "wardrobe": shot.get("wardrobe"), "continuity": shot.get("continuity"),
             "look": resolve_look(project)["prompt"], **({"acting_asked_for": acting_ask} if acting_ask else {})}
    content.append({"type": "input_text", "text": "Shot contract: " + json.dumps(brief, ensure_ascii=False) + "\nFrames from the take:"})
    for t, f in _frames_at(take, need, 5 if acting_ask else 3):        # a performance needs more frames than a still life: the change over time is the point
        content.append({"type": "input_text", "text": f"Frame at {t:g} s of {round(need, 1):g} s:"})
        content.append({"type": "input_image", "image_url": f"data:image/jpeg;base64,{f}"})
    resp = client.responses.create(
        model=model,
        input=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}],
        text={"format": {"type": "json_schema", "name": "take_review", "schema": ISSUE_SCHEMA, "strict": True}},
    )
    out = json.loads(resp.output_text)
    for i in out.get("issues") or []:                       # a flagged hand or limb carries the standard correction, so Fix asks for exactly that
        if isinstance(i, dict) and i.get("kind") == "anatomy":
            i["fix"] = with_fix(i.get("fix", ""))
    out["model"] = model
    return out


def review_job(d: str, job: dict, project: dict, shot: dict) -> dict:
    take = os.path.join(d, job["output"])
    need = shot["end"] - shot["start"]
    issues = technical(take, need)
    result = {"technical": issues, "visual": None, "reviewed": True}
    if not any(i["severity"] == "major" for i in issues):
        try:
            result["visual"] = visual(d, project, shot, take, need)
        except Exception as e:  # review must never break rendering
            from .director import openai_error
            result["visual_error"] = openai_error(e)
    all_issues = issues + ((result["visual"] or {}).get("issues") or [])
    result["issues"] = all_issues
    result["status"] = ("needs_attention" if any(i["severity"] == "major" for i in all_issues)
                        else "minor" if all_issues else "unchecked" if result.get("visual_error") else "good")
    result["summary"] = (result["visual"] or {}).get("summary") or (
        all_issues[0]["detail"] if all_issues
        else f"Technical checks passed; not checked visually. {result['visual_error']}" if result.get("visual_error")
        else "Looks good.")
    result["fixes"] = [i["fix"] for i in all_issues if i.get("fix")]
    return result


if __name__ == "__main__":
    # manual check: python -m filmcrafter_engine.review <take.mp4> <seconds>
    print(json.dumps(technical(sys.argv[1], float(sys.argv[2])), indent=1))
