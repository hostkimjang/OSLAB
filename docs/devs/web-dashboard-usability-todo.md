# Web Dashboard Usability TODO

이 문서는 `oslab` Web Dashboard v1을 실제 lab 운영 도구로 다듬기 위한 개발 TODO입니다.

검토 관점:

- UI/UX: 운영자가 실행 전 lab 상태를 보고 판단할 수 있는가
- Frontend: Next.js UI state, API error, SSE stream, component structure가 유지보수 가능한가
- QA/사용성 테스트: 브라우저에서 실제 demo/suite run을 반복 검증할 수 있는가
- Lab 운영: Proxmox 연결, VMID range, running/stale VM, cleanup 상태가 보이는가

## 2026-04-26 전문가 협업 라운드 반영

- [x] Run Launcher 단계형 readiness strip 추가
  - 대상 선택, Artifact, Lab, Option, Command 상태를 실행 전 요약
  - suite 실행은 artifact 필요 상태를 명확히 표시
  - scenario skeleton run은 artifact를 선택 사항으로 표시
- [x] 저장 전 diff preview 추가
  - Scenario/Fixture/Suite editor에서 변경/추가/삭제 line count 표시
  - editor 위에는 compact summary만 남기고, `저장` 클릭 또는 `큰 화면으로 보기`에서 90% viewport diff modal 표시
  - diff modal 안에서 최종 저장, X icon close, `Esc`, backdrop close 지원
  - Browser smoke: `output/web-dashboard/authoring-diff-modal-smoke.json`
  - Screenshots: `output/web-dashboard/authoring-diff-modal-desktop.png`, `output/web-dashboard/authoring-diff-modal-mobile.png`
- [x] 저장 전 YAML/PowerShell syntax check
  - API: `POST /api/validate/content`
  - YAML scenario/suite content는 저장 전 parse error와 line/column 표시
  - PowerShell `.ps1` fixture content는 PowerShell parser error와 line/column 표시
  - 문법 오류가 있으면 `저장` button disabled, 저장 직전에도 한 번 더 검사
  - invalid YAML 입력 시 visual builder inspect API가 `500`을 내지 않도록 `400`으로 정규화
  - API smoke: `output/web-dashboard/syntax-validation-api-smoke.json`
  - Browser smoke: `output/web-dashboard/syntax-validation-ui-smoke.json`
  - Screenshots: `output/web-dashboard/syntax-validation-yaml-valid.png`, `output/web-dashboard/syntax-validation-yaml-invalid.png`, `output/web-dashboard/syntax-validation-powershell-invalid.png`, `output/web-dashboard/syntax-validation-yaml-invalid-mobile.png`
- [x] Authoring list collapse/expand
  - Scenario/Fixture/Suite 파일 목록을 52px rail로 접어 editor 본문 폭 확장
  - rail에는 icon-only 펼치기 button과 현재 파일 수 표시
  - Browser smoke: `output/web-dashboard/catalog-list-collapse-smoke.json`
  - Screenshots: `output/web-dashboard/catalog-list-scenario-expanded.png`, `output/web-dashboard/catalog-list-scenario-collapsed.png`, `output/web-dashboard/catalog-list-suite-collapsed.png`, `output/web-dashboard/catalog-list-fixture-collapsed-mobile.png`
- [x] 구조/기능/디자인/사용성 개선 회의록 문서화
  - 문서: `docs/devs/oslab-expert-collaboration-plan.md`
- [x] Dashboard Lab Status Proxmox 요청에 CLI provider와 동일한 `User-Agent` 적용
- [x] `ProxmoxLabClient` 분리
  - URL normalization, HTTP request header, timeout, stop polling을 `LabService` 밖으로 이동
- [x] 1366x768, 390x844 viewport를 필수 browser smoke에 포함
  - 전체 감사 리포트: `output/web-dashboard/full-browser-audit.json`
  - 모바일 개선 재검증: `output/web-dashboard/full-browser-audit-mobile-fix.json`
- [x] Full HD/QHD viewport를 Web Dashboard 필수 디자인 검증 기준에 추가
  - 기본 matrix: 390x844 mobile, 768x1024 tablet, 1366x768 compact desktop, 1920x1080 Full HD, 2560x1440 QHD
  - 목적: 넓은 화면에서 builder/list/editor 비율이 과도하게 벌어지는지, 좁은 화면에서 clipping/overflow가 생기는지 같은 디자인 판단을 스크린샷으로 남김
  - 기준 문서: `AGENTS.md`, `docs/devs/browser-debug-checklist.md`
  - 자동 smoke: `corepack pnpm exec playwright test --config playwright.web-dashboard.config.cjs --reporter line`
  - 결과: `output/web-dashboard/viewport-design-matrix-smoke.json`, console/page errors `0`, 모든 viewport horizontal overflow `false`
- [x] Scenario Builder vertical polish
  - 단계 버튼은 active 여부와 관계없이 동일 폭/높이로 표시하고, active는 색/outline으로만 구분
  - compact horizontal stepper에서 첫 번째 버튼 track이 남은 폭을 차지하지 않도록 `grid-template-columns: none` 적용
  - builder detail/list 내부 Y scroll은 제거하고 panel/page 흐름으로 펼침
  - `빌더 접기`는 내부 내용만 접는 것이 아니라 builder column 자체를 56px rail로 줄여 YAML editor 폭을 즉시 확장
  - mobile/tablet에서는 접힌 builder를 왼쪽 rail이 아니라 상단 bar로 표시하고, 펼치기 glyph를 아래 방향 chevron으로 중앙 정렬
  - mobile/tablet scenario list 접힘 상태는 왼쪽 rail이 아니라 상단 bar로 유지하고, 열기/닫기 glyph를 위/아래 방향으로 표시
  - 접힘/펼침 glyph는 폰트 문자가 아니라 CSS chevron으로 중앙 정렬
  - 넓은 화면에서는 YAML editor가 workspace 높이를 꽉 채우도록 조정하고 matrix에 `yamlWorkspaceHeightDelta` 기록
  - FHD/QHD wide builder 폭을 `591px`/`860px`로 확대해 builder가 답답해 보이는 문제 완화
  - desktop 이상에서는 builder panel도 workspace 높이를 채워 아래가 빈 panel처럼 보이지 않게 함
  - scenario list row를 mobile/tablet `64px`, desktop 이상 `70px`로 조정해 title/path clipping 제거
  - builder checkbox/section/header typography를 12-13px 범위로 맞춰 단계별 글자 크기 튐을 줄임
  - viewport matrix smoke에서 step button width/height delta `0`, compact stepper gap `0`, builder internal Y scroll `false`, list text clipping `false`, desktop builder height delta `0` 확인
- [x] Authoring expansion 중간 회의 문서화
  - 문서: `docs/devs/authoring-expansion-collaboration-plan.md`
  - 대상: `New Fixture`, `New Suite`, `validation/artifacts` Web authoring/manager
  - 합의: `New Scenario`의 create-only, no-overwrite, catalog refresh, edit mode, validation, diff modal, browser evidence 흐름을 Fixture/Suite에도 확장
  - 합의: artifact는 upload/manage와 text-like authoring을 분리하고 `.exe/.msi/.zip` 같은 binary는 upload-only/read-only로 유지
- [x] Web authoring policy 공통화 + P0 hardening
  - Scenario/Suite는 `.yaml/.yml`, Fixture는 `.ps1/.sh`만 생성/수정 허용
  - read뿐 아니라 create/write에서도 `.env`, `*.local.*`, `oslab.local.env`, `product-specific.local*`, absolute path, `..`를 차단
  - Windows reserved device name, trailing dot/space segment, control char, 텍스트 authoring 1 MiB 초과를 차단
  - binary upload limit와 text authoring limit는 분리 유지
  - `artifactText` authoring kind 추가: `validation/artifacts/**/*.{ps1,sh,py,c,json,txt,cmd,bat}`만 Web 생성/수정 허용
- [x] `New Fixture` 생성 UX 1차
  - Fixture catalog header에 `새 환경 준비` 추가
  - Windows PowerShell, Linux shell template 제공
  - 생성 후 catalog refresh, 선택 파일 유지, edit mode 진입
  - Browser smoke: `output/web-dashboard/authoring-new-fixture-dialog.png`
  - 남음: product-specific profile starter template, shell syntax validation, generated fixture reference flow
- [x] `New Suite` 생성 UX 1차
  - Suite catalog header에 `새 실행 묶음` 추가
  - id/name/path, scenario multi-select, smoke/matrix starter, tier, allowFailure, enabled, maxParallel 제공
  - 생성 후 Suite Builder 로드, Run Launcher suite dropdown 즉시 반영, maxParallel 실행 폼 반영
  - Browser smoke: `output/web-dashboard/authoring-new-suite-dialog.png`
  - 남음: actual generated suite run smoke
- [x] Suite 저장 전 contract validation 강화
  - 빈 runs, 중복 run id, 잘못된 scenario path, 잘못된 `allowFailure/enabled/tier` shape를 저장 전 차단
  - `enabled` 필드는 suite schema/runner skip 계약과 연결됨
- [x] Artifact Manager / Web authorable artifacts MVP
  - `validation/artifacts/**`와 `.web-artifacts/**`를 browse하고 repo/uploaded provenance, size, modified time, hash를 표시
  - text-like artifact template 생성: PowerShell, shell, Python, C, JSON expected output, cmd/bat
  - binary artifact는 upload-only/read-only로 유지
  - API: `GET /api/artifacts/manage`, `GET /api/artifacts/content`, `POST /api/artifacts/template`, `PUT /api/artifacts/content`
  - UI: Run Launcher Artifact 단계의 `테스트 파일 관리`에서 repo/uploaded 통합 목록, source/type filter, text preview/edit, diff modal save, Run Launcher path 적용
  - Safety: `.web-artifacts/**`는 선택/read-only만 허용하고, Web 편집은 `validation/artifacts/**` text-like allowlist로 제한
  - Browser smoke: `output/web-dashboard/artifact-manager-smoke.json`
  - Screenshots: `output/web-dashboard/artifact-manager-list.png`, `output/web-dashboard/artifact-manager-create-text.png`, `output/web-dashboard/artifact-manager-edit-diff.png`, `output/web-dashboard/artifact-manager-run-result.png`, `output/web-dashboard/artifact-manager-qhd.png`, `output/web-dashboard/artifact-manager-tablet.png`, `output/web-dashboard/artifact-manager-mobile.png`
- [x] Artifact Studio + Script Assist 1차
  - 좌측 nav에 `아티팩트` 독립 화면 추가, Run Launcher `테스트 파일 관리` modal과 같은 Studio surface를 공유
  - 생성 모드: 단일 파일, 폴더형 프로젝트, product-specific starter
  - API: `POST /api/artifacts/project-template`, `POST /api/artifacts/assist/check`
  - Shared type: `ArtifactProjectTemplateKind`, `ArtifactAssistIssue`, `ArtifactAssistSnippet`, `ArtifactAssistCheckResult`
  - Monaco editor lazy-load, language mode 자동 선택, OSLAB placeholder/output contract/product-specific snippet 제공
  - Script Assist 검사: JSON parse, placeholder 오타, output JSON 힌트, 위험 경로 힌트, `Remove-Item -Recurse`/`rm -rf`/`del /s` warning
  - AI 도움 탭은 실제 호출 없이 extension point만 표시
  - Safety: 생성/편집 root는 `validation/artifacts/**`만 허용, `.web-artifacts/**`는 선택/read-only 유지
- [x] Artifact Studio viewport-height workspace 개선
  - Desktop/FHD/QHD에서는 `아티팩트` 화면이 viewport 높이를 채우고, Studio body가 남은 높이를 모두 사용
  - 좌측 artifact 목록, 상세 editor, Script Assist는 page를 밀어내지 않고 각 영역 내부 scroll 사용
  - Monaco editor는 고정 `520px` 대신 부모 높이 `100%`로 확장
  - Mobile/tablet에서는 문서 흐름을 유지하되 목록은 제한 높이 내부 scroll, editor는 360px 기준으로 표시
  - Browser smoke 완료: `output/web-dashboard/artifact-studio-viewport-layout-smoke.json`
  - Screenshots: `output/web-dashboard/artifact-studio-viewport-fhd.png`, `output/web-dashboard/artifact-studio-viewport-qhd.png`, `output/web-dashboard/artifact-studio-viewport-mobile.png`
- [x] Artifact Studio 생성 artifact end-to-end run 검증
  - Web UI에서 `validation/artifacts/web-ui-demo-20260430123434/run-system-demo.ps1` 생성 후 Monaco 자동완성 popup 표시 확인
  - PowerShell snippet은 Monaco snippet variable이 아니라 plain text completion으로 삽입해 `$OutputPath`, `$result` 렌더링 충돌을 방지
  - nested text artifact에서 `상위 폴더를 실행에서 사용` action으로 Run Launcher path를 `validation/artifacts/web-ui-demo-20260430123434`로 적용
  - 실제 Web run: job `cmokxp8su0003smrog10l9yo1`, run `20260430-123836-demo-powershell-system-windows`, `passed`
  - 확인: preflight `6/0`, assertions `2/0`, artifact upload `1 files / 438 B`, cleanup destroyed VM `9103`, browser console errors `0`
  - Screenshots: `output/web-dashboard/artifact-studio-demo-created.png`, `output/web-dashboard/artifact-studio-autocomplete-trigger.png`, `output/web-dashboard/artifact-studio-assist-check.png`, `output/web-dashboard/artifact-studio-run-launcher-linked.png`, `output/web-dashboard/artifact-studio-demo-run-complete.png`, `output/web-dashboard/artifact-studio-demo-result-detail.png`
- [x] Artifact Studio binary/folder 실행 전용 관리 + archive/delete
  - API: `GET /api/artifacts/tree`, `POST /api/artifacts/archive`, `POST /api/artifacts/delete`
  - Shared type: folder tree, archive/delete preview, confirm response 추가
  - binary/directory/uploaded/archive artifact는 editor 없이 read-only/run-only 상세로 표시
  - directory artifact는 file count/total bytes와 제한된 tree preview를 표시하고 symlink traversal을 하지 않음
  - `validation/artifacts/**` repo artifact는 direct hard delete 차단, `.artifact-archive/**`로 archive-first
  - `.web-artifacts/**`와 `.artifact-archive/**`는 dry-run/confirmToken modal 후 delete 가능
  - API unit test: tree 조회, repo archive, repo direct delete 차단, uploaded delete, archived delete, binary content read/write 거부, invalid path 차단
  - Browser QA: FHD/QHD/tablet/mobile headed Chromium 검증, binary read-only detail, folder tree, repo archive modal, archive delete modal, uploaded binary delete modal 확인
  - Run Launcher 연결 QA: Artifact Studio에서 `validation/artifacts/powershell-system` directory를 `실행에서 사용`으로 적용해 실행 탭 ready 상태와 artifact path 반영 확인
  - Regression fix: archived leaf 삭제 후 빈 `.artifact-archive/<timestamp>/repo/...` 부모 폴더가 Artifact Studio 목록에 남지 않도록 API cleanup 추가
  - Evidence: `output/web-dashboard/artifact-studio-binary-folder-smoke.json`, `artifact-studio-run-apply-smoke.json`, `artifact-studio-folder-tree-fhd.png`, `artifact-studio-archive-modal-fhd.png`, `artifact-studio-delete-modal-fhd.png`, `artifact-studio-binary-readonly-fhd.png`, `artifact-studio-binary-readonly-qhd.png`, `artifact-studio-tablet-layout.png`, `artifact-studio-mobile-layout.png`, `artifact-studio-directory-run-launcher-applied.png`
- [x] Artifact Studio 생성 흐름 + Script Assist 언어팩 2차
  - `새 아티팩트 제작` action을 Artifact 검색/필터 상단으로 올리고, 진입 시 선택 row를 해제해 browse/create/edit 상태를 분리
  - 생성 모드는 “새로운 artifact를 제작하시겠습니까?” 가이드 화면으로 전환하며 단일 파일, 폴더형 프로젝트, product-specific starter를 compact 작업 패널에서 선택
  - 생성 완료 후 새 artifact path를 자동 선택하고 Run Launcher/Scenario Builder 적용 action이 바로 보이도록 갱신
  - Monaco model은 artifact path 기준으로 유지하고 snippet 삽입은 `executeEdits`로 처리해 Assist 갱신 중 cursor/focus 튐을 줄임
  - API: `GET /api/artifacts/language-tools`, `POST /api/artifacts/language-tools/install`, `POST /api/artifacts/assist/check` language/toolStatus/firstRunTips 확장
  - 언어 도구 상태: PowerShell, shell, Python, JSON, CMD/BAT, C, txt를 지원하고, 설치/활성화는 자동 다운로드 없이 안내형 응답으로 유지
  - Runtime guard: Lab Status partial/mock response에서도 `checks.*` 누락으로 client crash가 나지 않도록 optional check 처리
  - Browser regression: `corepack pnpm exec playwright test apps/web/tests/artifact-studio-create-assist.spec.js --config=playwright.web-dashboard.config.cjs`
  - Screenshots: `output/web-dashboard/artifact-studio-create-flow.png`, `output/web-dashboard/artifact-studio-assist-language-tools.png`
- [x] Artifact Studio 전체 언어 LSP Assist 표면
  - API: `POST /api/artifacts/assist/complete`, `POST /api/artifacts/assist/diagnostics`, `GET /api/artifacts/language-tools`
  - Python/shell/JSON은 repo-bundled public LSP(`pyright-langserver`, `bash-language-server`, `vscode-json-language-server`)에 먼저 completion을 요청하고 backend completion endpoint로 후보를 반환
  - PowerShell/C는 project-local LSP tool cache 준비 상태와 internal fallback completion을 함께 표시
  - BAT/CMD/txt는 OSLAB internal LSP-compatible provider로 completion/diagnostics 표면을 통일
  - Internal fallback/lint dataset 확장: Python `print/range/json/pathlib/subprocess`, shell `grep/find/cat`, PowerShell common cmdlet, JSON output contract, C stdio, BAT control-flow completion과 언어별 위험 패턴 warning 제공
  - Monaco `fixedOverflowWidgets`로 suggest/hover/warning popup clipping 방지
  - Monaco editor는 controlled `value` 덮어쓰기를 피하고 path 기반 model/defaultValue로 유지해 빠른 입력 중 문자 누락 가능성을 낮춤
  - Script Assist `도움`/`자동완성` 탭에서 처음 만들기, 언어별 추천 항목, trigger, 설명, 예시 코드, 삽입 버튼을 한국어로 설명
  - Browser regression: Python artifact `pri` -> `print`, `for i in ra` -> `range` completion popup 확인, 빠른 입력 후 model value 일치 확인
  - Visible FHD QA: 사용자 화면에 뜬 Chrome에서 Artifact Studio 진입, Python artifact 편집, `print/range` completion popup, 자동완성 안내 탭 확인
  - Open LSP smoke: `output/web-dashboard/artifact-studio-lsp-open-service-smoke.json` (`pyright`는 `print/range` source `lsp`, JSON LS는 `$schema` source `lsp`, shell command는 fallback dataset)
  - Screenshots: `output/web-dashboard/artifact-studio-python-lsp-print.png`, `output/web-dashboard/artifact-studio-python-lsp-range.png`, `output/web-dashboard/artifact-studio-python-typing-stability.png`, `output/web-dashboard/artifact-studio-visible-python-print.png`, `output/web-dashboard/artifact-studio-visible-python-range.png`
- [x] 접근성 계약 1차 보강
  - focus ring
  - nav landmark
  - segmented `aria-pressed`
  - compact nav title
- [ ] 접근성 계약 추가 보강: disabled reason, authoring mode semantics
- [x] Authoring editor 공간 재조정
  - Scenario/Suite visual builder를 compact scroll panel로 낮춰 textarea가 주 작업공간으로 남도록 조정
  - 1366x768 smoke 기준 builder `123px`, textarea `245px`, horizontal overflow `false`
  - Browser smoke: `output/web-dashboard/authoring-diff-modal-smoke.json`
- [x] result filter pressed state 보강
  - Results status filter button에 `aria-pressed` 적용
- [x] 모바일 nav/readiness 압축 개선
  - 390x844 nav는 horizontal tab bar로 동작
  - Run readiness는 fixed 5-column 대신 responsive track/one-column mobile layout 사용
- [x] Run Launcher 5-step flow 1차 구현
  - 대상 선택, Artifact, 랩과 설정, 옵션, 검토와 실행 section으로 실행 흐름 재배치
  - 실행 묶음/시나리오 버튼별 ready/blocked reason 표시
  - Artifact 확인 중에는 stale artifact result로 실행 버튼이 활성화되지 않도록 조건 보강
  - Browser smoke: `output/web-dashboard/run-launcher-step-flow-smoke.json`
  - Screenshots: `output/web-dashboard/run-launcher-step-flow-scenario-ready.png`, `output/web-dashboard/run-launcher-step-flow-mobile.png`
- [x] Run Launcher scenario-aware Artifact 추천 1차 구현
  - 선택한 scenario basename과 artifact catalog basename을 매칭해 추천 chip 표시
  - `demo-powershell-system` -> `validation/artifacts/powershell-system` 확인
  - product-specific 전용 scenario는 repo-local 제품 artifact가 catalog에 없으면 demo artifact를 잘못 추천하지 않도록 제외
  - 390x844 mobile에서 Run form이 내부 scroll에 잘리지 않도록 page-level scroll로 수정
  - Browser smoke: `output/web-dashboard/run-launcher-artifact-recommendation-smoke.json`
  - Screenshots: `output/web-dashboard/run-launcher-artifact-recommendation-desktop.png`, `output/web-dashboard/run-launcher-artifact-recommendation-mobile.png`
- [x] Run Launcher Artifact upload 1차 구현
  - API: `POST /api/artifacts/upload`, `GET /api/artifacts/uploads`
  - 업로드 파일은 `.web-artifacts/`에 저장하고 artifact catalog/check/run path 흐름에 포함
  - UI: Artifact 단계 안에서 파일 선택 후 `업로드 후 사용`을 누르면 path가 자동 선택되고 artifact check가 ready로 연결
  - 폴더 선택은 `POST /api/artifacts/upload-directory`로 `.web-artifacts/<timestamp>-<folder>/`에 복사한 뒤 생성된 directory path를 자동 선택
  - 큰 폴더 upload는 Next rewrite proxy를 거치지 않고 API server `:3001`로 직접 전송해 대용량 multipart `Internal Server Error`를 피함
  - 브라우저 보안상 원본 `C:\...\Release` 절대 경로는 picker에서 받을 수 없으므로, 기존 서버 로컬 폴더를 그대로 쓰려면 `직접 입력 - 파일/폴더 경로`를 계속 사용
  - 좁은 Run panel에서도 업로드/추천 박스 header와 버튼이 세로로 찌그러지지 않도록 responsive grid로 정리
  - 업로드 상태 카드는 선택됨/업로드 중/사용 중/실패, 파일 수, 바이트 진행률, 저장된 `.web-artifacts/...` 경로를 표시
  - Browser/API smoke: `output/web-dashboard/artifact-upload-api-smoke.json`, `output/web-dashboard/run-launcher-artifact-upload-smoke.json`
  - Folder/responsive smoke: `output/web-dashboard/artifact-folder-upload-responsive-smoke.json`
  - Large Release folder smoke: `output/web-dashboard/artifact-release-folder-direct-upload.json`
  - Screenshots: `output/web-dashboard/run-launcher-artifact-upload-desktop.png`, `output/web-dashboard/run-launcher-artifact-upload-mobile.png`, `output/web-dashboard/artifact-folder-upload-controls-responsive.png`, `output/web-dashboard/artifact-folder-upload-responsive.png`
  - Large Release screenshot: `output/web-dashboard/artifact-release-folder-direct-upload.png`
- [x] Run Launcher 디렉터리 artifact 직접 경로 확인
  - API `GET /api/artifacts/check`는 절대 경로 디렉터리를 `kind=directory`로 반환
  - Browser smoke에서 `C:\Users\kysky\Documents\gitlab\agent-windows\ProductAgent\bin\Release` 입력 후 `테스트 파일 확인됨 · directory`와 시나리오 실행 준비 상태 확인
  - Browser smoke: `output/web-dashboard/artifact-directory-path-smoke.json`
  - Screenshot: `output/web-dashboard/artifact-directory-path-direct-input.png`
- [x] Run Launcher 좁은 화면 레이아웃 보강
  - 1280px 이하에서는 실행 설정 panel과 Live Console을 단일 컬럼으로 전환해 콘솔이 오른쪽으로 잘리지 않게 함
  - 좁은 viewport에서는 실행 설정 panel 내부 y-scroll 대신 page-level scroll을 사용
  - Lab Status card는 고정 4열이 아니라 auto-fit grid로 줄바꿈되어 Provider/Node/Template/VMID card가 viewport 밖으로 밀리지 않음
  - viewport matrix에 `1024x768 narrow-desktop`을 추가해 Run 화면의 horizontal overflow, 내부 scroll, Lab Status overflow를 회귀 검사
- [x] Running -> terminal 결과 동기화 보강
  - runtime polling이 오래된 `selectedRunId` closure를 보지 않고 현재 선택 run ref를 기준으로 상세를 갱신하도록 수정
  - SSE `done` 이벤트 수신 시 job을 재조회하고 연결된 run을 즉시 선택/상세 갱신
  - 선택된 run이 active 상태이면 2초 간격으로 상세/progress를 갱신해 Results 우측 요약과 timeline이 실행 중에도 따라오게 함
  - running/queued/pending 상태에서는 아직 생성 중인 필수 evidence를 `계약 누락`으로 확정 표시하지 않고 `확인 중`으로 표시해 실패처럼 보이는 조기 판정을 방지
  - Browser smoke: `output/web-dashboard/running-status-sync-smoke.json`
  - Screenshots: `output/web-dashboard/running-status-sync-started.png`, `output/web-dashboard/running-status-sync-results-open.png`, `output/web-dashboard/running-status-sync-results-terminal.png`, `output/web-dashboard/running-evidence-checking.png`
- [x] 카드/섹션 설명 tooltip 1차 구현
  - 디자이너/웹디자이너/프론트/QA/사용 개발자 관점 합의: 모든 row가 아니라 판단이 필요한 card/section header에만 원형 `i` tooltip 배치
  - 공통 `InfoTooltip` component로 hover, focus, click/tap, `Esc`, outside click을 지원
  - portal/fixed positioning과 viewport clamp로 결과 상세, 내부 scroll panel, 390x844 mobile에서 잘림/가로 overflow를 방지
  - 적용 위치: Lab Status, dashboard metric/list, Run readiness/step headers, authoring syntax/diff, Results 시간/파일/증거/timeline/file group
  - 후속 copy 조정: 개발자 내부 용어 설명보다 사용자 기능 설명을 우선하도록 변경. Artifact는 `VM 안에서 테스트할 프로그램, 설치 파일, 스크립트, ZIP 묶음`으로 설명
  - Information 확장: 환경 준비 dashboard metric, Scenario/Fixture/Suite catalog header, Scenario/Suite builder header, Suite policy, Results evidence group header, `run.json`/`progress.jsonl` 등 evidence row에 사용자 친화 설명 추가
  - QA 접근성 반영: evidence row 자체가 preview button이라 tooltip button을 row 내부에 중첩하지 않고 sibling control로 배치
  - Browser smoke: `output/web-dashboard/info-tooltip-smoke.json`
  - Screenshots: `output/web-dashboard/info-tooltip-dashboard-lab.png`, `output/web-dashboard/info-tooltip-dashboard-fixtures.png`, `output/web-dashboard/info-tooltip-scenario-catalog.png`, `output/web-dashboard/info-tooltip-fixture-catalog.png`, `output/web-dashboard/info-tooltip-suite-catalog.png`, `output/web-dashboard/info-tooltip-run-readiness.png`, `output/web-dashboard/info-tooltip-artifact-friendly.png`, `output/web-dashboard/info-tooltip-results-evidence.png`, `output/web-dashboard/info-tooltip-evidence-run-json.png`, `output/web-dashboard/info-tooltip-evidence-progress-jsonl.png`, `output/web-dashboard/info-tooltip-mobile-run.png`
- [ ] Matrix Run Planner 기획/구현
  - OS template axis x OS state/profile axis를 Web UI에서 직접 선택/검증
  - VMID capacity, maxParallel, allowFailure, expected evidence를 실행 전 표시
- [x] Cleanup dry-run/confirmation
  - API: `POST /api/lab/cleanup-stale`
  - 기본 대상은 configured VMID range 안의 stopped/stale `oslab-*` VM만 포함
  - Web UI는 먼저 dry-run으로 VMID/name/node/status 후보를 확인하고 `confirmToken`이 일치할 때만 삭제 요청
  - running VM 삭제는 기본 UI 흐름에서 제외하고 별도 `includeRunning` 계약으로만 확장 가능
  - Browser smoke: `output/web-dashboard/cleanup-dry-run-smoke.json`
  - Screenshot: `output/web-dashboard/cleanup-dry-run-run-tab.png`
  - 남음: age/owning run metadata는 run artifact 기록이 생긴 뒤 연결
- [x] Results evidence checklist
  - `run.json`, `progress.jsonl`, raw output, normalized output, reports, cleanup state 표시
  - `run.json`과 `progress.jsonl` 같은 핵심 증거는 파일이 무엇인지보다 언제 봐야 하는지 중심의 row-level information 제공
  - 완료된 run에서 누락된 필수 evidence는 contract gap으로 노출
  - 실행 중인 run에서 아직 쓰이지 않은 필수 evidence는 `확인 중`으로 표시하고 완료 후에만 contract gap으로 확정
  - API: `GET /api/runs/:runId/evidence`
  - UI: Results detail 상단 `증거 체크리스트` 패널
  - Browser smoke: `output/web-dashboard/results-evidence-checklist-smoke.json`
  - Screenshot: `output/web-dashboard/results-evidence-checklist.png`
  - Skeleton run에서 `result.html`/`result.junit.xml` 누락이 contract gap으로 표시되는 것을 확인
- [x] Results 실제 run 파일 discovery
  - API detail `GET /api/runs/:runId`가 `runs/<run-id>/` 하위 실제 파일을 재귀 스캔해 `files` 목록으로 반환
  - 고정 evidence 계약에 없는 파일은 `discovered=true`로 표시하고, top-level 경로 기준으로 core/timeline/outputs/reports/cleanup/other 그룹에 배치
  - 기대 evidence 경로지만 실제 생성되지 않은 파일은 `status=missing|contractGap` 상태로 `files`에 포함
  - UI 파일 목록은 hard-coded 링크 대신 API `files`를 렌더링하며, 발견 파일에 `추가 발견` 배지를 표시하고 누락 기대 파일은 dead link 없는 비활성 카드로 표시
  - Previewable 확장자: JSON/JSONL/log/XML 외 txt/csv/md/yaml/ps1/sh/cmd/bat 같은 text-like artifact
  - API smoke: `output/web-dashboard/results-run-files-api-smoke.json`
  - Missing API smoke: `output/web-dashboard/results-run-files-missing-api-smoke.json`
  - Browser smoke: `output/web-dashboard/results-run-files-ui-smoke.json`
  - Screenshots: `output/web-dashboard/results-run-files-discovered.png`, `output/web-dashboard/results-run-files-discovered-preview.png`, `output/web-dashboard/results-run-files-missing.png`
- [x] Results list filter/selection mismatch 수정
  - 상태 필터/검색으로 현재 선택 run이 리스트에서 사라지면 첫 visible run으로 선택 보정
  - 검색 결과가 0개면 상세 선택을 해제하고 빈 상태 안내 표시
  - Smoke report: `output/web-dashboard/results-list-selection-fix-smoke.json`
- [x] Results 사람이 읽는 시간 표시
  - 리스트의 `3m ago` 같은 상대 시간 옆에 절대 로컬 시간 표시
  - 상세 상단에 `결과 시간` 섹션 추가: 실행 시작, 완료, 소요 시간
  - `startedAt/completedAt` metadata가 없으면 `YYYYMMDD-HHMMSS` run ID timestamp를 fallback으로 사용
  - Browser smoke: `output/web-dashboard/results-human-time-smoke.json`
  - Screenshots: `output/web-dashboard/results-human-time-detail.png`, `output/web-dashboard/results-human-time-mobile.png`
- [x] Results 과거 running 상태 보정
  - run artifact가 `running`으로 남았지만 dashboard job이 `cancelled`/`failed`/`passed` terminal 상태이면 job 상태를 우선 표시
  - API list/detail에 `artifactStatus`, `statusMeta`, `jobId`, `jobStatus`를 포함
  - UI: 리스트/상세에 `상태 보정: running -> cancelled` 표시, `멈춤` filter 추가
  - Browser smoke: `output/web-dashboard/results-cancelled-status-detail-smoke.json`
  - Screenshot: `output/web-dashboard/results-cancelled-status-detail.png`
- [x] Results 고급 분석 필터
  - API run summary에 `scenarioId`, `scenarioPath`, `suiteId`, `failureClasses`, `requiredFailed`, `allowedFailed`, `evidenceSummary` 추가
  - UI: 종류(run/suite), 이슈(failureClass/필수 실패/허용 실패/취소/계약 누락), 증거(정상/누락 있음) filter 추가
  - row meta chip으로 scenario/suite lineage, failure class, contract gap 수 표시
  - suite 선택 시 없는 `logs/progress.jsonl` 요청을 하지 않도록 404 noise 제거
  - Browser smoke: `output/web-dashboard/results-advanced-filters-smoke.json`
  - Screenshot: `output/web-dashboard/results-advanced-filters.png`
- [x] Results list collapse/expand
  - 결과 목록 패널을 접으면 52px rail만 남기고 상세 영역을 확장
  - rail에는 icon-only 펼치기 button과 현재 결과 수 표시
  - Browser smoke: `output/web-dashboard/results-list-collapse-smoke.json`
  - Screenshots: `output/web-dashboard/results-list-expanded.png`, `output/web-dashboard/results-list-collapsed.png`, `output/web-dashboard/results-list-collapsed-mobile.png`
- [x] Results preview modal redesign
  - 기존 inline preview panel을 제거하고 클릭 기반 overlay modal로 변경
  - file chip preview와 present evidence row가 같은 modal을 사용
  - `Esc`, backdrop click, X icon close button으로 닫기
  - open 중 body scroll lock, close button focus 적용
  - desktop/mobile 모두 viewport 약 90% 크기의 responsive modal로 표시
  - 없는 run file 요청은 처리되지 않은 `500` 대신 `404` 반환
  - Smoke report: `output/web-dashboard/results-preview-modal-smoke.json`
  - Refinement smoke: `output/web-dashboard/results-preview-modal-90pct-smoke.json`
  - Screenshots: `output/web-dashboard/results-preview-modal-run-json.png`, `output/web-dashboard/results-preview-modal-progress-jsonl.png`, `output/web-dashboard/results-preview-modal-mobile.png`
  - Refinement screenshots: `output/web-dashboard/results-preview-modal-90pct-desktop.png`, `output/web-dashboard/results-preview-modal-90pct-mobile.png`
- [x] Results suite child run 파일 그룹과 drill-down
  - API `GET /api/runs/:runId`가 `runs/<suite>/scenarios/<child-run-id>/...` 형태의 nested child run도 직접 상세 조회
  - Suite detail은 상위 suite evidence와 child run artifact를 분리하고, child run id별 card/grid로 파일을 정렬
  - Child group의 `상세 보기`로 개별 scenario run 상세에 진입 가능
  - Child detail 상단에 `실행 묶음 안의 시나리오 상세` 맥락 배너, 상위 suite id, `전체 실행 묶음으로 돌아가기` CTA를 표시
  - Suite/child detail 전환 시 오른쪽 상세 scroll을 상단으로 초기화해 현재 맥락 배너가 바로 보이게 함
  - Child detail을 보고 있을 때도 왼쪽 목록에서는 부모 suite row가 선택 상태로 유지되어 사용자가 현재 실행 묶음 맥락을 잃지 않음
  - 이미 선택된 결과 row를 다시 눌러도 상세를 비우지 않아 `Loading...` 상태에 갇히지 않음
  - File chip 기본 클릭은 새 탭 대신 preview modal이며, 새 탭 열기는 modal 내부 보조 action으로 유지
  - Running/queued/pending 상세의 핵심 요약은 실패 문구가 아니라 진행 중 문구와 live job log 기반 timeline fallback을 표시
  - Browser smoke: `output/web-dashboard/results-suite-redesign-smoke.json`
  - Screenshots: `output/web-dashboard/results-suite-files-grouped.png`, `output/web-dashboard/results-suite-child-context.png`, `output/web-dashboard/results-suite-back-from-child.png`, `output/web-dashboard/results-child-preview-popup.png`
- [x] Results preview pretty format
  - `.json`은 전체 JSON을 2-space indent로 표시
  - `.jsonl`은 line-by-line JSON parse 후 각 줄을 pretty block으로 표시하고, 깨진 줄은 raw fallback
  - JSON 형태의 `.log`/`.txt`는 자동 pretty-print하고, 일반 log는 원문 줄바꿈을 유지
  - preview modal 본문은 `pre-wrap`/`overflow-wrap`으로 긴 Windows path나 token 값이 한 줄로 화면을 밀지 않도록 처리
  - Browser smoke: `output/web-dashboard/results-suite-redesign-smoke.json`, `prettyLogPreview=true`
  - Screenshot: `output/web-dashboard/results-pretty-json-log-preview.png`
- [x] Results HTML report iframe preview
  - `result.html`/`suite.html`을 previewable file로 분류
  - API는 `.html`을 `text/html`로 내려주고, Web modal은 raw text가 아니라 sandboxed iframe으로 보고서 화면을 표시
  - `새 탭에서 열기`는 기존처럼 보조 action으로 유지
  - Browser smoke: `output/web-dashboard/results-suite-redesign-smoke.json`, `htmlPreviewIframe=1`
  - Screenshot: `output/web-dashboard/results-html-iframe-preview.png`

## 2026-04-23 브라우저 점검 결과

실제 Web Dashboard에서 다음 흐름을 확인했습니다.

| 항목 | 결과 | 증거 |
| --- | --- | --- |
| Web/API dev server | 통과 | `http://127.0.0.1:3000`, `http://127.0.0.1:3001/api/me` |
| 로그인 | 통과 | `apps/api/.env` local admin 계정 |
| 한국어 UI | 통과 | `시나리오`, `환경 준비(Fixture)`, `실행 묶음(Suite)`, `실행`, `결과` |
| Scenario catalog filter | 통과 | `product-specific` 검색 |
| Run Launcher | 통과 | `demo-powershell-system` 선택, artifact path 입력 |
| 실제 dashboard-triggered demo run | 통과 | job `cmob5p1up0007smv00wkvjmit` |
| 실제 run id | 통과 | `20260423-162441-demo-powershell-system-windows` |
| VM lifecycle cleanup | 통과 | VMID `9102` clone stop/destroy 완료 |
| Result Explorer 표시 | 부분 통과 | report link 중심, drill-down 없음 |

확인된 실제 실행 command:

```text
uv run oslab run --scenario scenarios/windows/demo-powershell-system.example.yaml --config config/oslab.local.yaml --env-file config/oslab.local.env --artifact-path validation/artifacts/powershell-system --boot-timeout-seconds 300 --guest-timeout-seconds 300 --command-timeout-seconds 420 --poll-interval-seconds 5
```

확인된 UX 문제:

- Results 화면에 최신 run이 즉시 최상단에 보이지 않을 수 있습니다. `runs/` index 정렬과 job `runId` 연결을 더 명확히 해야 합니다.
- 실행 완료 후 notice가 `Live log connection was interrupted...`로 남을 수 있습니다. SSE `done`과 `error` 표시를 분리해야 합니다.
- Run Launcher는 실행 전 Proxmox/template/VMID 여유를 보여주지 않습니다.
- Result Explorer는 `result.html` 링크 중심이라 실패 원인, progress, raw/normalized output을 한 화면에서 추적하기 어렵습니다.

## 2026-04-23 추가 브라우저 점검 결과

실제 browser verification에서 이번 라운드 기능을 다시 확인했습니다.

| 항목 | 결과 | 증거 |
| --- | --- | --- |
| Scenario builder dirty-state guard | 통과 | builder 값 수정 후 tab 이동 시 confirm dialog 표시 |
| Dirty indicator | 통과 | 좌측 nav에 `수정됨` 표시 |
| Suite visual builder readonly | 통과 | `validation/suites/product-specific-windows-v1.example.yaml` |
| Recent artifacts | 통과 | `powershell-system`, `hello-c` chip 표시 |
| Global running banner + cancel | 통과 | job `cmobkm4al0007sm0wxkijzd6w`, `cancelled` |
| Dashboard cleanup action | 통과 | cleanup 후 running/stopped `oslab-*` VM `0` |
| Real VM demo run after cleanup | 통과 | `20260423-232535-demo-powershell-system-windows`, `passed` |
| Scenario/Results list header-body 분리 | 통과 | 검색 입력이 list row click을 가리지 않음 |
| Scenario/Results row clamp | 통과 | 긴 title/path가 ellipsis 처리되고 row 높이 유지 |

추가 screenshot:

- `output/web-dashboard/run-success-and-console.png`
- `output/web-dashboard/suite-builder-readonly.png`
- `output/web-dashboard/scenario-list-row-fix.png`
- `output/web-dashboard/results-list-row-fix.png`

## 2026-04-23 Authoring Safety 반영

- [x] 시나리오(Scenario), 환경 준비 스크립트(Fixture), 실행 묶음(Suite) 파일은 기본 `읽기 전용`으로 열림
- [x] `수정` 버튼을 눌러야 textarea가 편집 가능해짐
- [x] 편집 중에는 `저장`/`취소` action만 노출
- [x] 저장 후 다시 `읽기 전용`으로 돌아감
- [x] 취소하면 마지막으로 읽은 파일 내용으로 되돌림
- [x] 저장하지 않은 변경이 있는 상태에서 다른 파일을 열 때 discard confirm 표시
- [x] 로그아웃 시 login form 입력값 초기화

남은 authoring safety:

- [x] 저장하지 않은 변경이 있을 때 tab 이동, refresh, logout 전 확인
- [x] 저장 전 diff preview
- [x] 저장 전 diff preview 90% modal 전환
- [x] 현재 editor buffer 기준 syntax validation
- [x] 저장 전 YAML/PowerShell syntax check
- [ ] schema-aware validation

## P0: 운영 안정성

- [x] Lab Status API 추가
  - Proxmox API connectivity
  - configured node 존재 여부
  - template VMID/name/template flag
  - clone VMID range start/end
  - used/free/reserved VMID summary
  - running/kept/stale `oslab-*` VM 목록
  - local lock file 목록
  - `config/oslab.local.yaml`, `config/oslab.local.env` 존재 여부
  - 실제 확인: Proxmox `9.1.1`, node `softverse`, template `9101`, VMID range `9102-9199`, free `98`

- [x] Lab Status UI 추가
  - Dashboard 첫 화면 상단에 `랩 상태` 패널 배치
  - green/amber/red 상태로 API, template, VMID pool, stale VM 표시
  - stale VM이 있으면 실행 버튼 근처에도 경고 표시
  - screenshot: `output/web-dashboard/lab-status-dashboard.png`
  - screenshot: `output/web-dashboard/lab-status-run-launcher.png`

- [x] Run Launcher를 단계형 흐름으로 재구성
  - [x] 1단계: scenario/suite 선택
  - [x] 단계형 readiness strip 추가
  - [x] `없음 - 단일 시나리오 실행` suite option 추가
  - [x] `없음 - 실행 묶음만 실행` scenario option 추가
  - [x] 2단계: artifact 선택 또는 직접 파일/폴더 경로 입력
  - [x] 3단계: config/env/lab readiness 확인
  - [x] 4단계: advanced option 분리
  - [x] 5단계: CLI command preview와 최종 실행
  - [x] scenario-aware artifact recommendation 1차 구현
  - [x] artifact upload UX 1차 구현

- [x] 실행 전 safety gate
  - [x] artifact path 존재 여부 확인
  - [x] 단일 scenario run은 artifact path 없이 skeleton run 허용
  - [x] suite run은 artifact path가 있을 때만 활성화
  - [x] scenario/suite 선택 여부에 따라 실행 버튼 독립 활성화
  - [x] artifact 없는 scenario skeleton run 결과 연결: `20260423-165536-demo-powershell-system-windows`
  - [x] 브라우저 검증: scenario button enabled, suite button disabled, command preview에서 `--artifact-path` 제외
  - [x] config/env file path 존재 여부 확인
  - [x] suite `maxParallel` 대비 VMID range 여유 확인
  - [x] 실행될 CLI command preview 표시
  - [x] Lab Status가 `blocked`이면 실행 버튼 비활성화
  - [x] allowed failure scenario 요약
  - [x] `keepVm`, `fullClone`은 advanced mode에서만 노출
  - [x] advanced option warning 표시

- [x] Stale job reconciliation
  - API restart로 child process가 끊겼는데 DB job만 `running`으로 남는 경우 감지
  - 실제 process/VMID가 없으면 `failed` 또는 `cancelled` 계열 상태로 정리
  - jobs 목록 조회 시 API service 시작 이전의 `queued`/`running` job을 `failed`로 정리
  - 실제 정리 확인: `cmob66hie000asmv0b2knbjb9`
  - Results API는 artifact `run.json` 상태가 갱신되지 않은 과거 run도 dashboard job 최종 상태로 보정

- [x] Job 상태 표시 개선
  - SSE `done` payload의 `passed`/`failed`를 UI notice에 반영
  - SSE network error와 job failure를 다른 메시지로 표시
  - SSE error 시 job 상태를 재조회하고 completed job이면 최종 상태 표시
  - running job 중 EventSource가 일시적으로 끊기면 연결을 닫지 않고 자동 갱신/reconnect 대기 표시
  - selected job log fetch와 console auto-scroll
  - 수동 `로그 불러오기` action
  - direct API SSE + keepalive heartbeat
  - Python subprocess stdout unbuffered
  - long-running job에서 마지막 log 수신 시각 표시

- [x] Artifact path check
  - `GET /api/catalog/artifacts`로 `validation/artifacts` 선택 catalog 제공
  - Run Launcher에서 `Artifact 선택` dropdown 제공
  - `없음 - 시나리오 skeleton run`, `직접 입력 - 파일/폴더 경로`, catalog item 선택 지원
  - catalog item 선택 시 path input 비활성화, 직접 파일/폴더 경로 선택 시 활성화
  - server-local absolute path를 허용할지 정책 결정
  - read-only existence check와 warning 표시
  - 기본 권장 root: `validation/artifacts/**`, `.web-artifacts/**`

- [x] Layout overflow fix
  - Scenario/Fixture/Suite list는 panel 내부에서 스크롤
  - Scenario/Fixture/Suite list는 필요할 때 접어서 editor 본문 공간을 넓힐 수 있음
  - Results list와 Results detail은 각각 panel 내부에서 스크롤
  - Run Launcher 설정 panel과 Live Console이 viewport를 넘지 않음
  - 기본 `maxParallel`은 1
  - 전역 실행 상태 배너 추가
  - 결과 검색/상태 필터 toolbar 추가
  - 결과 row status badge와 상대 시간 표시

- [x] Authoring dirty-state guard 확장
  - [x] tab 이동 전 확인
  - [x] logout 전 확인
  - [x] browser refresh 전 확인
  - [x] builder draft까지 dirty-state 집계
  - [x] 저장 전 diff preview

## P1: 실패 분석과 작성 UX

- [x] Live Console timeline
  - `progress.jsonl` 기반 단계형 timeline
  - clone, boot, QGA ready, preflight, fixture, artifact upload, product execution, output collect, assertion, report, cleanup
  - run detail에서 최근 progress event를 단계형으로 표시
  - suite 병렬 run에서는 child run detail을 통해 확인

- [x] Results Explorer master-detail
  - suite summary: total/passed/failed/allowedFailed/requiredFailed
  - failed first sorting
  - failureClass, scenario id, VMID, cleanup status 표시
  - 결과 리스트/상세에 사람이 읽는 로컬 시간 표시
  - 결과 목록 접기/펼치기로 상세 본문 공간 확장
  - `suite.json`, `run.json`, `result.json`, `inventory.analysis.json`, stdout/stderr, progress log 바로 열기
  - overlay preview modal로 JSON/log 내용 표시

- [ ] Scenario Studio schema-aware form
  - [x] OS/provider/template/guest/artifact/report 핵심 필드 visual builder v1
  - [x] OS/provider/template/guest/artifact/fixtures/product steps/assertions/reports generic form 표시
  - [x] 새 시나리오 생성 dialog와 Windows/Linux/product-specific template 제공
  - [x] 새 시나리오 생성 dialog compact 비율/모바일 X close 배치 보정
  - [x] 새 시나리오 생성 시 template summary와 “파일만 생성, 실행은 나중” 안내 표시
  - [x] 새 시나리오 저장 경로의 필수/형식/중복/사용 가능 상태 inline 표시
  - [x] 기본 생성 경로가 이미 있으면 `-2` suffix로 자동 회피
  - [x] `id` 변경 시 저장 경로를 slug 기반으로 자동 동기화
  - [x] 기존 scenario editor/builder에 저장하지 않은 변경이 있을 때 생성 전 confirm guard
  - [x] 저장 전 최소 scenario contract validation 지원
  - raw YAML은 advanced mode로 유지
  - [x] 저장하지 않은 editor 내용에 대한 syntax validation 지원
  - [ ] assertion type별 전용 form
  - [ ] fixture side-effect schema-aware form
  - [ ] Suite/Fixture까지 포함한 full schema-aware validation
  - [ ] 새 시나리오 dialog focus trap/focus restore를 diff/preview modal 수준으로 맞추기
  - [ ] OS template axis x OS state/profile axis 선택 UI 추가 검토
  - [ ] `templateVmId`, `VMID range`, `output adapter`, `body JSON` 등 내부 레이블을 사용자 언어로 2차 정리
  - [ ] `Artifact 실행 명령`과 `제품 실행 단계`의 단계 번호/관계를 4A/4B 또는 단일 실행 섹션으로 재정리
  - [x] Scenario Builder V3 vertical axis prototype
    - desktop: 세로 stepper rail + 선택 step detail panel + 오른쪽 YAML editor
    - mobile: 1열 흐름으로 전환하고 horizontal overflow false 확인
    - `실행 명령` 단계는 `4A Artifact 실행 명령` + `4B 제품 실행 단계`로 분리
    - browser smoke: `output/web-dashboard/scenario-builder-v3-vertical-smoke.json`
    - screenshots: `output/web-dashboard/scenario-builder-v3-vertical-desktop.png`, `output/web-dashboard/scenario-builder-v3-vertical-mobile.png`
    - mockup: `output/web-dashboard/scenario-builder-vertical-axis-mockup.png`
  - [x] Scenario Builder V3 visual ratio fix
    - 1366x768 catalog open 상태에서 builder width `420px`, YAML `379px`; list collapse 후 YAML `546px`
    - FHD/QHD wide layout에서 builder rail/detail 상한 적용: FHD builder `591px`, QHD builder `860px`
    - builder collapse 상태는 desktop/FHD/QHD에서 56px rail로 접혀 YAML editor가 남은 폭을 사용
    - mobile/tablet builder collapse는 상단 bar로 표시되어 작은 화면에서 왼쪽 빈 rail을 만들지 않음
    - 1366/FHD/QHD에서 YAML editor가 workspace 높이를 채움: `yamlWorkspaceHeightDelta=0`
    - 1366/FHD/QHD에서 builder panel도 workspace 높이를 채움: `builderHeightDelta=0`
    - mobile/tablet list는 약 5-7개 항목 높이만 보여주고 내부 scroll로 전환
    - list row text clipping 방지를 위해 row height를 mobile/tablet `64px`, desktop 이상 `70px`로 조정
    - mobile/tablet list collapse는 왼쪽 rail이 아니라 상단 가로 bar로 표시해 editor가 전체 폭을 사용
    - YAML editor에 좌측 line number gutter 추가
    - builder 내부 form font/input density와 1열/2열 반응형 grid를 재정리해 field 침범 방지
  - [ ] Scenario Builder V3 follow-up
    - mobile/tablet은 builder와 YAML을 동시에 세로로 누르지 말고 `빌더 / YAML` segmented tab 또는 drawer로 분리
    - QHD 이상에서 YAML 초광폭 line length/readability 상한 검토
    - 긴 command/body JSON은 full-screen editor affordance 또는 auto wrap 제공
    - viewport matrix evidence: `output/web-dashboard/viewport-matrix-fhd-scenario.png`, `output/web-dashboard/viewport-matrix-qhd-scenario.png`

- [ ] Suite Composer visual builder
  - [x] scenario 추가/삭제/정렬
  - [x] `tier`, `allowFailure`, `enabled` 편집
  - [x] `maxParallel` 편집
  - [x] 새 실행 묶음 생성 dialog는 hidden default scenario를 자동 포함하지 않고, 사용자가 명시적으로 선택한 scenario만 저장
  - [x] create dialog draft reset regression 방지: parent refresh/re-render 중 입력한 id/name/path가 기본값으로 되돌아가지 않음
  - gap-probe scenario는 amber 상태로 표시

- [ ] Fixture Studio 보강
  - [x] PowerShell parse validation
  - fixture side effect 요약 영역
  - fixture를 참조하는 scenario reverse lookup

- [ ] API error 정규화
  - raw JSON/string 대신 사용자 조치 가능한 메시지 표시
  - 예: `configPath는 config/ 아래 YAML이어야 합니다`
  - 예: `QGA 미응답: template의 qemu-guest-agent 설치와 서비스 상태를 확인하세요`

## P2: 유지보수와 품질

- [x] `apps/web/src/app/page.tsx` thin entrypoint 유지
- [x] Dashboard presentational component 1차 분리
  - `components/authoring.tsx`
  - `components/common.tsx`
  - `components/lab-status.tsx`
  - `components/results.tsx`
- [x] Dashboard helper 1차 분리
  - `lib/api.ts`
  - `lib/commands.ts`
  - `lib/formatting.ts`
  - `lib/result-summary.ts`
  - `lib/ui-state.ts`
- [x] Dashboard 화면 섹션 1차 분리
  - `sections/LoginScreens.tsx`
  - `sections/DashboardHome.tsx`
  - `sections/ResultsExplorer.tsx`
- [x] NestJS feature module 1차 도입
  - `features/*/*.module.ts`
  - `infrastructure/prisma/prisma.module.ts`
  - `infrastructure/workspace/workspace.module.ts`
- [x] Builder DTO 추가: `features/builder/dto/builder.dto.ts`
- [ ] Dashboard state/effect custom hook 분리
  - `useDashboardAuth`
  - `useDashboardCatalog`
  - `useDashboardRuntime`
  - `useDashboardEditors`
  - `useDashboardBuilders`
- [ ] API service 내부 책임 분리
  - `JobCommandFactory`
  - `JobProcessRunner`
  - `JobEventStream`
  - `ProxmoxLabClient`

### 2026-04-24 구조 리팩터링 검증 메모

- [x] Playwright browser smoke: login -> dashboard -> scenario -> results
- [x] Web UI scenario run smoke: `20260424-163351-demo-powershell-system-windows`, `passed`
- [x] Skeleton run 결과 상세에서 없는 `logs/progress.jsonl`을 자동 요청하지 않도록 수정
- [x] 새 browser session에서 Results Explorer console errors `0`
- [x] screenshots:
  - `output/web-dashboard/structure-refactor-dashboard.png`
  - `output/web-dashboard/structure-refactor-scenario.png`
  - `output/web-dashboard/structure-refactor-results.png`
  - `output/web-dashboard/structure-refactor-skeleton-result-no-progress-error.png`

- [ ] i18n message catalog와 glossary 분리
  - `Fixture` 단독 음역 금지
  - `환경 준비 스크립트(Fixture)`를 문서/화면에서 통일

- [ ] Results filtering/search
  - passed/failed/running
  - suite/scenario
  - required failure/allowed failure
  - failureClass

- [ ] Browser upload UX
  - [x] 단일 파일 artifact upload와 `.web-artifacts/` path 자동 선택
  - [x] 폴더 선택 upload와 `.web-artifacts/<timestamp>-<folder>/` directory path 자동 선택
  - [x] 큰 폴더 upload는 API server `:3001` 직접 전송으로 Next rewrite proxy 500 회피
  - [x] 제품 Release 폴더 같은 디렉터리 artifact는 직접 경로 입력으로 확인
  - [x] 좁은 panel에서 upload/recommendation card responsive layout 정리
  - [x] 파일/폴더 upload progress와 선택/완료/실패 상태 카드
  - [x] ZIP/file upload progress
  - [x] artifact hash 표시
    - Artifact Manager 목록/detail에서 repo/uploaded file SHA-256 표시
  - [x] artifact size/modified time 표시
  - [x] 최근 artifact path 표시
  - [x] scenario-aware preset recommendation

- [ ] 접근성/반응형 보강
  - keyboard focus style
  - form label 연결
  - tab/nav landmark
  - 1366x768 viewport 확인
  - 768x1024 viewport 확인
  - 390x844 viewport 확인
  - 좁은 viewport에서 result badge 2-line fallback

- [x] product-specific 제품 Release 폴더 Web 실행 검증
  - [x] 실행 묶음 Web smoke: `cmognt5bg000usmmg6u6uvktu`, 실제 VM 실행과 결과/실패 표시 확인
  - [x] QGA `exec-status` transient retry 후 `path-profile` Web 재실행: `cmogpdv9r002gsmmg4f7b062i`, `passed`

- [ ] Web dashboard Playwright smoke test 정식화
  - login/logout
  - language switch
  - scenario search
  - mocked run launch
  - SSE pass/fail display
  - result explorer drill-down
  - [x] scenario/fixture/suite create dialog smoke uses stable `data-testid` selectors instead of input order

## 권장 개발 순서

1. Lab Status API/UI
2. Run Launcher readiness gate와 command preview
3. SSE pass/fail notice와 error message 정규화
4. Results Explorer master-detail
5. `progress.jsonl` timeline
6. Suite Composer visual builder
7. Component/API/i18n 분리
