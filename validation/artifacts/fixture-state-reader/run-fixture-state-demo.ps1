param(
  [Parameter(Mandatory = $true)]
  [string]$OutputPath,

  [string]$StatePath = "C:\Oslab\demo-fixture-state.json"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $StatePath)) {
  throw "Fixture state file was not found: $StatePath"
}

$state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
if (-not $state.ready) {
  throw "Fixture state file exists but is not ready: $StatePath"
}

$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$stdout = "fixture state: $($state.message)"
$result = @{
  schemaVersion = 1
  kind = "commandResult"
  command = "read fixture state"
  exitCode = 0
  stdout = ($stdout + [Environment]::NewLine)
  stderr = ""
  metadata = @{
    statePath = $StatePath
    fixtureId = $state.id
    ready = [bool]$state.ready
    message = $state.message
  }
}

$result |
  ConvertTo-Json -Depth 10 |
  Set-Content -Encoding UTF8 $OutputPath

Write-Host $stdout
