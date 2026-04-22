# Fixture 작성법

언어: [English](fixtures.md) | 한국어

Fixture는 artifact를 upload하거나 실행하기 전에 guest VM 내부 환경을 준비하는 script입니다. 쉽게 말하면 시험장을 준비하는 단계입니다. Runtime 설치, directory 생성, registry/policy 설정, reference data 생성, setup evidence 기록을 fixture에서 처리합니다.

Fixture는 main product validation을 실행하면 안 됩니다. Product 실행은 `artifact.command` 또는 `product.steps`에 둬야 setup failure와 product failure가 분리됩니다.

## 언제 Fixture를 쓰나

| 필요 | Fixture 사용? | 예시 |
| --- | --- | --- |
| Python artifact 실행 전 Python runtime 보장 | Yes | `demo-python-runtime.ps1` |
| `hello.c` compile 전 C compiler 보장 | Yes | `demo-c-compiler.ps1` |
| Scan 전 registry key나 test file 생성 | Yes | PowerShell setup script |
| 테스트 대상 product upload/run | No | `artifact` 사용 |
| Normalized output pass/fail 확인 | No | `assertions` 사용 |

## Scenario Contract

```yaml
fixtures:
  - id: demo-python-runtime
    type: powershell
    source: validation/fixtures/windows/demo-python-runtime.ps1
    expectedOutput: "C:\\Oslab\\demo-python-runtime.json"
```

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | Yes | Progress log, JUnit testcase name, raw output filename에 쓰이는 stable id |
| `type` | Yes | Fixture runner type. 현재 Windows demo는 `powershell` 사용 |
| `source` | Yes | Guest에 upload하고 실행할 local script |
| `expectedOutput` | No | Fixture 실행 후 setup evidence로 수집할 guest file path |

## PowerShell Fixture 규칙

권장 형태:

```powershell
$ErrorActionPreference = "Stop"

$root = "C:\Oslab"
New-Item -ItemType Directory -Force -Path $root | Out-Null

# 여기에서 guest state를 준비합니다.

$manifest = @{
  schemaVersion = 1
  kind = "fixtureResult"
  ready = $true
  details = @{}
}

$manifest |
  ConvertTo-Json -Depth 10 |
  Set-Content -Encoding UTF8 "$root\my-fixture.json"
```

규칙:

- `$ErrorActionPreference = "Stop"`을 사용해 setup 실패가 fixture failure로 잡히게 합니다.
- `expectedOutput`을 설정했다면 deterministic evidence JSON을 씁니다.
- File을 쓰기 전에 parent directory를 생성합니다.
- Fixture는 idempotent해야 합니다. 이미 tool/state가 있어도 다시 실행 가능해야 합니다.
- Secret을 출력하지 않습니다.
- Product command를 여기에서 실행하지 않습니다.

## Demo Fixture 동작

### Python Runtime Fixture

`validation/fixtures/windows/demo-python-runtime.ps1`:

1. `C:\Oslab`, `C:\Oslab\tools`를 생성합니다.
2. 기존 `C:\Oslab\tools\python\python.exe`, `python.exe`, `py.exe`가 있으면 재사용합니다.
3. Runtime이 없으면 portable Python을 `C:\Oslab\tools\python`에 다운로드합니다.
4. `C:\Oslab\demo-python-runtime.json`을 씁니다.
5. Working Python runtime을 만들지 못하면 `fixture_failure`가 됩니다.

예상 fixture evidence:

```json
{
  "schemaVersion": 1,
  "kind": "demoRuntime",
  "demo": "python-hello",
  "ready": true,
  "runtime": "python",
  "source": "portable",
  "executable": "C:\\Oslab\\tools\\python\\python.exe",
  "version": "Python 3.13.6"
}
```

### C Compiler Fixture

`validation/fixtures/windows/demo-c-compiler.ps1`:

1. `C:\Oslab`, `C:\Oslab\tools`를 생성합니다.
2. 기존 `cl.exe`, `gcc.exe`, `clang.exe`가 있으면 재사용합니다.
3. Compiler가 없으면 TinyCC를 `C:\Oslab\tools\tcc`에 다운로드합니다.
4. `C:\Oslab\demo-c-compiler.json`을 씁니다.
5. Compiler를 찾거나 bootstrap하지 못하면 `fixture_failure`가 됩니다.

예상 fixture evidence:

```json
{
  "schemaVersion": 1,
  "kind": "demoRuntime",
  "demo": "c-hello",
  "ready": true,
  "runtime": "c-compiler",
  "compiler": "tcc",
  "executable": "C:\\Oslab\\tools\\tcc\\tcc.exe"
}
```

## Result Flow

`oslab run` 중 fixture 흐름:

1. Fixture script가 disposable clone에 upload됩니다.
2. 선택된 guest channel로 fixture가 실행됩니다.
3. stdout/stderr와 exit code가 기록됩니다.
4. `expectedOutput`이 있으면 해당 guest file을 `runs/<run-id>/raw/`로 download합니다.
5. Fixture가 실패하면 artifact 실행을 중단하고 run을 `fixture_failure`로 분류합니다.

Demo run 통과 후 예상 file:

```text
runs/<run-id>/
  logs/
    progress.log
  raw/
    fixture-demo-python-runtime.expected-output.json
  reports/
    result.junit.xml
    result.json
    result.html
```

예상 progress log:

```text
[..] fixture.start - Apply scenario fixtures
[OK] fixture.done - Fixture applied
    fixtureId: demo-python-runtime
    exitCode: 0
[OK] fixture.all.done - Scenario fixtures applied
```

## Debugging

Fixture setup이 실패하면 fixture 중심 smoke test를 먼저 실행합니다.

```powershell
uv run oslab fixture-smoke `
  --scenario scenarios/windows/demo-python-hello.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --keep-vm
```

Kept VM 내부를 확인합니다.

```powershell
uv run oslab qga-exec `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --vm-id <kept-vm-id> `
  -- powershell.exe -NoProfile -Command "Get-ChildItem C:\Oslab -Recurse"
```

