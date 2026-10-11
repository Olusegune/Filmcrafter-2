# FilmCrafter

Story-first AI filmmaking for Windows (macOS to be proven). Craft stories into cinema.

FilmCrafter is a sibling of PULSEFRAME (music-first AI directing). It started from PULSEFRAME 1.36.0 and is developed independently; see `docs/architecture/` for the baseline, the plan, the reuse map, the port ledger and the honest status of every goal.

## What it does

Screenplay or idea -> Production Bible, Cast and World -> shots with Shot Contracts -> pictures -> video -> continuity check -> soundtrack -> export or hand-off to an editor.
Your story is kept exactly as given; suggestions never edit it. Every generation shows its price and waits for a yes. Chosen and locked work is never replaced.

- **Look:** about 100 looks in six kinds of film (photorealistic, 3D, 2D, hybrid, hands-on crafts, art movements), a genre feel on top, the twelve principles of animation, and 48 filmmakers' visual approaches that work in any look. Where: Cast & World > Rules & style.
- **Frame shape:** 2.39:1, 21:9, 16:9, 4:3, 1:1, 4:5 or 9:16, chosen when the film is made and changeable later.
- **Blocking:** a top-down plan per shot, with the 180-degree line checked across a scene.
- **Quality:** a Production Supervisor shot by shot, a hands and faces check, a continuity check.
- **Hand-off:** EDL, OpenTimelineIO and Final Cut Pro XML (verified in DaVinci Resolve Studio), manifest, subtitles.

See `docs/GETTING_STARTED.md` (also the in-app guide, F1) for a walk through with pictures, `docs/QA.md` for what has been tested and what has not, and `docs/architecture/STATUS.md` for the honest state of each phase.

## Develop

```
npm ci
npm run tauri dev        # desktop app
npm run dev              # UI only, http://localhost:1420
python scripts/test_all.py
```

The film workflow's engine tests need only: `pytest requests pillow numpy soundfile imageio-ffmpeg pyyaml keyring pypdf fal-client openai`. The whole suite also wants `librosa` and, for the hand-off test, `opentimelineio` with `otio-cmx3600-adapter`.

Scripts (`scripts/`):

| Script | What it does |
|---|---|
| `test_all.py` | every kind of check in one table |
| `docshots-edge.mjs` | opens each of the 40 screens in headless Edge and photographs it; `PF_QA=1` also fails on any console error |
| `make_look_docs.py` | rewrites the look library in the guide from `styles.json` |
| `make_handoff_sample.py`, `resolve_check.py` | a sample hand-off with real clips, and an import check in a running DaVinci Resolve Studio |
| `live_test.py` | one real picture on a real provider (prices first; `--yes` to spend) |
