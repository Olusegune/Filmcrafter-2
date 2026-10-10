# Status: what is done, what is partly done, what is not

Honest status against the goals in `PHASE0_PLAN.md` (written 2026-10-09, updated 2026-10-10 at version 0.2.0).
"Verified" means a test ran, or the thing was built and run here. Anything not marked verified was not run.

## Phase 0: architecture and safe reuse

| Goal | Status |
|---|---|
| Protect PULSEFRAME: baseline commit, tag, branch, backup of old `main` | Done and pushed. Tag `pulseframe-v1.36.0-filmcrafter-baseline` = `bad3645b6f13b17ceb8d24e4ce696a05af4757ae`. See `BASELINE.md`. |
| Repository strategy | Derived sibling, seeded from the tag with no shared history; port ledger in `PORT_LEDGER.md`. FrameCore extraction is not started (by design: only after both products are stable). |
| Seed FilmCrafter, rename identifiers | Done (product, bundle id, engine package `filmcrafter_engine`, key service `filmcrafter`, extensions). |
| Remove music-only modules | **Partly.** Removed: song maker, choreography sheet, lyric layers, music Home, wave animation. Still present, because they are wired into code the film uses: the dance/choreography engine code, the Produce and Wizard screens, song analysis, the timeline of older projects, the Producer package import. See `REUSE_MAP.md`. The film does not use them. The full engine set-up no longer installs audio-analysis or speech packages, so older music-video projects can't be analysed in a FilmCrafter build. |
| Windows build | **Built and verified:** installers build (`FilmCrafter_0.2.0_x64-setup.exe` and `.msi`, unsigned). |
| macOS build | **Not proven.** No Mac was available. The shell has a macOS Python download path in `setup_engine` and the keychain crate has `apple-native`, and the manual CI has a macOS compile job and a film-engine test job for `macos-14`, but none of it has been run. Signing, notarization and an auto-updater are not set up. |
| Windows signing | Not done: no certificate (the installer says "left unsigned"). |
| Auto-update | Not done (a version check from PULSEFRAME remains; there is no signed updater). |
| CI | The workflow is manual-only (as inherited). A job for the film engine tests on Windows and macOS was added; it is not verified on GitHub. The same tests pass in a clean Windows virtual environment with only the listed packages. |
| ADRs | Written (`PHASE0_PLAN.md` section 4). Decisions kept: Tauri 2, React/TypeScript/Vite, Python engine as a per-call process. A persistent engine service, a data-driven model registry and bundled FFmpeg per platform are planned, not built. |

## Phase 1: the golden path

| Step | Status |
|---|---|
| Import a short script; analyse; use as is or write revisions; Story Lock | Done and tested. "Revisions" are versions you write; FilmCrafter does not write revisions for you. |
| Story development ladder (logline to screenplay) by the Director | **Not built.** The ladder is shown and you add each step yourself. |
| Production Bible, characters, places, props, states, pictures | Done and tested. Character pictures are the ones you bring; making pictures of characters from their descriptions is not wired into the film workflow. |
| Breakdown into shots, Shot Contracts, acting, camera, light | Done and tested. The breakdown is a rule-based first pass (not an AI director). Camera and light suggestions are rule-based with reasons. |
| Storyboard, keyframes, video generation | Wired through the render engine with prices shown and confirmed, and tested end to end with locally made pictures and clips. **Not tried against a real provider** (no key was used and no money was spent). |
| Review versions, choose, lock | Done and tested. |
| Assemble, basic sound, export | Done and tested with a real FFmpeg export. Sound is one soundtrack file you bring (or silence); per-shot sound and lip sync from PULSEFRAME's engine are not exposed in the film screens. |
| Save, close, reopen, continue | Done at the engine level and tested (a film's whole state is files). |
| Hand-off | EDL, OpenTimelineIO, Final Cut Pro XML, manifest, subtitles, copied media. **The real OpenTimelineIO library reads the `.otio` and the real CMX 3600 adapter reads the `.edl`, with matching cuts (tested).** The FCPXML is checked for structure only. **Not opened in Premiere, Resolve or Final Cut.** Image sequences and stems are not written. |

## Phases 2 to 5

| Item | Status |
|---|---|
| Continuity Director | Done for film: rule-based, advisory. |
| Performance Director | Partly: you (or the suggestions) fill acting beats; no AI writes them. Blocking diagrams are not built. |
| Visual QA of pictures (hands, faces, drift) | Not exposed for films. PULSEFRAME's checks exist in the engine and are not wired to film screens. |
| Local models (Ollama, LM Studio, ComfyUI) | The routing and local-first logic of the render engine are inherited and untouched; nothing film-specific was added or tested. |
| Capability-driven model registry | Inherited (`router.py` plus provider manifests); not converted to a data-only registry. |
| Director Command | Done as a set of plain phrases (Ctrl+K in Shots), shown before it is applied. It does not use a language model. |
| Simple and Studio modes | Done (same film; Studio shows the Shots workspace). |
| Interchange for After Effects, AAF, stems | Not done. |
| FrameCore shared package | Not started. |

## Added after the first status (0.3.0 and 0.4.0)

- **Studio tools / Timeline view.** The full PULSEFRAME studio opens on a film (timeline with scenes, cuts, dialogue lane and soundtrack waveform; Supervisor, Review, Acting, Continuity, Lighting, Colour match, Clean up, Layers, Library, Export). Verified by loading a real film into the studio in the screenshot harness; not clicked through in the installed app.
- **Cards | Timeline** toggle on the same film (the two views of the same shots; the picks are shared through the render project).
- **Film strip** in the film workspace: drag a block's edge to change a shot's length, drag a block to reorder; changes are written to the shots (arithmetic tested; the drag was not tried by hand).
- Song-first parts hidden on a film (Autopilot, Direct My Video, song guide and tour, tempo, Who sings, dance direction).

## Known gaps worth fixing next

1. A real run against one provider (a few cents) on Windows, to confirm the storyboard, keyframe and video steps with a real model.
2. Open the hand-off files in DaVinci Resolve and Premiere Pro.
3. Prove the macOS build and set up signing and notarization (needs a Mac, an Apple Developer account and a Windows certificate).
4. Finish removing the music-era code, then drop the legacy screens and their tests.
5. Wire PULSEFRAME's keyframe check (hands and faces) into the film's keyframe step.
6. Let the Director write the next step of the story ladder, with a price shown first.
