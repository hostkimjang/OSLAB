from pathlib import Path

from oslab.config import OslabConfig
from oslab.models.scenario import load_scenario
from oslab.providers.proxmox import ProxmoxConfig
from oslab.runners import proxmox_clone_smoke
from oslab.runners.proxmox_clone_smoke import make_clone_name, run_proxmox_clone_smoke


class FakeProxmoxClient:
    def __init__(self, config: ProxmoxConfig) -> None:
        self.config = config
        self.destroyed_vmids: list[int] = []
        self.cloned_vmids: list[int] = []

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
        assert template_vmid == 9101
        assert new_vmid == 9102
        assert full_clone is False
        self.cloned_vmids.append(new_vmid)
        return "UPID:softverse:clone"

    def wait_for_task(self, task_id: str, *, failure_class: str = "provider_failure", **kwargs):
        return {"status": "stopped", "exitstatus": "OK"}

    def get_vm_status(self, vmid: int):
        return {"status": "stopped", "vmid": vmid}

    def destroy_vm(self, vmid: int, *, purge: bool = True):
        self.destroyed_vmids.append(vmid)
        return "UPID:softverse:destroy"


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


def test_make_clone_name_is_dns_like_and_contains_vmid() -> None:
    assert make_clone_name("supplyscan.gold-lite.windows", 9102) == "oslab-supplyscan-gold-lite-windows-9102"


def test_run_proxmox_clone_smoke_creates_and_destroys_clone(tmp_path: Path, monkeypatch) -> None:
    created_clients: list[FakeProxmoxClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> FakeProxmoxClient:
        client = FakeProxmoxClient(config)
        created_clients.append(client)
        return client

    monkeypatch.setattr(proxmox_clone_smoke, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/supplyscan/supplyscan-gold-lite.yaml"))

    result = run_proxmox_clone_smoke(
        scenario=scenario,
        oslab_config=make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
    )

    assert result.vm.vm_id == 9102
    assert result.destroyed is True
    assert result.kept is False
    assert created_clients[0].cloned_vmids == [9102]
    assert created_clients[0].destroyed_vmids == [9102]


def test_run_proxmox_clone_smoke_can_keep_clone(tmp_path: Path, monkeypatch) -> None:
    created_clients: list[FakeProxmoxClient] = []

    def fake_client_factory(config: ProxmoxConfig) -> FakeProxmoxClient:
        client = FakeProxmoxClient(config)
        created_clients.append(client)
        return client

    monkeypatch.setattr(proxmox_clone_smoke, "ProxmoxClient", fake_client_factory)
    scenario = load_scenario(Path("scenarios/windows/supplyscan/supplyscan-gold-lite.yaml"))

    result = run_proxmox_clone_smoke(
        scenario=scenario,
        oslab_config=make_config(tmp_path),
        proxmox_config=make_proxmox_config(),
        keep_vm=True,
    )

    assert result.vm.vm_id == 9102
    assert result.destroyed is False
    assert result.kept is True
    assert created_clients[0].destroyed_vmids == []
