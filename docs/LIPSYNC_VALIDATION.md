# Lip-sync validation: plan, readiness check and results

**Status: one real run was made on 2026-10-14** (owner-authorised caps: Kie 300 credits, ElevenLabs 50; spent Kie 200 credits and ElevenLabs 3; see Results). It is **one take of one shot**, judged by a crude measure of mouth movement and by looking at frames, **not by a person watching and listening**; the owner has the files to judge. Until a person has judged, the app's wording stays: *the request is built the right way; whether the video model honours the audio is not proven.*

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

**Run of 2026-10-14**: a throwaway film, one speaking close-up (a woman, picture made by Nano Banana), a 15-character line spoken by an ElevenLabs premade voice (1.36 s of speech, sent as a 4 s clip: the rest silence). Files for judging: `Desktop\FilmCrafter lip-sync test`.

| Step | What happened | Spent |
|---|---|---|
| Free readiness check | The request was built right: the recording as `reference_audio_urls`, the keyframe as a reference picture, `generate_audio` off, 4 s, 0 problems. | 0 |
| Seedance 2 with only the recording (no picture) | **Refused by Kie.ai, nothing charged**: "Audio cannot be empty in the scene of i2v-reference". Seedance's reference mode needs a reference picture with the audio. (The take record still kept the voice it was sent.) | 0 |
| Keyframe (Nano Banana) | Made and approved. | 4 Kie credits |
| **Take A**: Seedance 2, picture + recording | Made (4.04 s). The take's own sound is off by design. **Mouth-region motion was low while the voice spoke (0 to 1.25 s: 0.5) and high in the silent part (1.75 to 3 s: up to 4.9); correlation with the speech energy -0.35.** In the frames the mouth is open in silence. **The mouth did not follow the voice's timing.** | 164 Kie credits |
| **Take B**: Volcengine lip-sync pass on Take A, same recording | Made (4.04 s, the recording as its sound). Mouth-region motion in the speech window rose to 1.9 (from 0.5) and correlation became +0.35, but there is still movement in the silent part (about 2 to 3.2 s). **Better, not proven good.** | 32 Kie credits |

**Reading it honestly:** the reference-audio route alone (Take A) did not give lip-sync in this one test; the dedicated pass (Take B) moved the mouth toward the words. The measure is a crude proxy (motion in a box around the mouth), the sample is one shot with a mostly-silent clip, and a person has not yet watched it. What this supports: keep saying the reference audio is not a promise, keep the "Lip-sync this take…" pass as the dependable route, and judge a real shot with the real voice length (a clip that is mostly padding silence is a poor test: next time use a line that fills the shot). Things the test also showed: a model can refuse a request for reasons not in its documentation (nothing was charged); the pass costs about a fifth of a take.


**Retest of 2026-10-21 (owner-approved caps: Kie 40 credits, ElevenLabs 55 credits; same throwaway film).** The first test's line filled only a third of the clip, so this one used a longer line (55 characters, 3.92 s of speech in the 4 s clip) and ran the Kie lip-sync pass (Volcengine) again on the same Take A, with the new recording. That is also the "after a voice changes" check: the pass was the remedy for a take whose voice had changed.

| Step | What happened | Spent |
|---|---|---|
| New line | Spoken by the same voice; attached to the shot. The engine's safe estimate was 55 credits; **ElevenLabs reported 12**. | 12 ElevenLabs credits |
| Lip-sync pass | Made (4.04 s, 720p, the new recording as its sound). The review noted the take is 4.0 s but the shot needs 4.5 s (length, not sync). | 32 Kie credits |

Crude measure (motion in a box around the mouth, per 0.2 s, against the speech energy of the line): while the line was spoken the mouth region moved at 1.64 and in the pauses at 0.64; the correlation with the speech energy is **+0.16**. The base take (which never heard this line) moved at 1.33 and 0.26 (correlation -0.01). The contact sheet shows the mouth slightly open and changing in most quarter-second frames. **Reading it honestly:** the pass moves the mouth during speech, but this proxy cannot say whether it matches the words, and a weak correlation is not proof either way. It needs a person to watch and listen. Files: `Desktop\FilmCrafter lip-sync test 2`.

Two things this run showed about the app: (1) a spending limit is checked against the safe estimate of each paid step, not the amount ElevenLabs later reports, so a longer line needs a limit near the estimate even though the real charge is about a fifth of it; (2) the engine refused the line before sending anything when the limit was too small, which is the intended behaviour.

| Date | Shot | Route | Spent | Mouth followed the voice? | Notes |
|---|---|---|---|---|---|
| 2026-10-14 | S01-02 (close-up, 1.4 s line in a 4 s clip) | Seedance 2 reference audio | 164 Kie credits (+4 for the picture, 3 ElevenLabs) | **No** (measured and seen in frames) | The mouth moved mostly in the silent part. |
| 2026-10-14 | same take | + Kie lip-sync pass (Volcengine) | 32 Kie credits | **Better, not proven** (measured; not yet judged by a person) | Residual movement in the silent part. |
