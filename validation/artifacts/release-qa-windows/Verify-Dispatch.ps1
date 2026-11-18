[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('fresh-import', 'export', 'upgrade', 'regression', 'fixed')]
    [string]$Mode,

    [Parameter(Mandatory = $true)]
    [string]$DataDir,

    [string]$Baseline,
    [string]$ReportPath,
    [string]$ResultPath
)

$ErrorActionPreference = 'Stop'
$checks = [System.Collections.Generic.List[object]]::new()
$expectedIds = @('SHP-1041', 'SHP-1042', 'SHP-1043', 'SHP-1044', 'SHP-1045', 'SHP-1046', 'SHP-1047')
$rejectedId = 'SHP-1048'
$heldId = $expectedIds[0]
$columns = @('Id', 'Customer', 'Destination', 'Units', 'Priority', 'Status')

function Add-Check {
    param([string]$Id, [string]$Name, [bool]$Passed, [string]$Expected, [string]$Observed)

    $checks.Add([ordered]@{
        id = $Id
        name = $Name
        passed = $Passed
        expected = $Expected
        observed = $Observed
    })
}

function Save-Text {
    param([string]$Path, [string]$Value)

    $absolute = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($absolute)) | Out-Null
    [IO.File]::WriteAllText($absolute, $Value, [Text.UTF8Encoding]::new($false))
}

function Compare-DispatchRows {
    param([object[]]$ExpectedRows, [object[]]$ObservedRows)

    if ($ExpectedRows.Count -ne $ObservedRows.Count) {
        return $false
    }
    for ($index = 0; $index -lt $ExpectedRows.Count; $index++) {
        foreach ($column in $columns) {
            if ([string]$ExpectedRows[$index].$column -cne [string]$ObservedRows[$index].$column) {
                return $false
            }
        }
    }
    return $true
}

function Get-Sha256 {
    param([string]$Path)

    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try {
        return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $stream.Dispose()
        $algorithm.Dispose()
    }
}

$data = (Resolve-Path -LiteralPath $DataDir).ProviderPath
$statePath = Join-Path $data 'dispatch-state.json'
$inputPath = Join-Path $data 'input.csv'
$exportPath = Join-Path $data 'dispatch-export.csv'
$baselinePath = $null
if ($Baseline -and (Test-Path -LiteralPath $Baseline -PathType Leaf)) {
    $baselinePath = (Resolve-Path -LiteralPath $Baseline).ProviderPath
}

$fixture = @(Import-Csv -LiteralPath (Join-Path $PSScriptRoot 'input.csv') -Encoding UTF8)
$approvedFixture = (@($fixture.Id) -join ',') -ceq (@($expectedIds + $rejectedId) -join ',')
if (-not $approvedFixture) {
    throw 'Verifier input fixture has an unexpected shipment manifest.'
}
$expectedRows = @(
    foreach ($row in $fixture) {
        if ($row.Id -eq $rejectedId) { continue }
        $expectedStatus = if ($Mode -ne 'fresh-import' -and $row.Id -eq $heldId) { 'On Hold' } else { 'Ready' }
        [pscustomobject][ordered]@{
            Id = $row.Id
            Customer = $row.Customer
            Destination = $row.Destination
            Units = $row.Units
            Priority = $row.Priority
            Status = $expectedStatus
        }
    }
)

$state = $null
$stateStatus = 'Missing'
if (Test-Path -LiteralPath $statePath -PathType Leaf) {
    try {
        $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $stateStatus = if ($state) { 'Readable' } else { 'Empty' }
    }
    catch {
        $stateStatus = 'Invalid JSON'
    }
}
$records = @($state.Records | Where-Object { $null -ne $_ })
$rejected = @($state.Rejected | Where-Object { $null -ne $_ })
$events = @($state.Events | Where-Object { $null -ne $_ })
$version = if ($state.Version) { [string]$state.Version } else { 'Unknown' }
$registeredLaunches = @($events | Where-Object Action -eq 'Launch')
$launchVersions = @($registeredLaunches | ForEach-Object { [string]$_.Version })
$lastLaunch = if ($launchVersions.Count) { $launchVersions[-1] } else { 'Missing' }
$versionPattern = switch ($Mode) {
    'upgrade' { '^2\.0(?:\.0)?$' }
    'regression' { '^2\.0(?:\.0)?$' }
    'fixed' { '^2\.0\.1$' }
    default { '^1\.0(?:\.0)?$' }
}

Add-Check 'state.readable' 'Application wrote its guest state' ($stateStatus -eq 'Readable') 'Readable JSON' $stateStatus
$matchingFixtureBytes = (Test-Path -LiteralPath $inputPath -PathType Leaf) -and (
    (Get-Sha256 $inputPath) -ceq (Get-Sha256 (Join-Path $PSScriptRoot 'input.csv'))
)
$observedFixture = if ($matchingFixtureBytes) { 'Matching SHA-256' } else { 'Missing or different bytes' }
Add-Check 'input.fixture' 'Guest import used the approved QA fixture' $matchingFixtureBytes 'Matching SHA-256' $observedFixture
$versionMatches = ($version -match $versionPattern) -and ($lastLaunch -ceq $version)
$expectedVersion = switch ($Mode) {
    'upgrade' { 'Version 2.0.0 launch' }
    'regression' { 'Version 2.0.0 launch' }
    'fixed' { 'Version 2.0.1 launch' }
    default { 'Version 1.0.0 launch' }
}
Add-Check 'app.version' 'Installed build launched' $versionMatches $expectedVersion "State $version / Launch $lastLaunch"
$validShipmentsMatch = Compare-DispatchRows $expectedRows $records
$recordsObserved = if ($validShipmentsMatch) { "$($records.Count) matching rows" } else { "$($records.Count) rows / different values or order" }
Add-Check 'import.records' 'Accepted shipments match the fixture' $validShipmentsMatch '7 exact rows' $recordsObserved
$rejectHasUnitReason = $rejected.Count -eq 1 -and $rejected[0].Id -ceq $rejectedId -and [string]$rejected[0].Reason -match 'units|positive|number|numeric|integer'
$rejectObserved = if ($rejected.Count) { "$($rejected[0].Id) / $($rejected[0].Reason)" } else { 'No rejected shipment' }
Add-Check 'import.reject' 'Malformed quantity was rejected' $rejectHasUnitReason "$rejectedId / invalid units" $rejectObserved
$importEvents = @($events | Where-Object Action -eq 'Import')
Add-Check 'audit.import' 'Import appears in the app audit trail' ($importEvents.Count -gt 0) 'At least one import event' "$($importEvents.Count) events"

$exportRows = @()
if ($Mode -ne 'fresh-import') {
    $held = @($records | Where-Object Id -ceq $heldId)
    $heldStatus = if ($held.Count -eq 1) { [string]$held[0].Status } else { 'Missing or duplicate' }
    Add-Check 'state.hold' 'Operator hold was saved' ($heldStatus -ceq 'On Hold') "$heldId / On Hold" $heldStatus
    $holdEvents = @($events | Where-Object Action -eq 'StatusChanged')
    Add-Check 'audit.hold' 'Hold appears in the app audit trail' ($holdEvents.Count -gt 0) 'At least one status change' "$($holdEvents.Count) events"

    $exportHeader = 'Missing'
    if (Test-Path -LiteralPath $exportPath -PathType Leaf) {
        $exportHeader = ([string](Get-Content -LiteralPath $exportPath -Encoding UTF8 -TotalCount 1)).Replace('"', '')
        $exportRows = @(Import-Csv -LiteralPath $exportPath -Encoding UTF8 -WarningAction SilentlyContinue)
    }
    $approvedHeader = $columns -join ','
    Add-Check 'export.schema' 'Export preserves the shipment CSV schema' ($exportHeader -ceq $approvedHeader) $approvedHeader $exportHeader
    $countMatches = $exportRows.Count -eq $expectedRows.Count
    $contentMatches = Compare-DispatchRows $expectedRows $exportRows
    $matchedPrefix = $exportRows.Count -eq ($expectedRows.Count - 1) -and (
        Compare-DispatchRows @($expectedRows[0..($expectedRows.Count - 2)]) $exportRows
    )
    $observedContent = if ($contentMatches) {
        'Every shipment and status matches'
    }
    elseif ($matchedPrefix) {
        "Missing $($expectedIds[-1]), all earlier rows match"
    }
    else {
        'Exported values or order do not match'
    }
    Add-Check 'export.count' 'Export contains every accepted shipment' $countMatches "$($expectedRows.Count) records" "$($exportRows.Count) records"
    Add-Check 'export.content' 'Exact data and status survive export' $contentMatches '7 rows in order, including the held shipment' $observedContent
    $excluded = @($exportRows | Where-Object Id -ceq $rejectedId).Count -eq 0
    Add-Check 'export.exclude' 'Rejected shipment stayed out of the export' $excluded "No $rejectedId" $(if ($excluded) { "No $rejectedId" } else { "$rejectedId found" })
    $exportEvents = @($events | Where-Object Action -eq 'Export')
    $exportAuditMatches = $exportEvents.Count -gt 0 -and $state.LastExport.Expected -eq $expectedRows.Count -and
        $state.LastExport.Written -eq $exportRows.Count -and
        [IO.Path]::GetFileName([string]$state.LastExport.File) -ceq 'dispatch-export.csv'
    $auditObservation = if ($state.LastExport) {
        "$($state.LastExport.Written) of $($state.LastExport.Expected) recorded"
    }
    else { 'Missing export state' }
    Add-Check 'audit.export' 'App export audit matches the file' $exportAuditMatches 'Recorded counts and exported file agree' $auditObservation
}

if ($Mode -eq 'upgrade') {
    $oldLaunchSeen = $false
    $launchOrder = $false
    foreach ($launchVersion in $launchVersions) {
        if ($launchVersion -match '^1\.0(?:\.0)?$') { $oldLaunchSeen = $true }
        if ($oldLaunchSeen -and $launchVersion -match '^2\.0(?:\.0)?$') { $launchOrder = $true }
    }
    Add-Check 'upgrade.history' 'Upgrade retained the previous build audit' $launchOrder '1.0.0 then 2.0.0' ($launchVersions -join ' -> ')
    if ($Baseline) {
        $sameBytes = $false
        $baselineObservation = 'Baseline or upgraded export missing'
        if ($baselinePath -and (Test-Path -LiteralPath $exportPath -PathType Leaf)) {
            if ($baselinePath -eq (Resolve-Path -LiteralPath $exportPath).ProviderPath) {
                $baselineObservation = 'Baseline points to the current export'
            }
            else {
                $originalHash = Get-Sha256 $baselinePath
                $upgradedHash = Get-Sha256 $exportPath
                $sameBytes = $originalHash -ceq $upgradedHash
                $baselineObservation = if ($sameBytes) { "SHA-256 $($upgradedHash.Substring(0,12))... matches" } else { 'Different SHA-256' }
            }
        }
        Add-Check 'upgrade.baseline' 'Pre-upgrade and post-upgrade exports match' $sameBytes 'Byte-identical CSV' $baselineObservation
    }
}

$failed = @($checks | Where-Object { -not $_.passed })
$releaseVerdict = if ($failed.Count) { 'FAIL' } else { 'PASS' }
$expectedVerdict = 'PASS'
$executionPassed = $releaseVerdict -eq 'PASS'
if ($Mode -eq 'regression') {
    $expectedVerdict = 'FAIL'
    $executionPassed = ($failed.id -join ',') -ceq 'export.count,export.content' -and $matchedPrefix
}
$outcome = [ordered]@{
    mode = $Mode
    version = $version
    releaseVerdict = $releaseVerdict
    expectedVerdict = $expectedVerdict
    executionPassed = [bool]$executionPassed
    accepted = $records.Count
    rejected = $rejected.Count
    exported = $exportRows.Count
    checks = $checks.ToArray()
}
$json = ConvertTo-Json -InputObject $outcome -Depth 6 -Compress
if ($ResultPath) {
    Save-Text $ResultPath $json
}

if ($ReportPath) {
    $title = switch ($Mode) {
        'fresh-import' { 'Validate a mixed-quality import' }
        'export' { 'Verify the operator export' }
        'upgrade' { 'Upgrade with shipment state intact' }
        'regression' {
            if ($executionPassed) { 'Last shipment missing from export' } else { 'Verify the export regression' }
        }
        'fixed' {
            if ($executionPassed) { 'Patched build restores the export' } else { 'Verify the patched export' }
        }
    }
    $summary = if ($executionPassed -and $Mode -eq 'regression') {
        "Expected failure reproduced. Shipment $($expectedIds[-1]) was accepted but missing from the exported CSV."
    }
    elseif ($executionPassed) {
        'The Windows guest output meets the release gate assertions.'
    }
    else {
        'The Windows guest output diverges from the expected scenario result.'
    }
    $label = if ($Mode -eq 'regression') { 'Intentional regression build' } else { 'Release gate' }
    $reportRows = foreach ($check in ($failed + @($checks | Where-Object { $_.passed }))) {
        $status = if ($check.passed) { 'PASS' } else { 'FAIL' }
        $stateClass = if ($check.passed) { 'passed' } else { 'failed' }
        $cells = @($check.name, $check.expected, $check.observed) | ForEach-Object { '<td>' + [Net.WebUtility]::HtmlEncode([string]$_) + '</td>' }
        "<tr><td class=`"status $stateClass`">$status</td>$($cells -join '')</tr>"
    }
    $template = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'release-report.html') -Raw -Encoding UTF8
    $values = @{
        VERSION = $version
        VERDICT = $releaseVerdict
        LABEL = $label
        TITLE = $title
        SUMMARY = $summary
        ACCEPTED = $records.Count
        REJECTED = $rejected.Count
        EXPORTED = if ($Mode -eq 'fresh-import') { 'Pending' } else { $exportRows.Count }
        ASSERTIONS = "$($checks.Count - $failed.Count) / $($checks.Count)"
    }
    foreach ($token in $values.Keys) {
        $template = $template.Replace("@@${token}@@", [Net.WebUtility]::HtmlEncode([string]$values[$token]))
    }
    Save-Text $ReportPath ($template.Replace('@@ROWS@@', ($reportRows -join "`n")))
}

Write-Output $json
if ($executionPassed) { exit 0 }
exit 1
