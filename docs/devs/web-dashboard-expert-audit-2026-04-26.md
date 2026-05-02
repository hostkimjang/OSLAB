# Web Dashboard Expert Audit - 2026-04-26

이번 감사는 실제 브라우저 조작, UX/QA/제품 자동화 전문가 관점, 그리고 기존 체크리스트를 함께 사용해 진행했다.

## Browser Evidence

실제 Web UI에서 다음 흐름을 실행했다.

```text
login -> language switch -> dashboard -> scenario editor -> fixture editor -> suite builder
-> run launcher -> skeleton scenario run -> results -> mobile dashboard/run/results
```

결과:

- Run: `20260426-042038-demo-powershell-system-windows`
- Job: `cmoeq5g9g0009sm0s1x4n38lk`
- Scenario: `scenarios/windows/demo-powershell-system.example.yaml`
- Command: `uv run oslab run --scenario scenarios/windows/demo-powershell-system.example.yaml --config config/oslab.local.yaml --env-file config/oslab.local.env --boot-timeout-seconds 300 --guest-timeout-seconds 300 --command-timeout-seconds 420 --poll-interval-seconds 5`
- Result: `passed`
- Browser console issues: `0`
- Network issues: `0`
- Report: `output/web-dashboard/full-browser-audit.json`

Main screenshots:

- `output/web-dashboard/full-audit-01-login.png`
- `output/web-dashboard/full-audit-02-dashboard-home.png`
- `output/web-dashboard/full-audit-06-scenario-diff-preview.png`
- `output/web-dashboard/full-audit-10-run-readiness.png`
- `output/web-dashboard/full-audit-12-run-finished-console.png`
- `output/web-dashboard/full-audit-13-results-detail.png`
- `output/web-dashboard/full-audit-14-mobile-dashboard.png`
- `output/web-dashboard/full-audit-15-mobile-run.png`
- `output/web-dashboard/full-audit-16-mobile-results.png`

After the responsive/accessibility fix:

- `output/web-dashboard/full-browser-audit-mobile-fix.json`
- `output/web-dashboard/full-audit-fix-mobile-dashboard.png`
- `output/web-dashboard/full-audit-fix-mobile-run.png`
- `output/web-dashboard/full-audit-fix-mobile-results.png`

## Expert Findings

### UX/Design

- Mobile navigation at `390x844` needed a real horizontal tab bar. The old layout allowed Korean labels to wrap into unreadable fragments.
- Run readiness was too compressed when rendered as five equal columns inside a narrow run panel.
- Run Launcher should eventually become a staged flow: target, artifact, lab, options, review and run.
- Authoring should evolve toward explicit `Form`, `YAML`, and `Diff` modes instead of stacking every surface at once.
- Results Explorer is the strongest current surface, but it needs failure-first filters and lineage.

### QA/Browser

- Safe flows should be tested every dashboard change: auth, language switch, read-only editor gate, diff preview, run readiness, skeleton run, results detail, and responsive viewports.
- Destructive actions need separate handling. Cleanup was intentionally not executed in this audit because it can destroy lab VMs.
- Required evidence should include screenshots, JSON audit logs, console error count, network error count, and run IDs.
- Prior regression to keep watching: skeleton results must not emit noisy missing `logs/progress.jsonl` console errors.

### Product/Automation

- The dashboard should make the lab model explicit: OS template axis, OS state/profile axis, artifact, evidence, cleanup, and capacity.
- Add a Matrix Run Planner for `OS template x OS profile`.
- Add cleanup dry-run before destroy, with VMID/name/age/status/owning run.
- Add Proxmox/tunnel diagnostics showing stable User-Agent policy, `/api2/json` reachability, WAF hints, QGA, template flag, and VMID range.
- Add evidence checklist and result lineage: job -> suite -> scenario -> VMID -> template -> profile -> artifact -> cleanup.

## Changes Applied In This Round

- `LanguageSwitch` now exposes selected state with `aria-pressed`.
- Primary navigation now has an accessible landmark label.
- Navigation buttons include `title` text for compact/mobile views.
- Global `:focus-visible` styles were added for keyboard navigation.
- Run readiness now uses responsive `auto-fit` tracks instead of fixed five columns.
- Mobile shell now uses a horizontal scroll tab bar, wrapped top actions, visible page scrolling, and a one-column readiness layout.
- Results detail now includes an evidence checklist backed by `GET /api/runs/:runId/evidence`.
- The evidence checklist exposes `run.json`, timeline, raw/normalized output, reports, and cleanup state as present, missing, not applicable, or contract gap.

## Priority Roadmap

P0:

- Matrix Run Planner.
- Cleanup dry-run and explicit confirmation.
- Proxmox/tunnel readiness diagnostics.
- Evidence checklist in Results Explorer.

P1:

- Guided demo-run lane.
- Result lineage and baseline/profile diff.
- Failure-first result filters.
- Shared versioned run/evidence schemas.

P2:

- Profile authoring helpers for EXE/MSI, winget, Chocolatey, Appx/MSIX.
- Optional TRX preview/download for C# validation.
- Full authoring mode split: form, YAML, diff.
