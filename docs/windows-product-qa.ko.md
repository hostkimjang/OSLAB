# 실제 Windows 프로그램으로 릴리스 검증하기

[English](windows-product-qa.md) · 한국어

일회용 Windows 11 VM에서 실제 프로그램을 조작하는 릴리스 QA 시나리오 32개입니다. VM마다 프로그램 하나 또는 LibreOffice 앱 하나를 실행하고 합성 릴리스 데이터를 사용합니다. OSLab MCP는 Proxmox 콘솔로 클릭과 키 입력을 보냅니다. 실행기는 QEMU Guest Agent(QGA)를 통해 파일 해시, 계산 결과, 화면 상태를 별도로 확인합니다. [시나리오 소스](../validation/artifacts/windows-product-qa) · [콘솔 MCP](computer-use-mcp.ko.md)

32대 영상에서 일회용 Windows 11 VM으로 시나리오 32개를 실행했고, 검사 140개를 모두 통과했습니다. [소개 영상](intro-video.ko.md)의 06장은 이 녹화본을 다시 씁니다. [32대 영상 소개](intro-video.ko.md#32대-windows-qa-영상) · [1080p 영상](https://raw.githubusercontent.com/hostkimjang/OSLAB/master/docs/media/oslab-windows-product-qa.mp4) · [검증 기록](media/oslab-windows-product-qa-attestation.json)

## 시나리오 목록

| ID | 프로그램 | 확인할 결과 |
| --- | --- | --- |
| 01 | 7-Zip File Manager | 릴리스 ZIP에서 푼 파일 6개의 해시가 배포 명세와 일치합니다. |
| 02 | LibreOffice Calc | 산출물 개수를 수정하면 소계와 릴리스 판정이 다시 계산됩니다. |
| 03 | OBS Studio | 로컬 검증 장면을 녹화하면 재생 가능한 H.264/AAC 파일이 생성됩니다. |
| 04 | Notepad++ | INI의 실제 적용 항목이 바뀌고 롤백용 설정은 보존됩니다. |
| 05 | Visual Studio Code | 기동 시간 한도로 인해 실패한 검사가 설정을 수정한 뒤 통과합니다. |
| 06 | Git GUI | 로컬 Git 트리에 선택한 롤백 조건 변경만 반영됩니다. |
| 07 | Python IDLE | 재시도 상한을 수정한 뒤 단위 테스트 세 개가 통과합니다. |
| 08 | DB Browser for SQLite | 누락 값을 채우는 마이그레이션 후 기존 행이 보존되고 무결성 검사를 통과합니다. |
| 09 | WinMerge | 재시도 정책을 병합한 뒤에도 후보 버전과 라우팅 설정이 유지됩니다. |
| 10 | VLC media player | 영상이 12초 지점으로 이동한 뒤 일시 정지합니다. |
| 11 | Audacity | 앞부분의 테스트 슬레이트를 잘라내면 3초짜리 모노 PCM 파일이 나옵니다. |
| 12 | LibreOffice Writer | 승인 문구가 담긴 인수인계 문서를 두 페이지 PDF로 내보냅니다. |
| 13 | LibreOffice Impress | 내보낸 문서에서 슬라이드 순서와 16:9 비율이 유지됩니다. |
| 14 | LibreOffice Draw | 인쇄용 표식의 이동 좌표와 내보낸 PDF의 페이지 크기가 기대값과 일치합니다. |
| 15 | Shotcut | 클립 두 개를 편집해 내보낸 MP4의 해상도와 길이가 일치합니다. |
| 16 | ILSpy | 내보낸 소스에 후보 어셈블리의 공개 API 시그니처가 포함됩니다. |
| 17 | Inkscape | 페이지 밖의 인쇄 영역을 잘라내고 PNG 내부 픽셀을 유지합니다. |
| 18 | SumatraPDF | 릴리스 검토 문서의 롤백 근거 페이지와 최종 승인 페이지로 이동합니다. |
| 19 | Everything | 배포 후보를 검색해 기대한 ZIP 파일 경로만 찾습니다. |
| 20 | ImageMagick | 달라진 배지의 픽셀 차이를 찾고, 수정 후 차이가 없어지는지 확인합니다. |
| 21 | Event Viewer | 명세 누락 오류 뒤에 복구 이벤트가 남습니다. |
| 22 | Task Scheduler | 작업을 수동 실행하면 기대한 파일 목록과 해시가 기록됩니다. |
| 23 | Windows PowerShell ISE | 패키지 파일 개수의 기댓값을 고치면 실패하던 검사가 통과합니다. |
| 24 | ODBC Data Source Administrator | 64비트 테스트 데이터 원본의 드라이버와 라우팅 설정이 유지됩니다. |
| 25 | Process Monitor | 설정 파일이 없을 때의 오류와 복구 후 성공한 접근이 추적에 남습니다. |
| 26 | Process Explorer | 릴리스 명세 파일을 잠근 테스트 프로세스를 찾고 잠금이 풀렸는지 확인합니다. |
| 27 | TCPView | 테스트 서버의 수신 대기 포트와 연결 상태가 Windows 소켓 조회 결과와 일치합니다. |
| 28 | VMMap | 프로세스 스냅샷에 32 MiB 버퍼 할당이 기록됩니다. |
| 29 | Notepad | 저장한 인수인계 파일을 다시 열었을 때 파일 바이트가 기대값과 일치합니다. |
| 30 | File Explorer | ZIP에서 복원한 파일 두 개의 해시가 원본과 일치합니다. |
| 31 | Paint | 저장한 PNG의 크기와 채우기 색이 일치하고 비교용 픽셀은 유지됩니다. |
| 32 | Performance Monitor | 그래프를 멈췄다가 다시 갱신하고, 별도 CPU 측정값으로 부하와 복구를 확인합니다. |

## 테스트 환경 준비

저장소 루트에서 `uv`와 OSLab `computer-use` 의존성을 사용합니다. Proxmox에 그래픽 콘솔, QGA, Windows App Installer가 있는 x64 Windows 11 템플릿을 준비합니다. 설치 파일을 받을 때는 템플릿과 같은 `net0` 설정으로 준비용 VM을 연결합니다. 연결 복제를 지원하는 스토리지와 전용 VMID 범위가 필요합니다. Proxmox 토큰에는 VM 복제·정리, QGA 실행, 콘솔 접근 권한이 있어야 합니다. [Proxmox 연결](proxmox-connection.ko.md)

`prepare`는 준비용 VM을 만들고 패키지 설치를 시작합니다. 설치 작업이 끝나고 누락된 프로그램이 없어질 때까지 `inventory`로 확인합니다. `seal`은 설치 상태를 확인하고 네트워크 어댑터를 제거한 뒤 해당 디스크를 테스트 VM의 복제 원본으로 전환합니다. Windows 기본 도구는 게스트 템플릿에 포함된 것을 사용합니다. 패키지 출처와 고정된 해시는 설치 스크립트에서 확인할 수 있습니다. [패키지 준비 스크립트](../validation/artifacts/windows-product-qa/stage_products.ps1)

주요 프로그램의 공식 배포처는 [7-Zip](https://www.7-zip.org/download.html), [The Document Foundation](https://www.libreoffice.org/download/), [OBS Studio](https://obsproject.com/download), [WinMerge](https://winmerge.org/downloads/), [Microsoft Sysinternals](https://learn.microsoft.com/en-us/sysinternals/downloads/)입니다.

아래의 설정 경로와 VMID를 랩 환경에 맞게 바꿉니다. 새 실행마다 출력 디렉터리를 다르게 지정하고, 재시도와 정리에는 처음 사용한 값을 그대로 씁니다.

```powershell
$demo = 'validation/artifacts/windows-product-qa'
$lab = @(
    '--config', 'config/oslab.local.yaml',
    '--env-file', 'config/oslab.local.env',
    '--output', 'runs/windows-product-qa-demo',
    '--template-vmid', '9200',
    '--vmid-start', '9300',
    '--vmid-end', '9339'
)
uv run --locked --extra computer-use python "$demo/run.py" catalog
uv run --locked --extra computer-use python "$demo/setup.py" prepare @lab
uv run --locked --extra computer-use python "$demo/setup.py" inventory @lab
```

## 촬영 및 검증

도구 설치를 확인한 뒤 복제 원본을 봉인하고 시나리오를 실행합니다. `--wave-size`로 배치 크기를 정합니다. 기본은 4대, 최대는 8대이며, 노드의 가용 메모리에 따라 더 작아질 수 있습니다. 일부만 확인하려면 `--cases 01 02 03 08`을 추가합니다.

```powershell
uv run --locked --extra computer-use python "$demo/setup.py" seal @lab
if ($LASTEXITCODE -ne 0) { throw 'Windows product source was not sealed' }
uv run --locked --extra computer-use python "$demo/run.py" run @lab --wave-size 4
```

- `case-<ID>.json`에 프로그램, 배치, 기대값과 관찰값, 검사 판정, 프레임 해시, MCP 입력 시간을 기록합니다. 기대값과 다른 검사는 `unmatched-<ID>.json`에서 확인할 수 있습니다.
- `<ID>-stage-0.png`부터 `<ID>-stage-3.png`까지 주요 단계의 실제 게스트 화면입니다. 추가 프레임도 같은 배치의 촬영 시각을 기록합니다. 영상에서 같은 시간대의 화면은 시간축을 맞춰 압축하고, 여러 배치에서 가져온 32칸 화면에는 편집본임을 표시합니다.
- 다음 실행은 출력 디렉터리에 이미 결과가 있는 항목을 건너뜁니다. 남겨 둔 VM을 정리하고 다시 실행하려면 같은 설정으로 `cleanup-wave`를 사용합니다. 요청한 항목 중 결과가 빠져 있으면 실행기는 종료 코드 0을 반환하지 않습니다.

## 32대 영상 녹화

`fleet.py`는 같은 시나리오를 여러 묶음으로 나눠 실행하고, VM마다 콘솔 화면을 별도 영상으로 녹화합니다. 묶음마다 봉인한 원본에서 연결 복제본을 만들고, 노드의 가용 메모리를 확인하면서 몇 대씩 켭니다. 모든 콘솔을 30fps로 녹화하면서 묶음 안의 작업을 동시에 시작하고, 다음 묶음을 시작하기 전에 VM을 지웁니다. 실패한 작업은 다음 묶음에서 한 번 더 실행합니다. 명령을 다시 실행하면 아직 통과하지 못한 작업만 반복합니다.

녹화하려면 Proxmox 노드에 직접 연결해야 하므로 `--lan-address`에 노드의 LAN 주소를 지정합니다. 실행기는 설정된 API에서 클러스터 CA를 받아 출력 디렉터리에 LAN용 설정을 만들고, 노드 인증서를 그 CA로 검증합니다. `screen_recorder.py`는 QEMU에 바뀐 화면 영역만 요청하고 MCP 입력 세션과 콘솔을 함께 씁니다. 녹화 중에도 클릭과 키 입력은 그대로 전달됩니다.

`edit_video.py`는 이 녹화본으로 영상을 편집합니다. 녹화본마다 해당 작업의 시작 시점에 맞춰 한 화면에 모두 배치하고, 주요 작업은 확대해서 보여 줍니다. 기다리는 구간은 빠르게, 조작하는 구간은 실제 속도에 가깝게 재생합니다. 각 작업은 게스트 안에서 검사를 통과한 시점에 PASS로 표시합니다. 작업마다 테스트 에이전트를 색이 다른 커서로 보여 주는데, 커서는 `case-<ID>.json`에 기록된 MCP 클릭 위치와 시각을 따르고 클릭 사이 경로는 보간합니다. 편집기는 [Geist](https://github.com/vercel/geist-font) 글꼴을 사용하며, 오디오 트랙 없는 `oslab-intro-master.mp4`를 만듭니다.

공개용 파일은 원본을 2-pass로 다시 인코딩해 GitHub 무료 플랜의 영상 한도인 10MB 아래로 맞춘 것입니다. `--receipt`를 지정하면 프로그램, 검사 결과, 해당 파일의 해시를 담은 JSON 기록을 같은 위치에 만듭니다. [장면 구성](intro-video.ko.md#32대-windows-qa-영상)

```powershell
uv run --locked --extra computer-use python "$demo/fleet.py" run @lab --lan-address 192.168.0.10 --wave-size 8 --ffmpeg ffmpeg
$edit = @('--run-dir', 'runs/windows-product-qa-demo', '--fonts', 'fonts/geist', '--out', 'runs/windows-product-qa-demo/video', '--ffmpeg', 'ffmpeg')
uv run --locked --extra computer-use python "$demo/edit_video.py" @edit
$encode = @('-y', '-i', 'runs/windows-product-qa-demo/video/oslab-intro-master.mp4', '-an', '-c:v', 'libx264', '-preset', 'slower',
    '-b:v', '1150k', '-maxrate', '2600k', '-bufsize', '5200k', '-pix_fmt', 'yuv420p')
ffmpeg @encode -pass 1 -f mp4 NUL
ffmpeg @encode -pass 2 -movflags +faststart docs/media/oslab-windows-product-qa.mp4
uv run --locked --extra computer-use python "$demo/edit_video.py" @edit --receipt docs/media/oslab-windows-product-qa.mp4
uv run --locked --extra computer-use python "$demo/fleet.py" cleanup @lab --lan-address 192.168.0.10
```

GitHub 댓글 작성창에 첨부만 하고 게시하지 않은 파일은 로그아웃한 방문자에게 404로 보입니다. README에 넣을 첨부 파일은 게시한 댓글이나 PR 설명에 먼저 올린 뒤 연결합니다.

## 임시 자원 정리

작업 디렉터리를 지우기 전에 같은 설정으로 정리 명령을 실행합니다. 실행기가 소유권 기록을 바탕으로 VM, 디스크, VMID 예약을 확인합니다. 명령이 성공하면 `cleanup.ok`가 남습니다.

```powershell
uv run --locked --extra computer-use python "$demo/run.py" cleanup @lab
```
