# Demo Catalog

Language: English | [한국어](demos.ko.md)

The demos are small product-neutral examples. They teach one `oslab` concept at a time before you connect a real product.

## Which Demo Should I Run First?

| Demo | Scenario | Artifact path | Fixture | Teaches |
| --- | --- | --- | --- | --- |
| PowerShell system | `scenarios/windows/demo-powershell-system.example.yaml` | `validation/artifacts/powershell-system` | No | Lowest-dependency command-result demo |
| Python hello | `scenarios/windows/demo-python-hello.example.yaml` | `validation/artifacts/hello-python` | Python runtime bootstrap | Runtime fixture + command assertions |
| C hello | `scenarios/windows/demo-c-hello.example.yaml` | `validation/artifacts/hello-c` | C compiler bootstrap | Toolchain fixture + command assertions |
| Fixture state handoff | `scenarios/windows/demo-fixture-state.example.yaml` | `validation/artifacts/fixture-state-reader` | State file fixture | Fixture prepares VM state, artifact reads it |
| Agent steps | `scenarios/windows/demo-agent-steps.example.yaml` | `validation/artifacts/demo-agent-cli` | No | Ordered `product.steps`, stdout JSON, inventory output |
| Python unittest | `scenarios/windows/demo-python-unittest.example.yaml` | `validation/artifacts/python-unittest` | Python runtime bootstrap | Real unit test execution inside the VM |
| Python HTTP service | `scenarios/windows/demo-python-http-service.example.yaml` | `validation/artifacts/python-http-service` | Python runtime bootstrap | In-VM service lifecycle and HTTP smoke validation |
| C unit test | `scenarios/windows/demo-c-unit.example.yaml` | `validation/artifacts/c-unit` | C compiler bootstrap | Multi-file compile/link/run unit test |
| Intentional assertion failure | `scenarios/windows/demo-intentional-assertion-failure.example.yaml` | `validation/artifacts/hello-python` | Python runtime bootstrap | How assertion failures appear in reports/JUnit |

Recommended order:

1. Run PowerShell system first. It needs no runtime download.
2. Run Python or C to test fixture bootstrap.
3. Run fixture state handoff to understand fixture-to-artifact separation.
4. Run agent steps to understand ordered product workflows.
5. Run Python unittest, Python HTTP service, or C unit test when you want higher-fidelity code execution examples.
6. Run intentional assertion failure only when you want to inspect failure reports.

## Common Run Pattern

Copy an example scenario to a local scenario and edit the provider block.

```powershell
Copy-Item scenarios/windows/demo-powershell-system.example.yaml scenarios/windows/demo-powershell-system.local.yaml
Copy-Item scenarios/windows/demo-python-hello.example.yaml scenarios/windows/demo-python-hello.local.yaml
Copy-Item scenarios/windows/demo-c-hello.example.yaml scenarios/windows/demo-c-hello.local.yaml
Copy-Item scenarios/windows/demo-fixture-state.example.yaml scenarios/windows/demo-fixture-state.local.yaml
Copy-Item scenarios/windows/demo-agent-steps.example.yaml scenarios/windows/demo-agent-steps.local.yaml
Copy-Item scenarios/windows/demo-python-unittest.example.yaml scenarios/windows/demo-python-unittest.local.yaml
Copy-Item scenarios/windows/demo-python-http-service.example.yaml scenarios/windows/demo-python-http-service.local.yaml
Copy-Item scenarios/windows/demo-c-unit.example.yaml scenarios/windows/demo-c-unit.local.yaml
Copy-Item scenarios/windows/demo-intentional-assertion-failure.example.yaml scenarios/windows/demo-intentional-assertion-failure.local.yaml
```

Edit each local copy's provider block:

```yaml
provider:
  type: proxmox
  template: windows11-template-qga
  templateVmId: 9101
  vmIdRange:
    start: 9102
    end: 9199
```

Then run:

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-powershell-system.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/powershell-system
```

After the run:

```powershell
uv run oslab inspect-result --run-dir runs\<run-id>
Invoke-Item runs\<run-id>\reports\result.html
```

## Demo Details

### PowerShell System

This is the smallest passing demo. It runs a PowerShell script, collects OS/PowerShell metadata, writes `C:\Oslab\command-result.json`, and verifies `canonical.command` assertions.

Expected stdout marker:

```text
oslab powershell system demo
```

### Fixture State Handoff

This demo shows why fixtures exist. The fixture writes `C:\Oslab\demo-fixture-state.json`; the artifact command reads that file and produces a command result.

Run:

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-fixture-state.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/fixture-state-reader
```

Expected evidence:

```text
runs/<run-id>/raw/fixture-demo-state-file.expected-output.json
```

### Agent Steps

This demo models an agent-like product without using a private product. The artifact is a small PowerShell CLI with three commands:

```text
register -> status -> scan
```

The scenario uses `product.steps`, captures each step's stdout as JSON, writes `raw/product-steps.json`, and collects an inventory result from the final scan.

Run:

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-agent-steps.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/demo-agent-cli
```

Expected files:

```text
runs/<run-id>/raw/product-steps.json
runs/<run-id>/raw/actual-output.json
runs/<run-id>/normalized/inventory.json
```

### Python Unittest

This demo runs a real Python `unittest` suite inside the disposable VM. The artifact contains application code, tests, and a small test runner that writes a canonical command result.

Run:

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-python-unittest.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/python-unittest
```

Expected stdout markers:

```text
Ran 4 tests
OK
```

### Python HTTP Service

This demo starts a local HTTP service inside the VM, calls `/health`, calls `/add?left=20&right=22`, verifies the response, and shuts the service down.

Run:

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-python-http-service.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/python-http-service
```

Expected stdout markers:

```text
service smoke passed
add_result=42
```

### C Unit Test

This demo compiles a small multi-file C project and runs its test executable. It is closer to a build/test job than a hello-world command.

Run:

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-c-unit.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/c-unit
```

Expected stdout markers:

```text
PASS add
c unit tests passed: 5
```

### Intentional Assertion Failure

This scenario is supposed to fail. It proves that infrastructure and product execution can pass while an assertion fails.

Run only when you want to inspect failure reports:

```powershell
uv run oslab run `
  --scenario scenarios/windows/demo-intentional-assertion-failure.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --artifact-path validation/artifacts/hello-python
```

Expected result:

```text
status: failed
failureClass: assertion_failure
```

In JUnit, the missing-text assertion should appear as a `<failure>`, while infrastructure or product execution problems appear as `<error>`.
