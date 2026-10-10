# FilmCrafter

Story-first AI filmmaking for Windows (macOS to be proven). Craft stories into cinema.

FilmCrafter is a sibling of PULSEFRAME (music-first AI directing). It started from PULSEFRAME 1.36.0 and is developed independently; see `docs/architecture/` for the baseline, the plan, the reuse map, the port ledger and the honest status of every goal.

## What it does

Screenplay or idea -> Production Bible, Cast and World -> shots with Shot Contracts -> storyboard -> hero keyframes -> video -> continuity check -> soundtrack -> export or hand-off to an editor.
Your story is kept exactly as given; suggestions never edit it. Every generation shows its price and waits for a yes. Chosen and locked work is never replaced.

See `docs/GETTING_STARTED.md` (also the in-app guide, F1) for a walk through with pictures.

## Develop

```
npm ci
npm run tauri dev        # desktop app
npm run dev              # UI only, http://localhost:1420
python scripts/test_all.py
```

The film workflow's engine tests need only: `pytest requests pillow numpy soundfile imageio-ffmpeg pyyaml keyring pypdf fal-client openai`.
