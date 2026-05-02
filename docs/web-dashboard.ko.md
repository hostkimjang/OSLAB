# oslab Web Dashboard

Web dashboard는 `oslab`을 LAN/team 환경에서 더 편하게 쓰기 위한 control surface입니다. Python runner를 새로 대체하지 않습니다. 기존 CLI command를 감싸고, job history는 SQLite에 저장하며, 시나리오(Scenario), 실행 묶음(Suite), 환경 준비 스크립트(Fixture) 정의는 Git-friendly file로 유지합니다.

## Architecture

```text
apps/web   Next.js dashboard
apps/api   NestJS API, local auth, job runner, file/catalog API
oslab CLI  uv run oslab run / suite-run
runs/      기존 run output layout
```

첫 화면은 작업용 dashboard입니다. 최근 작업, 최근 실행 결과, 시나리오 작성, 실행 묶음 실행, 실시간 로그, 결과 리포트를 바로 볼 수 있게 구성합니다.

현재 소스 구조는 다음처럼 정리했습니다.

```text
apps/web/src/
  app/
    page.tsx                # thin entrypoint
  features/dashboard/
    DashboardPage.tsx       # stateful dashboard controller
    components/
      authoring.tsx
      common.tsx
      lab-status.tsx
      results.tsx
    lib/
      api.ts
      commands.ts
      formatting.ts
      result-summary.ts
      ui-state.ts
    sections/
      DashboardHome.tsx
      LoginScreens.tsx
      ResultsExplorer.tsx
    model.ts                # compatibility barrel
    defaults.ts
    i18n.ts
    types.ts

apps/api/src/
  app.module.ts
  common/guards/
  infrastructure/prisma/
  infrastructure/workspace/
  features/auth|artifacts|builder|catalog|files|jobs|lab|runs|validation/
    *.module.ts
    *.controller.ts
    dto/
    lab/proxmox-lab.client.ts  # Lab Status/cleanup용 Proxmox HTTP 정책
```

## Setup

서버 실행, LAN 접근, production-like start command, smoke check, troubleshooting은 [Web Dashboard 서버 실행 가이드](web-dashboard-server.ko.md)를 봅니다.

Node dependency 설치:

```powershell
corepack pnpm install
```

API/Web 환경 파일 생성:

```powershell
Copy-Item apps/api/.env.example apps/api/.env
Copy-Item apps/web/.env.example apps/web/.env
```

최소한 아래 값은 설정합니다.

```text
OSLAB_REPO_ROOT=C:/Users/kysky/Documents/gitlab/product-specific_autorun_test
OSLAB_WEB_ADMIN_USERNAME=admin
OSLAB_WEB_ADMIN_PASSWORD=<strong-password>
```

Prisma client 생성:

```powershell
corepack pnpm prisma:generate
```

API는 시작 시 local SQLite table이 없으면 자동 생성합니다. v1 development dashboard에서는 별도 Prisma migration step이 필요하지 않습니다.

Dashboard 실행:

```powershell
corepack pnpm dev
```

`pnpm`이 PATH에 잡혀 있다면 `pnpm dev`도 동작합니다. Windows에서는 global Corepack shim 활성화에 관리자 권한이 필요할 수 있으므로 `corepack pnpm ...`을 권장합니다.

Next.js dev server를 켜둔 상태에서 production build를 실행한 뒤 stale runtime error가 보이면 `corepack pnpm dev`를 중지하고 `apps/web/.next`를 삭제한 다음 다시 실행하세요.

기본 URL:

```text
API: http://127.0.0.1:3001
Web local URL: http://127.0.0.1:3000
Web bind: 0.0.0.0:3000
```

## Safety

- 시나리오(Scenario), 실행 묶음(Suite), 환경 준비 스크립트(Fixture) 편집은 `scenarios/**`, `validation/fixtures/**`, `validation/suites/**`로 제한됩니다.
- Authoring API는 read뿐 아니라 create/write에서도 root와 extension 정책을 강제합니다. Scenario/Suite는 `.yaml/.yml`, Fixture는 `.ps1/.sh`만 허용하고, env/secret 성격의 경로는 차단합니다.
- Artifact text authoring은 Artifact Studio에서 `validation/artifacts/**/*.{ps1,sh,py,c,json,txt,cmd,bat}`로 제한됩니다. `.web-artifacts/**`, binary 파일, directory artifact는 실행 선택/read-only만 허용합니다.
- Artifact archive/delete는 2단계 confirm 흐름입니다. `validation/artifacts/**` repo artifact는 직접 삭제하지 않고 `.artifact-archive/**`로 먼저 보관하며, `.web-artifacts/**`와 `.artifact-archive/**`만 confirm 후 삭제할 수 있습니다.
- Artifact Studio의 Script Assist는 스크립트를 실행하지 않습니다. 자동완성/진단은 API의 LSP Assist 표면을 통해 제공하며, JSON parse, placeholder 오타, 위험 경로 힌트, 파괴적 명령 패턴 같은 정적 검사만 수행합니다.
- 파일 authoring 화면은 기본 `읽기 전용`입니다. `수정` 버튼을 누른 뒤에만 YAML/PowerShell 내용을 바꿀 수 있고, `저장` 또는 `취소` 후 다시 읽기 전용으로 돌아갑니다.
- 수정된 내용은 저장 전에 변경/추가/삭제 line count와 상위 변경 preview를 표시합니다.
- 저장 전 현재 editor buffer 기준으로 YAML/PowerShell 문법을 검사합니다. 정상/검증중 상태는 레이아웃을 밀지 않는 toast로 표시하고, 문법 오류만 inline으로 남겨 `저장` 버튼을 차단합니다.
- 시나리오 저장은 파일 쓰기 전에 가벼운 scenario 계약 검증도 수행합니다. 잘못된 `schemaVersion`, OS 계열, guest mode, report format, cleanup 타입, assertion 누락은 대시보드에서 저장을 차단합니다.
- 실행 묶음 저장도 파일 쓰기 전에 가벼운 suite 계약 검증을 수행합니다. 빈 runs, 중복 run id, 잘못된 scenario path, 잘못된 `tier`/`allowFailure` 형태는 대시보드에서 저장을 차단합니다.
- 새 시나리오/환경 준비/실행 묶음 생성은 create-only입니다. API는 이미 존재하는 authoring 파일을 덮어쓰지 않습니다.
- 저장하지 않은 변경이 있는 상태에서 다른 파일을 열면 discard confirm을 표시합니다.
- Env file은 Web API로 읽을 수 없습니다.
- Job log는 선택된 env file에서 secret-like value를 읽어 redaction합니다.
- 실행은 `uv run oslab suite-run ...` 같은 subprocess로 처리합니다.
- Lab cleanup은 2단계로 동작합니다. API가 먼저 dry-run 후보와 `confirmToken`을 반환하고, 같은 후보군에 대한 토큰이 확인될 때만 실제 삭제를 요청합니다.
- Dashboard cleanup 기본 대상은 configured VMID range 안의 stopped/stale `oslab-*` VM입니다. running VM은 기본 UI cleanup 대상에서 제외합니다.
- Web dev/start server는 `0.0.0.0:3000`에 bind되어 같은 host의 모든 인터페이스에서 listen합니다. 브라우저 접속은 로컬에서는 `http://127.0.0.1:3000`, LAN에서는 `http://<dashboard-host-ip>:3000`처럼 실제 host/IP를 사용합니다.
- LAN에서 실시간 job event나 대용량 artifact upload까지 확인하려면 API도 LAN에서 접근 가능해야 합니다. `apps/api/.env`의 `OSLAB_WEB_HOST`를 `0.0.0.0`으로 바꾸고, `OSLAB_WEB_ORIGIN`은 실제 Web origin 예: `http://<dashboard-host-ip>:3000`에 맞춥니다.
- LAN 접근을 열 때는 OS 방화벽, 사설망 범위, 계정/password, reverse proxy 정책을 같이 확인합니다.

## Current V1 Features

- Local account login
- English/Korean language switch
- 정보 밀도가 높은 card/section header와 선택된 evidence row에 원형 `i` tooltip 추가
  - hover, focus, click/tap으로 열림
  - `Esc`, focus out, outside click으로 닫힘
  - viewport 밖으로 잘리지 않도록 portal/fixed 위치와 mobile clamp 적용
  - Scenario, 환경 준비(Fixture), 실행 묶음(Suite), 실행 준비, Suite 정책, `run.json`/`progress.jsonl` 같은 증거 파일을 사용자 관점 설명으로 안내
- Main workspace의 로그아웃 action
- `랩 상태(Lab Status)` read-only view
  - Proxmox API 연결 상태
  - Proxmox 요청은 Python provider와 같은 `oslab/0.1.0` user agent 정책을 사용해 reverse proxy/WAF 환경에서도 client signature를 안정화
  - node/template 상태
  - VMID range used/free/recommended
  - running/stale `oslab-*` VM
- 시나리오(Scenario), 실행 묶음(Suite), 환경 준비 스크립트(Fixture) 목록 탐색
- 긴 시나리오/환경 준비 스크립트 목록을 위한 검색/filter
- Scenario/Fixture/Suite 작성 화면의 파일 목록을 52px rail로 접어 YAML/PowerShell 본문 공간을 넓힐 수 있음
- 허용된 YAML/PowerShell file 읽기와 gated editing
- 시나리오/실행 묶음/환경 준비 스크립트 저장 전 diff preview는 저장 전에 viewport 약 90% modal로 열리고, editor 안에는 변경/추가/삭제 compact 요약만 남김
- 시나리오/실행 묶음 YAML과 PowerShell Fixture 저장 전 문법 검사
- 시나리오/실행 묶음 validation
- Windows smoke, Linux smoke, product-specific smoke 템플릿 기반 새 시나리오 생성
- Windows PowerShell 또는 Linux shell 템플릿 기반 새 환경 준비 생성
- Smoke 또는 Matrix starter 템플릿 기반 새 실행 묶음 생성. 생성된 파일은 편집 상태로 열리고 Suite Builder가 바로 로드됩니다.
- Local artifact path 기반 시나리오/실행 묶음 launch
- `실행 묶음 없음` 또는 `시나리오 없음` 선택을 통한 단일 scenario/suite-only 실행 흐름 분리
- 단일 scenario는 artifact path를 비워두면 skeleton run으로 실행 가능
- `validation/artifacts` catalog 기반 Artifact 선택
- 선택한 시나리오와 현재 catalog를 기준으로 한 추천 Artifact chip
- `직접 입력 - 파일/폴더 경로` 선택 시 Web에서 artifact path 직접 입력. 제품 `bin/Release` 같은 dashboard 서버가 접근 가능한 절대 디렉터리 경로도 허용
- 브라우저에서 artifact 파일을 `.web-artifacts/`로 업로드하고 현재 실행 경로로 즉시 선택
- 브라우저 폴더 선택 지원: 선택한 폴더를 `.web-artifacts/<timestamp>-<folder>/` 아래로 복사한 뒤, 생성된 서버 로컬 디렉터리를 현재 실행 artifact로 선택
- 큰 브라우저 업로드는 Next rewrite proxy를 거치지 않고 API server `:3001`로 직접 전송해, 브라우저 전송률이 100%가 된 뒤 multipart proxy에서 실패하는 문제를 피함
- 직접 업로드 상태 표시: 선택됨/업로드 중/사용 중/실패, 파일 수, 바이트 진행률, 저장된 `.web-artifacts/...` 경로를 표시
- 좌측 메뉴의 `아티팩트` 화면에서 Artifact Studio를 직접 열 수 있음
- Artifact Studio는 `validation/artifacts/**`, `.web-artifacts/**`, `.artifact-archive/**`를 source/type/size/hash와 함께 통합 표시하고, Run Launcher의 `테스트 파일 관리`에서도 같은 화면을 modal로 사용
- Artifact Studio는 단일 파일, 폴더형 프로젝트, product-specific starter를 create-only 방식으로 생성
- Artifact Studio의 `새 아티팩트 제작`은 검색/필터 상단에 있고, 누르면 왼쪽 선택 artifact를 해제한 뒤 제작 가이드 화면으로 전환합니다. 생성 완료 후에는 새 artifact가 자동 선택되고 Run Launcher/Scenario Builder에 적용할 수 있습니다.
- Artifact Studio 독립 화면은 desktop/FHD/QHD에서 viewport 높이를 채우는 작업형 layout을 사용합니다. 좌측 목록, 상세 editor, Script Assist는 page 밖으로 밀리지 않고 각 영역 내부에서 scroll됩니다. mobile/tablet에서는 자연스러운 세로 문서 흐름을 유지합니다.
- text artifact는 lazy-loaded Monaco editor로 편집하며 OSLAB placeholder, output contract, PowerShell/shell/Python template, product-specific agent-cli wrapper snippet, Python `print`/`range` 같은 언어 기본 추천을 제공
- binary artifact와 folder artifact는 `실행 전용` 상세 화면으로 표시합니다. binary는 hash/size/modified time을 보여주고, folder는 file count/total bytes와 제한된 내부 tree preview를 보여주며 둘 다 editor를 노출하지 않습니다.
- Artifact Studio에서 repo/uploaded artifact를 archive할 수 있고, uploaded/archive artifact는 confirm modal을 거쳐 삭제할 수 있습니다. Repo artifact hard delete는 막고 archive-first 정책을 적용합니다. 보관된 leaf artifact를 삭제하면 빈 archive 부모 폴더도 정리해 목록에 0-byte 잔여 폴더가 남지 않게 합니다.
- `validation/artifacts/<folder>/<script>`처럼 폴더 안에 있는 text artifact를 선택했을 때, 시나리오가 `{ArtifactDir}\...` 형태를 기대하면 `상위 폴더를 실행에서 사용`으로 Run Launcher artifact path를 폴더 경로에 맞출 수 있습니다.
- Script Assist 자동완성은 `POST /api/artifacts/assist/complete`를 통해 backend LSP/internal provider에서 받아옵니다. Python, shell, JSON은 repo에 설치된 공개 language server(`pyright-langserver`, `bash-language-server`, `vscode-json-language-server`)에 먼저 요청하고, 부족한 제작 스니펫은 OSLAB internal fallback dataset으로 보강합니다. PowerShell/C는 project-local LSP tool cache 준비 상태와 internal fallback을 함께 보여줍니다. BAT/CMD/txt는 OSLAB internal LSP-compatible provider를 사용합니다. `Ctrl+Space`, `.`, `{`, `$`, `p`, `W`, `r`, `f` 같은 언어별 trigger에서 자연스럽게 후보를 요청합니다.
- Monaco editor는 `fixedOverflowWidgets`를 사용해 suggest/hover/warning popup이 editor box 밖으로 나가도 잘리지 않도록 했고, path 기반 model/defaultValue로 유지해 Assist 갱신 중 React가 입력값을 되돌려 쓰지 않게 했습니다. Snippet 삽입은 plain text edit operation으로 처리해 PowerShell `$OutputPath`, `$result` 같은 변수가 Monaco snippet parser와 충돌하지 않게 합니다.
- Script Assist는 현재 artifact 확장자에 맞춰 PowerShell, shell, Python, JSON, CMD/BAT, C, txt language mode와 static check를 적용합니다. Static lint dataset은 공통 secret pattern 외에 PowerShell `Invoke-Expression`/elevation, shell `curl | sh`/`chmod -R 777`, Python `shell=True`/`os.system`, BAT `del /s`/`reg delete`, C `gets`/`system` 같은 위험 패턴을 언어별로 경고합니다. Monaco model은 artifact path 기준으로 유지해 검사 결과가 갱신되어도 cursor/focus가 튀지 않게 했습니다.
- Script Assist panel은 `처음 만들기`, `도움`, `자동완성`, `검사`, `출력 계약`, `AI 도움` 흐름을 제공하며, 언어 도구 상태(Python/PowerShell/shell/C 등)와 언어별 추천 항목 설명을 표시합니다. `도움` 탭에는 artifact가 VM에 복사/실행되는 흐름, output contract가 필요한 이유, Run Launcher 사용 순서, 언어별 최소 구조와 “무엇을 입력하면 어떤 추천이 뜨는지” 안내가 같이 표시됩니다. 추천 항목은 표시 이름, 설명, 예시 코드, 삽입 버튼을 가진 compact list로 표시합니다. `AI 도움`은 이번 단계에서 실제 모델 호출 없이 확장 지점만 표시합니다.
- Artifact path read-only existence check
- 최근 Artifact preset
- Scenario Builder V2는 기본 상태를 compact summary chip과 `빌더 열기` action으로 표시합니다.
  - `id`, `OS family`, `guest mode`, VMID 범위, artifact, output, report, cleanup 같은 필드는 사용자 친화 `i` tooltip으로 설명합니다.
  - 값 범위가 정해진 필드는 free text input만 두지 않고 select, chip toggle, checkbox로 표시합니다.
  - 환경 준비(Fixture), 제품 실행 단계(Product step), 결과 체크(Assertion)를 추가/삭제/편집하고 YAML로 round-trip 반영할 수 있습니다.
  - Scenario Builder V3 세로축 화면에서는 단계 버튼 폭/높이를 균일하게 유지하고, 선택 상태는 색과 outline만으로 구분합니다.
  - compact horizontal stepper에서는 첫 번째 단계 버튼만 큰 공간을 차지하지 않도록 버튼 track 간격을 고정합니다.
  - mobile/tablet에서 시나리오 목록 접힘은 상단 bar의 위/아래 방향 CSS chevron으로 표시하고, builder detail/list는 내부 Y scroll에 갇히지 않고 화면 흐름으로 펼쳐집니다.
  - 1366/FHD/QHD 넓은 화면에서는 builder panel과 YAML editor가 작업 영역 높이를 채우고, FHD/QHD에서는 builder 폭을 더 넓혀 좌측 조립 화면이 답답해 보이지 않게 합니다.
  - Scenario list row는 제목과 경로가 잘리지 않도록 mobile/tablet `64px`, desktop 이상 `70px` 기준으로 표시합니다.
- 실행 묶음(Suite) visual builder는 기본 상태를 compact summary chip과 `빌더 열기` action으로 표시하고, 필요할 때만 충분한 높이의 builder 작업 영역을 열어 YAML editor가 주 작업공간으로 남도록 조정
- 실행 묶음(Suite) builder의 run 항목은 순서, id, 시나리오, tier, 실패 허용, 이동/삭제 action을 한 줄로 스캔할 수 있는 compact list로 표시
- scenario/results list row height 안정화와 title/path ellipsis 처리
- 실행 묶음(Suite)의 entry 수와 `allowFailure` 수 요약
- 고급 실행 옵션: `keepVm`, `fullClone`
- 기본 동시 실행 수: `1`
- 전역 실행 상태 배너
- running job cancel action
- stopped/stale `oslab-*` VM dry-run/확인 기반 cleanup action
- tab 이동 / logout / browser refresh 전 unsaved-change guard
- builder draft를 포함한 dirty indicator
- 대상, Artifact, Lab, Option, Command 상태를 보여주는 실행 준비 상태 strip
- 대상 선택, Artifact, 랩과 설정, 옵션, 검토와 실행으로 나눈 Run Launcher 5단계 flow
- 실행 묶음/시나리오 버튼별 실행 가능/차단 사유 표시
- 모바일 Run Launcher는 실행 form을 잘린 내부 panel에 가두지 않고 page-level scroll로 접근 가능
- Run Launcher command preview
- Lab Status가 `실행 차단`이면 run button 비활성화
- API restart 후 남은 stale `running` job reconciliation
- jobs/runs 자동 갱신과 Lab Status 주기 갱신
- Results Explorer master-detail
- 결과 검색과 상태 필터
- 결과 종류, 이슈, 증거 필터로 run/suite, failure class, 필수/허용 실패, 취소, 계약 누락 결과를 좁혀봄
- 결과 목록 패널을 좁은 rail로 접어 결과 상세/증거 본문 공간을 넓히고, 선택 결과를 유지한 채 다시 펼칠 수 있음
- 결과 리스트는 검색/상태 필터에 맞춰 선택 상세를 자동 동기화하고, 일치하는 실행이 없으면 빈 상태를 표시
- 결과 리스트는 상대 시간과 절대 로컬 시간을 함께 표시하고, 결과 상세에는 `결과 시간` 섹션을 표시
- 결과 리스트/상세는 artifact `run.json`이 과거 `running`으로 멈춰 있어도 dashboard job의 최종 상태가 있으면 `cancelled`/`failed` 등으로 보정해 표시
- 결과 상세 파일 목록은 실제 `runs/<run-id>/` 디렉터리와 기대 evidence 경로를 합쳐 생성하므로, 고정 evidence 계약 밖의 추가 run artifact는 `추가 발견`으로 보이고 기대했지만 없는 artifact는 비활성 `누락` 파일 카드로 표시
- 실행 묶음 결과 상세는 상위 suite 증거와 하위 scenario run 산출물을 분리하고, child run id별로 파일을 묶어 개별 child 결과로 drill-down 가능
- 실행 묶음의 child 결과 상세는 상위 suite id와 `전체 실행 묶음으로 돌아가기` action이 있는 맥락 배너를 표시
- `progress.jsonl` 기반 run timeline
- running/queued 결과 상세는 실패 문구 대신 진행 중 요약을 표시하고, 최종 progress artifact가 아직 준비되지 않았을 때 live job log를 timeline fallback으로 사용
- 실시간 콘솔 log fetch, auto-scroll, 수동 로그 불러오기
- direct API SSE + keepalive heartbeat
- JSON/JSONL/log/XML과 기타 text-like 결과 evidence overlay preview modal
  - 파일 preview 버튼과 present evidence row에서 열림
  - 파일 카드는 기본적으로 modal을 열고, 새 탭 열기는 preview 창 내부 보조 action으로 유지
  - minified JSON, JSONL 각 줄, XML, JSON 형태의 log output을 읽기 좋은 줄바꿈/indent 형태로 표시하고 실패 시 원문 fallback
  - `result.html`/`suite.html`은 dashboard를 벗어나지 않고 sandboxed iframe으로 보고서 화면을 표시
  - desktop/mobile 모두 viewport 약 90% 크기의 반응형 dialog 사용
  - `Esc`, backdrop click, 접근성 label을 가진 X icon 닫기 버튼으로 닫기
  - 없는 run file 요청은 처리되지 않은 `500` 대신 `404` 반환
- SSE 기반 live job log streaming
- `runs/` result explorer와 generated HTML report 열기

## Verified Browser Smoke

2026-04-23 기준으로 실제 dashboard에서 아래 흐름을 확인했습니다.

```text
로그인 -> 실행 탭 -> demo-powershell-system 선택 -> artifact path 입력 -> 선택한 시나리오 실행 -> 결과 확인
```

검증된 실제 job:

| 항목 | 값 |
| --- | --- |
| Job | `cmob5p1up0007smv00wkvjmit` |
| Run | `20260423-162441-demo-powershell-system-windows` |
| Scenario | `scenarios/windows/demo-powershell-system.example.yaml` |
| Artifact | `validation/artifacts/powershell-system` |
| Result | `passed` |

이 테스트는 Web Dashboard가 단순 화면 mock이 아니라 실제 `uv run oslab run ...` subprocess를 통해 Proxmox clone, QGA, artifact upload, product command, assertion, report, cleanup까지 연결되는 것을 확인하기 위한 smoke입니다.

추가 검증:

| 항목 | 값 |
| --- | --- |
| Artifact 없는 skeleton run | `cmob7mcny000csmywln8n5ymu`, `passed` |
| Artifact 있는 실제 VM demo run | `cmob7mhd6000dsmywchkvb3df`, `20260423-171840-demo-powershell-system-windows`, `passed` |
| Results timeline | `output/web-dashboard/all-features-results-detail.png` |
| Suite detail | `output/web-dashboard/results-suite-detail.png` |

이번 라운드 추가 검증:

| 항목 | 값 |
| --- | --- |
| Scenario builder dirty-state guard | builder 값을 바꾼 뒤 tab 이동 시 confirm dialog 확인 |
| Suite visual builder | `validation/suites/product-specific-windows-v1.example.yaml` readonly builder 표시 확인 |
| Cancel job | `cmobkm4al0007sm0wxkijzd6w`, `cancelled` |
| Cleanup lab VM | Dashboard `남은 VM 정리` 후 `running/stopped oslab VM = 0` 확인 |
| Real VM demo run after cleanup | `cmobkqcfv0008sm0wg87k1lhy`, `20260423-232535-demo-powershell-system-windows`, `passed` |
| Recent artifact UX | `validation/artifacts/powershell-system`, `validation/artifacts/hello-c` chip 표시 확인 |
| Screenshot | `output/web-dashboard/run-success-and-console.png`, `output/web-dashboard/suite-builder-readonly.png` |
| Dense list layout fix | `output/web-dashboard/scenario-list-row-fix.png`, `output/web-dashboard/results-list-row-fix.png` |
| 구조 리팩터링 smoke | `20260424-163351-demo-powershell-system-windows`, `passed` |
| 구조 리팩터링 screenshots | `output/web-dashboard/structure-refactor-dashboard.png`, `output/web-dashboard/structure-refactor-scenario.png`, `output/web-dashboard/structure-refactor-results.png` |
| Skeleton result console 확인 | `output/web-dashboard/structure-refactor-skeleton-result-no-progress-error.png`, browser console errors `0` |
| 전문가 협업 UI pass | `output/web-dashboard/expert-collaboration-run-readiness.png`, `output/web-dashboard/expert-collaboration-diff-preview.png`, `output/web-dashboard/expert-collaboration-mobile-dashboard.png`, browser console errors `0` |
| Cleanup safety | dry-run/confirmation token 계약 추가, stopped/stale VM 후보가 있을 때만 UI cleanup button 노출, `output/web-dashboard/cleanup-dry-run-smoke.json`, console/network issues `0` |
| Results list selection fix | `Failed` 필터 적용 시 visible failed run으로 상세 자동 동기화, 빈 검색 시 stale detail 제거, `output/web-dashboard/results-list-selection-fix-smoke.json`, console/network issues `0` |
| Results stale running 상태 보정 | `20260423-232218-demo-c-hello-windows` artifact는 `running`이지만 job `cmobkm4al0007sm0wxkijzd6w`가 `cancelled`라 리스트/상세에서 `cancelled`와 `상태 보정` 표시 확인, `output/web-dashboard/results-cancelled-status-detail-smoke.json`, API errors `0` |
| Results 고급 필터 | 종류/이슈/증거 필터로 provider failure suite, 필수 실패 suite, 계약 누락 run을 좁혀봄, `output/web-dashboard/results-advanced-filters-smoke.json`, API errors `0` |
| Results 목록 접기 | 펼침 `500px/566px`, 접힘 `52px/1014px`로 상세 영역 `448px` 증가, 모바일 horizontal overflow false, `output/web-dashboard/results-list-collapse-smoke.json`, server/runtime errors `0` |
| Authoring 목록 접기 | Scenario/Fixture/Suite 목록이 `400px`에서 `52px` rail로 접힘, editor 폭 `664px -> 1012px`, 선택 파일 유지, 모바일 horizontal overflow false, `output/web-dashboard/catalog-list-collapse-smoke.json`, server/runtime errors `0` |
| Authoring 문법 검사 | 유효한 변경 YAML/PowerShell은 저장 가능, 정상/검증중 상태는 editor layout을 흔들지 않는 toast로 표시, invalid YAML/PowerShell은 line/column 이슈 표시와 함께 저장 차단, invalid builder inspect `500` 제거, `output/web-dashboard/syntax-validation-ui-smoke.json`, `output/web-dashboard/syntax-validation-api-smoke.json`, server/runtime errors `0` |
| Authoring diff modal과 compact builder | 저장 버튼이 파일을 바로 쓰지 않고 90% diff modal을 먼저 열며, editor 안에는 compact summary만 남김, desktop dialog `1229x691`, mobile dialog `351x760`, 1366x768에서 builder `123px`/textarea `245px`, `output/web-dashboard/authoring-diff-modal-smoke.json`, `output/web-dashboard/authoring-diff-modal-desktop.png`, `output/web-dashboard/authoring-diff-modal-mobile.png`, server/runtime errors `0` |
| Authoring builder 밀도 개선 | Builder 기본 상태는 summary chip과 `빌더 열기`만 표시, scenario summary height `109px`, textarea `416px`; builder를 열면 height `323px`, textarea `202px`; diff modal row는 빈 modal body 전체로 벌어지지 않고 `4px` gap으로 붙어 표시됨; `output/web-dashboard/authoring-builder-density-smoke.json`, `output/web-dashboard/authoring-scenario-builder-summary-desktop.png`, `output/web-dashboard/authoring-scenario-builder-expanded-desktop.png`, `output/web-dashboard/authoring-suite-builder-summary-selected-desktop.png`, `output/web-dashboard/authoring-diff-modal-compact-table-desktop.png` |
| Authoring syntax toast와 builder action | 정상 syntax feedback은 builder와 diff summary 사이에 block으로 생기지 않고 toast로 표시, invalid syntax는 inline 유지, invalid YAML에서는 builder inspect를 건너뛰어 400 console noise 없음, builder 적용 버튼은 secondary `YAML에 적용`으로 표시, `output/web-dashboard/authoring-syntax-toast-smoke.json`, `output/web-dashboard/authoring-syntax-toast-desktop.png`, `output/web-dashboard/authoring-builder-apply-subtle-desktop.png`, `output/web-dashboard/authoring-syntax-error-panel-desktop.png` |
| Suite builder compact list와 문법 체크 | Suite run row가 compact table-like list로 표시됨, `suiteRunRows=5`, `legacyBuilderRows=0`, 첫 row height `52.6px`, row overflow false, 390x844 mobile horizontal overflow false, Suite YAML syntax API/UI에서 valid toast와 invalid blocking panel 확인, `output/web-dashboard/suite-builder-compact-and-syntax-smoke.json`, `output/web-dashboard/suite-builder-compact-run-list-desktop.png`, `output/web-dashboard/suite-builder-compact-run-list-mobile.png`, `output/web-dashboard/suite-syntax-check-invalid-desktop.png` |
| Results preview modal | `run.json`, `progress.jsonl`, mobile overlay 확인, `output/web-dashboard/results-preview-modal-smoke.json`, console/network issues `0` |
| Results preview modal 90% refinement | 1366x768에서 `1230x691`, 390x844에서 `351x760` dialog 확인, X 닫기 버튼 확인, missing file `404`, `output/web-dashboard/results-preview-modal-90pct-smoke.json`, server errors `0` |
| Run Launcher 5-step flow | 대상 선택, Artifact, 랩과 설정, 옵션, 검토와 실행 섹션 확인, scenario skeleton run ready 상태와 suite disabled reason 확인, `output/web-dashboard/run-launcher-step-flow-smoke.json`, console/server errors `0` |
| Run Launcher Artifact 추천 | `demo-powershell-system` 선택 시 `validation/artifacts/powershell-system` 추천 chip 표시, 클릭 시 read-only artifact path 입력 및 ready 상태 확인, 모바일 document width `390`, `output/web-dashboard/run-launcher-artifact-recommendation-smoke.json`, server/runtime/log errors `0` |
| Run Launcher Artifact 업로드 | 브라우저 업로드 파일이 `.web-artifacts/`에 저장되고 현재 artifact path로 선택됨, artifact check `file`, 업로드 전후 상태 카드 표시, 모바일 horizontal overflow false 확인, `output/web-dashboard/run-launcher-artifact-upload-smoke.json`, server/runtime errors `0` |
| Run Launcher 폴더 업로드/반응형 박스 | 브라우저에서 선택한 `Release` 폴더가 `.web-artifacts/` 아래 생성 경로로 복사되고 현재 artifact path로 선택됨, artifact check `directory`, `325px` 폭에서 업로드/추천 박스 가독성 유지, horizontal overflow false, `output/web-dashboard/artifact-folder-upload-responsive-smoke.json`, `output/web-dashboard/artifact-folder-upload-controls-responsive.png`, server/runtime errors `0` |
| Run Launcher 직접 업로드 상태 카드 | 선택한 `Release` 폴더, `156`개 파일, 바이트 진행률, `사용 중` 상태, 저장된 `.web-artifacts/...` 경로 표시 확인, `output/web-dashboard/artifact-folder-upload-responsive-smoke.json`, `output/web-dashboard/artifact-folder-upload-controls-responsive.png`, server/runtime errors `0` |
| Run Launcher 큰 폴더 업로드 | 실제 product-specific `bin/Release` 폴더 업로드가 `http://127.0.0.1:3001/api/artifacts/upload-directory` 직접 API URL로 전송됨, `.web-artifacts/1777272853999-Release`에 `156` files / `72,749,326` bytes 저장, status `201`, UI `사용 중` 표시, `output/web-dashboard/artifact-release-folder-direct-upload.json`, `output/web-dashboard/artifact-release-folder-direct-upload.png`, console errors `0` |
| Artifact Studio + Script Assist | 독립 `아티팩트` 화면 진입, Monaco editor lazy-load, unknown placeholder/파괴적 명령 정적 warning, diff 저장 persistence, script project와 product-specific starter 생성, assist API JSON parse error 검출, FHD/QHD/tablet/mobile horizontal overflow `false` 확인, `output/web-dashboard/artifact-studio-smoke.json`, `output/web-dashboard/artifact-studio-list.png`, `output/web-dashboard/artifact-studio-monaco-editor.png`, `output/web-dashboard/artifact-studio-assist-panel.png`, `output/web-dashboard/artifact-studio-product-specific-template.png`, `output/web-dashboard/artifact-studio-diff-save.png`, `output/web-dashboard/artifact-studio-fhd.png`, `output/web-dashboard/artifact-studio-qhd.png`, `output/web-dashboard/artifact-studio-tablet.png`, `output/web-dashboard/artifact-studio-mobile.png` |
| Artifact Studio viewport layout | FHD/QHD desktop에서 `.workspace-artifacts` 높이가 viewport와 일치하고, Artifact Studio body가 남은 높이를 채우며, Monaco editor와 Script Assist가 화면 하단까지 확장됨. 좌측 artifact 목록은 내부 scroll만 사용하고 mobile에서는 목록 제한 높이와 360px editor 흐름을 유지. `output/web-dashboard/artifact-studio-viewport-layout-smoke.json`, `output/web-dashboard/artifact-studio-viewport-fhd.png`, `output/web-dashboard/artifact-studio-viewport-qhd.png`, `output/web-dashboard/artifact-studio-viewport-mobile.png` |
| Artifact Studio binary/folder archive-delete | FHD/QHD/tablet/mobile에서 repo folder tree, binary read-only detail, repo archive modal, archived delete modal, uploaded binary delete modal 확인. archive leaf 삭제 후 빈 `.artifact-archive/<timestamp>/repo/...` 부모 폴더가 목록에 남지 않도록 cleanup 확인. `validation/artifacts/powershell-system` directory를 `실행에서 사용`으로 Run Launcher에 적용 확인. `output/web-dashboard/artifact-studio-binary-folder-smoke.json`, `artifact-studio-run-apply-smoke.json`, `artifact-studio-folder-tree-fhd.png`, `artifact-studio-archive-modal-fhd.png`, `artifact-studio-delete-modal-fhd.png`, `artifact-studio-binary-readonly-fhd.png`, `artifact-studio-binary-readonly-qhd.png`, `artifact-studio-tablet-layout.png`, `artifact-studio-mobile-layout.png`, `artifact-studio-directory-run-launcher-applied.png` |
| Artifact Studio 생성 흐름/언어팩 | `새 아티팩트 제작` 클릭 시 선택 row가 해제되고 제작 가이드가 표시됨. 단일 PowerShell artifact 생성 후 새 artifact가 자동 선택되고, Script Assist의 언어 도구 상태/처음 만들기 안내가 표시됨. `output/web-dashboard/artifact-studio-create-flow.png`, `output/web-dashboard/artifact-studio-assist-language-tools.png`; 테스트: `corepack pnpm exec playwright test apps/web/tests/artifact-studio-create-assist.spec.js --config=playwright.web-dashboard.config.cjs` |
| Artifact Studio LSP Assist | Python/shell/JSON은 repo-bundled 공개 language server에 먼저 completion을 요청하고, 제작용 OSLAB fallback dataset을 함께 병합함. Python artifact에서 `pri` 입력 후 `print`, `for i in ra` 입력 후 LSP `range`와 fallback `for i in range` 후보가 표시됨. JSON은 LSP `$schema`와 fallback `schemaVersion`, shell은 fallback `grep` smoke를 확인함. `도움`/`자동완성` 탭은 처음 만들기, 언어별 trigger, 설명, 예시 코드, 삽입 action을 한국어로 표시함. Monaco suggest popup overflow가 editor box에 잘리지 않도록 `fixedOverflowWidgets` 적용. 빠른 입력 후 Monaco model value가 입력 문자열과 일치하는지 회귀 테스트 추가. 사용자 화면에 보이는 Chrome FHD 수동 QA에서도 Artifact Studio 진입, Python artifact 편집, `pri` -> `print`, `for i in ra` -> `range`, 자동완성 안내 탭을 확인함. `output/web-dashboard/artifact-studio-lsp-open-service-smoke.json`, `output/web-dashboard/artifact-studio-python-lsp-print.png`, `output/web-dashboard/artifact-studio-python-lsp-range.png`, `output/web-dashboard/artifact-studio-python-typing-stability.png`, `output/web-dashboard/artifact-studio-visible-browser-smoke.json`, `output/web-dashboard/artifact-studio-visible-python-print.png`, `output/web-dashboard/artifact-studio-visible-python-range.png`; 테스트: `corepack pnpm exec playwright test apps/web/tests/artifact-studio-create-assist.spec.js --config=playwright.web-dashboard.config.cjs` |
| Artifact Studio 생성 -> 자동완성 -> 실제 run | Web UI에서 `validation/artifacts/web-ui-demo-20260430123434/run-system-demo.ps1` 생성, Monaco 자동완성 popup에서 PowerShell/placeholder snippet 표시와 console error `0` 확인, `상위 폴더를 실행에서 사용`으로 Run Launcher에 `validation/artifacts/web-ui-demo-20260430123434` 적용, 실제 `demo-powershell-system` 실행 통과. job `cmokxp8su0003smrog10l9yo1`, run `20260430-123836-demo-powershell-system-windows`, assertions `2/0`, preflight `6/0`, cleanup 완료. 산출물: `output/web-dashboard/artifact-studio-demo-created.png`, `output/web-dashboard/artifact-studio-autocomplete-trigger.png`, `output/web-dashboard/artifact-studio-assist-check.png`, `output/web-dashboard/artifact-studio-run-launcher-linked.png`, `output/web-dashboard/artifact-studio-demo-run-complete.png`, `output/web-dashboard/artifact-studio-demo-result-detail.png` |
| product-specific 실행 묶음 Web smoke | Web에서 `validation/suites/product-specific-windows-v1.example.yaml`와 `C:\Users\kysky\Documents\gitlab\agent-windows\ProductAgent\bin\Release`로 실행, job `cmognt5bg000usmmg6u6uvktu`가 실제 VM 실행까지 진행, 3개 entry 통과, `appx-readonly`는 허용 실패, `path-profile`에서 필수 QGA `exec-status` 일시 실패 발견, `output/web-dashboard/product-specific-suite-web-ui-smoke.json`, `output/web-dashboard/product-specific-suite-web-final-console.png`, server/runtime errors `0` |
| product-specific path-profile Web 재검증 | QGA `exec-status` retry 추가 후 Web에서 `scenarios/windows/product-specific/product-specific-agent-path-profile.example.yaml` 재실행 통과, job `cmogpdv9r002gsmmg4f7b062i`, run `20260427-133443-product-specific-agent-path-profile-windows`, normalized records `9`, assertions `8`, cleanup 완료, `output/web-dashboard/product-specific-path-profile-web-regression.json`, `output/web-dashboard/product-specific-path-profile-web-final-console.png`, server/runtime errors `0` |
| Run Launcher 디렉터리 artifact 경로 | `직접 입력 - 파일/폴더 경로`로 `C:\Users\kysky\Documents\gitlab\agent-windows\ProductAgent\bin\Release` 입력 시 API/UI 모두 `kind=directory`로 확인, 시나리오 실행 준비 활성화, `output/web-dashboard/artifact-directory-path-smoke.json`, `output/web-dashboard/artifact-directory-path-direct-input.png`, server/runtime errors `0` |
| Run Launcher 단일 스크롤 | 실행 화면에서 실행 폼/실시간 콘솔 내부 스크롤과 page 스크롤이 겹치지 않게 수정. `.workspace-run` 하나만 스크롤을 담당하고, `1500px` 이하에서는 실행 폼과 실시간 콘솔이 1열로 배치됩니다. FHD wide 화면에서도 콘솔 panel/pre가 grid stretch와 내부 scrollbar를 만들지 않습니다. 검증: `output/web-dashboard/run-scroll-single-flow-smoke.json`, `output/web-dashboard/run-console-single-flow-smoke.json`, `output/web-dashboard/run-console-single-flow-fhd.png`, panel/pre `scrollTop=0` |
| Results 사람이 읽는 시간 | `20260426-174301-demo-python-hello-windows` 결과에서 리스트 절대 시간과 상세 `결과 시간` 섹션 확인, 시작/완료/소요 시간 표시, `output/web-dashboard/results-human-time-smoke.json`, console/server errors `0` |
| Results 발견/누락 run 파일 | `20260426-174301-demo-python-hello-windows`에서 `raw/fixture-demo-python-runtime.expected-output.json`은 `추가 발견` 파일로 표시되고, `normalized/inventory.json`/`raw/product-steps.json`은 dead link 없는 `누락` 기대 파일로 표시됨, 발견 JSON preview modal 확인, `output/web-dashboard/results-run-files-api-smoke.json`, `output/web-dashboard/results-run-files-missing-api-smoke.json`, `output/web-dashboard/results-run-files-ui-smoke.json`, server/runtime errors `0` |
| 카드/섹션 설명 tooltip | Lab Status, dashboard metric/list, 실행 준비/단계, authoring syntax/diff, Results 시간/파일/증거/timeline header에서 원형 `i` tooltip 확인, Artifact는 VM 안에서 테스트할 프로그램/설치 파일/스크립트/ZIP 묶음이라는 사용자 친화 설명으로 정리, `output/web-dashboard/info-tooltip-smoke.json`, `output/web-dashboard/info-tooltip-artifact-friendly.png`, server/runtime errors `0` |
| Information tooltip 확장 | 환경 준비 dashboard metric, Scenario/Fixture/Suite catalog header, Run Suite policy, Results evidence group header, `run.json`/`progress.jsonl` evidence row에 사용자 관점 설명 추가 확인, `output/web-dashboard/info-tooltip-smoke.json`, `output/web-dashboard/info-tooltip-dashboard-fixtures.png`, `output/web-dashboard/info-tooltip-scenario-catalog.png`, `output/web-dashboard/info-tooltip-fixture-catalog.png`, `output/web-dashboard/info-tooltip-suite-catalog.png`, `output/web-dashboard/info-tooltip-evidence-run-json.png`, `output/web-dashboard/info-tooltip-evidence-progress-jsonl.png`, server/runtime errors `0` |
| Results 실행 묶음 child drill-down | `20260427-125037-product-specific-windows-v1`에서 child run 5개와 child artifact 80개를 묶어 표시, child 결과 `20260427-125037-product-specific-windows-v1-appx-readonly` 상세에 상위 suite 맥락 배너와 돌아가기 action 표시, refresh 후에도 부모 suite row 선택 유지, `run.json`은 새 탭 없이 modal로 열림, `output/web-dashboard/results-suite-redesign-smoke.json`, `output/web-dashboard/results-suite-files-grouped.png`, `output/web-dashboard/results-suite-child-context.png`, `output/web-dashboard/results-suite-back-from-child.png`, `output/web-dashboard/results-child-preview-popup.png`, console errors `0` |
| Results pretty preview | JSON 형태의 `product-step-status.stdout.log`가 한 줄 minified 출력이 아니라 indent된 여러 줄 preview로 표시됨, `output/web-dashboard/results-pretty-json-log-preview.png`, `prettyLogPreview=true`, console errors `0` |
| Results HTML report preview | `reports/result.html`이 raw HTML text가 아니라 dashboard preview modal 안의 sandboxed iframe 보고서로 표시됨, `output/web-dashboard/results-html-iframe-preview.png`, `htmlPreviewIframe=1`, console errors `0` |
| Scenario Builder V2 | 새 시나리오 dialog, 사용자 관점 field tooltip, select/chip/toggle field, fixture/product/assertion 섹션, builder apply, diff modal 저장, scenario contract validation 확인. 디자인 pass에서 Target VM -> 환경 준비 -> Artifact/Output -> 실행 명령 -> 결과 체크 -> 정리 workflow로 재배치하고 `새 시나리오`와 목록 접기 action 정렬을 맞춤. 새 시나리오 dialog는 90% preview modal 비율에서 compact 생성 폼 비율로 보정함, `output/web-dashboard/scenario-builder-v2-validation-smoke.json`, `output/web-dashboard/scenario-builder-v2-mobile-smoke.json`, `output/web-dashboard/scenario-builder-v2-design-regression-smoke.json`, `output/web-dashboard/scenario-create-dialog-compact-smoke.json`, `output/web-dashboard/scenario-builder-v2-design-header-actions.png`, `output/web-dashboard/scenario-builder-v2-design-desktop-expanded.png`, `output/web-dashboard/scenario-builder-v2-design-mobile-expanded.png`, `output/web-dashboard/scenario-create-dialog-compact-desktop.png`, `output/web-dashboard/scenario-create-dialog-compact-mobile.png` |
| Fixture/Suite 생성 | `새 환경 준비`, `새 실행 묶음` 생성이 New Scenario와 같은 create-only 안전 흐름을 사용합니다. Dialog open/create 흐름과 screenshot을 focused Playwright로 확인했습니다: `output/web-dashboard/authoring-new-fixture-dialog.png`, `output/web-dashboard/authoring-new-suite-dialog.png`; 테스트: `corepack pnpm exec playwright test apps/web/tests/authoring-create-dialogs.spec.js --config=playwright.web-dashboard.config.cjs` |
| 새 시나리오 생성 UAT | 전문가 리뷰와 브라우저 인수테스트로 create-only 흐름 확인. dialog는 “파일만 생성, 실행은 나중”을 안내하고, 기본 저장 경로는 기존 파일과 충돌하면 자동 회피하며, `id` 변경 시 저장 경로도 동기화됩니다. 저장하지 않은 scenario/builder 변경은 생성 전 confirm으로 보호하고, 생성 후 새 파일이 선택/편집 상태로 열리며 builder가 로드됩니다. `output/web-dashboard/scenario-create-uat-smoke.json`, `output/web-dashboard/scenario-create-uat-dialog.png`, `output/web-dashboard/scenario-create-uat-after-create.png`, `output/web-dashboard/scenario-create-uat-mobile-dialog.png` |
| Scenario Builder V3 세로축 | 시나리오 작성 화면에서 세로 stepper builder와 오른쪽 YAML editor 구조를 지원합니다. 선택한 단계는 compact detail panel로 열리고 YAML은 오른쪽에 계속 보입니다. 실행 단계는 `4A Artifact 실행 명령`과 `4B 제품 실행 단계`로 나눠 4번 중복 혼란을 줄였습니다. desktop/mobile overflow smoke 통과, `output/web-dashboard/scenario-builder-v3-vertical-smoke.json`, `output/web-dashboard/scenario-builder-v3-vertical-desktop.png`, `output/web-dashboard/scenario-builder-v3-vertical-mobile.png`, `output/web-dashboard/scenario-builder-vertical-axis-mockup.png` |
| Viewport design matrix | 브라우저 검증 범위에 390x844, 768x1024, 1366x768, Full HD 1920x1080, QHD 2560x1440을 포함했습니다. 각 viewport에서 Scenario/Scenario collapsed/Run/Results 스크린샷을 남겼고 console/page errors `0`, horizontal overflow `false`입니다. Scenario Builder V3는 빌더 폭을 넓히고 YAML 좌측 줄번호 gutter를 추가했으며, mobile/tablet scenario list는 5-7개 높이의 scroll 영역으로 제한했습니다. mobile/tablet 접힘 상태는 왼쪽 rail이 아니라 상단 가로 bar로 표시합니다. 1366 open list builder/YAML은 `420px/379px`, collapsed YAML은 `546px`, FHD/QHD builder는 `591px`/`860px`, 1366/FHD/QHD builder/YAML height delta는 `0`, list text clipping은 `false`입니다. `output/web-dashboard/viewport-design-matrix-smoke.json`, `output/web-dashboard/viewport-matrix-mobile-scenario-collapsed.png`, `output/web-dashboard/viewport-matrix-qhd-scenario.png` |

## Korean UI Terminology

한국어 UI에서는 단순 음역을 피합니다. 필요한 경우 한국어 의미 표현 뒤에 원 영어 용어를 괄호로 병기합니다.

| English | Korean UI |
| --- | --- |
| Scenario | 시나리오 |
| Fixture | 환경 준비(Fixture) 또는 환경 준비 스크립트(Fixture) |
| Suite | 실행 묶음(Suite) |
| Run | 실행 |
| Job | 작업 |
| Results | 결과 |
| Dashboard | 대시보드 |
| Lab Status | 랩 상태 |
| Live Console | 실시간 콘솔 또는 실시간 로그 |

## UX Roadmap

전문가 리뷰와 브라우저 smoke 결과, 다음 순서로 개선합니다.

1. 실행 전 준비 확인 확장
   - scenario-aware artifact recommendation은 catalog 기반 demo/fake 시나리오 1차 구현을 완료했습니다.
   - ZIP/EXE/MSI/script 단일 파일과 폴더 artifact upload는 `.web-artifacts/` 기반으로 구현했습니다. 폴더 선택은 브라우저 보안상 원본 절대 경로를 넘기지 않고, 선택한 폴더를 dashboard 서버의 생성 디렉터리로 복사해 사용합니다.
   - 큰 폴더 업로드는 Next rewrite proxy를 우회하고 API server에 직접 전송해 multipart 업로드 안정성을 확보합니다.
   - 직접 업로드 상태 카드는 선택됨/업로드 중/사용 중/실패와 진행률, 저장 경로를 보여주므로 큰 Release 폴더 업로드 중에도 사용자가 현재 상태를 바로 이해할 수 있습니다.
2. Job 상태 표시 개선
   - long-running job의 마지막 log 수신 시각과 cancel 이후 cleanup 결과 반영을 추가합니다.
3. Authoring safety 확장
   - 현재 editor buffer 기준 YAML/PowerShell syntax validation은 구현했습니다.
   - Scenario 저장 전에는 `POST /api/validate/scenario-content`로 최소 scenario contract도 함께 검사합니다.
   - 저장 전 diff는 90% modal을 유지하되 변경 row를 빈 공간 전체로 벌리지 않고 위에서부터 촘촘히 표시합니다.
   - visual builder는 기본 compact summary chip으로 접고, 필요할 때 충분한 높이로 열 수 있게 해 YAML 편집 공간을 확보했습니다.
   - Scenario Builder V2는 사용자 설명 tooltip, enum control, cleanup toggle, fixture/product-step/assertion generic 편집까지 확장했습니다.
   - `새 환경 준비(Fixture)`와 `새 실행 묶음(Suite)` 생성도 `새 시나리오`와 같은 create-only 안전 흐름으로 확장했습니다.
   - Suite 저장은 `POST /api/validate/suite-content`로 최소 contract를 함께 검사합니다.
   - 다음은 assertion type별 전용 form, fixture side-effect 요약, fixture reference flow, suite multi-select/maxParallel 작성 UX를 추가합니다.
4. Artifact authoring/manager
   - 현재 upload flow는 파일/폴더를 `.web-artifacts/` 아래 저장하고 binary artifact는 upload-only로 둡니다.
   - Artifact Studio 독립 화면을 추가했습니다. `validation/artifacts/**`와 `.web-artifacts/**`를 browse하고 hash/size/provenance를 표시하며, text-like artifact, 폴더형 프로젝트, product-specific starter를 Web에서 생성/편집할 수 있습니다.
   - Script Assist는 Monaco editor 위에서 backend 공개 LSP 우선 completion, internal fallback dataset, JSON parse, placeholder, output contract, 언어별 위험 명령 warning, 언어 도구 상태 안내를 제공합니다. 실제 AI 호출은 아직 붙이지 않았습니다.
   - nested text artifact를 만든 뒤 시나리오가 폴더 artifact를 기대하는 경우를 위해 `상위 폴더를 실행에서 사용` 흐름을 제공합니다.
   - 다음은 recent-use ownership metadata, Scenario Builder artifact path 깊은 삽입, 실제 AI-assist backend, language tool install flow 고도화입니다.
   - 상세 계획: [Authoring Expansion Collaboration Plan](devs/authoring-expansion-collaboration-plan.md).
5. 실시간 콘솔 timeline
   - raw log만 보여주지 않고 clone, boot, QGA, preflight, fixture, artifact, product, assertion, cleanup 단계를 시각화합니다.
6. Results Explorer master-detail
   - `suite.html` 링크 외에도 `suite.json`, `run.json`, `progress.jsonl`, 발견된 raw/normalized output, generated report, 누락 기대 파일, 기타 text-like run 파일을 dashboard 안에서 탐색합니다.
   - `runs/<suite>/scenarios/<child>/...` 형태의 실행 묶음 child 파일 그룹과 child 결과 drill-down은 구현 완료했습니다.
7. Cleanup metadata
   - stale VM metadata를 run artifact에 남긴 뒤 candidate age와 owning run을 cleanup 확인 화면에 연결합니다.

상세 개발 TODO는 [Web Dashboard Usability TODO](devs/web-dashboard-usability-todo.md)를 봅니다.

## Known Gaps

- OIDC/SSO 없음
- local admin 외 role 분리 없음
- TRX aggregate report 미구현
- Fixture/Suite의 full schema-aware validation은 아직 남아 있습니다. Scenario/Suite 저장은 YAML 문법 검사와 최소 contract validation을 함께 수행합니다.
- Scenario visual builder는 fixture/assertion/product-step generic 편집까지 지원하지만, assertion type별 전용 form과 fixture side-effect form은 아직 남아 있습니다.
- Fixture와 Suite 생성은 1차 create-only 흐름이 구현되었습니다. product-specific fixture starter, mobile/FHD/QHD 시각 matrix, 생성된 suite 실제 실행 smoke는 후속입니다.
- Artifact Studio는 text/binary/directory 통합 관리, project starter, product-specific starter, Monaco Script Assist, 공개 LSP 우선 자동완성, internal fallback/lint dataset, archive/delete, 언어 도구 상태 안내까지 구현되었습니다. 남은 gap은 recent-use ownership metadata, Scenario Builder artifact path 깊은 연결, 실제 AI 도움 backend, project-local PowerShell/C LSP tool cache 설치 flow 고도화입니다.
- Job cancel 후 `run.json`이 남지 않은 interrupted run을 결과 화면에서 더 자연스럽게 정리하는 보강이 남아 있습니다.
