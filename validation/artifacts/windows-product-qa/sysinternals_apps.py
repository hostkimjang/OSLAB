"""Sysinternals scenarios with isolated workloads and machine-checked evidence."""

from __future__ import annotations

import asyncio
import base64
import json


GUEST = r"C:\OSLabWall"
MIB = 1024 * 1024
CASES = {
    "25": {
        "title": "Process Monitor",
        "kicker": "STARTUP DIAGNOSTICS",
        "scenario": "Trace a staged app that cannot find its settings, then verify the recovered file access.",
        "steps": ["Start a guest file trace", "Reproduce the failed startup", "Verify the successful rerun"],
        "package": "procmon",
    },
    "26": {
        "title": "Process Explorer",
        "kicker": "FILE LOCK DIAGNOSTICS",
        "scenario": "Identify the QA process holding a release manifest and verify that it releases the lock.",
        "steps": ["Start the dedicated exporter", "Find its manifest handle", "Verify the released file"],
        "package": "procexp",
    },
    "27": {
        "title": "TCPView",
        "kicker": "LOOPBACK SERVICE QA",
        "scenario": "Compare a QA service's listener and established loopback session against Windows socket state.",
        "steps": ["Start the local fixture listener", "Connect the QA client", "Save and compare the TCP snapshot"],
        "package": "tcpview",
    },
    "28": {
        "title": "VMMap",
        "kicker": "MEMORY BUDGET QA",
        "scenario": "Capture a native memory map surrounding a known 32 MiB QA allocation.",
        "steps": ["Attach to the synthetic loader", "Exercise the 32 MiB buffer", "Save and verify the memory snapshot"],
        "package": "vmmap",
    },
}


def path(name):
    return GUEST + "\\" + name


def check(name, expected, observed):
    return {"name": name, "expected": expected, "observed": observed, "passed": expected == observed}


async def capture(desktop, name, delay=.5):
    await asyncio.sleep(delay)
    return await desktop.screenshot(name)


async def powershell_json(desktop, script):
    command = (
        "$json=(& {\n" + script + "\n} | Out-String); "
        "[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))"
    )
    result = await desktop.ps(command)
    return json.loads(base64.b64decode(result.stdout.strip(), validate=True))


async def click_control(desktop, frame, controls, preferred=None):
    candidates = [control for control in controls
                  if 0 <= control["x"] < frame["width"] and 0 <= control["y"] < frame["height"]]
    if not candidates:
        return False
    control = min(candidates, key=lambda c: (bool(preferred) and c.get("kind") != preferred,
                                             c.get("width", 10) * c.get("height", 10)))
    await desktop.click(frame, control["x"], control["y"])
    return True


async def native_save(desktop, filename, process_pattern, dialog_shot=None):
    """Save from the application with MCP and verify that the dialog wrote a file."""
    await desktop.key("Ctrl", "s")
    await asyncio.sleep(.6)
    controls = await desktop.inspect(process_pattern, r"^Save as$|^Save As$|다른 이름으로 저장|^Save$")
    if not controls:
        await desktop.key("Alt", "f")
        await asyncio.sleep(.4)
        controls = await desktop.inspect(process_pattern, r"^Save(?: As)?(?:\.\.\.)?$|저장")
        frame, _ = await desktop.screenshot("file-menu")
        await click_control(desktop, frame, controls, "ControlType.MenuItem")
    if dialog_shot:
        await capture(desktop, dialog_shot)
    await desktop.key("Alt", "n")
    await desktop.paste(path(filename))
    await desktop.key("Enter")
    await desktop.wait(rf"(Test-Path -LiteralPath '{path(filename)}') -and (Get-Item -LiteralPath '{path(filename)}').Length -gt 32",
                       seconds=35)


async def helper(desktop, name, source):
    await desktop.upload(f"{name}.cs", source.encode("utf-8"))
    await desktop.ps(rf"""
        $compiler = Join-Path $env:windir 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
        & $compiler /nologo /target:winexe /optimize+ /out:{path(name + '.exe')} '{path(name + '.cs')}'
        if ($LASTEXITCODE -ne 0) {{ throw 'Failed to compile the synthetic QA helper' }}
    """)


async def launcher(desktop, name, args=""):
    argument = f" -ArgumentList '{args}'" if args else ""
    await desktop.task("OSLabProductFixture", f"Start-Process -FilePath '{path(name + '.exe')}'{argument}")


async def run_config_loader(desktop, phase, expected):
    marker = path(phase + ".txt")
    return (await desktop.ps(rf"""
        $loader = Start-Process -FilePath '{path('QAConfigLoader.exe')}' -ArgumentList @('{phase}') -Wait -PassThru
        if ($loader.ExitCode -ne 0) {{ throw "The synthetic loader exited with code $($loader.ExitCode)" }}
        $outcome = [IO.File]::ReadAllText('{marker}')
        if ($outcome -cne '{expected}') {{ throw "Unexpected synthetic loader outcome: $outcome" }}
        $outcome
    """)).stdout.strip()


async def find_procmon(desktop):
    await desktop.key("Ctrl", "f")
    await asyncio.sleep(.45)
    await desktop.paste("qa-fixture.json")
    await desktop.key("Enter")
    await asyncio.sleep(.6)
    await desktop.key("Escape")


async def procmon(desktop):
    await helper(desktop, "QAConfigLoader", r"""
        using System;
        using System.IO;
        class QAConfigLoader {
            static void Main(string[] args) {
                string root = @"C:\OSLabWall";
                string outcome;
                try {
                    string fixture = File.ReadAllText(Path.Combine(root, "qa-fixture.json"));
                    outcome = fixture.Contains("fixture-ready") ? "fixture-ready" : "unexpected-fixture";
                } catch (FileNotFoundException) { outcome = "missing-settings"; }
                File.WriteAllText(Path.Combine(root, args[0] + ".txt"), outcome);
            }
        }
    """)
    pml = path("startup.pml")
    csv = path("startup.csv")
    await desktop.launch("procmon", ["/AcceptEula", "/Quiet", "/BackingFile", pml])
    await desktop.wait(rf"Test-Path -LiteralPath '{pml}'", seconds=35)
    await capture(desktop, "startup-launch", 1.5)
    await desktop.key("Win", "Up")
    await capture(desktop, "stage-0")
    await run_config_loader(desktop, "before", "missing-settings")
    await find_procmon(desktop)
    await capture(desktop, "stage-1")
    await desktop.upload("qa-fixture.json", b'{"launch":"fixture-ready"}\n')
    await run_config_loader(desktop, "after", "fixture-ready")
    await desktop.key("Ctrl", "e")
    await desktop.key("End")
    await find_procmon(desktop)
    await capture(desktop, "stage-2")
    await desktop.key("F3")
    await desktop.key("Enter")
    await capture(desktop, "stage-3")
    await desktop.key("Escape")
    await desktop.key("Alt", "F4")
    await asyncio.sleep(1.2)
    await desktop.launch("procmon", ["/AcceptEula", "/Quiet", "/OpenLog", pml, "/SaveAs", csv])
    await desktop.wait(rf"(Test-Path -LiteralPath '{csv}') -and ((Get-Item '{csv}').Length -gt 32)", seconds=60)
    observed = await powershell_json(desktop, rf"""
        $rows = @(Import-Csv -LiteralPath '{csv}' |
            Where-Object {{ $_.'Process Name' -ieq 'QAConfigLoader.exe' -and $_.Path -eq '{path('qa-fixture.json')}' }})
        @{{before=[IO.File]::ReadAllText('{path('before.txt')}'); after=[IO.File]::ReadAllText('{path('after.txt')}');
           missing=[bool]($rows | Where-Object {{ $_.Operation -eq 'CreateFile' -and $_.Result -eq 'NAME NOT FOUND' }});
           success=[bool]($rows | Where-Object {{ $_.Operation -eq 'CreateFile' -and $_.Result -eq 'SUCCESS' }}) }} |
           ConvertTo-Json -Compress
    """)
    return [
        check("Synthetic loader reproduced the missing settings", "missing-settings", observed["before"]),
        check("Procmon captured CreateFile → NAME NOT FOUND for that loader", True, observed["missing"]),
        check("Procmon captured CreateFile → SUCCESS after restoring the fixture", True, observed["success"]),
        check("The same loader parsed the restored fixture", "fixture-ready", observed["after"]),
    ]


async def explorer_search(desktop, text, screenshot=None):
    proc = r"(?i)^(procexp|procexp64)$"
    await desktop.key("Ctrl", "Shift", "f")
    await asyncio.sleep(.6)
    await desktop.key("Ctrl", "a")
    await desktop.paste(text)
    if screenshot:
        await capture(desktop, screenshot, .25)
    controls = await desktop.inspect(proc, r"^Search$")
    frame, _ = await desktop.screenshot("handle-search-dialog")
    if not await click_control(desktop, frame, controls, "ControlType.Button"):
        await desktop.key("Enter")
    await asyncio.sleep(1.25)


async def save_handle_search(desktop, filename):
    controls = await desktop.inspect(r"(?i)^(procexp|procexp64)$", r"^Save(?:\.\.\.|…)$")
    frame, _ = await desktop.screenshot("handle-export-button")
    if not await click_control(desktop, frame, controls, "ControlType.Button"):
        raise RuntimeError("Process Explorer Search did not expose its Save button")
    await capture(desktop, "handle-export-dialog")
    await desktop.key("Alt", "n")
    await desktop.paste(path(filename))
    await desktop.key("Enter")
    await desktop.wait(rf"(Test-Path -LiteralPath '{path(filename)}') -and (Get-Item -LiteralPath '{path(filename)}').Length -gt 16",
                       seconds=35)


async def procexp(desktop):
    await helper(desktop, "QAManifestExporter", r"""
        using System;
        using System.IO;
        using System.Threading;
        class QAManifestExporter {
            static void Main() {
                const string root = @"C:\OSLabWall\";
                using (File.Open(root + "release-qa.lock", FileMode.Create, FileAccess.Write, FileShare.None)) {
                    File.WriteAllText(root + "exporter-ready.txt", System.Diagnostics.Process.GetCurrentProcess().Id.ToString());
                    DateTime deadline = DateTime.UtcNow.AddMinutes(5);
                    while (!File.Exists(root + "release-lock.txt") && DateTime.UtcNow < deadline) Thread.Sleep(150);
                }
                File.WriteAllText(root + "exporter-finished.txt", "released");
            }
        }
    """)
    await launcher(desktop, "QAManifestExporter")
    await desktop.wait(rf"Test-Path -LiteralPath '{path('exporter-ready.txt')}'")
    await desktop.launch("procexp", ["/AcceptEula"])
    await capture(desktop, "process-launch", 1.6)
    await desktop.key("Win", "Up")
    await capture(desktop, "stage-0")
    await explorer_search(desktop, "release-qa.lock", "stage-1")
    await capture(desktop, "stage-2")
    await save_handle_search(desktop, "release-handle-search.txt")
    locked = await powershell_json(desktop, rf"""
        $pidFixture = [int](Get-Content -LiteralPath '{path('exporter-ready.txt')}')
        $process = Get-Process -Id $pidFixture
        $locked = $false
        try {{ $handle = [IO.File]::Open('{path('release-qa.lock')}', 'Open', 'Read', 'None'); $handle.Dispose() }}
        catch [IO.IOException] {{ $locked = $true }}
        $export = [IO.File]::ReadAllText('{path('release-handle-search.txt')}')
        $match = [bool]($export -split '\r?\n' | Where-Object {{
            $_ -match 'QAManifestExporter(?:\.exe)?' -and $_ -match ('\b' + $pidFixture + '\b') -and
            $_ -match [regex]::Escape('{path('release-qa.lock')}')
        }})
        @{{name=$process.ProcessName; locked=$locked; pid=$pidFixture; searchMatches=$match}} | ConvertTo-Json -Compress
    """)
    await desktop.upload("release-lock.txt", b"finish\n")
    await desktop.wait(rf"Test-Path -LiteralPath '{path('exporter-finished.txt')}'", seconds=15)
    await desktop.key("Escape")
    await explorer_search(desktop, "release-qa.lock")
    await capture(desktop, "stage-3")
    remaining = await desktop.inspect(r"(?i)^(procexp|procexp64)$", r"^0 matching items\.?$")
    released = await powershell_json(desktop, rf"""
        $handle = [IO.File]::Open('{path('release-qa.lock')}', 'Open', 'Read', 'None')
        $handle.Dispose()
        @{{released=$true; exited=($null -eq (Get-Process -Id {int(locked["pid"])} -ErrorAction SilentlyContinue))}} |
            ConvertTo-Json -Compress
    """)
    return [
        check("Windows identified the dedicated manifest exporter", "QAManifestExporter", locked["name"]),
        check("An independent exclusive open was blocked while the exporter held the file", True, locked["locked"]),
        check("Process Explorer saved the exact exporter PID and file handle", True, locked["searchMatches"]),
        check("Process Explorer reported zero matches after release", True, bool(remaining)),
        check("The exporter exited and an independent exclusive open succeeded", True, released["released"] and released["exited"]),
    ]


async def tcpview(desktop):
    await desktop.ps(rf"""
        $active = Get-CimInstance Win32_Process -Filter "Name='QALoopbackService.exe'" |
            Where-Object ExecutablePath -eq '{path('QALoopbackService.exe')}'
        if ($active) {{ throw 'A prior loopback fixture is still running.' }}
        foreach ($name in @('tcp-ready.txt', 'tcp-connect.txt', 'tcp-established.txt', 'tcp-finish.txt', 'tcpview-snapshot.txt')) {{
            $file = Join-Path '{GUEST}' $name
            if (Test-Path -LiteralPath $file) {{ Remove-Item -LiteralPath $file }}
        }}
    """)
    await helper(desktop, "QALoopbackService", r"""
        using System;
        using System.IO;
        using System.Net;
        using System.Net.Sockets;
        using System.Threading;
        class QALoopbackService {
            static void Main() {
                const string root = @"C:\OSLabWall\";
                var listener = new TcpListener(IPAddress.Loopback, 46361);
                listener.Start();
                using (var client = new TcpClient()) {
                    File.WriteAllText(root + "tcp-ready.txt", System.Diagnostics.Process.GetCurrentProcess().Id.ToString());
                    DateTime deadline = DateTime.UtcNow.AddMinutes(3);
                    while (!File.Exists(root + "tcp-connect.txt") && DateTime.UtcNow < deadline) Thread.Sleep(150);
                    if (!File.Exists(root + "tcp-connect.txt")) return;
                    client.Connect(IPAddress.Loopback, 46361);
                    using (var accepted = listener.AcceptTcpClient()) {
                        File.WriteAllText(root + "tcp-established.txt", "connected");
                        while (!File.Exists(root + "tcp-finish.txt") && DateTime.UtcNow < deadline) Thread.Sleep(150);
                    }
                }
                listener.Stop();
            }
        }
    """)
    await launcher(desktop, "QALoopbackService")
    await desktop.wait(rf"Test-Path -LiteralPath '{path('tcp-ready.txt')}'")
    await desktop.launch("tcpview", ["/AcceptEula"])
    await capture(desktop, "tcp-launch", 1.6)
    await desktop.key("Win", "Up")
    await capture(desktop, "stage-0")
    await desktop.upload("tcp-connect.txt", b"establish\n")
    await desktop.wait(rf"Test-Path -LiteralPath '{path('tcp-established.txt')}'", seconds=20)
    await capture(desktop, "stage-1", 1.2)
    await native_save(desktop, "tcpview-snapshot.txt", r"(?i)^tcpview(64)?$", "stage-2")
    observed = await powershell_json(desktop, rf"""
        $pidFixture = [int](Get-Content -LiteralPath '{path('tcp-ready.txt')}')
        $sockets = @(Get-NetTCPConnection -OwningProcess $pidFixture)
        $export = '{path('tcpview-snapshot.txt')}'
        $bytes = [IO.File]::ReadAllBytes($export)
        # TCPView's native Save command can emit UTF-16 LE without a BOM.
        $text = if ($bytes.Length -ge 4 -and $bytes[1] -eq 0 -and $bytes[3] -eq 0) {{
            [Text.Encoding]::Unicode.GetString($bytes)
        }} else {{ [IO.File]::ReadAllText($export) }}
        $rows = $text -split '\r?\n' | ConvertFrom-Csv -Header Name,ProcessId,Protocol,State,LocalAddress,LocalPort,RemoteAddress,RemotePort
        $exported = $rows | Where-Object {{
            $_.Name -ieq 'QALoopbackService.exe' -and $_.ProcessId -eq $pidFixture -and
            $_.Protocol -eq 'TCP' -and $_.State -eq 'Established' -and
            $_.LocalAddress -eq '127.0.0.1' -and $_.LocalPort -eq 46361 -and $_.RemoteAddress -eq '127.0.0.1'
        }}
        @{{listener=[bool]($sockets | Where-Object {{ $_.State -eq 'Listen' -and $_.LocalAddress -eq '127.0.0.1' -and $_.LocalPort -eq 46361 }});
           connected=[bool]($sockets | Where-Object {{ $_.State -eq 'Established' -and $_.LocalAddress -eq '127.0.0.1' -and $_.RemoteAddress -eq '127.0.0.1' -and $_.LocalPort -eq 46361 }});
           snapshot=[bool]$exported}} |
            ConvertTo-Json -Compress
    """)
    await desktop.upload("tcp-finish.txt", b"close\n")
    await desktop.wait("(Get-NetTCPConnection -LocalPort 46361 -State Listen -ErrorAction SilentlyContinue | Measure-Object).Count -eq 0", seconds=20)
    await capture(desktop, "stage-3", 1.4)
    return [
        check("The QA program listened only on loopback port 46361", True, observed["listener"]),
        check("Windows observed the established local client session", True, observed["connected"]),
        check("TCPView's GUI export identified the same process, port, and connection state", True, observed["snapshot"]),
    ]


async def vmmap(desktop):
    from uuid import uuid4

    attempt = uuid4().hex[:6]
    loader = f"QABufferLoader-{attempt}"
    ready = f"memory-{attempt}-ready.txt"
    load = f"memory-{attempt}-load.txt"
    allocated = f"memory-{attempt}-allocated.txt"
    finish = f"memory-{attempt}-finish.txt"
    snapshot = f"buffer-after-{attempt}.mmp"
    await helper(desktop, loader, r"""
        using System;
        using System.IO;
        using System.Runtime.InteropServices;
        using System.Threading;
        class QABufferLoader {
            static void Main() {
                const string root = @"C:\OSLabWall\";
                File.WriteAllText(root + "memory-ready.txt", System.Diagnostics.Process.GetCurrentProcess().Id.ToString());
                DateTime deadline = DateTime.UtcNow.AddMinutes(3);
                while (!File.Exists(root + "memory-load.txt") && DateTime.UtcNow < deadline) Thread.Sleep(150);
                if (!File.Exists(root + "memory-load.txt")) return;
                var data = Marshal.AllocHGlobal(32 * 1024 * 1024);
                try {
                    for (int i = 0; i < 32 * 1024 * 1024; i += 4096) Marshal.WriteByte(data, i, 7);
                    File.WriteAllText(root + "memory-allocated.txt", "33554432");
                    while (!File.Exists(root + "memory-finish.txt") && DateTime.UtcNow < deadline) Thread.Sleep(150);
                } finally { Marshal.FreeHGlobal(data); }
            }
        }
    """.replace("memory-", f"memory-{attempt}-"))
    await launcher(desktop, loader)
    await desktop.wait(rf"Test-Path -LiteralPath '{path(ready)}'")
    process_id = int((await desktop.ps(rf"Get-Content -LiteralPath '{path(ready)}'")).stdout.strip())
    before = int((await desktop.ps(f"(Get-Process -Id {process_id}).PrivateMemorySize64")).stdout.strip())
    await desktop.launch("vmmap", ["/AcceptEula", "-p", str(process_id)])
    await capture(desktop, "memory-launch", 3)
    await desktop.key("Win", "Up")
    await capture(desktop, "stage-0")
    await desktop.upload(load, b"commit buffer\n")
    await desktop.wait(rf"Test-Path -LiteralPath '{path(allocated)}'", seconds=18)
    await desktop.key("F5")
    await capture(desktop, "stage-1", 2)
    # VMMap's Ctrl+S opens the native file picker with the filename selected.
    await desktop.key("Ctrl", "s")
    await capture(desktop, "snapshot-save-dialog", 1)
    await desktop.key("Alt", "n")
    await desktop.key("Ctrl", "a")
    await desktop.paste(path(snapshot))
    await capture(desktop, "stage-2")
    await desktop.key("Enter")
    await desktop.wait(rf"(Test-Path -LiteralPath '{path(snapshot)}') -and (Get-Item -LiteralPath '{path(snapshot)}').Length -gt 1024",
                       seconds=22)
    after = int((await desktop.ps(f"(Get-Process -Id {process_id}).PrivateMemorySize64")).stdout.strip())
    size = int((await desktop.ps(rf"(Get-Item -LiteralPath '{path(snapshot)}').Length")).stdout.strip())
    amount = int((await desktop.ps(rf"Get-Content -LiteralPath '{path(allocated)}'")).stdout.strip())
    await desktop.key("Ctrl", "o")
    await asyncio.sleep(.55)
    await desktop.key("Alt", "n")
    await desktop.paste(path(snapshot))
    await desktop.key("Enter")
    await capture(desktop, "stage-3", 1.5)
    await desktop.upload(finish, b"release\n")
    return [
        check("The test program committed an exact 32 MiB buffer", 32 * MIB, amount),
        check("Windows private bytes grew by at least 31 MiB", True, after - before >= 31 * MIB),
        check("VMMap saved a nonempty native memory-map snapshot", True, size > 1024),
    ]


async def execute(case_id, desktop):
    cases = {"25": procmon, "26": procexp, "27": tcpview, "28": vmmap}
    return await cases[str(case_id)](desktop)
