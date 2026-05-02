from pathlib import Path
import time
import xml.etree.ElementTree as ET

from oslab.config import OslabConfig
from oslab.models.result import RunResult
from oslab.models.suite import load_suite
from oslab.providers.proxmox import ProxmoxConfig
from oslab.runners.proxmox_artifact_smoke import ProgressEvent
from oslab.runners import suite_runner
from oslab.runners.suite_runner import run_suite_validation


def make_config(tmp_path: Path) -> OslabConfig:
    return OslabConfig(path=None, raw={"runDefaults": {"outputRoot": str(tmp_path / "runs")}})


def make_proxmox_config() -> ProxmoxConfig:
    return ProxmoxConfig(
        api_url="https://pve.example.local:8006",
        node="softverse",
        token_id="root@pam!auto_test",
        token_secret="secret",
        verify_tls=False,
    )


def test_run_suite_validation_writes_aggregate_result(tmp_path: Path, monkeypatch) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "SupplyScanAgent.exe").write_bytes(b"fake")

    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        """
schemaVersion: 1
id: local.suite
runs:
  - id: required
    scenario: scenarios/windows/supplyscan/supplyscan-agent-clean-baseline.example.yaml
    tier: ci
  - id: allowed
    scenario: scenarios/windows/supplyscan/supplyscan-agent-appx-readonly.example.yaml
    tier: gap-probe
    allowFailure: true
""",
        encoding="utf-8",
    )

    def fake_run_artifact_validation(scenario, config, **kwargs):
        result = RunResult(run_id=kwargs["run_id"], scenario_id=scenario.scenario_id, status="running")
        result.details["runDir"] = str(config.output_root / kwargs["run_id"])
        result.complete("failed" if scenario.scenario_id.endswith("appx-readonly.windows") else "passed", failure_class=None)
        return result

    monkeypatch.setattr(suite_runner, "run_artifact_validation", fake_run_artifact_validation)

    result = run_suite_validation(
        load_suite(suite_path),
        make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        artifact_path=artifact,
        run_id="suite-run",
    )

    suite_json = tmp_path / "runs" / "suite-run" / "suite.json"
    suite_html = tmp_path / "runs" / "suite-run" / "reports" / "suite.html"
    suite_junit = tmp_path / "runs" / "suite-run" / "reports" / "suite.junit.xml"
    assert result.status == "passed"
    assert suite_json.exists()
    assert suite_html.exists()
    assert suite_junit.exists()
    assert [entry.id for entry in result.entries] == ["required", "allowed"]
    assert result.entries[1].allow_failure is True
    assert result.to_dict()["summary"] == {
        "total": 2,
        "passed": 1,
        "failed": 1,
        "requiredFailed": 0,
        "allowedFailed": 1,
    }
    html = suite_html.read_text(encoding="utf-8")
    assert "local.suite" in html
    assert "allowed" in html
    junit = ET.parse(suite_junit).getroot()
    assert junit.attrib["tests"] == "2"
    assert junit.attrib["failures"] == "0"
    assert junit.attrib["skipped"] == "1"


def test_run_suite_validation_can_run_entries_in_parallel(tmp_path: Path, monkeypatch) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "SupplyScanAgent.exe").write_bytes(b"fake")

    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        """
schemaVersion: 1
id: parallel.suite
runs:
  - id: one
    scenario: scenarios/windows/supplyscan/supplyscan-agent-clean-baseline.example.yaml
  - id: two
    scenario: scenarios/windows/supplyscan/supplyscan-agent-cli.example.yaml
""",
        encoding="utf-8",
    )
    started: list[str] = []

    def fake_run_artifact_validation(scenario, config, **kwargs):
        started.append(kwargs["run_id"])
        time.sleep(0.05)
        result = RunResult(run_id=kwargs["run_id"], scenario_id=scenario.scenario_id, status="running")
        result.details["runDir"] = str(config.output_root / kwargs["run_id"])
        result.complete("passed")
        return result

    monkeypatch.setattr(suite_runner, "run_artifact_validation", fake_run_artifact_validation)

    result = run_suite_validation(
        load_suite(suite_path),
        make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        artifact_path=artifact,
        run_id="parallel-run",
        max_parallel=2,
    )

    assert result.status == "passed"
    assert [entry.id for entry in result.entries] == ["one", "two"]
    assert sorted(started) == ["parallel-run-one", "parallel-run-two"]


def test_run_suite_validation_prefixes_progress_events(tmp_path: Path, monkeypatch) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "SupplyScanAgent.exe").write_bytes(b"fake")

    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        """
schemaVersion: 1
id: progress.suite
runs:
  - id: one
    scenario: scenarios/windows/supplyscan/supplyscan-agent-clean-baseline.example.yaml
""",
        encoding="utf-8",
    )
    events: list[ProgressEvent] = []

    def fake_run_artifact_validation(scenario, config, **kwargs):
        kwargs["progress"](ProgressEvent("vm.boot.done", "VM is running", {"vmId": 9102}))
        result = RunResult(run_id=kwargs["run_id"], scenario_id=scenario.scenario_id, status="running")
        result.details["runDir"] = str(config.output_root / kwargs["run_id"])
        result.complete("passed")
        return result

    monkeypatch.setattr(suite_runner, "run_artifact_validation", fake_run_artifact_validation)

    run_suite_validation(
        load_suite(suite_path),
        make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        artifact_path=artifact,
        run_id="progress-run",
        progress=events.append,
    )

    assert events[0].message == "[one] VM is running"
    assert events[0].details["suiteEntry"] == "one"
    assert events[0].details["vmId"] == 9102
