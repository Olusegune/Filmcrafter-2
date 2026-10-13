# QA report: FilmCrafter 0.23.4 (2026-10-13)

What has been tested, how, what it found, and what has **not** been tested. It is written to be re-run: every number below comes from a command in the last section.

## Automated checks (all passing)

| Check | Result |
|---|---|
| Engine tests (Python, `pytest`): story, bible, shots, make, blocking, looks, principles, render with a mock provider, interchange, security, golden film, end-to-end | **1,772 passed**, 8 skipped (optional-dependency tests), 0 failed |
| Screen tests and logic (`vitest`): every screen's markup and arithmetic, the guide, the shortcuts, the looks | **503 passed** |
| App shell (`cargo test`) | **8 passed** |
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

## Measured, and decided against (0.16.0)

- **A long-running engine process.** Each engine call starts Python and answers in about 0.18 to 0.22 s (shots, make status, voiceover, blocking on a 58-shot film), of which about 0.24 s is importing the modules once. A resident process would save a fifth of a second per call, which no one would feel, and adds a process to supervise and restart. Not built. Reconsider if real use shows lag.
- **Removing the music-era code.** A reachability check from the app shell's commands finds 90 of the 93 engine modules still reachable; of the three it did not reach, two (`animation_principles`, `styleguard`) are in use (imported with an alias the check does not follow) and one (`model_audit`) is a developer tool. The music-era code is not dead: the app can still open PULSEFRAME projects. Removing it would mean dropping that, which is your call, not a clean-up.

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
| Whole-app pass (0.21.0) | A dialogue shot with no recording sent the film's silent soundtrack to Seedance as "the voice" and told it to speak along to it (probably why the first videos were mute) | films send no audio without a recording; tested |
| Whole-app pass | The File menu said "New Music Video" and most items did nothing from the film screens; the one-file save packed only the render project (no story, cast, shots or recordings) | a film-aware menu and a `.filmpack` of the whole film; round trip tested |
| Whole-app pass | Joining two shots lost the joined shot's recording; a deleted shot's recording stayed filed under an id a new shot could be given | recordings move or are put aside; tested |
| Film audit | Scene blocking kept a ghost character from an old breakdown and put it into prompts | blocking follows the shots; tested |
| Whole-app pass | Installer and app descriptions said "music video"; FilmCrafter registered `.pulse` and Producer files (PULSEFRAME's) with the old waveform icon | FilmCrafter's own icon, `.filmcrafter` and `.filmpack` only |
| Use (user report, with pictures) | A friend drawn in another character's clothes: the previous shot's picture was sent as a reference to a shot of other people; "two friends" had no friends in the shot | the reference is sent only for people the shots share; plurals mean the scene's numbered friends; tested |
| Clean-up | A Word (.docx) screenplay was silently cut after 6,000 characters | read whole; tested |
| Use (user report) | Choosing 21:9 in the Shape list gave 16:9 again: the shape was saved on the render project only and the next sync rebuilt it from the film | the film's shape is set from every place it can be chosen; tested |
| Use (user report) | The voiceover could not be found: it was only on the Shots screen, which Simple mode hides | opens from the Studio's bar and the Export screen as a sheet |
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

## What 0.19.0 changed, and how it was checked

- **Screen sweep** (47 screens, 1100 px and 1280 px wide): no console errors, 0 accessibility findings, no overflow. Run after the clapperboard, waveform and big-film changes.
- **Home clapperboard:** looked at in a browser (arm open and board scaled up mid-loop); structure and reduced-motion tested. Not seen in the installed app.
- **Waveform:** drawn from a generated test WAV in the browser harness (decode, bars, collapsing when a file can't be decoded); the peak arithmetic is unit tested. The `asset:` fetch inside the installed Tauri app is **not** tested.
- **Big films:** on the 300-shot harness film, relayout fell from about 115 ms to about 34 ms with off-screen cards skipped. Measured in a headless browser, not on a real film.
- **Nano Banana 2.1:** a read-only key check (no generation, no spend) showed the Kie key valid (17,451.6 credits) and `gemini-nano-banana-2.1` available to the Google key; no fal key was found. Kie's manifest was fetched live: model id `nano-banana-2-1`, 10 reference pictures, 1K/2K/4K, 15 shapes. Three engine tests cover the default, the list and which endpoints see pictures. **No picture has been made with it yet.** fal's 2.1 is untested; thinking level and web-search grounding are not passed on.
- **Minimum window height** 700 to 660 for 150% display scaling on a 1080p screen: reasoned from the screen arithmetic, not tried on a real 125% or 150% display.

## What 0.20.0 added, and how it was checked

- **Drop on a person, Undo, the recorder** (structure, WAV encoding, silence trimming, next-unvoiced-line, who is under the pointer): unit tested; the recorder's layout and the blocked-microphone message were seen in the browser harness. **Not tested:** a real microphone, Windows' microphone permission in the installed app, the drag-over highlight and drop-on-a-name (they only exist in the real window).
- **ElevenLabs voices** (`cast_voice`): 17 engine tests with every ElevenLabs request faked: no key means nothing is asked; the plan is read only when the plan view asks; a library voice is kept; a designed voice is heard before it is kept and a preview id cannot be a path; cloning refuses without consent, a non-audio file or a 30 MB+ file, and sends nothing then; a line is never spoken without a confirmed yes; a repeat is free; a busy service is retried but a refusal or a used-up plan is not; your own recording replaces a spoken one and the spoken one is kept. **Not tested against the real ElevenLabs** (no key stored here): the request shapes follow ElevenLabs' published reference (`/v1/text-to-voice/design`, `/v1/text-to-voice`, `/v1/voices/add`, `/v1/text-to-speech/{id}`, `/v1/user/subscription`, `/v2/voices`).
- **Home card padding:** seen in the browser harness; a test keeps it from growing back.

## What 0.22.0 added, and how it was checked

- **Voice lanes and the line studio:** structure and arithmetic unit tested (who speaks in what order, where two people sit in one shot, the engine's and the screen's list of tag-reading models kept equal, the price asked before the first spoken line); seen in the browser harness (4 lanes, filled and dashed clips; the studio opens; a feeling chip writes `[tired]` into the line; the price shows). **Not tested:** the lanes in the installed app on a long film, and drag-and-drop onto a clip (it only exists in the real window).
- **Takes:** engine tests with ElevenLabs faked (every version kept; switching sends nothing and archives, not deletes; a take from another line or a path is refused; the shot's written dialogue never gains a tag).
- **Real ElevenLabs run** (Eleven v4, a library voice, five short lines, voice design): a spoken line was attached and marked; a repeat was free; a directed take (`[sighs]`) and a second take were made; switching back cost nothing; a voice design returned three options. **Not done for real:** cloning, keeping a designed voice, the plan line (the key lacks `user_read`).

## What 0.23.0 changed, and how it was checked

- **Film strip | Edit:** seen in the browser harness (Film strip: no resize handle, no lanes, no layer button, cards at 112 px, timeline 328 px high); the layout memory is unit tested (a film starts in the Film strip, each film keeps its own mode, damaged storage is ignored). **Not tested:** dragging in Edit mode after the change (the code for it is untouched), and a real long film in the Film strip.
- **Voices in the Video tab:** seen in the harness (two cards for a two-speaker shot, one opens the editor inline); the summary wording and the wiring are unit tested. **Not tested:** the inline editor in the installed app's real panel width.

## Lip-sync: what was checked and what was not (0.23.1)

- **Checked, free:** on the real Summit Sprout film, for a voiced shot (S07-06), the app builds the Seedance 2 request with the recording as a reference-audio clip (now 4 s, the shot's length, instead of the 1.6 s line, which Kie would refuse: it takes 2 s or more), three character reference pictures, `generate_audio: false` and a prompt that says who speaks along to the audio. The golden path's own rules were kept: one test shot first (the Make film screen prefers a speaking one), voices before video.
- **Found and fixed:** a recording under 2 s was sent as it was; the clip is now padded to the shot's length (two unit tests).
- **NOT checked, and cannot be without spending:** whether Seedance 2 moves the mouth in time with reference audio. Kie's documentation does not say it does. The film has no approved keyframes yet. One take is estimated at about 164 Kie credits. The dependable alternative, the lip-sync pass on a finished take, has not been run either.

## Not tested (be honest about these)

- **A human walk-through of the installed app.** Everything above was driven by tests, a headless browser and scripts. Nobody has used the installed Windows app end to end for a real film.
- **Premiere Pro and Final Cut Pro** importing the hand-off (Resolve only).
- **macOS** (no Mac), **code signing and the updater** (no certificate; Windows warns about the installer).
- **Providers other than Kie.ai** (fal, Google, OpenAI; Google's Nano Banana 2.1 is reachable with your key but has not made a picture) for pictures and video; a **whole multi-shot film** with character pictures; the **hands and faces check** with a real vision model.
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
