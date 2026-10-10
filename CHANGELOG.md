# Changelog

## 0.1.0 (unreleased)

- **Story-first Home and creation flow.** Home is about stories: drop a screenplay, press New film, or start from an idea. New film asks how your story begins (screenplay, idea or logline, synopsis, treatment, scene outline), takes pasted text or a file (Fountain, text, Markdown, PDF, Word), shows what was found, and keeps the story exactly as given (the chosen file is copied untouched into the film). A film opens in the story workspace: scenes, the script as written, versions, Story Lock, suggestions that never edit the script, characters and places. New engine module `story.py` (film.json, script versions, analysis, lock history), a `film` shell command, a film kind in Recent.
- Removed: the music-first Home (Create from song, Make a song, New show, Producer package), the animated drop wave.
- Tests: `test_story.py` (16 engine tests), `story.test.tsx`.

- Seeded from PULSEFRAME 1.36.0 (see docs/architecture/BASELINE.md). Identifiers renamed (product, bundle id, engine package, key service). Music-specific modules are still present and are removed in Phase 0 steps listed in docs/architecture/PHASE0_PLAN.md.
