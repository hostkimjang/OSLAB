param(
  [Parameter(Mandatory = $true)]
  [string]$OutputPath
)

$ErrorActionPreference = "Stop"

function Get-CommandPath {
  param([Parameter(Mandatory = $true)][string]$Name)
  $command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -eq $command) { return $null }
  if (-not [string]::IsNullOrWhiteSpace($command.Source)) { return $command.Source }
  if (-not [string]::IsNullOrWhiteSpace($command.Path)) { return $command.Path }
  return $null
}

function Test-PythonRuntime {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [string[]]$Arguments = @()
  )
  if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) { return $null }
  try {
    $versionArgs = @($Arguments + @("--version"))
    $version = (& $Path @versionArgs 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -eq 0 -and $version -match "^Python\s+\d+") {
      return @{ Path = $Path; Arguments = $Arguments; Version = $version }
    }
  }
  catch {
    return $null
  }
  return $null
}

$portablePython = "C:\Oslab\tools\python\python.exe"
$runtime = $null
if (Test-Path -LiteralPath $portablePython) { $runtime = Test-PythonRuntime -Path $portablePython }
if ($null -eq $runtime) {
  $systemPython = Get-CommandPath "python.exe"
  if ($null -ne $systemPython) { $runtime = Test-PythonRuntime -Path $systemPython }
}
if ($null -eq $runtime) {
  $launcher = Get-CommandPath "py.exe"
  if ($null -ne $launcher) { $runtime = Test-PythonRuntime -Path $launcher -Arguments @("-3") }
}
if ($null -eq $runtime) {
  throw "Python runtime was not found. Run the demo-python-runtime fixture or install Python in the guest VM."
}

$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$scriptPath = Join-Path $PSScriptRoot "service_smoke.py"
$runArguments = @($runtime.Arguments) + @($scriptPath)
$output = & $runtime.Path @runArguments 2>&1
$exitCode = $LASTEXITCODE
if ($null -eq $exitCode) { $exitCode = 0 }
$text = ($output | Out-String)

$result = @{
  schemaVersion = 1
  kind = "commandResult"
  command = "python service_smoke.py"
  exitCode = $exitCode
  stdout = $text
  stderr = ""
  metadata = @{
    runtime = "python"
    executable = $runtime.Path
    arguments = @($runtime.Arguments)
    version = $runtime.Version
    serviceScript = $scriptPath
    smokeType = "local-http-service"
  }
}

$result |
  ConvertTo-Json -Depth 10 |
  Set-Content -Encoding UTF8 $OutputPath

if ($exitCode -ne 0 -and -not [string]::IsNullOrWhiteSpace($text)) {
  [Console]::Error.WriteLine($text)
}

exit $exitCode
