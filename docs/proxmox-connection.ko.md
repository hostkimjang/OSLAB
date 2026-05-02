# Proxmox Connection Guide

언어: [English](proxmox-connection.md) | 한국어

이 문서는 `oslab`을 Proxmox 원격 lab에 연결하는 방법을 설명합니다. 제품별 smoke test는 이 공개 Proxmox setup guide와 분리해 문서화합니다.

## 핵심 개념

Proxmox를 웹 대시보드로 접속해서 쓰는 경우에도 `oslab`은 브라우저를 자동화하지 않습니다. Proxmox 웹 대시보드와 REST API는 같은 HTTPS service 위에서 동작합니다.

| 용도 | URL 예시 |
| --- | --- |
| Web dashboard | `https://proxmox.example.local:8006` |
| REST API base URL | `https://proxmox.example.local:8006/api2/json` |

`config/oslab.local.yaml`에는 dashboard URL인 `https://<proxmox-host>:8006`을 넣어도 됩니다. 내부에서는 `/api2/json`을 붙여 API base URL로 정규화합니다.

Proxmox 앞단에 Cloudflare Tunnel이나 다른 reverse proxy/WAF를 두는 경우, `oslab`은 브라우저 세션이 아니라 `/api2/json/*` API client로 접속한다는 점을 기준으로 정책을 잡아야 합니다. Proxy 정책이 non-browser API 요청을 Proxmox까지 통과시켜야 합니다.

## 연결 값

| 값 | 위치 | 설명 |
| --- | --- | --- |
| `apiUrl` | YAML config | Proxmox dashboard URL 또는 API base URL |
| `node` | YAML config | VM을 생성할 Proxmox node 이름 |
| `verifyTls` | YAML config | Self-signed cert lab이면 `false` 가능 |
| token id | env var | API token id, 예: `root@pam!oslab` |
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

`config/oslab.local.yaml`과 `config/oslab.local.env`는 `.gitignore` 대상입니다.

Example `config/oslab.local.env`:

```text
OSLAB_PROXMOX_TOKEN_ID=root@pam!oslab
OSLAB_PROXMOX_TOKEN_SECRET=<token-secret>
```

운영 원칙:

- Token secret은 config YAML에 넣지 않습니다.
- Token secret은 issue, commit message, README, report, chat에 붙여넣지 않습니다.
- Token 권한은 validation 전용 template, datastore, node, VMID range로 제한합니다.
- Shared CI runner에서는 project/group secret 또는 runner-level secret로 주입합니다.

현재 Windows QEMU Guest Agent demo에서는 `OSLAB_WINDOWS_USERNAME`과 `OSLAB_WINDOWS_PASSWORD`를 비워둡니다. 해당 값은 향후 WinRM/SSH guest channel용입니다.

## Create API Token

Proxmox web UI에서 `root@pam` 또는 validation 전용 user 아래 API token을 만듭니다.

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

필요 권한은 실행하는 lifecycle 범위에 따라 달라집니다.

| Operation | Needs |
| --- | --- |
| Provider config/connectivity check | API token 인증 가능 |
| Resource preflight | Node, VM resource, VM config read access |
| Clone/start/stop/destroy | Template과 validation VMID range에 대한 VM lifecycle permission |
| Artifact upload through QGA | QEMU guest agent endpoint 호출 permission |
| Archive expand/product execution | Guest agent command execution permission |
| Datastore-backed clone | Target storage/datastore access |

Validation node, template, storage, VMID range에 대해 가능한 좁은 token을 사용하는 것이 좋습니다.

개인 lab demo에서는 `root@pam!oslab`이 편하지만 권한이 큽니다. Shared lab이나 CI runner에서는 validation 전용 user/token을 만들고, 선택한 template, storage, node, clone VMID range에 필요한 권한만 부여하세요. Cluster별 least-privilege role이 문서화되기 전까지는 이 설정을 production Proxmox policy가 아니라 lab-demo setup으로 취급하는 편이 안전합니다.

## Template Requirements

Windows demo scenario에는 다음 조건을 만족하는 template VM이 필요합니다.

| Requirement | Notes |
| --- | --- |
| QEMU Guest Agent installed in Windows | 현재 Windows execution path에 필요 |
| QEMU Guest Agent enabled in Proxmox VM options | Proxmox가 guest agent endpoint를 노출해야 함 |
| PowerShell available | Fixture와 artifact command에서 사용 |
| Admin-capable execution context | 현재 guest preflight가 확인 |
| Network access from guest | Demo fixture가 portable Python/TinyCC를 다운로드할 때 필요 |

### Windows Template Preparation Checklist

Base Windows VM을 template으로 변환하기 전에 다음 순서로 준비합니다.

1. Windows를 설치하고 정상 boot를 확인합니다.
2. 필요한 VirtIO/network/storage driver를 설치합니다.
3. QEMU Guest Agent를 Windows 안에 설치합니다.
4. Proxmox VM Options에서 `QEMU Guest Agent`를 enabled로 설정합니다.
5. Windows 안에서 QEMU Guest Agent service가 running인지 확인합니다.
6. PowerShell command가 admin-capable context에서 실행되는지 확인합니다.
7. Demo fixture가 외부 package를 받아야 한다면 guest internet access를 확인합니다.
8. VM을 shutdown합니다.
9. Proxmox에서 stopped VM을 template으로 변환합니다.
10. Scenario의 `provider.templateVmId`를 template VMID로 맞춥니다.

QEMU Guest Agent 설치 흐름:

1. Proxmox VM `Hardware`에서 VirtIO Windows ISO를 CD/DVD로 연결합니다.
2. Windows guest에서 ISO를 열고 `virtio-win-guest-tools.exe`를 설치하거나 `guest-agent\qemu-ga-x86_64.msi`를 실행합니다.
3. Proxmox VM `Options`에서 `QEMU Guest Agent`를 `Enabled`로 설정합니다.
4. Windows를 reboot하거나 QEMU Guest Agent service를 시작합니다.
5. Service와 Proxmox agent endpoint가 모두 응답하는지 확인한 뒤 template으로 변환합니다.

Windows guest에서 관리자 PowerShell로 확인:

```powershell
Get-Service QEMU-GA
Set-Service QEMU-GA -StartupType Automatic
Start-Service QEMU-GA

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$PSVersionTable.PSVersion.ToString()"

New-Item -ItemType Directory -Force -Path C:\Oslab | Out-Null
```

현재 `guest-preflight`는 QGA를 통해 다음을 확인합니다.

| Check | Meaning |
| --- | --- |
| `powershell.version` | PowerShell 실행 가능 |
| `windows.admin` | Guest command가 admin-capable context에서 실행됨 |
| `powershell.execution_policy` | Execution policy 조회 가능. Commands는 `-ExecutionPolicy Bypass`로 실행 |
| `oslab.directory` | `C:\Oslab` 생성 가능 |
| `oslab.file_roundtrip` | QGA file upload/download 가능 |
| `oslab.cleanup_test_file` | Test file cleanup 가능 |

### Optional WinRM Preparation

현재 구현된 Windows demo path는 QEMU Guest Agent입니다. WinRM은 scenario model과 guest channel selection에서 고려하고 있지만, 현재 일반 demo run의 필수 경로는 아닙니다.

WinRM fallback 또는 향후 WinRM channel을 실험하려면 template VM에서 PowerShell remoting을 준비합니다.

```powershell
Set-NetConnectionProfile -NetworkCategory Private
Enable-PSRemoting -Force
Get-ChildItem WSMan:\localhost\Listener
```

`Enable-PSRemoting -Force`는 기본 WinRM listener와 firewall rule을 준비합니다. Domain network가 아닌 lab VM에서는 먼저 network profile을 `Private`로 바꾸는 편이 안전합니다.

WinRM을 실제 운영 경로로 쓰려면 추가로 인증 방식, firewall, 계정 권한, secret 관리, TLS/HTTP 정책을 팀 기준에 맞게 정해야 합니다. 이 repository의 현재 full demo runner는 QGA를 사용하므로, WinRM 준비가 없어도 generic Windows demo는 실행할 수 있어야 합니다.

Template을 만든 후 scenario provider field를 수정합니다.

```yaml
provider:
  type: proxmox
  template: windows11-template-qga
  templateVmId: 9101
  vmIdRange:
    start: 9102
    end: 9199
```

`templateVmId`는 일반 VM이 아니라 stopped Proxmox template을 가리켜야 합니다.

## Connectivity Checks

Config/env만 확인:

```powershell
uv run oslab preflight `
  --scenario scenarios/windows/demo-python-hello.example.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --provider-config-check
```

Proxmox `/version` 호출:

```powershell
uv run oslab preflight `
  --scenario scenarios/windows/demo-python-hello.example.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --provider-connectivity-check
```

VM을 만들지 않고 node, template, template flag, VMID range 확인:

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

다른 PowerShell에서 progress를 볼 수 있습니다.

```powershell
Get-Content runs\<run-id>\logs\progress.log -Wait
```

Result 확인:

```powershell
uv run oslab inspect-result --run-dir runs\<run-id>
```

## QEMU Guest Agent Debug Commands

Clone을 유지한 경우:

```powershell
uv run oslab boot-smoke `
  --scenario scenarios/windows/demo-python-hello.example.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --keep-vm
```

Kept VM 내부 command 실행:

```powershell
uv run oslab qga-exec `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --vm-id 9102 `
  --timeout-seconds 30 `
  -- powershell.exe -NoProfile -Command whoami
```

작은 text file upload/download:

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

정상적인 resource preflight 상태:

```text
usedInRange: <none>
```

`usedInRange`가 비어 있지 않다면, 같은 range로 parallel run을 더 시작하기 전에 어떤 VMID가 점유 중인지 먼저 확인합니다.

수동 복구 checklist:

1. `--provider-resource-check`가 표시한 VMID를 Proxmox에서 확인합니다.
2. 해당 VM이 `oslab-*` disposable clone인지, 또는 `--keep-vm`으로 의도적으로 남긴 VM인지 확인합니다.
3. Running 상태라면 Proxmox UI 또는 팀의 운영 절차로 stop합니다.
4. Clone을 destroy하고 disk purge를 함께 수행합니다.
5. Target storage에 해당 VM의 leftover disk가 남아 있지 않은지 확인합니다.
6. `--provider-resource-check`를 다시 실행해 `usedInRange: <none>`을 확인합니다.

CI에서는 제약 없는 parallel job들이 같은 VMID range를 공유하지 않게 합니다. CI concurrency/resource group을 쓰거나 runner/job family별로 별도 VMID range를 예약하세요.

## Troubleshooting

| Symptom | Likely cause | Next check |
| --- | --- | --- |
| Proxmox API에 접근 불가 | Host/IP/port route 문제, firewall, VPN, wrong `apiUrl` | `Test-NetConnection <host> -Port 8006` |
| TLS/certificate failure | Self-signed certificate + `verifyTls: true` | Lab에서는 `verifyTls: false` 또는 trusted cert 설치 |
| HTTP 401/403 | Wrong token id/secret 또는 권한 부족 | `--provider-config-check` 재실행, token id format 확인 |
| Cloudflare `403 Error 1010` 또는 reverse proxy가 `/api2/json/*`를 차단 | Proxy/WAF가 Proxmox 인증 전에 API client 시그니처를 차단함 | explicit `User-Agent`를 보내는 `oslab` 버전으로 업데이트하고, Proxmox API 트래픽에 대한 proxy/WAF allowlist 또는 rule 완화를 확인 |
| Node not found | `node`가 dashboard node name과 다름 | Proxmox tree node name과 `GET /nodes` output 확인 |
| Template VMID missing | Scenario `templateVmId`가 template과 다름 | Proxmox VMID와 scenario provider block 확인 |
| Template flag is not set | VM은 있지만 template 변환 안 됨 | Stopped base VM을 template으로 변환 |
| QGA command fails | QGA 미설치, 비활성화, service down | `boot-smoke --keep-vm`, guest에서 `Get-Service QEMU-GA` 확인 |
| Demo fixture download fails | Guest internet 없음 또는 package URL blocked | Tools preinstall 또는 internal package URL로 fixture 수정 |
| `usedInRange` is not empty | 이전 run이 clone을 유지했거나 destroy 실패 | Proxmox VM list에서 `oslab-*` clone 확인 |

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
