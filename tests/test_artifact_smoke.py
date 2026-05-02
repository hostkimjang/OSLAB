from __future__ import annotations

import base64
import io
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from oslab.config import OslabConfig
from oslab.errors import ConfigError
from oslab.models.scenario import load_scenario
from oslab.providers.proxmox import ProxmoxConfig
from oslab.runners import proxmox_artifact_smoke
from oslab.runners.scenario_runner import run_artifact_validation
from oslab.runners.proxmox_artifact_smoke import run_proxmox_artifact_smoke


OUTPUT_JSON = {
    "schemaVersion": 1,
    "kind": "inventory",
    "records": [
        {
            "name": "Git",
            "version": "2.0.0",
            "publisher": "Fake Scanner",
            "sources": ["Registry"],
            "confidence": "high",
            "evidence": [
                {
                    "type": "registry",
                    "source": "Registry",
                    "path": r"HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\Git",
                }
            ],
            "metadata": {},
        }
    ],
}


class FakeProxmoxClient:
    def __init__(self, config: ProxmoxConfig, *, artifact_exit_code: int = 0) -> None:
        self.config = config
        self.artifact_exit_code = artifact_exit_code
        self.next_pid = 100
        self.status_by_pid: dict[int, dict] = {}
        self.files: dict[str, bytes] = {}
        self.commands: list[list[str]] = []
        self.cloned_vmids: list[int] = []
        self.started_vmids: list[int] = []
        self.stopped_vmids: list[int] = []
        self.destroyed_vmids: list[int] = []

    def list_nodes(self):
        return [{"node": "softverse"}]

    def list_vm_resources(self):
        return [
            {
                "vmid": 9101,
                "name": "windows11-template-qga-9101",
                "node": "softverse",
                "status": "stopped",
                "template": 1,
            }
        ]

    def get_vm_config(self, vmid: int, *, node: str | None = None):
        return {"template": 1}

    def clone_vm(self, *, template_vmid: int, new_vmid: int, name: str, full_clone: bool):
        self.cloned_vmids.append(new_vmid)
        return "UPID:softverse:clone"

    def start_vm(self, vmid: int):
        self.started_vmids.append(vmid)
        return "UPID:softverse:start"

    def stop_vm(self, vmid: int):
        self.stopped_vmids.append(vmid)
        return "UPID:softverse:stop"

    def destroy_vm(self, vmid: int, *, purge: bool = True):
        self.destroyed_vmids.append(vmid)
        return "UPID:softverse:destroy"

    def wait_for_task(self, task_id: str, *, failure_class: str = "provider_failure", **kwargs):
        return {"status": "stopped", "exitstatus": "OK"}

    def get_vm_status(self, vmid: int):
        if vmid in self.started_vmids and vmid not in self.stopped_vmids:
            return {"status": "running", "vmid": vmid}
        return {"status": "stopped", "vmid": vmid}

    def get_guest_network_interfaces(self, vmid: int):
        return {"result": [{"name": "Ethernet", "ip-addresses": [{"ip-address": "192.168.1.10"}]}]}

    def guest_exec(self, vmid: int, command: list[str]):
        pid = self.next_pid
        self.next_pid += 1
        self.commands.append(command)
        command_text = " ".join(command)
        if "$PSVersionTable.PSVersion" in command_text:
            exit_code = 0
            stdout = "5.1.22621.1\r\n"
        elif "IsInRole" in command_text:
            exit_code = 0
            stdout = "True\r\n"
        elif "Get-ExecutionPolicy" in command_text:
            exit_code = 0
            stdout = json.dumps([{"Scope": "LocalMachine", "ExecutionPolicy": "RemoteSigned"}]) + "\r\n"
        elif "Test-Path -LiteralPath $path" in command_text and "SupplyScanAgent\\config.ini" in command_text:
            exit_code = 0
            stdout = "absent\r\n"
        elif "-File C:\\Oslab\\fixtures\\gold-lite.ps1" in command_text:
            exit_code = 0
            stdout = "fixture manifest written\r\n"
            self.files["C:\\Oslab\\expected_inventory.json"] = json.dumps(OUTPUT_JSON).encode("utf-8")
        elif "-File C:\\Oslab\\fixtures\\demo-python-runtime.ps1" in command_text:
            exit_code = 0
            stdout = "Python runtime ready: C:\\Python\\python.exe\r\n"
            self.files["C:\\Oslab\\demo-python-runtime.json"] = json.dumps(
                {
                    "schemaVersion": 1,
                    "kind": "demoRuntime",
                    "demo": "python-hello",
                    "ready": True,
                    "runtime": "python",
                    "executable": "C:\\Python\\python.exe",
                    "version": "Python 3.13.0",
                }
            ).encode("utf-8")
        elif "-File C:\\Oslab\\fixtures\\demo-c-compiler.ps1" in command_text:
            exit_code = 0
            stdout = "C compiler ready: gcc at C:\\msys64\\ucrt64\\bin\\gcc.exe\r\n"
            self.files["C:\\Oslab\\demo-c-compiler.json"] = json.dumps(
                {
                    "schemaVersion": 1,
                    "kind": "demoRuntime",
                    "demo": "c-hello",
                    "ready": True,
                    "runtime": "c-compiler",
                    "compiler": "gcc",
                    "executable": "C:\\msys64\\ucrt64\\bin\\gcc.exe",
                }
            ).encode("utf-8")
        elif "run-python-demo.ps1" in command_text:
            exit_code = 0
            stdout = "python demo wrote command result\r\n"
            self.files["C:\\Oslab\\command-result.json"] = json.dumps(
                {
                    "schemaVersion": 1,
                    "kind": "commandResult",
                    "command": "python hello.py",
                    "exitCode": 0,
                    "stdout": "hello from python\n",
                    "stderr": "",
                    "metadata": {"runtime": "python"},
                }
            ).encode("utf-8")
        elif "run-c-demo.ps1" in command_text:
            exit_code = 0
            stdout = "c demo wrote command result\r\n"
            self.files["C:\\Oslab\\command-result.json"] = json.dumps(
                {
                    "schemaVersion": 1,
                    "kind": "commandResult",
                    "command": "compile and run hello.c",
                    "exitCode": 0,
                    "stdout": "hello from c\n",
                    "stderr": "",
                    "metadata": {"language": "c"},
                }
            ).encode("utf-8")
        elif "fake-agent.ps1" in command_text:
            exit_code = self.artifact_exit_code
            if " register " in command_text:
                stdout = json.dumps({"ok": True, "step": "register", "assetName": "oslab-test"}) + "\n"
            elif " status " in command_text:
                stdout = json.dumps(
                    {"ok": True, "step": "status", "registered": True, "tokenEcho": "secret-agent-token"}
                ) + "\n"
            elif " scan " in command_text:
                stdout = json.dumps({"ok": True, "step": "scan", "records": 1}) + "\n"
                if exit_code == 0:
                    self.files["C:\\Oslab\\scan-result.json"] = json.dumps(OUTPUT_JSON).encode("utf-8")
            else:
                exit_code = 3
                stdout = json.dumps({"artifactType": "supplyscan-agent-cli-failure", "step": "dispatch"}) + "\n"
        elif "SupplyScan.exe" in command_text or "fake-scanner.ps1" in command_text:
            exit_code = self.artifact_exit_code
            stdout = "fake supplyscan executed\r\n"
            if exit_code == 0:
                self.files["C:\\Oslab\\scan-result.json"] = json.dumps(OUTPUT_JSON).encode("utf-8")
        else:
            exit_code = 0
            stdout = ""
        self.status_by_pid[pid] = {"exited": 1, "exitcode": exit_code, "out-data": stdout, "err-data": ""}
        return {"pid": pid}

    def get_guest_exec_status(self, vmid: int, pid: int):
        return self.status_by_pid[pid]

    def guest_file_write(self, vmid: int, guest_path: str, content: str, *, encode: bool = True):
        self.files[guest_path] = base64.b64decode(content) if encode is False else content.encode("utf-8")

    def guest_file_read(self, vmid: int, guest_path: str):
        return {"content": self.files[guest_path].decode("utf-8"), "truncated": 0}


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


def make_artifact(tmp_path: Path) -> Path:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "SupplyScan.exe").write_bytes(b"fake exe")
    nested = artifact / "data"
    nested.mkdir()
    (nested / "config.json").write_text('{"mode":"test"}\n', encoding="utf-8")
    return artifact


def make_installer_artifact(tmp_path: Path) -> Path:
    installer = tmp_path / "fake-installer.ps1"
    installer.write_text("Write-Host 'fake installer'\n", encoding="utf-8")
    return installer


def make_agent_installer_artifact(tmp_path: Path) -> Path:
    installer = tmp_path / "fake-agent-installer.ps1"
    installer.write_text("Write-Host 'fake agent installer'\n", encoding="utf-8")
    return installer


def make_python_hello_artifact(tmp_path: Path) -> Path:
    artifact = tmp_path / "hello-python"
    artifact.mkdir()
    (artifact / "hello.py").write_text('print("hello from python")\n', encoding="utf-8")
    (artifact / "run-python-demo.ps1").write_text("param($OutputPath)\n", encoding="utf-8")
    return artifact


def test_run_proxmox_artifact_smoke_uploads_executes_collects_and_cleans_up(
    tmp_path: Path,
    monkeypatch,
) -> None:
    created_clients: list[FakeProxmoxClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> FakeProxmoxClient:
        client = FakeProxmoxClient(config)
        created_clients.append(client)
        return client

    monkeypatch.setattr(proxmox_artifact_smoke, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/supplyscan/supplyscan-gold-lite.yaml"))
    progress_events: list[proxmox_artifact_smoke.ProgressEvent] = []

    result = run_proxmox_artifact_smoke(
        scenario=scenario,
        oslab_config=make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        artifact_path=make_artifact(tmp_path),
        poll_interval_seconds=0,
        progress=progress_events.append,
    )

    client = created_clients[0]
    phases = [event.phase for event in progress_events]
    assert "vm.clone.start" in phases
    assert "vm.boot.done" in phases
    assert "guest.ready.done" in phases
    assert "artifact.upload.start" in phases
    assert "product.command.done" in phases
    assert "output.collect.done" in phases
    assert "assertions.done" in phases
    assert "vm.destroy.done" in phases
    assert result.passed is True
    assert result.vm.vm_id == 9102
    assert result.artifact_destination == "C:\\Oslab\\artifact"
    assert result.command.rendered == '& "C:\\Oslab\\artifact\\SupplyScan.exe" --output "C:\\Oslab\\scan-result.json"'
    assert result.collected_json == OUTPUT_JSON
    assert result.output_adapter == "supplyscan.inventory"
    assert result.normalized_json == OUTPUT_JSON
    assert result.local_normalized_path is not None
    assert json.loads(result.local_normalized_path.read_text(encoding="utf-8")) == OUTPUT_JSON
    assert set(result.local_log_paths) == {"product.stderr", "product.stdout"}
    assert result.local_log_paths["product.stdout"].read_bytes() == b"fake supplyscan executed\r\n"
    assert result.local_log_paths["product.stderr"].read_bytes() == b""
    assert set(result.local_report_paths) == {"html", "inventoryAnalysis", "json", "junit"}
    report_payload = json.loads(result.local_report_paths["json"].read_text(encoding="utf-8"))
    assert report_payload["kind"] == "artifactSmokeReport"
    assert report_payload["status"] == "passed"
    assert report_payload["vm"]["destroyed"] is True
    assert report_payload["artifact"]["uploadedFiles"] == 2
    assert "product.stdout" in report_payload["logs"]
    assert report_payload["assertions"]["total"] == 2
    assert report_payload["analysis"]["recordCount"] == 1
    analysis_payload = json.loads(result.local_report_paths["inventoryAnalysis"].read_text(encoding="utf-8"))
    assert analysis_payload["sourceCounts"] == {"Registry": 1}
    junit_root = ET.parse(result.local_report_paths["junit"]).getroot()
    assert junit_root.tag == "testsuite"
    assert junit_root.attrib["failures"] == "0"
    assert junit_root.attrib["errors"] == "0"
    testcase_names = {testcase.attrib["name"] for testcase in junit_root.findall("testcase")}
    assert "product.command" in testcase_names
    assert "assertion.known-registry-git" in testcase_names
    html_report = result.local_report_paths["html"].read_text(encoding="utf-8")
    assert "supplyscan.gold-lite.windows" in html_report
    assert "PASSED" in html_report
    assert [assertion.id for assertion in result.assertions] == ["known-registry-git", "known-registry-git-evidence"]
    assert all(assertion.passed for assertion in result.assertions)
    assert result.local_output_path is not None
    assert json.loads(result.local_output_path.read_text(encoding="utf-8")) == OUTPUT_JSON
    assert "C:\\Oslab\\artifact\\SupplyScan.exe" in client.files
    assert "C:\\Oslab\\artifact\\data\\config.json" in client.files
    assert client.destroyed_vmids == [9102]


def test_run_artifact_validation_writes_full_run_layout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    created_clients: list[FakeProxmoxClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> FakeProxmoxClient:
        client = FakeProxmoxClient(config)
        created_clients.append(client)
        return client

    monkeypatch.setattr(proxmox_artifact_smoke, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/supplyscan/supplyscan-gold-lite.yaml"))

    result = run_artifact_validation(
        scenario,
        make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        artifact_path=make_artifact(tmp_path),
        run_id="full-run",
        poll_interval_seconds=0,
    )

    run_dir = tmp_path / "runs" / "full-run"
    assert result.status == "passed"
    assert (run_dir / "run.json").exists()
    assert (run_dir / "raw" / "fixture-gold-lite.expected-output.json").exists()
    assert (run_dir / "raw" / "actual-output.json").exists()
    assert (run_dir / "normalized" / "inventory.json").exists()
    assert (run_dir / "logs" / "product.stdout.log").exists()
    assert (run_dir / "logs" / "progress.log").exists()
    assert (run_dir / "logs" / "progress.jsonl").exists()
    assert (run_dir / "reports" / "result.json").exists()
    assert (run_dir / "reports" / "result.junit.xml").exists()
    assert (run_dir / "reports" / "result.html").exists()
    assert (run_dir / "reports" / "inventory.analysis.json").exists()
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["runId"] == "full-run"
    assert run_payload["status"] == "passed"
    assert run_payload["details"]["mode"] == "artifact"
    assert run_payload["details"]["outputs"]["raw"].endswith(r"runs\full-run\raw\actual-output.json")
    assert run_payload["details"]["preflight"]["failed"] == 0
    assert run_payload["details"]["preflight"]["total"] == 6
    assert run_payload["details"]["fixtures"]["failed"] == 0
    assert run_payload["details"]["fixtures"]["total"] == 1
    assert run_payload["details"]["fixtures"]["items"][0]["localOutputPath"].endswith(
        r"runs\full-run\raw\fixture-gold-lite.expected-output.json"
    )
    assert run_payload["details"]["logs"]["progress"].endswith(r"runs\full-run\logs\progress.log")
    assert run_payload["details"]["logs"]["progressJsonl"].endswith(r"runs\full-run\logs\progress.jsonl")
    assert run_payload["details"]["logs"]["product.stdout"].endswith(r"runs\full-run\logs\product.stdout.log")
    assert run_payload["details"]["analysis"]["recordCount"] == 1
    assert "inventoryAnalysis" in run_payload["reports"]
    assert "html" in run_payload["reports"]
    report_payload = json.loads((run_dir / "reports" / "result.json").read_text(encoding="utf-8"))
    assert report_payload["outputs"]["localRawPath"].endswith(r"runs\full-run\raw\actual-output.json")
    assert report_payload["outputs"]["localNormalizedPath"].endswith(r"runs\full-run\normalized\inventory.json")
    assert report_payload["logs"]["progress"].endswith(r"runs\full-run\logs\progress.log")
    assert report_payload["logs"]["progressJsonl"].endswith(r"runs\full-run\logs\progress.jsonl")
    assert report_payload["preflight"]["failed"] == 0
    assert report_payload["fixtures"]["total"] == 1
    assert report_payload["fixtures"]["items"][0]["stdout"] == "fixture manifest written\r\n"
    assert report_payload["fixtures"]["items"][0]["stderr"] == ""
    junit_root = ET.parse(run_dir / "reports" / "result.junit.xml").getroot()
    testcase_names = {testcase.attrib["name"] for testcase in junit_root.findall("testcase")}
    assert "preflight.powershell.version" in testcase_names
    assert "fixture.gold-lite" in testcase_names
    html_report = (run_dir / "reports" / "result.html").read_text(encoding="utf-8")
    assert "Preflight" in html_report
    assert "Fixtures" in html_report
    assert "fixture manifest written" in html_report
    progress_log = (run_dir / "logs" / "progress.log").read_text(encoding="utf-8")
    assert "run.created - Run directory created" in progress_log
    assert "vm.boot.done - VM is running" in progress_log
    assert "run.done - Run completed" in progress_log
    progress_events = [
        json.loads(line)
        for line in (run_dir / "logs" / "progress.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert progress_events[0]["phase"] == "run.created"
    assert progress_events[-1]["phase"] == "run.done"
    assert any(event["phase"] == "artifact.upload.progress" for event in progress_events)
    assert created_clients[0].destroyed_vmids == [9102]


def test_run_artifact_validation_records_scan_step_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    created_clients: list[FakeProxmoxClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> FakeProxmoxClient:
        client = FakeProxmoxClient(config)
        created_clients.append(client)
        return client

    monkeypatch.setenv("OSLAB_FAKE_SUPPLYSCAN_TOKEN", "secret-agent-token")
    monkeypatch.setattr(proxmox_artifact_smoke, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/fake-agent-cli-smoke.example.yaml"))

    result = run_artifact_validation(
        scenario,
        make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        artifact_path=make_agent_installer_artifact(tmp_path),
        run_id="agent-full-run",
        poll_interval_seconds=0,
    )

    run_dir = tmp_path / "runs" / "agent-full-run"
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert result.status == "passed"
    assert run_payload["details"]["preflight"]["failed"] == 0
    assert run_payload["details"]["productSteps"][-1]["id"] == "scan"
    assert run_payload["details"]["productSteps"][-1]["stdoutJson"]["ok"] is True
    assert run_payload["details"]["scan"]["ok"] is True
    assert run_payload["details"]["scan"]["outputWritten"] is None
    assert run_payload["details"]["scan"]["bytesWritten"] is None
    assert run_payload["details"]["outputs"]["productSteps"].endswith(r"runs\agent-full-run\raw\product-steps.json")
    assert json.loads((run_dir / "raw" / "product-steps.json").read_text(encoding="utf-8"))[-1]["stdoutJson"]["ok"] is True
    assert created_clients[0].destroyed_vmids == [9102]


def test_run_artifact_validation_supports_generic_command_result_demo(
    tmp_path: Path,
    monkeypatch,
) -> None:
    created_clients: list[FakeProxmoxClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> FakeProxmoxClient:
        client = FakeProxmoxClient(config)
        created_clients.append(client)
        return client

    monkeypatch.setattr(proxmox_artifact_smoke, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/demo-python-hello.example.yaml"))

    result = run_artifact_validation(
        scenario,
        make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        artifact_path=make_python_hello_artifact(tmp_path),
        run_id="python-demo-run",
        poll_interval_seconds=0,
    )

    run_dir = tmp_path / "runs" / "python-demo-run"
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    normalized = json.loads((run_dir / "normalized" / "command-result.json").read_text(encoding="utf-8"))
    report_payload = json.loads((run_dir / "reports" / "result.json").read_text(encoding="utf-8"))

    assert result.status == "passed"
    assert normalized["kind"] == "commandResult"
    assert normalized["stdout"] == "hello from python\n"
    assert run_payload["details"]["outputs"]["normalized"].endswith(r"runs\python-demo-run\normalized\command-result.json")
    assert run_payload["details"]["fixtures"]["total"] == 1
    assert run_payload["details"]["fixtures"]["items"][0]["id"] == "demo-python-runtime"
    assert (run_dir / "raw" / "fixture-demo-python-runtime.expected-output.json").exists()
    assert "analysis" not in run_payload["details"]
    assert "inventoryAnalysis" not in run_payload["reports"]
    assert report_payload["outputs"]["records"] is None
    assert report_payload["analysis"] is None
    assert report_payload["fixtures"]["items"][0]["stdout"] == "Python runtime ready: C:\\Python\\python.exe\r\n"
    assert [assertion["id"] for assertion in report_payload["assertions"]["results"]] == [
        "python-exit-zero",
        "python-stdout-hello",
    ]
    assert created_clients[0].destroyed_vmids == [9102]


def test_run_proxmox_artifact_smoke_respects_folder_artifact_excludes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    created_clients: list[FakeProxmoxClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> FakeProxmoxClient:
        client = FakeProxmoxClient(config)
        created_clients.append(client)
        return client

    artifact = make_artifact(tmp_path)
    logs = artifact / "logs"
    logs.mkdir()
    (logs / "events.jsonl").write_text("huge log\n", encoding="utf-8")
    (artifact / "SupplyScanAgent.pdb").write_bytes(b"debug symbols")

    monkeypatch.setattr(proxmox_artifact_smoke, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/supplyscan/supplyscan-gold-lite.yaml"))
    scenario.raw["artifact"]["exclude"] = ["logs/**", "*.pdb"]

    result = run_proxmox_artifact_smoke(
        scenario=scenario,
        oslab_config=make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        artifact_path=artifact,
        poll_interval_seconds=0,
    )

    client = created_clients[0]
    assert result.passed is True
    assert "C:\\Oslab\\artifact\\SupplyScan.exe" in client.files
    assert "C:\\Oslab\\artifact\\logs\\events.jsonl" not in client.files
    assert "C:\\Oslab\\artifact\\SupplyScanAgent.pdb" not in client.files


def test_run_proxmox_artifact_smoke_can_upload_folder_as_archive(
    tmp_path: Path,
    monkeypatch,
) -> None:
    created_clients: list[FakeProxmoxClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> FakeProxmoxClient:
        client = FakeProxmoxClient(config)
        created_clients.append(client)
        return client

    artifact = make_artifact(tmp_path)
    (artifact / "debug.pdb").write_bytes(b"debug")

    monkeypatch.setattr(proxmox_artifact_smoke, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/supplyscan/supplyscan-gold-lite.yaml"))
    scenario.raw["artifact"]["transfer"] = "archive"
    scenario.raw["artifact"]["exclude"] = ["*.pdb"]

    result = run_proxmox_artifact_smoke(
        scenario=scenario,
        oslab_config=make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        artifact_path=artifact,
        poll_interval_seconds=0,
    )

    client = created_clients[0]
    assert result.passed is True
    assert result.uploaded_files[0].guest_path == "C:\\Oslab\\artifact.zip"
    with zipfile.ZipFile(io.BytesIO(client.files["C:\\Oslab\\artifact.zip"])) as archive:
        assert sorted(archive.namelist()) == ["SupplyScan.exe", "data/config.json"]
    assert any("Expand-Archive" in " ".join(command) for command in client.commands)


def test_run_proxmox_artifact_smoke_uploads_installs_executes_and_cleans_up(
    tmp_path: Path,
    monkeypatch,
) -> None:
    created_clients: list[FakeProxmoxClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> FakeProxmoxClient:
        client = FakeProxmoxClient(config)
        created_clients.append(client)
        return client

    monkeypatch.setattr(proxmox_artifact_smoke, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/fake-installer-smoke.example.yaml"))

    result = run_proxmox_artifact_smoke(
        scenario=scenario,
        oslab_config=make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        artifact_path=make_installer_artifact(tmp_path),
        poll_interval_seconds=0,
    )

    client = created_clients[0]
    assert result.passed is True
    assert result.artifact_destination == "C:\\Oslab\\installer\\fake-installer.ps1"
    assert result.uploaded_files[0].guest_path == "C:\\Oslab\\installer\\fake-installer.ps1"
    assert result.install_command is not None
    assert result.install_command.rendered == '& "C:\\Oslab\\installer\\fake-installer.ps1" -InstallDir "C:\\Oslab\\installed"'
    assert result.install_exit_code == 0
    assert result.command.rendered == '& "C:\\Oslab\\installed\\fake-scanner.ps1" -OutputPath "C:\\Oslab\\scan-result.json"'
    assert result.normalized_json == OUTPUT_JSON
    assert [assertion.id for assertion in result.assertions] == ["fake-installed-git"]
    assert "C:\\Oslab\\installer\\fake-installer.ps1" in client.files
    assert client.destroyed_vmids == [9102]


def test_run_proxmox_artifact_smoke_runs_product_steps_with_redacted_secret(
    tmp_path: Path,
    monkeypatch,
) -> None:
    created_clients: list[FakeProxmoxClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> FakeProxmoxClient:
        client = FakeProxmoxClient(config)
        created_clients.append(client)
        return client

    monkeypatch.setenv("OSLAB_FAKE_SUPPLYSCAN_TOKEN", "secret-agent-token")
    monkeypatch.setattr(proxmox_artifact_smoke, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/fake-agent-cli-smoke.example.yaml"))

    result = run_proxmox_artifact_smoke(
        scenario=scenario,
        oslab_config=make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        artifact_path=make_agent_installer_artifact(tmp_path),
        poll_interval_seconds=0,
    )

    client = created_clients[0]
    assert result.passed is True
    assert [step.id for step in result.product_steps] == ["register", "status", "scan"]
    assert all(step.passed for step in result.product_steps)
    assert result.product_steps[0].command.rendered.endswith('--access-token "secret-agent-token" --json')
    assert result.product_steps[0].command.safe_rendered.endswith('--access-token "<redacted>" --json')
    assert result.command == result.product_steps[-1].command
    assert result.local_product_steps_path is not None
    assert "productStep.register.stdout" in result.local_log_paths
    assert "productStep.status.stdout" in result.local_log_paths
    assert "productStep.scan.stdout" in result.local_log_paths
    assert "secret-agent-token" not in result.local_log_paths["productStep.register.stdout"].read_text(encoding="utf-8")
    assert "secret-agent-token" not in result.local_log_paths["productStep.status.stdout"].read_text(encoding="utf-8")
    product_steps_payload = result.local_product_steps_path.read_text(encoding="utf-8")
    assert "secret-agent-token" not in product_steps_payload
    assert '"stdoutJson"' in product_steps_payload
    assert result.normalized_json == OUTPUT_JSON
    assert [assertion.id for assertion in result.assertions] == ["fake-agent-git"]
    command_texts = [" ".join(command) for command in client.commands]
    assert any(" register " in command for command in command_texts)
    assert any(" status " in command for command in command_texts)
    assert any(" scan " in command for command in command_texts)
    assert client.destroyed_vmids == [9102]


def test_run_proxmox_artifact_smoke_requires_product_step_secret_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    created_clients: list[FakeProxmoxClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> FakeProxmoxClient:
        client = FakeProxmoxClient(config)
        created_clients.append(client)
        return client

    monkeypatch.delenv("OSLAB_FAKE_SUPPLYSCAN_TOKEN", raising=False)
    monkeypatch.setattr(proxmox_artifact_smoke, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/fake-agent-cli-smoke.example.yaml"))

    with pytest.raises(ConfigError, match="Required product step secret env var is not set"):
        run_proxmox_artifact_smoke(
            scenario=scenario,
            oslab_config=make_config(tmp_path),
            proxmox_config=make_proxmox_config(),
            artifact_path=make_agent_installer_artifact(tmp_path),
            poll_interval_seconds=0,
        )

    assert created_clients == []


def test_run_proxmox_artifact_smoke_treats_product_step_ok_false_as_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class JsonFailureClient(FakeProxmoxClient):
        def guest_exec(self, vmid: int, command: list[str]):
            result = super().guest_exec(vmid, command)
            command_text = " ".join(command)
            if "fake-agent.ps1" in command_text and " register " in command_text:
                self.status_by_pid[result["pid"]] = {
                    "exited": 1,
                    "exitcode": 0,
                    "out-data": json.dumps(
                        {"ok": False, "command": "register", "errorCode": "access_token_missing"}
                    )
                    + "\n",
                    "err-data": "",
                }
            return result

    created_clients: list[JsonFailureClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> JsonFailureClient:
        client = JsonFailureClient(config)
        created_clients.append(client)
        return client

    monkeypatch.setenv("OSLAB_FAKE_SUPPLYSCAN_TOKEN", "secret-agent-token")
    monkeypatch.setattr(proxmox_artifact_smoke, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/fake-agent-cli-smoke.example.yaml"))

    result = run_proxmox_artifact_smoke(
        scenario=scenario,
        oslab_config=make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        artifact_path=make_agent_installer_artifact(tmp_path),
        poll_interval_seconds=0,
    )

    assert result.passed is False
    assert result.message == "Product step failed: register"
    assert [step.id for step in result.product_steps] == ["register"]
    assert result.product_steps[0].exit_code == 0
    assert result.product_steps[0].passed is False
    assert result.product_steps[0].message == "Product step stdout reported failure"
    assert result.product_steps[0].stdout_json["ok"] is False


def test_run_proxmox_artifact_smoke_fails_product_step_stdout_json_expectation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    created_clients: list[FakeProxmoxClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> FakeProxmoxClient:
        client = FakeProxmoxClient(config)
        created_clients.append(client)
        return client

    monkeypatch.setenv("OSLAB_FAKE_SUPPLYSCAN_TOKEN", "secret-agent-token")
    monkeypatch.setattr(proxmox_artifact_smoke, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/fake-agent-cli-smoke.example.yaml"))
    scenario.raw["product"]["steps"][1]["expectStdoutJson"]["registered"] = False

    result = run_proxmox_artifact_smoke(
        scenario=scenario,
        oslab_config=make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        artifact_path=make_agent_installer_artifact(tmp_path),
        poll_interval_seconds=0,
    )

    assert result.passed is False
    assert result.message == "Product step failed: status"
    assert [step.id for step in result.product_steps] == ["register", "status"]
    failed_step = result.product_steps[-1]
    assert failed_step.passed is False
    assert failed_step.message == "Product step stdout JSON expectation failed"
    mismatch = failed_step.details["stdoutJsonExpectation"]["mismatches"][0]
    assert mismatch == {"path": "registered", "reason": "value_mismatch", "expected": False, "actual": True}
    assert result.collected_json is None
    assert created_clients[0].destroyed_vmids == [9102]


def test_run_proxmox_artifact_smoke_reports_command_failure_and_cleans_up(
    tmp_path: Path,
    monkeypatch,
) -> None:
    created_clients: list[FakeProxmoxClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> FakeProxmoxClient:
        client = FakeProxmoxClient(config, artifact_exit_code=9)
        created_clients.append(client)
        return client

    monkeypatch.setattr(proxmox_artifact_smoke, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/supplyscan/supplyscan-gold-lite.yaml"))

    result = run_proxmox_artifact_smoke(
        scenario=scenario,
        oslab_config=make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        artifact_path=make_artifact(tmp_path),
        poll_interval_seconds=0,
    )

    assert result.passed is False
    assert result.exit_code == 9
    assert result.message == "Artifact command failed"
    assert result.assertions == []
    assert result.normalized_json is None
    assert created_clients[0].destroyed_vmids == [9102]
