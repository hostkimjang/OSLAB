# Adoption Guide

언어: [English](adoption-guide.md) | 한국어

이 문서는 demo 실행을 넘어서, 자신의 제품에 `oslab`을 도입하려는 개발자를 위한 가이드입니다.

가장 중요한 원칙은 “환경 준비”와 “제품 실행”을 섞지 않는 것입니다. VM 안을 테스트 가능한 상태로 만드는 작업은 fixture에 두고, 실제 제품을 실행해 신호를 얻는 작업은 artifact command 또는 product steps에 둡니다.

## 무엇을 만들어야 하나

첫 product smoke test에는 가능한 작은 세트로 시작하세요.

| File or thing | Role | Example |
| --- | --- | --- |
| Scenario YAML | OS/template/state와 artifact 실행 방식을 정의 | `scenarios/windows/my-product.local.yaml` |
| Local config | `oslab`이 Proxmox lab을 찾는 방법 | `config/oslab.local.yaml` |
| Env file 또는 CI secrets | Proxmox token secret 제공 | `config/oslab.local.env` |
| Fixture, optional | Artifact 실행 전 guest state 준비 | `validation/fixtures/windows/my-runtime.ps1` |
| Artifact | 테스트 대상 folder 또는 installer | `C:\builds\my-product` 또는 `MyInstaller.exe` |
| Artifact command | VM 내부에서 실행되는 command | `run-smoke.ps1 -OutputPath "{OutputPath}"` |
| Output JSON | Guest 안에 작성되는 machine-readable result | `C:\Oslab\command-result.json` |
| Assertions | Normalized output에 대한 pass/fail rule | `command.exitCode`, `command.stdoutContains` |

처음에는 folder artifact와 `canonical.command`로 시작하는 것이 좋습니다. 가장 작은 smoke test가 안정된 뒤 installer flow, product steps, custom adapter를 추가하세요.

## 처음부터 만들 것 / 만들지 말 것

| 구분 | 처음부터 만들 것 | 처음에는 만들지 말 것 |
| --- | --- | --- |
| Scenario | Demo scenario를 복사한 local scenario | OS별로 완전히 다른 구조의 scenario 여러 개 |
| Fixture | Runtime, registry, policy 등 test prerequisite만 준비 | Product 실행, scan 실행, login flow 검증 |
| Artifact | 실제 build output 또는 smoke script folder | Lab 설정이나 secret을 포함한 artifact |
| Adapter | 먼저 `canonical.command` 사용 | 처음부터 custom adapter 설계 |
| Assertion | `exitCode=0`, stdout contains 같은 단순 기준 | 복잡한 inventory/plugin assertion |
| Reports | JUnit/JSON/HTML 기본 format | 별도 dashboard |

이렇게 시작하면 실패 원인이 명확합니다. Fixture가 실패하면 VM 환경 준비 문제이고, artifact command가 실패하면 제품 실행 문제이며, assertion이 실패하면 결과가 기대와 다르다는 뜻입니다.

## Fixture vs Artifact

Fixture는 “시험장 준비”입니다. VM 안에서 테스트 전에 필요한 조건을 만듭니다.

Artifact는 “시험 대상”입니다. 실제로 설치하거나 실행해서 제품 동작을 확인할 파일입니다.

| 질문 | Fixture | Artifact |
| --- | --- | --- |
| 언제 실행되나 | Artifact upload/execution 전 | Fixture 이후 |
| 무엇을 담나 | OS 상태 준비, runtime, policy, baseline | 제품 파일, installer, smoke script |
| 실패하면 의미 | 환경 준비 실패 | 제품 설치/실행 실패 |
| 예시 | Python bootstrap, registry key 생성 | `my-product.exe`, `setup.exe`, `run-smoke.ps1` |

Product 실행을 fixture에 넣으면 실패가 “환경 문제”인지 “제품 문제”인지 흐려집니다. 그래서 product signal은 artifact command 또는 product steps에 두는 것이 좋습니다.

## Adapter vs Assertion

Adapter는 번역기입니다. 제품마다 제각각인 raw output을 `oslab`이 공통으로 이해하는 canonical model로 바꿉니다.

Assertion은 채점 기준입니다. Adapter가 만든 canonical model만 보고 통과/실패를 판단합니다.

```text
raw product output
  -> adapter
  -> canonical result
  -> assertion
  -> pass/fail
```

이 분리 덕분에 제품 output 형식이 바뀌어도 adapter만 수정하고, `exitCode=0`, `stdout contains ...` 같은 assertion은 그대로 둘 수 있습니다.

## 권장 도입 흐름

| Phase | Goal | Command |
| --- | --- | --- |
| 1. Demo scenario 복사 | 안전하게 수정할 local scenario 생성 | `Copy-Item scenarios/windows/demo-python-hello.example.yaml scenarios/windows/my-product.local.yaml` |
| 2. Lab 연결 | Template VMID, VMID range, Proxmox node 설정 | `provider` block과 `config/oslab.local.yaml` 수정 |
| 3. YAML 검증 | Schema mistake를 먼저 잡기 | `uv run oslab validate-scenario --scenario scenarios/windows/my-product.local.yaml` |
| 4. Provider readiness 확인 | Config, token, node, template, VMID range 확인 | `uv run oslab preflight ... --provider-resource-check` |
| 5. Artifact 연결 | Build output을 `--artifact-path`로 전달 | `uv run oslab run ... --artifact-path <path>` |
| 6. Result 확인 | stdout, reports, normalized JSON 확인 | `uv run oslab inspect-result --run-dir runs\<run-id>` |
| 7. CI로 승격 | `runs/**` publish, JUnit 읽기 | `runs/<run-id>/reports/result.junit.xml` |

## Folder Artifact Pattern

Product가 folder 상태로 테스트 가능할 때 사용합니다.

Local artifact shape:

```text
my-artifact/
  run-smoke.ps1
  my-product.exe
  supporting-files/
```

Scenario shape:

```yaml
artifact:
  type: folder
  pathParam: artifactPath
  destination: "C:\\Oslab\\artifact"
  transfer: archive
  command:
    shell: powershell
    template: '& "{ArtifactDir}\run-smoke.ps1" -OutputPath "{OutputPath}"'
outputs:
  actual:
    path: "C:\\Oslab\\command-result.json"
    adapter: canonical.command
assertions:
  - type: command.exitCode
    id: exit-zero
    exitCode: 0
```

Script는 `{OutputPath}`에 다음 형태의 result를 써야 합니다.

```json
{
  "schemaVersion": 1,
  "kind": "commandResult",
  "command": "my-product.exe --smoke",
  "exitCode": 0,
  "stdout": "smoke passed\r\n",
  "stderr": "",
  "metadata": {}
}
```

## Installer Artifact Pattern

설치 자체도 검증해야 할 때 사용합니다.

```yaml
artifact:
  type: installer
  pathParam: artifactPath
  destination: "C:\\Oslab\\installer"
  installCommand:
    shell: powershell
    template: '& "{InstallerPath}" -InstallDir "C:\\Oslab\\installed"'
  command:
    shell: powershell
    template: '& "C:\\Oslab\\installed\\run-smoke.ps1" -OutputPath "{OutputPath}"'
outputs:
  actual:
    path: "C:\\Oslab\\command-result.json"
    adapter: canonical.command
```

`installCommand`는 setup/install 동작을 검증합니다. `command`는 설치된 product의 실제 동작을 검증합니다.

## Fixture Pattern

Fixture는 artifact upload/execution 전에 guest OS state를 준비합니다.

Fixture에 적합한 작업:

- runtime/toolchain bootstrap
- registry baseline setup
- test account 또는 policy setup
- expected inventory/result file 생성
- template contamination check

Product 실행은 fixture에 넣지 않는 것이 좋습니다. Product 실행은 `artifact.command` 또는 `product.steps`에 두어야 failure classification과 report가 정확해집니다.

## Fast-Fail Checks And Smoke Commands

`preflight`와 `*-smoke` command는 제품을 검증하려는 최종 명령이 아닙니다. 비싼 full run을 돌리기 전에 고장 위치를 좁히기 위한 진단 도구입니다.

| Command | 의도 |
| --- | --- |
| `preflight` | VM을 만들기 전에 config/token/node/template/VMID range 문제를 먼저 잡음 |
| `clone-smoke` | Proxmox clone/destroy 자체가 되는지 확인 |
| `boot-smoke` | Clone이 boot되고 QEMU Guest Agent가 준비되는지 확인 |
| `guest-preflight` | Guest 내부 PowerShell/admin/file roundtrip 같은 기본 조건 확인 |
| `fixture-smoke` | Fixture upload/execution/output collection만 따로 확인 |
| `artifact-smoke` | Artifact upload/install/command/output collection만 따로 확인 |

Full `oslab run`이 실패했을 때 바로 코드를 고치기보다, 실패 단계에 맞는 smoke command로 경계를 좁히는 편이 빠릅니다.

## Failure Triage

첫 run이 실패하면 다음 순서로 확인하세요.

| Order | What to check | Why |
| --- | --- | --- |
| 1 | `logs/progress.log` | 가장 빠르게 읽을 수 있는 timeline |
| 2 | `uv run oslab inspect-result --run-dir runs\<run-id>` | Summary, failure class, command output preview |
| 3 | `reports/result.html` | 사람이 읽기 좋은 report |
| 4 | `logs/product*.stderr.log` | Guest command error detail |
| 5 | `raw/actual-output.json` | Product가 expected raw file을 썼는지 확인 |
| 6 | `normalized/*.json` | Adapter가 assertion input을 만들었는지 확인 |
| 7 | `reports/result.junit.xml` | CI-facing failure classification |

VM-level debugging이 필요하면 `--keep-vm`으로 재실행하고 `qga-exec`로 guest 내부를 확인한 뒤, 수동 cleanup 후 `preflight --provider-resource-check`로 `usedInRange`를 확인하세요.

## CI Contract

CI는 보통 다음 흐름을 사용합니다.

1. `uv run oslab run ...` 실행
2. `runs/**`를 job artifact로 upload
3. `runs/<run-id>/reports/result.junit.xml`를 test report로 publish
4. 실패 분석을 위해 `reports/result.html`, `run.json`, logs, raw, normalized files 보존

`runs/`, local config, real secrets는 commit하지 않습니다.
