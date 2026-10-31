# Unified Studio: Phase 0 (repository audit, capability matrix and plan)

Status: **plan only, no code written.** Version audited: 0.31.1, `main` at the commit after the Performance Director steps three to five. Nothing in this file is a promise of a feature; what is not built is marked so.

## 1. What the audit found (the three facts that shape everything)

1. **The film is already assembled shot by shot, with a hook for a per-shot filter.** `export.build` cuts the timeline into whole-frame segments, renders each shot to its own small video (a take, a Ken Burns still, or a slate), applies the shot's colour correction (`colormatch.filter_for`) inside that one render, then joins the parts, adds transitions, captions, overlays, layers and the mixed sound. The per-shot cache key already includes the grade. So **a grade or a LUT is one more filter in a chain that exists and is cached**; no new renderer is needed for it.
2. **The "preview" is already a real export of a window.** `export.build(..., window=(a, b))` renders only that part through the same code. A preview that agrees with the export is therefore not a second renderer; the work is to keep it that way for every new operation (a frame grabbed through the same filter chain).
3. **Edit decisions live in loose JSON files beside the derived render project** (`grade.json`, `overlays.json`, layers, per-shot transitions in the shot state, captions). `make.sync` rewrites `production.json` and `project.json` of the render project and does not delete these, so they survive today, but they are not one versioned model. This is the risk the brief names ("derived render projects may be regenerated"). The film backup (`filmbackup.py`) already snapshots every `.json` it finds, so these are backed up, but there is no single schema, no version field on them and no undo across them (layers have their own undo: `test_layer_undo.py`).

The FFmpeg that ships with the engine (7.1, gyan essentials build) has the filters this needs: `lut3d`, `eq`, `colorbalance`, `colortemperature`, `curves`, `colorchannelmixer`, `hue`, `vibrance`, `chromakey`, `colorkey`, `despill`, `zscale`, `colorspace`, `tonemap`, `overlay`, `blend`, `alphamerge`. **Verified on the development machine only; the installed app's copy must be checked the same way before a release.**

## 2. Capability matrix (the brief against what exists)

| Brief item | Today | Where | Gap |
|---|---|---|---|
| Timeline with scenes, shots, dialogue, soundtrack, layers lanes | exists | `Studio.tsx` Timeline, `LayerLanes`, `CueLanes`, `VoiceLanes` | multiple video tracks, ripple/slip/slide/roll, magnetic mode, groups, nesting |
| Trim, split, move shots | partial | shots contract (`shots.py`, `shotsound`, pacing) | clip-level trim of a take inside a shot; ripple; snapping rules |
| Transitions | exists (cut, dip black/white, dissolve, wipe, slide, whip, zoom) | `transitions.py`, `export._enter` | length per cut exists; no curves, no custom |
| Keyframes | partial | layers carry keyframes (`layerkit.py`, `overlays.py`) | for clips and effects; easing curves editor |
| Time remap, speed ramps, freeze | missing | (hold of last frame exists: `tpad`) | all |
| Undo / redo | partial | layer undo; `director` undo; film backups | one undo across edit decisions |
| Autosave / recovery | exists | `safeio` atomic writes, film backups, crash report | none for the new model yet |
| Proxy media | missing | | all |
| Basic colour correction | partial | `colormatch.py`: per-shot Y/U/V straight-line match, film-wide cast removal, denoise, grain | exposure, contrast, saturation, temperature, tint, lift/gamma/gain, per-scene and per-clip user grades |
| LUTs (`.cube`) | **missing** (FFmpeg has `lut3d`, nothing uses it) | | parser and validator, library, intensity, scope, colour-space labels |
| Curves, HSL qualifiers, scopes, masks | missing | | all (later) |
| Image-artifact correction | exists | `colormatch` cast fix, `cleanup.py`, `handfix.py` | must stay first in the chain, see section 4 |
| Colour pipeline consistency | partial | every part labelled BT.709 studio range (`enc` in `export.build`) | explicit input/output space per LUT and per clip; HDR is out of scope for now |
| Smart Editor (agentic) | partial pieces | `pacing.py`, `composition.py`, `supervisor.py`, `director_audit.py`, Performance Director arcs and beats | no proposal object with preview, accept/reject and versions |
| Motion graphics | partial | text/shape/image layers with fades, movement, keyframes, templates and styles (`overlays.py`, `layerkit.py`), shapes (`shapes.py`) | motion paths, parenting, blend modes, masks, easing editor, prompt-to-motion |
| Compositing (alpha, chroma key, masks, blend) | missing in the UI | FFmpeg filters available | all |
| Tracking, rotoscoping, segmentation | missing | | all (needs a library; not claimed) |
| Style DNA | partial | `styles.json` (117 looks), per-scene/shot looks, `figures`/`figures_avoid` wording for 24 looks, animation principles | structured DNA profile per look; import-from-reference; a Storybook 2.5D preset |
| Performance integration | built | Performance Director (beats, nudges, arcs, flags) | the editor does not read it yet |
| Presets (production, social, series) | partial | looks, acting profiles, nudges, delivery presets in `export.py` | no preset engine, stack or series workflow |
| Export, hand-off | exists | `export.py` presets, `interchange.py` (EDL, OTIO, FCPXML), `editor_export.py` (Premiere, Resolve) | grades are not in the hand-off files yet |
| Spending approval | built | `paidops.py`, backend-validated approvals | any new paid step uses the same pattern |

## 3. Proposed architecture

Principle: **one new versioned model beside the existing stores; the existing stores keep working and migrate into it one at a time.** Nothing is replaced in one step.

```
<film>/edit/edit.json          {"schema": 1, "revision": n, "grades": {...}, "luts": [...], later: "tracks", "keyframes", "compositions"}
<film>/edit/history.json       the last N revisions (what changed, when, by whom: you or a suggestion you accepted)
~/.filmcrafter/luts/           imported .cube files (copied in, hashed, never edited)
```

- **It lives in the film, not in the render project**, so regenerating the render project can never lose it. The render project reads it at export time, the same way it reads `grade.json` today.
- **Scope order** (more specific wins, as for looks): clip, shot, scene, film. A grade is a short ordered list of operations; the effective grade of a shot is film, then scene, then shot, then clip, each applied in that order. A locked shot or an approved take is never changed by a higher scope without a prompt.
- **Every operation has a version, a name and a pure FFmpeg translation** (`to_filter(op) -> str`, numbers only, no user text ever goes into a filter string). The same function builds the export chain and the preview frame, which is how preview and export stay equal.
- **Old projects**: no `edit/edit.json` means exactly today's behaviour. Opening writes nothing.
- **Existing colour matching stays and goes first** in the chain: it corrects the AI's artefacts (the film-wide cast, shot-to-shot drift); the new grade is the creative layer on top. The brief asks to preserve intentional warm light, so the cast fix is measured before the grade and never runs after it.
- **Preview**: a frame (or a short window) rendered through `export.build(window=...)`, a before/after pair from the same frame. No second renderer. A real-time WebGL preview is deliberately deferred: it would be a second implementation that has to be kept equal to FFmpeg.

## 4. Milestone 1 (what I would build first, and nothing more)

**Colour Studio, basic.** Each item has a test that a number in the model changes the filter string and the exported frame.

1. `edit.json` v1 with `grades` at film, scene and shot scope (no clip scope yet: a shot has one take in the export today).
2. Operations: exposure, brightness, contrast, saturation, vibrance, temperature, tint, gamma, lift/gamma/gain, hue; each with sane limits so a grade cannot clip silently (a "clipping" note in the result when the chain would push values out of range).
3. `.cube` LUT import: strict parser (1D and 3D, size limit, domain, no code, no paths), copied into the LUT folder by content hash, and each LUT labelled **technical** (a colour-space transform) or **creative**, with the input/output space it expects. A LUT with no stated expectation is allowed only as creative and says so. Intensity is a mix between the graded and ungraded picture. Rec.709 in and out only; HDR and log inputs are refused with a plain message rather than guessed.
4. Apply to a shot, a scene, the film. Before/after on one frame. Presets saved as "My looks", favourites, search.
5. Export: the grade chain is added to the per-shot filter, so the cache key changes only when the grade does. The interchange and editor hand-off files note the grade (they cannot carry it faithfully; they say so).
6. UI: one **Color** sheet from the rail, in the style of the Performance sheet (tabs, compact, keyboard reachable, in the harness and the accessibility scan the day it exists).

**Style DNA and the Cinematic Storybook 2.5D preset** (separate, bounded):
- A `style_dna` block on a look (character design language, proportions, line weight, surfaces, palette, shadow construction, lighting, background, camera language, motion, negative constraints), turned into model-specific wording by the same path that already uses `figures`.
- The preset is built **from the five reference screenshots, which I have not seen yet.** It captures their shared grammar, never their characters or scenes. Six variations (Historical Storybook, Biblical Epic Illustration, Modern Urban Storybook, African Folktale Illustration, Fantasy Storybook, Educational Documentary Illustration) are wording and palette variants, labelled as visual variations, not historical reconstructions.
- Reference import (analyse images, propose a DNA, edit, save) is **not** in this milestone: it needs an image-understanding call, which is a paid, confirmed step; the plan is a free structural editor first.

**Not in Milestone 1:** scopes, curves, qualifiers, masks, power windows, clip-level scope, proxies, keyframed grades.

## 5. Later milestones (each releasable alone)

- **M2 Editing foundation**: clip model in `edit.json`, trim/split/ripple/snap, one undo across `edit.json`, keyframes and easing, speed ramps and freeze, proxies.
- **M3 AI Director's Edit**: a *proposal* object (what, why, clips affected, preview window, accept/reject, history). Start with four operations a test can check: keep a hesitation the Performance Director marked, give a reaction more time, remove an unmotivated camera move, flag a continuity jump. No operation applies without acceptance. Performance data (beats, arcs, nudges) is read, never changed.
- **M4 Motion graphics**: promote the existing layers into the composition model; motion paths, parenting, blend modes, easing editor; templates exist.
- **M5 Compositing**: alpha, chroma key with spill suppression, masks, blend modes using FFmpeg filters; validated on real footage before it is named supported.
- **M6 Advanced VFX, prompt-to-motion**: segmentation, tracking, rotoscoping need a library and real footage; prompt-to-motion builds editable layers from the existing primitives and never returns a flattened video when layers can do it.
- **Preset engine** (the addendum): after M1 and M2 there is something real to configure. First slice: a preset is a named bundle of existing settings (look, acting profile, grade, delivery) applied through the same scope rules, never over a locked or approved choice. The series workflow (micro-drama) is a separate project with its own plan.

**Status (2026-10-31).** Milestone 1 built: `grading.py` and the Color sheet (basic corrections, `.cube` LUTs with colour-space labels, scopes film/scene/shot, saved looks, undo, preview agreeing with the export, clipping note), and Style DNA with the Cinematic Storybook 2.5D looks (`style_dna.py`, written from the owner's own references; the reference pictures are not shipped). Not in M1, as planned: scopes, curves, qualifiers, masks, clip-level grades, proxies, keyframed grades, reference import. The installed app's ffmpeg is still to be checked.

**Status (2026-11-03).** Milestone 2 is built (the cut, its operations and undo, the export, the cut lane, the studio following the cut, preview copies, damaged-record safety; see UNIFIED_STUDIO_M2_PLAN.md). Milestone 3 has its first operations: the Smart Editor (two explainable rules, three of ten editing styles, previews, accept and reject, plain requests). Not built: more rules and styles, continuity and transition suggestions, motion graphics (M4), compositing (M5), advanced VFX and prompt-to-motion (M6), the preset engine.

**Status (2026-11-04).** Milestone 4 has its first slice: eight built-in motion graphics (lower third, title card, chapter title, place and time, callout, quote, big number, end card) that become ordinary grouped layers, and glow and blur effects on layers (`motion_templates.py`, `overlays.py`, `MotionGraphics.tsx`). Not built: blend modes, masks, parent and child layers, motion paths, keyframe curves beyond the existing animations, and prompt-to-motion.

**Status (2026-11-05).** Milestone 5 has its first slice: blend modes, shape masks and a colour key with spill suppression on layers (`composite.py`, the Mix and effects section). Not built: video-clip layers (so no keying of footage), animated or drawn masks, tracking, rotoscoping.

## 6. Risks

| Risk | Why it matters | Answer |
|---|---|---|
| Preview and export diverge | the brief's central test | one filter function for both; a test compares the preview frame to the exported frame |
| Colour space mistakes with LUTs | wrong results that look "fine" | refuse unknown spaces; label every LUT; Rec.709 only at first |
| Clipping and double-grading | AI images are already contrasty and tinted | colour matching first; a clipping report; a grade never stacks silently (it replaces the same-scope grade) |
| Cache growth | every grade change re-renders its shots | the key already isolates shots; a grade at film scope re-renders everything: say so before applying and show the shot count |
| Render-time on long films | grading adds a pass per shot | same pass as today (one filter chain per shot), not a new pass |
| FFmpeg differences in the installed app | the dev machine is not the installer | a start-up self-check of the needed filters; the feature greys out with a reason if one is missing |
| Scope creep | five applications at once | the milestone list above, each with its own tests and an honest report |
| Hand-off fidelity | EDL, XML cannot carry our grades | say so in the export notes |

## 7. What will not be claimed

No effect is called supported until a test renders it and compares the frame. No LUT is called colour-accurate without its stated space. No segmentation, tracking or rotoscoping is claimed until a library is chosen and tried on real footage. No AI result is called verified without a recorded run, and no paid step runs without the price shown and a yes.

## 8. Decisions for the owner

1. **Approve Milestone 1** as scoped in section 4 (basic Color Studio with LUTs, and the Storybook preset).
2. **Send the five reference screenshots** for the Storybook preset (and say whether they are yours to use as references).
3. **LUTs**: Rec.709 only for now? Which LUT collections do you want to try (so I can test with files that are licensed for it)?
4. **Edit data location**: confirm the new model lives in the film folder (`<film>/edit/`), not in the render project.
5. **Release**: nothing here is pushed or released without your say-so.
