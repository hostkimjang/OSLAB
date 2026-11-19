import asyncio
import base64
import json
import sys
from contextlib import asynccontextmanager
from datetime import timedelta
from io import BytesIO
from unittest.mock import Mock

import pytest

pytest.importorskip("mcp")
pytest.importorskip("PIL")
pytest.importorskip("websockets")
pytest.importorskip("cryptography")

from mcp.shared.memory import create_connected_server_and_client_session
from PIL import Image

from oslab import mcp_server
from oslab.errors import ProviderError
from oslab.mcp_server import build_server
from oslab.providers import proxmox_console


def vm_resource(vm_id, **overrides):
    return {
        "vmid": vm_id,
        "name": f"oslab-test-{vm_id}",
        "node": "lab",
        "type": "qemu",
        "status": "running",
        **overrides,
    }


class FakeLab:
    def __init__(self):
        self.resources = [vm_resource(101), vm_resource(102)]
        self.opened = []
        self.closed = []
        self.inputs = {101: [], 102: []}
        self.console_denied = set()
        self.permission_error = None
        self.permission_queries = []
        self.failing_vm = None
        self.click_barrier = None

    def list_vm_resources(self):
        return self.resources

    def has_vm_console_permission(self, vm_id):
        self.permission_queries.append(vm_id)
        if self.permission_error is not None:
            raise self.permission_error
        return vm_id not in self.console_denied

    @asynccontextmanager
    async def open_console(self, _client, vm):
        self.opened.append(vm.vm_id)
        try:
            yield FakeConsole(self, vm.vm_id)
        finally:
            self.closed.append(vm.vm_id)


class FakeConsole:
    def __init__(self, lab, vm_id):
        self.lab = lab
        self.vm_id = vm_id

    async def screenshot(self):
        with BytesIO() as png:
            Image.new("RGB", (16, 9), (self.vm_id, 0, 0)).save(png, format="PNG")
            return png.getvalue(), 16, 9

    async def click(self, x, y, button):
        self.lab.inputs[self.vm_id].append(("click", x, y, button))
        if self.lab.click_barrier is not None:
            await self.lab.click_barrier.wait()

    async def move(self, x, y):
        self.lab.inputs[self.vm_id].append(("move", x, y))

    async def press_key(self, keys):
        self.lab.inputs[self.vm_id].append(("keys", keys))
        if self.lab.failing_vm == self.vm_id:
            raise ProviderError("Mock console disconnected.")


async def screen(session, vm_id):
    result = await session.call_tool("screenshot", {"vm_id": vm_id})
    assert not result.isError, result.content
    metadata, image = result.content
    frame = json.loads(metadata.text)
    assert frame["vm_id"] == vm_id
    assert (frame["width"], frame["height"]) == (16, 9)
    assert image.type == "image"
    assert image.mimeType == "image/png"
    with Image.open(BytesIO(base64.b64decode(image.data))) as png:
        assert png.format == "PNG"
        assert png.size == (frame["width"], frame["height"])
        assert png.getpixel((0, 0)) == (vm_id, 0, 0)
    return frame["frame_id"]


def test_mcp_limits_console_access_and_routes_parallel_input(monkeypatch):
    lab = FakeLab()
    lab.resources[1] = vm_resource(102, name="manual-102")
    lab.resources.extend([
        vm_resource(103, status="stopped"),
        vm_resource(104, type="lxc"),
        vm_resource(105, template=1),
        vm_resource(106),
        vm_resource(107),
    ])
    lab.console_denied.add(107)
    monkeypatch.setattr(proxmox_console, "open_console", lab.open_console)

    async def run():
        lab.click_barrier = asyncio.Barrier(2)
        server = build_server(lab, {101, 102, 103, 104, 105, 107})
        async with create_connected_server_and_client_session(
            server, read_timeout_seconds=timedelta(seconds=5)
        ) as session:
            listed = await session.call_tool("list_vms")
            assert not listed.isError
            assert listed.structuredContent == {
                "result": [
                    {"vm_id": 101, "name": "oslab-test-101", "node": "lab"},
                    {"vm_id": 102, "name": "manual-102", "node": "lab"},
                ],
            }
            for vm_id in (103, 104, 105, 106, 107):
                assert (await session.call_tool("screenshot", {"vm_id": vm_id})).isError
            assert set(lab.permission_queries) == {101, 102, 107}
            assert (await session.call_tool("press_key", {"vm_id": 101, "keys": ["Enter"]})).isError

            old_frame = await screen(session, 101)
            frame_a, frame_b = await asyncio.gather(screen(session, 101), screen(session, 102))
            assert frame_a != old_frame
            for tool in ("click", "move_mouse"):
                for frame_id, x in [(old_frame, 1), (frame_b, 1), (frame_a, 16)]:
                    result = await session.call_tool(
                        tool, {"vm_id": 101, "frame_id": frame_id, "x": x, "y": 2},
                    )
                    assert result.isError
            for frame_id in (old_frame, frame_b):
                result = await session.call_tool("press_key", {"vm_id": 101, "frame_id": frame_id, "keys": ["Enter"]})
                assert result.isError
            assert lab.inputs == {101: [], 102: []}

            moved = await session.call_tool("move_mouse", {"vm_id": 101, "frame_id": frame_a, "x": 15, "y": 8})
            assert not moved.isError
            assert moved.content[0].text == "Pointer moved."
            clicks = await asyncio.gather(
                session.call_tool("click", {"vm_id": 101, "frame_id": frame_a, "x": 2, "y": 3}),
                session.call_tool(
                    "click", {"vm_id": 102, "frame_id": frame_b, "x": 14, "y": 8, "button": "right"},
                ),
            )
            assert all(not result.isError for result in clicks)
            keyed = await session.call_tool("press_key", {"vm_id": 101, "frame_id": frame_a, "keys": ["Enter"]})
            assert not keyed.isError
            assert not (await session.call_tool("press_key", {"vm_id": 102, "keys": ["Ctrl", "a"]})).isError
            assert lab.inputs == {
                101: [("move", 15, 8), ("click", 2, 3, "left"), ("keys", ["Enter"])],
                102: [("click", 14, 8, "right"), ("keys", ["Ctrl", "a"])],
            }

        assert sorted(lab.closed) == [101, 102]

    asyncio.run(run())


@pytest.mark.parametrize("scope_args", [
    [],
    ["--vm-id-range", "101", "108", "--vm-id", "101"],
    ["--vm-id", "99"],
    ["--vm-id-range", "108", "101"],
    ["--vm-id-range", "99", "108"],
    ["--vm-id-range", "101", "1000000000"],
])
def test_mcp_cli_rejects_missing_conflicting_or_invalid_scope(monkeypatch, scope_args):
    monkeypatch.setattr(sys, "argv", ["oslab-mcp", "--config", "unused.yaml", *scope_args])
    with pytest.raises(SystemExit) as exc:
        mcp_server.main()
    assert exc.value.code == 2


def test_mcp_cli_uses_inclusive_discovery_range(monkeypatch):
    lab = FakeLab()
    build_server_mock = Mock()
    monkeypatch.setattr(sys, "argv", ["oslab-mcp", "--config", "unused.yaml", "--vm-id-range", "101", "108"])
    monkeypatch.setattr(mcp_server, "load_config", Mock())
    monkeypatch.setattr(mcp_server, "proxmox_config_from_oslab", Mock())
    monkeypatch.setattr(mcp_server, "ProxmoxClient", Mock(return_value=lab))
    monkeypatch.setattr(mcp_server, "build_server", build_server_mock)

    assert mcp_server.main() == 0
    build_server_mock.assert_called_once_with(lab, range(101, 109))
    build_server_mock.return_value.run.assert_called_once_with(transport="stdio")


def test_mcp_discovers_late_running_qemu_clone_with_console_permission(monkeypatch):
    lab = FakeLab()
    lab.resources = [
        vm_resource(101, name="oslab-release-legacy-gui-change-101"),
        vm_resource(103, status="stopped"),
        vm_resource(104, type="lxc"),
        vm_resource(105, template=1),
        vm_resource(106),
        vm_resource(107, name="unrelated-running-workload"),
        vm_resource(109, name="oslab-outside-lab-range"),
    ]
    lab.console_denied.add(106)
    monkeypatch.setattr(proxmox_console, "open_console", lab.open_console)

    async def run():
        server = build_server(lab, range(101, 109))
        async with create_connected_server_and_client_session(
            server, read_timeout_seconds=timedelta(seconds=5)
        ) as session:
            listed = await session.call_tool("list_vms")
            assert not listed.isError
            assert listed.structuredContent == {
                "result": [{"vm_id": 101, "name": "oslab-release-legacy-gui-change-101", "node": "lab"}],
            }
            for vm_id in (102, 103, 104, 105, 106, 107, 109):
                assert (await session.call_tool("screenshot", {"vm_id": vm_id})).isError
            assert set(lab.permission_queries) == {101, 106}
            assert lab.opened == []

            lab.resources.append(vm_resource(108, name="OSLab-release-full-runtime-108", node="second-node"))
            listed = await session.call_tool("list_vms")
            assert not listed.isError
            assert listed.structuredContent == {
                "result": [
                    {"vm_id": 101, "name": "oslab-release-legacy-gui-change-101", "node": "lab"},
                    {"vm_id": 108, "name": "OSLab-release-full-runtime-108", "node": "second-node"},
                ],
            }
            await screen(session, 108)
            assert not (await session.call_tool("close_console", {"vm_id": 108})).isError
            assert (await session.call_tool("press_key", {"vm_id": 108, "keys": ["Enter"]})).isError
            assert lab.opened == lab.closed == [108]

    asyncio.run(run())


@pytest.mark.parametrize("access_loss", ["revoked", "invisible", "backend_error"])
def test_mcp_closes_open_console_when_access_cannot_be_confirmed(monkeypatch, access_loss):
    lab = FakeLab()
    monkeypatch.setattr(proxmox_console, "open_console", lab.open_console)

    async def run():
        server = build_server(lab, range(101, 109))
        async with create_connected_server_and_client_session(
            server, read_timeout_seconds=timedelta(seconds=5)
        ) as session:
            old_frame = await screen(session, 101)
            click = {"vm_id": 101, "frame_id": old_frame, "x": 1, "y": 1}
            if access_loss == "revoked":
                lab.console_denied.add(101)
            elif access_loss == "invisible":
                lab.resources.remove(vm_resource(101))
            else:
                lab.permission_error = ProviderError(
                    "private-token-marker", details={"status": 503, "body": "private-body-marker"},
                )

            denied = await session.call_tool("click", click)
            assert denied.isError
            assert lab.inputs[101] == []
            assert lab.closed == [101]
            if access_loss == "backend_error":
                assert "503" in denied.content[0].text
                assert "private-token-marker" not in denied.content[0].text
                assert "private-body-marker" not in denied.content[0].text

            lab.console_denied.clear()
            lab.resources = [vm_resource(101), vm_resource(102)]
            lab.permission_error = None
            assert (await session.call_tool("click", click)).isError
            new_frame = await screen(session, 101)
            assert new_frame != old_frame
            assert not (await session.call_tool("click", {**click, "frame_id": new_frame})).isError
            assert lab.opened == [101, 101]
            assert lab.inputs[101] == [("click", 1, 1, "left")]

        assert lab.closed == [101, 101]

    asyncio.run(run())


def test_mcp_recovers_one_console_without_replaying_input_or_switching_vms(monkeypatch):
    lab = FakeLab()
    monkeypatch.setattr(proxmox_console, "open_console", lab.open_console)

    async def run():
        server = build_server(lab, {101, 102})
        async with create_connected_server_and_client_session(
            server, read_timeout_seconds=timedelta(seconds=5)
        ) as session:
            await screen(session, 101)
            await screen(session, 102)
            lab.failing_vm = 101
            failed = await session.call_tool("press_key", {"vm_id": 101, "keys": ["Enter"]})
            assert failed.isError
            assert "Mock console disconnected" in failed.content[0].text
            assert lab.closed == [101]

            await screen(session, 102)
            old_frame = await screen(session, 101)
            assert lab.opened == [101, 102, 101]
            assert lab.inputs == {101: [("keys", ["Enter"])], 102: []}
            assert not (await session.call_tool("close_console", {"vm_id": 101})).isError
            assert (await session.call_tool(
                "click", {"vm_id": 101, "frame_id": old_frame, "x": 1, "y": 1},
            )).isError
            assert (await session.call_tool(
                "move_mouse", {"vm_id": 101, "frame_id": old_frame, "x": 1, "y": 1},
            )).isError

            lab.resources[0] = vm_resource(101, name="replacement-vm")
            replaced = await session.call_tool("screenshot", {"vm_id": 101})
            assert replaced.isError
            assert "identity" in replaced.content[0].text
            assert lab.opened == [101, 102, 101]

        assert lab.closed == [101, 101, 102]

    asyncio.run(run())
