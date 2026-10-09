# Acceptance: what PULSEFRAME promises

Each requirement is a promise to the people who use the app, with the scenario that checks it. The scenarios are in `analysis/tests/test_acceptance.py` (run with `python -m pytest -m acceptance`) and use the real engine and real ffmpeg, with the paid services stood in for.

| ID | Promise | Checked by |
|---|---|---|
| **REQ-01** | Everything that is free works with no internet and never calls a service: my own clips and pictures, inserted frames, layers (text, shapes, icons, keyframes), and the export. | `test_ACC01_…` (the network is switched off for the whole scenario) |
| **REQ-02** | Nothing is sent to a paid service until I have confirmed the price. A shot I have not described is never sent. A refused request sends nothing and charges nothing. | `test_ACC02_…`, `test_refgen`, `test_refgen_cards`, `test_golden` |
| **REQ-03** | Every render is kept as another version. A new render never replaces the take I chose. | `test_ACC03_…` |
| **REQ-04** | The film stays in step with the song. Inserting or removing a frame never moves the shots after it, and removing a frame gives the time back. | `test_ACC04_…`, `test_customframe` |
| **REQ-05** | Cleaning up is a step I can undo. Files go to a trash folder in the project; only emptying the trash deletes. | `test_ACC05_…`, `test_cleanup` |
| **REQ-06** | The film is always as long as the song, even before anything is rendered (slates stand in), so I can check the timing before I spend. | `test_ACC06_…`, `test_pipeline` |
| **REQ-07** | When something cannot be done I am told in one plain sentence, never a crash or a technical class name. | `test_ACC07_…`, `test_crash_report` |
| **REQ-08** | A whole song becomes a finished film: listening, a shot plan, rendered takes, my own clips, layers, export; the exported file has the song's length, its sound and the right things on screen at the right moments. | `test_e2e_journey` |
| **REQ-09** | The Golden Path holds: free steps come first, paid steps are marked, and the spend is shown against the budget. | `test_golden`, `src/__tests__/golden.test.ts` |
| **REQ-10** | On-screen text, shapes and icons are drawn exactly as I set them (position, size, colour, rotation, movement) in the export, and the player shows the same. | `test_overlays`, `test_shapes`, `test_keyframes`, `test_title_motion`; `overlayMotion.test.ts`, `overlayKeys.test.ts` |
| **REQ-11** | A preview of a few seconds is quick, small and honest: it is the part asked for, with its layers and the song's sound, and it never replaces or disturbs a full export. | `test_pipeline` (preview), `test_title_motion` |
| **REQ-12** | Colour match never changes my takes: it is off until I turn it on, leaves shots that already match alone, and the export shows the difference only while it is on. | `test_colormatch` |
| **REQ-13** | The sound a video model made is mine to keep, trim or drop, shot by shot, without paying to render again: kept for one shot, split into voices and effects, deleted, restored; no render is queued and the take file is unchanged. | `test_ACC13_…`, `test_shotsound`, `test_e2e_sound` |
| **REQ-14** | My song is never changed behind my back: untouched, the film plays the song as it is; after I change a shot and go back, it is the same again. | `test_ACC14_…`, `test_regressions_sound` |
| **REQ-15** | A change to my layers can be taken back and brought forward again (adding, editing, removing, lyric layers, templates and styles). | `test_ACC15_…`, `test_layer_undo` |
| **REQ-16** | I am told how loud my film is, and never given a made-up number: a film with sound gets a reading, one without gets none. | `test_ACC16_…`, `test_shotsound_unit` (the reading) |
| **REQ-17** | A layer I move, trim or hide on the timeline is exactly what the export shows: moved where I put it, hidden nowhere, and still in the project so I can bring it back. | `test_ACC17_…`, `test_security_timeline`; `lanes.test.tsx` |
| **REQ-18** | A transition never changes how long the film is, and each shot enters the way I chose, for as long as I chose. | `test_ACC18_…`, `test_transitions` (every kind, on real clips) |
| **REQ-19** | The dance-ready check, the sound check and the camera suggestions are free: they run on my computer and use no network. | `test_ACC19_…`, `test_dance`, `test_lipsync_timing`, `test_looks` |

Not yet covered by an automated scenario (checked by hand): the look and feel of the screens, dragging on the player, installer behaviour on a clean machine, and the quality of what real models return.
