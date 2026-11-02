$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Không tìm thấy Python runtime: $python" }
if (-not (Test-Path -LiteralPath (Join-Path $root 'models\VoxCPM2'))) { throw "Không tìm thấy model VoxCPM2 trong $root\models" }
$env:FILM_STUDIO_DATA = Join-Path $root 'data'
$env:VOXCPM_MODEL_DIR = Join-Path $root 'models\VoxCPM2'
$env:PATH = (Join-Path $root 'bin') + [IO.Path]::PathSeparator + $env:PATH
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
Set-Location $root
& $python -m uvicorn backend.app:app --host 127.0.0.1 --port 8765 --log-level info
