# Windows PowerShell setup (untested in the build environment; mirrors scripts/setup.sh).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path .venv)) { py -3.12 -m venv .venv }
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python -m pip install -r services/api/requirements.txt
Push-Location apps/web; npm install --no-audit --no-fund; Pop-Location
$env:PYTHONPATH = "$PWD\packages\irrivise_core;$PWD\services\api"
.\.venv\Scripts\python scripts/sample_data.py --check
.\.venv\Scripts\python -c "from irrivise_api.db.session import migrate; print(migrate())"
Write-Host "Setup finished. Start with .\scripts\dev.ps1"
