# oslab Platform Plan

Language: English | [한국어](oslab-platform-plan.ko.md)

## Executive Summary

`oslab is a provider-driven, scenario-based OS integration test platform for validating software inside disposable Windows and Linux VMs.`

The public goal of `oslab` is not to provide a validation tool for one specific product. It is a general-purpose OS/VM integration test platform for repeatedly validating software artifacts across combinations of OS versions, OS settings, runtime states, and preinstalled software.

The current public entry point is a generic demo suite that runs on Windows Proxmox templates. It validates the following capabilities without requiring any product-specific knowledge:

- Create a disposable VM clone from a Proxmox template
- Verify guest readiness through the QEMU Guest Agent
- Prepare the guest runtime and toolchain with fixtures
- Artifact folder upload
- Guest command execution
- Output collection
- Canonical result normalization
- Assertion evaluation
- JSON, JUnit XML, and HTML report generation
- Incremental run progress logging
- VM cleanup

Product-specific adapters, private scenarios, and private credential flows are not the focus of the public platform plan. This document defines the boundaries and contracts of the `oslab` core.

## Why It Exists

Unit, mock, and container tests are fast and important, but they cannot detect every issue that appears only in a real OS environment.

Examples:

- Does the same artifact work on Windows 10, Windows 11, Windows Server, Ubuntu, and other target systems?
- Does it behave consistently on both a clean image and an image with multiple runtimes already installed?
- Can it tolerate differences in registry state, services, policy, firewalls, user context, language packs, and patch levels?
- Can fixtures prepare the environment and run the test reliably even when the VM lacks the required runtime prerequisites?
- Can CI compare results from multiple OS and state combinations in the same report format?

`oslab` is a platform for solving these problems once instead of reimplementing the same infrastructure for every product. The core handles the VM lifecycle, guest command and file transport, fixtures, artifact execution, assertions, and reports, while adapters and plugins isolate product-specific output interpretation.

## Public Documentation Boundary

Public documentation remains focused on the generic demos and product-neutral platform concepts.

| Content | Public docs role |
| --- | --- |
| Generic demo suite | Default learning path |
| Proxmox/QGA setup | Lab connectivity and template preparation |
| Scenario YAML | Authoring general-purpose test recipes |
| Fixture | Preparing test prerequisites inside the VM |
| Artifact | File, folder, or installer under test |
| Canonical command result | Results from small executable and CLI smoke tests |
| Canonical inventory result | Shared result model for inventory-producing products |
| Product-specific scenarios | Kept in separate private or product documentation |

## Scope

| Area | Implemented/Public MVP | Future |
| --- | --- | --- |
| Provider | Proxmox | libvirt, cloud VM providers, local runners |
| OS | Windows execution with QEMU Guest Agent | Linux execution with SSH/QGA |
| Demo products | PowerShell system, Python hello world, C hello world, fixture state handoff, agent steps, intentional failure | Go, .NET, service, installer demos |
| Artifact type | Folder, installer-oriented flow | Remote artifact source, package registry |
| Fixtures | Windows PowerShell fixtures | Linux shell fixtures, reusable fixture catalog |
| Guest channel | QEMU Guest Agent for Windows path | WinRM fallback, SSH primary for Linux |
| Result models | `canonical.command`, `canonical.inventory` | More canonical schemas |
| Reports | JSON, JUnit XML, HTML, progress logs | TRX, dashboard, trend comparison |
| Test definition | YAML scenario | Versioned schemas, UI authoring |
| CI | Thin CLI wrapper model | GitHub/GitLab examples, matrix templates |

## Core Principles

| Principle | Decision |
| --- | --- |
| Product neutrality | Core must not depend on private product code or private scenario semantics. |
| Disposable execution | Default run creates and destroys one ephemeral VM clone. |
| Scenario-first | YAML scenario is the public test definition interface. |
| Provider abstraction | Proxmox is the first provider, not a permanent core assumption. |
| Guest abstraction | QGA, WinRM, and SSH implement the same command/file interface. |
| Fixture separation | VM preparation is separate from product execution. |
| Artifact separation | The artifact is the thing being tested, not the lab setup. |
| Structured failure | Provider, VM, guest, fixture, artifact, product, assertion, report, cleanup failures are separated. |
| CI neutrality | Local and CI execution use the same CLI contract. |
| Evidence-first reports | Every run produces logs, raw data, normalized data, and reports under `runs/<run-id>/`. |

## High-Level Architecture

```mermaid
flowchart TD
    A["Scenario YAML"] --> B["oslab CLI"]
    C["Local/CI Config"] --> B
    D["Environment Secrets"] --> B

    B --> E["Scenario Runner"]
    E --> F["Provider Interface"]
    F --> G["Proxmox Provider"]
    G --> H["Ephemeral VM Clone"]

    E --> I["Guest Channel Selector"]
    I --> J["QEMU Guest Agent"]
    I --> K["WinRM"]
    I --> L["SSH"]

    E --> M["Preflight Runner"]
    E --> N["Fixture Runner"]
    E --> O["Artifact Manager"]
    E --> P["Product Command Executor"]

    N --> Q["Fixture Outputs"]
    O --> R["Uploaded Artifact"]
    P --> S["Raw Product Output"]

    S --> T["Adapter / Normalizer"]
    T --> U["Canonical Result Model"]
    U --> V["Assertion Engine"]
    U --> W["Optional Analysis"]

    V --> X["Report Writers"]
    W --> X
    X --> Y["JSON Report"]
    X --> Z["JUnit XML"]
    X --> AA["HTML Report"]
    X --> AB["Progress Logs"]
```

## Component Responsibilities

| Component | Responsibility | Product-specific? |
| --- | --- | --- |
| CLI | Parse commands, options, config paths, env file paths | No |
| Scenario Loader | Parse and validate YAML scenario shape | No |
| Config Resolver | Merge CLI, scenario, local config, env, defaults | No |
| Scenario Runner | Orchestrate one run lifecycle | No |
| Provider | VM clone/start/stop/destroy/status | No |
| Guest Channel | Execute commands and upload/download files inside VM | No |
| Preflight Runner | Verify guest readiness and baseline capabilities | No |
| Fixture Runner | Prepare OS/runtime/tooling state before artifact execution | Mostly no |
| Artifact Manager | Upload artifact folder/installer and prepare remote paths | No |
| Product Command Executor | Execute scenario-defined command or ordered steps | No |
| Adapter / Normalizer | Convert raw output into canonical result | Sometimes |
| Assertion Engine | Evaluate pass/fail/error/skipped | No |
| Analysis | Summarize canonical result quality/distribution | No |
| Report Writers | Emit JSON, JUnit XML, HTML, progress logs | No |

## Execution Sequence

```mermaid
sequenceDiagram
    participant User
    participant CLI as oslab CLI
    participant Runner as Scenario Runner
    participant Provider as Provider
    participant Guest as Guest Channel
    participant Adapter as Adapter
    participant Reports as Report Writers

    User->>CLI: oslab run --scenario ... --artifact-path ...
    CLI->>Runner: Load scenario, config, env
    Runner->>Provider: Allocate VMID
    Runner->>Provider: Create ephemeral clone
    Provider-->>Runner: VM reference
    Runner->>Provider: Start VM
    Runner->>Guest: Wait/probe guest channel
    Guest-->>Runner: Selected channel
    Runner->>Guest: Run guest preflight
    Runner->>Guest: Upload and execute fixtures
    Runner->>Guest: Prepare artifact directory
    Runner->>Guest: Upload artifact
    Runner->>Guest: Execute artifact command or product steps
    Runner->>Guest: Collect raw outputs
    Runner->>Adapter: Normalize raw output
    Adapter-->>Runner: Canonical result
    Runner->>Runner: Evaluate assertions
    Runner->>Reports: Write run.json, JSON, JUnit, HTML, logs
    Runner->>Provider: Stop and destroy clone
    Runner-->>CLI: Return final run status
```

## Configuration Model

Local lab settings are stored in ignored config files. Secret values are read from environment variables or an env file and must not be committed.

```yaml
providerDefaults:
  proxmox:
    apiUrl: "https://proxmox.example.local:8006"
    node: "pve01"
    verifyTls: false
    timeoutSeconds: 30
    tokenEnv:
      id: OSLAB_PROXMOX_TOKEN_ID
      secret: OSLAB_PROXMOX_TOKEN_SECRET
runDefaults:
  outputRoot: runs
  keepVmOnFailure: false
```

Resolution order:

1. CLI args
2. Scenario YAML
3. Local config file
4. Environment variables/env file
5. Built-in defaults

## CLI Contract

Main public commands:

```powershell
uv run oslab validate-scenario --scenario scenarios/windows/demo-python-hello.example.yaml
uv run oslab preflight --scenario scenarios/windows/demo-python-hello.example.yaml --provider-resource-check
uv run oslab run --scenario scenarios/windows/demo-python-hello.example.yaml --artifact-path validation/artifacts/hello-python
uv run oslab inspect-result --run-dir runs\<run-id>
```

Debug and local analysis commands:

```powershell
uv run oslab boot-smoke --scenario scenarios/windows/demo-python-hello.example.yaml --keep-vm
uv run oslab guest-preflight --scenario scenarios/windows/demo-python-hello.example.yaml
uv run oslab qga-exec --vm-id 9102 -- powershell.exe -NoProfile -Command whoami
uv run oslab normalize-output --scenario scenarios/windows/fake-artifact-smoke.example.yaml --input-json raw.json --output-json normalized.json
uv run oslab assert-result --scenario scenarios/windows/demo-python-hello.example.yaml --actual-json result.json
```

Exit code categories:

| Exit Code | Meaning |
| --- | --- |
| `0` | Passed |
| `10-19` | Scenario/config/preflight failure |
| `20-29` | Provider/VM/guest failure |
| `30-39` | Fixture/artifact/product execution failure |
| `40-49` | Adapter/assertion/report failure |
| `50-59` | Cleanup/stale resource failure |

## Provider Abstraction

`Provider` owns VM lifecycle only. It does not execute commands inside the guest.

```python
class Provider:
    def create_clone(self, template, vm_spec): ...
    def start_vm(self, vm): ...
    def stop_vm(self, vm): ...
    def destroy_vm(self, vm): ...
    def get_vm_status(self, vm): ...
    def get_guest_info(self, vm): ...
```

| Method | Proxmox MVP behavior |
| --- | --- |
| `create_clone` | Clone from a stopped template VM |
| `start_vm` | Start clone and poll task completion/status |
| `stop_vm` | Stop clone before destroy when needed |
| `destroy_vm` | Destroy clone with purge |
| `get_vm_status` | Read VM status from Proxmox |
| `get_guest_info` | Read guest agent/network info when available |

### Proxmox Task Handling

Proxmox operations commonly return async task ids. The provider must poll completion rather than assuming the request is done.

| Operation | Required handling |
| --- | --- |
| clone | Poll task completion; classify timeout/error as `vm_clone_failure` |
| start | Poll VM running status; guest readiness is checked separately |
| stop | Treat already-stopped VM as success |
| destroy | Poll task completion; write stale VM metadata on failure |

### VMID Allocation

```yaml
provider:
  type: proxmox
  template: windows11-template-qga-9200
  templateVmId: 9200
  vmIdRange:
    start: 9102
    end: 9199
```

Rules:

- If `--vm-id` is supplied, use it.
- Otherwise allocate the first available VMID in `vmIdRange`.
- Use a local lock under the run output root to reduce local collision risk.
- CI concurrency should be controlled by resource groups/job concurrency.
- Allocation failure is `provider_failure`.

## Guest Channel API

```python
class GuestChannel:
    def probe(self): ...
    def upload(self, local_path, remote_path): ...
    def download(self, remote_path, local_path): ...
    def exec(self, command, timeout): ...
```

Command result shape:

```json
{
  "exitCode": 0,
  "stdout": "hello\n",
  "stderr": "",
  "durationMs": 1234,
  "channel": "qemuAgent"
}
```

| Channel | OS | Role |
| --- | --- | --- |
| QEMU Guest Agent | Windows, Linux | Current execution path for Windows and Linux |
| WinRM | Windows | Future/fallback Windows channel |
| SSH | Linux | Future primary Linux channel |

## Guest Channel Selection Flow

```mermaid
flowchart TD
    A["Scenario guest.mode"] --> B{Mode}
    B -->|qemuAgent| C["Use QEMU Guest Agent only"]
    B -->|winrm| D["Use WinRM only"]
    B -->|ssh| E["Use SSH only"]
    B -->|auto| F{OS Family}

    F -->|Windows| G["Probe QEMU Guest Agent"]
    G -->|Pass| H["Use QEMU Guest Agent"]
    G -->|Fail| I["Probe WinRM"]
    I -->|Pass| J["Use WinRM"]
    I -->|Fail| K["guest_channel_failure"]

    F -->|Linux| L["Probe SSH"]
    L -->|Pass| M["Use SSH"]
    L -->|Fail| N["Probe QEMU Guest Agent"]
    N -->|Pass| O["Use QEMU Guest Agent"]
    N -->|Fail| K
```

## Guest Preflight Contract

Preflight checks that the clone can execute the scenario before doing expensive artifact work.

Windows MVP checks:

| Check | Meaning | Failure |
| --- | --- | --- |
| `powershell.version` | PowerShell can run | `preflight_failure` |
| `windows.admin` | Commands run in admin-capable context | `preflight_failure` |
| `powershell.execution_policy` | Execution policy is queryable | `preflight_failure` |
| `oslab.directory` | `C:\Oslab` can be created | `preflight_failure` |
| `oslab.file_roundtrip` | Guest upload/download works | `preflight_failure` |
| `oslab.cleanup_test_file` | Temporary files can be removed | `preflight_failure` |

With `guest.screen.signIn: true`, the `desktop.sign_in` check comes first. It passes when the desktop test account is signed in and the automatic logon password is removed again, and fails with `preflight_failure` otherwise.

Linux design checks:

| Check | Meaning | Failure |
| --- | --- | --- |
| `shell.available` | `sh` or configured shell can run | `preflight_failure` |
| `workdir.writable` | `/tmp/oslab` or configured workdir is writable | `preflight_failure` |
| `os-release.readable` | `/etc/os-release` can be read | `preflight_failure` |
| `file.roundtrip` | Upload/download works through SSH/SFTP or QGA | `preflight_failure` |

## Fixture Model

Fixtures prepare the VM before the artifact is executed.

They are for:

- Installing or locating runtime prerequisites
- Preparing registry, files, services, policy, test data
- Creating expected output/reference data
- Verifying that the guest has the baseline needed by the scenario

They are not for:

- Running the product under test as the main validation target
- Hiding product execution failures as setup failures
- Storing secret values in scenario files

Example:

```yaml
fixtures:
  - id: demo-python-runtime
    type: powershell
    source: validation/fixtures/windows/demo-python-runtime.ps1
    expectedOutput: "C:\\Oslab\\demo-python-runtime.json"
```

If a Python runtime is absent, the fixture may install a portable runtime inside the disposable clone. If fixture setup fails, the run should stop as `fixture_failure`.

## Artifact Interface

Supported public MVP artifact types:

```yaml
artifact:
  type: folder
  pathParam: artifactPath
  destination: "C:\\Oslab\\artifact"
  transfer: archive
```

```yaml
artifact:
  type: installer
  pathParam: artifactPath
  destination: "C:\\Oslab\\installer\\app-installer.exe"
  installCommand:
    shell: powershell
    template: '& "{InstallerPath}" /quiet /norestart'
```

| Type | Behavior |
| --- | --- |
| `folder` | Upload local folder to guest, then run scenario command |
| `installer` | Upload installer, run install command, then run scenario command/steps |

## Scenario YAML Contract

Required top-level fields:

| Field | Required | Description |
| --- | --- | --- |
| `schemaVersion` | Yes | Scenario schema version |
| `id` | Yes | Stable scenario id |
| `os` | Yes | OS family/version |
| `provider` | Yes | Provider type/template |
| `guest` | Yes | Guest command strategy |
| `artifact` | Optional | Artifact upload/install contract |
| `fixtures` | Optional | OS setup scripts |
| `product` | Optional | Ordered command steps for agent-like products |
| `outputs` | Optional | Files to collect |
| `assertions` | Yes | Built-in/plugin assertions |
| `reports` | Optional | Report formats |
| `cleanup` | Optional | VM cleanup policy |

### Windows Python Demo Scenario

```yaml
schemaVersion: 1
id: demo.python-hello.windows
name: Generic Python hello world Windows demo
os:
  family: windows
  version: "11"
provider:
  type: proxmox
  template: windows11-template-qga-9200
  templateVmId: 9200
  vmIdRange:
    start: 9102
    end: 9199
isolation:
  mode: ephemeralClone
guest:
  mode: auto
  windowsOrder:
    - qemuAgent
    - winrm
fixtures:
  - id: demo-python-runtime
    type: powershell
    source: validation/fixtures/windows/demo-python-runtime.ps1
    expectedOutput: "C:\\Oslab\\demo-python-runtime.json"
artifact:
  type: folder
  pathParam: artifactPath
  destination: "C:\\Oslab\\artifact"
  transfer: archive
  command:
    shell: powershell
    template: '& "{ArtifactDir}\run-python-demo.ps1" -OutputPath "{OutputPath}"'
outputs:
  actual:
    path: "C:\\Oslab\\command-result.json"
    adapter: canonical.command
assertions:
  - type: command.exitCode
    id: python-exit-zero
    exitCode: 0
  - type: command.stdoutContains
    id: python-stdout-hello
    text: hello from python
reports:
  formats:
    - junit
    - json
    - html
cleanup:
  destroyVm: true
  keepVmOnFailure: false
```

### Windows C Demo Scenario

```yaml
schemaVersion: 1
id: demo.c-hello.windows
name: Generic C hello world Windows demo
os:
  family: windows
provider:
  type: proxmox
  template: windows11-template-qga-9200
  templateVmId: 9200
guest:
  mode: auto
fixtures:
  - id: demo-c-compiler
    type: powershell
    source: validation/fixtures/windows/demo-c-compiler.ps1
artifact:
  type: folder
  pathParam: artifactPath
  destination: "C:\\Oslab\\artifact"
  transfer: archive
  command:
    shell: powershell
    template: '& "{ArtifactDir}\run-c-demo.ps1" -OutputPath "{OutputPath}"'
outputs:
  actual:
    path: "C:\\Oslab\\command-result.json"
    adapter: canonical.command
assertions:
  - type: command.exitCode
    id: c-exit-zero
    exitCode: 0
  - type: command.stdoutContains
    id: c-stdout-hello
    text: hello from c
```

### Linux Design Scenario

Linux execution is a design target. The schema should not require Windows-only concepts.

```yaml
schemaVersion: 1
id: demo.shell-hello.linux
name: Generic Linux shell hello demo
os:
  family: linux
provider:
  type: proxmox
  template: ubuntu-2404-base-template
  vmIdRange:
    start: 9200
    end: 9299
guest:
  mode: auto
  linuxOrder:
    - ssh
    - qemuAgent
fixtures:
  - id: baseline
    type: shell
    source: validation/fixtures/linux/generic-smoke.sh
artifact:
  type: folder
  pathParam: artifactPath
  destination: "/tmp/oslab/artifact"
  command:
    shell: sh
    template: '"{ArtifactDir}/hello.sh" > "{OutputPath}"'
outputs:
  actual:
    path: "/tmp/oslab/command-result.json"
    adapter: canonical.command
assertions:
  - type: command.exitCode
    id: shell-exit-zero
    exitCode: 0
```

## Command Template Rules

Command templates are necessary because product entrypoints differ. They are risky because shell quoting differs by OS and channel.

Rules:

- Scenario commands must declare `shell`.
- Supported MVP shells are `powershell`, `cmd`, `sh`, and `bash`.
- Token replacement is limited to documented tokens.
- Unknown tokens fail before guest execution.
- Rendered command metadata must redact secret values.
- Secret values must not be written to reports or progress logs.

Supported public tokens:

| Token | Meaning |
| --- | --- |
| `{ArtifactDir}` | Remote artifact directory |
| `{InstallerPath}` | Remote installer path |
| `{OutputPath}` | Remote primary output path |
| `{RunId}` | Current run id |
| `{ScenarioId}` | Scenario id |
| `{VmId}` | Current clone VMID |
| `{WorkDir}` | Remote work directory |

## Product Steps

Simple demos use one `artifact.command`. Agent-like products may need ordered steps such as install, configure, status, run, export. `product.steps` provides that generic execution model.

```yaml
product:
  steps:
    - id: configure
      command:
        shell: powershell
        template: '& "{ArtifactDir}\example-agent.exe" configure --server "{ServerUrl}" --json'
      secretTokens:
        ServerUrl:
          env: OSLAB_PRODUCT_SERVER_URL
      captureStdoutJson: true
    - id: status
      command:
        shell: powershell
        template: '& "{ArtifactDir}\example-agent.exe" status --json'
      captureStdoutJson: true
      expectStdoutJson:
        ok: true
        registered: true
    - id: run
      command:
        shell: powershell
        template: '& "{ArtifactDir}\example-agent.exe" run --output "{OutputPath}" --json'
      captureStdoutJson: true
      expectStdoutJson:
        ok: true
        outputWritten: true
```

Rules:

- Steps run in order.
- A failed required step stops later steps.
- Step stdout/stderr are collected.
- `captureStdoutJson` parses stdout as a JSON object.
- `expectStdoutJson` optionally declares required stdout JSON fields. Dotted keys such as `policy.id` can address nested objects.
- Secret tokens are read from host env and redacted in logs/reports.
- Step results are included in `run.json` and raw output files.

## Adapter And Plugin Model

```mermaid
flowchart LR
    A["Raw Product Output"] --> B{Adapter Type}
    B -->|Built-in Adapter| C["canonical.command / canonical.inventory"]
    B -->|Python Plugin| D["normalize_output()"]
    B -->|Executable Plugin| E["plugin normalize"]
    C --> F["Canonical Result Model"]
    D --> F
    E --> F
    F --> G["Built-in Assertions"]
    F --> H["Plugin Assertions"]
    G --> I["Assertion Results"]
    H --> I
```

Python plugin protocol:

```python
def plugin_metadata() -> dict: ...

def normalize_output(context, raw_output_path): ...

def assertions() -> list: ...
```

Executable plugin protocol:

```powershell
plugin.exe normalize --input raw.json --output normalized.json --context context.json
plugin.exe assert --input normalized.json --scenario scenario.fragment.json --output assertions.json
```

Failure rules:

- Non-zero plugin process exit is `plugin_failure`.
- Missing/invalid output JSON is `plugin_failure`.
- Valid assertion mismatch is `assertion_failure`.

## Canonical Result Models

### `canonical.command`

Small executable, compiler, CLI, and hello-world smoke tests use `canonical.command`.

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

### `canonical.inventory`

Inventory-producing products use `canonical.inventory`.

```json
{
  "schemaVersion": 1,
  "kind": "inventory",
  "records": [
    {
      "name": "Example App",
      "version": "1.2.3",
      "publisher": "Example Publisher",
      "sources": ["packageManager"],
      "confidence": "high",
      "evidence": [
        {
          "type": "package",
          "source": "packageManager",
          "path": "example-app"
        }
      ],
      "metadata": {}
    }
  ]
}
```

## Analysis

Analysis is optional and product-neutral. For inventory results, `oslab` can summarize record counts, source distribution, publisher distribution, confidence distribution, and quality warnings.

```powershell
uv run oslab analyze-inventory `
  --inventory-json runs\<run-id>\normalized\inventory.json `
  --output-json runs\<run-id>\reports\inventory.analysis.json
```

## Assertion Model

MVP built-in assertions:

| Assertion | Purpose |
| --- | --- |
| `command.exitCode` | Check normalized command exit code |
| `command.stdoutContains` | Check normalized stdout text |
| `command.stderrContains` | Check normalized stderr text |
| `file.exists` | Check remote file exists |
| `file.notExists` | Check remote file does not exist |
| `directory.exists` | Check remote directory exists |
| `service.exists` | Check OS service exists |
| `process.exists` | Check process exists |
| `package.exists` | Check package exists |
| `inventory.contains` | Check canonical inventory contains matching record |
| `inventory.sourcePresent` | Check source exists in an inventory record |
| `inventory.sourceAbsent` | Check source is absent |
| `inventory.evidencePresent` | Check evidence exists |

`file.*`, `directory.*`, `process.exists`, `service.exists`, and `package.exists` evaluate reported state in normalized output metadata. The core runner does not perform a second guest query during assertion evaluation; scenario artifacts or adapters must emit checked state in fields such as `metadata.files`, `metadata.directories`, `metadata.processes`, `metadata.services`, and `metadata.packages`.

Assertion result:

```json
{
  "id": "python-stdout-hello",
  "status": "passed",
  "severity": "error",
  "message": "stdout contains expected text",
  "details": {}
}
```

Status values:

- `passed`
- `failed`
- `skipped`
- `error`

## Failure Taxonomy

```mermaid
flowchart TD
    A["Run Start"] --> B["Provider Setup"]
    B -->|Fail| F1["provider_failure"]
    B --> C["VM Clone"]
    C -->|Fail| F2["vm_clone_failure"]
    C --> D["Guest Ready"]
    D -->|Timeout| F3["guest_ready_timeout"]
    D --> E["Guest Channel"]
    E -->|Fail| F4["guest_channel_failure"]
    E --> G["Preflight"]
    G -->|Fail| F5["preflight_failure"]
    G --> H["Fixture"]
    H -->|Fail| F6["fixture_failure"]
    H --> I["Artifact"]
    I -->|Fail| F7["artifact_failure"]
    I --> J["Product Execution"]
    J -->|Fail| F8["product_execution_failure"]
    J --> K["Adapter Normalize"]
    K -->|Fail| F9["plugin_failure"]
    K --> L["Assertions"]
    L -->|Fail| F10["assertion_failure"]
    L --> M["Reports"]
    M -->|Fail| F11["report_failure"]
    M --> N["Cleanup"]
    N -->|Fail| F12["cleanup_failure"]
    N --> O["Run Complete"]
```

| Failure | Meaning |
| --- | --- |
| `provider_failure` | Provider config/API/auth/setup problem |
| `vm_clone_failure` | Clone operation failed or timed out |
| `guest_ready_timeout` | VM started but guest readiness timed out |
| `guest_channel_failure` | No usable command/file channel |
| `preflight_failure` | OS baseline does not satisfy scenario |
| `fixture_failure` | Fixture failed |
| `artifact_failure` | Artifact upload/install/prepare failed |
| `product_execution_failure` | Product command/step failed |
| `plugin_failure` | Adapter/plugin crashed or violated protocol |
| `assertion_failure` | Validation assertion failed |
| `report_failure` | Report writing failed |
| `cleanup_failure` | VM cleanup failed |

## Report Output Layout

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
    product-steps.json
    fixture-<id>.expected-output.json
  normalized/
    command-result.json
    inventory.json
  reports/
    result.junit.xml
    result.json
    result.html
    inventory.analysis.json
```

Not every scenario creates every file. Command-result demos create `normalized/command-result.json`; inventory scenarios create `normalized/inventory.json`.

`progress.log` and `progress.jsonl` are written incrementally while the run is active. The text log is for humans; JSONL is for future dashboards and CI parsers.

## JUnit Mapping

| oslab status | JUnit representation |
| --- | --- |
| Infrastructure/setup error | testcase `error` |
| Assertion mismatch | testcase `failure` |
| Optional check skipped | testcase `skipped` |
| Passed assertion | testcase pass |

JSON is the source of truth. JUnit is the CI interface. HTML is the human-readable report.

## Cleanup Policy

Default:

```yaml
cleanup:
  destroyVm: true
  keepVmOnFailure: false
```

Debug override:

```powershell
uv run oslab run --scenario scenarios/windows/demo-python-hello.example.yaml --keep-vm-on-failure
```

Rules:

- Successful runs destroy the clone.
- Failed runs destroy the clone by default.
- `--keep-vm-on-failure` preserves the VM for debugging.
- Cleanup failure writes stale VM metadata to `run.json`.
- Future stale cleanup command removes old validation VMs by label/range.

## Implementation Phases

| Phase | Goal | Public acceptance |
| --- | --- | --- |
| 1. Platform skeleton | CLI, package, run directory basics | `uv run oslab --help` |
| 2. Scenario/config loader | YAML/config/env resolution | `validate-scenario` passes demo scenarios |
| 3. Proxmox provider | Auth, clone/start/stop/destroy/status, VMID allocation | `preflight --provider-resource-check` |
| 4. Guest channel | QGA Windows path, selector contract | Guest can execute PowerShell command |
| 5. Preflight | Guest readiness checks | `guest-preflight` passes template clone |
| 6. Fixtures | PowerShell fixture execution/output collection | Python/C runtime fixtures pass |
| 7. Artifact execution | Folder upload/archive expansion/command execution | Python/C demo commands run |
| 8. Adapters | `canonical.command`, `canonical.inventory` | Normalized JSON written |
| 9. Assertions | Built-in command/inventory assertions | Demo assertions pass/fail deterministically |
| 10. Reports | JSON, JUnit, HTML, progress logs | `runs/<run-id>/reports/*` exists |
| 11. Linux design | Validate Linux schema without Windows assumptions | Linux example scenario validates |
| 12. CI examples | Thin wrappers around CLI | Local/CI command parity |

## Test Plan

### Unit Tests

- Scenario YAML parsing
- Config/env/default resolution
- Command template token replacement
- Secret redaction
- Provider fake implementation
- Guest channel auto-selection
- QGA file transfer helpers
- Fixture execution model
- Artifact folder/archive behavior
- Product step ordering and stdout JSON parsing
- Built-in adapter normalization
- Assertion pass/fail/error mapping
- JSON/JUnit/HTML report writers
- Inventory analysis

### Integration Tests Without Real VM

Use fake provider and fake guest channel.

| Scenario | Expected result |
| --- | --- |
| Python command success | Passed |
| C command success | Passed |
| Fixture failure | `fixture_failure` and product command skipped |
| Artifact upload failure | `artifact_failure` |
| Product non-zero exit | `product_execution_failure` |
| Assertion mismatch | `assertion_failure` with reports written |
| Cleanup failure | Stale VM metadata recorded |
| Linux scenario validation | Schema pass, real execution through QEMU Guest Agent |

### Real Lab Smoke Tests

Requires:

- Proxmox API access
- Windows template VM
- QEMU Guest Agent installed in Windows
- QEMU Guest Agent enabled in Proxmox VM options
- Guest internet access if demo fixtures download runtime/toolchain

Python demo:

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-python-hello.example.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/hello-python
```

C demo:

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-c-hello.example.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/hello-c
```

Pass criteria:

- Ephemeral clone created
- VM reaches running state
- QGA becomes ready
- Guest preflight passes
- Fixture prepares runtime/toolchain
- Artifact uploads by archive transfer
- Product command exits `0`
- Output JSON is collected
- `canonical.command` result is written
- Assertions pass
- JSON/JUnit/HTML reports are created
- VM clone is destroyed

## Implementation Readiness Checklist

- [ ] Public docs describe generic OS/VM integration testing, not a private product workflow.
- [ ] Scenario schema is stable enough for public demo use.
- [ ] Provider API does not leak Proxmox-specific fields into core contracts.
- [ ] Guest channel selection supports Windows now and Linux later.
- [ ] Fixtures are clearly documented as VM environment setup.
- [ ] Artifact execution is separate from fixture setup.
- [ ] Product-specific logic is isolated in adapters/plugins/scenarios.
- [ ] Reports are product-neutral.
- [ ] Failure taxonomy covers setup, execution, validation, report, and cleanup.
- [ ] Local and CI execution use the same CLI contract.
- [ ] Fake provider/guest tests can validate core without a real Proxmox lab.
- [ ] Demo scenarios are enough for new users to learn the platform without private product knowledge.

## Public Release Notes For This Plan

Before publishing the repository:

- Keep public README focused on generic demo usage.
- Keep private/product-specific scenario notes outside the public platform plan.
- Do not commit local config, env files, lab IPs, API tokens, or product credentials.
- Make sure `demo-python-hello` and `demo-c-hello` are the first learning path.
- Make sure Proxmox template prerequisites are documented before the run command.
- Make sure `runs/` artifacts are ignored or cleaned before release.
