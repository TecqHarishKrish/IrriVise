# Windows PowerShell: start API, worker and web in separate windows (untested in the build environment).
Set-Location (Join-Path $PSScriptRoot "..")
$env:PYTHONPATH = "$PWD\packages\irrivise_core;$PWD\services\api"
Start-Process .\.venv\Scripts\python -ArgumentList "-m uvicorn irrivise_api.main:app --host 127.0.0.1 --port 8000"
Start-Sleep -Seconds 4
Start-Process .\.venv\Scripts\python -ArgumentList "-m irrivise_api.worker"
Push-Location apps/web; Start-Process npm -ArgumentList "run dev"; Pop-Location
Write-Host "Web: http://127.0.0.1:5173  API docs: http://127.0.0.1:8000/docs"
