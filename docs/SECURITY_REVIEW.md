# Security review: Unified Studio work (2026-11-05)

What was reviewed: everything added since the creative presets (commit 5bff707): compositing (`composite.py`), motion graphics (`motion_templates.py`), video-clip layers (`overlays.py`), the preset setup and "remember the choice" record (`presets.py`),
the Home screen and its sheets, the Guide's new steps, and the Rust door changes. The method is the CWE Top 25 checklist for Python, JavaScript/TypeScript and Rust, walked against the diff, plus a hostile-input test suite and the dependency audit.

## What the new code reaches

| Surface | New code | Where the input comes from |
|---|---|---|
| A program run with arguments | `ffmpeg` for a clip's first-frame picture (`clip_still`) and for the film's overlay pass | A video the person chose, copied into the project; numbers and a parsed colour |
| Files | a chosen video is copied into `assets/overlays/<generated id>.<ext>`; layer pictures are cached under `cache/` | A file dialog, and the project's own `overlays.json` |
| A filter graph | blend modes, colour key, despill, opacity | A blend mode from a fixed list; numbers; a colour parsed to three integers |
| Stored records | `presets/state.json` (`pending`, `setup`, one preset of the person's own) | The Home screen's setup sheet |
| The screen | Home, preset gallery, New film setup, first-launch question | The person; the presets' own list (a file shipped with the app) |

## Walk of the checklist

- **Command injection (CWE-78).** No `shell=True`, `os.system`, `eval`, `exec` or dynamic import was added (searched across the changed engine files). The one new subprocess call is list-form (`clip_still`). Its input file is an absolute path that passed `clip_path` (inside the project, a video extension) so it can never start with `-`; its filter string is built by `clip_filters` from `int`/`float` values and a colour parsed by `_hex` into three integers. A test (`test_the_filters_only_contain_numbers_and_a_parsed_colour`) feeds it a colour with `; movie=/etc/passwd` in it and checks nothing of it reaches the string. A blend mode is looked up in a fixed table and refused otherwise, in both the layer check and the graph builder (`test_a_blend_mode_is_one_of_a_fixed_list...`).
- **Path traversal (CWE-22).** A clip's stored name is generated (`ov_<hex>` plus a lower-cased extension from an allow-list); the chosen file is only ever read and copied. At render time `clip_path` requires the file to be inside the project (`realpath` containment) with a video extension; a project file edited by hand to say `../secret.mp4` or `overlays.json` is refused (`test_a_tampered_project_cannot_make_a_clip_read_a_file_outside_it`).
- **Resource exhaustion (CWE-400).** A clip file is limited to 1 GB and its pixel size to 16,384 on a side; a project holds at most 8 clips and 200 layers; strings are cut to their limits; the preset record keeps at most 5 remembered presets and 100 of the person's own. Fuzzing with 20,000-character strings, deeply nested objects and 2^70 numbers produced only refusals or clean values.
- **Input validation (CWE-20).** Every number goes through one function that refuses text, lists, NaN and now infinity (the fuzz found infinity was clamped but accepted: fixed), then clamps. A layer's shape or icon sent as a list or object used to raise an unhandled error: it is now refused (found by the fuzz, fixed, tested).
- **Deserialization (CWE-502).** JSON only; no pickle, yaml or marshal. The presets file is read with `json`, each field validated by `clean_preset`/`clean_settings` (a preset of the person's own made from the setup sheet goes through the same checks).
- **Cross-site scripting (CWE-79) and code injection (CWE-94) in the screen.** No `innerHTML`, `dangerouslySetInnerHTML`, `document.write`, `eval` or `new Function` was added; text from presets, projects and the engine is rendered by React as text. No `postMessage` handler. The harness reads query parameters (`?many`, `?none`), but only the test harness page does, and only to choose made-up data.
- **Credentials (CWE-798).** `rafter secrets .` reports one made-up hash in the harness (a fixture, as before). Nothing in the new code reads, stores or logs a key. Choosing a preset, starting a film from one, adding a clip, a blend, a key or a motion graphic never calls a provider or spends money (a test reads the Home source for any paid call and finds none).
- **Rust (CWE-119, 704).** No `unsafe`, no truncating `as` cast was added. The door's allow-list of actions gained `set_pending`; the security test that compares the Rust list with the engine's choices passes. Recent films now also pass on the film's frame shape, read from its own file.
- **Information disclosure.** An unexpected engine failure used to show a Python error name (and sometimes a file path of ours) on screen; the engine now says "One of the values sent was not in a form FilmCrafter can use" and logs the technical text to stderr, and the screen turns any remaining Python error name into a plain sentence and logs it to the console. The test `test_fuzz_doors.py` checks 30 doors for this.
- **Dependencies (CWE-1104).** No dependency was added or changed. `npm audit --omit=dev`: no vulnerabilities. `cargo audit` and `pip-audit` are not installed on this machine, so those two were not run (a place to look at next).

## Not covered

- `rafter run` (remote analysis) could not be used: the account's allowance for the period is used up (1 of 1). The review above is the manual walk plus the tests.
- A hostile **video file** is read by `ffmpeg`, a large and complex program with a history of its own vulnerabilities. The app mitigates what it can (file size and dimension limits, a time limit on the first-frame picture, only the formats on the allow-list) but cannot make ffmpeg itself safe: keep the bundled ffmpeg up to date, and treat a clip from a stranger like any download.
- The installed app on a second computer, and a real camera's footage, were not tried.
