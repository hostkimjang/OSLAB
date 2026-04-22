"""Windows guest preflight runner over Proxmox and QEMU Guest Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from oslab.config import OslabConfig
from oslab.errors import OslabError, ProviderError
from oslab.guests.qemu_agent import QemuAgentChannel
from oslab.models.scenario import Scenario
from oslab.providers.base import GuestInfo, TemplateRef, VmRef, VmSpec, VmStatus
from oslab.providers.proxmox import ProxmoxClient, ProxmoxConfig, ProxmoxProvider
from oslab.providers.proxmox_checks import check_proxmox_resources
from oslab.providers.vmid import LocalVmidLock, VmidRange, VmidReservation, used_vmids_from_resources
from oslab.runners.proxmox_boot_smoke import _best_effort_cleanup, wait_for_guest_info, wait_for_vm_status
from oslab.runners.proxmox_clone_smoke import make_clone_name


@dataclass(frozen=True)
class GuestPreflightCheck:
    id: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GuestPreflightResult:
    vm: VmRef
    clone_name: str
    status: VmStatus
    guest_info: GuestInfo
    checks: list[GuestPreflightCheck]
    started: bool
    destroyed: bool
    kept: bool

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


def run_proxmox_guest_preflight(
    *,
    scenario: Scenario,
    oslab_config: OslabConfig,
    proxmox_config: ProxmoxConfig,
    vm_id: int | None = None,
    keep_vm: bool = False,
    full_clone: bool = False,
    boot_timeout_seconds: int = 300,
    guest_timeout_seconds: int = 300,
    command_timeout_seconds: int = 60,
    poll_interval_seconds: float = 5.0,
) -> GuestPreflightResult:
    """Clone/start a Windows VM and verify basic guest command/file readiness."""

    if scenario.os_family != "windows":
        raise OslabError("Proxmox guest preflight currently supports Windows scenarios only")
    if scenario.template_vm_id is None:
        raise ProviderError("Scenario provider.templateVmId is required for guest preflight")
    if scenario.vmid_range is None and vm_id is None:
        raise ProviderError("Scenario provider.vmIdRange is required when --vm-id is not supplied")

    client = ProxmoxClient(proxmox_config)
    provider = ProxmoxProvider(client)
    resource_check = check_proxmox_resources(client, scenario, proxmox_config)
    if not resource_check.passed:
        raise ProviderError(
            "Proxmox resource preflight failed before guest preflight",
            details={"issues": resource_check.issues, "warnings": resource_check.warnings},
        )

    resources = client.list_vm_resources()
    used_vmids = used_vmids_from_resources(resources)
    reservation: VmidReservation | None = None
    selected_vm_id = vm_id
    if selected_vm_id is None:
        raw_range = scenario.vmid_range
        assert raw_range is not None
        reservation = LocalVmidLock(oslab_config.output_root / ".locks").reserve(
            VmidRange(start=raw_range["start"], end=raw_range["end"]),
            used_vmids=used_vmids,
        )
        selected_vm_id = reservation.vm_id
    elif selected_vm_id in used_vmids:
        raise ProviderError(f"Requested VMID `{selected_vm_id}` is already in use")

    clone_name = make_clone_name(scenario.scenario_id, selected_vm_id)
    vm = VmRef(vm_id=selected_vm_id, name=clone_name, node=proxmox_config.node)
    started = False
    destroyed = False
    try:
        vm = provider.create_clone(
            TemplateRef(vm_id=scenario.template_vm_id, name=scenario.template_name),
            VmSpec(vm_id=selected_vm_id, name=clone_name, full_clone=full_clone),
        )
        provider.start_vm(vm)
        started = True
        status = wait_for_vm_status(
            provider,
            vm,
            expected_status="running",
            timeout_seconds=boot_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        guest_info = wait_for_guest_info(
            provider,
            vm,
            timeout_seconds=guest_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )

        checks = run_windows_guest_checks(
            QemuAgentChannel(client),
            vm,
            command_timeout_seconds=command_timeout_seconds,
        )

        if keep_vm:
            return GuestPreflightResult(
                vm=vm,
                clone_name=clone_name,
                status=status,
                guest_info=guest_info,
                checks=checks,
                started=started,
                destroyed=False,
                kept=True,
            )
        provider.stop_vm(vm)
        provider.destroy_vm(vm)
        destroyed = True
        return GuestPreflightResult(
            vm=vm,
            clone_name=clone_name,
            status=status,
            guest_info=guest_info,
            checks=checks,
            started=started,
            destroyed=destroyed,
            kept=False,
        )
    except Exception:
        if not keep_vm:
            _best_effort_cleanup(provider, vm, started=started)
        raise
    finally:
        if reservation is not None:
            reservation.release()


def run_windows_guest_checks(
    channel: QemuAgentChannel,
    vm: VmRef,
    *,
    command_timeout_seconds: int,
) -> list[GuestPreflightCheck]:
    checks: list[GuestPreflightCheck] = []
    checks.append(
        _run_command_check(
            channel,
            vm,
            check_id="powershell.version",
            command=[
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "$PSVersionTable.PSVersion.ToString()",
            ],
            timeout_seconds=command_timeout_seconds,
            require_stdout=True,
        )
    )
    checks.append(
        _run_command_check(
            channel,
            vm,
            check_id="windows.admin",
            command=[
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)",
            ],
            timeout_seconds=command_timeout_seconds,
            expected_stdout="True",
        )
    )
    checks.append(
        _run_command_check(
            channel,
            vm,
            check_id="powershell.execution_policy",
            command=[
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "Get-ExecutionPolicy -List | Select-Object Scope,@{Name='ExecutionPolicy';Expression={$_.ExecutionPolicy.ToString()}} | ConvertTo-Json -Compress",
            ],
            timeout_seconds=command_timeout_seconds,
            require_stdout=True,
        )
    )
    checks.append(
        _run_command_check(
            channel,
            vm,
            check_id="oslab.directory",
            command=[
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "New-Item -ItemType Directory -Force -Path C:\\Oslab | Out-Null",
            ],
            timeout_seconds=command_timeout_seconds,
        )
    )
    checks.append(_run_file_roundtrip_check(channel, vm))
    checks.append(
        _run_command_check(
            channel,
            vm,
            check_id="oslab.cleanup_test_file",
            command=[
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "Remove-Item -LiteralPath C:\\Oslab\\oslab-preflight.txt -Force -ErrorAction SilentlyContinue",
            ],
            timeout_seconds=command_timeout_seconds,
        )
    )
    return checks


def _run_command_check(
    channel: QemuAgentChannel,
    vm: VmRef,
    *,
    check_id: str,
    command: list[str],
    timeout_seconds: int,
    require_stdout: bool = False,
    expected_stdout: str | None = None,
) -> GuestPreflightCheck:
    try:
        result = channel.execute(vm, command, timeout_seconds=timeout_seconds)
    except OslabError as exc:
        return GuestPreflightCheck(check_id, False, exc.message, details=exc.details)
    stdout = result.stdout.strip()
    details = {"exitCode": result.exit_code, "stdout": stdout, "stderr": result.stderr.strip()}
    if not result.passed:
        return GuestPreflightCheck(check_id, False, "Command returned non-zero exit code", details=details)
    if require_stdout and not stdout:
        return GuestPreflightCheck(check_id, False, "Command stdout was empty", details=details)
    if expected_stdout is not None and stdout.lower() != expected_stdout.lower():
        return GuestPreflightCheck(check_id, False, f"Expected stdout `{expected_stdout}`", details=details)
    return GuestPreflightCheck(check_id, True, "Command check passed", details=details)


def _run_file_roundtrip_check(channel: QemuAgentChannel, vm: VmRef) -> GuestPreflightCheck:
    guest_path = "C:\\Oslab\\oslab-preflight.txt"
    content = "oslab guest preflight\n"
    try:
        upload = channel.upload_text(vm, guest_path, content)
        download = channel.download_text(vm, guest_path)
    except OslabError as exc:
        return GuestPreflightCheck("oslab.file_roundtrip", False, exc.message, details=exc.details)
    details = {
        "guestPath": guest_path,
        "bytesWritten": upload.bytes_written,
        "bytesRead": download.bytes_read,
    }
    if download.content != content:
        return GuestPreflightCheck("oslab.file_roundtrip", False, "Downloaded content did not match upload", details=details)
    return GuestPreflightCheck("oslab.file_roundtrip", True, "File round-trip check passed", details=details)
