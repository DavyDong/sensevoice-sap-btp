$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:AUTH_MODE = 'none'
$env:HOST = '127.0.0.1'
if (-not $env:PORT) { $env:PORT = '8000' }
& .\.venv\Scripts\python.exe run.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
