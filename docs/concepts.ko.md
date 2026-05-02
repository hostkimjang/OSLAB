# Concepts

언어: [English](concepts.md) | 한국어

`oslab`은 product-neutral한 몇 가지 개념을 중심으로 구성됩니다.

처음에는 이렇게 생각하면 쉽습니다.

```text
가상 머신(VM) 준비
  -> 테스트 전 환경 셋업
  -> 테스트할 파일 업로드
  -> VM 안에서 실행
  -> 결과 파일 수집
  -> 공통 채점 형식으로 변환
  -> 합격/불합격 판단
  -> 사람과 CI가 볼 보고서 작성
```

즉, `oslab`은 “테스트용 VM을 만들고, 시험장을 세팅하고, 시험 대상을 실행하고, 채점표와 보고서를 남기는” 흐름을 자동화합니다.

## Lifecycle Map

| Concept | Input | Role | Output |
| --- | --- | --- | --- |
| Scenario | YAML file | 전체 test contract를 설명 | Run plan |
| Provider | Scenario provider block + config | Disposable VM lifecycle 관리 | VM reference/status |
| Guest channel | Guest mode와 VM reference | Command 실행과 file transfer 수행 | Command/file results |
| Fixture | Fixture script | Guest OS state 준비 | Fixture logs와 optional expected output |
| Artifact | `--artifact-path` | 테스트 대상 product/folder/installer 제공 | Remote artifact path |
| Artifact command | Scenario command template | Upload된 artifact를 VM 안에서 실행 | Guest 내부 raw output file |
| Adapter | Raw output JSON | Product-specific 또는 command output을 canonical data로 변환 | `normalized/*.json` |
| Assertion | Scenario assertions | Normalized data 평가 | Pass/fail results |
| Report | Run result와 assertion results | CI/human/automation output 작성 | JUnit, JSON, HTML, logs |

## Why The Boundaries Exist

각 개념은 일부러 분리되어 있습니다. 실패했을 때 어느 단계가 문제인지 좁히고, 제품별 차이가 core platform을 오염시키지 않게 하기 위해서입니다.

| Concept | 왜 존재하나 | 담당하는 것 | 담당하지 않는 것 |
| --- | --- | --- | --- |
| Scenario | 테스트 실행 방법을 한 파일로 재사용하기 위해 | 어떤 VM에서 무엇을 어떻게 실행할지 선언 | Secret value 보관 |
| Fixture | 테스트 전 VM 상태를 일정하게 만들기 위해 | Runtime 설치, registry/policy/file baseline 준비 | Product 실행 |
| Artifact | 테스트 대상과 환경 준비를 분리하기 위해 | Product folder, installer, script 묶음 | 공통 OS 환경 셋업 |
| Adapter | 제품마다 다른 출력 형식을 공통 형식으로 바꾸기 위해 | Raw JSON -> canonical model 변환 | 합격/불합격 판단 |
| Assertion | 자동으로 통과/실패를 판단하기 위해 | Canonical model 검사 | Raw output 직접 파싱 |
| Report | 결과를 사람/CI/automation이 소비하게 하기 위해 | JUnit, JSON, HTML, logs 위치 제공 | VM 실행 제어 |

## Scenario

무엇을 실행할지 설명하는 YAML file입니다. 쉽게 말해 scenario는 “실행 레시피”입니다. 어떤 VM을 만들고, 어떤 사전 준비를 하고, 어떤 artifact를 올리고, 무엇을 통과 기준으로 볼지 한 장에 적습니다.

- OS family
- provider/template
- guest channel preference
- fixtures
- artifact upload contract
- command 또는 product steps
- output collection
- assertions
- reports
- cleanup policy

Examples:

- `scenarios/windows/demo-powershell-system.example.yaml`
- `scenarios/windows/demo-python-hello.example.yaml`
- `scenarios/windows/demo-c-hello.example.yaml`
- `scenarios/windows/demo-agent-steps.example.yaml`

## Provider

Provider는 VM lifecycle을 관리합니다.

현재 구현:

- Proxmox
- clone/start/stop/destroy
- VM status
- Proxmox/QGA를 통한 guest info

향후 provider는 같은 lifecycle surface를 구현하면 scenario semantics를 바꾸지 않고 추가할 수 있습니다.

## Guest Channel

Guest channel은 VM 내부에서 command를 실행하고 file을 전송하는 interface입니다.

현재 구현:

- Windows용 QEMU Guest Agent

설계된 경로:

- Windows fallback용 WinRM
- Linux용 SSH

## Fixture

Fixture는 artifact가 실행되기 전에 guest state를 준비합니다. 쉽게 말해 “테스트 전 환경 셋업 스크립트”입니다.

Fixture를 artifact와 분리하는 이유는 실패 원인을 나누기 위해서입니다. Python runtime 설치, registry baseline, policy 설정 같은 공통 준비가 실패하면 fixture failure로 보고, 제품 자체 실행이 실패하면 artifact/product failure로 봐야 합니다.

Examples:

- registry/file baseline 생성
- runtime 설치 또는 bootstrap
- expected output data 작성
- template contamination이 없는지 확인

Python/C demo는 disposable clone 내부의 `C:\Oslab\tools` 아래에 portable tool을 bootstrap하기 위해 fixture를 사용합니다. Product 실행은 fixture가 아니라 `artifact.command` 또는 `product.steps`에 두는 것이 좋습니다.

## Artifact

Artifact는 VM에 upload되는 local file 또는 folder입니다. 쉽게 말해 “실제로 시험 볼 대상”입니다. 예를 들어 실행할 프로그램 폴더, 설치 파일, smoke test script 묶음이 artifact입니다.

MVP supported types:

| Type | Behavior |
| --- | --- |
| `folder` | Directory를 upload합니다. 보통 archive로 전송합니다. |
| `installer` | Installer file을 upload하고 `installCommand`를 실행합니다. |

## Command Or Product Steps

간단한 scenario는 artifact command 하나를 사용합니다.

Agent-like product는 순서가 있는 `product.steps`를 사용할 수 있습니다.

```text
install -> register -> status -> scan
```

Core runner는 이 steps를 generic step으로 취급합니다. Product semantics는 scenario file과 plugin에 위치해야 합니다.

Step이 JSON을 출력하면 `captureStdoutJson: true`로 그 객체를 `raw/product-steps.json`에 저장할 수 있습니다. 그 다음 `expectStdoutJson`으로 `ok: true`, `registered: true`, `outputWritten: true` 같은 필수 field를 gate로 걸어 다음 step으로 넘어가기 전에 검증할 수 있습니다.

## Adapter

Adapter는 raw product output을 canonical model로 normalize합니다. 쉽게 말해 제품마다 제각각인 출력 형식을 `oslab`이 공통으로 채점할 수 있는 형태로 바꾸는 변환기입니다.

Adapter는 pass/fail을 판단하지 않습니다. Adapter는 “번역”만 하고, assertion이 번역된 결과를 보고 판단합니다. 이 분리 덕분에 제품 output schema가 바뀌어도 assertion/report 쪽 영향을 줄일 수 있습니다.

Implemented:

| Adapter | Model |
| --- | --- |
| `canonical.command` | command result |
| `canonical.inventory` | inventory result |

제품별 adapter logic은 core runner behavior 밖에 두고, generic getting-started 경로가 아니라 해당 제품 문서에 둡니다.

## Assertion

Assertion은 normalized output을 평가합니다. 쉽게 말해 “합격 기준”입니다. Assertion은 raw output이나 VM 상태를 직접 읽지 않고, adapter가 만든 canonical model만 보고 판단해야 합니다.

Implemented examples:

| Assertion | Meaning |
| --- | --- |
| `command.exitCode` | Command exit code 확인 |
| `command.stdoutContains` | stdout text 확인 |
| `command.stderrContains` | stderr text 확인 |
| `file.exists` | 보고된 file 존재 확인 |
| `file.notExists` | 보고된 file 부재 확인 |
| `directory.exists` | 보고된 directory 존재 확인 |
| `process.exists` | 보고된 process 존재 확인 |
| `service.exists` | 보고된 service 존재 확인 |
| `package.exists` | 보고된 package 존재 확인 |
| `inventory.contains` | Inventory에 matching record가 있는지 확인 |
| `inventory.evidencePresent` | Evidence 존재 확인 |

State assertion은 normalized output metadata에서 읽습니다. 예를 들면 `metadata.files`, `metadata.directories`, `metadata.processes`, `metadata.services`, `metadata.packages`입니다. 실제 guest 상태 관찰과 보고는 artifact command가 담당합니다.

## Report

각 full run은 다음 결과를 만들 수 있습니다.

- `run.json`
- `reports/result.json`
- `reports/result.junit.xml`
- `reports/result.html`
- `logs/progress.log`
- `logs/progress.jsonl`

JUnit은 CI용, HTML은 사람이 보는 용도, JSON은 automation용입니다.

Reports는 결과를 배포하는 층입니다. 반면 `raw/`, `normalized/`, `logs/`, `run.json`은 결과를 설명하는 증거입니다. 실패를 조사할 때는 증거 파일을 보고, CI나 리뷰에 공유할 때는 report를 봅니다.
