$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:UV_CACHE_DIR = "$PWD\.cache\uv"
$env:UV_PYTHON_INSTALL_DIR = "$PWD\.cache\python"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' }
if (-not (Test-Path -LiteralPath .venv\Scripts\python.exe)) {
    uv venv --python 3.11.15 .venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
uv pip install --python .venv\Scripts\python.exe --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match -r requirements-windows.lock
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv pip check --python .venv\Scripts\python.exe
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv\Scripts\python.exe scripts\download_models.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host 'Ready. Run: powershell -ExecutionPolicy Bypass -File scripts/start.ps1'
