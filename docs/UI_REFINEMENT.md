# UI/UX refinement pass (0.25.1)

Scope: make the interface consistent and calmer without a redesign: the dark theme, the amber accent and every workflow are unchanged. Started with the voice dialogs the owner marked up; the shared rules now apply app-wide.

## Audit findings, by impact

| # | Finding | Where | Fixed? |
|---|---|---|---|
| 1 | **A real bug, not just looks: the "Hear" button on library voices did nothing** (a red "!" appeared). A check added in 0.24.0 refused audio the voice bucket labels `text/plain`, which is true of about half of ElevenLabs' sample files. Verified against the real library: 3 of 6 refused, now 6 of 6 play. The bytes decide what is audio, not the label. | Voice library | **Yes** (+ regression test) |
| 2 | An amber gradient "Use for …" button on every row of a list: ten identical loud buttons, no hierarchy | Voice library, design options | Yes: a quiet amber-outline "Use this voice" / "Keep this one" (`.btn.sel`) |
| 3 | The model dropdown showed a long description and was clipped | Voice library, design, clone | Yes: short model name in the control, its one-line description under the tabs, a flexible width |
| 4 | Clone dialog: tiny "Choose recordings…" box, unlabelled groups, a disabled button that did not say why | Clone dialog | Yes: three titled groups (recordings, the voice, permission), a real drop area with file chips, and the button says what is missing ("To continue: choose at least one recording, tick the box…") |
| 5 | The bottom navigation button was a full-width amber billboard competing with the screen's own main action | Every film stage | Yes: compact, right-aligned, amber outline with an arrow; still obvious, no longer shouting |
| 6 | "Hear" was a large button with a cryptic "!" on failure | Library samples | Yes: a quiet play control, "Loading", and a plain "Could not play it" with "Try again" |
| 7 | The Search button stacked its icon over its text; heights and paddings of small buttons differed from screen to screen | Dialogs, lists | Yes: one control height rhythm (34 px, small 28 px), inline icon and label |
| 8 | Repeated "Save" in every provider row of Settings used the primary style | Settings | Yes: the quiet selection style |
| 9 | Disabled controls looked the same as enabled ones faded, with no reason | App-wide | Yes: one disabled look (dimmed, desaturated, not-allowed cursor) and the `.why` note pattern for the reason |
| 10 | Focus rings were visible on buttons but not on inputs, selects, tabs or audio | App-wide | Yes: one amber focus ring for every control |
| 11 | Voiceover rows clipped at narrower windows | Voiceover | Yes: flexible columns that stack below 900 px |

## Design-system changes (`src/ui-system.css`, loaded last)

- **Tokens:** control heights (`--ctl-h` 34, `--ctl-h-sm` 28), the amber line and wash, one focus ring. Corner radii stay in `corners.css` (`--r-btn`).
- **Button variants:** `.btn.primary` (the one main action of a view), `.btn` (secondary), `.btn.sel` (the quiet choice repeated down a list), `.btn.quiet` (text-like), `.btn.danger` / `.btn.ghost.danger` (destructive, unchanged).
- **Patterns:** `.why` (the reason a control is off, or a price/consent note), `.dlg-sec` (a titled group in a dialog), `.dropzone` (a file chooser that looks like one), `.cv-item` (a scannable voice row).
- **Rules kept:** every paid or consent step still asks first, and the clone button still needs recordings, a name and the consent box; nothing was hidden to simplify the look.

## Files

`src/ui-system.css` (new), `src/CastVoices.tsx` (library, design and clone panes, sample player), `src/FilmView.tsx` (footer button), `src/Settings.tsx` (per-provider Save), `src/main.tsx` and `src/docshots/main.tsx` (load order), `analysis/filmcrafter_engine/cast_voice.py` (sample check), tests updated in `voice.test.ts`, `voiceusage.test.ts`, `soundmusic.test.ts`, `test_cast_voice.py`.

## Results

- Engine tests for the sample fix pass (`test_cast_voice.py`, 26); screen tests 548 pass; `tsc` clean. Full-suite numbers are in `docs/QA.md`.
- Seen in the browser harness at 1100 px wide: the voice library, the clone dialog, the film footer and Sound & Music > Scene sound. Before and after screenshots of the dialogs are the owner's own markups (before) and the harness views described above (after); the screenshot sweep (`node scripts/docshots-edge.mjs`) regenerates the guide's pictures.

## Manual Windows checklist

1. Voiceover → **Give a voice… → From your library**: press **Hear** on five voices. Each plays (none shows "Could not play it"). The rows show a quiet **Use this voice**; pressing it asks nothing extra (choosing from the library is free) and assigns the voice.
2. **Design one**: type a description (the button explains the 20-character minimum), press **Hear a few options…** (asks first, uses a little plan). Options appear with **Keep this one**; keeping asks first.
3. **Clone my own**: the button says what is missing until you have a recording, a name and the consent box; nothing is sent until the confirmation question is answered.
4. The model control shows a short name; its description is under the tabs; nothing is clipped at 100%, 125% and 150% Windows scaling or in a narrow window.
5. Any film stage: the bottom-right **Cast & World ›** is compact and amber-outlined; the main action of the screen (for example **Lock this version**) is the only filled amber button.
6. Tab through a dialog with the keyboard: every control shows the amber focus ring; Esc closes.

## Remaining limitations

- The pass covers the voice dialogs, the navigation footer, Settings' key rows and the shared control rules. The other large screens (Studio timeline, Board, Compose, Export) were **not** individually re-audited at 125% and 150% scaling; they inherit the shared rules. A full per-screen scaling sweep is still to do.
- Where several amber filled buttons legitimately appear on one screen (for example a step with two stages), they were left: each is the main action of its own card.
- The screenshots of the new look were viewed in the browser harness only, not in the installed application.
