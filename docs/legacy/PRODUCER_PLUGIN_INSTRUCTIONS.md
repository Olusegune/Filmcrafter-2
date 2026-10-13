# Instructions for the PULSEFRAME Producer plugin

Paste or attach this to the ChatGPT plugin (its skill / system instructions). It says exactly what PULSEFRAME reads from a package, what it ignores, and what the plugin must produce so a music video can be directed and rendered without any manual repair. It is written from the importer's real behaviour (`analysis/pulseframe_analysis/producer_import.py`), checked against the "I Am Your Mother" package.

---

## 0. The one-paragraph version

Produce a folder (zipped, named `<project>.pfproducer`) with: the song, a plain-text lyrics file, **one picture for every character, outfit, prop and place**, a `pulseframe_manifest.json` that carries every rule PULSEFRAME should obey **as short text inside the manifest**, and a shot list in which every shot names its lyric line or song section. PULSEFRAME reads the manifest and the pictures. It does **not** read your `.md` spec files, PDFs, per-shot prompt files, `song_map.json` or `shot_plan.csv` (the text signs in `overlay_map.json` are read: section 8): anything that matters must be in the manifest or be a picture. Never invent timings, tempo or beats: PULSEFRAME analyses the song itself.

## 1. What goes wrong when these rules are not followed

| Symptom in PULSEFRAME | Cause in the package |
|---|---|
| Characters, outfits or props look different in every shot | No picture for them (only a written spec), or one group lineup shared by everyone |
| A render fails with "file type not supported" | A non-picture (a `.md`, `.pdf`, `.json`) or an SVG was listed as an image in an asset's `files` (PULSEFRAME now skips these, but the model still gets nothing to look at) |
| Shots are bunched or evenly spread, not on their lyric lines | `lyric_cue` text doesn't match a line of the lyrics file, no lyrics file, or no `song_section` |
| A prop or rule is ignored | It was written only in a `.md` spec; the app reads only the manifest's `locked_rules`, `flexible_rules` and `description` |
| On-screen text (signs, titles) is garbled or missing | The words were left for the model to paint, or `overlay_map.json` is missing, uses a section the song does not have, or a sign SVG uses shapes other than text. See section 8 |

## 2. Package layout

```
MyProject.pfproducer            (a ZIP renamed; .zip also works)
  pulseframe_manifest.json      the only machine-read file (any name works; it must contain schema_version, project, assets)
  media/
    AUDIO_MASTER.wav            the song (wav, mp3, m4a, flac, aac or ogg)
  sources/
    lyrics.txt                  plain text lyrics (section 6)
  assets/
    characters/  <id>_sheet.png      one per character
    wardrobe/    <id>.png            one per outfit
    props/       <id>.png            one per prop
    environments/<id>_<variant>.png  one per place and variant
    choreography/<id>_sheet.png      one per dance move sheet
  docs/
    PRODUCTION_BIBLE.md         world and tone, plain prose (read into the Production Bible)
    QA_REPORT.md                what is and is not finished
  README.md                     for humans (ignored by the app)
```

Rules for every path in the manifest:

- Relative to the manifest, forward slashes, no leading `/`, no `..`, no drive letters.
- Every path named must exist in the ZIP. Files with unsafe paths make the whole package unopenable.
- File names: letters, digits, `_`, `-`, `.`. No spaces.

## 3. Pictures: the rules that matter most

PULSEFRAME shows a model the pictures of everything in a shot, so a missing picture means a model has to invent it.

**Formats.** PNG, JPEG or WebP only. (GIF, BMP and TIFF are converted. **PDF, `.md`, `.txt` and `.json` are never sent to a model**, and SVG is only converted when it is a simple text sign, so do not use SVG for pictures.) Longest side up to 3840 px, ideally 1536 to 2048. One subject per file.

**Every one of these needs its own picture (at least one image file in `files`):**

| Asset | Picture to make | Shape and content |
|---|---|---|
| Character | A character sheet, **one file per character** | Plain light background, no text, no labels, no logos. Full-body front, three-quarter, side and back; a close face view; 4 to 6 expressions. Same face, hair, skin tone, build and outfit in every view. Square or 3:2. |
| Wardrobe | The outfit shown on its owner | Plain background, front and back, no text. Same outfit the character sheet wears. |
| Prop | A prop plate | Plain background, front, side and three-quarter, a small scale cue (a hand or ruler), no baked-in text. |
| Environment | A plate of the place, **one environment item per variant** (for example `env_home_ordinary`, `env_home_pageantry`) | 16:9, the whole room or location, no people. One picture per item. |
| Choreography | A move sheet for dancers | Numbered pose panels of one dancer (or a group), no text beyond numbers. |

A cast lineup of everyone together is welcome as an **extra**, but it can never be the only picture of a character: it cannot show a face at the size a close-up needs.

**Every picture in `files` is sent with every shot that uses the asset**, and a model accepts only a limited number of pictures (often 4 to 14). So give each asset **one picture, two at most** (for example a sheet and a face close-up). The same file listed under several assets is sent once. When there are too many, PULSEFRAME keeps characters first, then outfits, places, props.

Image generation advice for the plugin (ChatGPT image generation):

- Generate characters first, then generate every wardrobe, prop and environment image **using the character sheets as references** so faces, skin tones and outfits match.
- One request per image. Do not ask for "all props on one sheet": single props on separate plates stay consistent and can be sent to a model one at a time.
- Ask for "no text, no labels, no logos, no watermarks" in every image prompt. Image models copy any text they are shown into the video.
- Keep outfits identical across a project unless the script says otherwise (then make one wardrobe item per outfit).
- Check each image against its locked rules before including it. If an image does not match, regenerate it, or leave it out and say so in `qa.report`.

**Fallback inside PULSEFRAME.** If an asset has no picture, PULSEFRAME can make one from its spec (Reference library, **Make missing pictures…**), but only if the spec contains the image prompt. So even for assets whose pictures you do not generate, put the image prompt in the asset's `_SPEC.md` under a heading line `VISUAL GENERATION PROMPT` (or `PROMPT`) followed by one paragraph, written as in the image-generation advice above (plain background, no text, the project's style, the locked rules). That paragraph is what the app sends to the image model. It is a fallback, though: pictures you generate and verify yourself are better, because the user does not pay for them again and they have been checked against the locked rules.

## 4. The manifest

Top level (all required): `schema_version`, `project`, `song`, `assets`, `choreography`, `shots`, `continuity`, `qa`.

```json
{
  "schema_version": "1.0",
  "project": {"id": "...", "title": "...", "aspect_ratio": "16:9", "visual_style": "one or two sentences: rendering style, mood, colour, camera feel"},
  "song":    {"source": "media/AUDIO_MASTER.wav", "duration_seconds": 189.52, "lyrics_file": "sources/lyrics.txt"},
  "assets":  {"characters": [], "wardrobe": [], "props": [], "environments": [], "references": []},
  "choreography": [],
  "shots": [],
  "continuity": {"production_bible": "docs/PRODUCTION_BIBLE.md", "rules": [], "known_exceptions": []},
  "qa": {"readiness": "READY WITH WARNINGS", "report": "docs/QA_REPORT.md"}
}
```

### project
- `title` becomes the project name. `aspect_ratio` (`"16:9"`, `"9:16"`, `"1:1"`, `"21:9"`, `"2.39:1"`) sets the frame. `visual_style` is added to every prompt: keep it to the look, with no character descriptions in it.

### song
- `source`: the audio file (included in the package). `lyrics_file`: **plain text** (`.txt` or `.md`). The importer reads it, so the song can be aligned to the lyrics and each shot's `lyric_cue` can find its line. `duration_seconds` is informational. Do not write `bpm`, beats or section times: leave them out. PULSEFRAME analyses the audio.

### assets (each item)

```json
{"id": "char_queen", "name": "Beatrice Queen Bee Adeyemi", "kind": "character", "canonical": true,
 "files": ["assets/characters/char_queen_sheet.png", "assets/characters/char_queen_face.png"],
 "locked_rules": ["60; dark brown skin; round face; burgundy sculptural gele; rectangular gold reading glasses"],
 "flexible_rules": ["expression", "cloth folds"],
 "description": "Elegant, formidable mother; theatrical."}
```

- `id`: unique across the whole manifest; every other part refers to it. `name`: how the app labels it; for characters use the name the script and lyrics use.
- `kind`: `character`, `wardrobe`, `prop`, `environment`, `style`, `lighting`. (Environments are shown as "places".)
- `files`: pictures only, one or two (see section 3), the sheet first. Do not list `.md` specs here (they are ignored for prompts and add nothing for a model).
- `locked_rules`: **short statements that must never change**: age, skin tone, build, hair, accessories, outfit colours, scale. They are placed in full into every prompt that uses the asset. Keep each under 250 characters and the list under 6 items. No instructions about actions here.
- `flexible_rules`: what may vary.
- `description`: one sentence.
- `canonical: true` marks a locked design.
- Wardrobe and props: add `owner_character_id`. Wardrobe is attached to the shot through the shot's `wardrobe_ids`.
- Environments: make **one item per variant** (`env_home_ordinary`, `env_home_pageantry`), each with one picture, and name the right one in each shot's `environment_id`.
- `references`: items with `"kind": "style"` or `"lighting"` and a picture; lyrics and script PDFs are filed here for humans but are not read by the app.

### choreography (each entry)

```json
{"id": "choreo_queen", "character_id": "char_queen", "classification": "featured dance",
 "visual_sheet": "assets/choreography/choreo_queen_sheet.png",
 "moves": [{"id": "m1", "name": "Evidence Sweep", "song_section": "Verse 1",
            "action": "...", "footwork": "...", "arms": "...", "torso": "...", "head_gaze": "...", "travel": "..."}]}
```

- A `classification` containing "dance", "choreo", "groove" or "footwork" makes the entry **dance**: its sheet and its moves (by `song_section`) are added to the choreography notes. Any other classification (for example `acting only, restrained`; recognised words: restrained, subtle, dramatic, energetic, expressive) sets the character's **acting profile** instead.
- A shot lists the entries it uses in `choreography_ids`, and its movement text is built from their moves.

### continuity
- `rules`: short world rules that hold in every shot (set geography, time of day, "no new characters"). These go into every prompt: at most 8, each under 200 characters.
- `known_exceptions`: allowed deviations.
- `production_bible`: a `.md` or `.txt` of plain prose about the world and tone (read into the Production Bible; first 1,500 characters).

### qa
- `readiness`: `READY`, `READY WITH WARNINGS` or `NOT READY` (shown in the import review). Be honest: use `NOT READY` if a required picture is missing, and list what is missing in `report` (a `.md`).

## 5. Shots

One entry per shot, in story order. For a 3 to 4 minute song, plan **40 to 70 shots of 2.5 to 6 seconds**. A shot that carries more than one idea cannot be rendered as one generated clip: split it.

```json
{"id": "shot_014", "sequence_id": "seq_chorus1", "song_section": "Chorus", "lyric_cue": "I AM YOUR MOTHER!",
 "environment_id": "env_home", "scene": "Adeyemi home pageantry",
 "character_ids": ["char_queen", "char_zara"], "wardrobe_ids": ["wardrobe_queen", "wardrobe_zara"], "prop_ids": ["prop_constitution"],
 "action": "Queen Bee opens the giant Constitution on the platform; Zara watches, arms folded.",
 "performance": "Queen: triumphant, chin up. Zara: unimpressed, still.",
 "expression": "Queen: broad confident smile. Zara: flat, one raised eyebrow.",
 "framing": "Medium two-shot", "camera": "Slow push-in", "lighting": "Gold theatrical key, warm room fill",
 "choreography_ids": ["choreo_queen"], "continuity_notes": ["Glasses stay above the forehead", "Constitution is open to the middle"],
 "reference_assets": ["char_queen", "char_zara", "prop_constitution", "env_home"]}
```

What each field does:

| Field | Used for |
|---|---|
| `id` | Unique. Kept as the shot's plugin id. |
| `sequence_id` | Groups shots into a scene (a new scene starts when it changes; else when `environment_id` changes). Name scenes by story beat. |
| `start_seconds`, `end_seconds` | **Only if verified against the audio.** Otherwise leave them out (null). PULSEFRAME places the shot by `lyric_cue`, else `song_section`. |
| `lyric_cue` | The **exact words of one line from the lyrics file** (punctuation and case are ignored; a partial line is fine if it is unique). The shot is placed where that line is sung. Use it whenever the shot is on a lyric line. Do not paraphrase. |
| `song_section` | The section the shot is in, using the lyrics file's tags: `Intro`, `Verse 1`, `Pre-Chorus`, `Chorus`, `Bridge`, `Final Chorus`, `Outro`. For the nth shot of the same section, PULSEFRAME uses the nth matching section. |
| `environment_id` | The place. Its picture is sent with the shot. |
| `scene` | A short label for the place's state in this shot (for example `Adeyemi home pageantry`); added to the place description in the prompt. |
| `character_ids` | Everyone **visible** in the shot. They get their sheets sent, and their names appear in the prompt. Never list someone who is not on screen. |
| `wardrobe_ids`, `prop_ids` | Outfits and props **visible** in the shot; their pictures are sent. |
| `reference_assets` | Asset ids whose pictures should be sent, in addition to the shot's people, place, outfits and props. Count every picture: keep the total for a shot to **4 to 6** (the people, the place, at most one or two key props). More than the model accepts are dropped, lowest priority first. |
| `action` | What the camera sees, concretely, in one or two sentences, with named people. Present tense. Not mood, not theory. |
| `performance` | The acting: intention and body, per person. |
| `expression` | The face, per person. Specific ("tight smile that fades"), never generic ("smiles"). |
| `framing`, `camera`, `lighting` | Lens and shot size; camera movement (one move at most); light. |
| `choreography_ids` | Which movement entries apply. |
| `continuity_notes` | Facts to keep from the previous shot (hands, props, positions). |

Not used: `generation_prompt_file`, `transition`, `planned_coverage`, `source_reference`, `timing_confidence` (harmless to include, never read).

Writing rules for shot text:

- Describe **one** primary action per shot. Cut away for the next beat.
- Never ask for readable text on screen (signs, titles, charts, captions). Describe the object ("a gold-lettered title banner") and let text be added in editing; models cannot spell.
- No camera moves that need more than one cut, no "montage" shots, no impossible durations. A shot is a single generated clip of 2.5 to 6 seconds.
- Keep the same people, outfits and place geography as the references: do not add characters or change outfits in a shot.
- Do not describe a character's look in shot text; the pictures and `locked_rules` carry it. Do describe what they do.

## 6. The lyrics file

Plain UTF-8 text, **only** section tags and lyric lines:

```
[Intro]
Children!
Come downstairs!

[Verse 1]
Nine months I carry you,
Now you tell me, "Mummy, no"?
```

- Tags are `[Intro]`, `[Verse 1]`, `[Pre-Chorus]`, `[Chorus]`, `[Bridge]`, `[Final Chorus]`, `[Outro]`.
- Every `[...]` line starts a new section. **Do not use `[Singer Name]` tags** for who sings; write the singer in the shot's `performance` instead.
- No markdown (`**bold**`, `# headings`), no metadata lines (`Style:`), no stage directions. (PULSEFRAME ignores a `**Style:**` line and strips `**`, but other formats become lyric lines.)
- Spoken lines that are in the recording belong in the file (they are part of the audio). Lines that are not in the recording must not be.
- The lyrics text must match what is actually sung, line by line. PULSEFRAME aligns them to the audio; the shots' `lyric_cue` text is matched against these lines.

## 7. What PULSEFRAME does with all this

1. Creates the project from the song and the lyrics, **listens to the song** (tempo, beats, sections) and aligns the lyrics.
2. Files every asset in the Reference library, keeps `locked_rules` with it, copies the pictures into the project.
3. Places each shot on the song (its times, else its `lyric_cue`, else its `song_section`), cuts on the beat, and turns the shots into the shot plan.
4. For each shot, sends: the pictures of the people, outfits, place and props it names (in that priority order, within the model's limit) plus the prompt built from `visual_style`, `locked_rules`, the shot's text and `continuity.rules`.
5. Nothing is rendered or billed during import.

## 8. On-screen text, titles and overlays

Image and video models cannot reliably spell, so text that must read correctly (a title card, a sign, an org chart, a caption) is **not** drawn by the model. PULSEFRAME draws it over the finished film at export, from an `overlay_map.json` in the package. It is read, and it works, so use it.

`overlay_map.json` is a list; each entry:

```json
{"id": "overlay_title", "text": "I AM YOUR MOTHER!", "section": "chorus1", "file": "assets/overlays/TEXT_TITLE.svg"}
```

- `id`: unique. `text`: what the sign says (shown in the app's list; for a multi-line chart separate lines with ` | `, which also tells PULSEFRAME to centre it instead of putting it in the lower third).
- `section`: when to show it: `intro`, `verse1`, `verse2`, `pre1`, `pre2`, `chorus1`, `chorus2`, `bridge`, `final` (the last chorus), `outro`. Number the section by how many times it has occurred in the song. Several signs in one section are shown one after another through it (up to five seconds each), in the order they appear in the file, so list them in the order they should appear.
- `file`: a **text-sign SVG** or a PNG/JPG/WebP, inside the package. List the file (and `overlay_map.json` itself) in an asset's `files` (a `kind: "style"` item is fine) so it is copied into the project.

Text-sign SVG rules (anything else is refused, and the sign is listed in the app as unusable):

- Only `<svg>` with `width`, `height` (and optionally `viewBox`), `<rect>` and `<text>` / `<tspan>` elements. No paths, circles, gradients, images, scripts, links, `<!DOCTYPE>` or entities. Under 200 KB.
- `<text>` uses `x`, `y` (the baseline), `text-anchor` (`start`, `middle` or `end`), `font-size`, `font-weight` (`bold` or 600 to 900) and `fill` (`#rgb`, `#rrggbb` or a basic colour name). Draw on a transparent background: leave out any full-size `<rect>`.
- One sign per file, with a canvas about as big as its text (a 1600 x 180 canvas for one line is right). PULSEFRAME crops it to the lettering.

In the shot list, describe the object but never the words: `"a banner with gold lettering"`, and let the overlay carry the text. Do not repeat the sign's text in a shot's `action`, or the model will try to paint it and get it wrong. If you make a picture of a sign object (a prop plate of a banner), generate it with the text **blank**.

## 9. Final checklist: do not hand over a package until every line is true

1. Every character, outfit, prop and environment (one item per environment variant a shot names) has **one or two PNG/JPEG/WebP files** in its `files`; no `.md`, `.pdf`, `.svg` or `.json` in any asset's `files`.
2. Every character has **their own** sheet (not just a group lineup).
3. Every id used in a shot (`environment_id`, `character_ids`, `wardrobe_ids`, `prop_ids`, `reference_assets`, `choreography_ids`) exists in `assets` or `choreography`; every id is unique.
4. Every file path in the manifest exists in the ZIP, is relative, uses forward slashes, and has no spaces.
5. The song file and `lyrics.txt` are included; the lyrics are plain text with only `[Section]` tags and lyric lines.
6. Every shot has a `lyric_cue` (copied from the lyrics file) or a `song_section`; no shot has invented times (`start_seconds`/`end_seconds` are absent unless verified).
7. Every shot has `action`, `framing`, `camera`, `lighting`, `performance`, `expression` filled with specific text, and between 1 and 6 pictures worth of references.
8. 40 to 70 shots for a 3 to 4 minute song, each a single action of 2.5 to 6 seconds, in story order, covering the whole song.
9. `locked_rules` are short (under 250 characters each, under 6 per asset) and `continuity.rules` are under 8.
10. `qa.readiness` is honest, and `qa.report` lists anything missing, mismatched or unverified.
11. The package is a ZIP named `<project>.pfproducer`.

If any line cannot be made true, say so plainly in `qa.report` and set `readiness` to `NOT READY` rather than papering over it.

## 10. Reference: what PULSEFRAME reports when it opens a package

The import review shows counts, any missing files, how many assets have **no picture** ("written specs only"), whether lyrics were included, and the readiness. Treat anything in that list as a defect in the package, not as something the user should fix by hand.
