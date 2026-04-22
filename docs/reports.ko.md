# Reports And Results

언어: [English](reports.md) | 한국어

Full `oslab run`은 `runs/<run-id>/` 아래에 안정적인 output directory를 생성합니다.

Report 관련 파일은 두 종류로 나눠서 보면 쉽습니다.

- Evidence: 무슨 일이 있었는지 조사하기 위한 증거입니다. `logs/`, `raw/`, `normalized/`, `run.json`이 여기에 가깝습니다.
- Reports: 사람, CI, automation이 소비하는 최종 결과물입니다. `reports/result.html`, `reports/result.junit.xml`, `reports/result.json`이 여기에 해당합니다.

실패를 조사할 때는 evidence를 보고, 결과를 공유하거나 CI gate로 사용할 때는 reports를 봅니다.

## Layout

```text
runs/<run-id>/
  run.json
  logs/
    progress.log
    progress.jsonl
    product.stdout.log
    product.stderr.log
    product-step-<step-id>.stdout.log
    product-step-<step-id>.stderr.log
  raw/
    actual-output.json
    product-steps.json
    fixture-<fixture-id>.expected-output.json
  normalized/
    command-result.json
    inventory.json
  reports/
    result.json
    result.junit.xml
    result.html
    inventory.analysis.json
```

모든 run이 모든 file을 만들지는 않습니다. 예를 들어 command-result demo는 `normalized/command-result.json`을 만들고, inventory scenario는 `normalized/inventory.json`을 만듭니다.

## 어떤 파일을 먼저 봐야 하나

| Situation | First file/command | Why |
| --- | --- | --- |
| Local run 실패 | `logs/progress.log` | 가장 빠르게 읽을 수 있는 timeline |
| Summary가 필요 | `uv run oslab inspect-result --run-dir runs\<run-id>` | Status, failure class, reports, stdout preview 출력 |
| 사람이 읽을 report 필요 | `reports/result.html` | Review용 static report |
| CI pass/fail 필요 | `reports/result.junit.xml` | Standard test report |
| Adapter/assertion이 이상함 | `raw/actual-output.json` 다음 `normalized/*.json` | Raw collected data와 canonical data 비교 |
| Step-based product 실패 | `raw/product-steps.json`와 `logs/product-step-*.stderr.log` | Step별 result 확인 |

## File Roles

| File or directory | Primary reader | Role |
| --- | --- | --- |
| `run.json` | `inspect-result`, automation | Run status, failure class, path index |
| `logs/progress.log` | Human | Live progress와 triage |
| `logs/progress.jsonl` | Automation/dashboard | Structured progress events |
| `logs/product*.stdout.log` / `stderr.log` | Human/debugger | Guest command output |
| `raw/actual-output.json` | Adapter/debugger | `oslab`이 guest에서 수집한 raw output |
| `normalized/command-result.json` | Assertions/human/debugger | Canonical command result |
| `normalized/inventory.json` | Assertions/analysis | Canonical inventory result |
| `reports/result.junit.xml` | CI test reporter | Gate/pass-fail report |
| `reports/result.json` | Automation | Machine-readable report |
| `reports/result.html` | Human reviewer | Static report |

## Live Logs

Run 진행 상황 보기:

```powershell
Get-Content runs\<run-id>\logs\progress.log -Wait
```

`progress.jsonl`은 같은 event stream을 structured JSON으로 저장합니다.

```json
{"phase":"vm.boot.done","status":"done","message":"VM is running","details":{"vmId":9102}}
```

## Inspect Result

```powershell
uv run oslab inspect-result --run-dir runs\<run-id>
```

Raw `run.json`:

```powershell
uv run oslab inspect-result --run-dir runs\<run-id> --json
```

HTML report 열기:

```powershell
Invoke-Item runs\<run-id>\reports\result.html
```

## JUnit

CI system은 다음 file을 읽으면 됩니다.

```text
runs/<run-id>/reports/result.junit.xml
```

Mapping:

| Testcase | Meaning | Failure type |
| --- | --- | --- |
| `preflight.<check-id>` | Guest readiness | `error` |
| `fixture.<fixture-id>` | Fixture/bootstrap | `error` |
| `artifact.install` | Installer execution | `error` |
| `product.command` | Product/demo command execution | `error` |
| `product.step.<step-id>` | Ordered product step | `error` |
| `assertion.<assertion-id>` | Output mismatch | `failure` |

Infrastructure/execution failure는 JUnit error로, assertion mismatch는 JUnit failure로 표현되어야 합니다.

JUnit 생성은 scenario의 `reports.formats`에 `junit`이 있을 때 `oslab run`과 `artifact-smoke`에서 구현되어 있습니다. 검증 계층과 정확한 command 흐름은 [검증과 JUnit](validation.ko.md)을 참고하세요.

## CI Artifact Pattern

Job이 실패해도 항상 `runs/**`를 publish하세요. 그렇지 않으면 JUnit에는 실패만 남고, 원인 분석에 필요한 logs, raw output, normalized output, HTML report가 사라질 수 있습니다.

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

같은 Proxmox lab을 여러 job이 동시에 사용할 수 있다면 CI concurrency control을 쓰거나 job/runner별로 별도 VMID range를 예약하세요.
