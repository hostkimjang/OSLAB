# Scenario Authoring

언어: [English](scenarios.md) | 한국어

이 문서는 현재 scenario YAML contract를 실용적인 관점에서 설명합니다.

## 작성 순서

새 scenario를 만들 때는 보통 이 순서로 작성합니다.

1. Target OS/template과 VMID range를 정합니다.
2. Guest channel mode를 정합니다. 현재 Windows demo는 QEMU Guest Agent를 사용합니다.
3. Guest setup prerequisite만 fixture에 넣습니다.
4. Artifact type, destination, command를 정의합니다.
5. Command가 `{OutputPath}`에 machine-readable output을 쓰게 합니다.
6. `outputs.actual.path`를 같은 guest path로 맞춥니다.
7. `canonical.command` 같은 adapter를 선택합니다.
8. Normalized output에 대한 assertions를 추가합니다.
9. Reports를 켭니다.
10. Debugging이 아니면 cleanup을 켜둡니다.

가장 흔한 작성 실수는 `artifact.command`와 `outputs.actual.path` 불일치입니다. Command는 성공했지만 `oslab`이 수집하지 않는 위치에 output을 쓰면 run은 실패합니다.

## Minimal Shape

```yaml
schemaVersion: 1
id: demo.python-hello.windows
name: Generic Python hello world Windows demo
os:
  family: windows
  version: "11"
provider:
  type: proxmox
  template: windows11-template-qga
  templateVmId: 9101
  vmIdRange:
    start: 9102
    end: 9199
guest:
  mode: auto
fixtures: []
artifact:
  type: folder
  pathParam: artifactPath
  destination: "C:\\Oslab\\artifact"
  transfer: archive
  command:
    shell: powershell
    template: '& "{ArtifactDir}\run.ps1" -OutputPath "{OutputPath}"'
outputs:
  actual:
    path: "C:\\Oslab\\command-result.json"
    adapter: canonical.command
assertions:
  - type: command.exitCode
    id: exit-zero
    exitCode: 0
reports:
  formats:
    - junit
    - json
    - html
cleanup:
  destroyVm: true
  keepVmOnFailure: false
```

## Top-Level Fields

| Field | Required | Description |
| --- | --- | --- |
| `schemaVersion` | Yes | Scenario schema version |
| `id` | Yes | Stable scenario id |
| `name` | Recommended | Human-readable name |
| `os` | Yes | OS family/version |
| `provider` | Yes | Provider type/template/VMID range |
| `guest` | Yes | Guest command strategy |
| `fixtures` | Optional | Guest setup scripts |
| `artifact` | Optional | Artifact upload and command contract |
| `product.steps` | Optional | Agent-like product를 위한 ordered command steps |
| `outputs` | Optional | Remote output path and adapter |
| `assertions` | Yes | Built-in/plugin assertions |
| `reports` | Optional | Report formats |
| `cleanup` | Optional | VM cleanup behavior |

## Field Responsibilities

| Field | Run에서의 역할 | 흔한 실수 |
| --- | --- | --- |
| `provider` | Disposable clone을 만들 template과 VMID range 선택 | Stopped template이 아니라 normal VM을 가리킴 |
| `guest` | `oslab`이 VM과 통신하는 방식 선택 | QGA/WinRM/SSH 준비 없이 `auto`만 설정 |
| `fixtures` | Artifact 실행 전 guest state 준비 | Product 실행을 fixture에 넣음 |
| `artifact` | 어떤 local file/folder를 upload하고 어떻게 실행할지 정의 | `pathParam: artifactPath` 누락 |
| `artifact.installCommand` | Installer artifact의 설치/setup command | Install validation과 product smoke validation을 한 command에 섞음 |
| `artifact.command` | Upload/install 이후 실행되는 main command | Expected output file을 쓰지 않음 |
| `outputs.actual.path` | Guest에서 수집할 remote output path | Product가 다른 위치에 output 작성 |
| `outputs.actual.adapter` | Raw output을 assertion input으로 normalize | Raw output shape에 바로 assertion하려고 함 |
| `assertions` | Pass/fail rule 정의 | Adapter가 보존하지 않는 text를 검사 |
| `reports` | Output format 선택 | `junit`을 켜지 않고 CI JUnit을 기대 |
| `cleanup` | VM 삭제/유지 정책 | Failed VM을 남긴 뒤 VMID range 확인을 잊음 |

## Fixture Example

Fixture는 artifact command 전에 실행됩니다. Guest setup에 사용하고, main product validation을 fixture에 넣지 않습니다.

```yaml
fixtures:
  - id: demo-python-runtime
    type: powershell
    source: validation/fixtures/windows/demo-python-runtime.ps1
    expectedOutput: "C:\\Oslab\\demo-python-runtime.json"
```

| Field | Meaning |
| --- | --- |
| `id` | Logs와 reports에 남는 stable fixture id |
| `type` | Fixture runner type. 현재 Windows demo는 `powershell` 사용 |
| `source` | Guest에 upload할 local fixture script |
| `expectedOutput` | Optional guest path. Fixture evidence로 수집됨 |

Fixture가 실패하면 run은 `fixture_failure`로 멈추는 것이 맞습니다. Setup이 성공한 뒤 artifact command가 실패하면 product/artifact execution failure로 별도 분류되어야 합니다.

Fixture 전체 작성 규칙, manifest 예시, debugging command는 [Fixture 작성법](fixtures.ko.md)을 참고하세요.

## Command Template Tokens

| Token | Meaning |
| --- | --- |
| `{ArtifactDir}` | Remote artifact directory |
| `{InstallerPath}` | Remote installer path |
| `{OutputPath}` | Remote primary output path |
| `{AssetName}` | Product steps에서 사용할 generated/default asset name |

Unknown token은 guest execution 전에 command template rendering 단계에서 거부됩니다. `validate-scenario`는 schema shape를 확인하지만 모든 command token의 full dry run은 아닙니다.

## Generic Demo Scenarios

| Scenario | Purpose |
| --- | --- |
| `scenarios/windows/demo-powershell-system.example.yaml` | 최소 PowerShell command-result demo |
| `scenarios/windows/demo-python-hello.example.yaml` | Python을 bootstrap하고 `hello.py` 실행 |
| `scenarios/windows/demo-c-hello.example.yaml` | TinyCC를 bootstrap하고 `hello.c` compile/run |
| `scenarios/windows/demo-fixture-state.example.yaml` | Fixture가 VM state를 쓰고 artifact가 읽는 demo |
| `scenarios/windows/demo-agent-steps.example.yaml` | Ordered product steps, stdout JSON, inventory output demo |
| `scenarios/windows/demo-python-unittest.example.yaml` | VM 내부 Python unit test 실행 demo |
| `scenarios/windows/demo-python-http-service.example.yaml` | Python local HTTP service smoke test demo |
| `scenarios/windows/demo-c-unit.example.yaml` | Multi-file C compile/link/unit-test demo |
| `scenarios/windows/demo-intentional-assertion-failure.example.yaml` | Report/JUnit 학습용 intentional assertion failure |
| `scenarios/windows/fake-artifact-smoke.example.yaml` | Fake inventory-producing folder artifact |
| `scenarios/windows/fake-installer-smoke.example.yaml` | Fake installer 실행 후 product command |
| `scenarios/linux/generic-smoke.example.yaml` | Linux schema/design example |

## Minimal Custom Artifact Examples

Folder artifact:

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
```

Installer artifact:

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

두 경우 모두 command는 `outputs.actual.path`에 machine-readable output을 써야 합니다. `canonical.command`를 쓰는 경우 `commandResult` JSON object를 작성합니다.

## Artifact Command Output Contract

`canonical.command`를 쓰는 경우 remote output file은 다음 형태를 권장합니다.

```json
{
  "schemaVersion": 1,
  "kind": "commandResult",
  "command": "python hello.py",
  "exitCode": 0,
  "stdout": "hello from python\n",
  "stderr": "",
  "metadata": {
    "runtime": "python"
  }
}
```

Required fields:

| Field | Meaning |
| --- | --- |
| `schemaVersion` | Output schema version |
| `kind` | `canonical.command`에서는 `commandResult` |
| `command` | 사람이 읽는 command label |
| `exitCode` | Process exit code |
| `stdout` | Captured stdout text |
| `stderr` | Captured stderr text |
| `metadata` | Runtime/compiler/version/path 같은 optional object |

Artifact command가 console stdout/stderr도 출력할 수는 있지만, assertion은 수집된 JSON file을 기준으로 동작합니다. Console 출력만으로는 `canonical.command` 검증에 충분하지 않습니다.

Minimal PowerShell writer:

```powershell
param(
  [Parameter(Mandatory = $true)]
  [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$stdout = "hello from my artifact"
$result = @{
  schemaVersion = 1
  kind = "commandResult"
  command = "run-smoke"
  exitCode = 0
  stdout = "$stdout`n"
  stderr = ""
  metadata = @{}
}

$result |
  ConvertTo-Json -Depth 10 |
  Set-Content -Encoding UTF8 $OutputPath
```

## Expected Run Flow

Folder artifact scenario가 통과하면 보통 다음 lifecycle을 따릅니다.

```text
validate scenario
provider config/connectivity/resource preflight
allocate VMID
create ephemeral clone
start VM
wait for guest channel
run guest preflight
run fixtures
prepare artifact directory
upload artifact archive
expand artifact in guest
run artifact command
collect outputs.actual.path
normalize output with adapter
evaluate assertions
write reports
destroy VM clone
```

예상 progress marker:

```text
[OK] provider.preflight.done - Proxmox resource preflight passed
[OK] vm.clone.done - Ephemeral VM clone created
[OK] guest.ready.done - QEMU Guest Agent is ready
[OK] preflight.done - Guest preflight passed
[OK] fixture.all.done - Scenario fixtures applied
[OK] artifact.upload.done - Artifact folder uploaded
[OK] product.command.done - Product command completed
[OK] output.normalize.done - Product output normalized
[OK] assertions.done - Assertions passed
[OK] run.done - Run completed
    status: passed
    failureClass: <none>
```

예상 run files:

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
    fixture-<id>.expected-output.json
  normalized/
    command-result.json
  reports/
    result.junit.xml
    result.json
    result.html
```

## Product-Specific Scenarios

Product-specific scenario는 generic scenario authoring 경로가 아니라 product-owned docs에 둡니다. Generic docs는 특정 private product workflow가 아니라 platform contract를 설명해야 합니다.
