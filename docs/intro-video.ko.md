# OSLab 소개 영상

[English](intro-video.md) · 한국어

[![OSLab 소개 영상, 2분 45초](media/oslab-intro-film-poster.jpg)](https://raw.githubusercontent.com/hostkimjang/OSLAB/master/docs/media/oslab-intro-film.mp4)

[1080p MP4 다운로드](https://raw.githubusercontent.com/hostkimjang/OSLAB/master/docs/media/oslab-intro-film.mp4) · [검증 기록](media/oslab-intro-film-attestation.json) · [제작 방법](#제작-방법)

## 시놉시스

테스트 정의부터 OSLab이 남기는 증거까지 2분 45초 동안 따라가는 영상입니다. 일회용 Windows 11 VM 32대가 저마다 다른 실제 프로그램으로 릴리스 QA를 수행하는 장면으로 시작해, 테스트 하나가 처음부터 끝까지 진행되는 과정을 보여 줍니다.

시나리오 파일에는 Windows 템플릿, 실행할 빌드와 명령, 수집할 결과 파일, 통과 조건이 들어 있습니다. `oslab run` 한 번으로 OSLab은 Proxmox에서 VM을 복제하고, QEMU Guest Agent로 게스트에 접속해 빌드를 올려 실행합니다. 이어 출력을 검사한 뒤 VM을 삭제합니다. 터미널 출력 옆에는 이 실행이 만든 VM의 콘솔 화면이 함께 재생되고, 아래쪽 진행 막대에는 단계별 실제 소요 시간이 표시됩니다. 실행 폴더에는 로그, 원본·정규화 출력, JSON·JUnit·HTML 보고서가 남습니다.

이어서 로컬 웹 대시보드에서 다른 실행을 시작해 로그를 실시간으로 보고, 끝난 실행의 증거와 보고서를 엽니다. 그다음 Codex가 OSLab MCP 서버와 Proxmox 콘솔을 통해 Windows 데스크톱을 조작합니다. 메모장을 열어 한 줄을 입력하고 바탕 화면에 저장한 뒤 파일 탐색기에서 그 파일을 보여 줍니다. 그동안 호스트의 마우스와 키보드는 그대로 쓸 수 있고, QEMU Guest Agent가 저장된 파일을 확인합니다.

마지막 장은 다시 프로그램 32개로 돌아갑니다. LibreOffice Calc와 Visual Studio Code에서 문제를 찾고 고친 뒤 게스트 검사로 확인하는 과정을 보여 주고, 테스트 에이전트가 각 VM에 닿는 경로를 도식으로 설명합니다. 프로그램 8개를 더 보여 준 다음, 프로그램 32개 통과와 게스트 검사 140개 확인으로 마무리합니다.

## 장 구성

| 시간 | 장 | 화면 내용 |
| --- | --- | --- |
| 0:00–0:07 | 첫 장면 | VM 32대의 화면이 채워진 뒤 제목 |
| 0:07–0:19 | 01 시나리오 | 시나리오 YAML 전체를 보여 준 뒤 항목별로 확대 |
| 0:19–0:44 | 02 실행 | `oslab run` 출력과 그 실행이 만든 VM의 콘솔, 단계별 실제 소요 시간 |
| 0:44–0:57 | 03 증거 | 실행 폴더, HTML 보고서, assertion 결과 |
| 0:57–1:23 | 04 대시보드 | 웹 대시보드에서 시작한 실행, 실시간 로그, 증거 체크리스트와 보고서 |
| 1:23–1:54 | 05 AI 에이전트 | Codex가 OSLab MCP 서버로 메모장과 파일 탐색기를 조작한 뒤 게스트 검사 통과 |
| 1:54–2:38 | 06 규모 | 32대 화면, Calc와 VS Code 수정, 동작 원리, 프로그램 8개, 32개 모두 통과 |
| 2:38–2:45 | 마무리 | OSLab이 다루는 범위와 저장소 주소 |

## 실제 녹화와 편집

- **녹화 출처:** 02장과 03장은 CLI 실행 하나에서, 04장은 별도의 대시보드 실행에서, 05장은 별도 VM에서 진행한 Codex 세션에서 가져왔습니다. 첫 장면과 06장은 [32대 Windows QA 영상](#32대-windows-qa-영상)의 녹화본을 다시 썼습니다.
- **화면:** VM 콘솔은 각 실행이나 세션이 진행되는 동안 Proxmox 콘솔로 녹화한 30fps 영상입니다. HTML 보고서와 대시보드는 headless Chromium으로 녹화했고, 대시보드는 Playwright 스크립트가 조작했습니다.
- **다시 그린 패널:** YAML 패널은 이 저장소의 시나리오 파일을 그대로 조판했습니다. 터미널 패널은 녹화한 CLI 출력을 기록된 시각에 맞춰 재생하고, 명령을 입력하는 모습은 애니메이션입니다.
- **속도:** 기다리는 구간은 빠르게 재생하고, 녹화 화면이 나오는 장마다 현재 배속을 표시합니다. 02장의 진행 막대에는 실제 단계별 소요 시간이 나옵니다.
- **이름:** 터미널 텍스트, HTML 보고서, 대시보드에서 로컬 호스트 이름, 사용자 폴더, 비공개 변수 이름을 공개용 이름으로 바꿨습니다. VM ID와 실행 ID는 녹화된 그대로입니다.
- **커서:** 커서는 편집기가 기록된 포인터 위치에 그리고, 위치 사이의 이동은 보간합니다. 05장의 커서는 Codex가 호출한 MCP `move_mouse`와 `click`을 따르며, 녹화 화면에는 게스트 자체의 마우스 포인터도 보입니다.
- **판정:** PASS 표시는 `run.json`, assertion 결과, 게스트 검사 결과를 근거로 합니다. 실행이나 검사가 실패했다면 FAIL로 표시됩니다.
- **32대 화면:** VM은 최대 8대씩 묶어서 실행했고, 전체 화면은 녹화본마다 해당 작업의 시작 시점에 맞춰 배치했습니다. 처음에 커서가 빈 칸으로 날아드는 장면은 타이틀 애니메이션입니다. 모든 작업이 끝난 화면은 2초 동안 멈춰 보여 줍니다.
- **소리:** MP4에는 오디오 트랙이 없습니다.

## 제작 방법

영상은 네 종류의 녹화본으로 만듭니다. 캡처 스크립트마다 `edit_intro.py`가 읽는 폴더를 만들고, 스크립트가 만든 VM, 서버, 임시 파일은 스스로 정리합니다.

1. `capture_cli.py`는 `uv run --locked oslab run`으로 시나리오 하나를 실행하고 터미널 출력을 도착 시각과 함께 기록합니다. 실행이 만든 VM의 콘솔을 부팅부터 삭제까지 녹화하고, 실행 폴더를 복사한 뒤 `record_page.mjs`로 HTML 보고서를 녹화합니다. 비공개 이름을 대신할 공개용 이름은 `aliases.json`에 남깁니다.
2. `capture_dashboard.mjs`는 이 체크아웃에서 별도의 대시보드를 띄웁니다. API 포트, SQLite 데이터베이스, 웹 빌드를 따로 쓰므로 실행 중인 대시보드에는 영향을 주지 않습니다. headless Chromium으로 Run Launcher, 실시간 콘솔, Results Explorer를 차례로 조작하고, 녹화본과 포인터 동작, 주요 단계의 시각을 기록합니다. 대시보드는 경로에 `.local.`이 든 시나리오를 실행하지 않으므로, `scenarios/windows/qa-*.example.yaml`이나 `scenarios/<os>/private/` 아래 파일처럼 git에서 제외되는 다른 사본을 씁니다.
3. `capture_agent.py run`은 Windows 템플릿의 연결 복제본을 만들어 데스크톱에 로그인한 뒤, 중지 파일이 생길 때까지 콘솔을 녹화합니다. 그동안 Codex 같은 MCP 클라이언트가 OSLab MCP 도구로 VM을 조작하고 호출 기록을 `calls.json`에 남깁니다. `capture_agent.py check`는 QEMU Guest Agent로 저장된 파일을 읽어 `checks.json`을 씁니다.
4. `edit_intro.py`는 캡처 폴더 세 개와 32대 QA 실행의 출력 폴더를 읽어 1920×1080, 30fps의 `oslab-intro-film.mp4`를 만듭니다. `--preview`로 원하는 시점을 PNG로 먼저 확인할 수 있습니다. 최종 렌더링은 캡처가 하나라도 없으면 실패하고, `--receipt`는 인코딩한 사본의 검증 기록을 씁니다.

```powershell
$demo = 'validation/artifacts/intro-video'
$capture = "$env:TEMP/oslab-intro"
uv run --locked --extra computer-use python "$demo/capture_cli.py" --output "$capture/cli" `
    --scenario scenarios/windows/demo-powershell-system.local.yaml --artifact-path validation/artifacts/powershell-system `
    --config config/oslab.local.yaml --env-file config/oslab.local.env --lan-address 192.168.0.10 --ffmpeg ffmpeg
node "$demo/capture_dashboard.mjs" --out "$capture/dashboard" --scenario scenarios/windows/qa-demo-agent-steps.example.yaml `
    --artifact validation/artifacts/demo-agent-cli --ffmpeg ffmpeg
$agent = @('--config', 'config/oslab.local.yaml', '--env-file', 'config/oslab.local.env', '--work', "$env:TEMP/oslab-agent-capture",
    '--output', "$capture/agent", '--template-vmid', '9200', '--vmid-start', '9185', '--vmid-end', '9189', '--lan-address', '192.168.0.10')
uv run --locked --extra computer-use python "$demo/capture_agent.py" run @agent
# MCP 클라이언트가 작업을 마치고 calls.json을 쓴 뒤:
uv run --locked --extra computer-use python "$demo/capture_agent.py" check @agent
New-Item -ItemType File "$env:TEMP/oslab-agent-capture/stop.flag"
$edit = @('--captures', $capture, '--fleet', 'runs/windows-product-qa-demo', '--fonts', 'fonts/geist', '--out', "$capture/edit", '--ffmpeg', 'ffmpeg')
uv run --locked --extra computer-use python "$demo/edit_intro.py" @edit
```

공개용 파일은 원본을 2-pass H.264로 다시 인코딩해 GitHub 무료 플랜의 영상 한도인 10MB 아래로 맞췄습니다. 그래서 같은 파일을 README 영상 첨부로도 쓸 수 있습니다. `--receipt`는 그 옆에 검증 기록을 씁니다. 제출하지 않은 댓글 입력창에만 올린 첨부는 로그아웃한 방문자에게 404를 돌려주므로, README에 연결하기 전에 PR 설명에 첨부를 넣어 게시합니다.

```powershell
$encode = @('-y', '-i', "$capture/edit/oslab-intro-film.mp4", '-an', '-c:v', 'libx264', '-preset', 'slower',
    '-b:v', '450k', '-maxrate', '1100k', '-bufsize', '2200k', '-pix_fmt', 'yuv420p', '-x264-params', 'aq-mode=3')
ffmpeg @encode -pass 1 -f mp4 NUL
ffmpeg @encode -pass 2 -movflags +faststart docs/media/oslab-intro-film.mp4
uv run --locked --extra computer-use python "$demo/edit_intro.py" @edit --receipt docs/media/oslab-intro-film.mp4
```

## 검증 기록

[`oslab-intro-film-attestation.json`](media/oslab-intro-film-attestation.json)에는 CLI 실행과 단계별 소요 시간, 대시보드 실행, Codex 세션의 MCP 호출과 게스트 검사, 녹화본별 길이와 프레임 수, 32대 QA 실행의 집계, 위에 적은 편집 내용, 공개한 MP4의 SHA-256이 들어 있습니다. VM ID와 랩 호스트 이름은 넣지 않았습니다.

## 32대 Windows QA 영상

https://github.com/user-attachments/assets/52e5a594-a439-44a6-b461-f3e94d1c1c04

[1080p MP4 다운로드](https://raw.githubusercontent.com/hostkimjang/OSLAB/master/docs/media/oslab-windows-product-qa.mp4) · [검증 기록](media/oslab-windows-product-qa-attestation.json) · [재현 방법](windows-product-qa.ko.md#32대-영상-녹화)

이전에 만든 65초 영상은 06장 내용을 자세히 보여 줍니다. 일회용 Windows 11 VM 32대가 저마다 다른 실제 프로그램으로 릴리스 QA를 수행합니다. VM마다 QA 스크립트로 만든 테스트 에이전트가 MCP 도구 `screenshot`, `click`, `move_mouse`, `press_key`로 OSLab MCP 서버를 통해 화면을 조작하고, OSLab은 모든 결과를 게스트 안에서 확인합니다. 카메라는 LibreOffice Calc, OBS Studio, Visual Studio Code, 7-Zip을 차례로 확대하고, 도식으로 MCP 클라이언트에서 Proxmox 콘솔을 거쳐 게스트 검사까지 이어지는 경로를 보여 준 뒤, 프로그램 32개 통과와 검사 140개 확인으로 끝납니다.

모든 칸은 해당 VM을 끊김 없이 녹화한 콘솔 화면입니다. VM은 최대 8대씩 묶어 실행했고, 전체 화면은 녹화본마다 해당 작업의 시작 시점에 맞춰 배치했습니다. 실패한 시도는 다음 묶음에서 다시 실행했습니다. 첫 전체 화면은 8배속, 마지막 전체 화면은 약 10배속으로 재생하고, 에이전트 커서는 작업 기록에 남은 MCP 입력값으로 편집기가 그립니다. 이 영상은 `edit_video.py`가 만들고, 명령은 [32대 영상 녹화](windows-product-qa.ko.md#32대-영상-녹화)에 있습니다.
