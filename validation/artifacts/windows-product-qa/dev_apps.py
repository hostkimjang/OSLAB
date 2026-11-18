"""Local release QA scenarios for four installed Windows developer tools."""

from __future__ import annotations

import asyncio
import base64
import json


WORKSPACE = r"C:\OSLabWall"
CASES = {
    "05": {
        "title": "Visual Studio Code",
        "kicker": "RELEASE CONFIGURATION QA",
        "scenario": "Reproduce a Windows service startup-budget regression, fix the candidate configuration and rerun the gate.",
        "steps": ["Open candidate JSON", "Reproduce startup gate failure", "Correct the budget", "Rerun release checks"],
        "package": "vscode",
    },
    "06": {
        "title": "Git GUI",
        "kicker": "RELEASE DIFF REVIEW",
        "scenario": "Review the rollback guard diff, stage only that fixture change, and audit the resulting local Git tree.",
        "steps": ["Open the working tree", "Stage the guard change", "Review staged diff", "Confirm the local commit"],
        "package": "gitgui",
    },
    "07": {
        "title": "Python IDLE",
        "kicker": "UNIT TEST REGRESSION",
        "scenario": "Run three retry-budget tests, repair the off-by-one limit in IDLE, then rerun the suite.",
        "steps": ["Open the test fixture", "Run the failing suite", "Repair the retry cap", "Confirm three passing tests"],
        "package": "idle",
    },
    "16": {
        "title": "ILSpy",
        "kicker": ".NET BINARY CONTRACT QA",
        "scenario": "Inspect two synthetic release binaries and export the candidate's public API for signature checks.",
        "steps": ["Inspect baseline IL", "Open candidate decompilation", "Export the public class", "Validate exported signatures"],
        "package": "ilspy",
    },
}


def check(name, expected, observed):
    return {"name": name, "expected": expected, "observed": observed, "passed": expected == observed}


def ps_literal(value):
    return "'" + value.replace("'", "''") + "'"


def guest_path(name):
    return WORKSPACE + "\\" + name


async def upload_text(desktop, name, content):
    await desktop.upload(name, content.encode("utf-8"))


async def observed_json(desktop, script):
    result = await desktop.ps(
        "$json=(& {\n" + script + "\n} | Out-String); "
        "[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))"
    )
    return json.loads(base64.b64decode(result.stdout.strip(), validate=True))


async def snapshot(desktop, stage, delay=.55):
    await asyncio.sleep(delay)
    return await desktop.screenshot(stage)


async def maximize(desktop):
    await desktop.key("Escape")
    await desktop.key("Win", "Up")


async def interactive_window_titles(desktop, process):
    """Inspect windows from the same desktop session that owns them."""
    report = ps_literal(guest_path(process + "-window-evidence.json"))
    await desktop.ps(f"if (Test-Path -LiteralPath {report}) {{ Remove-Item -LiteralPath {report} }}")
    await desktop.task("OSLabDevWindowProbe", rf"""
        $session = (Get-Process -Id $PID).SessionId
        $titles = @()
        for ($attempt = 0; $attempt -lt 30 -and !$titles.Count; $attempt++) {{
            $titles = @(Get-Process -Name {ps_literal(process)} -ErrorAction SilentlyContinue |
                Where-Object {{ $_.SessionId -eq $session -and $_.MainWindowHandle -ne 0 }} |
                ForEach-Object {{ $_.MainWindowTitle }} | Where-Object {{ $_ }})
            if (!$titles.Count) {{ Start-Sleep -Milliseconds 800 }}
        }}
        [IO.File]::WriteAllText({report}, (@{{titles=$titles}} | ConvertTo-Json -Compress))
    """)
    await desktop.wait(f"Test-Path -LiteralPath {report}", seconds=40)
    return (await desktop.read_json(guest_path(process + "-window-evidence.json")))["titles"]


async def vscode_command(desktop, command):
    await desktop.key("F1")
    await desktop.paste(command)
    await asyncio.sleep(.3)
    await desktop.key("Enter")


async def show_vscode_document(desktop, profile_flags, name, stage=None):
    path = guest_path(name)
    await desktop.launch("vscode", [*profile_flags, "--reuse-window", path])
    await asyncio.sleep(1.35)
    titles = await interactive_window_titles(desktop, "Code")
    if not any(name.casefold() in title.casefold() for title in titles):
        await desktop.key("Ctrl", "o")
        await asyncio.sleep(.7)
        await desktop.key("Alt", "n")
        await desktop.paste(path)
        await desktop.key("Enter")
        await asyncio.sleep(1.25)
        titles = await interactive_window_titles(desktop, "Code")
    if not any(name.casefold() in title.casefold() for title in titles):
        await snapshot(desktop, "editor-document-unavailable")
        raise RuntimeError(f"Visual Studio Code did not open {name}")
    if stage:
        await snapshot(desktop, stage)


async def run_startup_gate(desktop, command, state, *, terminal_command=None):
    result_path = guest_path(f"vscode-{state}.json")
    quoted_path = ps_literal(result_path)
    await desktop.ps(f"if (Test-Path -LiteralPath {quoted_path}) {{ Remove-Item -LiteralPath {quoted_path} }}")
    if terminal_command:
        try:
            await vscode_command(desktop, terminal_command)
            await asyncio.sleep(1.5)
            await desktop.paste(command)
            await desktop.key("Enter")
            await desktop.wait(f"Test-Path -LiteralPath {quoted_path}", seconds=8)
            await snapshot(desktop, f"terminal-{state.lower()}")
            return True
        except TimeoutError:
            await snapshot(desktop, f"terminal-{state.lower()}-fallback")
            await desktop.key("Escape")
    expected_exit = 0 if state == "PASS" else 1
    await desktop.ps(
        "& " + command + "\n"
        f"if ($LASTEXITCODE -ne {expected_exit}) {{ throw 'Unexpected release-gate exit code.' }}\n"
        f"if (!(Test-Path -LiteralPath {quoted_path})) {{ throw 'Missing release-gate output.' }}\n"
        "exit 0"
    )
    return False


VS_GATE = r"""
$ErrorActionPreference = 'Stop'
$config = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'release-gate.json') -Raw | ConvertFrom-Json
$samples = @(2137,2291,2742,3198)
$missed = @($samples | Where-Object { $_ -gt $config.startupTimeoutMs }).Count
$configUnchanged = $config.artifact -ceq 'LedgerBridge-2.4.0-win-x64.msi' -and
    $config.channel -ceq 'candidate' -and $config.retryLimit -eq 3 -and
    ($config.routes -join ',') -ceq 'health,ready'
$passed = $missed -eq 0 -and $configUnchanged -and $config.startupTimeoutMs -le 5000
$state = if ($passed) { 'PASS' } else { 'FAIL' }
$result = [ordered]@{
    releaseCriterion = 'All four cold starts must fit the release budget.'
    status = $state
    limit = $config.startupTimeoutMs
    coldStartSamplesMs = $samples
    misses = $missed
    samples = $samples.Count
    artifact = $config.artifact
    unchanged = $configUnchanged
}
[IO.File]::WriteAllText((Join-Path $PSScriptRoot "vscode-$state.json"), ($result | ConvertTo-Json))
Write-Host 'LEDGER BRIDGE / WINDOWS RELEASE GATE' -ForegroundColor Cyan
Write-Host "Startup replay: $($samples -join ' / ') ms"
$color = if ($passed) { 'Green' } else { 'Red' }
Write-Host "$state - $missed/$($samples.Count) cold starts missed the $($config.startupTimeoutMs) ms budget." -ForegroundColor $color
if (!$passed) { exit 1 }
"""


async def vscode(desktop):
    name = "release-gate.json"
    path = guest_path(name)
    before = {
        "artifact": "LedgerBridge-2.4.0-win-x64.msi",
        "channel": "candidate",
        "startupTimeoutMs": 2000,
        "retryLimit": 3,
        "routes": ["health", "ready"],
    }
    after = {**before, "startupTimeoutMs": 3500}
    await upload_text(desktop, name, json.dumps(before, indent=2) + "\n")
    await upload_text(desktop, "verify-startup.ps1", VS_GATE)
    profile = guest_path("vscode-qa-profile")
    profile_flags = ["--user-data-dir", profile]
    flags = ["--disable-gpu", "--disable-extensions", "--locale", "en-US", "--new-window"]
    await desktop.launch("vscode", [*profile_flags, *flags, path])
    await snapshot(desktop, "editor-startup", 2.5)
    titles = await interactive_window_titles(desktop, "Code")
    if not titles:
        profile_flags = []
        await desktop.launch("vscode", [path])
        await snapshot(desktop, "editor-startup-retry", 2.5)
        titles = await interactive_window_titles(desktop, "Code")
    if not titles:
        await snapshot(desktop, "editor-window-unavailable")
        raise RuntimeError("Visual Studio Code did not open an interactive window")
    await maximize(desktop)
    if not any(name.lower() in title.lower() for title in titles):
        await show_vscode_document(desktop, profile_flags, name)
    await snapshot(desktop, "stage-0")
    run = r"powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File C:\OSLabWall\verify-startup.ps1"
    integrated = await run_startup_gate(desktop, run, "FAIL", terminal_command="Terminal: Create New Terminal")
    red = guest_path("vscode-FAIL.json")
    await show_vscode_document(desktop, profile_flags, "vscode-FAIL.json", "stage-1")

    await show_vscode_document(desktop, profile_flags, name)
    await desktop.key("Ctrl", "1")
    await desktop.key("Ctrl", "a")
    await desktop.paste(json.dumps(after, indent=2) + "\n")
    await desktop.key("Ctrl", "s")
    await desktop.wait(f"(Get-Content -LiteralPath {ps_literal(path)} -Raw | ConvertFrom-Json).startupTimeoutMs -eq 3500")
    await snapshot(desktop, "stage-2")
    await run_startup_gate(desktop, run, "PASS", terminal_command="Terminal: Focus Terminal" if integrated else None)
    green = guest_path("vscode-PASS.json")
    await show_vscode_document(desktop, profile_flags, "vscode-PASS.json", "stage-3")
    failed = await desktop.read_json(red)
    passed = await desktop.read_json(green)
    actual = await desktop.read_json(path)
    return [
        check("All four cold starts exceeded the original measured budget", [4, 4, 2000],
              [failed["misses"], failed["samples"], failed["limit"]]),
        check("All four cold starts pass with the updated candidate", [0, 4, 3500],
              [passed["misses"], passed["samples"], passed["limit"]]),
        check("Only startupTimeoutMs changed in the editor", after, actual),
        check("The gate retained the release artifact, routes and retry limit", True, passed["unchanged"]),
    ]


GIT_DISCOVERY = r"""
$candidates = @(
    'C:\Program Files\Git\cmd\git.exe',
    'C:\OSLabWall\apps\git\cmd\git.exe',
    'C:\OSLabWall\apps\gitgui\cmd\git.exe',
    'C:\OSLabApps\git\cmd\git.exe',
    'C:\OSLabApps\gitgui\cmd\git.exe'
)
$found = Get-Command git.exe -ErrorAction SilentlyContinue
if ($found) { $candidates += $found.Source }
$git = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (!$git) { throw 'The Git for Windows command was not found.' }
function Invoke-FixtureGit {
    $output = & $git -c safe.directory=C:/OSLabWall/release-repo -C 'C:\OSLabWall\release-repo' @args
    if ($LASTEXITCODE -ne 0) { throw "Fixture Git exited with $LASTEXITCODE" }
    $output
}
"""


async def git_gui(desktop):
    repo = guest_path("release-repo")
    message = "fix: keep rollback guard enabled"
    await desktop.task("OSLabGitFixture", "$ErrorActionPreference = 'Stop'\n" + GIT_DISCOVERY + r"""
$repo = 'C:\OSLabWall\release-repo'
New-Item -ItemType Directory -Path $repo | Out-Null
Invoke-FixtureGit init -q -b qa-release
Invoke-FixtureGit config --local user.name 'Release QA'
Invoke-FixtureGit config --local user.email 'release-qa@example.invalid'
Invoke-FixtureGit config --local core.autocrlf false
Invoke-FixtureGit config --local commit.gpgsign false
Invoke-FixtureGit config --local gui.gcwarning false
$gate = Join-Path $repo 'release-guard.ini'
$manifest = Join-Path $repo 'artifact-manifest.txt'
[IO.File]::WriteAllText($gate, "[release]`nchannel=candidate`nrollback_guard=off`nretry_limit=3`n")
[IO.File]::WriteAllText($manifest, "artifact=LedgerBridge-2.4.0-win-x64.msi`n")
Invoke-FixtureGit add -- 'release-guard.ini' 'artifact-manifest.txt'
Invoke-FixtureGit commit -qm 'baseline: record release fixtures'
[IO.File]::WriteAllText($gate, "[release]`nchannel=candidate`nrollback_guard=on`nretry_limit=3`n")
[IO.File]::WriteAllText('C:\OSLabWall\git-fixture-ready', 'ready')
""")
    await desktop.wait(r"Test-Path -LiteralPath 'C:\OSLabWall\git-fixture-ready'")
    await desktop.launch("gitgui", ["-C", repo, "gui"])
    await snapshot(desktop, "git-startup", 3.0)
    await maximize(desktop)
    await desktop.key("Alt", "1")
    await snapshot(desktop, "stage-0")
    await desktop.key("Ctrl", "i")
    await asyncio.sleep(.5)
    await desktop.key("Alt", "2")
    await snapshot(desktop, "stage-1")
    staged = await observed_json(desktop, GIT_DISCOVERY + r"""
        @{files=@(Invoke-FixtureGit diff --cached --name-only);
          change=@(Invoke-FixtureGit diff --cached --unified=0 -- 'release-guard.ini' |
            Where-Object { $_ -match '^[+-]rollback_guard=' })} | ConvertTo-Json -Compress
    """)
    if staged["files"] != ["release-guard.ini"]:
        raise RuntimeError("Git GUI did not stage the intended release-guard diff")
    await desktop.key("Alt", "4")
    await desktop.paste(message)
    await snapshot(desktop, "stage-2")
    await desktop.key("Ctrl", "Enter")
    await asyncio.sleep(1.7)
    result = await observed_json(desktop, GIT_DISCOVERY + r"""
        @{subject=[string](Invoke-FixtureGit show -s --format=%s HEAD);
          commits=[int](Invoke-FixtureGit rev-list --count HEAD);
          changes=@(Invoke-FixtureGit diff-tree --no-commit-id --name-only -r HEAD);
          gate=@(Invoke-FixtureGit show HEAD:release-guard.ini);
          unchanged=([string](Invoke-FixtureGit rev-parse HEAD:artifact-manifest.txt) -ceq
             [string](Invoke-FixtureGit rev-parse HEAD~1:artifact-manifest.txt));
          clean=@(Invoke-FixtureGit status --porcelain).Count -eq 0;
          remotes=@(Invoke-FixtureGit remote).Count} | ConvertTo-Json -Compress
    """)
    await snapshot(desktop, "stage-3")
    return [
        check("One staged line switched the rollback guard on", ["-rollback_guard=off", "+rollback_guard=on"], staged["change"]),
        check("The GUI created the intended second local commit", [message, 2], [result["subject"], result["commits"]]),
        check("Only the release guard changed in the committed tree", ["release-guard.ini"], result["changes"]),
        check("The approved rollback value is present in the Git blob", True, "rollback_guard=on" in result["gate"]),
        check("The original manifest blob is unchanged", True, result["unchanged"]),
        check("Fixture repository has a clean tree and no remotes", [True, 0], [result["clean"], result["remotes"]]),
    ]


IDLE_TEST = '''# Release test: Windows service retry budget.

RETRY_LIMIT = 4

import json
from pathlib import Path
import unittest


def retry_budget(requested):
    return max(0, min(requested, RETRY_LIMIT))


class CandidateBudgetTests(unittest.TestCase):
    def test_negative_requests_are_rejected(self):
        self.assertEqual(retry_budget(-4), 0)

    def test_release_caps_retries_at_three(self):
        self.assertEqual(retry_budget(18), 3, "One extra retry delays failover.")

    def test_requests_below_limit_are_preserved(self):
        self.assertEqual(retry_budget(2), 2)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CandidateBudgetTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    color = "green" if result.wasSuccessful() else "red"
    failures = [test._testMethodName for test, _ in result.failures]
    failures += [test._testMethodName for test, _ in result.errors]
    data = {"tests": result.testsRun, "failures": failures, "limit": RETRY_LIMIT}
    Path(__file__).with_name("idle-" + color + ".json").write_text(json.dumps(data), encoding="utf-8")
'''


async def idle(desktop):
    name = "release_retry_test.py"
    path = guest_path(name)
    await upload_text(desktop, name, IDLE_TEST)
    await desktop.launch("idle", ["-m", "idlelib", "-e", path])
    await snapshot(desktop, "idle-startup", 3.0)
    await maximize(desktop)
    await snapshot(desktop, "stage-0")
    await desktop.key("F5")
    red = guest_path("idle-red.json")
    await desktop.wait(f"Test-Path -LiteralPath {ps_literal(red)}")
    await desktop.key("Win", "Up")
    await snapshot(desktop, "stage-1", .85)

    await desktop.key("Alt", "Tab")
    await asyncio.sleep(.4)
    await desktop.key("Alt", "g")
    await desktop.paste("3")
    await desktop.key("Enter")
    await desktop.key("Home")
    await desktop.key("Shift", "End")
    await desktop.paste("RETRY_LIMIT = 3")
    await desktop.key("Ctrl", "s")
    await desktop.wait(
        f"@(Get-Content -LiteralPath {ps_literal(path)} -TotalCount 3)[2] -ceq 'RETRY_LIMIT = 3'"
    )
    await snapshot(desktop, "stage-2")
    await desktop.key("F5")
    green = guest_path("idle-green.json")
    await desktop.wait(f"Test-Path -LiteralPath {ps_literal(green)}")
    await snapshot(desktop, "stage-3", .85)
    original = await desktop.read_json(red)
    corrected = await desktop.read_json(green)
    source = await desktop.ps(
        f"[Convert]::ToBase64String([IO.File]::ReadAllBytes({ps_literal(path)}))"
    )
    text = base64.b64decode(source.stdout.strip(), validate=True).decode("utf-8-sig").replace("\r\n", "\n")
    return [
        check("Baseline runs three tests and isolates the off-by-one regression",
              {"tests": 3, "failures": ["test_release_caps_retries_at_three"], "limit": 4}, original),
        check("Corrected suite passes all three tests", {"tests": 3, "failures": [], "limit": 3}, corrected),
        check("Only the release retry constant changed in the saved fixture",
              IDLE_TEST.replace("RETRY_LIMIT = 4", "RETRY_LIMIT = 3"), text),
    ]


def contract_library(state):
    return f"""
using System.Reflection;
[assembly: AssemblyVersion("3.0.0.0")]
namespace ReleaseGate {{
    public static class ApiContract {{
        public const int ContractVersion = 3;
        public static string State() {{ return "{state}"; }}
        public static int GetRetryBudget(int supplied) {{
            return System.Math.Min(3, System.Math.Max(0, supplied));
        }}
    }}
}}
"""


async def ilspy(desktop):
    for filename, state in (("BaselineContract", "queued"), ("CandidateContract", "signed")):
        source = guest_path(filename + ".cs")
        output = guest_path(filename + ".dll")
        await upload_text(desktop, filename + ".cs", contract_library(state))
        await desktop.ps(
            f"Add-Type -TypeDefinition (Get-Content -LiteralPath {ps_literal(source)} -Raw) "
            f"-OutputAssembly {ps_literal(output)} -OutputType Library -Language CSharp"
        )

    baseline = guest_path("BaselineContract.dll")
    candidate = guest_path("CandidateContract.dll")
    args = ["--navigateto:T:ReleaseGate.ApiContract", "--language:C#"]
    await desktop.launch("ilspy", ["--newinstance", *args, baseline])
    await snapshot(desktop, "ilspy-startup", 2.0)
    if not await interactive_window_titles(desktop, "ILSpy"):
        raise RuntimeError("ILSpy did not open an interactive window")
    await asyncio.sleep(2.0)
    await maximize(desktop)
    await snapshot(desktop, "stage-0")
    await desktop.launch("ilspy", [*args, candidate])
    await snapshot(desktop, "stage-1", 2.0)

    export = guest_path("CandidateApi.review.cs")
    await desktop.key("Ctrl", "s")
    await snapshot(desktop, "save-dialog", .95)
    await desktop.key("Alt", "n")
    await desktop.key("Ctrl", "a")
    await desktop.paste(export)
    await snapshot(desktop, "stage-2")
    await desktop.key("Enter")
    await desktop.wait(f"Test-Path -LiteralPath {ps_literal(export)}", seconds=40)
    await snapshot(desktop, "stage-3", .85)
    actual = await observed_json(desktop, rf"""
        $old = [Reflection.Assembly]::LoadFile('{baseline}')
        $new = [Reflection.Assembly]::LoadFile('{candidate}')
        $oldApi = $old.GetType('ReleaseGate.ApiContract', $true)
        $newApi = $new.GetType('ReleaseGate.ApiContract', $true)
        function PublicMethods($type) {{
            @($type.GetMethods([Reflection.BindingFlags]'DeclaredOnly,Public,Static') |
                ForEach-Object {{ $_.Name }} | Sort-Object)
        }}
        $text = Get-Content -LiteralPath '{export}' -Raw
        @{{version=$new.GetName().Version.ToString(); baselineMethods=@(PublicMethods $oldApi);
          candidateMethods=@(PublicMethods $newApi);
          state=$newApi.GetMethod('State').Invoke($null, @());
          exportedPublic=($text -match 'public\s+static\s+class\s+ApiContract');
          exportedLimit=($text -match 'public\s+static\s+int\s+GetRetryBudget\s*\(\s*int\s+');
          exportedState=($text -match 'return\s+"signed"\s*;')}} | ConvertTo-Json -Compress
    """)
    return [
        check("The release candidate retains its 3.0 binary version", "3.0.0.0", actual["version"]),
        check("Baseline and candidate retain the exact public API methods",
              [["GetRetryBudget", "State"], ["GetRetryBudget", "State"]],
              [actual["baselineMethods"], actual["candidateMethods"]]),
        check("The compiled candidate returns the signed release state", "signed", actual["state"]),
        check("ILSpy exported the public class, retry signature and candidate state",
              [True, True, True], [actual["exportedPublic"], actual["exportedLimit"], actual["exportedState"]]),
    ]


async def execute(case_id, desktop):
    run = {"05": vscode, "06": git_gui, "07": idle, "16": ilspy}
    return await run[case_id](desktop)
