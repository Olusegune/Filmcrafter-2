# Creative production expansion: progress, evidence and what is left

Stages A to G of the Sound & Music / voice direction / audio expansion are **implemented on the local branch `stage-a-sound-bible`** (version label 0.25.0, not bumped, nothing pushed, no installer built). The owner approved running all stages in one go; pushing, releasing and every paid operation still wait for the owner (see "Decisions" at the end).

Rules kept throughout: no paid call was made (every provider call in the tests is faked); no new database (everything is additive JSON beside the existing records, written through `safeio`, copied by the film backup and the `.filmpack`); nothing approved is overwritten or deleted (removals move files aside); no real film was opened.

Baseline: FilmCrafter 0.24.0 (Phase 0 released 2026-10-14, tag `v0.24.0`).

## What already existed and was reused

| Reused | By which stage |
|---|---|
| Production Bible (`bible.py`, Cast & World tabs, history copies) | A: the Sound & Music tab, sound style and voice profile live in it |
| `cast_voice.py` voice assignments, library/design/clone/speak, takes, `VoiceMaker` sheet, the paid-operation ledger (`paidops.py`) | A, B, D (the same ledger and rules for sound and music), G |
| `voiceover.py` recordings, windows, `slice_for`, the render project's `voiceover.json` | B (table read, scene voicing), E (ducking spans), F (voice fingerprints) |
| `shotsound.py` layers and `export.build` mixing chain | E: the planned sound is added after the existing mix; a film with no plan exports exactly as before |
| Shot contract `sound` field (was unused) | C: edited in the Scene sound panel and read by the quick ideas and the sound director |
| `safeio`, `filmbackup`, `packer` (Phase 0) | everywhere: every new record is atomic, locked, damaged-file safe, backed up and packed without a list to maintain |
| `changes.compare` / `golden.is_stale` ideas ("made from") | C, F: cue freshness and the voice a take followed |
| `assist._call`, `acting._estimate`, `llm` (price first, local models free) | B, C: suggestions |

## Stage A: Sound & Music Bible foundation (done)

- **Built:** a fifth Cast & World tab "Sound & Music" with Voices, Sound effects, Music and Sound style (a fifth area, Scene sound, came in Stage C). Sound style (film-wide, in the Bible); per-character voice profile (description, age and range, accent, texture, pace, emotional range, delivery, notes, **approved** flag) stored with the character; the assigned ElevenLabs voice stays in `voice/cast.json` (no second voice database); SFX and music libraries (`audio/library.json`, files under `audio/sfx` and `audio/music`): import, hear, rename, describe, tag, categories, link to places/props/characters/scenes/shots, licence fields (default "not known"), approve/reject, take out (files move to `audio/_removed`, never deleted) and bring back. Stable ids `a-sfx-xxxxxxxx` / `a-music-xxxxxxxx` never change.
- **Owner decisions applied:** profile in the Bible; 200 MB cap; licence fields recorded, no enforcement until Stage D (then enforced as acknowledgement + report).
- **Files:** `audiolib.py`, `bible.py` (+ `safeio`), `SoundMusic.tsx`, `soundWords.ts`; shell `film_audio`, `film_bible` +2 actions.
- **Tests:** `test_audiolib.py` (12), `test_bible_sound.py` (5), `soundmusic.test.ts`.
- **Acceptance:** the audio world can be organised with no paid call (nothing in the tab can spend; a test forbids the paid actions in `SoundMusic.tsx`).

## Stage B: Intelligent voice production (done)

- **Built:** the **spoken version** of a line, kept apart from the screenplay (`voice/performance.json`; "the written line has changed since" is shown, the screenplay is never edited); **Make another take** (ElevenLabs `seed`, a different performance of the same words, priced first, earlier takes kept, the original words stay free); **Make this sound more natural** (writing AI, price first, up to three optional alternatives with the added words named; model without tag support gets plain punctuation); **Suggest voices for this character** (AI proposes the voice description and search terms, matching voices from your library are scored on this computer, free; `Find matches from my notes` needs no AI); **approved voice guard** (an approved voice is never replaced or removed by the engine without `replace_approved`; checked before anything is paid); **Voice a scene** (plan, price, one yes and a spending cap in credits, only lines without a recording, one failed line does not undo the others, an unclear charge stops the rest); **Table read** (the whole scene in order with adjustable pauses, free).
- **Verified against the official docs (2026-10-14):** ElevenLabs text-to-speech takes `seed` (0 to 4294967295, best-effort determinism).
- **Files:** `voicedirect.py`, `cast_voice.py` (seed, guard, spoken version), `VoiceScene.tsx`, `LineStudio.tsx`, `SoundMusic.tsx`; shell `film_voice_direct`.
- **Tests:** `test_voicedirect.py` (25).
- **Acceptance:** a scene can be voiced and heard before any video.

## Stage C: Audio cues and the sound director (done)

- **Built:** `audio/cues.json` (cue: kind, asset, scene or shot, start, duration, level, fades, loop, ducking, muted, approval, source, `made_from`); dialogue is listed from the existing voice files, **never copied**; planned cues that still need a sound; freshness flags (sound replaced or taken out, file missing, shot gone or a different length) that never change the cue (the person confirms with "It is fine"); quick ideas (free, keyword rules over the place, props, action and the shot's sound note) and the sound director (writing AI, price first; looks in your library first for each idea and offers use, plan, or import); manual placement; remove/restore.
- **Added area:** Scene sound inside Sound & Music (a fifth area; the brief listed four).
- **Files:** `audiocues.py`, `SceneSound.tsx`; shell `film_cues`.
- **Tests:** `test_audiocues.py` (15).
- **Acceptance:** a scene has a planned, editable soundscape with no generation.

## Stage D: Sound effect and music generation (done, never run for real)

- **Adapters (verified against current official pages on 2026-10-14):** ElevenLabs sound effects (`POST /v1/sound-generation`: text, duration_seconds 0.5 to 30, prompt_influence, loop on `eleven_text_to_sound_v2`); ElevenLabs Music (`POST /v1/music`: prompt, music_length_ms 3000 to 600000, model_id music_v1/v2/v2_5, force_instrumental); Suno through Kie.ai (`createTask` with `ai-music-api/generate` and `recordInfo`, state values waiting/queuing/generating/success/fail, `creditsConsumed`).
- **Not verified:** Kie's reply format for Suno tracks was read from the documentation only (no paid call); the adapter accepts both documented shapes (`resultJson.resultUrls` and `response.data[].audio_url`). ElevenLabs' sound-effect price is the help centre's figure (11 credits per second set, 100 per generation) and is shown as an estimate; ElevenLabs Music and Kie publish no price, so the person must accept "unknown". **Suno has no official public API; only the Kie gateway is offered.**
- **Rights:** none of the three providers' terms establish commercial use in a way the app can check (ElevenLabs Music's terms depend on the plan and changed on 2025-11-21; Kie's say nothing). Everything is saved as "commercial use: not known", generation asks for an explicit acknowledgement, and `rights_report` flags unconfirmed sounds that the plan uses (shown in Scene sound).
- **Safety:** the paid-operation rules of Phase 0 (confirmed, limit, ledger first, send once, never retry an unclear outcome); reuse by generation key (the same thing asked again is free); a variation is a new request; a finished Kie task that is still running is already paid for and fetched later with Check again.
- **Files:** `audiogen.py`, `audiolib.py` (`add_file`, `rights_report`), `MakeSound.tsx`; shell `film_audiogen`.
- **Tests:** `test_audiogen.py` (18).
- **Acceptance:** generated audio is reviewed, saved, reused and linked to scenes (all with faked providers).

## Stage E: Audio timeline and mixing (done)

- **Built:** cue lanes (effects, ambience, music) under the voices in Edit mode; drag to move, click to adjust level, fades, start, mute (left out of the film); lane mute; Film strip is unchanged. The mixer (`audiomix.py`) lays approved cues on the base soundtrack in blocks of 30 s (a flat amount of memory), with fades, looping, music and ambience dipping under voices (settable depth and speed), a peak limiter and an optional loudness target (two-pass, steady gain), a scene preview with Everything / Voices / Effects / Ambience / Music only. The exporter calls it after the existing mix; a film with no approved cue is not touched.
- **Measured (tests with real audio and ffmpeg):** a cue lands where planned at the level asked; fades; loops; ducking depth within 2.5 dB of the setting; peaks held under the ceiling; loudness within 2.5 LU of the target; a ten-minute film with a five-minute piece uses under 150 MB of numpy memory; an exported film contains the planned sound where it was placed and not the suggested-only one; the source file's hash is unchanged.
- **Files:** `audiomix.py`, `export.py` (one hook), `CueLanes.tsx`, `Studio.tsx`, `SceneSound.tsx`; shell `film_mix`.
- **Tests:** `test_audiomix.py` (14, one through `export.build`).
- **Acceptance:** a scene with dialogue, ambience, effects and music exports without clipping.

## Stage F: Lip-sync and asset continuity (done; the real lip-sync test is NOT run)

- **Built:** every video take and lip-sync pass records the exact voice it followed (`voice_ref`); `outdated.report` names takes whose voice was replaced, removed or added, planned sounds that may need another look, and a finished film exported before its sound changed; approved or locked takes are reported with a note, never changed; takes made before this have no record and are counted, not judged. The "Lip-sync this take…" pass already existed. `docs/LIPSYNC_VALIDATION.md` holds the controlled paid test (one character, one line, one shot, with a cap) and its results table, which is empty.
- **Not done:** a real lip-sync run (needs a separate authorization and cap); adapting the picture check's prompts for speech.
- **Files:** `outdated.py`, `voiceover.py` (`clip_record`), `render.py` (stores `voice_ref`), `OutdatedPanel.tsx`; shell `film_outdated`.
- **Tests:** `test_outdated.py` (9).

## Stage G: Model registry and update infrastructure (registry done; updater waits)

- **Registry (`registry.py`):** built-in models always answer; discovery from ElevenLabs `GET /v1/models` (with its credit multipliers, used in price estimates), Kie's published index and OpenRouter; stored in `~/.filmcrafter/registry.json`, apart from the app and from every film; a failed discovery changes nothing; a model that vanishes is marked, never removed; deprecations a provider announced are kept; unsupported parameters are refused before sending (for the models whose inputs are listed); the models behind a film's takes, chosen voices and generated sounds are reported and never swapped, least of all behind approved work. Settings has a "Refresh the model lists" row.
- **Updates:** evaluated in `docs/UPDATES.md`; the safe parts are built (`preupdate.py` snapshots recent films' records and the app's settings, never a key; `prepare_update` command; the update button calls it first); **the updater itself is not enabled**: it needs a public releases location, a code-signing certificate and an updater key pair (owner decisions).
- **Tests:** `test_registry.py` (14), `test_preupdate.py` (4).

## Manual Windows test instructions (for the owner; free unless marked)

1. Open a film, Cast & World → **Sound & Music**. Import two short sounds (Sound effects) and one piece of music. Hear them, rename one, set its place, approve one, take one out and bring it back. (Free.)
2. Voices: pick a character, fill the voice notes, **Find matches from my notes (free)** (needs the ElevenLabs key; reads your library only).
3. Scene sound: **Quick ideas (free)**; add a sound to the scene; open **Adjust** and change level and fades. Press **Hear this scene: Everything**; then **Music only**.
4. Open the Studio in **Edit** mode: the Sound lanes appear under the voices when the plan has cues; drag a clip; click it and mute it; the Film strip is unchanged.
5. Export the film: the sound you planned is in the file, nothing clips (watch the loudness note), and a film with no plan sounds exactly as before.
6. Replace a recording on a shot that has a video take (made after this version): Voiceover shows "may be out of date" and nothing is changed.
7. Settings → **Refresh the model lists** (free reads). Settings → Updates says checking is off.
8. **[spends]** only with your yes: Make with AI… for one short sound effect (about 22 credits for 2 s) after reading the price and the rights note; one voice scene with a small cap. Do not run a music generation until you accept the unknown-price and rights statements.

## Known limitations and remaining risks

- No provider call was made for real: the ElevenLabs sound-effect and music requests, the Kie task flow and the new seed parameter follow the documentation only. First real runs should be tiny.
- Music and sound rights are not established for any provider: generated assets are drafts until the person confirms their terms.
- The ducking follows voice **recordings** (the app's own placement of them); a model's built-in dialogue sound in a native-dialogue scene is not detected.
- The cue lanes show effects, ambience and music only (dialogue stays in the Voices band); there is no per-cue waveform and no snapping.
- Solo and the lane mute buttons in the timeline: mute leaves a lane out of the film, solo is for the preview only.
- The Edit timeline lanes and the new screens were checked in the browser harness with mocked data; not walked through in the installed app.
- Takes made before this version carry no voice record, so a later voice change cannot be detected for them.
- The speech-adapted picture check and the real lip-sync test are not done.
- Pricing figures for ElevenLabs credits come from help-centre text and may differ by plan; the app always labels them as estimates.

## Decisions for the owner

1. Approve a push and a release (version 0.25.0)? Nothing was pushed or built.
2. Authorize a small paid first run (a cap) for a sound effect and one voice scene, then, separately, the lip-sync test in `docs/LIPSYNC_VALIDATION.md`.
3. Public releases location, a code-signing certificate and an updater key pair (`docs/UPDATES.md`) before the secure updater is switched on.
4. Whether to keep Scene sound as a fifth area (the brief listed four).

## Stage log

| Stage | Status | Evidence |
|---|---|---|
| A | done | `test_audiolib.py`, `test_bible_sound.py`, `soundmusic.test.ts` |
| B | done | `test_voicedirect.py` |
| C | done | `test_audiocues.py` |
| D | done (providers faked) | `test_audiogen.py` |
| E | done | `test_audiomix.py` (real audio, one through the exporter) |
| F | done (real lip-sync not run) | `test_outdated.py`, `docs/LIPSYNC_VALIDATION.md` |
| G | registry and pre-update snapshots done; updater waiting on owner decisions | `test_registry.py`, `test_preupdate.py`, `docs/UPDATES.md` |
