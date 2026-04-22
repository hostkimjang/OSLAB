param(
  [Parameter(Mandatory = $true)]
  [string]$OutputPath
)

$ErrorActionPreference = "Stop"

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

function Invoke-CapturedProcess {
  param(
    [Parameter(Mandatory = $true)]
    [string]$FilePath,

    [string[]]$Arguments = @()
  )

  $output = & $FilePath @Arguments 2>&1
  $exitCode = $LASTEXITCODE
  if ($null -eq $exitCode) {
    $exitCode = 0
  }

  return @{
    ExitCode = $exitCode
    Stdout = ($output | Out-String)
    Stderr = ""
  }
}

$sourcePath = Join-Path $PSScriptRoot "hello.c"
$buildDirectory = "C:\Oslab\c-demo-build"
$exePath = Join-Path $buildDirectory "hello-c.exe"
$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
New-Item -ItemType Directory -Force -Path $buildDirectory | Out-Null

$compiler = Get-CommandPath "cl.exe"
$compilerKind = "msvc"
$compileArgs = @("/nologo", "/Fe:$exePath", $sourcePath)

if ($null -eq $compiler) {
  $compiler = Get-CommandPath "gcc.exe"
  $compilerKind = "gcc"
  $compileArgs = @($sourcePath, "-o", $exePath)
}

if ($null -eq $compiler) {
  $compiler = Get-CommandPath "clang.exe"
  $compilerKind = "clang"
  $compileArgs = @($sourcePath, "-o", $exePath)
}

if ($null -eq $compiler) {
  $tcc = Get-ChildItem -LiteralPath "C:\Oslab\tools\tcc" -Filter tcc.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -ne $tcc) {
    $compiler = $tcc.FullName
    $compilerKind = "tcc"
    $compileArgs = @($sourcePath, "-o", $exePath)
  }
}

if ($null -eq $compiler) {
  throw "C compiler was not found. Run the demo-c-compiler fixture or install cl.exe, gcc.exe, or clang.exe in the guest VM."
}

$compile = Invoke-CapturedProcess -FilePath $compiler -Arguments $compileArgs
if ($compile.ExitCode -ne 0) {
  $compileError = $compile.Stderr
  if ([string]::IsNullOrWhiteSpace($compileError)) {
    $compileError = $compile.Stdout
  }
  throw "C compile failed with exit code $($compile.ExitCode): $compileError"
}

$run = Invoke-CapturedProcess -FilePath $exePath -Arguments @()
$result = @{
  schemaVersion = 1
  kind = "commandResult"
  command = "compile and run hello.c"
  exitCode = $run.ExitCode
  stdout = $run.Stdout
  stderr = $run.Stderr
  metadata = @{
    language = "c"
    compiler = $compilerKind
    compilerPath = $compiler
    compileStdout = $compile.Stdout
    compileStderr = $compile.Stderr
    source = $sourcePath
    executable = $exePath
  }
}

$result |
  ConvertTo-Json -Depth 10 |
  Set-Content -Encoding UTF8 $OutputPath

if ($run.ExitCode -ne 0 -and -not [string]::IsNullOrWhiteSpace($run.Stdout)) {
  [Console]::Error.WriteLine($run.Stdout)
}

exit $run.ExitCode
