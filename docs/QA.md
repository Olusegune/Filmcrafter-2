# QA report: FilmCrafter 0.13.0 (2026-10-11)

What has been tested, how, what it found, and what has **not** been tested. It is written to be re-run: every number below comes from a command in the last section.

## Automated checks (all passing)

| Check | Result |
|---|---|
| Engine tests (Python, `pytest`): story, bible, shots, make, blocking, looks, principles, render with a mock provider, interchange, security, golden film, end-to-end | **1,817 passed**, 6 skipped (optional-dependency tests), 0 failed |
| Screen tests and logic (`vitest`): every screen's markup and arithmetic, the guide, the shortcuts, the looks | **440 passed** |
| App shell (`cargo test`) | **7 passed** |
| The shell's allow-lists match the engine's actions and the frame shapes (a test across Rust, Python and TypeScript) | passing |
| Secrets scan (`rafter secrets .`) | none found |
| The guide lists every look the app has (a test reads `styles.json`) | passing |

Not run: `rafter run` (the remote code-analysis scan; it needs an API key). This release's changes read and write only the film's own folders; the one place that reads a secret is a throw-away test script outside the repository.

## Every screen opened in a real browser engine

All **40** screens of the screenshot harness (Home, New film, the story workspace, Cast & World, Rules & style, Shots and its tabs, Blocking, the Studio and its inspector, Make, Export, the Supervisor, the Continuity check, the writing-help sheets, the Direction library, the Look picker and the rest) were opened in headless Edge with console errors and uncaught exceptions recorded: **none from FilmCrafter's own code**. (The testing browser's Grammarly extension throws one error of its own; it is filtered by reading, not hidden.)

Interaction was tried, not only rendering: dragging a person and a camera on the Blocking plan (it moves and saves), clicking through the kind of film, the look, the genre feel and the animation principles (state follows the clicks), and the Studio inspector's Advanced fold.

## Real runs

- **Kie.ai, 2026-10-10:** the same shot in photoreal, 3D, 2D hand-drawn and two stop-motion versions (one with a filmmaker's approach applied), and a 4-second video: 7 pictures and 1 video, about $0.96. The looks were distinct, the blocking held, the video stayed on-model.
- **DaVinci Resolve Studio 21.1:** the hand-off imported through Resolve's scripting API: the Final Cut XML, the EDL and the OpenTimelineIO file each give the six clips and 20.0 seconds.

## What testing found and fixed this cycle

| Found by | Problem | Fixed |
|---|---|---|
| Real Kie.ai run | A film with no pictures yet could not make its first picture (the automatic models need a reference) | text-only model of the same family is used when there is nothing to edit |
| Real Kie.ai run | Subtitles drawn into pictures, from quoted speech in the prompt | the prompt says who speaks, never the words |
| Resolve import | The EDL named clips after the original files, so Resolve placed one clip six times | the EDL names each clip after its copy in the hand-off folder |
| Screen sweep | Duplicate React key on Clean up; a dropdown given a null value on New film | both fixed |
| Screen sweep | Two panels (shot references, acting beats) crashed on a reply with a part missing | made tolerant; sample data corrected |
| Screen sweep | The film screen could be blanked by a progress reply with a part missing | made tolerant, tested |
| Screenshots | The Studio's top bar overflowed under the inspector on a film | Director Mode moves into More when the bar is full |
| Screenshots | A "Can't play" message in film mode spoke of a song | worded for the soundtrack |
| Frame-shape work | Changing Aspect in the Studio would have been undone by the next sync | the film keeps its shape; the Studio changes both |
| Looks work | Photorealistic looks would have had "photograph" reworded away like drawn looks | every photoreal look is exempt, from the data |

## Not tested (be honest about these)

- **A human walk-through of the installed app.** Everything above was driven by tests, a headless browser and scripts. Nobody has used the installed Windows app end to end for a real film.
- **Premiere Pro and Final Cut Pro** importing the hand-off (Resolve only).
- **macOS** (no Mac), **code signing and the updater** (no certificate; Windows warns about the installer).
- **Providers other than Kie.ai** (fal, Google, OpenAI) for pictures and video; a **whole multi-shot film** with character pictures; the **hands and faces check** with a real vision model.
- **New frame shapes** (21:9, 9:16...) on a real provider: whether a model returns that shape depends on the model.
- **Large films** (hundreds of shots), **long videos**, **low-end machines**, **screen readers** and **keyboard-only use** (some style and contrast tests exist; no assistive-technology run).
- **Money limits under failure** (a provider charging for a job that then fails) beyond what the mock provider tests cover.

## How to re-run everything

```
python scripts/test_all.py                          # engine, screens, shell, security in one table
npx vitest run ; npx tsc --noEmit                   # screens and types
cargo test --manifest-path src-tauri/Cargo.toml     # the shell
npm run dev                                         # then, in another terminal:
PF_QA=1 node scripts/docshots-edge.mjs              # all 40 screens, fails on any console error
python scripts/make_look_docs.py                    # after adding a look
python scripts/live_test.py                         # one real picture (prices first; --yes to spend)
python scripts/make_handoff_sample.py "<folder>" && python scripts/resolve_check.py "<folder>"   # the Resolve import check
```
