# Musical mode: plan

Status: phases 1 and 2 shipped in 1.2.0 (2026-10-01). Phases 3 and 4 shipped in 1.3.0 (2026-10-02): script to show (marker and screenplay formats), flow between items, costumes per act, subtitles and chapters, intermissions, ambience, show budget and show-wide overnight, and recorded dialogue. Native dialogue shipped in 1.6.0 (tuned in 1.6.1): a per-scene switch lets the video model speak the lines (Veo 3.1, Kling 2.6, Seedance 2 and others with sound), with free estimated line timings, a sound-on render, and an export built from each take's own sound. It has been tested with synthetic media and still needs proving on real, paid renders. Voices: MiniMax and ElevenLabs (1.5.0), plus your own recordings. Songs: you may bring your own, or make one with ElevenLabs Music (1.5.0); there is no Suno because it has no public API. Dialogue: generated voices + lip-sync, or native.

## Goal

Make a whole musical, or any multi-song production (a visual album, a stage show, a short film with songs), in one PULSEFRAME project: several **numbers** (songs) and **spoken scenes**, one cast that looks the same everywhere, one look, and one finished film.

## What already exists

Most of the work is reuse. Today one project = one song, and each song already gets everything a musical number needs:

| Need | Already in PULSEFRAME |
|---|---|
| Plan shots on the music | song analysis, beat-timed shot plan, script import (scenes, ACTION, DIALOGUE) |
| Several singers | per-performer lyric lines, lip-sync per performer, lip-sync check |
| Staging | choreography and acting profiles per character |
| Consistent cast | Reference library with locked designs, Production Bible, continuity |
| Control and cost | Select & review, start and end frames, quality ladder, overnight ComfyUI, routing modes, budgets |
| Voices and dialogue | **new**, but the providers are ready: ElevenLabs, MiniMax Speech and Kokoro on fal (checked); Veo 3.1, Seedance 2 and Kling 3 can also speak lines themselves |

## Design

### 1. A Show contains items

A **Show** is a new kind of project: an ordered list of items, grouped into acts.

- **Number**: a song. Internally it is a normal PULSEFRAME project inside the show folder, so the whole existing song workflow (wizard, Studio, Select & review, render, review) works unchanged.
- **Spoken scene**: dialogue (and optional underscore or ambience) with no song.
- **Transition**: a card, black, or an end-frame flow from one item into the next.

```
My Musical.pulseshow/
  show.json            acts, item order, show-level settings
  cast/  bible.json    the shared Reference library and Production Bible
  items/01 Overture/   a normal song project
  items/02 Scene 1/    a spoken scene (its dialogue audio acts as its "song")
  items/03 I Want/     a normal song project
  exports/
```

### 2. One cast and one world

The Reference library, locked designs, Bible, look and routing live at **show level**. Each item inherits them (the same inheritance the library already uses for project, scene and shot), and can still override per item, for example a costume change in Act 2. A character added once is in every number.

### 3. Spoken scenes, built on the song pipeline

The key idea: give a spoken scene an audio track, and the rest of PULSEFRAME already knows what to do.

1. Write or import the dialogue (from the script's DIALOGUE blocks), one line per character.
2. **Voices**: each character gets a voice once (ElevenLabs, MiniMax, or Kokoro as the cheap option; price shown first). Lines are generated, with pauses you can adjust, plus optional room tone or underscore.
3. That audio becomes the scene's track. Lines are timed like lyrics (existing Whisper alignment), shots are cut on the lines, and speaking close-ups get the existing lip-sync pass.
4. Alternative per scene: **native dialogue** on Veo 3.1, Seedance 2 or Kling 3 (the model speaks the line). Faster, less control over the voice. Offered only on models that support it.

You can also bring your own recorded dialogue (actors' takes) instead of generated voices.

### 4. The Show timeline and export

- A Show view: acts and items in order, each with its status (planned, rendering, ready), length and cost so far. Drag to reorder.
- Transitions between items, including **flowing** the last shot of one number into the first shot of the next (start and end frames across items).
- **Export the whole show** as one film, or any act or item. Optional chapter markers and subtitles (lyrics and dialogue are already timed).

### 5. Importing a whole musical

- A full script (PDF or text) where songs are marked: PULSEFRAME splits it into numbers and scenes and asks for the audio file of each song.
- PULSEFRAME Producer could output a show package (several numbers plus the shared cast) for the existing importer.

## Phases

| Phase | What you can do at the end | Size |
|---|---|---|
| **1. Show container** | Create a show, add existing or new songs as numbers, one shared cast, Bible and look, a show timeline, export the whole show | Large |
| **2. Spoken scenes** | Dialogue scenes with generated or recorded voices, lip-synced; per-character voice casting | Large |
| **3. Script to show** | Import a full musical script; split into numbers and scenes; flow between items; costume changes per act | Medium |
| **4. Polish** | Native-dialogue option, underscore and ambience, subtitles and chapters, act intermissions, show-level budget and overnight rendering | Medium |

Each phase ships on its own with tests and a real test render, like the 2.0 phases.

## Cost reality

A 90-minute musical is roughly 900 to 1,400 shots. On cloud video models that is about $100 to $500 in renders; voices add a few dollars per hour of dialogue. Hybrid or Local First (ComfyUI) cuts this sharply. The show view will show cost so far and an estimate for the rest, and the existing budgets and confirmations apply to every render.

## Decisions for you

1. **Songs**: you supply the recorded songs (assumed; PULSEFRAME does not generate music). Correct?
2. **Default voice provider**: ElevenLabs (best quality, priciest), MiniMax (good, cheaper), or Kokoro (cheapest)?
3. **Dialogue default**: generated voices + lip-sync (more control), or native-dialogue video models (simpler)?
4. **Scope first**: start with Phase 1 + 2 (a show of numbers and spoken scenes) as the first musical release?
