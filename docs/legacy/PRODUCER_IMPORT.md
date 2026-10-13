# Importing a PULSEFRAME Producer package

**Writing a package?** The complete instructions for the plugin (what to include, what PULSEFRAME ignores, and a checklist) are in [PRODUCER_PLUGIN_INSTRUCTIONS.md](PRODUCER_PLUGIN_INSTRUCTIONS.md).

**Where:** Home → **Import production package**. It accepts a ZIP, a folder, or a manifest JSON (schema 1.0).

**The flow:** choose the package → review what's in it and what's missing → choose the song (if the package doesn't include one) → Import. The project is created, the song is analysed, and the shots are placed on it. From there it's the usual Studio workflow; nothing is rendered or billed.

| Package | Lands in |
|---|---|
| characters, wardrobe, props, environments, references | Reference library (files copied to `assets/producer/`). Items keep their plugin id, so re-importing updates rather than duplicates. |
| canonical assets with `locked_rules` | The rules go in full into every prompt that uses the asset, and are added to the Production Bible's "Always". |
| `continuity.rules` / `known_exceptions` / `production_bible` (.md or .txt) | Production Bible: Always / World |
| choreography with a dance classification | Choreography sheets, plus per-section notes for that character |
| choreography with any other classification (for example "acting only, restrained") | The character's acting profile, plus acting notes |
| `project.aspect_ratio` / `visual_style` | The project's frame / look notes |
| shots | The shot plan. Each shot is placed by its own times, else its lyric cue, else its song section, cut on the beat. Shots with none of these share the time between their neighbours and are listed. The plugin id is kept as `external_id`. |
| `song.lyrics_file` (plain text) | The project's lyrics, so the song is aligned to them and shots can be placed by their `lyric_cue`. A `**Style:**` line and `**bold**` marks are removed. |
| `overlay_map.json` (text signs: `id`, `text`, `section`, `file`) | On-screen text, drawn over the film at export and timed by the song section each names (Export → On-screen text). See [PRODUCER_PLUGIN_INSTRUCTIONS.md](PRODUCER_PLUGIN_INSTRUCTIONS.md) section 8. |
| `qa`, missing files, unknown ids | Production Supervisor ("production package") |

**Only pictures, video and audio are sent to a model as references.** Written specs (`.md`, `.txt`), PDFs and JSON listed in an asset's `files` are kept in the project but never sent. The same picture shared by several characters is sent once. Characters, outfits, props and places with no picture are listed in the import review ("written specs only").

**File paths** are resolved relative to the manifest, then to each folder above it up to the package root, then by file name. The plugin's own Type 7 example writes its paths from the skill folder, and they resolve.

**Tests:** `analysis/tests/test_producer_import.py` covers:
- the real plugin ZIP's Type 7 example (imports as NOT READY, with no shots forced);
- a minimal complete package (mapping, timing, and the instructions reaching the prompt and references);
- shots waiting for the song analysis;
- re-importing without duplicates, and staying editable;
- unsafe ZIP paths being refused;
- the Supervisor report.

**Suggestions for the plugin:**
- Write file paths relative to the manifest.
- Give every shot a `song_section` or `lyric_cue`.
- Include the song file in the package.

## Opening a package straight into PULSEFRAME

A Producer ZIP renamed to `.pfproducer` opens PULSEFRAME with a double-click (the installer registers the file type), and goes straight to the import review. Dropping a `.zip`, `.pfproducer` or `manifest.json` on the Home screen does the same. The Producer plugin can save its package with the `.pfproducer` extension to make this one step.
