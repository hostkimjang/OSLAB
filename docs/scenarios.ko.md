# 시나리오 작성

언어: [English](scenarios.md) | 한국어

이 문서는 현재 scenario YAML contract를 실용적인 관점에서 설명합니다.

## 작성 순서

새 scenario를 만들 때는 보통 이 순서로 작성합니다.

1. Target OS/template과 VMID range를 정합니다.
2. Guest channel mode를 정합니다. 현재 Windows와 Linux 실행은 QEMU Guest Agent를 사용합니다.
3. Guest setup prerequisite만 fixture에 넣습니다.
4. Artifact type, destination, command를 정의합니다.
5. Command가 `{OutputPath}`에 machine-readable output을 쓰게 합니다.
6. `outputs.actual.path`를 같은 guest path로 맞춥니다.
7. `canonical.command` 같은 adapter를 선택합니다.
8. Normalized output에 대한 assertions를 추가합니다.
9. Reports를 켭니다.
10. Debugging이 아니면 cleanup을 켜둡니다.

가장 흔한 작성 실수는 `artifact.command`와 `outputs.actual.path` 불일치입니다. Command는 성공했지만 `oslab`이 수집하지 않는 위치에 output을 쓰면 run은 실패합니다.

<a id="minimal-shape"></a>

## 최소 구성

```yaml
schemaVersion: 1
id: demo.python-hello.windows
name: Generic Python hello world Windows demo
os:
  family: windows
  version: "11"
provider:
  type: proxmox
  template: windows11-template-qga-9200
  templateVmId: 9200
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

<a id="top-level-fields"></a>

## 최상위 필드

| Field | Required | Description |
| --- | --- | --- |
| `schemaVersion` | Yes | Scenario schema version |
| `id` | Yes | Stable scenario id |
| `name` | Recommended | Human-readable name |
| `os` | Yes | OS family/version |
| `provider` | Yes | Provider type/template/VMID range, 선택 사항인 clone 설정 |
| `guest` | Yes | Guest command strategy, 선택 사항인 screen 설정 |
| `fixtures` | Optional | Guest setup scripts |
| `artifact` | Optional | Artifact upload and command contract |
| `product.steps` | Optional | Agent-like product를 위한 ordered command steps |
| `outputs` | Optional | Remote output path and adapter |
| `assertions` | Yes | Built-in/plugin assertions |
| `reports` | Optional | Report formats |
| `cleanup` | Optional | VM cleanup behavior |

<a id="field-responsibilities"></a>

## 필드별 역할

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

<a id="clone-settings"></a>

## 복제본 설정

`provider.clone`은 Proxmox가 일회용 복제본을 만든 직후 그 복제본의 설정을 바꿉니다. 템플릿은 바뀌지 않습니다.

```yaml
provider:
  clone:
    display: virtio
    network: disconnected
```

| Field | 값 | 복제본에 적용되는 내용 |
| --- | --- | --- |
| `display` | `std`, `virtio` | 디스플레이 장치(Proxmox `vga`)를 바꿉니다. 템플릿이 직렬 디스플레이(`vga: serial0`)인데 VNC 콘솔을 보거나 녹화하려 할 때 사용합니다. |
| `network` | `disconnected` | 모든 네트워크 장치에 `link_down=1`을 설정합니다. 템플릿의 cloud-init 설정 때문에 모든 복제본이 `192.168.0.10/24` 같은 고정 주소를 똑같이 받게 될 때 사용합니다. QEMU Guest Agent는 네트워크가 필요 없습니다. |

필드를 생략하면 템플릿 값을 그대로 씁니다. 부팅 중 네트워크를 기다리는 게스트는 `network: disconnected`일 때 늦게 시작합니다. Ubuntu cloud image는 `systemd-networkd-wait-online`이 약 2분 뒤 시간 초과로 끝난 다음에야 QEMU Guest Agent가 응답합니다.

<a id="guest-screen"></a>

## 게스트 화면 설정

`guest.screen`은 실행 중 VM 화면에 무엇을 보여 줄지 정합니다.

| Field | 의미 |
| --- | --- |
| `showCommands` | 명령과 출력을 VM 화면에 보여 줍니다. 종료 코드와 출력은 게스트 채널로 수집합니다. |
| `signIn` | Windows 전용. 명령을 실행하기 전에 Windows 데스크톱에 로그인합니다. Windows에서 `showCommands: true`를 쓰려면 `signIn: true`가 필요합니다. |

Linux 시나리오에서는 `signIn`을 쓸 수 없습니다. Linux 콘솔 표시 방식은 [Linux 게스트](#linux-guests)를 참고하세요.

Windows 로그인과 콘솔 창은 [Windows 데스크톱 세션](#windows-desktop-session)에서 설명합니다.

<a id="fixture-example"></a>

## Fixture 예시

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
| `type` | Fixture runner type. Windows 게스트는 `powershell`, Linux 게스트는 `shell` |
| `source` | Guest에 upload할 local fixture script |
| `expectedOutput` | Optional guest path. Fixture evidence로 수집됨 |

Fixture가 실패하면 run은 `fixture_failure`로 멈추는 것이 맞습니다. Setup이 성공한 뒤 artifact command가 실패하면 product/artifact execution failure로 별도 분류되어야 합니다.

Fixture 전체 작성 규칙, manifest 예시, debugging command는 [Fixture 작성법](fixtures.ko.md)을 참고하세요.

<a id="command-template-tokens"></a>

## 명령 템플릿 토큰

| Token | Meaning |
| --- | --- |
| `{ArtifactDir}` | Remote artifact directory |
| `{InstallerPath}` | Remote installer path |
| `{OutputPath}` | Remote primary output path |
| `{AssetName}` | Product steps에서 사용할 generated/default asset name |

Unknown token은 guest execution 전에 command template rendering 단계에서 거부됩니다. `validate-scenario`는 schema shape를 확인하지만 모든 command token의 full dry run은 아닙니다.

Linux에서도 token의 의미는 같고, `/opt/oslab/artifact` 같은 POSIX 경로를 씁니다.

<a id="product-step-stdout-json-contract"></a>

## 제품 실행 단계 stdout JSON 계약

Agent-like scenario는 단일 `artifact.command` 대신 `product.steps`를 자주 사용합니다. Step에 `captureStdoutJson: true`가 있으면 stdout은 JSON object 하나여야 합니다. `expectStdoutJson`은 반드시 만족해야 하는 값을 선언합니다.

```yaml
product:
  steps:
    - id: scan
      command:
        shell: powershell
        template: '& "{ArtifactDir}\agent.exe" scan --wait --output "{OutputPath}" --json'
      captureStdoutJson: true
      expectStdoutJson:
        ok: true
        outputWritten: true
```

필수 field가 없거나 값이 다르면 해당 step은 product execution failure로 실패합니다. Dotted key를 사용하면 nested object도 확인할 수 있습니다.

<a id="generic-demo-scenarios"></a>

## 범용 데모 시나리오

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
| `scenarios/linux/generic-smoke.example.yaml` | QEMU Guest Agent로 실행하는 Linux 시스템 정보 demo. shell fixture, tar.gz artifact, VM 콘솔 명령 표시 포함 |

<a id="minimal-custom-artifact-examples"></a>

## 최소 사용자 아티팩트 예시

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

<a id="artifact-command-output-contract"></a>

## 아티팩트 명령 출력 계약

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
    "runtime": "python",
    "files": [
      {
        "path": "C:\\Oslab\\demo-fixture-state.json",
        "exists": true,
        "length": 128
      }
    ],
    "directories": [
      {
        "path": "C:\\Oslab",
        "exists": true
      }
    ]
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
| `metadata` | Runtime/compiler/version/path/state 같은 optional object |

Artifact command가 console stdout/stderr도 출력할 수는 있지만, assertion은 수집된 JSON file을 기준으로 동작합니다. Console 출력만으로는 `canonical.command` 검증에 충분하지 않습니다.

`file.exists`, `file.notExists`, `directory.exists` 같은 state assertion은 `metadata.files`, `metadata.directories`에 보고된 상태를 읽습니다. `oslab`이 command 종료 후 guest state를 추측하지 않으므로, artifact command가 자신이 확인한 path 상태를 result JSON에 써야 합니다.

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

<a id="expected-run-flow"></a>

## 예상 실행 흐름

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

<a id="windows-desktop-session"></a>

## Windows 데스크톱 세션

`guest.screen.signIn: true`는 게스트 사전 점검 전에 테스트 계정으로 Windows 데스크톱에 로그인합니다. `guest.screen.showCommands: true`도 함께 켜면 제품 명령이 그 데스크톱의 콘솔 창에서 실행됩니다. 두 설정은 선택 사항이며, 둘 다 생략하면 기존 QEMU Guest Agent 경로로 명령을 실행합니다.

```yaml
guest:
  mode: qemuAgent
  screen:
    signIn: true
    showCommands: true
```

<a id="windows-sign-in"></a>

### 로그인 과정

1. 무작위 비밀번호로 로컬 관리자 계정 `OslabDesktop`을 만듭니다. 비밀번호는 게스트 안에서 만들어 계정과 자동 로그인에만 쓰므로 OSLAB 로그와 보고서에 남지 않습니다.
2. 첫 로그인 애니메이션, 개인 정보 설정 화면, 알림, 설정 권유 화면, OneDrive 설정, 첫 로그인 뒤 Windows가 여는 시작 메뉴를 끕니다. 화면과 VM이 절전 상태로 들어가지 않게도 합니다.
3. 한 번만 쓰는 자동 로그인을 설정하고 Windows를 재시작한 뒤 `OslabDesktop`의 Explorer가 실행될 때까지 기다립니다.
4. 계정 설정이나 로그인에 실패해도 레지스트리의 자동 로그인 비밀번호(`DefaultPassword`)를 지우고 자동 로그인을 끄는 작업을 시도합니다. 비밀번호가 없어졌고 자동 로그인이 꺼졌음을 확인해야 로그인 단계를 통과합니다.

결과는 게스트 사전 점검 항목 `desktop.sign_in`으로 기록됩니다. 로그인에 실패하면 실행은 `preflight_failure`로 멈춥니다. 테스트 계정, 사용자 프로필, 화면 설정은 복제본에 적용되므로 복제본을 보존하는 동안 남습니다. 일반 실행은 종료할 때 복제본을 삭제합니다.

| Progress phase | 시점 |
| --- | --- |
| `desktop.signin.start` | 계정과 자동 로그인을 준비할 때 |
| `desktop.signin.restart` | Windows를 재시작할 때 |
| `desktop.signin.wait` | 데스크톱 세션을 기다릴 때 |
| `desktop.signin.done` 또는 `desktop.signin.failed` | 로그인을 마쳤거나 실패했을 때. details에 `user`, `seconds`, `autologonPasswordRemoved`가 들어갑니다. |

<a id="windows-console-commands"></a>

### 콘솔 창에서 실행되는 명령

`showCommands: true`이면 installer 명령, artifact 명령, 각 product step이 로그인된 세션의 콘솔 창에서 실행됩니다.

- 창 제목은 `OSLab · <단계>`이고, `<단계>`는 product step id, `install`, `command` 중 하나입니다.
- 모든 창은 같은 위치와 크기로 열립니다. 왼쪽에서 120, 위에서 80 픽셀 떨어진 곳에 1040x620 픽셀 크기로 열리고 글꼴은 24px Consolas(없으면 Cascadia Mono)입니다. Proxmox 기본 디스플레이의 1280x800 데스크톱에 맞춘 값이며, 화면이 더 작으면 화면 안에 들어가도록 창을 줄입니다.
- 창에는 `PS>`(`cmd`는 `>`) 뒤에 명령이 나옵니다. 명령이 끝나면 stdout과 stderr의 일부를 보여 주고, stderr는 빨간색으로 표시합니다. 종료 코드가 표시된 뒤 2분 안에 창이 닫힙니다. 다음 명령의 창이 먼저 열리면 앞 창을 가릴 수 있습니다.
- 창은 UTF-8을 쓰므로 한국어·일본어 Windows에서도 경로의 역슬래시가 그대로 보이고, UTF-8이나 시스템 코드 페이지로 나온 출력도 제 언어로 표시됩니다. 명령 자체는 QEMU Guest Agent와 같이 시스템 코드 페이지를 쓰는 숨겨진 콘솔에서 실행됩니다.
- `secretTokens`에 지정된 비밀값은 화면의 명령줄과 출력 미리 보기에서 `<redacted>`로 표시됩니다.
- OSLAB은 로그와 검증에 쓸 stdout, stderr, 종료 코드를 수집한 뒤 명령에 사용한 예약 작업과 임시 파일을 제거합니다. `--command-timeout-seconds`를 넘기면 예약 작업과 자식 프로세스를 종료하고 `guest_execution_timeout`을 기록합니다.

명령은 데스크톱 세션에서 `OslabDesktop` 계정의 관리자 권한으로 실행됩니다. QEMU Guest Agent는 같은 명령을 SYSTEM 계정으로 실행하므로 `%USERPROFILE%`, `%TEMP%`, `%APPDATA%`, `HKCU`가 가리키는 위치가 다릅니다. Fixture, 게스트 사전 점검, 출력 수집은 계속 QEMU Guest Agent로 실행합니다.

| Progress phase | Details |
| --- | --- |
| `desktop.console.setup.done` | 콘솔 helper 준비가 끝났을 때 한 번. `left`, `top`, `width`, `height`, `fontSize` |
| `desktop.console.start` | 명령마다 실행 전. `title`과 요청한 `left`, `top`, `width`, `height` |
| `desktop.console.done` | 명령마다 실행 후. `title`, `exitCode`, `seconds`, Windows가 실제로 적용한 창 위치와 크기(`left`, `top`, `width`, `height`), `screenWidth`, `screenHeight`, `font`(예: `Consolas 24`) |
| `desktop.console.failed` | 명령이 제한 시간을 넘겼거나 콘솔이 명령을 실행하지 못했을 때 |

<a id="windows-template-requirements"></a>

### 템플릿 요구 사항

템플릿에는 QEMU Guest Agent, .NET Framework 4의 C# 컴파일러(`csc.exe`, Windows 10과 11에 기본 포함), ScheduledTasks PowerShell 모듈이 있어야 합니다. OSLAB은 게스트 안에서 작은 콘솔 helper를 컴파일하고 예약 작업으로 콘솔 창을 엽니다. Windows 11 25H2 템플릿에서 검증했습니다.

자동 로그인은 한 번만 동작합니다. 명령이 Windows를 재시작하면 데스크톱에 다시 로그인하지 않으므로 이후 콘솔 명령은 실패합니다.

<a id="linux-guests"></a>

## Linux 게스트

Linux 시나리오는 QEMU Guest Agent 채널로 실행합니다. `os.family: linux`와 `guest.mode: qemuAgent`를 지정합니다. `guest.mode: auto`를 쓸 때는 `linuxOrder`를 생략하거나 목록에 `qemuAgent`를 넣습니다.

템플릿에는 Proxmox `agent: 1` 설정과 실행 중인 `qemu-guest-agent`가 있어야 하고, `guest-exec`와 `guest-file-*` 명령을 허용해야 합니다. 게스트에는 `sh`와 기본 Linux 유틸리티가 필요합니다. 아카이브 전송은 gzip을 지원하는 `tar`와 GNU 방식의 `cp -aT`를 씁니다. 큰 파일을 올릴 때는 `sha256sum`과 `mv -fT`를 쓰고, 텍스트 다운로드의 대체 경로는 `base64`를 씁니다.

```yaml
os:
  family: linux
provider:
  type: proxmox
  template: ubuntu-24.04-template
  templateVmId: 9000
  vmIdRange:
    start: 9185
    end: 9189
  clone:
    display: virtio
    network: disconnected
guest:
  mode: qemuAgent
  screen:
    showCommands: true
fixtures:
  - id: baseline
    type: shell
    source: validation/fixtures/linux/generic-smoke.sh
artifact:
  type: folder
  pathParam: artifactPath
  destination: /opt/oslab/artifact
  transfer: archive
  command:
    shell: sh
    template: '"{ArtifactDir}/run-system-demo.sh" "{OutputPath}"'
outputs:
  actual:
    path: /opt/oslab/command-result.json
    adapter: canonical.command
```

| 항목 | Linux 동작 |
| --- | --- |
| 명령 | `shell: sh` 또는 `shell: bash`. 게스트 에이전트 사용자(보통 root)로 셸을 실행하고 치환할 값을 위치 인자로 전달합니다. |
| 게스트 사전 점검 | `oslab run`에서 `linux.shell`(`sh`로 `uname -s` 실행), `oslab.directory`(`/opt/oslab` 쓰기 가능 확인), `oslab.file_roundtrip`(테스트 파일 쓰고 읽기), `oslab.cleanup_test_file`(테스트 파일 삭제)을 실행합니다. |
| Fixture | `type: shell`. 스크립트를 LF 줄바꿈으로 `/opt/oslab/fixtures/<파일 이름>`에 올리고 실행 권한을 준 뒤 경로로 실행합니다. shebang이 있으면 그 인터프리터를, 없으면 `sh`를 씁니다. |
| `transfer: archive` | `destination` 옆 임시 디렉터리에 tar.gz를 올려 풀고, 내용물을 `destination`에 복사합니다. 대상 디렉터리에 있던 다른 파일은 남고 임시 디렉터리는 정리합니다. |
| `transfer: files` | `mkdir -p`로 디렉터리를 만든 뒤 파일을 하나씩 올립니다. 폴더 아티팩트의 기본 전송 방식입니다. |
| 실행 파일 | shebang, ELF 시그니처 또는 로컬 실행 비트가 있는 파일은 실행할 수 있게 전송합니다. 아카이브에서는 해당 파일에 0755, 나머지 파일에 0644 권한을 부여합니다. |
| Installer artifact | 파일을 `destination`에 올리고 실행 권한을 줍니다. `{InstallerPath}`는 `destination`, `{ArtifactDir}`는 그 상위 디렉터리입니다. |
| 기본 출력 경로 | `outputs.actual.path`가 없으면 `/opt/oslab/result.json`입니다. |
| 큰 파일 | 게스트 에이전트의 파일 쓰기 한도(인코딩 후 60 KiB)를 넘으면 임시 조각으로 나눠 올립니다. 게스트에서 조각을 합치고 SHA-256을 확인한 뒤 대상 경로로 옮깁니다. |

`artifact.destination`은 일회용 게스트 안의 POSIX 절대 경로로 지정합니다. 폴더 아티팩트에는 디렉터리 경로를, 설치 파일에는 파일명까지 포함한 경로를 지정합니다. 아티팩트는 바이트 그대로 전송하므로 셸 스크립트는 LF 줄바꿈을 유지합니다. 저장소의 `.gitattributes`가 Windows에서도 `*.sh`를 LF로 체크아웃하게 합니다. [`commandResult` JSON을 쓰는 예제](../validation/artifacts/linux-system/run-system-demo.sh)

`guest-preflight`와 `fixture-smoke`는 아직 Windows만 지원합니다. Linux fixture를 디버깅할 때는 `oslab run --keep-vm`으로 실행한 뒤 `oslab qga-exec -- sh -c '...'`로 복제본을 확인합니다. `qga-upload`와 `qga-download` 도우미는 큰 파일 업로드와 읽기 대체 경로에 Windows 명령을 씁니다.

<a id="linux-console-commands"></a>

### Linux 콘솔에 명령 표시

`guest.screen.showCommands: true`이면 OSLAB은 첫 번째 텍스트 콘솔(tty1)을 명령 표시 화면으로 씁니다.

1. 첫 명령 전에 `getty@tty1` 로그인 프롬프트를 멈춰 로그인 화면이 명령 표시를 덮지 못하게 합니다. 이어서 게스트에 `setfont`와 프레임버퍼 콘솔이 있으면 Terminus 32x16 글꼴을 적용하고, 화면을 지운 뒤 `root@<host>:/# ` 같은 프롬프트를 띄웁니다.
2. 픽스처, 설치 명령, 제품 명령, 개별 실행 단계를 실행할 때마다 치환한 명령을 프롬프트 뒤에 표시합니다. 이어서 stdout·stderr와 새 프롬프트가 나오며, 종료 코드가 0이 아니면 `[exit N]`을 덧붙입니다.
3. 시나리오가 `secretTokens`를 쓰면 비밀값 자리에 `<redacted>`를 표시하고 tty1에는 명령의 출력을 표시하지 않습니다.

OSLAB이 기록하는 종료 코드와 stdout·stderr는 그대로 QEMU Guest Agent에서 받으므로 화면 표시가 결과를 바꾸지 않습니다. tty1이 없거나 쓸 수 없으면 화면 표시 없이 명령만 실행합니다.

글자 크기는 게스트 커널이 제공하는 콘솔에 따라 달라집니다. Ubuntu 24.04 cloud image에서는 다음과 같습니다.

| `provider.clone.display` | 콘솔 |
| --- | --- |
| `std` | VGA 텍스트 콘솔 720x400 픽셀(80x25). 커널에 `bochs` DRM 드라이버가 없어 큰 글꼴을 적용할 수 없습니다. |
| `virtio` | virtio-gpu 프레임버퍼 콘솔 1280x800 픽셀. Terminus 32x16 글꼴로 80x25 크기의 큰 글자를 보여 줍니다. |

<a id="product-specific-scenarios"></a>

## 제품별 시나리오

Product-specific scenario는 generic scenario authoring 경로가 아니라 product-owned docs에 둡니다. Generic docs는 특정 private product workflow가 아니라 platform contract를 설명해야 합니다.
