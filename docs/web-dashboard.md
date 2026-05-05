# oslab Web Dashboard

The web dashboard is a LAN/team control surface for `oslab`. It does not replace the Python runner. It wraps the existing CLI commands, stores job history in SQLite, and keeps scenario/suite/fixture definitions as Git-friendly files.

## Architecture

```text
apps/web   Next.js dashboard
apps/api   NestJS API, local auth, job runner, file/catalog API
oslab CLI  uv run oslab run / suite-run
runs/      Existing run output layout
```

The first screen is the working dashboard: recent jobs, recent runs, scenario authoring, suite execution, live logs, and result reports.

The current source layout is now organized like this:

```text
apps/web/src/
  app/
    page.tsx                # thin entrypoint
  features/dashboard/
    DashboardPage.tsx       # stateful dashboard controller
    components/
      artifacts.tsx
      authoring.tsx
      common.tsx
      lab-status.tsx
      results.tsx
    lib/
      api.ts
      commands.ts
      formatting.ts
      result-summary.ts
      ui-state.ts
    sections/
      DashboardHome.tsx
      LoginScreens.tsx
      ResultsExplorer.tsx
    model.ts                # compatibility barrel
    defaults.ts
    i18n.ts
    types.ts

apps/api/src/
  app.module.ts
  common/guards/
  infrastructure/prisma/
  infrastructure/workspace/
  features/auth|artifacts|builder|catalog|files|jobs|lab|runs|validation/
    *.module.ts
    *.controller.ts
    dto/
    lab/proxmox-lab.client.ts  # shared Proxmox HTTP policy for Lab Status/cleanup
```

## Setup

For the full server runbook, including LAN access, production-like start commands, smoke checks, and troubleshooting, see [Web Dashboard Server Guide](web-dashboard-server.md).

Install Node dependencies:

```powershell
corepack pnpm install
```

Configure the API:

```powershell
Copy-Item apps/api/.env.example apps/api/.env
Copy-Item apps/web/.env.example apps/web/.env
```

Set at least:

```text
OSLAB_REPO_ROOT=C:/Users/kysky/Documents/gitlab/product-specific_autorun_test
OSLAB_WEB_ADMIN_USERNAME=admin
OSLAB_WEB_ADMIN_PASSWORD=<strong-password>
```

Initialize Prisma client:

```powershell
corepack pnpm prisma:generate
```

The API creates the local SQLite tables on startup when they are missing. A separate Prisma migration step is not required for the v1 development dashboard.

Run the dashboard:

```powershell
corepack pnpm dev
```

If `pnpm` is available in your PATH, `pnpm dev` also works. On Windows, `corepack pnpm ...` is safer because enabling global Corepack shims can require administrator permission.

If the Next.js dev server shows a stale runtime error after running a production build, stop `corepack pnpm dev`, remove `apps/web/.next`, and start it again.

Default URLs:

```text
API: http://127.0.0.1:3001
Web local URL: http://127.0.0.1:3000
Web bind: 0.0.0.0:3000
```

## Safety

- Scenario/suite/fixture edits are restricted to `scenarios/**`, `validation/fixtures/**`, and `validation/suites/**`.
- The authoring API enforces root and extension rules on create/write as well as read: scenarios and suites use `.yaml/.yml`, fixtures use `.ps1/.sh`, secret/env-like paths are blocked, Windows reserved device names are rejected, path segments cannot end in dot/space, control characters are rejected, and text authoring is capped at 1 MiB.
- Artifact text authoring is restricted to safe text-like files under `validation/artifacts/**`: PowerShell, shell, Python, C, C#, JSON, YAML, JavaScript, TypeScript, HTML, CSS, Markdown, Dockerfile, txt, cmd, and bat. Uploaded `.web-artifacts/**`, binary files, and directories can be selected for execution but are read-only in the dashboard.
- Artifact archive/delete uses a two-step confirmation flow. Repo artifacts under `validation/artifacts/**` are archive-first and move to `.artifact-archive/**`; only `.web-artifacts/**` and `.artifact-archive/**` can be deleted after confirmation.
- Artifact Studio never executes scripts during assist checks. Completion and diagnostics are served through the dashboard API LSP Assist surface, while checks remain static: JSON parse validation, placeholder typo detection, suspicious path hints, and destructive command pattern warnings.
- Authoring screens open files in read-only mode by default. Operators must click `Edit` before changing YAML/PowerShell content, and `Save` or `Cancel` returns the editor to read-only mode.
- Authoring screens show a save preview with changed/added/removed line counts before saving modified content.
- Authoring screens validate the current editor buffer before saving. Normal/checking states use a non-layout toast, while YAML parse errors and PowerShell parse errors stay inline and block `Save` until fixed.
- Scenario saves also run a lightweight scenario contract check before writing, so invalid `schemaVersion`, OS family, guest mode, report format, cleanup type, or missing assertions are blocked in the dashboard.
- Suite saves also run a lightweight suite contract check before writing, so empty runs, duplicate run IDs, invalid scenario paths, invalid `tier`/`allowFailure`/`enabled` shapes, and invalid `maxParallel` values are blocked in the dashboard.
- New scenario, fixture, and suite creation are create-only: the API refuses to overwrite existing authoring files.
- Opening another file with unsaved changes shows a discard confirmation.
- Env files are not readable through the web API.
- Job logs redact secret-like values loaded from the selected env file.
- Execution uses subprocesses such as `uv run oslab suite-run ...`.
- Lab cleanup is a two-step action: the API returns a dry-run candidate list and a `confirmToken`, and destructive cleanup only proceeds when the same candidate set is confirmed.
- Dashboard cleanup targets stopped/stale `oslab-*` VMs in the configured VMID range by default. Running VMs are excluded from the default UI cleanup path.
- The Web dev/start server binds to `0.0.0.0:3000`, so it listens on all interfaces of the host. Use `http://127.0.0.1:3000` locally and `http://<dashboard-host-ip>:3000` from the LAN.
- To verify live job events and large artifact uploads over LAN, the API must also be reachable from LAN. Set `OSLAB_WEB_HOST=0.0.0.0` in `apps/api/.env`, and set `OSLAB_WEB_ORIGIN` to the actual Web origin, for example `http://<dashboard-host-ip>:3000`.
- When enabling LAN access, check the OS firewall, private network range, account/password, and reverse proxy policy together.

## Current V1 Features

- Local account login.
- English/Korean language switch.
- Contextual circular `i` info tooltips on dense card/section headers and selected evidence rows, with hover, focus, click/tap, `Esc` close, and viewport-clamped overlay positioning.
  - User-facing explanations cover Scenario, Fixture, Suite, Run readiness, Suite policy, and evidence items such as `run.json` and `progress.jsonl`.
- Logout action from the main workspace.
- Read-only Lab Status view.
  - Proxmox API connectivity.
  - Proxmox requests use the same explicit `oslab/0.1.0` user agent policy as the Python provider so reverse proxies and WAFs see a stable client signature.
  - Node/template state.
  - VMID range used/free/recommended summary.
  - Running/stale `oslab-*` VMs.
- Scenario, suite, and fixture catalog browsing.
- Catalog search/filter for long scenario and fixture lists.
- Authoring file lists can collapse into a 52px rail on Scenario, Fixture, and Suite screens to give the editor body more horizontal space.
- Read-only file viewing and gated editing for allowed YAML/PowerShell files.
- Save preview for scenario/suite/fixture edits opens as an approximately 90% viewport modal before the file is written; the editor keeps only a compact changed/added/removed summary.
- Save-before syntax checks for YAML scenario/suite files and PowerShell fixture files.
- Scenario and suite validation.
- New scenario creation from Windows smoke, Linux smoke, or product-specific smoke templates.
- New fixture creation from Windows PowerShell or Linux shell starter templates under `validation/fixtures/**`.
- New suite creation from smoke or matrix starter templates under `validation/suites/**`; the created file opens in edit mode and loads the Suite Builder.
- Scenario and suite launch using local artifact paths.
- Separate single-scenario and suite-only flows through explicit `None` options.
- Single scenario runs can omit artifact path to run the `oslab run` skeleton mode.
- Artifact selection from the `validation/artifacts` catalog.
- Scenario-aware recommended artifact chips based on the selected scenario and available artifact catalog.
- Direct artifact path input through the `Direct file/folder path` option, including absolute server-local directories such as a product `bin/Release` folder.
- Browser artifact upload to `.web-artifacts/`, with uploaded files immediately selected for the current run.
- Browser folder selection for directory artifacts: selected folders are copied under `.web-artifacts/<timestamp>-<folder>/` and that server-local directory is selected for the current run.
- Large browser uploads are sent directly to the API server on `:3001` instead of through the Next rewrite proxy, avoiding multipart proxy failures after the browser reaches 100%.
- Upload status feedback for direct uploads, including selected/uploading/in-use/failed state, file count, byte progress, and the saved `.web-artifacts/...` path.
- Artifact Studio as a dedicated navigation surface and from the Run Launcher artifact step.
  - Browses `validation/artifacts/**`, `.web-artifacts/**`, and `.artifact-archive/**` together with source, file/directory type, text/binary type, size, file count, modified time, and SHA-256 file hash metadata.
  - Creates safe text-like repo artifacts from PowerShell, shell, Python, C, C#, JSON, YAML, JavaScript, TypeScript, HTML, CSS, Markdown, Dockerfile, txt, cmd, and bat templates.
  - Creates folder-style artifact projects and product-specific starter projects under `validation/artifacts/**` with create-only no-overwrite behavior.
  - Places `New artifact` beside search/filter controls. Entering create mode clears the selected list row and shows a focused creation guide; after creation, the new artifact is selected automatically and can be applied to Run Launcher or Scenario Builder flows.
  - Uses a viewport-height workspace on desktop/FHD/QHD so the artifact list, editor, and Script Assist fill the available page height without pushing content outside the hidden workspace. Mobile/tablet keeps a natural vertical document flow with a bounded artifact list and shorter editor.
  - Uses a lazy-loaded Monaco editor for text artifacts with local snippet completion for OSLAB placeholders, output contract examples, PowerShell/shell/Python templates, product-specific agent-cli wrappers, and language basics such as Python `print` and `range`.
  - Offers `Use parent folder in Run Launcher` for nested text artifacts such as `validation/artifacts/<folder>/<script>` when the selected scenario expects a folder-style `{ArtifactDir}` artifact.
  - Requests completions from `POST /api/artifacts/assist/complete`. Python, shell, JSON, YAML, JavaScript, TypeScript, HTML, CSS, Markdown, and Dockerfile ask repo-installed public language servers first (`pyright-langserver`, `bash-language-server`, `vscode-json-language-server`, `yaml-language-server`, `typescript-language-server`, `vscode-html-language-server`, `vscode-css-language-server`, `vscode-markdown-language-server`, `docker-langserver`) and merge OSLAB fallback snippets for artifact and authoring workflows. YAML artifacts under `validation/artifacts/**/*.yaml`/`.yml` are associated with `docs/schemas/artifact-yaml.schema.json`; scenario and suite YAML are associated with `docs/schemas/scenario-yaml.schema.json` and `docs/schemas/suite-yaml.schema.json`. Scenario/Suite authoring and fixture PowerShell/Shell editing use the same Monaco/LSP-shaped surface while preserving the existing diff/save flow. PowerShell, C, and C# report project-local/toolchain LSP readiness plus internal fallback; C# uses `csharp-ls` when available and stays useful with `Console.WriteLine`/`System.Text.Json` snippets when only `dotnet` is present. BAT/CMD/txt use the OSLAB internal LSP-compatible provider. `Ctrl+Space`, `.`, `{`, `$`, `:`, `/`, `<`, `@`, `p`, `W`, `r`, and `f` trigger natural completion requests.
  - Enables Monaco `fixedOverflowWidgets` so suggest/hover/warning popups are not clipped by the editor box.
  - Keeps the Monaco model path-based and avoids controlled value rewrites while typing, so Assist refreshes do not revert or drop fast editor input.
  - Inserts Script Assist completions as plain text edit operations instead of Monaco snippet variables so PowerShell variables such as `$OutputPath` and `$result` do not collide with the snippet parser.
  - Keeps the Monaco model stable by artifact path, so updated Assist checks do not remount the editor or push the cursor/focus elsewhere.
  - Uses a language-specific static lint dataset: common secret-pattern hints plus YAML parse errors, PowerShell `Invoke-Expression`/elevation, shell `curl | sh`/`chmod -R 777`, Python `shell=True`/`os.system`, JS/TS `eval`/shell-based `child_process.exec`, Dockerfile remote `ADD`, BAT `del /s`/`reg delete`, C `gets`/`system`, and C# `Process.Start`/`File.Delete` warnings.
  - Shows first-run guidance, Help, Autocomplete, Checks, Output contract, AI Help extension tabs, and language tool status for PowerShell, shell, Python, JSON, YAML, JS/TS, HTML, CSS, Markdown, Dockerfile, CMD/BAT, C, C#, and txt. The Help tab now explains what an artifact is, how it is copied into the VM, why the output contract matters, how to run it from Run Launcher, each language's minimum structure, and what typed trigger produces which recommendation. Each recommendation is shown as a compact row with a label, description, example, and insert action. The AI Help tab is a placeholder only and does not call a model yet.
  - Allows preview/edit/diff/save only for allowlisted repo text artifacts; binary, directory, uploaded, and archived artifacts remain read-only.
  - Shows binary artifacts as run-only items with size/hash metadata and directory artifacts with total bytes, file count, and a bounded folder tree preview.
  - Provides archive/delete danger actions with dry-run confirmation. Repo artifacts are archive-first; uploaded and archived artifacts can be deleted after confirmation. Deleting an archived leaf also cleans up empty archive parent directories so zero-byte timestamp containers do not remain in the Studio list.
  - Generated or selected artifacts can be applied directly to the current Run Launcher artifact path.
- Read-only artifact path existence checks.
- Recent artifact presets.
- Scenario Builder V2, shown as a compact summary by default with an explicit open/hide control.
  - User-friendly `i` tooltips explain fields such as `id`, `OS family`, `guest mode`, VMID range, artifact, output, report, and cleanup.
  - Fixed-value fields use selects, chip toggles, and checkboxes instead of free-text-only inputs.
  - Fixture, product step, and assertion sections can be added/removed and round-tripped back to YAML.
  - Scenario Builder V3 vertical mode keeps every step button the same size; the selected step is indicated by color and outline only.
  - Compact horizontal steppers keep fixed tracks so the first step cannot consume the remaining row width.
  - The `Hide builder` action collapses the builder column itself into a 56px rail on desktop/FHD/QHD, so the YAML editor immediately gains the reclaimed width.
  - On mobile/tablet, the collapsed builder uses a top bar instead of a left rail, keeping the editor on the full available width.
  - On mobile/tablet, the scenario list collapses into a top bar with centered CSS chevrons, and builder details/lists expand in the page flow instead of creating nested Y-scroll panels.
  - On 1366/FHD/QHD wide screens, both the builder panel and YAML editor fill the workspace height while FHD/QHD give the builder a wider working area.
  - Scenario list rows use 64px on mobile/tablet and 70px on desktop+ so the title and path stay visible instead of clipping.
- Suite visual builder, shown as a compact summary by default with an explicit open/hide control. When opened, the builder gets a larger working area while the YAML editor remains the primary workspace.
- Suite builder run entries use a table-like compact list: order, id, scenario, tier, allow-failure, and move/remove actions stay on one scannable row.
- Stable row heights plus title/path ellipsis in dense scenario/result lists.
- Suite entry and `allowFailure` summary.
- Advanced run options: `keepVm` and `fullClone`.
- Default max parallel: `1`.
- Global running banner.
- Running result synchronization keeps the Results list, selected detail, timeline, and global running banner aligned without a manual refresh when a dashboard-launched job reaches a terminal status.
- Running results show incomplete required evidence as `checking`/`확인 중` until the run reaches a terminal status, so partially written result folders do not look like finalized contract failures too early.
- Running job cancel action.
- Cleanup action for stopped/stale `oslab-*` lab VMs with dry-run and explicit confirmation.
- Unsaved-change guard before tab changes, logout, and browser refresh.
- Dirty indicator that also tracks builder drafts.
- Run readiness strip for target, artifact, lab, option, and command readiness.
- Run Launcher 5-step flow for target, artifact, lab/config, options, and final review.
- Per-action launch readiness reasons for suite and scenario buttons.
- Responsive Run readiness layout for narrow panels and mobile screens.
- Mobile Run Launcher layout scrolls at page level instead of trapping the run form inside a clipped inner panel.
- Narrow desktop Run Launcher layout also switches settings and Live Console to a single page-flow column at 1280px and below, while Lab Status cards wrap automatically instead of forcing a fixed 4-column row.
- Run Launcher command preview.
- Run buttons are disabled when Lab Status is `blocked`.
- Stale `running` job reconciliation after API restarts.
- Automatic jobs/runs refresh and periodic Lab Status refresh.
- Results Explorer master-detail.
- Result search and status filter.
- Result kind, issue, and evidence filters for run/suite, failure class, required/allowed suite failures, cancelled runs, and contract gaps.
- Results list pane can collapse into a narrow rail to give the detail/evidence body more horizontal space, then expand back without losing the selected result.
- Results list keeps the selected detail synchronized with the active search/status filter and shows an empty state when no runs match.
- Results list shows both relative and absolute local time, and Result detail shows a dedicated Result time section.
- Results list/detail reconcile stale artifact `running` status with the dashboard job terminal state, so cancelled/failed runs do not remain visually stuck in progress.
- Results evidence checklist for `run.json`, timeline, raw/normalized output, reports, and cleanup state.
- Result detail file inventory combines the actual `runs/<run-id>/` directory with expected evidence paths, so extra run artifacts are marked as discovered and expected-but-missing artifacts remain visible as disabled missing file cards.
- Suite result detail separates top-level suite evidence from child scenario run artifacts, groups child files by child run ID, and supports drill-down into each child result while preserving the parent suite selection.
- Suite child result detail shows a context banner with the parent suite ID and a Back to suite action.
- `progress.jsonl` run timeline.
- Running/queued result detail uses an active-state summary and falls back to the live job log as a timeline source when the final run progress artifact is not ready yet.
- Live console log fetch, auto-scroll, and manual log reload.
- Direct API SSE with keepalive heartbeat.
- Overlay preview modal for JSON/JSONL/log/XML and other text-like result evidence.
  - Opens from file preview buttons and present evidence rows.
  - File cards open this modal by default; the new-tab action remains inside the preview window.
  - Pretty-prints minified JSON, JSONL lines, XML, and JSON-shaped log output with safe raw fallback.
  - Renders `result.html` and `suite.html` inside a sandboxed iframe so generated reports are readable without leaving the dashboard.
  - Uses an approximately 90% viewport dialog on desktop and mobile viewports.
  - Supports `Esc`, backdrop click, and an icon-only X close button with an accessible label.
  - Missing run files return `404` instead of an unhandled `500`.
- Live job log streaming through SSE.
- Results explorer for `runs/`, including generated HTML reports.
- Mobile horizontal navigation and visible keyboard focus states.

## Verified Browser Smoke

As of 2026-04-23, the dashboard was verified with this real browser flow:

```text
login -> Run Launcher -> select demo-powershell-system -> set artifact path -> run selected scenario -> inspect result
```

Verified job:

| Item | Value |
| --- | --- |
| Job | `cmob5p1up0007smv00wkvjmit` |
| Run | `20260423-162441-demo-powershell-system-windows` |
| Scenario | `scenarios/windows/demo-powershell-system.example.yaml` |
| Artifact | `validation/artifacts/powershell-system` |
| Result | `passed` |

This smoke confirms that the dashboard is not only a mock UI: it launched the existing `uv run oslab run ...` subprocess and completed the Proxmox clone, QGA, artifact upload, product command, assertion, report, and cleanup flow.

Additional checks:

| Item | Value |
| --- | --- |
| Scenario skeleton run without artifact | `cmob7mcny000csmywln8n5ymu`, `passed` |
| Real VM demo run with artifact | `cmob7mhd6000dsmywchkvb3df`, `20260423-171840-demo-powershell-system-windows`, `passed` |
| Results timeline screenshot | `output/web-dashboard/all-features-results-detail.png` |
| Suite detail screenshot | `output/web-dashboard/results-suite-detail.png` |

Additional verification in the latest browser pass:

| Item | Value |
| --- | --- |
| Scenario builder dirty-state guard | Confirm dialog appears when switching tabs after changing builder fields |
| Suite visual builder | Read-only builder confirmed for `validation/suites/product-specific-windows-v1.example.yaml` |
| Cancel job | `cmobkm4al0007sm0wxkijzd6w`, `cancelled` |
| Cleanup lab VM | Dashboard cleanup action returned lab state to `running/stopped oslab VM = 0` |
| Real VM demo run after cleanup | `cmobkqcfv0008sm0wg87k1lhy`, `20260423-232535-demo-powershell-system-windows`, `passed` |
| Recent artifact UX | Chips for `validation/artifacts/powershell-system` and `validation/artifacts/hello-c` confirmed |
| Screenshots | `output/web-dashboard/run-success-and-console.png`, `output/web-dashboard/suite-builder-readonly.png` |
| Dense list layout fix | `output/web-dashboard/scenario-list-row-fix.png`, `output/web-dashboard/results-list-row-fix.png` |
| Structure refactor smoke | `20260424-163351-demo-powershell-system-windows`, `passed` |
| Structure refactor screenshots | `output/web-dashboard/structure-refactor-dashboard.png`, `output/web-dashboard/structure-refactor-scenario.png`, `output/web-dashboard/structure-refactor-results.png` |
| Skeleton result console check | `output/web-dashboard/structure-refactor-skeleton-result-no-progress-error.png`, browser console errors `0` |
| Expert collaboration UI pass | `output/web-dashboard/expert-collaboration-run-readiness.png`, `output/web-dashboard/expert-collaboration-diff-preview.png`, `output/web-dashboard/expert-collaboration-mobile-dashboard.png`, browser console errors `0` |
| Full browser audit | `20260426-042038-demo-powershell-system-windows`, `passed`, `output/web-dashboard/full-browser-audit.json`, browser console errors `0`, network issues `0` |
| Mobile nav/readiness fix | `output/web-dashboard/full-browser-audit-mobile-fix.json`, `output/web-dashboard/full-audit-fix-mobile-dashboard.png`, `output/web-dashboard/full-audit-fix-mobile-run.png`, `output/web-dashboard/full-audit-fix-mobile-results.png` |
| Results evidence checklist | `20260423-232535-demo-powershell-system-windows`, evidence API `total=14`, `present=11`, `contractGaps=0`, `output/web-dashboard/results-evidence-checklist.png`, browser console errors `0`, network issues `0` |
| Cleanup safety | Dry-run/confirmation token contract added; UI cleanup button only appears for stopped/stale VM candidates; `output/web-dashboard/cleanup-dry-run-smoke.json`, console/network issues `0` |
| Results list selection fix | Failed filter now selects a visible failed run and empty search clears stale detail; `output/web-dashboard/results-list-selection-fix-smoke.json`, console/network issues `0` |
| Results stale running status fix | `20260423-232218-demo-c-hello-windows` artifact still says `running`, but dashboard job `cmobkm4al0007sm0wxkijzd6w` is `cancelled`; list/detail now show `cancelled` with status correction, `output/web-dashboard/results-cancelled-status-detail-smoke.json`, API errors `0` |
| Results advanced filters | Kind/issue/evidence filters verified with provider failure suites, required failed suites, and contract gap runs; `output/web-dashboard/results-advanced-filters-smoke.json`, API errors `0` |
| Results list collapse | Expanded list/detail columns `500px/566px`; collapsed rail/detail columns `52px/1014px`; detail width gain `448px`; mobile horizontal overflow `false`; `output/web-dashboard/results-list-collapse-smoke.json`, server/runtime errors `0` |
| Authoring list collapse | Scenario/Fixture/Suite lists collapse from `400px` to `52px`; editor width increases `664px -> 1012px`; selected file persists after collapse/expand; mobile horizontal overflow `false`; `output/web-dashboard/catalog-list-collapse-smoke.json`, server/runtime errors `0` |
| Authoring syntax validation | Valid dirty YAML/PowerShell enables Save; normal/checking syntax state is shown as a toast without moving the editor layout; invalid YAML/PowerShell blocks Save with line/column issue display; invalid builder inspect no longer emits `500`; `output/web-dashboard/syntax-validation-ui-smoke.json`, `output/web-dashboard/syntax-validation-api-smoke.json`, server/runtime errors `0` |
| Authoring diff modal and compact builder | Save opens the 90% diff modal before writing; inline full diff rows are removed; desktop dialog `1229x691`, mobile dialog `351x760`; builder `123px` and textarea `245px` at `1366x768`; `output/web-dashboard/authoring-diff-modal-smoke.json`, `output/web-dashboard/authoring-diff-modal-desktop.png`, `output/web-dashboard/authoring-diff-modal-mobile.png`, server/runtime errors `0` |
| Authoring builder density refinement | Builder defaults to summary chips plus `Open builder`; scenario summary height `109px`, textarea `416px`; expanded builder height `323px`, textarea `202px`; diff modal rows stay packed with `4px` row gap instead of stretching through the empty modal body; `output/web-dashboard/authoring-builder-density-smoke.json`, `output/web-dashboard/authoring-scenario-builder-summary-desktop.png`, `output/web-dashboard/authoring-scenario-builder-expanded-desktop.png`, `output/web-dashboard/authoring-suite-builder-summary-selected-desktop.png`, `output/web-dashboard/authoring-diff-modal-compact-table-desktop.png` |
| Authoring syntax toast and builder action | Valid syntax feedback no longer appears as a block between builder and diff summary; invalid syntax remains inline; invalid YAML skips builder inspect to avoid 400 console noise; builder apply action is a secondary `Apply to YAML` control; `output/web-dashboard/authoring-syntax-toast-smoke.json`, `output/web-dashboard/authoring-syntax-toast-desktop.png`, `output/web-dashboard/authoring-builder-apply-subtle-desktop.png`, `output/web-dashboard/authoring-syntax-error-panel-desktop.png` |
| Suite builder compact list and syntax check | Suite run rows render as a compact table-like list, `suiteRunRows=5`, `legacyBuilderRows=0`, first row height `52.6px`, row overflow false; 390x844 mobile horizontal overflow false; Suite YAML syntax API/UI verified for valid toast and invalid blocking panel; `output/web-dashboard/suite-builder-compact-and-syntax-smoke.json`, `output/web-dashboard/suite-builder-compact-run-list-desktop.png`, `output/web-dashboard/suite-builder-compact-run-list-mobile.png`, `output/web-dashboard/suite-syntax-check-invalid-desktop.png` |
| Results preview modal | `run.json`, `progress.jsonl`, and mobile overlay verified; `output/web-dashboard/results-preview-modal-smoke.json`, console/network issues `0` |
| Results preview modal 90% refinement | Desktop dialog `1230x691` at `1366x768`, mobile dialog `351x760` at `390x844`, X close button verified, missing file status `404`, `output/web-dashboard/results-preview-modal-90pct-smoke.json`, server errors `0` |
| Run Launcher 5-step flow | Target, artifact, lab/config, options, and review sections verified; scenario skeleton run ready state and suite disabled reason verified; `output/web-dashboard/run-launcher-step-flow-smoke.json`, console/server errors `0` |
| Run Launcher artifact recommendation | `demo-powershell-system` recommends `validation/artifacts/powershell-system`; clicking the chip fills the read-only artifact path, artifact status becomes ready, mobile document width stays `390`; `output/web-dashboard/run-launcher-artifact-recommendation-smoke.json`, server/runtime/log errors `0` |
| Run Launcher artifact upload | Browser upload stores a file under `.web-artifacts/`, selects the uploaded path, artifact check becomes `file`, and mobile horizontal overflow remains false; upload state is visible before and after upload; `output/web-dashboard/run-launcher-artifact-upload-smoke.json`, server/runtime errors `0` |
| Run Launcher folder upload/responsive box | Browser folder upload stores a selected `Release` folder under `.web-artifacts/`, selects the generated directory path, artifact check becomes `directory`, upload/recommendation boxes stay readable at `325px` width, horizontal overflow false; `output/web-dashboard/artifact-folder-upload-responsive-smoke.json`, `output/web-dashboard/artifact-folder-upload-controls-responsive.png`, server/runtime errors `0` |
| Run Launcher upload status card | Folder upload status shows the selected `Release` folder, `156` files, byte progress, `In use` state, and saved `.web-artifacts/...` path; `output/web-dashboard/artifact-folder-upload-responsive-smoke.json`, `output/web-dashboard/artifact-folder-upload-controls-responsive.png`, server/runtime errors `0` |
| Run Launcher large folder upload | Real product-specific `bin/Release` folder upload uses direct API URL `http://127.0.0.1:3001/api/artifacts/upload-directory`, stores `156` files / `72,749,326` bytes under `.web-artifacts/1777272853999-Release`, returns `201`, and shows `In use`; `output/web-dashboard/artifact-release-folder-direct-upload.json`, `output/web-dashboard/artifact-release-folder-direct-upload.png`, console errors `0` |
| Artifact Manager MVP | Run Launcher opens the Artifact Manager, repo/uploaded artifacts are listed with metadata, a JSON text artifact is created under `validation/artifacts/**`, edited through preview -> diff modal -> save, and then applied back to the Run Launcher path; `output/web-dashboard/artifact-manager-smoke.json`, `output/web-dashboard/artifact-manager-list.png`, `output/web-dashboard/artifact-manager-create-text.png`, `output/web-dashboard/artifact-manager-edit-diff.png`, `output/web-dashboard/artifact-manager-run-result.png`, `output/web-dashboard/artifact-manager-qhd.png`, `output/web-dashboard/artifact-manager-tablet.png`, `output/web-dashboard/artifact-manager-mobile.png`, errors `0` |
| Artifact Studio + Script Assist | Dedicated `Artifacts` page opens, Monaco editor lazy-loads, static Assist warnings appear for unknown placeholders/destructive commands, diff save persists a text artifact, script project and product-specific starter creation work, assist API detects JSON parse errors, and FHD/QHD/tablet/mobile horizontal overflow is `false`; `output/web-dashboard/artifact-studio-smoke.json`, `output/web-dashboard/artifact-studio-list.png`, `output/web-dashboard/artifact-studio-monaco-editor.png`, `output/web-dashboard/artifact-studio-assist-panel.png`, `output/web-dashboard/artifact-studio-product-specific-template.png`, `output/web-dashboard/artifact-studio-diff-save.png`, `output/web-dashboard/artifact-studio-fhd.png`, `output/web-dashboard/artifact-studio-qhd.png`, `output/web-dashboard/artifact-studio-tablet.png`, `output/web-dashboard/artifact-studio-mobile.png` |
| Artifact Studio viewport layout | On FHD/QHD desktop, `.workspace-artifacts` matches the viewport height, the Studio body fills the remaining workspace, and Monaco plus Script Assist extend to the lower edge. The artifact list uses internal scrolling only; mobile keeps a bounded list and 360px editor flow; `output/web-dashboard/artifact-studio-viewport-layout-smoke.json`, `output/web-dashboard/artifact-studio-viewport-fhd.png`, `output/web-dashboard/artifact-studio-viewport-qhd.png`, `output/web-dashboard/artifact-studio-viewport-mobile.png` |
| Artifact Studio binary/folder archive-delete | FHD/QHD/tablet/mobile verified repo folder tree, binary read-only detail, repo archive modal, archived delete modal, and uploaded binary delete modal. Deleting an archived leaf cleans up empty `.artifact-archive/<timestamp>/repo/...` parent folders so no zero-byte archive containers stay in the list. Applying `validation/artifacts/powershell-system` from Artifact Studio updates Run Launcher readiness and artifact path; `output/web-dashboard/artifact-studio-binary-folder-smoke.json`, `artifact-studio-run-apply-smoke.json`, `artifact-studio-folder-tree-fhd.png`, `artifact-studio-archive-modal-fhd.png`, `artifact-studio-delete-modal-fhd.png`, `artifact-studio-binary-readonly-fhd.png`, `artifact-studio-binary-readonly-qhd.png`, `artifact-studio-tablet-layout.png`, `artifact-studio-mobile-layout.png`, `artifact-studio-directory-run-launcher-applied.png` |
| Artifact Studio create flow/language tools | Clicking `New artifact` clears the selected artifact row and switches to the creation guide. Creating a PowerShell artifact auto-selects the new item, and Script Assist shows first-run guidance plus language tool status. Evidence: `output/web-dashboard/artifact-studio-create-flow.png`, `output/web-dashboard/artifact-studio-assist-language-tools.png`; test: `corepack pnpm exec playwright test apps/web/tests/artifact-studio-create-assist.spec.js --config=playwright.web-dashboard.config.cjs` |
| Artifact Studio LSP Assist | Python/shell/JSON ask repo-bundled public language servers first, then merge OSLAB fallback snippets. In a Python artifact, typing `pri` shows LSP `print`, and typing `for i in ra` shows LSP `range` plus the fallback `for i in range` snippet. The smoke also records JSON LSP `$schema`, fallback `schemaVersion`, shell fallback `grep`, and Python `shell=True` warning detection. The Help/Autocomplete tabs explain first-run artifact authoring, language triggers, descriptions, example code, and insert actions in Korean. Monaco suggest popup overflow is protected by `fixedOverflowWidgets`. A fast-typing regression verifies that the Monaco model value matches the typed input. User-visible FHD Chrome QA also confirmed Artifact Studio navigation, Python artifact editing, `pri` -> `print`, `for i in ra` -> `range`, and the Autocomplete guide tab. Evidence: `output/web-dashboard/artifact-studio-lsp-open-service-smoke.json`, `output/web-dashboard/artifact-studio-python-lsp-print.png`, `output/web-dashboard/artifact-studio-python-lsp-range.png`, `output/web-dashboard/artifact-studio-python-typing-stability.png`, `output/web-dashboard/artifact-studio-visible-browser-smoke.json`, `output/web-dashboard/artifact-studio-visible-python-print.png`, `output/web-dashboard/artifact-studio-visible-python-range.png`; test: `corepack pnpm exec playwright test apps/web/tests/artifact-studio-create-assist.spec.js --config=playwright.web-dashboard.config.cjs` |
| Artifact Studio npm LSP pack expansion | Repo-managed language packs now cover YAML, JavaScript, TypeScript, HTML, CSS, Markdown, and Dockerfile in addition to the earlier Python/shell/JSON surface. Artifact text authoring now allows `.yaml/.yml`, `.js/.mjs/.cjs`, `.ts`, `.html/.htm`, `.css`, `.md/.markdown`, `.dockerfile`, and `Dockerfile` under `validation/artifacts/**`. YAML completion is associated with `docs/schemas/artifact-yaml.schema.json`. API smoke confirmed all new tools report `available/lsp`; YAML, JS/TS, HTML, CSS, Markdown, and Dockerfile completion paths return expected labels; invalid YAML returns `yaml.parse`. Evidence: `output/web-dashboard/artifact-studio-language-pack-smoke.json`; tests: `corepack pnpm --filter @oslab/api lint`, `corepack pnpm --filter @oslab/web lint`, `corepack pnpm --filter @oslab/api build`, `corepack pnpm --filter @oslab/api test` |
| Authoring Monaco YAML LSP | Scenario/Suite YAML and fixture PowerShell/Shell authoring now use Monaco instead of the old textarea when a supported language is selected. The completion/diagnostics surface reuses the Artifact Assist LSP bridge but remains constrained to Web authoring roots. Scenario/Suite schemas provide first-level YAML completion, and internal fallback covers suite `scenario`, `runs`, scenario `assertions`, `provider`, `guest`, and fixture command snippets. LSP `publishDiagnostics` is merged with static checks, so scenario schema errors come from `OSLAB Scenario YAML` rather than unrelated YAML schema-store matches. Visible FHD smoke opened an existing scenario, entered edit mode without saving, confirmed `sche` -> `schemaVersion`, and confirmed invalid/schema-invalid YAML produced Monaco squiggle markers with console/page errors `0`. Evidence: `output/web-dashboard/authoring-yaml-lsp-smoke.json`, `output/web-dashboard/authoring-yaml-monaco-visible-smoke.json`, `output/web-dashboard/authoring-yaml-monaco-visible-open.png`, `output/web-dashboard/authoring-yaml-monaco-visible-completion.png`, `output/web-dashboard/authoring-yaml-monaco-visible-diagnostics-smoke.json`, `output/web-dashboard/authoring-yaml-monaco-visible-diagnostics.png`, `output/web-dashboard/authoring-yaml-monaco-visible-schema-diagnostics-smoke.json`, `output/web-dashboard/authoring-yaml-monaco-visible-schema-diagnostics.png`; tests: `corepack pnpm --filter @oslab/shared build`, `corepack pnpm --filter @oslab/api lint`, `corepack pnpm --filter @oslab/web lint`, `corepack pnpm --filter @oslab/api build`, `corepack pnpm --filter @oslab/api test`, `corepack pnpm --filter @oslab/web build` |
| Artifact Studio create -> assist -> real run | Created `validation/artifacts/web-ui-demo-20260430123434/run-system-demo.ps1` in the Web UI, opened Monaco completion with PowerShell/placeholder snippets and console errors `0`, applied the parent folder `validation/artifacts/web-ui-demo-20260430123434` to Run Launcher, then ran `demo-powershell-system` successfully. Job `cmokxp8su0003smrog10l9yo1`, run `20260430-123836-demo-powershell-system-windows`, assertions `2/0`, preflight `6/0`, cleanup complete. Evidence: `output/web-dashboard/artifact-studio-demo-created.png`, `output/web-dashboard/artifact-studio-autocomplete-trigger.png`, `output/web-dashboard/artifact-studio-assist-check.png`, `output/web-dashboard/artifact-studio-run-launcher-linked.png`, `output/web-dashboard/artifact-studio-demo-run-complete.png`, `output/web-dashboard/artifact-studio-demo-result-detail.png` |
| product-specific suite Web smoke | Web-launched `validation/suites/product-specific-windows-v1.example.yaml` with `C:\Users\kysky\Documents\gitlab\agent-windows\ProductAgent\bin\Release`; job `cmognt5bg000usmmg6u6uvktu` reached real VM execution, 3 entries passed, `appx-readonly` failed as allowed, and `path-profile` exposed a required QGA `exec-status` transient failure; `output/web-dashboard/product-specific-suite-web-ui-smoke.json`, `output/web-dashboard/product-specific-suite-web-final-console.png`, server/runtime errors `0` |
| product-specific path-profile Web regression | After adding QGA `exec-status` retry, Web-launched `scenarios/windows/product-specific/product-specific-agent-path-profile.example.yaml` passed with job `cmogpdv9r002gsmmg4f7b062i`, run `20260427-133443-product-specific-agent-path-profile-windows`, 9 normalized records, 8 assertions, cleanup complete; `output/web-dashboard/product-specific-path-profile-web-regression.json`, `output/web-dashboard/product-specific-path-profile-web-final-console.png`, server/runtime errors `0` |
| Run Launcher directory artifact path | Direct file/folder path accepts `C:\Users\kysky\Documents\gitlab\agent-windows\ProductAgent\bin\Release`; API and UI show `kind=directory`, scenario run readiness is enabled, `output/web-dashboard/artifact-directory-path-smoke.json`, `output/web-dashboard/artifact-directory-path-direct-input.png`, server/runtime errors `0` |
| Running status sync | Browser-launched `demo-powershell-system` skeleton run transitions from running to passed in Results without manual refresh; selected row badge, detail state, notice, and global running banner converge; active incomplete evidence is shown as `확인 중` instead of finalized `계약 누락`; `output/web-dashboard/running-status-sync-smoke.json`, `output/web-dashboard/running-status-sync-results-terminal.png`, `output/web-dashboard/running-evidence-checking.png`, console errors `0` |
| Results human-readable time | Result list and detail verified with `20260426-174301-demo-python-hello-windows`; detail shows started/completed/duration in local time; `output/web-dashboard/results-human-time-smoke.json`, console/server errors `0` |
| Results discovered and missing run files | `20260426-174301-demo-python-hello-windows` shows `raw/fixture-demo-python-runtime.expected-output.json` as a discovered output file and `normalized/inventory.json`/`raw/product-steps.json` as missing expected files without dead links; preview modal opens for the discovered JSON payload; `output/web-dashboard/results-run-files-api-smoke.json`, `output/web-dashboard/results-run-files-missing-api-smoke.json`, `output/web-dashboard/results-run-files-ui-smoke.json`, server/runtime errors `0` |
| Contextual info tooltips | Lab Status, dashboard metrics/lists, Run readiness/sections, authoring syntax/diff, Results time/files/evidence/timeline headers expose circular `i` tooltips; copy is written for users, including Artifact as a test file/program/installer/script/ZIP used inside the VM; `output/web-dashboard/info-tooltip-smoke.json`, `output/web-dashboard/info-tooltip-artifact-friendly.png`, server/runtime errors `0` |
| Information tooltip expansion | Fixture dashboard metric, Scenario/Fixture/Suite catalog headers, Run Suite policy, Results evidence group headers, and `run.json`/`progress.jsonl` evidence rows expose user-facing explanations; `output/web-dashboard/info-tooltip-smoke.json`, `output/web-dashboard/info-tooltip-dashboard-fixtures.png`, `output/web-dashboard/info-tooltip-scenario-catalog.png`, `output/web-dashboard/info-tooltip-fixture-catalog.png`, `output/web-dashboard/info-tooltip-suite-catalog.png`, `output/web-dashboard/info-tooltip-evidence-run-json.png`, `output/web-dashboard/info-tooltip-evidence-progress-jsonl.png`, server/runtime errors `0` |
| Results suite child drill-down | `20260427-125037-product-specific-windows-v1` groups 5 child runs and 80 child artifacts, child result `20260427-125037-product-specific-windows-v1-appx-readonly` opens with a parent-suite context banner and Back to suite action, refresh preserves the parent suite row selection, and `run.json` opens in a modal with no new browser tab; `output/web-dashboard/results-suite-redesign-smoke.json`, `output/web-dashboard/results-suite-files-grouped.png`, `output/web-dashboard/results-suite-child-context.png`, `output/web-dashboard/results-suite-back-from-child.png`, `output/web-dashboard/results-child-preview-popup.png`, console errors `0` |
| Results pretty preview | JSON-shaped `product-step-status.stdout.log` is formatted from one minified line into indented multi-line output in the preview modal; `output/web-dashboard/results-pretty-json-log-preview.png`, `prettyLogPreview=true`, console errors `0` |
| Results HTML report preview | `reports/result.html` opens inside the dashboard preview modal as a sandboxed iframe report instead of raw HTML text; `output/web-dashboard/results-html-iframe-preview.png`, `htmlPreviewIframe=1`, console errors `0` |
| Scenario Builder V2 | New scenario dialog, user-facing field tooltips, select/chip/toggle fields, fixture/product/assertion sections, builder apply, diff modal save, and scenario contract validation verified; design pass reorganized the builder into a Target VM -> setup -> artifact/output -> run command -> checks -> cleanup workflow and aligned `New scenario` with the list collapse action; the new scenario dialog was corrected from 90% preview-modal proportions to a compact creation form; `output/web-dashboard/scenario-builder-v2-validation-smoke.json`, `output/web-dashboard/scenario-builder-v2-mobile-smoke.json`, `output/web-dashboard/scenario-builder-v2-design-regression-smoke.json`, `output/web-dashboard/scenario-create-dialog-compact-smoke.json`, `output/web-dashboard/scenario-builder-v2-design-header-actions.png`, `output/web-dashboard/scenario-builder-v2-design-desktop-expanded.png`, `output/web-dashboard/scenario-builder-v2-design-mobile-expanded.png`, `output/web-dashboard/scenario-create-dialog-compact-desktop.png`, `output/web-dashboard/scenario-create-dialog-compact-mobile.png` |
| Fixture/Suite creation | New Fixture and New Suite creation now reuse the safe create-only authoring pattern. New Suite supports explicit scenario multi-select, generated entry ids, tier, allow-failure, enabled, and maxParallel; it no longer silently includes a hidden default scenario. Created suites stay selected in the Run Launcher. Browser smoke confirmed dialog open/create flows and generated screenshots: `output/web-dashboard/authoring-new-fixture-dialog.png`, `output/web-dashboard/authoring-new-suite-dialog.png`; visible-browser QA: `output/web-dashboard/visible-qa-create-flow.json`, `output/web-dashboard/visible-qa-suite-no-default.json`; focused test: `corepack pnpm --filter @oslab/web exec playwright test apps/web/tests/authoring-create-dialogs.spec.js` |
| Scenario creation UAT | Expert review and browser acceptance test verified the create-only flow: the dialog states that it only creates a file, default paths auto-avoid existing files, ID edits sync the save path, unsaved scenario/builder changes are guarded before creation, and the new scenario opens selected/editable with the builder loaded; `output/web-dashboard/scenario-create-uat-smoke.json`, `output/web-dashboard/scenario-create-uat-dialog.png`, `output/web-dashboard/scenario-create-uat-after-create.png`, `output/web-dashboard/scenario-create-uat-mobile-dialog.png` |
| Scenario Builder V3 vertical axis | Scenario authoring now supports a vertical stepper builder beside the YAML editor. The selected step opens as a compact detail panel while the YAML editor stays visible on the right; execution is split into `4A` artifact command and `4B` product steps; desktop and mobile overflow smoke passed; `output/web-dashboard/scenario-builder-v3-vertical-smoke.json`, `output/web-dashboard/scenario-builder-v3-vertical-desktop.png`, `output/web-dashboard/scenario-builder-v3-vertical-mobile.png`, `output/web-dashboard/scenario-builder-vertical-axis-mockup.png` |
| Viewport design matrix | Browser validation now includes 390x844, 768x1024, 1024x768 narrow desktop, 1366x768, Full HD 1920x1080, and QHD 2560x1440. Scenario/Run/Results plus scenario-collapsed screenshots were captured; console/page errors `0`, horizontal overflow `false`. Scenario Builder V3 now gives the builder more working width, adds a YAML line-number gutter, limits mobile/tablet scenario lists to a scroll area, and renders mobile/tablet collapsed lists as a top bar instead of a left rail; Run Launcher uses one-column page flow at 1280px and below and Lab Status auto-wraps; 1366 open list builder/YAML `420px/379px`, collapsed YAML `546px`, FHD/QHD builder `591px`/`860px`, 1366/FHD/QHD builder and YAML height delta `0`, scenario list text clipping `false`; `output/web-dashboard/viewport-design-matrix-smoke.json`, `output/web-dashboard/viewport-matrix-narrow-desktop-run.png`, `output/web-dashboard/viewport-matrix-qhd-scenario.png` |

## UX Roadmap

Based on expert review and the browser smoke, the next dashboard work should proceed in this order:

1. Pre-run readiness gate expansion
   - Scenario-aware artifact recommendation is now implemented for catalog-backed demo/fake scenarios.
   - Browser file/folder artifact upload is now implemented under `.web-artifacts/`; folder picker uploads copy the selected folder into a generated server-local directory.
   - Large folder upload bypasses the Next rewrite proxy and posts directly to the API server to keep multipart uploads stable.
   - Direct upload status now shows selection, progress, success/failure, and the generated path so users are not left guessing during large folder uploads.
   - Add a Matrix Run Planner for OS template x OS state/profile coverage.
2. Job status UX
   - Add last-log-received timestamps and better cleanup feedback after cancellations.
3. Authoring safety expansion
   - Syntax validation is implemented for current YAML/PowerShell editor buffers before save.
   - Scenario save now also runs minimum scenario contract validation through `POST /api/validate/scenario-content`.
   - Fixture and Suite creation are implemented with the same create-only/no-overwrite safety model, and Suite save runs `POST /api/validate/suite-content`.
   - Save preview now uses a 90% modal; changed rows stay packed at the top of the modal instead of stretching through empty space.
   - Visual builders now default to compact summary chips and can be opened when needed, so YAML editing keeps the main workspace without forcing a cramped builder scroll by default.
   - Scenario Builder V2 now covers user-facing field help, enum controls, cleanup toggles, and generic fixture/product-step/assertion editing.
   - Suite multi-select, enabled, and maxParallel authoring are implemented.
   - Next: add type-specific assertion forms, fixture side-effect summaries, fixture reference flow, and generated suite run smoke.
4. Artifact authoring and manager
   - Current upload flow stores files/folders under `.web-artifacts/` and keeps binary artifacts upload-only.
   - Artifact Studio now has an independent navigation surface, browses `validation/artifacts/**` and `.web-artifacts/**`, shows hash/size/provenance, creates safe text artifacts, creates project/product-specific starters, and applies selected artifacts back to Run Launcher.
   - Script Assist is implemented through backend public-LSP-first completion plus internal fallback datasets and static checks: placeholder checks, JSON/YAML parsing checks, output-contract hints, language-specific dangerous command warnings, and language tool status guidance.
   - Nested text artifacts can be applied as their parent folder when a scenario expects a folder artifact.
   - Next: add recent-use ownership metadata, deeper Scenario Builder path insertion, language tool install-flow polish, richer scenario/suite YAML schemas, and an optional real AI-assist backend.
   - Detailed plan: [Authoring Expansion Collaboration Plan](devs/authoring-expansion-collaboration-plan.md).
5. Live Console timeline
   - Visualize clone, boot, QGA, preflight, fixture, artifact, product, assertion, and cleanup stages alongside the raw log.
6. Results Explorer master-detail
   - Browse `suite.json`, `run.json`, `progress.jsonl`, discovered raw/normalized outputs, generated reports, missing expected files, and other text-like run files from the dashboard.
   - Suite child run file grouping and child result drill-down are implemented for nested `runs/<suite>/scenarios/<child>/...` artifacts.
   - Add lineage view for job, suite, scenario, VMID, template, profile, artifact, and cleanup state.
7. Cleanup metadata
   - Add candidate age and owning run once stale VM metadata is written into run artifacts.

Detailed maintainer TODOs live in [Web Dashboard Usability TODO](devs/web-dashboard-usability-todo.md).

## Known Gaps

- No OIDC/SSO.
- No role split beyond local admin.
- No TRX aggregate report yet.
- Full schema-aware validation is still incomplete for fixtures and suites; scenario and suite saves now have minimum contract gates in addition to YAML syntax.
- The scenario visual builder now has generic fixture/assertion/product-step editing, but type-specific assertion forms and fixture side-effect forms are still pending.
- Fixture and Suite creation now have the first create-only flow; follow-up work remains for product-specific fixture starters, mobile/FHD/QHD visual matrix evidence, and running a generated suite end to end.
- Artifact Studio is implemented for dedicated artifact browsing, Run Launcher selection, safe text/binary/directory artifact management, project starter creation, product-specific starter creation, Monaco editing, archive/delete, public-LSP-first autocomplete across repo-managed npm language packs, internal fallback/lint datasets, and static Script Assist with language tool status. Remaining gaps are recent-use ownership metadata, deeper Scenario Builder path insertion, richer scenario/suite YAML schemas, project-local PowerShell/C LSP tool-cache setup polish, and a real AI-assist backend.
- Interrupted runs without a complete `run.json` still need cleaner representation in the Results view.
