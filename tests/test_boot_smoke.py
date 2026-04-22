from pathlib import Path

from oslab.config import OslabConfig
from oslab.models.scenario import load_scenario
from oslab.providers.proxmox import ProxmoxConfig
from oslab.runners import proxmox_boot_smoke
from oslab.runners.proxmox_boot_smoke import run_proxmox_boot_smoke


class FakeProxmoxClient:
    def __init__(self, config: ProxmoxConfig) -> None:
        self.config = config
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


def test_run_proxmox_boot_smoke_starts_guest_and_cleans_up(tmp_path: Path, monkeypatch) -> None:
    created_clients: list[FakeProxmoxClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> FakeProxmoxClient:
        client = FakeProxmoxClient(config)
        created_clients.append(client)
        return client

    monkeypatch.setattr(proxmox_boot_smoke, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/supplyscan-gold-lite.yaml"))

    result = run_proxmox_boot_smoke(
        scenario=scenario,
        oslab_config=make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        poll_interval_seconds=0,
    )

    client = created_clients[0]
    assert result.vm.vm_id == 9102
    assert result.status.status == "running"
    assert result.guest_info is not None
    assert result.started is True
    assert result.destroyed is True
    assert result.kept is False
    assert client.cloned_vmids == [9102]
    assert client.started_vmids == [9102]
    assert client.stopped_vmids == [9102]
    assert client.destroyed_vmids == [9102]


def test_run_proxmox_boot_smoke_can_keep_running_vm(tmp_path: Path, monkeypatch) -> None:
    created_clients: list[FakeProxmoxClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> FakeProxmoxClient:
        client = FakeProxmoxClient(config)
        created_clients.append(client)
        return client

    monkeypatch.setattr(proxmox_boot_smoke, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/supplyscan-gold-lite.yaml"))

    result = run_proxmox_boot_smoke(
        scenario=scenario,
        oslab_config=make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        keep_vm=True,
        poll_interval_seconds=0,
    )

    client = created_clients[0]
    assert result.destroyed is False
    assert result.kept is True
    assert client.stopped_vmids == []
    assert client.destroyed_vmids == []
