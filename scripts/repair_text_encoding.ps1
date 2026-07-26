param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$excludedDirectoryNames = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)
@(
    ".deps", ".venv", ".tmp", ".ms-playwright", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".gradle", "__pycache__", "build", "dist", "htmlcov",
    "node_modules", "playwright-report", "test-results"
) | ForEach-Object { [void]$excludedDirectoryNames.Add($_) }

$excludedRootDirectories = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)
@("backups", "data", "logs", "reports", "vault") |
    ForEach-Object { [void]$excludedRootDirectories.Add($_) }

$textExtensions = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)
@(
    ".css", ".html", ".js", ".json", ".kt", ".kts", ".md", ".plist", ".ps1",
    ".py", ".swift", ".toml", ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml"
) | ForEach-Object { [void]$textExtensions.Add($_) }

$utf8Strict = [System.Text.UTF8Encoding]::new($false, $true)
$utf8Output = [System.Text.UTF8Encoding]::new($false)
$windows1252SpecialBytes = @{}
@(
    @(0x20AC, 0x80), @(0x201A, 0x82), @(0x0192, 0x83), @(0x201E, 0x84),
    @(0x2026, 0x85), @(0x2020, 0x86), @(0x2021, 0x87), @(0x02C6, 0x88),
    @(0x2030, 0x89), @(0x0160, 0x8A), @(0x2039, 0x8B), @(0x0152, 0x8C),
    @(0x017D, 0x8E), @(0x2018, 0x91), @(0x2019, 0x92), @(0x201C, 0x93),
    @(0x201D, 0x94), @(0x2022, 0x95), @(0x2013, 0x96), @(0x2014, 0x97),
    @(0x02DC, 0x98), @(0x2122, 0x99), @(0x0161, 0x9A), @(0x203A, 0x9B),
    @(0x0153, 0x9C), @(0x017E, 0x9E), @(0x0178, 0x9F)
) | ForEach-Object { $windows1252SpecialBytes[[int]$_[0]] = [byte]$_[1] }
$suspiciousCharacters = [System.Collections.Generic.HashSet[char]]::new()
@(
    [char]0x00E2,
    [char]0x00C3,
    [char]0x00C2,
    [char]0x00F0,
    [char]0xFFFD
) | ForEach-Object { [void]$suspiciousCharacters.Add($_) }

function Get-SuspiciousScore([string]$Value) {
    $score = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($suspiciousCharacters.Contains($character)) { $score += 1 }
    }
    return $score
}

function ConvertFrom-MojibakeLayer([string]$Value) {
    $bytes = [System.Collections.Generic.List[byte]]::new($Value.Length)
    foreach ($character in $Value.ToCharArray()) {
        $codePoint = [int]$character
        if ($codePoint -le 0xFF) {
            $bytes.Add([byte]$codePoint)
            continue
        }
        if ($windows1252SpecialBytes.ContainsKey($codePoint)) {
            $bytes.Add($windows1252SpecialBytes[$codePoint])
            continue
        }
        return $null
    }
    try {
        return $utf8Strict.GetString($bytes.ToArray())
    }
    catch {
        return $null
    }
}

function Repair-Text([string]$Value) {
    $current = $Value
    for ($attempt = 0; $attempt -lt 5; $attempt += 1) {
        $currentScore = Get-SuspiciousScore $current
        if ($currentScore -eq 0) { break }
        $candidate = ConvertFrom-MojibakeLayer $current
        if ($null -eq $candidate) { break }
        $candidateScore = Get-SuspiciousScore $candidate
        if ($candidateScore -ge $currentScore -or $candidate.Contains([char]0xFFFD)) { break }
        $current = $candidate
    }

    return $current.Replace([string][char]0x2014, "--").Replace([string][char]0x2013, "-").
        Replace([string][char]0x2192, "->").Replace([string][char]0x2500, "-").
        Replace([string][char]0x2018, "'").Replace([string][char]0x2019, "'").
        Replace([string][char]0x201C, '"').Replace([string][char]0x201D, '"').
        Replace([string][char]0x2026, "...").Replace([string][char]0x00A0, " ")
}

$directories = [System.Collections.Generic.Queue[System.IO.DirectoryInfo]]::new()
$directories.Enqueue((Get-Item -LiteralPath $root))
$changed = [System.Collections.Generic.List[string]]::new()
while ($directories.Count -gt 0) {
    $directory = $directories.Dequeue()
    foreach ($child in Get-ChildItem -LiteralPath $directory.FullName -Force) {
        if ($child -is [System.IO.DirectoryInfo]) {
            $relativeDirectory = $child.FullName.Substring($root.Length + 1).Replace("\", "/")
            if (
                $excludedDirectoryNames.Contains($child.Name) -or
                $excludedRootDirectories.Contains($relativeDirectory) -or
                ($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
            ) {
                continue
            }
            $directories.Enqueue($child)
            continue
        }
        $file = [System.IO.FileInfo]$child
        if (-not $textExtensions.Contains($file.Extension)) { continue }
        $original = [System.IO.File]::ReadAllText($file.FullName)
        if ((Get-SuspiciousScore $original) -eq 0) { continue }
        $repaired = [System.Text.RegularExpressions.Regex]::Replace(
            $original,
            '(?m)^.*$',
            [System.Text.RegularExpressions.MatchEvaluator]{
                param($match)
                Repair-Text $match.Value
            }
        )
        if ($repaired -ne $original) {
            [System.IO.File]::WriteAllText($file.FullName, $repaired, $utf8Output)
            $changed.Add($file.FullName.Substring($root.Length + 1).Replace("\", "/"))
        }
    }
}

[pscustomobject]@{
    ChangedFiles = $changed.Count
    Files = @($changed)
}
