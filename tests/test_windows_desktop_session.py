from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from oslab.config import OslabConfig
from oslab.errors import ProviderError, ScenarioValidationError
from oslab.guests.base import GuestCommandResult, GuestFileReadResult, GuestFileWriteResult
from oslab.models.scenario import load_scenario, validate_scenario_mapping
from oslab.providers.base import VmRef
from oslab.runners import proxmox_artifact_smoke, windows_desktop_session
from oslab.runners.proxmox_guest_preflight import GuestPreflightCheck
from oslab.runners.windows_desktop_session import (
    CONSOLE_HELPER,
    SIGN_IN_SCRIPT,
    DesktopConsole,
    _console_spec,
    open_desktop_console,
    sign_in_desktop,
)

VM = VmRef(vm_id=9191, name="oslab-desktop-session-9191", node="pve")


def scenario_mapping(os_family: str, screen: dict) -> dict:
    return {
        "schemaVersion": 1,
        "id": f"desktop.{os_family}",
        "os": {"family": os_family},
        "provider": {"type": "proxmox"},
        "guest": {"mode": "qemuAgent", "screen": screen},
        "assertions": [{"type": "command.exitCode", "id": "exit-zero", "exitCode": 0}],
    }


def test_windows_screen_settings_are_valid() -> None:
    validate_scenario_mapping(scenario_mapping("windows", {"signIn": True, "showCommands": True}))
    validate_scenario_mapping(scenario_mapping("windows", {"signIn": True}))


@pytest.mark.parametrize(
    ("os_family", "screen", "message"),
    [
        ("windows", {"showCommands": True}, "requires `guest.screen.signIn: true`"),
        ("windows", {"showCommands": True, "signIn": False}, "requires `guest.screen.signIn: true`"),
        ("linux", {"signIn": True}, "supported only for Windows"),
        ("windows", {"signIn": "yes"}, "must be a boolean"),
        ("windows", {"signin": True}, "Unsupported guest.screen field"),
    ],
)
def test_invalid_screen_settings_are_rejected(os_family: str, screen: dict, message: str) -> None:
    with pytest.raises(ScenarioValidationError, match=re.escape(message)):
        validate_scenario_mapping(scenario_mapping(os_family, screen))


def ok(stdout: str = "") -> GuestCommandResult:
    return GuestCommandResult(command=(), exited=True, exit_code=0, stdout=stdout)


class SigningInGuest:
    """Answers the sign-in scripts like a Windows guest that restarts and then signs the user in."""

    def __init__(self, *, desktop_ready_after: int = 2, password_present_for: int = 0) -> None:
        self.desktop_ready_after = desktop_ready_after
        self.password_present_for = password_present_for
        self.cleanup_attempts = 0
        self.commands: list[list[str]] = []
        self.restarted = False
        self.unanswered_after_restart = 1
        self.desktop_probes = 0

    def execute(self, vm, command, *, timeout_seconds, poll_interval_seconds=1.0):
        self.commands.append(list(command))
        script = command[-1]
        if command[0] == "shutdown.exe":
            self.restarted = True
            return ok()
        if "RandomNumberGenerator" in script:
            return ok("2026-11-20T01:00:00.0000000Z\r\n")
        if "LastBootUpTime" in script:
            if self.restarted and self.unanswered_after_restart:
                self.unanswered_after_restart -= 1
                raise ProviderError("QEMU guest agent is not running")
            return ok("2026-11-20T01:05:00.0000000Z\r\n" if self.restarted else "2026-11-20T01:00:00.0000000Z\r\n")
        if "LogonUI" in script:
            self.desktop_probes += 1
            return ok("ready\r\n" if self.desktop_probes >= self.desktop_ready_after else "waiting\r\n")
        if "Remove-ItemProperty -LiteralPath $winlogon -Name DefaultPassword" in script:
            self.cleanup_attempts += 1
            return ok("present\r\n" if self.cleanup_attempts <= self.password_present_for else "removed\r\n")
        return ok("ready\r\n")


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def __call__(self, phase: str, message: str, **details) -> None:
        self.events.append((phase, details))

    @property
    def phases(self) -> list[str]:
        return [phase for phase, _ in self.events]


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def monotonic(self) -> float:
        return self.now


def run_sign_in(guest: SigningInGuest) -> tuple[GuestPreflightCheck, Recorder]:
    recorder = Recorder()
    clock = Clock()
    check = sign_in_desktop(guest, VM, emit=recorder, sleep=clock.sleep, monotonic=clock.monotonic)
    return check, recorder


def test_sign_in_restarts_waits_for_the_desktop_and_removes_the_password() -> None:
    guest = SigningInGuest()

    check, recorder = run_sign_in(guest)

    assert check.passed is True
    assert check.id == "desktop.sign_in"
    assert check.details["user"] == "OslabDesktop"
    assert check.details["autologonPasswordRemoved"] is True
    assert recorder.phases == ["desktop.signin.start", "desktop.signin.restart", "desktop.signin.wait", "desktop.signin.done"]
    scripts = [command[-1] for command in guest.commands]
    restart = next(index for index, command in enumerate(guest.commands) if command[0] == "shutdown.exe")
    assert "RandomNumberGenerator" in scripts[restart - 1]
    assert "StartMenuExperienceHost" in scripts[-2]
    assert "-Name DefaultPassword -ErrorAction" in scripts[-1]


def test_sign_in_keeps_the_password_inside_the_guest() -> None:
    # The guest script generates the password. These are the only lines allowed to use it, so it
    # never reaches stdout, the progress log or the report.
    allowed = [
        "$password = 'Os9!' + [Convert]::ToBase64String($bytes)",
        "$secure = ConvertTo-SecureString $password -AsPlainText -Force",
        "Set-ItemProperty -LiteralPath $winlogon -Name DefaultPassword -Value $password",
    ]
    uses = [line.strip() for line in SIGN_IN_SCRIPT.splitlines() if "$password" in line]
    assert uses == allowed

    guest = SigningInGuest()
    check, recorder = run_sign_in(guest)
    assert all("DefaultPassword -Value '" not in part for command in guest.commands for part in command)
    assert set(check.details) == {"user", "seconds", "autologonPasswordRemoved"}
    assert all(set(details) <= {"user", "seconds", "autologonPasswordRemoved", "timeoutSeconds"} for _, details in recorder.events)


def test_sign_in_removes_the_password_when_the_desktop_never_appears() -> None:
    guest = SigningInGuest(desktop_ready_after=10**6)

    check, recorder = run_sign_in(guest)

    assert check.passed is False
    assert check.message == "Timed out waiting for the desktop session"
    assert check.details["autologonPasswordRemoved"] is True
    assert check.details["error"]["failureClass"] == "desktop_signin_timeout"
    assert recorder.phases[-1] == "desktop.signin.failed"
    assert "-Name DefaultPassword -ErrorAction" in guest.commands[-1][-1]


def test_sign_in_fails_when_the_password_stays_in_the_registry() -> None:
    guest = SigningInGuest(password_present_for=3)
    check, recorder = run_sign_in(guest)

    assert check.passed is False
    assert check.message == "The automatic logon password could not be removed"
    assert recorder.phases[-1] == "desktop.signin.failed"
    assert guest.cleanup_attempts == 3


def test_sign_in_retries_if_password_remains() -> None:
    guest = SigningInGuest(password_present_for=1)
    check, _ = run_sign_in(guest)
    assert check.passed
    assert guest.cleanup_attempts == 2


@pytest.mark.parametrize("error", [OSError("cannot write progress"), KeyboardInterrupt()])
def test_sign_in_cleans_the_attempt_when_restart_progress_is_interrupted(error: BaseException) -> None:
    guest = SigningInGuest()
    clock = Clock()

    def emit(phase: str, message: str, **details) -> None:
        if phase == "desktop.signin.restart":
            raise error

    with pytest.raises(type(error)) as raised:
        sign_in_desktop(guest, VM, emit=emit, sleep=clock.sleep, monotonic=clock.monotonic)

    assert raised.value is error
    assert guest.cleanup_attempts == 1
    assert "-Name DefaultPassword -ErrorAction" in guest.commands[-1][-1]
    assert re.search(r"\$attempt = '[a-f0-9]{32}'", guest.commands[-1][-1]).group() in guest.commands[-2][-1]


ARGV = [
    "powershell.exe",
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    '& "C:\\Oslab\\artifact\\agent.ps1" register --token "s3cret-token" -Json',
]


def decode_spec(spec: bytes) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for line in spec.decode("ascii").splitlines():
        key, value = line.split("=", 1)
        fields.setdefault(key, []).append(base64.b64decode(value).decode("utf-8"))
    return fields


def test_console_spec_runs_the_same_command_and_masks_secrets_on_screen() -> None:
    fields = decode_spec(_console_spec(ARGV, title="OSLab \u00b7 register", secrets=["s3cret-token"]))

    assert fields["title"] == ["OSLab \u00b7 register"]
    assert fields["fileName"] == ["powershell.exe"]
    assert fields["arguments"] == [subprocess.list2cmdline(ARGV[1:])]
    assert fields["prompt"] == ["PS>"]
    assert fields["display"] == ['& "C:\\Oslab\\artifact\\agent.ps1" register --token "<redacted>" -Json']
    assert fields["redact"] == ["s3cret-token"]
    assert [fields[key][0] for key in ("left", "top", "width", "height", "fontSize")] == ["120", "80", "1040", "620", "24"]
    assert fields["fontName"] == ["Consolas", "Cascadia Mono"]


def test_console_spec_masks_both_line_endings_in_a_multiline_secret() -> None:
    fields = decode_spec(_console_spec(["app.exe", "before first\r\nsecond after"], title="Test", secrets=["first\nsecond"]))

    assert fields["display"] == ["before <redacted> after"]
    assert fields["redact"] == ["first\r\nsecond", "first\nsecond"]


class ConsoleGuest:
    """Records the console helper calls and returns a prepared helper result."""

    def __init__(self, result: dict, *, stdout: bytes | None = None, stderr: bytes = b"warning\r\n") -> None:
        self.result = result
        self.streams = {
            "stdout": "token s3cret-token \ud55c\uae00\r\n".encode("cp949") if stdout is None else stdout,
            "stderr": stderr,
        }
        self.reads: list[tuple[str, str, int, int]] = []
        self.uploads: dict[str, bytes] = {}
        self.commands: list[tuple[list[str], int]] = []

    def upload_bytes(self, vm, guest_path, content, *, progress=None):
        self.uploads[guest_path] = content
        return GuestFileWriteResult(guest_path=guest_path, bytes_written=len(content))

    def execute(self, vm, command, *, timeout_seconds, poll_interval_seconds=1.0):
        self.commands.append((list(command), timeout_seconds))
        if command[0] != CONSOLE_HELPER:
            return ok()
        if command[1] == "start":
            return ok(json.dumps({
                **self.result,
                "stdoutBytes": len(self.streams["stdout"]),
                "stderrBytes": len(self.streams["stderr"]),
            }))
        attempt, stream, offset, length = command[2:]
        offset, length = int(offset), int(length)
        self.reads.append((attempt, stream, offset, length))
        return ok(base64.b64encode(self.streams[stream][offset : offset + length]).decode("ascii"))


def helper_result(**overrides) -> dict:
    result = {
        "exitCode": 3,
        "seconds": 2.5,
        "timedOut": False,
        "error": None,
        "window": base64.b64encode(b"120 80 1040 620 1280 800").decode("ascii"),
        "font": base64.b64encode(b"Consolas 24").decode("ascii"),
        "codePage": 949,
    }
    result.update(overrides)
    return result


def test_console_returns_the_exact_command_result_and_reports_the_window() -> None:
    guest = ConsoleGuest(helper_result())
    recorder = Recorder()
    console = DesktopConsole(channel=guest, vm=VM, secrets=("s3cret-token",), emit=recorder)

    result = console.command_channel("register").execute(VM, ARGV, timeout_seconds=120)

    assert (result.exit_code, result.stdout, result.stderr) == (3, "token s3cret-token \ud55c\uae00\r\n", "warning\r\n")
    assert result.command == tuple(ARGV)
    launch = guest.commands[1]
    attempt = launch[0][2]
    assert re.fullmatch("[a-f0-9]{32}", attempt)
    assert launch == ([CONSOLE_HELPER, "start", attempt, "120"], 180)
    assert decode_spec(guest.uploads[f"C:\\Oslab\\screen\\command-{attempt}\\spec.txt"])["title"] == ["OSLab \u00b7 register"]
    assert "$abortCommand = $false" in guest.commands[-1][0][-1]
    assert f"$attempt = '{attempt}'" in guest.commands[-1][0][-1]
    assert recorder.events == [
        ("desktop.console.start", {"title": "OSLab \u00b7 register", "left": 120, "top": 80, "width": 1040, "height": 620}),
        (
            "desktop.console.done",
            {
                "title": "OSLab \u00b7 register",
                "exitCode": 3,
                "seconds": 2.5,
                "left": 120,
                "top": 80,
                "width": 1040,
                "height": 620,
                "screenWidth": 1280,
                "screenHeight": 800,
                "font": "Consolas 24",
            },
        ),
    ]


def test_console_timeout_raises_a_guest_execution_timeout() -> None:
    guest = ConsoleGuest(helper_result(timedOut=True, exitCode=None, seconds=None))
    recorder = Recorder()
    console = DesktopConsole(channel=guest, vm=VM, secrets=("s3cret-token",), emit=recorder)

    with pytest.raises(ProviderError) as raised:
        console.run(ARGV, label="register", timeout_seconds=30)

    assert raised.value.details["failureClass"] == "guest_execution_timeout"
    assert "s3cret-token" not in str(raised.value.details)
    assert guest.reads == []
    assert "$abortCommand = $true" in guest.commands[-1][0][-1]
    assert recorder.phases == ["desktop.console.start", "desktop.console.failed"]


def test_console_reports_a_console_that_could_not_run() -> None:
    error = base64.b64encode(b"The desktop console did not start. Is the desktop user signed in?").decode("ascii")
    guest = ConsoleGuest(helper_result(error=error, exitCode=None, seconds=None))
    console = DesktopConsole(channel=guest, vm=VM, secrets=(), emit=Recorder())

    with pytest.raises(ProviderError, match="could not run the command") as raised:
        console.run(ARGV, label="register", timeout_seconds=30)

    assert raised.value.details["reason"].startswith("The desktop console did not start")


def test_console_reads_multiple_chunks_and_preserves_utf8_split_between_them() -> None:
    chunk_size = windows_desktop_session.CONSOLE_READ_BYTES
    content = "x" * (chunk_size - 1) + "試\r\n"
    guest = ConsoleGuest(helper_result(), stdout=content.encode("utf-8"), stderr=b"")
    console = DesktopConsole(channel=guest, vm=VM, secrets=(), emit=Recorder())

    assert console.run(ARGV, label="scan", timeout_seconds=120).stdout == content
    assert [(stream, offset, length) for _, stream, offset, length in guest.reads] == [
        ("stdout", 0, chunk_size),
        ("stdout", chunk_size, 4),
    ]


@pytest.mark.parametrize("helper_exits", [True, False])
def test_console_cleans_up_when_start_or_result_read_fails(helper_exits: bool) -> None:
    class UnreadableConsole(ConsoleGuest):
        def execute(self, vm, command, *, timeout_seconds, poll_interval_seconds=1.0):
            if command[0] == CONSOLE_HELPER and command[1] == "start":
                return GuestCommandResult(command=(), exited=True, exit_code=0 if helper_exits else 1, stdout="s3cret-token", stderr="s3cret-token")
            return super().execute(vm, command, timeout_seconds=timeout_seconds, poll_interval_seconds=poll_interval_seconds)

    guest = UnreadableConsole(helper_result())
    console = DesktopConsole(channel=guest, vm=VM, secrets=("s3cret-token",), emit=Recorder())

    with pytest.raises(ProviderError) as raised:
        console.run(ARGV, label="register", timeout_seconds=120)

    assert "s3cret-token" not in str(raised.value.details)
    assert "$abortCommand = $true" in guest.commands[-1][0][-1]
    attempt = re.search(r"\$attempt = '([a-f0-9]{32})'", guest.commands[-1][0][-1]).group(1)
    assert list(guest.uploads) == [f"C:\\Oslab\\screen\\command-{attempt}\\spec.txt"]


def test_open_desktop_console_compiles_the_helper() -> None:
    guest = ConsoleGuest(helper_result())
    recorder = Recorder()

    console = open_desktop_console(guest, VM, secrets=["s3cret-token"], emit=recorder)

    assert console.secrets == ("s3cret-token",)
    assert b"public static class OslabConsole" in guest.uploads["C:\\Oslab\\screen\\OslabConsole.cs"]
    setup = guest.commands[-1][0][-1]
    assert "csc.exe" in setup
    assert recorder.phases == ["desktop.console.setup.done"]


class WindowsGuest:
    """A Windows guest for run_windows_artifact: answers preflight commands and keeps uploaded files."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.commands: list[list[str]] = []

    def execute(self, vm, command, *, timeout_seconds, poll_interval_seconds=1.0):
        self.commands.append(list(command))
        return ok("True\r\n")

    def upload_bytes(self, vm, guest_path, content, *, progress=None):
        self.files[guest_path] = content
        return GuestFileWriteResult(guest_path=guest_path, bytes_written=len(content))

    def upload_text(self, vm, guest_path, content, *, encoding="utf-8"):
        return self.upload_bytes(vm, guest_path, content.encode(encoding))

    def download_text(self, vm, guest_path):
        return GuestFileReadResult(guest_path=guest_path, content=self.files[guest_path].decode("utf-8"))


class ShownCommands:
    """Stands in for the desktop console: answers the agent steps and records their window labels."""

    def __init__(self, guest: WindowsGuest) -> None:
        self.guest = guest
        self.labels: list[str] = []

    def command_channel(self, label: str):
        self.labels.append(label)
        return self

    def execute(self, vm, command, *, timeout_seconds, poll_interval_seconds=1.0):
        if " scan " in command[-1]:
            inventory = {"schemaVersion": 1, "kind": "inventory", "records": [{"name": "Demo Agent", "sources": ["DemoAgent"]}]}
            self.guest.files["C:\\Oslab\\inventory.json"] = json.dumps(inventory).encode("utf-8")
        return ok(json.dumps({"ok": True}) + "\r\n")


SCENARIO_YAML = r"""
schemaVersion: 1
id: desktop.session.windows
os:
  family: windows
provider:
  type: proxmox
  templateVmId: 9099
  vmIdRange: {start: 9190, end: 9194}
guest:
  mode: qemuAgent
  screen:
    signIn: true
    showCommands: true
artifact:
  type: folder
  pathParam: artifactPath
  destination: 'C:\Oslab\artifact'
product:
  steps:
    - id: register
      command: {shell: powershell, template: '& "{ArtifactDir}\agent.ps1" register -Json'}
      captureStdoutJson: true
    - id: scan
      command: {shell: powershell, template: '& "{ArtifactDir}\agent.ps1" scan -Output "{OutputPath}" -Json'}
      captureStdoutJson: true
outputs:
  actual:
    path: 'C:\Oslab\inventory.json'
    adapter: canonical.inventory
assertions:
  - type: inventory.contains
    id: demo-agent-record
    match: {name: Demo Agent}
"""


def run_desktop_scenario(tmp_path: Path, monkeypatch, *, signed_in: bool):
    scenario_path = tmp_path / "desktop.yaml"
    scenario_path.write_text(SCENARIO_YAML, encoding="utf-8")
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "agent.ps1").write_text("param($Action)\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    for child in ("logs", "raw", "normalized", "reports"):
        (run_dir / child).mkdir(parents=True)
    guest = WindowsGuest()
    shown = ShownCommands(guest)
    calls: list[str] = []

    def fake_sign_in(channel, vm, *, emit):
        calls.append("signIn")
        return GuestPreflightCheck("desktop.sign_in", signed_in, "Signed in" if signed_in else "Timed out")

    def fake_open_console(channel, vm, *, secrets, emit):
        calls.append("openConsole")
        return shown

    monkeypatch.setattr(proxmox_artifact_smoke, "sign_in_desktop", fake_sign_in)
    monkeypatch.setattr(proxmox_artifact_smoke, "open_desktop_console", fake_open_console)
    result = proxmox_artifact_smoke.run_windows_artifact(
        guest,
        VM,
        scenario=load_scenario(scenario_path),
        oslab_config=OslabConfig(path=None, raw={"runDefaults": {"outputRoot": str(tmp_path / "runs")}}),
        artifact_path=artifact,
        command_timeout_seconds=120,
        run_dir=run_dir,
    )
    return result, guest, shown, calls


def test_run_signs_in_before_preflight_and_shows_product_steps(tmp_path: Path, monkeypatch) -> None:
    result, guest, shown, calls = run_desktop_scenario(tmp_path, monkeypatch, signed_in=True)

    assert result.passed is True, result.message
    assert calls == ["signIn", "openConsole"]
    assert [check.id for check in result.guest_checks][:3] == ["desktop.sign_in", "powershell.version", "windows.admin"]
    assert shown.labels == ["register", "scan"]
    assert not any("agent.ps1" in part for command in guest.commands for part in command)


def test_run_stops_when_the_desktop_sign_in_fails(tmp_path: Path, monkeypatch) -> None:
    result, guest, shown, calls = run_desktop_scenario(tmp_path, monkeypatch, signed_in=False)

    assert result.passed is False
    assert result.message == "Desktop sign-in failed"
    assert proxmox_artifact_smoke.artifact_failure_class(result) == "preflight_failure"
    assert calls == ["signIn"]
    assert guest.commands == []
    assert shown.labels == []


CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")


@pytest.mark.skipif(sys.platform != "win32" or not CSC.exists(), reason="needs the .NET Framework C# compiler")
def test_console_helper_compiles_and_returns_exact_bounded_chunks(tmp_path: Path) -> None:
    source = Path(windows_desktop_session.__file__).with_name("windows_desktop_console.cs")
    helper = tmp_path / "OslabConsole.exe"
    compiled = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{helper}", str(source)],
        capture_output=True,
        text=True,
    )
    assert compiled.returncode == 0, compiled.stdout

    attempt = uuid4().hex
    folder = tmp_path / f"command-{attempt}"
    folder.mkdir()
    content = b"1234" + "試".encode() + bytes(range(256))
    (folder / "stdout.bin").write_bytes(content)
    chunk = subprocess.run([str(helper), "read", attempt, "stdout", "4", "19"], capture_output=True, check=True)
    assert base64.b64decode(chunk.stdout.strip(), validate=True) == content[4:23]

    missing_bytes = subprocess.run([str(helper), "read", attempt, "stdout", "4", str(len(content))], capture_output=True)
    assert missing_bytes.returncode != 0
    assert missing_bytes.stdout == b""

    excessive_bytes = subprocess.run([str(helper), "read", attempt, "stdout", "0", "12289"], capture_output=True)
    assert excessive_bytes.returncode != 0
    assert excessive_bytes.stdout == b""

    probe_source = tmp_path / "PreviewProbe.cs"
    probe = tmp_path / "PreviewProbe.exe"
    probe_source.write_text(r"""
using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text;

class PreviewProbe {
    static void Main(string[] args) {
        var console = Assembly.LoadFrom(args[0]).GetType("OslabConsole", true);
        var output = console.GetMethod("ShowOutput", BindingFlags.NonPublic | BindingFlags.Static);
        output.Invoke(null, new Object[] {
            args[1], null, Encoding.GetEncoding(949), new List<String> { "secret\r\nmultiline" }
        });
    }
}
""", encoding="utf-8")
    compiled = subprocess.run([str(CSC), "/nologo", f"/out:{probe}", str(probe_source)], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stdout
    preview_path = folder / "preview.bin"
    prefix = "x" * (4096 - len("secret\r"))
    preview_path.write_bytes((prefix + "secret\r\nmultiline end").encode())
    preview = subprocess.run([str(probe), str(helper), str(preview_path)], capture_output=True, check=True)
    assert preview.stdout.decode("ascii") == prefix + "<redacted> end"
