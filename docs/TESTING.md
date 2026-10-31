# Testing PULSEFRAME

One command runs every kind of check and prints one table:

```
python scripts/test_all.py            # everything that is installed
python scripts/test_all.py --quick    # skip the slow engine types (integration, e2e)
```

Set `PF_PYTHON` to the Python that has the engine's requirements installed. A step whose tool is not installed is reported as **SKIPPED** with the reason, never as passed.

## The six kinds of test, and where each lives

Every engine test carries one or more markers (`analysis/pytest.ini`, assigned in `analysis/tests/conftest.py`). Run one kind with `python -m pytest -m <kind>` inside `analysis/`.

| Kind | What it proves | Where | Run |
|---|---|---|---|
| **Unit** | one function or small module in isolation: parsing, clamping, curves, naming, price maths | most `analysis/tests/test_*.py`; `src/__tests__/*.test.ts` (movement and keyframe curves, helpers) | `pytest -m unit`, `npx vitest run` |
| **Integration** | several parts together: real ffmpeg, files on disk, a fake provider or local server, a project folder | `test_render`, `test_overlays`, `test_shapes`, `test_keyframes`, `test_title_motion`, `test_customframe`, `test_cleanup`, `test_producer_*`, `test_show*`, … | `pytest -m integration` |
| **End to end** | a whole journey, from an audio file to a finished film, with the paid services stood in for | `test_e2e_journey.py` (audio → listen → shot plan → rendered take, own clip, moving still → clean-up and restore → inserted frame → layers with keyframes → export → the exported file's length, sound and pixels are checked), `test_create_from_song_flow.py` | `pytest -m e2e` |
| **Regression** | a bug that really happened stays fixed: video-model failures from real renders, file-in-use errors on Windows, shared temp names, readable crashes, document reading | `test_video_models`, `test_render`, `test_replace_retry`, `test_tmp_names`, `test_crash_report`, `test_doc_text`, `test_stills`, `test_prompt_dedupe`, `test_acting_defaults`, `test_lipsync_mode` | `pytest -m regression` |
| **Acceptance** | the promises made to the user, written as scenarios and traced to requirements in [ACCEPTANCE.md](ACCEPTANCE.md) | `test_acceptance.py`, `test_golden.py`, the two end-to-end files | `pytest -m acceptance` |
| **Security** | hostile input, unsafe paths, leaked secrets, unsafe commands, oversized files, and the shell's gatekeeping of the engine | `test_security.py`, `test_fonts.py`, `test_updates.py`; plus the scans below | `pytest -m security` |

The screen has its own tests (`npx vitest run`: the Golden Path strip, dialogs, takes, the keyframe editor, the icon set, the movement and keyframe formulas, the shortcut list, the command palette, the sound panel, the documentation viewer, error wording) and the app shell has Rust tests (`cargo test` in `src-tauri`).

### Where the newest tests sit, by kind

| Kind | Engine (`analysis/tests`) | Screen (`src/__tests__`) |
|---|---|---|
| **Unit** | `test_shotsound_unit` (clamping, damaged files, layer rules, the loudness reading, the history file's shape; no ffmpeg) | `shortcuts.test.ts` (keys and modifiers), `palette.test.tsx` (matching and ranking), `errors.test.ts` (wording), `layers.test.tsx` (reduced motion) |
| **Integration** | `test_shotsound` (layers, levels, mix, preview, native scenes), `test_layer_undo`, `test_split_speech` (the real separator on synthesized speech; Windows only) | `shotsound.test.tsx` (the panel and Shift+M), `help.test.tsx` (pictures and keys in the guide) |
| **End to end** | `test_e2e_sound` (song, shots, a take with sound, keep, split, trim, preview, layers and undo, loudness; no render repeated) | none: no test drives the real window |
| **Regression** | `test_regressions_sound` (the mono 3 dB loss, a pristine shot marked changed, temp names) | `shortcuts.test.ts` (Ctrl+R, Ctrl+A, Ctrl+Z are not letter shortcuts), `help.test.tsx` (a repeated block key), `shotsound.test.tsx` ("Back to how it was" only after a change) |
| **Acceptance** | `test_acceptance` `ACC13` to `ACC16` (REQ-13 to REQ-16) | the shortcut table in the guide matches the list (`shortcuts.test.ts`) |
| **Security** | `test_security_sound` (hostile ids and layer names, a settings file or history from another project, nothing written outside the project); the shell/engine checks in `test_security` cover the new `shot_sound` command | none |

### Timeline, transitions, lip-sync, dance and camera (1.15)

| Kind | Engine (`analysis/tests`) | Screen (`src/__tests__`) |
|---|---|---|
| **Unit** | `test_dance` (the beat line, the dance-ready rules), `test_looks` (the right look for each feeling, never over a choice), `test_lipsync_timing` (early/late/own sound on synthetic vocals), `test_lipsync_mode` (Auto and the explicit modes) | `lanes.test.tsx` (lane packing, drag, trim, snap, bars, the transition picker, the list matching the engine's), `looks.test.tsx`, `dance.test.tsx`, `testShot.test.ts`, `lipsync.test.tsx` |
| **Unit** (1.16) | `test_changes` (prompt sentences, every kind of change, a real project before and after switching modes or editing beats), `test_track` (counts per model, only real dollars, junk records, the sound check run once and limited), `test_planio` (the light plan reader behaves exactly like the rendering module's and does not load it) | `changes.test.tsx` (the since-last-take strip and the per-model line) |
| **Integration** | `test_transitions` (all 14 transitions on real red and blue clips: where each side of the picture is, exact length, a longer one still under way), `test_lipsync_timing` (real takes with and without sound) | none |
| **Regression** | `test_lipsync_mode` (the Seedance 2 first-frame and audio conflict), `test_transitions` (the cache key includes the length) | the shortcut table in the guide matches the list (`T`, `H`) |
| **Acceptance** | `test_acceptance` `ACC17` to `ACC19` (REQ-17 to REQ-19) | none |
| **Security** | `test_security_timeline` (junk and out-of-range layer times, unknown transition names and lengths, nothing from the caller reaching an ffmpeg filter, unreadable project files, junk shot ids) | none |

Each fix was checked by undoing it and watching its test fail: the wipe direction, a person's choice being overruled, the sign of the sound lag, Auto applying to wide shots, the off-beat rule and the transition length in the cache key.

### Looking at the real screens (QA by hand, with a script)

No test renders real pixels, so layout bugs (a button on top of another, a squeezed player, a name missing for a screen reader) are found by looking. `scripts/ui-audit.js` and `scripts/ui-audit2.js` (contrast, keyboard focus, language, duplicate ids, cut-off text) does the looking for you: open the Studio in the browser preview (`npm run dev`, `http://localhost:1420/?mock`), set the window to the app's smallest size (1100 x 700) and to a large one, paste the script, and read `window.__audit()`: page scrolling, controls with no accessible name, controls covered by another control, tiny controls. Do it again with the Layers panel open and on each sheet. `layout.test.ts` keeps the specific layout fixes from coming back (it reads the style rules).

### Models, upscaling, OpenRouter, styles and the rest (1.17)

| Kind | Engine (`analysis/tests`) | Screen (`src/__tests__`) |
|---|---|---|
| **Unit** | `test_modelinfo` (what each Kie model can see, clean text, recommended, new; pinned to all 56 audited picture models; the `image_input` and code-fence parsing bugs), `test_styleguard` (words that ask for a photograph, the style lock, never dropped), `test_upscale` (the request read from each tool's schema, keyframe and take, undo, failure, resume), `test_openrouter` (settings, client, price list, estimates), `test_review_fix` (a lip-sync model is refused for a shot) | `glyphs.test.tsx`, `upscale.test.tsx`, `reviewfix.test.tsx`, `supervisor.test.tsx`, `splash.test.ts`, `dancers.test.tsx` |
| **Regression** | `test_styleguard`, `test_review_fix`, `test_modelinfo` (Nano Banana's `image_input`, Kling 3.0's fenced docs), `test_golden` (a copied project is not "stale"), `test_routing` (Kie first) | `supervisor.test.tsx` (an empty answer no longer crashes the sheet) |
| **Security** | `test_upscale` (a keyframe path that leaves the project, junk factors, junk run files), `test_openrouter` (https only, the key never in the settings file) | `splash.test.ts` (the splash can only ask for what it is allowed to) |

Run for real, not in the test suite: `python -m pulseframe_analysis.model_audit kie --kind image` and `--kind video` read every Kie model's published schema and build the request PULSEFRAME would send for it. As of 1.17: 56 of 56 picture models and 61 of 61 video models pass; 25 picture models are text-only (listed as "blind").

The screen tests have no markers, so the table above is how they are classed.

### A look for one scene or one shot (after 0.31.1)

| Kind | Engine (`analysis/tests`) | Screen (`src/__tests__`) and shell |
|---|---|---|
| **Unit** | `test_stylebible` (the order shot, scene, film; older projects; unknown looks; set, read, clear) | `stylestale.test.ts`, `shotlook.test.tsx` (markup and the save call) |
| **Component** (jsdom, clicked) | none | `component/shotlook.dom.test.tsx` (choosing a look saves for that shot only, the empty option clears it, a failed save says why, the panel stays open after clearing, the picker for one shot) |
| **Integration** | the look in the prompt and on each job; the real command run as a process, 8 at once | `cargo test` (the film's look keeps scene and shot looks) |
| **Regression** | `make.sync` keeps scene and shot looks | picking the inherited look clears it; the picker for one shot gives back only the look, not the film's notes; the panel folded shut when its look was cleared |
| **Security** | bad shot ids, scene numbers and looks; a folder that is not a project; a damaged project file | none |
| **End to end** (Playwright, real Edge) | none | `e2e/shotlook.spec.ts` (Shot tab, header chip, picker, Escape, no render button) |
| **Accessibility** (axe-core, WCAG 2.1 A and AA) | none | `e2e/a11y.spec.ts`: every scene of the screenshot harness (43) |

### Browser tests (Playwright) and component tests (jsdom)

```
npm run test:components            # jsdom component tests (src/__tests__/component), fast
npx playwright test                # all browser tests (starts npm run dev if it is not running)
npx playwright test e2e/a11y.spec.ts
```

The browser tests drive the **screenshot harness** (`http://localhost:1420/docshots.html?scene=...`), which answers the app's backend calls with made-up data held in memory: no engine, no provider, nothing can be charged. Locally they use the Microsoft Edge that Windows already has (`PW_CHANNEL=chrome` or `msedge` to choose); in CI use `npx playwright install chromium`. They do **not** drive the whole Studio: its browser preview (`?mock`) needs a `mock-data/` folder that is not in the repository (it is in `.gitignore`). The harness removes its own `docshot` class in these tests, because that class un-scrolls long lists for screenshots. Animations are switched off first: a sheet that is still fading in gives axe a colour that is not real (a first run reported 22 screens with low contrast that were not).

### Seedream sizes, BytePlus and the first-run screens (after 0.31.1)

| Kind | Engine (`analysis/tests`) | Screen (`src/__tests__`, `e2e`) and shell |
|---|---|---|
| **Unit** | `test_picture_size` (sizes, price per size), `test_byteplus` (sizes, prices, request, errors) | `modelpickersize.test.tsx`, `byteplus.test.ts`; `cargo test` (key slot, name, no free pass) |
| **Engine** (presets) | none | `test_presets.py` (every built-in preset valid, includes and thumbnails exist; stacking order and who wins; a preview changes nothing; applying sets only what is asked and calls no provider; a choice of yours is kept unless you replace it; the frame shape is yours once pictures exist; applying twice changes nothing; undo puts back only what is still as left; your own presets, favourites, files out and in, bad files refused with a reason; a preset cannot carry a LUT; a non-film project; a newer record), `test_presets_vertical.py` (the vertical version is a separate file in the phone shape and the original is untouched; the part of each shot kept is where the take's centre line lands; captions kept above the margin), `test_series.py` (a ten-episode plan from one idea without spending; the shape; the film's cast; suggestions versus yours; resizing keeps what you wrote; the report; export) | `pytest tests/test_presets.py tests/test_presets_vertical.py tests/test_series.py` |
| **Component** (jsdom, clicked) | none | `component/presets.dom.test.tsx` (stack order, the preview and replace choices sent with apply, nothing applied by looking, undo, search and filters, favourites, a refusal as an alert), `e2e/presets.spec.ts` (the sheet with the pack's thumbnails, stacking, the yours-kept rule, my own presets, the series plan, the vertical sliders; in the accessibility scan as the `presets` scene) |
| **Engine** (motion graphics) | none | `test_motion_templates.py` (every template well formed and every slot used; words go only into text slots and are cleaned; one group per use, removed alone; a bad moment or full project changes nothing; the preview is a real picture; glow and blur; a lower third in the finished film) |
| **Engine** (compositing) | none | `test_compositing.py` (blend names from a fixed list and never typed into the filter; mask and key values clamped and removable; a key removes a shadowed screen and keeps the subject; soft edges and spill; masks and vignettes; multiply and screen in a real export match the arithmetic; a blended shape changes only its own area) |
| **Browser** (compositing) | none | `e2e/mix.spec.ts` (the Mix and effects section: blend, shape, cut-out colour, glow and blur) |
| **Browser** (Home) | none | `e2e/home.spec.ts` (the three starts; pictures load and fall back; details and Start with a preset; the gallery, search and filters; recents, many films, no films; narrow width; keyboard and focus; accessibility with the sheets open) |
| **Unit / component** (Home) | none | `presetshelf.test.ts` (one list of presets, every picture exists, search, wording), `component/newfilmpreset.dom.test.tsx` (the preset is only remembered, never applied, when the film is made) |
| **Engine** (Home presets) | none | `test_home_presets.py` (remembering a preset changes nothing in the film; bad ids refused; the catalog shows it; applying clears it; old records load) |
| **Component** (motion graphics) | none | `component/motion.dom.test.tsx` (the words typed are the words sent; take-it-away sends only its group; one template's words never leak into another; an error is shown) and `e2e/motion.spec.ts` |
| **Engine** (the Smart Editor) | none | `test_smart_editor.py` (the two rules, each with its reason; a pause you asked for or a beat you wrote is kept and reported, a draft is not read; a locked track is not touched; styles; accepting is one change and one undo takes it back; a rejected suggestion stays away until reset; a stale suggestion is refused; the preview is two real clips and saves nothing; plain requests, and ones it cannot do; the same cut gives the same suggestions) | `pytest tests/test_smart_editor.py` |
| **Component** (jsdom, clicked) | none | `component/smarteditor.dom.test.tsx` (what, why, clips, time; preview before accept; accept and refuse send the right suggestion; an engine refusal is an alert; a request and an unbuilt style), `e2e/smart.spec.ts` (the sheet in a real browser engine; in the accessibility scan as the `smarteditor` scene) |
| **Engine** (preview copies and recovery) | none | `test_proxies_recovery.py` (only big clips get a copy; looking makes nothing; a changed take gets a new copy; the board offers the copy only when there is one; the export never names the proxies folder and its frames are identical with and without copies; clearing removes only the copies; a damaged edit record is put back from its backup and reported, and with no backup everything stops and nothing is written over it) | `pytest tests/test_proxies_recovery.py` |
| **Component** (jsdom, clicked) | none | `cutmath.test.ts` (snap points, nearest, the plain-language notes, times) and `component/cutlane.dom.test.tsx` (each button and each key sends the right edit; a refusal shows as an alert; a locked track disables the tools; Alt+arrows nudge), `e2e/cut.spec.ts` (S, Ctrl+Z, Delete, Q, B, dragging a handle and Esc, the locked track, in a real browser engine; the lane is in the accessibility scan as the `cutedit` scene) |
| **Engine** (editing) | none | `test_edit_time_ops.py` (exact time, the sequence's rules, every operation, 600 random edits that must keep the rules and never change what they were given, a check that the edit modules do no floating-point time), `test_editing.py` (a real export of frame-numbered footage proves a split changes nothing seen, a trim shows exactly the frames asked for, a ripple closes up by exactly that many frames, unplaced and orphaned shots are said, one undo and redo covers cuts and grades) | `pytest tests/test_edit_time_ops.py tests/test_editing.py` |
| **Component** (jsdom, clicked) | none | `component/colorstudio.dom.test.tsx`
| **Component** (jsdom, clicked) | none | `component/colorstudio.dom.test.tsx` (scope, sliders, preview of the unsaved grade, LUT refusal, import and cancel, clipping note, errors), `e2e/color.spec.ts` (the same on the harness, keyboard driven; in the accessibility scan). Engine: `test_grading.py` (each number moves a real exported picture the way its name says, the identity round trip stays within a few levels, a real `.cube` through `lut3d`, the preview frame agrees with the exported film, `.cube` refusals), `test_style_dna.py` |
| **Component** (jsdom, clicked) | none | `component/performancedirector.dom.test.tsx`
| **Component** (jsdom, clicked) | none | `component/performancedirector.dom.test.tsx` (draft vs yours, keep/undo/reset, the right path saved per line and per person, directions step up and off, free beat suggestion), `e2e/performance.spec.ts` (the same in a real browser engine on the `acting` and `shotacting` harness scenes; both are also in the accessibility scan) |

| **Component** (jsdom, clicked) | none | `component/keyrows.dom.test.tsx` (the grouped keys: save, Enter, remove, a refused key, never shown in clear) |
| **Integration** | BytePlus queued, sent (HTTP replaced), finished and counted | none |
| **End to end** (Playwright, Edge) | none | `e2e/ux.spec.ts` (no top-bar icon covers the inspector's title at 1100, 1280, 1440 and 1920 px; the rail shows the path and keeps the rest behind More, remembers it, Director Mode shows all; Connections is grouped and its rows keep their shape) |
| **Accessibility** | none | `e2e/a11y.spec.ts` now also scans the Settings screen (44 harness scenes + 1) |
| **Security** | BytePlus: no key, bad references, every error, no key in a message | none |

### Checks outside the test suites

- `python -m tests.speech_check` (in `analysis/`, Windows): measures how well the voice/effects split works on synthesized speech with effects and music at known levels, and prints the numbers quoted in the guide. `test_split_speech` guards them.
- `node scripts/docshots.mjs` regenerates the guide's screenshots from the browser preview; `PF_OUT=<folder> node scripts/docshots.mjs export review settings ...` captures other screens for an audit, and prints any error the page logs. `node scripts/probe.mjs <scene> "<expression>"` measures something in the page (sizes, text) after a scene's clicks. The preview is `npm run dev`, then `http://localhost:1420/?mock`.

### A dress rehearsal on a real project

```
python scripts/rehearse.py "C:\path\to\My Project"
```

Copies a real project (yours is never written to), adds an intro title card, a layer for every lyric line, a travelling shape and a pulsing icon, exports the whole film, and checks that it is as long as the song, has sound and shows every layer; it writes a few frames to look at. It costs nothing and calls no service. It is the closest thing to a real run that needs no account, and it found a real bug the generated tests had missed (an export with about eighty layers failed on Windows because the command line was too long).

### What cannot be tested from the command line

- **The real window.** No automated test clicks through the app. Components are checked as markup and logic; layout, drag and drop on the player, and how it feels are checked by hand.
- **Sound from a real model.** The separator was measured on synthesized speech, not on what a video model makes, and no test spends money. Whether a real take's voice survives the split is learned by splitting a real take once and playing the Preview.
- **Real paid services.** Every provider is a stand-in in tests (a fake that returns a real short clip). That a model accepts a request, and how its output looks, is only learned from real renders; each such failure becomes a regression test (see `test_video_models`).
- **Installers on a clean machine** and the update check on a private repository.

## Security checks

| Check | What it covers | Run |
|---|---|---|
| `pytest -m security` | path traversal through shot ids and file names, zip entries that climb out of their folder, zip bombs, fonts chosen by path, pictures that are not pictures, oversized files, links, SVG entities, text and numbers that could become filter expressions, API keys written into a project, the update URL, clean-up deleting outside the project, and that every action the app shell allows is one the engine knows and every command that takes a project folder checks it is a project | `python -m pytest -m security` |
| `rafter secrets .` | secrets in the repository | `rafter secrets .` |
| `bandit` | Python code, medium severity and up | `python -m bandit -q -r pulseframe_analysis -ll` (in `analysis/`) |
| `pip-audit` | known vulnerabilities in the engine's pinned packages | `python -m pip_audit -r requirements-engine.txt --no-deps --disable-pip` |
| `npm audit` | known vulnerabilities in the screen's packages | `npm audit --omit=dev` |
| `rafter run` | remote SAST and SCA scan; needs `RAFTER_API_KEY` and, for a private repository, `--github-token` | `rafter run` (the deeper `--mode plus` is paid and needs approval) |
| `cargo audit` | known vulnerabilities in the shell's Rust crates | `cargo install cargo-audit`, then `cargo audit` in `src-tauri` |

## Adding a test

- A bug was found: add a test that fails without the fix, in the module for that area, and add the module to `REGRESSION` in `conftest.py` if it is not there. Put the real-world detail (the model, the message) in the test's docstring.
- A feature that draws something: check it on real video (see `test_title_motion.py` and `test_keyframes.py`), not only on the picture it makes.
- A number or name that comes from outside: add it to `test_security.py`.
- A promise to the user: add an `ACCxx` scenario to `test_acceptance.py` and a line to `ACCEPTANCE.md`.


### Security scan with Rafter (2026-10-08)

Installed with `npm install -g @rafter-security/cli`. `rafter -a secrets .` over the repository (respecting `.gitignore`, patterns engine): **no secrets detected**. `--history` needs Rafter's betterleaks engine, which could not be fetched here, so the git history was not scanned. `rafter run` (remote code analysis) needs a `RAFTER_API_KEY` (and a GitHub token for a private repository), neither of which was available, so it was not run. To run it: set `RAFTER_API_KEY`, then `rafter run`.

## Looking at a screen without the desktop app (the screenshot harness)

`docshots.html` and `src/docshots/` render one real screen of the app with made-up data, so a layout can be looked at (and the guide's pictures regenerated) without a project, a key or the desktop shell. Nothing there ships in the app: only `index.html` is built.

```
npm run dev                                     (the preview on http://localhost:1420)
analysis\.venv\Scripts\python src\docshots\make_samples.py     (once: the placeholder pictures and clips)
node scripts/docshots-edge.mjs                  (every scene into docs/img)    node scripts/docshots-edge.mjs review kt   (just those)
http://localhost:1420/docshots.html?scene=review     (the same screen in a browser, to click about in)
```

It needs Edge or Chrome and Node 22 or newer. Each scene is measured and then photographed at exactly its own size (`scripts/docshots-edge.mjs` lists them; `PF_OUT=<folder>` keeps a run out of `docs/img`). To cover a new screen, add a scene to `src/docshots/main.tsx` (and the answers it needs to `mockIPC`), a line to the script, and reference `docs/img/<file>` from the guide. The pictures are made-up scenes, not real project frames.
