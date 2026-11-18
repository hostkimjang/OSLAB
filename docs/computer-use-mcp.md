# VM Computer Use MCP

English | [한국어](computer-use-mcp.ko.md)

`oslab-mcp` captures the screen of a running Proxmox QEMU VM and sends clicks and key presses to that VM. It works while the VM is running with its console window closed. The host mouse and keyboard remain available, and GUI control works independently of the QEMU Guest Agent.

The OSLab CLI can clone and boot a test VM as part of a scenario. The MCP server attaches to a selected running VM. Windows needs no separate computer-use software. The server can capture and send input to the sign-in screen. Sign in before working with desktop apps such as Notepad.

## Set up a client

- Start a test VM with a graphical console and note its VMID. Pixel clicks require an absolute pointing device. The default Proxmox QEMU USB tablet provides one. Add `--keep-vm` when running a scenario if you plan to connect to its clone afterward. [Getting started](getting-started.md)
- Use an OSLab config and environment file. You can omit `--env-file` if the token variables are already in the environment. The API token needs access to see the target VM and the `VM.Console` privilege. Any proxy in the connection path needs to pass the console WebSocket. [Proxmox connection guide](proxmox-connection.md)
- Use a local stdio MCP client that passes tool images to its model.

For CLI setup, see the README's [Codex setup and Notepad demo](../README.md#codex-mcp). If an open chat does not show `oslab` after registration, restart the desktop app, reopen the same chat, and check `/mcp`. [Codex MCP setup](https://learn.chatgpt.com/docs/extend/mcp#configure-in-the-chatgpt-desktop-app)

<a id="claude-code"></a>
### Claude Code

Use `--scope user` to make OSLab available across projects for your OS account. The registration also applies to local sessions in Claude Desktop's Code tab. Claude launches the same local stdio server as Codex. The VM allowlist still applies in every project. [Claude Code user scope](https://code.claude.com/docs/en/mcp#user-scope) · [Claude Desktop Code tab](https://code.claude.com/docs/en/desktop#mcp-servers-from-the-claude-desktop-chat-app)

Run this PowerShell example from the OSLab checkout and enter the VMID of your test VM. To allow more VMs, add one `--vm-id` option for each VMID.

```powershell
$repoPath = (Get-Location).Path
$uvPath = (Get-Command uv -CommandType Application).Source
$vmId = Read-Host 'Test VMID'
claude mcp add --transport stdio --scope user oslab -- $uvPath --directory $repoPath `
  run --locked --extra computer-use oslab-mcp --config config/oslab.local.yaml `
  --env-file config/oslab.local.env --vm-id $vmId
claude mcp get oslab
```

Start a Claude Code session and use `/mcp` to check that `oslab` is connected.

<a id="claude-desktop"></a>
### Claude Desktop chat

In Claude Desktop, open **Settings → Developer → Edit Config**. Add `oslab` alongside any existing entries in `mcpServers` in `claude_desktop_config.json`. Use the absolute path to `uv` as the command and the absolute path to the OSLab checkout after `--directory`. Replace the sample VMIDs `123` and `124` with the VMIDs you want to allow. The same entry works with other local clients that accept `mcpServers`. [MCP client setup](https://py.sdk.modelcontextprotocol.io/get-started/real-host/)

```json
{
  "mcpServers": {
    "oslab": {
      "command": "C:/path/to/uv.exe",
      "args": [
        "--directory", "C:/path/to/oslab",
        "run", "--locked", "--extra", "computer-use", "oslab-mcp",
        "--config", "config/oslab.local.yaml",
        "--env-file", "config/oslab.local.env",
        "--vm-id", "123",
        "--vm-id", "124"
      ]
    }
  }
}
```

Fully quit Claude Desktop and reopen it. Check that `oslab` appears in the chat's tool list. [Claude Desktop setup](https://py.sdk.modelcontextprotocol.io/get-started/real-host/#claude-desktop)

### Verify the connection

Try the following request in Codex, Claude Code, or Claude Desktop.

> Use OSLab to list the allowed VMs. Capture the test VM's screen and describe one visible detail from the image.

A VM listing checks the Proxmox API connection. A description based on the captured screen checks that the client passes MCP images to the model.

## Capture and control the VM

| Tool | Behavior |
| --- | --- |
| `list_vms()` | Returns the `vm_id`, `name`, and `node` of running QEMU VMs in the allowlist that the token can see. |
| `screenshot(vm_id)` | Opens the console and returns a PNG plus `vm_id`, `frame_id`, `width`, and `height`. |
| `click(vm_id, frame_id, x, y, button="left")` | Clicks pixel coordinates in the VM's latest frame, with `(0, 0)` at the top left. Buttons are `left`, `middle`, and `right`. |
| `move_mouse(vm_id, frame_id, x, y)` | Moves the pointer to pixel coordinates in the VM's latest frame without clicking. Use it to hover or to move the pointer before a click. |
| `press_key(vm_id, keys)` | Sends a key or a chord to a VM after its first capture. Examples include `['Enter']`, `['Win', 'r']`, and `['Ctrl', 'a']`. Single-character keys cover printable ASCII. |
| `close_console(vm_id)` | Closes the console connection. The VM stays running. |

Use `list_vms` to identify the VM and `screenshot` to see its desktop. Take another screenshot when a new window opens or the layout changes so you have the new positions and `frame_id`. Each `press_key` call sends one key or one simultaneous chord. Use one call per character for text. The guest's keyboard layout and input method determine the resulting text.

### Verify a saved document in a Windows VM

1. Capture the signed-in desktop. Send `['Win', 'r']`, then type `notepad` one character at a time in the Run dialog and press `Enter`.
2. Capture the Notepad window, click the editor, and type `oslab mcp ok`. Use `Ctrl+F` to search for the same text and check that Notepad highlights it.
3. Use `Ctrl+S` to open the save dialog and save under a new name in Documents. Close the Notepad tab. Open File Explorer with `Win+E`, find the file in Documents, and open it.
4. Capture the reopened document and check its filename and contents.

Call `close_console` when you finish. For a test VM kept with `--keep-vm`, verify the VMID and ownership before cleaning up. [VM cleanup procedure](proxmox-connection.md#stale-vm-and-vmid-range-recovery)

## How it works

1. **Select a VM.** The MCP client speaks stdio to the local `oslab-mcp` process. The server loads the OSLab Proxmox configuration and finds running QEMU VMs the token can see within the `--vm-id` allowlist. The first screenshot opens a connection to the selected VM. [MCP tools and sessions](../src/oslab/mcp_server.py)
2. **Authenticate to the console.** The OSLab Proxmox REST client uses its API token to get a short-lived console ticket from the VM's `vncproxy` endpoint. The transport connects to that VM's `vncwebsocket` endpoint and completes VNC authentication. An HTTPS API URL uses WSS for the console. [Proxmox console transport](../src/oslab/providers/proxmox_console.py)
3. **Capture and send input.** The transport converts a full RFB (Remote Framebuffer) 3.7/3.8 frame to a PNG and returns it as an MCP image. When the screen size changes, it requests a new frame at that size. Pixel clicks and key down/up events travel over RFB to the guest's QEMU virtual input devices. [RFB specification](https://www.rfc-editor.org/rfc/rfc6143.html#section-7.5)

Within an MCP process each VM has a separate WebSocket, latest frame, and lock that serializes requests. Different VMs can be controlled concurrently. Manual viewers and other MCP processes connected to the same VM share its guest screen and input devices.

Clicks and pointer moves require the latest `frame_id` for the target VM and coordinates within that frame. If an error or timeout interrupts the console, capture the VM again to reconnect. Interrupted input is never replayed automatically. Inspect the screen before retrying an action. If the node or name for a VMID changes between connections, verify the target and restart the MCP server. Closing a console or stopping the MCP process releases connections and leaves VM power unchanged.

### Run the tests

```powershell
uv run --locked --extra computer-use python -m pytest -q tests/test_mcp_server.py tests/test_proxmox_console.py
```

These tests use simulated Proxmox responses to check VM scope, concurrent requests, reconnection, frame decoding, and input events. Run the Windows walkthrough to verify the console path and guest input in a live lab.
