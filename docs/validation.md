# Validation And JUnit

Language: English | [한국어](validation.ko.md)

`oslab` validation is not one command. It is a ladder of checks that lets you stop at the cheapest layer that can explain a failure.

The short answer: JUnit is implemented. Full `oslab run` and `artifact-smoke` write `runs/<run-id>/reports/result.junit.xml` when the scenario contains `reports.formats: [junit, ...]`. CI reads that XML; `oslab` does not run a separate command named `junit`.

## Validation Ladder

Use the ladder from top to bottom when adopting a new scenario. Each step proves a narrower part of the system before you pay for a full VM run.

| Layer | Command | VM created? | What it proves | Main evidence |
| --- | --- | --- | --- | --- |
| 1. Scenario shape | `validate-scenario` | No | YAML schema, required fields, allowed enum values | Console result |
| 2. Provider config | `preflight --provider-config-check` | No | Config/env secrets can resolve to a provider client | Console result |
| 3. Provider API | `preflight --provider-connectivity-check` | No | Proxmox API/token/network works | Console result |
| 4. Provider resources | `preflight --provider-resource-check` | No | Node, template VM, and VMID range are usable | Console result |
| 5. Clone lifecycle | `clone-smoke` | Yes | Proxmox can clone and destroy the template | Console result |
| 6. Boot and guest readiness | `boot-smoke` | Yes | Clone boots and QEMU Guest Agent becomes ready | Console result |
| 7. Guest baseline | `guest-preflight` | Yes | PowerShell/admin/file roundtrip checks pass | Console result |
| 8. Fixture isolation | `fixture-smoke` | Yes | Fixture scripts run before artifact execution | Fixture logs/output |
| 9. Artifact isolation | `artifact-smoke` | Yes | Artifact upload/install/command/output collection works | Run layout and reports |
| 10. Full integration | `run` | Yes | End-to-end scenario, normalization, assertions, reports, cleanup | `runs/<run-id>/` |
| 11. Local result checks | `normalize-output`, `assert-result`, `analyze-inventory` | No | Adapter/assertion/analysis logic works without a VM | Local JSON output |
| 12. Result inspection | `inspect-result` | No | Completed run is readable by a human or automation | Console summary |

The usual flow for a new test is:

```powershell
uv run oslab validate-scenario --scenario scenarios/windows/demo-python-hello.local.yaml
uv run oslab preflight --scenario scenarios/windows/demo-python-hello.local.yaml --config config/oslab.local.yaml --env-file config/oslab.local.env --provider-resource-check
uv run oslab guest-preflight --scenario scenarios/windows/demo-python-hello.local.yaml --config config/oslab.local.yaml --env-file config/oslab.local.env
uv run oslab fixture-smoke --scenario scenarios/windows/demo-python-hello.local.yaml --config config/oslab.local.yaml --env-file config/oslab.local.env
uv run oslab run --scenario scenarios/windows/demo-python-hello.local.yaml --config config/oslab.local.yaml --env-file config/oslab.local.env --artifact-path validation/artifacts/hello-python
uv run oslab inspect-result --run-dir runs\<run-id>
```

## What Validation Means

`oslab` separates validation into four different meanings:

| Meaning | Where it happens | Example |
| --- | --- | --- |
| Static contract validation | Before lab access | `validate-scenario` rejects an unsupported `guest.mode` |
| Infrastructure validation | Before product execution | `preflight`, `clone-smoke`, `boot-smoke`, `guest-preflight` |
| Product behavior validation | Inside the disposable VM | `artifact.command`, `product.steps`, collected output |
| Result validation | After output collection | Adapter normalization and assertions |

This separation is intentional. If a fixture fails, the run should say `fixture_failure`. If the product command exits non-zero, it should say `product_execution_failure`. If the command succeeds but output is wrong, it should say `assertion_failure`.

## JUnit Status

JUnit XML is implemented.

Implementation points:

| Item | Status |
| --- | --- |
| JUnit writer | Implemented in `src/oslab/reports/junit.py` |
| Full run output | Implemented under `runs/<run-id>/reports/result.junit.xml` |
| `artifact-smoke` reports | Implemented through the same artifact validation report writer |
| Unicode details | Covered by unit tests so Korean stderr/details remain readable |
| CI workflow file | Documentation pattern exists; a committed provider-specific CI workflow is still project-specific |

JUnit is generated only if the scenario asks for it:

```yaml
reports:
  formats:
    - junit
    - json
    - html
```

If `reports.formats` is omitted, the scenario model defaults to JSON only. If you expect CI JUnit output, include `junit` explicitly.

## JUnit Mapping

`oslab` writes one test suite per scenario. Test cases map to run phases.

| Testcase name | Source | JUnit status on failure |
| --- | --- | --- |
| `preflight.<check-id>` | Guest readiness checks | `error` |
| `fixture.<fixture-id>` | Fixture script execution | `error` |
| `artifact.install` | Installer artifact install command | `error` |
| `product.command` | Main artifact command | `error` |
| `product.step.<step-id>` | Ordered product step | `error` |
| `assertion.<assertion-id>` | Assertion evaluation | `failure` |

The distinction matters in CI:

- `error` means the test could not execute cleanly because infrastructure, setup, install, or product execution failed.
- `failure` means the run executed, but the observed result did not satisfy the expected assertion.

## Generated Files

A full run with `junit`, `json`, and `html` enabled writes:

```text
runs/<run-id>/
  run.json
  logs/
    progress.log
    progress.jsonl
    product.stdout.log
    product.stderr.log
  raw/
    actual-output.json
    fixture-<fixture-id>.expected-output.json
  normalized/
    command-result.json
  reports/
    result.json
    result.junit.xml
    result.html
```

Use these files together:

| Need | Use |
| --- | --- |
| CI pass/fail | `reports/result.junit.xml` |
| Human review | `reports/result.html` |
| Automation | `reports/result.json` or `run.json` |
| Debug timeline | `logs/progress.log` |
| Raw product evidence | `raw/actual-output.json` |
| Assertion input | `normalized/*.json` |

## CI Usage

CI should run `oslab run`, always upload `runs/**`, and publish the JUnit XML.

GitHub Actions pattern:

```yaml
- name: Run oslab demo
  run: >
    uv run oslab run
    --scenario scenarios/windows/demo-python-hello.local.yaml
    --config config/oslab.local.yaml
    --env-file config/oslab.local.env
    --artifact-path validation/artifacts/hello-python

- name: Upload oslab run artifacts
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: oslab-runs
    path: runs/**
```

GitLab CI pattern:

```yaml
artifacts:
  when: always
  paths:
    - runs/
  reports:
    junit: runs/**/reports/result.junit.xml
```

## Local Adapter And Assertion Checks

You can test output logic without creating a VM.

Normalize raw output:

```powershell
uv run oslab normalize-output `
  --scenario scenarios/windows/demo-python-hello.example.yaml `
  --input-json validation/raw/command-result.example.json `
  --output-json runs/local-normalized.json
```

Evaluate assertions against a JSON result:

```powershell
uv run oslab assert-result `
  --scenario scenarios/windows/demo-python-hello.example.yaml `
  --actual-json runs\<run-id>\raw\actual-output.json
```

Analyze canonical inventory output:

```powershell
uv run oslab analyze-inventory `
  --inventory-json runs\<run-id>\normalized\inventory.json `
  --output-json runs\<run-id>\reports\inventory.analysis.json
```

These commands are useful when the VM run succeeded but the adapter, normalized shape, or assertions need tuning.

## What Is Still Not A Generic Validation Feature

Some validation pieces are deliberately outside the generic core:

| Area | Current position |
| --- | --- |
| Product-specific login/register flows | Put in scenario `product.steps`, artifact scripts, or product-owned docs |
| Product-specific inventory semantics | Put in adapters/assertions owned by that product |
| CI runner provisioning | Documented as a pattern, but each lab needs its own runner/network/secret setup |
| Linux SSH execution | Scenario model exists; implementation is not complete yet |

The generic core should keep owning VM lifecycle, guest execution, fixture execution, artifact transfer, output collection, normalization hooks, assertions, and reports.
