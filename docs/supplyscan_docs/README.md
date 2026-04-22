# SupplyScan Private Use-Case Notes

This directory keeps SupplyScan-specific validation notes separate from the public, product-neutral `oslab` documentation.

`oslab` itself should be explained as a generic OS/VM integration test platform. SupplyScan is one adapter/scenario set that happens to use the platform.

## Files

| File | Purpose |
| --- | --- |
| `scenarios/windows/supplyscan-agent-cli.example.yaml` | Full Agent CLI register/status/scan smoke |
| `scenarios/windows/supplyscan-agent-status.example.yaml` | Status-only Agent smoke |
| `scenarios/windows/supplyscan-gold-lite.yaml` | Legacy inventory-style SupplyScan smoke |
| `validation/fixtures/windows/gold-lite.ps1` | Legacy expected inventory fixture |
| `validation/expected/gold-lite.expected_inventory.json` | Legacy expected inventory data |
| `validation/raw/supplyscan/sample-output.json` | Sample SupplyScan raw output for normalize tests |
| `docs/supplyscan_docs/oslab-platform-plan.supplyscan.md` | Archived SupplyScan-oriented platform plan |
| `docs/supplyscan_docs/legacy-architecture.md` | Original SupplyScan validation CI architecture note |

## Env Values

The public `config/oslab.local.example.env` only includes Proxmox values. SupplyScan-specific values are in `config/supplyscan.local.example.env`.

Copy those values into your ignored `config/oslab.local.env` only when running SupplyScan scenarios:

```text
OSLAB_SUPPLYSCAN_SERVER_URL=https://supplyscan.example.local
OSLAB_SUPPLYSCAN_SABUN=10001
```

The full Agent CLI smoke does not require a host-provided SupplyScan access token. The scenario verifies that `register` performs initial login/registration from server URL + sabun, then stores token state inside the guest VM.

## Agent CLI Contract

Expected executable shape:

```powershell
SupplyScanAgent.exe cli_mode <command> [options]
```

Required commands:

| Command | Required behavior | oslab use |
| --- | --- | --- |
| `register --json` | Server URL, sabun, asset name/class로 headless registration/login 수행하고 config.ini에 token 저장 | 초기 등록 |
| `status --json` | Local config, token, policy, version 상태를 single JSON object로 출력 | 설치/등록 검증 |
| `status --remote --json` | Server/token/asset/policy endpoint 확인 | 서버 연동 smoke |
| `scan --wait --output <path> --json` | Software scan 실행 후 raw scan JSON을 output path에 기록 | product execution |

Automation requirements:

- No GUI prompt
- No stdin prompt
- Deterministic exit code
- With `--json`, stdout contains one final JSON object
- Secret values are never printed
- `scan --output` creates parent directories and writes final raw JSON
- Failure should write a machine-readable failure artifact to the same output path when possible

## Full Agent Smoke

Use the Release or Debug build output directory, not only the exe file. The folder must contain dependency DLLs/config files.

```powershell
uv run oslab run `
  --scenario scenarios/windows/supplyscan-agent-cli.example.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path C:\path\to\agent-windows\SupplyScanAgent\bin\Release `
  --command-timeout-seconds 420 `
  --poll-interval-seconds 5
```

The scenario performs:

1. Proxmox resource preflight
2. VMID allocation
3. Windows template clone
4. VM start and QGA readiness
5. Windows guest preflight
6. SupplyScan config contamination preflight
7. Folder artifact ZIP upload
8. `SupplyScanAgent.exe cli_mode register`
9. `SupplyScanAgent.exe cli_mode status --remote`
10. `SupplyScanAgent.exe cli_mode scan --wait`
11. Output collect, normalize, assertion, reports
12. VM stop/destroy cleanup

## Status-Only Smoke

Use this when you only want to check whether the built exe can launch and report status.

```powershell
uv run oslab artifact-smoke `
  --scenario scenarios/windows/supplyscan-agent-status.example.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path C:\path\to\agent-windows\SupplyScanAgent\bin\Release `
  --command-timeout-seconds 240
```

## Known SupplyScan Behavior

Register step starts with:

```text
accessTokenProvided: false
accessTokenSource: none
```

After successful registration, status should show:

```text
accessTokenPresent: true
refreshTokenPresent: true
encryptionKeyPresent: true
```

The initial policy sync may use `policy_id = -1`. A lower-level `/api/v1/policy` check can look like a failure before the first sync. The current `oslab` product step gate uses top-level `stdoutJson.ok`.

## Result Inspection

```powershell
uv run oslab inspect-result --run-dir runs\<run-id>
```

Important files:

| Path | Meaning |
| --- | --- |
| `run.json` | Run summary, VM lifecycle, reports, logs |
| `logs/progress.log` | Live progress log |
| `raw/product-steps.json` | Register/status/scan step output |
| `raw/actual-output.json` | Raw scan output |
| `normalized/inventory.json` | Canonical inventory |
| `reports/result.junit.xml` | CI test report |
| `reports/result.html` | Human report |
| `reports/inventory.analysis.json` | Inventory quality summary |

Analyze inventory again:

```powershell
uv run oslab analyze-inventory `
  --inventory-json runs\<run-id>\normalized\inventory.json `
  --output-json runs\<run-id>\reports\inventory.analysis.json
```

## Artifact Upload Notes

- Use folder artifact upload for real Agent builds.
- `artifact.transfer: archive` zips the folder locally, uploads one archive through QGA chunks, then expands it in the guest.
- Exclude `logs/**`, `*.pdb`, and `*.xml` from large build folders unless you intentionally need them.
- Do not point `--artifact-path` at a directory with huge generated logs.

## Legacy Context

`docs/supplyscan_docs/legacy-architecture.md` is legacy SupplyScan-specific validation CI context. `docs/architecture.md` is now only a compatibility redirect and should not be the public entry point for `oslab`.
