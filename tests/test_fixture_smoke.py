from __future__ import annotations

import base64
import json
from pathlib import Path

from oslab.config import OslabConfig
from oslab.models.scenario import load_scenario
from oslab.providers.proxmox import ProxmoxConfig
from oslab.runners import proxmox_fixture_smoke
from oslab.runners.proxmox_fixture_smoke import run_proxmox_fixture_smoke


EXPECTED_JSON = {
    "schema_version": 1,
    "image_id": "gold-lite",
    "fixtures": [
        {
            "id": "known-registry-git",
            "name_contains": "Git",
            "required_sources": ["Registry"],
            "optional_sources": ["PE", "StartMenu"],
            "must_not_sources": ["Portable"],
        }
    ],
}


class FakeProxmoxClient:
    def __init__(self, config: ProxmoxConfig, *, fixture_exit_code: int = 0) -> None:
        self.config = config
        self.fixture_exit_code = fixture_exit_code
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
        if "-File" in command_text:
            exit_code = self.fixture_exit_code
            stdout = "gold-lite fixture manifest written to C:\\Oslab\\expected_inventory.json\r\n"
            if exit_code == 0:
                self.files["C:\\Oslab\\expected_inventory.json"] = json.dumps(EXPECTED_JSON).encode("utf-8")
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


def test_run_proxmox_fixture_smoke_uploads_executes_collects_and_cleans_up(
    tmp_path: Path,
    monkeypatch,
) -> None:
    created_clients: list[FakeProxmoxClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> FakeProxmoxClient:
        client = FakeProxmoxClient(config)
        created_clients.append(client)
        return client

    monkeypatch.setattr(proxmox_fixture_smoke, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/supplyscan-gold-lite.yaml"))

    result = run_proxmox_fixture_smoke(
        scenario=scenario,
        oslab_config=make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        poll_interval_seconds=0,
    )

    client = created_clients[0]
    fixture = result.fixtures[0]
    assert result.passed is True
    assert result.vm.vm_id == 9102
    assert fixture.id == "gold-lite"
    assert fixture.guest_path == "C:\\Oslab\\fixtures\\gold-lite.ps1"
    assert fixture.expected_output == "C:\\Oslab\\expected_inventory.json"
    assert fixture.collected_json == EXPECTED_JSON
    assert fixture.local_output_path is not None
    assert json.loads(fixture.local_output_path.read_text(encoding="utf-8")) == EXPECTED_JSON
    assert "C:\\Oslab\\fixtures\\gold-lite.ps1" in client.files
    assert client.destroyed_vmids == [9102]


def test_run_proxmox_fixture_smoke_reports_fixture_failure_and_cleans_up(
    tmp_path: Path,
    monkeypatch,
) -> None:
    created_clients: list[FakeProxmoxClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> FakeProxmoxClient:
        client = FakeProxmoxClient(config, fixture_exit_code=7)
        created_clients.append(client)
        return client

    monkeypatch.setattr(proxmox_fixture_smoke, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/supplyscan-gold-lite.yaml"))

    result = run_proxmox_fixture_smoke(
        scenario=scenario,
        oslab_config=make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        poll_interval_seconds=0,
    )

    fixture = result.fixtures[0]
    assert result.passed is False
    assert fixture.passed is False
    assert fixture.exit_code == 7
    assert fixture.message == "Fixture command failed"
    assert created_clients[0].destroyed_vmids == [9102]
