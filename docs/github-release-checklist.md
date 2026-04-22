# GitHub Release Checklist

이 문서는 `oslab`을 처음 GitHub에 공개하기 전에 확인할 항목입니다.

## Public Positioning

- [x] `README.md`는 private product 중심이 아니라 generic OS/VM integration test platform 중심으로 설명한다.
- [x] `docs/oslab-platform-plan.md`는 public generic platform plan으로 정리한다.
- [x] 첫 실행 예시는 generic demo suite를 사용한다.
- [x] Product-specific 관련 내용은 product-owned/private docs로 분리한다.
- [x] 기존 product-specific 중심 platform plan은 private/product-owned docs에 보관한다.
- [x] 로컬 lab run id, 실제 Proxmox IP, 실제 node 이름은 공개 문서에 남기지 않는다.

## Onboarding

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

## Repository Hygiene

- [x] `config/oslab.local.yaml`과 `config/oslab.local.env`는 ignore 대상이다.
- [x] `runs/`는 ignore 대상이다.
- [x] Demo artifact files under `validation/artifacts/` are not ignored.
- [x] Example env files do not contain real secrets.
- [ ] 최종 commit 전에 secret scan을 한 번 더 실행한다.

## Validation

- [x] Demo scenario schema validation passes.
- [x] Local unit test suite passes.
- [ ] GitHub Actions workflow를 추가한다.
- [ ] README에 CI badge를 추가한다.

## Known Limits For First Release

- Windows/Proxmox/QEMU Guest Agent path is the implemented path.
- Linux support is documented as a target, but not the first complete implementation path.
- WinRM/SSH credentials in config are reserved for future guest channels.
- Proxmox least-privilege role guidance should be tightened before production cluster use.
