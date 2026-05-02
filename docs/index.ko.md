# oslab 문서

언어: [English](index.md) | 한국어

이 문서는 `oslab`의 공개 문서 맵입니다.

README:

- [English README](../README.md)
- [Korean README](../README.ko.md)

## 먼저 읽을 문서

| 문서 | 목적 |
| --- | --- |
| [Getting Started](getting-started.ko.md) | Proxmox Windows VM에서 generic demo 실행 |
| [Demo Catalog](demos.ko.md) | 공개 demo scenario와 각 demo가 가르치는 개념 |
| [Adoption Guide](adoption-guide.ko.md) | Demo를 자신의 product artifact 테스트로 바꾸는 방법 |
| [Concepts](concepts.ko.md) | Scenario, provider, guest channel, fixture, artifact, adapter, assertion, report 개념 |
| [Scenario Authoring](scenarios.ko.md) | YAML contract와 generic example |
| [Fixture Authoring](fixtures.ko.md) | Guest setup script 규칙, evidence manifest, fixture debugging |
| [Validation And JUnit](validation.ko.md) | 검증 계층, smoke command, JUnit 구현 상태, CI contract |
| [Proxmox Connection Guide](proxmox-connection.ko.md) | API token, template, QEMU Guest Agent, preflight |
| [Reports And Results](reports.ko.md) | `runs/<run-id>` layout, JUnit/JSON/HTML, progress logs |
| [Web Dashboard](web-dashboard.ko.md) | CLI 실행과 결과 탐색을 감싸는 LAN/team dashboard |
| [Web Dashboard 서버 실행 가이드](web-dashboard-server.ko.md) | API/Web 서버 실행, LAN 접근 설정, local dashboard runtime troubleshooting |

## 설계와 상태

| 문서 | 목적 |
| --- | --- |
| [Platform Plan](oslab-platform-plan.md) | Architecture와 장기 platform 방향 |
| [Expert Review](oslab-expert-review.md) | 구현 전 architecture review 기록 |
| [Developer Working Docs](devs/README.md) | 내부 작업 문서, 구현 체크리스트, maintainer task tracking |
| [GitHub Release Checklist](github-release-checklist.md) | 첫 공개 release readiness check |

구현 체크리스트는 maintainer에게 유용하지만, 내부 작업 로그에 가깝고 새 사용자가 처음 읽을 문서는 아닙니다.

제품별 메모는 공개 first-read map 밖에 둡니다. Core platform은 product-neutral을 유지해야 합니다.
