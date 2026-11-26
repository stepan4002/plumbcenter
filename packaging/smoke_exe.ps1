# Launch smoke test: the exe must open its window and exit 0 on its own (--smoke-test).
param([Parameter(Mandatory)][string]$Exe)
$ErrorActionPreference = "Stop"
$env:PLUMBNOTE_HOME = Join-Path $env:TEMP ("plumbcenter-smoke-" + [guid]::NewGuid())
$p = Start-Process -FilePath $Exe -ArgumentList "--smoke-test" -PassThru
if (-not $p.WaitForExit(60000)) { $p.Kill(); throw "Smoke test: exe still running after 60 s" }
if ($p.ExitCode -ne 0) { throw "Smoke test: exe exited with code $($p.ExitCode)" }
$v = (Get-Item -LiteralPath $Exe).VersionInfo
if ($v.ProductVersion -ne "1.0.0") { throw "Smoke test: version metadata is '$($v.ProductVersion)', expected 1.0.0" }
Write-Output "Smoke test OK ($Exe, version $($v.ProductVersion))"
