# oslab Expert Review

## Review Method

이 문서는 `docs/oslab-platform-plan.md`를 기준으로 다섯 개의 독립적인 전문가 관점에서 구현 가능성, 구조 일관성, 문서 품질, 시각화 흐름을 검토한 기록입니다.

실제 외부 subagent를 실행한 것은 아니며, 구현 전에 필요한 판단을 빠뜨리지 않기 위해 structured subagent-style panel로 작성했습니다.

각 관점은 다음 항목을 확인했습니다.

- Implementability
- Hidden coupling
- Missing interfaces
- OS assumptions
- Error handling
- Testability
- Documentation clarity
- Diagram correctness

각 review section은 다음 구조를 따릅니다.

- Verdict
- Strengths
- Risks
- Blocking issues
- Required changes
- Optional improvements
- Implementation concern
- Documentation/diagram concern

## Expert 1: Platform Architect

### Focus

- Abstraction boundaries
- Core/plugin separation
- Provider leakage
- Scenario schema stability
- Long-term extensibility

### Verdict

`Ready With Changes`

Core 방향은 타당합니다. 다만 provider async task, VMID allocation, command model, plugin failure semantics가 명시되지 않으면 구현 중 core에 Proxmox/product-specific 세부사항이 새어 들어갈 수 있습니다. 이 리뷰의 high-priority 변경은 `docs/oslab-platform-plan.md`에 반영되었습니다.

### Strengths

1. product-specific을 첫 plugin으로 두고 core platform에서 분리한 결정이 장기 확장성에 맞습니다.
2. Provider, Guest Channel, Artifact, Plugin, Assertion, Report가 서로 다른 책임으로 분해되어 있습니다.
3. YAML scenario를 public contract로 둔 것이 CI와 local 실행을 통합하기 좋습니다.
4. Canonical Result Model을 둔 덕분에 제품별 raw output 변화가 assertion engine에 직접 영향을 주지 않습니다.
5. JUnit/JSON/HTML report 조합은 CI, automation, human review를 동시에 지원합니다.

### Risks

1. Scenario schema가 너무 빨리 넓어지면 MVP 구현 전부터 schema migration 부담이 생길 수 있습니다.
2. Provider interface에 Proxmox-specific concepts가 섞이면 libvirt/cloud provider 확장이 어려워집니다.
3. Plugin protocol을 Python plugin과 executable plugin 모두 지원하면 MVP 구현량이 증가합니다.
4. Artifact model이 installer와 folder를 동시에 지원하므로 command template 검증이 부족하면 실행 실패가 많아질 수 있습니다.
5. Linux를 설계만 하고 구현하지 않으면 Windows-only assumption이 늦게 발견될 수 있습니다.

### Blocking Issues

No blocker.

### Required Changes

| Change | Severity | Status |
| --- | --- | --- |
| Proxmox async task handling을 provider contract에 명시 | High | Reflected |
| VMID allocation과 concurrency rule 명시 | High | Reflected |
| Command template에 shell과 token rule 명시 | High | Reflected |
| Plugin failure와 assertion failure를 구분 | Medium | Reflected |

### Optional Improvements

- Scenario schema를 JSON Schema 또는 Pydantic model로 문서화하고 테스트에 포함합니다.
- Provider capability discovery를 추가해 provider별 지원 기능을 runtime에 확인합니다.
- Plugin registry manifest를 추가해 plugin metadata, version, supported output kind를 명시합니다.

### Implementation Concern

Python plugin과 executable plugin을 동시에 MVP에 넣으면 loader, error handling, test fixture가 늘어납니다. 구현 순서는 Python plugin을 먼저 완료하고 executable plugin은 protocol skeleton과 fake test부터 추가하는 것이 안전합니다.

### Documentation/Diagram Concern

High-level architecture diagram은 product command executor에서 raw output으로 이어지는 흐름은 명확하지만, artifact install/copy 실패가 failure taxonomy로 어떻게 이어지는지 처음에는 약했습니다. Platform plan에 artifact failure taxonomy와 report layout을 명확히 추가해 해소했습니다.

## Expert 2: Windows And Proxmox Engineer

### Focus

- Proxmox API feasibility
- Windows clone lifecycle
- QEMU Guest Agent behavior
- WinRM fallback complexity
- Windows path/PowerShell quoting issues

### Verdict

`Ready With Changes`

Proxmox + Windows VM 기반 MVP는 구현 가능합니다. 핵심 위험은 Proxmox API의 async task polling, QEMU Guest Agent file/exec behavior, PowerShell quoting, WinRM fallback credential/network readiness입니다. 이 위험들은 platform plan에 구현 규칙으로 반영되었습니다.

### Strengths

1. Ephemeral clone 전략은 Windows test pollution을 줄이고 재현성을 높입니다.
2. QEMU Guest Agent를 Windows primary channel로 둔 것은 Proxmox 내부 제어 흐름과 잘 맞습니다.
3. WinRM fallback을 둔 덕분에 QEMU Agent exec/file transfer가 불안정할 때 복구 경로가 있습니다.
4. `--keep-vm-on-failure` 옵션은 Windows fixture나 product 실행 실패를 조사할 때 필요합니다.
5. Cleanup failure를 별도 failure class로 둔 것이 stale clone 운영에 유리합니다.

### Risks

1. Proxmox clone/start/destroy API는 task id를 반환하므로 polling 없이 다음 단계로 넘어가면 race condition이 생깁니다.
2. QEMU Guest Agent file transfer는 큰 directory artifact에서 느리거나 제한적일 수 있습니다.
3. Windows path escaping과 PowerShell command quoting은 YAML, Python string, remote shell을 거치며 깨질 수 있습니다.
4. WinRM fallback은 방화벽, network profile, credential policy에 따라 실패할 수 있습니다.
5. Windows template에 QEMU Guest Agent service가 설치되어 있어도 Proxmox VM option에서 agent가 꺼져 있으면 probe가 실패합니다.

### Blocking Issues

No blocker.

### Required Changes

| Change | Severity | Status |
| --- | --- | --- |
| Proxmox async task polling 명시 | High | Reflected |
| QEMU Agent와 WinRM probe order 명시 | High | Reflected |
| Command template shell 지정 필수화 | High | Reflected |
| Cleanup stale VM metadata 기록 명시 | Medium | Reflected |

### Optional Improvements

- Windows artifact upload는 큰 directory일 경우 zip upload + guest unzip 전략을 검토합니다.
- WinRM fallback에는 `Test-WSMan` equivalent probe와 credential validation step을 둡니다.
- Template validation command를 별도 `oslab preflight --template-only`로 분리할 수 있습니다.

### Implementation Concern

QEMU Guest Agent를 통해 PowerShell command를 실행할 때 stdout/stderr와 exit code를 안정적으로 얻는 wrapper가 필요합니다. Direct command execution 대신 guest 안에 temporary script를 쓰고, 결과 JSON을 파일로 남긴 뒤 download하는 방식이 더 안정적일 수 있습니다.

### Documentation/Diagram Concern

Guest Channel Selection Flow는 Windows fallback 순서를 잘 보여줍니다. 다만 QEMU Agent file transfer와 command execution이 같은 capability라고 가정하면 안 됩니다. 구현 문서에는 channel capability matrix가 필요하며, platform plan에 channel table과 result shape를 추가해 보완했습니다.

## Expert 3: Linux And SSH Engineer

### Focus

- Linux future support
- SSH-first design
- Shell fixture compatibility
- Path and permission differences
- Whether scenario schema is truly cross-OS

### Verdict

`Ready With Changes`

Linux를 MVP에서 실제 구현하지 않더라도 schema가 Linux를 막지 않는지 확인하는 것은 중요합니다. 현재 설계는 OS-specific path와 shell을 scenario에 분리할 수 있으므로 확장 가능합니다. 다만 Windows path가 canonical examples에만 머무르고 core model에는 들어가지 않아야 합니다.

### Strengths

1. Linux guest order를 SSH -> QEMU Agent로 둔 것은 일반적인 Linux automation과 잘 맞습니다.
2. Fixture type을 `powershell`과 `shell`로 나눈 구조는 cross-OS 확장에 유리합니다.
3. `file.exists`, `command.exitCode`, `process.exists`, `package.exists` 같은 built-in assertions는 Linux에서도 자연스럽게 적용됩니다.
4. Scenario YAML이 OS family를 명시하므로 OS별 default behavior를 분기할 수 있습니다.
5. Canonical result model이 Windows registry에만 묶이지 않고 evidence metadata를 일반화할 여지가 있습니다.

### Risks

1. Linux 구현을 뒤로 미루면 path separator, permission, sudo, package manager 차이를 늦게 발견할 수 있습니다.
2. SSH key management와 known_hosts handling이 명시되지 않으면 CI에서 불안정해질 수 있습니다.
3. Shell fixture가 idempotent하지 않으면 reusable debug VM이나 preserved VM에서 재실행 문제가 생깁니다.
4. `service.exists`는 Windows service와 Linux systemd service를 같은 assertion으로 표현할 때 adapter logic이 필요합니다.
5. QEMU Agent fallback for Linux가 installed/enabled 상태인지 template마다 다를 수 있습니다.

### Blocking Issues

No blocker.

### Required Changes

| Change | Severity | Status |
| --- | --- | --- |
| Linux example scenario 추가 | High | Reflected |
| Scenario command에 shell 명시 | High | Reflected |
| Linux preflight design checks 추가 | Medium | Reflected |
| Built-in assertions가 OS별 resolver를 가질 수 있음을 문서화 | Medium | Partially Reflected |

### Optional Improvements

- Linux package assertions는 provider-independent package resolver interface로 분리합니다.
- SSH known_hosts policy를 config에 추가합니다.
- `requiresPrivilege` field를 fixture/assertion에 추가해 sudo/admin 필요 여부를 명시합니다.

### Implementation Concern

Linux SSH implementation은 단순 command execution뿐 아니라 upload/download를 포함해야 합니다. Python dependency 선택 시 Paramiko를 쓸지 system `ssh/scp`를 호출할지 결정해야 합니다. MVP가 Windows real implementation이면 Linux SSH는 interface와 fake tests까지만 두는 것이 적절합니다.

### Documentation/Diagram Concern

Linux path와 Windows path가 scenario examples에 섞여 있으므로, core documentation에서 path는 opaque remote path string으로 취급한다고 명확히 해야 합니다. Platform plan은 OS별 examples를 분리해 이 문제를 완화했습니다.

## Expert 4: QA And Test Automation Engineer

### Focus

- Assertion model
- Fixture reproducibility
- Failure classification
- Report usefulness
- Testability without real VMs

### Verdict

`Ready With Changes`

테스트 플랫폼 자체를 테스트할 수 있는 구조가 중요합니다. Fake provider와 fake guest channel을 이용한 integration tests가 없으면 실제 Proxmox lab이 없을 때 core regression을 잡기 어렵습니다. 이 요구는 platform plan의 test plan에 반영되었습니다.

### Strengths

1. Failure taxonomy가 setup, execution, validation, cleanup을 분리하므로 실패 원인 분석이 쉽습니다.
2. Assertion result model이 `passed`, `failed`, `skipped`, `error`를 구분합니다.
3. JUnit/JSON/HTML report output은 CI와 사람이 모두 사용할 수 있습니다.
4. Scenario validation command가 있으면 VM을 만들기 전에 많은 오류를 잡을 수 있습니다.
5. product-specific raw output을 canonical model로 normalize하면 assertion tests를 product-independent하게 작성할 수 있습니다.

### Risks

1. Real VM integration test만 있으면 개발 속도가 느리고 flaky failure가 많아질 수 있습니다.
2. Fixture가 idempotent하지 않으면 실패 재현이 어렵습니다.
3. Product execution failure와 assertion failure가 섞이면 제품 crash와 product behavior mismatch를 구분하기 어렵습니다.
4. HTML report가 JSON report와 다른 source of truth를 가지면 report 불일치가 생길 수 있습니다.
5. Optional assertion과 required assertion의 severity rule이 없으면 CI gate semantics가 모호해질 수 있습니다.

### Blocking Issues

No blocker.

### Required Changes

| Change | Severity | Status |
| --- | --- | --- |
| Fake provider/guest 기반 integration test plan 추가 | High | Reflected |
| JUnit mapping 명시 | High | Reflected |
| Assertion status와 failure class 구분 명시 | Medium | Reflected |
| Report output layout 구체화 | Medium | Reflected |

### Optional Improvements

- Assertion severity를 `error`, `warning`, `info`로 명시하고 CI fail 조건을 문서화합니다.
- Fixture는 `apply`, `verify`, `cleanup` lifecycle로 확장할 수 있습니다.
- Golden JSON fixtures를 두어 report writer snapshot tests를 추가합니다.

### Implementation Concern

Report writer는 assertion engine output을 그대로 소비해야 합니다. HTML report가 자체적으로 pass/fail을 다시 계산하면 JSON/JUnit/HTML 간 불일치가 생깁니다.

### Documentation/Diagram Concern

Failure Taxonomy diagram은 단계별 failure를 보여주지만 `guest_channel_failure`가 initial diagram에서는 노드로 직접 연결되지 않았습니다. Platform plan에는 Guest Channel Selection Flow와 failure table을 추가해 `guest_channel_failure`를 명시했습니다.

## Expert 5: DevOps And CI Engineer

### Focus

- Local/CI parity
- Secret handling
- Artifact contract
- JUnit output
- Runner requirements

### Verdict

`Ready With Changes`

CI 중립 CLI를 먼저 만들고 GitLab/GitHub는 thin wrapper로 두는 방향은 좋습니다. 다만 secret source, artifact path contract, concurrency, output artifact layout을 명확히 해야 합니다. 해당 변경은 platform plan에 반영되었습니다.

### Strengths

1. Local과 CI가 같은 `oslab run` command를 쓰는 구조는 운영 drift를 줄입니다.
2. JUnit XML output은 GitLab/GitHub/Jenkins 등에서 널리 소비할 수 있습니다.
3. Secret을 scenario file이 아니라 environment variable에서 읽는 정책이 적절합니다.
4. Run output layout이 고정되어 CI artifact upload rule을 단순하게 만들 수 있습니다.
5. `inspect-result` command는 CI 실패 후 local 분석에 도움이 됩니다.

### Risks

1. Parallel CI jobs가 같은 VMID range를 쓰면 clone collision이 발생할 수 있습니다.
2. Artifact path가 runner local path인지, downloaded CI artifact path인지 명확하지 않으면 실행 실패가 생깁니다.
3. Proxmox API token permission scope가 너무 넓으면 lab cluster 운영 위험이 있습니다.
4. `verifyTls: false`가 예시로 남으면 실제 운영에서도 그대로 복사될 수 있습니다.
5. Cleanup failure가 발생한 뒤 stale VM cleanup process가 없으면 VMID range가 고갈될 수 있습니다.

### Blocking Issues

No blocker.

### Required Changes

| Change | Severity | Status |
| --- | --- | --- |
| VMID allocation/concurrency rule 명시 | High | Reflected |
| Secret values are env-only policy 명시 | High | Reflected |
| Run output layout과 report files 명시 | Medium | Reflected |
| Future stale cleanup command 명시 | Medium | Reflected |

### Optional Improvements

- GitLab CI example에는 `resource_group`을 사용해 VMID range collision을 줄입니다.
- GitHub Actions example에는 `concurrency` group을 사용합니다.
- Proxmox token permission example을 docs에 추가합니다.
- CI artifact upload pattern은 `runs/**`로 통일합니다.

### Implementation Concern

CI wrapper가 platform behavior를 새로 정의하면 local/CI parity가 깨집니다. CI는 artifact 준비와 secret 주입만 담당하고, clone/run/report/cleanup은 반드시 `oslab` CLI가 담당해야 합니다.

### Documentation/Diagram Concern

Architecture diagram은 CI를 직접 그리지 않습니다. 이는 platform-neutral 방향에는 맞지만, 운영자가 runner requirement를 놓칠 수 있습니다. 별도 CI examples document 또는 platform plan의 future CI section이 필요합니다.

## Diagram Validation

| Rule | Result | Notes |
| --- | --- | --- |
| Every major component in the diagram has a corresponding section | Pass | CLI, runner, provider, guest, fixture, artifact, plugin, assertion, reports are documented. |
| Every flow edge maps to an implementable method, command, or artifact | Pass with changes | Provider and guest APIs were clarified. |
| Product-specific logic does not appear inside core components | Pass | product-specific is plugin-only. |
| Windows-only concepts do not appear in Linux-generic flows | Pass with caution | Windows paths remain only in Windows scenario. |
| Failure nodes map to failure taxonomy | Pass with changes | `guest_channel_failure` is documented in table and channel flow. |
| Report outputs match documented run directory layout | Pass | Layout is explicit. |
| Guest channel fallback logic matches selected defaults | Pass | Windows QEMU -> WinRM, Linux SSH -> QEMU. |

## Cross-Review Issue Matrix

| Issue | Raised By | Severity | Decision | Required Change |
| --- | --- | --- | --- | --- |
| Proxmox API operations are async and need task polling | Windows/Proxmox, Platform Architect | High | Accept | Add Proxmox async task handling to provider section |
| VMID collisions can happen in local or CI parallel runs | DevOps/CI, Windows/Proxmox | High | Accept | Add VMID allocation and concurrency rules |
| Command templates can break due to shell quoting differences | Windows/Proxmox, Linux/SSH, Platform Architect | High | Accept | Require shell field and documented token set |
| Core must be testable without real Proxmox VMs | QA/Test Automation | High | Accept | Add fake provider/guest integration test plan |
| Scenario examples must prove cross-OS shape | Linux/SSH | High | Accept | Add Linux generic scenario example |
| Plugin failure and assertion failure can be confused | Platform Architect, QA/Test Automation | Medium | Accept | Define executable plugin protocol failure rules |
| JUnit semantics need setup error vs assertion failure mapping | QA/Test Automation, DevOps/CI | Medium | Accept | Add JUnit mapping table |
| Cleanup failure needs stale VM metadata | Windows/Proxmox, DevOps/CI | Medium | Accept | Require stale VM metadata in `run.json` |
| SSH key and known_hosts policy is not fully specified | Linux/SSH, DevOps/CI | Medium | Accept Later | Add when Linux execution becomes MVP implementation |
| Proxmox token permission model is not documented | DevOps/CI | Medium | Accept Later | Add security/operations doc before CI rollout |
| HTML report could diverge from JSON source of truth | QA/Test Automation | Low | Accept | State JSON is source of truth |
| Provider capability discovery is missing | Platform Architect | Low | Accept Later | Add after first provider is stable |

## Accepted Changes Reflected Back Into Platform Plan

The following accepted changes were reflected in `docs/oslab-platform-plan.md`:

| Accepted Change | Platform Plan Section |
| --- | --- |
| Proxmox async task handling | `Proxmox Async Task Handling` |
| VMID allocation and local locking | `VMID Allocation` |
| Guest channel API result shape | `Guest Channel API` |
| Guest fallback failure classification | `Guest Channel Selection Flow`, `Failure Taxonomy` |
| Preflight checks | `Preflight Contract` |
| Windows and Linux scenario examples | `Scenario YAML Contract` |
| Command shell/token rules | `Command Template Rules` |
| Artifact folder/installer behavior | `Artifact Interface` |
| Plugin protocol failure rules | `Plugin Model` |
| JUnit mapping | `JUnit Mapping` |
| Fake provider/guest test plan | `Test Plan` |
| Stale VM metadata | `Cleanup Policy`, `Report Output Layout` |

## Final Readiness Verdict

| Verdict | Meaning |
| --- | --- |
| `Ready` | Implementation can begin with no required plan changes |
| `Ready With Changes` | Apply documented changes first, then implement |
| `Not Ready` | Major architecture decisions are unresolved |

Final verdict: `Ready With Changes`

No blocker was found. High-severity issues were accepted and reflected back into the platform plan. Implementation can begin from the revised `docs/oslab-platform-plan.md`, with the understanding that Linux real execution, Proxmox permission hardening, and provider capability discovery are deferred follow-up items rather than MVP blockers.

## Implementation Gate

Before writing platform code, confirm these points from the revised plan:

- The first real lab target is Windows on Proxmox.
- Linux remains schema/design/fake-test coverage during MVP.
- product-specific remains a plugin, not a core dependency.
- CI wrappers must call the same local CLI.
- Real secrets must be provided through environment variables.
- Proxmox token permissions and runner concurrency rules must be finalized before shared CI rollout.

