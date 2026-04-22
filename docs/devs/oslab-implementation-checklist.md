# oslab 구현 체크리스트

> 내부 작업 로그입니다. 공개 온보딩은 `README.md`와 `docs/index.md`에서 시작하고, 이 파일은 구현 진행 상황과 lab 검증 기록을 추적하기 위한 개발자용 문서입니다.

최종 업데이트: 2026-04-22

## 현재 상태 요약

`oslab`은 현재 Python CLI 골격, scenario/config 검증, Proxmox API 연결, 읽기 전용 lab preflight, VMID 할당, 실제 clone/boot smoke, QEMU Guest Agent command 실행, 작은 파일 upload/download, Windows guest preflight, Windows fixture upload/execution/expected output 수집, folder/installer artifact upload/command execution/output collection, archive 기반 folder artifact transfer, artifact smoke 단계별 progress console 출력, artifact smoke JSON/JUnit/HTML report writer, full `oslab run` artifact output layout, full run guest preflight/fixture 통합, SupplyScan template `config.ini` 오염 preflight, product step sequence 실행, host env 기반 secret token resolve/redaction, product stdout JSON capture, scan 완료 정보 `run.json` 요약, QGA UTF-8/CP949 mojibake 복구, `stdoutJson.ok == false` 실패 판정, SupplyScan raw output normalize, canonical inventory assertion 평가, canonical inventory 분석 artifact, canonical command result adapter, command stdout/exit-code assertion, PowerShell/Python/C/fixture-state/agent-steps demo suite와 Windows demo bootstrap fixture까지 구현되어 있습니다.

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
- Real Agent status smoke: 실제 `SupplyScanAgent.exe` Release artifact archive upload, status-only command execution, output collect/normalize/assertion, cleanup 통과
- Real Agent full smoke: 실제 `SupplyScanAgent.exe cli_mode register/status/scan` 실행, host token 없이 register/login 후 config.ini token 저장, HTML/JUnit/JSON report 생성, cleanup 통과
- SupplyScan plugin normalize: sample raw JSON을 `supplyscan.inventory` adapter로 canonical inventory 변환 통과
- Inventory analysis: 최신 실제 full smoke의 `normalized/inventory.json`을 분석해 record/source/publisher/confidence/quality summary 생성 통과
- Generic Python demo: clean Windows clone에서 portable Python bootstrap 후 `hello from python` 검증 통과
- Generic C demo: clean Windows clone에서 TinyCC bootstrap 후 `hello from c` 검증 통과

최근 로컬 테스트 결과:

```text
uv run pytest
137 passed
```

## 2026-04-22 Console Unicode Detail 출력 개선 진행 결과

- [x] CLI error `details` 출력에서 JSON Unicode escape(`\uXXXX`) 대신 한글 원문을 표시
- [x] Console `detail()`이 dict/list를 공통 JSON formatter로 출력하도록 정리
- [x] `inspect-result --json`, normalize/analyze JSON 출력 파일, artifact/report JSON에서 `ensure_ascii=False` 적용
- [x] Proxmox 연결 실패 같은 localized Windows error가 `[WinError 10060] 연결하지 못했습니다` 형태로 표시되는지 샘플 검증
- [x] 로컬 테스트 결과: `137 passed`

## 2026-04-22 QGA UTF-8/CP949 Log Encoding Fix 진행 결과

- [x] QEMU Guest Agent exec stdout/stderr에서 UTF-8 bytes가 Latin-1 mojibake 문자열로 들어오는 경우 자동 복구
- [x] Korean Windows PowerShell stderr에서 CP949 bytes가 Latin-1 mojibake 문자열로 들어오는 경우 자동 복구
- [x] QEMU Guest Agent file-read content에서도 동일한 mojibake 복구 적용
- [x] 기존 UTF-8 BOM mojibake(`EF BB BF`가 Latin-1 text로 보이는 경우)와 실제 BOM `\ufeff` 제거 유지
- [x] 기존 SupplyScan full smoke run의 scan stderr log, product stderr log, product step JSON, normalized inventory를 복구
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
- [x] 실패 조합도 cleanup 확인: `supplyscan.gold-lite.windows` + fake artifact는 product command 실패 후 VM destroy 완료
- [x] 실행 후 VMID range cleanup 재확인: `usedInRange: <none>`
- [x] 로컬 테스트 결과: `108 passed`

## 2026-04-22 Result Inspection 및 Product Step Failure 판정 진행 결과

- [x] `captureStdoutJson: true` product step에서 stdout JSON의 `ok:false`를 실패로 분류
- [x] 실제 SupplyScan Agent 최신 full smoke에서 register `ok:false`/`access_token_missing`을 `product_execution_failure`로 검출
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
- [x] Agent Release build 통과: `MSBuild.exe SupplyScanAgent\\SupplyScanAgent.csproj /p:Configuration=Release /p:Platform=AnyCPU`
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
- [x] SupplyScan Agent scenario에서 기존 template clone의 `%LocalAppData%\SupplyScanAgent\config.ini` 오염 여부 preflight 추가
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
- [x] README에 SupplyScan 없는 범용 demo 실행/확인 흐름 추가
- [x] Platform plan에 `canonical.command` 모델 반영
- [x] Python demo fixture가 clean Windows clone에서 portable Python을 `C:\Oslab\tools\python`에 bootstrap하도록 개선
- [x] C demo fixture가 clean Windows clone에서 TinyCC를 `C:\Oslab\tools\tcc`에 bootstrap하도록 개선
- [x] 실제 lab Python demo 재실행: bootstrap 후 `hello from python` 통과 확인
- [x] 실제 lab C demo 재실행: bootstrap 후 `hello from c` 통과 확인
- [x] Fixture 실패 stdout/stderr를 `run.json`, `result.json`, JUnit detail, HTML report, `inspect-result`에 표시
- [x] 로컬 테스트 결과: `137 passed`

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
- [x] `supplyscan.gold-lite.windows` scenario validation 통과
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
- [x] 실제 Proxmox `supplyscan.agent-status.windows` status-only smoke 통과
- [x] Real Agent status smoke 이후 cleanup 재확인: `usedInRange: <none>`
- [x] `runs/artifact-smoke/supplyscan.agent-status.windows/scan-result.json`에 `assert-result` 재평가 통과
- [x] `docs/oslab-platform-plan.md`의 오래된 VMID/CLI 예시 정리
- [x] `docs/architecture.md`가 legacy SupplyScan 전용 문서임을 명시

## 2026-04-21 Plugin Normalize 진행 결과

- [x] Core generic plugin loader 추가
- [x] `canonical.inventory` passthrough adapter 추가
- [x] `plugins/supplyscan` Python plugin 추가
- [x] `supplyscan.inventory` raw-to-canonical normalize 구현
- [x] SupplyScan common raw field mapping 구현: name, version, publisher, source, evidence path
- [x] Source normalization 구현: Registry, PE, StartMenu, Appx, MSI 등
- [x] `oslab normalize-output` CLI 추가
- [x] `oslab assert-result`가 scenario adapter normalize 후 assertion 평가하도록 변경
- [x] `artifact-smoke`가 raw output과 normalized inventory를 모두 저장하도록 변경
- [x] Fake artifact scenario adapter를 `canonical.inventory`로 변경
- [x] `validation/raw/supplyscan/sample-output.json` sample 추가
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
- [x] `supplyscan-agent-cli-failure` artifact 감지 후 product execution failure로 분류하는 기반 구현
- [x] `{AssetName}` token 구현: `OSLAB_ASSET_NAME` 우선, 없으면 `oslab-{ScenarioId}-{VmId}`
- [x] Fake Agent CLI installer 추가: `validation/artifacts/fake-agent-installer.ps1`
- [x] Fake Agent CLI scenario 추가: `scenarios/windows/fake-agent-cli-smoke.example.yaml`
- [x] 실제 SupplyScan Agent CLI scenario 초안 추가: `scenarios/windows/supplyscan-agent-cli.example.yaml`
- [x] 실제 SupplyScan Agent status-only scenario 추가: `scenarios/windows/supplyscan-agent-status.example.yaml`
- [x] 실제 Agent build output의 `logs/**`, `*.pdb`, `*.xml` exclude 설정
- [x] SupplyScan Agent CLI용 env key 안내 추가: `OSLAB_SUPPLYSCAN_SERVER_URL`, `OSLAB_SUPPLYSCAN_SABUN`
- [x] 실제 SupplyScan Agent CLI scenario report format을 `junit`, `json`, `html`로 설정
- [x] 실제 SupplyScan Agent CLI scenario에서 host-provided `OSLAB_SUPPLYSCAN_TOKEN` 요구 제거
- [x] 실제 Agent folder artifact를 archive transfer로 VM에 업로드
- [x] 실제 `SupplyScanAgent.exe cli_mode status --json` 경로를 Proxmox clone에서 실행 검증
- [x] 실제 `SupplyScanAgent.exe cli_mode register/status/scan` full smoke 시도
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
- [x] 최신 로컬 테스트 결과: `137 passed`

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
- [x] 기존 SupplyScan 전용 architecture 문서는 `docs/architecture.md`에 legacy context로 유지

### Scenario 및 Config

- [x] Windows SupplyScan smoke scenario
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
- [x] SupplyScan 없는 generic PowerShell/Python/C/fixture-state/agent-steps demo scenarios
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
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
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
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env
```

최근 실제 출력 요약:

```text
[OK] Clone smoke completed
     cloneVmId: 9102
     cloneName: oslab-supplyscan-gold-lite-windows-9102
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
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
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
     cloneName: oslab-supplyscan-gold-lite-windows-9102
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
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
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

- [x] `validation/fixtures/windows/gold-lite.ps1` upload
- [x] Guest 안에서 fixture script 실행
- [x] `C:\Oslab\expected_inventory.json` collect
- [x] Folder artifact upload
- [x] Folder artifact exclude pattern 지원: `artifact.exclude`
- [x] Folder artifact archive transfer 지원: `artifact.transfer: archive`
- [x] 대형 QGA upload chunking 구현
- [x] 대형 QGA upload progress callback 구현
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

### SupplyScan Plugin

- [x] `plugins/supplyscan` package
- [x] Raw SupplyScan JSON parser
- [x] Canonical inventory model writer
- [x] Evidence normalization
- [x] Source normalization
- [x] Version/publisher/path mapping
- [x] Plugin metadata
- [x] 실제 SupplyScan scan output으로 adapter 호환성 검증: 이전 scan output에서 4 records normalize
- [ ] SupplyScan output schema가 확정되면 strict mode 추가

### SupplyScan Agent CLI 연동

- [x] Agent 쪽 CLI 자동화 문서 확인: `agent-windows/docs/13-agent-cli-automation.md`
- [x] CLI mode 요구사항을 `docs/oslab-platform-plan.md`에 반영
- [x] `register --json` 실행 step 지원
- [x] `status --remote --json` 실행 step 지원
- [x] `scan --wait --output --json` 실행 step 지원
- [x] `--access-token`용 command template secret render/redaction 기반 구현
- [x] Scenario/env에서 secret 값을 resolve하는 product step 구현
- [x] 실제 SupplyScan Agent full smoke scenario는 host token 없이 sabun 기반 register/login 흐름으로 변경
- [x] Product step stdout JSON의 `ok:false`를 실패로 분류
- [ ] 선택 경로: `--access-token-env`용 guest env injection 구현
- [x] `OSLAB_ASSET_NAME` 또는 `oslab-{RunId}-{VmId}` asset name token 구현
- [x] `requireAdministrator` manifest가 QGA 실행 컨텍스트에서 status-only smoke 기준 문제 없는지 검증
- [x] 실제 `SupplyScanAgent.exe cli_mode status --json`를 Proxmox clone에서 실행 검증
- [ ] `requireAdministrator` manifest가 WinRM 실행 컨텍스트에서 문제 없는지 검증
- [x] 실제 `SupplyScanAgent.exe cli_mode register/status/scan`를 Proxmox clone에서 실행하고 register 계약 실패를 검출
- [x] Agent 수정 후 실제 `SupplyScanAgent.exe cli_mode register/status/scan` 성공 경로 검증
- [x] CLI stdout single JSON artifact 저장: `product-steps.json`
- [x] CLI stderr progress/debug 기본 저장: `product-steps.json`
- [x] `supplyscan-agent-cli-failure` artifact를 `product_execution_failure`로 분류
- [x] CLI stdout/stderr sidecar log 저장
- [x] Windows template에서 기존 `%LocalAppData%\SupplyScanAgent\config.ini` 오염 여부 preflight

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
- [ ] `file.exists`
- [ ] `file.notExists`
- [ ] `directory.exists`
- [ ] `service.exists`
- [ ] `process.exists`
- [ ] `package.exists`
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
- [ ] Range 안의 오래된 `oslab-*` VM 제거
- [ ] Stale VM report
- [ ] Cleanup dry-run mode
- [ ] Cleanup confirmation/force flag

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
uv run oslab validate-scenario --scenario scenarios/windows/supplyscan-gold-lite.yaml

uv run oslab preflight `
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --provider-resource-check
```

Clone을 만들고 삭제:

```powershell
uv run oslab clone-smoke `
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env
```

Clone을 만들고 start/stop/delete:

```powershell
uv run oslab boot-smoke `
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env
```

Clone을 만들고 Windows guest readiness 확인 후 삭제:

```powershell
uv run oslab guest-preflight `
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env
```

Clone을 만들고 fixture 실행 및 expected output 수집 후 삭제:

```powershell
uv run oslab fixture-smoke `
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
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
$env:OSLAB_FAKE_SUPPLYSCAN_TOKEN="fake-token-for-oslab"
uv run oslab artifact-smoke `
  --scenario scenarios/windows/fake-agent-cli-smoke.example.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/fake-agent-installer.ps1
```

SupplyScan raw sample을 canonical inventory로 normalize:

```powershell
uv run oslab normalize-output `
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
  --input-json validation/raw/supplyscan/sample-output.json `
  --output-json runs\normalize-smoke\supplyscan.inventory.json
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
  --scenario scenarios/windows/supplyscan-gold-lite.yaml `
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

1. Inventory analysis를 baseline diff/expected inventory 비교까지 확장
2. `inspect-result --latest`, `inspect-result --open-html` 같은 결과 확인 편의 옵션 추가
3. `--keep-vm-on-failure`와 stale VM metadata 구현
4. Provider/guest diagnostic log artifact 저장
5. Known app baseline 확인
6. WinRM 실행 컨텍스트에서 `requireAdministrator` manifest 검증
7. CI example에서 `guest-preflight`/`fixture-smoke`/`artifact-smoke`/`run` 단계 정리
8. Linux SSH fixture/artifact smoke로 확장
