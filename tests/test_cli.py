from __future__ import annotations

import json
from pathlib import Path

import oslab.cli
from oslab.guests.base import GuestCommandResult, GuestFileReadResult, GuestFileWriteResult
from oslab.providers.base import VmRef, VmStatus
from oslab.providers.base import GuestInfo
from oslab.commands import CommandSpec
from oslab.assertions import AssertionResult
from oslab.models.result import RunResult
from oslab.runners.proxmox_boot_smoke import BootSmokeResult
from oslab.runners.proxmox_clone_smoke import CloneSmokeResult
from oslab.runners.proxmox_artifact_smoke import ArtifactSmokeResult, ProductStepResult, ProgressEvent, UploadedArtifactFile
from oslab.runners.proxmox_fixture_smoke import FixtureSmokeItem, FixtureSmokeResult
from oslab.runners.proxmox_guest_preflight import GuestPreflightCheck, GuestPreflightResult
from oslab.cli import main


def test_validate_scenario_command_passes(capsys) -> None:
    exit_code = main(["validate-scenario", "--scenario", "scenarios/windows/supplyscan-gold-lite.yaml"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "valid scenario: supplyscan.gold-lite.windows" in captured.out


def test_preflight_command_validates_config(capsys) -> None:
    exit_code = main(
        [
            "preflight",
            "--scenario",
            "scenarios/windows/supplyscan-gold-lite.yaml",
            "--config",
            "config/oslab.local.example.yaml",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "== oslab preflight ==" in captured.out
    assert "[OK] Scenario loaded" in captured.out
    assert "[OK] Config loaded" in captured.out
    assert "[WARN] Preflight completed without creating a VM" in captured.out


def test_preflight_provider_config_check_resolves_proxmox_env(monkeypatch, capsys) -> None:
    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_ID", "root@pam!oslab")
    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_SECRET", "secret")

    exit_code = main(
        [
            "preflight",
            "--scenario",
            "scenarios/windows/supplyscan-gold-lite.yaml",
            "--config",
            "config/oslab.local.example.yaml",
            "--provider-config-check",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[OK] Provider config resolved" in captured.out
    assert "node: pve01" in captured.out
    assert "apiUrl: https://proxmox.example.local:8006/api2/json" in captured.out
    assert "tokenSecret: <redacted>" in captured.out
    assert "secret" not in captured.out


def test_preflight_provider_connectivity_check_calls_proxmox(monkeypatch, capsys) -> None:
    class FakeProxmoxClient:
        def __init__(self, config) -> None:
            self.config = config

        def get_version(self):
            return {"version": "8.2.0", "release": "1"}

    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_ID", "root@pam!oslab")
    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_SECRET", "secret")
    monkeypatch.setattr(oslab.cli, "ProxmoxClient", FakeProxmoxClient)

    exit_code = main(
        [
            "preflight",
            "--scenario",
            "scenarios/windows/supplyscan-gold-lite.yaml",
            "--config",
            "config/oslab.local.example.yaml",
            "--provider-connectivity-check",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[..] Proxmox API connectivity" in captured.out
    assert "[OK] Proxmox API connectivity" in captured.out
    assert "endpoint: GET /version" in captured.out
    assert "version: 8.2.0" in captured.out
    assert "release: 1" in captured.out


def test_preflight_provider_resource_check_prints_lab_state(monkeypatch, capsys) -> None:
    class FakeProxmoxClient:
        def __init__(self, config) -> None:
            self.config = config

        def get_version(self):
            return {"version": "9.1.1", "release": "9.1"}

        def list_nodes(self):
            return [{"node": "pve01"}]

        def list_vm_resources(self):
            return [
                {
                    "vmid": 9101,
                    "name": "windows11-template-qga-9101",
                    "node": "pve01",
                    "status": "stopped",
                },
                {"vmid": 9102, "name": "validation-old", "node": "pve01", "status": "stopped"},
            ]

        def get_vm_config(self, vmid: int, *, node: str | None = None):
            return {"template": 1}

    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_ID", "root@pam!oslab")
    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_SECRET", "secret")
    monkeypatch.setattr(oslab.cli, "ProxmoxClient", FakeProxmoxClient)

    exit_code = main(
        [
            "preflight",
            "--scenario",
            "scenarios/windows/supplyscan-gold-lite.yaml",
            "--config",
            "config/oslab.local.example.yaml",
            "--provider-resource-check",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[OK] Configured Proxmox node exists" in captured.out
    assert "[OK] Template VMID exists" in captured.out
    assert "[OK] Template flag confirmed" in captured.out
    assert "recommendedVmId: 9103" in captured.out


def test_preflight_can_load_env_file(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("OSLAB_PROXMOX_TOKEN_ID", raising=False)
    monkeypatch.delenv("OSLAB_PROXMOX_TOKEN_SECRET", raising=False)
    env_file = tmp_path / "oslab.local.env"
    env_file.write_text(
        """
OSLAB_PROXMOX_TOKEN_ID=root@pam!oslab
OSLAB_PROXMOX_TOKEN_SECRET=secret-from-file
""",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "preflight",
            "--scenario",
            "scenarios/windows/supplyscan-gold-lite.yaml",
            "--config",
            "config/oslab.local.example.yaml",
            "--env-file",
            str(env_file),
            "--provider-config-check",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[OK] Env file loaded" in captured.out
    assert "loadedKeys: OSLAB_PROXMOX_TOKEN_ID, OSLAB_PROXMOX_TOKEN_SECRET" in captured.out
    assert "secret-from-file" not in captured.out
    assert "tokenSecret: <redacted>" in captured.out


def test_preflight_error_output_is_structured(capsys) -> None:
    exit_code = main(
        [
            "preflight",
            "--scenario",
            "scenarios/windows/supplyscan-gold-lite.yaml",
            "--provider-config-check",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "[FAIL]" in captured.err
    assert "providerDefaults.proxmox.apiUrl" in captured.err


def test_run_command_writes_skeleton_result(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.yaml"
    output_root = tmp_path / "runs"
    config_path.write_text(
        f"""
runDefaults:
  outputRoot: "{output_root.as_posix()}"
  timeoutMinutes: 45
  keepVmOnFailure: false
""",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run",
            "--scenario",
            "scenarios/windows/supplyscan-gold-lite.yaml",
            "--config",
            str(config_path),
            "--run-id",
            "test-run",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "skeleton run complete: test-run" in captured.out

    run_json = output_root / "test-run" / "run.json"
    result_json = output_root / "test-run" / "reports" / "result.json"
    assert run_json.exists()
    assert result_json.exists()

    payload = json.loads(run_json.read_text(encoding="utf-8"))
    assert payload["runId"] == "test-run"
    assert payload["scenarioId"] == "supplyscan.gold-lite.windows"
    assert payload["status"] == "passed"
    assert payload["details"]["mode"] == "skeleton"


def test_run_command_executes_artifact_validation(tmp_path: Path, monkeypatch, capsys) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "SupplyScan.exe").write_bytes(b"fake")

    def fake_run_artifact_validation(scenario, config, **kwargs):
        progress = kwargs.get("progress")
        assert progress is not None
        progress(ProgressEvent("vm.boot.done", "VM is running", {"vmId": 9102}))
        assert kwargs["artifact_path"] == artifact
        assert kwargs["run_id"] == "full-run"
        result = RunResult(run_id="full-run", scenario_id=scenario.scenario_id, status="running")
        result.reports = {
            "runJson": r"runs\full-run\run.json",
            "json": r"runs\full-run\reports\result.json",
            "html": r"runs\full-run\reports\result.html",
        }
        result.complete("passed")
        return result

    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_ID", "root@pam!oslab")
    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_SECRET", "secret")
    monkeypatch.setattr(oslab.cli, "run_artifact_validation", fake_run_artifact_validation)

    exit_code = main(
        [
            "run",
            "--scenario",
            "scenarios/windows/supplyscan-gold-lite.yaml",
            "--config",
            "config/oslab.local.example.yaml",
            "--artifact-path",
            str(artifact),
            "--run-id",
            "full-run",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "== oslab run ==" in captured.out
    assert "[OK] VM is running" in captured.out
    assert "[OK] Run completed" in captured.out
    assert "runId: full-run" in captured.out
    assert "report:html: runs\\full-run\\reports\\result.html" in captured.out


def test_inspect_result_prints_human_summary(tmp_path: Path, capsys) -> None:
    run_dir = tmp_path / "runs" / "failed-run"
    (run_dir / "raw").mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "runId": "failed-run",
                "scenarioId": "supplyscan.agent-cli.windows",
                "status": "failed",
                "failureClass": "product_execution_failure",
                "selectedGuestChannel": "qemuAgent",
                "reports": {"html": r"runs\failed-run\reports\result.html"},
                "details": {
                    "runDir": r"runs\failed-run",
                    "vm": {"id": 9102, "destroyed": True, "kept": False},
                    "assertions": {"total": 0, "failed": 0},
                    "outputs": {
                        "raw": None,
                        "normalized": None,
                        "productSteps": r"runs\failed-run\raw\product-steps.json",
                        "collectedBytes": None,
                    },
                    "preflight": {"total": 7, "failed": 1},
                    "fixtures": {
                        "total": 1,
                        "failed": 1,
                        "items": [
                            {
                                "id": "demo-python-runtime",
                                "passed": False,
                                "message": "Fixture command failed",
                                "exitCode": 1,
                                "stdout": "",
                                "stderr": "Python runtime was not found.\n위치 C:\\Oslab\\fixtures\\demo-python-runtime.ps1:15 문자:3",
                            }
                        ],
                    },
                    "scan": {
                        "ok": True,
                        "outputWritten": True,
                        "bytesWritten": 123,
                        "scanId": "scan-001",
                        "uploadRequested": True,
                        "uploadSuccess": False,
                    },
                    "logs": {"productStep.register.stdout": r"runs\failed-run\logs\product-step-register.stdout.log"},
                },
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "raw" / "product-steps.json").write_text(
        json.dumps(
            [
                {
                    "id": "register",
                    "passed": False,
                    "exitCode": 0,
                    "message": "Product step stdout reported failure",
                    "stdoutJson": {"ok": False, "errorCode": "access_token_missing"},
                },
                {
                    "id": "scan",
                    "passed": True,
                    "exitCode": 0,
                    "message": "Product step passed",
                    "stdoutJson": {
                        "ok": True,
                        "outputWritten": True,
                        "bytesWritten": 123,
                        "scanId": "scan-001",
                        "uploadRequested": True,
                        "uploadSuccess": False,
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(["inspect-result", "--run-dir", str(run_dir)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "== oslab inspect result ==" in captured.out
    assert "runId: failed-run" in captured.out
    assert "[FAIL] Run failed" in captured.out
    assert "failureClass: product_execution_failure" in captured.out
    assert "productSteps: runs\\failed-run\\raw\\product-steps.json" in captured.out
    assert "preflight: 7 total, 1 failed" in captured.out
    assert "fixtures: 1 total, 1 failed" in captured.out
    assert "[FAIL] fixture:demo-python-runtime" in captured.out
    assert "message: Fixture command failed" in captured.out
    assert "stderr: Python runtime was not found." in captured.out
    assert "[OK] Scan summary" in captured.out
    assert "scan.outputWritten: True" in captured.out
    assert "scan.bytesWritten: 123" in captured.out
    assert "scan.uploadRequested: True" in captured.out
    assert "scan.uploadSuccess: False" in captured.out
    assert "[FAIL] step:register" in captured.out
    assert "stdoutJson.ok: False" in captured.out
    assert "stdoutJson.errorCode: access_token_missing" in captured.out
    assert "[OK] step:scan" in captured.out
    assert "stdoutJson.outputWritten: True" in captured.out
    assert "stdoutJson.bytesWritten: 123" in captured.out
    assert "stdoutJson.uploadRequested: True" in captured.out
    assert "stdoutJson.uploadSuccess: False" in captured.out
    assert "report:html: runs\\failed-run\\reports\\result.html" in captured.out


def test_inspect_result_prints_command_result_summary(tmp_path: Path, capsys) -> None:
    run_dir = tmp_path / "runs" / "command-run"
    (run_dir / "normalized").mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "runId": "command-run",
                "scenarioId": "demo.python-hello.windows",
                "status": "passed",
                "failureClass": None,
                "selectedGuestChannel": "qemuAgent",
                "reports": {},
                "details": {
                    "runDir": r"runs\command-run",
                    "outputs": {
                        "raw": r"runs\command-run\raw\actual-output.json",
                        "normalized": r"runs\command-run\normalized\command-result.json",
                        "collectedBytes": 128,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "normalized" / "command-result.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "kind": "commandResult",
                "command": "python hello.py",
                "exitCode": 0,
                "stdout": "hello from python\n",
                "stderr": "",
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["inspect-result", "--run-dir", str(run_dir)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[OK] Command result" in captured.out
    assert "command: python hello.py" in captured.out
    assert "exitCode: 0" in captured.out
    assert "stdout: hello from python" in captured.out
    assert "stderr: <empty>" in captured.out


def test_inspect_result_json_mode_prints_run_json(tmp_path: Path, capsys) -> None:
    run_dir = tmp_path / "runs" / "json-run"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps({"runId": "json-run", "scenarioId": "demo", "status": "passed"}),
        encoding="utf-8",
    )

    exit_code = main(["inspect-result", "--run-dir", str(run_dir), "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["runId"] == "json-run"


def test_clone_smoke_command_prints_result(monkeypatch, capsys) -> None:
    def fake_clone_smoke(**kwargs):
        return CloneSmokeResult(
            vm=VmRef(vm_id=9101, name="oslab-supplyscan-gold-lite-windows-9101", node="softverse"),
            status=VmStatus(vm_id=9101, status="stopped"),
            clone_name="oslab-supplyscan-gold-lite-windows-9101",
            destroyed=True,
            kept=False,
        )

    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_ID", "root@pam!oslab")
    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_SECRET", "secret")
    monkeypatch.setattr(oslab.cli, "run_proxmox_clone_smoke", fake_clone_smoke)

    exit_code = main(
        [
            "clone-smoke",
            "--scenario",
            "scenarios/windows/supplyscan-gold-lite.yaml",
            "--config",
            "config/oslab.local.example.yaml",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "== oslab clone smoke ==" in captured.out
    assert "[OK] Clone smoke completed" in captured.out
    assert "cloneVmId: 9101" in captured.out
    assert "destroyed: true" in captured.out


def test_boot_smoke_command_prints_result(monkeypatch, capsys) -> None:
    def fake_boot_smoke(**kwargs):
        return BootSmokeResult(
            vm=VmRef(vm_id=9101, name="oslab-supplyscan-gold-lite-windows-9101", node="softverse"),
            clone_name="oslab-supplyscan-gold-lite-windows-9101",
            status=VmStatus(vm_id=9101, status="running"),
            guest_info=GuestInfo(vm_id=9101, raw={"result": []}),
            started=True,
            destroyed=True,
            kept=False,
        )

    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_ID", "root@pam!oslab")
    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_SECRET", "secret")
    monkeypatch.setattr(oslab.cli, "run_proxmox_boot_smoke", fake_boot_smoke)

    exit_code = main(
        [
            "boot-smoke",
            "--scenario",
            "scenarios/windows/supplyscan-gold-lite.yaml",
            "--config",
            "config/oslab.local.example.yaml",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "== oslab boot smoke ==" in captured.out
    assert "[OK] Boot smoke completed" in captured.out
    assert "cloneVmId: 9101" in captured.out
    assert "cloneStatus: running" in captured.out
    assert "guestInfo: available" in captured.out


def test_guest_preflight_command_prints_checks(monkeypatch, capsys) -> None:
    def fake_guest_preflight(**kwargs):
        return GuestPreflightResult(
            vm=VmRef(vm_id=9102, name="oslab-supplyscan-gold-lite-windows-9102", node="softverse"),
            clone_name="oslab-supplyscan-gold-lite-windows-9102",
            status=VmStatus(vm_id=9102, status="running"),
            guest_info=GuestInfo(vm_id=9102, raw={"result": []}),
            checks=[
                GuestPreflightCheck("powershell.version", True, "Command check passed", {"stdout": "5.1"}),
                GuestPreflightCheck("windows.admin", True, "Command check passed", {"stdout": "True"}),
            ],
            started=True,
            destroyed=True,
            kept=False,
        )

    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_ID", "root@pam!oslab")
    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_SECRET", "secret")
    monkeypatch.setattr(oslab.cli, "run_proxmox_guest_preflight", fake_guest_preflight)

    exit_code = main(
        [
            "guest-preflight",
            "--scenario",
            "scenarios/windows/supplyscan-gold-lite.yaml",
            "--config",
            "config/oslab.local.example.yaml",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "== oslab guest preflight ==" in captured.out
    assert "[OK] Guest preflight completed" in captured.out
    assert "cloneVmId: 9102" in captured.out
    assert "[OK] check:powershell.version" in captured.out
    assert "[OK] check:windows.admin" in captured.out


def test_fixture_smoke_command_prints_fixture_result(monkeypatch, capsys) -> None:
    def fake_fixture_smoke(**kwargs):
        return FixtureSmokeResult(
            vm=VmRef(vm_id=9102, name="oslab-supplyscan-gold-lite-windows-9102", node="softverse"),
            clone_name="oslab-supplyscan-gold-lite-windows-9102",
            status=VmStatus(vm_id=9102, status="running"),
            guest_info=GuestInfo(vm_id=9102, raw={"result": []}),
            fixtures=[
                FixtureSmokeItem(
                    id="gold-lite",
                    fixture_type="powershell",
                    source=Path("validation/fixtures/windows/gold-lite.ps1"),
                    guest_path=r"C:\Oslab\fixtures\gold-lite.ps1",
                    expected_output=r"C:\Oslab\expected_inventory.json",
                    uploaded_bytes=512,
                    exit_code=0,
                    stdout="manifest written\n",
                    stderr="",
                    collected_bytes=256,
                    collected_json={"schema_version": 1},
                    local_output_path=Path("runs/fixture-smoke/supplyscan.gold-lite.windows/gold-lite.expected_inventory.json"),
                    passed=True,
                )
            ],
            started=True,
            destroyed=True,
            kept=False,
        )

    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_ID", "root@pam!oslab")
    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_SECRET", "secret")
    monkeypatch.setattr(oslab.cli, "run_proxmox_fixture_smoke", fake_fixture_smoke)

    exit_code = main(
        [
            "fixture-smoke",
            "--scenario",
            "scenarios/windows/supplyscan-gold-lite.yaml",
            "--config",
            "config/oslab.local.example.yaml",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "== oslab fixture smoke ==" in captured.out
    assert "[OK] Fixture smoke completed" in captured.out
    assert "cloneVmId: 9102" in captured.out
    assert "[OK] fixture:gold-lite" in captured.out
    assert "collectedBytes: 256" in captured.out


def test_artifact_smoke_command_prints_artifact_result(tmp_path: Path, monkeypatch, capsys) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    local_file = artifact / "SupplyScan.exe"
    local_file.write_bytes(b"fake")

    def fake_artifact_smoke(**kwargs):
        progress = kwargs.get("progress")
        assert progress is not None
        progress(ProgressEvent("vm.clone.start", "Create ephemeral VM clone", {"vmId": 9102}))
        progress(ProgressEvent("vm.boot.done", "VM is running", {"vmId": 9102, "status": "running"}))
        progress(ProgressEvent("artifact.upload.progress", "Uploading artifact archive", {"percent": "50%"}))
        progress(ProgressEvent("artifact.upload.done", "Artifact folder uploaded", {"files": 1, "bytes": 4}))
        return ArtifactSmokeResult(
            vm=VmRef(vm_id=9102, name="oslab-supplyscan-gold-lite-windows-9102", node="softverse"),
            clone_name="oslab-supplyscan-gold-lite-windows-9102",
            status=VmStatus(vm_id=9102, status="running"),
            guest_info=GuestInfo(vm_id=9102, raw={"result": []}),
            artifact_path=artifact,
            artifact_destination=r"C:\Oslab\artifact",
            uploaded_files=[
                UploadedArtifactFile(local_path=local_file, guest_path=r"C:\Oslab\artifact\SupplyScan.exe", bytes_written=4)
            ],
            command=CommandSpec(
                shell="powershell",
                template='& "{ArtifactDir}\\SupplyScan.exe" --access-token "{AccessToken}" --output "{OutputPath}"',
                rendered='& "C:\\Oslab\\artifact\\SupplyScan.exe" --access-token "secret-from-test" --output "C:\\Oslab\\scan-result.json"',
                redacted='& "C:\\Oslab\\artifact\\SupplyScan.exe" --access-token "<redacted>" --output "C:\\Oslab\\scan-result.json"',
            ),
            exit_code=0,
            stdout="fake supplyscan executed\n",
            stderr="",
            output_path=r"C:\Oslab\scan-result.json",
            output_adapter="supplyscan.inventory",
            collected_bytes=32,
            collected_json={"records": []},
            local_output_path=Path("runs/artifact-smoke/supplyscan.gold-lite.windows/scan-result.json"),
            normalized_json={"records": []},
            local_normalized_path=Path("runs/artifact-smoke/supplyscan.gold-lite.windows/inventory.normalized.json"),
            started=True,
            destroyed=True,
            kept=False,
            passed=True,
            message="Artifact smoke passed",
            assertions=[
                AssertionResult(
                    id="fake-git",
                    type="inventory.contains",
                    passed=True,
                    message="Inventory record matched",
                )
            ],
        )

    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_ID", "root@pam!oslab")
    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_SECRET", "secret")
    monkeypatch.setattr(oslab.cli, "run_proxmox_artifact_smoke", fake_artifact_smoke)

    exit_code = main(
        [
            "artifact-smoke",
            "--scenario",
            "scenarios/windows/supplyscan-gold-lite.yaml",
            "--config",
            "config/oslab.local.example.yaml",
            "--artifact-path",
            str(artifact),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "== oslab artifact smoke ==" in captured.out
    assert "[..] Create ephemeral VM clone" in captured.out
    assert "[OK] VM is running" in captured.out
    assert "[..] Uploading artifact archive" in captured.out
    assert "percent: 50%" in captured.out
    assert "[OK] Artifact folder uploaded" in captured.out
    assert "[OK] Artifact smoke completed" in captured.out
    assert "cloneVmId: 9102" in captured.out
    assert "uploadedFiles: 1" in captured.out
    assert "collectedBytes: 32" in captured.out
    assert "outputAdapter: supplyscan.inventory" in captured.out
    assert "localNormalizedPath: runs\\artifact-smoke\\supplyscan.gold-lite.windows\\inventory.normalized.json" in captured.out
    assert "[OK] assertion:fake-git" in captured.out
    assert "secret-from-test" not in captured.out
    assert '--access-token "<redacted>"' in captured.out


def test_artifact_smoke_command_prints_product_steps_without_secret(tmp_path: Path, monkeypatch, capsys) -> None:
    artifact = tmp_path / "fake-agent-installer.ps1"
    artifact.write_text("fake", encoding="utf-8")

    def fake_artifact_smoke(**kwargs):
        return ArtifactSmokeResult(
            vm=VmRef(vm_id=9102, name="oslab-fake-agent-cli-smoke-windows-9102", node="softverse"),
            clone_name="oslab-fake-agent-cli-smoke-windows-9102",
            status=VmStatus(vm_id=9102, status="running"),
            guest_info=GuestInfo(vm_id=9102, raw={"result": []}),
            artifact_path=artifact,
            artifact_destination=r"C:\Oslab\installer\fake-agent-installer.ps1",
            uploaded_files=[
                UploadedArtifactFile(
                    local_path=artifact,
                    guest_path=r"C:\Oslab\installer\fake-agent-installer.ps1",
                    bytes_written=4,
                )
            ],
            install_command=CommandSpec(
                shell="powershell",
                template='& "{InstallerPath}" -InstallDir "C:\\Oslab\\agent"',
                rendered='& "C:\\Oslab\\installer\\fake-agent-installer.ps1" -InstallDir "C:\\Oslab\\agent"',
            ),
            install_exit_code=0,
            command=CommandSpec(
                shell="powershell",
                template='& "C:\\Oslab\\agent\\fake-agent.ps1" scan --output "{OutputPath}" --json',
                rendered='& "C:\\Oslab\\agent\\fake-agent.ps1" scan --output "C:\\Oslab\\scan-result.json" --json',
            ),
            exit_code=0,
            stdout='{"ok":true,"step":"scan"}\n',
            stderr="",
            output_path=r"C:\Oslab\scan-result.json",
            output_adapter="canonical.inventory",
            collected_bytes=32,
            collected_json={"records": []},
            local_output_path=Path("runs/artifact-smoke/fake.agent-cli-smoke.windows/scan-result.json"),
            normalized_json={"records": []},
            local_normalized_path=Path("runs/artifact-smoke/fake.agent-cli-smoke.windows/inventory.normalized.json"),
            started=True,
            destroyed=True,
            kept=False,
            passed=True,
            message="Artifact smoke passed",
            product_steps=[
                ProductStepResult(
                    id="register",
                    command=CommandSpec(
                        shell="powershell",
                        template='& "C:\\Oslab\\agent\\fake-agent.ps1" register --access-token "{SupplyScanAccessToken}" --json',
                        rendered='& "C:\\Oslab\\agent\\fake-agent.ps1" register --access-token "secret-agent-token" --json',
                        redacted='& "C:\\Oslab\\agent\\fake-agent.ps1" register --access-token "<redacted>" --json',
                    ),
                    exit_code=0,
                    stdout='{"ok":true,"step":"register"}\n',
                    stderr="",
                    stdout_json={"ok": True, "step": "register"},
                    passed=True,
                    message="Product step passed",
                )
            ],
            local_product_steps_path=Path("runs/artifact-smoke/fake.agent-cli-smoke.windows/product-steps.json"),
        )

    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_ID", "root@pam!oslab")
    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_SECRET", "secret")
    monkeypatch.setattr(oslab.cli, "run_proxmox_artifact_smoke", fake_artifact_smoke)

    exit_code = main(
        [
            "artifact-smoke",
            "--scenario",
            "scenarios/windows/fake-agent-cli-smoke.example.yaml",
            "--config",
            "config/oslab.local.example.yaml",
            "--artifact-path",
            str(artifact),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[OK] productStep:register" in captured.out
    assert "stdoutJson: available" in captured.out
    assert "localProductStepsPath: runs\\artifact-smoke\\fake.agent-cli-smoke.windows\\product-steps.json" in captured.out
    assert "secret-agent-token" not in captured.out
    assert '--access-token "<redacted>"' in captured.out


def test_assert_result_command_evaluates_local_json(tmp_path: Path, capsys) -> None:
    actual_json = tmp_path / "scan-result.json"
    actual_json.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "kind": "inventory",
                "records": [
                    {
                        "name": "Git",
                        "version": "2.0.0",
                        "sources": ["Registry"],
                        "evidence": [{"type": "registry", "source": "Registry", "path": "HKLM"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "assert-result",
            "--scenario",
            "scenarios/windows/fake-artifact-smoke.example.yaml",
            "--actual-json",
            str(actual_json),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "== oslab assert result ==" in captured.out
    assert "[OK] Assertions passed" in captured.out
    assert "[OK] assertion:fake-git" in captured.out
    assert "adapter: canonical.inventory" in captured.out


def test_normalize_output_command_writes_canonical_inventory(tmp_path: Path, capsys) -> None:
    raw_json = tmp_path / "supplyscan-raw.json"
    output_json = tmp_path / "inventory.json"
    raw_json.write_text(
        json.dumps(
            {
                "software": [
                    {
                        "sw_name": "Git",
                        "sw_version": "2.0.0",
                        "sw_publisher": "Git Project",
                        "sw_scan_method": "registry, pe",
                        "registry_path": r"HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\Git",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "normalize-output",
            "--adapter",
            "supplyscan.inventory",
            "--input-json",
            str(raw_json),
            "--output-json",
            str(output_json),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["kind"] == "inventory"
    assert payload["records"][0]["name"] == "Git"
    assert payload["records"][0]["sources"] == ["Registry", "PE"]
    assert "[OK] Output normalized" in captured.out
    assert "adapter: supplyscan.inventory" in captured.out


def test_analyze_inventory_command_writes_analysis(tmp_path: Path, capsys) -> None:
    inventory_json = tmp_path / "inventory.json"
    output_json = tmp_path / "reports" / "inventory.analysis.json"
    inventory_json.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "kind": "inventory",
                "records": [
                    {
                        "name": "Git",
                        "version": "2.0.0",
                        "publisher": "Git Project",
                        "sources": ["Registry"],
                        "confidence": "high",
                        "evidence": [{"path": r"HKLM\Software\Git"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "analyze-inventory",
            "--inventory-json",
            str(inventory_json),
            "--output-json",
            str(output_json),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["kind"] == "inventoryAnalysis"
    assert payload["recordCount"] == 1
    assert payload["sourceCounts"] == {"Registry": 1}
    assert "== oslab analyze inventory ==" in captured.out
    assert "[OK] Inventory analyzed" in captured.out
    assert "records: 1" in captured.out


def test_qga_exec_command_prints_stdout_and_exit_code(monkeypatch, capsys) -> None:
    class FakeQemuAgentChannel:
        def __init__(self, client) -> None:
            self.client = client

        def execute(self, vm, command, *, timeout_seconds: int, poll_interval_seconds: float):
            assert vm.vm_id == 9101
            assert command == ["cmd.exe", "/c", "echo hello"]
            assert timeout_seconds == 10
            assert poll_interval_seconds == 0
            return GuestCommandResult(
                command=tuple(command),
                exited=True,
                exit_code=0,
                stdout="hello\n",
                stderr="",
            )

    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_ID", "root@pam!oslab")
    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_SECRET", "secret")
    monkeypatch.setattr(oslab.cli, "ProxmoxClient", lambda config: object())
    monkeypatch.setattr(oslab.cli, "QemuAgentChannel", FakeQemuAgentChannel)

    exit_code = main(
        [
            "qga-exec",
            "--config",
            "config/oslab.local.example.yaml",
            "--vm-id",
            "9101",
            "--timeout-seconds",
            "10",
            "--poll-interval-seconds",
            "0",
            "--",
            "cmd.exe",
            "/c",
            "echo hello",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "== oslab qga exec ==" in captured.out
    assert "[OK] QEMU Guest Agent command completed" in captured.out
    assert "exitCode: 0" in captured.out
    assert "== stdout ==" in captured.out
    assert "hello" in captured.out
    assert "secret" not in captured.out


def test_qga_exec_requires_command_after_separator(monkeypatch, capsys) -> None:
    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_ID", "root@pam!oslab")
    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_SECRET", "secret")

    exit_code = main(
        [
            "qga-exec",
            "--config",
            "config/oslab.local.example.yaml",
            "--vm-id",
            "9101",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Guest command is required after `--`" in captured.err


def test_qga_upload_reads_local_file_and_prints_result(tmp_path: Path, monkeypatch, capsys) -> None:
    local_file = tmp_path / "fixture.ps1"
    local_file.write_bytes(b"Write-Output 'hello'\n")

    class FakeQemuAgentChannel:
        def __init__(self, client) -> None:
            self.client = client

        def upload_bytes(self, vm, guest_path: str, content: bytes):
            assert vm.vm_id == 9102
            assert guest_path == r"C:\Oslab\fixture.ps1"
            assert content == b"Write-Output 'hello'\n"
            return GuestFileWriteResult(guest_path=guest_path, bytes_written=len(content))

    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_ID", "root@pam!oslab")
    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_SECRET", "secret")
    monkeypatch.setattr(oslab.cli, "ProxmoxClient", lambda config: object())
    monkeypatch.setattr(oslab.cli, "QemuAgentChannel", FakeQemuAgentChannel)

    exit_code = main(
        [
            "qga-upload",
            "--config",
            "config/oslab.local.example.yaml",
            "--vm-id",
            "9102",
            "--local-path",
            str(local_file),
            "--guest-path",
            r"C:\Oslab\fixture.ps1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "== oslab qga upload ==" in captured.out
    assert "[OK] QEMU Guest Agent file upload completed" in captured.out
    assert "bytesWritten: 21" in captured.out


def test_qga_download_writes_local_file(tmp_path: Path, monkeypatch, capsys) -> None:
    output_file = tmp_path / "downloads" / "result.json"

    class FakeQemuAgentChannel:
        def __init__(self, client) -> None:
            self.client = client

        def download_text(self, vm, guest_path: str):
            assert vm.vm_id == 9102
            assert guest_path == r"C:\Oslab\result.json"
            return GuestFileReadResult(guest_path=guest_path, content='{"ok": true}\n')

    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_ID", "root@pam!oslab")
    monkeypatch.setenv("OSLAB_PROXMOX_TOKEN_SECRET", "secret")
    monkeypatch.setattr(oslab.cli, "ProxmoxClient", lambda config: object())
    monkeypatch.setattr(oslab.cli, "QemuAgentChannel", FakeQemuAgentChannel)

    exit_code = main(
        [
            "qga-download",
            "--config",
            "config/oslab.local.example.yaml",
            "--vm-id",
            "9102",
            "--guest-path",
            r"C:\Oslab\result.json",
            "--local-path",
            str(output_file),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert output_file.read_text(encoding="utf-8") == '{"ok": true}\n'
    assert "== oslab qga download ==" in captured.out
    assert "[OK] QEMU Guest Agent file download completed" in captured.out
    assert "bytesRead: 13" in captured.out
