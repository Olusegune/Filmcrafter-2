# PULSEFRAME

**Direct music into motion.** PULSEFRAME turns a song into a directed music video. It listens to the music, plans every shot on the beat, renders the shots with the AI models you choose (or for free on your own ComfyUI), checks them, and exports the finished video with your song as the soundtrack.

You stay the director. Nothing is charged to your accounts without a confirmation that shows the price first.

## Install

Windows 10/11 (64-bit): run `PULSEFRAME_<version>_x64-setup.exe`. On first launch PULSEFRAME sets up its engine once (about 2 GB, or 3 GB with an NVIDIA card).

## Documentation

The user guide is built into the app: **Documentation** on the Home screen, in Settings, or press `F1`. The same guide is at [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md). Importing packages from PULSEFRAME Producer is described in [docs/PRODUCER_IMPORT.md](docs/PRODUCER_IMPORT.md), and the instructions for making one are in [docs/PRODUCER_PLUGIN_INSTRUCTIONS.md](docs/PRODUCER_PLUGIN_INSTRUCTIONS.md).

## What it does

- **Understands the song**: tempo, beats, sections, energy, vocals and lyric timing.
- **Directs**: creative directions, a treatment, and a shot list timed to the music; or follows your own script.
- **Create from song**: the Producer plans the whole production inside the app: cast with locked looks and one outfit each, props, places, movement and a shot list laid on your song's lyric lines. You approve and reshape each step ("make the mother more theatrical"), and it imports exactly like a package from the Producer plugin.
- **Camera and lighting by name**: shot size, angle, movement, lens, lighting and focus (including rack focus) for every shot, chosen by the Director or by you.
- **Renders** on fal.ai, Kie.ai, Google, or free on ComfyUI, in five modes: Cheapest, Hybrid, Local First, Balanced, Premium.
- **Select & review**: pick shots, choose between keyframe options, and pay for video only where the still is right.
- **Keeps your characters consistent** with a Reference library, a Production Bible and per-shot locked designs.
- **Makes musicals**: a **Show** holds acts of songs and spoken scenes with one shared cast, look and Production Bible. Dialogue is voiced per character (MiniMax or any ElevenLabs voice), recorded by your own actors, or spoken by the video model itself (native dialogue), and timed so the director cuts on the lines. Import a whole script into acts, numbers and scenes, give characters a costume per act, add intermission cards and ambience, set a show budget, render the whole show overnight on ComfyUI, and export it as one film with subtitles and chapters.
- **Makes songs** (optional): compose one with ElevenLabs Music from your tagged lyrics or a description, or bring your own.
- **Imports production packages** from PULSEFRAME Producer, generates pictures for assets the package only described, and shows what the Director merged, with a one-click split back.
- **Supervises**: review findings, lip-sync checks and render problems in one place.
- **Exports** for YouTube, cinema, vertical and square, with editable **lyric captions** and **on-screen text** (titles, signs, charts) in the fonts you choose, plus a matching subtitles file.
- **Sends to Premiere Pro or DaVinci Resolve**: one import file with the finished film and every shot as timelines.
- **Protects your work**: approved takes are never overwritten, and automatic backups can restore any earlier state.

## Security and privacy

API keys are stored only in the operating system's credential store (Windows Credential Manager, macOS Keychain), never in projects or logs. Projects stay on your computer; media is sent only to the renderer you choose, when you confirm a render.

## Development

Requirements: Node 20+, Rust (stable), Python 3.11.

```bash
npm install
npm run tauri dev
```

Tests:

```bash
npx vitest run
```

```bash
cd analysis && python -m pytest -q
```

Release build (installer in `src-tauri/target/release/bundle/`; signing setup in [docs/CODE_SIGNING.md](docs/CODE_SIGNING.md)):

```bash
npm run tauri build
```

Layout: `src/` (React UI), `src-tauri/` (Tauri shell and commands), `analysis/pulseframe_analysis/` (the Python engine: analysis, direction, rendering, export), `docs/` (guide and release notes).

See [CHANGELOG.md](CHANGELOG.md) for what changed in each release.

## License

Proprietary. Copyright (c) 2026 PULSEFRAME. All rights reserved. See [LICENSE.txt](LICENSE.txt). Not for redistribution.
