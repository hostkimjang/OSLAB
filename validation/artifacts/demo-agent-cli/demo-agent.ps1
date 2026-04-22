param(
  [Parameter(Position = 0, Mandatory = $true)]
  [ValidateSet("register", "status", "scan")]
  [string]$Action,

  [string]$ServerUrl = "https://demo.example.invalid",

  [string]$AssetName,

  [string]$Output,

  [switch]$Json
)

$ErrorActionPreference = "Stop"

$root = "C:\Oslab"
$statePath = Join-Path $root "demo-agent-state.json"
New-Item -ItemType Directory -Force -Path $root | Out-Null

function Write-Payload {
  param(
    [Parameter(Mandatory = $true)]
    [hashtable]$Payload
  )

  if ($Json) {
    $Payload | ConvertTo-Json -Depth 10 -Compress | Write-Output
    return
  }

  Write-Host "$($Payload.step): ok=$($Payload.ok)"
}

function Read-State {
  if (-not (Test-Path -LiteralPath $statePath)) {
    throw "Demo agent is not registered. State file is missing: $statePath"
  }

  return Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
}

if ($Action -eq "register") {
  if ([string]::IsNullOrWhiteSpace($AssetName)) {
    throw "register requires -AssetName"
  }

  $state = @{
    schemaVersion = 1
    kind = "demoAgentState"
    registered = $true
    assetName = $AssetName
    serverUrl = $ServerUrl
    statePath = $statePath
    registeredAtUtc = [DateTime]::UtcNow.ToString("o")
  }

  $state |
    ConvertTo-Json -Depth 10 |
    Set-Content -Encoding UTF8 $statePath

  Write-Payload @{
    ok = $true
    step = "register"
    assetName = $AssetName
    statePath = $statePath
  }
  exit 0
}

if ($Action -eq "status") {
  $state = Read-State
  Write-Payload @{
    ok = [bool]$state.registered
    step = "status"
    assetName = $state.assetName
    serverUrl = $state.serverUrl
    registered = [bool]$state.registered
  }
  exit 0
}

if ($Action -eq "scan") {
  $state = Read-State
  if ([string]::IsNullOrWhiteSpace($Output)) {
    throw "scan requires -Output"
  }

  $outputDirectory = Split-Path -Parent $Output
  New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

  $inventory = @{
    schemaVersion = 1
    kind = "inventory"
    records = @(
      @{
        name = "Demo Agent"
        version = "1.0.0"
        publisher = "oslab"
        sources = @("DemoAgent")
        confidence = "high"
        evidence = @(
          @{
            type = "state"
            source = "DemoAgent"
            path = $statePath
          }
        )
        metadata = @{
          assetName = $state.assetName
          serverUrl = $state.serverUrl
        }
      }
    )
  }

  $inventory |
    ConvertTo-Json -Depth 10 |
    Set-Content -Encoding UTF8 $Output

  Write-Payload @{
    ok = $true
    step = "scan"
    assetName = $state.assetName
    output = $Output
    recordCount = 1
  }
  exit 0
}
