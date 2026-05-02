# oslab Documentation

Language: English | [한국어](index.ko.md)

This is the public documentation map for `oslab`.

README:

- [English README](../README.md)
- [Korean README](../README.ko.md)

## Start Here

| Document | Purpose |
| --- | --- |
| [Getting Started](getting-started.md) | Run the generic demos in a Proxmox Windows VM |
| [Demo Catalog](demos.md) | Public demo scenarios and what each one teaches |
| [Adoption Guide](adoption-guide.md) | Adapt the demos to your own product artifact |
| [Concepts](concepts.md) | Scenario, provider, guest channel, fixture, artifact, adapter, assertion, report |
| [Scenario Authoring](scenarios.md) | YAML contract and generic examples |
| [Fixture Authoring](fixtures.md) | Guest setup script rules, evidence manifests, and fixture debugging |
| [Validation And JUnit](validation.md) | Validation ladder, smoke commands, JUnit status, and CI contract |
| [Proxmox Connection Guide](proxmox-connection.md) | API token, template, QEMU Guest Agent, preflight |
| [Reports And Results](reports.md) | `runs/<run-id>` layout, JUnit/JSON/HTML, progress logs |
| [Web Dashboard](web-dashboard.md) | LAN/team dashboard for wrapping CLI execution and browsing results |
| [Web Dashboard Server Guide](web-dashboard-server.md) | Start API/Web servers, configure LAN access, and troubleshoot local dashboard runtime |

## Design And Status

| Document | Purpose |
| --- | --- |
| [Platform Plan](oslab-platform-plan.md) | Architecture and longer-term platform direction |
| [Expert Review](oslab-expert-review.md) | Pre-implementation architecture review record |
| [Developer Working Docs](devs/README.md) | Internal working docs, implementation checklist, and maintainer task tracking |
| [GitHub Release Checklist](github-release-checklist.md) | First public release readiness checks |

The implementation checklist is useful for maintainers, but it is an internal working log, not a first-read public guide.

Product-specific notes should live outside this public first-read map. The core platform should remain product-neutral.
