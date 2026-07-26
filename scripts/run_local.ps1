param(
    [switch]$ApiOnly,
    [switch]$BotOnly
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}

$env:PYTHONPATH = "src"

$Args = @("-m", "thoughtpins.server")
if ($ApiOnly) {
    $Args += "--api-only"
}
if ($BotOnly) {
    $Args += "--bot-only"
}

& $Python @Args
