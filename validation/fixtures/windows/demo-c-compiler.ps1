$ErrorActionPreference = "Stop"

$root = "C:\Oslab"
$toolsRoot = Join-Path $root "tools"
$tccRoot = Join-Path $toolsRoot "tcc"
$tccZip = Join-Path $toolsRoot "tcc-0.9.27-win64-bin.zip"
$tccUrl = "https://download.savannah.gnu.org/releases/tinycc/tcc-0.9.27-win64-bin.zip"
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

$compiler = Get-CommandPath "cl.exe"
$compilerKind = "msvc"

if ($null -eq $compiler) {
  $compiler = Get-CommandPath "gcc.exe"
  $compilerKind = "gcc"
}

if ($null -eq $compiler) {
  $compiler = Get-CommandPath "clang.exe"
  $compilerKind = "clang"
}

if ($null -eq $compiler) {
  $tcc = Get-ChildItem -LiteralPath $tccRoot -Filter tcc.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -eq $tcc) {
    Write-Host "C compiler was not found. Bootstrapping TinyCC into $tccRoot"
    New-Item -ItemType Directory -Force -Path $tccRoot | Out-Null
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri $tccUrl -OutFile $tccZip
    Expand-Archive -LiteralPath $tccZip -DestinationPath $tccRoot -Force
    Remove-Item -LiteralPath $tccZip -Force -ErrorAction SilentlyContinue
    $tcc = Get-ChildItem -LiteralPath $tccRoot -Filter tcc.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
  }
  if ($null -eq $tcc) {
    throw "TinyCC bootstrap did not produce tcc.exe under $tccRoot"
  }
  $compiler = $tcc.FullName
  $compilerKind = "tcc"
}

$compilerPath = [string]$compiler
$manifest = @{
  schemaVersion = 1
  kind = "demoRuntime"
  demo = "c-hello"
  ready = $true
  runtime = "c-compiler"
  compiler = $compilerKind
  executable = $compilerPath
  bootstrap = @{
    used = ($compilerPath.StartsWith($tccRoot, [System.StringComparison]::OrdinalIgnoreCase))
    toolRoot = $tccRoot
    sourceUrl = $tccUrl
  }
}

$manifest |
  ConvertTo-Json -Depth 10 |
  Set-Content -Encoding UTF8 "$root\demo-c-compiler.json"

Write-Host "C compiler ready: $compilerKind at $compilerPath"
