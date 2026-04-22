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
      publisher = "Fake Scanner"
      sources = @("Registry")
      confidence = "high"
      evidence = @(
        @{
          type = "fixture"
          source = "fake-scanner"
          path = "validation/artifacts/fake-scanner/fake-scanner.ps1"
        }
      )
      metadata = @{}
    }
  )
}

$result |
  ConvertTo-Json -Depth 10 |
  Set-Content -Encoding UTF8 $OutputPath

Write-Host "fake scanner wrote $OutputPath"
