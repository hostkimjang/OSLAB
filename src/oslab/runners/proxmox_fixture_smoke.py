"""Windows fixture upload/execution smoke runner over Proxmox QEMU Guest Agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
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

FIXTURE_ROOT = "C:\\Oslab\\fixtures"


@dataclass(frozen=True)
class FixtureSmokeItem:
    id: str
    fixture_type: str
    source: Path
    guest_path: str
    expected_output: str | None
    uploaded_bytes: int
    exit_code: int | None
    stdout: str
    stderr: str
    collected_bytes: int | None = None
    collected_json: dict[str, Any] | list[Any] | None = None
    local_output_path: Path | None = None
    passed: bool = True
    message: str = "Fixture smoke passed"


@dataclass(frozen=True)
class FixtureSmokeResult:
    vm: VmRef
    clone_name: str
    status: VmStatus
    guest_info: GuestInfo
    fixtures: list[FixtureSmokeItem]
    started: bool
    destroyed: bool
    kept: bool

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.fixtures)


def run_proxmox_fixture_smoke(
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
) -> FixtureSmokeResult:
    """Clone/start a Windows VM, upload scenario fixtures, execute them, collect expected outputs."""

    if scenario.os_family != "windows":
        raise OslabError("Proxmox fixture smoke currently supports Windows scenarios only")
    if scenario.template_vm_id is None:
        raise ProviderError("Scenario provider.templateVmId is required for fixture smoke")
    if scenario.vmid_range is None and vm_id is None:
        raise ProviderError("Scenario provider.vmIdRange is required when --vm-id is not supplied")

    fixtures = _scenario_fixtures(scenario)
    if not fixtures:
        raise OslabError("Scenario does not define any fixtures")

    client = ProxmoxClient(proxmox_config)
    provider = ProxmoxProvider(client)
    resource_check = check_proxmox_resources(client, scenario, proxmox_config)
    if not resource_check.passed:
        raise ProviderError(
            "Proxmox resource preflight failed before fixture smoke",
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
        fixture_results = run_windows_fixtures(
            QemuAgentChannel(client),
            vm,
            scenario=scenario,
            oslab_config=oslab_config,
            command_timeout_seconds=command_timeout_seconds,
        )

        if keep_vm:
            return FixtureSmokeResult(
                vm=vm,
                clone_name=clone_name,
                status=status,
                guest_info=guest_info,
                fixtures=fixture_results,
                started=started,
                destroyed=False,
                kept=True,
            )
        provider.stop_vm(vm)
        provider.destroy_vm(vm)
        destroyed = True
        return FixtureSmokeResult(
            vm=vm,
            clone_name=clone_name,
            status=status,
            guest_info=guest_info,
            fixtures=fixture_results,
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


def run_windows_fixtures(
    channel: QemuAgentChannel,
    vm: VmRef,
    *,
    scenario: Scenario,
    oslab_config: OslabConfig,
    command_timeout_seconds: int,
    run_dir: Path | None = None,
) -> list[FixtureSmokeItem]:
    mkdir = channel.execute(
        vm,
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f"New-Item -ItemType Directory -Force -Path {FIXTURE_ROOT} | Out-Null",
        ],
        timeout_seconds=command_timeout_seconds,
    )
    if not mkdir.passed:
        raise OslabError(
            "Failed to create guest fixture directory",
            details={"exitCode": mkdir.exit_code, "stdout": mkdir.stdout, "stderr": mkdir.stderr},
        )

    results: list[FixtureSmokeItem] = []
    for fixture in _scenario_fixtures(scenario):
        results.append(
            _run_fixture(
                channel,
                vm,
                fixture=fixture,
                scenario=scenario,
                oslab_config=oslab_config,
                command_timeout_seconds=command_timeout_seconds,
                run_dir=run_dir,
            )
        )
    return results


def _run_fixture(
    channel: QemuAgentChannel,
    vm: VmRef,
    *,
    fixture: dict[str, Any],
    scenario: Scenario,
    oslab_config: OslabConfig,
    command_timeout_seconds: int,
    run_dir: Path | None = None,
) -> FixtureSmokeItem:
    fixture_id = str(fixture["id"])
    fixture_type = str(fixture["type"])
    source = _resolve_repo_path(scenario.path.parent.parent.parent, str(fixture["source"]))
    if not source.exists() or not source.is_file():
        raise OslabError(f"Fixture source does not exist: {source}", details={"fixtureId": fixture_id, "source": str(source)})
    if fixture_type != "powershell":
        raise OslabError(f"Unsupported Windows fixture type for fixture smoke: {fixture_type}", details={"fixtureId": fixture_id})

    guest_path = f"{FIXTURE_ROOT}\\{source.name}"
    upload = channel.upload_bytes(vm, guest_path, source.read_bytes())
    command = channel.execute(
        vm,
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            guest_path,
        ],
        timeout_seconds=command_timeout_seconds,
    )

    expected_output = fixture.get("expectedOutput")
    collected_bytes: int | None = None
    collected_json: dict[str, Any] | list[Any] | None = None
    local_output_path: Path | None = None
    passed = command.passed
    message = "Fixture smoke passed" if command.passed else "Fixture command failed"

    if command.passed and isinstance(expected_output, str) and expected_output.strip():
        download = channel.download_text(vm, expected_output)
        collected_bytes = download.bytes_read
        try:
            collected_json = json.loads(download.content.lstrip("\ufeff"))
        except json.JSONDecodeError as exc:
            passed = False
            message = "Expected output was not valid JSON"
            collected_json = None
            json_error = {"jsonError": str(exc)}
        else:
            json_error = {}
        local_output_path = _write_fixture_output(
            oslab_config.output_root,
            scenario.scenario_id,
            fixture_id,
            download.content,
            run_dir=run_dir,
        )
    else:
        json_error = {}

    item = FixtureSmokeItem(
        id=fixture_id,
        fixture_type=fixture_type,
        source=source,
        guest_path=guest_path,
        expected_output=expected_output if isinstance(expected_output, str) else None,
        uploaded_bytes=upload.bytes_written,
        exit_code=command.exit_code,
        stdout=command.stdout,
        stderr=command.stderr,
        collected_bytes=collected_bytes,
        collected_json=collected_json,
        local_output_path=local_output_path,
        passed=passed,
        message=message,
    )
    if json_error:
        return FixtureSmokeItem(
            **{
                **item.__dict__,
                "collected_json": json_error,
            }
        )
    return item


def _scenario_fixtures(scenario: Scenario) -> list[dict[str, Any]]:
    fixtures = scenario.raw.get("fixtures") or []
    return [item for item in fixtures if isinstance(item, dict)]


def _resolve_repo_path(repo_root: Path, path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return repo_root / candidate


def _write_fixture_output(
    output_root: Path,
    scenario_id: str,
    fixture_id: str,
    content: str,
    *,
    run_dir: Path | None = None,
) -> Path:
    output_dir = output_root / "fixture-smoke" / scenario_id if run_dir is None else run_dir / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / (
        f"{fixture_id}.expected_inventory.json" if run_dir is None else f"fixture-{fixture_id}.expected-output.json"
    )
    path.write_bytes(content.encode("utf-8"))
    return path
