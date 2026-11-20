# Recreates what Demo Agent 2.3.1 leaves on a registered Windows machine so the
# upgrade scenario starts from the previous release: the program files, the INI
# config, and the schema 1 state that holds the asset registration.
param(
  [string]$ManifestPath = "C:\Oslab\demo-agent-2.3.1-fixture.json"
)

$ErrorActionPreference = "Stop"

$version = "2.3.1"
$registration = [ordered]@{
  assetId = "3f6b2a8c-9d41-4e27-b5c3-1a7e0d9f4b62"
  assetName = "demo-win11-upgrade"
  serverUrl = "https://inventory.example.invalid"
  registeredAtUtc = "2026-08-03T09:14:27Z"
}

if ($env:DEMO_AGENT_ROOT) {
  $programDir = Join-Path $env:DEMO_AGENT_ROOT "Program Files\DemoAgent"
  $dataDir = Join-Path $env:DEMO_AGENT_ROOT "ProgramData\DemoAgent"
} else {
  $programFiles = $env:ProgramW6432
  if (-not $programFiles) { $programFiles = $env:ProgramFiles }
  $programDir = Join-Path $programFiles "DemoAgent"
  $dataDir = Join-Path $env:ProgramData "DemoAgent"
}
$configPath = Join-Path $dataDir "agent.ini"
$statePath = Join-Path $dataDir "state.json"
$utf8 = New-Object System.Text.UTF8Encoding $false

function Write-TextFile([string]$Path, [string]$Text) {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
  [System.IO.File]::WriteAllText($Path, $Text, $utf8)
}

Write-TextFile (Join-Path $programDir "VERSION") "$version`n"
Write-TextFile (Join-Path $programDir "demo-agent.ps1") "Write-Output 'Demo Agent $version'`n"
Write-TextFile $configPath @"
; Demo Agent 2.3 configuration
[server]
url = $($registration.serverUrl)

[scan]
interval_hours = 6
exclude = C:\Windows\Temp;C:\Users\Public\Downloads
"@

$state = [ordered]@{
  schemaVersion = 1
  kind = "demoAgentState"
  registered = $true
  assetId = $registration.assetId
  assetName = $registration.assetName
  serverUrl = $registration.serverUrl
  registeredAtUtc = $registration.registeredAtUtc
  lastScanUtc = "2026-11-18T21:00:04Z"
  lastScanRecords = 46
}
Write-TextFile $statePath (ConvertTo-Json -InputObject $state -Depth 5)
Write-TextFile (Join-Path $dataDir "logs\agent.log") @"
$($registration.registeredAtUtc) INFO register asset=$($registration.assetName) id=$($registration.assetId)
2026-11-18T21:00:04Z INFO scan records=46
"@

$manifest = [ordered]@{
  schemaVersion = 1
  kind = "fixtureResult"
  ready = $true
  fixture = "demo-agent-2.3.1-installed"
  product = "Demo Agent"
  version = $version
  registration = $registration
  paths = [ordered]@{ programDir = $programDir; config = $configPath; state = $statePath }
}
Write-TextFile $ManifestPath (ConvertTo-Json -InputObject $manifest -Depth 5)
Write-Output "Demo Agent $version installed and registered as $($registration.assetName) ($($registration.assetId))"
