"""Proxmox boot and QEMU Guest Agent smoke runner."""

from __future__ import annotations

import time
from dataclasses import dataclass

from oslab.config import OslabConfig
from oslab.errors import ProviderError
from oslab.models.scenario import Scenario
from oslab.providers.base import GuestInfo, TemplateRef, VmRef, VmSpec, VmStatus
from oslab.providers.proxmox import ProxmoxClient, ProxmoxConfig, ProxmoxProvider
from oslab.providers.proxmox_checks import check_proxmox_resources
from oslab.providers.vmid import LocalVmidLock, VmidRange, VmidReservation, used_vmids_from_resources
from oslab.runners.proxmox_clone_smoke import make_clone_name


@dataclass(frozen=True)
class BootSmokeResult:
    vm: VmRef
    clone_name: str
    status: VmStatus
    guest_info: GuestInfo | None
    started: bool
    destroyed: bool
    kept: bool


def run_proxmox_boot_smoke(
    *,
    scenario: Scenario,
    oslab_config: OslabConfig,
    proxmox_config: ProxmoxConfig,
    vm_id: int | None = None,
    keep_vm: bool = False,
    full_clone: bool = False,
    boot_timeout_seconds: int = 300,
    guest_timeout_seconds: int = 300,
    poll_interval_seconds: float = 5.0,
) -> BootSmokeResult:
    """Clone, start, wait for running state and QEMU Guest Agent, then cleanup."""

    if scenario.template_vm_id is None:
        raise ProviderError("Scenario provider.templateVmId is required for boot smoke")
    if scenario.vmid_range is None and vm_id is None:
        raise ProviderError("Scenario provider.vmIdRange is required when --vm-id is not supplied")

    client = ProxmoxClient(proxmox_config)
    provider = ProxmoxProvider(client)
    resource_check = check_proxmox_resources(client, scenario, proxmox_config)
    if not resource_check.passed:
        raise ProviderError(
            "Proxmox resource preflight failed before boot smoke",
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
        if keep_vm:
            return BootSmokeResult(
                vm=vm,
                clone_name=clone_name,
                status=status,
                guest_info=guest_info,
                started=started,
                destroyed=False,
                kept=True,
            )
        provider.stop_vm(vm)
        provider.destroy_vm(vm)
        destroyed = True
        return BootSmokeResult(
            vm=vm,
            clone_name=clone_name,
            status=status,
            guest_info=guest_info,
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


def wait_for_vm_status(
    provider: ProxmoxProvider,
    vm: VmRef,
    *,
    expected_status: str,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> VmStatus:
    deadline = time.monotonic() + timeout_seconds
    last_status: VmStatus | None = None
    while time.monotonic() <= deadline:
        last_status = provider.get_vm_status(vm)
        if last_status.status == expected_status:
            return last_status
        time.sleep(poll_interval_seconds)
    raise ProviderError(
        f"Timed out waiting for VM {vm.vm_id} status `{expected_status}`",
        details={"lastStatus": last_status.status if last_status else None},
    )


def wait_for_guest_info(
    provider: ProxmoxProvider,
    vm: VmRef,
    *,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> GuestInfo:
    deadline = time.monotonic() + timeout_seconds
    last_error: str | None = None
    last_details: dict | None = None
    while time.monotonic() <= deadline:
        try:
            return provider.get_guest_info(vm)
        except ProviderError as exc:
            last_error = exc.message
            last_details = exc.details
            time.sleep(poll_interval_seconds)
    raise ProviderError(
        f"Timed out waiting for QEMU Guest Agent on VM {vm.vm_id}",
        details={"lastError": last_error, "lastDetails": last_details, "vmId": vm.vm_id},
    )


def _best_effort_cleanup(provider: ProxmoxProvider, vm: VmRef, *, started: bool) -> None:
    try:
        if started:
            provider.stop_vm(vm)
    except Exception:
        pass
    try:
        provider.destroy_vm(vm)
    except Exception:
        pass
