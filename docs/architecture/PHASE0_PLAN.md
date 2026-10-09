# FilmCrafter: audit, strategy and plan (Phase 0 deliverables)

Status: proposal for approval. Nothing in either repository has been changed.
Prepared against the local PULSEFRAME 1.36.0 source (`C:\Users\eduni\Pulseframe-Music-Video-Maker-main`).

---

## 0. Critical finding: the 1.36.0 source is not in GitHub

| Where | State |
|---|---|
| Local folder | PULSEFRAME **1.36.0** (package.json, tauri.conf.json, Cargo.toml, Cargo.lock, CHANGELOG all say 1.36.0). **Not a git repository** (no `.git`). |
| `Olusegune/Pulseframe-Music-Video-Maker` `main` | `f5164a2` (2026-10-08), version **1.26.0**. Ten releases (1.27.0 to 1.36.0) exist only in the local folder. Branches: `main`, `feature/acting-depth`, `feature/audit-shortcuts-sound-lane`, `feature/ui-polish`. 38 tag refs (v1.7.0 … plus `backup-2026-09-28`, `latest-2026-09-28-*`). |
| `Olusegune/FilmCrafter` | Exists, readable, **empty** (no refs). |
| Access | `gh` is not logged in, but `git` over HTTPS works through the Windows credential manager (read confirmed; push not tried). |

So the requested baseline tag `pulseframe-v1.36.0-filmcrafter-baseline` cannot be created today: there is no commit that represents 1.36.0. Seeding FilmCrafter from GitHub `main` would have started from 1.26.0, exactly the stale snapshot you ruled out.

---

## 1. Backup report (proposed, not yet executed)

Goal: one immutable, pushed commit that is exactly 1.36.0, with the old `main` preserved.

Procedure (needs your OK, because it pushes to your repository):

1. Tag the current GitHub `main` first, so the 1.26.0 state is never lost: `backup-main-1.26.0-2026-10-08` at `f5164a2`.
2. Clone `main` into a scratch folder (not the working folder).
3. Replace its tree with the local 1.36.0 tree, excluding `analysis/.venv`, `node_modules`, `src-tauri/target`, `dist`, `__pycache__`, `.pytest_cache`, installers. Keep `.gitignore` aligned with that list.
4. Check that the resulting tree contains no secrets (`rafter secrets` over the clean tree, not the venv; the last scan's only non-venv hits were two compiled `.rlib` files under `target/`, which are excluded).
5. Verify: `package.json` / `tauri.conf.json` / `Cargo.toml` / `Cargo.lock` all 1.36.0; `CHANGELOG.md` top entry 1.36.0; `npm ci && tsc && vitest`; engine pytest groups with a fresh venv; `tauri build` produces the 1.36.0 installers (the pair on your Desktop, `PULSEFRAME_1.36.0_x64-setup.exe` and `.msi`, are the reference artifacts).
6. Commit on top of `main` (no history rewrite; message: "1.36.0 snapshot, source of record"), push `main`, then create and push the **annotated tag** `pulseframe-v1.36.0-filmcrafter-baseline` and a branch `baseline/pulseframe-1.36.0`.
7. Record the new SHA in `FilmCrafter/docs/architecture/BASELINE.md`.

Trade-off: versions 1.27 to 1.35 will appear as one commit (their detail lives in `CHANGELOG.md`). Per-version history can't be reconstructed because it was never committed. From here on, PULSEFRAME should be committed per release.

Also recommended: add a GitHub release for 1.36.0 with the two installers attached, so the artifacts and the source tag point at each other.

---

## 2. Repository strategy

Options evaluated:

- **A. GitHub fork.** Rejected. GitHub doesn't allow forking your own repo into the same account, a fork keeps one shared history and a standing temptation to merge music-specific changes, and "pulling upstream" would constantly collide with a product that is deliberately different.
- **B. Derived sibling repository.** Recommended start. FilmCrafter begins from the tagged 1.36.0 tree as a first commit in its own history, then diverges.
- **C. Shared core now.** Rejected for now. It forces a large refactor of a working 25k-line engine and a 2.3k-line `lib.rs` before FilmCrafter has proved which parts are really common.
- **D. Hybrid (recommended end state): B now, C by incremental extraction.**

Recommendation: **B, evolving to C**.

- Seed FilmCrafter with `git archive` of the baseline tag into the empty repo (a fresh root commit whose message names the baseline SHA). No shared git history means it is physically impossible to push FilmCrafter work to PULSEFRAME by accident.
- Keep a **port ledger** (`docs/architecture/PORT_LEDGER.md`): every PULSEFRAME fix worth carrying over is logged with its commit and ported deliberately (cherry-pick-by-hand, since histories differ).
- Extract to a shared package (**FrameCore**) only when a module has been stable in both products for a release cycle and its public surface is small. Likely first extractions: provider router and model registry, job persistence, credential storage, ComfyUI integration, design tokens. Mechanism then: a third repo (`Olusegune/FrameCore`) consumed as a pinned dependency (Python package + npm package), not a git submodule tangle.
- Both products keep separate identifiers, bundle IDs, file extensions, keyring service names and data folders so they can be installed side by side.

---

## 3. PULSEFRAME reuse audit

### 3.1 Architecture overview (verified from the source)

- **Shell**: Tauri 2 (`src-tauri/src/lib.rs`, 2,297 lines, one file). Spawns the Python engine as a child process per call, brokers an action whitelist (`ACTIONS`), stores provider keys in the OS keychain (`keyring` crate with `windows-native` and `apple-native`), single-instance plugin, asset protocol scoped to `$DOCUMENT` and `$HOME`, strict CSP, splash window, file associations (`.pulseframe`, `.pulse`, `.pfproducer`).
- **UI**: React 19 + TypeScript + Vite, about 15.5k lines in `src/` (largest: `Studio.tsx` 1,249, `Wizard.tsx` 967, `Produce.tsx` 500, `Board.tsx` 475, `api.ts` 441). Styling is plain CSS with tokens (`styles.css`, `polish.css`, `corners.css`, `focus.css`, others). No state library; screens call `api.*` which invokes Tauri commands.
- **Engine**: Python 3.11, about 25.8k lines in `analysis/pulseframe_analysis` (largest: `render.py` 3,063; `producer_plan.py` 999; `overlays.py` 916; `show.py` 826; `library.py` 658; `compose.py` 629). Project state is files in the project folder (JSON per concern, takes as media files, undo journals).
- **Tests**: 1,279 pytest functions in six groups (unit, regression, security, acceptance, integration, e2e), about 400 vitest tests, cargo test, plus scans (rafter secrets, bandit, pip-audit, npm audit) via `scripts/test_all.py`. A security test enforces that every Rust-whitelisted action exists in the engine.
- **Docs and harness**: `docs/GETTING_STARTED.md`, `docs/TESTING.md`, a headless screenshot harness (`docshots.html`, `src/docshots`, `scripts/docshots-edge.mjs`).

### 3.2 Classification (by module; names and sizes verified, behaviour spot-checked; each module gets a line-by-line check in Phase 0 before it moves)

**REUSE DIRECTLY**
`safe.py`, `planio.py`, `fonts.py`, `hardware.py` (GPU/hardware detection), `diagnostics.py`, `updates.py`, `comfy.py`, `comfy_install.py`, `comfy_setup.py`, `localmodels.py`, `llm.py` (cloud and local LLM), `media.py`, `budget.py`, `shothistory.py` (undo journal), `retrycheap.py`, `upscale.py`, `cleanup.py`, `colormatch.py`, `anatomy.py`, `handfix.py`, `keyframeset.py`, `stills.py`, `overlays.py` + `layerkit.py` + `svg_text.py` + `shapes.py` + `shape_icons.py` + `titlecard.py` + `captions.py` (on-screen layers), `transitions.py`, `crash`/diagnostics, `command.py` (Ctrl+K), `changes.py`, `proof.py`, `model_audit.py`, `modelinfo.py`, `modelblurbs.py` (data refreshed), `styleguard.py`.
UI: `Dock`, `Command`, `Help`, `Settings`, `Cleanup`, `Compare`, `Takes`, `RenderQueue`, `Review`/`SelectReview`/`reviewSwap`, `HandFix`, `KeyframeTools`, `Layers`/`LayerLanes`/`laneMath`, `ModelChoice`, `ModelPicker`, `Routing`, `ColourMatch`, `UpscaleSheet`, `Export`, design CSS tokens, docshots harness.

**REUSE WITH GENERALIZATION**
- `router.py` + `routing.py`: today a family table (`seedance`, `kling`, `veo`, `hailuo`, `wan`, `ltx`, image models) mapping to fal/kie/google ids. Becomes the capability-driven model registry the brief asks for (capabilities per model: first/last frame, references, audio, duration, aspect, seed), with names as data, not code.
- `library.py` + `refgen.py` + `Board.tsx` library: reference library becomes the Cast & World asset system with character states (age/wardrobe/injury) and environment spatial data.
- `continuity.py` (409 lines): music-video continuity checks; becomes the narrative Continuity Director (identity, wardrobe, props, screen direction, eyelines, emotional progression).
- `acting.py` + `performance.py` + `ActingDepth.tsx` + `Performance.tsx`: the beats/arc/gesture ideas are the right seed for the Performance Director, but they are profile-driven (Natural/Dramatic/…); FilmCrafter needs motivation-driven beats (want/need/fear/hiding/subtext).
- `lighting.py`, `camera.py`, `director.py` + `director_audit.py`, `promptwriter.py`, `frames.py`, `compose.py`, `extend.py`, `lipsync_check.py`, `voices.py`, `shotsound.py`: carry the mechanics; the song-timed assumptions (lyric cues, sections, beats) must be replaced by script/scene timing.
- `script_import.py` + `show_script.py`: script reading exists; screenplay parsing (sluglines, dialogue, action, versions, story lock) must be built properly.
- `export.py` + `editor_export.py`: Premiere/Resolve hand-off exists; add OTIO, FCPXML, EDL, image sequences, stems, shot manifest.
- `directions_library.py` + `looks.py` + `concepts.py`: become the Style Profile library (photoreal, stylized 3D, 2D, anime-inspired, stop-motion, etc.) affecting characters, environments, materials, lighting, camera and movement, not a prompt suffix.
- `golden.py`, `overnight.py`, `render.py`: render orchestration and job persistence are valuable, but `render.py` (3,063 lines) is a monolith that must be read and split before reuse.
- UI: `Studio.tsx` (shell, panes, timeline), `Board.tsx` (cards become storyboard wall), `Frames.tsx`, `Keyframe.tsx`, `Render.tsx`, `Produce.tsx`, `Home.tsx`.

**PULSEFRAME ONLY (do not carry)**
`analyze.py` (beat/section/lyric analysis), `track.py`, `lyrics.py`, `songgen.py`, `dance.py`, `choreo.py`, `packer.py` and the pieces of `render.py` that are cut-to-beat; `Analysis.tsx`, `SongMaker.tsx`, `ChoreoSheet.tsx`, `LyricLayers.tsx`, `LivingWave.tsx`, `ShowView.tsx`/`ShowExtras.tsx` if they are the performance "show" view (verify), the Wizard's song-first steps (`Wizard.tsx` 967 lines is rewritten for story-first), `producer_plan.py` / `producer_import.py` / `ProducerImport.tsx` and `.pfproducer` (the Producer plugin; verify its scope before deciding), `Autopilot.tsx` (verify), `MUSICAL_MODE_PLAN.md`/`CREATE_FROM_SONG_PLAN.md` docs.

**EXTRACT TO FRAMECORE LATER** (only after both products are stable)
Provider/model registry and router, job persistence and recovery, keyring credential layer, ComfyUI integration and installer, cost/budget controls, media probing/thumbnails, project backup/undo journal, export/interchange writers, design tokens and base components, local-AI detection.

### 3.3 Technical debt and risks

1. **Monoliths**: `render.py` (3k), `lib.rs` (2.3k), `Studio.tsx` (1.2k), `Wizard.tsx` (967). Reusing them means inheriting them; split before building on them.
2. **Windows-first bootstrap**: engine environment setup uses the embeddable Python zip plus `curl.exe` and `tar.exe` (`lib.rs` ~line 333). macOS needs a separate path (python-build-standalone or a bundled interpreter).
3. **No signed releases yet**: the NSIS installer is "left unsigned (no signing certificate configured)"; `scripts/sign.ps1` is a placeholder. macOS needs a Developer ID certificate, hardened runtime and notarization.
4. **No in-app updater**: `updates.py` checks for a new version; there is no `tauri-plugin-updater` with signed manifests.
5. **Per-call engine process**: fine for the current action model, but long jobs rely on files for state. A long-lived engine service would help local inference and progress streaming; evaluate in the ADR.
6. **Secrets-scan noise**: the venv and `target/` trigger false positives; scoped scanning must be set up for the new repo.
7. **No git history for 1.27 to 1.36** (section 0).
8. **Provider model ids are hard-coded** in `router.py`; they churn quickly. A data-driven registry (JSON or fetched, with a signature) is needed.

---

## 4. Architecture Decision Record

**ADR-001 Keep Tauri 2.** Small installers, native WebView, Rust boundary that already enforces an action whitelist, OS keychain support on both platforms, file associations, a strict CSP. Costs: WebView2 vs WKWebView rendering and codec differences (test `<video>` formats on macOS: prefer H.264/AAC proxies), and no Node runtime. Electron would add ~100 MB and a larger attack surface without solving the Python question. Decision: keep.

**ADR-002 Keep React + TypeScript + Vite**, and add a small state layer (Zustand or equivalent) for the Shot Lab and timeline instead of passing props through a 1,200-line `Studio.tsx`. Component library split into `ui/` (tokens, primitives) and `features/`.

**ADR-003 Python engine stays, but becomes a package with a stable service boundary.** Keep the per-call JSON action protocol for Phase 1 (proved, tested, whitelisted). Plan a persistent "engine daemon" (local socket, JSON-RPC) in Phase 3 for streaming progress and long local inference. Python pinned to 3.11 and bundled as a standalone distribution on both OSes, with the pinned `requirements-engine.txt` installed at first run (Windows) or shipped in the app (macOS, universal2/arm64 wheels).

**ADR-004 Media pipeline.** FFmpeg through `imageio_ffmpeg` today. Decision: bundle a pinned FFmpeg per platform and architecture (Windows x64; macOS arm64 and x64) with a recorded licence note, and generate H.264/AAC proxies for the viewer. Keep ProRes/DNxHR for export hand-off where the FFmpeg build supports it. Verify arm64 wheels for every engine dependency (`librosa`, `demucs`, `faster-whisper`, `pypdf`, `PIL`) in Phase 0; drop what FilmCrafter doesn't need (audio analysis).

**ADR-005 Local AI.** Detect and manage Ollama / LM Studio (OpenAI-compatible HTTP) for reasoning, ComfyUI for image/video, as PULSEFRAME does; hardware detection per OS (NVIDIA/CUDA on Windows, Metal/MPS on Apple Silicon). Local mode is a routing strategy, not a separate app. Apple Silicon: ComfyUI with MPS is possible but slower and model-dependent; the UI must say so before offering local video.

**ADR-006 Provider architecture.** Capability-driven registry (data file + adapter per provider API, not per model). Each model entry declares inputs (first/last frame, N references, video/audio reference, text prompt), outputs (duration range, resolutions, aspect ratios, audio), controls (seed, camera), price model, and "proven" status; the UI shows only supported controls. Adapters: OpenAI, Google (Gemini image, Veo), fal.ai, Kie.ai, ElevenLabs, Suno-compatible, OpenRouter, ComfyUI, Ollama/LM Studio.

**ADR-007 Storage.** Project = a folder (human-inspectable JSON per entity plus media), as in PULSEFRAME, with a `film.json` manifest and schema version, atomic writes (write-temp-then-rename), rolling automatic backups, and an append-only job journal. Optional single-file package (`.filmcrafter`, zip) for sharing. No database in Phase 1; revisit a local SQLite index only if project sizes require it.

**ADR-008 Background jobs.** Persistent job records (queued/submitted/ready/failed/uncertain) that survive a crash and are re-polled on reopen, which is already how PULSEFRAME treats provider jobs; cost estimate and confirmation before any billable job; budget caps.

**ADR-009 Credentials.** OS keychain only (Windows Credential Manager, macOS Keychain) through the existing `keyring` layer; never in project files or logs.

**ADR-010 Packaging and release.**
- Windows: NSIS + MSI, Authenticode signing (certificate required), WebView2 bootstrapper.
- macOS: universal or per-arch `.dmg`, Developer ID signing, hardened runtime, notarization with `notarytool`, entitlements for network, file access and (if needed) JIT-less Python.
- Updates: `tauri-plugin-updater` with signed manifests and a staged channel.
- CI: GitHub Actions matrix (windows-latest, macos-14 arm64, macos-13 x64) running the same `test_all` gate, producing unsigned artifacts per PR and signed ones on tags.
- Crash recovery: reuse crash-report capture and the job journal; autosave on every state change; "recovered session" prompt.

**ADR-011 Identifiers and side-by-side install.** Bundle id `com.filmcrafter.app`, keyring service `filmcrafter`, app-data folder `FilmCrafter`, extensions `.filmcrafter` / `.fcpack`; different icon and accent so the two apps are distinguishable in the taskbar.

**ADR-012 Branding assets.** Three images supplied (file-shaped app icon, film-strip "F" mark, and the launch banner "FilmCrafter, Craft stories into cinema."). Plan: store originals under `brand/`, derive `icon.ico`/`icon.icns`/PNG sizes and the splash from them, and check that the name "FilmCrafter" is clear of existing trademarks before public release (not verifiable from here).

---

## 5. FilmCrafter PR (engineering and product requirements, concise)

Story-first AI filmmaking desktop app (Windows and macOS). The durable value is the filmmaking intelligence (script understanding, production bible, performance, shot contracts, continuity, QA); models are replaceable rendering engines selected by capability.

Must:
1. Import or write a script; analyze without rewriting; **Use story as-is** always available; **Story Lock** versions the script; revisions create new versions.
2. Production Bible as the single source of truth (characters with states, sets with spatial data, props, style profile, philosophy notes).
3. Scene breakdown, then director-quality shot design into a renderer-independent **Shot Contract**.
4. Storyboard wall (approve/edit/regenerate/duplicate/reorder/split/merge/delete/add, import existing), **Storyboard Lock**.
5. Hero keyframe workflow with **Keyframe Lock** recording image, references, prompt, provider, model, seed.
6. Video generation or import by capability; no controls a model can't honor; versions never destroyed.
7. Shot Lab: viewer, references, contract, acting, camera, lighting, continuity, generation, versions, QA, side-by-side.
8. Continuity Director and advisory QA ("may have changed", never "is wrong").
9. Integrated assembly timeline and basic sound; hand-off exports; Simple Mode and Studio Mode on the same project.
10. Cost estimates and confirmation before billable work; local-first strategy; Ctrl/Cmd+K Director Command; crash-safe save/close/reopen.
11. Windows and macOS builds from the same codebase and the same test gate.

Won't (Phase 1): VFX compositor, DAW, 3D suite, node editor, collaboration, marketplace, mocap.

---

## 6. FilmCrafter PRD (summary of behaviour; detail grows per phase)

**Modes.** *Simple*: Story, Cast & World, Storyboard, Make Film, Review, Export. *Studio*: Script, Breakdown, Cast, World, Wardrobe, Props, Performance, Blocking, Storyboard, Shot Lab, Camera, Lighting, Generate, Edit, Sound, Continuity, Review, Deliver. Same project; Studio only reveals more.

**Story.** Sources: screenplay, logline, idea, synopsis, treatment, outline, storyboard. Development ladder logline, synopsis, treatment, beat sheet, scene outline, screenplay, with a review gate between steps. Recommendations (structure, pacing, motivation, exposition, visual storytelling, emotional turns, setup/payoff, production complexity) are suggestions with accept/reject per item; the original is preserved byte for byte.

**Cast & World.** Characters with a master reference, views (front, 3/4, side, back), expressions, pose sheets, wardrobe, accessories, age/hair/injury/story states (SARAH 8, 28, 70 are states of one character). Environments with entrances, exits, doors, windows, landmarks, furniture, blocking areas, camera zones, lighting, day/night. User-supplied art is always first-class.

**Style Profile.** A structured profile (characters, environments, materials, textures, lighting, animation, cinematography, movement, compositing, editing) across the listed lanes; recognisable studios or films are translated into high-level visual traits, never copied.

**Performance Director.** For key scenes produce acting beats from want, need, fear, hiding, subtext, start state, turn and end state; translate into visible behaviour (gaze, blinks, breathing, tension, posture, hands, weight, pauses, restraint). Micro-animation is derived from intention, never generic idle loops.

**Camera and Lighting.** Choices carry a stated dramatic reason; lighting reasons from "what should the audience feel" before choosing a setup.

**Generation.** Hero keyframe first; video only from approved contract plus keyframe; routing strategies Local First, Cheapest, Balanced, Premium, Custom with realistic estimates and a confirmation gate.

**Review and QA.** Continuity and QA findings carry severity, evidence (frames), and a suggested fix; the director dismisses or accepts.

**Edit, Sound, Deliver.** Basic timeline (assemble, trim, order, audio tracks); imported/generated dialogue, ADR, ambience, music; export film + OTIO, FCPXML, EDL, image sequences, stems, subtitles, shot manifest; Premiere and Resolve hand-off.

**Director Command.** Ctrl/Cmd+K, contextual to the current selection, returns a proposed change set the user approves; never a permanent chat panel.

**UI.** Left navigation, centre viewer, right contextual inspector, bottom storyboard/timeline; palette Obsidian, Graphite, deep navy, Frost, Silver, Signal Blue, Cinema Amber; restrained glow; film content dominates. Inherits PULSEFRAME's rules: say things once, serious findings first with detail behind a disclosure, one primary action per card, one scroll per sheet.

---

## 7. Phase 1 data model

Project folder:

```
MyFilm.filmcrafter/            (folder; or zipped .filmcrafter package)
  film.json                    manifest: id, title, schemaVersion, created, modes, strategy, budget
  script/
    versions/v001.fountain.json, v002...   ScriptVersion (text, source, hash, parent, locked: bool)
    analysis/v001.json         structure notes + recommendations + accept/reject state
  bible/bible.json             ProductionBible (rules, philosophy, style profile ref)
  cast/<characterId>/character.json    Character + CharacterState[] + media refs
  world/<environmentId>/environment.json   Environment + EnvironmentState[] + spatial map
  props/<propId>.json          Prop + PropState[]
  scenes/<sceneId>.json        Scene (ScriptVersion ref, slugline, purpose, emotion, continuity)
  shots/<shotId>/
    contract.json              ShotContract (see below)
    storyboard/                Storyboard panel versions + lock
    keyframes/                 Keyframe versions + lock (provenance)
    renders/                   RenderVersion files + records
  jobs/journal.jsonl           GenerationJob append-only log
  continuity/state.json        ContinuityState per shot boundary + QAFinding[]
  audio/                       AudioAsset
  timeline/timeline.json       TimelineClip[]
  backups/                     rolling automatic copies
```

Entities and relations (Phase 1):

- **Project** 1..n **ScriptVersion** (one may be locked; every Scene/Shot stores the ScriptVersion id it was derived from).
- **Project** 1..n **Sequence** 1..n **Scene** 1..n **Shot** 1..n **Take (RenderVersion)**.
- **Character** 1..n **CharacterState** (age, wardrobe, hair, injury, story state); a Shot references characters by state id.
- **Environment** 1..n **EnvironmentState** (time of day, dressing); **Prop** 1..n **PropState**.
- **ShotContract** (1:1 with Shot): shot id, scene id, story purpose, characters with state ids, wardrobe, environment state, prop states, blocking, action, dialogue, performance (PerformanceBeat[]), emotional intention, micro-animation, camera plan (framing, angle, position, lens intent, movement, focus), lighting plan, opening/closing state, continuity requirements, reference assets, sound requirements, generation requirements, plus `contractVersion` and `lockedAt`.
- **Storyboard** (versions per shot, `locked`), **Keyframe** (versions per shot; provenance: image, references, prompt, provider, model, seed, `locked`), **RenderVersion** (provider, model, params, cost, file, status, approved flag; never deleted automatically).
- **GenerationJob** (kind, target ids, provider config id, estimate, state, timestamps).
- **ContinuityState** (per shot boundary: positions, props held, costume/dirt/injury, time, lighting) and **QAFinding** (shot, category, severity, evidence frames, suggestion, status).
- **PerformanceBeat**, **CameraPlan**, **LightingPlan**, **AudioAsset**, **TimelineClip**, **ProviderConfiguration** (non-secret settings; keys live in the keychain).

Reuse mapping: PULSEFRAME's shot, take/version, job, library item, keyframe-set and undo records map to Shot, RenderVersion, GenerationJob, Asset and Keyframe; song/section/lyric records and choreography have no equivalent and are not carried.

---

## 8. Repository and module plan

```
FilmCrafter/
  README.md  LICENSE.txt  CHANGELOG.md  AGENTS.md
  brand/                         icon, mark, banner originals
  docs/ architecture/ (BASELINE.md, ADRs, PORT_LEDGER.md, REUSE_MAP.md)  product/ (PR.md, PRD.md)  img/
  src/                           React + TS
    app/        shell, routing, modes (Simple/Studio), command palette
    ui/         tokens, primitives, layout (from PULSEFRAME design CSS)
    features/   story/ bible/ cast/ world/ breakdown/ performance/ storyboard/ shotlab/ generate/ review/ timeline/ sound/ deliver/ settings/
    state/      stores, api client
    docshots/   screenshot harness
  src-tauri/                     Rust shell split into modules: commands/, jobs/, keys/, engine/, fs/, updater/
  engine/                        Python package `filmcrafter_engine`
    core/       (safe, planio, media, budget, hardware, diagnostics)         <- future FrameCore
    providers/  registry.json + adapters/ (openai, google, fal, kie, elevenlabs, comfy, ollama, lmstudio)
    jobs/       persistence, polling, recovery, estimates
    story/      script_import, screenplay parser, analysis, versions, lock
    bible/      production bible, style profiles
    cast/ world/  characters, states, environments, spatial
    direct/     breakdown, shot contracts, performance, camera, lighting, blocking
    boards/     storyboard + keyframe generation and locks
    video/      generation, extend, lipsync, versions
    continuity/ qa/
    edit/ sound/ export/ (premiere, resolve, otio, fcpxml, edl, sequences)
    tests/      unit regression security acceptance integration e2e
  scripts/      test_all.py, docshots, build and signing scripts
  .github/workflows/ ci.yml (win + mac matrix), release.yml
```

---

## 9. Migration / seed plan

1. Complete section 1 (baseline commit, tag, branch, release) and obtain the tag SHA.
2. In a scratch folder: `git archive pulseframe-v1.36.0-filmcrafter-baseline | tar -x` into a fresh directory, **not** a clone, so there is no remote or history link to PULSEFRAME.
3. `git init`, remote `FilmCrafter` only, first commit "Seed from PULSEFRAME 1.36.0 (baseline <SHA>)". Push only after a human check that `git remote -v` shows FilmCrafter.
4. Second commit: rename identifiers (productName, bundle id, keyring service, extensions, window titles, CSS brand), remove PULSEFRAME-only modules from section 3.2 behind a checklist, one commit per removal group so each is revertable, tests pruned and passing at each step.
5. Add `docs/architecture/REUSE_MAP.md` listing every module as REUSE / GENERALIZE / REMOVED / LATER-EXTRACT with the commit that did it.
6. CI first: Windows + macOS build/test matrix green before any new feature work.
7. PULSEFRAME stays untouched: its own working copy, its own repo, builds from its own tags.

---

## 10. Phased development plan

**Phase 0: architecture and safe reuse (about 1 to 2 weeks).** Baseline commit/tag/release; seed FilmCrafter; rename and prune; module-by-module audit of the "verify" items; macOS toolchain proof (Tauri build on Apple Silicon, Python and FFmpeg bundled, keychain, a `<video>` playback check); CI matrix; ADRs ratified. Exit: both OS builds launch an empty FilmCrafter shell with provider keys and the engine handshake working.

**Phase 1: Golden Path.** Import short script, analyze, use as-is or approve revisions, Story Lock, Production Bible, create/import characters and one or more sets, break one scene into shots, acting/camera/lighting on the contract, storyboard generate and lock, keyframe generate and lock, generate/import video, review versions, assemble, basic sound, save, close, reopen, continue, export. Target: one polished 1 to 3 minute scene. Acceptance: scripted end-to-end test with a mock provider (no spend), plus a manual run with one real provider, on both OSes; save/close/reopen test after every stage.

**Phase 2: continuity and performance.** Narrative Continuity Director; Performance Director with motivation-driven beats and micro-animation; blocking data and diagrams; advisory QA expansion; Shot Lab side-by-side.

**Phase 3: broader providers and local models.** Capability registry fully data-driven; more adapters; Ollama/LM Studio reasoning and ComfyUI workflows productised; engine daemon with streamed progress; Apple Silicon local paths.

**Phase 4: professional interchange.** OTIO, FCPXML, EDL, AAF-ready where practical, image sequences, stems, subtitles, shot manifests; Premiere/Resolve/After Effects hand-off tested with real projects.

**Phase 5: advanced studio workflows.** Deeper sound (ADR, Foley), richer timeline, style-profile authoring, extraction of **FrameCore** shared packages, collaboration groundwork only if justified.

Working rule at every phase gate: audit, build the minimum, test, save/close/reopen test, Windows build test, macOS build test, then next phase. PULSEFRAME is preserved throughout.

---

## Decisions needed from you

1. **Baseline procedure (section 1):** may I commit the local 1.36.0 tree on top of GitHub `main`, tag the old `main` as a backup, and push `pulseframe-v1.36.0-filmcrafter-baseline`? (This writes to your PULSEFRAME repository; I will not do it without your yes.)
2. **Repository strategy:** approve B-evolving-to-C (derived sibling, FrameCore later).
3. **Apple side:** do you have an Apple Developer account and a Mac (or are CI runners the plan) for macOS build, signing and notarization? Same for a Windows code-signing certificate.
4. **Name:** OK to proceed with "FilmCrafter" and a trademark check later, and to use the three supplied images as the brand starting point?
