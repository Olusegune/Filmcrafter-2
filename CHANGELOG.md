# Changelog

## 0.4.1 (2026-10-10)

- **Fixed: PULSEFRAME's splash screen sometimes showed on launch.** FilmCrafter had inherited its two opening designs (one of them the music app's "steps" picture, on every other launch). There is now one opening: FilmCrafter's own artwork, with a film strip rolling past and a slow sweep of light. A test keeps the music app's pictures out.
- **Fixed: an imported screenplay showed one word per line.** The script column shrank to the width of a word (an auto margin on a flex child). It is centred by padding now, and a test guards it.
- **New: a living film strip on the Home screen.** Two rows of frames roll past behind the drop card; drag a screenplay over it and they speed up and glow. Still with reduced motion.

## 0.4.0 (2026-10-10)

- **Cards | Timeline** on the same film: the story-first cards, or the full studio timeline, one click apart.
- **Film strip** in Make film: shots as blocks along time; drag an edge to change a shot's length, drag a block to reorder.
- The studio on a film no longer shows "Who sings" or the dance direction; lip-sync reads "speaking shots follow the voice".
- Hand-off checked with the real OpenTimelineIO library (OTIO and CMX 3600 EDL parse, same cut).

## 0.3.0 (2026-10-10)

- **Studio tools.** The full PULSEFRAME studio opens on a film from the film workspace: the timeline (scenes as sections, cuts as the grid, dialogue as a lane of words, the soundtrack as the waveform, shots as cards, layers on their own lanes), Supervisor, Review, Acting, Continuity, Lighting, Colour match, Clean up, Layers, Library and Export. Home returns to the film.
- Song-first parts are hidden on a film (Autopilot, Direct My Video, the song guide, tempo); labels say Timeline, Soundtrack and Scenes.
- `scripts/live_test.py`: one real picture through a real provider, price first, nothing without `--yes`.

## 0.2.0 (2026-10-10)

The first version that takes a film from a screenplay to an exported file.

- **Story:** a screenplay (or an idea, synopsis, treatment or outline) is kept exactly as given; scenes, speaking characters and places are read from it; versions; Story Lock; suggestions that never edit the script.
- **Production Bible, Cast and World:** characters, places and props with related states, wardrobe, your own pictures, place layouts, rules and a visual style; filled from the story, then yours; every change is kept in a history.
- **Shots:** the story broken down into a draft of shots, each a Shot Contract (purpose, people and states, place, action, dialogue, acting beats, camera, light, continuity); suggestions with reasons; split, join, duplicate, move, take out.
- **Making the film:** storyboard panels, hero keyframes and video through the proven render engine, with choose and lock at each stage, your own pictures and video, a soundtrack, and export. Every generation shows its price and waits for a yes.
- **Continuity Director:** advisory findings ("may have changed") with reasons; your decisions are kept.
- **Hand-off:** EDL, OpenTimelineIO, Final Cut Pro XML, shot manifest, subtitles, copied takes and soundtrack.
- **Simple and Studio** modes on the same film; **Director Command** (Ctrl+K) for plain phrases about a shot.
- New app icon from the FilmCrafter mark.
- Tests: 90 new engine tests including a whole film from screenplay to export with no provider and no spend.

## 0.1.0 (unreleased)

- **Story-first Home and creation flow.** Home is about stories: drop a screenplay, press New film, or start from an idea. New film asks how your story begins (screenplay, idea or logline, synopsis, treatment, scene outline), takes pasted text or a file (Fountain, text, Markdown, PDF, Word), shows what was found, and keeps the story exactly as given (the chosen file is copied untouched into the film). A film opens in the story workspace: scenes, the script as written, versions, Story Lock, suggestions that never edit the script, characters and places. New engine module `story.py` (film.json, script versions, analysis, lock history), a `film` shell command, a film kind in Recent.
- Removed: the music-first Home (Create from song, Make a song, New show, Producer package), the animated drop wave.
- Tests: `test_story.py` (16 engine tests), `story.test.tsx`.

- Seeded from PULSEFRAME 1.36.0 (see docs/architecture/BASELINE.md). Identifiers renamed (product, bundle id, engine package, key service). Music-specific modules are still present and are removed in Phase 0 steps listed in docs/architecture/PHASE0_PLAN.md.
