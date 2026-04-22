# Adoption Guide

Language: English | [한국어](adoption-guide.ko.md)

This guide is for developers who want to use `oslab` for their own product, not just run the demos.

The key principle is to keep environment setup separate from product execution. Put guest preparation in fixtures. Put product behavior in `artifact.command` or `product.steps`.

## What You Need To Create

For the first product smoke test, create the smallest possible set:

| File or thing | Role | Example |
| --- | --- | --- |
| Scenario YAML | Defines the OS/template/state and how the artifact should run | `scenarios/windows/my-product.local.yaml` |
| Local config | Points `oslab` at your Proxmox lab | `config/oslab.local.yaml` |
| Env file or CI secrets | Supplies Proxmox token secrets | `config/oslab.local.env` |
| Fixture, optional | Prepares guest state before the artifact runs | `validation/fixtures/windows/my-runtime.ps1` |
| Artifact | Folder or installer being tested | `C:\builds\my-product` or `MyInstaller.exe` |
| Artifact command | Command that runs inside the VM | `run-smoke.ps1 -OutputPath "{OutputPath}"` |
| Output JSON | Machine-readable result written in the guest | `C:\Oslab\command-result.json` |
| Assertions | Pass/fail rules over normalized output | `command.exitCode`, `command.stdoutContains` |

Start with a folder artifact and `canonical.command`. Add installer flow, product steps, or custom adapters only after the simplest smoke test is stable.

## Build First / Avoid First

| Area | Build first | Avoid first |
| --- | --- | --- |
| Scenario | A local scenario copied from a demo | Many OS-specific scenario shapes at once |
| Fixture | Test prerequisites such as runtime, registry, policy | Product execution, scan execution, login flow validation |
| Artifact | Real build output or a smoke script folder | Artifacts that contain lab config or secrets |
| Adapter | `canonical.command` | A custom adapter before the smoke path works |
| Assertion | Simple `exitCode=0`, stdout contains checks | Complex inventory/plugin assertions |
| Reports | Built-in JUnit/JSON/HTML | A custom dashboard |

This keeps failure causes clear: fixture failure means setup failed, artifact command failure means product execution failed, assertion failure means the output did not match expectations.

## Fixture vs Artifact

A fixture prepares the test room. It creates the VM state needed before the product runs.

An artifact is the thing taking the test. It is the product folder, installer, or smoke script bundle that should produce a signal.

| Question | Fixture | Artifact |
| --- | --- | --- |
| When does it run? | Before artifact upload/execution | After fixture setup |
| What belongs there? | OS state, runtime, policy, baseline | Product files, installer, smoke script |
| What does failure mean? | Environment setup failed | Product install/execution failed |
| Example | Python bootstrap, registry key creation | `my-product.exe`, `setup.exe`, `run-smoke.ps1` |

Putting product execution in fixtures blurs whether a failure is environmental or product-related.

## Adapter vs Assertion

An adapter is a translator. It turns product-specific raw output into a canonical model that `oslab` can score.

An assertion is the scoring rule. It reads the canonical model and decides pass/fail.

```text
raw product output
  -> adapter
  -> canonical result
  -> assertion
  -> pass/fail
```

This separation lets product output schemas change without rewriting every assertion.

## Recommended Adoption Flow

| Phase | Goal | Command |
| --- | --- | --- |
| 1. Copy a demo scenario | Create a local scenario you can edit safely | `Copy-Item scenarios/windows/demo-python-hello.example.yaml scenarios/windows/my-product.local.yaml` |
| 2. Point at your lab | Set template VMID, VMID range, Proxmox node | Edit `provider` and `config/oslab.local.yaml` |
| 3. Validate the YAML | Catch schema mistakes early | `uv run oslab validate-scenario --scenario scenarios/windows/my-product.local.yaml` |
| 4. Check provider readiness | Verify config, token, node, template, VMID range | `uv run oslab preflight ... --provider-resource-check` |
| 5. Attach your artifact | Pass your build output through `--artifact-path` | `uv run oslab run ... --artifact-path <path>` |
| 6. Inspect results | Read stdout, reports, normalized JSON | `uv run oslab inspect-result --run-dir runs\<run-id>` |
| 7. Promote to CI | Publish `runs/**`, read JUnit | `runs/<run-id>/reports/result.junit.xml` |

## Folder Artifact Pattern

Use this when your product can be tested from a folder.

Local artifact shape:

```text
my-artifact/
  run-smoke.ps1
  my-product.exe
  supporting-files/
```

Scenario shape:

```yaml
artifact:
  type: folder
  pathParam: artifactPath
  destination: "C:\\Oslab\\artifact"
  transfer: archive
  command:
    shell: powershell
    template: '& "{ArtifactDir}\run-smoke.ps1" -OutputPath "{OutputPath}"'
outputs:
  actual:
    path: "C:\\Oslab\\command-result.json"
    adapter: canonical.command
assertions:
  - type: command.exitCode
    id: exit-zero
    exitCode: 0
```

The script should write a result like this to `{OutputPath}`:

```json
{
  "schemaVersion": 1,
  "kind": "commandResult",
  "command": "my-product.exe --smoke",
  "exitCode": 0,
  "stdout": "smoke passed\r\n",
  "stderr": "",
  "metadata": {}
}
```

## Installer Artifact Pattern

Use this when installation itself is part of what you need to test.

```yaml
artifact:
  type: installer
  pathParam: artifactPath
  destination: "C:\\Oslab\\installer"
  installCommand:
    shell: powershell
    template: '& "{InstallerPath}" -InstallDir "C:\\Oslab\\installed"'
  command:
    shell: powershell
    template: '& "C:\\Oslab\\installed\\run-smoke.ps1" -OutputPath "{OutputPath}"'
outputs:
  actual:
    path: "C:\\Oslab\\command-result.json"
    adapter: canonical.command
```

`installCommand` validates setup/install behavior. `command` validates the installed product behavior.

## Fixture Pattern

Fixtures prepare the guest OS state before artifact upload/execution.

Use fixtures for:

- runtime/toolchain bootstrap
- registry baseline setup
- test account or policy setup
- expected inventory/result files
- template contamination checks

Avoid putting product execution in fixtures. Product execution belongs in `artifact.command` or `product.steps` so reports can classify failures correctly.

## Fast-Fail Checks And Smoke Commands

`preflight` and `*-smoke` commands are diagnostic tools. They are not replacements for a full product run; they narrow the broken boundary before you spend time on a full VM test.

| Command | Intent |
| --- | --- |
| `preflight` | Catch config/token/node/template/VMID range issues before creating a VM |
| `clone-smoke` | Check Proxmox clone/destroy lifecycle |
| `boot-smoke` | Check clone boot and QEMU Guest Agent readiness |
| `guest-preflight` | Check guest PowerShell/admin/file roundtrip prerequisites |
| `fixture-smoke` | Isolate fixture upload/execution/output collection |
| `artifact-smoke` | Isolate artifact upload/install/command/output collection |

When `oslab run` fails, use the smoke command that matches the failed phase to narrow the problem.

## Failure Triage

When a first run fails, inspect in this order:

| Order | What to check | Why |
| --- | --- | --- |
| 1 | `logs/progress.log` | Fastest readable timeline |
| 2 | `uv run oslab inspect-result --run-dir runs\<run-id>` | Summary, failure class, command output preview |
| 3 | `reports/result.html` | Human-readable report |
| 4 | `logs/product*.stderr.log` | Guest command error details |
| 5 | `raw/actual-output.json` | Confirm product wrote the expected raw file |
| 6 | `normalized/*.json` | Confirm adapter produced assertion input |
| 7 | `reports/result.junit.xml` | CI-facing failure classification |

For VM-level debugging, rerun with `--keep-vm`, use `qga-exec`, then check `preflight --provider-resource-check` after manual cleanup.

## CI Contract

CI should usually:

1. Run `uv run oslab run ...`.
2. Upload `runs/**` as a job artifact.
3. Publish `runs/<run-id>/reports/result.junit.xml` as the test report.
4. Keep `reports/result.html`, `run.json`, logs, raw, and normalized files for failure review.

Do not commit `runs/`, local config, or real secrets.
