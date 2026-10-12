# Next phase: what to do after 0.20.0

Written 2026-10-12. Read `HANDOVER.md` first (setup, checks, release steps, rules); this note is the plan for what comes next and what was learned recently. Everything here is in GitHub (`Olusegune/FilmCrafter`, branch `main`, commit of 0.18.0 or later).

## 1. Where things stand

FilmCrafter is at **0.20.0**: a Windows app (Tauri 2 + React/TypeScript + Python engine) that turns a screenplay into a film. Recently done:

- **Voiceover** (0.15 to 0.17): attach your own recordings to people in shots by file name (`CHLOE_S01-04.wav`), from the Studio's bar, the Export screen, a shot's card, the timeline's shot cards (a mic and a bar) and the shot panel; drag a file onto a card or timeline shot; one or two speakers per shot; the recording is the audio a Seedance 2 shot follows (keyframe sent as a reference picture), the sound at export, and per-shot files in the editor hand-off. "Lip-sync this take" uses the recording.
- **Correctness fixes found by using the app**: a title read as a character, action shots with no people, long picture names dropped, one person using every reference slot, the frame shape reverting to 16:9, the previous shot's picture copying one character onto another, plural "friends", Word screenplays cut at 6,000 characters.
- **0.19.0**: Nano Banana 2.1 (Google default; Kie checked; fal not), a calm clapperboard Home, a waveform beside each recording, big films skip off-screen cards, window minimum height 660.
- **0.20.0**: drop a file on a person's name (with Undo); record a line inside the app (teleprompter, level, silence trimmed, retake, next unvoiced line); custom voices with ElevenLabs (library, design, clone, speak a line, price first); a snugger Home card. The microphone has **not** been tried in the installed app, and ElevenLabs has **not** been tried for real (no key was stored here): try both first.
- **Cleanup**: music-video screens, commands and engine modules removed (92 to 81 modules); tag `before-music-removal` marks the old code.

**Not proven**: a real Seedance render with a user recording (nobody has heard the lip-sync); the installed app has not been walked through by a person end to end; no keyboard-only or screen-reader run; Premiere Pro / Final Cut hand-off; macOS; code signing; 125% and 150% display scaling.

## 2. Decisions that belong to the user (ask, do not assume)

1. **Spend**: any real provider run needs their explicit yes and a cap (they have used about $0.96 of a $5 cap). Show the price first.
2. **Summit Sprout's frame shape**: set to 21:9 on 2026-10-12 at their request; its older 16:9 pictures (S01-02 and others) should be re-made. Ask before re-making (it costs money).
3. **Old folders** beside the film in `Documents\FilmCrafter\`: `... Final Version 2 (before repair)` (a full backup, 850 MB) and the stale `... Final Version`. Never delete without their say.
4. **Native dialogue** (the video model speaks the lines): keep or remove? It has tests and no screen. Removing it means changing `render.compile_request`, the price sheet and the Studio's estimate fields.
5. Their two "FilmCrafter hand-off check..." projects in DaVinci Resolve: theirs to delete.

## 3. The next steps, in order

### A. The real voiceover test (the most valuable thing left)
Goal: hear whether a Seedance 2 mouth follows a recording. Steps:
1. Ask for permission and a cap. Pick one short shot with one speaker (a Summit Sprout shot with a line; a close-up is best). Have the user name a recording `CHARACTER_SHOT.wav` (3 to 8 seconds).
2. Attach it (Make film card, or `python -m filmcrafter_engine.voiceover import <film> --data '{"items":[{"file":"...","shot":"S01-04","speaker":"Lila"}]}'`).
3. Check the request is right without spending: `python scripts/audit_film.py "<film folder>" --kind video --model bytedance/seedance-2` (it should report 0 problems and show the audio carried), and the shot's "What the model is told" panel.
4. Render one take on Kie.ai (Seedance 2). Audio is uploaded to the provider as reference: tell the user first.
5. Judge: does the mouth follow the voice? Does the exported film play the recording (not Seedance's sound)? If the mouth drifts, try the Studio's "Lip-sync this take…" (extra cost, shown first).
6. Write the result into `docs/QA.md` ("Real runs") and `CHANGELOG.md`.
Facts: Seedance 2 takes up to 3 reference audio files, 9 reference pictures, and refuses a first frame together with reference audio; that is why `render.audio_first` sends the keyframe as a reference picture. Two speakers in one shot are one clip with each person's window; the prompt says who speaks when.

### A2. Ideas for making voices feel magical (agreed order)
1. Done in 0.20.0: drop on a person; record in the app; a voice per character with ElevenLabs (items 3 below is now mostly built: what remains is routing unnamed files to a person's voice).
2. **Match by what is said:** drop unnamed files or one long session; transcribe and match to the scripted lines, asking only when unsure. Needs speech-to-text (0.18.0 removed the bundled one): an optional local model or a priced provider call. The user decides which.
3. **A voice per character** (Cast & World): unnamed files go to the right person; optional ElevenLabs scratch voice from the written line (priced first).
4. **Next-line flow in the Studio's bar** (N for the next unvoiced line) and a play-through of the film with voices and soundtrack before any video is paid for.
Also: a first-run sample film, a "film so far" animatic on Home, hover previews on the Make wall.

### B. A person walks through the installed app
Install, open Summit Sprout, and try (watch for confusion, not only bugs): New film from a screenplay file (also a Word file), the frame-shape tiles, Cast & World, Shots (Studio mode), Select & review (enlarge, fold scenes), Make film cards (add a voice, drop a file), the Studio timeline mic, Export (formats for every shape), the editor hand-off. Keep a list; fix in small releases. Also try with only the keyboard (Tab, Enter, Esc, arrow keys in the preview) and, if possible, a screen reader.

### C. Smaller improvements already identified
- A waveform (not just a length bar) on the Voiceover screen.
- Separate lip-sync per speaker in one shot, and a lip-sync pass chosen per speaker, if the real test shows the joined clip is not enough.
- Props: found from a shot's action by the cast list's prop names; consider also wardrobe and set pieces.
- The breakdown's pronoun rule ("She wrinkles her nose" after a line) guesses the last speaker; review in real use.
- Large films (hundreds of shots): folding scenes exists; the Make wall and strip draw everything.
- Display scaling at 125% and 150%.

### D. Platform work (needs hardware or certificates)
macOS build and signing (needs a Mac; see `docs/CODE_SIGNING.md`), Premiere Pro / Final Cut hand-off check, a code-signing certificate for Windows.

## 4. How the recent parts work (so you can change them safely)

- **Voiceover** (`analysis/filmcrafter_engine/voiceover.py`; screens `VoiceoverPanel`, `VoiceoverSheet`, `VoiceChip`, `VoiceDrop`, `voiceHooks.ts`, `voiceLogic.ts`): the film folder holds `voice/voice.json` and `voice/<shot>/<person>.<ext>`; `make.sync` copies recordings into `render/assets/voice` and writes `render/voiceover.json`; `render.singing()` returns the recording as the voice of a shot, `slice_for` builds the one clip, `windows` gives each speaker's turn, `export.build` mixes with `mix_into`, `interchange.write` copies the files. All paths from the film are checked with `voiceover.inside`; nothing is ever deleted (`voice/_removed`). Any screen that changes a recording calls `notifyVoice()` so the others reload. Dropping on a card uses Tauri's drag-drop event and the `data-shot-id` attribute.
- **Frame shape**: `film.json` is the source of truth; `render/project.json` is rebuilt from it by `make.sync`. Every screen that sets the shape goes through `frame.ts saveFrame`, which also calls `film set_aspect`. Nine shapes: 16:9, 21:9, 2.39:1, 4:3, 1:1, 4:5, 3:4, 9:16, 9:21; export formats in `exportFormats.ts` and `export.PRESETS`.
- **Who is in a shot** (`shots._draft_scene`, `_named_in`): people with a line, people the action names (full name, unique last name, "Friend #1", plural "friends" for the scene's numbered friends), pronouns after a line. The previous shot's picture is a reference only for people the two shots share (`continuity.previous_keyframe(..., shared_with)`).
- **References** (`library.fit_to_model`): every person gets one picture before anyone gets a second. Files copied into the render project keep their extension (`safe.file_name`).
- **Prompts**: pictures never quote speech (it is drawn as subtitles); videos do carry the spoken line. A picture with no reference on an image-to-image model falls back to its text-to-image twin.

## 5. Tools and checks (all in `HANDOVER.md` section 3)

`scripts/audit_film.py` (every shot's prompt, free), `scripts/engine_reach.py` (what is reachable), `scripts/docshots-edge.mjs` (screens: errors, accessibility, layout at 1100 px, performance, `?n=300`). Run the whole suite before every release: engine about 1,730 tests (5 minutes), screens 477, shell 7, `rafter secrets .`.

## 6. Gotchas that cost time recently

- Shell heredocs eat backslashes: for any file with regexes, newlines in strings or Windows paths, write it with an editor tool and check it.
- The Vite dev server can serve a stale module after quick edits (a missing import at runtime while `tsc` passes): `touch` the file.
- `docshots` harness scenes use fixed sample data; a new component must tolerate missing parts of a reply (several crashes came from that).
- `make.sync` rewrites `render/`: never edit it by hand, and never assume a setting saved only there survives.
- The user tests the installed app and sends screenshots; those reports found the real bugs. Reply plainly, say what was and was not tested.
