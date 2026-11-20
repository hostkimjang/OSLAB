from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import tarfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from oslab.config import OslabConfig
from oslab.errors import OslabError, ProviderError, ScenarioValidationError
from oslab.guests.qemu_agent import MAX_CHUNK_RAW_BYTES, LinuxQemuAgentChannel, _ASSEMBLE_LINUX_UPLOAD
from oslab.models.scenario import load_scenario, validate_scenario_mapping
from oslab.providers.base import TemplateRef, VmRef, VmSpec
from oslab.providers.proxmox import ProxmoxConfig, ProxmoxProvider
from oslab.runners import proxmox_artifact_smoke
from oslab.runners.proxmox_artifact_smoke import run_proxmox_artifact_smoke
from oslab.runners.proxmox_linux_artifact import CONSOLE_COMMAND_SCRIPT, CONSOLE_SETUP_SCRIPT, _render_linux_command, linux_shell_argv
from oslab.runners.scenario_runner import run_artifact_validation
from oslab.commands import CommandSpec

Program = Callable[["FakeGuestClient"], tuple[int, str]]


class FakeGuestClient:
    """Proxmox client double that keeps guest files in memory and runs known guest commands."""

    def __init__(self, config: ProxmoxConfig, programs: dict[str, Program] | None = None) -> None:
        self.config = config
        self.programs = programs or {}
        self.files: dict[str, bytes] = {}
        self.modes: dict[str, int] = {}
        self.commands: list[list[str]] = []
        self.vm_config = {"net0": "virtio=BC:24:11:00:00:01,bridge=vmbr0", "vga": "serial0"}
        self.vm_names: dict[int, str] = {}
        self.config_updates: list[dict[str, str]] = []
        self.running: set[int] = set()
        self.destroyed_vmids: list[int] = []
        self.statuses: dict[int, dict[str, Any]] = {}

    def list_nodes(self):
        return [{"node": "pve01"}]

    def list_vm_resources(self):
        return [{"vmid": 9000, "name": "ubuntu-template", "node": "pve01", "status": "stopped", "template": 1}]

    def get_vm_config(self, vmid: int, *, node: str | None = None):
        return {**self.vm_config, "name": self.vm_names.get(vmid)}

    def update_vm_config(self, vmid: int, settings: dict[str, str]) -> None:
        self.config_updates.append(dict(settings))

    def clone_vm(self, *, template_vmid: int, new_vmid: int, name: str, full_clone: bool):
        self.vm_names[new_vmid] = name
        return "UPID:pve01:clone"

    def start_vm(self, vmid: int):
        self.running.add(vmid)
        return "UPID:pve01:start"

    def stop_vm(self, vmid: int):
        self.running.discard(vmid)
        return "UPID:pve01:stop"

    def destroy_vm(self, vmid: int, *, purge: bool = True):
        self.destroyed_vmids.append(vmid)
        self.vm_names.pop(vmid, None)
        return "UPID:pve01:destroy"

    def wait_for_task(self, task_id: str, **kwargs):
        return {"status": "stopped", "exitstatus": "OK"}

    def get_vm_status(self, vmid: int):
        return {"status": "running" if vmid in self.running else "stopped"}

    def get_guest_network_interfaces(self, vmid: int):
        return {"result": []}

    def guest_exec(self, vmid: int, command: list[str]):
        self.commands.append(list(command))
        exit_code, stdout = self._run(list(command))
        pid = len(self.commands)
        self.statuses[pid] = {"exited": 1, "exitcode": exit_code, "out-data": stdout, "err-data": ""}
        return {"pid": pid}

    def get_guest_exec_status(self, vmid: int, pid: int):
        return self.statuses[pid]

    def guest_file_write(self, vmid: int, guest_path: str, content: str, *, encode: bool = True) -> None:
        self.files[guest_path] = content.encode("utf-8") if encode else base64.b64decode(content)

    def guest_file_read(self, vmid: int, guest_path: str):
        if guest_path not in self.files:
            raise ProviderError("guest-file-open failed", details={"path": guest_path})
        return {"content": self.files[guest_path].decode("utf-8"), "truncated": 0}

    def _run(self, argv: list[str]) -> tuple[int, str]:
        if argv[:3] == ["sh", "-c", CONSOLE_COMMAND_SCRIPT]:
            argv = [argv[4], "-c", argv[5], "oslab", *argv[8:]]
        if argv[0] == "mkdir":
            return 0, ""
        if argv[0] == "rm":
            for target in argv[2:]:
                if target != "--":
                    for path in list(self.files):
                        if path == target or path.startswith(f"{target}/"):
                            del self.files[path]
            return 0, ""
        if argv[0] == "chmod":
            self.modes.update({path: 0o755 for path in argv[2:]})
            return 0, ""
        if argv[0] == "base64":
            return 0, base64.encodebytes(self.files[argv[1]]).decode("ascii")
        script = argv[2]
        if script == CONSOLE_SETUP_SCRIPT:
            return 0, ""
        if script == "uname -s":
            return 0, "Linux\n"
        if script == 'mkdir -p "$1" && test -w "$1"':
            return 0, ""
        if script == 'test ! -e "$1" && test ! -L "$1"':
            return int(argv[4] in self.files), ""
        if script == 'test -f "$1" && test ! -L "$1"':
            return int(argv[4] not in self.files), ""
        if "tar -xzf" in script:
            self._extract(destination=argv[6], archive=argv[5])
            return 0, ""
        if script == _ASSEMBLE_LINUX_UPLOAD:
            return self._assemble_chunks(parts_dir=argv[4], target=argv[5], count=int(argv[6]), digest=argv[7])
        script = re.sub(r"\$\{(\d+)\}", lambda match: argv[3 + int(match[1])], script)
        return self.programs[script](self)

    def _extract(self, *, destination: str, archive: str) -> None:
        with tarfile.open(fileobj=io.BytesIO(self.files.pop(archive)), mode="r:gz") as tar:
            for member in tar.getmembers():
                stream = tar.extractfile(member)
                assert stream is not None
                self.files[f"{destination}/{member.name}"] = stream.read()
                self.modes[f"{destination}/{member.name}"] = member.mode

    def _assemble_chunks(self, *, parts_dir: str, target: str, count: int, digest: str) -> tuple[int, str]:
        part_paths = [f"{parts_dir}/part-{index:06d}" for index in range(count)]
        if any(path not in self.files for path in part_paths):
            return 1, ""
        assembled = b"".join(self.files[path] for path in part_paths)
        if hashlib.sha256(assembled).hexdigest() != digest:
            return 1, ""
        self.files[target] = assembled
        return 0, ""


def write_command_result(path: str, *, stdout: str, files: list[dict[str, Any]] | None = None) -> Program:
    def program(client: FakeGuestClient) -> tuple[int, str]:
        payload = {
            "schemaVersion": 1,
            "kind": "commandResult",
            "command": "linux demo",
            "exitCode": 0,
            "stdout": stdout,
            "stderr": "",
            "metadata": {"files": files or []},
        }
        client.files[path] = json.dumps(payload).encode("utf-8")
        return 0, stdout

    return program


def make_proxmox_config() -> ProxmoxConfig:
    return ProxmoxConfig(api_url="https://pve.example.local:8006", node="pve01", token_id="root@pam!oslab", token_secret="secret")


def make_config(tmp_path: Path) -> OslabConfig:
    return OslabConfig(path=None, raw={"runDefaults": {"outputRoot": str(tmp_path / "runs")}})


def write_scenario(tmp_path: Path, **overrides: Any) -> Path:
    raw: dict[str, Any] = {
        "schemaVersion": 1,
        "id": "test.linux.smoke",
        "os": {"family": "linux"},
        "provider": {
            "type": "proxmox",
            "templateVmId": 9000,
            "vmIdRange": {"start": 9185, "end": 9189},
            "clone": {"display": "std", "network": "disconnected"},
        },
        "guest": {"mode": "qemuAgent"},
        "artifact": {
            "type": "folder",
            "pathParam": "artifactPath",
            "destination": "/opt/oslab/artifact",
            "transfer": "archive",
            "command": {"shell": "sh", "template": '"{ArtifactDir}/run.sh" "{OutputPath}"'},
        },
        "outputs": {"actual": {"path": "/opt/oslab/command-result.json", "adapter": "canonical.command"}},
        "assertions": [{"type": "command.exitCode", "id": "exit-zero", "exitCode": 0}],
        "reports": {"formats": ["junit", "json", "html"]},
    }
    raw.update(overrides)
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


def make_artifact(tmp_path: Path) -> Path:
    artifact = tmp_path / "artifact"
    (artifact / "data").mkdir(parents=True)
    (artifact / "run.sh").write_bytes(b"#!/bin/sh\necho linux demo\n")
    (artifact / "data" / "input.txt").write_bytes(b"input\n")
    return artifact


def install_fake_client(monkeypatch, programs: dict[str, Program]) -> list[FakeGuestClient]:
    clients: list[FakeGuestClient] = []

    def factory(config: ProxmoxConfig) -> FakeGuestClient:
        clients.append(FakeGuestClient(config, programs))
        return clients[-1]

    monkeypatch.setattr(proxmox_artifact_smoke, "ProxmoxClient", factory)
    return clients


def test_linux_run_applies_clone_settings_fixture_archive_and_assertions(tmp_path: Path, monkeypatch) -> None:
    fixture = tmp_path / "prepare.sh"
    fixture.write_bytes(b"#!/bin/sh\necho ready\n")
    scenario_path = write_scenario(
        tmp_path,
        fixtures=[{"id": "prepare", "type": "shell", "source": str(fixture), "expectedOutput": "/opt/oslab/state.json"}],
        assertions=[
            {"type": "command.exitCode", "id": "exit-zero", "exitCode": 0},
            {"type": "file.exists", "id": "fixture-state", "path": "/opt/oslab/state.json"},
        ],
    )

    def prepare(client: FakeGuestClient) -> tuple[int, str]:
        client.files["/opt/oslab/state.json"] = b'{"ready": true}'
        client.files["/opt/oslab/artifact/preserved-state.ini"] = b"version=2.3.1\n"
        return 0, "fixture ready\n"

    clients = install_fake_client(
        monkeypatch,
        {
            "/opt/oslab/fixtures/prepare.sh": prepare,
            '"/opt/oslab/artifact/run.sh" "/opt/oslab/command-result.json"': write_command_result(
                "/opt/oslab/command-result.json",
                stdout="linux demo\n",
                files=[{"path": "/opt/oslab/state.json", "exists": True}],
            ),
        },
    )

    result = run_artifact_validation(
        load_scenario(scenario_path),
        make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        artifact_path=make_artifact(tmp_path),
        run_id="linux-run",
        poll_interval_seconds=0,
    )

    client = clients[0]
    assert result.status == "passed"
    assert client.config_updates == [{"vga": "std", "net0": "virtio=BC:24:11:00:00:01,bridge=vmbr0,link_down=1"}]
    assert [check["id"] for check in result.details["preflight"]["checks"]] == [
        "linux.shell",
        "oslab.directory",
        "oslab.file_roundtrip",
        "oslab.cleanup_test_file",
    ]
    assert result.details["fixtures"]["items"][0]["passed"] is True
    assert ["chmod", "+x", "/opt/oslab/fixtures/prepare.sh"] in client.commands
    assert client.modes["/opt/oslab/artifact/run.sh"] == 0o755
    assert client.modes["/opt/oslab/artifact/data/input.txt"] == 0o644
    assert client.files["/opt/oslab/artifact/data/input.txt"] == b"input\n"
    assert client.files["/opt/oslab/artifact/preserved-state.ini"] == b"version=2.3.1\n"
    assert all(".oslab-archive-" not in file for file in client.files)
    assert ["sh", "-c", '"${1}/run.sh" "${2}"', "oslab", "/opt/oslab/artifact", "/opt/oslab/command-result.json"] in client.commands
    assert client.destroyed_vmids == [9185]
    report = json.loads((tmp_path / "runs" / "linux-run" / "reports" / "result.json").read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["assertions"]["total"] == 2


def test_linux_files_transfer_creates_directories_and_marks_scripts_executable(tmp_path: Path, monkeypatch) -> None:
    scenario_path = write_scenario(
        tmp_path,
        artifact={
            "type": "folder",
            "pathParam": "artifactPath",
            "destination": "/opt/oslab/artifact",
            "transfer": "files",
            "command": {"shell": "bash", "template": '"{ArtifactDir}/run.sh" "{OutputPath}"'},
        },
    )
    clients = install_fake_client(
        monkeypatch,
        {
            '"/opt/oslab/artifact/run.sh" "/opt/oslab/command-result.json"': write_command_result(
                "/opt/oslab/command-result.json", stdout="linux demo\n"
            )
        },
    )

    result = run_proxmox_artifact_smoke(
        scenario=load_scenario(scenario_path),
        oslab_config=make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        artifact_path=make_artifact(tmp_path),
        poll_interval_seconds=0,
    )

    client = clients[0]
    assert result.passed is True
    assert [file.guest_path for file in result.uploaded_files] == [
        "/opt/oslab/artifact/data/input.txt",
        "/opt/oslab/artifact/run.sh",
    ]
    assert ["mkdir", "-p", "/opt/oslab/artifact", "/opt/oslab/artifact/data"] in client.commands
    assert ["chmod", "+x", "/opt/oslab/artifact/run.sh"] in client.commands
    assert ["bash", "-c", '"${1}/run.sh" "${2}"', "oslab", "/opt/oslab/artifact", "/opt/oslab/command-result.json"] in client.commands
    assert result.destroyed is True


def test_linux_product_steps_show_commands_on_console_without_secret_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OSLAB_TEST_AGENT_TOKEN", "secret-agent-token")
    scenario_path = write_scenario(
        tmp_path,
        guest={"mode": "qemuAgent", "screen": {"showCommands": True}},
        artifact={"type": "folder", "pathParam": "artifactPath", "destination": "/opt/oslab/artifact"},
        product={
            "steps": [
                {
                    "id": "register",
                    "command": {"shell": "sh", "template": '"{ArtifactDir}/run.sh" register --token "{Token}"'},
                    "secretTokens": {"Token": {"env": "OSLAB_TEST_AGENT_TOKEN"}},
                    "captureStdoutJson": True,
                    "expectStdoutJson": {"ok": True},
                },
                {"id": "scan", "command": {"shell": "sh", "template": '"{ArtifactDir}/run.sh" scan "{OutputPath}"'}},
            ]
        },
    )
    clients = install_fake_client(
        monkeypatch,
        {
            '"/opt/oslab/artifact/run.sh" register --token "secret-agent-token"': lambda client: (0, '{"ok": true}\n'),
            '"/opt/oslab/artifact/run.sh" scan "/opt/oslab/command-result.json"': write_command_result(
                "/opt/oslab/command-result.json", stdout="scanned secret-agent-token\n"
            ),
        },
    )

    result = run_proxmox_artifact_smoke(
        scenario=load_scenario(scenario_path),
        oslab_config=make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        artifact_path=make_artifact(tmp_path),
        poll_interval_seconds=0,
    )

    console_commands = [command for command in clients[0].commands if command[:3] == ["sh", "-c", CONSOLE_COMMAND_SCRIPT]]
    assert result.passed is True
    assert clients[0].commands[0] == ["sh", "-c", CONSOLE_SETUP_SCRIPT]
    assert clients[0].commands.count(["sh", "-c", CONSOLE_SETUP_SCRIPT]) == 1
    assert [step.id for step in result.product_steps] == ["register", "scan"]
    assert result.product_steps[0].stdout_json == {"ok": True}
    assert [command[6:8] for command in console_commands] == [
        ['"/opt/oslab/artifact/run.sh" register --token "<redacted>"', "0"],
        ['"/opt/oslab/artifact/run.sh" scan "/opt/oslab/command-result.json"', "0"],
    ]
    assert "secret-agent-token" not in console_commands[0][5]
    assert console_commands[0][-1] == "secret-agent-token"
    assert result.product_steps[1].stdout == "scanned <redacted>\n"
    assert result.collected_json["stdout"] == "scanned <redacted>\n"
    assert "secret-agent-token" not in result.local_output_path.read_text(encoding="utf-8")
    assert "secret-agent-token" not in result.local_normalized_path.read_text(encoding="utf-8")


def test_linux_shell_separates_token_arguments_from_shell_script() -> None:
    secret = "example token with 'quotes', \"spaces\", $ and a\nnewline"
    path = '/opt/demo "build"'
    command = _render_linux_command(
        {"shell": "sh", "template": '''tool "{Path}/run" '{Secret}' {Secret}'''},
        {"Path": path},
        secret_tokens={"Secret": secret},
    )

    argv = linux_shell_argv(command, show_on_console=True, secrets=(secret,))

    assert argv[5] == '''tool "${1}/run" ''"${2}"'' "${2}"'''
    assert argv[6] == f'''tool "{path}/run" '<redacted>' <redacted>'''
    assert argv[7:] == ["0", path, secret]
    assert secret not in repr(command)


def test_linux_qga_timeout_keeps_sensitive_argv_out_of_diagnostics() -> None:
    client = FakeGuestClient(make_proxmox_config(), {"test-program": lambda client: (0, "")})
    ticks = iter((0, 120))
    channel = LinuxQemuAgentChannel(client, monotonic=lambda: next(ticks))
    vm = VmRef(vm_id=9185)
    secret = "example token"

    with pytest.raises(ProviderError, match="Timed out") as failure:
        channel.execute_with_diagnostics(
            vm,
            ["sh", "-c", "test-program", "oslab", secret],
            diagnostic_command=("sh", "-c", "test-program <redacted>"),
            timeout_seconds=60,
        )

    assert client.commands[0][-1] == secret
    assert failure.value.details == {
        "vmId": 9185,
        "failureClass": "guest_execution_timeout",
        "command": ["sh", "-c", "test-program <redacted>"],
    }


def test_linux_shell_argv_rejects_windows_shells() -> None:
    with pytest.raises(Exception, match="Unsupported Linux command shell: powershell"):
        linux_shell_argv(CommandSpec(shell="powershell", template="Get-Date", rendered="Get-Date"))


def test_linux_channel_uploads_large_files_in_base64_chunks_and_reads_back_with_fallback() -> None:
    client = FakeGuestClient(make_proxmox_config())
    channel = LinuxQemuAgentChannel(client, sleep=lambda _: None)
    vm = VmRef(vm_id=9185)
    content = bytes(range(256)) * 400

    write = channel.upload_bytes(vm, "/opt/oslab/artifact/tool.bin", content)
    client.files["/opt/oslab/report.txt"] = "linux 결과\n".encode("utf-8")

    def file_read_disabled(vmid: int, guest_path: str):
        raise ProviderError("file-read disabled")

    client.guest_file_read = file_read_disabled
    download = channel.download_text(vm, "/opt/oslab/report.txt")

    assert write.bytes_written == len(content)
    assert client.files["/opt/oslab/artifact/tool.bin"] == content
    staging = client.commands[0][-1]
    assert staging.startswith("/opt/oslab/artifact/.oslab-chunks-")
    assert client.commands[0] == ["mkdir", "-m", "700", "--", staging]
    assert client.commands[1][4:] == [staging, "/opt/oslab/artifact/tool.bin", "3", hashlib.sha256(content).hexdigest()]
    assert client.commands[2] == ["rm", "-rf", "--", staging]
    assert all(not path.startswith(staging) for path in client.files)
    assert len(base64.b64encode(content)) > MAX_CHUNK_RAW_BYTES
    assert download.content == "linux 결과\n"
    assert download.raw["fallback"] == "base64"


@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_linux_chunk_upload_refuses_to_replace_target_when_a_part_is_invalid(fault: str) -> None:
    client = FakeGuestClient(make_proxmox_config())
    channel = LinuxQemuAgentChannel(client)
    target = "/opt/oslab/artifact/tool.bin"
    client.files[target] = b"existing"
    original_write = client.guest_file_write

    def write(vmid: int, guest_path: str, content: str, *, encode: bool = True) -> None:
        if not guest_path.endswith("/part-000001"):
            original_write(vmid, guest_path, content, encode=encode)
        elif fault == "corrupt":
            client.files[guest_path] = b"x" * MAX_CHUNK_RAW_BYTES

    client.guest_file_write = write

    with pytest.raises(ProviderError, match="Failed to assemble or verify"):
        channel.upload_bytes(VmRef(vm_id=9185), target, b"0" * (MAX_CHUNK_RAW_BYTES * 2))

    assert client.files == {target: b"existing"}


def test_linux_rejects_preexisting_output_from_template_or_fixture(tmp_path: Path, monkeypatch) -> None:
    fixture = tmp_path / "prepare.sh"
    fixture.write_bytes(b"#!/bin/sh\n")
    scenario_path = write_scenario(tmp_path, fixtures=[{"id": "prepare", "type": "shell", "source": str(fixture)}])
    output_path = "/opt/oslab/command-result.json"
    original_output = b'{"schemaVersion": 1, "kind": "commandResult", "exitCode": 0}'

    def prepare(client: FakeGuestClient) -> tuple[int, str]:
        client.files[output_path] = original_output
        return 0, ""

    clients = install_fake_client(monkeypatch, {"/opt/oslab/fixtures/prepare.sh": prepare})

    with pytest.raises(OslabError, match="Product output path already exists"):
        run_proxmox_artifact_smoke(
            scenario=load_scenario(scenario_path),
            oslab_config=make_config(tmp_path),
            proxmox_config=make_proxmox_config(),
            artifact_path=make_artifact(tmp_path),
            run_dir=tmp_path / "runs" / "linux-run",
            poll_interval_seconds=0,
        )

    assert clients[0].files[output_path] == original_output
    assert clients[0].destroyed_vmids == [9185]


def test_create_clone_applies_display_and_disconnects_every_network_link() -> None:
    client = FakeGuestClient(make_proxmox_config())
    client.vm_config = {
        "net0": "virtio=BC:24:11:00:00:01,bridge=vmbr0,link_down=0",
        "net1": "e1000=BC:24:11:00:00:02,bridge=vmbr1",
        "vga": "serial0",
        "netboot": "keep",
    }
    provider = ProxmoxProvider(client)

    provider.create_clone(TemplateRef(vm_id=9000), VmSpec(vm_id=9185, name="clone", display="std", network="disconnected"))
    provider.create_clone(TemplateRef(vm_id=9000), VmSpec(vm_id=9186, name="plain"))

    assert client.config_updates == [
        {
            "vga": "std",
            "net0": "virtio=BC:24:11:00:00:01,bridge=vmbr0,link_down=1",
            "net1": "e1000=BC:24:11:00:00:02,bridge=vmbr1,link_down=1",
        }
    ]


@pytest.mark.parametrize(
    ("section", "value", "message"),
    [
        ("provider", {"clone": {"display": "qxl"}}, "Unsupported provider.clone.display"),
        ("provider", {"clone": {"netwrok": "disconnected"}}, "Unsupported provider.clone field"),
        ("guest", {"screen": {"signIn": True}}, "supported only for Windows"),
        ("guest", {"screen": {"showCommands": "yes"}}, "must be a boolean"),
    ],
)
def test_linux_scenario_rejects_invalid_clone_and_screen_settings(section: str, value: dict, message: str) -> None:
    raw = {
        "schemaVersion": 1,
        "id": "test.linux.invalid",
        "os": {"family": "linux"},
        "provider": {"type": "proxmox", "templateVmId": 9000},
        "guest": {"mode": "qemuAgent"},
        "assertions": [{"type": "command.exitCode", "id": "exit-zero", "exitCode": 0}],
    }
    raw[section] = {**raw[section], **value}

    with pytest.raises(ScenarioValidationError, match=message):
        validate_scenario_mapping(raw)


class FakeWindowsGuestClient(FakeGuestClient):
    """Answers every PowerShell command with success and writes the command result for run.ps1."""

    def _run(self, argv: list[str]) -> tuple[int, str]:
        if "run.ps1" in argv[-1]:
            return write_command_result("C:\\Oslab\\command-result.json", stdout="windows demo\n")(self)
        return 0, ""


def test_windows_scenarios_still_run_through_powershell(tmp_path: Path, monkeypatch) -> None:
    scenario_path = write_scenario(
        tmp_path,
        os={"family": "windows"},
        provider={"type": "proxmox", "templateVmId": 9000, "vmIdRange": {"start": 9185, "end": 9189}},
        artifact={
            "type": "folder",
            "pathParam": "artifactPath",
            "destination": "C:\\Oslab\\artifact",
            "command": {"shell": "powershell", "template": '& "{ArtifactDir}\\run.ps1" -OutputPath "{OutputPath}"'},
        },
        outputs={"actual": {"path": "C:\\Oslab\\command-result.json", "adapter": "canonical.command"}},
    )
    clients: list[FakeWindowsGuestClient] = []

    def factory(config: ProxmoxConfig) -> FakeWindowsGuestClient:
        clients.append(FakeWindowsGuestClient(config))
        return clients[-1]

    monkeypatch.setattr(proxmox_artifact_smoke, "ProxmoxClient", factory)

    result = run_proxmox_artifact_smoke(
        scenario=load_scenario(scenario_path),
        oslab_config=make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        artifact_path=make_artifact(tmp_path),
        poll_interval_seconds=0,
    )

    assert result.passed is True
    assert clients[0].config_updates == []
    assert all(command[0] == "powershell.exe" for command in clients[0].commands)
    assert "C:\\Oslab\\artifact\\data\\input.txt" in clients[0].files
