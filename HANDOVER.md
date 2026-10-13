# Handover: continuing FilmCrafter on another computer

Written 2026-10-12 at version **0.23.0**. Everything described here is in GitHub (`Olusegune/FilmCrafter`, branch `main`); the only things that are not are your **API keys**, your **film folders** and anything on your Desktop. Read this first, then **`docs/NEXT_PHASE.md` (the plan for what to do next and what was learned recently)**, `SETUP.md` (a fresh-clone walk-through), `README.md`, `docs/QA.md` (what has and has not been tested) and `CHANGELOG.md` (what each version did and why).

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
- API keys: an ElevenLabs key was **not** stored on the development computer, so `cast_voice` has only been tested with faked replies; do a real run (a short line, a small cap) before trusting it. The Kie.ai key was read from Credential Manager entry `kie.filmcrafter` only for the authorised real run. Never print, save or commit a key.

## 8. Where things stand

- **Version 0.21.1** (`main`, tag `before-music-removal` marks the code before the cleanup below). Installers are on the Desktop only (`FilmCrafter 0.21.1`); rebuild with section 4.
- **Built recently:** frame shapes (9), Select & review with enlarge preview and folding scenes, accessibility pass, export formats for every shape, the voiceover system (attach your own recordings by file name, one or two speakers per shot, drag and drop, lip-sync pass to your recording, export mix, hand-off files), props reach only the shots that show them, the film audit tool, and the removal of the music-video ways in.
- **Frame shape lesson (0.17.0):** the film's `film.json` is the source of truth for its shape and `render/` is rebuilt from it; any screen that changes the shape must also set it on the film (`frame.ts saveFrame` does). Summit Sprout was set to 21:9 on 2026-10-12 at the user's request (its existing 16:9 pictures should be re-made).
- **The Summit Sprout film** (`Documents\FilmCrafter\SUMMIT SPROUT FROM SHAME TO LIVING WATER Final Version 2`): repaired breakdown (58 shots, 8 scenes, all linked to the cast; `audit_film.py` reports 0 problems). A backup copy sits beside it, `... (before repair)`. The older `... Final Version` folder is stale. The film's frame shape is 16:9 in `film.json`; the user's screenshot once showed 21:9, so ask which they want (change it with the Frame shape panel or `film set_aspect`).
- **Not tested, be honest about these:** a real Seedance render with one of the user's recordings (needs their go-ahead and a spend cap; Seedance 2 takes up to 3 reference audio files and refuses a first frame together with reference audio, which is why the keyframe goes as a reference picture); Premiere Pro and Final Cut hand-off (only Resolve was verified); macOS; code signing; a human walk-through of the installed app; keyboard-only and screen-reader use.

## 9. Next steps, in order

1. The user decides the Summit Sprout frame shape (21:9 or 16:9).
2. The real voiceover test: one Seedance 2 shot (Kie.ai) with one recording; ask permission, get a cap, show the price. Check the mouth follows the voice and the export plays the recording.
3. **Engine cleanup: done in 0.18.0.** The music-video ways in went in 0.16.1; 0.18.0 removed the engine modules behind them (dance, choreography, producer packages, onboarding, shows, show script, show finish, voices, lyrics, song analysis) with their tests, in three batches with the full suite after each (engine 92 -> 81 modules). `python scripts/engine_reach.py` lists what the app can still reach (only `model_audit`, a developer tool, is left unreached). What is deliberately **kept**: the shared render pipeline (song map, plan, render project), native-dialogue code in `render` (the model speaks the lines; it has tests but no screen), and `from . import x as Y` helpers. If you want to go further, native dialogue is the next candidate: it touches `compile_request`, the price sheet and the Studio's estimate fields, so do it carefully.
4. The user's own walk-through of the installed app; a keyboard-only and screen-reader pass.
5. Premiere Pro / Final Cut hand-off check, macOS build and signing (needs a Mac and certificates; see `docs/CODE_SIGNING.md`).

## 10. Working with the user

They like a calm, cinematic, premium look with consistent centred layouts and squarer (less rounded) boxes. They often ask "What's next on the list?" (answer with what needs them vs what you can do now), "Build, package to Desktop, push, and install X", and "Install FilmCrafter X and launch it". They welcome pushback and honest opinions, and they test the installed app and send screenshots, which has found real bugs more than once (a title read as a character, missing frame shapes, long picture names dropped). Answer them plainly, say what was and was not tested, and never claim something works that was not run.
