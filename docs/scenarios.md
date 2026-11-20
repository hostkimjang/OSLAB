# Scenario Authoring

Language: English | [한국어](scenarios.ko.md)

This page documents the practical YAML contract for current scenarios.

## Authoring Workflow

When you create a new scenario, write it in this order:

1. Choose the target OS/template and VMID range.
2. Decide the guest channel mode. Windows and Linux runs currently use QEMU Guest Agent.
3. Add fixtures only for guest setup prerequisites.
4. Define the artifact type, destination, and command.
5. Make the command write machine-readable output to `{OutputPath}`.
6. Set `outputs.actual.path` to the same guest path.
7. Choose an adapter such as `canonical.command`.
8. Add assertions over the normalized output.
9. Enable reports.
10. Keep cleanup enabled unless debugging.

The most common authoring bug is a mismatch between `artifact.command` and `outputs.actual.path`: the command succeeds but writes output somewhere `oslab` does not collect.

## Minimal Shape

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
guest:
  mode: auto
fixtures: []
artifact:
  type: folder
  pathParam: artifactPath
  destination: "C:\\Oslab\\artifact"
  transfer: archive
  command:
    shell: powershell
    template: '& "{ArtifactDir}\run.ps1" -OutputPath "{OutputPath}"'
outputs:
  actual:
    path: "C:\\Oslab\\command-result.json"
    adapter: canonical.command
assertions:
  - type: command.exitCode
    id: exit-zero
    exitCode: 0
reports:
  formats:
    - junit
    - json
    - html
cleanup:
  destroyVm: true
  keepVmOnFailure: false
```

## Top-Level Fields

| Field | Required | Description |
| --- | --- | --- |
| `schemaVersion` | Yes | Scenario schema version |
| `id` | Yes | Stable scenario id |
| `name` | Recommended | Human-readable name |
| `os` | Yes | OS family/version |
| `provider` | Yes | Provider type/template/VMID range and optional clone settings |
| `guest` | Yes | Guest command strategy and optional screen settings |
| `fixtures` | Optional | Guest setup scripts |
| `artifact` | Optional | Artifact upload and command contract |
| `product.steps` | Optional | Ordered command steps for agent-like products |
| `outputs` | Optional | Remote output path and adapter |
| `assertions` | Yes | Built-in/plugin assertions |
| `reports` | Optional | Report formats |
| `cleanup` | Optional | VM cleanup behavior |

## Field Responsibilities

| Field | Role in the run | Common mistake |
| --- | --- | --- |
| `provider` | Selects the template and VMID range used to create a disposable clone | Pointing at a normal VM instead of a stopped template |
| `guest` | Chooses how `oslab` talks to the VM | Assuming `auto` can work without QEMU Guest Agent/WinRM/SSH readiness |
| `fixtures` | Prepares guest state before artifact execution | Putting product execution here instead of in `artifact.command` |
| `artifact` | Defines what local file/folder is uploaded and how it runs | Forgetting `pathParam: artifactPath`, so CLI `--artifact-path` has nowhere to bind |
| `artifact.installCommand` | Installer-only setup command | Mixing install validation and product smoke validation into one command |
| `artifact.command` | Main command run after upload/install | Not writing the expected output file |
| `outputs.actual.path` | Remote path collected from the guest | Writing output somewhere else in the guest |
| `outputs.actual.adapter` | Normalizes raw output for assertions | Asserting against raw output shape instead of canonical shape |
| `assertions` | Defines pass/fail rules | Checking text that the adapter does not preserve |
| `reports` | Selects output formats | Expecting CI JUnit without enabling `junit` |
| `cleanup` | Controls VM deletion/retention | Keeping failed VMs without later checking the VMID range |

## Clone Settings

`provider.clone` changes the disposable clone right after Proxmox creates it. The template itself never changes.

```yaml
provider:
  clone:
    display: virtio
    network: disconnected
```

| Field | Values | Effect on the clone |
| --- | --- | --- |
| `display` | `std`, `virtio` | Sets the display adapter (Proxmox `vga`). Use it when the template uses a serial display (`vga: serial0`) and you want to watch or record the VNC console. |
| `network` | `disconnected` | Sets `link_down=1` on every network device. Use it when the template's cloud-init settings would give every clone the same fixed address, such as `192.168.0.10/24`. QEMU Guest Agent does not need the network. |

Leaving a field out keeps the template value. Guests that wait for the network while booting start more slowly with `network: disconnected`. Ubuntu cloud images wait about two minutes for `systemd-networkd-wait-online` to time out before QEMU Guest Agent answers.

## Guest Screen

`guest.screen` controls what the VM screen shows during a run.

| Field | Meaning |
| --- | --- |
| `showCommands` | Shows commands and their output on the VM screen. OSLAB still collects exit codes and output through the guest channel. |
| `signIn` | Windows only. Signs in to the Windows desktop before commands run. On Windows, `showCommands: true` requires `signIn: true`. |

Linux scenarios reject `signIn`. [Linux Guests](#linux-guests) describes the Linux console display.

[Windows Desktop Session](#windows-desktop-session) describes the Windows sign-in and the console windows.

## Fixture Example

Fixtures run before the artifact command. Use them for guest setup, not for the main product validation.

```yaml
fixtures:
  - id: demo-python-runtime
    type: powershell
    source: validation/fixtures/windows/demo-python-runtime.ps1
    expectedOutput: "C:\\Oslab\\demo-python-runtime.json"
```

| Field | Meaning |
| --- | --- |
| `id` | Stable fixture id used in logs and reports |
| `type` | Fixture runner type, `powershell` for Windows guests and `shell` for Linux guests |
| `source` | Local fixture script uploaded to the guest |
| `expectedOutput` | Optional guest path collected as fixture evidence |

If the fixture fails, the run should stop as `fixture_failure`. If the artifact command fails after setup succeeded, that should be reported separately as product/artifact execution failure.

See [Fixture Authoring](fixtures.md) for full fixture rules, manifest examples, and debugging commands.

## Command Template Tokens

| Token | Meaning |
| --- | --- |
| `{ArtifactDir}` | Remote artifact directory |
| `{InstallerPath}` | Remote installer path |
| `{OutputPath}` | Remote primary output path |
| `{AssetName}` | Generated/default asset name for product steps |

Unknown tokens are rejected when the command template is rendered before guest execution. `validate-scenario` checks schema shape; it is not a full dry run of every command token.

Tokens mean the same on Linux, with POSIX paths such as `/opt/oslab/artifact`.

## Product Step Stdout JSON Contract

Agent-like scenarios often use `product.steps` instead of a single `artifact.command`. If a step sets `captureStdoutJson: true`, stdout must contain one JSON object. `expectStdoutJson` can declare required values:

```yaml
product:
  steps:
    - id: scan
      command:
        shell: powershell
        template: '& "{ArtifactDir}\agent.exe" scan --wait --output "{OutputPath}" --json'
      captureStdoutJson: true
      expectStdoutJson:
        ok: true
        outputWritten: true
```

If a required field is missing or has a different value, the step fails as product execution failure. Dotted keys can address nested objects.

## Generic Demo Scenarios

| Scenario | Purpose |
| --- | --- |
| `scenarios/windows/demo-powershell-system.example.yaml` | Minimal PowerShell command-result demo |
| `scenarios/windows/demo-python-hello.example.yaml` | Bootstrap Python and run `hello.py` |
| `scenarios/windows/demo-c-hello.example.yaml` | Bootstrap TinyCC and compile/run `hello.c` |
| `scenarios/windows/demo-fixture-state.example.yaml` | Fixture writes VM state and artifact reads it |
| `scenarios/windows/demo-agent-steps.example.yaml` | Ordered product steps with stdout JSON and inventory output |
| `scenarios/windows/demo-python-unittest.example.yaml` | Python unit test execution inside the VM |
| `scenarios/windows/demo-python-http-service.example.yaml` | Python local HTTP service smoke test |
| `scenarios/windows/demo-c-unit.example.yaml` | Multi-file C compile/link/unit-test demo |
| `scenarios/windows/demo-intentional-assertion-failure.example.yaml` | Intentional assertion failure for report/JUnit learning |
| `scenarios/windows/fake-artifact-smoke.example.yaml` | Fake inventory-producing folder artifact |
| `scenarios/windows/fake-installer-smoke.example.yaml` | Fake installer then product command |
| `scenarios/linux/generic-smoke.example.yaml` | Linux system information demo over QEMU Guest Agent with a shell fixture, a tar.gz artifact, and commands shown on the VM console |

## Minimal Custom Artifact Examples

Folder artifact:

```yaml
artifact:
  type: folder
  pathParam: artifactPath
  destination: "C:\\Oslab\\artifact"
  transfer: archive
  command:
    shell: powershell
    template: '& "{ArtifactDir}\run-smoke.ps1" -OutputPath "{OutputPath}"'
outputs:
  actual:
    path: "C:\\Oslab\\command-result.json"
    adapter: canonical.command
```

Installer artifact:

```yaml
artifact:
  type: installer
  pathParam: artifactPath
  destination: "C:\\Oslab\\installer"
  installCommand:
    shell: powershell
    template: '& "{InstallerPath}" -InstallDir "C:\\Oslab\\installed"'
  command:
    shell: powershell
    template: '& "C:\\Oslab\\installed\\run-smoke.ps1" -OutputPath "{OutputPath}"'
outputs:
  actual:
    path: "C:\\Oslab\\command-result.json"
    adapter: canonical.command
```

In both cases, the command should write machine-readable output to `outputs.actual.path`. For `canonical.command`, write a `commandResult` JSON object.

## Artifact Command Output Contract

For `canonical.command`, the remote output file should look like this:

```json
{
  "schemaVersion": 1,
  "kind": "commandResult",
  "command": "python hello.py",
  "exitCode": 0,
  "stdout": "hello from python\n",
  "stderr": "",
  "metadata": {
    "runtime": "python",
    "files": [
      {
        "path": "C:\\Oslab\\demo-fixture-state.json",
        "exists": true,
        "length": 128
      }
    ],
    "directories": [
      {
        "path": "C:\\Oslab",
        "exists": true
      }
    ]
  }
}
```

Required fields:

| Field | Meaning |
| --- | --- |
| `schemaVersion` | Output schema version |
| `kind` | Must be `commandResult` for `canonical.command` |
| `command` | Human-readable command label |
| `exitCode` | Process exit code |
| `stdout` | Captured stdout text |
| `stderr` | Captured stderr text |
| `metadata` | Optional object for runtime/compiler/version/path/state details |

The artifact command may also write stdout/stderr to the console, but assertions use the collected JSON file. Console output alone is not enough for `canonical.command`.

State assertions such as `file.exists`, `file.notExists`, and `directory.exists` read checked state from `metadata.files` and `metadata.directories`. `oslab` does not guess guest state after the command finishes; the artifact command should report the paths it checked.

Minimal PowerShell writer:

```powershell
param(
  [Parameter(Mandatory = $true)]
  [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$stdout = "hello from my artifact"
$result = @{
  schemaVersion = 1
  kind = "commandResult"
  command = "run-smoke"
  exitCode = 0
  stdout = "$stdout`n"
  stderr = ""
  metadata = @{}
}

$result |
  ConvertTo-Json -Depth 10 |
  Set-Content -Encoding UTF8 $OutputPath
```

## Expected Run Flow

A passing folder-artifact scenario should follow this lifecycle:

```text
validate scenario
provider config/connectivity/resource preflight
allocate VMID
create ephemeral clone
start VM
wait for guest channel
run guest preflight
run fixtures
prepare artifact directory
upload artifact archive
expand artifact in guest
run artifact command
collect outputs.actual.path
normalize output with adapter
evaluate assertions
write reports
destroy VM clone
```

Expected progress markers:

```text
[OK] provider.preflight.done - Proxmox resource preflight passed
[OK] vm.clone.done - Ephemeral VM clone created
[OK] guest.ready.done - QEMU Guest Agent is ready
[OK] preflight.done - Guest preflight passed
[OK] fixture.all.done - Scenario fixtures applied
[OK] artifact.upload.done - Artifact folder uploaded
[OK] product.command.done - Product command completed
[OK] output.normalize.done - Product output normalized
[OK] assertions.done - Assertions passed
[OK] run.done - Run completed
    status: passed
    failureClass: <none>
```

Expected run files:

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
    fixture-<id>.expected-output.json
  normalized/
    command-result.json
  reports/
    result.junit.xml
    result.json
    result.html
```

## Windows Desktop Session

`guest.screen.signIn: true` signs a test account in to the Windows desktop before guest preflight. With `guest.screen.showCommands: true` as well, product commands run in a visible console window on that desktop. The desktop session is optional. With both settings omitted, commands use the regular QEMU Guest Agent path.

```yaml
guest:
  mode: qemuAgent
  screen:
    signIn: true
    showCommands: true
```

### Sign-In

1. OSLAB creates the local administrator account `OslabDesktop` with a random password. The guest generates the password and uses it only for the account and the automatic logon, so it never reaches OSLAB logs or reports.
2. It turns off the first sign-in animation, the privacy settings screen, notifications, setup reminders, OneDrive setup, and the Start menu that Windows may open after a first sign-in. It also keeps the display and the VM from going to sleep.
3. It enables automatic logon for one sign-in, restarts Windows, and waits until Explorer runs for `OslabDesktop`.
4. It attempts to remove the automatic logon password (`DefaultPassword`) from the registry and disables automatic logon, including when setup or sign-in fails. The run treats sign-in as passed only after it verifies the password is gone and automatic logon is off.

The result is recorded as the `desktop.sign_in` guest preflight check. A failed sign-in stops the run with `preflight_failure`. The test account, profile and presentation settings belong to the disposable clone and remain there while the clone is kept. The usual VM cleanup removes the clone at the end of the run.

| Progress phase | When |
| --- | --- |
| `desktop.signin.start` | OSLAB prepares the account and automatic logon |
| `desktop.signin.restart` | Windows restarts |
| `desktop.signin.wait` | OSLAB waits for the desktop session |
| `desktop.signin.done` or `desktop.signin.failed` | The desktop is signed in, or the sign-in failed. Details include `user`, `seconds`, and `autologonPasswordRemoved`. |

### Commands In Console Windows

With `showCommands: true`, the installer command, the artifact command, and every product step run in a console window of the signed-in session.

- The window title is `OSLab · <step>`, where `<step>` is the product step id, `install`, or `command`.
- Every window opens at the same position and size, 120 pixels from the left and 80 pixels from the top, 1040x620 pixels, with 24 px Consolas text (Cascadia Mono when Consolas is missing). The rectangle fits the 1280x800 desktop of the default Proxmox display. On a smaller screen the window is cut to fit.
- The window shows the command after `PS>` (or `>` for `cmd`). When the command finishes, it shows a preview of stdout and stderr, with stderr in red, and the exit code. Each window closes on its own within two minutes of the result. A later command can open another window over it.
- The window uses UTF-8, so paths show backslashes on Korean and Japanese Windows too, and UTF-8 or code page output appears in its own language. The command itself still runs in a hidden console with the system code page, as under QEMU Guest Agent.
- Literal values supplied through `secretTokens` appear as `<redacted>` in the displayed command line and output preview.
- OSLAB collects stdout, stderr and the exit code for logs and assertions. After collection, it unregisters the command's scheduled task and removes the command's temporary files. `--command-timeout-seconds` still applies. On timeout it stops the scheduled task and its command process tree. The run reports `guest_execution_timeout`.

The commands run as `OslabDesktop` with administrator rights in the desktop session, where QEMU Guest Agent would run them as SYSTEM. `%USERPROFILE%`, `%TEMP%`, `%APPDATA%`, and `HKCU` therefore refer to the desktop account. Fixtures, the guest preflight, and output collection still use QEMU Guest Agent.

| Progress phase | Details |
| --- | --- |
| `desktop.console.setup.done` | Once, after the console helper is ready. `left`, `top`, `width`, `height`, `fontSize` |
| `desktop.console.start` | Before each command. `title` and the requested `left`, `top`, `width`, `height` |
| `desktop.console.done` | After each command. `title`, `exitCode`, `seconds`, the rectangle Windows applied (`left`, `top`, `width`, `height`), `screenWidth`, `screenHeight`, and `font` (for example `Consolas 24`) |
| `desktop.console.failed` | The command timed out, or the console could not run it |

### Template Requirements

The template needs QEMU Guest Agent, the C# compiler of .NET Framework 4 (`csc.exe`, included in Windows 10 and 11), and the ScheduledTasks PowerShell module. OSLAB compiles a small console helper in the guest and opens the console windows through a scheduled task. The feature has been tested with a Windows 11 25H2 template.

Automatic logon works for one sign-in. If a command restarts Windows, the desktop does not sign in again and later console commands fail.

## Linux Guests

Linux scenarios run through QEMU Guest Agent. Set `os.family: linux` and `guest.mode: qemuAgent`. With `guest.mode: auto`, leave `linuxOrder` unset or include `qemuAgent` in its list.

The template needs `agent: 1` in Proxmox and a running `qemu-guest-agent` that allows `guest-exec` and the `guest-file-*` commands. The guest needs `sh` and standard Linux utilities. Archive transfer uses gzip-capable `tar` and GNU-style `cp -aT`. Large uploads use `sha256sum` and `mv -fT`. The text download fallback uses `base64`.

```yaml
os:
  family: linux
provider:
  type: proxmox
  template: ubuntu-24.04-template
  templateVmId: 9000
  vmIdRange:
    start: 9185
    end: 9189
  clone:
    display: virtio
    network: disconnected
guest:
  mode: qemuAgent
  screen:
    showCommands: true
fixtures:
  - id: baseline
    type: shell
    source: validation/fixtures/linux/generic-smoke.sh
artifact:
  type: folder
  pathParam: artifactPath
  destination: /opt/oslab/artifact
  transfer: archive
  command:
    shell: sh
    template: '"{ArtifactDir}/run-system-demo.sh" "{OutputPath}"'
outputs:
  actual:
    path: /opt/oslab/command-result.json
    adapter: canonical.command
```

| Item | Linux behavior |
| --- | --- |
| Commands | `shell: sh` or `shell: bash`. OSLAB runs the shell as the guest agent user, normally root, and passes substituted token values as positional arguments. |
| Guest preflight | During `oslab run`, `linux.shell` runs `uname -s` through `sh`, `oslab.directory` makes `/opt/oslab` writable, `oslab.file_roundtrip` writes and reads a test file, and `oslab.cleanup_test_file` removes it. |
| Fixtures | `type: shell`. The script is uploaded to `/opt/oslab/fixtures/<file name>` with LF line endings, made executable, and run by path. A shebang line picks the interpreter, and a script without one runs under `sh`. |
| `transfer: archive` | Uploads and unpacks a tar.gz in a temporary directory next to `destination`, then copies the contents into `destination`. Existing unrelated files in `destination` remain. OSLAB removes the staging directory. |
| `transfer: files` | Creates directories with `mkdir -p` and uploads each file separately. This is the default for folder artifacts. |
| Executable files | Files with a shebang, an ELF signature or a local execute bit become executable. The archive uses mode 0755 for these files and mode 0644 for others. |
| Installer artifacts | The file is uploaded to `destination` and made executable. `{InstallerPath}` is `destination`, and `{ArtifactDir}` is its parent directory. |
| Default output path | `/opt/oslab/result.json` when `outputs.actual.path` is not set. |
| Large files | Uploads beyond the guest agent's file-write limit (60 KiB encoded) use temporary parts. OSLAB joins the parts and verifies their SHA-256 before moving the assembled file into place. |

Use an absolute POSIX path in the disposable guest for `artifact.destination`. A folder artifact uses that path as a directory, and an installer uses it as the uploaded filename. Artifact files are uploaded byte for byte, so keep LF line endings in shell scripts. The repository's `.gitattributes` does this for `*.sh` files on Windows checkouts. [Example that writes a `commandResult` JSON file](../validation/artifacts/linux-system/run-system-demo.sh)

`guest-preflight` and `fixture-smoke` still support Windows only. To debug a Linux fixture, run the scenario with `oslab run --keep-vm` and inspect the clone with `oslab qga-exec -- sh -c '...'`. The `qga-upload` and `qga-download` helpers use Windows commands for large uploads and for the read fallback.

### Commands On The Linux Console

With `guest.screen.showCommands: true`, OSLAB turns the first text console (tty1) into a command display.

1. Before the first command, it stops the `getty@tty1` login prompt so the prompt cannot redraw over the display. It then loads a Terminus 32x16 font when the guest has `setfont` and a framebuffer console, clears the screen, and prints a prompt such as `root@<host>:/# `.
2. The prompt shows each fixture, install command, product command and product step in readable form after token substitution. Its stdout and stderr follow, then a fresh prompt. A non-zero exit code adds `[exit N]`.
3. When the scenario uses `secretTokens`, the display masks their literal values with `<redacted>` and withholds command output from tty1.

The exit code, stdout, and stderr that OSLAB records still come from QEMU Guest Agent, so the display does not change results. If tty1 is missing or not writable, commands run without the display.

The text size depends on the console the guest kernel provides. On the Ubuntu 24.04 cloud image:

| `provider.clone.display` | Console |
| --- | --- |
| `std` | VGA text console, 720x400 pixels (80x25). The kernel has no `bochs` DRM driver, so the large font cannot load. |
| `virtio` | virtio-gpu framebuffer console, 1280x800 pixels. Terminus 32x16 gives 80x25 large characters. |

## Product-Specific Scenarios

Product-specific scenarios should be documented in product-owned docs outside the generic scenario authoring path. The generic docs should explain the platform contract, not one private product workflow.
