# Creative Production Expansion: progress and plan

Tracks the Sound & Music / voice direction / audio expansion (stages A to G). Updated at the end of every stage. Rules from the owner: one stage at a time; stop for approval after each; no paid call without approval and a spending cap; never overwrite approved work; no new database; no push or release without approval.

Baseline: FilmCrafter **0.24.0** (Phase 0 released 2026-10-14, tag `v0.24.0`).

## What already exists (inspected, to be reused)

| Need in the brief | Already in the app | Where |
|---|---|---|
| Character identity, stable IDs | Production Bible: characters/places/props with stable ids, states, history (newest 30), seeding that only adds | `bible.py`, `bible/bible.json`, `CastWorld.tsx` (tabs: Rules & style, Characters, Places, Props) |
| Assigned ElevenLabs voice, model, audition, design, clone | Per-person voice records, library/design/clone/speak, takes, direction tags, usage ledger | `cast_voice.py`, `voice/cast.json`, `CastVoices.tsx`, `LineStudio.tsx` |
| Recordings, shot dialogue files | `voiceover.py` (`voice/voice.json`, files under `voice/`), voice lanes, drop-on-a-name, recorder | `voiceover.py`, `VoiceLanes.tsx` |
| Per-shot sound layers, mixing at export | `shotsound.py` (`sound.json`: song/all/voice/other layers, Demucs split), `export.build` mixes them (no ducking, no loudness management) | `shotsound.py`, `export.py` |
| Shot `sound` direction text | Field exists in the shot contract (`shots.py`, empty by default) and is not used by anything yet | `shots.py:148,360` |
| Paid-operation rules | `paidops.py` ledger/limits/uncertain handling, `docs/PAID_OPERATIONS.md` (written for future sound/music) | `paidops.py` |
| Safe records and backups | `safeio.py`, `filmbackup.py` (snapshots every small `.json`/`.md` found, so a new `audio/` records folder is covered with no code change) | Phase 0 |
| Staleness ("made from") | `changes.compare`, `golden.is_stale` | `changes.py`, `golden.py` |

Missing (all of Stages A to G): the Sound & Music tab, any SFX/music library, audio cues, scene-level voicing and table read, natural-dialogue/voice-casting assistants, SFX/music generation adapters, ducking/loudness in the export mix, lip-sync clip tracking per take, a model registry, a signed updater.

## Stage A: Sound & Music Bible foundation (plan, awaiting owner approval)

**Acceptance:** the filmmaker can organise the film's audio world without any paid call.

### What Stage A builds
1. **A fifth tab, "Sound & Music", in Cast & World**, after Props, built from the existing tab/list/editor patterns. Four calm sub-areas inside it: **Voices · Sound effects · Music · Sound style**.
2. **Sound style** (film-wide): free text fields in the same style as "Rules & style", with chips: overall sound philosophy, realism vs stylised, ambience density, dialogue clarity priority, "prefer silence when…". Music style: genre, instrumentation, mood, tempo, influences, emotional palette, recurring motifs, intensity, silence preference. Stored in the Bible so it is backed up and travels in the `.filmpack`.
3. **Voices** (view over what exists, no second database): one card per Bible character showing the existing voice assignment (from `voice/cast.json`), and the **voice profile** fields: description, perceived age and range, accent/language, timbre, pace, emotional range, default delivery, performance notes. The profile is stored with the character in the Bible (`character.voice_profile`, additive, optional); the assigned ElevenLabs voice stays where it is. "Give a voice…" opens the existing casting sheet (library/design/clone: those still ask and are ledgered). Approved voice is marked by the existing assignment; Stage A adds an explicit "approved" flag so nothing replaces it silently (the AI suggestions of Stage B will respect it).
4. **Sound effects library** and **Music library**: lists of audio assets. Import files (WAV/MP3/M4A/FLAC/OGG, size cap), preview inside the app, rename, describe, tag, category (SFX categories as in the brief), link to places/props/characters/scenes, mark approved. Imported files are copied into the film (`audio/sfx/`, `audio/music/`), never moved or changed. Removing moves the file to `audio/_removed/` (nothing deleted). No AI provider is involved.
5. **Stable audio asset references:** each asset has an id `a-<kind>-<short>` that never changes, plus a content hash, duration, source (`imported`, later `generated`), generation metadata (empty in Stage A), licensing metadata (music: source, licence note, commercial use yes/no/unknown, default unknown), approval status. These ids are what cues will point at in Stage C.

### Data (additive; no database)
- `bible/bible.json` gains optional keys: `sound_style` (film-wide) and per-character `voice_profile`. Old films simply lack them; schema number unchanged (readers default missing keys).
- `audio/library.json`: `{schema, assets: [...]}` written with `safeio` (atomic, locked, damaged-file safe). Files under `audio/sfx/<id>.<ext>` and `audio/music/<id>.<ext>`.
- `audio/cues.json` is **not** created in Stage A (Stage C).
- The voice files stay in `voice/`. Existing films open exactly as before; the Sound & Music tab shows empty lists.

### Code (new/changed)
- New `analysis/filmcrafter_engine/audiolib.py` (import, probe duration via the existing ffprobe/wave helpers, list, update, remove-to-`_removed`, link, approve), with a `main()` using argparse `choices` (the shell allow-list test then applies).
- `bible.py`: add `sound_style` and `voice_profile` to the update paths (additive); history copy already covers it.
- Shell: one new command `film_audio` with an `ACTIONS` allow-list; `film_backup` already covers `audio/library.json` and the Bible.
- UI: `SoundMusic.tsx` (+ small CSS), the new tab in `CastWorld.tsx`, `api.ts` wrapper and types; audio preview via the existing `mediaUrl` (media scope already allows the film folder).
- Safety: imports validated by content (real audio, not just extension), size cap, name sanitising, no path accepted from the screen (files chosen by dialog, copied by the engine).

### Tests
Engine: import/dedupe/rename/link/approve/remove (never deletes), non-audio refused, huge file refused, damaged `library.json` handled, ids stable across rename and across backup/restore, concurrent imports keep both, old film opens, `.filmpack` round-trip and backup snapshot include `audio/library.json` and the Bible fields, shell allow-list agrees. Screens: vitest behaviour/source tests for the tab, empty states, import flow words, "no cost" wording, approved voice guard. Browser-harness look at all four sub-areas, plus the full regression.

### Stage A explicitly does NOT do
Any generation (voice, SFX, music), any AI suggestion, cues, timeline lanes, mixing, scene voicing/table read, lip-sync changes, model registry, updater. (Those are Stages B to G.)

### Decisions needed from the owner before coding
1. **Where the voice profile lives.** Recommended: inside the Bible character (`voice_profile`), so there is one record per character and it is backed up with the Bible. Alternative: in `voice/cast.json` next to the assignment. (Recommended: Bible.)
2. **Audio import size cap.** Recommended 200 MB per file (same as recordings), with a plain-words refusal above that.
3. **Music licensing fields.** Recommended: record source, licence note and a three-state "commercial use: yes / no / not known" (default *not known*), shown as a quiet badge, and later (Stage D) refuse to *generate* with a provider whose commercial rights are not established. OK to ship the fields now with no enforcement yet?
4. **Version.** Stage A as 0.25.0 on a new branch `stage-a-sound-bible`, local only until you approve a push.

### After Stage A
Stop and report: what was built, files, tests, results, limitations, risks, manual Windows test steps, and the recommended next stage (B: intelligent voice production).

## Stage log
| Stage | Status | Evidence |
|---|---|---|
| A | plan written, waiting for owner approval of the decisions above | this section |
| B to G | not started | |

## Deferred / open questions (carry forward)
- Real lip-sync validation is still unrun (needs a spending cap and a go): Stage F.
- ElevenLabs sound-generation and music API capabilities, prices and licensing must be verified against the current official docs at the start of Stage D; nothing about them is assumed here.
- Suno has no confirmed official public API; Kie.ai's music models and ElevenLabs Music need a commercial-rights check before any is enabled (Stage D).
- Signed updates need a code-signing certificate and a public releases location (Stage G).
