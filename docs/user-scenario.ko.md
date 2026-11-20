# Windows와 Ubuntu에서 엔드포인트 에이전트 재검증하기

[English](user-scenario.md) · 한국어

Windows 11과 Ubuntu 24.04용 인벤토리 에이전트를 만드는 개발자가 다음 빌드를 QA에 넘기려고 합니다. 두 OS에서 새로 설치할 수 있고, 기존 설치를 올려도 동작한다는 증거가 필요합니다. 후보 빌드, OS 이미지, 업그레이드 기준 버전, 빌드 환경이 바뀔 때마다 같은 네 가지 시험을 다시 실행합니다.

예제에 쓰는 Demo Agent 2.4.0은 자산을 로컬에 등록하고 Windows 레지스트리나 Ubuntu 패키지 데이터베이스에서 설치된 소프트웨어 목록을 수집합니다. 두 OS용 스크립트는 같은 `VERSION`을 읽고 시나리오가 검사할 값을 JSON으로 출력합니다. 서버 주소는 로컬 상태에 기록하므로 복제 VM 네 대는 네트워크를 끊은 채 실행할 수 있습니다. [Demo Agent 파일](../validation/artifacts/demo-agent-cli)

## 업그레이드에서 지켜야 할 값

새로 설치하면 처음부터 현재 형식으로 상태 파일을 씁니다. 업그레이드할 장비에는 2.3.1의 등록 정보와 INI 설정이 남아 있습니다. 2.4.0이 업그레이드 중에 새 자산 ID를 만들면 인벤토리 서버에 같은 장비가 두 번 나타나고 기존 자산의 이력이 끊길 수 있습니다.

업그레이드용 픽스처는 자산 ID, 등록 시각, 설정을 고정값으로 채웁니다. 후보 빌드는 이전 파일을 백업하고, INI 설정을 JSON으로 옮기고, 상태 스키마를 1에서 2로 바꿉니다. 업그레이드 시나리오는 등록 명령을 실행하지 않고, 2.4.0의 첫 스캔 결과에 기존 자산 ID가 들어 있는지 확인합니다. [Windows 픽스처](../validation/fixtures/windows/demo-agent-2.3-installed.ps1) · [Ubuntu 픽스처](../validation/fixtures/linux/demo-agent-2.3-installed.sh)

## 네 가지 검증 환경

| 실행 묶음 항목 | 게스트와 시작 상태 | 단계 |
| --- | --- | --- |
| [`windows-fresh`](../scenarios/windows/demo-agent-fresh-install.example.yaml) | 초기 상태의 Windows 11 | version, install, register, status, scan |
| [`windows-upgrade`](../scenarios/windows/demo-agent-upgrade.example.yaml) | 2.3.1 설치와 등록을 마친 Windows 11 | version, install, status, scan |
| [`ubuntu-fresh`](../scenarios/linux/demo-agent-fresh-install.example.yaml) | 초기 상태의 Ubuntu 24.04 | version, install, register, status, scan |
| [`ubuntu-upgrade`](../scenarios/linux/demo-agent-upgrade.example.yaml) | 2.3.1 설치와 등록을 마친 Ubuntu 24.04 | version, install, status, scan |

제품 실행 단계는 stdout에 JSON 객체 하나를 쓰고 진행 상황은 stderr에 표시합니다. `expectStdoutJson`으로 지정한 필드가 기대값과 다르면 해당 단계가 실패합니다. 새 설치에서는 신규 등록과 스키마 2 상태를 확인합니다. 업그레이드에서는 마이그레이션, 백업, 기존 자산 ID와 등록 시각, 360분 스캔 간격 같은 설정값을 확인합니다. 네 환경 모두 수집한 인벤토리에 Demo Agent 2.4.0과 해당 OS에서 수집한 레코드가 있는지 검사합니다. [stdout JSON 계약](scenarios.ko.md#제품-실행-단계-stdout-json-계약)

## 매트릭스 실행하기

저장소 루트에서 아래 절차를 진행합니다. QEMU Guest Agent가 설치된 Windows 11과 Ubuntu 24.04 템플릿, OSLab 로컬 config와 env 파일, 비어 있는 VMID 네 개와 VM 네 대를 동시에 띄울 메모리가 필요합니다. Windows 시나리오는 테스트 계정으로 로그인한 바탕 화면에 명령을 표시합니다. Ubuntu 시나리오는 VirtIO 디스플레이를 쓰고 첫 번째 텍스트 콘솔에 명령을 표시합니다. [Proxmox 준비](proxmox-connection.ko.md#템플릿-요구-사항) · [Linux 게스트 준비](scenarios.ko.md#linux-게스트) · [시작하기](getting-started.ko.md)

다른 랩에서도 같은 예제를 쓸 수 있도록 랩 설정은 사본에 넣습니다. 아래에서 만든 `qa-` 파일은 Git이 무시하며 대시보드에서도 실행할 수 있습니다.

```powershell
$names = 'windows/demo-agent-fresh-install', 'windows/demo-agent-upgrade',
         'linux/demo-agent-fresh-install', 'linux/demo-agent-upgrade'
foreach ($name in $names) {
    $source = "scenarios/$name.example.yaml"
    $copy = $source -replace '/demo-agent-', '/qa-demo-agent-'
    if (-not (Test-Path -LiteralPath $copy)) { Copy-Item -LiteralPath $source -Destination $copy }
}
$suite = 'validation/suites/qa-demo-agent-matrix.example.yaml'
if (-not (Test-Path -LiteralPath $suite)) {
    $content = (Get-Content -Raw 'validation/suites/demo-agent-matrix.example.yaml') -replace 'scenario: scenarios/(windows|linux)/demo-agent-', 'scenario: scenarios/$1/qa-demo-agent-'
    Set-Content -LiteralPath $suite -Value $content -Encoding utf8
}
```

시나리오 사본 네 개에서 `provider.template`, `provider.templateVmId`, `provider.vmIdRange`를 랩에 맞게 지정합니다. 복제에 필요한 빈 번호가 충분하면 네 항목이 같은 범위를 써도 됩니다. `--max-parallel 4`를 지정하면 네 환경을 동시에 실행합니다. 네 항목에 같은 아티팩트 폴더를 전달하고, 각 시나리오는 다른 OS용 스크립트를 제외합니다.

```powershell
uv run --locked oslab suite-run `
    --suite validation/suites/qa-demo-agent-matrix.example.yaml `
    --config config/oslab.local.yaml `
    --env-file config/oslab.local.env `
    --artifact-path validation/artifacts/demo-agent-cli `
    --max-parallel 4
```

웹 대시보드에서는 **실행** 탭에서 같은 실행 묶음을 고르고 테스트 폴더에 `validation/artifacts/demo-agent-cli`를 지정한 뒤 동시 실행 수를 4로 설정합니다. 한 항목만 CLI에서 다시 실행하려면 `oslab run`에 해당 시나리오와 같은 아티팩트 폴더를 넘깁니다. [대시보드 실행 가이드](web-dashboard-server.ko.md)

## 실행 결과 읽기

`runs/<suite-run-id>/reports/suite.html`을 열면 네 항목의 결과를 볼 수 있습니다. 모두 통과했을 때 `suite.json`에는 `status: passed`, `summary.passed: 4`, `summary.requiredFailed: 0`이 남습니다. 영상에 사용한 랩 실행 `intro-suite-v2-20261120`은 네 환경에서 검사 16개를 모두 통과했습니다. [영상 검증 기록](media/oslab-intro-film-attestation.json)

개별 결과는 `scenarios/<suite-run-id>-<entry-id>/`에서 확인합니다. `raw/product-steps.json`에 단계별 명령, 종료 코드, stdout JSON 비교 결과가 남습니다. 업그레이드 항목의 `raw/` 아래 픽스처 매니페스트에는 비교에 쓴 기준값이 들어 있고, `logs/product-step-status.stderr.log`에는 마이그레이션 상태가 기록됩니다. 후보 빌드가 새 자산 ID를 만들면 실패한 단계의 `details.stdoutJsonExpectation.mismatches`에서 기대값과 실제 값을 비교할 수 있습니다. [보고서와 결과](reports.ko.md)

## 내 제품에 적용하기

1. 지원하는 OS와 설치 경로를 짝지어 실행 묶음에 한 항목씩 넣습니다. 고객이 업그레이드할 수 있는 이전 릴리스를 포함합니다.
2. 보존해야 하는 식별값, 설정, 파일, 레지스트리 키를 픽스처로 복원합니다.
3. 제품 명령이 JSON을 출력하게 하거나 필요한 값을 출력하는 스크립트로 감쌉니다. 실행 단계에서 보존할 값을 비교하고, 수집한 결과 파일에도 통과 조건을 둡니다.
4. 매번 후보 아티팩트 하나를 네 항목에 공통으로 전달합니다. 컴파일러나 패키징 방식, 빌드 장비를 바꿨다면 소스 리비전을 고정한 채 비교합니다. OS 이미지를 바꿨다면 후보 빌드를 고정하고 템플릿을 항목별로 기록합니다.

[예제 실행 묶음](../validation/suites/demo-agent-matrix.example.yaml)과 [시나리오 작성 가이드](scenarios.ko.md)를 참고하세요.
