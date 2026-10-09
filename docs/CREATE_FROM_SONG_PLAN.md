# Create from song: the Producer, inside PULSEFRAME

Status: Phases 1, 2, 3 and 4 built (3 Oct 2026; Phase 3: one-card revision, `.pfproducer` export, resume to the last step). Phase 1: the plan engine (`producer_plan.py`), the four-step screen (`Produce.tsx`), and the hand-off to the importer. Phase 2: the Pictures step (`ProducePictures.tsx`, `refgen.cards/own`, redo with a note, owner sheets as references, dance sheets, spend limit, draft quality). Phase 4: shot list review with per-section approval, shot editing and per-section movement.

What Phase 1 learned from a real plugin package (the "I Am Your Mother" bundle): a package carries 8 characters, one outfit each, 21 props, 2 place variants, 4 choreography entries and 45 shots; each picture is a 1536x1024 sheet (a character sheet is four views plus six expressions on white; a choreography sheet is eight numbered pose panels with motion arrows); the continuity block also carries `world`, `always`, `palette` and `never_show`, which the importer now reads. Phase 2 (built) makes the choreography sheets and shows approved character sheets to the model for the other pictures.

## The idea

Today the best results come from the PULSEFRAME Producer plugin in ChatGPT: it writes a package (a manifest, character and prop sheets,
environments, choreography sheets, a shot list) that PULSEFRAME imports. That workflow is loved and stays exactly as it is.

**Create from song** does the same job inside the app: give it a song, lyrics and (optionally) a script or character pictures, and it
produces the same kind of package, shows it for approval, makes the pictures, and opens a populated project.

## The one design decision that matters: two front doors, one pipeline

The in-app Producer must **not** be a second way of building a project. It writes a package in the plugin's own format (the manifest
schema in `PRODUCER_PLUGIN_INSTRUCTIONS.md`) and hands it to the existing importer.

```
  ChatGPT plugin ──► package (.pfproducer) ─┐
                                            ├──► producer_import ──► project ──► "Pictures the package only described" ──► Studio
  Create from song ──► package (written     ─┘                       (existing)        (existing refgen, with prices)
                       in the app)
```

Why this is the right shape:

- Both doors produce identical projects, so everything downstream (Supervisor, continuity, locked designs, overlays) already works.
- "Bring your own package" is never at risk: it is the same code path.
- The picture generator already exists and already shows prices before anything is sent. Create from song only adds the **planning** step in
  front of it and a nicer way to approve the result.
- A package made in the app can be exported as a `.pfproducer` too, so the two doors stay interchangeable.

## The flow (kept on the Golden Path: free first, ask before spending, approve before the next stage)

1. **Start** (Home, the obvious first card: *Create from song*, beside *Import production package*). Song, lyrics, optional script, optional character
   pictures. PULSEFRAME says what is missing and what that will cost you in quality. *Free.*
2. **Direction.** Three creative directions and a recommended art style (the app already proposes these), shown as cards with a small preview.
   Pick one, or write your own. Choreography amount is one slider. Beginners accept the suggestion. *Cents (one language-model call).*
3. **The plan.** Concept, cast, places, props, outfits, choreography, story arc, as plain-language cards. Say "make Queen Bee more theatrical" or
   "fewer locations" and only the affected cards change. *Cents per revision.*
4. **The pictures.** Every sheet appears as a named card (character, outfit, prop, place, dance sheet). Approve, revise ("older, warmer"),
   regenerate or swap in your own picture, one card at a time. Price for the whole batch shown first; a cap is enforced. *The main spend.*
5. **Open in the Studio.** The project is populated: library filled, Production Bible written, shots planned and tied to the lyrics. From here
   the existing Golden Path takes over (keyframe, approve, video).

Deliberately **not** in this wizard: video generation and editing. The Studio already does those well, and a second copy would drift. The wizard
ends where the Studio begins.

## Improvements over the first sketch

- Fewer stages. Seven became five, because rendering and export already live in the Studio and the editor export.
- Costs are visible at every step, in the same wording as the rest of the app, and a stage never starts paying on its own.
- Save and resume at every step: close the app, reopen, and the wizard returns to where it was without redoing approved work.
- Approvals are per card, not all-or-nothing, and rejected pictures are kept (as in keyframes) until you say otherwise.
- Style recommendations come from the song itself (tempo, energy, mood, language, lyrics) and from the app's existing look library, with the
  reason given in one line each.

## Phases

| Phase | What ships | Why in this order |
|---|---|---|
| 1 | Plan engine (song + lyrics + script → package manifest and written specs), direction and plan screens, hand-off to the importer | Proves the idea with little spend and no new image code |
| 2 (built) | Picture stage as cards (approve, revise, regenerate, own picture), batch price and cap, choreography and environment sheets | Reuses the picture generator; adds the approval experience |
| 3 (built) | Save and resume, export as `.pfproducer`, per-card natural-language revision | Makes it comfortable for long productions |
| 4 (built) | Shot list review before generation, per-section choreography detail | Polish once the core is trusted |

## Risks to be honest about

- Quality of the plan depends on the language model; it needs the same rules the plugin follows (no invented timings, one subject per
  picture, no text in pictures). These are written down and can be reused verbatim.
- Picture consistency across sheets is the hard part. The plugin's rules for sheets (plain background, same face in every view) apply, and
  each approved sheet becomes a reference for the next ones.
- A full cast is many pictures. The batch price and cap exist for this; a cheap draft quality for sheets should be the default.
- It will not match a hand-tuned plugin run on the first try. The aim is "good starting point, easy to steer", not a replacement.
