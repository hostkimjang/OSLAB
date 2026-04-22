param(
  [Parameter(Mandatory = $true)]
  [string]$OutputPath
)

$ErrorActionPreference = "Stop"

$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$os = Get-CimInstance -ClassName Win32_OperatingSystem
$psVersion = $PSVersionTable.PSVersion.ToString()
$lines = @(
  "oslab powershell system demo",
  "computer=$env:COMPUTERNAME",
  "os=$($os.Caption)",
  "version=$($os.Version)",
  "powershell=$psVersion"
)

$result = @{
  schemaVersion = 1
  kind = "commandResult"
  command = "powershell system inventory"
  exitCode = 0
  stdout = (($lines -join [Environment]::NewLine) + [Environment]::NewLine)
  stderr = ""
  metadata = @{
    computerName = $env:COMPUTERNAME
    osCaption = $os.Caption
    osVersion = $os.Version
    osBuildNumber = $os.BuildNumber
    architecture = $env:PROCESSOR_ARCHITECTURE
    powershellVersion = $psVersion
  }
}

$result |
  ConvertTo-Json -Depth 10 |
  Set-Content -Encoding UTF8 $OutputPath

Write-Host "system demo wrote $OutputPath"
