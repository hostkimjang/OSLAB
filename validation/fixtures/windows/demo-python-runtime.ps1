$ErrorActionPreference = "Stop"

$root = "C:\Oslab"
$toolsRoot = Join-Path $root "tools"
$pythonRoot = Join-Path $toolsRoot "python"
$pythonZip = Join-Path $toolsRoot "python-3.13.6-embeddable-amd64.zip"
$pythonUrl = "https://www.python.org/ftp/python/3.13.6/python-3.13.6-embeddable-amd64.zip"
New-Item -ItemType Directory -Force -Path $root | Out-Null
New-Item -ItemType Directory -Force -Path $toolsRoot | Out-Null

function Get-CommandPath {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Name
  )

  $command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -eq $command) {
    return $null
  }

  if (-not [string]::IsNullOrWhiteSpace($command.Source)) {
    return $command.Source
  }

  if (-not [string]::IsNullOrWhiteSpace($command.Path)) {
    return $command.Path
  }

  return $null
}

function Test-PythonRuntime {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,

    [string[]]$Arguments = @()
  )

  if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) {
    return $null
  }

  try {
    $versionArgs = @($Arguments + @("--version"))
    $version = (& $Path @versionArgs 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -eq 0 -and $version -match "^Python\s+\d+") {
      return @{
        Path = $Path
        Arguments = $Arguments
        Version = $version
      }
    }
  }
  catch {
    return $null
  }

  return $null
}

$embeddedPython = Join-Path $pythonRoot "python.exe"
$runtime = $null

if (Test-Path -LiteralPath $embeddedPython) {
  $runtime = Test-PythonRuntime -Path $embeddedPython
}

if ($null -eq $runtime) {
  $systemPython = Get-CommandPath "python.exe"
  if ($null -ne $systemPython) {
    $runtime = Test-PythonRuntime -Path $systemPython
  }
}

if ($null -eq $runtime) {
  $launcher = Get-CommandPath "py.exe"
  if ($null -ne $launcher) {
    $runtime = Test-PythonRuntime -Path $launcher -Arguments @("-3")
  }
}

if ($null -eq $runtime) {
  if (-not (Test-Path -LiteralPath $embeddedPython)) {
    Write-Host "Python runtime was not found. Bootstrapping portable Python into $pythonRoot"
    New-Item -ItemType Directory -Force -Path $pythonRoot | Out-Null
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri $pythonUrl -OutFile $pythonZip
    Expand-Archive -LiteralPath $pythonZip -DestinationPath $pythonRoot -Force
    Remove-Item -LiteralPath $pythonZip -Force -ErrorAction SilentlyContinue
  }

  $runtime = Test-PythonRuntime -Path $embeddedPython
}

if ($null -eq $runtime) {
  throw "Python bootstrap did not produce a working runtime at $embeddedPython"
}

$runtimePath = [string]$runtime.Path
$runtimeArgs = @($runtime.Arguments)
$runtimeSource = "system"
if ($runtimePath.StartsWith($pythonRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
  $runtimeSource = "portable"
}
elseif ((Split-Path -Leaf $runtimePath) -ieq "py.exe") {
  $runtimeSource = "launcher"
}

$manifest = @{
  schemaVersion = 1
  kind = "demoRuntime"
  demo = "python-hello"
  ready = $true
  runtime = "python"
  source = $runtimeSource
  executable = $runtimePath
  arguments = $runtimeArgs
  version = [string]$runtime.Version
  bootstrap = @{
    used = ($runtimeSource -eq "portable")
    toolRoot = $pythonRoot
    sourceUrl = $pythonUrl
  }
}

$manifest |
  ConvertTo-Json -Depth 10 |
  Set-Content -Encoding UTF8 "$root\demo-python-runtime.json"

Write-Host "Python runtime ready: $runtimePath"
