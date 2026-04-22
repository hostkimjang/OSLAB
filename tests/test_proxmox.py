from __future__ import annotations

import json
import urllib.parse
from typing import Any

import pytest

from oslab.config import OslabConfig
from oslab.errors import ConfigError, ProviderError
from oslab.providers.base import TemplateRef, VmRef, VmSpec
from oslab.providers.proxmox import (
    ProxmoxClient,
    ProxmoxConfig,
    ProxmoxProvider,
    normalize_proxmox_api_url,
    proxmox_config_from_oslab,
)


class FakeResponse:
    def __init__(self, data: Any) -> None:
        self.body = json.dumps({"data": data}).encode("utf-8")

    def read(self) -> bytes:
        return self.body


class FakeTransport:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.requests = []

    def open(self, request, *, timeout: int):
        self.requests.append((request, timeout))
        if not self.responses:
            raise AssertionError("No fake response configured")
        return FakeResponse(self.responses.pop(0))


def make_client(responses: list[Any]) -> tuple[ProxmoxClient, FakeTransport]:
    transport = FakeTransport(responses)
    config = ProxmoxConfig(
        api_url="https://proxmox.example.local:8006/api2/json",
        node="pve01",
        token_id="root@pam!oslab",
        token_secret="secret",
        verify_tls=False,
        timeout_seconds=7,
    )
    return ProxmoxClient(config, transport=transport, sleep=lambda _: None), transport


def test_normalize_proxmox_api_url_accepts_dashboard_or_api_url() -> None:
    assert normalize_proxmox_api_url("https://pve.example.local:8006") == "https://pve.example.local:8006/api2/json"
    assert (
        normalize_proxmox_api_url("https://pve.example.local:8006/api2/json")
        == "https://pve.example.local:8006/api2/json"
    )


def test_clone_vm_sends_expected_proxmox_request() -> None:
    client, transport = make_client(["UPID:pve01:clone"])

    task_id = client.clone_vm(template_vmid=9000, new_vmid=9101, name="validation-test", full_clone=False)

    request, timeout = transport.requests[0]
    assert task_id == "UPID:pve01:clone"
    assert timeout == 7
    assert request.get_method() == "POST"
    assert request.full_url == "https://proxmox.example.local:8006/api2/json/nodes/pve01/qemu/9000/clone"
    assert request.get_header("Authorization") == "PVEAPIToken=root@pam!oslab=secret"
    assert request.get_header("Content-type") == "application/x-www-form-urlencoded"

    body = urllib.parse.parse_qs(request.data.decode("utf-8"))
    assert body == {"newid": ["9101"], "name": ["validation-test"], "full": ["0"]}


def test_wait_for_task_polls_until_ok() -> None:
    client, transport = make_client(
        [
            {"status": "running"},
            {"status": "stopped", "exitstatus": "OK"},
        ]
    )

    status = client.wait_for_task("UPID:pve01:task", poll_interval_seconds=0)

    assert status["exitstatus"] == "OK"
    assert len(transport.requests) == 2
    assert "/tasks/UPID%3Apve01%3Atask/status" in transport.requests[0][0].full_url


def test_wait_for_task_reports_failed_exit_status() -> None:
    client, _ = make_client([{"status": "stopped", "exitstatus": "ERROR"}])

    with pytest.raises(ProviderError, match="Proxmox task failed") as exc:
        client.wait_for_task("UPID:pve01:task", poll_interval_seconds=0, failure_class="vm_clone_failure")

    assert exc.value.details["failureClass"] == "vm_clone_failure"


def test_get_version_calls_remote_api() -> None:
    client, transport = make_client([{"version": "8.2.0", "release": "1"}])

    version = client.get_version()

    assert version == {"version": "8.2.0", "release": "1"}
    assert transport.requests[0][0].get_method() == "GET"
    assert transport.requests[0][0].full_url == "https://proxmox.example.local:8006/api2/json/version"


def test_guest_exec_sends_command_as_repeated_proxmox_parameters() -> None:
    client, transport = make_client([{"result": {"pid": 1234}}])

    result = client.guest_exec(
        9101,
        ["powershell.exe", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
    )

    request, _ = transport.requests[0]
    body = urllib.parse.parse_qs(request.data.decode("utf-8"))
    assert result == {"pid": 1234}
    assert request.get_method() == "POST"
    assert request.full_url == "https://proxmox.example.local:8006/api2/json/nodes/pve01/qemu/9101/agent/exec"
    assert body == {
        "command": ["powershell.exe", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
    }


def test_guest_exec_status_unwraps_agent_result() -> None:
    client, transport = make_client([{"result": {"exited": True, "exitcode": 0, "out-data": "ok\n"}}])

    result = client.get_guest_exec_status(9101, 1234)

    request, _ = transport.requests[0]
    assert result["exitcode"] == 0
    assert result["out-data"] == "ok\n"
    assert request.get_method() == "GET"
    assert (
        request.full_url
        == "https://proxmox.example.local:8006/api2/json/nodes/pve01/qemu/9101/agent/exec-status?pid=1234"
    )


def test_guest_file_write_sends_guest_path_content_and_encode_flag() -> None:
    client, transport = make_client([None])

    client.guest_file_write(9101, r"C:\Oslab\fixture.ps1", "Zm9v", encode=False)

    request, _ = transport.requests[0]
    body = urllib.parse.parse_qs(request.data.decode("utf-8"))
    assert request.get_method() == "POST"
    assert request.full_url == "https://proxmox.example.local:8006/api2/json/nodes/pve01/qemu/9101/agent/file-write"
    assert body == {"file": [r"C:\Oslab\fixture.ps1"], "content": ["Zm9v"], "encode": ["0"]}


def test_guest_file_read_unwraps_agent_result() -> None:
    client, transport = make_client([{"result": {"content": "hello\n", "truncated": 0}}])

    result = client.guest_file_read(9101, r"C:\Oslab\result.json")

    request, _ = transport.requests[0]
    assert result == {"content": "hello\n", "truncated": 0}
    assert request.get_method() == "GET"
    assert request.full_url.endswith(
        "/nodes/pve01/qemu/9101/agent/file-read?file=C%3A%5COslab%5Cresult.json"
    )


def test_provider_create_clone_waits_for_task() -> None:
    client, _ = make_client(["UPID:pve01:clone", {"status": "stopped", "exitstatus": "OK"}])
    provider = ProxmoxProvider(client)

    vm = provider.create_clone(TemplateRef(vm_id=9000), VmSpec(vm_id=9101, name="validation-test"))

    assert vm.vm_id == 9101
    assert vm.name == "validation-test"
    assert vm.node == "pve01"


def test_provider_stop_treats_already_stopped_as_success() -> None:
    client, transport = make_client([{"status": "stopped"}])
    provider = ProxmoxProvider(client)

    provider.stop_vm(VmRef(vm_id=9000))

    assert len(transport.requests) == 1
    assert "/status/current" in transport.requests[0][0].full_url


def test_provider_lists_used_vmids_from_cluster_resources() -> None:
    client, _ = make_client(
        [
            [
                {"vmid": 9000, "type": "qemu"},
                {"vmid": "9101", "type": "qemu"},
                {"type": "storage"},
            ]
        ]
    )
    provider = ProxmoxProvider(client)

    assert provider.list_used_vmids() == {9000, 9101}


def test_proxmox_config_resolves_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OSLAB_TOKEN_ID", "root@pam!oslab")
    monkeypatch.setenv("OSLAB_TOKEN_SECRET", "secret")
    config = OslabConfig(
        path=None,
        raw={
            "providerDefaults": {
                "proxmox": {
                    "apiUrl": "https://pve",
                    "node": "pve01",
                    "verifyTls": False,
                    "timeoutSeconds": 12,
                    "tokenEnv": {
                        "id": "OSLAB_TOKEN_ID",
                        "secret": "OSLAB_TOKEN_SECRET",
                    },
                }
            }
        },
    )

    proxmox = proxmox_config_from_oslab(config)

    assert proxmox.api_url == "https://pve/api2/json"
    assert proxmox.node == "pve01"
    assert proxmox.token_id == "root@pam!oslab"
    assert proxmox.token_secret == "secret"
    assert proxmox.verify_tls is False
    assert proxmox.timeout_seconds == 12


def test_proxmox_config_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OSLAB_MISSING_TOKEN_ID", raising=False)
    config = OslabConfig(
        path=None,
        raw={
            "providerDefaults": {
                "proxmox": {
                    "apiUrl": "https://pve/api2/json",
                    "node": "pve01",
                    "tokenEnv": {
                        "id": "OSLAB_MISSING_TOKEN_ID",
                        "secret": "OSLAB_MISSING_TOKEN_SECRET",
                    },
                }
            }
        },
    )

    with pytest.raises(ConfigError, match="Required environment variable is not set"):
        proxmox_config_from_oslab(config)
