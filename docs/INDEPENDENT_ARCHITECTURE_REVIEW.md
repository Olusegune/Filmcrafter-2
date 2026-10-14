# FilmCrafter: independent architectural, security and readiness review

- **Version reviewed:** 0.23.4, commit `8a8d0be` (verified: `HEAD` = `origin/main` = `8a8d0be`, working tree clean, 83 engine modules, 117 engine test files, 61 screen test files).
- **Date:** 2026-10-14.
- **Method:** read the code, ran the free keyless checks, made free read-only lookups (public GitHub API, public provider documentation). **No code was changed. No paid call was made. No key was used or printed. Nothing was pushed.** This file is the only thing added to the repository and it is uncommitted.
- **Disclosure:** the reviewer is the same assistant that wrote most of the voice, timeline and ElevenLabs code in versions 0.19 to 0.23. This is a genuine attempt at a hard look, but it is a self-review. An independent reviewer (the GPT agent) should treat Sections D and E as claims to re-check, not conclusions.

## How to read the evidence labels

| Label | Meaning |
|---|---|
| **V-code** | Verified by reading the source (file and line given). |
| **V-test** | Verified by running an automated test in this review. |
| **V-doc** | Verified against the provider's current public documentation (fetched 2026-10-14). |
| **V-live** | Verified by a real provider call. Earlier sessions made small ElevenLabs calls (listed in `CHANGELOG.md` 0.22.0). **This review made none.** |
| **V-app** | Verified in the installed Windows app. **Nothing in this review was.** |
| **Reported** | Stated in the handover, not independently verified here. |
| **Suspected** | A plausible risk from reading the code; not demonstrated. |

## Checks run in this review (all free, all keyless)

| Check | Result |
|---|---|
| Engine tests (`pytest`, fresh venv run at `8a8d0be`) | **1,772 passed, 8 skipped** (V-test), matching the handover |
| Screen tests (`vitest`) | **503 passed** (V-test) |
| Rust shell tests (`cargo test`) | **8 passed** (V-test) |
| Type check (`tsc --noEmit`) | clean (V-test) |
| `rafter secrets .` | no secrets (V-test) |
| `npm audit --omit=dev` | 0 vulnerabilities (V-test) |
| The 8 skips | explained and benign: symlink creation, optional OTIO adapters, optional Demucs, Windows-only tests, two environment guards (V-code, `analysis/tests/*`) |

**Not run (limitations):** the installed Windows app (no V-app evidence anywhere in this review); the screen sweep (`docshots-edge.mjs`, which does not open Edit mode anyway, see E3); `pip-audit` and `cargo audit` (not installed here); any 125% / 150% display-scaling test; any real provider call; the macOS build. The repository `Olusegune/FilmCrafter` is **private**: an unauthenticated request to the GitHub API returns 404 (V-live, free). Any outside reviewer needs an invitation or the source zip.

---

## A. Executive assessment

**Condition: sound core, honest documentation, a few real gaps at the edges. Safe to keep building on; not yet safe to claim "finished voice and lip-sync".**

**Strengths (evidence in brackets)**
1. **The render engine is genuinely robust.** A job state machine (`queued, submitting, submitted, uncertain`), crash recovery that never re-sends a possibly-paid job (`render.py:2126-2149`), a pause when a provider is out of credits (`render.py:2179-2185`), a file lock plus merge-save so concurrent writers do not undo each other (`render.py:1639-1670`), and an engine-level budget guard (`routing.py:203-219`). This is better than most hobby-grade pipelines.
2. **The source-of-truth design is correct and consistent.** One film folder, a derived render project, atomic writes in 44 modules, archive-never-delete (`_removed`), and a deliberate separation between the written screenplay and per-shot dialogue.
3. **Credentials are handled well.** Keys live in the Windows Credential Manager, are read per call, are passed to the child process by environment variable, are used only as request headers, and are **never returned to the screens** (`lib.rs:364` returns booleans only; there is no `get_key` command). `jobs.json` stores request payloads without headers.
4. **The web layer is hardened.** `script-src 'self'`, no `dangerouslySetInnerHTML`, `innerHTML =`, `eval` or `new Function` in any screen source (V-code, grep), `object-src 'none'`, `form-action 'none'` (`tauri.conf.json:43-56`).
5. **Documentation is unusually honest** about what is unverified (QA, NEXT_PHASE, the lip-sync section).
6. **Dependencies are pinned** (`requirements-engine.txt`: 10 packages, all `==`), and `npm audit` is clean.

**Weaknesses**
1. **Spending safety is uneven.** Renders have a state machine and a budget guard; voice calls have neither a ledger nor engine-side confirmation for design, design-save and cloning (D2, D3).
2. **"Out of date" is tracked for keyframes but not for voices** (C3, D4): replace a recording and the video take is not flagged.
3. **Lip-sync is unproven** (Section 5). The request is built correctly; whether the model honours it is unknown, and the provider's own documentation does not promise it.
4. **The in-app update check cannot work** (D5), the first-run runtime download is unverified (D6), and installers are unsigned.
5. **Frontend tests prove wiring, not behaviour** (E1): no DOM test environment, no interaction tests.
6. **Legacy music-video concepts still run through the film path** (G3), and the layout arithmetic for the timeline is a fragile set of duplicated constants (F1).

**Readiness for expansion:** the architecture can carry SFX, music, selective regeneration and a model registry **as extensions**, without a new database or a rewrite. The two prerequisites are small and should come first: close the spending gaps and add a "made from" record to voice assets. Detail in Sections C, F and G.

---

## B. Verified feature inventory

| Feature | Status | Evidence | Recommended action |
|---|---|---|---|
| Film folder as source of truth, derived `render/` | Implemented | `story.py:402,463`; `make.sync`; `docs/` | Keep |
| `.filmpack` pack / unpack, zip-slip guard | Implemented | `packer.py:127-155`; `test_film_pack.py:73` | Keep; add size cap (D7) |
| Render job queue with crash recovery | Implemented, **V-test** | `render.py:1639,2126`; many `test_render*` | Keep |
| Engine-level budget guard | Partial | `routing.py:203-219` returns early when no budget is set (`:212`) | Improve (D3) |
| ElevenLabs: library, set, clear | Implemented, **V-live** (earlier session) | `cast_voice.py:142-240` | Keep |
| ElevenLabs: design | Implemented, **V-live** (3 previews returned) | `cast_voice.py:243-273` | Gate in engine (D2) |
| ElevenLabs: keep a designed voice | Implemented, **not tried live** | `cast_voice.py:276-285` | Gate (D2); try once |
| ElevenLabs: clone | Implemented, **not tried live** | `cast_voice.py:288-316` | Gate (D2); try once |
| ElevenLabs: speak, takes, switch takes | Implemented, **V-live** | `cast_voice.py:410-465` | Keep; fix F3 |
| Direction `[tags]` kept out of picture/video prompts | Implemented, **V-test** | `test_cast_voice.py` (dialogue untouched test) | Keep |
| Voice lanes / Voices band / line editor | Implemented, V-test (structure), **not V-app** | `VoiceLanes.tsx`, `LineStudio.tsx`, `ShotVoice.tsx` | Add behaviour tests (E2) |
| In-app recorder | Implemented, **not tried with a real microphone** | `VoiceRecorder.tsx`, `lib.rs:1209` | Try in the installed app |
| Lip-sync via reference audio (Seedance 2) | **Unverified** | request built at `render.py` (`compile_request`, `audio_first:2505`); Kie docs do not promise it (V-doc) | Test once (Section 5) |
| Lip-sync pass on a finished take | Implemented, **not run** | `render.py:2000-2029`; lite/basic mode chosen by shot | Run if the first test drifts |
| Per-shot sound layers (song, model sound, voice, effects) | Implemented | `shotsound.py:1-25,492` | Reuse for SFX (Section 6) |
| Voices laid on the film at export | Implemented | `export.py:347-353`, `voiceover.py:478-507` | Keep; add ducking (Section 6) |
| AI sound effects / ambience / score | **Missing** | no module; contract `sound` is an unused empty string (`shots.py:148,360`) | Build as extension (Section 6) |
| Dependency / staleness tracking | Partial | `golden.py:37` (keyframe only); `changes.py:36-60` (request diff) | Extend (C3) |
| Dynamic model discovery | Partial | Kie: scrape of `docs.kie.ai/llms.txt` (`render.py:244`); fal: API; Google / OpenAI / ElevenLabs: static lists | Extend (Section 7) |
| In-app update check | **Broken by configuration** | `updates.py:20` | Fix (D5) |
| Code signing | Optional, not in use | `tauri.conf.json` `signCommand`; `build.yml:167-190` | Needs a certificate |
| Film strip / Edit timeline modes | Implemented | `Studio.tsx:1164-1171` | Keep; simplify arithmetic (F1) |
| Automatic backup of film data | **Missing** (only the timeline project is backed up) | `packer.py` backup needs `project.json`; menu text "Backups are made of the timeline" | Build (D11) |

---

## C. Architectural findings

### C1. Layers and responsibilities: appropriate (Retain)

React calls the shell only through `src/api.ts`; the shell (`lib.rs`, 93 commands) validates and forwards to the Python engine as a child process; the engine reads and writes the film folder. Responsibilities are separated cleanly. The `ACTIONS` allow-list per shell command, checked against the engine's argparse choices by `test_security.py`, is a good pattern that the new commands follow (`film_cast_voice:1251` has 13 actions).

**Recommendation: retain.** No rewrite is justified.

### C2. Identity: people are keyed by display name (Extend)

A person's voice and recordings are keyed by `key_of(name)` (`voiceover.py:77-80`, lower-case slug), and `cast.json` uses the same key. The bible gives characters stable ids (`bible.py:123-128`, `c_<slug>`), but they are also derived from the name at creation, and the voice system does not use them. **Confirmed:** identity is the name. **Suspected impact:** renaming a character in the bible orphans their recordings and their ElevenLabs voice. Not demonstrated by a test.

**Recommendation (small):** store the bible id alongside the key in `cast.json` and `voice.json` entries, and resolve through it, with the slug as a fallback. No migration needed: old files keep working.

### C3. The "Production Asset Graph": do not build a new one; extend what exists (Extend, small)

**What already exists (V-code):**
- Every shot contract carries `story_version`, `locks`, `status`, `edited`, `reference_assets` and `sound` (sample contract from the user's film pack; `shots.py:143-148`).
- Every render job stores its **full request** (`payload`), the **keyframe it was made from** (`keyframe_ref`, `render.py:2376`), and the model.
- `changes.since_last_take` (`changes.py:70-82`) compares a take's stored request with the request that would be sent now and lists what changed, sentence by sentence. This is already a working "what is out of date and why" engine for video.
- `golden.is_stale` (`golden.py:37-62`) flags a take made from a different keyframe than the one approved now.
- Spoken takes keep a sidecar with the exact words, model and voice (`cast_voice.py` `_sidecar`).

**What is missing (confirmed):**
1. Dialogue lines have **no stable id and no hash**: `{speaker, line, paren}` only (V-code, sample contract). So a voice take cannot know whether its line has since changed.
2. A video take does **not record which voice clip it used**, and `changes.compare` only tests whether audio is present, not whether it changed, and its message still says "The song's vocal…" (`changes.py:49-52`). Replacing a recording therefore does **not** mark the shot's video as out of date. **Confirmed defect (D4).**
3. Nothing links a recording back to the line it voices, or a caption to the take it follows.

**Smallest extension that works (no database):** add a `made_from` map to each generated or attached artefact, recording the **fingerprints of its inputs**, and one function that compares those fingerprints with the current ones.

```
voice.json entry   : made_from { line: sha1(speaker|line|paren), voice: sha1(recording file), model, voice_id }
spoken take sidecar: (already has text, model, voice_id) + line_hash
video job          : made_from { keyframe: ref (exists), voice: sha1(clip), prompt: sha1, duration }
captions / exports : made_from { dialogue: sha1 of the shot's lines, take: job id }
stale_reasons(d, shot) -> [{asset, reason, regenerates: "voice"|"video"|"caption"}]   # one function, reuse golden.is_stale and changes.compare
```

This generalises the pattern the code already uses (`keyframe_ref`). It gives selective regeneration for free: because every artefact knows its inputs, the app can say "Lila's line changed, so her voice take and this shot's video are out of date; the keyframe and Chloe's voice are not", and the user can regenerate only those. Approved or locked assets are protected because the stale check never edits anything.

**Verdict on the Production Asset Graph: do not implement it as a separate subsystem.** Extend `made_from` and `stale_reasons` instead.

### C4. Recovery and interrupted operations (Extend)

- **Renders:** excellent (A1).
- **Voice calls:** none of that machinery. `_speak_to` retries on timeouts and 5xx up to three times (`cast_voice.py:366-381`); there is no `uncertain` state and no ledger (D4b). An interrupted write is safe (`.part` file then `os.replace`, `:382-385`), but an interrupted *charge* is not recorded.
- **Film data:** atomic writes everywhere important (44 modules use `os.replace`), but 56 modules carry their own copy of a `_read` that turns a corrupted file into "empty" without a word (D11).

### C5. Compatibility and migration (Retain)

Files carry `schema` fields; old `.pulse` files and render projects still open (tests exist). New voice files are additive. No migration is needed for the recommendations here.

---

## D. Security and reliability findings

Severity reflects likelihood × impact for this app (single user, local, user-supplied keys). **Confirmed** = shown in code or by a test; **Suspected** = plausible, not demonstrated.

### D1. Broad asset-protocol scope plus `connect-src asset:` (Medium, confirmed config, exploit requires script execution)
- **Where:** `src-tauri/tauri.conf.json:44-63`. `assetProtocol.scope` = `$DOCUMENT/**` and `$HOME/**`; `connect-src` includes `asset: http://asset.localhost` (added in 0.19.0 so the waveform can `fetch` local audio).
- **Impact:** any script running in the webview could read any file under the user's profile (documents, `.ssh`, browser profiles, `~/.filmcrafter`). Before 0.19.0 those files could only be used as media sources; now they can be read as bytes.
- **Exploitability:** low today. `script-src 'self'`; no HTML injection sinks anywhere in the screens (V-code); user text (titles, names, dialogue) is rendered through React, which escapes. Exfiltration is further limited because `connect-src` allows no remote host, and the only outward channels are IPC commands. One of those, `film_cast_voice` `clone` (`cast_voice.py:288-316`), accepts arbitrary file paths with audio extensions and uploads them to ElevenLabs. So this is defence-in-depth, not an open hole.
- **Remediation:** narrow the static scope to `$DOCUMENT/FilmCrafter/**` and `$HOME/.filmcrafter/**`, and allow other folders at run time when a film is opened from elsewhere. Tauri exposes `asset_protocol_scope()` (`tauri-2.11.6/src/lib.rs:761`, present in 2.12.1 too, V-code), whose `allow_directory(dir, true)` can be called from `film_dir`/`project_dir` when a film is opened. **Side benefit (suspected):** today a film on another drive (`D:\Films\...`) cannot show pictures, because the scope covers only `$DOCUMENT` and `$HOME`; verify before relying on this.
- **Also (Low):** `style-src 'unsafe-inline'` (`tauri.conf.json:48`). Leave unless a refactor removes inline styles.
- **Confidence:** high on configuration; moderate on real-world risk.

### D2. Engine does not enforce confirmation for voice design, keeping a designed voice, or cloning (Medium, confirmed)
- **Where:** `cast_voice.py:243` (`design`), `:276` (`design_save`), `:288` (`clone`). Only `speak` (`:418`) and `preview` (`:477`) check `confirmed is True`; `clone` checks only `consent` (`:291`).
- **Documentation mismatch:** the module docstring (`:8`) says "Nothing is spent unless the call says `confirmed: true`". That is not true of the three above. A future reader or reviewer will assume it is.
- **UI today:** design asks first (`CastVoices.tsx:157`), but keeping a designed voice (`:160`, which takes a plan voice slot) and cloning (`:162`) ask nothing beyond a consent tick.
- **Impact:** uses plan characters or a voice slot without an explicit yes at engine level. Exploitability needs a UI bug or compromised webview; the realistic risk is an accidental double action.
- **Remediation:** require `confirmed: true` in all three, make the UI send it after the existing asks (add a short "this uses one of your N voice slots" confirm to keep and clone), and correct the docstring. Add three tests mirroring the existing `speak` test.

### D3. Spend accounting is incomplete (Medium, confirmed)
- **Where:** `routing.py:212` returns without any cap when `budget_usd` is unset (the default: `settings()`, `:98-102`); `budget.py:35-57` counts only render jobs and counts OpenAI and Google as **counts, not dollars** (`:50-53`); ElevenLabs is outside any ledger.
- **Mitigation present:** unknown prices use a deliberately high fallback in the guard (`routing.py:168-176`, V-code), so the guard errs conservative.
- **Impact:** a user who never sets a budget has no engine-side cap; voice spending is invisible to the "spent so far" total.
- **Remediation:** an append-only `voice/ledger.json` (`when, action, characters, credits, outcome`) and a single "project spend" that includes it; prompt once for a budget on first paid action. Small.

### D4. ElevenLabs retries could double-charge on an ambiguous failure (Medium, suspected)
- **Where:** `cast_voice.py:366-381`. Retries on connection errors and on 429/500/502/503.
- **Why it matters:** a timeout after the server processed the request is retried, and ElevenLabs may bill both. The render path treats the same situation as `uncertain` and never re-sends blindly (`render.py:2144-2149, 2191-2196`).
- **Remediation:** mirror that rule: retry only on responses that prove nothing was accepted (429, connection refused before send); on timeout or 5xx, record `uncertain` in the ledger and ask. Not verified against ElevenLabs' billing behaviour.

### D4b. A replaced recording does not flag the video take as stale (Medium, confirmed)
See C3. `changes.py:49-52` and `golden.py:37`. Recommended fix is the `made_from` extension. This is the dependency-tracking gap in its most concrete form: it can lead to paying to keep a video that no longer matches its voice, or, worse, to believing a take matches when it does not.

### D5. The update check cannot work (Medium for product readiness, confirmed)
- **Where:** `updates.py:20-21` sets `REPO = "Olusegune/FilmCrafter-Music-Video-Maker"`. Both that repository and `Olusegune/FilmCrafter` return **404** to an unauthenticated GitHub API request (V-live, free): the first does not exist or is private; the second is private.
- **Impact:** "Is there a newer FilmCrafter?" never finds one. There is also no updater plugin (`Cargo.toml` has none) and no signature verification, so the app can only *tell* users about a release, never fetch one.
- **Remediation:** decide where releases live (a small public `FilmCrafter-releases` repo or a project site), set `REPO`/`PAGE`, and plan signing (Section 7). Until then the pill should be hidden rather than silently useless.

### D6. First-run runtime download is unverified (Medium-Low, confirmed)
- **Where:** `lib.rs:290-291` (`PY_EMBED` from python.org, `GET_PIP` from bootstrap.pypa.io), fetched with `curl.exe` at `:333,346`; macOS asks the GitHub API for the "latest" python-build-standalone with a fallback (`:277-290`). No checksum or signature is checked (the only checksum language in the file concerns ComfyUI, `:1124`).
- **Impact:** supply-chain exposure at first launch (TLS protects transport, not authenticity). Pip then installs pinned versions, but without `--require-hashes`.
- **Remediation:** pin SHA-256 for the embed zip and `get-pip.py`; or bundle the Python runtime in the installer (removes the network step and the failure mode where first launch needs internet).

### D7. `.filmpack` extraction has no total-size or entry cap (Low, confirmed)
`packer.py:140-151` totals the sizes only for the progress bar. Zip-slip is guarded and tested (`test_film_pack.py:73-81`). A hostile or corrupt pack could fill the disk. **Remediation:** refuse packs over a sane total (for example 20 GB) or entry count.

### D8. `save_voice_take` (Informational; adequate)
`lib.rs:1202-1226`: the raw body is accepted only if it is at most 64 MB and begins `RIFF…WAVE`; it is written under `~/.filmcrafter/incoming` with a name the shell makes (no path from the screen), and files older than a day are cleared. Header-only validation is acceptable because the engine re-decodes every recording when it is imported (`voiceover.probe:119-140`). **No action required**; an optional stricter `fmt`/`data` chunk check would be cheap.

### D9. `cast_voice.sample` SSRF controls (Informational; verified, one small gap)
`cast_voice.py:159-205`. Controls present and unit-tested: https only, no userinfo, default port only, a host allow-list (`elevenlabs.io` and subdomains, or `storage.googleapis.com` under `/eleven-`), `allow_redirects=False`, a 3 MB cap, and the API key attached only for elevenlabs.io hosts. **Small gaps:** (1) the allow-list admits *any* `*.elevenlabs.io` subdomain and would send the key to it; narrowing to the known hosts (`api.elevenlabs.io`, `api.us.elevenlabs.io`) is cheap. (2) The body is not checked to be audio before it is kept as `.mp3`; a short magic-byte sniff, or the existing `voiceover.probe`, would close that. Neither is exploitable as far as the code shows.

### D10. Voice cloning handling (Low, confirmed)
`cast_voice.py:288-316`: consent flag enforced in the engine; extension and 30 MB checks; up to 5 files; files opened and closed in `try/finally`. Samples are uploaded as-is and not kept by the app (the voice lives at ElevenLabs). No local storage of the sensitive recordings beyond the user's own originals. Gap: no record that consent was given (a `clone` entry in the ledger with the consent timestamp would help the owner if ever asked).

### D11. Silent loss on corrupted film data; no automatic film backup (Low-Medium, confirmed)
- 56 modules define their own `_read` that returns a default on `OSError/ValueError` (for example `voiceover.py:50-55`, `_meta:92-94`). A corrupted `voice.json` is read as empty and the next write replaces it, losing every other entry, with no message.
- Automatic backups exist for the render project only (`packer.py` needs `project.json`); the app's own wording says "Backups are made of the timeline". `film.json`, the bible and the contracts are not covered.
- **Remediation (small, mechanical):** one shared `safeio.py` with `read_json` (on a parse error: move the bad file to `*.corrupt-<time>`, keep going with a clear message) and `write_json` (atomic, keeps one `*.bak`); migrate the 56 copies gradually. Add a daily snapshot of the film's small JSON files.

### D12. Credential handling (Positive finding)
`key_status` returns booleans (`lib.rs:364`); `set_key` validates the provider (`:377`); no command returns a key; the engine reads `os.environ` only for headers; `jobs.json` stores payloads, not headers; no `print`/logging of keys found (V-code, grep). The error path returns the last six lines of the engine's stderr to the screen (`lib.rs:163-165`); tracebacks can include local paths but not headers. **No action.**

### D13. Memory use of the audio mix (Low now, High if feature-length is in scope)
`voiceover.mix_into` (`:478-507`) and `shotsound.mix_track` (`:492+`) hold the entire film as a float32 stereo array: about 121 MB for the 5:42 sample film, about 1.9 GB for 90 minutes (computed). **Remediation:** mix per scene and concatenate, only when long films matter.

### D14. Retry classification risk on providers other than ElevenLabs
Not re-audited in depth. The render runner's classification (`render.py:2150-2215`) is thorough and tested; nothing alarming found.

---

## E. Testing gaps

### E1. What the tests demonstrate, and do not (measured)

| Layer | Count | What it proves | What it does not |
|---|---|---|---|
| Engine (`pytest`) | 1,772 cases from 1,368 test functions, 117 files; **no test file calls `requests` directly**; 65 files use `monkeypatch` fakes | Logic, file handling, request building, failure paths (402/403/5xx for ElevenLabs; state machine for renders), security refusals | Real provider behaviour; any UI |
| Screens (`vitest`) | 503 tests, 61 files, **no DOM environment and no Testing Library** (not in `package.json`) | Pure logic (20 files); static markup via `renderToStaticMarkup` (30 files: no effects, no clicks, no state) | Anything interactive: clicking, typing, drag, scroll, effects, timers |
| **Source-text tests** | 55 `readFileSync` calls over `src/*.tsx`, `*.css`, `lib.rs`, `*.py`, across 12 files holding **98 of 481** tests | That a string, class or function name exists | That it works. They guard wiring and regressions in CSS, but would pass on broken behaviour. |
| Rust | 8 | Key store, `wav_ok`, action lists | The 93 commands |
| Sweep (`docshots-edge.mjs`) | 49 screens | Opens each screen in headless Edge with sample data: no console errors, no axe findings, no overflow at 1100 px | **Edit mode is never opened** (the layout is fixed at Film strip); no interaction |
| Installed app | **0** | nothing | everything |

**Verdict:** engine coverage is strong and honest. Screen coverage is thin on behaviour, and the source-text tests, while useful as guards, should not be mistaken for component tests. The recent timeline bugs (voice lanes cut off, three attempts to fix) were exactly the kind a behavioural test would have caught.

### E2. Highest-value additions (in order)
1. **A DOM test environment** (`happy-dom` or `jsdom` plus `@testing-library/react`, dev-only). Then add behaviour tests for: `VoiceLanes` (band shows three lanes, "Show all" opens more, a clip click opens the editor), `LineEditor` (chip inserts `[tag]` at the right place; Speak asks before sending; takes switch), `ShotVoice` (one speaker opens straight away), `useShotDrop` drop-on-person logic with a fake webview. Replace the corresponding source-text assertions rather than adding to them.
2. **A layout test for the timeline arithmetic** as a pure function: extract `reserve/shown/cardH/tops` from `Studio.tsx:1164-1171` into `timelineLayout.ts` and test it across lane counts, window heights and modes (this is the code that failed three times).
3. **Edit-mode coverage in the sweep:** let the harness open a film already in Edit mode (seed `pf-tl:<dir>` with `edit: true`, `voices: true`) and run axe and overflow checks on it.
4. **Engine tests for the gaps above:** `design`, `design_save` and `clone` refuse without `confirmed`; a replaced recording marks the video take stale; a corrupted `voice.json` is quarantined, not overwritten; `sample` refuses non-audio bodies.
5. **A "known price" test** that every model the app can route to either has a price or is marked unknown, so budget guard behaviour is explicit.
6. **A Windows smoke test script** the owner can run in the installed app (a checklist generated from the golden path), since no automated installed-app test exists.

### E3. Golden path: coverage map

| Step | Automated | Evidence | Gap |
|---|---|---|---|
| Create film from screenplay | Yes | `test_golden_film.py:56` | none |
| Story → Bible (cast, world) | Yes | same | none |
| Shots / contracts | Yes | same; `test_shots*` | none |
| Storyboard / keyframe | Yes (local test pictures) | same | real provider output unverified |
| Assign voices (recorded or ElevenLabs) | **Partly:** unit tests only | `test_voiceover.py`, `test_cast_voice.py` | **not in the golden film test** (0 mentions of "voice" in `test_golden_film.py`) |
| Generate video | Yes with a fake provider | `test_render*`, golden | real Seedance output unverified |
| **Lip-sync** | **No** | request-level tests only | needs one real take (Section 5) |
| Add audio / mix | Yes | `export.py:347-353`; `test_e2e_sound.py` | no loudness or ducking tests (none exist to write) |
| Review / continuity | Yes | `test_continuity*`, supervisor | vision checks need a model |
| Export / hand-off | Yes | golden; `test_interchange.py` (OTIO adapters skipped when absent) | Premiere / FCP import unverified |
| Close and reopen | Yes | golden `...and_back` | none |
| `.filmpack` round trip | Yes | `test_film_pack.py:29` | opening a >1 GB pack in the UI was done once by hand |

Note: `test_e2e_journey.py` is the **music-video** journey ("a song becomes a finished film"). It is legacy and should be re-pointed at the film path or retired.

### E4. Failure scenarios

| Scenario | Handling | Evidence | Gap |
|---|---|---|---|
| Missing API key | Clear message, nothing sent | `SystemExit("Add your … key")` in each provider class | none |
| Insufficient credits | Pause provider, keep jobs queued | `render.py:2179-2185`; ElevenLabs 402 message `cast_voice.py:82` | voices: no resume or ledger |
| Network interruption | Renders: keep job, retry or mark uncertain. Voices: retry then stop | `render.py:2191-2196`; `cast_voice.py:366-381` | D4 |
| API timeout / outage | as above | | D4 |
| Invalid model response | Per-job error; one job never stops the others | `render.py:2199-2215` | none |
| Interrupted generation | **Renders: recovered.** Voices: partial file is `.part`, safe | `render.py:2144-2149`; `cast_voice.py:382-385` | charge not recorded |
| Corrupted project file | Silently treated as empty (D11) | `_read` pattern | Fix |
| Missing media | Per-feature checks (`RequestProblem`: "caught before anything was sent") | `render.py:2197` | none found |
| Failed export | `.part` then replace | `export.py:359-360` | none |
| Duplicate paid requests | Renders: never double-queue the same shot and model (`render.py:2062-2064`); voices: identical words cached | `cast_voice._cache` | none, but see F3 (cannot re-take the same words) |
| Application crash | Renders recover; film data atomic; no film backup | | D11 |

---

## F. Feature, UX and maintainability findings

### F1. Timeline layout arithmetic (Medium, confirmed fragile; one suspected defect)
- **Cause of the repeated "cut off" reports (confirmed):** `lanes.css:2` set `.tl-scroll { overflow-y: auto }`, but `styles.css:222` sets `overflow-y: hidden` and wins in the shipped stylesheet order, so the timeline never scrolled vertically. 0.23.3's wheel fix could not work; 0.23.4 fixed the cause with a fixed-height Voices band and an override (`film.css:956`). **Resolved**, but the dead rule at `lanes.css:2` remains and should be removed so nobody trusts it.
- **Fragility (confirmed):** the heights are sums of hand-copied constants (`34 + 136 + reserve + …`, `laneTop = 118`, `LANE_H`, `VLANE_H`, `VHEAD_H`) at `Studio.tsx:1164-1171`, which must equal the CSS positions (`.tl-wave top 32px`, `.tl-lyrics top 90px`, `.tl-shots top 116px`). Any change to one without the other produces clipping. **Recommendation:** extract to one tested pure function (E2.2), and ideally compute tops from the rendered rows instead of copying numbers.
- **Suspected defect:** the timeline's height is derived from `window.innerHeight` during render (`Studio.tsx:1123,1168`), but the component only re-renders when its `width` state changes (`ResizeObserver` at `:1127` calls `setWidth`). A window resize that changes only the height may leave the timeline stale until something else re-renders. Verify with a test.
- **Display scaling:** `minHeight` 660 / `minWidth` 1100 (`tauri.conf.json:18-19`) are reasoned to fit 150% scaling on a 1080p screen (about 690 px usable height); **not tested** at 125% or 150%.
- **UX:** the two modes (Film strip default, Edit opt-in) are a good simplification. Keep. The Voices band's fixed three-lane view with "Show all" scales to large casts.

### F2. Voice interface duplication (Medium, confirmed)
Six surfaces expose overlapping voice controls: `VoiceChip` (card), `VoiceoverPanel` rows, `ShotVoice` cards, `LineStudio` sheet, `VoiceLanes` clips, `CastVoices`. They share `LineEditor`, `VoiceRecorder` and `VoiceMaker` (good), but **the "import a recording" call is written in four places** (`LineStudio.tsx:72`, `VoiceChip.tsx:37`, `VoiceRecorder.tsx:101`, `VoiceoverPanel.tsx:61`) plus two helpers in `voiceHooks.ts` (`:34,46`). **Recommendation:** one `attachRecording(dir, shot, who, file)` helper in `voiceHooks.ts`, used by all; retire `VoiceChip`'s record/add rows in favour of opening `LineEditor`. **When:** during the next voice phase, not before.

### F3. Same words always return the same take (Medium for the director's workflow, confirmed)
`speak` returns the cached file whenever the words, model, voice and settings match (`cast_voice.py:338-345, 410-425`), and ElevenLabs output varies per call, so a filmmaker cannot ask for "another take of this exact line" without editing the text. Directors iterate on performance. **Recommendation:** a `variant` counter in the cache key and a "Make another take" button; every take is already kept and switchable.

### F4. The single source of spoken dialogue (confirmed behaviour; improve)
Written dialogue lives in `shots/<id>/contract.json` (`dialogue`), separate from the original script versions (the screenplay is not edited). The spoken words live in the take sidecar. These can drift apart (C3.1). Direction tags are kept out of picture and video prompts: `_line` builds the default text from the contract (`cast_voice.py:319-335`) and tags exist only in the text sent to ElevenLabs; a test asserts the contract is unchanged (V-test).

### F5. Several characters in one shot (confirmed)
Supported: recordings are concatenated in speaking order with a fixed 0.25 s gap (`voiceover.slice_for:449-475`, `GAP`), the prompt names the turns, and the lane shows each person's clip offset. **Not supported:** per-line timing offsets, overlaps, or custom pauses. Fine for now.

### F6. Legacy music-video concepts in the film path (Low-Medium, confirmed)
`render.py` (3,124 lines) still centres on `singing()` (`:1866`), "vocal", "lyrics" and the song map (17 modules read `songmap`); voiceover shots flow through the "singing" code, user-visible text still says "the song's vocal" (`changes.py:52`), `lipsync_check.py` talks about "a singer in an animated music video" (`:1-30`), `song.wav` is the soundtrack's file name (`export.py:344`), and `test_e2e_journey.py` is the music-video journey. **Recommendation:** not a rewrite. Step 1: rename the user-facing strings. Step 2: add a thin `speech.py` facade (`speaking_shots`, `speech_audio_for`) that the film path calls, delegating to `singing()` internally, so the vocabulary can be fixed without touching `render.py`'s core. **When:** with the next audio phase.

### F7. Technical debt, classified

| Item | Real debt or reasonable tradeoff? | Action | When |
|---|---|---|---|
| 56 copies of `_read`, 27 of `_write` | **Real** (D11) | shared `safeio.py`, migrate gradually | now (small) |
| `render.py` at 3,124 lines | Real, but stable and heavily tested | do not split now; add the `speech.py` facade only | later |
| Regex model capability (`modelinfo.py:24-29`) | **Reasonable tradeoff**: schema roles drive requests (`render.py` manifest `roles`); regexes only decide "can see pictures" and "draws text well" | keep as fallback; add schema-derived signals where available | with the registry |
| Duplicate model metadata (`TAGGED` in TS and Python; `MODELS` static) | Small real debt | send `tagged` from the engine in `castVoice("status")`; delete the TS copy (the test then becomes unnecessary) | now (tiny) |
| Static lists: `GOOGLE_MODELS:434`, `OPENAI_IMAGE_MODELS:354`, `cast_voice.MODELS:30`, `CREDITS:36` | Real, moderate | live discovery with these as fallback (Section 7) | next |
| Source-text tests | Real (E1) | replace with behaviour tests | incrementally |
| LF/CRLF warnings on every commit | Cosmetic | add `.gitattributes` (`* text=auto eol=lf` for source) | quick win |
| `lanes.css:2` dead rule; magic numbers | Real, small | remove; extract layout function | with F1 |

---

## Section 5. Lip-sync and audio-to-video

### What the code does (V-code)
- A voiced shot sends the person's recording, **padded to the shot's length** (`voiceover.slice_for:449-475`, fixed in 0.23.1 because Kie takes reference audio of 2 s or more), as `reference_audio_urls`, with the character pictures as `reference_image_urls`, `generate_audio: false`, and a prompt line "Chloe speaks along to the reference audio…" (`render.py:1066-1090`; checked on a real shot of the user's film during an earlier session).
- Because Seedance 2 forbids a first frame together with reference media, the approved keyframe goes as a **reference picture**, so the opening frame may differ from the keyframe (`audio_first`, `render.py:2505`, documented in the code).
- A **separate lip-sync pass** exists (`compile_lipsync`, `render.py:2000-2029`): the finished take plus the exact audio at the take's length; for Kie's Volcengine model it picks `lite` (one person facing the camera, close-up) or `basic` (otherwise, with scene detection); fal's `sync-lipsync/v3` gets `sync_mode: cut_off`.
- `lipsync_check.py` can sample frames and ask a vision model whether the mouth matches, but its prompts and logic are written for a **singer in a music video** (`:1-30`), so it needs adapting for speech before it is trusted.

### What is documented by the provider (V-doc, 2026-10-14)
- **Kie, Seedance 2.0** (`docs.kie.ai/market/bytedance/seedance-2`): `reference_audio_urls` up to 3 clips, wav or mp3, **2 to 15 s each, 15 s combined**, under 15 MB; `generate_audio` default true; first-frame and reference modes are **mutually exclusive**. The page **does not say** the audio drives lip-sync, acts as a voice reference, or interacts with `generate_audio`, and itself says to test directly.
- **Kie, Volcengine video-to-video lip-sync:** takes a video and a pure-vocal audio and "changes the speaker's lip movements to match the audio"; modes `lite` / `basic`; audio over 1 s; output follows the audio length; **no per-task price documented** (credits are reported after the task).
- **fal, sync-lipsync/v3:** **$8 per minute** as shown on its page; inputs video and audio; no stated duration limit.

### Verdict
**The request is correct in form. Whether Seedance honours the audio with matching mouth movement is unknown.** The documentation does not promise it. Do not claim lip-sync works. The lip-sync pass is the dependable route in principle; it too has never been run in this project.

### Minimal real-world validation plan (one character, one line, one shot)
Preconditions: owner approval and a cap (Section I). The golden path already prescribes the shape: one test shot first, preferably a speaking one; voices before video.

1. **Pick the shot:** a speaking shot with one person clearly facing the camera, a close or medium framing, 4 s, in the user's film (23 speaking slots; none currently has an approved keyframe, V-code on the user's copy).
2. **Keyframe:** one still with the app's picture model. Estimated **about 4 to 10 Kie credits** (the app's own table lists $0.02 for Nano Banana edit; the price of `nano-banana-2-1` is not in the table, `routing.shot_price` returns none).
3. **Voice:** one ElevenLabs line of 15 to 40 characters on Eleven v4 (about 15 to 40 credits of the user's plan).
4. **Take A:** one Seedance 2 render with the voice as reference audio. Estimated **about 164 Kie credits (about $0.82)** (the app's recorded cost for this model, `routing.shot_price` and `render.estimate`).
5. **Judge (the decision):** compose the finished clip with the ElevenLabs line (the export always uses the recording, never the model's sound) and watch the mouth. Acceptance criteria: mouth opens on the words and closes in pauses; no obvious drift over the 4 s; face remains the right character. Optionally run the adapted vision check (a small OpenAI cost, and the check needs adapting first).
6. **Only if A drifts:** run the lip-sync pass once on Take A. Estimated **about $0.53 on fal** (4 s at $8/min, V-doc) **or the Kie credits shown after the task** (not documented in advance; the app shows its own estimate before the owner approves).
7. **Record the outcome** in `docs/QA.md` "Real runs" and `CHANGELOG.md`, including which route (reference audio vs pass) worked.

**Estimated total:** about 190 Kie credits (roughly $0.95) if Take A is enough; about 190 credits plus about $0.53 (or the Kie lip-sync credits) if the pass is needed; plus under 50 ElevenLabs credits. All within a cap of 800 Kie credits.

---

## Section 6. Sound effects and music architecture

### What exists (V-code)
- **Per-shot sound layers:** the song under the shot, "all" (everything the video model made), and after a free local Demucs split, "voice" and "other" (effects and music), each with an on/off switch and a gain, applied only when the film is assembled and never destructive (`shotsound.py:1-25`, `mix_track:492`). UI: `ShotSound.tsx`.
- **One soundtrack file** (`song.wav`; the user picks a file or silence via `make` `soundtrack`), with the model's own sound optional per shot.
- **Export mixing:** soundtrack, then shot layers, then voices laid on top, then one AAC stream (`export.py:347-353`). **No ducking, no loudness normalisation, no crossfades**; the only protection is a global scale-down if the sum exceeds 0.98 (`voiceover.py:505-507`), which lowers the music as well as the voices.
- **Contract field `sound`** exists on every shot, is editable (`shots.py:360`), is an empty string in practice, and **nothing reads it** (V-code, grep). It is the natural home for per-shot sound direction.
- **Captions** (`captions.py`) exist for on-screen text; no automatic subtitles from the dialogue were found.

### Provider facts (V-doc, 2026-10-14; **each needs the owner's re-check before commitment**)
| Need | Option | Facts | Caveats |
|---|---|---|---|
| Sound effects, ambience | ElevenLabs `POST /v1/sound-generation` | 0.5 to 30 s; `loop: true` for seamless ambience; `prompt_influence`; model `eleven_text_to_sound_v2`; **same key and same adapter pattern as `cast_voice`** | per-generation price not on the API page; verify |
| Music | ElevenLabs `POST /v1/music` | prompt or a section-by-section composition plan; streaming | search results state that **film and TV rights require an Enterprise plan** (secondary source; read the Eleven Music terms before using for a released film); not fetched from the official terms page here |
| Music | Suno through **Kie.ai** | Kie's docs index has a **Music Models** category (92 entries); `POST /api/v1/jobs/createTask` with `model: ai-music-api/generate` and `input{custom_mode, instrumental, model (V6 etc.), style, lyrics, duration 10-360 s}`; polled with `GET /jobs/recordInfo?taskId`; several variations per request; **audio kept 14 days**, so it must be downloaded at once | licensing / commercial-use terms **not stated** in Kie's page; per-request price **not stated**; the app's Kie index regex ignores "Music Models" today (`render.py:248`) |
| Speech models on Kie | ElevenLabs TTS and text-to-dialogue v3, Gemini TTS | listed in the same index | not needed; direct ElevenLabs is richer |
| SFX from Kie | none found | no sound-effects generator in Kie's index | the video models' own audio (MiniMax H3, Grok Imagine…) can supply effects inside a take |
| Suno directly | Not verified | no official public API confirmed in this review | **requires external verification** |

**Licensing is the real blocker for music.** A film that is shown publicly needs clear rights. Do not ship AI music generation until the owner has read and accepted the provider's terms for the exact plan in use.

### Recommended architecture: extend, do not replace
1. **A cue list, not new tracks.** Add `audio/cues.json` to the film: `[{id, kind: dialogue|sfx|ambience|music, file, shot|at, offset, gain, fade_in, fade_out, duck: true|false, made_from}]`. Voices keep their current files; a small function derives dialogue cues from `voice.json`, so nothing migrates.
2. **One mixer.** Generalise `voiceover.mix_into` into `mix_cues(d, cues, duration, base)` and let the existing `shotsound.mix_track` supply the base. Add: ducking of `music`/`ambience` under `dialogue` (a fixed -9 dB with a short attack and release is enough), a peak limiter instead of whole-track scaling, and a loudness target. These three fix the mix quality regardless of new features.
3. **Providers as adapters beside `cast_voice`**: `sfx_gen.py` (ElevenLabs sound generation, same key, same `confirmed` rule, same ledger) and `music_gen.py` (Kie Suno via the existing Kie adapter shape). Each result goes to `audio/_generated/` with a sidecar, cached like voices.
4. **Reuse `contract.sound`** as the director's note per shot; an "AI Sound Director" is then one assistant call (the app already has `assist.py` and `prompts`) that reads the shot's action, location and sound note and proposes cues; the user approves each (price shown).
5. **UI: extend the Voices band into an Audio band**, one lane per *kind* when expanded (Dialogue lanes per person as now, plus Effects, Ambience, Music), clips draggable in Edit mode only; Film strip stays silent and calm. Show only kinds that have content. **A separate mixing workspace is not justified yet**; revisit if lanes exceed about 12 or per-clip automation is requested.
6. **Native video audio** stays as the existing per-shot "model sound" layer; the Audio band simply shows it as a lane when switched on.

---

## Section 7. Providers, model registry and updates

### Findings
- **Kie.ai:** discovered dynamically by scraping `docs.kie.ai/llms.txt` with a regex over markdown lines (`render.py:244-251`) and parsing the YAML request schema from each model's doc page (`kie_manifest:260`). This is clever and is why Nano Banana 2.1 appeared without a code change; it is also **brittle**: it depends on the docs site's format, has no pinned fallback, and ignores "Music Models". Cached (`render.py:1794`, 12 h for Kie).
- **fal:** official catalog API (robust).
- **Google, OpenAI, ElevenLabs:** static lists (`render.py:434, 354`; `cast_voice.py:30-36`). The model ids are right today, but go stale: Google's `gemini-3.1-flash-image` retires on 2026-10-29 (per secondary sources, **not confirmed on Google's own page**).
- **Prices:** `routing.shot_price` returns none for several newer models (`nano-banana-2-1`, the lip-sync models; V-code, called directly). The guard falls back to a high figure (`routing.py:168-176`), which is safe but opaque to the user.
- **Capability detection:** requests are built from schema-derived `roles` (good); regexes only classify "can see pictures" and "draws text well" (`modelinfo.py:24-29`). **Significant? Moderate:** a mis-classified new model degrades a recommendation but cannot send a wrong request.

### Recommendation: extend, with a small registry file
1. **`models.json` cache in `~/.filmcrafter/`** populated at most once a day by free discovery calls, with the current static lists baked in as the fallback: ElevenLabs `GET /v1/models` (returns `model_id`, `can_do_text_to_speech`, `maximum_text_length_per_request` and a **`character_cost_multiplier`**, V-live earlier; replaces the hand-maintained `CREDITS`, and also lists v4); Google `ListModels` (V-live: the app's key reached `models/gemini-nano-banana-2.1`); fal's catalog; Kie's index (and include Music).
2. **Fields per model:** `provider, id, kind, title, capabilities (from schema), price (known | unknown), status (current | deprecated | retired-on <date>), seen_at`. Deprecation shows as a quiet warning in the picker; a retired model is never the automatic choice.
3. **Keep the adapters as they are**; the registry only supplies *what exists and what it costs*. No plug-in framework is needed.
4. **Project compatibility:** a project stores the model id it used (it already does in jobs); an unknown id is shown by its stored title, not an error.

### Application updates (separate from model updates)
- **Today:** a notification-only check that points at the wrong repository (D5); unsigned installers; Windows only (macOS build exists in CI but is untested).
- **Recommended path (in order):** (1) make the check work against a public releases location and hide it until then; (2) obtain a Windows code-signing certificate and enable the existing `signCommand`/CI hook (`build.yml:167-190`); (3) adopt Tauri's signed updater (a separate key pair, signature verified before install) once signing exists; (4) keep user films and settings outside the install folder (already true: `Documents\FilmCrafter`, Credential Manager, `~/.filmcrafter`), and snapshot before any migration. Rollback = keep the previous installer; migrations must be additive.

---

## G. Feature gap analysis

| Capability | Today | Gap | Size |
|---|---|---|---|
| Voice suggestion from character description | none | needs the bible's `voice` field (exists, `assist.py:144`) + library search | S |
| Multi-character auditions | none | speak one line in N voices, price shown once | S-M |
| Scene table read | none | reuse the export "window" preview (`export.build(window=…)`) with voices only | M |
| "Voice the scene" with one price and a cap | per-line and "speak all missing" exist (`CastVoices.tsx:68-74`) | single scene estimate, cap, ledger | S-M |
| Natural dialogue enhancement | tags work; no assistant | an "add natural hesitation, breath, laughter" suggestion that edits only the spoken text, never the dialogue | S |
| Character performance continuity | voice identity per name; no emotion arc | store per-character defaults and a per-scene mood | M |
| SFX / ambience / score | none | Section 6 | L |
| Selective regeneration | audio takes yes; video no | `made_from` + `stale_reasons` | M |
| Automatic subtitles | none found | derive from dialogue timing; reuse `captions.py` | S-M |
| Better audio mixing | basic | ducking, limiter, loudness | M |
| Dynamic model registry | partial | Section 7 | M |
| Project recovery | timeline only | film snapshot | S |

## H. Quick wins (safe, small)

1. Fix `updates.py:20` or hide the update pill until a releases location exists.
2. Correct the docstring at `cast_voice.py:8`; require `confirmed` in `design`, `design_save`, `clone` (+3 tests).
3. Send `tagged` from the engine and delete the TypeScript `TAGGED` copy (`LineStudio.tsx:13`).
4. Remove the dead rule `lanes.css:2`; add `.gitattributes`.
5. Change "The song's vocal…" to speech wording in `changes.py:49-52`.
6. Narrow `_sample_host_ok` to the known hosts and sniff the body as audio (`cast_voice.py:159-205`).
7. Cap `.filmpack` total size and entry count (`packer.py:140`).
8. Add `variant` to the voice cache key + "Make another take" (F3).
9. Seed the sweep with Edit mode (E2.3).
10. Make the Windows first-run Python download verifiable (pin SHA-256) or bundle it.

## I. Issues requiring owner approval

| Item | Why it needs a decision |
|---|---|
| **Paid test of lip-sync** (about 190 Kie credits, plus the lip-sync pass if needed, plus under 50 ElevenLabs credits) | spends money; a cap of **800 Kie credits** and **3,000 ElevenLabs characters** was already offered in conversation; confirm it applies |
| **Music licensing** (ElevenLabs Music film rights; Suno via Kie terms) | a legal and commercial decision for any released film |
| **Where releases live, and a code-signing certificate** | a purchase and a public repository decision |
| **Narrowing the asset scope** | security-sensitive; changes what the webview may read |
| **Any change to confirmation rules** (D2) | changes spending behaviour |
| **Film-level backups** | writes new files into the owner's film folders |
| **Pushing or releasing** | not done in this review; each phase should be approved before it ships |
| **Voice cloning on any real person's voice** | consent, as always |

---

## J. Recommended development roadmap

Sizes are relative (S = a day or two of focused work, M = about a week, L = several weeks), not calendar promises.

### Phase 0: Truth and safety (S to M) *do first*
- **Objective:** close the spending and honesty gaps before adding features.
- **Reuse:** `render.py` ledger patterns, `routing.guard`, `golden.is_stale`, `changes.compare`.
- **Changes:** Quick wins 1, 2, 3, 4, 5, 6, 7 above; `voice/ledger.json` and a unified "project spend"; D4 retry rule; shared `safeio.py` (quarantine + `.bak`) used first by voice and `film.json` writers; engine tests for each.
- **Dependencies:** none. **Risks:** low; the `safeio` migration must be gradual.
- **Acceptance:** no paid ElevenLabs call succeeds without `confirmed`; every paid voice call appears in the ledger; a corrupted `voice.json` is quarantined with a message and nothing else is lost; the update pill either works or is hidden.
- **Tests:** E2.4 list.

### Phase 1: Prove lip-sync, track what is out of date (M)
- **Objective:** answer the product's biggest open question and stop paying for stale video.
- **Changes:** run the Section 5 plan (with approval); add `made_from` to voice entries and video jobs, `stale_reasons(d, shot)`, a "Voice changed since this take" line in the existing "Since the last take" panel and a stale badge in Make film; fix identity to use the bible id (C2).
- **Acceptance:** replacing a recording marks that shot's video stale and says why; approved or locked takes are untouched; the QA doc records the real lip-sync result.
- **Tests:** stale detection for line edit, recording replacement, keyframe change; rename-a-character keeps the voice.

### Phase 2: Voice flow to "voice the scene" (M)
- **Reuse:** `CastVoices`, `LineEditor`, `export.build(window)`.
- **Changes:** voice suggestions from the bible; auditions; one scene estimate with a cap and a single yes; "Make another take" (F3); scene table read; one `attachRecording` helper (F2); retire the duplicated card controls.
- **Acceptance:** from a scene, one price and one approval voices every missing line, stops at the cap, and a table read plays before any video is paid for.

### Phase 3: Behavioural tests and layout hardening (S to M; can run in parallel with 2)
- DOM test environment; behaviour tests for the voice screens; `timelineLayout.ts` pure function with tests; fix the possible resize defect; Edit mode in the sweep; install-test checklist.

### Phase 4: Audio cues, SFX and music (L)
- Section 6: `audio/cues.json`, `mix_cues` with ducking and limiting, `sfx_gen.py`, then `music_gen.py` (only after licensing is settled), Audio band, `contract.sound` as the Sound Director's input, automatic subtitles from dialogue timing.
- **Acceptance:** a scene with dialogue, one effect and a music cue exports with the music ducked under speech and no clipping; each generated asset is cached, priced first and regenerable alone.

### Phase 5: Model registry and updates (M)
- Section 7: `models.json` with live discovery and fallbacks, ElevenLabs cost multipliers from the API, deprecation warnings; public releases, signing, signed updater.

---

## K. Recommended next development prompt (do not execute until approved)

> **Task: FilmCrafter Phase 0 and the first half of Phase 1. Work on a branch; do not push or release without asking.**
>
> **Context.** FilmCrafter 0.23.4 (commit `8a8d0be`) is a Tauri 2 / React / Python-engine app. Read `HANDOVER.md`, `docs/NEXT_PHASE.md`, `docs/QA.md` and `docs/INDEPENDENT_ARCHITECTURE_REVIEW.md` first. The voice system (`analysis/filmcrafter_engine/cast_voice.py`, `voiceover.py`; screens `CastVoices`, `LineStudio`, `ShotVoice`, `VoiceLanes`) already exists and works against faked providers; do not rebuild it.
>
> **Rules.** No paid API calls without the owner's explicit yes and a stated cap. Never print or store a key. Preserve all user data; archive, never delete. Keep changes small and tested. Run the full suites (engine, screens, shell, sweep, `rafter secrets .`) before and after each step, and stop if anything regresses.
>
> **Step 1: spending safety.**
> 1. In `cast_voice.py`, require `confirmed is True` in `design`, `design_save` and `clone` (keep `consent` for `clone`); update the module docstring (line 8) to say exactly which calls can spend.
> 2. Make the screens (`CastVoices.tsx`) send `confirmed: true` only after an explicit ask for keep-a-designed-voice and clone ("this uses one of your N voice slots"); design already asks.
> 3. Add `voice/ledger.json` (append-only, atomic): `{at, action, characters, credits, outcome: ok|refused|uncertain, shot?, person?}`; write an entry for every call that can spend. Show "spent on voices this film" in the Voiceover screen.
> 4. Change `_speak_to` so only responses that prove nothing was accepted (429, connection refused before send) are retried; on a timeout or 5xx after sending, record `uncertain` and raise with a clear message.
> 5. Tests: each of the three refuses without `confirmed`; ledger entries appear; an ambiguous timeout is not retried.
>
> **Step 2: honest wording and small hardening.** Fix `updates.py:20` (or hide the update pill until a releases location exists; ask the owner which); replace "The song's vocal…" in `changes.py:49-52`; narrow `_sample_host_ok` and sniff the body as audio in `sample()`; cap `.filmpack` extraction size and entry count in `packer.py`; remove `lanes.css:2`; add `.gitattributes`.
>
> **Step 3: shared safe I/O.** Create `analysis/filmcrafter_engine/safeio.py` with `read_json(path, default)` (on a parse error: rename the bad file to `<name>.corrupt-<timestamp>`, return the default, and report it) and `write_json(path, data)` (atomic, keeps one `<name>.bak`). Adopt it in `voiceover.py`, `cast_voice.py` and the `film.json` writers in `story.py`. Do not touch the other modules yet. Tests for corruption, quarantine and the `.bak`.
>
> **Step 4: "made from" for voices.** Give each `voice.json` entry `made_from {line, voice, model, voice_id}` (`line` = sha1 of `speaker|line|paren` from the shot contract, `voice` = sha1 of the file) and store `voice_hash` on video jobs (`render.py`, near where `keyframe_ref` is recorded, lines 2266 and 2376). Add `stale_reasons(d, shot)` that reuses `golden.is_stale` and `changes.compare` and returns reasons for keyframe, voice-line and voice-file changes. Surface "Voice changed since this take" in the existing "Since the last take" panel. Never modify or delete anything; only report. Resolve identity through the bible id with the slug as fallback. Tests: replacing a recording marks the video stale; editing a line marks both; locked and approved assets are reported but never altered.
>
> **Step 5: report.** Update `CHANGELOG.md`, `docs/QA.md` (what was and was not verified, including any provider run), and `docs/NEXT_PHASE.md`; list every file touched. Stop and ask before any release or push.
>
> **Out of scope for this task:** SFX, music, lip-sync spending, the model registry, signing, and the timeline arithmetic (Phases 2 to 5).
