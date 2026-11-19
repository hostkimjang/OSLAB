"""Local MCP entry point for graphical Proxmox VM consoles."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from oslab.config import load_config
from oslab.env_file import load_env_file
from oslab.errors import OslabError, ProviderError
from oslab.providers.base import VmRef
from oslab.providers.proxmox import ProxmoxClient, proxmox_config_from_oslab

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from oslab.providers.proxmox_console import ConsoleConnection


@dataclass(frozen=True)
class Frame:
    id: str
    width: int
    height: int


@dataclass
class VmConsole:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    target: VmRef | None = None
    stack: AsyncExitStack | None = None
    connection: ConsoleConnection | None = None
    frame: Frame | None = None

    async def close(self) -> None:
        stack, self.stack = self.stack, None
        self.connection = None
        self.frame = None
        if stack is not None:
            await stack.aclose()


def build_server(client: ProxmoxClient, vm_ids: set[int] | range) -> FastMCP:
    from anyio import CancelScope
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ImageContent, TextContent

    from oslab.providers.proxmox_console import open_console

    consoles: dict[int, VmConsole] = {}
    permission_requests = asyncio.Semaphore(8)

    async def visible_vms() -> dict[int, VmRef]:
        try:
            resources = await asyncio.to_thread(client.list_vm_resources)
        except ProviderError as exc:
            status = exc.details.get("status")
            detail = f" (HTTP {status})" if isinstance(status, int) else ""
            raise ProviderError(f"Could not list Proxmox VMs{detail}.") from None
        vms = {}
        for resource in resources:
            vm_id = resource.get("vmid")
            node = resource.get("node")
            name = resource.get("name")
            if (
                isinstance(vm_id, int)
                and vm_id in vm_ids
                and resource.get("type") == "qemu"
                and not resource.get("template")
                and resource.get("status") == "running"
                and isinstance(node, str) and node
                and isinstance(name, str) and name
                and (not isinstance(vm_ids, range) or name.lower().startswith("oslab-"))
            ):
                vms[vm_id] = VmRef(vm_id, name, node)
        return vms

    async def has_console_access(vm_id: int) -> bool:
        try:
            async with permission_requests:
                return await asyncio.to_thread(client.has_vm_console_permission, vm_id)
        except ProviderError as exc:
            status = exc.details.get("status")
            detail = f" (HTTP {status})" if isinstance(status, int) else ""
            raise ProviderError(f"Could not check Proxmox console permission for VM {vm_id}{detail}.") from None

    async def require_available_vm(vm_id: int) -> VmRef:
        vm = (await visible_vms()).get(vm_id)
        if vm is None or not await has_console_access(vm_id):
            raise ProviderError(f"VM {vm_id} must be a visible, running QEMU VM with console permission.")
        return vm

    def get_console(vm_id: int) -> VmConsole | None:
        if vm_id not in vm_ids:
            raise OslabError(f"VM {vm_id} is outside the configured VM scope.")
        return consoles.get(vm_id)

    @asynccontextmanager
    async def connected(console: VmConsole, vm_id: int, *, checked_vm: VmRef | None = None):
        try:
            vm = checked_vm if checked_vm is not None else await require_available_vm(vm_id)
            if console.target is not None and vm != console.target:
                raise ProviderError(f"The identity of VM {vm_id} changed. Check the target and restart the MCP server.")
            if console.connection is None:
                async with AsyncExitStack() as stack:
                    console.connection = await stack.enter_async_context(open_console(client, vm))
                    console.stack = stack.pop_all()
                    console.target = vm
            yield console.connection
        except (ProviderError, asyncio.CancelledError):
            # Never replay an input after an interrupted console operation.
            with CancelScope(shield=True):
                await console.close()
            raise

    @asynccontextmanager
    async def lifespan(_server: FastMCP):
        try:
            yield
        finally:
            with CancelScope(shield=True):
                await asyncio.gather(*(console.close() for console in consoles.values()))

    server = FastMCP(
        "OSLab VM Computer Use",
        instructions=(
            "Use list_vms to find a VM and screenshot to see its desktop. "
            "Send input to the same vm_id with the latest screenshot's frame_id. "
            "Take another screenshot to inspect the result."
        ),
        lifespan=lifespan,
    )

    @server.tool()
    async def list_vms() -> list[dict[str, int | str | None]]:
        """List running QEMU VMs in scope that this server can access with console permission."""
        vms = sorted((await visible_vms()).values(), key=lambda vm: vm.vm_id)
        allowed = await asyncio.gather(*(has_console_access(vm.vm_id) for vm in vms))
        return [
            {"vm_id": vm.vm_id, "name": vm.name, "node": vm.node}
            for vm, has_access in zip(vms, allowed)
            if has_access
        ]

    @server.tool(structured_output=False)
    async def screenshot(vm_id: int) -> list:
        """Capture a VM desktop as a PNG. Use its frame_id and pixel size for clicks."""
        console = get_console(vm_id)
        checked_vm = None
        if console is None:
            checked_vm = await require_available_vm(vm_id)
            new_console = VmConsole()
            console = consoles.setdefault(vm_id, new_console)
            if console is not new_console:
                checked_vm = None
        async with console.lock, connected(console, vm_id, checked_vm=checked_vm) as connection:
            png, width, height = await connection.screenshot()
            frame = Frame(uuid4().hex, width, height)
            console.frame = frame
        return [
            TextContent(type="text", text=json.dumps({
                "vm_id": vm_id, "frame_id": frame.id, "width": width, "height": height,
            })),
            ImageContent(type="image", mimeType="image/png", data=base64.b64encode(png).decode("ascii")),
        ]

    @server.tool()
    async def click(
        vm_id: int, frame_id: str, x: int, y: int, button: Literal["left", "middle", "right"] = "left",
    ) -> str:
        """Click a pixel in the VM's latest screenshot. The top-left pixel is (0, 0)."""
        console = get_console(vm_id)
        if console is None:
            raise OslabError("Use the frame_id from the latest screenshot of this VM.")
        async with console.lock:
            frame = console.frame
            if frame is None or frame.id != frame_id:
                raise OslabError("Use the frame_id from the latest screenshot of this VM.")
            if not (0 <= x < frame.width and 0 <= y < frame.height):
                raise OslabError("Click coordinates are outside the screenshot.")
            async with connected(console, vm_id) as connection:
                await connection.click(x, y, button)
        return "Click sent."

    @server.tool()
    async def move_mouse(vm_id: int, frame_id: str, x: int, y: int) -> str:
        """Move the pointer to a pixel in the VM's latest screenshot without clicking, to hover or before a click."""
        console = get_console(vm_id)
        if console is None:
            raise OslabError("Use the frame_id from the latest screenshot of this VM.")
        async with console.lock:
            frame = console.frame
            if frame is None or frame.id != frame_id:
                raise OslabError("Use the frame_id from the latest screenshot of this VM.")
            if not (0 <= x < frame.width and 0 <= y < frame.height):
                raise OslabError("Pointer coordinates are outside the screenshot.")
            async with connected(console, vm_id) as connection:
                await connection.move(x, y)
        return "Pointer moved."

    @server.tool()
    async def press_key(vm_id: int, keys: list[str], frame_id: str | None = None) -> str:
        """Press a key or chord in a captured VM. Supply its latest frame_id to check the target."""
        console = get_console(vm_id)
        if console is None:
            raise OslabError(f"Take a screenshot of VM {vm_id} before sending input.")
        async with console.lock:
            frame = console.frame
            if frame is None:
                raise OslabError(f"Take a screenshot of VM {vm_id} before sending input.")
            if frame_id is not None and frame.id != frame_id:
                raise OslabError("Use the frame_id from the latest screenshot of this VM.")
            async with connected(console, vm_id) as connection:
                await connection.press_key(keys)
        return "Keys sent."

    @server.tool()
    async def close_console(vm_id: int) -> str:
        """Disconnect this VM's console. The VM keeps running."""
        console = get_console(vm_id)
        if console is not None:
            async with console.lock:
                with CancelScope(shield=True):
                    await console.close()
        return "Console closed."

    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve OSLab VM computer use over MCP stdio.")
    parser.add_argument("--config", type=Path, required=True, help="OSLab local YAML config.")
    parser.add_argument("--env-file", type=Path, help="Read missing environment variables from this file.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--vm-id", type=int, action="append", help="A controllable VMID. Repeat for multiple VMs.")
    scope.add_argument(
        "--vm-id-range", type=int, nargs=2, metavar=("START", "END"),
        help="Discover running OSLab VMs in this inclusive VMID range.",
    )
    args = parser.parse_args()
    if any(vm_id < 100 or vm_id > 999999999 for vm_id in (args.vm_id or args.vm_id_range)):
        parser.error("VMIDs must be between 100 and 999999999")
    vm_ids: set[int] | range
    if args.vm_id_range is not None:
        start, end = args.vm_id_range
        if start > end:
            parser.error("--vm-id-range START must be less than or equal to END")
        vm_ids = range(start, end + 1)
    else:
        vm_ids = set(args.vm_id)
    try:
        if args.env_file is not None:
            load_env_file(args.env_file)
        config = proxmox_config_from_oslab(load_config(args.config))
        server = build_server(ProxmoxClient(config), vm_ids)
    except ModuleNotFoundError as exc:
        if exc.name not in {"anyio", "cryptography", "mcp", "PIL", "websockets"}:
            raise
        print("Install the MCP dependencies with: uv sync --extra computer-use", file=sys.stderr)
        return 1
    except OslabError as exc:
        print(exc.message, file=sys.stderr)
        return exc.exit_code
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
