param([string]$Python = "")
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not $Python) {
    $Python = Join-Path (Get-Location) '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $Python)) { $Python = 'python' }
}
& $Python -X utf8 -m compileall -q core ui launcher.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -X utf8 -m pip check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -X utf8 -m pytest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& node --check assets/antigravity-hans-overlay.js
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& npm.cmd test
exit $LASTEXITCODE
