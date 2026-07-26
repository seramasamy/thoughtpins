param(
    [Parameter(Mandatory = $true)]
    [string]$SourceDirectory,
    [Parameter(Mandatory = $true)]
    [string]$DestinationDirectory,
    [Parameter(Mandatory = $true)]
    [securestring]$ProtectionPassword,
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$SevenZipPath = "C:\Program Files\7-Zip\7z.exe"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repo = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$workspace = (Resolve-Path -LiteralPath (Split-Path -Parent $repo)).Path
$sourceRoot = (Resolve-Path -LiteralPath $SourceDirectory).Path
$destinationRoot = (Resolve-Path -LiteralPath $DestinationDirectory).Path
$workspacePrefix = $workspace.TrimEnd("\") + "\"
foreach ($path in @($repo, $sourceRoot, $destinationRoot)) {
    if (
        -not $path.Equals($workspace, [StringComparison]::OrdinalIgnoreCase) -and
        -not $path.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase)
    ) {
        throw "Legacy backup migration path escaped the intended workspace: $path"
    }
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

$tempRoot = Join-Path $repo ".tmp"
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$resolvedTempRoot = (Resolve-Path -LiteralPath $tempRoot).Path
$tempPrefix = $resolvedTempRoot.TrimEnd("\") + "\"
$password = ConvertFrom-SecureValue $ProtectionPassword
if ($password.Length -lt 8) {
    throw "The legacy bundle protection password must contain at least eight characters."
}

$results = @()
try {
    $archives = Get-ChildItem -LiteralPath $sourceRoot -File | Where-Object {
        $_.Name -match '^ThoughtPins-private-source-docs-env-\d{4}-\d{2}-\d{2}_\d{6}\.7z$'
    }
    foreach ($archive in $archives) {
        if ($archive.DirectoryName -ne $sourceRoot) {
            throw "Unexpected legacy backup source parent: $($archive.FullName)"
        }
        $sourcePaths = @(
            $archive.FullName,
            "$($archive.FullName).private-backup.json",
            "$($archive.FullName).recovery-key.txt",
            "$($archive.FullName).sha256"
        )
        $sourceFiles = foreach ($sourcePath in $sourcePaths) {
            $sourceFile = Get-Item -LiteralPath (Resolve-Path -LiteralPath $sourcePath).Path
            if ($sourceFile.DirectoryName -ne $sourceRoot) {
                throw "Legacy backup source escaped its expected directory: $($sourceFile.FullName)"
            }
            $sourceFile
        }

        $bundlePath = Join-Path $destinationRoot ($archive.BaseName + ".legacy-bundle.7z")
        $bundleChecksumPath = "$bundlePath.sha256"
        if (Test-Path -LiteralPath $bundlePath) {
            throw "Legacy bundle already exists: $bundlePath"
        }

        $expectedHashes = @{}
        foreach ($sourceFile in $sourceFiles) {
            $expectedHashes[$sourceFile.Name] = (
                Get-FileHash -LiteralPath $sourceFile.FullName -Algorithm SHA256
            ).Hash.ToLowerInvariant()
        }

        Push-Location $sourceRoot
        try {
            $sourceNames = $sourceFiles | ForEach-Object { $_.Name }
            & $SevenZipPath a -t7z -mx=0 -mhe=on "-p$password" -- `
                $bundlePath $sourceNames | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "7-Zip failed to create legacy bundle: $bundlePath"
            }
        }
        finally {
            Pop-Location
        }

        & $SevenZipPath t "-p$password" -- $bundlePath | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Legacy bundle integrity verification failed: $bundlePath"
        }

        $verifyDirectory = Join-Path $resolvedTempRoot (
            "legacy-private-backup-" + [guid]::NewGuid().ToString("N")
        )
        New-Item -ItemType Directory -Path $verifyDirectory | Out-Null
        try {
            $resolvedVerifyDirectory = (Resolve-Path -LiteralPath $verifyDirectory).Path
            if (-not $resolvedVerifyDirectory.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Legacy verification directory escaped the repository temporary directory."
            }
            & $SevenZipPath x "-p$password" "-o$resolvedVerifyDirectory" -y -- $bundlePath | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "Legacy bundle extraction verification failed: $bundlePath"
            }
            foreach ($name in $expectedHashes.Keys) {
                $restoredPath = Join-Path $resolvedVerifyDirectory $name
                $actualHash = (
                    Get-FileHash -LiteralPath $restoredPath -Algorithm SHA256
                ).Hash.ToLowerInvariant()
                if ($actualHash -ne $expectedHashes[$name]) {
                    throw "Legacy bundle entry hash mismatch: $name"
                }
            }
        }
        finally {
            if (Test-Path -LiteralPath $verifyDirectory -PathType Container) {
                $resolvedVerifyDirectory = (Resolve-Path -LiteralPath $verifyDirectory).Path
                if (-not $resolvedVerifyDirectory.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) {
                    throw "Refusing unsafe legacy verification cleanup path."
                }
                Remove-Item -LiteralPath $resolvedVerifyDirectory -Recurse -Force
            }
        }

        $bundleHash = (Get-FileHash -LiteralPath $bundlePath -Algorithm SHA256).Hash.ToLowerInvariant()
        [IO.File]::WriteAllText(
            $bundleChecksumPath,
            "$bundleHash *$(Split-Path -Leaf $bundlePath)`n",
            [Text.UTF8Encoding]::new($false)
        )
        foreach ($sourceFile in $sourceFiles) {
            Remove-Item -LiteralPath $sourceFile.FullName -Force
        }
        $results += [pscustomobject]@{
            Bundle = $bundlePath
            BundleChecksum = $bundleChecksumPath
            BundledFiles = $sourceFiles.Count
            EntryHashesVerified = $true
            LooseSourceFilesRemoved = $true
        }
    }
    $results
}
finally {
    $password = $null
}
