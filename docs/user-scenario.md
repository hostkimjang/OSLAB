# Retest an endpoint agent on Windows and Ubuntu

English · [한국어](user-scenario.ko.md)

A developer ships an endpoint inventory agent for Windows 11 and Ubuntu 24.04. Before sending the next build to QA, they need evidence that it installs on a clean machine and upgrades an existing installation on both systems. They rerun the same four tests whenever the build, OS image, upgrade baseline, or build environment changes.

This example uses Demo Agent 2.4.0, a sample product that registers an asset locally and inventories software from the Windows registry or Ubuntu's package database. Both editions read the same `VERSION` file and emit JSON for the fields the scenarios check. The sample records the server URL in local state, so the four clones can run with their network interfaces disconnected. [Demo Agent artifact](../validation/artifacts/demo-agent-cli)

## What the upgrade must preserve

A clean install writes the current state format. An upgrade starts with a 2.3.1 registration and INI settings that 2.4.0 has to migrate. If the upgrade generates a new asset ID, an inventory server could create a second record for the same machine and split its history.

The upgrade fixtures seed known registration IDs, timestamps and settings. The candidate backs up the old files, moves the INI settings into JSON, and rewrites state from schema 1 to 2. The upgrade scenarios omit the registration command and check that the first 2.4.0 scan still belongs to the original asset. [Windows fixture](../validation/fixtures/windows/demo-agent-2.3-installed.ps1) · [Ubuntu fixture](../validation/fixtures/linux/demo-agent-2.3-installed.sh)

## The four test cases

| Suite entry | Guest and starting state | Steps |
| --- | --- | --- |
| [`windows-fresh`](../scenarios/windows/demo-agent-fresh-install.example.yaml) | Clean Windows 11 | version, install, register, status, scan |
| [`windows-upgrade`](../scenarios/windows/demo-agent-upgrade.example.yaml) | Windows 11 with a registered 2.3.1 installation | version, install, status, scan |
| [`ubuntu-fresh`](../scenarios/linux/demo-agent-fresh-install.example.yaml) | Clean Ubuntu 24.04 | version, install, register, status, scan |
| [`ubuntu-upgrade`](../scenarios/linux/demo-agent-upgrade.example.yaml) | Ubuntu 24.04 with a registered 2.3.1 installation | version, install, status, scan |

Each product step emits one JSON object on stdout and writes human-readable progress to stderr. `expectStdoutJson` compares selected fields and fails the step on a mismatch. The fresh rows verify the new registration and schema 2 state. The upgrade rows verify the migration, backup, preserved asset ID and registration time, and settings such as the 360-minute scan interval. All rows assert that the collected inventory contains Demo Agent 2.4.0 and a record from the guest OS. [Stdout JSON contract](scenarios.md#product-step-stdout-json-contract)

## Run the matrix

Run these commands from the repository root. Prepare one Windows 11 template and one Ubuntu 24.04 template with QEMU Guest Agent, local OSLab config and env files, four free VMIDs, and enough memory for four simultaneous clones. The Windows scenarios sign in a test account and show the commands on its desktop. The Ubuntu scenarios use a VirtIO display and show the commands on the first text console. [Proxmox setup](proxmox-connection.md#template-requirements) · [Linux guest setup](scenarios.md#linux-guests) · [Getting started](getting-started.md)

Make local copies so the checked-in examples remain usable on other labs. The repository ignores these `qa-` files, and the dashboard can run them.

```powershell
$names = 'windows/demo-agent-fresh-install', 'windows/demo-agent-upgrade',
         'linux/demo-agent-fresh-install', 'linux/demo-agent-upgrade'
foreach ($name in $names) {
    $source = "scenarios/$name.example.yaml"
    $copy = $source -replace '/demo-agent-', '/qa-demo-agent-'
    if (-not (Test-Path -LiteralPath $copy)) { Copy-Item -LiteralPath $source -Destination $copy }
}
$suite = 'validation/suites/qa-demo-agent-matrix.example.yaml'
if (-not (Test-Path -LiteralPath $suite)) {
    $content = (Get-Content -Raw 'validation/suites/demo-agent-matrix.example.yaml') -replace 'scenario: scenarios/(windows|linux)/demo-agent-', 'scenario: scenarios/$1/qa-demo-agent-'
    Set-Content -LiteralPath $suite -Value $content -Encoding utf8
}
```

In the four local scenarios, set `provider.template`, `provider.templateVmId` and `provider.vmIdRange` for your lab. The four entries may share a range that has room for the planned clones. `--max-parallel 4` requests concurrent execution, and all entries receive the same artifact folder. Each scenario excludes the other OS's script.

```powershell
uv run --locked oslab suite-run `
    --suite validation/suites/qa-demo-agent-matrix.example.yaml `
    --config config/oslab.local.yaml `
    --env-file config/oslab.local.env `
    --artifact-path validation/artifacts/demo-agent-cli `
    --max-parallel 4
```

In the web dashboard, choose the same suite in **Run Launcher**, select `validation/artifacts/demo-agent-cli` as the test folder, and set **Max parallel** to 4. To rerun only one row from the CLI, use `oslab run` with that scenario and the same artifact folder. [Dashboard setup](web-dashboard-server.md)

## Read the evidence

Open `runs/<suite-run-id>/reports/suite.html` for the four results. In `suite.json`, a passing matrix has `status: passed`, `summary.passed: 4` and `summary.requiredFailed: 0`. The recorded lab run `intro-suite-v2-20261120` passed all 16 assertions across the four environments. [Video verification record](media/oslab-intro-film-attestation.json)

Open the child run under `scenarios/<suite-run-id>-<entry-id>/` to investigate an individual result. `raw/product-steps.json` records each command, exit code and stdout JSON comparison. The upgrade child's fixture manifest under `raw/` contains the reference values, and `logs/product-step-status.stderr.log` shows the migration status. If the candidate changes the asset ID, compare the expected and actual values at `details.stdoutJsonExpectation.mismatches` in the failed step. [Reports and Results](reports.md)

## Adapt the example to your product

1. Give each supported OS and installation path a suite entry. Include every prior release that customers are expected to upgrade from.
2. Use a fixture to reproduce the relevant old state, including any identifiers, settings, files, or registry keys that must survive.
3. Give each product step a JSON mode or wrap it with a script that emits the fields you need. Check stable field values during the steps and add assertions for the collected output.
4. Upload one candidate artifact per suite execution. When a compiler, packaging step, or build machine changes, keep the source revision fixed for the comparison. When an OS image changes, keep the candidate fixed and record the template used for each row.

Start with the supplied [suite YAML](../validation/suites/demo-agent-matrix.example.yaml) and the [scenario authoring guide](scenarios.md).
