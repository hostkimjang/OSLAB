# Browser Debug Checklist

이 문서는 `oslab` Web Dashboard를 브라우저에서 실제로 디버깅할 때 계속 누적해서 사용하는 체크리스트입니다.

목적:

- 기능이 “코드상 구현됨”이 아니라 “브라우저에서 실제로 작동함”을 확인
- 레이아웃 깨짐, overflow, 빈 상태, 실시간 로그, 결과 상세 UX를 스크린샷과 함께 추적
- 다음 작업에서도 같은 smoke를 반복해서 회귀를 빠르게 잡음

## 기본 원칙

- Web 작업을 할 때는 **항상 브라우저를 실제로 띄워서 확인**합니다.
- 수정 전/후에 **스크린샷**을 남깁니다.
- 화면 검증은 mobile/tablet/desktop뿐 아니라 Full HD와 QHD까지 포함합니다.
- 주요 기능 화면은 해상도별 스크린샷과 overflow/clipping 측정값을 `output/web-dashboard/`에 남겨 다음 디자인 개선 회의의 근거로 사용합니다.
- 가능하면 **실제 run 하나 이상**을 Web에서 실행합니다.
- 회귀가 있었던 기능은 다음 작업에서도 다시 확인합니다.
- 스크린샷과 검증 결과는 `output/web-dashboard/` 아래에 남깁니다.

## 공통 사전 확인

- [ ] API dev server 응답 확인: `http://127.0.0.1:3001/api/me`
- [ ] Web dev server 로컬 응답 확인: `http://127.0.0.1:3000`
- [ ] Web dev server bind 확인: `0.0.0.0:3000` listen 상태, LAN 검증 시 `http://<dashboard-host-ip>:3000`
- [ ] `apps/api/.env`, `apps/web/.env`가 유효한지 확인
- [ ] LAN 검증 시 `apps/api/.env`의 `OSLAB_WEB_HOST`, `OSLAB_WEB_ORIGIN`이 실제 Web/API 접근 경로와 맞는지 확인
- [ ] build 후 dev server를 다시 띄웠다면 `.next` stale cache가 없는지 확인

## 공통 브라우저 Smoke

### 1. 로그인과 기본 상태

- [ ] 로그인 화면 표시
- [ ] 로컬 admin 계정 로그인 성공
- [ ] `KO/EN` 전환 확인
- [ ] 로그아웃 확인
- [ ] Dashboard 첫 화면에서 `랩 상태` 패널 표시
- [ ] card/section header와 선택된 evidence row의 원형 `i` tooltip이 hover/focus/click 또는 tap으로 열리고 `Esc`/outside click으로 닫힘
- [ ] tooltip이 내부 scroll panel과 mobile viewport에서 잘리거나 가로 overflow를 만들지 않음
- [ ] 실행 중 job이 있으면 상단 `전역 실행 상태` 배너 표시

### 2. Authoring

- [ ] 시나리오 목록 로드
- [ ] 검색 필터 동작
- [ ] 작성 화면 파일 목록 접기/펼치기 버튼 동작
- [ ] 목록을 접었을 때 editor 본문이 넓어지고 rail에 펼치기 버튼과 파일 수가 표시됨
- [ ] Scenario/Fixture/Suite 각각 접기/펼치기 후 선택 파일이 유지됨
- [ ] 파일 열기
- [ ] 기본 읽기 전용 표시
- [ ] `수정` -> 편집 가능
- [ ] 편집 중 YAML/PowerShell 정상/검증중 상태는 editor 레이아웃을 밀지 않는 toast로 표시
- [ ] 유효한 변경 content는 `저장` 버튼 활성화
- [ ] `저장` 클릭 시 inline full diff가 아니라 viewport 약 90% 크기의 저장 전 diff modal이 먼저 열림
- [ ] diff modal 안에서 최종 `저장` action과 X icon close, `Esc`, backdrop close가 동작함
- [ ] authoring 화면에는 compact diff summary만 남아 editor textarea 공간을 계속 확보함
- [ ] Scenario/Suite visual builder는 기본 compact summary로 표시되고, 사용자가 열었을 때만 충분한 높이의 builder 작업 영역을 표시함
- [ ] Scenario 목록 header의 `새 시나리오` 버튼이 열리고 X/`Esc`/backdrop으로 닫힘
- [ ] 새 시나리오 dialog에서 Windows smoke, Linux smoke, product-specific smoke template 선택이 path/id/name을 바꿈
- [ ] 새 시나리오 생성 후 기존 파일을 덮어쓰지 않고 catalog에 추가되며 해당 YAML이 편집 상태로 열림
- [ ] Fixture 목록 header의 `새 환경 준비` 버튼이 열리고 X/`Esc`/backdrop으로 닫힘
- [ ] 새 환경 준비 dialog에서 Windows PowerShell, Linux shell, product-specific profile template 선택이 path/id/name/source를 바꿈
- [ ] 새 환경 준비 생성 후 기존 파일을 덮어쓰지 않고 catalog에 추가되며 해당 Fixture가 편집 상태로 열림
- [ ] Suite 목록 header의 `새 실행 묶음` 버튼이 열리고 X/`Esc`/backdrop으로 닫힘
- [ ] 새 실행 묶음 dialog에서 scenario multi-select, tier, allowFailure, enabled, maxParallel starter가 YAML로 생성됨
- [ ] 새 실행 묶음 생성 후 Suite Builder가 로드되고 Run Launcher suite dropdown에 반영됨
- [ ] 새 실행 묶음 생성 후 Run Launcher의 maxParallel이 생성 dialog 값으로 반영됨
- [ ] Suite Builder에서 enabled/maxParallel을 수정해 YAML에 적용할 수 있음
- [x] validation/artifacts manager에서 repo artifact와 `.web-artifacts` 업로드 artifact가 구분되어 표시됨
- [x] text-like artifact는 Web에서 생성/편집 가능하지만 `.exe/.msi/.zip`은 upload-only/read-only로 표시됨
- [x] 좌측 nav `아티팩트` 화면에서 Artifact Studio 목록/검색/source/type filter가 동작함
- [x] `새 아티팩트 제작` 클릭 시 왼쪽 선택 row가 해제되고 제작 가이드 화면으로 전환됨
- [x] 새 artifact 생성 완료 후 새 항목이 자동 선택되고 Run Launcher/Scenario Builder 적용 action을 바로 사용할 수 있음
- [x] Artifact Studio에서 단일 파일, 폴더형 프로젝트, product-specific starter 생성이 create-only/no-overwrite로 동작함
- [x] Artifact Studio Monaco editor가 확장자별 language mode로 로딩되고 snippet 삽입/자동완성이 동작함
- [x] Monaco editor는 Assist check/언어 상태 갱신 중 cursor/focus가 다른 영역으로 튀지 않음
- [x] Artifact Studio에서 binary artifact를 선택하면 editor 없이 실행 전용 상세, size/hash/modified metadata, archive/delete 정책이 표시됨
- [x] Artifact Studio에서 directory artifact를 선택하면 file count/total bytes와 내부 tree preview가 표시되고 page overflow가 발생하지 않음
- [x] Artifact Studio archive/delete modal은 dry-run 정보를 먼저 보여주고 confirm 후 목록과 현재 선택 상태를 갱신함
- [x] Repo artifact는 hard delete 버튼이 보이지 않거나 차단되고 archive-first 정책이 안내됨
- [x] Uploaded 또는 archived artifact는 confirm 후 삭제 가능하며 `.web-artifacts/**`/`.artifact-archive/**` 밖 경로는 거부됨
- [x] Artifact Studio desktop/FHD/QHD 화면에서 Studio body가 남은 viewport 높이를 채우고, Monaco editor와 Script Assist가 화면 하단까지 확장됨
- [x] Artifact Studio 좌측 artifact 목록은 page를 밀어내지 않고 목록 내부 scroll만 사용함
- [x] Artifact Studio mobile/tablet 화면에서는 목록이 제한 높이 안에서 scroll되고 editor/Assist가 세로 흐름으로 겹침 없이 표시됨
- [x] Script Assist `처음 만들기` 안내가 artifact 의미, VM 복사/실행 흐름, output contract, Run Launcher 사용 순서를 설명함
- [x] Script Assist `도움`/`자동완성` 탭이 언어별 추천 항목, trigger, 설명, 예시 코드, 삽입 버튼을 한국어 compact list로 설명함
- [x] Python artifact에서 `pri` 입력 후 backend completion으로 `print` 후보가 표시됨
- [x] Python artifact에서 `for i in ra` 입력 후 completion으로 `range` 후보가 표시됨
- [x] Monaco suggest/hover/warning popup은 editor box 밖으로 나가도 잘리지 않음
- [x] Script Assist `검사` 탭이 JSON 오류, placeholder 오타, output contract 힌트, 파괴적 명령 warning을 표시함
- [x] Script Assist 언어 도구 상태가 PowerShell/shell/Python/JSON/CMD/BAT/C/txt에 맞게 표시되고, Python/shell/JSON은 repo-bundled LSP, PowerShell/C는 project-local LSP cache 준비 상태, BAT/txt는 internal provider로 구분됨
- [x] Script Assist `AI 도움` 탭은 실제 호출 없이 placeholder/extension point로 표시됨
- [ ] Scenario builder의 `id`, `name`, `OS family`, `guest mode`, VMID, artifact, output, cleanup tooltip이 사용자 친화 설명으로 표시됨
- [ ] `OS family`, `guest mode`, `artifact type`, `artifact transfer`는 text input이 아니라 select로 표시됨
- [ ] report format과 guest 접속 우선순서는 chip toggle로 표시되고 YAML에 적용됨
- [ ] Fixture/Product step/Assertion 섹션이 열리고 추가/삭제/편집 후 YAML round-trip이 동작함
- [ ] scenario 저장 전 YAML 문법뿐 아니라 scenario contract 검증 실패도 저장을 차단함
- [ ] Suite visual builder는 실행 순서 리스트처럼 보이며 각 run row가 한 줄 compact 편집으로 표시됨
- [ ] invalid YAML/PowerShell은 line/column issue를 inline으로 표시하고 `저장` 버튼 비활성화
- [ ] `취소` -> 읽기 전용 복귀
- [ ] 저장하지 않은 변경 discard confirm

### 3. Run Launcher

- [ ] `실행 묶음 없음` / `시나리오 없음` 옵션 표시
- [ ] `Artifact 선택` dropdown 표시
- [ ] 선택한 scenario에 맞는 추천 Artifact chip 표시 및 클릭 적용
- [ ] Artifact 업로드 박스 표시
- [ ] 파일 업로드 후 `.web-artifacts/` path가 artifact path로 자동 선택됨
- [ ] 폴더 선택 후 `.web-artifacts/<timestamp>-<folder>/` directory path가 artifact path로 자동 선택됨
- [ ] 큰 폴더 업로드는 Next rewrite proxy가 아니라 API server `:3001`로 직접 전송됨
- [ ] 직접 업로드 상태 카드가 선택됨/업로드 중/사용 중/실패, 파일 수, 진행률, 저장 경로를 표시함
- [ ] 좁은 Run panel에서도 Artifact 업로드/추천 박스 title, 설명, 버튼이 세로로 찌그러지지 않음
- [ ] catalog 선택 시 path input disabled
- [ ] `직접 입력 - 파일/폴더 경로` 시 path input enabled
- [ ] 제품 `bin/Release` 같은 서버 접근 가능 디렉터리 경로 입력 시 artifact status가 `directory`로 표시됨
- [ ] Artifact 존재 여부 배지 표시
- [ ] 기본 `동시 실행 수 = 1`
- [ ] `고급 옵션` 토글 표시
- [ ] `keepVm`, `fullClone` 체크박스 표시
- [ ] command preview 표시
- [ ] Run Launcher가 대상 선택, Artifact, 랩과 설정, 옵션, 검토와 실행 5단계 section으로 표시됨
- [ ] Run Launcher readiness/step header tooltip이 차단/주의/선택 사항 의미를 설명함
- [ ] 실행 묶음/시나리오 버튼이 비활성일 때 각각 차단 사유를 표시함
- [ ] Artifact 확인 중에는 stale artifact check 결과로 실행 버튼이 활성화되지 않음

### 4. Live Console

- [ ] 실행 직후 selected job 표시
- [ ] 콘솔에 시작 메시지 표시
- [ ] 콘솔에 실제 진행 로그 표시
- [ ] `로그 불러오기` 버튼 동작
- [ ] 실행 완료 후 최종 상태 notice 반영
- [ ] Results tab에서 running run이 완료되면 수동 새로고침 없이 목록 row, 상세 badge, 핵심 요약이 terminal status로 갱신됨
- [ ] running run의 progress/timeline이 Results tab에서도 주기적으로 갱신됨

### 5. Results

- [ ] 결과 리스트 로드
- [ ] 결과 검색/filter toolbar 표시
- [ ] 결과 종류/이슈/증거 filter가 run/suite, failure class, 필수/허용 실패, 계약 누락을 좁혀봄
- [ ] 결과 목록 접기/펼치기 버튼 동작
- [ ] 목록을 접었을 때 상세 본문 영역이 넓어지고 rail에 펼치기 버튼과 결과 수가 표시됨
- [ ] 최근 run 선택
- [ ] 결과 상세 요약 표시
- [ ] 결과 리스트에 상대 시간과 사람이 읽는 절대 시간이 함께 표시
- [ ] 결과 상세에 `결과 시간` 섹션이 표시되고 시작/완료/소요 시간이 사람이 읽는 형식으로 표시
- [ ] 과거 artifact `running` 상태가 dashboard job 최종 상태와 다르면 리스트/상세에 보정된 상태와 `상태 보정` 문구가 표시
- [ ] `멈춤` status filter가 오래된 active artifact 상태를 분리해 볼 수 있음
- [ ] timeline 표시
- [ ] file link 표시
- [ ] 실제 `runs/<run-id>/` 폴더에 존재하는 파일이 고정 evidence 목록 밖에 있어도 파일 목록에 표시됨
- [ ] 고정 evidence 계약 밖에서 발견된 파일은 그룹과 `추가 발견` 배지로 표시됨
- [ ] 기대 evidence 경로지만 실제 파일이 없으면 `누락` 파일 카드로 표시되고 dead link/preview button을 만들지 않음
- [ ] preview modal에서 JSON/log 표시
- [ ] preview modal에서 minified JSON, JSONL, JSON 형태의 log가 줄바꿈/indent된 읽기 좋은 형태로 표시됨
- [ ] preview modal에서 `result.html`/`suite.html`은 raw text가 아니라 sandboxed iframe 보고서로 표시됨
- [ ] suite result detail 표시
- [ ] suite result detail에서 상위 suite 파일과 하위 scenario run 파일이 분리되어 보임
- [ ] 하위 scenario run 파일은 child run id별로 묶이고 `상세 보기`로 child detail에 진입 가능함
- [ ] child detail 상단에 `실행 묶음 안의 시나리오 상세` 맥락 배너와 상위 suite id가 표시됨
- [ ] child detail에서 `전체 실행 묶음으로 돌아가기` 버튼으로 suite summary/child file group에 복귀 가능함
- [ ] suite/child detail 전환 시 오른쪽 상세 패널 scroll이 상단으로 초기화됨
- [ ] child detail 선택 후 자동 refresh가 돌아도 부모 suite row 선택 강조가 유지됨
- [ ] 이미 선택된 결과 row를 다시 눌러도 상세가 `Loading...` 상태로 비지 않음
- [ ] file chip 기본 클릭은 새 탭이 아니라 preview modal을 염
- [ ] Evidence checklist 표시
- [ ] 결과 시간/파일/증거/timeline/file group/evidence row tooltip이 현재 섹션과 핵심 파일의 사용 시점을 설명함
- [ ] `run.json`, `progress.jsonl`, raw/normalized output, report, cleanup state가 present/missing/contract gap으로 표시
- [ ] present JSON/log/XML evidence row 클릭 시 preview modal 열림
- [ ] preview modal close button, backdrop click, `Esc` close 동작
- [ ] preview modal close control이 텍스트 버튼이 아니라 X icon button으로 표시되고 접근성 label을 가짐
- [ ] preview modal이 desktop/mobile viewport에서 약 90% 크기로 반응형 표시됨
- [ ] preview modal에서 긴 JSON/log가 modal 내부 scroll로 처리됨
- [ ] 없는 run file 또는 미지원 preview 경로가 처리되지 않은 `500`으로 떨어지지 않음

## 실제 Demo Run Smoke

### PowerShell demo

- [x] `scenarios/windows/demo-powershell-system.example.yaml`
- [x] artifact: `validation/artifacts/powershell-system`
- [x] Web에서 실행
- [x] 결과: `passed`

### Python demo

- [ ] `scenarios/windows/demo-python-hello.example.yaml`
- [ ] artifact: `validation/artifacts/hello-python`
- [ ] fixture bootstrap 확인
- [ ] stdout: `hello from python`
- [ ] 결과: `passed`

### C demo

- [ ] `scenarios/windows/demo-c-hello.example.yaml`
- [ ] artifact: `validation/artifacts/hello-c`
- [ ] fixture bootstrap 확인
- [ ] stdout: `hello from c`
- [ ] 결과: `passed`

## 레이아웃/디자인 확인 포인트

- [ ] 2560x1440 QHD viewport에서 넓은 화면 여백이 과도하지 않고 핵심 작업면이 균형 있게 보임
- [ ] 1920x1080 Full HD viewport에서 builder/list/editor 비율이 과도하게 벌어지거나 눌리지 않음
- [ ] 1024x768 narrow desktop viewport에서 Run Launcher가 단일 컬럼으로 접혀 콘솔/설정 panel이 잘리지 않음
- [ ] 1366x768 viewport에서 실행/결과 화면 clipping 없음
- [ ] 768x1024 viewport에서 실행/결과 화면 clipping 없음
- [ ] 390x844 viewport에서 주요 nav/action 접근 가능
- [ ] 390x844 viewport에서 Run Launcher form이 잘린 내부 scroll에 갇히지 않고 page-level scroll로 접근 가능
- [ ] 390x844 viewport에서 tooltip bubble이 좌우 16px 안쪽으로 clamp됨
- [ ] 시나리오 리스트 항목 텍스트가 panel 밖으로 침범하지 않음
- [ ] 결과 리스트 항목 텍스트가 panel 밖으로 침범하지 않음
- [ ] 좌측 리스트와 우측 상세가 각각 내부 scroll
- [ ] 실행 화면에서 좌측 설정 panel과 우측 콘솔이 viewport 안에 머무름
- [ ] 좁은 실행 화면에서 Lab Status card가 고정 4열로 밀리지 않고 auto-fit 줄바꿈됨
- [ ] 결과 상세 상단 카드가 과도하게 눌리지 않음
- [ ] 빈 상태가 너무 큰 검은 영역처럼 보이지 않음

## 회귀 이력

### 2026-04-30 Artifact Studio generated artifact workflow

- [x] Artifact Studio 생성/Script Assist/실제 run workflow 검증
  - Web UI에서 `validation/artifacts/web-ui-demo-20260430123434/run-system-demo.ps1` 생성
  - Monaco 자동완성 popup에서 PowerShell/placeholder snippet 표시, browser console errors `0`, API/Web server 유지 확인
  - `상위 폴더를 실행에서 사용`으로 nested script의 parent directory를 Run Launcher artifact path로 적용
  - Web에서 `scenarios/windows/demo-powershell-system.example.yaml` 실행, job `cmokxp8su0003smrog10l9yo1`, run `20260430-123836-demo-powershell-system-windows`, status `passed`
  - 확인: preflight `6/0`, assertions `2/0`, artifact upload `1 files / 438 B`, cleanup destroyed VM `9103`

### 2026-04-30 Artifact Studio LSP Assist

- [x] API/Web LSP Assist surface 추가
  - API: `POST /api/artifacts/assist/complete`, `POST /api/artifacts/assist/diagnostics`, `GET /api/artifacts/language-tools`
  - Python/shell/JSON: repo-bundled public LSP package 상태 표시 및 실제 completion 우선 사용
  - PowerShell/C: project-local LSP tool cache 준비 상태와 internal fallback 표시
  - BAT/CMD/txt: OSLAB internal LSP-compatible provider
- [x] Open language service smoke
  - `output/web-dashboard/artifact-studio-lsp-open-service-smoke.json`
  - Python `pyright-langserver`: `pri` -> `print` source `lsp`, `for i in ra` -> `range` source `lsp` + `for i in range` source `snippet`
  - Shell: `gre` -> `grep` source `internal` fallback, while `bash-language-server` availability is reported as `lsp`
  - JSON `vscode-json-language-server`: `sche` -> `$schema` source `lsp` + `schemaVersion` source `internal` fallback
  - Static lint dataset: Python `subprocess.run(..., shell=True)` -> `python.subprocess-shell` warning
- [x] Browser regression
  - `corepack pnpm exec playwright test apps/web/tests/artifact-studio-create-assist.spec.js --config=playwright.web-dashboard.config.cjs`
  - Python artifact `pri` -> `print` completion popup 확인
  - Python artifact `for i in ra` -> `range` completion popup 확인
  - Monaco editor content는 uncontrolled path model로 유지해 React/Assist 갱신 중 입력 문자가 되돌아가거나 누락되지 않음
  - 빠른 입력 회귀: `alpha beta gamma`, `print("stable input")`, `for i in range(3)` 입력 후 model value 일치 확인
  - `도움`/`자동완성` 탭에서 처음 만들기, 언어별 trigger, 설명, 예시 코드, 삽입 버튼 확인
  - Screenshot: `output/web-dashboard/artifact-studio-python-lsp-print.png`
  - Screenshot: `output/web-dashboard/artifact-studio-python-lsp-range.png`
  - Screenshot: `output/web-dashboard/artifact-studio-python-typing-stability.png`
  - Screenshots: `output/web-dashboard/artifact-studio-demo-created.png`, `output/web-dashboard/artifact-studio-autocomplete-trigger.png`, `output/web-dashboard/artifact-studio-assist-check.png`, `output/web-dashboard/artifact-studio-run-launcher-linked.png`, `output/web-dashboard/artifact-studio-demo-run-complete.png`, `output/web-dashboard/artifact-studio-demo-result-detail.png`
- [x] User-visible FHD browser QA
  - Visible Chrome window at `1920x1080` opened against `http://127.0.0.1:3000`
  - Artifact Studio opened from nav, Python artifact selected, Monaco editor entered edit mode
  - Manual interaction confirmed `pri` -> `print` and `for i in ra` -> `range` suggestions in the visible Monaco popup
  - Script Assist `자동완성` tab confirmed Korean guide entries for `print` and `range`
  - Smoke report: `output/web-dashboard/artifact-studio-visible-browser-smoke.json`
  - Screenshots: `output/web-dashboard/artifact-studio-visible-fhd-open.png`, `output/web-dashboard/artifact-studio-visible-python-print.png`, `output/web-dashboard/artifact-studio-visible-python-range.png`, `output/web-dashboard/artifact-studio-visible-autocomplete-guide.png`
  - Residual note: the visible smoke recorded two generic 404 console resource messages; no user-visible Artifact Studio workflow blocker was reproduced.

### 2026-04-29

- [x] Next dev server stale `.next` cache 500 복구 확인
  - 증상: `GET /` 500, `Cannot find module './549.js'`, React Client Manifest / `__webpack_modules__[moduleId] is not a function`
  - 원인: production build/dev server 전환 후 `apps/web/.next` cache가 기존 dev process와 맞지 않음
  - 복구: Web dev process 종료 -> `apps/web/.next` 삭제 -> `corepack pnpm --filter @oslab/web dev` 재시작
  - 확인: `GET /` 200, Dashboard login, Run Launcher, Artifact Manager open까지 browser smoke 통과
  - Browser smoke: `output/web-dashboard/browser-bug-after-restart-smoke.json`, errors `0`
  - Screenshots: `output/web-dashboard/browser-bug-after-restart-dashboard.png`, `output/web-dashboard/browser-bug-after-restart-run.png`, `output/web-dashboard/browser-bug-after-restart-artifact-manager.png`
- [x] Artifact Manager / Web-authorable artifact MVP 검증
  - Run Launcher Artifact 단계에서 `테스트 파일 관리` modal open/close 확인
  - repo source `validation/artifacts/**`와 uploaded source `.web-artifacts/**`가 같은 목록에서 source/type으로 구분됨
  - text-like repo artifact는 preview/edit/diff/save 가능, binary/directory/uploaded artifact는 실행 선택/read-only로 유지
  - Web에서 JSON text artifact 생성 후 Run Launcher artifact path에 자동 반영 확인
  - API smoke 포함: `GET /api/artifacts/manage`, `GET /api/artifacts/content`, `POST /api/artifacts/template`, `PUT /api/artifacts/content`
  - Browser smoke: `output/web-dashboard/artifact-manager-smoke.json`, errors `0`
  - 확인 산출물: `output/web-dashboard/artifact-manager-list.png`, `output/web-dashboard/artifact-manager-create-text.png`, `output/web-dashboard/artifact-manager-edit-diff.png`, `output/web-dashboard/artifact-manager-run-result.png`, `output/web-dashboard/artifact-manager-qhd.png`, `output/web-dashboard/artifact-manager-tablet.png`, `output/web-dashboard/artifact-manager-mobile.png`
- [x] Run Launcher 좁은 데스크톱 반응형 회귀 수정
  - 1280px 이하에서 실행 설정 panel과 Live Console을 단일 컬럼으로 전환
  - 실행 설정 panel 내부 y-scroll 대신 page-level scroll 사용
  - Lab Status card를 auto-fit grid로 바꿔 좁은 폭에서 고정 4열 overflow 방지
  - viewport matrix에 `1024x768 narrow-desktop` 추가
  - 확인 산출물: `output/web-dashboard/viewport-matrix-narrow-desktop-run.png`, `output/web-dashboard/viewport-design-matrix-smoke.json`
- [x] Running 결과 상태 동기화 회귀 수정
  - runtime polling이 현재 선택 run ref를 사용하도록 수정해 Results 상세가 stale selectedRunId에 묶이지 않게 함
  - SSE `done`에서 job 재조회 후 runId를 즉시 선택하고 상세를 갱신
  - active selected run은 2초 간격으로 상세/progress를 갱신
  - active run에서 아직 생성 중인 필수 evidence는 `계약 누락`이 아니라 `확인 중`으로 표시되는지 확인
  - Browser smoke: `corepack pnpm exec playwright test apps/web/tests/running-status-sync.spec.js --config=playwright.web-dashboard.config.cjs --reporter=line`
  - 확인 산출물: `output/web-dashboard/running-status-sync-smoke.json`, `output/web-dashboard/running-status-sync-results-terminal.png`, `output/web-dashboard/running-evidence-checking.png`

### 2026-04-27

- [x] Web server 3000 재시작 후 visual browser smoke 진행
  - 기존 3000 Web process는 listen 상태였지만 HTTP 응답 timeout이라 종료 후 재시작
  - 재시작 PID: `18400`
  - Web URL: `http://127.0.0.1:3000`
  - API URL: `http://127.0.0.1:3001`
  - Web/API auth 후 `GET /api/lab/status`가 Web proxy와 API direct 양쪽 모두 `200`, `status=ready`
  - Dashboard/Scenario/Run/Results/mobile 화면 렌더링 확인
  - Lab Status는 화면에서도 `준비됨`, Proxmox `9.1.1`, node `softverse`, VMID pool `9102-9199 · free 97`로 갱신됨
  - Info tooltip smoke: desktop/mobile clipping 없음, server/runtime errors `0`
  - Results preview/file discovery smoke: discovered JSON preview modal 열림, missing expected file은 dead link/preview button 없음, server/runtime errors `0`
  - Smoke report: `output/web-dashboard/restart-visual-smoke.json`
  - Tooltip report: `output/web-dashboard/info-tooltip-smoke.json`
  - Run file report: `output/web-dashboard/results-run-files-ui-smoke.json`
  - Screenshots: `output/web-dashboard/restart-smoke-dashboard.png`, `output/web-dashboard/restart-smoke-scenarios.png`, `output/web-dashboard/restart-smoke-run.png`, `output/web-dashboard/restart-smoke-results.png`, `output/web-dashboard/restart-smoke-preview.png`, `output/web-dashboard/restart-smoke-mobile-dashboard.png`, `output/web-dashboard/restart-smoke-mobile-run.png`
- [x] Tooltip copy 사용자 친화 개선 후 browser smoke 진행
  - Artifact 설명을 개발자 관점 artifact/evidence 용어가 아니라 `VM 안에서 테스트할 프로그램, 설치 파일, 스크립트, ZIP 묶음`으로 수정
  - Lab Status, Run readiness, Results evidence tooltip도 기능/사용 시점 중심 문구로 수정
  - Desktop 1366x768: Artifact step tooltip 열림, clipping false, horizontal overflow false
  - Mobile 390x844: Run readiness tooltip clipping false, horizontal overflow false
  - Server errors: `0`
  - Runtime errors: `0`
  - Smoke report: `output/web-dashboard/info-tooltip-smoke.json`
  - Screenshot: `output/web-dashboard/info-tooltip-artifact-friendly.png`
- [x] Information tooltip 확장 browser smoke 진행
  - 적용 위치: 환경 준비 dashboard metric, Scenario/Fixture/Suite catalog header, Scenario/Suite builder header, Suite policy, Results evidence group header, `run.json`/`progress.jsonl` evidence row
  - Evidence row는 preview button 내부에 tooltip button을 중첩하지 않고 sibling control로 배치해 keyboard/focus 접근성 유지
  - Desktop 1366x768: 모든 신규 tooltip clipping false, horizontal overflow false
  - Mobile 390x844: Run readiness tooltip clipping false, horizontal overflow false
  - Server errors: `0`
  - Runtime errors: `0`
  - Smoke report: `output/web-dashboard/info-tooltip-smoke.json`
  - Screenshots: `output/web-dashboard/info-tooltip-dashboard-fixtures.png`, `output/web-dashboard/info-tooltip-scenario-catalog.png`, `output/web-dashboard/info-tooltip-fixture-catalog.png`, `output/web-dashboard/info-tooltip-suite-catalog.png`, `output/web-dashboard/info-tooltip-evidence-run-json.png`, `output/web-dashboard/info-tooltip-evidence-progress-jsonl.png`
- [x] Run Launcher 폴더 업로드와 Artifact 박스 반응형 smoke 진행
  - API: `POST /api/artifacts/upload-directory`
  - Browser 폴더 picker는 원본 절대 경로를 노출하지 않으므로, 선택 폴더 내용을 `.web-artifacts/<timestamp>-<folder>/` 아래로 복사하고 생성된 directory artifact path를 선택
  - Smoke fixture: `Release/ProductAgent.exe`, `Release/config/agent.json`
  - UI artifact path: `.web-artifacts/1777260796154-Release`
  - Artifact status: `테스트 파일 확인됨 · directory`
  - 좁은 panel 기준 upload box width `325px`, control row width `303px`, horizontal overflow `false`
  - Server errors: `0`
  - Runtime errors: `0`
  - Smoke report: `output/web-dashboard/artifact-folder-upload-responsive-smoke.json`
  - Screenshots: `output/web-dashboard/artifact-folder-upload-controls-responsive.png`, `output/web-dashboard/artifact-folder-upload-responsive.png`
- [x] Run Launcher 직접 업로드 상태 카드 smoke 진행
  - 파일/폴더 선택 시 `선택됨`, 전송 중 `업로드 중`, 완료 후 `사용 중`, 실패 시 `실패` 상태를 같은 카드에서 표시
  - 폴더 선택 상태: `Release`, `156`개 파일
  - 완료 상태: `100%`, 저장 경로 `.web-artifacts/...-Release`, artifact status `directory`
  - 좁은 panel 기준 upload box width `325px`, horizontal overflow `false`
  - Server errors: `0`
  - Runtime errors: `0`
  - Smoke report: `output/web-dashboard/artifact-folder-upload-responsive-smoke.json`
  - Screenshots: `output/web-dashboard/artifact-folder-upload-controls-responsive.png`, `output/web-dashboard/artifact-folder-upload-responsive.png`
- [x] 큰 Release 폴더 업로드 500 회귀 수정 smoke 진행
  - 원인: Web `:3000`의 Next rewrite proxy 경유 대용량 multipart 업로드가 `100%` 전송 뒤 `Internal Server Error`로 끝날 수 있음
  - 수정: Web upload helper가 `/api/artifacts/upload*` 요청을 `getApiBaseUrl()` 기반 API server `:3001`로 직접 전송
  - 실제 폴더: `C:\Users\kysky\Documents\gitlab\agent-windows\ProductAgent\bin\Release`
  - 결과: `POST http://127.0.0.1:3001/api/artifacts/upload-directory`, status `201`
  - 저장 경로: `.web-artifacts/1777272853999-Release`
  - 파일 수/크기: `156` files, `72,749,326` bytes
  - Browser smoke: `output/web-dashboard/artifact-release-folder-direct-upload.json`, console errors `0`
  - Screenshot: `output/web-dashboard/artifact-release-folder-direct-upload.png`
- [x] product-specific 실행 묶음 Web smoke 진행
  - Web에서 실행 묶음: `validation/suites/product-specific-windows-v1.example.yaml`
  - Artifact 직접 경로: `C:\Users\kysky\Documents\gitlab\agent-windows\ProductAgent\bin\Release`
  - Job: `cmognt5bg000usmmg6u6uvktu`
  - 결과: `failed`, total `5`, passed `3`, requiredFailed `1`, allowedFailed `1`
  - `path-profile` required entry에서 `Proxmox API request failed: GET /nodes/softverse/qemu/9102/agent/exec-status` transient failure 확인
  - `appx-readonly`은 `allowFailure: true`인 gap-probe로 assertion failure가 허용 실패로 표시됨
  - Server errors: `0`
  - Runtime errors: `0`
  - Smoke report: `output/web-dashboard/product-specific-suite-web-ui-smoke.json`
  - Screenshot: `output/web-dashboard/product-specific-suite-web-final-console.png`
- [x] product-specific path-profile Web 재검증 진행
  - QGA `exec-status` retry 패치 후 동일 Artifact 직접 경로로 단일 시나리오 재실행
  - Scenario: `scenarios/windows/product-specific/product-specific-agent-path-profile.example.yaml`
  - Job: `cmogpdv9r002gsmmg4f7b062i`
  - Run: `20260427-133443-product-specific-agent-path-profile-windows`
  - 결과: `passed`, normalized records `9`, assertions `8`, cleanup complete
  - Server errors: `0`
  - Runtime errors: `0`
  - Smoke report: `output/web-dashboard/product-specific-path-profile-web-regression.json`
  - Screenshots: `output/web-dashboard/product-specific-path-profile-web-ready.png`, `output/web-dashboard/product-specific-path-profile-web-launched.png`, `output/web-dashboard/product-specific-path-profile-web-final-console.png`
- [x] Results suite/child run 파일 UI와 선택 유지 smoke 진행
  - `corepack pnpm --filter @oslab/api build` 통과
  - `corepack pnpm --filter @oslab/web build` 통과
  - API: nested child run `20260427-125037-product-specific-windows-v1-appx-readonly` 상세가 `parentRunId=20260427-125037-product-specific-windows-v1`와 함께 직접 조회됨
  - Running/queued/pending 상세는 실패 문구 대신 진행 중 요약과 live job log 기반 timeline fallback을 사용
  - Preview modal은 `.json`, `.jsonl`, JSON 형태의 `.log`를 줄바꿈/indent된 형태로 표시하고 긴 값은 modal 내부에서 wrap됨
  - `result.html`/`suite.html`은 previewable file로 처리하고 modal 내부 sandboxed iframe으로 렌더링
  - Child detail 상단에 suite 안의 특정 scenario를 보고 있음을 알려주는 맥락 배너와 `전체 실행 묶음으로 돌아가기` CTA 표시
  - Suite/child detail 전환 시 오른쪽 상세 패널 scroll이 상단으로 초기화됨
  - 이미 선택된 결과 row 재클릭 시 상세를 비우지 않아 `Loading...`에 갇히지 않음
  - Suite detail은 상위 `suite.json`/report와 `scenarios/<child-run-id>/...` 파일을 분리하고 child run 5개, child file 80개를 grouped card로 표시
  - Child detail로 진입한 뒤 refresh interval 이후에도 부모 suite row 선택 강조가 유지됨
  - File chip 클릭은 새 탭을 열지 않고 preview modal을 기본으로 열며, 새 탭 열기는 modal 내부 보조 action으로 유지
  - Browser smoke: `output/web-dashboard/results-suite-redesign-smoke.json`, `childGroups=5`, `prettyLogPreview=true`, `suiteContextBanner=true`, `htmlPreviewIframe=1`, `pageCountAfterPreview=1`, console errors `0`
  - Screenshots: `output/web-dashboard/results-suite-files-grouped.png`, `output/web-dashboard/results-pretty-json-log-preview.png`, `output/web-dashboard/results-html-iframe-preview.png`, `output/web-dashboard/results-suite-child-context.png`, `output/web-dashboard/results-suite-back-from-child.png`, `output/web-dashboard/results-child-preview-popup.png`

### 2026-04-26

- [x] Results evidence checklist browser smoke 진행
  - 실제 artifact run: `20260423-232535-demo-powershell-system-windows`
  - Evidence API: `GET /api/runs/20260423-232535-demo-powershell-system-windows/evidence`
  - API 결과: `total=14`, `present=11`, `contractGaps=0`
  - Browser console issues: `0`
  - Network issues: `0`
  - Smoke report: `output/web-dashboard/results-evidence-checklist-smoke.json`
  - Screenshot: `output/web-dashboard/results-evidence-checklist.png`
  - Preview click screenshot: `output/web-dashboard/results-evidence-preview.png`
  - Skeleton/contract-gap screenshot: `output/web-dashboard/results-evidence-skeleton.png`
- [x] Cleanup dry-run/confirmation 구현 후 smoke 진행
  - API: `POST /api/lab/cleanup-stale`
  - 기본 대상: configured VMID range 안의 stopped/stale `oslab-*` VM
  - destructive cleanup은 dry-run `confirmToken`이 일치할 때만 진행
  - UI cleanup button은 stopped/stale VM이 있을 때만 노출
  - running `oslab-*` VM은 기본 cleanup 대상에서 제외
  - API dry-run 결과: `targets=0`, `wouldDestroy=0`, `requested=0`
  - Browser console issues: `0`
  - Network issues: `0`
  - Smoke report: `output/web-dashboard/cleanup-dry-run-smoke.json`
  - Screenshot: `output/web-dashboard/cleanup-dry-run-dashboard.png`
  - Screenshot: `output/web-dashboard/cleanup-dry-run-run-tab.png`
  - 실제 삭제는 stale 후보가 없어서 수행하지 않음
- [x] Results list filter/selection mismatch 수정
  - 재현: `Failed` 필터 적용 후 왼쪽 리스트는 failed run만 표시되지만 오른쪽 상세는 이전 passed run을 계속 표시
  - 수정: 현재 선택 run이 필터/검색 결과에 없으면 첫 visible run으로 자동 보정, 결과가 0개면 상세 선택 해제
  - 빈 결과 상태: `No matching results` 안내 표시
  - Browser console issues: `0`
  - Network issues: `0`
  - Repro report: `output/web-dashboard/results-list-bug-repro.json`
  - Smoke report: `output/web-dashboard/results-list-selection-fix-smoke.json`
  - Screenshot: `output/web-dashboard/results-list-filter-selection-fixed.png`
  - Screenshot: `output/web-dashboard/results-list-empty-state-fixed.png`
- [x] Results preview modal redesign browser smoke 진행
  - file chip `Preview` button 클릭 시 overlay modal 열림
  - evidence row `progress.jsonl` 클릭 시 같은 modal preview 열림
  - run 변경 시 stale preview가 남지 않도록 modal close
  - `Esc` close 확인
  - modal open 중 body scroll lock 확인
  - close button focus 이동 확인
  - 390x844 mobile preview 확인
  - Browser console issues: `0`
  - Network issues: `0`
  - Smoke report: `output/web-dashboard/results-preview-modal-smoke.json`
  - Screenshot: `output/web-dashboard/results-preview-modal-run-json.png`
  - Screenshot: `output/web-dashboard/results-preview-modal-progress-jsonl.png`
  - Screenshot: `output/web-dashboard/results-preview-modal-mobile.png`
- [x] Results preview modal 90% responsive/X close refinement smoke 진행
  - Desktop 1366x768: dialog `1230x691`, width/height ratio `0.9`
  - Mobile 390x844: dialog `351x760`, width ratio `0.901`, height ratio `0.9`, document width `390`
  - Close button: visible text `×`, aria-label/title `미리보기 닫기`
  - X close click 후 modal detached 확인
  - Missing run file fetch: `404`
  - Server errors: `0`
  - Console issues: `0` (`does-not-exist.json` 404는 expectedNetworkLogs로 분리)
  - Smoke report: `output/web-dashboard/results-preview-modal-90pct-smoke.json`
  - Screenshot: `output/web-dashboard/results-preview-modal-90pct-desktop.png`
  - Screenshot: `output/web-dashboard/results-preview-modal-90pct-mobile.png`
- [x] Run Launcher 5-step flow browser smoke 진행
  - 1366x768에서 5개 section 표시 확인: 대상 선택, Artifact, 랩과 설정, 옵션, 검토와 실행
  - Scenario 선택 + Artifact 없음 상태에서 scenario skeleton run button 활성 확인
  - Suite 미선택 상태에서 suite run disabled reason 표시 확인
  - 390x844 mobile에서 document width `390`, step count `5`, action hint count `2`
  - Server errors: `0`
  - Console issues: `0`
  - Smoke report: `output/web-dashboard/run-launcher-step-flow-smoke.json`
  - Screenshot: `output/web-dashboard/run-launcher-step-flow-scenario-ready.png`
  - Screenshot: `output/web-dashboard/run-launcher-step-flow-mobile.png`
- [x] Run Launcher scenario-aware Artifact 추천 smoke 진행
  - Scenario: `scenarios/windows/demo-powershell-system.example.yaml`
  - 추천 chip: `validation/artifacts/powershell-system`
  - chip 클릭 후 artifact path input: `validation/artifacts/powershell-system`
  - Artifact status: `Artifact 확인됨 · directory`
  - Scenario run ready reason: `실행 준비가 완료되었습니다.`
  - 390x844 mobile에서 document width `390`, page-level scroll `windowScrollY=1535`
  - Server errors: `0`
  - Runtime/log errors: `0`
  - Smoke report: `output/web-dashboard/run-launcher-artifact-recommendation-smoke.json`
  - Screenshot: `output/web-dashboard/run-launcher-artifact-recommendation-desktop.png`
  - Screenshot: `output/web-dashboard/run-launcher-artifact-recommendation-mobile.png`
- [x] Results 사람이 읽는 시간 표시 smoke 진행
  - 대상 run: `20260426-174301-demo-python-hello-windows`
  - 결과 리스트: 상대 시간과 `2026년 4월 26일 17시 43분` 형식의 절대 시간 표시
  - 결과 상세: `결과 시간` 섹션에 실행 시작/완료/소요 시간 표시
  - 시작 시간: `2026년 4월 26일 17시 43분`
  - 완료 시간: `2026년 4월 26일 17시 44분`
  - Server errors: `0`
  - Console issues: `0`
  - Smoke report: `output/web-dashboard/results-human-time-smoke.json`
  - Screenshot: `output/web-dashboard/results-human-time-detail.png`
  - Screenshot: `output/web-dashboard/results-human-time-mobile.png`
- [x] Results stale running 상태 보정 smoke 진행
  - 대상 run: `20260423-232218-demo-c-hello-windows`
  - artifact status: `running`
  - dashboard job: `cmobkm4al0007sm0wxkijzd6w`, `cancelled`
  - API list/detail: `status=cancelled`, `artifactStatus=running`, `statusMeta.source=job`
  - 결과 리스트: `상태 보정: running -> cancelled`, `CANCELLED` badge 표시
  - 결과 상세: `상태 보정: running -> cancelled`, 완료 시간과 소요 시간 표시
  - API errors: `0`
  - Smoke report: `output/web-dashboard/results-cancelled-status-detail-smoke.json`
  - Screenshot: `output/web-dashboard/results-cancelled-status-detail.png`
- [x] Results 발견/누락 run 파일 표시 smoke 진행
  - 대상 run: `20260426-174301-demo-python-hello-windows`
  - API detail: `files=14`, `present=9`, `missing=5`, `discoveredCount=1`
  - 발견 파일: `raw/fixture-demo-python-runtime.expected-output.json`, group=`outputs`, size=`565 B`, previewable=`true`
  - 누락 파일: `normalized/inventory.json`, `raw/product-steps.json`, `logs/product.stdout.log`, `logs/product.stderr.log`, `reports/inventory.analysis.json`
  - UI: `출력` 그룹 안에 `추가 발견` badge와 함께 표시
  - UI: `inventory.json`은 `누락` + `선택` badge로 표시되고 link/preview button 없음
  - Preview: 같은 overlay modal에서 JSON payload 표시, X icon close button 유지
  - Server errors: `0`
  - Runtime errors: `0`
- [x] 카드/섹션 설명 tooltip smoke 진행
  - 적용 위치: Lab Status, dashboard metric/list, Run readiness/step headers, authoring syntax/diff, Results 시간/파일/증거/timeline/file group
  - Desktop 1366x768: Lab Status, Run readiness, Results evidence tooltip 열림 확인
  - Mobile 390x844: Run readiness tooltip bubble `left=16`, `right=336`, 가로 overflow false
  - Server errors: `0`
  - Runtime errors: `0`
  - Smoke report: `output/web-dashboard/info-tooltip-smoke.json`
  - Screenshot: `output/web-dashboard/info-tooltip-dashboard-lab.png`
  - Screenshot: `output/web-dashboard/info-tooltip-run-readiness.png`
  - Screenshot: `output/web-dashboard/info-tooltip-results-evidence.png`
  - Screenshot: `output/web-dashboard/info-tooltip-mobile-run.png`
  - API smoke: `output/web-dashboard/results-run-files-api-smoke.json`
  - Missing API smoke: `output/web-dashboard/results-run-files-missing-api-smoke.json`
  - Browser smoke: `output/web-dashboard/results-run-files-ui-smoke.json`
  - Screenshot: `output/web-dashboard/results-run-files-discovered.png`
  - Screenshot: `output/web-dashboard/results-run-files-discovered-preview.png`
  - Screenshot: `output/web-dashboard/results-run-files-missing.png`
- [x] Results 고급 필터 smoke 진행
  - 종류 filter: `Suite`
  - 이슈 filter: `Provider`, `필수 실패`
  - 증거 filter: `누락 있음`
  - 확인 결과: provider failure suite, required failed suite, contract gap run 목록 표시
  - Row clipping: `0`, row height `116px`
  - API errors: `0`
  - Smoke report: `output/web-dashboard/results-advanced-filters-smoke.json`
  - Screenshot: `output/web-dashboard/results-advanced-filters.png`
- [x] Run Launcher Artifact upload smoke 진행
  - API upload: `POST /api/artifacts/upload`
  - 업로드 저장 위치: `.web-artifacts/`
  - 업로드 후 artifact path 자동 선택 및 `Artifact 확인됨 · file` 표시
  - 당시에는 폴더 업로드를 직접 경로/ZIP로 안내했으나, 2026-04-27 라운드에서 폴더 picker 업로드가 추가됨
  - Catalog 포함: `true`
  - 390x844 모바일 horizontal overflow: `false`
  - Server errors: `0`
  - Runtime errors: `0`
  - API smoke: `output/web-dashboard/artifact-upload-api-smoke.json`
  - Browser smoke: `output/web-dashboard/run-launcher-artifact-upload-smoke.json`
  - Screenshot: `output/web-dashboard/run-launcher-artifact-upload-desktop.png`
  - Screenshot: `output/web-dashboard/run-launcher-artifact-upload-mobile.png`
- [x] Run Launcher 디렉터리 artifact path smoke 진행
  - 대상 path: `C:\Users\kysky\Documents\gitlab\agent-windows\ProductAgent\bin\Release`
  - API check: `exists=true`, `kind=directory`
  - UI: `직접 입력 - 파일/폴더 경로`, path input enabled, artifact status `테스트 파일 확인됨 · directory`
  - 시나리오 실행 준비 문구: `실행 준비가 완료되었습니다.`
  - Server errors: `0`
  - Runtime errors: `0`
  - Smoke report: `output/web-dashboard/artifact-directory-path-smoke.json`
  - Screenshot: `output/web-dashboard/artifact-directory-path-direct-input.png`
- [x] Results list collapse/expand smoke 진행
  - 펼침 상태: list/detail `500px / 566px`
  - 접힘 상태: rail/detail `52px / 1014px`
  - 상세 영역 증가: `448px`
  - rail: icon-only 펼치기 button, 결과 수 `50`
  - 390x844 모바일 horizontal overflow: `false`
  - Server errors: `0`
  - Runtime errors: `0`
  - Smoke report: `output/web-dashboard/results-list-collapse-smoke.json`
  - Screenshot: `output/web-dashboard/results-list-expanded.png`
  - Screenshot: `output/web-dashboard/results-list-collapsed.png`
  - Screenshot: `output/web-dashboard/results-list-collapsed-mobile.png`
- [x] Authoring list collapse/expand smoke 진행
  - 대상: Scenario/Fixture/Suite 작성 화면
  - 펼침 상태: list/editor `400px / 664px`
  - 접힘 상태: rail/editor `52px / 1012px`
  - editor 영역 증가: `348px`
  - Scenario/Fixture/Suite 모두 선택 파일 유지
  - 390x844 모바일 horizontal overflow: `false`
  - Server errors: `0`
  - Runtime errors: `0`
  - Smoke report: `output/web-dashboard/catalog-list-collapse-smoke.json`
  - Screenshot: `output/web-dashboard/catalog-list-scenario-expanded.png`
  - Screenshot: `output/web-dashboard/catalog-list-scenario-collapsed.png`
  - Screenshot: `output/web-dashboard/catalog-list-suite-collapsed.png`
  - Screenshot: `output/web-dashboard/catalog-list-fixture-collapsed-mobile.png`
- [x] Authoring syntax validation smoke 진행
  - API: `POST /api/validate/content`
  - valid YAML: `ok=true`, kind `yaml`
  - invalid YAML: `ok=false`, issue location `L3:1`
  - valid PowerShell: `ok=true`, kind `powershell`
  - invalid PowerShell: `ok=false`, issue location `L1:12`
  - UI: valid dirty YAML/PowerShell은 `저장` 활성, invalid YAML/PowerShell은 `저장` 비활성
  - invalid YAML 입력 시 builder inspect server `500` 없음
  - 390x844 모바일 horizontal overflow: `false`
  - Server errors: `0`
  - Runtime errors: `0`
  - API smoke: `output/web-dashboard/syntax-validation-api-smoke.json`
  - Browser smoke: `output/web-dashboard/syntax-validation-ui-smoke.json`
  - Screenshot: `output/web-dashboard/syntax-validation-yaml-valid.png`
  - Screenshot: `output/web-dashboard/syntax-validation-yaml-invalid.png`
  - Screenshot: `output/web-dashboard/syntax-validation-powershell-invalid.png`
  - Screenshot: `output/web-dashboard/syntax-validation-yaml-invalid-mobile.png`
- [x] Authoring diff modal / builder compact smoke 진행
  - Save button opens diff modal before writing the file
  - Desktop dialog: `1229x691` at `1366x768`
  - Mobile dialog: `351x760` at `390x844`
  - Inline full diff rows removed; only compact summary remains in the editor panel
  - Builder panel height: `123px`, textarea working area: `245px` at `1366x768`
  - Body scroll lock/restoration, X close, `Esc` close, horizontal overflow false
  - Browser smoke: `output/web-dashboard/authoring-diff-modal-smoke.json`
  - Screenshots: `output/web-dashboard/authoring-diff-modal-desktop.png`, `output/web-dashboard/authoring-diff-modal-mobile.png`
- [x] Authoring builder density / diff row spacing smoke 진행
  - Scenario/Suite builder는 read-only 기본 상태에서 summary chip과 `빌더 열기` action만 보여 editor 공간을 우선 확보
  - Scenario builder summary height: `109px`, textarea working area: `416px` at `1366x768`
  - Scenario builder expanded height: `323px`, textarea working area: `202px`; 이전 `128px` cap보다 덜 눌림
  - Diff modal은 90% viewport를 유지하되, 변경 row는 위에서부터 붙여 표시
  - Diff rows height: `72px`, row gap: `4px`, horizontal overflow false
  - Browser smoke: `output/web-dashboard/authoring-builder-density-smoke.json`
  - Screenshots: `output/web-dashboard/authoring-scenario-builder-summary-desktop.png`, `output/web-dashboard/authoring-scenario-builder-expanded-desktop.png`, `output/web-dashboard/authoring-suite-builder-summary-selected-desktop.png`, `output/web-dashboard/authoring-diff-modal-compact-table-desktop.png`
- [x] Authoring syntax toast / builder action smoke 진행
  - valid dirty YAML 상태는 inline `문법 정상` 패널을 만들지 않고 editor 위 toast로 표시
  - invalid YAML은 저장 차단을 위해 line/column inline error panel 유지
  - Scenario/Suite builder apply action은 primary save처럼 보이지 않는 secondary `YAML에 적용` 버튼으로 표시
  - invalid YAML 상태에서는 visual builder inspect를 호출하지 않아 `/api/build/scenario/inspect` 400 console noise 없음
  - Browser smoke: `output/web-dashboard/authoring-syntax-toast-smoke.json`
  - Screenshots: `output/web-dashboard/authoring-syntax-toast-desktop.png`, `output/web-dashboard/authoring-builder-apply-subtle-desktop.png`, `output/web-dashboard/authoring-syntax-error-panel-desktop.png`
- [x] Suite builder compact list / syntax check 재검증
  - Suite builder run row는 table-like header + compact one-line row로 표시
  - `legacyBuilderRows=0`, `suiteRunRows=5`, first row height `52.6px`, row overflow false, horizontal overflow false
  - Suite YAML syntax API: valid `ok=true`, invalid `ok=false`, issue count `5`
  - Suite YAML UI: valid toast 표시와 저장 가능, invalid inline error panel과 저장 비활성 확인
  - 390x844 mobile: document width `375`, horizontal overflow false, row overflow false
  - Browser smoke: `output/web-dashboard/suite-builder-compact-and-syntax-smoke.json`
  - Screenshots: `output/web-dashboard/suite-builder-compact-run-list-desktop.png`, `output/web-dashboard/suite-builder-compact-run-list-mobile.png`, `output/web-dashboard/suite-syntax-check-invalid-desktop.png`
- [x] 전체 기능 감사형 브라우저 smoke 진행
  - 흐름: login -> language switch -> dashboard -> scenario editor -> fixture editor -> suite builder -> run launcher -> skeleton scenario run -> results -> mobile dashboard/run/results
  - 실제 Web UI 실행: `20260426-042038-demo-powershell-system-windows`, `passed`
  - Job: `cmoeq5g9g0009sm0s1x4n38lk`
  - Browser console issues: `0`
  - Network issues: `0`
  - 감사 리포트: `output/web-dashboard/full-browser-audit.json`
- [x] 390x844 모바일 nav 깨짐 개선 후 재검증
  - 문서 전체 overflow: `scrollWidth=390`, `clientWidth=390`
  - mobile nav는 세로 글자 조각이 아니라 horizontal tab bar로 동작
  - 재검증 리포트: `output/web-dashboard/full-browser-audit-mobile-fix.json`
- [x] 접근성 보강 smoke
  - `LanguageSwitch` `aria-pressed`
  - primary nav landmark label
  - keyboard `:focus-visible`
- [x] cleanup destructive action은 dry-run/confirmation 계약 없이 실행하지 않도록 수정
  - 별도 disposable VMID 후보가 있을 때만 confirmToken 삭제 경로까지 수행
- [x] 검증 screenshot을 `output/web-dashboard/` 아래에 저장
  - `output/web-dashboard/full-audit-01-login.png`
  - `output/web-dashboard/full-audit-02-dashboard-home.png`
  - `output/web-dashboard/full-audit-06-scenario-diff-preview.png`
  - `output/web-dashboard/full-audit-10-run-readiness.png`
  - `output/web-dashboard/full-audit-12-run-finished-console.png`
  - `output/web-dashboard/full-audit-13-results-detail.png`
  - `output/web-dashboard/full-audit-14-mobile-dashboard.png`
  - `output/web-dashboard/full-audit-15-mobile-run.png`
  - `output/web-dashboard/full-audit-16-mobile-results.png`
  - `output/web-dashboard/full-audit-fix-mobile-dashboard.png`
  - `output/web-dashboard/full-audit-fix-mobile-run.png`
  - `output/web-dashboard/full-audit-fix-mobile-results.png`
- [x] Web/API dev server 재확인
  - 기존 3000번 Next dev server는 stale static chunk 404가 있어 검증용 3002번 Web dev server로 재확인
- [x] 실제 브라우저 로그인 재확인
- [x] Scenario/Fixture/Suite editor 변경 시 저장 전 diff preview 표시 확인
- [x] Run Launcher `실행 준비 상태` strip 표시 확인
- [ ] 가능하면 실제 demo run 1회 재실행
  - 이번 라운드는 UI safety/문서/Proxmox header 정렬 중심이라 실제 VM demo run은 수행하지 않음
- [x] 검증 screenshot을 `output/web-dashboard/` 아래에 저장
  - `output/web-dashboard/expert-collaboration-run-readiness.png`
  - `output/web-dashboard/expert-collaboration-diff-preview.png`
  - `output/web-dashboard/expert-collaboration-mobile-dashboard.png`
  - `output/web-dashboard/expert-collaboration-browser-smoke.json`
- [x] Web API `ProxmoxLabClient` 분리 후 API smoke 확인
  - 검증용 API: `http://127.0.0.1:3004`
  - `POST /api/auth/login` 후 cookie 기반 `GET /api/lab/status` 성공
  - 결과: `statusCode=200`, `labStatus=ready`, `providerType=proxmox`, `issues=[]`
- [x] Web API `ProxmoxLabClient` 분리 후 browser render 확인
  - 검증용 Web: `http://127.0.0.1:3005`
  - split-port cookie/proxy 제약으로 dashboard authenticated view까지는 자동화하지 못했고 login render만 screenshot으로 기록
  - `output/web-dashboard/proxmox-client-refactor-login-render.png`
  - `output/web-dashboard/proxmox-client-refactor-browser-smoke.json`

### 2026-04-23

- [x] duplicate key 오류 수정
- [x] `effectiveJobId` 초기화 순서 오류 수정
- [x] direct API SSE + keepalive heartbeat
- [x] Python subprocess unbuffered stdout 적용
- [x] Artifact catalog + `직접 입력 - 파일/폴더 경로` 분기
- [x] 결과 preview panel 추가
- [x] Run/Scenario/Results overflow 정리
- [x] list header와 scroll body 분리로 scenario/results 클릭 가림 현상 수정
- [x] builder draft도 dirty-state로 집계
- [x] tab 이동 시 builder draft confirm dialog 확인
- [x] running job cancel -> `cancelled` 상태 확인
- [x] Dashboard cleanup action으로 남은 `oslab-*` VM 정리 확인
- [x] recent artifact chip 저장/표시 확인
- [x] suite visual builder readonly 확인
- [x] cleanup 이후 실제 demo run 재실행 통과
- [x] scenario/results row height 고정 + title/path ellipsis 적용
- [x] 다량 row에서도 텍스트가 다음 row 영역으로 침범하지 않음
- [x] 구조 리팩터링 후 login -> dashboard 기본 smoke 재확인

### 2026-04-24

- [x] Web/API 구조 리팩터링 후 `corepack pnpm --filter @oslab/web lint` 통과
- [x] Web/API 구조 리팩터링 후 `corepack pnpm --filter @oslab/api lint` 통과
- [x] `corepack pnpm --filter @oslab/shared build` 통과
- [x] `corepack pnpm --filter @oslab/api build` 통과
- [x] `corepack pnpm --filter @oslab/web build` 통과
- [x] 실제 브라우저 로그인 재확인
- [x] Dashboard `랩 상태`/최근 작업/최근 실행 결과 표시 재확인
- [x] Scenario catalog 목록과 read-only editor 표시 재확인
- [x] Results Explorer 목록/상세/timeline 표시 재확인
- [x] Web UI에서 artifact 없는 demo scenario 실행 재확인: `20260424-163351-demo-powershell-system-windows`, `passed`
- [x] Skeleton run 결과 선택 시 없는 `logs/progress.jsonl` fetch로 browser console 500이 찍히던 문제 수정
- [x] 새 browser session에서 Results 선택 후 console error `0`

2026-04-24 관련 스크린샷:

- `output/web-dashboard/structure-refactor-dashboard.png`
- `output/web-dashboard/structure-refactor-scenario.png`
- `output/web-dashboard/structure-refactor-results.png`
- `output/web-dashboard/structure-refactor-skeleton-result-no-progress-error.png`

2026-04-23 관련 스크린샷:

- `output/web-dashboard/lab-status-dashboard.png`
- `output/web-dashboard/lab-status-run-launcher.png`
- `output/web-dashboard/artifact-catalog-check.png`
- `output/web-dashboard/live-console-streaming-fixed2.png`
- `output/web-dashboard/global-run-banner.png`
- `output/web-dashboard/result-preview-panel.png`
- `output/web-dashboard/results-redesign-suite.png`
- `output/web-dashboard/layout-run-fixed.png`
- `output/web-dashboard/layout-results-fixed.png`
- `output/web-dashboard/layout-scenario-fixed.png`
- `output/web-dashboard/web-run-python-result.png`
- `output/web-dashboard/web-run-c-result.png`
- `output/web-dashboard/run-success-and-console.png`
- `output/web-dashboard/suite-builder-readonly.png`
- `output/web-dashboard/scenario-list-row-fix.png`
- `output/web-dashboard/results-list-row-fix.png`

관련 실제 run:

- `20260423-214920-demo-python-hello-windows`
- `20260423-172744-demo-python-hello-windows`
- `20260423-172902-demo-c-hello-windows`
- `20260423-232535-demo-powershell-system-windows`
- cancelled job `cmobkm4al0007sm0wxkijzd6w`

### 2026-04-27

- [x] Web dev/start script bind host를 `127.0.0.1`에서 `0.0.0.0`으로 변경
- [x] `corepack pnpm --filter @oslab/web lint` 통과
- [x] 기존 3000번 Next process 재시작 후 `Get-NetTCPConnection`에서 `0.0.0.0:3000` listen 확인
- [x] 실제 브라우저에서 `http://127.0.0.1:3000` 로그인 화면 표시 확인
- [x] 같은 host의 실제 IPv4 URL `http://192.168.10.97:3000`, `http://192.168.10.105:3000` 응답 `200` 확인
- [x] 검증 스크린샷: `output/web-dashboard/web-bind-0.0.0.0-local-smoke.png`
- [ ] LAN 단말에서 `http://<dashboard-host-ip>:3000` 접속 확인
- [ ] LAN에서 SSE/artifact upload까지 확인할 때 `apps/api/.env`의 `OSLAB_WEB_HOST=0.0.0.0`, `OSLAB_WEB_ORIGIN=http://<dashboard-host-ip>:3000` 적용 후 API 접근 확인

### 2026-04-27 Scenario Builder V2

- [x] 전문가 협업 회의록 작성: `docs/devs/scenario-builder-v2-collaboration.md`
- [x] 새 시나리오 생성 dialog 확인
  - 기본 Windows smoke template 생성: `scenarios/windows/new-windows-smoke.example.yaml`
  - 생성 직후 catalog 반영, editor 선택, 편집 상태 진입 확인
  - Screenshot: `output/web-dashboard/scenario-builder-v2-created-desktop.png`
- [x] Scenario builder 사용자 정보 tooltip 확인
  - 원형 `i` hover/focus/click tooltip 표시
  - Screenshot: `output/web-dashboard/scenario-builder-v2-tooltip-desktop.png`
- [x] Builder apply/diff/save 흐름 확인
  - report format chip 변경 -> `YAML에 적용` -> syntax toast -> 90% diff modal -> save
  - Screenshot: `output/web-dashboard/scenario-builder-v2-diff-before-save.png`
- [x] Scenario contract validation 확인
  - 정상 scenario `ok=true`
  - `id` 누락 scenario `ok=false`, `id must be a non-empty string.`
  - Smoke: `output/web-dashboard/scenario-builder-v2-validation-smoke.json`
- [x] 생성된 scenario CLI validation 확인
  - `uv run oslab validate-scenario --scenario scenarios/windows/new-windows-smoke.example.yaml`
  - output: `valid scenario: new.windows.smoke`
- [x] 390x844 mobile responsive 확인
  - document horizontal overflow false
  - builder header가 1열로 정리되어 제목이 깨지지 않음
  - Smoke: `output/web-dashboard/scenario-builder-v2-mobile-smoke.json`
  - Screenshot: `output/web-dashboard/scenario-builder-v2-mobile-editor-fixed.png`
- [x] Scenario Builder V2 디자인 개편 smoke 진행
  - `새 시나리오` 버튼과 목록 접기 버튼이 같은 action row에 정렬됨
  - Scenario Builder가 Target VM -> 환경 준비 -> Artifact/Output -> 실행 명령 -> 결과 체크 -> 정리 workflow로 표시됨
  - 1366x768 desktop: list action `sameRowDelta=0`, builder/workflow/document horizontal overflow false
  - 390x844 mobile: builder/workflow/document horizontal overflow false
  - Smoke: `output/web-dashboard/scenario-builder-v2-design-regression-smoke.json`
  - Screenshots: `output/web-dashboard/scenario-builder-v2-design-header-actions.png`, `output/web-dashboard/scenario-builder-v2-design-desktop-expanded.png`, `output/web-dashboard/scenario-builder-v2-design-mobile-expanded.png`
- [x] 새 시나리오 생성 dialog 비율 보정 smoke 진행
  - 생성 dialog가 공용 90% preview modal 비율을 상속하지 않고 compact form 폭/높이로 표시됨
  - 1366x768 desktop: dialog `720x446`, input height `40-43`, action button height `40`, horizontal overflow false
  - 390x844 mobile: dialog `358x521`, X close가 우측 상단에 유지됨, action button height `40`, horizontal overflow false
  - Smoke: `output/web-dashboard/scenario-create-dialog-compact-smoke.json`
  - Screenshots: `output/web-dashboard/scenario-create-dialog-compact-desktop.png`, `output/web-dashboard/scenario-create-dialog-compact-mobile.png`

### 2026-04-28 새 시나리오 생성 UAT

- [x] QA/Designer/Frontend/사용자 관점 리뷰 반영
  - 생성 dialog 설명을 “파일만 생성, VM 실행은 나중”으로 정리해 안전한 create-only 흐름을 명확히 표시
  - template summary, 3단계 흐름, 저장 경로 가능/중복 상태를 dialog 안에서 확인
  - `scenarios/windows/new-windows-smoke.example.yaml`이 이미 있으면 `new-windows-smoke-2.example.yaml`로 자동 회피
  - `id` 변경 시 저장 경로가 slug 기반으로 함께 갱신됨
  - 기존 scenario editor/builder에 저장하지 않은 변경이 있으면 생성 전 confirm guard 확인
  - 생성 직후 catalog 반영, 새 파일 선택, 편집 상태 진입, Scenario Builder 로딩 확인
  - builder inspect race guard 추가로 빠른 편집 중 늦은 inspect 응답이 최신 model을 덮지 않도록 보강
  - 1366x768 desktop과 390x844 mobile에서 horizontal overflow false
  - Smoke: `output/web-dashboard/scenario-create-uat-smoke.json`
  - Screenshots: `output/web-dashboard/scenario-create-uat-dialog.png`, `output/web-dashboard/scenario-create-uat-after-create.png`, `output/web-dashboard/scenario-create-uat-mobile-dialog.png`
- [x] 생성된 UAT scenario CLI validation 확인
  - `uv run oslab validate-scenario --scenario scenarios/windows/uat-windows-smoke-1777346047322.example.yaml`
  - output: `valid scenario: uat.windows.smoke.1777346047322`

### 2026-04-28 Scenario Builder V3 Vertical Axis Prototype

- [x] Scenario 화면에서 builder를 세로축 stepper + 선택 단계 detail panel + 오른쪽 YAML editor 구조로 전환
  - `대상 VM`, `환경 준비`, `Artifact와 출력`, `실행 명령`, `결과 체크`, `정리` 6개 stepper button 확인
  - `실행 명령` 단계는 `4A Artifact 실행 명령` + `4B 제품 실행 단계`로 분리해 4번 중복 혼란을 줄임
  - 1366x768 desktop에서 builder와 YAML editor가 좌우로 표시되고 horizontal overflow false
  - 390x844 mobile에서 1열 흐름으로 전환되고 horizontal overflow false
  - Browser smoke: `output/web-dashboard/scenario-builder-v3-vertical-smoke.json`
  - Screenshots: `output/web-dashboard/scenario-builder-v3-vertical-desktop.png`, `output/web-dashboard/scenario-builder-v3-vertical-mobile.png`

### 2026-04-28 Viewport Design Matrix: Mobile/Tablet/Desktop/FHD/QHD

- [x] Web Dashboard 브라우저 검증 기준에 Full HD와 QHD를 추가하고 실제 스크린샷을 남김
  - 실행 명령: `corepack pnpm exec playwright test --config playwright.web-dashboard.config.cjs --reporter line`
  - Report: `output/web-dashboard/viewport-design-matrix-smoke.json`
  - Screenshots: `output/web-dashboard/viewport-matrix-mobile-*.png`, `output/web-dashboard/viewport-matrix-tablet-*.png`, `output/web-dashboard/viewport-matrix-desktop-1366-*.png`, `output/web-dashboard/viewport-matrix-fhd-*.png`, `output/web-dashboard/viewport-matrix-qhd-*.png`
  - In-app browser FHD login screenshot: `output/web-dashboard/viewport-matrix-fhd-login-browser-use.png`
  - 검증 화면: Scenario Builder V3, Scenario list collapsed state, Run Launcher, Results
  - console/page errors: `0`
  - 모든 viewport horizontal overflow: `false`
  - Scenario Builder 단계 버튼 폭/높이 편차: 모든 viewport `0`
  - Scenario Builder 내부 Y scroll panel: 모든 viewport `false`
  - mobile/tablet scenario list 접힘 action은 좌우 rail 화살표가 아니라 상단 bar의 위/아래 방향 glyph 사용
  - 접힘/펼침 glyph는 문자 기준선이 아니라 CSS chevron으로 중앙 정렬
  - 1366/FHD/QHD Scenario YAML editor는 workspace 높이를 채움: `yamlWorkspaceHeightDelta=0`
  - compact horizontal stepper의 첫 번째 button track 과확장 방지: mobile/tablet/1366 `stepButtonGapMax=0`
  - FHD/QHD wide builder 폭 재조정: FHD `591px`, QHD `860px`
  - desktop/FHD/QHD Scenario Builder panel은 workspace 높이를 채움: `builderHeightDelta=0`
  - Scenario list row text clipping: 모든 viewport `false`, row height mobile/tablet `64px`, desktop 이상 `70px`
  - Scenario Builder collapse rail:
    - desktop/FHD/QHD에서는 `빌더 접기` 후 builder column이 56px rail로 줄고 YAML editor가 남은 폭을 사용해야 함
    - mobile/tablet에서는 접힌 builder가 왼쪽 rail이 아니라 상단 bar로 표시되어야 함
    - 열기/닫기 chevron은 button 중앙에 정렬되고, 접힘 상태에서 불필요한 빈 builder panel이 남지 않아야 함

| Viewport | Scenario workspace | Builder | YAML editor | 판단 |
| --- | ---: | ---: | ---: | --- |
| 390x844 | `324px` wide flow | `324x1054` | `324x805` | list row `64px`, text clipping 없음, builder 내부 Y scroll 없음 |
| 768x1024 | `702px` wide flow | `702x992` | `702x805` | list row `64px`, text clipping 없음, builder 내부 Y scroll 없음 |
| 1366x768 | `811x534` workspace | `420x534` | `379x534` | builder/YAML full-height, step button 균일, list row `70px` |
| 1920x1080 | `1284x846` workspace | `591x846` | `681x846` | builder/YAML full-height, list row `70px` |
| 2560x1440 | `1924x1206` workspace | `860x1206` | `1052x1206` | builder/YAML full-height, wide builder 상한 확대 |

### 2026-04-28 Scenario Builder Collapse Manual QA

- [x] 실제 브라우저 조작 흐름으로 Scenario tab -> scenario 선택 -> 수정 -> builder 접기/열기 -> scenario list 접기 확인
  - Manual QA report: `output/web-dashboard/manual-qa-builder-collapse-report.json`
  - Screenshots: `output/web-dashboard/manual-qa-mobile-builder-collapsed.png`, `output/web-dashboard/manual-qa-desktop-1366-builder-collapsed.png`, `output/web-dashboard/manual-qa-fhd-builder-collapsed.png`, `output/web-dashboard/manual-qa-qhd-builder-collapsed.png`
  - console/page errors: `0`
  - desktop/FHD/QHD builder collapse: builder rail `56px`, YAML `743px` / `1216px` / `1856px`
  - mobile builder collapse: builder top bar `324px`, YAML `324px`, horizontal overflow `false`
  - residual UX note: mobile에서는 builder collapse 자체는 정상이나, scenario list가 editor 위쪽 vertical space를 많이 차지하므로 이후 `list max-height + 빠른 접기 affordance` 추가 검토

### 2026-04-28 Authoring Expansion Planning

- [x] New Fixture, New Suite, validation/artifacts authoring 중간 회의 문서화
  - 회의록: `docs/devs/authoring-expansion-collaboration-plan.md`
  - 전문가 합의: New Scenario create-only 흐름을 Fixture/Suite에 확장
  - 전문가 합의: binary artifact는 upload-only/read-only, text-like artifact만 Web authoring 허용
- [x] New Fixture creation smoke 1차
  - Fixture tab `새 환경 준비` dialog open, Windows PowerShell template, create-only `/api/files` flow 확인
  - 생성 후 `validation/fixtures/windows/web-ui-fixture.ps1`가 editor에 선택되고 edit mode로 열림
  - Browser smoke: `corepack pnpm exec playwright test apps/web/tests/authoring-create-dialogs.spec.js --config=playwright.web-dashboard.config.cjs`
  - Screenshot: `output/web-dashboard/authoring-new-fixture-dialog.png`
  - 남음: mobile/FHD/QHD visual matrix, diff modal save, generated fixture reference flow
- [x] New Suite creation smoke 2차
  - Suite tab `새 실행 묶음` dialog open, scenario multi-select, maxParallel, tier, allowFailure, enabled API template, create-only `/api/files` flow 확인
  - 생성 후 `validation/suites/web-ui-smoke.example.yaml`가 editor에 선택되고 Suite Builder inspect mock이 로드됨
  - Run Launcher suite dropdown에 생성 suite가 선택되고 maxParallel starter가 반영됨
  - Browser smoke: `corepack pnpm exec playwright test apps/web/tests/authoring-create-dialogs.spec.js --config=playwright.web-dashboard.config.cjs`
  - Screenshot: `output/web-dashboard/authoring-new-suite-dialog.png`
  - 남음: mobile/FHD/QHD visual matrix, actual suite run smoke
- [x] Authoring P0 safety hardening regression
  - API unit: reserved device names, trailing dot/space segment, control char, and 1 MiB text authoring limit rejection 확인
  - Suite contract: `enabled` boolean and positive integer `maxParallel` validation 확인
  - Commands: `corepack pnpm --filter @oslab/api test`, `uv run pytest tests/test_suite.py tests/test_suite_runner.py`
- [x] Suite creation viewport matrix refresh
  - FHD/QHD/tablet/mobile matrix smoke 재실행
  - Browser smoke: `corepack pnpm exec playwright test apps/web/tests/viewport-design-matrix.spec.js --config=playwright.web-dashboard.config.cjs`
  - Screenshots/report: `output/web-dashboard/viewport-design-matrix-smoke.json`, `output/web-dashboard/viewport-matrix-fhd-scenario.png`, `output/web-dashboard/viewport-matrix-qhd-scenario.png`, `output/web-dashboard/viewport-matrix-tablet-scenario.png`, `output/web-dashboard/viewport-matrix-mobile-scenario.png`
- [x] Artifact Manager authoring smoke
  - Browser smoke: `output/web-dashboard/artifact-manager-smoke.json`
  - Screenshots: `output/web-dashboard/artifact-manager-list.png`, `output/web-dashboard/artifact-manager-create-text.png`, `output/web-dashboard/artifact-manager-edit-diff.png`, `output/web-dashboard/artifact-manager-run-result.png`, `output/web-dashboard/artifact-manager-qhd.png`, `output/web-dashboard/artifact-manager-tablet.png`, `output/web-dashboard/artifact-manager-mobile.png`
  - 확인: repo/uploaded artifact list, text artifact creation/edit/diff save, Run Launcher path 반영, QHD/tablet/mobile modal layout

### 2026-04-29 Visible Browser Authoring QA

- [x] User-visible Chrome window QA
  - Browser Use MCP was unavailable in this environment because the bundled node repl requires Node `>=22.22.0` while local Node is `22.18.0`; QA fell back to a visible Chrome window launched with `--remote-debugging-port=9223`.
  - Evidence screenshots: `output/web-dashboard/visible-cdp-open.png`, `output/web-dashboard/visible-cdp-login-after-click.png`
- [x] Create dialog state reset regression
  - Finding: Scenario/Fixture/Suite create dialogs could reset draft values while open when parent catalog refreshes or parent callbacks re-rendered.
  - Fix: create dialog draft initialization now happens only when the modal opens, and stable `data-testid` hooks were added for create fields/buttons.
  - Regression: `corepack pnpm --filter @oslab/web exec playwright test apps/web/tests/authoring-create-dialogs.spec.js`
- [x] Visible create flow
  - Created scenario: `scenarios/windows/qa-visible-windows-202604290812.example.yaml`
  - Created fixture: `validation/fixtures/windows/qa-visible-fixture-202604290812.ps1`
  - Created suite: `validation/suites/qa-visible-suite-202604290812.example.yaml`
  - Screenshots/report: `output/web-dashboard/visible-qa-create-flow.json`, `output/web-dashboard/visible-qa-scenario-dialog-filled.png`, `output/web-dashboard/visible-qa-scenario-created.png`, `output/web-dashboard/visible-qa-fixture-dialog-filled.png`, `output/web-dashboard/visible-qa-fixture-created.png`, `output/web-dashboard/visible-qa-suite-dialog-filled.png`, `output/web-dashboard/visible-qa-suite-created.png`
- [x] Suite hidden default selection regression
  - Finding: New Suite preselected the first scenario, so searching/selecting one scenario could silently include a hidden default run such as `scenarios/linux/generic-smoke.example.yaml`.
  - Fix: New Suite now starts with zero selected scenarios and requires explicit selection.
  - Visible proof: `output/web-dashboard/visible-qa-suite-no-default.json`, `output/web-dashboard/visible-qa-suite-no-default-dialog.png`, `output/web-dashboard/visible-qa-suite-no-default-created.png`
  - Result: `checkedBefore=0`, generated suite did not include `scenarios/linux/generic-smoke.example.yaml`.

### 2026-04-29 Run Launcher Single Scroll QA

- [x] Run tab nested scroll regression
  - Finding: Run Launcher used fixed-height `runGrid` plus `overflow:auto` on child panels, so the page scroll and the launch panel scroll could fight each other in a narrow desktop window.
  - Fix: `.workspace-run` now owns the page scroll, while `.runGrid` and its panels use visible overflow. At `1500px` and below, Run Launcher and Live Console stack into a single column instead of squeezing side by side.
  - Verification: `corepack pnpm --filter @oslab/web lint`
  - Visible browser evidence: `output/web-dashboard/run-scroll-single-flow-smoke.json`, `output/web-dashboard/run-scroll-single-flow-1400-top.png`, `output/web-dashboard/run-scroll-single-flow-1400-bottom.png`
  - Result: workspace scrolls once, run panel `scrollTop=0`, console is below the launcher in the same page flow.
- [x] Live Console nested scroll regression
  - Finding: On FHD/wide run layout, the Live Console column stretched to match the tall Run Launcher column and its `pre` created another internal scrollbar.
  - Fix: `.workspace-run .runGrid` aligns rows to start, panels opt out of grid stretch, and `.workspace-run .console pre` uses visible overflow with no max-height.
  - Visible browser evidence: `output/web-dashboard/run-console-single-flow-smoke.json`, `output/web-dashboard/run-console-single-flow-fhd.png`
  - Result: console panel/pre `overflow=visible`, `scrollTop=0`, `maxHeight=none`; only the workspace scrolls.

### 2026-04-29 Artifact Studio + Script Assist

- [x] Artifact Studio 구현 범위 추가
  - 좌측 nav `아티팩트` 화면 추가
  - Run Launcher `테스트 파일 관리` modal은 같은 Artifact Studio surface를 사용
  - 단일 파일, 폴더형 프로젝트, product-specific starter 생성 API 추가
  - Monaco editor lazy-load와 확장자별 language mode 적용
  - Script Assist 탭: 도움, 검사, 출력 계약, AI 도움 placeholder
  - Static assist check: JSON parse, placeholder 오타, output contract 힌트, 위험 경로/파괴적 명령 warning
  - Verification commands: `corepack pnpm --filter @oslab/api build`, `corepack pnpm --filter @oslab/api test`, `corepack pnpm --filter @oslab/api lint`, `corepack pnpm --filter @oslab/web lint`, `corepack pnpm --filter @oslab/web build`
  - Browser smoke: `output/web-dashboard/artifact-studio-smoke.json`
  - Screenshots: `output/web-dashboard/artifact-studio-list.png`, `output/web-dashboard/artifact-studio-monaco-editor.png`, `output/web-dashboard/artifact-studio-assist-panel.png`, `output/web-dashboard/artifact-studio-product-specific-template.png`, `output/web-dashboard/artifact-studio-diff-save.png`, `output/web-dashboard/artifact-studio-fhd.png`, `output/web-dashboard/artifact-studio-qhd.png`, `output/web-dashboard/artifact-studio-tablet.png`, `output/web-dashboard/artifact-studio-mobile.png`
  - Result: Artifact Studio visible, Monaco loaded, Assist warnings visible, diff save persisted, script project and product-specific starter created, assist API JSON parse issue detected, FHD/QHD/tablet/mobile horizontal overflow `false`.

### 2026-04-30 Artifact Studio viewport-height layout

- [x] Artifact Studio desktop layout가 viewport 높이 안에 들어오도록 재정렬
  - `.workspace-artifacts`는 desktop에서 `100vh` 작업 영역을 유지하고 Artifact Studio page가 flex 남은 높이를 채움
  - `.artifactStudioBody`는 page를 3000px 이상 밀어내지 않고 남은 높이를 채움
  - 좌측 목록, editor 상세, Script Assist는 각 영역 내부 scroll을 사용
  - Monaco editor는 고정 `520px` 대신 부모 높이 `100%`를 사용
- [x] Mobile/tablet layout은 문서 흐름 유지
  - 목록은 제한 높이 내부 scroll
  - Monaco editor는 360px 작업 높이
  - Assist는 editor 아래 세로 배치
- [x] Browser vision QA 통과
  - FHD `1920x1080`: document height가 viewport와 일치하고 좌측 list만 내부 scroll 사용
  - QHD `2560x1440`: workspace/studio/body가 viewport 안에서 확장되고 Monaco/Assist가 남은 높이에 맞춰 늘어남
  - Mobile `390x844`: 문서 scroll 유지, artifact list는 `334px` 제한 높이 내부 scroll, Monaco는 `360px`
  - horizontal overflow: FHD/QHD/mobile 모두 `false`
  - 확인 산출물:
  - `output/web-dashboard/artifact-studio-viewport-layout-smoke.json`
  - `output/web-dashboard/artifact-studio-viewport-fhd.png`
  - `output/web-dashboard/artifact-studio-viewport-qhd.png`
  - `output/web-dashboard/artifact-studio-viewport-mobile.png`

### 2026-04-30 Artifact Studio binary/folder archive/delete

- [x] Browser vision QA 통과
  - FHD `1920x1080`: repo directory artifact 상세에서 file count, total bytes, folder tree, archive-first 안내 확인
  - FHD `1920x1080`: repo directory `보관` dry-run modal 확인 후 `.artifact-archive/**`로 이동
  - FHD `1920x1080`: archived artifact `삭제` dry-run modal 확인 후 hard delete
  - QHD `2560x1440`: uploaded binary artifact 상세에서 editor 없이 실행 전용 안내, size/hash/modifiedAt 확인
  - Tablet/mobile: Artifact Studio가 세로 흐름에서 겹침 없이 표시되고 horizontal overflow `false`
  - Run Launcher 연결: Artifact Studio에서 `validation/artifacts/powershell-system` directory를 `실행에서 사용`으로 적용하면 실행 탭 artifact path와 readiness가 갱신됨
  - archive leaf 삭제 후 빈 `.artifact-archive/<timestamp>/repo/...` 부모 폴더가 목록에 남지 않도록 API cleanup 보강
- [x] 확인 산출물:
  - `output/web-dashboard/artifact-studio-binary-folder-smoke.json`
  - `output/web-dashboard/artifact-studio-run-apply-smoke.json`
  - `output/web-dashboard/artifact-studio-folder-tree-fhd.png`
  - `output/web-dashboard/artifact-studio-archive-modal-fhd.png`
  - `output/web-dashboard/artifact-studio-delete-modal-fhd.png`
  - `output/web-dashboard/artifact-studio-binary-readonly-fhd.png`
  - `output/web-dashboard/artifact-studio-binary-readonly-qhd.png`
  - `output/web-dashboard/artifact-studio-tablet-layout.png`
  - `output/web-dashboard/artifact-studio-mobile-layout.png`
  - `output/web-dashboard/artifact-studio-directory-run-launcher-applied.png`

## 다음 작업 시 사용 방법

1. 이 문서의 공통 Smoke를 위에서 아래로 다시 확인
2. 수정한 페이지의 스크린샷을 `output/web-dashboard/`에 저장
3. 실제 demo run 한 개 이상 실행
4. 새로 찾은 버그/수정사항을 `회귀 이력`에 추가
5. 장기 TODO는 [web-dashboard-usability-todo.md](web-dashboard-usability-todo.md)에 반영
