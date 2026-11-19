# OSLab introduction video

English · [한국어](intro-video.ko.md)

https://github.com/user-attachments/assets/52e5a594-a439-44a6-b461-f3e94d1c1c04

[Download the 1080p MP4](https://raw.githubusercontent.com/hostkimjang/OSLAB/master/docs/media/oslab-windows-product-qa.mp4) · [Verification record](media/oslab-windows-product-qa-attestation.json) · [Reproduce the runs](windows-product-qa.md#record-the-readme-video)

## Synopsis

The video introduces OSLab in 65 seconds. Thirty-two disposable Windows 11 VMs each run release QA in a different real program, a test agent drives each VM through the OSLab MCP server, and OSLab checks every result inside the guest.

The opening starts from a wall of empty slots. A colored cursor for each test agent flies in, and each VM's console opens where its agent lands. The wall then plays as an 8× time-lapse. Cursors glide to the recorded clicks, typing bubbles mark key presses, and a PASS badge appears when a VM's guest checks pass. Counters track active agents, passed programs and guest checks.

The camera then pushes into four workflows that play close to real speed:

- **LibreOffice Calc:** a release gate blocked at 37 of 42 artifacts is corrected to 42/42 and recalculates to PASS.
- **OBS Studio:** a local evidence scene is recorded, and the guest confirms an H.264/AAC file.
- **Visual Studio Code:** four cold starts exceed the 2,000 ms budget, and only the timeout setting changes.
- **7-Zip:** a release archive is extracted, and six recovered files match their SHA-256 hashes.

A diagram traces the path from the MCP client through the Proxmox console to the guest checks. Two montages add eight more programs, and the wall returns with 32 of 32 programs passed and 140 checks verified in the guests.

## Scenes

| Time | Scene | On screen |
| --- | --- | --- |
| 0:00–0:09 | Agents and the wall | 32 agents reach their VMs, then all 32 console recordings play together at 8× |
| 0:09–0:10 | Push-in | The camera moves from the Calc tile into its console |
| 0:10–0:40 | Featured workflows | Calc, OBS Studio, VS Code and 7-Zip with the agent's clicks, key presses and guest check status |
| 0:40–0:47 | How it works | MCP client, OSLab MCP, Proxmox console, Windows 11 VM, QEMU Guest Agent and guest checks |
| 0:47–0:55 | More programs | DB Browser for SQLite, VLC, WinMerge, Process Monitor, Performance Monitor, Inkscape, Impress and Writer |
| 0:55–1:05 | Finale and end card | All 32 programs pass, then the repository address |

## Recorded and edited parts

- **Screens:** every tile and zoomed screen is a continuous 30 fps console recording of its own VM, captured through the Proxmox console while the workflow ran.
- **Waves:** the VMs ran in waves of up to 8. The wall lines up each recording at the start of its own workflow, so the 32 runs on the wall did not all run at the same moment. The passing runs come from 8 waves, and failed attempts ran again in later waves.
- **Speed:** the opening wall plays at 8× and the final wall at about 10×. Featured workflows play close to real speed around inputs and faster during waits. The header shows the current speed, and result screens are held while the guest checks finish.
- **Cursors:** the editor draws the agent cursors. Click positions and times come from the MCP inputs recorded in each case file, and the paths between clicks are interpolated. The flight into the empty slots at the start is a title animation.
- **PASS:** a tile shows PASS when its workflow finished with every guest check passed.
- **Test agents:** each agent in this video is a scripted QA workflow that calls the MCP tools `screenshot`, `click`, `move_mouse` and `press_key`. Codex and Claude can drive the same tools. [Console MCP](computer-use-mcp.md)
- **Sound:** the MP4 has no audio track.

## How it was made

1. `setup.py` installs 24 programs on a staging Windows 11 VM and seals it as the source for linked clones. The Windows built-in tools come from the template.
2. `fleet.py` gives each workflow its own linked clone and starts the clones in waves while it watches the node's available memory. `screen_recorder.py` records each console. One OSLab MCP server per wave sends the workflow inputs over the console, QEMU Guest Agent reads the results, and each `case-<ID>.json` stores the checks and the times of the MCP inputs.
3. `edit_video.py` reads the recordings and case files. It builds the wall, zooms into the featured workflows, draws the agent cursors and writes the master MP4 with the verification record.
4. The README copy is a two-pass H.264 encode of the master that stays under the 10 MB video limit for GitHub's free plan.

The commands are in [Record the README video](windows-product-qa.md#record-the-readme-video).

## Verification record

[`oslab-windows-product-qa-attestation.json`](media/oslab-windows-product-qa-attestation.json) lists the program, version, scenario, steps, wave, run time, guest checks, recording frame count and stage screenshot hashes for each workflow. It also records the SHA-256 of the published MP4. VM IDs and lab host names are left out.
