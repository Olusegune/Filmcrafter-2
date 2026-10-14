# Phase 0 implementation report: stability, safety and data protection

Branch `phase-0-stability` (local only). **Nothing was pushed, released, installed or built into an installer. No paid provider call was made. No real film project was opened or modified** (every test uses temporary folders and faked providers). No API key was printed, logged or committed.

Version label in the CHANGELOG: 0.24.0 (unreleased). The version numbers in `package.json`, `Cargo.toml` and `tauri.conf.json` were not changed: bumping is a release step.

## 1. What was done, against the brief

| Brief item | Done | Where | Tested by |
|---|---|---|---|
| B1 Engine-level confirmation for design / keep / clone / speak / preview; consent separate from spending; unknown cost must be accepted | Yes | `cast_voice.py` (`_paid`), `paidops.require_authorised` | `test_voice_paid_safety.py` |
| B2 Voice ledger `voice/ledger.json` (estimate vs reported kept apart, no credentials, bounded size) | Yes | `paidops.Ledger` | same |
| B3 Safe retry / no duplicate charge; uncertain outcomes resolved by the person | Yes | `paidops`, `cast_voice._paid`, usage panel | same |
| B4 One shared paid-operation policy | Yes | `paidops.py`, `docs/PAID_OPERATIONS.md` | same |
| B5 Screens: provider, cost or "unknown", voice slot, usage line, limit, unresolved list | Yes | `voiceUsage.ts`, `VoiceUsagePanel.tsx`, `CastVoices.tsx`, `LineStudio.tsx` | `voiceusage.test.ts`; looked at in the browser harness |
| C1 Shared JSON I/O (absent / valid / damaged / unreadable / unsupported; preserve damaged bytes; atomic; locked) | Yes | `safeio.py` | `test_safeio.py` |
| C2 Adopt it for voice.json, cast.json, film.json (incrementally) | Yes: voice.json, cast.json, the ledger, film.json and every record `story.py` reads/writes through `_read/_write`. Other modules keep their own readers (listed in 4). | `voiceover.py`, `cast_voice.py`, `story.py` | `test_voice_paid_safety.py`, `test_filmbackup.py`, `test_story*.py` |
| C3 Film-level metadata backups with a tested restore | Yes | `filmbackup.py`, shell `film_backup`, Backups sheet, snapshot on open | `test_filmbackup.py` |
| D1 Narrow the asset scope without breaking external-drive films | Yes in config and code; **not proven on a real install** (see 3) | `tauri.conf.json`, `lib.rs` `allow_media` | Rust test reads the config |
| D2 Sample download validation | Yes (host list was already narrow; added content-type, size from header, real audio check, atomic write) | `cast_voice.sample` | `test_cast_voice.py` |
| D3 `.filmpack` extraction limits | Yes | `packer._check_archive` | `test_film_pack.py` |
| E1 Update check honesty | Check is off, Settings says so; repository name corrected | `updates.py`, `Updates.tsx` | `test_updates.py`, `ui.test.tsx` |
| E2 Voice docs accuracy | Yes | `docs/GETTING_STARTED.md`, `HANDOVER.md`, `QA.md` | read-through |
| E3 TAGGED duplication | Engine is the one list; screen reads `models[].tagged` | `cast_voice.py`, `LineStudio.tsx` | `voice.test.ts`, `test_cast_voice.py` |
| E4 Obsolete timeline CSS rule | Removed (`lanes.css:2`; the working rule in `film.css` stays) | `lanes.css` | tsc/vitest; **layout not re-walked in the installed app** |
| E5 Speech terminology | The user-visible "song's vocal" in the shot changes list is now "voice or sung line" | `changes.py`, `devmock.ts` | `test_changes.py`. Other internal wording (`render.py` labels, `lipsync_check.py`) left; see 4 |
| E6 `.gitattributes` | Added (conservative: `text=auto`, binaries marked) | `.gitattributes` | none needed |
| F Behavioural tests, regression, smoke checklist | Yes | this file, section 5 | section 2 |
| Forward compatibility for Sound & Music | Designed for; nothing built | `docs/PAID_OPERATIONS.md` section "Adding a new paid operation" | n/a |

## 2. Test results

Filled in from the final run on this branch (Windows 11, project `.venv`, Python 3.11):

- Engine suite: see the "Final regression" block at the end of this file.
- Focused new suites: `test_voice_paid_safety.py` 33, `test_safeio.py` ~26, `test_render_lock.py`, `test_filmbackup.py` 10, `test_film_pack.py` 13 (7 new), `test_cast_voice.py` 26, `test_updates.py` 9.
- Screen suite (vitest): 514 passed before the last small edits; re-run in the final block.
- `tsc --noEmit`, `cargo test --lib` (9), `rafter secrets`, `npm audit`: final block.
- Real, non-fake checks: the six-process write tests and the lock race (a real Windows behaviour); the usage panel was loaded in the browser harness with a mocked ledger (screenshot looked right: usage line, the "not sure whether this was charged" box with both buttons, a collapsed details list).

## 3. What was NOT verified

- **The installed Windows app.** Nothing was built or installed. Everything in the checklist in section 5 is for a person to do.
- **The narrowed asset scope on a real install.** The configuration is narrowed and opened film folders are added at run time (`allow_media`); that code compiles and the config is tested, but whether pictures and audio of a film that lives on another drive or the Desktop still display is proven only by the smoke test. If they do not, the single-line revert is `$HOME/**` back in `tauri.conf.json` (documented in the checklist). The file picker adds chosen files by itself (the dialog plugin does this; I read its source, I did not run it).
- **Any real ElevenLabs behaviour** for the new code paths (no paid call was made): the confirmation flow, the ledger entries, the usage line, a limit, the uncertain handling and resolving. They are covered with faked HTTP replies only. The real ElevenLabs response fields that report charges (`character-cost` header) are read as before; whether a plan reports it for every call is unknown, which is why the app labels amounts "reported" or "estimated".
- Cloning, keeping a designed voice, the microphone recorder, 125%/150% scaling, and **real lip-sync quality** remain unverified in the real app (unchanged from before Phase 0). Edit mode is not covered by the screenshot sweep.
- The new Backups section was not walked through in the running app (the screens are type-checked and source-tested; the engine side is behaviour-tested).

## 4. Remaining risks and deliberate limits

- Only `story.py`, voice and cast code use the safe I/O layer so far. Other modules (`bible.py`, `shots.py`, `render.py` Store, `planio.py`, ...) still use their own readers; a damaged `bible.json` or `shots.json` can still be treated as missing by those modules. The film backup now holds copies of all of them, which is the safety net until they are adopted (a Phase 1 item).
- The render queue's own state (`jobs.json`) has its own protection (job state machine, merge-save with a lock) and was left alone, except for the lock race fix.
- The ledger covers ElevenLabs voice operations only. Picture and video generation spend is covered by the render engine's own states/budget guard, not the ledger; a unified view is future work.
- The usage line can only show what ElevenLabs reports. Without `user_read` on the key, the plan line stays blank (unchanged).
- A sample or voice slot count shown before confirming comes from the plan read; if the plan could not be read the screen says "one voice slot of your ElevenLabs plan" rather than a number.
- Update checking is off. Re-enabling is a one-line change in two places once a public releases page exists (a test keeps the two in step).
- Internal wording about singing remains in `render.py` and `lipsync_check.py` (see the independent review, section on audio). Not changed: it is not user-facing except one label under a shot's request, which would be the next step with the speech facade.

## 5. Windows smoke-test checklist (for you, on the installed or dev app)

Do these on a **copy** of a film (copy the folder first). Steps marked **[spends]** use your ElevenLabs plan: do them only if you choose to, and look at the price the app shows first. All others are free.

Free:
1. Open the app; open a film from `Documents\FilmCrafter`. Pictures and video thumbnails show.
2. Copy that film folder to the Desktop (or another drive) and open the copy. **Pictures and play-backs must still show** (this is the asset-scope check). If they are blank, tell me: the fix is one line.
3. Open **Voiceover**. Under "Voices for your characters" there is no usage line yet on a fresh film (it appears after the first paid action).
4. Click **Give a voice… → Design one**, type a description, press **Hear a few options…**: a question appears naming ElevenLabs, saying the cost is not published and asking you to accept. **Press No/Cancel.** Nothing happens, no usage line appears.
5. Click **Hear it** on a voice: a question appears with the character count. Cancel.
6. **Backups:** menu File → Backups (with the film open on its home screen). A section "The film's records" lists a backup made when the film opened. Change a character's name somewhere, reopen the film: a second backup appears. Restore the older one: the name goes back, a backup "Before restore" appears.
7. Settings → Updates says checking is off in this version, with no button that contacts anything.
8. Open a `.filmpack` you made earlier (File → Open). It unpacks to a new folder as before.
9. Damaged-file test on a **copy**: close the app, open the copy's `voice\voice.json` in Notepad, delete the last half of the text, save, reopen the film and go to Voiceover. The app should say that file is damaged and stop voice work on that film (nothing is overwritten); a `voice.json.corrupt-…` copy appears beside it. If a good `voice.json.bak` exists it is put back automatically and used instead, with a note.

Spends **[spends]** (small: a 20-character line is about 20 credits):
10. **Speak it** on one short line: a question appears first with Provider / Cost / Voice slot. Confirm. The line is attached. A usage line appears ("ElevenLabs credits reported" or "has not reported amounts… estimated"). Speak the same line again: free, no question.
11. Open **Usage details and limit**, set a limit of 5, then try to speak a different 20-character line: it is refused before anything is sent. Clear the limit.
12. Pull out the network cable (or turn off Wi-Fi) and press Speak it: nothing is charged and the message says so. (No entry should say "not sure".)

## 6. Phase 1 readiness recommendation

Ready to start Phase 1 once you have (a) read this report, (b) done checklist steps 1–9 on the app built from this branch (free), and (c) decided whether to approve the small paid steps 10–12. Recommended order for Phase 1: adopt `safeio` in the remaining record-keepers (bible, shots, planio) with a damaged-file test each; move the render `Store` onto the same layer; then the Sound & Music Bible, which can reuse the ledger and the backup as they are (see `docs/PAID_OPERATIONS.md`). No Phase 1 work should begin on this branch before it is reviewed and merged.

Needs your decision: (1) approve a push of `phase-0-stability` and a version bump/release (I did neither); (2) whether to run the small paid steps 10–12; (3) when to create a public releases page so update checking can be turned on.

## Final regression

Run on the final code of this branch (Windows 11, project `.venv`):

- Engine (`pytest`, whole suite): **1855 passed, 8 skipped**, 0 failed (6 min 43 s). The skipped ones are the existing platform/optional-tool skips. (An earlier run found one failure, a repository rule against a temp-file naming pattern that my new `filmbackup.py` tripped; fixed and re-run.)
- Screens (`vitest`): **514 passed**, 61 files. `tsc --noEmit`: clean.
- Shell (`cargo test --lib`): **9 passed**.
- `rafter secrets .`: no secrets detected.
- `npm audit`: **0 vulnerabilities in what ships** (`--omit=dev`). The full audit lists 4 in development tools only (vitest/tinypool/source-map-js); fixing them needs a major test-tool upgrade, which is outside Phase 0 and was not done.
- Not run: the screenshot sweep (`docshots`) and any installer build, because nothing was to be released. Edit mode is not in the sweep.
