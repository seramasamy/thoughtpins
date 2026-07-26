param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$OutputDirectory = (Join-Path `
        (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) `
        "backups\thoughtpins-private-source\current"),
    [Parameter(Mandatory = $true)]
    [securestring]$RecoveryKeyProtectionPassword,
    [string]$SevenZipPath = "C:\Program Files\7-Zip\7z.exe"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repo = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$workspace = (Resolve-Path -LiteralPath (Split-Path -Parent $repo)).Path
if (-not $repo.StartsWith($workspace, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Repository escaped the intended workspace."
}
$outputCandidate = [IO.Path]::GetFullPath($OutputDirectory)
if (-not $outputCandidate.StartsWith($workspace.TrimEnd("\") + "\", [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Backup destination escaped the intended workspace."
}
New-Item -ItemType Directory -Path $outputCandidate -Force | Out-Null
$outputRoot = (Resolve-Path -LiteralPath $outputCandidate).Path
if (-not (Test-Path -LiteralPath $SevenZipPath -PathType Leaf)) {
    throw "7-Zip was not found at the configured path."
}

$tempRoot = Join-Path $repo ".tmp"
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$buildDirectory = Join-Path $tempRoot ("private-source-backup-" + [guid]::NewGuid().ToString("N"))
$verifyDirectory = Join-Path $tempRoot ("private-source-verify-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $buildDirectory, $verifyDirectory | Out-Null

function Assert-TemporaryPath([string]$Path) {
    $resolvedTempRoot = (Resolve-Path -LiteralPath $tempRoot).Path.TrimEnd("\") + "\"
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if (-not $resolved.StartsWith($resolvedTempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Temporary backup path escaped the repository .tmp directory: $resolved"
    }
}

function ConvertFrom-SecureValue([securestring]$Value) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

Assert-TemporaryPath $buildDirectory
Assert-TemporaryPath $verifyDirectory

$archivePath = $null
$keyArchivePath = $null
$checksumPath = $null
$sidecarPath = $null
$password = $null
$keyProtectionPassword = $null
$keyRecord = $null
try {
    $keyProtectionPassword = ConvertFrom-SecureValue $RecoveryKeyProtectionPassword
    if ($keyProtectionPassword.Length -lt 8) {
        throw "The recovery-key protection password must contain at least eight characters."
    }

    $inner = & (Join-Path $PSScriptRoot "create_source_backup.ps1") `
        -RepositoryRoot $repo `
        -OutputDirectory $buildDirectory
    if (-not $inner.EnvironmentIncluded -or $inner.HashVerification -ne "all entries match source") {
        throw "The verified inner source archive did not include the environment or pass entry hashing."
    }

    $innerArchive = Get-Item -LiteralPath $inner.Backup
    $innerChecksum = Get-Item -LiteralPath $inner.ChecksumFile
    $innerSidecar = Get-Item -LiteralPath $inner.PrivateRecoverySidecar
    $innerSha256 = (Get-FileHash -LiteralPath $innerArchive.FullName -Algorithm SHA256).Hash.ToLowerInvariant()

    $randomBytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($randomBytes)
    }
    finally {
        $rng.Dispose()
    }
    $password = [Convert]::ToBase64String($randomBytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")

    $timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
    $archivePath = Join-Path $outputRoot "ThoughtPins-private-source-docs-env-$timestamp.7z"
    $keyArchivePath = "$archivePath.recovery-key.7z"
    $checksumPath = "$archivePath.sha256"
    $sidecarPath = "$archivePath.private-backup.json"

    Push-Location $buildDirectory
    try {
        & $SevenZipPath a -t7z -mx=0 -mhe=on "-p$password" -- `
            $archivePath $innerArchive.Name $innerChecksum.Name $innerSidecar.Name | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "7-Zip failed to create the encrypted private archive."
        }
    }
    finally {
        Pop-Location
    }

    & $SevenZipPath t "-p$password" -- $archivePath | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "7-Zip integrity verification failed."
    }

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $uncredentialedListing = & $SevenZipPath l -ba -- $archivePath 2>&1
        $uncredentialedExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($uncredentialedExitCode -eq 0 -and ($uncredentialedListing -join "`n").Contains($innerArchive.Name)) {
        throw "Archive headers are readable without the recovery password."
    }

    & $SevenZipPath x "-p$password" "-o$verifyDirectory" -y -- $archivePath | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Encrypted archive extraction verification failed."
    }
    $restoredInner = Join-Path $verifyDirectory $innerArchive.Name
    $restoredSha256 = (Get-FileHash -LiteralPath $restoredInner -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($restoredSha256 -ne $innerSha256) {
        throw "Extracted source payload does not match the verified input archive."
    }

    $archive = Get-Item -LiteralPath $archivePath
    $archiveSha256 = (Get-FileHash -LiteralPath $archive.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($checksumPath, "$archiveSha256 *$($archive.Name)`n", $utf8NoBom)

    $keyEntryName = "$($archive.Name).recovery-key.txt"
    $temporaryKeyPath = Join-Path $buildDirectory $keyEntryName
    $keyRecord = @(
        "Thought Pins private source backup recovery key",
        "Archive: $($archive.Name)",
        "Password: $password",
        "Keep this key private. It unlocks an archive containing local environment secrets."
    ) -join "`n"
    [System.IO.File]::WriteAllText($temporaryKeyPath, $keyRecord + "`n", $utf8NoBom)

    Push-Location $buildDirectory
    try {
        & $SevenZipPath a -t7z -mx=0 -mhe=on "-p$keyProtectionPassword" -- `
            $keyArchivePath $keyEntryName | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "7-Zip failed to protect the recovery key."
        }
    }
    finally {
        Pop-Location
    }

    & $SevenZipPath t "-p$keyProtectionPassword" -- $keyArchivePath | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Recovery-key archive integrity verification failed."
    }

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $uncredentialedKeyListing = & $SevenZipPath l -ba -- $keyArchivePath 2>&1
        $uncredentialedKeyExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($uncredentialedKeyExitCode -eq 0 -and ($uncredentialedKeyListing -join "`n").Contains($keyEntryName)) {
        throw "Recovery-key archive headers are readable without the protection password."
    }

    $keyVerifyDirectory = Join-Path $verifyDirectory "recovery-key"
    New-Item -ItemType Directory -Path $keyVerifyDirectory | Out-Null
    & $SevenZipPath x "-p$keyProtectionPassword" "-o$keyVerifyDirectory" -y -- $keyArchivePath | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Recovery-key archive extraction verification failed."
    }
    $restoredKeyPath = Join-Path $keyVerifyDirectory $keyEntryName
    $restoredKeyRecord = [System.IO.File]::ReadAllText($restoredKeyPath, $utf8NoBom)
    if ($restoredKeyRecord -ne ($keyRecord + "`n")) {
        throw "Protected recovery key does not match the generated archive key."
    }
    $keyArchiveSha256 = (Get-FileHash -LiteralPath $keyArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()

    $sidecar = [ordered]@{
        format = "thoughtpins-private-source-backup-v3"
        created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        archive_name = $archive.Name
        archive_bytes = $archive.Length
        sha256 = $archiveSha256
        contains_local_secrets = $true
        embedded_secret_file = ".env"
        encrypted_headers = $true
        encryption = [ordered]@{
            scheme = "7z-aes-256"
            recovery_key_reference = (Split-Path -Leaf $keyArchivePath)
            recovery_key_entry_name = $keyEntryName
            recovery_key_sha256 = $keyArchiveSha256
            recovery_key_scheme = "7z-aes-256"
            recovery_key_headers_encrypted = $true
            recovery_key_password_storage = "operator-managed; not stored in backup metadata"
        }
        payload = [ordered]@{
            name = $innerArchive.Name
            sha256 = $innerSha256
            included_files = [int]$inner.IncludedFiles
            included_source_bytes = [long]$inner.IncludedSourceBytes
            manifest = $inner.Manifest
            source_entry_hash_verification = $inner.HashVerification
        }
        verification = [ordered]@{
            encrypted_archive_test = "passed"
            header_confidentiality = "passed"
            extraction_hash_match = "passed"
            recovery_key_archive_test = "passed"
            recovery_key_header_confidentiality = "passed"
            recovery_key_extraction_match = "passed"
        }
        warning = "Private development backup. Never publish the archive, recovery key, or sidecars."
    }
    [System.IO.File]::WriteAllText(
        $sidecarPath,
        ($sidecar | ConvertTo-Json -Depth 6) + "`n",
        $utf8NoBom
    )

    $recorded = Get-Content -LiteralPath $sidecarPath -Raw | ConvertFrom-Json
    if ($recorded.sha256 -ne $archiveSha256 -or $recorded.payload.sha256 -ne $innerSha256) {
        throw "Private backup metadata verification failed."
    }

    [pscustomobject]@{
        Backup = $archive.FullName
        RecoveryKeyArchive = $keyArchivePath
        ChecksumFile = $checksumPath
        PrivateRecoverySidecar = $sidecarPath
        ArchiveBytes = $archive.Length
        IncludedFiles = [int]$inner.IncludedFiles
        IncludedSourceBytes = [long]$inner.IncludedSourceBytes
        EnvironmentIncluded = $true
        Encryption = "7z-aes-256 with encrypted headers"
        Verification = "archive test, hidden headers, extraction SHA-256, source entry hashes"
    }
}
catch {
    foreach ($partial in @($archivePath, $keyArchivePath, $checksumPath, $sidecarPath)) {
        if ($partial -and (Test-Path -LiteralPath $partial -PathType Leaf)) {
            Remove-Item -LiteralPath $partial -Force
        }
    }
    throw
}
finally {
    $password = $null
    $keyProtectionPassword = $null
    $keyRecord = $null
    foreach ($temporary in @($buildDirectory, $verifyDirectory)) {
        if (Test-Path -LiteralPath $temporary -PathType Container) {
            Assert-TemporaryPath $temporary
            Remove-Item -LiteralPath $temporary -Recurse -Force
        }
    }
}
