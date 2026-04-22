param(
  [Parameter(Mandatory = $true)]
  [string]$InstallDir
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$agentPath = Join-Path $InstallDir "fake-agent.ps1"

@'
$ErrorActionPreference = "Stop"

function Get-OptionValue {
  param(
    [Parameter(Mandatory = $true)]
    [string[]]$Items,
    [Parameter(Mandatory = $true)]
    [string]$Name,
    [string]$Default = ""
  )

  for ($index = 1; $index -lt $Items.Count; $index++) {
    if ($Items[$index] -eq $Name -and ($index + 1) -lt $Items.Count) {
      return $Items[$index + 1]
    }
  }

  return $Default
}

function Write-Json {
  param(
    [Parameter(Mandatory = $true)]
    [hashtable]$Payload
  )

  $Payload | ConvertTo-Json -Depth 10 -Compress | Write-Output
}

function Write-Failure {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Step,
    [Parameter(Mandatory = $true)]
    [string]$Message
  )

  Write-Json @{
    artifactType = "supplyscan-agent-cli-failure"
    failureClass = "supplyscan-agent-cli-failure"
    step = $Step
    message = $Message
  }
}

$mode = if ($args.Count -gt 0) { $args[0] } else { "" }
$statePath = Join-Path $PSScriptRoot "fake-agent-state.json"

switch ($mode) {
  "register" {
    $token = Get-OptionValue -Items $args -Name "--access-token"
    if ([string]::IsNullOrWhiteSpace($token)) {
      Write-Failure -Step "register" -Message "missing access token"
      exit 4
    }

    $assetName = Get-OptionValue -Items $args -Name "--asset-name" -Default "oslab-agent"
    $state = @{
      registered = $true
      assetName = $assetName
      registeredAt = (Get-Date).ToString("o")
    }
    $state | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $statePath
    Write-Json @{
      ok = $true
      step = "register"
      assetName = $assetName
    }
    exit 0
  }

  "status" {
    $registered = Test-Path $statePath
    Write-Json @{
      ok = $registered
      step = "status"
      registered = $registered
    }
    if ($registered) { exit 0 }
    exit 5
  }

  "scan" {
    if (-not (Test-Path $statePath)) {
      Write-Failure -Step "scan" -Message "agent is not registered"
      exit 6
    }

    $outputPath = Get-OptionValue -Items $args -Name "--output" -Default "C:\Oslab\scan-result.json"
    $outputDirectory = Split-Path -Parent $outputPath
    New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

    $result = @{
      schemaVersion = 1
      kind = "inventory"
      records = @(
        @{
          name = "Git"
          version = "2.0.0"
          publisher = "Fake Agent"
          sources = @("Registry")
          confidence = "high"
          evidence = @(
            @{
              type = "registry"
              source = "Registry"
              path = "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\Git"
            }
          )
          metadata = @{
            mode = "agent-cli"
          }
        }
      )
    }

    $result | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $outputPath
    Write-Json @{
      ok = $true
      step = "scan"
      outputPath = $outputPath
      records = 1
    }
    exit 0
  }

  default {
    Write-Failure -Step "dispatch" -Message "unknown mode"
    exit 3
  }
}
'@ | Set-Content -Encoding UTF8 $agentPath

Write-Host "fake agent installer wrote $agentPath"
