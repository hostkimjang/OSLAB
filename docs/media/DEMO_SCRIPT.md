# README 데모 미디어 제작

README 상단의 릴리스 QA 영상은 실제 Proxmox Windows 게스트에서 캡처한 화면을 사용합니다.

## 구성

### 실제 Windows 프로그램으로 릴리스 QA

[실행 가이드](../windows-product-qa.ko.md#readme-영상-녹화)에 따라 `fleet.py`로 일회용 Windows 11 VM 32대에서 릴리스 QA를 실행하고, VM마다 콘솔 화면을 30fps로 녹화합니다. 결과는 MCP 화면과 별도로 QGA로 읽어 온 파일, 해시, 데이터베이스, 미디어 정보로 검증합니다. 장면 구성과 편집 범위는 [소개 영상 문서](../intro-video.ko.md)에 정리했습니다.

1. 첫 장면은 녹화본 32개를 각 작업의 시작 시점에 맞춰 8열로 배치하고 8배속으로 재생합니다. 처음에 에이전트 커서가 빈 칸으로 날아드는 부분은 타이틀 애니메이션입니다. 그 뒤로 커서는 `case-*.json`에 기록된 MCP 클릭 위치와 시각을 따르고, 클릭 사이 경로는 보간합니다.
2. 확대 장면에는 Calc의 판정표 수정, OBS의 로컬 녹화, VS Code 설정 수정, 7-Zip의 압축 복원을 담습니다. FOUND와 PASS 표시는 각 단계가 기록된 시각에 맞춥니다.
3. 몽타주 두 장면에서 프로그램 8개를 더 보여 줍니다. 마지막 전체 화면의 통과 수와 검사 수는 통과 기록에서 집계합니다.

공개 전에 README용 MP4를 디코딩해 재생을 확인하고, 공개 결과 JSON에 그 파일의 SHA-256을 기록합니다. README의 플레이어는 PR 설명에 올린 GitHub 첨부 주소를 쓰고, 같은 파일을 `docs/media`에도 둡니다.

### Windows 앱 매트릭스

[매트릭스 실행 가이드](../windows-app-matrix.ko.md)에 따라 앱을 번들링하고 Windows 11 VM에서 실행합니다. 웹 예제 앱과 네이티브 Windows 앱 모두 OSLab MCP로 화면을 캡처하고 입력을 보냅니다. 게스트 파일 또는 UI Automation에서 확인한 기대값과 관찰값을 `case-*.json`에 남깁니다.

1. 첫 장면은 실제 게스트 화면을 골라 배치 번호와 함께 보여 줍니다.
2. 동시 실행 장면은 같은 배치에서 캡처 시간이 겹치는 VM 화면을 한 시간축에 맞춰 배치합니다.
3. 확대 장면에서는 입력, 검출한 결함, 수정 결과를 보여 줍니다. 클릭 강조는 MCP가 전송한 실제 좌표를 사용합니다.
4. 전체 앱 목록에는 각 화면의 원래 배치 번호를 표시합니다.

원본 PNG에서 작업 표시줄 등 불필요한 영역을 제외하고 합성합니다. 공개 전 미디어를 디코딩하고, 촬영 배치·검증 결과·파일 해시·정리 결과를 결과 기록과 대조합니다. 원본 PNG와 랩 내부 식별자는 공개 저장소에 포함하지 않습니다.

### 소개 애니메이션

`apps/web/scripts/oslab-marketing.html`을 브라우저에서 결정적으로 렌더링합니다. OSLAB의 디자인 토큰과 아이콘을 사용해 다음 흐름을 보여 줍니다.

1. 하나의 시나리오가 반복 가능한 검증 증거로 이어진다는 핵심 메시지
2. YAML 시나리오와 VM 상태 정의
3. Clone, Prepare, Upload, Execute 실행 단계
4. PASS 결과와 JSON, JUnit, HTML 보고서

화면에는 `ILLUSTRATED DEMO · NO VM CREATED`를 고정해 실제 VM 실행 장면으로 오해되지 않도록 합니다. 원본은 1280×720 크기로 녹화됩니다.

### Web Dashboard 데모

`apps/web/scripts/capture-readme-demo.mjs`가 로컬 Next.js 서버를 열고 실제 Dashboard 화면을 Playwright로 조작합니다. 데모는 다음 사용자 흐름을 담습니다.

1. Dashboard에서 lab 준비 상태 확인
2. Scenario Builder에서 Windows 시나리오와 YAML 확인
3. Run 화면에서 시나리오와 PowerShell artifact 선택
4. 실행 로그와 단계별 상태 변화 확인
5. Results에서 PASS 결과와 evidence 확인

브라우저 안의 API 응답, 로그, 시간, VM ID와 node 이름은 촬영 스크립트가 제공하는 고정 fixture입니다. Proxmox나 실제 VM에는 연결하지 않습니다. 캡처 context는 `serviceWorkers: "block"`로 service worker를 차단합니다. HTTP는 OS가 고른 동적 localhost 캡처 포트, 로컬 API 포트와 스크립트가 직접 응답하는 Monaco asset만 허용하고 나머지는 중단·기록한 뒤 캡처 전체를 실패 처리합니다. WebSocket은 같은 캡처 포트의 HMR 연결만 서버에 이어 주고, 그 밖의 연결은 code 1008로 닫아 기록한 뒤 실패 처리합니다. EventSource는 고정된 로컬 구현으로 교체합니다. 캡처 서버는 `output/readme-media/` 아래의 임시 작업공간과 독립된 `.next`를 사용하고 종료할 때 제거하므로, 개발 서버의 port나 build 결과와 공유하지 않습니다. 커서 이동과 클릭은 접근성 선택자로 찾은 실제 요소 위치를 기준으로 연출하며, 화면 밖의 대상은 페이지를 부드럽게 스크롤해 찾습니다. 원본은 1280×800 크기로 녹화됩니다.

### 단계별 실행 워크플로우

`apps/web/scripts/oslab-run-workflow.html`은 `oslab run`을 실행했을 때 책임이 이동하는 순서를 10단계로 보여 줍니다.

1. CLI 실행 요청
2. 시나리오 검증과 lab preflight
3. Proxmox API를 통한 VM 복제
4. 일회용 VM 부팅
5. QEMU Guest Agent 준비
6. Fixture 적용
7. Artifact 전송
8. 테스트 실행과 assertion
9. JSON, JUnit, HTML 증거 생성
10. VM 삭제와 VMID 반환

이 영상도 고정 데이터로 만든 설명용 애니메이션이며 실제 Proxmox에 접속하지 않습니다. 화면에는 `ORCHESTRATED DEMO · NO PROXMOX CONTACTED`를 항상 표시합니다.

### 실제 Proxmox와 Windows VM 화면

`oslab-live-lab` 미디어는 실제 Proxmox 기반 Windows 복제 VM에서 통과한 PowerShell 데모를 바탕으로 합니다. 실제 촬영은 다른 VM이 없는 전용 범위를 사용하거나, 공개 전 다음 영역을 반드시 잘라낸 뒤 진행합니다.

- 다른 VM과 storage가 보이는 resource tree
- 실제 node 이름, 계정 이름, API 주소와 IP 주소
- 다른 사용자의 task history와 운영 로그
- 로컬 경로, 비밀 값, VM 안의 개인 정보

현재 공개 영상은 실제 Proxmox의 `Clone`/`Start` task와 실행 중 CPU 그래프, Windows 11 부팅 콘솔, 실제 게스트 PowerShell 데스크톱을 사용합니다. 인프라와 부팅 화면은 기존 통과 run의 촬영분이고, PowerShell 화면은 현재 Windows template을 별도로 검증한 통과 run의 촬영분입니다. 부팅 콘솔은 guest가 화면을 제공한다는 사실만 보여 주며, QGA 진행 패널은 run evidence에서 만든 오버레이이지 guest 터미널 촬영이 아닙니다. 이후 PowerShell 장면은 실제 guest 픽셀로 전달된 artifact, `exitCode: 0`, Windows 11 정보와 운영자가 결과 확인 후 출력한 `OSLAB-DEMO-PASS` 표식을 보여 줍니다.

원본 화면은 `output/readme-media/live-capture/`에만 두고 Git에는 포함하지 않습니다. Proxmox task 원본 crop에는 촬영용 일회성 VMID가 픽셀로 남아 있을 수 있으므로 원본을 그대로 공개하지 않습니다. 합성 화면에서는 해당 영역을 public alias로 가리고, CPU 그래프·Windows 부팅 콘솔·PowerShell guest 픽셀은 실제 캡처를 유지합니다.

`capture-live-lab.mjs`는 다음 승인 절차를 통과한 입력만 받아 1280×720 영상으로 합성합니다.

1. Git에서 제외된 `output/readme-media/live-capture/source-approval.json`에 crop 이미지 네 장의 SHA-256을 기록합니다.
2. 같은 파일에서 `checks.infrastructureSourcesReviewed`, `checks.guestPowerShellMatchesRun`, `checks.sensitiveRegionsReviewed`, `checks.cleanupVerified`가 모두 `true`인지 확인합니다. 인프라 촬영 run과 PowerShell 검증 run의 `run.json`, PowerShell의 normalized command result도 각각 SHA-256으로 고정합니다.
3. 합성 후 전체 프레임을 수동 검수하고 `docs/media/oslab-live-lab-attestation.json`에 최종 MP4·GIF·poster hash, 두 run evidence hash, PowerShell 검증 요약, `cleanup.resourceAbsent: true`, `privacy.manualPublicFrameReview: true`를 남깁니다.

촬영용 VM은 이름과 VMID를 다시 확인한 뒤 중지·삭제하고, resource가 실제로 사라진 것을 확인한 경우에만 `cleanupVerified`와 공개 attestation을 승인합니다.

### Dashboard → 실제 lab → Results 3막 합성본

`apps/web/scripts/compose-readme-end-to-end.mjs`는 이미 검수한 `oslab-dashboard-demo.mp4`와 `oslab-live-lab.mp4`만 읽어 다음 편집 순서로 합성합니다.

1. Dashboard 0–13.2초: scenario 준비와 실행 시작
2. Live lab 0–22.4초: 실제 sanitized Proxmox, QGA, Windows PowerShell
3. Dashboard 22.6–27.52초: PASS 결과와 evidence 복귀

두 전환은 0.32초 crossfade를 사용합니다. Dashboard 원본은 1280×800을 유지하고, 1280×720 live lab은 위아래 40px padding을 넣어 1280×800으로 배치합니다. Dashboard 구간에는 `ACTUAL DASHBOARD UI · FIXTURE DATA · NO PROXMOX CONTACTED`, live lab에는 `SEPARATELY CAPTURED LIVE LAB FOOTAGE · NOT ONE CONTINUOUS RUN`을 항상 표시합니다. 따라서 실제 Dashboard UI가 fixture 응답으로 움직이는 장면과 별도로 촬영한 live lab이 하나의 연속 실측 run으로 오인되지 않습니다.

Compositor는 두 입력의 고정 SHA-256, 해상도·코덱·오디오 부재, live lab의 공개 alias·privacy·cleanup attestation을 먼저 검사합니다. private crop이나 local 승인 manifest는 직접 읽지 않습니다. 결과 계약은 `docs/media/oslab-end-to-end-demo-attestation.json`에 기록하며, README에 연결하기 전 전체 타임라인·전환 경계·GIF·poster를 독립적으로 검수하고 `review.fullFrameReview`와 검수 방법을 함께 기록합니다.

이 3막 합성본은 source 비교와 이전 편집 재현을 위해 보존합니다. README의 대표 영상은 아래 step-by-step 통합본입니다.

### README step-by-step 대표 통합 영상

`apps/web/scripts/compose-readme-step-by-step.mjs`는 Dashboard, workflow explainer와 실제 lab을 시간축에 맞게 교차 편집합니다.

1. 전체 편집 구성을 밝히는 2.2초 title card
2. Dashboard에서 scenario, 실행 옵션과 Run Launcher 확인
3. Request·preflight·clone·boot 설명 뒤 실제 Proxmox clone/start 화면
4. QGA·fixture·artifact 설명 뒤 실제 Windows 콘솔과 evidence 기반 QGA trace
5. Test·assertion·evidence 설명 뒤 실제 guest PowerShell과 PASS 화면
6. Cleanup 설명과 실제 lab 요약 뒤 Dashboard Results Explorer의 fixture evidence `7/7` 복귀

초기 편집본은 단계당 실제 가독 시간이 약 1.76초였고, workflow와 live source의 자체 fade 경계에 0.24초 합성 crossfade가 겹쳐 일부 장면이 건너뛰는 것처럼 보였습니다. 현재 편집은 source 자체 fade 밖의 안정 프레임에서 자르고, workflow 설명 구간을 0.75배속으로 늘립니다. 장면 전환은 0.55초 fade-through-black 10회로 구분하고, 실제 lab 요약과 최종 Results에는 각각 1초와 1.5초 정지 여백을 둡니다.

각 장면은 시작 후 약 2.65초 동안 현재 단계와 화면의 의미를 설명하는 lower-third를 표시합니다. 상단에는 `FIXTURE DASHBOARD`, `WORKFLOW EXPLAINER · FIXTURE DATA`, `REAL LAB · SEPARATE CAPTURE`, `FIXTURE RESULTS`처럼 짧은 출처 badge만 유지합니다. workflow source의 공개 template·VM 식별자는 Dashboard와 동일한 `9200`·`9102`입니다. 최종 영상은 66.44초, 1280×800, 25fps H.264 무음이며 GIF는 720×450, 6fps, 64색으로 생성합니다.

인접 장면은 하나의 사용자 흐름을 설명할 뿐 동일 run이나 동일 결과 레코드임을 뜻하지 않습니다. source bytes·SHA-256, title을 포함한 11개 EDL, 10개 전환, 재생 속도와 정지 여백, live attestation과 cleanup 상속, 최종 output hash는 `oslab-step-by-step-demo-attestation.json`에 기록합니다.

## 원본 캡처

Node.js 의존성을 설치한 뒤 저장소 루트에서 실행합니다.

```powershell
corepack pnpm install --frozen-lockfile
corepack pnpm --filter @oslab/web exec playwright install chromium
corepack pnpm --filter @oslab/web run readme:overview:capture
corepack pnpm --filter @oslab/web run readme:workflow:capture
corepack pnpm --filter @oslab/web run readme:dashboard:capture
```

Git에서 제외된 `output/readme-media/`에 다음 원본이 생성됩니다.

- `oslab-overview.webm`
- `oslab-run-workflow.webm`
- `oslab-dashboard-demo.webm`

실제 lab 합성은 먼저 공개 검사를 통과한 다음 파일을 준비한 경우에만 실행합니다.

```powershell
corepack pnpm --filter @oslab/web run readme:live:capture
```

필요한 로컬 전용 입력은 `proxmox-task-crop.png`, `proxmox-cpu-crop.png`, `windows-vm-console-crop.png`, `windows-vm-powershell-crop.png`, `source-approval.json`입니다. 입력·run evidence·normalized result hash가 승인 파일과 다르거나 필수 확인 값이 하나라도 `true`가 아니면 실제 lab 합성 명령은 의도적으로 실패해야 합니다.

Dashboard, workflow와 live lab 공개 MP4가 준비된 뒤 README 대표 영상을 생성합니다.

```powershell
corepack pnpm --filter @oslab/web run readme:step-by-step:compose
```

통합 스크립트는 MP4, GIF, poster, attestation과 `output/readme-media/oslab-step-by-step-demo-contact-sheet.png`를 함께 생성합니다.

캡처 스크립트가 오류로 끝나면 결과물을 공개 파일로 변환하지 않습니다. 특히 브라우저 콘솔 오류, 알 수 없는 API 요청, 외부 네트워크 요청 또는 공개 금지 문자열 검사가 실패한 경우 원인을 먼저 해결합니다.

## MP4, GIF와 포스터 만들기

아래 명령은 저장소 루트에서 ffmpeg 7.x로 실행합니다. MP4는 GIF를 클릭했을 때 볼 수 있는 고화질 원본이고, GIF는 GitHub README 안에서 바로 재생되는 미리보기입니다.

### 소개 애니메이션

```powershell
ffmpeg -y -i output/readme-media/oslab-overview.webm -an -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p -movflags +faststart docs/media/oslab-overview.mp4
ffmpeg -y -ss 00:00:15.6 -i docs/media/oslab-overview.mp4 -frames:v 1 -update 1 docs/media/oslab-overview-poster.png
ffmpeg -y -i docs/media/oslab-overview.mp4 -vf "fps=8,scale=800:-2:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" -loop 0 docs/media/oslab-overview.gif
```

### Web Dashboard 데모

```powershell
ffmpeg -y -i output/readme-media/oslab-dashboard-demo.webm -an -c:v libx264 -preset slow -crf 21 -pix_fmt yuv420p -movflags +faststart docs/media/oslab-dashboard-demo.mp4
ffmpeg -y -ss 00:00:26.2 -i docs/media/oslab-dashboard-demo.mp4 -frames:v 1 -update 1 docs/media/oslab-dashboard-demo-poster.png
ffmpeg -y -i docs/media/oslab-dashboard-demo.mp4 -vf "fps=8,scale=800:-2:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" -loop 0 docs/media/oslab-dashboard-demo.gif
```

### 단계별 실행 워크플로우

```powershell
ffmpeg -y -i output/readme-media/oslab-run-workflow.webm -an -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p -movflags +faststart docs/media/oslab-run-workflow.mp4
ffmpeg -y -ss 00:00:21.5 -i docs/media/oslab-run-workflow.mp4 -frames:v 1 -update 1 docs/media/oslab-run-workflow-poster.png
ffmpeg -y -i docs/media/oslab-run-workflow.mp4 -vf "fps=8,scale=800:-2:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" -loop 0 docs/media/oslab-run-workflow.gif
```

### 실제 lab 합성 영상

```powershell
ffmpeg -y -i output/readme-media/oslab-live-lab.webm -an -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p -movflags +faststart docs/media/oslab-live-lab.mp4
ffmpeg -y -ss 00:00:23.2 -i docs/media/oslab-live-lab.mp4 -frames:v 1 -update 1 docs/media/oslab-live-lab-poster.png
ffmpeg -y -i docs/media/oslab-live-lab.mp4 -vf "fps=8,scale=800:-2:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" -loop 0 docs/media/oslab-live-lab.gif
```

### Dashboard와 실제 lab 통합 영상

구간 선택, disclosure label, crossfade, 1280×800 정규화, MP4/GIF/poster/contact sheet 생성을 한 명령에서 재현합니다.

```powershell
corepack pnpm --filter @oslab/web run readme:end-to-end:compose
```

### README step-by-step 대표 통합 영상

Dashboard, 10단계 workflow, 실제 lab과 Results 복귀를 시간축에 맞게 한 영상으로 생성합니다.

```powershell
corepack pnpm --filter @oslab/web run readme:step-by-step:compose
```

공개 파일은 영상마다 MP4, GIF, poster PNG 세 개씩 생성합니다.

- `docs/media/oslab-overview.mp4`
- `docs/media/oslab-overview.gif`
- `docs/media/oslab-overview-poster.png`
- `docs/media/oslab-dashboard-demo.mp4`
- `docs/media/oslab-dashboard-demo.gif`
- `docs/media/oslab-dashboard-demo-poster.png`
- `docs/media/oslab-run-workflow.mp4`
- `docs/media/oslab-run-workflow.gif`
- `docs/media/oslab-run-workflow-poster.png`
- `docs/media/oslab-live-lab.mp4`
- `docs/media/oslab-live-lab.gif`
- `docs/media/oslab-live-lab-poster.png`
- `docs/media/oslab-live-lab-attestation.json`
- `docs/media/oslab-end-to-end-demo.mp4`
- `docs/media/oslab-end-to-end-demo.gif`
- `docs/media/oslab-end-to-end-demo-poster.png`
- `docs/media/oslab-end-to-end-demo-attestation.json`
- `docs/media/oslab-step-by-step-demo.mp4`
- `docs/media/oslab-step-by-step-demo.gif`
- `docs/media/oslab-step-by-step-demo-poster.png`
- `docs/media/oslab-step-by-step-demo-attestation.json`

README에서는 GIF를 이미지로 표시하고 같은 GIF에 MP4 링크를 겁니다. 포스터는 영상 검토, 공유 카드 또는 GIF가 재생되지 않는 환경의 대체 이미지로 사용할 수 있습니다. 실제 lab attestation은 최종 파생 파일과 검수·정리 증거를 함께 확인하기 위한 공개 메타데이터입니다.

```markdown
[![OSLAB complete step-by-step walkthrough](docs/media/oslab-step-by-step-demo.gif)](docs/media/oslab-step-by-step-demo.mp4)
```

## 공개 안전 규칙

- 실제 계정, API token, 쿠키, 비밀번호와 환경 변수 값을 촬영하지 않습니다.
- 실제 Proxmox 주소, node 이름, template 이름과 사설 IP를 공개하지 않습니다. 실제 task crop의 일회성 VMID는 원본에 남을 수 있으므로 Git에서 제외하고, 공개 합성본에서는 public alias로 가린 뒤 프레임 단위로 확인합니다.
- `C:\Users\...`, `/Users/...` 같은 로컬 사용자 경로와 사내 경로를 화면이나 로그에 남기지 않습니다.
- 실제 scenario, run, artifact와 운영 로그를 fixture로 복사하지 않습니다. 공개용 이름과 최소한의 고정 값으로 새로 작성합니다.
- 브라우저 시각과 실행 상태를 고정해 촬영할 때마다 같은 순서와 결과가 나오게 합니다.
- Dashboard 캡처는 `serviceWorkers: "block"`을 사용하고, HTTP는 동적 localhost 캡처 포트·로컬 API 포트·로컬에서 응답하는 Monaco asset만 허용합니다. WebSocket은 캡처 포트의 HMR만 연결하며 나머지는 code 1008로 닫고, 차단 기록이 하나라도 있으면 캡처를 실패 처리합니다. EventSource는 고정 mock으로 교체합니다.
- 소개 애니메이션은 실제 실행이 아닌 연출임을 표시하고, Dashboard 영상은 mock 응답만 사용합니다.
- 실제 lab 영상은 전용 촬영 run만 사용하고, resource tree·node·계정·IP·다른 작업 내역을 crop한 뒤 승인 hash와 수동 전체 프레임 검사를 다시 수행합니다.
- Windows 부팅 콘솔은 guest 부팅 확인 자료로만 설명합니다. QGA 패널은 run evidence 기반 trace임을 표시하고, 실제 PowerShell 화면은 별도 guest 캡처임을 명시합니다.
- PowerShell 캡처의 `OSLAB-DEMO-PASS`는 명령 결과를 확인한 운영자 표식이며, artifact 자체가 출력한 문자열로 설명하지 않습니다.
- 실제 lab 촬영을 위해 남긴 VM은 영상 확보 직후 정확한 이름과 VMID를 확인한 다음 정리합니다.
- Step-by-step 통합본은 검수된 공개 MP4만 읽고, Dashboard fixture·workflow explainer·별도 live lab·fixture Results 경계를 모든 프레임에 disclosure label로 표시합니다.
- PASS 장면은 제품의 모든 기능이나 환경에서 성공을 보장한다는 뜻이 아니라, 공개용 고정 데모 흐름의 결과임을 전제로 합니다.

## 공개 전 확인

- 소개 애니메이션 첫 장면에서 프로젝트 이름과 핵심 메시지가 바로 읽히는지 확인합니다.
- Dashboard의 글자, 선택 값, 실행 로그와 evidence가 800px 너비 GIF에서도 식별 가능한지 확인합니다.
- 커서가 대상에 도착한 뒤 클릭 표시가 나오고, 스크롤 과정에서 핵심 UI가 잘리지 않는지 확인합니다.
- README의 두 대표 영상과 보존한 source 미디어에 흰 화면, 로딩 실패, 콘솔 오류와 갑작스러운 화면 전환이 없는지 확인합니다.
- 고정 데모 표기와 공개용 node, VM, artifact 이름이 끝까지 유지되는지 확인합니다.
- MP4에 오디오 트랙이 없고, H.264와 `yuv420p`로 인코딩되었는지 확인합니다.
- GIF 크기가 저장소에 적합한지 확인하고, 너무 크면 해상도보다 우선 프레임 수와 색상 수를 낮춥니다.
- README의 GIF와 MP4 상대 링크를 GitHub에서 열어 봅니다.
- 실제 lab 파생 파일 hash가 `oslab-live-lab-attestation.json`과 일치하고, `privacy.manualPublicFrameReview` 및 `cleanup.resourceAbsent`가 `true`인지 확인합니다.
- 대표 통합 영상의 source/output hash가 `oslab-step-by-step-demo-attestation.json`과 일치하고, 1초 간격 전체 타임라인과 전환 10개, title card, lower-third를 독립 검수한 뒤 `review.fullFrameReview`와 검수 방법을 갱신했는지 확인합니다.
- `scripts/check-public-release.ps1 -IncludeUntracked`와 최종 secret scan을 다시 실행합니다.
