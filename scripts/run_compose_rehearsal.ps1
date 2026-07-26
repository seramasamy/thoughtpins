param(
  [switch]$KeepRunning,
  [switch]$SkipBuild,
  [int]$HealthTimeoutSeconds = 180,
  [string]$ProjectName = "thoughtpins-rehearsal",
  [string]$ReportPath = ""
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
  $Python = "python"
}

$Steps = New-Object System.Collections.Generic.List[object]
$StartedAt = [DateTime]::UtcNow
$OverallStatus = "running"
$StoppedComposeProject = $false

function New-Stamp {
  return [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
}

function Assert-SafeComposeProjectName {
  param([string]$Name)
  if ([string]::IsNullOrWhiteSpace($Name)) {
    throw "Compose ProjectName cannot be empty."
  }
  if ($Name -notmatch "^thoughtpins-[a-z0-9][a-z0-9-]{0,50}$") {
    throw "Refusing Compose ProjectName '$Name'. Use a thoughtpins-* project name so teardown cannot target unrelated Compose projects."
  }
}

function Add-StepResult {
  param(
    [string]$Name,
    [string]$Status,
    [datetime]$Started,
    [string]$Detail = ""
  )
  $elapsed = [Math]::Round(([DateTime]::UtcNow - $Started).TotalSeconds, 2)
  $Steps.Add([pscustomobject]@{
    name = $Name
    status = $Status
    seconds = $elapsed
    detail = $Detail
  }) | Out-Null
}

function Invoke-Step {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][scriptblock]$Block
  )
  $started = [DateTime]::UtcNow
  Write-Host "==> $Name"
  try {
    & $Block
    if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {
      throw "step failed with exit code $LASTEXITCODE"
    }
    Add-StepResult -Name $Name -Status "passed" -Started $started
    Write-Host "ok: $Name"
  } catch {
    Add-StepResult -Name $Name -Status "failed" -Started $started -Detail ($_.Exception.Message)
    throw
  }
}

function Set-ScopedEnv {
  param([string]$Name, [string]$Value, [hashtable]$Previous)
  if (-not $Previous.ContainsKey($Name)) {
    $Previous[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process")
  }
  [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
}

function Restore-ScopedEnv {
  param([hashtable]$Previous)
  foreach ($name in $Previous.Keys) {
    [Environment]::SetEnvironmentVariable($name, $Previous[$name], "Process")
  }
}

function Wait-ForHealth {
  param([string]$Url, [int]$TimeoutSeconds)
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    try {
      $response = Invoke-RestMethod -Uri $Url -TimeoutSec 5
      if ($response.status -eq "ok") { return }
    } catch {
      Start-Sleep -Seconds 2
    }
  } while ((Get-Date) -lt $deadline)
  throw "Timed out waiting for $Url"
}

function Invoke-DockerCompose {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
  docker compose -p $ProjectName @Args
  if ($LASTEXITCODE -ne 0) { throw "docker compose $($Args -join ' ') failed with exit code $LASTEXITCODE" }
}

function Write-RehearsalReport {
  param([string]$Status)
  $reports = Join-Path $Root "reports"
  New-Item -ItemType Directory -Force -Path $reports | Out-Null
  $path = $ReportPath
  if ([string]::IsNullOrWhiteSpace($path)) {
    $path = Join-Path $reports ("compose-rehearsal-{0}.json" -f (New-Stamp))
  }
  $payload = [pscustomobject]@{
    app = "Thought Pins"
    generated_at_utc = [DateTime]::UtcNow.ToString("o")
    status = $Status
    project_name = $ProjectName
    keep_running = [bool]$KeepRunning
    skip_build = [bool]$SkipBuild
    started_at_utc = $StartedAt.ToString("o")
    finished_at_utc = [DateTime]::UtcNow.ToString("o")
    stopped_compose_project = $StoppedComposeProject
    base_url = "http://127.0.0.1:8420"
    checks = @(
      "docker compose config",
      "compose up api web worker postgres redis qdrant migrate",
      "GET /health",
      "web smoke GET /app",
      "production_parity_check.py --strict-api --with-postgres-rls",
      "smoke_api.py",
      "smoke_restore_backup.py"
    )
    steps = @($Steps)
  }
  $payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $path -Encoding utf8
  Write-Host "compose rehearsal report: $path"
}

Set-Location -LiteralPath $Root
Assert-SafeComposeProjectName -Name $ProjectName

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker is not installed or is not on PATH."
}

$previous = @{}
$ownerDb = "postgresql+psycopg2://thoughtpins:thoughtpins@127.0.0.1:5432/thoughtpins"
$appDb = "postgresql+psycopg2://thoughtpins_app:thoughtpins_app@127.0.0.1:5432/thoughtpins"
$baseUrl = "http://127.0.0.1:8420"

try {
  Invoke-Step "docker daemon" {
    docker info *> $null
    if ($LASTEXITCODE -ne 0) { throw "docker info failed with exit code $LASTEXITCODE" }
  }

  Invoke-Step "docker compose config" {
    Invoke-DockerCompose config *> $null
  }

  Invoke-Step "start compose services" {
    if ($SkipBuild) {
      Invoke-DockerCompose up -d postgres redis qdrant migrate api web worker
    } else {
      Invoke-DockerCompose up -d --build postgres redis qdrant migrate api web worker
    }
  }

  Invoke-Step "wait for API health" {
    Wait-ForHealth -Url "$baseUrl/health" -TimeoutSeconds $HealthTimeoutSeconds
  }

  Invoke-Step "web smoke" {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8421/app" -TimeoutSec 10
    if ($response.StatusCode -ne 200 -or $response.Content -notmatch "Thought Pins") {
      throw "web smoke failed for http://127.0.0.1:8421/app"
    }
  }

  Set-ScopedEnv -Name "DATABASE_URL" -Value $ownerDb -Previous $previous
  Set-ScopedEnv -Name "RLS_VERIFY_DATABASE_URL" -Value $appDb -Previous $previous
  Set-ScopedEnv -Name "THOUGHTPINS_BASE_URL" -Value $baseUrl -Previous $previous
  Set-ScopedEnv -Name "THOUGHTPINS_SMOKE_WAIT_JOB" -Value "true" -Previous $previous
  Set-ScopedEnv -Name "THOUGHTPINS_SMOKE_SEED_LOCAL" -Value "true" -Previous $previous
  Set-ScopedEnv -Name "THOUGHTPINS_SMOKE_HTTP_TIMEOUT_SECONDS" -Value "90" -Previous $previous

  Invoke-Step "production parity with live API and RLS" {
    & $Python scripts\production_parity_check.py --base-url $baseUrl --strict-api --with-postgres-rls
    if ($LASTEXITCODE -ne 0) { throw "step failed with exit code $LASTEXITCODE" }
  }

  Invoke-Step "HTTP API smoke" {
    & $Python scripts\smoke_api.py
    if ($LASTEXITCODE -ne 0) { throw "step failed with exit code $LASTEXITCODE" }
  }

  Invoke-Step "backup restore smoke" {
    & $Python scripts\smoke_restore_backup.py
    if ($LASTEXITCODE -ne 0) { throw "step failed with exit code $LASTEXITCODE" }
  }

  $OverallStatus = "passed"
  Write-Host "compose rehearsal passed"
} catch {
  $OverallStatus = "failed"
  throw
} finally {
  Restore-ScopedEnv -Previous $previous
  if (-not $KeepRunning) {
    Write-Host "==> stop compose project $ProjectName"
    try {
      docker compose -p $ProjectName down
      if ($LASTEXITCODE -eq 0) { $StoppedComposeProject = $true }
    } catch {
      Write-Warning ("Failed to stop compose project {0}: {1}" -f $ProjectName, $_.Exception.Message)
    }
  } else {
    Write-Host "compose project $ProjectName left running because -KeepRunning was supplied"
  }
  Write-RehearsalReport -Status $OverallStatus
}
