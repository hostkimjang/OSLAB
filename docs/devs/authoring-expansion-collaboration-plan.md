# Authoring Expansion Collaboration Plan

Date: 2026-04-28

Scope: Web Dashboard authoring expansion after Scenario Builder V3. This meeting covers New Fixture creation, New Suite creation, and whether `validation/artifacts` should become web-authorable instead of upload-only.

## Expert Roles

| Role | Review Focus | Decision |
| --- | --- | --- |
| UX/Design | Creation flows, screen density, user mental model | Reuse the New Scenario create-only pattern for Fixture and Suite. Keep artifact authoring separate from run-time upload. |
| Frontend | Authoring state, catalog refresh, diff/save UX | Use the existing catalog editor, syntax toast, diff modal, dirty guard, and viewport matrix contracts. |
| Backend/API | File safety, template generation, validation | Add a shared authoring policy before opening more executable-file creation paths. |
| QA | Browser acceptance, demo run, evidence | Every new authoring surface needs create -> edit -> validate -> diff -> save -> run/result evidence smoke. |
| Operator/User | Day-to-day lab workflow | New items should be immediately usable in Run Launcher or Scenario Builder without manual refresh or path guessing. |

## Meeting Decisions

1. `New Fixture` is P0 because Environment preparation is already a first-class dashboard section but currently lacks the same creation affordance as Scenario.
2. `New Suite` is P0/P1 because Suite Builder exists, but users still need to start from existing YAML rather than composing a new run bundle from the UI.
3. `validation/artifacts` web authoring is useful, but should be split:
   - Upload/manage binary or directory artifacts: keep under Artifact upload/manager.
   - Create/edit text-like repo artifacts: allow only safe text extensions.
   - Binary files such as `.exe`, `.msi`, `.zip` remain upload-only/read-only in the dashboard.
4. Before adding more creation buttons, API-side authoring policy must check root, extension, secret path, path traversal, size, and create-only semantics.
5. The acceptance contract should mirror New Scenario: create-only, no overwrite, catalog refresh, selected file opens in edit mode, validation, diff modal, final save, browser screenshot evidence.

## P0: Safety And Creation Parity

- [x] Add shared Web authoring policy.
  - Root allowlist by kind:
    - Scenario: `scenarios/**/*.yaml|yml`
    - Fixture: `validation/fixtures/**/*.ps1|sh`
    - Suite: `validation/suites/**/*.yaml|yml`
    - Editable artifact: `validation/artifacts/**/*.{ps1,sh,py,c,json,txt,cmd,bat}`
  - Implemented now: root allowlist, extension allowlist, absolute path, `..`, `.env`/`*.local.*`/known secret path blocking, create-only behavior, Windows reserved device name blocking, control character blocking, trailing dot/space segment blocking, and a 1 MiB text authoring limit.
  - `artifactText` authoring kind now enforces the text-like artifact allowlist under `validation/artifacts/**`.
  - Keep binary artifacts upload-only.
- [x] Add `New Fixture` creation flow.
  - UI entry: Fixture catalog header, aligned with list collapse control like `New Scenario`.
  - Templates now: Windows PowerShell fixture and Linux shell fixture.
  - Follow-up: product-specific profile fixture starter.
  - Default paths: `validation/fixtures/windows/<slug>.ps1`, `validation/fixtures/linux/<slug>.sh`.
  - After create: refresh fixture catalog, select file, enter edit mode.
- [x] Add `New Suite` creation flow.
  - UI entry: Suite catalog header.
  - Template fields now: id, name, save path, scenario multi-select, smoke/matrix starter, tier, allow failure, enabled, and max parallel.
  - Follow-up: actual generated suite run smoke.
  - Default path: `validation/suites/<slug>.example.yaml`.
  - After create: refresh suite catalog, select file, enter edit mode, load Suite Builder, select the suite in Run Launcher, and mirror maxParallel into the run form.
- [x] Add suite contract validation at save time.
  - Blocks empty runs, duplicate entry ids, invalid scenario paths, and invalid `allowFailure/enabled/tier/maxParallel` shapes.
  - `enabled: false` is a real suite contract field and the Python suite runner skips disabled entries.
  - Shows blocking notice for invalid content and keeps syntax toast behavior for valid content.

## P1: Builder Integration

- [ ] Upgrade Fixture Studio from script-only editing to a visual fixture starter.
  - Fields: fixture type, id/name, shell, source path, expected output path, side-effect summary.
  - Generate `$ErrorActionPreference = "Stop"` for PowerShell templates.
  - Warn that product execution belongs to Scenario product steps, not fixture setup.
- [ ] Connect created fixtures into Scenario Builder.
  - Fixture section can choose from fixture catalog.
  - Show reverse lookup: scenarios that already reference this fixture.
  - Round-trip fixture references into YAML and save through the existing diff modal.
- [ ] Improve Suite Builder creation UX.
  - Scenario multi-select with search.
  - Auto-generate suite entry ids and avoid duplicates.
  - Reorder, tier, allowFailure, enabled stay editable immediately after creation.
  - New suite appears in Run Launcher without manual reload.
- [x] Add artifact manager MVP.
  - Browse `validation/artifacts/**` and `.web-artifacts/**`.
  - Show type, size, modified time, SHA-256 file hash, file count, and source: repo vs uploaded.
  - Provide "Use in Run Launcher" and "Use in Scenario Builder" actions.
  - Current MVP applies both actions to the selected runtime artifact path; a later Scenario Builder-specific insertion action remains.

## P2: Web-Authorable Artifacts

- [x] Add text artifact template creation.
  - Templates: PowerShell script, shell script, Python script, C source, JSON expected output, command batch.
  - Editable extensions only: `.ps1`, `.sh`, `.py`, `.c`, `.json`, `.txt`, `.cmd`, `.bat`.
  - Save through the same syntax/diff/dirty guard path where applicable.
- [ ] Strengthen artifact upload safety.
  - Folder upload should reject unsupported file extensions, not only unsafe paths.
  - Preserve current direct API upload path for large folders to avoid Next rewrite proxy failure.
  - Add hash/byte count/provenance for uploaded artifacts.
  - Artifact Manager now displays file hash, byte count, file count, and provenance; upload rejection rules remain a follow-up.
- [ ] Align authoring vocabulary with Results evidence.
  - While editing Scenario/Suite, preview expected evidence: `run.json`, `progress.jsonl`, raw output, normalized output, reports, cleanup state.
  - After run, Results should use the same names so users can compare planned evidence with actual evidence.

## P3: Matrix And Advanced Authoring

- [ ] Keep Matrix Run Planner as a separate higher-level UX, not inside New Suite dialog.
  - Axes: OS template axis x OS state/profile axis.
  - Show capacity, VMID range, `maxParallel`, allowFailure policy, expected evidence.
- [ ] Add real install profile creation helpers.
  - EXE/MSI, winget, Chocolatey, Appx/MSIX fixture/suite starters.
  - These should reuse New Fixture, New Scenario, New Suite, and Artifact Manager building blocks.
- [ ] Add TRX aggregate report planning once JSON/HTML suite flow is stable.

## Acceptance Matrix

| Flow | Required Acceptance |
| --- | --- |
| New Fixture | Create-only under `validation/fixtures/**`, no overwrite, catalog refresh, selected/edit mode, syntax validation, diff modal save, read-only after save. |
| New Suite | Create-only under `validation/suites/**`, at least one scenario, builder loads, suite validation blocks bad content, Run Launcher dropdown refreshes. |
| Artifact Manager | Done for MVP: upload file/folder selection, browse repo/uploaded artifacts, check file/directory kind, binary read-only, text artifacts editable only inside allowlist. Follow-up: independent nav, recent-use, delete/archive, Scenario Builder-specific insertion. |
| Demo Run | At least one generated fixture or generated suite is used from Web UI and reaches Results with `run.json`, `progress.jsonl`, report preview, and cleanup state visible. |
| Viewports | 390x844, 768x1024, 1366x768, 1920x1080, 2560x1440 screenshots with horizontal overflow false. |

## Test Plan

- API:
  - create fixture/suite/artifact template success
  - duplicate path rejects
  - root escape rejects
  - unsupported extension rejects
  - secret path create/read/write rejects
  - folder upload rejects unsupported nested file extensions
- Web:
  - New Fixture dialog open/close/X/Esc/backdrop/focus restore
  - New Suite dialog open/close/X/Esc/backdrop/focus restore
  - catalog refresh and selected file persistence
  - syntax toast, inline invalid panel, diff modal, save
  - Run Launcher refresh for generated suite/artifact
- Browser evidence:
  - `output/web-dashboard/fixture-create-uat-smoke.json`
  - `output/web-dashboard/suite-create-uat-smoke.json`
  - `output/web-dashboard/artifact-manager-smoke.json`
  - `output/web-dashboard/artifact-manager-list.png`
  - `output/web-dashboard/artifact-manager-create-text.png`
  - `output/web-dashboard/artifact-manager-edit-diff.png`
  - viewport screenshots for each flow.
