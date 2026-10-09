# Baseline

FilmCrafter was seeded from PULSEFRAME **1.36.0**.

| | |
|---|---|
| PULSEFRAME repository | `Olusegune/Pulseframe-Music-Video-Maker` |
| Baseline tag | `pulseframe-v1.36.0-filmcrafter-baseline` (annotated) |
| Baseline commit SHA | `bad3645b6f13b17ceb8d24e4ce696a05af4757ae` |
| Baseline branch | `baseline/pulseframe-1.36.0` |
| Previous `main` (1.26.0) kept as | tag `backup-main-1.26.0-2026-10-08` at `f5164a281d8ba9748f7fbb919238e1457ed32ccc` |
| Reference installers | `PULSEFRAME_1.36.0_x64-setup.exe`, `PULSEFRAME_1.36.0_x64_en-US.msi` |
| Verified at baseline | `package.json`, `tauri.conf.json`, `Cargo.toml`, `Cargo.lock`, `CHANGELOG.md` all 1.36.0; `tsc` clean; 404 vitest tests pass; `cargo check` clean; `rafter secrets` clean on the committed tree |
| FilmCrafter seed commit | `29161fd4ac3221c37986bfe51fe7f8b8d37073d6` (unmodified copy, no shared git history) |

PULSEFRAME 1.27.0 to 1.35.0 were never committed separately, so the baseline commit contains them together; see `CHANGELOG.md`.

Rules: FilmCrafter never pushes to the PULSEFRAME repository; PULSEFRAME fixes are ported by hand and logged in `PORT_LEDGER.md`.
