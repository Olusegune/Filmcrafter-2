# Paid operations: the shared policy

Anything that uses the person's money or plan (a provider account, a voice slot, credits) follows one rule set. It is implemented in `analysis/filmcrafter_engine/paidops.py` and used today by the ElevenLabs voice tools (`cast_voice.py`). The picture/video render engine already has an equivalent (job states including `uncertain`, a credits pause, a budget guard); new paid features use this module.

## The rules

1. **Authorise.** The engine refuses a paid call unless the request says `confirmed` (`require_authorised`). This is checked in the engine, not only in the screen, so no other caller (a script, a stale screen, a future feature) can spend by accident. Nothing is sent when it refuses.
   - Cloning needs `consent` (the voice is the person's own, or its owner agreed) **and** `confirmed`. They are separate: consent is about the person, confirmation is about spending.
   - A call whose cost is not published (voice design) also needs `unknown_cost_accepted`. The app never shows an invented number; it says the cost is unknown and asks the person to accept that.
2. **Limit.** An optional per-film limit per unit (`elevenlabs_credits`). The engine refuses a call that would pass it. Operations of unknown outcome count against it, because they may have been charged.
3. **Record first.** The operation is written to `<film>/voice/ledger.json` (status `prepared` → `confirmed` → `submitted`) before anything is sent.
4. **Send once.** One request. A retry happens only with evidence the provider never accepted the first one: HTTP 429 (bounded, with the provider's wait) or a connection that was never made. A timeout, a dropped connection after sending, or a 5xx is `uncertain`, **never** retried automatically. Creating things (design, keep, clone) is never retried.
5. **Settle.** `completed` (with what the provider reported, kept apart from the estimate), `refused`, `failed_before_submission`, or `uncertain`.
6. **Recover.** An operation left `prepared`/`submitted` by a crash is settled the next time the ledger is read: `prepared` that never reached the network becomes `failed_before_submission`; `submitted` becomes `uncertain`. An identical request is blocked while an earlier one is `uncertain`. Only the person can resolve it (`charged` / `not_charged`) after looking at the provider's usage page; `charged` then counts as used.

## What is recorded

`id`, time, `action` (design, design_save, clone, speak, preview…), `person`, `shot`, `status`, `estimate {unit, amount, basis}` (our own count, always labelled an estimate), `actual {unit, amount, reported, source}` (only what the provider reported), `note`, optional `resolved`. Never a key, a token, an `Authorization` header, or a request body. Newest 2,000 entries are kept.

Estimates and actuals are never added together. A summary gives, per unit: operations, reported total, number of operations with nothing reported, and the estimate for only those.

## Units

Units are provider-specific and never converted: `elevenlabs_credits`, `voice_slot` (each keep or clone takes one). Dollars are not shown for ElevenLabs because it bills the person's own plan.

## Concurrency and damage

The ledger is read and written through `safeio` (atomic, locked read-modify-write, a damaged file is preserved and never replaced by an empty one). Several processes can add entries at the same moment without losing any (a six-process test covers it). Restoring an older film backup never rolls the ledger back: it is the record of what was spent.

## Adding a new paid operation (including future sound effects and music)

The ledger is **not specific to dialogue**: an entry is `action` + `unit` + `estimate` + `actual`, and the screens only read those. To add sound effects or music generation:

1. Pick the action names (`sfx`, `music`, `music_stems`…) and, if the provider bills in a new unit, a new unit key (for example `elevenlabs_credits` for ElevenLabs sound generation, `kie_credits` for Kie music). Add the unit to the module's allowed limit units (today `cast_voice.LIMIT_UNITS`) so a limit can be set for it.
2. Call `_paid(...)`-style flow: `require_authorised` → `ledger.begin` → one send → `complete`/`mark`. Do not write a second mechanism.
3. State the cost honestly: a published rate may be shown as an estimate; an unpublished one needs `unknown_cost_accepted`.
4. Asset naming: ledger entries refer to a `shot` or a `person` today; a sound/music entry would carry the asset's role in `action` and its target in `shot` (or a new optional `asset`; `begin` already accepts an `asset` field) so a sound that belongs to a scene or the whole film is not forced into a shot.
5. Store generated audio in its own folder (not `voice/`): the film's `voice/` folder means *spoken lines*. `filmbackup` snapshots every small record it finds without a list to update, and it leaves audio alone.

## Where each guarantee is tested

`analysis/tests/test_voice_paid_safety.py` (33 tests: refusals send nothing, consent vs spending, uncertain outcomes, no retry of creation, crash settlement, limits, concurrency, damaged files), `test_safeio.py`, `test_render_lock.py`, `src/__tests__/voiceusage.test.ts` (the words the person sees, and that the screens ask before they send the flags).
