# Windows 앱 테스트 매트릭스

[English](windows-app-matrix.md) · 한국어

일회용 Windows 11 VM에서 실행하는 시나리오 32개입니다. `01`~`28`은 Microsoft Edge에서 실행되는 서로 다른 오프라인 예제 웹 앱이고, `29`~`32`는 Windows 앱을 사용합니다. 시나리오마다 VM을 따로 띄우고, 화면에 나타난 작업을 게스트에서 얻은 결과로 검증합니다. [매트릭스 소스](../validation/artifacts/windows-app-matrix)

| 시나리오 | 작업 | 검증 대상 |
| --- | --- | --- |
| 01~28 | 실사 재고 대조, 사진 중복 제거 및 콘택트 시트 제작, 예약 시간에 맞춘 경로 수정 등 | 앱이 단계별로 계산한 값과 별도로 정의한 기대값 일치 여부 |
| 29 · 메모장 | 릴리스 인수인계 문서를 수정하고 다시 열기 | 저장된 승인 상태, 줄 수, 수정 파일의 SHA-256 |
| 30 · 파일 탐색기 | ZIP 폴더에서 증거 파일 두 개 복구 | 복구한 파일 수와 두 파일의 SHA-256 |
| 31 · 그림판 | PNG의 승인 칸을 채운 뒤 저장 | PNG 형식, 이미지 크기, 채운 픽셀과 그대로 남아야 하는 비교용 픽셀 |
| 32 · 계산기 | 상자 수에 상자당 수량을 곱하고 예비 수량을 뺀 뒤 팔레트 수로 환산 | 연산 단계별 표시값 |

공개 영상 촬영에서는 32개 작업의 검증 항목 351개가 통과했습니다. 배치별 화면 수와 각 검증의 기대값·관찰값을 확인할 수 있습니다. [촬영 및 검증 기록](media/oslab-windows-app-matrix-attestation.json)

## 테스트 환경 준비

저장소 루트에서 Node.js 18 이상과 OSLab의 `computer-use` 추가 의존성을 사용합니다. Proxmox 노드에는 Edge와 네 Windows 앱을 실행할 수 있는 Windows 11 QEMU 템플릿이 필요합니다. 그래픽 콘솔에서 절대 좌표 포인팅을 지원하고 QEMU Guest Agent(QGA)가 동작해야 합니다. 연결 복제를 지원하는 스토리지와 전용 VMID 범위를 준비합니다. Proxmox 토큰에는 임시 VM 관리, QGA 사용, `VM.Console` 권한이 필요합니다. [Proxmox 연결](proxmox-connection.ko.md) · [콘솔 MCP](computer-use-mcp.ko.md)

아래 예시에서 템플릿 VMID와 복제본 범위를 랩에 맞게 바꿉니다. 새 실행마다 별도 출력 디렉터리를 지정합니다. 재시도하거나 정리할 때는 같은 출력 디렉터리, 설정 파일, VMID 범위를 사용합니다.

```powershell
$demo = 'validation/artifacts/windows-app-matrix'
$runner = "$demo/run_matrix.py"
$job = 'runs/windows-app-matrix-demo'
$bundle = "$job/bundle"
$lab = @(
    '--config', 'config/oslab.local.yaml',
    '--env-file', 'config/oslab.local.env',
    '--output', "$job/capture",
    '--template-vmid', '9200',
    '--vmid-start', '9300',
    '--vmid-end', '9339'
)
node "$demo/bundle.js" $bundle
if ($LASTEXITCODE -ne 0) { throw 'App bundle validation failed.' }
uv run --locked --extra computer-use python $runner prepare @lab
```

`bundle.js`는 예제 앱의 단계별 동작을 로컬에서 검증하고 각 앱의 HTML과 `cases.json`을 생성합니다. `prepare`는 Windows 템플릿을 복사해 테스트용 계정을 구성하고, 격리된 임시 복제 원본을 만듭니다. 이 원본과 각 테스트 VM에는 네트워크 어댑터를 연결하지 않습니다.

## 실행하고 결과 확인하기

```powershell
uv run --locked --extra computer-use python $runner run @lab --bundle $bundle
```

일부만 실행하려면 `--cases 01 02 29 31`을 추가합니다. 배치당 기본 상한은 4대입니다. 메모리가 충분하면 `--wave-size 8`로 상한을 올릴 수 있습니다. 실행기는 VM 한 대당 5 GiB를 기준으로 계산하며, 배치를 시작할 때 노드에 12 GiB 여유가 남도록 동시 실행 대수를 조정합니다.

웹 앱은 게스트 안의 `127.0.0.1:7788`에서 열리고, PowerShell 리스너가 작업마다 JSON을 저장합니다. 앞 단계 결과가 저장되어야 다음 버튼을 누를 수 있습니다. 앱은 예제 데이터를 바탕으로 실제 값을 계산합니다. 일부 시나리오는 잘못된 입력이나 결함을 일부러 넣고, 기대한 이유로 작업이 차단되는지 확인합니다.

OSLab MCP는 Proxmox의 VNC 콘솔로 각 VM에 클릭과 키 입력을 보내고 화면을 캡처합니다. QGA는 별도 경로로 게스트 앱을 시작하고 저장된 결과를 읽습니다. 실행기는 웹 앱의 결과를 `cases.json`의 기대값과 대조하고, Windows 앱은 저장한 파일이나 계산기에서 표시한 값으로 검증합니다.

- `capture/case-*.json`에 기대값과 관찰값, 배치 번호, 프레임 파일명과 SHA-256, 입력과 캡처 시간을 기록합니다. 같은 배치의 프레임은 공통 시작 시각을 기준으로 비교할 수 있습니다.
- `capture/*-stage-*.png`와 나머지 PNG에는 작업 전후 게스트 화면이 담깁니다. 촬영 시각으로 동시에 기록한 화면을 확인하고, 배치 번호로 다른 시간에 촬영한 장면을 구분할 수 있습니다.
- 요청한 시나리오 중 검증 결과가 빠진 항목이 있으면 종료 코드가 0이 아닙니다. 오류를 확인한 뒤 같은 출력 디렉터리에서 다시 실행하면 검증을 마친 항목은 건너뜁니다. 중단한 배치의 VM이 남아 있다면 `run` 대신 `cleanup-wave`를 먼저 실행하면 임시 복제 원본을 유지한 채 해당 VM을 정리할 수 있습니다.

## 임시 VM 정리

배치를 마칠 때마다 해당 배치의 VM이 정리됩니다. 전체 실행을 마쳤거나 중단했다면 `cleanup`을 실행해 남은 VM, 디스크와 임시 복제 원본을 정리합니다. 소유권을 확인하는 기록이 있으므로 정리 전에 캡처 디렉터리를 삭제하지 않습니다.

```powershell
uv run --locked --extra computer-use python $runner cleanup @lab
```

실행기가 촬영용 VM, 디스크, VMID 예약이 남아 있는지 확인한 뒤 `capture/cleanup.ok`를 기록합니다. 필요한 촬영·검증 결과를 보관합니다.
