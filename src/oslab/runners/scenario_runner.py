"""Skeleton scenario runner.

The real VM/provider implementation lands in later phases. This runner creates
the stable run directory and result shape so CLI, report, and tests can harden
before a Proxmox lab is required.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from oslab.analysis import analyze_inventory
from oslab.config import OslabConfig
from oslab.errors import RunDirectoryError
from oslab.models.result import RunResult, make_run_id, relative_to_cwd
from oslab.models.scenario import Scenario
from oslab.providers.proxmox import ProxmoxConfig
from oslab.reports.json_report import write_json
from oslab.runners.proxmox_artifact_smoke import ProgressCallback, ProgressEvent, artifact_failure_class, run_proxmox_artifact_smoke


def create_run_directory(output_root: Path, run_id: str) -> Path:
    run_dir = output_root / run_id
    try:
        for child in ("logs", "raw", "normalized", "reports"):
            (run_dir / child).mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise RunDirectoryError(f"Cannot create run directory: {run_dir}", details={"error": str(exc)}) from exc
    return run_dir


def run_skeleton(scenario: Scenario, config: OslabConfig, *, run_id: str | None = None) -> RunResult:
    """Create a run directory and JSON report without touching any VM."""

    resolved_run_id = run_id or make_run_id(scenario.scenario_id)
    run_dir = create_run_directory(config.output_root, resolved_run_id)
    result = RunResult(
        run_id=resolved_run_id,
        scenario_id=scenario.scenario_id,
        status="running",
        selected_guest_channel=None,
        details={
            "mode": "skeleton",
            "scenarioPath": str(scenario.path),
            "providerType": scenario.provider_type,
            "osFamily": scenario.os_family,
            "guestMode": scenario.guest_mode,
            "reportFormats": scenario.report_formats,
        },
    )
    result.complete("passed")

    run_json = run_dir / "run.json"
    result.reports["json"] = relative_to_cwd(run_json)
    write_json(run_json, result.to_dict())

    report_json = run_dir / "reports" / "result.json"
    result.reports["resultJson"] = relative_to_cwd(report_json)
    write_json(report_json, result.to_dict())
    write_json(run_json, result.to_dict())
    return result


def run_artifact_validation(
    scenario: Scenario,
    config: OslabConfig,
    *,
    proxmox_config: ProxmoxConfig,
    artifact_path: Path,
    run_id: str | None = None,
    vm_id: int | None = None,
    keep_vm: bool = False,
    full_clone: bool = False,
    boot_timeout_seconds: int = 300,
    guest_timeout_seconds: int = 300,
    command_timeout_seconds: int = 120,
    poll_interval_seconds: float = 5.0,
    progress: ProgressCallback | None = None,
) -> RunResult:
    """Run the Proxmox artifact validation path into the full run directory layout."""

    resolved_run_id = run_id or make_run_id(scenario.scenario_id)
    run_dir = create_run_directory(config.output_root, resolved_run_id)
    run_json = run_dir / "run.json"
    progress_recorder, progress_log_paths = _make_progress_recorder(run_dir, progress)
    progress_logs = _relative_log_paths(progress_log_paths)
    result = RunResult(
        run_id=resolved_run_id,
        scenario_id=scenario.scenario_id,
        status="running",
        selected_guest_channel="qemuAgent",
        reports={"runJson": relative_to_cwd(run_json)},
        details={
            "mode": "artifact",
            "scenarioPath": str(scenario.path),
            "providerType": scenario.provider_type,
            "osFamily": scenario.os_family,
            "guestMode": scenario.guest_mode,
            "artifactPath": str(artifact_path),
            "reportFormats": scenario.report_formats,
            "runDir": relative_to_cwd(run_dir),
            "logs": progress_logs,
        },
    )
    write_json(run_json, result.to_dict())
    progress_recorder(
        ProgressEvent(
            phase="run.created",
            message="Run directory created",
            details={
                "runId": resolved_run_id,
                "runDir": relative_to_cwd(run_dir),
                "progressLog": progress_logs["progress"],
                "progressJsonl": progress_logs["progressJsonl"],
            },
        )
    )

    try:
        artifact_result = run_proxmox_artifact_smoke(
            scenario=scenario,
            oslab_config=config,
            proxmox_config=proxmox_config,
            artifact_path=artifact_path,
            vm_id=vm_id,
            keep_vm=keep_vm,
            full_clone=full_clone,
            boot_timeout_seconds=boot_timeout_seconds,
            guest_timeout_seconds=guest_timeout_seconds,
            command_timeout_seconds=command_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            progress=progress_recorder,
            run_dir=run_dir,
        )
    except Exception as exc:
        result.details["error"] = str(exc)
        result.complete("failed", failure_class="run_failure")
        _append_progress_event(
            progress_log_paths,
            ProgressEvent(
                phase="run.failed",
                message="Run failed",
                details={"runId": resolved_run_id, "status": result.status, "failureClass": result.failure_class},
            )
        )
        write_json(run_json, result.to_dict())
        raise

    result.reports.update({name: relative_to_cwd(path) for name, path in artifact_result.local_report_paths.items()})
    analysis = (
        analyze_inventory(artifact_result.normalized_json)
        if artifact_result.normalized_json is not None and artifact_result.normalized_json.get("kind") == "inventory"
        else None
    )
    result.details.update(
        {
            "vm": {
                "id": artifact_result.vm.vm_id,
                "name": artifact_result.clone_name,
                "status": artifact_result.status.status,
                "destroyed": artifact_result.destroyed,
                "kept": artifact_result.kept,
            },
            "artifact": {
                "destination": artifact_result.artifact_destination,
                "uploadedFiles": len(artifact_result.uploaded_files),
                "uploadedBytes": sum(file.bytes_written for file in artifact_result.uploaded_files),
            },
            "outputs": {
                "raw": relative_to_cwd(artifact_result.local_output_path) if artifact_result.local_output_path else None,
                "normalized": relative_to_cwd(artifact_result.local_normalized_path) if artifact_result.local_normalized_path else None,
                "collectedBytes": artifact_result.collected_bytes,
                "productSteps": relative_to_cwd(artifact_result.local_product_steps_path) if artifact_result.local_product_steps_path else None,
            },
            "logs": {name: relative_to_cwd(path) for name, path in artifact_result.local_log_paths.items()},
            "preflight": {
                "total": len(artifact_result.guest_checks),
                "failed": sum(1 for check in artifact_result.guest_checks if not check.passed),
                "checks": [
                    {
                        "id": check.id,
                        "passed": check.passed,
                        "message": check.message,
                    }
                    for check in artifact_result.guest_checks
                ],
            },
            "fixtures": {
                "total": len(artifact_result.fixtures),
                "failed": sum(1 for fixture in artifact_result.fixtures if not fixture.passed),
                "items": [
                    {
                        "id": fixture.id,
                        "passed": fixture.passed,
                        "message": fixture.message,
                        "exitCode": fixture.exit_code,
                        "stdout": _text_preview(fixture.stdout),
                        "stderr": _text_preview(fixture.stderr),
                        "localOutputPath": relative_to_cwd(fixture.local_output_path) if fixture.local_output_path else None,
                    }
                    for fixture in artifact_result.fixtures
                ],
            },
            "productSteps": _product_step_summaries(artifact_result.product_steps),
            "scan": _scan_summary(artifact_result.product_steps),
            "assertions": {
                "total": len(artifact_result.assertions),
                "failed": sum(1 for assertion in artifact_result.assertions if not assertion.passed),
            },
        }
    )
    result.details["logs"] = {
        **progress_logs,
        **{name: relative_to_cwd(path) for name, path in artifact_result.local_log_paths.items()},
    }
    if analysis is not None:
        result.details["analysis"] = {
            "recordCount": analysis.get("recordCount", 0),
            "sourceCounts": analysis.get("sourceCounts", {}),
            "quality": analysis.get("quality", {}),
            "warnings": analysis.get("warnings", []),
        }
    result.complete("passed" if artifact_result.passed else "failed", failure_class=artifact_failure_class(artifact_result))
    _append_progress_event(
        progress_log_paths,
        ProgressEvent(
            phase="run.done" if result.status == "passed" else "run.failed",
            message="Run completed" if result.status == "passed" else "Run failed",
            details={"runId": result.run_id, "status": result.status, "failureClass": result.failure_class or "<none>"},
        )
    )
    write_json(run_json, result.to_dict())
    return result


def _make_progress_recorder(run_dir: Path, upstream: ProgressCallback | None) -> tuple[ProgressCallback, dict[str, Path]]:
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "progress": logs_dir / "progress.log",
        "progressJsonl": logs_dir / "progress.jsonl",
    }
    paths["progress"].touch()
    paths["progressJsonl"].touch()

    def record(event: ProgressEvent) -> None:
        _append_progress_event(paths, event)
        if upstream is not None:
            upstream(event)

    return record, paths


def _relative_log_paths(paths: dict[str, Path]) -> dict[str, str]:
    return {name: relative_to_cwd(path) for name, path in paths.items()}


def _append_progress_event(paths: dict[str, Path], event: ProgressEvent) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    status = _progress_status(event.phase)
    details = _json_safe(event.details)
    payload = {
        "timestamp": timestamp,
        "status": status,
        "phase": event.phase,
        "message": event.message,
        "details": details,
    }
    with paths["progressJsonl"].open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()

    with paths["progress"].open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(f"{timestamp} {_progress_badge(status)} {event.phase} - {event.message}\n")
        for key, value in details.items() if isinstance(details, dict) else []:
            stream.write(f"    {key}: {_progress_detail_text(value)}\n")
        stream.flush()


def _progress_status(phase: str) -> str:
    if phase.endswith(".failed") or phase == "run.failed":
        return "failed"
    if phase.endswith(".done") or phase == "run.done":
        return "done"
    if phase.endswith(".skipped"):
        return "skipped"
    return "running"


def _progress_badge(status: str) -> str:
    if status == "done":
        return "[OK]"
    if status == "failed":
        return "[FAIL]"
    if status == "skipped":
        return "[WARN]"
    return "[..]"


def _progress_detail_text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _product_step_summaries(steps) -> list[dict]:
    return [
        {
            "id": step.id,
            "passed": step.passed,
            "exitCode": step.exit_code,
            "message": step.message,
            "stdoutJson": _safe_stdout_json_summary(step.stdout_json),
        }
        for step in steps
    ]


def _scan_summary(steps) -> dict | None:
    for step in steps:
        if step.id != "scan" or not isinstance(step.stdout_json, dict):
            continue
        return {
            "ok": step.stdout_json.get("ok"),
            "command": step.stdout_json.get("command"),
            "outputPath": step.stdout_json.get("outputPath"),
            "outputWritten": step.stdout_json.get("outputWritten"),
            "bytesWritten": step.stdout_json.get("bytesWritten"),
            "scanId": step.stdout_json.get("scanId"),
            "uploadRequested": step.stdout_json.get("uploadRequested"),
            "uploadSuccess": step.stdout_json.get("uploadSuccess"),
        }
    return None


def _safe_stdout_json_summary(payload) -> dict | list | None:
    if not isinstance(payload, dict):
        return payload if isinstance(payload, list) else None
    allowed = {
        "ok",
        "command",
        "errorCode",
        "accessTokenPresent",
        "refreshTokenPresent",
        "encryptionKeyPresent",
        "accessTokenProvided",
        "accessTokenSource",
        "remoteRegistered",
        "tokenRemoteValid",
        "policyRemoteAvailable",
        "outputWritten",
        "bytesWritten",
        "scanId",
        "uploadRequested",
        "uploadSuccess",
    }
    return {key: value for key, value in payload.items() if key in allowed}


def _text_preview(value: str, *, limit: int = 2000) -> str:
    if not value:
        return ""
    return value if len(value) <= limit else value[:limit] + "...<truncated>"
