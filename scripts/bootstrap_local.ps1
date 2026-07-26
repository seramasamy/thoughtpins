param(
    [switch]$WithTelegramHeavy,
    [switch]$WithVoice
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
$NpmCache = Join-Path $Root ".tmp\npm-cache"
$NpmTmp = Join-Path $Root ".tmp\npm-tmp"
New-Item -ItemType Directory -Force -Path $NpmCache, $NpmTmp | Out-Null

& $Python -m pip install --upgrade pip
& $Python -m pip install -e ".[dev,workers]"
& $Python -m pip install "ruff>=0.8" "mypy>=1.11" "pip-audit>=2.7"

if ($WithTelegramHeavy) {
    & $Python -m pip install -e ".[telegram]"
} else {
    & $Python -m pip install "python-telegram-bot>=21.0"
    if ($WithVoice) {
        & $Python -m pip install -e ".[voice]"
    }
}

Push-Location (Join-Path $Root "frontend")
$env:npm_config_cache = $NpmCache
$env:TMP = $NpmTmp
$env:TEMP = $NpmTmp
npm install --ignore-scripts --no-audit --no-fund --loglevel=warn
Pop-Location

& $Python scripts\release_check.py --strict-quality
