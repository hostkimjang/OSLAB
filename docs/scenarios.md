# Scenario Authoring

Language: English | [한국어](scenarios.ko.md)

This page documents the practical YAML contract for current scenarios.

## Authoring Workflow

When you create a new scenario, write it in this order:

1. Choose the target OS/template and VMID range.
2. Decide the guest channel mode. Current Windows demos use QEMU Guest Agent.
3. Add fixtures only for guest setup prerequisites.
4. Define the artifact type, destination, and command.
5. Make the command write machine-readable output to `{OutputPath}`.
6. Set `outputs.actual.path` to the same guest path.
7. Choose an adapter such as `canonical.command`.
8. Add assertions over the normalized output.
9. Enable reports.
10. Keep cleanup enabled unless debugging.

The most common authoring bug is a mismatch between `artifact.command` and `outputs.actual.path`: the command succeeds but writes output somewhere `oslab` does not collect.

## Minimal Shape

```yaml
schemaVersion: 1
id: demo.python-hello.windows
name: Generic Python hello world Windows demo
os:
  family: windows
  version: "11"
provider:
  type: proxmox
  template: windows11-template-qga
  templateVmId: 9101
  vmIdRange:
    start: 9102
    end: 9199
guest:
  mode: auto
fixtures: []
artifact:
  type: folder
  pathParam: artifactPath
  destination: "C:\\Oslab\\artifact"
  transfer: archive
  command:
    shell: powershell
    template: '& "{ArtifactDir}\run.ps1" -OutputPath "{OutputPath}"'
outputs:
  actual:
    path: "C:\\Oslab\\command-result.json"
    adapter: canonical.command
assertions:
  - type: command.exitCode
    id: exit-zero
    exitCode: 0
reports:
  formats:
    - junit
    - json
    - html
cleanup:
  destroyVm: true
  keepVmOnFailure: false
```

## Top-Level Fields

| Field | Required | Description |
| --- | --- | --- |
| `schemaVersion` | Yes | Scenario schema version |
| `id` | Yes | Stable scenario id |
| `name` | Recommended | Human-readable name |
| `os` | Yes | OS family/version |
| `provider` | Yes | Provider type/template/VMID range |
| `guest` | Yes | Guest command strategy |
| `fixtures` | Optional | Guest setup scripts |
| `artifact` | Optional | Artifact upload and command contract |
| `product.steps` | Optional | Ordered command steps for agent-like products |
| `outputs` | Optional | Remote output path and adapter |
| `assertions` | Yes | Built-in/plugin assertions |
| `reports` | Optional | Report formats |
| `cleanup` | Optional | VM cleanup behavior |

## Field Responsibilities

| Field | Role in the run | Common mistake |
| --- | --- | --- |
| `provider` | Selects the template and VMID range used to create a disposable clone | Pointing at a normal VM instead of a stopped template |
| `guest` | Chooses how `oslab` talks to the VM | Assuming `auto` can work without QEMU Guest Agent/WinRM/SSH readiness |
| `fixtures` | Prepares guest state before artifact execution | Putting product execution here instead of in `artifact.command` |
| `artifact` | Defines what local file/folder is uploaded and how it runs | Forgetting `pathParam: artifactPath`, so CLI `--artifact-path` has nowhere to bind |
| `artifact.installCommand` | Installer-only setup command | Mixing install validation and product smoke validation into one command |
| `artifact.command` | Main command run after upload/install | Not writing the expected output file |
| `outputs.actual.path` | Remote path collected from the guest | Writing output somewhere else in the guest |
| `outputs.actual.adapter` | Normalizes raw output for assertions | Asserting against raw output shape instead of canonical shape |
| `assertions` | Defines pass/fail rules | Checking text that the adapter does not preserve |
| `reports` | Selects output formats | Expecting CI JUnit without enabling `junit` |
| `cleanup` | Controls VM deletion/retention | Keeping failed VMs without later checking the VMID range |

## Fixture Example

Fixtures run before the artifact command. Use them for guest setup, not for the main product validation.

```yaml
fixtures:
  - id: demo-python-runtime
    type: powershell
    source: validation/fixtures/windows/demo-python-runtime.ps1
    expectedOutput: "C:\\Oslab\\demo-python-runtime.json"
```

| Field | Meaning |
| --- | --- |
| `id` | Stable fixture id used in logs and reports |
| `type` | Fixture runner type, currently `powershell` for Windows demos |
| `source` | Local fixture script uploaded to the guest |
| `expectedOutput` | Optional guest path collected as fixture evidence |

If the fixture fails, the run should stop as `fixture_failure`. If the artifact command fails after setup succeeded, that should be reported separately as product/artifact execution failure.

See [Fixture Authoring](fixtures.md) for full fixture rules, manifest examples, and debugging commands.

## Command Template Tokens

| Token | Meaning |
| --- | --- |
| `{ArtifactDir}` | Remote artifact directory |
| `{InstallerPath}` | Remote installer path |
| `{OutputPath}` | Remote primary output path |
| `{AssetName}` | Generated/default asset name for product steps |

Unknown tokens are rejected when the command template is rendered before guest execution. `validate-scenario` checks schema shape; it is not a full dry run of every command token.

## Generic Demo Scenarios

| Scenario | Purpose |
| --- | --- |
| `scenarios/windows/demo-powershell-system.example.yaml` | Minimal PowerShell command-result demo |
| `scenarios/windows/demo-python-hello.example.yaml` | Bootstrap Python and run `hello.py` |
| `scenarios/windows/demo-c-hello.example.yaml` | Bootstrap TinyCC and compile/run `hello.c` |
| `scenarios/windows/demo-fixture-state.example.yaml` | Fixture writes VM state and artifact reads it |
| `scenarios/windows/demo-agent-steps.example.yaml` | Ordered product steps with stdout JSON and inventory output |
| `scenarios/windows/demo-python-unittest.example.yaml` | Python unit test execution inside the VM |
| `scenarios/windows/demo-python-http-service.example.yaml` | Python local HTTP service smoke test |
| `scenarios/windows/demo-c-unit.example.yaml` | Multi-file C compile/link/unit-test demo |
| `scenarios/windows/demo-intentional-assertion-failure.example.yaml` | Intentional assertion failure for report/JUnit learning |
| `scenarios/windows/fake-artifact-smoke.example.yaml` | Fake inventory-producing folder artifact |
| `scenarios/windows/fake-installer-smoke.example.yaml` | Fake installer then product command |
| `scenarios/linux/generic-smoke.example.yaml` | Linux schema/design example |

## Minimal Custom Artifact Examples

Folder artifact:

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
```

Installer artifact:

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

In both cases, the command should write machine-readable output to `outputs.actual.path`. For `canonical.command`, write a `commandResult` JSON object.

## Artifact Command Output Contract

For `canonical.command`, the remote output file should look like this:

```json
{
  "schemaVersion": 1,
  "kind": "commandResult",
  "command": "python hello.py",
  "exitCode": 0,
  "stdout": "hello from python\n",
  "stderr": "",
  "metadata": {
    "runtime": "python"
  }
}
```

Required fields:

| Field | Meaning |
| --- | --- |
| `schemaVersion` | Output schema version |
| `kind` | Must be `commandResult` for `canonical.command` |
| `command` | Human-readable command label |
| `exitCode` | Process exit code |
| `stdout` | Captured stdout text |
| `stderr` | Captured stderr text |
| `metadata` | Optional object for runtime/compiler/version/path details |

The artifact command may also write stdout/stderr to the console, but assertions use the collected JSON file. Console output alone is not enough for `canonical.command`.

Minimal PowerShell writer:

```powershell
param(
  [Parameter(Mandatory = $true)]
  [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$stdout = "hello from my artifact"
$result = @{
  schemaVersion = 1
  kind = "commandResult"
  command = "run-smoke"
  exitCode = 0
  stdout = "$stdout`n"
  stderr = ""
  metadata = @{}
}

$result |
  ConvertTo-Json -Depth 10 |
  Set-Content -Encoding UTF8 $OutputPath
```

## Expected Run Flow

A passing folder-artifact scenario should follow this lifecycle:

```text
validate scenario
provider config/connectivity/resource preflight
allocate VMID
create ephemeral clone
start VM
wait for guest channel
run guest preflight
run fixtures
prepare artifact directory
upload artifact archive
expand artifact in guest
run artifact command
collect outputs.actual.path
normalize output with adapter
evaluate assertions
write reports
destroy VM clone
```

Expected progress markers:

```text
[OK] provider.preflight.done - Proxmox resource preflight passed
[OK] vm.clone.done - Ephemeral VM clone created
[OK] guest.ready.done - QEMU Guest Agent is ready
[OK] preflight.done - Guest preflight passed
[OK] fixture.all.done - Scenario fixtures applied
[OK] artifact.upload.done - Artifact folder uploaded
[OK] product.command.done - Product command completed
[OK] output.normalize.done - Product output normalized
[OK] assertions.done - Assertions passed
[OK] run.done - Run completed
    status: passed
    failureClass: <none>
```

Expected run files:

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
    fixture-<id>.expected-output.json
  normalized/
    command-result.json
  reports/
    result.junit.xml
    result.json
    result.html
```

## Product-Specific Scenarios

Product-specific scenarios should be documented in product-owned docs outside the generic scenario authoring path. The generic docs should explain the platform contract, not one private product workflow.
