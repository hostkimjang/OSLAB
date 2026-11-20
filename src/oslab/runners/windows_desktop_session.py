"""Signed-in Windows desktop session for scenarios with `guest.screen`.

`sign_in_desktop()` creates a local test account, signs it in through automatic logon and
removes the stored logon password again. `open_desktop_console()` compiles a small console helper in
the guest so product commands run in a visible console window of that session while OSLab still
collects their exit code, stdout and stderr.
"""

from __future__ import annotations

import base64
import binascii
import json
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib import resources
from uuid import uuid4

from oslab.errors import OslabError, ProviderError
from oslab.guests.base import GuestCommandResult
from oslab.guests.qemu_agent import QemuAgentChannel
from oslab.providers.base import VmRef
from oslab.runners.proxmox_guest_preflight import GuestPreflightCheck

DESKTOP_USER = "OslabDesktop"
CONSOLE_FOLDER = "C:\\Oslab\\screen"
CONSOLE_HELPER = CONSOLE_FOLDER + "\\OslabConsole.exe"
# Every console window opens at this rectangle (pixels) so recordings can frame it.
CONSOLE_WINDOW = {"left": 120, "top": 80, "width": 1040, "height": 620}
# The window uses the first of these fonts that the console accepts, 24 px high (about 80 columns).
CONSOLE_FONT_NAMES = ("Consolas", "Cascadia Mono")
CONSOLE_FONT_SIZE = 24
# Each wait of the sign-in (guest commands, restart, desktop session) may take this long.
WAIT_TIMEOUT_SECONDS = 300
# Time the helper may need on top of the command timeout to start the console and return the result.
CONSOLE_START_SECONDS = 60
CONSOLE_LINGER_SECONDS = 120
CONSOLE_READ_BYTES = 12_288

Emit = Callable[..., None]

SIGN_IN_GUARD = r"""
$winlogon = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
$marker = Join-Path $env:windir "Temp\oslab-desktop-$attempt"
function Invoke-LogonUpdate([scriptblock]$action) {
    $mutex = New-Object System.Threading.Mutex($false, 'Global\OSLabDesktopLogon')
    $held = $false
    try {
        try { $held = $mutex.WaitOne(15000) }
        catch [System.Threading.AbandonedMutexException] { $held = $true }
        if (-not $held) { throw 'The desktop logon update is busy' }
        & $action
    } finally {
        if ($held) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}
"""

ARM_SIGN_IN_SCRIPT = SIGN_IN_GUARD + r"""
$ErrorActionPreference = 'Stop'
New-Item -ItemType File -Path $marker | Out-Null
"""

SIGN_IN_SCRIPT = SIGN_IN_GUARD + r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
function Set-DWord($path, $name, $value) {
    if (-not (Test-Path -LiteralPath $path)) { New-Item -Path $path -Force | Out-Null }
    New-ItemProperty -LiteralPath $path -Name $name -PropertyType DWord -Value $value -Force | Out-Null
}
# The password is generated and used inside the guest only. Nothing in this script prints it.
$bytes = New-Object byte[] 24
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$password = 'Os9!' + [Convert]::ToBase64String($bytes)
$secure = ConvertTo-SecureString $password -AsPlainText -Force
$account = Get-LocalUser -Name $user -ErrorAction SilentlyContinue
if ($account) {
    Set-LocalUser -Name $user -Password $secure -PasswordNeverExpires $true
    Enable-LocalUser -Name $user
} else {
    $account = New-LocalUser -Name $user -Password $secure -PasswordNeverExpires -AccountNeverExpires -Description 'OSLab desktop session'
}
try { Add-LocalGroupMember -SID 'S-1-5-32-544' -Member $account } catch [Microsoft.PowerShell.Commands.MemberExistsException] { }

# Skip the first sign-in animation and the privacy questions, and keep OneDrive and consumer offers away.
Set-DWord 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon' EnableFirstLogonAnimation 0
Set-DWord 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' EnableFirstLogonAnimation 0
Set-DWord 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\OOBE' DisablePrivacyExperience 1
Set-DWord 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\OneDrive' DisableFileSyncNGSC 1
Set-DWord 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent' DisableWindowsConsumerFeatures 1
# Keep the display on and the VM awake while someone watches the desktop.
foreach ($setting in 'monitor-timeout-ac', 'monitor-timeout-dc', 'standby-timeout-ac', 'standby-timeout-dc') {
    & powercfg.exe /change $setting 0
}

# A new profile starts from the default user hive: no toasts, no setup reminders, no Start menu on the
# first sign-in, no OneDrive setup, and the classic console host that OSLab can place on the screen.
$defaultProfile = [Environment]::ExpandEnvironmentVariables((Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList').Default)
& reg.exe load 'HKU\OslabDefaultUser' (Join-Path $defaultProfile 'NTUSER.DAT') | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not load the default user profile' }
try {
    $hive = 'Registry::HKEY_USERS\OslabDefaultUser'
    Set-DWord "$hive\Software\Microsoft\Windows\CurrentVersion\PushNotifications" ToastEnabled 0
    Set-DWord "$hive\Software\Microsoft\Windows\CurrentVersion\UserProfileEngagement" ScoobeSystemSettingEnabled 0
    Set-DWord "$hive\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager" SubscribedContent-310093Enabled 0
    Set-DWord "$hive\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager" SoftLandingEnabled 0
    Set-DWord "$hive\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced" StartShownOnUpgrade 1
    Remove-ItemProperty -LiteralPath "$hive\Software\Microsoft\Windows\CurrentVersion\Run" -Name OneDriveSetup -ErrorAction SilentlyContinue
    $console = "$hive\Console\%%Startup"
    if (-not (Test-Path -LiteralPath $console)) { New-Item -Path $console -Force | Out-Null }
    New-ItemProperty -LiteralPath $console -Name DelegationConsole -Value '{B23D10C0-E52E-411E-9D5B-C09FDF709C7D}' -Force | Out-Null
    New-ItemProperty -LiteralPath $console -Name DelegationTerminal -Value '{B23D10C0-E52E-411E-9D5B-C09FDF709C7D}' -Force | Out-Null
} finally {
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
    & reg.exe unload 'HKU\OslabDefaultUser' | Out-Null
}

Invoke-LogonUpdate {
    if (-not (Test-Path -LiteralPath $marker)) { throw 'The desktop logon request was cancelled' }
    Remove-Item -LiteralPath $marker
    Set-ItemProperty -LiteralPath $winlogon -Name DefaultUserName -Value $user
    Set-ItemProperty -LiteralPath $winlogon -Name DefaultDomainName -Value $env:COMPUTERNAME
    Set-ItemProperty -LiteralPath $winlogon -Name DefaultPassword -Value $password
    Set-DWord $winlogon AutoLogonCount 1
    Set-ItemProperty -LiteralPath $winlogon -Name AutoAdminLogon -Value '1'
}
(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')
"""

RESTART_COMMAND = ["shutdown.exe", "/r", "/t", "2", "/f", "/d", "p:4:1"]

BOOT_TIME_SCRIPT = "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')"

# Explorer runs for the user and the sign-in screen and first sign-in animation are gone.
DESKTOP_READY_SCRIPT = r"""
$shell = Get-Process explorer -IncludeUserName -ErrorAction SilentlyContinue | Where-Object UserName -like "*\$user"
$busy = Get-Process LogonUI, FirstLogonAnim -ErrorAction SilentlyContinue
if ($shell -and -not $busy) { 'ready' } else { 'waiting' }
"""

# Windows may open the Start menu on a first sign-in. It would cover the console windows.
CLOSE_START_MENU_SCRIPT = r"""
Get-Process StartMenuExperienceHost -IncludeUserName -ErrorAction SilentlyContinue |
    Where-Object UserName -like "*\$user" | Stop-Process -Force -ErrorAction SilentlyContinue
"""

REMOVE_PASSWORD_SCRIPT = SIGN_IN_GUARD + r"""
$ErrorActionPreference = 'Stop'
Invoke-LogonUpdate {
    if (Test-Path -LiteralPath $marker) { Remove-Item -LiteralPath $marker }
    $key = Get-Item -LiteralPath $winlogon
    if ($key.GetValue('DefaultUserName') -eq $user) {
        Remove-ItemProperty -LiteralPath $winlogon -Name DefaultPassword -ErrorAction SilentlyContinue
        Remove-ItemProperty -LiteralPath $winlogon -Name AutoLogonCount -ErrorAction SilentlyContinue
        Set-ItemProperty -LiteralPath $winlogon -Name AutoAdminLogon -Value '0'
    }
    $key = Get-Item -LiteralPath $winlogon
    if ($key.GetValueNames() -contains 'DefaultPassword' -or $key.GetValue('AutoAdminLogon') -eq '1') {
        'present'
    } else {
        'removed'
    }
}
"""

CONSOLE_SETUP_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$compiler = Join-Path ([Runtime.InteropServices.RuntimeEnvironment]::GetRuntimeDirectory()) 'csc.exe'
$output = & $compiler /nologo /target:exe /optimize+ "/out:$folder\OslabConsole.exe" "$folder\OslabConsole.cs" 2>&1
if ($LASTEXITCODE -ne 0) { throw ('Compiling the desktop console failed: ' + ($output -join ' ')) }
"""

COMMAND_PATHS = r"""
$ErrorActionPreference = 'Stop'
$taskName = "Console-$attempt"
$commandFolder = Join-Path $folder "command-$attempt"
"""

REGISTER_COMMAND_SCRIPT = COMMAND_PATHS + r"""
# Only SYSTEM and the elevated desktop task can read the command specification and raw streams.
$acl = New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true, $false)
foreach ($sid in 'S-1-5-18', 'S-1-5-32-544') {
    $identity = New-Object System.Security.Principal.SecurityIdentifier($sid)
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
}
[System.IO.Directory]::CreateDirectory($commandFolder, $acl) | Out-Null
$action = New-ScheduledTaskAction -Execute "$folder\OslabConsole.exe" -Argument "show $attempt"
$principal = New-ScheduledTaskPrincipal -UserId "$env:COMPUTERNAME\$user" -LogonType Interactive -RunLevel Highest
# Priority 5 keeps the command at normal process priority, as under QEMU Guest Agent.
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::FromSeconds($limit)) -Priority 5
Register-ScheduledTask -TaskPath '\OSLab\' -TaskName $taskName -Action $action -Principal $principal -Settings $settings | Out-Null
"""

CLEAN_COMMAND_SCRIPT = COMMAND_PATHS + r"""
function Get-CommandTask {
    Get-ScheduledTask | Where-Object { $_.TaskPath -eq '\OSLab\' -and $_.TaskName -eq $taskName }
}
try {
    $task = Get-CommandTask
    if ($task) {
        if ($abortCommand) {
            $task | Disable-ScheduledTask | Out-Null
            $task | Stop-ScheduledTask
        }
        $task | Unregister-ScheduledTask -Confirm:$false
    }
} finally {
    if (Test-Path -LiteralPath $commandFolder) {
        Remove-Item -LiteralPath $commandFolder -Recurse -Force
    }
}
if ((Get-CommandTask) -or (Test-Path -LiteralPath $commandFolder)) {
    throw 'The desktop console command resources remain'
}
"""


def sign_in_desktop(
    channel: QemuAgentChannel,
    vm: VmRef,
    *,
    emit: Emit,
    poll_interval_seconds: float = 3.0,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> GuestPreflightCheck:
    """Sign the desktop test account in through automatic logon and report it as the `desktop.sign_in` check.

    The automatic logon password is removed from the registry again, also when the sign-in fails.
    """

    emit("desktop.signin.start", "Sign in to the Windows desktop", user=DESKTOP_USER)
    started = monotonic()
    failure: OslabError | None = None
    attempt = uuid4().hex
    cleanup_needed = False
    password_removed = False
    waits = {"timeout_seconds": WAIT_TIMEOUT_SECONDS, "poll_interval_seconds": poll_interval_seconds, "sleep": sleep, "monotonic": monotonic}
    try:
        # Right after boot QEMU Guest Agent answers before Windows can start processes promptly.
        _wait_for_guest(channel, vm, "'ready'", lambda value: value == "ready", what="guest commands", **waits)
        cleanup_needed = True
        _run_script(channel, vm, ARM_SIGN_IN_SCRIPT, timeout_seconds=60, attempt=attempt)
        boot_time = _run_script(channel, vm, SIGN_IN_SCRIPT, timeout_seconds=180, attempt=attempt, include_stderr=False)
        emit("desktop.signin.restart", "Restart Windows to sign in automatically")
        restart = channel.execute(vm, RESTART_COMMAND, timeout_seconds=60)
        if not restart.passed:
            raise ProviderError("Could not restart Windows", details={"exitCode": restart.exit_code, "stderr": restart.stderr})
        _wait_for_guest(channel, vm, BOOT_TIME_SCRIPT, lambda value: value not in ("", boot_time), what="Windows to restart", **waits)
        emit("desktop.signin.wait", "Wait for the desktop session", timeoutSeconds=WAIT_TIMEOUT_SECONDS)
        _wait_for_guest(channel, vm, DESKTOP_READY_SCRIPT, lambda value: value == "ready", what="the desktop session", **waits)
        _wait_for_guest(channel, vm, CLOSE_START_MENU_SCRIPT, lambda value: True, what="the Start menu to close", **waits)
    except OslabError as exc:
        failure = exc
    finally:
        if cleanup_needed:
            password_removed = _remove_autologon_password(channel, vm, attempt=attempt, sleep=sleep)
            if not password_removed and (interrupted := sys.exception()) is not None:
                interrupted.add_note("The automatic logon password could not be removed")
    details: dict[str, object] = {
        "user": DESKTOP_USER,
        "seconds": round(monotonic() - started, 1),
        "autologonPasswordRemoved": password_removed,
    }
    if failure is not None:
        details["error"] = failure.details
    elif not password_removed:
        failure = OslabError("The automatic logon password could not be removed")
    if failure is not None:
        emit("desktop.signin.failed", "Windows desktop sign-in failed", reason=failure.message, **details)
        return GuestPreflightCheck("desktop.sign_in", False, failure.message, details=details)
    emit("desktop.signin.done", "Windows desktop is signed in", **details)
    return GuestPreflightCheck("desktop.sign_in", True, "Desktop session is signed in", details=details)


def open_desktop_console(
    channel: QemuAgentChannel,
    vm: VmRef,
    *,
    secrets: Sequence[str],
    emit: Emit,
) -> DesktopConsole:
    """Compile the console helper in the guest so each product command can open its own desktop task.

    `secrets` are masked in the command line and output that the windows show.
    """

    _run_script(channel, vm, "New-Item -ItemType Directory -Force -Path $folder | Out-Null", timeout_seconds=60)
    source = resources.files("oslab.runners").joinpath("windows_desktop_console.cs").read_bytes()
    channel.upload_bytes(vm, CONSOLE_FOLDER + "\\OslabConsole.cs", source)
    _run_script(channel, vm, CONSOLE_SETUP_SCRIPT, timeout_seconds=180)
    emit("desktop.console.setup.done", "Desktop console is ready", **CONSOLE_WINDOW, fontSize=CONSOLE_FONT_SIZE)
    return DesktopConsole(channel=channel, vm=vm, secrets=tuple(secrets), emit=emit)


@dataclass(frozen=True)
class DesktopConsole:
    """Runs product commands in a console window of the signed-in desktop session."""

    channel: QemuAgentChannel
    vm: VmRef
    secrets: tuple[str, ...]
    emit: Emit

    def command_channel(self, label: str) -> ConsoleCommandChannel:
        return ConsoleCommandChannel(console=self, label=label)

    def run(self, command: Sequence[str], *, label: str, timeout_seconds: int) -> GuestCommandResult:
        """Run `command` (the argv QEMU Guest Agent would run) in a window titled "OSLab · <label>"."""

        title = _mask(f"OSLab \u00b7 {label}", self.secrets)
        self.emit("desktop.console.start", "Show the command in the desktop console", title=title, **CONSOLE_WINDOW)
        attempt = uuid4().hex
        completed = False
        try:
            limit = timeout_seconds + CONSOLE_START_SECONDS + CONSOLE_LINGER_SECONDS
            self._script(f"$limit = {limit}\n" + REGISTER_COMMAND_SCRIPT, attempt)
            try:
                self.channel.upload_bytes(
                    self.vm,
                    f"{CONSOLE_FOLDER}\\command-{attempt}\\spec.txt",
                    _console_spec(command, title=title, secrets=self.secrets),
                )
            except OslabError:
                raise ProviderError("Could not upload the desktop console specification", details={"vmId": self.vm.vm_id}) from None
            result = self._result(attempt, timeout_seconds=timeout_seconds)
            outcome = self._collect_result(result, command, title, attempt, timeout_seconds=timeout_seconds)
            completed = True
        finally:
            active_error = sys.exception()
            try:
                self._cleanup(attempt, abort=not completed)
            except ProviderError as cleanup_error:
                if active_error is None:
                    raise
                active_error.add_note(cleanup_error.message)
        return outcome

    def _script(self, script: str, attempt: str) -> str:
        return _run_script(self.channel, self.vm, script, timeout_seconds=60, attempt=attempt, include_stderr=False)

    def _cleanup(self, attempt: str, *, abort: bool) -> None:
        script = f"$abortCommand = ${'true' if abort else 'false'}\n" + CLEAN_COMMAND_SCRIPT
        for _ in range(3):
            try:
                self._script(script, attempt)
                return
            except (OslabError, OSError):
                continue
        raise ProviderError("The desktop console command resources could not be removed", details={"vmId": self.vm.vm_id})

    def _execute_helper(self, argv: list[str], *, timeout_seconds: int) -> str:
        try:
            helper = self.channel.execute(self.vm, [CONSOLE_HELPER, *argv], timeout_seconds=timeout_seconds)
        except OslabError as exc:
            raise ProviderError(
                "The desktop console helper could not complete",
                details={"vmId": self.vm.vm_id, "failureClass": exc.details.get("failureClass", exc.failure_class)},
            ) from None
        if not helper.passed:
            raise ProviderError(
                "The desktop console helper failed",
                details={"vmId": self.vm.vm_id, "exitCode": helper.exit_code},
            )
        return helper.stdout.strip()

    def _result(self, attempt: str, *, timeout_seconds: int) -> dict:
        metadata = self._execute_helper(["start", attempt, str(timeout_seconds)], timeout_seconds=timeout_seconds + CONSOLE_START_SECONDS)
        try:
            result = json.loads(metadata)
            for key in ("stdoutBytes", "stderrBytes", "codePage"):
                if type(result[key]) is not int or result[key] < 0:
                    raise ValueError("invalid result size or code page")
            if type(result["timedOut"]) is not bool or (result["exitCode"] is not None and type(result["exitCode"]) is not int):
                raise ValueError("invalid exit result")
            result["error"] = None if result["error"] is None else _console_text(result["error"])
            dimensions = list(map(int, _console_text(result.pop("window")).split()))
            names = ("left", "top", "width", "height", "screenWidth", "screenHeight")
            if len(dimensions) not in (0, len(names)):
                raise ValueError("invalid window dimensions")
            result["window"] = dict(zip(names, dimensions), font=_console_text(result.pop("font")))
            if result["exitCode"] is not None and type(result["seconds"]) not in (float, int):
                raise ValueError("invalid command duration")
            return result
        except (KeyError, TypeError, ValueError):
            raise ProviderError("The desktop console helper returned an unreadable result", details={"vmId": self.vm.vm_id}) from None

    def _read_stream(self, attempt: str, stream: str, size: int, code_page: int) -> str:
        content = bytearray()
        while len(content) < size:
            length = min(CONSOLE_READ_BYTES, size - len(content))
            chunk = self._execute_helper(
                ["read", attempt, stream, str(len(content)), str(length)],
                timeout_seconds=60,
            )
            try:
                raw = base64.b64decode(chunk, validate=True)
            except binascii.Error:
                raw = b""
            if len(raw) != length:
                raise ProviderError("The desktop console output was incomplete", details={"vmId": self.vm.vm_id, "stream": stream})
            content.extend(raw)
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return content.decode(f"cp{code_page}", errors="replace")
            except LookupError:
                return content.decode("utf-8", errors="replace")

    def _collect_result(
        self, result: dict, command: Sequence[str], title: str, attempt: str, *, timeout_seconds: int
    ) -> GuestCommandResult:
        window = result["window"]
        if result["timedOut"]:
            self.emit("desktop.console.failed", "Desktop console command timed out", title=title, timeoutSeconds=timeout_seconds, **window)
            raise ProviderError(
                f"Timed out waiting for the desktop console command on VM {self.vm.vm_id}",
                details={
                    "failureClass": "guest_execution_timeout",
                    "vmId": self.vm.vm_id,
                    "title": title,
                    "timeoutSeconds": timeout_seconds,
                },
            )
        if result["error"] is not None:
            reason = _mask(result["error"], self.secrets)
            self.emit("desktop.console.failed", "Desktop console could not run the command", title=title, reason=reason, **window)
            raise ProviderError(
                "The desktop console could not run the command",
                details={"vmId": self.vm.vm_id, "title": title, "reason": reason},
            )
        if result["exitCode"] is None:
            raise ProviderError("The desktop console did not report an exit code", details={"vmId": self.vm.vm_id})
        code_page = result["codePage"]
        stdout = self._read_stream(attempt, "stdout", result["stdoutBytes"], code_page)
        stderr = self._read_stream(attempt, "stderr", result["stderrBytes"], code_page)
        self.emit(
            "desktop.console.done",
            "Desktop console command finished",
            title=title,
            exitCode=result["exitCode"],
            seconds=result["seconds"],
            **window,
        )
        return GuestCommandResult(
            command=tuple(command),
            exited=True,
            exit_code=result["exitCode"],
            stdout=stdout,
            stderr=stderr,
            raw={"desktopConsole": {"title": title, **window}},
        )

@dataclass(frozen=True)
class ConsoleCommandChannel:
    """Takes the place of the QEMU Guest Agent channel for one product command."""

    console: DesktopConsole
    label: str

    def execute(
        self,
        vm: VmRef,
        command: Sequence[str],
        *,
        timeout_seconds: int,
        poll_interval_seconds: float = 1.0,
    ) -> GuestCommandResult:
        return self.console.run(command, label=self.label, timeout_seconds=timeout_seconds)


def _console_spec(command: Sequence[str], *, title: str, secrets: Sequence[str]) -> bytes:
    """Describe the command for the console helper: one `key=base64(UTF-8 value)` line per field.

    `arguments` quotes the argv the way QEMU Guest Agent does on Windows, so the command runs unchanged.
    The window shows the shell command with secrets masked, and masks secrets in the output it shows.
    """

    display = _mask(command[-1], secrets)
    fields = [
        ("title", title),
        ("prompt", "PS>" if command[0] == "powershell.exe" else ">"),
        ("display", display),
        ("fileName", command[0]),
        ("arguments", subprocess.list2cmdline(command[1:])),
        *((key, str(value)) for key, value in CONSOLE_WINDOW.items()),
        *(("fontName", name) for name in CONSOLE_FONT_NAMES),
        ("fontSize", str(CONSOLE_FONT_SIZE)),
        *(("redact", secret) for secret in _secret_forms(secrets)),
    ]
    lines = [f"{key}={base64.b64encode(value.encode('utf-8')).decode('ascii')}\n" for key, value in fields]
    return "".join(lines).encode("ascii")


def _console_text(value: str) -> str:
    return base64.b64decode(value, validate=True).decode("utf-8")


def _secret_forms(secrets: Sequence[str]) -> list[str]:
    forms = set()
    for secret in secrets:
        if not secret:
            continue
        lines = secret.replace("\r\n", "\n")
        forms.update((secret, lines, lines.replace("\n", "\r\n")))
    return sorted(forms, key=lambda value: (-len(value), value))


def _mask(text: str, secrets: Sequence[str]) -> str:
    for secret in _secret_forms(secrets):
        text = text.replace(secret, "<redacted>")
    return text


def _run_script(
    channel: QemuAgentChannel, vm: VmRef, script: str, *, timeout_seconds: int, attempt: str = "", include_stderr: bool = True
) -> str:
    """Run a PowerShell script and return its last output line.

    The script can use `$user` (the desktop account) and `$folder` (the console helper folder).
    """

    try:
        result = channel.execute(vm, _powershell(script, attempt=attempt), timeout_seconds=timeout_seconds)
    except OslabError as exc:
        if include_stderr:
            raise
        raise ProviderError(
            "Guest PowerShell script failed", details={"vmId": vm.vm_id, "failureClass": exc.details.get("failureClass", exc.failure_class)}
        ) from None
    if not result.passed:
        details = {"vmId": vm.vm_id, "exitCode": result.exit_code}
        if include_stderr:
            details["stderr"] = result.stderr.strip()
        raise ProviderError("Guest PowerShell script failed", details=details)
    lines = result.stdout.strip().splitlines()
    return lines[-1].strip() if lines else ""


def _powershell(script: str, *, attempt: str) -> list[str]:
    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        f"$user = '{DESKTOP_USER}'\n$folder = '{CONSOLE_FOLDER}'\n$attempt = '{attempt}'\n{script}",
    ]


def _wait_for_guest(
    channel: QemuAgentChannel,
    vm: VmRef,
    script: str,
    is_done: Callable[[str], bool],
    *,
    what: str,
    timeout_seconds: int,
    poll_interval_seconds: float,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
) -> None:
    deadline = monotonic() + timeout_seconds
    while monotonic() < deadline:
        try:
            if is_done(_run_script(channel, vm, script, timeout_seconds=30)):
                return
        except OslabError:
            pass  # QEMU Guest Agent does not answer while Windows restarts or signs in.
        sleep(poll_interval_seconds)
    raise ProviderError(
        f"Timed out waiting for {what}",
        details={"failureClass": "desktop_signin_timeout", "vmId": vm.vm_id, "timeoutSeconds": timeout_seconds},
    )


def _remove_autologon_password(
    channel: QemuAgentChannel, vm: VmRef, *, attempt: str, sleep: Callable[[float], None]
) -> bool:
    for retry in range(3):
        try:
            if _run_script(channel, vm, REMOVE_PASSWORD_SCRIPT, timeout_seconds=60, attempt=attempt, include_stderr=False) == "removed":
                return True
        except (OslabError, OSError):
            pass
        if retry < 2:
            sleep(5)
    return False
