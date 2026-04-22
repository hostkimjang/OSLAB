# Getting Started

언어: [English](getting-started.md) | 한국어

이 문서는 generic demo를 실행하는 가장 짧은 경로를 설명합니다. Private product-specific 지식은 필요하지 않습니다.

Demo가 통과한 뒤에는 [Adoption Guide](adoption-guide.ko.md)를 따라 demo artifact를 자신의 folder 또는 installer로 바꾸면 됩니다. 전체 demo 목록은 [Demo Catalog](demos.ko.md)를 참고하세요.

## Prerequisites

Local runner:

- Python `>= 3.11`
- `uv`
- Proxmox API endpoint에 접근 가능한 network
- Proxmox API token

Proxmox lab:

- Windows template VM
- Windows template에 설치 및 활성화된 QEMU Guest Agent
- Guest에서 PowerShell 사용 가능
- Disposable clone을 위한 예약 VMID range
- Demo fixture가 runtime/toolchain package를 다운로드해야 한다면 guest internet access

## 1. Install Development Dependencies

Repository root에서 실행합니다.

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

`config/oslab.local.yaml`을 lab에 맞게 수정합니다.

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

`config/oslab.local.env`를 수정합니다.

```text
OSLAB_PROXMOX_TOKEN_ID=root@pam!oslab
OSLAB_PROXMOX_TOKEN_SECRET=<token-secret>
```

이 local files는 Git에서 ignore됩니다.

## 3. Create Local Scenario Copies

Lab-specific template과 VMID 값을 수정하기 전에 demo scenario를 복사합니다.

```powershell
Copy-Item scenarios/windows/demo-powershell-system.example.yaml scenarios/windows/demo-powershell-system.local.yaml
Copy-Item scenarios/windows/demo-python-hello.example.yaml scenarios/windows/demo-python-hello.local.yaml
Copy-Item scenarios/windows/demo-c-hello.example.yaml scenarios/windows/demo-c-hello.local.yaml
```

`scenarios/**/*.local.yaml`은 Git에서 ignore됩니다.

다음 파일을 수정합니다.

- `scenarios/windows/demo-powershell-system.local.yaml`
- `scenarios/windows/demo-python-hello.local.yaml`
- `scenarios/windows/demo-c-hello.local.yaml`

Provider block 예시:

```yaml
provider:
  template: windows11-template-qga
  templateVmId: 9101
  vmIdRange:
    start: 9102
    end: 9199
```

Template은 stopped 상태여야 하고, Proxmox template으로 변환되어 있어야 하며, QEMU Guest Agent가 설치 및 활성화되어 있어야 합니다.

## 4. Prepare Windows Template VM

현재 Windows demo는 QEMU Guest Agent 경로를 사용합니다. Template으로 변환하기 전에 Windows base VM에서 아래 조건을 맞추세요.

자세한 Proxmox/QGA/WinRM 준비 절차는 [docs/proxmox-connection.ko.md](proxmox-connection.ko.md)의 `Template Requirements`를 참고하세요.

필수 준비:

- Proxmox VM Options에서 QEMU Guest Agent enabled
- Windows guest 안에 QEMU Guest Agent installed/running
- PowerShell 사용 가능
- Guest Agent command가 admin-capable context에서 실행 가능
- Demo fixture가 Python/TinyCC를 다운로드한다면 guest internet access

Windows guest에서 관리자 PowerShell로 확인:

```powershell
Get-Service QEMU-GA
Set-Service QEMU-GA -StartupType Automatic
Start-Service QEMU-GA
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$PSVersionTable.PSVersion.ToString()"
```

WinRM fallback을 실험할 계획이라면 추가로 PowerShell remoting을 켭니다. 현재 demo에는 필수가 아닙니다.

```powershell
Set-NetConnectionProfile -NetworkCategory Private
Enable-PSRemoting -Force
Get-ChildItem WSMan:\localhost\Listener
```

준비가 끝나면 VM을 shutdown하고 Proxmox에서 template으로 변환합니다.

그 다음 두 local scenario copy에 실제 Proxmox 값을 반영합니다.

- `provider.template`: run metadata에 남길 사람이 읽는 template 이름
- `provider.templateVmId`: 실제 Proxmox template VMID
- `provider.vmIdRange`: `oslab` disposable clone 전용 VMID range

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

의존성이 가장 낮은 demo입니다. Runtime/toolchain download가 필요 없습니다.

```powershell
Test-Path validation/artifacts/powershell-system/run-system-demo.ps1
```

결과는 `True`여야 합니다.

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

예상 command marker:

```text
oslab powershell system demo
```

## 7. Run Python Demo

```powershell
Test-Path validation/artifacts/hello-python/run-python-demo.ps1
```

결과는 `True`여야 합니다.

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

Command stdout preview는 `inspect-result`로 확인합니다.

```powershell
uv run oslab inspect-result --run-dir runs\<run-id>
```

## 8. Run C Demo

```powershell
Test-Path validation/artifacts/hello-c/run-c-demo.ps1
```

결과는 `True`여야 합니다.

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

## 9. Watch And Inspect

Run id는 `oslab run` 마지막 출력에 표시됩니다. `runs/` 아래 최신 timestamp folder로도 확인할 수 있습니다.

최신 run directory 찾기:

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

`usedInRange: <none>`이면 disposable clone이 남아 있지 않은 상태입니다.
