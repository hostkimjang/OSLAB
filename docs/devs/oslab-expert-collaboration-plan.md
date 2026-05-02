# oslab 전문가 협업 기획 및 개발 계획

최종 업데이트: 2026-04-27

## 목적

이 문서는 현재 `oslab` 구현 상태를 기준으로 남은 구조 개선, 새 기능 개선, 디자인 개선, 사용성 개선을 한 번의 협업 회의처럼 정리한 개발 계획입니다. 기존 체크리스트의 방향을 유지하면서 바로 개발 가능한 항목과 장기 로드맵을 분리합니다.

## 회의 참가 관점

| 관점 | 책임 | 이번 결론 |
| --- | --- | --- |
| Platform Architecture | core/provider/guest/plugin/report 경계 | URL/API/CLI contract는 유지하고 내부 책임 분리를 단계적으로 진행 |
| Validation Automation | scenario/profile/suite/CI 실행성 | OS template axis와 OS state/profile axis를 계속 분리하고, real install profile을 다음 핵심 기능으로 유지 |
| Web UX/Design | Dashboard 실행/결과/작성 경험 | 운영자가 실행 전 상태를 판단할 수 있도록 단계형 readiness, 90% diff modal, compact builder를 우선 반영 |
| QA/Browser Verification | 브라우저 회귀와 실제 demo run | Web 변경은 browser smoke와 screenshot을 남기고, 가능하면 demo run으로 닫음 |
| Operations/Security | local env, Proxmox, cleanup, secrets | stale cleanup, least-privilege token, CI concurrency guidance를 운영 로드맵 상단에 둠 |
| Results/Evidence | run artifact contract와 실패 분석 | Evidence checklist는 계약 누락을 드러내고, 실제 run 파일 discovery는 계약 밖 artifact도 숨기지 않게 함 |

## 합의된 개발 원칙

1. `oslab` public identity는 generic OS integration test platform으로 유지하고, product-specific 전용 검증은 `docs/product-specific_docs/`와 전용 scenario/fixture 아래에 둡니다.
2. Web Dashboard는 marketing 화면이 아니라 lab operator tool입니다. 정보 밀도, 실행 전 safety gate, 결과 분석 속도를 우선합니다.
3. 문서와 checklist는 구현과 동시에 갱신합니다.
4. Web Dashboard 변경은 `docs/devs/browser-debug-checklist.md` 기준으로 실제 브라우저에서 확인합니다.
5. real VM 실행이 필요한 항목과 local compile/browser smoke만으로 닫을 수 있는 항목을 분리해 기록합니다.

## 우선순위 로드맵

### P0: 구조 안정화

- [x] Next.js `app/page.tsx` thin entrypoint 유지
- [x] dashboard component/helper/section 1차 분리 유지
- [x] Web Lab Status Proxmox request에도 CLI provider와 같은 `User-Agent` 적용
- [x] Web/API Proxmox HTTP 정책을 `ProxmoxLabClient`로 분리
- [ ] Python CLI provider와 Web `ProxmoxLabClient`의 상위 계약 단일화 검토
- [ ] `DashboardPage.tsx` state/effect를 custom hook으로 분리
- [ ] `JobService`를 command factory, process runner, event stream으로 분리
- [ ] `LabService`를 config parsing, Proxmox client, cleanup orchestration으로 분리
- [ ] Scenario/Suite 검증 계약 단일화: `validate-suite` CLI 추가 또는 API가 동일 검증기 호출
- [ ] versioned report artifact schema를 문서와 `packages/shared` 타입으로 고정

### P0: Web 운영 UX

- [x] Run Launcher 단계형 readiness strip 추가
- [x] Run Launcher 5단계 flow 1차 구현
  - 대상 선택, Artifact, 랩과 설정, 옵션, 검토와 실행 section으로 분리
  - 실행 묶음/시나리오 버튼별 ready/blocked reason 표시
  - Artifact 확인 중 stale check 결과로 실행되지 않도록 disabled 조건 보강
- [x] authoring 저장 전 diff preview 추가
  - editor 안에는 compact summary만 남기고, 저장 클릭 시 viewport 약 90% diff modal을 먼저 표시
  - modal 안에서 최종 저장/X close/`Esc`/backdrop close 지원
- [x] Authoring builder/editor 공간 재조정
  - Scenario/Suite visual builder를 compact scroll panel로 낮춰 YAML editor가 주 작업공간으로 남도록 조정
- [x] Authoring builder 밀도 재조정
  - 디자이너/웹디자이너: read-only 기본 상태에서는 summary chip만 보이게 해 빈 공간과 내부 스크롤을 줄임
  - 프론트: `빌더 열기`/`빌더 접기`로 builder 작업 공간을 명시적으로 전환하고, 열린 상태는 이전 `128px` cap보다 넓게 제공
  - QA: 1366x768에서 summary builder `109px`, textarea `416px`, expanded builder `323px`, diff row gap `4px`, horizontal overflow false 확인
- [x] Suite builder run list 정리
  - 디자인: 반복 form card 대신 실행 순서, id, 시나리오, tier, 실패 허용, 이동/삭제 action이 한 줄로 스캔되는 compact list 적용
  - 프론트: row별 반복 label을 table-like header로 올리고, 이동/삭제는 icon action으로 축약
  - QA: `suiteRunRows=5`, `legacyBuilderRows=0`, first row height `52.6px`, row overflow false, 390x844 mobile horizontal overflow false 확인
- [x] Authoring list collapse/expand
  - Scenario/Fixture/Suite 파일 목록을 52px rail로 접어 YAML/PowerShell editor 본문 공간을 확장
  - 접기/펼치기 후에도 선택 파일을 유지하고, 모바일에서는 horizontal overflow 없이 단일 column으로 표시
- [x] 저장 전 YAML/PowerShell syntax check
  - 현재 editor buffer를 저장 전에 검사하고 문법 오류가 있으면 저장을 차단
  - YAML scenario/suite와 PowerShell fixture 모두 line/column issue를 UI에 표시
  - invalid YAML 입력 시 visual builder inspect API가 `500`을 내지 않도록 정규화
- [x] Authoring syntax feedback UX 정리
  - UX/디자인: 정상/검증중 문법 상태는 editor 레이아웃을 흔들지 않는 toast로 이동
  - 프론트: 저장 차단이 필요한 invalid 상태만 inline issue panel로 유지
  - QA: invalid YAML 상태에서는 visual builder inspect 호출을 막아 `/api/build/scenario/inspect` 400 console noise 제거
  - 사용자 개발자: builder apply action은 primary 저장 버튼과 구분되는 secondary `YAML에 적용`으로 정리
- [x] Scenario Builder V2 조립형 작성 UX
  - 회의록: `docs/devs/scenario-builder-v2-collaboration.md`
  - 디자이너/UX: `id`, `name`, `OS family`, `guest mode`, cleanup 등 판단 비용이 큰 필드에 사용자 친화 `i` tooltip 추가
  - 프론트: enum 성격의 field는 text input 대신 select/chip/toggle로 정리
  - 개발자: artifact command, fixture, product step, assertion을 visual builder에서 round-trip 편집 가능하게 확장
  - QA: 저장 전 YAML 문법뿐 아니라 scenario 계약 검증도 수행하고, create-only 새 시나리오 생성 flow를 추가
- [x] 1366x768, 390x844 viewport smoke를 필수 체크로 승격
- [x] keyboard focus ring, nav landmark, segmented/result filter `aria-pressed` 등 접근성 계약 1차 보강
- [ ] disabled reason, authoring mode semantics 등 접근성 계약 추가
- [x] Results evidence checklist 추가
  - API: `GET /api/runs/:runId/evidence`
  - UI: `run.json`, timeline, raw/normalized output, reports, cleanup state present/missing/contract gap 표시
- [x] Results 실제 run 파일 discovery
  - API detail이 `runs/<run-id>/` 하위 실제 파일을 스캔해 `files` 목록 반환
  - evidence 계약 밖 파일은 `추가 발견`으로 표시하고 미리보기 가능한 text-like artifact는 modal preview 지원
  - evidence 계약상 기대하지만 실제 생성되지 않은 파일은 `누락` 파일 카드로 표시하고 dead link/preview request를 만들지 않음
- [x] Results 사람이 읽는 시간 표시
  - 결과 리스트에 상대 시간과 절대 로컬 시간을 함께 표시
  - 결과 상세에 실행 시작, 완료, 소요 시간을 보여주는 `결과 시간` 섹션 추가
- [x] Results 과거 running 상태 보정
  - artifact가 `running`으로 남아 있어도 dashboard job의 terminal 상태가 있으면 `cancelled`/`failed`/`passed`를 우선 표시
  - 리스트/상세에 `상태 보정` 문구를 표시하고, dashboard job과 매칭되지 않는 오래된 active artifact는 `멈춤` filter로 분리
- [x] Results 고급 분석 필터
  - 종류(run/suite), 이슈(failure class, 필수/허용 실패, 취소, 계약 누락), 증거(정상/누락 있음) 필터 추가
  - 리스트 row에 scenario/suite lineage, failure class, contract gap 수를 chip으로 표시
- [x] Results list collapse/expand
  - 결과 목록 패널을 icon button으로 접어 상세/증거 본문 영역을 확장
  - 접힘 상태에서도 좁은 rail에 펼치기 버튼과 현재 결과 수를 유지
  - 1366px에서 detail 영역이 `566px -> 1014px`로 확장되는 것을 browser smoke로 확인
- [x] Results preview modal redesign
  - inline preview panel을 overlay modal로 전환
  - file preview button/evidence row click 기반으로 열림
  - `Esc`/backdrop/X icon close button 닫기, body scroll lock 적용
  - desktop/mobile 모두 viewport 약 90% 크기의 responsive preview 적용
  - 없는 run file 요청은 처리되지 않은 `500` 대신 `404`로 정규화
- [x] Web cleanup dry-run/confirmation 추가
  - API: `POST /api/lab/cleanup-stale`
  - 기본 대상은 stopped/stale `oslab-*` VM으로 제한
  - `confirmToken`이 dry-run 후보와 일치할 때만 destructive cleanup 진행
- [x] 저장 전 YAML/PowerShell syntax check
- [x] Run Launcher 5단계 form layout 1차 구현
- [x] Run Launcher scenario-aware artifact recommendation 1차 구현
  - 선택한 scenario와 catalog artifact 이름을 매칭해 추천 chip 표시
  - product-specific 전용 scenario는 repo-local 제품 artifact가 catalog에 없으면 demo artifact를 추천하지 않음
  - 390x844 mobile Run 화면이 내부 panel scroll에 잘리지 않도록 page-level scroll로 보정
- [x] Run Launcher artifact upload 확장
  - 브라우저에서 ZIP/EXE/MSI/script 단일 파일을 업로드하면 `.web-artifacts/`에 저장
  - 업로드 성공 후 해당 path를 artifact source/path로 즉시 선택하고 existence check까지 연결
  - `.web-artifacts` 업로드 artifact도 catalog/check/run command 흐름에서 같은 artifact로 취급
  - 직접 업로드 상태 카드는 선택됨/업로드 중/사용 중/실패, 파일 수, 바이트 진행률, 저장 경로를 표시
- [x] Run Launcher folder artifact upload와 반응형 박스 개선
  - 브라우저 폴더 picker로 선택한 폴더 내용을 `.web-artifacts/<timestamp>-<folder>/` 아래 복사하고 생성된 directory path를 현재 artifact로 선택
  - 제품 `bin/Release`처럼 서버 로컬 원본 경로를 그대로 쓰는 경우는 기존 `직접 입력 - 파일/폴더 경로`를 유지
  - 좁은 Run panel에서도 업로드/추천 박스의 title, 설명, action button이 세로로 눌리지 않도록 responsive grid로 정리
- [x] 카드/섹션 설명 tooltip 1차 구현
  - 디자이너/웹디자이너: 전체 row가 아니라 판단 비용이 큰 card/section header에 원형 `i`를 배치
  - 프론트: 공통 `InfoTooltip` component, portal/fixed positioning, viewport clamp로 내부 scroll clipping 방지
  - QA/사용 개발자: hover뿐 아니라 focus/click/tap, `Esc`, outside click, mobile 390x844를 검증 범위에 포함
  - 후속 UX copy 리뷰: 내부 구현 설명보다 사용자가 이해할 기능 설명을 우선. Artifact는 `VM 안에서 테스트할 프로그램, 설치 파일, 스크립트, ZIP 묶음`으로 설명
- [x] Information tooltip 확장
  - 디자이너/콘텐츠: Scenario/Fixture/Suite, Suite policy, evidence file은 “정의”보다 “언제 봐야 하는지” 중심으로 설명
  - 프론트: Results evidence row는 preview button이므로 tooltip button을 내부에 중첩하지 않고 sibling control로 분리
  - QA: 1366x768/390x844에서 clipping/horizontal overflow/server/runtime error `0` 확인
- [x] QGA `exec-status` transient retry
  - 실제 product-specific 실행 묶음 Web 검증 중 path-profile preflight에서 `agent/exec-status` 일시 실패가 시나리오 실패로 번지는 문제 확인
  - QGA command timeout 안에서는 `exec-status` ProviderError를 재시도하고, timeout 시 마지막 오류를 diagnostic에 남기도록 수정
  - 적용: 환경 준비 dashboard metric, Scenario/Fixture/Suite catalog header, Scenario/Suite builder header, Suite policy, Results evidence group header, `run.json`/`progress.jsonl` evidence row
- [ ] Web smoke를 Playwright/Browser 자동화 테스트로 정식화

### P1: 검증 기능

- [ ] 빠른 artifact 전송 mode 설계/구현
  - Platform/Operations: 현재 QGA `file-write` 대형 upload는 base64/chunk/API round-trip 때문에 제품 artifact suite의 주 병목입니다.
  - QA evidence: 최신 suite run `20260427-160236-product-specific-windows-v1`에서 `16,575,826` bytes archive upload가 시나리오별 약 `450-478s`, guest 압축 해제는 약 `6s`였습니다.
  - Front/Web: Web에서 업로드한 `.web-artifacts`와 직접 입력 path 모두 동일 archive를 만들고, guest가 HTTP/BITS로 pull 받는 진행률을 live console/result timeline에 표시합니다.
  - Fallback: guest가 host URL에 접근하지 못하면 기존 QGA upload path로 자동 후퇴합니다.
- [ ] `keepVmOnFailure`를 실제 VM lifecycle 정책으로 연결
- [ ] fixture expected manifest 기반 `inventory.expectedFixture` assertion 설계/구현
- [ ] EXE/MSI real install profile 구현
- [ ] winget real install profile 구현
- [ ] Chocolatey real install profile 구현
- [ ] Appx/MSIX profile 구현
- [ ] baseline diff와 expected inventory 비교 확장
- [ ] Suite aggregate TRX report 구현
- [ ] OS template x profile 선언형 matrix schema 또는 suite v2 설계

### P1: 운영/복구

- [ ] `oslab cleanup-stale` CLI 구현
- [ ] stale VM metadata를 run artifact에 기록
- [ ] Provider/guest diagnostic log artifact 저장
- [ ] least-privilege Proxmox token role 문서화
- [ ] GitLab/GitHub CI example과 concurrency/resource group guidance 추가
- [ ] `oslab init-config` 또는 `oslab doctor`로 config/env 진입장벽 완화

### P2: 확장성

- [ ] WinRM probe/command/file transfer 구현
- [ ] Linux SSH command/upload/download 구현
- [ ] provider capability discovery 추가
- [ ] response DTO와 shared transport model 정리
- [ ] Dashboard Home을 최근 실패/마지막 run/새 실행 시작이 가능한 작업 시작점으로 개선
- [x] Results Explorer에 failureClass, suite/scenario, required/allowed failure 필터 추가

## 이번 개발 라운드에서 반영한 항목

- Run Launcher 상단에 `실행 준비 상태` strip을 추가해 대상 선택, artifact, lab, option, command 상태를 한눈에 보이게 했습니다.
- Scenario/Fixture/Suite editor에서 저장 전 변경 줄 수를 compact summary로 표시하고, 저장 버튼은 파일을 바로 쓰기 전에 90% diff modal을 먼저 엽니다.
- Scenario/Suite visual builder를 compact scroll panel로 낮춰, builder가 textarea 편집 공간을 과하게 밀어내지 않도록 조정했습니다.
- 추가 UX 리뷰를 반영해 Scenario/Suite visual builder를 기본 summary chip 형태로 접고, 사용자가 `빌더 열기`를 누를 때만 더 넓은 builder 작업 영역을 보여주게 했습니다.
- 저장 전 diff modal에서 변경 row가 modal 높이 전체로 벌어지던 grid stretch 문제를 수정해, 4줄 이하 변경도 위쪽에 촘촘히 붙어 보이게 했습니다.
- Scenario Builder V2 협업 회의록을 추가하고, P0-P3 항목을 구현 단위로 정리했습니다. 새 회의록은 `docs/devs/scenario-builder-v2-collaboration.md`입니다.
- Scenario Builder에 `id`, `name`, `OS family`, `guest mode`, VMID, artifact, output, report, cleanup 설명 tooltip을 추가하고, enum 필드는 select/chip/toggle로 바꿨습니다.
- 새 시나리오 생성 dialog를 추가했습니다. Windows smoke, Linux smoke, product-specific smoke 템플릿에서 시작하고, `POST /api/files` create-only 저장으로 기존 파일 덮어쓰기를 막습니다.
- Scenario Builder에서 fixture, product step, assertion까지 편집할 수 있게 확장하고, 저장 전 scenario contract 검증을 추가했습니다.
- Scenario/Fixture/Suite 작성 화면에 파일 목록 접기/펼치기를 추가했습니다. 목록을 접으면 52px rail만 남기고 editor 본문을 넓혀 긴 YAML/PowerShell을 더 편하게 볼 수 있습니다.
- Scenario/Fixture/Suite editor에 저장 전 문법 검사를 추가했습니다. YAML/PowerShell 오류는 line/column과 함께 표시되고, 오류가 있는 동안 저장 버튼이 차단됩니다.
- Web API Lab Status의 Proxmox HTTP request에 CLI provider와 같은 `User-Agent`를 적용해 reverse proxy/WAF 환경 drift를 줄였습니다.
- Web API 내부의 Proxmox HTTP transport, URL normalization, stop polling을 `ProxmoxLabClient`로 분리했습니다.
- Results Explorer에 evidence checklist를 추가해 `run.json`, `progress.jsonl`, raw/normalized output, reports, cleanup state를 한 화면에서 확인하게 했습니다.
- Results Explorer가 실제 run 폴더 파일과 기대 evidence 경로를 합쳐 고정 evidence 목록에 없던 `raw/fixture-demo-python-runtime.expected-output.json`은 `추가 발견`으로, 실제 생성되지 않은 `normalized/inventory.json` 같은 파일은 `누락` 카드로 표시하게 했습니다.
- Results Explorer의 결과 리스트/상세에 사람이 읽는 시간 표시를 추가해 `20260426-174301-...` 같은 run ID만 보던 흐름을 시작/완료/소요 시간 중심으로 읽을 수 있게 했습니다.
- Results Explorer에서 과거 취소된 job의 run artifact가 `running`으로 남아 있던 문제를 보정했습니다. 이제 `20260423-232218-demo-c-hello-windows`는 job 최종 상태를 따라 `cancelled`로 표시되고 `상태 보정: running -> cancelled`가 노출됩니다.
- Results Explorer에 종류/이슈/증거 고급 필터를 추가했습니다. provider failure suite, 필수 실패 suite, contract gap run을 리스트에서 바로 좁혀볼 수 있고 row에 lineage/failure/evidence chip을 표시합니다.
- Results Explorer에 결과 목록 접기/펼치기를 추가했습니다. 목록을 접으면 52px rail만 남기고 상세 본문 영역을 크게 확장해 evidence와 preview를 더 넓게 볼 수 있습니다.
- 디자이너/웹디자이너/프론트/QA 관점 검토를 반영해 Results preview를 상세 하단 inline panel에서 집중형 overlay modal로 전환했습니다.
- 추가 UX 리뷰를 반영해 Results preview modal을 viewport 약 90% 크기로 조정하고, 텍스트 닫기 버튼을 X icon close button으로 바꿨으며, 없는 preview file 요청이 `500`으로 보이지 않도록 `404`로 정규화했습니다.
- UX/프론트/QA 관점 후속 합의에 따라 Run Launcher를 5단계 실행 flow로 재배치하고, 각 실행 버튼의 차단 사유를 UI에 직접 표시했습니다.
- 디자이너/프론트/QA/사용 개발자 관점 후속 검토를 반영해 Run Launcher Artifact 단계에 scenario-aware 추천 chip을 추가했습니다. 추천 chip 클릭 시 artifact path가 catalog 선택으로 고정되고 existence check가 ready로 이어집니다.
- 사용 개발자/운영자 관점 후속 검토를 반영해 Run Launcher Artifact 단계에 브라우저 파일 업로드를 추가했습니다. 업로드 파일은 `.web-artifacts/`에 저장되고 즉시 현재 실행 artifact로 선택됩니다.
- 사용 개발자/QA 관점 후속 검토를 반영해 폴더 선택도 지원했습니다. 브라우저 보안상 원본 절대 경로는 받을 수 없기 때문에, 선택한 폴더는 `.web-artifacts` 아래 생성 디렉터리로 복사하고 그 directory artifact path를 현재 실행에 사용합니다.
- UX/QA 후속 검토를 반영해 직접 업로드 상태 카드를 추가했습니다. 사용자는 선택한 파일/폴더, 파일 수와 용량, 업로드 진행률, 완료 후 저장 경로, 실패 상태를 한 자리에서 확인할 수 있습니다.
- 실제 product-specific 실행 묶음 Web 검증 중 발견한 QGA `exec-status` transient 실패를 반영해, command 완료 대기 루프가 일시적인 Proxmox status 조회 실패를 재시도하도록 안정화했습니다.
- 좁은 실행 panel에서 `테스트 파일 업로드`와 `추천 테스트 파일` 박스가 세로로 찌그러지던 문제를 responsive grid/header 배치로 정리했습니다.
- 디자이너/웹디자이너/프론트/QA/사용 개발자 관점 협업 결과로 card/section header에 원형 `i` tooltip을 추가했습니다. 이후 UX copy를 다시 조정해 Artifact 같은 용어는 내부 개발 용어가 아니라 `테스트할 프로그램/설치 파일/스크립트/ZIP 묶음`처럼 사용자 기능 설명으로 읽히게 했습니다.
- 이어서 정보 설명을 넓혀 환경 준비(Fixture), 시나리오, 실행 묶음(Suite), Suite policy, `run.json`, `progress.jsonl` 같은 evidence까지 사용자가 “이걸 언제 봐야 하는지” 이해할 수 있게 했습니다.
- 모바일 Run Launcher에서 form이 viewport 안의 내부 scroll에 갇히던 문제를 수정해, 390x844 화면에서도 page-level scroll로 Artifact 추천과 실행 준비 상태까지 접근할 수 있게 했습니다.
- 전문가 추가 검토 결과로 확인된 cleanup 위험을 반영해 Web/API cleanup을 dry-run/confirmation/token-match 계약으로 변경했습니다. 기본 UI cleanup은 stopped/stale VM만 대상으로 잡고, running VM은 기본 삭제 대상에서 제외합니다.
- Matrix Planner는 새 실행 엔진이 아니라 기존 `suite-run` 위의 `product-specific Windows v1` profile coverage planner로 시작하는 방향으로 정리했습니다.
- Web Dashboard 브라우저 검증 지침에 Full HD `1920x1080`과 QHD `2560x1440`을 추가하고, 디자이너/UI/UX/프론트엔드 subagent 리뷰와 실제 viewport matrix smoke를 진행했습니다.
- Scenario Builder V3는 방향은 유지하되, 사용자 screenshot review에서 제목 세로 깨짐, list collapse 공간 미반환, builder 폭 부족, mobile/tablet list 과확장, builder field 침범이 확인되어 비율 계약을 다시 재설계했습니다. `1366x768` open list에서는 builder/YAML `420px/379px`, list collapse 후 YAML `546px`, QHD builder `680px`로 확인했습니다. mobile/tablet list collapse는 상단 가로 bar로 바꿨고 YAML에는 줄번호 gutter를 추가했습니다.
- 추가 screenshot review에서 남아 있던 글자 크기 불일치, active 단계 버튼만 과하게 커 보이는 문제, builder detail/list 내부 Y scroll, mobile/tablet 접힘 glyph 방향 문제를 보정했습니다. viewport matrix smoke에서 모든 Scenario 화면의 step button width/height delta `0`, builder internal Y scroll `false`, horizontal overflow `false`를 확인했습니다.
- 이어서 접힘/펼침 glyph를 폰트 문자가 아닌 CSS chevron으로 바꿔 버튼 중앙 정렬을 고정했고, 1366/FHD/QHD 넓은 화면에서는 YAML editor가 workspace 높이를 꽉 채우도록 수정했습니다. viewport matrix에서 wide 화면 `yamlWorkspaceHeightDelta=0`을 확인했습니다.
- compact horizontal stepper에 남아 있던 `1fr` explicit column 때문에 1번 단계만 큰 공간을 차지하던 문제를 제거했습니다. FHD/QHD에서는 builder 폭을 `591px`/`860px`로 확대해 넓은 화면에서 빌더가 답답해 보이지 않도록 조정했습니다.
- 추가 desktop/QHD screenshot review를 반영해 tablet/mobile이 아닌 화면에서는 Scenario Builder panel도 workspace Y축을 끝까지 채우도록 맞췄습니다. 시나리오 리스트 row는 mobile/tablet `64px`, desktop+ `70px`로 조정해 title/path clipping이 없도록 확인했습니다.
- 관련 문서와 checklist를 갱신해 다음 작업자가 같은 맥락에서 이어갈 수 있게 했습니다.

## 추가 전문가 리뷰에서 이어갈 항목

- Operations/Security: Web cleanup 안전장치는 닫았고, 다음은 CLI `oslab cleanup-stale`의 `--dry-run`/confirmation/force 계약과 stale VM metadata 기록입니다.
- Validation Automation: synthetic profile 다음 단계는 EXE/MSI real install profile과 fixture expected manifest 기반 assertion입니다.
- Platform Architecture: Python provider와 Web API의 상위 Proxmox 계약, `JobService` 책임 분리, versioned report artifact schema를 계속 구조 안정화 항목으로 유지합니다. 대형 artifact 전송은 QGA chunk upload 대신 guest pull HTTP/BITS fast path를 우선 검토합니다.
- Web UX/QA: Run Launcher 5-step layout, disabled reason, scenario-aware artifact recommendation, artifact upload, Results 고급 필터는 반영되었고, 이후 Playwright/Browser smoke 정식화를 이어갑니다.
- Design/UI/Frontend: Scenario Builder V3의 list collapse, mobile/tablet top-bar collapse, builder/YAML 비율, mobile/tablet list scroll, builder form density, YAML line number gutter는 반영했습니다. 다음 우선순위는 mobile/tablet `빌더/YAML` tab 분리와 QHD 이상 YAML line-length 가독성 보정입니다.
- Authoring Expansion: `New Scenario`의 create-only 안전 흐름을 `New Fixture`와 `New Suite`로 1차 확장했습니다. 다음은 product-specific fixture starter, generated suite run smoke, Artifact Manager/text-like authoring입니다. 회의록은 `docs/devs/authoring-expansion-collaboration-plan.md`입니다.
- API/Security: Web authoring policy 1차 공통화로 root, extension, `.env`/`*.local.*`/known secret path, overwrite, path traversal을 서버에서 강제했습니다. 다음은 size limit, Windows reserved device name, trailing dot/space/control char 차단입니다.

## 검증 계획

| 검증 | 명령/방법 | 기대 |
| --- | --- | --- |
| Web typecheck | `corepack pnpm --filter @oslab/web lint` | 통과 |
| API/shared 영향 확인 | `corepack pnpm --filter @oslab/shared build`, `corepack pnpm --filter @oslab/api lint` | 통과 |
| QGA exec-status retry unit/regression | `uv run pytest tests/test_qemu_agent_guest.py`, `uv run pytest tests/test_guest_preflight.py tests/test_artifact_smoke.py tests/test_fixture_smoke.py` | 통과 |
| Cleanup API smoke | 로그인 후 `POST /api/lab/cleanup-stale` dry-run 호출 | 후보만 반환, 토큰 없이는 삭제하지 않음 |
| Browser smoke | `http://127.0.0.1:3000` 로그인 후 Scenario/Run 화면 확인 | diff modal/readiness strip/Artifact 추천 표시 |
| Artifact recommendation smoke | `demo-powershell-system` 선택 후 추천 chip 클릭 | `validation/artifacts/powershell-system` path ready, mobile width `390`, errors `0` |
| Artifact upload smoke | Run Launcher에서 파일 업로드 | `.web-artifacts/` path 선택, artifact check `file`, upload state 표시, mobile horizontal overflow false |
| Folder artifact upload/responsive smoke | Run Launcher에서 폴더 업로드와 좁은 panel 확인 | `.web-artifacts/<timestamp>-Release` directory path 선택, artifact check `directory`, `Release` 156개 파일/진행률/저장 경로 상태 카드 표시, `output/web-dashboard/artifact-folder-upload-responsive-smoke.json` |
| Fast artifact transfer smoke | product-specific `bin/Release` artifact를 `http-pull` mode로 suite 실행 | archive hash/bytes 일치, guest download progress 표시, 기존 QGA upload 대비 전송 시간 단축, 실패 시 QGA fallback 가능 |
| product-specific suite Web smoke | Web에서 product-specific 실행 묶음 + 제품 `bin/Release` 경로 실행 | job `cmognt5bg000usmmg6u6uvktu`, 실제 VM 단계 진행, 3 passed / 1 required failed / 1 allowed failed, QGA `exec-status` transient bug 발견 |
| product-specific path-profile Web regression | QGA retry 패치 후 path-profile 단일 시나리오 Web 재실행 | job `cmogpdv9r002gsmmg4f7b062i`, run `20260427-133443-product-specific-agent-path-profile-windows`, `passed`, assertions `8`, server/runtime errors `0` |
| Evidence smoke | Results에서 `20260423-232535-demo-powershell-system-windows` 선택 | evidence checklist 표시, contract gaps `0` |
| Results discovered/missing file smoke | Results에서 `20260426-174301-demo-python-hello-windows` 선택 | `raw/fixture-demo-python-runtime.expected-output.json`은 `추가 발견`, `normalized/inventory.json`은 dead link 없는 `누락` 카드로 표시 |
| Results time smoke | Results에서 `20260426-174301-demo-python-hello-windows` 선택 | 리스트 절대 시간, 상세 `결과 시간` 섹션 표시 |
| Results stale running smoke | Results에서 `20260423-232218-demo-c-hello-windows` 선택 | artifact `running`을 job `cancelled`로 보정, `상태 보정` 표시 |
| Results advanced filters smoke | Results에서 종류/이슈/증거 필터 조합 | provider failure suite, 필수 실패 suite, contract gap run 표시 |
| Results list collapse smoke | Results에서 목록 접기/펼치기 | detail 폭 증가, rail 펼치기 버튼, mobile overflow 없음 |
| Authoring list collapse smoke | Scenario/Fixture/Suite에서 목록 접기/펼치기 | editor 폭 `664px -> 1012px`, 선택 파일 유지, mobile overflow 없음 |
| Authoring syntax smoke | Scenario/Fixture/Suite에서 valid/invalid syntax 입력 | valid dirty content는 toast로 표시되고 layout shift 없음, invalid YAML/PowerShell은 inline issue와 함께 저장 차단, server/runtime errors 0 |
| Authoring diff modal smoke | Scenario editor dirty 상태에서 저장/큰 화면으로 보기 | desktop `1229x691`, mobile `351x760`, builder summary `109px`, expanded builder `323px`, diff row gap `4px`, server/runtime errors 0 |
| Authoring syntax toast smoke | Scenario editor dirty 상태에서 정상/오류 syntax 입력 | 정상 syntax inline panel 0개, toast 표시, builder action `YAML에 적용`, invalid inline panel 표시 |
| Suite builder compact/syntax smoke | Suite editor에서 builder와 valid/invalid YAML 입력 | compact run list, row overflow false, valid syntax toast/저장 가능, invalid syntax inline panel/저장 차단 |
| Info tooltip smoke | Lab Status/Run/Artifact/Results/mobile에서 원형 `i` tooltip 열기 | 사용자 친화 copy 확인, hover/focus/click/tap 대응, desktop/mobile clipping 없음, server/runtime errors 0 |
| Information tooltip expansion smoke | Scenario/Fixture/Suite catalog, Fixture metric, evidence `run.json`/`progress.jsonl` tooltip 열기 | 신규 설명 copy 확인, evidence row nested button 없음, desktop/mobile clipping 없음, server/runtime errors 0 |
| Viewport design matrix smoke | `corepack pnpm exec playwright test --config playwright.web-dashboard.config.cjs --reporter line` | mobile/tablet/1366/FHD/QHD에서 Scenario/Scenario collapsed/Run/Results screenshot 20장, horizontal overflow false, console/page errors 0, `output/web-dashboard/viewport-design-matrix-smoke.json` |
| Scenario Builder vertical polish smoke | viewport matrix report의 Scenario/Scenario collapsed metrics 확인 | step button width/height delta `0`, compact stepper gap `0`, builder internal Y scroll `false`, mobile/tablet list collapse glyph 위/아래 방향, wide builder/YAML height delta `0`, scenario list text clipping `false` |
| New Fixture creation smoke | `corepack pnpm exec playwright test apps/web/tests/authoring-create-dialogs.spec.js --config=playwright.web-dashboard.config.cjs` | create-only API template, `validation/fixtures/**`, catalog refresh, edit mode, screenshot `output/web-dashboard/authoring-new-fixture-dialog.png` |
| New Suite creation smoke | `corepack pnpm exec playwright test apps/web/tests/authoring-create-dialogs.spec.js --config=playwright.web-dashboard.config.cjs` | create-only API template, `validation/suites/**`, 최소 1개 scenario, Suite Builder inspect, screenshot `output/web-dashboard/authoring-new-suite-dialog.png` |
| Artifact Manager authoring smoke | Artifact manager에서 repo/uploaded artifact 확인 및 text artifact 생성 | binary upload-only/read-only, text artifact allowlist 편집, hash/size/provenance 표시, artifact check `file|directory` |
| Demo run | Web UI에서 PowerShell/Python/C 중 하나 실행 | 가능하면 `passed` 및 screenshot 기록 |
