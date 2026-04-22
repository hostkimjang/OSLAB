# Reports And Results

Language: English | [한국어](reports.ko.md)

Full `oslab run` writes a stable output directory under `runs/<run-id>/`.

It helps to separate report-related files into two groups:

- Evidence: files used to investigate what happened, such as `logs/`, `raw/`, `normalized/`, and `run.json`.
- Reports: final outputs consumed by humans, CI, or automation, such as `reports/result.html`, `reports/result.junit.xml`, and `reports/result.json`.

Use evidence for investigation. Use reports for sharing, CI gates, and automation.

## Layout

```text
runs/<run-id>/
  run.json
  logs/
    progress.log
    progress.jsonl
    product.stdout.log
    product.stderr.log
    product-step-<step-id>.stdout.log
    product-step-<step-id>.stderr.log
  raw/
    actual-output.json
    product-steps.json
    fixture-<fixture-id>.expected-output.json
  normalized/
    command-result.json
    inventory.json
  reports/
    result.json
    result.junit.xml
    result.html
    inventory.analysis.json
```

Not every run creates every file. For example, command-result demos create `normalized/command-result.json`, while inventory scenarios create `normalized/inventory.json`.

## Which File Should I Open First?

| Situation | First file/command | Why |
| --- | --- | --- |
| A local run failed | `logs/progress.log` | Fast readable timeline |
| You want a summary | `uv run oslab inspect-result --run-dir runs\<run-id>` | Prints status, failure class, reports, stdout preview |
| You need a human report | `reports/result.html` | Static report for review |
| CI needs pass/fail | `reports/result.junit.xml` | Standard test report |
| Adapter/assertion looks wrong | `raw/actual-output.json` then `normalized/*.json` | Compare raw collected data with canonical data |
| Step-based product failed | `raw/product-steps.json` and `logs/product-step-*.stderr.log` | Shows each step's result |

## File Roles

| File or directory | Primary reader | Role |
| --- | --- | --- |
| `run.json` | `inspect-result`, automation | Run status, failure class, and path index |
| `logs/progress.log` | Human | Live progress and triage |
| `logs/progress.jsonl` | Automation/dashboard | Structured progress events |
| `logs/product*.stdout.log` / `stderr.log` | Human/debugger | Guest command output |
| `raw/actual-output.json` | Adapter/debugger | Raw guest output collected by `oslab` |
| `normalized/command-result.json` | Assertions/human/debugger | Canonical command result |
| `normalized/inventory.json` | Assertions/analysis | Canonical inventory result |
| `reports/result.junit.xml` | CI test reporter | Gate/pass-fail report |
| `reports/result.json` | Automation | Machine-readable report |
| `reports/result.html` | Human reviewer | Static report |

## Live Logs

Watch a run:

```powershell
Get-Content runs\<run-id>\logs\progress.log -Wait
```

`progress.jsonl` contains the same events as structured JSON:

```json
{"phase":"vm.boot.done","status":"done","message":"VM is running","details":{"vmId":9102}}
```

## Inspect Result

```powershell
uv run oslab inspect-result --run-dir runs\<run-id>
```

Raw `run.json`:

```powershell
uv run oslab inspect-result --run-dir runs\<run-id> --json
```

Open HTML:

```powershell
Invoke-Item runs\<run-id>\reports\result.html
```

## JUnit

CI systems should read:

```text
runs/<run-id>/reports/result.junit.xml
```

Mapping:

| Testcase | Meaning | Failure type |
| --- | --- | --- |
| `preflight.<check-id>` | Guest readiness | `error` |
| `fixture.<fixture-id>` | Fixture/bootstrap | `error` |
| `artifact.install` | Installer execution | `error` |
| `product.command` | Product/demo command execution | `error` |
| `product.step.<step-id>` | Ordered product step | `error` |
| `assertion.<assertion-id>` | Output mismatch | `failure` |

Infrastructure/execution failures should appear as JUnit errors. Assertion mismatches should appear as JUnit failures.

JUnit generation is implemented for `oslab run` and `artifact-smoke` when the scenario includes `junit` in `reports.formats`. For the validation ladder and exact command flow, see [Validation And JUnit](validation.md).

## CI Artifact Pattern

Always publish `runs/**` even when the job fails. Otherwise the JUnit file may show a failure, but the logs, raw output, normalized output, and HTML report needed for triage may be lost.

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

Use CI concurrency controls or separate VMID ranges when multiple jobs can run against the same Proxmox lab.
