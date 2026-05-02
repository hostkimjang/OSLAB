from __future__ import annotations

import base64
from pathlib import Path

from oslab.config import OslabConfig
from oslab.models.scenario import load_scenario
from oslab.providers.proxmox import ProxmoxConfig
from oslab.runners import proxmox_guest_preflight
from oslab.runners.proxmox_guest_preflight import run_proxmox_guest_preflight


class FakeProxmoxClient:
    def __init__(self, config: ProxmoxConfig, *, admin: bool = True) -> None:
        self.config = config
        self.admin = admin
        self.next_pid = 100
        self.status_by_pid: dict[int, dict] = {}
        self.files: dict[str, bytes] = {}
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
        command_text = " ".join(command)
        stdout = ""
        if "$PSVersionTable.PSVersion.ToString()" in command_text:
            stdout = "5.1.22621.1\r\n"
        elif "IsInRole" in command_text:
            stdout = "True\r\n" if self.admin else "False\r\n"
        elif "Get-ExecutionPolicy -List" in command_text:
            stdout = '{"LocalMachine":"RemoteSigned"}\r\n'
        self.status_by_pid[pid] = {"exited": 1, "exitcode": 0, "out-data": stdout, "err-data": ""}
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


def test_run_proxmox_guest_preflight_passes_and_cleans_up(tmp_path: Path, monkeypatch) -> None:
    created_clients: list[FakeProxmoxClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> FakeProxmoxClient:
        client = FakeProxmoxClient(config)
        created_clients.append(client)
        return client

    monkeypatch.setattr(proxmox_guest_preflight, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/supplyscan/supplyscan-gold-lite.yaml"))

    result = run_proxmox_guest_preflight(
        scenario=scenario,
        oslab_config=make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        poll_interval_seconds=0,
    )

    client = created_clients[0]
    assert result.passed is True
    assert result.vm.vm_id == 9102
    assert [check.id for check in result.checks] == [
        "powershell.version",
        "windows.admin",
        "powershell.execution_policy",
        "oslab.directory",
        "oslab.file_roundtrip",
        "oslab.cleanup_test_file",
    ]
    assert client.cloned_vmids == [9102]
    assert client.started_vmids == [9102]
    assert client.stopped_vmids == [9102]
    assert client.destroyed_vmids == [9102]


def test_run_proxmox_guest_preflight_reports_failed_check_and_still_cleans_up(
    tmp_path: Path,
    monkeypatch,
) -> None:
    created_clients: list[FakeProxmoxClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> FakeProxmoxClient:
        client = FakeProxmoxClient(config, admin=False)
        created_clients.append(client)
        return client

    monkeypatch.setattr(proxmox_guest_preflight, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/supplyscan/supplyscan-gold-lite.yaml"))

    result = run_proxmox_guest_preflight(
        scenario=scenario,
        oslab_config=make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        poll_interval_seconds=0,
    )

    failed = [check for check in result.checks if not check.passed]
    assert result.passed is False
    assert [check.id for check in failed] == ["windows.admin"]
    assert created_clients[0].destroyed_vmids == [9102]
