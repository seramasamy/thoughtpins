param(
    [string]$ApiBaseUrl = "https://api-staging.thoughtpins.com",
    [string]$PublicUrl = "https://thoughtpins.com",
    [string]$AppUrl = "https://staging.thoughtpins.com"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}

$env:PYTHONPATH = "src"
$env:THOUGHTPINS_BASE_URL = $ApiBaseUrl.TrimEnd("/")
$env:THOUGHTPINS_API_URL = $ApiBaseUrl.TrimEnd("/")
$env:THOUGHTPINS_PUBLIC_URL = $PublicUrl.TrimEnd("/")
$env:THOUGHTPINS_APP_URL = $AppUrl.TrimEnd("/")

& $Python scripts\smoke_public_domain.py
& $Python scripts\smoke_api.py

if (Get-Command k6 -ErrorAction SilentlyContinue) {
    $env:BASE_URL = $ApiBaseUrl.TrimEnd("/")
    k6 run load/k6-health.js
    k6 run load/k6-api-flow.js
} else {
    Write-Host "k6 not found; skipped load tests."
}
