"""Windows-native QA scenarios for event logs, scheduled jobs, scripts, and ODBC."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json


ROOT = r"C:\OSLabWall"
CASES = {
    "21": {
        "title": "Event Viewer",
        "kicker": "RELEASE INCIDENT TRIAGE",
        "scenario": "Inspect a filtered deployment incident and verify that recovery followed the missing-manifest error.",
        "steps": ["Open the incident log", "Inspect the blocked release", "Compare the recovery event"],
        "package": "windows",
    },
    "22": {
        "title": "Task Scheduler",
        "kicker": "ON-DEMAND JOB QA",
        "scenario": "Run the release-manifest task on demand and match its output hashes against the fixture bytes.",
        "steps": ["Locate the isolated task folder", "Run the manifest job", "Verify result and artifact hashes"],
        "package": "windows",
    },
    "23": {
        "title": "Windows PowerShell ISE",
        "kicker": "INSTALLER ACCEPTANCE CRITERIA",
        "scenario": "Run a package-file test, correct a stale expected file count, and compare both test receipts.",
        "steps": ["Review the smoke test", "Reproduce the count mismatch", "Correct the expectation and rerun"],
        "package": "windows",
    },
    "24": {
        "title": "ODBC Data Source Administrator",
        "kicker": "DATABASE CLIENT UPGRADE QA",
        "scenario": "Inspect a migrated 64-bit test data source and verify that its offline driver and routing settings survived.",
        "steps": ["Open the system data sources", "Inspect the release QA data source", "Verify the installed driver and registry values"],
        "package": "windows",
    },
}


def check(name, expected, observed):
    return {"name": name, "expected": expected, "observed": observed, "passed": expected == observed}


async def snap(desktop, name, delay=.55):
    await asyncio.sleep(delay)
    return await desktop.screenshot(name)


async def launch(desktop, name, exe, args=""):
    task_name = "OSLab" + name.replace("-", "")
    await desktop.task(task_name, f"Start-Process -FilePath '{exe}' {('-ArgumentList ' + args) if args else ''}")
    await snap(desktop, name, 1.6)
    await desktop.key("Win", "Up")


async def click(desktop, process, pattern, label, *, kind="", attempts=3):
    for attempt in range(attempts):
        rows = await desktop.inspect(process, pattern)
        frame, _ = await desktop.screenshot(label)
        rows = [row for row in rows if 0 <= row["x"] < frame["width"] and 0 <= row["y"] < frame["height"]]
        if rows:
            target = min(rows, key=lambda row: (bool(kind) and kind not in row.get("kind", ""),
                                               row.get("width", 1) * row.get("height", 1)))
            await desktop.click(frame, target["x"], target["y"])
            return
        if attempt + 1 < attempts:
            await asyncio.sleep(.8)
    raise RuntimeError(f"Visible Windows control was missing: {label}")


async def guest_json(desktop, script):
    result = await desktop.ps(
        "$value=(& {\n" + script + "\n} | Out-String); "
        "[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($value))"
    )
    return json.loads(base64.b64decode(result.stdout.strip(), validate=True))


async def event_viewer(desktop):
    source = "OSLabReleaseIncident"
    archive = ROOT + r"\release-incident.evtx"
    fail = "RC-2147 startup blocked: release.manifest was missing."
    recovered = "RC-2147 recovered: release.manifest verified; startup gate passed."
    await desktop.ps(rf"""
        if (-not [Diagnostics.EventLog]::SourceExists('{source}')) {{
            New-EventLog -LogName Application -Source '{source}'
        }}
        Write-EventLog -LogName Application -Source '{source}' -EventId 271 -EntryType Error -Message '{fail}'
        Write-EventLog -LogName Application -Source '{source}' -EventId 272 -EntryType Information -Message '{recovered}'
        wevtutil.exe epl Application '{archive}' "/q:*[System[Provider[@Name='{source}']]]"
        if ($LASTEXITCODE -ne 0) {{ throw 'Filtered incident log export failed' }}
    """)
    await launch(desktop, "event-viewer-window", r"C:\Windows\System32\eventvwr.exe", f"""'/l:"{archive}"'""")
    process = r"^(mmc|eventvwr)$"
    await snap(desktop, "stage-0", 2.2)
    await desktop.key("Ctrl", "f")
    await snap(desktop, "find-incident", .75)
    await desktop.paste("startup blocked")
    await snap(desktop, "stage-1")
    await desktop.key("Enter")
    await asyncio.sleep(1.2)
    await desktop.key("Escape")
    await snap(desktop, "stage-2")
    try:
        await click(desktop, process, r"(?:^|\D)272(?:\D|$)", "select-recovery-event", kind="DataItem", attempts=2)
    except RuntimeError:
        # Saved logs default to newest first, so Up from event 271 opens event 272.
        await desktop.key("Up")
    await snap(desktop, "stage-3")
    actual = await guest_json(desktop, rf"""
        $events=@(Get-WinEvent -Path '{archive}' | Sort-Object RecordId | ForEach-Object {{
            $message = ([xml]$_.ToXml()).Event.EventData.Data
            [pscustomobject]@{{ id=$_.Id; provider=$_.ProviderName; level=$_.Level; text=[string]@($message)[0]; record=$_.RecordId }}
        }})
        ConvertTo-Json -InputObject $events -Depth 4 -Compress
    """)
    return [
        check("Incident and recovery event IDs", [271, 272], [row["id"] for row in actual]),
        check("Failure and success event levels", [2, 4], [row["level"] for row in actual]),
        check("Both events belong to the release test provider", [source, source], [row["provider"] for row in actual]),
        check("The same release failed and then recovered", [fail, recovered], [row["text"] for row in actual]),
        check("Record IDs establish the recovery order", True, len(actual) == 2 and actual[0]["record"] < actual[1]["record"]),
    ]


JOB_INPUTS = {
    "qa-app.ini": b"[Release]\r\nversion=2.14.7\r\nplatform=win-x64\r\n",
    "qa-migration.sql": b"ALTER TABLE sample ADD COLUMN state TEXT;\r\n",
}


async def task_scheduler(desktop):
    folder = "\\OSLabReleaseQA\\"
    name = "ReleaseManifestGate"
    marker = ROOT + r"\scheduled-manifest.json"
    await desktop.screenshot("scheduler-before-launch")
    await desktop.key("Shift")
    for key, value in JOB_INPUTS.items():
        data = base64.b64encode(value).decode("ascii")
        await desktop.ps(f"[IO.File]::WriteAllBytes('{ROOT}\\{key}', [Convert]::FromBase64String('{data}'))")
    await desktop.ps(rf"""
        $scheduler=New-Object -ComObject Schedule.Service
        $scheduler.Connect()
        $base=$scheduler.GetFolder('\')
        try {{ $scheduler.GetFolder('\OSLabReleaseQA') | Out-Null }} catch {{ $base.CreateFolder('OSLabReleaseQA', $null) | Out-Null }}
        $script=@'
        $ErrorActionPreference='Stop'
        $files=@('qa-app.ini','qa-migration.sql')
        Start-Sleep -Seconds 3
        $manifest=[ordered]@{{ version='2.14.7'; channel='staging'; files=[ordered]@{{}} }}
        foreach ($file in $files) {{
            $manifest.files[$file]=(Get-FileHash -LiteralPath (Join-Path '{ROOT}' $file) -Algorithm SHA256).Hash.ToLowerInvariant()
        }}
        [IO.File]::WriteAllText('{marker}', ($manifest | ConvertTo-Json -Depth 4 -Compress))
'@
        $taskArguments='-NoProfile -NonInteractive -EncodedCommand ' + [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($script))
        $action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $taskArguments
        Register-ScheduledTask -TaskPath '{folder}' -TaskName '{name}' -Description 'QA: hash the staging release payload' -Action $action -User 'SYSTEM' -RunLevel Highest -Force | Out-Null
        if (Test-Path -LiteralPath '{marker}') {{ Remove-Item -LiteralPath '{marker}' }}
    """)
    await desktop.task("OSLabSchedulerWindow", r"Start-Process -FilePath 'C:\Windows\System32\mmc.exe' -ArgumentList 'taskschd.msc'")
    await snap(desktop, "scheduler-window", 3.0)
    await desktop.key("Alt", "Space")
    await desktop.key("x")
    await desktop.key("Escape")
    frame, _ = await snap(desktop, "stage-0", 1)
    # The standard 1280×800 VM view exposes the Korean library label at x=85, y=104.
    # Selecting the label then pressing Right expands the tree without toggling it closed.
    default_layout = (frame["width"], frame["height"]) == (1280, 800)
    if default_layout:
        await desktop.click(frame, 85, 104)
    else:
        await click(desktop, r"^mmc$", r"Task Scheduler Library|작업 스케줄러 라이브러리",
                    "scheduler-library", kind="TreeItem")
    await desktop.key("Right")
    if default_layout:
        frame, _ = await snap(desktop, "scheduler-library")
        await desktop.click(frame, 105, 137)
        frame, _ = await snap(desktop, "scheduler-folder")
        await desktop.click(frame, 251, 115)
    else:
        await click(desktop, r"^mmc$", "^OSLabReleaseQA$", "scheduler-folder", kind="TreeItem")
        await click(desktop, r"^mmc$", name, "scheduler-job", kind="DataItem")
    frame, _ = await snap(desktop, "stage-1")
    if default_layout:
        # The selected task exposes Run as the first link in the right action pane.
        await desktop.click(frame, 1090, 410)
    else:
        await click(desktop, r"^mmc$", r"^Run(?:\s*\(R\))?$|^실행(?:\s*\(R\))?$",
                    "run-scheduler-job", kind="Hyperlink", attempts=1)
    await asyncio.sleep(.65)
    await desktop.key("F5")
    await snap(desktop, "stage-2")
    await desktop.wait(rf"(Test-Path -LiteralPath '{marker}') -and (Get-ScheduledTask -TaskPath '{folder}' -TaskName '{name}').State -eq 'Ready'",
                       seconds=25)
    await desktop.key("F5")
    await snap(desktop, "stage-3")
    payload = await desktop.read_json(marker)
    result = await desktop.ps(f"(Get-ScheduledTaskInfo -TaskPath '{folder}' -TaskName '{name}').LastTaskResult")
    return [
        check("On-demand task finished with exit code zero", 0, int(result.stdout.strip())),
        check("Manifest identifies the release candidate", "2.14.7", payload["version"]),
        check("Release manifest lists exactly two files", sorted(JOB_INPUTS), sorted(payload["files"])),
        check("Every artifact matches the input SHA-256", {key: hashlib.sha256(value).hexdigest() for key, value in JOB_INPUTS.items()},
              payload["files"]),
    ]


ISE_INPUTS = ["setup-x64.msi", "runtime.zip", "release-notes.txt"]
ISE_SOURCE = """function Invoke-ReleaseGate([int]$ExpectedFiles) {
    $inputPath = 'C:\\OSLabWall\\ise-package-list.json'
    $files = [string[]](ConvertFrom-Json (Get-Content -LiteralPath $inputPath -Raw))
    $observed = $files.Count
    $outcome = if ($observed -eq $ExpectedFiles) { 'PASS' } else { 'FAIL' }
    $color = if ($outcome -eq 'PASS') { 'Green' } else { 'Red' }
    Write-Host 'RELEASE QA / WINDOWS x64' -ForegroundColor Cyan
    Write-Host "Expected package files: $ExpectedFiles | Found: $observed"
    Write-Host "[$outcome] Package manifest count gate" -ForegroundColor $color
    $receipt = @{ expected=$ExpectedFiles; observed=$observed; verdict=$outcome; files=$files }
    $path = "C:\\OSLabWall\\ise-result-$ExpectedFiles.json"
    [IO.File]::WriteAllText($path, ($receipt | ConvertTo-Json -Compress))
}

Invoke-ReleaseGate -ExpectedFiles 4"""


ISE_PROCESS = r"^powershell_ise$"


async def run_ise_script(desktop, label):
    frame, _ = await desktop.screenshot(label)
    if (frame["width"], frame["height"]) == (1280, 800):
        await desktop.click(frame, 328, 53)
    else:
        await desktop.key("F5")


async def ise(desktop):
    await desktop.upload("ise-package-list.json", json.dumps(ISE_INPUTS).encode())
    await desktop.upload("release-acceptance.ps1", ISE_SOURCE.replace("\n", "\r\n").encode())
    await desktop.task("OSLabIseWindow", rf"""
        Start-Process -FilePath 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell_ise.exe' -WindowStyle Maximized `
            -ArgumentList '-NoProfile','-File','{ROOT}\release-acceptance.ps1'
    """)
    # Wait for the script tab. Sending shortcuts while the splash is active loses the input.
    await click(desktop, ISE_PROCESS, r"^release-acceptance\.ps1$", "ise-script-ready", kind="TabItem", attempts=8)
    return await capture_ise(desktop)


async def capture_ise(desktop):
    await snap(desktop, "stage-0")
    await run_ise_script(desktop, "ise-run-original")
    failure = ROOT + r"\ise-result-4.json"
    success = ROOT + r"\ise-result-3.json"
    await desktop.wait(f"Test-Path -LiteralPath '{failure}'", seconds=20)
    await snap(desktop, "stage-1")
    frame, _ = await desktop.screenshot("ise-edit-expectation")
    if (frame["width"], frame["height"]) == (1280, 800):
        await desktop.click(frame, 270, 480)
    else:
        await desktop.key("Ctrl", "d")
    await desktop.key("Escape")
    await desktop.paste("$psISE.CurrentFile.Editor.Text = $psISE.CurrentFile.Editor.Text.Replace("
                        "'ExpectedFiles 4','ExpectedFiles 3'); $psISE.CurrentFile.Save($psISE.CurrentFile.Encoding)")
    await desktop.key("Enter")
    await desktop.wait(rf"(Get-Content -LiteralPath '{ROOT}\release-acceptance.ps1' -Tail 1) "
                       "-ceq 'Invoke-ReleaseGate -ExpectedFiles 3'", seconds=20)
    await snap(desktop, "stage-2")
    await run_ise_script(desktop, "ise-run-corrected")
    await desktop.wait(f"Test-Path -LiteralPath '{success}'", seconds=20)
    await snap(desktop, "stage-3")
    before = await desktop.read_json(failure)
    after = await desktop.read_json(success)
    return [
        check("Stale package count blocked the release", [4, 3, "FAIL"],
              [before["expected"], before["observed"], before["verdict"]]),
        check("Corrected expected count passed the release gate", [3, 3, "PASS"],
              [after["expected"], after["observed"], after["verdict"]]),
        check("The manifests contained the same three names", [ISE_INPUTS, ISE_INPUTS], [before["files"], after["files"]]),
    ]


async def odbc(desktop):
    name = "OSLabReleaseDbQA"
    driver = "SQL Server"
    server = "127.0.0.1,39487"
    description = "OSLab release 2.14.7 / offline migration fixture"
    await desktop.ps(rf"""
        if (-not (Get-OdbcDriver -Name '{driver}' -Platform '64-bit')) {{ throw 'SQL Server legacy ODBC driver is unavailable' }}
        $values = @('Server={server}', 'Description={description}', 'Trusted_Connection=Yes')
        $existing = Get-OdbcDsn -DsnType System -Platform '64-bit' | Where-Object Name -eq '{name}'
        if ($existing) {{ Set-OdbcDsn -Name '{name}' -DsnType System -Platform '64-bit' -SetPropertyValue $values }}
        else {{ Add-OdbcDsn -Name '{name}' -DsnType System -Platform '64-bit' -DriverName '{driver}' -SetPropertyValue $values }}
    """)
    await launch(desktop, "odbc-window", r"C:\Windows\System32\odbcad32.exe")
    await snap(desktop, "stage-0")

    async def property_sheet_click(label, x, y):
        # The classic property sheet does not reliably expose its tab names
        # through UI Automation. Check its visible frame before sending input.
        frame, image = await snap(desktop, label)
        left, top = frame["width"] // 2 - 344, frame["height"] // 2 - 242
        anchors = ((6, 35), (670, 35), (6, 290), (670, 290))
        if left < 0 or top < 0 or not all(
            (lambda rgb: min(rgb) >= 210 and max(rgb) - min(rgb) <= 6)(image.getpixel((left + dx, top + dy))[:3])
            for dx, dy in anchors
        ):
            raise RuntimeError("The ODBC property sheet is not in the expected desktop position")
        await desktop.click(frame, left + x, top + y)

    await property_sheet_click("system-dsn-tab", 124, 51)
    dsns = await guest_json(desktop, """
        $names = @(Get-OdbcDsn -DsnType System -Platform '64-bit' | Select-Object -ExpandProperty Name | Sort-Object)
        @{names=$names} | ConvertTo-Json -Compress
    """)
    row = dsns["names"].index(name)
    if row >= 10:
        raise RuntimeError("The QA DSN is below the visible entries")
    await property_sheet_click("select-release-data-source", 63, 126 + 17 * row)
    await snap(desktop, "stage-1")
    await property_sheet_click("configure-data-source", 581, 196)
    await snap(desktop, "stage-2", 1)
    await desktop.key("Escape")
    await property_sheet_click("odbc-drivers-tab", 259, 51)
    await snap(desktop, "stage-3")
    actual = await guest_json(desktop, rf"""
        $dsn = Get-OdbcDsn -Name '{name}' -DsnType System -Platform '64-bit'
        $driver = Get-OdbcDriver -Name '{driver}' -Platform '64-bit'
        $record = Get-ItemProperty 'HKLM:\SOFTWARE\ODBC\ODBC.INI\{name}'
        @{{ driver=$dsn.DriverName; platform=$driver.Platform; server=$record.Server;
           description=$record.Description; integrated=$record.Trusted_Connection;
           registered=$driver.Name }} | ConvertTo-Json -Compress
    """)
    return [
        check("System DSN uses the intended installed driver", [driver, driver], [actual["driver"], actual["registered"]]),
        check("ODBC architecture", "64-bit", actual["platform"]),
        check("Data source maps to the isolated fixture address", server, actual["server"]),
        check("Release description was preserved", description, actual["description"]),
        check("The DSN requests integrated authentication", "yes", str(actual["integrated"]).lower()),
    ]


async def execute(case_id, desktop):
    cases = {"21": event_viewer, "22": task_scheduler, "23": ise, "24": odbc}
    return await cases[str(case_id)](desktop)
