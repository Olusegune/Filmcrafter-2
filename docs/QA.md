# QA report: FilmCrafter 0.25.4 (2026-10-15)

What has been tested, how, what it found, and what has **not** been tested. It is written to be re-run: every number below comes from a command in the last section.

## Automated checks (all passing)

| Check | Result |
|---|---|
| Engine tests (Python, `pytest`): story, bible, shots, make, blocking, looks, principles, render with a mock provider, interchange, security, golden film, end-to-end | **1,976 passed**, 8 skipped (optional-dependency tests), 0 failed |
| Screen tests and logic (`vitest`): every screen's markup and arithmetic, the guide, the shortcuts, the looks | **549 passed** |
| App shell (`cargo test`) | **9 passed** |
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

## Layout and accessibility sweep (2026-10-15, 0.25.4)

`PF_OVERFLOW=1 PF_QA=1 PF_WIDTH=1000 (and 1280) node scripts/docshots-edge.mjs home film cast castsound soundfx soundscene soundstyle shots make select studio export dirliball compose library supervisor`: nothing outside the window, no page scrolling sideways, no console errors. `PF_A11Y=1` (axe-core, WCAG 2.1 A and AA) on 14 of those screens: 0 findings. The one defect found by eye was the Direction library's squashed cards (fixed). Not covered: 125% and 150% Windows scaling (a person must look), and dialogs, which the harness draws inline rather than as modals.

## Release checks for 0.25.3 (2026-10-14, the last whole runs on the release code)

Engine 1975 passed, 8 skipped, 0 failed in the last whole run (6 min 15 s), plus one test added afterwards (the learned sound-effect price: 1976); screens 549 passed; `cargo test --lib` 9 passed; `rafter secrets` none; `npm audit --omit=dev` 0 vulnerabilities. New since 0.25.0: `test_damage_records` (a damaged shot record is reported and kept, a good backup is used, no temp files or locks left), the learned-price test in `test_audiogen`, the class-name collision guard in the screen tests, and the corrected clone and lip-sync-document wiring tests. Not re-checked by a person: the installed app, the new Edit shot cards and the voice dialogs at 125% and 150% Windows scaling.

## Real runs of 0.25.0 (2026-10-14, the owner's ElevenLabs credits, a throwaway film, cap 150 credits)

Done with the engine from the released code on a **throwaway film** (not a real project), the key read from the Windows Credential Manager and never printed. Total ElevenLabs credits **reported** by ElevenLabs: **39** (our estimates added up to 91).

| What | Result |
|---|---|
| Sound effect, 2 s ("a kettle clicking off in a quiet kitchen") | Worked: a 2.04 s file was saved to the library as *generated*, pending approval, `commercial use: not known`; ledger entry completed; **ElevenLabs reported 11 credits** (estimate 22). Asking again was free and sent nothing. |
| Sound effect, 4 s, same words | Worked: 4.05 s; **reported 22 credits** (estimate 44). So on this account a sound effect cost about **5.5 credits per second**, half of the help-centre figure the app uses. The app keeps the higher figure as a safe upper bound and always calls it an estimate; it is not changed from two data points. |
| Voice scene (two short lines, Eleven v4, a premade library voice, cap 60) | Worked: both lines spoken and attached, no failures; the scene's price was shown first (25 characters, about 25 credits); **reported 4 and 2 credits** for 18 and 7 characters. The reported amounts are well below the app's characters-times-multiplier estimate; what ElevenLabs' `character-cost` header measures is not documented, so the app shows it only as "reported" and keeps the estimate apart. |
| Table read of the scene | Both lines found in order (1.2 s and 0.96 s), none silent. |
| Model list refresh (free) | ElevenLabs answered with 9 speech models; its stated credit multipliers (v4 1.0, v4 Turbo 0.5, Flash 0.5) matched the app's built-in ones. |
| Lip-sync test (Kie 200 of 300 credits, ElevenLabs 3 of 50) | Run on a throwaway film: Take A (Seedance 2, picture + recording) did **not** follow the voice's timing by a crude mouth-motion measure; Take B (Kie lip-sync pass) moved the mouth toward the words but is not proven good. Full table in `docs/LIPSYNC_VALIDATION.md`. Files for judging are on the owner's Desktop. |
| Not run | Music (ElevenLabs Music or Suno through Kie.ai) and a person's judgement of any generated audio or video. |

## What 0.25.0 (creative production expansion) added, and how it was checked

- **Whole-suite results on the branch `stage-a-sound-bible`:** engine **1971 passed, 8 skipped, 0 failed** (6 min 9 s); screens (`vitest`) **548 passed**; `tsc` clean; `cargo test --lib` 9 passed; `rafter secrets` none found; `npm audit --omit=dev` 0 vulnerabilities.
- **New engine tests (no provider, no network):** `test_audiolib` 12, `test_bible_sound` 5, `test_voicedirect` 25, `test_audiocues` 15, `test_audiogen` 18, `test_audiomix` 14 (real audio and ffmpeg; one through `export.build`; a ten-minute film for memory), `test_outdated` 9, `test_registry` 14, `test_preupdate` 4.
- **What the audio tests measure:** where a cue lands and at what level; fades and loops; the depth of the dip under a voice (within 2.5 dB of the setting); peaks under the ceiling; loudness within 2.5 LU of a target; memory under 150 MB for a ten-minute film; the planned sound present in an exported film and a suggested-only cue absent; the sound file's hash unchanged.
- **What the paid-path tests prove (all providers faked):** nothing is sent without `confirmed`, the rights acknowledgement and (for unpublished prices) the accepted unknown cost; an unclear outcome is never retried and blocks the identical request; a refusal, a busy provider and no connection are each recorded as what they are; a sound made before is reused free; non-audio replies are not kept; only parameters the registry lists are sent.
- **Not tested:** any real ElevenLabs sound-effect, music or seed request; any real Kie.ai Suno task (its reply format was read from the documentation); the real lip-sync (see `docs/LIPSYNC_VALIDATION.md`); the Edit timeline lanes and the new screens in the installed app (browser harness with mocked data only); a clean-machine update (the updater is not built).

## What 0.24.0 (Phase 0) added, and how it was checked

- **Paid-voice safety** (`test_voice_paid_safety.py`, 33 tests, every provider call faked, no network): each paid action refused by the engine unless confirmed and sends nothing; consent and spending are separate; design needs the unknown-cost acceptance; cancelled means no request; estimates and reported amounts never added; an ambiguous 5xx / timeout is `uncertain` and never re-sent; creation is never retried; 429 retried a bounded number of times; crash leftovers settled truthfully; identical request blocked until the person resolves it; limits; six processes writing entries at once keep every entry; no credential in the ledger; a film with no ledger works as before.
- **Safe I/O** (`test_safeio.py`, ~26 tests incl. a six-process hammer and a folder that refuses writes): absent / valid / damaged / unreadable cases kept apart; the damaged bytes are preserved; `.bak` only ever holds a good file; a failed write leaves the old file; `film.json` and the voice files adopted. `test_render_lock.py`: the render queue's lock under contention (the Windows race was reproduced on the old code, 1 run in 8).
- **Film backups** (`test_filmbackup.py`, 10 tests): snapshot contents (no media, no render project), skipped when unchanged, restore verified first, an undo snapshot, nothing deleted, the ledger never rolled back, a tampered or unreadable snapshot refused with nothing changed, an unsafe path refused, only 30 kept, a damaged film.json reported and recovered from its `.bak`.
- **Opening files** (`test_film_pack.py`, +7): hostile paths, links, too many items, expansion bomb, too little disk, a file lying about its size, a normal film still opens. `test_cast_voice.py`: a sample must really be audio, is written whole; the engine says which models take tags.
- **Screens** (`voiceusage.test.ts` and updated `voice.test.ts`, `ui.test.tsx`): the confirmation words, the usage line (reported vs estimated), each screen asks before it sends the flags, the update check is off in both the engine and the screen, the asset scope is not the whole home folder (a Rust test reads `tauri.conf.json`).
- **Not tested:** the installed app (nothing was installed); the narrowed media scope on a real Windows install with a film on another drive (the code adds opened folders at run time, which compiles and is unit-tested only for the configured scope: see the smoke checklist in the Phase 0 report); real ElevenLabs behaviour for any of the new paths (no paid call was made); the usage panel was checked in the browser harness only.

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

## What 0.28.0 added, and how it was checked (2026-10-21)

- **Sheet matching (which of a person's pictures go to which shot).** Engine unit tests (`test_sheetmatch.py`, 6 + an integration test through `make.sync`): near words are understood (anxious finds worried; sprints finds running), identity pictures are chosen first and at most four, an expression, pose or outfit picture goes only to a shot whose words fit (and at most one of each kind), an outfit needs its own words not one shared word ("red coat" is not sent for "a red dress"), a rebuild leaves no stale picture, and a film with no sheets is unchanged. **Not tested:** on a real film with real sheets, or how a video model uses the extra references.
- **Action choreography.** Engine unit tests (`test_choreography.py`, 32): every kind and every ending gives a valid plan (camera words from the lists, lengths 1.5 to 6 s, no unfilled placeholders); the same request gives the same plan and a variation another; a contact is never more than three action shots in a row without a cut to a reaction or detail; the momentum ends with the winner; who was hurt is carried forward and only for the person hit; people and counts are checked; editing keeps the plan valid; **applying adds new shots after the scene (or a chosen shot) and every existing shot file is byte-identical afterwards**; a plan is applied once; plans are listed and removed aside; the module cannot spend or send, and its wording has no gore. Screen: words and wiring unit tested (`choreo.test.ts`), the sheet seen in the browser harness (kinds, a plan of four shots, centred over the screen). **Not tested:** how the planned shots render on a real video model, or by a person who directs action.
- **A visible Materials button** next to Guide and Costs (wiring tested, seen in the harness).
- **Player.** Scrubbing, previous and next shot and the rounded gold volume bar were driven in the browser harness; the no-sound-file clock is covered by code review and a source-text test only (the harness film has a mock soundtrack that cannot play).
- **Dialogs, spending token, finished-film check, Costs, Guide, materials import** (0.26 to 0.27): see the changelog; each has its own tests.

## Yellow tint, noise and waxy skin (after 0.28.0): what was checked

- **Prompt wording** (`test_picturecare.py`, 6): on by default and off per film; the line asks for neutral white balance, real skin and a clean image; a warm shot (golden hour, candlelight, sunset, fireplace, sepia, or a warm look) keeps its warmth; the negative prompt gets the words once and not for warm shots; it reaches the real request for both a picture and a video model; it gives way to the hands line but not to loose extras when a prompt is too long. An existing anatomy test was updated: a model with a negative prompt now always gets a clean-image negative unless picture care is off.
- **Whole-film cast** (`test_colormatch.py`, 5 new, with real ffmpeg clips): an all-yellow film is found where matching shots to each other sees nothing; a neutral film has no cast and a small cast is left alone; removing the cast moves a yellow shot clearly towards neutral (measured on exported pixels) while a cool shot stays cool; denoise and grain are off until asked and are plain ffmpeg filters that run in a real export; the picture-care switch is a setting of the film.
- **Screen:** the Colour match sheet shows the new options (seen in the browser harness with mock data; wording and wiring unit tested).
- **NOT checked:** on a real film from a real model. Whether the new wording actually reduces the yellow cast or the waxy look in a given model's pictures is unknown until a film is made with it; the post-export cast removal is a measurement-and-offset, so a film with a deliberately warm palette needs the strength lowered or the option left off.

## Not tested (be honest about these)

- **A human walk-through of the installed app** (in particular the Guide, bringing materials in from a real storyboard, the Action scene sheet, and the player's Play on a film with no sound file). Everything above was driven by tests, a headless browser and scripts. Nobody has used the installed Windows app end to end for a real film.
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
