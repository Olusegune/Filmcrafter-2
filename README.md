# FilmCrafter

Story-first AI filmmaking for Windows and macOS. Craft stories into cinema.

FilmCrafter is a sibling of PULSEFRAME (music-first AI directing). It started from PULSEFRAME 1.36.0 and is developed independently; see `docs/architecture/` for the baseline, the plan, the port ledger and the architecture decisions.

Status: Phase 0 (architecture and safe reuse). The app still contains PULSEFRAME's music-video screens until they are replaced by the story-first workflow.

## Develop

```
npm ci
npm run tauri dev        # desktop app
npm run dev              # UI only, http://localhost:1420
python scripts/test_all.py
```
