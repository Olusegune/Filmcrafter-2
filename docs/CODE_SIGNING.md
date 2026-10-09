# Code signing

Signed installers show **PULSEFRAME** as the publisher instead of "Unknown publisher", and avoid most "Windows protected your PC" (SmartScreen) warnings. Signing is already wired into the build (`src-tauri/scripts/sign.ps1`, called by Tauri for the app, the installer, its plugins and the uninstaller). It only needs a certificate.

Verified on 2026-10-01 with a temporary test certificate: the installer, the installed `pulseframe.exe` and `uninstall.exe` were all signed and timestamped. The test certificate was then removed.

## 1. Get a certificate (pick one)

| Option | Cost (approx.) | SmartScreen | Notes |
|---|---|---|---|
| **Azure Trusted Signing** | ~$10 / month | Good; reputation builds quickly | Recommended. No USB token. Needs an Azure account and identity validation (individuals: available in US/Canada; organisations: more countries). |
| **OV code-signing certificate** (Sectigo, DigiCert, SSL.com…) | $200–400 / year | Warnings fade as downloads build reputation | Since 2023 issued on a hardware token or cloud HSM. |
| **EV code-signing certificate** | $300–600 / year | Same treatment as OV today | Stricter identity checks; also on a token. |

Your identity (or company) is verified by the issuer, so allow a few days.

## 2. Configure this PC (no secrets go into the repository)

Set environment variables (Windows: **Settings → System → About → Advanced system settings → Environment Variables**, user variables).

**Certificate in the Windows store** (a token or cloud HSM that shows up in the store, or an imported `.pfx`):

| Variable | Value |
|---|---|
| `PULSEFRAME_SIGN_THUMBPRINT` | the certificate's SHA-1 thumbprint (certmgr.msc → Personal → Certificates → the certificate → Details → Thumbprint) |

**Azure Trusted Signing**:

1. Install the Trusted Signing client tools (they provide `Azure.CodeSigning.Dlib.dll`) and the Azure CLI, then run `az login`.
2. Create `metadata.json` somewhere outside the repository:
   ```json
   { "Endpoint": "https://<region>.codesigning.azure.net", "CodeSigningAccountName": "<account>", "CertificateProfileName": "<profile>" }
   ```
3. Set:

| Variable | Value |
|---|---|
| `PULSEFRAME_TRUSTED_SIGNING_DLIB` | full path to `Azure.CodeSigning.Dlib.dll` |
| `PULSEFRAME_TRUSTED_SIGNING_METADATA` | full path to `metadata.json` |

**Optional**

| Variable | Value |
|---|---|
| `PULSEFRAME_REQUIRE_SIGNING` | `1` for release builds: the build fails instead of producing an unsigned installer |
| `PULSEFRAME_TIMESTAMP_URL` | a different RFC 3161 timestamp server (default `http://timestamp.digicert.com`) |

## 3. Build

```bash
npm run tauri build
```

The build log shows `PULSEFRAME: signed <file> with …` for each file. Check the result: right-click the installer → **Properties → Digital Signatures**.

Without any of the variables, builds still work and print `left unsigned`, so development is never blocked.

## Signing the installers GitHub builds

Tagged releases are built by GitHub Actions (`.github/workflows/build.yml`). To sign the Windows installer there, add two repository secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `WINDOWS_CERTIFICATE` | your `.pfx` certificate file, base64-encoded (PowerShell: `[Convert]::ToBase64String([IO.File]::ReadAllBytes('cert.pfx'))`) |
| `WINDOWS_CERTIFICATE_PASSWORD` | its password |

When `WINDOWS_CERTIFICATE` exists, the build imports it, signs the installer and fails rather than release an unsigned one. Without it, nothing changes. Certificates that live on a hardware token or in a cloud HSM (most EV and many OV certificates) cannot be exported as a `.pfx`; for those, sign on your own PC as described above, or use Azure Trusted Signing.

## macOS (later)

Tauri signs and notarizes Mac builds from environment variables on the Mac that builds them: `APPLE_SIGNING_IDENTITY` (a "Developer ID Application" certificate from an Apple Developer account, $99/year), plus `APPLE_ID`, `APPLE_PASSWORD` (an app-specific password) and `APPLE_TEAM_ID` for notarization. No changes to the project are needed.
