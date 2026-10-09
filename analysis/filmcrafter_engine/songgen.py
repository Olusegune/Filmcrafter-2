"""Make a song with ElevenLabs Music (optional: FilmCrafter works from songs you bring, and this is one way to get one).

Two ways to ask, both on ElevenLabs' music model with your own ElevenLabs key and plan:

  from lyrics   your lyrics, with their [Verse]/[Chorus] tags, become a composition plan: one section per tag, with its own lines,
                a length that fits the lines, and the style words you give. The song sings your words, section by section.
  describe it   a plain description (and, if you like, a length, or "no vocals").

The result is saved as an mp3 in ~/.filmcrafter/songs and offered to you to listen to; nothing is added to a project until you
choose to use it. ElevenLabs bills the music API to your plan in credits that FilmCrafter cannot see in advance, so there is no
price here, only the length it will ask for and a clear note; a refused request (an exhausted plan, a prompt it won't make) is
shown in ElevenLabs' own words. Nothing a user types is placed in a path or a command: text goes into a JSON request body and the
file name is made here.

  python -m filmcrafter_engine.songgen <plan|make> --data '{...}'
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid

SONGS_DIR = os.path.join(os.path.expanduser("~"), ".filmcrafter", "songs")
MODELS = [("music_v2_5", "Music v2.5 (newest)"), ("music_v2", "Music v2"), ("music_v1", "Music v1")]
MIN_SECTION_MS, MAX_SECTION_MS = 3000, 120_000
MAX_SONG_MS = 300_000            # the music model makes at most five minutes
MIN_PROMPT_MS, MAX_PROMPT_MS = 3000, 300_000
MAX_LINES = 30                   # lines in one section
MAX_LINE = 200
MAX_TAGS = 12
MAX_PROMPT = 2000
PER_LINE_MS = 3200
BED_MS = 2000
MAX_BYTES = 100_000_000


def emit(**kw) -> None:
    try:
        print(json.dumps(kw), flush=True)
    except (OSError, ValueError):
        pass


def tags(text: str | list | None) -> list[str]:
    """Style words: split on commas, semicolons and new lines; trimmed, short, no duplicates."""
    raw = text if isinstance(text, list) else str(text or "").replace(";", ",").replace("\n", ",").split(",")
    out: list[str] = []
    for t in raw:
        t = " ".join(str(t).split())[:80]
        if t and t.lower() not in (x.lower() for x in out):
            out.append(t)
    return out[:MAX_TAGS]


def _chunks(line: str) -> list[str]:
    """A lyric line longer than the model takes is cut at spaces into lines of at most 200 characters."""
    line = " ".join(line.split())
    out = []
    while len(line) > MAX_LINE:
        cut = line.rfind(" ", 0, MAX_LINE)
        cut = cut if cut > 40 else MAX_LINE
        out.append(line[:cut].strip())
        line = line[cut:].strip()
    return out + ([line] if line else [])


def build_plan(lyrics: str, style: str | list | None = None, avoid: str | list | None = None) -> dict:
    """A composition plan from tagged lyrics. Returns {"plan", "sections", "seconds", "warnings"}."""
    from .lyrics import parse_lyrics
    secs = parse_lyrics(lyrics or "")
    if not secs or not any(ln.text.strip() for s in secs for ln in s.lines):
        raise SystemExit("Add your lyrics first, with a tag such as [Verse 1] or [Chorus] above each part.")
    sections, warnings = [], []
    for s in secs:
        lines = [c for ln in s.lines for c in _chunks(ln.text)]
        name = " ".join(s.tag.split())[:100] or "Verse"
        parts = [lines[i:i + MAX_LINES] for i in range(0, len(lines), MAX_LINES)] or [[]]
        if len(parts) > 1:
            warnings.append(f"\"{name}\" has more than {MAX_LINES} lines, so it is made as {len(parts)} parts.")
        for k, part in enumerate(parts, 1):
            ms = BED_MS * 4 if not part else int(len(part) * PER_LINE_MS + BED_MS)
            sections.append({"section_name": name if k == 1 else f"{name} ({k})"[:100], "positive_local_styles": [], "negative_local_styles": [],
                             "duration_ms": min(MAX_SECTION_MS, max(MIN_SECTION_MS, ms)), "lines": part})
    total = sum(x["duration_ms"] for x in sections)
    if total > MAX_SONG_MS:
        raise SystemExit(f"These lyrics make about {total / 60000:.1f} minutes of music. The music model makes at most 5 minutes: shorten them, "
                         "or make the song in parts.")
    plan = {"positive_global_styles": tags(style), "negative_global_styles": tags(avoid), "sections": sections}
    return {"plan": plan, "sections": [{"name": x["section_name"], "lines": len(x["lines"]), "seconds": round(x["duration_ms"] / 1000)} for x in sections],
            "seconds": round(total / 1000), "warnings": warnings}


def make(mode: str, lyrics: str = "", style: str | list | None = None, avoid: str | list | None = None, prompt: str = "", seconds: float = 90,
         instrumental: bool = False, model: str = "music_v2_5") -> dict:
    """Ask ElevenLabs for the song and save it. Takes a minute or more; the reply is the mp3 itself."""
    import requests
    from . import voices as V
    if model not in {m for m, _ in MODELS}:
        model = MODELS[0][0]
    body: dict = {"model_id": model}
    if mode == "lyrics":
        info = build_plan(lyrics, style, avoid)
        body["composition_plan"] = info["plan"]
        length = info["seconds"]
    elif mode == "describe":
        text = " ".join(str(prompt).split())[:MAX_PROMPT]
        if not text and not tags(style):
            raise SystemExit("Describe the song you want: the style, the mood, what it is for.")
        if tags(style):
            text = (text + " Style: " + ", ".join(tags(style)) + ".").strip()
        body["prompt"] = text
        body["music_length_ms"] = int(min(MAX_PROMPT_MS, max(MIN_PROMPT_MS, float(seconds) * 1000)))
        body["force_instrumental"] = bool(instrumental)
        length = round(body["music_length_ms"] / 1000)
    else:
        raise SystemExit("Choose to make the song from your lyrics, or to describe it.")
    emit(event="progress", stage="ElevenLabs is composing the song (this takes a minute or two)", progress=0.1)
    r = None
    for attempt in range(2):
        r = requests.post(f"{V.ELEVEN}/v1/music", headers={**V._eleven_headers(), "Accept": "audio/mpeg"}, params={"output_format": "mp3_44100_128"},
                          json=body, timeout=600)
        if r.status_code != 429:       # busy means not started: safe to ask again once
            break
        time.sleep(5)
    if r.status_code in (401, 403):
        raise SystemExit("ElevenLabs refused the key, or your plan doesn't include the music API (it needs a paid plan). Check Settings and your ElevenLabs plan.")
    if r.status_code == 402 or (not r.ok and "quota" in V._eleven_error(r).lower()):
        raise SystemExit("Your ElevenLabs plan is out of credits: " + V._eleven_error(r))
    if not r.ok:
        raise SystemExit("ElevenLabs didn't make the song: " + V._eleven_error(r))
    if len(r.content) > MAX_BYTES or len(r.content) < 1000:
        raise SystemExit("ElevenLabs sent back something that isn't a song.")
    os.makedirs(SONGS_DIR, exist_ok=True)
    out = os.path.join(SONGS_DIR, f"song-{uuid.uuid4().hex[:8]}.mp3")
    with open(out + ".part", "wb") as f:
        f.write(r.content)
    try:
        secs = len(V._decode(out + ".part")) / V.RATE         # it must decode as audio before it is offered
    except SystemExit:
        os.remove(out + ".part")
        raise SystemExit("ElevenLabs sent back something that isn't a song.")
    os.replace(out + ".part", out)
    return {"path": out, "seconds": round(secs, 1), "asked_seconds": length, "model": model, "bytes": os.path.getsize(out)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="filmcrafter-songgen")
    ap.add_argument("action", choices=["plan", "make"])
    ap.add_argument("--data", default="{}")
    a = ap.parse_args(argv)
    x = json.loads(a.data)
    try:
        if a.action == "plan":
            res = build_plan(x.get("lyrics", ""), x.get("style"), x.get("avoid"))
            res = {k: v for k, v in res.items() if k != "plan"}
        else:
            res = make(x.get("mode", "lyrics"), x.get("lyrics", ""), x.get("style"), x.get("avoid"), x.get("prompt", ""), float(x.get("seconds", 90)),
                       bool(x.get("instrumental")), x.get("model", "music_v2_5"))
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
