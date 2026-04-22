"""Proxmox provider implementation.

This module intentionally keeps Proxmox API details behind the provider layer.
Tests use fake transports, so the core behavior can harden without a real lab.
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from oslab.config import OslabConfig
from oslab.errors import CleanupError, ConfigError, ProviderError, VmCloneError
from oslab.providers.base import GuestInfo, TemplateRef, VmRef, VmSpec, VmStatus
from oslab.providers.vmid import used_vmids_from_resources


@dataclass(frozen=True)
class ProxmoxConfig:
    """Connection details for the Proxmox API."""

    api_url: str
    node: str
    token_id: str
    token_secret: str
    verify_tls: bool = True
    timeout_seconds: int = 30

    @property
    def base_url(self) -> str:
        return normalize_proxmox_api_url(self.api_url)


def normalize_proxmox_api_url(url: str) -> str:
    """Accept either a dashboard URL or an API URL and return API base URL."""

    normalized = url.rstrip("/")
    if normalized.endswith("/api2/json"):
        return normalized
    return f"{normalized}/api2/json"


class ProxmoxTransport:
    """Small transport protocol wrapper for easy testing."""

    def open(self, request: urllib.request.Request, *, timeout: int) -> Any:
        context = None
        if getattr(request, "_oslab_verify_tls", True) is False:
            context = ssl._create_unverified_context()
        return urllib.request.urlopen(request, timeout=timeout, context=context)


class ProxmoxClient:
    """Low-level Proxmox API client."""

    def __init__(
        self,
        config: ProxmoxConfig,
        *,
        transport: ProxmoxTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.transport = transport or ProxmoxTransport()
        self.sleep = sleep
        self.monotonic = monotonic

    def request(self, method: str, path: str, params: dict[str, Any] | list[tuple[str, Any]] | None = None) -> Any:
        """Perform a Proxmox API request and return the `data` field."""

        method = method.upper()
        params = params or {}
        url = self._build_url(path)
        data = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"PVEAPIToken={self.config.token_id}={self.config.token_secret}",
        }

        if method in {"GET", "DELETE"} and params:
            url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
        elif params:
            data = urllib.parse.urlencode(params, doseq=True).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        setattr(request, "_oslab_verify_tls", self.config.verify_tls)

        try:
            response = self.transport.open(request, timeout=self.config.timeout_seconds)
            raw_body = response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ProviderError(
                f"Proxmox API request failed: {method} {path}",
                details={"status": exc.code, "body": body},
            ) from exc
        except urllib.error.URLError as exc:
            raise ProviderError(
                f"Cannot reach Proxmox API: {self.config.base_url}",
                details={"error": str(exc.reason)},
            ) from exc

        if not raw_body:
            return None

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ProviderError(
                f"Proxmox API returned invalid JSON: {method} {path}",
                details={"body": raw_body.decode("utf-8", errors="replace")},
            ) from exc

        if isinstance(payload, dict) and "errors" in payload and payload["errors"]:
            raise ProviderError(
                f"Proxmox API returned errors: {method} {path}",
                details={"errors": payload["errors"]},
            )
        if not isinstance(payload, dict) or "data" not in payload:
            raise ProviderError(
                f"Proxmox API response missing `data`: {method} {path}",
                details={"payload": payload},
            )
        return payload["data"]

    def list_vm_resources(self) -> list[dict[str, Any]]:
        data = self.request("GET", "/cluster/resources", {"type": "vm"})
        if not isinstance(data, list):
            raise ProviderError("Proxmox cluster resources response must be a list")
        return [item for item in data if isinstance(item, dict)]

    def list_nodes(self) -> list[dict[str, Any]]:
        data = self.request("GET", "/nodes")
        if not isinstance(data, list):
            raise ProviderError("Proxmox nodes response must be a list")
        return [item for item in data if isinstance(item, dict)]

    def get_version(self) -> dict[str, Any]:
        """Return Proxmox API version information.

        This is intentionally lightweight and is used by
        `oslab preflight --provider-connectivity-check` to prove that the
        remote dashboard/API endpoint is reachable with the configured token.
        """

        data = self.request("GET", "/version")
        if not isinstance(data, dict):
            raise ProviderError("Proxmox version response must be a mapping", details={"data": data})
        return data

    def get_vm_config(self, vmid: int, *, node: str | None = None) -> dict[str, Any]:
        node_name = node or self.config.node
        data = self.request("GET", f"/nodes/{node_name}/qemu/{vmid}/config")
        if not isinstance(data, dict):
            raise ProviderError("Proxmox VM config response must be a mapping", details={"data": data})
        return data

    def clone_vm(self, *, template_vmid: int, new_vmid: int, name: str, full_clone: bool) -> str:
        data = self.request(
            "POST",
            f"/nodes/{self.config.node}/qemu/{template_vmid}/clone",
            {"newid": new_vmid, "name": name, "full": int(full_clone)},
        )
        if not isinstance(data, str) or not data:
            raise VmCloneError("Proxmox clone response did not return a task id", details={"data": data})
        return data

    def start_vm(self, vmid: int) -> str:
        return self._task_request("POST", f"/nodes/{self.config.node}/qemu/{vmid}/status/start")

    def stop_vm(self, vmid: int) -> str:
        return self._task_request("POST", f"/nodes/{self.config.node}/qemu/{vmid}/status/stop")

    def destroy_vm(self, vmid: int, *, purge: bool = True) -> str:
        return self._task_request("DELETE", f"/nodes/{self.config.node}/qemu/{vmid}", {"purge": int(purge)})

    def get_vm_status(self, vmid: int) -> dict[str, Any]:
        data = self.request("GET", f"/nodes/{self.config.node}/qemu/{vmid}/status/current")
        if not isinstance(data, dict):
            raise ProviderError("Proxmox VM status response must be a mapping", details={"data": data})
        return data

    def get_guest_network_interfaces(self, vmid: int) -> dict[str, Any]:
        data = self.request("GET", f"/nodes/{self.config.node}/qemu/{vmid}/agent/network-get-interfaces")
        if not isinstance(data, dict):
            raise ProviderError("Proxmox guest info response must be a mapping", details={"data": data})
        return data

    def guest_exec(self, vmid: int, command: list[str]) -> dict[str, Any]:
        data = self.request(
            "POST",
            f"/nodes/{self.config.node}/qemu/{vmid}/agent/exec",
            {"command": command},
        )
        result = _unwrap_guest_agent_result(data)
        if not isinstance(result, dict):
            raise ProviderError("Proxmox guest exec response must be a mapping", details={"data": data})
        if "pid" not in result:
            raise ProviderError("Proxmox guest exec response missing pid", details={"data": data})
        return result

    def get_guest_exec_status(self, vmid: int, pid: int) -> dict[str, Any]:
        data = self.request("GET", f"/nodes/{self.config.node}/qemu/{vmid}/agent/exec-status", {"pid": pid})
        result = _unwrap_guest_agent_result(data)
        if not isinstance(result, dict):
            raise ProviderError("Proxmox guest exec-status response must be a mapping", details={"data": data})
        return result

    def guest_file_write(self, vmid: int, guest_path: str, content: str, *, encode: bool = True) -> None:
        data = self.request(
            "POST",
            f"/nodes/{self.config.node}/qemu/{vmid}/agent/file-write",
            {"file": guest_path, "content": content, "encode": int(encode)},
        )
        if data is not None:
            raise ProviderError("Proxmox guest file-write response must be null", details={"data": data})

    def guest_file_read(self, vmid: int, guest_path: str) -> dict[str, Any]:
        data = self.request("GET", f"/nodes/{self.config.node}/qemu/{vmid}/agent/file-read", {"file": guest_path})
        result = _unwrap_guest_agent_result(data)
        if not isinstance(result, dict):
            raise ProviderError("Proxmox guest file-read response must be a mapping", details={"data": data})
        return result

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        encoded = urllib.parse.quote(task_id, safe="")
        data = self.request("GET", f"/nodes/{self.config.node}/tasks/{encoded}/status")
        if not isinstance(data, dict):
            raise ProviderError("Proxmox task status response must be a mapping", details={"data": data})
        return data

    def wait_for_task(
        self,
        task_id: str,
        *,
        timeout_seconds: int = 300,
        poll_interval_seconds: float = 2.0,
        failure_class: str = "provider_failure",
    ) -> dict[str, Any]:
        """Poll a Proxmox UPID until it finishes or times out."""

        deadline = self.monotonic() + timeout_seconds
        last_status: dict[str, Any] | None = None
        while self.monotonic() <= deadline:
            last_status = self.get_task_status(task_id)
            if last_status.get("status") == "stopped":
                exit_status = last_status.get("exitstatus")
                if exit_status == "OK":
                    return last_status
                raise ProviderError(
                    f"Proxmox task failed: {task_id}",
                    details={"failureClass": failure_class, "task": last_status},
                )
            self.sleep(poll_interval_seconds)

        raise ProviderError(
            f"Timed out waiting for Proxmox task: {task_id}",
            details={"failureClass": failure_class, "lastStatus": last_status},
        )

    def _task_request(self, method: str, path: str, params: dict[str, Any] | None = None) -> str:
        data = self.request(method, path, params)
        if not isinstance(data, str) or not data:
            raise ProviderError(f"Proxmox task request did not return a task id: {method} {path}", details={"data": data})
        return data

    def _build_url(self, path: str) -> str:
        return f"{self.config.base_url}/{path.lstrip('/')}"


def _unwrap_guest_agent_result(data: Any) -> Any:
    if isinstance(data, dict) and "result" in data:
        return data["result"]
    return data


class ProxmoxProvider:
    """Provider implementation backed by Proxmox API calls."""

    def __init__(self, client: ProxmoxClient) -> None:
        self.client = client

    def create_clone(self, template: TemplateRef, vm_spec: VmSpec) -> VmRef:
        if template.vm_id is None:
            raise VmCloneError("Proxmox MVP requires template.vm_id")

        task_id = self.client.clone_vm(
            template_vmid=template.vm_id,
            new_vmid=vm_spec.vm_id,
            name=vm_spec.name,
            full_clone=vm_spec.full_clone,
        )
        self.client.wait_for_task(task_id, failure_class="vm_clone_failure")
        return VmRef(vm_id=vm_spec.vm_id, name=vm_spec.name, node=self.client.config.node)

    def start_vm(self, vm: VmRef) -> None:
        task_id = self.client.start_vm(vm.vm_id)
        self.client.wait_for_task(task_id, failure_class="provider_failure")

    def stop_vm(self, vm: VmRef) -> None:
        current = self.get_vm_status(vm)
        if current.status == "stopped":
            return
        task_id = self.client.stop_vm(vm.vm_id)
        self.client.wait_for_task(task_id, failure_class="provider_failure")

    def destroy_vm(self, vm: VmRef) -> None:
        try:
            task_id = self.client.destroy_vm(vm.vm_id)
            self.client.wait_for_task(task_id, failure_class="cleanup_failure")
        except ProviderError as exc:
            raise CleanupError(
                f"Failed to destroy Proxmox VM {vm.vm_id}",
                details={"vmId": vm.vm_id, "cause": exc.details},
            ) from exc

    def get_vm_status(self, vm: VmRef) -> VmStatus:
        raw = self.client.get_vm_status(vm.vm_id)
        return VmStatus(vm_id=vm.vm_id, status=str(raw.get("status") or "unknown"), raw=raw)

    def get_guest_info(self, vm: VmRef) -> GuestInfo:
        return GuestInfo(vm_id=vm.vm_id, raw=self.client.get_guest_network_interfaces(vm.vm_id))

    def list_used_vmids(self) -> set[int]:
        return used_vmids_from_resources(self.client.list_vm_resources())

    def list_nodes(self) -> set[str]:
        return {str(item["node"]) for item in self.client.list_nodes() if "node" in item}


def proxmox_config_from_oslab(config: OslabConfig) -> ProxmoxConfig:
    """Resolve Proxmox connection config from oslab config and env vars."""

    provider_defaults = config.raw.get("providerDefaults") or {}
    proxmox = provider_defaults.get("proxmox") or {}
    if not isinstance(proxmox, dict):
        raise ConfigError("`providerDefaults.proxmox` must be a mapping")

    api_url = proxmox.get("apiUrl")
    node = proxmox.get("node")
    if not isinstance(api_url, str) or not api_url.strip():
        raise ConfigError("`providerDefaults.proxmox.apiUrl` must be a non-empty string")
    if not isinstance(node, str) or not node.strip():
        raise ConfigError("`providerDefaults.proxmox.node` must be a non-empty string")

    token_env = proxmox.get("tokenEnv") or {}
    if not isinstance(token_env, dict):
        raise ConfigError("`providerDefaults.proxmox.tokenEnv` must be a mapping")
    token_id_env = token_env.get("id")
    token_secret_env = token_env.get("secret")
    if not isinstance(token_id_env, str) or not token_id_env.strip():
        raise ConfigError("`providerDefaults.proxmox.tokenEnv.id` must be a non-empty string")
    if not isinstance(token_secret_env, str) or not token_secret_env.strip():
        raise ConfigError("`providerDefaults.proxmox.tokenEnv.secret` must be a non-empty string")

    verify_tls = proxmox.get("verifyTls", True)
    if not isinstance(verify_tls, bool):
        raise ConfigError("`providerDefaults.proxmox.verifyTls` must be a boolean")

    timeout_seconds = proxmox.get("timeoutSeconds", 30)
    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        raise ConfigError("`providerDefaults.proxmox.timeoutSeconds` must be a positive integer")

    return ProxmoxConfig(
        api_url=normalize_proxmox_api_url(api_url),
        node=node,
        token_id=config.resolve_env_reference(token_id_env),
        token_secret=config.resolve_env_reference(token_secret_env),
        verify_tls=verify_tls,
        timeout_seconds=timeout_seconds,
    )
