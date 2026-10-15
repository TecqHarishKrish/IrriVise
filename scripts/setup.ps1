$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
if (-not (Test-Path '.venv')) { py -3.12 -m venv .venv }
& .venv/Scripts/python.exe -m pip install -r services/api/requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Push-Location apps/web
try { npm install; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } } finally { Pop-Location }
$env:PYTHONPATH = 'packages/irrivise_core'
& .venv/Scripts/python.exe scripts/sample_data.py
Write-Host 'Setup finished. Start API, worker and web in three terminals as shown in README.md.'
