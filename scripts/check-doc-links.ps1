param(
    [string]$RepositoryRoot = (Join-Path $PSScriptRoot "..")
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$docsDirectory = Join-Path $root "docs"

$markdownFiles = @(
    Get-Item -LiteralPath (Join-Path $root "README.md")
    Get-Item -LiteralPath (Join-Path $root "README.ko.md")
    Get-ChildItem -LiteralPath $docsDirectory -Recurse -File -Filter "*.md"
)

$failures = [System.Collections.Generic.List[string]]::new()
$linkPattern = [regex]'!?\[[^\]]*\]\((?<target>[^)]+)\)'

foreach ($file in $markdownFiles) {
    $contents = Get-Content -LiteralPath $file.FullName -Raw
    $contentsWithoutFences = [regex]::Replace($contents, '(?ms)^```.*?^```\s*', '')

    foreach ($match in $linkPattern.Matches($contentsWithoutFences)) {
        $rawTarget = $match.Groups['target'].Value.Trim()
        if ($rawTarget -match '^(https?://|mailto:|tel:|data:|javascript:|app:|#)') {
            continue
        }

        $target = ($rawTarget -split '\s+"', 2)[0].Trim('<', '>')
        $target = ($target -split '#', 2)[0]
        if ([string]::IsNullOrWhiteSpace($target)) {
            continue
        }

        try {
            $decodedTarget = [Uri]::UnescapeDataString($target)
            $candidate = [IO.Path]::GetFullPath((Join-Path $file.DirectoryName $decodedTarget))
        }
        catch {
            $relativeSource = $file.FullName.Substring($root.Length).TrimStart('\', '/')
            $failures.Add("Invalid local link in ${relativeSource}: ${rawTarget}")
            continue
        }

        if (-not (Test-Path -LiteralPath $candidate)) {
            $relativeSource = $file.FullName.Substring($root.Length).TrimStart('\', '/')
            $failures.Add("Missing local link target in ${relativeSource}: ${rawTarget}")
        }
    }
}

$publicPairs = @(
    "index",
    "getting-started",
    "concepts",
    "demos",
    "proxmox-connection",
    "scenarios",
    "fixtures",
    "validation",
    "reports",
    "adoption-guide",
    "web-dashboard",
    "web-dashboard-server",
    "oslab-platform-plan",
    "github-release-checklist"
)

foreach ($baseName in $publicPairs) {
    $englishPath = Join-Path $docsDirectory "${baseName}.md"
    $koreanPath = Join-Path $docsDirectory "${baseName}.ko.md"

    if (-not (Test-Path -LiteralPath $englishPath)) {
        $failures.Add("Missing English document: docs/${baseName}.md")
        continue
    }
    if (-not (Test-Path -LiteralPath $koreanPath)) {
        $failures.Add("Missing Korean document: docs/${baseName}.ko.md")
        continue
    }

    $englishHeader = (Get-Content -LiteralPath $englishPath -TotalCount 12) -join "`n"
    $koreanHeader = (Get-Content -LiteralPath $koreanPath -TotalCount 12) -join "`n"
    if ($englishHeader -notmatch [regex]::Escape("[한국어](${baseName}.ko.md)")) {
        $failures.Add("English language switch missing near top of docs/${baseName}.md")
    }
    if ($koreanHeader -notmatch [regex]::Escape("[English](${baseName}.md)")) {
        $failures.Add("Korean language switch missing near top of docs/${baseName}.ko.md")
    }
}

$readmeEnglish = Get-Content -LiteralPath (Join-Path $root "README.md") -Raw
$readmeKorean = Get-Content -LiteralPath (Join-Path $root "README.ko.md") -Raw
$indexEnglish = Get-Content -LiteralPath (Join-Path $docsDirectory "index.md") -Raw
$indexKorean = Get-Content -LiteralPath (Join-Path $docsDirectory "index.ko.md") -Raw

foreach ($baseName in $publicPairs | Where-Object { $_ -ne "index" }) {
    if ($readmeEnglish -notmatch [regex]::Escape("docs/${baseName}.md")) {
        $failures.Add("README.md does not link the English docs/${baseName}.md")
    }
    if ($readmeKorean -notmatch [regex]::Escape("docs/${baseName}.ko.md")) {
        $failures.Add("README.ko.md does not link the Korean docs/${baseName}.ko.md")
    }
    if ($indexEnglish -notmatch [regex]::Escape("(${baseName}.md)")) {
        $failures.Add("docs/index.md does not link ${baseName}.md")
    }
    if ($indexKorean -notmatch [regex]::Escape("(${baseName}.ko.md)")) {
        $failures.Add("docs/index.ko.md does not link ${baseName}.ko.md")
    }
}

if ($failures.Count -gt 0) {
    $failures | Sort-Object -Unique | ForEach-Object { Write-Error $_ }
    throw "Documentation link and locale audit failed with $($failures.Count) issue(s)."
}

Write-Output "[OK] Documentation links and English/Korean public document pairs are valid."
