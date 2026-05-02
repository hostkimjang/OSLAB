# Scenario Builder V2 협업 회의록

작성일: 2026-04-27

## 회의 목적

시나리오 작성 화면을 “YAML을 잘 아는 개발자만 쓰는 화면”에서 “운영자도 빌더로 조립하고, 필요하면 YAML로 내려가 확인하는 화면”으로 확장한다. 이번 라운드는 P0부터 P3까지 나온 이슈를 한 번에 정리하고, 구현/검증/문서 갱신까지 같은 단위로 닫는다.

## 참가 관점별 결론

| 관점 | 결론 |
| --- | --- |
| UI/UX | 필드 설명은 화면을 밀어내는 문장 대신 작은 원형 `i` tooltip으로 둔다. 설명은 내부 구현보다 사용자가 언제/왜 쓰는지 중심으로 쓴다. |
| Web Design | 시나리오 빌더는 compact summary를 먼저 보여주고, 편집 시에만 섹션형 조립 UI를 연다. 반복 항목은 카드 더미가 아니라 촘촘한 리스트로 정리한다. |
| Frontend | `OS family`, `guest mode`, report format, cleanup처럼 값 범위가 정해진 필드는 text input이 아니라 select/chip/toggle로 바꾼다. |
| API/Architecture | YAML을 직접 저장하기 전에 Web API에서 scenario contract를 한 번 더 확인한다. 새 시나리오 생성은 create-only API로 덮어쓰기를 막는다. |
| QA | 1366x768 desktop, 390x844 mobile, hover/focus/click tooltip, invalid YAML 저장 차단, builder apply, 새 시나리오 생성까지 smoke 대상에 넣는다. |
| 사용자 개발자 | product-specific 같은 실제 제품 검증을 만들 때 artifact, fixture, product step, assertion이 한 화면에서 서로 연결되어 보여야 한다. |

## P0 구현 항목

- [x] `id`, `name`, `OS family`, `guest mode`, VMID range 등 주요 필드 옆에 사용자 친화 tooltip 추가
- [x] `OS family`, `guest mode`, `artifact type`, `artifact transfer`를 select로 변경
- [x] report format과 guest 접속 우선순서를 chip toggle로 변경
- [x] cleanup 정책을 checkbox/toggle 형태로 변경
- [x] YAML 저장 전 `scenario-content` 계약 검증 추가
- [x] 정상/검증중 문법 상태는 toast로 유지하고 invalid 상태만 inline으로 유지

## P1 구현 항목

- [x] 새 시나리오 생성 dialog 추가
- [x] Windows smoke, Linux smoke, product-specific smoke template 제공
- [x] 새 파일 생성은 `POST /api/files` create-only로 처리해 기존 파일 덮어쓰기 방지
- [x] 생성 직후 catalog에 반영하고 해당 파일을 편집 상태로 열기

## P2 구현 항목

- [x] Fixture 섹션 추가: id/type/source/expectedOutput 편집
- [x] Product step 섹션 추가: shell/command/stdout JSON/secret token 편집
- [x] Assertion 섹션 추가: id/type/body JSON 편집
- [x] JSON body는 render API에서 parse 검증 후 YAML로 변환

## P3 구현 항목

- [x] 한국어/영어 microcopy 정리
- [x] 좁은 화면에서 builder row가 1열로 접히도록 반응형 스타일 적용
- [x] 목록 header에 `새 시나리오` action 추가
- [x] 실제 브라우저 smoke와 screenshot 산출물 추가
- [ ] Playwright 자동 회귀 케이스는 CI/로컬 runner 의존성 정리 후 고정

## 검증 항목

| 검증 | 기대 |
| --- | --- |
| `corepack pnpm --filter @oslab/api lint` | API typecheck 통과 |
| `corepack pnpm --filter @oslab/web lint` | Web typecheck 통과 |
| 브라우저 desktop smoke | 새 시나리오 버튼, dialog, builder field, tooltip, apply 동작 |
| 브라우저 mobile smoke | builder/dialog/list가 horizontal overflow 없이 표시 |
| 저장 차단 smoke | YAML syntax 또는 scenario contract 오류가 있으면 저장 차단 |

## 2026-04-27 중간 회의/검증 결과

| 관점 | 확인/결정 |
| --- | --- |
| UI/UX | 새 시나리오 dialog는 90% preview/diff overlay가 아니라 compact creation form으로 분리하고, X icon close와 create-only flow를 확인했습니다. |
| Frontend | report format chip을 변경한 뒤 `YAML에 적용`으로 editor buffer가 갱신되고 syntax toast/diff modal이 이어지는 흐름을 확인했습니다. |
| QA | `scenario-content` API에서 정상 scenario는 `ok=true`, id 누락 scenario는 `ok=false`와 `id must be a non-empty string.`을 반환했습니다. |
| Runner | Web에서 생성한 `scenarios/windows/new-windows-smoke.example.yaml`이 `uv run oslab validate-scenario --scenario ...`에서 `valid scenario: new.windows.smoke`로 통과했습니다. |
| Mobile | 390x844에서 document horizontal overflow는 없고, builder header가 1열로 정리되어 제목이 깨지지 않도록 CSS를 보정했습니다. |

증거:

- `output/web-dashboard/scenario-builder-v2-created-desktop.png`
- `output/web-dashboard/scenario-builder-v2-tooltip-desktop.png`
- `output/web-dashboard/scenario-builder-v2-diff-before-save.png`
- `output/web-dashboard/scenario-builder-v2-validation-smoke.json`
- `output/web-dashboard/scenario-builder-v2-mobile-smoke.json`
- `output/web-dashboard/scenario-builder-v2-mobile-editor-fixed.png`

## 2026-04-27 생성 Dialog 비율 수정 회의/검증 결과

| 관점 | 확인/결정 |
| --- | --- |
| Designer | 새 시나리오는 빠른 생성 폼이므로 90% 전체 화면 modal을 쓰지 않습니다. 사용자가 채울 필드는 template, id, name, path 네 가지라 720px 내외의 compact dialog가 맞습니다. |
| UI/UX | action button은 우측 하단의 일반 버튼 비율로 유지하고, 모바일에서도 X close는 우측 상단에 고정했습니다. |
| Frontend | `.previewDialog` 공용 90vw/90svh 규칙이 `.scenarioCreateDialog`를 덮어쓰던 순서 문제를 scenario 전용 override로 분리했습니다. |
| QA | 1366x768 desktop과 390x844 mobile에서 dialog 크기, input/button 높이, horizontal overflow false를 확인했습니다. |

증거:

- `output/web-dashboard/scenario-create-dialog-compact-desktop.png`
- `output/web-dashboard/scenario-create-dialog-compact-mobile.png`
- `output/web-dashboard/scenario-create-dialog-compact-smoke.json`

## 2026-04-28 새 시나리오 생성 UAT 회의/검증 결과

| 관점 | 확인/결정 |
| --- | --- |
| QA | 새 파일 생성은 기존 파일을 덮지 않아야 하며, 이미 편집 중인 scenario/builder 변경이 있으면 생성 전에 확인해야 합니다. 생성 후에는 catalog 선택, editor 편집 가능 상태, builder model 로딩까지 한 번에 확인합니다. |
| Designer | 생성 dialog는 “시작 파일 만들기” 성격이므로 과한 여백 없이 compact 유지합니다. 대신 template summary와 3단계 흐름으로 사용자가 다음 행동을 예측하게 합니다. |
| Frontend | `id`를 바꾸면 저장 경로도 자동으로 slug 기반 갱신합니다. `new-windows-smoke.example.yaml`처럼 기본 파일이 이미 있으면 `-2` suffix로 자동 회피합니다. |
| 사용자/운영자 | 생성은 VM을 만들거나 제품을 실행하지 않는다는 문구를 명시했습니다. 실제 실행은 Run 화면에서 artifact와 lab 상태를 확인한 뒤 시작합니다. |

구현:

- 저장 경로 inline 상태: 사용 가능/필수/형식 오류/중복 표시
- `id`와 저장 경로 자동 동기화
- default path 자동 중복 회피
- 기존 scenario editor/builder dirty-state confirm guard
- scenario/suite builder inspect request race guard

증거:

- `output/web-dashboard/scenario-create-uat-smoke.json`
- `output/web-dashboard/scenario-create-uat-dialog.png`
- `output/web-dashboard/scenario-create-uat-after-create.png`
- `output/web-dashboard/scenario-create-uat-mobile-dialog.png`
- CLI: `uv run oslab validate-scenario --scenario scenarios/windows/uat-windows-smoke-1777346047322.example.yaml`

남은 후속 안건:

- 생성 dialog focus trap/focus restore를 diff/preview modal과 같은 수준으로 맞추기
- OS template axis x OS state/profile axis 선택 UI로 product-specific 검증 matrix 목적 드러내기
- `templateVmId`, `output adapter`, `body JSON` 등 내부 레이블을 운영자 언어로 2차 정리
- `Artifact 실행 명령`과 `제품 실행 단계`가 모두 4번처럼 보이는 문제를 4A/4B 또는 단일 실행 섹션으로 정리

## 2026-04-27 디자인 개편 회의/검증 결과

| 관점 | 확인/결정 |
| --- | --- |
| Designer | 기존 V2는 조립기보다 압축 설정 폼에 가까웠습니다. Target VM -> 환경 준비 -> Artifact/Output -> 실행 명령 -> 결과 체크 -> 정리 순서의 workflow로 재배치했습니다. |
| UI/UX | `새 시나리오` action과 파일 목록 접기 버튼이 같은 action group, 같은 높이로 보이도록 정렬했습니다. |
| Frontend | builder summary는 실행 판단형 metadata strip으로 정리하고, workflow는 화면 폭에 맞춰 줄바꿈되도록 변경했습니다. 내부 horizontal overflow는 제거했습니다. |
| QA | 1366x768 desktop과 390x844 mobile에서 list action same-row, builder/workflow/document horizontal overflow false를 확인했습니다. |

증거:

- `output/web-dashboard/scenario-builder-v2-design-header-actions.png`
- `output/web-dashboard/scenario-builder-v2-design-desktop-expanded.png`
- `output/web-dashboard/scenario-builder-v2-design-mobile-expanded.png`
- `output/web-dashboard/scenario-builder-v2-design-regression-smoke.json`

## 2026-04-28 Vertical Axis Builder 디자인 시안 회의

시안:

- `output/web-dashboard/scenario-builder-vertical-axis-mockup.png`

제안 구조:

- 좌측 catalog list는 유지
- main editor 영역 안에서 왼쪽에 세로 stepper builder rail 배치
- rail 오른쪽에 선택 단계의 compact form/detail panel 배치
- 가장 오른쪽과 대부분의 면적은 YAML/text editor가 차지
- top bar에는 path, dirty 상태, diff/compare, `빌더 내용을 YAML에 반영`, 저장/취소를 한 줄로 정리

| 관점 | 평가 |
| --- | --- |
| Designer | 긍정적입니다. 현재 horizontal builder는 위쪽 공간을 많이 먹어 YAML 영역을 아래로 밀어냅니다. 세로축은 “시나리오 흐름”을 한눈에 보여주면서 editor 높이를 보존합니다. |
| UI/UX | 흐름 이해가 좋아집니다. 사용자는 1 대상 VM -> 2 환경 준비 -> 3 테스트 파일/출력 -> 4 실행 명령 -> 5 결과 체크 -> 6 정리 순서로 조립한다는 감각을 유지합니다. |
| Frontend | desktop에서는 grid 3열 구조가 현실적입니다: `builder rail 180-220px`, `step detail 260-360px`, `editor minmax(520px, 1fr)`. 단, detail panel 폭이 좁아 JSON textarea/긴 command는 overflow 대응이 필요합니다. |
| QA | 1366px 이하, 390px mobile, 긴 path/긴 command/JSON body, builder dirty-state, diff modal, keyboard focus 순서를 별도 smoke로 묶어야 합니다. |
| 사용자/운영자 | YAML이 계속 보이므로 “빌더에서 바꾼 게 실제 파일에 어떻게 반영되는지” 이해하기 쉽습니다. 반대로 초보자에게 YAML이 너무 크게 보일 수 있으므로 editor collapse/preview mode도 필요합니다. |

결론:

- 이 방향은 현재 공간 낭비 문제를 줄일 가능성이 큽니다.
- `Scenario Builder V3 vertical layout` prototype을 1차 구현했습니다.
- desktop은 vertical axis + 오른쪽 YAML editor 구조로 진행합니다.
- mobile/tablet은 1열 흐름으로 전환하고, 후속으로 `빌더 / YAML` segmented tab 또는 drawer를 검토합니다.
- `Artifact 실행 명령`과 `제품 실행 단계`의 4번 중복 문제는 `4A`/`4B`로 1차 정리했습니다.

수용 기준:

- 1366x768에서 editor visible height가 기존 expanded builder 대비 증가해야 함
- 선택된 step detail이 YAML editor를 520px 미만으로 압박하지 않아야 함
- 390x844에서 horizontal overflow false
- `빌더 내용을 YAML에 반영` 후 dirty/diff/save 흐름이 기존과 동일하게 동작
- keyboard tab 순서: catalog -> stepper -> detail form -> apply/save -> editor
- 긴 JSON/log/command 입력은 줄바꿈 또는 full-screen editor affordance 제공

1차 구현/검증:

- Browser smoke: `output/web-dashboard/scenario-builder-v3-vertical-smoke.json`
- Screenshots: `output/web-dashboard/scenario-builder-v3-vertical-desktop.png`, `output/web-dashboard/scenario-builder-v3-vertical-mobile.png`
- Mockup: `output/web-dashboard/scenario-builder-vertical-axis-mockup.png`
- Desktop smoke: `railButtons=6`, YAML editor `520x534`, horizontal overflow false
- Mobile smoke: workspace/editor width `324px`, horizontal overflow false

## 2026-04-28 FHD/QHD Viewport Design Review

요청에 따라 디자이너, UI/UX, 프론트엔드 관점의 subagent 리뷰를 병렬로 진행하고, 실제 브라우저 viewport matrix를 남겼습니다.

검증:

- Command: `corepack pnpm exec playwright test --config playwright.web-dashboard.config.cjs --reporter line`
- Report: `output/web-dashboard/viewport-design-matrix-smoke.json`
- Screenshots: `output/web-dashboard/viewport-matrix-mobile-*.png`, `output/web-dashboard/viewport-matrix-tablet-*.png`, `output/web-dashboard/viewport-matrix-desktop-1366-*.png`, `output/web-dashboard/viewport-matrix-fhd-*.png`, `output/web-dashboard/viewport-matrix-qhd-*.png`
- Scope: Scenario Builder V3, Run Launcher, Results
- Result: console/page errors `0`, horizontal overflow `false`

| Viewport | Scenario workspace | Builder | YAML editor | 전문가 판단 |
| --- | ---: | ---: | ---: | --- |
| 390x844 | `324px` wide flow | `324x1054` | `324x805` | list body `409px`, collapsed list is top bar `358x48`, builder 내부 Y scroll 없음 |
| 768x1024 | `702px` wide flow | `702x992` | `702x805` | list body `416px`, collapsed list is top bar `736x48`, builder 내부 Y scroll 없음 |
| 1366x768 | `811x534` workspace | `420x534` | `379x534` | builder/YAML workspace height fill. step button 균일, list clipping 없음 |
| 1920x1080 | `1284x846` workspace | `591x846` | `681x846` | builder/YAML full-height, line number gutter `44px`, list clipping 없음 |
| 2560x1440 | `1924x1206` workspace | `860x1206` | `1052x1206` | wide builder 상한 확대, builder/YAML full-height |

회의 결론:

- P0 완료: scenario list collapse가 실제 `52px` rail로 줄어들고 editor 공간을 돌려줍니다.
- P0 완료: 1366 desktop에서 builder를 `420px`로 넓혀 조립 UI가 작업면답게 보이도록 했습니다. list collapse 후 YAML은 `546px`까지 회복합니다.
- P0 완료: mobile/tablet의 list는 전체 항목을 끝없이 펼치지 않고 약 5-7개 높이의 scroll 영역으로 제한합니다. 접힘 상태는 왼쪽 rail이 아니라 상단 가로 bar로 표시합니다.
- P1 완료: FHD/QHD에서는 builder 폭을 `591px`/`860px`까지 넓히고 builder/YAML 모두 workspace 높이를 채우게 했습니다.
- P1: `YAML에 적용`은 저장처럼 오해되지 않게 builder draft, YAML applied, save required 상태를 분리합니다.
- P2: Run 화면은 FHD 이상에서 console/log 영역이 전체 작업면의 절반 이상을 가져가게 하고, 설정 form은 `480-640px` 상한을 둡니다.
- P2: Results 화면은 list/filter panel을 `360-480px` 상한으로 두고 detail/preview가 남은 폭을 가져가게 합니다.
- P3: 생성 완료 후에는 `대상 VM 확인`, `Artifact 설정`, `실행 화면으로 이동` 같은 후속 action을 작게 제공합니다.

## 2026-04-28 Vertical Axis Polish 회의/검증 결과

| 관점 | 확인/결정 |
| --- | --- |
| Designer | 선택된 단계만 큰 카드처럼 보이면 사용자는 흐름보다 특정 번호가 비정상적으로 강조된다고 느낍니다. 모든 단계 버튼 외곽을 같은 규격으로 보이고, active는 색과 얇은 outline으로만 구분합니다. |
| UI/UX | mobile/tablet에서 scenario list가 상단 bar로 접힐 때는 좌우 이동이 아니라 위/아래 열림 affordance가 자연스럽습니다. 접힘/펼침 glyph를 viewport 방향에 맞춰 전환했습니다. |
| Frontend | Scenario Builder 내부 `builderStepDetail`, 반복 row list, scenario builder panel이 별도 Y scroll을 만들지 않게 하고, 내용은 panel/page 흐름으로 펼쳐집니다. |
| QA | viewport matrix에 step button width/height delta와 builder internal Y scroll 여부를 수집하도록 추가했습니다. mobile/tablet/1366/FHD/QHD 모두 delta `0`, internal Y scroll `false`, horizontal overflow `false`입니다. |
| Frontend Polish | list 접힘/펼침 glyph는 문자 대신 CSS chevron으로 그려 버튼 중앙에 고정했습니다. 넓은 화면에서는 YAML editor가 workspace 높이를 꽉 채우도록 `yamlWorkspaceHeightDelta=0`을 matrix에 기록합니다. |
| Layout Polish | compact horizontal stepper에서 기존 `1fr` explicit track이 첫 번째 버튼 앞 공간을 먹던 문제를 제거했습니다. matrix는 `stepButtonGapMax`를 추가로 기록하며 mobile/tablet/1366 compact 구간은 `0`입니다. |
| Visual Polish | desktop 이상에서는 builder panel도 workspace 높이를 채웁니다. scenario list row는 mobile/tablet `64px`, desktop 이상 `70px`로 조정해 제목과 경로가 한 행 안에서 잘리지 않게 했습니다. |

검증:

- Command: `corepack pnpm --filter @oslab/web lint`
- Command: `corepack pnpm exec playwright test --config playwright.web-dashboard.config.cjs --reporter line`
- Report: `output/web-dashboard/viewport-design-matrix-smoke.json`
- Screenshots: `output/web-dashboard/viewport-matrix-mobile-scenario-collapsed.png`, `output/web-dashboard/viewport-matrix-desktop-1366-scenario.png`, `output/web-dashboard/viewport-matrix-fhd-scenario.png`

## 2026-04-28 Scenario Builder V3 Visual Ratio Fix

사용자 피드백과 screenshot review에서 제목이 세로로 쪼개지고 builder가 YAML을 과하게 밀어내는 문제가 확인되어, 디자인/UI/프론트 관점으로 비율 계약을 재조정했습니다.

- Builder header title은 줄바꿈 금지, read-only 안내 문구는 다음 줄로 내려 제목을 압박하지 않게 했습니다.
- 1366 desktop에서는 builder를 `420px`로 넓히고, list collapse 후 YAML을 `546px`로 회복하게 했습니다.
- FHD/QHD에서는 builder가 각각 `591px`, `860px`까지 커져 실제 조립 작업면을 확보하고 YAML이 남은 작업면을 가져갑니다.
- desktop/FHD/QHD에서 builder panel과 YAML editor가 모두 workspace 높이를 채웁니다.
- mobile/tablet은 scenario list body를 `409-416px` scroll 영역으로 제한하고, list collapse는 상단 가로 bar(`358x48`, `736x48`)로 표시합니다.
- scenario list row는 제목과 경로가 잘리지 않도록 mobile/tablet `64px`, desktop 이상 `70px`로 조정했습니다.
- YAML editor에 vim `set nu`처럼 좌측 line number gutter를 추가했습니다.
- 901-1500px 구간에서는 stepper rail을 compact number strip으로 전환해 좁은 editor panel에서 label이 뭉치거나 세로로 깨지지 않게 했습니다.

검증:

- Command: `corepack pnpm exec playwright test --config playwright.web-dashboard.config.cjs --reporter line`
- Report: `output/web-dashboard/viewport-design-matrix-smoke.json`
- Screenshots: `output/web-dashboard/viewport-matrix-desktop-1366-scenario.png`, `output/web-dashboard/viewport-matrix-fhd-scenario.png`, `output/web-dashboard/viewport-matrix-qhd-scenario.png`

## 후속 회의 안건

- 빠른 artifact 전송 mode와 Scenario Builder의 artifact transfer 옵션을 실제 실행 경로와 연결
- fixture expected manifest를 builder에서 schema-aware form으로 더 세분화
- assertion type별 전용 form 제공 여부 결정
- Suite Builder도 Scenario Builder V2와 같은 tooltip/section density로 맞추기
