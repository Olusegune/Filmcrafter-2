# Unified Studio, milestone 2: the editing foundation (design, before any code)

Status: **design only.** Builds on `docs/UNIFIED_STUDIO_PLAN.md` (the audit) and milestone 1 (Color Studio, shipped in `59fa30a`). Nothing here is built or claimed yet.

## 1. What the audit of our own timeline found

1. **Shots are laid end to end from their contracts; there is no clip to trim.** `make.sync` builds the render project from the Shot Contracts (`shots/<id>/contract.json`), each shot has a duration, and the export (`export.build`) cuts the film into whole-frame segments, one per shot, from the take chosen for that shot. A take is used from its start for the shot's length (a shorter take holds its last frame). There is no in-point, no out-point, no overlap and no second video track.
2. **Time is float seconds with a fixed 24 fps.** Boundaries are `round(seconds * 24)` (`export.FPS`). Every other thing in the film (voices, sound cues, captions, layers, overlays) is also timed in seconds on the film's own clock, and the mix and voice items are placed from the segment positions the export computes. That is why trimming a shot has knock-on effects on everything else, see the risks.
3. **Transitions belong to the shot they lead into** (`transitions.py`): every cut keeps its frame; a transition is a taking-away of the previous shot's held last frame over the first moments of the new one. They do not overlap the two takes.
4. **Edits to the film's decisions already have three separate homes**: shot contracts (`shots.py`: split, join, duplicate, move, remove; a `_removed` folder, never deleted), layers and overlays (their own undo file `cache/undo-layers.json`), and now `edit/edit.json` (grades). There is no single undo.
5. **The preview is a real export of a window** (`export.build(window=...)`), so preview and export already agree; the new work must keep that true.
6. **Hand-off** (`interchange.py`: EDL, OTIO, FCPXML; `editor_export.py`: Premiere and Resolve) is built from the shots and will not know about trims until it reads the same model.

## 2. What filmcraft teaches (read with permission of its licence, ideas only)

Source: the public repository `storytold/filmcraft` (Rust, MIT OR Apache-2.0, alpha by its own description). We use none of its code; we read its design notes and its time crate to learn from a team that has solved the same problems. The ideas worth taking, and what I checked:

| Idea | What it does there | What we take |
|---|---|---|
| **Exact integer time** | One tick base, 254,016,000,000 per second, which divides evenly into 23.976, 24, 25, 29.97, 30, 48, 50, 59.94, 60 and 120 fps and the common audio rates; frame to tick rounds up at boundaries, tick to frame rounds down; snapping to a frame has "nearest" with ties going down | The same constant (I checked that it is 2^12 x 3^4 x 5^6 x 7^2, so every common frame duration is a whole number of ticks), as the unit of the new sequence model. No floating seconds in edit maths. |
| **Source time is separate from timeline time** | A clip has `start` on the timeline and `source_in` in the media; keyframes are in media time | Trimming or splitting a clip never moves its keyframes or its grade. |
| **An edit is a function on a copy** | Edits work on a clone and write it back only when they succeed | Every operation validates the whole sequence (sorted, no overlaps, positive durations, inside the take) before it is kept. |
| **Undo by snapshots** | The old project value is pushed on a stack of 200; undo and redo swap them | Simple and hard to get wrong. We keep the last 40 (a film's edit record is small), in the file, so undo survives closing the app. |
| **One command table** | Every menu, the command line and the agent call the same command ids | Our Smart Editor (milestone 3) will propose the same operations the person uses by hand, so a proposal is just a list of commands that can be previewed and undone. |
| **Migrations as a chain of single steps, never edited once shipped; refuse a newer file; back up on the first save over an older one** | `schema_version`, `vN_to_vN1` | Same, applied to `edit.json` (milestone 1 is schema 1). |
| **Atomic saves, recovery journal** | temp file, fsync, rename | We already do atomic writes (`safeio`); add a recovery journal for the edit session. |
| **Proxies change speed, never size or export** | Export always reads the original | Same rule. |
| **A CPU reference is the oracle** | the GPU path is tested against it | Our oracle is the export; a faster preview, if one is ever added, is tested against it. |

One warning from the same notes: their documentation says "no floating-point seconds in edit maths" and the code still multiplies by speed in floating point in two places. Our rule will be tested, not only stated: a test searches the new edit module for float time.

OpenCut and effectcraft are not needed for this milestone (a web editor mid-rewrite, and a compositor; effectcraft is for milestone 4).

## 3. Design

### 3.1 Time (`edit_time.py`)
- `TICKS_PER_SECOND = 254_016_000_000`, `FrameRate(num, den)` exact; `tick_of_frame`, `frame_at_tick`, `snap`, `snap_nearest`, `seconds_to_ticks` (round half up, once, at the edge) and `ticks_to_seconds` (display only).
- The film stays at **24 fps** for now. The unit is chosen so a film with another frame rate later is a setting, not a rewrite.
- **Conformance test:** for every shot of existing test films, the frame boundaries the new model produces equal the ones `export.build` produces today (`round(start * 24)`), so nothing moves for a film that is never edited.

### 3.2 The sequence (in `edit/edit.json`, schema 2)
```
"sequence": {"fps": [24, 1], "revision": n,
  "tracks": [{"id": "V1", "kind": "video", "locked": false, "hidden": false, "muted": false,
              "clips": [{"id": "c1", "shot": "S01-01", "start": ticks, "source_in": ticks, "duration": ticks, "take": null}]}],
  "markers": [{"id": "m1", "at": ticks, "name": "..."}], "ranges": [{"id": "r1", "start": ticks, "end": ticks, "name": "..."}]}
```
- **No `sequence` means exactly today's behaviour:** the sequence is derived from the contracts, never written by opening a film. The first edit that needs it **conforms** it (writes it once, with a backup). Milestone 1's grades are untouched by the migration (schema 1 to 2 adds `sequence`, nothing else).
- **One video track** in this milestone (V1, the film's shots). More tracks, nesting and groups are later; the model already has a list of tracks so they will not need a migration.
- A clip refers to a **shot** (and optionally a pinned **take**), never to a file path, so regenerating a take or approving another one still works; `source_in` and `duration` are in the take's own time.
- **Reconciling with the contracts:** a shot added or removed after the sequence was conformed appears in the sequence as an item that needs a decision (kept at its place, flagged, never silently dropped or added in the middle of your edit). The screenplay and the contracts are never written.

### 3.3 Operations (`edit_ops.py`, pure functions on a copy)
First set, each with tests that it keeps the invariants:
`trim_in`, `trim_out` (regular and ripple), `split` (razor at a time), `delete` and `ripple_delete`, `move`, `roll`, `close_gap`, `set_marker`, `set_range`, `lock/hide/mute track`.
Second set (later in the milestone): `slip`, `slide`. **Deferred, with reasons:** speed changes, ramps and freeze frames (they change duration vs source and affect audio; own sub-milestone), keyframed transforms and crop (need the compositor decisions of milestone 4), nested sequences and groups.
- **Snapping:** a pure function from a time to the nearest of: cuts, markers, the playhead, dialogue starts and ends (from `laneMath.snapPoints`, which exists), within a tolerance in frames.
- **Magnetic mode** is a flag that makes `move` and `trim` ripple.

### 3.4 Undo and redo
- Each operation stores the sequence as it was (and, from this milestone, also the grades and saved looks) in one revision log, so **one undo covers a trim, a split and a grade alike**. Milestone 1's `undo` is extended, not replaced; its tests keep passing.
- Redo keeps the undone steps until a new edit is made.
- Layers keep their own undo (`undo-layers.json`) for now; unifying them is listed under later work because the layers have their own tests and a different file.

### 3.5 Export and preview
- `export.build` reads the sequence when there is one: each clip becomes a segment with `-ss source_in -t duration` applied to its take (placed after `-i` for frame-accurate seeking), the same cache key idea (the key already includes the grade; it will include the trim).
- Everything placed from segment positions (the mix, the voices, `vo_items`) follows automatically.
- A ripple shortens or lengthens the film, so **the soundtrack, layers, overlays and captions that sit on the film's own clock need a stated rule** (see the risks). The preview stays an export of a window, so the two cannot disagree by construction.

### 3.6 Proxies, autosave, recovery, shortcuts (last in the milestone)
- Proxies: a low-resolution copy per take in the film's cache, used only by the preview, never by the export (as in filmcraft); regenerated when the take changes.
- Recovery: a small journal beside `edit.json` written before each change and removed after the save, so a crash mid-edit is detected on open and offered back.
- Shortcuts: a table of command id to key, the defaults below, editable in Settings, stored in the user's settings.

### 3.7 Interface
- The existing timeline's **Edit** mode gets: trim handles on shot cards, **S** to split at the playhead, **Delete** and **Shift+Delete** (ripple), **Ctrl+Z / Ctrl+Y**, **M** for a marker, a snap toggle and a ripple toggle, lock/hide/mute on the track header. **Simple Edit** shows none of this (no handles, no toggles); both read the same sequence.
- Keyboard-only editing is a requirement (every command reachable from the palette and by keys), and the new controls join the harness and the accessibility scan on the day they exist.
- The preview plays a grade and a trim the same way, because it is the export.

## 4. Sub-milestones (each releasable alone)

| | Delivers | Proof |
|---|---|---|
| **M2a** | `edit_time.py`, sequence schema 2 and its migration, the conform step, the derived sequence, export of trims, the revision log extended to cover the sequence | conformance test with today's boundaries; a trimmed clip's exported frames equal the expected source frames (frame-numbered test footage); old projects open with no write |
| **M2b** | the operations above with snapping, their commands and undo/redo | invariant tests (property-style: random operation sequences never break order, overlap or range); every operation undone returns the identical sequence |
| **M2c** | the Edit-mode controls, shortcuts, markers, harness scenes, accessibility | component and browser tests; keyboard-only run |
| **M2d** | proxies, recovery journal | a killed export or edit is recovered; export never reads a proxy |
| **later** | speed, ramps, freeze; keyframed transforms; groups and nesting; unified layer undo; slip and slide in the UI | |

**Status (2026-11-01).** M2a and M2b built: `edit_time.py`, `sequence.py`, `sequence_derive.py`, `edit_ops.py`, `editing.py`, the export reading the cut, the audio offsets, one undo and redo, the Rust door and API types. Free layers and captions stay where they are on a ripple (the owner's choice was assumed: recommended default); they are not yet flagged when they fall past the end (to do in M2c, with the controls). Split `source_in` and trims on image takes are not applicable. Not built: M2c (controls, shortcuts, markers UI), M2d (proxies, recovery journal).

**Status (2026-11-02).** M2c built: the cut lane, toolbar and keys in the timeline's Edit mode, with a note when a layer now starts after the end of the cut. The voice, cue and layer lanes still draw at the planned times (they are not yet moved with a ripple); the player still plays the plan, Preview plays the cut. Shortcuts are listed in one table but are not yet remappable by the person. M2d (proxies, recovery journal) is not built.

## 5. Risks

| Risk | Answer |
|---|---|
| **Layers, overlays, captions, cues and the soundtrack are timed on the film's own clock** and a trim or ripple moves the picture under them | Decide the rule with you before M2b: by default **picture-locked items follow their shot** (voices and sound cues already do, being placed from the shot's segment); free layers and captions stay where they are and are flagged when they now fall beyond the end or across a different shot; an option moves them with the ripple. The soundtrack (the music under the film) is never cut by a trim; the film can become shorter than it and the export says so. |
| A trimmed take is shorter than the shot it is in | The clip's range is validated against the take's real length; the film holds the last frame only where it does today and says so. |
| Frame boundaries move for films nobody edited | The conformance test against today's rounding, on every shot of the test films. |
| Contract changes after an edit | Reconcile as items that need a decision; never silent. |
| Hand-off files (EDL, XML) ignore trims | They are changed to read the sequence in M2a, with their own tests; until then they say so in the notes. |
| Float drift creeping back | A test greps the new modules for float time; positions are integers in the file. |
| Too much at once | The sub-milestones above; M2a is useful by itself (a trimmed film exports correctly) even with no new interface. |

## 6. What will not be claimed
No operation is called supported until its test passes, and no frame-accuracy is claimed until frame-numbered footage proves it in an export. Speed changes, groups, nested sequences and keyframed transforms are not in this milestone. No code from other projects is copied; their licences allow it, but their stack (Rust, egui, no FFmpeg) is not ours, and the value here is the design.

## 7. Decisions for the owner
1. **Start with M2a and M2b** (the model, the export of trims, the operations and undo), then the interface in M2c?
2. **The ripple rule for free layers and captions** (section 5): stay where they are and be flagged (recommended), or move with the ripple by default?
3. **Frame rate:** keep 24 fps for now (recommended), with the tick unit ready for others later?
4. **Nothing is pushed or released** without your say-so.
