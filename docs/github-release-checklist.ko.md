# GitHub 공개 체크리스트

언어: [English](github-release-checklist.md) | 한국어

이 문서는 `oslab`을 처음 GitHub에 공개하기 전에 확인할 항목입니다.

## 공개 포지셔닝

- [x] `README.md`는 private product 중심이 아니라 generic OS/VM integration test platform 중심으로 설명한다.
- [x] `docs/oslab-platform-plan.md`는 public generic platform plan으로 정리한다.
- [x] 첫 실행 예시는 generic demo suite를 사용한다.
- [x] Product-specific 관련 내용은 product-owned/private docs로 분리한다.
- [x] 기존 product-specific 중심 platform plan은 private/product-owned docs에 보관한다.
- [ ] 공개 대상 Markdown과 미디어에서 로컬 lab run id, 실제 Proxmox IP, 실제 node 이름을 모두 제거했는지 최종 감사한다.

## 온보딩

- [x] 초기 설치 명령을 제공한다.
- [x] `config/oslab.local.example.yaml`과 `config/oslab.local.example.env` 복사 흐름을 설명한다.
- [x] Proxmox API token 생성 위치와 token id 형식을 설명한다.
- [x] Proxmox token은 lab demo 기준이며 production/shared cluster 전 least-privilege 검토가 필요하다고 명시한다.
- [x] staged preflight 흐름을 제공한다.
- [x] PowerShell/Python/C demo 실행 명령과 demo catalog를 제공한다.
- [x] `runs/<run-id>/` 결과 확인 방법을 설명한다.
- [x] JUnit/JSON/HTML report의 용도를 설명한다.
- [x] Stale VM/VMID range 수동 복구 runbook을 제공한다.
- [x] CI에서 실패 시에도 `runs/**` artifact를 보존하는 pattern을 설명한다.
- [x] README를 30초 개요, 소개 애니메이션, Dashboard → 10단계 workflow → 실제 Proxmox·Windows → cleanup → Results를 담은 단일 step-by-step 영상, 빠른 시작, 현재 지원 범위, 상세 문서 순서로 정리한다.
- [x] 한국어와 영어 README의 핵심 메시지, 명령과 지원 범위를 맞춘다.
- [x] `scripts/check-doc-links.ps1`로 README 링크, 언어 전환 링크, 공개 영문·한국어 문서 14쌍을 검증한다.

## 저장소 위생

- [x] `config/oslab.local.yaml`과 `config/oslab.local.env`는 ignore 대상이다.
- [x] `runs/`는 ignore 대상이다.
- [x] `validation/artifacts/` 아래의 demo artifact 파일은 ignore하지 않는다.
- [x] Example env 파일에는 실제 secret을 넣지 않는다.
- [x] 개발/브라우저/authoring smoke 중 생성되는 timestamp 더미 산출물은 ignore 대상이다.
- [x] 공개 repo에 포함하면 안 되는 product-specific overlay는 `private/`, `*.local.*`, `*.private.yaml` 계열로 분리한다.
- [x] README 미디어는 `docs/media/`에 추적하고 재생성 절차를 `docs/media/DEMO_SCRIPT.md`에 기록한다.
- [x] 소개·워크플로우·Dashboard 데모는 고정 fixture만 사용한다.
- [x] Dashboard 캡처에서 service worker를 차단하고 HTTP·WebSocket을 허용 목록 기반으로 차단하는지 실제 Chromium/Playwright 재촬영으로 검증한다.
- [x] 실제 lab 영상은 전용 run만 촬영하고 resource tree, node, 계정, IP, 다른 작업 내역을 crop한 뒤 촬영용 VM을 정리한다.
- [x] 실제 lab 입력 네 장과 두 run evidence의 SHA-256, `sameRun`·`guestPowerShellMatchesRun`·`sensitiveRegionsReviewed`·`cleanupVerified`, cleanup의 `resourceAbsent`를 `source-approval.json`으로 다시 검증한다.
- [x] 실제 lab 최종 MP4·GIF·poster hash, private run evidence hash, 실행 요약, `cleanup.resourceAbsent`, `privacy.manualPublicFrameReview`를 공개 attestation과 대조한다.
- [x] 단일 step-by-step 영상에 Dashboard fixture·explainer fixture·별도 실제 촬영·fixture Results 경계를 source badge로 표시하고, title/lower-third·source/output hash·11개 EDL·10개 전환·cleanup 상속·독립 시각 검수를 별도 attestation에 기록한다.
- [ ] `config/public-release-blocklist.local.txt`에 사내용 product marker와 private domain marker를 추가한다.
- [x] `scripts/check-public-release.ps1 -IncludeUntracked`로 tracked/untracked 기본 공개 차단 marker와 더미 산출물을 확인한다. (local private marker blocklist 추가는 별도 미완료)
- [ ] 수정된 `apps/api/prisma/prisma/dev.db`를 공개 commit에서 제외하고, 세션 token·password hash·실행 메타데이터가 없는 배포용 fixture DB로 교체한다.
- [ ] 최종 commit 전에 secret scan을 한 번 더 실행한다.

## 검증

- [x] Demo scenario schema validation을 통과한다.
- [ ] Public candidate에서 local unit test suite를 다시 통과시킨다. (제거된 product-specific scenario 참조 테스트 정리 필요)
- [ ] Local private marker blocklist를 포함해 public release audit script를 통과한다.
- [ ] GitHub Actions workflow를 추가한다.
- [ ] README에 CI badge를 추가한다.

## 첫 공개 배포의 알려진 제한

- Windows/Proxmox/QEMU Guest Agent 경로가 현재 구현된 경로다.
- Linux 지원은 목표로 문서화되어 있지만 첫 번째 완성 구현 경로는 아니다.
- Config의 WinRM/SSH credential은 향후 guest channel을 위해 예약되어 있다.
- Production cluster에 사용하기 전에 Proxmox least-privilege role 지침을 더 엄격하게 다듬어야 한다.
