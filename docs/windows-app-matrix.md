# Windows app test matrix

English · [한국어](windows-app-matrix.ko.md)

The matrix defines 32 workflows for disposable Windows 11 VMs. Cases `01`–`28` are distinct offline sample web apps that open in Microsoft Edge. Cases `29`–`32` use Windows apps. Each case runs in its own VM and produces guest evidence for the actions shown in its screenshots. [Matrix source](../validation/artifacts/windows-app-matrix)

| Case | Workflow | What the runner checks |
| --- | --- | --- |
| 01–28 | Product workflows such as reconciling a stock count, removing a duplicate photo from a contact sheet, and repairing a route that misses reservations | Values computed from the fixtures must match the independently declared expectations for each of the three actions. |
| 29 · Notepad | Edit and reopen a release handoff record | Saved gate text, line count, and exact SHA-256 of the edited file |
| 30 · File Explorer | Recover two artifacts from a ZIP folder using the desktop UI | File count and SHA-256 for both recovered files |
| 31 · Paint | Fill an approval tile on a PNG and save the artwork | PNG format, image dimensions, filled pixel, and an unchanged control pixel |
| 32 · Calculator | Multiply a carton order, deduct reserve units, and divide by pallet capacity | The displayed result after each operation |

The published recording covers 32 workflows and 351 passing assertions. The evidence includes capture batches and the expected and observed values for each check. [Capture and validation record](media/oslab-windows-app-matrix-attestation.json)

## Prepare the lab

Use the repository root, Node.js 18 or later, and the OSLab `computer-use` extra. The Proxmox node needs a Windows 11 QEMU template with Edge, the four Windows apps, a graphical console with absolute pointing, and a working QEMU Guest Agent (QGA). Use storage that supports linked clones and a dedicated VMID range on the configured node. The Proxmox token needs permissions for the temporary VM lifecycle, QGA, and `VM.Console`. [Proxmox setup](proxmox-connection.md) · [Console MCP](computer-use-mcp.md)

Change the example VMIDs below to match the lab. Give each new run its own output directory. Keep the same directory, config, and VMID settings when resuming or cleaning up that run.

```powershell
$demo = 'validation/artifacts/windows-app-matrix'
$runner = "$demo/run_matrix.py"
$job = 'runs/windows-app-matrix-demo'
$bundle = "$job/bundle"
$lab = @(
    '--config', 'config/oslab.local.yaml',
    '--env-file', 'config/oslab.local.env',
    '--output', "$job/capture",
    '--template-vmid', '9200',
    '--vmid-start', '9300',
    '--vmid-end', '9339'
)
node "$demo/bundle.js" $bundle
if ($LASTEXITCODE -ne 0) { throw 'App bundle validation failed.' }
uv run --locked --extra computer-use python $runner prepare @lab
```

`bundle.js` checks the sample apps locally and generates standalone HTML pages and `cases.json`. `prepare` creates an isolated temporary source by copying the Windows template and configuring a throwaway desktop account. The source and its test clones run without a network adapter.

## Run and review

```powershell
uv run --locked --extra computer-use python $runner run @lab --bundle $bundle
```

To run a subset, add `--cases 01 02 29 31`. The default wave limit is four guests. `--wave-size 8` raises the limit when there is enough memory. The runner uses 5 GiB per guest and reduces the wave size based on the node's available memory, leaving 12 GiB available when starting a wave.

For the web apps, a PowerShell listener bound to `127.0.0.1:7788` serves the page and saves each action's JSON in the guest. Buttons unlock in sequence after the preceding action's evidence is saved. Each action computes a result from synthetic input. Some deliberately trigger a validation error or a blocked release, and the runner checks that the observed rejection matches the expected result.

OSLab MCP sends clicks and keys to each guest and captures screenshots through the Proxmox VNC console. QGA starts the apps and reads the saved results through a separate path. The runner checks the web results against the expected values in `cases.json` and examines native artifacts or the Calculator display for the four Windows app workflows.

- `capture/case-*.json` contains verified results, expected and observed values, wave number, frame filenames and SHA-256 hashes, and input and capture timestamps. Frame offsets share a clock within a wave.
- `capture/*-stage-*.png` and the other capture PNGs show the guest state around actions. Use timestamps to identify simultaneous captures and the wave number to distinguish scenes recorded at different times.
- The command returns a nonzero status when any requested case has no verified result. After resolving the reported issue, rerun with the same output directory to skip already verified cases. If an interrupted wave left guests in the ledger, run `cleanup-wave` in place of `run` before retrying. This keeps the temporary source.

## Remove the temporary VMs

Each completed wave removes its guest clones. Run `cleanup` after all waves or after an aborted capture to remove the remaining clones, their storage, and the temporary source. Keep the capture directory until cleanup completes because it contains the ownership ledger.

```powershell
uv run --locked --extra computer-use python $runner cleanup @lab
```

`capture/cleanup.ok` records completion after the runner checks for leftover capture VMs, volumes, and VMID reservations. Preserve only the local capture records you need.
