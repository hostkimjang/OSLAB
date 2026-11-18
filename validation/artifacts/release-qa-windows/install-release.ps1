[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Package,
    [Parameter(Mandatory)][string]$LogPath
)

$ErrorActionPreference = 'Stop'
$msi = (Resolve-Path -LiteralPath $Package).ProviderPath
$log = [IO.Path]::GetFullPath($LogPath)
[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($log)) | Out-Null

$name = [IO.Path]::GetFileName($msi)
if ($name -notmatch '^DispatchBoard-(\d+\.\d+\.\d+)\.msi$') {
    throw "Unexpected release package name: $name"
}
$version = $Matches[1]
$arguments = '/i "{0}" /qn /norestart /l*v "{1}"' -f $msi, $log
$installer = Start-Process msiexec.exe -ArgumentList $arguments -Wait -PassThru
$programFiles = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
if (-not $programFiles) { $programFiles = $env:ProgramFiles }
$launcher = Join-Path $programFiles 'OSLab\Dispatch Board\Start-DispatchBoard.ps1'
$versionMarker = "# Dispatch Board release $version"
$installed = $installer.ExitCode -eq 0 -and (Test-Path -LiteralPath $launcher -PathType Leaf) -and
    ($versionMarker -in (Get-Content -LiteralPath $launcher))
[pscustomobject]@{ exitCode = $installer.ExitCode; version = $version; installed = $installed; launcher = $launcher } |
    ConvertTo-Json -Compress
if (-not $installed) { exit 1 }
