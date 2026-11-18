# Windows release QA with Dispatch Board

English | [한국어](release-qa-demo.ko.md)

Dispatch Board is a sample Windows desktop app for dispatching shipments. This demo installs real MSI packages, exercises the app with sample shipment data, and checks the saved state and exported CSV. OSLab MCP sends input to the Windows guest and captures its screen. A separate PowerShell verifier reads the resulting files and produces JSON and HTML reports.

| Scenario | What the verifier checks |
| --- | --- |
| Clean install and first use | Release `1.0.0` opens. Seven valid shipments load, `SHP-1048` is rejected for an invalid quantity, and the exported CSV retains the hold on `SHP-1041`. |
| Upgrade with existing data | Release `2.0.0` opens the same workspace. The hold and launch history survive, and the existing CSV has the same SHA-256 hash. |
| Release gate detects data loss | When `2.0.0` exports a fresh CSV, it writes six of seven accepted rows and omits `SHP-1047`. The release verdict is `FAIL`. |
| Patch restores complete export | Release `2.0.1` exports all seven accepted rows in order, including the held shipment. The release verdict is `PASS`. |

## Prepare a Windows guest

Use a disposable 64-bit Windows 11 VM with a signed-in desktop and an administrator account. Copy the artifact folder into the guest and open an elevated Windows PowerShell from that folder. The package build uses Windows components, and the app imports the included synthetic CSV. [Dispatch Board artifacts](../validation/artifacts/release-qa-windows)

```powershell
$sample = (Get-Location).Path
$workspace = Join-Path $env:LOCALAPPDATA ('OSLab\DispatchQA-' + [guid]::NewGuid())
$packages = Join-Path $workspace 'packages'
$data = Join-Path $workspace 'shipments'
$evidence = Join-Path $workspace 'evidence'
New-Item -Path $packages, $data, $evidence -ItemType Directory -Force | Out-Null
Copy-Item (Join-Path $sample 'input.csv') $data

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\package-release.ps1 -OutputDir $packages
if ($LASTEXITCODE -ne 0) { throw 'MSI build failed.' }

$launcher = Join-Path ${env:ProgramFiles(x86)} 'OSLab\Dispatch Board\Start-DispatchBoard.ps1'
$baseline = Join-Path $evidence 'dispatch-before-upgrade.csv'

function Open-DispatchBoard {
    $arguments = '-NoProfile -ExecutionPolicy Bypass -STA -File "{0}" -DataDir "{1}"' -f $launcher, $data
    Start-Process powershell.exe -ArgumentList $arguments -WindowStyle Hidden
}

function Test-DispatchGate {
    param([string]$Mode, [string]$BaselinePath)

    $options = @()
    if ($BaselinePath) { $options += @('-Baseline', $BaselinePath) }
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Verify-Dispatch.ps1 `
        -Mode $Mode -DataDir $data @options `
        -ReportPath (Join-Path $evidence "$Mode.html") `
        -ResultPath (Join-Path $evidence "$Mode.json")
    if ($LASTEXITCODE -ne 0) { throw "Unexpected result in $Mode. See $evidence." }
}
```

Connect Codex or Claude to this guest’s VMID. Use `screenshot` to find the target, `click` with the latest `frame_id`, and `press_key` for keyboard shortcuts. Capture the screen again after an action to see the new state. [OSLab MCP setup and tools](computer-use-mcp.md)

## Run the scenarios

Run the commands below in the same PowerShell session. Use the app window for the clicks and keyboard shortcuts.

1. **Install and import.** Open the Windows Installer wizard, finish the installation, and launch the app.

   ```powershell
   $msi = Join-Path $packages 'DispatchBoard-1.0.0.msi'
   $log = Join-Path $evidence 'install-1.0.0.log'
   $installer = Start-Process msiexec.exe -ArgumentList ('/i "{0}" /l*v "{1}"' -f $msi, $log) -Wait -PassThru
   if ($installer.ExitCode -ne 0) { throw "Installation failed. See $log." }
   Open-DispatchBoard
   ```

   Click **Import CSV** or press **Ctrl+I**. When the board shows seven accepted shipments and one rejected shipment, verify the import.

   ```powershell
   Test-DispatchGate fresh-import
   ```

2. **Save a hold and export.** Select `SHP-1041` and click **Hold / release** or press **Ctrl+H**. Click **Export manifest** or press **Ctrl+E**. Verify the CSV and copy it for the upgrade check. Close Dispatch Board when finished.

   ```powershell
   Test-DispatchGate export
   Copy-Item (Join-Path $data 'dispatch-export.csv') $baseline
   ```

3. **Upgrade and reopen.** Install `2.0.0` and reopen the same data directory. Check that `SHP-1041` is still on hold. Run the upgrade check before requesting a new export so it can verify that the existing manifest survived the upgrade.

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-release.ps1 `
       -Package (Join-Path $packages 'DispatchBoard-2.0.0.msi') `
       -LogPath (Join-Path $evidence 'install-2.0.0.log')
   if ($LASTEXITCODE -ne 0) { throw 'Upgrade to 2.0.0 failed.' }
   Open-DispatchBoard
   ```

   ```powershell
   Test-DispatchGate upgrade $baseline
   ```

4. **Reproduce the export defect.** On `2.0.0` click **Export manifest** again. Open the report to see the two failed assertions for count and content and the omitted shipment ID.

   ```powershell
   Test-DispatchGate regression
   Copy-Item (Join-Path $data 'dispatch-export.csv') (Join-Path $evidence 'dispatch-2.0.0.csv')
   Invoke-Item (Join-Path $evidence 'regression.html')
   ```

   The verifier exits with code 0 when it observes exactly the intended failure. The report and JSON still show the actual release verdict `FAIL`.

5. **Verify the patch.** Close Dispatch Board, install `2.0.1`, then reopen the same data directory and click **Export manifest**. The verifier compares each exported value, the row order, and the hold status.

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-release.ps1 `
       -Package (Join-Path $packages 'DispatchBoard-2.0.1.msi') `
       -LogPath (Join-Path $evidence 'install-2.0.1.log')
   if ($LASTEXITCODE -ne 0) { throw 'Installation of 2.0.1 failed.' }
   Open-DispatchBoard
   ```

   ```powershell
   Test-DispatchGate fixed
   $fixed = Join-Path $data 'dispatch-export.csv'
   if ((Get-FileHash $baseline -Algorithm SHA256).Hash -ne (Get-FileHash $fixed -Algorithm SHA256).Hash) {
       throw 'The patched export differs from the 1.0.0 baseline.'
   }
   Invoke-Item (Join-Path $evidence 'fixed.html')
   ```

The evidence directory holds the MSI logs, the original and defective exports, and the JSON and HTML verdicts. `dispatch-state.json` in the data directory holds the app’s recorded actions, and `dispatch-export.csv` holds the latest manifest. Copy the files you want to keep before disposing of the VM.
