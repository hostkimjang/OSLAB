param(
  [string]$BlocklistPath = "config/public-release-blocklist.local.txt",
  [switch]$IncludeUntracked
)

$ErrorActionPreference = "Stop"

function Convert-ToRepoPath {
  param([string]$Path)
  return ($Path -replace "\\", "/").TrimStart("./")
}

function Test-TextFile {
  param([string]$Path)

  $extension = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
  $textExtensions = @(
    ".cfg", ".cmd", ".cs", ".css", ".env", ".html", ".js", ".json", ".jsx",
    ".md", ".mjs", ".ps1", ".py", ".sh", ".toml", ".ts", ".tsx", ".txt",
    ".xml", ".yaml", ".yml"
  )

  return $textExtensions -contains $extension
}

$repoRoot = (& git rev-parse --show-toplevel).Trim()
if (-not $repoRoot) {
  throw "Could not resolve git repository root."
}

Set-Location $repoRoot

$tracked = @(& git ls-files | ForEach-Object { Convert-ToRepoPath $_ })
$untracked = @()
if ($IncludeUntracked) {
  $untracked = @(& git ls-files --others --exclude-standard | ForEach-Object { Convert-ToRepoPath $_ })
}

$paths = @($tracked + $untracked) |
  Where-Object { $_ -and ($_ -notmatch '(^|/)(node_modules|\.next|\.venv|__pycache__|\.git)(/|$)') } |
  Sort-Object -Unique

$generatedPatterns = @(
  '^artifact-studio-.*\.(png|md)$',
  '^test-results/',
  '^apps/[^/]+/test-results/',
  '^validation/artifacts/(web-|artifact-studio-smoke-|artifact-studio-project-|api-project-debug-|.*-starter-|web-ui-demo-)',
  '^validation/fixtures/windows/qa-.*\.ps1$',
  '^scenarios/windows/(new-windows-smoke|qa-|uat-).*\.example\.yaml$',
  '^validation/suites/(new-smoke|qa-).*\.example\.yaml$'
)

$blocklistFullPath = Join-Path $repoRoot $BlocklistPath
$privateMarkers = @()
if (Test-Path -LiteralPath $blocklistFullPath) {
  $privateMarkers = @(
    Get-Content -LiteralPath $blocklistFullPath |
      ForEach-Object { $_.Trim() } |
      Where-Object { $_ -and -not $_.StartsWith("#") }
  )
} else {
  Write-Warning "No local private marker blocklist found at $BlocklistPath."
}

$issues = New-Object System.Collections.Generic.List[string]

foreach ($path in $paths) {
  $fullPath = Join-Path $repoRoot $path
  if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
    continue
  }

  foreach ($pattern in $generatedPatterns) {
    if ($path -match $pattern) {
      $issues.Add("generated local artifact path: $path")
      break
    }
  }

  foreach ($marker in $privateMarkers) {
    if ($path.IndexOf($marker, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
      $issues.Add("private marker in path: $path")
      break
    }
  }

  if (-not (Test-TextFile $fullPath)) {
    continue
  }

  $item = Get-Item -LiteralPath $fullPath
  if ($item.Length -gt 5MB) {
    continue
  }

  $content = Get-Content -LiteralPath $fullPath -Raw -ErrorAction SilentlyContinue
  if ($null -eq $content) {
    continue
  }

  foreach ($marker in $privateMarkers) {
    if ($content.IndexOf($marker, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
      $issues.Add("private marker in content: $path")
      break
    }
  }
}

if ($issues.Count -gt 0) {
  Write-Host "[BLOCK] Public release check found $($issues.Count) issue(s)." -ForegroundColor Red
  $issues | Select-Object -First 120 | ForEach-Object { Write-Host " - $_" }
  if ($issues.Count -gt 120) {
    Write-Host " - ... $($issues.Count - 120) more"
  }
  exit 1
}

Write-Host "[OK] Public release check passed." -ForegroundColor Green
