# 데모 카탈로그

언어: [English](demos.md) | 한국어

데모는 product-neutral한 작은 예제들입니다. 실제 제품을 연결하기 전에 `oslab`의 개념을 하나씩 익히도록 설계되어 있습니다.

## 어떤 데모를 먼저 실행할까?

| Demo | Scenario | Artifact path | Fixture | 배우는 것 |
| --- | --- | --- | --- | --- |
| PowerShell system | `scenarios/windows/demo-powershell-system.example.yaml` | `validation/artifacts/powershell-system` | No | 의존성이 가장 낮은 command-result demo |
| Python hello | `scenarios/windows/demo-python-hello.example.yaml` | `validation/artifacts/hello-python` | Python runtime bootstrap | Runtime fixture + command assertions |
| C hello | `scenarios/windows/demo-c-hello.example.yaml` | `validation/artifacts/hello-c` | C compiler bootstrap | Toolchain fixture + command assertions |
| Fixture state handoff | `scenarios/windows/demo-fixture-state.example.yaml` | `validation/artifacts/fixture-state-reader` | State file fixture | Fixture가 VM 상태를 만들고 artifact가 읽는 흐름 |
| Agent steps | `scenarios/windows/demo-agent-steps.example.yaml` | `validation/artifacts/demo-agent-cli` | No | Ordered `product.steps`, stdout JSON, inventory output |
| Python unittest | `scenarios/windows/demo-python-unittest.example.yaml` | `validation/artifacts/python-unittest` | Python runtime bootstrap | VM 내부에서 실제 unit test 실행 |
| Python HTTP service | `scenarios/windows/demo-python-http-service.example.yaml` | `validation/artifacts/python-http-service` | Python runtime bootstrap | VM 내부 service lifecycle과 HTTP smoke 검증 |
| C unit test | `scenarios/windows/demo-c-unit.example.yaml` | `validation/artifacts/c-unit` | C compiler bootstrap | Multi-file compile/link/run unit test |
| Intentional assertion failure | `scenarios/windows/demo-intentional-assertion-failure.example.yaml` | `validation/artifacts/hello-python` | Python runtime bootstrap | Assertion failure가 report/JUnit에 표시되는 방식 |

추천 순서:

1. PowerShell system을 먼저 실행합니다. Runtime download가 필요 없습니다.
2. Python 또는 C demo로 fixture bootstrap을 확인합니다.
3. Fixture state handoff로 fixture와 artifact의 역할 분리를 익힙니다.
4. Agent steps로 ordered product workflow를 확인합니다.
5. Python unittest, Python HTTP service, C unit test로 더 실제 코드 실행에 가까운 예제를 확인합니다.
6. Intentional assertion failure는 실패 report를 보고 싶을 때만 실행합니다.

## 공통 실행 패턴

Example scenario를 local scenario로 복사하고 provider block을 수정합니다.

```powershell
Copy-Item scenarios/windows/demo-powershell-system.example.yaml scenarios/windows/demo-powershell-system.local.yaml
Copy-Item scenarios/windows/demo-python-hello.example.yaml scenarios/windows/demo-python-hello.local.yaml
Copy-Item scenarios/windows/demo-c-hello.example.yaml scenarios/windows/demo-c-hello.local.yaml
Copy-Item scenarios/windows/demo-fixture-state.example.yaml scenarios/windows/demo-fixture-state.local.yaml
Copy-Item scenarios/windows/demo-agent-steps.example.yaml scenarios/windows/demo-agent-steps.local.yaml
Copy-Item scenarios/windows/demo-python-unittest.example.yaml scenarios/windows/demo-python-unittest.local.yaml
Copy-Item scenarios/windows/demo-python-http-service.example.yaml scenarios/windows/demo-python-http-service.local.yaml
Copy-Item scenarios/windows/demo-c-unit.example.yaml scenarios/windows/demo-c-unit.local.yaml
Copy-Item scenarios/windows/demo-intentional-assertion-failure.example.yaml scenarios/windows/demo-intentional-assertion-failure.local.yaml
```

각 local copy의 provider block을 수정합니다.

```yaml
provider:
  type: proxmox
  template: windows11-template-qga
  templateVmId: 9101
  vmIdRange:
    start: 9102
    end: 9199
```

그 다음 실행합니다.

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-powershell-system.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/powershell-system
```

Run 이후 확인:

```powershell
uv run oslab inspect-result --run-dir runs\<run-id>
Invoke-Item runs\<run-id>\reports\result.html
```

## 데모 상세

### PowerShell System

가장 작은 passing demo입니다. PowerShell script가 OS/PowerShell metadata를 수집하고, `C:\Oslab\command-result.json`을 쓰고, `canonical.command` assertions로 검증합니다.

예상 stdout marker:

```text
oslab powershell system demo
```

### Fixture State Handoff

Fixture가 왜 필요한지 보여주는 데모입니다. Fixture는 `C:\Oslab\demo-fixture-state.json`을 쓰고, artifact command는 그 파일을 읽어서 command result를 만듭니다.

실행:

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-fixture-state.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/fixture-state-reader
```

예상 evidence:

```text
runs/<run-id>/raw/fixture-demo-state-file.expected-output.json
```

### Agent Steps

Private product 없이 agent-like product 흐름을 보여주는 데모입니다. Artifact는 작은 PowerShell CLI이고 세 명령을 제공합니다.

```text
register -> status -> scan
```

Scenario는 `product.steps`를 사용하고, 각 step stdout을 JSON으로 capture하며, `raw/product-steps.json`을 쓰고, 마지막 scan output을 inventory result로 수집합니다.

실행:

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-agent-steps.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/demo-agent-cli
```

예상 파일:

```text
runs/<run-id>/raw/product-steps.json
runs/<run-id>/raw/actual-output.json
runs/<run-id>/normalized/inventory.json
```

### Python Unittest

Disposable VM 내부에서 실제 Python `unittest` suite를 실행하는 데모입니다. Artifact에는 application code, tests, test runner가 들어 있고, 실행 결과는 canonical command result로 수집됩니다.

실행:

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-python-unittest.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/python-unittest
```

예상 stdout marker:

```text
Ran 4 tests
OK
```

### Python HTTP Service

VM 내부에서 local HTTP service를 시작하고, `/health`와 `/add?left=20&right=22`를 호출해 응답을 검증한 뒤 service를 종료하는 데모입니다.

실행:

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-python-http-service.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/python-http-service
```

예상 stdout marker:

```text
service smoke passed
add_result=42
```

### C Unit Test

작은 multi-file C project를 compile/link하고 test executable을 실행합니다. Hello world보다 실제 build/test job에 더 가깝습니다.

실행:

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-c-unit.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/c-unit
```

예상 stdout marker:

```text
PASS add
c unit tests passed: 5
```

### Intentional Assertion Failure

이 scenario는 의도적으로 실패해야 합니다. Infrastructure와 product execution은 통과했지만 assertion만 실패하는 상황을 보여줍니다.

실패 report를 확인하고 싶을 때만 실행합니다.

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-intentional-assertion-failure.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/hello-python
```

예상 결과:

```text
status: failed
failureClass: assertion_failure
```

JUnit에서는 missing-text assertion이 `<failure>`로 표시되어야 합니다. Infrastructure나 product execution 문제는 `<error>`로 표시됩니다.
