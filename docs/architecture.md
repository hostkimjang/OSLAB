# Architecture

The original product-specific architecture note has moved to private/product-owned docs and is no longer the public architecture entry point.

For the product-neutral `oslab` platform architecture, start here:

- [docs/index.md](index.md)
- [docs/concepts.md](concepts.md)
- [docs/scenarios.md](scenarios.md)
- [docs/proxmox-connection.md](proxmox-connection.md)
- [docs/reports.md](reports.md)
- [docs/oslab-platform-plan.md](oslab-platform-plan.md)

## VM Computer Use MCP

The local MCP server connects to a running VM's Proxmox VNC console to capture its screen and send clicks and keystrokes. The Proxmox API grants console access and the VNC WebSocket carries the screen and input. [Implementation and tools](computer-use-mcp.md)
