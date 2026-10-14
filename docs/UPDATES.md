# Updating FilmCrafter itself: evaluation, what is built, what is waiting

**Status (0.25 work): updates are NOT switched on.** There is no public place the app can read releases from (an unauthenticated request for the repository's releases returns 404), the installers are not code-signed, and there is no updater key pair. Until those exist the check is off and says so (`updates.ENABLED = False`, `UPDATES_ENABLED = false`; a test keeps the two in step). Nothing in the app downloads or installs a program.

## Requirements (from the expansion brief) and where each stands

| Requirement | Plan | Built now? |
|---|---|---|
| Verified update source | A fixed address in the app (a public GitHub Releases page or a static `latest.json`), https only, nothing the user or a film can change | The address is fixed in `updates.py`; its repository is corrected; it is off until public |
| Signed updates | Tauri's updater verifies a minisign signature of every update bundle against a public key built into the app *before* installing; Windows code-signing (Authenticode) is separate and covers SmartScreen | Not built: needs the key pair and a certificate (decisions below) |
| Clear version information | The release's version, date and notes shown before anything is downloaded (already parsed and length-limited by `updates.check`) | Yes (when enabled) |
| User approval | Nothing installs without a click on a button that says what will happen | Yes: the only action is "Open the download page"; the future in-app install will keep the question |
| Preservation of film projects | Films live in `Documents\FilmCrafter`, outside the program folder, and an update never touches them. Before the person is sent to a new version, `prepare_update` snapshots every recent film's records and copies the app's settings | **Yes** (`preupdate.py`, `prepare_update` command, called by `goToUpdate`; tested) |
| Safe migrations | Migrations are additive (new optional keys; older films open unchanged: the Phase 0 and Stage A to G tests open films without the new files), and a snapshot is taken first | Rule documented and tested for every new record; no migration framework needed yet |
| Recovery from a failed update | Keep the previous installer; films and snapshots are outside the program folder; a failed install leaves the old program or a clean reinstall | Snapshots yes; installer retention is a release step |
| Do not install unverified updates | With Tauri's updater a bundle whose signature does not match is rejected by the plugin itself | Nothing installs at all today |

## Options considered

1. **Tauri updater plugin (`tauri-plugin-updater`) with a signed manifest** (recommended). Signature verification is built in; works with the NSIS installer already produced; the manifest can be a `latest.json` attached to a GitHub release. Needs: a public releases location, an updater key pair (`tauri signer generate`; the private key kept offline and out of the repository), the public key and endpoint in `tauri.conf.json`, the CI step that signs and uploads `.nsis.zip` + `.sig` + `latest.json`.
2. **Winget or the Microsoft Store.** Verified and signed by the store, but needs a publisher account, a certificate and a review process; later, not instead.
3. **Keep manual installers** (today). Honest and safe, but each user must find and trust the file themselves.

## Decisions needed from the owner (nothing here can be done without them)

1. **Where do releases live publicly?** (a public repository's Releases page, or a website). Without it nothing can be checked.
2. **A Windows code-signing certificate.** See `docs/CODE_SIGNING.md`; the build already has a place for it (`signCommand`).
3. **Generate the updater key pair** and keep the private key offline (the app will only trust updates signed by it).
4. **Approve adding `tauri-plugin-updater`** (a new dependency) once 1 to 3 exist.

## How to switch it on once those exist

1. Set `REPO`/`PAGE` in `updates.py` to the public location, flip `ENABLED = True` and `UPDATES_ENABLED = true`.
2. Add the updater plugin, the public key and the endpoint; sign in CI.
3. In the update flow call `prepare_update(version)` (already done by `goToUpdate`) before the plugin installs.
4. Test on a clean Windows machine: an older version updating to a newer one with a film open on the Desktop and another on a second drive; a tampered bundle (must be refused); a network cut mid-download (must leave the old version working).
