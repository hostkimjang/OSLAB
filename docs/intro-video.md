# OSLab introduction video

English · [한국어](intro-video.ko.md)

[![OSLab introduction video](media/oslab-intro-film-poster.jpg)](https://raw.githubusercontent.com/hostkimjang/OSLAB/master/docs/media/oslab-intro-film.mp4)

[Download the 1080p MP4](https://raw.githubusercontent.com/hostkimjang/OSLAB/master/docs/media/oslab-intro-film.mp4) · [Verification record](media/oslab-intro-film-attestation.json) · [How the video is made](#how-the-video-is-made)

## Synopsis

The video opens on 32 Windows 11 VM consoles, then follows one candidate build through fresh installs and upgrades on Windows 11 and Ubuntu 24.04. The tests use Demo Agent, a sample endpoint inventory agent. [Run the same environment matrix](user-scenario.md)

One `oslab suite-run` starts four disposable VMs. The Windows fresh-install console shows the agent commands on the signed-in desktop. The Ubuntu upgrade shows the migration from 2.3.1 to 2.4.0 and the checks that the original asset ID and settings survive. OSLab keeps the logs, inventory and reports after removing the VMs.

The local web dashboard launches another run, streams its log and opens the result with its evidence and report. Codex then operates a Windows desktop through the OSLab MCP server and the Proxmox console. It opens Notepad, types a line, saves the file to the Desktop and shows it in File Explorer while the host mouse and keyboard stay free, and QEMU Guest Agent confirms the saved file.

The last chapter returns to the 32 Windows programs. It shows the fixes in LibreOffice Calc and Visual Studio Code and how the agents reach the VMs, then brings the consoles together with the final tally of 32 programs passed and 140 guest checks verified.

## Chapters

| Chapter | On screen |
| --- | --- |
| Opening | 32 Windows VMs and the OSLab title |
| 01 Scenario | The Windows fresh-install scenario for Demo Agent |
| 02 Run | `oslab suite-run` and the signed-in Windows desktop, then the Windows and Ubuntu consoles for all four test cases |
| 03 Evidence | Files, HTML report and assertions from the Ubuntu upgrade |
| 04 Dashboard | A separate run launched from the web dashboard, its live log and its results |
| 05 AI agents | Codex operates Notepad and File Explorer through MCP and the guest checks confirm the saved file |
| 06 Scale | The Calc and VS Code fixes, the MCP control path and the final tally across 32 Windows VMs |
| End card | OSLab and the repository address |

## Recorded and edited parts

- Chapters 02 and 03 use a single four-entry suite recording. The first close-up follows the `windows-fresh` child run, and the evidence chapter shows the `ubuntu-upgrade` child. Chapters 04 and 05 reuse the original dashboard run and the Codex session on its own VM.
- The VM footage came from the Proxmox consoles during the runs. The report and dashboard footage came from headless Chromium. Playwright drove the dashboard.
- The editor typesets the YAML and replays the captured terminal text. It animates command typing, speeds up wait periods and uses recorded event times for the lifecycle rail. Private names in the terminal, report and dashboard text use public aliases.
- The editor draws cursors at recorded input positions and interpolates the movement between them. The cursor in chapter 05 follows Codex's MCP `move_mouse` and `click` calls. The guest's own pointer also appears in the recording.
- The outcome badges use the run results and guest checks. The opening and finale reuse the original [32-VM Windows QA recordings](#the-32-vm-windows-qa-video), made in groups of up to eight VMs and aligned by the start of each workflow. The title and final verification tally are animated. The MP4 is silent.

## How the video is made

Prepare the local suite and four scenario copies first. The capture commands also need FFmpeg, Node.js with the repository's Playwright dependencies installed, and access to the Proxmox node's LAN API. [Prepare the suite](user-scenario.md#run-the-matrix)

1. `capture_suite.py` runs `uv run --locked oslab suite-run` with timestamped terminal output and records the four consoles. It saves `suite.json` and the child run evidence. `--report-entry ubuntu-upgrade` records the HTML report used in chapter 03. `--chromium` selects an installed Chromium executable for report recording. Use `--evidence-only --run-id <same-run-id>` to retry the report without rerunning the VMs.
2. `capture_dashboard.mjs` starts an isolated dashboard with its own API port, SQLite database and web build. It records Run Launcher, the live console and Results Explorer together with the pointer inputs and their times. Copy the [ordered Windows steps scenario](../scenarios/windows/demo-agent-steps.example.yaml) to `scenarios/windows/qa-demo-agent-steps.example.yaml` and set the Windows template and VMID range for your lab.
3. `capture_agent.py run` records a signed-in Windows clone while an MCP client uses the console and writes its call log to `calls.json`. In a second terminal, run `capture_agent.py check` after the client has saved the file, then write the stop file to end the recording.
4. `edit_intro.py` reads the `suite`, `dashboard` and `agent` capture folders and the 32-VM footage. It renders a 1920×1080, 30 fps MP4. Use `--preview` to inspect selected frames and `--receipt` to write the verification record for the encoded copy. [Reproduce the 32-VM footage](windows-product-qa.md#record-the-32-vm-video)

```powershell
$demo = 'validation/artifacts/intro-video'
$capture = "$env:TEMP/oslab-intro"
$lan = Read-Host 'Proxmox API LAN address'
uv run --locked --extra computer-use python "$demo/capture_suite.py" --output "$capture/suite" `
    --suite validation/suites/qa-demo-agent-matrix.example.yaml --artifact-path validation/artifacts/demo-agent-cli `
    --config config/oslab.local.yaml --env-file config/oslab.local.env --lan-address $lan `
    --max-parallel 4 --report-entry ubuntu-upgrade --ffmpeg ffmpeg
node "$demo/capture_dashboard.mjs" --out "$capture/dashboard" --scenario scenarios/windows/qa-demo-agent-steps.example.yaml `
    --artifact validation/artifacts/demo-agent-cli --ffmpeg ffmpeg
$agent = @('--config', 'config/oslab.local.yaml', '--env-file', 'config/oslab.local.env', '--work', "$env:TEMP/oslab-agent-capture",
    '--output', "$capture/agent", '--template-vmid', '9200', '--vmid-start', '9185', '--vmid-end', '9189', '--lan-address', $lan)
uv run --locked --extra computer-use python "$demo/capture_agent.py" run @agent
# In a second terminal with the same variables, after the MCP client writes calls.json.
uv run --locked --extra computer-use python "$demo/capture_agent.py" check @agent
New-Item -ItemType File "$env:TEMP/oslab-agent-capture/stop.flag"
$edit = @('--captures', $capture, '--fleet', 'runs/windows-product-qa-demo', '--fonts', 'fonts/geist', '--out', "$capture/edit", '--ffmpeg', 'ffmpeg')
uv run --locked --extra computer-use python "$demo/edit_intro.py" @edit
```

Adjust the example template and VMID values for your lab before recording the MCP session. For a smaller H.264 copy, set the target bitrate to fit the required file size at the rendered duration. This example locates FFmpeg's pass logs in the capture folder.

```powershell
$encode = @('-y', '-i', "$capture/edit/oslab-intro-film.mp4", '-an', '-c:v', 'libx264', '-preset', 'medium',
    '-b:v', '404k', '-maxrate', '1100k', '-bufsize', '2200k', '-pix_fmt', 'yuv420p', '-x264-params', 'aq-mode=3',
    '-passlogfile', "$capture/edit/intro-encode")
ffmpeg @encode -pass 1 -f mp4 NUL
ffmpeg @encode -pass 2 -movflags +faststart docs/media/oslab-intro-film.mp4
uv run --locked --extra computer-use python "$demo/edit_intro.py" @edit --receipt docs/media/oslab-intro-film.mp4
```

## Verification record

The verification record ties the published MP4's SHA-256 to the lab runs, capture timings, Codex MCP activity, and 32-VM guest checks shown in the video. [Verification record](media/oslab-intro-film-attestation.json)

## The 32-VM Windows QA video

https://github.com/user-attachments/assets/52e5a594-a439-44a6-b461-f3e94d1c1c04

[Download the 1080p MP4](https://raw.githubusercontent.com/hostkimjang/OSLAB/master/docs/media/oslab-windows-product-qa.mp4) · [Verification record](media/oslab-windows-product-qa-attestation.json) · [Reproduce the runs](windows-product-qa.md#record-the-32-vm-video)

The earlier 65-second video focuses on chapter 06. Thirty-two disposable Windows 11 VMs each run release QA in a different real program, a scripted test agent drives each VM through the OSLab MCP server with the tools `screenshot`, `click`, `move_mouse` and `press_key`, and OSLab checks every result inside the guest. The camera zooms into LibreOffice Calc, OBS Studio, Visual Studio Code and 7-Zip, a diagram traces the path from the MCP client through the Proxmox console to the guest checks, and the wall ends with 32 of 32 programs passed and 140 checks verified.

Every tile is a continuous console recording of its own VM. The VMs ran in waves of up to 8, the wall lines up each recording at the start of its own workflow, and failed attempts ran again in later waves. The opening wall plays at 8× and the final wall at about 10×, and the editor draws the agent cursors from the MCP inputs recorded in each case file. `edit_video.py` builds that video, and [Record the 32-VM video](windows-product-qa.md#record-the-32-vm-video) lists the commands.
