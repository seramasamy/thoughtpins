param(
    [Parameter(Mandatory = $true)]
    [string]$SidecarPath,
    [Parameter(Mandatory = $true)]
    [securestring]$RecoveryKeyProtectionPassword,
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$SevenZipPath = "C:\Program Files\7-Zip\7z.exe"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repo = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$sidecarFile = Get-Item -LiteralPath (Resolve-Path -LiteralPath $SidecarPath).Path
$sidecar = Get-Content -LiteralPath $sidecarFile.FullName -Raw | ConvertFrom-Json
if ($sidecar.format -ne "thoughtpins-private-source-backup-v3") {
    throw "Unsupported private source backup sidecar format."
}
if (-not $sidecar.contains_local_secrets -or -not $sidecar.encrypted_headers) {
    throw "Private source backup metadata does not assert encrypted secret-bearing content."
}

$archiveDirectory = $sidecarFile.DirectoryName
$archivePath = Join-Path $archiveDirectory $sidecar.archive_name
$keyPath = Join-Path $archiveDirectory $sidecar.encryption.recovery_key_reference
if (-not (Test-Path -LiteralPath $archivePath -PathType Leaf)) {
    throw "Encrypted archive is missing."
}
if (-not (Test-Path -LiteralPath $keyPath -PathType Leaf)) {
    throw "Protected recovery-key archive is missing."
}
if (-not (Test-Path -LiteralPath $SevenZipPath -PathType Leaf)) {
    throw "7-Zip was not found at the configured path."
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

$keyProtectionPassword = ConvertFrom-SecureValue $RecoveryKeyProtectionPassword
if ($keyProtectionPassword.Length -lt 8) {
    throw "The recovery-key protection password must contain at least eight characters."
}
$password = $null

$tempRoot = Join-Path $repo ".tmp"
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$verifyDirectory = Join-Path $tempRoot ("private-source-independent-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $verifyDirectory | Out-Null
$resolvedTempRoot = (Resolve-Path -LiteralPath $tempRoot).Path.TrimEnd("\") + "\"
$resolvedVerifyDirectory = (Resolve-Path -LiteralPath $verifyDirectory).Path
if (-not $resolvedVerifyDirectory.StartsWith($resolvedTempRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Verification directory escaped the repository .tmp boundary."
}

try {
    $keyArchiveSha256 = (Get-FileHash -LiteralPath $keyPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($keyArchiveSha256 -ne $sidecar.encryption.recovery_key_sha256) {
        throw "Protected recovery-key archive SHA-256 does not match its sidecar."
    }
    & $SevenZipPath t "-p$keyProtectionPassword" -- $keyPath | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Protected recovery-key archive integrity test failed."
    }
    $keyExtractDirectory = Join-Path $verifyDirectory "recovery-key"
    New-Item -ItemType Directory -Path $keyExtractDirectory | Out-Null
    & $SevenZipPath x "-p$keyProtectionPassword" "-o$keyExtractDirectory" -y -- $keyPath | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Protected recovery-key archive extraction failed."
    }
    $recoveryKeyEntry = Join-Path $keyExtractDirectory $sidecar.encryption.recovery_key_entry_name
    if (-not (Test-Path -LiteralPath $recoveryKeyEntry -PathType Leaf)) {
        throw "Recovery-key record is missing from its protected archive."
    }
    $passwordLine = Get-Content -LiteralPath $recoveryKeyEntry |
        Where-Object { $_.StartsWith("Password: ") } |
        Select-Object -First 1
    if (-not $passwordLine) {
        throw "Recovery password record is missing."
    }
    $password = $passwordLine.Substring(10)

    $archiveSha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($archiveSha256 -ne $sidecar.sha256) {
        throw "Encrypted archive SHA-256 does not match its sidecar."
    }

    & $SevenZipPath t "-p$password" -- $archivePath | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Encrypted archive integrity test failed."
    }
    & $SevenZipPath x "-p$password" "-o$verifyDirectory" -y -- $archivePath | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Encrypted archive extraction failed."
    }

    $innerPath = Join-Path $verifyDirectory $sidecar.payload.name
    $innerSha256 = (Get-FileHash -LiteralPath $innerPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($innerSha256 -ne $sidecar.payload.sha256) {
        throw "Extracted source payload SHA-256 does not match its sidecar."
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($innerPath)
    try {
        $entryMap = @{}
        foreach ($entry in $zip.Entries) {
            if ($entryMap.ContainsKey($entry.FullName)) {
                throw "Duplicate source payload entry: $($entry.FullName)"
            }
            $entryMap[$entry.FullName] = $entry
        }
        $manifestEntry = $entryMap["_BACKUP_MANIFEST.json"]
        if (-not $manifestEntry) {
            throw "Source payload manifest is missing."
        }
        $reader = [System.IO.StreamReader]::new($manifestEntry.Open())
        try {
            $manifest = $reader.ReadToEnd() | ConvertFrom-Json
        }
        finally {
            $reader.Dispose()
        }
        if ([int]$manifest.file_count -ne [int]$sidecar.payload.included_files) {
            throw "Source payload file count does not match its sidecar."
        }
        if (-not $entryMap.ContainsKey(".env")) {
            throw "Source payload does not contain the required environment file."
        }

        $sha = [System.Security.Cryptography.SHA256]::Create()
        try {
            foreach ($file in $manifest.files) {
                $path = [string]$file.path
                if (-not $entryMap.ContainsKey($path)) {
                    throw "Source payload entry is missing: $path"
                }
                $stream = $entryMap[$path].Open()
                try {
                    $actual = ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace("-", "").ToLowerInvariant()
                }
                finally {
                    $stream.Dispose()
                }
                if ($actual -ne [string]$file.sha256) {
                    throw "Source payload entry hash mismatch: $path"
                }
            }
        }
        finally {
            $sha.Dispose()
        }

        [pscustomobject]@{
            Status = "passed"
            Archive = (Split-Path -Leaf $archivePath)
            ArchiveBytes = (Get-Item -LiteralPath $archivePath).Length
            ManifestFiles = [int]$manifest.file_count
            EnvironmentEntryPresent = $true
            AllEntryHashesMatch = $true
            OuterChecksumMatches = $true
            EncryptedHeaders = $true
            ProtectedRecoveryKey = $true
            RecoveryKeyHeadersEncrypted = $true
        }
    }
    finally {
        $zip.Dispose()
    }
}
finally {
    $password = $null
    $keyProtectionPassword = $null
    if (Test-Path -LiteralPath $verifyDirectory -PathType Container) {
        $resolvedVerifyDirectory = (Resolve-Path -LiteralPath $verifyDirectory).Path
        if (-not $resolvedVerifyDirectory.StartsWith($resolvedTempRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing unsafe verification cleanup path."
        }
        Remove-Item -LiteralPath $resolvedVerifyDirectory -Recurse -Force
    }
}
