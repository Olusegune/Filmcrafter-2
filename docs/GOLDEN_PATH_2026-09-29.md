# Golden-path improvements 1–6, with QA (29 Sep 2026)

| # | Idea | What was built | QA in the installed app |
|---|---|---|---|
| 1 | Free preview first | New Autopilot step "Watch a free preview". Every shot with a keyframe becomes a moving still, a draft of the whole song is cut, and it plays inside Autopilot. Autopilot then stops so you can watch. The video step lets you pick which shots get real video; the rest stay moving stills. | Preview cut in 16 s on QA Flow Song. On Exit Plan copy the step shows as done (every shot already has video). |
| 2 | Re-render only what changed | Each new render records which keyframe it started from; older takes are compared by time. The Supervisor lists videos made from an older keyframe and offers a priced "Re-render these". | Found exactly the 12 Exit Plan shots whose keyframes were replaced. Price shown, then cancelled; nothing was sent. |
| 3 | Grouped fixes | The Supervisor groups findings of the same kind in the same scene, for example "Scene 6 · Framing in 6 shots", with one priced "Fix all". Each shot keeps its own correction, and the batch is checked against the mode and budget as a whole. | Groups listed on Exit Plan copy. Tests cover each shot's own fix note. |
| 4 | Review before export | Export opens with a summary: how many shots are real video, moving stills or storyboard cards; serious findings still open; stale videos. It links to the Supervisor or lets you export as it is. | "76 video · 0 moving stills · 0 storyboard cards · 57 serious findings · 12 videos from an older keyframe". |
| 5 | Split across Kie and fal | When a batch doesn't fit one balance, Autopilot offers "Split across Kie and fal": Kie is filled up to its balance and the rest goes to fal on the same model family. Separately, the budget guard now also counts renders already queued or in flight. | For the 12 stale shots, Kie covers all of them (768 credits ≈ $3.84), so no split is needed. Tests cover the split and the queued-cost guard. |
| 6 | Lip-sync check | For singing shots, frames at sung words and at a pause are checked by the AI brain's vision model; out-of-sync shots become major Supervisor findings with a lip-sync pass as the fix. | 5 singing shots checked (gpt-5.5, a few cents): 3 in sync; S03-08 and S04-06 out of sync, each with a reason. |

## Also in this build

- **Top bar:** the plan chip is now a compact one-line pill (online dot, mode, spend) instead of a large grey button.
- **`.pulse` files:** they get the PULSEFRAME document icon; the installer now registers it.
- **fal price lookups:** a failed lookup keeps the last known price, and failures are retried within the hour. Before, one failure could make a price "unknown" for a day.

## Tests

- 160 engine tests pass, 10 of them new.
- 5 app tests pass; the TypeScript build is clean.

## Follow-up the same afternoon

### Re-render of the 12 stale Exit Plan videos (Kie, Wan 3.0)

- **First attempt:** 1 of 12 succeeded; 11 failed with "input file could not be downloaded", at no charge (Kie balance fell by exactly the 96 credits of the one success).
  - **Root cause:** Kie deletes temporary uploads after about a day, but PULSEFRAME reused upload links for 2 days. The 404s were confirmed on the three character reference images, 26.7 hours old.
  - **Fix:** Kie links are reused for at most 12 hours. A link older than an hour gets a free check that it still exists, and is uploaded again if not. The error now reads "A reference image had expired at the provider (nothing is charged). Retry: it is uploaded again."
- **Retry:** all 11 succeeded. Total for the 12 videos: 832 credits (about $4.16).
- **Result:** no stale videos are left, and a new full export was made (`Exit Plan copy - Cinema - 2026-09-29 1643.mp4`).
- **To review:** S05-06 drifts to a stairwell door mid-shot.

### Recommendations implemented

- **No unasked AI spending.** The renderer no longer reviews old, never-checked takes on its own; that is what spent OpenAI credit earlier today. New takes are still reviewed as they finish. The backlog is a Supervisor button that shows the count first.
- **Cross-dissolve transition.** Added next to cut, dip to black and flash of white. Every cut stays exactly on its frame. It was tested with a real export whose length stays exact.

### Tests

- 162 engine tests pass.
- 5 app tests pass.
