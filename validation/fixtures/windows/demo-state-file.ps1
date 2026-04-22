$ErrorActionPreference = "Stop"

$root = "C:\Oslab"
$statePath = Join-Path $root "demo-fixture-state.json"
New-Item -ItemType Directory -Force -Path $root | Out-Null

$state = @{
  schemaVersion = 1
  kind = "fixtureState"
  ready = $true
  id = "demo-state-file"
  message = "fixture state ready"
  statePath = $statePath
  createdAtUtc = [DateTime]::UtcNow.ToString("o")
}

$state |
  ConvertTo-Json -Depth 10 |
  Set-Content -Encoding UTF8 $statePath

Write-Host "fixture state wrote $statePath"
