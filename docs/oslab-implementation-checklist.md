# oslab 구현 체크리스트

최종 업데이트: 2026-04-21

## 현재 상태 요약

`oslab`은 현재 Python CLI 골격, scenario/config 검증, Proxmox API 연결, 읽기 전용 lab preflight, VMID 할당, 실제 clone/boot smoke, QEMU Guest Agent command 실행, 작은 파일 upload/download, Windows guest preflight, Windows fixture upload/execution/expected output 수집까지 구현되어 있습니다.

최근 실제 lab 결과:

- Proxmox API 연결: 통과
- Node `softverse`: 통과
- Windows template VMID `9101`: 통과
- Template flag: 통과
- Clone smoke: 통과
- Clone smoke 이후 cleanup: 통과
- Windows QEMU Guest Agent 수정 clone `9101`을 새 template `windows11-template-qga-9101`로 변환
- Boot smoke: `9101` template에서 `9102` clone 생성, boot, QEMU Guest Agent 확인, cleanup 통과
- QGA file transfer: `README.md`를 `9102` clone에 upload/download하고 SHA256 hash 일치 확인
- Windows guest preflight: PowerShell version, admin context, execution policy, `C:\Oslab` directory, file round-trip, cleanup check 통과
- Fixture smoke: `gold-lite.ps1` upload/execution, `C:\Oslab\expected_inventory.json` collect/JSON parse, cleanup 통과

최근 로컬 테스트 결과:

```text
uv run pytest
77 passed
```

## 구현 완료

### 프로젝트 골격

- [x] `pyproject.toml` 기반 `uv` workflow
- [x] `oslab` console entrypoint
- [x] `src/oslab` 아래 package layout
- [x] Pytest 테스트 suite
- [x] `.gitignore`에 local run, env file, virtualenv, cache, Python metadata 제외 규칙 추가

### 문서

- [x] `docs/oslab-platform-plan.md`
- [x] `docs/oslab-expert-review.md`
- [x] `docs/proxmox-connection.md`
- [x] `docs/oslab-implementation-checklist.md`
- [x] `README.md`에 `oslab` 사용 흐름 반영
- [x] 기존 SupplyScan 전용 architecture 문서는 `docs/architecture.md`에 legacy context로 유지

### Scenario 및 Config

- [x] Windows SupplyScan smoke scenario
- [x] Linux generic smoke example scenario
- [x] Local config example
- [x] Git에 올리지 않는 local config 흐름: `config/oslab.local.yaml`
- [x] Git에 올리지 않는 local env 흐름: `config/oslab.local.env`
- [x] YAML top-level 구조 검증
- [x] Scenario schema version 검증
- [x] Provider, guest, artifact, fixture, assertion, report, cleanup 검증
- [x] Windows scenario의 template VMID를 `9100`으로 갱신
- [x] Windows scenario의 clone range를 `9101-9199`로 갱신
- [x] QEMU Guest Agent가 설치된 Windows template VMID `9101`로 갱신
- [x] Windows scenario의 clone range를 `9102-9199`로 갱신

### Console 및 Secret 처리

- [x] `[OK]`, `[WARN]`, `[FAIL]`, `[..]` 기반 구조화 console output
- [x] Token id redaction
- [x] Token secret 미출력
- [x] 구조화된 error detail 출력
- [x] Local env file parser
- [x] PowerShell에서 생성된 env file의 UTF-8 BOM 처리
- [x] Env file 작성 형식 안내
- [x] 기존 VM 대상으로 QEMU Guest Agent command를 실행하는 `oslab qga-exec`
- [x] 기존 VM 대상으로 작은 파일을 업로드하는 `oslab qga-upload`
- [x] 기존 VM에서 텍스트 파일을 다운로드하는 `oslab qga-download`
- [x] Windows guest readiness를 검증하는 `oslab guest-preflight`
- [x] Scenario fixture를 실행하고 expected output을 수집하는 `oslab fixture-smoke`

### Proxmox API 기반

- [x] Proxmox API URL normalization
  - `https://host:8006` 입력 허용
  - 내부적으로 `https://host:8006/api2/json` 형태로 정규화
- [x] API token authentication header
- [x] Lab/self-signed certificate 환경을 위한 TLS verification toggle
- [x] Timeout config
- [x] `GET /version`
- [x] `GET /nodes`
- [x] `GET /cluster/resources?type=vm`
- [x] `GET /nodes/<node>/qemu/<vmid>/config`
- [x] `POST /nodes/<node>/qemu/<templateVmId>/clone`
- [x] `POST /nodes/<node>/qemu/<vmid>/status/start`
- [x] `POST /nodes/<node>/qemu/<vmid>/status/stop`
- [x] `DELETE /nodes/<node>/qemu/<vmid>?purge=1`
- [x] `POST /nodes/<node>/qemu/<vmid>/agent/exec`
- [x] `GET /nodes/<node>/qemu/<vmid>/agent/exec-status`
- [x] `POST /nodes/<node>/qemu/<vmid>/agent/file-write`
- [x] `GET /nodes/<node>/qemu/<vmid>/agent/file-read`
- [x] Proxmox async task polling

### Provider 및 VMID

- [x] Provider contracts
- [x] `TemplateRef`
- [x] `VmSpec`
- [x] `VmRef`
- [x] `VmStatus`
- [x] `GuestInfo`
- [x] Proxmox provider implementation
- [x] VMID range parser
- [x] Proxmox resource에서 사용 중인 VMID 추출
- [x] Local lock-file 기반 VMID reservation
- [x] 자동 VMID 추천

### Proxmox 읽기 전용 Preflight

- [x] `oslab preflight --provider-config-check`
- [x] `oslab preflight --provider-connectivity-check`
- [x] `oslab preflight --provider-resource-check`
- [x] Node 존재 여부 확인
- [x] Template VMID 존재 여부 확인
- [x] Template flag 확인
- [x] VM resource count 출력
- [x] VMID range 사용 현황 출력
- [x] 권장 VMID 출력

실제 실행 명령:

```powershell
uv run oslab preflight `
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --provider-resource-check
```

최근 실제 출력 요약:

```text
[OK] Proxmox API connectivity
     version: 9.1.1
     release: 9.1
[OK] Configured Proxmox node exists
     configuredNode: softverse
     vmResourceCount: 111
[OK] Template VMID exists
     templateVmId: 9101
     templateName: windows11-template-qga-9101
[OK] Template flag confirmed
[OK] VMID range inspected
     range: 9102-9199
     usedInRange: <none>
     recommendedVmId: 9102
```

### Clone Smoke

- [x] `oslab clone-smoke`
- [x] Clone 전 resource preflight
- [x] 자동 VMID reservation
- [x] Clone name generation
- [x] Template 기반 clone 생성
- [x] Clone status 조회
- [x] 기본 cleanup
- [x] `--keep-vm`
- [x] `--full-clone`
- [x] Create/destroy 및 keep behavior 테스트
- [x] 실제 Proxmox clone smoke 통과

실제 실행 명령:

```powershell
uv run oslab clone-smoke `
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env
```

최근 실제 출력 요약:

```text
[OK] Clone smoke completed
     cloneVmId: 9102
     cloneName: oslab-supplyscan-gold-lite-windows-9102
     cloneStatus: stopped
     destroyed: true
     kept: false
```

### Boot Smoke

- [x] `oslab boot-smoke`
- [x] Clone 생성
- [x] VM start
- [x] Running status wait
- [x] QEMU Guest Agent network info wait
- [x] 기본 stop/destroy cleanup
- [x] 실패 시 best-effort cleanup
- [x] `--keep-vm`
- [x] Boot timeout option
- [x] Guest timeout option
- [x] Poll interval option
- [x] Start/guest/cleanup 및 keep behavior 테스트
- [x] 실제 Proxmox boot smoke가 QEMU Guest Agent 확인 및 cleanup까지 통과

실제 실행 명령:

```powershell
uv run oslab boot-smoke `
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --boot-timeout-seconds 300 `
  --guest-timeout-seconds 300 `
  --poll-interval-seconds 5
```

이전 실제 실패:

```text
[FAIL] Timed out waiting for QEMU Guest Agent on VM 9101
details:
  status: 500
  body: {"message":"QEMU guest agent is not running\n","data":null}
```

실패 후 cleanup 검증 결과:

```text
usedInRange: <none>
recommendedVmId: 9101
```

새 template `9101` 전환 후 실제 성공:

```text
[OK] Boot smoke completed
     cloneVmId: 9102
     cloneName: oslab-supplyscan-gold-lite-windows-9102
     cloneStatus: running
     guestInfo: available
     started: true
     destroyed: true
     kept: false
```

## 해결된 Blocker

### Windows Template의 QEMU Guest Agent

- [x] Windows template에서 clone boot 이후 QEMU Guest Agent가 실행되도록 수정

확인된 증거:

- Proxmox VM config에는 `agent: 1`이 설정되어 있음
- VMID `9101`의 Proxmox config는 `template: 1`, `agent: 1`, `status: stopped`
- `oslab qga-exec`로 `cmd.exe /c echo oslab-qga-check` 실행 성공
- Clone/start/cleanup 경로는 정상 동작

원인이었던 항목:

- Windows 내부에 QEMU Guest Agent service가 설치되어 있지 않음
- `9100` template 생성 시 QEMU Guest Agent 설치가 누락됨

남은 주의점:

- 기존 `9100` template은 legacy template으로 남아 있음
- 현재 scenario는 QGA가 포함된 `9101` template을 사용함
- 새 clone은 `9102-9199` range에서 생성해야 함

향후 template 회귀가 의심될 때의 debug 명령:

```powershell
uv run oslab boot-smoke `
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --keep-vm `
  --guest-timeout-seconds 30
```

이후 Proxmox console에서 유지된 clone에 접속해 확인:

```powershell
Get-Service | Where-Object { $_.Name -match "qemu|guest" -or $_.DisplayName -match "qemu|guest" }
```

Service가 존재하면:

```powershell
Start-Service QEMU-GA
Set-Service QEMU-GA -StartupType Automatic
```

Service가 없다면 VirtIO tools ISO에서 QEMU Guest Agent를 설치한 뒤 template을 다시 만들어야 합니다.

## 미구현 항목

### Guest Channel 구현

- [x] QEMU Guest Agent command execution wrapper
- [x] QEMU Guest Agent file upload/download
- [x] QEMU Guest Agent stdout/stderr/exit code capture
- [ ] WinRM probe
- [ ] WinRM command execution
- [ ] WinRM file transfer
- [ ] Linux용 SSH probe
- [ ] Linux용 SSH command execution
- [ ] Linux용 SSH upload/download
- [ ] 실제 channel 구현과 연결된 automatic guest channel selection

### Windows Guest 내부 Preflight

- [x] `$PSVersionTable` 실행
- [x] `Get-ExecutionPolicy -List` 확인
- [x] Admin context 확인
- [x] `C:\Oslab` test file 생성/삭제
- [ ] Known app baseline 확인
- [ ] Fallback이 활성화된 경우 WinRM readiness 확인
- [x] QEMU Guest Agent command execution readiness 확인

### Fixture 및 Artifact 실행

- [x] `validation/fixtures/windows/gold-lite.ps1` upload
- [x] Guest 안에서 fixture script 실행
- [x] `C:\Oslab\expected_inventory.json` collect
- [ ] Folder artifact upload
- [ ] Installer artifact upload
- [ ] Artifact command template 실행
- [ ] Remote execution용 command token render
- [ ] Scanner output JSON collect
- [ ] Log collect

### SupplyScan Plugin

- [ ] `plugins/supplyscan` package
- [ ] Raw SupplyScan JSON parser
- [ ] Canonical inventory model writer
- [ ] Evidence normalization
- [ ] Source normalization
- [ ] Version/publisher/path mapping
- [ ] Plugin metadata

### Assertion Engine

- [ ] Assertion result model
- [ ] `inventory.contains`
- [ ] `inventory.sourcePresent`
- [ ] `inventory.sourceAbsent`
- [ ] `inventory.evidencePresent`
- [ ] `file.exists`
- [ ] `file.notExists`
- [ ] `directory.exists`
- [ ] `command.exitCode`
- [ ] `service.exists`
- [ ] `process.exists`
- [ ] `package.exists`
- [ ] Severity/gating rules

### Reports

- [x] Skeleton JSON run result
- [ ] Full JSON validation report
- [ ] JUnit XML writer
- [ ] HTML report writer
- [ ] Report consistency tests
- [ ] `run.json`에 raw/normalized/result path 첨부
- [ ] Provider/guest log를 `runs/<run-id>/logs` 아래 보존

### Full Validation Run

- [ ] Skeleton 상태의 `oslab run`을 실제 orchestration으로 교체
- [ ] Resource preflight
- [ ] Clone
- [ ] Start
- [ ] Guest channel select
- [ ] Guest preflight
- [ ] Fixture apply
- [ ] Artifact install/copy
- [ ] Product execution
- [ ] Output collection
- [ ] Plugin normalize
- [ ] Assertion evaluate
- [ ] Report write
- [ ] Cleanup
- [ ] `--keep-vm-on-failure`
- [ ] Stale VM metadata

### Cleanup 및 Recovery

- [ ] `oslab cleanup-stale`
- [ ] Range 안의 오래된 `oslab-*` VM 제거
- [ ] Stale VM report
- [ ] Cleanup dry-run mode
- [ ] Cleanup confirmation/force flag

### CI Integration

- [ ] GitLab CI example
- [ ] GitHub Actions example
- [ ] JUnit artifact upload
- [ ] HTML artifact upload
- [ ] `runs/**` artifact upload
- [ ] CI concurrency/resource group guidance
- [ ] Secret configuration guide

### Linux 구현

- [x] Linux scenario example
- [x] Linux guest channel selection design
- [ ] Linux SSH implementation
- [ ] Linux shell fixture execution
- [ ] Linux file/package/process assertions
- [ ] Linux real Proxmox template
- [ ] Linux boot smoke
- [ ] Linux guest preflight

### Security 및 운영

- [x] Token secret redaction
- [x] Git에 올리지 않는 env file 흐름
- [ ] 초기에 노출된 테스트 token rotation
- [ ] Least-privilege Proxmox token role 문서화
- [ ] Validation VMID range permission boundary 문서화
- [ ] Production cluster에 broad permission을 주지 않는 운영 가이드
- [ ] Commit 전 secret scanning check

## 현재 실제 Lab 설정

Local-only files:

- `config/oslab.local.yaml`
- `config/oslab.local.env`

현재 Proxmox 값:

```text
apiUrl: https://192.168.2.254:8006/api2/json
node: softverse
templateVmId: 9101
templateName: windows11-template-qga-9101
cloneRange: 9102-9199
```

위 local files는 ignore 대상이며 commit하면 안 됩니다.

## 안전한 명령

읽기 전용:

```powershell
uv run oslab validate-scenario --scenario scenarios/windows/supplyscan-gold-lite.yaml

uv run oslab preflight `
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --provider-resource-check
```

Clone을 만들고 삭제:

```powershell
uv run oslab clone-smoke `
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env
```

Clone을 만들고 start/stop/delete:

```powershell
uv run oslab boot-smoke `
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env
```

Clone을 만들고 Windows guest readiness 확인 후 삭제:

```powershell
uv run oslab guest-preflight `
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env
```

Clone을 만들고 fixture 실행 및 expected output 수집 후 삭제:

```powershell
uv run oslab fixture-smoke `
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env
```

Debug mode: VM이 남을 수 있음

```powershell
uv run oslab boot-smoke `
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --keep-vm `
  --guest-timeout-seconds 30
```

유지된 VM에서 QEMU Guest Agent command 실행:

```powershell
uv run oslab qga-exec `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --vm-id 9102 `
  --timeout-seconds 30 `
  -- powershell.exe -NoProfile -Command whoami
```

유지된 VM으로 작은 파일 upload:

```powershell
uv run oslab qga-upload `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --vm-id 9102 `
  --local-path README.md `
  --guest-path C:\Oslab\README.uploaded.md
```

유지된 VM에서 텍스트 파일 download:

```powershell
uv run oslab qga-download `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --vm-id 9102 `
  --guest-path C:\Oslab\README.uploaded.md `
  --local-path runs\qga-download-readme.md
```

## 권장 다음 순서

1. Known app baseline 확인
2. Folder artifact upload 구현
3. Artifact command template remote execution 구현
4. Scanner output JSON collect
5. SupplyScan plugin normalize 구현
6. Assertion engine 구현
7. JSON/JUnit report에 fixture/artifact/assertion 결과 연결
8. Full `oslab run` orchestration으로 통합
9. CI example에서 `guest-preflight`/`fixture-smoke`/`run` 단계 정리
