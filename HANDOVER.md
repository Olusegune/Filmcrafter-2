# Handover: continuing FilmCrafter on another computer

Written 2026-10-12 at version **0.23.4**. Everything described here is in GitHub (`Olusegune/FilmCrafter`, branch `main`); the only things that are not are your **API keys**, your **film folders** and anything on your Desktop. Read this first, then **`docs/NEXT_PHASE.md` (the plan for what to do next and what was learned recently)**, `SETUP.md` (a fresh-clone walk-through), `README.md`, `docs/QA.md` (what has and has not been tested) and `CHANGELOG.md` (what each version did and why).

## 1. What this is

FilmCrafter is a Windows desktop app (Tauri 2 shell in Rust, React + TypeScript screens, a Python engine) that turns a screenplay or idea into a film: story, cast and world, shots, pictures, video, continuity checks, soundtrack and your own recorded voices, then an export or a hand-off to an editor. It began as PULSEFRAME (a separate, music-first app) and is developed independently. FilmCrafter opens **films only**; a PULSEFRAME project shows a message saying so.

Installed app: `%LOCALAPPDATA%\FilmCrafter\filmcrafter.exe`. Films live in `Documents\FilmCrafter\<title>\` (a folder with `film.json`).

## 2. Get it running on a new computer (about 30 minutes)

Follow `SETUP.md` (tools: Git, Node 22+, Rust stable + Visual Studio Build Tools, Python 3.11). The short version:

```
git clone https://github.com/Olusegune/FilmCrafter.git
cd FilmCrafter
npm ci
cd analysis ; py -3.11 -m venv .venv ; .venv\Scripts\python -m pip install -r requirements-engine.txt ; cd ..
npm run tauri dev        # the desktop app; or `npm run dev` for the screens only at http://localhost:1420
```

Then enter your API keys again in the app (**Settings**): they live in the Windows Credential Manager of the computer, never in the repository. Copy your film folders across (Documents\FilmCrafter\...).

## 3. The checks (run all of these before a release)

```
cd analysis ; python -X utf8 -m pytest -q            # engine: about 1,730 tests, about 5 minutes
npx tsc --noEmit ; npx vitest run                    # screens: about 475 tests
cargo test --manifest-path src-tauri/Cargo.toml      # shell: 7 tests
rafter secrets .                                     # no secrets in the repo (rafter run needs RAFTER_API_KEY and has not been run)
npm run dev                                          # then, in another terminal, the screen sweep:
PF_QA=1 PF_A11Y=1 PF_OVERFLOW=1 PF_WIDTH=1100 PF_OUT=/tmp/sweep node scripts/docshots-edge.mjs
python scripts/audit_film.py "<film folder>" [--kind video --model bytedance/seedance-2]
```

- `docshots-edge.mjs` opens every screen (46) in headless Edge: `PF_QA=1` fails on console errors, `PF_A11Y=1` runs axe-core (WCAG 2.1 A/AA), `PF_OVERFLOW=1 PF_WIDTH=1100` checks the layout at the app's minimum width, `PF_PERF=1` prints page size, `?n=300` makes the sample film 300 shots. With no `PF_OUT` it rewrites the screenshots in `docs/img/` (the guide's pictures: use `PF_OUT=docs/img/film` for the film ones).
- `audit_film.py` builds the prompt of every shot in a film (free, nothing is sent) and checks that the right people, pictures, props, setting and look reached each shot.

## 4. Releasing (what has been done every time)

1. Bump the version in four places: `package.json`, `package-lock.json` (lines 3 and 9), `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml` (line 3).
2. Add the entry to `CHANGELOG.md` and update `docs/QA.md` (title version, test counts, what was found and fixed, what was not tested).
3. `npm run tauri build` (about 3 minutes). Installers appear in `src-tauri/target/release/bundle/msi` and `.../nsis`.
4. Put them on the Desktop in `FilmCrafter X.Y.Z` with a source zip: `git archive --format=zip -o "FilmCrafter-source-X.Y.Z.zip" HEAD`.
5. `git add -A ; git commit ; git push` (commit messages end with the `Co-Authored-By` line the tooling asks for).
6. Install only when asked: stop `filmcrafter.exe`, run the NSIS setup with `/S`, start `%LOCALAPPDATA%\FilmCrafter\filmcrafter.exe`.

## 5. How the code is laid out

| Where | What |
|---|---|
| `src/*.tsx` | the screens. `App.tsx` (Home, film, studio), `Home.tsx`, `NewFilm.tsx`, `FilmView.tsx` and its stages (`CastWorld`, `ShotLab`, `MakeFilm`, `VoiceoverPanel`...), `Studio.tsx` (the timeline editor), `SelectReview.tsx`, `film.css` (most of the look) |
| `src/api.ts` | every call to the shell (`invoke("...")`) with its types |
| `src-tauri/src/lib.rs` | the shell: file dialogs, key storage, and one command per engine area. Each command has an `ACTIONS` list that **`analysis/tests/test_security.py` checks against the engine's argparse choices**: add an action in both places or the test fails |
| `analysis/filmcrafter_engine/` | the engine, one module per area: `story` (script reading, `ASPECTS`), `shots` (breakdown into shots, contracts), `bible` (cast, world, style), `make` (builds the render project from the film), `render` (provider requests, prompts, the queue), `library` (reference pictures), `export` and `interchange` (the film file and the editor hand-off), `voiceover` (your own recordings), `cast_voice` (ElevenLabs voices: library, design, clone, speak a line; never spends without `confirmed`), `blocking`, `looks`/`styles.json`, `animation_principles`, `styleguard`, `supervisor`, `continuity`... |
| `analysis/tests/` | about 126 test files |
| `scripts/` | the tools in section 3, plus Resolve and look-library helpers |
| `docs/` | `GETTING_STARTED.md` (the in-app guide, with screenshots in `docs/img/film/`), `QA.md`, `architecture/`, older phase notes |

**The film folder** (source of truth): `film.json` (title, aspect ratio, story), `script/versions`, `bible/bible.json`, `shots/<id>/contract.json`, `voice/` (your recordings, `voice.json`, `_removed/`), and `render/`, a derived render project that `make.sync` rewrites from the film each time (so never edit `render/` by hand; the frame shape, for example, is read from `film.json`).

## 6. Rules this project follows (keep them)

- Your story is kept exactly as given; suggestions never edit it. Chosen and locked work is never replaced, and **nothing the user made is deleted** (replaced things are archived, e.g. `shots/_removed`, `voice/_removed`).
- **Every paid generation shows its price first and waits for a yes.** Real provider runs need the user's explicit permission and a spend cap (they gave $5 earlier; about $0.96 was spent in the real Kie.ai test).
- Prompts name who speaks but never quote speech for pictures (models draw it as subtitles); looks are stated strongly; director names are never sent to a model, only their traits.
- A shot with no reference picture falls back to the text-to-image twin of an image-to-image model.
- Anything that reads or copies a file the user names is checked to stay inside the film (`voiceover.inside`, `safe.check_id`, `safe.file_name`). Security review (`rafter-code-review` skill, then `rafter secrets .`) is expected for changes touching file paths, uploads, subprocesses or dependencies.

## 7. Gotchas that cost time

- **Heredocs eat backslashes** (regexes and `\n` strings turn into backspaces or lose their `\`). Write files with an editor tool, then check the file.
- Windows console: use `python -X utf8`. Git warns about LF→CRLF: harmless.
- Background node sweeps get killed: run them in the foreground, in chunks.
- DaVinci Resolve scripting needs Preferences > System > General > External scripting = Local, and the Preferences window closed. Two test projects named "FilmCrafter hand-off check…" are still in the user's Resolve; **do not delete anything of theirs** (a project called "wEN" is theirs).
- API keys: `cast_voice` is tested with faked replies, and a small real run was made in 0.22 (library voice, five short lines, voice design; cloning and keeping a designed voice were not). Since Phase 0 every paid voice call needs `confirmed` at the engine, is written to `voice/ledger.json`, and an unclear outcome is never retried: see `docs/PAID_OPERATIONS.md`. The Kie.ai key was read from Credential Manager entry `kie.filmcrafter` only for the authorised real run. Never print, save or commit a key.

## 8. Where things stand

- **Version 0.25.3** (`main`, tag `v0.25.3`; the GitHub Release has the two installers and the source zip; the repository is private; the installers are not code-signed). Earlier tags: `v0.24.0` (Phase 0), `v0.25.0`, `v0.25.1`, `v0.25.2`. Rebuild with section 4.
- **Read these first:** `docs/PHASE_0_IMPLEMENTATION_REPORT.md` (safety and data protection), `docs/CREATIVE_PRODUCTION_EXPANSION.md` (Sound & Music, voice direction, audio cues and mixing, generation, "may be out of date", the model registry: what was verified, what was not), `docs/PAID_OPERATIONS.md` (the one set of rules for anything that spends), `docs/LIPSYNC_VALIDATION.md` (the real lip-sync run and what it showed), `docs/UI_REFINEMENT.md` (the shared control rules in `src/ui-system.css`), `docs/UPDATES.md` (why in-app updates are off and what they need), `docs/QA.md`.
- **Built since 0.21:** engine-level confirmation, a ledger and no-retry-when-unclear for paid voice calls; safe JSON records (`safeio.py`) in film.json, voice, cast, bible, shots, make, continuity, the audio library and cues; film-level backups with verified restore; a narrower media scope; the Sound & Music tab; spoken versions, another take, natural-delivery and voice suggestions, voice a scene, table read; audio cues and the sound director; sound-effect and music generation (ElevenLabs, Suno through Kie.ai); audio lanes and a mixer in the exporter (ducking, limiter, loudness target); takes that remember the voice they followed and a report of what may be out of date; the model registry (`~/.filmcrafter/registry.json`); pre-update snapshots.
- **Real runs so far (small, on throwaway films):** two sound effects and a two-line voice scene on ElevenLabs (39 credits reported), a lip-sync test on Kie (200 credits: reference audio alone did not follow the voice's timing, the Kie lip-sync pass improved it, not proven; nobody has judged the files by eye and ear yet). **Never run for real:** music generation (ElevenLabs Music, Suno through Kie), the cue lanes and the export mix on a real film in the installed app.
- **Lessons worth keeping:** a global CSS class name can break the whole app (`.sm` is the small-button size; a wrapper once reused it, and every small button became a column in 0.25.0 to 0.25.1: a test now forbids it); a provider can label real mp3 files `text/plain` (check the bytes, not the label); Kie can refuse a request for a reason its documentation does not give (Seedance reference audio needs a reference picture), and then charges nothing; ElevenLabs charged about half the help-centre rate for sound effects and far less than characters-times-multiplier for speech, so estimates stay labelled estimates.
- **Frame shape lesson (0.17.0):** the film's `film.json` is the source of truth for its shape and `render/` is rebuilt from it.
- **Not tested, be honest about these:** the installed app walked through end to end by a person; the Edit timeline's new sound lanes and the mixed export on a real film; music generation; real clone and keep-a-designed-voice; the microphone recorder; 125% and 150% Windows scaling across all screens; keyboard-only and screen-reader runs.

## 9. Next steps, in order

1. **The owner's walk-through of 0.25.3** (checklists in `docs/PHASE_0_IMPLEMENTATION_REPORT.md`, `docs/CREATIVE_PRODUCTION_EXPANSION.md` and `docs/UI_REFINEMENT.md`), and a person judging the lip-sync files from the test.
2. A better lip-sync retest (a line that fills the shot; about 100 Kie credits of the earlier cap were left, but a new go-ahead and cap are needed), and adapting the picture check's prompts for speech.
3. A first tiny music generation, only with the owner's go-ahead (unknown price and unestablished rights: see `docs/PAID_OPERATIONS.md`).
4. The 125%/150% scaling sweep of the Studio timeline, Board, Compose and Export screens; keyboard-only and screen-reader passes.
5. Updates: a public releases location, a code-signing certificate and an updater key (`docs/UPDATES.md`); then `tauri-plugin-updater`.
6. Safe records in the remaining record-keepers (the render `Store`, planio); a per-account calibration of cost estimates from the ledger.
7. Premiere Pro / Final Cut hand-off check, macOS build and signing (needs a Mac and certificates; see `docs/CODE_SIGNING.md`).

## 10. Working with the user

They like a calm, cinematic, premium look with consistent centred layouts and squarer (less rounded) boxes. They often ask "What's next on the list?" (answer with what needs them vs what you can do now), "Build, package to Desktop, push, and install X", and "Install FilmCrafter X and launch it". They welcome pushback and honest opinions, and they test the installed app and send screenshots, which has found real bugs more than once (a title read as a character, missing frame shapes, long picture names dropped). Answer them plainly, say what was and was not tested, and never claim something works that was not run.
