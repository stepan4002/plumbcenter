# One-folder windowed PyInstaller build of PlumbCenter.
# Outputs dist\PlumbCenter\, zips it, and prints the SHA256 of the zip.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$icon = Join-Path $Root "assets\plumbcenter.ico"
if (-not (Test-Path -LiteralPath $icon)) {
    throw "Missing icon: $icon"
}

$entry = Join-Path $env:TEMP "plumbcenter-pyinstaller-entry.py"
$entrySource = "from plumbcenter.gui.app import main`r`nraise SystemExit(main())`r`n"
[System.IO.File]::WriteAllText($entry, $entrySource)

& python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name PlumbCenter `
    --icon $icon `
    --paths $Root `
    --collect-submodules plumbcenter `
    --collect-all PySide6 `
    --hidden-import keyring.backends.Windows `
    $entry
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller exited with code $LASTEXITCODE"
}

$dist = Join-Path $Root "dist\PlumbCenter"
$exe = Join-Path $dist "PlumbCenter.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "Build did not produce $exe"
}

$zip = Join-Path $Root "dist\PlumbCenter-1.0.0-win64.zip"
if (Test-Path -LiteralPath $zip) {
    Remove-Item -LiteralPath $zip -Force
}
Compress-Archive -Path $dist -DestinationPath $zip
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLower()
Write-Output "SHA256 $hash"
Write-Output $zip
