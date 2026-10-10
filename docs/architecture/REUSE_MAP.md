# Reuse map (what happened to each PULSEFRAME module)

Status key: KEPT (works as is), GENERALIZE (kept, still has music-era assumptions to remove), REMOVED, ENTANGLED (music-only in purpose but wired into code FilmCrafter still needs; removed together with its replacement).

## Removed so far

| Commit group | Removed | Notes |
|---|---|---|
| 1. Song maker | `songgen.py`, `SongMaker.tsx`, the `songgen` Rust command and API, "Make a song" buttons on Home and in a show, `test_songgen.py` | ElevenLabs keys stay: voices and sound still use them. |
| 2. Choreography and lyric UI | `ChoreoSheet.tsx` (sheet, per-shot choreography panel, dance report), `LyricLayers.tsx`, their buttons and listeners, `dance.test.tsx` | The engine side of choreography is ENTANGLED (below). |

| 3. Story-first Home | Home's music hero, `LivingWave.tsx` (and its test), Create from song, New show and Producer package buttons | File > New now opens New film. The Wizard and Produce screens are reachable only through older projects until they are removed. |

## Added

`story.py` (+ `test_story.py`): films, script versions, story analysis, Story Lock. `NewFilm.tsx`, `FilmView.tsx`, `storyView.ts`, `film.css`. See `docs/GETTING_STARTED.md`.

## Corrections to the Phase 0 plan (found by reading the call sites)

- `track.py` (per-model results in a project) is **not** music-only: GENERALIZE (sung-shot lines to be dropped later).
- `packer.py` (single-file project package) is **GENERALIZE**: FilmCrafter needs a package format.
- `show.py`, `show_script.py`, `show_finish.py` (acts, scenes, spoken scenes, script import, finishing) are story-structured and likely valuable for narrative film: **GENERALIZE**, not removed.

## Still music-specific, not yet removed

| Module | Why it stays for now |
|---|---|
| `dance.py`, `choreo.py` and the dance/choreography fields in `performance.py`, `onboarding.py`, `directions_library.py`, `producer_plan.py`, `render.py`, `acting.py`; Rust `choreography` and `dance` commands | Used by prompt building and the Produce flow; removed together with the Produce flow. 30 test files mention them. |
| `producer_plan.py`, `producer_import.py`, `concepts.py`, `Produce.tsx`, `ProducePictures.tsx`, `ProducerImport.tsx` (create from a song) | Replaced by the story-first creation flow (Phase 1). |
| `analyze.py`, `lyrics.py`, song map, `Analysis.tsx`, the waveform and lyric lane in the timeline, `LivingWave.tsx` ("Drop a song here" hero) | The timeline and Home are rewritten for scenes and shots, not removed piecemeal. |
| `Wizard.tsx` | Rewritten story-first. |

Rule: a module is removed only in a commit that keeps `tsc`, vitest, cargo test and the engine regression and security groups green.
