[CmdletBinding()]
param([Parameter(Mandatory)][string]$OutputDir)

$ErrorActionPreference = 'Stop'
$appPath = Join-Path $PSScriptRoot 'dispatch-board.ps1'
if (-not (Test-Path -LiteralPath $appPath -PathType Leaf)) {
    throw "Dispatch Board source is missing: $appPath"
}
$outputPath = [IO.Path]::GetFullPath($OutputDir)
[IO.Directory]::CreateDirectory($outputPath) | Out-Null

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class DispatchMsi {
    [DllImport("msi.dll", CharSet=CharSet.Unicode)] public static extern uint MsiOpenDatabase(string path, IntPtr mode, out uint database);
    [DllImport("msi.dll", CharSet=CharSet.Unicode)] public static extern uint MsiDatabaseOpenView(uint database, string sql, out uint view);
    [DllImport("msi.dll")] public static extern uint MsiViewExecute(uint view, uint record);
    [DllImport("msi.dll")] public static extern uint MsiDatabaseCommit(uint database);
    [DllImport("msi.dll")] public static extern uint MsiCloseHandle(uint handle);
    [DllImport("msi.dll")] public static extern uint MsiCreateRecord(uint fields);
    [DllImport("msi.dll", CharSet=CharSet.Unicode)] public static extern uint MsiRecordSetString(uint record, uint field, string value);
    [DllImport("msi.dll", CharSet=CharSet.Unicode)] public static extern uint MsiRecordSetStream(uint record, uint field, string path);
    [DllImport("msi.dll", CharSet=CharSet.Unicode)] public static extern uint MsiGetSummaryInformation(uint database, string path, uint updates, out uint summary);
    [DllImport("msi.dll", CharSet=CharSet.Unicode)] public static extern uint MsiSummaryInfoSetProperty(uint summary, uint property, uint type, int number, IntPtr time, string value);
    [DllImport("msi.dll")] public static extern uint MsiSummaryInfoPersist(uint summary);
}
'@ -PassThru | Out-Null

function Assert-Msi([uint32]$Result, [string]$Operation) {
    if ($Result -ne 0) { throw "Windows Installer returned $Result while running $Operation" }
}

function Invoke-Sql([uint32]$Database, [string]$Sql, [uint32]$Record = 0) {
    [uint32]$view = 0
    Assert-Msi ([DispatchMsi]::MsiDatabaseOpenView($Database, $Sql, [ref]$view)) $Sql
    try {
        Assert-Msi ([DispatchMsi]::MsiViewExecute($view, $Record)) $Sql
    } finally {
        [void][DispatchMsi]::MsiCloseHandle($view)
    }
}

function Add-Row($Database, [string]$Table, [object[]]$Values) {
    $fields = foreach ($value in $Values) {
        if ($null -eq $value) { 'NULL' }
        elseif ($value -is [string]) { "'" + $value.Replace("'", "''") + "'" }
        else { [string]$value }
    }
    Invoke-Sql $Database ('INSERT INTO `{0}` ({1}) VALUES ({2})' -f $Table, $columns[$Table], ($fields -join ', '))
}

function Write-InstallerCabinet([string]$Directory) {
    $directive = @'
.OPTION EXPLICIT
.Set CabinetNameTemplate=dispatch.cab
.Set DiskDirectoryTemplate=.
.Set Cabinet=on
.Set Compress=on
.Set CompressionType=MSZIP
.Set InfFileName=dispatch.inf
.Set RptFileName=dispatch.rpt
dispatch-board.ps1 BoardScript
Start-DispatchBoard.ps1 LaunchScript
'@
    Set-Content -LiteralPath (Join-Path $Directory 'package.ddf') -Value $directive -Encoding Ascii
    Push-Location -LiteralPath $Directory
    try {
        $cabOutput = & makecab.exe /F package.ddf 2>&1
        if ($LASTEXITCODE -ne 0) { throw "makecab failed: $cabOutput" }
    } finally {
        Pop-Location
    }
}

function New-Package([string]$Version, [string]$ProductCode, [string]$PackageCode, [bool]$Regression) {
    $destination = Join-Path $outputPath "DispatchBoard-$Version.msi"
    if (Test-Path -LiteralPath $destination) { throw "Package already exists: $destination" }

    $tempPath = Join-Path ([IO.Path]::GetTempPath()) ("oslab-dispatch-package-" + [guid]::NewGuid())
    [IO.Directory]::CreateDirectory($tempPath) | Out-Null
    [uint32]$db = 0
    [uint32]$summary = 0
    try {
        Copy-Item -LiteralPath $appPath -Destination $tempPath
        $regressionArgument = if ($Regression) { ' -Regression' } else { '' }
        $launcher = @"
[CmdletBinding()]
param([Parameter(Mandatory)][string]`$DataDir)
# Dispatch Board release $Version
& (Join-Path `$PSScriptRoot 'dispatch-board.ps1') -DataDir `$DataDir -Version '$Version'$regressionArgument
"@
        Set-Content -LiteralPath (Join-Path $tempPath 'Start-DispatchBoard.ps1') -Value $launcher -Encoding UTF8
        Write-InstallerCabinet $tempPath
        $msi = Join-Path $tempPath 'dispatch.msi'
        Assert-Msi ([DispatchMsi]::MsiOpenDatabase($msi, [IntPtr]3, [ref]$db)) 'create package'
        $tables = @(
            'CREATE TABLE `Property` (`Property` CHAR(72) NOT NULL, `Value` CHAR(0) LOCALIZABLE PRIMARY KEY `Property`)'
            'CREATE TABLE `Directory` (`Directory` CHAR(72) NOT NULL, `Directory_Parent` CHAR(72), `DefaultDir` CHAR(255) NOT NULL LOCALIZABLE PRIMARY KEY `Directory`)'
            'CREATE TABLE `Component` (`Component` CHAR(72) NOT NULL, `ComponentId` CHAR(38), `Directory_` CHAR(72) NOT NULL, `Attributes` SHORT NOT NULL, `Condition` CHAR(255), `KeyPath` CHAR(72) PRIMARY KEY `Component`)'
            'CREATE TABLE `Feature` (`Feature` CHAR(38) NOT NULL, `Feature_Parent` CHAR(38), `Title` CHAR(64) LOCALIZABLE, `Description` CHAR(255) LOCALIZABLE, `Display` SHORT, `Level` SHORT NOT NULL, `Directory_` CHAR(72), `Attributes` SHORT NOT NULL PRIMARY KEY `Feature`)'
            'CREATE TABLE `FeatureComponents` (`Feature_` CHAR(38) NOT NULL, `Component_` CHAR(72) NOT NULL PRIMARY KEY `Feature_`, `Component_`)'
            'CREATE TABLE `File` (`File` CHAR(72) NOT NULL, `Component_` CHAR(72) NOT NULL, `FileName` CHAR(255) NOT NULL LOCALIZABLE, `FileSize` LONG NOT NULL, `Version` CHAR(72), `Language` CHAR(20), `Attributes` SHORT, `Sequence` SHORT NOT NULL PRIMARY KEY `File`)'
            'CREATE TABLE `Media` (`DiskId` SHORT NOT NULL, `LastSequence` SHORT NOT NULL, `DiskPrompt` CHAR(64) LOCALIZABLE, `Cabinet` CHAR(255), `VolumeLabel` CHAR(32), `Source` CHAR(72) PRIMARY KEY `DiskId`)'
            'CREATE TABLE `Upgrade` (`UpgradeCode` CHAR(38) NOT NULL, `VersionMin` CHAR(20), `VersionMax` CHAR(20), `Language` CHAR(255), `Attributes` LONG NOT NULL, `Remove` CHAR(255), `ActionProperty` CHAR(72) NOT NULL PRIMARY KEY `UpgradeCode`, `VersionMin`, `VersionMax`, `Language`, `Attributes`)'
            'CREATE TABLE `InstallExecuteSequence` (`Action` CHAR(72) NOT NULL, `Condition` CHAR(255), `Sequence` SHORT PRIMARY KEY `Action`)'
            'CREATE TABLE `InstallUISequence` (`Action` CHAR(72) NOT NULL, `Condition` CHAR(255), `Sequence` SHORT PRIMARY KEY `Action`)'
            'CREATE TABLE `Dialog` (`Dialog` CHAR(72) NOT NULL, `HCentering` SHORT NOT NULL, `VCentering` SHORT NOT NULL, `Width` SHORT NOT NULL, `Height` SHORT NOT NULL, `Attributes` LONG NOT NULL, `Title` CHAR(128) LOCALIZABLE, `Control_First` CHAR(50) NOT NULL, `Control_Default` CHAR(50), `Control_Cancel` CHAR(50) PRIMARY KEY `Dialog`)'
            'CREATE TABLE `Control` (`Dialog_` CHAR(72) NOT NULL, `Control` CHAR(50) NOT NULL, `Type` CHAR(20) NOT NULL, `X` SHORT NOT NULL, `Y` SHORT NOT NULL, `Width` SHORT NOT NULL, `Height` SHORT NOT NULL, `Attributes` LONG, `Property` CHAR(50), `Text` CHAR(0) LOCALIZABLE, `Control_Next` CHAR(50), `Help` CHAR(50) LOCALIZABLE PRIMARY KEY `Dialog_`, `Control`)'
            'CREATE TABLE `ControlEvent` (`Dialog_` CHAR(72) NOT NULL, `Control_` CHAR(50) NOT NULL, `Event` CHAR(50) NOT NULL, `Argument` CHAR(255) NOT NULL, `Condition` CHAR(255), `Ordering` SHORT PRIMARY KEY `Dialog_`, `Control_`, `Event`, `Argument`, `Condition`)'
            'CREATE TABLE `TextStyle` (`TextStyle` CHAR(72) NOT NULL, `FaceName` CHAR(32) NOT NULL LOCALIZABLE, `Size` SHORT NOT NULL, `Color` LONG, `StyleBits` SHORT PRIMARY KEY `TextStyle`)'
        )
        $columns = @{}
        foreach ($table in $tables) {
            Invoke-Sql $db $table
            $name = [regex]::Match($table, '^CREATE TABLE `(\w+)`').Groups[1].Value
            $columns[$name] = [regex]::Matches($table, '`\w+`(?= (?:CHAR|LONG|SHORT))').Value -join ', '
        }

        $upgradeCode = '{03ADA579-D1B2-46B6-B551-6395E9C9EBB0}'
        $properties = [ordered]@{
            ProductCode = $ProductCode
            ProductName = 'Dispatch Board'
            ProductVersion = $Version
            ProductLanguage = '1033'
            Manufacturer = 'OSLab'
            UpgradeCode = $upgradeCode
            ALLUSERS = '1'
            INSTALLLEVEL = '1'
            SecureCustomProperties = 'PREVIOUSRELEASE'
            DefaultUIFont = 'Body'
        }
        foreach ($property in $properties.GetEnumerator()) {
            Add-Row $db Property @($property.Key, $property.Value)
        }
        Add-Row $db Directory @('TARGETDIR', $null, 'SourceDir')
        Add-Row $db Directory @('ProgramFilesFolder', 'TARGETDIR', '.')
        Add-Row $db Directory @('OSLABDIR', 'ProgramFilesFolder', 'OSLab')
        Add-Row $db Directory @('INSTALLDIR', 'OSLABDIR', 'BOARD|Dispatch Board')
        Add-Row $db Component @('DesktopScripts', '{56D05CC7-8D96-4C01-BB6C-FC3009BC49BA}', 'INSTALLDIR', 0, $null, 'LaunchScript')
        Add-Row $db Feature @('Desktop', $null, 'Dispatch Board', 'Windows desktop shipment workflow', 1, 1, 'INSTALLDIR', 0)
        Add-Row $db FeatureComponents @('Desktop', 'DesktopScripts')
        $boardSize = (Get-Item -LiteralPath (Join-Path $tempPath 'dispatch-board.ps1')).Length
        $launcherSize = (Get-Item -LiteralPath (Join-Path $tempPath 'Start-DispatchBoard.ps1')).Length
        Add-Row $db File @('BoardScript', 'DesktopScripts', 'BOARD.PS1|dispatch-board.ps1', $boardSize, $null, $null, 0, 1)
        Add-Row $db File @('LaunchScript', 'DesktopScripts', 'START.PS1|Start-DispatchBoard.ps1', $launcherSize, $null, $null, 0, 2)
        Add-Row $db Media @(1, 2, $null, '#dispatch.cab', $null, $null)
        Add-Row $db Upgrade @($upgradeCode, '1.0.0', $Version, $null, 256, $null, 'PREVIOUSRELEASE')

        $execution = [ordered]@{
            FindRelatedProducts = 25
            CostInitialize = 800
            FileCost = 900
            CostFinalize = 1000
            InstallValidate = 1400
            InstallInitialize = 1500
            RemoveExistingProducts = 1525
            ProcessComponents = 1600
            UnpublishFeatures = 1800
            RemoveFiles = 3500
            InstallFiles = 4000
            RegisterUser = 6000
            RegisterProduct = 6100
            PublishFeatures = 6300
            PublishProduct = 6400
            InstallFinalize = 6600
        }
        foreach ($action in $execution.GetEnumerator()) {
            $condition = if ($action.Key -eq 'RemoveExistingProducts') { 'PREVIOUSRELEASE' } else { $null }
            Add-Row $db InstallExecuteSequence @($action.Key, $condition, $action.Value)
        }
        Add-Row $db InstallUISequence @('FindRelatedProducts', $null, 25)
        Add-Row $db InstallUISequence @('CostInitialize', $null, 800)
        Add-Row $db InstallUISequence @('FileCost', $null, 900)
        Add-Row $db InstallUISequence @('CostFinalize', $null, 1000)
        Add-Row $db InstallUISequence @('WelcomeDialog', 'NOT Installed', 1200)
        Add-Row $db InstallUISequence @('ExecuteAction', $null, 1300)
        Add-Row $db InstallUISequence @('CompleteDialog', 'NOT Installed', -1)

        Add-Row $db TextStyle @('Body', 'Segoe UI', 10, 3615524, 0)
        Add-Row $db TextStyle @('Heading', 'Segoe UI', 20, 9716496, 1)
        foreach ($complete in @($false, $true)) {
            $dialog = if ($complete) { 'CompleteDialog' } else { 'WelcomeDialog' }
            $heading = if ($complete) { 'Dispatch Board is ready' } else { 'Install Dispatch Board' }
            $detail = if ($complete) {
                'The desktop app was registered with Windows Installer. Shipment data remains in your workspace.'
            } else {
                'Install the desktop release used to import, review, and export shipment records. Existing workspace data stays in place.'
            }
            $next = if ($complete) { 'Finish' } else { 'Install' }
            $cancel = if ($complete) { 'Confirm' } else { 'Cancel' }
            Add-Row $db Dialog @($dialog, 50, 50, 390, 205, 3, 'Dispatch Board Setup', 'Confirm', 'Confirm', $cancel)
            Add-Row $db Control @($dialog, 'Heading', 'Text', 22, 24, 345, 28, 3, $null, ('{\Heading}' + $heading), $null, $null)
            Add-Row $db Control @($dialog, 'Version', 'Text', 24, 64, 334, 16, 3, $null, "WINDOWS DESKTOP RELEASE  $Version", $null, $null)
            Add-Row $db Control @($dialog, 'Details', 'Text', 24, 91, 335, 60, 3, $null, $detail, $null, $null)
            Add-Row $db Control @($dialog, 'Confirm', 'PushButton', 215, 167, 75, 24, 3, $null, $next, $cancel, $null)
            Add-Row $db ControlEvent @($dialog, 'Confirm', 'EndDialog', 'Return', '1', 1)
            if (-not $complete) {
                Add-Row $db Control @($dialog, 'Cancel', 'PushButton', 298, 167, 75, 24, 3, $null, 'Cancel', 'Confirm', $null)
                Add-Row $db ControlEvent @($dialog, 'Cancel', 'EndDialog', 'Exit', '1', 1)
            }
        }

        $record = [DispatchMsi]::MsiCreateRecord(2)
        try {
            Assert-Msi ([DispatchMsi]::MsiRecordSetString($record, 1, 'dispatch.cab')) 'name cabinet stream'
            Assert-Msi ([DispatchMsi]::MsiRecordSetStream($record, 2, (Join-Path $tempPath 'dispatch.cab'))) 'read cabinet file'
            Invoke-Sql $db 'INSERT INTO `_Streams` (`Name`, `Data`) VALUES (?, ?)' $record
        } finally {
            [void][DispatchMsi]::MsiCloseHandle($record)
        }

        Assert-Msi ([DispatchMsi]::MsiGetSummaryInformation($db, $null, 20, [ref]$summary)) 'open package metadata'
        $metadata = @{
            2 = 'Installation Database'
            3 = "Dispatch Board $Version"
            4 = 'OSLab'
            7 = 'Intel;1033'
            9 = $PackageCode
            14 = 200
            15 = 2
            19 = 2
        }
        foreach ($property in $metadata.GetEnumerator()) {
            $type = if ($property.Value -is [int]) { 3 } else { 30 }
            $number = if ($type -eq 3) { $property.Value } else { 0 }
            $value = if ($type -eq 30) { $property.Value } else { $null }
            Assert-Msi ([DispatchMsi]::MsiSummaryInfoSetProperty($summary, $property.Key, $type, $number, [IntPtr]::Zero, $value)) 'set package metadata'
        }
        Assert-Msi ([DispatchMsi]::MsiSummaryInfoPersist($summary)) 'persist package metadata'
        Assert-Msi ([DispatchMsi]::MsiDatabaseCommit($db)) 'commit package'
        [void][DispatchMsi]::MsiCloseHandle($summary)
        $summary = 0
        [void][DispatchMsi]::MsiCloseHandle($db)
        $db = 0
        [IO.File]::Move($msi, $destination)
        Write-Output $destination
    } finally {
        foreach ($handle in @($summary, $db)) {
            if ($handle -ne 0) { [void][DispatchMsi]::MsiCloseHandle($handle) }
        }
        [IO.Directory]::Delete($tempPath, $true)
    }
}

New-Package '1.0.0' '{DFDB98BC-1060-4F4A-85D3-E9713E2212D3}' '{E8402BA7-B239-40F8-83B4-A21004E342E2}' $false
New-Package '2.0.0' '{0F77BB57-F0AA-4EF0-859B-B35604AA72F8}' '{54EE46E5-5B58-4A27-A61B-FD96BC4CC6E6}' $true
New-Package '2.0.1' '{AAC9BC16-D056-4236-8A4A-42961F9365CA}' '{C04C67CE-0A24-4C04-B45D-DB82ED9BA8B3}' $false
