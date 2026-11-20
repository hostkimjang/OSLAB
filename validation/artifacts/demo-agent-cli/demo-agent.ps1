<#
.SYNOPSIS
Demo Agent for Windows, a stand-in endpoint inventory agent for OSLab demos.

.DESCRIPTION
demo-agent.py in the same folder is the Linux edition. Both editions read the
package version from VERSION and provide the same commands:

  version                                   build, OS, installed version and registration
  install                                   install or upgrade, migrating 2.3 config and state
  register -ServerUrl URL -AssetName NAME   create the local asset registration
  status                                    version, registration, config and migration state
  scan -Output PATH                         write an inventory of installed programs

With -Json, stdout carries exactly one JSON object and the human-readable
progress goes to stderr. DEMO_AGENT_ROOT points every write at a sandbox
directory instead of C:\, which is useful for local testing.
#>
param(
  [Parameter(Position = 0)]
  [ValidateSet("version", "install", "register", "status", "scan")]
  [string]$Action,

  [string]$ServerUrl = "https://demo.example.invalid",

  [string]$AssetName,

  [string]$Output,

  [switch]$Json
)

$ErrorActionPreference = "Stop"

$Product = "Demo Agent"
$Publisher = "OSLab demo"
$Build = "20261120.1"
$StateSchema = 2
$DefaultScanIntervalMinutes = 360
$PackageDir = $PSScriptRoot
$PackageFiles = @("demo-agent.ps1", "VERSION")
$LegacySettings = @("server.url", "scan.interval_hours", "scan.exclude")
$UninstallRoots = @(
  "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
  "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
)

if ($env:DEMO_AGENT_ROOT) {
  $ProgramDir = Join-Path $env:DEMO_AGENT_ROOT "Program Files\DemoAgent"
  $DataDir = Join-Path $env:DEMO_AGENT_ROOT "ProgramData\DemoAgent"
} else {
  $programFiles = $env:ProgramW6432
  if (-not $programFiles) { $programFiles = $env:ProgramFiles }
  $ProgramDir = Join-Path $programFiles "DemoAgent"
  $DataDir = Join-Path $env:ProgramData "DemoAgent"
}
$ConfigPath = Join-Path $DataDir "agent.json"
$LegacyConfigPath = Join-Path $DataDir "agent.ini"
$StatePath = Join-Path $DataDir "state.json"
$BackupRoot = Join-Path $DataDir "backup"
$LogPath = Join-Path $DataDir "logs\agent.log"

# Human-readable progress for someone watching the VM screen. With -Json it goes
# to stderr so that stdout stays a single JSON object.
if ($Json) {
  $script:UiWriter = [Console]::Error
  $script:UiInteractive = -not [Console]::IsErrorRedirected
} else {
  $script:UiWriter = [Console]::Out
  $script:UiInteractive = -not [Console]::IsOutputRedirected
}
$script:StepTotal = 0
$script:StepCurrent = 0

function Write-UiSegment {
  param([string]$Text, [string]$Color = "")
  if ($script:UiInteractive -and $Color) {
    $previousColor = [Console]::ForegroundColor
    [Console]::ForegroundColor = [ConsoleColor]$Color
    $script:UiWriter.Write($Text)
    [Console]::ForegroundColor = $previousColor
  } else {
    $script:UiWriter.Write($Text)
  }
}

function Write-UiTitle([string]$Text) {
  Write-UiSegment $Text "White"
  $script:UiWriter.WriteLine()
}

function Write-UiRow([string]$Label, [string]$Value) {
  $dots = "." * [Math]::Max(3, 40 - $Label.Length)
  Write-UiSegment "  $Label $dots "
  Write-UiSegment $Value "Cyan"
  $script:UiWriter.WriteLine()
}

function Start-UiSteps([int]$Total) {
  $script:StepTotal = $Total
  $script:StepCurrent = 0
}

function Write-UiStep([string]$Label, [string]$Value) {
  $script:StepCurrent += 1
  Write-UiRow "[$($script:StepCurrent)/$($script:StepTotal)] $Label" $Value
  if ($script:UiInteractive) { Start-Sleep -Milliseconds 300 }
}

function Write-UiOk([string]$Text) {
  Write-UiSegment "  "
  Write-UiSegment "OK" "Green"
  Write-UiSegment "  $Text"
  $script:UiWriter.WriteLine()
}

function Write-UiNote([string]$Text) {
  $script:UiWriter.WriteLine("  --  $Text")
}

function Write-UiFail([string]$Text) {
  Write-UiSegment "  "
  Write-UiSegment "FAIL" "Red"
  Write-UiSegment "  $Text"
  $script:UiWriter.WriteLine()
}

function New-AgentError([string]$Code, [string]$Message) {
  $exception = New-Object System.Exception $Message
  $exception.Data["code"] = $Code
  return $exception
}

function Get-UtcNow {
  return [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
}

function Get-ShortId([string]$AssetId) {
  if (-not $AssetId) { return "-" }
  return $AssetId.Substring(0, [Math]::Min(8, $AssetId.Length))
}

function Read-VersionFile([string]$Directory) {
  $path = Join-Path $Directory "VERSION"
  if (-not (Test-Path -LiteralPath $path)) { return $null }
  $version = (Get-Content -LiteralPath $path -Raw -Encoding UTF8).Trim()
  if (-not $version) { return $null }
  return $version
}

function Get-PackageVersion {
  $version = Read-VersionFile $PackageDir
  if (-not $version) { throw (New-AgentError "PACKAGE_INCOMPLETE" "VERSION is missing next to demo-agent.ps1") }
  return $version
}

# ConvertFrom-Json returns PSCustomObject. Ordered hashtables are easier to update and write back.
function ConvertTo-PlainData($Value) {
  if ($null -eq $Value) { return $null }
  if ($Value -is [System.Management.Automation.PSCustomObject]) {
    $table = [ordered]@{}
    foreach ($property in $Value.PSObject.Properties) { $table[$property.Name] = ConvertTo-PlainData $property.Value }
    return $table
  }
  if ($Value -is [System.Array]) {
    $items = @(foreach ($item in $Value) { ConvertTo-PlainData $item })
    return ,$items
  }
  return $Value
}

function Read-JsonFile([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) { return $null }
  try {
    $parsed = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
  } catch {
    throw (New-AgentError "FILE_CORRUPT" "$Path is not valid JSON: $($_.Exception.Message)")
  }
  return ConvertTo-PlainData $parsed
}

function Write-JsonFile([string]$Path, $Payload) {
  $directory = Split-Path -Parent $Path
  New-Item -ItemType Directory -Force -Path $directory | Out-Null
  $text = (ConvertTo-Json -InputObject $Payload -Depth 10) + [Environment]::NewLine
  $encoding = New-Object System.Text.UTF8Encoding $false
  $temporary = "$Path.tmp"
  [System.IO.File]::WriteAllText($temporary, $text, $encoding)
  Move-Item -LiteralPath $temporary -Destination $Path -Force
  return $encoding.GetByteCount($text)
}

function Add-LogLine([string]$Message) {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LogPath) | Out-Null
  Add-Content -LiteralPath $LogPath -Value "$(Get-UtcNow) INFO $Message" -Encoding UTF8
}

function ConvertTo-AsciiJson([string]$Text) {
  $builder = New-Object System.Text.StringBuilder
  foreach ($character in $Text.ToCharArray()) {
    if ([int]$character -gt 127) {
      [void]$builder.AppendFormat("\u{0:x4}", [int]$character)
    } else {
      [void]$builder.Append($character)
    }
  }
  return $builder.ToString()
}

function Get-OsDescription {
  try {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    return "$($os.Caption) $($os.Version)"
  } catch {
    return [Environment]::OSVersion.VersionString
  }
}

function New-State([string]$Version) {
  return [ordered]@{
    schemaVersion = $StateSchema
    kind = "demoAgentState"
    agentVersion = $Version
    registration = $null
    lastScan = $null
    migration = $null
  }
}

function New-DefaultConfig {
  return [ordered]@{
    schemaVersion = 2
    server = [ordered]@{ url = $null }
    scan = [ordered]@{ intervalMinutes = $DefaultScanIntervalMinutes; excludePaths = @() }
  }
}

# Returns the asset registration from a 2.3 (schema 1) or 2.4 (schema 2) state.
function Get-Registration($State) {
  if ($null -eq $State) { return $null }
  if ($State["schemaVersion"] -eq 1) {
    if (-not $State["registered"]) { return $null }
    return [ordered]@{
      assetId = $State["assetId"]
      assetName = $State["assetName"]
      serverUrl = $State["serverUrl"]
      registeredAtUtc = $State["registeredAtUtc"]
      origin = "legacy"
    }
  }
  return $State["registration"]
}

function Format-Registration($Registration) {
  if ($null -eq $Registration) { return "none" }
  return "$(Get-ShortId $Registration["assetId"]) ($($Registration["assetName"]))"
}

function Test-SameRegistration($Current, $Previous) {
  if ($null -eq $Current -or $null -eq $Previous) { return $false }
  return ($Current["assetId"] -eq $Previous["assetId"]) -and ($Current["registeredAtUtc"] -eq $Previous["registeredAtUtc"])
}

function Assert-CurrentState($State) {
  if ($null -ne $State -and $State["schemaVersion"] -ne $StateSchema) {
    throw (New-AgentError "MIGRATION_REQUIRED" "State from an earlier version was found. Run install to migrate it.")
  }
}

function Read-IniFile([string]$Path) {
  $settings = @{}
  $section = ""
  foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
    $trimmed = $line.Trim()
    if ($trimmed -eq "" -or $trimmed.StartsWith(";") -or $trimmed.StartsWith("#")) { continue }
    if ($trimmed -match "^\[(.+)\]$") {
      $section = $Matches[1].Trim().ToLowerInvariant()
      continue
    }
    $separator = $trimmed.IndexOf("=")
    if ($separator -lt 1) { continue }
    $key = $trimmed.Substring(0, $separator).Trim().ToLowerInvariant()
    $settings["$section.$key"] = $trimmed.Substring($separator + 1).Trim()
  }
  return $settings
}

# Translates the 2.3 INI config into the 2.4 JSON config and counts the migrated settings.
function Convert-LegacyConfig([string]$Path) {
  $ini = Read-IniFile $Path
  $intervalHours = [int]($DefaultScanIntervalMinutes / 60)
  if ($ini.ContainsKey("scan.interval_hours")) { $intervalHours = [int]$ini["scan.interval_hours"] }
  $excludePaths = @()
  if ($ini.ContainsKey("scan.exclude")) {
    $excludePaths = @($ini["scan.exclude"].Split(";") | ForEach-Object { $_.Trim() } | Where-Object { $_ })
  }
  $config = [ordered]@{
    schemaVersion = 2
    server = [ordered]@{ url = $ini["server.url"] }
    scan = [ordered]@{ intervalMinutes = $intervalHours * 60; excludePaths = $excludePaths }
  }
  $migrated = @($LegacySettings | Where-Object { $ini.ContainsKey($_) }).Count
  return [ordered]@{ config = $config; migrated = $migrated }
}

# Converts the 2.3 state (schema 1) to schema 2 and keeps its registration as is.
function Convert-LegacyState($Legacy, [string]$Version) {
  $state = New-State $Version
  $registration = Get-Registration $Legacy
  if ($null -ne $registration) {
    if (-not $registration["assetId"]) { $registration["assetId"] = [guid]::NewGuid().ToString() }
    $registration["origin"] = "migrated"
  }
  $state["registration"] = $registration
  if ($Legacy["lastScanUtc"]) {
    $state["lastScan"] = [ordered]@{ atUtc = $Legacy["lastScanUtc"]; recordCount = $Legacy["lastScanRecords"]; scanId = $null }
  }
  return $state
}

function New-BackupDirectory([string]$FromVersion) {
  $backupDir = Join-Path $BackupRoot $FromVersion
  if (Test-Path -LiteralPath $backupDir) {
    $backupDir = Join-Path $BackupRoot "$FromVersion-$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))"
  }
  New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
  return $backupDir
}

# Backs up the 2.3 data, then converts its INI config and schema 1 state.
function Invoke-Migration([string]$Version, [string]$FromVersion, $State, [bool]$LegacyState, [bool]$LegacyConfig) {
  $backupDir = New-BackupDirectory $FromVersion
  foreach ($path in @($LegacyConfigPath, $StatePath)) {
    if (Test-Path -LiteralPath $path) { Copy-Item -LiteralPath $path -Destination $backupDir }
  }
  Write-UiStep "Backup of $FromVersion data" $backupDir

  $migration = [ordered]@{
    status = "migrated"
    from = $FromVersion
    to = $Version
    atUtc = Get-UtcNow
    backupDir = $backupDir
    configFormat = $null
    stateSchema = $null
    previousRegistration = $null
  }
  if ($LegacyConfig) {
    $converted = Convert-LegacyConfig $LegacyConfigPath
    Write-JsonFile $ConfigPath $converted["config"] | Out-Null
    Remove-Item -LiteralPath $LegacyConfigPath -Force
    $migration["configFormat"] = "ini->json"
    Write-UiStep "Config agent.ini -> agent.json" "$($converted["migrated"]) settings migrated"
  }
  if ($LegacyState) {
    $previous = Get-Registration $State
    $migrated = Convert-LegacyState $State $Version
    Write-JsonFile $StatePath $migrated | Out-Null
    $migration["stateSchema"] = "1->2"
    if ($null -eq $previous) {
      Write-UiStep "State schema 1 -> 2" "no registration to keep"
    } else {
      $migration["previousRegistration"] = [ordered]@{ assetId = $previous["assetId"]; registeredAtUtc = $previous["registeredAtUtc"] }
      $kept = "CHANGED"
      if (Test-SameRegistration $migrated["registration"] $previous) { $kept = "kept" }
      Write-UiStep "State schema 1 -> 2" "registration $(Get-ShortId $previous["assetId"]) $kept"
    }
  }
  return $migration
}

# Replaces the program directory with this package.
function Install-ProgramFiles {
  $source = (Resolve-Path -LiteralPath $PackageDir).Path.TrimEnd("\")
  if ((Test-Path -LiteralPath $ProgramDir) -and ((Resolve-Path -LiteralPath $ProgramDir).Path.TrimEnd("\") -eq $source)) { return }
  if (Test-Path -LiteralPath $ProgramDir) { Remove-Item -LiteralPath $ProgramDir -Recurse -Force }
  New-Item -ItemType Directory -Force -Path $ProgramDir | Out-Null
  foreach ($name in $PackageFiles) {
    Copy-Item -LiteralPath (Join-Path $PackageDir $name) -Destination (Join-Path $ProgramDir $name)
  }
}

function Get-MigrationSummary($State) {
  $currentSchema = $null -ne $State -and $State["schemaVersion"] -eq $StateSchema
  $record = $null
  if ($currentSchema) { $record = $State["migration"] }
  if ($null -eq $record) { $record = @{} }
  $legacyConfig = Test-Path -LiteralPath $LegacyConfigPath
  if (($null -ne $State -and -not $currentSchema) -or $legacyConfig) {
    $status = "required"
  } elseif ($record.Count -gt 0) {
    $status = "migrated"
  } else {
    $status = "not-needed"
  }
  $backupDir = $record["backupDir"]
  $registrationKept = $null
  if ($record["previousRegistration"]) {
    $registrationKept = Test-SameRegistration (Get-Registration $State) $record["previousRegistration"]
  }
  return [ordered]@{
    status = $status
    from = $record["from"]
    backupPresent = [bool]($backupDir -and (Test-Path -LiteralPath $backupDir -PathType Container))
    legacyConfigPresent = $legacyConfig
    registrationKept = $registrationKept
  }
}

function Read-InstalledPrograms {
  $records = New-Object System.Collections.Generic.List[object]
  $seen = @{}
  foreach ($root in $UninstallRoots) {
    if (-not (Test-Path -LiteralPath $root)) { continue }
    foreach ($key in Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue) {
      $entry = Get-ItemProperty -LiteralPath $key.PSPath -ErrorAction SilentlyContinue
      if ($null -eq $entry -or [string]::IsNullOrWhiteSpace($entry.DisplayName)) { continue }
      if ($entry.SystemComponent -eq 1 -or $entry.ParentKeyName) { continue }
      $identity = "$($entry.DisplayName)|$($entry.DisplayVersion)"
      if ($seen.ContainsKey($identity)) { continue }
      $seen[$identity] = $true
      $records.Add([ordered]@{
        name = [string]$entry.DisplayName
        version = [string]$entry.DisplayVersion
        publisher = [string]$entry.Publisher
        sources = @("Registry")
        confidence = "high"
        evidence = @([ordered]@{ type = "registry"; source = "Registry"; path = $key.Name })
        metadata = [ordered]@{ installLocation = [string]$entry.InstallLocation }
      })
    }
  }
  $sorted = @($records | Sort-Object -Property { $_["name"] })
  return ,$sorted
}

function New-AgentRecord([string]$Version, $State, $Registration) {
  $evidence = @(
    [ordered]@{ type = "state"; source = "DemoAgent"; path = $StatePath },
    [ordered]@{ type = "config"; source = "DemoAgent"; path = $ConfigPath }
  )
  $migration = $State["migration"]
  $migratedFrom = $null
  if ($null -ne $migration -and $migration["backupDir"]) {
    $evidence += [ordered]@{ type = "migration"; source = "DemoAgent"; path = $migration["backupDir"] }
    $migratedFrom = $migration["from"]
  }
  return [ordered]@{
    name = $Product
    version = $Version
    publisher = $Publisher
    sources = @("DemoAgent")
    confidence = "high"
    evidence = $evidence
    metadata = [ordered]@{
      assetId = $Registration["assetId"]
      assetName = $Registration["assetName"]
      serverUrl = $Registration["serverUrl"]
      registeredAtUtc = $Registration["registeredAtUtc"]
      registrationOrigin = $Registration["origin"]
      migratedFrom = $migratedFrom
      installed = $null -ne (Read-VersionFile $ProgramDir)
    }
  }
}

function Invoke-Version {
  $version = Get-PackageVersion
  $installedVersion = Read-VersionFile $ProgramDir
  $registration = Get-Registration (Read-JsonFile $StatePath)
  $osName = Get-OsDescription
  $arch = "x86"
  if ([Environment]::Is64BitOperatingSystem) { $arch = "x64" }
  $installedText = "none"
  if ($installedVersion) { $installedText = $installedVersion }
  Write-UiTitle "$Product $version (build $Build)"
  Write-UiRow "Platform" "windows $arch"
  Write-UiRow "Operating system" $osName
  Write-UiRow "Installed version" $installedText
  Write-UiRow "Registration" (Format-Registration $registration)
  return [ordered]@{
    version = $version
    build = $Build
    platform = "windows"
    os = $osName
    installed = [ordered]@{ present = $null -ne $installedVersion; version = $installedVersion }
    registered = $null -ne $registration
    registration = $registration
  }
}

function Invoke-Install {
  $version = Get-PackageVersion
  Write-UiTitle "$Product $version | install"
  $previousVersion = Read-VersionFile $ProgramDir
  $state = Read-JsonFile $StatePath
  $legacyState = $null -ne $state -and $state["schemaVersion"] -eq 1
  $legacyConfig = Test-Path -LiteralPath $LegacyConfigPath
  $needsMigration = $legacyState -or $legacyConfig
  $needsDefaultConfig = -not (Test-Path -LiteralPath $ConfigPath) -and -not $legacyConfig
  if (-not $previousVersion) {
    $mode = "fresh"
  } elseif ($previousVersion -eq $version) {
    $mode = "reinstall"
  } else {
    $mode = "upgrade"
  }

  $plannedSteps = 2
  if ($needsDefaultConfig) { $plannedSteps += 1 }
  if ($needsMigration) { $plannedSteps += 1 + [int]$legacyConfig + [int]$legacyState }
  Start-UiSteps $plannedSteps
  $previousText = "none"
  if ($previousVersion) { $previousText = $previousVersion }
  Write-UiStep "Installed version" $previousText

  $migration = [ordered]@{ status = "not-needed" }
  if ($needsMigration) {
    $fromVersion = "unknown"
    if ($previousVersion) { $fromVersion = $previousVersion }
    $migration = Invoke-Migration $version $fromVersion $state $legacyState $legacyConfig
  }
  Install-ProgramFiles
  Write-UiStep "Program files" $ProgramDir
  if ($needsDefaultConfig) {
    Write-JsonFile $ConfigPath (New-DefaultConfig) | Out-Null
    Write-UiStep "Default config" $ConfigPath
  }

  $state = Read-JsonFile $StatePath
  if ($null -ne $state) {
    $state["agentVersion"] = $version
    if ($needsMigration) { $state["migration"] = $migration }
    Write-JsonFile $StatePath $state | Out-Null
  }
  Add-LogLine "install mode=$mode version=$version previous=$previousText migration=$($migration["status"])"

  if ($mode -eq "upgrade") {
    $summary = "upgraded $previousVersion -> $version"
    if ($migration["previousRegistration"]) {
      $summary += ", registration $(Get-ShortId $migration["previousRegistration"]["assetId"]) kept, no re-registration"
    }
  } elseif ($mode -eq "fresh") {
    $summary = "installed $version"
  } else {
    $summary = "reinstalled $version"
  }
  Write-UiOk $summary
  return [ordered]@{
    mode = $mode
    version = $version
    previousVersion = $previousVersion
    migration = $migration
  }
}

function Invoke-Register {
  $version = Get-PackageVersion
  Write-UiTitle "$Product $version | register"
  if ([string]::IsNullOrWhiteSpace($AssetName)) { throw (New-AgentError "USAGE" "register requires -AssetName") }
  $state = Read-JsonFile $StatePath
  Assert-CurrentState $state
  $existing = Get-Registration $state
  if ($null -ne $existing) {
    Start-UiSteps 1
    Write-UiStep "Existing registration" (Format-Registration $existing)
    Write-UiOk "already registered as $($existing["assetName"]), nothing changed"
    return [ordered]@{ registered = $true; alreadyRegistered = $true; registration = $existing }
  }

  Start-UiSteps 3
  Write-UiStep "Existing registration" "none"
  $registration = [ordered]@{
    assetId = [guid]::NewGuid().ToString()
    assetName = $AssetName
    serverUrl = $ServerUrl
    registeredAtUtc = Get-UtcNow
    origin = "registered"
  }
  Write-UiStep "Registration ID" $registration["assetId"]
  if ($null -eq $state) { $state = New-State $version }
  $state["registration"] = $registration
  Write-JsonFile $StatePath $state | Out-Null
  $config = Read-JsonFile $ConfigPath
  if ($null -eq $config) { $config = New-DefaultConfig }
  if ($null -eq $config["server"]) { $config["server"] = [ordered]@{} }
  $config["server"]["url"] = $ServerUrl
  Write-JsonFile $ConfigPath $config | Out-Null
  Write-UiStep "Saved to" $StatePath
  Add-LogLine "register asset=$AssetName id=$($registration["assetId"])"
  Write-UiOk "registered $AssetName with $ServerUrl"
  return [ordered]@{ registered = $true; alreadyRegistered = $false; registration = $registration }
}

function Invoke-Status {
  $version = Get-PackageVersion
  Write-UiTitle "$Product $version | status"
  $installedVersion = Read-VersionFile $ProgramDir
  $state = Read-JsonFile $StatePath
  $config = Read-JsonFile $ConfigPath
  $registration = Get-Registration $state
  $migration = Get-MigrationSummary $state
  $scanConfig = @{}
  $serverConfig = @{}
  if ($null -ne $config) {
    if ($null -ne $config["scan"]) { $scanConfig = $config["scan"] }
    if ($null -ne $config["server"]) { $serverConfig = $config["server"] }
  }
  $lastScan = $null
  if ($null -ne $state) { $lastScan = $state["lastScan"] }

  if (-not $installedVersion) {
    Write-UiRow "Version" "$version, not installed"
  } elseif ($migration["status"] -eq "migrated") {
    Write-UiRow "Version" "$installedVersion, upgraded from $($migration["from"])"
  } else {
    Write-UiRow "Version" $installedVersion
  }
  if ($null -eq $registration) {
    Write-UiRow "Asset" "not registered"
  } else {
    Write-UiRow "Asset" ([string]$registration["assetName"])
    Write-UiRow "Registration ID" ([string]$registration["assetId"])
    Write-UiRow "Registered at" ([string]$registration["registeredAtUtc"])
    if ($migration["registrationKept"] -eq $true) {
      Write-UiRow "Registration source" "kept from $($migration["from"]), no re-registration"
    } elseif ($migration["registrationKept"] -eq $false) {
      Write-UiRow "Registration source" "CHANGED during upgrade from $($migration["from"])"
    } else {
      Write-UiRow "Registration source" "new registration"
    }
    Write-UiRow "Server" ([string]$registration["serverUrl"])
  }
  if ($null -eq $config) {
    Write-UiRow "Config" "missing"
  } else {
    Write-UiRow "Config" "schema $($config["schemaVersion"]), scan every $($scanConfig["intervalMinutes"]) min"
  }
  if ($null -eq $state) {
    Write-UiRow "State" "missing"
  } else {
    Write-UiRow "State" "schema $($state["schemaVersion"])"
  }
  if ($null -ne $lastScan) {
    Write-UiRow "Last scan" "$($lastScan["atUtc"]), $($lastScan["recordCount"]) records"
  } else {
    Write-UiRow "Last scan" "never"
  }

  if ($migration["status"] -eq "required") {
    Write-UiFail "data from an earlier version is waiting for install to migrate it"
  } elseif ($null -eq $registration) {
    Write-UiNote "not registered yet"
  } else {
    Write-UiOk "registered as $($registration["assetName"]), ready to scan"
  }
  $stateSchemaVersion = $null
  if ($null -ne $state) { $stateSchemaVersion = $state["schemaVersion"] }
  return [ordered]@{
    version = $version
    installed = [ordered]@{ present = $null -ne $installedVersion; version = $installedVersion }
    registered = $null -ne $registration
    registration = $registration
    config = [ordered]@{
      serverUrl = $serverConfig["url"]
      scanIntervalMinutes = $scanConfig["intervalMinutes"]
      excludePaths = $scanConfig["excludePaths"]
    }
    state = [ordered]@{ schemaVersion = $stateSchemaVersion }
    migration = $migration
  }
}

function Invoke-Scan {
  $version = Get-PackageVersion
  Write-UiTitle "$Product $version | scan"
  if ([string]::IsNullOrWhiteSpace($Output)) { throw (New-AgentError "USAGE" "scan requires -Output") }
  $state = Read-JsonFile $StatePath
  Assert-CurrentState $state
  $registration = Get-Registration $state
  if ($null -eq $registration) { throw (New-AgentError "NOT_REGISTERED" "Register the agent before scanning.") }

  $scanId = [guid]::NewGuid().ToString("N")
  Start-UiSteps 4
  Write-UiStep "Registration" (Format-Registration $registration)
  $programs = Read-InstalledPrograms
  Write-UiStep "Installed programs (Registry)" "$($programs.Count) found"
  $records = @(New-AgentRecord $version $state $registration) + $programs
  Write-UiStep "Agent record" "$Product $version"

  $generatedAt = Get-UtcNow
  $inventory = [ordered]@{
    schemaVersion = 1
    kind = "inventory"
    generatedAtUtc = $generatedAt
    scanId = $scanId
    agent = [ordered]@{ name = $Product; version = $version; platform = "windows" }
    asset = [ordered]@{ id = $registration["assetId"]; name = $registration["assetName"] }
    records = $records
  }
  $bytesWritten = Write-JsonFile $Output $inventory
  Write-UiStep "Inventory" $Output
  $state["lastScan"] = [ordered]@{ atUtc = $generatedAt; recordCount = $records.Count; scanId = $scanId }
  Write-JsonFile $StatePath $state | Out-Null
  Add-LogLine "scan id=$scanId records=$($records.Count) output=$Output"
  Write-UiOk "inventory $($scanId.Substring(0, 8)) written: $($records.Count) records for $($registration["assetName"])"
  return [ordered]@{
    outputPath = $Output
    outputWritten = $true
    bytesWritten = $bytesWritten
    scanId = $scanId
    recordCount = $records.Count
    sources = [ordered]@{ DemoAgent = 1; Registry = $programs.Count }
    asset = [ordered]@{ id = $registration["assetId"]; name = $registration["assetName"]; origin = $registration["origin"] }
    uploadRequested = $false
  }
}

if (-not $Action) {
  [Console]::Error.WriteLine("usage: demo-agent.ps1 <version|install|register|status|scan> [-ServerUrl URL] [-AssetName NAME] [-Output PATH] [-Json]")
  exit 2
}

try {
  switch ($Action) {
    "version" { $result = Invoke-Version }
    "install" { $result = Invoke-Install }
    "register" { $result = Invoke-Register }
    "status" { $result = Invoke-Status }
    "scan" { $result = Invoke-Scan }
  }
  $payload = [ordered]@{ ok = $true; command = $Action }
  foreach ($key in $result.Keys) { $payload[$key] = $result[$key] }
} catch {
  $code = $_.Exception.Data["code"]
  if (-not $code) { $code = "INTERNAL_ERROR" }
  $payload = [ordered]@{ ok = $false; command = $Action; error = [ordered]@{ code = $code; message = $_.Exception.Message } }
  Write-UiFail "$($code): $($_.Exception.Message)"
}

if ($Json) {
  [Console]::Out.WriteLine((ConvertTo-AsciiJson (ConvertTo-Json -InputObject $payload -Depth 10 -Compress)))
  [Console]::Out.Flush()
}
if ($payload["ok"]) { exit 0 }
exit 1
