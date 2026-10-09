<#
  Code signing for FilmCrafter's Windows builds. Tauri calls this for every file it signs (the app, the installer,
  the uninstaller) through bundle.windows.signCommand. Configure ONE of the routes below with environment variables;
  nothing secret is stored in the repository.

  Route A: a code-signing certificate in the Windows certificate store (a .pfx you imported, or an EV/OV certificate
           on a USB token / cloud HSM that exposes itself to the store):
             FILMCRAFTER_SIGN_THUMBPRINT   the certificate's SHA-1 thumbprint

  Route B: Azure Trusted Signing (Microsoft's signing service; no hardware token):
             FILMCRAFTER_TRUSTED_SIGNING_DLIB       full path to Azure.CodeSigning.Dlib.dll
             FILMCRAFTER_TRUSTED_SIGNING_METADATA   full path to metadata.json (Endpoint, CodeSigningAccountName,
                                                   CertificateProfileName); sign in with `az login` first

  Optional:  FILMCRAFTER_TIMESTAMP_URL   RFC 3161 timestamp server (default http://timestamp.digicert.com)
             FILMCRAFTER_REQUIRE_SIGNING=1   fail the build instead of producing an unsigned one (use for releases)

  With nothing configured the build continues unsigned and says so, so everyday development builds keep working.
#>
param([Parameter(Mandatory = $true)][string]$File)
$ErrorActionPreference = "Stop"

function Find-SignTool {
  $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $kits = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
  $hit = Get-ChildItem $kits -Filter signtool.exe -Recurse -ErrorAction SilentlyContinue |
         Where-Object { $_.FullName -match "\\x64\\" } | Sort-Object FullName -Descending | Select-Object -First 1
  if ($hit) { return $hit.FullName }
  throw "signtool.exe not found. Install the Windows SDK (Signing Tools for Desktop Apps)."
}

$name = Split-Path $File -Leaf
$ts = if ($env:FILMCRAFTER_TIMESTAMP_URL) { $env:FILMCRAFTER_TIMESTAMP_URL } else { "http://timestamp.digicert.com" }

if ($env:FILMCRAFTER_SIGN_THUMBPRINT) {
  $signArgs = @("sign", "/sha1", $env:FILMCRAFTER_SIGN_THUMBPRINT, "/fd", "SHA256", "/tr", $ts, "/td", "SHA256",
            "/d", "FilmCrafter", $File)
  $route = "certificate $($env:FILMCRAFTER_SIGN_THUMBPRINT.Substring(0, 8))..."
} elseif ($env:FILMCRAFTER_TRUSTED_SIGNING_DLIB -and $env:FILMCRAFTER_TRUSTED_SIGNING_METADATA) {
  $signArgs = @("sign", "/fd", "SHA256", "/tr", $ts, "/td", "SHA256", "/d", "FilmCrafter",
            "/dlib", $env:FILMCRAFTER_TRUSTED_SIGNING_DLIB, "/dmdf", $env:FILMCRAFTER_TRUSTED_SIGNING_METADATA, $File)
  $route = "Azure Trusted Signing"
} else {
  if ($env:FILMCRAFTER_REQUIRE_SIGNING -eq "1") { throw "Signing is required but no signing route is configured (see src-tauri/scripts/sign.ps1)." }
  Write-Host "FilmCrafter: $name left unsigned (no signing certificate configured)."
  exit 0
}

$tool = Find-SignTool
for ($try = 1; $try -le 3; $try++) {   # timestamp servers are occasionally busy
  & $tool @signArgs
  if ($LASTEXITCODE -eq 0) { break }
  if ($try -eq 3) { throw "Signing $name failed (signtool exit $LASTEXITCODE)." }
  Start-Sleep -Seconds (5 * $try)
}
& $tool verify /pa /q $File | Out-Null
if ($LASTEXITCODE -ne 0 -and $env:FILMCRAFTER_SIGN_TEST -ne "1") { throw "$name was signed but its signature does not verify." }
Write-Host "FilmCrafter: signed $name with $route."
