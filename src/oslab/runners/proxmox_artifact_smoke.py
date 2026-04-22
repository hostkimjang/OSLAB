"""Windows artifact upload/execution smoke runner over Proxmox QEMU Guest Agent."""

from __future__ import annotations

import json
import os
import re
import tempfile
import zipfile
from collections.abc import Callable
from fnmatch import fnmatch
from dataclasses import dataclass, field, replace
from pathlib import Path, PureWindowsPath
from typing import Any

from oslab.analysis import analyze_inventory
from oslab.assertions import AssertionResult, evaluate_assertions
from oslab.commands import CommandSpec, render_command_template
from oslab.config import OslabConfig
from oslab.errors import ConfigError, OslabError, ProviderError
from oslab.guests.qemu_agent import QemuAgentChannel
from oslab.models.scenario import Scenario
from oslab.plugins import normalize_output
from oslab.providers.base import GuestInfo, TemplateRef, VmRef, VmSpec, VmStatus
from oslab.providers.proxmox import ProxmoxClient, ProxmoxConfig, ProxmoxProvider
from oslab.providers.proxmox_checks import check_proxmox_resources
from oslab.providers.vmid import LocalVmidLock, VmidRange, VmidReservation, used_vmids_from_resources
from oslab.reports.html import write_artifact_html
from oslab.reports.json_report import write_json
from oslab.reports.junit import JUnitCase, write_junit
from oslab.runners.proxmox_boot_smoke import _best_effort_cleanup, wait_for_guest_info, wait_for_vm_status
from oslab.runners.proxmox_clone_smoke import make_clone_name
from oslab.runners.proxmox_fixture_smoke import FixtureSmokeItem, run_windows_fixtures
from oslab.runners.proxmox_guest_preflight import GuestPreflightCheck, run_windows_guest_checks


@dataclass(frozen=True)
class UploadedArtifactFile:
    local_path: Path
    guest_path: str
    bytes_written: int


@dataclass(frozen=True)
class ProgressEvent:
    phase: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


ProgressCallback = Callable[[ProgressEvent], None]


@dataclass(frozen=True)
class ProductStepResult:
    id: str
    command: CommandSpec
    exit_code: int | None
    stdout: str
    stderr: str
    stdout_json: dict[str, Any] | list[Any] | None
    passed: bool
    message: str


@dataclass(frozen=True)
class ArtifactSmokeResult:
    vm: VmRef
    clone_name: str
    status: VmStatus
    guest_info: GuestInfo
    artifact_path: Path
    artifact_destination: str
    uploaded_files: list[UploadedArtifactFile]
    command: CommandSpec
    exit_code: int | None
    stdout: str
    stderr: str
    output_path: str
    output_adapter: str
    collected_bytes: int | None
    collected_json: dict[str, Any] | list[Any] | None
    local_output_path: Path | None
    normalized_json: dict[str, Any] | None
    local_normalized_path: Path | None
    started: bool
    destroyed: bool
    kept: bool
    passed: bool
    message: str
    install_command: CommandSpec | None = None
    install_exit_code: int | None = None
    install_stdout: str = ""
    install_stderr: str = ""
    product_steps: list[ProductStepResult] = field(default_factory=list)
    local_product_steps_path: Path | None = None
    assertions: list[AssertionResult] = field(default_factory=list)
    local_log_paths: dict[str, Path] = field(default_factory=dict)
    local_report_paths: dict[str, Path] = field(default_factory=dict)
    guest_checks: list[GuestPreflightCheck] = field(default_factory=list)
    fixtures: list[FixtureSmokeItem] = field(default_factory=list)


def run_proxmox_artifact_smoke(
    *,
    scenario: Scenario,
    oslab_config: OslabConfig,
    proxmox_config: ProxmoxConfig,
    artifact_path: Path,
    vm_id: int | None = None,
    keep_vm: bool = False,
    full_clone: bool = False,
    boot_timeout_seconds: int = 300,
    guest_timeout_seconds: int = 300,
    command_timeout_seconds: int = 120,
    poll_interval_seconds: float = 5.0,
    progress: ProgressCallback | None = None,
    run_dir: Path | None = None,
) -> ArtifactSmokeResult:
    """Clone/start a Windows VM, upload artifact files, execute artifact command, collect output JSON."""

    if scenario.os_family != "windows":
        raise OslabError("Proxmox artifact smoke currently supports Windows scenarios only")
    if scenario.template_vm_id is None:
        raise ProviderError("Scenario provider.templateVmId is required for artifact smoke")
    if scenario.vmid_range is None and vm_id is None:
        raise ProviderError("Scenario provider.vmIdRange is required when --vm-id is not supplied")
    if not artifact_path.exists():
        raise OslabError(f"Artifact path does not exist: {artifact_path}", details={"path": str(artifact_path)})

    artifact = _scenario_artifact(scenario)
    if artifact.get("type") not in {"folder", "installer"}:
        raise OslabError("Artifact smoke supports folder and installer artifacts", details={"type": artifact.get("type")})
    _validate_required_product_secret_envs(scenario)

    client = ProxmoxClient(proxmox_config)
    provider = ProxmoxProvider(client)
    _emit_progress(
        progress,
        "provider.preflight.start",
        "Check Proxmox resources",
        node=proxmox_config.node,
        templateVmId=scenario.template_vm_id,
    )
    resource_check = check_proxmox_resources(client, scenario, proxmox_config)
    if not resource_check.passed:
        _emit_progress(
            progress,
            "provider.preflight.failed",
            "Proxmox resource preflight failed",
            issues=len(resource_check.issues),
            warnings=len(resource_check.warnings),
        )
        raise ProviderError(
            "Proxmox resource preflight failed before artifact smoke",
            details={"issues": resource_check.issues, "warnings": resource_check.warnings},
        )
    _emit_progress(
        progress,
        "provider.preflight.done",
        "Proxmox resource preflight passed",
        warnings=len(resource_check.warnings),
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
    _emit_progress(progress, "vm.allocate.done", "VMID allocated", vmId=selected_vm_id)

    clone_name = make_clone_name(scenario.scenario_id, selected_vm_id)
    vm = VmRef(vm_id=selected_vm_id, name=clone_name, node=proxmox_config.node)
    started = False
    destroyed = False
    try:
        _emit_progress(
            progress,
            "vm.clone.start",
            "Create ephemeral VM clone",
            vmId=selected_vm_id,
            cloneName=clone_name,
            fullClone=str(full_clone).lower(),
        )
        vm = provider.create_clone(
            TemplateRef(vm_id=scenario.template_vm_id, name=scenario.template_name),
            VmSpec(vm_id=selected_vm_id, name=clone_name, full_clone=full_clone),
        )
        _emit_progress(progress, "vm.clone.done", "Ephemeral VM clone created", vmId=vm.vm_id, cloneName=vm.name)
        _emit_progress(progress, "vm.start.start", "Start VM", vmId=vm.vm_id)
        provider.start_vm(vm)
        started = True
        _emit_progress(progress, "vm.start.done", "VM start requested", vmId=vm.vm_id)
        _emit_progress(
            progress,
            "vm.boot.wait",
            "Wait for VM running state",
            vmId=vm.vm_id,
            timeoutSeconds=boot_timeout_seconds,
        )
        status = wait_for_vm_status(
            provider,
            vm,
            expected_status="running",
            timeout_seconds=boot_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        _emit_progress(progress, "vm.boot.done", "VM is running", vmId=vm.vm_id, status=status.status)
        _emit_progress(
            progress,
            "guest.ready.wait",
            "Wait for QEMU Guest Agent",
            vmId=vm.vm_id,
            timeoutSeconds=guest_timeout_seconds,
        )
        guest_info = wait_for_guest_info(
            provider,
            vm,
            timeout_seconds=guest_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        _emit_progress(progress, "guest.ready.done", "QEMU Guest Agent is ready", vmId=vm.vm_id)
        result = run_windows_artifact(
            QemuAgentChannel(client),
            vm,
            scenario=scenario,
            oslab_config=oslab_config,
            artifact_path=artifact_path,
            command_timeout_seconds=command_timeout_seconds,
            progress=progress,
            run_dir=run_dir,
        )

        if keep_vm:
            _emit_progress(progress, "cleanup.skipped", "Cleanup skipped because keepVm is enabled", vmId=vm.vm_id)
            final_result = _with_lifecycle(result, status=status, guest_info=guest_info, started=started, destroyed=False, kept=True)
            return _with_report_paths(final_result, _write_artifact_reports(oslab_config.output_root, scenario, final_result, run_dir=run_dir))
        _emit_progress(progress, "vm.stop.start", "Stop VM", vmId=vm.vm_id)
        provider.stop_vm(vm)
        _emit_progress(progress, "vm.stop.done", "VM stopped", vmId=vm.vm_id)
        _emit_progress(progress, "vm.destroy.start", "Destroy VM clone", vmId=vm.vm_id)
        provider.destroy_vm(vm)
        destroyed = True
        _emit_progress(progress, "vm.destroy.done", "VM clone destroyed", vmId=vm.vm_id)
        final_result = _with_lifecycle(result, status=status, guest_info=guest_info, started=started, destroyed=destroyed, kept=False)
        return _with_report_paths(final_result, _write_artifact_reports(oslab_config.output_root, scenario, final_result, run_dir=run_dir))
    except Exception:
        if not keep_vm:
            _emit_progress(progress, "cleanup.best_effort.start", "Run best-effort cleanup", vmId=vm.vm_id)
            _best_effort_cleanup(provider, vm, started=started)
            _emit_progress(progress, "cleanup.best_effort.done", "Best-effort cleanup finished", vmId=vm.vm_id)
        raise
    finally:
        if reservation is not None:
            reservation.release()


def run_windows_artifact(
    channel: QemuAgentChannel,
    vm: VmRef,
    *,
    scenario: Scenario,
    oslab_config: OslabConfig,
    artifact_path: Path,
    command_timeout_seconds: int,
    progress: ProgressCallback | None = None,
    run_dir: Path | None = None,
) -> ArtifactSmokeResult:
    artifact = _scenario_artifact(scenario)
    artifact_type = str(artifact.get("type"))
    destination = str(artifact["destination"])
    output_path = _scenario_output_path(scenario)
    output_adapter = scenario.output_adapter

    command_tokens = {"ArtifactDir": destination, "OutputPath": output_path}
    install_command: CommandSpec | None = None
    install_exit_code: int | None = None
    install_stdout = ""
    install_stderr = ""
    guest_checks: list[GuestPreflightCheck] = []
    fixtures: list[FixtureSmokeItem] = []

    if run_dir is not None:
        guest_checks = _run_full_run_guest_preflight(
            channel,
            vm,
            scenario=scenario,
            command_timeout_seconds=command_timeout_seconds,
            progress=progress,
        )
        if any(not check.passed for check in guest_checks):
            return _early_artifact_result(
                vm,
                scenario=scenario,
                artifact_path=artifact_path,
                artifact_destination=destination,
                output_path=output_path,
                output_adapter=output_adapter,
                message="Guest preflight failed",
                guest_checks=guest_checks,
                fixtures=fixtures,
            )

        if _scenario_fixture_specs(scenario):
            _emit_progress(progress, "fixture.start", "Apply scenario fixtures", fixtures=len(_scenario_fixture_specs(scenario)))
            fixtures = run_windows_fixtures(
                channel,
                vm,
                scenario=scenario,
                oslab_config=oslab_config,
                command_timeout_seconds=command_timeout_seconds,
                run_dir=run_dir,
            )
            for fixture in fixtures:
                _emit_progress(
                    progress,
                    "fixture.done" if fixture.passed else "fixture.failed",
                    "Fixture applied" if fixture.passed else "Fixture failed",
                    fixtureId=fixture.id,
                    exitCode=fixture.exit_code if fixture.exit_code is not None else "<missing>",
                    collectedBytes=fixture.collected_bytes if fixture.collected_bytes is not None else "<none>",
                )
            if any(not fixture.passed for fixture in fixtures):
                return _early_artifact_result(
                    vm,
                    scenario=scenario,
                    artifact_path=artifact_path,
                    artifact_destination=destination,
                    output_path=output_path,
                    output_adapter=output_adapter,
                    message="Fixture failed",
                    guest_checks=guest_checks,
                    fixtures=fixtures,
                )
            _emit_progress(progress, "fixture.all.done", "Scenario fixtures applied", fixtures=len(fixtures))

    if artifact_type == "folder":
        _emit_progress(progress, "artifact.prepare.start", "Prepare artifact directory", destination=destination)
        _ensure_guest_directory(channel, vm, destination, timeout_seconds=command_timeout_seconds)
        _emit_progress(progress, "artifact.prepare.done", "Artifact directory is ready", destination=destination)
        uploaded_files = _upload_folder_artifact(
            channel,
            vm,
            artifact_path,
            destination,
            exclude_patterns=_artifact_exclude_patterns(artifact),
            transfer_mode=_artifact_transfer_mode(artifact),
            command_timeout_seconds=command_timeout_seconds,
            progress=progress,
        )
    elif artifact_type == "installer":
        uploaded_files = [
            _upload_installer_artifact(
                channel,
                vm,
                artifact_path,
                destination,
                command_timeout_seconds=command_timeout_seconds,
                progress=progress,
            )
        ]
        command_tokens = {
            "ArtifactDir": str(PureWindowsPath(destination).parent),
            "InstallerPath": destination,
            "OutputPath": output_path,
        }
        install_command = render_command_template(_scenario_install_command(artifact), command_tokens)
        _emit_progress(progress, "artifact.install.start", "Run artifact installer", destination=destination)
        install_execution = channel.execute(
            vm,
            _shell_argv(install_command),
            timeout_seconds=command_timeout_seconds,
        )
        install_exit_code = install_execution.exit_code
        install_stdout = install_execution.stdout
        install_stderr = install_execution.stderr
        if not install_execution.passed:
            local_log_paths = _write_artifact_logs(
                oslab_config.output_root,
                scenario.scenario_id,
                install_stdout=install_stdout,
                install_stderr=install_stderr,
                product_stdout="",
                product_stderr="",
                product_steps=[],
                run_dir=run_dir,
            )
            _emit_progress(
                progress,
                "artifact.install.failed",
                "Artifact installer failed",
                exitCode=install_exit_code if install_exit_code is not None else "<missing>",
            )
            return ArtifactSmokeResult(
                vm=vm,
                clone_name=vm.name or f"vm-{vm.vm_id}",
                status=VmStatus(vm_id=vm.vm_id, status="unknown"),
                guest_info=GuestInfo(vm_id=vm.vm_id),
                artifact_path=artifact_path,
                artifact_destination=destination,
                uploaded_files=uploaded_files,
                install_command=install_command,
                install_exit_code=install_exit_code,
                install_stdout=install_stdout,
                install_stderr=install_stderr,
                command=CommandSpec(shell="powershell", template="", rendered=""),
                exit_code=None,
                stdout="",
                stderr="",
                output_path=output_path,
                output_adapter=output_adapter,
                collected_bytes=None,
                collected_json=None,
                local_output_path=None,
                normalized_json=None,
                local_normalized_path=None,
                started=True,
                destroyed=False,
                kept=True,
                passed=False,
                message="Artifact install command failed",
                local_log_paths=local_log_paths,
                local_report_paths={},
                guest_checks=guest_checks,
                fixtures=fixtures,
            )
        _emit_progress(progress, "artifact.install.done", "Artifact installer completed", exitCode=install_exit_code)
    else:
        raise OslabError("Unsupported artifact type", details={"type": artifact_type})

    product_steps: list[ProductStepResult] = []
    local_product_steps_path: Path | None = None
    product_step_specs = _scenario_product_steps(scenario)
    if product_step_specs:
        command = CommandSpec(shell="powershell", template="", rendered="")
        execution_exit_code: int | None = None
        execution_stdout = ""
        execution_stderr = ""
        execution_passed = True
        execution_message = "Artifact smoke passed"
        for step in product_step_specs:
            step_id = str(step.get("id", "<missing>"))
            _emit_progress(progress, "product.step.start", "Run product step", stepId=step_id)
            step_result = _run_product_step(
                channel,
                vm,
                scenario=scenario,
                step=step,
                tokens=command_tokens,
                timeout_seconds=command_timeout_seconds,
            )
            product_steps.append(step_result)
            command = step_result.command
            execution_exit_code = step_result.exit_code
            execution_stdout = step_result.stdout
            execution_stderr = step_result.stderr
            if not step_result.passed:
                execution_passed = False
                execution_message = f"Product step failed: {step_result.id}"
                _emit_progress(
                    progress,
                    "product.step.failed",
                    "Product step failed",
                    stepId=step_result.id,
                    exitCode=step_result.exit_code if step_result.exit_code is not None else "<missing>",
                )
                break
            _emit_progress(
                progress,
                "product.step.done",
                "Product step completed",
                stepId=step_result.id,
                exitCode=step_result.exit_code if step_result.exit_code is not None else "<missing>",
            )
        local_product_steps_path = _write_product_steps_output(
            oslab_config.output_root,
            scenario.scenario_id,
            product_steps,
            run_dir=run_dir,
        )
        _emit_progress(progress, "product.steps.write.done", "Product step results written", path=local_product_steps_path)
    else:
        command = render_command_template(
            _scenario_artifact_command(artifact),
            command_tokens,
        )
        _emit_progress(progress, "product.command.start", "Run product command")
        execution = channel.execute(
            vm,
            _shell_argv(command),
            timeout_seconds=command_timeout_seconds,
        )
        execution_exit_code = execution.exit_code
        execution_stdout = execution.stdout
        execution_stderr = execution.stderr
        execution_passed = execution.passed
        execution_message = "Artifact smoke passed" if execution.passed else "Artifact command failed"
        _emit_progress(
            progress,
            "product.command.done" if execution.passed else "product.command.failed",
            "Product command completed" if execution.passed else "Product command failed",
            exitCode=execution.exit_code if execution.exit_code is not None else "<missing>",
            stdoutBytes=len(execution.stdout.encode("utf-8")),
            stderrBytes=len(execution.stderr.encode("utf-8")),
        )

    local_log_paths = _write_artifact_logs(
        oslab_config.output_root,
        scenario.scenario_id,
        install_stdout=install_stdout,
        install_stderr=install_stderr,
        product_stdout=execution_stdout,
        product_stderr=execution_stderr,
        product_steps=product_steps,
        run_dir=run_dir,
    )

    collected_bytes: int | None = None
    collected_json: dict[str, Any] | list[Any] | None = None
    local_output_path: Path | None = None
    normalized_json: dict[str, Any] | None = None
    local_normalized_path: Path | None = None
    assertions: list[AssertionResult] = []
    passed = execution_passed
    message = execution_message

    if execution_passed:
        _emit_progress(progress, "output.collect.start", "Collect product output", outputPath=output_path)
        download = channel.download_text(vm, output_path)
        collected_bytes = download.bytes_read
        _emit_progress(progress, "output.collect.done", "Product output collected", bytesRead=collected_bytes)
        try:
            _emit_progress(progress, "output.parse.start", "Parse product output JSON")
            collected_json = json.loads(download.content.lstrip("\ufeff"))
        except json.JSONDecodeError as exc:
            passed = False
            message = "Artifact output was not valid JSON"
            collected_json = {"jsonError": str(exc)}
            _emit_progress(progress, "output.parse.failed", "Product output JSON parse failed")
        else:
            _emit_progress(progress, "output.parse.done", "Product output JSON parsed")
            if _is_product_failure_artifact(collected_json):
                passed = False
                message = "Product CLI returned failure artifact"
                _emit_progress(progress, "product.failure_artifact", "Product returned failure artifact")
            else:
                _emit_progress(progress, "output.normalize.start", "Normalize product output", adapter=output_adapter)
                normalization = normalize_output(
                    output_adapter,
                    collected_json,
                    context={"scenarioId": scenario.scenario_id, "outputPath": output_path},
                )
                normalized_json = normalization.canonical
                local_normalized_path = _write_normalized_output(
                    oslab_config.output_root,
                    scenario.scenario_id,
                    normalized_json,
                    run_dir=run_dir,
                )
                _emit_progress(
                    progress,
                    "output.normalize.done",
                    "Product output normalized",
                    records=len(normalized_json.get("records", [])),
                    path=local_normalized_path,
                )
                _emit_progress(progress, "assertions.start", "Evaluate assertions", assertions=len(scenario.assertions))
                assertion_summary = evaluate_assertions(scenario.assertions, normalized_json)
                assertions = assertion_summary.results
                if not assertion_summary.passed:
                    passed = False
                    message = "Artifact assertions failed"
                    _emit_progress(
                        progress,
                        "assertions.failed",
                        "Assertions failed",
                        total=len(assertions),
                        failed=assertion_summary.failed_count,
                    )
                else:
                    _emit_progress(progress, "assertions.done", "Assertions passed", total=len(assertions))
        local_output_path = _write_artifact_output(oslab_config.output_root, scenario.scenario_id, download.content, run_dir=run_dir)
        _emit_progress(progress, "output.write.done", "Raw product output written", path=local_output_path)

    return ArtifactSmokeResult(
        vm=vm,
        clone_name=vm.name or f"vm-{vm.vm_id}",
        status=VmStatus(vm_id=vm.vm_id, status="unknown"),
        guest_info=GuestInfo(vm_id=vm.vm_id),
        artifact_path=artifact_path,
        artifact_destination=destination,
        uploaded_files=uploaded_files,
        install_command=install_command,
        install_exit_code=install_exit_code,
        install_stdout=install_stdout,
        install_stderr=install_stderr,
        command=command,
        exit_code=execution_exit_code,
        stdout=execution_stdout,
        stderr=execution_stderr,
        output_path=output_path,
        output_adapter=output_adapter,
        collected_bytes=collected_bytes,
        collected_json=collected_json,
        local_output_path=local_output_path,
        normalized_json=normalized_json,
        local_normalized_path=local_normalized_path,
        started=True,
        destroyed=False,
        kept=True,
        passed=passed,
        message=message,
        product_steps=product_steps,
        local_product_steps_path=local_product_steps_path,
        assertions=assertions,
        local_log_paths=local_log_paths,
        local_report_paths={},
        guest_checks=guest_checks,
        fixtures=fixtures,
    )


def _run_full_run_guest_preflight(
    channel: QemuAgentChannel,
    vm: VmRef,
    *,
    scenario: Scenario,
    command_timeout_seconds: int,
    progress: ProgressCallback | None,
) -> list[GuestPreflightCheck]:
    _emit_progress(progress, "preflight.start", "Run guest preflight checks")
    checks = run_windows_guest_checks(channel, vm, command_timeout_seconds=command_timeout_seconds)
    if _scenario_requires_supplyscan_config_check(scenario):
        checks.append(_run_supplyscan_config_contamination_check(channel, vm, timeout_seconds=command_timeout_seconds))
    for check in checks:
        _emit_progress(
            progress,
            "preflight.check.done" if check.passed else "preflight.check.failed",
            "Guest preflight check passed" if check.passed else "Guest preflight check failed",
            checkId=check.id,
            checkMessage=check.message,
        )
    if all(check.passed for check in checks):
        _emit_progress(progress, "preflight.done", "Guest preflight passed", checks=len(checks))
    else:
        _emit_progress(
            progress,
            "preflight.failed",
            "Guest preflight failed",
            checks=len(checks),
            failed=sum(1 for check in checks if not check.passed),
        )
    return checks


def _run_supplyscan_config_contamination_check(
    channel: QemuAgentChannel,
    vm: VmRef,
    *,
    timeout_seconds: int,
) -> GuestPreflightCheck:
    path = r"C:\WINDOWS\system32\config\systemprofile\AppData\Local\SupplyScanAgent\config.ini"
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            f"$path = {_ps_single_quote(path)}; "
            "if (Test-Path -LiteralPath $path) { 'present' } else { 'absent' }"
        ),
    ]
    try:
        result = channel.execute(vm, command, timeout_seconds=timeout_seconds)
    except OslabError as exc:
        return GuestPreflightCheck("supplyscan.config_contamination", False, exc.message, details=exc.details)
    state = result.stdout.strip().lower()
    details = {"path": path, "state": state, "exitCode": result.exit_code, "stderr": result.stderr.strip()}
    if not result.passed:
        return GuestPreflightCheck(
            "supplyscan.config_contamination",
            False,
            "Could not inspect SupplyScan config.ini contamination",
            details=details,
        )
    if state == "present":
        return GuestPreflightCheck(
            "supplyscan.config_contamination",
            False,
            "SupplyScan config.ini already exists in the template clone",
            details=details,
        )
    return GuestPreflightCheck(
        "supplyscan.config_contamination",
        True,
        "SupplyScan config.ini was not present before register",
        details=details,
    )


def _scenario_requires_supplyscan_config_check(scenario: Scenario) -> bool:
    steps_text = json.dumps(_scenario_product_steps(scenario), ensure_ascii=False)
    return "SupplyScanAgent.exe" in steps_text or scenario.scenario_id.startswith("supplyscan.agent")


def _early_artifact_result(
    vm: VmRef,
    *,
    scenario: Scenario,
    artifact_path: Path,
    artifact_destination: str,
    output_path: str,
    output_adapter: str,
    message: str,
    guest_checks: list[GuestPreflightCheck],
    fixtures: list[FixtureSmokeItem],
) -> ArtifactSmokeResult:
    return ArtifactSmokeResult(
        vm=vm,
        clone_name=vm.name or f"vm-{vm.vm_id}",
        status=VmStatus(vm_id=vm.vm_id, status="unknown"),
        guest_info=GuestInfo(vm_id=vm.vm_id),
        artifact_path=artifact_path,
        artifact_destination=artifact_destination,
        uploaded_files=[],
        command=CommandSpec(shell="powershell", template="", rendered=""),
        exit_code=None,
        stdout="",
        stderr="",
        output_path=output_path,
        output_adapter=output_adapter,
        collected_bytes=None,
        collected_json=None,
        local_output_path=None,
        normalized_json=None,
        local_normalized_path=None,
        started=True,
        destroyed=False,
        kept=True,
        passed=False,
        message=message,
        guest_checks=guest_checks,
        fixtures=fixtures,
    )


def _with_lifecycle(
    result: ArtifactSmokeResult,
    *,
    status: VmStatus,
    guest_info: GuestInfo,
    started: bool,
    destroyed: bool,
    kept: bool,
) -> ArtifactSmokeResult:
    return ArtifactSmokeResult(
        vm=result.vm,
        clone_name=result.clone_name,
        status=status,
        guest_info=guest_info,
        artifact_path=result.artifact_path,
        artifact_destination=result.artifact_destination,
        uploaded_files=result.uploaded_files,
        install_command=result.install_command,
        install_exit_code=result.install_exit_code,
        install_stdout=result.install_stdout,
        install_stderr=result.install_stderr,
        product_steps=result.product_steps,
        local_product_steps_path=result.local_product_steps_path,
        command=result.command,
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        output_path=result.output_path,
        output_adapter=result.output_adapter,
        collected_bytes=result.collected_bytes,
        collected_json=result.collected_json,
        local_output_path=result.local_output_path,
        normalized_json=result.normalized_json,
        local_normalized_path=result.local_normalized_path,
        started=started,
        destroyed=destroyed,
        kept=kept,
        passed=result.passed,
        message=result.message,
        assertions=result.assertions,
        local_log_paths=result.local_log_paths,
        local_report_paths=result.local_report_paths,
        guest_checks=result.guest_checks,
        fixtures=result.fixtures,
    )


def _with_report_paths(result: ArtifactSmokeResult, report_paths: dict[str, Path]) -> ArtifactSmokeResult:
    return ArtifactSmokeResult(
        vm=result.vm,
        clone_name=result.clone_name,
        status=result.status,
        guest_info=result.guest_info,
        artifact_path=result.artifact_path,
        artifact_destination=result.artifact_destination,
        uploaded_files=result.uploaded_files,
        install_command=result.install_command,
        install_exit_code=result.install_exit_code,
        install_stdout=result.install_stdout,
        install_stderr=result.install_stderr,
        product_steps=result.product_steps,
        local_product_steps_path=result.local_product_steps_path,
        command=result.command,
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        output_path=result.output_path,
        output_adapter=result.output_adapter,
        collected_bytes=result.collected_bytes,
        collected_json=result.collected_json,
        local_output_path=result.local_output_path,
        normalized_json=result.normalized_json,
        local_normalized_path=result.local_normalized_path,
        started=result.started,
        destroyed=result.destroyed,
        kept=result.kept,
        passed=result.passed,
        message=result.message,
        assertions=result.assertions,
        local_log_paths=result.local_log_paths,
        local_report_paths=report_paths,
        guest_checks=result.guest_checks,
        fixtures=result.fixtures,
    )


def _emit_progress(progress: ProgressCallback | None, phase: str, message: str, **details: Any) -> None:
    if progress is not None:
        progress(ProgressEvent(phase=phase, message=message, details=details))


def _emit_transfer_progress(
    progress: ProgressCallback | None,
    phase: str,
    message: str,
    *,
    transferred: int,
    total: int,
    last_percent: int,
    **details: Any,
) -> int:
    if progress is None or total <= 0:
        return last_percent
    percent = min(100, int((transferred / total) * 100))
    if percent < 10:
        return last_percent
    if percent < 100 and percent < last_percent + 10:
        return last_percent
    _emit_progress(
        progress,
        phase,
        message,
        percent=f"{percent}%",
        bytesTransferred=transferred,
        totalBytes=total,
        **details,
    )
    return percent


def _write_artifact_reports(
    output_root: Path,
    scenario: Scenario,
    result: ArtifactSmokeResult,
    *,
    run_dir: Path | None = None,
) -> dict[str, Path]:
    report_paths: dict[str, Path] = {}
    formats = set(scenario.report_formats)
    reports_dir = _artifact_reports_dir(output_root, scenario.scenario_id, run_dir=run_dir)
    analysis = _inventory_analysis_payload(result.normalized_json)
    if analysis is not None:
        analysis_path = reports_dir / "inventory.analysis.json"
        write_json(analysis_path, analysis)
        report_paths["inventoryAnalysis"] = analysis_path
    if "junit" in formats:
        junit_path = reports_dir / "result.junit.xml"
        write_junit(junit_path, suite_name=scenario.scenario_id, cases=_artifact_junit_cases(scenario, result))
        report_paths["junit"] = junit_path
    if "html" in formats:
        report_paths["html"] = reports_dir / "result.html"
    if "json" in formats:
        json_path = reports_dir / "result.json"
        report_paths["json"] = json_path
    report_result = replace(
        result,
        local_log_paths={
            **_existing_progress_log_paths(run_dir),
            **result.local_log_paths,
        },
    )
    payload = _artifact_report_payload(scenario, report_result, report_paths=report_paths, analysis=analysis)
    if "json" in report_paths:
        write_json(report_paths["json"], payload)
    if "html" in report_paths:
        write_artifact_html(report_paths["html"], payload)
    return report_paths


def _existing_progress_log_paths(run_dir: Path | None) -> dict[str, Path]:
    if run_dir is None:
        return {}
    logs_dir = run_dir / "logs"
    paths = {
        "progress": logs_dir / "progress.log",
        "progressJsonl": logs_dir / "progress.jsonl",
    }
    return {name: path for name, path in paths.items() if path.exists()}


def _artifact_report_payload(
    scenario: Scenario,
    result: ArtifactSmokeResult,
    *,
    report_paths: dict[str, Path],
    analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "kind": "artifactSmokeReport",
        "scenarioId": scenario.scenario_id,
        "scenarioName": scenario.name,
        "status": "passed" if result.passed else "failed",
        "message": result.message,
        "failureClass": _artifact_failure_class(result),
        "vm": {
            "id": result.vm.vm_id,
            "name": result.clone_name,
            "node": result.vm.node,
            "status": result.status.status,
            "started": result.started,
            "destroyed": result.destroyed,
            "kept": result.kept,
        },
        "artifact": {
            "path": str(result.artifact_path),
            "destination": result.artifact_destination,
            "uploadedFiles": len(result.uploaded_files),
            "uploadedBytes": sum(file.bytes_written for file in result.uploaded_files),
            "files": [
                {
                    "localPath": str(file.local_path),
                    "guestPath": file.guest_path,
                    "bytesWritten": file.bytes_written,
                }
                for file in result.uploaded_files
            ],
        },
        "preflight": _preflight_report_payload(result),
        "fixtures": _fixtures_report_payload(result),
        "install": _install_report_payload(result),
        "product": {
            "command": result.command.safe_rendered,
            "exitCode": result.exit_code,
            "stdoutBytes": len(result.stdout.encode("utf-8")),
            "stderrBytes": len(result.stderr.encode("utf-8")),
            "steps": [_product_step_report_payload(step) for step in result.product_steps],
            "localProductStepsPath": str(result.local_product_steps_path) if result.local_product_steps_path else None,
        },
        "outputs": {
            "guestPath": result.output_path,
            "adapter": result.output_adapter,
            "collectedBytes": result.collected_bytes,
            "localRawPath": str(result.local_output_path) if result.local_output_path else None,
            "localNormalizedPath": str(result.local_normalized_path) if result.local_normalized_path else None,
            "records": _record_count(result.normalized_json),
        },
        "analysis": analysis,
        "assertions": {
            "passed": all(assertion.passed for assertion in result.assertions),
            "total": len(result.assertions),
            "failed": sum(1 for assertion in result.assertions if not assertion.passed),
            "results": [assertion.to_dict() for assertion in result.assertions],
        },
        "logs": {name: str(path) for name, path in sorted(result.local_log_paths.items())},
        "reports": {name: str(path) for name, path in sorted(report_paths.items())},
    }


def _inventory_analysis_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    if payload.get("kind") != "inventory":
        return None
    return analyze_inventory(payload)


def _preflight_report_payload(result: ArtifactSmokeResult) -> dict[str, Any]:
    return {
        "passed": all(check.passed for check in result.guest_checks),
        "total": len(result.guest_checks),
        "failed": sum(1 for check in result.guest_checks if not check.passed),
        "checks": [
            {
                "id": check.id,
                "passed": check.passed,
                "message": check.message,
                "details": check.details,
            }
            for check in result.guest_checks
        ],
    }


def _fixtures_report_payload(result: ArtifactSmokeResult) -> dict[str, Any]:
    return {
        "passed": all(fixture.passed for fixture in result.fixtures),
        "total": len(result.fixtures),
        "failed": sum(1 for fixture in result.fixtures if not fixture.passed),
        "items": [
            {
                "id": fixture.id,
                "type": fixture.fixture_type,
                "source": str(fixture.source),
                "guestPath": fixture.guest_path,
                "expectedOutput": fixture.expected_output,
                "uploadedBytes": fixture.uploaded_bytes,
                "exitCode": fixture.exit_code,
                "stdoutBytes": len(fixture.stdout.encode("utf-8")),
                "stderrBytes": len(fixture.stderr.encode("utf-8")),
                "stdout": fixture.stdout,
                "stderr": fixture.stderr,
                "collectedBytes": fixture.collected_bytes,
                "localOutputPath": str(fixture.local_output_path) if fixture.local_output_path else None,
                "passed": fixture.passed,
                "message": fixture.message,
            }
            for fixture in result.fixtures
        ],
    }


def _install_report_payload(result: ArtifactSmokeResult) -> dict[str, Any] | None:
    if result.install_command is None:
        return None
    return {
        "command": result.install_command.safe_rendered,
        "exitCode": result.install_exit_code,
        "stdoutBytes": len(result.install_stdout.encode("utf-8")),
        "stderrBytes": len(result.install_stderr.encode("utf-8")),
    }


def _product_step_report_payload(step: ProductStepResult) -> dict[str, Any]:
    return {
        "id": step.id,
        "command": step.command.safe_rendered,
        "exitCode": step.exit_code,
        "stdoutBytes": len(step.stdout.encode("utf-8")),
        "stderrBytes": len(step.stderr.encode("utf-8")),
        "stdoutJson": step.stdout_json,
        "passed": step.passed,
        "message": step.message,
    }


def _artifact_junit_cases(scenario: Scenario, result: ArtifactSmokeResult) -> list[JUnitCase]:
    classname = f"oslab.{scenario.scenario_id}"
    cases: list[JUnitCase] = []
    for check in result.guest_checks:
        cases.append(
            JUnitCase(
                name=f"preflight.{check.id}",
                classname=classname,
                status="passed" if check.passed else "error",
                message=check.message,
                details=check.details,
            )
        )
    for fixture in result.fixtures:
        cases.append(
            JUnitCase(
                name=f"fixture.{fixture.id}",
                classname=classname,
                status="passed" if fixture.passed else "error",
                message=fixture.message,
                details={
                    "exitCode": fixture.exit_code,
                    "source": str(fixture.source),
                    "guestPath": fixture.guest_path,
                    "expectedOutput": fixture.expected_output,
                    "localOutputPath": str(fixture.local_output_path) if fixture.local_output_path else None,
                    "stdout": fixture.stdout,
                    "stderr": fixture.stderr,
                },
            )
        )
    if result.install_command is not None:
        cases.append(
            JUnitCase(
                name="artifact.install",
                classname=classname,
                status="passed" if result.install_exit_code == 0 else "error",
                message="Artifact installer completed" if result.install_exit_code == 0 else "Artifact installer failed",
                details={"exitCode": result.install_exit_code, "command": result.install_command.safe_rendered},
            )
        )
    if result.product_steps:
        for step in result.product_steps:
            cases.append(
                JUnitCase(
                    name=f"product.step.{step.id}",
                    classname=classname,
                    status="passed" if step.passed else "error",
                    message=step.message,
                    details={"exitCode": step.exit_code, "command": step.command.safe_rendered},
                )
            )
    elif result.command.rendered:
        cases.append(
            JUnitCase(
                name="product.command",
                classname=classname,
                status="passed" if result.exit_code == 0 else "error",
                message="Product command completed" if result.exit_code == 0 else result.message,
                details={"exitCode": result.exit_code, "command": result.command.safe_rendered},
            )
        )
    for assertion in result.assertions:
        cases.append(
            JUnitCase(
                name=f"assertion.{assertion.id}",
                classname=classname,
                status="passed" if assertion.passed else "failed",
                message=assertion.message,
                details=assertion.details,
            )
        )
    if not cases:
        cases.append(
            JUnitCase(
                name="artifact.smoke",
                classname=classname,
                status="passed" if result.passed else "error",
                message=result.message,
            )
        )
    return cases


def _artifact_failure_class(result: ArtifactSmokeResult) -> str | None:
    if result.passed:
        return None
    if any(not check.passed for check in result.guest_checks):
        return "preflight_failure"
    if any(not fixture.passed for fixture in result.fixtures):
        return "fixture_failure"
    if any(not assertion.passed for assertion in result.assertions):
        return "assertion_failure"
    if result.install_command is not None and result.install_exit_code not in (0, None):
        return "artifact_failure"
    if any(not step.passed for step in result.product_steps):
        return "product_execution_failure"
    if result.exit_code not in (0, None):
        return "product_execution_failure"
    return "product_execution_failure"


def _record_count(payload: dict[str, Any] | None) -> int | None:
    if payload is None:
        return None
    records = payload.get("records")
    return len(records) if isinstance(records, list) else None


def _upload_folder_artifact(
    channel: QemuAgentChannel,
    vm: VmRef,
    artifact_path: Path,
    destination: str,
    *,
    exclude_patterns: list[str] | None = None,
    transfer_mode: str = "files",
    command_timeout_seconds: int,
    progress: ProgressCallback | None = None,
) -> list[UploadedArtifactFile]:
    if not artifact_path.is_dir():
        raise OslabError(f"Folder artifact path is not a directory: {artifact_path}", details={"path": str(artifact_path)})

    patterns = exclude_patterns or []
    files = _folder_artifact_files(artifact_path, patterns)
    if not files:
        raise OslabError(f"Folder artifact does not contain any files: {artifact_path}", details={"path": str(artifact_path)})
    total_bytes = sum(path.stat().st_size for path in files)
    _emit_progress(
        progress,
        "artifact.upload.start",
        "Upload artifact folder",
        mode=transfer_mode,
        files=len(files),
        bytes=total_bytes,
    )

    if transfer_mode == "archive":
        uploaded = _upload_folder_artifact_archive(
            channel,
            vm,
            artifact_path,
            files,
            destination,
            command_timeout_seconds=command_timeout_seconds,
            progress=progress,
        )
        _emit_progress(
            progress,
            "artifact.upload.done",
            "Artifact folder uploaded",
            mode=transfer_mode,
            files=len(files),
            uploadedFiles=len(uploaded),
            bytes=sum(file.bytes_written for file in uploaded),
        )
        return uploaded
    if transfer_mode != "files":
        raise OslabError("Unsupported folder artifact transfer mode", details={"transfer": transfer_mode})

    directories = {destination}
    for path in files:
        guest_path = _guest_path_for_file(artifact_path, path, destination)
        parent = str(PureWindowsPath(guest_path).parent)
        directories.add(parent)
    for directory in sorted(directories):
        _ensure_guest_directory(channel, vm, directory, timeout_seconds=command_timeout_seconds)

    uploaded: list[UploadedArtifactFile] = []
    uploaded_bytes = 0
    last_percent = -10
    for path in files:
        guest_path = _guest_path_for_file(artifact_path, path, destination)
        write = channel.upload_bytes(vm, guest_path, path.read_bytes())
        uploaded.append(UploadedArtifactFile(local_path=path, guest_path=guest_path, bytes_written=write.bytes_written))
        uploaded_bytes += write.bytes_written
        last_percent = _emit_transfer_progress(
            progress,
            "artifact.upload.progress",
            "Uploading artifact files",
            transferred=uploaded_bytes,
            total=total_bytes,
            last_percent=last_percent,
            filesUploaded=len(uploaded),
            totalFiles=len(files),
        )
    _emit_progress(
        progress,
        "artifact.upload.done",
        "Artifact folder uploaded",
        mode=transfer_mode,
        files=len(uploaded),
        bytes=uploaded_bytes,
    )
    return uploaded


def _upload_folder_artifact_archive(
    channel: QemuAgentChannel,
    vm: VmRef,
    artifact_path: Path,
    files: list[Path],
    destination: str,
    *,
    command_timeout_seconds: int,
    progress: ProgressCallback | None = None,
) -> list[UploadedArtifactFile]:
    parent = str(PureWindowsPath(destination).parent)
    clean_destination = destination.rstrip("\\")
    zip_guest_path = f"{clean_destination}.zip"
    _ensure_guest_directory(channel, vm, parent, timeout_seconds=command_timeout_seconds)

    with tempfile.TemporaryDirectory(prefix="oslab-artifact-") as temp_dir:
        archive_path = Path(temp_dir) / f"{artifact_path.name or 'artifact'}.zip"
        _emit_progress(progress, "artifact.archive.start", "Create artifact archive", files=len(files), path=archive_path)
        with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for path in files:
                archive.write(path, arcname=path.relative_to(artifact_path).as_posix())

        archive_bytes = archive_path.read_bytes()
        _emit_progress(
            progress,
            "artifact.archive.done",
            "Artifact archive created",
            bytes=len(archive_bytes),
            guestPath=zip_guest_path,
        )
        last_percent = -10

        def on_upload_progress(bytes_written: int, total_bytes: int) -> None:
            nonlocal last_percent
            last_percent = _emit_transfer_progress(
                progress,
                "artifact.upload.progress",
                "Uploading artifact archive",
                transferred=bytes_written,
                total=total_bytes,
                last_percent=last_percent,
                guestPath=zip_guest_path,
            )

        write = channel.upload_bytes(vm, zip_guest_path, archive_bytes, progress=on_upload_progress)

    _emit_progress(progress, "artifact.archive.upload.done", "Artifact archive uploaded", guestPath=zip_guest_path, bytes=write.bytes_written)
    _emit_progress(progress, "artifact.archive.expand.start", "Expand artifact archive in guest", destination=destination)
    expand = channel.execute(
        vm,
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                "$ErrorActionPreference = 'Stop'; "
                f"Remove-Item -LiteralPath {_ps_single_quote(destination)} -Recurse -Force -ErrorAction SilentlyContinue; "
                f"New-Item -ItemType Directory -Force -Path {_ps_single_quote(destination)} | Out-Null; "
                f"Expand-Archive -LiteralPath {_ps_single_quote(zip_guest_path)} -DestinationPath {_ps_single_quote(destination)} -Force; "
                f"Remove-Item -LiteralPath {_ps_single_quote(zip_guest_path)} -Force"
            ),
        ],
        timeout_seconds=command_timeout_seconds,
    )
    if not expand.passed:
        _emit_progress(
            progress,
            "artifact.archive.expand.failed",
            "Artifact archive expansion failed",
            destination=destination,
            exitCode=expand.exit_code if expand.exit_code is not None else "<missing>",
        )
        raise OslabError(
            "Failed to expand guest artifact archive",
            details={
                "destination": destination,
                "zipGuestPath": zip_guest_path,
                "exitCode": expand.exit_code,
                "stdout": expand.stdout,
                "stderr": expand.stderr,
            },
        )
    _emit_progress(progress, "artifact.archive.expand.done", "Artifact archive expanded", destination=destination)
    return [UploadedArtifactFile(local_path=artifact_path, guest_path=zip_guest_path, bytes_written=write.bytes_written)]


def _folder_artifact_files(artifact_path: Path, exclude_patterns: list[str]) -> list[Path]:
    return [
        path
        for path in sorted(artifact_path.rglob("*"))
        if path.is_file() and not _artifact_file_is_excluded(artifact_path, path, exclude_patterns)
    ]


def _artifact_exclude_patterns(artifact: dict[str, Any]) -> list[str]:
    excludes = artifact.get("exclude")
    if not isinstance(excludes, list):
        return []
    return [str(pattern) for pattern in excludes if isinstance(pattern, str) and pattern.strip()]


def _artifact_transfer_mode(artifact: dict[str, Any]) -> str:
    value = artifact.get("transfer")
    if not isinstance(value, str) or not value.strip():
        return "files"
    return value


def _artifact_file_is_excluded(root: Path, file_path: Path, patterns: list[str]) -> bool:
    if not patterns:
        return False
    relative = file_path.relative_to(root).as_posix()
    name = file_path.name
    return any(fnmatch(relative, pattern) or fnmatch(name, pattern) for pattern in patterns)


def _upload_installer_artifact(
    channel: QemuAgentChannel,
    vm: VmRef,
    artifact_path: Path,
    destination: str,
    *,
    command_timeout_seconds: int,
    progress: ProgressCallback | None = None,
) -> UploadedArtifactFile:
    if not artifact_path.is_file():
        raise OslabError(f"Installer artifact path is not a file: {artifact_path}", details={"path": str(artifact_path)})
    parent = str(PureWindowsPath(destination).parent)
    _emit_progress(progress, "artifact.upload.start", "Upload installer artifact", destination=destination, bytes=artifact_path.stat().st_size)
    _ensure_guest_directory(channel, vm, parent, timeout_seconds=command_timeout_seconds)
    write = channel.upload_bytes(vm, destination, artifact_path.read_bytes())
    _emit_progress(progress, "artifact.upload.done", "Installer artifact uploaded", destination=destination, bytes=write.bytes_written)
    return UploadedArtifactFile(local_path=artifact_path, guest_path=destination, bytes_written=write.bytes_written)


def _ensure_guest_directory(channel: QemuAgentChannel, vm: VmRef, path: str, *, timeout_seconds: int) -> None:
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        f"New-Item -ItemType Directory -Force -Path {_ps_single_quote(path)} | Out-Null",
    ]
    result = channel.execute(vm, command, timeout_seconds=timeout_seconds)
    if not result.passed:
        raise OslabError(
            "Failed to create guest artifact directory",
            details={"path": path, "exitCode": result.exit_code, "stdout": result.stdout, "stderr": result.stderr},
        )


def _guest_path_for_file(root: Path, file_path: Path, destination: str) -> str:
    relative = file_path.relative_to(root)
    windows_relative = str(PureWindowsPath(*relative.parts))
    clean_destination = destination.rstrip("\\")
    return f"{clean_destination}\\{windows_relative}"


def _shell_argv(command: CommandSpec) -> list[str]:
    if command.shell == "powershell":
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command.rendered]
    if command.shell == "cmd":
        return ["cmd.exe", "/c", command.rendered]
    raise OslabError(f"Unsupported Windows artifact command shell: {command.shell}")


def _scenario_artifact(scenario: Scenario) -> dict[str, Any]:
    artifact = scenario.raw.get("artifact")
    if not isinstance(artifact, dict):
        raise OslabError("Scenario does not define an artifact contract")
    return artifact


def _scenario_artifact_command(artifact: dict[str, Any]) -> dict[str, Any]:
    command = artifact.get("command")
    if not isinstance(command, dict):
        raise OslabError("Scenario artifact does not define a command")
    return command


def _scenario_install_command(artifact: dict[str, Any]) -> dict[str, Any]:
    command = artifact.get("installCommand")
    if not isinstance(command, dict):
        raise OslabError("Installer artifact does not define an installCommand")
    return command


def _scenario_product_steps(scenario: Scenario) -> list[dict[str, Any]]:
    product = scenario.raw.get("product")
    if not isinstance(product, dict):
        return []
    steps = product.get("steps")
    if not isinstance(steps, list):
        return []
    return [step for step in steps if isinstance(step, dict)]


def _scenario_fixture_specs(scenario: Scenario) -> list[dict[str, Any]]:
    fixtures = scenario.raw.get("fixtures")
    if not isinstance(fixtures, list):
        return []
    return [fixture for fixture in fixtures if isinstance(fixture, dict)]


def _validate_required_product_secret_envs(scenario: Scenario) -> None:
    for step in _scenario_product_steps(scenario):
        _resolve_secret_tokens(step, step_id=str(step.get("id") or "<missing>"))


def _run_product_step(
    channel: QemuAgentChannel,
    vm: VmRef,
    *,
    scenario: Scenario,
    step: dict[str, Any],
    tokens: dict[str, str],
    timeout_seconds: int,
) -> ProductStepResult:
    step_id = str(step["id"])
    command_mapping = step["command"]
    step_tokens = dict(tokens)
    step_tokens.update(
        {
            "ScenarioId": scenario.scenario_id,
            "VmId": str(vm.vm_id),
            "AssetName": os.environ.get("OSLAB_ASSET_NAME") or _default_asset_name(scenario.scenario_id, vm.vm_id),
        }
    )
    secret_tokens = _resolve_secret_tokens(step, step_id=step_id)
    command = render_command_template(command_mapping, step_tokens, secret_tokens=secret_tokens)
    execution = channel.execute(vm, _shell_argv(command), timeout_seconds=timeout_seconds)
    stdout_json: dict[str, Any] | list[Any] | None = None
    passed = execution.passed
    message = "Product step passed" if execution.passed else "Product step command failed"
    if passed and bool(step.get("captureStdoutJson", False)):
        try:
            stdout_json = json.loads(execution.stdout.lstrip("\ufeff"))
        except json.JSONDecodeError as exc:
            passed = False
            message = "Product step stdout was not valid JSON"
            stdout_json = {"jsonError": str(exc)}
        else:
            if isinstance(stdout_json, dict) and stdout_json.get("ok") is False:
                passed = False
                message = "Product step stdout reported failure"
            elif _is_product_failure_artifact(stdout_json):
                passed = False
                message = "Product step returned failure artifact"
            stdout_json = _redact_json_secrets(stdout_json, secret_tokens.values())
    return ProductStepResult(
        id=step_id,
        command=command,
        exit_code=execution.exit_code,
        stdout=_redact_text_secrets(execution.stdout, secret_tokens.values()),
        stderr=_redact_text_secrets(execution.stderr, secret_tokens.values()),
        stdout_json=stdout_json,
        passed=passed,
        message=message,
    )


def _resolve_secret_tokens(step: dict[str, Any], *, step_id: str) -> dict[str, str]:
    secret_tokens = step.get("secretTokens")
    if not isinstance(secret_tokens, dict):
        return {}
    resolved: dict[str, str] = {}
    for token_name, source in secret_tokens.items():
        if not isinstance(token_name, str) or not token_name.strip():
            raise ConfigError("Product step secret token name must be a non-empty string", details={"step": step_id})
        if not isinstance(source, dict):
            raise ConfigError(
                "Product step secret token source must be a mapping",
                details={"step": step_id, "token": token_name},
            )
        env_name = source.get("env")
        if not isinstance(env_name, str) or not env_name.strip():
            raise ConfigError(
                "Product step secret token source requires `env`",
                details={"step": step_id, "token": token_name},
            )
        value = os.environ.get(env_name)
        if value is None or value == "":
            raise ConfigError(
                "Required product step secret env var is not set",
                details={"step": step_id, "token": token_name, "env": env_name},
            )
        resolved[token_name] = value
    return resolved


def _default_asset_name(scenario_id: str, vm_id: int) -> str:
    safe_scenario = re.sub(r"[^A-Za-z0-9-]+", "-", scenario_id).strip("-").lower()
    return f"oslab-{safe_scenario}-{vm_id}"


def _scenario_output_path(scenario: Scenario) -> str:
    outputs = scenario.raw.get("outputs")
    if isinstance(outputs, dict):
        actual = outputs.get("actual")
        if isinstance(actual, dict):
            path = actual.get("path")
            if isinstance(path, str) and path.strip():
                return path
    return "C:\\Oslab\\scan-result.json"


def _is_product_failure_artifact(payload: dict[str, Any] | list[Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    artifact_type = payload.get("artifactType") or payload.get("kind")
    return artifact_type == "supplyscan-agent-cli-failure"


def _redact_text_secrets(text: str, secrets: Any) -> str:
    redacted = text
    for secret in secrets:
        if isinstance(secret, str) and secret:
            redacted = redacted.replace(secret, "<redacted>")
    return redacted


def _redact_json_secrets(payload: Any, secrets: Any) -> Any:
    if isinstance(payload, dict):
        return {key: _redact_json_secrets(value, secrets) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_redact_json_secrets(value, secrets) for value in payload]
    if isinstance(payload, str):
        return _redact_text_secrets(payload, secrets)
    return payload


def _write_artifact_output(output_root: Path, scenario_id: str, content: str, *, run_dir: Path | None = None) -> Path:
    if run_dir is None:
        output_dir = output_root / "artifact-smoke" / scenario_id
        path = output_dir / "scan-result.json"
    else:
        output_dir = run_dir / "raw"
        path = output_dir / "actual-output.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    return path


def _write_product_steps_output(
    output_root: Path,
    scenario_id: str,
    steps: list[ProductStepResult],
    *,
    run_dir: Path | None = None,
) -> Path:
    output_dir = output_root / "artifact-smoke" / scenario_id if run_dir is None else run_dir / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "product-steps.json"
    payload = [
        {
            "id": step.id,
            "command": step.command.safe_rendered,
            "exitCode": step.exit_code,
            "stdout": step.stdout,
            "stderr": step.stderr,
            "stdoutJson": step.stdout_json,
            "passed": step.passed,
            "message": step.message,
        }
        for step in steps
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_artifact_logs(
    output_root: Path,
    scenario_id: str,
    *,
    install_stdout: str,
    install_stderr: str,
    product_stdout: str,
    product_stderr: str,
    product_steps: list[ProductStepResult],
    run_dir: Path | None = None,
) -> dict[str, Path]:
    logs_dir = _artifact_logs_dir(output_root, scenario_id, run_dir=run_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    if install_stdout or install_stderr:
        paths["install.stdout"] = _write_log(logs_dir / "install.stdout.log", install_stdout)
        paths["install.stderr"] = _write_log(logs_dir / "install.stderr.log", install_stderr)
    if product_stdout or product_stderr:
        paths["product.stdout"] = _write_log(logs_dir / "product.stdout.log", product_stdout)
        paths["product.stderr"] = _write_log(logs_dir / "product.stderr.log", product_stderr)
    for step in product_steps:
        safe_id = _safe_file_stem(step.id)
        paths[f"productStep.{step.id}.stdout"] = _write_log(logs_dir / f"product-step-{safe_id}.stdout.log", step.stdout)
        paths[f"productStep.{step.id}.stderr"] = _write_log(logs_dir / f"product-step-{safe_id}.stderr.log", step.stderr)
    return paths


def _write_log(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8", newline="")
    return path


def _write_normalized_output(
    output_root: Path,
    scenario_id: str,
    payload: dict[str, Any],
    *,
    run_dir: Path | None = None,
) -> Path:
    output_dir = output_root / "artifact-smoke" / scenario_id if run_dir is None else run_dir / "normalized"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / _normalized_output_filename(payload, run_dir=run_dir)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _normalized_output_filename(payload: dict[str, Any], *, run_dir: Path | None) -> str:
    if payload.get("kind") == "inventory":
        return "inventory.normalized.json" if run_dir is None else "inventory.json"
    if payload.get("kind") == "commandResult":
        return "command-result.normalized.json" if run_dir is None else "command-result.json"
    return "result.normalized.json" if run_dir is None else "result.json"


def _artifact_reports_dir(output_root: Path, scenario_id: str, *, run_dir: Path | None) -> Path:
    return output_root / "artifact-smoke" / scenario_id / "reports" if run_dir is None else run_dir / "reports"


def _artifact_logs_dir(output_root: Path, scenario_id: str, *, run_dir: Path | None) -> Path:
    return output_root / "artifact-smoke" / scenario_id / "logs" if run_dir is None else run_dir / "logs"


def artifact_failure_class(result: ArtifactSmokeResult) -> str | None:
    return _artifact_failure_class(result)


def _safe_file_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "step"


def _ps_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
