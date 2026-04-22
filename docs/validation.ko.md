# 검증과 JUnit

언어: [English](validation.md) | 한국어

`oslab`에서 검증은 명령 하나가 아닙니다. 실패 원인을 가장 싼 단계에서 멈춰서 확인할 수 있도록 여러 층으로 나뉘어 있습니다.

짧게 답하면: JUnit은 구현되어 있습니다. Full `oslab run`과 `artifact-smoke`는 scenario에 `reports.formats: [junit, ...]`이 있을 때 `runs/<run-id>/reports/result.junit.xml`을 씁니다. CI는 이 XML을 읽습니다. `oslab`에 `junit`이라는 별도 실행 명령이 있는 구조는 아닙니다.

## 검증 계층

새 scenario를 도입할 때는 아래 순서로 확인하면 좋습니다. 각 단계는 full VM run을 하기 전에 더 작은 범위의 문제를 먼저 잡기 위해 존재합니다.

| 계층 | 명령 | VM 생성 | 무엇을 확인하나 | 주요 증거 |
| --- | --- | --- | --- | --- |
| 1. Scenario 형태 | `validate-scenario` | No | YAML schema, 필수 field, 허용 enum 값 | Console result |
| 2. Provider config | `preflight --provider-config-check` | No | Config/env secret이 provider client로 resolve되는지 | Console result |
| 3. Provider API | `preflight --provider-connectivity-check` | No | Proxmox API/token/network 연결 | Console result |
| 4. Provider resources | `preflight --provider-resource-check` | No | Node, template VM, VMID range 사용 가능 여부 | Console result |
| 5. Clone lifecycle | `clone-smoke` | Yes | Proxmox clone/destroy 자체가 되는지 | Console result |
| 6. Boot와 guest readiness | `boot-smoke` | Yes | Clone boot와 QEMU Guest Agent readiness | Console result |
| 7. Guest baseline | `guest-preflight` | Yes | PowerShell/admin/file roundtrip checks | Console result |
| 8. Fixture 단독 검증 | `fixture-smoke` | Yes | Artifact 전 setup script 실행과 output 수집 | Fixture logs/output |
| 9. Artifact 단독 검증 | `artifact-smoke` | Yes | Artifact upload/install/command/output collection | Run layout and reports |
| 10. Full integration | `run` | Yes | End-to-end scenario, normalization, assertions, reports, cleanup | `runs/<run-id>/` |
| 11. Local result checks | `normalize-output`, `assert-result`, `analyze-inventory` | No | Adapter/assertion/analysis logic | Local JSON output |
| 12. Result inspection | `inspect-result` | No | 완료된 run을 사람이 읽기 좋게 요약 | Console summary |

새 테스트의 일반적인 흐름:

```powershell
uv run oslab validate-scenario --scenario scenarios/windows/demo-python-hello.local.yaml
uv run oslab preflight --scenario scenarios/windows/demo-python-hello.local.yaml --config config/oslab.local.yaml --env-file config/oslab.local.env --provider-resource-check
uv run oslab guest-preflight --scenario scenarios/windows/demo-python-hello.local.yaml --config config/oslab.local.yaml --env-file config/oslab.local.env
uv run oslab fixture-smoke --scenario scenarios/windows/demo-python-hello.local.yaml --config config/oslab.local.yaml --env-file config/oslab.local.env
uv run oslab run --scenario scenarios/windows/demo-python-hello.local.yaml --config config/oslab.local.yaml --env-file config/oslab.local.env --artifact-path validation/artifacts/hello-python
uv run oslab inspect-result --run-dir runs\<run-id>
```

## 검증이라는 말의 의미

`oslab`은 검증을 네 가지 의미로 분리합니다.

| 의미 | 어디서 일어나나 | 예시 |
| --- | --- | --- |
| Static contract validation | Lab 접근 전 | `validate-scenario`가 unsupported `guest.mode`를 거부 |
| Infrastructure validation | Product 실행 전 | `preflight`, `clone-smoke`, `boot-smoke`, `guest-preflight` |
| Product behavior validation | Disposable VM 내부 | `artifact.command`, `product.steps`, collected output |
| Result validation | Output collection 이후 | Adapter normalization과 assertions |

이 분리는 의도적인 설계입니다. Fixture가 실패하면 `fixture_failure`여야 하고, product command가 non-zero로 끝나면 `product_execution_failure`여야 합니다. Command는 성공했지만 결과가 기대와 다르면 `assertion_failure`여야 합니다.

## JUnit 구현 상태

JUnit XML은 구현되어 있습니다.

| 항목 | 상태 |
| --- | --- |
| JUnit writer | `src/oslab/reports/junit.py`에 구현 |
| Full run output | `runs/<run-id>/reports/result.junit.xml`로 구현 |
| `artifact-smoke` reports | 같은 artifact validation report writer를 통해 구현 |
| Unicode details | 한글 stderr/details가 읽히도록 unit test로 보호 |
| CI workflow file | 문서 패턴은 있음. 실제 provider-specific CI workflow는 lab마다 별도 작성 필요 |

JUnit은 scenario가 요청할 때만 생성됩니다.

```yaml
reports:
  formats:
    - junit
    - json
    - html
```

`reports.formats`를 생략하면 scenario model은 기본적으로 JSON만 사용합니다. CI에서 JUnit을 기대한다면 `junit`을 명시하세요.

## JUnit Mapping

`oslab`은 scenario 하나를 하나의 test suite로 쓰고, run phase를 testcase로 나눕니다.

| Testcase name | Source | 실패 시 JUnit status |
| --- | --- | --- |
| `preflight.<check-id>` | Guest readiness checks | `error` |
| `fixture.<fixture-id>` | Fixture script execution | `error` |
| `artifact.install` | Installer artifact install command | `error` |
| `product.command` | Main artifact command | `error` |
| `product.step.<step-id>` | Ordered product step | `error` |
| `assertion.<assertion-id>` | Assertion evaluation | `failure` |

CI에서 이 구분이 중요합니다.

- `error`는 infrastructure, setup, install, product execution 문제로 테스트가 정상적으로 수행되지 못했다는 뜻입니다.
- `failure`는 실행은 되었지만 관측 결과가 기대 assertion과 다르다는 뜻입니다.

## 생성되는 파일

`junit`, `json`, `html`이 켜진 full run은 보통 다음 layout을 만듭니다.

```text
runs/<run-id>/
  run.json
  logs/
    progress.log
    progress.jsonl
    product.stdout.log
    product.stderr.log
  raw/
    actual-output.json
    fixture-<fixture-id>.expected-output.json
  normalized/
    command-result.json
  reports/
    result.json
    result.junit.xml
    result.html
```

파일은 이렇게 함께 봅니다.

| 필요 | 볼 파일 |
| --- | --- |
| CI pass/fail | `reports/result.junit.xml` |
| 사람이 읽을 report | `reports/result.html` |
| Automation | `reports/result.json` 또는 `run.json` |
| Debug timeline | `logs/progress.log` |
| Raw product evidence | `raw/actual-output.json` |
| Assertion input | `normalized/*.json` |

## CI 사용 방식

CI는 `oslab run`을 실행하고, 실패해도 항상 `runs/**`를 artifact로 보존하고, JUnit XML을 test report로 publish하는 형태가 좋습니다.

GitHub Actions pattern:

```yaml
- name: Run oslab demo
  run: >
    uv run oslab run
    --scenario scenarios/windows/demo-python-hello.local.yaml
    --config config/oslab.local.yaml
    --env-file config/oslab.local.env
    --artifact-path validation/artifacts/hello-python

- name: Upload oslab run artifacts
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: oslab-runs
    path: runs/**
```

GitLab CI pattern:

```yaml
artifacts:
  when: always
  paths:
    - runs/
  reports:
    junit: runs/**/reports/result.junit.xml
```

## VM 없이 결과 로직 검증

VM run은 성공했는데 adapter나 assertion만 조정해야 할 때는 로컬 명령으로 확인할 수 있습니다.

Raw output normalize:

```powershell
uv run oslab normalize-output `
  --scenario scenarios/windows/demo-python-hello.example.yaml `
  --input-json validation/raw/command-result.example.json `
  --output-json runs/local-normalized.json
```

Scenario assertions 평가:

```powershell
uv run oslab assert-result `
  --scenario scenarios/windows/demo-python-hello.example.yaml `
  --actual-json runs\<run-id>\raw\actual-output.json
```

Canonical inventory 분석:

```powershell
uv run oslab analyze-inventory `
  --inventory-json runs\<run-id>\normalized\inventory.json `
  --output-json runs\<run-id>\reports\inventory.analysis.json
```

이 명령들은 VM/lab 문제가 아니라 adapter, normalized shape, assertion을 조정할 때 유용합니다.

## 아직 Generic Validation Feature가 아닌 것

아래 항목은 generic core에 넣기보다 product나 lab 쪽 책임으로 두는 것이 맞습니다.

| 영역 | 현재 위치 |
| --- | --- |
| Product-specific login/register flow | Scenario `product.steps`, artifact scripts, product-owned docs |
| Product-specific inventory semantics | 해당 product가 소유한 adapter/assertion |
| CI runner provisioning | 문서 패턴은 제공. Runner/network/secret 구성은 lab마다 다름 |
| Linux SSH execution | Scenario model은 있음. 구현은 아직 완료 전 |

Generic core는 VM lifecycle, guest execution, fixture execution, artifact transfer, output collection, normalization hook, assertion, report를 담당합니다.
