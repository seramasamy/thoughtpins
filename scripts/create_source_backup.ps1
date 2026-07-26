param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$OutputDirectory = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [long]$MaxFileBytes = 25MB
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repo = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$outputRoot = (Resolve-Path -LiteralPath $OutputDirectory).Path
$workspace = (Resolve-Path -LiteralPath (Split-Path -Parent $repo)).Path
if (-not $repo.StartsWith($workspace, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Repository escaped the intended workspace."
}
if (-not $outputRoot.StartsWith($workspace, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Backup destination escaped the intended workspace."
}

$excludedDirectoryNames = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)
@(
    ".deps", ".venv", ".tmp", ".ms-playwright", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".gradle", ".gradle-local", ".android-local", ".kotlin",
    "__pycache__", "build", "dist", "htmlcov",
    "node_modules", "playwright-report", "test-results"
) | ForEach-Object { [void]$excludedDirectoryNames.Add($_) }

$excludedRootDirectories = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)
@("backups", "data", "logs", "reports", "vault") |
    ForEach-Object { [void]$excludedRootDirectories.Add($_) }

$excludedExtensions = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)
@(
    ".aab", ".apk", ".db", ".dmg", ".exe", ".ipa", ".log", ".pyc", ".pyo",
    ".sqlite", ".sqlite3", ".zip"
) | ForEach-Object { [void]$excludedExtensions.Add($_) }

$selected = [System.Collections.Generic.List[object]]::new()
$skipped = 0
$directories = [System.Collections.Generic.Queue[System.IO.DirectoryInfo]]::new()
$directories.Enqueue((Get-Item -LiteralPath $repo))
while ($directories.Count -gt 0) {
    $directory = $directories.Dequeue()
    foreach ($child in Get-ChildItem -LiteralPath $directory.FullName -Force) {
        if ($child -is [System.IO.DirectoryInfo]) {
            $relativeDirectory = $child.FullName.Substring($repo.Length + 1).Replace("\", "/")
            if (
                $excludedDirectoryNames.Contains($child.Name) -or
                $excludedRootDirectories.Contains($relativeDirectory) -or
                ($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
            ) {
                $skipped += 1
                continue
            }
            $directories.Enqueue($child)
            continue
        }
        $file = [System.IO.FileInfo]$child
        $relative = $file.FullName.Substring($repo.Length + 1)
        if ($excludedExtensions.Contains($file.Extension) -or $file.Length -gt $MaxFileBytes) {
            $skipped += 1
            continue
        }
        $selected.Add([pscustomobject]@{
            Source = $file.FullName
            Path = $relative.Replace("\", "/")
            Size = [long]$file.Length
            Sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        })
    }
}

if ($selected.Count -lt 100) {
    throw "Backup selection is unexpectedly small: $($selected.Count) files."
}

$selectedPaths = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)
$selected | ForEach-Object { [void]$selectedPaths.Add($_.Path) }
$required = @(
    ".env",
    "README.md",
    "pyproject.toml",
    "src/thoughtpins/api.py",
    "src/thoughtpins/reports/generator.py",
    "frontend/package.json",
    "site/index.html",
    "mobile/ios/ThoughtPinsNative/project.yml",
    "mobile/android/thoughtpins-app/build.gradle.kts",
    "docs/README.md",
    "scripts/create_source_backup.ps1"
)
$missing = @($required | Where-Object { -not $selectedPaths.Contains($_) })
if ($missing.Count -gt 0) {
    throw "Backup selection is missing required files: $($missing -join ', ')"
}

$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$archivePath = Join-Path $outputRoot "ThoughtPins-code-docs-CONTAINS-LOCAL-SECRETS-$timestamp.zip"
$totalBytes = [long](($selected | Measure-Object -Property Size -Sum).Sum)
$manifest = [ordered]@{
    format = "thoughtpins-source-backup-v1"
    created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    source_root = "thoughtpins"
    includes_local_secret_environment = $true
    max_individual_file_bytes = $MaxFileBytes
    exclusions = @(
        "dependencies", "generated builds", "runtime data", "reports",
        "existing archives", "files over 25 MiB"
    )
    file_count = $selected.Count
    total_source_bytes = $totalBytes
    files = @(
        $selected | Sort-Object Path | ForEach-Object {
            [ordered]@{ path = $_.Path; size = $_.Size; sha256 = $_.Sha256 }
        }
    )
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open(
    $archivePath,
    [System.IO.Compression.ZipArchiveMode]::Create
)
try {
    foreach ($item in $selected) {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $zip,
            $item.Source,
            $item.Path,
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }
    $manifestEntry = $zip.CreateEntry(
        "_BACKUP_MANIFEST.json",
        [System.IO.Compression.CompressionLevel]::Optimal
    )
    $writer = [System.IO.StreamWriter]::new(
        $manifestEntry.Open(),
        [System.Text.UTF8Encoding]::new($false)
    )
    try {
        $writer.Write(($manifest | ConvertTo-Json -Depth 6))
    }
    finally {
        $writer.Dispose()
    }
}
finally {
    $zip.Dispose()
}

$verify = [System.IO.Compression.ZipFile]::OpenRead($archivePath)
try {
    $entries = @($verify.Entries)
    if ($entries.Count -ne ($selected.Count + 1)) {
        throw "Archive entry count mismatch: expected $($selected.Count + 1), found $($entries.Count)."
    }
    $entryMap = @{}
    foreach ($entry in $entries) {
        if ($entryMap.ContainsKey($entry.FullName)) {
            throw "Duplicate archive entry: $($entry.FullName)"
        }
        $entryMap[$entry.FullName] = $entry
    }
    if (-not $entryMap.ContainsKey("_BACKUP_MANIFEST.json")) {
        throw "Backup manifest is missing."
    }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        foreach ($item in $selected) {
            if (-not $entryMap.ContainsKey($item.Path)) {
                throw "Archive entry is missing: $($item.Path)"
            }
            $stream = $entryMap[$item.Path].Open()
            try {
                $actual = ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace("-", "").ToLowerInvariant()
            }
            finally {
                $stream.Dispose()
            }
            if ($actual -ne $item.Sha256) {
                throw "Archive hash mismatch: $($item.Path)"
            }
        }
    }
    finally {
        $sha.Dispose()
    }
}
finally {
    $verify.Dispose()
}

$archive = Get-Item -LiteralPath $archivePath
$archiveSha256 = (Get-FileHash -LiteralPath $archive.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$checksumPath = "$archivePath.sha256"
$sidecarPath = "$archivePath.private-backup.json"
$checksumText = "$archiveSha256 *$($archive.Name)`n"
$sidecar = [ordered]@{
    format = "thoughtpins-private-backup-sidecar-v1"
    created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    archive_name = $archive.Name
    archive_bytes = $archive.Length
    sha256 = $archiveSha256
    contains_local_secrets = $true
    embedded_secret_file = ".env"
    encryption = [ordered]@{
        scheme = "none"
        archive_password = $null
        recovery_key_reference = $null
    }
    recovery = [ordered]@{
        verify = "Compare this SHA-256 with $($archive.Name).sha256 before restore."
        warning = "Private local source backup. Do not publish or submit this archive or sidecar."
    }
}
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($checksumPath, $checksumText, $utf8NoBom)
[System.IO.File]::WriteAllText($sidecarPath, ($sidecar | ConvertTo-Json -Depth 5) + "`n", $utf8NoBom)

$recorded = Get-Content -LiteralPath $sidecarPath -Raw | ConvertFrom-Json
if ($recorded.sha256 -ne $archiveSha256) {
    throw "Backup sidecar SHA-256 verification failed."
}

[pscustomobject]@{
    Backup = $archive.FullName
    Sha256 = $archiveSha256
    ChecksumFile = $checksumPath
    PrivateRecoverySidecar = $sidecarPath
    ArchiveBytes = $archive.Length
    IncludedFiles = $selected.Count
    IncludedSourceBytes = $totalBytes
    SkippedGeneratedOrLarge = $skipped
    Manifest = "_BACKUP_MANIFEST.json"
    EnvironmentIncluded = $selectedPaths.Contains(".env")
    HashVerification = "all entries match source"
}
