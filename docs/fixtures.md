# Fixture Authoring

Language: English | [한국어](fixtures.ko.md)

Fixtures prepare the guest VM before the artifact is uploaded or executed. Think of a fixture as the test-room setup: install or locate runtimes, create directories, set registry/policy state, prepare reference data, and write setup evidence.

Fixtures should not run the main product validation. Put product execution in `artifact.command` or `product.steps` so setup failures and product failures stay separate.

## When To Use A Fixture

| Need | Fixture? | Example |
| --- | --- | --- |
| Ensure Python exists before running a Python artifact | Yes | `demo-python-runtime.ps1` |
| Ensure a C compiler exists before compiling `hello.c` | Yes | `demo-c-compiler.ps1` |
| Create a registry key or test file before scan | Yes | PowerShell setup script |
| Upload and run the product under test | No | Use `artifact` |
| Check normalized output pass/fail | No | Use `assertions` |

## Scenario Contract

```yaml
fixtures:
  - id: demo-python-runtime
    type: powershell
    source: validation/fixtures/windows/demo-python-runtime.ps1
    expectedOutput: "C:\\Oslab\\demo-python-runtime.json"
```

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | Yes | Stable id used in progress logs, JUnit testcase names, and raw output filenames |
| `type` | Yes | Fixture runner type. Current Windows demos use `powershell` |
| `source` | Yes | Local script uploaded and executed in the guest |
| `expectedOutput` | No | Guest path collected after fixture execution as setup evidence |

## PowerShell Fixture Rules

Recommended shape:

```powershell
$ErrorActionPreference = "Stop"

$root = "C:\Oslab"
New-Item -ItemType Directory -Force -Path $root | Out-Null

# Prepare guest state here.

$manifest = @{
  schemaVersion = 1
  kind = "fixtureResult"
  ready = $true
  details = @{}
}

$manifest |
  ConvertTo-Json -Depth 10 |
  Set-Content -Encoding UTF8 "$root\my-fixture.json"
```

Rules:

- Use `$ErrorActionPreference = "Stop"` so real setup failures fail the fixture.
- Write deterministic evidence JSON when `expectedOutput` is configured.
- Create parent directories before writing files.
- Keep setup idempotent; a fixture should tolerate being run on a clone that already has the tool/state.
- Do not print secrets.
- Do not run the product command here.

## Demo Fixture Behavior

### Python Runtime Fixture

`validation/fixtures/windows/demo-python-runtime.ps1`:

1. Creates `C:\Oslab` and `C:\Oslab\tools`.
2. Reuses existing `C:\Oslab\tools\python\python.exe`, `python.exe`, or `py.exe` if available.
3. If no runtime exists, downloads portable Python into `C:\Oslab\tools\python`.
4. Writes `C:\Oslab\demo-python-runtime.json`.
5. Fails as `fixture_failure` if no working Python runtime is produced.

Expected fixture evidence shape:

```json
{
  "schemaVersion": 1,
  "kind": "demoRuntime",
  "demo": "python-hello",
  "ready": true,
  "runtime": "python",
  "source": "portable",
  "executable": "C:\\Oslab\\tools\\python\\python.exe",
  "version": "Python 3.13.6"
}
```

### C Compiler Fixture

`validation/fixtures/windows/demo-c-compiler.ps1`:

1. Creates `C:\Oslab` and `C:\Oslab\tools`.
2. Reuses `cl.exe`, `gcc.exe`, or `clang.exe` if available.
3. If no compiler exists, downloads TinyCC into `C:\Oslab\tools\tcc`.
4. Writes `C:\Oslab\demo-c-compiler.json`.
5. Fails as `fixture_failure` if no compiler is found or bootstrapped.

Expected fixture evidence shape:

```json
{
  "schemaVersion": 1,
  "kind": "demoRuntime",
  "demo": "c-hello",
  "ready": true,
  "runtime": "c-compiler",
  "compiler": "tcc",
  "executable": "C:\\Oslab\\tools\\tcc\\tcc.exe"
}
```

## Result Flow

During `oslab run`:

1. The fixture script is uploaded to the disposable clone.
2. The fixture runs through the selected guest channel.
3. stdout/stderr and exit code are recorded.
4. If `expectedOutput` is set, that guest file is downloaded into `runs/<run-id>/raw/`.
5. A failed fixture stops artifact execution and classifies the run as `fixture_failure`.

Expected files after a passing demo run:

```text
runs/<run-id>/
  logs/
    progress.log
  raw/
    fixture-demo-python-runtime.expected-output.json
  reports/
    result.junit.xml
    result.json
    result.html
```

Expected progress log markers:

```text
[..] fixture.start - Apply scenario fixtures
[OK] fixture.done - Fixture applied
    fixtureId: demo-python-runtime
    exitCode: 0
[OK] fixture.all.done - Scenario fixtures applied
```

## Debugging

Run a fixture-focused smoke test when setup fails:

```powershell
uv run oslab fixture-smoke `
  --scenario scenarios/windows/demo-python-hello.local.yaml `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --keep-vm
```

Then inspect the kept VM:

```powershell
uv run oslab qga-exec `
  --config config/oslab.local.yaml `
  --env-file config/oslab.local.env `
  --vm-id <kept-vm-id> `
  -- powershell.exe -NoProfile -Command "Get-ChildItem C:\Oslab -Recurse"
```

