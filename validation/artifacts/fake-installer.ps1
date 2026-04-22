param(
  [Parameter(Mandatory = $true)]
  [string]$InstallDir
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$scannerPath = Join-Path $InstallDir "fake-scanner.ps1"

@'
param(
  [Parameter(Mandatory = $true)]
  [string]$OutputPath
)

$ErrorActionPreference = "Stop"

$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$result = @{
  schemaVersion = 1
  kind = "inventory"
  records = @(
    @{
      name = "Git"
      version = "2.0.0"
      publisher = "Fake Installer"
      sources = @("Registry")
      confidence = "high"
      evidence = @(
        @{
          type = "registry"
          source = "Registry"
          path = "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\Git"
        }
      )
      metadata = @{}
    }
  )
}

$result |
  ConvertTo-Json -Depth 10 |
  Set-Content -Encoding UTF8 $OutputPath

Write-Host "fake installed scanner wrote $OutputPath"
'@ | Set-Content -Encoding UTF8 $scannerPath

Write-Host "fake installer wrote $scannerPath"
