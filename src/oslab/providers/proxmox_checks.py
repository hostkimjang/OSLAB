"""Read-only Proxmox lab preflight checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from oslab.errors import ProviderError
from oslab.models.scenario import Scenario
from oslab.providers.proxmox import ProxmoxClient, ProxmoxConfig
from oslab.providers.vmid import VmidRange, allocate_vmid, used_vmids_from_resources


@dataclass(frozen=True)
class TemplateCheck:
    vm_id: int | None
    expected_name: str | None
    found: bool
    name: str | None = None
    node: str | None = None
    status: str | None = None
    is_template: bool | None = None
    config_error: str | None = None


@dataclass(frozen=True)
class VmidRangeCheck:
    start: int | None
    end: int | None
    used_in_range: list[int] = field(default_factory=list)
    recommended_vmid: int | None = None


@dataclass(frozen=True)
class ProxmoxResourceCheck:
    node: str
    nodes: list[str]
    node_exists: bool
    vm_resource_count: int
    template: TemplateCheck
    vmid_range: VmidRangeCheck
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.issues


def check_proxmox_resources(client: ProxmoxClient, scenario: Scenario, config: ProxmoxConfig) -> ProxmoxResourceCheck:
    """Run read-only checks for node/template/VMID range readiness."""

    issues: list[str] = []
    warnings: list[str] = []

    node_items = client.list_nodes()
    nodes = sorted(str(item["node"]) for item in node_items if "node" in item)
    node_exists = config.node in nodes
    if not node_exists:
        issues.append(f"Configured node `{config.node}` was not found")

    resources = client.list_vm_resources()
    template = _check_template(client, scenario, resources, issues, warnings)
    vmid_range = _check_vmid_range(scenario, resources, issues, warnings)

    return ProxmoxResourceCheck(
        node=config.node,
        nodes=nodes,
        node_exists=node_exists,
        vm_resource_count=len(resources),
        template=template,
        vmid_range=vmid_range,
        issues=issues,
        warnings=warnings,
    )


def _check_template(
    client: ProxmoxClient,
    scenario: Scenario,
    resources: list[dict[str, Any]],
    issues: list[str],
    warnings: list[str],
) -> TemplateCheck:
    template_vmid = scenario.template_vm_id
    expected_name = scenario.template_name
    if template_vmid is None:
        issues.append("Scenario provider.templateVmId is required for Proxmox MVP")
        return TemplateCheck(vm_id=None, expected_name=expected_name, found=False)

    resource = next((item for item in resources if _to_int(item.get("vmid")) == template_vmid), None)
    if resource is None:
        issues.append(f"Template VMID `{template_vmid}` was not found")
        return TemplateCheck(vm_id=template_vmid, expected_name=expected_name, found=False)

    name = _to_optional_str(resource.get("name"))
    node = _to_optional_str(resource.get("node"))
    status = _to_optional_str(resource.get("status"))
    if expected_name and name and expected_name != name:
        warnings.append(f"Template VMID `{template_vmid}` name is `{name}`, scenario expected `{expected_name}`")

    config_error = None
    is_template = _to_bool(resource.get("template"))
    if is_template is None and node:
        try:
            vm_config = client.get_vm_config(template_vmid, node=node)
            is_template = _to_bool(vm_config.get("template"))
        except ProviderError as exc:
            config_error = exc.message
            warnings.append(f"Could not read template VM config for `{template_vmid}`: {exc.message}")

    if is_template is False:
        issues.append(f"VMID `{template_vmid}` exists but is not marked as a template")
    elif is_template is None:
        warnings.append(f"Could not confirm whether VMID `{template_vmid}` is marked as a template")

    return TemplateCheck(
        vm_id=template_vmid,
        expected_name=expected_name,
        found=True,
        name=name,
        node=node,
        status=status,
        is_template=is_template,
        config_error=config_error,
    )


def _check_vmid_range(
    scenario: Scenario,
    resources: list[dict[str, Any]],
    issues: list[str],
    warnings: list[str],
) -> VmidRangeCheck:
    raw_range = scenario.vmid_range
    if raw_range is None:
        warnings.append("Scenario provider.vmIdRange is missing; automatic VMID allocation will be unavailable")
        return VmidRangeCheck(start=None, end=None)

    vmid_range = VmidRange(start=raw_range["start"], end=raw_range["end"])
    used_vmids = used_vmids_from_resources(resources)
    used_in_range = sorted(vm_id for vm_id in used_vmids if vmid_range.start <= vm_id <= vmid_range.end)
    try:
        recommended = allocate_vmid(vmid_range, used_vmids=used_vmids)
    except ProviderError as exc:
        issues.append(exc.message)
        recommended = None

    return VmidRangeCheck(
        start=vmid_range.start,
        end=vmid_range.end,
        used_in_range=used_in_range,
        recommended_vmid=recommended,
    )


def _to_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _to_optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _to_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes"}:
            return True
        if normalized in {"0", "false", "no"}:
            return False
    return None
