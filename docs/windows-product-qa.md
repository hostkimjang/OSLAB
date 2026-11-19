# Windows desktop release QA

English · [한국어](windows-product-qa.ko.md)

Run 32 release QA workflows against real programs on disposable Windows 11 VMs. Each VM operates a separate program or LibreOffice application using synthetic release files. The OSLab MCP sends clicks and keystrokes through the Proxmox console. The runner collects separate evidence through QEMU Guest Agent (QGA), including file hashes, computed values and observed desktop state. [Scenario source](../validation/artifacts/windows-product-qa) · [Console MCP](computer-use-mcp.md)

The 32-VM video recorded all 32 workflows on disposable Windows 11 VMs, and all 140 checks passed. Chapter 06 of the [introduction video](intro-video.md) reuses these recordings. [About the 32-VM video](intro-video.md#the-32-vm-windows-qa-video) · [1080p recording](https://raw.githubusercontent.com/hostkimjang/OSLAB/master/docs/media/oslab-windows-product-qa.mp4) · [Verification record](media/oslab-windows-product-qa-attestation.json)

## Scenario catalog

| ID | Program | Expected evidence |
| --- | --- | --- |
| 01 | 7-Zip File Manager | Six files extracted from a release bundle match the manifest hashes. |
| 02 | LibreOffice Calc | Correcting an artifact count recalculates the subtotal and release gate. |
| 03 | OBS Studio | A local evidence scene produces a playable H.264/AAC recording. |
| 04 | Notepad++ | The saved INI changes the active release gate while preserving the rollback template. |
| 05 | Visual Studio Code | A startup gate fails with the candidate budget and passes after the configuration edit. |
| 06 | Git GUI | The local Git tree records the selected rollback guard change. |
| 07 | Python IDLE | Three retry tests pass after the off-by-one fix. |
| 08 | DB Browser for SQLite | A committed backfill preserves the original rows and passes SQLite integrity checks. |
| 09 | WinMerge | The merged retry policy preserves the candidate version and route. |
| 10 | VLC media player | The player reaches the 12-second seek marker and pauses. |
| 11 | Audacity | Trimming the test slate leaves an exact three-second mono PCM export. |
| 12 | LibreOffice Writer | The release handoff exports as a two-page PDF with its approval receipt. |
| 13 | LibreOffice Impress | The brief keeps the intended slide order and 16:9 export geometry. |
| 14 | LibreOffice Draw | The moved registration mark and exported page match the expected geometry. |
| 15 | Shotcut | The two-shot MP4 export has the required dimensions and duration. |
| 16 | ILSpy | The exported source contains the candidate assembly's public API signatures. |
| 17 | Inkscape | The PNG export clips print bleed and retains the expected page pixels. |
| 18 | SumatraPDF | Navigation reaches the rollback evidence and final sign-off pages. |
| 19 | Everything | The filtered release inventory yields the exact ZIP package paths. |
| 20 | ImageMagick | A visual diff identifies a changed badge and clears after correction. |
| 21 | Event Viewer | A recovery event follows the fixture's missing-manifest error. |
| 22 | Task Scheduler | An on-demand job writes the expected manifest and hashes. |
| 23 | Windows PowerShell ISE | A packaging check fails with the stale expected file count and passes after correction. |
| 24 | ODBC Data Source Administrator | The fixture retains its 64-bit data source, driver and routing properties. |
| 25 | Process Monitor | The trace captures a missing settings file and successful access after recovery. |
| 26 | Process Explorer | The dedicated process holds and then releases the release manifest file. |
| 27 | TCPView | The fixture's listener and established loopback connection match Windows socket state. |
| 28 | VMMap | A native process snapshot records the fixture's 32 MiB allocation. |
| 29 | Notepad | The saved and reopened handoff record matches the expected bytes. |
| 30 | File Explorer | Two files recovered from an evidence ZIP match their original hashes. |
| 31 | Paint | The edited PNG has the expected dimensions, fill color and unchanged reference pixel. |
| 32 | Performance Monitor | The graph freezes and resumes while separate CPU samples confirm load and recovery. |

## Prepare the lab

Use `uv` and the OSLab `computer-use` extra from the repository root. Prepare an x64 Windows 11 Proxmox template with a graphical console, QGA, a `net0` adapter for staging vendor downloads, and Windows App Installer. Use a linked-clone-capable datastore and a dedicated VMID range. The Proxmox credentials must support clone lifecycle, QGA and VM console access. [Proxmox connection](proxmox-connection.md)

`prepare` creates a disposable staging VM, starts package installation, and returns while that task runs. Review `inventory` until the staging task has finished and no required program is missing. `seal` checks the inventory and makes the staging disk the source for the test clones after removing its network adapter. Windows built-in tools come from the guest template. Package sources and pinned hashes are listed in the staging script. [Staging script](../validation/artifacts/windows-product-qa/stage_products.ps1)

Official sources for the main demo programs include [7-Zip](https://www.7-zip.org/download.html), [The Document Foundation](https://www.libreoffice.org/download/), [OBS Studio](https://obsproject.com/download), [WinMerge](https://winmerge.org/downloads/) and [Microsoft Sysinternals](https://learn.microsoft.com/en-us/sysinternals/downloads/).

Replace the example VMIDs and config paths with those of your lab. Use a new output directory for each run and the same parameters when resuming or cleaning up.

```powershell
$demo = 'validation/artifacts/windows-product-qa'
$lab = @(
    '--config', 'config/oslab.local.yaml',
    '--env-file', 'config/oslab.local.env',
    '--output', 'runs/windows-product-qa-demo',
    '--template-vmid', '9200',
    '--vmid-start', '9300',
    '--vmid-end', '9339'
)
uv run --locked --extra computer-use python "$demo/run.py" catalog
uv run --locked --extra computer-use python "$demo/setup.py" prepare @lab
uv run --locked --extra computer-use python "$demo/setup.py" inventory @lab
```

## Capture and check the evidence

Once the inventory is complete, seal the source and run the workflows. `--wave-size` sets the batch limit, which defaults to four and can be set as high as eight. The runner lowers the batch size when available memory requires it. Add `--cases 01 02 03 08` to capture only a selection.

```powershell
uv run --locked --extra computer-use python "$demo/setup.py" seal @lab
if ($LASTEXITCODE -ne 0) { throw 'Windows product source was not sealed' }
uv run --locked --extra computer-use python "$demo/run.py" run @lab --wave-size 4
```

- `case-<ID>.json` records the program, batch, expected and observed values, check results, frame hashes and times of MCP inputs. `unmatched-<ID>.json` records checks that did not match.
- `<ID>-stage-0.png` through `<ID>-stage-3.png` capture actual guest pixels at the workflow milestones. Extra captures use the same batch clock. For a video, align overlapping captures for the parallel segment and label a composite drawn from multiple batches.
- The runner skips cases already recorded in the output directory. Use `cleanup-wave` with the same lab parameters to clear a retained batch before retrying. A run with any requested evidence still missing returns a nonzero exit code.

## Record the 32-VM video

`fleet.py` runs the same workflows in waves and records each VM console to its own video. Each wave creates linked clones from the sealed source and starts them a few at a time while it watches the node's available memory. It records every console at 30 fps, starts the wave's workflows at the same moment, and removes the wave's VMs before the next wave starts. A failed workflow runs once more in a later wave, and running the command again repeats only the workflows that have not passed yet.

The recorder needs a direct connection to the Proxmox node, so pass the node's LAN address with `--lan-address`. The runner reads the cluster CA through the configured API, writes a LAN copy of the config into the output directory, and verifies the node certificate against that CA. `screen_recorder.py` asks QEMU only for the screen regions that changed and shares the console with the MCP input session. Recording does not get in the way of clicks or key presses.

`edit_video.py` builds the video from those recordings. It lines up every recording at the start of its own workflow, shows all of them as one wall, and zooms into the featured workflows. Long waits play faster and the actions play close to real time. A workflow is marked as passed at the moment its guest checks passed. Each workflow's test agent appears as a colored cursor that follows the MCP click positions and times in `case-<ID>.json`, and the editor interpolates the paths between clicks. The editor uses the [Geist](https://github.com/vercel/geist-font) fonts and writes `oslab-intro-master.mp4` without an audio track.

The published copy is a two-pass encode of the master that stays under the 10 MB video limit for GitHub's free plan. `--receipt` writes a JSON record of the programs, checks and that file's hash next to it. [Scene breakdown](intro-video.md#the-32-vm-windows-qa-video)

```powershell
uv run --locked --extra computer-use python "$demo/fleet.py" run @lab --lan-address 192.168.0.10 --wave-size 8 --ffmpeg ffmpeg
$edit = @('--run-dir', 'runs/windows-product-qa-demo', '--fonts', 'fonts/geist', '--out', 'runs/windows-product-qa-demo/video', '--ffmpeg', 'ffmpeg')
uv run --locked --extra computer-use python "$demo/edit_video.py" @edit
$encode = @('-y', '-i', 'runs/windows-product-qa-demo/video/oslab-intro-master.mp4', '-an', '-c:v', 'libx264', '-preset', 'slower',
    '-b:v', '1150k', '-maxrate', '2600k', '-bufsize', '5200k', '-pix_fmt', 'yuv420p')
ffmpeg @encode -pass 1 -f mp4 NUL
ffmpeg @encode -pass 2 -movflags +faststart docs/media/oslab-windows-product-qa.mp4
uv run --locked --extra computer-use python "$demo/edit_video.py" @edit --receipt docs/media/oslab-windows-product-qa.mp4
uv run --locked --extra computer-use python "$demo/fleet.py" cleanup @lab --lan-address 192.168.0.10
```

An attachment that is only added to an unsubmitted GitHub comment box returns 404 to signed-out visitors. Put the README attachment in a posted comment or pull request description before linking it.

## Remove test resources

Run cleanup with the same parameters before deleting the working directory. The ownership records let the runner find its VMs, storage and VMID reservations. Look for `cleanup.ok` after verifying the cleanup command succeeded.

```powershell
uv run --locked --extra computer-use python "$demo/run.py" cleanup @lab
```
