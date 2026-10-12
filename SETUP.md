# Setting up FilmCrafter on a new computer

This gets the code running from a fresh clone. It is written for Windows (the app's main target); macOS differs only where noted.

## 1. Install the tools

| Tool | Version | Why |
|---|---|---|
| Git | any recent | to clone |
| Node.js | 22 | the screens (React + Vite) |
| Rust | stable (via [rustup](https://rustup.rs)) | the app shell (Tauri 2) |
| Visual Studio Build Tools | "Desktop development with C++" | Rust needs the MSVC linker on Windows |
| WebView2 runtime | already part of Windows 11 | the app's window |
| Python | 3.11 | the engine (analysis, rendering, export) |

macOS: Xcode command line tools instead of the Visual Studio Build Tools. Linux is not a target.

## 2. Get the code and the screens' packages

```bash
git clone https://github.com/Olusegune/FilmCrafter.git
cd FilmCrafter
npm ci
```

## 3. Set up the engine (Python)

The app runs the engine from `analysis/.venv` when it is there (development), so make that environment:

```bash
cd analysis
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements-engine.txt
cd ..
```

On macOS use `python3.11 -m venv .venv` and `.venv/bin/python`.

Notes from the top of `requirements-engine.txt`:
- The film workflow needs only those packages. ffmpeg needs no separate install: it comes with the `imageio-ffmpeg` package.
- Optional: splitting a video model's own sound into voices and the rest (Sound layers) uses `demucs`, which needs `torch`. Without an NVIDIA GPU: `pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cpu`, then `pip install demucs`. The app works without it.

Check it: `analysis\.venv\Scripts\python -c "import imageio_ffmpeg, PIL, numpy, soundfile; print('ok')"`.

## 4. Run the app

```bash
npm run tauri dev
```

The first run compiles the Rust shell (a few minutes); after that it starts in about 20 seconds. If another copy of the app is already open, close it first (only one runs at a time).

To keep the build files off a synced or slow folder, set `CARGO_TARGET_DIR` first, for example `$env:CARGO_TARGET_DIR="C:\pf-target"` in PowerShell.

## 5. Bring your own things (they are not in the repository)

- **Your films.** A film is a folder (it has `film.json`), usually in `Documents\FilmCrafter\`. Copy the whole folder across, including `render`, `voice` and `cast`; or open the film's Studio and use **Save as One File (.pulse)…** in the File menu to pack its render project into a single file. Open the folder from Home (or double-click the `.filmcrafter` file inside it).
- **API keys.** They live in the computer's own keychain, so enter them again under **Settings** (fal.ai, Kie.ai, OpenAI, Google, ElevenLabs, whichever you use). They are never stored in a project or in this repository.
- **Your settings and saved items** in `C:\Users\<you>\.filmcrafter`: the directions library (`directions.json`), the language-model settings (`llm.json`), the ComfyUI setup (`comfyui`), and, once you have made them, your saved layer styles (`layer_styles.json`) and templates (`layer_templates.json`). Copy that folder if you want them; the model catalogue cache in it (`manifests`) rebuilds itself.

## 6. Check that everything works

```bash
set PF_PYTHON=analysis\.venv\Scripts\python.exe
python scripts/test_all.py
```

This runs the type checks, the screen tests, the app shell's tests, the engine tests by type and the security scans, and prints one table. See [docs/TESTING.md](docs/TESTING.md). A step whose tool is not installed shows as SKIPPED with the reason (for example `rafter`, `bandit`, `pip-audit`).

To try the export on one of your own projects without touching it: `python scripts/rehearse.py "C:\path\to\My Project"`.

## 7. Building installers

```bash
npm run tauri build
```

The Windows installers (`.msi` and `-setup.exe`) appear under `src-tauri/target/release/bundle/`. They are unsigned unless a code-signing certificate is set up ([docs/CODE_SIGNING.md](docs/CODE_SIGNING.md)), so Windows SmartScreen will warn when they are installed. The GitHub workflow in `.github/workflows/build.yml` is manual-only: start it from the repository's Actions tab with **Run workflow**.

## Where things are

| Folder | What it holds |
|---|---|
| `src/` | the screens (React + TypeScript) and their tests (`src/__tests__`) |
| `src-tauri/` | the app shell (Rust): windows, the keychain, running the engine |
| `analysis/filmcrafter_engine/` | the engine (Python): story, shots, cast, prompts and rendering, voiceover, export and the editor hand-off |
| `analysis/tests/` | the engine's tests |
| `docs/` | the user guide (`GETTING_STARTED.md`), testing, acceptance, code signing, plans |
| `scripts/` | `test_all.py` (every check) and `rehearse.py` (a dress rehearsal on a real project) |

## Releases and the changelog

Every change goes in `CHANGELOG.md` under `## Unreleased`. A release renames that heading to the version and date, bumps the version in `package.json`, `package-lock.json` (two places), `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml` and `src-tauri/Cargo.lock`, runs `python scripts/test_all.py`, then tags `vX.Y.Z` and builds the installers.
