"""Ownership and Windows desktop setup for the disposable app-matrix lab."""

from __future__ import annotations

import base64
import json
import re
import secrets
import time
from pathlib import Path
from urllib.parse import quote

from oslab.config import load_config
from oslab.env_file import load_env_file
from oslab.errors import ProviderError
from oslab.guests.qemu_agent import QemuAgentChannel
from oslab.providers.base import VmRef
from oslab.providers.proxmox import ProxmoxClient, ProxmoxProvider, proxmox_config_from_oslab
from oslab.providers.vmid import LocalVmidLock, VmidRange, VmidReservation, used_vmids_from_resources

ROOT = r"C:\OSLabWall"
USER = "MatrixQA"
READY = ROOT + r"\interactive.ok"
SERVER = Path(__file__).with_name("listen.ps1")


def log(message):
    print(message, flush=True)


def write_json(path, value):
    scratch = path.with_suffix(".new")
    scratch.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    scratch.replace(path)


class Lab:
    def __init__(self, args):
        self.output = args.output.resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.ledger = self.output / "owned.json"
        self.identity = self.output / "owner.txt"
        if not self.identity.exists():
            with self.identity.open("x", encoding="ascii") as handle:
                handle.write("oslab-matrix-" + secrets.token_hex(5))
        self.prefix = self.identity.read_text(encoding="ascii").strip()
        if not re.fullmatch(r"oslab-matrix-[0-9a-f]{10}", self.prefix):
            raise ValueError("Invalid capture owner ID")
        self.owned = json.loads(self.ledger.read_text(encoding="utf-8")) if self.ledger.exists() else {}
        self.config_path = args.config.resolve()
        self.env_path = args.env_file.resolve() if args.env_file else None
        if self.env_path is not None:
            load_env_file(self.env_path)
        config = load_config(self.config_path)
        self.client = ProxmoxClient(proxmox_config_from_oslab(config))
        self.provider = ProxmoxProvider(self.client)
        self.guest = QemuAgentChannel(self.client)
        self.lease_dir = config.output_root / ".locks"
        self.ids = VmidRange(args.vmid_start, args.vmid_end)
        self.source = args.template_vmid
        self.node = self.client.config.node
        self.api = f"/nodes/{quote(self.node, safe='')}"

    def ref(self, role):
        return VmRef(self.owned[role]["id"], f"{self.prefix}-{role}", self.node)

    def verify(self, vm):
        state = self.client.get_vm_config(vm.vm_id)
        if state.get("name") != vm.name or not vm.name.startswith(self.prefix + "-"):
            raise RuntimeError("Capture VM ownership changed")
        return state

    def resources(self):
        return used_vmids_from_resources(self.client.list_vm_resources())

    def ps(self, vm, command, timeout=45, expected=(0,)):
        script = (
            "$ErrorActionPreference='Stop'\n$ProgressPreference='SilentlyContinue'\n"
            "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)\n" + command
        )
        data = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        result = self.guest.execute(vm, ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", data],
                                    timeout_seconds=timeout, poll_interval_seconds=.45)
        if expected is not None and result.exit_code not in expected:
            message = re.sub(r"Win9![0-9a-f]{44}", "[redacted]", result.stderr)
            raise RuntimeError(f"Guest PowerShell exited {result.exit_code}: {message[:500]}")
        return result

    def wait(self, vm, condition, seconds=140):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                if self.ps(vm, "if (" + condition + ") { 'ready' }", timeout=8).stdout.strip() == "ready":
                    return
            except (RuntimeError, ProviderError):
                pass
            time.sleep(1.8)
        raise TimeoutError(f"{vm.name.removeprefix(self.prefix + '-')}: guest condition timed out")

    def task(self, vm, name, command, *, logon=False, system=False):
        if not re.fullmatch(r"[A-Za-z0-9]+", name):
            raise ValueError("Invalid capture task name")
        data = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
        user = "'SYSTEM'" if system else rf'"$env:COMPUTERNAME\{USER}"'
        logon_type = "ServiceAccount" if system else "Interactive"
        trigger = "-Trigger (New-ScheduledTaskTrigger -AtLogOn -User $account)" if logon else ""
        start = "" if logon else f"Start-ScheduledTask -TaskName '{name}'"
        self.ps(vm, f"""
            $account={user}
            $action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -STA -EncodedCommand {data}'
            $principal=New-ScheduledTaskPrincipal -UserId $account -LogonType {logon_type} -RunLevel Highest
            Register-ScheduledTask -TaskName '{name}' -Action $action -Principal $principal {trigger} -Force | Out-Null
            {start}
        """)

    def upload(self, vm, basename, content):
        if not re.fullmatch(r"[\w.-]+", basename) or basename in (".", ".."):
            raise ValueError("Unsafe guest artifact name")
        self.guest.upload_bytes(vm, ROOT + "\\" + basename, content)

    def create(self, role, template, *, full=False):
        if role in self.owned:
            raise RuntimeError(f"{role} already belongs to this capture")
        lease = LocalVmidLock(self.lease_dir).reserve(self.ids, used_vmids=self.resources())
        self.owned[role] = {"id": lease.vm_id}
        write_json(self.ledger, self.owned)
        vm = self.ref(role)
        task = self.client.clone_vm(template_vmid=template, new_vmid=vm.vm_id, name=vm.name, full_clone=full)
        self.client.wait_for_task(task, timeout_seconds=400)
        state = self.verify(vm)
        ports = [key for key in state if re.fullmatch(r"net\d+", key)]
        settings = {"memory": 5120, "balloon": 0, "cores": 2, "sockets": 1}
        if ports:
            settings["delete"] = ",".join(ports)
        self.client.request("PUT", f"{self.api}/qemu/{vm.vm_id}/config", settings)
        if any(re.fullmatch(r"net\d+", key) for key in self.verify(vm)):
            raise RuntimeError("Guest still has a network adapter")
        self.provider.start_vm(vm)
        log(f"{role}: offline Windows VM started")
        return vm

    def prepare(self):
        if self.owned:
            raise RuntimeError("Capture already owns VM reservations")
        if not self.client.get_vm_config(self.source).get("template"):
            raise RuntimeError("Select a Windows source template")
        base = self.create("base", self.source, full=True)
        self.wait(base, "$true", 210)
        password = "Win9!" + secrets.token_hex(22)
        self.ps(base, rf"""
            New-Item -Path '{ROOT}' -ItemType Directory -Force | Out-Null
            $account=New-LocalUser -Name '{USER}' -Password (ConvertTo-SecureString '{password}' -AsPlainText -Force) -PasswordNeverExpires
            Add-LocalGroupMember -SID 'S-1-5-32-544' -Member $account
            $oobe='HKLM:\Software\Policies\Microsoft\Windows\OOBE'
            New-Item $oobe -Force | Out-Null
            New-ItemProperty $oobe DisablePrivacyExperience -Type DWord -Value 1 -Force | Out-Null
        """)
        self.upload(base, "listen.ps1", SERVER.read_bytes())
        self.task(base, "OSLabMatrixLogin", rf"""
            $ErrorActionPreference='Stop'
            $winlogon='HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
            Set-ItemProperty $winlogon AutoAdminLogon '0'
            Remove-ItemProperty $winlogon DefaultPassword -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 4
            [IO.File]::WriteAllText('{READY}','ready')
        """, logon=True)
        self.autologon(base, password)
        self.ps(base, "shutdown.exe /r /f /t 2")
        self.wait(base, f"Test-Path '{READY}'", 240)
        self.ps(base, f"Remove-Item -LiteralPath '{READY}'")
        self.ps(base, "shutdown.exe /s /f /t 2")
        deadline = time.monotonic() + 110
        while self.client.get_vm_status(base.vm_id)["status"] != "stopped":
            if time.monotonic() >= deadline:
                raise TimeoutError("Filming source did not shut down after desktop setup")
            time.sleep(2)
        converted = self.client.request("POST", f"{self.api}/qemu/{base.vm_id}/template")
        if isinstance(converted, str):
            self.client.wait_for_task(converted)
        if not self.verify(base).get("template"):
            raise RuntimeError("Filming source did not become an isolated template")
        log("Offline filming source ready")

    def start_desktop(self, vm):
        self.verify(vm)
        self.wait(vm, "$true", 175)
        password = "Win9!" + secrets.token_hex(22)
        self.ps(vm, rf"""
            Set-LocalUser -Name '{USER}' -Password (ConvertTo-SecureString '{password}' -AsPlainText -Force)
            if (Test-Path -LiteralPath '{READY}') {{ Remove-Item -LiteralPath '{READY}' }}
        """)
        self.autologon(vm, password)
        self.ps(vm, "shutdown.exe /r /f /t 2")
        self.wait(vm, f"Test-Path '{READY}'", 190)
        log(f"{vm.name.rsplit('-', 1)[-1]}: Windows desktop ready")

    def autologon(self, vm, password):
        self.ps(vm, rf"""
            $winlogon='HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
            Set-ItemProperty $winlogon AutoAdminLogon '1'
            Set-ItemProperty $winlogon DefaultUserName '{USER}'
            Set-ItemProperty $winlogon DefaultDomainName $env:COMPUTERNAME
            Set-ItemProperty $winlogon DefaultPassword '{password}'
            New-ItemProperty $winlogon AutoLogonCount -PropertyType DWord -Value 1 -Force | Out-Null
        """)

    def remove(self, role):
        vm = self.ref(role)
        active = self.client.request("GET", f"{self.api}/tasks", {"vmid": vm.vm_id, "source": "active", "limit": 30})
        for row in active:
            self.client.wait_for_task(row["upid"])
        if vm.vm_id in self.resources():
            state = self.verify(vm)
            if not state.get("template"):
                self.provider.stop_vm(vm)
            self.provider.destroy_vm(vm)
        if vm.vm_id in self.resources():
            raise RuntimeError("Temporary capture VM still exists")
        stores = self.client.request("GET", f"{self.api}/storage")
        for item in stores:
            if not item.get("active") or "images" not in item.get("content", "").split(","):
                continue
            storage = quote(item["storage"], safe="")
            disks = self.client.request("GET", f"{self.api}/storage/{storage}/content", {"vmid": vm.vm_id})
            if any("volid" in row for row in disks):
                raise RuntimeError("Temporary capture volume still exists")
        lease = self.lease_dir / f"vmid-{vm.vm_id}.lock"
        if lease.read_text(encoding="utf-8") != str(vm.vm_id):
            raise RuntimeError("Capture reservation ownership changed")
        VmidReservation(vm.vm_id, lease).release()
        self.owned.pop(role)
        write_json(self.ledger, self.owned)
        log(f"{role}: VM, storage and reservation removed")

    def cleanup(self, *, keep_base=False):
        for role in reversed(list(self.owned)):
            if role != "base" or not keep_base:
                self.remove(role)
        if not keep_base:
            if any(str(row.get("name", "")).startswith(self.prefix + "-") for row in self.client.list_vm_resources()):
                raise RuntimeError("An untracked capture guest still exists")
            (self.output / "cleanup.ok").write_text("confirmed\n", encoding="utf-8")
