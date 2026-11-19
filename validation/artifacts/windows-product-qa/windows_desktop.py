"""Release QA using four Windows desktop programs already in the guest."""

from __future__ import annotations

import asyncio
import statistics

from PIL import ImageChops

import matrix_native

ROOT = r"C:\OSLabWall"
PERFMON = r"^(perfmon|mmc)$"
CASES = {
    case_id: {**matrix_native.NATIVE[case_id], "package": "windows"}
    for case_id in ("29", "30", "31")
}
CASES["32"] = {
    "title": "Performance Monitor",
    "kicker": "PERFORMANCE REGRESSION QA",
    "scenario": "Capture a bounded CPU regression, freeze the graph for inspection, and verify that the guest recovers.",
    "steps": ["Record the idle baseline", "Run the CPU stress fixture", "Freeze the observed spike", "Confirm CPU recovery"],
    "package": "windows",
}


CPU_SAMPLES = r"""
$samples = @(1..5 | ForEach-Object {
    $value = Get-CimInstance -ClassName Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'"
    if ($null -eq $value) { throw 'Windows processor counter is unavailable' }
    [int]$value.PercentProcessorTime
    Start-Sleep -Milliseconds 550
})
ConvertTo-Json -InputObject $samples -Compress
"""

PULSE_TASK = rf"""
$ErrorActionPreference='Stop'
$workspace = '{ROOT}'
$work = @'
$clock = [Diagnostics.Stopwatch]::StartNew()
$value = 1.0
while ($clock.Elapsed.TotalSeconds -lt 19) {{
    for ($n = 1; $n -le 1000; $n++) {{ $value = [Math]::Sqrt($value + $n) }}
}}
'@
$arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand ' +
    [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($work))
$count = [Math]::Min([Math]::Max(1, [Environment]::ProcessorCount), 4)
$workers = @()
try {{
    for ($i = 0; $i -lt $count; $i++) {{
        $workers += Start-Process -FilePath powershell.exe -ArgumentList $arguments -WindowStyle Hidden -PassThru
    }}
    [IO.File]::WriteAllText((Join-Path $workspace 'qa-pulse-started.json'),
        (ConvertTo-Json -Compress -InputObject @{{workers=$workers.Count}}))
    foreach ($worker in $workers) {{
        if (!$worker.WaitForExit(25000)) {{ throw 'QA pulse exceeded its bounded runtime' }}
        if ($worker.ExitCode -ne 0) {{ throw 'QA pulse worker failed' }}
    }}
    [IO.File]::WriteAllText((Join-Path $workspace 'qa-pulse-finished.json'),
        (ConvertTo-Json -Compress -InputObject @{{workers=$workers.Count; completed=$true}}))
}} finally {{
    foreach ($worker in $workers) {{
        if (!$worker.HasExited) {{ $worker.Kill(); $worker.WaitForExit() }}
        $worker.Dispose()
    }}
}}
"""


def graph_crop(image):
    """Keep the plotted samples and exclude the labels, toolbars, and taskbar."""
    width, height = image.size
    return image.crop((round(width * .045), round(height * .121), round(width * .958), round(height * .768)))


def chart_same(first, second):
    return first.size == second.size and ImageChops.difference(graph_crop(first), graph_crop(second)).getbbox() is None


def budget_check(name, limit, observed, passed):
    return {"name": name, "expected": limit, "observed": observed, "passed": passed}


async def scan_cpu(desktop):
    samples = await matrix_native.ps_json(desktop, CPU_SAMPLES)
    if len(samples) != 5 or any(type(sample) is not int or not 0 <= sample <= 100 for sample in samples):
        raise RuntimeError("Invalid Windows processor counter samples")
    return round(statistics.mean(samples), 1)


async def perfmon_control(desktop, pattern, label, attempts=15):
    """Find a visible Performance Monitor control through UI Automation, waiting while the dialog loads."""
    for _ in range(attempts):
        controls = await desktop.inspect(PERFMON, pattern)
        if controls:
            return min(controls, key=lambda row: row["width"] * row["height"])
        await asyncio.sleep(1)
    visible = await desktop.inspect(PERFMON, ".")
    names = sorted({f"{row['name']} ({row['kind'].removeprefix('ControlType.')})" for row in visible if row["name"]})
    raise RuntimeError(f"Performance Monitor did not show {label}. Visible controls: {'; '.join(names)[:900]}")


async def add_processor_time(desktop):
    """Add \\Processor(_Total)\\% Processor Time in the Add Counters dialog using MCP clicks."""
    frame, _ = await desktop.screenshot("perfmon-focus")
    await desktop.click(frame, 103, 56)
    # The dialog shows the object list while it is still loading the counter catalog.
    await perfmon_control(desktop, r"^(사용 가능한 카운터|Available counters)$", "the loaded counter list", attempts=20)
    add = await perfmon_control(desktop, r"^(추가|Add).*>>$", "the Add button")
    # UI Automation shows this dialog only as window panes, without the rows of its counter
    # list. The list opens on the default Processor object at the top, so its rows are placed
    # relative to the Add button. Expanded, Processor lists % C1, % C2, % C3, % DPC, % Idle,
    # % Interrupt and % Privileged Time, then % Processor Time as the eighth counter.
    frame, _ = await desktop.screenshot("perfmon-add-counters")
    await desktop.click(frame, add["x"] + 9, add["y"] - 396)
    await asyncio.sleep(.8)
    frame, _ = await desktop.screenshot("perfmon-processor-counters")
    await desktop.click(frame, add["x"] - 233, add["y"] - 228)
    await asyncio.sleep(.8)
    frame, _ = await desktop.screenshot("perfmon-processor-time")
    await desktop.click(frame, add["x"] - 295, add["y"] - 172)
    await asyncio.sleep(.5)
    frame, _ = await desktop.screenshot("perfmon-total-instance")
    await desktop.click(frame, add["x"], add["y"])
    await asyncio.sleep(.8)
    ok = await perfmon_control(desktop, r"^(확인|OK)$", "the OK button")
    frame, _ = await desktop.screenshot("perfmon-counter-added")
    await desktop.click(frame, ok["x"], ok["y"])


async def performance_monitor(desktop):
    await desktop.screenshot("perfmon-before-launch")
    await desktop.key("Shift")
    await desktop.ps(rf"""
        foreach ($name in @('qa-pulse-started.json','qa-pulse-finished.json')) {{
            $file=Join-Path '{ROOT}' $name
            if (Test-Path -LiteralPath $file) {{ Remove-Item -LiteralPath $file }}
        }}
    """)
    await desktop.task("OSLabPerfMonitor", "Start-Process -FilePath perfmon.exe -ArgumentList '/sys'")
    await desktop.wait("@(Get-Process -Name 'perfmon' -ErrorAction SilentlyContinue).Count -gt 0", seconds=20)
    await asyncio.sleep(1.8)
    await desktop.screenshot("perfmon-launch")
    await desktop.key("Escape")
    await desktop.key("Alt", "Space")
    await desktop.key("x")
    await desktop.key("Escape")
    await asyncio.sleep(.7)
    monitors = await desktop.inspect(PERFMON, r"Performance Monitor|System Monitor|성능 모니터|시스템 모니터")
    if not monitors:
        raise RuntimeError("Performance Monitor window was not visible")
    frame, _ = await desktop.screenshot("perfmon-window")
    if (frame["width"], frame["height"]) != (1280, 800):
        raise RuntimeError("Performance Monitor capture requires the 1280×800 guest desktop")
    await add_processor_time(desktop)
    await asyncio.sleep(1.6)

    baseline = await scan_cpu(desktop)
    if baseline > 50:
        await asyncio.sleep(3)
        baseline = await scan_cpu(desktop)
    _, idle_chart = await desktop.screenshot("stage-0")

    await desktop.task("OSLabPerfPulse", PULSE_TASK)
    await desktop.wait(rf"Test-Path -LiteralPath '{ROOT}\qa-pulse-started.json'", seconds=12)
    await asyncio.sleep(2)
    loaded = await scan_cpu(desktop)
    frame, spike_chart = await desktop.screenshot("stage-1")

    await desktop.click(frame, 279, 56)
    await asyncio.sleep(.35)
    _, frozen_chart = await desktop.screenshot("stage-2")
    await asyncio.sleep(1.45)
    frame, freeze_sample = await desktop.screenshot("perfmon-frozen-proof")
    frozen = chart_same(frozen_chart, freeze_sample)
    await desktop.click(frame, 279, 56)
    await desktop.wait(rf"Test-Path -LiteralPath '{ROOT}\qa-pulse-finished.json'", seconds=26)
    report = await desktop.read_json(rf"{ROOT}\qa-pulse-finished.json")
    await asyncio.sleep(2)
    recovered = await scan_cpu(desktop)
    _, recovered_chart = await desktop.screenshot("stage-3")

    check = matrix_native.check
    return [
        check("The PerfMon graph visibly changed under load", True, not chart_same(idle_chart, spike_chart)),
        budget_check("Guest CPU rose during the regression fixture", "at least +20 percentage points",
                     {"idle_percent": baseline, "load_percent": loaded}, loaded - baseline >= 20),
        check("The PerfMon freeze held the chart steady", True, frozen),
        check("All bounded CPU workers exited normally", True, report.get("completed") is True and 1 <= report.get("workers", 0) <= 4),
        budget_check("Guest CPU returned toward baseline", "at least -20 percentage points from load",
                     {"load_percent": loaded, "recovery_percent": recovered}, loaded - recovered >= 20),
        check("The unpaused PerfMon chart resumed updates", True, not chart_same(frozen_chart, recovered_chart)),
    ]


async def execute(case_id, desktop):
    selected = str(case_id).zfill(2)
    if selected == "32":
        return await performance_monitor(desktop)
    return (await matrix_native.execute(selected, desktop))["checks"]
