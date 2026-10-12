# QA report: FilmCrafter 0.15.0 (2026-10-11)

What has been tested, how, what it found, and what has **not** been tested. It is written to be re-run: every number below comes from a command in the last section.

## Automated checks (all passing)

| Check | Result |
|---|---|
| Engine tests (Python, `pytest`): story, bible, shots, make, blocking, looks, principles, render with a mock provider, interchange, security, golden film, end-to-end | **1,868 passed**, 6 skipped (optional-dependency tests), 0 failed |
| Screen tests and logic (`vitest`): every screen's markup and arithmetic, the guide, the shortcuts, the looks | **469 passed** |
| App shell (`cargo test`) | **7 passed** |
| The shell's allow-lists match the engine's actions and the frame shapes (a test across Rust, Python and TypeScript) | passing |
| Secrets scan (`rafter secrets .`) | none found |
| The guide lists every look the app has (a test reads `styles.json`) | passing |

Not run: `rafter run` (the remote code-analysis scan; it needs an API key). This release's changes read and write only the film's own folders; the one place that reads a secret is a throw-away test script outside the repository.

## Every screen opened in a real browser engine

All **41** screens of the screenshot harness (Home, New film, the story workspace, Cast & World, Rules & style, Shots and its tabs, Blocking, the Studio and its inspector, Make, Export, the Supervisor, the Continuity check, the writing-help sheets, the Direction library, the Look picker and the rest) were opened in headless Edge with console errors and uncaught exceptions recorded: **none from FilmCrafter's own code**. (The testing browser's Grammarly extension throws one error of its own; it is filtered by reading, not hidden.)

Interaction was tried, not only rendering: dragging a person and a camera on the Blocking plan (it moves and saves), clicking through the kind of film, the look, the genre feel and the animation principles (state follows the clicks), and the Studio inspector's Advanced fold.

## Accessibility scan (automated)

`PF_A11Y=1 node scripts/docshots-edge.mjs` runs axe-core (WCAG 2.1 A and AA) on every one of the 41 screens: **0 findings** after this cycle's fixes (7 kinds were found first, listed below). Automated rules catch only part of accessibility (roughly names, roles, contrast and structure); it is not a substitute for a keyboard-only or screen-reader walk-through, which has not been done.

## Voiceover (new in 0.15.0)

34 engine tests: file names to shots and people (odd spellings, the longer name winning, unknown names asked about, never guessed), bad files refused with a reason, attaching, lengthening a short shot, replacing and removing without deleting, the render request for Seedance 2 (audio sent, who speaks named, the recording beating native speech), the exported film playing the recording at its shot, the hand-off folder, and a film from elsewhere unable to point outside itself. A security review (path containment, size and length limits, no shell) found two hardening gaps that are fixed. **Not tested:** a real provider run with a recording (needs your permission and a spend cap), two people speaking in one shot, long films with hundreds of recordings.

## Film audit (every shot's prompt)

`python scripts/audit_film.py "<film folder>"` (free; nothing is sent) was run on the repaired Summit Sprout film: 58 shots, 45 with people, **0 problems** for pictures. For video it also passes (spoken lines are meant to reach video, so the quoted-speech check is for pictures only). Before this release the same film failed in four ways (see the table below). Screenplay layouts tested: numbered scene headings, forced `@Name` cues, title pages with author and contact lines, `(V.O.)`, `(O.S.)`, `(CONT'D)`, scripts with no scene headings, PDF-extracted text.

## Layout at the smallest window

All screens at 1100 px (the app's minimum width) and 1280 px: nothing outside the window, no sideways scrolling (`PF_OVERFLOW=1 PF_WIDTH=1100`). Tested in a browser engine, not in the installed window; nothing was tested below 1100 px (the app does not allow it), at 125% or 150% display scaling, or on a second monitor.

## Large film

A synthetic 300-shot film: the engine (breakdown 2.2 s; sync 1.0 s; shots view, make status, continuity, hand-off and blocking each 0.1 s or less) and the screens (`?n=300` in the harness; `PF_PERF=1` prints sizes). Select & review, Make and Shots draw in under 3 s with 2,100 to 4,900 page elements and 40 to 84 MB of script memory, no errors. Scenes fold in Select & review (a film over 60 shots opens with only its first scene open), so a 300-shot film is one scene of tiles and a list of headings.

## Real runs

- **Kie.ai, 2026-10-10:** the same shot in photoreal, 3D, 2D hand-drawn and two stop-motion versions (one with a filmmaker's approach applied), and a 4-second video: 7 pictures and 1 video, about $0.96. The looks were distinct, the blocking held, the video stayed on-model.
- **DaVinci Resolve Studio 21.1:** the hand-off imported through Resolve's scripting API: the Final Cut XML, the EDL and the OpenTimelineIO file each give the six clips and 20.0 seconds.

## What testing found and fixed this cycle

| Found by | Problem | Fixed |
|---|---|---|
| Real Kie.ai run | A film with no pictures yet could not make its first picture (the automatic models need a reference) | text-only model of the same family is used when there is nothing to edit |
| Real Kie.ai run | Subtitles drawn into pictures, from quoted speech in the prompt | the prompt says who speaks, never the words |
| Resolve import | The EDL named clips after the original files, so Resolve placed one clip six times | the EDL names each clip after its copy in the hand-off folder |
| Use (user report), real screenplay | An all-capitals title was read as a speaker (shot 1 "Title speaks", scenes off by one); action shots had no people; people with long picture names were never sent; one person could take every picture slot | all four fixed; a test for each |
| Use (user report) | A shot with no people could not make its picture on GPT Image 2.5 Flare ("Needs an image"): the fallback to a text-to-image twin only covered Nano Banana | every image-to-image model falls back to its text twin; the audit tool checks it |
| Film audit | A pronoun action shot ("She wrinkles her nose") had no one in it; numbered scene headings were not scenes; a forced @Name was not a speaker | all three fixed; tested |
| Use (user report) | The Export format list had no 21:9 (nor 4:3, 4:5, 3:4, 9:21), and did not start on the film's shape | one format per frame shape, shared by three screens, tested against the engine |
| Accessibility scan | Film strip blocks' names did not contain their visible text | name now matches the text |
| Accessibility scan | The Studio's inspector tab list held a button that is not a tab | Advanced sits beside the tab list |
| Accessibility scan | Three selects (Aspect, Quality, Lip-sync) had no name | named |
| Accessibility scan | Select tiles' labels differed from their visible text | named by what they show |
| Accessibility scan | Direction cards were a radio containing buttons and a fold | a real radio, its label, the fold beside it |
| Accessibility scan | The lighting strip was a "picture" holding buttons; a Lighting summary held a checkbox | group role; the tick moved out of the summary |
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
- **Long videos**, **low-end machines**, **screen readers** and **keyboard-only use** by a person (the automated scan above is the only accessibility test).
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
