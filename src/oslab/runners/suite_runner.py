"""Suite runner for executing multiple scenarios as one validation batch."""

from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from oslab.config import OslabConfig
from oslab.errors import OslabError, RunDirectoryError
from oslab.models.result import make_run_id, relative_to_cwd
from oslab.models.scenario import load_scenario
from oslab.models.suite import Suite, SuiteEntry
from oslab.providers.proxmox import ProxmoxConfig
from oslab.reports.html import write_suite_html
from oslab.reports.json_report import write_json
from oslab.reports.junit import JUnitCase, write_junit
from oslab.runners.proxmox_artifact_smoke import ProgressCallback, ProgressEvent
from oslab.runners.scenario_runner import run_artifact_validation


@dataclass(frozen=True)
class SuiteEntryResult:
    id: str
    scenario_path: str
    scenario_id: str | None
    status: str
    allow_failure: bool
    tier: str | None
    run_id: str | None = None
    run_dir: str | None = None
    failure_class: str | None = None
    error: str | None = None

    @property
    def required_failed(self) -> bool:
        return self.status != "passed" and not self.allow_failure

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "scenarioPath": self.scenario_path,
            "scenarioId": self.scenario_id,
            "status": self.status,
            "allowFailure": self.allow_failure,
            "tier": self.tier,
            "runId": self.run_id,
            "runDir": self.run_dir,
            "failureClass": self.failure_class,
            "error": self.error,
        }


@dataclass
class SuiteRunResult:
    suite_id: str
    run_id: str
    status: str
    suite_dir: Path
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None
    entries: list[SuiteEntryResult] = field(default_factory=list)
    reports: dict[str, str] = field(default_factory=dict)

    def complete(self) -> None:
        self.status = "failed" if any(entry.required_failed for entry in self.entries) else "passed"
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "suiteId": self.suite_id,
            "runId": self.run_id,
            "status": self.status,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "suiteDir": relative_to_cwd(self.suite_dir),
            "summary": {
                "total": len(self.entries),
                "passed": sum(1 for entry in self.entries if entry.status == "passed"),
                "failed": sum(1 for entry in self.entries if entry.status != "passed"),
                "requiredFailed": sum(1 for entry in self.entries if entry.required_failed),
                "allowedFailed": sum(1 for entry in self.entries if entry.status != "passed" and entry.allow_failure),
            },
            "entries": [entry.to_dict() for entry in self.entries],
            "reports": self.reports,
        }


def run_suite_validation(
    suite: Suite,
    config: OslabConfig,
    *,
    proxmox_config: ProxmoxConfig,
    artifact_path: Path,
    run_id: str | None = None,
    keep_vm: bool = False,
    full_clone: bool = False,
    boot_timeout_seconds: int = 300,
    guest_timeout_seconds: int = 300,
    command_timeout_seconds: int = 120,
    poll_interval_seconds: float = 5.0,
    max_parallel: int = 1,
    progress: ProgressCallback | None = None,
) -> SuiteRunResult:
    """Run enabled suite entries and write aggregate suite.json."""

    if max_parallel <= 0:
        raise OslabError("Suite max_parallel must be a positive integer")

    suite_run_id = run_id or make_run_id(suite.suite_id)
    suite_dir = config.output_root / suite_run_id
    try:
        (suite_dir / "scenarios").mkdir(parents=True, exist_ok=False)
        (suite_dir / "reports").mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RunDirectoryError(f"Cannot create suite directory: {suite_dir}", details={"error": str(exc)}) from exc

    result = SuiteRunResult(suite_id=suite.suite_id, run_id=suite_run_id, status="running", suite_dir=suite_dir)
    suite_json = suite_dir / "suite.json"
    result.reports["suiteJson"] = relative_to_cwd(suite_json)
    write_json(suite_json, result.to_dict())

    enabled_entries = [item for item in suite.entries if item.enabled]
    child_config = _config_with_output_root(config, suite_dir / "scenarios")
    if max_parallel == 1:
        for entry in enabled_entries:
            entry_result = _run_suite_entry(
                suite,
                entry,
                child_config,
                proxmox_config=proxmox_config,
                artifact_path=artifact_path,
                suite_run_id=suite_run_id,
                keep_vm=keep_vm,
                full_clone=full_clone,
                boot_timeout_seconds=boot_timeout_seconds,
                guest_timeout_seconds=guest_timeout_seconds,
                command_timeout_seconds=command_timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
                progress=progress,
            )
            result.entries.append(entry_result)
            write_json(suite_json, result.to_dict())
    else:
        entry_order = {entry.id: index for index, entry in enumerate(enabled_entries)}
        completed: list[SuiteEntryResult] = []
        with ThreadPoolExecutor(max_workers=min(max_parallel, len(enabled_entries))) as executor:
            futures = {
                executor.submit(
                    _run_suite_entry,
                    suite,
                    entry,
                    child_config,
                    proxmox_config=proxmox_config,
                    artifact_path=artifact_path,
                    suite_run_id=suite_run_id,
                    keep_vm=keep_vm,
                    full_clone=full_clone,
                    boot_timeout_seconds=boot_timeout_seconds,
                    guest_timeout_seconds=guest_timeout_seconds,
                    command_timeout_seconds=command_timeout_seconds,
                    poll_interval_seconds=poll_interval_seconds,
                    progress=progress,
                ): entry
                for entry in enabled_entries
            }
            for future in as_completed(futures):
                entry = futures[future]
                try:
                    completed.append(future.result())
                except Exception as exc:
                    completed.append(
                        SuiteEntryResult(
                            id=entry.id,
                            scenario_path=relative_to_cwd(_resolve_path(suite.path, entry.scenario)),
                            scenario_id=None,
                            status="failed",
                            allow_failure=entry.allow_failure,
                            tier=entry.tier,
                            failure_class="suite_entry_failure",
                            error=str(exc),
                        )
                    )
                result.entries = sorted(completed, key=lambda item: entry_order.get(item.id, 0))
                write_json(suite_json, result.to_dict())

    result.complete()
    entry_order = {entry.id: index for index, entry in enumerate(enabled_entries)}
    result.entries = sorted(result.entries, key=lambda item: entry_order.get(item.id, 0))
    _write_suite_reports(result)
    write_json(suite_json, result.to_dict())
    return result


def _run_suite_entry(
    suite: Suite,
    entry: SuiteEntry,
    config: OslabConfig,
    *,
    proxmox_config: ProxmoxConfig,
    artifact_path: Path,
    suite_run_id: str,
    keep_vm: bool,
    full_clone: bool,
    boot_timeout_seconds: int,
    guest_timeout_seconds: int,
    command_timeout_seconds: int,
    poll_interval_seconds: float,
    progress: ProgressCallback | None,
) -> SuiteEntryResult:
    scenario_path = _resolve_path(suite.path, entry.scenario)
    try:
        scenario = load_scenario(scenario_path)
        child_run_id = f"{suite_run_id}-{entry.id}"
        run_result = run_artifact_validation(
            scenario,
            config,
            proxmox_config=proxmox_config,
            artifact_path=artifact_path,
            run_id=child_run_id,
            keep_vm=keep_vm,
            full_clone=full_clone,
            boot_timeout_seconds=boot_timeout_seconds,
            guest_timeout_seconds=guest_timeout_seconds,
            command_timeout_seconds=command_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            progress=_entry_progress(entry, progress),
        )
        return SuiteEntryResult(
            id=entry.id,
            scenario_path=relative_to_cwd(scenario_path),
            scenario_id=scenario.scenario_id,
            status=run_result.status,
            allow_failure=entry.allow_failure,
            tier=entry.tier,
            run_id=run_result.run_id,
            run_dir=run_result.details.get("runDir") if isinstance(run_result.details, dict) else None,
            failure_class=run_result.failure_class,
        )
    except OslabError as exc:
        return SuiteEntryResult(
            id=entry.id,
            scenario_path=relative_to_cwd(scenario_path),
            scenario_id=None,
            status="failed",
            allow_failure=entry.allow_failure,
            tier=entry.tier,
            failure_class=exc.failure_class,
            error=exc.message,
        )


def _config_with_output_root(config: OslabConfig, output_root: Path) -> OslabConfig:
    raw = copy.deepcopy(config.raw)
    run_defaults = raw.get("runDefaults")
    if not isinstance(run_defaults, dict):
        run_defaults = {}
    run_defaults["outputRoot"] = str(output_root)
    raw["runDefaults"] = run_defaults
    return OslabConfig(path=config.path, raw=raw)


def _resolve_path(suite_path: Path, target: Path) -> Path:
    if target.is_absolute():
        return target
    cwd_candidate = Path.cwd() / target
    if cwd_candidate.exists():
        return cwd_candidate
    return suite_path.resolve().parent / target


def _write_suite_reports(result: SuiteRunResult) -> None:
    html_path = result.suite_dir / "reports" / "suite.html"
    junit_path = result.suite_dir / "reports" / "suite.junit.xml"
    result.reports["html"] = relative_to_cwd(html_path)
    result.reports["junit"] = relative_to_cwd(junit_path)
    payload = result.to_dict()
    write_suite_html(html_path, payload)
    write_junit(junit_path, suite_name=result.suite_id, cases=_suite_junit_cases(result))


def _suite_junit_cases(result: SuiteRunResult) -> list[JUnitCase]:
    cases: list[JUnitCase] = []
    for entry in result.entries:
        if entry.status == "passed":
            status = "passed"
            message = ""
        elif entry.allow_failure:
            status = "skipped"
            message = entry.failure_class or entry.error or "Allowed failure"
        else:
            status = "failed"
            message = entry.failure_class or entry.error or "Suite entry failed"
        cases.append(
            JUnitCase(
                name=entry.id,
                classname=f"oslab.suite.{result.suite_id}",
                status=status,
                message=message,
                details=entry.to_dict(),
            )
        )
    return cases


def _entry_progress(entry: SuiteEntry, upstream: ProgressCallback | None) -> ProgressCallback | None:
    if upstream is None:
        return None

    def emit(event: ProgressEvent) -> None:
        details = {**event.details, "suiteEntry": entry.id}
        prefix = f"[{entry.id}] "
        message = event.message if event.message.startswith(prefix) else f"{prefix}{event.message}"
        upstream(ProgressEvent(phase=event.phase, message=message, details=details))

    return emit
