# Concepts

Language: English | [한국어](concepts.ko.md)

`oslab` is organized around a small set of product-neutral concepts.

The easiest mental model is:

```text
Prepare a virtual machine (VM)
  -> set up the guest environment
  -> upload the thing under test
  -> run it inside the VM
  -> collect the result file
  -> translate it into a common scoring model
  -> decide pass/fail
  -> write reports for humans and CI
```

In short, `oslab` automates the test room, the setup, the product execution, the scoring input, and the report.

## Lifecycle Map

| Concept | Input | Role | Output |
| --- | --- | --- | --- |
| Scenario | YAML file | Describes the whole test contract | Run plan |
| Provider | Scenario provider block + config | Manages disposable VM lifecycle | VM reference/status |
| Guest channel | Guest mode and VM reference | Executes commands and transfers files | Command/file results |
| Fixture | Fixture script | Prepares guest OS state | Fixture logs and optional expected output |
| Artifact | `--artifact-path` | Supplies the product/folder/installer under test | Remote artifact path |
| Artifact command | Scenario command template | Runs the uploaded artifact inside the VM | Raw output file in guest |
| Adapter | Raw output JSON | Converts product-specific or command output into canonical data | `normalized/*.json` |
| Assertion | Scenario assertions | Evaluates normalized data | Pass/fail results |
| Report | Run result and assertion results | Writes CI/human/automation output | JUnit, JSON, HTML, logs |

## Why The Boundaries Exist

These concepts are intentionally separated so a failure can be classified and product-specific behavior does not leak into the core platform.

| Concept | Why it exists | Owns | Does not own |
| --- | --- | --- | --- |
| Scenario | Reuse the same test recipe across OS templates and states | Declaring what VM/setup/artifact/assertions to use | Secret values |
| Fixture | Make guest state predictable before the product runs | Runtime, registry, policy, file baseline setup | Product execution |
| Artifact | Keep the product under test separate from lab setup | Product folder, installer, smoke script bundle | Shared OS setup |
| Adapter | Translate product-specific output into a common model | Raw JSON -> canonical model | Pass/fail decisions |
| Assertion | Let CI decide pass/fail automatically | Checks over canonical model | Raw output parsing |
| Report | Publish results for humans, CI, and automation | JUnit, JSON, HTML, log locations | VM execution control |

## Scenario

A YAML file that describes what to run. A scenario is the run recipe: which VM to create, what setup to apply, what artifact to upload, and what counts as pass/fail.

- OS family
- provider/template
- guest channel preference
- fixtures
- artifact upload contract
- command or product steps
- output collection
- assertions
- reports
- cleanup policy

Examples:

- `scenarios/windows/demo-powershell-system.example.yaml`
- `scenarios/windows/demo-python-hello.example.yaml`
- `scenarios/windows/demo-c-hello.example.yaml`
- `scenarios/windows/demo-agent-steps.example.yaml`

## Provider

The provider manages VM lifecycle.

Current implementation:

- Proxmox
- clone/start/stop/destroy
- VM status
- guest info through Proxmox/QGA

Future providers can implement the same lifecycle surface without changing scenario semantics.

## Guest Channel

The guest channel executes commands and transfers files inside the VM.

Current implementation:

- QEMU Guest Agent for Windows

Designed:

- WinRM for Windows fallback
- SSH for Linux

## Fixture

A fixture prepares guest state before the artifact runs. In plain terms, it is pre-test environment setup inside the VM.

Fixtures are separated from artifacts to keep failure causes clear. If Python bootstrap, registry setup, or policy setup fails, that is a fixture failure. If the product itself fails, that should be an artifact/product failure.

Examples:

- create registry/file baseline
- install or bootstrap a runtime
- write expected output data
- verify template contamination is absent

The Python/C demos use fixtures to bootstrap portable tools inside the disposable clone under `C:\Oslab\tools`. Product execution should live in `artifact.command` or `product.steps`, not in fixtures.

## Artifact

An artifact is the local file or folder uploaded into the VM. In plain terms, it is the thing being tested: a product folder, installer, binary set, or smoke script bundle.

Supported MVP types:

| Type | Behavior |
| --- | --- |
| `folder` | Upload a directory, usually as an archive |
| `installer` | Upload an installer file and run `installCommand` |

## Command Or Product Steps

Simple scenarios use one artifact command.

Agent-like products can use ordered `product.steps`, for example:

```text
install -> register -> status -> scan
```

The core runner treats these as generic steps. Product semantics belong in scenario files and plugins.

## Adapter

An adapter normalizes raw product output into a canonical model. In plain terms, it translates each product's output shape into a common scoring shape that `oslab` can assert on.

Adapters do not decide pass/fail. They translate. Assertions make the decision. This keeps output schema changes separate from validation rules.

Implemented:

| Adapter | Model |
| --- | --- |
| `canonical.command` | command result |
| `canonical.inventory` | inventory result |

Product-specific adapter logic should stay outside the core runner behavior and should be documented with that product, not in the generic getting-started path.

## Assertion

Assertions evaluate normalized output. In plain terms, an assertion is a pass/fail rule over the canonical model, not over raw guest state.

Implemented examples:

| Assertion | Meaning |
| --- | --- |
| `command.exitCode` | Check command exit code |
| `command.stdoutContains` | Check stdout text |
| `command.stderrContains` | Check stderr text |
| `inventory.contains` | Check inventory contains a matching record |
| `inventory.evidencePresent` | Check evidence exists |

## Report

Each full run can write:

- `run.json`
- `reports/result.json`
- `reports/result.junit.xml`
- `reports/result.html`
- `logs/progress.log`
- `logs/progress.jsonl`

JUnit is for CI. HTML is for humans. JSON is for automation.

Reports are the publication layer. `raw/`, `normalized/`, `logs/`, and `run.json` are evidence that explains the report.
