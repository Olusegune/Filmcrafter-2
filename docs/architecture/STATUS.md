# Status: what is done, what is partly done, what is not

Honest status against the goals in `PHASE0_PLAN.md` (written 2026-10-09, rewritten 2026-10-10 at version 0.12.0).
"Verified" means a test ran, or the thing was built and run here. Anything not marked verified was not run. Nothing here has been run on a Mac; the hand-off has been run in DaVinci Resolve only; one real provider run (Kie.ai) has been made, described below.

## What was verified in this release

- Engine: the whole Python suite (about 1,800 tests, including the end-to-end journeys) passes on Windows.
- Screens: 423 component and logic tests pass; every one of the 40 screen scenes in the screenshot harness opens with no console error or uncaught exception of our own (`PF_QA=1 node scripts/docshots-edge.mjs`).
- Shell: Rust tests pass; the secrets scan is clean; the command allow-lists in the shell match the engine's choices (a test).
- Not verified: anything that spends money at a provider, the macOS build, signing, the hand-off in Premiere Pro or Final Cut Pro.

## Phase 0: architecture and safe reuse

| Goal | Status |
|---|---|
| Protect PULSEFRAME: baseline commit, tag, branch, backup of old `main` | Done and pushed. Tag `pulseframe-v1.36.0-filmcrafter-baseline` = `bad3645b6f13b17ceb8d24e4ce696a05af4757ae`. See `BASELINE.md`. |
| Repository strategy | Derived sibling, seeded from the tag with no shared history; port ledger in `PORT_LEDGER.md`. FrameCore extraction is not started (by design: only after both products are stable). |
| Seed FilmCrafter, rename identifiers | Done (product, bundle id, engine package `filmcrafter_engine`, key service `filmcrafter`, extensions). |
| Remove music-only modules | **Mostly.** Gone in 0.9.0: the song-first screens (setup wizard, listening, production planner, shows, Producer-package import), their unused shell commands, and the Producer planner engine module. A music project that was never finished now says it belongs in PULSEFRAME; a finished one still opens in the Studio. **Still present** because the film path imports them: the dance/choreography and onboarding engine code (imported by the renderer, the story reader and the acting code), the song-first parts of the Studio (hidden on a film), the voices and show-finish helpers. Removing these is a refactor of shared code, not a deletion. |
| Windows build | **Built and verified:** installers build (`FilmCrafter_0.9.0_x64-setup.exe` and `.msi`, unsigned). |
| macOS build | **Not proven.** No Mac was available. The shell has a macOS Python download path and the keychain crate has `apple-native`; the manual CI has a macOS compile job. |
| Windows signing | Not done: no certificate (the installer says "left unsigned"; Windows will warn). |
| Auto-update | Not done (a version check remains; there is no signed updater). |
| CI | Manual-only (as inherited). A job for the film engine tests on Windows and macOS was added; it is not verified on GitHub. |
| ADRs | Written. Kept: Tauri 2, React/TypeScript/Vite, Python engine as a per-call process. A persistent engine service, a data-only model registry and bundled FFmpeg per platform are planned, not built. |

## Phase 1: the golden path

| Step | Status |
|---|---|
| Import a short script; analyse; use as is or write versions; Story Lock | Done and tested. PDFs read in layout order with a repair for broken text. |
| Story development ladder (logline to screenplay) | **Done with the writing helper.** The ladder is shown; *Write it for me* drafts the next step (price first) and opens it in the new-version sheet for you to edit. |
| Production Bible, characters, places, props, states, pictures | Done and tested. **Look:** six kinds of film and about 100 looks, a genre feel layered on top, the twelve principles of animation. Character pictures are the ones you bring; making pictures of characters from descriptions is not wired into the film workflow. |
| Breakdown into shots, Shot Contracts, acting, camera, light | Done and tested. The breakdown is a rule-based first pass; camera and light suggestions are rule-based with reasons; the writing helper can suggest acting, camera and light for a shot (price first). Each shot shows the animation principles it will carry. |
| Storyboard, keyframes, video generation | Wired through the render engine with prices shown and confirmed; tested end to end with locally made pictures and clips, and **run once against a real provider (Kie.ai, 2026-10-10)**: 7 pictures in five looks and one 4-second video, about $0.96. The looks were distinct, the blocking held, and the video stayed on-model; the run found and fixed two bugs (no-reference pictures, captions drawn from quoted speech). Not yet run: fal, Google or OpenAI as the picture or video provider, a multi-shot film, shots with character pictures, and the hands and faces check with a real vision model. The look leads every prompt, with a style lock, a genre layer, the filmmaker's approach and the animation principles; the prompt text is tested, how a real model obeys it is not known. |
| Hands, bodies and faces check on chosen pictures | Done: *Check hands & faces* (price first), a flag on the card, and a question before locking or making video from a flagged picture. Tested at the engine level and in the screens; not run with a real vision model. |
| Review versions, choose, lock | Done and tested. |
| Assemble, basic sound, export | Done and tested with a real FFmpeg export. Sound is one soundtrack file you bring (or silence). |
| Save, close, reopen, continue | Done at the engine level and tested (a film's whole state is files). |
| Hand-off | EDL, OpenTimelineIO, Final Cut Pro XML, manifest, subtitles, copied media. The real OpenTimelineIO library reads the `.otio` and the real CMX 3600 adapter reads the `.edl`, with matching cuts (tested). **Verified in DaVinci Resolve Studio 21.1** (imported through its scripting API: all three files give the six clips and the right length; this found and fixed an EDL naming bug). Not yet tried in Premiere Pro or Final Cut Pro. |

## Phases 2 to 5

| Item | Status |
|---|---|
| Continuity Director | Done for film: rule-based, advisory. |
| Performance Director | Partly: you (or the suggestions) fill acting beats; the writing helper can propose them. |
| Blocking diagrams | **Done (0.10.0):** a top-down plan per shot (people, facing, camera, cone, props), a free rule-based suggestion from framing and the shot before, the 180-degree line checked across a scene, and the plan turned into words in the shot's prompts. Tested at the engine and in the screen; drag tested in a browser. Not tested with a real model: whether a video model keeps people where the words say is unknown. |
| Visual QA of pictures (hands, faces, drift) | Done for the film's Pictures step (above) and in the Production Supervisor. |
| Production Supervisor | Done: findings shot by shot with pictures, a strip of the shots that need you, batch fixes, Director changes. |
| Direction library | 48 filmmakers from every region; traits (never names) reach every shot's prompt in any look; matching follows the story. |
| Local models (Ollama, LM Studio, ComfyUI) | Inherited routing and local-first logic; nothing film-specific was added or tested. |
| Capability-driven model registry | Inherited (`router.py` plus provider manifests); not converted to a data-only registry. |
| Director Command | Plain phrases (Ctrl+K in Shots), shown before they are applied. It does not use a language model. |
| Simple and Pro modes | Done. |
| Interchange for After Effects, AAF, stems | Not done. |
| Engine daemon with streamed progress | Not built. |
| FrameCore shared package | Not started. |

## Known gaps worth fixing next

1. Wider real runs: a whole short film (several shots, character pictures, continuity), the other providers, and the hands and faces check with a real vision model.
2. Open the hand-off files in Premiere Pro and Final Cut Pro (DaVinci Resolve is verified).
3. Prove the macOS build and set up signing and notarization (needs a Mac, an Apple Developer account and a Windows certificate).
4. Finish untangling the music-era code the renderer still imports (onboarding, dance, choreography, voices), then drop the song-first parts of the Studio.
5. The engine daemon, After Effects and AAF interchange (Phases 3 to 5).
