# One-folder windowed PyInstaller build of PlumbCenter (run from anywhere).
# Outputs dist\PlumbCenter\, zips it, smoke-tests the exe, prints the zip SHA256.
param([switch]$SkipSmoke)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

# Single source of truth for the version: plumbcenter/__init__.py
$Version = (Select-String -LiteralPath (Join-Path $Root "plumbcenter\__init__.py") -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
if (-not $Version) { throw "Could not read __version__ from plumbcenter/__init__.py" }

$icon = Join-Path $Root "assets\plumbcenter.ico"
if (-not (Test-Path -LiteralPath $icon)) { throw "Missing icon: $icon" }

& python -m PyInstaller `
    --noconfirm --clean --windowed `
    --name PlumbCenter `
    --icon $icon `
    --version-file (Join-Path $Root "packaging\version_info.txt") `
    --paths $Root `
    --collect-submodules plumbcenter `
    --collect-all PySide6 `
    --hidden-import keyring.backends.Windows `
    (Join-Path $Root "packaging\launch_gui.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller exited with code $LASTEXITCODE" }

$dist = Join-Path $Root "dist\PlumbCenter"
$exe = Join-Path $dist "PlumbCenter.exe"
if (-not (Test-Path -LiteralPath $exe)) { throw "Build did not produce $exe" }

if (-not $SkipSmoke) { & (Join-Path $Root "packaging\smoke_exe.ps1") -Exe $exe -Version $Version }

$zip = Join-Path $Root "dist\PlumbCenter-$Version-win64.zip"
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path $dist -DestinationPath $zip
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLower()
Write-Output "SHA256 $hash"
Write-Output $zip
# Sidecar checksum: the in-app updater verifies downloads against <asset>.sha256
Set-Content -LiteralPath "$zip.sha256" -Value "$hash  $(Split-Path -Leaf $zip)" -Encoding ascii
