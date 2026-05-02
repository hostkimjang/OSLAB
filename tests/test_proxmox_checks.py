from pathlib import Path

from oslab.models.scenario import load_scenario
from oslab.providers.proxmox import ProxmoxConfig
from oslab.providers.proxmox_checks import check_proxmox_resources


class FakeProxmoxClient:
    def __init__(self, *, nodes, resources, configs=None) -> None:
        self.nodes = nodes
        self.resources = resources
        self.configs = configs or {}

    def list_nodes(self):
        return self.nodes

    def list_vm_resources(self):
        return self.resources

    def get_vm_config(self, vmid: int, *, node: str | None = None):
        return self.configs.get((node, vmid), {})


def make_config() -> ProxmoxConfig:
    return ProxmoxConfig(
        api_url="https://pve.example.local:8006",
        node="softverse",
        token_id="root@pam!auto_test",
        token_secret="secret",
        verify_tls=False,
    )


def test_check_proxmox_resources_passes_with_template_and_free_vmid() -> None:
    scenario = load_scenario(Path("scenarios/windows/supplyscan/supplyscan-gold-lite.yaml"))
    client = FakeProxmoxClient(
        nodes=[{"node": "softverse"}],
        resources=[
            {"vmid": 9101, "name": "windows11-template-qga-9101", "node": "softverse", "status": "stopped"},
            {"vmid": 9102, "name": "old-validation", "node": "softverse", "status": "stopped"},
        ],
        configs={("softverse", 9101): {"template": 1}},
    )

    result = check_proxmox_resources(client, scenario, make_config())

    assert result.passed is True
    assert result.node_exists is True
    assert result.vm_resource_count == 2
    assert result.template.found is True
    assert result.template.is_template is True
    assert result.vmid_range.used_in_range == [9102]
    assert result.vmid_range.recommended_vmid == 9103


def test_check_proxmox_resources_reports_missing_node_and_template() -> None:
    scenario = load_scenario(Path("scenarios/windows/supplyscan/supplyscan-gold-lite.yaml"))
    client = FakeProxmoxClient(nodes=[{"node": "other-node"}], resources=[])

    result = check_proxmox_resources(client, scenario, make_config())

    assert result.passed is False
    assert "Configured node `softverse` was not found" in result.issues
    assert "Template VMID `9101` was not found" in result.issues


def test_check_proxmox_resources_reports_non_template_vmid() -> None:
    scenario = load_scenario(Path("scenarios/windows/supplyscan/supplyscan-gold-lite.yaml"))
    client = FakeProxmoxClient(
        nodes=[{"node": "softverse"}],
        resources=[{"vmid": 9101, "name": "ordinary-vm", "node": "softverse", "status": "running"}],
        configs={("softverse", 9101): {"template": 0}},
    )

    result = check_proxmox_resources(client, scenario, make_config())

    assert result.passed is False
    assert "VMID `9101` exists but is not marked as a template" in result.issues
