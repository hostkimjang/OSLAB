# oslab 구현 체크리스트

> 내부 작업 로그입니다. 공개 온보딩은 `README.md`와 `docs/index.md`에서 시작하고, 이 파일은 구현 진행 상황과 lab 검증 기록을 추적하기 위한 개발자용 문서입니다.

최종 업데이트: 2026-04-29

## 현재 상태 요약

`oslab`은 현재 Python CLI 골격, scenario/config 검증, Proxmox API 연결, 읽기 전용 lab preflight, VMID 할당, 실제 clone/boot smoke, QEMU Guest Agent command 실행, 작은 파일 upload/download, Windows guest preflight, Windows fixture upload/execution/expected output 수집, folder/installer artifact upload/command execution/output collection, archive 기반 folder artifact transfer, artifact smoke 단계별 progress console 출력, artifact smoke JSON/JUnit/HTML report writer, full `oslab run` artifact output layout, full run guest preflight/fixture 통합, product-specific template `config.ini` 오염 preflight, product step sequence 실행, host env 기반 secret token resolve/redaction, product stdout JSON capture, scan 완료 정보 `run.json` 요약, QGA UTF-8/CP949 mojibake 복구, QGA `exec-status` transient retry, `stdoutJson.ok == false` 실패 판정, product-specific raw output normalize, canonical inventory assertion 평가, canonical inventory 분석 artifact, canonical command result adapter, command stdout/exit-code assertion, PowerShell/Python/C/fixture-state/agent-steps demo suite, Windows demo bootstrap fixture, product-specific scan OS/profile fixture 검증, product-specific 전용 scenario/fixture 하위 디렉터리 분리까지 구현되어 있습니다.

Web dashboard v1은 NestJS API + Next.js UI 기반으로 추가되어 있으며, local account login, English/Korean language switch, logout, scenario/suite/fixture catalog, file editor, validation, run launcher, Artifact Manager, live log stream, result explorer를 제공합니다.

브라우저 기반 회귀 검증은 [Browser Debug Checklist](browser-debug-checklist.md)에 누적합니다.

최근 실제 lab 결과:

- Proxmox API 연결: 통과
- Node `<lab-node>`: 통과
- Windows template VMID `9101`: 통과
- Template flag: 통과
- Clone smoke: 통과
- Clone smoke 이후 cleanup: 통과
- Windows QEMU Guest Agent 수정 clone `9101`을 새 template `windows11-template-qga-9101`로 변환
- Boot smoke: `9101` template에서 `9102` clone 생성, boot, QEMU Guest Agent 확인, cleanup 통과
- QGA file transfer: `README.md`를 `9102` clone에 upload/download하고 SHA256 hash 일치 확인
- Windows guest preflight: PowerShell version, admin context, execution policy, `C:\Oslab` directory, file round-trip, cleanup check 통과
- Fixture smoke: `gold-lite.ps1` upload/execution, `C:\Oslab\expected_inventory.json` collect/JSON parse, cleanup 통과
- Artifact smoke: fake folder artifact upload, command template remote execution, `C:\Oslab\scan-result.json` collect/JSON parse, normalized inventory write, `inventory.contains` assertion 평가, cleanup 통과
- Installer smoke: fake installer upload, installCommand execution, installed scanner execution, output collect/normalize/assertion, cleanup 통과
- Product step smoke: fake Agent CLI installer upload, register/status/scan 순차 실행, stdout JSON capture, output collect/normalize/assertion, cleanup 통과
- Real Agent status smoke: 실제 `ProductAgent.exe` Release artifact archive upload, status-only command execution, output collect/normalize/assertion, cleanup 통과
- Real Agent full smoke: 실제 `ProductAgent.exe cli_mode register/status/scan` 실행, host token 없이 register/login 후 config.ini token 저장, HTML/JUnit/JSON report 생성, cleanup 통과
- product-specific Agent step contract full smoke: `expectStdoutJson` gate 적용 후 register/status/scan 통과, run id `20260422-182034-product-specific-agent-cli-windows`, normalized inventory 4 records, scan output 217055 bytes, cleanup 통과
- product-specific Agent OS profile scan: registry x64/WOW6432/Korean path fixture 3개를 실제 scan으로 검출, run id `20260422-182820-product-specific-agent-os-profile-windows`, normalized inventory 7 records, assertions 4개 통과, cleanup 통과
- product-specific Agent path profile scan: Program Files, Program Files (x86), space/symbol, Unicode path, deep path fixture 5개를 실제 scan으로 검출, run id `20260422-183716-product-specific-agent-path-profile-windows`, normalized inventory 9 records, assertions 8개 통과, cleanup 통과
- product-specific Windows v1 suite: run id `20260423-135819-product-specific-windows-v1`, 5 scenarios 실행, required 4개 통과, Appx read-only gap probe 1개 allowed failure, cleanup 통과
- product-specific plugin normalize: sample raw JSON을 `product-specific.inventory` adapter로 canonical inventory 변환 통과
- Inventory analysis: 최신 실제 full smoke의 `normalized/inventory.json`을 분석해 record/source/publisher/confidence/quality summary 생성 통과
- Generic Python demo: clean Windows clone에서 portable Python bootstrap 후 `hello from python` 검증 통과
- Generic C demo: clean Windows clone에서 TinyCC bootstrap 후 `hello from c` 검증 통과
- External Cloudflare Tunnel Proxmox access: 기본 `Python-urllib/3.13` 시그니처는 Cloudflare `403 Error 1010`으로 차단되었고, explicit `User-Agent: oslab/0.1.0` 적용 후 `GET /version`, `GET /nodes`, `GET /cluster/resources?type=vm`, template config read가 다시 통과

최근 로컬 테스트 결과:

```text
uv run pytest
155 passed
```

## 2026-04-22 product-specific Scan OS/Profile 검증 진행 결과

- [x] 실제 Agent scan 검증 목표를 `register/status/scan` 성공 여부에서 "OS 상태 fixture가 inventory로 정확히 검출되는지"로 확장
- [x] `product-specific.inventory` adapter가 실제 Agent output의 `sw_vendor`, `sw_manufacturer`, `sw_install_path`, `sw_dependencies`를 canonical publisher/evidence로 mapping
- [x] product-specific real/legacy scenario를 `scenarios/windows/product-specific/` 하위로 이동
- [x] product-specific fixture를 `validation/fixtures/windows/product-specific/` 하위로 이동
- [x] Nested scenario path에서도 fixture source를 repo root 기준으로 resolve하도록 fixture runner 수정
- [x] Clean baseline scenario 추가: `scenarios/windows/product-specific/product-specific-agent-clean-baseline.example.yaml`
- [x] Appx read-only gap probe scenario 추가: `scenarios/windows/product-specific/product-specific-agent-appx-readonly.example.yaml`
- [x] Appx read-only fixture 추가: `validation/fixtures/windows/product-specific/product-specific-appx-readonly.ps1`
- [x] product-specific Windows v1 suite 추가: `validation/suites/product-specific-windows-v1.example.yaml`
- [x] Compose-like `oslab suite-run --suite ...` CLI 추가
- [x] `oslab suite-run --max-parallel <n>` 병렬 실행 옵션 추가
- [x] 병렬 suite progress event에 `[suite-entry]` prefix와 `suiteEntry` detail 추가
- [x] 실제 product-specific Windows v1 suite 실행 통과: `20260423-135819-product-specific-windows-v1`
- [x] Suite 결과: `total: 5`, `passed: 4`, `failed: 1`, `requiredFailed: 0`, `allowedFailed: 1`
- [x] 실제 product-specific Windows v1 suite 병렬 실행 통과: `20260423-141756-product-specific-windows-v1`, `--max-parallel 2`
- [x] 병렬 실행에서 VMID `9102`, `9103` 동시 할당 확인 및 cleanup 통과
- [x] Suite aggregate HTML report 구현: `reports/suite.html`
- [x] Suite aggregate JUnit report 구현: `reports/suite.junit.xml`
- [x] Suite allowed failure는 aggregate JUnit에서 skipped testcase로 기록
- [x] Appx read-only fixture가 inbox Appx 후보 3개를 기록함: `Microsoft.DesktopAppInstaller`, `Microsoft.WindowsStore`, `Microsoft.WindowsCalculator`
- [x] Appx read-only scan 결과는 `Appx` source 미검출로 `assertion_failure`; Agent Appx/MSIX inventory gap 증거로 기록
- [x] 최신 suite artifact secret scan 결과: `remainingSecretFileHits=0`
- [x] 최신 Proxmox resource preflight cleanup 확인: `usedInRange: <none>`
- [x] Registry OS profile fixture 추가: `validation/fixtures/windows/product-specific/product-specific-os-profile.ps1`
- [x] Registry OS profile scenario 추가: `scenarios/windows/product-specific/product-specific-agent-os-profile.example.yaml`
- [x] Registry profile 검증 항목: HKLM x64 uninstall key, WOW6432 uninstall key, Korean path fixture
- [x] 실제 Registry profile run 통과: `20260422-182820-product-specific-agent-os-profile-windows`
- [x] Registry profile 결과: `records: 7`, `assertions: 4 total, 0 failed`, `missingPublisher: 0`, `missingEvidencePath: 0`
- [x] Path profile fixture 추가: `validation/fixtures/windows/product-specific/product-specific-path-profile.ps1`
- [x] Path profile scenario 추가: `scenarios/windows/product-specific/product-specific-agent-path-profile.example.yaml`
- [x] Path profile 검증 항목: `Program Files`, `Program Files (x86)`, space/symbol path, Unicode path, deep path
- [x] 실제 Path profile run 통과: `20260422-183716-product-specific-agent-path-profile-windows`
- [x] Path profile 결과: `records: 9`, `assertions: 8 total, 0 failed`, `missingPublisher: 0`, `missingEvidencePath: 0`
- [x] product-specific scan profile matrix 목표 문서화: `docs/product-specific_docs/scan-profile-matrix.md`
- [x] 최신 두 실제 run artifact secret scan 결과: `remainingSecretFileHits=0`
- [x] 최신 Proxmox resource preflight cleanup 확인: `usedInRange: <none>`
- [x] 로컬 테스트 결과: `155 passed`

## 2026-04-23 Web Dashboard V1 진행 결과

- [x] NestJS API workspace 추가: `apps/api`
- [x] Next.js dashboard workspace 추가: `apps/web`
- [x] Shared TypeScript DTO package 추가: `packages/shared`
- [x] Web Dashboard 서버 실행 가이드 추가: `docs/web-dashboard-server.md`, `docs/web-dashboard-server.ko.md`
- [x] Local account auth, session cookie, admin upsert 구현
- [x] Scenario/suite/fixture catalog API 구현
- [x] Allowlisted file read/write API 구현
- [x] Scenario/suite validation API 구현
- [x] Job runner API 구현: `uv run oslab run`, `uv run oslab suite-run`
- [x] SSE 기반 live job log stream 구현
- [x] Runs/result explorer API 구현
- [x] Dashboard UI 구현: Dashboard, Scenario Studio, Fixture Studio, Suite Composer, Run Launcher, Results Explorer
- [x] English/Korean language switch 추가
- [x] 한국어 UI 용어 정리: `Fixture`는 `환경 준비(Fixture)`, `Suite`는 `실행 묶음(Suite)`로 표기
- [x] Logout action 추가
- [x] Scenario/fixture/suite catalog search/filter 추가
- [x] YAML/PowerShell editor 줄바꿈/스크롤 가독성 개선
- [x] Login 실패를 alert 대신 inline notice로 표시
- [x] 주요 action 실패 처리 추가: file open/save/validate/run API error를 notice로 표시
- [x] Artifact path 미입력 시 실행 방지 및 실행 버튼 비활성화
- [x] SSE live log 오류 처리와 log size cap 추가
- [x] Scenario/Fixture/Suite 탭별 editor state 분리
- [x] Scenario/Fixture/Suite authoring 기본 읽기 전용 모드 적용
- [x] `수정` 버튼을 누른 뒤에만 YAML/PowerShell editor 편집 가능
- [x] 편집 중 `저장`/`취소` action 제공, 저장/취소 후 읽기 전용으로 복귀
- [x] 저장하지 않은 변경이 있는 상태에서 다른 파일을 열 때 discard confirm 표시
- [x] 브라우저 검증: `readOnlyBefore=true`, `readOnlyAfter=false`, `readOnlyAfterCancel=true`
  - screenshot: `output/web-dashboard/editor-readonly-before-edit.png`
  - screenshot: `output/web-dashboard/editor-readonly-after-edit.png`
- [x] Lab Status API 구현: `GET /api/lab/status`
  - config/env 존재 여부 확인
  - Proxmox token env 존재 여부 확인
  - Proxmox API `/version`, `/nodes`, `/cluster/resources?type=vm`, template config 읽기 전용 조회
  - VMID range used/free/reserved/recommended 계산
  - running/stale `oslab-*` VM 목록 계산
- [x] Lab Status UI 구현
  - Dashboard 상단 `랩 상태` 패널
  - Run Launcher 상단 `랩 상태` 패널
  - status badge: `준비됨`, `주의 필요`, `실행 차단`
  - 실제 확인: Proxmox `9.1.1`, node `softverse`, template `9101`, VMID range `9102-9199`, free `98`, running/stale `0`
  - screenshot: `output/web-dashboard/lab-status-dashboard.png`
  - screenshot: `output/web-dashboard/lab-status-run-launcher.png`
- [x] Run Launcher 최소 readiness gate 구현
  - Lab Status가 `blocked`이면 실행 버튼 비활성화
  - suite/scenario CLI command preview 표시
  - `maxParallel` 값을 Lab Status required capacity로 반영
- [x] 동시 실행 수 기본값을 `1`로 변경
- [x] 전역 실행 상태 배너 구현
  - 실행 중 job이 있으면 모든 탭 상단에 small banner 표시
  - spinner animation 표시
  - `실행 탭 열기`, `결과 보기` action 제공
  - screenshot: `output/web-dashboard/global-run-banner.png`
- [x] 실시간 콘솔 UX 보강
  - job launch 직후 selected job 설정
  - selected job log 즉시 fetch
  - 실행 중 job이 있는데 selected job이 비어 있으면 자동 선택
  - console auto-scroll
  - 수동 `로그 불러오기` button 제공
  - SSE를 Next proxy 대신 API direct stream으로 연결
  - API SSE response `flushHeaders`, keepalive heartbeat 추가
  - API subprocess env에 `PYTHONUNBUFFERED=1`, `PYTHONIOENCODING=utf-8` 적용
  - 브라우저 검증: `cmobhakgn0003sm7k9e2ue938`, `20260423-214920-demo-python-hello-windows`, `passed`
  - console에 `== oslab run ==`, env load, provider preflight, run directory created 등 진행 로그 표시 확인
  - screenshot: `output/web-dashboard/live-console-streaming-fixed2.png`
- [x] 레이아웃 overflow 수정
  - Run Launcher 좌측 설정 panel 내부 스크롤
  - Live Console panel 내부 스크롤
  - Scenario/Fixture/Suite editor list 내부 스크롤
  - Results list 내부 스크롤
  - Results detail/timeline 내부 스크롤
  - screenshots: `output/web-dashboard/layout-run-fixed.png`, `output/web-dashboard/layout-results-fixed.png`, `output/web-dashboard/layout-scenario-fixed.png`
- [x] Run Launcher `None` 옵션 추가
  - Suite select: `없음 - 단일 시나리오 실행`
  - Scenario select: `없음 - 실행 묶음만 실행`
  - suite/scenario 실행 버튼은 각 선택 상태에 따라 독립 활성화
  - 단일 scenario run은 artifact path 없이 `oslab run` skeleton mode 허용
  - suite run은 artifact path가 있을 때만 활성화
  - 브라우저 검증: artifact 없음 + suite 없음에서 scenario button 활성화, suite button 비활성화
  - API 검증: artifact 없는 scenario job `cmob6stgu0003sml0kv42q75i`, run `20260423-165536-demo-powershell-system-windows`, `passed`
  - screenshot: `output/web-dashboard/run-launcher-none-options.png`
- [x] Artifact path read-only existence check 구현: `GET /api/artifacts/check`
- [x] Artifact catalog API 구현: `GET /api/catalog/artifacts`
  - `validation/artifacts` 하위 folder artifact와 `.ps1/.zip/.exe/.msi/...` file artifact 노출
  - Web upload artifact가 저장되는 `.web-artifacts`도 catalog에 포함
- [x] Run Launcher Artifact 선택 UI 구현
  - `Artifact 선택` dropdown 추가
  - `없음 - 시나리오 skeleton run`
  - `직접 입력 - 파일/폴더 경로`
  - `validation/artifacts/hello-c`, `hello-python`, `powershell-system` 등 선택 가능
  - artifact catalog 항목 선택 시 path input 비활성화
  - `직접 입력 - 파일/폴더 경로` 선택 시 path input 활성화
  - 브라우저 검증: `selectedValue=validation/artifacts/hello-c`, catalog 선택 시 input disabled, 직접 입력 시 input enabled
  - screenshot: `output/web-dashboard/artifact-catalog-check.png`
- [x] Run Launcher Artifact upload 1차 구현
  - API: `POST /api/artifacts/upload`, `GET /api/artifacts/uploads`
  - 허용 확장자: `.zip`, `.exe`, `.msi`, `.ps1`, `.cmd`, `.bat`, `.py`, `.c`, `.json`, `.txt`
  - 업로드 성공 후 `.web-artifacts/...` path가 현재 artifact path로 선택되고 existence check가 ready로 이어짐
  - 폴더 선택은 `POST /api/artifacts/upload-directory`로 지원. 선택 폴더 내용은 `.web-artifacts/<timestamp>-<folder>/` 아래로 복사되고 생성된 directory path가 현재 artifact path로 선택됨
  - 브라우저 보안상 picker가 원본 `C:\...\Release` 절대 경로를 넘기지 않으므로, 기존 dashboard 서버 로컬 디렉터리를 복사 없이 쓰려면 `직접 입력 - 파일/폴더 경로` 사용
  - 직접 업로드 상태 카드: 선택됨/업로드 중/사용 중/실패, 파일 수, 바이트 진행률, 저장 경로 표시
  - smoke: `output/web-dashboard/artifact-upload-api-smoke.json`, `output/web-dashboard/run-launcher-artifact-upload-smoke.json`
  - folder/responsive smoke: `output/web-dashboard/artifact-folder-upload-responsive-smoke.json`
  - screenshots: `output/web-dashboard/run-launcher-artifact-upload-desktop.png`, `output/web-dashboard/run-launcher-artifact-upload-mobile.png`, `output/web-dashboard/artifact-folder-upload-controls-responsive.png`, `output/web-dashboard/artifact-folder-upload-responsive.png`
- [x] Artifact Manager / Web-authorable artifact MVP 구현
  - API: `GET /api/artifacts/manage`, `GET /api/artifacts/content`, `POST /api/artifacts/template`, `PUT /api/artifacts/content`
  - Shared type: `ManagedArtifactItem`, `ArtifactTemplateKind`
  - `validation/artifacts/**` repo artifact와 `.web-artifacts/**` uploaded artifact를 source/type/size/fileCount/modifiedAt/SHA-256 metadata와 함께 통합 표시
  - text-like repo artifact template 생성/미리보기/수정/diff 저장 지원: `.ps1`, `.sh`, `.py`, `.c`, `.json`, `.txt`, `.cmd`, `.bat`
  - `.web-artifacts/**`, binary file, directory artifact는 실행 선택/read-only로 유지
  - Browser smoke: `output/web-dashboard/artifact-manager-smoke.json`, errors `0`
  - Screenshots: `output/web-dashboard/artifact-manager-list.png`, `output/web-dashboard/artifact-manager-create-text.png`, `output/web-dashboard/artifact-manager-edit-diff.png`, `output/web-dashboard/artifact-manager-run-result.png`, `output/web-dashboard/artifact-manager-qhd.png`, `output/web-dashboard/artifact-manager-tablet.png`, `output/web-dashboard/artifact-manager-mobile.png`
- [x] Artifact Studio + Script Assist 구현
  - 좌측 nav `아티팩트` 독립 화면 추가, Run Launcher의 `테스트 파일 관리` modal도 같은 Studio를 사용
  - API: `POST /api/artifacts/project-template`, `POST /api/artifacts/assist/check`
  - Shared type: `ArtifactProjectTemplateKind`, `ArtifactProjectTemplateRequest`, `ArtifactAssistIssue`, `ArtifactAssistSnippet`, `ArtifactAssistCheckResult`
  - 생성 모드: 단일 파일, 폴더형 프로젝트, product-specific starter
  - Monaco editor lazy-load, 확장자 기반 language mode, OSLAB placeholder/output contract/product-specific wrapper snippet 제공
  - Script Assist는 실행 없이 JSON parse, placeholder 오타, output JSON 힌트, 위험 경로/파괴적 명령 warning을 정적 검사
  - AI 도움 탭은 실제 모델 호출 없이 extension point로만 제공
  - Safety: 생성/편집 가능 root는 `validation/artifacts/**`, `.web-artifacts/**`와 binary/directory artifact는 read-only/selection-only
- [x] Artifact Studio binary/folder 실행 전용 관리 및 archive/delete 구현
  - API: `GET /api/artifacts/tree`, `POST /api/artifacts/archive`, `POST /api/artifacts/delete`
  - Shared type: `ArtifactTreeResponse`, `ArtifactManageActionResponse`
  - `validation/artifacts/**`, `.web-artifacts/**`, `.artifact-archive/**`를 관리 목록에서 구분 표시
  - binary artifact는 size/hash/modified metadata 중심의 실행 전용 상세로 표시하고 editor 미노출
  - directory artifact는 fileCount/totalBytes와 제한된 tree preview 표시, symlink traversal 차단
  - repo artifact는 direct hard delete 차단, archive-first로 `.artifact-archive/**` 이동
  - uploaded/archive artifact는 dry-run/confirmToken modal 후 delete 가능
  - API unit test: tree, archive, delete, invalid path, binary content read/write 거부 확인
  - Browser QA: FHD/QHD/tablet/mobile에서 folder tree, binary read-only detail, repo archive, archived delete, uploaded binary delete 확인
  - Run Launcher 연결 QA: Artifact Studio에서 `validation/artifacts/powershell-system` directory를 `실행에서 사용`으로 적용해 실행 탭 ready 상태와 artifact path 반영 확인
  - Regression fix: archived artifact 삭제 후 빈 `.artifact-archive/<timestamp>/repo/...` 부모 폴더를 cleanup해 목록에 0-byte 잔여 폴더가 남지 않음
  - screenshots: `output/web-dashboard/artifact-studio-folder-tree-fhd.png`, `artifact-studio-archive-modal-fhd.png`, `artifact-studio-delete-modal-fhd.png`, `artifact-studio-binary-readonly-fhd.png`, `artifact-studio-binary-readonly-qhd.png`, `artifact-studio-tablet-layout.png`, `artifact-studio-mobile-layout.png`, `artifact-studio-directory-run-launcher-applied.png`
- [x] Artifact Studio 생성 흐름 + Script Assist 언어팩 개선
  - Shared type: `ArtifactStudioMode`, `ArtifactLanguageKind`, `ArtifactLanguageToolStatus`, `ArtifactLanguageToolInstallResponse`
  - API: `GET /api/artifacts/language-tools`, `POST /api/artifacts/language-tools/install`, `POST /api/artifacts/assist/check` language/toolStatus/firstRunTips 확장
  - `새 아티팩트 제작` 진입 시 선택 artifact를 해제하고 create mode 전용 제작 가이드 화면을 표시
  - 단일 파일/폴더형 프로젝트/product-specific starter 생성 완료 후 새 artifact 자동 선택 및 Run Launcher/Scenario Builder 적용 가능
  - Monaco model은 artifact path 기준으로 유지하고 snippet 삽입은 Monaco edit operation으로 처리해 cursor/focus 튐을 줄임
  - Script Assist는 PowerShell, shell, Python, JSON, CMD/BAT, C, txt language/tool status와 처음 만들기 안내를 표시
  - Lab Status partial response guard 추가: `checks.*` 누락 응답에서도 client runtime crash 방지
  - test: `corepack pnpm exec playwright test apps/web/tests/artifact-studio-create-assist.spec.js --config=playwright.web-dashboard.config.cjs`
  - screenshots: `output/web-dashboard/artifact-studio-create-flow.png`, `output/web-dashboard/artifact-studio-assist-language-tools.png`
- [x] Artifact Studio 전체 언어 LSP Assist 표면 구현
  - Shared type: `ArtifactAssistCompletionRequest`, `ArtifactAssistCompletionResponse`, `ArtifactAssistDiagnosticsResponse`, `ArtifactLanguageToolMode`
  - API: `POST /api/artifacts/assist/complete`, `POST /api/artifacts/assist/diagnostics`
  - API service: `ArtifactLanguageService`가 Python/shell/JSON repo-bundled public LSP를 먼저 호출하고, PowerShell/C project-local tool cache 상태, BAT/CMD/txt internal provider 상태를 반환
  - Open LSP smoke: Python `print/range`와 JSON `$schema`가 `source=lsp`로 반환되고, shell command/OSLAB 제작 스니펫은 fallback dataset으로 병합됨
  - Internal fallback/lint dataset: Python/shell/PowerShell/JSON/C/BAT 기본 completion과 언어별 위험 패턴 warning 보강
  - Monaco provider는 backend completion을 비동기로 호출하고 실패 시 local snippet fallback을 사용
  - Script Assist `도움`/`자동완성` 탭 추가, 처음 만들기 안내와 언어별 추천 항목/trigger/예시/삽입 action 한국어 설명 제공
  - Popup clipping fix: Monaco `fixedOverflowWidgets`와 suggest/hover/marker z-index 정리
  - API unit test: Python `pri` -> `print`, JSON `schemaVersion`, diagnostics JSON parse error, invalid root 거부
  - Browser regression: `corepack pnpm exec playwright test apps/web/tests/artifact-studio-create-assist.spec.js --config=playwright.web-dashboard.config.cjs`
  - Visible FHD QA: 사용자 화면의 Chrome에서 Artifact Studio를 직접 조작해 Python `pri` -> `print`, `for i in ra` -> `range`, 자동완성 안내 탭 확인
  - smoke: `output/web-dashboard/artifact-studio-lsp-open-service-smoke.json`
  - visible smoke: `output/web-dashboard/artifact-studio-visible-browser-smoke.json`
  - screenshot: `output/web-dashboard/artifact-studio-python-lsp-print.png`
  - screenshot: `output/web-dashboard/artifact-studio-python-lsp-range.png`
- [x] Artifact Studio 생성 artifact 실제 run 검증
  - 생성 파일: `validation/artifacts/web-ui-demo-20260430123434/run-system-demo.ps1`
  - Run Launcher 적용 경로: `validation/artifacts/web-ui-demo-20260430123434`
  - Web job: `cmokxp8su0003smrog10l9yo1`
  - Run id: `20260430-123836-demo-powershell-system-windows`
  - 결과: `passed`, preflight `6/0`, assertions `2/0`, artifact upload `1 files / 438 B`, cleanup destroyed VM `9103`
  - 자동완성 popup QA: PowerShell/placeholder snippet 표시, browser console errors `0`, API/Web server 유지
  - screenshots: `output/web-dashboard/artifact-studio-demo-created.png`, `output/web-dashboard/artifact-studio-autocomplete-trigger.png`, `output/web-dashboard/artifact-studio-assist-check.png`, `output/web-dashboard/artifact-studio-run-launcher-linked.png`, `output/web-dashboard/artifact-studio-demo-run-complete.png`, `output/web-dashboard/artifact-studio-demo-result-detail.png`
- [x] Run Launcher 디렉터리 artifact 직접 경로 확인
  - 대상 path: `C:\Users\kysky\Documents\gitlab\agent-windows\ProductAgent\bin\Release`
  - API artifact check: `exists=true`, `kind=directory`
  - Browser UI: `테스트 파일 확인됨 · directory`, 시나리오 실행 준비 활성화
  - smoke: `output/web-dashboard/artifact-directory-path-smoke.json`
  - screenshot: `output/web-dashboard/artifact-directory-path-direct-input.png`
- [x] Artifact check UI 구현
  - existing directory/file kind 표시
  - size/modified time 표시
  - missing artifact이면 실제 VM/artifact run 버튼 비활성화
- [x] Advanced run options UI 구현
  - `keepVm`
  - `fullClone`
  - warning copy 표시
- [x] Selected suite policy 요약 표시
  - suite entry count
  - `allowFailure: true` count
- [x] 자동 갱신 구현
  - jobs/runs: 5초 주기
  - Lab Status: 30초 주기
- [x] SSE done/error UX 개선
  - `done` event payload의 `passed`/`failed`를 notice에 표시
  - SSE error 발생 시 job 상태를 재조회하고 이미 완료된 job이면 최종 상태 표시
- [x] Results Explorer master-detail 구현
  - run/suite 목록 선택
  - 결과 검색/상태 필터 toolbar
  - row status badge
  - relative time 표시
  - run detail summary
  - suite summary와 failed-first entries
  - report/log/raw/normalized file links
  - 결과 파일 overlay preview modal
  - screenshot: `output/web-dashboard/result-preview-panel.png`
  - screenshot: `output/web-dashboard/results-redesign-suite.png`
- [x] Results evidence checklist 구현
  - API: `GET /api/runs/:runId/evidence`
  - Web detail: `run.json`, `progress.jsonl`, raw output, normalized output, reports, cleanup state를 present/missing/contract gap으로 표시
  - 실제 artifact run 검증: `20260423-232535-demo-powershell-system-windows`, `total=14`, `present=11`, `contractGaps=0`
  - skeleton run 검증: `20260426-042038-demo-powershell-system-windows`, report 누락이 contract gap으로 표시됨
  - screenshot: `output/web-dashboard/results-evidence-checklist.png`
  - screenshot: `output/web-dashboard/results-evidence-skeleton.png`
- [x] Results 실제 run 파일 discovery 구현
  - API detail: `GET /api/runs/:runId` 응답에 `files` 목록 추가
  - `runs/<run-id>/` 하위 실제 파일을 재귀 스캔하고 core/timeline/outputs/reports/cleanup/other 그룹으로 분류
  - 고정 evidence 계약 밖 파일은 `discovered=true`로 내려 UI에서 `추가 발견` 배지 표시
  - 기대 evidence 경로지만 실제 생성되지 않은 파일은 `status=missing|contractGap`으로 `files`에 포함해 누락 파일 카드로 표시
  - 누락 파일 카드는 link/preview button 없이 상태, 필수/선택 여부, 설명만 보여 dead link 요청을 만들지 않음
  - Previewable text-like artifact 확장자: JSON/JSONL/log/XML/txt/csv/md/yaml/PowerShell/shell/cmd/bat
  - 검증 run: `20260426-174301-demo-python-hello-windows`
  - 발견 파일: `raw/fixture-demo-python-runtime.expected-output.json`
  - 누락 파일: `normalized/inventory.json`, `raw/product-steps.json`, `logs/product.stdout.log`, `logs/product.stderr.log`, `reports/inventory.analysis.json`
  - API smoke: `output/web-dashboard/results-run-files-api-smoke.json`
  - Missing API smoke: `output/web-dashboard/results-run-files-missing-api-smoke.json`
  - Browser smoke: `output/web-dashboard/results-run-files-ui-smoke.json`
  - screenshots: `output/web-dashboard/results-run-files-discovered.png`, `output/web-dashboard/results-run-files-discovered-preview.png`, `output/web-dashboard/results-run-files-missing.png`
- [x] Results list filter/selection mismatch 수정
  - `Failed` 필터 적용 시 리스트와 상세가 서로 다른 run을 보여주던 문제 수정
  - 필터/검색 결과에서 현재 선택 run이 사라지면 첫 visible run으로 선택 보정
  - 검색 결과 0개일 때 빈 상태 표시 및 stale detail 제거
  - smoke: `output/web-dashboard/results-list-selection-fix-smoke.json`
- [x] Results 사람이 읽는 시간 표시
  - 결과 리스트에서 상대 시간과 절대 로컬 시간을 함께 표시
  - 결과 상세에 `결과 시간` 섹션 추가: 실행 시작, 완료, 소요 시간
  - `startedAt/completedAt`이 없으면 `YYYYMMDD-HHMMSS` run ID timestamp fallback 사용
  - browser smoke: `output/web-dashboard/results-human-time-smoke.json`
  - screenshots: `output/web-dashboard/results-human-time-detail.png`, `output/web-dashboard/results-human-time-mobile.png`
- [x] Results 과거 running 상태 보정
  - artifact `run.json`이 `running`으로 남아도 matching dashboard job이 terminal 상태면 job 상태를 우선 표시
  - `20260423-232218-demo-c-hello-windows`: artifact `running`, job `cancelled` -> Results list/detail `cancelled`
  - 리스트/상세에 `상태 보정: running -> cancelled` 표시
  - `멈춤` filter 추가로 dashboard job과 매칭되지 않는 오래된 active artifact 상태를 분리 가능
  - smoke: `output/web-dashboard/results-cancelled-status-detail-smoke.json`
  - screenshot: `output/web-dashboard/results-cancelled-status-detail.png`
- [x] Results 고급 분석 필터
  - API summary: scenario/suite lineage, failure class, required/allowed failure, evidence summary 포함
  - UI filter: 종류(run/suite), 이슈(provider/preflight/assertion/run/suite entry/필수 실패/허용 실패/취소/계약 누락), 증거(정상/누락 있음)
  - row meta: scenario/suite id, failure class, contract gap 수 chip 표시
  - suite detail 선택 시 없는 progress file 404 요청 방지
  - smoke: `output/web-dashboard/results-advanced-filters-smoke.json`
  - screenshot: `output/web-dashboard/results-advanced-filters.png`
- [x] Results list collapse/expand
  - 결과 목록 패널을 접으면 52px rail만 남기고 상세/evidence 본문을 넓힘
  - 펼침/접힘/다시 펼침 상태에서 선택 결과 유지
  - 1366x768 smoke 기준 상세 폭 `566px -> 1014px`, 증가량 `448px`
  - mobile 390x844 horizontal overflow false
  - smoke: `output/web-dashboard/results-list-collapse-smoke.json`
  - screenshots: `output/web-dashboard/results-list-expanded.png`, `output/web-dashboard/results-list-collapsed.png`, `output/web-dashboard/results-list-collapsed-mobile.png`
- [x] Authoring list collapse/expand
  - Scenario/Fixture/Suite 파일 목록 패널을 접으면 52px rail만 남기고 editor 본문을 넓힘
  - 펼침/접힘/다시 펼침 상태에서 선택 파일 유지
  - 1366x768 smoke 기준 editor 폭 `664px -> 1012px`, 증가량 `348px`
  - mobile 390x844 horizontal overflow false
  - smoke: `output/web-dashboard/catalog-list-collapse-smoke.json`
  - screenshots: `output/web-dashboard/catalog-list-scenario-expanded.png`, `output/web-dashboard/catalog-list-scenario-collapsed.png`, `output/web-dashboard/catalog-list-suite-collapsed.png`, `output/web-dashboard/catalog-list-fixture-collapsed-mobile.png`
- [x] Authoring syntax validation/save gate
  - API: `POST /api/validate/content`
  - YAML scenario/suite content parse error를 저장 전 표시
  - PowerShell `.ps1` fixture parse error를 저장 전 표시
  - 문법 오류가 있으면 `저장` 버튼 비활성화, 저장 직전에도 재검사
  - invalid YAML 입력 시 visual builder inspect API가 처리되지 않은 `500`을 내지 않도록 `400`으로 정규화
  - API smoke: `output/web-dashboard/syntax-validation-api-smoke.json`
  - Browser smoke: `output/web-dashboard/syntax-validation-ui-smoke.json`
  - screenshots: `output/web-dashboard/syntax-validation-yaml-valid.png`, `output/web-dashboard/syntax-validation-yaml-invalid.png`, `output/web-dashboard/syntax-validation-powershell-invalid.png`, `output/web-dashboard/syntax-validation-yaml-invalid-mobile.png`
- [x] Scenario Builder V2
  - `id/name/OS family/guest mode/VMID/artifact/cleanup` 필드에 사용자 설명 tooltip 추가
  - enum 성격 필드는 select/chip/toggle로 전환
  - fixture, product step, assertion 반복 섹션을 builder 안에서 추가/편집 가능
  - 새 시나리오 생성 dialog와 Windows/Linux/product-specific template 제공
  - 새 파일 생성은 `POST /api/files` create-only 계약으로 기존 파일 덮어쓰기 방지
  - Scenario 저장 전 `POST /api/validate/scenario-content`로 최소 scenario contract 검증
  - 협업/회의 문서: `docs/devs/scenario-builder-v2-collaboration.md`
  - Browser smoke: `output/web-dashboard/scenario-builder-v2-validation-smoke.json`, `output/web-dashboard/scenario-builder-v2-mobile-smoke.json`
  - screenshots: `output/web-dashboard/scenario-builder-v2-created-desktop.png`, `output/web-dashboard/scenario-builder-v2-tooltip-desktop.png`, `output/web-dashboard/scenario-builder-v2-diff-before-save.png`, `output/web-dashboard/scenario-builder-v2-mobile-editor-fixed.png`
- [x] Results preview modal redesign
  - 기존 inline preview panel 제거
  - file chip `Preview` button과 present evidence row click으로 overlay modal 표시
  - `Esc`, backdrop click, X icon close button 닫기
  - modal open 중 body scroll lock, close button focus 이동
  - desktop/mobile viewport 약 90% responsive modal layout
  - 없는 run file 요청은 처리되지 않은 `500` 대신 `404` 반환
  - smoke: `output/web-dashboard/results-preview-modal-smoke.json`
  - refinement smoke: `output/web-dashboard/results-preview-modal-90pct-smoke.json`
- [x] 카드/섹션 설명 tooltip 1차 구현
  - 공통 `InfoTooltip` component로 원형 `i` 버튼과 portal/fixed tooltip bubble 제공
  - hover, focus, click/tap, `Esc`, outside click 지원
  - Lab Status, dashboard metric/list, Run readiness/step headers, authoring syntax/diff, Results 시간/파일/증거/timeline/file group에 적용
  - 후속 copy 조정: 개발자 내부 상태 설명보다 사용자 기능 설명을 우선. Artifact는 `VM 안에서 테스트할 프로그램, 설치 파일, 스크립트, ZIP 묶음`으로 설명
  - Information 확장: 환경 준비 dashboard metric, Scenario/Fixture/Suite catalog header, Scenario/Suite builder header, Suite policy, Results evidence group header, `run.json`/`progress.jsonl` 등 evidence row에 사용자 관점 설명 추가
  - Evidence row tooltip은 row preview button 내부에 중첩하지 않고 sibling control로 배치해 accessibility와 keyboard focus 계약 유지
  - 1366x768 desktop과 390x844 mobile에서 잘림/가로 overflow 없는 것을 browser smoke로 확인
  - smoke: `output/web-dashboard/info-tooltip-smoke.json`
  - screenshots: `output/web-dashboard/info-tooltip-dashboard-lab.png`, `output/web-dashboard/info-tooltip-dashboard-fixtures.png`, `output/web-dashboard/info-tooltip-scenario-catalog.png`, `output/web-dashboard/info-tooltip-fixture-catalog.png`, `output/web-dashboard/info-tooltip-suite-catalog.png`, `output/web-dashboard/info-tooltip-run-readiness.png`, `output/web-dashboard/info-tooltip-artifact-friendly.png`, `output/web-dashboard/info-tooltip-results-evidence.png`, `output/web-dashboard/info-tooltip-evidence-run-json.png`, `output/web-dashboard/info-tooltip-evidence-progress-jsonl.png`, `output/web-dashboard/info-tooltip-mobile-run.png`
- [x] `progress.jsonl` timeline UI 구현
  - artifact run progress event를 단계형으로 표시
- [x] 브라우저 전체 기능 검증
  - read-only editor: `true -> false`
  - artifact 없는 skeleton scenario run: `cmob7mcny000csmywln8n5ymu`, `passed`
  - artifact 있는 실제 VM demo run: `cmob7mhd6000dsmywchkvb3df`, `20260423-171840-demo-powershell-system-windows`, `passed`
  - Results run detail/timeline screenshot: `output/web-dashboard/all-features-results-detail.png`
  - Results suite detail screenshot: `output/web-dashboard/results-suite-detail.png`
- [x] Stale job reconciliation 구현
  - API service 시작 이전에 생성된 `queued`/`running` job이 현재 API process에 attach되어 있지 않으면 `failed`로 정리
  - 실제 정리 확인: suite job `cmob66hie000asmv0b2knbjb9`
  - error: `Job was left running after API restart and is no longer attached to a live dashboard process.`
  - Results API도 job terminal 상태를 기준으로 stale artifact `running` 표시를 보정
- [x] 접근성 보강: language button `type=button`, `role=status`, `role=log`, report link `rel=noopener`
- [x] `/api/me`는 비로그인 상태에서도 `200 { user: null }` 반환하도록 개선
- [x] favicon 404 제거
- [x] 전문가 협업 기획 문서 추가: `docs/devs/oslab-expert-collaboration-plan.md`
- [x] Run Launcher 단계형 readiness strip 추가
- [x] Run Launcher 5단계 flow 1차 구현
  - 대상 선택, Artifact, 랩과 설정, 옵션, 검토와 실행 section으로 재배치
  - suite/scenario 실행 버튼별 ready/blocked reason 표시
  - artifact checking 중 stale check 결과로 실행 버튼이 켜지지 않도록 조건 보강
  - browser smoke: `output/web-dashboard/run-launcher-step-flow-smoke.json`
  - screenshots: `output/web-dashboard/run-launcher-step-flow-scenario-ready.png`, `output/web-dashboard/run-launcher-step-flow-mobile.png`
- [x] Run Launcher scenario-aware Artifact 추천 1차 구현
  - `demo-powershell-system` 선택 시 `validation/artifacts/powershell-system` 추천 chip 표시
  - 추천 chip 클릭 시 catalog artifact path가 read-only input에 적용되고 existence check가 ready로 표시
  - product-specific 전용 scenario는 repo-local 제품 artifact가 catalog에 없으면 demo artifact 추천 제외
  - mobile Run 화면은 page-level scroll로 전환해 390x844에서 Artifact 단계가 잘리지 않음
  - browser smoke: `output/web-dashboard/run-launcher-artifact-recommendation-smoke.json`
  - screenshots: `output/web-dashboard/run-launcher-artifact-recommendation-desktop.png`, `output/web-dashboard/run-launcher-artifact-recommendation-mobile.png`
- [x] Scenario/Fixture/Suite editor 저장 전 diff preview 추가
- [x] Web Lab Status Proxmox 요청에 CLI provider와 동일한 `User-Agent` 적용
- [x] Web API `ProxmoxLabClient` 분리: URL normalization, HTTP header policy, stop polling
- [x] Web Dashboard 전체 기능 감사형 browser smoke
  - 흐름: login, language switch, dashboard, scenario/fixture/suite authoring, run launcher, live console, results, mobile views
  - skeleton scenario run: `20260426-042038-demo-powershell-system-windows`, `passed`
  - job: `cmoeq5g9g0009sm0s1x4n38lk`
  - browser console issues: `0`
  - network issues: `0`
  - report: `output/web-dashboard/full-browser-audit.json`
- [x] Web Dashboard 모바일/접근성 1차 개선
  - mobile nav horizontal tab bar
  - Run readiness responsive layout
  - `LanguageSwitch` `aria-pressed`
  - primary nav landmark
  - keyboard focus-visible style
  - mobile fix report: `output/web-dashboard/full-browser-audit-mobile-fix.json`
- [x] Web Dashboard 전문가 감사 문서 추가: `docs/devs/web-dashboard-expert-audit-2026-04-26.md`
- [x] 브라우저 직접 확인: login, language switch, scenario search/filter, file open, logout
- [x] Playwright screenshots 저장 위치: `output/playwright/`
- [x] Web dashboard 사용성 전문가 리뷰 결과 정리: `docs/devs/web-dashboard-usability-todo.md`
- [x] Web/API 구조 리뷰 문서화: `docs/devs/dashboard-structure-review.md`
- [x] Next.js dashboard component/helper/section 1차 분리
  - `apps/web/src/features/dashboard/components/*`
  - `apps/web/src/features/dashboard/lib/*`
  - `apps/web/src/features/dashboard/sections/*`
- [x] NestJS feature module 1차 도입
  - `apps/api/src/features/*/*.module.ts`
  - `apps/api/src/infrastructure/prisma/prisma.module.ts`
  - `apps/api/src/infrastructure/workspace/workspace.module.ts`
- [x] Builder controller DTO 분리: `apps/api/src/features/builder/dto/builder.dto.ts`
- [x] Dashboard에서 실제 demo scenario job 실행 검증
  - job: `cmob5p1up0007smv00wkvjmit`
  - run: `20260423-162441-demo-powershell-system-windows`
  - scenario: `scenarios/windows/demo-powershell-system.example.yaml`
  - artifact: `validation/artifacts/powershell-system`
  - result: `passed`
  - VMID `9102` stop/destroy cleanup 완료
- [x] Dashboard에서 실제 Python/C demo scenario 실행 검증
  - Python job: `cmob7y563000lsmywnwcky6au`
  - Python run: `20260423-172744-demo-python-hello-windows`
  - Python stdout: `hello from python`
  - C job: `cmob7zt0b000msmyw5q91gsc1`
  - C run: `20260423-172902-demo-c-hello-windows`
  - C stdout: `hello from c`
  - 두 run 모두 fixture runtime/compiler bootstrap, artifact upload, command execution, assertion, report, cleanup 통과
  - Lab Status 재확인: `ready`, running/stale VM `0`, free VMID `98`
  - screenshots: `output/web-dashboard/web-run-python-result.png`, `output/web-dashboard/web-run-c-result.png`
- [x] Scenario builder dirty-state guard 구현
  - builder draft 수정 후 tab 이동 시 confirm dialog 표시
  - browser refresh / logout 전 확인 포함
  - 좌측 nav에 `수정됨` dirty indicator 표시
- [x] Scenario visual builder v1 구현
  - `id`, `name`, OS family/version, template/templateVmId, vmId range, guest mode, artifact pathParam/destination, report formats
  - fixture/assertion count summary 표시
- [x] Scenario Builder V2 확장
  - 회의록: `docs/devs/scenario-builder-v2-collaboration.md`
  - 필드별 사용자 친화 `i` tooltip 추가: `id`, `name`, `OS family`, `guest mode`, VMID, artifact, output, report, cleanup
  - enum 성격 field는 select/chip/toggle/checkbox로 전환
  - Fixture/Product step/Assertion 추가, 삭제, 편집 및 YAML round-trip
  - 새 시나리오 생성 dialog: Windows smoke, Linux smoke, product-specific smoke template
  - 새 시나리오 생성 dialog compact 비율 보정 및 desktop/mobile browser smoke: `output/web-dashboard/scenario-create-dialog-compact-smoke.json`
  - 새 시나리오 생성 UAT 보강: template summary, “파일만 생성/실행은 나중” 안내, 저장 경로 중복 회피, `id`-path 자동 동기화, dirty-state confirm guard
  - UAT smoke: `output/web-dashboard/scenario-create-uat-smoke.json`
  - UAT screenshots: `output/web-dashboard/scenario-create-uat-dialog.png`, `output/web-dashboard/scenario-create-uat-after-create.png`, `output/web-dashboard/scenario-create-uat-mobile-dialog.png`
  - Scenario Builder V3 vertical axis prototype: 세로 stepper rail + 선택 단계 detail panel + 오른쪽 YAML editor
  - V3 smoke: `output/web-dashboard/scenario-builder-v3-vertical-smoke.json`
  - V3 screenshots: `output/web-dashboard/scenario-builder-v3-vertical-desktop.png`, `output/web-dashboard/scenario-builder-v3-vertical-mobile.png`
  - Full HD/QHD 포함 viewport matrix smoke: `output/web-dashboard/viewport-design-matrix-smoke.json`
  - V3 visual ratio fix: `1366x768` open list builder/YAML `420px/379px`, list collapse 후 YAML `546px`, QHD builder `860px`, mobile/tablet list scroll 제한, mobile/tablet top-bar collapse, YAML line number gutter 적용
  - V3 polish: 단계 버튼 폭/높이 편차 `0`, active step 과강조 완화, builder detail/list 내부 Y scroll 제거, mobile/tablet list collapse glyph 위/아래 방향 적용
  - V3 polish follow-up: 접힘/펼침 glyph를 CSS chevron으로 중앙 정렬, 1366/FHD/QHD YAML editor full-height 적용, `yamlWorkspaceHeightDelta=0`
  - V3 polish follow-up: compact horizontal stepper 첫 column 과확장 제거, `stepButtonGapMax=0`, FHD/QHD builder 폭 `591px`/`860px`로 확대
  - V3 polish follow-up: desktop/FHD/QHD builder panel full-height 적용, scenario list row mobile/tablet `64px` 및 desktop+ `70px`로 조정, list title/path clipping `false`
  - V3 follow-up P0: mobile/tablet은 builder와 YAML을 segmented tab/drawer로 분리
  - 저장 전 scenario contract 검증과 create-only file 생성 API 추가
- [x] Suite visual builder v1 구현
  - `id`, `name`, suite entry list
  - entry add/remove/reorder
  - `tier`, `allowFailure` 편집
  - readonly/open state 브라우저 검증: `output/web-dashboard/suite-builder-readonly.png`
- [x] Recent artifact preset UX 구현
  - 최근 artifact chip 저장/재선택
  - 실제 확인: `validation/artifacts/powershell-system`, `validation/artifacts/hello-c`
- [x] Job cancel action 구현
  - API: `POST /api/jobs/:id/cancel`
  - child process tree terminate + final `cancelled` 상태 기록
  - 실제 browser 검증: job `cmobkm4al0007sm0wxkijzd6w`, status `cancelled`
- [x] Dashboard cleanup action 구현
  - API: `POST /api/lab/cleanup-stale`
  - 기본 대상은 configured VMID range 안의 stopped/stale `oslab-*` VM
  - dry-run 후보와 `confirmToken`을 먼저 반환하고, 같은 후보군 토큰이 확인될 때만 destructive cleanup 진행
  - running VM 삭제는 기본 UI 흐름에서 제외
  - 과거 실제 browser 검증: cleanup 요청 후 `running/stopped oslab VM = 0`
- [x] List header/body 분리로 클릭 가림 문제 수정
  - Scenario list, Results list의 search/filter header를 scroll body에서 분리
  - sticky input/toolbar가 row click을 가리던 문제 해결
- [x] Dense list row 안정화
  - Scenario/Results list row 최소 높이 고정
  - title/path/meta에 ellipsis/clamp 적용
  - 긴 텍스트가 다음 row 영역으로 침범하지 않도록 overflow 차단
  - screenshots: `output/web-dashboard/scenario-list-row-fix.png`, `output/web-dashboard/results-list-row-fix.png`
- [x] Web 구조 1차 리팩터링
  - `apps/web/src/app/page.tsx`를 thin entrypoint로 축소
  - Dashboard 구현을 `apps/web/src/features/dashboard/` 아래로 이동
  - `DashboardPage.tsx`, `model.ts`, `lib.ts`, `components.tsx`로 분리
  - 기존 `page.tsx` 1826 lines -> `DashboardPage.tsx` 874 lines + feature files로 분리
- [x] API 구조 1차 리팩터링
  - flat `apps/api/src/modules/` 제거
  - `common/guards`, `infrastructure/prisma`, `infrastructure/workspace`, `features/*` 구조 도입
  - `app.module.ts`를 root로 이동
  - basic controller-boundary DTO 추가
    - auth login
    - files read/write
    - jobs run-scenario/run-suite
    - lab status/cleanup
    - validation path
  - 구조 리뷰 문서: `docs/devs/dashboard-structure-review.md`
- [x] Dashboard에서 실제 demo run 재검증
  - cancel/cleanup 이후 real VM demo run: `cmobkqcfv0008sm0wg87k1lhy`
  - run: `20260423-232535-demo-powershell-system-windows`
  - result: `passed`
  - screenshot: `output/web-dashboard/run-success-and-console.png`
- [x] Node/Web 검증: `corepack pnpm build`, `corepack pnpm lint`
- [x] Python 검증: `uv run pytest`, `155 passed`
- [x] Dashboard에서 실제 suite result detail UX 검증
- [x] Lab Status view 구현: Proxmox connectivity, node/template, VMID range, running/kept/stale VM 상태
- [x] Lab Status API 구현: config/env 존재, template flag, used/free VMID, running/kept/stale VM, local lock file
- [x] Run Launcher readiness gate 확장: artifact path existence, allowed failure 요약, advanced `keepVm/fullClone` 경고
- [x] SSE done/error UX 개선: `passed`/`failed`와 network interruption을 분리 표시
- [x] Artifact path existence policy 구현
- [x] Stale job reconciliation 구현: API restart 후 DB에 남은 `running` job 감지/정리
- [x] Authoring dirty-state guard 확장: tab 이동, logout, refresh 전 확인 및 diff preview
- [x] Authoring syntax validation 구현: 현재 editor buffer 기준 YAML/PowerShell 저장 전 검사
- [x] Results Explorer master-detail 구현: suite summary, failure class, assertion/product step/fixture/preflight drilldown
- [x] Results list collapse/expand 구현: detail/evidence 본문 공간 확장
- [x] Authoring list collapse/expand 구현: Scenario/Fixture/Suite editor 본문 공간 확장
- [x] progress.jsonl 기반 structured timeline 구현
- [x] Scenario/Suite visual builder 핵심 구현
  - Scenario V2는 fixture/product step/assertion generic form까지 확장
  - Suite V1은 entry add/remove/reorder와 `tier`/`allowFailure` 편집 지원
- [ ] Fixture 전용 visual builder 구현
  - Fixture 파일 자체의 side-effect/expected manifest를 schema-aware form으로 편집하는 작업은 별도 후속
- [x] New Fixture creation 1차 구현
  - 회의록: `docs/devs/authoring-expansion-collaboration-plan.md`
  - `New Scenario`와 같은 create-only/no-overwrite/catalog refresh/edit mode/diff modal 흐름 적용
  - 허용 경로: `validation/fixtures/**/*.ps1|sh`
  - 기본 template: Windows PowerShell fixture, Linux shell fixture
  - 남음: product-specific profile starter, fixture reference flow, mobile/FHD/QHD visual matrix
- [x] New Suite creation 1차 구현
  - 회의록: `docs/devs/authoring-expansion-collaboration-plan.md`
  - 허용 경로: `validation/suites/**/*.yaml|yml`
  - id/name/path, scenario multi-select, smoke/matrix starter, tier, allowFailure, enabled, maxParallel 제공
  - 생성 후 Suite Builder 로드, Run Launcher dropdown 선택 유지, 생성 시 maxParallel 실행 폼 반영
  - 남음: actual generated suite run smoke
- [x] Web authoring policy 공통화 + P0 hardening
  - create/write에서 root, extension, `.env`/`*.local.*`/known secret path, path traversal, overwrite 차단
  - Scenario/Suite `.yaml/.yml`, Fixture `.ps1/.sh`
  - `.exe/.msi/.zip`은 upload-only/read-only artifact로 유지
  - Windows reserved device name, trailing dot/space segment, control char, 텍스트 authoring 1 MiB 초과 차단
  - 남음: editable artifact authoring allowlist
- [x] Suite 저장 전 contract validation 강화
  - 빈 runs, 중복 run id, 잘못된 scenario path, 잘못된 `allowFailure/enabled/tier/maxParallel` shape를 저장 전 차단
  - API: `POST /api/validate/suite-content`
- [ ] Artifact Manager / text artifact authoring 구현
  - `validation/artifacts/**`와 `.web-artifacts/**` browse
  - repo/uploaded provenance, size, modified time, hash 표시
  - text artifact template 생성: PowerShell, shell, Python, C, JSON expected output, cmd/bat
- [ ] Catalog list metadata 강화: id/kind/tier/provider/template/last validation status
- [x] Results filtering/search 구현
- [x] Browser upload UX 보강: 단일 파일과 폴더 upload, `.web-artifacts` 저장, artifact path 자동 선택, 업로드 상태/진행률 카드, 좁은 panel responsive layout 검증
- [x] QGA `exec-status` 일시 실패 retry: Proxmox `agent/exec-status` 조회가 한 번 실패해도 command timeout 안에서는 재시도하고 timeout diagnostic에 마지막 오류를 남김
- [x] product-specific 제품 Release 폴더 Web 검증
  - 실행 묶음 smoke: job `cmognt5bg000usmmg6u6uvktu`, 실제 VM 실행 확인, path-profile `exec-status` transient failure 발견, appx-readonly allowed failure 표시 확인
  - retry 패치 후 path-profile 단일 시나리오 Web 재실행: job `cmogpdv9r002gsmmg4f7b062i`, run `20260427-133443-product-specific-agent-path-profile-windows`, `passed`
- [ ] Role split/OIDC 검토
- [ ] TRX aggregate report 연동

## 2026-04-22 product-specific Agent Step Contract 진행 결과

- [x] `product.steps[*].expectStdoutJson` scenario contract 추가
- [x] `expectStdoutJson`은 `captureStdoutJson: true`가 있을 때만 허용되도록 schema validation 추가
- [x] Product step stdout JSON의 필수 field/value mismatch를 `product_execution_failure`로 분류
- [x] Product step mismatch detail을 `product-steps.json`, report payload, JUnit detail에 기록
- [x] Product step 전체에서 선언된 secret 값은 step 경계를 넘어 stdout/stderr/stdoutJson에도 redaction 적용
- [x] Fake Agent CLI smoke에 `ok/step/registered` stdout JSON gate 추가
- [x] product-specific Agent CLI register/status/scan scenario에 실제 step gate 추가
- [x] product-specific register gate: tokenless register 이후 token/refresh/encryption key 저장 확인
- [x] product-specific status gate: remote token/asset registration 확인
- [x] product-specific scan gate: scan output file write 확인
- [x] 전체 scenario validation 통과
- [x] 로컬 테스트 결과: `143 passed`

## 2026-04-22 Metadata State Assertion 진행 결과

- [x] `commandResult.metadata.files` 기반 `file.exists`, `file.notExists` 구현
- [x] `commandResult.metadata.directories` 기반 `directory.exists` 구현
- [x] `commandResult.metadata.processes/services/packages` 기반 `process.exists`, `service.exists`, `package.exists` 구현
- [x] State assertion은 live guest query가 아니라 normalized output metadata를 평가하도록 설계 고정
- [x] Fixture state demo가 fixture-created file/directory state를 metadata로 보고하도록 갱신
- [x] Fixture state demo scenario에 `file.exists`, `directory.exists` assertion 추가
- [x] Scenario/assertion/docs 테스트 갱신
- [x] 로컬 테스트 결과: `143 passed`

## 2026-04-22 Console Unicode Detail 출력 개선 진행 결과

- [x] CLI error `details` 출력에서 JSON Unicode escape(`\uXXXX`) 대신 한글 원문을 표시
- [x] Console `detail()`이 dict/list를 공통 JSON formatter로 출력하도록 정리
- [x] `inspect-result --json`, normalize/analyze JSON 출력 파일, artifact/report JSON에서 `ensure_ascii=False` 적용
- [x] Proxmox 연결 실패 같은 localized Windows error가 `[WinError 10060] 연결하지 못했습니다` 형태로 표시되는지 샘플 검증
- [x] 로컬 테스트 결과: `143 passed`

## 2026-04-22 QGA UTF-8/CP949 Log Encoding Fix 진행 결과

- [x] QEMU Guest Agent exec stdout/stderr에서 UTF-8 bytes가 Latin-1 mojibake 문자열로 들어오는 경우 자동 복구
- [x] Korean Windows PowerShell stderr에서 CP949 bytes가 Latin-1 mojibake 문자열로 들어오는 경우 자동 복구
- [x] QEMU Guest Agent file-read content에서도 동일한 mojibake 복구 적용
- [x] 기존 UTF-8 BOM mojibake(`EF BB BF`가 Latin-1 text로 보이는 경우)와 실제 BOM `\ufeff` 제거 유지
- [x] 기존 product-specific full smoke run의 scan stderr log, product stderr log, product step JSON, normalized inventory를 복구
- [x] 기존 run artifact 전체에서 남은 UTF-8/CP949 mojibake marker 점검 및 4개 파일 추가 복구
- [x] `Microsoft Edge WebView2 런타임`, `스캔 진행`, `취약점 ScanAgent` 등 한글 표시 확인
- [x] `위치`, `문자`, `용어가 cmdlet...` 같은 PowerShell localized error 한글 표시 확인
- [x] 로컬 테스트 결과: `127 passed`

## 2026-04-22 Artifact Smoke Report Writer 진행 결과

- [x] Generic JUnit XML writer 추가: `src/oslab/reports/junit.py`
- [x] Static HTML report writer 추가: `src/oslab/reports/html.py`
- [x] `artifact-smoke` 결과를 `runs/artifact-smoke/<scenario-id>/reports/result.json`에 저장
- [x] Scenario `reports.formats`에 `junit`이 있으면 `reports/result.junit.xml` 저장
- [x] Scenario `reports.formats`에 `html`이 있으면 `reports/result.html` 저장
- [x] JUnit mapping: product/install non-zero는 `error`, assertion mismatch는 `failure`
- [x] Artifact report에 VM lifecycle, artifact upload, product command/steps, output paths, assertion summary, report paths 기록
- [x] CLI 최종 출력에 `localReport:<format>` 경로 표시
- [x] Report writer unit test 추가
- [x] Artifact smoke report consistency test 추가
- [x] 실제 Proxmox `fake.artifact-smoke.windows` 재실행 후 `reports/result.json` 생성 확인
- [x] 실행 후 VMID range cleanup 재확인: `usedInRange: <none>`
- [x] 로컬 테스트 결과: `106 passed`

## 2026-04-22 Full `oslab run` Artifact Layout 진행 결과

- [x] `oslab run --artifact-path ...`가 실제 Proxmox artifact validation orchestration을 실행
- [x] Artifact run output을 `runs/<run-id>/raw/actual-output.json`에 저장
- [x] Normalized inventory를 `runs/<run-id>/normalized/inventory.json`에 저장
- [x] 실시간 진행 로그를 `runs/<run-id>/logs/progress.log`에 append 저장
- [x] 구조화 진행 이벤트를 `runs/<run-id>/logs/progress.jsonl`에 append 저장
- [x] Product stdout/stderr log를 `runs/<run-id>/logs`에 저장
- [x] JSON/JUnit/HTML report를 `runs/<run-id>/reports`에 저장
- [x] `runs/<run-id>/run.json`에 report/log/raw/normalized path와 VM lifecycle 요약 기록
- [x] Product step secret env var를 VM 생성 전에 선검증
- [x] 실제 Proxmox `oslab run` + `fake.artifact-smoke.windows` 실행 통과
- [x] 실패 조합도 cleanup 확인: `product-specific.gold-lite.windows` + fake artifact는 product command 실패 후 VM destroy 완료
- [x] 실행 후 VMID range cleanup 재확인: `usedInRange: <none>`
- [x] 로컬 테스트 결과: `108 passed`

## 2026-04-22 Result Inspection 및 Product Step Failure 판정 진행 결과

- [x] `captureStdoutJson: true` product step에서 stdout JSON의 `ok:false`를 실패로 분류
- [x] 실제 product-specific Agent 최신 full smoke에서 register `ok:false`/`access_token_missing`을 `product_execution_failure`로 검출
- [x] 실제 실패 run id 기록 확인
- [x] 실패 run에서도 HTML/JUnit/JSON report와 `run.json`, `product-steps.json`, sidecar logs 생성 확인
- [x] 실패 run 이후 VMID range cleanup 재확인: `usedInRange: <none>`
- [x] `inspect-result` 기본 summary 출력 구현
- [x] `inspect-result --json` raw `run.json` 출력 유지
- [x] README에 full smoke 실행, 결과 확인, HTML report 열기, product step JSON 확인 방법 정리
- [x] 로컬 테스트 결과: `111 passed`

## 2026-04-22 Agent Tokenless Register Full Smoke 진행 결과

- [x] `agent-windows` CLI register에서 host-provided access token 필수 조건 제거
- [x] token이 없으면 asset/agent registration 후 `sabun + uuid` headless login으로 token 저장
- [x] 명시적으로 전달한 token이 만료된 경우만 `access_token_expired`로 실패
- [x] 기존 config의 만료 token은 무시하고 새 register/login 시도
- [x] Agent Release build 통과: `MSBuild.exe ProductAgent\\ProductAgent.csproj /p:Configuration=Release /p:Platform=AnyCPU`
- [x] 실제 full smoke 최신 성공 run id 기록 확인
- [x] register stdout JSON: `ok:true`, `accessTokenProvided:false`, `accessTokenSource:none`, `accessTokenPresent:true`, `refreshTokenPresent:true`, `encryptionKeyPresent:true`
- [x] status stdout JSON: `ok:true`, `tokenRemoteValid:true`, `remoteRegistered:true`
- [x] scan stdout JSON: `ok:true`, `outputWritten:true`
- [x] normalized inventory: 5 records
- [x] assertion: 1 total, 0 failed
- [x] report 생성: `result.json`, `result.junit.xml`, `result.html`
- [x] cleanup 재확인: `usedInRange: <none>`

## 2026-04-22 Scan Result Analysis 진행 결과

- [x] `canonical inventory` 전용 분석 모듈 추가: `src/oslab/analysis/inventory.py`
- [x] `oslab analyze-inventory` CLI 추가
- [x] `oslab run` report phase에서 `reports/inventory.analysis.json` 자동 생성
- [x] `inspect-result`가 `normalized/inventory.json`을 읽어 inventory analysis summary 출력
- [x] HTML report에 Inventory Analysis section 추가
- [x] Analysis output schema: `inventoryAnalysis`
- [x] 분석 항목: `recordCount`, `sourceCounts`, `publisherCounts`, `confidenceCounts`, `quality`, compact `records`
- [x] 품질 경고 항목: `missingVersion`, `missingPublisher`, `missingEvidence`, `missingEvidencePath`, `duplicateRecords`
- [x] 최신 실제 full smoke 분석 생성:
  - `records: 5`
  - `sources: Registry=5`
  - `publishers: <missing>=5`
  - `confidence: unknown=5`
  - `missingVersion: 0`
  - `missingPublisher: 5`
  - `missingEvidencePath: 5`
- [x] `/api/v1/policy` 세부 check 실패는 최초 `policy_id = -1` 정책 갱신 흐름에서는 product step hard failure로 보지 않음
- [x] Product step gate 기준은 `stdoutJson.ok == false`; 최신 실제 run의 register/status/scan 최상위 `ok:true` 확인
- [x] 분석 테스트 추가: `tests/test_analysis.py`
- [x] 로컬 테스트 결과: `114 passed`

## 2026-04-22 Full Run Preflight/Fixture/Scan Summary 진행 결과

- [x] `oslab run --artifact-path` 흐름에 Windows guest preflight 통합
- [x] Full run preflight 결과를 `run.json.details.preflight`에 기록
- [x] JUnit에 `preflight.<check-id>` testcase 기록
- [x] Scenario fixture apply를 full `oslab run` 흐름에 통합
- [x] Full run fixture expected output을 `runs/<run-id>/raw/fixture-<fixture-id>.expected-output.json`에 저장
- [x] Fixture 결과를 `run.json.details.fixtures`와 `reports/result.json.fixtures`에 기록
- [x] JUnit에 `fixture.<fixture-id>` testcase 기록
- [x] product-specific Agent scenario에서 기존 template clone의 `%LocalAppData%\ProductAgent\config.ini` 오염 여부 preflight 추가
- [x] Product step stdout JSON에서 scan 완료 정보를 `run.json.details.scan`에 요약
- [x] Scan 요약 항목: `ok`, `outputWritten`, `bytesWritten`, `scanId`, `uploadRequested`, `uploadSuccess`
- [x] `inspect-result`가 preflight/fixture/scan summary와 scan stdout JSON 핵심 값을 출력
- [x] README에 JUnit testcase mapping, full run output layout, scan summary 확인 방법 반영
- [x] 로컬 테스트 결과: `117 passed`

## 2026-04-22 Generic Demo Suite 진행 결과

- [x] `canonical.command` adapter 추가
- [x] Command result normalized schema 추가: `kind: commandResult`
- [x] `command.exitCode` assertion 구현
- [x] `command.stdoutContains` assertion 구현
- [x] `command.stderrContains` assertion 구현
- [x] Python hello world artifact 추가: `validation/artifacts/hello-python`
- [x] C hello world artifact 추가: `validation/artifacts/hello-c`
- [x] PowerShell system artifact 추가: `validation/artifacts/powershell-system`
- [x] Fixture state reader artifact 추가: `validation/artifacts/fixture-state-reader`
- [x] Demo agent CLI artifact 추가: `validation/artifacts/demo-agent-cli`
- [x] Python unittest artifact 추가: `validation/artifacts/python-unittest`
- [x] Python HTTP service artifact 추가: `validation/artifacts/python-http-service`
- [x] C unit test artifact 추가: `validation/artifacts/c-unit`
- [x] Python demo runtime pre-run fixture 추가: `validation/fixtures/windows/demo-python-runtime.ps1`
- [x] C demo compiler pre-run fixture 추가: `validation/fixtures/windows/demo-c-compiler.ps1`
- [x] Fixture state handoff fixture 추가: `validation/fixtures/windows/demo-state-file.ps1`
- [x] PowerShell system demo scenario 추가: `scenarios/windows/demo-powershell-system.example.yaml`
- [x] Python demo scenario 추가: `scenarios/windows/demo-python-hello.example.yaml`
- [x] C demo scenario 추가: `scenarios/windows/demo-c-hello.example.yaml`
- [x] Fixture state handoff demo scenario 추가: `scenarios/windows/demo-fixture-state.example.yaml`
- [x] Agent steps demo scenario 추가: `scenarios/windows/demo-agent-steps.example.yaml`
- [x] Python unittest demo scenario 추가: `scenarios/windows/demo-python-unittest.example.yaml`
- [x] Python HTTP service demo scenario 추가: `scenarios/windows/demo-python-http-service.example.yaml`
- [x] C unit test demo scenario 추가: `scenarios/windows/demo-c-unit.example.yaml`
- [x] Intentional assertion failure demo scenario 추가: `scenarios/windows/demo-intentional-assertion-failure.example.yaml`
- [x] Python/C demo scenario가 VM boot 후 fixture로 runtime/compiler 준비 또는 bootstrap 수행
- [x] Demo catalog 문서 추가: `docs/demos.md`, `docs/demos.ko.md`
- [x] Demo setup manifest를 `raw/fixture-*.expected-output.json`으로 수집
- [x] Command result는 full run에서 `runs/<run-id>/normalized/command-result.json`으로 저장
- [x] Command result run은 inventory analysis를 생성하지 않도록 분리
- [x] `inspect-result`에서 `normalized/command-result.json` 요약 출력
- [x] README에 product-specific 없는 범용 demo 실행/확인 흐름 추가
- [x] Platform plan에 `canonical.command` 모델 반영
- [x] Python demo fixture가 clean Windows clone에서 portable Python을 `C:\Oslab\tools\python`에 bootstrap하도록 개선
- [x] C demo fixture가 clean Windows clone에서 TinyCC를 `C:\Oslab\tools\tcc`에 bootstrap하도록 개선
- [x] 실제 lab Python demo 재실행: bootstrap 후 `hello from python` 통과 확인
- [x] 실제 lab C demo 재실행: bootstrap 후 `hello from c` 통과 확인
- [x] Fixture 실패 stdout/stderr를 `run.json`, `result.json`, JUnit detail, HTML report, `inspect-result`에 표시
- [x] 로컬 테스트 결과: `143 passed`

## 2026-04-22 Product Sidecar Log 저장 진행 결과

- [x] `artifact-smoke` 실행 결과 stdout/stderr를 sidecar log로 저장
- [x] 단일 product command log 저장: `runs/artifact-smoke/<scenario-id>/logs/product.stdout.log`, `product.stderr.log`
- [x] Product step log 저장: `product-step-<step-id>.stdout.log`, `product-step-<step-id>.stderr.log`
- [x] Windows newline 변환 없이 원문 log content 보존
- [x] Artifact JSON report에 sidecar log path 기록
- [x] CLI 최종 출력에 `localLog:<name>` 경로 표시
- [x] Product step log secret redaction 테스트 추가
- [x] 실제 Proxmox `fake.artifact-smoke.windows` 재실행 후 sidecar log 생성 확인
- [x] 실행 후 VMID range cleanup 재확인: `usedInRange: <none>`
- [x] 로컬 테스트 결과: `106 passed`

## 2026-04-22 Artifact Smoke Progress 출력 진행 결과

- [x] `artifact-smoke` runner에 `ProgressEvent` callback contract 추가
- [x] CLI에서 progress event를 `[OK]`, `[..]`, `[FAIL]`, `[WARN]` 형식으로 출력
- [x] Proxmox resource preflight, VMID 할당, clone 생성, VM start, running wait, QEMU Guest Agent wait 단계 출력
- [x] Artifact directory 준비, folder upload, archive 생성, archive upload, guest 압축 해제 단계 출력
- [x] QGA 대형 upload 중 10% 단위 transfer progress callback 추가
- [x] Product command 및 product step 실행 시작/완료/실패 출력
- [x] Output collect, JSON parse, normalize, assertion, raw output write 단계 출력
- [x] VM stop/destroy 및 best-effort cleanup 단계 출력
- [x] 실제 Proxmox `fake.artifact-smoke.windows` 재실행 통과
- [x] 실행 후 VMID range cleanup 재확인: `usedInRange: <none>`
- [x] 로컬 테스트 결과: `106 passed`

## 2026-04-21 중간 재점검 결과

- [x] `uv run pytest`: `105 passed`
- [x] `product-specific.gold-lite.windows` scenario validation 통과
- [x] `fake.artifact-smoke.windows` scenario validation 통과
- [x] `fake.installer-smoke.windows` scenario validation 통과
- [x] `fake.agent-cli-smoke.windows` scenario validation 통과
- [x] `generic.linux.smoke` scenario validation 통과
- [x] Proxmox resource preflight 재확인 통과
- [x] Template VMID `9101`, template name `windows11-template-qga-9101`, clone range `9102-9199` 확인
- [x] VMID range 안에 남은 clone 없음: `usedInRange: <none>`
- [x] 기존 `runs/artifact-smoke/fake.artifact-smoke.windows/scan-result.json`에 `assert-result` 재평가 통과
- [x] 실제 Proxmox `fake.agent-cli-smoke.windows` product step smoke 통과
- [x] Product step smoke 이후 cleanup 재확인: `usedInRange: <none>`
- [x] `runs/artifact-smoke/fake.agent-cli-smoke.windows/scan-result.json`에 `assert-result` 재평가 통과
- [x] 실제 Proxmox `product-specific.agent-status.windows` status-only smoke 통과
- [x] Real Agent status smoke 이후 cleanup 재확인: `usedInRange: <none>`
- [x] `runs/artifact-smoke/product-specific.agent-status.windows/scan-result.json`에 `assert-result` 재평가 통과
- [x] `docs/oslab-platform-plan.md`의 오래된 VMID/CLI 예시 정리
- [x] `docs/architecture.md`가 legacy product-specific 전용 문서임을 명시

## 2026-04-21 Plugin Normalize 진행 결과

- [x] Core generic plugin loader 추가
- [x] `canonical.inventory` passthrough adapter 추가
- [x] `plugins/product-specific` Python plugin 추가
- [x] `product-specific.inventory` raw-to-canonical normalize 구현
- [x] product-specific common raw field mapping 구현: name, version, publisher, source, evidence path
- [x] Source normalization 구현: Registry, PE, StartMenu, Appx, MSI 등
- [x] `oslab normalize-output` CLI 추가
- [x] `oslab assert-result`가 scenario adapter normalize 후 assertion 평가하도록 변경
- [x] `artifact-smoke`가 raw output과 normalized inventory를 모두 저장하도록 변경
- [x] Fake artifact scenario adapter를 `canonical.inventory`로 변경
- [x] `validation/raw/product-specific/sample-output.json` sample 추가
- [x] 실제 Proxmox artifact smoke 재검증 통과
- [x] Cleanup 재확인: `usedInRange: <none>`

## 2026-04-21 Installer 및 Secret Redaction 진행 결과

- [x] Command template secret token render/redaction 구현
- [x] CLI 출력에서 `CommandSpec.safe_rendered` 사용
- [x] `artifact-smoke`에서 `installer` artifact type 지원
- [x] Installer artifact file upload 구현
- [x] Installer `installCommand` 실행 구현
- [x] `{InstallerPath}` token 지원
- [x] Fake installer scenario 추가: `scenarios/windows/fake-installer-smoke.example.yaml`
- [x] Fake installer artifact 추가: `validation/artifacts/fake-installer.ps1`
- [x] 실제 Proxmox fake installer smoke 통과
- [x] Cleanup 재확인: `usedInRange: <none>`
- [x] 로컬 테스트 결과: `105 passed`

## 2026-04-21 Product Step 진행 결과

- [x] Top-level `product.steps` scenario contract 추가
- [x] `register -> status -> scan` 같은 순차 product step 실행 구현
- [x] Step별 `command.shell/template` 검증
- [x] Step별 `secretTokens.<Token>.env` 검증
- [x] Host env에서 product secret token resolve
- [x] Command render 시 실제 secret 전달, console/report용 `<redacted>` command 보관
- [x] `captureStdoutJson: true` step stdout single JSON parse
- [x] `stdoutJson.ok == false`를 product step failure로 분류
- [x] Step 결과를 `runs/artifact-smoke/<scenario-id>/product-steps.json`에 저장
- [x] `product-specific-agent-cli-failure` artifact 감지 후 product execution failure로 분류하는 기반 구현
- [x] `{AssetName}` token 구현: `OSLAB_ASSET_NAME` 우선, 없으면 `oslab-{ScenarioId}-{VmId}`
- [x] Fake Agent CLI installer 추가: `validation/artifacts/fake-agent-installer.ps1`
- [x] Fake Agent CLI scenario 추가: `scenarios/windows/fake-agent-cli-smoke.example.yaml`
- [x] 실제 product-specific Agent CLI scenario 초안 추가: `scenarios/windows/product-specific/product-specific-agent-cli.example.yaml`
- [x] 실제 product-specific Agent status-only scenario 추가: `scenarios/windows/product-specific/product-specific-agent-status.example.yaml`
- [x] 실제 Agent build output의 `logs/**`, `*.pdb`, `*.xml` exclude 설정
- [x] product-specific Agent CLI용 env key 안내 추가: `OSLAB_PRODUCT_SERVER_URL`, `OSLAB_PRODUCT_SABUN`
- [x] 실제 product-specific Agent CLI scenario report format을 `junit`, `json`, `html`로 설정
- [x] 실제 product-specific Agent CLI scenario에서 host-provided `OSLAB_PRODUCT_TOKEN` 요구 제거
- [x] 실제 Agent folder artifact를 archive transfer로 VM에 업로드
- [x] 실제 `ProductAgent.exe cli_mode status --json` 경로를 Proxmox clone에서 실행 검증
- [x] 실제 `ProductAgent.exe cli_mode register/status/scan` full smoke 시도
- [x] 실제 full smoke 실패 run id 기록 확인
- [x] 실제 full smoke 실패 결과: register step stdout JSON `ok:false`, `errorCode: access_token_missing`
- [x] 실제 full smoke 실패 판정: `status: failed`, `failureClass: product_execution_failure`
- [x] 실제 full smoke 실패 report 생성: `result.json`, `result.junit.xml`, `result.html`
- [x] 실제 full smoke cleanup 재확인: `usedInRange: <none>`
- [x] Agent Release artifact가 host token 없이 server URL/sabun 기반 register/login 후 config.ini token 저장을 수행하도록 갱신
- [x] 갱신된 Agent Release artifact로 full smoke 재실행 및 register/status/scan 모두 `stdoutJson.ok == true` 확인
- [x] 실제 full smoke 성공 run id 기록 확인
- [x] 실제 Proxmox fake Agent CLI product step smoke 통과
- [x] Cleanup 재확인: `usedInRange: <none>`
- [x] 최신 로컬 테스트 결과: `155 passed`

## 구현 완료

### 프로젝트 골격

- [x] `pyproject.toml` 기반 `uv` workflow
- [x] `oslab` console entrypoint
- [x] `src/oslab` 아래 package layout
- [x] Pytest 테스트 suite
- [x] `.gitignore`에 local run, env file, virtualenv, cache, Python metadata 제외 규칙 추가

### 문서

- [x] `docs/oslab-platform-plan.md`
- [x] `docs/oslab-expert-review.md`
- [x] `docs/proxmox-connection.md`
- [x] `docs/devs/oslab-implementation-checklist.md`
- [x] `README.md`에 `oslab` 사용 흐름 반영
- [x] 기존 product-specific 전용 architecture 문서는 `docs/architecture.md`에 legacy context로 유지

### Scenario 및 Config

- [x] Windows product-specific smoke scenario
- [x] Linux generic smoke example scenario
- [x] Local config example
- [x] Git에 올리지 않는 local config 흐름: `config/oslab.local.yaml`
- [x] Git에 올리지 않는 local env 흐름: `config/oslab.local.env`
- [x] Local env example 추가: `config/oslab.local.example.env`
- [x] YAML top-level 구조 검증
- [x] Scenario schema version 검증
- [x] Provider, guest, artifact, fixture, assertion, report, cleanup 검증
- [x] Windows scenario의 현재 template VMID를 `9101`로 고정
- [x] Windows scenario의 현재 template name을 `windows11-template-qga-9101`로 고정
- [x] Windows scenario의 현재 clone range를 `9102-9199`로 고정
- [x] QEMU Guest Agent가 설치된 Windows template을 기준으로 scenario 갱신
- [x] product-specific 없는 generic PowerShell/Python/C/fixture-state/agent-steps demo scenarios
- [x] Report/JUnit 학습용 intentional assertion failure demo scenario

### Console 및 Secret 처리

- [x] `[OK]`, `[WARN]`, `[FAIL]`, `[..]` 기반 구조화 console output
- [x] `artifact-smoke` 장기 실행 단계별 progress console output
- [x] Token id redaction
- [x] Token secret 미출력
- [x] 구조화된 error detail 출력
- [x] Local env file parser
- [x] PowerShell에서 생성된 env file의 UTF-8 BOM 처리
- [x] Env file 작성 형식 안내
- [x] 기존 VM 대상으로 QEMU Guest Agent command를 실행하는 `oslab qga-exec`
- [x] 기존 VM 대상으로 작은 파일을 업로드하는 `oslab qga-upload`
- [x] 기존 VM에서 텍스트 파일을 다운로드하는 `oslab qga-download`
- [x] Windows guest readiness를 검증하는 `oslab guest-preflight`
- [x] Scenario fixture를 실행하고 expected output을 수집하는 `oslab fixture-smoke`
- [x] Folder artifact를 실행하고 output JSON을 수집하는 `oslab artifact-smoke`
- [x] 수집된 JSON에 scenario assertion을 로컬에서 평가하는 `oslab assert-result`

### Proxmox API 기반

- [x] Proxmox API URL normalization
  - `https://host:8006` 입력 허용
  - 내부적으로 `https://host:8006/api2/json` 형태로 정규화
- [x] API token authentication header
- [x] Lab/self-signed certificate 환경을 위한 TLS verification toggle
- [x] Timeout config
- [x] `GET /version`
- [x] `GET /nodes`
- [x] `GET /cluster/resources?type=vm`
- [x] `GET /nodes/<node>/qemu/<vmid>/config`
- [x] `POST /nodes/<node>/qemu/<templateVmId>/clone`
- [x] `POST /nodes/<node>/qemu/<vmid>/status/start`
- [x] `POST /nodes/<node>/qemu/<vmid>/status/stop`
- [x] `DELETE /nodes/<node>/qemu/<vmid>?purge=1`
- [x] `POST /nodes/<node>/qemu/<vmid>/agent/exec`
- [x] `GET /nodes/<node>/qemu/<vmid>/agent/exec-status`
- [x] `POST /nodes/<node>/qemu/<vmid>/agent/file-write`
- [x] `GET /nodes/<node>/qemu/<vmid>/agent/file-read`
- [x] Proxmox async task polling

### Provider 및 VMID

- [x] Provider contracts
- [x] `TemplateRef`
- [x] `VmSpec`
- [x] `VmRef`
- [x] `VmStatus`
- [x] `GuestInfo`
- [x] Proxmox provider implementation
- [x] VMID range parser
- [x] Proxmox resource에서 사용 중인 VMID 추출
- [x] Local lock-file 기반 VMID reservation
- [x] 자동 VMID 추천

### Proxmox 읽기 전용 Preflight

- [x] `oslab preflight --provider-config-check`
- [x] `oslab preflight --provider-connectivity-check`
- [x] `oslab preflight --provider-resource-check`
- [x] Node 존재 여부 확인
- [x] Template VMID 존재 여부 확인
- [x] Template flag 확인
- [x] VM resource count 출력
- [x] VMID range 사용 현황 출력
- [x] 권장 VMID 출력

실제 실행 명령:

```powershell
uv run oslab preflight `
  --scenario scenarios/windows/product-specific/product-specific-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --provider-resource-check
```

최근 실제 출력 요약:

```text
[OK] Proxmox API connectivity
     version: 9.1.1
     release: 9.1
[OK] Configured Proxmox node exists
     configuredNode: <lab-node>
     vmResourceCount: 111
[OK] Template VMID exists
     templateVmId: 9101
     templateName: windows11-template-qga-9101
[OK] Template flag confirmed
[OK] VMID range inspected
     range: 9102-9199
     usedInRange: <none>
     recommendedVmId: 9102
```

### Clone Smoke

- [x] `oslab clone-smoke`
- [x] Clone 전 resource preflight
- [x] 자동 VMID reservation
- [x] Clone name generation
- [x] Template 기반 clone 생성
- [x] Clone status 조회
- [x] 기본 cleanup
- [x] `--keep-vm`
- [x] `--full-clone`
- [x] Create/destroy 및 keep behavior 테스트
- [x] 실제 Proxmox clone smoke 통과

실제 실행 명령:

```powershell
uv run oslab clone-smoke `
  --scenario scenarios/windows/product-specific/product-specific-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env
```

최근 실제 출력 요약:

```text
[OK] Clone smoke completed
     cloneVmId: 9102
     cloneName: oslab-product-specific-gold-lite-windows-9102
     cloneStatus: stopped
     destroyed: true
     kept: false
```

### Boot Smoke

- [x] `oslab boot-smoke`
- [x] Clone 생성
- [x] VM start
- [x] Running status wait
- [x] QEMU Guest Agent network info wait
- [x] 기본 stop/destroy cleanup
- [x] 실패 시 best-effort cleanup
- [x] `--keep-vm`
- [x] Boot timeout option
- [x] Guest timeout option
- [x] Poll interval option
- [x] Start/guest/cleanup 및 keep behavior 테스트
- [x] 실제 Proxmox boot smoke가 QEMU Guest Agent 확인 및 cleanup까지 통과

실제 실행 명령:

```powershell
uv run oslab boot-smoke `
  --scenario scenarios/windows/product-specific/product-specific-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --boot-timeout-seconds 300 `
  --guest-timeout-seconds 300 `
  --poll-interval-seconds 5
```

이전 실제 실패:

```text
[FAIL] Timed out waiting for QEMU Guest Agent on VM 9101
details:
  status: 500
  body: {"message":"QEMU guest agent is not running\n","data":null}
```

실패 후 cleanup 검증 결과:

```text
usedInRange: <none>
recommendedVmId: 9101
```

새 template `9101` 전환 후 실제 성공:

```text
[OK] Boot smoke completed
     cloneVmId: 9102
     cloneName: oslab-product-specific-gold-lite-windows-9102
     cloneStatus: running
     guestInfo: available
     started: true
     destroyed: true
     kept: false
```

## 해결된 Blocker

### Windows Template의 QEMU Guest Agent

- [x] Windows template에서 clone boot 이후 QEMU Guest Agent가 실행되도록 수정

확인된 증거:

- Proxmox VM config에는 `agent: 1`이 설정되어 있음
- VMID `9101`의 Proxmox config는 `template: 1`, `agent: 1`, `status: stopped`
- `oslab qga-exec`로 `cmd.exe /c echo oslab-qga-check` 실행 성공
- Clone/start/cleanup 경로는 정상 동작

원인이었던 항목:

- Windows 내부에 QEMU Guest Agent service가 설치되어 있지 않음
- `9100` template 생성 시 QEMU Guest Agent 설치가 누락됨

남은 주의점:

- 기존 `9100` template은 legacy template으로 남아 있음
- 현재 scenario는 QGA가 포함된 `9101` template을 사용함
- 새 clone은 `9102-9199` range에서 생성해야 함

향후 template 회귀가 의심될 때의 debug 명령:

```powershell
uv run oslab boot-smoke `
  --scenario scenarios/windows/product-specific/product-specific-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --keep-vm `
  --guest-timeout-seconds 30
```

이후 Proxmox console에서 유지된 clone에 접속해 확인:

```powershell
Get-Service | Where-Object { $_.Name -match "qemu|guest" -or $_.DisplayName -match "qemu|guest" }
```

Service가 존재하면:

```powershell
Start-Service QEMU-GA
Set-Service QEMU-GA -StartupType Automatic
```

Service가 없다면 VirtIO tools ISO에서 QEMU Guest Agent를 설치한 뒤 template을 다시 만들어야 합니다.

## 미구현 항목

### Guest Channel 구현

- [x] QEMU Guest Agent command execution wrapper
- [x] QEMU Guest Agent file upload/download
- [x] QEMU Guest Agent stdout/stderr/exit code capture
- [ ] WinRM probe
- [ ] WinRM command execution
- [ ] WinRM file transfer
- [ ] Linux용 SSH probe
- [ ] Linux용 SSH command execution
- [ ] Linux용 SSH upload/download
- [ ] 실제 channel 구현과 연결된 automatic guest channel selection

### Windows Guest 내부 Preflight

- [x] `$PSVersionTable` 실행
- [x] `Get-ExecutionPolicy -List` 확인
- [x] Admin context 확인
- [x] `C:\Oslab` test file 생성/삭제
- [ ] Known app baseline 확인
- [ ] Fallback이 활성화된 경우 WinRM readiness 확인
- [x] QEMU Guest Agent command execution readiness 확인

### Fixture 및 Artifact 실행

- [x] `validation/fixtures/windows/product-specific/gold-lite.ps1` upload
- [x] Guest 안에서 fixture script 실행
- [x] `C:\Oslab\expected_inventory.json` collect
- [x] Folder artifact upload
- [x] Folder artifact exclude pattern 지원: `artifact.exclude`
- [x] Folder artifact archive transfer 지원: `artifact.transfer: archive`
- [x] 대형 QGA upload chunking 구현
- [x] 대형 QGA upload progress callback 구현
- [ ] 빠른 artifact 전송 mode 설계/구현
  - 현재 QGA `file-write` 기반 대형 업로드는 base64/chunk/API round-trip 비용이 커서 제품 `bin/Release` artifact suite 실행의 병목이 됨
  - 최근 run `20260427-160236-product-specific-windows-v1` 기준 `16,575,826` bytes archive upload가 시나리오별 약 `450-478s`, guest `Expand-Archive`는 약 `6s`
  - 우선 검토안: dashboard/API 또는 임시 host HTTP server가 archive를 제공하고, guest가 PowerShell/BITS로 직접 다운로드하는 `http-pull` transfer mode
  - fallback: guest가 host URL에 접근하지 못하면 기존 QGA upload를 유지
- [x] QGA file-read 실패 시 PowerShell base64 fallback download 구현
- [x] Installer artifact upload
- [x] Installer install command execution
- [x] Artifact command template 실행
- [x] Remote execution용 command token render
- [x] Remote execution용 command token secret redaction
- [x] Scanner output JSON collect
- [x] Scanner output JSON에 대한 assertion 평가
- [x] Scanner output JSON normalize
- [x] Generic command result JSON collect
- [x] Generic command result normalize
- [ ] Log collect
- [x] Product command sequence: register/status/scan
- [x] Artifact smoke lifecycle/progress 단계별 console 출력
- [x] Product step secret delivery: scenario/env 기반 redacted CLI arg token
- [x] Product stdout final JSON parse
- [x] Product stderr/progress 기본 capture: `product-steps.json`
- [x] Product stdout/stderr sidecar log artifact 저장
- [x] CLI failure artifact detection
- [ ] 선택 경로: guest env injection 기반 secret delivery
- [ ] Provider/guest channel diagnostic log artifact 저장

### product-specific Plugin

- [x] `plugins/product-specific` package
- [x] Raw product-specific JSON parser
- [x] Canonical inventory model writer
- [x] Evidence normalization
- [x] Source normalization
- [x] Version/publisher/path mapping
- [x] Plugin metadata
- [x] 실제 product-specific scan output으로 adapter 호환성 검증: 이전 scan output에서 4 records normalize
- [ ] product-specific output schema가 확정되면 strict mode 추가

### product-specific Agent CLI 연동

- [x] Agent 쪽 CLI 자동화 문서 확인: `agent-windows/docs/13-agent-cli-automation.md`
- [x] CLI mode 요구사항을 `docs/oslab-platform-plan.md`에 반영
- [x] `register --json` 실행 step 지원
- [x] `status --remote --json` 실행 step 지원
- [x] `scan --wait --output --json` 실행 step 지원
- [x] `--access-token`용 command template secret render/redaction 기반 구현
- [x] Scenario/env에서 secret 값을 resolve하는 product step 구현
- [x] 실제 product-specific Agent full smoke scenario는 host token 없이 sabun 기반 register/login 흐름으로 변경
- [x] Product step stdout JSON의 `ok:false`를 실패로 분류
- [ ] 선택 경로: `--access-token-env`용 guest env injection 구현
- [x] `OSLAB_ASSET_NAME` 또는 `oslab-{RunId}-{VmId}` asset name token 구현
- [x] `requireAdministrator` manifest가 QGA 실행 컨텍스트에서 status-only smoke 기준 문제 없는지 검증
- [x] 실제 `ProductAgent.exe cli_mode status --json`를 Proxmox clone에서 실행 검증
- [ ] `requireAdministrator` manifest가 WinRM 실행 컨텍스트에서 문제 없는지 검증
- [x] 실제 `ProductAgent.exe cli_mode register/status/scan`를 Proxmox clone에서 실행하고 register 계약 실패를 검출
- [x] Agent 수정 후 실제 `ProductAgent.exe cli_mode register/status/scan` 성공 경로 검증
- [x] CLI stdout single JSON artifact 저장: `product-steps.json`
- [x] CLI stderr progress/debug 기본 저장: `product-steps.json`
- [x] `product-specific-agent-cli-failure` artifact를 `product_execution_failure`로 분류
- [x] CLI stdout/stderr sidecar log 저장
- [x] Windows template에서 기존 `%LocalAppData%\ProductAgent\config.ini` 오염 여부 preflight

### product-specific 설치 환경 Profile Matrix

목표: 실제 `ProductAgent.exe cli_mode scan`이 다양한 OS template과 다양한 설치 상태에서 software inventory를 정확히 수집하는지 검증합니다. OS version/language/patch 차이는 template axis로 두고, 설치 상태 차이는 fixture/profile axis로 둡니다.

- [x] 이전 fixture/profile 기획 채팅 이관
  - Reference chat id: `019da8e7-0c01-7c83-b5f8-b68e5aa72131`
  - 내용: product-specific fixture 류 준비, 다양한 설치 환경별 테스트 범위 논의
  - 이관 문서: `docs/product-specific_docs/agent-windows-analysis-and-validation-notes.md`
  - 반영 내용: product gap, 성능 리스크, gold-lite 우선 전략, profile script 수동/spec화, clone/provision/run 자동화, TRX/JSON/HTML 리포트 판단
- [x] product-specific 전용 scenario/fixture OS-first 하위 디렉터리 분리
  - Scenario root: `scenarios/windows/product-specific/`
  - Fixture root: `validation/fixtures/windows/product-specific/`
- [x] Clean baseline profile 구현
  - Scenario: `scenarios/windows/product-specific/product-specific-agent-clean-baseline.example.yaml`
  - Fixture: 없음
  - 검증: clean Windows template scan output과 Registry source 존재 확인
- [x] Appx read-only gap probe 구현
  - Scenario: `scenarios/windows/product-specific/product-specific-agent-appx-readonly.example.yaml`
  - Fixture: `validation/fixtures/windows/product-specific/product-specific-appx-readonly.ps1`
  - 검증: inbox Appx 후보 manifest를 기록하고 normalized inventory의 `Appx` source 존재 여부 확인
  - 실제 결과: 후보 3개 기록, normalized inventory는 Registry-only 4 records, `Appx` source 미검출
  - 주의: Agent Appx/MSIX 구현 전에는 실패할 수 있으므로 CI 기본 pass set에 넣지 않음
- [x] Registry x64/WOW6432/Unicode path synthetic profile 구현
  - Scenario: `scenarios/windows/product-specific/product-specific-agent-os-profile.example.yaml`
  - Fixture: `validation/fixtures/windows/product-specific/product-specific-os-profile.ps1`
  - 검증: synthetic uninstall registry entries가 scan inventory로 검출되고 evidence path가 보존됨
- [x] Program Files/x86/space/unicode/deep path synthetic profile 구현
  - Scenario: `scenarios/windows/product-specific/product-specific-agent-path-profile.example.yaml`
  - Fixture: `validation/fixtures/windows/product-specific/product-specific-path-profile.ps1`
  - 검증: 설치 경로 형태가 달라도 scan inventory와 evidence가 보존됨
- [ ] EXE/MSI real install profile 구현
  - 예정 Scenario: `scenarios/windows/product-specific/product-specific-agent-exe-msi-profile.example.yaml`
  - 예정 Fixture: `validation/fixtures/windows/product-specific/product-specific-exe-msi-profile.ps1`
  - 검증: silent EXE/MSI 설치 후 uninstall key, MSI metadata, version/publisher/install path evidence 검출
- [ ] winget real install profile 구현
  - 예정 Scenario: `scenarios/windows/product-specific/product-specific-agent-winget-profile.example.yaml`
  - 예정 Fixture: `validation/fixtures/windows/product-specific/product-specific-winget-profile.ps1`
  - 검증: `winget install`로 설치한 package의 registry/file evidence와 source classification 검출
  - 주의: public network 의존을 줄이려면 internal source/cache 또는 package pinning 필요
- [ ] Chocolatey real install profile 구현
  - 예정 Scenario: `scenarios/windows/product-specific/product-specific-agent-chocolatey-profile.example.yaml`
  - 예정 Fixture: `validation/fixtures/windows/product-specific/product-specific-chocolatey-profile.ps1`
  - 검증: `C:\ProgramData\chocolatey\lib` metadata와 실제 installed app footprint 검출
  - 주의: choco source/cache 전략 필요
- [ ] Appx/MSIX profile 구현
  - 예정 Scenario: `scenarios/windows/product-specific/product-specific-agent-appx-profile.example.yaml`
  - 예정 Fixture: `validation/fixtures/windows/product-specific/product-specific-appx-profile.ps1`
  - 검증: Appx package identity, version, publisher, install path, user/system package visibility 검출
  - 주의: real install은 signed package 또는 trusted test certificate 필요; 초기에는 inbox Appx read-only 검증도 가능
- [ ] Mixed endpoint profile 구현
  - 예정 Scenario: `scenarios/windows/product-specific/product-specific-agent-mixed-profile.example.yaml`
  - 예정 Fixture: 위 profile fixture 조합 또는 전용 mixed fixture
  - 검증: 여러 설치 방식이 섞인 현실적인 endpoint 상태에서도 scan 결과가 누락/중복 없이 유지됨
- [ ] Previous Agent install/config state profile 구현
  - 예정 Scenario: `scenarios/windows/product-specific/product-specific-agent-previous-state-profile.example.yaml`
  - 예정 Fixture: `validation/fixtures/windows/product-specific/product-specific-previous-state-profile.ps1`
  - 검증: 기존 config/token/install state가 있을 때 re-register, upgrade, stale config 처리 확인
- [x] Scan profile suite runner MVP 구현
  - Suite: `validation/suites/product-specific-windows-v1.example.yaml`
  - CLI: `uv run oslab suite-run --suite ...`
  - 검증: 여러 profile scenario를 순차 실행하고 aggregate `suite.json` 생성
- [x] Suite runner 병렬 실행 옵션 구현
  - CLI: `--max-parallel <n>`
  - 기본값: `1`
  - 주의: VMID range와 Proxmox host resource 여유 필요
- [x] Suite 병렬 console 가독성 개선
  - Progress message 예: `[clean-baseline] VM is running`
  - Progress detail: `suiteEntry: clean-baseline`
- [x] Suite aggregate HTML/JUnit report 구현
- [ ] Suite aggregate TRX report 구현

### Assertion Engine

- [x] Assertion result model
- [x] Assertion summary model
- [x] `inventory.contains`
- [x] `inventory.sourcePresent`
- [x] `inventory.sourceAbsent`
- [x] `inventory.evidencePresent`
- [x] `command.exitCode`
- [x] `command.stdoutContains`
- [x] `command.stderrContains`
- [x] `artifact-smoke` 결과에 assertion 평가 연결
- [x] `assert-result` local CLI
- [x] `file.exists`
- [x] `file.notExists`
- [x] `directory.exists`
- [x] `service.exists`
- [x] `process.exists`
- [x] `package.exists`
- [x] `metadata.files/directories/processes/services/packages` 기반 state assertion contract 문서화
- [ ] Severity/gating rules

### Reports

- [x] Skeleton JSON run result
- [x] Artifact smoke JSON validation report
- [x] JUnit XML writer
- [x] HTML report writer
- [x] `inspect-result` 기본 summary 출력
- [x] `inspect-result` inventory analysis summary 출력
- [x] `inspect-result --json` raw `run.json` 출력
- [x] `analyze-inventory` local CLI
- [x] `reports/inventory.analysis.json` 생성
- [x] Artifact smoke report consistency tests
- [x] Full artifact `run.json`에 raw/normalized/result path 첨부
- [x] Full artifact `run.json`에 preflight/fixture/product step/scan summary 첨부
- [x] Product stdout/stderr log를 `runs/<run-id>/logs` 아래 보존
- [x] Provider/VM/guest/artifact/product 단계 progress event를 `runs/<run-id>/logs/progress.log`와 `progress.jsonl`에 실시간 저장
- [ ] Provider/guest diagnostic log를 `runs/<run-id>/logs` 아래 보존

### Full Validation Run

- [x] `oslab run --artifact-path`를 실제 artifact orchestration으로 교체
- [x] Resource preflight
- [x] Clone
- [x] Start
- [ ] Guest channel select
- [x] Guest preflight를 `oslab run` 흐름에 통합
- [x] Fixture apply를 `oslab run` 흐름에 통합
- [x] Artifact install/copy
- [x] Product register/status/scan execution
- [x] Output collection
- [x] Plugin normalize
- [x] Assertion evaluate
- [x] Inventory analysis artifact write
- [x] Report write
- [x] Cleanup
- [ ] `--keep-vm-on-failure`
- [ ] Stale VM metadata

### Cleanup 및 Recovery

- [ ] `oslab cleanup-stale`
- [x] Web/API Range 안의 stopped/stale `oslab-*` VM 후보 제거
- [x] Web/API Cleanup dry-run mode
- [x] Web/API Cleanup confirmation token
- [ ] Stale VM report
- [ ] CLI Cleanup dry-run mode
- [ ] CLI Cleanup confirmation/force flag

### CI Integration

- [ ] GitLab CI example
- [ ] GitHub Actions example
- [ ] JUnit artifact upload
- [ ] HTML artifact upload
- [ ] `runs/**` artifact upload
- [ ] CI concurrency/resource group guidance
- [ ] Secret configuration guide

### Linux 구현

- [x] Linux scenario example
- [x] Linux guest channel selection design
- [ ] Linux SSH implementation
- [ ] Linux shell fixture execution
- [ ] Linux file/package/process assertions
- [ ] Linux real Proxmox template
- [ ] Linux boot smoke
- [ ] Linux guest preflight

### Security 및 운영

- [x] Token secret redaction
- [x] Git에 올리지 않는 env file 흐름
- [ ] 초기에 노출된 테스트 token rotation
- [ ] Least-privilege Proxmox token role 문서화
- [ ] Validation VMID range permission boundary 문서화
- [ ] Production cluster에 broad permission을 주지 않는 운영 가이드
- [ ] Commit 전 secret scanning check

## 현재 실제 Lab 설정

Local-only files:

- `config/oslab.local.yaml`
- `config/oslab.local.env`

현재 Proxmox 값:

```text
apiUrl: https://proxmox.example.local:8006/api2/json
node: <lab-node>
templateVmId: 9101
templateName: windows11-template-qga-9101
cloneRange: 9102-9199
```

위 local files는 ignore 대상이며 commit하면 안 됩니다.

## 안전한 명령

읽기 전용:

```powershell
uv run oslab validate-scenario --scenario scenarios/windows/product-specific/product-specific-gold-lite.yaml

uv run oslab preflight `
  --scenario scenarios/windows/product-specific/product-specific-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --provider-resource-check
```

Clone을 만들고 삭제:

```powershell
uv run oslab clone-smoke `
  --scenario scenarios/windows/product-specific/product-specific-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env
```

Clone을 만들고 start/stop/delete:

```powershell
uv run oslab boot-smoke `
  --scenario scenarios/windows/product-specific/product-specific-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env
```

Clone을 만들고 Windows guest readiness 확인 후 삭제:

```powershell
uv run oslab guest-preflight `
  --scenario scenarios/windows/product-specific/product-specific-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env
```

Clone을 만들고 fixture 실행 및 expected output 수집 후 삭제:

```powershell
uv run oslab fixture-smoke `
  --scenario scenarios/windows/product-specific/product-specific-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env
```

Clone을 만들고 fake folder artifact 실행 및 output JSON 수집 후 삭제:

```powershell
uv run oslab artifact-smoke `
  --scenario scenarios/windows/fake-artifact-smoke.example.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/fake-scanner
```

Clone을 만들고 fake installer upload/install/product 실행 및 output JSON 수집 후 삭제:

```powershell
uv run oslab artifact-smoke `
  --scenario scenarios/windows/fake-installer-smoke.example.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/fake-installer.ps1
```

Clone을 만들고 fake Agent CLI install/register/status/scan 실행 및 output JSON 수집 후 삭제:

```powershell
$env:OSLAB_FAKE_PRODUCT_TOKEN="fake-token-for-oslab"
uv run oslab artifact-smoke `
  --scenario scenarios/windows/fake-agent-cli-smoke.example.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/fake-agent-installer.ps1
```

product-specific raw sample을 canonical inventory로 normalize:

```powershell
uv run oslab normalize-output `
  --scenario scenarios/windows/product-specific/product-specific-gold-lite.yaml `
  --input-json validation/raw/product-specific/sample-output.json `
  --output-json runs\normalize-smoke\product-specific.inventory.json
```

Canonical inventory를 분석:

```powershell
uv run oslab analyze-inventory `
  --inventory-json runs\<run-id>\normalized\inventory.json `
  --output-json runs\<run-id>\reports\inventory.analysis.json
```

수집된 JSON을 VM 생성 없이 assertion만 재평가:

```powershell
uv run oslab assert-result `
  --scenario scenarios/windows/fake-artifact-smoke.example.yaml `
  --actual-json runs\artifact-smoke\fake.artifact-smoke.windows\scan-result.json
```

Debug mode: VM이 남을 수 있음

```powershell
uv run oslab boot-smoke `
  --scenario scenarios/windows/product-specific/product-specific-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --keep-vm `
  --guest-timeout-seconds 30
```

유지된 VM에서 QEMU Guest Agent command 실행:

```powershell
uv run oslab qga-exec `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --vm-id 9102 `
  --timeout-seconds 30 `
  -- powershell.exe -NoProfile -Command whoami
```

유지된 VM으로 작은 파일 upload:

```powershell
uv run oslab qga-upload `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --vm-id 9102 `
  --local-path README.md `
  --guest-path C:\Oslab\README.uploaded.md
```

유지된 VM에서 텍스트 파일 download:

```powershell
uv run oslab qga-download `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --vm-id 9102 `
  --guest-path C:\Oslab\README.uploaded.md `
  --local-path runs\qga-download-readme.md
```

## TODO

1. product-specific EXE/MSI real install profile scenario/fixture 추가
2. product-specific clean baseline profile 및 baseline diff 구현
3. product-specific winget real install profile scenario/fixture 추가
4. product-specific Chocolatey real install profile scenario/fixture 추가
5. product-specific Appx/MSIX profile scenario/fixture 추가
6. product-specific scan profile matrix runner 추가: 여러 OS template/profile scenario를 한 명령에서 순차 실행하고 aggregate report 생성
7. Inventory analysis를 baseline diff/expected inventory 비교까지 확장
8. Fixture expected manifest를 assertion 입력으로 자동 연결하는 `inventory.expectedFixture` 계열 assertion 검토
9. `inspect-result --latest`, `inspect-result --open-html` 같은 결과 확인 편의 옵션 추가
10. `--keep-vm-on-failure`와 stale VM metadata 구현
11. Provider/guest diagnostic log artifact 저장
12. Known app baseline 확인
13. WinRM 실행 컨텍스트에서 `requireAdministrator` manifest 검증
14. CI example에서 `guest-preflight`/`fixture-smoke`/`artifact-smoke`/`run` 단계 정리
15. Linux SSH fixture/artifact smoke로 확장
16. Python CLI provider와 Web `ProxmoxLabClient` 상위 계약 단일화
17. `validate-suite` CLI 또는 동일 suite 검증기 공유
18. `inventory.expectedFixture` 계열 assertion 설계/구현
19. `oslab cleanup-stale` CLI 구현
20. Run artifact schema versioning 및 `packages/shared` 타입 정리
21. Web Matrix Run Planner 구현: OS template axis x OS state/profile axis, capacity, evidence, allowFailure 표시
22. Web cleanup dry-run/confirmation 구현 완료: 삭제 후보 VMID/name/node/status 표시, age/owning run은 stale metadata 이후 연결
23. Web Proxmox/tunnel readiness diagnostics 확장: User-Agent policy, `/api2/json`, WAF hint, QGA, template flag
24. 빠른 artifact 전송 mode 구현: `artifact.transfer: http-pull|qga` 또는 동등한 config로 대형 제품 artifact를 guest가 host/API에서 직접 다운로드하게 하여 QGA chunk upload 병목 완화
