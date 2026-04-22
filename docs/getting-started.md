# Getting Started

Language: English | [한국어](getting-started.ko.md)

This guide runs the generic demos. It does not require private product-specific knowledge.

After the demos pass, use [Adoption Guide](adoption-guide.md) to replace the demo artifact with your own folder or installer. For the full demo list, see [Demo Catalog](demos.md).

## Prerequisites

Local runner:

- Python `>= 3.11`
- `uv`
- Network access to a Proxmox API endpoint
- A Proxmox API token

Proxmox lab:

- A Windows template VM
- QEMU Guest Agent installed and enabled in the Windows template
- PowerShell available in the guest
- A reserved VMID range for disposable clones
- Guest internet access, unless you preinstall or internally host demo runtime/toolchain packages

## 1. Install Development Dependencies

From the repository root:

```powershell
uv sync
uv run oslab --help
uv run pytest
```

## 2. Create Local Config

```powershell
Copy-Item config/oslab.local.example.yaml config/oslab.local.yaml
Copy-Item config/oslab.local.example.env config/oslab.local.env
```

Edit `config/oslab.local.yaml` for your Proxmox lab:

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

Edit `config/oslab.local.env`:

```text
OSLAB_PROXMOX_TOKEN_ID=root@pam!oslab
OSLAB_PROXMOX_TOKEN_SECRET=<token-secret>
```

These local files are ignored by Git.

## 3. Create Local Scenario Copies

Copy the demo scenarios before editing lab-specific template and VMID values:

```powershell
Copy-Item scenarios/windows/demo-powershell-system.example.yaml scenarios/windows/demo-powershell-system.local.yaml
Copy-Item scenarios/windows/demo-python-hello.example.yaml scenarios/windows/demo-python-hello.local.yaml
Copy-Item scenarios/windows/demo-c-hello.example.yaml scenarios/windows/demo-c-hello.local.yaml
```

`scenarios/**/*.local.yaml` is ignored by Git.

Edit:

- `scenarios/windows/demo-powershell-system.local.yaml`
- `scenarios/windows/demo-python-hello.local.yaml`
- `scenarios/windows/demo-c-hello.local.yaml`

Set:

```yaml
provider:
  template: windows11-template-qga
  templateVmId: 9101
  vmIdRange:
    start: 9102
    end: 9199
```

The template should be stopped, converted to a Proxmox template, and have QEMU Guest Agent installed and enabled.

## 4. Prepare Windows Template VM

The current Windows demos use QEMU Guest Agent. Before converting the base VM into a template, prepare the Windows guest.

For detailed Proxmox/QGA/WinRM setup steps, see `Template Requirements` in [docs/proxmox-connection.md](proxmox-connection.md).

Required setup:

- QEMU Guest Agent enabled in Proxmox VM Options
- QEMU Guest Agent installed and running inside Windows
- PowerShell available
- Guest Agent commands run in an admin-capable context
- Guest internet access if demo fixtures download Python/TinyCC

Verify inside the Windows guest with Administrator PowerShell:

```powershell
Get-Service QEMU-GA
Set-Service QEMU-GA -StartupType Automatic
Start-Service QEMU-GA
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$PSVersionTable.PSVersion.ToString()"
```

If you plan to experiment with WinRM fallback, also enable PowerShell remoting. This is not required for the current QGA demos.

```powershell
Set-NetConnectionProfile -NetworkCategory Private
Enable-PSRemoting -Force
Get-ChildItem WSMan:\localhost\Listener
```

After setup, shut down the VM and convert it to a Proxmox template.

Then update both local scenario copies with the real Proxmox values:

- `provider.template`: human-readable template name used in run metadata
- `provider.templateVmId`: actual Proxmox template VMID
- `provider.vmIdRange`: disposable clone range reserved for `oslab`

## 5. Check Proxmox Readiness

```powershell
uv run oslab validate-scenario --scenario scenarios/windows/demo-python-hello.local.yaml

uv run oslab preflight `
  --scenario scenarios/windows/demo-python-hello.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --provider-config-check

uv run oslab preflight `
  --scenario scenarios/windows/demo-python-hello.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --provider-connectivity-check

uv run oslab preflight `
  --scenario scenarios/windows/demo-python-hello.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --provider-resource-check
```

Healthy state:

```text
Template flag confirmed
usedInRange: <none>
```

## 6. Run PowerShell System Demo

This is the lowest-dependency demo. It does not need a runtime/toolchain download.

```powershell
Test-Path validation/artifacts/powershell-system/run-system-demo.ps1
```

The check should return `True`.

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-powershell-system.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/powershell-system `
  --guest-timeout-seconds 300 `
  --command-timeout-seconds 300 `
  --poll-interval-seconds 5
```

Expected output:

```text
[OK] Run completed
     status: passed
     failureClass: <none>
```

Expected command marker:

```text
oslab powershell system demo
```

## 7. Run Python Demo

```powershell
Test-Path validation/artifacts/hello-python/run-python-demo.ps1
```

The check should return `True`.

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-python-hello.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/hello-python `
  --guest-timeout-seconds 300 `
  --command-timeout-seconds 300 `
  --poll-interval-seconds 5
```

Expected output:

```text
[OK] Run completed
     status: passed
     failureClass: <none>
```

Run `inspect-result` to see the command stdout preview.

## 8. Run C Demo

```powershell
Test-Path validation/artifacts/hello-c/run-c-demo.ps1
```

The check should return `True`.

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-c-hello.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/hello-c `
  --guest-timeout-seconds 300 `
  --command-timeout-seconds 300 `
  --poll-interval-seconds 5
```

Expected output:

```text
[OK] Run completed
     status: passed
     failureClass: <none>
```

Run `inspect-result` to see the command stdout preview.

## 9. Watch And Inspect

The run id is printed near the end of `oslab run`. It is also the newest timestamped folder under `runs/`.

Find the latest run directory:

```powershell
$runDir = Get-ChildItem runs -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1
$runDir.FullName
```

Live progress:

```powershell
Get-Content "$($runDir.FullName)\logs\progress.log" -Wait
```

Summary:

```powershell
uv run oslab inspect-result --run-dir $runDir.FullName
```

Open report:

```powershell
Invoke-Item "$($runDir.FullName)\reports\result.html"
```

Cleanup check:

```powershell
uv run oslab preflight `
  --scenario scenarios/windows/demo-python-hello.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --provider-resource-check
```

`usedInRange: <none>` means no disposable clone is left behind.
