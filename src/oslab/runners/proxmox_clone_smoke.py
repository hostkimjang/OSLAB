"""Proxmox clone smoke runner."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from oslab.config import OslabConfig
from oslab.errors import ProviderError
from oslab.models.scenario import Scenario
from oslab.providers.base import TemplateRef, VmRef, VmSpec, VmStatus
from oslab.providers.proxmox import ProxmoxClient, ProxmoxConfig, ProxmoxProvider
from oslab.providers.proxmox_checks import ProxmoxResourceCheck, check_proxmox_resources
from oslab.providers.vmid import LocalVmidLock, VmidRange, VmidReservation, used_vmids_from_resources


@dataclass(frozen=True)
class CloneSmokeResult:
    vm: VmRef
    status: VmStatus | None
    clone_name: str
    destroyed: bool
    kept: bool


def run_proxmox_clone_smoke(
    *,
    scenario: Scenario,
    oslab_config: OslabConfig,
    proxmox_config: ProxmoxConfig,
    vm_id: int | None = None,
    keep_vm: bool = False,
    full_clone: bool = False,
) -> CloneSmokeResult:
    """Create one clone from the scenario template, inspect it, and cleanup by default."""

    if scenario.template_vm_id is None:
        raise ProviderError("Scenario provider.templateVmId is required for clone smoke")
    if scenario.vmid_range is None and vm_id is None:
        raise ProviderError("Scenario provider.vmIdRange is required when --vm-id is not supplied")

    client = ProxmoxClient(proxmox_config)
    provider = ProxmoxProvider(client)
    resource_check = check_proxmox_resources(client, scenario, proxmox_config)
    if not resource_check.passed:
        raise ProviderError(
            "Proxmox resource preflight failed before clone smoke",
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
    status: VmStatus | None = None
    destroyed = False
    try:
        vm = provider.create_clone(
            TemplateRef(vm_id=scenario.template_vm_id, name=scenario.template_name),
            VmSpec(vm_id=selected_vm_id, name=clone_name, full_clone=full_clone),
        )
        status = provider.get_vm_status(vm)
        if keep_vm:
            return CloneSmokeResult(vm=vm, status=status, clone_name=clone_name, destroyed=False, kept=True)
        provider.destroy_vm(vm)
        destroyed = True
        return CloneSmokeResult(vm=vm, status=status, clone_name=clone_name, destroyed=destroyed, kept=False)
    finally:
        if reservation is not None:
            reservation.release()


def make_clone_name(scenario_id: str, vm_id: int) -> str:
    safe = re.sub(r"[^a-zA-Z0-9-]+", "-", scenario_id).strip("-").lower()
    base = f"oslab-{safe}"
    max_base_len = 50
    if len(base) > max_base_len:
        base = base[:max_base_len].rstrip("-")
    return f"{base}-{vm_id}"

