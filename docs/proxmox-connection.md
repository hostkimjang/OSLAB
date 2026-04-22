# Proxmox Connection Guide

Language: English | [한국어](proxmox-connection.ko.md)

This guide explains how to connect `oslab` to a remote Proxmox lab. Product-specific smoke tests should be documented separately from this public Proxmox setup guide.

## Core Concept

Even if you normally use Proxmox through the web dashboard, `oslab` does not automate the browser. The Proxmox web dashboard and REST API are served by the same HTTPS service.

| Use | URL example |
| --- | --- |
| Web dashboard | `https://proxmox.example.local:8006` |
| REST API base URL | `https://proxmox.example.local:8006/api2/json` |

You can put the dashboard URL, such as `https://<proxmox-host>:8006`, in `config/oslab.local.yaml`. `oslab` normalizes it to the API base URL by appending `/api2/json` when needed.

## Connection Values

| Value | Location | Description |
| --- | --- | --- |
| `apiUrl` | YAML config | Proxmox dashboard URL or API base URL |
| `node` | YAML config | Proxmox node name where clones are created |
| `verifyTls` | YAML config | Can be `false` for a self-signed lab certificate |
| token id | env var | API token id, for example `root@pam!oslab` |
| token secret | env var | API token secret |

Example:

```yaml
providerDefaults:
  proxmox:
    apiUrl: "https://proxmox.example.local:8006"
    node: "pve01"
    verifyTls: false
    timeoutSeconds: 30
    tokenEnv:
      id: OSLAB_PROXMOX_TOKEN_ID
      secret: OSLAB_PROXMOX_TOKEN_SECRET
```

## Local Config

```powershell
Copy-Item config/oslab.local.example.yaml config/oslab.local.yaml
Copy-Item config/oslab.local.example.env config/oslab.local.env
```

`config/oslab.local.yaml` and `config/oslab.local.env` are ignored by Git.

Example `config/oslab.local.env`:

```text
OSLAB_PROXMOX_TOKEN_ID=root@pam!oslab
OSLAB_PROXMOX_TOKEN_SECRET=<token-secret>
```

Operating rules:

- Do not put token secrets in config YAML.
- Do not paste token secrets into issues, commit messages, README files, reports, or chats.
- Scope token permissions to the validation template, datastore, node, and VMID range where possible.
- On shared CI runners, inject tokens through project/group secrets or runner-level secrets.

For the current Windows QEMU Guest Agent demos, leave `OSLAB_WINDOWS_USERNAME` and `OSLAB_WINDOWS_PASSWORD` unset. Those values are for future WinRM/SSH guest channels.

## Create API Token

In the Proxmox web UI, create an API token under a user such as `root@pam` or a dedicated validation user.

Typical UI path:

```text
Datacenter -> Permissions -> API Tokens -> Add
```

Token id format:

```text
user@realm!token-name
```

Example:

```text
root@pam!oslab
```

Permission needs depend on how much of the lifecycle you run:

| Operation | Needs |
| --- | --- |
| Provider config/connectivity check | API token can authenticate |
| Resource preflight | Read access to nodes, VM resources, and VM config |
| Clone/start/stop/destroy | VM lifecycle permissions on the template and validation VMID range |
| Artifact upload through QGA | Permission to call QEMU guest agent endpoints |
| Archive expand/product execution | Guest agent command execution permission |
| Datastore-backed clone | Access to the target storage/datastore |

Use the narrowest practical token for the validation node, template, storage, and VMID range.

For a personal lab demo, `root@pam!oslab` is convenient but overpowered. For a shared lab or CI runner, create a dedicated validation user/token and grant only the permissions needed for the chosen template, storage, node, and clone VMID range. Until a least-privilege role is documented for your cluster, treat this as a lab-demo setup rather than a production Proxmox policy.

## Template Requirements

Windows demo scenarios require a template VM with:

| Requirement | Notes |
| --- | --- |
| QEMU Guest Agent installed in Windows | Required for the current Windows execution path |
| QEMU Guest Agent enabled in Proxmox VM options | Proxmox must expose guest agent endpoints |
| PowerShell available | Used for fixtures and artifact commands |
| Admin-capable execution context | Current guest preflight checks this |
| Network access from guest | Needed if demo fixtures download portable Python/TinyCC |

### Windows Template Preparation Checklist

Prepare the base Windows VM before converting it to a template.

1. Install Windows and confirm it boots.
2. Install any required VirtIO/network/storage drivers.
3. Install QEMU Guest Agent inside Windows.
4. Enable `QEMU Guest Agent` in Proxmox VM Options.
5. Confirm the QEMU Guest Agent service is running inside Windows.
6. Confirm PowerShell commands run in an admin-capable context.
7. Confirm guest internet access if demo fixtures must download packages.
8. Shut down the VM.
9. Convert the stopped VM to a Proxmox template.
10. Set scenario `provider.templateVmId` to the template VMID.

QEMU Guest Agent installation flow:

1. Attach the VirtIO Windows ISO to the VM from Proxmox VM `Hardware`.
2. Open the ISO inside Windows and install `virtio-win-guest-tools.exe`, or run `guest-agent\qemu-ga-x86_64.msi`.
3. Enable `QEMU Guest Agent` from Proxmox VM `Options`.
4. Reboot Windows or start the QEMU Guest Agent service.
5. Confirm that both the Windows service and the Proxmox agent endpoint respond before converting the VM into a template.

Verify inside the Windows guest with Administrator PowerShell:

```powershell
Get-Service QEMU-GA
Set-Service QEMU-GA -StartupType Automatic
Start-Service QEMU-GA

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$PSVersionTable.PSVersion.ToString()"

New-Item -ItemType Directory -Force -Path C:\Oslab | Out-Null
```

Current `guest-preflight` checks:

| Check | Meaning |
| --- | --- |
| `powershell.version` | PowerShell can run |
| `windows.admin` | Guest command runs in an admin-capable context |
| `powershell.execution_policy` | Execution policy can be queried. Commands run with `-ExecutionPolicy Bypass` |
| `oslab.directory` | `C:\Oslab` can be created |
| `oslab.file_roundtrip` | QGA file upload/download works |
| `oslab.cleanup_test_file` | Test file cleanup works |

### Optional WinRM Preparation

The implemented Windows demo path currently uses QEMU Guest Agent. WinRM exists in the scenario model and guest channel selection design, but it is not required for the current demo run path.

If you plan to experiment with WinRM fallback or a future WinRM channel, prepare PowerShell remoting in the template VM:

```powershell
Set-NetConnectionProfile -NetworkCategory Private
Enable-PSRemoting -Force
Get-ChildItem WSMan:\localhost\Listener
```

`Enable-PSRemoting -Force` creates the default WinRM listener and firewall rule. On non-domain lab VMs, set the network profile to `Private` first.

For a real WinRM operating path, also define team policy for authentication, firewall rules, account permissions, secret handling, and TLS/HTTP behavior. The current full demo runner uses QGA, so the generic Windows demos should run without WinRM being configured.

After creating your template, update scenario fields:

```yaml
provider:
  type: proxmox
  template: windows11-template-qga
  templateVmId: 9101
  vmIdRange:
    start: 9102
    end: 9199
```

`templateVmId` must point to a stopped Proxmox template, not a normal VM.

## Connectivity Checks

Config and env only:

```powershell
uv run oslab preflight `
  --scenario scenarios/windows/demo-python-hello.example.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --provider-config-check
```

Call Proxmox `/version`:

```powershell
uv run oslab preflight `
  --scenario scenarios/windows/demo-python-hello.example.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --provider-connectivity-check
```

Check node, template, template flag, and VMID range without creating a VM:

```powershell
uv run oslab preflight `
  --scenario scenarios/windows/demo-python-hello.example.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --provider-resource-check
```

Expected healthy cleanup state:

```text
[OK] VMID range inspected
     range: 9102-9199
     usedInRange: <none>
```

## Run A Small Demo

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-python-hello.example.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/hello-python `
  --guest-timeout-seconds 300 `
  --command-timeout-seconds 300
```

Watch progress from another PowerShell:

```powershell
Get-Content runs\<run-id>\logs\progress.log -Wait
```

Inspect result:

```powershell
uv run oslab inspect-result --run-dir runs\<run-id>
```

## QEMU Guest Agent Debug Commands

If you keep a clone running:

```powershell
uv run oslab boot-smoke `
  --scenario scenarios/windows/demo-python-hello.example.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --keep-vm
```

Run a command inside the kept VM:

```powershell
uv run oslab qga-exec `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --vm-id 9102 `
  --timeout-seconds 30 `
  -- powershell.exe -NoProfile -Command whoami
```

Upload/download a small text file:

```powershell
uv run oslab qga-upload `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --vm-id 9102 `
  --local-path README.md `
  --guest-path C:\Oslab\README.uploaded.md

uv run oslab qga-download `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --vm-id 9102 `
  --guest-path C:\Oslab\README.uploaded.md `
  --local-path runs\qga-download-readme.md
```

## Stale VM And VMID Range Recovery

The healthy resource preflight state is:

```text
usedInRange: <none>
```

If `usedInRange` is not empty, do not start more parallel runs against the same range until you understand what is using those VMIDs.

Manual recovery checklist:

1. In Proxmox, inspect the VMID listed by `--provider-resource-check`.
2. Confirm it is an `oslab-*` disposable clone or a VM you intentionally kept with `--keep-vm`.
3. If it is running, stop it from the Proxmox UI or with your normal Proxmox operational process.
4. Destroy the clone with disk purge enabled.
5. Check the target storage for leftover disks from the destroyed VM.
6. Rerun `--provider-resource-check` and confirm `usedInRange: <none>`.

For CI, do not share one VMID range across unconstrained parallel jobs. Use CI concurrency/resource groups, or allocate a separate VMID range per runner/job family.

## Troubleshooting

| Symptom | Likely cause | Next check |
| --- | --- | --- |
| Cannot reach Proxmox API | Host/IP/port route problem, firewall, VPN, or wrong `apiUrl` | `Test-NetConnection <host> -Port 8006` |
| TLS/certificate failure | Self-signed certificate with `verifyTls: true` | Set `verifyTls: false` for lab or install trusted cert |
| HTTP 401/403 | Wrong token id/secret or insufficient permissions | Rerun `--provider-config-check`; verify token id format |
| Node not found | `node` does not match dashboard node name | Check Proxmox tree node name and `GET /nodes` output |
| Template VMID missing | Scenario `templateVmId` does not match template | Check Proxmox VMID and scenario provider block |
| Template flag is not set | VM exists but was not converted to template | Convert stopped base VM to template |
| QGA command fails | QGA is not installed, enabled, or running | Use `boot-smoke --keep-vm`, then check `Get-Service QEMU-GA` in guest |
| Demo fixture download fails | Guest has no internet access or package URL is blocked | Preinstall tools or change fixture to internal package URL |
| `usedInRange` is not empty | Previous run kept or failed to destroy a clone | Inspect Proxmox VM list for `oslab-*` clones |

## Code Map

| Concept | Code |
| --- | --- |
| Config/env resolution | `src/oslab/providers/proxmox.py::proxmox_config_from_oslab` |
| HTTP transport | `src/oslab/providers/proxmox.py::ProxmoxTransport` |
| API client | `src/oslab/providers/proxmox.py::ProxmoxClient` |
| Resource preflight | `src/oslab/providers/proxmox_checks.py` |
| VMID allocation | `src/oslab/providers/vmid.py` |
| QEMU Guest Agent command/file transfer | `src/oslab/guests/qemu_agent.py` |
| Full run orchestration | `src/oslab/runners/scenario_runner.py` |
