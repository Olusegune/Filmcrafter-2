# Performance Director: Phase 0 (audit, architecture and plan)

Status: **proposal for the owner's approval. No code for the Performance Director has been written.** Written 2026-10-30 against the repository's current `main` (0.31.1) plus the owner's five unpushed commits (looks per shot, Seedream sizes, BytePlus, browser tests, first-run UX).

How to read this: every statement in the audit comes from reading the code in this repository. Nothing here was run against a real provider. `HANDOVER.md` (0.25.4) and `FilmCrafter-REVIEW-HANDOVER-0.23.4w.md` are historical; this document replaces them as the description of what exists.

## 1. The finding that shapes everything

The brief reads as if FilmCrafter has no acting layer. It has a substantial one. Building the "Performance Director" as a new system beside it would duplicate it, leave two sources of truth, and break the rule "avoid creating duplicate systems". The right project is: **make the existing acting, voice, continuity and review pieces into one coherent Performance Director, fill the real gaps, and connect what is currently separate.**

What is genuinely missing is narrower than the brief implies: a structured character psychology, a scene-level performance breakdown, emotional state carried between scenes, non-human acting channels, per-feature model-capability provenance, and a backend-enforced approval for the AI steps.

## 2. Current state: what exists

| Area | What exists (file) | What it does |
|---|---|---|
| Timed acting beats | `acting.py`, `ActingDepth.tsx`, `acting.json` | 1 to 6 timed beats per shot (`t0`, `t1`, `what`, `face`, `eyes`, `hands`, `breath`). Written by the person or by the Director (AI, price shown first). Go into the video prompt as a timed sequence and the first beat into the keyframe prompt. |
| Emotional arc | `acting.py` (`arc_*`) | A character's emotion and strength per section ("Verse 1: stern, 4/10 -> Chorus 1: flustered, 7/10"); each shot's prompt says where its people are in their arc. |
| Signature gestures | `acting.py` (`business_*`) | "When flustered: touches her gele"; one that fits the moment is suggested in the prompt. |
| Performance profile | `performance.py`, `Performance.tsx` | Natural / Restrained / Expressive / Dramatic / Energetic, plus micro-motion (blinks, breathing, weight shifts, hair and fabric). Precedence shot > scene > character > project. |
| Dramatic beats in the contract | `shots.py` (`BEAT_FIELDS`) | Per shot: `character, what, want, need, fear, hiding, subtext, start, turn, end`; plus `emotional_intention` and `micro_animation`. **A second, different "beat" concept**, not linked to `acting.json`. |
| Character data | `bible.py` | `name, role, age, physical, relationships, arc, voice, notes`, wardrobe, **states** (a state can carry an age), media. Plan characters also carry `motivation` and `acting_notes`. No character *kind* (human, robot, creature). |
| Animation principles | `animation_principles.py` | The twelve principles, chosen per shot by relevance and by look family (photoreal, 3D, 2D, craft...). Pure text, free. |
| Voice | `voicedirect.py`, `cast_voice.py`, `voiceover.py`, `LineStudio.tsx` | A spoken version of a line kept apart from the screenplay; natural-delivery suggestions (AI, price first); voice casting; table read; ElevenLabs voices (library, design, clone) with takes; imported recordings. A tag-capable-model table (`TAGGED`: Eleven v3 and v4 read `[whispers]`, `[laughs]`). Feelings and reactions pickers. |
| Voice and picture | `render.py` (`audio_first`, `lip_sync_mode`, `native_for`, `wants_lipsync_pass`), `lipsync_check.py`, `LipSyncNote.tsx` | Reference-audio conditioning, native audio, a separate lip-sync pass and a free timing check are separate, named paths. |
| Continuity | `continuity.py`, `filmcheck.py`, `FilmContinuity.tsx` | Blocking, 180-degree line, eyelines, wardrobe, light; advisory drift findings ("may have changed"). Nothing about emotional state. |
| Camera and light | `camera.py`, `lighting.py`, `shots.py` rules | Named choices with a reason; a lighting designer that reads each shot's mood. See risk 5. |
| Review | `review.py`, `lipsync_check.py`, `exportcheck.py` | Technical and visual take review. **It already judges acting**: it is told the emotion, strength, expression, timed beats and arc, sees time-labelled frames, and may report a `performance` issue. |
| Models and routing | `router.py`, `routing.py`, `modelinfo.py`, `render.capabilities()` | Families per provider, `VERIFIED` (a real render proved it), capabilities derived from each model's published schema (reference counts, first/last frame, audio refs, native audio). |
| Spend | Rust `SPEND` tokens, `paidops.py`, `budget.py`, `routing.guard`, `cast_voice` ledger | Every render needs a backend-redeemed, single-use confirmation token; voice operations need `confirmed: true`, an optional limit and a ledger written before the call. |
| Draft-first | quality tiers (Draft...Max), `pickTestShot`, Select & review, `upscale.py` | A cheap test shot, choose-then-pay-for-video, upscaling. |
| Golden path | `GoldenStrip`, `readiness.py`, `NextStep.tsx`, the Acting rail tool | One next step at a time; the Acting sheet holds profiles, beats and arcs. |

## 3. Brief against reality

| Brief requirement | Verdict | Reality and gap |
|---|---|---|
| A. Character Performance Bible | **Partial** | `physical`, `relationships`, `arc`, `voice`, `notes`, `motivation`, `acting_notes`, business exist. Missing: objective, fears, triggers, contradictions, defences, restraint, stress behaviour, current emotional state, **outward versus inner emotion**. |
| B. Script-to-performance analysis | **Partial** | Story analysis, a shot breakdown with `emotional_intention`, and the dramatic beat fields exist. Missing: a **scene-level** breakdown (purpose, start and end state, objectives, obstacles, tension, subtext, turning points, reaction beats) and shot fields for gaze, posture, head, reaction timing, silence. |
| C. Performance beat engine | **Partial** | Timed beats and an editor exist. Missing: gaze target, emotional change, dialogue link, confidence, auto-or-user marker, **beats that continue across shots**; and the two beat concepts are unlinked. |
| D. Actor Performance Director | **Partial** | Profile, micro-motion, principles, business exist. Missing: choosing only the *relevant* acting categories per shot (effort, interaction, listening) and **per-model wording**. |
| E. Specialised animation acting | **Partial** | Look families exist. Missing entirely: robots, creatures, anthropomorphic animals (no character kind, no non-human expressive channels). |
| F. Emotion-aware voice director | **Mostly exists** | Separate spoken version, delivery suggestions, tags, takes, feelings. Missing: linking a line's delivery to the acting beat and the character's state; a provider capability registry beyond the `TAGGED` table; only ElevenLabs. |
| G. Voice-to-performance sync | **Partial** | The capability levels are already distinct paths. Missing: analysing a recording's pauses into beats; labelling each path as documented, tested or unverified per model. |
| H. Emotional continuity | **Missing** | Arcs run across *sections*; nothing carries a state across scenes (entering, exiting, unresolved tension, fatigue, physical condition), and there is no Emotional Arc view. |
| I. Character and world consistency | **Exists** | References, age states, library, locks, previous-shot reference, wardrobe. Gap is only the performance side (age-appropriate movement and voice). |
| J. Cinematic emotion director | **Partial** | Camera and light advice with a reason exists but maps emotion to stereotypes (see risk 5). Missing: reaction shots, silence and pacing recommendations in plain language. |
| K. Model capability and cost-aware routing | **Partial** | Schema-derived capabilities, `VERIFIED`, costs and gates exist. Missing: per-feature provenance (documented, tested, unverified, unsupported) and any performance-aware ranking; draft-first exists but is not performance-aware. |
| L. Performance review | **Partial** | Acting-aware review exists. Missing: confidence per observation, plain corrective options ("looks away too early"), selective regeneration from a finding. |

## 4. Integration risks

1. **Two beat concepts.** Dramatic beats (`shots.py`, want/need/fear/hiding/subtext) and acting beats (`acting.json`, timed face/eyes/hands/breath). They must be linked, not merged blindly: a dramatic beat *explains*, an acting beat *shows*. Pick one owner of timing (`acting.json`) and one of intent (the contract).
2. **Prompt budget.** Prompts are already long and have a budget view. New acting text must enter as prioritised blocks that the budget can drop, chosen by relevance (the brief's "do not force all of it into every prompt").
3. **AI approval is not enforced by the backend.** `acting.beats_write` and `arc_write` call the AI brain with no `confirmed` check in the engine; the screen asks first and the Rust command passes the call through. Voice already does this correctly (`cast_voice`, `paidops`). The brief requires backend approval for every paid operation: new AI steps must follow the voice pattern, and the existing acting ones should be brought in line.
4. **Data safety.** `acting.json` is read defensively but unversioned. New data needs `schema` versions, migrations that never drop unknown keys, and no write into the screenplay or the story files.
5. **Stereotyped light and camera.** `lighting.py` maps melancholy to "cool blue-grey" and joy to "golden"; `shots.py` maps sad to a wide shot, anger to a low close-up. These are exactly the equivalences the brief warns against. They are advisory today, so the fix is to add alternatives, the scene's own motivated light, a plain "why" and a restrained option, not to rip them out.
6. **Little real-provider evidence.** Most paths have only been tested with mocks; `docs/QA.md` lists the few real runs (Kie.ai, October 2026). Capability labels must start as *documented* or *unverified*; none may be shown as *tested* until a real run is recorded.
7. **UI surface.** The Studio has no browser preview here (its mock data is missing), so new screens will be checked on the screenshot harness, as the look and BytePlus work were.
8. **Scale of change.** `Studio.tsx`, `CastWorld.tsx` and `render.py` are very large. New code goes in new modules and new components, with small hook points.

## 5. Proposed architecture

Principle: **one Performance layer over the existing stores, one new folder, no second copy of anything.**

```
<film>/performance/                       new, optional; a film without it opens exactly as before
  characters.json    {"schema": 1, "people": {key: {psychology...}}}      what a character wants, fears, hides
  scenes.json        {"schema": 1, "scenes": {n: {breakdown...}}}         the editable Performance Breakdown
  emotion.json       {"schema": 1, "people": {key: {scene: {enter, exit, ...}}}}   derived + overrides
<project>/acting.json                     existing; schema 1 -> 2: beats gain gaze, change, link, source, confidence
```

Modules (reusing before adding; filenames are suggestions):

| Module | Role | Reuses |
|---|---|---|
| `character_performance.py` | psychology profile, outward and inner emotion, character *kind* (human, stylised human, 2D, clay, animal, robot, creature) | `bible.py` (read-only link), `performance.py` |
| `performance_analysis.py` | the scene Performance Breakdown: a free rule-based draft from the story analysis, dialogue and shot intent; an optional AI refinement | `story.py` analysis, `shots.py` contract, `llm.py` |
| `acting.py` (extended, not replaced) | beats v2, multi-shot continuation, link to dramatic beats | itself |
| `emotional_continuity.py` | per person and scene: state entering and leaving, unresolved tension, fatigue; mismatch flags | `acting.arc`, `filmcheck.py` for the advisory pattern |
| `performance_prompts.py` | choose the relevant acting categories for one shot and phrase them for the look family, the character kind and the model; emits prioritised prompt blocks | `animation_principles.py`, `performance.py`, the prompt-block budget in `render.compile_request` |
| `model_capabilities.py` | a registry: feature -> {documented, tested, unverified, unsupported} plus source and date; seeded from `capabilities()` (documented) and `VERIFIED` (tested) | `render.py`, `router.py`, `modelinfo.py` |
| `performance_review.py` | extend `review.py`'s acting judgement: confidence, plain corrective options, "regenerate only this" suggestions | `review.py`, `lipsync_check.py` |
| voice link | a small addition to `voicedirect.py`: a line's delivery pre-filled from its beat and the person's state; provider capability table generalised from `TAGGED` | `voicedirect.py`, `cast_voice.py` |

Keep free what can be free: the breakdown draft, the beat selector, the continuity tracker and the prompt chooser are **deterministic and local**. AI is an optional refinement, never a prerequisite.

Approval and spending (every new AI or paid step): estimate first (`*_estimate`), then the same call with `confirmed: true`; the **engine** refuses without it, records the intent in a ledger before the call (the `paidops` pattern), honours a per-film limit, and the existing render tokens stay untouched. Existing `beats_write` and `arc_write` get the same check in the same change that touches them.

The screenplay is never written to. Anything inferred is stored apart, marked `source: "auto"`, and every inferred field can be overridden (`source: "user"`), after which an automatic refresh never touches it.

## 6. UI plan (golden path, progressive disclosure)

- The **Acting** rail tool becomes the **Performance** workspace, found where it is now (behind *More*, and in Director Mode); a shot's Shot tab gets a compact "Performance" panel for the common case.
- First view is one question per scene: *what does each person want here, and what are they hiding?* with the draft filled in and one button to accept or edit. Beats, categories, models and take comparison sit behind a disclosure.
- The simple controls from the brief (More restrained, More hesitant, Hold the reaction longer, Let the eyes tell the story...) each change **named fields** (strength, beat duration, gaze, movement amount), never append adjectives; each has a test that the structured data changed.
- An **Emotional Arc** view: one track per person across scenes, flags on likely mismatches, each flag dismissible.
- Everything keyboard reachable; new screens added to the harness and the accessibility scan the day they exist.

## 7. Milestones

Each milestone is releasable by itself, adds tests for what it does, and reports honestly which results used a mock.

| # | Milestone | Delivers | Brief tests |
|---|---|---|---|
| **M1** | Psychology and breakdown (free, local) | `character_performance.py` and the profile form; `performance_analysis.py` rule-based draft; outward versus inner emotion; storage, versions and migrations; editable | B (hidden emotion, "I'm fine"), part of F |
| **M2** | Beats v2 and the workspace | `acting.json` v2, link to dramatic beats, multi-shot continuation, the Performance workspace and the simple controls, accessibility scan | C |
| **M3** | Relevance and non-human acting | `performance_prompts.py`; character kinds (robot, creature, animal, stylised) with their expressive channels; effort and interaction categories; per-look wording; prompt budget integration | A, C, H |
| **M4** | Voice and model honesty | beat-to-line delivery link; provider capability registry with provenance; `model_capabilities.py`; the sync paths labelled by what is documented or tested | G |
| **M5** | Emotional continuity and review | `emotional_continuity.py`, the Emotional Arc view, review confidence and corrective options, selective regeneration | D, E |
| **M6** | Draft-first and approval hardening | performance-aware draft flow, backend approval and budget for the AI steps (old and new), a recorded real run **only with the owner's approval of the spend** | all, F |
| Cross-cutting | Light and camera advice | alternatives and a restrained option beside the stereotyped mappings; plain explanations | part of J |

Rough size: M1 and M2 are the largest user-visible steps; M3 and M5 carry the most new logic; M6 is mostly hardening.

## 8. What will not be claimed

No label of "verified" for any model feature without a recorded real run; no wording like "Hollywood quality" or "perfect acting"; the review will say what it saw and how sure it is, never that a performance is good; nothing is rendered, charged, pushed or released without the owner's say-so.

## 9. Decisions the owner should make before M1

1. **Scope of the first build.** Recommended: M1 and M2 together (a free, local Performance Breakdown and the workspace), because they are useful before any paid generation.
2. **Where psychology lives.** Recommended: its own `performance/characters.json` linked to the Bible by id (the Bible stays the identity record; psychology is a layer that can be absent).
3. **Naming.** Rename the Acting tool to **Performance** in the interface, or keep *Acting* and add *Performance Director* as the workspace's title.
4. **Default for analysis.** Recommended: rule-based and free first; AI refinement as an explicit, priced, confirmed button.
5. **The existing AI steps.** Approve bringing `beats_write` and `arc_write` under backend approval in M2 (a small behaviour change: the engine will refuse without `confirmed`).
6. **Real-provider validation.** Which provider and a spending cap, if any, for the M6 recorded run.
