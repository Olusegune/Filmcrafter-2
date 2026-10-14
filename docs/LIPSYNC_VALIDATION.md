# Lip-sync validation: plan, readiness check and results

**Status: the real test has NOT been run.** It spends money, so it needs the owner's separate, explicit authorization and a spending cap (the expansion rules: "Any paid tests require separate authorization and a spending cap"). Nothing below claims that a mouth follows a voice. Until a run is recorded in the table at the end, the app's wording stays: *the request is built the right way; whether the video model honours the audio is unknown.*

## What the app does now (checked by tests, no spending)

- A shot's recordings are sent to the video model as one reference audio clip (`voiceover.slice_for`), the keyframe going along as a reference picture (Seedance 2 forbids a first frame together with reference media).
- **New in Stage F:** every video take and lip-sync pass records the exact voice it followed (`voice_ref`: each recording's fingerprint, length, speaker and source, and one digest). `outdated.report` compares that record with the shot's voice now and says when a recording was replaced, removed or added, **without changing, deleting or re-making anything**. Approved or locked takes are reported with a note and kept. A take made before this existed carries no record and is **not judged** (the report counts them as "not checked").
- The separate lip-sync pass (`compile_lipsync`: the finished take plus the exact audio at the take's length) is unchanged: the Studio's *Lip-sync this take…* shows its price first. For the voice that changed, it is the cheaper way to re-time the mouth than a new take.
- The free timing check (`lipsync_check timing`) says whether the sound in a take follows the song's vocal. Its picture check asks a vision model whether a mouth matches, with prompts written for a singer; **it needs adapting for speech before its verdict is trusted** (not done: it would change what a paid vision call asks).

## Free readiness check (run before authorizing anything)

1. Open the film, make sure the chosen shot has a recording attached (own recording or an ElevenLabs line) and no `voice_ref`-less take hides behind it.
2. `python scripts/audit_film.py "<film folder>" --kind video --model bytedance/seedance-2` builds every shot's request without sending it and reports 0 problems, showing the audio carried.
3. In the app the shot's **What would be sent** list shows the recording as the audio the mouth follows.
4. Check the estimated price shown next to Make the video; write it down.

## The paid test (only with authorization and a cap)

One character, one line, one shot, in order, stopping at the first decision:

1. **Shot:** a speaking shot, one person clearly facing the camera, close or medium framing, about 4 s.
2. **Keyframe:** one still. Estimated about 4 to 10 Kie credits (the price of the picture model is shown by the app first).
3. **Voice:** one ElevenLabs line of 15 to 40 characters on Eleven v4 (about 15 to 40 credits of the plan). Or the person's own recording (free).
4. **Take A:** one Seedance 2 render with the voice as reference audio. Estimated about 164 Kie credits (about $0.82), shown by the app before the yes.
5. **Judge:** assemble the finished clip with the recording (the export always uses the recording, never the model's sound) and watch. Acceptance: the mouth opens on the words and closes in pauses; no obvious drift over the clip; the face is still the right character.
6. **Only if Take A drifts:** run the lip-sync pass once on Take A (about $0.53 on fal for 4 s at $8 per minute, or the Kie credits shown after the task), then judge again.
7. **Record the result** below, with the route that worked.

Total if Take A is enough: about 190 Kie credits (about $0.95) plus under 50 ElevenLabs credits. A cap of 800 Kie credits and 3,000 ElevenLabs characters covers every step with room to spare. Stop rules: stop at the first refusal, at the first unclear charge (the ledger will say so), or when the running total reaches the cap.

## After a voice changes (the same test, smaller)

Replace the recording on the tested shot, confirm that Voices/Scene sound shows the take as "may be out of date", press *Lip-sync this take…*, check the price shown, and judge the result the same way. This verifies that the stale-take report points at the right remedy.

## Results

| Date | Shot | Route | Spent | Mouth followed the voice? | Notes |
|---|---|---|---|---|---|
| (not run) | | | | | Awaiting the owner's authorization and cap. |
